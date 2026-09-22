"""`/api/ai/question/{book_uuid}` —— 问答，含 SSE 流式那条路。

拆自 `web/server.py`（011 WI-4）。路由正文一字未改。

**这个文件带着 011 §5 那条唯一的、具名的、会到期的行数豁免**（上限 560 行，
判据与到期条件在 011 §5，机器执行者是 `scripts/check_router_size.py`）。
豁免存在的原因就在这个文件里：`api_ai_question` 是一个 433 行的**单函数**，
里面 6 个嵌套闭包，按职责再怎么搬也搬不散——拆它是行为变更，不属于本 WI。
跟它一起搬过来的是只有它用的 SSE 机件：`_sse_event`、`_stop_stream_worker`。
**豁免只许下调不许上调**：等哪天 `api_ai_question` 真被分解了，把 560 改小，
`check_router_size.py` 会因为「豁免不再被挣得」自己报红，要求删掉这条豁免。

`_push_event` 没有跟过来，留在 `server`：它有 4 处 `server._push_event(...)` 的直接
测试调用点（tests/unit/test_exception_stream_push.py），那些用例钉的是队列背压语义，
不是本路由的行为。这是个判断，不是规避——它和 `_sse_event` 只差一层，
搬它也对，只是要顺手改 4 个调用点而换不来什么。

**这个文件里有全进程唯一的 provider 出口**：`_server._call_provider` 与
`_server._egress_post_stream`（ADR-0006）。两者都必须走 `_server.` 属性访问，
形状一旦退化成导入期绑定，「保证零真实外发」的测试会一边全绿、一边把明文 API key
打到真 provider 上。实测哪道闸抓哪种形状，见 011 WI-4/4 的 commit message。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ... import server as _server
from ...schemas import AIQuestionRequest
from ....ai.conversations import ConversationMessage as DiskConversationMessage
from ....ai.routing import (
    provider_context_window,
    unique_chapter_orders_from_passages,
)

router: APIRouter = APIRouter()


def _sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _stop_stream_worker(
    *,
    label: str,
    stop_event: Optional[threading.Event] = None,
    thread: Optional[threading.Thread] = None,
    task: "Optional[asyncio.Task]" = None,
    timeout_s: Optional[float] = None,
) -> bool:
    """取消一个流式 worker 并**等它真的停下**，最多等 ``_server.AI_WORKER_STOP_TIMEOUT_S``。

    为什么要等：调用方紧接着就会释放队列租约，而释放租约的含义是「这本书可以开始
    下一个请求了」。不等就放，下一个「本该串行」的请求会和上一个还活着的 worker
    并发打同一个 provider——串行语义于是只是个说法。

    **等不到怎么办：仍然释放租约，只留一条 ERROR。** 这个取舍是刻意的，两害相权：

    * 租约永久泄漏 = 这本书的 AI 问答**功能性死亡**，之后每一个请求都排在一个永不
      结束的请求后面，且只有重启才能恢复；
    * 一个跑飞的 worker = 多一次 provider 调用的开销和一个线程。ollama 线程是
      ``daemon=True``，进程退出时会被回收；非流式 task 已经 cancel 过，它下一个
      await 点就会退出。

    后者可观测（这条 ERROR 就是），前者不可观测且不可恢复。所以宁可漏 worker，
    不可漏租约。

    返回 worker 是否在上界内停住——调用方不看返回值，返回值是给测试和以后的调用方的。
    """
    bound = _server.AI_WORKER_STOP_TIMEOUT_S if timeout_s is None else timeout_s

    if stop_event is not None:
        stop_event.set()

    if task is not None:
        if not task.done():
            task.cancel()
        await asyncio.wait({task}, timeout=max(0.0, bound))
        if not task.done():
            _server.ai_logger.error(
                "%s worker did not stop within %.1fs after cancellation; "
                "releasing the AI queue lease anyway (a leaked lease would block this book permanently)",
                label,
                bound,
            )
            return False
        return True

    if thread is not None:
        if thread.is_alive():
            await run_in_threadpool(thread.join, max(0.0, bound))
        if thread.is_alive():
            _server.ai_logger.error(
                "%s worker thread did not stop within %.1fs after the stop event was set; "
                "releasing the AI queue lease anyway (a leaked lease would block this book permanently)",
                label,
                bound,
            )
            return False
        return True

    return True


@router.post("/api/ai/question/{book_uuid}")
async def api_ai_question(request: Request, book_uuid: str, body: AIQuestionRequest, stream: bool = False):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="question too long (max 1000 chars)")

    provider_name, api_key, base_url, model, timeout_s = _server._get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    if stream:
        # 租约的**唯一**释放点在这个栈上（下面 push_async_callback 注册的
        # ``_release_lease``）。以前这里是三处散落的显式 release，各自兜一种具体
        # 异常——而 acquire 到 return 之间的那一大段还会抛别的：任何一种没被点名的
        # 异常都带着租约逃走，那条队列于是永久 active（C4）。
        #
        # 为什么必须是栈而不是一个 try/finally：租约的生命周期跨越「函数返回」这
        # 条界——正常路径上它要活到 SSE 流结束为止。``pop_all()`` 把待办的释放动作
        # **移交**给生成器；移交发生在最后一步，在那之前的任何异常都由这里的
        # ``async with`` 收尾，移交之后这里关的是一个空栈。
        #
        # 后压进去的回调先跑（LIFO），所以生成器里压的「停 worker」一定跑在
        # 「放租约」之前——顺序即语义：租约放掉就等于允许下一个请求开始。
        lease_stack = contextlib.AsyncExitStack()
        async with lease_stack:
            lease = await _server.ai_queue.acquire(
                queue_key,
                request=request,
                timeout_s=float(timeout_s),
                request_label="question",
            )

            async def _release_lease() -> None:
                await _server.ai_queue.release(lease)

            lease_stack.push_async_callback(_release_lease)

            book = await run_in_threadpool(_server.load_book_cached, book_folder)
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")

            try:
                passages, retrieval_time_ms = await run_in_threadpool(
                    _server.retrieve_passages,
                    book_folder,
                    books_dir=_server.BOOKS_DIR,
                    query=question,
                    k=body.rag_k,
                    min_similarity=0.35,
                )
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e))

            ctx_window = provider_context_window(provider_name, model)
            book_tokens, max_chapter_tokens = await run_in_threadpool(_server.book_token_stats, book)
            decision = _server.choose_routing(
                provider_ctx_window=ctx_window,
                book_tokens=book_tokens,
                max_chapter_tokens=max_chapter_tokens,
            )
            _server.ai_logger.debug(
                "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=1",
                str(book_uuid),
                provider_name,
                model,
                decision.mode,
                int(book_tokens),
                int(ctx_window),
            )
            if decision.mode == "full_book":
                context = await run_in_threadpool(_server.build_full_book_context, book, budget_tokens=decision.budget_tokens)
            elif decision.mode == "multi_chapter":
                orders = unique_chapter_orders_from_passages(passages, limit=8)
                context, _used = await run_in_threadpool(
                    _server.build_multi_chapter_context, book, chapter_orders=orders, budget_tokens=decision.budget_tokens
                )
            else:
                context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
            history = (body.conversation_history or [])[-50:]
            chat_history = []
            for m in history:
                role = (m.role or "").strip().lower()
                if role not in ("user", "assistant"):
                    continue
                content = (m.content or "").strip()
                if not content:
                    continue
                chat_history.append({"role": role, "content": content})

            system = (
                "你是 Reader3 的 AI 阅读助手。"
                "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
                "回答要清晰、简洁。"
            )
            user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

            message_id = str(__import__("uuid").uuid4())
            started = time.perf_counter()
            answer_parts: list[str] = []
            conversation_id = _server._conversation_id_from_history(history)

            async def event_gen(lease_stack: contextlib.AsyncExitStack):
                q: asyncio.Queue[dict] = asyncio.Queue()
                loop = asyncio.get_running_loop()
                stop_event = threading.Event()

                def push(evt: dict) -> None:
                    _server._push_event(q, evt)

                def worker_ollama() -> None:
                    url = _server._ollama_root_base_url(base_url or "http://localhost:11434") + "/api/chat"
                    chat_messages = []
                    if system:
                        chat_messages.append({"role": "system", "content": system})
                    chat_messages.extend([*chat_history, {"role": "user", "content": user}])
                    payload = {
                        "model": model,
                        "messages": chat_messages,
                        "stream": True,
                        "options": {"num_predict": max(64, min(int(body.max_tokens), 4096))},
                    }
                    model_out = model
                    finish_reason = "stop"
                    try:
                        # post_stream 交出的是**还没读**的 response：下面这个循环仍然逐行读，
                        # 每行之前检查 stop_event。换成 post_json 就等于先把整段回答读完
                        # 再开始推 chunk，断连之后也停不下来。
                        with _server._egress_post_stream(url, payload=payload, timeout_s=int(timeout_s)) as resp:
                            while True:
                                # 客户端走了或者超时了：别再往一个没人读的队列里推，
                                # 也别继续跟 provider 说话。检查放在读之前，所以
                                # 「停」最迟在下一行数据到达时生效。
                                if stop_event.is_set():
                                    return
                                line = resp.readline()
                                if not line:
                                    break
                                raw = line.strip()
                                if not raw:
                                    continue
                                try:
                                    obj = json.loads(raw.decode("utf-8", errors="replace") or "{}")
                                except Exception:  # noqa: BLE001 - 第 3 档：ollama 流里解析不了的一行直接跳过，下一行还会来；终止条件是 done 事件，不是这一行
                                    continue
                                if not isinstance(obj, dict):
                                    continue
                                if obj.get("model"):
                                    model_out = str(obj.get("model") or model_out)
                                msg = obj.get("message")
                                if isinstance(msg, dict):
                                    delta = msg.get("content")
                                    if delta:
                                        loop.call_soon_threadsafe(push, {"type": "chunk", "delta": str(delta)})
                                if obj.get("done") is True:
                                    finish_reason = str(obj.get("done_reason") or finish_reason)
                                    break
                        loop.call_soon_threadsafe(push, {"type": "done", "model": model_out, "finish_reason": finish_reason})
                    except Exception as e:  # noqa: BLE001 - 第 2 档：worker 线程的最外层，失败经 error 事件送到客户端，痕迹在 SSE 流里
                        if stop_event.is_set():
                            # 已经被叫停了：这个异常多半就是叫停造成的（连接被拆、
                            # 循环已关）。往一个没人读的队列里推 error 只会在
                            # worker 线程里再抛一次，那次没人接得住。
                            return
                        loop.call_soon_threadsafe(push, {"type": "error", "message": str(e)})

                async def worker_non_stream() -> None:
                    try:
                        resp = await run_in_threadpool(
                            _server._call_provider,
                            provider_name,
                            api_key=api_key,
                            base_url=base_url,
                            model=model,
                            system=system,
                            messages=[*chat_history, {"role": "user", "content": user}],
                            max_tokens=body.max_tokens,
                            timeout_s=timeout_s,
                        )
                    except Exception as e:  # noqa: BLE001 - 第 2 档：worker 协程的最外层，失败经 error 事件送到客户端，痕迹在 SSE 流里
                        await q.put({"type": "error", "message": str(e)})
                        return
                    await q.put({"type": "chunk", "delta": resp.text})
                    await q.put({"type": "done", "model": resp.model, "finish_reason": resp.finish_reason})

                # 租约从 handler 那边**移交**到这里；出这个 with 块就是放租约，
                # 无论是正常 return、客户端断连、超时，还是生成器被 aclose()。
                async with lease_stack:
                    yield _sse_event(
                        "meta",
                        {
                            "message_id": message_id,
                            "retrieval_sources": passages,
                            "metadata": {"retrieval_time_ms": retrieval_time_ms, "provider": provider_name},
                        },
                    )

                    # 停 worker 的回调**后**压栈，所以它**先**跑（LIFO）：租约必须
                    # 在 worker 真的停下之后才放，否则下一个「本该串行」的请求会
                    # 和上一个还活着的 worker 并发打同一个 provider（C5）。
                    if provider_name == "ollama":
                        thread = threading.Thread(target=worker_ollama, daemon=True)
                        thread.start()
                        lease_stack.push_async_callback(
                            _stop_stream_worker,
                            label="ollama question stream",
                            stop_event=stop_event,
                            thread=thread,
                        )
                    else:
                        task = asyncio.create_task(worker_non_stream())
                        lease_stack.push_async_callback(
                            _stop_stream_worker,
                            label="question stream",
                            stop_event=stop_event,
                            task=task,
                        )

                    while True:
                        if request is not None and await request.is_disconnected():
                            yield _sse_event("error", {"message": "Client disconnected"})
                            return
                        if time.monotonic() >= lease.deadline:
                            yield _sse_event("error", {"message": "AI request timed out"})
                            return
                        try:
                            evt = await asyncio.wait_for(q.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue

                        et = str(evt.get("type") or "")
                        if et == "chunk":
                            delta = str(evt.get("delta") or "")
                            answer_parts.append(delta)
                            yield _sse_event("chunk", {"delta": delta})
                            continue
                        if et == "done":
                            generation_time_ms = int((time.perf_counter() - started) * 1000)
                            if conversation_id:
                                ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
                                answer_text = "".join(answer_parts)
                                await run_in_threadpool(
                                    _server._save_conversation_snapshot,
                                    book_uuid=str(book_uuid),
                                    book_folder=book_folder,
                                    conversation_id=conversation_id,
                                    provider=provider_name,
                                    model=str(evt.get("model") or model),
                                    history=history,
                                    assistant_message=DiskConversationMessage(
                                        id=message_id,
                                        role="assistant",
                                        content=answer_text,
                                        timestamp=ts,
                                        metadata={
                                            "retrieval_sources": passages,
                                            "provider": provider_name,
                                        },
                                    ),
                                )
                            yield _sse_event(
                                "done",
                                {
                                    "model": str(evt.get("model") or model),
                                    "finish_reason": str(evt.get("finish_reason") or "stop"),
                                    "metadata": {
                                        "retrieval_time_ms": retrieval_time_ms,
                                        "generation_time_ms": generation_time_ms,
                                        "provider": provider_name,
                                    },
                                },
                            )
                            return
                        if et == "error":
                            yield _sse_event("error", {"message": str(evt.get("message") or "AI request failed")})
                            return

            # pop_all() 之后本层的 lease_stack 是空的，上面那个 async with 关它是
            # 个 no-op —— 租约的收尾责任已经在生成器手上。这一步必须是本分支的
            # 最后一步：在它之前抛的任何异常都还由这里负责释放。
            return StreamingResponse(event_gen(lease_stack.pop_all()), media_type="text/event-stream")

    async def _do() -> dict:
        book = await run_in_threadpool(_server.load_book_cached, book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        try:
            passages, retrieval_time_ms = await run_in_threadpool(
                _server.retrieve_passages,
                book_folder,
                books_dir=_server.BOOKS_DIR,
                query=question,
                k=body.rag_k,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = await run_in_threadpool(_server.book_token_stats, book)
        decision = _server.choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        _server.ai_logger.debug(
            "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=0",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

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

        history = (body.conversation_history or [])[-50:]
        anthropic_history = []
        for m in history:
            role = (m.role or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            anthropic_history.append({"role": role, "content": content})

        system = (
            "你是 Reader3 的 AI 阅读助手。"
            "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
            "回答要清晰、简洁。"
        )
        user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

        started = time.perf_counter()
        try:
            resp = await run_in_threadpool(
                _server._call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[*anthropic_history, {"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                _server.ai_logger.debug(
                    "question fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于回答）：\n{rag_context}\n\n问题：{question}\n"
                resp = await run_in_threadpool(
                    _server._call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[*anthropic_history, {"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        generation_time_ms = int((time.perf_counter() - started) * 1000)

        msg_id = str(__import__("uuid").uuid4())
        conversation_id = _server._conversation_id_from_history(body.conversation_history or [])
        if conversation_id:
            ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
            await run_in_threadpool(
                _server._save_conversation_snapshot,
                book_uuid=str(book_uuid),
                book_folder=book_folder,
                conversation_id=conversation_id,
                provider=provider_name,
                model=resp.model,
                history=(body.conversation_history or [])[-50:],
                assistant_message=DiskConversationMessage(
                    id=msg_id,
                    role="assistant",
                    content=resp.text,
                    timestamp=ts,
                    metadata={
                        "retrieval_sources": passages,
                        "provider": provider_name,
                    },
                ),
            )
        return {
            "answer": resp.text,
            "message_id": msg_id,
            "retrieval_sources": passages,
            "metadata": {
                "token_count": resp.token_count,
                "model": resp.model,
                "finish_reason": resp.finish_reason,
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "provider": provider_name,
                "routing": routing_meta,
            },
        }

    return await _server.ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="question",
        fn=_do,
    )
