"""The boundary to headless Chrome, which draws Slide cards from a Brand pack's page."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from .project import ProjectError

CHROME = "google-chrome"
CHROME_TIMEOUT_S = 60  # a card page draws in about a second; longer means Chrome is stuck
# Run in a copy of the page: every leaf text element must sit inside the viewport, which is the card's frame.
# A range measures the glyphs, which run past an element's box when a word is too wide to wrap (the approved look's probe).
FIT_PROBE = """<script>
document.fonts.ready.then(() => {
  const vw = innerWidth, vh = innerHeight;
  const out = [...document.querySelectorAll('.frame *')].filter(el => !el.children.length && el.textContent.trim())
    .some(el => { const g = document.createRange(); g.selectNodeContents(el); const r = g.getBoundingClientRect();
      return r.left < -0.5 || r.top < -0.5 || r.right > vw + 0.5 || r.bottom > vh + 0.5; });
  document.body.setAttribute('data-fit', out ? '0' : '1');
});
</script>"""


class Browser(Protocol):
    def screenshot(self, page: Path, width: int, height: int, out: Path) -> None:
        """Write a PNG of `page` drawn in a `width` by `height` window to `out`."""
        ...

    def fits(self, page: Path, width: int, height: int) -> bool:
        """Whether all of the page's text sits inside a `width` by `height` window."""
        ...


class ChromeBrowser:
    @classmethod
    def found(cls) -> ChromeBrowser | None:
        return cls() if shutil.which(CHROME) else None

    def screenshot(self, page: Path, width: int, height: int, out: Path) -> None:
        drawn = self._run(page, width, height, "--force-device-scale-factor=1", "--default-background-color=00000000",
                          f"--screenshot={out}")
        if drawn.returncode or not out.is_file():
            raise ProjectError(f"{CHROME} could not draw the Slide card {page}: {drawn.stderr.strip()[-400:]}")

    def fits(self, page: Path, width: int, height: int) -> bool:
        """A missing marker means the probe did not run, which counts as not fitting, so it shows as a warning."""
        html = page.read_text()
        probe = page.with_name(page.stem + ".fit.html")
        probe.write_text(html.replace("</body>", FIT_PROBE + "</body>") if "</body>" in html else html + FIT_PROBE)
        dumped = self._run(probe, width, height, "--dump-dom")
        return dumped.returncode == 0 and 'data-fit="1"' in dumped.stdout

    def _run(self, page: Path, width: int, height: int, *flags: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                 "--virtual-time-budget=2000", *flags, page.resolve().as_uri()],
                capture_output=True, text=True, timeout=CHROME_TIMEOUT_S, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            raise ProjectError(f"{CHROME} did not finish the Slide card {page} within {CHROME_TIMEOUT_S} s") from None
