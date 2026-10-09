"""012 WI-4c.2: ``/read/{id}/{n}`` is order-addressed and total for n >= 0 (Units A, B, E).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c2.md`` cases RO-01..RO-10, RO-P1, TB-01..TB-04, TB-P1,
GE-01, GE-02. Binding rulings: coordinator ruling 2026-10-09 WI-4c R-1 (any n >= 0 is 200, a gap renders with
no active TOC entry, no redirect for /0), R-2 (``totalChapters`` stays ``book.spine|length``), Q2 (indicator N is
the 1-based spine position, a gap shows an en dash).

Every case is an in-process ``TestClient`` over a real tmp ``BOOKS_DIR``: a real pickle and real Jinja. The
books are ``wi4c2_world.order_book`` pkl books with ``toc=True``; ``nav_state`` asserts the TOC link count, so
an empty TOC cannot make an "active" assertion vacuous.
"""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path
from typing import Iterator, List

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from wi2b_world import ABSENT, disk, rec, seed_notes
from wi4c2_world import (
    GAP_DASH,
    H,
    books_dir_patched,
    chapter_index_in_script,
    make_client,
    nav_state,
    order_book,
    total_chapters_in_script,
)

G02, G13, GL3, E0 = "g02_data", "g13_data", "gl3_data", "e0_data"
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
    order_book(b, GL3, [0, 1, 2])
    order_book(b, E0, [])
    return b


@pytest.fixture
def client(books: Path) -> Iterator[TestClient]:
    with make_client(books) as c:
        yield c


def _get(client: TestClient, path: str):  # type: ignore[no-untyped-def]
    return client.get(path, follow_redirects=False)


# --------------------------------------------------------------------------- Unit A


def test_ro_01_member_at_0_links_next_to_order_2(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/0")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[:4] == (["Text/c0.xhtml"], None, f"/read/{G02}/2", ["Previous"])


def test_ro_02_last_member_order_renders(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/2")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[:4] == (["Text/c1.xhtml"], f"/read/{G02}/0", None, ["Next"])


def test_ro_03_internal_gap_has_no_active_entry_and_order_neighbours(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/1")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[:4] == ([], f"/read/{G02}/0", f"/read/{G02}/2", [])
    assert re.search(r"chapterIndex:\s*1\b", r.text)


def test_ro_04_leading_gap_0_is_200_not_a_redirect(client: TestClient) -> None:
    r = _get(client, f"/read/{G13}/0")
    assert r.status_code == 200
    assert "location" not in r.headers
    assert nav_state(r.text, 2)[:4] == ([], None, f"/read/{G13}/1", ["Previous"])


def test_ro_05_past_the_end_prev_is_last_order(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/9")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[:4] == ([], f"/read/{G02}/2", None, ["Next"])


def test_ro_06_last_member_on_g13_prev_is_order_1(client: TestClient) -> None:
    r = _get(client, f"/read/{G13}/3")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[:4] == (["Text/c1.xhtml"], f"/read/{G13}/1", None, ["Next"])


def test_ro_07_negative_n_is_404(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/-1")
    assert r.status_code == 404
    assert r.json() == {"detail": "Chapter not found"}


@pytest.mark.parametrize("n", [0, 9])
def test_ro_08_unknown_book_is_404_before_chapter_logic(client: TestClient, n: int) -> None:
    r = _get(client, f"/read/nosuch_data/{n}")
    assert r.status_code == 404
    assert r.json() == {"detail": "Book not found"}


@pytest.mark.parametrize("n", [0, 5])
def test_ro_09_empty_spine_renders_with_both_sides_disabled(client: TestClient, n: int) -> None:
    r = _get(client, f"/read/{E0}/{n}")
    assert r.status_code == 200
    assert nav_state(r.text, 0)[:4] == ([], None, None, ["Previous", "Next"])
    assert "totalChapters: 0" in r.text


@pytest.mark.parametrize("folder,active", [(G13, []), (G02, ["Text/c0.xhtml"])])
def test_ro_10_bare_route_renders_exactly_what_0_renders(client: TestClient, folder: str, active: List[str]) -> None:
    a = _get(client, f"/read/{folder}")
    b = _get(client, f"/read/{folder}/0")
    assert a.status_code == b.status_code == 200
    assert a.text == b.text
    assert nav_state(a.text, 2)[0] == active
    assert nav_state(b.text, 2)[0] == active


def _model(folder: str, orders: List[int], n: int):  # type: ignore[no-untyped-def]
    below = [o for o in orders if o < n]
    above = [o for o in orders if o > n]
    return (
        [H(orders, n)] if n in orders else [],
        f"/read/{folder}/{max(below)}" if below else None,
        f"/read/{folder}/{min(above)}" if above else None,
    )


@settings(max_examples=60, deadline=None)
@given(orders=ORDER_SETS, n=st.integers(-3, 14))
def test_ro_p1_route_is_the_order_model(orders: List[int], n: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        folder = f"rop1_{uuid.uuid4().hex[:8]}_data"
        order_book(books, folder, orders)
        with books_dir_patched(books) as client:
            r = client.get(f"/read/{folder}/{n}", follow_redirects=False)
        if n < 0:
            assert (r.status_code, r.json()) == (404, {"detail": "Chapter not found"})
            return
        assert r.status_code == 200
        assert nav_state(r.text, len(orders))[:3] == _model(folder, orders, n)
        assert chapter_index_in_script(r.text) == n


# --------------------------------------------------------------------------- Unit B


def test_tb_01_gap_page_dash_indicator_and_r2_total(client: TestClient) -> None:
    r = _get(client, f"/read/{G02}/1")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[4] == f"Section {GAP_DASH} of 2"
    assert GAP_DASH == "–"
    assert "totalChapters: 2" in r.text
    count = re.search(r'data-testid="rd-chapter-count">(.*?)</span>', r.text, re.S)
    assert count is not None and "None" not in count.group(1)
    title = re.search(r"<title>(.*?)</title>", r.text, re.S)
    assert title is not None and "None" not in title.group(1)


@pytest.mark.parametrize("n,expected", [(3, "Section 2 of 2"), (1, "Section 1 of 2")])
def test_tb_02_member_indicator_is_1_based_position(client: TestClient, n: int, expected: str) -> None:
    r = _get(client, f"/read/{G13}/{n}")
    assert r.status_code == 200
    assert nav_state(r.text, 2)[4] == expected


def test_tb_03_spine_map_maps_hrefs_to_orders(client: TestClient) -> None:
    r = _get(client, f"/read/{G13}/1")
    assert r.status_code == 200
    m = re.search(r"const spineMap = \{(.*?)\};", r.text, re.S)
    assert m is not None
    body = m.group(1)
    assert re.search(r'"Text/c0\.xhtml"\s*:\s*1\s*,', body)
    assert re.search(r'"Text/c1\.xhtml"\s*:\s*3\s*,', body)
    assert not re.search(r":\s*0\s*,", body)


@pytest.mark.parametrize("path", [f"/read/{G02}/1", f"/read/{E0}/0"])
def test_tb_04_no_unguarded_current_chapter_dereference(client: TestClient, path: str) -> None:
    r = _get(client, path)
    assert r.status_code == 200
    for bad in ("Undefined", "None</", "jinja2.exceptions"):
        assert bad not in r.text, bad


@settings(max_examples=60, deadline=None)
@given(orders=ORDER_SETS, n=st.integers(0, 14))
def test_tb_p1_indicator_law(orders: List[int], n: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        folder = f"tbp1_{uuid.uuid4().hex[:8]}_data"
        order_book(books, folder, orders)
        with books_dir_patched(books) as client:
            r = client.get(f"/read/{folder}/{n}", follow_redirects=False)
        assert r.status_code == 200
        pos = f"{orders.index(n) + 1}" if n in orders else GAP_DASH
        assert nav_state(r.text, len(orders))[4] == f"Section {pos} of {len(orders)}"
        assert total_chapters_in_script(r.text) == len(orders)


# --------------------------------------------------------------------------- Unit E


def _positional_read(folder: str, k: int, n: int):  # type: ignore[no-untyped-def]
    return (
        [f"Text/c{n}.xhtml"],
        f"/read/{folder}/{n - 1}" if n > 0 else None,
        f"/read/{folder}/{n + 1}" if n < k - 1 else None,
        f"Section {n + 1} of {k}",
    )


@settings(max_examples=60, deadline=None)
@given(data=st.data(), k=st.integers(0, 5), route=st.sampled_from(["read", "notes_get", "notes_post"]))
def test_ge_01_gapless_books_match_the_positional_model(data: st.DataObject, k: int, route: str) -> None:
    n = data.draw(st.integers(-2, k - 1)) if k > 0 else data.draw(st.integers(-2, -1))
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        folder = f"ge01_{uuid.uuid4().hex[:8]}_data"
        book_dir = order_book(books, folder, list(range(k)))
        seed_notes(book_dir, [rec(f"m{i}", i, f"uniq-{i}-end", book_id=folder) for i in range(k)], fp=ABSENT)
        with books_dir_patched(books) as client:
            if route == "read":
                r = client.get(f"/read/{folder}/{n}", follow_redirects=False)
                if n < 0:
                    assert r.status_code == 404
                    return
                assert r.status_code == 200
                state = nav_state(r.text, k)
                assert (state[0], state[1], state[2], state[4]) == _positional_read(folder, k, n)
            elif route == "notes_get":
                r = client.get(f"/api/notes/{folder}/{n}")
                if n < 0:
                    assert r.status_code == 400
                    return
                assert r.status_code == 200
                assert [a["id"] for a in r.json()["annotations"]] == [f"m{n}"]
            else:
                r = client.post(f"/api/notes/{folder}/{n}", json={"type": "marker", "quote": f"uniq-{n}-end"})
                if n < 0:
                    assert r.status_code == 400
                    return
                assert r.status_code == 201
                parsed = disk(book_dir)[2]
                assert parsed is not None
                assert len(parsed["annotations"]) == k + 1
                seeded = {f"m{i}" for i in range(k)}
                new = [a for a in parsed["annotations"] if a["id"] not in seeded]
                assert len(new) == 1
                assert (new[0]["chapter_index"], new[0]["chapter_href"]) == (n, f"Text/c{n}.xhtml")


def test_ge_02_worked_gapless_example(client: TestClient) -> None:
    r = _get(client, f"/read/{GL3}/1")
    assert r.status_code == 200
    assert nav_state(r.text, 3) == (
        ["Text/c1.xhtml"],
        f"/read/{GL3}/0",
        f"/read/{GL3}/2",
        [],
        "Section 2 of 3",
    )
