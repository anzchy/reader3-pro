"""012 WI-4c.3a route level: ``/api/search/*`` emits the ADR-0016 order; corrupt orders give the DP-7 500.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c3.md`` r2, cases SR-01..SR-04. Binding: coordinator ruling OQ-2
-- the central 500 applies to per-book search (every mode) and highlight; library search keeps its per-book
``failed_books`` (200).

Every case is an in-process ``TestClient`` over a real tmp ``BOOKS_DIR`` (real pickles, real routers, real Jinja
reader page). The only double is ``reader3_app.vector_search.BookVectorIndex`` in the semantic/hybrid legs, paired
with ``tests/unit/test_search_order.py::test_so_10_*`` (real ChromaDB). The CB-01 body is spelled out, not imported.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from wi4c2_world import H, chapter_index_in_script, make_client, nav_state, order_book
from wi4c3_world import VecStub, book

CORRUPT_JSON = {"detail": "Book storage is corrupt", "state": "corrupt"}
ORDERS = {"g02_data": [0, 2], "g13_data": [1, 3]}


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


def _bump_mtime(pkl: Path) -> None:
    t = os.stat(pkl).st_mtime_ns
    os.utime(pkl, ns=(t, t + 10**9))


def _assert_links_land_on_the_hit(client: TestClient, results: list) -> None:
    assert results
    for r in results:
        page = client.get(f"/read/{r['book_id']}/{r['chapter_order']}", follow_redirects=False)
        assert page.status_code == 200, r
        assert chapter_index_in_script(page.text) == r["chapter_order"]
        assert nav_state(page.text, 2)[0] == [H(ORDERS[r["book_id"]], r["chapter_order"])], r


def test_sr_01_route_search_emits_orders_and_every_link_lands_on_the_hit(client: TestClient, books: Path) -> None:
    for folder, orders in ORDERS.items():
        order_book(books, folder, orders)

    r = client.get("/api/search/g02_data", params={"q": "uniq-2-end"})
    assert r.status_code == 200
    got = [(x["chapter_order"], x["chapter_title"], x["match_text"], x["position"]) for x in r.json()["results"]]
    assert got == [(2, "T1", "uniq-2-end", 16)]

    for folder, orders in ORDERS.items():
        r = client.get(f"/api/search/{folder}", params={"q": "text-of-order"})
        assert r.status_code == 200
        results = r.json()["results"]
        assert [x["chapter_order"] for x in results] == orders
        _assert_links_land_on_the_hit(client, results)

    r = client.get("/api/search/library", params={"q": "text-of-order", "max_results_per_book": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["failed_books"] == []
    for folder, orders in ORDERS.items():
        assert [x["chapter_order"] for x in body["grouped_by_book"][folder]] == orders
        _assert_links_land_on_the_hit(client, body["grouped_by_book"][folder])
    _assert_links_land_on_the_hit(client, body["results"])


def test_sr_02_corrupt_orders_give_the_dp7_500_per_book_and_failed_books_in_library(
    client: TestClient, books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book(books, "x21_data", ["uniq-a", "uniq-b"], [2, 1])
    book(books, "x00_data", ["uniq-a", "uniq-b"], [0, 0])
    book(books, "xb_data", ["", "  "], [2, 1])
    order_book(books, "g02_data", [0, 2])
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([0]))
    modes = ("keyword", "semantic", "hybrid")

    for bid in ("x21_data", "x00_data", "xb_data"):
        for m in modes:
            r = client.get(f"/api/search/{bid}", params={"q": "uniq", "mode": m})
            assert (bid, m, r.status_code, r.json()) == (bid, m, 500, CORRUPT_JSON)

    for m in modes:
        r = client.get("/api/search/library", params={"q": "uniq", "mode": m, "max_results_per_book": 10})
        assert r.status_code == 200, m
        assert sorted(r.json()["failed_books"]) == ["x00_data", "x21_data", "xb_data"], m

    r = client.get("/api/search/library", params={"q": "uniq-2-end", "max_results_per_book": 10})
    assert r.status_code == 200
    g02 = r.json()["grouped_by_book"]["g02_data"]
    assert g02 and {x["chapter_order"] for x in g02} <= {0, 2}


def test_sr_03_a_repaired_book_is_searchable_without_a_restart(client: TestClient, books: Path) -> None:
    book(books, "x21_data", ["uniq-a", "uniq-b"], [2, 1])
    r = client.get("/api/search/x21_data", params={"q": "uniq-b"})
    assert (r.status_code, r.json()) == (500, CORRUPT_JSON)

    pkl = book(books, "x21_data", ["uniq-a", "uniq-b"], [1, 2])
    _bump_mtime(pkl)
    r = client.get("/api/search/x21_data", params={"q": "uniq-b"})
    assert r.status_code == 200
    assert [(x["chapter_order"], x["chapter_title"]) for x in r.json()["results"]] == [(2, "T1")]


def test_sr_04_orders_are_rederived_after_a_republish_in_both_modes(
    client: TestClient, books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([1]))

    def both() -> tuple:
        sem = client.get("/api/search/rp_data", params={"q": "zzz-nomatch", "mode": "semantic"})
        kw = client.get("/api/search/rp_data", params={"q": "uniq", "mode": "keyword"})
        assert (sem.status_code, kw.status_code) == (200, 200)
        return (
            [(x["chapter_order"], x["match_text"]) for x in sem.json()["results"]],
            [(x["chapter_order"], x["match_text"], x["position"]) for x in kw.json()["results"]],
        )

    order_book(books, "rp_data", [0, 2])
    assert both() == ([(2, "sem-pos-1")], [(0, "uniq", 16), (2, "uniq", 16)])

    order_book(books, "rp_data", [0, 3])
    _bump_mtime(books / "rp_data" / "book.pkl")
    assert both() == ([(3, "sem-pos-1")], [(0, "uniq", 16), (3, "uniq", 16)])
