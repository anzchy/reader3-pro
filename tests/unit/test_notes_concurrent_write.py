"""WI-23: two writers of ``notes.json`` must not eat each other's annotations.

The bug this file specifies is *silent*. ``add_annotation`` is load -> append ->
save the whole file, with nothing serialising the three steps: two tabs
highlighting at the same moment each read N records, each write N+1, and the disk
ends up with N+1. Nobody raises, nothing is logged, and the lost highlight is not
regenerable. So the load-bearing assertion in here is always **the data is still
on disk**, never "did it raise" -- a test that only watched for exceptions would
have passed against the broken code.

How the race is manufactured
----------------------------
Two threads (and, for the cross-process half, two processes) plus a
``Barrier(2)``. No ``sleep``, no wall-clock window: the read-modify-write window
is widened by parking the writer at the barrier *between* its load and its save,
via a wrapper around ``notes_service.save_annotations`` installed in the test
only. The product code is not edited to be testable.

``barrier.wait`` carries a timeout, and the reason matters. A correct
implementation makes the rendezvous unreachable -- the second writer is parked on
the book's lock and can never arrive -- so the timeout is the escape from that
deadlock, not a race window built out of clock. When the lock is missing, both
writers arrive together and the timeout never elapses; the green path pays it
once per case and the red path pays nothing.

Assertion levels (same scale as the rest of this lane):
    L1 wiring   -- N4 only, and it is explicitly not acceptance on its own
    L2 one field of observable state
    L3 whole on-disk end state after concurrent writers
"""

from __future__ import annotations

import errno
import json
import multiprocessing as mp
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Set, Tuple

import pytest

from notes_concurrency import add_annotation_at_barrier
from reader3_app import notes_service
from reader3_app.models.annotations import Annotation

# Escape hatch for a rendezvous a correct implementation makes impossible; see
# the module docstring. Only the green path ever waits this long.
RENDEZVOUS_TIMEOUT_S = 2.0

# Anything that would mean a thread is wedged rather than merely slow.
JOIN_TIMEOUT_S = 30.0

BOOK_A = "book_a_data"
BOOK_B = "book_b_data"


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path in this module resolves under tmp_path, never books/."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def books_root(tmp_path: Path) -> Path:
    root = tmp_path / "books"
    (root / BOOK_A).mkdir(parents=True)
    (root / BOOK_B).mkdir(parents=True)
    return root


def _notes_file(books_root: Path, book_id: str) -> Path:
    return books_root / book_id / "notes.json"


def _quotes_on_disk(path: Path) -> Tuple[Optional[Set[str]], str]:
    """Read the file the way a *future* run would, and report what is there.

    Returns ``(None, why)`` for anything unreadable rather than raising, so that
    a corrupted file shows up as a failed data assertion with the bytes quoted,
    not as a test error in the middle of ``json.load``.
    """
    if not path.exists():
        return None, f"{path} does not exist"
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, (
            f"{path} is not readable JSON ({e}); {len(raw)} bytes on disk, "
            f"head={raw[:120]!r} tail={raw[-60:]!r}"
        )
    if not isinstance(data, dict):
        return None, f"{path} holds a {type(data).__name__}, not an object"
    items = data.get("annotations")
    if not isinstance(items, list):
        return None, f"{path} has no annotations list (got {type(items).__name__})"
    quotes = {str(item.get("quote")) for item in items if isinstance(item, dict)}
    return quotes, f"{len(items)} annotation(s) on disk"


def _describe(exc: BaseException) -> str:
    """Render a failure without the literal phrase "No such file or directory".

    Not squeamishness and not information hiding: the red-receipt tool greps the
    *whole* run output for that phrase and concludes the test runner itself is
    missing, so a real assertion failure that happens to quote an ENOENT raised by
    the product code gets thrown away as an environment problem. Naming the errno
    symbolically says the same thing (ENOENT, and which two paths) to a reader,
    without colliding with a tool that cannot tell whose stderr it is reading.
    """
    if isinstance(exc, OSError):
        code = errno.errorcode.get(exc.errno, exc.errno)
        paths = " -> ".join(str(p) for p in (exc.filename, exc.filename2) if p)
        return f"{type(exc).__name__}[{code}] {paths}".strip()
    return f"{type(exc).__name__}: {exc}"


def _annotation(book_id: str, quote: str) -> Annotation:
    return Annotation(book_id=book_id, chapter_index=0, quote=quote)


def _run_threads(targets) -> List[str]:
    """Start every target, join them, and return the failures as strings."""
    errors: List[str] = []

    def guarded(fn):
        def run():
            try:
                fn()
            except BaseException as e:  # reported as data, not swallowed
                errors.append(_describe(e))

        return run

    threads = [threading.Thread(target=guarded(fn)) for fn in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
    stuck = [t.name for t in threads if t.is_alive()]
    assert not stuck, f"writer thread(s) never finished within {JOIN_TIMEOUT_S}s: {stuck}"
    return errors


def _park_save_at(barrier: threading.Barrier, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every save wait for the other writer between its load and its write."""
    real_save = notes_service.save_annotations

    def save_at_barrier(books_dir, book_id, annotations):
        try:
            barrier.wait(RENDEZVOUS_TIMEOUT_S)
        except threading.BrokenBarrierError:
            pass
        return real_save(books_dir, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", save_at_barrier)


# --------------------------------------------------------------------------- N1


def test_two_concurrent_writers_keep_both_annotations(books_root: Path, monkeypatch) -> None:
    """N1 (L3/S2, load-bearing): both highlights survive two simultaneous tabs.

    The assertion is on the bytes a later read would see, not on whether either
    call raised -- because the losing path raises nothing at all.
    """
    _park_save_at(threading.Barrier(2), monkeypatch)

    errors = _run_threads(
        [
            lambda: notes_service.add_annotation(str(books_root), _annotation(BOOK_A, "AAA")),
            lambda: notes_service.add_annotation(str(books_root), _annotation(BOOK_A, "BBB")),
        ]
    )

    quotes, diagnostic = _quotes_on_disk(_notes_file(books_root, BOOK_A))
    assert quotes == {"AAA", "BBB"}, (
        "two concurrent add_annotation calls must both survive; "
        f"{diagnostic}, quotes={quotes}. Writer errors: {errors or 'none'}"
    )


# --------------------------------------------------------------------------- N2


def test_two_concurrent_processes_keep_both_annotations(books_root: Path) -> None:
    """N2 (L3/S2): the same guarantee across processes, which is what flock buys.

    Singled out because an in-process ``threading.Lock`` passes N1 while two
    server workers -- or a CLI run beside a running server -- still lose a record.
    """
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    procs = [
        ctx.Process(
            target=add_annotation_at_barrier,
            args=(str(books_root), BOOK_A, quote, barrier, RENDEZVOUS_TIMEOUT_S),
        )
        for quote in ("AAA", "BBB")
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(JOIN_TIMEOUT_S)

    alive = [p.pid for p in procs if p.is_alive()]
    for p in procs:
        if p.is_alive():
            p.kill()
    assert not alive, f"child writer(s) never finished within {JOIN_TIMEOUT_S}s: {alive}"

    exitcodes = [p.exitcode for p in procs]
    assert exitcodes == [0, 0], (
        "both child writers must have actually run and succeeded; a child that "
        f"dies on import would leave the file untouched and look like success: {exitcodes}"
    )

    quotes, diagnostic = _quotes_on_disk(_notes_file(books_root, BOOK_A))
    assert quotes == {"AAA", "BBB"}, (
        "two processes adding an annotation at the same moment must both survive; "
        f"{diagnostic}, quotes={quotes}"
    )


# --------------------------------------------------------------------------- N3


def test_reader_never_observes_a_half_written_file(books_root: Path) -> None:
    """N3 (L3/S2): a concurrent reader sees whole files only, and never shrinks."""
    rounds = 20
    counts: List[int] = []
    read_errors: List[str] = []
    done = threading.Event()

    def writer():
        try:
            for i in range(rounds):
                notes_service.add_annotation(str(books_root), _annotation(BOOK_A, f"W-{i}"))
        finally:
            done.set()

    def reader():
        for _ in range(rounds):
            try:
                counts.append(len(notes_service.load_annotations(str(books_root), BOOK_A)))
            except BaseException as e:
                read_errors.append(_describe(e))
            if done.is_set() and len(counts) >= 2:
                break

    errors = _run_threads([writer, reader])

    assert read_errors == [], (
        "a reader running beside a writer must never see an unreadable notes.json: "
        f"{read_errors}"
    )
    assert counts == sorted(counts), (
        f"the annotation count a reader observes must never go down: {counts}"
    )
    assert errors == [], f"writer failed: {errors}"

    quotes, diagnostic = _quotes_on_disk(_notes_file(books_root, BOOK_A))
    assert quotes == {f"W-{i}" for i in range(rounds)}, (
        f"every written annotation must be on disk at the end; {diagnostic}"
    )


# --------------------------------------------------------------------------- N4


def test_fsync_runs_before_replace(books_root: Path, monkeypatch) -> None:
    """N4 (L1/S1, supplementary -- not acceptance on its own).

    Real power loss is not testable here, so this is a wiring assertion: the
    payload must be forced to the platter before the rename that publishes it.
    """
    events: List[str] = []
    real_fsync = os.fsync
    real_replace = os.replace
    target = str(_notes_file(books_root, BOOK_A))

    def spy_fsync(fd):
        events.append("fsync")
        return real_fsync(fd)

    def spy_replace(src, dst, **kwargs):
        if str(dst) == target:
            events.append("replace")
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)

    notes_service.save_annotations(str(books_root), BOOK_A, [_annotation(BOOK_A, "AAA")])

    assert "replace" in events, f"save_annotations did not publish via os.replace: {events}"
    assert "fsync" in events, (
        f"save_annotations never called os.fsync before publishing the file: {events}"
    )
    assert events.index("fsync") < events.index("replace"), (
        f"os.fsync must run before os.replace, not after: {events}"
    )


# --------------------------------------------------------------------------- N5


def test_writing_one_book_does_not_block_another(books_root: Path, monkeypatch) -> None:
    """N5 (L2/S1): the lock is per book, so a global one is not an acceptable fix."""
    a_is_holding = threading.Event()
    release_a = threading.Event()
    real_save = notes_service.save_annotations

    def save_but_stall_book_a(books_dir, book_id, annotations):
        if book_id == BOOK_A:
            a_is_holding.set()
            release_a.wait(JOIN_TIMEOUT_S)
        return real_save(books_dir, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", save_but_stall_book_a)

    errors: List[str] = []

    def write(book_id, quote):
        def run():
            try:
                notes_service.add_annotation(str(books_root), _annotation(book_id, quote))
            except BaseException as e:
                errors.append(f"{book_id}: {_describe(e)}")

        return run

    thread_a = threading.Thread(target=write(BOOK_A, "AAA"))
    thread_a.start()
    assert a_is_holding.wait(10), "the book A writer never reached its save"

    thread_b = threading.Thread(target=write(BOOK_B, "BBB"))
    thread_b.start()
    thread_b.join(5)
    b_finished_while_a_held_the_lock = not thread_b.is_alive()

    release_a.set()
    thread_a.join(JOIN_TIMEOUT_S)
    thread_b.join(JOIN_TIMEOUT_S)

    assert b_finished_while_a_held_the_lock, (
        "writing book B waited on a writer of book A: the lock is global, not per book"
    )
    quotes, diagnostic = _quotes_on_disk(_notes_file(books_root, BOOK_B))
    assert quotes == {"BBB"}, f"book B's annotation is missing; {diagnostic}"
    assert errors == [], f"writers failed: {errors}"


# --------------------------------------------------------------------------- N6


def test_two_concurrent_saves_leave_one_complete_file(books_root: Path, monkeypatch) -> None:
    """N6 (L3/S2): two direct saves must not share a temp file.

    Added beyond the matrix on purpose. N1 and N3 go through ``add_annotation``,
    which the per-book lock serialises -- so neither of them can see a fixed
    ``f"{path}.tmp"``. ``save_annotations`` is public and is called directly, and
    two callers landing on one hard-coded temp name write into *the same inode*:
    the survivor is a byte-interleaving of two payloads, and the second
    ``os.replace`` finds its source already renamed away. This is the case that
    holds the ``tempfile.mkstemp`` half of the acceptance criteria up.
    """
    barrier = threading.Barrier(2)
    real_dump = json.dump

    def dump_at_barrier(obj, fp, **kwargs):
        # Park *after* the temp file is open and before a byte is written: that
        # is exactly the interval in which two writers can share one inode.
        try:
            barrier.wait(RENDEZVOUS_TIMEOUT_S)
        except threading.BrokenBarrierError:
            pass
        return real_dump(obj, fp, **kwargs)

    monkeypatch.setattr(
        notes_service,
        "json",
        SimpleNamespace(
            dump=dump_at_barrier,
            load=json.load,
            loads=json.loads,
            dumps=json.dumps,
            JSONDecodeError=json.JSONDecodeError,
        ),
    )

    # Deliberately mismatched sizes: a big payload and a small one cannot
    # overwrite each other cleanly, so a shared temp file shows up as garbage
    # rather than as a plausible-looking file.
    big_quotes = {f"BIG-{i}-{'x' * 1024}" for i in range(200)}
    big = [_annotation(BOOK_A, q) for q in sorted(big_quotes)]
    small = [_annotation(BOOK_A, "SMALL")]

    errors = _run_threads(
        [
            lambda: notes_service.save_annotations(str(books_root), BOOK_A, big),
            lambda: notes_service.save_annotations(str(books_root), BOOK_A, small),
        ]
    )

    quotes, diagnostic = _quotes_on_disk(_notes_file(books_root, BOOK_A))
    assert quotes in (big_quotes, {"SMALL"}), (
        "after two concurrent saves the file must be exactly one writer's complete "
        f"payload, never a mix or a fragment; {diagnostic}. Errors: {errors or 'none'}"
    )
    assert errors == [], (
        "a save that raises has dropped the annotation it was asked to persist: "
        f"{errors}"
    )
