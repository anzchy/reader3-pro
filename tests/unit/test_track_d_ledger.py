"""013 WI-13 A13.10 / C13.31: the Track-D ledger equals the plan markers.

The plan (`plan-frontend-ui-refactor.md` §4, WI-1..WI-8) marks 34 acceptance rows
`【实现类·前置 WI-9·验于 013】`. Each row is split into halves: `library` and `reader` for
the four rows that name both pages, `all` otherwise. Every (row, half) pair is exactly one of:

* **collected** -- a pytest test function (docstring) or a Vitest `it(...)` title carrying the
  tag `[track_d_013 WI-n#m]` (half `all`) or `[track_d_013 WI-n#m/library]`; plus the three
  WI-10 tests of `tests/e2e/shell_4a/test_track_d_wi7.py`, named by node id in `EXISTING`;
* **pinned** -- an entry of `tests/fixtures/track_d_pinned_014.json`.

Laws: the regex finds exactly 34 rows; collected + pinned == required; the sources are
pairwise disjoint; pinned is a subset of `C8_SET`; a pinned C-8 reader half has a collected
library half; every C-8 pin names a WI. A skipped / xfailed / `.todo` / `.skip` test is not
collected (it would count as covered without running).

C13.34 (executed-and-passed from fresh artefacts) is not implemented here; its absence is
reported, not faked.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / "docs" / "plans" / "20260817-frontend-ui-refactor" / "plan-frontend-ui-refactor.md"
PINNED = REPO / "tests" / "fixtures" / "track_d_pinned_014.json"
#: The cross-wave debt register (`### 跨波欠账`); 012's opening list is copied from it (migration plan §9).
REGISTER = REPO / "docs" / "plans" / "20260816-tech-stack-migration" / "tasks" / "009-e2e-annotations.md"

ROW_RE = re.compile(r"^\s*(\d+)\.\s*【实现类·前置 WI-9·验于 013】", re.M)
# RV-15: an inserted WI carries a one-letter suffix (`WI-16b`); the heading regex accepts it so a
# marked row under such a heading is never attributed to the WI before it.
WI_HEADING_RE = re.compile(r"^#{2,4}\s*WI-(\d+[a-z]?)\b", re.M)
TAG_RE = re.compile(r"\[track_d_013 (WI-\d+#\d+)(?:/(library|reader))?\]")

#: Rows whose text names both pages; everything else is a single `all` half.
TWO_HALF_ROWS = frozenset({"WI-3#5", "WI-4#1", "WI-4#2", "WI-4#7"})

Pair = Tuple[str, str]

#: C-8 (user-signed) plus ruling D12 (2026-09-25). Pinning outside this set is refused.
C8_ONLY: frozenset = frozenset(
    {("WI-7#1", "all"), ("WI-7#2", "all"), ("WI-3#5", "reader"), ("WI-4#1", "reader"), ("WI-4#7", "reader")}
)
D12_SET: frozenset = frozenset(
    {(f"WI-4#{n}", h) for n in (1, 2, 7) for h in ("library", "reader")}
    | {(f"WI-4#{n}", "all") for n in (3, 4, 5, 6)}
    | {(f"WI-5#{n}", "all") for n in range(1, 7)}
    | {("WI-8#4", "all")}
)
C8_SET: frozenset = C8_ONLY | D12_SET

#: WI-10 tests that predate the tag convention (node ids; C10.16-C10.18).
EXISTING: Dict[Pair, str] = {
    ("WI-7#1", "all"): "tests/e2e/shell_4a/test_track_d_wi7.py::test_no_literal_colors_in_nine_roles",
    ("WI-7#2", "all"): "tests/e2e/shell_4a/test_track_d_wi7.py::test_nine_roles_rgb_var_alpha",
    ("WI-7#3", "all"): "tests/e2e/shell_4a/test_track_d_wi7.py::test_token_lint_and_colorset_eq_markercolor",
}

SKIP_MARKS = ("skip", "skipif", "xfail")
VITEST_TITLE_RE = re.compile(
    r"\b(?:it|test)(?:\.each\((?:[^()]|\([^()]*\))*\))?\(\s*([\"'`])((?:(?!\1).)*)\1", re.S
)


def plan_rows(text: str) -> List[str]:
    """`WI-n#m` for every marked row, by the enclosing WI heading."""
    headings = [(m.start(), m.group(1)) for m in WI_HEADING_RE.finditer(text)]
    rows = []
    for m in ROW_RE.finditer(text):
        wi = [n for pos, n in headings if pos < m.start()]
        assert wi, f"marked row at offset {m.start()} has no enclosing WI heading"
        rows.append(f"WI-{wi[-1]}#{m.group(1)}")
    return rows


def required_pairs(rows: List[str]) -> Set[Pair]:
    out: Set[Pair] = set()
    for r in rows:
        out |= {(r, "library"), (r, "reader")} if r in TWO_HALF_ROWS else {(r, "all")}
    return out


def _tags(text: str) -> List[Pair]:
    return [(m.group(1), m.group(2) or "all") for m in TAG_RE.finditer(text)]


def _is_skipped(fn: ast.AST) -> bool:
    for dec in getattr(fn, "decorator_list", []):
        src = ast.unparse(dec)
        if any(f"mark.{m}" in src for m in SKIP_MARKS):
            return True
    return False


def pytest_collected(root: Path) -> Dict[Pair, List[str]]:
    out: Dict[Pair, List[str]] = {}
    for path in sorted((root / "tests").rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_skipped = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
            and any(f"mark.{m}" in ast.unparse(node.value) for m in SKIP_MARKS)
            for node in tree.body
        )
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                doc = ast.get_docstring(node) or ""
                if module_skipped or _is_skipped(node):
                    continue
                for pair in _tags(doc):
                    out.setdefault(pair, []).append(f"{path.relative_to(root).as_posix()}::{node.name}")
    return out


def vitest_collected(root: Path) -> Dict[Pair, List[str]]:
    out: Dict[Pair, List[str]] = {}
    for path in sorted((root / "frontend" / "tests").rglob("*.test.ts")):
        text = path.read_text(encoding="utf-8")
        for m in VITEST_TITLE_RE.finditer(text):
            for pair in _tags(m.group(2)):
                out.setdefault(pair, []).append(f"{path.relative_to(root).as_posix()}: {m.group(2)[:60]}")
    return out


def load_pins() -> List[dict]:
    return json.loads(PINNED.read_text(encoding="utf-8"))["pinned"]


# SEPARATION-BROKEN (013 WI-13, coordinator-approved): the two laws below were inline in
# `test_ledger_equals_plan_markers` and are now helpers with a D12 carve-out. As first written
# they contradicted ruling D12: D12 defers WI-4#1 / WI-4#7 **both halves** (routes absent, HTTP
# API frozen), so "a pinned C-8 reader half has a collected library half" could not hold, and
# the D12 target "012 (routes) / 014 (UI acceptance)" names no `WI-n`. The carve-out is scoped
# strictly to D12-tagged pins (pair in `D12_SET` *and* the reason cites D12); every other pin is
# held to the original laws, and `test_non_d12_*` below prove that they still bite.
D12_TARGET = "012 (routes) / 014 (UI acceptance)"

# Ruling R2 (2026-09-25, RV-11): `D12_TARGET` above is now the *refused* legacy form. A D12 pin
# names an address: a 014 WI (UI acceptance) and/or a debt-register id (route). The register
# is `REGISTER`.
# 018 WI-1 (2026-09-30, spec §6 Q1): 2026-09-26 ruling D1 moved #51 / #53 / #56 / #58 from 012 to
# 018, so a route address is `012 debt #N` or `018 debt #N`. Generalised, not loosened: the cited
# row's owner column (兑付方) must parse to a branch number that is allocated in the migration plan
# §9 and *equals* the citation prefix. The old check was `"012" in owner`, a substring test that
# `0120-x` or a narrative 「可能 012」 passed.
WI_RE = re.compile(r"\bWI-(\d+)(?:[a-z])?\b")  # RV-15: `WI-16b` counts as its number (16, inside 014)
WI_014 = frozenset(range(14, 20))  # 014-ts-frontend-reader owns WI-14 – WI-19 (plan §4)
DEBT_RE = re.compile(r"\b(012|018) debt #(\d+)\b")
REGISTER_HEADER = "| # | 欠什么 |"
#: The branch-number table (`## 9.`, column 分支) is the single definition of allocated numbers.
MIGRATION_PLAN = REPO / "docs" / "plans" / "20260816-tech-stack-migration" / "plan-tech-stack-migration.md"
#: Owner-cell grammar (`parse_owner_branch`): struck spans are history; the owner is the first bold
#: span, and the grammar is anchored to that *whole* span (`fullmatch`, fix-plan WI-6 / #7): `NNN`,
#: `NNN-slug` or `[NNN WI-x](link)`, each optionally followed by ` <narrative…>` (so `NNN 后端重构`,
#: `NNN-slug (…)`). 3 ASCII digits followed by anything else (`012→…`, `018x`, `[018x WI-7]`) is None.
STRIKE_RE = re.compile(r"~~.*?~~", re.S)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
OWNER_BRANCH_RE = re.compile(
    r"(?=\[?([0-9]{3}))(?:\[[0-9]{3} WI-[^\]\s]+\]\([^)\s]*\)|[0-9]{3}(?:-[a-z0-9-]+)?)(?: .*)?",
    re.ASCII | re.S,
)


def d12_target_has_address(target: str) -> bool:
    return bool(DEBT_RE.search(target)) or any(int(n) in WI_014 for n in WI_RE.findall(target))


def register_owners(text: str) -> Dict[int, str]:
    """`{debt number: owner cell}` for the rows of the register table (header `| # | 欠什么 |`)."""
    out: Dict[int, str] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith(REGISTER_HEADER):
            in_table = True
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if in_table and len(cells) >= 4 and cells[0].isdigit():
            out[int(cells[0])] = cells[3]
    return out


def parse_owner_branch(cell: str) -> Optional[str]:
    """The 3-digit branch number an owner cell (兑付方) names, or None when it names none.

    Every `~~…~~` span is struck history and is removed first, wherever it sits. The owner is the
    first remaining `**…**` span, and the number must *start* it: `**012-storage-format**`,
    `**011**`, `**011 后端重构**`, `**[018 WI-7](…)**`. A 4-digit run, a prefixed number
    (`**v012-x**`, `**待定 012**`), a number in a later bold span or only in narrative is None.
    """
    first = BOLD_RE.search(STRIKE_RE.sub("", cell))
    if first is None:
        return None
    m = OWNER_BRANCH_RE.fullmatch(first.group(1))
    return m.group(1) if m else None


def allocated_branches(text: str) -> Set[str]:
    """`NNN` of every backticked `NNN-slug` in the 分支 column of the `## 9.` tables, and nothing else."""
    m = re.search(r"^## 9\.[^\n]*$", text, re.M)
    if m is None:
        return set()
    end = re.search(r"^## ", text[m.end():], re.M)
    section = text[m.end(): m.end() + end.start()] if end else text[m.end():]
    out: Set[str] = set()
    col: Optional[int] = None
    for line in section.splitlines():
        if not line.startswith("|"):
            col = None
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if col is None:
            col = cells.index("分支") if "分支" in cells else -1
            continue
        if col < 0 or col >= len(cells) or set(cells[col]) <= set("-: "):
            continue
        out.update(re.findall(r"`(\d{3})-[a-z0-9-]+`", cells[col], re.ASCII))
    return out


def debt_citation_problems(pins: List[dict], owners: Dict[int, str], allocated: Set[str]) -> List[str]:
    """One problem per `(012|018) debt #N` citation that does not resolve exactly.

    A citation resolves when row N is in the register, its owner cell parses
    (`parse_owner_branch`), the parsed branch is allocated in §9, and it equals the citation
    prefix. Only cited rows are parsed: a 「待定」 or free-text owner elsewhere is out of scope.
    """
    out = []
    for p in pins:
        where = f"{p['row']}/{p['half']}"
        for prefix, num in DEBT_RE.findall(p["target"]):
            n = int(num)
            owner = owners.get(n)
            if owner is None:
                out.append(f"{where}: {prefix} debt #{n} is not in the register")
                continue
            branch = parse_owner_branch(owner)
            if branch is None:
                out.append(f"{where}: {prefix} debt #{n}: owner {owner!r} names no branch number")
            elif branch not in allocated:
                out.append(f"{where}: {prefix} debt #{n} is owned by {branch}, which §9 has not allocated")
            elif branch != prefix:
                out.append(f"{where}: {prefix} debt #{n} is owned by {branch}, not {prefix}")
    return out


def is_d12_pin(p: dict) -> bool:
    return (p["row"], p["half"]) in D12_SET and "D12" in p.get("reason", "")


def unpaired_reader_halves(pins: List[dict], covered: Set[Pair]) -> List[Pair]:
    """C-8 reader halves that are pinned while their library half is neither tested nor D12-pinned."""
    by_pair = {(p["row"], p["half"]): p for p in pins}
    out = []
    for (r, h) in by_pair:
        if h != "reader" or (r, h) not in C8_ONLY or (r, "library") in covered:
            continue
        lib = by_pair.get((r, "library"))
        if lib is not None and is_d12_pin(lib):
            continue
        out.append((r, h))
    return sorted(out)


def pin_owner_problem(p: dict) -> "str | None":
    """None when the pin names an owner the ledger accepts; otherwise the reason it does not."""
    # 013 final review (RV-2): the branch-level forms (D12_TARGET, or any target naming 014) are
    # licensed by citing D12 and nothing else. A D12_SET pair whose reason does not cite D12 used
    # to fall through to the bare `"014" in target` check; it now meets the normal rule below.
    # Ruling R2 (2026-09-25, RV-11) withdrew that licence: citing D12 no longer admits a branch.
    if is_d12_pin(p):
        if d12_target_has_address(p["target"]):
            return None
        return f"D12 pin must name its owner: {p}"
    if not re.search(r"\bWI-\d+[a-z]?\b", p["target"]):
        kind = "C-8" if (p["row"], p["half"]) in C8_ONLY else "non-D12"
        return f"{kind} pin must name a WI: {p}"
    return None


# RV-15 (2026-09-25, user ruling relayed by reader-a2): 014 had no library-page WI, so R2 parked
# the library-side UI acceptance of every D12 pin on WI-16 (the reader shell). The ruling opens a
# dedicated library WI inside 014, `WI-16b` (inserted after WI-16 without renumbering; same
# suffix convention as 011's WI-0a / WI-5b), and hands it all 17 D12 pins. `pin_owner_problem`
# above stays the R2 *address-form* law; the law below is about *which* WI owns the UI half:
# a library-side D12 pin (half `library` or `all`) names `LIBRARY_WI` and no other WI; a reader
# half names `LIBRARY_WI` or a 014 WI (`WI-14`..`WI-19`).
LIBRARY_WI = "WI-16b"
LIBRARY_HALVES = frozenset({"library", "all"})
WI_ID_RE = re.compile(r"(?<![\w-])(WI-\d+[a-z]?)\b")


def wi_ids(target: str) -> List[str]:
    """Every WI id a target names, suffix included (`WI-16b` is not `WI-16`)."""
    return WI_ID_RE.findall(target)


def d12_ui_owner_problem(p: dict) -> "str | None":
    """None when a D12 pin's UI-acceptance owner is the WI the ruling assigns; otherwise why not."""
    ids = wi_ids(p["target"])
    if p["half"] in LIBRARY_HALVES:
        if ids != [LIBRARY_WI]:
            return f"library-side D12 pin must name {LIBRARY_WI} and no other WI: {p}"
        return None
    allowed = {LIBRARY_WI} | {f"WI-{n}" for n in WI_014}
    if not ids or any(i not in allowed for i in ids):
        return f"reader-half D12 pin must name {LIBRARY_WI} or a 014 WI (WI-14..WI-19): {p}"
    return None


# ---------------------------------------------------------------------------
def test_plan_has_exactly_34_marked_rows() -> None:
    rows = plan_rows(PLAN.read_text(encoding="utf-8"))
    assert len(rows) == 34, rows
    assert len(set(rows)) == 34, "two marked rows map to the same (WI, n)"


def test_existing_node_ids_exist() -> None:
    for pair, node in EXISTING.items():
        file, name = node.split("::")
        tree = ast.parse((REPO / file).read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert name in names, f"{pair}: {node} no longer exists"


def test_ledger_equals_plan_markers() -> None:
    """C13.31: collected + pinned == required, pairwise disjoint, pins bounded by C8_SET."""
    required = required_pairs(plan_rows(PLAN.read_text(encoding="utf-8")))
    py = pytest_collected(REPO)
    vi = vitest_collected(REPO)
    ex = set(EXISTING)
    pins = load_pins()
    pinned = {(p["row"], p["half"]) for p in pins}
    assert len(pinned) == len(pins), "a (row, half) is pinned twice"

    tagged = set(py) | set(vi)
    unknown = (tagged | pinned | ex) - required
    assert unknown == set(), f"tags or pins that name no required (row, half): {sorted(unknown)}"

    overlaps = {
        "pytest & vitest": set(py) & set(vi),
        "tagged & existing": tagged & ex,
        "tagged & pinned": tagged & pinned,
        "existing & pinned": ex & pinned,
    }
    assert {k: sorted(v) for k, v in overlaps.items() if v} == {}

    missing = required - tagged - ex - pinned
    assert missing == set(), f"(row, half) neither tested nor pinned: {sorted(missing)}"

    outside = pinned - C8_SET
    assert outside == set(), f"pins outside C-8 / D12: {sorted(outside)}"

    unpaired = unpaired_reader_halves(pins, tagged | ex)
    assert unpaired == [], f"reader halves pinned with no library test: {unpaired}"

    for p in pins:
        assert p.get("reason"), p
        problem = pin_owner_problem(p)
        assert problem is None, problem
        if is_d12_pin(p):
            owner = d12_ui_owner_problem(p)
            assert owner is None, owner


def test_skipped_tests_do_not_count(tmp_path: Path) -> None:
    """Seed: a skipped pytest and an `it.todo` / `it.skip` carry the tag but are not collected."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_seed.py").write_text(
        "import pytest\n"
        "@pytest.mark.skip(reason='x')\n"
        "def test_a():\n    '''[track_d_013 WI-1#1]'''\n"
        "@pytest.mark.xfail(strict=True)\n"
        "def test_b():\n    '''[track_d_013 WI-1#3]'''\n"
        "def test_c():\n    '''[track_d_013 WI-3#5/library]'''\n",
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "tests").mkdir(parents=True)
    (tmp_path / "frontend" / "tests" / "x.test.ts").write_text(
        'it.todo("[track_d_013 WI-3#2] later");\n'
        'it.skip("[track_d_013 WI-3#3] off", () => {});\n'
        'it.each([1, 2])("[track_d_013 WI-3#4] %s", (n) => {});\n',
        encoding="utf-8",
    )
    assert set(pytest_collected(tmp_path)) == {("WI-3#5", "library")}
    assert set(vitest_collected(tmp_path)) == {("WI-3#4", "all")}


def test_row_regex_rejects_the_legend_shapes() -> None:
    legend = "- `【实现类·前置 WI-9·验于 013】` legend\n〔实现类·前置 WI-9〕验于 013 prose\n"
    assert ROW_RE.findall(legend) == []


def test_non_d12_c8_pin_without_a_wi_still_fails() -> None:
    """The D12 carve-out is not a general licence: a C-8 pin not tagged D12 must still name a WI."""
    no_tag = {"row": "WI-7#1", "half": "all", "target": D12_TARGET, "reason": "C-8: deferred"}
    assert pin_owner_problem(no_tag) is not None
    # Same pair as a real D12 pin, but the reason does not cite D12: the target form is refused.
    untagged = {"row": "WI-4#1", "half": "reader", "target": D12_TARGET, "reason": "C-8: later"}
    assert pin_owner_problem(untagged) is not None
    tagged = dict(untagged, reason="D12 (2026-09-25): routes absent")
    # Ruling R2 (2026-09-25): citing D12 no longer licenses the bare branch-level target; the
    # pin must also carry an address (see test_d12_pin_must_name_a_014_wi_or_a_012_debt_id).
    assert pin_owner_problem(tagged) is not None
    assert pin_owner_problem(dict(tagged, target="012 debt #54 / 014 WI-16")) is None
    named = {"row": "WI-3#5", "half": "reader", "target": "014 WI-16", "reason": "C-8"}
    assert pin_owner_problem(named) is None


def test_non_d12_reader_half_without_library_test_still_fails() -> None:
    """WI-3#5's library half is not D12-pinned; pinning its reader half with no library test is unpaired."""
    reader = {"row": "WI-3#5", "half": "reader", "target": "014 WI-16", "reason": "C-8"}
    assert unpaired_reader_halves([reader], set()) == [("WI-3#5", "reader")]
    assert unpaired_reader_halves([reader], {("WI-3#5", "library")}) == []
    # A library half pinned without the D12 tag does not excuse the reader half either.
    r4 = {"row": "WI-4#1", "half": "reader", "target": D12_TARGET, "reason": "C-8"}
    l4 = {"row": "WI-4#1", "half": "library", "target": D12_TARGET, "reason": "deferred"}
    assert unpaired_reader_halves([r4, l4], set()) == [("WI-4#1", "reader")]
    l4_d12 = dict(l4, reason="D12 (2026-09-25): routes absent")
    assert unpaired_reader_halves([r4, l4_d12], set()) == []


def test_d12_set_pin_without_d12_citation_must_name_a_wi() -> None:
    """013 final review (RV-2): the branch-level target form belongs to D12-cited pins only.

    `WI-5#1` is in `D12_SET` but not in `C8_ONLY`. Pinned with a reason that does not cite D12,
    a target that merely contains "014" used to pass; the normal rule (name a `WI-n`) applies.
    """
    uncited = {"row": "WI-5#1", "half": "all", "target": "014", "reason": "DEG-S4: deferred"}
    assert pin_owner_problem(uncited) is not None
    assert pin_owner_problem(dict(uncited, target=D12_TARGET)) is not None
    # Naming a WI satisfies the normal rule without citing D12.
    assert pin_owner_problem(dict(uncited, target="014 WI-16")) is None
    # Ruling R2 (2026-09-25) withdrew the licence this block used to assert: citing D12 no longer
    # admits the branch-level forms ("014", `D12_TARGET`). A D12-cited pin names a WI or a debt id.
    cited = dict(uncited, reason="D12 (2026-09-25): routes absent")
    assert pin_owner_problem(cited) is not None
    assert pin_owner_problem(dict(cited, target=D12_TARGET)) is not None
    assert pin_owner_problem(dict(cited, target="012 debt #55 / 014 WI-16")) is None
    # A D12-cited pin still has to name its owner.
    assert pin_owner_problem(dict(cited, target="later")) is not None


def test_d12_pin_must_name_a_014_wi_or_a_012_or_018_debt_id() -> None:
    """RV-11 (2026-09-25, user ruling R2): a D12 pin names its owner by address, not by branch.

    The branch-level target (`D12_TARGET`, or any target that merely contains "014") said which
    branches owe the row without saying which WI or which debt entry. A D12 pin must name a 014
    WI (`WI-14`..`WI-19`, the UI-acceptance owner) and/or a debt-register id (`012 debt #N` or,
    since 018 WI-1, `018 debt #N`: the route owner). A WI outside 014, or a debt number without
    the `012 debt` / `018 debt` prefix, is no address.
    """
    base = {"row": "WI-5#1", "half": "all", "reason": "D12 (2026-09-25): routes absent"}
    for bare in (D12_TARGET, "014", "012", "012 (routes) / 014", "later", "debt #55", "012 #55",
                 "#55", "013 WI-13", "WI-9", "015 WI-20"):
        assert pin_owner_problem(dict(base, target=bare)) is not None, bare
    for named in ("014 WI-16", "WI-14", "012 debt #55",
                  "012 debt #55 (routes) / 014 WI-16 (UI acceptance)"):
        assert pin_owner_problem(dict(base, target=named)) is None, named
    # 018 WI-1: the same boundaries hold for the 018 prefix; no other branch prefix is an address.
    for bare in ("018 #56", "0180 debt #56", "x018 debt #56", "018 debt #", "019 debt #56"):
        assert pin_owner_problem(dict(base, target=bare)) is not None, bare
    for named in ("018 debt #56", "018 debt #56 (routes) / 014 WI-16b (UI acceptance)"):
        assert pin_owner_problem(dict(base, target=named)) is None, named
    # Only D12 pins are held to the 014 range: a C-8 pin keeps the plain "names a WI" rule.
    assert pin_owner_problem({"row": "WI-3#5", "half": "reader", "target": "014 WI-16", "reason": "C-8"}) is None


def test_register_owners_reads_the_owner_column() -> None:
    """Seed: rows parse by number; an escaped `\\|` inside a cell does not shift the columns."""
    text = (
        "| # | 欠什么 | 欠账方 | 兑付方 | 验收怎么查 | 状态 |\n"
        "|---|---|---|---|---|---|\n"
        "| 7 | a `x \\|\\| y` b | WI-7 | **012-storage-format** | c | 未结清 |\n"
        "| 8 | a | WI-7 | **011** | c | 未结清 |\n"
        "prose | 9 | not a row\n"
    )
    assert register_owners(text) == {7: "**012-storage-format**", 8: "**011**"}


def test_cited_debt_ids_must_resolve_to_rows_owned_by_the_cited_branch() -> None:
    """Seed: a cited id must exist in the register and its owner must parse to the cited branch.

    018 WI-1 renamed this from `…_resolve_to_012_rows`: the owner branch must *equal* the prefix.
    """
    owners = {55: "**012-storage-format**", 18: "**011**", 56: "**018-library-routes**"}
    ok = {"row": "WI-5#1", "half": "all", "target": "012 debt #55 / 014 WI-16", "reason": "D12"}
    assert debt_citation_problems([ok], owners, ALLOCATED) == []
    assert debt_citation_problems([dict(ok, target="018 debt #56 / 014 WI-16b")], owners, ALLOCATED) == []
    assert len(debt_citation_problems([dict(ok, target="012 debt #18 / 014 WI-16")], owners, ALLOCATED)) == 1
    assert len(debt_citation_problems([dict(ok, target="012 debt #99")], owners, ALLOCATED)) == 1
    assert len(debt_citation_problems([dict(ok, target="018 debt #55")], owners, ALLOCATED)) == 1


def test_every_d12_pin_cites_a_registered_debt_and_a_014_wi() -> None:
    """R2 on the real data: each of the 17 D12 pins carries both addresses (route and UI)."""
    owners = register_owners(REGISTER.read_text(encoding="utf-8"))
    allocated = allocated_branches(MIGRATION_PLAN.read_text(encoding="utf-8"))
    assert len(plan_rows(PLAN.read_text(encoding="utf-8"))) == 34
    assert len(load_pins()) == 18
    pins = [p for p in load_pins() if is_d12_pin(p)]
    assert len(pins) == 17, [(p["row"], p["half"]) for p in pins]
    assert debt_citation_problems(pins, owners, allocated) == []
    for p in pins:
        assert DEBT_RE.search(p["target"]), p
        assert any(n in WI_014 for n in map(int, WI_RE.findall(p["target"]))), p


def test_wi_ids_read_the_suffixed_library_wi() -> None:
    """RV-15: the id regex accepts `WI-16b` and keeps it distinct from `WI-16`."""
    assert wi_ids("012 debt #55 (routes) / 014 WI-16b (UI acceptance)") == ["WI-16b"]
    assert wi_ids("014 WI-16 / WI-16b") == ["WI-16", "WI-16b"]
    assert wi_ids("WI-14, WI-19") == ["WI-14", "WI-19"]
    assert wi_ids("WI-16bc or xWI-16 or 012 debt #16") == []


def test_library_d12_pin_still_pointing_at_wi16_fails() -> None:
    """RV-15 negative: a library-side D12 pin whose UI owner is still WI-16 is refused.

    Before the ruling this was the correct target (R2: "014 has no library-page WI"). After it,
    WI-16 is the reader shell only; the library half of a D12 pin belongs to `LIBRARY_WI`.
    """
    d12 = "D12 (2026-09-25): routes absent"
    for row, half in (("WI-5#1", "all"), ("WI-4#1", "library"), ("WI-8#4", "all")):
        stale = {"row": row, "half": half, "reason": d12,
                 "target": "012 debt #55 (routes) / 014 WI-16 (UI acceptance)"}
        assert d12_ui_owner_problem(stale) is not None, (row, half)
        assert d12_ui_owner_problem(dict(stale, target="012 debt #55 / 014 WI-16b")) is None, (row, half)
        # Naming the new WI next to a stale one is still two owners, not one.
        assert d12_ui_owner_problem(dict(stale, target="012 debt #55 / 014 WI-16 + WI-16b")) is not None
        # Any other 014 WI, a WI outside 014, or no WI at all: refused for a library half.
        for bad in ("012 debt #55 / 014 WI-18", "012 debt #55 / 013 WI-13", "012 debt #55 / 015 WI-20",
                    "012 debt #55"):
            assert d12_ui_owner_problem(dict(stale, target=bad)) is not None, (row, half, bad)


def test_reader_half_d12_pin_may_name_wi16b_or_a_014_wi() -> None:
    """RV-15: a reader half keeps the 014 range; the new WI is also a legal owner for it."""
    reader = {"row": "WI-4#1", "half": "reader", "reason": "D12 (2026-09-25): routes absent"}
    for ok in ("012 debt #54 / 014 WI-16b", "012 debt #54 / 014 WI-16", "012 debt #54 / 014 WI-19"):
        assert d12_ui_owner_problem(dict(reader, target=ok)) is None, ok
    for bad in ("012 debt #54 / 013 WI-13", "012 debt #54 / 015 WI-20", "012 debt #54"):
        assert d12_ui_owner_problem(dict(reader, target=bad)) is not None, bad


def test_every_d12_pin_is_handed_to_the_library_wi() -> None:
    """RV-15 on the real data: all 17 D12 pins name `LIBRARY_WI` as their UI owner, and nothing else."""
    pins = [p for p in load_pins() if is_d12_pin(p)]
    assert len(pins) == 17, [(p["row"], p["half"]) for p in pins]
    for p in pins:
        assert wi_ids(p["target"]) == [LIBRARY_WI], p
        assert d12_ui_owner_problem(p) is None, p


# ---------------------------------------------------------------------------
# 018 WI-1: owner-exact debt citations (spec §6 Q1). Case ids are the test matrix's (W1-nn).
ALLOCATED: Set[str] = {f"{n:03d}" for n in range(7, 21)}


def _pin(target: str, row: str = "WI-5#1", half: str = "all") -> dict:
    return {"row": row, "half": half, "target": target, "reason": "D12 (2026-09-25): routes absent"}


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("**012-storage-format**", "012"),
        ("**018-library-routes**", "018"),
        ("**[018 WI-7](./018-library-routes.md)**（收尾对账）", "018"),
        ("**011**", "011"),
        ("**011 后端重构**", "011"),
        ("**012-storage-format**（随 `load_book_metadata()` 一起落，与 #35 同批）", "012"),
        ("~~**012-storage-format**~~ → **018-library-routes**", "018"),
        ("~~a~~ **011** ~~b~~", "011"),
        ("**012-storage-format** / **018-library-routes**", "012"),
        ("**0120-x**", None),
        ("**1234**", None),
        ("**12-x**", None),
        ("待定", None),
        ("**待定**（可能 012）", None),
        ("随 012 一起兑付", None),
        ("~~**待定**~~（…）⬛ …", None),
        ("", None),
        # FX-6-01 (fix-plan WI-6, #7): the whole bold span is anchored, not just its first digits.
        ("**012→018-library-routes**", None),
        ("**018x**", None),
        ("**[018x WI-7](x.md)**", None),
        ("**012-storage-format (随 #35 同批)**", "012"),
        ("**[018 WI-7](./018-library-routes.md) 收尾对账**", "018"),
    ],
)
def test_parse_owner_branch_table(cell: str, expected: "str | None") -> None:
    """W1-01: each accepted owner form and its near-miss neighbour."""
    assert parse_owner_branch(cell) == expected, cell


_NO_MARKUP = st.text(alphabet=st.characters(blacklist_characters="~*"))
_SLUG = st.from_regex(r"[a-z0-9]+(-[a-z0-9]+)*", fullmatch=True)


@settings(max_examples=200, deadline=None)
@given(n=st.integers(0, 999), slug=_SLUG, d=st.sampled_from("0123456789"), noise=_NO_MARKUP,
       tail=_NO_MARKUP, data=st.data())
def test_parse_owner_branch_properties(n: int, slug: str, d: str, noise: str, tail: str, data) -> None:
    """W1-02: digit boundary, start anchoring, strikethrough transparent at any offset outside the span."""
    num = f"{n:03d}"
    head = f"**{num}-{slug}**"
    base = head + tail
    assert parse_owner_branch(base) == num  # (a)
    assert parse_owner_branch(f"**{num}{d}-{slug}**") is None  # (b)
    k = data.draw(st.one_of(st.just(0), st.integers(len(head), len(base))), label="k")
    struck = base[:k] + f"~~**{noise}**~~" + base[k:]
    assert parse_owner_branch(struck) == num, struck  # (c)
    for cell in (base, struck, noise, f"**{noise}**"):  # (d)
        r = parse_owner_branch(cell)
        assert r is None or re.fullmatch(r"[0-9]{3}", r), (cell, r)
    p = data.draw(
        st.text(alphabet=st.characters(blacklist_characters="[~*"), min_size=1).filter(
            lambda t: not re.match(r"^\d{3}(?!\d)", t)
        ),
        label="p",
    )
    assert parse_owner_branch(f"**{p}{num}-{slug}**") is None  # (e)
    # FX-6-02 (fix-plan WI-6, #7): a digit run followed by a character outside the grammar's
    # continuations (`-`, space, or `]` in the link form) is no owner, plain or link form.
    c = data.draw(
        st.characters(blacklist_characters="- ]*~[()", blacklist_categories=("Nd", "Cs", "Cc")), label="c"
    )
    rest = data.draw(st.from_regex(r"[a-z0-9-]{0,12}", fullmatch=True), label="rest")
    assert parse_owner_branch(f"**{num}{c}{rest}**") is None  # (f)
    assert parse_owner_branch(f"**[{num}{c}WI-7](x.md)**") is None  # (g)


#: FX-6-03: the owner regex as it stood before fix-plan WI-6 (#7), frozen. Do not update it.
_OLD_OWNER_BRANCH_RE = re.compile(r"\[?([0-9]{3})(?![0-9])(?:-[a-z0-9-]+| WI-\S+)?", re.ASCII)


def test_parse_owner_branch_conserves_every_real_row_the_old_parser_read() -> None:
    """FX-6-03: anchoring the whole span changes no real register row the old `.match` parsed."""
    owners = register_owners(REGISTER.read_text(encoding="utf-8"))
    old: Dict[int, str] = {}
    for n, cell in owners.items():
        first = BOLD_RE.search(STRIKE_RE.sub("", cell))
        m = _OLD_OWNER_BRANCH_RE.match(first.group(1)) if first else None
        if m:
            old[n] = m.group(1)
    assert old, "the register yielded no parsed owner at all"
    assert {n: parse_owner_branch(owners[n]) for n in old} == old
    pinned = (31, 51, 53, 54, 55, 56, 58)
    assert {n: old[n] for n in pinned} == {31: "018", 51: "018", 53: "018", 54: "012", 55: "012", 56: "018", 58: "018"}


def test_parse_owner_branch_reads_the_real_31_row_as_is() -> None:
    """W1-03: #31's struck 「待定」 prefix is skipped; if this fails, fix the parser, never the doc."""
    cell = register_owners(REGISTER.read_text(encoding="utf-8"))[31]
    assert cell.startswith("~~**待定**")
    assert parse_owner_branch(cell) == "018"


@pytest.mark.parametrize("cell", ["**待定 012**", "**v012-x**", "**0120-abc-123**", "**待定**（可能 **012**）"])
def test_parse_owner_branch_is_start_anchored_and_first_span_only(cell: str) -> None:
    """W1-20: a number that does not start the first bold span is no owner."""
    assert parse_owner_branch(cell) is None


@pytest.mark.parametrize(
    "cell",
    ["前注 ~~**012-a**~~ **018-b**", "前注 **018-b** ~~**012-a**~~", "~~**012-a**~~ 中段 ~~**011-c**~~ **018-b**"],
)
def test_parse_owner_branch_strips_strikethrough_anywhere(cell: str) -> None:
    """W1-21: not only a leading `~~…~~` is history."""
    assert parse_owner_branch(cell) == "018"


def test_allocated_branches_on_the_real_plan() -> None:
    """W1-04: §9 allocates exactly 007…025 today (025-verify-control, branched from master 22e387a). Allocating 026 moves this constant in the same commit."""
    got = allocated_branches(MIGRATION_PLAN.read_text(encoding="utf-8"))
    assert got == {f"{n:03d}" for n in range(7, 26)}
    assert len(got) == 19


def test_allocated_branches_reads_only_the_section_9_branch_column() -> None:
    """W1-05: other columns of the §9 table, and 分支 columns of other sections, do not count."""
    doc = (
        "## 7. 阶段门槛表\n\n"
        "| 门槛 | 分支 |\n|---|---|\n| x | `021-x` |\n\n"
        "## 9. 里程碑与分支\n\n"
        "| 里程碑 | 内容 | 分支 | 归属 |\n|---|---|---|---|\n"
        "| M0 | `099-decoy` | `007-a` | A |\n"
        "| M1 | b | `018-b` | `reader3 launch` |\n\n"
        "## 10. 决策依据\n\n"
        "| 里程碑 | 分支 |\n|---|---|\n| M9 | `022-y` |\n"
    )
    assert allocated_branches(doc) == {"007", "018"}


@pytest.mark.parametrize(
    ("target", "owners", "prefix", "branch", "n"),
    [
        ("018 debt #54", {54: "**012-storage-format**"}, "018", "012", 54),
        ("012 debt #56", {56: "**018-library-routes**"}, "012", "018", 56),
        ("012 debt #18", {18: "**011**"}, "012", "011", 18),
    ],
)
def test_debt_citation_mismatch_is_exactly_one_problem(target, owners, prefix, branch, n) -> None:
    """W1-06: the owner branch must equal the citation prefix."""
    problems = debt_citation_problems([_pin(target)], owners, ALLOCATED)
    assert len(problems) == 1, problems
    for field in ("WI-5#1/all", f"#{n}", prefix, branch):
        assert field in problems[0], (field, problems)


def test_debt_citation_unresolvable_id() -> None:
    """W1-07"""
    problems = debt_citation_problems([_pin("018 debt #99")], {56: "**018-library-routes**"}, ALLOCATED)
    assert len(problems) == 1, problems
    assert "#99" in problems[0] and "not in the register" in problems[0]


def test_debt_citation_owner_branch_must_be_allocated() -> None:
    """W1-08: the owner's number must be in the §9 allocation, whatever the prefix."""
    upto_017 = {f"{n:03d}" for n in range(7, 18)}
    problems = debt_citation_problems([_pin("018 debt #56")], {56: "**018-library-routes**"}, upto_017)
    assert len(problems) == 1, problems
    assert "018" in problems[0] and "not allocated" in problems[0]
    assert len(debt_citation_problems([_pin("018 debt #60")], {60: "**021-x**"}, ALLOCATED)) == 1


@pytest.mark.parametrize("owner", ["**待定**（可能 012）", "**0120-x**", "随 012 一起兑付", "**待定**（可能 **012**）"])
def test_debt_citation_substring_owner_is_refused(owner: str) -> None:
    """W1-09: each of these passed the old `"012" in owner` substring check."""
    assert len(debt_citation_problems([_pin("012 debt #40")], {40: owner}, ALLOCATED)) == 1


def test_debt_citation_positive_controls_and_multi_citation_targets() -> None:
    """W1-10"""
    real31 = register_owners(REGISTER.read_text(encoding="utf-8"))[31]
    owners = {54: "**012-storage-format**", 55: "**012-storage-format**", 56: "**018-library-routes**", 31: real31}
    multi = "012 debt #54 + 018 debt #56 (routes) / 014 WI-16b"
    for target in ("012 debt #55", "018 debt #56", "018 debt #31", multi):
        assert debt_citation_problems([_pin(target)], owners, ALLOCATED) == [], target
    wrong = {**owners, 56: "**012-storage-format**"}
    problems = debt_citation_problems([_pin(multi)], wrong, ALLOCATED)
    assert len(problems) == 1, problems
    assert "#56" in problems[0] and "#54" not in problems[0]


def test_debt_citation_counts_per_citation_not_per_pin() -> None:
    """W1-22: two bad citations in one pin are two problems, on seeded and on real owners."""
    pin = _pin("018 debt #54 + 012 debt #56", row="WI-4#6")
    seeded = {54: "**012-storage-format**", 56: "**018-library-routes**"}
    real = register_owners(REGISTER.read_text(encoding="utf-8"))
    for owners in (seeded, real):
        problems = debt_citation_problems([pin], owners, ALLOCATED)
        assert len(problems) == 2, problems
        assert sum("#54" in x for x in problems) == 1, problems
        assert sum("#56" in x for x in problems) == 1, problems


def test_debt_citation_never_parses_uncited_rows() -> None:
    """W1-11: a 「待定」 or free-text owner that no pin cites is out of scope."""
    owners = {50: "~~**待定**~~（…）", 49: "free text 012", 55: "**012-storage-format**"}
    assert debt_citation_problems([_pin("012 debt #55")], owners, ALLOCATED) == []


_TEMPLATES = [
    (lambda b, c: f"**{b}-slug**", True),
    (lambda b, c: f"**[{b} WI-7](x)**（…）", True),
    (lambda b, c: f"前注 ~~**{c}-x**~~ **{b}-y**", True),
    (lambda b, c: f"**待定**（可能 **{b}**）", False),
    (lambda b, c: f"**v{b}-x**", False),
    (lambda b, c: f"**{b}0-x**", False),
]
_BRANCH = st.sampled_from(["011", "012", "018", "021"])


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_debt_citation_problem_count_matches_an_independent_oracle(data) -> None:
    """W1-12: ground truth comes from how each owner cell was generated, not from the parser."""
    keys = data.draw(st.lists(st.integers(1, 60), min_size=1, max_size=6, unique=True), label="keys")
    owners: Dict[int, str] = {}
    truth: Dict[int, "str | None"] = {}
    for k in keys:
        tpl, parses = data.draw(st.sampled_from(_TEMPLATES), label=f"tpl{k}")
        b, c = data.draw(_BRANCH, label=f"b{k}"), data.draw(_BRANCH, label=f"c{k}")
        owners[k] = tpl(b, c)
        truth[k] = b if parses else None
    cite = st.tuples(st.sampled_from(["012", "018"]), st.sampled_from(keys + [99]))
    pins = data.draw(st.lists(st.lists(cite, min_size=1, max_size=3), min_size=1, max_size=4), label="pins")
    expected = 0
    for cites in pins:
        for p, n in cites:
            t = truth.get(n)
            if n not in owners or t is None or t not in ALLOCATED or t != p:
                expected += 1
    built = [_pin(" + ".join(f"{p} debt #{n}" for p, n in cites)) for cites in pins]
    assert len(debt_citation_problems(built, owners, ALLOCATED)) == expected


def test_real_ledger_citations_map_exactly() -> None:
    """W1-15: every pin citation resolves to a row owned by the cited branch; the mapping is pinned."""
    owners = register_owners(REGISTER.read_text(encoding="utf-8"))
    allocated = allocated_branches(MIGRATION_PLAN.read_text(encoding="utf-8"))
    pins = load_pins()
    assert debt_citation_problems(pins, owners, allocated) == []
    assert {n: parse_owner_branch(owners[n]) for n in (54, 55, 56)} == {54: "012", 55: "012", 56: "018"}
    cites = Counter((pre, int(n)) for p in pins for pre, n in DEBT_RE.findall(p["target"]))
    assert cites == Counter({("012", 54): 10, ("012", 55): 6, ("018", 56): 2})
    assert sum(cites.values()) == 18
    cite56 = {(p["row"], p["half"]) for p in pins if ("018", "56") in DEBT_RE.findall(p["target"])}
    assert cite56 == {("WI-4#6", "all"), ("WI-8#4", "all")}


def test_real_register_owners_of_the_rows_018_wi1_governs() -> None:
    """W1-17: D1 (2026-09-26) moved #51 / #53 / #56 / #58 to 018; #31 already says 018 WI-7."""
    owners = register_owners(REGISTER.read_text(encoding="utf-8"))
    got = {n: parse_owner_branch(owners[n]) for n in (31, 51, 53, 54, 55, 56, 58)}
    assert got == {31: "018", 51: "018", 53: "018", 54: "012", 55: "012", 56: "018", 58: "018"}
    assert "与 #35 同批" not in owners[56]


def test_pin_fixture_has_no_stale_012_citation_of_the_moved_rows() -> None:
    """W1-18"""
    text = PINNED.read_text(encoding="utf-8")
    assert re.findall(r"\b012 debt #5[1368]\b", text) == []
    assert "(012/014)" not in text
    assert "012|018 debt #N" in json.loads(text)["_doc"]
