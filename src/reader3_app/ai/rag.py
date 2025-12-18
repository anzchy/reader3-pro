from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from ..vector_search import BookVectorIndex


def _keyword_fallback(
    idx: BookVectorIndex,
    *,
    query: str,
    k: int,
) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    q_lower = q.lower()

    book = idx._load_book()  # type: ignore[attr-defined]
    results: List[Dict[str, Any]] = []
    for chapter_order, chapter in enumerate(getattr(book, "spine", []) or []):
        text = str(getattr(chapter, "text", "") or "")
        if not text:
            continue
        hay = text.lower()
        pos = hay.find(q_lower)
        if pos < 0:
            continue
        start = max(0, pos - 400)
        end = min(len(text), pos + 400)
        snippet = text[start:end].strip()
        title = str(getattr(chapter, "title", "") or f"Section {chapter_order + 1}")
        results.append(
            {
                "chapter_id": str(chapter_order),
                "chapter_order": int(chapter_order),
                "chapter_title": title,
                "text": snippet,
                "similarity": 1.0,
            }
        )
        if len(results) >= k:
            break
    return results


def retrieve_passages(
    book_folder: str,
    *,
    books_dir: str,
    query: str,
    k: int = 5,
    min_similarity: float = 0.5,
) -> Tuple[List[Dict[str, Any]], int]:
    started = time.perf_counter()
    q = (query or "").strip()
    if not q:
        return [], 0

    idx = BookVectorIndex(book_folder, books_dir=books_dir)
    if not idx.is_indexed():
        passages = _keyword_fallback(idx, query=q, k=max(1, min(int(k), 20)))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if passages:
            return passages, elapsed_ms
        raise RuntimeError(
            "This book is not indexed for semantic retrieval yet. "
            "Run /api/index/{book_id} or click the 'Index for semantic' button first."
        )

    k = max(1, min(int(k), 20))
    min_similarity = max(0.0, min(float(min_similarity), 1.0))

    results = idx.semantic_search(q, n_results=k)
    passages: List[Dict[str, Any]] = []
    for r in results:
        if r.similarity_score < min_similarity:
            continue
        passages.append(
            {
                "chapter_id": str(r.chapter_order),
                "chapter_order": int(r.chapter_order),
                "chapter_title": str(r.chapter_title),
                "text": str(r.text),
                "similarity": float(r.similarity_score),
            }
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return passages, elapsed_ms
