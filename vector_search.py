from __future__ import annotations

import json
import os
import pickle
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "reader3_book"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_semantic_deps() -> Tuple[Any, Any]:
    try:
        import chromadb  # type: ignore
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Semantic search dependencies are not installed. "
            "Run: uv add chromadb sentence-transformers"
        ) from e
    return chromadb, SentenceTransformerEmbeddingFunction


class _Reader3Unpickler(pickle.Unpickler):
    _REMAP = {"Book", "BookMetadata", "ChapterContent", "TOCEntry"}

    def find_class(self, module: str, name: str):  # type: ignore[override]
        if module == "__main__" and name in self._REMAP:
            module = "reader3"
        return super().find_class(module, name)


@dataclass
class SemanticSearchResult:
    book_id: str
    chapter_order: int
    chapter_title: str
    chunk_id: str
    chunk_index: int
    chunk_start: int
    chunk_end: int
    text: str
    similarity_score: float


class BookVectorIndex:
    def __init__(self, book_id: str, *, books_dir: str = ".") -> None:
        self.book_id = book_id
        self.books_dir = books_dir
        self.book_dir = os.path.join(books_dir, book_id)
        self.chroma_path = os.path.join(self.book_dir, "chroma_db")
        self.meta_path = os.path.join(self.chroma_path, "index_meta.json")

    def _load_book(self) -> Any:
        pkl_path = os.path.join(self.book_dir, "book.pkl")
        with open(pkl_path, "rb") as f:
            try:
                return _Reader3Unpickler(f).load()
            except Exception:
                f.seek(0)
                return pickle.load(f)

    def _client_and_collection(self):
        chromadb, SentenceTransformerEmbeddingFunction = _require_semantic_deps()
        os.makedirs(self.chroma_path, exist_ok=True)
        model_name = os.environ.get("READER3_EMBED_MODEL", MODEL_NAME)
        embed_fn = SentenceTransformerEmbeddingFunction(model_name=model_name)
        client = chromadb.PersistentClient(path=self.chroma_path)
        try:
            collection = client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)
        except Exception:
            collection = client.create_collection(COLLECTION_NAME, embedding_function=embed_fn)
        return client, collection

    def is_indexed(self) -> bool:
        """
        Fast check that does not require semantic dependencies.

        We treat a book as indexed if `index_meta.json` exists and indicates at
        least one chunk was indexed.
        """
        if not os.path.exists(self.meta_path):
            return False
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("status") != "indexed":
                return False
            chunk_count = meta.get("chunk_count")
            return chunk_count is None or int(chunk_count) > 0
        except Exception:
            # If the meta file exists but is unreadable, assume not indexed.
            return False

    def _chunk_text(self, text: str, *, chunk_size: int = 1000, overlap: int = 120) -> List[Tuple[int, int, str]]:
        if not text:
            return []
        if chunk_size <= overlap:
            overlap = 0
        chunks: List[Tuple[int, int, str]] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(n, start + chunk_size)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append((start, end, chunk))
            if end >= n:
                break
            start = max(end - overlap, start + 1)
        return chunks

    def index_book(self, *, force_reindex: bool = False) -> Dict[str, Any]:
        if force_reindex and os.path.exists(self.chroma_path):
            shutil.rmtree(self.chroma_path, ignore_errors=True)

        _, collection = self._client_and_collection()
        book = self._load_book()

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for chapter_order, chapter in enumerate(getattr(book, "spine", []) or []):
            chapter_text = getattr(chapter, "text", "") or ""
            chapter_title = getattr(chapter, "title", f"Section {chapter_order + 1}")
            for chunk_index, (start, end, chunk) in enumerate(self._chunk_text(chapter_text)):
                chunk_id = f"c{chapter_order}-k{chunk_index}"
                ids.append(chunk_id)
                documents.append(chunk)
                metadatas.append(
                    {
                        "book_id": self.book_id,
                        "chapter_order": chapter_order,
                        "chapter_title": chapter_title,
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "chunk_start": start,
                        "chunk_end": end,
                    }
                )

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        meta = {
            "book_id": self.book_id,
            "status": "indexed",
            "chunk_count": len(ids),
            "model_name": os.environ.get("READER3_EMBED_MODEL", MODEL_NAME),
            "indexed_at": _utc_now_iso(),
        }
        os.makedirs(self.chroma_path, exist_ok=True)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    def status(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.meta_path):
                return {
                    "book_id": self.book_id,
                    "status": "not_indexed",
                    "chunk_count": 0,
                    "model_name": os.environ.get("READER3_EMBED_MODEL", MODEL_NAME),
                }
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "book_id": self.book_id,
                "status": "unknown",
                "chunk_count": None,
                "model_name": os.environ.get("READER3_EMBED_MODEL", MODEL_NAME),
            }

    def semantic_search(self, query: str, *, n_results: int = 10) -> List[SemanticSearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        if not self.is_indexed():
            raise RuntimeError(f"Book {self.book_id} not indexed. Run indexing first.")

        _, collection = self._client_and_collection()
        res = collection.query(query_texts=[query], n_results=n_results, include=["documents", "metadatas", "distances"])
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        out: List[SemanticSearchResult] = []
        for doc, meta, dist in zip(docs, metas, dists):
            similarity = max(0.0, min(1.0, 1.0 - float(dist)))
            out.append(
                SemanticSearchResult(
                    book_id=self.book_id,
                    chapter_order=int(meta.get("chapter_order", 0)),
                    chapter_title=str(meta.get("chapter_title", "")),
                    chunk_id=str(meta.get("chunk_id", "")) or "",
                    chunk_index=int(meta.get("chunk_index", 0)),
                    chunk_start=int(meta.get("chunk_start", 0)),
                    chunk_end=int(meta.get("chunk_end", 0)),
                    text=str(doc or ""),
                    similarity_score=similarity,
                )
            )
        return out
