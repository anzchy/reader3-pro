"""013 WI-9 A9.9 (case C9.35): pytest-xdist is a dev dependency and `-n 4` partitions the suite exactly.

§5.0 of the frontend plan runs the browser suite as `pytest -n 4`. Its distribution check:
the union of the node ids handed to the four workers equals the `-n 1` set, and the
workers are pairwise disjoint.

`-n 4 --collect-only` alone cannot show that: xdist does not distribute under
`--collect-only`, so both sides would be the same in-process collection and the
comparison would be green by construction. The literal A9.9 comparison is kept (it is
the clause as written, and it catches a plugin that breaks collection under `-n`), and
the partition itself is observed with the `xdist_recorder` plugin, which records each
worker's items and claims the run protocol so nothing executes.

Scope: the whole `testpaths` tree, as §5.0's `pytest -n 4` would run it. Child processes
are time-bounded; nothing starts a server or a browser.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
PYPROJECT = REPO_ROOT / "pyproject.toml"
TIMEOUT_S = 300


def _env(record_dir: Path | None = None) -> Dict[str, str]:
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(FIXTURES), env.get("PYTHONPATH", "")]))
    if record_dir is not None:
        env["XDIST_RECORDER_DIR"] = str(record_dir)
    return env


def _pytest(args: List[str], env: Dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env=env,
    )


def _explain(proc: subprocess.CompletedProcess) -> str:
    return f"rc={proc.returncode}\n{proc.stdout[-2500:]}\n{proc.stderr[-2500:]}"


def _require_xdist() -> None:
    """Assert the plugin is importable before any `-n` child runs.

    Without this the child dies in argparse and the red is a wall of usage text.
    """
    import importlib.util

    assert importlib.util.find_spec("xdist") is not None, "pytest-xdist is not installed (uv sync --all-groups)"


def _collect_ids(workers: int) -> Set[str]:
    _require_xdist()
    proc = _pytest(["-n", str(workers), "--collect-only", "-q"], _env())
    assert proc.returncode == 0, _explain(proc)
    ids = {ln.strip() for ln in proc.stdout.splitlines() if "::" in ln and not ln.startswith(" ")}
    assert ids, "collected zero node ids\n" + _explain(proc)
    return ids


def _record(workers: int, record_dir: Path) -> Dict[str, List[str]]:
    _require_xdist()
    record_dir.mkdir()
    proc = _pytest(["-n", str(workers), "-p", "xdist_recorder", "-q"], _env(record_dir))
    assert proc.returncode == 0, _explain(proc)
    per_worker = {f.stem: f.read_text().splitlines() for f in sorted(record_dir.glob("*.txt"))}
    assert per_worker, "recorder saw no worker\n" + _explain(proc)
    return per_worker


def test_pytest_xdist_in_dev_group() -> None:
    text = PYPROJECT.read_text()
    block = re.search(r"^\[dependency-groups\]\s*\ndev\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    assert block, "no [dependency-groups].dev list in pyproject.toml"
    assert re.search(r'^\s*"pytest-xdist[<>=~!]', block.group(1), re.M), "pytest-xdist missing from the dev group"


def test_collect_only_n4_equals_n1() -> None:
    """A9.9 as written: the `-n 4 --collect-only -q` id set equals the `-n 1` one."""
    n4 = _collect_ids(4)
    n1 = _collect_ids(1)
    assert n4 == n1, f"only -n 4: {sorted(n4 - n1)[:20]}\nonly -n 1: {sorted(n1 - n4)[:20]}"


def test_n4_partition_is_exact(tmp_path: Path) -> None:
    """C9.35: union of the four workers' items == the -n 1 set; workers pairwise disjoint."""
    n1 = _record(1, tmp_path / "n1")
    assert set(n1) == {"gw0"}, sorted(n1)
    single = n1["gw0"]
    assert len(single) == len(set(single)), "an item ran twice under -n 1"

    n4 = _record(4, tmp_path / "n4")
    assert set(n4) == {"gw0", "gw1", "gw2", "gw3"}, f"expected four workers, got {sorted(n4)}"
    union: Set[str] = set().union(*map(set, n4.values()))
    assert union == set(single), (
        f"only -n 4: {sorted(union - set(single))[:20]}\nonly -n 1: {sorted(set(single) - union)[:20]}"
    )
    assert sum(len(v) for v in n4.values()) == len(single), {k: len(v) for k, v in n4.items()}
    # The collect-only view of the same tree names the same items.
    assert set(single) == _collect_ids(1)
