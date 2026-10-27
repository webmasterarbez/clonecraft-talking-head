import shutil
from typing import Any

import numpy as np
import pytest

from clonecraft.cli import main
from clonecraft.face import FACE_SIZES
from clonecraft.voice import Word
from tests.support import (
    CARD_COLOURS,
    Answers,
    FakeBrowser,
    FakeGpu,
    FakeFaceEngine,
    FakeVoiceEngine,
    Project,
    decode_audio,
    ffprobe,
    frame_colour,
    service,
    write_banded_likeness,
    write_brand_pack,
)

GREY = (128, 128, 128)  # the fake face engine's clip
SPOKEN = "Hello there friend. Here is the trick."
HEARD = [  # what the transcriber hears in the 2.06 s Voiceover, and when
    Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.7, 1.0),
    Word("Here", 1.2, 1.4), Word("is", 1.4, 1.5), Word("the", 1.5, 1.6), Word("trick.", 1.6, 2.0),
]


@pytest.fixture
def ready(project: Project) -> Project:
    """A small 9:16 Format at the face engine's 25 fps so ffmpeg is quick, a Likeness, a Brand pack and a 2.06 s Voiceover."""
    project.channel_yaml.write_text('persona: examplepersona\nformats:\n  - aspect: "9:16"\n    resolution: 108x192\n    fps: 25\n')
    write_banded_likeness(project.likeness)
    write_brand_pack(project.root / "persona" / "examplepersona")
    project.write_voiceover("script-01", seconds=2.0)
    return project


def slides(*entries: str) -> str:
    return f"{SPOKEN}\n\n<!-- slides -->\n" + "".join(entries)


def run(project: Project, face: FakeFaceEngine, heard: list[Word] | None = None, **extra: Any) -> int:
    engine = FakeVoiceEngine(words_in={project.voiceover("script-01"): heard or HEARD})
    return main(
        ["video", project.channel_ref, "script-01"], root=project.root, voice_engine=engine, face_engine=face,
        browser=extra.pop("browser", FakeBrowser()), **extra,
    )


def video(project: Project) -> Any:
    return project.video("script-01", "108x192")


def test_an_opening_face_section_is_the_only_stretch_rendered_and_the_cards_follow_it(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    face = FakeFaceEngine()

    assert run(ready, face) == 0

    # the card cuts in at 1.2 s - 0.12 s = 1.08 s; the slice runs 0.2 s past it: 1.28 s
    assert face.sessions == 1 and face.slices == [pytest.approx(1.28, abs=0.01)]
    assert frame_colour(video(ready), 0.5) == pytest.approx(GREY, abs=40)
    assert frame_colour(video(ready), 1.5) == pytest.approx(CARD_COLOURS[0], abs=40)


def test_a_face_entry_brings_the_face_back_and_every_face_section_renders_in_one_session(ready: Project) -> None:
    ready.write_script(
        "script-01", slides("- at: friend\n  text: One\n", "- at: Here is the trick\n  kind: face\n")
    )
    face = FakeFaceEngine()
    heard = [Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.75, 1.0),
             Word("Here", 1.35, 1.5), Word("is", 1.5, 1.6), Word("the", 1.6, 1.7), Word("trick.", 1.7, 2.0)]

    assert run(ready, face, heard) == 0

    # opening: 0 to 0.75 - 0.12 = 0.63 s, sliced 0.2 s past it: 0.83 s
    # closing: from 1.35 - 0.12 = 1.23 s to the 2.06 s end, sliced from 1.03 s: 1.03 s
    assert face.sessions == 1 and face.slices == [pytest.approx(0.83, abs=0.01), pytest.approx(1.03, abs=0.01)]
    assert frame_colour(video(ready), 0.3) == pytest.approx(GREY, abs=40)
    assert frame_colour(video(ready), 0.9) == pytest.approx(CARD_COLOURS[0], abs=40)
    assert frame_colour(video(ready), 1.6) == pytest.approx(GREY, abs=40)


OPENING_AND_CLOSING = [  # card "friend" from 0.63 s, the face back from 1.23 s (see the test above)
    Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.75, 1.0),
    Word("Here", 1.35, 1.5), Word("is", 1.5, 1.6), Word("the", 1.6, 1.7), Word("trick.", 1.7, 2.0),
]


def test_changing_only_a_cards_text_renders_no_face_and_asks_nothing_about_the_gpu(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: friend\n  text: One\n", "- at: Here is the trick\n  kind: face\n"))
    run(ready, FakeFaceEngine(), OPENING_AND_CLOSING)
    ready.write_script("script-01", slides("- at: friend\n  text: Changed\n", "- at: Here is the trick\n  kind: face\n"))
    face = FakeFaceEngine()
    gpu = FakeGpu([service("llama-server@11434.service", 8_000)])

    assert run(ready, face, OPENING_AND_CLOSING, gpu=gpu, ask=Answers()) == 0

    assert face.sessions == 0 and gpu.events == []


def test_moving_one_face_section_renders_only_that_one_and_forgets_the_old_clip(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: friend\n  text: One\n", "- at: Here is the trick\n  kind: face\n"))
    run(ready, FakeFaceEngine(), OPENING_AND_CLOSING)
    ready.write_script("script-01", slides("- at: friend\n  text: One\n", "- at: is the trick\n  kind: face\n"))
    face = FakeFaceEngine()

    assert run(ready, face, OPENING_AND_CLOSING) == 0

    # the face now comes back at "is": 1.5 - 0.12 = 1.38 s, sliced from 1.18 s to the 2.06 s end: 0.88 s
    assert face.slices == [pytest.approx(0.88, abs=0.01)]
    assert len(list(ready.channel_dir.glob("videos/face-sections/script-01.108x192/*.mp4"))) == 2


def test_with_every_face_section_kept_no_face_engine_is_needed(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    run(ready, FakeFaceEngine())
    engine = FakeVoiceEngine(words_in={ready.voiceover("script-01"): HEARD})

    code = main(["video", ready.channel_ref, "script-01"], root=ready.root, voice_engine=engine, browser=FakeBrowser())

    assert code == 0


def test_a_face_section_under_six_tenths_of_a_second_is_left_out_with_a_warning(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", slides("- at: Hello\n  text: One\n", "- at: friend\n  kind: face\n",
                                           "- at: Here is the trick\n  text: Two\n"))
    face = FakeFaceEngine()

    assert run(ready, face) == 0

    # the face would come back at 0.7 - 0.12 = 0.58 s until 1.2 - 0.12 = 1.08 s: 0.5 s, under 0.6 s
    assert "Face section 'friend'" in capsys.readouterr().err
    assert face.sessions == 0 and frame_colour(video(ready), 0.8) == pytest.approx(CARD_COLOURS[0], abs=40)


def test_face_sections_that_meet_are_rendered_as_one(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: friend\n  text: One\n", "- at: Here is the trick\n  kind: face\n"))
    heard = [Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.75, 0.95),
             Word("Here", 1.0, 1.4), Word("is", 1.4, 1.5), Word("the", 1.5, 1.6), Word("trick.", 1.6, 2.0)]
    face = FakeFaceEngine()

    assert run(ready, face, heard) == 0

    # the opening face runs to 0.75 - 0.12 = 0.63 s and stays; the card would show from 0.63 s to
    # 1.0 - 0.12 = 0.88 s, 0.25 s, so it is left out and the two faces meet: one section over the whole 2.06 s
    assert face.slices == [pytest.approx(2.06, abs=0.01)]


def test_face_ends_after_ends_the_opening_face_section_at_that_phrase(ready: Project) -> None:
    ready.write_script("script-01", "---\nface_ends_after: Hello there\n---\n" + slides("- at: Here is the trick\n  text: One\n"))
    face = FakeFaceEngine()

    assert run(ready, face) == 0

    # the face ends with "there" at 0.7 s, where the card cuts in; the slice runs to 0.9 s
    assert face.slices == [pytest.approx(0.9, abs=0.01)]
    assert frame_colour(video(ready), 0.8) == pytest.approx(CARD_COLOURS[0], abs=40)


@pytest.mark.parametrize(("phrase", "problem"), [("Hello again", "not in the Script"), ("is the trick", "before the first")])
def test_a_face_ends_after_phrase_the_script_does_not_say_before_the_first_card_is_refused(
    ready: Project, capsys: pytest.CaptureFixture[str], phrase: str, problem: str
) -> None:
    ready.write_script("script-01", f"---\nface_ends_after: {phrase}\n---\n" + slides("- at: Here is\n  text: One\n"))

    assert run(ready, FakeFaceEngine()) == 1

    error = capsys.readouterr().err
    assert repr(phrase) in error and problem in error


def test_a_face_section_over_forty_five_seconds_is_warned_about(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_voiceover("script-01", seconds=46.0)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    heard = HEARD[:3] + [Word("Here", 45.3, 45.5), Word("is", 45.5, 45.6), Word("the", 45.6, 45.7), Word("trick.", 45.7, 46.0)]

    assert run(ready, FakeFaceEngine(), heard) == 0

    # the opening face runs to 45.3 - 0.12 = 45.18 s, over 45 s
    assert "the opening Face section runs 45.2 s" in capsys.readouterr().err


def test_a_script_with_no_slides_list_over_forty_five_seconds_is_warned_about(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_voiceover("script-01", seconds=46.0)
    ready.write_script("script-01", SPOKEN)

    assert run(ready, FakeFaceEngine()) == 0

    assert "the opening Face section runs 46.1 s" in capsys.readouterr().err


def test_a_new_face_engine_size_renders_the_face_sections_again(
    ready: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    assert run(ready, FakeFaceEngine()) == 0
    monkeypatch.setitem(FACE_SIZES, "9:16", (240, 416))
    face = FakeFaceEngine()

    assert run(ready, face) == 0

    assert face.sessions == 1


def hooked(hook: str, *slides_list: str) -> str:
    return f"---\n{hook}---\n" + (slides(*slides_list) if slides_list else SPOKEN)


def test_the_hook_shows_below_the_chin_over_the_opening_face_section_until_its_hold_ends(ready: Project) -> None:
    ready.write_script("script-01", hooked('hook: "Did you *apply*\\ntoday?"\nhook_hold: 0.5\n', "- at: Here is the trick\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    drawn = next(n for n, page in enumerate(browser.pages) if "apply" in page)
    assert browser.sizes[drawn] == (1080, 420)  # the approved look's hook box, drawn at its own size
    assert '>apply<\\/span><br>today?' in browser.pages[drawn]  # as JSON inside the page's script
    # the approved look's box sits 1300 - 150 = 1150 px down a 1920 px frame: rows 115 to 157 of this 192 px one
    assert frame_colour(video(ready), 0.2, down=0.71) == pytest.approx(CARD_COLOURS[drawn], abs=40)
    assert frame_colour(video(ready), 0.2, down=0.5) == pytest.approx(GREY, abs=40)  # never over the face
    assert frame_colour(video(ready), 0.7, down=0.71) == pytest.approx(GREY, abs=40)  # gone after 0.5 - 0.05 s


def test_a_hook_in_sixteen_by_nine_is_scaled_to_the_same_share_of_the_frame(ready: Project) -> None:
    ready.channel_yaml.write_text('persona: examplepersona\nformats:\n  - aspect: "16:9"\n    resolution: 192x108\n    fps: 25\n')
    write_banded_likeness(ready.likeness_horizontal, 800, 600)
    ready.write_script("script-01", hooked('hook: "Did you *apply*?"\nhook_hold: 0.5\n'))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    sixteen = ready.video("script-01", "192x108")
    # scaled by 108 / 1920: a 61 x 24 px box at row 65, centred
    assert frame_colour(sixteen, 0.2, down=0.71) == pytest.approx(CARD_COLOURS[0], abs=40)
    assert frame_colour(sixteen, 0.2, down=0.5) == pytest.approx(GREY, abs=40)
    assert frame_colour(sixteen, 0.2, down=0.71, across=0.1) == pytest.approx(GREY, abs=40)  # not the frame's width


def test_a_script_with_a_hook_but_no_hook_hold_is_refused_naming_the_key(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", hooked('hook: "Did you apply?"\n'))

    assert run(ready, FakeFaceEngine()) == 1

    error = capsys.readouterr().err
    assert "has a hook but no hook_hold" in error and "script-01.md" in error


def test_a_hook_on_a_video_that_opens_on_a_slide_card_is_left_out_with_a_warning(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", hooked('hook: "Did you apply?"\nhook_hold: 0.5\n', "- at: Hello there\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert not any("Did you apply" in page for page in browser.pages)
    assert "the hook is not shown" in capsys.readouterr().err


def test_the_hook_is_drawn_as_plain_text_not_as_markup(ready: Project) -> None:
    ready.write_script("script-01", hooked('hook: "Is 3 < 5 & <b>bold</b>?"\nhook_hold: 0.5\n'))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert "Is 3 &lt; 5 &amp; &lt;b&gt;bold&lt;" in browser.pages[0]


def test_a_hook_of_more_than_two_lines_is_warned_about(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    ready.write_script("script-01", hooked('hook: "One\\nTwo\\nThree"\nhook_hold: 0.5\n'))

    assert run(ready, FakeFaceEngine()) == 0

    assert "the hook is more than two lines" in capsys.readouterr().err


def test_an_empty_hook_is_no_hook(ready: Project) -> None:
    ready.write_script("script-01", hooked('hook: ""\n'))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert browser.pages == []


TWO_CARDS = [  # the face to 0.9 - 0.12 = 0.78 s, card One 0.78 to 2.2 - 0.12 = 2.08 s, card Two 2.08 s to the 3.0 s end
    Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 0.9, 1.1),
    Word("Here", 2.2, 2.4), Word("is", 2.4, 2.5), Word("the", 2.5, 2.6), Word("trick.", 2.6, 3.0),
]


def test_the_disclosure_pill_is_drawn_on_the_last_slide_card_at_the_approved_size_and_place(ready: Project) -> None:
    ready.write_voiceover("script-01", seconds=3.0)
    ready.write_script("script-01", slides("- at: friend\n  text: One\n", "- at: Here is the trick\n  text: Two\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), TWO_CARDS, browser=browser) == 0

    pill = next(n for n, page in enumerate(browser.pages) if "An AI clone, with consent" in page)
    assert browser.sizes[pill] == (720, 84)  # the approved look's pill, drawn at its own size
    # the approved look's pill sits 1330 px down a 1920 px frame: 1330 * 192 / 1920 = 133 rows of this 192 px one.
    # 84 px * 0.1 = 8.4 rows tall, so rows 133 to 140. 0.72 * 192 = 138.24, row 138, inside it.
    # 720 px * 0.1 = 72 columns wide, centred: (108 - 72) / 2 = 18 columns in, so columns 18 to 89.
    assert frame_colour(video(ready), 2.5, down=0.72) == pytest.approx(CARD_COLOURS[pill], abs=40)
    assert frame_colour(video(ready), 2.5, down=0.72, across=0.1) == pytest.approx(CARD_COLOURS[1], abs=40)  # column 10: outside
    assert frame_colour(video(ready), 2.5, down=0.72, across=0.2) == pytest.approx(CARD_COLOURS[pill], abs=40)  # 0.2 * 108 = 21.6, column 21: inside
    assert frame_colour(video(ready), 1.5, down=0.72) == pytest.approx(CARD_COLOURS[0], abs=40)  # card One: no pill
    # card Two cuts in at 2.2 - 0.12 = 2.08 s, and the pill comes with it. At 25 fps frames are 0.04 s apart:
    # the last frame of card One is at 2.04 s, and the first frame of card Two at 2.08 s
    assert frame_colour(video(ready), 2.04, down=0.72) == pytest.approx(CARD_COLOURS[0], abs=40)
    assert frame_colour(video(ready), 2.08, down=0.72) == pytest.approx(CARD_COLOURS[pill], abs=40)


def test_a_video_with_a_hook_but_no_slide_card_leaves_out_the_disclosure_with_a_warning(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", hooked('hook: "Did you apply?"\nhook_hold: 0.5\n'))  # the hook loads the Brand pack
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert not any("An AI clone" in page for page in browser.pages)
    error = capsys.readouterr().err
    assert "the disclosure is not shown in" in error and "no Slide card is drawn in it" in error


def test_a_video_drawn_in_no_brand_pack_says_nothing_about_a_disclosure(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", SPOKEN)  # no cards and no hook: nothing is drawn in the Brand pack

    assert run(ready, FakeFaceEngine()) == 0

    assert "the disclosure is not shown" not in capsys.readouterr().err  # not "disclosure": the test's name is in the path


END = {"line": "Do the *work*.", "url": "example.test"}


def marked(project: Project, **extra: Any) -> None:
    """Replace the plain Brand pack with one that has a wordmark, and any other settings given."""
    persona = project.root / "persona" / "examplepersona"
    shutil.rmtree(persona / "brand-packs")
    write_brand_pack(persona, **{"wordmark": "Brand Name", **extra})


def drawn_in(browser: FakeBrowser, mode: str) -> int:
    return next(n for n, page in enumerate(browser.pages) if f'"mode": "{mode}"' in page)


def test_the_badge_shows_bottom_left_over_the_face_section_and_never_over_a_slide_card(ready: Project) -> None:
    marked(ready)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    badge = drawn_in(browser, "badge")
    assert browser.sizes[badge] == (360, 100)
    assert '"text": "Brand Name"' in browser.pages[badge]
    # 360 x 100 at (48, 1500) of a 1920 px frame, scaled by 0.1: columns 5 to 40, rows 150 to 159.
    # 0.81 * 192 = 155.5, row 155; 0.2 * 108 = 21.6, column 21: inside it
    assert frame_colour(video(ready), 0.5, down=0.81, across=0.2) == pytest.approx(CARD_COLOURS[badge], abs=40)
    assert frame_colour(video(ready), 0.5, down=0.81, across=0.6) == pytest.approx(GREY, abs=40)  # column 64: outside
    assert frame_colour(video(ready), 0.5, down=0.5, across=0.2) == pytest.approx(GREY, abs=40)  # never over the face
    assert frame_colour(video(ready), 1.5, down=0.81, across=0.2) == pytest.approx(CARD_COLOURS[0], abs=40)  # the card


def test_a_badge_in_sixteen_by_nine_is_scaled_with_the_frame(ready: Project) -> None:
    ready.channel_yaml.write_text('persona: examplepersona\nformats:\n  - aspect: "16:9"\n    resolution: 192x108\n    fps: 25\n')
    write_banded_likeness(ready.likeness_horizontal, 800, 600)
    marked(ready)
    ready.write_script("script-01", hooked('hook: "Did you *apply*?"\nhook_hold: 0.5\n'))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    sixteen = ready.video("script-01", "192x108")
    badge = drawn_in(browser, "badge")
    # scaled by 108 / 1920 = 0.05625: a 20 x 6 px box at column 3, row 84; 0.81 * 108 = 87.5, row 87: inside it
    assert frame_colour(sixteen, 0.8, down=0.81, across=0.06) == pytest.approx(CARD_COLOURS[badge], abs=40)
    assert frame_colour(sixteen, 0.8, down=0.81, across=0.3) == pytest.approx(GREY, abs=40)  # column 57: outside


def test_a_brand_pack_with_no_wordmark_draws_no_badge(ready: Project) -> None:
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert not any('"mode": "badge"' in page for page in browser.pages)
    assert frame_colour(video(ready), 0.5, down=0.81, across=0.2) == pytest.approx(GREY, abs=40)


def test_the_end_card_holds_after_the_voiceover_in_silence_without_the_disclosure(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    marked(ready, end_card=END)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    end = drawn_in(browser, "end")
    assert browser.sizes[end] == (108, 192)
    assert '"line": "Do the *work*."' in browser.pages[end] and '"url": "example.test"' in browser.pages[end]
    assert float(ffprobe(video(ready))["format"]["duration"]) == pytest.approx(2.06 + 2.5, abs=0.06)
    assert frame_colour(video(ready), 1.5) == pytest.approx(CARD_COLOURS[0], abs=40)  # the Slide card while speaking
    assert frame_colour(video(ready), 3.5) == pytest.approx(CARD_COLOURS[end], abs=40)
    assert frame_colour(video(ready), 3.5, down=0.72) == pytest.approx(CARD_COLOURS[end], abs=40)  # no pill on it
    rate, samples = decode_audio(video(ready))
    assert np.abs(samples[int(2.2 * rate) :]).max() < 30  # silent once the Voiceover has ended
    speaking, fading = (np.abs(samples[int(a * rate) : int(b * rate)].astype(float)).mean() for a, b in ((1.0, 1.5), (1.95, 2.0)))
    assert fading < speaking / 2  # the fade-out still ends with the Voiceover, not with the end card
    assert "4.6 s long" in capsys.readouterr().out


def test_a_brand_pack_with_no_end_card_ends_the_video_with_the_voiceover(ready: Project) -> None:
    marked(ready)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))

    assert run(ready, FakeFaceEngine()) == 0

    assert float(ffprobe(video(ready))["format"]["duration"]) == pytest.approx(2.06, abs=0.06)


@pytest.mark.parametrize(
    ("settings", "named"),
    [
        ({"end_card": {"url": "example.test"}}, "end_card.line"),
        ({"end_card": {"line": "Do the work.", "url": " "}}, "end_card.url"),
        ({"wordmark": " "}, "empty wordmark"),
    ],
)
def test_a_brand_pack_with_an_unusable_wordmark_or_end_card_is_refused_naming_the_setting(
    ready: Project, capsys: pytest.CaptureFixture[str], settings: dict[str, Any], named: str
) -> None:
    marked(ready, **settings)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))

    assert run(ready, FakeFaceEngine()) == 1

    error = capsys.readouterr().err
    assert named in error and "pack.json" in error


def test_an_end_card_without_a_wordmark_is_refused(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    persona = ready.root / "persona" / "examplepersona"
    shutil.rmtree(persona / "brand-packs")
    write_brand_pack(persona, end_card=END)
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))

    assert run(ready, FakeFaceEngine()) == 1

    assert "has an end_card but no wordmark" in capsys.readouterr().err


def test_the_brand_packs_serif_is_filled_into_the_page_when_it_names_one(ready: Project) -> None:
    persona = ready.root / "persona" / "examplepersona"
    shutil.rmtree(persona / "brand-packs")
    pack = write_brand_pack(persona, fonts={"ui": "Ui.ttf", "mono": "Mono.ttf", "artifact": "Serif.ttf"})
    (pack / "fonts" / "Serif.ttf").write_bytes(b"font")
    (pack / "slide.html").write_text('<style>@font-face{src:url("__FONT_ARTIFACT__")}</style><script>const S = __SLIDE__;</script>')
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))
    browser = FakeBrowser()

    assert run(ready, FakeFaceEngine(), browser=browser) == 0

    assert (pack / "fonts" / "Serif.ttf").resolve().as_uri() in browser.pages[0]


def test_a_brand_pack_naming_a_missing_serif_is_refused(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    persona = ready.root / "persona" / "examplepersona"
    shutil.rmtree(persona / "brand-packs")
    write_brand_pack(persona, fonts={"ui": "Ui.ttf", "mono": "Mono.ttf", "artifact": "Serif.ttf"})
    ready.write_script("script-01", slides("- at: Here is the trick\n  text: One\n"))

    assert run(ready, FakeFaceEngine()) == 1

    assert "names font Serif.ttf for fonts.artifact" in capsys.readouterr().err
