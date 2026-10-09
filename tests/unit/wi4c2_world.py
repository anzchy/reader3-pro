"""Shared fixture module for 012 WI-4c.2 (matrix: .claude/tdd-guardian/tests-20261009-wi4c2.md, F-2).

Not a test file and not frozen. Order-addressed books, the route client and the reader-page parser the
4c.2 route cases share:

- ``text(o)`` -- the one text of the chapter whose ``order`` is ``o``. The ``-end`` delimiter keeps
  ``uniq-1-end`` from being a substring of ``uniq-10-end``.
- ``H(orders, o)`` / ``T(orders, o)`` -- the positional href and title ``wi2b_world`` gives that chapter.
- ``order_book(books, folder, orders)`` -- a **pkl** book (``book_fingerprint=None``) with ``toc=True``.
  Notes for it are always seeded with ``fp=ABSENT``, so ``fingerprints_agree`` holds and the refresh really
  runs ``_mark_orphans`` (FR-C).
- ``make_client(books)`` -- a ``TestClient`` over ``server.app``; the caller has already pointed
  ``reader3_app.web.server.BOOKS_DIR`` at ``books``.
- ``books_dir_patched(books)`` -- the context-managed ``BOOKS_DIR`` patch the Hypothesis cases use inside
  ``@given`` (no ``tmp_path`` / ``monkeypatch`` there; adversary round 2 item 3).
- ``nav_state(html, spine_len)`` -- ``(active, prev, next, disabled, indicator)`` read with the real
  ``data-testid`` selectors of ``reader.html`` (FR-A), with the TOC-count vacuity guard.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple
from unittest import mock

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from wi2b_world import write_book_pkl

from reader3_app import book_store, search_service
from reader3_app.web import server

BASE_URL = "http://127.0.0.1"
#: The dash the gap indicator renders: U+2013 EN DASH (coordinator ruling 2026-10-09).
GAP_DASH = "–"


def text(o: int) -> str:
    return f"text-of-order-{o} uniq-{o}-end"


def H(orders: Sequence[int], o: int) -> str:
    return f"Text/c{list(orders).index(o)}.xhtml"


def T(orders: Sequence[int], o: int) -> str:
    return f"T{list(orders).index(o)}"


def order_book(books: Path, folder: str, orders: Sequence[int], *, toc: bool = True) -> Path:
    """``write_book_pkl(books, folder, [text(o) ...], None, orders=orders, toc=toc)``; returns the book dir."""
    write_book_pkl(books, folder, [text(o) for o in orders], None, orders=list(orders), toc=toc)
    return Path(books) / folder


def clear_caches() -> None:
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_cached.cache_clear()


def make_client(books: Path) -> TestClient:
    clear_caches()
    return TestClient(server.app, base_url=BASE_URL)


@contextlib.contextmanager
def books_dir_patched(books: Path) -> Iterator[TestClient]:
    """Inside ``@given``: patch ``BOOKS_DIR`` (literal target) and the env, clear both caches, yield a client.

    Also chdirs into ``books.parent`` for the duration (restored after), as the fixtures' ``monkeypatch.chdir``
    does: ``server.book_uuid_resolver`` was built from the import-time relative ``"books"``, so without it the
    uuid mint's ``.locks/`` would land in the cwd's ``books/``. ``books`` must be named ``books``.
    """
    assert Path(books).name == "books", books
    env = {k: v for k, v in os.environ.items() if k not in ("READER3_TOKEN", "READER3_ALLOWED_HOSTS")}
    cwd = os.getcwd()
    os.chdir(Path(books).parent)
    try:
        with mock.patch("reader3_app.web.server.BOOKS_DIR", str(books)), mock.patch.dict(
            os.environ, env, clear=True
        ):
            yield make_client(books)
    finally:
        os.chdir(cwd)
        clear_caches()


def nav_state(
    html: str, spine_len: int
) -> Tuple[List[str], Optional[str], Optional[str], List[str], str]:
    soup = BeautifulSoup(html, "html.parser")
    toc_links = soup.select("a.toc-link")
    assert len(toc_links) == spine_len, (len(toc_links), spine_len)
    active = [a["data-file-href"] for a in soup.select("a.toc-link.active")]
    prev_a = soup.select_one("[data-testid=rd-chapter-prev]")
    next_a = soup.select_one("[data-testid=rd-chapter-next]")
    disabled = [s.get_text(strip=True) for s in soup.select("[data-testid=rd-chapter-nav] span.nav-btn.disabled")]
    assert (prev_a is None) == ("Previous" in disabled), (prev_a, disabled)
    assert (next_a is None) == ("Next" in disabled), (next_a, disabled)
    count = soup.select_one("[data-testid=rd-chapter-count]")
    assert count is not None
    indicator = " ".join(count.get_text().split())
    prev_href = str(prev_a["href"]) if prev_a is not None else None
    next_href = str(next_a["href"]) if next_a is not None else None
    return [str(a) for a in active], prev_href, next_href, disabled, indicator


def chapter_index_in_script(html: str) -> int:
    m = re.search(r"chapterIndex:\s*(-?\d+)\s*,", html)
    assert m is not None
    return int(m.group(1))


def total_chapters_in_script(html: str) -> int:
    m = re.search(r"totalChapters:\s*(\d+)\s*,", html)
    assert m is not None
    return int(m.group(1))
