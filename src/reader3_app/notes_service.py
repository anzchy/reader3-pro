from __future__ import annotations

import json
import os
from typing import List

from .models.annotations import Annotation


NOTES_FILENAME = "notes.json"
NOTES_SCHEMA_VERSION = 1


def _notes_path(books_dir: str, book_id: str) -> str:
    return os.path.join(books_dir, book_id, NOTES_FILENAME)


def load_annotations(books_dir: str, book_id: str) -> List[Annotation]:
    path = _notes_path(books_dir, book_id)
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        items = data.get("annotations") or []
        if not isinstance(items, list):
            return []
        out: List[Annotation] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                out.append(Annotation.from_dict(raw))
            except Exception:
                continue
        return out
    except Exception:
        return []


def save_annotations(books_dir: str, book_id: str, annotations: List[Annotation]) -> None:
    path = _notes_path(books_dir, book_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload = {
        "schema_version": NOTES_SCHEMA_VERSION,
        "book_id": book_id,
        "annotations": [a.to_dict() for a in annotations],
    }

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def add_annotation(books_dir: str, annotation: Annotation) -> Annotation:
    annotations = load_annotations(books_dir, annotation.book_id)
    annotations.append(annotation)
    save_annotations(books_dir, annotation.book_id, annotations)
    return annotation


def delete_annotation(books_dir: str, book_id: str, note_id: str) -> bool:
    annotations = load_annotations(books_dir, book_id)
    before = len(annotations)
    annotations = [a for a in annotations if a.id != note_id]
    if len(annotations) == before:
        return False
    save_annotations(books_dir, book_id, annotations)
    return True
