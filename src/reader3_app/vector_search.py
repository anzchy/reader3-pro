from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .safe_paths import safe_book_folder
from .safe_pickle import load_book_file

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "reader3_book"

#: 距离度量。Chroma 的默认是平方 L2，距离可以远大于 1，而下面的换算要把距离映射到
#: [0, 1] 的相似度——L2 之下每一条结果都会被夹到 0.0，similarity_score 对排序和阈值
#: 双双失效。显式声明 cosine，距离才有上界（[0, 2]）。
SPACE = "cosine"
#: cosine 距离的上界。similarity = 1 - dist / DISTANCE_CEILING。
DISTANCE_CEILING = 2.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_model_name() -> str:
    return os.environ.get("READER3_EMBED_MODEL", MODEL_NAME)


#: 补救动作的唯一写法。文案必须指向 **extra**，不是 `uv add chromadb sentence-transformers`
#: 也不是 `pip install sentence_transformers`：那两种都会把包装回主依赖（或装在 extra 之外），
#: 照做的人修好了语义搜索，同时无声撤销了「语义依赖可选」这件事（011 WI-7）。
_EXTRA_HINT = (
    "Install the optional extra: `uv sync --extra semantic` "
    "(or `pip install 'reader3[semantic]'`)."
)


def _require_semantic_deps() -> Tuple[Any, Any]:
    try:
        import chromadb  # type: ignore
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # type: ignore
    except Exception as e:  # noqa: BLE001 - 第 2 档：唯一的 import 点，把任何 import 期故障统一转译成调用方（路由 / CLI）认得的 RuntimeError；原因留在 __cause__ 里
        raise RuntimeError("Semantic search dependencies are not installed. " + _EXTRA_HINT) from e
    return chromadb, SentenceTransformerEmbeddingFunction


def _build_embedding_function(factory: Any) -> Any:
    """构造嵌入函数，并把「依赖不全」在这里转译成 RuntimeError。

    017 WI-14（审计 #25）：`_require_semantic_deps()` **不是**唯一的依赖检查点，尽管本文件
    此前是这么被描述的。`chromadb` 装了而 `sentence-transformers` 没装时，那个函数一路通过
    ——`SentenceTransformerEmbeddingFunction` 只是个类对象，import 它不需要底层包——真正的
    失败推迟到**构造**这一刻，而 chromadb 在那里抛的是 `ValueError`：

        ValueError: The sentence_transformers python package is not installed.
                    Please install it with `pip install sentence_transformers`

    两个调用方都接不住它：CLI（`reader3.main` 的 `except RuntimeError`）漏成一屏裸
    traceback，HTTP（`routers/search.py`）落到兜底的 `except Exception` 给 500——而缺一个
    可选依赖不是服务端故障，前端据此没法把它渲染成「可补救」。半装状态不是臆造的：
    `uv sync --extra semantic` 装到一半被打断、或有人手工 `pip uninstall sentence-transformers`
    就是它。

    捕获收得很窄（`ImportError` / `ValueError`），不是 `Exception`：模型名写错、权重下载失败
    是**别的**毛病，把它们也说成「依赖没装」会把人指向错误的修法。它们照常往上抛。

    chromadb 那句 `pip install sentence_transformers` 刻意**不**转给用户：它把包装在 extra
    之外，正是 `_EXTRA_HINT` 存在要防的那件事。原文留在 `__cause__` 里，开发者查得到。
    """
    try:
        return factory(model_name=_current_model_name())
    except (ImportError, ValueError) as e:
        raise RuntimeError(
            "Semantic search dependencies are incomplete: the embedding model could not be "
            "initialised. " + _EXTRA_HINT
        ) from e


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
        # 在构造处拒绝，而不是在 rmtree 前一行：index_book(force_reindex=True)
        # 对 self.chroma_path 走 shutil.rmtree，而 BookVectorIndex("..") 的
        # chroma_path 是 books/../chroma_db。少一个可绕过的窗口。
        book_id = safe_book_folder(book_id)
        self.book_id = book_id
        self.books_dir = books_dir
        self.book_dir = os.path.join(books_dir, book_id)
        self.chroma_path = os.path.join(self.book_dir, "chroma_db")
        self.meta_path = os.path.join(self.chroma_path, "index_meta.json")

    def _load_book(self) -> Any:
        # No fallback loader: see safe_pickle. An unreadable book.pkl raises.
        return load_book_file(os.path.join(self.book_dir, "book.pkl"))

    def _prepare_deps(self):
        """依赖 + 嵌入模型，**不碰磁盘**。

        单独拆出来是为了让 ``index_book(force_reindex=True)`` 能在删掉可用索引之前
        先把「依赖装了没、模型加载得起来没」验完：``_client_and_collection`` 会
        ``os.makedirs`` 并建集合，在 rmtree 之前跑它会让集合句柄指向一个随后被删掉的目录。
        """
        chromadb, SentenceTransformerEmbeddingFunction = _require_semantic_deps()
        embed_fn = _build_embedding_function(SentenceTransformerEmbeddingFunction)
        deps = (chromadb, embed_fn)
        self._deps = deps
        return deps

    def _client_and_collection(self):
        chromadb, embed_fn = getattr(self, "_deps", None) or self._prepare_deps()
        os.makedirs(self.chroma_path, exist_ok=True)
        client = chromadb.PersistentClient(path=self.chroma_path)
        try:
            collection = client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)
        except Exception:  # noqa: BLE001 - 第 3 档：chromadb 在集合不存在时抛的类型跨版本不稳定，这里只能宽捕获后建集合；建失败会照常抛
            collection = client.create_collection(
                COLLECTION_NAME,
                embedding_function=embed_fn,
                metadata={"hnsw:space": SPACE},
            )
        return client, collection

    def _existing_chunk_ids(self, collection) -> Optional[set]:
        """collection 当前持有的 id 集合；读不出来时返回 None（调用方据此保守处理）。"""
        try:
            got = collection.get(include=[])
        except Exception:  # noqa: BLE001 - 第 3 档：拿不到现有 id 就不做删除，宁可留下陈旧 chunk 也不误删；下一次索引还有机会
            return None
        if not isinstance(got, dict):
            return None
        ids = got.get("ids")
        if ids is None:
            return None
        return set(ids)

    @staticmethod
    def _stale_reason(meta: Dict[str, Any]) -> Optional[str]:
        """meta 描述的索引为什么不能用；``None`` 表示可用。

        `is_indexed()` 和 `status()` 都只走这一个判据。两处各判各的，就会出现
        界面报「已索引 N chunks」而 `semantic_search` 同时抛「not indexed」的
        矛盾——那正是这个函数存在的理由。
        """
        if meta.get("status") != "indexed":
            return "status"
        # 距离度量不符（含旧格式：根本没有 space 键）就当作没索引。换了嵌入模型
        # 同理——用新模型的 query 向量去查旧模型的 embedding，维度都可能不同。
        # 这是可完全恢复的降级：重新索引不丢任何用户数据。
        if meta.get("space") != SPACE:
            return "space"
        if str(meta.get("model_name") or "") != _current_model_name():
            return "model_name"
        chunk_count = meta.get("chunk_count")
        if chunk_count is not None and int(chunk_count) <= 0:
            return "empty"
        return None

    def _read_meta(self) -> Optional[Dict[str, Any]]:
        """磁盘上的 meta；文件不存在或读不出来都返回 ``None``。"""
        if not os.path.exists(self.meta_path):
            return None
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:  # noqa: BLE001 - 第 3 档：index_meta.json 读不出来就当作没索引，重新索引可完全恢复，不丢用户数据
            return None
        return meta if isinstance(meta, dict) else None

    def is_indexed(self) -> bool:
        """
        Fast check that does not require semantic dependencies.

        We treat a book as indexed if `index_meta.json` exists, is readable, and
        describes an index the *current* code and model can actually query.
        """
        meta = self._read_meta()
        if meta is None:
            return False
        return self._stale_reason(meta) is None

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
        # 先验证，再销毁。依赖、模型、book.pkl 任何一步失败时，force_reindex 之前
        # 那个可用的索引必须原封不动——否则用户既没有新索引也没有旧索引。
        self._prepare_deps()
        book = self._load_book()

        if force_reindex and os.path.exists(self.chroma_path):
            shutil.rmtree(self.chroma_path, ignore_errors=True)

        _, collection = self._client_and_collection()

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

        # 书变短、章节被删、chunk 边界移动之后，上一次索引留下的 id 还在 collection 里，
        # 检索会带着 chapter_order/chunk_start 把它们返回——指向已经不存在的正文。
        # upsert 覆盖不掉这些，只有显式 delete 差集才行。
        existing = self._existing_chunk_ids(collection)
        if existing is not None:
            stale = sorted(existing - set(ids))
            if stale:
                collection.delete(ids=stale)

        # chunk_count 记的是删完之后 collection 真实持有的数量，不是本次生成的数量：
        # 差集删除失败（或压根没删成）时，元数据不该替它掩盖。
        remaining = self._existing_chunk_ids(collection)
        chunk_count = len(remaining) if remaining is not None else len(ids)

        meta = {
            "book_id": self.book_id,
            "status": "indexed",
            "chunk_count": chunk_count,
            "model_name": _current_model_name(),
            "space": SPACE,
            "indexed_at": _utc_now_iso(),
        }
        os.makedirs(self.chroma_path, exist_ok=True)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    def status(self) -> Dict[str, Any]:
        if not os.path.exists(self.meta_path):
            return {
                "book_id": self.book_id,
                "status": "not_indexed",
                "chunk_count": 0,
                "model_name": _current_model_name(),
            }
        meta = self._read_meta()
        if meta is None:
            return {
                "book_id": self.book_id,
                "status": "unknown",
                "chunk_count": None,
                "model_name": _current_model_name(),
            }

        reason = self._stale_reason(meta)
        if reason is None or reason == "status":
            # 合格的当前索引原样透传；meta 自己说 status != "indexed"（indexing /
            # error / 半路中断）时也原样透传——那是索引流程自己的状态，不是失效。
            return meta

        # 失效索引：报 "not_indexed"。前端（library.js:290 起、library-search.js:163 起）
        # 只在这个分支渲染 Index 按钮，而 "unknown" 分支给不出任何补救动作；验收要的是
        # 「提示重新索引」。"曾经索引过、只是过期了" 由下面的附加字段承担，前端会忽略
        # 未知键，所以这里只改 Python 就够。
        stale = dict(meta)
        stale["status"] = "not_indexed"
        # chunk_count 会被前端渲染成 "N chunks"，失效索引不该再报一个有效数量。
        stale["chunk_count"] = 0
        stale["stale"] = True
        stale["stale_reason"] = reason
        stale["previous_status"] = meta.get("status")
        stale["indexed_chunk_count"] = meta.get("chunk_count")
        stale["indexed_model_name"] = meta.get("model_name")
        stale["model_name"] = _current_model_name()
        return stale

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
            # cosine 距离的值域是 [0, 2]，除以上界才不会把 dist > 1 的一整段夹到 0。
            similarity = max(0.0, min(1.0, 1.0 - float(dist) / DISTANCE_CEILING))
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
