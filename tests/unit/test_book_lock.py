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
        #: fix-up 2 (W1-04): when set before ``_go``, the body exits by raising.
        self._raise = False
        self.thread = threading.Thread(target=self._run, args=(str(books), folder, mode, holder), daemon=True)

    def _run(self, books: str, folder: str, mode: str, holder: str) -> None:
        try:
            with book_lock.acquire(books, folder, mode=mode, holder=holder):
                self.ready.set()
                self._go.wait(JOIN_TIMEOUT_S)
                if self._raise:
                    raise RuntimeError("fu2-body-raise")
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

    def release_raising(self) -> None:
        """Release by making the body raise ``RuntimeError("fu2-body-raise")``."""
        self._raise = True
        self.release()


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
    assert 0.4 <= box["value"] < book_lock.BUDGET_S


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
    # FX-5-08: the one default-budget pin. Unpatched on purpose; a leaked patch fails here.
    assert book_lock.BUDGET_S == 2.0
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
    assert book_lock.BUDGET_S - 0.2 <= elapsed < book_lock.BUDGET_S + EPS_S
    assert _quotes(books_dir) == {"Q1"}


def test_w2_14b_resource_flock_layer_waiter_refused_at_the_shared_deadline(
    books_dir: Path, tmp_path: Path, short_budget: float
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
    assert book_lock.BUDGET_S - 0.2 <= elapsed < book_lock.BUDGET_S + EPS_S
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


# --------------------------------------------------------------------------- FX-2-14


def test_fx_2_14_short_budget_is_one_poll_and_acquires_a_free_book(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FX-2-14 (tests-20261001-003726.md): the smallest deadline that still acquires."""
    short = getattr(book_lock, "SHORT_BUDGET_S", None)
    assert short is not None, "book_lock.SHORT_BUDGET_S is not defined"
    assert short == book_lock.POLL_S > 0

    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    deadline = clock.now + short

    def enter() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=deadline):
            return "entered"

    free = _run_waiter(clock, enter)
    assert not free["alive"]
    assert free.get("value") == "entered", repr(free.get("error"))

    clock2 = FakeClock()
    _install_clock(monkeypatch, clock2)
    deadline2 = clock2.now + short
    a = Held(books_dir, EX, "import").start()
    try:
        def refused() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=deadline2):
                pass

        box = _run_waiter(clock2, refused)
    finally:
        a.release()
    assert not box["alive"]
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("error"))
    assert box["at"] <= deadline2


# --------------------------------------------------------------------------- FX-3 (fix-plan WI-3)
#
# FX-3-01..10 and FX-3-05b of ``.claude/tdd-guardian/tests-20261001-003726.md``
# (audit findings #41, #42, #20). Law:
#   * a layer is accepted only if ``_monotonic() < deadline`` at the moment it
#     succeeds -- a success at or after the deadline releases every layer taken and
#     refuses; a deadline already reached refuses without acquiring anything;
#   * every exit path, including a failing teardown syscall, empties the table;
#   * the holder-category read is charged to the same deadline.

import errno  # noqa: E402 - section-local imports keep the W2 block untouched
import fcntl  # noqa: E402
import math  # noqa: E402

from hypothesis import assume  # noqa: E402

from reader3_app.ai import books as ai_books  # noqa: E402

#: FX-3 fake-clock bounds are exact up to float error, not ``FAKE_SLACK_S``.
FX_TICK_EPS_S = 1e-9


def _restore_real_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book_lock, "_monotonic", time.monotonic)
    monkeypatch.setattr(book_lock, "_sleep", time.sleep)


def _ex_ok_in_fresh_thread(books: Path, folder: str = BOOK) -> Dict[str, Any]:
    def body() -> str:
        with book_lock.acquire(str(books), folder, mode=EX, holder="delete"):
            return "ok"

    t0 = time.monotonic()
    box = _run_in_thread(body)
    box["elapsed"] = time.monotonic() - t0
    return box


def _raw_flock_holder(path: Path) -> int:
    """An in-process fd holding ``flock(LOCK_EX)`` on ``path``; writes no record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _nb_flock_free(path: Path) -> bool:
    """Level-4 kernel check without a spawn: a fresh open file description gets EX."""
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(fd)
    return True


def _resource_lock_file(books: Path, resource: str, folder: str = BOOK) -> Path:
    if resource == "notes":
        return books / folder / notes_service.NOTES_LOCK_FILENAME
    return books / ".locks" / resource / f"{folder}.lock"


def _resource_cm(books: Path, resource: str, folder: str = BOOK):
    if resource == "notes":
        return notes_service._book_write_lock(str(books), folder)
    return book_lock.resource_lock(str(books), folder, category=resource)


def fresh_resource_ok(books: Path, resource: str, folder: str = BOOK) -> tuple:
    """SH book lock + the resource lock in a fresh thread; ``(value, real_elapsed)``."""

    def body() -> str:
        with book_lock.acquire(str(books), folder, mode=SH, holder=resource):
            with _resource_cm(books, resource, folder):
                return "ok"

    t0 = time.monotonic()
    box = _run_in_thread(body)
    elapsed = time.monotonic() - t0
    assert not box["alive"], f"a fresh {resource} holder never finished"
    return box.get("value", repr(box.get("error"))), elapsed


class ResourceHeld:
    """A thread holding SH on the book plus one resource lock until ``release()``."""

    def __init__(self, books: Path, resource: str, folder: str = BOOK) -> None:
        self.ready = threading.Event()
        self._go = threading.Event()
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, args=(books, resource, folder), daemon=True)

    def _run(self, books: Path, resource: str, folder: str) -> None:
        try:
            with book_lock.acquire(str(books), folder, mode=SH, holder=resource):
                with _resource_cm(books, resource, folder):
                    self.ready.set()
                    self._go.wait(PARK_GUARD_S)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            self.error = exc
            self.ready.set()

    def start(self) -> "ResourceHeld":
        self.thread.start()
        assert self.ready.wait(JOIN_TIMEOUT_S), "resource holder never became ready"
        assert self.error is None, f"resource holder failed to acquire: {self.error!r}"
        return self

    def release(self) -> None:
        self._go.set()
        self.thread.join(JOIN_TIMEOUT_S)
        assert not self.thread.is_alive(), "resource holder deadlocked on release"


def _seed_resource(books: Path, resource: str) -> Path:
    """The book dir plus the resource's data file; returns that file."""
    (books / BOOK).mkdir(exist_ok=True)
    if resource == "notes":
        notes_service.add_annotation_and_version(str(books), _ann("seed"))
        return books / BOOK / notes_service.NOTES_FILENAME
    meta = books / BOOK / ai_books.AI_META_FILENAME
    meta.write_text(json.dumps({"indexed_at": 1}), encoding="utf-8")
    return meta


def _resource_call(books: Path, resource: str) -> Callable[[float], Any]:
    if resource == "notes":
        return lambda d: notes_service.add_annotation_and_version(str(books), _ann("LATE"), deadline=d)
    return lambda d: ai_books.ensure_book_uuid(str(books), BOOK, deadline=d)


# ---- FX-3-01 / FX-3-02: teardown syscalls failing


class _OsCloseShim:
    """``book_lock.os`` with ``close`` doing the real close and then raising, once."""

    def __init__(self) -> None:
        self.close_calls = 0
        self._armed = True

    def close(self, fd: int) -> None:
        self.close_calls += 1
        os.close(fd)
        if self._armed:
            self._armed = False
            raise OSError(errno.EIO, "close failed")

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


class _FcntlUnlockShim:
    """``book_lock.fcntl`` with ``flock(fd, LOCK_UN)`` raising, once."""

    def __init__(self) -> None:
        self.unlock_calls = 0
        self._armed = True

    def flock(self, fd: int, op: int) -> None:
        if op == fcntl.LOCK_UN:
            self.unlock_calls += 1
            if self._armed:
                self._armed = False
                raise OSError(errno.EIO, "unlock failed")
        fcntl.flock(fd, op)

    def __getattr__(self, name: str) -> Any:
        return getattr(fcntl, name)


@pytest.mark.parametrize("mode", [SH, EX])
def test_fx_3_01_os_close_raising_in_teardown_propagates_and_leaves_no_stale_holder(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float, mode: str
) -> None:
    shim = _OsCloseShim()
    monkeypatch.setattr(book_lock, "os", shim)
    with pytest.raises(OSError, match="close failed"):
        with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder="import"):
            pass
    assert shim.close_calls == 1, "acquire no longer closes its fd through book_lock.os.close"

    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", f"stale in-process holder left behind: {box.get('error')!r}"
    assert box["elapsed"] < 0.5
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


@pytest.mark.parametrize("mode", [SH, EX])
def test_fx_3_02_flock_unlock_raising_in_teardown_is_suppressed_and_still_unregisters(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float, mode: str
) -> None:
    shim = _FcntlUnlockShim()
    monkeypatch.setattr(book_lock, "fcntl", shim)
    with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder="import"):
        pass
    assert shim.unlock_calls == 1

    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", repr(box.get("error"))
    assert box["elapsed"] < 0.5
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


# ---- FX-3-03..05b: a success at the deadline is refused, at every layer


def test_fx_3_03_late_wake_up_at_layer_1_is_refused(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = Held(books_dir, EX, "import").start()
    clock = FakeClock(start=100.0, hook_at=100.3, hook=held.release)
    _install_clock(monkeypatch, clock)
    try:
        def waiter() -> str:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=100.3):
                return "acquired"

        box = _run_waiter(clock, waiter)
    finally:
        if held.thread.is_alive():
            held.release()
    _restore_real_clock(monkeypatch)
    assert not box["alive"]
    assert clock.fired, "the release hook never ran"
    assert isinstance(box.get("error"), book_lock.BookLockBusy), repr(box.get("value", box.get("error")))
    assert box["at"] <= 100.3 + FX_TICK_EPS_S
    fresh = _ex_ok_in_fresh_thread(books_dir)
    assert fresh.get("value") == "ok", repr(fresh.get("error"))
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


def test_fx_3_04_late_wake_up_at_layer_2_is_refused_and_holds_nothing(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fd = _raw_flock_holder(_lock_file(books_dir))
    closed: List[int] = []

    def release() -> None:
        os.close(fd)
        closed.append(fd)

    clock = FakeClock(start=100.0, hook_at=100.3, hook=release)
    _install_clock(monkeypatch, clock)
    try:
        def waiter() -> str:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes", deadline=100.3):
                return "acquired"

        box = _run_waiter(clock, waiter)
    finally:
        if not closed:
            os.close(fd)
    _restore_real_clock(monkeypatch)
    assert not box["alive"]
    assert clock.fired
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(box.get("value", err))
    assert box["at"] <= 100.3 + FX_TICK_EPS_S
    assert err.holder_category in (book_lock.CATEGORIES | {book_lock.UNKNOWN})
    assert err.holder_category != "notes", "the waiter read its own category record"
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"
    fresh = _ex_ok_in_fresh_thread(books_dir)
    assert fresh.get("value") == "ok", repr(fresh.get("error"))


@pytest.mark.parametrize("resource", ["notes", "ai_meta"])
def test_fx_3_05_late_wake_up_at_the_resource_thread_lock_layer_is_refused(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float, resource: str
) -> None:
    data = _seed_resource(books_dir, resource)
    before = data.read_bytes()
    holder = ResourceHeld(books_dir, resource).start()
    clock = FakeClock(start=100.0, hook_at=100.3, hook=holder.release)
    _install_clock(monkeypatch, clock)
    call = _resource_call(books_dir, resource)
    try:
        box = _run_waiter(clock, lambda: call(100.3))
    finally:
        if holder.thread.is_alive():
            holder.release()
    _restore_real_clock(monkeypatch)
    assert not box["alive"]
    assert clock.fired
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(box.get("value", err))
    assert err.holder_category == resource
    assert box["at"] <= 100.3 + FX_TICK_EPS_S
    assert data.read_bytes() == before

    value, elapsed = fresh_resource_ok(books_dir, resource)
    assert value == "ok"
    assert elapsed < 0.1, f"fresh {resource} holder waited {elapsed:.3f}s: a late refusal leaked a lock"
    fresh = _ex_ok_in_fresh_thread(books_dir)
    assert fresh.get("value") == "ok", repr(fresh.get("error"))
    assert probe(str(_resource_lock_file(books_dir, resource)), "EX", str(tmp_path)) == "ok"


@pytest.mark.parametrize("resource", ["ai_meta", "notes"])
def test_fx_3_05b_late_wake_up_at_the_resource_flock_layer_is_refused(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float, resource: str
) -> None:
    data = _seed_resource(books_dir, resource)
    before = data.read_bytes()
    lock_file = _resource_lock_file(books_dir, resource)
    fd = _raw_flock_holder(lock_file)
    closed: List[int] = []

    def release() -> None:
        os.close(fd)
        closed.append(fd)

    clock = FakeClock(start=100.0, hook_at=100.3, hook=release)
    _install_clock(monkeypatch, clock)
    call = _resource_call(books_dir, resource)
    try:
        box = _run_waiter(clock, lambda: call(100.3))
    finally:
        if not closed:
            os.close(fd)
    _restore_real_clock(monkeypatch)
    assert not box["alive"]
    assert clock.fired
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(box.get("value", err))
    assert err.holder_category == resource
    assert box["at"] <= 100.3 + FX_TICK_EPS_S
    assert data.read_bytes() == before

    assert probe(str(lock_file), "EX", str(tmp_path)) == "ok"
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"
    value, elapsed = fresh_resource_ok(books_dir, resource)
    assert value == "ok"
    assert elapsed < 0.1, f"fresh {resource} holder waited {elapsed:.3f}s: a late refusal leaked a lock"


# ---- FX-3-06: a deadline at or before now


@pytest.mark.parametrize("mode", [SH, EX])
@pytest.mark.parametrize("offset, acquires", [(-0.001, False), (0.0, False), (1e-6, True)])
def test_fx_3_06_deadline_at_or_before_now_refuses_a_free_book(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, offset: float, acquires: bool
) -> None:
    clock = FakeClock(start=100.0)
    _install_clock(monkeypatch, clock)
    deadline = clock.now + offset

    def enter() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder="notes", deadline=deadline):
            return "entered"

    box = _run_waiter(clock, enter)
    _restore_real_clock(monkeypatch)
    assert not box["alive"]
    if acquires:
        assert box.get("value") == "entered", repr(box.get("error"))
        return
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(box.get("value", err))
    assert err.holder_category == book_lock.UNKNOWN
    assert box["at"] <= 100.0 + FX_TICK_EPS_S, "a refusal on a reached deadline must not sleep"
    # ADR-0015 item 1: the lock file "may exist". A refusal of an already-reached
    # deadline happens before any disk access, so "missing" is as free as "ok".
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) in {"ok", "missing"}
    fresh = _ex_ok_in_fresh_thread(books_dir)
    assert fresh.get("value") == "ok", repr(fresh.get("error"))


# ---- FX-3-07: the deadline law over a generated domain


def _near_tick(x: float) -> bool:
    ticks = x / book_lock.POLL_S
    return abs(ticks - round(ticks)) * book_lock.POLL_S < 1e-6


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    remaining=st.floats(0, 0.5),
    release_at=st.floats(0.001, 0.6),
    layer=st.sampled_from(["table", "raw-flock", "resource-flock"]),
)
def test_fx_3_07_acquires_iff_the_first_tick_after_release_is_before_the_deadline(
    remaining: float, release_at: float, layer: str
) -> None:
    assume(not _near_tick(remaining) and not _near_tick(release_at))
    start = 100.0
    deadline = start + remaining
    expected = book_lock.POLL_S * math.ceil(release_at / book_lock.POLL_S) < remaining

    with tempfile.TemporaryDirectory() as tmp:
        books = Path(tmp) / "books"
        books.mkdir()
        meta = books / BOOK / ai_books.AI_META_FILENAME
        released: List[int] = []
        held: Optional[Held] = None
        fd = -1
        if layer == "table":
            held = Held(books, EX, "import").start()

            def release() -> None:
                assert held is not None
                held.release()
                released.append(1)
        else:
            if layer == "resource-flock":
                (books / BOOK).mkdir()
                meta.write_text(json.dumps({"indexed_at": 1}), encoding="utf-8")
                fd = _raw_flock_holder(books / ".locks" / "ai_meta" / f"{BOOK}.lock")
            else:
                fd = _raw_flock_holder(_lock_file(books))

            def release() -> None:
                os.close(fd)
                released.append(1)

        before = meta.read_bytes() if meta.exists() else None
        clock = FakeClock(start=start, hook_at=start + release_at, hook=release)
        real_monotonic, real_sleep = book_lock._monotonic, book_lock._sleep
        book_lock._monotonic, book_lock._sleep = clock.monotonic, clock.sleep
        try:
            if layer == "resource-flock":
                box = _run_waiter(clock, lambda: ai_books.ensure_book_uuid(str(books), BOOK, deadline=deadline))
            else:
                def waiter() -> str:
                    with book_lock.acquire(str(books), BOOK, mode=SH, holder="notes", deadline=deadline):
                        return "acquired"

                box = _run_waiter(clock, waiter)
        finally:
            book_lock._monotonic, book_lock._sleep = real_monotonic, real_sleep
            if not released:
                release()

        assert not box["alive"]
        err = box.get("error")
        if layer == "resource-flock":
            on_disk = json.loads(meta.read_text(encoding="utf-8")).get("book_uuid")
            acquired = err is None and on_disk is not None and box.get("value") == on_disk
        else:
            acquired = err is None and box.get("value") == "acquired"
        assert acquired == expected, (remaining, release_at, layer, box.get("value"), err)
        if not acquired:
            assert isinstance(err, book_lock.BookLockBusy), repr(err)
            assert box["at"] <= deadline + FX_TICK_EPS_S
            want = {"table": "import", "raw-flock": book_lock.UNKNOWN, "resource-flock": "ai_meta"}[layer]
            assert err.holder_category == want
            if layer == "resource-flock":
                assert meta.read_bytes() == before

        fresh = _ex_ok_in_fresh_thread(books)
        assert fresh.get("value") == "ok", repr(fresh.get("error"))
        if layer == "resource-flock":
            assert _nb_flock_free(books / ".locks" / "ai_meta" / f"{BOOK}.lock")
            value, _elapsed = fresh_resource_ok(books, "ai_meta")
            assert value == "ok"


# ---- FX-3-08 / FX-3-09: the category settle is charged to the deadline


@pytest.mark.parametrize("mode", [SH, EX])
def test_fx_3_08_settle_with_little_time_left_lands_at_or_before_the_deadline(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    fd = _raw_flock_holder(_lock_file(books_dir))
    try:
        clock = FakeClock(start=100.0)
        _install_clock(monkeypatch, clock)
        deadline = clock.now + 0.03

        def waiter() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder="notes", deadline=deadline):
                pass

        box = _run_waiter(clock, waiter)
    finally:
        os.close(fd)
    assert not box["alive"]
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(err)
    assert err.holder_category == book_lock.UNKNOWN
    assert box["at"] <= deadline + FX_TICK_EPS_S
    assert box["real_elapsed"] < 0.06, f"the settle cost {box['real_elapsed']:.3f}s of real time"


def test_fx_3_09_settle_with_plenty_of_time_still_spends_the_full_window(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fd = _raw_flock_holder(_lock_file(books_dir))
    try:
        clock = FakeClock(start=100.0)
        _install_clock(monkeypatch, clock)
        deadline = clock.now + 2.0

        def waiter() -> None:
            with book_lock.acquire(str(books_dir), BOOK, mode=EX, holder="notes", deadline=deadline):
                pass

        box = _run_waiter(clock, waiter)
    finally:
        os.close(fd)
    assert not box["alive"]
    err = box.get("error")
    assert isinstance(err, book_lock.BookLockBusy), repr(err)
    assert err.holder_category == book_lock.UNKNOWN
    spent = box["at"] - 100.0
    settle = book_lock._CATEGORY_SETTLE_S
    assert settle - FX_TICK_EPS_S <= spent <= settle + 0.01, spent



# --------------------------------------------------------------------------- FX-5 (fix-plan WI-5)
#
# FX-5-01, FX-5-02, FX-5-06 of ``.claude/tdd-guardian/tests-20261001-003726.md``
# (audit findings #1, #2, #9-#11). FX-5-08 is the pin at the top of W2-14a.


def test_fx_5_01_book_lock_on_another_folder_inside_the_notes_resource_is_exactly_an_order_error(
    books_dir: Path,
) -> None:
    """The inner book lock is on a *different* folder, so the re-entry guard cannot fire first."""
    (books_dir / BOOK).mkdir()

    def body() -> str:
        with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
            with notes_service._book_write_lock(str(books_dir), BOOK):
                with book_lock.acquire(str(books_dir), "y_data", mode=SH, holder="notes"):
                    return "entered"

    box = _run_in_thread(body)
    assert not box["alive"], "a book lock inside the resource lock deadlocked"
    err = box.get("error")
    assert type(err) is book_lock.BookLockOrderError, repr(box.get("value", err))
    assert not _lock_file(books_dir, "y_data").exists(), "the refusal came after an fd was opened"


def test_fx_5_02_in_process_ex_holders_category_survives_a_junked_record_with_no_settle_wait(
    books_dir: Path,
) -> None:
    a = Held(books_dir, EX, "delete").start()
    try:
        with open(_lock_file(books_dir), "r+b") as f:
            f.write(b"\xff\xfe junk")

        def b() -> tuple:
            t0 = time.monotonic()
            try:
                with book_lock.acquire(str(books_dir), BOOK, mode=EX, holder="import"):
                    return ("entered", time.monotonic() - t0)
            except book_lock.BookLockBusy as exc:
                return (exc.holder_category, time.monotonic() - t0)

        box = _run_in_thread(b)
    finally:
        a.release()
    assert not box["alive"]
    assert "value" in box, repr(box.get("error"))
    category, elapsed = box["value"]
    assert category == "delete", "the refusal read the on-disk record instead of the in-process table"
    assert elapsed < 0.05, f"refusal took {elapsed:.3f}s: it went through the category settle"


def test_fx_5_06_the_short_budget_fixture_actually_shortens_a_real_refusal(
    books_dir: Path, short_budget: float
) -> None:
    assert book_lock.BUDGET_S == 0.3
    a = Held(books_dir, EX, "import").start()
    try:
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
                pass
        elapsed = time.monotonic() - t0
    finally:
        a.release()
    assert info.value.holder_category == "import"
    assert 0.25 <= elapsed < 0.6, elapsed


# --------------------------------------------------------------------------- fix-up 2, WI-1 (#21)
#
# W1-04..W1-07 and W1-09 of ``.claude/tdd-guardian/tests-20261001-170000.md``. The
# cross-process edges (W1-01..W1-03, W1-08) are in ``test_book_lock_cross_process.py``.
#
# Law: a refusal never names a category that has no live holder. Over one process,
# with no same-category count guard (plan decision 3), the on-disk record obeys
# ``acquire C`` -> ``record := C``; ``release C`` (normal or raising exit) ->
# ``record := None if record == C else record``; an EX cycle leaves ``record := None``.
# The SH clear runs before ``LOCK_UN`` / ``close`` on the one fd it opened (decision 1),
# never raises (decision 4), and clears only an exact ``holder pid`` record (decision 5).

from typing import Tuple  # noqa: E402

from hypothesis import example  # noqa: E402

FU2_CATEGORIES = ["notes", "reindex", "search"]
FU2_RAISE_MSG = "fu2-body-raise"


def _read_record(books: Path, folder: str = BOOK) -> bytes:
    """The first record-width bytes of the lock file; ``b""`` if it does not exist yet."""
    try:
        with open(_lock_file(books, folder), "rb") as f:
            return f.read(64)
    except FileNotFoundError:
        return b""


_fu2_step = st.one_of(
    st.tuples(st.just("acq"), st.sampled_from(FU2_CATEGORIES)),
    st.tuples(st.just("rel"), st.integers(min_value=0, max_value=7)),
    st.tuples(st.just("rel_raise"), st.integers(min_value=0, max_value=7)),
    st.just(("ex",)),
)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(_fu2_step, min_size=1, max_size=8))
@example(steps=[("acq", "notes"), ("rel", 0)])
@example(steps=[("acq", "notes"), ("acq", "reindex"), ("rel", 0)])
@example(steps=[("acq", "reindex"), ("acq", "notes"), ("rel", 1)])
@example(steps=[("acq", "notes"), ("acq", "notes"), ("rel", 0)])
@example(steps=[("acq", "notes"), ("rel", 0), ("ex",)])
@example(steps=[("acq", "notes"), ("rel_raise", 0)])
@example(steps=[("acq", "notes"), ("acq", "reindex"), ("rel_raise", 0)])
def test_fu2_w1_04_category_record_matches_the_model(steps: List[tuple]) -> None:
    books = Path(tempfile.mkdtemp(prefix="fu2-w1-04-"))
    live: List[Tuple[Held, str]] = []
    model: Optional[str] = None
    done: List[tuple] = []
    try:
        for step in steps:
            done.append(step)
            kind = step[0]
            if kind == "acq":
                category = step[1]
                live.append((Held(books, SH, category).start(), category))
                model = category
            elif kind in ("rel", "rel_raise"):
                if live:
                    held, category = live.pop(step[1] % len(live))
                    if kind == "rel":
                        held.release()
                        assert held.error is None, f"after {done!r}: clean release raised {held.error!r}"
                    else:
                        held.release_raising()
                        err = held.error
                        assert type(err) is RuntimeError and str(err) == FU2_RAISE_MSG, (
                            f"after {done!r}: the body's raise did not come back through acquire: {err!r}"
                        )
                    if model == category:
                        model = None
            else:  # "ex": only when no SH is live
                if not live:
                    with book_lock.acquire(str(books), BOOK, mode=EX, holder="delete"):
                        inside = book_lock._parse_category(_read_record(books))
                        assert inside == "delete", f"after {done!r}: EX record parses to {inside!r}"
                    model = None
            got = book_lock._parse_category(_read_record(books))
            assert got == (model or "unknown"), (
                f"after {done!r}: on-disk record parses to {got!r}, the model says {model or 'unknown'!r} (#21)"
            )
    finally:
        for held, _ in live:
            held.release()
        shutil.rmtree(books, ignore_errors=True)


class _ClearWriteFailsShim:
    """``book_lock.os`` whose blank-payload ``pwrite`` (the clear) raises EIO; the rest is real."""

    def __init__(self) -> None:
        self.clear_attempts = 0

    def pwrite(self, fd: int, data: bytes, offset: int) -> int:
        if data.strip() == b"":
            self.clear_attempts += 1
            raise OSError(errno.EIO, "pwrite failed")
        return os.pwrite(fd, data, offset)

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


class _ReadFailsShim:
    """``book_lock.os`` whose ``pread`` always raises EIO; the rest is real."""

    def __init__(self) -> None:
        self.read_attempts = 0

    def pread(self, fd: int, n: int, offset: int) -> bytes:
        self.read_attempts += 1
        raise OSError(errno.EIO, "pread failed")

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


def test_fu2_w1_05_a_failing_clear_write_never_makes_sh_release_raise(
    books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_budget: float
) -> None:
    shim = _ClearWriteFailsShim()
    monkeypatch.setattr(book_lock, "os", shim)
    with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
        pass
    attempts = shim.clear_attempts
    monkeypatch.setattr(book_lock, "os", os)

    assert attempts == 1, (
        f"SH release made {attempts} clear attempts, expected exactly 1. If the clear no longer goes "
        "through book_lock.os.pwrite with a blank payload, retarget the shim rather than weaken this."
    )
    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", repr(box.get("error"))
    assert box["elapsed"] < 0.5
    assert probe(str(_lock_file(books_dir)), "EX", str(tmp_path)) == "ok"


def test_fu2_w1_06_a_failing_record_read_skips_the_clear_and_never_raises(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = _ReadFailsShim()
    monkeypatch.setattr(book_lock, "os", shim)
    with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
        pass
    attempts = shim.read_attempts
    monkeypatch.setattr(book_lock, "os", os)

    assert attempts >= 1, (
        "SH release never read the record. If the compare no longer reads through book_lock.os.pread, "
        "retarget the shim rather than weaken this."
    )
    tokens = _read_record(books_dir).decode("ascii", errors="replace").split()
    assert tokens == ["notes", str(os.getpid())], f"a failed read must skip the clear, record is {tokens!r}"
    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", repr(box.get("error"))


class _TeardownSpyOs:
    """Pass-through ``book_lock.os`` that logs the clear, ``close`` and every ``open`` before delegating."""

    def __init__(self, log: List[str], opens: List[str]) -> None:
        self._log = log
        self._opens = opens

    def pwrite(self, fd: int, data: bytes, offset: int) -> int:
        if data.strip() == b"":
            self._log.append("clear")
        return os.pwrite(fd, data, offset)

    def close(self, fd: int) -> None:
        self._log.append("close")
        os.close(fd)

    def open(self, path: str, flags: int, mode: int = 0o777) -> int:
        self._opens.append(path)
        return os.open(path, flags, mode)

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


class _TeardownSpyFcntl:
    """Pass-through ``book_lock.fcntl`` that logs ``flock(LOCK_UN)`` before delegating."""

    def __init__(self, log: List[str]) -> None:
        self._log = log

    def flock(self, fd: int, op: int) -> None:
        if op == fcntl.LOCK_UN:
            self._log.append("unlock")
        fcntl.flock(fd, op)

    def __getattr__(self, name: str) -> Any:
        return getattr(fcntl, name)


@pytest.mark.parametrize("mode", [SH, EX])
def test_fu2_w1_07_release_clears_while_still_holding_the_flock_on_its_one_fd(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    (books_dir / ".locks").mkdir()
    log: List[str] = []
    opens: List[str] = []
    monkeypatch.setattr(book_lock, "os", _TeardownSpyOs(log, opens))
    monkeypatch.setattr(book_lock, "fcntl", _TeardownSpyFcntl(log))
    with book_lock.acquire(str(books_dir), BOOK, mode=mode, holder=("notes" if mode == SH else "delete")):
        pass
    monkeypatch.setattr(book_lock, "os", os)
    monkeypatch.setattr(book_lock, "fcntl", fcntl)

    assert log == ["clear", "unlock", "close"], (
        f"{mode} teardown was {log!r}; expected ['clear', 'unlock', 'close']: the record is cleared with a "
        "blank pwrite while the flock is still held, then flock(LOCK_UN), then close. A deliberate change of "
        "syscall retargets this spy; it does not relax the order."
    )
    assert opens == [book_lock.lock_path(str(books_dir), BOOK)], f"expected one os.open of the lock path: {opens!r}"
    assert _read_record(books_dir).strip() == b"", "the record was not left blank"
    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", repr(box.get("error"))
    assert box["elapsed"] < 0.5


@pytest.mark.parametrize(
    "template",
    [b"notes {me}7", b"notes {me} extra", b"\xff\xfe junk", b"notes 12ab", b"notes"],
    ids=["pid-prefix", "extra-field", "non-ascii", "non-numeric-pid", "one-field"],
)
def test_fu2_w1_09_the_compare_never_clears_or_raises_on_a_foreign_or_torn_record(
    books_dir: Path, template: bytes
) -> None:
    raw = template.replace(b"{me}", str(os.getpid()).encode())
    injected = raw[:63].ljust(63, b" ") + b"\n"
    lock_file = _lock_file(books_dir)
    with book_lock.acquire(str(books_dir), BOOK, mode=SH, holder="notes"):
        fd2 = os.open(str(lock_file), os.O_RDWR)
        try:
            os.pwrite(fd2, injected, 0)
        finally:
            os.close(fd2)

    assert lock_file.read_bytes()[:64] == injected, "the release rewrote a record it does not own"
    box = _ex_ok_in_fresh_thread(books_dir)
    assert not box["alive"]
    assert box.get("value") == "ok", repr(box.get("error"))
    assert box["elapsed"] < 0.5
