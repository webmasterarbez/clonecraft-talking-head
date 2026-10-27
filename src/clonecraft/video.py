"""Turning a Voiceover, its Face sections and its Slide cards into a Video."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import audio, frame, loudness
from .face import FACE_FPS, FACE_SIZES, FaceEngine, FaceEngineError
from .project import Format

PUSH = 0.035  # each Slide card scales up by this much over its hold (the approved look; ADR 0007)
FACE_MARGIN_S = 0.2  # a Face section's audio slice runs this far past each edge, so its cut never runs short (the approved look)
HOOK_TOP = frame.HOOK_Y - 150  # the hook box's top, below the chin (the approved look's hook position, less 150)
# CloneCraft's own, in the approved look's frame: bottom left, below the hook and above the platforms' caption strip
BADGE_BOX = (360, 100)  # the badge is drawn this size
BADGE_XY = (48, 1500)  # its left and top
END_CARD_S = 2.5  # the end card holds this long after the Voiceover ends, in silence


@dataclass(frozen=True)
class Hook:
    """The drawn hook and how long it shows over the opening Face section."""

    picture: Path
    until: float


@dataclass(frozen=True)
class Pill:
    """The drawn disclosure pill, shown over the Video's last Slide card."""

    picture: Path


@dataclass(frozen=True)
class Stretch:
    """A stretch of the Video in seconds: a drawn card, or the face when `picture` is None."""

    start: float
    end: float
    picture: Path | None = None

    @property
    def is_card(self) -> bool:
        return self.picture is not None


@dataclass(frozen=True)
class FaceClip:
    """A Face section's kept clip, the audio slice it speaks, and where that slice starts in the Voiceover."""

    clip: Path
    audio: Path
    slice_start: float


@dataclass
class Faces:
    """The face clips a Video needs: each section's kept clip, and the ones that must be rendered first."""

    clips: list[FaceClip]
    to_render: list[FaceClip]

    def check_rendered(self) -> None:
        for face in self.to_render:
            needed, made = audio.seconds(face.audio), _duration(face.clip)
            if made < needed - 0.05:
                face.clip.unlink()  # never reuse a short clip
                raise FaceEngineError(
                    f"the face clip for the Face section from {face.slice_start + FACE_MARGIN_S if face.slice_start else 0.0:.2f} s "
                    f"is shorter than its slice of the Voiceover ({made:.2f} s against {needed:.2f} s)"
                )


def faces_for(stretches: list[Stretch], likeness: Path, voiceover: Path, fmt: Format, kept: Path, work: Path) -> Faces:
    """Slice the Voiceover for each Face section and find its kept clip, keyed by the Likeness and the slice."""
    rate, samples = audio.read_wav(voiceover)
    seconds = len(samples) / rate
    clips = []
    for n, stretch in enumerate(s for s in stretches if s.picture is None):
        a, b = max(0.0, stretch.start - FACE_MARGIN_S), min(seconds, stretch.end + FACE_MARGIN_S)
        piece = work / f"face-{n:02d}.wav"
        audio.write_wav(piece, samples[round(a * rate) : round(b * rate)], rate)
        crop = f"{fmt.aspect} {FACE_SIZES[fmt.aspect]}".encode()  # a new crop size makes new clips
        key = hashlib.sha256(likeness.read_bytes() + crop + piece.read_bytes()).hexdigest()[:20]
        clips.append(FaceClip(kept / f"{key}.mp4", piece, a))
    kept.mkdir(parents=True, exist_ok=True)
    return Faces(clips, [c for c in clips if not c.clip.is_file()])


def render_faces(faces: Faces, likeness: Path, fmt: Format, face_engine: FaceEngine, work: Path) -> None:
    """Render every missing face clip from a crop of the Likeness, in one face-engine session."""
    if faces.to_render:
        portrait = work / "portrait.png"
        _crop(likeness, fmt, portrait)
        face_engine.render(portrait, [(face.audio, face.clip) for face in faces.to_render])
        faces.check_rendered()


def assemble(
    stretches: list[Stretch],
    faces: Faces,
    voiceover: Path,
    fmt: Format,
    out: Path,
    hook: Hook | None = None,
    pill: Pill | None = None,
    badge: Path | None = None,
    end_card: Path | None = None,
) -> float:
    """Write the Video to `out`, replacing any earlier one, and return its length in seconds.

    A hook goes over the Face section that opens the Video, if one does, and the badge over every Face section. The
    disclosure pill goes over its last Slide card. An end card adds END_CARD_S of silence after the Voiceover.
    """
    spoken = audio.seconds(voiceover)
    seconds = spoken + (END_CARD_S if end_card else 0.0)
    face_clips = iter(faces.clips)
    last_card = max((n for n, stretch in enumerate(stretches) if stretch.is_card), default=None)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        clips = []
        for n, stretch in enumerate(stretches):
            frames = round(stretch.end * fmt.fps) - round(stretch.start * fmt.fps)  # from whole-Video frame numbers: no drift
            clip = work / f"{n:03d}.mp4"
            if stretch.picture is None:
                face = next(face_clips)
                shown_hook = hook if stretch.start == 0 else None
                offset = stretch.start - face.slice_start
                clips.append(_face_clip(face.clip, offset, frames, fmt, clip, shown_hook, badge))
            else:
                shown_pill = pill if n == last_card else None
                clips.append(_card_clip(stretch.picture, frames, fmt, clip, shown_pill))
        if end_card:
            frames = round(seconds * fmt.fps) - round(spoken * fmt.fps)
            clips.append(_card_clip(end_card, frames, fmt, work / "end.mp4", None))
        listing = work / "clips.txt"
        listing.write_text("".join(f"file '{clip}'\n" for clip in clips))
        video = work / "video.mp4"
        # the Voiceover file itself is never changed: the loudness and the fade-out are filters on the Video's audio
        fade = f"afade=t=out:st={max(0.0, spoken - frame.FADE_OUT_S):.3f}:d={frame.FADE_OUT_S}"  # a short take fades all of it
        pad = f"apad=whole_dur={seconds:.3f}" if end_card else ""
        audio_filter = ",".join(part for part in (loudness.normalising_filter(voiceover), fade, pad) if part)
        _ffmpeg(
            "-f", "concat", "-safe", "0", "-i", listing, "-i", voiceover, "-map", "0:v", "-map", "1:a",
            "-t", f"{seconds:.3f}", "-c:v", "copy", "-af", audio_filter,
            "-c:a", "aac", "-b:a", "192k", video,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(video, out)
    return seconds


def forget_unused(faces: Faces, kept: Path) -> None:
    """Delete kept face clips this Video no longer uses, so the folder holds only the current ones."""
    used = {face.clip for face in faces.clips}
    for clip in kept.glob("*.mp4"):
        if clip not in used:
            clip.unlink()


def _duration(media: Path) -> float:
    shown = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    return float(shown.stdout)


def _ffmpeg(*args: str | Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True, capture_output=True, stdin=subprocess.DEVNULL
    )


def _crop(likeness: Path, fmt: Format, out: Path) -> None:
    """Centre-crop to the Format's aspect at full height, then scale to the face engine's size for it."""
    w, h = (int(part) for part in fmt.aspect.split(":"))
    width, height = FACE_SIZES[fmt.aspect]
    crop = f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})',scale={width}:{height}:flags=lanczos"
    _ffmpeg("-i", likeness, "-vf", crop, "-frames:v", "1", out)


def _face_clip(
    source: Path,
    offset: float,
    frames: int,
    fmt: Format,
    out: Path,
    hook: Hook | None,
    badge: Path | None = None,
) -> Path:
    """The face from `offset` seconds into its clip, at the Format's size and frame rate; the last frame holds if short.

    The hook and the badge go over the face, scaled to the Format as the approved look's frame is.
    """
    retime = (
        f"minterpolate=fps={fmt.fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        if fmt.fps != FACE_FPS
        else ""
    )
    picture = f"[0:v]{retime}scale={fmt.width}:{fmt.height}:flags=lanczos,unsharp=5:5:0.6"
    overlay: list[str | Path] = []
    if hook:
        width, height, top = _placed(frame.HOOK_BOX, HOOK_TOP, fmt)
        overlay = ["-i", hook.picture]
        picture += (
            f"[face];[1:v]scale={width}:{height}:flags=lanczos[hook];"
            f"[face][hook]overlay={(fmt.width - width) // 2}:{top}:enable='lt(t,{hook.until - 0.05:.3f})'"
        )
    if badge:
        width, height, top = _placed(BADGE_BOX, BADGE_XY[1], fmt)
        left = round(BADGE_XY[0] * frame.scale(fmt.width, fmt.height))
        index = 2 if hook else 1  # the input after the source and, when there is one, the hook
        overlay += ["-i", badge]
        picture += f"[under];[{index}:v]scale={width}:{height}:flags=lanczos[badge];[under][badge]overlay={left}:{top}"
    picture += ",tpad=stop_mode=clone:stop_duration=1[out]"
    _ffmpeg(
        "-ss", f"{offset:.3f}", "-i", source, *overlay, "-filter_complex", picture, "-map", "[out]", "-an",
        "-frames:v", str(frames), *_same_stream(fmt), "-c:v", "libx264", "-crf", "16", "-preset", "fast",
        "-pix_fmt", "yuv420p", out,
    )
    return out


def _card_clip(picture: Path, frames: int, fmt: Format, out: Path, pill: Pill | None) -> Path:
    """A slow push-in on the card, drawn on a canvas twice the size so the zoom doesn't wobble.

    The disclosure pill, if any, is laid over the card and held for all of it, scaled to the Format as the approved look's frame is.
    """
    w, h = fmt.width, fmt.height
    graph = (
        f"[0:v]scale={2 * w}:{2 * h}:flags=lanczos,zoompan=z='1+{PUSH}*on/{frames}':x='iw/2-iw/zoom/2':"
        f"y='ih/2-ih/zoom/2':d={frames + 1}:s={w}x{h}:fps={fmt.fps}[s]"
    )
    inputs: list[str | Path] = ["-loop", "1", "-framerate", str(fmt.fps), "-i", picture]
    label = "s"
    if pill:
        width, height, top = _placed(frame.PILL_BOX, frame.PILL_Y, fmt)
        inputs += ["-loop", "1", "-framerate", str(fmt.fps), "-i", pill.picture]
        graph += f";[1:v]scale={width}:{height}:flags=lanczos[pill];[s][pill]overlay=(W-w)/2:{top}[t]"
        label = "t"
    graph += f";[{label}]format=yuv420p[v]"
    _ffmpeg(
        *inputs, "-filter_complex", graph, "-map", "[v]",
        "-frames:v", str(frames), *_same_stream(fmt), "-c:v", "libx264", "-crf", "16", "-preset", "fast", out,
    )
    return out


def _placed(box: tuple[int, int], y: float, fmt: Format) -> tuple[int, int, int]:
    """A drawn box's width and height, and the row its top sits on, scaled from the approved look's frame to the Format."""
    scale = frame.scale(fmt.width, fmt.height)
    return round(box[0] * scale), round(box[1] * scale), frame.row_of(y, fmt.height)


def _same_stream(fmt: Format) -> list[str]:
    """Face and card clips share frame rate and time base, so they join without re-encoding."""
    return ["-r", str(fmt.fps), "-video_track_timescale", "90000"]
