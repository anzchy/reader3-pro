"""013 WI-11 A11.1 (ET-10), case C11.09: `no-console` is on and enforced over `frontend/src`.

Scope per ruling D3 (2026-09-24): "源码内" is the frontend source root `frontend/src` only; the
42 legacy `console.log` calls in `static/js/` are cleared by WI-14 / WI-16 when those files move.
D3 also adds the positive check: exactly one `debug` definition, in `frontend/src/shared/`.

ESLint is run for real (no mocks). Seeds are fed through `--stdin --stdin-filename` so they are
linted under the real config at a real `frontend/src` path without touching the tree. Inline
`eslint-disable` comments are switched off by config, so a seed cannot opt itself out.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FE_SRC = ROOT / "frontend" / "src"
ESLINT = ROOT / "node_modules" / ".bin" / "eslint"
TIMEOUT_S = 120

CONSOLE_LOG_RE = re.compile(r"\bconsole\s*\.\s*log\s*\(")
DEBUG_DEF_RE = re.compile(r"\bexport\s+(?:const|let|var|function)\s+debug\b|\b(?:const|let|var|function)\s+debug\b")


def _eslint(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    if not ESLINT.exists():
        pytest.fail(f"eslint is not installed at {ESLINT}; run npm ci")
    return subprocess.run(
        [str(ESLINT), *args], cwd=ROOT, input=stdin, capture_output=True, text=True, timeout=TIMEOUT_S
    )


def _lint_seed(body: str, filename: str = "frontend/src/shared/__seed__.ts") -> subprocess.CompletedProcess[str]:
    return _eslint("--stdin", "--stdin-filename", filename, stdin=body)


def test_zero_console_log_calls_in_frontend_src() -> None:
    hits = [
        f"{p.relative_to(ROOT).as_posix()}:{text.count(chr(10), 0, m.start()) + 1}"
        for p in sorted(FE_SRC.glob("**/*.ts"))
        for text in [p.read_text(encoding="utf-8")]
        for m in CONSOLE_LOG_RE.finditer(text)
    ]
    assert hits == []


def test_exactly_one_debug_definition_in_shared() -> None:
    sites = [
        p.relative_to(FE_SRC).as_posix()
        for p in sorted(FE_SRC.glob("**/*.ts"))
        for _ in DEBUG_DEF_RE.finditer(p.read_text(encoding="utf-8"))
    ]
    assert sites == ["shared/debug.ts"]


def test_no_console_rule_is_on_with_only_warn_and_error_allowed() -> None:
    proc = _eslint("--print-config", "frontend/src/library/index.ts")
    assert proc.returncode == 0, proc.stderr
    config = json.loads(proc.stdout)
    assert config["rules"]["no-console"] == [2, {"allow": ["warn", "error"]}]
    assert config["linterOptions"]["noInlineConfig"] is True


def test_eslint_passes_on_the_real_tree() -> None:
    proc = _eslint("--max-warnings", "0", "frontend/src")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_seeded_console_log_fails() -> None:
    proc = _lint_seed('export function f(): void {\n  console.log("x");\n}\n')
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "no-console" in proc.stdout


def test_seeded_console_log_cannot_disable_itself() -> None:
    body = '// eslint-disable-next-line no-console\nexport function f(): void {\n  console.log("x");\n}\n'
    proc = _lint_seed("/* eslint-disable */\n" + body)
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_seeded_console_log_in_debug_ts_still_fails() -> None:
    # debug.ts is allowed info/debug as its output sinks, never log.
    proc = _lint_seed('export function f(): void {\n  console.log("x");\n}\n', "frontend/src/shared/debug.ts")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "no-console" in proc.stdout


@pytest.mark.parametrize("method", ["info", "debug"])
def test_seeded_info_or_debug_outside_debug_ts_fails(method: str) -> None:
    proc = _lint_seed(f'export function f(): void {{\n  console.{method}("x");\n}}\n')
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_seeded_warn_and_error_pass() -> None:
    proc = _lint_seed('export function f(): void {\n  console.warn("w");\n  console.error("e");\n}\n')
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_package_json_exposes_the_lint() -> None:
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert scripts["lint:eslint"] == "eslint --max-warnings 0 frontend/src"
