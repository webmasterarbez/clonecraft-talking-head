import json
import os
import shutil
from typing import Any

import pytest

from clonecraft import browser as browser_module
from clonecraft.browser import Browser, ChromeBrowser
from clonecraft.cli import main
from clonecraft.voice import Word
from tests.support import (
    CARD_COLOURS,
    Answers,
    FakeBrowser,
    FakeFaceEngine,
    FakeGpu,
    FakeVoiceEngine,
    Project,
    ffprobe,
    frame_colour,
    service,
    video_stream,
    write_brand_pack,
)


def run_voiceover(project: Project, engine: FakeVoiceEngine, script: str = "script-01") -> int:
    return main(["voiceover", project.channel_ref, script], root=project.root, voice_engine=engine)


def test_the_voiceover_saves_the_words_it_was_heard_to_say_with_their_times(project: Project) -> None:
    project.write_script("script-01", "Hello there friend.")

    assert run_voiceover(project, FakeVoiceEngine()) == 0

    saved = json.loads(project.words("script-01").read_text())
    assert [w["text"] for w in saved["words"]] == ["Hello", "there", "friend."]
    # the fake hears the words spread evenly over the whole file: 1.0 s of speech + 0.03 s padding each side
    assert saved["words"][0]["start"] == 0.0
    assert saved["words"][-1]["end"] == pytest.approx(1.06, abs=0.01)


CARDS_SCRIPT = """---
title: Example title
face_ends_after: Hello there
---
Hello there friend. Here is the trick.

<!-- slides -->
- at: Here is the trick
  kind: title
  text: The *trick*
"""


def test_only_the_words_between_the_front_matter_and_the_slides_list_are_spoken(project: Project) -> None:
    project.write_script("script-01", CARDS_SCRIPT)
    engine = FakeVoiceEngine()

    assert run_voiceover(project, engine) == 0

    assert [text for _, text in engine.calls] == ["Hello there friend. Here is the trick."]


def test_an_unknown_front_matter_key_is_named_with_the_script_file(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.write_script("script-01", "---\ntitel: Typo\n---\nHello there.\n")

    assert run_voiceover(project, FakeVoiceEngine()) == 1

    error = capsys.readouterr().err
    assert "titel" in error and "script-01.md" in error


@pytest.mark.parametrize(
    ("first", "second", "named", "problem"),
    [
        ("Hello there", "Here is no trick", "Here is no trick", "is not in the Script"),
        ("Hello there friend", "Hello there", "Hello there", "is said before the card above it"),
        ("Hello there", "Hello there", "Hello there", "is said before the card above it"),  # said only once
    ],
)
def test_a_card_phrase_the_script_does_not_say_in_order_stops_before_anything_is_spoken(
    project: Project, capsys: pytest.CaptureFixture[str], first: str, second: str, named: str, problem: str
) -> None:
    project.write_script(
        "script-01",
        f"Hello there friend. Here is the trick.\n\n<!-- slides -->\n- at: {first}\n  text: One\n- at: {second}\n  text: Two\n",
    )
    engine = FakeVoiceEngine()

    assert run_voiceover(project, engine) == 1

    assert engine.calls == []
    assert f"{named!r} in" in (error := capsys.readouterr().err) and problem in error


FACE_FIRST = "- at: Here is the trick\n  text: One\n"  # leaves a Face section before the first card
FACE_ENTRY = "- at: Hello there\n  text: One\n- at: Here is the trick\n  kind: face\n"


@pytest.mark.parametrize("listing", [FACE_FIRST, FACE_ENTRY])
def test_a_script_written_for_face_sections_can_still_be_voiced(project: Project, listing: str) -> None:
    project.write_script("script-01", f"Hello there friend. Here is the trick.\n\n<!-- slides -->\n{listing}")

    assert run_voiceover(project, FakeVoiceEngine()) == 0


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        ("  text: One\n  colour: red\n", "'colour'"),
        ("  kind: cta\n  text: One\n", "'button'"),
        ("  kind: stat\n  text: One\n", "'value'"),
        ("  text: One\n  button: Follow\n", "'button'"),  # only a cta card shows a button
        ("  kind: quote\n  text: One\n", "'quote'"),
        ("  kind: title\n", "'text'"),
    ],
)
def test_a_card_the_template_cannot_draw_is_named_before_anything_is_spoken(
    project: Project, capsys: pytest.CaptureFixture[str], entry: str, named: str
) -> None:
    project.write_script("script-01", f"Hello there friend.\n\n<!-- slides -->\n- at: Hello there\n{entry}")
    engine = FakeVoiceEngine()

    assert run_voiceover(project, engine) == 1

    error = capsys.readouterr().err
    assert engine.calls == [] and named in error and "Slide card 1" in error


SPOKEN = "Hello there friend. Here is the trick."
HEARD = [  # what the transcriber hears in the 2.06 s Voiceover, and when
    Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.7, 1.0),
    Word("Here", 1.2, 1.4), Word("is", 1.4, 1.5), Word("the", 1.5, 1.6), Word("trick.", 1.6, 2.0),
]


def slides(*entries: str) -> str:
    return f"{SPOKEN}\n\n<!-- slides -->\n" + "".join(entries)


@pytest.fixture
def cards_ready(project: Project) -> Project:
    """A small 9:16 Format so ffmpeg is quick, a Brand pack, a 2.06 s Voiceover and a two-card Script."""
    project.channel_yaml.write_text('persona: examplepersona\nformats:\n  - aspect: "9:16"\n    resolution: 108x192\n    fps: 10\n')
    write_brand_pack(project.root / "persona" / "examplepersona")
    project.write_voiceover("script-01", seconds=2.0)
    project.write_script("script-01", slides("- at: Hello there\n  text: One\n", "- at: Here is the trick\n  text: Two\n"))
    return project


def run_card_video(
    project: Project, browser: Browser | None = None, engine: FakeVoiceEngine | None = None, **extra: Any
) -> int:
    engine = engine or FakeVoiceEngine(words_in={project.voiceover("script-01"): HEARD})
    return main(
        ["video", project.channel_ref, "script-01"], root=project.root, voice_engine=engine,
        browser=browser or FakeBrowser(), **extra,
    )


def test_a_cards_only_video_shows_each_card_from_just_before_its_phrase_and_never_touches_the_face_or_gpu(
    cards_ready: Project,
) -> None:
    face = FakeFaceEngine()
    gpu = FakeGpu(known=[service("llama-server@11434.service", 2_000)])  # 12000 - 1200 - 2000 = 8800 MiB free

    assert run_card_video(cards_ready, face_engine=face, gpu=gpu, ask=Answers()) == 0

    video = cards_ready.video("script-01", "108x192")
    stream = video_stream(video)
    assert (stream["width"], stream["height"], stream["avg_frame_rate"]) == (108, 192, "10/1")
    assert float(ffprobe(video)["format"]["duration"]) == pytest.approx(2.06, abs=0.1)  # 2.0 s tone + 0.03 s each side
    # card two cuts in at 1.2 s ("Here") - 0.12 s lead = 1.08 s
    assert frame_colour(video, 0.9) == pytest.approx(CARD_COLOURS[0], abs=40)
    assert frame_colour(video, 1.3) == pytest.approx(CARD_COLOURS[1], abs=40)
    assert face.portraits == [] and gpu.events == []


def test_each_card_is_drawn_from_the_brand_packs_template_at_the_formats_size(cards_ready: Project) -> None:
    browser = FakeBrowser()

    run_card_video(cards_ready, browser)

    assert browser.sizes == [(108, 192), (108, 192), (720, 84)]  # two cards, then the disclosure pill at the approved look's size
    first = browser.pages[0]
    assert '"text": "One"' in first and '"kind": "bullet"' in first
    assert "fonts/Ui.ttf" in first and "fonts/Mono.ttf" in first and "mark.svg" in first
    assert "__SLIDE__" not in first and "__PACK__" not in first


def test_card_text_cannot_close_the_templates_script_element(cards_ready: Project) -> None:
    cards_ready.write_script("script-01", slides("- at: Hello there\n  text: </script><b>Bold</b>\n"))
    browser = FakeBrowser()

    run_card_video(cards_ready, browser)

    assert "</script><b>" not in browser.pages[0]


def test_a_voiceover_without_word_timings_is_transcribed_once_and_its_timings_kept(cards_ready: Project) -> None:
    engine = FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): HEARD})

    assert run_card_video(cards_ready, engine=engine) == 0
    assert run_card_video(cards_ready, engine=FakeVoiceEngine()) == 0  # this engine hears nothing: the saved words are used

    saved = json.loads(cards_ready.words("script-01").read_text())
    assert [w["text"] for w in saved["words"]] == [w.text for w in HEARD]


def test_timings_of_an_earlier_voiceover_are_not_used(cards_ready: Project) -> None:
    run_card_video(cards_ready)
    cards_ready.write_voiceover("script-01", seconds=2.5)
    later = [Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("Here", 2.0, 2.2), Word("is", 2.2, 2.3),
             Word("the", 2.3, 2.4), Word("trick.", 2.4, 2.5)]

    run_card_video(cards_ready, engine=FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): later}))

    # card two now cuts in at 2.0 s - 0.12 s lead = 1.88 s
    assert frame_colour(cards_ready.video("script-01", "108x192"), 1.6) == pytest.approx(CARD_COLOURS[0], abs=40)


def test_a_phrase_heard_with_digits_still_finds_its_card(cards_ready: Project) -> None:
    cards_ready.write_script("script-01", "Hello there friend. Ten jobs a day.\n\n<!-- slides -->\n"
                             "- at: Hello there\n  text: One\n- at: Ten jobs\n  text: Two\n")
    heard = HEARD[:3] + [Word("10", 1.2, 1.4), Word("jobs", 1.4, 1.6), Word("a", 1.6, 1.7), Word("day.", 1.7, 2.0)]

    assert run_card_video(cards_ready, engine=FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): heard})) == 0

    assert frame_colour(cards_ready.video("script-01", "108x192"), 1.3) == pytest.approx(CARD_COLOURS[1], abs=40)


def test_a_misheard_word_late_in_a_phrase_still_finds_its_card(cards_ready: Project) -> None:
    heard = HEARD[:6] + [Word("trek.", 1.6, 2.0)]  # "trick" heard as "trek": the first three words still match

    assert run_card_video(cards_ready, engine=FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): heard})) == 0


def test_a_phrase_not_heard_in_the_voiceover_is_named_before_any_card_is_drawn(
    cards_ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = FakeBrowser()
    heard = HEARD[:3] + [Word("Over", 1.2, 1.4), Word("yonder", 1.4, 2.0)]  # no word of "Here is the trick"

    assert run_card_video(cards_ready, browser, FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): heard})) == 1

    assert "'Here is the trick'" in capsys.readouterr().err
    assert browser.pages == [] and not cards_ready.video("script-01", "108x192").exists()


def test_a_card_that_would_show_for_under_six_tenths_of_a_second_is_left_out_with_a_warning(
    cards_ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    cards_ready.write_script(
        "script-01", slides("- at: Hello there\n  text: One\n", "- at: friend\n  text: Two\n", "- at: Here is\n  text: Three\n")
    )
    browser = FakeBrowser()
    heard = [Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.75), Word("friend.", 0.75, 1.0)] + HEARD[3:]

    assert run_card_video(cards_ready, browser, FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): heard})) == 0

    # "friend" cuts in at 0.75 s - 0.12 s = 0.63 s and "Here" at 1.2 s - 0.12 s = 1.08 s: a 0.45 s hold, under 0.6 s;
    # the first card holds 0.63 s, just enough to stay
    assert "'friend'" in capsys.readouterr().err
    assert len(browser.pages) == 3 and not any('"text": "Two"' in page for page in browser.pages)  # cards one and three, the pill
    assert frame_colour(cards_ready.video("script-01", "108x192"), 0.8) == pytest.approx(CARD_COLOURS[0], abs=40)


def test_a_card_too_long_to_read_in_its_hold_or_too_big_for_its_frame_is_warned_about_but_still_made(
    cards_ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    long = "A very long card text that takes a while"  # 32 letters / 15 a second + 1.5 s = 3.6 s, over the 1.08 s hold
    cards_ready.write_script("script-01", slides(f"- at: Hello there\n  text: {long}\n", "- at: Here is the trick\n  text: Two\n"))

    assert run_card_video(cards_ready, FakeBrowser(overflowing={'"Two"'})) == 0

    error = capsys.readouterr().err
    assert "warning: Slide card 'Hello there': reads in 3.6 s but shows for 1.1 s" in error
    assert "warning: Slide card 'Here is the trick': its text runs outside the card" in error
    assert cards_ready.video("script-01", "108x192").exists()


def test_the_brand_pack_named_in_channel_yaml_is_used_when_the_persona_has_several(cards_ready: Project) -> None:
    other = write_brand_pack(cards_ready.root / "persona" / "examplepersona", "bold")
    (other / "slide.html").write_text("<p>bold look</p>__SLIDE__ __PACK__")
    cards_ready.channel_yaml.write_text(cards_ready.channel_yaml.read_text() + "brand_pack: bold\n")
    browser = FakeBrowser()

    assert run_card_video(cards_ready, browser) == 0

    assert "bold look" in browser.pages[0]


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ("several", "brand_pack:"),
        ("none", "copy config/brand-pack-starter"),
        ("unknown name", "brand-packs/missing"),
        ("no template", "slide.html"),
        ("no mark", "mark.svg"),
        ("no font", "Mono.ttf"),
        ("bad json", "not valid JSON"),
        ("not utf-8", "not valid JSON"),
    ],
)
def test_a_brand_pack_that_cannot_be_used_is_named_before_any_card_is_drawn(
    cards_ready: Project, capsys: pytest.CaptureFixture[str], change: str, named: str
) -> None:
    persona = cards_ready.root / "persona" / "examplepersona"
    pack = persona / "brand-packs" / "plain"
    if change == "several":
        write_brand_pack(persona, "bold")
    elif change == "none":
        shutil.rmtree(persona / "brand-packs")
    elif change == "unknown name":
        cards_ready.channel_yaml.write_text(cards_ready.channel_yaml.read_text() + "brand_pack: missing\n")
    elif change == "no template":
        (pack / "slide.html").unlink()
    elif change == "no mark":
        (pack / "mark.svg").unlink()
    elif change == "no font":
        (pack / "fonts" / "Mono.ttf").unlink()
    elif change == "bad json":
        (pack / "pack.json").write_text("{colors")
    else:
        (pack / "pack.json").write_bytes(b"\xff\xfe{}")
    browser = FakeBrowser()

    assert run_card_video(cards_ready, browser) == 1

    assert named in capsys.readouterr().err and browser.pages == []


def test_without_chrome_the_card_video_stops_naming_the_program(
    cards_ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): HEARD})

    assert main(["video", cards_ready.channel_ref, "script-01"], root=cards_ready.root, voice_engine=engine) == 1

    assert "google-chrome" in capsys.readouterr().err


def test_without_saved_timings_or_a_voice_engine_the_card_video_says_how_to_install_it(
    cards_ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["video", cards_ready.channel_ref, "script-01"], root=cards_ready.root, browser=FakeBrowser()) == 1

    assert "install-voice-engine.sh" in capsys.readouterr().err


def test_a_cards_only_video_in_sixteen_by_nine_draws_each_card_at_the_formats_size(cards_ready: Project) -> None:
    cards_ready.channel_yaml.write_text('persona: examplepersona\nformats:\n  - aspect: "16:9"\n    resolution: 192x108\n    fps: 10\n')
    browser = FakeBrowser()

    assert run_card_video(cards_ready, browser) == 0

    assert browser.sizes == [(192, 108), (192, 108), (720, 84)]  # the pill is drawn at the approved look's size, then scaled into the frame
    assert browser.fit_sizes == [(192, 108), (192, 108)]  # only the cards are checked for fit
    video = cards_ready.video("script-01", "192x108")
    stream = video_stream(video)
    assert (stream["width"], stream["height"]) == (192, 108)
    # as in 9:16: card two cuts in at 1.2 s ("Here") - 0.12 s lead = 1.08 s
    assert frame_colour(video, 0.9) == pytest.approx(CARD_COLOURS[0], abs=40)
    assert frame_colour(video, 1.3) == pytest.approx(CARD_COLOURS[1], abs=40)


def test_a_phrase_said_twice_cuts_in_its_second_card_the_second_time_it_is_heard(cards_ready: Project) -> None:
    cards_ready.write_script("script-01", "Hello there friend. Hello there again.\n\n<!-- slides -->\n"
                             "- at: Hello there\n  text: One\n- at: Hello there\n  text: Two\n")
    heard = HEARD[:3] + [Word("Hello", 1.2, 1.4), Word("there", 1.4, 1.6), Word("again.", 1.6, 2.0)]

    assert run_card_video(cards_ready, engine=FakeVoiceEngine(words_in={cards_ready.voiceover("script-01"): heard})) == 0

    video = cards_ready.video("script-01", "108x192")
    assert frame_colour(video, 0.9) == pytest.approx(CARD_COLOURS[0], abs=40)  # card two at 1.2 s - 0.12 s = 1.08 s
    assert frame_colour(video, 1.3) == pytest.approx(CARD_COLOURS[1], abs=40)


def test_when_the_first_card_is_left_out_the_next_one_opens_the_video(cards_ready: Project) -> None:
    cards_ready.write_script("script-01", slides("- at: Hello\n  text: One\n", "- at: there friend\n  text: Two\n"))
    browser = FakeBrowser()

    run_card_video(cards_ready, browser)

    # "there" cuts in at 0.4 s - 0.12 s = 0.28 s: card one would hold 0.28 s, under 0.6 s, so card two shows from 0 s
    assert len(browser.pages) == 2 and '"text": "Two"' in browser.pages[0]  # card two, then the disclosure pill
    video_seconds = float(video_stream(cards_ready.video("script-01", "108x192"))["duration"])
    assert video_seconds == pytest.approx(2.06, abs=0.1)  # pictures for the whole Voiceover: 2.0 s + 0.03 s each side
    assert frame_colour(cards_ready.video("script-01", "108x192"), 0.1) == pytest.approx(CARD_COLOURS[0], abs=40)


def test_making_missing_word_timings_asks_about_gpu_programs_when_memory_is_short(cards_ready: Project) -> None:
    gpu = FakeGpu([service("llama-server@11434.service", 8_000)])  # 12000 - 1200 - 8000 = 2800 MiB free
    ask = Answers("y", "y")  # stop it, and start it again afterwards

    assert run_card_video(cards_ready, gpu=gpu, ask=ask) == 0

    assert "Voiceover transcription" in ask.prompts[0]
    assert gpu.events == ["stop llama-server@11434.service", "start llama-server@11434.service"]


def test_with_saved_word_timings_no_gpu_question_is_asked(cards_ready: Project) -> None:
    run_card_video(cards_ready)
    gpu = FakeGpu([service("llama-server@11434.service", 8_000)])

    assert run_card_video(cards_ready, gpu=gpu, ask=Answers()) == 0

    assert gpu.events == []


@pytest.mark.parametrize(("chrome", "named"), [("exit 1", "could not draw"), ("sleep 5", "did not finish")])
def test_a_chrome_that_fails_or_hangs_ends_in_one_line_naming_it(
    cards_ready: Project, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, chrome: str, named: str
) -> None:
    bin_dir = cards_ready.root / "bin"
    bin_dir.mkdir()
    (bin_dir / "google-chrome").write_text(f"#!/bin/sh\n{chrome}\n")
    (bin_dir / "google-chrome").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setattr(browser_module, "CHROME_TIMEOUT_S", 1)

    assert run_card_video(cards_ready, ChromeBrowser.found()) == 1

    error = capsys.readouterr().err
    assert error.startswith("clonecraft: google-chrome") and named in error and len(error.splitlines()) == 1
