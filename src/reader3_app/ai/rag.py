from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from ..vector_search import BookVectorIndex


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
