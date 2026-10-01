"""Unit-lane fixtures.

The EPUB-reprocessing fixtures below came first and still make up most of this
file, but the lane has long since outgrown them: it now also holds the server
patch-seam locks, the AI-stub contract tests and the lane-wide egress backstop.
Read the fixture docstrings, not this header, for what each one covers.

Three autouse fences run around **every** test in this lane. They are
deliberately separate, because each one fails in a way the others cannot see:

1. ``_never_touch_the_real_books_dir`` — detects damage to the developer's
   library after the fact (recursive tree comparison).
2. ``_process_epub_refuses_the_real_library`` — blocks that same damage at the
   call site, before it happens.
3. ``_no_real_egress`` — blocks (and records) any real TCP ``connect``.
   The gate body is shared, not copied: it lives in ``tests/unit/egress_guard.py``
   so that ``tests/contract/conftest.py`` and the synthetic tree
   ``tests/unit/test_egress_backstop_subprocess.py`` drives in a child
   interpreter all install *the same* gate. A copy would make those tests
   evidence about the copy.

What the egress fence does **not** reach (documented holes, not oversights;
``tests/unit/test_egress_backstop_unit.py`` pins ``connect_ex`` as a red/green
fact so that widening the gate has to be a deliberate edit):

* egress at import / collection time — the fence is a function-scoped fixture
  and is not installed yet;
* egress inside the setup of a higher-scoped (session/module) fixture — same
  reason;
* child interpreters started with ``subprocess`` — the patch is per-process;
* ``socket.socket.connect_ex``, UDP ``sendto`` and ``socket.getaddrinfo`` —
  separate methods that never route through ``connect``.

A test that genuinely needs a real loopback socket carries
``@pytest.mark.real_loopback_socket``. That exemption list is itself locked by
``EXPECTED_EXEMPTIONS`` in ``tests/unit/test_egress_backstop_unit.py``.

Assertion levels used across this lane (defined in
`.claude/tdd-guardian/plan-20260816T122646Z.md`; there is no policy-core file
in this repo):

    L1 wiring/smoke - not used, no case in this lane stops here
    L2 return value, or a single field of on-disk state
    L3 whole-tree observable end state (sha256 + size + mtime_ns + inode)
    L4 fault injection / invariant under an interrupted run
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pytest

import egress_guard
from bookdir import make_seeded_book_dir
from epub_builder import build_imageless, build_v1, build_v2, snapshot_tree


def shallow_tree(root: Path) -> Dict[str, Tuple[int, int, int]]:
    """Map every path under ``root`` to ``(size, mtime_ns, inode)``, recursively.

    Deliberately hash-free: the real library holds tens of megabytes of EPUBs
    and this runs around every test. Size + mtime_ns + inode still catches a
    deleted ``notes.json``, a rewritten ``book.pkl``, or a recreated
    ``images/`` — which a top-level ``os.listdir`` of ``books/`` does not.
    """
    tree: Dict[str, Tuple[int, int, int]] = {}
    if not root.exists():
        return tree
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                tree[rel] = (-1, -1, -1)
                continue
            tree[rel] = (st.st_size, st.st_mtime_ns, st.st_ino)
    return tree


@pytest.fixture(scope="session")
def _real_books_baseline(repo_root: Path) -> Tuple[bool, Dict[str, Tuple[int, int, int]]]:
    """Walk the developer's real library once per session, not twice per test.

    A per-test "before" would be O(tests x library), and a working library holds
    a ``chroma_db/`` of thousands of small files per book. One baseline is just
    as strong: nothing in this lane is allowed to change ``books/`` at any point,
    so every test may be compared against the same starting state.
    """
    real_books = repo_root / "books"
    return real_books.exists(), shallow_tree(real_books)


@pytest.fixture(autouse=True)
def _never_touch_the_real_books_dir(repo_root: Path, _real_books_baseline):
    """Fail loudly if any test in this lane disturbs the developer's library.

    The bug under test destroys real annotations. A test that accidentally
    pointed at the real ``books/`` would do exactly the same damage, so the
    whole lane is fenced -- recursively, because the damage this fence exists
    to catch happens *inside* ``books/{name}_data/`` and changes neither the
    top-level listing nor ``books/``'s own mtime.
    """
    real_books = repo_root / "books"
    existed, before = _real_books_baseline

    yield

    assert real_books.exists() == existed, "the real books/ directory appeared or vanished"
    after = shallow_tree(real_books)
    if after != before:
        changed = sorted(
            set(before) ^ set(after)
            | {p for p in set(before) & set(after) if before[p] != after[p]}
        )
        raise AssertionError(
            f"the real books/ directory was modified during a test: {changed[:20]}"
        )


@pytest.fixture(autouse=True)
def _process_epub_refuses_the_real_library(repo_root: Path):
    """Block the damage before it happens, not just detect it afterwards.

    The recursive fence above notices a violation only once the annotations are
    already gone. This one raises at the call. It replaces an earlier check on
    ``READER3_BOOKS_DIR`` that could never fire: that check ran in a fixture
    finalizer, by which point ``monkeypatch`` had already restored the
    environment and the variable was always unset.

    Reach: it rebinds the name in the ``reader3`` module, so it covers the CLI
    path (``main`` resolves ``process_epub`` in that namespace) and every
    fixture that seeds through ``reader3.process_epub``. Test modules that
    imported the function directly call the original, which is why the
    recursive fence above stays as the catch-all.
    """
    from reader3_app import reader3

    real_books = (repo_root / "books").resolve()
    real_process_epub = reader3.process_epub

    def guarded(epub_path, output_dir, *a, **kw):
        resolved = Path(output_dir).resolve()
        assert real_books not in resolved.parents and resolved != real_books, (
            f"a test tried to process a book into the real library: {resolved}"
        )
        return real_process_epub(epub_path, output_dir, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3, "process_epub", guarded)
        yield


@pytest.fixture
def egress_violations(request: pytest.FixtureRequest) -> List[Tuple[str, str, str]]:
    """This test's ledger of attempted real TCP connections."""
    return egress_guard.egress_violations(request)


@pytest.fixture(autouse=True)
def _no_real_egress(request: pytest.FixtureRequest, egress_violations):
    """The third autouse fence: no test in this lane opens a real TCP connection.

    Registration is duplicated in ``tests/contract/conftest.py`` because the one
    place that would cover both directories is ``tests/conftest.py``, a frozen
    ``suite_hash`` path. The *body* is not duplicated — see ``egress_guard``.

    ``yield from`` is load-bearing. ``next(gen); yield`` would never resume the
    generator, so the teardown assertion inside the gate would never be
    evaluated, and every swallowed egress would pass silently. Every case in
    ``test_egress_backstop_unit.py`` that reads the ledger clears it in the test
    body, so those cases cannot tell the two spellings apart; the child-process
    case ``test_the_lane_conftest_itself_reddens_at_teardown`` is what can.
    """
    yield from egress_guard.no_real_egress(request, egress_violations)


@pytest.fixture
def epub_v1(tmp_path: Path) -> Path:
    return build_v1(tmp_path / "sources" / "v1.epub")


@pytest.fixture
def epub_v2(tmp_path: Path) -> Path:
    return build_v2(tmp_path / "sources" / "v2.epub")


@pytest.fixture
def epub_imageless(tmp_path: Path) -> Path:
    """A plain-text book: no ITEM_IMAGE, so the staged images/ dir stays empty."""
    return build_imageless(tmp_path / "sources" / "plain.epub")


@pytest.fixture
def snapshot() -> Callable[[Path | str], Dict[str, Tuple[str, int, int, int]]]:
    return snapshot_tree


@pytest.fixture
def seeded_book_dir(books_dir: Path, epub_v1: Path) -> Path:
    return make_seeded_book_dir(books_dir, epub_v1)


# --- book_store loader helpers (011 §4 / WI-1) -----------------------------
#
# Two helpers the `book_store` cases share. `merged_loader_cache` from the test
# matrix's §0.5 is deliberately absent: it asserts that `search_service` and
# `book_store` share one cache, which is only true after WI-2 lands. Adding it
# now would either fail or have to be written tolerantly, and a tolerant
# fixture is not evidence of the sharing it exists to prove.


class UnpickleSpy:
    """A counting passthrough over the *real* ``safe_pickle.safe_load``.

    This is a spy, not a mock: the allow-listed unpickle still runs and its
    result is returned unchanged. ``before`` is an optional hook the
    concurrency case uses to park two threads inside the load at once.

    The lock is load-bearing. ``self.count += 1`` from two threads can lose an
    increment, which would make the forced-interleaving case flake green.
    """

    def __init__(self) -> None:
        self.count = 0
        self.before = None
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.count = 0


@pytest.fixture
def count_unpickles(monkeypatch: pytest.MonkeyPatch) -> UnpickleSpy:
    """Count every read that reaches the shared unpickler.

    Patched at ``safe_pickle.safe_load`` on purpose. ``safe_pickle.load_book_file``
    resolves ``safe_load`` as a module global at call time, so any loader that
    imports ``load_book_file`` is visible here; a loader that did
    ``from .safe_pickle import safe_load`` would not be, and the count would
    read 0. That is the failure this seam is chosen to expose.
    """
    from reader3_app import safe_pickle

    spy = UnpickleSpy()
    real_safe_load = safe_pickle.safe_load

    def counting(f):
        with spy._lock:
            spy.count += 1
        hook = spy.before
        if hook is not None:
            hook()
        return real_safe_load(f)

    monkeypatch.setattr(safe_pickle, "safe_load", counting)
    return spy


@pytest.fixture
def rewrite_book_pkl():
    """Pickle ``book`` over ``{book_dir}/book.pkl`` at an exact forced ``mtime_ns``.

    Returns the read-back ``(st_mtime_ns, st_size)`` and asserts the forced
    mtime really landed (matrix §0.4 rule 2). A filesystem that truncates
    nanoseconds must fail here, loudly, rather than let a cache-invalidation
    case pass vacuously.
    """
    import pickle as _pickle

    def rewrite(book_dir, book, *, mtime_ns: int):
        path = Path(book_dir) / "book.pkl"
        with open(path, "wb") as f:
            _pickle.dump(book, f)
        os.utime(path, ns=(mtime_ns, mtime_ns))
        st = os.stat(path)
        assert st.st_mtime_ns == mtime_ns, (
            f"the filesystem did not keep the forced mtime: asked for {mtime_ns}, "
            f"read back {st.st_mtime_ns}. Nanosecond resolution is a precondition "
            "for every invalidation case in this file."
        )
        return (st.st_mtime_ns, st.st_size)

    return rewrite


@pytest.fixture
def merged_loader_cache():
    """Empty the one shared loader cache before and after, clearing via `book_store`.

    Post-merge (011 §4, WI-2) `search_service.load_book_cached` *is*
    `book_store.load_book_cached`, so clearing either name is enough. The
    fixture clears through one name and asserts the emptiness through the
    other, which makes it prove the sharing it depends on rather than assume
    it: before WI-2 lands, the teardown check fails on any test that warmed the
    cache through `search_service`.

    Both ends matter. The *before* clear stops a neighbouring test's warm book
    from turning a miss into a hit here; the *after* clear stops this file's
    books — which live under `tmp_path` and are deleted — from sitting in a
    cache that `test_fixture_synthetic_library.py` counts exactly.
    """
    from reader3_app import book_store, search_service

    def clear_through_book_store_and_check(when: str) -> None:
        book_store.load_book_cached.cache_clear()
        currsize = search_service.load_book_cached.cache_info().currsize
        assert currsize == 0, (
            f"{when}: clearing book_store.load_book_cached left "
            f"search_service.load_book_cached holding {currsize} entries. The two "
            "names are not the same object, so WI-2's one-cache premise is false."
        )

    clear_through_book_store_and_check("setup")
    yield
    clear_through_book_store_and_check("teardown")


#: The patched book-lock budget ``short_budget`` installs (fix-plan WI-5, #9-#11).
SHORT_BUDGET_S = 0.3


@pytest.fixture
def short_budget(monkeypatch: pytest.MonkeyPatch) -> float:
    """Patch ``book_lock.BUDGET_S`` to 0.3 s for this test; returns the patched value.

    For tests whose subject is a *refusal*, not the 2 s default: ``acquire`` reads
    ``BUDGET_S`` at call time, so a refusal lands in ~0.3 s instead of ~2 s. Bounds in
    those tests read ``book_lock.BUDGET_S``, never a local copy of the default.

    Deliberately NOT used where the subject is a real short deadline (the
    ``_book_uuid_or_none`` / scan / page timing cases and FX-4-03, which assert
    ``book_lock.BUDGET_S >= 1.0``) or the default itself (W2-14a, FX-5-08).
    """
    from reader3_app import book_lock

    monkeypatch.setattr(book_lock, "BUDGET_S", SHORT_BUDGET_S)
    return SHORT_BUDGET_S
