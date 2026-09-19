"""`/`、`/api/collections/*`、`/api/library/stats` —— 书架页与藏书管理。

拆自 `web/server.py`（011 WI-4）。**路由正文一字未改**，改的只有三类引用：
`@app.x` → `@router.x`，接缝与 `server` 私有 helper／模块级状态改走 `_server.` 属性访问。

三个接缝：`BOOKS_DIR`、`load_book_cached`、`BookVectorIndex`。
`_stats_cache` 走 `_server._stats_cache` 不是随手写的：测试里是
`server._stats_cache.clear()`（tests/contract/conftest.py:212 等三处），
那是**原地改同一个 dict**，从来不重新绑定这个名字，所以属性访问读到的就是同一个对象。

留在 `server` 的：`_validate_book_id`、`_validate_book_id_path_safe`、
`_validate_collection_id`、`_collections_file_path`、`_book_uuid_or_none`、
`_library_ui_mode`、`_library_template_name`、`_ui_default_provider`、`templates`。
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import server as _server
from ... import collections_service
from ...search_service import list_book_ids

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(_server.BOOKS_DIR):
        for item in os.listdir(_server.BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(os.path.join(_server.BOOKS_DIR, item)):
                # Try to load it to get the title
                book = _server.load_book_cached(item)
                if book:
                    cover_image = None
                    try:
                        images_dir = os.path.join(_server.BOOKS_DIR, item, "images")
                        if os.path.isdir(images_dir):
                            candidates = [
                                f
                                for f in os.listdir(images_dir)
                                if os.path.isfile(os.path.join(images_dir, f)) and not f.startswith(".")
                            ]
                            preferred = [f for f in candidates if "cover" in f.lower() or "title" in f.lower()]
                            pick_from = preferred or candidates
                            if pick_from:
                                cover_image = sorted(pick_from, key=lambda x: (len(x), x.lower()))[0]
                    except Exception:  # noqa: BLE001 - 第 3 档：封面挑选失败只影响一张缩略图，书本身照常打开
                        cover_image = None

                    cover_url = f"/read/{item}/images/{cover_image}" if cover_image else None
                    book_uuid = _server._book_uuid_or_none(item)
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine),
                        "section_count": len(book.spine),
                        "cover_url": cover_url,
                        "format": "epub",
                        "book_uuid": book_uuid,
                    })

    existing_book_ids = {b.get("id") for b in books if b.get("id")}
    collections = []
    collections_error: Optional[str] = None
    try:
        for c in collections_service.load_collections(_server._collections_file_path()):
            present = [bid for bid in (c.book_ids or []) if bid in existing_book_ids]
            missing = [bid for bid in (c.book_ids or []) if bid not in existing_book_ids]
            collections.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "created_at": c.created_at,
                    "book_ids": list(c.book_ids),
                    "book_count": len(present),
                    "missing_book_ids": missing,
                    "missing_count": len(missing),
                }
            )
        collections.sort(key=lambda x: str(x.get("name") or "").lower())
    except collections_service.CollectionsFileError as e:
        collections_error = str(e)

    return _server.templates.TemplateResponse(
        request,
        _server._library_template_name(),
        {
            "books": books,
            "counts": {
                "all": len(books),
                "epub": sum(1 for b in books if b.get("format") == "epub"),
                "pdf": sum(1 for b in books if b.get("format") == "pdf"),
            },
            "collections": collections,
            "collections_error": collections_error,
            "library_ui_mode": _server._library_ui_mode(),
            "ai_default_provider": _server._ui_default_provider(),
        },
    )


class CollectionCreateRequest(BaseModel):
    name: str


class CollectionRenameRequest(BaseModel):
    name: str


class CollectionBooksUpdateRequest(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


@router.get("/api/collections")
async def api_collections_list():
    try:
        cols = collections_service.load_collections(_server._collections_file_path())
        return {"collections": [c.to_dict() for c in cols]}
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/collections", status_code=201)
async def api_collections_create(body: CollectionCreateRequest):
    try:
        created = collections_service.create_collection(_server._collections_file_path(), name=body.name)
        return created.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/collections/{collection_id}")
async def api_collections_get(collection_id: str):
    cid = _server._validate_collection_id(collection_id)
    try:
        col = collections_service.get_collection(_server._collections_file_path(), cid)
        if not col:
            raise HTTPException(status_code=404, detail="Collection not found")
        return col.to_dict()
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/collections/{collection_id}")
async def api_collections_rename(collection_id: str, body: CollectionRenameRequest):
    cid = _server._validate_collection_id(collection_id)
    try:
        updated = collections_service.rename_collection(_server._collections_file_path(), cid, name=body.name)
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/collections/{collection_id}/books")
async def api_collections_update_books(collection_id: str, body: CollectionBooksUpdateRequest):
    cid = _server._validate_collection_id(collection_id)
    try:
        col = collections_service.get_collection(_server._collections_file_path(), cid)
        if not col:
            raise HTTPException(status_code=404, detail="Collection not found")

        add_ids = [_server._validate_book_id(x) for x in (body.add or [])]
        remove_ids = [_server._validate_book_id_path_safe(x) for x in (body.remove or [])]
        remove_allowed = set(col.book_ids or [])
        remove_ids = [x for x in remove_ids if x in remove_allowed]
        updated = collections_service.update_collection_books(
            _server._collections_file_path(),
            cid,
            add=add_ids,
            remove=remove_ids,
        )
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/collections/{collection_id}", status_code=204)
async def api_collections_delete(collection_id: str):
    cid = _server._validate_collection_id(collection_id)
    try:
        collections_service.delete_collection(_server._collections_file_path(), cid)
        return Response(status_code=204)
    except KeyError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except collections_service.CollectionsFileError as e:
        raise HTTPException(status_code=500, detail=str(e))


@dataclass(frozen=True)
class LibraryStats:
    scope: str
    books_total: int
    books_indexed: int
    indexed_percent: int
    sections_total: int
    chunks_total: int
    computed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "books_total": self.books_total,
            "books_indexed": self.books_indexed,
            "indexed_percent": self.indexed_percent,
            "sections_total": self.sections_total,
            "chunks_total": self.chunks_total,
            "computed_at": self.computed_at,
        }


def _validate_stats_scope(scope: str) -> tuple[str, Optional[str], Optional[str]]:
    scope = (scope or "all").strip()
    if scope == "all":
        return ("all", None, None)
    if scope.startswith("format:"):
        fmt = scope.split(":", 1)[1].strip().lower()
        if fmt in {"epub", "pdf"}:
            return (f"format:{fmt}", fmt, None)
        raise HTTPException(status_code=400, detail="Invalid scope")
    if scope.startswith("collection:"):
        raw = scope.split(":", 1)[1].strip()
        try:
            cid = str(uuid.UUID(raw))
        except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 Invalid scope；类型待收窄为 ValueError
            raise HTTPException(status_code=400, detail="Invalid scope")
        return (f"collection:{cid}", None, cid)
    raise HTTPException(status_code=400, detail="Invalid scope")


def _compute_stats_for_scope(scope: str) -> LibraryStats:
    validated_scope, fmt, collection_id = _validate_stats_scope(scope)

    all_book_ids = list(list_book_ids(_server.BOOKS_DIR))
    book_ids: list[str] = []
    if validated_scope == "all":
        book_ids = all_book_ids
    elif fmt:
        # PDF is a placeholder in 004; treat as no-op unless PDFs are supported later.
        if fmt == "pdf":
            book_ids = []
        else:
            book_ids = all_book_ids
    elif collection_id:
        col = collections_service.get_collection(_server._collections_file_path(), collection_id)
        if not col:
            raise HTTPException(status_code=404, detail="Collection not found")
        allowed = set(col.book_ids or [])
        book_ids = [bid for bid in all_book_ids if bid in allowed]

    books_total = len(book_ids)
    books_indexed = 0
    sections_total = 0
    chunks_total = 0

    for bid in book_ids:
        book = _server.load_book_cached(bid)
        if book:
            sections_total += len(book.spine)

        try:
            idx = _server.BookVectorIndex(bid, books_dir=_server.BOOKS_DIR)
            if idx.is_indexed():
                books_indexed += 1
                status = idx.status()
                cc = status.get("chunk_count")
                if isinstance(cc, int):
                    chunks_total += cc
        except Exception:  # noqa: BLE001 - FIXME(011): 无正当理由——单本索引统计失败被跳过，首页那个百分比就静默偏小，没有任何痕迹说明它不准
            continue

    indexed_percent = 0
    if books_total > 0:
        indexed_percent = int(round((books_indexed / books_total) * 100))

    computed_at = datetime.now(timezone.utc).isoformat()
    return LibraryStats(
        scope=validated_scope,
        books_total=books_total,
        books_indexed=books_indexed,
        indexed_percent=indexed_percent,
        sections_total=sections_total,
        chunks_total=chunks_total,
        computed_at=computed_at,
    )


@router.get("/api/library/stats")
async def api_library_stats(scope: str = "all", fresh: bool = False):
    validated_scope, _, _ = _validate_stats_scope(scope)
    cache_key = validated_scope
    now = time.monotonic()
    if not fresh:
        cached = _server._stats_cache.get(cache_key)
        if cached:
            ts, payload = cached
            if now - ts <= 5.0:
                return payload

    try:
        stats = _compute_stats_for_scope(validated_scope).to_dict()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 500 且 detail 带上原因
        raise HTTPException(status_code=500, detail=str(e))

    _server._stats_cache[cache_key] = (now, stats)
    return stats

