"""012 WI-2b.3: the ``_mark_orphans`` skip rule and the stale-Book GET race.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases K3-01 … K3-14 (ADR-0019 section 三, D-1, D-2).

The law: when the notes fingerprint **read inside the lock** and the request's ``Book.book_fingerprint``
disagree, GET is read-only -- ``notes.json`` bytes and mtime unchanged, no new orphan judgement, already
orphaned records stay hidden. When they agree, rematching always runs (no Q4 fast path).

Every route case runs against a real ``TestClient(server.app)`` on a tmp ``books/`` dir, real generations
(``book_format.publish`` under the real EX book lock), a real ``book.pkl`` and the real notes lock.
"""

from __future__ import annotations

import dataclasses
import json
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from wi2b_world import ABSENT, FP_A, FP_B, Q13_A, disk, gen_book, pkl_book, rec, seed_notes, version_on_disk

from reader3_app import book_store, notes_service, search_service
from reader3_app.reader3 import Book, BookMetadata
from reader3_app.web import server

KEY = notes_service.NOTES_FINGERPRINT_KEY
G = "g_data"
P = "p_data"
BASE_URL = "http://127.0.0.1"
JOIN_TIMEOUT_S = 10.0
OLD_TEXTS = ["alpha old text", "c1", "c2"]
NEW_TEXTS = ["alpha NEWQUOTE text", "c1", "c2"]


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


def _clear_caches() -> None:
    # Reached through book_store so a test that wraps "reader3_app.web.server.load_book_cached" can still clear it.
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_cached.cache_clear()


@dataclass
class World:
    client: TestClient
    books: Path

    def book(self, folder: str) -> Path:
        return self.books / folder

    def snapshot(self, folder: str) -> tuple:
        raw, mtime_ns, _ = disk(self.book(folder))
        return raw, mtime_ns

    def records(self, folder: str) -> Dict[str, Dict[str, Any]]:
        parsed = disk(self.book(folder))[2]
        assert isinstance(parsed, dict)
        return {r["id"]: r for r in parsed["annotations"]}


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    books = tmp_path / "books"
    books.mkdir()
    monkeypatch.setattr(server, "BOOKS_DIR", str(books))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)
    _clear_caches()
    try:
        yield World(client=TestClient(server.app, base_url=BASE_URL), books=books)
    finally:
        _clear_caches()


def _nx(folder: str, **kw: Any) -> Dict[str, Any]:
    """The annotation the old matcher rejects in every row: orphaned vs listed is agree vs skip."""
    return rec("nx", 0, "NOT-IN-TEXT", book_id=folder, **kw)


def _n1(folder: str, **kw: Any) -> Dict[str, Any]:
    return rec("n1", 0, "QUOTE-ONE", "alpha ", " beta", book_id=folder, **kw)


def _nb(**kw: Any) -> Dict[str, Any]:
    """``NEWQUOTE`` exists only in generation B's chapter 0 text."""
    return rec("nb", 0, "NEWQUOTE", book_id=G, **kw)


def _listed(resp: Any) -> List[str]:
    return [a["id"] for a in resp.json()["annotations"]]


def _assert_skipped(world: World, folder: str, before: tuple) -> None:
    """One GET of chapter 0 under a disagreement: 200 + ETag, ``nx`` listed, file untouched."""
    resp = world.client.get(f"/api/notes/{folder}/0")
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("ETag")
    assert "nx" in _listed(resp)
    assert world.snapshot(folder) == before
    assert world.records(folder)["nx"]["orphaned"] is False


# --------------------------------------------------------------------------- K3-07 (pure truth table)


def _oracle(n: Any, b: Optional[str]) -> bool:
    return (n is None and b is None) or (isinstance(n, str) and isinstance(b, str) and n == b)


_NOTES_SIDE = (
    st.none()
    | st.text(max_size=5)
    | st.integers()
    | st.booleans()
    | st.floats(allow_nan=False)
    | st.lists(st.integers(), max_size=2)
    | st.dictionaries(st.text(max_size=2), st.integers(), max_size=1)
)


@settings(max_examples=200, deadline=None)
@given(n=_NOTES_SIDE, b=st.none() | st.text(max_size=5))
def test_k3_07_truth_table_property(n: Any, b: Optional[str]) -> None:
    got = notes_service.fingerprints_agree(n, b)
    assert got is _oracle(n, b)


@settings(max_examples=50, deadline=None)
@given(pair=st.text().map(lambda s: (s, s)))
def test_k3_07_equal_strings_agree(pair: tuple) -> None:
    assert notes_service.fingerprints_agree(pair[0], pair[1]) is True


@pytest.mark.parametrize(
    ("n", "b", "expected"),
    [
        (None, None, True),
        (FP_A, FP_A, True),
        (FP_A, FP_B, False),
        ("STALE", None, False),
        (None, FP_A, False),
        (123, FP_A, False),
        ({}, None, False),
        ([], FP_A, False),
        (0, None, False),
        (False, None, False),
    ],
)
def test_k3_07_named_rows(n: Any, b: Optional[str], expected: bool) -> None:
    assert notes_service.fingerprints_agree(n, b) is expected


# --------------------------------------------------------------------------- K3-01 … K3-06 (D-1 rows via GET)


@pytest.mark.parametrize("fp", [ABSENT, None], ids=["absent", "null"])
def test_k3_01_legacy_row_agrees_and_orphans(world: World, fp: Any) -> None:
    pkl_book(world.books, P, Q13_A)
    seed_notes(world.book(P), [_nx(P)], fp=fp)

    resp = world.client.get(f"/api/notes/{P}/0")

    assert resp.status_code == 200, resp.text
    assert "nx" not in _listed(resp)
    assert world.records(P)["nx"]["orphaned"] is True
    assert disk(world.book(P))[2].get(KEY) is None


def test_k3_02_equal_strs_agree_and_rematch_still_runs(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G), _n1(G, bound=FP_A, evaluated=FP_A)], fp=FP_A)

    resp = world.client.get(f"/api/notes/{G}/0")

    assert resp.status_code == 200, resp.text
    assert _listed(resp) == ["n1"]
    on_disk = world.records(G)
    assert on_disk["nx"]["orphaned"] is True
    assert on_disk["n1"]["orphaned"] is False


def test_k3_03_different_strs_skip(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G)], fp=FP_B)

    _assert_skipped(world, G, world.snapshot(G))


def test_k3_04_str_notes_with_pkl_only_book_skip(world: World) -> None:
    pkl_book(world.books, P, Q13_A)
    seed_notes(world.book(P), [_nx(P)], fp="STALE")

    _assert_skipped(world, P, world.snapshot(P))


@pytest.mark.parametrize("fp", [ABSENT, None], ids=["absent", "null"])
def test_k3_05_unstamped_notes_with_str_book_skip(world: World, fp: Any) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G)], fp=fp)

    _assert_skipped(world, G, world.snapshot(G))


@pytest.mark.parametrize("value", [123, {}, []], ids=["int", "dict", "list"])
def test_k3_06_non_str_notes_value_skips_and_is_carried_through_a_save(world: World, value: Any) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G, bound=FP_A, evaluated=FP_A)], fp=value)

    _assert_skipped(world, G, world.snapshot(G))

    created = world.client.post(
        f"/api/notes/{G}/0", json={"type": "marker", "quote": "QUOTE-ONE", "prefix": "alpha ", "suffix": " beta"}
    )

    assert created.status_code == 201, created.text
    parsed = disk(world.book(G))[2]
    assert isinstance(parsed, dict)
    assert json.dumps(parsed[KEY]) == json.dumps(value)
    assert type(parsed[KEY]) is type(value)
    assert world.records(G)["nx"]["orphaned"] is False


# --------------------------------------------------------------------------- K3-08, K3-09 (state)


def test_k3_08_skip_is_idempotent_across_chapter_and_book_gets(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G)], fp=FP_B)
    before = world.snapshot(G)

    first = world.client.get(f"/api/notes/{G}/0")
    second = world.client.get(f"/api/notes/{G}/0")
    book_level = world.client.get(f"/api/notes/{G}")

    assert [r.status_code for r in (first, second, book_level)] == [200, 200, 200]
    etags = {r.headers.get("ETag") for r in (first, second, book_level)}
    assert len(etags) == 1 and None not in etags
    assert "nx" in _listed(first)
    assert "nx" in _listed(second)
    [chapter0] = [c for c in book_level.json()["annotations_by_chapter"] if c["chapter_index"] == 0]
    assert "nx" in [a["id"] for a in chapter0["annotations"]]
    assert world.snapshot(G) == before


def test_k3_08_book_level_get_alone_skips(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_nx(G)], fp=FP_B)
    before = world.snapshot(G)

    resp = world.client.get(f"/api/notes/{G}")

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("ETag")
    assert resp.json()["total_count"] == 1
    assert world.snapshot(G) == before


def test_k3_09_already_orphaned_record_stays_hidden_during_skip(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    old = rec("old", 0, "QUOTE-ONE", book_id=G, orphaned=True)
    seed_notes(world.book(G), [old, _n1(G)], fp=FP_B)
    before = world.snapshot(G)

    resp = world.client.get(f"/api/notes/{G}/0")

    assert resp.status_code == 200, resp.text
    assert _listed(resp) == ["n1"]
    assert world.records(G)["old"]["orphaned"] is True
    assert world.snapshot(G) == before


# --------------------------------------------------------------------------- K3-10 (service-level argument)


def test_k3_10_skip_argument_default_means_no_check_and_none_is_a_value(world: World) -> None:
    pkl_book(world.books, P, Q13_A)
    seed_notes(world.book(P), [_n1(P)], fp="X")
    books = str(world.books)
    loaded = [a.to_dict() for a in notes_service.load_annotations(books, P)]
    before = world.snapshot(P)
    calls: List[int] = []

    def refresh(anns: Any) -> bool:
        calls.append(1)
        return False

    notes_service.refresh_annotations_and_version(books, P, refresh)
    assert len(calls) == 1

    calls.clear()
    anns, version = notes_service.refresh_annotations_and_version(books, P, refresh, book_fingerprint=None)
    assert len(calls) == 0
    assert [a.to_dict() for a in anns] == loaded
    assert version == version_on_disk(books, P)
    assert world.snapshot(P) == before

    calls.clear()
    notes_service.refresh_annotations_and_version(books, P, refresh, book_fingerprint="X")
    assert len(calls) == 1


# --------------------------------------------------------------------------- K3-11, K3-12, K3-14 (the race)


def _stamp_as_rebind() -> bytes:
    """What WI-2b.4's rebind would leave behind: ``nb`` resolved and bound to B, notes stamped B."""
    path = seed_notes(Path(server.BOOKS_DIR) / G, [_nb(bound=FP_B, evaluated=FP_B)], fp=FP_B)
    return path.read_bytes()


def _seed_race(world: World) -> None:
    gen_book(world.books, G, OLD_TEXTS, FP_A)
    seed_notes(world.book(G), [_nb(bound=FP_A)], fp=FP_A)


def _assert_fresh_get_keeps_nb(world: World) -> None:
    _clear_caches()
    resp = world.client.get(f"/api/notes/{G}/0")
    assert resp.status_code == 200, resp.text
    assert "nb" in _listed(resp)
    assert world.records(G)["nb"]["orphaned"] is False


def test_k3_11_stale_book_loaded_before_import_cannot_orphan(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_race(world)
    real = server.load_book_cached
    hits: List[int] = []
    stamped: List[bytes] = []

    def wrapper(folder: str) -> Any:
        book = real(folder)
        gen_book(world.books, G, NEW_TEXTS, FP_B, "B")
        stamped.append(_stamp_as_rebind())
        hits.append(1)
        return book

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", wrapper)

    first = world.client.get(f"/api/notes/{G}/0")

    assert len(hits) == 1
    assert first.status_code == 200, first.text
    assert world.records(G)["nb"]["orphaned"] is False
    assert disk(world.book(G))[0] == stamped[0]

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", real)
    _assert_fresh_get_keeps_nb(world)


def test_k3_12_race_with_real_threaded_interleaving(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_race(world)
    real = server.load_book_cached
    entered = threading.Event()
    go = threading.Event()
    hits: List[int] = []
    out: Dict[str, Any] = {}

    def wrapper(folder: str) -> Any:
        book = real(folder)
        hits.append(1)
        entered.set()
        assert go.wait(JOIN_TIMEOUT_S)
        return book

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", wrapper)

    def run_get() -> None:
        try:
            out["resp"] = world.client.get(f"/api/notes/{G}/0")
        except BaseException as exc:  # surfaced by the assertions below
            out["exc"] = exc

    t = threading.Thread(target=run_get, daemon=True)
    t.start()
    try:
        assert entered.wait(JOIN_TIMEOUT_S)
        gen_book(world.books, G, NEW_TEXTS, FP_B, "B")
        stamped = _stamp_as_rebind()
    finally:
        go.set()
        t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()

    assert "exc" not in out, out.get("exc")
    assert len(hits) == 1
    assert out["resp"].status_code == 200, out["resp"].text
    assert world.records(G)["nb"]["orphaned"] is False
    assert disk(world.book(G))[0] == stamped

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", real)
    _assert_fresh_get_keeps_nb(world)


def test_k3_14_race_at_lock_entry_in_lock_notes_read_sees_the_stamp(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_race(world)
    real = notes_service._notes_write
    hits: List[int] = []
    stamped: List[bytes] = []

    def wrapper(books_dir: str, book_id: str, expected_book_uuid: object, deadline: Optional[float]) -> Any:
        if not hits:
            gen_book(world.books, G, NEW_TEXTS, FP_B, "B")
            stamped.append(_stamp_as_rebind())
        hits.append(1)
        return real(books_dir, book_id, expected_book_uuid, deadline)

    monkeypatch.setattr("reader3_app.notes_service._notes_write", wrapper)

    resp = world.client.get(f"/api/notes/{G}/0")

    assert resp.status_code == 200, resp.text
    assert "nb" in _listed(resp)
    assert world.records(G)["nb"]["orphaned"] is False
    assert disk(world.book(G))[0] == stamped[0]
    assert len(hits) == 1


# --------------------------------------------------------------------------- K3-13 (Book field)


def _bare_book() -> Book:
    return Book(metadata=BookMetadata(title="t", language="en"), spine=[], toc=[], images={},
                source_file="s", processed_at="p")


def test_k3_13a_constructor_default_is_none() -> None:
    book = _bare_book()
    assert getattr(book, "book_fingerprint", "MISSING") is None
    assert "book_fingerprint" in {f.name for f in dataclasses.fields(Book)}


def test_k3_13b_old_pickle_without_the_attribute_reads_none(tmp_path: Path) -> None:
    book = _bare_book()
    book.__dict__.pop("book_fingerprint", None)
    books = tmp_path / "books"
    (books / "old_data").mkdir(parents=True)
    (books / "old_data" / "book.pkl").write_bytes(pickle.dumps(book))
    _clear_caches()
    try:
        loaded = book_store.load_book_cached("old_data", str(books))
    finally:
        _clear_caches()

    assert "book_fingerprint" not in loaded.__dict__
    assert getattr(loaded, "book_fingerprint", "MISSING") is None
