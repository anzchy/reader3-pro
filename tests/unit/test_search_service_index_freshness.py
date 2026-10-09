"""WI-8 (C1, narrowed): `search_service.load_book_index` — invalidation and capacity.

Two holes, one work item, both on the one decorator at `search_service.py`:

1. **Staleness.** The index cache was keyed on `(book_id, books_dir,
   case_sensitive)` and nothing else. After WI-3 put `(st_mtime_ns, st_size)`
   into `book_store.load_book_cached`'s key, a republished `book.pkl` reached
   the reader fresh and reached *search* stale: the loader returned the new
   `Book` while a warm `load_book_index` entry kept serving normalised text
   built from the old one. `test_search_service_loader_delegation.py`'s W2-C4
   recorded exactly that divergence and is rewritten to its opposite by this
   work item.
2. **Capacity.** `maxsize=4` with `case_sensitive` in the key is an effective
   capacity of *two books*. The new bound is stated as a rule — the working set
   of ordinary reading, six books in hand, times the two case flags each of
   them can be held under — and the rule, not the number, is what a future
   change has to argue with.

**What this file deliberately does not claim.** A bigger bound does not fix a
sequential pass over a library larger than the cache; at any bound below the
library size the hit rate for that access pattern is zero, and it was measured
at zero for 2/4/10/19 over a 20-book library. That cliff belongs to C5/012. The
eviction case below therefore demonstrates eviction *as the designed
behaviour*, not as a defect this work item was supposed to remove.

**Why the outer stat is advisory rather than authoritative.** `load_book_index`
reads the stat for key material and falls back to a sentinel key when the stat
raises, instead of letting the `OSError` out of the outer function. Two reasons,
both asserted below rather than left in prose: the authority on "is there a
readable book here" stays in `book_store.load_book_cached`, so there is exactly
one place that can produce a `FileNotFoundError` and exactly one message to keep
stable (C3); and `search_service.load_book_cached` is a listed patch seam
(`test_server_patch_seam_ownership.py`'s `GLOBAL_RESOLVERS`), so a test that
substitutes the loader must still be isolated from the disk — an authoritative
outer stat would add a second, unlisted disk dependency underneath the seam
(C7).

No case here asserts wall-clock time, and no mtime here comes from the clock:
every republish forces an explicit `mtime_ns` through `rewrite_book_pkl`, which
itself fails loudly if the filesystem truncates nanoseconds.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reader3_app import search_service
from synthetic_library import chapter_marker, make_book, make_synthetic_library

#: An explicit constant, never the clock. Two writes inside one filesystem tick
#: with the same byte count are invisible to a `(mtime_ns, size)` key, so no
#: invalidation claim in this file may ride on wall time.
BASE_NS = 1_700_000_000_000_000_000


@pytest.fixture
def clean_index_cache():
    """Empty the index cache before and after, so counters here are this file's.

    The loader cache underneath is cleared too: a warm `Book` left behind would
    not change any assertion in this file, but it would change the unpickle
    counts `test_fixture_synthetic_library.py` measures exactly. That clear goes
    through `book_store` rather than `search_service`, because C7 substitutes
    `search_service.load_book_cached` and `monkeypatch` does not undo it until
    after this fixture's teardown has run — the two names are one object, so
    either spelling clears the one cache when nothing is patched.
    """
    from reader3_app import book_store

    search_service.load_book_index.cache_clear()
    book_store.load_book_cached.cache_clear()
    yield
    search_service.load_book_index.cache_clear()
    book_store.load_book_cached.cache_clear()


def one_book(books_dir: Path):
    """A one-book synthetic library. Small chapters: this lane is budgeted in seconds."""
    return make_synthetic_library(books_dir, count=1, chapters=2, chapter_chars=200)


# ==========================================================================
# C1 — an unchanged file still hits
# ==========================================================================


def test_an_unchanged_pickle_returns_the_identical_index_object(
    books_dir: Path, clean_index_cache
):
    """L2 - freshness must not be bought by rebuilding on every call.

    This case exists to refuse the cheapest way to pass C2/C6: a
    `load_book_index` that re-normalises the whole book every time is trivially
    never stale, and would satisfy every invalidation assertion in this file
    while making cross-book search cost what it cost before any cache existed.
    Identity, not equality — an index rebuilt from identical bytes compares
    equal field by field, so equality would not see the rebuild.
    """
    one_book(books_dir)
    directory = str(books_dir)

    first = search_service.load_book_index("synth00_data", directory, case_sensitive=False)
    before = search_service.load_book_index.cache_info()
    again = search_service.load_book_index("synth00_data", directory, case_sensitive=False)
    after = search_service.load_book_index.cache_info()

    assert again is first, (
        "an unchanged book.pkl must be served from the cache; a rebuild here "
        "means the stat is in the key but the cache no longer caches"
    )
    assert after.hits == before.hits + 1
    assert after.misses == before.misses
    assert after.currsize == before.currsize == 1


# ==========================================================================
# C2 — same mtime, different size: still invalid
# ==========================================================================


def test_a_size_change_at_an_identical_mtime_still_invalidates(
    books_dir: Path, clean_index_cache, rewrite_book_pkl
):
    """L3 - why the key carries `st_size` and not `st_mtime_ns` alone.

    A republish that lands inside one filesystem tick is exactly the case a
    mtime-only key cannot see, and it is not hypothetical: a scripted
    reprocess writes the same book twice in well under a tick. `book_store`
    carries both fields for this reason and this cache must carry both for the
    same one. The two writes below are forced to the *identical* nanosecond, so
    the only thing that can distinguish them is the byte count — which the test
    asserts really did change before it asserts anything about the index.
    """
    directories = one_book(books_dir)
    directory = str(books_dir)
    book_id = "synth00_data"
    old_marker = chapter_marker(0, 0)
    new_marker = "WI8SAMETICKMARKER"
    frozen_ns = BASE_NS + 3_000_000_000

    short = make_book(0, chapters=2, chapter_chars=200)
    short.spine[0].text = f"{old_marker} a short chapter."
    _mtime, short_size = rewrite_book_pkl(directories[0], short, mtime_ns=frozen_ns)

    warm = search_service.load_book_index(book_id, directory, case_sensitive=False)
    assert old_marker.casefold() in warm.chapters[0].normalized_text

    longer = make_book(0, chapters=2, chapter_chars=200)
    longer.spine[0].text = f"{new_marker} a rather longer chapter. " + ("tide " * 200)
    same_mtime, long_size = rewrite_book_pkl(directories[0], longer, mtime_ns=frozen_ns)

    # Preconditions, asserted so a vacuous pass is impossible: the clock did not
    # move and the size did.
    assert same_mtime == frozen_ns
    assert long_size != short_size

    fresh = search_service.load_book_index(book_id, directory, case_sensitive=False)

    assert fresh is not warm
    assert new_marker.casefold() in fresh.chapters[0].normalized_text
    assert old_marker.casefold() not in fresh.chapters[0].normalized_text, (
        "the index survived a same-tick republish, so st_size is not in its key"
    )


# ==========================================================================
# C3 — an absent book raises exactly what it raised before
# ==========================================================================


def test_an_absent_book_raises_the_loaders_own_error_unchanged(
    books_dir: Path, clean_index_cache
):
    """L3 - the error a caller sees must not move when the stat moves.

    Before this work item the `FileNotFoundError` came out of the `os.stat`
    inside `load_book_cached`. Adding a stat to `load_book_index` creates a
    second place that could raise, with a second message; the expected value
    here is therefore *derived from the loader at run time*, not copied into
    this file, so the two can never drift apart silently. `web/server.py` turns
    this exception into a 404 by type, and `errno`/`filename` are what a log
    line carries.
    """
    directory = str(books_dir)
    missing = "there_is_no_such_book_data"

    with pytest.raises(OSError) as loader_error:
        search_service.load_book_cached(missing, directory)

    with pytest.raises(OSError) as index_error:
        search_service.load_book_index(missing, directory, case_sensitive=False)

    assert type(index_error.value) is type(loader_error.value) is FileNotFoundError
    assert index_error.value.errno == loader_error.value.errno
    assert index_error.value.filename == loader_error.value.filename
    assert str(index_error.value) == str(loader_error.value)
    assert index_error.value.filename == os.path.join(directory, missing, "book.pkl")

    # A raise must not leave a poisoned entry behind: `lru_cache` does not
    # memoize exceptions, and nothing above this line may start doing so.
    assert search_service.load_book_index.cache_info().currsize == 0


# ==========================================================================
# C4 — eviction past the new bound, demonstrated
# ==========================================================================


def test_the_index_cache_evicts_once_the_working_set_is_exceeded(
    books_dir: Path, clean_index_cache
):
    """L3 - eviction shown by re-reading an evicted book, not inferred from maxsize.

    The bound is read live rather than written down here; the number itself is
    pinned once, in `test_fixture_synthetic_library.py`. Two books past the
    bound is enough to push the first one out, and the *last* book is re-read
    afterwards to prove the cache works at all — without that, a cache that
    never hit anything would pass the eviction half.
    """
    bound = search_service.load_book_index.cache_parameters()["maxsize"]
    count = bound + 2
    assert count <= 20, "keep the fixture inside the synthetic library's range"

    created = make_synthetic_library(books_dir, count=count, chapters=1, chapter_chars=120)
    names = [p.name for p in created]
    directory = str(books_dir)

    for name in names:
        search_service.load_book_index(name, directory, case_sensitive=False)

    first_pass = search_service.load_book_index.cache_info()
    assert first_pass.misses == count
    assert first_pass.hits == 0
    assert first_pass.currsize == first_pass.maxsize == bound

    search_service.load_book_index(names[0], directory, case_sensitive=False)
    after = search_service.load_book_index.cache_info()
    assert after.misses == count + 1
    assert after.hits == 0, "the re-read was not a hit: it had been evicted"

    search_service.load_book_index(names[-1], directory, case_sensitive=False)
    assert search_service.load_book_index.cache_info().hits == 1


# ==========================================================================
# C5 — the cache surface is forwarded to the public name
# ==========================================================================


def test_the_cache_surface_is_reachable_on_the_public_name(
    books_dir: Path, clean_index_cache
):
    """L2 - the three attributes are exercised for their effect, not their existence.

    Eleven call sites across the suite hold `load_book_index.cache_clear()`,
    `.cache_info()` and `.cache_parameters()`. Splitting the function into an
    outer stat and an inner memo moves the real cache off the public name, so
    the forwarding is not cosmetic: a `cache_clear` that clears nothing leaves
    every neighbouring test counting another test's entries. Asserted by
    observing a cleared cache actually miss again.
    """
    one_book(books_dir)
    directory = str(books_dir)

    parameters = search_service.load_book_index.cache_parameters()
    assert parameters["maxsize"] == 12
    assert parameters["typed"] is False

    search_service.load_book_index("synth00_data", directory, case_sensitive=False)
    warm = search_service.load_book_index.cache_info()
    assert (warm.currsize, warm.misses) == (1, 1)

    search_service.load_book_index.cache_clear()
    cleared = search_service.load_book_index.cache_info()
    assert (cleared.currsize, cleared.hits, cleared.misses) == (0, 0, 0)

    search_service.load_book_index("synth00_data", directory, case_sensitive=False)
    assert search_service.load_book_index.cache_info().misses == 1


# ==========================================================================
# C6 — a republish invalidates every case flag, not just the one that was read
# ==========================================================================


def test_a_republish_invalidates_both_case_sensitivity_entries(
    books_dir: Path, clean_index_cache, rewrite_book_pkl
):
    """L3 - the stat belongs to the key, so it applies to every entry for the book.

    One book occupies two slots, and a user who toggles the case switch after a
    reprocess must not be shown the pre-reprocess text through the slot they did
    not happen to warm last. An implementation that stored the stat beside the
    entry and compared it only on the path it was read through would pass the
    single-flag case and fail here.
    """
    directories = one_book(books_dir)
    directory = str(books_dir)
    book_id = "synth00_data"
    old_marker = chapter_marker(0, 0)
    new_marker = "WI8BothFlagsMarker"

    warm_insensitive = search_service.load_book_index(book_id, directory, case_sensitive=False)
    warm_sensitive = search_service.load_book_index(book_id, directory, case_sensitive=True)
    assert old_marker.casefold() in warm_insensitive.chapters[0].normalized_text
    assert old_marker in warm_sensitive.chapters[0].normalized_text

    replacement = make_book(0, chapters=2, chapter_chars=200)
    replacement.spine[0].text = f"{new_marker} the tide came back in."
    rewrite_book_pkl(directories[0], replacement, mtime_ns=BASE_NS + 11_000_000_000)

    fresh_insensitive = search_service.load_book_index(book_id, directory, case_sensitive=False)
    fresh_sensitive = search_service.load_book_index(book_id, directory, case_sensitive=True)

    assert fresh_insensitive is not warm_insensitive
    assert fresh_sensitive is not warm_sensitive
    assert new_marker.casefold() in fresh_insensitive.chapters[0].normalized_text
    assert new_marker in fresh_sensitive.chapters[0].normalized_text
    assert old_marker.casefold() not in fresh_insensitive.chapters[0].normalized_text
    assert old_marker not in fresh_sensitive.chapters[0].normalized_text


# ==========================================================================
# C7 — the loader patch seam still isolates the index from the disk
# ==========================================================================


def test_substituting_the_loader_still_keeps_the_index_off_the_disk(
    monkeypatch: pytest.MonkeyPatch, clean_index_cache
):
    """L3 - the outer stat is key material, not an existence check.

    `test_highlight_utf16_offsets.py` and `test_normalize_index_map_container.py`
    both build a `BookIndex` from a fabricated `Book` by patching
    `search_service.load_book_cached` and passing a `books_dir` that does not
    exist. That works because `load_book_cached` is the one listed seam for
    reaching `book.pkl`. An outer stat that raised would put a second, unlisted
    disk dependency under that seam and break both files' setup — so the
    fallback key is a contract, not an implementation detail, and this case is
    where it is stated.
    """

    class _Chapter:
        title = "Only Chapter"
        text = "WI8SEAMMARKER the tide went out."
        order = 0  # rule 12: coordinator ruling 2026-10-09 WI-4c.3 (fake must model ChapterContent.order)

    class _Metadata:
        title = "Seam Book"
        authors = ["Seam Author"]

    class _Book:
        metadata = _Metadata()
        spine = [_Chapter()]

    book = _Book()
    monkeypatch.setattr(search_service, "load_book_cached", lambda book_id, books_dir: book)

    nowhere = "/dev/null/reader3-wi8-no-such-books-dir"
    assert not os.path.exists(nowhere)

    index = search_service.load_book_index("wi8_fake_data", nowhere, case_sensitive=False)

    assert index.book_title == "Seam Book"
    assert index.book_author == "Seam Author"
    assert "wi8seammarker" in index.chapters[0].normalized_text
