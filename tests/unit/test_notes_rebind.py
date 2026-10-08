"""012 WI-2b.4: ``notes_service.rebind_annotations`` -- re-resolve every annotation against the current generation.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases R4-10 … R4-29 (ADR-0019), plus the self-checks of
the WI-2b.4 fixtures in ``wi2b_world`` (``flip_chapter_byte``, ``FakeClock``, ``run_in_worker``, ``post_counts``).

The law:
- Conservation: the binding fields (``BINDING``) are equal before and after; orphans are never revived.
- Oracle: every non-orphaned record that is not (accepted and bound to current) ends with
  ``resolution == match_resolution(text at its own chapter_index, or "unmatched" past the end)``,
  ``evaluated == current``, and ``bound == current`` iff resolved (otherwise unchanged).
- Write rule: save iff a record changed or the advance target is not KEEP and differs from the stored value;
  ``advanced`` is exactly the second half. Otherwise nothing is written and the ETag is unchanged.
- Idempotence: a second rebind writes nothing. Cannot judge (no generation, corrupt manifest, any chapter read
  failure) writes nothing. A missing ``notes.json`` is never created.
- Counts: the post-rebind tally of non-orphaned resolutions, skipped accepts included, zeros absent.

Every case runs against real generations (``book_format.publish`` under the real EX book lock), a real
``book.pkl``, the real book and notes locks and a real ``TestClient(server.app)`` on a tmp ``books/`` dir.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from book_format_helpers import REPAIRABLE
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from wi2b_world import (
    ABSENT,
    FP_A,
    FP_B,
    Q13_A,
    Q13_B,
    RESOLUTIONS,
    FakeClock,
    disk,
    flip_chapter_byte,
    gen_book,
    gen_inputs,
    pkl_book,
    post_counts,
    publish_gen,
    rec,
    run_in_worker,
    seed_notes,
    version_on_disk,
    write_book_pkl,
)

from reader3_app import book_format, book_lock, book_store, notes_service, search_service
from reader3_app.models.annotations import Annotation, match_resolution
from reader3_app.web import server

KEY = notes_service.NOTES_FINGERPRINT_KEY
G = "g_data"
BASE_URL = "http://127.0.0.1"
JOIN_TIMEOUT_S = 10.0
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
    # Reached through book_store so a test that wraps "reader3_app.web.server.load_book_cached" can still clear it.
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_cached.cache_clear()


@dataclass
class World:
    client: TestClient
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

    def rebind(self, **kw: Any) -> notes_service.RebindResult:
        return notes_service.rebind_annotations(self.dir, G, **kw)


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


def _n1(**kw: Any) -> Dict[str, Any]:
    """Unique in both Q13_A and Q13_B chapter 0."""
    return rec("n1", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, **kw)


def _n2(**kw: Any) -> Dict[str, Any]:
    """Unique in Q13_A chapter 0, twice in Q13_B chapter 0."""
    return rec("n2", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, **kw)


def _binding(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: record[k] for k in BINDING}


def _q13_reimport(world: World, records: List[Dict[str, Any]], notes_fp: Any = FP_A) -> None:
    """Generation A (Q13_A, FP_A), ``records`` seeded, then re-import as generation B (Q13_B, FP_B)."""
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book, records, fp=notes_fp)
    gen_book(world.books, G, Q13_B, FP_B, "B")


# --------------------------------------------------------------------------- fixture self-checks


def test_fixture_flip_chapter_byte_passes_stat_and_fails_the_content_read(tmp_path: Path) -> None:
    books = tmp_path / "books"
    publish_gen(books, G, ["t0 zero", "t1 one", "t2 two"], FP_A, "A")
    gen_dir = books / G / book_format.GEN_DIR / str(book_format.validate_stat(books / G).generation)
    size = (gen_dir / book_format.CHAPTERS).stat().st_size

    flip_chapter_byte(books / G)

    m = book_format.validate_stat(books / G)
    assert (gen_dir / book_format.CHAPTERS).stat().st_size == size
    assert book_format.read_chapter(gen_dir, m.chapters[0]).text == "t0 zero"
    with pytest.raises(book_format.ChapterReadError):
        book_format.read_chapter(gen_dir, m.chapters[1])


def test_fixture_fake_clock_tells_a_passed_deadline_from_the_default_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    books = tmp_path / "books"
    publish_gen(books, G, ["t0"], FP_A, "A")
    clock = FakeClock().install(monkeypatch)

    def shared(deadline: Optional[float]) -> None:
        with book_lock.acquire(str(books), G, mode=book_lock.SHARED, holder="notes", deadline=deadline):
            pass

    with book_lock.acquire(str(books), G, mode=book_lock.EXCLUSIVE, holder="import"):
        start = clock.now
        _, exc = run_in_worker(lambda: shared(start + 0.2))
        assert isinstance(exc, book_lock.BookLockBusy)
        assert exc.holder_category == "import"
        assert clock.now == start + 0.2
        assert clock.sleeps >= 1

        start = clock.now
        _, exc = run_in_worker(lambda: shared(None))
        assert isinstance(exc, book_lock.BookLockBusy)
        assert clock.now == start + book_lock.BUDGET_S


def test_fixture_run_in_worker_returns_result_or_exception() -> None:
    assert run_in_worker(lambda: 7) == (7, None)
    _, exc = run_in_worker(lambda: 1 // 0)
    assert isinstance(exc, ZeroDivisionError)


def test_fixture_post_counts_omits_orphans_and_zeros() -> None:
    records = [
        rec("a", 0, "q", resolution="resolved"),
        rec("b", 0, "q", resolution="resolved"),
        rec("c", 0, "q", resolution="ambiguous", orphaned=True),
        rec("d", 0, "q", resolution="accepted"),
    ]
    assert post_counts(records) == {"resolved": 2, "accepted": 1}


# --------------------------------------------------------------------------- R4-10 … R4-17 (examples)


def test_r4_10_q13_unique_match_resolves_binds_and_advances(world: World) -> None:
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A)])

    result = world.rebind()

    assert result.fingerprint == FP_B
    assert result.counts == {"resolved": 1}
    assert result.advanced is True
    assert result.version == version_on_disk(world.dir, G)
    n1 = world.records()["n1"]
    assert n1["resolution"] == "resolved"
    assert n1["bound_fingerprint"] == FP_B
    assert n1["evaluated_fingerprint"] == FP_B
    assert world.parsed()[KEY] == FP_B


def test_r4_11_q13_quote_twice_is_ambiguous_binding_kept_and_visible_in_the_chapter_get(world: World) -> None:
    seeded_n2 = _n2(bound=FP_A, evaluated=FP_A)
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A), seeded_n2])

    result = world.rebind()

    assert result.counts == {"resolved": 1, "ambiguous": 1}
    assert result.advanced is False
    records = world.records()
    n2 = records["n2"]
    assert n2["resolution"] == "ambiguous"
    assert n2["evaluated_fingerprint"] == FP_B
    assert n2["bound_fingerprint"] == FP_A
    assert _binding(n2) == _binding(seeded_n2)
    assert records["n1"]["resolution"] == "resolved"
    assert records["n1"]["bound_fingerprint"] == FP_B
    assert world.parsed()[KEY] == FP_A

    # Book pkl FP_B vs notes FP_A: the GET skips orphan judgement and lists n2 as ambiguous.
    _clear_caches()
    resp = world.client.get(f"/api/notes/{G}/0")
    assert resp.status_code == 200, resp.text
    listed = {a["id"]: a for a in resp.json()["annotations"]}
    assert listed["n2"]["resolution"] == "ambiguous"


def test_r4_12_strict_unique_quote_with_changed_context_is_unmatched(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book, [_n1(bound=FP_A, evaluated=FP_A)], fp=FP_A)
    gen_book(world.books, G, ["omega QUOTE-ONE beta.", Q13_A[1], Q13_A[2]], FP_B, "B")

    result = world.rebind()

    n1 = world.records()["n1"]
    assert n1["resolution"] == "unmatched"
    assert n1["evaluated_fingerprint"] == FP_B
    assert n1["bound_fingerprint"] == FP_A
    assert world.parsed()[KEY] == FP_A
    assert result.advanced is False
    assert result.counts == {"unmatched": 1}


def test_r4_13_same_chapter_index_only_and_past_the_end_is_unmatched_not_orphaned(world: World) -> None:
    gen_book(world.books, G, ["MOVED there", "c1 text", "c2text"], FP_A)
    seed_notes(
        world.book,
        [rec("mv", 0, "MOVED", book_id=G, bound=FP_A), rec("hi", 2, "c2text", book_id=G, bound=FP_A)],
        fp=FP_A,
    )
    gen_book(world.books, G, ["nothing", "MOVED here"], FP_B, "B")

    result = world.rebind()

    records = world.records()
    assert records["mv"]["resolution"] == "unmatched"
    assert records["hi"]["resolution"] == "unmatched"
    assert records["hi"]["orphaned"] is False
    assert records["hi"]["chapter_index"] == 2
    assert records["hi"]["evaluated_fingerprint"] == FP_B
    assert result.counts == {"unmatched": 2}


def test_r4_14_orphaned_records_stay_orphaned_untouched_and_uncounted(world: World) -> None:
    orphan = rec(
        "o", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G,
        orphaned=True, resolution="unmatched", bound=None, evaluated=None,
    )
    _q13_reimport(world, [orphan, _n1(bound=FP_A, evaluated=FP_A)])

    result = world.rebind()

    records = world.records()
    assert records["o"] == orphan
    assert records["n1"]["bound_fingerprint"] == FP_B
    assert result.counts == {"resolved": 1}


def test_r4_15_accepted_on_current_is_left_alone_accepted_on_stale_is_rematched(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    ac = rec("ac", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, resolution="accepted", bound=FP_B, evaluated=FP_B)
    stale = rec("as", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, resolution="accepted", bound=FP_A, evaluated=FP_A)
    seed_notes(world.book, [ac, stale], fp=FP_A)

    result = world.rebind()

    records = world.records()
    assert records["ac"] == ac
    assert records["as"]["resolution"] == "resolved"
    assert records["as"]["bound_fingerprint"] == FP_B
    assert records["as"]["evaluated_fingerprint"] == FP_B
    assert result.counts == {"accepted": 1, "resolved": 1}


def test_r4_16_idempotence_second_rebind_writes_nothing(world: World) -> None:
    ac = rec("ac", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, resolution="accepted", bound=FP_B, evaluated=FP_B)
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A), _n2(bound=FP_A, evaluated=FP_A), ac])

    r1 = world.rebind()
    snap = world.snapshot()
    r2 = world.rebind()

    assert world.snapshot() == snap
    assert r2.version == r1.version == version_on_disk(world.dir, G)
    assert r2.advanced is False
    assert r2.counts == r1.counts
    assert world.records()["ac"]["resolution"] == "accepted"


def test_r4_17_advance_only_rebind_still_writes_the_pending_advance(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    n1 = _n1(resolution="resolved", bound=FP_B, evaluated=FP_B)
    seed_notes(world.book, [n1], fp="OLD")

    result = world.rebind()

    assert world.parsed()[KEY] == FP_B
    assert result.advanced is True
    assert world.records()["n1"] == n1
    assert result.counts == {"resolved": 1}


# --------------------------------------------------------------------------- R4-18 (conservation + oracle)

R18_TEXTS = ["x QA y QA z QB w", "QC only here", "a b a b"]
_R18_ROW = st.tuples(
    st.integers(0, 3),
    st.sampled_from(["QA", "QB", "QC", "a b", "missing"]),
    st.sampled_from(["", "x ", " y", "a ", " z", "nope"]),
    st.sampled_from(["", "x ", " y", "a ", " z", "nope"]),
    st.sampled_from(RESOLUTIONS),
    st.sampled_from([FP_A, FP_B, None]),
    st.booleans(),
)


def test_r4_18_binding_conservation_and_oracle_property(world: World) -> None:
    gen_book(world.books, G, R18_TEXTS, FP_B)

    @settings(max_examples=40, deadline=None)
    @given(rows=st.lists(_R18_ROW, min_size=1, max_size=5))
    def prop(rows: List[tuple]) -> None:
        seeded = [
            rec(f"r{i}", ci, q, p, s, book_id=G, resolution=res, bound=b, orphaned=orph)
            for i, (ci, q, p, s, res, b, orph) in enumerate(rows)
        ]
        seed_notes(world.book, seeded, fp="OLD")

        result = world.rebind()

        parsed = world.parsed()
        after = parsed["annotations"]
        assert [r["id"] for r in after] == [r["id"] for r in seeded]
        for before, now in zip(seeded, after):
            assert _binding(now) == _binding(before)
            skipped = before["resolution"] == "accepted" and before["bound_fingerprint"] == FP_B
            if before["orphaned"] or skipped:
                assert now == before
                continue
            ci = before["chapter_index"]
            expected = (
                match_resolution(R18_TEXTS[ci], before["prefix"], before["quote"], before["suffix"])
                if ci < len(R18_TEXTS)
                else "unmatched"
            )
            assert now["resolution"] == expected
            assert now["evaluated_fingerprint"] == FP_B
            assert now["bound_fingerprint"] == (FP_B if expected == "resolved" else before["bound_fingerprint"])
        advances = notes_service._advance_target([Annotation.from_dict(r) for r in after], FP_B, "OLD") == FP_B
        assert parsed[KEY] == (FP_B if advances else "OLD")
        assert result.advanced is advances
        assert result.counts == post_counts(after)
        assert result.fingerprint == FP_B
        assert result.version == version_on_disk(world.dir, G)

    prop()


# --------------------------------------------------------------------------- R4-19 (cannot judge)


def _cannot_judge(world: World, kind: str, outside: Path) -> None:
    if kind == "pkl_only":
        pkl_book(world.books, G, Q13_A)
        seed_notes(world.book, [_n1()], fp="OLD")
    elif kind == "corrupt_manifest":
        gen_book(world.books, G, Q13_A, FP_A)
        seed_notes(world.book, [_n1(bound="OLD")], fp="OLD")
        REPAIRABLE["R-unparse"][0](world.book, outside)
    else:
        gen_book(world.books, G, Q13_A, FP_A)
        seed_notes(world.book, [_n1(bound="OLD"), rec("c1", 1, "chapter one", book_id=G)], fp="OLD")
        flip_chapter_byte(world.book)


@pytest.mark.parametrize("kind", ["pkl_only", "corrupt_manifest", "chapter_read_failure"])
def test_r4_19_cannot_judge_writes_nothing(world: World, tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _cannot_judge(world, kind, outside)
    snap = world.snapshot()

    result = world.rebind()

    assert world.snapshot() == snap
    assert result.fingerprint is None
    assert result.advanced is False
    assert result.version == version_on_disk(world.dir, G)
    # (c): chapter 0 is readable, yet n1 is not rebound -- the whole rebind is a no-op.
    assert world.records()["n1"]["bound_fingerprint"] == ("OLD" if kind != "pkl_only" else None)


# --------------------------------------------------------------------------- R4-20, R4-21 (concurrency)


def test_r4_20_import_holds_ex_rebind_waits_then_sees_the_new_generation(world: World) -> None:
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book, [_n1(bound=FP_A, evaluated=FP_A), _n2(bound=FP_A, evaluated=FP_A)], fp=FP_A)
    out: Dict[str, Any] = {}

    def run() -> None:
        try:
            out["result"] = world.rebind(deadline=book_lock._monotonic() + 10)
        except BaseException as exc:  # surfaced by the assertions below
            out["exc"] = exc

    t = threading.Thread(target=run, daemon=True)
    with book_lock.acquire(world.dir, G, mode=book_lock.EXCLUSIVE, holder="import"):
        book_format.publish(world.book, gen_inputs(Q13_B, FP_B, "B"))
        write_book_pkl(world.books, G, Q13_B, FP_B)
        t.start()
        t.join(0.3)
        still_waiting = t.is_alive()
    t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()

    assert still_waiting
    assert "exc" not in out, out.get("exc")
    assert out["result"].fingerprint == FP_B
    live = [r for r in world.parsed()["annotations"] if not r["orphaned"]]
    assert len(live) == 2
    assert all(r["evaluated_fingerprint"] == FP_B for r in live)


def _assert_add_and_rebind_both_landed(world: World) -> None:
    records = world.records()
    assert len(records) == 3
    added = [r for nid, r in records.items() if nid not in ("n1", "n2")]
    assert len(added) == 1
    assert added[0]["bound_fingerprint"] == FP_B
    assert added[0]["evaluated_fingerprint"] == FP_B
    assert records["n1"]["resolution"] == "resolved"
    assert records["n1"]["bound_fingerprint"] == FP_B
    assert records["n2"]["resolution"] == "ambiguous"
    assert records["n2"]["evaluated_fingerprint"] == FP_B


def _seed_add_race(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    seed_notes(world.book, [_n1(bound=FP_A, evaluated=FP_A), _n2(bound=FP_A, evaluated=FP_A)], fp=FP_A)


def _thread(fn: Callable[[], Any], out: Dict[str, Any], name: str) -> threading.Thread:
    def target() -> None:
        try:
            out[name] = fn()
        except BaseException as exc:  # surfaced by the assertions below
            out[name + "_exc"] = exc

    return threading.Thread(target=target, daemon=True)


def test_r4_21_add_against_rebind_rebind_first_no_lost_update(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_add_race(world)
    real = book_store.current_generation
    inside = threading.Event()
    go = threading.Event()
    hits: List[int] = []

    def wrapper(book_id: str, books_dir: str) -> Any:
        got = real(book_id, books_dir)
        hits.append(1)
        if len(hits) == 1:
            inside.set()
            assert go.wait(JOIN_TIMEOUT_S)
        return got

    monkeypatch.setattr("reader3_app.book_store.current_generation", wrapper)
    out: Dict[str, Any] = {}
    r = _thread(world.rebind, out, "rebind")
    body = {"type": "marker", "color": "yellow", "quote": "QUOTE-ONE"}
    c = _thread(lambda: world.client.post(f"/api/notes/{G}/0", json=body), out, "add")
    try:
        r.start()
        assert inside.wait(JOIN_TIMEOUT_S)
        c.start()
        c.join(0.3)
        assert c.is_alive()
    finally:
        go.set()
        r.join(JOIN_TIMEOUT_S)
        if c.ident is not None:
            c.join(JOIN_TIMEOUT_S)
    assert not r.is_alive() and not c.is_alive()

    assert "rebind_exc" not in out and "add_exc" not in out, out
    assert out["add"].status_code == 201, out["add"].text
    assert len(hits) >= 1
    _assert_add_and_rebind_both_landed(world)


def test_r4_21_add_against_rebind_add_first_no_lost_update(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_add_race(world)
    real = book_store.book_fingerprint
    inside = threading.Event()
    go = threading.Event()
    hits: List[int] = []
    out: Dict[str, Any] = {}
    added = Annotation(book_id=G, chapter_index=0, type="marker", color="yellow", quote="QUOTE-ONE")
    c = _thread(lambda: notes_service.add_annotation_and_version(world.dir, added), out, "add")

    def wrapper(book_id: str, books_dir: str) -> Any:
        got = real(book_id, books_dir)
        if threading.current_thread() is c and not hits:
            hits.append(1)
            inside.set()
            assert go.wait(JOIN_TIMEOUT_S)
        return got

    monkeypatch.setattr("reader3_app.book_store.book_fingerprint", wrapper)
    r = _thread(world.rebind, out, "rebind")
    try:
        c.start()
        assert inside.wait(JOIN_TIMEOUT_S)
        r.start()
        r.join(0.3)
        assert r.is_alive()
    finally:
        go.set()
        c.join(JOIN_TIMEOUT_S)
        if r.ident is not None:
            r.join(JOIN_TIMEOUT_S)
    assert not r.is_alive() and not c.is_alive()

    assert "rebind_exc" not in out and "add_exc" not in out, out
    assert len(hits) == 1
    _assert_add_and_rebind_both_landed(world)


# --------------------------------------------------------------------------- R4-22 (race with the real rebind)

OLD_TEXTS = ["alpha old text", "c1", "c2"]
NEW_TEXTS = ["alpha NEWQUOTE text", "c1", "c2"]


def test_r4_22_stale_book_race_with_the_real_rebind(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    gen_book(world.books, G, OLD_TEXTS, FP_A)
    seed_notes(world.book, [rec("nb", 0, "NEWQUOTE", book_id=G, bound=FP_A)], fp=FP_A)
    real = server.load_book_cached
    hits: List[int] = []

    def wrapper(folder: str) -> Any:
        book = real(folder)
        gen_book(world.books, G, NEW_TEXTS, FP_B, "B")
        notes_service.rebind_annotations(world.dir, G)
        hits.append(1)
        return book

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", wrapper)

    first = world.client.get(f"/api/notes/{G}/0")

    assert len(hits) == 1
    assert first.status_code == 200, first.text
    nb = world.records()["nb"]
    assert nb["orphaned"] is False
    assert nb["resolution"] == "resolved"
    assert nb["bound_fingerprint"] == FP_B
    assert world.parsed()[KEY] == FP_B

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", real)
    _clear_caches()
    second = world.client.get(f"/api/notes/{G}/0")
    assert second.status_code == 200, second.text
    assert "nb" in [a["id"] for a in second.json()["annotations"]]
    assert world.records()["nb"]["orphaned"] is False


# --------------------------------------------------------------------------- R4-23 … R4-29


def test_r4_23_mismatched_expected_uuid_refuses_with_no_write(world: World) -> None:
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A)])
    (world.book / "ai_meta.json").write_text(json.dumps({"book_uuid": UUID_1}), encoding="utf-8")
    snap = world.snapshot()

    with pytest.raises(book_lock.BookChanged):
        world.rebind(expected_book_uuid=UUID_2)

    assert world.snapshot() == snap


def test_r4_24_non_str_notes_key_survives_a_rebind_that_changes_annotations(world: World) -> None:
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A)], notes_fp=123)

    result = world.rebind()

    parsed = world.parsed()
    assert parsed["annotations"][0]["bound_fingerprint"] == FP_B
    assert parsed[KEY] == 123
    assert type(parsed[KEY]) is int
    assert result.advanced is False


def test_r4_25_rebind_after_an_advancing_rebind_is_a_full_no_op(world: World) -> None:
    _q13_reimport(world, [_n1(bound=FP_A, evaluated=FP_A)])

    r1 = world.rebind()
    snap = world.snapshot()
    r2 = world.rebind()

    assert r1.advanced is True
    assert r2.advanced is False
    assert r2.version == r1.version == version_on_disk(world.dir, G)
    assert r2.counts == {"resolved": 1}
    assert world.snapshot() == snap


def test_r4_26_lock_wait_is_bounded_by_the_callers_deadline(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    seed_notes(world.book, [_n1(bound=FP_A), _n2(resolution="ambiguous")], fp=FP_A)
    b0 = disk(world.book)[0]
    clock = FakeClock().install(monkeypatch)
    calls: Dict[str, Callable[[float], Any]] = {
        "add": lambda d: notes_service.add_annotation_and_version(
            world.dir,
            Annotation(book_id=G, chapter_index=0, type="marker", color="yellow", quote="QUOTE-ONE"),
            deadline=d,
        ),
        "rebind": lambda d: notes_service.rebind_annotations(world.dir, G, deadline=d),
    }
    rows: Dict[tuple, tuple] = {}

    with book_lock.acquire(world.dir, G, mode=book_lock.EXCLUSIVE, holder="import"):
        for name in ("add", "rebind"):
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
    for span in (0.2, 5.0):
        assert type(rows[("rebind", span)][0]) is type(rows[("add", span)][0])


def _r4_27_seed(with_unmatched: bool) -> List[Dict[str, Any]]:
    out = [
        rec("o", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, orphaned=True, resolution="ambiguous"),
        rec("ac", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, resolution="accepted", bound=FP_B, evaluated=FP_B),
        _n1(),
        rec("r2", 1, "chapter one", "", " only", book_id=G),
        _n2(),
    ]
    if with_unmatched:
        out.append(rec("um", 0, "GONE", book_id=G))
    return out


@pytest.mark.parametrize(
    "with_unmatched, expected",
    [
        (True, {"accepted": 1, "resolved": 2, "ambiguous": 1, "unmatched": 1}),
        (False, {"accepted": 1, "resolved": 2, "ambiguous": 1}),
    ],
)
def test_r4_27_counts_are_an_exact_tally_with_zeros_omitted(
    world: World, with_unmatched: bool, expected: Dict[str, int]
) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    seed_notes(world.book, _r4_27_seed(with_unmatched), fp="OLD")

    result = world.rebind()

    assert result.counts == expected
    if not with_unmatched:
        assert "unmatched" not in result.counts


def test_r4_28_no_notes_json_nothing_written_no_file_created(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    before = set(os.listdir(world.book))

    r = world.rebind()

    assert r.counts == {}
    assert r.advanced is False
    assert r.fingerprint == FP_B
    assert r.version == notes_service.annotations_version([])
    assert not (world.book / notes_service.NOTES_FILENAME).exists()
    after = set(os.listdir(world.book))
    assert before <= after
    assert after - before <= {notes_service.NOTES_LOCK_FILENAME}


@pytest.mark.parametrize("stored", [ABSENT, "OLD"])
def test_r4_29_present_but_empty_notes_advances_the_key(world: World, stored: Any) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    seed_notes(world.book, [], fp=stored)

    r = world.rebind()

    parsed = world.parsed()
    assert parsed.get(KEY) == FP_B
    assert parsed["annotations"] == []
    assert r.advanced is True
    assert r.counts == {}
    assert r.version == notes_service.annotations_version([]) == version_on_disk(world.dir, G)


def test_r4_29b_present_empty_and_already_current_writes_nothing(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B)
    seed_notes(world.book, [], fp=FP_B)
    snap = world.snapshot()

    r = world.rebind()

    assert r.advanced is False
    assert r.counts == {}
    assert world.snapshot() == snap
