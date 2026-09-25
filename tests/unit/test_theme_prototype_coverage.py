"""013 WI-10 A10.13 (C10.07) and A10.14 (C10.08): the prototype translation tables.

The two tables stay where the plan defines them -- `plan-frontend-ui-refactor.md`
§10.1 (43 prototype variables -> `--r3-*`) and §10.1.1 (13 prototype z-index sites ->
nine tiers). This test parses them rather than keeping a second copy (Risk C-15: a
copy would be a second author of the same mapping).

C10.07: the left column of §10.1, expanded, equals the set of custom properties the
prototype `designs/reader-pro-next/index.html` defines -- 43, with both set
differences empty. Every row either names `--r3-*` targets that the built CSS defines,
or says 「不进 Tier 2」 with a reason.

C10.08: §10.1.1 has 13 rows; each cites a prototype line whose `z-index` literal equals
the row's value, the 13 cited lines are exactly the prototype's z-index sites, and each
maps to one of the nine tiers; the nine tiers are defined once, with the spec §3.5.1
values, in strictly increasing order; and no frontend stylesheet has a bare
`z-index: <number>` (seeded copy goes red).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import shell_4a_theme as th

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / "docs" / "plans" / "20260817-frontend-ui-refactor" / "plan-frontend-ui-refactor.md"
PROTOTYPE = REPO / "designs" / "reader-pro-next" / "index.html"
FE_SRC = REPO / "frontend" / "src"
TOKENS_CSS = FE_SRC / "styles" / "tokens.css"

NOT_TIER2 = "不进 Tier 2"

#: spec §3.5.1, in the required order.
Z_TIERS: Tuple[Tuple[str, int], ...] = (
    ("--r3-z-base", 0),
    ("--r3-z-raised", 10),
    ("--r3-z-sticky", 100),
    ("--r3-z-panel", 200),
    ("--r3-z-overlay", 300),
    ("--r3-z-toolbar", 400),
    ("--r3-z-popover", 500),
    ("--r3-z-toast", 600),
    ("--r3-z-skip", 700),
)


def _section(start: str, end: str) -> List[str]:
    text = PLAN.read_text(encoding="utf-8")
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b].splitlines()


def _cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _expand(tokens: List[str]) -> List[str]:
    """`--anno-yellow` / `-green` -> [--anno-yellow, --anno-green]."""
    out: List[str] = []
    base: Optional[str] = None
    for tok in tokens:
        if tok.startswith("--"):
            out.append(tok)
            base = tok.rsplit("-", 1)[0]
        else:
            assert base is not None and tok.startswith("-"), f"suffix {tok!r} with no base"
            out.append(base + tok)
    return out


def mapping_rows() -> List[Tuple[List[str], Optional[List[str]], str]]:
    rows = []
    for line in _section("#### 10.1 原型变量", "#### 10.1.1"):
        if not line.startswith("| `--"):
            continue
        left, right, note = _cells(line)[:3]
        lefts = _expand(re.findall(r"`(-{1,2}[a-z0-9-]+)`", left))
        if NOT_TIER2 in right:
            rows.append((lefts, None, note))
            continue
        if right.startswith("同名"):
            pattern = re.search(r"`(--r3-[a-z0-9-]+)\*`", right)
            assert pattern, f"unreadable 同名 row: {line}"
            targets = ["--r3-" + name[2:] for name in lefts]
        else:
            targets = _expand(re.findall(r"`(-{1,2}[a-z0-9-]+)`", right))
        rows.append((lefts, targets, note))
    return rows


def prototype_vars() -> List[str]:
    text = PROTOTYPE.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", text, re.MULTILINE)))


def test_43_vars_mapped() -> None:
    rows = mapping_rows()
    assert rows, "§10.1 table not found"
    left = [name for lefts, _, _ in rows for name in lefts]
    assert len(left) == len(set(left)), f"a prototype variable is mapped twice: {left}"
    proto = prototype_vars()
    assert len(proto) == 43
    assert sorted(set(proto) - set(left)) == [], "prototype variables with no row"
    assert sorted(set(left) - set(proto)) == [], "rows naming no prototype variable"

    defined = set(th.dist_token_names())
    unresolved: Dict[str, List[str]] = {}
    for lefts, targets, note in rows:
        if targets is None:
            assert note, f"{lefts} is marked {NOT_TIER2} without a reason"
            continue
        assert len(targets) in (1, len(lefts)), f"{lefts} -> {targets}: arity mismatch"
        for t in targets:
            assert t.startswith("--r3-"), f"{lefts} maps to a non-Tier-2 name {t}"
            if t not in defined:
                unresolved.setdefault(t, []).extend(lefts)
    assert unresolved == {}, "mapping targets the built CSS does not define"


Z_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*`:(\d+)`")


def zindex_rows() -> List[Tuple[int, int, str]]:
    rows = []
    for line in _section("#### 10.1.1", "**涉及 testid**"):
        m = Z_ROW_RE.match(line)
        if not m:
            continue
        tokens = re.findall(r"`(--r3-z-[a-z]+)`", _cells(line)[-1])
        assert len(tokens) == 1, f"row must name exactly one tier: {line}"
        rows.append((int(m.group(1)), int(m.group(2)), tokens[0]))
    return rows


def _tier_values() -> Dict[str, int]:
    assert TOKENS_CSS.is_file(), "frontend/src/styles/tokens.css does not exist"
    text = TOKENS_CSS.read_text(encoding="utf-8")
    found = re.findall(r"(--r3-z-[a-z]+)\s*:\s*(-?\d+)\s*;", text)
    names = [n for n, _ in found]
    assert len(names) == len(set(names)), f"a z tier is defined twice: {names}"
    return {n: int(v) for n, v in found}


def test_13_zindex_mapped() -> None:
    rows = zindex_rows()
    assert len(rows) == 13
    proto_lines = PROTOTYPE.read_text(encoding="utf-8").splitlines()
    proto_sites = {
        i + 1: int(m.group(1))
        for i, line in enumerate(proto_lines)
        for m in [re.search(r"z-index:\s*(\d+)", line)]
        if m
    }
    assert len(proto_sites) == 13
    assert sorted(line for _, line, _ in rows) == sorted(proto_sites)
    for value, line, _ in rows:
        assert proto_sites[line] == value, f"row cites :{line} with value {value}, prototype has {proto_sites[line]}"

    tiers = _tier_values()
    assert tiers == dict(Z_TIERS)
    ordered = [tiers[name] for name, _ in Z_TIERS]
    assert ordered == sorted(ordered) and len(set(ordered)) == 9
    assert {tok for _, _, tok in rows} <= set(tiers)
    # The two role traps §10.1.1 names: 55 is a panel at :560 but an overlay at :775.
    by_line = {line: tok for _, line, tok in rows}
    assert by_line[560] == "--r3-z-panel" and by_line[775] == "--r3-z-overlay"
    assert by_line[179] == "--r3-z-skip"


BARE_Z_RE = re.compile(r"z-index\s*:\s*-?\d")


def bare_zindex_hits(paths: List[Path]) -> List[str]:
    hits = []
    for p in paths:
        text = re.sub(r"/\*[\s\S]*?\*/", "", p.read_text(encoding="utf-8"))
        hits += [f"{p}:{m.group(0)}" for m in BARE_Z_RE.finditer(text)]
    return hits


def test_no_bare_zindex_in_frontend(tmp_path: Path) -> None:
    css = sorted(FE_SRC.rglob("*.css"))
    assert TOKENS_CSS in css
    assert bare_zindex_hits(css) == []
    seed = tmp_path / "seed.css"
    seed.write_text(".x { z-index: 999; }\n.y { z-index: var(--r3-z-toast); }\n", encoding="utf-8")
    assert len(bare_zindex_hits([seed])) == 1
