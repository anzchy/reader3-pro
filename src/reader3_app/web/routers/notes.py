"""`/api/notes/*` —— 标注的读写。

拆自 `web/server.py`（011 WI-4）。**拆分那一次**路由正文一字未改，改的只有三类引用：
`@app.x` → `@router.x`，以及 `server` 私有 helper 与打桩接缝改走 `_server.` 属性访问。
为什么必须是属性访问而不是 `from ..server import …`，见 `routers/__init__.py` 的 docstring。
此后路由正文**已经改过**（011 WI-5a 的乐观并发、017 WI-3/WI-4 的审计修复），所以这句话
只描述搬家那一步，不是本文件此刻与 `server.py` 旧版的关系——把它当成后者会读错代码。

对外的写入契约（`ETag` 出、可选 `If-Match` 入、书级版本、409 载荷的形状）写在
`docs/storage-and-data-locations.md`「Write contract」一节，那里是它的定义处。

本组用到的两个接缝：`load_book_cached`、`BOOKS_DIR`（都在 `OWNERSHIP` 名单里）。
留在 `server` 的 helper：`_validate_book_id`、`_annotation_matches_chapter_text`
—— 前者全组通用，后者是 `_refresh_orphaned_annotations` 的文本匹配细节，两者都还有别的用户。
"""

from __future__ import annotations

import html
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...models.annotations import Annotation
from ...notes_service import (
    NOTES_SCHEMA_VERSION,
    NotesVersionConflict,
    add_annotation_and_version as add_note_annotation,
    delete_annotation_and_version as delete_note_annotation,
    refresh_annotations_and_version,
    update_annotation_and_version as update_note_annotation,
)
from ...reader3 import Book

router: APIRouter = APIRouter()

#: 011 WI-5a —— 乐观并发的 HTTP 半边。版本进出都走 header：`ETag` 出、`If-Match` 入。
#: `If-Match` **可选**：不带它的请求与乐观并发落地之前逐字节一致（状态码、响应体都不变），
#: 这是 ADR-0011「不得改变任何响应形状」在本组的兑付方式，也是 `tests/contract` 一行不改
#: 仍然全绿的原因。带它的请求换来的是一次真正的 compare-and-swap —— 比较在
#: `notes_service` 的书级锁里做，不在这一层，否则两个请求会双双通过检查再依次落盘。
CONFLICT_DETAIL = "Annotation version conflict"


def _etag(version: str) -> str:
    """把裸版本号包成一个强 ETag。客户端原样抄回 `If-Match` 即可。"""
    return f'"{version}"'


def _conflict(exc: NotesVersionConflict) -> JSONResponse:
    """409 的响应体：当前版本 ＋ 服务端当前那一条标注（新建时为 `null`）。

    `annotation` 不是可选的装饰。DEG-S5 要求冲突对话框把两版正文**同时**摆出来让用户二选一；
    本地那版客户端自己有，远端那版只能从这里来。少了它，用户只能闭着眼睛丢掉一版自己的字。

    `note_text` 按 GET 的口径 `html.unescape` 还原：对话框要展示的是他打的字，不是 `&amp;`。
    """
    annotation = None
    if exc.current_annotation is not None:
        annotation = exc.current_annotation.to_dict()
        if annotation.get("note_text") is not None:
            annotation["note_text"] = html.unescape(str(annotation["note_text"]))
    return JSONResponse(
        status_code=409,
        content={
            "detail": CONFLICT_DETAIL,
            "etag": _etag(exc.current_version),
            "annotation": annotation,
        },
    )


def _mark_orphans(book: Book, annotations: list[Annotation]) -> bool:
    """把正文里找不到的标注标成 orphaned，返回「改没改」。

    纯内存、不碰盘：它在书级写锁里跑（见 `refresh_annotations_and_version`），
    这里做的任何 I/O 都是在加长其他写者的排队时间。
    """
    changed = False
    chapter_text_by_index: dict[int, str] = {}

    for ann in annotations:
        if ann.orphaned:
            continue
        if ann.chapter_index < 0 or ann.chapter_index >= len(book.spine):
            ann.orphaned = True
            changed = True
            continue
        if ann.chapter_index not in chapter_text_by_index:
            chapter_text_by_index[ann.chapter_index] = book.spine[ann.chapter_index].text or ""
        if not _server._annotation_matches_chapter_text(chapter_text_by_index[ann.chapter_index], ann):
            ann.orphaned = True
            changed = True

    return changed


def _refresh_orphaned_annotations(book_id: str, book: Book) -> tuple[list[Annotation], list[Annotation], str]:
    """读路由的 load → 刷新 → 存盘，**整段在书级锁里**（017 WI-4，审计 #1）。

    load 也搬进了锁里，这是关键：只把 save 包起来，GET 依旧会拿着一份锁外读到的陈旧
    快照覆盖别人在这期间提交成功的写。返回 `(全部, 活着的, 版本)` —— ETag 算的是整本书
    的全部标注，读结果里只出现活着的那些。
    """
    annotations, version = refresh_annotations_and_version(
        _server.BOOKS_DIR, book_id, lambda anns: _mark_orphans(book, anns)
    )
    return annotations, [a for a in annotations if not a.orphaned], version


class CreateAnnotationRequest(BaseModel):
    type: str = Field(..., description="marker|wavy|underline|note")
    color: Optional[str] = Field(default=None, description="yellow|green|pink|blue")
    quote: str
    prefix: str = ""
    suffix: str = ""
    position: Optional[int] = None
    cfi: Optional[str] = Field(default=None, description="epub.js CFI for precise anchor")
    note_text: Optional[str] = None


class UpdateAnnotationRequest(BaseModel):
    note_text: str = Field(..., description="Updated note text")


@router.get("/api/notes/{book_id}")
async def api_get_book_notes(book_id: str, response: Response):
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    annotations, active, version = _refresh_orphaned_annotations(safe_book_id, book)

    by_chapter: dict[int, list[Annotation]] = {}
    for ann in active:
        by_chapter.setdefault(ann.chapter_index, []).append(ann)

    def _sort_key(a: Annotation):
        return (a.position is None, a.position or 0, a.created_at, a.id)

    annotations_by_chapter = []
    total_count = 0
    for chapter_index in sorted(by_chapter.keys()):
        items = sorted(by_chapter[chapter_index], key=_sort_key)
        chapter_title = book.spine[chapter_index].title if 0 <= chapter_index < len(book.spine) else ""

        summaries = []
        for a in items:
            quote = a.quote if len(a.quote) <= 200 else a.quote[:197] + "..."
            note_text = html.unescape(a.note_text) if a.note_text is not None else None
            if note_text is not None and len(note_text) > 200:
                note_text = note_text[:197] + "..."
            summaries.append(
                {
                    "id": a.id,
                    "type": a.type,
                    "color": a.color,
                    "quote": quote,
                    "note_text": note_text,
                    "position": a.position,
                    "created_at": a.created_at,
                }
            )

        annotations_by_chapter.append(
            {
                "chapter_index": chapter_index,
                "chapter_title": chapter_title,
                "count": len(items),
                "annotations": summaries,
            }
        )
        total_count += len(items)

    # 书级汇总也带版本，且与章级那条是同一个值 —— 版本的粒度是「一本书的全部标注」，两条读
    # 路由读的是同一份状态。笔记面板只走这一条，不给它 ETag 等于逼它为了拿版本号多读一次章级
    # 路由。只加 header，响应体一个字段都没动。
    response.headers["ETag"] = _etag(version)

    return {
        "schema_version": NOTES_SCHEMA_VERSION,
        "book_id": safe_book_id,
        "total_count": total_count,
        "annotations_by_chapter": annotations_by_chapter,
    }


@router.get("/api/notes/{book_id}/{chapter_index}")
async def api_get_chapter_notes(book_id: str, chapter_index: int, response: Response):
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    annotations, active, version = _refresh_orphaned_annotations(safe_book_id, book)
    items = [a for a in active if a.chapter_index == chapter_index]
    items.sort(key=lambda a: (a.position is None, a.position or 0, a.created_at, a.id))

    out = []
    for a in items:
        d = a.to_dict()
        if d.get("note_text") is not None:
            d["note_text"] = html.unescape(str(d["note_text"]))
        out.append(d)

    # 版本算的是**整本书**的标注（`annotations`，含 orphaned 的那些），不是本章过滤后的
    # `items`：写路由的比较对象是整份文件，读回来的版本若只覆盖一章，客户端拿它去写就会在
    # 另一章的改动上撞出假冲突，或者更糟 —— 漏掉真冲突。
    response.headers["ETag"] = _etag(version)

    return {
        "book_id": safe_book_id,
        "chapter_index": chapter_index,
        "count": len(items),
        "annotations": out,
    }


@router.post("/api/notes/{book_id}/{chapter_index}", status_code=201)
async def api_create_annotation(
    book_id: str,
    chapter_index: int,
    payload: CreateAnnotationRequest,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    ann_type = str(payload.type or "").strip().lower()
    if ann_type not in ("marker", "wavy", "underline", "note"):
        raise HTTPException(status_code=400, detail="Invalid type")

    color = payload.color
    if not color:
        color = "yellow"
    if color not in ("yellow", "green", "pink", "blue"):
        raise HTTPException(status_code=400, detail="Invalid color")

    note_text = payload.note_text
    if ann_type == "note":
        if note_text is None or not str(note_text).strip():
            raise HTTPException(status_code=400, detail="note_text is required for type=note")
        note_text = html.escape(str(note_text))
    else:
        note_text = None

    quote = str(payload.quote or "")
    if not quote.strip():
        raise HTTPException(status_code=400, detail="quote is required")

    prefix = str(payload.prefix or "")
    suffix = str(payload.suffix or "")
    if len(prefix) > 50:
        prefix = prefix[-50:]
    if len(suffix) > 50:
        suffix = suffix[:50]

    position = payload.position
    if position is not None:
        try:
            position = int(position)
        except Exception:  # noqa: BLE001 - 第 3 档：position 解析不出来就退回 None，标注仍靠 quote/prefix/suffix 锚定；类型待收窄为 (TypeError, ValueError)
            position = None
    if position is not None and position < 0:
        position = 0

    cfi = str(payload.cfi).strip() if payload.cfi is not None else None
    if not cfi:
        cfi = None

    annotation = Annotation(
        book_id=safe_book_id,
        chapter_index=chapter_index,
        type=ann_type,  # type: ignore[arg-type]
        color=color,  # type: ignore[arg-type]
        quote=quote,
        prefix=prefix,
        suffix=suffix,
        position=position,
        cfi=cfi,
        note_text=note_text,
        orphaned=False,
    )

    try:
        saved, version = add_note_annotation(_server.BOOKS_DIR, annotation, if_match=if_match)
    except NotesVersionConflict as e:
        return _conflict(e)

    response.headers["ETag"] = _etag(version)
    return {"id": saved.id, "created_at": saved.created_at, "message": "Annotation created successfully"}


@router.delete("/api/notes/{book_id}/{chapter_index}/{note_id}", status_code=204)
async def api_delete_annotation(
    book_id: str,
    chapter_index: int,
    note_id: str,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    try:
        ok, version = delete_note_annotation(_server.BOOKS_DIR, safe_book_id, note_id, if_match=if_match)
    except NotesVersionConflict as e:
        return _conflict(e)

    if not ok:
        raise HTTPException(status_code=404, detail="Annotation not found")
    # 204 仍然是 204、仍然没有 body；多的只有一个 header。
    return Response(status_code=204, headers={"ETag": _etag(version)})


@router.put("/api/notes/{book_id}/{chapter_index}/{note_id}")
async def api_update_annotation(
    book_id: str,
    chapter_index: int,
    note_id: str,
    payload: UpdateAnnotationRequest,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    note_text = str(payload.note_text or "").strip()
    if not note_text:
        raise HTTPException(status_code=400, detail="note_text is required")

    note_text = html.escape(note_text)
    try:
        updated, version = update_note_annotation(
            _server.BOOKS_DIR, safe_book_id, note_id, note_text, if_match=if_match
        )
    except NotesVersionConflict as e:
        return _conflict(e)

    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")

    response.headers["ETag"] = _etag(version)
    return {"id": updated.id, "note_text": updated.note_text, "message": "Annotation updated successfully"}

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from .. import server as _server  # noqa: E402
