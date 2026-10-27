"""Reading a Script: its words, and the Delivery Cues that shape how they are spoken."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import cards
from .cards import Card
from .project import ProjectError

CUE = re.compile(r"\[([^\[\]]+)\]")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
SLIDES_MARKER = "<!-- slides -->"
FRONT_KEYS = {"title", "hook", "face_ends_after", "hook_hold", "face_front_s", "face_back_s"}  # title is not used yet
CHUNK_WORDS = 18  # whole sentences are packed into pieces of at most this many words, as the approved look did (ADR 0005)


@dataclass(frozen=True)
class ScriptParts:
    """A Script file split into what is spoken and what is shown."""

    spoken: str  # the words and Delivery Cues, without front matter or slides list
    cards: list[Card]
    opens_with_card: bool = False  # the first card's phrase is the Script's opening words
    face_ends_after: str | None = None
    hook: str | None = None  # drawn over the opening Face section; *word* is highlighted
    hook_hold: float = 0.0  # seconds the hook shows; required with a hook
    face_front_s: float | None = None  # the opening Face section's target length, checked against the Voiceover (ADR 0010)
    face_back_s: float | None = None  # the closing Face section's target length, checked against the Voiceover (ADR 0010)

    @property
    def uses_brand_pack(self) -> bool:
        """Whether the Video is drawn in the Brand pack: a Slide card that is not a Face section, or a hook."""
        return any(card.kind != cards.FACE for card in self.cards) or self.hook is not None


def parts_of(text: str, script_file: Path) -> ScriptParts:
    """Front matter between two '---' lines may open the file; a slides marker may close the spoken part."""
    front: dict[str, Any] = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
        if closing is None:
            raise ProjectError(f"the front matter in {script_file} has no closing '---' line")
        front = _front_matter("\n".join(lines[1:closing]), script_file)
        lines = lines[closing + 1:]
    marker = next((i for i, line in enumerate(lines) if line.strip() == SLIDES_MARKER), None)
    spoken = "\n".join(lines if marker is None else lines[:marker])
    listed = [] if marker is None else cards.parse("\n".join(lines[marker + 1:]), script_file)
    opens = cards.check_order(listed, CUE.sub(" ", spoken), script_file)
    face = front.get("face_ends_after")
    if face is not None and listed:
        cards.check_face_ends_after(str(face), listed[0], CUE.sub(" ", spoken), script_file)
    hook = str(front.get("hook") or "").strip() or None  # an empty hook is no hook
    return ScriptParts(
        spoken, listed, opens, None if face is None else str(face),
        hook, _hook_hold(front, script_file) if hook is not None else 0.0,
        face_front_s=_seconds(front, "face_front_s", script_file),
        face_back_s=_seconds(front, "face_back_s", script_file),
    )


def _seconds(front: dict[str, Any], key: str, script_file: Path) -> float | None:
    value = front.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ProjectError(f"{key} in {script_file} must be a number of seconds above 0, not {value!r}")
    return float(value)


def _hook_hold(front: dict[str, Any], script_file: Path) -> float:
    hold = front.get("hook_hold")
    if hold is None:
        raise ProjectError(f"the front matter in {script_file} has a hook but no hook_hold (the seconds it shows)")
    if isinstance(hold, bool) or not isinstance(hold, (int, float)) or hold <= 0:
        raise ProjectError(f"hook_hold in {script_file} must be a number of seconds above 0, not {hold!r}")
    return float(hold)


def _front_matter(text: str, script_file: Path) -> dict[str, Any]:
    try:
        front: Any = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        raise ProjectError(f"the front matter in {script_file} is not valid YAML ({error})") from None
    if not isinstance(front, dict):
        raise ProjectError(f"the front matter in {script_file} must be 'key: value' lines")
    unknown = sorted(set(map(str, front)) - FRONT_KEYS)
    if unknown:
        raise ProjectError(
            f"the front matter in {script_file} has unknown key {unknown[0]!r} (allowed: {', '.join(sorted(FRONT_KEYS))})"
        )
    return front


@dataclass(frozen=True)
class Piece:
    """A stretch of text spoken in one go, with the style its Delivery Cue asks for."""

    style: str | None
    text: str


def spoken_fingerprint(spoken: str) -> str:
    """A hash of the words spoken, without Delivery Cues: only a change to the words makes a Voiceover out of date (ADR 0008)."""
    words = " ".join(CUE.sub(" ", spoken).split())
    return hashlib.sha256(words.encode()).hexdigest()


def pieces_of(script: str) -> list[Piece]:
    """A cue styles the text after it until the end of its paragraph or the next cue."""
    pieces: list[Piece] = []
    for paragraph in re.split(r"\n\s*\n", script):
        style: str | None = None
        position = 0
        for cue in [*CUE.finditer(paragraph), None]:
            end = cue.start() if cue else len(paragraph)
            text = " ".join(paragraph[position:end].split())
            if text:
                pieces.extend(Piece(style, part) for part in _split(text))
            if cue:
                style = cue.group(1).strip()
                position = cue.end()
    return pieces


def _split(text: str) -> list[str]:
    """Pack whole sentences into pieces of at most CHUNK_WORDS words; a longer sentence stays whole."""
    pieces: list[list[str]] = []
    for sentence in SENTENCE_END.split(text):
        words = len(sentence.split())
        if pieces and sum(len(s.split()) for s in pieces[-1]) + words <= CHUNK_WORDS:
            pieces[-1].append(sentence)
        else:
            pieces.append([sentence])
    return [" ".join(piece) for piece in pieces]
