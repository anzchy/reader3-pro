"""A corrupt book at the HTTP boundary (012 WI-3.2, Q3/Q4): one central mapping for ``BookCorrupt``.

``book_store`` raises ``book_format.BookCorrupt`` when a book's ``manifest.json`` exists but cannot be trusted, and
``server.load_book_cached`` lets exactly that class through. Single-book routes therefore answer here:

  * HTML routes (``response_class=HTMLResponse``, i.e. ``/read/*``) → 500 with a plain page;
  * every other route (notes, search, highlight, AI, …) → 500 ``{"detail": "Book storage is corrupt",
    "state": "corrupt"}``.

The body is fixed text, never ``str(exc)``: no path, no folder name, no traceback reaches the client. Nothing is
logged here — the one ERROR is written at the raise site in ``book_store``. Listing routes guard per book and never
reach this handler.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute

from ..book_format import BookCorrupt

CORRUPT_DETAIL = "Book storage is corrupt"

_CORRUPT_PAGE = (
    "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>Book storage is corrupt</title></head>"
    "<body><h1>Book storage is corrupt</h1>"
    "<p>This book's stored files are damaged and cannot be opened. Re-import the book to repair it.</p>"
    "<p><a href=\"/\">Back to library</a></p></body></html>\n"
)


def _is_html_route(request: Request) -> bool:
    """Decided by the matched route's declared response class, not by URL prefix or ``Accept``."""
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return False
    response_class = route.response_class
    return isinstance(response_class, type) and issubclass(response_class, HTMLResponse)


async def _corrupt(request: Request, exc: Exception) -> Response:
    if _is_html_route(request):
        return HTMLResponse(status_code=500, content=_CORRUPT_PAGE)
    return JSONResponse(status_code=500, content={"detail": CORRUPT_DETAIL, "state": "corrupt"})


def install(app: FastAPI) -> None:
    app.add_exception_handler(BookCorrupt, _corrupt)
