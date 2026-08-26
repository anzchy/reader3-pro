"""The 20-book library must actually defeat the caches it is built to defeat.

§6 measures homepage TTFB against library size. That measurement is only real
if the library is bigger than the caches on the read path -- otherwise the
second run reports the cost of ten dictionary lookups and everyone concludes
the scan is free.

The bounds are read from the live ``cache_parameters()`` of the production
functions, never copied into this file. Raising ``maxsize`` to 20 in a future
refactor would silently invalidate the benchmark; here it turns the lane red.

``web.server.load_book_cached`` is only *inspected*, never called: it closes
over the module-level ``BOOKS_DIR``, which is the user's real library.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

import synthetic_library as sl
from reader3_app import search_service
from reader3_app.web import server as web_server


@pytest.fixture
def library(books_dir: Path):
    return books_dir, sl.make_synthetic_library(books_dir)


def test_library_publishes_exactly_twenty_loadable_books(library):
    """L3 - the whole directory tree, not just the return value's length.

    ``make_synthetic_library`` asserts its own count, so this checks the thing
    that assertion cannot: that each directory is what a loader would accept.
    """
    books_dir, created = library

    on_disk = sorted(p.name for p in books_dir.iterdir() if p.is_dir())
    assert len(on_disk) == sl.DEFAULT_BOOK_COUNT == 20
    assert on_disk == sorted(p.name for p in created)
    assert all(name.endswith("_data") for name in on_disk)

    for path in created:
        assert (path / "book.pkl").is_file()
        assert (path / "images" / "cover.png").is_file()
        with open(path / "book.pkl", "rb") as f:
            book = pickle.load(f)
        assert len(book.spine) == 8
        assert len(book.toc) == 8


def test_the_library_is_larger_than_every_cache_on_the_read_path():
    """L2 - asserted against the live bounds, so a maxsize bump breaks here.

    Two caches sit between the homepage and the disk. The library has to exceed
    both, or the benchmark measures cache hits instead of scan cost.
    """
    homepage_bound = web_server.load_book_cached.cache_parameters()["maxsize"]
    loader_bound = search_service.load_book_cached.cache_parameters()["maxsize"]
    index_bound = search_service.load_book_index.cache_parameters()["maxsize"]

    assert (homepage_bound, loader_bound, index_bound) == (10, 10, 4)
    assert sl.DEFAULT_BOOK_COUNT > homepage_bound
    assert sl.DEFAULT_BOOK_COUNT > loader_bound
    assert sl.DEFAULT_BOOK_COUNT > index_bound


def test_one_pass_over_the_library_evicts_books_it_already_loaded(library):
    """L3 - eviction demonstrated, not inferred from the maxsize number.

    Walking the library once costs 20 misses. Re-reading the *first* book
    immediately afterwards costs a 21st, because a 10-entry LRU dropped it
    ten books ago. That is the cost the homepage pays on every request.
    """
    books_dir, created = library
    names = [p.name for p in created]

    search_service.load_book_cached.cache_clear()
    try:
        for name in names:
            search_service.load_book_cached(name, str(books_dir))

        first_pass = search_service.load_book_cached.cache_info()
        assert first_pass.misses == sl.DEFAULT_BOOK_COUNT
        assert first_pass.hits == 0
        assert first_pass.currsize == first_pass.maxsize == 10

        search_service.load_book_cached(names[0], str(books_dir))
        after = search_service.load_book_cached.cache_info()
        assert after.misses == sl.DEFAULT_BOOK_COUNT + 1
        assert after.hits == 0  # the re-read was not a hit: it had been evicted

        # A book still inside the window does hit, so the miss above is
        # eviction and not a cache that never worked at all.
        search_service.load_book_cached(names[-1], str(books_dir))
        assert search_service.load_book_cached.cache_info().hits == 1
    finally:
        search_service.load_book_cached.cache_clear()


def test_the_search_index_cache_thrashes_four_times_faster(library):
    """L3 - the tighter bound is the one that decides cross-book search cost."""
    books_dir, created = library
    names = [p.name for p in created[:6]]

    search_service.load_book_index.cache_clear()
    search_service.load_book_cached.cache_clear()
    try:
        for name in names:
            search_service.load_book_index(name, str(books_dir), case_sensitive=False)

        info = search_service.load_book_index.cache_info()
        assert info.misses == 6
        assert info.currsize == info.maxsize == 4

        # names[0] and names[1] have already been pushed out by names[4:6].
        search_service.load_book_index(names[0], str(books_dir), case_sensitive=False)
        assert search_service.load_book_index.cache_info().misses == 7
    finally:
        search_service.load_book_index.cache_clear()
        search_service.load_book_cached.cache_clear()


def test_case_sensitivity_doubles_the_index_cache_pressure(library):
    """L2 - two entries per book, so four books already overflow a 4-slot cache."""
    books_dir, created = library
    name = created[0].name

    search_service.load_book_index.cache_clear()
    try:
        search_service.load_book_index(name, str(books_dir), case_sensitive=False)
        search_service.load_book_index(name, str(books_dir), case_sensitive=True)

        info = search_service.load_book_index.cache_info()
        assert info.misses == 2
        assert info.currsize == 2
    finally:
        search_service.load_book_index.cache_clear()


def test_every_marker_identifies_exactly_one_chapter_of_one_book(library):
    """L3 - a benchmark that reads the wrong book must be detectable.

    If two books shared text, "did this query touch book 17" would be
    unanswerable and a cache-hit could masquerade as a scan.
    """
    books_dir, created = library

    seen = {}
    for path in created:
        with open(path / "book.pkl", "rb") as f:
            book = pickle.load(f)
        for chapter in book.spine:
            marker = chapter.text.split(" ", 1)[0]
            assert marker not in seen, f"{marker} appears in {seen.get(marker)} and {path.name}"
            seen[marker] = path.name

    assert len(seen) == sl.DEFAULT_BOOK_COUNT * 8
    assert sl.chapter_marker(17, 3) in seen
    assert seen[sl.chapter_marker(17, 3)] == "synth17_data"

    # And a book marker is a prefix shared by that book's chapters only.
    owners = {name for marker, name in seen.items() if marker.startswith(sl.book_marker(4))}
    assert owners == {"synth04_data"}


def test_a_smaller_library_can_be_requested_but_still_asserts_its_own_size(books_dir: Path):
    """L4 - the fixture's post-condition is load-bearing, so provoke it.

    A seeding helper that silently produced fewer directories than asked would
    turn every "20 books" claim downstream into an unfalsifiable one.
    """
    created = sl.make_synthetic_library(books_dir, count=3, chapters=2, chapter_chars=100)
    assert len(created) == 3

    (created[1] / "book.pkl").unlink()
    with pytest.raises(AssertionError, match="should hold 3 published books, found"):
        sl.make_synthetic_library(books_dir, count=3, chapters=2, chapter_chars=100, prefix="other")
