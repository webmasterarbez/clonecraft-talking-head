"""Stands in for scripts/voxcpm_worker.py: same protocol, no model. argv[1] picks how it behaves."""

import json
import os
import sys
import wave

import numpy as np

mode = sys.argv[1]
with open(os.environ["FAKE_WORKER_LOG"], "a") as log:
    log.write("start\n")


def reply(**fields: object) -> None:
    print(json.dumps(fields), flush=True)


if mode == "no-gpu":
    reply(error="gpu_memory", detail="needs about 8.5 GB, 3.0 GB free")
    sys.exit(0)
if mode == "crash":
    sys.exit(3)
reply(ready=True, sample_rate=48_000)
said: dict[str, str] = {}
for line in sys.stdin:
    request = json.loads(line)
    if "transcribe" in request:
        with open(os.environ["FAKE_WORKER_LOG"], "a") as log:
            log.write(f"hear {os.path.basename(request['transcribe'])}\n")
        # a take is heard exactly; a whole Voiceover is every take's words; both spread over one second
        text = said.get(request["transcribe"], " ".join(said.values()))
        words = text.split()
        timed = [{"text": w, "start": i / len(words), "end": (i + 1) / len(words)} for i, w in enumerate(words)]
        reply(ok=True, text=text, words=timed)
        continue
    if mode == "fails":
        reply(error="failed", detail="RuntimeError: the model gave up")
        continue
    with open(os.environ["FAKE_WORKER_LOG"], "a") as log:
        log.write(f"say style={request['style']} text={request['text']} reference={request['reference']} transcript={request['transcript']}\n")
    t = np.arange(48_000) / 48_000
    tone = (np.cos(2 * np.pi * 220 * t) * 0.5 * 32767).astype(np.int16)
    with wave.open(request["out"], "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48_000)
        out.writeframes(tone.tobytes())
    said[request["out"]] = request["text"]
    reply(ok=True)
