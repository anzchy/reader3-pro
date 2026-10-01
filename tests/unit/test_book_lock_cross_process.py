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
        # #49: the winner reports only after release, so wait for the 3 losers first,
        # then release, then collect the winner.
        _wait_for_losers([c.result_path for c in children], 3)
        release_evt.set()
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
    books_dir: Path, tmp_path: Path, short_budget: float
) -> None:
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode="shared", holder="notes"):
                pass
        elapsed = time.monotonic() - t0
    assert info.value.holder_category == "import"
    assert book_lock.BUDGET_S - 0.2 <= elapsed < book_lock.BUDGET_S + EPS_S


def test_w2_19_ex_refused_against_a_cross_process_sh_holder_naming_it(books_dir: Path, tmp_path: Path) -> None:
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode="exclusive", holder="delete"):
                pass
        elapsed = time.monotonic() - t0
    assert info.value.holder_category == "reindex"
    assert elapsed < 0.25


@pytest.mark.parametrize("who", ["live", "dead"])
def test_w2_20_a_lock_file_left_behind_is_not_a_held_lock(books_dir: Path, who: str) -> None:
    """W2-01 (fix-up 2, #13): the record is telemetry, never a decision input.

    ``live`` names this test process's own pid -- the partition the old ``999999``
    record never reached (that pid is never alive on macOS), so an EX that refused on
    a live recorded pid used to pass. ``dead`` is a reaped child's pid, carrying the
    old case's coverage over to a pid that is dead on every OS.
    """
    from book_lock_workers import reaped_pid

    pid = os.getpid() if who == "live" else reaped_pid()
    lock_file = _lock_file(books_dir)
    lock_file.parent.mkdir()
    lock_file.write_text(f"import {pid}\n")
    t0 = time.monotonic()
    with book_lock.acquire(str(books_dir), BOOK, mode="exclusive", holder="delete"):
        elapsed = time.monotonic() - t0
    assert elapsed < 0.25
    assert lock_file.exists()
    assert os.path.realpath(book_lock.lock_path(str(books_dir), BOOK)) == os.path.realpath(lock_file)


# --------------------------------------------------------------------------- FX-5 (fix-plan WI-5, #49)
#
# FX-5-04 / FX-5-05 of ``.claude/tdd-guardian/tests-20261001-003726.md``. Law: a
# ``try_exclusive`` winner reports ``"acquired"`` only after it has fully released,
# and a teardown error is ``"error:..."`` with a nonzero exit, never ``"acquired"``.

from book_lock_workers import (  # noqa: E402 - section-local imports keep the W2 block untouched
    AT_CLOSE_SUFFIX,
    probe,
    read_result,
    try_exclusive_close_fails,
)


def _wait_for_losers(paths: list, n: int, timeout: float = CHILD_WAIT_S) -> int:
    """Poll (bounded) until at least ``n`` of ``paths`` hold a ``busy:`` outcome; return how many do."""
    give_up = time.monotonic() + timeout
    while True:
        losers = sum((outcome(read_result(p)) or "").startswith("busy:") for p in paths)
        if losers >= n or time.monotonic() >= give_up:
            return losers
        time.sleep(0.01)


def test_fx_5_04_a_teardown_error_in_the_child_is_an_error_outcome_and_a_nonzero_exit(
    books_dir: Path, tmp_path: Path
) -> None:
    path = str(tmp_path / "close-fails.json")
    child = Child(try_exclusive_close_fails, (str(books_dir), BOOK, "delete", path), path).start()
    code = child.reap(CHILD_TIMEOUT_S)
    got = read_result(path)
    at_close = read_result(path + AT_CLOSE_SUFFIX)

    assert at_close is not None, "the close shim never ran: try_exclusive no longer closes via book_lock.os"
    assert at_close == {"result_existed": False}, "the winner reported before its teardown finished"
    out = outcome(got)
    assert out is not None and out.startswith("error:"), got
    assert "OSError" in out, got
    assert code != 0, f"a teardown error exited {code}"
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


def test_fx_5_05_the_winners_result_file_does_not_exist_while_it_still_holds(
    books_dir: Path, tmp_path: Path
) -> None:
    ctx = spawn_ctx()
    barrier = ctx.Barrier(4)
    release_evt = ctx.Event()
    paths = [str(tmp_path / f"ex-{i}.json") for i in range(4)]
    children = [
        Child(try_exclusive, (str(books_dir), BOOK, "import", p, barrier, release_evt), p).start() for p in paths
    ]
    try:
        losers_at_check = _wait_for_losers(paths, 3)
        acquired_at_check = [p for p in paths if outcome(read_result(p)) == "acquired"]
        absent_at_check = [p for p in paths if not os.path.exists(p)]
        probe_at_check = probe(str(_lock_file(books_dir)), "EX", str(tmp_path))
        release_evt.set()
        results = [c.wait_result(CHILD_WAIT_S) for c in children]
    finally:
        release_evt.set()
        codes = [c.reap(CHILD_TIMEOUT_S) for c in children]

    assert losers_at_check == 3, f"only {losers_at_check} losers reported"
    assert acquired_at_check == [], "the winner reported 'acquired' while it still held the lock"
    assert len(absent_at_check) == 1, f"while the winner still held, {4 - len(absent_at_check)} results existed"
    assert probe_at_check == "blocked"
    assert Counter(outcome(r) for r in results) == Counter({"acquired": 1, "busy:import": 3}), results
    assert codes == [0, 0, 0, 0]


# --------------------------------------------------------------------------- fix-up 2, WI-1 (#21)
#
# W1-01..W1-03 and W1-08 of ``.claude/tdd-guardian/tests-20261001-170000.md``. Law: a
# refusal never names a category that has no live holder. A shared holder clears its
# own record on release, and only its own: across processes the record at most
# degrades to ``unknown``, never to another holder's name.


def _ex_refusal_category(books: Path) -> tuple:
    """One parent-side EX attempt that must be refused; ``(holder_category, elapsed)``."""
    t0 = time.monotonic()
    with pytest.raises(book_lock.BookLockBusy) as info:
        with book_lock.acquire(str(books), BOOK, mode="exclusive", holder="delete"):
            pass
    return info.value.holder_category, time.monotonic() - t0


def test_fu2_w1_01_a_released_sh_holder_is_not_named_by_a_later_ex_refusal(
    books_dir: Path, tmp_path: Path
) -> None:
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        with book_lock.acquire(str(books_dir), BOOK, mode="shared", holder="notes"):
            pass
        category, elapsed = _ex_refusal_category(books_dir)
    assert category != "notes", "#21: the refusal named a shared holder that had already released"
    assert category == "unknown"
    assert elapsed < 0.5


def _ex_child_outcome_while_parent_holds_sh(books: Path, tmp_path: Path, child_category: str) -> tuple:
    """Child A holds SH ``child_category``; the parent takes SH notes, A releases, an EX child tries."""
    a = Holder(str(books), BOOK, "shared", child_category, str(tmp_path)).start()
    try:
        with book_lock.acquire(str(books), BOOK, mode="shared", holder="notes"):
            a_code = a.release()
            path = str(tmp_path / "ex-after-release.json")
            child = Child(try_exclusive, (str(books), BOOK, "delete", path), path).start()
            result = child.wait_result(CHILD_WAIT_S)
            code = child.reap(CHILD_TIMEOUT_S)
    finally:
        a.release()
    return a_code, result, code


def test_fu2_w1_02_release_leaves_another_categorys_record_alone(books_dir: Path, tmp_path: Path) -> None:
    a_code, result, code = _ex_child_outcome_while_parent_holds_sh(books_dir, tmp_path, "reindex")
    assert a_code == 0
    assert outcome(result) == "busy:notes", f"a reindex release cleared the parent's notes record: {result!r}"
    assert result is not None and result["type"] == "BookLockBusy"
    assert code == 0


def test_fu2_w1_03_release_leaves_a_same_category_record_of_another_pid_alone(
    books_dir: Path, tmp_path: Path
) -> None:
    a_code, result, code = _ex_child_outcome_while_parent_holds_sh(books_dir, tmp_path, "notes")
    assert a_code == 0
    assert outcome(result) == "busy:notes", f"a notes release cleared another pid's notes record: {result!r}"
    assert result is not None and result["type"] == "BookLockBusy"
    assert code == 0


def test_fu2_w1_08_a_body_that_raises_still_compares_and_clears_its_record(
    books_dir: Path, tmp_path: Path
) -> None:
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        with pytest.raises(RuntimeError, match="fu2-body-raise"):
            with book_lock.acquire(str(books_dir), BOOK, mode="shared", holder="notes"):
                raise RuntimeError("fu2-body-raise")
        category, elapsed = _ex_refusal_category(books_dir)
    assert category != "notes", "#21: a shared holder whose body raised was still named after release"
    assert category == "unknown"
    assert elapsed < 0.5
