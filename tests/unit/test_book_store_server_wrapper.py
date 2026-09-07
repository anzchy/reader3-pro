"""`reader3_app.web.server.load_book_cached` — the thin wrapper (011 §4, WI-3).

Three laws, and every case below belongs to one of them (matrix
`.claude/tdd-guardian/tests-20260907T073506Z.md`, "Unit: `reader3_app.web.server#load_book_cached`"):

1. **Conservation of unpickles across the merged cache.** For `N` distinct
   books read `K` times each through *any* interleaving of the two loader
   names, with the `books_dir` string spelled the way production spells it:
   exactly `N` calls to `safe_pickle.safe_load`. Not `N*K`, and not `2N` —
   `2N` is today's number and is precisely what this work item deletes.
2. **Late binding.** The result is a function of `server.BOOKS_DIR` **as read
   at call time**. Today it is not: the cache keys on `folder_name` alone, so a
   rebound `BOOKS_DIR` keeps serving the old library's book. W3-C4 is the only
   evidence for that fix anywhere in the suite.
3. **Totality of the degradation.** For *every* exception the core can raise —
   not merely the two types the damage fixtures happen to produce — the server
   side is a total function into `Optional[Book]`. It never raises; the core
   raises on the identical file. D1-a *is* that asymmetry, and
   `tests/unit/test_fixture_damaged_bookdir.py` must stay green unedited.

Assertion rungs (L1-L4) and spec levels (S1-S6) follow §0.1-§0.2 of the matrix.

Every case here points `server.BOOKS_DIR` at a directory under `tmp_path`
before calling the wrapper (§0.4 rule 3). Unpatched it reads the developer's
real library, and post-merge those real books would land in the *shared* cache
and poison `test_fixture_synthetic_library.py`'s exact miss counts.
"""

from __future__ import annotations

import os
import pickle
import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader3_app import book_store, safe_pickle, search_service
from reader3_app.web import server
from synthetic_library import make_book, make_synthetic_library

#: An explicit constant, never the clock. Two writes inside one filesystem tick
#: with the same byte count are invisible to a `(mtime_ns, size)` key, so no
#: case in this file may let wall-clock time carry an invalidation claim
#: (§0.4 rule 1).
BASE_NS = 1_700_000_000_000_000_000


@pytest.fixture(autouse=True)
def _clear_the_server_name_too():
    """Empty whatever cache `server.load_book_cached` is holding, both ends.

    `merged_loader_cache` (tests/unit/conftest.py) clears through `book_store`,
    which post-merge is enough because there is one cache. Before WI-3 lands,
    `server.load_book_cached` owns a *second* `lru_cache` that nothing else
    here clears, and a book left in it by the previous case would turn this
    file's first miss into a hit — a pre-implementation red that fails for the
    wrong reason. Clearing both names costs nothing once they coincide.
    """
    server.load_book_cached.cache_clear()
    yield
    server.load_book_cached.cache_clear()


def _library(books_dir: Path, count: int) -> list[str]:
    created = make_synthetic_library(books_dir, count=count, chapters=2, chapter_chars=200)
    return [p.name for p in created]


def _library_once(books_dir: Path, count: int) -> list[str]:
    """`_library`, but idempotent — for the two hypothesis cases.

    A function-scoped fixture is built once per *test*, while hypothesis
    re-enters the body once per *example*. Rebuilding the library on every
    example would rewrite `book.pkl` (new mtime, new cache generation) inside
    a case whose whole subject is how many unpickles a *fixed* library costs,
    so the counting law would be measuring the fixture instead of the cache.
    """
    names = [f"synth{i:02d}_data" for i in range(count)]
    if all((books_dir / n / "book.pkl").is_file() for n in names):
        return names
    return _library(books_dir, count)


# ==========================================================================
# W3-C1 / W3-C2 / W3-C11 — law 1: conservation of unpickles
# ==========================================================================


def test_both_names_return_the_same_book_object_through_the_production_books_dir(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
):
    """L3 / S2 (W3-C1) — **the §4 acceptance test**: one book, one object, one unpickle.

    Each direction of first call is exercised, because ordering is a real risk:
    a wrapper that always re-keys would be caught in one direction and not the
    other. Book A is read server-first, book B search-first, book C twice
    through the server name only.

    The search-side call passes `server.BOOKS_DIR` itself rather than a
    hand-written path string — the whole claim is that the two key tuples
    *coincide in production*, and a test that spells the directory by hand
    cannot see them diverge.
    """
    names = _library(books_dir, 3)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    count_unpickles.reset()

    a_server = server.load_book_cached(names[0])
    a_search = search_service.load_book_cached(names[0], server.BOOKS_DIR)

    b_search = search_service.load_book_cached(names[1], server.BOOKS_DIR)
    b_server = server.load_book_cached(names[1])

    c_first = server.load_book_cached(names[2])
    c_second = server.load_book_cached(names[2])

    assert a_server is a_search, "server-first: the two names built two Book objects"
    assert b_server is b_search, "search-first: the two names built two Book objects"
    assert c_second is c_first

    assert a_server.metadata.title == "Synthetic Book 00"
    assert b_server.metadata.title == "Synthetic Book 01"

    info = server.load_book_cached.cache_info()
    assert info.misses == 3, f"six reads of three books cost {info.misses} misses"
    assert count_unpickles.count == 3, (
        f"six reads of three books cost {count_unpickles.count} unpickles; "
        "3 is the merged number, 6 is one cache per module"
    )


@given(
    schedule=st.lists(
        st.tuples(st.integers(0, 4), st.sampled_from(["server", "search"])),
        min_size=1,
        max_size=30,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
def test_five_books_read_through_both_names_cost_five_unpickles(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
    schedule,
):
    """L3 / S5 (W3-C2) — **the conservation law**, over a generated schedule.

    Written as a counting invariant rather than three examples on purpose: the
    claim is about *any* interleaving of the two names, and an example-based
    version would only ever pin the interleavings someone thought of. No
    rewrites here — W1-C7 owns the rewrite dimension, this case owns the
    two-names dimension.
    """
    names = _library_once(books_dir, 5)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    book_store.load_book_cached.cache_clear()
    count_unpickles.reset()

    seen: dict[int, object] = {}
    for index, which in schedule:
        if which == "server":
            got = server.load_book_cached(names[index])
        else:
            got = search_service.load_book_cached(names[index], server.BOOKS_DIR)
        if index in seen:
            assert got is seen[index], (
                f"book {index} came back as a different object through {which!r}"
            )
        else:
            seen[index] = got

    distinct = len({i for i, _ in schedule})
    info = server.load_book_cached.cache_info()

    assert count_unpickles.count == distinct, (
        f"{len(schedule)} reads of {distinct} distinct books cost "
        f"{count_unpickles.count} unpickles"
    )
    assert info.misses == distinct
    assert info.hits + info.misses == len(schedule), (
        "hits + misses does not equal the number of outer calls — something "
        "above the cache is memoizing as well"
    )


def test_a_relative_books_dir_keys_both_names_identically(
    tmp_path: Path,
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
):
    """L3 / S2 (W3-C11) — production's own spelling of `BOOKS_DIR` is *relative*.

    Every other case in this file points `BOOKS_DIR` at an absolute `tmp_path`,
    where `os.path.abspath` is the identity function. A wrapper written as
    `book_store.load_book_cached(folder_name, os.path.abspath(BOOKS_DIR))` —
    or `str(Path(BOOKS_DIR).resolve())` — therefore passes W3-C1, W3-C2 and
    W3-C4 while shipping the exact defect §4 exists to delete: `server.py:99`
    defaults `BOOKS_DIR` to the bare literal `"books"` and `server.py:1072`
    forwards *that string* to `search_service`, so the two names would key on
    `"/abs/.../books"` and `"books"` — two entries, two unpickles per book.

    The one normalization this case owns is the one **in the server wrapper**,
    between `server.BOOKS_DIR` and the call into `book_store`. Normalization
    inside `_book_pkl_path` is W1-C0a's to catch, not this case's.
    """
    names = _library(books_dir, 1)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "BOOKS_DIR", "books")

    # Guard first, so the case cannot silently go absolute if someone tidies it.
    assert server.BOOKS_DIR == "books"
    assert not os.path.isabs(server.BOOKS_DIR)

    count_unpickles.reset()

    through_server = server.load_book_cached(names[0])
    through_search = search_service.load_book_cached(names[0], "books")

    assert through_server is not None, "the relative directory did not resolve at all"
    assert through_server is through_search, (
        "the wrapper re-spelled BOOKS_DIR on its way into book_store: two "
        "spellings of one directory are two cache entries"
    )
    assert count_unpickles.count == 1
    info = server.load_book_cached.cache_info()
    assert (info.misses, info.currsize) == (1, 1)


# ==========================================================================
# W3-C3 / W3-C3n / W3-C4 — law 2: the value follows the disk, and the constant
# ==========================================================================


def test_the_server_seam_sees_a_rewritten_book_pkl(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    rewrite_book_pkl,
    merged_loader_cache,
):
    """L3 / S1 (W3-C3) — **the §4.2 acceptance test**: republish is visible without a restart.

    `baseline_1b` cannot cover this. `tests/e2e/conftest.py`'s session fixture
    publishes all four books *before* the server starts and never touches
    `book.pkl` again, so a green E2E run is evidence that nothing else broke —
    it is not evidence for sub-item (b). This case and W3-C9 are the only
    evidence that exists.
    """
    names = _library(books_dir, 1)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    first = server.load_book_cached(names[0])
    assert first.metadata.title == "Synthetic Book 00"

    replacement = make_book(0, chapters=2, chapter_chars=200)
    replacement.metadata.title = "Republished Book"
    mtime_ns, size = rewrite_book_pkl(books_dir / names[0], replacement, mtime_ns=BASE_NS)
    stat_now = os.stat(books_dir / names[0] / "book.pkl")
    assert (stat_now.st_mtime_ns, stat_now.st_size) == (mtime_ns, size)

    second = server.load_book_cached(names[0])

    assert second.metadata.title == "Republished Book"
    assert second is not first


@pytest.mark.parametrize("shape", ["no_write_at_all", "identical_bytes_same_mtime"])
def test_an_untouched_book_pkl_does_not_invalidate_at_the_server_seam(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
    shape,
):
    """L2 / S2 (W3-C3n) — the mandatory negative control paired with W3-C3.

    An implementation that stats and reloads unconditionally passes W3-C3,
    W3-C9 and every freshness case in this file. It is caught only here, by
    the two shapes of "nothing really changed": no write at all, and a rewrite
    with identical bytes whose mtime is restored to the exact original ns.
    """
    names = _library(books_dir, 1)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    path = books_dir / names[0] / "book.pkl"
    count_unpickles.reset()

    first = server.load_book_cached(names[0])
    before = os.stat(path)

    if shape == "identical_bytes_same_mtime":
        payload = path.read_bytes()
        path.write_bytes(payload)
        os.utime(path, ns=(before.st_mtime_ns, before.st_mtime_ns))
        after = os.stat(path)
        assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size), (
            "the no-op rewrite changed the stat, so this control proves nothing"
        )

    second = server.load_book_cached(names[0])

    assert second is first
    info = server.load_book_cached.cache_info()
    assert (info.hits, info.misses) == (1, 1)
    assert count_unpickles.count == 1


def test_books_dir_is_read_at_call_time_not_at_import_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rewrite_book_pkl,
    merged_loader_cache,
):
    """L4 / S2 (W3-C4) — the module constant is rebound mid-flight, both directions.

    Two libraries hold a directory with the *same* folder name and different
    titles, so a wrapper that baked `BOOKS_DIR` at import time (a
    `functools.partial`, a default argument, a module-level closure) returns
    library A's book for the library-B read. Today's code does exactly that,
    because its key is `folder_name` alone. `server.py:104` already documents
    this hazard for `book_uuid_resolver`; this is the behavioural half of the
    plan's rejection of those three shapes.
    """
    library_a = tmp_path / "lib_a"
    library_b = tmp_path / "lib_b"
    for root, title, ns in (
        (library_a, "Library A book", BASE_NS),
        (library_b, "Library B book", BASE_NS + 1_000_000_000),
    ):
        make_synthetic_library(root, count=1, chapters=2, chapter_chars=200)
        book = make_book(0, chapters=2, chapter_chars=200)
        book.metadata.title = title
        rewrite_book_pkl(root / "synth00_data", book, mtime_ns=ns)

    monkeypatch.setattr(server, "BOOKS_DIR", str(library_a))
    from_a = server.load_book_cached("synth00_data")

    monkeypatch.setattr(server, "BOOKS_DIR", str(library_b))
    from_b = server.load_book_cached("synth00_data")

    monkeypatch.setattr(server, "BOOKS_DIR", str(library_a))
    from_a_again = server.load_book_cached("synth00_data")

    assert from_a.metadata.title == "Library A book"
    assert from_b.metadata.title == "Library B book", (
        "rebinding server.BOOKS_DIR did not change which directory was read — "
        "the directory is baked in somewhere above the cache key"
    )
    assert from_a_again is from_a, "the third read should be a hit on library A's entry"


# ==========================================================================
# W3-C5 / W3-C5x — law 3: totality of the degradation
# ==========================================================================


def _damage(book_dir: Path, shape: str) -> None:
    path = book_dir / "book.pkl"
    if shape == "garbage":
        path.write_bytes(b"\x80\x05not-a-pickle-at-all")
    elif shape == "truncated":
        path.write_bytes(path.read_bytes()[:32])
    elif shape == "missing_pkl":
        path.unlink()
    elif shape == "missing_dir":
        shutil.rmtree(book_dir)
    elif shape == "pkl_is_a_directory":
        path.unlink()
        path.mkdir()
    else:  # pragma: no cover - a typo in the parametrize list must not pass
        raise AssertionError(f"unknown damage shape {shape!r}")


@pytest.mark.parametrize(
    ("shape", "raises", "prints"),
    [
        ("garbage", pickle.UnpicklingError, True),
        ("truncated", pickle.UnpicklingError, True),
        ("missing_pkl", FileNotFoundError, False),
        ("missing_dir", FileNotFoundError, False),
        ("pkl_is_a_directory", IsADirectoryError, True),
    ],
)
def test_the_server_swallows_what_the_core_raises(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    merged_loader_cache,
    shape,
    raises,
    prints,
):
    """L4 / S3 (W3-C5) — five real on-disk damage shapes; the server never raises.

    `pkl_is_a_directory` is the cheap half of the narrow-catch gap and needs no
    injection at all: `os.stat` **succeeds** on a directory, so D2's pre-stat
    passes and `open()` then raises `IsADirectoryError` — a third exception
    type, produced by a filesystem state a half-finished unzip really leaves
    behind.

    **The silence on absence is asserted, not incidental.** Today
    `server.py:355` returns `None` for a missing `book.pkl` without printing,
    because `os.path.exists` precedes the `try`. Under D1-a the stat raises and
    a naive wrapper would print — and D2 makes that path hot, since
    `library_view` hits every `*_data` directory on every homepage request.
    A per-row print would be a per-request log flood. Anyone who decides to
    print instead must edit this case and argue for it.
    """
    names = _library(books_dir, 1)
    book_dir = books_dir / names[0]
    _damage(book_dir, shape)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    capsys.readouterr()

    assert server.load_book_cached(names[0]) is None, (
        f"the server side raised or returned a book for damage shape {shape!r}"
    )

    out = capsys.readouterr().out
    if prints:
        assert "Error loading book" in out and names[0] in out, (
            f"{shape!r} degraded silently; the trace at server.py:363 is gone: {out!r}"
        )
    else:
        assert out == "", f"{shape!r} printed on a path library_view walks every request: {out!r}"

    with pytest.raises(raises):
        search_service.load_book_cached(names[0], str(books_dir))


@given(
    exc_type=st.sampled_from([RuntimeError, MemoryError, OSError, ValueError, RecursionError])
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
def test_the_wrapper_swallows_every_exception_class_not_just_the_two_it_has_seen(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    merged_loader_cache,
    exc_type,
):
    """L4 / S4 (W3-C5x) — **the blind `except Exception` is the specification here.**

    `pyproject.toml` selects `BLE001` on `src/`, and `server.py:362` survives
    that rule only because it carries an explicit `# noqa: BLE001`. The
    likeliest wrong implementation of D1-a is therefore not carelessness but
    *diligence*: an implementer who reads BLE001 and narrows the clause to
    `except (FileNotFoundError, pickle.UnpicklingError)` so the `noqa` can go.
    Every damage shape in W3-C5 and in `test_fixture_damaged_bookdir.py`
    produces exactly those types, so that narrowed wrapper ships green — and
    then the first `MemoryError`, `RecursionError` on a deep TOC, or `OSError`
    (EIO on a failing disk, ENAMETOOLONG, ENOTDIR mid-path) **500s the
    homepage**, because `library_view` calls the loader once per `*_data`
    directory with no pre-check and no per-row guard. One damaged book takes
    the whole library page down.

    The five types are a *sample of an open class*, not the specification: the
    claim is "any `Exception`", and hypothesis is how this case says so rather
    than enumerating. **Anyone deleting the `# noqa: BLE001` must delete this
    test and argue for a 500-on-one-bad-book homepage.**
    """
    names = _library_once(books_dir, 1)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    def raiser(f):
        raise exc_type("injected")

    # Patched at `safe_pickle.safe_load`: the seam guaranteed to be reached
    # however `book_store` imports `load_book_file` (§0.5).
    monkeypatch.setattr(safe_pickle, "safe_load", raiser)
    # Both names, per example. Not belt-and-braces: pre-merge the server name
    # owns a second cache that memoizes the `None` this case produces, so the
    # second example would be served from it and observe no trace at all. That
    # is D2's defect and W3-C8 owns it; this case must be red only for a
    # narrowed `except`.
    book_store.load_book_cached.cache_clear()
    server.load_book_cached.cache_clear()
    capsys.readouterr()

    assert server.load_book_cached(names[0]) is None, (
        f"{exc_type.__name__} propagated out of the server wrapper"
    )
    out = capsys.readouterr().out
    assert names[0] in out, f"{exc_type.__name__} was swallowed without a trace: {out!r}"

    with pytest.raises(exc_type):
        search_service.load_book_cached(names[0], str(books_dir))


# ==========================================================================
# W3-C6 / W3-C7 / W3-C8 — the seam, the surface, and D2
# ==========================================================================


def test_patching_the_server_name_does_not_reach_the_search_path(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch, merged_loader_cache
):
    """L2 / S1 (W3-C6) — D5-a: the two names stay two objects sharing one cache.

    The one-argument lambda **is** the thing under test: it reproduces the six
    existing `monkeypatch.setattr(server, "load_book_cached", ...)` sites, of
    which `test_event_loop_not_blocked.py:532,560,599` are literally this
    shape. Under D5-b the two-argument search call would route through it and
    `TypeError` — which is why the blast radius is measured by calling the
    other name for a real value, not by inspecting objects.
    """
    names = _library(books_dir, 1)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    assert server.load_book_cached is not book_store.load_book_cached, (
        "server.load_book_cached is the shared core itself: patching it would "
        "now silently re-route every search-path call site too"
    )

    sentinel = object()
    monkeypatch.setattr(server, "load_book_cached", lambda folder: sentinel)

    assert server.load_book_cached("anything") is sentinel
    still_real = search_service.load_book_cached(names[0], str(books_dir))
    assert still_real.metadata.title == "Synthetic Book 00"


def test_clearing_through_either_name_empties_the_one_shared_cache(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
):
    """L2->L3 / S2 (W3-C7) — the surface is live on both names and reaches one cache.

    Also protects `tests/contract/test_read_chapter_traversal.py:159`, which
    copies `cache_clear` off the real loader onto a spy. Copying it from a
    *different* cache object, or holding a wrapper-level memo the clear cannot
    reach, is caught by the "really went back to disk" leg: three reads must
    cost three unpickles when each is preceded by a clear.
    """
    names = _library(books_dir, 1)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))

    for attr in ("cache_clear", "cache_info", "cache_parameters"):
        assert callable(getattr(server.load_book_cached, attr, None)), (
            f"server.load_book_cached has no callable {attr}"
        )
    assert server.load_book_cached.cache_parameters()["maxsize"] == 10

    count_unpickles.reset()

    search_service.load_book_cached(names[0], str(books_dir))
    assert server.load_book_cached.cache_info().currsize == 1, (
        "a read through search_service is invisible through the server name"
    )

    server.load_book_cached.cache_clear()
    assert search_service.load_book_cached.cache_info().currsize == 0

    server.load_book_cached(names[0])
    assert search_service.load_book_cached.cache_info().currsize == 1

    search_service.load_book_cached.cache_clear()
    assert server.load_book_cached.cache_info().currsize == 0

    search_service.load_book_cached(names[0], str(books_dir))
    assert count_unpickles.count == 3, (
        f"three reads each preceded by a clear cost {count_unpickles.count} "
        "unpickles; anything less means a clear did not reach the real cache"
    )


def test_a_book_published_after_a_failed_lookup_appears_without_a_restart(
    books_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_unpickles,
    merged_loader_cache,
):
    """L2->L3 / S2 (W3-C8) — D2's specification: the `None` is not memoized.

    A `*_data` directory with no `book.pkl` is the state between `mkdir` and
    the atomic publish. Today's code caches the `None` and the book stays
    invisible until the process restarts. D2 chose to pay one `os.stat` per
    call instead, which is cheap next to the `listdir` `library_view` is
    already doing — and buys "a newly published book appears without a
    restart", the same property (b) exists to add.

    Flipping D2 (memoizing negatives inside the core) requires editing this
    case and saying why.
    """
    pending = books_dir / "pending_data"
    (pending / "images").mkdir(parents=True)
    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    count_unpickles.reset()

    assert server.load_book_cached("pending_data") is None
    assert server.load_book_cached("pending_data") is None
    assert count_unpickles.count == 0, "an absent book.pkl reached the unpickler"
    assert server.load_book_cached.cache_info().currsize == 0, (
        "the negative was memoized: the book will stay invisible until restart"
    )

    book = make_book(7, chapters=2, chapter_chars=200)
    book.metadata.title = "Late Arrival"
    with open(pending / "book.pkl", "wb") as f:
        pickle.dump(book, f)

    published = server.load_book_cached("pending_data")

    assert published is not None, "the newly published book is still invisible"
    assert published.metadata.title == "Late Arrival"
    assert count_unpickles.count == 1
