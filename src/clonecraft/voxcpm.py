"""The real voice engine: VoxCPM2 running in its own environment, spoken to through a worker process."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
from pathlib import Path
from typing import IO, Any, NoReturn

from .voice import Heard, NotEnoughGpuMemory, VoiceEngineError, Word

INSTALL_HINT = "run `sh scripts/install-voice-engine.sh`, then `uv run clonecraft models --fix`"
PYTHON = Path("vendor/voice-env/bin/python")
WORKER = Path("scripts/voxcpm_worker.py")
VOXCPM_SNAPSHOTS = Path("models/hf/hub/models--openbmb--VoxCPM2/snapshots")
WHISPER_SNAPSHOTS = Path("models/hf/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots")


def missing_parts(root: Path) -> list[str]:
    """The parts of the voice engine not yet in `root`, as paths relative to it."""
    files = [p for p in (PYTHON, WORKER) if not (root / p).is_file()]
    models = [p for p in (VOXCPM_SNAPSHOTS, WHISPER_SNAPSHOTS) if not any((root / p).glob("*"))]
    return [str(p) for p in files + models]


class VoxCpmEngine:
    """Starts the worker on first use, keeps the model loaded for every piece, and stops it at exit."""

    def __init__(self, python: Path, worker: Path, snapshot: Path, whisper: Path) -> None:
        self.command = [str(python), str(worker), str(snapshot), str(whisper)]
        self.process: subprocess.Popen[str] | None = None
        self.sample_rate = 0

    @classmethod
    def installed_in(cls, root: Path) -> VoxCpmEngine | None:
        if missing_parts(root):
            return None
        snapshot, whisper = (sorted((root / p).glob("*"))[0] for p in (VOXCPM_SNAPSHOTS, WHISPER_SNAPSHOTS))
        return cls(root / PYTHON, root / WORKER, snapshot, whisper)

    def synthesize(self, text: str, style: str | None, reference: Path, out: Path) -> None:
        transcript_file = reference.with_suffix(".txt")
        transcript = transcript_file.read_text().strip() if transcript_file.is_file() else None
        # With a transcript the engine reads a style prefix aloud instead of obeying it (ADR 0004), so send none.
        request = {
            "text": text, "style": None if transcript else style,
            "reference": str(reference), "transcript": transcript or None, "out": str(out),
        }
        self._ask(request)

    def transcribe(self, audio: Path) -> Heard:
        reply = self._ask({"transcribe": str(audio)})
        return Heard(reply["text"], [Word(w["text"], float(w["start"]), float(w["end"])) for w in reply["words"]])

    def _ask(self, request: dict[str, Any]) -> dict[str, Any]:
        process = self._started()
        assert process.stdin is not None
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
        except BrokenPipeError:
            pass  # the reply below reports why the worker is gone
        reply = self._read_reply(process)
        if reply.get("ok"):
            return reply
        self.close()
        _raise(reply)

    def close(self) -> None:
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=30)

    def _started(self) -> subprocess.Popen[str]:
        if self.process and self.process.poll() is None:
            return self.process
        self.process = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, text=True,
            env={**os.environ, "TQDM_DISABLE": "1"},  # no progress bars in the Operator's terminal
        )
        atexit.register(self.close)
        reply = self._read_reply(self.process)
        if not reply.get("ready"):
            self.close()
            _raise(reply)
        self.sample_rate = int(reply["sample_rate"])
        return self.process

    def _read_reply(self, process: subprocess.Popen[str]) -> dict[str, Any]:
        stdout: IO[str] = process.stdout  # type: ignore[assignment]
        line = stdout.readline()
        if not line:
            process.wait()
            raise VoiceEngineError(f"the voice engine stopped unexpectedly (exit code {process.returncode}); see its output above")
        reply: dict[str, Any] = json.loads(line)
        return reply


def _raise(reply: dict[str, Any]) -> NoReturn:
    detail = str(reply.get("detail", "no detail"))
    if reply.get("error") == "gpu_memory":
        raise NotEnoughGpuMemory(detail)
    raise VoiceEngineError(f"the voice engine failed: {detail}")


