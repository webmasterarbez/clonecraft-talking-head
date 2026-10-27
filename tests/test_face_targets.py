from pathlib import Path

import pytest

from clonecraft.cards import Shown, parse
from clonecraft.face_targets import sentence_starts, warnings
from clonecraft.project import ProjectError
from clonecraft.script import ScriptParts, parts_of
from clonecraft.voice import Word

SCRIPT = Path("script-01.md")
WORDS = [Word("Hello.", 0.0, 0.5), Word("There", 0.6, 0.9), Word("friend?", 1.0, 1.4), Word("Yes", 2.0, 2.2)]


def test_sentence_starts_are_the_first_word_and_each_word_after_a_full_stop_or_question_mark() -> None:
    assert sentence_starts(WORDS) == [0.0, 0.6, 2.0]


def opening_and_closing(front: float, back: float, total: float) -> list[Shown]:
    closing = parse("- at: So tonight\n  kind: face\n", SCRIPT)[0]
    return [Shown(None, 0.0, front), Shown(closing, back, total)]


def parts(front: float | None = None, back: float | None = None) -> ScriptParts:
    return ScriptParts("spoken", [], face_front_s=front, face_back_s=back)


def test_a_face_section_within_a_second_and_a_half_of_its_target_gives_no_warning() -> None:
    assert warnings(parts(20, 10), opening_and_closing(20.9, 60.0, 70.0), WORDS, 70.0) == []


def test_an_opening_face_section_that_misses_its_target_names_the_nearest_sentence_start() -> None:
    out = warnings(parts(20), opening_and_closing(24.0, 60.0, 70.0), WORDS, 70.0)

    assert len(out) == 1 and "the opening Face section is 24.0 s, not 20 s" in out[0] and "2.0 s" in out[0]


def test_a_closing_face_section_that_misses_its_target_names_the_nearest_sentence_start() -> None:
    out = warnings(parts(back=10), opening_and_closing(20.0, 40.0, 70.0), WORDS, 70.0)

    assert len(out) == 1 and "the closing Face section is 30.0 s, not 10 s" in out[0]


def test_a_target_with_no_face_section_is_warned_about() -> None:
    card_only = [Shown(parse("- at: Hello\n  text: One\n", SCRIPT)[0], 0.0, 70.0)]

    out = warnings(parts(20), card_only, WORDS, 70.0)

    assert out == ["face_front_s is 20 s but the Video opens on a Slide card, so there is no opening Face section"]


def test_a_front_matter_target_is_read_as_seconds_and_a_bad_one_is_refused_naming_the_key(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("---\nface_front_s: 20\nface_back_s: 10.5\n---\nHello there.\n")
    assert parts_of(good.read_text(), good).face_front_s == 20.0
    assert parts_of(good.read_text(), good).face_back_s == 10.5

    bad = tmp_path / "bad.md"
    bad.write_text("---\nface_front_s: 0\n---\nHello there.\n")
    with pytest.raises(ProjectError, match="face_front_s in .*bad.md must be a number of seconds above 0"):
        parts_of(bad.read_text(), bad)
