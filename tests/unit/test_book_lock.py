"""018 WI-2 — the per-book lock, in-process semantics (ADR-0015, contract items 2/4/7).

Cases W2-01..W2-14 and W2-53 of ``.claude/tdd-guardian/tests-20260930-111748.md``.

Law:
  * SH is compatible with SH; EX excludes everything;
  * a lock stays held while any acquisition is live and is released on every exit
    path, exceptions included;
  * the same thread can neither re-enter nor upgrade; order is book → resource;
  * one monotonic deadline bounds every wait across all three layers
    (in-process RW, the book flock, the resource lock);
  * the lock file is created at most once and never unlinked;
  * the lock never creates the book dir.

Locks, files, threads and child processes are all real. The only substitution in
this file is time itself (``book_lock._monotonic`` / ``book_lock._sleep``), and only
in W2-13, which is what makes "one deadline across layers" checkable to the tick.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from book_lock_workers import (
    CHILD_WAIT_S,
    Child,
    Holder,
    acquire_ex_when_free,
    outcome,
    probe,
)
from reader3_app import book_lock, notes_service
from reader3_app.models.annotations import Annotation

BUDGET_S = 2.0
EPS_S = 0.75
JOIN_TIMEOUT_S = 30.0
#: How long a parked writer 1 waits before giving up and finishing on its own. It is
#: past the 2 s budget with margin, so a waiter that blocks instead of being refused
#: lets writer 1 complete -- and then fails on its own assertion -- instead of hanging.
PARK_GUARD_S = 5.0
CHILD_TIMEOUT_S = 60.0

#: W2-13 windows (addendum, gap A): a fixed slack instead of the poll interval.
FAKE_SLACK_S = 0.25

SH = "shared"
EX = "exclusive"
BOOK = "x_data"
CATEGORIES = {"import", "delete", "reindex", "notes", "ai_meta", "conversations"}


# --------------------------------------------------------------------------- helpers


def _lock_file(books: Path, folder: str = BOOK) -> Path:
    return books / ".locks" / f"{folder}.lock"


class Held:
    """A thread that holds a book lock until ``release()``."""

    def __init__(self, books: Path, mode: str, holder: str, folder: str = BOOK) -> None:
        self.ready = threading.Event()
        self._go = threading.Event()
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, args=(str(books), folder, mode, holder), daemon=True)

    def _run(self, books: str, folder: str, mode: str, holder: str) -> None:
        try:
            with book_lock.acquire(books, folder, mode=mode, holder=holder):
                self.ready.set()
                self._go.wait(JOIN_TIMEOUT_S)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            self.error = exc
            self.ready.set()

    def start(self) -> "Held":
        self.thread.start()
        assert self.ready.wait(JOIN_TIMEOUT_S), "holder thread never became ready"
        assert self.error is None, f"holder thread failed to acquire: {self.error!r}"
        return self

    def release(self) -> None:
        self._go.set()
        self.thread.join(JOIN_TIMEOUT_S)
        assert not self.thread.is_alive(), "holder thread deadlocked on release"


def _run_in_thread(fn: Callable[[], Any], timeout: float = JOIN_TIMEOUT_S) -> Dict[str, Any]:
    box: Dict[str, Any] = {}

    def body() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
            box["error"] = exc

    t = threading.Thread(target=body, daemon=True)
    t.start()
    t.join(timeout)
    box["alive"] = t.is_alive()
    return box


def _quotes(books: Path, folder: str = BOOK) -> set:
    path = books / folder / notes_service.NOTES_FILENAME
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {a["quote"] for a in data.get("annotations") or []}


def _ann(quote: str, folder: str = BOOK) -> Annotation:
    return Annotation(book_id=folder, chapter_index=0, quote=quote)


# --------------------------------------------------------------------------- W2-01..W2-12


def test_w2_01_sh_sh_coexist_in_process(books_dir: Path) -> None:
    barrier = threading.Barrier(2)
    outcomes: List[str] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                barrier.wait(timeout=5)
                result = "passed-barrier"
        except BaseException as exc:  # noqa: BLE001
            result = f"error:{type(exc).__name__}:{exc}"
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
    assert not any(t.is_alive() for t in threads)
    assert outcomes == ["passed-barrier", "passed-barrier"]
    assert _lock_file(books_dir).exists()


def test_w2_02_and_w2_12_in_process_ex_refused_while_sh_held(books_dir: Path, tmp_path: Path) -> None:
    a = Held(books_dir, SH, "reindex").start()
    try:
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode=EX, holder="delete"):
                pass
        elapsed = time.monotonic() - t0
        exc = info.value

        assert elapsed < 0.25, f"EX must never wait, took {elapsed:.3f}s"
        assert exc.holder_category == "reindex"
        # W2-12: the payload and the type contract.
        assert isinstance(exc.retry_after, int) and exc.retry_after >= 1
        assert not isinstance(exc, RuntimeError)
        assert exc.holder_category in CATEGORIES
        assert exc.holder_category in str(exc)

        assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "blocked"
    finally:
        a.release()


def test_w2_03_sh_waits_on_in_process_ex_and_succeeds_on_release(books_dir: Path) -> None:
    a = Held(books_dir, EX, "delete").start()
    timer = threading.Timer(0.5, a.release)
    try:
        box: Dict[str, Any] = {}

        def waiter() -> float:
            t0 = time.monotonic()
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                return time.monotonic() - t0

        timer.start()
        box = _run_in_thread(waiter)
    finally:
        timer.join(JOIN_TIMEOUT_S)
    assert not box["alive"]
    assert "error" not in box, f"SH should have been granted: {box.get('error')!r}"
    assert 0.4 <= box["value"] < BUDGET_S


@pytest.mark.parametrize(
    "outer,inner", [(SH, SH), (EX, EX), (EX, SH)], ids=["sh-sh", "ex-ex", "ex-sh"]
)
def test_w2_04_same_stack_reentry_raises_without_deadlock(
    books_dir: Path, tmp_path: Path, outer: str, inner: str
) -> None:
    def body() -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        with book_lock.acquire(str(books_dir), BOOK, mode=outer, holder="notes"):
            t0 = time.monotonic()
            try:
                with book_lock.acquire(str(books_dir), BOOK, mode=inner, holder="notes"):
                    out["inner"] = "entered"
            except BaseException as exc:  # noqa: BLE001
                out["inner"] = exc
            out["elapsed"] = time.monotonic() - t0
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            out["fresh"] = "ok"
        return out

    box = _run_in_thread(body)
    assert not box["alive"], "re-entry deadlocked"
    assert "error" not in box, repr(box.get("error"))
    out = box["value"]
    assert isinstance(out["inner"], book_lock.BookLockReentry), repr(out["inner"])
    assert out["elapsed"] < 0.25
    assert out["fresh"] == "ok"
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


def test_w2_05_reentry_guard_is_per_thread_and_per_book(books_dir: Path) -> None:
    # (a) another thread on the same book
    def second_thread_same_book() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            return "ok"

    a = Held(books_dir, SH, "notes").start()
    try:
        box = _run_in_thread(second_thread_same_book)
    finally:
        a.release()
    assert box.get("value") == "ok", repr(box.get("error"))

    # (b) the same thread on another book
    def nested_other_book() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            with book_lock.acquire(str(books_dir), "y_data", mode=SH, holder="notes"):
                return "ok"

    box = _run_in_thread(nested_other_book)
    assert box.get("value") == "ok", repr(box.get("error"))
    assert _lock_file(books_dir).exists()
    assert _lock_file(books_dir, "y_data").exists()


def test_w2_06_upgrade_raises_and_the_sh_is_retained(books_dir: Path, tmp_path: Path) -> None:
    def body() -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            t0 = time.monotonic()
            try:
                with book_lock.acquire(str(books_dir), BOOK, mode=EX, holder="delete"):
                    out["inner"] = "entered"
            except BaseException as exc:  # noqa: BLE001
                out["inner"] = exc
            out["elapsed"] = time.monotonic() - t0
            out["probe_sh"] = probe(str(_lock_file(books_dir)), "SH", str(tmp_path))
            out["probe_ex"] = probe(str(_lock_file(books_dir)), "EX", str(tmp_path))
        return out

    box = _run_in_thread(body)
    assert not box["alive"]
    assert "error" not in box, repr(box.get("error"))
    out = box["value"]
    assert isinstance(out["inner"], book_lock.BookLockUpgrade), repr(out["inner"])
    assert out["elapsed"] < 0.25
    assert out["probe_sh"] == "ok"
    assert out["probe_ex"] == "blocked"


def test_w2_07a_resource_lock_without_book_lock_raises_before_any_fd(books_dir: Path) -> None:
    (books_dir / BOOK).mkdir()

    def body() -> None:
        with notes_service._book_write_lock(str(books_dir), BOOK):
            pass

    box = _run_in_thread(body)
    assert not box["alive"]
    assert isinstance(box.get("error"), book_lock.BookLockOrderError), repr(box.get("error"))
    assert not (books_dir / BOOK / notes_service.NOTES_LOCK_FILENAME).exists()


def test_w2_07b_book_lock_inside_resource_lock_raises(books_dir: Path) -> None:
    (books_dir / BOOK).mkdir()

    def body() -> None:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            with notes_service._book_write_lock(str(books_dir), BOOK):
                with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                    pass

    box = _run_in_thread(body)
    assert not box["alive"], "book lock inside the resource lock deadlocked"
    assert isinstance(
        box.get("error"), (book_lock.BookLockReentry, book_lock.BookLockOrderError)
    ), repr(box.get("error"))


def test_w2_08_one_acquisition_one_fd(books_dir: Path, tmp_path: Path) -> None:
    a = Held(books_dir, SH, "notes").start()
    b = Held(books_dir, SH, "reindex").start()
    try:
        a.release()
        assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "blocked"
    finally:
        b.release()
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.sampled_from(["sh", "ex", "rm", "mk"]), min_size=1, max_size=8))
def test_w2_09_lock_file_stable_and_book_dir_never_created(ops: List[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        books = os.path.join(tmp, "books")
        os.mkdir(books)
        book_dir = os.path.join(books, BOOK)
        lock_file = os.path.join(books, ".locks", f"{BOOK}.lock")
        inode: Optional[int] = None
        last_dir_op: Optional[str] = None
        for op in ops:
            if op in ("sh", "ex"):
                with book_lock.acquire(books, BOOK, mode=SH if op == "sh" else EX, holder="notes"):
                    pass
            elif op == "rm":
                shutil.rmtree(book_dir, ignore_errors=True)
                last_dir_op = "rm"
            else:
                os.makedirs(book_dir, exist_ok=True)
                last_dir_op = "mk"
            if os.path.exists(lock_file):
                ino = os.stat(lock_file).st_ino
                if inode is None:
                    inode = ino
                assert ino == inode, "the lock file was replaced"
            assert os.path.isdir(book_dir) == (last_dir_op == "mk")
            assert set(os.listdir(books)) <= {BOOK, ".locks"}
        if any(op in ("sh", "ex") for op in ops):
            assert inode is not None and os.path.exists(lock_file)


def test_w2_10_every_path_spelling_maps_to_one_lock(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, epub_v1: Path
) -> None:
    from reader3_app import reader3

    monkeypatch.chdir(tmp_path)
    abs_books = str(books_dir)
    spellings = ["books", abs_books, "./books", "books/../books"]
    derived_books, derived_folder = os.path.split(os.path.normpath(abs_books + "/" + BOOK + "/"))
    assert derived_folder == BOOK

    for holder_spelling in (derived_books, "./books"):
        with Holder(holder_spelling, BOOK, EX, "import", str(tmp_path)):
            for spelling in spellings + [derived_books]:
                if spelling == holder_spelling:
                    continue
                with pytest.raises(book_lock.BookLockBusy) as info:
                    with book_lock.acquire(spelling, BOOK, mode=EX, holder="delete"):
                        pass
                assert info.value.holder_category == "import", spelling
            # The process_epub-derived spelling, trailing slash included.
            with pytest.raises(book_lock.BookLockBusy):
                reader3.process_epub(str(epub_v1), "books/" + BOOK + "/")
    assert sorted(os.listdir(books_dir / ".locks")) == [f"{BOOK}.lock"]
    assert not (books_dir / BOOK).exists()


@pytest.mark.parametrize("name", ["..", ".", "a/b", "", "../x_data"])
def test_w2_11_unsafe_folder_refused_before_anything_is_created(tmp_path: Path, books_dir: Path, name: str) -> None:
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    with pytest.raises(ValueError):
        with book_lock.acquire(str(books_dir), name, mode=EX, holder="delete"):
            pass
    locks = books_dir / ".locks"
    assert not locks.exists() or list(locks.iterdir()) == []
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert [p for p in after if p not in before and p != "books/.locks"] == []


# --------------------------------------------------------------------------- W2-13 fake clock


class FakeClock:
    """Monotonic time the test owns. Only the waiter thread advances it.

    ``sleep`` on the waiter advances by ``dt`` and fires ``hook`` exactly once, the
    first time the clock crosses ``hook_at``. Any other thread that sleeps through
    the seam gets a short real sleep and leaves the clock alone.
    """

    def __init__(self, start: float = 100.0, hook_at: Optional[float] = None, hook=None) -> None:
        self.now = start
        self.hook_at = hook_at
        self.hook = hook
        self.fired = False
        self.waiter: Optional[int] = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, dt: float) -> None:
        if threading.get_ident() != self.waiter:
            time.sleep(min(max(dt, 0.0), 0.01))
            return
        before = self.now
        self.now = before + max(dt, 0.0)
        if (
            not self.fired
            and self.hook is not None
            and self.hook_at is not None
            and before < self.hook_at <= self.now
        ):
            self.fired = True
            self.hook()
        time.sleep(0.001)


def _install_clock(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> None:
    monkeypatch.setattr(book_lock, "_monotonic", clock.monotonic)
    monkeypatch.setattr(book_lock, "_sleep", clock.sleep)


def _run_waiter(clock: FakeClock, fn: Callable[[], Any]) -> Dict[str, Any]:
    """Run ``fn`` on a thread the clock treats as the waiter; 10 s real-time watchdog."""
    box: Dict[str, Any] = {}

    def body() -> None:
        clock.waiter = threading.get_ident()
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        box["at"] = clock.now

    t0 = time.monotonic()
    t = threading.Thread(target=body, daemon=True)
    t.start()
    t.join(10.0)
    box["alive"] = t.is_alive()
    box["real_elapsed"] = time.monotonic() - t0
    return box


def test_w2_13a_explicit_deadline_in_process_layer(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    a = Held(books_dir, EX, "delete").start()
    try:
        def waiter() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=100.4):
                pass

        box = _run_waiter(clock, waiter)
    finally:
        a.release()
    assert not box["alive"] and box["real_elapsed"] < 10.0
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("error"))
    assert box["error"].holder_category == "delete"
    assert 100.4 <= box["at"] <= 100.4 + FAKE_SLACK_S


def test_w2_13b_explicit_deadline_flock_layer(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Holder(str(books_dir), BOOK, EX, "import", str(tmp_path)):
        clock = FakeClock()
        _install_clock(monkeypatch, clock)

        def waiter() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=100.4):
                pass

        box = _run_waiter(clock, waiter)
    assert not box["alive"] and box["real_elapsed"] < 10.0
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("error"))
    assert box["error"].holder_category == "import"
    assert 100.4 <= box["at"] <= 100.4 + FAKE_SLACK_S


def test_w2_13c_one_deadline_across_in_process_and_flock_layers(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from book_lock_workers import spawn_ctx

    clock = FakeClock(hook_at=101.5)
    _install_clock(monkeypatch, clock)
    a = Held(books_dir, EX, "delete").start()

    ctx = spawn_ctx()
    holds_evt = ctx.Event()
    release_evt = ctx.Event()
    result_path = str(tmp_path / "ex-when-free.json")
    child = Child(
        acquire_ex_when_free, (str(books_dir), BOOK, "import", holds_evt, release_evt, result_path), result_path
    ).start()

    def hook() -> None:
        a.release()
        holds_evt.wait(10.0)

    clock.hook = hook
    try:
        def waiter() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                pass

        box = _run_waiter(clock, waiter)
    finally:
        release_evt.set()
        if a.thread.is_alive():
            a.release()
        code = child.reap()
    assert not box["alive"] and box["real_elapsed"] < 10.0
    assert clock.fired, "the hand-off hook never ran"
    assert outcome(child.wait_result(1.0)) == "acquired"
    assert code == 0
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("error"))
    assert box["error"].holder_category == "import"
    assert 102.0 <= box["at"] <= 102.0 + FAKE_SLACK_S


def test_w2_13d_one_deadline_across_book_flock_and_resource_layer(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (books_dir / BOOK).mkdir()
    holder = Holder(str(books_dir), BOOK, EX, "delete", str(tmp_path)).start()

    clock = FakeClock(hook_at=101.5)
    _install_clock(monkeypatch, clock)

    w_parked = threading.Event()
    w_release = threading.Event()
    real_save = notes_service.save_annotations

    def parked_save(books: str, book_id: str, annotations: List[Annotation]) -> None:
        if any(a.quote == "W" for a in annotations):
            w_parked.set()
            w_release.wait(10.0)
        return real_save(books, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", parked_save)
    w_box: Dict[str, Any] = {}

    def w_body() -> None:
        try:
            w_box["value"] = notes_service.add_annotation_and_version(str(books_dir), _ann("W"))
        except BaseException as exc:  # noqa: BLE001
            w_box["error"] = exc

    w_thread = threading.Thread(target=w_body, daemon=True)

    def hook() -> None:
        holder.release_evt.set()
        holder.released.wait(10.0)
        w_thread.start()
        w_parked.wait(10.0)

    clock.hook = hook
    try:
        box = _run_waiter(
            clock, lambda: notes_service.add_annotation_and_version(str(books_dir), _ann("LATE"))
        )
    finally:
        w_release.set()
        if w_thread.is_alive() or w_thread.ident is not None:
            w_thread.join(JOIN_TIMEOUT_S)
        code = holder.release()
    assert not box["alive"] and box["real_elapsed"] < 10.0
    assert clock.fired
    assert code == 0
    assert "error" not in w_box, repr(w_box.get("error"))
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("error"))
    assert box["error"].holder_category == "notes"
    assert 102.0 <= box["at"] <= 102.0 + FAKE_SLACK_S
    assert _quotes(books_dir) == {"W"}


def test_w2_13e_a_release_inside_the_budget_is_seen_within_one_poll(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert book_lock.POLL_S <= 0.1
    holder = Holder(str(books_dir), BOOK, EX, "import", str(tmp_path)).start()
    codes: List[Optional[int]] = []

    clock = FakeClock(hook_at=100.5, hook=lambda: codes.append(holder.release()))
    _install_clock(monkeypatch, clock)

    def waiter() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            return "acquired"

    try:
        box = _run_waiter(clock, waiter)
    finally:
        if not codes:
            codes.append(holder.release())
    assert not box["alive"] and box["real_elapsed"] < 10.0
    assert clock.fired
    assert codes == [0]
    assert box.get("value") == "acquired", repr(box.get("error"))
    assert box["at"] <= 100.75


# --------------------------------------------------------------------------- W2-14 (a)/(b)


def test_w2_14a_resource_thread_layer_waiter_refused_at_the_shared_deadline(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (books_dir / BOOK).mkdir()
    parked = threading.Event()
    release_evt = threading.Event()
    real_save = notes_service.save_annotations

    def parked_save(books: str, book_id: str, annotations: List[Annotation]) -> None:
        if any(a.quote == "Q1" for a in annotations):
            parked.set()
            release_evt.wait(PARK_GUARD_S)
        return real_save(books, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", parked_save)
    w1: Dict[str, Any] = {}

    def writer1() -> None:
        try:
            w1["value"] = notes_service.add_annotation_and_version(str(books_dir), _ann("Q1"))
        except BaseException as exc:  # noqa: BLE001
            w1["error"] = exc

    t = threading.Thread(target=writer1, daemon=True)
    t.start()
    try:
        assert parked.wait(10.0), f"writer 1 never parked: {w1!r}"
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            notes_service.add_annotation_and_version(str(books_dir), _ann("Q2"))
        elapsed = time.monotonic() - t0
    finally:
        release_evt.set()
        t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()
    assert "error" not in w1, repr(w1.get("error"))
    assert info.value.holder_category == "notes"
    assert BUDGET_S - 0.2 <= elapsed < BUDGET_S + EPS_S
    assert _quotes(books_dir) == {"Q1"}


def test_w2_14b_resource_flock_layer_waiter_refused_at_the_shared_deadline(
    books_dir: Path, tmp_path: Path
) -> None:
    from book_lock_workers import add_annotation_parked, spawn_ctx

    (books_dir / BOOK).mkdir()
    ctx = spawn_ctx()
    parked = ctx.Event()
    release_evt = ctx.Event()
    result_path = str(tmp_path / "w1.json")
    child = Child(
        add_annotation_parked, (str(books_dir), BOOK, "Q1", parked, release_evt, result_path, PARK_GUARD_S), result_path
    ).start()
    try:
        assert parked.wait(CHILD_WAIT_S), f"child writer never parked: {child.wait_result(0.1)!r}"
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            notes_service.add_annotation_and_version(str(books_dir), _ann("Q2"))
        elapsed = time.monotonic() - t0
    finally:
        release_evt.set()
        code = child.reap(CHILD_TIMEOUT_S)
    assert code == 0
    assert outcome(child.wait_result(1.0)) == "acquired"
    assert info.value.holder_category == "notes"
    assert BUDGET_S - 0.2 <= elapsed < BUDGET_S + EPS_S
    assert _quotes(books_dir) == {"Q1"}


# --------------------------------------------------------------------------- W2-53


@pytest.mark.parametrize("mode", [SH, EX])
def test_w2_53_release_on_the_exception_path(books_dir: Path, tmp_path: Path, mode: str) -> None:
    raised = threading.Event()
    proceed = threading.Event()
    out: Dict[str, Any] = {}

    def body() -> None:
        try:
            with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder="notes"):
                raise KeyError("boom")
        except BaseException as exc:  # noqa: BLE001
            out["captured"] = exc
        raised.set()
        proceed.wait(JOIN_TIMEOUT_S)
        try:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                out["same_thread"] = "ok"
        except BaseException as exc:  # noqa: BLE001
            out["same_thread"] = exc

    t = threading.Thread(target=body, daemon=True)
    t.start()
    try:
        assert raised.wait(JOIN_TIMEOUT_S)
        out["probe"] = probe(str(_lock_file(books_dir)), "EX", str(tmp_path))
    finally:
        proceed.set()
        t.join(JOIN_TIMEOUT_S)
    assert not t.is_alive()

    captured = out["captured"]
    assert type(captured) is KeyError and captured.args == ("boom",)
    assert out["probe"] == "ok"
    assert out["same_thread"] == "ok", repr(out["same_thread"])

    def other_thread_ex() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=EX, holder="delete"):
            return "ok"

    box = _run_in_thread(other_thread_ex)
    assert box.get("value") == "ok", repr(box.get("error"))
