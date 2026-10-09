"""012 WI-4b.1 (a): ``GET /`` enumerates through ``list_book_ids``
(matrix ``.claude/tdd-guardian/tests-20261009-wi4b1.md``,
cases B1-01..B1-11, B1-09b, B1-13 and the G-b rows B1-20..B1-25).

Law (enumeration agreement): for every books dir ``d``, the card ids on ``/``, in document order, equal
``[b for b in list_book_ids(d) if loadable(b)]``. Corollaries: the ids are ascending (asserted against
``sorted``, not against ``list_book_ids``), and adding a directory ``list_book_ids`` rejects never changes ``/``.

No mocks (Q2): every library is real files under a tmp ``BOOKS_DIR``. The G-b rows pin the 012-interim state --
a gen-only book is invisible on every surface -- and flip at 4b.5 by design (test names end
``_gb_flips_at_4b5``). Each gen-only book is first proven real and loadable (P1-P3), and every route that
resolves uuids carries a positive mint control, so "no ``ai_meta.json`` for the gen-only book" is not vacuous.
"""

from __future__ import annotations

import ast
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import pytest
from bs4 import BeautifulSoup
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from wi2b_world import FP_A, publish_gen, write_book_pkl
from wi4c2_world import assert_locks_under, books_dir_patched, clear_caches

from reader3_app import book_store
from reader3_app.ai.books import BookUuidResolver
from reader3_app.book_format import MANIFEST
from reader3_app.search_service import list_book_ids

from conftest import BOOK_AUTHOR, BOOK_ID, BOOK_TITLE, World, build_book

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_PY = REPO_ROOT / "src" / "reader3_app" / "web" / "routers" / "library.py"

AI_META = "ai_meta.json"
SAMPLE_COVER_URL = "/read/sample_data/images/cover.jpg"  # build_cover_url("sample_data", "cover.jpg"), inlined


# --------------------------------------------------------------------------- fixtures and parsers


@pytest.fixture
def lib(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """``world``, with the cwd moved to its project root (B1-09b's relative ``books/`` decoy; no stray relative
    path can touch the real checkout)."""
    monkeypatch.chdir(world.project_root)
    clear_caches()
    yield world


def _get(world: World, url: str, root: Optional[Path] = None):
    resp = world.client.get(url)
    assert_locks_under(root if root is not None else world.project_root)
    return resp


def card_ids(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [str(c["data-book-id"]) for c in soup.select('article[data-testid="lib-book-card"]')]


def card(html: str, book_id: str):
    soup = BeautifulSoup(html, "html.parser")
    found = [c for c in soup.select('article[data-testid="lib-book-card"]') if c.get("data-book-id") == book_id]
    assert len(found) == 1, (book_id, len(found))
    return found[0]


def section_counts(html: str) -> Dict[str, int]:
    """``{book_id: int(td[3])}`` from the ``lib-book-row`` table, with the column vacuity guard."""
    soup = BeautifulSoup(html, "html.parser")
    heads = [th.get_text() for th in soup.select("table.lib-table thead th")]
    assert heads[3] == "Sections", heads
    return {
        str(row["data-book-id"]): int(row.select("td")[3].get_text(strip=True))
        for row in soup.select('tr[data-testid="lib-book-row"]')
    }


def gen_only_preconditions(books: Path, gid: str) -> None:
    """P1-P3: the gen-only book is real and loadable, and has no flat pkl; then clear the caches P2 warmed."""
    assert book_store.storage_format(gid, str(books)) == "valid"  # P1
    loaded = book_store.load_book_cached(gid, str(books))
    assert loaded.metadata.title == gid  # type: ignore[attr-defined]  # P2
    assert not (books / gid / "book.pkl").exists()  # P3
    clear_caches()


def corrupt_manifest(book_dir: Path) -> None:
    """The ``corrupt(world, "garbage")`` shape of ``test_storage_format_routes.py``, re-implemented locally."""
    (book_dir / MANIFEST).write_bytes(b"{ not json")


def _gb_world(world: World) -> Path:
    """G-b common input: sample_data (flat), bflat_data (flat, 2 chapters), cgen_data (gen-only), P1-P3 run."""
    books = world.books_dir
    write_book_pkl(books, "bflat_data", ["bflat one", "bflat two"], None)
    publish_gen(books, "cgen_data", ["cgen one"], FP_A, "g1")
    gen_only_preconditions(books, "cgen_data")
    return books


# --------------------------------------------------------------------------- B1-01 .. B1-02


def test_b1_01_mixed_library_lists_exactly_the_flat_books(lib: World) -> None:
    """B1-01 -- L2+L3, S1/S3: five shapes; three of them are negatives. Red-first at HEAD."""
    books = lib.books_dir
    write_book_pkl(books, "bflat_data", ["one", "two"], None)
    publish_gen(books, "cgen_data", ["gen one"], FP_A, "g1")
    (books / "xempty_data").mkdir()
    (books / "dgenonly_data" / "gen").mkdir(parents=True)
    gen_only_preconditions(books, "cgen_data")
    assert not (books / "bflat_data" / AI_META).exists()

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["bflat_data", "sample_data"]
    assert "cgen_data" not in resp.text
    assert (books / "bflat_data" / AI_META).is_file()
    assert not (books / "cgen_data" / AI_META).exists()


def test_b1_02_flat_books_keep_every_rendered_field(lib: World) -> None:
    """B1-02 -- L1/S1: the R-6 regression pin -- title, author, cover, section count per flat book."""
    books = lib.books_dir
    write_book_pkl(books, "bflat_data", ["one", "two"], None)

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert set(card_ids(resp.text)) == {"bflat_data", BOOK_ID}
    sample = card(resp.text, BOOK_ID)
    assert sample.select_one("span.lib-card-title").get_text() == BOOK_TITLE
    assert sample.select_one("span.lib-card-author").get_text() == BOOK_AUTHOR
    img = sample.select_one("img.lib-cover")
    assert img is not None and img["src"] == SAMPLE_COVER_URL
    bflat = card(resp.text, "bflat_data")
    assert bflat.select_one("img.lib-cover") is None
    assert bflat.select_one("span.lib-cover--blank") is not None
    assert bflat.select_one("span.lib-card-title").get_text() == "bflat_data"
    counts = section_counts(resp.text)
    assert counts[BOOK_ID] == len(build_book().spine)
    assert counts["bflat_data"] == 2


# --------------------------------------------------------------------------- B1-03 (Hypothesis)

_NAMES3 = st.lists(st.from_regex(r"[a-z0-9]{1,8}", fullmatch=True), min_size=2, max_size=8, unique=True).flatmap(
    lambda ns: st.tuples(st.just(ns), st.permutations(ns))
)
_TWENTY = [f"n{k:02d}" for k in range(20)]


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@example(data=(_TWENTY, list(reversed(_TWENTY))))
@given(data=_NAMES3)
def test_b1_03_card_order_is_ascending_regardless_of_creation_order(data: Tuple[List[str], List[str]]) -> None:
    """B1-03 -- L1/S4: the creation order is drawn independently of the names. Green-first guard (APFS listdir
    order is unspecified); this pins the new ascending order."""
    names, creation_order = data
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        for n in creation_order:
            write_book_pkl(books, f"{n}_data", [f"text {n}"], None)
        with books_dir_patched(books) as client:
            resp = client.get("/")
            assert_locks_under(Path(tmp))
        assert resp.status_code == 200
        ids = card_ids(resp.text)
        assert ids == sorted(ids)
        assert set(ids) == {f"{n}_data" for n in names}
        assert ids == list_book_ids(str(books))


# --------------------------------------------------------------------------- B1-04


def _shape(books: Path, shape: str) -> None:
    if shape == "empty":
        (books / "edge_data").mkdir()
    elif shape == "gen_only_dir":
        (books / "edge_data" / "gen").mkdir(parents=True)
    elif shape == "images_only":
        (books / "edge_data" / "images").mkdir(parents=True)
        (books / "edge_data" / "images" / "cover.jpg").write_bytes(b"\xff\xd8 jpeg-ish")
    elif shape == "regular_file":
        (books / "edge_data").write_bytes(b"not a directory")
    elif shape == "no_suffix":
        write_book_pkl(books, "edge", ["edge text"], None)
    elif shape == "dotted":
        write_book_pkl(books, ".hidden_data", ["hidden text"], None)
    else:  # pragma: no cover - a typo in the parametrize list
        raise AssertionError(shape)


@pytest.mark.parametrize("shape", ["empty", "gen_only_dir", "images_only", "regular_file", "no_suffix", "dotted"])
def test_b1_04_directories_that_are_not_books_are_never_listed(lib: World, shape: str) -> None:
    """B1-04 -- L2/S2: each predicate edge of ``list_book_ids`` on its own; ``dotted`` is left to the law."""
    books = lib.books_dir
    _shape(books, shape)

    resp = _get(lib, "/")

    assert resp.status_code == 200
    ids = card_ids(resp.text)
    assert ids == [b for b in list_book_ids(str(books)) if b in (BOOK_ID, ".hidden_data")]
    if shape != "dotted":
        assert ids == [BOOK_ID]


# --------------------------------------------------------------------------- B1-05


def test_b1_05_only_a_gen_only_book_renders_the_empty_state(lib: World) -> None:
    """B1-05 -- L3, S3+S5: the minimal I1 red, then a state step proving the route does mint."""
    books = lib.books_dir
    shutil.rmtree(books / BOOK_ID)
    publish_gen(books, "cgen_data", ["gen one"], FP_A, "g1")
    gen_only_preconditions(books, "cgen_data")

    first = _get(lib, "/")

    assert first.status_code == 200
    assert card_ids(first.text) == []
    assert BeautifulSoup(first.text, "html.parser").select_one("[data-testid=lib-empty]") is not None
    assert "cgen_data" not in first.text
    assert not (books / "cgen_data" / AI_META).exists()

    write_book_pkl(books, "bflat_data", ["one"], None)
    clear_caches()
    second = _get(lib, "/")

    assert second.status_code == 200
    assert card_ids(second.text) == ["bflat_data"]
    assert (books / "bflat_data" / AI_META).is_file()
    assert not (books / "cgen_data" / AI_META).exists()


# --------------------------------------------------------------------------- B1-06


def test_b1_06_corrupt_manifest_with_flat_pkl_is_skipped_with_one_error(
    lib: World, caplog: pytest.LogCaptureFixture
) -> None:
    """B1-06 -- L3+L5/S3: 200, absent, exactly one ERROR naming the id. Kills iterate-and-also-rescan."""
    books = lib.books_dir
    corrupt_manifest(books / BOOK_ID)
    write_book_pkl(books, "zgood_data", ["good"], None)
    manifest_before = (books / BOOK_ID / MANIFEST).read_bytes()
    caplog.set_level(logging.ERROR)

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["zgood_data"]
    assert BOOK_TITLE not in resp.text
    named = [r for r in caplog.records if r.levelno >= logging.ERROR and BOOK_ID in r.getMessage()]
    assert len(named) == 1, [(r.name, r.getMessage()) for r in named]
    assert named[0].name == "reader3_app.book_store"
    assert (books / BOOK_ID / MANIFEST).read_bytes() == manifest_before


# --------------------------------------------------------------------------- B1-07 / B1-08 (Hypothesis)

SHAPES = ("flat", "gen_only", "empty", "gen_dir_only", "corrupt_flat", "no_suffix_flat", "regular_file")
_NAME = st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True)


def _folder(name: str, shape: str) -> str:
    return name if shape == "no_suffix_flat" else f"{name}_data"


def _make(books: Path, folder: str, shape: str, chapters: int) -> None:
    texts = [f"{folder} chapter {i}" for i in range(chapters)]
    if shape in ("flat", "no_suffix_flat"):
        write_book_pkl(books, folder, texts, None)
    elif shape == "gen_only":
        publish_gen(books, folder, texts, FP_A, "g1")
    elif shape == "empty":
        (books / folder).mkdir()
    elif shape == "gen_dir_only":
        (books / folder / "gen").mkdir(parents=True)
    elif shape == "corrupt_flat":
        write_book_pkl(books, folder, texts, None)
        corrupt_manifest(books / folder)
    elif shape == "regular_file":
        (books / folder).write_bytes(b"not a directory")
    else:  # pragma: no cover
        raise AssertionError(shape)


@st.composite
def _libraries(draw) -> Tuple[List[Tuple[str, int]], List[str], List[int]]:
    entries = draw(st.lists(st.tuples(st.sampled_from(SHAPES), st.integers(1, 3)), max_size=6))
    names = draw(st.lists(_NAME, min_size=len(entries), max_size=len(entries), unique=True))
    order = draw(st.permutations(range(len(entries))))
    return entries, names, list(order)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@example(lib_=([("gen_only", 1), ("flat", 2)], ["c", "b"], [0, 1]))
@given(lib_=_libraries())
def test_b1_07_law_root_agrees_with_enumeration(lib_: Tuple[List[Tuple[str, int]], List[str], List[int]]) -> None:
    """B1-07 -- L2+L1/S4: ``/`` == loadable-filtered ``list_book_ids`` over generated libraries. Red-first at
    HEAD through the @example (leg c)."""
    entries, names, order = lib_
    shape_of = {_folder(names[i], entries[i][0]): entries[i][0] for i in range(len(entries))}
    chapters_of = {_folder(names[i], entries[i][0]): entries[i][1] for i in range(len(entries))}
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        for i in order:
            shape, chapters = entries[i]
            _make(books, _folder(names[i], shape), shape, chapters)
        gen_only = {f for f, s in shape_of.items() if s == "gen_only"}
        corrupt = {f for f, s in shape_of.items() if s == "corrupt_flat"}
        flat = {f for f, s in shape_of.items() if s == "flat"}
        for gid in sorted(gen_only):
            gen_only_preconditions(books, gid)
        with books_dir_patched(books) as client:
            resp = client.get("/")
            assert_locks_under(Path(tmp))
        assert resp.status_code == 200
        ids = card_ids(resp.text)
        enumerated = list_book_ids(str(books))
        assert ids == [b for b in enumerated if b not in corrupt]  # (a)
        if not corrupt:
            assert ids == enumerated  # (b)
        assert set(ids).isdisjoint(gen_only)  # (c)
        counts = section_counts(resp.text)
        for fid in sorted(flat):  # (d)
            assert card(resp.text, fid).select_one("span.lib-card-title").get_text() == fid
            assert counts[fid] == chapters_of[fid]
        assert ids == sorted(ids)  # (e)
        if flat and gen_only:  # positive mint control
            assert all((books / f / AI_META).is_file() for f in flat)
            assert not any((books / g / AI_META).exists() for g in gen_only)


EXTRA_SHAPES = ("gen_only", "empty", "gen_dir_only", "regular_file", "no_suffix_flat")


@st.composite
def _metamorphic(draw) -> Tuple[List[str], str, str]:
    names = draw(st.lists(_NAME, min_size=1, max_size=5, unique=True))
    return names[1:], names[0], draw(st.sampled_from(EXTRA_SHAPES))


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@example(case=(["a", "b"], "c", "gen_only"))
@given(case=_metamorphic())
def test_b1_08_adding_a_rejected_directory_never_changes_root(case: Tuple[List[str], str, str]) -> None:
    """B1-08 -- L2+L3/S6 metamorphic. Red-first when ``extra == gen_only``."""
    flats, extra_name, extra_shape = case
    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        for n in flats:
            write_book_pkl(books, f"{n}_data", [f"{n} text"], None)
        extra = _folder(extra_name, extra_shape)
        with books_dir_patched(books) as client:
            before = client.get("/")
            assert_locks_under(Path(tmp))
            assert before.status_code == 200
            assert all((books / f"{n}_data" / AI_META).is_file() for n in flats)  # positive mint control
            _make(books, extra, extra_shape, 2)
            if extra_shape == "gen_only":
                gen_only_preconditions(books, extra)
            clear_caches()
            after = client.get("/")
            assert_locks_under(Path(tmp))
        assert after.status_code == 200
        assert card_ids(before.text) == card_ids(after.text)
        assert not (books / extra / AI_META).exists()


# --------------------------------------------------------------------------- B1-09 / B1-09b / B1-10 / B1-11


def test_b1_09_absent_books_dir_is_an_empty_library(lib: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1-09 -- L3/S2."""
    nope = lib.project_root / "nope"
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(nope))
    clear_caches()

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == []
    assert not nope.exists()


def test_b1_09b_root_reads_server_books_dir_not_a_relative_books(lib: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1-09b -- L1+L3/S6: the cwd's relative ``books/`` (holding sample_data) is a decoy."""
    lib2 = lib.project_root / "lib2"
    write_book_pkl(lib2, "only_here_data", ["only here"], None)
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(lib2))
    monkeypatch.setattr("reader3_app.web.server.book_uuid_resolver", BookUuidResolver(str(lib2)))
    clear_caches()

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["only_here_data"]
    assert (lib2 / "only_here_data" / AI_META).is_file()
    assert not (lib.project_root / "books" / "only_here_data").exists()


def test_b1_10_unreadable_flat_pkl_is_skipped(lib: World) -> None:
    """B1-10 -- L2/S3: the wrapper's ``None`` path; dropping ``if book:`` fails this."""
    books = lib.books_dir
    (books / BOOK_ID / "book.pkl").write_bytes(b"not a pickle")
    write_book_pkl(books, "zgood_data", ["good"], None)

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["zgood_data"]


def test_b1_11_corrupt_manifest_without_flat_pkl_interim(lib: World) -> None:
    """B1-11 -- L3/S3, interim per R-B1-11 (a): 200 and absent, nothing else pinned. Successor: the 4b.5 row
    (corrupt manifest, no flat pkl -> ``/`` skips with exactly one ERROR, ``/api/library`` carries an error entry)."""
    books = lib.books_dir
    (books / BOOK_ID / "book.pkl").unlink()
    corrupt_manifest(books / BOOK_ID)
    write_book_pkl(books, "zgood_data", ["good"], None)

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["zgood_data"]
    assert BOOK_TITLE not in resp.text


# --------------------------------------------------------------------------- B1-13 structural pin


def test_b1_13_library_view_enumerates_through_list_book_ids() -> None:
    """B1-13 -- STRUCTURAL PIN (L1/S3), not a behaviour test; retired with a stated reason when G-final lands at
    4b.5. The behaviour cases cannot tell a ``list_book_ids`` call from an inline re-implementation of it, which
    would silently drift when 4b.5 changes ``list_book_ids``. Known false-red: binding ``ids = list_book_ids(...)``
    and then ``for item in ids`` -- keep the call inline as the loop's iterable."""
    tree = ast.parse(LIBRARY_PY.read_text(encoding="utf-8"))
    views = [
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "library_view"
    ]
    assert len(views) == 1, len(views)
    calls = [n for n in ast.walk(views[0]) if isinstance(n, ast.Call)]
    enum = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "list_book_ids"]
    assert len(enum) == 1, f"library_view must call list_book_ids exactly once (found {len(enum)})"  # (a)
    (call,) = enum
    assert not call.keywords and len(call.args) == 1, ast.dump(call)
    arg = call.args[0]
    assert (
        isinstance(arg, ast.Attribute)
        and arg.attr == "BOOKS_DIR"
        and isinstance(arg.value, ast.Name)
        and arg.value.id == "_server"
    ), ast.dump(arg)
    banned = {"listdir", "scandir", "iterdir", "walk", "glob"}  # (b)
    rescans = [
        ast.dump(c.func)
        for c in calls
        if (isinstance(c.func, ast.Attribute) and c.func.attr in banned)
        or (isinstance(c.func, ast.Name) and c.func.id in {"listdir", "scandir"})
    ]
    assert rescans == [], rescans
    loops = [  # (c)
        n
        for n in ast.walk(views[0])
        if isinstance(n, ast.For) and n.iter is call and isinstance(n.target, ast.Name) and n.target.id == "item"
    ]
    assert len(loops) == 1, (
        "library_view must iterate `for item in list_book_ids(_server.BOOKS_DIR):` -- the call inline as the loop's "
        "iterable, the loop variable named `item` (test_book_store_metadata_seam.py needs `load_book_cached(item)`)"
    )


# --------------------------------------------------------------------------- G-b rows: flip at 4b.5


def test_b1_20_list_book_ids_gb_flips_at_4b5(lib: World) -> None:
    """B1-20 -- L1/S3, green-first."""
    books = _gb_world(lib)
    assert list_book_ids(str(books)) == ["bflat_data", BOOK_ID]


def test_b1_21_root_gb_flips_at_4b5(lib: World) -> None:
    """B1-21 -- L2+L3/S3, red-first; positive mint control."""
    books = _gb_world(lib)
    assert not (books / "bflat_data" / AI_META).exists()

    resp = _get(lib, "/")

    assert resp.status_code == 200
    assert card_ids(resp.text) == ["bflat_data", BOOK_ID]
    assert (books / "bflat_data" / AI_META).is_file()
    assert not (books / "cgen_data" / AI_META).exists()


def test_b1_22_api_library_gb_flips_at_4b5(lib: World) -> None:
    """B1-22 -- L3/S3, green-first. The route mints (library_books.py:64 -> _book_uuid_or_none): mint leg kept."""
    books = _gb_world(lib)
    assert not (books / "bflat_data" / AI_META).exists()

    resp = _get(lib, "/api/library")

    assert resp.status_code == 200
    entries = resp.json()["books"]
    assert {e["book_id"] for e in entries} == {"bflat_data", BOOK_ID}
    assert not [e for e in entries if e.get("book_id") == "cgen_data"]
    assert (books / "bflat_data" / AI_META).is_file()
    assert not (books / "cgen_data" / AI_META).exists()


def test_b1_23_export_gb_flips_at_4b5(lib: World) -> None:
    """B1-23 -- L3/S3, green-first."""
    _gb_world(lib)

    resp = _get(lib, "/api/library/export")

    assert resp.status_code == 200
    assert {e["book_id"] for e in resp.json()["books"]} == {"bflat_data", BOOK_ID}


def test_b1_24_stats_gb_flips_at_4b5(lib: World) -> None:
    """B1-24 -- L1/S3, green-first: sections_total proves the counted books are the flat two."""
    _gb_world(lib)

    resp = _get(lib, "/api/library/stats?fresh=true")

    assert resp.status_code == 200
    body = resp.json()
    assert body["books_total"] == 2
    assert body["sections_total"] == len(build_book().spine) + 2


def test_b1_25_read_gb_flips_at_4b5(lib: World) -> None:
    """B1-25 -- L3+L1/S3, green-first, with a 200 control."""
    _gb_world(lib)

    resp = _get(lib, "/read/cgen_data/0")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Book not found"}
    assert _get(lib, "/read/bflat_data/0").status_code == 200
