"""013 WI-9 A9.12 (C9.15): the 0.8 token dangling-reference lint scans `frontend/src`.

Before this, `scripts/lint_token_refs.py` scanned designs/, static/**/*.css, templates and
the spec CSS fences — not the frontend source root, so every "0.8 passes" claim for
WI-1 #7 / WI-7 #3 / WI-10 was made over a directory the lint never read. The extension
is registered at the 0.8 definition site (MIG, the paragraph that says the scan set will
grow once more).
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
import pytest

import contract_lints as cl

MIG = cl.REPO_ROOT / "docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md"


@pytest.fixture(scope="module")
def lint():
    return cl.load(cl.TOKEN_REFS_LINT, "lint_token_refs_fe_under_test")


def test_scan_globs_cover_frontend_src(lint) -> None:
    assert "frontend/src/**/*.css" in lint.SCAN_GLOBS
    assert "frontend/src/**/*.ts" in lint.SCAN_GLOBS


def test_real_tree_scans_fe_files_and_passes(lint) -> None:
    scanned = {p.relative_to(cl.REPO_ROOT).as_posix() for p, _, _ in lint.sources(cl.REPO_ROOT)}
    fe_files = {p.relative_to(cl.REPO_ROOT).as_posix() for p in (cl.REPO_ROOT / "frontend/src").rglob("*") if p.suffix in {".css", ".ts"}}
    assert fe_files and fe_files <= scanned, sorted(fe_files - scanned)
    rc, out = cl.call_main(lint, ["--root", str(cl.REPO_ROOT)])
    assert rc == 0, out


_NAME = st.from_regex(r"--r3-[a-z][a-z0-9-]{0,20}", fullmatch=True).filter(lambda s: s != "--r3-ok")


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=_NAME, where=st.sampled_from(["frontend/src/p.css", "frontend/src/nested/q.ts"]))
def test_generated_dangling_names_are_reported(lint, tmp_path_factory, name: str, where: str) -> None:
    root = tmp_path_factory.mktemp("c915")
    cl.write(root, "frontend/src/defs.css", ":root { --r3-ok: 1px; }\n")
    body = f".a {{ gap: var({name}); }}\n" if where.endswith(".css") else f'export const s = "gap: var({name})";\n'
    cl.write(root, where, body)
    rc, out = cl.call_main(lint, ["--root", str(root)])
    assert rc == 1, out
    assert f"{where}:1: 悬空引用 {name}" in out, out


def test_fallback_form_is_reported(lint, tmp_path: Path) -> None:
    cl.write(tmp_path, "frontend/src/p.css", ":root { --r3-text: #000; }\n.a { color: var(--r3-text, #000); }\n")
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 1, out
    assert "带 fallback 的引用 --r3-text" in out, out


def test_control_passes(lint, tmp_path: Path) -> None:
    cl.write(tmp_path, "frontend/src/p.css", ":root { --r3-ok: 1px; }\n.a { gap: var(--r3-ok); }\n")
    rc, out = cl.call_main(lint, ["--root", str(tmp_path)])
    assert rc == 0, out


def test_extension_registered_at_mig_definition_site() -> None:
    text = MIG.read_text(encoding="utf-8")
    para = next(line for line in text.splitlines() if "扫描范围会再扩一次" in line)
    assert "frontend/src/" in para and "已落地" in para, para
