"""013 WI-11 A11.3 (ET-9), case C11.04: `escapeHtml` has exactly one definition, in shared.

The scan counts **definitions**, not references. It is exercised against seeded trees with 0
and 2 definitions so that "exactly one" cannot be passed by a scanner that finds nothing.

The legacy half of A11.3 (the four local definitions in `static/*.js` deleted) is not done in
WI-11: those files are non-module IIFE scripts that cannot import `escape.ts`, and each one is
retired by the page WI that migrates it. It is recorded here as a strict xfail so the gap is
visible in every run and the marker has to be removed the moment the last copy goes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FE_SRC = ROOT / "frontend" / "src"
STATIC = ROOT / "src" / "reader3_app" / "web" / "static"
STATIC_EXCLUDE = ("vendor", "dist")

DEFINITION_RE = re.compile(
    r"\bfunction\s+escapeHtml\b"
    r"|\b(?:const|let|var)\s+escapeHtml\s*="
    r"|\bescapeHtml\s*:\s*(?:function\b|\()"
)
EXPORT_RE = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|const|let|var|class|type|interface)\s+(\w+)", re.M)
EXPORT_LIST_RE = re.compile(r"^\s*export\s*\{([^}]*)\}", re.M)


def definition_sites(root: Path, pattern: str) -> list[str]:
    sites: list[str] = []
    for path in sorted(root.glob(pattern)):
        rel = path.relative_to(root).as_posix()
        if any(part in STATIC_EXCLUDE for part in path.relative_to(root).parts):
            continue
        sites += [rel] * len(DEFINITION_RE.findall(path.read_text(encoding="utf-8")))
    return sites


def single_definition_problems(fe_src: Path) -> list[str]:
    sites = definition_sites(fe_src, "**/*.ts")
    if sites != ["shared/escape.ts"]:
        return [f"expected exactly one escapeHtml definition at shared/escape.ts, found {sites}"]
    return []


def test_frontend_has_exactly_one_definition_in_shared() -> None:
    assert single_definition_problems(FE_SRC) == []


def test_escape_module_exports_only_escape_html() -> None:
    text = (FE_SRC / "shared" / "escape.ts").read_text(encoding="utf-8")
    named = EXPORT_RE.findall(text)
    listed = [n.strip() for group in EXPORT_LIST_RE.findall(text) for n in group.split(",") if n.strip()]
    assert named + listed == ["escapeHtml"]


@pytest.mark.parametrize(
    ("files", "expected_sites"),
    [
        ({"shared/escape.ts": "export const x = 1;\n"}, []),
        (
            {
                "shared/escape.ts": "export function escapeHtml(v: unknown): string { return ''; }\n",
                "library/index.ts": "const escapeHtml = (s: string) => s;\n",
            },
            ["library/index.ts", "shared/escape.ts"],
        ),
        (
            {"shared/escape.ts": "export function escapeHtml(v: unknown): string { return ''; }\n"},
            ["shared/escape.ts"],
        ),
    ],
    ids=["seed-0-red", "seed-2-red", "seed-1-green"],
)
def test_scanner_on_seeded_trees(tmp_path: Path, files: dict[str, str], expected_sites: list[str]) -> None:
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    assert definition_sites(tmp_path, "**/*.ts") == expected_sites
    assert (single_definition_problems(tmp_path) == []) is (expected_sites == ["shared/escape.ts"])


def test_references_are_not_counted(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "escape.ts").write_text(
        "export function escapeHtml(v: unknown): string { return String(v ?? ''); }\n", encoding="utf-8"
    )
    (tmp_path / "page.ts").write_text(
        'import { escapeHtml } from "@shared/escape";\nel.innerHTML = escapeHtml(x);\n', encoding="utf-8"
    )
    assert definition_sites(tmp_path, "**/*.ts") == ["shared/escape.ts"]


def test_scanner_sees_both_legacy_styles_and_skips_vendor(tmp_path: Path) -> None:
    # Guards the xfail below from being vacuous: the two legacy spellings (group A and B) are
    # both definitions to this scanner, and vendor/dist are out of scope.
    (tmp_path / "a.js").write_text("(() => {\n  function escapeHtml(text) {\n  }\n})();\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("const escapeHtml = (str) => String(str || '');\n", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "c.js").write_text("function escapeHtml(x) {}\n", encoding="utf-8")
    assert definition_sites(tmp_path, "**/*.js") == ["a.js", "b.js"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A11.3 legacy half deferred: static/settings.js -> WI-12 (done: deleted), static/library-search.js -> WI-13 (done: deleted), "
        "static/search.js + static/ai.js -> reader migration in 014 (WI-16). IIFE scripts cannot import "
        "escape.ts and WI-11 does not edit static/. Remove this marker when the last copy is deleted."
    ),
)
def test_legacy_static_definitions_removed() -> None:
    assert definition_sites(STATIC, "**/*.js") == []
