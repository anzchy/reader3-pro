"""Shared helpers for the 013 WI-9 frontend-toolchain tests (unit and packaging lanes).

One definition of "where the frontend lives" for every Python test that drives Node:
the Vite/Vitest workspace is the repo root (`package.json`, `tsconfig.json`), the
sources are `frontend/src/`, the Vitest specs are `frontend/tests/`, and the build
lands in `src/reader3_app/web/static/dist/` (Risk R-5: the TS sources stay outside the
Python package, so package-data never ships them).

**Node missing is a failure, never a skip.** A unit-lane case that skipped on a machine
without Node would report green while proving nothing -- the exact shape
`test_unit_lane_has_no_browser_dependency.py` exists to rule out. `require_node_toolchain`
calls `pytest.fail`.

**Every subprocess carries an explicit wall-clock timeout** (the unit lane's rule for
child processes; see the lane description in `.claude/tdd-guardian/config.json`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
FE_SRC = FRONTEND / "src"
FE_TESTS = FRONTEND / "tests"
DIST_REL = "src/reader3_app/web/static/dist"
DIST = REPO_ROOT / DIST_REL
MANIFEST_NAME = "manifest.json"
#: Wheel member prefix for everything under `dist/`.
WHEEL_DIST_PREFIX = "reader3_app/web/static/dist/"

#: The three Vite entries, as the manifest names them (paths relative to the Vite root,
#: which is `frontend/`). Adding a fourth entry or renaming one is a contract change.
ENTRY_SRCS: Dict[str, str] = {
    "library": "src/library/index.ts",
    "reader": "src/reader/index.ts",
    "settings": "src/settings/index.ts",
}

#: Root-level files a copied frontend workspace needs besides `frontend/` itself.
WORKSPACE_FILES = (
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    ".npmrc",
    ".nvmrc",
    ".dependency-cruiser.cjs",
)

IGNORED_NAMES = {".DS_Store"}


def node_env() -> Dict[str, str]:
    """Environment for Node children: no colour codes in anything we parse."""
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    return env


def require_node_toolchain(need_node_modules: bool = True) -> None:
    """Fail -- not skip -- when Node, npm or the installed workspace is absent."""
    problems: List[str] = []
    for exe in ("node", "npm", "npx"):
        if shutil.which(exe) is None:
            problems.append(f"`{exe}` is not on PATH (install the Node version in .nvmrc)")
    if not (REPO_ROOT / "package.json").is_file():
        problems.append("package.json is missing at the repo root")
    if need_node_modules and not (REPO_ROOT / "node_modules").is_dir():
        problems.append("node_modules/ is missing -- run `npm ci` at the repo root")
    if problems:
        pytest.fail("frontend toolchain unavailable:\n  " + "\n  ".join(problems), pytrace=False)


def run(
    cmd: Sequence[str] | str,
    cwd: Path,
    timeout: float,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Bounded subprocess. A hang becomes a TimeoutExpired (red), never a stuck lane."""
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env if env is not None else node_env(),
        shell=shell,
    )


def describe(proc: subprocess.CompletedProcess) -> str:
    return (
        f"rc={proc.returncode}\n--- stdout (tail) ---\n{proc.stdout[-3000:]}"
        f"\n--- stderr (tail) ---\n{proc.stderr[-3000:]}"
    )


def make_workspace(dest: Path) -> Path:
    """Copy `frontend/` plus the root workspace files into `dest`; symlink node_modules.

    Seeds (a failing spec, a retargeted alias) go into this copy, never into R.
    """
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FRONTEND, dest / "frontend", ignore=shutil.ignore_patterns("node_modules", ".vite"))
    for name in WORKSPACE_FILES:
        src = REPO_ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    (dest / "node_modules").symlink_to(REPO_ROOT / "node_modules", target_is_directory=True)
    return dest


def worktree_files(root: Path = REPO_ROOT, pathspec: Iterable[str] = ()) -> List[str]:
    """Files a commit of the current working tree would contain (tracked + untracked, not ignored).

    This is what a clean clone of the about-to-be-committed tree holds: it respects
    .gitignore exactly like `git add -A` would, and drops files deleted in the tree.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *pathspec],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"git ls-files failed: {proc.stderr}"
    out = []
    for rel in proc.stdout.split("\0"):
        if rel and (root / rel).is_file() and Path(rel).name not in IGNORED_NAMES:
            out.append(rel)
    return sorted(set(out))


def snapshot_worktree(dest: Path, root: Path = REPO_ROOT) -> Path:
    """A clean-clone equivalent of the working tree: only files git would commit."""
    for rel in worktree_files(root):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    return dest


def digest_map(base: Path) -> Dict[str, str]:
    """`{relative posix path: sha256}` for every file under `base`."""
    out: Dict[str, str] = {}
    if not base.is_dir():
        return out
    for f in sorted(base.rglob("*")):
        if f.is_file() and f.name not in IGNORED_NAMES:
            out[f.relative_to(base).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def committed_dist_map(root: Path = REPO_ROOT) -> Dict[str, str]:
    """The dist digest map as the tree would commit it (see `worktree_files`)."""
    prefix = DIST_REL + "/"
    out: Dict[str, str] = {}
    for rel in worktree_files(root, [DIST_REL]):
        out[rel[len(prefix):]] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    return out


def diff_maps(a: Dict[str, str], b: Dict[str, str]) -> str:
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return f"only in first: {only_a}\nonly in second: {only_b}\nchanged digests: {changed}"
