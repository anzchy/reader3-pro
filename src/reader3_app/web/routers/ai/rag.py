"""`/api/ai/rag/retrieve` —— 检索片段，不调用任何 provider。

拆自 `web/server.py`（011 WI-4）。路由正文一字未改。
接缝：`BOOKS_DIR`、`book_uuid_resolver`、`retrieve_passages`。
**这个文件里没有 LLM 出口**——它只做检索，答案的生成在 `chat.py` / `summary.py`。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from ... import server as _server
from ...schemas import AIRagRequest

router = APIRouter()


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


