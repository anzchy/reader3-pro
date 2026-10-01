"""018 WI-2 — every per-book writer under the book lock: no resurrection, no ABA.

Cases W2-21..W2-33, W2-50, W2-51, W2-54, W2-56a, W2-56b(a) and W2-57 of
``.claude/tdd-guardian/tests-20260930-111748.md`` (ADR-0015 contract items 3, 5, 6).

Law:
  * no writer ever creates the book dir (only the import path does);
  * a write lands only in the book identity captured when the request started;
  * the lock wraps the whole operation (read, compare, write), not just the check.

Refusals are observed by *type name* (``_exc_name``), not by ``pytest.raises``: a
red that fails on a ``FileNotFoundError`` would otherwise print its errno text, and
the red-receipt tool reads that text as a broken runner rather than a real red.

Substitutions: the embedding function (``HashEmbedder``) only; chromadb is real.
Interposers wrap a real function, perform one real side effect, and delegate.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid as uuid_mod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from book_lock_workers import (
    CHILD_TIMEOUT_S,
    CHILD_WAIT_S,
    Child,
    HashEmbedder,
    Holder,
    _interpose_acquire,
    outcome,
    probe,
    try_exclusive,
)
from reader3_app import book_lock, notes_service, reader3, vector_search
from reader3_app.ai import books as ai_books
from reader3_app.ai.conversations import (
    CONVERSATIONS_DIRNAME,
    ConversationMessage,
    ConversationThread,
    save_conversation_multi,
)
from reader3_app.models.annotations import Annotation

EPS_S = 0.75
JOIN_TIMEOUT_S = 30.0
BOOK = "x_data"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
U3 = "33333333-3333-4333-8333-333333333333"


# --------------------------------------------------------------------------- helpers


def _exc_name(fn: Callable[[], Any]) -> str:
    """Run ``fn``; return ``"ok"`` or the raised exception's class name."""
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001 - the type is the observation
        return type(exc).__name__
    return "ok"


def _raised(fn: Callable[[], Any]) -> Optional[BaseException]:
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001
        return exc
    return None


def _ann(quote: str, folder: str = BOOK) -> Annotation:
    return Annotation(book_id=folder, chapter_index=0, quote=quote)


def _write_meta(book_dir: Path, book_uuid: Optional[str], **extra: Any) -> None:
    meta: Dict[str, Any] = dict(extra)
    if book_uuid is not None:
        meta["book_uuid"] = book_uuid
    (book_dir / ai_books.AI_META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")


def _meta_uuid(book_dir: Path) -> Optional[str]:
    path = book_dir / ai_books.AI_META_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("book_uuid")


def _notes_bytes(books: Path, folder: str = BOOK) -> Optional[bytes]:
    path = books / folder / notes_service.NOTES_FILENAME
    return path.read_bytes() if path.exists() else None


def _quotes(books: Path, folder: str = BOOK) -> List[str]:
    raw = _notes_bytes(books, folder)
    if raw is None:
        return []
    return [a["quote"] for a in json.loads(raw.decode("utf-8")).get("annotations") or []]


def _seed_notes(books: Path, quotes: List[str], folder: str = BOOK) -> bytes:
    notes_service.save_annotations(str(books), folder, [_ann(q, folder) for q in quotes])
    raw = _notes_bytes(books, folder)
    assert raw is not None
    return raw


def _stray_files(root: Path) -> List[str]:
    """Temp / lock leftovers of any writer anywhere under ``root``."""
    out = []
    for p in root.rglob("*"):
        name = p.name
        if name in (notes_service.NOTES_FILENAME, notes_service.NOTES_LOCK_FILENAME):
            out.append(str(p.relative_to(root)))
        elif name.endswith(".tmp"):
            out.append(str(p.relative_to(root)))
    return sorted(out)


def _swap(books: Path, folder: str, new_uuid: Optional[str], notes: Optional[bytes] = None,
          pkl: Optional[bytes] = None) -> None:
    """Replace the book with a different one under the same folder name."""
    book_dir = books / folder
    shutil.rmtree(book_dir)
    book_dir.mkdir()
    if new_uuid is not None:
        _write_meta(book_dir, new_uuid)
    if notes is not None:
        (book_dir / notes_service.NOTES_FILENAME).write_bytes(notes)
    if pkl is not None:
        (book_dir / "book.pkl").write_bytes(pkl)


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_dir():
            h.update(b"D" + rel.encode())
        else:
            h.update(b"F" + rel.encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


# --------------------------------------------------------------------------- notes writers


def _notes_ops(books: Path) -> Dict[str, Callable[[], Any]]:
    b = str(books)
    return {
        "add": lambda: notes_service.add_annotation_and_version(b, _ann("NEW")),
        "update": lambda: notes_service.update_annotation_and_version(b, BOOK, "nope", "t"),
        "delete": lambda: notes_service.delete_annotation_and_version(b, BOOK, "nope"),
        "refresh": lambda: notes_service.refresh_annotations_and_version(b, BOOK, lambda anns: True),
    }


@pytest.mark.parametrize("op", ["add", "update", "delete", "refresh"])
def test_w2_21_notes_writer_never_resurrects_a_removed_book(books_dir: Path, op: str) -> None:
    (books_dir / BOOK).mkdir()
    shutil.rmtree(books_dir / BOOK)

    assert _exc_name(_notes_ops(books_dir)[op]) == "BookGone"
    assert not (books_dir / BOOK).exists()
    assert set(os.listdir(books_dir)) <= {".locks"}


def test_w2_22_dir_deleted_between_validation_and_lock_is_rechecked_in_lock(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (books_dir / BOOK).mkdir()
    with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(books_dir / BOOK)) as fired:
        name = _exc_name(lambda: notes_service.add_annotation_and_version(str(books_dir), _ann("Q")))
    assert fired == [1], "the writer never took the book lock"
    assert name == "BookGone"
    assert not (books_dir / BOOK).exists()
    assert _stray_files(books_dir) == []


def test_w2_23_notes_save_succeeds_beside_a_cross_process_reindex_sh(books_dir: Path, tmp_path: Path) -> None:
    (books_dir / BOOK).mkdir()
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        t0 = time.monotonic()
        notes_service.add_annotation_and_version(str(books_dir), _ann("Q1"))
        elapsed = time.monotonic() - t0
    assert elapsed < 1.0
    assert set(_quotes(books_dir)) == {"Q1"}


def test_w2_24_notes_write_against_an_ex_holder_refused_writing_nothing(
    books_dir: Path, tmp_path: Path, short_budget: float
) -> None:
    (books_dir / BOOK).mkdir()
    b0 = _seed_notes(books_dir, ["SEED"])
    seeded_id = notes_service.load_annotations(str(books_dir), BOOK)[0].id
    ops = {
        "add": lambda: notes_service.add_annotation_and_version(str(books_dir), _ann("NEW")),
        "update": lambda: notes_service.update_annotation_and_version(str(books_dir), BOOK, seeded_id, "x"),
        "delete": lambda: notes_service.delete_annotation_and_version(str(books_dir), BOOK, seeded_id),
    }
    results: Dict[str, Any] = {}
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        for name, fn in ops.items():
            t0 = time.monotonic()
            exc = _raised(fn)
            results[name] = (
                type(exc).__name__ if exc is not None else "ok",
                getattr(exc, "holder_category", None),
                time.monotonic() - t0,
            )
    for name, (typ, cat, elapsed) in results.items():
        assert (typ, cat) == ("BookLockBusy", "import"), name
        assert elapsed < book_lock.BUDGET_S + EPS_S, name
    assert _notes_bytes(books_dir) == b0
    assert [p for p in _stray_files(books_dir) if p.endswith(".tmp")] == []


def test_w2_51_ex_refused_while_a_notes_writer_is_parked_mid_write(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (books_dir / BOOK).mkdir()
    parked = threading.Event()
    go = threading.Event()
    real_save = notes_service.save_annotations

    def parked_save(*a: Any, **kw: Any) -> None:
        parked.set()
        go.wait(JOIN_TIMEOUT_S)
        return real_save(*a, **kw)

    monkeypatch.setattr(notes_service, "save_annotations", parked_save)
    w: Dict[str, Any] = {}

    def writer() -> None:
        try:
            w["value"] = notes_service.add_annotation_and_version(str(books_dir), _ann("MID"))
        except BaseException as exc:  # noqa: BLE001
            w["error"] = type(exc).__name__

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    first_path = str(tmp_path / "first.json")
    try:
        assert parked.wait(10.0), f"writer never parked: {w!r}"
        first = Child(try_exclusive, (str(books_dir), BOOK, "delete", first_path), first_path).start()
        first_result = first.wait_result(CHILD_WAIT_S)
        first_code = first.reap(CHILD_TIMEOUT_S)
    finally:
        go.set()
        t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()
    assert "error" not in w, w
    assert outcome(first_result) == "busy:notes", first_result
    assert "MID" in _quotes(books_dir)

    second_path = str(tmp_path / "second.json")
    second = Child(try_exclusive, (str(books_dir), BOOK, "delete", second_path), second_path).start()
    second_result = second.wait_result(CHILD_WAIT_S)
    second_code = second.reap(CHILD_TIMEOUT_S)
    assert outcome(second_result) == "acquired", second_result
    assert (first_code, second_code) == (0, 0)


def test_w2_25_aba_at_the_service_layer_is_refused(books_dir: Path) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    _write_meta(book_dir, U1)
    captured = book_lock.read_book_uuid(str(books_dir), BOOK)
    assert captured == U1

    b_new = json.dumps({"schema_version": 1, "book_id": BOOK, "annotations": []}).encode()
    _swap(books_dir, BOOK, U2, notes=b_new)

    name = _exc_name(
        lambda: notes_service.add_annotation_and_version(str(books_dir), _ann("Q"), expected_book_uuid=captured)
    )
    assert name == "BookChanged"
    assert _notes_bytes(books_dir) == b_new
    assert _meta_uuid(book_dir) == U2


def test_w2_54_the_same_thread_can_write_after_each_typed_refusal(books_dir: Path, tmp_path: Path) -> None:
    b = str(books_dir)
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    _write_meta(book_dir, U1)

    # (a) ABA → BookChanged, then a write against the new identity.
    _swap(books_dir, BOOK, U2)
    assert _exc_name(
        lambda: notes_service.add_annotation_and_version(b, _ann("X"), expected_book_uuid=U1)
    ) == "BookChanged"
    notes_service.add_annotation_and_version(b, _ann("AFTER-ABA"), expected_book_uuid=U2)
    assert "AFTER-ABA" in _quotes(books_dir)

    # (b) an EX holder → BookLockBusy; once it has exited, the same thread writes.
    holder = Holder(b, BOOK, "exclusive", "import", str(tmp_path)).start()
    try:
        busy = _exc_name(
            lambda: notes_service.add_annotation_and_version(
                b, _ann("Y"), deadline=book_lock._monotonic() + 0.3
            )
        )
    finally:
        code = holder.release()
    assert busy == "BookLockBusy"
    assert code == 0
    notes_service.add_annotation_and_version(b, _ann("AFTER-BUSY"))
    assert "AFTER-BUSY" in _quotes(books_dir)

    # (c) the dir is gone → BookGone; recreate it with U3 and write again.
    shutil.rmtree(book_dir)
    assert _exc_name(lambda: notes_service.add_annotation_and_version(b, _ann("Z"))) == "BookGone"
    book_dir.mkdir()
    _write_meta(book_dir, U3)
    notes_service.add_annotation_and_version(b, _ann("AFTER-GONE"), expected_book_uuid=U3)
    assert "AFTER-GONE" in _quotes(books_dir)

    assert probe(str(books_dir / ".locks" / f"{BOOK}.lock"), "EX", str(tmp_path)) == "ok"


@pytest.mark.parametrize(
    "captured,new_uuid,expected",
    [(U1, None, "BookChanged"), (None, U2, "BookChanged"), (None, None, "ok")],
    ids=["u1-to-none", "none-to-u2", "none-none-documented-non-guarantee"],
)
def test_w2_26_aba_uuid_boundaries(
    books_dir: Path, captured: Optional[str], new_uuid: Optional[str], expected: str
) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    if captured is not None:
        _write_meta(book_dir, captured)
    assert book_lock.read_book_uuid(str(books_dir), BOOK) == captured

    b_new = json.dumps({"schema_version": 1, "book_id": BOOK, "annotations": []}).encode()
    _swap(books_dir, BOOK, new_uuid, notes=b_new)

    name = _exc_name(
        lambda: notes_service.add_annotation_and_version(str(books_dir), _ann("Q"), expected_book_uuid=captured)
    )
    assert name == expected
    if expected == "ok":
        assert _quotes(books_dir) == ["Q"]
    else:
        assert _notes_bytes(books_dir) == b_new


def test_w2_57a_the_e2e_seed_notes_call_shape_stays_lock_free(books_dir: Path, tmp_path: Path) -> None:
    (books_dir / BOOK).mkdir(parents=True, exist_ok=True)
    (books_dir / BOOK / "book.pkl").write_bytes(b"placeholder")
    records = [
        Annotation.from_dict({"book_id": BOOK, "chapter_index": 0, "type": "marker", "color": "yellow",
                              "quote": "first seeded"}),
        Annotation.from_dict({"book_id": BOOK, "chapter_index": 0, "type": "note", "color": "green",
                              "quote": "second seeded", "note_text": "n"}),
    ]
    notes_service.save_annotations(str(books_dir), BOOK, records)

    back = notes_service.load_annotations(str(books_dir), BOOK)
    assert [(a.id, a.quote) for a in back] == [(r.id, r.quote) for r in records]
    probe_result_path = str(tmp_path / "after-seed.json")
    child = Child(try_exclusive, (str(books_dir), BOOK, "delete", probe_result_path), probe_result_path).start()
    got = child.wait_result(CHILD_WAIT_S)
    assert child.reap(CHILD_TIMEOUT_S) == 0
    assert outcome(got) == "acquired", got


def test_w2_57b_direct_save_into_a_missing_dir_raises_and_creates_nothing(books_dir: Path) -> None:
    exc = _raised(lambda: notes_service.save_annotations(str(books_dir), BOOK, [_ann("Q")]))
    assert exc is not None and type(exc).__name__ == "FileNotFoundError", type(exc).__name__
    assert not (books_dir / BOOK).exists()


# --------------------------------------------------------------------------- ai_meta writers


@pytest.mark.parametrize("variant", ["removed-before", "no-meta-deleted-at-acquire", "meta-without-uuid-deleted-at-acquire"])
def test_w2_27_ai_meta_mint_never_resurrects(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    if variant == "removed-before":
        shutil.rmtree(book_dir)
        name = _exc_name(lambda: ai_books.ensure_book_uuid(str(books_dir), BOOK))
    else:
        if variant == "meta-without-uuid-deleted-at-acquire":
            _write_meta(book_dir, None, indexed_at=1)
        with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(book_dir)) as fired:
            name = _exc_name(lambda: ai_books.ensure_book_uuid(str(books_dir), BOOK))
        assert fired == [1], "the mint path never took the book lock"
    assert name == "BookGone"
    assert not book_dir.exists()
    assert [p for p in _stray_files(books_dir) if "ai_meta" in p] == []


def test_w2_28_resolver_scan_survives_a_busy_book(books_dir: Path, tmp_path: Path, short_budget: float) -> None:
    ub = "44444444-4444-4444-8444-444444444444"
    (books_dir / "a_data").mkdir()
    (books_dir / "b_data").mkdir()
    _write_meta(books_dir / "b_data", ub)
    resolver = ai_books.BookUuidResolver(str(books_dir))
    with Holder(str(books_dir), "a_data", "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        resolver.scan()
        elapsed = time.monotonic() - t0
        assert not (books_dir / "a_data" / ai_books.AI_META_FILENAME).exists()
    assert resolver.book_uuid_for_folder("b_data") == ub
    assert elapsed < book_lock.BUDGET_S + EPS_S


def _meta_uuid_of(book_dir: Path) -> Optional[str]:
    path = book_dir / ai_books.AI_META_FILENAME
    return json.loads(path.read_text(encoding="utf-8")).get("book_uuid") if path.exists() else None


def test_fx_2_12_scan_with_one_busy_book_is_bounded_and_maps_the_others(books_dir: Path, tmp_path: Path) -> None:
    """FX-2-12 (tests-20261001-003726.md): the per-book deadline bounds the scan.

    W2-28 above accepts a full budget per busy book; this pins the short one.
    """
    assert book_lock.BUDGET_S >= 1.0
    (books_dir / "a_data").mkdir()
    (books_dir / "b_data").mkdir()
    r = ai_books.BookUuidResolver(str(books_dir))
    with Holder(str(books_dir), "a_data", "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        r.scan()
        elapsed = time.monotonic() - t0
    assert elapsed < 0.5
    ub = _meta_uuid_of(books_dir / "b_data")
    assert ub is not None
    assert r.book_uuid_for_folder("b_data") == ub
    assert r.folder_for_book_uuid(ub) == "b_data"
    assert not (books_dir / "a_data" / ai_books.AI_META_FILENAME).exists()


class _ListdirShim:
    """``ai_books.os`` with ``listdir(books_dir)`` pinned to an order; all else forwards."""

    def __init__(self, books_dir: Path, order: List[str]) -> None:
        self._books = os.path.abspath(str(books_dir))
        self._order = order
        self.listdir_calls = 0

    def listdir(self, path: Any = ".") -> List[str]:
        real = os.listdir(path)
        if os.path.abspath(str(path)) != self._books:
            return real
        self.listdir_calls += 1
        return list(self._order) + [n for n in real if n not in self._order]

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


@pytest.mark.parametrize("order", [["a_data", "b_data"], ["b_data", "a_data"]])
def test_fx_2_12b_scan_deadline_is_per_book_not_scan_wide(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order: List[str]
) -> None:
    assert book_lock.BUDGET_S >= 1.0
    (books_dir / "a_data").mkdir()
    (books_dir / "b_data").mkdir()
    shim = _ListdirShim(books_dir, order)
    r = ai_books.BookUuidResolver(str(books_dir))
    with Holder(str(books_dir), "a_data", "exclusive", "import", str(tmp_path)):
        monkeypatch.setattr(ai_books, "os", shim)
        t0 = time.monotonic()
        r.scan()
        elapsed = time.monotonic() - t0
        monkeypatch.setattr(ai_books, "os", os)
    assert shim.listdir_calls >= 1, "the scan never enumerated through ai_books.os.listdir"
    assert elapsed < 0.5
    ub = _meta_uuid_of(books_dir / "b_data")
    assert ub is not None
    assert r.book_uuid_for_folder("b_data") == ub
    assert not (books_dir / "a_data" / ai_books.AI_META_FILENAME).exists()


# --------------------------------------------------------------------------- per-book conversations


def _thread(book_uuid: str, folder: str = BOOK) -> ConversationThread:
    return ConversationThread(
        schema_version=1,
        book_uuid=book_uuid,
        book_folder=folder,
        conversation_id=str(uuid_mod.UUID("55555555-5555-4555-8555-555555555555")),
        provider="ollama",
        model="llama3",
        messages=[ConversationMessage(id="m1", role="user", content="hello", timestamp="2026-09-30T00:00:00Z")],
    )


def test_w2_29a_per_book_conversation_never_resurrects_a_removed_book(books_dir: Path) -> None:
    (books_dir / BOOK).mkdir()
    shutil.rmtree(books_dir / BOOK)
    name = _exc_name(lambda: save_conversation_multi(str(books_dir), thread=_thread(U1), storage_mode="per_book"))
    assert name == "BookGone"
    assert not (books_dir / BOOK).exists()
    assert _stray_files(books_dir) == []


def test_w2_29b_per_book_conversation_dir_deleted_at_acquire(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    _write_meta(book_dir, U1)
    with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(book_dir)) as fired:
        name = _exc_name(
            lambda: save_conversation_multi(str(books_dir), thread=_thread(U1), storage_mode="per_book")
        )
    assert fired == [1], "the per-book save never took the book lock"
    assert name == "BookGone"
    assert not book_dir.exists()
    assert _stray_files(books_dir) == []


def test_w2_29c_per_book_conversation_positive_control(books_dir: Path) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    _write_meta(book_dir, U1)
    thread = _thread(U1)
    save_conversation_multi(str(books_dir), thread=thread, storage_mode="per_book")
    path = book_dir / CONVERSATIONS_DIRNAME / f"{thread.conversation_id}.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    expected = thread.to_dict()
    for key in ("book_uuid", "book_folder", "conversation_id", "provider", "model", "messages"):
        assert saved[key] == expected[key], key


def test_w2_56a_aba_recheck_for_per_book_conversations(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book_dir = books_dir / BOOK
    book_dir.mkdir()
    _write_meta(book_dir, U1)
    with _interpose_acquire(monkeypatch, lambda: _swap(books_dir, BOOK, U2)) as fired:
        name = _exc_name(
            lambda: save_conversation_multi(str(books_dir), thread=_thread(U1), storage_mode="per_book")
        )
    assert fired == [1]
    assert name == "BookChanged"
    assert not (book_dir / CONVERSATIONS_DIRNAME).exists()
    assert _meta_uuid(book_dir) == U2
    assert os.listdir(book_dir) == [ai_books.AI_META_FILENAME]


# --------------------------------------------------------------------------- vector index


@pytest.fixture
def hash_embedder(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Replace only the embedding function; chromadb stays real."""
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


def test_w2_30a_index_book_never_resurrects_a_removed_book(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any]
) -> None:
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    shutil.rmtree(real_book)
    assert _exc_name(idx.index_book) == "BookGone"
    assert not real_book.exists()


def test_w2_30b_index_book_dir_deleted_at_acquire(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with _interpose_acquire(monkeypatch, lambda: shutil.rmtree(real_book)) as fired:
        name = _exc_name(idx.index_book)
    assert fired == [1], "index_book never took the book lock"
    assert name == "BookGone"
    assert not real_book.exists()


def test_w2_50_ex_refused_while_index_book_is_mid_embedding(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path
) -> None:
    embedding_started = threading.Event()
    go = threading.Event()

    def pause() -> None:
        embedding_started.set()
        go.wait(10.0)

    hash_embedder["on_first_call"] = pause
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    r: Dict[str, Any] = {}

    def run() -> None:
        try:
            r["meta"] = idx.index_book()
        except BaseException as exc:  # noqa: BLE001
            r["error"] = type(exc).__name__

    t = threading.Thread(target=run, daemon=True)
    t.start()
    first_path = str(tmp_path / "first.json")
    try:
        assert embedding_started.wait(JOIN_TIMEOUT_S), f"indexer never embedded: {r!r}"
        first = Child(try_exclusive, (str(books_dir), BOOK, "delete", first_path), first_path).start()
        first_result = first.wait_result(CHILD_WAIT_S)
        first_code = first.reap(CHILD_TIMEOUT_S)
    finally:
        go.set()
        t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()
    assert "error" not in r, r
    assert outcome(first_result) == "busy:reindex", first_result
    assert idx.is_indexed() is True

    second_path = str(tmp_path / "second.json")
    second = Child(try_exclusive, (str(books_dir), BOOK, "delete", second_path), second_path).start()
    second_result = second.wait_result(CHILD_WAIT_S)
    second_code = second.reap(CHILD_TIMEOUT_S)
    assert outcome(second_result) == "acquired", second_result
    assert (first_code, second_code) == (0, 0)


def test_w2_56b_aba_recheck_for_index_book(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_meta(real_book, U1)
    pkl = (real_book / "book.pkl").read_bytes()
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with _interpose_acquire(monkeypatch, lambda: _swap(books_dir, BOOK, U2, pkl=pkl)) as fired:
        name = _exc_name(lambda: idx.index_book(expected_book_uuid=U1))
    assert fired == [1]
    assert name == "BookChanged"
    assert not (real_book / "chroma_db").exists()
    assert _meta_uuid(real_book) == U2


def test_w2_31_semantic_search_read_path_never_resurrects(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any]
) -> None:
    vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book()
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    real_is_indexed = idx.is_indexed

    def is_indexed_then_delete() -> bool:
        got = real_is_indexed()
        shutil.rmtree(real_book)
        return got

    idx.is_indexed = is_indexed_then_delete  # type: ignore[method-assign]
    exc = _raised(lambda: idx.semantic_search("q"))
    assert exc is not None, "semantic_search returned normally over a deleted book"
    assert type(exc).__name__ in ("RuntimeError", "BookGone"), type(exc).__name__
    if type(exc).__name__ == "RuntimeError":
        assert "not indexed" in str(exc)
    assert not real_book.exists()


def test_w2_32_import_in_progress_without_chroma_db_is_a_clean_not_indexed(
    books_dir: Path, real_book: Path, tmp_path: Path
) -> None:
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        exc = _raised(lambda: idx.semantic_search("q"))
        elapsed = time.monotonic() - t0
        status = idx.status()
    assert type(exc).__name__ == "RuntimeError" and "not indexed" in str(exc)
    assert elapsed < 0.25
    assert status["status"] == "not_indexed"
    assert not (real_book / "chroma_db").exists()


def test_w2_33_a_forced_reindex_refused_by_ex_keeps_the_old_index(
    books_dir: Path, real_book: Path, hash_embedder: Dict[str, Any], tmp_path: Path, short_budget: float
) -> None:
    vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir)).index_book()
    h0 = _tree_hash(real_book / "chroma_db")
    idx = vector_search.BookVectorIndex(BOOK, books_dir=str(books_dir))
    with Holder(str(books_dir), BOOK, "exclusive", "delete", str(tmp_path)):
        exc = _raised(lambda: idx.index_book(force_reindex=True))
    assert type(exc).__name__ == "BookLockBusy"
    assert getattr(exc, "holder_category", None) == "delete"
    assert _tree_hash(real_book / "chroma_db") == h0
