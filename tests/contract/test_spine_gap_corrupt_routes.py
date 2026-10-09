"""012 WI-4c.2 CB-01: non-strict chapter orders reach every 4c.2 order-resolving route as the DP-7 500.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c2.md`` Unit H. On a book whose orders are not strictly
increasing (``[0, 2, 2]``), the 4c.1 helpers raise ``BookCorrupt``; the routes must let it reach the central
``book_corrupt_http`` handler and write nothing -- never degrade to ``orders = []`` (a blank 200 reader,
mass-orphaned notes, or never-orphaned notes).

The fixed HTML page is spelled out here rather than imported: it is the response contract, and importing the
constant would let a change to it pass unnoticed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from wi2b_world import ABSENT, disk, rec, seed_notes
from wi4c2_world import make_client, order_book

X3 = "x3_data"
CORRUPT_PAGE = (
    "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>Book storage is corrupt</title></head>"
    "<body><h1>Book storage is corrupt</h1>"
    "<p>This book's stored files are damaged and cannot be opened. Re-import the book to repair it.</p>"
    "<p><a href=\"/\">Back to library</a></p></body></html>\n"
)
CORRUPT_JSON = {"detail": "Book storage is corrupt", "state": "corrupt"}


@pytest.fixture
def books(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    b = tmp_path / "books"
    b.mkdir()
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(b))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)
    monkeypatch.chdir(tmp_path)
    return b


@pytest.fixture
def corrupt_client(books: Path) -> Iterator[TestClient]:
    with make_client(books) as c:
        yield c


def test_cb_01_non_strict_orders_give_the_dp7_500_on_every_order_resolving_route(
    corrupt_client: TestClient, books: Path
) -> None:
    d = order_book(books, X3, [0, 2, 2])
    seed_notes(d, [rec("v0", 0, "vanished", book_id=X3)], fp=ABSENT)
    raw0, mtime0, _ = disk(d)

    for path in (f"/read/{X3}/0", f"/read/{X3}"):
        r = corrupt_client.get(path, follow_redirects=False)
        assert r.status_code == 500, path
        assert r.headers["content-type"].startswith("text/html"), path
        assert r.text == CORRUPT_PAGE, path

    legs = [
        ("GET", f"/api/notes/{X3}/0", None),
        ("GET", f"/api/notes/{X3}", None),
        ("POST", f"/api/notes/{X3}/0", {"type": "marker", "quote": "uniq-0-end"}),
        ("PUT", f"/api/notes/{X3}/0/v0", {"note_text": "n"}),
    ]
    for method, path, body in legs:
        r = corrupt_client.request(method, path, json=body)
        assert (method, path, r.status_code, r.json()) == (method, path, 500, CORRUPT_JSON)

    raw1, mtime1, parsed = disk(d)
    assert (raw1, mtime1) == (raw0, mtime0)
    assert parsed is not None
    assert [(a["id"], a["orphaned"]) for a in parsed["annotations"]] == [("v0", False)]
