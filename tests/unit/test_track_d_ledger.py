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
from pathlib import Path
from typing import Dict, List, Set, Tuple

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
# names an address: a 014 WI (UI acceptance) and/or a 012 debt-register id (route). The register
# is `REGISTER`; a cited id must be a row there whose owner column (兑付方) names 012.
WI_RE = re.compile(r"\bWI-(\d+)(?:[a-z])?\b")  # RV-15: `WI-16b` counts as its number (16, inside 014)
WI_014 = frozenset(range(14, 20))  # 014-ts-frontend-reader owns WI-14 – WI-19 (plan §4)
DEBT_012_RE = re.compile(r"\b012 debt #(\d+)\b")
REGISTER_HEADER = "| # | 欠什么 |"


def d12_target_has_address(target: str) -> bool:
    return bool(DEBT_012_RE.search(target)) or any(int(n) in WI_014 for n in WI_RE.findall(target))


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


def debt_citation_problems(pins: List[dict], owners: Dict[int, str]) -> List[str]:
    """Every `012 debt #N` a pin cites must be a register row whose owner names 012."""
    out = []
    for p in pins:
        for n in map(int, DEBT_012_RE.findall(p["target"])):
            owner = owners.get(n)
            if owner is None:
                out.append(f"{p['row']}/{p['half']}: 012 debt #{n} is not in the register")
            elif "012" not in owner:
                out.append(f"{p['row']}/{p['half']}: debt #{n} is owned by {owner!r}, not 012")
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


def test_d12_pin_must_name_a_014_wi_or_a_012_debt_id() -> None:
    """RV-11 (2026-09-25, user ruling R2): a D12 pin names its owner by address, not by branch.

    The branch-level target (`D12_TARGET`, or any target that merely contains "014") said which
    branches owe the row without saying which WI or which debt entry. A D12 pin must name a 014
    WI (`WI-14`..`WI-19`, the UI-acceptance owner) and/or a 012 debt-register id (`012 debt #N`,
    the route owner). A WI outside 014, or a debt number without the `012 debt` prefix, is no address.
    """
    base = {"row": "WI-5#1", "half": "all", "reason": "D12 (2026-09-25): routes absent"}
    for bare in (D12_TARGET, "014", "012", "012 (routes) / 014", "later", "debt #55", "012 #55",
                 "#55", "013 WI-13", "WI-9", "015 WI-20"):
        assert pin_owner_problem(dict(base, target=bare)) is not None, bare
    for named in ("014 WI-16", "WI-14", "012 debt #55",
                  "012 debt #55 (routes) / 014 WI-16 (UI acceptance)"):
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


def test_cited_debt_ids_must_resolve_to_012_rows() -> None:
    """Seed: a cited id must exist in the register and its owner column must name 012."""
    owners = {55: "**012-storage-format**", 18: "**011**"}
    ok = {"row": "WI-5#1", "half": "all", "target": "012 debt #55 / 014 WI-16", "reason": "D12"}
    assert debt_citation_problems([ok], owners) == []
    assert debt_citation_problems([dict(ok, target="012 debt #18 / 014 WI-16")], owners) != []
    assert debt_citation_problems([dict(ok, target="012 debt #99")], owners) != []


def test_every_d12_pin_cites_a_registered_012_debt_and_a_014_wi() -> None:
    """R2 on the real data: each of the 17 D12 pins carries both addresses (route and UI)."""
    owners = register_owners(REGISTER.read_text(encoding="utf-8"))
    pins = [p for p in load_pins() if is_d12_pin(p)]
    assert len(pins) == 17, [(p["row"], p["half"]) for p in pins]
    assert debt_citation_problems(pins, owners) == []
    for p in pins:
        assert DEBT_012_RE.search(p["target"]), p
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
