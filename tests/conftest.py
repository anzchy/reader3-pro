"""Shared pytest fixtures for the reader3 test suite.

Lane layout (see .claude/tdd-guardian/config.json):
    tests/unit/      in-process, no I/O beyond tmp_path
    tests/contract/  FastAPI TestClient against the real router tree
    tests/e2e/       Playwright against a live server
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


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
