"""The GPU and the programs on it: listing them, and stopping and starting them (ADR 0003)."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GpuError(Exception):
    """The GPU or a program on it could not be read, stopped or started."""


@dataclass(frozen=True)
class GpuProgram:
    """All the processes of one program that hold GPU compute memory."""

    name: str
    used_mib: int
    pids: tuple[int, ...]
    service: str | None  # the systemd unit it runs as, if it is a system service

    @property
    def key(self) -> str:
        """What saved answers are filed under."""
        return self.service or self.name


class GpuControl(Protocol):
    def programs(self) -> list[GpuProgram]: ...

    def free_mib(self) -> int: ...

    def stop(self, program: GpuProgram) -> None: ...

    def start(self, unit: str) -> None: ...


STOP_WAIT_S = 20.0


class SystemGpu:
    """The real GPU: nvidia-smi to look, sudo systemctl for services, SIGTERM for other programs."""

    def __init__(self, cgroups: Path = Path("/proc")) -> None:
        self.cgroups = cgroups  # where <pid>/cgroup is read from

    def programs(self) -> list[GpuProgram]:
        rows = _run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"])
        grouped: dict[str, GpuProgram] = {}
        for line in rows.splitlines():
            pid, name, mib = (field.strip() for field in line.split(",", 2))
            unit = self._service_of(int(pid))
            program = GpuProgram(Path(name).name, int(mib), (int(pid),), unit)
            before = grouped.get(program.key)
            if before:
                program = GpuProgram(before.name, before.used_mib + program.used_mib, before.pids + program.pids, unit)
            grouped[program.key] = program
        return list(grouped.values())

    def free_mib(self) -> int:
        return int(_run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"]).split()[0])

    def stop(self, program: GpuProgram) -> None:
        if program.service:
            _run(["sudo", "-n", "systemctl", "stop", program.service])
            return
        for pid in program.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + STOP_WAIT_S
        while any(self._alive(pid) for pid in program.pids):
            if time.monotonic() > deadline:
                raise GpuError(f"{program.name} did not exit within {STOP_WAIT_S:.0f} s of being asked to stop")
            time.sleep(0.2)

    def start(self, unit: str) -> None:
        _run(["sudo", "-n", "systemctl", "start", unit])

    def _service_of(self, pid: int) -> str | None:
        try:
            cgroup = (self.cgroups / str(pid) / "cgroup").read_text()
        except OSError:
            return None
        path = cgroup.strip().splitlines()[-1].split(":", 2)[-1]
        if "/user@" in path:
            return None  # a user service needs systemctl --user, so it is treated as a plain program
        units = [part for part in path.split("/") if part.endswith(".service")]
        return units[-1] if units else None

    def _alive(self, pid: int) -> bool:
        try:
            state = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            return False
        return state != "Z"  # a zombie has already exited


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise GpuError(f"{command[0]} was not found") from None
    except subprocess.CalledProcessError as error:
        raise GpuError(f"`{' '.join(command)}` failed: {error.stderr.strip() or error.returncode}") from None
    return result.stdout
