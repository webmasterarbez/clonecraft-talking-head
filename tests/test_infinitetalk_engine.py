import sys
from pathlib import Path

import pytest

from clonecraft.cli import main
from clonecraft.infinitetalk import InfiniteTalkEngine
from clonecraft.voice import Word
from tests.support import (
    FakeBrowser,
    FakeVoiceEngine,
    Project,
    ffprobe,
    video_stream,
    write_banded_likeness,
    write_brand_pack,
)

REPO = Path(__file__).parent.parent
FAKE_COMFY = Path(__file__).parent / "fake_comfy.py"


@pytest.fixture
def ready(project: Project) -> Project:
    write_banded_likeness(project.likeness)
    project.write_voiceover("script-01", seconds=1.0)
    return project


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "comfy.log"
    monkeypatch.setenv("FAKE_COMFY_LOG", str(path))
    return path


def run_video(project: Project, mode: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("FAKE_COMFY_MODE", mode)
    engine = InfiniteTalkEngine(Path(sys.executable), FAKE_COMFY, project.root, REPO / "config" / "infinitetalk-graph.json")
    return main(["video", project.channel_ref, "script-01"], root=project.root, face_engine=engine)


def test_comfyui_gets_the_portrait_the_voiceover_and_its_frame_count_and_its_clip_becomes_the_video(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_video(ready, "ok", monkeypatch) == 0

    # 0.03 s + 1.0 s + 0.03 s of Voiceover = 1.06 s, at 25 fps 26.5 frames, rounded up to 27
    assert log.read_text().splitlines() == [
        "start",
        "prompt image=portrait.png exists=True audio=voiceover-00.wav exists=True frames=27 size=480x832",
        "stopped",
    ]
    stream = video_stream(ready.video("script-01"))
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert float(ffprobe(ready.video("script-01"))["format"]["duration"]) == pytest.approx(1.06, abs=0.1)


def test_the_engine_is_found_only_when_its_environment_comfyui_and_models_are_installed(tmp_path: Path) -> None:
    assert InfiniteTalkEngine.installed_in(tmp_path) is None


def test_without_the_face_engine_the_missing_parts_and_the_install_command_are_named(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["video", ready.channel_ref, "script-01"], root=ready.root) != 0

    err = capsys.readouterr().err
    assert "vendor/face-env/bin/python" in err and "vendor/ComfyUI/main.py" in err and "models/comfy" in err
    assert "sh scripts/install-face-engine.sh" in err


def test_a_graph_comfyui_refuses_is_reported_with_the_node_at_fault_and_comfyui_is_stopped(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_video(ready, "invalid", monkeypatch) != 0

    err = capsys.readouterr().err
    assert "ComfyUI refused the graph: text_embeds (WanVideoTextEncodeCached): Value not in list" in err
    assert log.read_text().splitlines()[-1] == "stopped"
    assert not ready.video("script-01").exists()


def test_a_node_that_fails_while_rendering_is_named_with_its_error_and_comfyui_is_stopped(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_video(ready, "fails", monkeypatch) != 0

    err = capsys.readouterr().err
    assert "sampler (WanVideoSampler) failed with torch.OutOfMemoryError: Allocation on device" in err
    assert log.read_text().splitlines()[-1] == "stopped"


def test_comfyui_dying_on_start_is_reported_with_its_exit_code(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_video(ready, "crash", monkeypatch) != 0

    assert "ComfyUI stopped unexpectedly (exit code 3)" in capsys.readouterr().err


def test_a_face_section_comfyui_never_finishes_is_abandoned_with_the_section_named(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("clonecraft.infinitetalk.JOB_TIMEOUT_S", 2.0)
    assert run_video(ready, "hangs", monkeypatch) != 0

    err = capsys.readouterr().err
    assert "ComfyUI did not finish voiceover-00.wav within 2 s; see its output above" in err
    assert log.read_text().splitlines()[-1] == "stopped"



def test_comfyui_is_asked_for_the_landscape_size_for_a_sixteen_by_nine_video(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_COMFY_MODE", "ok")
    monkeypatch.setattr("clonecraft.cli.SIXTEEN_BY_NINE_VERIFIED", True)
    ready.channel_yaml.write_text(
        'persona: examplepersona\nformats:\n  - aspect: "9:16"\n    resolution: 1080x1920\n    fps: 30\n'
        '  - aspect: "16:9"\n    resolution: 1920x1080\n    fps: 30\n'
    )
    write_banded_likeness(ready.likeness_horizontal, width=1600, height=900)
    engine = InfiniteTalkEngine(Path(sys.executable), FAKE_COMFY, ready.root, REPO / "config" / "infinitetalk-graph.json")

    code = main(["video", ready.channel_ref, "script-01", "--format", "16:9"], root=ready.root, face_engine=engine)

    assert code == 0
    assert log.read_text().splitlines()[1].endswith("size=832x480")


def test_every_face_section_of_a_video_is_rendered_by_one_comfyui_start(
    ready: Project, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_COMFY_MODE", "ok")
    ready.write_voiceover("script-01", seconds=3.0)
    write_brand_pack(ready.root / "persona" / "examplepersona")
    ready.write_script("script-01", "Hello there friend. Here is the trick.\n\n<!-- slides -->\n"
                       "- at: friend\n  text: One\n- at: Here is the trick\n  kind: face\n")
    heard = [Word("Hello", 0.03, 0.4), Word("there", 0.4, 0.7), Word("friend.", 1.0, 1.3),
             Word("Here", 2.0, 2.2), Word("is", 2.2, 2.4), Word("the", 2.4, 2.6), Word("trick.", 2.6, 3.0)]
    engine = InfiniteTalkEngine(Path(sys.executable), FAKE_COMFY, ready.root, REPO / "config" / "infinitetalk-graph.json")

    code = main(
        ["video", ready.channel_ref, "script-01"], root=ready.root, face_engine=engine, browser=FakeBrowser(),
        voice_engine=FakeVoiceEngine(words_in={ready.voiceover("script-01"): heard}),
    )

    assert code == 0
    lines = log.read_text().splitlines()
    assert lines[0] == "start" and lines[-1] == "stopped" and lines.count("start") == 1
    assert [line.split()[3] for line in lines if line.startswith("prompt")] == ["audio=voiceover-00.wav", "audio=voiceover-01.wav"]
