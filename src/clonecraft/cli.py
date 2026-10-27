"""The clonecraft command line."""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, nullcontext
from pathlib import Path

from . import audio
from . import brandpack
from . import cards
from . import face_targets
from . import infinitetalk
from . import loudness
from . import models
from . import speechcheck
from . import timings
from . import voxcpm
from .browser import CHROME, Browser, ChromeBrowser
from .face import FaceEngine, FaceEngineError
from .gpu import GpuControl, GpuError, SystemGpu
from .handoff import VOICEOVER_NEEDED_MIB, Handoff, cleared_gpu
from .infinitetalk import InfiniteTalkEngine
from .project import (
    Channel,
    Format,
    ProjectError,
    choose_format,
    current_voiceover,
    likeness_path,
    load_channel,
    read_script,
)
from .script import ScriptParts, parts_of, pieces_of, spoken_fingerprint
from .frame import HOOK_BOX, PILL_BOX
from .video import BADGE_BOX, Faces, Hook, Pill, Stretch, assemble, faces_for, forget_unused, render_faces
from .voicesample import choose_voice_reference
from .voxcpm import VoxCpmEngine
from .voice import NotEnoughGpuMemory, VoiceEngine, VoiceEngineError, Word


# 16:9 is on: the 832x480 test render was approved on the RTX 5070 (ADR 0006).
SIXTEEN_BY_NINE_VERIFIED = True


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    voice_engine: VoiceEngine | None = None,
    face_engine: FaceEngine | None = None,
    gpu: GpuControl | None = None,
    browser: Browser | None = None,
    ask: Callable[[str], str] = input,
) -> int:
    parser = argparse.ArgumentParser(prog="clonecraft")
    commands = parser.add_subparsers(dest="command", required=True)
    voiceover = commands.add_parser("voiceover", help="make the Voiceover for a Script")
    voiceover.add_argument("channel", help="platform/@handle, for example youtube/@examplechannel")
    voiceover.add_argument("script", help="the Script's name, for example script-01")
    video = commands.add_parser("video", help="make the Video for a Script from its current Voiceover")
    video.add_argument("channel", help="platform/@handle, for example youtube/@examplechannel")
    video.add_argument("script", help="the Script's name, for example script-01")
    video.add_argument("--format", dest="aspect", help="the Format to make, such as 9:16 or 16:9, when the Channel has several")
    check_models = commands.add_parser("models", help="check the model files in models/ against config/models.toml")
    check_models.add_argument("--fix", action="store_true", help="download anything missing or wrong, then check again")
    args = parser.parse_args(argv)

    root = root or Path.cwd()
    try:
        if args.command == "models":
            return _models(root, args.fix)
        if args.command == "video":
            return _video(root, args.channel, args.script, args.aspect, voice_engine, face_engine, gpu, browser, ask)
        return _voiceover(root, args.channel, args.script, voice_engine, gpu, ask)
    except (ProjectError, VoiceEngineError, FaceEngineError, GpuError) as error:
        print(f"clonecraft: {error}", file=sys.stderr)
    except NotEnoughGpuMemory as error:
        print(
            f"clonecraft: not enough free GPU memory for the voice engine ({error}). "
            "Nothing was stopped; free some memory and run it again.",
            file=sys.stderr,
        )
    except KeyboardInterrupt:
        print("clonecraft: interrupted", file=sys.stderr)
        return 130
    return 1


def _voiceover(
    root: Path,
    channel_ref: str,
    script: str,
    voice_engine: VoiceEngine | None,
    gpu: GpuControl | None,
    ask: Callable[[str], str],
) -> int:
    channel = load_channel(root, channel_ref)
    parts = parts_of(read_script(channel, script), channel.script_path(script))
    pieces = pieces_of(parts.spoken)
    if not pieces:
        raise ProjectError(f"Script {script} has nothing to speak")
    if voice_engine is None:
        raise ProjectError(
            f"The voice engine is not installed yet ({', '.join(voxcpm.missing_parts(root))} missing); {voxcpm.INSTALL_HINT}"
        )
    reference = choose_voice_reference(root, channel.persona, ask)
    with _voice_engine_running(voice_engine, gpu, root, ask, "Voiceover") as handoff:
        with tempfile.TemporaryDirectory() as scratch:
            wavs: list[Path] = []
            for i, piece in enumerate(pieces):
                folder = Path(scratch) / f"piece-{i:03d}"
                folder.mkdir()
                wavs.append(speechcheck.speak(voice_engine, piece.text, piece.style, reference, folder))
            seconds = audio.assemble(wavs, channel.voiceover_path(script))
            channel.spoken_record_path(script).write_text(spoken_fingerprint(parts.spoken) + "\n")
        timings.save(voice_engine, channel.voiceover_path(script), channel.words_path(script))
    if handoff.not_restarted:
        raise GpuError(f"the Voiceover was made, but {', '.join(handoff.not_restarted)} could not be started again")
    print(f"Voiceover: {channel.voiceover_path(script)} ({seconds:.1f} s)")
    return 0


@contextmanager
def _voice_engine_running(
    voice_engine: VoiceEngine, gpu: GpuControl | None, root: Path, ask: Callable[[str], str], step: str
) -> Iterator[Handoff]:
    """Free GPU memory for the voice engine if it is short, asking first, and close the engine afterwards."""
    short = gpu is not None and gpu.free_mib() < VOICEOVER_NEEDED_MIB  # ask only when memory is actually short
    with cleared_gpu(gpu, root, ask, VOICEOVER_NEEDED_MIB, step) if gpu and short else nullcontext(Handoff()) as handoff:
        try:
            yield handoff
        finally:
            if isinstance(voice_engine, VoxCpmEngine):
                voice_engine.close()  # give its GPU memory back before the stopped services start again


def _models(root: Path, fix: bool) -> int:
    verdicts = models.check(root)
    errors: list[str] = []
    if fix:
        fixed, errors = models.fix(root, verdicts)
        for path in fixed:
            print(f"FIXED {path}")
        verdicts = models.check(root)
    for error in errors:
        print(f"clonecraft: {error}", file=sys.stderr)
    for verdict in verdicts:
        print(f"{verdict.problem or 'OK'} {verdict.model.path}")
    bad = [v for v in verdicts if v.problem]
    if bad or errors:
        print(f"{len(bad)} of {len(verdicts)} model files need attention")
        return 1
    print(f"all {len(verdicts)} model files are good")
    return 0


def _video(
    root: Path,
    channel_ref: str,
    script: str,
    aspect: str | None,
    voice_engine: VoiceEngine | None,
    face_engine: FaceEngine | None,
    gpu: GpuControl | None,
    browser: Browser | None,
    ask: Callable[[str], str],
) -> int:
    """Inputs are checked and the Slide cards drawn before the face engine's GPU handoff.

    Missing word timings are made first, with their own handoff, since they decide which Face sections exist. The
    face engine is needed only when a Face section has no kept clip.
    """
    started = time.monotonic()
    channel = load_channel(root, channel_ref)
    fmt = choose_format(channel, aspect)
    if fmt.aspect == "16:9" and not SIXTEEN_BY_NINE_VERIFIED:
        raise ProjectError(
            "Format 16:9 is not turned on yet: its render has not been verified on this machine (ADR 0006)"
        )
    parts = parts_of(read_script(channel, script), channel.script_path(script))
    voiceover = current_voiceover(channel, script)
    _check_voiceover_is_current(channel_ref, channel, script, parts.spoken)
    seconds = audio.seconds(voiceover)
    pack: brandpack.BrandPack | None = None
    if parts.uses_brand_pack:
        pack = brandpack.choose(root, channel.persona, channel)
        if browser is None:
            raise ProjectError(
                f"{CHROME} was not found on PATH; it draws the Slide cards and the hook "
                "(see docs/setup-and-maintenance.md)"
            )
    has_face = not parts.opens_with_card or any(card.kind == cards.FACE for card in parts.cards)
    likeness = likeness_path(root, channel.persona, fmt.aspect) if has_face else None
    timeline = [cards.Shown(None, 0.0, seconds)]  # a Script with no slides list is one continuous Face section
    warnings = cards.drift_warnings(timeline)
    # the word timings place the cards
    heard = _word_timings(root, channel, script, voiceover, voice_engine, gpu, ask) if parts.cards else []
    if parts.cards:
        timeline, warnings = cards.place(
            parts.cards, heard, seconds, voiceover, opening_face=not parts.opens_with_card,
            face_ends_after=parts.face_ends_after,
        )
    warnings.extend(face_targets.warnings(parts, timeline, heard, seconds))
    kept = channel.face_sections_path(script, fmt)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        stretches = [
            Stretch(shown.start, shown.end, None if shown.is_face else _drawn(shown, pack, browser, fmt, work, n, warnings))
            for n, shown in enumerate(timeline)
        ]
        hook = _hook(parts, timeline, pack, browser, work, warnings, channel.script_path(script))
        pill = _pill(pack, browser, work, stretches, warnings, channel.script_path(script))
        badge = _badge(pack, browser, work) if any(shown.is_face for shown in timeline) else None
        end_card = _end_card(pack, browser, fmt, work)
        faces = faces_for(stretches, likeness, voiceover, fmt, kept, work) if likeness else Faces([], [])
        face_seconds = 0.0
        not_restarted: list[str] = []
        if faces.to_render and likeness:  # likeness is always set here; the check is for mypy
            if face_engine is None:
                raise ProjectError(
                    f"The face engine is not installed yet ({', '.join(infinitetalk.missing_parts(root))} missing); "
                    f"{infinitetalk.INSTALL_HINT}"
                )
            with cleared_gpu(gpu, root, ask) if gpu else nullcontext(Handoff()) as handoff:  # no gpu: leave the GPU alone
                rendering = time.monotonic()
                render_faces(faces, likeness, fmt, face_engine, work)
                face_seconds = time.monotonic() - rendering
            not_restarted = handoff.not_restarted
        length = assemble(stretches, faces, voiceover, fmt, channel.video_path(script, fmt), hook, pill, badge, end_card)
    forget_unused(faces, kept)
    warnings.extend(loudness.qc_warnings(channel.video_path(script, fmt)))
    if not_restarted:
        raise GpuError(f"the Video was made, but {', '.join(not_restarted)} could not be started again")
    for warning in warnings:
        print(f"clonecraft: warning: {warning}", file=sys.stderr)
    shown_cards = sum(1 for s in stretches if s.is_card)
    print(
        f"Video: {channel.video_path(script, fmt)} ({fmt.aspect}; {length:.1f} s long; {shown_cards} Slide cards, "
        f"{'an end card, ' if end_card else ''}"
        f"{len(faces.clips)} Face sections, {len(faces.to_render)} rendered; "
        f"face engine {face_seconds:.1f} s, whole Video step {time.monotonic() - started:.1f} s)"
    )
    return 0


def _check_voiceover_is_current(channel_ref: str, channel: Channel, script: str, spoken: str) -> None:
    """Refuse a Video whose Voiceover was not made from the Script's current words (ADR 0008)."""
    record = channel.spoken_record_path(script)
    made_from = record.read_text().strip() if record.is_file() else None
    if made_from != spoken_fingerprint(spoken):
        raise ProjectError(
            f"The Voiceover {channel.voiceover_path(script)} was not made from the current words of "
            f"{channel.script_path(script)}; run `clonecraft voiceover {channel_ref} {script}` first"
        )


def _word_timings(
    root: Path, channel: Channel, script: str, voiceover: Path, voice_engine: VoiceEngine | None,
    gpu: GpuControl | None, ask: Callable[[str], str],
) -> list[Word]:
    """The Voiceover's saved word timings, made first with the voice engine when there are none."""
    heard = timings.load(voiceover, channel.words_path(script))
    if heard is not None:
        return heard
    if voice_engine is None:
        raise ProjectError(
            f"Voiceover {voiceover} has no word timings and the voice engine that makes them is not installed; "
            f"{voxcpm.INSTALL_HINT}"
        )
    with _voice_engine_running(voice_engine, gpu, root, ask, "Voiceover transcription") as handoff:
        heard = timings.save(voice_engine, voiceover, channel.words_path(script))
    if handoff.not_restarted:
        raise GpuError(f"the word timings were made, but {', '.join(handoff.not_restarted)} could not be started again")
    return heard


def _hook(
    parts: ScriptParts, timeline: list[cards.Shown], pack: brandpack.BrandPack | None, browser: Browser | None,
    work: Path, warnings: list[str], script_file: Path,
) -> Hook | None:
    """Draw the Script's hook for the opening Face section; it goes on that section's clip only, so it never runs past it."""
    if parts.hook is None:
        return None
    if not timeline[0].is_face:
        warnings.append(
            f"the hook is not shown in {script_file}: the Video opens on a Slide card, and the hook goes over the opening face"
        )
        return None
    assert pack is not None and browser is not None  # checked before anything was drawn
    if parts.hook.count("\n") > 1:
        warnings.append("the hook is more than two lines; it will crowd the face")
    page = pack.hook_page(parts.hook, work / "hook.html")
    browser.screenshot(page, *HOOK_BOX, page.with_suffix(".png"))
    return Hook(page.with_suffix(".png"), parts.hook_hold)


def _pill(
    pack: brandpack.BrandPack | None, browser: Browser | None, work: Path, stretches: list[Stretch], warnings: list[str],
    script_file: Path,
) -> Pill | None:
    """Draw the Brand pack's disclosure pill for the last Slide card; a Video with no card drawn leaves it out, with a warning."""
    if not any(stretch.is_card for stretch in stretches):
        if pack is not None:  # no pack means nothing was drawn in the Brand pack, so there is no disclosure to hold
            warnings.append(f"the disclosure is not shown in {script_file}: no Slide card is drawn in it")
        return None
    assert pack is not None and browser is not None  # checked before anything was drawn
    page = pack.pill_page(work / "pill.html")
    browser.screenshot(page, *PILL_BOX, page.with_suffix(".png"))
    return Pill(page.with_suffix(".png"))


def _badge(pack: brandpack.BrandPack | None, browser: Browser | None, work: Path) -> Path | None:
    """Draw the Brand pack's badge for the Face sections, when the pack has a wordmark."""
    if pack is None or pack.wordmark is None:
        return None
    assert browser is not None  # checked before anything was drawn
    page = pack.badge_page(work / "badge.html")
    browser.screenshot(page, *BADGE_BOX, page.with_suffix(".png"))
    return page.with_suffix(".png")


def _end_card(pack: brandpack.BrandPack | None, browser: Browser | None, fmt: Format, work: Path) -> Path | None:
    """Draw the Brand pack's end card at the Format's size, when the pack has one."""
    if pack is None or pack.end_card is None:
        return None
    assert browser is not None  # checked before anything was drawn
    page = pack.end_page(work / "end.html")
    browser.screenshot(page, fmt.width, fmt.height, page.with_suffix(".png"))
    return page.with_suffix(".png")


def _drawn(
    shown: cards.Shown, pack: brandpack.BrandPack | None, browser: Browser | None, fmt: Format, work: Path, n: int,
    warnings: list[str],
) -> Path:
    """Draw one Slide card, adding a warning when its text overflows or takes longer to read than it shows."""
    assert shown.card is not None and pack is not None and browser is not None  # checked before anything was drawn
    page = pack.page(shown.card, work / f"card-{n:03d}.html")
    picture = page.with_suffix(".png")
    browser.screenshot(page, fmt.width, fmt.height, picture)
    if not browser.fits(page, fmt.width, fmt.height):
        warnings.append(f"{shown.name}: its text runs outside the card")
    reading = cards.reading_seconds(f"{shown.card.text} {shown.card.sub or ''}")
    if reading > shown.end - shown.start:
        warnings.append(f"{shown.name}: reads in {reading:.1f} s but shows for {shown.end - shown.start:.1f} s")
    return picture


def run() -> None:
    root = Path.cwd()
    sys.exit(main(
        gpu=SystemGpu(),
        voice_engine=VoxCpmEngine.installed_in(root),
        face_engine=InfiniteTalkEngine.installed_in(root),
        browser=ChromeBrowser.found(),
    ))
