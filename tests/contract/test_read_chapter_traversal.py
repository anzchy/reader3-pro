"""WI-5: ``/read/{book_id}/{chapter_index}`` must validate ``book_id`` before ``pickle.load``.

``read_chapter`` was the only ``/read/*`` route that fed the raw path segment to
``load_book_cached`` — i.e. straight into ``os.path.join(BOOKS_DIR, book_id,
"book.pkl")`` and ``pickle.load``. Its ``os.path.basename`` call came *after* the
unpickle, so it sanitised the rendered URLs and nothing else.

**Why these tests do not use ``TestClient`` for the traversal vector.**
``TestClient`` goes through httpx, which resolves dot segments per RFC 3986
§5.2.4 before the request is built: ``client.get("/read/../0")`` leaves the test
process as ``GET /0`` and comes back 404 no matter what the route does. A test
written that way is green against the *vulnerable* code and proves nothing.
uvicorn does no such normalisation — it percent-decodes the target and hands the
literal path to the app — so the honest reproduction is to build the ASGI scope
uvicorn would build and call ``server.app`` directly. That is what
``_call_asgi`` does, and it is the whole reason this file exists as its own
module instead of a case in ``test_route_contracts.py``.

``%2F`` (P2) is the opposite situation: it *is* safely handled, but by the
router's ``[^/]+`` path converter rather than by any validation inside the
handler. It is asserted here so the division of labour is on record — deleting
the validation would leave P2 green, and only P1 turns red.
"""

from __future__ import annotations

import asyncio
import pickle
from pathlib import Path
from typing import Any

from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

from conftest import BOOK_ID, BOOK_TITLE, World

#: Title of the book planted one directory *above* the isolated library. Appears
#: nowhere else in the repo, so finding it in a response body is unambiguous
#: proof that a file outside BOOKS_DIR was opened, unpickled and rendered.
OUTSIDE_TITLE = "ONE LEVEL UP"


def _build_outside_book() -> Book:
    return Book(
        metadata=BookMetadata(
            title=OUTSIDE_TITLE,
            language="en",
            authors=["Nobody"],
            description="Planted outside the library root.",
        ),
        spine=[
            ChapterContent(
                id="outside_0",
                href="outside0.html",
                title="Outside Chapter",
                content="<p>secret contents of a file outside the library</p>",
                text="secret contents of a file outside the library",
                order=0,
            )
        ],
        toc=[TOCEntry(title="Outside Chapter", href="outside0.html", file_href="outside0.html", anchor="")],
        images={},
        source_file="outside.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


def _plant_book_one_level_up(project_root: Path) -> Path:
    """Write ``<project_root>/book.pkl``; BOOKS_DIR is ``<project_root>/books``.

    So ``os.path.join(BOOKS_DIR, "..", "book.pkl")`` resolves exactly here.
    """
    path = project_root / "book.pkl"
    with open(path, "wb") as f:
        pickle.dump(_build_outside_book(), f)
    return path


def _call_asgi(path: str) -> tuple[int, str]:
    """Deliver a request to ``server.app`` the way uvicorn would, verbatim path included.

    Returns ``(status, body_text)``. No httpx, no URL parsing, no dot-segment
    normalisation — the scope is what the ASGI server hands over.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("ascii"),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"127.0.0.1")],
        "client": ("1.1.1.1", 1),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
    }

    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(server.app(scope, receive, send))

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body.decode("utf-8", errors="replace")


# --- P1 -------------------------------------------------------------------


def test_read_chapter_traversal_does_not_reach_outside_books_dir(world: World) -> None:
    """P1: ``/read/../0`` must not unpickle and render ``<BOOKS_DIR>/../book.pkl``.

    Two assertions, and the second is the load-bearing one: a handler that
    rendered the outside book and *then* happened to return 404 would satisfy a
    status-code-only test while still having run ``pickle.load`` on an
    attacker-chosen path.
    """
    planted = _plant_book_one_level_up(world.project_root)
    assert planted.exists(), "fixture precondition: the outside book.pkl was not written"

    status, body = _call_asgi("/read/../0")

    assert OUTSIDE_TITLE not in body, (
        f"HTTP {status} and the response body contains {OUTSIDE_TITLE!r}, a book from "
        f"outside BOOKS_DIR: read_chapter unpickled an attacker-controlled path "
        f"(body length {len(body)})"
    )
    assert status == 404, f"expected 404 from the book_id whitelist, got {status}"


def test_read_chapter_traversal_rejects_before_unpickling(world: World, monkeypatch) -> None:
    """P1 (companion): the pickle is never opened at all, not merely hidden from the body.

    Asserting only on the body would still pass an implementation that loads the
    file and drops it — and ``pickle.load`` on an attacker-chosen file is the
    vulnerability, independent of what gets rendered afterwards.
    """
    _plant_book_one_level_up(world.project_root)

    loaded: list[str] = []
    real_loader = server.load_book_cached

    def _spy(folder_name: str):
        loaded.append(folder_name)
        return real_loader(folder_name)

    # The ``world`` fixture calls ``server.load_book_cached.cache_clear()`` on
    # teardown, and it shares this very MonkeyPatch instance — so the stand-in
    # has to keep the lru_cache surface or the fixture errors out while
    # unwinding, turning a clean red into a confusing one.
    _spy.cache_clear = real_loader.cache_clear  # type: ignore[attr-defined]

    monkeypatch.setattr(server, "load_book_cached", _spy)

    status, _body = _call_asgi("/read/../0")

    assert status == 404
    assert loaded == [], f"load_book_cached was reached with an unvalidated book_id: {loaded!r}"


# --- P2 -------------------------------------------------------------------


def test_encoded_slash_vector_is_stopped_by_the_router(world: World) -> None:
    """P2: ``..%2Fsecret_data`` never reaches the handler — the ``[^/]+`` converter rejects it.

    Recorded so nobody concludes from a green suite that the handler is
    unnecessary: this case would stay green with every validation deleted.
    """
    response = world.client.get("/read/..%2Fsecret_data/0")
    assert response.status_code == 404


# --- P3 -------------------------------------------------------------------


def test_valid_book_id_still_renders(world: World) -> None:
    """P3: the fix must be invisible to legitimate reads."""
    response = world.client.get(f"/read/{BOOK_ID}/0")
    assert response.status_code == 200
    assert BOOK_TITLE in response.text


def test_valid_book_id_still_renders_via_raw_asgi(world: World) -> None:
    """P3: and the same holds through the raw-scope driver, so P1's 404 is about ``..``.

    Without this, a driver that was simply broken (wrong scope keys, unrouted
    path) would make P1 pass for the wrong reason.
    """
    status, body = _call_asgi(f"/read/{BOOK_ID}/0")
    assert status == 200
    assert BOOK_TITLE in body
