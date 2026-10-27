"""The boundary to the face engine."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

FACE_SIZES = {"9:16": (480, 832), "16:9": (832, 480)}  # width and height the face engine works at, per aspect
FACE_FPS = 25


class FaceEngine(Protocol):
    def render(self, portrait: Path, jobs: list[tuple[Path, Path]]) -> None:
        """For each (audio, out) job, write to `out` one continuous mp4 clip of `portrait` speaking `audio`.

        All jobs run in one session, so the models load once. `portrait` is already cropped and scaled to
        its aspect's FACE_SIZES entry. Each clip is that size at FACE_FPS and at least as long as its audio;
        it may run longer.
        """
        ...


class FaceEngineError(Exception):
    """The engine gave back a clip that cannot be used."""
