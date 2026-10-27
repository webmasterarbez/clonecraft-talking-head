"""The boundary to the voice engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Word:
    """A word the transcriber heard, with where it starts and ends in seconds."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Heard:
    """What the transcriber heard in a take: the whole text and its timed words."""

    text: str
    words: list[Word]


class VoiceEngine(Protocol):
    def synthesize(self, text: str, style: str | None, reference: Path, out: Path) -> None:
        """Speak `text` in the voice of `reference`, writing a mono 16-bit WAV to `out`.

        `style` is the Delivery Cue's wording, or None for a neutral delivery.
        """
        ...

    def transcribe(self, audio: Path) -> Heard:
        """What a listener hears in the WAV at `audio`, for the speech check."""
        ...


class NotEnoughGpuMemory(Exception):
    """The engine could not run because too little GPU memory was free."""


class VoiceEngineError(Exception):
    """The engine gave back audio that cannot be used."""
