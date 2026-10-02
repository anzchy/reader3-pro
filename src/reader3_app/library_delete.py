"""Crash-safe library delete: intent, commit rename, finalize, sweep (018 WI-5a).

The protocol, in the order ``delete_book`` runs it (each name is a ``STEPS`` entry,
fired *after* its action):

1. ``swept`` -- finish (or conserve) whatever an earlier crashed delete left behind.
2. ``locked`` -- the book's EX lock, holder ``"delete"``; held to the end.
3. ``intent_written`` -- ``.{folder}.deleted-{pid}-{token}.intent.json`` records every
   input the finalizer needs (conversation root, collections file, uuid, mode), so a
   sweep in another process never consults settings or the web layer.
4. ``committed`` -- ``rename(folder -> .{folder}.deleted-{pid}-{token})``. This is the
   commit point: before it nothing user-visible changed; after it the book is gone
   from the listing and the finalizer must run to completion, now or in a later sweep.
5. ``fin_collections`` / ``fin_caches`` / ``conv_published`` / ``conv_done`` /
   ``rmtree_done`` / ``intent_removed`` -- the finalizer, idempotent under a crash at
   any point.

False mode (``delete_conversations=False``) moves the book's conversations into the
project-root store ``{root}/{uuid}/``; a file the finalizer cannot place is never
dropped -- the whole tombstone is conserved instead. True mode removes ``{root}/{uuid}``.

This module must not import ``reader3_app.web``: the server reaches in through
``register_invalidator`` instead (call-time lambdas), so a CLI or startup sweep works
without the web stack.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import UUID

from . import book_lock, book_store, collections_service, search_service, vector_search
from .safe_paths import safe_book_folder

logger = logging.getLogger(__name__)

STEPS: Tuple[str, ...] = (
    "swept",
    "locked",
    "intent_written",
    "committed",
    "fin_collections",
    "fin_caches",
    "conv_published",
    "conv_done",
    "rmtree_done",
    "intent_removed",
)

#: Test-only observation point; ``None`` in production. Nothing in ``src/`` sets it.
_STEP_HOOK: Optional[Callable[[str], None]] = None

_AI_META = "ai_meta.json"
_CONV_DIR = "ai_conversations"
_CHROMA_DIR = "chroma_db"

_PID = r"(?P<pid>0|[1-9][0-9]*)"
_TOKEN = r"(?P<token>[0-9a-f]{8})"
TOMBSTONE_RE = re.compile(r"\.(?P<folder>.+_data)\.deleted-" + _PID + r"(?:-" + _TOKEN + r")?\Z", re.DOTALL)
INTENT_RE = re.compile(r"\.(?P<folder>.+_data)\.deleted-" + _PID + r"-" + _TOKEN + r"\.intent\.json\Z", re.DOTALL)

PathLike = Union[str, "os.PathLike[str]"]
Invalidator = Callable[[str, Optional[str]], None]


def _step(name: str) -> None:
    hook = _STEP_HOOK
    if hook is not None:
        hook(name)


# --------------------------------------------------------------------------- errors


class DeleteRefused(Exception):
    """The delete was refused before the commit point; nothing changed.

    ``reason``: ``"conversation_root"``, ``"book_uuid"`` or ``"conversation_unreadable"``
    (then ``path`` is the offending file's basename).
    """

    def __init__(self, reason: str, path: Optional[str] = None) -> None:
        self.reason = reason
        self.path = path
        super().__init__(reason if path is None else f"{reason}: {path}")


class IntentUnreadable(ValueError):
    """An intent file that cannot be trusted; its tombstone is conserved."""


class ConversationUnreadable(ValueError):
    """A conversation file ``plan_publish`` cannot place (``reason`` names the check)."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{os.path.basename(path)}: {reason}")


# --------------------------------------------------------------------------- names


def _parse_folder(folder: str) -> Optional[str]:
    try:
        return safe_book_folder(folder)
    except ValueError:
        return None


def tombstone_name(folder: str, pid: int, token: Optional[str]) -> str:
    base = f".{folder}.deleted-{pid}"
    return base if token is None else f"{base}-{token}"


def intent_name(folder: str, pid: int, token: str) -> str:
    return f"{tombstone_name(folder, pid, token)}.intent.json"


def _parse(regex: "re.Pattern[str]", name: str) -> Optional[Tuple[str, int, Optional[str]]]:
    m = regex.match(name)
    if m is None:
        return None
    folder = _parse_folder(m.group("folder"))
    if folder is None:
        return None
    return (folder, int(m.group("pid")), m.group("token"))


def parse_tombstone(name: str) -> Optional[Tuple[str, int, Optional[str]]]:
    """``(folder, pid, token)`` for a tombstone basename (``token`` is ``None`` for a legacy one)."""
    return _parse(TOMBSTONE_RE, name)


def parse_intent(name: str) -> Optional[Tuple[str, int, Optional[str]]]:
    """``(folder, pid, token)`` for an intent basename, else ``None``."""
    return _parse(INTENT_RE, name)


def _canonical_uuid(value: Any) -> Optional[str]:
    """``str(UUID(value))`` for a string that parses as a UUID; ``None`` otherwise."""
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------- durable writes


def _fsync_dir(directory: PathLike) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_durably(directory: str, final: str, payload: bytes, *, prefix: str, mode: Optional[int] = None) -> None:
    """Temp file in ``directory`` -> fsync at full size -> ``os.replace`` -> fsync the directory.

    Same-directory only, so the rename never crosses a filesystem. On any failure
    the temp file is removed and the error re-raised.
    """
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=".tmp")
    try:
        try:
            if mode is not None:
                os.fchmod(fd, mode)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(directory)


# --------------------------------------------------------------------------- intent


@dataclass(frozen=True)
class DeleteIntent:
    folder: str
    pid: int
    token: str
    delete_conversations: bool
    book_uuid: Optional[str]
    conversation_root: Optional[str]
    collections_path: str

    def to_json(self) -> Dict[str, Any]:
        return {
            "folder": self.folder,
            "pid": self.pid,
            "token": self.token,
            "delete_conversations": self.delete_conversations,
            "book_uuid": self.book_uuid,
            "conversation_root": self.conversation_root,
            "collections_path": self.collections_path,
        }


def write_intent(books_dir: PathLike, intent: DeleteIntent) -> str:
    """Publish the intent durably next to the book; returns its path."""
    directory = os.fspath(books_dir)
    final = os.path.join(directory, intent_name(intent.folder, intent.pid, intent.token))
    payload = json.dumps(intent.to_json(), ensure_ascii=False).encode("utf-8")
    _write_durably(directory, final, payload, prefix=".delete-intent-")
    return final


def read_intent(path: PathLike) -> DeleteIntent:
    """Parse an intent file; ``IntentUnreadable`` for anything that cannot be trusted.

    A ``book_uuid`` that is not a UUID reads as ``None`` (it would otherwise become
    a path component under the conversation root).
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise IntentUnreadable(f"{os.path.basename(os.fspath(path))}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise IntentUnreadable(f"{os.path.basename(os.fspath(path))}: not JSON") from exc
    if not isinstance(data, dict):
        raise IntentUnreadable("intent is not an object")

    folder = data.get("folder")
    pid = data.get("pid")
    token = data.get("token")
    mode = data.get("delete_conversations")
    root = data.get("conversation_root")
    coll = data.get("collections_path")
    if not isinstance(folder, str) or _parse_folder(folder) is None or not folder.endswith("_data"):
        raise IntentUnreadable("bad folder")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 0:
        raise IntentUnreadable("bad pid")
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{8}", token) is None:
        raise IntentUnreadable("bad token")
    if not isinstance(mode, bool):
        raise IntentUnreadable("bad delete_conversations")
    if root is not None and (not isinstance(root, str) or not os.path.isabs(root)):
        raise IntentUnreadable("conversation_root must be null or an absolute path")
    if not isinstance(coll, str) or not os.path.isabs(coll):
        raise IntentUnreadable("collections_path must be an absolute path")
    return DeleteIntent(
        folder=folder,
        pid=pid,
        token=token,
        delete_conversations=mode,
        book_uuid=_canonical_uuid(data.get("book_uuid")),
        conversation_root=root,
        collections_path=coll,
    )


def commit_tombstone(books_dir: PathLike, intent: DeleteIntent) -> str:
    """The commit point: rename the book folder onto its tombstone, then fsync ``books_dir``.

    A missing source is ``book_lock.BookGone``. Returns the tombstone path.
    """
    directory = os.fspath(books_dir)
    src = os.path.join(directory, intent.folder)
    dst = os.path.join(directory, tombstone_name(intent.folder, intent.pid, intent.token))
    if os.path.lexists(dst):
        raise FileExistsError(f"tombstone {os.path.basename(dst)!r} already exists")
    try:
        os.rename(src, dst)
    except FileNotFoundError as exc:
        raise book_lock.BookGone(f"book folder {intent.folder!r} is gone") from exc
    _fsync_dir(directory)
    return dst


# --------------------------------------------------------------------------- publish planning


def lu_key(value: Any) -> str:
    """The ordering key of a ``last_updated`` value: a string keys as itself, anything else as ``""``."""
    return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class PublishItem:
    src: Path
    dst: Path
    last_updated: str


def _conversation_files(conv_dir: PathLike) -> List[str]:
    try:
        names = os.listdir(conv_dir)
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted(n for n in names if n.endswith(".json"))


def plan_publish(conv_dir: PathLike, *, root: PathLike, fallback_uuid: Optional[str]) -> List[PublishItem]:
    """Where every conversation in ``conv_dir`` goes, sorted by filename; never writes.

    Raises ``ConversationUnreadable`` at the first file (in that order) that fails:
    ``filename`` (stem not a canonical UUID), ``json``, ``not_object``,
    ``conversation_id`` (present but not the stem), ``uuid`` (neither the file's own
    ``book_uuid`` nor ``fallback_uuid`` is a UUID), ``target`` (an existing copy at the
    destination is not a JSON object).
    """
    out: List[PublishItem] = []
    for name in _conversation_files(conv_dir):
        src = Path(conv_dir) / name
        stem = name[: -len(".json")]
        if _canonical_uuid(stem) != stem:
            raise ConversationUnreadable(str(src), "filename")
        try:
            data = json.loads(src.read_bytes())
        except IsADirectoryError as exc:
            raise ConversationUnreadable(str(src), "json") from exc
        except ValueError as exc:
            raise ConversationUnreadable(str(src), "json") from exc
        if not isinstance(data, dict):
            raise ConversationUnreadable(str(src), "not_object")
        if "conversation_id" in data and data["conversation_id"] != stem:
            raise ConversationUnreadable(str(src), "conversation_id")
        target = _canonical_uuid(data.get("book_uuid")) or _canonical_uuid(fallback_uuid)
        if target is None:
            raise ConversationUnreadable(str(src), "uuid")
        dst = Path(root) / target / name
        if os.path.lexists(dst) and _read_object(dst) is None:
            raise ConversationUnreadable(str(src), "target")
        out.append(PublishItem(src=src, dst=dst, last_updated=lu_key(data.get("last_updated"))))
    return out


def _read_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- invalidators


_INVALIDATORS: List[Tuple[Invalidator, bool]] = []


def register_invalidator(fn: Invalidator, *, folder_scoped: bool) -> Callable[[], None]:
    """Call ``fn(folder, book_uuid)`` after every finalize; returns an unregister callable.

    ``folder_scoped`` invalidators drop per-folder state and are skipped when a live
    book of the same name exists; the others (global caches) always run.
    """
    entry = (fn, folder_scoped)
    _INVALIDATORS.append(entry)

    def unregister() -> None:
        registry = _INVALIDATORS
        for i, existing in enumerate(registry):
            if existing is entry:
                del registry[i]
                return

    return unregister


def _run_invalidators(folder: str, book_uuid: Optional[str], *, folder_scoped: bool) -> None:
    for fn, scoped in list(_INVALIDATORS):
        if scoped != folder_scoped:
            continue
        try:
            fn(folder, book_uuid)
        except Exception as exc:  # noqa: BLE001 - one stale cache must not stop the others or the delete
            logger.error("invalidator %r failed for %s: %s", fn, folder, exc)


def _invalidate(books_dir: str, folder: str, book_uuid: Optional[str], *, folder_scoped: bool) -> None:
    # The cache surface is attached to the public names (see book_store / search_service).
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    search_service.load_book_index.cache_clear()  # type: ignore[attr-defined]
    _run_invalidators(folder, book_uuid, folder_scoped=False)
    if folder_scoped:
        _run_invalidators(folder, book_uuid, folder_scoped=True)
        vector_search.retire_chroma_system(os.path.realpath(os.path.join(books_dir, folder, _CHROMA_DIR)))


# --------------------------------------------------------------------------- finalize


@dataclass
class FinalizeResult:
    done: bool
    conserved: bool
    live_same_name: bool


def _conserve(tomb: str, reason: str) -> FinalizeResult:
    logger.warning("delete: tombstone %s conserved, nothing removed: %s", tomb, reason)
    return FinalizeResult(done=False, conserved=True, live_same_name=False)


def _should_publish(item: PublishItem) -> bool:
    if not os.path.lexists(item.dst):
        return True
    existing = _read_object(item.dst)
    if existing is None:
        raise ConversationUnreadable(str(item.src), "target")
    return item.last_updated > lu_key(existing.get("last_updated"))


def _publish(item: PublishItem) -> None:
    parent = item.dst.parent
    os.makedirs(parent, exist_ok=True)
    payload = item.src.read_bytes()
    mode = stat.S_IMODE(os.stat(item.src).st_mode)
    _write_durably(os.fspath(parent), os.fspath(item.dst), payload, prefix=f".{item.dst.name}.", mode=mode)


def _remove_conversation_dir(intent: DeleteIntent) -> None:
    root, book_uuid = intent.conversation_root, intent.book_uuid
    if root is None:
        logger.warning("delete of %s: no conversation root recorded; its conversations were not removed", intent.folder)
        return
    if book_uuid is None:
        logger.warning("delete of %s: no valid book_uuid recorded; its conversations were not removed", intent.folder)
        return
    target = os.path.join(root, book_uuid)
    if os.path.islink(target) or os.path.isfile(target):
        os.unlink(target)
    elif os.path.isdir(target):
        shutil.rmtree(target)


def finalize_tombstone(books_dir: PathLike, tombstone: PathLike, intent: Optional[DeleteIntent]) -> FinalizeResult:
    """Finish one committed delete. Idempotent: safe to re-run after a crash at any step.

    Conserves (one WARNING, no other effect) when there is no intent, or in false mode
    when the conversations cannot all be placed. Other errors propagate and leave the
    tombstone and intent for the next sweep.
    """
    directory = os.fspath(books_dir)
    tomb_name = os.path.basename(os.fspath(tombstone))
    tomb = os.path.join(directory, tomb_name)
    if intent is None:
        return _conserve(tomb_name, "no readable intent")

    conv_dir = os.path.join(tomb, _CONV_DIR)
    items: List[PublishItem] = []
    if not intent.delete_conversations and _conversation_files(conv_dir):
        if intent.conversation_root is None:
            return _conserve(tomb_name, "conversations present but no conversation root recorded")
        try:
            items = plan_publish(conv_dir, root=intent.conversation_root, fallback_uuid=intent.book_uuid)
        except ConversationUnreadable as exc:
            return _conserve(tomb_name, f"conversation {os.path.basename(exc.path)} is unreadable ({exc.reason})")

    live = intent.folder in search_service.list_book_ids(directory)
    if live:
        logger.info("delete: a live book named %s exists; collections and its caches are kept", intent.folder)
    else:
        collections_service.remove_book_everywhere(Path(intent.collections_path), intent.folder)
    _step("fin_collections")

    _invalidate(directory, intent.folder, intent.book_uuid, folder_scoped=not live)
    _step("fin_caches")

    if intent.delete_conversations:
        _remove_conversation_dir(intent)
    else:
        for item in items:
            if _should_publish(item):
                _publish(item)
                _step("conv_published")
    _step("conv_done")

    if os.path.lexists(tomb):
        shutil.rmtree(tomb)
    _step("rmtree_done")

    try:
        os.unlink(os.path.join(directory, intent_name(intent.folder, intent.pid, intent.token)))
    except FileNotFoundError:
        pass
    _step("intent_removed")
    return FinalizeResult(done=True, conserved=False, live_same_name=live)


# --------------------------------------------------------------------------- sweep


@dataclass
class SweepReport:
    finalized: List[str] = field(default_factory=list)
    orphan_intents: List[str] = field(default_factory=list)
    conserved: List[str] = field(default_factory=list)
    busy: List[str] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


Triple = Tuple[str, int, Optional[str]]


def _entries(books_dir: str) -> Tuple[Dict[Triple, str], Dict[Triple, str]]:
    try:
        names = os.listdir(books_dir)
    except FileNotFoundError:
        return {}, {}
    tombs: Dict[Triple, str] = {}
    intents: Dict[Triple, str] = {}
    for name in names:
        parsed = parse_tombstone(name)
        if parsed is not None:
            tombs[parsed] = name
            continue
        parsed = parse_intent(name)
        if parsed is not None:
            intents[parsed] = name
    return tombs, intents


def _sweep_folder(books_dir: str, folder: str, report: SweepReport) -> None:
    """Re-list and classify ``folder``'s entries; the caller holds its EX lock."""
    tombs, intents = _entries(books_dir)
    tombs = {k: v for k, v in tombs.items() if k[0] == folder}
    intents = {k: v for k, v in intents.items() if k[0] == folder}

    for triple in sorted(tombs, key=lambda t: tombs[t]):
        tomb = tombs[triple]
        try:
            intent_file = intents.pop(triple, None)
            intent: Optional[DeleteIntent] = None
            if intent_file is not None:
                try:
                    intent = read_intent(os.path.join(books_dir, intent_file))
                    if (intent.folder, intent.pid, intent.token) != triple:
                        raise IntentUnreadable("the intent names another tombstone")
                except IntentUnreadable as exc:
                    logger.warning("sweep: tombstone %s conserved: its intent %s is unreadable: %s", tomb, intent_file, exc)
                    report.conserved.append(tomb)
                    report.unreadable.append(intent_file)
                    continue
            result = finalize_tombstone(books_dir, tomb, intent)
            (report.finalized if result.done else report.conserved).append(tomb)
        except Exception as exc:  # noqa: BLE001 - one bad tombstone must not block the others
            logger.error("sweep: finalizing %s failed; left for the next sweep: %s", tomb, exc)
            report.failed.append(tomb)

    for triple in sorted(intents, key=lambda t: intents[t]):
        name = intents[triple]
        try:
            os.unlink(os.path.join(books_dir, name))
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 - reported, retried by the next sweep
            logger.error("sweep: removing orphan intent %s failed: %s", name, exc)
            report.failed.append(name)
            continue
        report.orphan_intents.append(name)


def sweep(books_dir: PathLike, *, budget: float) -> SweepReport:
    """Finalize, conserve or drop every tombstone / intent in ``books_dir``.

    One folder at a time under its EX lock (holder ``"delete"``, ``budget`` per
    folder); a busy folder's entries are reported in ``busy`` and left alone.
    """
    directory = os.fspath(books_dir)
    report = SweepReport()
    tombs, intents = _entries(directory)
    by_folder: Dict[str, List[str]] = {}
    for triple, name in list(tombs.items()) + list(intents.items()):
        by_folder.setdefault(triple[0], []).append(name)

    for folder in sorted(by_folder):
        try:
            with book_lock.acquire(directory, folder, mode=book_lock.EXCLUSIVE, holder="delete", budget=budget):
                _sweep_folder(directory, folder, report)
        except book_lock.BookLockBusy:
            report.busy.extend(sorted(by_folder[folder]))
    return report



def pending_tombstones(books_dir: PathLike, folder: str) -> List[str]:
    """The tombstone names in ``books_dir`` whose parsed folder is ``folder``, sorted.

    What ``process_epub`` checks after its sweep (018 WI-5b, W5-18): an import never
    publishes over a same-name tombstone the sweep could not clear (busy, conserved
    or failed) -- that tombstone's finalizer still has to run against this name.
    """
    tombs, _intents = _entries(os.fspath(books_dir))
    return sorted(name for triple, name in tombs.items() if triple[0] == folder)


class ImportRefused(Exception):
    """``process_epub`` found a same-name tombstone left after its sweep."""


# --------------------------------------------------------------------------- delete


def _read_book_uuid(book_dir: str) -> Optional[str]:
    """The uuid in ``ai_meta.json``, read strictly: anything but a UUID string is ``None``."""
    try:
        data = json.loads(Path(book_dir, _AI_META).read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return _canonical_uuid(data.get("book_uuid"))


def delete_book(
    books_dir: PathLike,
    folder: str,
    *,
    delete_conversations: bool,
    conversation_root: Optional[str],
    collections_path: PathLike,
) -> None:
    """Delete one book. Raises before the commit point (nothing changed):
    ``book_lock.BookLockBusy``, ``book_lock.BookGone``, ``DeleteRefused``, ``OSError``.

    After the commit the delete has happened: a finalize failure is logged and left
    for the next sweep, and the caches are invalidated on every exit path.
    """
    directory = os.fspath(books_dir)
    folder = safe_book_folder(folder)
    root = None if conversation_root is None else os.path.abspath(conversation_root)
    coll = os.path.abspath(os.fspath(collections_path))

    sweep(directory, budget=book_lock.SHORT_BUDGET_S)
    _step("swept")

    with book_lock.acquire(directory, folder, mode=book_lock.EXCLUSIVE, holder="delete", budget=book_lock.SHORT_BUDGET_S):
        _step("locked")
        book_dir = os.path.join(directory, folder)
        if not os.path.isdir(book_dir):
            raise book_lock.BookGone(f"book folder {folder!r} is gone")
        book_uuid = _read_book_uuid(book_dir)
        conv_dir = os.path.join(book_dir, _CONV_DIR)
        if not delete_conversations and _conversation_files(conv_dir):
            if root is None:
                raise DeleteRefused("conversation_root")
            if book_uuid is None:
                raise DeleteRefused("book_uuid")
            try:
                plan_publish(conv_dir, root=root, fallback_uuid=book_uuid)
            except ConversationUnreadable as exc:
                raise DeleteRefused("conversation_unreadable", path=os.path.basename(exc.path)) from exc

        intent = DeleteIntent(
            folder=folder,
            pid=os.getpid(),
            token=secrets.token_hex(4),
            delete_conversations=delete_conversations,
            book_uuid=book_uuid,
            conversation_root=root,
            collections_path=coll,
        )
        write_intent(directory, intent)
        _step("intent_written")

        committed = False
        try:
            tomb = commit_tombstone(directory, intent)
            committed = True
            _step("committed")
            try:
                finalize_tombstone(directory, tomb, intent)
            except Exception as exc:  # noqa: BLE001 - past the commit point; the sweep finishes it
                logger.error("delete of %s committed but not finalized; left for the sweep: %s", folder, exc)
        finally:
            if committed:
                _invalidate(directory, folder, book_uuid, folder_scoped=True)
