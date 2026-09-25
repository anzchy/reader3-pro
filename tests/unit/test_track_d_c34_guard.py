"""013 WI-13 C13.34 / A13.10: the `track_d_013` marker selects exactly the ledger's PASS rows.

`test_track_d_ledger.py` proves the ledger is *complete* (collected + pinned == the 34 plan
rows). It reads docstring tags, so it cannot tell whether `pytest -m track_d_013` -- the
command that actually executes Track D -- runs the same set. This guard closes that gap:

(a) the node ids that `pytest -m track_d_013 --collect-only` selects over `tests/unit` and
    `tests/e2e`, mapped to (row, half) by their docstring tags (plus `EXISTING`), together
    with the Vitest-tagged pairs, equal exactly the PASS rows (required minus pinned);
    every marked node maps to a row (no over-collection), and every tagged pytest node is
    marked (no under-collection);
(b) every deferred row (required minus executed) is an entry of `track_d_pinned_014.json`.

Vitest rows cannot carry a pytest marker; they are mapped through the ledger's
`vitest_collected` and run by `npm test`. None of the PASS-row tests is in the frozen set,
so no frozen file needed a ledger-only mapping.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set

import pytest

from test_track_d_ledger import (
    EXISTING,
    PLAN,
    REPO,
    Pair,
    load_pins,
    plan_rows,
    pytest_collected,
    required_pairs,
    vitest_collected,
)

MARKER = "track_d_013"
SCOPES = ("tests/unit", "tests/e2e")


def marked_node_ids(root: Path) -> Set[str]:
    """Node ids selected by `-m track_d_013`, parametrization suffix stripped."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", MARKER, "--collect-only", "-q", "-p", "no:cacheprovider",
         *SCOPES],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=240,
    )
    # rc 5 == "no tests collected": still a valid answer (the empty set), judged below.
    assert proc.returncode in (0, 5), f"collect-only failed rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    nodes = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("=", "<")):
            nodes.add(line.split("[", 1)[0])
    return nodes


def node_to_pairs() -> Dict[str, List[Pair]]:
    out: Dict[str, List[Pair]] = {}
    for pair, nodes in pytest_collected(REPO).items():
        for node in nodes:
            out.setdefault(node, []).append(pair)
    for pair, node in EXISTING.items():
        out.setdefault(node, []).append(pair)
    return out


def compare(marked: Set[str], by_node: Dict[str, List[Pair]], vitest: Set[Pair],
            required: Set[Pair], pinned: Set[Pair]) -> Dict[str, list]:
    """Every mismatch between the marker selection and the ledger; empty dict when they agree."""
    problems: Dict[str, list] = {}
    in_scope = {n for n in by_node if n.startswith(tuple(s + "/" for s in SCOPES))}
    untagged = sorted(n for n in marked if n not in by_node)
    unmarked = sorted(in_scope - marked)
    executed = {p for n in marked for p in by_node.get(n, [])} | vitest
    pass_rows = required - pinned
    if untagged:
        problems["marked but maps to no Track-D row"] = untagged
    if unmarked:
        problems["tagged Track-D test missing the marker"] = unmarked
    if executed != pass_rows:
        problems["executed != PASS rows (extra)"] = sorted(executed - pass_rows)
        problems["executed != PASS rows (missing)"] = sorted(pass_rows - executed)
    deferred_unpinned = sorted((required - executed) - pinned)
    if deferred_unpinned:
        problems["deferred but not pinned"] = deferred_unpinned
    return problems


@pytest.fixture(scope="module")
def ledger() -> dict:
    return {
        "required": required_pairs(plan_rows(PLAN.read_text(encoding="utf-8"))),
        "pinned": {(p["row"], p["half"]) for p in load_pins()},
        "vitest": set(vitest_collected(REPO)),
        "by_node": node_to_pairs(),
    }


def test_marker_selection_equals_ledger_pass_rows(ledger: dict) -> None:
    """C13.34 (a) + (b): `-m track_d_013` runs exactly the PASS rows; the rest are all pinned."""
    marked = marked_node_ids(REPO)
    assert marked, "`-m track_d_013` selected nothing"
    problems = compare(marked, ledger["by_node"], ledger["vitest"], ledger["required"], ledger["pinned"])
    assert problems == {}
    assert len(ledger["required"] - ledger["pinned"]) + len(ledger["pinned"]) == len(ledger["required"])


def test_compare_catches_each_mismatch_kind() -> None:
    """Seeds: a dropped marker, a stray marker, and an unpinned deferral each produce a finding."""
    a, b, c = ("WI-1#1", "all"), ("WI-1#2", "all"), ("WI-1#3", "all")
    by_node = {"tests/unit/t.py::x": [a], "tests/e2e/t.py::y": [c]}
    required, pinned, vitest = {a, b, c}, {b}, set()
    assert compare({"tests/unit/t.py::x", "tests/e2e/t.py::y"}, by_node, vitest, required, pinned) == {}
    dropped = compare({"tests/unit/t.py::x"}, by_node, vitest, required, pinned)
    assert dropped["tagged Track-D test missing the marker"] == ["tests/e2e/t.py::y"]
    assert dropped["deferred but not pinned"] == [c]
    stray = compare({"tests/unit/t.py::x", "tests/e2e/t.py::y", "tests/unit/t.py::z"},
                    by_node, vitest, required, pinned)
    assert stray == {"marked but maps to no Track-D row": ["tests/unit/t.py::z"]}
