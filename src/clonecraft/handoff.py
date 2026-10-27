"""Taking the GPU for a Voiceover or Video: ask about each big program, stop what the Operator agreed to, give it back."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .gpu import GpuControl, GpuError, GpuProgram
from .project import ProjectError

SETTINGS_FILE = "settings.local.yaml"  # git-ignored
MIN_PROGRAM_MIB = 100
NEEDED_MIB = 10_000
VOICEOVER_NEEDED_MIB = 8_704  # 8.5 GiB: VoxCPM2 plus the speech check's GPU faster-whisper, measured at about 7.4 GB (ADR 0005)


@dataclass
class Handoff:
    """What the step took, and what could not be given back."""

    to_restart: list[str] = field(default_factory=list)
    not_restarted: list[str] = field(default_factory=list)


def _load(path: Path) -> dict[str, dict[str, bool]]:
    if not path.is_file():
        return {}
    try:
        answers = (yaml.safe_load(path.read_text()) or {}).get("gpu", {})
        return {key: {"stop": bool(a["stop"]), "restart": bool(a["restart"])} for key, a in answers.items()}
    except (yaml.YAMLError, AttributeError, KeyError, TypeError) as error:
        raise ProjectError(f"{path} is not a valid settings file ({error}); fix it or delete it to be asked again") from None


def _save(path: Path, answers: dict[str, dict[str, bool]]) -> None:
    document: dict[str, Any] = {"gpu": answers}
    path.write_text(yaml.safe_dump(document, sort_keys=True))


def _yes_no(ask: Callable[[str], str], question: str) -> bool:
    while True:
        try:
            answer = ask(question).strip().lower()
        except EOFError:
            raise GpuError("no answer was given, so nothing was stopped") from None
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please type y or n.")


def _ask_about(program: GpuProgram, ask: Callable[[str], str], step: str) -> dict[str, bool]:
    kind = f"the system service {program.service}" if program.service else f"a program (process {program.pids[0]})"
    stop = _yes_no(ask, f"{program.name}, {kind}, holds {program.used_mib} MiB of GPU memory. Stop it for the {step}? (y/n) ")
    restart = False
    if stop and program.service:
        restart = _yes_no(ask, f"Start {program.service} again when the {step} step ends? (y/n) ")
    elif stop:
        print(f"{program.name} is not a service, so CloneCraft cannot start it again; start it again yourself afterwards.")
    return {"stop": stop, "restart": restart}


def _too_little_memory(gpu: GpuControl, free: int, needed: int, step: str) -> GpuError:
    holders = [p for p in gpu.programs() if p.used_mib >= MIN_PROGRAM_MIB]
    held = ", ".join(f"{p.name} ({p.used_mib} MiB)" for p in holders)
    where = (
        f"Still holding memory: {held}."
        if holders
        else "No program of 100 MiB or more is left, so the rest is held by the desktop or smaller programs."
    )
    return GpuError(f"only {free} MiB of GPU memory is free and the {step} needs about {needed} MiB. {where}")


@contextmanager
def cleared_gpu(
    gpu: GpuControl, root: Path, ask: Callable[[str], str], needed_mib: int = NEEDED_MIB, step: str = "Video"
) -> Iterator[Handoff]:
    """Free the GPU for the body, then start again every service the Operator asked to have restarted.

    Everything is asked before anything is stopped. A service that cannot be started again is named in
    `not_restarted` and on stderr; the body's own error, if any, is not hidden by it.
    """
    path = root / SETTINGS_FILE
    answers = _load(path)
    big = [p for p in gpu.programs() if p.used_mib >= MIN_PROGRAM_MIB]
    for program in big:
        if program.key not in answers:
            answers[program.key] = _ask_about(program, ask, step)
            _save(path, answers)
    handoff = Handoff()
    try:
        for program in big:
            if answers[program.key]["stop"]:
                if program.service and answers[program.key]["restart"]:
                    handoff.to_restart.append(program.service)  # before the stop, so a half-done stop is still undone
                print(f"Stopping {program.name} ({program.used_mib} MiB)")
                gpu.stop(program)
        free = gpu.free_mib()
        if free < needed_mib:
            raise _too_little_memory(gpu, free, needed_mib, step)
        yield handoff
    finally:
        for unit in reversed(handoff.to_restart):
            print(f"Starting {unit} again")
            try:
                gpu.start(unit)
            except GpuError as error:
                handoff.not_restarted.append(unit)
                print(f"clonecraft: {unit} was not started again: {error}", file=sys.stderr)
