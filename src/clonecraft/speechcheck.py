"""The speech check: score each take against its piece's text and decide whether to keep it or try again.

Ported as-is from the earlier project's voice check, which made the approved voice (ADR 0005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import audio
from .voice import Heard, VoiceEngine, VoiceEngineError

# Scores blend word and letter accuracy, 0 to 100.
PASS_SCORE = 92.0
MID_SCORE = 85.0
MID_TAKES = 2  # a take from MID_SCORE up to PASS_SCORE is kept, but one more is tried
LOW_TAKES = 3  # a take under MID_SCORE, or with too much trailing audio, is tried again up to this many takes
TRAIL_WARN_S = 0.5  # unheard audio after the last matched word longer than this is cut off
TRAIL_FAIL_S = 1.0  # and longer than this makes the take bad


@dataclass(frozen=True)
class Verdict:
    score: float
    trailing: float

    @property
    def bad_trail(self) -> bool:
        return self.trailing > TRAIL_FAIL_S

    @property
    def keep(self) -> bool:
        return not self.bad_trail and self.score >= MID_SCORE

    @property
    def passed(self) -> bool:
        return self.keep and self.score >= PASS_SCORE

    @property
    def message(self) -> str:
        if self.bad_trail:
            return f"{self.trailing:.2f} s of audio after the last word, over {TRAIL_FAIL_S} s"
        return f"scored {self.score:.1f}"


def speak(engine: VoiceEngine, text: str, style: str | None, reference: Path, folder: Path) -> Path:
    """Speak `text` until a take passes the speech check or the tries run out, and return the take to use."""
    best: tuple[float, Path] | None = None
    kept: Path | None = None
    attempt = 0
    while True:
        take = folder / f"take-{attempt}.wav"
        engine.synthesize(text, style, reference, take)
        verdict = check(text, engine.transcribe(take), audio.seconds(take))
        if not verdict.bad_trail and (best is None or verdict.score > best[0]):
            best = (verdict.score, take)
        if verdict.keep:
            kept = take
            if TRAIL_WARN_S < verdict.trailing:
                kept = audio.trim_after(take, audio.seconds(take) - verdict.trailing, folder / f"take-{attempt}-trim.wav")
            if verdict.passed:
                return kept
            print(f"speech check: {text!r} {verdict.message}, under {PASS_SCORE:.0f}")
        attempt += 1
        if attempt < (MID_TAKES if verdict.keep else LOW_TAKES):
            continue
        if kept is not None and verdict.keep:
            return kept  # the latest take kept, even when an earlier one scored higher, as the earlier project did
        if best is not None and best[0] >= MID_SCORE:
            print(f"speech check: {text!r} kept its best take, which scored {best[0]:.1f}")
            return best[1]
        raise VoiceEngineError(f"no take of the piece {text!r} passed the speech check (the last {verdict.message})")


def check(text: str, heard: Heard, seconds: float) -> Verdict:
    return Verdict(accuracy(text, heard.text), trailing(text, heard, seconds))


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def accuracy(text: str, heard: str) -> float:
    """Blended word and letter accuracy in 0 to 100."""
    # The transcriber writes digits where Scripts spell numbers out; compare like with like.
    heard = re.sub(r"\b\d+\b", lambda m: " ".join(number_words(m.group())), heard)
    if not words_of(text) and not words_of(heard):
        return 100.0
    word = SequenceMatcher(None, words_of(text), words_of(heard)).ratio()
    letters = SequenceMatcher(None, _letters(text), _letters(heard)).ratio()
    return 100.0 * (0.5 * word + 0.5 * letters)


def _letters(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(token: str) -> list[str]:
    """Spell out a digit token below 1000 ("48" is forty eight); any other token passes through."""
    if not token.isdigit() or int(token) >= 1000:
        return [token]
    n = int(token)
    out: list[str] = []
    if n >= 100:
        out += [_ONES[n // 100], "hundred"]
        n %= 100
        if n == 0:
            return out
    if n < 20:
        return out + [_ONES[n]]
    return out + [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])


def trailing(text: str, heard: Heard, seconds: float) -> float:
    """Seconds of audio after the last word of `text` heard in order; all of it when none was heard."""
    want = words_of(text)
    if not want:
        return 0.0
    timed = [(w, word.end) for word in heard.words for token in words_of(word.text) for w in number_words(token)]
    matcher = SequenceMatcher(None, want, [w for w, _ in timed], autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    if not blocks:
        return max(0.0, seconds)
    return max(0.0, seconds - timed[blocks[-1].b + blocks[-1].size - 1][1])
