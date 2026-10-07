"""`GET /api/library/export` —— 整个书库的一次性 JSON 导出（018 WI-6，债 #53）。

一个 ``JSONResponse``，``Content-Disposition: attachment; filename="reader3-library.json"``，
不流式、不设上限。信封只有 ``{"books": [...]}``，顺序即 ``search_service.list_book_ids``。

- 读得出的书：``GET /api/library`` 的同一条目（``library_books.library_entry``，两边不分叉），
  加 ``annotations``（``Annotation.to_dict()`` 列表，``notes.json`` 读不懂时为 ``null``）、
  ``component_errors``（总在，可为空），以及仅在 ``?include=conversations`` 时出现的
  ``conversations``（磁盘上原样的线程对象，含 messages）。
- 读不出的书：恰好 ``{book_id, error: "unreadable"}``，它的笔记、对话、uuid 一样都不读。
- 导出期间消失的书：跳过（D19）。只有枚举本身失败才是 500。

**只读，不取锁，不铸 uuid**（W6-1）：uuid 走 ``book_lock.read_book_uuid``，不是
``_server._book_uuid_or_none``（那个会取书锁、在 ``ai_meta.json`` 缺失时铸一个）。所以
``GET /api/library`` 会铸 uuid 的书，这里报 ``book_uuid: null`` 并记一条 WARNING；不是合法
UUID 的值同样报 ``null``，也不会被拿去拼 project-root 路径（W6-4）。

对话来源（W6-2）：每本书的 ``ai_conversations/`` 总是读；project-root 的
``_project_conversations_root(settings)/{uuid}/`` 在根能解析、uuid 合法时也读——与
``conversation_disk_storage`` 无关。同一 ``conversation_id`` 两边都有时，``last_updated``
严格更大的胜出（非字符串按 ``""`` 比），相等时 project-root 那份胜出（W6-11）。

``component_errors`` 的三种形状：``{"component": "annotations"}``；
``{"component": "conversations", "conversation_id": <文件主名>}``（单个文件读不懂，两边都
坏只报一次）；``{"component": "conversations"}``（整个来源读不动：根无法解析、目录无权限、
``ai_meta.json`` 存在却读不出合法 uuid）。来源目录不存在不是错误。

所有接缝都在调用时经模块属性解析（``book_store``、``notes_service``、``book_lock``、
``conversations``、``_server``），因为测试 monkeypatch 的是这些属性。
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ... import book_lock, notes_service
from ...ai import conversations
from ...search_service import list_book_ids

logger = logging.getLogger("reader3.web.library_export")

router: APIRouter = APIRouter()

EXPORT_FILENAME = "reader3-library.json"
_INCLUDE_DETAIL = 'include must be "conversations"'
_AI_META = "ai_meta.json"

_CONVERSATIONS_SOURCE_ERROR: dict[str, str] = {"component": "conversations"}


class _BookVanished(Exception):
    """The book directory went away mid-export: the entry is skipped (D19)."""


def _parse_include(request: Request) -> bool:
    """W6-7：缺省不含对话；恰好一个值、不分大小写的 ``conversations`` 才含；其余（空串、重复、列表）400。"""
    values = request.query_params.getlist("include")
    if not values:
        return False
    if len(values) == 1 and values[0].lower() == "conversations":
        return True
    raise HTTPException(status_code=400, detail=_INCLUDE_DETAIL)


def _export_uuid(books_dir: str, book_id: str) -> Optional[str]:
    """只读的 uuid：不取锁、不铸；缺失、读不懂、不是合法 UUID 都是 ``None``，并记 WARNING。"""
    raw = book_lock.read_book_uuid(books_dir, book_id)
    if raw is not None:
        try:
            return str(_uuid.UUID(raw))
        except ValueError:
            pass
    logger.warning(
        "library export: no valid book_uuid for %s (ai_meta.json absent or unreadable); exported as null",
        book_id,
    )
    return None


def _annotations(books_dir: str, book_id: str) -> Optional[list[dict[str, Any]]]:
    """笔记列表；``notes.json`` 读不懂时 ``None``。读的途中文件没了，就是没有笔记。"""
    try:
        return [a.to_dict() for a in notes_service.load_annotations(books_dir, book_id)]
    except notes_service.NotesFileError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            return []
        logger.warning("library export: notes.json for %s is unreadable: %s", book_id, exc)
        return None


def _read_source(book_dir: str, directory: str) -> tuple[list[dict[str, Any]], list[str]]:
    """一个对话来源。``FileNotFoundError``：书没了 → ``_BookVanished``；书还在 → 空来源。

    其余 ``OSError`` 原样抛给调用方，记成整源错误。
    """
    try:
        return conversations.read_conversation_threads(directory)
    except FileNotFoundError:
        if not os.path.isdir(book_dir):
            raise _BookVanished() from None
        return [], []


def _lu_key(thread: dict[str, Any]) -> str:
    value = thread.get("last_updated")
    return value if isinstance(value, str) else ""


def _cid(thread: dict[str, Any]) -> str:
    return str(_uuid.UUID(str(thread.get("conversation_id"))))


def _conversations(
    books_dir: str,
    book_id: str,
    book_uuid: Optional[str],
    project_root: Optional[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """两个来源合并去重后的原样线程，加上对话那一半的 component_errors。"""
    book_dir = os.path.join(books_dir, book_id)
    source_failed = False
    unreadable: list[str] = []
    best: dict[str, dict[str, Any]] = {}

    try:
        threads, bad = _read_source(book_dir, os.path.join(book_dir, conversations.CONVERSATIONS_DIRNAME))
    except OSError as exc:
        logger.warning("library export: per-book conversations of %s are unreadable: %s", book_id, exc)
        source_failed = True
        threads, bad = [], []
    for t in threads:
        best[_cid(t)] = t
    unreadable.extend(bad)

    if book_uuid is None:
        # 有 ai_meta.json 却读不出合法 uuid：project-root 那一半找不到了，必须说出来（R-2）。
        if os.path.lexists(os.path.join(book_dir, _AI_META)):
            source_failed = True
    elif project_root is None:
        logger.warning("library export: project conversations root is unresolvable; skipped for %s", book_id)
        source_failed = True
    else:
        try:
            threads, bad = _read_source(book_dir, os.path.join(project_root, book_uuid))
        except OSError as exc:
            logger.warning("library export: project-root conversations of %s are unreadable: %s", book_id, exc)
            source_failed = True
            threads, bad = [], []
        for t in threads:
            cid = _cid(t)
            prev = best.get(cid)
            # W6-11：严格更新的胜出；相等时 project-root 那份胜出。
            if prev is None or _lu_key(t) >= _lu_key(prev):
                best[cid] = t
        unreadable.extend(bad)

    errors: list[dict[str, str]] = [dict(_CONVERSATIONS_SOURCE_ERROR)] if source_failed else []
    for stem in sorted(set(unreadable)):
        errors.append({"component": "conversations", "conversation_id": stem})
    return list(best.values()), errors


def _export_entry(
    books_dir: str, book_id: str, include_conversations: bool, project_root: Optional[str]
) -> Optional[dict[str, Any]]:
    entry = _library_books.library_entry(book_id, books_dir, lambda b: _export_uuid(books_dir, b))
    if entry is None or "error" in entry:
        return entry
    errors: list[dict[str, str]] = []
    annotations = _annotations(books_dir, book_id)
    if annotations is None:
        errors.append({"component": "annotations"})
    entry["annotations"] = annotations
    if include_conversations:
        try:
            threads, conv_errors = _conversations(books_dir, book_id, entry["book_uuid"], project_root)
        except _BookVanished:
            return None
        entry["conversations"] = threads
        errors.extend(conv_errors)
    entry["component_errors"] = errors
    # D19：读完所有部件后复核——书在途中被删就跳过，而不是导出一条「空」的书。
    if not os.path.isdir(os.path.join(books_dir, book_id)):
        return None
    return entry


def _export_library(books_dir: str, include_conversations: bool) -> list[dict[str, Any]]:
    project_root: Optional[str] = None
    if include_conversations:
        project_root = _server._project_conversations_root(_server.load_ai_settings())
    entries: list[dict[str, Any]] = []
    for book_id in list_book_ids(books_dir):
        entry = _export_entry(books_dir, book_id, include_conversations, project_root)
        if entry is not None:
            entries.append(entry)
    return entries


@router.get("/api/library/export")
async def api_library_export(request: Request) -> JSONResponse:
    """导出书库（只读）：200 附件 JSON；``include`` 不合语法 400；只有枚举失败才 500。"""
    include_conversations = _parse_include(request)
    books = await run_in_threadpool(_export_library, _server.BOOKS_DIR, include_conversations)
    return JSONResponse(
        {"books": books},
        headers={"Content-Disposition": f'attachment; filename="{EXPORT_FILENAME}"'},
    )


# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
# library_books 也放在这里：它的末尾会导入 server，而 server 末尾要取本模块的 `router`。
from . import library_books as _library_books  # noqa: E402
from .. import server as _server  # noqa: E402
