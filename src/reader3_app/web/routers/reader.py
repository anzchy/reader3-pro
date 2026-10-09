"""`/read/*` —— 阅读页、epub 原件与书内图片。

拆自 `web/server.py`（011 WI-4）。**路由正文一字未改**（含 `serve_image` 里那段
关于 `isfile` 而不是 `exists` 的注释——它记的是一个真实缺陷的判据，不能在搬家时丢）。
改的只有三类引用：`@app.x` → `@router.x`，接缝与 `server` 私有 helper 改走 `_server.`。

两个接缝：`BOOKS_DIR`、`load_book_cached`。
留在 `server` 的：`_validate_book_id`、`_book_uuid_or_none`、`_ui_default_provider`、
`templates`。注意 `_validate_book_id_path_safe` 本组不用——`serve_image` 用的是
裸 `os.path.basename`，那是它自己的历史，改它是行为变更，不属于本 WI。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse

from ...book_store import chapter_orders, find_chapter, neighbour_orders
from ..urls import cover_url as build_cover_url


router: APIRouter = APIRouter()


@router.get("/read/{book_id}/book.epub")
async def serve_epub(book_id: str):
    """Serve the original EPUB for epub.js rendering."""
    safe_book_id = _server._validate_book_id(book_id)
    epub_path = os.path.join(_server.BOOKS_DIR, safe_book_id, "book.epub")
    if not os.path.exists(epub_path):
        raise HTTPException(status_code=404, detail="EPUB not found")
    return FileResponse(epub_path, filename="book.epub")


@router.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(request: Request, book_id: str):
    """Helper to just go to chapter 0.

    ``request`` 必须显式接下来再透传：``read_chapter`` 要拿它渲染模板，漏了会
    在**每一次**调用上 TypeError，也就是这条路由一直是 500 而不是 404。它逃过
    人眼是因为书库页链接直接指向 ``/read/{id}/0``，只有手敲 URL 的人会撞上。
    mypy 的 ``call-arg`` 抓到了它 —— 这是本仓库开 mypy 的第一笔收益。
    """
    return await read_chapter(request=request, book_id=book_id, chapter_index=0)

@router.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface.

    ``_server._validate_book_id`` must run **before** ``_server.load_book_cached``, and that
    ordering is the whole point: ``_server.load_book_cached`` joins its argument onto
    ``_server.BOOKS_DIR`` and ``pickle.load``s the result, so an unvalidated ``book_id``
    is arbitrary-file deserialisation. ``GET /read/../0`` used to return 200
    with ``<_server.BOOKS_DIR>/../book.pkl`` rendered. The ``os.path.basename`` further
    down only ever sanitised the URLs written into the template — it ran after
    the unpickle and protected nothing. Everything below therefore uses
    ``safe_book_id``; the raw ``book_id`` must not appear again in this function.

    Note that ``TestClient``/httpx normalises ``..`` away before the request is
    built, so this is only reproducible by handing the raw ASGI scope to the
    app the way uvicorn does — see ``tests/contract/test_read_chapter_traversal.py``.
    """
    safe_book_id = _server._validate_book_id(book_id)
    book = _server.load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 012 WI-4c.2（ADR-0016 D-b，裁定 R-1）：chapter_index 是 order，不是位置。任何 n >= 0 都渲染 200；
    # 缺口（含越尾）没有章节 —— current_chapter 为 None、目录无高亮，epub.js 自己去显示那一节。
    # 次序不严格递增时这三个 helper 抛 BookCorrupt，交给中央的 book_corrupt_http（DP-7）。
    current_chapter = find_chapter(book, chapter_index, book_id=safe_book_id)
    prev_idx, next_idx = neighbour_orders(book, chapter_index, book_id=safe_book_id)
    chapter_position = (
        chapter_orders(book, book_id=safe_book_id).index(chapter_index) + 1 if current_chapter is not None else None
    )

    # 018 WI-2 (#6)：可能要取书锁，放进线程池，不在事件循环上等。
    book_uuid = await run_in_threadpool(_server._book_uuid_or_none, safe_book_id)
    cover_image = None
    try:
        images_dir = os.path.join(_server.BOOKS_DIR, safe_book_id, "images")
        if os.path.isdir(images_dir):
            candidates = [f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))]
            preferred = [f for f in candidates if "cover" in f.lower() or "title" in f.lower()]
            pick_from = preferred or candidates
            if pick_from:
                cover_image = sorted(pick_from, key=lambda x: (len(x), x.lower()))[0]
    except Exception:  # noqa: BLE001 - 第 3 档：同 187，封面挑选失败只影响一张缩略图
        cover_image = None
    cover_url = build_cover_url(safe_book_id, cover_image)
    epub_available = os.path.exists(os.path.join(_server.BOOKS_DIR, safe_book_id, "book.epub"))
    return _server.templates.TemplateResponse(request, "reader.html", {
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "chapter_position": chapter_position,
        "book_id": safe_book_id,
        "book_uuid": book_uuid,
        "cover_url": cover_url,
        "epub_url": f"/read/{safe_book_id}/book.epub",
        "epub_available": epub_available,
        "ai_default_provider": _server._ui_default_provider(),
        "prev_idx": prev_idx,
        "next_idx": next_idx
    })


@router.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(_server.BOOKS_DIR, safe_book_id, "images", safe_image_name)

    # isfile 而不是 exists：`image_name=".."` 是**唯一能穿过路由到达这里**的可疑输入
    # （路由参数是 [^/]+，任何含 `/` 的 payload 在匹配阶段就 404 了，所以上面两行
    # basename 其实碰不到东西）。而 basename("..") 仍是 ".."，于是 img_path 指向
    # images/ 的父目录——它存在，exists() 放行，FileResponse 拿到一个目录，
    # 在 send 阶段炸成 500。一次「文件不存在」被报成「服务器坏了」。
    if not os.path.isfile(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from .. import server as _server  # noqa: E402
