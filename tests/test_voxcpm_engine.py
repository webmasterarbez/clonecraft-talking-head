import sys
from pathlib import Path

import pytest

from clonecraft.cli import main
from clonecraft.voxcpm import VoxCpmEngine
from tests.support import RATE, Project, read_wav

WORKER = Path(__file__).parent / "fake_worker.py"


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "worker.log"
    monkeypatch.setenv("FAKE_WORKER_LOG", str(path))
    return path


def run_voiceover(project: Project, mode: str) -> int:
    engine = VoxCpmEngine(Path(sys.executable), WORKER, Path(mode), Path("whisper"))
    return main(["voiceover", project.channel_ref, "script-01"], root=project.root, voice_engine=engine)


def test_the_worker_speaks_and_hears_every_piece_with_its_style_and_the_voice_reference_and_is_started_once(
    project: Project, log: Path
) -> None:
    project.write_script("script-01", "[warmly] First paragraph.\n\nSecond paragraph.")

    assert run_voiceover(project, "ok") == 0

    lines = log.read_text().splitlines()
    assert lines == [
        "start",
        f"say style=warmly text=First paragraph. reference={project.voice_reference} transcript=None",
        "hear take-0.wav",
        f"say style=None text=Second paragraph. reference={project.voice_reference} transcript=None",
        "hear take-0.wav",
        "hear script-01.wav",  # the whole Voiceover, once, for its word timings
    ]
    rate, _ = read_wav(project.voiceover("script-01"))
    assert rate == RATE


def test_not_enough_gpu_memory_in_the_worker_is_reported_as_such(
    project: Project, log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_voiceover(project, "no-gpu") != 0

    err = capsys.readouterr().err
    assert "GPU memory" in err and "needs about 8.5 GB, 3.0 GB free" in err
    assert not project.voiceover("script-01").exists()


def test_a_worker_that_dies_is_reported_with_its_exit_code(project: Project, log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_voiceover(project, "crash") != 0

    assert "stopped unexpectedly (exit code 3)" in capsys.readouterr().err


def test_a_failed_piece_is_reported_with_the_workers_reason(project: Project, log: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_voiceover(project, "fails") != 0

    assert "the model gave up" in capsys.readouterr().err


def test_the_engine_is_found_only_when_its_environment_and_model_are_installed(tmp_path: Path) -> None:
    assert VoxCpmEngine.installed_in(tmp_path) is None


def test_a_transcript_beside_the_voice_reference_is_sent_with_every_piece(project: Project, log: Path) -> None:
    project.voice_reference.with_suffix(".txt").write_text("  The exact words of the reference.\n")
    project.write_script("script-01", "First paragraph.\n\nSecond paragraph.")

    assert run_voiceover(project, "ok") == 0

    said = [line for line in log.read_text().splitlines() if line.startswith("say")]
    assert [line.rsplit(" transcript=", 1)[1] for line in said] == ["The exact words of the reference."] * 2


def test_a_cue_is_not_sent_when_there_is_a_transcript_because_the_engine_would_read_it_aloud(
    project: Project, log: Path
) -> None:
    project.voice_reference.with_suffix(".txt").write_text("The exact words of the reference.")
    project.write_script("script-01", "[warmly] First paragraph.")

    assert run_voiceover(project, "ok") == 0

    said = [line for line in log.read_text().splitlines() if line.startswith("say")]
    assert said == [
        f"say style=None text=First paragraph. reference={project.voice_reference} transcript=The exact words of the reference."
    ]
