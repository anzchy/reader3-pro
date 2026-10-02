"""018 WI-5a: in-process caches after a delete (matrix cases K-1 .. K-4).

K-3 is a dependency pin and is green at red by design (excluded from the 5a receipt).
"""

from __future__ import annotations

import os
import threading

import pytest
from delete_world import (
    U,
    V,
    chroma_env,  # noqa: F401 - fixture
    ld,
    make_book,
    new_world,
    seat_resolver,
)

PROBE_EMBEDDING = [0.25] * 8
WAIT_S = 10.0
JOIN_S = 15.0


def _stats_totals(server):
    return [payload.get("books_total") for _ts, payload in list(server._stats_cache.values())]


# =========================================================================== K-1


def test_k1_stats_generation_discards_a_computation_that_spanned_a_delete(tmp_path, monkeypatch):
    """K-1: a stats GET blocked across a delete must not cache ``books_total == 2``."""
    from fastapi.testclient import TestClient

    from reader3_app.web import server
    m = ld()
    g0 = getattr(server, "_stats_generation")

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    make_book(w.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    monkeypatch.setattr(server, "BOOKS_DIR", str(w.books))
    seat_resolver(monkeypatch, w.books)

    inside = threading.Event()
    go = threading.Event()
    first = {"done": False}
    base_index = server.BookVectorIndex

    class BarrierIndex(base_index):  # type: ignore[misc, valid-type]
        def is_indexed(self):
            if not first["done"]:
                first["done"] = True
                inside.set()
                assert go.wait(timeout=WAIT_S), "the barrier was never released"
            return super().is_indexed()

    monkeypatch.setattr(server, "BookVectorIndex", BarrierIndex)
    server._stats_cache.clear()
    client = TestClient(app=server.app, base_url="http://127.0.0.1")
    t1_result = {}

    def t1():
        try:
            t1_result["resp"] = client.get("/api/library/stats")
        except BaseException as exc:  # noqa: BLE001 - reported by the main thread
            t1_result["exc"] = exc

    thread = threading.Thread(target=t1, daemon=True)
    try:
        thread.start()
        assert inside.wait(timeout=WAIT_S), "the stats computation never reached BookVectorIndex.is_indexed"
        try:
            m.delete_book(
                str(w.books),
                "a_data",
                delete_conversations=False,
                conversation_root=str(w.R),
                collections_path=str(w.coll),
            )
        finally:
            go.set()
        thread.join(timeout=JOIN_S)
        assert not thread.is_alive(), "the first stats request never finished"
        assert "exc" not in t1_result, t1_result.get("exc")

        second = client.get("/api/library/stats")
        assert second.status_code == 200, second.text
        assert second.json()["books_total"] == 1
        assert getattr(server, "_stats_generation") > g0
        assert 2 not in _stats_totals(server)
    finally:
        go.set()
        thread.join(timeout=JOIN_S)
        server._stats_cache.clear()


# =========================================================================== K-2


def test_k2_recreated_book_with_equal_stat_is_read_fresh(tmp_path):
    """K-2: delete, re-create with an equal-size book.pkl and the old mtime -> "bravo" is read."""
    from reader3_app import book_store, search_service

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", body="AAAA alpha", book_uuid=U)
    pkl = w.books / "a_data" / "book.pkl"
    book_store.load_book_cached("a_data", str(w.books))
    search_service.load_book_index("a_data", str(w.books), case_sensitive=False)
    assert search_service.search_book("a_data", search_service.SearchQuery(term="alpha"), books_dir=str(w.books)).results
    old = os.stat(pkl)

    w.delete(mode=False)

    make_book(w.books, "a_data", body="BBBB bravo", book_uuid=U)
    assert pkl.stat().st_size == old.st_size, "precondition: the re-created book.pkl must have an equal size"
    os.utime(pkl, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert pkl.stat().st_mtime_ns == old.st_mtime_ns

    assert book_store.load_book_cached("a_data", str(w.books)).spine[0].text == "BBBB bravo"
    assert search_service.search_book("a_data", search_service.SearchQuery(term="bravo"), books_dir=str(w.books)).results
    assert search_service.search_book("a_data", search_service.SearchQuery(term="alpha"), books_dir=str(w.books)).results == []


# =========================================================================== K-3


def test_k3_chromadb_private_registry_still_exists():
    """K-3: the private registry ``retire_chroma_system`` relies on is still there (green at red)."""
    from chromadb.api.shared_system_client import SharedSystemClient

    assert isinstance(SharedSystemClient._identifier_to_system, dict)
    assert callable(getattr(SharedSystemClient, "clear_system_cache", None))


# =========================================================================== K-4


def _client_add_query(chroma_path):
    import chromadb

    client = chromadb.PersistentClient(path=chroma_path)
    col = client.get_or_create_collection("k4_probe", embedding_function=None)
    col.add(ids=["1"], embeddings=[PROBE_EMBEDDING], documents=["k4"])
    return client, col


def _query(col):
    return list(col.query(query_embeddings=[PROBE_EMBEDDING], n_results=1)["ids"][0])


def _k4_setup(tmp_path, monkeypatch):
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U, chroma=True)
    seat_resolver(monkeypatch, w.books)
    chroma_path = os.path.realpath(str(w.books / "a_data" / "chroma_db"))
    return w, chroma_path


def test_k4a_index_delete_reimport_index_query_in_one_process(tmp_path, monkeypatch, chroma_env):  # noqa: F811
    """K-4(a): delete(true) retires the realpath-keyed system; a re-imported book indexes and queries."""
    from chromadb.api.shared_system_client import SharedSystemClient

    w, chroma_path = _k4_setup(tmp_path, monkeypatch)
    _client, col = _client_add_query(chroma_path)
    assert _query(col) == ["1"]
    assert chroma_path in SharedSystemClient._identifier_to_system

    w.delete(mode=True)

    assert chroma_path not in SharedSystemClient._identifier_to_system
    make_book(w.books, "a_data", book_uuid=U, chroma=True)
    _client2, col2 = _client_add_query(chroma_path)
    assert _query(col2) == ["1"]


def test_k4b_retirement_falls_back_when_the_private_registry_is_gone(tmp_path, monkeypatch, chroma_env):  # noqa: F811
    """K-4(b): with ``_identifier_to_system`` deleted, the delete still retires (fallback) and the query works."""
    from chromadb.api.shared_system_client import SharedSystemClient

    w, chroma_path = _k4_setup(tmp_path, monkeypatch)
    _client, col = _client_add_query(chroma_path)
    assert _query(col) == ["1"]

    with pytest.MonkeyPatch.context() as mp:
        mp.delattr(SharedSystemClient, "_identifier_to_system")
        w.delete(mode=True)
        make_book(w.books, "a_data", book_uuid=U, chroma=True)
        _client2, col2 = _client_add_query(chroma_path)
        assert _query(col2) == ["1"]
