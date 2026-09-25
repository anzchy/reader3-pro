"""REG-1 part 2, C9.23 (013 WI-9): the snapshot's metadata names the unmodified base.

Unit lane: it reads a JSON file and asks git for two tree hashes; no browser.
It trusts the capture code's self-report, which C9.38 (e2e) closes with an
independent capture from a `671f580` worktree.

Needs `671f580` in the object store. A shallow CI checkout (fetch-depth 1) does not
have it; that fails loudly here rather than skipping.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "tests" / "fixtures" / "snapshots" / "reg1_computed_style.json"
BASE = "671f580"
TREES = {
    "templates": "src/reader3_app/web/templates",
    "static": "src/reader3_app/web/static",
}


def _rev_parse(spec: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", spec],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"git rev-parse {spec} failed: {proc.stderr.strip()} "
        f"(is {BASE} in the object store? a fetch-depth 1 checkout lacks it)"
    )
    return proc.stdout.strip()


def test_c9_23_snapshot_metadata_names_the_unmodified_base() -> None:
    assert SNAPSHOT.is_file(), f"{SNAPSHOT} is missing; see test_reg1_computed_style.py's docstring"
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert doc["base_commit"].startswith(BASE)
    assert doc["base_commit"] == _rev_parse(f"{BASE}^{{commit}}")
    assert doc["source_tree"] == {k: _rev_parse(f"{BASE}:{p}") for k, p in TREES.items()}
