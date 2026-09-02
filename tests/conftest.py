"""Shared pytest fixtures for the reader3 test suite.

Lane layout (see .claude/tdd-guardian/config.json):
    tests/unit/         in-process, no I/O beyond tmp_path
    tests/contract/     FastAPI TestClient against the real router tree
    tests/integration/  builds and installs a wheel, starts a real server (@slow)
    tests/e2e/          Playwright against a live server
"""

import os
import re
import sys
from pathlib import Path

import pytest

# Marker names that are pytest's own expression grammar, not markers.
_MARKEXPR_KEYWORDS = {"and", "or", "not", "True", "False", "None"}
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# `-m "marker(name='x')"` is legal in pytest 8+; the kwargs inside the parens are
# not marker names, so they are stripped before identifiers are extracted.
_MARK_ARGS_RE = re.compile(r"\([^()]*\)")


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Reject unknown marker names inside `-m` expressions.

    `--strict-markers` (see pyproject) only validates markers *applied to items*;
    it does not look at the `-m` expression at all. So `-m baseline_1b_typo`
    silently deselects everything and exits 5 -- "no tests collected", which reads
    like an empty group rather than a typo. That is exactly how a soak run comes to
    count the empty set (policy-core completion bar #1: a lane that discovered zero
    tests is a failure, not a pass). This hook supplies the half `--strict-markers`
    does not cover; the two together make a misspelt marker loud on both sides.

    `trylast` is not cosmetic. Plugins register their markers from inside their own
    `pytest_configure` via `addinivalue_line`, and a conftest is registered late
    enough that its hook would otherwise run FIRST -- before pytest-playwright has
    declared `only_browser` / `skip_browser` / `browser_context_args`. Running early
    makes every plugin marker look unknown, so `-m only_browser` dies with a bogus
    UsageError. Measured: without `trylast`, `pytest tests/e2e -m only_browser`
    exits 4 naming a marker that is perfectly real.
    """
    markexpr = str(getattr(config.option, "markexpr", "") or "")
    if not markexpr.strip():
        return
    known = {line.split(":", 1)[0].split("(", 1)[0].strip() for line in config.getini("markers")}
    stripped = _MARK_ARGS_RE.sub(" ", markexpr)
    unknown = sorted(
        {
            name
            for name in _IDENT_RE.findall(stripped)
            if name not in _MARKEXPR_KEYWORDS and name not in known
        }
    )
    if unknown:
        raise pytest.UsageError(
            "unknown marker(s) in -m expression: "
            + ", ".join(unknown)
            + ". Register them in [tool.pytest.ini_options].markers, or fix the spelling. "
            "Without this check the run would deselect everything and report "
            "'no tests collected', which is indistinguishable from an empty group."
        )

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Make tests/fixtures/*.py importable as plain modules (epub_builder, ...).
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def books_dir(tmp_path: Path) -> Path:
    """An isolated books/ root.

    Never point a test at the real books/ directory: process_epub() calls
    shutil.rmtree() on its output dir before writing anything, which would
    destroy real annotations, AI metadata and vector indexes.
    """
    d = tmp_path / "books"
    d.mkdir()
    return d
