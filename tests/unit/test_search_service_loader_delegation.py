"""`reader3_app.search_service.load_book_cached` — delegation to `book_store` (011 §4, WI-2).

**Law: object identity ⇒ cache identity.** `search_service.load_book_cached`
*is* `book_store.load_book_cached` — one object, therefore one cache, therefore
one unpickle per book per stat generation across both modules. There is no
separate `search_service` loading behaviour left to specify; that is the whole
point of the work item, and W2-C1 is where the "one object" claim is pinned.

W2-C1 is deliberately the single L1 case in this file. On its own an identity
assertion between two module attributes would be wiring-checking, so it is
paired with three behavioural cases: the cache surface reaching across the two
names (W2-C2), the derived index still resting on the merged loader (W2-C3),
and the characterization of what the merge did *not* fix (W2-C4).

What this file must **not** grow: a restatement of
`tests/unit/test_fixture_synthetic_library.py::test_one_pass_over_the_library_evicts_books_it_already_loaded`
(`misses == 20`, `hits == 0`, `currsize == maxsize == 10`). That test is the
eviction evidence for the merged cache and it is run as a regression, not
duplicated here.

Assertion rungs (L1-L4) and spec levels (S1-S6) follow
`.claude/tdd-guardian/tests-20260907T073506Z.md` §0.1-§0.2.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from reader3_app import book_store, search_service
from synthetic_library import chapter_marker, make_book, make_synthetic_library

#: An explicit constant, never the clock (§0.4 rule 1). Two writes inside one
#: filesystem tick with the same byte count are invisible to a
#: `(mtime_ns, size)` key, so no invalidation claim here rides on wall time.
BASE_NS = 1_700_000_000_000_000_000


def two_books(books_dir: Path):
    """A two-book synthetic library. Small chapters: this lane is budgeted in seconds."""
    return make_synthetic_library(books_dir, count=2, chapters=2, chapter_chars=200)


# ==========================================================================
# W2-C1 — the identity that carries every other claim in this file
# ==========================================================================


def test_search_service_exports_the_book_store_loader_itself():
    """L1 / S1 (W2-C1) - `search_service.load_book_cached` IS `book_store`'s.

    Not "behaves like", not "delegates to": the same object. A re-export shim
    (`from .book_store import load_book_cached as _loader` plus a wrapper), or
    D5-b routing the search path through `server`, would each satisfy a
    behavioural test and fail here — which is why the identity is asserted
    directly rather than inferred from a shared cache count.

    The signature half forecloses the `*args/**kwargs` passthrough escape
    hatch: a variadic forwarder would keep every call site working while
    quietly dropping the two-positional-parameter contract that
    `test_read_chapter_traversal.py` and the six `monkeypatch.setattr` stubs
    are written against.
    """
    assert search_service.load_book_cached is book_store.load_book_cached, (
        "WI-2 requires `from .book_store import load_book_cached` with no alias "
        "and no wrapper: two objects mean two caches, which is the bug §4 exists "
        "to remove."
    )

    signature = inspect.signature(search_service.load_book_cached)
    parameters = list(signature.parameters.values())

    assert [p.name for p in parameters] == ["book_id", "books_dir"]
    for parameter in parameters:
        assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        # `from __future__ import annotations` leaves annotations as strings in
        # the defining module, so accept either spelling of the same type.
        annotation = parameter.annotation
        assert getattr(annotation, "__name__", annotation) == "str"


# ==========================================================================
# W2-C2 — one cache, reachable and clearable through either name
# ==========================================================================


def test_the_cache_surface_survives_the_delegation(
    books_dir: Path, count_unpickles, merged_loader_cache
):
    """L2 / S2 (W2-C2) - the surface is exercised for its effect *through the other name*.

    `cache_clear()` is called on `book_store` and observed on
    `search_service`. That cross-name observation is what "one cache" means
    operationally, and it is what a `search_service` holding its own wrapper
    object with copied attributes would fail: such a wrapper can expose
    `cache_clear` and still leave the search path serving a stale object.

    `maxsize` is read off the live `cache_parameters()` rather than compared to
    a copied literal, so D3-a (maxsize stays 10) turns this red if it is ever
    revisited without the WI-8 sizing work that owns it.
    """
    two_books(books_dir)
    directory = str(books_dir)

    assert search_service.load_book_cached.cache_parameters()["maxsize"] == 10

    count_unpickles.reset()
    first = search_service.load_book_cached("synth00_data", directory)
    again = search_service.load_book_cached("synth00_data", directory)

    assert first is again
    assert count_unpickles.count == 1
    assert search_service.load_book_cached.cache_info().currsize == 1

    # The clear goes through the *other* name.
    book_store.load_book_cached.cache_clear()

    info = search_service.load_book_cached.cache_info()
    assert (info.currsize, info.hits, info.misses) == (0, 0, 0)

    after_clear = search_service.load_book_cached("synth00_data", directory)

    assert after_clear is not first
    assert after_clear.metadata.title == first.metadata.title == "Synthetic Book 00"
    assert count_unpickles.count == 2
    assert search_service.load_book_cached.cache_info().misses == 1


# ==========================================================================
# W2-C3 — the derived index still rests on the merged loader
# ==========================================================================


@pytest.mark.parametrize("book_index", [0, 1])
def test_load_book_index_still_builds_on_the_merged_loader(
    books_dir: Path, count_unpickles, merged_loader_cache, book_index
):
    """L3 / S2 (W2-C3) - one unpickle feeds three derived reads, both case modes.

    `load_book_index` must keep reaching the loader as a module-level Name load
    (`search_service.py:284`). Two shapes break this and both are caught here:
    the index acquiring its own `load_book_file` call (the count goes to 2 or
    3), and the call site being rewritten as `book_store.load_book_cached(...)`
    — which would also turn `test_server_patch_seam_ownership.py::test_a6` red
    by dropping `search_service` from `GLOBAL_RESOLVERS["load_book_cached"]`.

    The index's own cache stays keyed on `case_sensitive`, so the two index
    reads are two misses over one loaded book, not one.
    """
    two_books(books_dir)
    search_service.load_book_index.cache_clear()
    directory = str(books_dir)
    book_id = f"synth{book_index:02d}_data"

    count_unpickles.reset()
    book = search_service.load_book_cached(book_id, directory)
    insensitive = search_service.load_book_index(book_id, directory, case_sensitive=False)
    sensitive = search_service.load_book_index(book_id, directory, case_sensitive=True)

    assert count_unpickles.count == 1, (
        "three reads of one book at one stat generation must cost exactly one "
        "unpickle; a second read means the index stopped sharing the loader"
    )
    assert search_service.load_book_index.cache_info().misses == 2
    assert insensitive.book_title == sensitive.book_title == book.metadata.title
    assert insensitive.book_title == f"Synthetic Book {book_index:02d}"

    marker = chapter_marker(book_index, 0)
    assert marker.casefold() in insensitive.chapters[0].normalized_text
    assert marker in sensitive.chapters[0].normalized_text


# ==========================================================================
# W2-C4 — characterization: what the merge did NOT fix
# ==========================================================================


def test_the_index_cache_still_serves_stale_text_after_the_pickle_changes(
    books_dir: Path, merged_loader_cache, rewrite_book_pkl
):
    """L3 / S2 (W2-C4) - characterization. Recorded, not endorsed.

    `load_book_index` (`maxsize=4`, no re-stat) is WI-8/C1's job; this test is
    its ready-made red. 011 §4 must not be read as "the cache knows the disk
    changed": after `book.pkl` is republished, `load_book_cached` returns the
    new bytes while a *warm* `load_book_index` entry keeps serving the old
    normalized text.

    Both halves are asserted in one test on purpose. Split apart, the fresh
    half would pass on a codebase where the stale half had been fixed and the
    stale half would pass on a codebase where the loader fix had been reverted;
    together they pin the exact divergence that exists today. WI-8 putting the
    stat into the index's key is the intended future red — when it lands, this
    test must be rewritten deliberately, not relaxed.
    """
    directories = two_books(books_dir)
    search_service.load_book_index.cache_clear()
    directory = str(books_dir)
    book_id = "synth00_data"
    old_marker = chapter_marker(0, 0)
    new_marker = "W2C4REPUBLISHEDMARKER"

    warm = search_service.load_book_index(book_id, directory, case_sensitive=False)
    assert old_marker.casefold() in warm.chapters[0].normalized_text
    assert new_marker.casefold() not in warm.chapters[0].normalized_text

    replacement = make_book(0, chapters=2, chapter_chars=200)
    replacement.spine[0].text = f"{new_marker} the tide came back in."
    replacement.spine[0].content = f"<p>{new_marker} the tide came back in.</p>"
    mtime_ns, _size = rewrite_book_pkl(
        directories[0], replacement, mtime_ns=BASE_NS + 9_000_000_000
    )
    assert mtime_ns == BASE_NS + 9_000_000_000

    # Half one: the loader is fresh. This is what WI-1/WI-2 bought.
    reloaded = search_service.load_book_cached(book_id, directory)
    assert new_marker in reloaded.spine[0].text
    assert old_marker not in reloaded.spine[0].text

    # Half two: the derived index is not. This is the gap WI-8 owns.
    stale = search_service.load_book_index(book_id, directory, case_sensitive=False)
    assert stale is warm
    assert old_marker.casefold() in stale.chapters[0].normalized_text
    assert new_marker.casefold() not in stale.chapters[0].normalized_text, (
        "load_book_index re-stated the file, which means WI-8/C1 landed. Rewrite "
        "this characterization deliberately; do not delete the assertion."
    )
