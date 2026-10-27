"""The real face engine: InfiniteTalk run by ComfyUI in its own environment, driven through ComfyUI's HTTP API."""

from __future__ import annotations

import json
import math
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import audio
from .face import FACE_FPS, FaceEngineError

INSTALL_HINT = "run `sh scripts/install-face-engine.sh`, then `uv run clonecraft models --fix`"
PYTHON = Path("vendor/face-env/bin/python")
COMFY = Path("vendor/ComfyUI/main.py")
MODELS = Path("models/comfy")
GRAPH = Path("config/infinitetalk-graph.json")  # the recorded InfiniteTalk graph and settings, in ComfyUI's API format
START_TIMEOUT_S = 300.0
POLL_S = 1.0
JOB_TIMEOUT_S = 3600.0  # generous ceiling for one Face section: a full-length Video's face engine took about 68 minutes for all of its sections


def missing_parts(root: Path) -> list[str]:
    """The parts of the face engine not yet in `root`, as paths relative to it."""
    files = [p for p in (PYTHON, COMFY, GRAPH) if not (root / p).is_file()]
    models = [MODELS] if not any((root / MODELS).glob("*")) else []
    return [str(p) for p in files + models]


class InfiniteTalkEngine:
    """Starts ComfyUI once for all the clips of a render, sends it the graph for each, and stops it again."""

    def __init__(self, python: Path, comfy: Path, models: Path, graph: Path) -> None:
        self.python, self.comfy, self.models, self.graph = python, comfy, models, graph

    @classmethod
    def installed_in(cls, root: Path) -> InfiniteTalkEngine | None:
        if missing_parts(root):
            return None
        return cls(root / PYTHON, root / COMFY, root / MODELS, root / GRAPH)

    def render(self, portrait: Path, jobs: list[tuple[Path, Path]]) -> None:
        width, height = _size(portrait)
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            folders = {name: work / name for name in ("input", "output", "temp", "user")}
            for folder in folders.values():
                folder.mkdir()
            shutil.copy(portrait, folders["input"] / "portrait.png")
            graphs = []
            for n, (voiceover, _) in enumerate(jobs):
                name = f"voiceover-{n:02d}.wav"
                shutil.copy(voiceover, folders["input"] / name)
                rate, samples = audio.read_wav(voiceover)
                graph: dict[str, Any] = json.loads(self.graph.read_text())
                _inputs(graph, "LoadImage")["image"] = "portrait.png"
                _inputs(graph, "LoadAudio")["audio"] = name
                _inputs(graph, "MultiTalkWav2VecEmbeds")["num_frames"] = math.ceil(len(samples) / rate * FACE_FPS)
                _inputs(graph, "WanVideoImageToVideoMultiTalk").update(width=width, height=height)
                graphs.append((graph, name))
            port = _free_port()
            server = subprocess.Popen(
                [str(self.python), str(self.comfy), "--listen", "127.0.0.1", "--port", str(port),
                 "--models-directory", str(self.models.resolve()), "--disable-auto-launch",
                 *(arg for name, folder in folders.items() for arg in (f"--{name}-directory", str(folder)))],
                stdin=subprocess.DEVNULL,
            )
            try:
                comfy = _Comfy(server, f"http://127.0.0.1:{port}")
                comfy.wait_until_up()
                for (graph, name), (_, out) in zip(graphs, jobs):
                    clip = comfy.run(graph, name)
                    shutil.copy(folders["output"] / clip["subfolder"] / clip["filename"], out)
            finally:
                _stop(server)


class _Comfy:
    def __init__(self, server: subprocess.Popen[bytes], url: str) -> None:
        self.server, self.url = server, url

    def wait_until_up(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT_S
        while True:
            try:
                self._get("/system_stats")
                return
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    raise FaceEngineError(f"ComfyUI did not answer within {START_TIMEOUT_S:.0f} s of starting") from None
                time.sleep(0.2)

    def run(self, graph: dict[str, Any], label: str) -> dict[str, str]:
        """Queue the graph, wait for it to finish, and return the face clip's output entry."""
        prompt_id = str(self._post("/prompt", {"prompt": graph})["prompt_id"])
        deadline = time.monotonic() + JOB_TIMEOUT_S
        while not (entry := self._get(f"/history/{prompt_id}").get(prompt_id)):
            if time.monotonic() > deadline:
                raise FaceEngineError(f"ComfyUI did not finish {label} within {JOB_TIMEOUT_S:.0f} s; see its output above")
            time.sleep(POLL_S)
        status = entry.get("status") or {}
        if status.get("status_str") != "success":
            raise FaceEngineError(f"ComfyUI could not render the face: {_execution_error(status)}")
        clips: list[dict[str, str]] = [c for o in entry["outputs"].values() for c in o.get("gifs", [])]
        if not clips:
            raise FaceEngineError("ComfyUI finished but wrote no face clip")
        return clips[0]

    def _get(self, path: str) -> dict[str, Any]:
        return self._ask(urllib.request.Request(self.url + path))

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            return self._ask(request)
        except urllib.error.HTTPError as error:
            raise FaceEngineError(f"ComfyUI refused the graph: {_validation_errors(error)}") from None

    def _ask(self, request: urllib.request.Request) -> dict[str, Any]:
        if self.server.poll() is not None:
            raise FaceEngineError(f"ComfyUI stopped unexpectedly (exit code {self.server.returncode}); see its output above")
        with urllib.request.urlopen(request, timeout=60) as response:
            reply: dict[str, Any] = json.load(response)
        return reply


def _size(image: Path) -> tuple[int, int]:
    shown = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(image)],
        check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    width, height = shown.stdout.strip().split("x")
    return int(width), int(height)


def _inputs(graph: dict[str, Any], class_type: str) -> dict[str, Any]:
    found: dict[str, Any] = next(node["inputs"] for node in graph.values() if node["class_type"] == class_type)
    return found


def _validation_errors(error: urllib.error.HTTPError) -> str:
    try:
        body = json.load(error)
    except ValueError:
        return f"HTTP {error.code}"
    problems = [
        f"{node_id} ({node.get('class_type')}): {e.get('message')}, {e.get('details')}"
        for node_id, node in (body.get("node_errors") or {}).items()
        for e in node.get("errors", [])
    ]
    return "; ".join(problems) or str((body.get("error") or {}).get("message", f"HTTP {error.code}"))


def _execution_error(status: dict[str, Any]) -> str:
    for event, data in status.get("messages", []):
        if event == "execution_error":
            return f"{data.get('node_id')} ({data.get('node_type')}) failed with {data.get('exception_type')}: {data.get('exception_message', '').strip()}"
        if event == "execution_interrupted":
            return f"it was interrupted at {data.get('node_id')} ({data.get('node_type')})"
    return "no reason was given"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _stop(server: subprocess.Popen[bytes]) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
