"""`reader3_app.book_store` — the merged, mtime-keyed book loader (011 §4, WI-1).

Three laws are under test here, and every case below belongs to one of them:

1. **Invalidation is exactly one-way (read-your-writes).** The value returned is
   the content of ``book.pkl`` as of its current ``(st_mtime_ns, st_size)``.
   Changed stat means a new object built from the new bytes; **unchanged stat
   means the `is`-identical previous object and zero new unpickles**. The second
   half is the negative control without which "a cache that never caches" passes
   every freshness case.
2. **Conservation of unpickles.** Exactly one ``safe_pickle.safe_load`` per
   distinct ``(book, generation)`` pair, and ``hits + misses`` equals the number
   of outer calls — which is what forbids a second memo layer in the wrapper.
3. **The bound holds under invalidation.** ``currsize <= maxsize == 10`` at every
   point, including after invalidations that leave stale keys behind.

`book_store` is imported inside each test body rather than at module scope. That
is not style: before the module exists, a top-level import turns the whole file
into a *collection error*, which reports as an error with no test counts and is
indistinguishable from a broken runner. Resolved in the body through `book_store()`
below, the pre-implementation red is a counted assertion failure that names the
missing module in a sentence.

Assertion rungs (L1-L4) and spec levels (S1-S6) follow
`.claude/tdd-guardian/tests-20260907T073506Z.md` §0.1-§0.2.
"""

from __future__ import annotations

import importlib
import importlib.util
import itertools
import json
import os
import pickle
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from synthetic_library import make_book, make_synthetic_library

#: Same alphabet as `test_process_epub_staging.py:28`. A book id that reaches
#: `_book_pkl_path` in production is `listdir` output already filtered by
#: `_validate_book_id_path_safe`, i.e. `[A-Za-z0-9_-]+` ending in `_data`.
SEGMENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=8)

#: Every `books_dir` spelling an `abspath`/`normpath` would rewrite. If a future
#: normalizer lands, W1-C0a must go red on one of these, not squeak by on two
#: already-canonical examples.
DIRECTORY_SPELLINGS = ["books", "./books", "books/", "books//sub", "../books", "/abs/books", ""]

#: An explicit constant, never the clock. Two writes inside one filesystem tick
#: with the same byte count are invisible to a `(mtime_ns, size)` key, so no case
#: in this file may let wall-clock time carry an invalidation claim (§0.4 rule 1).
BASE_NS = 1_700_000_000_000_000_000


def book_store():
    """Import the module under test, in the test body. See the file docstring.

    The existence check is `find_spec` plus an `assert` rather than a bare
    import, so that a not-yet-written module fails as a *counted assertion*
    carrying a sentence instead of as an unresolved-import traceback. The
    distinction is not cosmetic: the red-run classifiers in this repo's tooling
    read an unresolved import as a broken environment, which is exactly the
    verdict a deliberately-absent module must not produce.
    """
    assert importlib.util.find_spec("reader3_app.book_store") is not None, (
        "src/reader3_app/book_store.py does not exist. It belongs at the package "
        "root, never under reader3_app/web/ — see D6 and Check B-i "
        "(web_namespace_offenders), which has no whitelist by design."
    )
    return importlib.import_module("reader3_app.book_store")


@pytest.fixture(autouse=True)
def _clear_book_store_cache():
    """Teardown-only, and tolerant of the module not existing yet.

    Written as teardown rather than setup on purpose: a *setup* fixture that
    imported `book_store` would make the pre-implementation red a fixture error
    instead of a test failure, which is the exact confusion the file docstring
    describes.
    """
    yield
    module = sys.modules.get("reader3_app.book_store")
    if module is not None:
        module.load_book_cached.cache_clear()


def fresh_loader():
    """The module under test, with an empty cache."""
    module = book_store()
    module.load_book_cached.cache_clear()
    return module


def one_book(books_dir: Path, *, count: int = 1):
    """A minimal synthetic library. Small chapters: this lane is budgeted in seconds."""
    return make_synthetic_library(books_dir, count=count, chapters=2, chapter_chars=200)


# ==========================================================================
# _book_pkl_path
# ==========================================================================


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(directory=st.sampled_from(DIRECTORY_SPELLINGS), stem=SEGMENT)
def test_book_pkl_path_never_normalizes_the_directory_it_was_given(directory, stem):
    """L2 / S4 (W1-C0a) - the path builder preserves its `books_dir` prefix verbatim.

    No `abspath`, no `normpath`, no `realpath`, no trailing-separator cleanup.
    This is the law that makes `"books"` and `"./books"` two distinct cache keys
    (W1-C0b), and it is what `tests/contract/test_read_chapter_traversal.py`
    guards from the other side. A property rather than two examples because the
    risk is a *future* normalizer that a canonical-input test would not see.
    """
    module = book_store()
    book_id = stem + "_data"

    result = module._book_pkl_path(book_id, directory)

    assert result == os.path.join(directory, book_id, "book.pkl")
    assert result.startswith(directory)
    assert os.path.basename(result) == "book.pkl"
    # Pure function: it answers for a directory that does not exist, so it
    # cannot be consulting the filesystem.
    assert not os.path.exists(result)


def test_two_spellings_of_one_directory_are_two_cache_entries(
    books_dir: Path, monkeypatch, count_unpickles
):
    """L2 / S2 (W1-C0b) - characterization: `books` and `./books` are two keys.

    `books_dir` is **not** normalized into the cache key. Production always
    passes the identical `server.BOOKS_DIR` string, so the duplicate never
    happens there, and normalizing would alter the path construction that
    `tests/contract/test_read_chapter_traversal.py` guards.

    A future normalizer must turn this case red **deliberately**, and read the
    tension it records: normalizing would make W3-C11 (relative `BOOKS_DIR` at a
    production call site) easier, and not normalizing is what the plan chose.
    """
    one_book(books_dir)
    monkeypatch.chdir(books_dir.parent)
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", "books")
    second = module.load_book_cached("synth00_data", "./books")

    assert first.metadata.title == second.metadata.title == "Synthetic Book 00"
    assert first is not second
    info = module.load_book_cached.cache_info()
    assert (info.misses, info.hits, info.currsize) == (2, 0, 2)
    assert count_unpickles.count == 2


# ==========================================================================
# load_book_cached
# ==========================================================================


def test_a_second_read_of_an_untouched_book_is_the_same_object(
    books_dir: Path, count_unpickles
):
    """L2 / S1 (W1-C1) - the base example: one unpickle, two calls, one object.

    The `count_unpickles` spy sits on `safe_pickle.safe_load`. A `book_store`
    that bound `safe_load` directly into its own globals would make this count
    0 and say so here on the first run.
    """
    one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    second = module.load_book_cached("synth00_data", str(books_dir))

    assert first is second
    assert first.metadata.title == "Synthetic Book 00"
    info = module.load_book_cached.cache_info()
    assert (info.misses, info.hits, info.currsize) == (1, 1, 1)
    assert count_unpickles.count == 1


def test_a_rewritten_book_pkl_is_seen_on_the_next_read(
    books_dir: Path, count_unpickles, rewrite_book_pkl
):
    """L3 / S1 (W1-C2) - read-your-writes: a republished book.pkl is observed.

    The whole point of §4: today `server` and `search_service` each hold a
    `(book_id, books_dir)`-keyed cache, so a republish is invisible until the
    process restarts. Dropping `st_mtime_ns` from the key brings that back.
    """
    dirs = one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    assert first.metadata.title == "Synthetic Book 00"

    replacement = make_book(0, chapters=2, chapter_chars=200)
    replacement.metadata.title = "Rewritten Book"
    mtime_ns, _size = rewrite_book_pkl(dirs[0], replacement, mtime_ns=1_800_000_000_000_000_000)
    assert mtime_ns == 1_800_000_000_000_000_000

    second = module.load_book_cached("synth00_data", str(books_dir))

    assert second.metadata.title == "Rewritten Book"
    assert second is not first
    assert module.load_book_cached.cache_info().misses == 2
    assert count_unpickles.count == 2


@pytest.mark.parametrize(
    "delta_ns", [1_000, 1_000_000, 1_000_000_000], ids=["1us", "1ms", "1s"]
)
def test_identical_bytes_with_a_bumped_mtime_still_invalidate(
    books_dir: Path, count_unpickles, delta_ns
):
    """L3 / S2 (W1-C3) - the key carries mtime, not content, at nanosecond resolution.

    Two jobs in one case. First, the negative control against a content-derived
    key: identical bytes plus a moved mtime must still produce a *new* object.
    Second, the resolution test — **the 1 us leg is the one that matters**. Every
    coarser delta survives a key built from `int(st.st_mtime)` or
    `os.path.getmtime()`, so a single-delta case would greenlight a
    seconds-resolution key that silently loses every sub-second republish.
    """
    dirs = one_book(books_dir)
    path = Path(dirs[0]) / "book.pkl"
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    before = os.stat(path)

    path.write_bytes(path.read_bytes())  # byte-identical
    target = before.st_mtime_ns + delta_ns
    os.utime(path, ns=(target, target))

    # Precondition, asserted before the cache claim (§0.4 rule 2). On a
    # filesystem that truncates to whole seconds the 1us leg fails *here*,
    # loudly, instead of passing vacuously.
    after = os.stat(path)
    assert after.st_mtime_ns == target
    assert after.st_size == before.st_size

    second = module.load_book_cached("synth00_data", str(books_dir))

    assert second is not first
    assert second.metadata.title == first.metadata.title
    assert module.load_book_cached.cache_info().misses == 2
    assert count_unpickles.count == 2


def test_a_same_mtime_size_change_also_invalidates(
    books_dir: Path, count_unpickles, rewrite_book_pkl
):
    """L3 / S1 (W1-C4) - the size half of the key, isolated by holding mtime still.

    Keying on `st_mtime_ns` alone loses this. It is not hypothetical: a restore
    that preserves timestamps writes a different book under the old mtime.
    """
    dirs = one_book(books_dir)
    path = Path(dirs[0]) / "book.pkl"
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    before = os.stat(path)

    longer = make_book(0, chapters=5, chapter_chars=200)
    rewrite_book_pkl(dirs[0], longer, mtime_ns=before.st_mtime_ns)

    after = os.stat(path)
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_size != before.st_size

    second = module.load_book_cached("synth00_data", str(books_dir))

    assert second is not first
    assert len(second.spine) != len(first.spine)
    assert module.load_book_cached.cache_info().misses == 2


def test_the_exact_original_stat_is_a_hit_even_after_a_rewrite(
    books_dir: Path, count_unpickles
):
    """L2 / S1 (W1-C5) - the mandatory negative control for W1-C2/C3/C4.

    An implementation that re-loads on every call and only *pretends* to cache
    passes all three invalidation cases and fails here. So does any `open()`-based
    staleness heuristic. Note that `os.utime` restores atime and mtime but still
    bumps `st_ctime`: a key that carried ctime would fail this case, which is
    exactly what it is for.
    """
    dirs = one_book(books_dir)
    path = Path(dirs[0]) / "book.pkl"
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    before = os.stat(path)

    path.write_bytes(path.read_bytes())
    os.utime(path, ns=(before.st_mtime_ns, before.st_mtime_ns))

    after = os.stat(path)
    assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)

    second = module.load_book_cached("synth00_data", str(books_dir))

    assert second is first
    info = module.load_book_cached.cache_info()
    assert (info.misses, info.hits) == (1, 1)
    assert count_unpickles.count == 1


@pytest.mark.parametrize("damage", ["garbage", "truncated", "missing_pkl", "missing_dir"])
def test_a_corrupt_or_missing_book_pkl_raises_and_caches_nothing(
    books_dir: Path, count_unpickles, damage
):
    """L4 / S3 (W1-C6) - exhaustive over the damage shapes, plus absence. D1-a: it raises.

    The core does not swallow and does not return `None`. The repair leg is the
    load-bearing half: it kills an implementation that memoizes a sentinel or
    caches the exception, which a raise-only assertion cannot see.
    """
    import bookdir

    dirs = one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()

    if damage == "garbage":
        bookdir.break_book_pkl(dirs[0])
        book_id, expected = "synth00_data", pickle.UnpicklingError
    elif damage == "truncated":
        bookdir.truncate_book_pkl(dirs[0], keep=32)
        book_id, expected = "synth00_data", pickle.UnpicklingError
    elif damage == "missing_pkl":
        (Path(dirs[0]) / "book.pkl").unlink()
        book_id, expected = "synth00_data", FileNotFoundError
    else:
        book_id, expected = "no_such_book_data", FileNotFoundError

    with pytest.raises(expected) as excinfo:
        module.load_book_cached(book_id, str(books_dir))

    if expected is FileNotFoundError:
        # Raised by the `os.stat`, before any `open()` — same exception type the
        # pre-merge loader produced (`test_fixture_damaged_bookdir.py:120`), so
        # this is preservation, not change.
        assert str(excinfo.value.filename).endswith("book.pkl")
        assert count_unpickles.count == 0

    assert module.load_book_cached.cache_info().currsize == 0, (
        "a failed read must cache nothing: neither a sentinel nor the exception"
    )

    repaired = make_book(0, chapters=2, chapter_chars=200)
    repaired.metadata.title = "Repaired Book"
    target = Path(books_dir) / book_id
    target.mkdir(parents=True, exist_ok=True)
    with open(target / "book.pkl", "wb") as f:
        pickle.dump(repaired, f)

    assert module.load_book_cached(book_id, str(books_dir)).metadata.title == "Repaired Book"


@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=50,
    deadline=None,
)
@given(
    schedule=st.lists(
        st.tuples(st.sampled_from(["read", "rewrite"]), st.integers(0, 4)),
        min_size=1,
        max_size=10,
    )
)
def test_one_unpickle_per_book_generation_across_any_read_and_rewrite_schedule(
    books_dir: Path, count_unpickles, rewrite_book_pkl, schedule
):
    """L3 / S5 (W1-C7) - one unpickle per distinct (book, generation), whatever the schedule.

    This is the case that kills the whole class: no-cache, double-memo,
    per-call restat-and-reload, "a fresh object every time", and — the one a
    matrix of single-book invalidation cases cannot see — an implementation that
    calls `cache_clear()` whenever it notices a stat change. That last one makes
    the homepage re-unpickle the whole warm library after any publish, strictly
    worse than today, and `bench.py`'s sequence has no publish step so the
    benchmark would still read as improved.

    `max_size=10` is load-bearing: at most 10 read ops means at most 10 distinct
    keys, so `maxsize=10` never evicts and the counts below are exact equalities
    rather than inequalities.
    """
    dirs = one_book(books_dir, count=5)
    module = book_store()

    # Hypothesis reuses the tmp library across examples: reset to generation 0.
    gen = [0] * 5
    for i in range(5):
        base = make_book(i, chapters=2, chapter_chars=200)
        base.metadata.title = f"book{i} gen0"
        rewrite_book_pkl(dirs[i], base, mtime_ns=BASE_NS + i * 1_000_000_000)
    module.load_book_cached.cache_clear()
    count_unpickles.reset()

    maxsize = module.load_book_cached.cache_parameters()["maxsize"]
    first_seen = {}
    distinct_pairs = set()
    reads = 0

    for op, i in schedule:
        if op == "rewrite":
            gen[i] += 1
            replacement = make_book(i, chapters=2, chapter_chars=200)
            replacement.metadata.title = f"book{i} gen{gen[i]}"
            rewrite_book_pkl(
                dirs[i],
                replacement,
                mtime_ns=BASE_NS + i * 1_000_000_000 + gen[i] * 1_000_000,
            )
            continue

        reads += 1
        key = (i, gen[i])
        distinct_pairs.add(key)
        got = module.load_book_cached(f"synth{i:02d}_data", str(books_dir))

        # Freshness, so the identity claim below cannot be satisfied by an
        # implementation that simply never reloads.
        assert got.metadata.title == f"book{i} gen{gen[i]}"
        if key in first_seen:
            assert got is first_seen[key]
        else:
            first_seen[key] = got

        assert module.load_book_cached.cache_info().currsize <= maxsize

    info = module.load_book_cached.cache_info()
    assert count_unpickles.count == len(distinct_pairs)
    assert info.misses == len(distinct_pairs)
    assert info.hits + info.misses == reads, (
        "hits + misses must equal the number of outer calls; anything else means "
        "a second memo layer is answering some calls before the cache sees them"
    )


def test_rewriting_one_book_does_not_evict_the_others(
    books_dir: Path, count_unpickles, rewrite_book_pkl
):
    """L3 / S2 (W1-C7b) - invalidating book A must not cost book B its entry.

    The legible-message companion to W1-C7's third bullet. When a blanket
    `cache_clear()` on stat change ships, this fails in one line — "B was
    re-unpickled" — where W1-C7 fails with a shrunk schedule that takes ten
    minutes to read.
    """
    dirs = one_book(books_dir, count=2)
    module = fresh_loader()
    count_unpickles.reset()

    a_first = module.load_book_cached("synth00_data", str(books_dir))
    b_first = module.load_book_cached("synth01_data", str(books_dir))

    replacement = make_book(0, chapters=2, chapter_chars=200)
    replacement.metadata.title = "A prime"
    rewrite_book_pkl(dirs[0], replacement, mtime_ns=BASE_NS + 42_000_000)

    a_second = module.load_book_cached("synth00_data", str(books_dir))
    b_second = module.load_book_cached("synth01_data", str(books_dir))

    assert b_second is b_first, "rewriting book A evicted book B"
    assert a_second is not a_first
    assert a_second.metadata.title == "A prime"
    assert count_unpickles.count == 3
    info = module.load_book_cached.cache_info()
    assert (info.hits, info.misses) == (1, 3)


def test_eleven_generations_of_one_book_never_exceed_the_bound(
    books_dir: Path, rewrite_book_pkl
):
    """L3 / S3 (W1-C8) - one more generation than `maxsize`, bound asserted after every call.

    The refactor this forbids is the obvious "simplification": replacing
    `lru_cache` with an unbounded dict keyed on the stat tuple. That dict grows
    without limit as books are republished, which is precisely why the bound is
    an acceptance criterion.
    """
    dirs = one_book(books_dir)
    module = fresh_loader()
    maxsize = module.load_book_cached.cache_parameters()["maxsize"]
    assert maxsize == 10

    for generation in range(11):
        replacement = make_book(0, chapters=2, chapter_chars=200)
        replacement.metadata.title = f"generation {generation}"
        rewrite_book_pkl(dirs[0], replacement, mtime_ns=BASE_NS + generation * 1_000_000)

        got = module.load_book_cached("synth00_data", str(books_dir))

        assert got.metadata.title == f"generation {generation}"
        assert module.load_book_cached.cache_info().currsize <= maxsize

    assert module.load_book_cached.cache_info().misses == 11


@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=30,
    deadline=None,
)
@given(
    ops=st.lists(
        st.tuples(st.integers(0, 11), st.booleans()), min_size=1, max_size=24
    )
)
def test_the_bound_holds_across_a_generated_interleaving_of_twelve_books(
    books_dir: Path, rewrite_book_pkl, ops
):
    """L3 / S4 (W1-C8, generalized) - `currsize <= maxsize` over generated interleavings.

    Twelve books against a bound of ten, with generated mutation points, so the
    bound is exercised under eviction *and* under stale keys left behind by
    invalidation rather than only under the single-book ramp above.
    """
    dirs = one_book(books_dir, count=12)
    module = book_store()
    module.load_book_cached.cache_clear()
    maxsize = module.load_book_cached.cache_parameters()["maxsize"]
    generations = [0] * 12

    for index, mutate in ops:
        if mutate:
            generations[index] += 1
            replacement = make_book(index, chapters=2, chapter_chars=200)
            replacement.metadata.title = f"book{index} gen{generations[index]}"
            rewrite_book_pkl(
                dirs[index],
                replacement,
                mtime_ns=BASE_NS + index * 1_000_000_000 + generations[index] * 1_000_000,
            )
        module.load_book_cached(f"synth{index:02d}_data", str(books_dir))
        assert module.load_book_cached.cache_info().currsize <= maxsize


def test_the_cache_surface_is_live_and_adds_no_second_layer(
    books_dir: Path, count_unpickles
):
    """L1+L2 / S2 (W1-C9) - the three cache attributes exist and actually reach the disk.

    Existence alone is L1 and would pass for a `cache_clear` that zeroes a
    counter while a second memo keeps answering. The load-bearing half is that
    a read *after* the clear produces a fresh `safe_load`. `functools.partial`
    (no attributes), a hand-rolled dict (no `cache_parameters`) and a
    double-wrapped `lru_cache` all fail somewhere in here.
    """
    one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()
    loader = module.load_book_cached

    assert callable(loader.cache_clear)
    assert callable(loader.cache_info)
    assert callable(loader.cache_parameters)
    assert loader.cache_parameters() == {"maxsize": 10, "typed": False}

    loader("synth00_data", str(books_dir))
    assert count_unpickles.count == 1

    loader.cache_clear()
    assert tuple(loader.cache_info()) == (0, 0, 10, 0)

    loader("synth00_data", str(books_dir))
    assert loader.cache_info().misses == 1
    assert count_unpickles.count == 2, (
        "the read after cache_clear() did not reach the disk, so something above "
        "the lru_cache is still memoizing"
    )

    loader.cache_clear()
    loader.cache_clear()
    assert tuple(loader.cache_info()) == (0, 0, 10, 0)


def test_keyword_and_positional_calls_are_one_entry(books_dir: Path, count_unpickles):
    """L2 / S2 (W1-C10) - characterization: the same read spelled two ways is one key.

    Pre-merge these were genuinely **two** `lru_cache` keys: `search_service.py:233`
    decorated the public name directly, and `lru_cache` keys on the raw call
    shape, so `(name, d)` and `(name,) + kwargs-marker` hashed differently.
    Post-merge the public name must `os.stat` on every call, so it is a plain
    `def` with named parameters and Python binds `book_id`/`books_dir` to the
    same locals *before* the inner memo is reached. **The wart closes as a free
    consequence of the stat wrapper.** Recorded here so nobody reintroduces it by
    re-decorating the public name, and so no reader is left believing the old
    "all call sites must pass positionally" folklore.
    """
    one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()

    first = module.load_book_cached("synth00_data", str(books_dir))
    second = module.load_book_cached(book_id="synth00_data", books_dir=str(books_dir))

    assert second is first
    info = module.load_book_cached.cache_info()
    assert (info.misses, info.hits) == (1, 1)
    assert count_unpickles.count == 1


def test_two_threads_missing_the_same_key_load_twice_and_cache_once(
    books_dir: Path, count_unpickles
):
    """L4 / S1 (W1-C11) - the stat-then-load race is accepted; this pins its bound.

    The barrier makes the interleaving deterministic: both threads are provably
    inside `safe_load` at the same moment, so `count == 2` is a recorded
    contract rather than a flake. Adding a lock around the load would make it 1
    — a real improvement, and one that must be a deliberate edit here, because
    three call sites run under `run_in_threadpool`.
    """
    one_book(books_dir)
    module = fresh_loader()
    count_unpickles.reset()

    barrier = threading.Barrier(2, timeout=5)
    invocations = itertools.count()

    def park_the_first_two():
        if next(invocations) < 2:
            barrier.wait()  # BrokenBarrierError on timeout: fails loudly, never hangs

    count_unpickles.before = park_the_first_two

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(module.load_book_cached, "synth00_data", str(books_dir))
            for _ in range(2)
        ]
        results = [f.result(timeout=10) for f in futures]

    assert all(r.metadata.title == "Synthetic Book 00" for r in results)
    assert count_unpickles.count == 2
    assert module.load_book_cached.cache_info().currsize == 1

    third = module.load_book_cached("synth00_data", str(books_dir))
    assert third is results[0] or third is results[1]
    assert count_unpickles.count == 2
    assert module.load_book_cached.cache_info().hits == 1


def test_book_store_imports_without_fastapi_or_the_web_package():
    """L1 / S1 (W1-C12) - the package-root location (D6) is load-bearing, so assert it.

    A child interpreter, because in-process inspection cannot answer this: the
    lane has already imported `fastapi` by the time this runs. `book_store`
    reaching for `server.BOOKS_DIR` would be simultaneously an import cycle and
    a Check-C capture in `test_server_patch_seam_ownership.py`.
    """
    book_store()  # precondition: the module exists at all, asserted before the child runs

    snippet = (
        "import json, sys\n"
        "import reader3_app.book_store\n"
        "bad = sorted(m for m in sys.modules "
        "if m.startswith(('fastapi', 'starlette', 'reader3_app.web')))\n"
        "print(json.dumps(bad))\n"
    )

    proc = subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == []
