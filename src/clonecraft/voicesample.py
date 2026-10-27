"""Choosing a Voice Reference: proposing 20-second stretches of a Voice Sample and saving the Operator's pick."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import audio
from .project import ProjectError, persona_dir

RATE = 48_000
WINDOW_S = 20
CANDIDATES = 3
FRAME_S = 0.05
FRAMES_PER_S = int(1 / FRAME_S)
SILENCE_FLOOR_DB = -50.0  # frames quieter than this are not speech when finding the typical loudness
GAP_BELOW_TYPICAL_DB = 20.0  # a frame this far under the typical loudness counts as quiet
MAX_GAP_S = 1.0
FULL_SCALE = 32_768.0
CLIP_LEVEL = 32_700
LOUDNESS_TOLERANCE_DB = 3.0


def find_voice_sample(directory: Path) -> Path | None:
    found = sorted(directory.glob("voice-sample.*"))
    return found[0] if found else None


def decode(path: Path) -> audio.Samples:
    """The recording as mono 16-bit samples at 48 kHz, whatever format it is in."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True, stdin=subprocess.DEVNULL,  # ffmpeg would read the Operator's typing
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


def _per_frame_power_and_per_second_clips(samples: audio.Samples) -> tuple[np.ndarray, np.ndarray]:
    seconds = len(samples) // RATE
    frame = int(FRAME_S * RATE)
    power = np.empty(seconds * FRAMES_PER_S)
    clips = np.empty(seconds, dtype=np.int64)
    for second in range(seconds):  # one second at a time keeps the float copies small
        chunk = samples[second * RATE : (second + 1) * RATE].astype(np.float64)
        power[second * FRAMES_PER_S : (second + 1) * FRAMES_PER_S] = (chunk.reshape(-1, frame) ** 2).mean(axis=1)
        clips[second] = int((np.abs(chunk) >= CLIP_LEVEL).sum())
    return power, clips


def _window_sums(values: np.ndarray, starts: int) -> np.ndarray:
    """The sum of each run of WINDOW_S consecutive per-second values, for every start."""
    total = np.concatenate([[0], np.cumsum(values)])
    window: np.ndarray = total[WINDOW_S : WINDOW_S + starts] - total[:starts]
    return window


def _gap_invalid(quiet: np.ndarray, starts: int) -> np.ndarray:
    """Starts whose window touches a quiet run longer than MAX_GAP_S."""
    window = WINDOW_S * FRAMES_PER_S
    invalid = np.zeros(starts, dtype=bool)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], quiet.astype(np.int8), [0]])))
    for run_start, run_end in zip(edges[::2], edges[1::2], strict=True):
        if run_end - run_start > MAX_GAP_S * FRAMES_PER_S:
            invalid[max(0, (run_start - window) // FRAMES_PER_S + 1) : min(starts, (run_end - 1) // FRAMES_PER_S + 1)] = True
    return invalid


def _loudness_invalid(db: np.ndarray, voiced: np.ndarray, typical: float, starts: int) -> np.ndarray:
    """Starts whose median voiced-frame loudness is more than LOUDNESS_TOLERANCE_DB from the typical one."""
    window = WINDOW_S * FRAMES_PER_S
    invalid = np.zeros(starts, dtype=bool)
    for start in range(starts):
        first = start * FRAMES_PER_S
        frames = db[first : first + window][voiced[first : first + window]]
        invalid[start] = frames.size == 0 or abs(float(np.median(frames)) - typical) > LOUDNESS_TOLERANCE_DB
    return invalid


def _steadiest_apart(steadiness: np.ndarray, invalid: np.ndarray) -> list[int]:
    chosen: list[int] = []
    # steadiest first; stretches within 0.1 dB of each other tie, and the earliest wins
    for start in np.lexsort((np.arange(len(steadiness)), np.round(steadiness, 1))):
        if invalid[start]:
            break
        if all(abs(int(start) - c) >= WINDOW_S for c in chosen):
            chosen.append(int(start))
        if len(chosen) == CANDIDATES:
            break
    return chosen


def propose(samples: audio.Samples) -> list[int]:
    """Start times, in whole seconds, of up to three non-overlapping 20 s stretches that make a good Voice Reference.

    A good stretch has no gap over a second, no clipping, and a loudness near the typical speech loudness
    of the whole recording. Steadier stretches win.
    """
    power, clips = _per_frame_power_and_per_second_clips(samples)
    seconds = len(clips)
    if seconds < WINDOW_S:
        return []
    db = 10 * np.log10(power / FULL_SCALE**2 + 1e-20)
    speech = db > SILENCE_FLOOR_DB
    if not speech.any():
        return []
    typical = float(np.median(db[speech]))
    quiet = db < typical - GAP_BELOW_TYPICAL_DB
    voiced = ~quiet
    starts = seconds - WINDOW_S + 1

    invalid = _gap_invalid(quiet, starts)
    invalid |= _window_sums(clips, starts) > 0
    invalid |= _loudness_invalid(db, voiced, typical, starts)

    per_second_power = (power * voiced).reshape(seconds, FRAMES_PER_S).sum(axis=1)
    per_second_voiced = voiced.reshape(seconds, FRAMES_PER_S).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        per_second_db = 10 * np.log10(per_second_power / per_second_voiced / FULL_SCALE**2)
    steadiness = np.array([
        np.nanstd(per_second_db[start : start + WINDOW_S]) if not invalid[start] else np.inf for start in range(starts)
    ])
    return sorted(_steadiest_apart(steadiness, invalid))


def choose_voice_reference(root: Path, persona: str, ask: Callable[[str], str]) -> Path:
    """The Persona's Voice Reference, made from its Voice Sample with the Operator's pick if it does not exist yet."""
    directory = persona_dir(root, persona)
    reference = directory / "voice-reference.wav"
    if reference.is_file():
        return reference
    sample = find_voice_sample(directory)
    if sample is None:
        raise ProjectError(
            f"Persona {persona} has no Voice Reference and no Voice Sample to make one from "
            f"(expected {reference} or {directory / 'voice-sample.<ext>'}), so it is not ready"
        )
    samples = decode(sample)
    starts = propose(samples)
    if not starts:
        raise ProjectError(f"No steady, unclipped 20 s stretch was found in {sample}; record a cleaner Voice Sample")
    folder = directory / "voice-reference-candidates"
    for old in folder.glob("candidate-*.wav"):
        old.unlink()
    for number, start in enumerate(starts, 1):
        first = start * RATE
        audio.write_wav(folder / f"candidate-{number}.wav", samples[first : first + WINDOW_S * RATE], RATE)
        print(f"candidate {number}: starts at {start} s  ({folder / f'candidate-{number}.wav'})")
    while True:
        try:
            answer = ask(f"Listen to the files above, then type the number of the one to use (1-{len(starts)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ProjectError(
                f"No Voice Reference was chosen for Persona {persona}; run the command again to choose one"
            ) from None
        if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(starts):
            break
        print(f"Please type a number from 1 to {len(starts)}.")
    reference.write_bytes((folder / f"candidate-{answer}.wav").read_bytes())
    print(f"Saved candidate {answer} as {reference}")
    return reference
