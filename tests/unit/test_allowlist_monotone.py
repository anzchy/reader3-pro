"""013 WI-9 A9.6a / A9.11e: allowlists only shrink, measured against the merge-base (C9.11).

`scripts/check_allowlist_monotone.py` exposes
`check_allowlist_monotone(repo, base_ref, path) -> list[str]` (violation messages, empty =
pass). Law: for every key `current[key] <= base[key]` (ints) or `current[key] ⊆ base[key]`
(lists), and `keys(current) ⊆ keys(base)`. The base is `git merge-base HEAD <base_ref>`,
never `HEAD~1` (the base→4→4 row), and an unresolvable base raises instead of passing.

Rows run against both guarded files: the inline allowlist (ints) and the hardcode
baseline (fingerprint lists, file-granular keys).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import contract_lints as cl

INLINE_BASE = {"style": {"a.html": 3}, "script": {}}
HARD_BASE = {"frontend/src/a.css": [".x:color", ".y:gap"]}


@pytest.fixture(scope="module")
def guard():
    return cl.load(cl.MONOTONE_GUARD, "check_allowlist_monotone_under_test")


def _put(repo: Path, rel: str, data) -> None:
    cl.write(repo, rel, json.dumps(data, indent=2, sort_keys=True) + "\n")


INLINE_ROWS = {
    "growth": ([{"style": {"a.html": 4}, "script": {}}], ["a.html", "3→4"]),
    "new-key": ([{"style": {"a.html": 3, "b.html": 1}, "script": {}}], ["b.html"]),
    "shrink": ([{"style": {"a.html": 2}, "script": {}}], None),
    "base-4-4": ([{"style": {"a.html": 4}, "script": {}}, {"style": {"a.html": 4}, "script": {}}], ["a.html", "3→4"]),
}
HARD_ROWS = {
    "growth": ([{"frontend/src/a.css": [".x:color", ".y:gap", ".z:width"]}], ["a.css", ".z:width"]),
    "new-key": ([{"frontend/src/a.css": [".x:color", ".y:gap"], "frontend/src/b.css": [".x:color"]}], ["b.css"]),
    "shrink": ([{"frontend/src/a.css": [".x:color"]}], None),
    "base-4-4": (
        [{"frontend/src/a.css": [".x:color", ".y:gap", ".z:width"]}] * 2,
        ["a.css", ".z:width"],
    ),
}


@pytest.mark.parametrize(
    ("rel", "base", "row"),
    [(cl.INLINE_ALLOWLIST_REL, INLINE_BASE, r) for r in INLINE_ROWS]
    + [(cl.HARDCODE_BASELINE_REL, HARD_BASE, r) for r in HARD_ROWS],
)
def test_growth_over_merge_base_rejected(guard, tmp_path: Path, rel: str, base, row: str) -> None:
    rows = INLINE_ROWS if rel == cl.INLINE_ALLOWLIST_REL else HARD_ROWS
    commits, needles = rows[row]
    repo = tmp_path / "repo"
    _put(repo, rel, base)
    cl.init_repo(repo)
    for i, data in enumerate(commits):
        _put(repo, rel, data)
        cl.commit_all(repo, f"c{i}")
    problems = guard.check_allowlist_monotone(repo, base_ref="base", path=rel)
    if needles is None:
        assert problems == [], problems
    else:
        assert problems, f"{row}: growth not detected"
        assert any(all(n in p for n in needles) for p in problems), problems


def test_uncommitted_growth_is_seen(guard, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _put(repo, cl.INLINE_ALLOWLIST_REL, INLINE_BASE)
    cl.init_repo(repo)
    _put(repo, cl.INLINE_ALLOWLIST_REL, {"style": {"a.html": 5}, "script": {}})
    problems = guard.check_allowlist_monotone(repo, base_ref="base", path=cl.INLINE_ALLOWLIST_REL)
    assert any("3→5" in p for p in problems), problems


def test_file_introduced_after_base_is_unconstrained_but_deletion_is_fine(guard, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    cl.write(repo, "README", "x\n")
    cl.init_repo(repo)
    _put(repo, cl.INLINE_ALLOWLIST_REL, INLINE_BASE)
    assert guard.check_allowlist_monotone(repo, base_ref="base", path=cl.INLINE_ALLOWLIST_REL) == []

    repo2 = tmp_path / "repo2"
    _put(repo2, cl.INLINE_ALLOWLIST_REL, INLINE_BASE)
    cl.init_repo(repo2)
    (repo2 / cl.INLINE_ALLOWLIST_REL).unlink()
    assert guard.check_allowlist_monotone(repo2, base_ref="base", path=cl.INLINE_ALLOWLIST_REL) == []


def test_unresolvable_base_raises(guard, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _put(repo, cl.INLINE_ALLOWLIST_REL, INLINE_BASE)
    cl.init_repo(repo)
    with pytest.raises(guard.BaseUnresolvedError):
        guard.check_allowlist_monotone(repo, base_ref="no-such-ref", path=cl.INLINE_ALLOWLIST_REL)
    with pytest.raises(guard.BaseUnresolvedError):
        guard.check_allowlist_monotone(repo, base_ref=None, path=cl.INLINE_ALLOWLIST_REL)
    with pytest.raises(guard.BaseUnresolvedError):
        guard.check_allowlist_monotone(tmp_path / "not-a-repo", base_ref="base", path=cl.INLINE_ALLOWLIST_REL)


def test_cli_fails_closed_without_base(guard, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _put(repo, cl.INLINE_ALLOWLIST_REL, INLINE_BASE)
    cl.init_repo(repo)
    rc, out = cl.call_main(guard, ["--root", str(repo)])
    assert rc != 0, out
    assert "cannot resolve base" in out.lower(), out
    assert "OK" not in out and "no growth" not in out, out


def test_real_repo_guard_passes(guard) -> None:
    rc, out = cl.call_main(guard, ["--root", str(cl.REPO_ROOT)])
    assert rc == 0, out
