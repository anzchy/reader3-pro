"""012 WI-2b.5: ``notes_service.dispose_annotation_and_version`` -- the user's explicit disposition of one annotation.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases D5-01 … D5-14 (ADR-0019 section 七).

The law:
- Error precedence is total, all decided inside the lock: AnnotationNotFound > BookFingerprintUnavailable (both
  actions) > AnnotationOrphaned (accept only) > NotesVersionConflict. Every error writes nothing.
- The no-op accept (target already ``resolved`` or ``accepted``) is decided only after the whole ladder, and
  writes nothing (D-8): same bytes, same mtime, same version, ``advanced is False``.
- ``accept_binding`` is idempotent. ``delete`` conserves every other record (``to_dict`` equal, order kept).
- ``result.advanced`` is True iff the advance target is a str that differs from the stored notes value, so with
  prior ``p`` it is exactly ``key_after == current and p != current``.
- The caller's ``deadline`` bounds the lock wait (not ``book_lock.BUDGET_S``).

Every case runs against real generations (``book_format.publish`` under the real EX book lock), a real
``book.pkl``, the real book and notes locks and a real ``notes.json`` on a tmp ``books/`` dir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from wi2b_world import (
    FP_A,
    FP_B,
    Q13_B,
    RESOLUTIONS,
    FakeClock,
    disk,
    gen_book,
    pkl_book,
    rec,
    run_in_worker,
    seed_notes,
    version_on_disk,
)

from reader3_app import book_lock, book_store, notes_service, search_service
from reader3_app.models.annotations import Annotation
from reader3_app.web import server

KEY = notes_service.NOTES_FINGERPRINT_KEY
G = "g_data"
ACCEPT = "accept_binding"
DELETE = "delete"
STALE = '"' + "0" * 64 + '"'
BINDING = (
    "id",
    "book_id",
    "chapter_index",
    "type",
    "color",
    "quote",
    "prefix",
    "suffix",
    "position",
    "cfi",
    "note_text",
    "created_at",
    "chapter_href",
    "orphaned",
)
UUID_1 = "11111111-1111-4111-8111-111111111111"
UUID_2 = "22222222-2222-4222-8222-222222222222"


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


def _clear_caches() -> None:
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_cached.cache_clear()


@dataclass
class World:
    books: Path

    @property
    def dir(self) -> str:
        return str(self.books)

    @property
    def book(self) -> Path:
        return self.books / G

    def parsed(self) -> Dict[str, Any]:
        parsed = disk(self.book)[2]
        assert isinstance(parsed, dict)
        return parsed

    def records(self) -> Dict[str, Dict[str, Any]]:
        return {r["id"]: r for r in self.parsed()["annotations"]}

    def snapshot(self) -> tuple:
        raw, mtime_ns, _ = disk(self.book)
        return raw, mtime_ns

    def version(self) -> str:
        return version_on_disk(self.dir, G)

    def dispose(self, nid: str, action: str, if_match: Optional[str], **kw: Any) -> notes_service.DispositionResult:
        return notes_service.dispose_annotation_and_version(self.dir, G, nid, action, if_match, **kw)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    books = tmp_path / "books"
    books.mkdir()
    monkeypatch.setattr(server, "BOOKS_DIR", str(books))
    _clear_caches()
    try:
        yield World(books=books)
    finally:
        _clear_caches()


def _n1(**kw: Any) -> Dict[str, Any]:
    """Unique in Q13_B chapter 0."""
    return rec("n1", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, **kw)


def _n2(**kw: Any) -> Dict[str, Any]:
    """Twice in Q13_B chapter 0."""
    return rec("n2", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, **kw)


def _binding(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: record[k] for k in BINDING}


def _gen_world(world: World, records: List[Dict[str, Any]], notes_fp: Any = FP_A) -> None:
    """Generation B is current (Q13_B, FP_B); ``records`` seeded with notes key ``notes_fp``."""
    gen_book(world.books, G, Q13_B, FP_B, "B")
    seed_notes(world.book, records, fp=notes_fp)


def _pkl_world(world: World, records: List[Dict[str, Any]], notes_fp: Any = FP_A) -> None:
    """A pkl-only book: ``book_store.book_fingerprint`` is ``None``."""
    pkl_book(world.books, G, Q13_B)
    seed_notes(world.book, records, fp=notes_fp)


# --------------------------------------------------------------------------- D5-01 … D5-05 (accept_binding)


def test_d5_01_accept_on_ambiguous_accepts_binds_to_current_and_advances(world: World) -> None:
    seeded_n2 = _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B), seeded_n2])
    v0 = world.version()

    result = world.dispose("n2", ACCEPT, v0, expected_book_uuid=book_lock.NO_UUID_CHECK, deadline=None)

    assert result == notes_service.DispositionResult(
        id="n2", action=ACCEPT, resolution="accepted", advanced=True, version=world.version()
    )
    n2 = world.records()["n2"]
    assert n2["resolution"] == "accepted"
    assert n2["bound_fingerprint"] == FP_B
    assert n2["evaluated_fingerprint"] == FP_B
    assert _binding(n2) == _binding(seeded_n2)
    assert world.parsed()[KEY] == FP_B


def test_d5_02_accept_on_unmatched_while_an_ambiguous_remains_does_not_advance(world: World) -> None:
    seeded_u = rec("u", 0, "GONE", book_id=G, resolution="unmatched", bound=FP_A, evaluated=FP_B)
    _gen_world(world, [seeded_u, _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)])

    result = world.dispose("u", ACCEPT, world.version())

    assert result.advanced is False
    assert result.resolution == "accepted"
    u = world.records()["u"]
    assert u["resolution"] == "accepted"
    assert u["bound_fingerprint"] == FP_B
    assert u["evaluated_fingerprint"] == FP_B
    assert _binding(u) == _binding(seeded_u)
    assert world.parsed()[KEY] == FP_A
    assert result.version == world.version()


def test_d5_03_accept_is_idempotent_the_second_call_writes_nothing(world: World) -> None:
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B), _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)])

    r1 = world.dispose("n2", ACCEPT, world.version())
    snap = world.snapshot()
    r2 = world.dispose("n2", ACCEPT, r1.version)

    assert r1.advanced is True
    assert r2.version == r1.version
    assert r2.advanced is False
    assert r2.resolution == "accepted"
    assert world.snapshot() == snap


def test_d5_04_accept_on_resolved_is_a_no_op_and_stays_resolved(world: World) -> None:
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B)])
    v0 = world.version()
    snap = world.snapshot()

    result = world.dispose("n1", ACCEPT, v0)

    assert result == notes_service.DispositionResult(
        id="n1", action=ACCEPT, resolution="resolved", advanced=False, version=v0
    )
    assert world.snapshot() == snap
    assert world.parsed()[KEY] == FP_A
    assert world.records()["n1"]["resolution"] == "resolved"


def test_d5_05_accept_on_already_accepted_with_a_stale_bound_is_still_a_no_op(world: World) -> None:
    seeded_ac = rec(
        "ac", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, resolution="accepted", bound=FP_A, evaluated=FP_A
    )
    _gen_world(world, [seeded_ac])
    v0 = world.version()
    snap = world.snapshot()

    result = world.dispose("ac", ACCEPT, v0)

    assert result.resolution == "accepted"
    assert result.advanced is False
    assert result.version == v0
    assert world.snapshot() == snap
    assert world.records()["ac"]["bound_fingerprint"] == FP_A


# --------------------------------------------------------------------------- D5-06 (orphaned)


@pytest.mark.parametrize("resolution", ["unmatched", "resolved"])
def test_d5_06_accept_on_orphaned_raises_and_revives_nothing(world: World, resolution: str) -> None:
    seeded_o = rec("o", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, orphaned=True, resolution=resolution, bound=FP_B)
    _gen_world(world, [seeded_o])
    snap = world.snapshot()

    with pytest.raises(notes_service.AnnotationOrphaned):
        world.dispose("o", ACCEPT, world.version())

    assert world.snapshot() == snap
    assert world.records()["o"]["orphaned"] is True
    assert world.records()["o"] == seeded_o


# --------------------------------------------------------------------------- D5-07 … D5-09 (delete)

_ROW = st.tuples(st.sampled_from(RESOLUTIONS), st.sampled_from([FP_B, FP_A, None]), st.booleans())


def _rows_to_records(rows: List[tuple]) -> List[Dict[str, Any]]:
    return [
        rec(f"r{i}", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, resolution=res, bound=b, orphaned=orph)
        for i, (res, b, orph) in enumerate(rows)
    ]


def test_d5_07_delete_conserves_every_other_record_property(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B, "B")

    @settings(max_examples=25, deadline=None)
    @given(rows=st.lists(_ROW, min_size=1, max_size=5), pick=st.integers(0, 4))
    def prop(rows: List[tuple], pick: int) -> None:
        seed_notes(world.book, _rows_to_records(rows), fp="OLD")
        before = [a.to_dict() for a in notes_service.load_annotations(world.dir, G)]
        target = before[pick % len(before)]["id"]

        result = world.dispose(target, DELETE, world.version())

        after = notes_service.load_annotations(world.dir, G)
        assert [a.to_dict() for a in after] == [d for d in before if d["id"] != target]
        assert result.id == target
        assert result.action == DELETE
        assert result.resolution is None
        assert (world.parsed()[KEY] == FP_B) is result.advanced
        assert result.version == world.version()

    prop()


def test_d5_08_delete_of_an_orphan_is_allowed(world: World) -> None:
    orphan = rec("o", 0, "GONE", book_id=G, orphaned=True, resolution="unmatched", bound=FP_A)
    _gen_world(world, [orphan, _n1(bound=FP_B, evaluated=FP_B)])

    result = world.dispose("o", DELETE, world.version())

    assert list(world.records()) == ["n1"]
    assert result.resolution is None
    assert result.advanced is True
    assert world.parsed()[KEY] == FP_B
    assert result.version == world.version()


def test_d5_09_deleting_the_last_blocker_advances(world: World) -> None:
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B), _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)])

    result = world.dispose("n2", DELETE, world.version())

    assert result.advanced is True
    assert result.resolution is None
    assert world.parsed()[KEY] == FP_B
    assert list(world.records()) == ["n1"]


# --------------------------------------------------------------------------- D5-10 (precedence ladder)


def _ladder_seed() -> List[Dict[str, Any]]:
    return [
        _n1(bound=FP_B, evaluated=FP_B),
        _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B),
        rec("o", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, orphaned=True, resolution="resolved", bound=FP_B),
        rec("ac", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, resolution="accepted", bound=FP_B, evaluated=FP_B),
    ]


_CONFLICT = notes_service.NotesVersionConflict
_LADDER = [
    ("a", "gen", "missing", ACCEPT, "stale", notes_service.AnnotationNotFound),
    ("b", "pkl", "missing", ACCEPT, "stale", notes_service.AnnotationNotFound),
    ("c", "pkl", "o", ACCEPT, "stale", notes_service.BookFingerprintUnavailable),
    ("d", "pkl", "n1", DELETE, "stale", notes_service.BookFingerprintUnavailable),
    ("e", "gen", "o", ACCEPT, "stale", notes_service.AnnotationOrphaned),
    ("f", "gen", "o", DELETE, "stale", _CONFLICT),
    ("g", "gen", "n2", ACCEPT, "stale", _CONFLICT),
    ("h", "gen", "n1", ACCEPT, "stale", _CONFLICT),
    ("i", "gen", "ac", ACCEPT, "stale", _CONFLICT),
    ("j", "pkl", "n1", ACCEPT, "current", notes_service.BookFingerprintUnavailable),
]


@pytest.mark.parametrize("row, kind, nid, action, match, expected", _LADDER, ids=[r[0] for r in _LADDER])
def test_d5_10_precedence_the_first_failure_in_order_wins_and_nothing_is_written(
    world: World, row: str, kind: str, nid: str, action: str, match: str, expected: type
) -> None:
    (_gen_world if kind == "gen" else _pkl_world)(world, _ladder_seed())
    v0 = world.version()
    on_disk = world.records()
    snap = world.snapshot()

    with pytest.raises(expected) as info:
        world.dispose(nid, action, STALE if match == "stale" else v0)

    assert type(info.value) is expected
    assert world.snapshot() == snap
    if expected is _CONFLICT:
        exc = info.value
        assert isinstance(exc, _CONFLICT)
        assert exc.current_version == v0
        assert exc.current_annotation is not None
        assert exc.current_annotation.id == nid
        assert exc.current_annotation.to_dict() == on_disk[nid]


# --------------------------------------------------------------------------- D5-11 (advanced consistency)

_ROW11 = st.tuples(st.sampled_from(RESOLUTIONS), st.sampled_from([FP_B, FP_A, None]), st.booleans())


def test_d5_11_advanced_is_exactly_whether_the_stored_key_moved_property(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B, "B")

    @settings(max_examples=30, deadline=None)
    @given(
        rows=st.lists(_ROW11, min_size=1, max_size=4),
        prior=st.sampled_from(["OLD", FP_B]),
        action=st.sampled_from([ACCEPT, DELETE]),
        pick=st.integers(0, 3),
    )
    def prop(rows: List[tuple], prior: str, action: str, pick: int) -> None:
        i = pick % len(rows)
        resolution, _, orphaned = rows[i]
        assume(not (orphaned and action == ACCEPT))
        seed_notes(world.book, _rows_to_records(rows), fp=prior)
        snap = world.snapshot()

        result = world.dispose(f"r{i}", action, world.version())

        parsed = world.parsed()
        assert result.advanced is (parsed[KEY] == FP_B and prior != FP_B)
        if prior == FP_B:
            assert parsed[KEY] == FP_B
        assert result.version == world.version()
        if action == ACCEPT and resolution in ("resolved", "accepted"):
            assert world.snapshot() == snap
            assert result.resolution == resolution
        elif action == ACCEPT:
            assert result.resolution == "accepted"
        else:
            assert result.resolution is None

    prop()


# --------------------------------------------------------------------------- D5-12, D5-13


def test_d5_12a_mismatched_expected_uuid_refuses_with_no_write(world: World) -> None:
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B), _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)])
    (world.book / "ai_meta.json").write_text(json.dumps({"book_uuid": UUID_1}), encoding="utf-8")
    snap = world.snapshot()

    with pytest.raises(book_lock.BookChanged):
        world.dispose("n2", ACCEPT, world.version(), expected_book_uuid=UUID_2)

    assert world.snapshot() == snap


@pytest.mark.parametrize("spelling", ["weak", "bare"])
def test_d5_12b_if_match_is_normalized(world: World, spelling: str) -> None:
    _gen_world(world, [_n1(bound=FP_B, evaluated=FP_B), _n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B)])
    v0 = world.version()

    result = world.dispose("n2", ACCEPT, f'W/"{v0}"' if spelling == "weak" else v0)

    assert result.resolution == "accepted"
    assert world.records()["n2"]["resolution"] == "accepted"


def test_d5_13_delete_when_the_key_is_already_current_is_not_advanced(world: World) -> None:
    _gen_world(
        world,
        [_n1(bound=FP_B, evaluated=FP_B), _n2(resolution="resolved", bound=FP_B, evaluated=FP_B)],
        notes_fp=FP_B,
    )

    result = world.dispose("n2", DELETE, world.version())

    assert result.advanced is False
    assert result.resolution is None
    assert world.parsed()[KEY] == FP_B
    assert list(world.records()) == ["n1"]
    assert result.version == world.version()


# --------------------------------------------------------------------------- D5-14 (deadline)


def test_d5_14_lock_wait_is_bounded_by_the_callers_deadline(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _gen_world(world, [_n1(bound=FP_A), _n2(resolution="ambiguous")])
    b0 = disk(world.book)[0]
    v0 = world.version()
    clock = FakeClock().install(monkeypatch)
    calls: Dict[str, Callable[[float], Any]] = {
        "add": lambda d: notes_service.add_annotation_and_version(
            world.dir,
            Annotation(book_id=G, chapter_index=0, type="marker", color="yellow", quote="QUOTE-ONE"),
            deadline=d,
        ),
        ACCEPT: lambda d: notes_service.dispose_annotation_and_version(
            world.dir, G, "n2", ACCEPT, if_match=v0, expected_book_uuid=book_lock.NO_UUID_CHECK, deadline=d
        ),
        DELETE: lambda d: notes_service.dispose_annotation_and_version(
            world.dir, G, "n2", DELETE, if_match=v0, expected_book_uuid=book_lock.NO_UUID_CHECK, deadline=d
        ),
    }
    rows: Dict[tuple, tuple] = {}

    with book_lock.acquire(world.dir, G, mode=book_lock.EXCLUSIVE, holder="import"):
        for name in ("add", ACCEPT, DELETE):
            for span in (0.2, 5.0):
                start = clock.now
                sleeps0 = clock.sleeps
                _, exc = run_in_worker(lambda f=calls[name], d=start + span: f(d))
                rows[(name, span)] = (exc, start, clock.now, clock.sleeps - sleeps0)

    assert disk(world.book)[0] == b0
    for (name, span), (exc, start, now, polls) in rows.items():
        assert isinstance(exc, book_lock.BookLockBusy), (name, span, exc)
        assert exc.holder_category == "import"
        assert polls >= 1
        elapsed = now - start
        if span == 0.2:
            assert now >= start + 0.2
            assert elapsed < 1.0, (name, elapsed)
        else:
            assert elapsed >= 5.0, (name, elapsed)
    for name in (ACCEPT, DELETE):
        for span in (0.2, 5.0):
            assert type(rows[(name, span)][0]) is type(rows[("add", span)][0])
