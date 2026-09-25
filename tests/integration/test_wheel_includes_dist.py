"""013 WI-9 A9.5 (cases C9.05, C9.42): `dist/**` reaches the wheel at every depth, and the checker says so.

Packaging lane (`-m slow`): real `uv build --wheel` runs, each in a tmp snapshot of the
tree (`frontend_host.snapshot_worktree`), so R is never touched -- `check_wheel_contents.py`
deletes `build/` and `*.egg-info` in whatever root it is pointed at.

- C9.05: a probe seeded three directories deep under `dist/` is in the wheel, every dist
  file is, and the checker passes reporting at least one dist member. A one-level glob
  such as `static/dist/*` fails this.
- C9.42: with dist excluded from package data the wheel has no dist member (precondition
  -- the seed took effect) and the checker exits non-zero naming a dist path.
- C9.42 companion: with no `dist/` in the tree at all, per-file reconciliation is
  vacuously complete, so the checker must fail on "zero dist members" by itself.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Set

import frontend_host as fh
import pytest

pytestmark = pytest.mark.slow

CHECKER = fh.REPO_ROOT / "scripts" / "check_wheel_contents.py"
PROBE_REL = "__probe__/a/b/probe.txt"
BUILD_TIMEOUT_S = 600


def _repo_copy(tmp_path: Path) -> Path:
    return fh.snapshot_worktree(tmp_path / "repo")


def _wheel_names(repo: Path, out: Path) -> Set[str]:
    proc = subprocess.run(
        ["uv", "build", "--wheel", "-o", str(out)], cwd=str(repo), capture_output=True, text=True, timeout=BUILD_TIMEOUT_S
    )
    assert proc.returncode == 0, fh.describe(proc)
    wheels = sorted(out.glob("*.whl"))
    assert len(wheels) == 1, wheels
    with zipfile.ZipFile(wheels[0]) as z:
        return set(z.namelist())


def _checker(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(repo)],
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT_S,
    )


def test_deep_dist_file_in_wheel(tmp_path: Path) -> None:
    """C9.05."""
    repo = _repo_copy(tmp_path)
    probe = repo / fh.DIST_REL / PROBE_REL
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("probe\n")

    names = _wheel_names(repo, tmp_path / "wheel")
    assert fh.WHEEL_DIST_PREFIX + PROBE_REL in names
    want = {fh.WHEEL_DIST_PREFIX + rel for rel in fh.digest_map(repo / fh.DIST_REL)}
    assert len(want) > 1, "dist/ holds nothing but the probe -- the build output is not in the tree"
    assert want <= names, f"dist files missing from the wheel: {sorted(want - names)}"

    proc = _checker(repo)
    assert proc.returncode == 0, fh.describe(proc)
    counted = re.search(r"static/dist/\D*?(\d+)", proc.stdout)
    assert counted and int(counted.group(1)) >= 1, fh.describe(proc)


def test_checker_fails_when_dist_excluded_from_wheel(tmp_path: Path) -> None:
    """C9.42."""
    repo = _repo_copy(tmp_path)
    pyproject = repo / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text()
        + '\n[tool.setuptools.exclude-package-data]\n"reader3_app.web" = ["static/dist/**/*"]\n'
    )
    # Seed correction (found by the precondition below on the first green run): setuptools'
    # `static/dist/**/*` does not match files directly in dist/ (manifest.json), so the
    # top level needs its own pattern for the exclusion to be total.
    pyproject.write_text(
        pyproject.read_text().replace('["static/dist/**/*"]', '["static/dist/*", "static/dist/**/*"]')
    )
    names = _wheel_names(repo, tmp_path / "wheel")
    assert not [n for n in names if n.startswith(fh.WHEEL_DIST_PREFIX)], "seed did not exclude dist/"

    proc = _checker(repo)
    assert proc.returncode != 0, fh.describe(proc)
    assert "static/dist/" in proc.stdout + proc.stderr, fh.describe(proc)


def test_checker_fails_when_tree_has_no_dist(tmp_path: Path) -> None:
    """C9.42 companion: zero dist members is a failure on its own, not a vacuous pass."""
    repo = _repo_copy(tmp_path)
    shutil.rmtree(repo / fh.DIST_REL, ignore_errors=True)

    proc = _checker(repo)
    assert proc.returncode != 0, fh.describe(proc)
    assert "static/dist/" in proc.stdout + proc.stderr, fh.describe(proc)
