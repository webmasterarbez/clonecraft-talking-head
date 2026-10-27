"""Checking the model files in models/ against config/models.toml."""

from __future__ import annotations

import hashlib
import os
import shutil
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .project import ProjectError


@dataclass(frozen=True)
class ModelFile:
    path: str
    size: int
    sha256: str
    url: str


@dataclass(frozen=True)
class Verdict:
    model: ModelFile
    problem: str | None  # None when the file is good


def load_listing(root: Path) -> list[ModelFile]:
    listing = root / "config" / "models.toml"
    if not listing.is_file():
        raise ProjectError(f"The model list is missing (expected {listing})")
    try:
        entries = tomllib.loads(listing.read_text())["model"]
        found = [ModelFile(e["path"], int(e["size"]), e["sha256"], e["url"]) for e in entries]
    except (tomllib.TOMLDecodeError, KeyError, ValueError, TypeError) as error:
        raise ProjectError(
            f"{listing} is not a valid model list (each [[model]] needs path, size, sha256 and url): {error}"
        ) from None
    inside = (root / "models").resolve()
    for model in found:
        if not (inside / model.path).resolve().is_relative_to(inside):
            raise ProjectError(f"Model path {model.path} in {listing} points outside models/")
    return found


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def check(root: Path) -> list[Verdict]:
    verdicts = []
    for model in load_listing(root):
        path = root / "models" / model.path
        problem: str | None = None
        if not path.is_file():
            problem = "MISSING"
        elif path.stat().st_size != model.size:
            problem = f"WRONG SIZE ({path.stat().st_size} bytes, expected {model.size})"
        elif sha256_of(path) != model.sha256:
            problem = "WRONG CONTENT"
        verdicts.append(Verdict(model, problem))
    return verdicts


def fix(root: Path, verdicts: list[Verdict]) -> tuple[list[str], list[str]]:
    """Download every file with a problem. Returns the paths fixed and an error line per failure."""
    fixed: list[str] = []
    errors: list[str] = []
    for verdict in verdicts:
        if verdict.problem is None:
            continue
        model = verdict.model
        target = root / "models" / model.path
        partial = target.with_name(target.name + ".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(model.url) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, 1 << 24)
        except (OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            errors.append(f"{model.path}: download from {model.url} failed ({error})")
            continue
        if partial.stat().st_size != model.size or sha256_of(partial) != model.sha256:
            partial.unlink()
            errors.append(f"{model.path}: the downloaded file still fails its check, so it was not kept")
            continue
        os.replace(partial, target)
        fixed.append(model.path)
    return fixed, errors
