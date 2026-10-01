"""Fix-plan WI-4 -- the vector read path (audit #44, #45, #48; ADR-0015 item 2, item 5).

Cases FX-4-01 .. FX-4-08 of ``.claude/tdd-guardian/tests-20261001-003726.md``.
FX-4-07 is the existing W2-31 / W2-32 / W2-33 in
``test_book_writers_no_resurrection.py``, which stay unedited.

Contract under test (``BookVectorIndex._client_and_collection(create=False)``):
  * an unlocked fast pre-check (``chroma_db`` absent -> not indexed, no lock);
  * then SH on the book lock as holder ``"search"`` with the short budget, an in-lock
    recheck of ``chroma_db``, the ``PersistentClient`` open and ``get_collection``;
  * the lock is released before the query runs;
  * ``BookLockBusy`` -> the existing "not indexed" ``RuntimeError``, chained;
  * only chromadb's collection-not-found maps to "not indexed"; anything else
    propagates as itself.

Empirical probe (chromadb 1.3.7): ``get_collection`` on a missing collection raises
``chromadb.errors.NotFoundError``, whose MRO is NotFoundError -> ChromaError ->
Exception. ``issubclass(chromadb.errors.NotFoundError, ValueError)`` is ``False``, so
the ``ValueError`` row of FX-4-05 is kept and the fact is pinned below.

Substitutions: the embedding function (``HashEmbedder``) everywhere; in FX-4-02 and
FX-4-05 the chromadb module in the index's deps tuple is a shim that forwards to real
chromadb and only delays (02) or fails (05) the open. Refusals are observed with
``_raised`` rather than ``pytest.raises`` so a red prints an assertion, not errno text.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import chromadb
import chromadb.errors
import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from book_lock_workers import (
    CHILD_TIMEOUT_S,
    CHILD_WAIT_S,
    Child,
    HashEmbedder,
    Holder,
    outcome,
    probe,
    try_exclusive,
)
from reader3_app import book_lock, reader3, vector_search
from reader3_app.safe_pickle import load_book_file

BOOK = "x_data"
JOIN_TIMEOUT_S = 30.0


# --------------------------------------------------------------------------- fixtures / helpers
# ``hash_embedder`` and ``real_book`` are copies of the fixtures of the same name in
# ``test_book_writers_no_resurrection.py`` (tests/conftest.py is frozen).


class _QueryHashEmbedder(HashEmbedder):
    """``HashEmbedder`` that can also embed a query.

    chromadb 1.3.7's ``collection.query`` calls ``embed_query``; the shared
    ``HashEmbedder`` does not subclass chromadb's ``EmbeddingFunction``, so it lacks the
    default (which is ``__call__``). The writer tests never query, so it is added here.
    """

    def embed_query(self, input: List[str]) -> List[List[float]]:  # noqa: A002 - chromadb's protocol name
        return self(input)


@pytest.fixture
def hash_embedder(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Replace only the embedding function; chromadb stays real."""
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    box: Dict[str, Any] = {"on_first_call": None}
    monkeypatch.setattr(
        vector_search,
        "_build_embedding_function",
        lambda factory: _QueryHashEmbedder(on_first_call=box["on_first_call"]),
    )
    return box


@pytest.fixture
def real_book(books_dir: Path, epub_v1: Path) -> Path:
    reader3.process_epub(str(epub_v1), str(books_dir / BOOK))
    assert (books_dir / BOOK / "book.pkl").exists()
    return books_dir / BOOK


def _raised(fn: Callable[[], Any]) -> Optional[BaseException]:
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001 - the exception is the observation
        return exc
    return None


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_dir():
            h.update(b"D" + rel.encode())
        else:
            h.update(b"F" + rel.encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


@contextlib.contextmanager
def _interpose_acquire(monkeypatch: pytest.MonkeyPatch, before: Callable[[], None]) -> Iterator[List[int]]:
    """Wrap ``book_lock.acquire``: run ``before`` once, then delegate. Counts calls."""
    real = book_lock.acquire
    calls: List[int] = []

    @contextlib.contextmanager
    def wrapper(*args: Any, **kwargs: Any) -> Iterator[None]:
        calls.append(1)
        if len(calls) == 1:
            before()
        with real(*args, **kwargs):
            yield

    monkeypatch.setattr(book_lock, "acquire", wrapper)
    try:
        yield calls
    finally:
        monkeypatch.setattr(book_lock, "acquire", real)


class _ChromaShim:
    """The chromadb module as seen through the deps tuple; only ``PersistentClient`` differs."""

    def __init__(self, persistent_client: Callable[..., Any]) -> None:
        self.PersistentClient = persistent_client

    def __getattr__(self, name: str) -> Any:
        return getattr(chromadb, name)


def _index(books_dir: Path) -> None:
    vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book()


def _lock_file(books_dir: Path) -> str:
    return book_lock.lock_path(str(books_dir), BOOK)


def _is_not_indexed(exc: Optional[BaseException]) -> bool:
    return type(exc) is RuntimeError and "not indexed" in str(exc)


# --------------------------------------------------------------------------- FX-4-01


def test_fx_4_01_book_deleted_between_precheck_and_lock_is_not_indexed_and_not_resurrected(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(books_dir)
    SharedSystemClient.clear_system_cache()
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(real_book)) as calls:
        exc = _raised(lambda: idx.semantic_search("q"))
    assert exc is not None, "semantic_search returned normally: the read path never rechecked under a lock"
    assert len(calls) == 1, f"the read path must take the book lock exactly once, took it {len(calls)} times"
    assert type(exc) is RuntimeError, type(exc).__name__
    assert "not indexed" in str(exc)
    assert not real_book.exists(), "the read path resurrected the deleted book dir"
    assert set(os.listdir(books_dir)) <= {".locks"}, sorted(os.listdir(books_dir))


# --------------------------------------------------------------------------- FX-4-02


def test_fx_4_02_delete_during_a_parked_open_is_refused_as_busy_search(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path
) -> None:
    _index(books_dir)
    parked = threading.Event()
    release = threading.Event()

    def parking_client(*args: Any, **kwargs: Any) -> Any:
        parked.set()
        release.wait(5)
        return chromadb.PersistentClient(*args, **kwargs)

    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    idx._deps = (_ChromaShim(parking_client), _QueryHashEmbedder())
    box: Dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = idx.semantic_search("q")
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    r = threading.Thread(target=run, daemon=True)
    r.start()
    result_path = str(tmp_path / "delete.json")
    child_result: Optional[Dict[str, Any]] = None
    code: Optional[int] = None
    try:
        assert parked.wait(JOIN_TIMEOUT_S), f"the open never went through the deps tuple: {box!r}"
        child = Child(try_exclusive, (str(books_dir), BOOK, "delete", result_path), result_path).start()
        child_result = child.wait_result(CHILD_WAIT_S)
        code = child.reap(CHILD_TIMEOUT_S)
    finally:
        release.set()
        r.join(JOIN_TIMEOUT_S)
    assert not r.is_alive()
    assert outcome(child_result) == "busy:search", child_result
    assert code == 0
    assert "error" not in box, repr(box.get("error"))
    assert isinstance(box.get("result"), list)
    assert real_book.is_dir()
    assert (real_book / "chroma_db").is_dir()
    assert probe(_lock_file(books_dir), "EX", str(tmp_path)) == "ok", "the SH search lock outlived the open"


# --------------------------------------------------------------------------- FX-4-03


def test_fx_4_03_ex_import_with_chroma_db_present_is_not_indexed_fast_and_changes_nothing(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path
) -> None:
    # No short_budget on purpose: the < 0.25 s bound must come from a real short deadline.
    assert book_lock.BUDGET_S >= 1.0
    _index(books_dir)
    chroma = real_book / "chroma_db"
    h = _tree_hash(chroma)
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        exc = _raised(lambda: idx.semantic_search("q"))
        elapsed = time.monotonic() - t0
    assert exc is not None, "semantic_search opened the store under an EX import"
    assert _is_not_indexed(exc), f"{type(exc).__name__}: {exc}"
    assert isinstance(exc.__cause__, book_lock.BookLockBusy), repr(exc.__cause__)
    assert elapsed < 0.25, f"the read path waited {elapsed:.3f}s; it must use the short budget"
    assert _tree_hash(chroma) == h


# --------------------------------------------------------------------------- FX-4-04


def test_fx_4_04_real_empty_chroma_db_without_collection_is_not_indexed(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any]
) -> None:
    chroma = real_book / "chroma_db"
    client = chromadb.PersistentClient(path=str(chroma))
    assert client.list_collections() == []
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    (chroma / "index_meta.json").write_text(
        '{"status": "indexed", "chunk_count": 1, "space": "%s", "model_name": "%s"}'
        % (vector_search.SPACE, vector_search._current_model_name()),
        encoding="utf-8",
    )
    assert idx.is_indexed() is True
    exc = _raised(lambda: idx.semantic_search("q"))
    assert _is_not_indexed(exc), f"{type(exc).__name__}: {exc}"
    assert isinstance(exc.__cause__, chromadb.errors.NotFoundError), repr(exc.__cause__)
    assert client.list_collections() == []


# --------------------------------------------------------------------------- FX-4-05


def test_fx_4_05_not_found_is_not_a_value_error_in_this_chromadb() -> None:
    """Pins the probe that keeps FX-4-05's ``ValueError`` row (chromadb 1.3.7)."""
    assert not issubclass(chromadb.errors.NotFoundError, ValueError)


@pytest.mark.parametrize(
    "injected",
    [
        PermissionError("denied"),
        ValueError("embedding function conflict"),
        chromadb.errors.InternalError("x"),
    ],
    ids=["permission", "value-conflict", "chroma-internal"],
)
def test_fx_4_05_other_get_collection_errors_propagate_and_release_the_lock(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path, injected: BaseException
) -> None:
    _index(books_dir)

    class _FailingClient:
        def get_collection(self, *args: Any, **kwargs: Any) -> Any:
            raise injected

    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    idx._deps = (_ChromaShim(lambda *a, **kw: _FailingClient()), _QueryHashEmbedder())
    exc = _raised(lambda: idx.semantic_search("q"))
    assert type(exc) is type(injected), f"{type(exc).__name__}: {exc}"
    assert str(exc) == str(injected)
    assert probe(_lock_file(books_dir), "EX", str(tmp_path)) == "ok", "the error path left SH held"


# --------------------------------------------------------------------------- FX-4-06


def test_fx_4_06_indexed_book_returns_results_and_releases_the_lock(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path
) -> None:
    _index(books_dir)
    book = load_book_file(str(real_book / "book.pkl"))
    spine_len = len(book.spine)
    first_text = (book.spine[0].text or "").split()
    token = first_text[0] if first_text else "q"
    results = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).semantic_search(token, n_results=3)
    assert len(results) >= 1
    assert all(0 <= r.chapter_order < spine_len for r in results), [r.chapter_order for r in results]
    assert probe(_lock_file(books_dir), "EX", str(tmp_path)) == "ok"
    result_path = str(tmp_path / "delete.json")
    child = Child(try_exclusive, (str(books_dir), BOOK, "delete", result_path), result_path).start()
    got = child.wait_result(CHILD_WAIT_S)
    assert child.reap(CHILD_TIMEOUT_S) == 0
    assert outcome(got) == "acquired", got


# --------------------------------------------------------------------------- FX-4-08


def test_fx_4_08_sh_lock_is_not_held_across_the_query(
    books_dir: Path,
    real_book: Path,
    hash_embedder: Dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _index(books_dir)
    SharedSystemClient.clear_system_cache()

    # Lock events, to prove the open (under the lock) completed before the query parked.
    events: List[str] = []
    real_acquire = book_lock.acquire

    @contextlib.contextmanager
    def recording(*args: Any, **kwargs: Any) -> Iterator[None]:
        with real_acquire(*args, **kwargs):
            events.append("acquired")
            yield
        events.append("released")

    monkeypatch.setattr(book_lock, "acquire", recording)

    q_parked = threading.Event()
    release = threading.Event()
    at_park: List[List[str]] = []

    def park() -> None:
        at_park.append(list(events))
        q_parked.set()
        release.wait(5)

    # Armed after indexing: the next HashEmbedder built (by the search's deps) parks on
    # its first call, which is the query embedding.
    hash_embedder["on_first_call"] = park
    box: Dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).semantic_search("q")
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    r = threading.Thread(target=run, daemon=True)
    r.start()
    result_path = str(tmp_path / "delete.json")
    child_result: Optional[Dict[str, Any]] = None
    code: Optional[int] = None
    try:
        assert q_parked.wait(JOIN_TIMEOUT_S), f"the query never embedded: {box!r}"
        child = Child(try_exclusive, (str(books_dir), BOOK, "delete", result_path), result_path).start()
        child_result = child.wait_result(CHILD_WAIT_S)
        code = child.reap(CHILD_TIMEOUT_S)
    finally:
        release.set()
        r.join(JOIN_TIMEOUT_S)
    assert not r.is_alive()
    assert at_park == [["acquired", "released"]], (
        f"the open must take and release the search lock before the query embeds; saw {at_park!r}"
    )
    assert outcome(child_result) == "acquired", child_result
    assert code == 0
    err = box.get("error")
    assert not isinstance(err, book_lock.BookLockError), repr(err)
    assert err is None or _is_not_indexed(err), repr(err)
    if err is None:
        assert isinstance(box.get("result"), list)
