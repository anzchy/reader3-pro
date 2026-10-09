"""012 WI-2b.6: ``POST /api/notes/{book_id}/{chapter_index}/{note_id}/disposition`` (ADR-0019 section 七).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi2b.md`` cases H6-01 … H6-13, plus the coordinator's
service-level guard on an unknown ``action`` (``ValueError`` before any lock, zero writes).

The error order pinned here, outermost first. FastAPI validates the body, the path ints and the
``extra="forbid"`` keys before the handler runs, so 422 is first:

    422 (body / path int / extra key) → 428 If-Match missing or blank → 400 invalid book_id
    → 404 book → 400 chapter_index (< 0 or >= len(spine)) → 404 note "Annotation not found"
    → 409 "Book fingerprint unavailable" → 409 "Annotation orphaned" → 409 version conflict.

The no-op 200 (accept on ``resolved`` / ``accepted``) is decided only after the whole ladder. Every non-2xx
leaves ``notes.json`` byte-identical. On 200 the ETag equals the version on disk and the next GET's ETag.

Every case runs against a real ``TestClient(server.app)`` on a tmp ``books/`` dir, real generations
(``book_format.publish`` under the real EX book lock), a real ``book.pkl``, the real book and notes locks
and a real ``notes.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient
from wi2b_world import FP_A, FP_B, Q13_A, Q13_B, disk, gen_book, pkl_book, rec, seed_notes, version_on_disk

from reader3_app import book_store, notes_service, search_service
from reader3_app.web import server

KEY = notes_service.NOTES_FINGERPRINT_KEY
G = "g_data"
P = "p_data"
BASE_URL = "http://127.0.0.1"
ACCEPT = {"action": "accept_binding"}
DELETE = {"action": "delete"}
STALE = '"' + "0" * 64 + '"'
#: No existing contract test pins a literal for ``_validate_book_id``'s 400 (see the H6-05 docstring); this is
#: the traversal-shaped id, decoded by Starlette to ``..`` before it reaches the route.
INVALID_ID = "%2e%2e"
BODY_KEYS = {"id", "action", "resolution", "book_fingerprint_advanced", "message"}
CONFLICT_KEYS = {"detail", "etag", "annotation"}
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

    def book(self, folder: str = G) -> Path:
        return self.books / folder

    def snapshot(self, folder: str = G) -> tuple:
        raw, mtime_ns, _ = disk(self.book(folder))
        return raw, mtime_ns

    def parsed(self, folder: str = G) -> Dict[str, Any]:
        parsed = disk(self.book(folder))[2]
        assert isinstance(parsed, dict)
        return parsed

    def records(self, folder: str = G) -> Dict[str, Dict[str, Any]]:
        return {r["id"]: r for r in self.parsed(folder)["annotations"]}

    def etag_on_disk(self, folder: str = G) -> str:
        return f'"{version_on_disk(self.dir, folder)}"'

    def post(
        self, nid: str, body: Any, if_match: Optional[str], *, book: str = G, chapter: Any = 0
    ) -> Any:
        headers = {} if if_match is None else {"If-Match": if_match}
        return self.client.post(f"/api/notes/{book}/{chapter}/{nid}/disposition", json=body, headers=headers)

    def get_chapter(self, folder: str = G, chapter: int = 0) -> Any:
        resp = self.client.get(f"/api/notes/{folder}/{chapter}")
        assert resp.status_code == 200, resp.text
        return resp


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
    return rec("n1", 0, "QUOTE-ONE", "alpha ", " beta", book_id=G, **kw)


def _n2(**kw: Any) -> Dict[str, Any]:
    return rec("n2", 0, "QUOTE-TWO", "gamma ", " delta", book_id=G, **kw)


def _h6_state(world: World) -> str:
    """H6-01 steps 1-3: Q13 generation A with [n1, n2] bound FP_A, re-import as B, rebind, GET → ETag.

    After the rebind n1 is ``resolved`` (bound FP_B) and n2 is ``ambiguous``, so the notes key stays FP_A.
    The GET therefore disagrees with the Book (FP_B) and is read-only (D-1): its ETag is the on-disk version.
    """
    gen_book(world.books, G, Q13_A, FP_A)
    seed_notes(world.book(), [_n1(bound=FP_A, evaluated=FP_A), _n2(bound=FP_A, evaluated=FP_A)], fp=FP_A)
    gen_book(world.books, G, Q13_B, FP_B, "B")
    _clear_caches()
    notes_service.rebind_annotations(world.dir, G)
    records = world.records()
    assert (records["n1"]["resolution"], records["n2"]["resolution"]) == ("resolved", "ambiguous")
    assert world.parsed()[KEY] == FP_A
    etag = world.get_chapter().headers["ETag"]
    assert etag == world.etag_on_disk()
    return etag


def _listed(resp: Any) -> List[str]:
    return [a["id"] for a in resp.json()["annotations"]]


# --------------------------------------------------------------------------- H6-01 / H6-02 success


def test_h6_01_accept_binding_on_the_q13_ambiguous_note_advances_end_to_end(world: World) -> None:
    e = _h6_state(world)

    resp = world.post("n2", ACCEPT, e)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == BODY_KEYS
    assert (body["id"], body["action"], body["resolution"]) == ("n2", "accept_binding", "accepted")
    assert body["book_fingerprint_advanced"] is True
    assert isinstance(body["message"], str) and body["message"]
    assert resp.headers["ETag"] == world.etag_on_disk()
    assert world.records()["n2"]["resolution"] == "accepted"
    assert world.parsed()[KEY] == FP_B

    after = world.get_chapter()
    assert "n2" in _listed(after)
    assert after.headers["ETag"] == resp.headers["ETag"]


def test_h6_02_delete_removes_the_note_and_the_next_get_agrees_on_the_etag(world: World) -> None:
    e = _h6_state(world)

    resp = world.post("n2", DELETE, e)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == BODY_KEYS
    assert (body["id"], body["action"], body["resolution"]) == ("n2", "delete", None)
    assert body["book_fingerprint_advanced"] is True
    assert "n2" not in world.records()
    assert "n1" in world.records()
    assert resp.headers["ETag"] == world.etag_on_disk()
    assert world.get_chapter().headers["ETag"] == resp.headers["ETag"]


# --------------------------------------------------------------------------- H6-03 / H6-04 guards


@pytest.mark.parametrize("if_match", [None, "", "   "], ids=["missing", "empty", "whitespace"])
def test_h6_03_missing_or_blank_if_match_is_428_and_writes_nothing(world: World, if_match: Optional[str]) -> None:
    _h6_state(world)
    before = world.snapshot()

    resp = world.post("n2", ACCEPT, if_match)

    assert resp.status_code == 428, resp.text
    assert resp.json() == {"detail": "If-Match required"}
    assert world.snapshot() == before


@pytest.mark.parametrize(
    "body, chapter",
    [
        ({"action": "revive"}, 0),
        ({}, 0),
        ({"action": "delete", "extra": 1}, 0),
        (DELETE, "abc"),
    ],
    ids=["unknown-action", "missing-action", "extra-key", "path-int"],
)
def test_h6_04_validation_422_precedes_the_428(world: World, body: Dict[str, Any], chapter: Any) -> None:
    _h6_state(world)
    before = world.snapshot()

    resp = world.post("n2", body, None, chapter=chapter)

    assert resp.status_code == 422, resp.text
    assert isinstance(resp.json()["detail"], list)
    assert world.snapshot() == before


# --------------------------------------------------------------------------- H6-05 ladder


def test_h6_05_the_full_precedence_ladder_one_rung_per_request(world: World) -> None:
    """One request per rung, each built so that the next rung would also fire.

    Order: 422 (H6-04) → 428 → 400 invalid book_id → 404 book → 400 chapter_index (< 0, >= len(spine))
    → 404 note → 409 fingerprint unavailable → 409 orphaned → 409 version.

    Rung 2 deviation (recorded): ``_validate_book_id``'s 400 branch fires only when ``basename(id) != id``, and
    Starlette's ``{book_id}`` segment never carries a ``/``, so no HTTP request reaches that 400 (``%2e%2e``,
    ``a%2Fb_data``, ``a%5Cb_data`` were probed: 404). The matrix's own oracle is kept -- status and body equal
    PUT's for the identical id -- and the rung still pins that book-id validation runs after the 428 and before
    every later rung.
    """
    gen_book(world.books, G, Q13_B, FP_B, "B")
    seed_notes(world.book(G), [_n2(resolution="ambiguous", bound=FP_A, evaluated=FP_B),
                               rec("o", 0, "QUOTE-ONE", orphaned=True, book_id=G)], fp=FP_A)
    pkl_book(world.books, P, ["p zero", "p one"])
    seed_notes(world.book(P), [rec("o", 0, "gone", orphaned=True, book_id=P), rec("n1", 0, "p zero", book_id=P)])
    _clear_caches()
    before = (world.snapshot(G), world.snapshot(P))

    def status_body(resp: Any) -> tuple:
        return resp.status_code, resp.json()

    # 1. 428 before book-id validation.
    assert status_body(world.post("n2", ACCEPT, None, book=INVALID_ID)) == (428, {"detail": "If-Match required"})
    # 2. invalid book_id: identical to PUT for the identical id.
    rung2 = world.post("n2", ACCEPT, STALE, book=INVALID_ID)
    put2 = world.client.put(f"/api/notes/{INVALID_ID}/0/n2", json={"note_text": "x"}, headers={"If-Match": STALE})
    assert status_body(rung2) == status_body(put2)
    assert rung2.status_code in (400, 404)
    # 3. 404 book, before the chapter range.
    assert status_body(world.post("missing", ACCEPT, STALE, book="nosuch_data", chapter=999)) == (
        404,
        {"detail": "Book not found"},
    )
    # 4. 400 chapter_index, before the note lookup.
    for chapter in (999, -1, 3):
        resp = world.post("missing" if chapter != 3 else "n2", ACCEPT, STALE, chapter=chapter)
        assert status_body(resp) == (400, {"detail": "Invalid chapter_index"}), chapter
    # 4b. the last valid chapter gets past the range check.
    last = world.post("n2", ACCEPT, STALE, chapter=2)
    assert last.status_code == 409, last.text
    assert last.json()["detail"] == "Annotation version conflict"
    # 5. 404 note on a pkl-only book (fingerprint None would also fire).
    assert status_body(world.post("missing", ACCEPT, STALE, book=P)) == (404, {"detail": "Annotation not found"})
    # 6. fingerprint unavailable, before orphaned and version.
    assert status_body(world.post("o", ACCEPT, STALE, book=P)) == (409, {"detail": "Book fingerprint unavailable"})
    # 7. orphaned, before version.
    assert status_body(world.post("o", ACCEPT, STALE)) == (409, {"detail": "Annotation orphaned"})
    # 8. version conflict.
    rung8 = world.post("n2", ACCEPT, STALE)
    assert rung8.status_code == 409, rung8.text
    assert set(rung8.json()) == CONFLICT_KEYS
    assert rung8.json()["detail"] == "Annotation version conflict"

    assert (world.snapshot(G), world.snapshot(P)) == before


# --------------------------------------------------------------------------- H6-06 / H6-07 relations to PUT


def test_h6_06_a_book_replaced_between_snapshot_and_lock_is_refused_like_put(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _h6_state(world)
    meta = world.book() / "ai_meta.json"

    def set_uuid(value: str) -> None:
        meta.write_text(json.dumps({"book_uuid": value}), encoding="utf-8")

    set_uuid(UUID_1)
    real: Callable[..., Any] = server.load_book_cached
    hits: List[int] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        book = real(*args, **kwargs)
        set_uuid(UUID_2)  # after the route's identity snapshot, before the lock's recheck
        hits.append(1)
        return book

    monkeypatch.setattr("reader3_app.web.server.load_book_cached", wrapper)
    before = world.snapshot()

    resp_a = world.client.put(f"/api/notes/{G}/0/n2", json={"note_text": "x"}, headers={"If-Match": e})
    assert world.snapshot() == before
    set_uuid(UUID_1)
    resp_b = world.post("n2", ACCEPT, e)
    assert world.snapshot() == before

    assert hits == [1, 1]
    assert not 200 <= resp_a.status_code < 300, resp_a.text
    assert resp_b.status_code == resp_a.status_code
    assert resp_b.json() == resp_a.json()


def test_h6_07_stale_if_match_gets_the_same_409_payload_as_put(world: World) -> None:
    _h6_state(world)
    before = world.snapshot()

    resp_disp = world.post("n2", ACCEPT, STALE)
    resp_put = world.client.put(f"/api/notes/{G}/0/n2", json={"note_text": "x"}, headers={"If-Match": STALE})

    assert (resp_disp.status_code, resp_put.status_code) == (409, 409)
    assert resp_disp.json() == resp_put.json()
    assert resp_disp.json()["etag"] == world.etag_on_disk()
    assert resp_disp.json()["annotation"]["id"] == "n2"
    assert world.snapshot() == before


# --------------------------------------------------------------------------- H6-08 / H6-09 / H6-13 versions


def test_h6_08_accept_on_a_resolved_note_is_a_no_op_echoing_the_if_match(world: World) -> None:
    e = _h6_state(world)
    before = world.snapshot()

    resp = world.post("n1", ACCEPT, e)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["id"], body["action"], body["resolution"]) == ("n1", "accept_binding", "resolved")
    assert body["book_fingerprint_advanced"] is False
    assert resp.headers["ETag"] == e
    assert world.snapshot() == before


@pytest.mark.parametrize(
    "spelling, expect", [("weak", 200), ("bare", 200), ("star", 409)], ids=["weak", "bare", "star"]
)
def test_h6_09_if_match_forms_weak_and_bare_accepted_star_is_a_conflict(
    world: World, spelling: str, expect: int
) -> None:
    e = _h6_state(world)
    v = e.strip('"')
    sent = {"weak": f'W/"{v}"', "bare": v, "star": "*"}[spelling]
    before = world.snapshot()

    resp = world.post("n2", ACCEPT, sent)

    assert resp.status_code == expect, resp.text
    if expect == 200:
        assert world.records()["n2"]["resolution"] == "accepted"
        assert resp.headers["ETag"] == world.etag_on_disk()
    else:
        assert set(resp.json()) == CONFLICT_KEYS
        assert resp.json()["etag"] == e
        assert world.snapshot() == before


def _ac_state(world: World) -> str:
    """Generation B with one ``accepted`` note bound to FP_B; the ETag is the on-disk version."""
    gen_book(world.books, G, Q13_B, FP_B, "B")
    ac = rec("ac", 0, "QUOTE-ONE", resolution="accepted", bound=FP_B, evaluated=FP_B, book_id=G)
    seed_notes(world.book(), [ac], fp=FP_A)
    _clear_caches()
    return world.etag_on_disk()


@pytest.mark.parametrize("target", ["n1", "ac"], ids=["resolved", "accepted"])
def test_h6_13_stale_if_match_on_a_no_op_accept_is_a_409_not_a_200(world: World, target: str) -> None:
    if target == "n1":
        _h6_state(world)
    else:
        _ac_state(world)
    before = world.snapshot()

    resp = world.post(target, ACCEPT, STALE)

    assert resp.status_code == 409, resp.text
    payload = resp.json()
    assert set(payload) == CONFLICT_KEYS
    assert payload["detail"] == "Annotation version conflict"
    assert payload["etag"] == world.etag_on_disk()
    assert payload["etag"] != STALE
    assert payload["annotation"]["id"] == target
    assert world.snapshot() == before


# --------------------------------------------------------------------------- H6-10 / H6-11 semantics


def test_h6_10_lookup_is_by_id_and_the_path_chapter_is_only_range_checked(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B, "B")
    seed_notes(world.book(), [rec("c1n", 1, "chapter one", resolution="ambiguous", book_id=G)], fp=FP_A)
    _clear_caches()

    resp = world.post("c1n", ACCEPT, world.etag_on_disk(), chapter=0)

    assert resp.status_code == 200, resp.text
    assert resp.json()["resolution"] == "accepted"
    assert world.records()["c1n"]["resolution"] == "accepted"
    assert world.records()["c1n"]["chapter_index"] == 1


def test_h6_11_accept_on_unmatched_then_the_next_agreeing_get_orphans_it(world: World) -> None:
    gen_book(world.books, G, Q13_B, FP_B, "B")
    seed_notes(
        world.book(),
        [rec("um", 0, "GONE-TEXT", resolution="unmatched", bound=FP_A, evaluated=FP_B, book_id=G)],
        fp=FP_A,
    )
    _clear_caches()

    resp = world.post("um", ACCEPT, world.etag_on_disk())

    assert resp.status_code == 200, resp.text
    assert resp.json()["book_fingerprint_advanced"] is True
    assert world.parsed()[KEY] == FP_B
    after = world.get_chapter()
    assert "um" not in _listed(after)
    assert world.records()["um"]["orphaned"] is True


# --------------------------------------------------------------------------- H6-12 inventory


def test_h6_12_the_disposition_path_is_post_only(world: World) -> None:
    _h6_state(world)
    assert world.client.get(f"/api/notes/{G}/0/n2/disposition").status_code == 405


# --------------------------------------------------------------------------- service guard (coordinator ruling)


@pytest.mark.parametrize("action", ["revive", "", "DELETE", "accept"])
def test_service_rejects_an_unknown_action_before_any_lock_and_writes_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    e = _h6_state(world)
    real = notes_service._notes_write
    hits: List[int] = []

    def wrapper(books_dir: str, book_id: str, expected_book_uuid: object, deadline: Optional[float]) -> Any:
        hits.append(1)
        return real(books_dir, book_id, expected_book_uuid, deadline)

    monkeypatch.setattr("reader3_app.notes_service._notes_write", wrapper)
    before = world.snapshot()

    with pytest.raises(ValueError):
        notes_service.dispose_annotation_and_version(world.dir, G, "n2", action, e)

    assert hits == []
    assert world.snapshot() == before
    # Positive control: the seam binds -- a valid action enters the lock exactly once through it.
    result = notes_service.dispose_annotation_and_version(world.dir, G, "n2", "accept_binding", e)
    assert hits == [1]
    assert result.resolution == "accepted"
