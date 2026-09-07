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
