"""Slide cards: the list after a Script's slides marker, and when each card shows in the Voiceover."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .project import ProjectError
from .speechcheck import number_words, words_of
from .voice import Word

READING_CHARS_PER_S = 15  # how fast a card's text is read (the approved look; ADR 0007)
READING_START_S = 1.5  # time to take a card in before reading it (the approved look; ADR 0007)
LEAD = 0.12  # a card cuts in this long before its phrase is spoken (the approved look; ADR 0007)
MIN_HOLD = 0.6  # a card or Face section that would show for less than this is left out (the approved look; ADR 0007)
DRIFT_WARNING_S = 45.0  # a Face section longer than this gets a warning: full-length heads drifted after about 50 s (ADR 0007)
FACE = "face"  # an entry that brings the face back instead of showing a card (ADR 0007)
KINDS = ("title", "bullet", "stat", "posting", "checklist", "cta")  # the kinds the approved look's slide template draws
CARD_KEYS = {"at", "text", "sub", "eyebrow", "kind", "button", "value"}


@dataclass(frozen=True)
class Card:
    at: str  # the spoken phrase that cuts the card in
    text: str
    kind: str = "bullet"
    sub: str | None = None
    eyebrow: str | None = None
    button: str | None = None  # cta cards only
    value: str | None = None  # stat cards only: the big number


def parse(listing: str, script_file: Path) -> list[Card]:
    """The cards written after the slides marker, each checked against what the template can draw."""
    try:
        items: Any = yaml.safe_load(listing)
    except yaml.YAMLError as error:
        raise ProjectError(f"the slides list in {script_file} is not valid YAML ({error})") from None
    if not isinstance(items, list) or not items:
        raise ProjectError(f"the slides list in {script_file} must be a list of '- at: ...' entries")
    return [_card(item, n, script_file) for n, item in enumerate(items, 1)]


@dataclass(frozen=True)
class Shown:
    """A stretch of the Video, in seconds: a card, or the face when `card` is None or a face entry."""

    card: Card | None  # None is the opening Face section
    start: float
    end: float

    @property
    def is_face(self) -> bool:
        return self.card is None or self.card.kind == FACE

    @property
    def name(self) -> str:
        return "the opening Face section" if self.card is None else f"{'Face section' if self.is_face else 'Slide card'} {self.card.at!r}"


def place(
    listed: list[Card], heard: list[Word], seconds: float, voiceover: Path, *, opening_face: bool,
    face_ends_after: str | None = None,
) -> tuple[list[Shown], list[str]]:
    """What fills each stretch of the Video, and warnings about anything left out or too long.

    An opening Face section runs until LEAD before the first entry's phrase, or to the end of `face_ends_after`.
    Each entry then shows from LEAD before its phrase is heard until the next. Neighbouring Face sections join.
    """
    # The transcriber writes digits ("10") where Scripts spell numbers out, so heard digits become words.
    timed = [(token, word) for word in heard for heard_token in words_of(word.text) for token in number_words(heard_token)]
    tokens = [token for token, _ in timed]
    starts: list[float] = []
    position = 0
    for card in listed:
        at = _find_loosely(tokens, card.at, position)
        if at is None:
            raise ProjectError(f"Slide card phrase {card.at!r} was not heard in the Voiceover {voiceover}")
        starts.append(timed[at][1].start)
        position = at + 1
    entries: list[Card | None] = list(listed)
    cuts = [max(0.0, start - LEAD) for start in starts]
    if opening_face:
        if face_ends_after is not None:
            at = find_phrase(tokens, face_ends_after)
            if at is None:
                raise ProjectError(f"face_ends_after phrase {face_ends_after!r} was not heard in the Voiceover {voiceover}")
            cuts[0] = timed[at + len(words_of(face_ends_after)) - 1][1].end
        cuts = [cuts[0]] + [max(cuts[0], cut) for cut in cuts[1:]]
        entries, cuts = [None, *entries], [0.0, *cuts]
    else:
        cuts[0] = 0.0
    ends = cuts[1:] + [seconds]
    whole = [Shown(entry, a, b) for entry, a, b in zip(entries, cuts, ends)]
    kept = [shown for shown in whole if shown.end - shown.start >= MIN_HOLD]
    warnings = [
        f"{shown.name} would show for only {shown.end - shown.start:.2f} s, so it is left out"
        for shown in whole if shown not in kept
    ]
    if not kept:
        raise ProjectError(f"everything in the slides list would show for less than {MIN_HOLD} s in the Voiceover {voiceover}")
    starts_kept = [0.0] + [shown.start for shown in kept[1:]]
    timeline: list[Shown] = []
    for shown, a, b in zip(kept, starts_kept, starts_kept[1:] + [seconds]):
        if timeline and timeline[-1].is_face and shown.is_face:
            timeline[-1] = Shown(timeline[-1].card, timeline[-1].start, b)  # one continuous face, not two renders
        else:
            timeline.append(Shown(shown.card, a, b))
    return timeline, warnings + drift_warnings(timeline)


def drift_warnings(timeline: list[Shown]) -> list[str]:
    """A warning for each Face section long enough for the face to drift."""
    return [
        f"{shown.name} runs {shown.end - shown.start:.1f} s; the face has drifted in sections longer than {DRIFT_WARNING_S:.0f} s"
        for shown in timeline if shown.is_face and shown.end - shown.start > DRIFT_WARNING_S
    ]


def reading_seconds(text: str) -> float:
    """How long a card's text takes to read, not counting spaces or emphasis marks."""
    return len(re.sub(r"\s+", "", text.replace("*", ""))) / READING_CHARS_PER_S + READING_START_S


def check_order(listed: list[Card], words: str, script_file: Path) -> bool:
    """Each card's phrase must be said in the Script after the one above it. True when the first is its opening words."""
    tokens = words_of(words)
    position = 0
    opens = False
    for n, card in enumerate(listed):
        at = find_phrase(tokens, card.at, position)
        if at is None:
            problem = "is said before the card above it" if find_phrase(tokens, card.at) is not None else "is not in the Script"
            raise ProjectError(f"Slide card phrase {card.at!r} in {script_file} {problem}")
        opens = opens if n else at == 0
        position = at + 1
    return opens


def check_face_ends_after(phrase: str, first: Card, words: str, script_file: Path) -> None:
    """The opening Face section must end at a phrase the Script says before the first card's phrase."""
    tokens = words_of(words)
    at = find_phrase(tokens, phrase)
    if at is None:
        raise ProjectError(f"face_ends_after phrase {phrase!r} in {script_file} is not in the Script")
    first_at = find_phrase(tokens, first.at)
    if first_at is not None and at + len(words_of(phrase)) > first_at:
        raise ProjectError(
            f"face_ends_after phrase {phrase!r} in {script_file} must be said before the first Slide card phrase {first.at!r}"
        )


def find_phrase(tokens: list[str], phrase: str, start: int = 0) -> int | None:
    """Where the phrase's words first run in `tokens`, at or after `start`."""
    want = words_of(phrase)
    for i in range(start, len(tokens) - len(want) + 1):
        if want and tokens[i : i + len(want)] == want:
            return i
    return None


def _find_loosely(tokens: list[str], phrase: str, start: int) -> int | None:
    """The phrase's first four words, then fewer: the transcriber sometimes mishears a word."""
    want = words_of(phrase)
    for n in range(min(len(want), 4), 0, -1):
        at = find_phrase(tokens, " ".join(want[:n]), start)
        if at is not None:
            return at
    return None


def _card(item: Any, n: int, script_file: Path) -> Card:
    where = f"Slide card {n} in {script_file}"
    if not isinstance(item, dict):
        raise ProjectError(f"{where} must be 'key: value' lines")
    unknown = sorted(set(item) - CARD_KEYS)
    if unknown:
        raise ProjectError(f"{where} has unknown key {unknown[0]!r} (allowed: {', '.join(sorted(CARD_KEYS))})")
    kind = str(item.get("kind", "bullet"))
    if kind not in KINDS + (FACE,):
        raise ProjectError(f"{where} has kind {kind!r}; use one of {', '.join(KINDS + (FACE,))}")
    for key in ("at",) + (("text",) if kind != FACE else ()) + (("button",) if kind == "cta" else ()) + (("value",) if kind == "stat" else ()):
        if not str(item.get(key) or "").strip():
            raise ProjectError(f"{where} needs {key!r}")
    for key, only in (("button", "cta"), ("value", "stat")):
        if key in item and kind != only:
            raise ProjectError(f"{where} has {key!r}, which only a {only} card shows")
    return Card(
        at=str(item["at"]), text=str(item.get("text") or ""), kind=kind,
        sub=_optional(item.get("sub")), eyebrow=_optional(item.get("eyebrow")),
        button=_optional(item.get("button")), value=_optional(item.get("value")),
    )


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)
