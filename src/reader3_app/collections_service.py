from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

logger = logging.getLogger("reader3.collections")

COLLECTIONS_SCHEMA_VERSION = 1
COLLECTIONS_FILENAME = "library_collections.json"
COLLECTIONS_LOCK_FILENAME = "library_collections.json.lock"

# One threading.Lock per collections file, keyed by the absolute lock-file path.
_LOCK_REGISTRY_GUARD = threading.Lock()
_COLLECTIONS_THREAD_LOCKS: dict[str, threading.Lock] = {}

_NAME_RE = re.compile(r"^[A-Za-z0-9 _\\-\\.&()]+$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    created_at: str
    book_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "book_ids": list(self.book_ids),
        }

    @staticmethod
    def from_dict(d: dict) -> "Collection":
        return Collection(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or ""),
            created_at=str(d.get("created_at") or ""),
            book_ids=[str(x) for x in (d.get("book_ids") or [])],
        )


class CollectionsFileError(RuntimeError):
    pass


def collections_path(project_root_dir: str) -> Path:
    return Path(project_root_dir) / "config" / COLLECTIONS_FILENAME


def validate_collection_name(name: str, *, existing_names: Iterable[str] = ()) -> str:
    trimmed = str(name or "").strip()
    if not (1 <= len(trimmed) <= 60):
        raise ValueError("Collection name must be 1–60 characters.")
    if not _NAME_RE.match(trimmed):
        raise ValueError("Collection name contains invalid characters.")
    existing_ci = {str(n).strip().lower() for n in existing_names}
    if trimmed.lower() in existing_ci:
        raise ValueError("A collection with this name already exists.")
    return trimmed


def _ensure_config_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def _collections_write_lock(path: Path) -> Iterator[None]:
    """Serialise one collections file's read-modify-write against every writer.

    Every mutator below is load -> modify -> save of the whole file. Two writers
    interleaving inside that window each save their own stale copy and the disk
    keeps the last one: an added book vanishes, a deleted collection comes back,
    a name-uniqueness check passes twice. ``os.replace`` cannot help — the race
    is between the read and the write — so the lock spans all three steps,
    name validation included.

    Same two layers as ``notes_service._book_write_lock``: a ``threading.Lock``
    for threads in one process, ``fcntl.flock`` on a sibling lock file for other
    processes (a second uvicorn worker, a script). POSIX only. The lock file is
    separate from the data file because ``os.replace`` swaps the data inode out.

    Not reentrant: ``save_collections`` must not take it (flock is per open file
    description, so a nested acquire in the same thread would deadlock).
    """
    _ensure_config_dir(path)
    lock_path = path.parent / COLLECTIONS_LOCK_FILENAME

    key = os.path.abspath(lock_path)
    with _LOCK_REGISTRY_GUARD:
        thread_lock = _COLLECTIONS_THREAD_LOCKS.setdefault(key, threading.Lock())

    with thread_lock:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_json(path: Path, data: dict) -> None:
    _ensure_config_dir(path)
    # Private scratch name from mkstemp, not a fixed "<name>.tmp": a shared tmp
    # name lets two writers stream into one inode and the loser's os.replace
    # fail with ENOENT (the notes_service bug, same fix).
    fd, tmp_path = tempfile.mkstemp(prefix=".library_collections.", suffix=".tmp", dir=path.parent)
    try:
        try:
            # fdopen takes ownership of fd; only an fdopen failure leaves it ours.
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            # Bytes on disk before the name points at them; otherwise a crash
            # can publish an empty file in place of the user's collections.
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # The old file is untouched; do not leave the half-written scratch behind.
        # A failed cleanup is logged, never raised: it must not mask the real error.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("collections: could not remove scratch file %s: %s", tmp_path, e)
        raise
    # Make the rename itself durable. The new file is already published, so a
    # failure here is logged rather than raised: raising would report failure
    # for a change the caller can already see, and a retried create would then
    # hit "already exists". The rename may not survive a power loss; the warning
    # is the only signal. Only OSError: an interrupt still propagates.
    try:
        _fsync_dir(path.parent)
    except OSError as e:
        logger.warning("collections: directory fsync failed after publishing %s: %s", path, e)


def load_collections(path: Path) -> list[Collection]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CollectionsFileError("Collections file contains invalid JSON.") from e
    except Exception as e:
        raise CollectionsFileError("Failed to read collections file.") from e

    if not isinstance(raw, dict) or raw.get("schema_version") != COLLECTIONS_SCHEMA_VERSION:
        raise CollectionsFileError("Collections file schema is invalid or unsupported.")

    items = raw.get("collections") or []
    if not isinstance(items, list):
        raise CollectionsFileError("Collections file is malformed.")
    out: list[Collection] = []
    for item in items:
        if isinstance(item, dict):
            out.append(Collection.from_dict(item))
    return out


def save_collections(path: Path, collections: list[Collection]) -> None:
    payload = {
        "schema_version": COLLECTIONS_SCHEMA_VERSION,
        "collections": [c.to_dict() for c in collections],
    }
    _atomic_write_json(path, payload)


def _normalize_book_id(book_id: str) -> str:
    safe = os.path.basename(str(book_id or ""))
    if safe != book_id:
        raise ValueError("Invalid book_id")
    return safe


def create_collection(path: Path, *, name: str) -> Collection:
    with _collections_write_lock(path):
        collections = load_collections(path)
        validated = validate_collection_name(name, existing_names=[c.name for c in collections])
        new = Collection(id=str(uuid.uuid4()), name=validated, created_at=_utc_now_iso(), book_ids=[])
        collections.append(new)
        save_collections(path, collections)
        return new


def get_collection(path: Path, collection_id: str) -> Optional[Collection]:
    collections = load_collections(path)
    for c in collections:
        if c.id == collection_id:
            return c
    return None


def rename_collection(path: Path, collection_id: str, *, name: str) -> Collection:
    with _collections_write_lock(path):
        collections = load_collections(path)
        existing_names = [c.name for c in collections if c.id != collection_id]
        validated = validate_collection_name(name, existing_names=existing_names)
        updated: Optional[Collection] = None
        for i, c in enumerate(collections):
            if c.id == collection_id:
                updated = Collection(id=c.id, name=validated, created_at=c.created_at, book_ids=list(c.book_ids))
                collections[i] = updated
                break
        if not updated:
            raise KeyError("Collection not found")
        save_collections(path, collections)
        return updated


def delete_collection(path: Path, collection_id: str) -> None:
    with _collections_write_lock(path):
        collections = load_collections(path)
        next_collections = [c for c in collections if c.id != collection_id]
        if len(next_collections) == len(collections):
            raise KeyError("Collection not found")
        save_collections(path, next_collections)


def update_collection_books(
    path: Path,
    collection_id: str,
    *,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
) -> Collection:
    with _collections_write_lock(path):
        collections = load_collections(path)
        updated: Optional[Collection] = None
        for i, c in enumerate(collections):
            if c.id != collection_id:
                continue
            book_ids = list(c.book_ids)
            book_id_set = {x for x in book_ids}
            for bid in add:
                safe = _normalize_book_id(str(bid))
                if safe not in book_id_set:
                    book_ids.append(safe)
                    book_id_set.add(safe)
            for bid in remove:
                safe = _normalize_book_id(str(bid))
                if safe in book_id_set:
                    book_id_set.remove(safe)
            book_ids = [x for x in book_ids if x in book_id_set]
            updated = Collection(id=c.id, name=c.name, created_at=c.created_at, book_ids=book_ids)
            collections[i] = updated
            break
        if not updated:
            raise KeyError("Collection not found")
        save_collections(path, collections)
        return updated

