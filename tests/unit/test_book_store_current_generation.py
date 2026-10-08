"""012 WI-2b.4: ``book_store.current_generation`` -- the current generation, read for rebind.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases R4-01 … R4-05 (critical path: 100% lines).

The law: read-only and consistent with ``book_fingerprint``. ``current_generation(b, d) is None`` iff
``book_fingerprint(b, d) is None``; otherwise ``.fingerprint == book_fingerprint(b, d)``,
``.chapter_count == len(manifest.chapters)`` and ``chapter_text(i)`` is the text of ``manifest.chapters[i]``
by position (R-3: never by the ``order`` field).

Every case runs against real generations (``book_format.publish`` under the real EX book lock) in ``tmp_path``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from book_format_helpers import REPAIRABLE, snapshot
from wi2b_world import FP_A, flip_chapter_byte, pkl_book, publish_gen

from reader3_app import book_format, book_store

G = "g_data"
TEXTS = ["t0 zero", "t1 one", "t2 two"]


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def books(tmp_path: Path) -> Path:
    out = tmp_path / "books"
    out.mkdir()
    return out


def test_r4_01_fingerprint_count_and_position_indexed_texts(books: Path) -> None:
    publish_gen(books, G, TEXTS, FP_A, "A")
    before = snapshot(books / G)

    g = book_store.current_generation(G, str(books))

    assert g is not None
    assert g.fingerprint == FP_A
    assert g.fingerprint == book_store.book_fingerprint(G, str(books))
    assert g.chapter_count == 3
    assert [g.chapter_text(i) for i in range(3)] == TEXTS
    # Read-only: nothing under the book dir changed, reading every chapter included.
    assert snapshot(books / G) == before


def test_r4_01_texts_follow_the_manifest_position_not_a_fixed_order(books: Path) -> None:
    """A second generation with different texts: ``chapter_text(i)`` is the *current* manifest's i-th record."""
    publish_gen(books, G, TEXTS, FP_A, "A")
    publish_gen(books, G, ["n0", "n1"], "f" * 64, "B")

    g = book_store.current_generation(G, str(books))

    assert g is not None
    assert g.fingerprint == "f" * 64
    assert g.chapter_count == 2
    assert [g.chapter_text(i) for i in range(2)] == ["n0", "n1"]


def test_r4_02_missing_manifest_gives_none_silently(books: Path, caplog: pytest.LogCaptureFixture) -> None:
    pkl_book(books, "p_data", ["x"])
    caplog.set_level(logging.WARNING)

    assert book_store.current_generation("p_data", str(books)) is None
    assert book_store.current_generation("nope_data", str(books)) is None
    # The law: None exactly where book_fingerprint is None.
    assert book_store.book_fingerprint("p_data", str(books)) is None
    assert book_store.book_fingerprint("nope_data", str(books)) is None
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_r4_03_corrupt_manifest_gives_none(books: Path, tmp_path: Path) -> None:
    publish_gen(books, G, TEXTS, FP_A, "A")
    outside = tmp_path / "outside"
    outside.mkdir()
    REPAIRABLE["R-unparse"][0](books / G, outside)

    assert book_store.current_generation(G, str(books)) is None
    assert book_store.book_fingerprint(G, str(books)) is None


def test_r4_04_chapter_read_failure_surfaces_from_chapter_text(books: Path) -> None:
    publish_gen(books, G, TEXTS, FP_A, "A")
    flip_chapter_byte(books / G)

    g = book_store.current_generation(G, str(books))

    assert g is not None
    assert g.chapter_text(0) == "t0 zero"
    with pytest.raises((book_format.ChapterReadError, OSError)):
        g.chapter_text(1)


@pytest.mark.parametrize("bad_id", ["../escape_data", "a/b"])
def test_r4_05_traversal_id_is_refused_before_any_path_is_built(books: Path, bad_id: str) -> None:
    with pytest.raises(ValueError):
        book_store.current_generation(bad_id, str(books))
