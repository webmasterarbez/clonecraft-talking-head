from pathlib import Path

import pytest
import yaml

from clonecraft.cli import main
from clonecraft.face import FaceEngineError
from tests.support import (
    Answers,
    FakeFaceEngine,
    FakeGpu,
    FakeVoiceEngine,
    Project,
    plain_program,
    service,
    write_banded_likeness,
)

LLAMA = "llama-server@11434.service"
COMFY = "comfyui.service"


@pytest.fixture
def ready(project: Project) -> Project:
    write_banded_likeness(project.likeness)
    project.write_voiceover("script-01", seconds=1.0)
    return project


def run_video(project: Project, gpu: FakeGpu, ask: Answers, engine: FakeFaceEngine | None = None) -> int:
    engine = engine or FakeFaceEngine(log=gpu.events)
    return main(["video", project.channel_ref, "script-01"], root=project.root, face_engine=engine, gpu=gpu, ask=ask)


def llama_gpu(mib: int = 8_000) -> FakeGpu:
    return FakeGpu([service(LLAMA, mib)])


def settings_file(project: Project) -> Path:
    return project.root / "settings.local.yaml"


def test_a_stopped_service_is_started_again_after_the_video_and_not_before(ready: Project) -> None:
    gpu = llama_gpu()

    assert run_video(ready, gpu, Answers("y", "y")) == 0

    assert gpu.events == [f"stop {LLAMA}", "render", f"start {LLAMA}"]
    assert ready.video("script-01").exists()


def test_only_programs_of_100_mib_or_more_are_asked_about(ready: Project) -> None:
    gpu = FakeGpu([service(LLAMA, 8_000), plain_program("tiny", 99), plain_program("edge", 100, pid=300)])
    ask = Answers("y", "y", "n")  # llama: stop, restart; edge: don't stop

    run_video(ready, gpu, ask)

    assert len(ask.prompts) == 3
    assert "llama-server" in ask.prompts[0] and "edge" in ask.prompts[2]
    assert not any("tiny" in prompt for prompt in ask.prompts)
    assert "stop tiny" not in gpu.events


def test_a_declined_stop_is_not_requested(ready: Project) -> None:
    gpu = FakeGpu([service(LLAMA, 3_000), plain_program("comfy", 500)])

    assert run_video(ready, gpu, Answers("y", "y", "n")) == 0

    assert gpu.events == [f"stop {LLAMA}", "render", f"start {LLAMA}"]


def test_answers_are_saved_and_a_known_program_is_not_asked_about_again(ready: Project) -> None:
    run_video(ready, llama_gpu(), Answers("y", "y"))
    ready.write_voiceover("script-01", seconds=2.0)  # a new Voiceover, so the face is rendered again
    ask = Answers()  # nothing to say: asking would fail the test
    gpu = llama_gpu()

    assert run_video(ready, gpu, ask) == 0

    assert ask.prompts == []
    assert gpu.events == [f"stop {LLAMA}", "render", f"start {LLAMA}"]
    assert yaml.safe_load(settings_file(ready).read_text()) == {"gpu": {LLAMA: {"stop": True, "restart": True}}}


def test_a_saved_no_is_kept_and_a_new_program_is_asked_about(ready: Project) -> None:
    settings_file(ready).write_text(yaml.safe_dump({"gpu": {COMFY: {"stop": False, "restart": False}}}))
    gpu = FakeGpu([service(COMFY, 500), service(LLAMA, 3_000)])
    ask = Answers("y", "n")

    assert run_video(ready, gpu, ask) == 0

    assert len(ask.prompts) == 2 and all("llama-server" in prompt for prompt in ask.prompts)
    assert gpu.events == [f"stop {LLAMA}", "render"]  # asked to stop llama and told not to restart it


@pytest.mark.parametrize(
    "engine",
    [FakeFaceEngine(), FakeFaceEngine(raises=FaceEngineError("the render broke")), FakeFaceEngine(raises=KeyboardInterrupt())],
    ids=["success", "failure", "Ctrl-C"],
)
def test_the_service_is_started_again_however_the_video_step_ends(ready: Project, engine: FakeFaceEngine) -> None:
    gpu = llama_gpu()
    engine.log = gpu.events

    code = run_video(ready, gpu, Answers("y", "y"), engine)

    assert (code == 0) == (engine.raises is None)
    assert gpu.events == [f"stop {LLAMA}", "render", f"start {LLAMA}"]


def test_a_program_that_is_not_a_service_is_only_offered_a_stop_with_a_note(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = FakeGpu([plain_program("comfy", 8_000)])
    ask = Answers("y")

    assert run_video(ready, gpu, ask) == 0

    assert len(ask.prompts) == 1
    assert "start it again yourself" in capsys.readouterr().out
    assert gpu.events == ["stop comfy", "render"]
    assert yaml.safe_load(settings_file(ready).read_text()) == {"gpu": {"comfy": {"stop": True, "restart": False}}}


def test_memory_still_short_names_what_holds_it_and_still_starts_stopped_services_again(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = FakeGpu([service(LLAMA, 2_000), service(COMFY, 6_000)])  # 12000 - 1200 - 6000 = 4800 MiB free once llama is gone

    assert run_video(ready, gpu, Answers("y", "y", "n")) != 0

    err = capsys.readouterr().err
    assert "comfyui" in err and "6000 MiB" in err and "10000 MiB" in err
    assert gpu.events == [f"stop {LLAMA}", f"start {LLAMA}"]  # no render
    assert not ready.video("script-01").exists()


def test_when_nothing_listed_holds_the_memory_the_message_says_so(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = FakeGpu([], desktop_mib=5_000)

    assert run_video(ready, gpu, Answers()) != 0

    assert "desktop" in capsys.readouterr().err


def test_a_service_that_will_not_start_again_is_reported_by_name_even_though_the_video_was_made(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = llama_gpu()
    gpu.cannot_start.add(LLAMA)

    assert run_video(ready, gpu, Answers("y", "y")) != 0

    assert LLAMA in capsys.readouterr().err
    assert ready.video("script-01").exists()


def test_a_stop_that_fails_still_starts_the_service_again_and_makes_no_video(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = llama_gpu()
    gpu.cannot_stop.add(LLAMA)

    assert run_video(ready, gpu, Answers("y", "y")) != 0

    assert gpu.events == [f"stop {LLAMA}", f"start {LLAMA}"]
    assert LLAMA in capsys.readouterr().err
    assert not ready.video("script-01").exists()


def test_bad_inputs_stop_the_video_before_anything_is_asked_or_stopped(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = llama_gpu()  # no Voiceover has been made

    assert run_video(project, gpu, Answers()) != 0

    assert gpu.events == []
    assert "Voiceover" in capsys.readouterr().err


def test_an_answer_that_is_not_yes_or_no_is_asked_again(ready: Project) -> None:
    gpu = llama_gpu()
    ask = Answers("maybe", "y", "y")

    assert run_video(ready, gpu, ask) == 0

    assert len(ask.prompts) == 3


def test_no_answer_at_the_prompt_stops_before_anything_is_stopped(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    gpu = llama_gpu()

    def gives_up(prompt: str) -> str:
        raise EOFError

    code = main(
        ["video", ready.channel_ref, "script-01"], root=ready.root, face_engine=FakeFaceEngine(), gpu=gpu, ask=gives_up
    )

    assert code != 0 and gpu.events == []
    assert not settings_file(ready).exists()


def run_voiceover(project: Project, gpu: FakeGpu, ask: Answers) -> int:
    return main(["voiceover", project.channel_ref, "script-01"], root=project.root, voice_engine=FakeVoiceEngine(), gpu=gpu, ask=ask)


def test_the_voiceover_step_asks_for_nothing_when_enough_memory_is_free(project: Project) -> None:
    gpu = FakeGpu([service(LLAMA, 2_000)])  # 12000 - 1200 - 2000 = 8800 MiB free
    ask = Answers()

    assert run_voiceover(project, gpu, ask) == 0

    assert gpu.events == [] and ask.prompts == []


def test_the_voiceover_step_lists_big_programs_and_stops_the_agreed_ones_when_memory_is_short(project: Project) -> None:
    gpu = FakeGpu([service(LLAMA, 8_000), plain_program("comfy", 500)])  # 2300 MiB free
    ask = Answers("y", "y", "n")  # llama: stop, restart; comfy: don't stop

    assert run_voiceover(project, gpu, ask) == 0

    assert len(ask.prompts) == 3 and "Voiceover" in ask.prompts[0]
    assert gpu.events == [f"stop {LLAMA}", f"start {LLAMA}"]
    assert project.voiceover("script-01").exists()


def test_the_voiceover_step_names_what_still_holds_the_memory(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    gpu = FakeGpu([service(COMFY, 6_000)])

    assert run_voiceover(project, gpu, Answers("n")) != 0

    err = capsys.readouterr().err
    assert "comfyui" in err and "Voiceover needs about 8704 MiB" in err
    assert gpu.events == [] and not project.voiceover("script-01").exists()
