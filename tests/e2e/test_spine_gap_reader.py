"""012 WI-4c.2 Unit G: a book with a spine gap, read through the real server and the real epub.js.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c2.md`` E2E-01..E2E-03. The server laws (R-1 totality, order
neighbours, the "Section – of M" gap indicator) are pinned in-process by RO-P1 / TB-P1; this module pins by
example what the user actually sees once epub.js takes over:

* **E2E-01** an out-of-range n (9) is a 200 page; ``display(undefined)`` falls back to the first section,
  ``syncLocationToUrl`` rewrites the URL to ``/0`` and the indicator ends as "Section 1 of 2". No error.
* **E2E-02** a gap n (1, a ``text/html`` spine item ebooklib does not extract) displays that gap section itself.
* **E2E-03** the last member order (2, spine position 1) renders its chapter -- a positional bound would 404.

The book is built with ``tests/fixtures/gap_epub.py`` (a, g.html, b) and run through the real ``process_epub``
into the session library as ``gap_data``; it is removed in a ``finally`` so later modules in the same session
see the library unchanged. ``e2e_books_dir`` / ``live_server`` are used read-only.

**Placement: the ``UNGROUPED_E2E_MODULES`` whitelist, no expiry.** The six group markers are bound one-to-one to
their directories: ``baseline_1b`` is frozen under ``suite_hash``, the ``acceptance_*`` groups are other features'
activation-staged gates, and ``shell_4a`` is 013's Phase-4A shell regression gate. A 012 storage-format check of
spine-gap addressing belongs to none of them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, List

import pytest
from playwright.sync_api import expect

from deg_assertions import remove_book_dir  # type: ignore[import-not-found]
from gap_epub import HTML, XHTML, GapItem, build_gap_epub  # type: ignore[import-not-found]
from helpers import pathname_is, reader_frame  # type: ignore[import-not-found]

GAP_BOOK_ID = "gap_data"
CH_A = "CH-A-MARKER"
GAP = "GAP-PAGE-MARKER"
CH_B = "CH-B-MARKER"
ITEMS = (
    GapItem("a", "a.xhtml", XHTML, CH_A),
    GapItem("g", "g.html", HTML, GAP),
    GapItem("b", "b.xhtml", XHTML, CH_B),
)


@pytest.fixture(scope="module")
def gap_book(e2e_books_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    from reader3_app.reader3 import process_epub

    epub_path = build_gap_epub(tmp_path_factory.mktemp("gap_epub") / "gap.epub", ITEMS)
    target = e2e_books_dir / GAP_BOOK_ID
    try:
        process_epub(str(epub_path), str(target))
        yield GAP_BOOK_ID
    finally:
        remove_book_dir(target)


def _body_text(frame: Any) -> str:
    return str(frame.locator("body").inner_text())  # lint-e2e-selectors: allow —— iframe 内是那本书自己的 XHTML


def _open(page: Any, url: str, errors: List[str]) -> Any:
    page.on("pageerror", lambda e: errors.append(str(e)))
    return page.goto(url)


def test_e2e_01_out_of_range_n_shows_the_first_section_and_rewrites_url(
    page: Any, live_server: str, gap_book: str
) -> None:
    errors: List[str] = []
    resp = _open(page, f"{live_server}/read/{gap_book}/9", errors)
    assert resp is not None and resp.status == 200
    frame = reader_frame(page, CH_A)
    assert GAP not in _body_text(frame)
    pathname_is(page, f"/read/{gap_book}/0")
    expect(page.get_by_test_id("rd-chapter-count")).to_have_text("Section 1 of 2")
    assert errors == []


def test_e2e_02_gap_n_displays_the_gap_section_itself(page: Any, live_server: str, gap_book: str) -> None:
    errors: List[str] = []
    resp = _open(page, f"{live_server}/read/{gap_book}/1", errors)
    assert resp is not None and resp.status == 200
    reader_frame(page, GAP)
    pathname_is(page, f"/read/{gap_book}/1")
    assert errors == []


def test_e2e_03_last_member_order_renders_its_chapter(page: Any, live_server: str, gap_book: str) -> None:
    errors: List[str] = []
    resp = _open(page, f"{live_server}/read/{gap_book}/2", errors)
    assert resp is not None and resp.status == 200
    reader_frame(page, CH_B)
    pathname_is(page, f"/read/{gap_book}/2")
    assert errors == []
