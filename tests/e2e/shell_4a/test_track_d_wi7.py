"""013 WI-10 hosts Track-D WI-7 #1-#3 (fold-in rows 28-30; C10.16-C10.18; A10.D1-D3).

The contract (source plan WI-7, :584-:587) is an alpha contract: the highlight colours
are stored as RGB triplets (`--r3-hl-*-rgb`, defined by WI-10 per spec §3.2 / §3.3) and
the alpha lives at the point of use, `rgb(var(--r3-hl-X-rgb) / <alpha>)`.

The nine roles (plan WI-7 table; the prototype selectors are only code names):

    1-4  notes chip x four colours           alpha .35   (new; lives with the notes panel)
    5-8  marker highlight x four colours     alpha .45   (today: literal rgba in static annotations.css)
    9    note mark background                alpha .18   (today: no background at all; must not be brand blue)

**Split verdict (C-8a, user-signed).** All nine live on the reader side (the notes panel
and `annotations.css`), whose move into `{前端源码根}` is 014 WI-16. In 013 none is
present in `frontend/src`, so each role is either PRESENT in the frontend CSS and then
checked in full, or listed in `PINNED_TO_014` -- never both, never neither. When 014
writes one, it must delete the pin in the same change, or `test_nine_roles_rgb_var_alpha`
goes red on the overlap. That is what keeps the pin list from being an unbounded
escape hatch.

These are static checks (no browser); they sit in `shell_4a` because the fold-in table
names this node id, and carry the `track_d_013` marker the 34-item ledger selects on.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, get_args

import pytest

from reader3_app.models.annotations import MarkerColor

pytestmark = [pytest.mark.shell_4a, pytest.mark.track_d_013]

REPO = Path(__file__).resolve().parents[3]
FE_SRC = REPO / "frontend" / "src"
THEME_TOKENS_TS = FE_SRC / "shared" / "theme-tokens.ts"
TOKENS_CSS = FE_SRC / "styles" / "tokens.css"
TOKEN_LINT = REPO / "scripts" / "lint_token_refs.py"

COLORS: Tuple[str, ...] = ("yellow", "green", "pink", "blue")


class Role(NamedTuple):
    name: str
    selector_re: str  # matched against one selector of a rule's selector list
    alpha: str


ROLES: Tuple[Role, ...] = (
    *(Role(f"chip-{c}", rf"\.note-chip\.is-{c}\b", ".35") for c in COLORS),
    *(
        Role(f"marker-{c}", rf"mark\.annotation\.annotation--marker\.annotation--{c}\b", ".45")
        for c in COLORS
    ),
    Role("note", r"mark\.annotation\.annotation--note\b", ".18"),
)
ROLE_NAMES = {r.name for r in ROLES}

#: role -> the 014 work item that writes it (C-8a split verdict).
PINNED_TO_014: Dict[str, str] = {
    **{f"chip-{c}": "014 WI-16 (notes panel into the frontend root)" for c in COLORS},
    **{f"marker-{c}": "014 WI-16 (annotations.css into the frontend root)" for c in COLORS},
    "note": "014 WI-16 (annotations.css into the frontend root)",
}

LITERAL_COLOR_RE = re.compile(
    r"color-mix\(|#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b|rgba?\(\s*[\d.]"
)
BACKGROUND_DECL_RE = re.compile(r"(?<![\w-])(background(?:-color)?)\s*:\s*([^;}]*)")


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", text)


def css_rules(text: str) -> List[Tuple[str, str]]:
    """(selector list, body) for every innermost `{...}` block; @media wrappers are looked through."""
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", _strip_comments(text))
    ]


def role_declarations(paths: List[Path]) -> Dict[str, List[Tuple[Path, str]]]:
    """role name -> [(file, background value)] for every rule whose selector names that role."""
    found: Dict[str, List[Tuple[Path, str]]] = {}
    for path in paths:
        for selectors, body in css_rules(path.read_text(encoding="utf-8")):
            for sel in selectors.split(","):
                for role in ROLES:
                    if re.search(role.selector_re + r"(?![\w-])", sel.strip()):
                        for m in BACKGROUND_DECL_RE.finditer(body):
                            found.setdefault(role.name, []).append((path, m.group(2).strip()))
    return found


def literal_color_hits(paths: List[Path]) -> List[str]:
    return [
        f"{p}: {role}: {value}"
        for role, decls in role_declarations(paths).items()
        for p, value in decls
        if LITERAL_COLOR_RE.search(value)
    ]


def fe_css() -> List[Path]:
    return sorted(FE_SRC.rglob("*.css"))


def test_no_literal_colors_in_nine_roles(tmp_path: Path) -> None:
    css = fe_css()
    assert css, "no stylesheet under frontend/src; the scan would be vacuous by absence of files"
    assert literal_color_hits(css) == []

    seed = tmp_path / "seed.css"
    seed.write_text(
        "mark.annotation.annotation--marker.annotation--yellow { background: rgba(255, 229, 143, 0.75); }\n"
        ".note-chip.is-green { background: color-mix(in srgb, #4ade80 35%, transparent); }\n"
        "mark.annotation.annotation--note { background: rgb(var(--r3-hl-pink-rgb) / .18); }\n",
        encoding="utf-8",
    )
    assert len(literal_color_hits([seed])) == 2


ROLE_FORM_RE = re.compile(r"^rgb\(\s*var\(\s*--r3-hl-([a-z]+)-rgb\s*\)\s*/\s*(0?\.\d+)\s*\)$")


def role_form_problems(role: Role, values: List[str]) -> List[str]:
    problems = []
    for value in values:
        m = ROLE_FORM_RE.match(value)
        if not m:
            problems.append(f"{role.name}: {value!r} is not rgb(var(--r3-hl-*-rgb) / <alpha>)")
            continue
        color, alpha = m.group(1), m.group(2)
        if float(alpha) != float(role.alpha):
            problems.append(f"{role.name}: alpha {alpha} != {role.alpha}")
        expected: Optional[str] = role.name.split("-", 1)[1] if "-" in role.name else None
        if expected is not None and color != expected:
            problems.append(f"{role.name}: uses the {color} token")
        if role.name == "note" and color == "blue":
            problems.append("note: uses the blue token, which collides with the brand accent")
    return problems


def test_nine_roles_rgb_var_alpha(tmp_path: Path) -> None:
    assert len(ROLES) == 9 and set(PINNED_TO_014) <= ROLE_NAMES
    present = role_declarations(fe_css())
    overlap = sorted(set(present) & set(PINNED_TO_014))
    assert overlap == [], f"roles written in frontend/src but still pinned to 014: {overlap}"
    assert set(present) | set(PINNED_TO_014) == ROLE_NAMES
    problems = [
        p for role in ROLES if role.name in present for p in role_form_problems(role, [v for _, v in present[role.name]])
    ]
    assert problems == []

    # The form check can fail: the alpha swap, the wrong colour, the brand-blue note.
    seed = tmp_path / "seed.css"
    seed.write_text(
        ".note-chip.is-yellow { background: rgb(var(--r3-hl-yellow-rgb) / .45); }\n"
        "mark.annotation.annotation--marker.annotation--pink { background: rgb(var(--r3-hl-blue-rgb) / .45); }\n"
        "mark.annotation.annotation--note { background: rgb(var(--r3-hl-blue-rgb) / .18); }\n"
        "mark.annotation.annotation--marker.annotation--green { background: rgb(var(--r3-hl-green-rgb) / .45); }\n",
        encoding="utf-8",
    )
    seeded = role_declarations([seed])
    by_role = {r.name: r for r in ROLES}
    assert {name: len(role_form_problems(by_role[name], [v for _, v in decls])) for name, decls in seeded.items()} == {
        "chip-yellow": 1,
        "marker-pink": 1,
        "note": 1,
        "marker-green": 0,
    }


def _declared_hl_colors(text: str, prefix: str, suffix: str = "-rgb") -> List[str]:
    return sorted(set(re.findall(rf"{prefix}-hl-([a-z]+){suffix}[\"']?\s*:", text)))


def test_token_lint_and_colorset_eq_markercolor() -> None:
    markers = sorted(get_args(MarkerColor))
    assert markers == sorted(COLORS)
    assert THEME_TOKENS_TS.is_file() and TOKENS_CSS.is_file()
    assert _declared_hl_colors(THEME_TOKENS_TS.read_text(encoding="utf-8"), "--r3") == markers
    palette = TOKENS_CSS.read_text(encoding="utf-8")
    assert _declared_hl_colors(palette, "--p") == markers
    assert _declared_hl_colors(palette, "--p", "-dk-rgb") == markers

    proc = subprocess.run(
        [sys.executable, str(TOKEN_LINT)], cwd=REPO, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
