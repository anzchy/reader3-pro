"""018 WI-2 audit fix-up, WI-1 — per-resource locks under the SH book lock (#3, #4, #43).

Cases FX-1-01..FX-1-08 and FX-1-10..FX-1-13 of
``.claude/tdd-guardian/tests-20261001-003726.md``. FX-1-09 (the HTTP 409) lives in
``test_book_lock_routes.py``; FX-1-14..FX-1-16 live in ``test_book_uuid_race.py``.

Law (``book_lock.resource_lock``): for any (resource, folder) at most one holder
exists at a time, across threads and processes. A refused request is refused no
later than the enclosing book lock's deadline and leaves neither its per-path thread
lock nor its flock held. A request made without a book lock creates nothing.

Where the lock files go (ADR-0015 item 2): ``books/.locks/{resource}/{folder}.lock``
for reindex / conversations / ai_meta; notes keeps its historical in-dir
``notes.json.lock``.

Substitutions:
  * the embedding function (``HashEmbedder``), because the real model is a download;
  * ``conversations.json`` replaced by a module-local forwarding shim, as a
    scheduling seam (park inside the write) or to simulate an I/O failure mid-write.
Everything else is real: flock, the filesystem, chromadb, threads.

Failure texts never quote an ENOENT message (``_describe`` renders the errno
symbolically): the red-receipt tool reads that phrase as a broken runner.
"""

from __future__ import annotations

import errno
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from book_lock_workers import HashEmbedder, probe
from notes_concurrency import _install_observable_lock
from reader3_app import book_lock, notes_service, reader3, vector_search
from reader3_app.ai import books as ai_books
from reader3_app.ai import conversations
from reader3_app.ai.conversations import ConversationMessage, ConversationThread
from reader3_app.models.annotations import Annotation

BOOK = "x_data"
OTHER = "y_data"
SH = book_lock.SHARED
#: The WI-5 ``short_budget`` value; defined locally until WI-5 lands its fixture.
SHORT_BUDGET_S = 0.3
JOIN_TIMEOUT_S = 30.0
#: A parked holder gives up after this long, so a lock that fails to refuse turns
#: into a red on the assertions instead of a hung test.
PARK_GUARD_S = 5.0
NEW_RESOURCES = ("reindex", "conversations", "ai_meta")
U = "11111111-1111-4111-8111-111111111111"
# Conversation ids must be UUIDs (``_safe_conversation_id``); these stand for the
# matrix's "c1" / "c2".
C1 = "c1c1c1c1-0000-4000-8000-000000000001"
C2 = "c2c2c2c2-0000-4000-8000-000000000002"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def short_budget(monkeypatch: pytest.MonkeyPatch) -> float:
    monkeypatch.setattr(book_lock, "BUDGET_S", SHORT_BUDGET_S)
    return SHORT_BUDGET_S


@pytest.fixture
def hash_embedder(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Same seam as ``test_book_writers_no_resurrection.hash_embedder``; chromadb stays real."""
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    box: Dict[str, Any] = {"on_first_call": None}
    monkeypatch.setattr(
        vector_search,
        "_build_embedding_function",
        lambda factory: HashEmbedder(on_first_call=box["on_first_call"]),
    )
    return box


@pytest.fixture
def real_book(books_dir: Path, epub_v1: Path) -> Path:
    reader3.process_epub(str(epub_v1), str(books_dir / BOOK))
    assert (books_dir / BOOK / "book.pkl").exists()
    return books_dir / BOOK


# --------------------------------------------------------------------------- helpers


def _describe(exc: Optional[BaseException]) -> str:
    if exc is None:
        return "None"
    if isinstance(exc, OSError):
        code = errno.errorcode.get(exc.errno or 0, exc.errno)
        paths = " -> ".join(str(p) for p in (exc.filename, exc.filename2) if p)
        return f"{type(exc).__name__}[{code}] {paths}".strip()
    return f"{type(exc).__name__}: {exc}"


def _start(fn: Callable[[], Any], after: Optional[Callable[[], None]] = None) -> Tuple[threading.Thread, Dict[str, Any]]:
    """Start ``fn`` on a daemon thread; the box gets value/error and in-thread elapsed."""
    box: Dict[str, Any] = {}

    def body() -> None:
        t0 = time.monotonic()
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
            box["error"] = exc
        finally:
            box["elapsed"] = time.monotonic() - t0
            if after is not None:
                after()

    t = threading.Thread(target=body, daemon=True)
    t.start()
    return t, box


def _run_in_thread(fn: Callable[[], Any], timeout: float = JOIN_TIMEOUT_S) -> Dict[str, Any]:
    t, box = _start(fn)
    t.join(timeout)
    box["alive"] = t.is_alive()
    return box


def _res_lock(books: Path, resource: str, folder: str = BOOK) -> Path:
    return books / ".locks" / resource / f"{folder}.lock"


def _listing(path: Path) -> Optional[List[str]]:
    """``sorted(os.listdir(path))``, or ``None`` if the directory is not there."""
    return sorted(os.listdir(path)) if path.is_dir() else None


def _resource_cm(books: Path, folder: str, resource: str):
    if resource == "notes":
        return notes_service._book_write_lock(str(books), folder)
    return book_lock.resource_lock(str(books), folder, category=resource)


def _hold_and_return(books: Path, folder: str, resource: str) -> Callable[[], str]:
    def body() -> str:
        with book_lock.acquire(str(books), folder, mode=SH, holder=resource):
            with _resource_cm(books, folder, resource):
                return "ok"

    return body


def fresh_resource_ok(books: Path, resource: str, folder: str = BOOK) -> Tuple[Any, float]:
    """SH book lock + the resource lock in a fresh thread; ``(value, real_elapsed)``."""
    box = _run_in_thread(_hold_and_return(books, folder, resource))
    assert not box["alive"], f"a fresh {resource} holder never finished"
    return box.get("value", _describe(box.get("error"))), box["elapsed"]


class ResourceHeld:
    """A thread holding SH on the book plus one resource lock until ``release()``."""

    def __init__(self, books: Path, folder: str, resource: str) -> None:
        self.ready = threading.Event()
        self._go = threading.Event()
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, args=(books, folder, resource), daemon=True)

    def _run(self, books: Path, folder: str, resource: str) -> None:
        try:
            with book_lock.acquire(str(books), folder, mode=SH, holder=resource):
                with _resource_cm(books, folder, resource):
                    self.ready.set()
                    self._go.wait(PARK_GUARD_S)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            self.error = exc
            self.ready.set()

    def start(self) -> "ResourceHeld":
        self.thread.start()
        assert self.ready.wait(JOIN_TIMEOUT_S), "resource holder thread never became ready"
        assert self.error is None, f"resource holder failed to acquire: {_describe(self.error)}"
        return self

    def release(self) -> None:
        self._go.set()
        self.thread.join(JOIN_TIMEOUT_S)
        assert not self.thread.is_alive(), "resource holder deadlocked on release"


class JsonShim:
    """Module-local stand-in for ``conversations.json``: forwards everything but ``dump``.

    ``dump(index, obj, fp, ...)`` receives a 1-based call counter, so a test can park
    or fail the first caller only. Never a global patch of ``json.dump``.
    """

    def __init__(self, dump: Callable[..., Any]) -> None:
        self._dump = dump
        self._guard = threading.Lock()
        self.calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(json, name)

    def dump(self, obj: Any, fp: Any, *args: Any, **kwargs: Any) -> Any:
        with self._guard:
            self.calls += 1
            index = self.calls
        return self._dump(index, obj, fp, *args, **kwargs)


def _thread(book_uuid: str, cid: str, text: str, folder: str = BOOK) -> ConversationThread:
    return ConversationThread(
        schema_version=conversations.SCHEMA_VERSION,
        book_uuid=book_uuid,
        book_folder=folder,
        conversation_id=cid,
        provider="stub",
        messages=[
            ConversationMessage(
                id=f"m-{text}", role="user", content=text, timestamp="2026-10-01T00:00:00+00:00"
            )
        ],
    )


def _messages(thread: ConversationThread) -> List[Dict[str, Any]]:
    return thread.to_dict()["messages"]


def _write_meta(book_dir: Path, meta: Dict[str, Any]) -> None:
    (book_dir / ai_books.AI_META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")


def _conv_dir(books: Path) -> Path:
    return Path(conversations._conversations_dir(str(books), BOOK))


def _conv_path(books: Path, cid: str) -> Path:
    return Path(conversations._conversation_path(str(books), BOOK, cid))


def _tmp_files(directory: Path) -> List[str]:
    return [p for p in (_listing(directory) or []) if p.endswith(".tmp")]


# --------------------------------------------------------------------------- FX-1-01


@pytest.mark.parametrize("resource", NEW_RESOURCES)
def test_fx_1_01_resource_lock_without_book_lock_is_an_order_error_and_creates_nothing(
    books_dir: Path, resource: str
) -> None:
    (books_dir / BOOK).mkdir()
    before = sorted(os.listdir(books_dir / BOOK))

    def body() -> None:
        with book_lock.resource_lock(str(books_dir), BOOK, category=resource):
            pass

    box = _run_in_thread(body)
    assert not box["alive"]
    err = box.get("error")
    assert type(err) is book_lock.BookLockOrderError, _describe(err)
    assert not (books_dir / ".locks" / resource).exists()
    assert sorted(os.listdir(books_dir / BOOK)) == before


# --------------------------------------------------------------------------- FX-1-02


def test_fx_1_02_book_lock_inside_a_new_resource_lock_keeps_the_order_guard(
    books_dir: Path, tmp_path: Path
) -> None:
    (books_dir / BOOK).mkdir()
    (books_dir / OTHER).mkdir()

    def body() -> None:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="reindex"):
            with book_lock.resource_lock(str(books_dir), BOOK, category="ai_meta"):
                with book_lock.acquire(str(books_dir), OTHER, mode=SH, holder="notes"):
                    pass

    box = _run_in_thread(body)
    assert not box["alive"], "book lock inside a resource lock deadlocked"
    err = box.get("error")
    assert type(err) is book_lock.BookLockOrderError, _describe(err)
    assert not (books_dir / ".locks" / f"{OTHER}.lock").exists()
    assert probe(str(books_dir / ".locks" / f"{BOOK}.lock"), "EX", str(tmp_path)) == "ok"


# --------------------------------------------------------------------------- FX-1-03


def test_fx_1_03_same_resource_same_folder_second_holder_refused_nothing_leaks(
    books_dir: Path, tmp_path: Path, short_budget: float
) -> None:
    (books_dir / BOOK).mkdir()
    lock_file = _res_lock(books_dir, "reindex")

    a = ResourceHeld(books_dir, BOOK, "reindex").start()
    try:
        probe_while_held = probe(str(lock_file), "EX", str(tmp_path))
        b = _run_in_thread(_hold_and_return(books_dir, BOOK, "reindex"), timeout=2.0)
    finally:
        a.release()

    fresh_value, fresh_elapsed = fresh_resource_ok(books_dir, "reindex")
    probe_after = probe(str(lock_file), "EX", str(tmp_path))

    assert probe_while_held == "blocked", "the resource lock holds no flock while A is inside it"
    assert not b["alive"], "B waited without bound for the resource lock"
    err = b.get("error")
    assert isinstance(err, book_lock.BookLockBusy), f"B={b.get('value')!r} error={_describe(err)}"
    assert err.holder_category == "reindex"
    assert err.retry_after >= 1
    assert 0.25 <= b["elapsed"] < 1.0, b["elapsed"]
    assert fresh_value == "ok"
    assert fresh_elapsed < 0.1, f"a fresh holder waited {fresh_elapsed:.3f}s: B's refusal leaked a layer"
    assert probe_after == "ok"


# --------------------------------------------------------------------------- FX-1-04


def test_fx_1_04_different_resources_and_different_folders_do_not_block_each_other(
    books_dir: Path, short_budget: float
) -> None:
    (books_dir / BOOK).mkdir()
    (books_dir / OTHER).mkdir()

    a = ResourceHeld(books_dir, BOOK, "reindex").start()
    try:
        tb, b = _start(_hold_and_return(books_dir, BOOK, "conversations"))
        tc, c = _start(_hold_and_return(books_dir, OTHER, "reindex"))
        tb.join(JOIN_TIMEOUT_S)
        tc.join(JOIN_TIMEOUT_S)
    finally:
        a.release()

    assert b.get("value") == "ok", _describe(b.get("error"))
    assert c.get("value") == "ok", _describe(c.get("error"))
    assert b["elapsed"] < 0.1, b["elapsed"]
    assert c["elapsed"] < 0.1, c["elapsed"]
    assert _res_lock(books_dir, "reindex", BOOK).is_file()
    assert _res_lock(books_dir, "reindex", OTHER).is_file()
    assert _res_lock(books_dir, "conversations", BOOK).is_file()


# --------------------------------------------------------------------------- FX-1-05


def test_fx_1_05_resource_lock_files_live_under_locks_never_in_the_book_dir(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any]
) -> None:
    assert not (real_book / ai_books.AI_META_FILENAME).exists(), "precondition: no ai_meta.json yet"

    vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book()
    book_uuid = ai_books.ensure_book_uuid(str(books_dir), BOOK)
    conversations.save_conversation(str(books_dir), thread=_thread(book_uuid, C1, "hello"))

    for resource in ("reindex", "ai_meta", "conversations"):
        assert _listing(books_dir / ".locks" / resource) == [f"{BOOK}.lock"], resource
    in_book = sorted(str(p.relative_to(real_book)) for p in real_book.rglob("*") if p.name.endswith(".lock"))
    assert in_book == []


# --------------------------------------------------------------------------- FX-1-06


def test_fx_1_06_the_observable_registry_lock_is_still_the_one_contended(books_dir: Path) -> None:
    (books_dir / BOOK).mkdir()
    lock = _install_observable_lock(notes_service, str(books_dir), BOOK)
    a_in = threading.Event()
    release_a = threading.Event()

    def a_body() -> None:
        with notes_service._notes_write(str(books_dir), BOOK, book_lock.NO_UUID_CHECK, None):
            a_in.set()
            release_a.wait(PARK_GUARD_S)

    ann = Annotation(book_id=BOOK, chapter_index=0, quote="FX-1-06")
    ta, a = _start(a_body)
    try:
        assert a_in.wait(JOIN_TIMEOUT_S), _describe(a.get("error"))
        tb, b = _start(lambda: notes_service.add_annotation_and_version(str(books_dir), ann))
        waited = lock.someone_is_waiting.wait(2.0)
        waited_before_release = waited and not release_a.is_set()
    finally:
        release_a.set()
        ta.join(JOIN_TIMEOUT_S)
    tb.join(JOIN_TIMEOUT_S)

    assert waited_before_release, "the notes writer never waited on the registry lock"
    assert _describe(a.get("error")) == "None"
    assert _describe(b.get("error")) == "None"
    assert isinstance(b.get("value"), tuple) and isinstance(b["value"][1], str), repr(b.get("value"))
    notes = json.loads((books_dir / BOOK / notes_service.NOTES_FILENAME).read_text(encoding="utf-8"))
    assert ann.id in {x["id"] for x in notes.get("annotations") or []}
    assert (books_dir / BOOK / notes_service.NOTES_LOCK_FILENAME).exists()
    assert not (books_dir / ".locks" / "notes").exists()


# --------------------------------------------------------------------------- FX-1-08


def _collection_count(chroma_path: Path) -> int:
    import chromadb
    from chromadb.api.shared_system_client import SharedSystemClient

    SharedSystemClient.clear_system_cache()
    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_collection(vector_search.COLLECTION_NAME, embedding_function=HashEmbedder()).count()


def _park_once(parked: threading.Event, release: threading.Event) -> Callable[[], None]:
    """``on_first_call`` that parks only the first embedder that ever calls it."""
    guard = threading.Lock()
    fired: List[int] = []

    def park() -> None:
        with guard:
            if fired:
                return
            fired.append(1)
        parked.set()
        release.wait(PARK_GUARD_S)

    return park


def test_fx_1_08_concurrent_in_process_reindex_exactly_one_runs_the_other_is_refused(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], short_budget: float
) -> None:
    a_parked = threading.Event()
    release_a = threading.Event()
    hash_embedder["on_first_call"] = _park_once(a_parked, release_a)

    ta, a = _start(
        lambda: vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book(force_reindex=True)
    )
    try:
        assert a_parked.wait(JOIN_TIMEOUT_S), f"indexer A never embedded: {_describe(a.get('error'))}"
        b = _run_in_thread(
            lambda: vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book(force_reindex=True),
            timeout=10.0,
        )
        a_still_parked = not release_a.is_set() and ta.is_alive()
    finally:
        release_a.set()
        ta.join(JOIN_TIMEOUT_S)

    err = b.get("error")
    assert isinstance(err, book_lock.BookLockBusy), f"B={b.get('value')!r} error={_describe(err)}"
    assert err.holder_category == "reindex"
    assert 0.25 <= b["elapsed"] < 1.0, b["elapsed"]
    assert a_still_parked, "B returned only after A was released"
    assert _describe(a.get("error")) == "None"

    assert vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).is_indexed()
    meta = json.loads((real_book / "chroma_db" / "index_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "indexed"
    assert meta["chunk_count"] == _collection_count(real_book / "chroma_db")


# --------------------------------------------------------------------------- FX-1-10


def test_fx_1_10_two_concurrent_saves_of_one_conversation_both_succeed_no_torn_file_no_tmp(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (books_dir / BOOK).mkdir()
    _write_meta(books_dir / BOOK, {"book_uuid": U})
    thread_a = _thread(U, C1, "payload-a")
    thread_b = _thread(U, C1, "payload-b")
    a_in_dump = threading.Event()
    b_done = threading.Event()

    def dump(index: int, obj: Any, fp: Any, *args: Any, **kwargs: Any) -> None:
        json.dump(obj, fp, *args, **kwargs)
        if index == 1:
            a_in_dump.set()
            b_done.wait(0.2)

    shim = JsonShim(dump)
    monkeypatch.setattr(conversations, "json", shim)

    ta, a = _start(lambda: conversations.save_conversation(str(books_dir), thread=thread_a))
    assert a_in_dump.wait(JOIN_TIMEOUT_S), _describe(a.get("error"))
    tb, b = _start(lambda: conversations.save_conversation(str(books_dir), thread=thread_b), after=b_done.set)
    ta.join(JOIN_TIMEOUT_S)
    tb.join(JOIN_TIMEOUT_S)

    assert _describe(a.get("error")) == "None"
    assert _describe(b.get("error")) == "None"
    assert shim.calls >= 2
    got = json.loads(_conv_path(books_dir, C1).read_text(encoding="utf-8"))["messages"]
    assert got in (_messages(thread_a), _messages(thread_b)), got
    assert _tmp_files(_conv_dir(books_dir)) == []


# --------------------------------------------------------------------------- FX-1-11


def test_fx_1_11_different_conversations_of_one_book_are_serialised(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float
) -> None:
    (books_dir / BOOK).mkdir()
    _write_meta(books_dir / BOOK, {"book_uuid": U})
    thread_a = _thread(U, C1, "payload-a")
    thread_b = _thread(U, C2, "payload-b")
    a_in_dump = threading.Event()
    release_a = threading.Event()

    def dump(index: int, obj: Any, fp: Any, *args: Any, **kwargs: Any) -> None:
        if index == 1:
            a_in_dump.set()
            release_a.wait(PARK_GUARD_S)
        json.dump(obj, fp, *args, **kwargs)

    monkeypatch.setattr(conversations, "json", JsonShim(dump))

    ta, a = _start(lambda: conversations.save_conversation(str(books_dir), thread=thread_a))
    try:
        assert a_in_dump.wait(JOIN_TIMEOUT_S), _describe(a.get("error"))
        b = _run_in_thread(lambda: conversations.save_conversation(str(books_dir), thread=thread_b), timeout=10.0)
    finally:
        release_a.set()
        ta.join(JOIN_TIMEOUT_S)

    err = b.get("error")
    assert isinstance(err, book_lock.BookLockBusy), f"B={b.get('value')!r} error={_describe(err)}"
    assert err.holder_category == "conversations"
    assert 0.25 <= b["elapsed"] < 1.0, b["elapsed"]
    assert _describe(a.get("error")) == "None"
    assert json.loads(_conv_path(books_dir, C1).read_text(encoding="utf-8"))["messages"] == _messages(thread_a)
    assert not _conv_path(books_dir, C2).exists()
    assert _tmp_files(_conv_dir(books_dir)) == []


# --------------------------------------------------------------------------- FX-1-12


@pytest.mark.parametrize("writer", ["save_conversation", "save_project_conversation"])
def test_fx_1_12_a_save_failing_mid_write_leaves_the_old_file_and_no_tmp(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    (books_dir / BOOK).mkdir()
    _write_meta(books_dir / BOOK, {"book_uuid": U})
    thread = _thread(U, C1, "new")
    if writer == "save_conversation":
        target = _conv_path(books_dir, C1)

        def call() -> None:
            conversations.save_conversation(str(books_dir), thread=thread)
    else:
        root = tmp_path / "project_root"
        target = Path(conversations._project_conversation_path(str(root), U, C1))

        def call() -> None:
            conversations.save_project_conversation(str(root), thread=thread)

    target.parent.mkdir(parents=True, exist_ok=True)
    old_bytes = json.dumps({"conversation_id": C1, "messages": []}).encode("utf-8")
    target.write_bytes(old_bytes)

    def dump(index: int, obj: Any, fp: Any, *args: Any, **kwargs: Any) -> None:
        fp.write('{"partial": ')
        raise RuntimeError("disk full")

    monkeypatch.setattr(conversations, "json", JsonShim(dump))

    for attempt in (1, 2):
        with pytest.raises(RuntimeError, match="disk full"):
            call()
        assert target.read_bytes() == old_bytes, f"attempt {attempt}"
        assert _tmp_files(target.parent) == [], f"attempt {attempt}"


# --------------------------------------------------------------------------- FX-1-13


def test_fx_1_13_project_root_saves_of_one_id_concurrently_no_torn_file_no_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project_root"
    thread_a = _thread(U, C1, "payload-a")
    thread_b = _thread(U, C1, "payload-b")
    a_in_dump = threading.Event()
    b_done = threading.Event()

    def dump(index: int, obj: Any, fp: Any, *args: Any, **kwargs: Any) -> None:
        json.dump(obj, fp, *args, **kwargs)
        if index == 1:
            a_in_dump.set()
            b_done.wait(0.2)

    shim = JsonShim(dump)
    monkeypatch.setattr(conversations, "json", shim)

    ta, a = _start(lambda: conversations.save_project_conversation(str(root), thread=thread_a))
    assert a_in_dump.wait(JOIN_TIMEOUT_S), _describe(a.get("error"))
    tb, b = _start(lambda: conversations.save_project_conversation(str(root), thread=thread_b), after=b_done.set)
    ta.join(JOIN_TIMEOUT_S)
    tb.join(JOIN_TIMEOUT_S)

    assert _describe(a.get("error")) == "None"
    assert _describe(b.get("error")) == "None"
    assert shim.calls >= 2
    path = Path(conversations._project_conversation_path(str(root), U, C1))
    got = json.loads(path.read_text(encoding="utf-8"))["messages"]
    assert got in (_messages(thread_a), _messages(thread_b)), got
    assert _tmp_files(path.parent) == []


# --------------------------------------------------------------------------- FX-1-18


FX18_MARKER = "fx18-rebuilt-text"


def _collection_contents(chroma_path: Path) -> Dict[str, str]:
    """``{id: document}`` read with a fresh client, after dropping chromadb's system cache."""
    import chromadb
    from chromadb.api.shared_system_client import SharedSystemClient

    SharedSystemClient.clear_system_cache()
    client = chromadb.PersistentClient(path=str(chroma_path))
    got = client.get_collection(vector_search.COLLECTION_NAME, embedding_function=HashEmbedder()).get(
        include=["documents"]
    )
    return dict(zip(got["ids"], got["documents"] or []))


def _shrink_book_to_one_chapter(book_dir: Path) -> None:
    """Rewrite ``book.pkl`` in place: one short chapter carrying ``FX18_MARKER``."""
    import pickle

    from reader3_app.safe_pickle import load_book_file

    pkl = book_dir / "book.pkl"
    book = load_book_file(str(pkl))
    first = book.spine[0]
    first.text = f"{FX18_MARKER} " * 20
    book.spine = [first]
    with open(pkl, "wb") as f:
        pickle.dump(book, f)


def test_fx_1_18_force_reindex_after_an_in_process_index_rebuilds_from_the_current_book(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any]
) -> None:
    """FX-1-18 (added with WI-1): ``index_book()`` then ``index_book(force_reindex=True)``
    in one process. The forced run used to ``rmtree`` ``chroma_db`` under chromadb's
    per-path system cache and fail with "attempt to write a readonly database".
    """
    vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book()
    before = _collection_contents(real_book / "chroma_db")
    assert len(before) > 1, before.keys()
    assert not any(FX18_MARKER in doc for doc in before.values())

    _shrink_book_to_one_chapter(real_book)
    err: Optional[BaseException] = None
    result: Any = None
    try:
        result = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book(force_reindex=True)
    except Exception as exc:  # noqa: BLE001
        err = exc
    assert _describe(err) == "None"
    assert isinstance(result, dict) and result.get("status") == "indexed", result

    meta = json.loads((real_book / "chroma_db" / "index_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "indexed"
    after = _collection_contents(real_book / "chroma_db")
    assert meta["chunk_count"] == len(after)
    assert after, "rebuilt collection is empty"
    assert all(FX18_MARKER in doc for doc in after.values()), after
    assert all(i.startswith("c0-") for i in after), sorted(after)
    assert vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).is_indexed()
