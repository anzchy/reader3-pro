"""012 WI-2a.7: the chroma meta records the book fingerprint; a mismatch is a *soft* stale.

**Law**: ``_stale_reason(meta, cur) == "fingerprint"`` if and only if no hard reason (status, space, model_name,
empty) applies, ``meta.get("book_fingerprint")`` is not None, ``cur`` is not None, and the two differ. Otherwise the
result is the hard reason, or ``None``. Rulings: R2 (``book_store.book_fingerprint`` gives ``None`` for pkl-only or
corrupt books = cannot judge = not stale), R3 (pre-012 meta without the key = not stale), R4 soft (a fingerprint-only
stale keeps answering queries and keeps the meta's own ``status``; a hard reason still refuses and wins the reason).

Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md``, cases V7-01..V7-12 (V7-IT1 dropped by coordinator
decision 2). Manifest books are real ``book_format.publish`` into ``tmp_path`` plus a real ``book.pkl`` at the root;
pkl-only books are ``synthetic_library.make_book`` pickles. No module of this repo is mocked. V7-08/V7-09 run real
chromadb with only the embedding function replaced (the ``hash_embedder`` pattern of ``test_vector_read_path.py``).

``_stale_reason`` is reached through ``_reason()``, which first asserts the two-parameter signature, so a red against
the pre-2a.7 one-parameter function is an assertion, not a ``TypeError``.
"""

from __future__ import annotations

import inspect
import json
import logging
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from book_format_helpers import make_inputs
from book_lock_workers import HashEmbedder
from deg_assertions import NOTES_FINGERPRINT_KEY, STALE_FINGERPRINT, write_stale_index_meta
from hypothesis import given, settings
from hypothesis import strategies as st

from reader3_app import book_format, vector_search
from reader3_app.vector_search import SPACE, BookVectorIndex
from synthetic_library import make_book

BOOK = "b_data"
KEY = "book_fingerprint"
FP_X = "0123456789abcdef" * 4
FP_Y = "fedcba9876543210" * 4
ABSENT = object()
META_KEYS = {"book_id", "status", "chunk_count", "model_name", "space", "indexed_at"}


def valid_meta(**extra: Any) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "book_id": BOOK,
        "status": "indexed",
        "chunk_count": 3,
        "model_name": vector_search._current_model_name(),
        "space": SPACE,
        "indexed_at": "2026-10-08T00:00:00+00:00",
    }
    meta.update(extra)
    return meta


def _reason(meta: Dict[str, Any], cur: Optional[str]) -> Optional[str]:
    params = list(inspect.signature(BookVectorIndex._stale_reason).parameters)
    assert len(params) == 2, f"_stale_reason must take (meta, current_fingerprint), has {params}"
    return BookVectorIndex._stale_reason(meta, cur)


def write_pkl(book_dir: Path, text: Optional[str] = None) -> None:
    book = make_book(0, chapters=1 if text else 2, chapter_chars=200)
    if text is not None:
        book.spine[0].text = text
    book_dir.mkdir(parents=True, exist_ok=True)
    with open(book_dir / "book.pkl", "wb") as f:
        pickle.dump(book, f)


def manifest_book(books: Path, fingerprint: str = FP_X, text: Optional[str] = None) -> Path:
    books.mkdir(parents=True, exist_ok=True)
    book_dir = books / BOOK
    book_format.publish(book_dir, make_inputs("v0", book_fingerprint=fingerprint), create=True)
    write_pkl(book_dir, text)
    return book_dir


def pkl_only_book(books: Path) -> Path:
    write_pkl(books / BOOK)
    return books / BOOK


def corrupt_book(books: Path) -> Path:
    book_dir = manifest_book(books)
    path = book_dir / book_format.MANIFEST
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    return book_dir


def write_meta(books: Path, meta: Dict[str, Any]) -> Path:
    path = books / BOOK / "chroma_db" / "index_meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def index_of(books: Path) -> BookVectorIndex:
    return BookVectorIndex(BOOK, books_dir=str(books))


@pytest.fixture(autouse=True)
def _stable_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("READER3_EMBED_MODEL", raising=False)


# --------------------------------------------------------------------------- V7-01


TRUTH_TABLE = [
    pytest.param(valid_meta(**{KEY: FP_X}), FP_X, None, id="equal"),
    pytest.param(valid_meta(**{KEY: FP_X}), FP_Y, "fingerprint", id="differ"),
    pytest.param(valid_meta(**{KEY: STALE_FINGERPRINT}), FP_X, "fingerprint", id="deg-stale-value"),
    pytest.param(valid_meta(**{KEY: FP_X}), None, None, id="book-cannot-judge"),
    pytest.param(valid_meta(), FP_X, None, id="pre012-meta-R3"),
    pytest.param(valid_meta(), None, None, id="both-missing"),
    pytest.param(valid_meta(**{KEY: None}), FP_X, None, id="explicit-null-is-absent"),
    pytest.param(valid_meta(status="indexing", **{KEY: FP_X}), FP_Y, "status", id="status-wins"),
    pytest.param(valid_meta(space="l2", **{KEY: FP_X}), FP_Y, "space", id="space-wins"),
    pytest.param(valid_meta(model_name="other", **{KEY: FP_X}), FP_Y, "model_name", id="model-wins"),
    pytest.param(valid_meta(chunk_count=0, **{KEY: FP_X}), FP_Y, "empty", id="empty-wins"),
]


@pytest.mark.parametrize("meta, cur, expected", TRUTH_TABLE)
def test_v7_01_stale_reason_truth_table_with_precedence(meta, cur, expected):
    assert _reason(meta, cur) == expected


# --------------------------------------------------------------------------- V7-02


def reference_reason(status, space, model_name, chunk_count, meta_fp, cur) -> Optional[str]:
    current = vector_search._current_model_name()
    if status != "indexed":
        hard: Optional[str] = "status"
    elif space != SPACE:
        hard = "space"
    elif (model_name or "") != current:
        hard = "model_name"
    elif chunk_count is not None and chunk_count <= 0:
        hard = "empty"
    else:
        hard = None
    judged = meta_fp is not ABSENT and meta_fp is not None and cur is not None
    soft = "fingerprint" if judged and meta_fp != cur else None
    return hard or soft


HEX64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)


@st.composite
def generated_rows(draw):
    status = draw(st.sampled_from(["indexed", "indexing", "error"]))
    space = draw(st.sampled_from([SPACE, "l2", None]))
    model_name = draw(st.sampled_from([vector_search._current_model_name(), "other", None]))
    chunk_count = draw(st.sampled_from([None, 0, 1, 5]))
    meta_fp = draw(st.one_of(st.none(), st.just(ABSENT), HEX64, st.just(STALE_FINGERPRINT)))
    cur = draw(st.one_of(st.none(), HEX64, st.just(meta_fp if isinstance(meta_fp, str) else None)))
    meta: Dict[str, Any] = {"book_id": BOOK, "status": status, "space": space, "model_name": model_name}
    if chunk_count is not None:
        meta["chunk_count"] = chunk_count
    if meta_fp is not ABSENT:
        meta[KEY] = meta_fp
    return meta, (status, space, model_name, chunk_count, meta_fp, cur)


@settings(max_examples=300, deadline=None)
@given(row=generated_rows())
def test_v7_02_fingerprint_iff_law_over_generated_metas(row):
    meta, args = row
    assert _reason(meta, args[-1]) == reference_reason(*args)


# --------------------------------------------------------------------------- V7-03


@pytest.mark.parametrize(
    "meta, expected",
    [
        pytest.param(valid_meta(**{KEY: FP_X}), True, id="a-fresh"),
        pytest.param(valid_meta(**{KEY: FP_Y}), True, id="b-soft"),
        pytest.param(valid_meta(space="l2", **{KEY: FP_Y}), False, id="c-hard-plus-fingerprint"),
        pytest.param(valid_meta(space="l2"), False, id="d-hard-only"),
    ],
)
def test_v7_03_is_indexed_splits_hard_from_soft(tmp_path, meta, expected):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    write_meta(books, meta)
    assert index_of(books).is_indexed() is expected


# --------------------------------------------------------------------------- V7-04


def test_v7_04_soft_stale_status_keeps_the_original_status_and_adds_two_keys(tmp_path):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    meta = valid_meta(**{KEY: FP_Y})
    path = write_meta(books, meta)
    before = path.read_bytes()

    got = index_of(books).status()

    assert got == {**meta, "stale": True, "stale_reason": "fingerprint"}
    assert got["status"] == "indexed" and got["chunk_count"] == 3
    assert not {"previous_status", "indexed_chunk_count", "indexed_model_name"} & set(got)
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- V7-05


def test_v7_05_hard_plus_fingerprint_mismatch_hard_wins_on_reason_and_shape(tmp_path):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    write_meta(books, valid_meta(space="l2", **{KEY: FP_Y}))

    got = index_of(books).status()

    assert got["status"] == "not_indexed"
    assert got["stale_reason"] == "space"
    assert got["stale"] is True
    assert got["chunk_count"] == 0
    assert got["previous_status"] == "indexed"
    assert got["indexed_chunk_count"] == 3


# --------------------------------------------------------------------------- V7-06


@pytest.mark.parametrize(
    "make, meta",
    [
        pytest.param(pkl_only_book, valid_meta(**{KEY: FP_Y}), id="a-pkl-only"),
        pytest.param(manifest_book, valid_meta(), id="b-pre012-meta-R3"),
        pytest.param(corrupt_book, valid_meta(**{KEY: FP_Y}), id="c-corrupt-manifest"),
    ],
)
def test_v7_06_cannot_judge_rows_pass_status_through_untouched(tmp_path, caplog, make, meta):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    make(books)
    write_meta(books, meta)
    idx = index_of(books)

    assert idx.status() == meta
    assert idx.status() == meta
    assert idx.is_indexed() is True

    store_warnings = [r for r in caplog.records if r.name == "reader3_app.book_store" and r.levelno == logging.WARNING]
    if make is corrupt_book:
        assert len(store_warnings) == 1, [r.getMessage() for r in store_warnings]
    else:
        assert store_warnings == []


# --------------------------------------------------------------------------- V7-07


def test_v7_07_deg_fixture_stale_index_meta_is_a_soft_stale_on_a_manifest_book(tmp_path):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    assert NOTES_FINGERPRINT_KEY == KEY
    write_stale_index_meta(books, BOOK)
    idx = index_of(books)

    got = idx.status()

    assert got.get("stale") is True
    assert got.get("stale_reason") == "fingerprint"
    assert got["status"] == "indexed"
    assert idx.is_indexed() is True


# --------------------------------------------------------------------------- V7-08 / V7-09 (real chromadb)


class _QueryHashEmbedder(HashEmbedder):
    """``HashEmbedder`` plus ``embed_query`` (chromadb 1.3.7's ``collection.query`` calls it)."""

    def embed_query(self, input: List[str]) -> List[List[float]]:  # noqa: A002 - chromadb's protocol name
        return self(input)


@pytest.fixture
def hash_embedder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Replace only the embedding function; chromadb, book_lock and book_store stay real."""
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.setattr(vector_search, "_build_embedding_function", lambda factory: _QueryHashEmbedder())
    yield
    vector_search.retire_chroma_system(str(tmp_path / "books" / BOOK / "chroma_db"))


def _meta_on_disk(books: Path) -> Dict[str, Any]:
    return json.loads((books / BOOK / "chroma_db" / "index_meta.json").read_text(encoding="utf-8"))


def test_v7_08a_index_book_writes_the_books_fingerprint_into_meta(tmp_path, hash_embedder):
    books = tmp_path / "books"
    manifest_book(books, FP_X)

    returned = index_of(books).index_book()

    on_disk = _meta_on_disk(books)
    assert on_disk.get(KEY) == FP_X
    assert returned == on_disk
    assert set(on_disk) - {KEY} == META_KEYS


def test_v7_08b_pkl_only_index_omits_the_key_and_is_not_stale(tmp_path, hash_embedder):
    books = tmp_path / "books"
    pkl_only_book(books)
    idx = index_of(books)

    returned = idx.index_book()

    on_disk = _meta_on_disk(books)
    assert KEY not in on_disk, "pkl-only meta must omit the key, not write null"
    assert set(on_disk) == META_KEYS
    assert returned == on_disk
    assert idx.status() == on_disk
    assert idx.is_indexed() is True


def test_v7_09_republish_after_indexing_soft_stale_query_still_answers(tmp_path, hash_embedder):
    books = tmp_path / "books"
    book_dir = manifest_book(books, FP_X, text="the lantern swung in the dark corridor")
    idx = index_of(books)
    idx.index_book()
    book_format.publish(book_dir, make_inputs("v1", book_fingerprint=FP_Y), create=False)
    meta_before = (book_dir / "chroma_db" / "index_meta.json").read_bytes()

    got = idx.status()
    assert got.get("stale_reason") == "fingerprint"
    assert got["status"] == "indexed"

    results = idx.semantic_search("lantern", n_results=3)

    assert len(results) >= 1
    assert all(isinstance(r, vector_search.SemanticSearchResult) for r in results)
    assert results[0].book_id == BOOK
    assert "lantern" in results[0].text
    assert (book_dir / "chroma_db" / "index_meta.json").read_bytes() == meta_before


# --------------------------------------------------------------------------- V7-10 / V7-11


@pytest.fixture
def deps_spy(monkeypatch: pytest.MonkeyPatch) -> List[int]:
    calls: List[int] = []
    real = vector_search._require_semantic_deps

    def counting():
        calls.append(1)
        return real()

    monkeypatch.setattr(vector_search, "_require_semantic_deps", counting)
    return calls


def test_v7_10_hard_stale_still_refuses_the_query(tmp_path, deps_spy):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    write_meta(books, valid_meta(model_name="other", **{KEY: FP_X}))

    with pytest.raises(RuntimeError, match="not indexed"):
        index_of(books).semantic_search("lantern")
    assert deps_spy == []


def test_v7_11_hard_plus_fingerprint_mismatch_refuses_and_reports_hard(tmp_path, deps_spy):
    books = tmp_path / "books"
    manifest_book(books, FP_X)
    write_meta(books, valid_meta(space="l2", **{KEY: FP_Y}))
    idx = index_of(books)

    with pytest.raises(RuntimeError, match="not indexed"):
        idx.semantic_search("x")
    got = idx.status()
    assert got["stale_reason"] == "space"
    assert got["status"] == "not_indexed"
    assert deps_spy == []


# --------------------------------------------------------------------------- V7-12


@st.composite
def disk_rows(draw):
    meta, _ = draw(generated_rows())
    if KEY in meta and draw(st.booleans()):
        meta[KEY] = FP_X
    return meta, draw(st.booleans())


@settings(max_examples=40, deadline=None)
@given(row=disk_rows())
def test_v7_12_status_and_is_indexed_agree_on_every_row(row):
    meta, with_manifest = row
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        if with_manifest:
            manifest_book(books, FP_X)
        else:
            pkl_only_book(books)
        write_meta(books, meta)
        idx = index_of(books)
        got = idx.status()
        indexed = idx.is_indexed()

    reason = got.get("stale_reason")
    assert indexed == (got["status"] == "indexed" and reason in (None, "fingerprint"))
    if reason == "fingerprint":
        assert got["status"] == meta["status"]
        assert with_manifest and meta.get(KEY) not in (None, FP_X)
    expected_soft = (
        with_manifest and meta.get(KEY) is not None and meta[KEY] != FP_X and _reason(meta, None) is None
    )
    assert (reason == "fingerprint") == expected_soft
