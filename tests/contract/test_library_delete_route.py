"""018 WI-5c: ``DELETE /api/library/{book_id}`` (matrix cases C-1 .. C-10b, C-12, C-14).

Law 4:
- ``GET /api/library`` shows a book either fully or not at all.
- The status mapping is total: 204, 400, 404 or 409.
- ``DeleteRefused`` maps to 409 with no ``Retry-After``; busy maps to 409 with ``Retry-After``.

Every case has its own books directory, with the ``BOOKS_DIR``, resolver and
``load_ai_settings`` seams patched. Books are created *after* the client has started,
so the startup uuid scan never mints into a fixture whose ``ai_meta.json`` is the
point of the case (C-7).

Green at red, excluded from the WI-5c receipt:
- C-4's ``..%2Fa_data`` id (Starlette's converter 404, before any handler);
- C-9(b), a separate function (existing ``writer_scope`` behaviour).
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from fastapi.testclient import TestClient

from book_lock_workers import spawn_ctx
from delete_world import (
    ABSENT,
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    U,
    U2,
    V,
    ZERO_UUID,
    Child,
    Fault,
    Holder,
    World,
    conv,
    conv_payload,
    dot_entries,
    hold_ex_rename_on_go,
    intents,
    ld,
    make_book,
    new_world,
    put_file,
    raw_conv,
    read_collections,
    seat_resolver,
    tombstones,
    tree_bytes,
    under,
    write_book_pkl,
    write_collections,
)
from reader3_app import book_lock, search_service
from reader3_app.web import server

BASE_URL = "http://127.0.0.1"
WAIT_S = 10.0
JOIN_S = 15.0
FULL_KEYS = {"book_id", "title", "authors", "cover_url", "book_uuid"}
ZERO_NAME = f"{ZERO_UUID}.json"


# --------------------------------------------------------------------------- fixture


@dataclass
class RouteWorld:
    w: World
    client: TestClient
    prefs: Dict[str, Any]

    @property
    def books(self) -> Path:
        return self.w.books

    @property
    def R(self) -> Path:
        return self.w.R


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def rw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouteWorld]:
    """A books dir under ``proj/``; the conversation root setting is ``convroot`` (= ``w.R``)."""
    w = new_world(tmp_path / "proj")
    monkeypatch.setattr(server, "BOOKS_DIR", str(w.books))
    seat_resolver(monkeypatch, w.books)
    prefs: Dict[str, Any] = {"conversation_disk_storage": "per_book", "conversation_project_root_dir": "convroot"}

    def _settings(*_a: Any, **_kw: Any) -> Dict[str, Any]:
        from reader3_app.ai.config import default_settings_dict

        settings = default_settings_dict()
        settings["preferences"] = {**(settings.get("preferences") or {}), **prefs}
        return settings

    monkeypatch.setattr(server, "load_ai_settings", _settings)
    _clear_caches()
    try:
        with TestClient(app=server.app, base_url=BASE_URL) as client:
            yield RouteWorld(w=w, client=client, prefs=prefs)
    finally:
        _clear_caches()


# --------------------------------------------------------------------------- helpers


def _put_conversation(rw: RouteWorld, book_uuid: str, cid: str, text: str) -> None:
    resp = rw.client.put(
        f"/api/ai/conversations/{book_uuid}/{cid}",
        json={
            "provider": "anthropic",
            "model": "m",
            "created_at": "2026-08-01T00:00:00Z",
            "last_updated": D_MID,
            "messages": [
                {"id": f"m-{cid[:8]}", "role": "user", "content": text, "timestamp": D_MID, "metadata": {}}
            ],
        },
    )
    assert resp.status_code == 200, f"precondition: PUT conversation -> {resp.status_code} {resp.text}"


def _c1_setup(rw: RouteWorld) -> Dict[str, bytes]:
    """``a_data`` (U) + ``b_data`` (V); two conversations saved through PUT; ``c1:[a_data,b_data]``."""
    make_book(rw.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U)
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    _put_conversation(rw, U, CID_FRESH, "first turn")
    _put_conversation(rw, U, CID_COLLIDE, "second turn")
    write_collections(rw.w.coll, {"c1": ["a_data", "b_data"]})
    conv_dir = rw.books / "a_data" / "ai_conversations"
    saved = {n: (conv_dir / n).read_bytes() for n in sorted(os.listdir(conv_dir))}
    assert sorted(saved) == sorted([f"{CID_FRESH}.json", f"{CID_COLLIDE}.json"]), saved
    return saved


def _library(rw: RouteWorld) -> List[Dict[str, Any]]:
    resp = rw.client.get("/api/library")
    assert resp.status_code == 200, resp.text
    return resp.json()["books"]


def _library_ids(rw: RouteWorld) -> List[str]:
    return [b["book_id"] for b in _library(rw)]


def _entry(books: List[Dict[str, Any]], book_id: str) -> Dict[str, Any]:
    found = [b for b in books if b.get("book_id") == book_id]
    assert len(found) == 1, books
    return found[0]


def _detail(resp) -> Any:
    try:
        return resp.json().get("detail")
    except ValueError:
        return None


def _stats_total(rw: RouteWorld) -> int:
    resp = rw.client.get("/api/library/stats")
    assert resp.status_code == 200, resp.text
    return resp.json()["books_total"]


def _search_matches(rw: RouteWorld, book_id: str, term: str) -> int:
    resp = rw.client.get(f"/api/search/{book_id}", params={"q": term})
    assert resp.status_code == 200, resp.text
    return resp.json()["total_matches"]


def _reader_title(rw: RouteWorld, title: str) -> bool:
    resp = rw.client.get("/read/a_data/0")
    assert resp.status_code == 200, resp.text
    return f"<title>{title} - Reader3 Pro</title>" in resp.text


def _recreate_equal_stat(books: Path, old: os.stat_result, *, book_uuid: str) -> None:
    """Re-create ``a_data`` ("Omega" / "BBBB bravo", same pickle size) with the old ``book.pkl`` mtime."""
    d = books / "a_data"
    d.mkdir()
    pkl = write_book_pkl(d, title="Omega", body="BBBB bravo")
    (d / "ai_meta.json").write_text('{"book_uuid": "%s"}' % book_uuid, encoding="utf-8")
    os.utime(pkl, ns=(old.st_atime_ns, old.st_mtime_ns))
    new = os.stat(pkl)
    assert (new.st_mtime_ns, new.st_size) == (old.st_mtime_ns, old.st_size), "precondition: equal book.pkl stat"


# =========================================================================== C-1


def test_c1_delete_false_204_conserves_and_unlists(rw):
    """C-1: default mode -> 204 empty; library ``[b_data]``; ``c1 == [b_data]``; ``R/U`` holds both conversations."""
    saved = _c1_setup(rw)

    resp = rw.client.delete("/api/library/a_data")

    assert (resp.status_code, resp.content) == (204, b""), resp.text
    published = rw.R / U
    assert {
        "library": _library_ids(rw),
        "collections": read_collections(rw.w.coll),
        "R/U": {n: (published / n).read_bytes() for n in sorted(os.listdir(published))} if published.is_dir() else None,
        "dot_entries": dot_entries(rw.books),
    } == {
        "library": ["b_data"],
        "collections": {"c1": ["b_data"]},
        "R/U": saved,
        "dot_entries": [],
    }


# =========================================================================== C-2


@pytest.mark.parametrize(
    "value, removes",
    [("true", True), ("TRUE", True), ("True", True), ("false", False), ("FALSE", False)],
)
def test_c2_delete_true_removes_conversations_and_parsing_is_case_insensitive(rw, value, removes):
    """C-2 (W5-8): ``true``/``TRUE``/``True`` -> 204, ``R/U`` absent; ``false``/``FALSE`` -> 204, ``R/U`` conserved."""
    saved = _c1_setup(rw)

    resp = rw.client.delete(f"/api/library/a_data?delete_conversations={value}")

    assert resp.status_code == 204, resp.text
    published = rw.R / U
    got = {n: (published / n).read_bytes() for n in sorted(os.listdir(published))} if published.is_dir() else None
    assert os.path.lexists(published) is (not removes)
    assert got == (None if removes else saved)
    assert _library_ids(rw) == ["b_data"]


# =========================================================================== C-3


def test_c3_unknown_book_404_and_retry_after_success_404(rw):
    """C-3: (a) ``nope_data`` -> 404 "Book not found"; (b) delete twice -> 204 then 404 "Book not found"."""
    make_book(rw.books, "a_data", book_uuid=U)

    missing = rw.client.delete("/api/library/nope_data")
    assert (missing.status_code, _detail(missing)) == (404, "Book not found"), missing.text

    first = rw.client.delete("/api/library/a_data")
    second = rw.client.delete("/api/library/a_data")
    assert (first.status_code, second.status_code, _detail(second)) == (204, 404, "Book not found"), (
        first.text,
        second.text,
    )


# =========================================================================== C-4

C4_CASES = [
    pytest.param("/api/library/notabook", 400, None, id="notabook"),
    pytest.param("/api/library/.a_data.deleted-1-abcdef12", 400, None, id="tombstone-name"),
    pytest.param("/api/library/a_data?delete_conversations=maybe", 400, None, id="q-maybe"),
    pytest.param("/api/library/a_data?delete_conversations=", 400, None, id="q-empty"),
    pytest.param("/api/library/a_data?delete_conversations=1", 400, None, id="q-1"),
    pytest.param("/api/library/a_data?delete_conversations=yes", 400, None, id="q-yes"),
    # Green at red, excluded: the ``[^/]+`` converter rejects it before any handler.
    pytest.param("/api/library/..%2Fa_data", 404, "Not Found", id="encoded-slash"),
]


@pytest.mark.parametrize("path, status, exact_detail", C4_CASES)
def test_c4_invalid_id_and_bad_query(rw, path, status, exact_detail):
    """C-4 (W5-8): bad ids and non-boolean queries -> 400 with a detail; ``a_data`` byte-identical."""
    make_book(rw.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    before = tree_bytes(rw.books / "a_data")

    resp = rw.client.delete(path)

    assert resp.status_code == status, resp.text
    detail = _detail(resp)
    if exact_detail is None:
        assert isinstance(detail, str) and detail, resp.text
    else:
        assert detail == exact_detail, resp.text
    assert tree_bytes(rw.books / "a_data") == before


# =========================================================================== C-5


@pytest.mark.parametrize("category", ["reindex", "conversations"])
def test_c5_busy_is_409_with_retry_after_and_book_intact(rw, tmp_path, category):
    """C-5 (W5-19): an SH holder -> 409 ``book busy: <cat>``, ``Retry-After`` == body ``retry_after`` > 0."""
    make_book(rw.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    before = tree_bytes(rw.books / "a_data")

    holder = Holder(str(rw.books), "a_data", book_lock.SHARED, category, str(tmp_path))
    holder.start()
    try:
        resp = rw.client.delete("/api/library/a_data")
    finally:
        holder.release()

    assert resp.status_code == 409, resp.text
    body = resp.json()
    header = resp.headers.get("Retry-After")
    assert header is not None and header.isdigit(), resp.headers
    assert int(header) > 0
    assert int(header) == body.get("retry_after")
    assert body.get("detail") == f"book busy: {category}"
    assert tree_bytes(rw.books / "a_data") == before
    assert intents(rw.books) == []


# =========================================================================== C-6


@pytest.mark.parametrize("root_setting", ["/abs/elsewhere", "../out"])
def test_c6_invalid_conversation_root_refuses_409(rw, root_setting):
    """C-6 (Q2): an invalid root -> (a) default mode 409 "conversation root", no Retry-After;
    (b) ``=true`` 204; (c) a book with no conversations 204."""
    rw.prefs["conversation_project_root_dir"] = root_setting
    make_book(rw.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    before = tree_bytes(rw.books / "a_data")

    refused = rw.client.delete("/api/library/a_data")
    assert refused.status_code == 409, refused.text
    assert "conversation root" in str(_detail(refused)), refused.text
    assert "Retry-After" not in refused.headers
    assert tree_bytes(rw.books / "a_data") == before
    assert intents(rw.books) == []

    forced = rw.client.delete("/api/library/a_data?delete_conversations=true")
    assert forced.status_code == 204, forced.text

    no_convs = rw.client.delete("/api/library/b_data")
    assert no_convs.status_code == 204, no_convs.text


# =========================================================================== C-7

C7_META = [
    pytest.param("../x", id="dotdot-x"),
    pytest.param(ABSENT, id="absent"),
    pytest.param(b"{not json", id="not-json"),
    pytest.param({"book_uuid": 7}, id="int-uuid"),
]


@pytest.mark.parametrize("meta", C7_META)
def test_c7_malformed_uuid_refuses_409_in_false_mode(rw, meta):
    """C-7 (Q3, G5): a book with conversations and an unusable ai_meta uuid -> 409 "uuid"; book and
    ai_meta unchanged. (b) on the ``../x`` row: ``=true`` -> 204 and nothing at ``R/../x``."""
    make_book(rw.books, "a_data", book_uuid=meta, convs=[conv(CID_FRESH, D_MID, "kept")])
    before = tree_bytes(rw.books / "a_data")

    refused = rw.client.delete("/api/library/a_data")
    assert refused.status_code == 409, refused.text
    assert "uuid" in str(_detail(refused)), refused.text
    assert tree_bytes(rw.books / "a_data") == before

    if meta == "../x":
        forced = rw.client.delete("/api/library/a_data?delete_conversations=true")
        assert forced.status_code == 204, forced.text
        assert not os.path.lexists(os.path.join(str(rw.R), "..", "x"))


# =========================================================================== C-8


def test_c8_post_commit_failure_still_204_then_404_and_caches_cleared(rw, monkeypatch):
    """C-8 (Q-F, G9): a publish fault after the commit -> 204, stats one lower, then 404; an equal-stat
    re-create is served fresh; after the fault is gone a restart publishes ``R/U``, no dot-names."""
    make_book(rw.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    saved = (rw.books / "a_data" / "ai_conversations" / f"{CID_FRESH}.json").read_bytes()
    old = os.stat(rw.books / "a_data" / "book.pkl")
    assert _reader_title(rw, "Alpha")
    assert _search_matches(rw, "a_data", "alpha") > 0
    assert _stats_total(rw) == 2

    fault = Fault(monkeypatch, "replace", when=lambda _s, d: under(d, rw.R))

    first = rw.client.delete("/api/library/a_data")
    assert (first.status_code, first.content) == (204, b""), first.text
    assert fault.hits, "precondition: the publish into R was attempted (and failed)"
    assert _stats_total(rw) == 1
    again = rw.client.delete("/api/library/a_data")
    assert (again.status_code, _detail(again)) == (404, "Book not found"), again.text

    _recreate_equal_stat(rw.books, old, book_uuid=U2)
    assert _reader_title(rw, "Omega")
    assert _search_matches(rw, "a_data", "bravo") > 0
    assert _search_matches(rw, "a_data", "alpha") == 0

    fault.armed = False
    with TestClient(app=server.app, base_url=BASE_URL):
        pass

    assert {
        "R/U": (rw.R / U / f"{CID_FRESH}.json").read_bytes() if (rw.R / U / f"{CID_FRESH}.json").is_file() else None,
        "dot_entries": dot_entries(rw.books),
    } == {"R/U": saved, "dot_entries": []}


def _fault_books_dir_fsync_after_commit(monkeypatch: pytest.MonkeyPatch, books: Path) -> Dict[str, Any]:
    """A delegating ``os.fsync`` that raises EIO on a directory fsync of ``books`` once a tombstone
    is in it: the commit rename went through, only its durability step fails."""
    import errno

    from delete_world import fd_path

    m = ld()
    real = os.fsync
    books_real = os.path.realpath(books)
    state: Dict[str, Any] = {"armed": True, "hits": 0}

    def fsync(fd: int) -> None:
        try:
            path = fd_path(fd)
        except OSError:
            path = None
        if state["armed"] and path == books_real and any(m.parse_tombstone(n) for n in os.listdir(books_real)):
            state["hits"] += 1
            raise OSError(errno.EIO, os.strerror(errno.EIO), path)
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return state


def test_c8b_dir_fsync_failure_after_commit_rename_still_204_and_caches_cleared(rw, monkeypatch):
    """C-8b (audit 20261007 #3 / #15, FX37-1): the commit rename succeeds and the ``books_dir`` fsync
    after it raises EIO -> 204 (Q-F), stats one lower, then 404; an equal-stat re-create is served
    fresh (the caches were invalidated); after the fault is gone a restart sweep publishes ``R/U``."""
    make_book(rw.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    saved = (rw.books / "a_data" / "ai_conversations" / f"{CID_FRESH}.json").read_bytes()
    old = os.stat(rw.books / "a_data" / "book.pkl")
    assert _reader_title(rw, "Alpha")
    assert _search_matches(rw, "a_data", "alpha") > 0
    assert _stats_total(rw) == 2

    fault = _fault_books_dir_fsync_after_commit(monkeypatch, rw.books)

    first = rw.client.delete("/api/library/a_data")
    assert (first.status_code, first.content) == (204, b""), first.text
    assert fault["hits"], "precondition: the post-rename books_dir fsync was attempted (and failed)"
    assert _stats_total(rw) == 1
    again = rw.client.delete("/api/library/a_data")
    assert (again.status_code, _detail(again)) == (404, "Book not found"), again.text

    _recreate_equal_stat(rw.books, old, book_uuid=U2)
    assert _reader_title(rw, "Omega")
    assert _search_matches(rw, "a_data", "bravo") > 0
    assert _search_matches(rw, "a_data", "alpha") == 0

    fault["armed"] = False
    with TestClient(app=server.app, base_url=BASE_URL):
        pass

    assert {
        "R/U": (rw.R / U / f"{CID_FRESH}.json").read_bytes() if (rw.R / U / f"{CID_FRESH}.json").is_file() else None,
        "dot_entries": dot_entries(rw.books),
    } == {"R/U": saved, "dot_entries": []}


# =========================================================================== C-9


def test_c9a_reindex_holder_makes_delete_409(rw, tmp_path):
    """C-9(a) (D15): an SH ``reindex`` holder -> DELETE is 409 and the book is intact."""
    make_book(rw.books, "a_data", book_uuid=U)
    before = tree_bytes(rw.books / "a_data")

    holder = Holder(str(rw.books), "a_data", book_lock.SHARED, "reindex", str(tmp_path))
    holder.start()
    try:
        resp = rw.client.delete("/api/library/a_data")
    finally:
        holder.release()

    assert resp.status_code == 409, resp.text
    assert tree_bytes(rw.books / "a_data") == before


def test_c9b_reindex_waiting_on_a_delete_gets_404_and_creates_nothing(rw, tmp_path, monkeypatch):
    """C-9(b) (D15): a child holds EX on ``a_data``; a concurrent ``POST /api/index/a_data`` is
    proven to be *waiting on that lock* (it reached ``book_lock._sleep``) before the child renames
    the folder away and releases -> 404, no folder, no ``chroma_db``.

    Audit 20261007 #16 (FX37-10): the old version renamed on a 0.15 s timer, so on a slow runner
    the POST could arrive after the rename and get its 404 from the pre-lock check, never
    exercising the in-lock recheck. Now the order is a handshake, with no timing threshold.
    """
    make_book(rw.books, "a_data", book_uuid=U)
    away = ".a_data.away"
    ctx = spawn_ctx()
    ready, go = ctx.Event(), ctx.Event()
    result = str(tmp_path / "c9b-child.json")

    polled = threading.Event()
    real_sleep = book_lock._sleep

    def sleep_spy(seconds: float) -> None:
        polled.set()
        real_sleep(seconds)

    monkeypatch.setattr(book_lock, "_sleep", sleep_spy)
    box: Dict[str, Any] = {}

    def post() -> None:
        box["resp"] = rw.client.post("/api/index/a_data", json={"force_reindex": False})

    worker = threading.Thread(target=post, daemon=True)
    child = Child(hold_ex_rename_on_go, (str(rw.books), "a_data", away, ready, go, result), result).start()
    try:
        assert ready.wait(WAIT_S), "the EX child never became ready"
        worker.start()
        assert polled.wait(WAIT_S), "the POST never waited on the book lock"
        assert "resp" not in box, "the POST returned while the EX holder still had the lock"
        go.set()
        worker.join(WAIT_S)
        assert not worker.is_alive(), "the POST never returned after the EX holder released"
    finally:
        go.set()
        got = child.wait_result()
        child.reap()

    assert got == {"outcome": "released"}, got
    resp = box["resp"]
    assert resp.status_code == 404, resp.text
    assert not os.path.lexists(rw.books / "a_data")
    assert not os.path.lexists(rw.books / away / "chroma_db")


# =========================================================================== C-10


def _c10_setup(rw: RouteWorld) -> os.stat_result:
    make_book(rw.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U)
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    assert _stats_total(rw) == 2
    assert _library_ids(rw) == ["a_data", "b_data"]
    return os.stat(rw.books / "a_data" / "book.pkl")


def test_c10a_delete_invalidates_before_any_recreate(rw):
    """C-10a (G8): warmed stats (2) and library; DELETE; stats without ``fresh`` -> 1, library ``[b_data]``."""
    _c10_setup(rw)

    resp = rw.client.delete("/api/library/a_data")
    assert resp.status_code == 204, resp.text

    assert (_stats_total(rw), _library_ids(rw)) == (1, ["b_data"])


def test_c10b_recreate_after_delete_is_served_fresh(rw):
    """C-10b (Q4): after the C-10a delete, an equal-stat re-create (new term, uuid U2) is served fresh."""
    old = _c10_setup(rw)
    assert _reader_title(rw, "Alpha")
    assert _search_matches(rw, "a_data", "alpha") > 0
    resp = rw.client.delete("/api/library/a_data")
    assert resp.status_code == 204, resp.text

    _recreate_equal_stat(rw.books, old, book_uuid=U2)

    assert _reader_title(rw, "Omega")
    assert _search_matches(rw, "a_data", "bravo") > 0
    assert _stats_total(rw) == 2
    assert _entry(_library(rw), "a_data").get("book_uuid") == U2


# =========================================================================== C-12

#: ``conv_published`` never fires in true mode (D-1, ``test_v1``): that pair is unreachable.
C12_CASES = [
    pytest.param(step, mode, id=f"{step}-{'true' if mode else 'false'}")
    for mode in (False, True)
    for step in (
        "swept",
        "locked",
        "intent_written",
        "committed",
        "fin_collections",
        "fin_caches",
        "conv_published",
        "conv_done",
        "rmtree_done",
        "intent_removed",
    )
    if not (mode and step == "conv_published")
]


@pytest.mark.parametrize("step, mode", C12_CASES)
def test_c12_no_partial_visibility_over_http_at_every_step(rw, monkeypatch, step, mode):
    """C-12 (law 4): paused at each step, ``GET /api/library`` lists ``a_data`` fully before
    ``committed`` and not at all from ``committed`` on; never an error entry or a dot-name."""
    make_book(rw.books, "a_data", title="Alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    m = ld()
    paused = threading.Event()
    resume = threading.Event()

    def pause_at(name: str) -> None:
        if name == step and not paused.is_set():
            paused.set()
            assert resume.wait(timeout=WAIT_S), "the main thread never resumed the delete"

    monkeypatch.setattr(m, "_STEP_HOOK", pause_at)
    url = "/api/library/a_data" + ("?delete_conversations=true" if mode else "")
    t1_result: Dict[str, Any] = {}

    def t1() -> None:
        try:
            t1_result["resp"] = rw.client.delete(url)
        except BaseException as exc:  # noqa: BLE001 - reported by the main thread
            t1_result["exc"] = exc

    thread = threading.Thread(target=t1, daemon=True)
    thread.start()
    try:
        # Bounded like ``paused.wait(timeout=10)``, but returns as soon as T1 is done:
        # a DELETE that finished without ever pausing is an assertion failure, not a wait.
        give_up = time.monotonic() + WAIT_S
        while not paused.is_set() and thread.is_alive() and time.monotonic() < give_up:
            paused.wait(0.02)
        assert paused.is_set(), f"the DELETE never paused at {step!r}: {t1_result!r}"
        books = _library(rw)
        index = rw.client.get("/")
    finally:
        resume.set()
    thread.join(timeout=JOIN_S)
    assert not thread.is_alive(), "the DELETE never finished"

    ids = [b.get("book_id") for b in books]
    assert all("error" not in b for b in books), books
    assert not any(str(i).startswith(".") for i in ids), ids
    if m.STEPS.index(step) < m.STEPS.index("committed"):
        assert ids == ["a_data", "b_data"], (step, books)
        assert all(set(b) == FULL_KEYS for b in books), books
        assert _entry(books, "a_data")["title"] == "Alpha"
    else:
        assert ids == ["b_data"], (step, books)
    assert index.status_code == 200, index.text[:400]
    assert "exc" not in t1_result, t1_result.get("exc")
    assert t1_result["resp"].status_code == 204, t1_result["resp"].text


# =========================================================================== C-14

C14_ROWS = {
    "syntax": raw_conv(ZERO_NAME, b"{trunc"),
    "traversal_cid": (ZERO_NAME, json.dumps(conv_payload(ZERO_UUID, D_MID, "t", conversation_id="../../x")).encode()),
    "undated": (ZERO_NAME, json.dumps(conv_payload(ZERO_UUID, ABSENT, "undated turn")).encode()),
}


@pytest.mark.parametrize(
    "row, force",
    [
        pytest.param("syntax", False, id="syntax"),
        pytest.param("traversal_cid", False, id="traversal_cid"),
        pytest.param("undated", False, id="undated"),
        pytest.param("syntax", True, id="syntax-true"),
    ],
)
def test_c14_unreadable_conversation_refuses_409_and_book_stays_listed(rw, row, force):
    """C-14 (W5-15, W5-17): an unreadable conversation refuses 409 with the pinned basename detail
    and leaves everything as it was; an undated one is readable (204, published byte-identical);
    ``=true`` skips the pre-scan (204, ``R/U`` absent)."""
    zero = C14_ROWS[row]
    make_book(rw.books, "a_data", title="Alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "valid"), zero])
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    book_before = tree_bytes(rw.books / "a_data")
    r_before = tree_bytes(rw.R)

    resp = rw.client.delete("/api/library/a_data" + ("?delete_conversations=true" if force else ""))

    if force:
        assert resp.status_code == 204, resp.text
        assert not os.path.lexists(rw.R / U)
        return
    if row == "undated":
        assert resp.status_code == 204, resp.text
        assert _library_ids(rw) == ["b_data"]
        assert (rw.R / U / ZERO_NAME).read_bytes() == zero[1]
        return

    assert resp.status_code == 409, resp.text
    assert "Retry-After" not in resp.headers
    detail = _detail(resp)
    assert detail == f"unreadable conversation file: {ZERO_NAME}", resp.text
    assert str(rw.books) not in str(detail)
    entry = _entry(_library(rw), "a_data")
    assert set(entry) == FULL_KEYS and entry["title"] == "Alpha", entry
    assert tree_bytes(rw.books / "a_data") == book_before
    assert tree_bytes(rw.R) == r_before
    assert (intents(rw.books), tombstones(rw.books)) == ([], [])


# =========================================================================== CP2 additions (WI-5 test-review gaps)


def test_c14_bad_target_array_refuses_409_and_book_stays_listed(rw):
    """C-14 (CP2 M2, W5-21): the existing ``R/U/CID_COLLIDE.json`` is valid JSON but ``[]`` (not an
    object) -> false-mode DELETE is 409 with no ``Retry-After``, the detail names the basename, and the
    book, R and the dot-names are exactly as before."""
    collide = f"{CID_COLLIDE}.json"
    make_book(
        rw.books,
        "a_data",
        title="Alpha",
        book_uuid=U,
        convs=[conv(CID_FRESH, D_MID, "valid"), conv(CID_COLLIDE, D_NEW, "collide-book")],
    )
    make_book(rw.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    put_file(rw.R / U / collide, b"[]")
    book_before = tree_bytes(rw.books / "a_data")
    r_before = tree_bytes(rw.R)

    resp = rw.client.delete("/api/library/a_data")

    assert resp.status_code == 409, resp.text
    assert "Retry-After" not in resp.headers
    detail = _detail(resp)
    assert detail == f"unreadable conversation file: {collide}", resp.text
    assert str(rw.books) not in str(detail)
    entry = _entry(_library(rw), "a_data")
    assert set(entry) == FULL_KEYS and entry["title"] == "Alpha", entry
    assert tree_bytes(rw.books / "a_data") == book_before
    assert tree_bytes(rw.R) == r_before
    assert (intents(rw.books), tombstones(rw.books)) == ([], [])


# =========================================================================== C-15 (audit 20261007 #1, FX37-3)


def test_c15_conversation_delete_during_a_book_delete_is_409_and_removes_nothing(rw, tmp_path):
    """C-15 (FX37-3, ADR-0018 amendment 2026-10-07): while a book delete holds EX on ``a_data``, a
    ``DELETE /api/ai/conversations/{U}/{cid}`` is refused like a save -- 409 ``book busy: delete``
    with ``Retry-After`` -- and the project-root copy is untouched; once the holder is gone it is 204."""
    rw.prefs["conversation_disk_storage"] = "project_root"
    make_book(rw.books, "a_data", book_uuid=U)
    _put_conversation(rw, U, CID_FRESH, "first turn")
    target = rw.R / U / f"{CID_FRESH}.json"
    assert target.is_file(), "precondition: the PUT wrote the project-root copy"
    before = target.read_bytes()

    holder = Holder(str(rw.books), "a_data", book_lock.EXCLUSIVE, "delete", str(tmp_path))
    holder.start()
    try:
        busy = rw.client.delete(f"/api/ai/conversations/{U}/{CID_FRESH}")
    finally:
        holder.release()
    header = busy.headers.get("Retry-After")

    after_busy = target.read_bytes() if target.is_file() else None
    done = rw.client.delete(f"/api/ai/conversations/{U}/{CID_FRESH}")

    assert {
        "busy": (busy.status_code, _detail(busy), header is not None and header.isdigit() and int(header) > 0),
        "kept": after_busy == before,
        "done": done.status_code,
        "gone": target.exists(),
    } == {
        "busy": (409, "book busy: delete", True),
        "kept": True,
        "done": 204,
        "gone": False,
    }
