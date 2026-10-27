"""Stands in for ComfyUI's main.py: same command line and HTTP API, no model. FAKE_COMFY_MODE picks how it behaves.

Each finished prompt writes a 480x832, 25 fps grey clip of its frame count plus half a second, as InfiniteTalk rounds
up to whole windows, and its history entry has the shape real ComfyUI gives, with VideoHelperSuite's "gifs" output.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

parser = argparse.ArgumentParser()
for flag in ("--listen", "--port", "--models-directory", "--input-directory", "--output-directory",
             "--temp-directory", "--user-directory"):
    parser.add_argument(flag, required=True)
parser.add_argument("--disable-auto-launch", action="store_true")
args = parser.parse_args()
mode = os.environ["FAKE_COMFY_MODE"]


def log(line: str) -> None:
    with open(os.environ["FAKE_COMFY_LOG"], "a") as f:
        f.write(line + "\n")


def stopped(*_: object) -> None:
    log("stopped")
    sys.exit(0)


signal.signal(signal.SIGTERM, stopped)
log("start")
if mode == "crash":
    sys.exit(3)
history: dict[str, Any] = {}


def node(graph: dict[str, Any], class_type: str) -> dict[str, Any]:
    inputs: dict[str, Any] = next(n["inputs"] for n in graph.values() if n["class_type"] == class_type)
    return inputs


def run(graph: dict[str, Any]) -> dict[str, Any]:
    inputs = Path(args.input_directory)
    image, audio = node(graph, "LoadImage")["image"], node(graph, "LoadAudio")["audio"]
    frames = node(graph, "MultiTalkWav2VecEmbeds")["num_frames"]
    sampler = node(graph, "WanVideoImageToVideoMultiTalk")
    size = f"{sampler['width']}x{sampler['height']}"
    log(f"prompt image={image} exists={(inputs / image).is_file()} audio={audio} exists={(inputs / audio).is_file()} frames={frames} size={size}")
    if mode == "fails":
        error = {"node_id": "sampler", "node_type": "WanVideoSampler", "exception_type": "torch.OutOfMemoryError",
                 "exception_message": "Allocation on device", "traceback": [], "executed": []}
        return {"outputs": {}, "status": {"status_str": "error", "completed": False,
                                           "messages": [["execution_start", {}], ["execution_error", error]]}}
    name = f"{node(graph, 'VHS_VideoCombine')['filename_prefix']}_00001.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={size}:r=25:d={frames / 25 + 0.5}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(Path(args.output_directory) / name)],
        check=True, stdin=subprocess.DEVNULL,
    )
    clip = {"filename": name, "subfolder": "", "type": "output", "format": "video/h264-mp4"}
    return {"outputs": {"face_clip": {"gifs": [clip]}},
            "status": {"status_str": "success", "completed": True, "messages": [["execution_success", {}]]}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/system_stats":
            return self.send({"system": {}})
        prompt_id = self.path.removeprefix("/history/")
        return self.send({prompt_id: history[prompt_id]} if prompt_id in history else {})

    def do_POST(self) -> None:
        graph = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["prompt"]
        if mode == "invalid":
            errors = {"text_embeds": {"class_type": "WanVideoTextEncodeCached", "dependent_outputs": ["face_clip"], "errors": [
                {"type": "value_not_in_list", "message": "Value not in list",
                 "details": "model_name: 'umt5.safetensors' not in []"}]}}
            return self.send({"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                              "node_errors": errors}, status=400)
        if mode == "hangs":  # takes the prompt and never writes its history entry, like a hung render
            return self.send({"prompt_id": "p1", "number": 0, "node_errors": {}})
        history["p1"] = run(graph)
        return self.send({"prompt_id": "p1", "number": 0, "node_errors": {}})

    def send(self, body: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_: object) -> None:
        pass


ThreadingHTTPServer((args.listen, int(args.port)), Handler).serve_forever()
