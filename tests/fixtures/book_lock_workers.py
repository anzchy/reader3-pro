"""Spawn-safe child-process workers for the 018 WI-2 book-lock tests (ADR-0015).

Every function here runs in a *spawned* interpreter, so each one lives at module
level and takes only picklable arguments. Outcomes are reported as JSON written to
``result_path``; rendezvous happens on ``multiprocessing`` Events / Barriers, never
on sleeps. Every wait is bounded by ``CHILD_WAIT_S`` so a regression gives the
parent a red, not a hang.

Outcome vocabulary shared by the parent tests:
    ``"acquired"``                 the child got the lock it asked for
    ``"busy:<holder_category>"``   ``BookLockBusy`` with that category
    ``"passed-barrier"``           the child held the lock while crossing a barrier
    ``"error:<Type>:<msg>"``       anything else

The embedding function substitute (``HashEmbedder``) also lives here, so the same
deterministic 8-dim embedder can be used in-process and in a child.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

#: Upper bound on any single wait inside a child.
CHILD_WAIT_S = 30.0


def write_result(result_path: str, payload: Dict[str, Any]) -> None:
    tmp = f"{result_path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, result_path)


def read_result(result_path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _busy_payload(exc: BaseException) -> Dict[str, Any]:
    return {
        "outcome": f"busy:{getattr(exc, 'holder_category', '?')}",
        "type": type(exc).__name__,
        "retry_after": getattr(exc, "retry_after", None),
        "is_runtime_error": isinstance(exc, RuntimeError),
    }


def _error_payload(exc: BaseException) -> Dict[str, Any]:
    return {"outcome": f"error:{type(exc).__name__}:{exc}", "type": type(exc).__name__}


# --------------------------------------------------------------------------- lock holders


def hold(
    books_dir: str,
    book_folder: str,
    mode: str,
    holder: str,
    ready_evt,
    release_evt,
    result_path: str,
    released_evt=None,
) -> None:
    """Acquire ``mode`` and hold it until ``release_evt``; then (optionally) signal release."""
    from reader3_app import book_lock

    try:
        with book_lock.acquire(books_dir, book_folder, mode=mode, holder=holder):
            write_result(result_path, {"outcome": "acquired"})
            ready_evt.set()
            release_evt.wait(CHILD_WAIT_S)
    except book_lock.BookLockBusy as exc:
        write_result(result_path, _busy_payload(exc))
        ready_evt.set()
        return
    except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
        write_result(result_path, _error_payload(exc))
        ready_evt.set()
        raise
    if released_evt is not None:
        released_evt.set()


def hold_forever(books_dir: str, book_folder: str, mode: str, holder: str, ready_evt) -> None:
    """Acquire and then sleep until killed (bounded)."""
    from reader3_app import book_lock

    with book_lock.acquire(books_dir, book_folder, mode=mode, holder=holder):
        ready_evt.set()
        time.sleep(CHILD_WAIT_S)


def hold_at_barrier(
    books_dir: str, book_folder: str, mode: str, holder: str, barrier, result_path: str
) -> None:
    """Hold ``mode`` while crossing ``barrier`` -- proves two holders coexist."""
    from reader3_app import book_lock

    try:
        with book_lock.acquire(books_dir, book_folder, mode=mode, holder=holder):
            barrier.wait(10)
            write_result(result_path, {"outcome": "passed-barrier"})
    except book_lock.BookLockBusy as exc:
        write_result(result_path, _busy_payload(exc))
    except BaseException as exc:  # noqa: BLE001
        write_result(result_path, _error_payload(exc))


def try_exclusive(
    books_dir: str,
    book_folder: str,
    holder: str,
    result_path: str,
    barrier=None,
    release_evt=None,
) -> None:
    """One non-blocking EX attempt. A winner holds until ``release_evt`` (if given).

    A winner reports ``"acquired"`` only after the ``with`` has exited, i.e. once its
    teardown has released the lock (#49): a parent that sees the result can rely on
    the lock being free. A teardown error is recorded as ``"error:..."`` and re-raised,
    so the child exits nonzero instead of reporting a clean win. A parent that needs
    to observe the winner *while it holds* waits for the losers' results instead.
    """
    from reader3_app import book_lock

    if barrier is not None:
        barrier.wait(CHILD_WAIT_S)
    try:
        with book_lock.acquire(books_dir, book_folder, mode="exclusive", holder=holder):
            if release_evt is not None:
                release_evt.wait(CHILD_WAIT_S)
    except book_lock.BookLockBusy as exc:
        write_result(result_path, _busy_payload(exc))
        return
    except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised for a nonzero exit
        write_result(result_path, _error_payload(exc))
        raise
    write_result(result_path, {"outcome": "acquired"})


#: Suffix of the file ``try_exclusive_close_fails`` writes at its failing ``close``.
AT_CLOSE_SUFFIX = ".at-close"


def try_exclusive_close_fails(books_dir: str, book_folder: str, holder: str, result_path: str) -> None:
    """FX-5-04 test-only worker: ``try_exclusive`` whose book-lock teardown ``close`` raises once.

    Only ``book_lock.os`` is replaced (module-local, never a global ``os.close``). The
    shim really closes the fd, then -- before raising ``OSError`` -- records in
    ``result_path + AT_CLOSE_SUFFIX`` whether the result file already existed. That
    tells the parent "reported after teardown" apart from "reported while holding".
    """
    import errno

    from reader3_app import book_lock

    real_os = book_lock.os
    armed = [True]

    class _CloseFailsOnce:
        def close(self, fd: int) -> None:
            real_os.close(fd)
            if armed[0]:
                armed[0] = False
                write_result(result_path + AT_CLOSE_SUFFIX, {"result_existed": real_os.path.exists(result_path)})
                raise OSError(errno.EIO, "close failed")

        def __getattr__(self, name: str) -> Any:
            return getattr(real_os, name)

    book_lock.os = _CloseFailsOnce()  # type: ignore[assignment]
    try_exclusive(books_dir, book_folder, holder, result_path)


def acquire_ex_when_free(
    books_dir: str, book_folder: str, holder: str, holds_evt, release_evt, result_path: str
) -> None:
    """Loop on non-blocking EX until it succeeds, set ``holds_evt``, hold until release."""
    from reader3_app import book_lock

    give_up = time.monotonic() + CHILD_WAIT_S
    while time.monotonic() < give_up:
        try:
            with book_lock.acquire(books_dir, book_folder, mode="exclusive", holder=holder):
                write_result(result_path, {"outcome": "acquired"})
                holds_evt.set()
                release_evt.wait(CHILD_WAIT_S)
                return
        except book_lock.BookLockBusy:
            time.sleep(0.01)
    write_result(result_path, {"outcome": "error:gave-up"})


def raw_flock_probe(lock_file: str, op: str, result_path: str) -> None:
    """A raw ``flock(LOCK_EX|LOCK_NB)`` / ``flock(LOCK_SH|LOCK_NB)`` on the lock file."""
    flag = fcntl.LOCK_EX if op == "EX" else fcntl.LOCK_SH
    if not os.path.exists(lock_file):
        # Reported as an outcome, never as a traceback: an ENOENT traceback's text is
        # what the red-receipt tool reads as "the runner is missing".
        write_result(result_path, {"outcome": "missing"})
        return
    fd = os.open(lock_file, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, flag | fcntl.LOCK_NB)
        except BlockingIOError:
            write_result(result_path, {"outcome": "blocked"})
            return
        fcntl.flock(fd, fcntl.LOCK_UN)
        write_result(result_path, {"outcome": "ok"})
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- notes writers


def _annotation(book_folder: str, quote: str):
    from reader3_app.models.annotations import Annotation

    return Annotation(
        book_id=book_folder,
        chapter_index=0,
        type="marker",
        color="yellow",
        quote=quote,
    )


def add_annotation_parked(
    books_dir: str,
    book_folder: str,
    quote: str,
    parked_evt,
    release_evt,
    result_path: str,
    park_s: float = CHILD_WAIT_S,
) -> None:
    """A notes writer that parks inside ``save_annotations`` -- holding SH + the resource lock."""
    from reader3_app import book_lock, notes_service

    real_save = notes_service.save_annotations

    def parked_save(*a, **kw):
        parked_evt.set()
        release_evt.wait(park_s)
        return real_save(*a, **kw)

    notes_service.save_annotations = parked_save
    try:
        notes_service.add_annotation_and_version(books_dir, _annotation(book_folder, quote))
        write_result(result_path, {"outcome": "acquired"})
    except book_lock.BookLockBusy as exc:
        write_result(result_path, _busy_payload(exc))
    except BaseException as exc:  # noqa: BLE001
        write_result(result_path, _error_payload(exc))
    finally:
        notes_service.save_annotations = real_save


# --------------------------------------------------------------------------- process_epub


def _run_process_epub(epub_path: str, output_dir: str, result_path: str) -> None:
    from reader3_app import book_lock, reader3

    try:
        book = reader3.process_epub(epub_path, output_dir)
        write_result(result_path, {"outcome": "acquired", "title": book.metadata.title})
    except book_lock.BookLockBusy as exc:
        write_result(result_path, _busy_payload(exc))
    except BaseException as exc:  # noqa: BLE001
        write_result(result_path, _error_payload(exc))


def process_epub_run(epub_path: str, output_dir: str, result_path: str) -> None:
    _run_process_epub(epub_path, output_dir, result_path)


def process_epub_paused(
    epub_path: str, output_dir: str, paused_evt, go_evt, result_path: str
) -> None:
    """``process_epub`` that pauses inside ``_build_into_staging`` (this child's namespace)."""
    from reader3_app import reader3

    real_build = reader3._build_into_staging

    def paused_build(*a, **kw):
        paused_evt.set()
        go_evt.wait(CHILD_WAIT_S)
        return real_build(*a, **kw)

    reader3._build_into_staging = paused_build
    _run_process_epub(epub_path, output_dir, result_path)


def process_epub_paused_at_publish(
    epub_path: str, output_dir: str, publishing_evt, go_evt, result_path: str
) -> None:
    """``process_epub`` that pauses right before ``_commit_staged_artifacts``."""
    from reader3_app import reader3

    real_commit = reader3._commit_staged_artifacts

    def paused_commit(*a, **kw):
        publishing_evt.set()
        go_evt.wait(CHILD_WAIT_S)
        return real_commit(*a, **kw)

    reader3._commit_staged_artifacts = paused_commit
    _run_process_epub(epub_path, output_dir, result_path)


# --------------------------------------------------------------------------- embedding substitute


class HashEmbedder:
    """Deterministic 8-dim hash embedder: the only stand-in for the real model.

    chromadb itself stays real. ``on_first_call`` lets a test pause the indexer
    mid-embedding (W2-50) without touching any internal symbol.
    """

    def __init__(self, on_first_call=None) -> None:
        self._on_first_call = on_first_call
        self._called = False
        self._guard = threading.Lock()

    def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002 - chromadb's protocol name
        with self._guard:
            first = not self._called
            self._called = True
        if first and self._on_first_call is not None:
            self._on_first_call()
        out: List[List[float]] = []
        for text in input:
            digest = hashlib.sha256(str(text).encode("utf-8")).digest()
            out.append([b / 255.0 + 0.01 for b in digest[:8]])
        return out

    @staticmethod
    def name() -> str:
        return "reader3-test-hash8"

    def get_config(self) -> Dict[str, Any]:
        return {}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "HashEmbedder":
        return HashEmbedder()

    def is_legacy(self) -> bool:
        return False


# --------------------------------------------------------------------------- parent-side helpers
#
# Used by the parent tests only; they never run in a child. Kept here so the five
# WI-2 test modules share one definition of "start a child, wait for it, reap it".

#: Hard cap on a child's lifetime as seen from the parent.
CHILD_TIMEOUT_S = 60.0


def spawn_ctx():
    import multiprocessing

    return multiprocessing.get_context("spawn")


class Child:
    """One spawned worker plus its result file."""

    def __init__(self, target, args: tuple, result_path: str) -> None:
        self.result_path = result_path
        self.proc = spawn_ctx().Process(target=target, args=args, daemon=True)

    def start(self) -> "Child":
        self.proc.start()
        return self

    def wait_result(self, timeout: float = CHILD_WAIT_S) -> Optional[Dict[str, Any]]:
        """Poll for the child's JSON result (bounded). ``None`` if it never wrote one."""
        give_up = time.monotonic() + timeout
        while time.monotonic() < give_up:
            got = read_result(self.result_path)
            if got is not None:
                return got
            if not self.proc.is_alive() and self.proc.exitcode is not None:
                return read_result(self.result_path)
            time.sleep(0.01)
        return None

    def reap(self, timeout: float = CHILD_TIMEOUT_S) -> Optional[int]:
        self.proc.join(timeout)
        if self.proc.is_alive():
            self.proc.kill()
            self.proc.join(5)
        return self.proc.exitcode


def outcome(result: Optional[Dict[str, Any]]) -> Optional[str]:
    return None if result is None else result.get("outcome")


def probe(lock_file: str, op: str, tmp_dir: str) -> Optional[str]:
    """Run a raw flock probe in a fresh child; return ``"ok"`` / ``"blocked"``."""
    import uuid as _uuid

    path = os.path.join(tmp_dir, f"probe-{_uuid.uuid4().hex}.json")
    child = Child(raw_flock_probe, (lock_file, op, path), path).start()
    got = child.wait_result()
    code = child.reap()
    assert code == 0, f"probe child exited {code}"
    return outcome(got)


class Holder:
    """A child that holds a book lock until told to release.

    ``start()`` waits for the child to report; a child that failed to acquire makes
    ``start()`` raise ``AssertionError`` naming what it reported instead, so a broken
    lock never lets a test proceed as if the holder were in place.
    """

    def __init__(self, books_dir: str, book_folder: str, mode: str, holder: str, tmp_dir: str) -> None:
        import uuid as _uuid

        ctx = spawn_ctx()
        self.ready = ctx.Event()
        self.release_evt = ctx.Event()
        self.released = ctx.Event()
        path = os.path.join(tmp_dir, f"holder-{_uuid.uuid4().hex}.json")
        self.child = Child(
            hold,
            (str(books_dir), book_folder, mode, holder, self.ready, self.release_evt, path, self.released),
            path,
        )

    def start(self) -> "Holder":
        self.child.start()
        got = self.child.wait_result()
        assert outcome(got) == "acquired", f"the holder child did not acquire its lock: {got!r}"
        assert self.ready.wait(CHILD_WAIT_S), "the holder child never became ready"
        return self

    def release(self) -> Optional[int]:
        self.release_evt.set()
        return self.child.reap()

    def __enter__(self) -> "Holder":
        return self.start()

    def __exit__(self, *exc) -> None:
        code = self.release()
        if exc[0] is None:
            assert code == 0, f"holder child exited {code}"


# --------------------------------------------------------------------------- in-process interposer


@contextlib.contextmanager
def _interpose_acquire(monkeypatch: Any, before: Callable[[], None]) -> Iterator[List[int]]:
    """Wrap ``book_lock.acquire``: run ``before`` once (on the first call), then delegate.

    Parent-side only (moved here from the WI-2 test modules, #15). Yields ``[1]`` once
    the first call has been intercepted, so ``fired == [1]`` reads "the writer took
    the book lock". ``_interpose_acquire_counting`` counts every call instead.
    Restores the real ``acquire`` on exit.
    """
    with _interpose(monkeypatch, before, count_all=False) as fired:
        yield fired


@contextlib.contextmanager
def _interpose_acquire_counting(monkeypatch: Any, before: Callable[[], None]) -> Iterator[List[int]]:
    """``_interpose_acquire`` that appends on *every* call, so ``len(calls)`` counts acquisitions."""
    with _interpose(monkeypatch, before, count_all=True) as calls:
        yield calls


@contextlib.contextmanager
def _interpose(monkeypatch: Any, before: Callable[[], None], *, count_all: bool) -> Iterator[List[int]]:
    from reader3_app import book_lock

    real = book_lock.acquire
    calls: List[int] = []

    @contextlib.contextmanager
    def wrapper(*args: Any, **kwargs: Any) -> Iterator[None]:
        first = not calls
        if first or count_all:
            calls.append(1)
        if first:
            before()
        with real(*args, **kwargs):
            yield

    monkeypatch.setattr(book_lock, "acquire", wrapper)
    try:
        yield calls
    finally:
        monkeypatch.setattr(book_lock, "acquire", real)
