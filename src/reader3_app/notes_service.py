from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import threading
from typing import Iterator, List

from .models.annotations import Annotation
from .safe_paths import safe_book_folder


class NotesFileError(RuntimeError):
    """Raised when notes.json exists but cannot be understood."""


NOTES_FILENAME = "notes.json"
NOTES_LOCK_FILENAME = "notes.json.lock"
NOTES_SCHEMA_VERSION = 1

# One threading.Lock per book, keyed by the absolute lock-file path. Bounded by
# the number of books ever written to in this process, so it is never evicted.
_LOCK_REGISTRY_GUARD = threading.Lock()
_BOOK_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _notes_path(books_dir: str, book_id: str) -> str:
    """校验在拼路径之前，也就在任何读写之前。

    这里以前一次校验都没有：``_notes_path(books, "..")`` 直接给出
    ``books/../notes.json``，而 ``add_annotation`` 是 load → append → save
    整份文件，一次越权写就把库根之外那份标注覆盖掉。标注不可再生。
    """
    return os.path.join(books_dir, safe_book_folder(book_id), NOTES_FILENAME)


def _lock_path(books_dir: str, book_id: str) -> str:
    return os.path.join(books_dir, safe_book_folder(book_id), NOTES_LOCK_FILENAME)


@contextlib.contextmanager
def _book_write_lock(books_dir: str, book_id: str) -> Iterator[None]:
    """Serialise one book's read-modify-write against every other writer.

    ``add_annotation`` is load -> append -> save *the whole file*. Two writers
    interleaving inside that window each read N records and each write N+1, and
    the disk keeps N+1: one highlight is gone, with no exception anywhere.
    ``os.replace`` cannot help — the race is between the read and the write, not
    inside the write — so the only fix is to hold a lock across all three steps.

    Two layers, because they cover different escapes:
      * a per-book ``threading.Lock`` for two requests inside one server process;
      * ``fcntl.flock`` on ``notes.json.lock`` for two *processes* — a second
        uvicorn worker, or the CLI running beside a live server.

    POSIX only. ``fcntl`` does not exist on Windows, which this project does not
    support (macOS and Linux only); if that ever changes, this is the line that
    has to grow a branch, and a silent no-op lock would be the wrong branch.

    The lock file is separate from ``notes.json`` on purpose: locking the data
    file itself would mean holding a descriptor to an inode that ``os.replace``
    is about to swap out, so each writer would end up locking a different inode.

    Granularity is one book, not one library: two books' writers never wait on
    each other.
    """
    path = _lock_path(books_dir, book_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    key = os.path.abspath(path)
    with _LOCK_REGISTRY_GUARD:
        thread_lock = _BOOK_THREAD_LOCKS.setdefault(key, threading.Lock())

    with thread_lock:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def load_annotations(books_dir: str, book_id: str) -> List[Annotation]:
    """Read every annotation for a book, or refuse.

    A file that is missing means "this book has no annotations yet" — a legal
    state, and the only one that yields ``[]``. A file that exists but cannot be
    understood means we do not know what the user has, and there is exactly one
    caller-visible way to say that without lying: raise.

    The reason this is not a "be lenient in what you accept" situation is
    ``add_annotation``: it is load → append → save *the whole file*. Anything
    this function silently omits from its return value is deleted from disk by
    the next highlight the user makes, with no error anywhere. Annotations are
    not regenerable.
    """
    path = _notes_path(books_dir, book_id)
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise NotesFileError(
            f"{path} is not valid JSON ({e}); refusing to treat it as an empty "
            "annotation list — the next saved highlight would overwrite it"
        ) from e
    except OSError as e:
        raise NotesFileError(
            f"{path} exists but could not be read ({e}); refusing to treat it as "
            "an empty annotation list — the next saved highlight would overwrite it"
        ) from e

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise NotesFileError(
            f"{path} is not a JSON object (got {type(data).__name__}); refusing to "
            "treat it as an empty annotation list — the next saved highlight would "
            "overwrite it"
        )

    # The hole WI-6 left open: WI-6 refuses an "annotations" field that is not a
    # list, but a *missing* field is not "not a list". A file from a later schema
    # may well have renamed it (012 plans to); `data.get("annotations")` then
    # returns None, the next lines normalise that to `[]`, and the user's
    # annotations are reported as absent while they sit in the file under
    # another name -- after which `add_annotation` saves the emptiness over
    # them. Measured, not inferred: it cost a hand-written v2 file its records.
    #
    # This sits above that lookup, but be honest about what the placement buys:
    # nothing observable. Moving it below the normalisation kills no test,
    # because every placement before the `return` still refuses and therefore
    # still stops `add_annotation` from writing. The reason to keep it first is
    # maintenance, not behaviour -- it keeps the "we cannot read this file"
    # decision ahead of the code that would otherwise conclude "there is nothing
    # in this file", so a future edit to the latter cannot silently reopen this.
    found_version = data.get("schema_version")
    if found_version is not None and (
        not isinstance(found_version, int)
        or isinstance(found_version, bool)
        or found_version > NOTES_SCHEMA_VERSION
    ):
        raise NotesFileError(
            f"{path} declares schema_version {found_version!r}, but this reader "
            f"only understands version {NOTES_SCHEMA_VERSION}; refusing to treat "
            "it as an empty annotation list — the next saved highlight would "
            "overwrite it"
        )

    items = data.get("annotations")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise NotesFileError(
            f"{path} has an \"annotations\" field that is not a list (got "
            f"{type(items).__name__}); refusing to treat it as an empty annotation "
            "list — the next saved highlight would overwrite it"
        )

    out: List[Annotation] = []
    for index, raw in enumerate(items):
        try:
            out.append(Annotation.from_dict(raw))
        except Exception as e:  # noqa: BLE001 - Annotation.from_dict raises ValueError / TypeError / AttributeError depending on which field is wrong; the point here is that *no* failure mode may be dropped
            # Deliberate trade-off, and it is not the comfortable one: a single
            # malformed record now 500s every notes endpoint for this book,
            # rather than costing the user only that record. That is the right
            # way round. A 500 is loud, bounded and recoverable — the file is
            # still on disk and a human can fix it. The alternative, skipping
            # the record, is silent and permanent: the very next
            # add_annotation writes the survivors back and the skipped record
            # ceases to exist. We prefer an outage over a deletion.
            raise NotesFileError(
                f"{path} contains an annotation at index {index} that could not be "
                f"read ({e}); refusing to drop it — the next saved highlight would "
                "erase it permanently"
            ) from e
    return out


def save_annotations(books_dir: str, book_id: str, annotations: List[Annotation]) -> None:
    """Write the whole annotation list, atomically.

    Callers that read-modify-write must hold ``_book_write_lock``; this function
    does not take it, so that it stays a plain atomic write with no reentrancy
    question (``flock`` is per open-file-description — taking it twice in one
    call stack would deadlock).

    Payload shape is deliberately unchanged here: 012 owns the schema.
    """
    path = _notes_path(books_dir, book_id)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)

    payload = {
        "schema_version": NOTES_SCHEMA_VERSION,
        "book_id": book_id,
        "annotations": [a.to_dict() for a in annotations],
    }

    # tmp name from tempfile.mkstemp(dir=...), not a fixed f"{path}.tmp" — same
    # reasoning as ai/config.py:save_ai_settings, and the same one-line cost. A
    # hard-coded temp name is shared state: two writers open *one inode*, both
    # stream a payload into it at their own offsets, and whichever renames first
    # publishes an interleaving of the two while the other's os.replace fails
    # with ENOENT, having dropped the annotation it was asked to persist.
    fd, tmp_path = tempfile.mkstemp(prefix=".notes.", suffix=".tmp", dir=directory)
    try:
        try:
            # fdopen takes ownership of fd; only an fdopen failure leaves it ours.
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            # Publish only what is actually on the platter: without the fsync,
            # os.replace can make the new name visible while the bytes behind it
            # are still in the page cache, and a crash leaves an empty file where
            # the annotations were.
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Failed halfway: the old file is untouched. Take the half-written tmp
        # with us rather than leaving fragments beside the user's annotations.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_annotation(books_dir: str, annotation: Annotation) -> Annotation:
    with _book_write_lock(books_dir, annotation.book_id):
        annotations = load_annotations(books_dir, annotation.book_id)
        annotations.append(annotation)
        save_annotations(books_dir, annotation.book_id, annotations)
    return annotation


def delete_annotation(books_dir: str, book_id: str, note_id: str) -> bool:
    with _book_write_lock(books_dir, book_id):
        annotations = load_annotations(books_dir, book_id)
        before = len(annotations)
        annotations = [a for a in annotations if a.id != note_id]
        if len(annotations) == before:
            return False
        save_annotations(books_dir, book_id, annotations)
    return True


def update_annotation(books_dir: str, book_id: str, note_id: str, note_text: str) -> Annotation | None:
    """Update note_text for an existing annotation. Returns updated annotation or None if not found."""
    with _book_write_lock(books_dir, book_id):
        annotations = load_annotations(books_dir, book_id)
        for ann in annotations:
            if ann.id == note_id:
                ann.note_text = note_text
                save_annotations(books_dir, book_id, annotations)
                return ann
    return None
