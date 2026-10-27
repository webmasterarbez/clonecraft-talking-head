"""A Persona's Brand pack: the look its Slide cards are drawn in."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cards import Card
from .project import Channel, ProjectError

# Settings every pack must hold, as the approved look checked them: (key path, names a font file in fonts/?).
PACK_KEYS = [("colors.teal", False), ("fonts.ui", True), ("fonts.mono", True), ("mark", False), ("disclosure", False)]
CARD_STYLE = "p"  # the template style the approved look drew every approved card in


@dataclass(frozen=True)
class BrandPack:
    directory: Path
    settings: dict[str, Any]

    @property
    def fonts(self) -> Path:
        return self.directory / "fonts"

    @property
    def accent(self) -> str:
        """The colour of the hook's *words* and the card accents."""
        return str(self.settings["colors"]["teal"])

    def page(self, card: Card, out: Path) -> Path:
        """Fill the pack's slide template with one card, writing the page to `out`."""
        slide = {
            "kind": card.kind, "text": card.text, "sub": card.sub, "eyebrow": card.eyebrow or "",
            "button": card.button, "value": card.value, "style": CARD_STYLE, "mode": "card",
        }
        return self._filled(slide, out)

    def pill_page(self, out: Path) -> Path:
        """Fill the pack's slide template with the disclosure pill: the pack's `disclosure` text in its look."""
        return self._filled({"kind": "pill", "text": self.settings["disclosure"], "mode": "pill", "style": CARD_STYLE}, out)

    @property
    def wordmark(self) -> str | None:
        """The name drawn beside the mark on the badge and the end card; a pack without one draws no badge."""
        value = self.settings.get("wordmark")
        return str(value) if value else None

    @property
    def end_card(self) -> dict[str, str] | None:
        """The end card's `line` and `url`; a pack without `end_card` adds nothing after the Voiceover."""
        value = self.settings.get("end_card")
        return {"line": str(value["line"]), "url": str(value["url"])} if value else None

    def badge_page(self, out: Path) -> Path:
        """Fill the pack's slide template with the badge: the mark and the wordmark, for the Face sections."""
        return self._filled({"kind": "badge", "text": self.wordmark, "mode": "badge", "style": CARD_STYLE}, out)

    def end_page(self, out: Path) -> Path:
        """Fill the pack's slide template with the end card: the mark, the wordmark, the line and the web address."""
        end = self.end_card or {}
        slide = {"kind": "end", "text": self.wordmark or "", "line": end.get("line", ""), "url": end.get("url", ""),
                 "mode": "end", "style": CARD_STYLE}
        return self._filled(slide, out)

    def hook_page(self, hook: str, out: Path) -> Path:
        """Fill the pack's slide template with the hook, the approved look's white outlined text with *words* in the accent colour."""
        text = html.escape(hook).replace("\n", "<br>")
        text = re.sub(r"\*(.+?)\*", rf'<span style="color:{html.escape(self.accent)}">\1</span>', text)
        box = (
            '<div style="font:800 76px/1.1 Jakarta;color:#fff;-webkit-text-stroke:4px #000;paint-order:stroke fill;'
            f'text-shadow:0 6px 18px rgba(0,0,0,.55);max-width:1020px">{text}</div>'
        )
        return self._filled({"kind": "raw", "html": box, "mode": "hookbox"}, out)

    def _filled(self, slide: dict[str, Any], out: Path) -> Path:
        pack = {"colors": self.settings["colors"], "mark_url": (self.directory / self.settings["mark"]).resolve().as_uri()}
        page = (
            (self.directory / "slide.html").read_text()
            .replace("__FONT_UI__", (self.fonts / self.settings["fonts"]["ui"]).resolve().as_uri())
            .replace("__FONT_MONO__", (self.fonts / self.settings["fonts"]["mono"]).resolve().as_uri())
            .replace("__FONT_ARTIFACT__", self._artifact_font())
            .replace("__SLIDE__", _script_json(slide))
            .replace("__PACK__", _script_json(pack))
        )
        out.write_text(page)
        return out

    def _artifact_font(self) -> str:
        """The serif for *words* on the cards; an empty URL when the pack names none, so the page falls back."""
        name = self.settings["fonts"].get("artifact")
        return (self.fonts / name).resolve().as_uri() if name else ""


def choose(root: Path, persona: str, channel: Channel) -> BrandPack:
    """The pack `channel.yaml` names with brand_pack:, or the Persona's only pack when it names none."""
    folder = root / "persona" / persona / "brand-packs"
    named = channel.settings.get("brand_pack")
    if named:
        directory = folder / str(named)
        if not directory.is_dir():
            raise ProjectError(
                f"Brand pack {named} named in {channel.directory / 'channel.yaml'} not found (expected {directory})"
            )
    else:
        packs = sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
        if not packs:
            raise ProjectError(
                f"Persona {persona} has no Brand pack (expected a folder in {folder}; "
                "copy config/brand-pack-starter there to start one)"
            )
        if len(packs) > 1:
            raise ProjectError(
                f"Persona {persona} has several Brand packs ({', '.join(p.name for p in packs)}); "
                f"name one with brand_pack: in {channel.directory / 'channel.yaml'}"
            )
        directory = packs[0]
    return BrandPack(directory, _checked(directory))


def _checked(directory: Path) -> dict[str, Any]:
    settings_file = directory / "pack.json"
    for needed in (settings_file, directory / "slide.html"):
        if not needed.is_file():
            raise ProjectError(f"Brand pack {directory.name} has no {needed.name} (expected {needed})")
    try:
        settings: Any = json.loads(settings_file.read_text())
    except json.JSONDecodeError as error:
        raise ProjectError(f"{settings_file} is not valid JSON ({error.msg}, line {error.lineno})") from None
    except UnicodeDecodeError:
        raise ProjectError(f"{settings_file} is not valid JSON (it is not UTF-8 text)") from None
    if not isinstance(settings, dict):
        raise ProjectError(f"{settings_file} must hold a JSON object of settings")
    for key, is_font in PACK_KEYS:
        value: Any = settings
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ProjectError(f"{settings_file} is missing the setting {key}")
        if is_font and not (directory / "fonts" / value).is_file():
            raise ProjectError(f"{settings_file} names font {value} for {key}, which is not in {directory / 'fonts'}")
    if not (directory / settings["mark"]).is_file():
        raise ProjectError(f"{settings_file} names mark {settings['mark']}, which is not in {directory}")
    artifact = settings["fonts"].get("artifact")
    if artifact is not None and (not isinstance(artifact, str) or not (directory / "fonts" / artifact).is_file()):
        raise ProjectError(f"{settings_file} names font {artifact} for fonts.artifact, which is not in {directory / 'fonts'}")
    if "wordmark" in settings and (not isinstance(settings["wordmark"], str) or not settings["wordmark"].strip()):
        raise ProjectError(f"{settings_file} has an empty wordmark; give the name to draw or remove the setting")
    if "end_card" in settings:
        end = settings["end_card"]
        if "wordmark" not in settings:
            raise ProjectError(f"{settings_file} has an end_card but no wordmark; the end card draws the wordmark")
        for key in ("line", "url"):
            if not isinstance(end, dict) or not isinstance(end.get(key), str) or not end[key].strip():
                raise ProjectError(f"{settings_file} is missing the setting end_card.{key}")
    return settings


def _script_json(value: Any) -> str:
    """JSON safe inside a <script> element: card text holding '</script>' cannot end it."""
    return json.dumps(value).replace("</", "<\\/")
