from pathlib import Path

import numpy as np
import pytest

from clonecraft.cli import main
from clonecraft.voice import NotEnoughGpuMemory
from tests.support import (
    RATE,
    Answers,
    FakeVoiceEngine,
    Project,
    longest_quiet_run_seconds,
    read_wav,
    write_sample_with_known_regions,
)


def run_voiceover(project: Project, engine: FakeVoiceEngine, script: str = "script-01") -> int:
    return main(["voiceover", project.channel_ref, script], root=project.root, voice_engine=engine)


def test_voiceover_is_written_named_after_the_script_and_its_duration_is_printed(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_voiceover(project, FakeVoiceEngine()) == 0

    rate, samples = read_wav(project.voiceover("script-01"))
    assert rate == RATE
    assert len(samples) / rate == pytest.approx(1.06, abs=0.01)  # 1.0 s of speech plus 0.03 s of padding each side
    assert "1.1 s" in capsys.readouterr().out


def test_a_cue_styles_its_paragraph_and_the_next_paragraph_is_neutral(project: Project) -> None:
    project.write_script(
        "script-01",
        "[warmly] So did you apply this morning?\nHere is the thing.\n\nI spent years on the hiring side.\n",
    )
    engine = FakeVoiceEngine()

    assert run_voiceover(project, engine) == 0

    assert engine.calls == [
        ("warmly", "So did you apply this morning? Here is the thing."),
        (None, "I spent years on the hiring side."),
    ]


def test_a_cue_in_the_middle_of_a_paragraph_restyles_the_rest_of_it(project: Project) -> None:
    project.write_script("script-01", "Listen up. [firmly] This part matters. Check the date.\n\nBack to normal.")
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    assert engine.calls == [
        (None, "Listen up."),
        ("firmly", "This part matters. Check the date."),
        (None, "Back to normal."),
    ]


def test_no_cue_is_spoken_and_every_word_of_the_script_is_kept(project: Project) -> None:
    project.write_script(
        "script-01",
        "[warmly] You're not — because you're not good enough.\n\n[firmly] Cross off the ghosts, ten of them.",
    )
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    spoken = " ".join(text for _, text in engine.calls)
    assert spoken == "You're not — because you're not good enough. Cross off the ghosts, ten of them."


def test_pieces_are_joined_with_a_short_pause(project: Project) -> None:
    project.write_script("script-01", "First paragraph.\n\nSecond paragraph.")

    run_voiceover(project, FakeVoiceEngine())

    _, samples = read_wav(project.voiceover("script-01"))
    # two 1.0 s pieces, each with 0.03 s padding either side, and 0.34 s of silence added between them
    assert len(samples) / RATE == pytest.approx(2.46, abs=0.01)
    assert longest_quiet_run_seconds(samples, RATE) == pytest.approx(0.40, abs=0.02)


def test_joins_fade_instead_of_clicking(project: Project) -> None:
    project.write_script("script-01", "First paragraph.\n\nSecond paragraph.")

    run_voiceover(project, FakeVoiceEngine())

    _, samples = read_wav(project.voiceover("script-01"))
    biggest_step = int(np.abs(np.diff(samples.astype(np.int32))).max())
    # a 220 Hz tone at half scale never steps more than about 470 between samples; an unfaded start jumps by 16000
    assert biggest_step < 1500


def test_a_long_pause_inside_a_piece_is_shortened_to_the_join_pause(project: Project) -> None:
    run_voiceover(project, FakeVoiceEngine(inner_pause=1.5))

    _, samples = read_wav(project.voiceover("script-01"))
    # 0.5 s + 1.5 s pause + 0.5 s, the pause cut to 0.4 s, plus 0.03 s padding each side
    assert len(samples) / RATE == pytest.approx(1.46, abs=0.01)
    assert longest_quiet_run_seconds(samples, RATE) == pytest.approx(0.40, abs=0.02)


def test_a_hum_louder_than_the_pause_floor_is_not_cut_as_a_pause(project: Project) -> None:
    run_voiceover(project, FakeVoiceEngine(inner_pause=1.5, pause_amplitude=0.0045))  # about -47 dBFS: over -50

    _, samples = read_wav(project.voiceover("script-01"))
    assert len(samples) / RATE == pytest.approx(2.56, abs=0.01)  # 0.5 s + 1.5 s hum + 0.5 s + 0.06 s padding


def test_a_quiet_but_voiced_tail_is_not_cut_off(project: Project) -> None:
    run_voiceover(project, FakeVoiceEngine(tail=0.2))

    _, samples = read_wav(project.voiceover("script-01"))
    assert len(samples) / RATE == pytest.approx(1.26, abs=0.01)  # 1.0 s + 0.2 s tail + 0.06 s padding


def test_remaking_a_voiceover_replaces_the_old_one(project: Project) -> None:
    run_voiceover(project, FakeVoiceEngine())
    project.write_script("script-01", "First paragraph.\n\nSecond paragraph.")

    run_voiceover(project, FakeVoiceEngine())

    _, samples = read_wav(project.voiceover("script-01"))
    assert len(samples) / RATE == pytest.approx(2.46, abs=0.01)  # as in the join test: 1.06 + 0.34 + 1.06
    assert sorted(p.name for p in project.voiceover("script-01").parent.iterdir()) == ["script-01.spoken.sha256", "script-01.wav", "script-01.words.json"]


def test_the_engines_own_sample_rate_is_kept(project: Project) -> None:
    run_voiceover(project, FakeVoiceEngine(rate=24_000))

    rate, samples = read_wav(project.voiceover("script-01"))
    assert rate == 24_000
    assert len(samples) / rate == pytest.approx(1.06, abs=0.01)


def test_the_persona_voice_reference_is_what_the_engine_clones_from(project: Project) -> None:
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    assert engine.references == [project.voice_reference]


def sentence(n: int, words: int) -> str:
    return " ".join([f"w{n}"] * (words - 1)) + f" end{n}."


def test_a_sentence_over_the_chunk_size_is_spoken_whole_and_keeps_its_cue(project: Project) -> None:
    sentences = [sentence(i, 20) for i in (1, 2, 3)]  # each over the 18 word chunk size
    project.write_script("script-01", "[warmly] " + " ".join(sentences) + "\n\nShort one.")
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    assert engine.calls == [("warmly", s) for s in sentences] + [(None, "Short one.")]


def test_whole_sentences_are_packed_into_chunks_of_at_most_18_words(project: Project) -> None:
    sentences = [sentence(i, 8) for i in (1, 2, 3, 4, 5)]  # 8 + 8 = 16 fits; a third would make 24
    project.write_script("script-01", " ".join(sentences))
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    assert engine.calls == [
        (None, f"{sentences[0]} {sentences[1]}"),
        (None, f"{sentences[2]} {sentences[3]}"),
        (None, sentences[4]),
    ]


def test_a_paragraph_that_fits_in_one_chunk_is_spoken_whole(project: Project) -> None:
    whole = " ".join([sentence(i, 9) for i in (1, 2)])  # 18 words: exactly the chunk size
    project.write_script("script-01", whole)
    engine = FakeVoiceEngine()

    run_voiceover(project, engine)

    assert engine.calls == [(None, whole)]


def test_a_missing_script_is_named_in_the_error(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_voiceover(project, FakeVoiceEngine(), script="script-99") != 0

    assert "script-99" in capsys.readouterr().err


def test_an_unknown_channel_is_named_in_the_error(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["voiceover", "youtube/@nobody", "script-01"], root=project.root, voice_engine=FakeVoiceEngine())

    assert code != 0
    assert "youtube/@nobody" in capsys.readouterr().err


def test_a_channel_without_settings_is_named_in_the_error(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    (project.channel_dir / "channel.yaml").unlink()

    assert run_voiceover(project, FakeVoiceEngine()) != 0

    assert "channel.yaml" in capsys.readouterr().err


def test_a_channel_naming_a_persona_that_does_not_exist_is_named_in_the_error(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    (project.channel_dir / "channel.yaml").write_text("persona: nobody\n")

    assert run_voiceover(project, FakeVoiceEngine()) != 0

    err = capsys.readouterr().err
    assert "nobody" in err and "Persona" in err


def test_a_missing_voice_reference_is_named_in_the_error(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.voice_reference.unlink()

    assert run_voiceover(project, FakeVoiceEngine()) != 0

    err = capsys.readouterr().err
    assert "Voice Reference" in err and "examplepersona" in err


def test_not_enough_free_gpu_memory_is_reported_and_nothing_is_written(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = FakeVoiceEngine(raises=NotEnoughGpuMemory("needs about 8.5 GB, 3 GB free"))

    assert run_voiceover(project, engine) != 0

    err = capsys.readouterr().err
    assert "GPU memory" in err and "needs about 8.5 GB, 3 GB free" in err
    assert not project.voiceover("script-01").exists()


def test_without_an_installed_voice_engine_the_command_says_so(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["voiceover", project.channel_ref, "script-01"], root=project.root) != 0

    err = capsys.readouterr().err
    assert "voice engine" in err and "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo" in err


def test_without_an_installed_voice_engine_no_voice_reference_is_asked_for(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.voice_reference.unlink()
    write_sample_with_known_regions(project.voice_sample)

    assert main(["voiceover", project.channel_ref, "script-01"], root=project.root, ask=Answers()) != 0

    assert "voice engine" in capsys.readouterr().err
    assert not project.candidates_dir.exists()


def test_a_script_with_nothing_to_speak_asks_for_no_voice_reference(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.voice_reference.unlink()
    write_sample_with_known_regions(project.voice_sample)
    project.write_script("script-01", "[warmly]\n")

    assert main(["voiceover", project.channel_ref, "script-01"], root=project.root, voice_engine=FakeVoiceEngine(), ask=Answers()) != 0

    assert "nothing to speak" in capsys.readouterr().err
    assert not project.candidates_dir.exists()


def test_a_script_with_nothing_to_speak_is_reported(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write_script("script-01", "[warmly]\n\n   \n")

    assert run_voiceover(project, FakeVoiceEngine()) != 0

    assert "nothing to speak" in capsys.readouterr().err


class RateDriftingEngine(FakeVoiceEngine):
    """Writes its first piece at 48 kHz and every later one at 24 kHz."""

    def synthesize(self, text: str, style: str | None, reference: Path, out: Path) -> None:
        self.rate = RATE if not self.calls else 24_000
        super().synthesize(text, style, reference, out)


def test_pieces_at_different_sample_rates_are_an_error_and_keep_the_old_voiceover(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    run_voiceover(project, FakeVoiceEngine())
    project.write_script("script-01", "First paragraph.\n\nSecond paragraph.")

    assert run_voiceover(project, RateDriftingEngine()) != 0

    assert "sample rate" in capsys.readouterr().err
    _, samples = read_wav(project.voiceover("script-01"))
    assert len(samples) / RATE == pytest.approx(1.06, abs=0.01)  # still the first, one-piece Voiceover
