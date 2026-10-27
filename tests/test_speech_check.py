import pytest

from clonecraft.cli import main
from tests.support import RATE, FakeVoiceEngine, Project, Take, read_wav

# One piece of 20 three-letter words, with no punctuation, so a transcript missing its last k words scores
# 2×(20−k)/(40−k) on words and 2×3(20−k)/(60+3(20−k)) on letters: the same number, which is the score.
WORDS = [f"w{i:02d}" for i in range(1, 21)]
SCRIPT = " ".join(WORDS)


def first(n: int) -> str:
    return " ".join(WORDS[:n])


def run_voiceover(project: Project, engine: FakeVoiceEngine, script: str = SCRIPT) -> int:
    project.write_script("script-01", script)
    return main(["voiceover", project.channel_ref, "script-01"], root=project.root, voice_engine=engine)


def seconds_of_voiceover(project: Project) -> float:
    _, samples = read_wav(project.voiceover("script-01"))
    return len(samples) / RATE


def test_a_take_heard_almost_right_is_kept_without_another_try(project: Project) -> None:
    engine = FakeVoiceEngine(takes=[Take(heard=first(18))])  # 2×18/38 = 94.7: at least 92 passes

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 1


def test_a_take_in_the_middle_band_is_tried_once_more_and_the_better_one_kept(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = FakeVoiceEngine(takes=[Take(heard=first(17)), Take(seconds=2.0)])  # 2×17/37 = 91.9: from 85 to 92

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 2
    assert seconds_of_voiceover(project) == pytest.approx(2.06, abs=0.01)  # the 2.0 s second take + 0.06 s padding
    assert "91.9" in capsys.readouterr().out


def test_after_two_middle_band_takes_the_later_one_is_kept_as_the_approved_look_did(project: Project) -> None:
    engine = FakeVoiceEngine(takes=[Take(heard=first(17)), Take(heard=first(16), seconds=2.0)])  # 91.9, then 2×16/36 = 88.9

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 2
    assert seconds_of_voiceover(project) == pytest.approx(2.06, abs=0.01)  # the later 2.0 s take + 0.06 s padding


def test_after_three_takes_the_best_one_of_at_least_85_is_kept(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    # 2×15/35 = 85.7 is in the middle band, so a second take is tried; 2×14/34 = 82.4 is low, so a third
    low = Take(heard=first(14))
    engine = FakeVoiceEngine(takes=[Take(heard=first(15), seconds=2.0), low, low])

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 3
    assert seconds_of_voiceover(project) == pytest.approx(2.06, abs=0.01)  # the first, 2.0 s take + 0.06 s padding
    flags = [line for line in capsys.readouterr().out.splitlines() if line.startswith("speech check")]
    assert any("kept" in line and "85.7" in line for line in flags)
    assert all(SCRIPT in line for line in flags)  # each flag names its piece


def test_a_take_with_too_much_audio_after_the_last_word_is_never_kept_however_well_it_scored(project: Project) -> None:
    # the first take is heard perfectly but runs on 1.1 s (0.2 s gap + 0.6 s babble + 0.3 s padding); the others score 82.4
    low = Take(heard=first(14))
    engine = FakeVoiceEngine(takes=[Take(babble=0.6), low, low])

    assert run_voiceover(project, engine) == 1

    assert len(engine.calls) == 3
    assert not project.voiceover("script-01").exists()


def test_the_score_blends_words_and_letters(project: Project) -> None:
    # The last two words each misheard by one letter: words 2×18/40 = 90.0, letters 2×58/120 = 96.7,
    # blended (90.0 + 96.7)/2 = 93.3, a pass. Words alone would be in the middle band and try again.
    engine = FakeVoiceEngine(takes=[Take(heard=first(18) + " w1x w2x")])

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 1


def test_a_piece_with_no_take_of_at_least_85_stops_the_run_and_names_the_piece(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = FakeVoiceEngine(takes=[Take(heard=first(14))] * 3)  # 82.4 every time

    assert run_voiceover(project, engine) == 1

    assert len(engine.calls) == 3
    err = capsys.readouterr().err
    assert err.startswith("clonecraft: ") and SCRIPT in err and "82.4" in err
    assert not project.voiceover("script-01").exists()


def test_up_to_a_second_of_unheard_audio_after_the_last_word_is_cut_off(project: Project) -> None:
    # after the last heard word: 0.1 s still speaking + 0.2 s gap + 0.2 s babble + 0.3 s padding = 0.8 s, over 0.5 s,
    # so it is cut where the gap begins, not where the transcriber put the end of the last word
    engine = FakeVoiceEngine(takes=[Take(babble=0.2, early=0.1)])

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 1
    assert seconds_of_voiceover(project) == pytest.approx(1.06, abs=0.01)  # 1.0 s speech + 0.06 s padding, no babble


def test_over_a_second_of_unheard_audio_after_the_last_word_is_tried_again(project: Project) -> None:
    # 0.2 s gap + 0.6 s babble + 0.3 s padding = 1.1 s after the last heard word: over 1.0 s, a bad take
    engine = FakeVoiceEngine(takes=[Take(babble=0.6, seconds=2.0), Take()])

    assert run_voiceover(project, engine) == 0

    assert len(engine.calls) == 2
    assert seconds_of_voiceover(project) == pytest.approx(1.06, abs=0.01)  # the second, 1.0 s take + 0.06 s padding


def test_digits_the_transcriber_writes_count_as_the_spelled_out_number(project: Project) -> None:
    engine = FakeVoiceEngine(takes=[Take(heard="she has 48 cats and 100 dogs")])

    assert run_voiceover(project, engine, script="she has forty eight cats and one hundred dogs") == 0

    assert len(engine.calls) == 1  # heard as "forty eight" and "one hundred": a perfect score
