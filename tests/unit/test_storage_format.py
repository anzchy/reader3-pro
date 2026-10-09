"""012 WI-3.2: ``book_store.storage_format`` and the three-state read in the book loaders.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi3.md`` section ``## WI-3.2`` (revision 2, rulings Q1-Q6), cases
S3-01 … S3-15, S3-05b, S3-14b, S3-25. The web half (S3-14b-W, S3-18 … S3-23) lives in
``tests/contract/test_storage_format_routes.py``; S3-24 is a rule-12 edit in ``test_book_store_server_wrapper.py``.

Laws pinned here:

* ``storage_format`` is a total, read-only, silent query whose answer depends on the manifest alone, and equals
  ``book_format.classify(<dir>, full=False)`` for every id ``safe_book_folder`` accepts.
* No fallback: corrupt raises ``book_format.BookCorrupt`` from every loader entry point, with zero unpickles and
  exactly one ERROR per call. Missing reads the flat pkl silently; valid also reads the flat pkl in WI-3.2 (Q1).
* The verdict is evaluated on every call, outside the ``lru_cache`` (never memoized on any stat).
* Unsafe ids raise ``safe_book_folder``'s ``ValueError`` before any path is touched.

Every case runs on real files under ``tmp_path`` (real ``publish`` under the real EX book lock). The only patches
are passthrough counters on the two deserializer seams, named by literal string.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import logging
import os
import pickle
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

import pytest
from book_format_helpers import (
    MANIFEST,
    MANIFEST_TMP,
    PKL,
    REPAIRABLE,
    add_orphan,
    add_stale_tmp,
    build_repairable,
    setup_scenario,
    snapshot,
    write_file,
)
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from wi2b_world import FP_A, flip_chapter_byte, gen_inputs, pkl_book, publish_gen, write_book_pkl

from reader3_app import book_format, book_lock, book_store, safe_pickle, search_service
from reader3_app.reader3 import Book, BookMetadata, ChapterContent
from reader3_app.safe_paths import safe_book_folder

G = "g_data"
TEXTS = ["t0 zero", "t1 one", "t2 two"]
BC = book_format.BookCorrupt
LOUD_LOGGERS = {"reader3_app.book_store", "reader3_app.book_format"}
BAD_IDS = ["", ".", "..", "../x", "a/b", "a\\b", "a\x00b"]


# --------------------------------------------------------------------------- fixtures and local helpers


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _empty_loader_cache() -> Iterator[None]:
    book_store.load_book_cached.cache_clear()
    yield
    book_store.load_book_cached.cache_clear()


@pytest.fixture
def books(tmp_path: Path) -> Path:
    out = tmp_path / "books"
    out.mkdir()
    return out


class Counters:
    """Passthrough counters on both deserializer seams. Nothing is stubbed: the real load still runs.

    ``paths`` are the path arguments ``book_store.load_book_file`` saw. ``n`` counts unpickles whichever seam
    they went through (``max`` of the two, since one load through ``load_book_file`` also passes ``safe_load``).
    """

    def __init__(self) -> None:
        self.paths: List[str] = []
        self.raw = 0

    @property
    def n(self) -> int:
        return max(len(self.paths), self.raw)

    def install(self, mp: pytest.MonkeyPatch) -> "Counters":
        real_file = safe_pickle.load_book_file
        real_load = safe_pickle.safe_load

        def counting_file(path: str) -> Any:
            self.paths.append(str(path))
            return real_file(path)

        def counting_load(f: Any) -> Any:
            self.raw += 1
            return real_load(f)

        mp.setattr("reader3_app.book_store.load_book_file", counting_file)
        mp.setattr("reader3_app.safe_pickle.safe_load", counting_load)
        return self


@pytest.fixture
def counters(monkeypatch: pytest.MonkeyPatch) -> Counters:
    return Counters().install(monkeypatch)


def garbage(book: Path) -> None:
    (book / MANIFEST).write_bytes(b"{ not json")


def book_bytes(title: str, texts: List[str]) -> bytes:
    """``pickle.dumps`` of a ``Book`` built the way ``write_book_pkl`` builds one, titled ``title``."""
    book = Book(
        metadata=BookMetadata(title=title, language="en"),
        spine=[
            ChapterContent(id=f"c{i}", href=f"Text/c{i}.xhtml", title=f"T{i}", content=f"<p>{t}</p>", text=t,
                           order=i)
            for i, t in enumerate(texts)
        ],
        toc=[],
        images={},
        source_file=f"{title}.epub",
        processed_at="2026-10-09T00:00:00+00:00",
    )
    setattr(book, "book_fingerprint", None)
    return pickle.dumps(book)


def real_gen_pkl(books: Path, folder: str, texts: List[str], fp: str, tag: str,
                 pkl: Optional[bytes] = None) -> int:
    """``publish_gen`` with a real pickle as the generation's ``book.pkl`` (default: the flat pkl's bytes)."""
    inputs = dataclasses.replace(gen_inputs(texts, fp, tag), pkl=pkl or (books / folder / PKL).read_bytes())
    book_dir = books / folder
    book_dir.mkdir(parents=True, exist_ok=True)
    with book_lock.acquire(str(books), folder, mode=book_lock.EXCLUSIVE, holder="import"):
        return book_format.publish(book_dir, inputs)


def _edit_manifest(book: Path, **fields: Any) -> None:
    doc = json.loads((book / MANIFEST).read_bytes())
    doc.update(fields)
    (book / MANIFEST).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def loud(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.levelno >= logging.WARNING and r.name in LOUD_LOGGERS]


def entry_points() -> list[tuple[str, Callable[[str, str], Any]]]:
    return [
        ("book_store.load_book", lambda b, d: book_store.load_book(b, d)),
        ("book_store.load_book_cached", lambda b, d: book_store.load_book_cached(b, d)),
        ("book_store.load_book_metadata", lambda b, d: book_store.load_book_metadata(b, d)),
        ("search_service.load_book_cached", lambda b, d: search_service.load_book_cached(b, d)),
    ]


# The corrupt shapes of S3-03 / S3-09. Each builder returns the book id under ``books``.
CORRUPT_EXTRA = ["garbage", "empty-manifest", "non-utf8", "format-v2", "manifest-is-dir", "truncated-artifact"]
CORRUPT_SHAPES = sorted(REPAIRABLE) + CORRUPT_EXTRA


def build_corrupt(shape: str, tmp_path: Path, books: Path, *, flat_pkl: bool) -> str:
    if shape in REPAIRABLE:
        build_repairable(shape, tmp_path)
        if flat_pkl:
            write_book_pkl(books, "sample_data", TEXTS, None)
        return "sample_data"
    book = books / G
    if shape in ("garbage", "empty-manifest", "non-utf8", "manifest-is-dir"):
        pkl_book(books, G, TEXTS)
        if shape == "garbage":
            garbage(book)
        elif shape == "empty-manifest":
            (book / MANIFEST).write_bytes(b"")
        elif shape == "non-utf8":
            (book / MANIFEST).write_bytes(b"\xff\xfe{}")
        else:
            (book / MANIFEST).mkdir()
        return G
    publish_gen(books, G, TEXTS, FP_A, "A")
    if shape == "format-v2":
        _edit_manifest(book, format_version=2)
    elif shape == "truncated-artifact":
        p = book / "gen" / "1" / "chapters.jsonl"
        os.truncate(p, os.path.getsize(p) - 1)
    else:  # pragma: no cover - a typo in the shape list must not pass
        raise AssertionError(shape)
    if flat_pkl:
        write_book_pkl(books, G, TEXTS, None)
    return G


# --------------------------------------------------------------------------- storage_format


MISSING_ROWS = ["pkl-only", "empty-dir", "absent-dir", "gen-without-manifest", "orphan-gen-only", "tmp-only",
                "pkl+gen-without-manifest"]


def build_missing(row: str, books: Path) -> str:
    book = books / G
    if row == "pkl-only":
        pkl_book(books, G, TEXTS)
    elif row == "empty-dir":
        book.mkdir()
    elif row == "absent-dir":
        return "nope_data"
    elif row == "gen-without-manifest":
        publish_gen(books, G, TEXTS, FP_A, "A")
        (book / MANIFEST).unlink()
    elif row == "orphan-gen-only":
        book.mkdir()
        add_orphan(book, 9)
    elif row == "tmp-only":
        book.mkdir()
        add_stale_tmp(book)
    elif row == "pkl+gen-without-manifest":
        pkl_book(books, G, TEXTS)
        add_orphan(book, 1)
    else:  # pragma: no cover
        raise AssertionError(row)
    return G


@pytest.mark.parametrize("row", MISSING_ROWS)
def test_s3_01_missing_for_every_shape_without_manifest(books: Path, row: str) -> None:
    book_id = build_missing(row, books)
    assert book_store.storage_format(book_id, str(books)) == "missing"


@pytest.mark.parametrize("row", ["one-gen", "S4-scenario", "dual"])
def test_s3_02_valid_after_publish(tmp_path: Path, books: Path, row: str) -> None:
    if row == "one-gen":
        publish_gen(books, G, TEXTS, FP_A, "A")
        book_id = G
    elif row == "S4-scenario":
        setup_scenario("S4", tmp_path)
        book_id = "sample_data"
    else:
        pkl_book(books, G, TEXTS)
        publish_gen(books, G, TEXTS, FP_A, "A")
        book_id = G
    assert book_store.storage_format(book_id, str(books)) == "valid"


@pytest.mark.parametrize("shape", CORRUPT_SHAPES)
def test_s3_03_corrupt_for_every_named_shape(tmp_path: Path, books: Path, shape: str) -> None:
    book_id = build_corrupt(shape, tmp_path, books, flat_pkl=False)
    assert book_store.storage_format(book_id, str(books)) == "corrupt"


def test_s3_04_same_size_content_flip_is_still_valid_pinned(books: Path) -> None:
    publish_gen(books, G, TEXTS, FP_A, "A")
    flip_chapter_byte(books / G, 1)
    assert book_store.storage_format(G, str(books)) == "valid"
    # Guard: the fixture really corrupted content -- only full=False misses it.
    assert book_format.classify(books / G, full=True) == "corrupt"


def _plant_outside(tmp_path: Path) -> None:
    (tmp_path / MANIFEST).write_bytes(b"{ not json")
    (tmp_path / PKL).write_bytes(book_bytes("OUTSIDE", ["outside text"]))


def _ref_message(bad: str) -> str:
    with pytest.raises(ValueError) as ref:
        safe_book_folder(bad)
    return str(ref.value)


@pytest.mark.parametrize("bad", BAD_IDS, ids=repr)
def test_s3_05_unsafe_ids_raise_safe_book_folder_error_before_touching_disk(
    tmp_path: Path, books: Path, bad: str
) -> None:
    _plant_outside(tmp_path)
    ref = _ref_message(bad)
    before = snapshot(tmp_path)

    with pytest.raises(ValueError) as ei:
        book_store.storage_format(bad, str(books))

    assert str(ei.value) == ref
    assert not isinstance(ei.value, book_format.BookFormatError)
    assert snapshot(tmp_path) == before


EXTRAS = [PKL, "book.epub", "images/a.png", "notes.json", "ai_meta.json", "chroma_db/x.bin", "README.txt",
          MANIFEST_TMP, "gen/9/chapters.jsonl", "gen/tmp/scratch.bin"]


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(base=st.sampled_from(["missing", "valid", "corrupt"]), extras=st.sets(st.sampled_from(EXTRAS)))
@example(base="missing", extras={"gen/9/chapters.jsonl"})
@example(base="valid", extras={MANIFEST_TMP, PKL})
@example(base="corrupt", extras={PKL})
def test_s3_06_property_extraneous_root_entries_never_change_the_state(base: str, extras: set) -> None:
    with tempfile.TemporaryDirectory() as td:
        books = Path(td)
        book = books / G
        if base == "missing":
            book.mkdir()
        elif base == "valid":
            publish_gen(books, G, TEXTS, FP_A, "A")
        else:
            book.mkdir()
            garbage(book)
        for rel in sorted(extras):
            data = book_bytes(G, TEXTS) if rel == PKL else b"extra " + rel.encode()
            write_file(book / rel, data)

        assert book_store.storage_format(G, str(books)) == base == book_format.classify(book, full=False)


S3_07_ROWS = ["pkl+gen-without-manifest", "S4-scenario", "R-gen-missing", "garbage", "manifest-is-dir"]


@pytest.mark.parametrize("row", S3_07_ROWS)
def test_s3_07_read_only_and_silent(tmp_path: Path, books: Path, caplog: pytest.LogCaptureFixture,
                                    row: str) -> None:
    caplog.set_level(logging.DEBUG)
    if row == "pkl+gen-without-manifest":
        book_id = build_missing(row, books)
    elif row == "S4-scenario":
        setup_scenario("S4", tmp_path)
        book_id = "sample_data"
    else:
        book_id = build_corrupt(row, tmp_path, books, flat_pkl=False)
    before = snapshot(books.parent)
    caplog.clear()

    states = [book_store.storage_format(book_id, str(books)) for _ in range(3)]

    assert len(set(states)) == 1, states
    assert snapshot(books.parent) == before
    assert loud(caplog) == []


def test_s3_08_book_store_does_not_import_the_web_layer() -> None:
    tree = ast.parse(Path(book_store.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names += [("." * node.level) + mod] + [("." * node.level) + mod + "." + a.name for a in node.names]
    bad = [n for n in names
           if n.startswith("reader3_app.web") or n.lstrip(".").startswith("web") or n == ".web"]
    assert bad == [], bad


# --------------------------------------------------------------------------- the loaders


@pytest.mark.parametrize("shape", CORRUPT_SHAPES)
def test_s3_09_no_fallback_every_corrupt_shape_every_entry_point(
    tmp_path: Path, books: Path, counters: Counters, shape: str
) -> None:
    book_id = build_corrupt(shape, tmp_path, books, flat_pkl=True)
    assert (books / book_id / PKL).is_file()
    before = snapshot(books / book_id)

    for name, call in entry_points():
        book_store.load_book_cached.cache_clear()
        with pytest.raises(BC) as ei:
            call(book_id, str(books))
        e = ei.value
        assert type(e) is BC, (name, type(e))
        assert isinstance(e, book_format.BookFormatError)
        assert not isinstance(e, (FileNotFoundError, pickle.UnpicklingError))

    assert counters.n == 0
    assert snapshot(books / book_id) == before
    assert book_store.load_book_cached.cache_info().currsize == 0


def _gen_digit_index(raw: bytes) -> int:
    i = raw.index(b'"generation"')
    j = raw.index(b":", i) + 1
    while raw[j:j + 1] in (b" ",):
        j += 1
    return j


def _s3_10_check(kind: str, pos: int, xor: int, blob: bytes) -> None:
    with tempfile.TemporaryDirectory() as td, pytest.MonkeyPatch.context() as mp:
        books = Path(td)
        book = books / G
        write_book_pkl(books, G, TEXTS, None)
        real_gen_pkl(books, G, TEXTS, FP_A, "A")
        raw = (book / MANIFEST).read_bytes()
        if kind == "truncate":
            mutated = raw[: pos % len(raw)]
        elif kind == "flip":
            i = pos % len(raw)
            mutated = raw[:i] + bytes([raw[i] ^ xor]) + raw[i + 1:]
        elif kind == "flip-generation":
            i = _gen_digit_index(raw)
            mutated = raw[:i] + bytes([raw[i] ^ xor]) + raw[i + 1:]
        else:
            mutated = blob
        (book / MANIFEST).write_bytes(mutated)
        c = Counters().install(mp)
        book_store.load_book_cached.cache_clear()
        try:
            state = book_store.storage_format(G, str(books))
            assert state != "missing"
            if state == "corrupt":
                with pytest.raises(BC):
                    book_store.load_book(G, str(books))
                assert c.n == 0
            else:
                b = book_store.load_book(G, str(books))
                assert [ch.text for ch in b.spine] == TEXTS  # type: ignore[attr-defined]
                assert c.paths == [str(book / PKL)]
        finally:
            book_store.load_book_cached.cache_clear()


@settings(max_examples=40, deadline=None)
@given(
    kind=st.sampled_from(["truncate", "flip", "replace"]),
    pos=st.integers(min_value=0, max_value=1_000_000),
    xor=st.integers(min_value=1, max_value=255),
    blob=st.binary(max_size=64),
)
@example(kind="truncate", pos=0, xor=1, blob=b"")
@example(kind="flip-generation", pos=0, xor=1, blob=b"")
def test_s3_10_property_loader_agrees_with_storage_format(kind: str, pos: int, xor: int, blob: bytes) -> None:
    _s3_10_check(kind, pos, xor, blob)


def test_s3_11_corrupt_logs_exactly_one_error_per_call(books: Path, caplog: pytest.LogCaptureFixture) -> None:
    pkl_book(books, G, TEXTS)
    garbage(books / G)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    calls = [
        lambda: book_store.load_book(G, str(books)),
        lambda: book_store.load_book(G, str(books)),
        lambda: search_service.load_book_cached(G, str(books)),
    ]
    for call in calls:
        with pytest.raises(BC) as ei:
            call()
        assert G in str(ei.value)

    ours = [r for r in caplog.records if r.name in LOUD_LOGGERS]
    errors = [r for r in ours if r.levelno == logging.ERROR]
    assert len(errors) == 3, [r.getMessage() for r in ours]
    assert all(G in r.getMessage() for r in errors)
    assert [r for r in ours if r.levelno == logging.WARNING] == []
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize("row", ["pkl-only", "pkl+orphan-gen", "pkl+gen-without-manifest", "pkl+tmp",
                                 "pkl+user-data"])
def test_s3_12_missing_is_silent_and_unchanged(
    books: Path, counters: Counters, caplog: pytest.LogCaptureFixture, row: str
) -> None:
    book = books / G
    if row == "pkl+gen-without-manifest":
        publish_gen(books, G, TEXTS, FP_A, "A")
        (book / MANIFEST).unlink()
    write_book_pkl(books, G, TEXTS, None)
    if row == "pkl+orphan-gen":
        add_orphan(book, 9)
    elif row == "pkl+tmp":
        add_stale_tmp(book)
    elif row == "pkl+user-data":
        (book / "notes.json").write_bytes(b"[]")
        (book / "ai_meta.json").write_bytes(b'{"book_uuid": "u"}')
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    d = str(books)

    b1: Any = book_store.load_book(G, d)
    b2 = book_store.load_book(G, d)
    meta = book_store.load_book_metadata(G, d)

    assert b1.metadata.title == G
    assert [c.text for c in b1.spine] == TEXTS
    assert b2 is b1
    assert getattr(b1, "book_fingerprint", None) is None
    assert meta == book_store.BookMetadataView(G, G, ())
    assert loud(caplog) == []
    assert counters.n == 1


@pytest.mark.parametrize("row", ["absent-dir", "empty-dir", "orphan-gen-only", "tmp-only", "gen-without-manifest"])
def test_s3_13_missing_with_no_pkl_is_still_file_not_found(
    books: Path, counters: Counters, caplog: pytest.LogCaptureFixture, row: str
) -> None:
    book_id = build_missing(row, books)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    for name, call in entry_points():
        with pytest.raises(FileNotFoundError) as ei:
            call(book_id, str(books))
        assert not isinstance(ei.value, book_format.BookFormatError), name

    assert loud(caplog) == []
    assert counters.n == 0


def test_s3_14_state_evaluated_on_every_call_across_a_warm_cache(
    books: Path, counters: Counters, caplog: pytest.LogCaptureFixture
) -> None:
    pkl_book(books, G, TEXTS)
    book = books / G
    st0 = os.stat(book / PKL)
    d = str(books)
    caplog.set_level(logging.DEBUG)

    b1 = book_store.load_book_cached(G, d)

    garbage(book)
    st2 = os.stat(book / PKL)
    assert (st2.st_mtime_ns, st2.st_size) == (st0.st_mtime_ns, st0.st_size)
    with pytest.raises(BC):
        book_store.load_book_cached(G, d)

    (book / MANIFEST).unlink()
    b3 = book_store.load_book_cached(G, d)
    assert b3 is b1

    garbage(book)
    with pytest.raises(BC):
        book_store.load_book(G, d)

    assert counters.n == 1
    ours = [r for r in caplog.records if r.name in LOUD_LOGGERS]
    assert len([r for r in ours if r.levelno == logging.ERROR]) == 2
    assert [r for r in ours if r.levelno == logging.WARNING] == []


def _damage(book: Path, damage: str) -> None:
    if damage == "rmtree-gen":
        shutil.rmtree(book / "gen" / "1")
    elif damage == "truncate-chapters":
        p = book / "gen" / "1" / "chapters.jsonl"
        os.truncate(p, os.path.getsize(p) - 1)
    elif damage == "unlink-gen-pkl":
        os.unlink(book / "gen" / "1" / "book.pkl")
    else:  # pragma: no cover
        raise AssertionError(damage)


@pytest.mark.parametrize("damage", ["rmtree-gen", "truncate-chapters", "unlink-gen-pkl"])
def test_s3_14b_verdict_not_memoized_on_manifest_identity(
    books: Path, counters: Counters, caplog: pytest.LogCaptureFixture, damage: str
) -> None:
    write_book_pkl(books, G, TEXTS, None)
    real_gen_pkl(books, G, TEXTS, FP_A, "A")
    book = books / G
    m0 = os.stat(book / MANIFEST)
    p0 = os.stat(book / PKL)
    d = str(books)
    caplog.set_level(logging.DEBUG)

    w: Any = book_store.load_book_cached(G, d)
    assert w.metadata.title == G
    caplog.clear()

    _damage(book, damage)
    m = os.stat(book / MANIFEST)
    p = os.stat(book / PKL)
    assert (m.st_ino, m.st_mtime_ns, m.st_size) == (m0.st_ino, m0.st_mtime_ns, m0.st_size)
    assert (p.st_mtime_ns, p.st_size) == (p0.st_mtime_ns, p0.st_size)
    assert book_store.storage_format(G, d) == "corrupt"

    for call in (book_store.load_book_cached, book_store.load_book):
        with pytest.raises(BC) as ei:
            call(G, d)
        assert type(ei.value) is BC

    assert counters.n == 1
    ours = [r for r in caplog.records if r.name in LOUD_LOGGERS]
    assert len([r for r in ours if r.levelno == logging.ERROR]) == 2
    assert [r for r in ours if r.levelno == logging.WARNING] == []


def _raised(call, *args) -> tuple[str, str]:
    try:
        call(*args)
    except Exception as e:  # noqa: BLE001 — the type is the thing under test
        return type(e).__name__, str(e) if isinstance(e, ValueError) else ""
    return "nothing", ""


@pytest.mark.parametrize("bad", BAD_IDS, ids=repr)
def test_s3_05b_loaders_reject_unsafe_ids_with_safe_book_folder_error(
    tmp_path: Path, books: Path, counters: Counters, bad: str
) -> None:
    _plant_outside(tmp_path)
    ref = _ref_message(bad)
    before = snapshot(tmp_path)

    for name, call in entry_points():
        # Captured broadly and compared by type name, so a wrong exception (e.g. today's FileNotFoundError from the
        # pre-stat) reports as an assertion naming the type rather than an escaped traceback.
        raised = _raised(call, bad, str(books))
        assert raised[0] == "ValueError", (name, raised[0])
        assert raised[1] == ref, name

    assert counters.n == 0
    assert snapshot(tmp_path) == before
    assert book_store.load_book_cached.cache_info().currsize == 0


@pytest.mark.parametrize("row", ["dual-different", "gen-only"])
def test_s3_15_valid_reads_the_flat_pkl_in_wi_3_2(
    books: Path, counters: Counters, caplog: pytest.LogCaptureFixture, row: str
) -> None:
    book = books / G
    gen_pkl = book_bytes("GEN", ["gen text"])
    if row == "dual-different":
        write_book_pkl(books, G, TEXTS, None)
    real_gen_pkl(books, G, TEXTS, FP_A, "A", pkl=gen_pkl)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    d = str(books)

    assert book_store.storage_format(G, d) == "valid"
    if row == "dual-different":
        b: Any = book_store.load_book(G, d)
        assert b.metadata.title == G
        assert [c.text for c in b.spine] == TEXTS
        assert book_store.load_book_metadata(G, d).title == G
        assert counters.paths == [str(book / PKL)]
    else:
        for name, call in entry_points():
            with pytest.raises(FileNotFoundError) as ei:
                call(G, d)
            assert not isinstance(ei.value, book_format.BookFormatError), name
    assert loud(caplog) == []


# --------------------------------------------------------------------------- book_fingerprint (pin)


@pytest.mark.parametrize("row", ["corrupt", "missing", "valid"])
def test_s3_25_book_fingerprint_unchanged_none_plus_one_warning_on_corrupt(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, row: str
) -> None:
    monkeypatch.setattr("reader3_app.book_store._FINGERPRINT_WARNED", set())
    d = str(books)
    if row == "corrupt":
        pkl_book(books, G, TEXTS)
        garbage(books / G)
    elif row == "missing":
        pkl_book(books, G, TEXTS)
    else:
        write_book_pkl(books, G, TEXTS, None)
        real_gen_pkl(books, G, TEXTS, FP_A, "A")
    c = Counters().install(monkeypatch)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    if row == "corrupt":
        assert book_store.book_fingerprint(G, d) is None
        assert c.n == 0
        with pytest.raises(BC):
            book_store.load_book(G, d)
        assert book_store.book_fingerprint(G, d) is None
        assert c.n == 0
        ours = [r for r in caplog.records if r.name in LOUD_LOGGERS]
        warns = [r for r in ours if r.levelno == logging.WARNING]
        assert len(warns) == 1 and warns[0].name == "reader3_app.book_store"
        assert "fingerprint unknown" in warns[0].getMessage()
        assert len([r for r in ours if r.levelno == logging.ERROR]) == 1
    elif row == "missing":
        assert book_store.book_fingerprint(G, d) is None
        assert book_store.book_fingerprint(G, d) is None
        assert loud(caplog) == []
        assert c.n == 0
    else:
        assert book_store.book_fingerprint(G, d) == FP_A
        assert loud(caplog) == []
        assert c.n == 0
