import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from clonecraft.cli import main
from tests.support import (
    RATE,
    GOOD_LOUDNESS_DB,
    tone,
    Answers,
    FakeVoiceEngine,
    Project,
    longest_quiet_run_seconds,
    read_wav,
    silence,
    speechy,
    write_sample_with_known_regions,
    write_wav,
)


def run_voiceover(project: Project, engine: FakeVoiceEngine, ask: Answers) -> int:
    return main(["voiceover", project.channel_ref, "script-01"], root=project.root, voice_engine=engine, ask=ask)


def printed_starts(output: str) -> list[float]:
    return [float(start) for start in re.findall(r"candidate \d: starts at ([\d.]+) s", output)]


@pytest.fixture
def needs_reference(project: Project) -> Project:
    project.voice_reference.unlink()
    write_sample_with_known_regions(project.voice_sample)
    return project


def test_three_good_candidates_are_offered_and_the_chosen_one_becomes_the_voice_reference(
    needs_reference: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = FakeVoiceEngine()

    assert run_voiceover(needs_reference, engine, Answers("2")) == 0

    assert sorted(printed_starts(capsys.readouterr().out)) == [0.0, 73.0, 119.0]
    candidates = sorted(needs_reference.candidates_dir.glob("candidate-*.wav"))
    assert [c.name for c in candidates] == ["candidate-1.wav", "candidate-2.wav", "candidate-3.wav"]
    for candidate in candidates:
        rate, samples = read_wav(candidate)
        assert (rate, len(samples)) == (RATE, 20 * RATE)
    assert needs_reference.voice_reference.read_bytes() == candidates[1].read_bytes()
    assert engine.references == [needs_reference.voice_reference]


def test_an_invalid_choice_asks_again_instead_of_saving(needs_reference: Project) -> None:
    ask = Answers("9", "zero", "", "3")

    assert run_voiceover(needs_reference, FakeVoiceEngine(), ask) == 0

    assert len(ask.prompts) == 4
    chosen = (needs_reference.candidates_dir / "candidate-3.wav").read_bytes()
    assert needs_reference.voice_reference.read_bytes() == chosen


def test_the_saved_voice_reference_is_used_next_time_without_asking(needs_reference: Project) -> None:
    run_voiceover(needs_reference, FakeVoiceEngine(), Answers("1"))
    saved = needs_reference.voice_reference.read_bytes()

    assert run_voiceover(needs_reference, FakeVoiceEngine(), Answers()) == 0  # Answers() fails if it is asked anything

    assert needs_reference.voice_reference.read_bytes() == saved


def test_a_persona_with_no_voice_sample_and_no_voice_reference_is_not_ready(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.voice_reference.unlink()

    assert run_voiceover(project, FakeVoiceEngine(), Answers()) != 0

    err = capsys.readouterr().err
    assert "examplepersona" in err and "Voice Sample" in err and "not ready" in err


def test_every_candidate_is_steady_unclipped_and_as_loud_as_the_rest_of_the_speech(needs_reference: Project) -> None:
    run_voiceover(needs_reference, FakeVoiceEngine(), Answers("1"))

    for candidate in needs_reference.candidates_dir.glob("candidate-*.wav"):
        _, samples = read_wav(candidate)
        assert longest_quiet_run_seconds(samples, RATE, below_db=GOOD_LOUDNESS_DB - 20) <= 1.0
        assert int(np.abs(samples.astype(np.int32)).max()) < 32_700
        spoken = samples[np.abs(samples) > 1_000].astype(np.float64)  # the tone, without its pauses
        loudness = 10 * np.log10(np.mean(spoken**2) / 32768.0**2)
        assert abs(loudness - GOOD_LOUDNESS_DB) < 3.0


def test_fewer_than_three_good_stretches_means_fewer_candidates(
    needs_reference: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    write_wav(needs_reference.voice_sample, np.concatenate([speechy(20.0), silence(3.0), speechy(20.0)]))

    assert run_voiceover(needs_reference, FakeVoiceEngine(), Answers("2")) == 0

    assert printed_starts(capsys.readouterr().out) == [0.0, 23.0]
    assert needs_reference.voice_reference.read_bytes() == (needs_reference.candidates_dir / "candidate-2.wav").read_bytes()


def test_a_sample_with_no_good_stretch_is_an_error_naming_it(
    needs_reference: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    write_wav(needs_reference.voice_sample, speechy(12.0))  # shorter than 20 s

    assert run_voiceover(needs_reference, FakeVoiceEngine(), Answers()) != 0

    assert "voice-sample.wav" in capsys.readouterr().err
    assert not needs_reference.voice_reference.exists()


@pytest.mark.parametrize("failure", [EOFError(), KeyboardInterrupt()], ids=["end of input", "Ctrl-C"])
def test_no_choice_at_the_prompt_stops_cleanly_without_saving(
    needs_reference: Project, capsys: pytest.CaptureFixture[str], failure: BaseException
) -> None:
    def gives_up(prompt: str) -> str:
        raise failure

    code = main(
        ["voiceover", needs_reference.channel_ref, "script-01"],
        root=needs_reference.root, voice_engine=FakeVoiceEngine(), ask=gives_up,
    )

    assert code != 0
    assert "No Voice Reference was chosen" in capsys.readouterr().err
    assert not needs_reference.voice_reference.exists()


def test_a_look_alike_digit_is_not_a_choice(needs_reference: Project) -> None:
    ask = Answers("²", "1")

    assert run_voiceover(needs_reference, FakeVoiceEngine(), ask) == 0

    assert len(ask.prompts) == 2


def test_speech_with_loud_bursts_still_gets_candidates(needs_reference: Project) -> None:
    """Every second is 0.9 s at 0.1 and 0.1 s at 0.5: the average power sits 5 dB above the usual loudness."""
    second = np.concatenate([tone(0.9, amplitude=0.1), tone(0.1, amplitude=0.5)])
    write_wav(needs_reference.voice_sample, np.tile(second, 45))
    ask = Answers("1")

    assert run_voiceover(needs_reference, FakeVoiceEngine(), ask) == 0

    assert len(list(needs_reference.candidates_dir.glob("candidate-*.wav"))) == 2  # 45 s holds two 20 s stretches


def test_a_voice_sample_in_another_format_such_as_mp3_is_read(
    needs_reference: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    needs_reference.voice_sample.unlink()
    wav = needs_reference.voice_sample.with_name("source.wav")
    write_wav(wav, np.concatenate([speechy(20.0), silence(3.0), speechy(20.0)]))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav), str(needs_reference.voice_sample.with_suffix(".mp3"))],
        check=True,
        stdin=subprocess.DEVNULL)
    wav.unlink()

    assert run_voiceover(needs_reference, FakeVoiceEngine(), Answers("1")) == 0

    assert printed_starts(capsys.readouterr().out) == [0.0, 23.0]


def test_a_choice_typed_at_the_real_prompt_is_not_read_by_the_decoder(
    needs_reference: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stand-in ffmpeg takes one byte from its standard input, as the real one does while it runs."""
    stub = tmp_path / "bin" / "ffmpeg"
    stub.parent.mkdir()
    stub.write_text(f'#!/bin/sh\nhead -c 1 > /dev/null\nexec {shutil.which("ffmpeg")} "$@"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub.parent}{os.pathsep}{os.environ['PATH']}")
    typed = tmp_path / "typed"
    typed.write_text("2\n")
    saved = os.dup(0)
    os.dup2(os.open(typed, os.O_RDONLY), 0)  # the descriptor a child program would inherit
    monkeypatch.setattr(sys, "stdin", open(0, closefd=False))
    try:
        code = main(["voiceover", needs_reference.channel_ref, "script-01"], root=needs_reference.root, voice_engine=FakeVoiceEngine())
    finally:
        os.dup2(saved, 0)
        os.close(saved)

    assert code == 0
    chosen = needs_reference.candidates_dir / "candidate-2.wav"
    assert needs_reference.voice_reference.read_bytes() == chosen.read_bytes()
