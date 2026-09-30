from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from .. import book_lock
from ..safe_paths import safe_book_folder


AI_META_FILENAME = "ai_meta.json"

logger = logging.getLogger("reader3.ai.books")


@dataclass(frozen=True)
class BookIdentity:
    book_uuid: str
    book_folder: str


def _safe_folder_name(folder_name: str) -> str:
    """名字和 ValueError 类型保持不变，判据委托给 safe_paths。

    旧判据是 ``os.path.basename(x) == x``，``"."`` 和 ``".."`` 都满足它，于是
    ``ensure_book_uuid(books, ".")`` 往 ``books/ai_meta.json`` 写了一个新 uuid。
    """
    return safe_book_folder(folder_name)


def _ai_meta_path(books_dir: str, book_folder: str) -> str:
    return os.path.join(books_dir, book_folder, AI_META_FILENAME)


def _read_ai_meta(path: str) -> Optional[Dict[str, Any]]:
    """读 ai_meta.json：不存在返回 None，**读不懂就抛**，读得懂就原样返回。

    这两件事以前都返回 None，于是 ensure_book_uuid() 无法分辨「这本书还没有
    uuid」和「这本书的 uuid 我读不出来」，把后者也当成前者去覆盖——用户的 AI
    会话全靠 book_uuid 关联，覆盖一次就永久失联。OSError（权限、坏盘）同理，
    直接冒上去。

    返回值不再过滤非字符串。旧代码这里有一句 ``if isinstance(v, str)``，两个后果：
    非字符串的 book_uuid 读回来是「不存在」，于是走上面那条覆盖的路；而
    ensure_book_uuid() 是「读整份 → 改一个键 → 整份写回」，被滤掉的键在那次写回里
    从磁盘上消失——连首次生成 uuid 这条本该正确的路径也一样。

    只有 book_uuid 做类型硬校验：它是所有 AI 会话的挂靠点，读不出就绝不能当成
    「还没有」。别的键不校验——将来谁加一个 ``{"indexed_at": 1724...}``，不该让
    每一次读都炸。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object (got {type(data).__name__})")
    if "book_uuid" in data and not isinstance(data["book_uuid"], str):
        raise ValueError(
            f"{path} holds a book_uuid that is not a string "
            f"(got {type(data['book_uuid']).__name__}); "
            "refusing to overwrite it -- fix or delete the file"
        )
    return dict(data)


def _uuid_from_meta(meta_path: str, meta: Dict[str, Any]) -> Optional[str]:
    """Normalise the stored ``book_uuid``, or report that there is not one yet.

    ``_read_ai_meta`` has already refused anything that is not a string, so the
    only two outcomes left are "absent/blank" and "present". A present value that
    will not parse is the first tier of WI-4: it must never be treated as an
    absence, because the next step after an absence is a fresh uuid written over
    it, and every AI conversation filed under the old one becomes unreachable.
    """
    raw = (meta.get("book_uuid") or "").strip()
    if not raw:
        return None
    try:
        return str(UUID(raw))
    except ValueError as e:
        raise ValueError(
            f"{meta_path} holds a book_uuid that is not a UUID ({raw!r}); "
            "refusing to overwrite it -- fix or delete the file"
        ) from e


def _write_meta_to_scratch(meta_path: str, meta: Dict[str, Any]) -> str:
    """Serialise ``meta`` into a scratch file no other writer can be holding.

    The scratch name used to be a fixed ``ai_meta.json.tmp``, which two
    simultaneous writers open as the *same* file: one truncates the other's
    half-written JSON, and whichever renames second finds nothing there to rename.
    Naming it after the pid plus random bytes makes the scratch step private, so
    the only contention left is the one step that is supposed to be contended --
    the publish below.

    ``O_EXCL`` on the scratch file too: if that name somehow exists we are not
    looking at the file we think we are, and quietly truncating it is how the
    previous version lost data.
    """
    # No makedirs (018 WI-2, ADR-0015 contract item 5): every caller holds the book
    # lock and has just seen the book dir; if it is gone, O_EXCL below fails rather
    # than a deleted book coming back as a directory holding only ai_meta.json.
    tmp_path = f"{meta_path}.{os.getpid()}.{os.urandom(6).hex()}.tmp"
    fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return tmp_path


def _mint_first_uuid(meta_path: str) -> str:
    """Create ``ai_meta.json`` if and only if nobody else already did.

    This is the whole of WI-25. The old sequence was read -> mint -> ``os.replace``
    with no check in between, so two requests arriving at a book that has no
    ``ai_meta.json`` yet each minted a *different* uuid and each wrote it over the
    file. Last writer won the disk; the other request had already handed its uuid
    to a client, and that uuid now resolves to nothing -- permanently, since
    book_uuid is what every AI conversation is filed under. Neither request saw an
    error, which is what made it survive this long.

    ``os.link`` onto the final name is the create-if-absent: it is atomic and it
    fails with ``EEXIST`` rather than clobbering, and because the content was
    fully written to the scratch file first, the file is complete the instant it
    becomes visible -- a concurrent reader never sees a half-written object.

    Losing is not an error. The loser goes back to the file and returns *the
    winner's* uuid, so both callers leave with the same identity, which is the
    only outcome that leaves neither client orphaned. Raising here would satisfy
    "the two never disagree" by handing both of them nothing.

    The lock ``BookUuidResolver`` already owns cannot do this job: it is a
    ``threading.Lock`` taken after the mint, and the race is equally real between
    two uvicorn workers or a CLI run beside a live server. ``O_EXCL`` is the
    kernel's answer and it holds across processes.
    """
    new_uuid = str(uuid4())
    tmp_path = _write_meta_to_scratch(meta_path, {"book_uuid": new_uuid})
    won = True
    try:
        try:
            os.link(tmp_path, meta_path)
        except FileExistsError:
            won = False
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    if won:
        return new_uuid

    winner = _uuid_from_meta(meta_path, _read_ai_meta(meta_path) or {})
    if winner:
        return winner
    raise ValueError(
        f"{meta_path} appeared while a book_uuid was being minted but holds none; "
        "refusing to overwrite it -- fix or delete the file"
    )


def _add_uuid_to_existing_meta(meta_path: str, meta: Dict[str, Any]) -> str:
    """Give an ``ai_meta.json`` that exists but carries no uuid one, keeping its keys.

    Separate from ``_mint_first_uuid`` because create-if-absent cannot express
    this: the target is already there, so an exclusive create would read "somebody
    won" for a file that in fact holds no uuid at all, and either refuse forever
    or throw away the keys the file arrived with (WI-9).

    This path keeps the previous write-then-``os.replace`` and therefore keeps its
    much narrower window: it needs two writers to meet on a book whose metadata
    file was created *without* a uuid, which nothing in this codebase does -- the
    only writer of the file is the line above, and it always writes a uuid. Two
    fresh-install requests, the case that actually happens, go through
    ``_mint_first_uuid``.
    """
    new_uuid = str(uuid4())
    payload = dict(meta)
    payload["book_uuid"] = new_uuid
    tmp_path = _write_meta_to_scratch(meta_path, payload)
    try:
        os.replace(tmp_path, meta_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return new_uuid


def ensure_book_uuid(books_dir: str, book_folder: str, *, deadline: Optional[float] = None) -> str:
    """The book's uuid; minted (or added to an existing meta) if it has none yet.

    The read of an existing uuid takes no lock. Minting is a write into the book
    dir, so it runs under the book lock (SH, category ``ai_meta``) with the
    existence recheck inside it (018 WI-2): a book deleted meanwhile raises
    ``BookGone`` instead of being recreated as a folder holding only ai_meta.json.
    The meta is re-read inside the lock, so a uuid another writer minted while this
    one waited is returned rather than overwritten.
    """
    book_folder = _safe_folder_name(book_folder)
    meta_path = _ai_meta_path(books_dir, book_folder)
    meta = _read_ai_meta(meta_path)

    existing = _uuid_from_meta(meta_path, meta or {})
    if existing:
        return existing

    with book_lock.writer_scope(books_dir, book_folder, holder="ai_meta", deadline=deadline):
        meta = _read_ai_meta(meta_path)
        existing = _uuid_from_meta(meta_path, meta or {})
        if existing:
            return existing
        if meta is None:
            return _mint_first_uuid(meta_path)
        return _add_uuid_to_existing_meta(meta_path, meta)


class BookUuidResolver:
    def __init__(self, books_dir: str) -> None:
        self.books_dir = books_dir
        self._lock = threading.Lock()
        self._uuid_to_folder: Dict[str, str] = {}
        self._folder_to_uuid: Dict[str, str] = {}

    def scan(self) -> None:
        if not os.path.exists(self.books_dir):
            return
        for item in os.listdir(self.books_dir):
            if not item.endswith("_data"):
                continue
            full = os.path.join(self.books_dir, item)
            if not os.path.isdir(full):
                continue
            try:
                self._load_folder(item)
            except book_lock.BookLockBusy as e:
                # A book being imported or deleted (EX) is skipped after one budget,
                # not fatal to startup; its uuid is resolved on first use.
                logger.info("skipping %s for now: %s", item, e)
            except (OSError, ValueError) as e:
                # 第 2 档：这个扫描跑在服务启动时。一本书的 ai_meta.json 坏了不该
                # 让整个书库起不来——跳过并留痕。该书的 AI 端点随后 404（明确的
                # 缺失），而不是被悄悄换上一个新 uuid（无声的数据丢失）。
                logger.warning("skipping %s: cannot resolve its book_uuid: %s", item, e)

    def _load_folder(self, book_folder: str) -> str:
        book_folder = _safe_folder_name(book_folder)
        book_uuid = ensure_book_uuid(self.books_dir, book_folder)
        with self._lock:
            self._register(book_folder, book_uuid)
        return book_uuid

    def _register(self, book_folder: str, book_uuid: str) -> None:
        """Map folder <-> uuid, dropping the reverse entry of the folder's old uuid.

        Caller holds ``_lock``. Without the cleanup a folder whose uuid changed kept
        answering reverse lookups for the uuid it no longer holds.
        """
        old = self._folder_to_uuid.get(book_folder)
        if old is not None and old != book_uuid and self._uuid_to_folder.get(old) == book_folder:
            del self._uuid_to_folder[old]
        self._uuid_to_folder[book_uuid] = book_folder
        self._folder_to_uuid[book_folder] = book_uuid

    def _forget(self, book_folder: str, book_uuid: str, *, keep_forward: bool = False) -> None:
        """Compare-and-delete: drop X->U / U->X only if they still say exactly that.

        Another thread may already have replaced a stale entry with a fresh one;
        a blind delete would throw the fresh one away.
        """
        with self._lock:
            if not keep_forward and self._folder_to_uuid.get(book_folder) == book_uuid:
                del self._folder_to_uuid[book_folder]
            if self._uuid_to_folder.get(book_uuid) == book_folder:
                del self._uuid_to_folder[book_uuid]

    def _uuid_on_disk(self, book_folder: str) -> Optional[str]:
        """The folder's uuid as ``ai_meta.json`` holds it now -- read only, never written.

        ``None`` means the folder exists but carries no uuid yet. An unreadable file
        raises (ADR-0003: refuse, do not mint over it), and so does a missing
        folder: minting for it would makedirs the deleted book back into existence.
        """
        meta_path = _ai_meta_path(self.books_dir, book_folder)
        meta = _read_ai_meta(meta_path)
        if meta is None and not os.path.isdir(os.path.dirname(meta_path)):
            raise FileNotFoundError(f"book folder {book_folder!r} is gone")
        return _uuid_from_meta(meta_path, meta or {})

    def book_uuid_for_folder(self, book_folder: str) -> str:
        book_folder = _safe_folder_name(book_folder)
        with self._lock:
            cached = self._folder_to_uuid.get(book_folder)
        if cached:
            # WI-3: the cache is a hint, the file is the truth. A folder deleted
            # and reprocessed (or replaced by another book) used to keep answering
            # with the uuid it had before, and conversations attached to the wrong
            # identity with nothing raised.
            try:
                on_disk = self._uuid_on_disk(book_folder)
            except FileNotFoundError:
                # Keep the forward entry: dropping it would send the next call down
                # the miss path, whose makedirs recreates the deleted folder.
                self._forget(book_folder, cached, keep_forward=True)
                raise
            except (OSError, ValueError):
                self._forget(book_folder, cached)
                raise
            if on_disk == cached:
                return cached
            self._forget(book_folder, cached)
            if on_disk is not None:
                with self._lock:
                    self._register(book_folder, on_disk)
                return on_disk
        return self._load_folder(book_folder)

    def folder_for_book_uuid(self, book_uuid: str) -> str:
        normalized = str(UUID(str(book_uuid)))
        with self._lock:
            cached = self._uuid_to_folder.get(normalized)
        if cached:
            try:
                held = self._uuid_on_disk(cached)
            except (OSError, ValueError):
                held = None
            if held == normalized:
                return cached
            # Only the reverse entry: the forward one re-validates on its own hit.
            with self._lock:
                if self._uuid_to_folder.get(normalized) == cached:
                    del self._uuid_to_folder[normalized]
        self.scan()
        with self._lock:
            cached = self._uuid_to_folder.get(normalized)
        if not cached:
            raise KeyError(f"Unknown book_uuid: {normalized}")
        # A thread paused between ensure_book_uuid and _register can land a stale
        # entry after the scan above, so the post-scan hit is checked like any other.
        try:
            held = self._uuid_on_disk(cached)
        except (OSError, ValueError):
            held = None
        if held != normalized:
            # Reverse entry only, compare-and-delete: keeping the forward one means a
            # deleted folder degrades by raising, not by the miss path's makedirs.
            with self._lock:
                if self._uuid_to_folder.get(normalized) == cached:
                    del self._uuid_to_folder[normalized]
            raise KeyError(f"Unknown book_uuid: {normalized}")
        return cached

    def identity_for_folder(self, book_folder: str) -> BookIdentity:
        return BookIdentity(
            book_uuid=self.book_uuid_for_folder(book_folder),
            book_folder=_safe_folder_name(book_folder),
        )

