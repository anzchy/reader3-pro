"""013 WI-10 static token hygiene: A10.1, A10.10, A10.11 (handwritten side), A10.15.

C10.05 -- three absence scans over the real tree, each proven failable by a seed:
    * component styles reference no Tier 1 `--p-*` (only the token definition files may);
    * no stylesheet anywhere (sources, legacy static, templates, built dist) has a
      `[data-reading-theme="auto"]` selector -- auto works by having NO rule;
    * no handwritten stylesheet carries a dark chrome block -- the only author is the
      Vite plugin, so the two dark selectors appear in the built CSS and nowhere else.

C10.06 -- every `var(--r3-duration-*)` in a transition/animation declaration is paired
with a `var(--r3-ease-*)` in the SAME comma segment (plan WI-10: "43 处一律写成
`var(--r3-duration-X) var(--r3-ease-Y)`"). The check is per segment, not per
declaration or per file: `transition: opacity var(--r3-duration-fast), color
var(--r3-duration-fast) var(--r3-ease-standard)` has an unpaired first segment. A
Hypothesis oracle builds declarations whose violations are known by construction.
Also: `var(--dedao-transition-` occurs 0 times.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import shell_4a_theme as th
from hypothesis import given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[2]
FE_SRC = REPO / "frontend" / "src"
WEB = REPO / "src" / "reader3_app" / "web"
STATIC = WEB / "static"
TEMPLATES = WEB / "templates"

TOKENS_CSS = FE_SRC / "styles" / "tokens.css"
THEME_TOKENS_TS = FE_SRC / "shared" / "theme-tokens.ts"
#: The Tier 1 definition sites: the only files allowed to mention `--p-*`.
TOKEN_DEFINITION_FILES = {TOKENS_CSS, THEME_TOKENS_TS}


def fe_css() -> List[Path]:
    return sorted(FE_SRC.rglob("*.css"))


def static_css() -> List[Path]:
    return sorted(
        p for p in STATIC.rglob("*.css") if "dist" not in p.relative_to(STATIC).parts[:1]
        and "vendor" not in p.relative_to(STATIC).parts[:1]
    )


def templates() -> List[Path]:
    return sorted(TEMPLATES.glob("*.html"))


def handwritten_styles() -> List[Path]:
    return fe_css() + static_css() + templates()


def _read(paths: Iterable[Path]) -> List[Tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in paths]


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", text)


# --------------------------------------------------------------------------
# C10.05 scanners
# --------------------------------------------------------------------------
PRIMITIVE_REF_RE = re.compile(r"var\(\s*--p-")
AUTO_SELECTOR_RE = re.compile(r"\[\s*data-reading-theme\s*[~|^$*]?=\s*[\"']?auto\b")
DARK_BLOCK_RE = re.compile(
    r"prefers-color-scheme\s*:\s*dark|\[\s*data-theme\s*=\s*[\"']?dark\b"
)


def count_hits(regex: re.Pattern[str], files: Sequence[Tuple[Path, str]]) -> List[str]:
    hits = []
    for path, text in files:
        for m in regex.finditer(_strip_comments(text)):
            hits.append(f"{path}:{m.group(0)}")
    return hits


def component_styles() -> List[Path]:
    return [p for p in handwritten_styles() if p not in TOKEN_DEFINITION_FILES]


def test_no_primitive_refs_in_components(tmp_path: Path) -> None:
    assert TOKENS_CSS.is_file(), "the Tier 1 palette file frontend/src/styles/tokens.css does not exist"
    assert re.search(r"--p-[a-z0-9-]+\s*:", TOKENS_CSS.read_text(encoding="utf-8")), (
        "tokens.css defines no --p-* palette entry"
    )
    files = _read(component_styles())
    assert files, "no component stylesheet was scanned"
    assert count_hits(PRIMITIVE_REF_RE, files) == []

    seed = tmp_path / "seed.css"
    seed.write_text(".x { color: var(--p-gray-800); }\n", encoding="utf-8")
    assert len(count_hits(PRIMITIVE_REF_RE, _read([seed]))) == 1


def test_no_auto_selector(tmp_path: Path) -> None:
    dist = th.dist_css_files()
    dist_text = "".join(p.read_text(encoding="utf-8") for p in dist)
    assert re.search(r"data-reading-theme\s*=\s*[\"']?paper", dist_text), (
        "the built CSS has no reading-axis rule at all; the absence check would be vacuous"
    )
    assert count_hits(AUTO_SELECTOR_RE, _read(handwritten_styles() + dist)) == []

    seed = tmp_path / "seed.css"
    seed.write_text('html[data-reading-theme="auto"] .reader-shell { --r3-page-bg: #fff; }\n', encoding="utf-8")
    assert len(count_hits(AUTO_SELECTOR_RE, _read([seed]))) == 1


def test_no_handwritten_dark_block(tmp_path: Path) -> None:
    dist_text = "".join(p.read_text(encoding="utf-8") for p in th.dist_css_files())
    assert re.search(r"prefers-color-scheme\s*:\s*dark", dist_text), "the built CSS has no system-dark rule"
    assert re.search(r"\[\s*data-theme\s*=\s*[\"']?dark", dist_text), "the built CSS has no explicit-dark rule"
    assert count_hits(DARK_BLOCK_RE, _read(handwritten_styles())) == []

    for body in (
        '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --r3-bg: #000; } }\n',
        ':root[data-theme="dark"] { --r3-bg: #000; }\n',
    ):
        seed = tmp_path / "seed.css"
        seed.write_text(body, encoding="utf-8")
        assert len(count_hits(DARK_BLOCK_RE, _read([seed]))) == 1


# --------------------------------------------------------------------------
# C10.06 duration/ease pairing
# --------------------------------------------------------------------------
MOTION_DECL_RE = re.compile(
    r"(?<![\w-])(transition|transition-duration|animation|animation-duration)\s*:\s*([^;{}\"]*)"
)
DURATION_RE = re.compile(r"var\(\s*--r3-duration-[a-z]+\s*\)")
EASE_RE = re.compile(r"var\(\s*--r3-ease-[a-z]+\s*\)")


def split_top_level(value: str) -> List[str]:
    parts, depth, cur = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def pairing_violations(text: str) -> List[Tuple[str, int, str]]:
    """(property, segment index, segment) for every segment with a duration and no ease."""
    out = []
    for m in MOTION_DECL_RE.finditer(_strip_comments(text)):
        prop, value = m.group(1), m.group(2)
        segments = [value] if prop.endswith("-duration") else split_top_level(value)
        for i, seg in enumerate(segments):
            if DURATION_RE.search(seg) and not EASE_RE.search(seg):
                out.append((prop, i, seg.strip()))
    return out


def test_duration_paired_with_ease() -> None:
    files = _read(handwritten_styles())
    legacy = [f"{p}" for p, text in files for _ in re.finditer(r"var\(\s*--dedao-transition-", text)]
    assert legacy == [], f"{len(legacy)} var(--dedao-transition-*) references remain"
    violations = [(str(p), v) for p, text in files for v in pairing_violations(text)]
    assert violations == []
    uses = sum(len(DURATION_RE.findall(_strip_comments(text))) for _, text in files)
    assert uses > 0, "no stylesheet references a --r3-duration-* token; the pairing check is vacuous"


def test_pairing_is_per_segment_seed() -> None:
    text = ".a { transition: opacity var(--r3-duration-fast), color var(--r3-duration-fast) var(--r3-ease-standard); }"
    assert pairing_violations(text) == [("transition", 0, "opacity var(--r3-duration-fast)")]
    text = ".b { transition: transform var(--r3-duration-normal) cubic-bezier(0.2, 0, 0, 1); }"
    assert [v[1] for v in pairing_violations(text)] == [0]


segment_spec = st.tuples(
    st.sampled_from(["all", "opacity", "transform", "color", "width"]),
    st.sampled_from([None, "fast", "normal", "slow", "150ms"]),
    st.sampled_from([None, "standard", "decelerate", "accelerate", "ease", "cubic-bezier(0.3, 0, 1, 1)"]),
)


def _render(spec: Tuple[str, object, object]) -> str:
    prop, dur, ease = spec
    parts = [prop]
    if dur is not None:
        parts.append(f"var(--r3-duration-{dur})" if dur in ("fast", "normal", "slow") else str(dur))
    if ease is not None:
        parts.append(f"var(--r3-ease-{ease})" if ease in ("standard", "decelerate", "accelerate") else str(ease))
    return " ".join(parts)


@settings(max_examples=300, deadline=None)
@given(st.lists(segment_spec, min_size=1, max_size=5))
def test_pairing_matches_segment_oracle(specs: List[Tuple[str, object, object]]) -> None:
    decl = ", ".join(_render(s) for s in specs)
    expected = [
        i
        for i, (_, dur, ease) in enumerate(specs)
        if dur in ("fast", "normal", "slow") and ease not in ("standard", "decelerate", "accelerate")
    ]
    assert [v[1] for v in pairing_violations(f".x {{ transition: {decl}; }}")] == expected
