"""012 WI-4c.2 Unit F: which spine items ``process_epub`` turns into gaps (characterization).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c2.md`` SG-01..SG-05. No law: these pin third-party behaviour
(ebooklib 0.20.0 plus the reader3 spine loop, which keeps a document's raw OPF spine index as ``order`` and
skips anything that is missing or not ``ITEM_DOCUMENT``) for the commit evidence line. Cited alongside:
``test_reader3_fingerprint.py::test_r3_04*``.

Each case builds a synthetic EPUB with ``tests/fixtures/gap_epub.py`` and runs the real ``process_epub`` into a
tmp ``books/out_data``; the published generation is read back through ``book_store`` and ``book_format``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from ebooklib import epub
from gap_epub import HTML, SVG, XHTML, GapItem, build_gap_epub

from reader3_app import book_store, reader3
from reader3_app.reader3 import process_epub

A = GapItem("a", "a.xhtml", XHTML, "CH-A-MARKER")
B = GapItem("b", "b.xhtml", XHTML, "CH-B-MARKER")


def _spine(tmp_path: Path, items: Sequence[GapItem]) -> Tuple[List[int], List[str], Path]:
    books = tmp_path / "books"
    books.mkdir()
    epub_path = build_gap_epub(tmp_path / "g.epub", items)
    process_epub(str(epub_path), str(books / "out_data"))
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    try:
        book = book_store.load_book("out_data", str(books))
    finally:
        book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    spine = book.spine  # type: ignore[attr-defined]
    return [c.order for c in spine], [c.href for c in spine], books / "out_data"


def test_sg_01_svg_spine_item_between_two_xhtml_is_a_gap(tmp_path: Path) -> None:
    orders, hrefs, out = _spine(tmp_path, [A, GapItem("p", "p.svg", SVG, "GAP-PAGE-MARKER"), B])
    assert orders == [0, 2]
    assert hrefs == ["a.xhtml", "b.xhtml"]
    # Carried over from the 4c.1 adversary round 1 (Observation 2), as far as this HEAD allows: no production
    # path calls ``book_format.publish`` yet (``process_epub`` publishes ``book.pkl`` only), so there is no
    # manifest to compare. The other list the same spine loop feeds -- the fingerprint components (R6) -- must
    # carry exactly the Book's orders.
    epub_path = tmp_path / "g.epub"
    comps = reader3.fingerprint_components(epub_path, epub.read_epub(str(epub_path)))
    assert [o for _, o, _ in comps.spine] == orders
    assert (out / "book.pkl").is_file()


def test_sg_02_text_html_spine_item_is_a_gap(tmp_path: Path) -> None:
    orders, _, _ = _spine(tmp_path, [A, GapItem("g", "g.html", HTML, "GAP-PAGE-MARKER"), B])
    assert orders == [0, 2]


def test_sg_03_cover_property_xhtml_with_non_cover_id_is_a_gap(tmp_path: Path) -> None:
    # Trigger: manifest ``properties="cover"`` on an application/xhtml+xml item -> ebooklib EpubCoverHtml.
    titlepage = GapItem("titlepage", "t.xhtml", XHTML, "TITLE-PAGE-MARKER", props="cover")
    orders, hrefs, _ = _spine(tmp_path, [titlepage, A, B])
    assert orders == [1, 2]
    assert hrefs == ["a.xhtml", "b.xhtml"]


def test_sg_04_dangling_idref_leaves_a_gap(tmp_path: Path) -> None:
    ghost = GapItem("ghost", "ghost.xhtml", XHTML, "GHOST", in_manifest=False)
    orders, _, _ = _spine(tmp_path, [A, ghost, B])
    assert orders == [0, 2]


def test_sg_05_linear_no_xhtml_is_kept(tmp_path: Path) -> None:
    orders, hrefs, _ = _spine(tmp_path, [A, GapItem("n", "n.xhtml", XHTML, "NONLINEAR", linear=False), B])
    assert orders == [0, 1, 2]
    assert hrefs == ["a.xhtml", "n.xhtml", "b.xhtml"]
