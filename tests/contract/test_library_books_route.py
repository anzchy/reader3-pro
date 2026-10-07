"""`GET /api/library` — the library as JSON (018 WI-4, debt #56).

**Law.** (i) Bijection: ``[e["book_id"] for e in body["books"]]`` equals
``search_service.list_book_ids(BOOKS_DIR)`` minus the ids that vanish after
enumeration, in that order, each once. A readable id maps to exactly
``{book_id, title, authors, cover_url, book_uuid}``; an unreadable-but-present id
maps to exactly ``{book_id, error: "unreadable"}``. Only "vanished"
(``FileNotFoundError``, ``BookGone`` included) is skipped (Q-G); every other load
failure, other ``OSError``s included, is an error entry. (ii) GET is safe and
idempotent. (iii) Metadata load and uuid resolution run off the event loop.

Everything here runs through the real ``world`` fixture and the real router tree;
``server.load_book_cached`` is never stubbed. Corrupt books live only in
per-test books dirs (R8), never in a shared one.
"""

from __future__ import annotations

import collections
import json
import os
import pickle
import shutil
import tempfile
import threading
import types
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import bookdir
import pytest
from bs4 import BeautifulSoup
from hypothesis import given, settings
from hypothesis import strategies as st

from reader3_app import book_lock, book_store, search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.reader3 import Book, BookMetadata
from reader3_app.web import server

from conftest import BOOK_AUTHOR, BOOK_ID, BOOK_TITLE, World, _clear_caches

ROUTE = "/api/library"
ENTRY_KEYS = {"book_id", "title", "authors", "cover_url", "book_uuid"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _sample_entry(world: World) -> Dict[str, Any]:
    """The exact entry for the seeded book (T4-C1's expectation, reused as "intact")."""
    return {
        "book_id": BOOK_ID,
        "title": BOOK_TITLE,
        "authors": [BOOK_AUTHOR],
        "cover_url": f"/read/{BOOK_ID}/images/cover.jpg",
        "book_uuid": world.book_uuid,
    }


def _get_books(client) -> List[Dict[str, Any]]:
    response = client.get(ROUTE)
    assert response.status_code == 200, (
        f"GET {ROUTE} -> {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    assert isinstance(body, dict) and set(body) == {"books"}, body
    assert isinstance(body["books"], list), body
    return body["books"]


def _write_book(
    books_dir: Path,
    name: str,
    *,
    title: str = "Fresh",
    authors: Optional[List[str]] = None,
    with_metadata: bool = True,
) -> Path:
    out = books_dir / name
    out.mkdir(parents=True, exist_ok=True)
    book = Book(
        metadata=(
            BookMetadata(title=title, language="en", authors=list(authors or []))
            if with_metadata
            else None  # type: ignore[arg-type]
        ),
        spine=[],
        toc=[],
        images={},
        source_file=f"{name}.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )
    with open(out / "book.pkl", "wb") as f:
        pickle.dump(book, f)
    return out


def _corrupt(books_dir: Path, name: str, kind: str) -> Path:
    out = books_dir / name
    out.mkdir(parents=True, exist_ok=True)
    if kind == "garbage":
        bookdir.break_book_pkl(out)
    elif kind == "empty":
        (out / "book.pkl").write_bytes(b"")
    elif kind == "truncated":
        _write_book(books_dir, name, title="Truncated", authors=["T"])
        bookdir.truncate_book_pkl(out, keep=32)
    elif kind == "disallowed_class":
        (out / "book.pkl").write_bytes(pickle.dumps(collections.OrderedDict()))
    elif kind == "directory":
        (out / "book.pkl").mkdir()
    else:  # pragma: no cover - test bug
        raise AssertionError(kind)
    return out


def _snapshot(root: Path) -> Dict[str, Optional[bytes]]:
    """Every path under ``root``: file -> bytes, directory -> None."""
    snap: Dict[str, Optional[bytes]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            snap[os.path.relpath(os.path.join(dirpath, d), root)] = None
        for f in filenames:
            p = os.path.join(dirpath, f)
            with open(p, "rb") as fh:
                snap[os.path.relpath(p, root)] = fh.read()
    return snap


class _Rehomed:
    """A fresh books dir per hypothesis example, swapped in for the world's one."""

    def __init__(self) -> None:
        self.path = Path(tempfile.mkdtemp(prefix="api-library-"))
        self._mp = pytest.MonkeyPatch()

    def __enter__(self) -> Path:
        self._mp.setattr(server, "BOOKS_DIR", str(self.path))
        self._mp.setattr(server, "book_uuid_resolver", BookUuidResolver(str(self.path)))
        _clear_caches()
        return self.path

    def __exit__(self, *exc: object) -> None:
        self._mp.undo()
        _clear_caches()
        shutil.rmtree(self.path, ignore_errors=True)


# --------------------------------------------------------------------------
# T4-C1
# --------------------------------------------------------------------------


def test_readable_book_entry_shape_and_values(world: World) -> None:
    """T4-C1 — L3+L1/S1: exact payload, which pins key set and JSON types."""
    response = world.client.get(ROUTE)
    assert response.status_code == 200, f"GET {ROUTE} -> {response.status_code}"
    assert response.json() == {"books": [_sample_entry(world)]}


# --------------------------------------------------------------------------
# T4-C2
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["garbage", "empty", "truncated", "disallowed_class", "directory"])
def test_corrupt_pkl_yields_error_entry(world: World, kind: str) -> None:
    """T4-C2 — L3+L1+L2/S3: each corruption the loader can meet is an error entry."""
    _corrupt(world.books_dir, "broken_data", kind)
    assert "broken_data" in search_service.list_book_ids(str(world.books_dir)), (
        "fixture precondition: list_book_ids must enumerate broken_data, so a missing "
        "entry can only be the router's skip"
    )

    books = _get_books(world.client)

    assert books == [{"book_id": "broken_data", "error": "unreadable"}, _sample_entry(world)]
    assert not (world.books_dir / "broken_data" / "ai_meta.json").exists(), (
        "a uuid was resolved (and minted) for an unreadable book"
    )


# --------------------------------------------------------------------------
# T4-C3
# --------------------------------------------------------------------------

_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=30)
_BASE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6)
_KIND = st.sampled_from(
    [
        "healthy",
        "no_metadata",
        "corrupt",
        "data_dir_no_pkl",
        "data_named_regular_file",
        "non_data_dir_with_pkl",
        "tombstone",
    ]
)
_LISTED_KINDS = {"healthy", "no_metadata", "corrupt"}


def test_listed_ids_equal_enumeration_exactly_once(world: World) -> None:
    """T4-C3 — L3+L1/S4: conservation of the enumerated set over generated layouts."""
    _get_books(world.client)  # the route exists at all; fail fast and by name if not

    @settings(max_examples=25, deadline=None)
    @given(
        entries=st.lists(
            st.tuples(_BASE, _KIND, _TEXT, st.lists(_TEXT, max_size=3)),
            max_size=6,
            unique_by=lambda t: t[0],
        ),
        with_locks=st.booleans(),
    )
    def check(entries, with_locks):
        with _Rehomed() as d:
            spec: Dict[str, tuple] = {}
            for base, kind, title, authors in entries:
                name = f"{base}_data"
                if kind == "healthy":
                    _write_book(d, name, title=title, authors=authors)
                    spec[name] = (kind, title, authors)
                elif kind == "no_metadata":
                    _write_book(d, name, with_metadata=False)
                    spec[name] = (kind, None, None)
                elif kind == "corrupt":
                    _corrupt(d, name, "garbage")
                    spec[name] = (kind, None, None)
                elif kind == "data_dir_no_pkl":
                    (d / name).mkdir()
                elif kind == "data_named_regular_file":
                    (d / name).write_bytes(b"not a dir")
                elif kind == "non_data_dir_with_pkl":
                    _write_book(d, f"{base}_books")
                elif kind == "tombstone":
                    _write_book(d, f".{base}_data.deleted-123-abcdef12")
            if with_locks:
                (d / ".locks").mkdir(exist_ok=True)
                (d / ".locks" / "x.lock").write_bytes(b"")

            books = _get_books(world.client)
            ids = [e["book_id"] for e in books]

            assert ids == search_service.list_book_ids(str(d))
            assert set(ids) == set(spec)
            for e in books:
                kind, title, authors = spec[e["book_id"]]
                if kind == "corrupt":
                    assert e == {"book_id": e["book_id"], "error": "unreadable"}
                    continue
                assert set(e) == ENTRY_KEYS, e
                uuid.UUID(e["book_uuid"])
                if kind == "healthy":
                    assert e["title"] == title
                    assert e["authors"] == authors
                else:
                    assert e["title"] == e["book_id"]
                    assert e["authors"] == []

    check()


# --------------------------------------------------------------------------
# T4-C4
# --------------------------------------------------------------------------


def test_excluded_directories_are_not_listed(world: World) -> None:
    """T4-C4 — L3+L1/S2: one fixture per excluded class, each maximally tempting."""
    d = world.books_dir
    (d / ".locks").mkdir(exist_ok=True)
    (d / ".locks" / "held.lock").write_bytes(b"")
    tomb = d / ".sample_data.deleted-123-abcdef12"
    tomb.mkdir()
    shutil.copyfile(world.book_dir / "book.pkl", tomb / "book.pkl")
    (d / "nopkl_data").mkdir()
    (d / "stray_data").write_bytes(b"a regular file")
    (d / "notabook").mkdir()
    shutil.copyfile(world.book_dir / "book.pkl", d / "notabook" / "book.pkl")

    books = _get_books(world.client)

    assert [e["book_id"] for e in books] == [BOOK_ID]


# --------------------------------------------------------------------------
# T4-C5
# --------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["rmtree", "bookgone"])
def test_book_vanishing_after_enumeration_is_skipped(
    world: World, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """T4-C5 — L3+L1/S3 (Q-G): vanished after enumeration -> absent, not an error entry."""
    _write_book(world.books_dir, "ghost_data", title="Ghost", authors=["G"])
    real = book_store.load_book_metadata

    def wrapper(book_id: str, books_dir: str):
        if book_id == "ghost_data":
            if how == "rmtree":
                shutil.rmtree(os.path.join(books_dir, book_id))
            else:
                raise book_lock.BookGone(book_id)
        return real(book_id, books_dir)

    monkeypatch.setattr(book_store, "load_book_metadata", wrapper)

    books = _get_books(world.client)

    assert books == [_sample_entry(world)]


# --------------------------------------------------------------------------
# T4-C6
# --------------------------------------------------------------------------


def test_unreadable_ai_meta_gives_null_uuid_without_rewrite(world: World) -> None:
    """T4-C6 — L3+L1+L2/S3 (ADR-0003): unreadable ai_meta -> null, file untouched."""
    out = _write_book(world.books_dir, "metabad_data", title="Meta Bad", authors=["M", "N"])
    meta = out / "ai_meta.json"
    meta.write_bytes(b"{not json")

    books = _get_books(world.client)

    assert books == [
        {
            "book_id": "metabad_data",
            "title": "Meta Bad",
            "authors": ["M", "N"],
            "cover_url": None,
            "book_uuid": None,
        },
        _sample_entry(world),
    ]
    assert meta.read_bytes() == b"{not json"


# --------------------------------------------------------------------------
# T4-C13
# --------------------------------------------------------------------------


def test_uuid_for_a_book_without_ai_meta_is_persisted_and_stable(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T4-C13 — L3+L4+L1/S5: the reported uuid is the persisted one, at every step."""
    _write_book(world.books_dir, "fresh_data", title="Fresh", authors=["F"])
    meta = world.books_dir / "fresh_data" / "ai_meta.json"
    assert not meta.exists()

    def fresh_uuid() -> Any:
        by_id = {e["book_id"]: e for e in _get_books(world.client)}
        assert by_id[BOOK_ID]["book_uuid"] == world.book_uuid
        return by_id["fresh_data"]["book_uuid"]

    u1 = fresh_uuid()
    assert meta.is_file(), "the first GET did not persist the uuid it reported"
    uuid.UUID(u1)
    stat1, bytes1 = meta.stat().st_mtime_ns, meta.read_bytes()

    u2 = fresh_uuid()
    assert (meta.stat().st_mtime_ns, meta.read_bytes()) == (stat1, bytes1)

    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(world.books_dir)))
    u3 = fresh_uuid()
    assert (meta.stat().st_mtime_ns, meta.read_bytes()) == (stat1, bytes1)

    persisted = json.loads(bytes1.decode("utf-8"))["book_uuid"]
    assert u1 == u2 == u3 == persisted


# --------------------------------------------------------------------------
# T4-C10
# --------------------------------------------------------------------------


def test_empty_library_is_an_empty_list(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T4-C10 — L3+L1+L2/S2: empty dir and absent dir both give an empty list."""
    empty = tmp_path / "empty_books"
    empty.mkdir()
    monkeypatch.setattr(server, "BOOKS_DIR", str(empty))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(empty)))
    response = world.client.get(ROUTE)
    assert response.status_code == 200, f"GET {ROUTE} -> {response.status_code}"
    assert response.json() == {"books": []}

    absent = tmp_path / "does-not-exist"
    monkeypatch.setattr(server, "BOOKS_DIR", str(absent))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(absent)))
    response = world.client.get(ROUTE)
    assert response.status_code == 200, f"GET {ROUTE} -> {response.status_code}"
    assert response.json() == {"books": []}
    assert not absent.exists()


# --------------------------------------------------------------------------
# T4-C12
# --------------------------------------------------------------------------


def test_listing_is_read_only_and_idempotent(world: World) -> None:
    """T4-C12 — L3+L2/S5: two calls, equal payloads, byte-identical tree."""
    _corrupt(world.books_dir, "broken_data", "garbage")
    out = _write_book(world.books_dir, "metabad_data", title="Meta Bad", authors=["M"])
    (out / "ai_meta.json").write_bytes(b"{not json")

    before = _snapshot(world.books_dir)
    first = _get_books(world.client)
    after_first = _snapshot(world.books_dir)
    second = _get_books(world.client)
    after_second = _snapshot(world.books_dir)

    assert first == second
    assert after_first == before, sorted(set(after_first) ^ set(before))
    assert after_second == before, sorted(set(after_second) ^ set(before))


# --------------------------------------------------------------------------
# T4-C8
# --------------------------------------------------------------------------


def _blocking(real: Callable[..., Any], entered: threading.Event, release: threading.Event):
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        release.wait(10)
        return real(*args, **kwargs)

    return wrapper


@pytest.mark.parametrize("point", ["metadata", "uuid"])
def test_health_responsive_while_library_lists(
    world: World, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    """T4-C8 — L3+L1/S3: /api/health answers while /api/library is blocked mid-listing.

    ``world.client`` is entered as a context manager, so both requests share one
    event loop; a per-request ``TestClient`` would give each its own loop and make
    this a false green.
    """
    entered = threading.Event()
    release = threading.Event()
    if point == "metadata":
        monkeypatch.setattr(
            book_store, "load_book_metadata", _blocking(book_store.load_book_metadata, entered, release)
        )
    else:
        # Both `_book_uuid_or_none` and `_book_uuids_or_none` resolve through
        # `server.book_uuid_resolver` at call time, so blocking that one registered
        # seam covers either helper without pinning which the router calls (and keeps
        # this file inside the patch-seam registry, test_server_patch_seam_ownership).
        real_resolver = server.book_uuid_resolver
        blocking_resolver = types.SimpleNamespace(
            book_uuid_for_folder=_blocking(real_resolver.book_uuid_for_folder, entered, release)
        )
        monkeypatch.setattr(server, "book_uuid_resolver", blocking_resolver)

    results: Dict[str, Any] = {}

    def list_library() -> None:
        results["library"] = world.client.get(ROUTE)

    def health() -> None:
        results["health"] = world.client.get("/api/health")

    a = threading.Thread(target=list_library, daemon=True)
    b = threading.Thread(target=health, daemon=True)
    try:
        a.start()
        assert entered.wait(5), (
            f"the {point} blocking point was never reached by GET {ROUTE}"
        )
        b.start()
        b.join(timeout=3)
        assert not b.is_alive(), "/api/health did not answer while /api/library was blocked"
        assert a.is_alive(), "/api/library finished before release: the block did not hold"
        assert results["health"].status_code == 200
    finally:
        release.set()
        for t in (a, b):
            if t.ident is not None:  # never started when an earlier assert fired
                t.join(timeout=10)

    assert not a.is_alive()
    response = results["library"]
    assert response.status_code == 200, f"GET {ROUTE} -> {response.status_code}"
    assert response.json() == {"books": [_sample_entry(world)]}


# --------------------------------------------------------------------------
# T4-C7
# --------------------------------------------------------------------------

_IMAGE_NAME = st.one_of(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
        min_size=1,
        max_size=14,
    ),
    st.sampled_from(["cover.jpg", "Cover.png", "title.gif", ".cover.jpg", "TITLEPAGE.jpeg"]),
).filter(lambda n: n not in (".", ".."))

_IMAGE_SET = st.lists(
    st.tuples(_IMAGE_NAME, st.sampled_from(["file", "dir"])),
    max_size=6,
    unique_by=lambda t: t[0].lower(),
)


def _page_covers(html: str) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    covers: Dict[str, Optional[str]] = {}
    for card in soup.select('article[data-testid="lib-book-card"]'):
        img = card.select_one("img.lib-cover")
        covers[str(card.get("data-book-id"))] = str(img.get("src")) if img is not None else None
    return covers


def test_cover_url_matches_library_page(world: World) -> None:
    """T4-C7 — L3+L1/S6: GET / and GET /api/library agree on every book's cover."""
    _get_books(world.client)  # the route exists at all; fail fast and by name if not

    @settings(max_examples=15, deadline=None)
    @given(books=st.lists(_IMAGE_SET, min_size=1, max_size=3))
    def check(books):
        with _Rehomed() as d:
            for i, image_set in enumerate(books):
                name = f"cov{i}_data"
                out = _write_book(d, name, title=f"Cover {i}", authors=["C"])
                if image_set:
                    images = out / "images"
                    images.mkdir()
                    for img, kind in image_set:
                        if kind == "file":
                            (images / img).write_bytes(b"x")
                        else:
                            (images / img).mkdir()

            api = {e["book_id"]: e["cover_url"] for e in _get_books(world.client)}
            page = world.client.get("/")
            assert page.status_code == 200
            rendered = _page_covers(page.text)

            assert set(api) == {f"cov{i}_data" for i in range(len(books))}
            for book_id, cover_url in api.items():
                assert book_id in rendered, (book_id, sorted(rendered))
                assert rendered[book_id] == cover_url, (book_id, rendered[book_id], cover_url)

    check()




# --------------------------------------------------------------------------
# FX37-7 (audit #7): cover_url percent-encodes both path segments
# --------------------------------------------------------------------------


def _cover_world(world: World) -> Dict[str, bytes]:
    """``A#B_data`` (a full copy of the sample book: cover.jpg) and ``img_data`` whose only
    image is ``c#1 封面.jpg``. Returns the expected cover URL -> image bytes."""
    hashed = world.books_dir / "A#B_data"
    shutil.copytree(world.book_dir, hashed)
    odd = _write_book(world.books_dir, "img_data", title="Odd", authors=["O"])
    (odd / "images").mkdir()
    (odd / "images" / "c#1 封面.jpg").write_bytes(b"odd-cover-bytes")
    _clear_caches()
    return {
        "/read/A%23B_data/images/cover.jpg": (hashed / "images" / "cover.jpg").read_bytes(),
        "/read/img_data/images/c%231%20%E5%B0%81%E9%9D%A2.jpg": b"odd-cover-bytes",
    }


def test_fx37_7_cover_url_is_percent_encoded_and_fetchable(world: World) -> None:
    """FX37-7 (#7): a ``#`` / space / non-ASCII in the folder or image name is percent-encoded,
    the URL fetches the image (200, same bytes), and plain names are unchanged."""
    expected = _cover_world(world)
    api = {e["book_id"]: e["cover_url"] for e in _get_books(world.client)}
    assert api["A#B_data"] == "/read/A%23B_data/images/cover.jpg"
    assert api["img_data"] == "/read/img_data/images/c%231%20%E5%B0%81%E9%9D%A2.jpg"
    assert api[BOOK_ID] == f"/read/{BOOK_ID}/images/cover.jpg"
    for url, body in expected.items():
        response = world.client.get(url)
        assert response.status_code == 200, (url, response.status_code)
        assert response.content == body


def test_fx37_7_library_page_and_reader_page_emit_the_same_encoded_url(world: World) -> None:
    """FX37-7 (#7, Q-C parity): GET / renders exactly the API's URL; the reader page for the
    ``#`` book carries the same URL."""
    _cover_world(world)
    api = {e["book_id"]: e["cover_url"] for e in _get_books(world.client)}
    page = world.client.get("/")
    assert page.status_code == 200
    rendered = _page_covers(page.text)
    for book_id in ("A#B_data", "img_data", BOOK_ID):
        assert rendered[book_id] == api[book_id], book_id

    reader = world.client.get("/read/A%23B_data/0")
    assert reader.status_code == 200, reader.text[:300]
    assert 'src="/read/A%23B_data/images/cover.jpg"' in reader.text
    assert "/read/A#B_data/images/" not in reader.text
