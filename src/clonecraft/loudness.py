"""The loudness of a Video's audio: normalising the Voiceover to the approved look's target, and checking the finished Video (ADR 0007)."""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import frame
from .project import ProjectError

@dataclass(frozen=True)
class Loudness:
    """Integrated loudness in LUFS and true peak in dBFS, as ffmpeg's EBU R128 filter reports them."""

    lufs: float
    peak: float


def measure(media: Path) -> Loudness:
    """The loudness of `media`'s audio, from the summary ffmpeg's ebur128 filter prints at the end."""
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    ).stderr
    summary = err[err.rfind("Summary:") :]
    lufs = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summary)
    if not (lufs and peak):
        raise ProjectError(f"the loudness of {media} could not be measured: ffmpeg printed no summary")
    return Loudness(float(lufs.group(1)), float(peak.group(1)))


def normalising_filter(voiceover: Path) -> str | None:
    """The audio filter that brings the Voiceover to LUFS: a first pass measures it, a second applies the gain and the limiter.

    The approved look's two passes : one pass alone undershoots on narration with long pauses. Silence cannot be
    normalised, so it gives None and the Video's audio stays silent.
    """
    target = f"loudnorm=I={frame.LUFS:.0f}:TP={frame.TRUE_PEAK}:LRA={frame.LOUDNESS_RANGE}"
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(voiceover), "-af", f"{target}:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    ).stderr
    if "{" not in probe:
        raise ProjectError(f"the loudness of {voiceover} could not be measured: {probe.strip()[-400:]}")
    try:
        m = json.loads(probe[probe.rindex("{") : probe.rindex("}") + 1])
        if not math.isfinite(float(m["input_i"])):
            return None
        return (
            f"{target}:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']},"
            f"alimiter=limit={frame.LIMITER}:attack=0.1:release=50:level=disabled"
        )
    except (ValueError, KeyError):
        raise ProjectError(f"the loudness of {voiceover} could not be measured: ffmpeg's report was not read") from None


def qc_warnings(video: Path) -> list[str]:
    """Warnings for a finished Video whose loudness or true peak is outside the approved look's QC limits. The Video is still kept."""
    got = measure(video)
    if got.peak == float("-inf"):
        return [f"the Video's audio is silent in {video}, so it cannot be normalised to {frame.LUFS:.0f} LUFS"]
    warnings = []
    if not abs(got.lufs - frame.LUFS) <= frame.LUFS_TOLERANCE:
        warnings.append(
            f"loudness {got.lufs:.1f} LUFS in {video}, want {frame.LUFS:.0f} ±{frame.LUFS_TOLERANCE}"
        )
    if got.peak > frame.MAX_PEAK:
        warnings.append(f"true peak {got.peak:.1f} dBFS in {video}, want ≤ {frame.MAX_PEAK:.0f}")
    return warnings
