"""The Voiceover's word timings: what the transcriber heard in the finished file, and when."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .project import ProjectError
from .voice import VoiceEngine, Word


def save(engine: VoiceEngine, voiceover: Path, out: Path) -> list[Word]:
    """Transcribe the whole Voiceover and save its words beside it, tied to the file they came from."""
    words = engine.transcribe(voiceover).words
    record = {
        "voiceover_sha256": _sha256(voiceover),
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in words],
    }
    out.write_text(json.dumps(record, indent=1) + "\n")
    return words


def load(voiceover: Path, saved: Path) -> list[Word] | None:
    """The saved words, or None when there are none or they belong to an earlier Voiceover."""
    if not saved.is_file():
        return None
    try:
        record = json.loads(saved.read_text())
        if record["voiceover_sha256"] != _sha256(voiceover):
            return None
        return [Word(str(w["text"]), float(w["start"]), float(w["end"])) for w in record["words"]]
    except (ValueError, KeyError, TypeError):
        raise ProjectError(f"{saved} is not a word timings file; delete it and CloneCraft makes it again") from None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
