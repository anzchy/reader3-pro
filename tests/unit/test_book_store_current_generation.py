"""012 WI-2b.4: ``book_store.current_generation`` -- the current generation, read for rebind.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases R4-01 … R4-06 (critical path: 100% lines).

The law: read-only and consistent with ``book_fingerprint``. ``current_generation(b, d) is None`` iff
``book_fingerprint(b, d) is None``; otherwise ``.fingerprint == book_fingerprint(b, d)``,
``.chapter_count == len(manifest.chapters)`` and ``chapter_text(i)`` is the text of ``manifest.chapters[i]``
by position (R-3: never by the ``order`` field).

Every case runs against real generations (``book_format.publish`` under the real EX book lock) in ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
from pathlib import Path
from typing import List

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from book_format_helpers import REPAIRABLE, snapshot
from wi2b_world import FP_A, flip_chapter_byte, gen_inputs, pkl_book, publish_gen

from reader3_app import book_format, book_lock, book_store

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


# --------------------------------------------------------------------------- R4-06 (WI-3.3 O3-12)
#
# Matrix: ``.claude/tdd-guardian/tests-20261009-wi3.md`` case O3-12. The first fixtures anywhere with
# ``order != position``: ``chapter_text(i)`` must read ``manifest.chapters[i]`` by position (R-3), never by order.


def _publish_with_orders(books_dir: Path, texts: List[str], orders: List[int]) -> None:
    inputs = gen_inputs(texts, FP_A, "A")
    inputs = dataclasses.replace(inputs, chapters=tuple(
        dataclasses.replace(c, order=o) for c, o in zip(inputs.chapters, orders)))
    (books_dir / G).mkdir()
    with book_lock.acquire(str(books_dir), G, mode=book_lock.EXCLUSIVE, holder="import"):
        book_format.publish(books_dir / G, inputs)


def test_r4_06_chapter_text_is_positional_on_gapped_orders(books: Path) -> None:
    _publish_with_orders(books, TEXTS, [0, 2, 5])
    before = snapshot(books / G)

    g = book_store.current_generation(G, str(books))

    assert g is not None
    assert g.chapter_count == 3
    assert g.chapter_text(1) == "t1 one"  # the chapter whose order is 2
    assert g.chapter_text(2) == "t2 two"
    assert [g.chapter_text(i) for i in range(3)] == TEXTS
    assert snapshot(books / G) == before


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(xs=st.lists(st.integers(0, 50), min_size=1, max_size=5, unique=True).map(sorted))
def test_r4_06_chapter_text_is_positional_on_gapped_orders_property(xs: List[int]) -> None:
    texts = [f"text-{i}-{x}" for i, x in enumerate(xs)]
    with tempfile.TemporaryDirectory() as d:
        books_dir = Path(d)
        _publish_with_orders(books_dir, texts, xs)
        m = book_format.validate_stat(books_dir / G)
        assert [e.order for e in m.chapters] == xs
        gen_dir = books_dir / G / "gen" / str(m.generation)

        g = book_store.current_generation(G, str(books_dir))

        assert g is not None
        assert g.chapter_count == len(xs)
        for i in range(len(xs)):
            assert g.chapter_text(i) == texts[i] == book_format.read_chapter(gen_dir, m.chapters[i]).text
