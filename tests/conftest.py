"""Shared pytest fixtures for the reader3 test suite.

Lane layout (see .claude/tdd-guardian/config.json):
    tests/unit/         in-process, no I/O beyond tmp_path
    tests/contract/     FastAPI TestClient against the real router tree
    tests/integration/  builds and installs a wheel, starts a real server (@slow)
    tests/e2e/          Playwright against a live server
"""

import sys
from pathlib import Path

import pytest
from _pytest.mark.expression import IDENT_PREFIX, Expression

# `True` / `False` / `None` are legal identifiers in pytest's `-m` grammar and are
# evaluated as literals, not looked up as markers. `and` / `or` / `not` never reach
# here at all -- the parser turns them into operators, not identifiers.
_MARKEXPR_LITERALS = {"True", "False", "None"}


def _compile_markexpr(markexpr: str) -> Expression:
    """Parse a `-m` expression with pytest's own parser. Seam for the fail-closed test."""
    return Expression.compile(markexpr)


def _marker_names(markexpr: str) -> set[str]:
    """Every marker identifier in a `-m` expression.

    Extraction goes through pytest's own parser rather than a regex over the raw
    string, because the two things a regex has to tell apart look identical from
    the outside: `mark(name='x')` is a marker with keyword arguments (`name` is
    NOT a marker), while `(a or b)` is Boolean grouping (`a` and `b` both ARE).
    The previous implementation deleted every parenthesised run before extracting
    identifiers, so `-m "(baseline_1b_typo)"` reduced to the empty string, passed
    validation, and then silently selected zero tests -- the exact "green-looking
    empty set" this hook exists to prevent. Regression cases:
    `tests/unit/test_markexpr_guard.py`.

    `Expression.compile` builds a Python AST in which each marker identifier
    becomes a `Name` load prefixed with `IDENT_PREFIX`; those land in the compiled
    code object's `co_names`. Reading them there is exhaustive, which evaluating
    the expression against a recording matcher would not be -- `and` / `or` short
    circuit, so `a and (typo or b)` never asks about `b`.
    """
    try:
        compiled = _compile_markexpr(markexpr)
    except SyntaxError as exc:
        raise pytest.UsageError(
            f"-m expression is not valid pytest marker syntax: {markexpr!r} ({exc.msg})"
        ) from exc
    co_names = getattr(getattr(compiled, "_code", None), "co_names", None)
    names = {
        name[len(IDENT_PREFIX):]
        for name in (co_names or ())
        if isinstance(name, str) and name.startswith(IDENT_PREFIX)
    }
    if not names and markexpr.strip():
        # Fail closed. An empty result here means the extraction itself broke (a
        # pytest internal changed shape), and a broken extractor is indistinguishable
        # from "every marker in this expression is known" -- which would turn this
        # whole hook into a no-op without anything going red.
        raise pytest.UsageError(
            f"could not extract marker names from the -m expression {markexpr!r}. "
            "tests/conftest.py reads them out of pytest's own compiled match "
            "expression; that internal has probably changed shape. Fix the extractor "
            "(see tests/unit/test_markexpr_guard.py) -- do not skip the check, or a "
            "misspelt marker will again select zero tests and report a green empty set."
        )
    return names


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
    unknown = sorted(
        name
        for name in _marker_names(markexpr)
        if name not in _MARKEXPR_LITERALS and name not in known
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
