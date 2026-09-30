"""018 WI-2 — the book lock at the HTTP boundary.

Cases W2-14(c), W2-34..W2-40, W2-46 and W2-56b(b) of
``.claude/tdd-guardian/tests-20260930-111748.md`` (ADR-0015 contract items 4, 5, 6).

Law:
  * lock-busy → 409 + ``Retry-After``, distinguishable from the version-conflict 409;
  * book gone → 404; book changed (ABA) → 409 with its own body;
  * the pre-existing ``RuntimeError``→400 / ``Exception``→500 index mappings stand;
  * no lock wait ever runs on the event-loop thread;
  * ``.locks`` is never a book.

The app is real (``TestClient`` / ``httpx.ASGITransport``); holders are real spawned
children; the only substitution is the embedding function on the index route
(plus ``_require_semantic_deps`` in W2-35(a), where "deps missing" is the scenario).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pickle
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from book_lock_workers import (
    CHILD_TIMEOUT_S,
    CHILD_WAIT_S,
    Child,
    HashEmbedder,
    Holder,
    outcome,
    try_exclusive,
)
from reader3_app import book_lock, notes_service, search_service, vector_search
from reader3_app.ai import books as ai_books
from reader3_app.ai.books import BookUuidResolver
from reader3_app.models.annotations import Annotation
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

BUDGET_S = 2.0
EPS_S = 0.75
JOIN_TIMEOUT_S = 30.0
#: Parked writer 1 gives up after this long (past the 2 s budget), so a request that
#: blocks instead of being refused fails on its assertions instead of hanging.
PARK_GUARD_S = 5.0
BOOK = "x_data"
QUOTE = "LOCK-ROUTE-QUOTE-SENTINEL-51c2"
CONFLICT_DETAIL = "Annotation version conflict"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"


def _build_book(title: str = "Lock Fixture") -> Book:
    return Book(
        metadata=BookMetadata(title=title, language="en", authors=["WI-2"], description="fixture"),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title="Chapter One",
                content=f"<p>{QUOTE} " + ("lorem ipsum " * 50) + "</p>",
                text=f"{QUOTE} " + ("lorem ipsum " * 50),
                order=0,
            )
        ],
        toc=[TOCEntry(title="Chapter One", href="chap0.html", file_href="chap0.html", anchor="")],
        images={},
        source_file="lock.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


def _write_pkl(book_dir: Path, title: str = "Lock Fixture") -> None:
    with open(book_dir / "book.pkl", "wb") as f:
        pickle.dump(_build_book(title), f)


def _write_meta(book_dir: Path, book_uuid: Optional[str]) -> None:
    meta = {} if book_uuid is None else {"book_uuid": book_uuid}
    (book_dir / ai_books.AI_META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")


def _meta_uuid(book_dir: Path) -> Optional[str]:
    path = book_dir / ai_books.AI_META_FILENAME
    return json.loads(path.read_text(encoding="utf-8")).get("book_uuid") if path.exists() else None


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@dataclass
class World:
    client: TestClient
    books_dir: Path

    @property
    def book_dir(self) -> Path:
        return self.books_dir / BOOK

    @property
    def notes_path(self) -> Path:
        return self.book_dir / notes_service.NOTES_FILENAME

    def notes_bytes(self) -> Optional[bytes]:
        return self.notes_path.read_bytes() if self.notes_path.exists() else None

    def quotes(self) -> List[str]:
        raw = self.notes_bytes()
        if raw is None:
            return []
        return [a["quote"] for a in json.loads(raw.decode("utf-8")).get("annotations") or []]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    books_dir = tmp_path / "books"
    (books_dir / BOOK).mkdir(parents=True)
    _write_pkl(books_dir / BOOK)
    _write_meta(books_dir / BOOK, U1)

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(tmp_path / "no_such_books_dir")))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(vector_search, "_build_embedding_function", lambda factory: HashEmbedder())

    _clear_caches()
    try:
        yield World(client=TestClient(server.app, base_url="http://127.0.0.1"), books_dir=books_dir)
    finally:
        _clear_caches()


def _create_body(quote: str = QUOTE) -> Dict[str, Any]:
    return {"type": "marker", "color": "yellow", "quote": quote}


def _seed_note(world: World) -> str:
    resp = world.client.post(f"/api/notes/{BOOK}/0", json=_create_body())
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


ROUTES = ["post", "put", "delete", "get_book", "get_chapter"]


def _call(client: Any, route: str, note_id: str):
    """One notes request. ``client`` is a TestClient or an httpx.AsyncClient."""
    if route == "post":
        return client.post(f"/api/notes/{BOOK}/0", json=_create_body())
    if route == "put":
        return client.put(f"/api/notes/{BOOK}/0/{note_id}", json={"note_text": "edited"})
    if route == "delete":
        return client.delete(f"/api/notes/{BOOK}/0/{note_id}")
    if route == "get_book":
        return client.get(f"/api/notes/{BOOK}")
    if route == "get_chapter":
        return client.get(f"/api/notes/{BOOK}/0")
    if route == "index":
        return client.post(f"/api/index/{BOOK}", json={"force_reindex": False})
    raise AssertionError(route)


def _assert_busy(resp: Any, category: str) -> None:
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert int(resp.headers["Retry-After"]) >= 1
    assert body["holder_category"] == category
    assert isinstance(body["retry_after"], int) and body["retry_after"] >= 1
    assert body["detail"] != CONFLICT_DETAIL
    assert "etag" not in body


def _assert_changed(resp: Any) -> None:
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("detail") != CONFLICT_DETAIL
    assert "etag" not in body
    assert "holder_category" not in body
    assert "Retry-After" not in resp.headers


@contextlib.contextmanager
def _interpose_acquire(monkeypatch: pytest.MonkeyPatch, before: Callable[[], None]) -> Iterator[List[int]]:
    real = book_lock.acquire
    fired: List[int] = []

    @contextlib.contextmanager
    def wrapper(*args: Any, **kwargs: Any) -> Iterator[None]:
        if not fired:
            fired.append(1)
            before()
        with real(*args, **kwargs):
            yield

    monkeypatch.setattr(book_lock, "acquire", wrapper)
    try:
        yield fired
    finally:
        monkeypatch.setattr(book_lock, "acquire", real)


# --------------------------------------------------------------------------- W2-14(c)


def test_w2_14c_http_writer_refused_while_another_writer_holds_the_resource_lock(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    parked = threading.Event()
    release_evt = threading.Event()
    real_save = notes_service.save_annotations

    def parked_save(books: str, book_id: str, annotations: List[Annotation]) -> None:
        if any(a.quote == "Q1" for a in annotations):
            parked.set()
            release_evt.wait(PARK_GUARD_S)
        return real_save(books, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", parked_save)
    w1: Dict[str, Any] = {}

    def writer1() -> None:
        try:
            notes_service.add_annotation_and_version(
                str(world.books_dir), Annotation(book_id=BOOK, chapter_index=0, quote="Q1")
            )
        except BaseException as exc:  # noqa: BLE001
            w1["error"] = type(exc).__name__

    t = threading.Thread(target=writer1, daemon=True)
    t.start()
    try:
        assert parked.wait(10.0), f"writer 1 never parked: {w1!r}"
        t0 = time.monotonic()
        resp = world.client.post(f"/api/notes/{BOOK}/0", json=_create_body("Q2"))
        elapsed = time.monotonic() - t0
    finally:
        release_evt.set()
        t.join(JOIN_TIMEOUT_S)
    assert "error" not in w1, w1
    _assert_busy(resp, "notes")
    assert BUDGET_S - 0.2 <= elapsed < BUDGET_S + EPS_S
    assert world.quotes() == ["Q1"]


# --------------------------------------------------------------------------- index route


def test_w2_34_index_route_with_an_ex_holder_is_409_with_retry_after(world: World, tmp_path: Path) -> None:
    with Holder(str(world.books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        resp = world.client.post(f"/api/index/{BOOK}", json={"force_reindex": False})
        elapsed = time.monotonic() - t0
    _assert_busy(resp, "import")
    assert elapsed < BUDGET_S + EPS_S
    assert not (world.book_dir / "chroma_db").exists()


def test_w2_35a_missing_semantic_deps_is_still_400(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Any:
        raise RuntimeError("install the semantic extra")

    monkeypatch.setattr(vector_search, "_require_semantic_deps", missing)
    resp = world.client.post(f"/api/index/{BOOK}", json={"force_reindex": False})
    assert resp.status_code == 400, resp.text
    assert "semantic extra" in resp.json()["detail"]
    assert "Retry-After" not in resp.headers


def test_w2_35b_corrupt_book_pkl_is_still_500(world: World) -> None:
    (world.book_dir / "book.pkl").write_bytes(b"\x80\x04not-a-pickle")
    _clear_caches()
    resp = world.client.post(f"/api/index/{BOOK}", json={"force_reindex": False})
    assert resp.status_code == 500, resp.text
    assert "Retry-After" not in resp.headers


def test_w2_56b_http_aba_recheck_for_the_index_route(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    pkl = (world.book_dir / "book.pkl").read_bytes()

    def swap() -> None:
        shutil.rmtree(world.book_dir)
        world.book_dir.mkdir()
        _write_meta(world.book_dir, U2)
        (world.book_dir / "book.pkl").write_bytes(pkl)

    with _interpose_acquire(monkeypatch, swap) as fired:
        resp = world.client.post(f"/api/index/{BOOK}", json={"force_reindex": False})
    assert fired == [1], "the index route never took the book lock"
    _assert_changed(resp)
    assert not (world.book_dir / "chroma_db").exists()
    assert _meta_uuid(world.book_dir) == U2


# --------------------------------------------------------------------------- notes routes


@pytest.mark.parametrize("route", ROUTES)
def test_w2_36_every_notes_route_with_an_ex_holder_is_409(world: World, tmp_path: Path, route: str) -> None:
    note_id = _seed_note(world)
    b0 = world.notes_bytes()
    with Holder(str(world.books_dir), BOOK, "exclusive", "delete", str(tmp_path)):
        resp = _call(world.client, route, note_id)
    _assert_busy(resp, "delete")
    assert world.notes_bytes() == b0


@pytest.mark.parametrize("route", ROUTES)
def test_w2_37_aba_over_http_is_409_and_the_new_notes_are_untouched(
    world: World, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    note_id = _seed_note(world)
    b_new = json.dumps(
        {"schema_version": 1, "book_id": BOOK, "annotations": []}, ensure_ascii=False
    ).encode("utf-8")
    pkl = (world.book_dir / "book.pkl").read_bytes()

    def swap() -> None:
        shutil.rmtree(world.book_dir)
        world.book_dir.mkdir()
        _write_meta(world.book_dir, U2)
        (world.book_dir / "book.pkl").write_bytes(pkl)
        world.notes_path.write_bytes(b_new)

    with _interpose_acquire(monkeypatch, swap) as fired:
        resp = _call(world.client, route, note_id)
    assert fired == [1], f"{route} never took the book lock"
    _assert_changed(resp)
    assert world.notes_bytes() == b_new


def test_w2_38_book_deleted_after_validation_is_404_and_not_resurrected(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(world.book_dir)) as fired:
        resp = world.client.post(f"/api/notes/{BOOK}/0", json=_create_body())
    assert fired == [1]
    assert resp.status_code == 404, resp.text
    assert not world.book_dir.exists()
    assert set(os.listdir(world.books_dir)) <= {".locks"}


@pytest.mark.parametrize("route", ROUTES + ["index"])
def test_w2_39_lock_waits_never_block_the_event_loop(world: World, tmp_path: Path, route: str) -> None:
    note_id = _seed_note(world)

    async def scenario() -> Dict[str, Any]:
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            done: Dict[str, float] = {}
            t0 = time.monotonic()

            async def route_request() -> httpx.Response:
                resp = await _call(client, route, note_id)
                done["route"] = time.monotonic()
                return resp

            async def health() -> httpx.Response:
                await asyncio.sleep(0.05)
                start = time.monotonic()
                resp = await client.get("/api/health")
                done["health"] = time.monotonic()
                done["health_latency"] = done["health"] - start
                return resp

            route_resp, health_resp = await asyncio.gather(route_request(), health())
            return {"route": route_resp, "health": health_resp, "done": done, "t0": t0}

    with Holder(str(world.books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        got = asyncio.run(scenario())
    done = got["done"]
    assert got["health"].status_code == 200
    assert done["health_latency"] < 0.5
    assert done["route"] - done["health"] >= 1.0
    assert got["route"].status_code == 409, got["route"].text


def test_w2_40_no_leaked_hold_across_requests_on_a_one_token_pool(world: World, tmp_path: Path) -> None:
    import anyio.to_thread

    with TestClient(server.app, base_url="http://127.0.0.1") as client:
        def set_tokens(n: int) -> int:
            limiter = anyio.to_thread.current_default_thread_limiter()
            old = int(limiter.total_tokens)
            limiter.total_tokens = n
            return old

        old = client.portal.call(set_tokens, 1)  # type: ignore[union-attr]
        try:
            statuses = [
                client.post(f"/api/notes/{BOOK}/0", json=_create_body()).status_code for _ in range(20)
            ]
        finally:
            client.portal.call(set_tokens, old)  # type: ignore[union-attr]
    assert statuses == [201] * 20
    assert len(world.quotes()) == 20

    path = str(tmp_path / "after.json")
    child = Child(try_exclusive, (str(world.books_dir), BOOK, "delete", path), path).start()
    got = child.wait_result(CHILD_WAIT_S)
    assert child.reap(CHILD_TIMEOUT_S) == 0
    assert outcome(got) == "acquired", got


# --------------------------------------------------------------------------- W2-46


def test_w2_46_locks_dir_never_appears_as_a_book(world: World) -> None:
    books = world.books_dir
    shutil.rmtree(books / BOOK)
    for name in ("a_data", "b_data"):
        (books / name).mkdir()
        _write_pkl(books / name, title=name)
    (books / ".locks").mkdir()
    (books / ".locks" / "a_data.lock").write_text("")
    (books / ".locks" / "ghost_data.lock").write_text("")
    _clear_caches()

    assert set(search_service.list_book_ids(str(books))) == {"a_data", "b_data"}
    stats = world.client.get("/api/library/stats", params={"fresh": "true"})
    assert stats.status_code == 200, stats.text
    assert stats.json()["books_total"] == 2
    for bad in (".locks", "ghost_data"):
        with pytest.raises(server.HTTPException) as info:
            server._validate_book_id(bad)
        assert info.value.status_code == 404, bad

    resolver = BookUuidResolver(str(books))
    resolver.scan()
    assert set(resolver._folder_to_uuid) == {"a_data", "b_data"}
