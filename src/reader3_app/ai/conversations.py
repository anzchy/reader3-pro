from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID


logger = logging.getLogger("reader3.ai.conversations")

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


def _safe_book_uuid(book_uuid: str) -> str:
    try:
        return str(UUID(str(book_uuid)))
    except Exception as e:
        raise ValueError("Invalid book_uuid") from e


def _conversations_dir(books_dir: str, book_folder: str) -> str:
    book_folder = _safe_folder_name(book_folder)
    return os.path.join(books_dir, book_folder, CONVERSATIONS_DIRNAME)


def _conversation_path(books_dir: str, book_folder: str, conversation_id: str) -> str:
    cid = _safe_conversation_id(conversation_id)
    return os.path.join(_conversations_dir(books_dir, book_folder), f"{cid}.json")


def _project_conversations_dir(project_conversations_root: str, book_uuid: str) -> str:
    root = os.path.abspath(project_conversations_root or "")
    if not root:
        raise ValueError("Invalid project_conversations_root")
    return os.path.join(root, _safe_book_uuid(book_uuid))


def _project_conversation_path(project_conversations_root: str, book_uuid: str, conversation_id: str) -> str:
    cid = _safe_conversation_id(conversation_id)
    return os.path.join(_project_conversations_dir(project_conversations_root, book_uuid), f"{cid}.json")


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


def _list_conversations_from_dir(root: str, *, provider: Optional[str] = None) -> List[Dict[str, Any]]:
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
        except Exception:  # noqa: BLE001 - FIXME(011): 无正当理由——一个坏会话文件从列表里静默消失，用户只会看到历史少了一条，无痕迹可查；至少要收窄到 (OSError, json.JSONDecodeError) 并 log
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


def list_conversations(
    books_dir: str,
    *,
    book_folder: str,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    book_folder = _safe_folder_name(book_folder)
    return _list_conversations_from_dir(_conversations_dir(books_dir, book_folder), provider=provider)


def list_project_conversations(
    project_conversations_root: str,
    *,
    book_uuid: str,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return _list_conversations_from_dir(_project_conversations_dir(project_conversations_root, book_uuid), provider=provider)


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


def load_project_conversation(
    project_conversations_root: str,
    *,
    book_uuid: str,
    book_folder: str,
    conversation_id: str,
) -> ConversationThread:
    book_folder = _safe_folder_name(book_folder)
    path = _project_conversation_path(project_conversations_root, book_uuid, conversation_id)
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


def save_project_conversation(
    project_conversations_root: str,
    *,
    thread: ConversationThread,
) -> None:
    book_uuid = _safe_book_uuid(thread.book_uuid)
    book_folder = _safe_folder_name(thread.book_folder)
    os.makedirs(_project_conversations_dir(project_conversations_root, book_uuid), exist_ok=True)
    path = _project_conversation_path(project_conversations_root, book_uuid, thread.conversation_id)
    tmp = f"{path}.tmp"
    payload = thread.to_dict()
    payload["schema_version"] = SCHEMA_VERSION
    payload["book_uuid"] = book_uuid
    payload["book_folder"] = book_folder
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


def delete_project_conversation(
    project_conversations_root: str,
    *,
    book_uuid: str,
    conversation_id: str,
) -> None:
    path = _project_conversation_path(project_conversations_root, book_uuid, conversation_id)
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def _dedupe_conversation_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for it in items:
        cid = str(it.get("conversation_id") or "").strip()
        if not cid:
            continue
        prev = best.get(cid)
        if not prev:
            best[cid] = it
            continue
        if str(it.get("last_updated") or "") > str(prev.get("last_updated") or ""):
            best[cid] = it
    out = list(best.values())
    out.sort(key=lambda x: str(x.get("last_updated") or ""), reverse=True)
    return out


def list_conversations_combined(
    books_dir: str,
    *,
    book_folder: str,
    book_uuid: str,
    provider: Optional[str] = None,
    project_conversations_root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = list_conversations(books_dir, book_folder=book_folder, provider=provider)
    if project_conversations_root:
        try:
            items.extend(list_project_conversations(project_conversations_root, book_uuid=book_uuid, provider=provider))
        except OSError as e:
            # 第 2 档：project-root 存储读不动（权限、坏盘、被别的进程挪走）时，
            # 返回「只有 per-book 那一半」比整个列表 500 更有用——但必须留痕：
            # 用户看到的是一段凭空消失的历史，运维得有东西可查。
            # 只吞 OSError；book_uuid 不合法这类调用方 bug 由 ValueError 冒上去。
            logger.warning(
                "project-root conversations unavailable for book_uuid=%s under %s: %s; "
                "returning per-book conversations only",
                book_uuid,
                project_conversations_root,
                e,
            )
    return _dedupe_conversation_list(items)


def load_conversation_combined(
    books_dir: str,
    *,
    book_folder: str,
    book_uuid: str,
    conversation_id: str,
    project_conversations_root: Optional[str] = None,
) -> ConversationThread:
    try:
        return load_conversation(
            books_dir,
            book_folder=book_folder,
            book_uuid=book_uuid,
            conversation_id=conversation_id,
        )
    except FileNotFoundError:
        pass
    if project_conversations_root:
        return load_project_conversation(
            project_conversations_root,
            book_uuid=book_uuid,
            book_folder=book_folder,
            conversation_id=conversation_id,
        )
    raise FileNotFoundError(conversation_id)


def save_conversation_multi(
    books_dir: str,
    *,
    thread: ConversationThread,
    project_conversations_root: Optional[str] = None,
    storage_mode: str = "per_book",
) -> None:
    mode = str(storage_mode or "per_book").strip().lower()
    if mode not in ("per_book", "project_root", "both"):
        mode = "per_book"
    if mode in ("per_book", "both"):
        save_conversation(books_dir, thread=thread)
    if project_conversations_root and mode in ("project_root", "both"):
        save_project_conversation(project_conversations_root, thread=thread)


def delete_conversation_multi(
    books_dir: str,
    *,
    book_folder: str,
    book_uuid: str,
    conversation_id: str,
    project_conversations_root: Optional[str] = None,
) -> None:
    delete_conversation(books_dir, book_folder=book_folder, conversation_id=conversation_id)
    if project_conversations_root:
        delete_project_conversation(project_conversations_root, book_uuid=book_uuid, conversation_id=conversation_id)
