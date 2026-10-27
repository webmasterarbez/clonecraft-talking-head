"""Speaks text with VoxCPM2 and hears it back with faster-whisper for CloneCraft. Runs inside vendor/voice-env.

Protocol: one JSON object per line. On start it prints {"ready": true, "sample_rate": N} (or an error),
then for each request {"text", "style", "reference", "transcript", "out"} it writes a 16-bit mono WAV to "out" and
prints {"ok": true}, and for each {"transcribe": path} it prints {"ok": true, "text": ..., "words": [{"text", "start",
"end"}]}. Errors are {"error": "gpu_memory" | "failed", "detail": "..."}.
"""

import json
import os
import sys
import wave

NEEDED_GIB = 8.5  # measured 2026-10-26: VoxCPM2 plus the GPU faster-whisper peak at about 7.4 GB (ADR 0005)

reply_stream = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)  # anything the libraries print goes to stderr, so stdout carries only replies


def reply(**fields: object) -> None:
    reply_stream.write(json.dumps(fields) + "\n")
    reply_stream.flush()


def main(snapshot: str, whisper_snapshot: str) -> None:
    import numpy as np
    import torch

    free_gib = torch.cuda.mem_get_info()[0] / 2**30
    if free_gib < NEEDED_GIB:
        reply(error="gpu_memory", detail=f"needs about {NEEDED_GIB:.1f} GB, {free_gib:.1f} GB free")
        return
    from voxcpm import VoxCPM

    model = VoxCPM(voxcpm_model_path=snapshot, enable_denoiser=False, optimize=False)
    rate = int(model.tts_model.sample_rate)
    reply(ready=True, sample_rate=rate)
    whisper = None
    for line in sys.stdin:
        request = json.loads(line)
        if "transcribe" in request:
            try:
                if whisper is None:
                    from faster_whisper import WhisperModel

                    whisper = WhisperModel(whisper_snapshot, device="cuda", compute_type="int8")  # GPU, not CPU (ADR 0005)
                segments, _ = whisper.transcribe(request["transcribe"], word_timestamps=True)
                texts, words = [], []
                for segment in segments:
                    texts.append(segment.text)
                    words += [{"text": w.word.strip(), "start": w.start, "end": w.end} for w in segment.words or []]
                reply(ok=True, text=" ".join(texts).strip(), words=[w for w in words if w["text"]])
            except Exception as error:  # noqa: BLE001 - reported to the caller
                reply(error="failed", detail=f"{type(error).__name__}: {error}")
            continue
        text = f"({request['style']}){request['text']}" if request["style"] else request["text"]
        try:
            # With the reference's transcript this is "ultimate cloning" (the approved voice, ADR 0004), which
            # ignores the style prefix. Without one it is "controllable cloning" from the audio alone.
            options = {
                "reference_wav_path": request["reference"], "cfg_value": 2.0,
                "denoise": False,  # VoxCPM's default 10 diffusion steps, as the approved look used (ADR 0005)
            }
            if request["transcript"]:
                options.update(prompt_wav_path=request["reference"], prompt_text=request["transcript"])
            wav = model.generate(text=text, **options)
            pcm = (np.clip(np.asarray(wav, dtype=np.float64), -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(request["out"], "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(pcm.tobytes())
            reply(ok=True)
        except torch.cuda.OutOfMemoryError as error:
            reply(error="gpu_memory", detail=str(error).splitlines()[0])
        except Exception as error:  # noqa: BLE001 - reported to the caller, which names the piece
            reply(error="failed", detail=f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
