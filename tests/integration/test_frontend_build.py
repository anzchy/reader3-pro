"""013 WI-9 build acceptance: A9.1 (C9.01, C9.04), A9.2 (C9.02), A9.6b build half (C9.03).

Packaging lane (`-m slow`): it runs a real `npm ci` and two real `vite build`s.

**"Clean clone" is a snapshot of what the working tree would commit** -- tracked plus
untracked-but-not-ignored files, `.gitignore` applied exactly as `git add -A` would
(`frontend_host.snapshot_worktree`). Before the branch commits, `git clone --local`
would clone `671f580` and test nothing of this WI; after it commits, the two are the same
set. The same rule defines "committed dist" for C9.02. The clone's committed `dist/` is
deleted before the first build, so the three entry outputs can only exist because the
build wrote them.

**A9.6b is only half here.** C9.03 asserts every entry emits its own non-empty `.css`.
The other half -- each template links its hashed CSS through `<link>` -- belongs to the
page WIs (WI-12 settings, WI-13 library, WI-16 reader): wiring a template now would
change the REG-1 baseline, which must stay zero-diff until those WIs migrate the pages.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import frontend_host as fh
import pytest

pytestmark = pytest.mark.slow

NPM_CI_TIMEOUT_S = 600
BUILD_TIMEOUT_S = 300


@dataclass
class BuiltClone:
    root: Path
    map_a: Dict[str, str]
    map_b: Dict[str, str]

    @property
    def dist(self) -> Path:
        return self.root / fh.DIST_REL

    def manifest(self) -> dict:
        path = self.dist / fh.MANIFEST_NAME
        assert path.is_file(), f"no Vite manifest at {path}"
        return json.loads(path.read_text())


def _build(root: Path):
    return fh.run(["npm", "run", "build"], cwd=root, timeout=BUILD_TIMEOUT_S)


@pytest.fixture(scope="module")
def built_clone(tmp_path_factory: pytest.TempPathFactory) -> BuiltClone:
    fh.require_node_toolchain(need_node_modules=False)
    root = fh.snapshot_worktree(tmp_path_factory.mktemp("clone"))
    assert (root / "package-lock.json").is_file(), "package-lock.json is not part of the tree"

    ci = fh.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=root, timeout=NPM_CI_TIMEOUT_S)
    assert ci.returncode == 0, "npm ci failed on a clean clone\n" + fh.describe(ci)

    shutil.rmtree(root / fh.DIST_REL, ignore_errors=True)
    first = _build(root)
    assert first.returncode == 0, "npm run build failed on a clean clone\n" + fh.describe(first)
    map_a = fh.digest_map(root / fh.DIST_REL)
    second = _build(root)
    assert second.returncode == 0, fh.describe(second)
    map_b = fh.digest_map(root / fh.DIST_REL)
    return BuiltClone(root=root, map_a=map_a, map_b=map_b)


def _entries(manifest: dict) -> Dict[str, dict]:
    return {chunk["src"]: chunk for chunk in manifest.values() if chunk.get("isEntry")}


def test_clean_clone_builds_three_entries(built_clone: BuiltClone) -> None:
    """C9.01: exactly the three entries, each emitted as a non-empty file under dist/."""
    entries = _entries(built_clone.manifest())
    assert sorted(entries) == sorted(fh.ENTRY_SRCS.values()), sorted(entries)
    for src, chunk in entries.items():
        out = built_clone.dist / chunk["file"]
        assert out.is_file() and out.stat().st_size > 0, f"{src} -> {chunk['file']} missing or empty"


def test_build_is_reproducible(built_clone: BuiltClone) -> None:
    """C9.02: two builds give one digest map, and it equals the dist the tree commits."""
    assert built_clone.map_a, "the build produced no files"
    assert built_clone.map_a == built_clone.map_b, fh.diff_maps(built_clone.map_a, built_clone.map_b)
    committed = fh.committed_dist_map()
    assert built_clone.map_a == committed, (
        "rebuild differs from the committed dist/ (rebuild before committing)\n"
        + fh.diff_maps(built_clone.map_a, committed)
    )


def test_each_entry_emits_nonempty_css(built_clone: BuiltClone) -> None:
    """C9.03, build half of A9.6b: every entry owns a non-empty .css asset. Template half: see module docstring."""
    entries = _entries(built_clone.manifest())
    assert sorted(entries) == sorted(fh.ENTRY_SRCS.values())
    for src, chunk in entries.items():
        css = chunk.get("css") or []
        assert css, f"{src} emitted no CSS"
        for rel in css:
            path = built_clone.dist / rel
            assert path.suffix == ".css" and path.is_file() and path.stat().st_size > 0, f"{src}: {rel}"
    all_css = [tuple(sorted(chunk["css"])) for chunk in entries.values()]
    assert len(set(all_css)) == len(all_css), f"entries share a CSS asset: {all_css}"


def test_missing_entry_module_fails_build(built_clone: BuiltClone, tmp_path: Path) -> None:
    """C9.04: deleting an entry module fails the build and names the module."""
    ws = tmp_path / "ws"
    shutil.copytree(built_clone.root, ws, ignore=shutil.ignore_patterns("node_modules"), symlinks=True)
    (ws / "node_modules").symlink_to(built_clone.root / "node_modules", target_is_directory=True)
    (ws / "frontend" / fh.ENTRY_SRCS["settings"]).unlink()

    proc = _build(ws)
    assert proc.returncode != 0, "build tolerated a missing entry module\n" + fh.describe(proc)
    assert "settings/index.ts" in proc.stdout + proc.stderr, fh.describe(proc)
