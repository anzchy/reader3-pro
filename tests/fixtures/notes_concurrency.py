"""Module-level workers for the cross-process half of WI-23.

macOS defaults ``multiprocessing`` to *spawn*: the child re-imports the target's
module and looks the function up by qualified name. A closure, a lambda, or a
function defined inside a test body would fail to pickle, and the failure is the
quiet kind -- the parent sees two dead children and an unchanged file, which
looks exactly like "the lock worked". So the workers live here, at module level,
and every caller asserts on ``proc.exitcode`` so that a child which died on
import fails the test instead of passing it.

``tests/fixtures`` is on ``sys.path`` (see ``tests/conftest.py``), and spawn
ships the parent's ``sys.path`` to the child, so this module is importable there.
"""

from __future__ import annotations

from threading import BrokenBarrierError


def add_annotation_at_barrier(
    books_dir: str,
    book_id: str,
    quote: str,
    barrier,
    timeout_s: float,
) -> None:
    """Add one annotation, pausing at ``barrier`` between the load and the save.

    The pause is what widens the read-modify-write window to something a test can
    hit every time. It is deliberately placed by wrapping ``save_annotations`` in
    the child's own module namespace rather than by editing the product code.

    ``barrier.wait`` is given a timeout because a correct implementation makes the
    rendezvous *impossible*: the second writer is parked on the file lock and can
    never arrive. The timeout is the escape from that deadlock, not a window
    manufactured with wall clock -- when the lock is missing, both writers arrive
    at once and the timeout never elapses.
    """
    from reader3_app import notes_service
    from reader3_app.models.annotations import Annotation

    real_save = notes_service.save_annotations

    def save_at_barrier(bd, bid, anns):
        try:
            barrier.wait(timeout_s)
        except BrokenBarrierError:
            pass
        return real_save(bd, bid, anns)

    notes_service.save_annotations = save_at_barrier
    try:
        notes_service.add_annotation(
            books_dir,
            Annotation(book_id=book_id, chapter_index=0, quote=quote),
        )
    except OSError as e:
        # Report the errno by name and exit non-zero, instead of letting
        # multiprocessing print a traceback. An ENOENT traceback carries the
        # string "No such file or directory", which the red-receipt tool greps
        # for across the entire run as evidence that the *test runner* is
        # missing -- and would discard a perfectly real red. The parent still
        # sees exitcode 1 and still fails.
        print(f"child writer for {book_id!r} failed: {type(e).__name__} errno={e.errno}", flush=True)
        raise SystemExit(1) from None
