"""`/api/ai/rag/retrieve` —— 检索片段，不调用任何 provider。

拆自 `web/server.py`（011 WI-4）。路由正文一字未改。
接缝：`BOOKS_DIR`、`book_uuid_resolver`、`retrieve_passages`。
**这个文件里没有 LLM 出口**——它只做检索，答案的生成在 `chat.py` / `summary.py`。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...schemas import AIRagRequest

router: APIRouter = APIRouter()


@router.post("/api/ai/rag/retrieve")
async def api_ai_rag_retrieve(body: AIRagRequest):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(body.book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        passages, retrieval_time_ms = await run_in_threadpool(
            _server.retrieve_passages,
            book_folder,
            books_dir=_server.BOOKS_DIR,
            query=body.query,
            k=body.k,
            min_similarity=body.min_similarity,
        )
        return {"passages": passages, "retrieval_time_ms": retrieval_time_ms}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------------------------
# 017 WI-1（审计 #7）——**这一行必须留在文件末尾**，在 `router` 与所有路由都定义完之后。
#
# `server` 在它自己的文件末尾要取 `routers.<本模块>.router` 这个**属性**来 include。
# 如果本模块在顶部就导入 `server`，而本进程又是从本模块开始导入的，那么 `server` 会在
# 本模块只执行到第 1 行的时候跑完整个文件体，然后去取一个还不存在的 `router`：
#     AttributeError: partially initialized module ... has no attribute 'router'
# 把导入挪到末尾，`router` 就已经在模块命名空间里，`server` 取得到，环自己解开。
#
# 这不影响打桩接缝：`_server.X` 仍是**调用时**解析属性，`monkeypatch.setattr(server, …)`
# 照常生效。绑的依旧是模块对象，不是属性——规矩见 `routers/__init__.py` 的 docstring。
# ---------------------------------------------------------------------------
from ... import server as _server  # noqa: E402
