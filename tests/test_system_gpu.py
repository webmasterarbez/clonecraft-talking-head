"""The real GPU control, run against stand-in nvidia-smi and sudo programs on the PATH."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from clonecraft.cli import main
from clonecraft.gpu import SystemGpu
from tests.support import Answers, FakeFaceEngine, Project, write_banded_likeness

NVIDIA_SMI = """#!/bin/sh
case "$*" in
  *compute-apps*) cat "$STUB_DIR/apps.csv" ;;
  *memory.free*) echo 11000 ;;
  *) exit 1 ;;
esac
"""
SUDO = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$STUB_DIR/sudo.log"\n'


@pytest.fixture
def stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "stubs"
    folder.mkdir()
    for name, body in (("nvidia-smi", NVIDIA_SMI), ("sudo", SUDO)):
        (folder / name).write_text(body)
        (folder / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_DIR", str(folder))
    return folder


@pytest.fixture
def ready(project: Project) -> Project:
    write_banded_likeness(project.likeness)
    project.write_voiceover("script-01", seconds=1.0)
    return project


def cgroup_of(folder: Path, pid: int, path: str) -> None:
    (folder / str(pid)).mkdir(parents=True, exist_ok=True)
    (folder / str(pid) / "cgroup").write_text(f"0::{path}\n")


def run_video(project: Project, gpu: SystemGpu, ask: Answers) -> int:
    return main(["video", project.channel_ref, "script-01"], root=project.root, face_engine=FakeFaceEngine(), gpu=gpu, ask=ask)


def test_a_system_service_is_found_in_the_process_list_and_stopped_and_started_with_sudo(
    ready: Project, stubs: Path
) -> None:
    unit = "llama-server@11434.service"
    (stubs / "apps.csv").write_text(
        "4242, /opt/llama.cpp/bin/llama-server, 6000\n4243, /opt/llama.cpp/bin/llama-server, 2000\n"
    )
    groups = stubs / "cgroups"
    for pid in (4242, 4243):
        cgroup_of(groups, pid, f"/system.slice/system-llama\\x2dserver.slice/{unit}")
    ask = Answers("y", "y")

    assert run_video(ready, SystemGpu(groups), ask) == 0

    assert len(ask.prompts) == 2 and "8000 MiB" in ask.prompts[0]  # both processes are one program
    assert (stubs / "sudo.log").read_text().splitlines() == [f"-n systemctl stop {unit}", f"-n systemctl start {unit}"]


def test_a_program_that_is_not_a_service_is_ended_and_not_started(ready: Project, stubs: Path) -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL)
    try:
        (stubs / "apps.csv").write_text(f"{child.pid}, /usr/bin/python3, 7000\n")
        groups = stubs / "cgroups"
        cgroup_of(groups, child.pid, "/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-terminal.scope")

        assert run_video(ready, SystemGpu(groups), Answers("y")) == 0

        assert child.wait(timeout=5) != 0  # ended by the stop request
        assert not (stubs / "sudo.log").exists()
    finally:
        child.kill()
        child.wait()


def test_without_nvidia_smi_the_video_says_so(ready: Project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PATH", str(ready.root))  # nothing on it

    assert run_video(ready, SystemGpu(), Answers()) != 0

    assert "nvidia-smi was not found" in capsys.readouterr().err
