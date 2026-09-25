"""013 WI-10 theme-layer helpers shared by `tests/e2e/shell_4a/` and the unit lane.

Group directories cannot hold a `conftest.py` (see `scripts/lint_e2e_groups.py`), so
the helpers live here, next to `shell_4a_fixtures.py`.

What is here:

    CHROMES / READINGS / COMBOS         the 2 x 5 = 10 theme combinations (spec §3.3)
    relative_luminance / contrast       WCAG 2.1 contrast ratio (C10.13)
    parse_rgb                            computed-style colour string -> (r, g, b)
    dist_token_names()                   every `--r3-*` the built CSS defines
    FOUC_KEYS / expected_stamp()         the FOUC stamp's table oracle (C10.15 / C10.22)
    storage_init_script()                localStorage seeding for one storage row
    RESOLVE_JS / RESOLVE_COLOR_JS        page-side readers for custom properties

**Why chrome and reading are set by attribute here, not through localStorage.** The
resolution cases (C10.09-C10.14) test the CSS, not the stamp; setting the two `<html>`
attributes directly keeps a stamp bug from masquerading as a token bug. The stamp has
its own cases (`test_fouc.py`), which go through localStorage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "src" / "reader3_app" / "web" / "static" / "dist"

CHROMES: Tuple[str, ...] = ("light", "dark")
READINGS: Tuple[str, ...] = ("auto", "paper", "sepia", "green", "night")
ABSOLUTE_PAPERS: Tuple[str, ...] = ("paper", "sepia", "green", "night")
COMBOS: Tuple[Tuple[str, str], ...] = tuple((c, r) for c in CHROMES for r in READINGS)

#: The reading-axis tokens (spec §3.3 table): the page trio and the four highlights.
MARKER_COLORS: Tuple[str, ...] = ("yellow", "green", "pink", "blue")
READING_TOKENS: Tuple[str, ...] = (
    "--r3-page-bg",
    "--r3-page-ink",
    "--r3-page-quiet",
    *(f"--r3-hl-{c}-rgb" for c in MARKER_COLORS),
    *(f"--r3-hl-{c}" for c in MARKER_COLORS),
)
STATUS_TOKENS: Tuple[str, ...] = (
    "--r3-success",
    "--r3-warning",
    "--r3-error",
    "--r3-info",
)

# --------------------------------------------------------------------------
# WCAG 2.1 contrast
# --------------------------------------------------------------------------
_RGB_RE = re.compile(r"^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

RGB = Tuple[float, float, float]


def parse_rgb(value: str) -> RGB:
    """`rgb(1, 2, 3)` / `rgb(1 2 3)` / `rgba(..., 1)` / `#abc` / `#aabbcc` -> (r, g, b) in 0..255.

    A colour with an alpha below 1 is refused: a contrast ratio against a translucent
    colour depends on what is under it, and pretending otherwise yields a number that
    means nothing.
    """
    text = value.strip()
    m = _RGB_RE.match(text)
    if m:
        alpha = m.group(4)
        if alpha is not None:
            a = float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)
            if a < 1:
                raise ValueError(f"translucent colour has no standalone contrast: {value!r}")
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = _HEX_RE.match(text)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return (float(int(h[0:2], 16)), float(int(h[2:4], 16)), float(int(h[4:6], 16)))
    raise ValueError(f"not a colour: {value!r}")


def relative_luminance(rgb: RGB) -> float:
    def lin(channel: float) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str | RGB, b: str | RGB) -> float:
    la = relative_luminance(parse_rgb(a) if isinstance(a, str) else a)
    lb = relative_luminance(parse_rgb(b) if isinstance(b, str) else b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------------
# The built CSS
# --------------------------------------------------------------------------
_DEFINE_RE = re.compile(r"(--r3-[a-z0-9-]+)\s*:")


def dist_css_files(dist: Path = DIST) -> List[Path]:
    manifest = dist / "manifest.json"
    assert manifest.is_file(), f"no Vite manifest at {manifest} -- run `npm run build`"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    files: Set[str] = set()
    for chunk in doc.values():
        files.update(chunk.get("css", []))
    return [dist / f for f in sorted(files)]


def dist_token_names(dist: Path = DIST) -> List[str]:
    names: Set[str] = set()
    for path in dist_css_files(dist):
        names.update(_DEFINE_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(names)


# --------------------------------------------------------------------------
# FOUC oracle
# --------------------------------------------------------------------------
COLOR_SCHEME_KEY = "reader3.ui.colorScheme"
READING_THEME_KEY = "reader3.reader.theme"
FOUC_KEYS: Tuple[str, str] = (COLOR_SCHEME_KEY, READING_THEME_KEY)

#: None = the key is absent from localStorage.
COLOR_SCHEME_ROWS: Tuple[Optional[str], ...] = (None, "system", "light", "dark", "bogus")
READING_ROWS: Tuple[Optional[str], ...] = (None, "auto", "paper", "night", "bogus")
STORAGE_ROWS: Tuple[Tuple[Optional[str], Optional[str]], ...] = tuple(
    (cs, rd) for cs in COLOR_SCHEME_ROWS for rd in READING_ROWS
)


def expected_stamp(color_scheme: Optional[str], reading: Optional[str]) -> List[Optional[str]]:
    """[data-theme, data-reading-theme] the stamp must leave on `<html>` (spec §3.3 table)."""
    theme = color_scheme if color_scheme in ("light", "dark") else None
    reading_attr = reading if reading in READINGS else "auto"
    return [theme, reading_attr]


def storage_init_script(color_scheme: Optional[str], reading: Optional[str]) -> str:
    """An init script that leaves localStorage holding exactly this row's two keys."""
    lines = ["(() => {", "  try {"]
    for key, value in ((COLOR_SCHEME_KEY, color_scheme), (READING_THEME_KEY, reading)):
        if value is None:
            lines.append(f"    localStorage.removeItem({json.dumps(key)});")
        else:
            lines.append(f"    localStorage.setItem({json.dumps(key)}, {json.dumps(value)});")
    lines += ["  } catch (e) {}", "})();"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Page-side readers
# --------------------------------------------------------------------------
#: Set both axes on <html>. `chrome` is "light" | "dark"; reading is one of READINGS.
SET_AXES_JS = """([chrome, reading]) => {
  const html = document.documentElement;
  html.setAttribute("data-theme", chrome);
  html.setAttribute("data-reading-theme", reading);
}"""

#: Resolve custom properties on an element: el -> {name: computed value (trimmed)}.
RESOLVE_JS = """(el, names) => {
  const cs = getComputedStyle(el);
  const out = {};
  for (const n of names) out[n] = cs.getPropertyValue(n).trim();
  return out;
}"""

#: Resolve colour-valued custom properties to computed rgb() strings through a probe
#: child, so hex, rgb() and var()-chained values all come back in one canonical form.
RESOLVE_COLOR_JS = """(el, names) => {
  const probe = document.createElement("span");
  el.appendChild(probe);
  const out = {};
  try {
    for (const n of names) {
      probe.style.color = "";
      probe.style.color = `var(${n})`;
      out[n] = getComputedStyle(probe).color;
    }
  } finally {
    probe.remove();
  }
  return out;
}"""


def triplet_ok(value: str) -> bool:
    return re.fullmatch(r"\d{1,3} \d{1,3} \d{1,3}", value) is not None and all(
        0 <= int(x) <= 255 for x in value.split()
    )


def unique(values: Sequence[object]) -> int:
    return len({json.dumps(v, sort_keys=True) for v in values})
