from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional
from uuid import UUID, uuid4


AI_META_FILENAME = "ai_meta.json"


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
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        out: Dict[str, str] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
        return out
    except FileNotFoundError:
        return None
    except Exception:
        return None


def ensure_book_uuid(books_dir: str, book_folder: str) -> str:
    book_folder = _safe_folder_name(book_folder)
    meta_path = _ai_meta_path(books_dir, book_folder)
    meta = _read_ai_meta(meta_path) or {}

    raw = (meta.get("book_uuid") or "").strip()
    if raw:
        try:
            return str(UUID(raw))
        except Exception:
            pass

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
            self._load_folder(item)

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

