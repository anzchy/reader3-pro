"""`GET /api/library` —— 书库的 JSON 视图（018 WI-4，债 #56）。

``{"books": [...]}``，顺序即 ``search_service.list_book_ids(BOOKS_DIR)``。每本书一条：

- 读得出：``{book_id, title, authors, cover_url, book_uuid}``。标题与作者走
  ``book_store.load_book_metadata``（012 的粒度接缝，Q-A），不碰整本 ``Book``；
  封面走 ``book_store.pick_cover_image``，与 ``GET /`` 同一个挑选器（Q-C）；
  ``book_uuid`` 走 ``_server._book_uuid_or_none``——``ai_meta.json`` 读不懂时降级成
  ``None``，原文件一个字节都不动（ADR-0003）。
- 读不出（坏 pickle、book.pkl 是目录、别的 OSError …）：``{book_id, error: "unreadable"}``，
  且不为它解析 uuid——不给一本打不开的书铸 ``ai_meta.json``。
- 枚举之后消失了（``FileNotFoundError``，``BookGone`` 是它的子类）：跳过（Q-G）。

整个逐本循环一次进线程池：载入元数据与解析 uuid（可能取书锁）都不在事件循环上等。
所有接缝都在调用时经模块属性解析（``_server.BOOKS_DIR``、``_server._book_uuid_or_none``、
``book_store.load_book_metadata``），因为测试 monkeypatch 的是这些属性。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from ... import book_store
from ...search_service import list_book_ids

router: APIRouter = APIRouter()


def _list_library(books_dir: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for book_id in list_book_ids(books_dir):
        try:
            meta = book_store.load_book_metadata(book_id, books_dir)
        except FileNotFoundError:
            # Q-G：枚举之后被删（含 BookGone）——它已经不在书库里了，不是错误条目。
            continue
        except Exception:  # noqa: BLE001 - 第 2 档：一本读不出的书转译成 error 条目，其余照常列出
            entries.append({"book_id": book_id, "error": "unreadable"})
            continue
        cover_image = book_store.pick_cover_image(book_id, books_dir)
        entries.append(
            {
                "book_id": book_id,
                "title": meta.title,
                "authors": list(meta.authors),
                "cover_url": f"/read/{book_id}/images/{cover_image}" if cover_image else None,
                "book_uuid": _server._book_uuid_or_none(book_id),
            }
        )
    return entries


@router.get("/api/library")
async def api_library_books() -> dict[str, list[dict[str, Any]]]:
    books = await run_in_threadpool(_list_library, _server.BOOKS_DIR)
    return {"books": books}

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from .. import server as _server  # noqa: E402
