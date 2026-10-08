"""012 WI-2b.2: the shared recompute / maybe-advance at every save site, and in-lock create stamping.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases V2-01 … V2-15 (ADR-0019 sections 四 and 五).

The law: after every save the notes-level ``book_fingerprint`` is
``_advance_target(post_state, current_in_lock, existing_before)`` when that is a str, and otherwise the
byte-identical prior value (or the key stays absent). Null is never written. Create stamps
``resolution="resolved"`` and ``bound_fingerprint = evaluated_fingerprint = current_in_lock``.

Every case runs against real generations (``book_format.publish`` under the real EX book lock), a real
``book.pkl``, the real notes lock and a real ``TestClient(server.app)`` on a tmp ``books/`` dir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from wi2b_world import (
    ABSENT,
    FP_A,
    FP_B,
    Q13_A,
    Q13_B,
    RESOLUTIONS,
    disk,
    gen_book,
    pkl_book,
    publish_gen,
    rec,
    seed_notes,
    version_on_disk,
)

from reader3_app import book_store, notes_service, search_service
from reader3_app.models.annotations import Annotation
from reader3_app.web import server

KEY = notes_service.NOTES_FINGERPRINT_KEY
G = "g_data"
P = "p_data"
BASE_URL = "http://127.0.0.1"


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


def _advance(anns: List[Annotation], cur: Any, existing: Any) -> Any:
    return notes_service._advance_target(anns, cur, existing)


def _ann(resolution: Any = "resolved", bound: Optional[str] = None, orphaned: bool = False) -> Annotation:
    return Annotation(book_id="x_data", quote="q", resolution=resolution, bound_fingerprint=bound, orphaned=orphaned)


def _clear_caches() -> None:
    # The one shared cache behind server/search_service's loaders; reached through book_store so a
    # test that wraps the literal "reader3_app.web.server.load_book_cached" can still clear it on teardown.
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_cached.cache_clear()


@dataclass
class World:
    client: TestClient
    books: Path

    def book(self, folder: str) -> Path:
        return self.books / folder

    def parsed(self, folder: str) -> Dict[str, Any]:
        parsed = disk(self.book(folder))[2]
        assert isinstance(parsed, dict)
        return parsed


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.chdir(tmp_path)
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


def _g(nid: str, quote: str, prefix: str = "", suffix: str = "", **kw: Any) -> Dict[str, Any]:
    return rec(nid, 0, quote, prefix, suffix, book_id=G, **kw)


def _n1(**kw: Any) -> Dict[str, Any]:
    return _g("n1", "QUOTE-ONE", "alpha ", " beta", bound=FP_A, evaluated=FP_A, **kw)


def _n2(**kw: Any) -> Dict[str, Any]:
    return _g("n2", "QUOTE-TWO", "gamma ", " delta", bound=FP_A, evaluated=FP_A, **kw)


# --------------------------------------------------------------------------- fixture self-checks


def test_fixture_publish_gen_leaves_ai_meta_bytes_unchanged(tmp_path: Path) -> None:
    book_dir = tmp_path / G
    book_dir.mkdir()
    meta = book_dir / "ai_meta.json"
    meta.write_bytes(b'{"book_uuid": "u-wi2b"}')
    publish_gen(tmp_path, G, Q13_A, FP_A, "A")
    publish_gen(tmp_path, G, Q13_B, FP_B, "B")
    assert meta.read_bytes() == b'{"book_uuid": "u-wi2b"}'
    assert book_store.book_fingerprint(G, str(tmp_path)) == FP_B


def test_fixture_gen_and_pkl_books_load_and_report_their_fingerprint(tmp_path: Path) -> None:
    gen_book(tmp_path, G, Q13_A, FP_A)
    pkl_book(tmp_path, P, Q13_A)
    try:
        loaded = book_store.load_book_cached(G, str(tmp_path))
        assert loaded.spine[0].text == Q13_A[0]  # type: ignore[attr-defined]
        assert loaded.spine[1].href == "Text/c1.xhtml"  # type: ignore[attr-defined]
        assert book_store.book_fingerprint(G, str(tmp_path)) == FP_A
        assert book_store.book_fingerprint(P, str(tmp_path)) is None
    finally:
        book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- V2-01 … V2-04 (pure predicate)

_EXISTING = [None, "OLD", "CUR", 123, {}, []]


@settings(max_examples=80, deadline=None)
@given(
    rows=st.lists(
        st.tuples(st.sampled_from(list(RESOLUTIONS)), st.sampled_from(["CUR", "OTHER", None]), st.booleans()),
        max_size=5,
    ),
    cur=st.sampled_from(["CUR", None]),
    existing=st.sampled_from(_EXISTING),
)
def test_v2_01_predicate_oracle(rows: List[tuple], cur: Optional[str], existing: Any) -> None:
    anns = [_ann(r, b, o) for r, b, o in rows]
    expected_advance = (
        isinstance(cur, str)
        and (existing is None or isinstance(existing, str))
        and all(a.resolution in {"resolved", "accepted"} and a.bound_fingerprint == cur for a in anns if not a.orphaned)
    )
    result = _advance(anns, cur, existing)
    assert result is notes_service.KEEP or result == cur
    assert result is not None
    if expected_advance:
        assert result == cur
    else:
        assert result is notes_service.KEEP


def test_v2_02_empty_and_all_orphaned_advance() -> None:
    assert _advance([], "CUR", "OLD") == "CUR"
    orphans = [_ann("ambiguous", "CUR", orphaned=True), _ann("unmatched", None, orphaned=True)]
    assert _advance(orphans, "CUR", "OLD") == "CUR"


@pytest.mark.parametrize(
    ("resolution", "bound"),
    [("ambiguous", "CUR"), ("unmatched", "CUR"), ("resolved", "OTHER"), ("resolved", None), ("accepted", "OTHER")],
)
def test_v2_03_single_blocker_keeps(resolution: str, bound: Optional[str]) -> None:
    assert _advance([_ann("resolved", "CUR"), _ann(resolution, bound)], "CUR", "OLD") is notes_service.KEEP


def test_v2_03_positive_control_resolved_and_accepted_advance() -> None:
    assert _advance([_ann("resolved", "CUR"), _ann("accepted", "CUR")], "CUR", "OLD") == "CUR"


@pytest.mark.parametrize(
    ("cur", "existing"),
    [(None, "OLD"), (None, None), ("CUR", 123), ("CUR", {}), ("CUR", []), ("CUR", True), ("CUR", 1.5)],
)
def test_v2_04_current_none_or_existing_non_str_keeps(cur: Optional[str], existing: Any) -> None:
    assert _advance([], cur, existing) is notes_service.KEEP


# --------------------------------------------------------------------------- service-level mutators

Mutator = Callable[[str, str], Any]


def _add(books: str, folder: str) -> Any:
    ann = Annotation(book_id=folder, chapter_index=0, type="marker", color="yellow",
                     quote="QUOTE-TWO", prefix="gamma ", suffix=" delta")
    return notes_service.add_annotation_and_version(books, ann)


def _update(books: str, folder: str) -> Any:
    return notes_service.update_annotation_and_version(books, folder, "n1", "t")


def _delete(books: str, folder: str) -> Any:
    return notes_service.delete_annotation_and_version(books, folder, "n1")


def _refresh(books: str, folder: str) -> Any:
    return notes_service.refresh_annotations_and_version(books, folder, lambda anns: True)


MUTATORS: Dict[str, Mutator] = {"add": _add, "update": _update, "delete": _delete, "refresh": _refresh}


def _ids(parsed: Dict[str, Any]) -> List[str]:
    return [a["id"] for a in parsed["annotations"]]


def _check_mutated(name: str, parsed: Dict[str, Any]) -> None:
    if name == "add":
        assert len(parsed["annotations"]) == 2
    elif name == "update":
        assert [a["note_text"] for a in parsed["annotations"]] == ["t"]
    elif name == "delete":
        assert parsed["annotations"] == []
    else:
        assert _ids(parsed) == ["n1"]


def _note_n1(folder: str) -> Dict[str, Any]:
    r = rec("n1", 0, "QUOTE-ONE", "alpha ", " beta", bound=FP_A, evaluated=FP_A, book_id=folder)
    r["type"] = "note"
    r["note_text"] = "seed"
    return r


@pytest.mark.parametrize("mutator", sorted(MUTATORS))
@pytest.mark.parametrize("value", [123, {}, []], ids=["int", "dict", "list"])
def test_v2_05_non_str_existing_carried_byte_identical(tmp_path: Path, mutator: str, value: Any) -> None:
    gen_book(tmp_path, G, Q13_A, FP_A)
    seed_notes(tmp_path / G, [_note_n1(G)], fp=value)
    before = json.dumps(disk(tmp_path / G)[2][KEY])  # type: ignore[index]

    MUTATORS[mutator](str(tmp_path), G)

    parsed = disk(tmp_path / G)[2]
    assert parsed is not None
    _check_mutated(mutator, parsed)
    assert json.dumps(parsed[KEY]) == before
    assert type(parsed[KEY]) is type(value)


@pytest.mark.parametrize("mutator", sorted(MUTATORS))
@pytest.mark.parametrize("value", ["OLD", ABSENT], ids=["old", "absent"])
def test_v2_06_pkl_only_book_keeps_or_omits(tmp_path: Path, mutator: str, value: Any) -> None:
    pkl_book(tmp_path, P, Q13_A)
    seed_notes(tmp_path / P, [_note_n1(P)], fp=value)

    MUTATORS[mutator](str(tmp_path), P)

    raw, _, parsed = disk(tmp_path / P)
    assert parsed is not None
    _check_mutated(mutator, parsed)
    if value is ABSENT:
        assert KEY not in parsed
    else:
        assert parsed[KEY] == "OLD"
    assert b'"book_fingerprint": null' not in raw


# --------------------------------------------------------------------------- V2-07 (property, S5)

_SEED_FP = st.sampled_from([ABSENT, "OLD", FP_A])
_SEED_RECORDS = st.lists(
    st.tuples(st.sampled_from(list(RESOLUTIONS)), st.sampled_from([FP_A, "OLD", None]), st.booleans()),
    max_size=3,
)
_OPS = st.lists(
    st.tuples(st.sampled_from(["add", "update", "delete", "refresh"]), st.integers(0, 10)),
    min_size=1,
    max_size=4,
)


@pytest.fixture(scope="module")
def v207_books(tmp_path_factory: pytest.TempPathFactory) -> Path:
    books = tmp_path_factory.mktemp("v207")
    gen_book(books, G, Q13_A, FP_A)
    return books


def _apply(books: str, op: str, pick: int, ids: List[str]) -> None:
    if op == "add":
        notes_service.add_annotation_and_version(
            books, Annotation(book_id=G, chapter_index=0, quote="QUOTE-ONE", prefix="alpha ", suffix=" beta"))
    elif op == "update":
        notes_service.update_annotation_and_version(books, G, ids[0], f"t{pick}")
    elif op == "delete":
        notes_service.delete_annotation_and_version(books, G, ids[pick % len(ids)])
    else:
        notes_service.refresh_annotations_and_version(books, G, lambda anns: True)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seed_fp=_SEED_FP, seed=_SEED_RECORDS, ops=_OPS)
def test_v2_07_recompute_law_across_operation_sequences(
    v207_books: Path, seed_fp: Any, seed: List[tuple], ops: List[tuple]
) -> None:
    records = [_g(f"s{i}", "QUOTE-ONE", resolution=r, bound=b, evaluated=b, orphaned=o)
               for i, (r, b, o) in enumerate(seed)]
    seed_notes(v207_books / G, records, fp=seed_fp)
    books = str(v207_books)
    for op, pick in ops:
        before_parsed = disk(v207_books / G)[2]
        assert before_parsed is not None
        before = before_parsed.get(KEY, ABSENT)
        ids = _ids(before_parsed)
        if op in ("update", "delete") and not ids:
            continue
        _apply(books, op, pick, ids)
        parsed = disk(v207_books / G)[2]
        assert parsed is not None
        post = notes_service.load_annotations(books, G)
        target = _advance(post, FP_A, None if before is ABSENT else before)
        if target == FP_A:
            assert parsed[KEY] == FP_A
        elif before is ABSENT:
            assert KEY not in parsed
        else:
            assert parsed[KEY] == before
        assert parsed.get(KEY, "absent") is not None


# --------------------------------------------------------------------------- V2-08 … V2-13 (routes)


def test_v2_08a_create_with_ambiguous_present_does_not_advance(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_n2(resolution="ambiguous")], fp="OLD")

    resp = world.client.post(f"/api/notes/{G}/0", json={"type": "marker", "quote": "QUOTE-ONE",
                                                        "prefix": "alpha ", "suffix": " beta"})

    assert resp.status_code == 201, resp.text
    parsed = world.parsed(G)
    assert _ids(parsed) == ["n2", resp.json()["id"]]
    assert parsed[KEY] == "OLD"


def test_v2_08b_update_with_ambiguous_present_does_not_advance(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    n2 = _n2(resolution="ambiguous")
    n2["type"] = "note"
    n2["note_text"] = "seed"
    seed_notes(world.book(G), [n2], fp="OLD")

    resp = world.client.put(f"/api/notes/{G}/0/n2", json={"note_text": "x"})

    assert resp.status_code == 200, resp.text
    parsed = world.parsed(G)
    assert [a["note_text"] for a in parsed["annotations"]] == ["x"]
    assert parsed[KEY] == "OLD"


def _seed_v209(world: World) -> str:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(G), [_n1(), _n2(resolution="ambiguous")], fp="OLD")
    got = world.client.get(f"/api/notes/{G}/0")
    assert got.status_code == 200, got.text
    return got.headers["ETag"]


def test_v2_09_old_delete_route_advances_when_last_blocker_goes(world: World) -> None:
    etag = _seed_v209(world)

    resp = world.client.delete(f"/api/notes/{G}/0/n2", headers={"If-Match": etag})

    assert resp.status_code == 204
    assert resp.content == b""
    assert resp.headers["ETag"] == f'"{version_on_disk(world.books, G)}"'
    parsed = world.parsed(G)
    assert parsed[KEY] == FP_A
    assert _ids(parsed) == ["n1"]


def test_v2_10_delete_with_ambiguous_remaining_does_not_advance(world: World) -> None:
    etag = _seed_v209(world)

    resp = world.client.delete(f"/api/notes/{G}/0/n1", headers={"If-Match": etag})

    assert resp.status_code == 204
    parsed = world.parsed(G)
    assert parsed[KEY] == "OLD"
    assert _ids(parsed) == ["n2"]


def test_v2_11_create_stores_chapter_href_resolution_and_fingerprints(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)

    resp = world.client.post(f"/api/notes/{G}/1", json={"type": "marker", "quote": "one only"})

    assert resp.status_code == 201, resp.text
    [record] = world.parsed(G)["annotations"]
    assert record["id"] == resp.json()["id"]
    assert record["chapter_href"] == "Text/c1.xhtml"
    assert record["resolution"] == "resolved"
    assert record["bound_fingerprint"] == FP_A
    assert record["evaluated_fingerprint"] == FP_A


@pytest.mark.parametrize("start", ["absent-file", "empty-unstamped"])
def test_v2_12_first_create_stamps_notes_then_orphan_marking_is_live(world: World, start: str) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    if start == "empty-unstamped":
        seed_notes(world.book(G), [], fp=ABSENT)

    resp = world.client.post(f"/api/notes/{G}/0", json={"type": "marker", "quote": "QUOTE-ONE",
                                                        "prefix": "alpha ", "suffix": " beta"})
    assert resp.status_code == 201, resp.text
    created_id = resp.json()["id"]
    parsed = world.parsed(G)
    assert parsed[KEY] == FP_A

    parsed["annotations"].append(_g("nx", "NOT-IN-TEXT", bound=FP_A, evaluated=FP_A))
    (world.book(G) / notes_service.NOTES_FILENAME).write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")

    got = world.client.get(f"/api/notes/{G}/0")

    assert got.status_code == 200, got.text
    assert [a["id"] for a in got.json()["annotations"]] == [created_id]
    persisted = {a["id"]: a for a in world.parsed(G)["annotations"]}
    assert persisted["nx"]["orphaned"] is True
    assert persisted[created_id]["orphaned"] is False


def test_v2_13_create_on_pkl_only_book_writes_no_key(world: World) -> None:
    pkl_book(world.books, P, Q13_A)

    resp = world.client.post(f"/api/notes/{P}/0", json={"type": "marker", "quote": "QUOTE-ONE"})

    assert resp.status_code == 201, resp.text
    parsed = world.parsed(P)
    [record] = parsed["annotations"]
    assert record["resolution"] == "resolved"
    assert record["bound_fingerprint"] is None
    assert record["evaluated_fingerprint"] is None
    assert record["chapter_href"] == "Text/c0.xhtml"
    assert KEY not in parsed


# --------------------------------------------------------------------------- V2-14, V2-15 (in-lock read)


def test_v2_14_create_stamps_in_lock_fingerprint_not_request_time(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    real = server.load_book_cached
    hits: List[int] = []

    def wrapper(folder: str) -> Any:
        book = real(folder)
        publish_gen(world.books, G, Q13_B, FP_B, "B")
        hits.append(1)
        return book

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", wrapper)

    resp = world.client.post(f"/api/notes/{G}/0", json={"type": "marker", "quote": "QUOTE-ONE",
                                                        "prefix": "alpha ", "suffix": " beta"})

    assert resp.status_code == 201, resp.text
    parsed = world.parsed(G)
    [record] = parsed["annotations"]
    assert record["bound_fingerprint"] == FP_B
    assert record["evaluated_fingerprint"] == FP_B
    assert parsed[KEY] == FP_B
    assert len(hits) == 1


def test_v2_15_create_stamps_fingerprint_read_inside_the_lock(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    real = notes_service._notes_write
    hits: List[int] = []

    def wrapper(books_dir: str, book_id: str, expected_book_uuid: object, deadline: Optional[float]) -> Any:
        if not hits:
            gen_book(world.books, G, Q13_B, FP_B, "B")
        hits.append(1)
        return real(books_dir, book_id, expected_book_uuid, deadline)

    monkeypatch.setattr("reader3_app.notes_service._notes_write", wrapper)

    resp = world.client.post(f"/api/notes/{G}/0", json={"type": "marker", "quote": "QUOTE-ONE",
                                                        "prefix": "alpha ", "suffix": " beta"})

    assert resp.status_code == 201, resp.text
    parsed = world.parsed(G)
    [record] = parsed["annotations"]
    assert record["bound_fingerprint"] == FP_B
    assert record["evaluated_fingerprint"] == FP_B
    assert parsed[KEY] == FP_B
    assert len(hits) == 1
