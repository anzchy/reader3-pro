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

``DELETE /api/library/{book_id}``（018 WI-5c，债 #58）也在本模块：路由只做查询解析、
id 校验与状态码映射，协议本身（意图 → 改名提交 → 终结器 → 清扫）在 ``library_delete``。

整个逐本循环一次进线程池：载入元数据与解析 uuid（可能取书锁）都不在事件循环上等。
所有接缝都在调用时经模块属性解析（``_server.BOOKS_DIR``、``_server._book_uuid_or_none``、
``book_store.load_book_metadata``），因为测试 monkeypatch 的是这些属性。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from ... import book_store, library_delete
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


# --------------------------------------------------------------------------- DELETE (018 WI-5c)

#: ``DeleteRefused.reason`` → 409 detail. A refusal is not a busy lock: no ``Retry-After``.
_REFUSED_DETAIL = {
    "conversation_root": "invalid conversation root: the book's conversations have nowhere to go",
    "book_uuid": "invalid book_uuid in ai_meta.json: the book's conversations cannot be kept",
}


def _parse_delete_conversations(request: Request) -> bool:
    """W5-8：手工解析——缺省为 ``false``；``true`` / ``false`` 不分大小写；其余（含空串）400。"""
    values = request.query_params.getlist("delete_conversations")
    if not values:
        return False
    if len(values) == 1 and values[0].lower() in ("true", "false"):
        return values[0].lower() == "true"
    raise HTTPException(status_code=400, detail="delete_conversations must be true or false")


@router.delete("/api/library/{book_id}", status_code=204)
async def api_library_delete_book(book_id: str, request: Request) -> Response:
    """删一本书（``library_delete.delete_book``）：204 / 400 / 404 / 409。

    - 400：``book_id`` 不是 ``*_data`` 基名（墓碑名也在此列），或 ``delete_conversations`` 不是布尔字面量。
    - 404：书不在书库里，或锁内复核时已消失（``BookGone`` → 全局处理器）。
    - 409 ＋ ``Retry-After``：书锁被占（``BookLockBusy`` → 全局处理器，ADR-0015）。
    - 409 无 ``Retry-After``：``DeleteRefused``（对话根无效 / uuid 畸形 / 对话文件读不懂），书原样不动。
    - 提交点之后的失败只记日志、留给清扫（Q-F），仍是 204。
    """
    delete_conversations = _parse_delete_conversations(request)
    folder = _server._validate_book_id_path_safe(book_id)
    books_dir = _server.BOOKS_DIR
    if folder not in list_book_ids(books_dir):
        raise HTTPException(status_code=404, detail="Book not found")
    conversation_root = _server._project_conversations_root(_server.load_ai_settings())
    try:
        await run_in_threadpool(
            library_delete.delete_book,
            books_dir,
            folder,
            delete_conversations=delete_conversations,
            conversation_root=conversation_root,
            collections_path=_server._collections_file_path(),
        )
    except library_delete.DeleteRefused as exc:
        if exc.reason == "conversation_unreadable":
            detail = f"unreadable conversation file: {exc.path}"
        else:
            detail = _REFUSED_DETAIL.get(exc.reason, f"delete refused: {exc.reason}")
        raise HTTPException(status_code=409, detail=detail) from exc
    return Response(status_code=204)

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from .. import server as _server  # noqa: E402
