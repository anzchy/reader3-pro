"""012 WI-4c.3b route level: ``POST /api/highlight/{book_id}/{chapter_order}`` addresses a chapter by its order.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c3.md`` r2, cases HR-01..HR-04. Binding: coordinator rulings
2026-10-09 (WI-4c.3) -- negative / gap / past-the-end order -> 404 ``{"detail": "Chapter not found"}``; corrupt
orders -> the central DP-7 500 (OQ-2); a blank term stays 200 with empty ranges.

Every case is an in-process ``TestClient`` over a real tmp ``BOOKS_DIR`` (real pickles, real routers). HR-03 runs
the real ``process_epub`` on a synthetic gap EPUB. No doubles. The CB-01 body is spelled out, not imported.

Green-first by design: HR-04 (blank-term guard). HR-01, HR-02 (non-blank legs at n=2) and HR-03 are red against
the 4c.3a commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator

import pytest
from fastapi.testclient import TestClient
from gap_epub import SVG, XHTML, GapItem, build_gap_epub
from wi4c2_world import assert_locks_under, chapter_index_in_script, make_client, nav_state, order_book
from wi4c3_world import book

from reader3_app import reader3

CORRUPT_JSON = {"detail": "Book storage is corrupt", "state": "corrupt"}
NOT_FOUND = {"detail": "Chapter not found"}
EMPTY = {"ranges": [], "total_matches": 0, "selected_occurrence_index": None}


def R(s: int, e: int) -> Dict[str, Any]:
    return {"start": s, "end": e, "start_utf16": s, "end_utf16": e, "style": "search-match", "occurrence_index": 0}


def ONE(s: int, e: int) -> Dict[str, Any]:
    return {"ranges": [R(s, e)], "total_matches": 1, "selected_occurrence_index": 0}


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
def client(books: Path) -> Iterator[TestClient]:
    with make_client(books) as c:
        yield c


def _post(client: TestClient, bid: str, n: int, term: str, occ: Any = None) -> tuple:
    body: Dict[str, Any] = {"search_term": term}
    if occ is not None:
        body["occurrence_index"] = occ
    r = client.post(f"/api/highlight/{bid}/{n}", json=body)
    return r.status_code, r.json()


# --------------------------------------------------------------------------- HR-01


HR01_TABLE = [
    ("g02_data", 2, "uniq-2-end", 200, ONE(16, 26)),
    ("g02_data", 0, "uniq-2-end", 200, EMPTY),
    ("g02_data", 1, "uniq-2-end", 404, NOT_FOUND),
    ("g02_data", 3, "uniq-2-end", 404, NOT_FOUND),
    ("g02_data", -1, "uniq-2-end", 404, NOT_FOUND),
    ("g13_data", 1, "order-1", 200, ONE(8, 15)),
    ("g13_data", 3, "uniq-3-end", 200, ONE(16, 26)),
    ("g13_data", 1, "uniq-3-end", 200, EMPTY),
    ("g13_data", 0, "x", 404, NOT_FOUND),
    ("g13_data", 2, "x", 404, NOT_FOUND),
    ("g13_data", 4, "x", 404, NOT_FOUND),
]


def test_hr_01_route_table_on_gapped_books(client: TestClient, books: Path) -> None:
    order_book(books, "g02_data", [0, 2])
    order_book(books, "g13_data", [1, 3])
    for bid, n, term, status, body in HR01_TABLE:
        assert (bid, n, term, *_post(client, bid, n, term)) == (bid, n, term, status, body)


# --------------------------------------------------------------------------- HR-02


def test_hr_02_corrupt_orders_give_the_central_500_and_blank_stays_200(client: TestClient, books: Path) -> None:
    book(books, "x21_data", ["uniq-a", "uniq-b"], [2, 1])
    book(books, "x00_data", ["uniq-a", "uniq-b"], [0, 0])
    for bid in ("x21_data", "x00_data"):
        for n in (0, 1, 2):
            assert (bid, n, *_post(client, bid, n, "uniq")) == (bid, n, 500, CORRUPT_JSON)
    assert _post(client, "x21_data", 1, "  ") == (200, EMPTY)


# --------------------------------------------------------------------------- HR-03 (real pipeline)


def test_hr_03_gap_epub_search_highlight_and_read_share_one_address(
    client: TestClient, books: Path, tmp_path: Path
) -> None:
    epub = build_gap_epub(tmp_path / "g.epub", [
        GapItem("a", "a.xhtml", XHTML, "CH-A-MARKER"),
        GapItem("p", "p.svg", SVG, "GAP-PAGE-MARKER"),
        GapItem("b", "b.xhtml", XHTML, "CH-B-MARKER"),
    ])
    reader3.process_epub(str(epub), str(books / "gap_data"))
    assert (books / "gap_data" / "book.pkl").exists()
    assert_locks_under(tmp_path)

    r = client.get("/api/search/gap_data", params={"q": "CH-B-MARKER"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert [x["chapter_order"] for x in results] == [2]
    hit = results[0]

    status, body = _post(client, "gap_data", hit["chapter_order"], "CH-B-MARKER", 0)
    assert status == 200, body
    assert body["ranges"][0]["start"] == hit["position"]
    assert body["ranges"][0]["end"] - body["ranges"][0]["start"] == len("CH-B-MARKER")
    assert (body["total_matches"], body["selected_occurrence_index"]) == (1, 0)

    assert _post(client, "gap_data", 1, "CH-B-MARKER", 0) == (404, NOT_FOUND)

    page = client.get(f"/read/gap_data/{hit['chapter_order']}", follow_redirects=False)
    assert page.status_code == 200
    assert chapter_index_in_script(page.text) == 2
    active = nav_state(page.text, 2)[0]
    assert len(active) == 1 and active[0].endswith("b.xhtml"), active

    r = client.get("/api/search/gap_data", params={"q": "GAP-PAGE-MARKER"})
    assert (r.status_code, r.json()["results"]) == (200, [])


# --------------------------------------------------------------------------- HR-04 (blank term, guard)


def test_hr_04_blank_term_at_gap_negative_and_past_end_is_200_empty(client: TestClient, books: Path) -> None:
    order_book(books, "g02_data", [0, 2])
    legs = [(n, t) for n in (1, 3) for t in ("", " ")] + [(-1, " ")]
    for n, t in legs:
        assert (n, t, *_post(client, "g02_data", n, t)) == (n, t, 200, EMPTY)
