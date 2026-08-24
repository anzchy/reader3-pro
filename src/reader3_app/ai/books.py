from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional
from uuid import UUID, uuid4


AI_META_FILENAME = "ai_meta.json"

logger = logging.getLogger("reader3.ai.books")


@dataclass(frozen=True)
class BookIdentity:
    book_uuid: str
    book_folder: str


def _safe_folder_name(folder_name: str) -> str:
    safe = os.path.basename(folder_name)
    if safe != folder_name:
        raise ValueError("Invalid book folder name")
    return safe


def _ai_meta_path(books_dir: str, book_folder: str) -> str:
    return os.path.join(books_dir, book_folder, AI_META_FILENAME)


def _read_ai_meta(path: str) -> Optional[Dict[str, str]]:
    """读 ai_meta.json：不存在返回 None，**读不懂就抛**。

    这两件事以前都返回 None，于是 ensure_book_uuid() 无法分辨「这本书还没有
    uuid」和「这本书的 uuid 我读不出来」，把后者也当成前者去覆盖——用户的 AI
    会话全靠 book_uuid 关联，覆盖一次就永久失联。OSError（权限、坏盘）同理，
    直接冒上去。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object (got {type(data).__name__})")
    out: Dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def ensure_book_uuid(books_dir: str, book_folder: str) -> str:
    book_folder = _safe_folder_name(book_folder)
    meta_path = _ai_meta_path(books_dir, book_folder)
    meta = _read_ai_meta(meta_path) or {}

    raw = (meta.get("book_uuid") or "").strip()
    if raw:
        try:
            return str(UUID(raw))
        except ValueError as e:
            # 第 1 档：读不懂的 book_uuid 不许当成「没有」。旧代码在这里 pass，
            # 于是下面那段生成新 uuid 并覆盖原文件——原值就此消失，用户所有 AI
            # 会话当场失联且救不回来。人还能修一个自己读得到的文件。
            raise ValueError(
                f"{meta_path} holds a book_uuid that is not a UUID ({raw!r}); "
                "refusing to overwrite it -- fix or delete the file"
            ) from e

    new_uuid = str(uuid4())
    meta["book_uuid"] = new_uuid
    os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
    tmp_path = f"{meta_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, meta_path)
    return new_uuid


class BookUuidResolver:
    def __init__(self, books_dir: str) -> None:
        self.books_dir = books_dir
        self._lock = threading.Lock()
        self._uuid_to_folder: Dict[str, str] = {}
        self._folder_to_uuid: Dict[str, str] = {}

    def scan(self) -> None:
        if not os.path.exists(self.books_dir):
            return
        for item in os.listdir(self.books_dir):
            if not item.endswith("_data"):
                continue
            full = os.path.join(self.books_dir, item)
            if not os.path.isdir(full):
                continue
            try:
                self._load_folder(item)
            except (OSError, ValueError) as e:
                # 第 2 档：这个扫描跑在服务启动时。一本书的 ai_meta.json 坏了不该
                # 让整个书库起不来——跳过并留痕。该书的 AI 端点随后 404（明确的
                # 缺失），而不是被悄悄换上一个新 uuid（无声的数据丢失）。
                logger.warning("skipping %s: cannot resolve its book_uuid: %s", item, e)

    def _load_folder(self, book_folder: str) -> None:
        book_folder = _safe_folder_name(book_folder)
        book_uuid = ensure_book_uuid(self.books_dir, book_folder)
        with self._lock:
            self._uuid_to_folder[book_uuid] = book_folder
            self._folder_to_uuid[book_folder] = book_uuid

    def book_uuid_for_folder(self, book_folder: str) -> str:
        book_folder = _safe_folder_name(book_folder)
        with self._lock:
            cached = self._folder_to_uuid.get(book_folder)
        if cached:
            return cached
        self._load_folder(book_folder)
        with self._lock:
            return self._folder_to_uuid[book_folder]

    def folder_for_book_uuid(self, book_uuid: str) -> str:
        normalized = str(UUID(str(book_uuid)))
        with self._lock:
            cached = self._uuid_to_folder.get(normalized)
        if cached:
            return cached
        self.scan()
        with self._lock:
            cached = self._uuid_to_folder.get(normalized)
        if not cached:
            raise KeyError(f"Unknown book_uuid: {normalized}")
        return cached

    def identity_for_folder(self, book_folder: str) -> BookIdentity:
        return BookIdentity(
            book_uuid=self.book_uuid_for_folder(book_folder),
            book_folder=_safe_folder_name(book_folder),
        )

