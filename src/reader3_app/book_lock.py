"""Per-book cross-process write lock (ADR-0015).

One lock per book, shared by every writer of that book: import / delete take it
**exclusive**, the writers that only touch their own file (notes, reindex,
ai_meta, conversations) take it **shared** and then their own resource lock.

Three layers, one deadline:
  1. an in-process reader/writer table (``flock`` is per open file description,
     so two threads of one process with two fds already exclude each other at the
     kernel -- but only a table can say *who* holds it without touching disk, and
     it keeps SH-with-SH genuinely concurrent inside one process);
  2. ``flock`` on ``books/.locks/{folder}.lock`` for other processes;
  3. the writer's own resource lock (``resource_lock`` below; notes reaches it
     through ``notes_service._book_write_lock``), which reads the deadline back
     from here.

Every wait polls with ``LOCK_NB`` and ``_sleep(min(POLL_S, remaining))`` against
one absolute ``_monotonic`` deadline; an exclusive request never waits. A layer is
accepted only if ``_monotonic() < deadline`` when it succeeds: a success at or after
the deadline releases that layer and every layer already taken, then refuses, and a
deadline already reached refuses before anything is attempted (fix-plan WI-3, #42).

The lock file lives *outside* the book dir and is never unlinked: an ``rmtree``
of the book would otherwise unlink it and the next writer would lock a new inode
(two processes each holding "the" lock). Creating ``.locks/`` is the only thing
this module ever creates; it never creates the book dir.

The holder category written into the lock file is best-effort telemetry for the
409 message (ADR-0015 R6). It is read only after a non-blocking attempt has
already failed, and no decision is ever taken on it: stale, empty, torn, or
naming a dead pid all read as ``"unknown"``.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Dict, Iterator, Optional, Tuple

POLL_S = 0.05
BUDGET_S = 2.0
#: Best-effort callers (page uuid lookup, the resolver scan): one poll, no meaningful
#: wait. Must stay > 0 -- a deadline already reached refuses even a free book.
SHORT_BUDGET_S = POLL_S
LOCKS_DIRNAME = ".locks"
SHARED = "shared"
EXCLUSIVE = "exclusive"
CATEGORIES = frozenset({"import", "delete", "reindex", "notes", "ai_meta", "conversations"})
UNKNOWN = "unknown"
#: Fixed width of the category record at offset 0 of the lock file.
_RECORD_BYTES = 64
#: How long a refused caller keeps re-reading an empty category record: the winner
#: writes it right after its ``flock`` succeeds, so a loser can read it too early.
#: Charged to the caller's deadline: the window is ``min(this, deadline - now)``.
_CATEGORY_SETTLE_S = 0.1
_CATEGORY_POLL_S = 0.005
_AI_META_FILENAME = "ai_meta.json"

# Time seams. Tests substitute both. Every wait in this module -- the layer polls and
# the holder-category settle in ``_read_category`` -- reads time only through them.
_monotonic = time.monotonic
_sleep = time.sleep


class _NoCheck:
    def __repr__(self) -> str:
        return "NO_UUID_CHECK"


#: Sentinel for ``expected_book_uuid``: "do not compare identities".
NO_UUID_CHECK = _NoCheck()


class BookLockError(Exception):
    pass


class BookLockBusy(BookLockError):
    """Another writer holds the book. Not a ``RuntimeError``: routes map it to 409."""

    def __init__(self, holder_category: str, retry_after: int = 1) -> None:
        super().__init__(f"book busy: {holder_category}")
        self.holder_category = holder_category
        self.retry_after = max(1, int(retry_after))


class BookChanged(BookLockError):
    """The folder now holds a different book than the one the request started on."""


class BookGone(FileNotFoundError):
    """The book dir was removed; the writer refused instead of recreating it."""


class BookLockMisuse(BookLockError):
    pass


class BookLockReentry(BookLockMisuse):
    pass


class BookLockUpgrade(BookLockMisuse):
    pass


class BookLockOrderError(BookLockMisuse):
    pass


# --------------------------------------------------------------------------- paths


def _safe_folder(book_folder: str) -> str:
    from .safe_paths import safe_book_folder

    return safe_book_folder(book_folder)


def lock_path(books_dir: str, book_folder: str) -> str:
    return os.path.join(books_dir, LOCKS_DIRNAME, f"{_safe_folder(book_folder)}.lock")


def _key(books_dir: str, book_folder: str) -> str:
    """One key per lock file, whatever spelling of ``books_dir`` the caller used."""
    return os.path.realpath(lock_path(books_dir, book_folder))


def _resource_lock_path(books_dir: str, book_folder: str, category: str) -> str:
    """``books/.locks/{category}/{folder}.lock`` (ADR-0015 item 2).

    Outside the book dir, like the book lock itself, and for the same reason: an
    ``rmtree`` of the book must not take the lock inode with it. It cannot collide
    with a ``{folder}.lock``, because a category subdir carries no ``.lock`` suffix.
    """
    return os.path.join(books_dir, LOCKS_DIRNAME, category, f"{_safe_folder(book_folder)}.lock")


# --------------------------------------------------------------------------- in-process state


@dataclass
class _KeyState:
    readers: Dict[str, int] = field(default_factory=dict)
    writer: Optional[str] = None

    def holder(self) -> str:
        if self.writer is not None:
            return self.writer
        for category, count in self.readers.items():
            if count > 0:
                return category
        return UNKNOWN


_STATE_GUARD = threading.Lock()
_STATES: Dict[str, _KeyState] = {}
_TLS = threading.local()
# One ``threading.Lock`` per resource-lock file, keyed by its realpath. Bounded by
# the number of (resource, book) pairs ever written in this process; never evicted.
_RESOURCE_GUARD = threading.Lock()
_RESOURCE_THREAD_LOCKS: Dict[str, threading.Lock] = {}


def _held() -> Dict[str, Tuple[str, float]]:
    held = getattr(_TLS, "held", None)
    if held is None:
        held = {}
        _TLS.held = held
    return held


def _resource_depth() -> int:
    return int(getattr(_TLS, "resource_depth", 0))


def held_deadline(books_dir: str, book_folder: str) -> Optional[float]:
    """The deadline of this thread's live acquisition of that book, or ``None``."""
    got = _held().get(_key(books_dir, book_folder))
    return None if got is None else got[1]


@contextlib.contextmanager
def resource_section() -> Iterator[None]:
    """Mark this thread as inside a resource lock: a book lock taken now is an order error."""
    _TLS.resource_depth = _resource_depth() + 1
    try:
        yield
    finally:
        _TLS.resource_depth = _resource_depth() - 1


def _register(key: str, mode: str, holder: str) -> Optional[str]:
    """Try to enter the in-process table. ``None`` on success, else the blocking category."""
    with _STATE_GUARD:
        st = _STATES.setdefault(key, _KeyState())
        if mode == EXCLUSIVE:
            if st.writer is not None or any(c > 0 for c in st.readers.values()):
                return st.holder()
            st.writer = holder
            return None
        if st.writer is not None:
            return st.writer
        st.readers[holder] = st.readers.get(holder, 0) + 1
        return None


def _unregister(key: str, mode: str, holder: str) -> None:
    with _STATE_GUARD:
        st = _STATES.get(key)
        if st is None:
            return
        if mode == EXCLUSIVE:
            st.writer = None
        else:
            left = st.readers.get(holder, 0) - 1
            if left > 0:
                st.readers[holder] = left
            else:
                st.readers.pop(holder, None)


# --------------------------------------------------------------------------- category record


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _parse_category(raw: bytes) -> str:
    parts = raw.decode("ascii", errors="replace").split()
    if len(parts) != 2 or parts[0] not in CATEGORIES:
        return UNKNOWN
    try:
        pid = int(parts[1])
    except ValueError:
        return UNKNOWN
    return parts[0] if _pid_alive(pid) else UNKNOWN


def _read_category(fd: int, deadline: float) -> str:
    """Best-effort holder category. Re-reads briefly while the record is still empty.

    The settle window is ``min(_CATEGORY_SETTLE_S, deadline - now)`` on the injected
    clock (#20): a refusal never lands later than the deadline it is refusing at.
    """
    give_up = min(_monotonic() + _CATEGORY_SETTLE_S, deadline)
    while True:
        try:
            got = _parse_category(os.pread(fd, _RECORD_BYTES, 0))
        except OSError:
            got = UNKNOWN
        now = _monotonic()
        if got != UNKNOWN or now >= give_up:
            return got
        _sleep(min(_CATEGORY_POLL_S, give_up - now))


def _write_category(fd: int, text: str) -> None:
    record = text.encode("ascii", errors="replace")[: _RECORD_BYTES - 1].ljust(_RECORD_BYTES - 1) + b"\n"
    with contextlib.suppress(OSError):
        os.pwrite(fd, record, 0)


# --------------------------------------------------------------------------- acquire


@contextlib.contextmanager
def acquire(
    books_dir: str,
    book_folder: str,
    *,
    mode: str = SHARED,
    holder: str,
    deadline: Optional[float] = None,
    budget: Optional[float] = None,
) -> Iterator[None]:
    """Hold the book lock in ``mode`` for the body; release on every exit path.

    ``deadline`` is absolute on ``_monotonic``. ``budget`` is a duration instead,
    turned into a deadline *here*, at the start of the acquisition -- callers with a
    short budget pass that, so work done before the lock is requested does not eat
    into it. Neither means now + ``BUDGET_S``; both is a ``ValueError``.
    A layer that succeeds at or after the deadline is released and refused.
    Exclusive never waits. Raises ``BookLockBusy`` on refusal, ``ValueError`` on an
    unsafe folder name (before anything is created), and a ``BookLockMisuse``
    subclass on same-thread re-entry, SH→EX upgrade, or book-inside-resource order.
    """
    if mode not in (SHARED, EXCLUSIVE):
        raise ValueError(f"unknown book lock mode: {mode!r}")
    if deadline is not None and budget is not None:
        raise ValueError("pass a deadline or a budget, not both")
    if holder not in CATEGORIES:
        raise ValueError(f"unknown book lock holder category: {holder!r}")
    folder = _safe_folder(book_folder)
    key = _key(books_dir, folder)

    if _resource_depth() > 0:
        raise BookLockOrderError("a book lock was requested while holding a resource lock (order is book → resource)")
    held = _held()
    if key in held:
        if held[key][0] == SHARED and mode == EXCLUSIVE:
            raise BookLockUpgrade(f"shared → exclusive upgrade on {folder!r} is not allowed")
        raise BookLockReentry(f"this thread already holds the book lock on {folder!r}")

    if deadline is None:
        deadline = _monotonic() + (BUDGET_S if budget is None else budget)

    # 审计 #41：``_unregister`` 在最外层 finally 里，由 ``registered`` 守着 -- 拆锁时
    # ``os.close`` 抛错也不会留下一个进程内的僵尸持有者。第一层的轮询也在这个 try
    # 里面（#19）。
    registered = False
    fd = -1
    locked = False
    try:
        # Layer 1: the in-process reader/writer table.
        last = UNKNOWN
        while True:
            now = _monotonic()
            if now >= deadline:
                raise BookLockBusy(last)
            blocking = _register(key, mode, holder)
            if blocking is None:
                registered = True
                if _monotonic() >= deadline:
                    raise BookLockBusy(last)
                break
            if mode == EXCLUSIVE:
                raise BookLockBusy(blocking)
            last = blocking
            _sleep(min(POLL_S, deadline - now))

        # Layer 2: flock across processes.
        path = lock_path(books_dir, folder)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        flag = fcntl.LOCK_EX if mode == EXCLUSIVE else fcntl.LOCK_SH
        while True:
            try:
                fcntl.flock(fd, flag | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                pass
            now = _monotonic()
            if locked and now < deadline:
                break
            if locked or mode == EXCLUSIVE or now >= deadline:
                # A late success is refused like a failure; the finally unlocks it.
                raise BookLockBusy(_read_category(fd, deadline))
            _sleep(min(POLL_S, deadline - now))

        _write_category(fd, f"{holder} {os.getpid()}")
        held[key] = (mode, deadline)
        try:
            yield
        finally:
            held.pop(key, None)
            if mode == EXCLUSIVE:
                _write_category(fd, "")
    finally:
        try:
            if fd >= 0:
                if locked:
                    # Suppressed: the close below releases the flock anyway.
                    with contextlib.suppress(OSError):
                        fcntl.flock(fd, fcntl.LOCK_UN)
                # Propagates; the finally still empties the table.
                os.close(fd)
        finally:
            if registered:
                _unregister(key, mode, holder)


# --------------------------------------------------------------------------- resource locks


@contextlib.contextmanager
def resource_lock(
    books_dir: str,
    book_folder: str,
    *,
    category: str,
    path: Optional[str] = None,
    thread_lock: Optional[threading.Lock] = None,
) -> Iterator[None]:
    """Hold one writer's own resource lock for the body (ADR-0015 item 2).

    Must be taken *inside* this thread's book lock on the same book: its deadline is
    read back from that acquisition, so the one budget covers the in-process table,
    the book flock and this lock -- not a budget each. Without a book lock it raises
    ``BookLockOrderError`` before creating anything.

    Two layers, polled against that deadline and refused as ``BookLockBusy(category)``:
      * a per-path ``threading.Lock`` for two threads of this process;
      * ``flock(LOCK_EX)`` on the lock file for other processes.
    While held the thread is inside ``resource_section()``, so a book lock requested
    from the body is an order error rather than a deadlock.

    ``path`` defaults to ``books/.locks/{category}/{folder}.lock``, created on demand
    and never unlinked; nothing inside the book dir is ever created. ``thread_lock``
    lets a caller keep its own registry (notes does, and its tests reach into it).
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown resource lock category: {category!r}")
    folder = _safe_folder(book_folder)
    deadline = held_deadline(books_dir, folder)
    if deadline is None:
        raise BookLockOrderError(
            f"{category} resource lock for {folder!r} requested without the book lock (order is book → resource)"
        )
    if path is None:
        path = _resource_lock_path(books_dir, folder, category)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    if thread_lock is None:
        with _RESOURCE_GUARD:
            thread_lock = _RESOURCE_THREAD_LOCKS.setdefault(os.path.realpath(path), threading.Lock())

    with resource_section():
        # Same rule as ``acquire``: each layer is accepted only before the deadline; a
        # late success is released by the finally below and refused.
        got_thread_lock = False
        fd = -1
        locked = False
        try:
            while True:
                now = _monotonic()
                if now >= deadline:
                    raise BookLockBusy(category)
                if thread_lock.acquire(False):
                    got_thread_lock = True
                    if _monotonic() >= deadline:
                        raise BookLockBusy(category)
                    break
                _sleep(min(POLL_S, deadline - now))
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError:
                    pass
                now = _monotonic()
                if now >= deadline:
                    raise BookLockBusy(category)
                if locked:
                    break
                _sleep(min(POLL_S, deadline - now))
            yield
        finally:
            try:
                if fd >= 0:
                    try:
                        if locked:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
            finally:
                if got_thread_lock:
                    thread_lock.release()


# --------------------------------------------------------------------------- identity


def _normalise_uuid(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return str(_uuid.UUID(text))
    except ValueError:
        return text


def read_book_uuid(books_dir: str, book_folder: str) -> Optional[str]:
    """The book's ``book_uuid`` as ``ai_meta.json`` holds it now; ``None`` on any failure.

    Read-only and tolerant on purpose: it is an identity *snapshot* for the ABA
    check, not the place that decides what to do with an unreadable meta file.
    """
    try:
        path = os.path.join(books_dir, _safe_folder(book_folder), _AI_META_FILENAME)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("book_uuid")
    if not isinstance(raw, str):
        return None
    return _normalise_uuid(raw)


@contextlib.contextmanager
def writer_scope(
    books_dir: str,
    book_folder: str,
    *,
    holder: str,
    expected_book_uuid: object = NO_UUID_CHECK,
    deadline: Optional[float] = None,
    budget: Optional[float] = None,
) -> Iterator[None]:
    """A shared writer's whole operation: SH, then in-lock existence and identity rechecks.

    ``BookGone`` if the book dir is not there (never recreated); ``BookChanged`` if
    ``expected_book_uuid`` was given and the folder now holds another identity.
    ``None`` is an identity like any other, so ``None → None`` passes -- the
    documented non-guarantee of ADR-0015.
    """
    folder = _safe_folder(book_folder)
    # Module-global lookup at call time, not a bound reference: a substituted
    # ``acquire`` must see every writer's acquisition.
    with acquire(books_dir, folder, mode=SHARED, holder=holder, deadline=deadline, budget=budget):
        if not os.path.isdir(os.path.join(books_dir, folder)):
            raise BookGone(f"book {folder!r} was removed; refusing to recreate it")
        if expected_book_uuid is not NO_UUID_CHECK:
            current = read_book_uuid(books_dir, folder)
            if current != _normalise_uuid(expected_book_uuid):
                raise BookChanged(f"book {folder!r} changed identity while the request was in flight")
        yield
