"""WI-19 — 向量索引会返回指向已不存在文本的结果，且相似度恒为 0。

四个缺陷（`vector_search.BookVectorIndex`）：

* ``A1 ≡ B9`` 不带 ``force_reindex`` 的 ``index_book()`` 只 ``upsert``，从不 ``delete``。
  书变短之后旧的 ``cN-kM`` 还留在 collection 里，``semantic_search`` 会带着
  ``chapter_order``/``chunk_start`` 把它们返回——指向**已经不存在的正文**。
* ``A2`` ``create_collection`` 没设 ``hnsw:space``，Chroma 默认平方 L2 距离；而换算是
  ``max(0.0, min(1.0, 1.0 - dist))``，距离 >1 时每一条 ``similarity_score`` 都被夹到 0。
* ``B10`` ``force_reindex`` 在依赖／模型／``book.pkl`` 都还没验证之前就 ``rmtree``。
* ``B11`` meta 里记了 ``model_name``，但 ``is_indexed`` 不比对。

承重断言：

* V1 断的是 collection **最终持有的 id 集合等于本次生成的集合**，不是「delete 被调过」——
  「调了 delete 但删错 id」必须也红。
* V5 断的是**旧索引目录连同哨兵文件逐字节仍在**，不是抛了什么异常。用
  ``contextlib.suppress`` 而不是 ``pytest.raises``：后者会在断磁盘之前先失败，
  红的内容就变成「异常类型不对」（WI-7／WI-9 的教训）。

离线硬约束：``chromadb`` / ``sentence-transformers`` 是可选依赖。这份测试**不 import
它们**，也不让被测代码 import 成功才跑——``_require_semantic_deps`` 与
``_client_and_collection`` 全部 monkeypatch 掉。

Assertion levels（同本 lane 的既有约定，见 tests/unit/conftest.py）:
    L2 返回值，或单个 on-disk 字段
    L3 整棵树 / 整个 id 集合的可观察终态
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from reader3_app import vector_search
from reader3_app.vector_search import BookVectorIndex

BOOK_ID = "freshness_data"
TEST_MODEL = "test-embedder-v1"


# ---------------------------------------------------------------- 假件


class FakeCollection:
    """记录每一次 ``upsert`` / ``delete`` / ``get`` / ``query`` 的**参数**。

    ``get()`` 返回它自己持有的 id 集合，所以「upsert 之后 collection 里有什么」
    是真实状态，而不是测试替身编出来的。
    """

    def __init__(self) -> None:
        self.store: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        self.upsert_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.query_calls: List[Dict[str, Any]] = []
        self.query_response: Dict[str, Any] = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    # -- chroma 面 ------------------------------------------------
    def upsert(self, ids=None, documents=None, metadatas=None, **kw: Any) -> None:
        ids = list(ids or [])
        documents = list(documents or [])
        metadatas = list(metadatas or [])
        self.upsert_calls.append({"ids": ids, "documents": documents, "metadatas": metadatas, **kw})
        for i, d, m in zip(ids, documents, metadatas):
            self.store[i] = (d, m)

    def delete(self, ids=None, **kw: Any) -> None:
        ids = list(ids or [])
        self.delete_calls.append({"ids": ids, **kw})
        for i in ids:
            self.store.pop(i, None)

    def get(self, **kw: Any) -> Dict[str, Any]:
        self.get_calls.append(dict(kw))
        held = list(self.store.keys())
        return {
            "ids": held,
            "documents": [self.store[i][0] for i in held],
            "metadatas": [self.store[i][1] for i in held],
        }

    def query(self, **kw: Any) -> Dict[str, Any]:
        self.query_calls.append(dict(kw))
        return self.query_response

    # -- 测试面 ---------------------------------------------------
    @property
    def ids(self) -> set:
        return set(self.store)


class FakeClient:
    def __init__(self, path: str = "") -> None:
        self.path = path
        self.get_collection_calls: List[Dict[str, Any]] = []
        self.create_collection_calls: List[Dict[str, Any]] = []
        self.collection = FakeCollection()
        self.existing: set = set()

    def get_collection(self, name, **kw: Any):
        self.get_collection_calls.append({"name": name, **kw})
        if name not in self.existing:
            raise ValueError(f"Collection {name} does not exist.")
        return self.collection

    def create_collection(self, name, **kw: Any):
        self.create_collection_calls.append({"name": name, **kw})
        self.existing.add(name)
        return self.collection


class FakeChapter:
    def __init__(self, title: str, text: str) -> None:
        self.title = title
        self.text = text


class FakeBook:
    def __init__(self, chapters: List[Tuple[str, str]]) -> None:
        self.spine = [FakeChapter(t, x) for t, x in chapters]


# ---------------------------------------------------------------- 夹具


@pytest.fixture(autouse=True)
def _cwd_is_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """任何可能落到相对路径的写入都留在 tmp_path 里，绝不碰真实 books/。"""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _pinned_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("READER3_EMBED_MODEL", TEST_MODEL)


class _FakeEmbedFn:
    instances: List[str] = []

    def __init__(self, model_name: str = "", **kw: Any) -> None:
        self.model_name = model_name
        _FakeEmbedFn.instances.append(model_name)


@pytest.fixture(autouse=True)
def _no_real_semantic_deps(monkeypatch: pytest.MonkeyPatch):
    """默认把 ``_require_semantic_deps`` 换成假件：不 import chromadb，不加载模型。

    需要测「依赖缺失」的用例自己再 monkeypatch 成抛错。
    """

    class _FakeChromadb:
        last_client: Optional[FakeClient] = None

        @staticmethod
        def PersistentClient(path: str = "", **kw: Any) -> FakeClient:  # noqa: N802
            _FakeChromadb.last_client = FakeClient(path)
            return _FakeChromadb.last_client

    monkeypatch.setattr(vector_search, "_require_semantic_deps", lambda: (_FakeChromadb, _FakeEmbedFn))
    return _FakeChromadb


def make_index(books_dir: Path, collection: Optional[FakeCollection], book: Optional[FakeBook],
               monkeypatch: pytest.MonkeyPatch) -> BookVectorIndex:
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))
    if collection is not None:
        client = FakeClient(idx.chroma_path)
        monkeypatch.setattr(idx, "_client_and_collection", lambda *a, **kw: (client, collection))
    if book is not None:
        monkeypatch.setattr(idx, "_load_book", lambda *a, **kw: book)
    return idx


def write_meta(idx: BookVectorIndex, **overrides: Any) -> Dict[str, Any]:
    meta = {
        "book_id": BOOK_ID,
        "status": "indexed",
        "chunk_count": 3,
        "model_name": TEST_MODEL,
        "space": "cosine",
        "indexed_at": "2026-01-01T00:00:00+00:00",
    }
    meta.update(overrides)
    for key in [k for k, v in overrides.items() if v is _MISSING]:
        meta.pop(key, None)
    os.makedirs(idx.chroma_path, exist_ok=True)
    with open(idx.meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return meta


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - 只为报错好看
        return "<missing>"


_MISSING = _Missing()


# ---------------------------------------------------------------- V1 / V2 / V3


def test_v1_书变短之后旧chunk不再出现在检索结果里(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V1（承重）— 第二次索引之后，collection 持有的 id 集合 == 本次生成的集合。

    断集合相等，不断 ``delete`` 的调用次数：那是接线断言，而且没有陈旧 chunk 时
    一次不调也是对的。「调了 delete 但删错 id」必须在这里红。
    L3 / S2
    """
    collection = FakeCollection()
    long_book = FakeBook([("第一章", "甲" * 200), ("第二章", "乙" * 200), ("第三章", "丙" * 200)])
    idx = make_index(books_dir, collection, long_book, monkeypatch)
    idx.index_book()
    assert collection.ids == {"c0-k0", "c1-k0", "c2-k0"}, "前置：三章各落一个 chunk"

    short_book = FakeBook([("第一章", "甲" * 200)])
    idx2 = make_index(books_dir, collection, short_book, monkeypatch)
    idx2.index_book()

    assert collection.ids == {"c0-k0"}
    assert "c2-k0" not in collection.ids
    assert "c1-k0" not in collection.ids


def test_v2_chunk_count记的是删完之后的真实数量(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V2 — 两边都断，``chunk_count`` 才不能靠「碰巧等于本次生成数」蒙混。L3 / S2"""
    collection = FakeCollection()
    long_book = FakeBook([("第一章", "甲" * 200), ("第二章", "乙" * 200), ("第三章", "丙" * 200)])
    make_index(books_dir, collection, long_book, monkeypatch).index_book()

    short_book = FakeBook([("第一章", "甲" * 200)])
    meta = make_index(books_dir, collection, short_book, monkeypatch).index_book()

    assert meta["chunk_count"] == len(collection.ids)
    assert meta["chunk_count"] == 1


def test_v3_新旧id完全不相交时也不留残渣(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V3 — 章节文本改写后 chunk 边界变化，新旧 id 前缀不同。L2 / S1"""
    collection = FakeCollection()
    first = FakeBook([("第一章", "甲" * 1500), ("第二章", "")])
    make_index(books_dir, collection, first, monkeypatch).index_book()
    old_ids = set(collection.ids)
    assert old_ids == {"c0-k0", "c0-k1"}, "前置：1500 字落两个 chunk"

    second = FakeBook([("第一章", ""), ("第二章", "乙" * 200)])
    make_index(books_dir, collection, second, monkeypatch).index_book()

    assert collection.ids == {"c1-k0"}
    assert collection.ids & old_ids == set()


# ---------------------------------------------------------------- V4


def _search_with_distances(books_dir: Path, monkeypatch: pytest.MonkeyPatch,
                           distances: List[float]) -> List[Any]:
    collection = FakeCollection()
    n = len(distances)
    collection.query_response = {
        "documents": [[f"段落 {i}" for i in range(n)]],
        "metadatas": [[
            {
                "book_id": BOOK_ID,
                "chapter_order": i,
                "chapter_title": f"第{i}章",
                "chunk_id": f"c{i}-k0",
                "chunk_index": 0,
                "chunk_start": 0,
                "chunk_end": 10,
            }
            for i in range(n)
        ]],
        "distances": [list(distances)],
    }
    idx = make_index(books_dir, collection, None, monkeypatch)
    write_meta(idx)
    return idx.semantic_search("查询词")


def test_v4_相似度有区分度且不被夹成零(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V4 — cosine 口径的 0.05 / 0.5 / 0.95 必须换算成严格递减且都不为 0 的分数。

    断严格递减而非具体数值：换算公式将来可能微调，「有区分度」才是性质。
    但必须同时断不为 0，finding 说的正是「全被夹到 0」。L3 / S2
    """
    results = _search_with_distances(books_dir, monkeypatch, [0.05, 0.5, 0.95])
    scores = [r.similarity_score for r in results]

    assert len(scores) == 3
    assert scores[0] > scores[1] > scores[2]
    assert all(s != 0.0 for s in scores), f"距离换算把结果夹成 0：{scores}"


def test_v4b_距离大于一时相似度依然有区分度(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V4b（补充）— cosine 距离可以 >1（向量方向相反）。

    ``1.0 - dist`` 会把这一整段全部夹成 0.0，正是 finding 描述的失效方式。L3 / S2
    """
    results = _search_with_distances(books_dir, monkeypatch, [1.2, 1.5, 1.8])
    scores = [r.similarity_score for r in results]

    assert len(scores) == 3
    assert scores[0] > scores[1] > scores[2]
    assert all(s != 0.0 for s in scores), f"距离 >1 的结果被夹到 0：{scores}"


def test_v4_接线_建集合时声明cosine空间(books_dir: Path, monkeypatch: pytest.MonkeyPatch,
                                        _no_real_semantic_deps) -> None:
    """V4 的接线补充（不单独成 case 级别）：``create_collection`` 收到 hnsw:space=cosine。"""
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))
    idx._client_and_collection()

    client = _no_real_semantic_deps.last_client
    assert client is not None and client.create_collection_calls, "应当建了集合"
    metadata = client.create_collection_calls[0].get("metadata") or {}
    assert metadata.get("hnsw:space") == "cosine"


# ---------------------------------------------------------------- V5


@pytest.mark.parametrize("failing_step", ["deps", "book"])
def test_v5_前置校验失败时旧索引原封不动(books_dir: Path, monkeypatch: pytest.MonkeyPatch,
                                        failing_step: str) -> None:
    """V5（承重）— ``force_reindex`` 在验证通过之前不许删掉可用索引。

    无条件断磁盘状态，不用 ``pytest.raises``。L3 / S2
    """
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))
    os.makedirs(idx.chroma_path, exist_ok=True)
    sentinel = Path(idx.chroma_path) / "chroma.sqlite3"
    sentinel.write_bytes(b"\x00OLD-INDEX-PAYLOAD\x01")
    write_meta(idx, chunk_count=7)
    before_sentinel = sentinel.read_bytes()
    before_meta = Path(idx.meta_path).read_bytes()

    def _boom(*a: Any, **kw: Any):
        raise RuntimeError("前置校验失败")

    if failing_step == "deps":
        monkeypatch.setattr(vector_search, "_require_semantic_deps", _boom)
    else:
        monkeypatch.setattr(idx, "_load_book", _boom)

    with contextlib.suppress(Exception):
        idx.index_book(force_reindex=True)

    assert os.path.isdir(idx.chroma_path), "旧索引目录被删了"
    assert sentinel.exists(), "旧索引的数据文件被删了"
    assert sentinel.read_bytes() == before_sentinel
    assert Path(idx.meta_path).read_bytes() == before_meta


# ---------------------------------------------------------------- V6 / V7


def test_v6_换了嵌入模型之后旧索引被判为未索引(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V6 — 用新模型的 query 向量去查旧模型的 embedding，维度都可能不同。L2 / S1"""
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))
    write_meta(idx, model_name="old-model")

    monkeypatch.setenv("READER3_EMBED_MODEL", "new-model")
    assert idx.is_indexed() is False

    monkeypatch.setenv("READER3_EMBED_MODEL", "old-model")
    assert idx.is_indexed() is True


def test_v7_旧格式的meta没有space键被判为未索引(books_dir: Path) -> None:
    """V7 — 重新索引可完全恢复，所以这里退回「当作没索引」是可接受的降级。L2 / S1"""
    idx = BookVectorIndex(BOOK_ID, books_dir=str(books_dir))
    write_meta(idx, space=_MISSING)
    assert idx.is_indexed() is False

    write_meta(idx, space="cosine")
    assert idx.is_indexed() is True


def test_v7b_index_book写下的meta自己就带space(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V7 的回归保护：新写的索引必须能被新的 ``is_indexed`` 认出来。L2 / S1"""
    collection = FakeCollection()
    idx = make_index(books_dir, collection, FakeBook([("第一章", "甲" * 200)]), monkeypatch)
    meta = idx.index_book()

    assert meta["space"] == "cosine"
    assert idx.is_indexed() is True
