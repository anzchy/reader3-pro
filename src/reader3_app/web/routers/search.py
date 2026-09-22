"""`/api/search/*`、`/api/highlight/*`、`/api/index/*` —— 检索与向量索引。

拆自 `web/server.py`（011 WI-4）。**路由正文一字未改**，改的只有三类引用：
`@app.x` → `@router.x`，接缝与 `server` 私有 helper 改走 `_server.` 属性访问。

本组碰到的四个接缝：`BOOKS_DIR`、`BookVectorIndex`、`search_library`、`search_book`
——都在 `test_server_patch_seam_ownership.py` 的 OWNERSHIP 名单里，所以一律
`_server.X`，不许 `from ..server import X`（理由与实测见 `routers/__init__.py`）。
`highlight_ranges_for_chapter`、`SearchMode/Query/Scope` 不是接缝，直接从
`search_service` 导入即可。

留在 `server` 的：`_validate_book_id`、`logger`。
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .. import server as _server
from ...search_service import (
    SearchMode,
    SearchQuery,
    SearchScope,
    highlight_ranges_for_chapter,
)

router: APIRouter = APIRouter()


@router.get("/api/search/library")
async def api_search_library(
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results_per_book: int = 3,
    max_total_results: int = 100,
    sort_by: str = "relevance",
):
    started = time.perf_counter()
    try:
        query_obj = SearchQuery(
            term=q,
            mode=SearchMode(mode),
            scope=SearchScope.ALL_BOOKS,
            case_sensitive=case_sensitive,
            max_results=1000,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    max_results_per_book = max(1, min(int(max_results_per_book), 10))
    max_total_results = max(1, min(int(max_total_results), 1000))
    if sort_by not in ("relevance", "book_title", "book_author"):
        raise HTTPException(status_code=400, detail="Invalid sort_by")

    try:
        result_set, book_order = await run_in_threadpool(
            _server.search_library,
            query_obj,
            books_dir=_server.BOOKS_DIR,
            max_results_per_book=max_results_per_book,
            max_total_results=max_total_results,
            sort_by=sort_by,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result_set.execution_time_ms > 2000:
        _server.logger.warning(
            "slow library search (%.1fms) mode=%s books=%s",
            result_set.execution_time_ms,
            query_obj.mode.value,
            result_set.searched_books,
        )

    book_metadata = {}
    for book_id in book_order:
        results = result_set.grouped_by_book.get(book_id, [])
        if not results:
            continue
        book_metadata[book_id] = {
            "book_id": book_id,
            "title": results[0].book_title,
            "author": results[0].book_author,
        }

    return {
        "query": {
            "term": query_obj.term,
            "mode": query_obj.mode.value,
            "scope": query_obj.scope.value,
        },
        "results": [r.__dict__ for r in result_set.results],
        "grouped_by_book": {bid: [r.__dict__ for r in result_set.grouped_by_book.get(bid, [])] for bid in book_order},
        "book_order": book_order,
        "book_metadata": book_metadata,
        "index_status_by_book": result_set.index_status_by_book,
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "unindexed_books": result_set.unindexed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms or ((time.perf_counter() - started) * 1000),
        "status_message": result_set.status_message(),
    }


@router.get("/api/search/{book_id}")
async def api_search_book(
    book_id: str,
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results: int = 1000,
):
    safe_book_id = _server._validate_book_id(book_id)
    started = time.perf_counter()
    try:
        query_obj = SearchQuery(
            term=q,
            mode=SearchMode(mode),
            scope=SearchScope.CURRENT_BOOK,
            case_sensitive=case_sensitive,
            max_results=max_results,
            book_id=safe_book_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result_set = await run_in_threadpool(_server.search_book, safe_book_id, query_obj, books_dir=_server.BOOKS_DIR)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result_set.execution_time_ms > 500:
        _server.logger.info(
            "slow in-book search (%.1fms) book=%s mode=%s",
            result_set.execution_time_ms,
            safe_book_id,
            query_obj.mode.value,
        )

    return {
        "query": {
            "term": query_obj.term,
            "mode": query_obj.mode.value,
            "scope": query_obj.scope.value,
            "case_sensitive": query_obj.case_sensitive,
            "max_results": query_obj.max_results,
            "book_id": query_obj.book_id,
        },
        "results": [r.__dict__ for r in result_set.results],
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "unindexed_books": result_set.unindexed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms or ((time.perf_counter() - started) * 1000),
        "status_message": result_set.status_message(),
    }


class HighlightRequest(BaseModel):
    search_term: str
    occurrence_index: Optional[int] = None
    case_sensitive: bool = False


@router.post("/api/highlight/{book_id}/{chapter_order}")
async def api_highlight(book_id: str, chapter_order: int, body: HighlightRequest):
    safe_book_id = _server._validate_book_id(book_id)
    try:
        ranges, total_matches, selected = highlight_ranges_for_chapter(
            safe_book_id,
            int(chapter_order),
            search_term=body.search_term,
            occurrence_index=body.occurrence_index,
            case_sensitive=body.case_sensitive,
            books_dir=_server.BOOKS_DIR,
        )
    except IndexError:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return {
        "ranges": ranges,
        "total_matches": total_matches,
        "selected_occurrence_index": selected,
    }


class IndexRequest(BaseModel):
    force_reindex: bool = False


@router.post("/api/index/{book_id}")
async def api_index_book(book_id: str, body: IndexRequest):
    safe_book_id = _server._validate_book_id(book_id)
    try:
        idx = _server.BookVectorIndex(safe_book_id, books_dir=_server.BOOKS_DIR)
        status = await run_in_threadpool(idx.index_book, force_reindex=body.force_reindex)
        return status
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 500 且 detail 带上原因
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/{book_id}/status")
async def api_index_status(book_id: str):
    safe_book_id = _server._validate_book_id(book_id)
    try:
        idx = _server.BookVectorIndex(safe_book_id, books_dir=_server.BOOKS_DIR)
        return await run_in_threadpool(idx.status)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 500 且 detail 带上原因
        raise HTTPException(status_code=500, detail=str(e))
