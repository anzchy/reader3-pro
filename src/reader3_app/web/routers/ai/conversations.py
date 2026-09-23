"""`/api/ai/conversations/*` —— 会话的读写、删除与导出。

拆自 `web/server.py`（011 WI-4）。路由正文一字未改，只改引用形状。
接缝：`BOOKS_DIR`、`book_uuid_resolver`、`load_ai_settings`。
留在 `server` 的：`_conversation_disk_storage_mode`、`_project_conversations_root`、
`SUPPORTED_AI_PROVIDERS`。`SaveConversationRequest` 只有本文件用，所以留在本文件，
没有塞进 `web/schemas.py`——schemas 收的是**跨 router 共用**的模型，不是所有模型。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ...schemas import AIMessage
from ....ai.conversations import (
    ConversationMessage as DiskConversationMessage,
    ConversationThread as DiskConversationThread,
    delete_conversation_multi as delete_disk_conversation_multi,
    list_conversations_combined as list_disk_conversations_combined,
    load_conversation_combined as load_disk_conversation_combined,
    save_conversation_multi as save_disk_conversation_multi,
)

router: APIRouter = APIRouter()


@router.get("/api/ai/conversations/{book_uuid}")
async def api_ai_list_conversations(book_uuid: str, provider: Optional[str] = None):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    settings = _server.load_ai_settings()
    threads = list_disk_conversations_combined(
        _server.BOOKS_DIR,
        book_folder=book_folder,
        book_uuid=str(book_uuid),
        provider=provider,
        project_conversations_root=_server._project_conversations_root(settings),
    )
    return {"book_uuid": str(book_uuid), "provider": (provider or "").strip().lower() or None, "conversations": threads}


@router.get("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_get_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = _server.load_ai_settings()
        thread = load_disk_conversation_combined(
            _server.BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_server._project_conversations_root(settings),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return thread.to_dict()


class SaveConversationRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    messages: list[AIMessage] = Field(default_factory=list)


@router.put("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_put_conversation(book_uuid: str, conversation_id: str, body: SaveConversationRequest):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    provider = (body.provider or "").strip().lower()
    if provider not in _server.SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    msgs: list[DiskConversationMessage] = []
    for m in body.messages or []:
        role = (m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        msg_id = str(m.id or "").strip()
        if not msg_id:
            continue
        msgs.append(
            DiskConversationMessage(
                id=msg_id,
                role=role,
                content=str(m.content or ""),
                timestamp=str(m.timestamp or ""),
                metadata=dict(m.metadata or {}),
            )
        )

    thread = DiskConversationThread(
        schema_version=1,
        book_uuid=str(book_uuid),
        book_folder=book_folder,
        conversation_id=str(conversation_id),
        provider=provider,
        model=str(body.model or ""),
        created_at=str(body.created_at or ""),
        last_updated=str(body.last_updated or ""),
        messages=msgs,
    )
    try:
        settings = _server.load_ai_settings()
        save_disk_conversation_multi(
            _server.BOOKS_DIR,
            thread=thread,
            project_conversations_root=_server._project_conversations_root(settings),
            storage_mode=_server._conversation_disk_storage_mode(settings),
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/api/ai/conversations/{book_uuid}/{conversation_id}", status_code=204)
async def api_ai_delete_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = _server.load_ai_settings()
        delete_disk_conversation_multi(
            _server.BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_server._project_conversations_root(settings),
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))
    return None


def _conversation_to_text(thread: dict) -> str:
    lines = []
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        label = "User" if role == "user" else "Assistant"
        content = str(m.get("content") or "").rstrip()
        lines.append(f"{label}: {content}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _conversation_to_markdown(thread: dict) -> str:
    book_uuid = str(thread.get("book_uuid") or "").strip()
    provider = str(thread.get("provider") or "").strip()
    model = str(thread.get("model") or "").strip()
    conv_id = str(thread.get("conversation_id") or "").strip()
    created_at = str(thread.get("created_at") or "").strip()
    last_updated = str(thread.get("last_updated") or "").strip()

    out = [
        "# AI Conversation",
        "",
        f"- book_uuid: `{book_uuid}`",
        f"- conversation_id: `{conv_id}`",
        f"- provider: `{provider}`",
        f"- model: `{model}`",
        f"- created_at: `{created_at}`",
        f"- last_updated: `{last_updated}`",
        "",
        "---",
        "",
    ]
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        title = "User" if role == "user" else "Assistant"
        ts = str(m.get("timestamp") or "").strip()
        content = str(m.get("content") or "").rstrip()
        out.append(f"## {title}")
        if ts:
            out.append(f"- time: `{ts}`")
            out.append("")
        out.append(content or "")
        out.append("")
    return "\n".join(out).strip() + "\n"


@router.get("/api/ai/conversations/{book_uuid}/{conversation_id}/export")
async def api_ai_export_conversation(book_uuid: str, conversation_id: str, format: str = "json"):
    try:
        book_folder = _server.book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:  # noqa: BLE001 - 第 2 档：HTTP 边界，解析不出 book_uuid 即「这本书不存在」→404；类型待收窄为 (KeyError, ValueError)
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = _server.load_ai_settings()
        thread = load_disk_conversation_combined(
            _server.BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_server._project_conversations_root(settings),
        ).to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 400 且 detail 带上原因
        raise HTTPException(status_code=400, detail=str(e))

    fmt = str(format or "json").strip().lower()
    if fmt == "json":
        return thread
    if fmt in ("text", "txt"):
        body = _conversation_to_text(thread)
        return Response(content=body, media_type="text/plain; charset=utf-8")
    if fmt in ("md", "markdown"):
        body = _conversation_to_markdown(thread)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    raise HTTPException(status_code=400, detail="Invalid format (use json|text|md)")

# 017 WI-1（审计 #7）：必须留在文件末尾。理由见 `routers/__init__.py` 的 docstring。
from ... import server as _server  # noqa: E402
