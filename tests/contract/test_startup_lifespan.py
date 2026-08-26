"""The contract lane must actually run the ASGI lifespan.

``TestClient`` only runs startup/shutdown when it is entered as a context
manager. Constructing one and firing requests at it works fine — every request
opens its own portal — so a lane built on a bare ``TestClient(app=...)`` never
executes ``server._startup_scan_books`` and cannot tell whether that function
still exists.

The hard part is that the *end state* of the startup scan and of the lazy
``book_uuid_for_folder`` path is byte-identical: both call ``ensure_book_uuid``
and both write ``ai_meta.json``. So "``ai_meta.json`` exists for the book this
test asked about" proves nothing about lifespan.

The one observation that separates them is **a book nothing ever asked about**:
the startup scan resolves every ``*_data`` directory in the library, the lazy
path resolves only the folder that was named. These tests therefore seed their
own two-book library and send *no HTTP request at all* — the only thing that can
put an ``ai_meta.json`` next to ``untouched_data/book.pkl`` is the startup scan.

``TOUCHED_ID`` is not requested either; the pair exists so that a scan which
stopped after the first directory it happened to list would still be caught.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from reader3_app.ai.books import BookUuidResolver
from reader3_app.reader3 import Book, BookMetadata, ChapterContent
from reader3_app.web import server

#: Both names end in ``_data``; that suffix is what ``BookUuidResolver.scan``
#: keys on when it walks the library.
TOUCHED_ID = "touched_data"
UNTOUCHED_ID = "untouched_data"


@dataclass
class UntouchedLibrary:
    """A library on disk that no request has been sent about."""

    books_dir: Path

    def ai_meta(self, book_id: str) -> Path:
        return self.books_dir / book_id / "ai_meta.json"


def _seed_book(books_dir: Path, book_id: str) -> None:
    """A processed book directory, minus ``ai_meta.json``.

    Leaving the meta file out is the whole point: the assertions below are about
    who writes it, so seeding it would answer the question in the fixture.
    """
    out = books_dir / book_id
    out.mkdir(parents=True)
    book = Book(
        metadata=BookMetadata(title=f"Book {book_id}", language="en", authors=["Nobody"]),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title="Only Chapter",
                content="<p>Nothing reads this.</p>",
                text="Nothing reads this.",
                order=0,
            )
        ],
        toc=[],
        images={},
        source_file=f"{book_id}.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )
    with open(out / "book.pkl", "wb") as f:
        pickle.dump(book, f)


@pytest.fixture
def untouched_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[UntouchedLibrary]:
    """Two unresolved books, deliberately *not* the shared ``world`` library.

    Adding a second book to ``world`` would move every assertion in the lane that
    counts books, lists the library, or searches across books. This library is
    private to this module and never receives a request.

    Both patches are required: ``BookUuidResolver`` captured the old
    ``BOOKS_DIR`` in ``__init__``, so replacing the constant alone would leave
    the startup scan pointed at the developer's real library.
    """
    books_dir = tmp_path / "project" / "books"
    books_dir.mkdir(parents=True)
    _seed_book(books_dir, TOUCHED_ID)
    _seed_book(books_dir, UNTOUCHED_ID)

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(books_dir)))

    yield UntouchedLibrary(books_dir=books_dir)


def _assert_holds_a_uuid(meta_path: Path) -> None:
    """Existence is not enough — an empty or uuid-less file would still 'exist'."""
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    UUID(payload["book_uuid"])


# C1 -------------------------------------------------------------------------
def test_world_client_runs_asgi_lifespan(world) -> None:  # type: ignore[no-untyped-def]
    """The shared fixture's book is resolved once the client is live.

    This one cannot distinguish startup scan from lazy resolution — the fixture
    asks for the book's uuid itself, which writes the same file. It guards the
    fixture, not the scan; the discriminating power lives in C2.
    """
    meta_path = world.book_dir / "ai_meta.json"
    assert meta_path.exists(), f"{meta_path} was never written"
    _assert_holds_a_uuid(meta_path)
    assert UUID(world.book_uuid)

    # Measured, not assumed: with only the assertions above, reverting the
    # fixture's ``with`` leaves all 146 contract tests green -- C2 builds its own
    # client, so nothing in the lane guards the lane's own client. ``portal`` is
    # ``None`` until ``TestClient.__enter__`` runs and a ``BlockingPortal``
    # afterwards, which is the one difference visible from outside. It couples
    # this line to a starlette attribute; the trade is deliberate, and the
    # failure mode is a loud ``AttributeError`` on upgrade rather than a guard
    # that quietly stops guarding.
    assert world.client.portal is not None, (
        "the world fixture's TestClient was constructed but never entered, so "
        "the ASGI lifespan did not run for this lane -- see the fixture docstring"
    )


# C2 -------------------------------------------------------------------------
def test_startup_scan_resolves_untouched_books_before_any_request(
    untouched_library: UntouchedLibrary,
) -> None:
    """Entering the lifespan resolves the whole library, not just what was asked for."""
    with TestClient(app=server.app, base_url="http://127.0.0.1"):
        # No request is sent inside this block on purpose. Any ai_meta.json that
        # appears here was written by _startup_scan_books and by nothing else.
        untouched_meta = untouched_library.ai_meta(UNTOUCHED_ID)
        assert untouched_meta.exists(), (
            f"{untouched_meta} is missing: the startup scan did not run, or it "
            f"did not cover every *_data directory"
        )
        _assert_holds_a_uuid(untouched_meta)

        touched_meta = untouched_library.ai_meta(TOUCHED_ID)
        assert touched_meta.exists(), (
            f"{touched_meta} is missing: the scan stopped short of the whole library"
        )
        _assert_holds_a_uuid(touched_meta)


# C3 -------------------------------------------------------------------------
def test_without_lifespan_the_untouched_book_stays_unresolved(
    untouched_library: UntouchedLibrary,
) -> None:
    """Control group for C2: same seed, and the only variable is the ``with``.

    Without this, C2 is just "a file exists" and a seeding mistake would look
    exactly like a working startup scan.
    """
    TestClient(app=server.app, base_url="http://127.0.0.1")  # constructed, never entered -> no lifespan

    assert not untouched_library.ai_meta(UNTOUCHED_ID).exists(), (
        "ai_meta.json appeared without the lifespan; something other than the "
        "startup scan is resolving books, so C2 proves nothing about lifespan"
    )
    assert not untouched_library.ai_meta(TOUCHED_ID).exists()
