"""018 WI-2 — the per-book lock across processes (ADR-0015 Confirmation target).

Cases W2-15..W2-20 of ``.claude/tdd-guardian/tests-20260930-111748.md``.

Law: ``flock`` mutual exclusion holds across processes; SH is compatible with SH;
death releases the lock; a refusal is typed and names the holder.

Every holder is a real spawned interpreter (``tests/fixtures/book_lock_workers.py``)
and every child's ``exitcode`` is asserted, so a child that died on import is a red.
"""

from __future__ import annotations

import os
import signal
import time
from collections import Counter
from pathlib import Path

import pytest

from book_lock_workers import (
    CHILD_TIMEOUT_S,
    CHILD_WAIT_S,
    Child,
    Holder,
    hold_at_barrier,
    hold_forever,
    outcome,
    spawn_ctx,
    try_exclusive,
)
from reader3_app import book_lock

BUDGET_S = 2.0
EPS_S = 0.75
BOOK = "x_data"


def _lock_file(books: Path, folder: str = BOOK) -> Path:
    return books / ".locks" / f"{folder}.lock"


def test_w2_15_ex_vs_ex_across_processes_exactly_one_winner(books_dir: Path, tmp_path: Path) -> None:
    ctx = spawn_ctx()
    barrier = ctx.Barrier(4)
    release_evt = ctx.Event()
    children = []
    for i in range(4):
        path = str(tmp_path / f"ex-{i}.json")
        children.append(
            Child(try_exclusive, (str(books_dir), BOOK, "import", path, barrier, release_evt), path).start()
        )
    try:
        results = [c.wait_result(CHILD_WAIT_S) for c in children]
    finally:
        release_evt.set()
        codes = [c.reap(CHILD_TIMEOUT_S) for c in children]

    outcomes = Counter(outcome(r) for r in results)
    assert outcomes == Counter({"acquired": 1, "busy:import": 3}), results
    for r in results:
        if outcome(r) == "busy:import":
            assert r["type"] == "BookLockBusy"
            assert isinstance(r["retry_after"], int) and r["retry_after"] >= 1
            assert r["is_runtime_error"] is False
    assert codes == [0, 0, 0, 0]
    assert _lock_file(books_dir).exists()


def test_w2_16_a_sigkilled_holder_releases_immediately(books_dir: Path) -> None:
    ctx = spawn_ctx()
    ready = ctx.Event()
    proc = ctx.Process(target=hold_forever, args=(str(books_dir), BOOK, "exclusive", "import", ready), daemon=True)
    proc.start()
    try:
        give_up = time.monotonic() + CHILD_WAIT_S
        while not ready.wait(0.05) and proc.is_alive() and time.monotonic() < give_up:
            pass
        assert ready.is_set(), f"holder never became ready (exitcode={proc.exitcode})"
        inode = os.stat(_lock_file(books_dir)).st_ino
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(CHILD_TIMEOUT_S)
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(5)
    assert proc.exitcode == -signal.SIGKILL

    t0 = time.monotonic()
    with book_lock.acquire(str(books_dir), BOOK, mode="exclusive", holder="delete"):
        elapsed = time.monotonic() - t0
    assert elapsed < 0.25
    assert os.stat(_lock_file(books_dir)).st_ino == inode


def test_w2_17_sh_and_sh_across_processes_hold_at_once(books_dir: Path, tmp_path: Path) -> None:
    ctx = spawn_ctx()
    barrier = ctx.Barrier(2)
    children = []
    for i, holder in enumerate(("notes", "reindex")):
        path = str(tmp_path / f"sh-{i}.json")
        children.append(
            Child(hold_at_barrier, (str(books_dir), BOOK, "shared", holder, barrier, path), path).start()
        )
    results = [c.wait_result(CHILD_WAIT_S) for c in children]
    codes = [c.reap(CHILD_TIMEOUT_S) for c in children]
    assert [outcome(r) for r in results] == ["passed-barrier", "passed-barrier"], results
    assert codes == [0, 0]


def test_w2_18_sh_against_a_cross_process_ex_holder_refused_within_one_budget(
    books_dir: Path, tmp_path: Path
) -> None:
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode="shared", holder="notes"):
                pass
        elapsed = time.monotonic() - t0
    assert info.value.holder_category == "import"
    assert BUDGET_S - 0.2 <= elapsed < BUDGET_S + EPS_S


def test_w2_19_ex_refused_against_a_cross_process_sh_holder_naming_it(books_dir: Path, tmp_path: Path) -> None:
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode="exclusive", holder="delete"):
                pass
        elapsed = time.monotonic() - t0
    assert info.value.holder_category == "reindex"
    assert elapsed < 0.25


def test_w2_20_a_lock_file_left_behind_is_not_a_held_lock(books_dir: Path) -> None:
    lock_file = _lock_file(books_dir)
    lock_file.parent.mkdir()
    lock_file.write_text("import 999999\n")
    t0 = time.monotonic()
    with book_lock.acquire(str(books_dir), BOOK, mode="exclusive", holder="delete"):
        elapsed = time.monotonic() - t0
    assert elapsed < 0.25
    assert lock_file.exists()
    assert os.path.realpath(book_lock.lock_path(str(books_dir), BOOK)) == os.path.realpath(lock_file)
