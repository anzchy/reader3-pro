from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import threading
from typing import Callable, Iterator, List, Optional, Tuple, Union

from . import book_lock, book_store
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
#: Top-level key in notes.json naming the book content the annotations were made against
#: (012 WI-2a.6). Additive, so NOTES_SCHEMA_VERSION stays 1: older readers ignore it.
#: Must equal tests/fixtures/deg_assertions.NOTES_FINGERPRINT_KEY.
NOTES_FINGERPRINT_KEY = "book_fingerprint"


class _Keep:
    """Type of :data:`KEEP`: ``save_annotations`` carries the file's existing fingerprint."""

    def __repr__(self) -> str:
        return "KEEP"


#: ``save_annotations(..., book_fingerprint=KEEP)``: carry whatever the current file holds.
#: 2b.2: every mutator passes ``_advance_target``'s result -- KEEP or an explicit str, never None.
KEEP = _Keep()


class _NoFingerprintCheck:
    """Type of :data:`NO_FINGERPRINT_CHECK`."""

    def __repr__(self) -> str:
        return "NO_FINGERPRINT_CHECK"


#: ``refresh_annotations_and_version(..., book_fingerprint=NO_FINGERPRINT_CHECK)``: run ``refresh``
#: unconditionally. A distinct sentinel because ``None`` is a real Book fingerprint ("pkl-only").
NO_FINGERPRINT_CHECK = _NoFingerprintCheck()
#: The holder category notes writers report, for both the book lock and the resource lock.
RESOURCE_CATEGORY = "notes"

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
    # 018 WI-2 (ADR-0015 contract items 2, 4, 5): this is the *resource* layer under
    # the book lock -- no book-dir creation, no blocking, one deadline for all layers.
    # 018 WI-1: the body is now the shared ``book_lock.resource_lock``. Notes keeps
    # its in-dir ``notes.json.lock`` and its own thread-lock registry (ADR-0015 item 2);
    # the order check there still refuses before any fd is opened.
    key = os.path.abspath(path)
    with _LOCK_REGISTRY_GUARD:
        thread_lock = _BOOK_THREAD_LOCKS.setdefault(key, threading.Lock())
    with book_lock.resource_lock(
        books_dir, book_id, category=RESOURCE_CATEGORY, path=path, thread_lock=thread_lock
    ):
        yield


@contextlib.contextmanager
def _notes_write(
    books_dir: str,
    book_id: str,
    expected_book_uuid: object,
    deadline: Optional[float],
) -> Iterator[None]:
    """Book lock (SH, in-lock existence + identity recheck) → notes resource lock."""
    with book_lock.writer_scope(
        books_dir,
        book_id,
        holder=RESOURCE_CATEGORY,
        expected_book_uuid=expected_book_uuid,
        deadline=deadline,
    ):
        with _book_write_lock(books_dir, book_id):
            yield


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
    except UnicodeDecodeError as e:
        raise NotesFileError(
            f"{path} is not valid UTF-8 ({e}); refusing to treat it as an empty "
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
            out.append(Annotation.from_dict(raw, index=index))
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


def _existing_fingerprint(path: str) -> object:
    """The current file's top-level fingerprint, or ``None`` when there is nothing to carry.

    Best-effort on purpose: a missing, unreadable, corrupt or non-object file carries
    nothing, and the save goes ahead exactly as it did before 2a.6. Refusing here would
    turn a lost *marker* into a lost *annotation* -- ``load_annotations`` is the gate
    that refuses to overwrite a file it cannot read, not this.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get(NOTES_FINGERPRINT_KEY)


def fingerprints_agree(notes_fp: object, book_fp: object) -> bool:
    """ADR-0019 section 三 (D-1): may a GET make orphan judgements for this pair?

    True only when both are missing (notes key absent or null, Book ``None`` -- the legacy row)
    or both are equal strs. Everything else -- str vs ``None`` either way, two different strs,
    or a non-str notes value -- is False: skip. Pure.
    """
    if notes_fp is None and book_fp is None:
        return True
    return isinstance(notes_fp, str) and isinstance(book_fp, str) and notes_fp == book_fp


#: The resolutions under which an annotation does not block the notes fingerprint from advancing.
_SETTLED = frozenset({"resolved", "accepted"})


def _advance_target(annotations: List[Annotation], current_fp: object, existing: object) -> Union[str, _Keep]:
    """What the notes-level ``book_fingerprint`` should be after a save: ``current_fp`` or ``KEEP``.

    012 WI-2b.2, ADR-0019 section 四 (D-4 plus ruling 4). Advances to ``current_fp`` only when
    all of these hold, and otherwise carries the existing value (``KEEP``):

    - ``current_fp`` is a str (``None`` means "cannot judge", never "drop");
    - ``existing`` is absent/``None`` or a str -- a non-str value on disk is never overwritten;
    - every non-orphaned annotation is ``resolved`` or ``accepted`` **and** bound to
      ``current_fp``. The bound check stops a delete between an import and its rebind from
      advancing on stale ``resolved`` flags. The empty set qualifies, so deleting the last
      blocking annotation advances.

    Pure. Never returns ``None``, so a save driven by it never writes a null.
    """
    if not isinstance(current_fp, str):
        return KEEP
    if existing is not None and not isinstance(existing, str):
        return KEEP
    for ann in annotations:
        if ann.orphaned:
            continue
        if ann.resolution not in _SETTLED or ann.bound_fingerprint != current_fp:
            return KEEP
    return current_fp


def _recomputed_fingerprint(books_dir: str, book_id: str, annotations: List[Annotation]) -> Union[str, _Keep]:
    """The ``book_fingerprint=`` argument for a save. **Callers must hold ``_notes_write``.**

    Reads the current generation's fingerprint and the file's existing value inside the
    caller's lock, on the post-mutation list. ``book_store.book_fingerprint`` is called through
    the module attribute so test seams on it bind.
    """
    current = book_store.book_fingerprint(book_id, books_dir)
    return _advance_target(annotations, current, _existing_fingerprint(_notes_path(books_dir, book_id)))


def save_annotations(
    books_dir: str,
    book_id: str,
    annotations: List[Annotation],
    *,
    book_fingerprint: Union[str, None, _Keep] = KEEP,
) -> None:
    """Write the whole annotation list, atomically.

    Callers that read-modify-write must hold ``_book_write_lock``; this function
    does not take it, so that it stays a plain atomic write with no reentrancy
    question (``flock`` is per open-file-description — taking it twice in one
    call stack would deadlock).

    Payload is ``{schema_version, book_id, annotations}`` plus, when known, the
    top-level ``NOTES_FINGERPRINT_KEY``. With the default ``KEEP`` the current
    file's value is carried verbatim (read under the caller's lock); a file
    without the key stays without it, and ``null`` is never written. A ``str``
    stamps that value; ``None`` drops the key. Since 012 WI-2b.2 every mutator
    passes ``_advance_target``'s result (a str or ``KEEP``), never ``None``.
    """
    path = _notes_path(books_dir, book_id)
    # No makedirs (018 WI-2, ADR-0015 contract item 5): a missing book dir means the
    # book was deleted, and recreating it would resurrect a partial book. mkstemp
    # below raises FileNotFoundError instead.
    directory = os.path.dirname(path)

    fingerprint = _existing_fingerprint(path) if isinstance(book_fingerprint, _Keep) else book_fingerprint

    payload: dict[str, object] = {
        "schema_version": NOTES_SCHEMA_VERSION,
        "book_id": book_id,
        "annotations": [a.to_dict() for a in annotations],
    }
    if fingerprint is not None:
        payload[NOTES_FINGERPRINT_KEY] = fingerprint

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


def refresh_annotations_and_version(
    books_dir: str,
    book_id: str,
    refresh: Callable[[List[Annotation]], bool],
    *,
    expected_book_uuid: object = book_lock.NO_UUID_CHECK,
    deadline: Optional[float] = None,
    book_fingerprint: object = NO_FINGERPRINT_CHECK,
) -> Tuple[List[Annotation], str]:
    """load → 让调用者改 → 改动了就 save，**全程握着同一把书级锁**。

    这里存在的理由，是读路由也会写盘。`GET /api/notes/{book_id}` 的孤儿刷新发现某条
    标注在正文里找不到了，就把它标成 ``orphaned`` 并重写整份文件——那是一次货真价实的
    load → 改 → save，和 add/delete/update 一模一样，唯独它从前不进队（017 WI-4，审计 #1）：

        GET  load → [ann1 活, ann2 "旧"]          （不在锁里）
        PUT  load → 改 ann2 → save → 200 OK       （在锁里，If-Match 也对得上）
        GET  save → [ann1 orphaned, ann2 "旧"]    （把 T0 的快照拍下去）

    PUT 提交的那一版无声消失，而客户端手里拿着一个 200。乐观并发看不见这件事，因为比较
    只在写口里做，而这个写者不是写口。**任何 read-modify-write 都必须在这把锁里**，
    「它是个 GET」不是例外。

    ``refresh`` 必须是纯粹的「改这份列表，返回改没改」：它在锁里跑，做的任何 I/O 都在
    加长别人的等待。返回的是**整份**标注（含 orphaned 的那些），因为 ETag 算的是整本书。

    012 WI-2b.3（ADR-0019 第三节）：传了 ``book_fingerprint``（请求那份 ``Book`` 的指纹，
    ``None`` 也是一个真值）时，先在**锁内**读 notes 顶层指纹，``fingerprints_agree`` 不成立就
    不调 ``refresh``、不写盘，原样返回读到的列表——锁外读会漏掉「锁前刚完成的导入 ＋ rebind」。
    默认 ``NO_FINGERPRINT_CHECK`` 不做比对，其余调用者行为不变。
    """
    with _notes_write(books_dir, book_id, expected_book_uuid, deadline):
        annotations = load_annotations(books_dir, book_id)
        if book_fingerprint is not NO_FINGERPRINT_CHECK and not fingerprints_agree(
            _existing_fingerprint(_notes_path(books_dir, book_id)), book_fingerprint
        ):
            return annotations, annotations_version(annotations)
        if refresh(annotations):
            target = _recomputed_fingerprint(books_dir, book_id, annotations)
            save_annotations(books_dir, book_id, annotations, book_fingerprint=target)
        return annotations, annotations_version(annotations)


def add_annotation_and_version(
    books_dir: str,
    annotation: Annotation,
    if_match: Optional[str] = None,
    *,
    expected_book_uuid: object = book_lock.NO_UUID_CHECK,
    deadline: Optional[float] = None,
) -> Tuple[Annotation, str]:
    """Append one annotation; return it together with the resulting version.

    ``note_id`` is ``None`` in the version check on purpose: a create has no
    "the server's copy of this annotation" to report back, because the thing
    being created does not exist on the server. The conflict still fires — a
    client that chose to send ``If-Match`` said its create was based on a list
    it had seen — but it carries only the current version.

    012 WI-2b.2 (ADR-0019 section 五, D-3): the new annotation is stamped in the lock --
    ``resolution="resolved"`` and ``bound_fingerprint = evaluated_fingerprint`` = the current
    generation's fingerprint read *here*, not from the request-time ``Book`` (both ``None``
    for a book with no generation). ``chapter_href`` is the caller's (the route sets it).
    """
    book_id = annotation.book_id
    with _notes_write(books_dir, book_id, expected_book_uuid, deadline):
        annotations = load_annotations(books_dir, book_id)
        _require_version(annotations, if_match, None)
        current = book_store.book_fingerprint(book_id, books_dir)
        annotation.resolution = "resolved"
        annotation.bound_fingerprint = current
        annotation.evaluated_fingerprint = current
        annotations.append(annotation)
        target = _advance_target(annotations, current, _existing_fingerprint(_notes_path(books_dir, book_id)))
        save_annotations(books_dir, book_id, annotations, book_fingerprint=target)
        return annotation, annotations_version(annotations)


def delete_annotation_and_version(
    books_dir: str,
    book_id: str,
    note_id: str,
    if_match: Optional[str] = None,
    *,
    expected_book_uuid: object = book_lock.NO_UUID_CHECK,
    deadline: Optional[float] = None,
) -> Tuple[bool, str]:
    """Delete by id; return whether it was there, and the resulting version.

    The version check runs *before* the "was it there" check, so a stale client
    whose target has already been deleted by someone else is told 409, not 404.
    404 invites a retry ("wrong id?"); 409 says what actually happened —
    something you did not see has changed here, re-read it.
    """
    with _notes_write(books_dir, book_id, expected_book_uuid, deadline):
        annotations = load_annotations(books_dir, book_id)
        _require_version(annotations, if_match, note_id)
        before = len(annotations)
        annotations = [a for a in annotations if a.id != note_id]
        if len(annotations) == before:
            return False, annotations_version(annotations)
        target = _recomputed_fingerprint(books_dir, book_id, annotations)
        save_annotations(books_dir, book_id, annotations, book_fingerprint=target)
        return True, annotations_version(annotations)


def update_annotation_and_version(
    books_dir: str,
    book_id: str,
    note_id: str,
    note_text: str,
    if_match: Optional[str] = None,
    *,
    expected_book_uuid: object = book_lock.NO_UUID_CHECK,
    deadline: Optional[float] = None,
) -> Tuple[Optional[Annotation], str]:
    """Update note_text; return the updated annotation (or None) and the version."""
    with _notes_write(books_dir, book_id, expected_book_uuid, deadline):
        annotations = load_annotations(books_dir, book_id)
        _require_version(annotations, if_match, note_id)
        for ann in annotations:
            if ann.id == note_id:
                ann.note_text = note_text
                target = _recomputed_fingerprint(books_dir, book_id, annotations)
                save_annotations(books_dir, book_id, annotations, book_fingerprint=target)
                return ann, annotations_version(annotations)
        return None, annotations_version(annotations)


def add_annotation(books_dir: str, annotation: Annotation) -> Annotation:
    return add_annotation_and_version(books_dir, annotation)[0]


def delete_annotation(books_dir: str, book_id: str, note_id: str) -> bool:
    return delete_annotation_and_version(books_dir, book_id, note_id)[0]


def update_annotation(books_dir: str, book_id: str, note_id: str, note_text: str) -> Annotation | None:
    """Update note_text for an existing annotation. Returns updated annotation or None if not found."""
    return update_annotation_and_version(books_dir, book_id, note_id, note_text)[0]
