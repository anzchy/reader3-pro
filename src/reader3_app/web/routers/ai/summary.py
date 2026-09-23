"""`/api/ai/summary/{book_uuid}` —— 整本／多章摘要。

拆自 `web/server.py`（011 WI-4）。路由正文一字未改，`_summary_prompt` 与
`_parse_summary_payload` 两个只有本路由用的 helper 一起搬了过来。

**这个文件里有一条真实的 LLM 出口**（`_server._call_provider`，ADR-0006 的全进程唯一
provider 出口）。它和排队、上下文预算相关的接缝一律走 `_server.`：`ai_queue`、
`_get_provider_runtime`、`book_token_stats`、`choose_routing`、
`build_full_book_context`、`build_multi_chapter_context`、`retrieve_passages`、
`load_book_cached`、`BOOKS_DIR`、`book_uuid_resolver`。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from ...schemas import AISummaryRequest
from ....ai.queue import QueueBudget
from ....ai.routing import (
    provider_context_window,
    unique_chapter_orders_from_passages,
)

router: APIRouter = APIRouter()


def _summary_prompt(summary_type: str) -> str:
    st = (summary_type or "full").strip().lower()
    if st not in {"overview", "highlights", "background", "full"}:
        st = "full"
    if st == "overview":
        return "只生成 overview（2-3 段），其余字段可以留空。"
    if st == "highlights":
        return "只生成 highlights（5-10 条要点，每条 1-2 句），其余字段可以留空。"
    if st == "background":
        return "只生成 background（2-4 段：作者/时代/意义/背景），其余字段可以留空。"
    return "生成 overview（2-3 段）、highlights（5-10 条）、background（2-4 段）。"


def _parse_summary_payload(text: str, *, summary_type: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"overview": "", "highlights": [], "background": ""}
    payload: Any = None
    try:
        payload = json.loads(raw)
    except ValueError as e:
        # 第 3 档：模型直接回散文是预期的降级路径，不是错误——但它得留痕，
        # 否则「为什么这本书的 highlights 永远是空的」无从查起。
        # 只吞 JSONDecodeError（ValueError 子类）：RecursionError / MemoryError
        # 这类「不是散文，是出事了」的失败必须冒上去，不然用户拿到的是一段被
        # 当成 overview 的括号。字段组装也因此移出 try——它出错是我们的 bug。
        _server.ai_logger.debug("summary reply is not JSON (summary_type=%s): %s", summary_type, e)

    if isinstance(payload, dict):
        overview = str(payload.get("overview") or "")
        background = str(payload.get("background") or "")
        highlights_raw = payload.get("highlights") or []
        highlights = [str(x) for x in highlights_raw] if isinstance(highlights_raw, list) else []
        return {"overview": overview, "highlights": highlights, "background": background}
    if payload is not None:
        _server.ai_logger.debug(
            "summary reply parsed as %s, not an object (summary_type=%s)",
            type(payload).__name__,
            summary_type,
        )

    st = (summary_type or "full").strip().lower()
    if st == "highlights":
        lines = [ln.strip(" \t-•*") for ln in raw.splitlines() if ln.strip()]
        highlights = [ln for ln in lines if ln][:10]
        return {"overview": "", "highlights": highlights, "background": ""}
    if st == "background":
        return {"overview": "", "highlights": [], "background": raw}
    return {"overview": raw, "highlights": [], "background": ""}


@router.post("/api/ai/summary/{book_uuid}")
async def api_ai_summary(
    request: Request,
    book_uuid: str,
    body: AISummaryRequest,
    summary_type: str = "full",
    force_regenerate: bool = False,  # cache is frontend-side for v1
):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")

    provider_name, api_key, base_url, model, timeout_s = _server._get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    async def _do(budget: QueueBudget) -> dict:
        book = await run_in_threadpool(_server.load_book_cached, book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = await run_in_threadpool(_server.book_token_stats, book)
        decision = _server.choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        _server.ai_logger.debug(
            "summary routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

        try:
            passages, retrieval_time_ms = await run_in_threadpool(
                _server.retrieve_passages,
                book_folder,
                books_dir=_server.BOOKS_DIR,
                query="Summarize the entire book: main ideas, structure, themes, and key takeaways.",
                k=12,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        routing_meta: dict[str, Any] = {"mode": decision.mode, "provider_context_window": int(ctx_window)}
        if decision.mode == "full_book":
            context = await run_in_threadpool(_server.build_full_book_context, book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, used_orders = await run_in_threadpool(
                _server.build_multi_chapter_context, book, chapter_orders=orders, budget_tokens=decision.budget_tokens
            )
            routing_meta["chapters"] = used_orders
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
        system = (
            "你是 Reader3 的 AI 阅读助手。默认用中文回答（如果用户明确用英文提问，则用英文）。"
            "请基于提供的书籍内容生成总结。"
            "严格输出 JSON，且仅输出 JSON。"
            "JSON 格式：{"
            '"overview": string, '
            '"highlights": string[], '
            '"background": string'
            "}。"
            + _summary_prompt(summary_type)
        )
        user = f"书籍内容（用于总结）：\n{context}\n"
        try:
            resp = await run_in_threadpool(
                _server._call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
                deadline=budget.deadline,
                should_stop=budget.should_stop,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                _server.ai_logger.debug(
                    "summary fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于总结）：\n{rag_context}\n"
                resp = await run_in_threadpool(
                    _server._call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                    deadline=budget.deadline,
                    should_stop=budget.should_stop,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        payload = _parse_summary_payload(resp.text, summary_type=summary_type)
        return {
            "book_uuid": str(book_uuid),
            "content": payload,
            "provider": provider_name,
            "model": resp.model,
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "token_count": resp.token_count,
            "from_cache": False,
            "metadata": {
                "retrieval_time_ms": retrieval_time_ms,
                "finish_reason": resp.finish_reason,
                "routing": routing_meta,
            },
        }

    return await _server.ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="summary",
        fn=_do,
    )

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from ... import server as _server  # noqa: E402
