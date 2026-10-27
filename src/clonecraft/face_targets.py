"""Checks a Script's Face section targets against the Voiceover's real word timings (ADR 0010).

The targets are seconds in the front matter. The Slides list still triggers every cut by a phrase (ADR 0007),
so a target only produces a warning that names the nearest sentence start, and the Operator moves the phrase.
"""

from __future__ import annotations

from .cards import Shown
from .script import ScriptParts
from .voice import Word

TOLERANCE_S = 1.5  # a Face section this far from its target is warned about
SENTENCE_END = (".", "?", "!")
TRAILING = "\"'’”)*"  # quotes and emphasis that may follow a sentence's last word


def sentence_starts(words: list[Word]) -> list[float]:
    """The start of the Voiceover and of every word that begins a sentence."""
    starts = [0.0]
    for before, word in zip(words, words[1:]):
        if before.text.rstrip(TRAILING).endswith(SENTENCE_END):
            starts.append(word.start)
    return starts


def nearest(starts: list[float], seconds: float) -> float:
    return min(starts, key=lambda start: abs(start - seconds))


def warnings(parts: ScriptParts, timeline: list[Shown], words: list[Word], seconds: float) -> list[str]:
    """Warnings for any target that the Video's real Face sections miss by more than TOLERANCE_S."""
    out: list[str] = []
    if parts.face_front_s is None and parts.face_back_s is None:
        return out
    starts = sentence_starts(words)
    first, last = timeline[0], timeline[-1]
    multi = len(timeline) > 1  # a Video with no Slide cards has no front or back to measure
    front = first.end if multi and first.is_face else None
    back = seconds - last.start if multi and last.is_face else None
    if parts.face_front_s is not None:
        target = parts.face_front_s
        if front is None:
            out.append(f"face_front_s is {target:g} s but the Video opens on a Slide card, so there is no opening Face section")
        elif abs(front - target) > TOLERANCE_S:
            out.append(
                f"the opening Face section is {front:.1f} s, not {target:g} s; the nearest sentence start to "
                f"{target:g} s is {nearest(starts, target):.1f} s, so move the first card's phrase there"
            )
    if parts.face_back_s is not None:
        target = parts.face_back_s
        if back is None:
            out.append(f"face_back_s is {target:g} s but the Video has no closing Face section")
        elif abs(back - target) > TOLERANCE_S:
            start = nearest(starts, seconds - target)
            out.append(
                f"the closing Face section is {back:.1f} s, not {target:g} s; the nearest sentence start is "
                f"{start:.1f} s, so move the Face entry's phrase there"
            )
    return out
