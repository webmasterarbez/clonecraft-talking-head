"""Assembling spoken pieces into one Voiceover."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

from .voice import VoiceEngineError

Samples = npt.NDArray[np.int16]

# The approved look's join (ADR 0005): take edges quieter than EDGE_DB are cut, pauses inside a take quieter than
# PAUSE_DB are shortened to JOIN_PAUSE_S, and takes are joined so each join lasts JOIN_PAUSE_S.
EDGE_DB = -45.0
PAUSE_DB = -50.0
EDGE_PAD_S = 0.03
JOIN_PAUSE_S = 0.4
FADE_S = 0.01
# The transcriber ends a last word before its sound does, so a trailing cut runs on to the first stretch
# this long below EDGE_DB.
SPEECH_GAP_S = 0.1


def read_wav(path: Path) -> tuple[int, Samples]:
    with wave.open(str(path), "rb") as f:
        return f.getframerate(), np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)


def write_wav(path: Path, samples: Samples, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.tobytes())


def seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as f:
        return f.getnframes() / f.getframerate()


def trim_after(take: Path, start: float, out: Path) -> Path:
    """Write `take` to `out` cut where the first SPEECH_GAP_S of quiet at or after `start` seconds begins."""
    rate, samples = read_wav(take)
    need = int(SPEECH_GAP_S * rate)
    quiet = (np.abs(samples[int(start * rate) :].astype(np.float64)) <= 32768 * 10 ** (EDGE_DB / 20)).astype(np.int64)
    runs = np.flatnonzero(np.convolve(quiet, np.ones(need, dtype=np.int64), "valid") == need)
    end = int(start * rate) + int(runs[0]) if runs.size else len(samples)
    write_wav(out, samples[:end], rate)
    return out


def _fade(speech: Samples, rate: int) -> Samples:
    n = min(int(FADE_S * rate), len(speech) // 2)
    ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(n) / n))
    faded = speech.astype(np.float64)
    faded[:n] *= ramp
    faded[len(faded) - n :] *= ramp[::-1]
    return faded.astype(np.int16)


def _cap_pauses(speech: Samples, rate: int) -> Samples:
    """Shorten every quiet stretch longer than the join pause to the join pause, cutting its middle."""
    cap = int(JOIN_PAUSE_S * rate)
    quiet = np.abs(speech.astype(np.float64)) <= 32768 * 10 ** (PAUSE_DB / 20)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], quiet.astype(np.int8), [0]])))
    keep = np.ones(len(speech), dtype=bool)
    for start, end in zip(edges[::2], edges[1::2], strict=True):
        if end - start > cap:
            keep[start + cap // 2 : end - (cap - cap // 2)] = False
    return speech[keep]


def _trim(samples: Samples, rate: int) -> Samples:
    loud = np.flatnonzero(np.abs(samples.astype(np.float64)) > 32768 * 10 ** (EDGE_DB / 20))
    if loud.size == 0:
        return samples[:0]
    pad = np.zeros(int(EDGE_PAD_S * rate), dtype=np.int16)
    return np.concatenate([pad, _fade(_cap_pauses(samples[loud[0] : loud[-1] + 1], rate), rate), pad])


def assemble(pieces: list[Path], out: Path) -> float:
    """Join the pieces into one WAV at `out` and return its duration in seconds."""
    rate = 0
    parts: list[Samples] = []
    for piece in pieces:
        piece_rate, samples = read_wav(piece)
        if rate and piece_rate != rate:
            raise VoiceEngineError(f"the voice engine wrote pieces at different sample rates ({rate} and {piece_rate} Hz)")
        rate = piece_rate
        parts.append(_trim(samples, rate))
    gap = np.zeros(int((JOIN_PAUSE_S - 2 * EDGE_PAD_S) * rate), dtype=np.int16)
    joined = np.concatenate([part for i, p in enumerate(parts) for part in ((gap, p) if i else (p,))])
    write_wav(out, joined, rate)
    return len(joined) / rate
