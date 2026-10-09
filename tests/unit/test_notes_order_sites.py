"""012 WI-4c.2: the notes routes and ``_mark_orphans`` resolve chapters by ``order`` (Units C, D).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c2.md`` cases NO-01..NO-12, NO-P1, MO-01..MO-06, MO-P1.
Binding rulings (coordinator ruling 2026-10-09 WI-4c):

- R-3 follow-up 2: chapter GET on a gap or past the end is 200 with the stored notes; such notes are never
  orphaned (``_mark_orphans`` skips them); a negative index is still orphaned; ``orphaned=True`` stays True.
- R-3 follow-up 3: POST / PUT / disposition on a non-member order is 400 ``{"detail": "Invalid chapter_index"}``.
- NO-11 (R-3 amendment 2026-10-09): DELETE is id-keyed and 204 for any n >= 0.
- NO-03: a negative chapter GET stays 400.
- ``_mark_orphans(book, annotations, *, book_id: str) -> bool`` (adversary round 2 item 1).

Every route case seeds notes with ``fp=ABSENT`` on a pkl book (``book_fingerprint=None``), so the fingerprints
agree and the refresh really runs ``_mark_orphans`` (FR-C). Nothing is mocked.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from wi2b_world import ABSENT, _book, disk, rec, seed_notes
from wi4c2_world import H, books_dir_patched, make_client, order_book, text

from reader3_app.models.annotations import Annotation
from reader3_app.web.routers import notes

G02, G13 = "g02_data", "g13_data"
INVALID = {"detail": "Invalid chapter_index"}
NOT_FOUND = {"detail": "Book not found"}
ORDER_SETS = st.sets(st.integers(0, 9), max_size=5).map(sorted)


@pytest.fixture
def books(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    b = tmp_path / "books"
    b.mkdir()
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(b))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)
    monkeypatch.chdir(tmp_path)
    order_book(b, G02, [0, 2])
    order_book(b, G13, [1, 3])
    return b


@pytest.fixture
def client(books: Path) -> Iterator[TestClient]:
    with make_client(books) as c:
        yield c


def _records(book_dir: Path) -> Dict[str, Dict[str, Any]]:
    parsed = disk(book_dir)[2]
    assert parsed is not None
    return {r["id"]: r for r in parsed["annotations"]}


def _snap(book_dir: Path) -> Tuple[bytes, int]:
    raw, mtime_ns, _ = disk(book_dir)
    return raw, mtime_ns


def _listed_book(client: TestClient, folder: str) -> List[str]:
    r = client.get(f"/api/notes/{folder}")
    assert r.status_code == 200
    return sorted(a["id"] for c in r.json()["annotations_by_chapter"] for a in c["annotations"])


def _note_rec(nid: str, ci: int, quote: str, folder: str, note_text: str = "old") -> Dict[str, Any]:
    out = rec(nid, ci, quote, book_id=folder)
    out["type"] = "note"
    out["note_text"] = note_text
    return out


# --------------------------------------------------------------------------- Unit C


def test_no_01_chapter_get_on_internal_gap_returns_the_stored_note(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("g1", 1, "nowhere", book_id=G02)], fp=ABSENT)
    r = client.get(f"/api/notes/{G02}/1")
    assert r.status_code == 200
    body = r.json()
    assert [a["id"] for a in body["annotations"]] == ["g1"]
    assert body["chapter_index"] == 1
    assert _records(d)["g1"]["orphaned"] is False


def test_no_02_chapter_get_past_the_end_is_200_with_the_stored_note(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("p9", 9, "nowhere", book_id=G02)], fp=ABSENT)
    r = client.get(f"/api/notes/{G02}/9")
    assert r.status_code == 200
    assert [a["id"] for a in r.json()["annotations"]] == ["p9"]
    assert _records(d)["p9"]["orphaned"] is False


def test_no_03_negative_chapter_get_stays_400(client: TestClient) -> None:
    r = client.get(f"/api/notes/{G02}/-1")
    assert r.status_code == 400
    assert r.json() == INVALID


def test_no_04_book_get_lists_gap_notes_and_titles_members_by_order(client: TestClient, books: Path) -> None:
    d = books / G13
    seed_notes(
        d,
        [
            rec("m1", 1, "uniq-1-end", book_id=G13),
            rec("g2", 2, "nowhere", book_id=G13),
            rec("m3", 3, "uniq-3-end", book_id=G13),
        ],
        fp=ABSENT,
    )
    r = client.get(f"/api/notes/{G13}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_count"] == 3
    got = [
        (c["chapter_index"], c["chapter_title"], [a["id"] for a in c["annotations"]])
        for c in body["annotations_by_chapter"]
    ]
    assert got == [(1, "T0", ["m1"]), (2, "", ["g2"]), (3, "T1", ["m3"])]
    assert [r_["orphaned"] for r_ in _records(d).values()] == [False, False, False]


def test_no_05_post_on_gap_is_400_and_disk_untouched(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("n0", 0, "uniq-0-end", book_id=G02)], fp=ABSENT)
    before = _snap(d)
    r = client.post(f"/api/notes/{G02}/1", json={"type": "marker", "quote": "uniq-2-end"})
    assert r.status_code == 400
    assert r.json() == INVALID
    assert G02 not in r.text
    assert _snap(d) == before


@pytest.mark.parametrize("n", [9, -1])
def test_no_06_post_past_end_and_negative_stay_400(client: TestClient, books: Path, n: int) -> None:
    d = books / G02
    seed_notes(d, [rec("n0", 0, "uniq-0-end", book_id=G02)], fp=ABSENT)
    before = _snap(d)
    r = client.post(f"/api/notes/{G02}/{n}", json={"type": "marker", "quote": "uniq-2-end"})
    assert r.status_code == 400
    assert r.json() == INVALID
    assert _snap(d) == before


def test_no_07_post_on_last_member_stores_its_href(client: TestClient, books: Path) -> None:
    r = client.post(f"/api/notes/{G02}/2", json={"type": "marker", "quote": "uniq-2-end"})
    assert r.status_code == 201
    parsed = disk(books / G02)[2]
    assert parsed is not None
    [only] = parsed["annotations"]
    assert (only["chapter_index"], only["chapter_href"]) == (2, "Text/c1.xhtml")


def test_no_08_post_on_member_whose_order_differs_from_position(client: TestClient, books: Path) -> None:
    r = client.post(f"/api/notes/{G13}/1", json={"type": "marker", "quote": "uniq-1-end"})
    assert r.status_code == 201
    parsed = disk(books / G13)[2]
    assert parsed is not None
    [only] = parsed["annotations"]
    assert (only["chapter_index"], only["chapter_href"]) == (1, "Text/c0.xhtml")


def _seed_no09(d: Path) -> None:
    seed_notes(d, [_note_rec("g1", 1, "nowhere", G02), rec("n0", 0, "uniq-0-end", book_id=G02)], fp=ABSENT)


def test_no_09_put_on_gap_note_is_400_and_file_untouched(client: TestClient, books: Path) -> None:
    d = books / G02
    _seed_no09(d)
    before = _snap(d)
    r = client.put(f"/api/notes/{G02}/1/g1", json={"note_text": "new"})
    assert r.status_code == 400
    assert r.json() == INVALID
    assert _snap(d) == before


def test_no_10_disposition_on_gap_is_400_and_428_order_kept(client: TestClient, books: Path) -> None:
    d = books / G02
    _seed_no09(d)
    g = client.get(f"/api/notes/{G02}")
    assert g.status_code == 200
    etag = g.headers["ETag"]
    before = _snap(d)
    a = client.post(f"/api/notes/{G02}/1/g1/disposition", json={"action": "accept_binding"}, headers={"If-Match": etag})
    assert (a.status_code, a.json()) == (400, INVALID)
    b = client.post(f"/api/notes/{G02}/1/g1/disposition", json={"action": "accept_binding"})
    assert (b.status_code, b.json()) == (428, {"detail": "If-Match required"})
    assert _snap(d) == before


def test_no_11_delete_on_gap_and_past_end_note_is_204(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("g1", 1, "nowhere", book_id=G02), rec("p9", 9, "nowhere", book_id=G02)], fp=ABSENT)
    r1 = client.delete(f"/api/notes/{G02}/1/g1")
    assert r1.status_code == 204
    assert sorted(_records(d)) == ["p9"]
    r2 = client.delete(f"/api/notes/{G02}/9/p9")
    assert r2.status_code == 204
    assert sorted(_records(d)) == []


def _nosuch_requests(n: int) -> List[Tuple[str, str, Any, Dict[str, str]]]:
    base = f"/api/notes/nosuch_data/{n}"
    return [
        ("GET", base, None, {}),
        ("POST", base, {"type": "marker", "quote": "q"}, {}),
        ("PUT", f"{base}/x", {"note_text": "t"}, {}),
        ("DELETE", f"{base}/x", None, {}),
        ("POST", f"{base}/x/disposition", {"action": "accept_binding"}, {"If-Match": '"x"'}),
    ]


@pytest.mark.parametrize("n", [1, 9])
def test_no_12_book_not_found_precedes_chapter_check_on_all_five_sites(client: TestClient, n: int) -> None:
    for method, path, body, headers in _nosuch_requests(n):
        r = client.request(method, path, json=body, headers=headers)
        assert (method, path, r.status_code, r.json()) == (method, path, 404, NOT_FOUND)


def _listed(orders: List[int], ci: int, quote: str) -> bool:
    return ci not in orders or quote in text(ci)


@settings(max_examples=50, deadline=None)
@given(
    orders=st.sets(st.integers(0, 9), min_size=1, max_size=5).map(sorted),
    n=st.integers(-2, 12),
    route=st.sampled_from(["get", "post", "put", "disposition"]),
    vanish=st.booleans(),
)
def test_no_p1_read_write_domain_law(orders: List[int], n: int, route: str, vanish: bool) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        folder = f"nop1_{uuid.uuid4().hex[:8]}_data"
        d = order_book(books, folder, orders)
        y = rec("y", orders[0], f"uniq-{orders[0]}-end", book_id=folder)
        seeded = [y]
        if n >= 0:
            qx = "vanished" if (route == "get" and vanish) else f"uniq-{n}-end"
            seeded.append(rec("x", n, qx, book_id=folder))
        seed_notes(d, seeded, fp=ABSENT)
        with books_dir_patched(books) as client:
            if route == "get":
                r = client.get(f"/api/notes/{folder}/{n}")
                if n < 0:
                    assert (r.status_code, r.json()) == (400, INVALID)
                    return
                assert r.status_code == 200
                want = sorted(s["id"] for s in seeded if s["chapter_index"] == n and _listed(orders, n, s["quote"]))
                assert sorted(a["id"] for a in r.json()["annotations"]) == want
                return
            if route == "disposition":
                g = client.get(f"/api/notes/{folder}")
                assert g.status_code == 200
                before = _snap(d)
                r = client.post(
                    f"/api/notes/{folder}/{n}/x/disposition",
                    json={"action": "accept_binding"},
                    headers={"If-Match": g.headers["ETag"]},
                )
                if n in orders:
                    assert (r.status_code, r.json()) == (409, {"detail": "Book fingerprint unavailable"})
                else:
                    assert (r.status_code, r.json()) == (400, INVALID)
                assert _snap(d) == before
                return
            before = _snap(d)
            if route == "post":
                r = client.post(f"/api/notes/{folder}/{n}", json={"type": "marker", "quote": f"uniq-{n}-end"})
            else:
                r = client.put(f"/api/notes/{folder}/{n}/x", json={"note_text": "edited"})
            if n not in orders:
                assert (r.status_code, r.json()) == (400, INVALID)
                assert _snap(d) == before
                return
            if route == "post":
                assert r.status_code == 201
                new = [a for a in _records(d).values() if a["id"] not in {"x", "y"}]
                assert len(new) == 1
                assert (new[0]["chapter_index"], new[0]["chapter_href"]) == (n, H(orders, n))
            else:
                assert r.status_code == 200


# --------------------------------------------------------------------------- Unit D


def test_mo_01_gap_and_past_end_notes_not_orphaned_file_byte_identical(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("g1", 1, "nowhere", book_id=G02), rec("p9", 9, "nowhere", book_id=G02)], fp=ABSENT)
    before = _snap(d)
    assert _listed_book(client, G02) == ["g1", "p9"]
    assert _snap(d) == before


def test_mo_02_negative_index_on_disk_is_500_and_file_untouched(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(d, [rec("neg", -1, "uniq-0-end", book_id=G02)], fp=ABSENT)
    before = _snap(d)
    r = client.get(f"/api/notes/{G02}")
    assert r.status_code == 500
    assert "could not be read" in r.json()["detail"]
    assert _snap(d) == before


def test_mo_03_persisted_orphaned_gap_note_is_never_cleared(client: TestClient, books: Path) -> None:
    d = books / G02
    seed_notes(
        d,
        [rec("og", 1, "nowhere", orphaned=True, book_id=G02), rec("op", 9, "nowhere", orphaned=True, book_id=G02)],
        fp=ABSENT,
    )
    assert _listed_book(client, G02) == []
    r = client.get(f"/api/notes/{G02}/1")
    assert r.status_code == 200
    assert r.json()["annotations"] == []
    recs = _records(d)
    assert (recs["og"]["orphaned"], recs["op"]["orphaned"]) == (True, True)


def test_mo_04_member_note_matched_against_its_orders_text(client: TestClient, books: Path) -> None:
    d = books / G13
    seed_notes(d, [rec("m1", 1, "uniq-1-end", book_id=G13)], fp=ABSENT)
    assert _listed_book(client, G13) == ["m1"]
    assert _records(d)["m1"]["orphaned"] is False


def test_mo_05_member_note_whose_quote_is_not_in_its_order_is_orphaned(client: TestClient, books: Path) -> None:
    d = books / G13
    seed_notes(d, [rec("x1", 1, "uniq-3-end", book_id=G13), rec("v3", 3, "vanished", book_id=G13)], fp=ABSENT)
    assert _listed_book(client, G13) == []
    recs = _records(d)
    assert (recs["x1"]["orphaned"], recs["v3"]["orphaned"]) == (True, True)


def test_mo_06_negative_chapter_index_is_orphaned_by_mark_orphans() -> None:
    book = _book(G02, [text(0), text(2)], None, orders=[0, 2], toc=True)
    ann = Annotation.from_dict(rec("neg", 0, "uniq-0-end", book_id=G02), index=0)
    ann.chapter_index = -1
    changed = notes._mark_orphans(book, [ann], book_id=G02)
    assert changed is True
    assert ann.orphaned is True


@settings(max_examples=100, deadline=None)
@given(
    data=st.data(),
    orders=ORDER_SETS,
)
def test_mo_p1_mark_orphans_against_the_reference_model(data: st.DataObject, orders: List[int]) -> None:
    quotes = sorted({f"uniq-{o}-end" for o in orders} | {"vanished"})
    specs = data.draw(
        st.lists(st.tuples(st.integers(0, 12), st.sampled_from(quotes), st.booleans()), max_size=8)
    )
    folder = "mop1_data"
    book = _book(folder, [text(o) for o in orders], None, orders=list(orders), toc=True)
    anns = [
        Annotation.from_dict(rec(f"n{i}", ci, q, orphaned=orph, book_id=folder), index=i)
        for i, (ci, q, orph) in enumerate(specs)
    ]
    before = [a.orphaned for a in anns]
    changed = notes._mark_orphans(book, anns, book_id=folder)
    after = [a.orphaned for a in anns]
    for (ci, q, _), b, a in zip(specs, before, after):
        assert a == (b or (ci in orders and q not in text(ci))), (ci, q, b, a)
    assert changed == any(x != y for x, y in zip(before, after))
