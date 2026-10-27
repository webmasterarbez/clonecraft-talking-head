"""Where a Channel's, Persona's and Script's files live."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProjectError(Exception):
    """A problem the Operator can fix, worded for them."""


ASPECTS = ("9:16", "16:9")  # the only Formats the face engine can make (ADR 0006)


@dataclass(frozen=True)
class Format:
    """The look every Video of a Channel has."""

    aspect: str
    width: int
    height: int
    fps: int


@dataclass(frozen=True)
class Channel:
    directory: Path
    persona: str
    settings: dict[str, Any]

    def script_path(self, script: str) -> Path:
        return self.directory / "scripts" / f"{script}.md"

    def voiceover_path(self, script: str) -> Path:
        return self.directory / "voiceovers" / f"{script}.wav"

    def words_path(self, script: str) -> Path:
        return self.directory / "voiceovers" / f"{script}.words.json"

    def spoken_record_path(self, script: str) -> Path:
        return self.directory / "voiceovers" / f"{script}.spoken.sha256"

    def video_path(self, script: str, fmt: Format) -> Path:
        return self.directory / "videos" / f"{script}.{fmt.width}x{fmt.height}.mp4"

    def face_sections_path(self, script: str, fmt: Format) -> Path:
        """Where a Video's rendered Face sections are kept for reuse."""
        return self.directory / "videos" / "face-sections" / f"{script}.{fmt.width}x{fmt.height}"

    def formats(self) -> list[Format]:
        config_path = self.directory / "channel.yaml"
        if "format" in self.settings:
            raise ProjectError(
                f"{config_path} has a single format: block; change it to a formats: list with one entry (see the operator guide)"
            )
        raw: Any = self.settings.get("formats")
        try:
            formats = [_format_of(entry) for entry in raw]
        except (TypeError, KeyError, ValueError):
            raise ProjectError(
                f"{config_path} needs a formats: list, each with aspect, resolution (for example 1080x1920) and fps"
            ) from None
        for fmt in formats:
            if fmt.aspect not in ASPECTS:
                raise ProjectError(f"{config_path} has Format {fmt.aspect}; only 9:16 and 16:9 are supported")
        aspects = [fmt.aspect for fmt in formats]
        if len(set(aspects)) != len(aspects):
            raise ProjectError(f"{config_path} lists a Format more than once for one aspect ({', '.join(aspects)})")
        return formats


def choose_format(channel: Channel, aspect: str | None) -> Format:
    """The Format a Video is made in: the named aspect, or the only Format when none is named."""
    formats = channel.formats()
    listed = ", ".join(f.aspect for f in formats)
    if aspect is None:
        if len(formats) == 1:
            return formats[0]
        raise ProjectError(f"Channel {channel.directory.name} has several Formats ({listed}); choose one with --format")
    for fmt in formats:
        if fmt.aspect == aspect:
            return fmt
    raise ProjectError(f"Format {aspect} is not one of this Channel's Formats in {channel.directory / 'channel.yaml'} ({listed})")


def _format_of(entry: Any) -> Format:
    width, height = str(entry["resolution"]).split("x")
    return Format(str(entry["aspect"]), int(width), int(height), int(entry["fps"]))


def load_channel(root: Path, channel_ref: str) -> Channel:
    platform, _, handle = channel_ref.partition("/")
    directory = root / "platform" / platform / "channels" / handle
    if not directory.is_dir():
        raise ProjectError(f"Channel {channel_ref} not found (looked for {directory})")
    settings = directory / "channel.yaml"
    if not settings.is_file():
        raise ProjectError(f"Channel {channel_ref} has no channel.yaml (expected {settings})")
    config = yaml.safe_load(settings.read_text())
    if not isinstance(config, dict) or not config.get("persona"):
        raise ProjectError(f"{settings} does not name a persona")
    return Channel(directory, str(config["persona"]), config)


def read_script(channel: Channel, script: str) -> str:
    path = channel.script_path(script)
    if not path.is_file():
        raise ProjectError(f"Script {script} not found (expected {path})")
    return path.read_text()


def persona_dir(root: Path, persona: str) -> Path:
    directory = root / "persona" / persona
    if not directory.is_dir():
        raise ProjectError(f"Persona {persona} not found (expected {directory})")
    return directory


def likeness_path(root: Path, persona: str, aspect: str) -> Path:
    """The Likeness for a Format's aspect: `likeness.*` for 9:16, `likeness-horizontal.*` for 16:9."""
    name = {"9:16": "likeness", "16:9": "likeness-horizontal"}[aspect]
    found = sorted((root / "persona" / persona).glob(f"{name}.*"))
    if not found:
        raise ProjectError(
            f"Persona {persona} has no Likeness for {aspect} (expected {root / 'persona' / persona / f'{name}.<ext>'})"
        )
    return found[0]


def current_voiceover(channel: Channel, script: str) -> Path:
    path = channel.voiceover_path(script)
    if not path.is_file():
        raise ProjectError(f"Script {script} has no Voiceover yet (expected {path}); run clonecraft voiceover first")
    return path
