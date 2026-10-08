"""`book_store.book_fingerprint(book_id, books_dir)` — read, never recompute (012 WI-2a.5, ruling R2).

**Law**: the result is exactly the stored ``manifest.book_fingerprint`` of the current generation, or ``None``
("cannot judge"). It never raises for a missing or corrupt book; a corrupt book logs ONE WARNING per
``(books_dir, book_id)``, not one per call; and the dedup set is not a negative cache, so a repaired manifest is
read again. Traversal ids raise ``ValueError("Invalid book folder name")`` before any path is built.

Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md``, cases B5-01..B5-11. Manifest books are real
``book_format.publish`` into ``tmp_path``; pkl-only books are ``synthetic_library.make_book`` pickles. No module of
this repo is mocked. Every test uses its own ``tmp_path``, which gives the dedup set a fresh key without a reset
hook.

`book_store` is imported in the test body through `book_store()`, as in `test_book_store.py`.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import logging
import os
import pickle
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest
from book_format_helpers import make_inputs, snapshot
from hypothesis import given, settings
from hypothesis import strategies as st

from reader3_app import book_format
from synthetic_library import make_book

FP_X = "0123456789abcdef" * 4
FP_Y = "fedcba9876543210" * 4
FP_OUT = "abcdef0123456789" * 4
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def book_store() -> Any:
    return importlib.import_module("reader3_app.book_store")


def publish_book(books_dir: Path, book_id: str, fingerprint: str = FP_X) -> Path:
    books_dir.mkdir(parents=True, exist_ok=True)
    book_dir = books_dir / book_id
    book_format.publish(book_dir, make_inputs("v0", book_fingerprint=fingerprint), create=True)
    return book_dir


def write_pkl(book_dir: Path, title: str = "T") -> None:
    book = make_book(0, chapters=2, chapter_chars=200)
    book.metadata.title = title
    book_dir.mkdir(parents=True, exist_ok=True)
    with open(book_dir / "book.pkl", "wb") as f:
        pickle.dump(book, f)


def manifest_path(book_dir: Path) -> Path:
    return book_dir / book_format.MANIFEST


def truncate_manifest(book_dir: Path) -> None:
    path = manifest_path(book_dir)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _corrupt_key_missing(book_dir: Path) -> None:
    doc = json.loads(manifest_path(book_dir).read_bytes())
    del doc["book_fingerprint"]
    manifest_path(book_dir).write_bytes(json.dumps(doc).encode())


def _corrupt_bad_hex(book_dir: Path) -> None:
    doc = json.loads(manifest_path(book_dir).read_bytes())
    doc["book_fingerprint"] = "A" * 64
    manifest_path(book_dir).write_bytes(json.dumps(doc).encode())


def _corrupt_not_json(book_dir: Path) -> None:
    manifest_path(book_dir).write_bytes(b"\xff\xfe")


def _corrupt_readback(book_dir: Path) -> None:
    doc = json.loads(manifest_path(book_dir).read_bytes())
    (book_dir / book_format.GEN_DIR / str(doc["generation"]) / book_format.CHAPTERS).unlink()


CORRUPTIONS = {
    "truncated": truncate_manifest,
    "key_missing": _corrupt_key_missing,
    "bad_hex": _corrupt_bad_hex,
    "not_json": _corrupt_not_json,
    "readback": _corrupt_readback,
}


# --------------------------------------------------------------------------- B5-01


def test_b5_01_valid_manifest_returns_exactly_the_stored_digest(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    publish_book(books, "a_data", FP_X)
    publish_book(books, "b_data", FP_Y)

    bs = book_store()
    assert bs.book_fingerprint("a_data", str(books)) == FP_X
    assert bs.book_fingerprint("b_data", str(books)) == FP_Y
    assert warnings_of(caplog) == []


# --------------------------------------------------------------------------- B5-02


def _missing_pkl_only(books: Path) -> None:
    write_pkl(books / "a_data")


def _missing_empty_dir(books: Path) -> None:
    (books / "a_data").mkdir(parents=True)


def _missing_no_dir(books: Path) -> None:
    books.mkdir(parents=True)


@pytest.mark.parametrize(
    "setup", [_missing_pkl_only, _missing_empty_dir, _missing_no_dir], ids=["pkl_only", "empty_dir", "no_dir"]
)
def test_b5_02_missing_manifest_returns_none_silently(tmp_path, caplog, setup):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    setup(books)
    before = snapshot(books)

    assert book_store().book_fingerprint("a_data", str(books)) is None
    assert warnings_of(caplog) == []
    assert snapshot(books) == before
    assert not manifest_path(books / "a_data").exists()


# --------------------------------------------------------------------------- B5-03


@pytest.mark.parametrize("corruption", sorted(CORRUPTIONS))
def test_b5_03_corrupt_manifest_returns_none_and_logs_one_warning(tmp_path, caplog, corruption):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    book_dir = publish_book(books, "a_data")
    CORRUPTIONS[corruption](book_dir)
    before = snapshot(book_dir)

    assert book_store().book_fingerprint("a_data", str(books)) is None
    records = warnings_of(caplog)
    assert len(records) == 1
    assert "a_data" in records[0].getMessage()
    assert snapshot(book_dir) == before


# --------------------------------------------------------------------------- B5-04


def test_b5_04_one_warning_per_book_not_per_call(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    truncate_manifest(publish_book(books, "a_data"))
    truncate_manifest(publish_book(books, "b_data"))

    bs = book_store()
    results = [bs.book_fingerprint(b, str(books)) for b in ("a_data", "a_data", "b_data", "a_data", "b_data")]

    assert results == [None] * 5
    records = warnings_of(caplog)
    assert len(records) == 2
    assert "a_data" in records[0].getMessage() and "b_data" not in records[0].getMessage()
    assert "b_data" in records[1].getMessage() and "a_data" not in records[1].getMessage()


# --------------------------------------------------------------------------- B5-05


def test_b5_05_dedup_key_includes_books_dir(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    lib1, lib2 = tmp_path / "lib1", tmp_path / "lib2"
    truncate_manifest(publish_book(lib1, "a_data"))
    truncate_manifest(publish_book(lib2, "a_data"))

    bs = book_store()
    assert bs.book_fingerprint("a_data", str(lib1)) is None
    assert bs.book_fingerprint("a_data", str(lib2)) is None
    assert len(warnings_of(caplog)) == 2


# --------------------------------------------------------------------------- B5-06

_MANIFEST_KEYS = sorted(f.name for f in dataclasses.fields(book_format.BookManifest))
_JSON_VALUES = (
    st.none() | st.booleans() | st.integers() | st.text(max_size=8) | st.lists(st.integers(), max_size=2)
)
_HEX64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
MUTATIONS = st.one_of(
    st.tuples(st.just("raw"), st.binary(max_size=512)),
    st.tuples(st.just("set_fp"), _HEX64),
    st.tuples(st.just("set_key"), st.sampled_from(_MANIFEST_KEYS), _JSON_VALUES),
    st.tuples(st.just("drop_key"), st.sampled_from(_MANIFEST_KEYS)),
)


def _apply(original: bytes, mutation: tuple[Any, ...]) -> bytes:
    if mutation[0] == "raw":
        return bytes(mutation[1])
    doc = json.loads(original)
    if mutation[0] == "set_fp":
        doc["book_fingerprint"] = mutation[1]
    elif mutation[0] == "set_key":
        doc[mutation[1]] = mutation[2]
    else:
        del doc[mutation[1]]
    return json.dumps(doc, ensure_ascii=False).encode()


@settings(max_examples=60, deadline=None)
@given(mutation=MUTATIONS)
def test_b5_06_none_or_the_stored_digest_under_arbitrary_manifest_bytes(mutation):
    bs = book_store()
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        book_dir = publish_book(books, "a_data")
        written = _apply(manifest_path(book_dir).read_bytes(), mutation)
        manifest_path(book_dir).write_bytes(written)

        result = bs.book_fingerprint("a_data", str(books))

    assert result is None or (isinstance(result, str) and HEX64.match(result))
    if result is not None:
        assert result == book_format.manifest_from_bytes(written).book_fingerprint
    if mutation[0] == "set_fp":
        assert result == mutation[1]


# --------------------------------------------------------------------------- B5-07


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes")
def test_b5_07_unreadable_manifest_returns_none_and_warns(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    path = manifest_path(publish_book(books, "a_data"))
    mode = path.stat().st_mode
    os.chmod(path, 0)
    try:
        result = book_store().book_fingerprint("a_data", str(books))
    finally:
        os.chmod(path, mode)

    assert result is None
    records = warnings_of(caplog)
    assert len(records) == 1
    assert "a_data" in records[0].getMessage()


# --------------------------------------------------------------------------- B5-08


@pytest.mark.parametrize("bad_id", ["../outside", "..", "", ".", "a/b", "a\x00"])
def test_b5_08_traversal_ids_raise_and_never_read_outside_books_dir(tmp_path, bad_id):
    books = tmp_path / "books"
    books.mkdir()
    publish_book(tmp_path, "outside", FP_OUT)

    try:
        result = book_store().book_fingerprint(bad_id, str(books))
    except ValueError as exc:
        assert "Invalid book folder name" in str(exc)
    else:
        raise AssertionError(f"traversal id {bad_id!r} was not rejected; returned {result!r}")


# --------------------------------------------------------------------------- B5-09


def _seed_corrupt_manifest(books: Path) -> None:
    book_dir = publish_book(books, "a_data")
    truncate_manifest(book_dir)
    write_pkl(book_dir)


def _seed_fingerprint_mismatch(books: Path) -> None:
    from deg_assertions import make_notes_stale, write_stale_index_meta  # type: ignore[import-not-found]

    book_dir = publish_book(books, "a_data", FP_X)
    write_pkl(book_dir)
    make_notes_stale(books, "a_data")
    write_stale_index_meta(books, "a_data")


@pytest.mark.parametrize(
    "seed", [_seed_corrupt_manifest, _seed_fingerprint_mismatch], ids=["corrupt_manifest", "fingerprint_mismatch"]
)
def test_b5_09_load_book_is_unaffected_by_manifest_state(tmp_path, caplog, merged_loader_cache, seed):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    seed(books)

    bs = book_store()
    assert bs.load_book("a_data", str(books)).metadata.title == "T"
    assert bs.load_book_metadata("a_data", str(books)).title == "T"
    assert warnings_of(caplog) == []


# --------------------------------------------------------------------------- B5-11


def test_b5_11_repaired_manifest_is_read_again(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    books = tmp_path / "books"
    book_dir = publish_book(books, "a_data", FP_X)
    truncate_manifest(book_dir)

    bs = book_store()
    assert bs.book_fingerprint("a_data", str(books)) is None
    assert len(warnings_of(caplog)) == 1

    book_format.publish(book_dir, make_inputs("v1", book_fingerprint=FP_Y), create=False)
    assert bs.book_fingerprint("a_data", str(books)) == FP_Y
