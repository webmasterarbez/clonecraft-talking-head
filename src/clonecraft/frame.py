"""The approved look's frame, where its overlays sit in pixels of its 1080 x 1920 frame, and its loudness (ADR 0007).

The approved look is the look of the earlier approved series, which Slide cards, the hook and the disclosure pill were copied from.

Every other Format scales from this one: a size by the smaller of the two ratios, a distance down the frame by the
height ratio. These are the only copies of these numbers.
"""

from __future__ import annotations

REFERENCE_FRAME = (1080, 1920)  # the 9:16 frame the approved look's sizes and positions are in pixels of
HOOK_Y = 1300  # the hook sits below the chin: its box's top is HOOK_Y less 150
HOOK_BOX = (1080, 420)  # the hook is drawn this size (the approved look's hookbox)
PILL_Y = 1330  # the disclosure pill's top, below the chin, on the last Slide card (the approved look's PILL_Y)
PILL_BOX = (720, 84)  # the disclosure pill is drawn this size (the approved look's pill)
LUFS = -14.0  # the Video's audio is normalised to this integrated loudness (the approved look's compose and QC steps)
LUFS_TOLERANCE = 1.5  # a finished Video within this many LUFS of LUFS passes the loudness check
TRUE_PEAK = -1.5  # dBFS: the loudnorm target for the true peak
LIMITER = 0.794  # linear, -2 dBFS: the limiter after the gain, one dB under the QC ceiling
MAX_PEAK = -1.0  # dBFS: the true peak a finished Video may reach
LOUDNESS_RANGE = 11  # LU: the loudnorm range
FADE_OUT_S = 0.4  # seconds: the Video's audio fades out over its last this long


def scale(width: int, height: int) -> float:
    """How much to scale a size from the approved look for a frame of this width and height."""
    return min(width / REFERENCE_FRAME[0], height / REFERENCE_FRAME[1])


def row_of(y: float, height: int) -> int:
    """A distance down the approved look's frame, as rows of a frame this high."""
    return round(y * height / REFERENCE_FRAME[1])
