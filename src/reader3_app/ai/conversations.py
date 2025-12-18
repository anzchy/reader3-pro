from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID


CONVERSATIONS_DIRNAME = "ai_conversations"
SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_folder_name(folder_name: str) -> str:
    safe = os.path.basename(folder_name)
    if safe != folder_name:
        raise ValueError("Invalid book folder name")
    return safe


def _safe_conversation_id(conversation_id: str) -> str:
    try:
        return str(UUID(str(conversation_id)))
    except Exception as e:
        raise ValueError("Invalid conversation_id") from e


def _conversations_dir(books_dir: str, book_folder: str) -> str:
    book_folder = _safe_folder_name(book_folder)
    return os.path.join(books_dir, book_folder, CONVERSATIONS_DIRNAME)


def _conversation_path(books_dir: str, book_folder: str, conversation_id: str) -> str:
    cid = _safe_conversation_id(conversation_id)
    return os.path.join(_conversations_dir(books_dir, book_folder), f"{cid}.json")


@dataclass
class ConversationMessage:
    id: str
    role: str
    content: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationThread:
    schema_version: int
    book_uuid: str
    book_folder: str
    conversation_id: str
    provider: str
    model: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    last_updated: str = field(default_factory=_utc_now_iso)
    messages: List[ConversationMessage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "book_uuid": str(self.book_uuid),
            "book_folder": str(self.book_folder),
            "conversation_id": str(self.conversation_id),
            "provider": str(self.provider),
            "model": str(self.model or ""),
            "created_at": str(self.created_at),
            "last_updated": str(self.last_updated),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata or {},
                }
                for m in (self.messages or [])
            ],
        }


def _parse_message(raw: Any) -> Optional[ConversationMessage]:
    if not isinstance(raw, dict):
        return None
    role = str(raw.get("role") or "").strip().lower()
    if role not in ("user", "assistant"):
        return None
    msg_id = str(raw.get("id") or "").strip()
    if not msg_id:
        return None
    content = str(raw.get("content") or "")
    timestamp = str(raw.get("timestamp") or "")
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return ConversationMessage(
        id=msg_id,
        role=role,
        content=content,
        timestamp=timestamp,
        metadata=dict(metadata or {}),
    )


def _parse_thread(raw: Any, *, book_folder: str, default_book_uuid: str, conversation_id: str) -> ConversationThread:
    if not isinstance(raw, dict):
        raw = {}
    messages_raw = raw.get("messages") if isinstance(raw.get("messages"), list) else []
    messages: List[ConversationMessage] = []
    for m in messages_raw:
        parsed = _parse_message(m)
        if parsed:
            messages.append(parsed)
    return ConversationThread(
        schema_version=int(raw.get("schema_version") or SCHEMA_VERSION),
        book_uuid=str(raw.get("book_uuid") or default_book_uuid),
        book_folder=book_folder,
        conversation_id=_safe_conversation_id(str(raw.get("conversation_id") or conversation_id)),
        provider=str(raw.get("provider") or ""),
        model=str(raw.get("model") or ""),
        created_at=str(raw.get("created_at") or _utc_now_iso()),
        last_updated=str(raw.get("last_updated") or _utc_now_iso()),
        messages=messages,
    )


def list_conversations(
    books_dir: str,
    *,
    book_folder: str,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    book_folder = _safe_folder_name(book_folder)
    root = _conversations_dir(books_dir, book_folder)
    if not os.path.isdir(root):
        return []
    out: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(root), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        p = str(data.get("provider") or "").strip().lower()
        if provider and p != provider.strip().lower():
            continue
        msgs = data.get("messages") if isinstance(data.get("messages"), list) else []
        title = ""
        for m in msgs:
            if isinstance(m, dict) and str(m.get("role") or "").strip().lower() == "user":
                title = str(m.get("content") or "").strip().replace("\n", " ")
                break
        title = (title[:60] + "…") if len(title) > 60 else title
        out.append(
            {
                "conversation_id": str(data.get("conversation_id") or name[:-5]),
                "provider": p,
                "model": str(data.get("model") or ""),
                "created_at": str(data.get("created_at") or ""),
                "last_updated": str(data.get("last_updated") or ""),
                "message_count": len(msgs),
                "title": title,
            }
        )
    out.sort(key=lambda x: str(x.get("last_updated") or ""), reverse=True)
    return out


def load_conversation(
    books_dir: str,
    *,
    book_folder: str,
    book_uuid: str,
    conversation_id: str,
) -> ConversationThread:
    book_folder = _safe_folder_name(book_folder)
    path = _conversation_path(books_dir, book_folder, conversation_id)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return _parse_thread(raw, book_folder=book_folder, default_book_uuid=str(book_uuid), conversation_id=conversation_id)


def save_conversation(
    books_dir: str,
    *,
    thread: ConversationThread,
) -> None:
    book_folder = _safe_folder_name(thread.book_folder)
    os.makedirs(_conversations_dir(books_dir, book_folder), exist_ok=True)
    path = _conversation_path(books_dir, book_folder, thread.conversation_id)
    tmp = f"{path}.tmp"
    payload = thread.to_dict()
    payload["schema_version"] = SCHEMA_VERSION
    payload["last_updated"] = _utc_now_iso()
    if not payload.get("created_at"):
        payload["created_at"] = payload["last_updated"]
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def delete_conversation(
    books_dir: str,
    *,
    book_folder: str,
    conversation_id: str,
) -> None:
    book_folder = _safe_folder_name(book_folder)
    path = _conversation_path(books_dir, book_folder, conversation_id)
    try:
        os.remove(path)
    except FileNotFoundError:
        return

