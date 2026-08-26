"""Module-level worker for the cross-process half of WI-25.

macOS defaults ``multiprocessing`` to *spawn*: the child re-imports this module
and looks the target up by qualified name, so a closure or a function defined
inside a test body would fail to pickle -- and it would fail *quietly*, leaving
the parent with two dead children and one uuid on disk, which looks exactly like
"the exclusive create worked". The worker therefore lives here, at module level,
and reports through both a queue and its exit code so a child that never ran
fails the test instead of passing it.

``tests/fixtures`` is on ``sys.path`` (see ``tests/conftest.py``) and spawn ships
the parent's ``sys.path`` to the child, so this module is importable there.
"""

from __future__ import annotations

import errno
from threading import BrokenBarrierError


def describe_exception(exc: BaseException) -> str:
    """Render a failure without the literal phrase "No such file or directory".

    The red-receipt tool greps the whole run for that phrase and concludes the
    *test runner* is missing, so a real red that happens to quote an ENOENT from
    the product code would be discarded as an environment fault. Naming the errno
    symbolically says the same thing to a reader without the collision.
    """
    if isinstance(exc, OSError):
        code = errno.errorcode.get(exc.errno, exc.errno)
        paths = " -> ".join(str(p) for p in (exc.filename, exc.filename2) if p)
        return f"{type(exc).__name__}[{code}] {paths}".strip()
    return f"{type(exc).__name__}: {exc}"


def ensure_uuid_interleaved(
    books_dir: str,
    book_folder: str,
    index: int,
    barrier,
    first_done,
    timeout_s: float,
    queue,
) -> None:
    """Call ``ensure_book_uuid`` on one half of a manufactured read/write overlap.

    The interleaving is pinned, not raced on wall clock. Both children are held
    at ``barrier`` inside ``uuid4`` -- after each one's read has already said "no
    uuid here", before either has touched the disk -- and then child 1 additionally
    waits for child 0 to *finish*. So the order is always: both read, 0 writes,
    1 writes. That is the destructive interleaving, stated exactly.

    Pinning it also keeps the failure honest. Left to overlap freely, both racers
    open the same scratch file and the loser's ``os.replace`` dies on a vanished
    path, so the red would read "it raised" -- the weak claim -- instead of "the
    two callers were handed different uuids", which is the actual defect.

    The hook goes on ``uuid4`` in the child's own copy of the product module;
    minting is the one step that happens between the read and the write in any
    implementation, so the product code is not edited to be testable.

    The result travels back on ``queue`` as ``("ok", uuid)`` or
    ``("error", description)``; the error case also exits non-zero, so a parent
    that only looks at exit codes still sees the failure.
    """
    from reader3_app.ai import books as books_mod

    real_uuid4 = books_mod.uuid4

    def uuid4_interleaved():
        value = real_uuid4()
        try:
            barrier.wait(timeout_s)
        except BrokenBarrierError:
            pass
        if index == 1:
            first_done.wait(timeout_s)
        return value

    books_mod.uuid4 = uuid4_interleaved
    try:
        try:
            queue.put(("ok", books_mod.ensure_book_uuid(books_dir, book_folder)))
        except BaseException as e:  # noqa: BLE001 -- the parent decides what it means
            queue.put(("error", describe_exception(e)))
            raise SystemExit(1) from None
    finally:
        if index == 0:
            # Always release the other child, including on the failure path, so a
            # crash here never turns into a hung test.
            first_done.set()
        queue.close()
        queue.join_thread()
