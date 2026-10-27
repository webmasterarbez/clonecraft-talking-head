"""Render one Slide card of each kind from a Brand pack, at each size, in the real headless Chrome.

Run from the repo root:
    uv run python .claude/skills/talking-head-video-composition/scripts/render-card-kinds.py PACK_DIR OUT_DIR SIZE...
e.g.
    uv run python .claude/skills/talking-head-video-composition/scripts/render-card-kinds.py config/brand-pack-starter /tmp/cards/before 1080x1920 1920x1080

Prints "<kind> <size> fits" or "<kind> <size> OVERFLOWS" for each card. Render a baseline before editing
slide.html, render again after the edit, then cmp the PNGs of the aspect that must not change.
"""

import json
import sys
from pathlib import Path

from clonecraft.brandpack import BrandPack
from clonecraft.browser import ChromeBrowser
from clonecraft.cards import Card

CARDS = {
    "title": Card("x", "Three *signs* a posting is a ghost job", "title", eyebrow="Job search"),
    "bullet": Card("x", "Check when it was *first* posted", "bullet", sub="Anything older than 30 days is a warning sign"),
    "stat": Card("x", "of postings never lead to a hire", "stat", value="27%"),
    "posting": Card("x", "Spot the *red flags*", "posting"),
    "checklist": Card("x", "Posted this week / Named hiring manager / Real salary range", "checklist"),
    "cta": Card("x", "Get the full **checklist**", "cta", sub="Free, one page", button="Download"),
    "long": Card("x", "A very long line of card text that keeps on going and going to test how wrapping behaves at width", "bullet", sub="And a sub line under it that is also fairly long"),
}


def main(argv: list[str]) -> int:
    pack_dir, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    pack = BrandPack(pack_dir, json.loads((pack_dir / "pack.json").read_text()))
    browser = ChromeBrowser()
    for size in argv[3:]:
        width, height = (int(part) for part in size.split("x"))
        for kind, card in CARDS.items():
            page = pack.page(card, out / f"{kind}-{size}.html")
            browser.screenshot(page, width, height, out / f"{kind}-{size}.png")
            status = "fits" if browser.fits(page, width, height) else "OVERFLOWS"
            print(kind, size, status)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
