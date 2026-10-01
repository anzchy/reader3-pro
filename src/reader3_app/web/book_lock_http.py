"""The book lock at the HTTP boundary (018 WI-2, ADR-0015 contract items 4-6).

One place maps the three lock outcomes for every route, the same way
``server._notes_file_error_handler`` covers every notes call site:

  * ``BookLockBusy``  → 409 + ``Retry-After``; the body names the holder category.
    Deliberately not the version-conflict 409 shape (no ``etag``, different
    ``detail``), so a client can tell "someone is importing / deleting this book,
    retry" from "your copy is stale, re-read".
  * ``BookChanged``   → 409 with its own detail and no ``Retry-After``: retrying
    cannot help, the book under this name is not the one the page was opened on.
  * ``BookGone``      → 404, same detail as every other missing-book 404.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..book_lock import BookChanged, BookGone, BookLockBusy

BUSY_DETAIL_PREFIX = "book busy"
CHANGED_DETAIL = "book changed: reload before writing"


async def _busy(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BookLockBusy)
    retry_after = max(1, int(exc.retry_after))
    return JSONResponse(
        status_code=409,
        content={
            "detail": f"{BUSY_DETAIL_PREFIX}: {exc.holder_category}",
            "holder_category": exc.holder_category,
            "retry_after": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


async def _changed(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": CHANGED_DETAIL})


async def _gone(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Book not found"})


def install(app: FastAPI) -> None:
    app.add_exception_handler(BookLockBusy, _busy)
    app.add_exception_handler(BookChanged, _changed)
    app.add_exception_handler(BookGone, _gone)
