from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
import threading
from typing import Iterator, List, Optional, Tuple

from .models.annotations import Annotation
from .safe_paths import safe_book_folder


class NotesFileError(RuntimeError):
    """Raised when notes.json exists but cannot be understood."""


class NotesVersionConflict(RuntimeError):
    """A write arrived holding a version that is no longer the current one.

    This is the *only* thing ``_book_write_lock`` cannot catch. The lock closes
    the window between one writer's load and its own save; it says nothing about
    a client that read the file at T0, was overtaken at T1, and submits at T2 a
    payload computed from what it saw at T0. Both writes are individually
    well-formed and individually serialised — and the earlier one is gone.

    Carries the server's current version and, when the request named a single
    annotation, that annotation as the server currently holds it. The caller
    needs both: the version to retry with, and the remote text to show the user
    beside their own before anything is discarded.
    """

    def __init__(self, current_version: str, current_annotation: Optional[Annotation] = None) -> None:
        super().__init__(
            f"the current notes version is {current_version}, which the caller did not hold"
        )
        self.current_version = current_version
        self.current_annotation = current_annotation


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


def annotations_version(annotations: List[Annotation]) -> str:
    """A version token for one book's annotations, derived from their content.

    Hashes the *logical* content — the canonical (sorted-key) JSON of every
    record — and not the bytes of ``notes.json``. The difference is not
    cosmetic: 012 owns the on-disk schema and will reformat that file (indent,
    key order, possibly field names). A byte-derived token would invalidate
    every live client's version on the day of that reformat, with not one
    annotation changed, and every one of those clients would be shown a conflict
    dialog it cannot act on.

    Nothing is stored. ``notes.json`` gains no field and ``NOTES_SCHEMA_VERSION``
    stays 1 — a version that is a function of the content needs no home of its
    own, and Phase 3 requires the file's bytes to survive migration unchanged.

    Granularity is **one version per book**, and that is a choice with a known,
    accepted cost: A adding a highlight in chapter 3 invalidates B's version
    while B edits an unrelated note in chapter 7, so B gets a conflict dialog it
    did not earn. Per-annotation versioning would avoid that, and would also
    fail to describe the operations that are not about one annotation (create,
    delete, and any future reorder). Book granularity is what
    ``load_annotations``/``save_annotations`` already work in — the whole list,
    always — so it is the granularity the writes actually have. Do not "fix"
    this into per-annotation versions without first giving the file a
    per-annotation write path.
    """
    canonical = json.dumps(
        [a.to_dict() for a in annotations],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_etag(value: str) -> str:
    """Reduce the three spellings of one ``If-Match`` value to the bare token.

    Clients, proxies and hand-written ``curl`` lines send ``"v"``, ``v`` and
    ``W/"v"`` for the same version. Treating those as different versions costs a
    *false* conflict, and a dialog that fires when nothing is wrong is how users
    learn to dismiss the dialog that matters.
    """
    token = value.strip()
    if token.startswith("W/"):
        token = token[2:].strip()
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    return token


def _require_version(
    annotations: List[Annotation],
    if_match: Optional[str],
    note_id: Optional[str],
) -> None:
    """Compare-and-swap, first half. **Callers must already hold the book lock.**

    Comparing outside the lock would be theatre: two requests would each read
    the same version, each pass, and then write in turn — exactly the lost
    update this function exists to refuse, with a conflict check on top of it.
    So this is a module-private helper called from inside the ``with`` block,
    never from the router.

    ``if_match is None`` means the client did not opt in, and then every write
    behaves exactly as it did before optimistic concurrency existed. That is
    what keeps the frozen response shapes (ADR-0011) intact for every existing
    caller.
    """
    if if_match is None:
        return

    current = annotations_version(annotations)
    if normalize_etag(if_match) == current:
        return

    current_annotation: Optional[Annotation] = None
    if note_id is not None:
        for ann in annotations:
            if ann.id == note_id:
                current_annotation = ann
                break
    raise NotesVersionConflict(current, current_annotation)


def add_annotation_and_version(
    books_dir: str,
    annotation: Annotation,
    if_match: Optional[str] = None,
) -> Tuple[Annotation, str]:
    """Append one annotation; return it together with the resulting version.

    ``note_id`` is ``None`` in the version check on purpose: a create has no
    "the server's copy of this annotation" to report back, because the thing
    being created does not exist on the server. The conflict still fires — a
    client that chose to send ``If-Match`` said its create was based on a list
    it had seen — but it carries only the current version.
    """
    with _book_write_lock(books_dir, annotation.book_id):
        annotations = load_annotations(books_dir, annotation.book_id)
        _require_version(annotations, if_match, None)
        annotations.append(annotation)
        save_annotations(books_dir, annotation.book_id, annotations)
        return annotation, annotations_version(annotations)


def delete_annotation_and_version(
    books_dir: str,
    book_id: str,
    note_id: str,
    if_match: Optional[str] = None,
) -> Tuple[bool, str]:
    """Delete by id; return whether it was there, and the resulting version.

    The version check runs *before* the "was it there" check, so a stale client
    whose target has already been deleted by someone else is told 409, not 404.
    404 invites a retry ("wrong id?"); 409 says what actually happened —
    something you did not see has changed here, re-read it.
    """
    with _book_write_lock(books_dir, book_id):
        annotations = load_annotations(books_dir, book_id)
        _require_version(annotations, if_match, note_id)
        before = len(annotations)
        annotations = [a for a in annotations if a.id != note_id]
        if len(annotations) == before:
            return False, annotations_version(annotations)
        save_annotations(books_dir, book_id, annotations)
        return True, annotations_version(annotations)


def update_annotation_and_version(
    books_dir: str,
    book_id: str,
    note_id: str,
    note_text: str,
    if_match: Optional[str] = None,
) -> Tuple[Optional[Annotation], str]:
    """Update note_text; return the updated annotation (or None) and the version."""
    with _book_write_lock(books_dir, book_id):
        annotations = load_annotations(books_dir, book_id)
        _require_version(annotations, if_match, note_id)
        for ann in annotations:
            if ann.id == note_id:
                ann.note_text = note_text
                save_annotations(books_dir, book_id, annotations)
                return ann, annotations_version(annotations)
        return None, annotations_version(annotations)


def add_annotation(books_dir: str, annotation: Annotation) -> Annotation:
    return add_annotation_and_version(books_dir, annotation)[0]


def delete_annotation(books_dir: str, book_id: str, note_id: str) -> bool:
    return delete_annotation_and_version(books_dir, book_id, note_id)[0]


def update_annotation(books_dir: str, book_id: str, note_id: str, note_text: str) -> Annotation | None:
    """Update note_text for an existing annotation. Returns updated annotation or None if not found."""
    return update_annotation_and_version(books_dir, book_id, note_id, note_text)[0]
