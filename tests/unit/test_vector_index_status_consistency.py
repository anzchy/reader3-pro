"""WI-19b — `status()` 与 `is_indexed()` 必须对同一本书给出同一个答案。

WI-19 收紧了 ``is_indexed()``（meta 缺 ``space`` 键、或 ``model_name`` 与当前
``READER3_EMBED_MODEL`` 不符 → 当作没索引），但 ``status()`` 仍然把磁盘上的 meta
**原样**返回。于是对**每一个存量索引**（都没有 ``space`` 键）出现了两个相反的答案：

* ``GET /api/index/{book_id}/status`` 回 ``"status": "indexed"``；
  ``library.js`` 据此渲染绿色 **"Indexed"** 徽标，后面还跟一个 ``N chunks``；
* 同一本书上 ``semantic_search()`` 每一次都抛 ``not indexed. Run indexing first.``。

验收要求这个降级「提示重新索引」，而现在界面告诉用户的恰好相反——用户没有任何理由
去重新索引，而语义搜索永远失败。命中面是 100% 的存量用户。

**落到哪个前端分支是本文件的核心决定**：``status`` 串取 ``"not_indexed"``。
理由见 ``test_s1``。诊断信息（曾经索引过、为什么失效、原来有多少 chunk）不丢，
放在**新增的附加字段**里；今天的前端会忽略未知键，所以只改 Python 就够。

承重断言：``test_s1_存量索引的状态串与is_indexed一致`` 和
``test_s4_状态串与is_indexed在任何meta下都不打架``。把 ``status()`` 改回「原样返回
磁盘 meta」必须让它们红。

反向哨兵：``test_s3_当前格式的索引仍然原样报indexed`` 和 ``test_s7`` ——
过度修复（连合格的当前索引也不回 ``indexed``）必须红。

Assertion levels（同本 lane 的既有约定，见 tests/unit/conftest.py）:
    L2 返回值，或单个 on-disk 字段
    L3 两个公开方法之间的一致性属性
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from reader3_app import vector_search
from reader3_app.vector_search import BookVectorIndex

BOOK_ID = "consistency_data"
TEST_MODEL = "test-embedder-v1"

#: 前端（library.js:290 起、library-search.js:163 起）只认得这几个串，其余一律落到
#: "unknown"。失效索引必须落在一个**给得出补救动作**的分支上。
FRONTEND_KNOWN_STATUSES = {"indexed", "not_indexed", "indexing", "error"}


@pytest.fixture(autouse=True)
def _cwd_is_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _pinned_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("READER3_EMBED_MODEL", TEST_MODEL)


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - 只为报错好看
        return "<missing>"


_MISSING = _Missing()


def make_index(books_dir: Path) -> BookVectorIndex:
    return BookVectorIndex(BOOK_ID, books_dir=str(books_dir))


def write_meta(idx: BookVectorIndex, **overrides: Any) -> Dict[str, Any]:
    """写一份「当前格式」的 meta，再按 overrides 改写；``_MISSING`` 表示删掉这个键。"""
    meta: Dict[str, Any] = {
        "book_id": BOOK_ID,
        "status": "indexed",
        "chunk_count": 7,
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


# ------------------------------------------------------------- 承重


def test_s1_存量索引的状态串与is_indexed一致(books_dir: Path) -> None:
    """S1（承重）— 存量 meta（没有 ``space`` 键）不许再报 ``"indexed"``。

    为什么取 ``not_indexed`` 而不是新造一个串落到前端的 ``unknown`` 分支：
    ``library-search.js:165`` 只在 ``not_indexed`` 时渲染 **Index 按钮**，
    ``unknown`` 分支渲染的 "Index: unknown" 没有任何补救动作。验收要的是
    「提示重新索引」，只有前者给得出这个动作。「曾经索引过、只是过期了」这条信息
    由下面的附加字段承担，不靠状态串。L2 / S2
    """
    idx = make_index(books_dir)
    write_meta(idx, space=_MISSING)

    st = idx.status()
    assert st["status"] == "not_indexed"
    assert st["status"] in FRONTEND_KNOWN_STATUSES
    assert idx.is_indexed() is False
    assert (st["status"] == "indexed") == idx.is_indexed()


def test_s2_换了模型之后状态串也跟着降级(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S2 — ``model_name`` 不符与缺 ``space`` 是同一种失效。L2 / S2"""
    idx = make_index(books_dir)
    write_meta(idx, model_name="old-model")

    monkeypatch.setenv("READER3_EMBED_MODEL", "new-model")
    st = idx.status()
    assert st["status"] == "not_indexed"
    assert (st["status"] == "indexed") == idx.is_indexed()


def test_s5_失效索引不再报一个会被前端显示的chunk数(books_dir: Path) -> None:
    """S5 — ``library.js`` 拿 ``chunk_count`` 渲染 "N chunks"。

    失效索引报 0；原来的数量挪进诊断字段，信息不丢但不再被当成有效数据。L2 / S2
    """
    idx = make_index(books_dir)
    write_meta(idx, space=_MISSING, chunk_count=4242)

    st = idx.status()
    assert st["chunk_count"] == 0
    assert st.get("indexed_chunk_count") == 4242


def test_s6_失效索引带得出可诊断的原因(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S6 — 「曾经索引过、只是过期了」这条信息不许在降级里丢掉。

    前端今天会忽略未知键，所以这些字段只改 Python 就能加；010/013 那条线
    要把它渲染成「已过期，请重新索引」时不需要再动后端。L2 / S1
    """
    idx = make_index(books_dir)
    write_meta(idx, space=_MISSING)
    st = idx.status()
    assert st.get("stale") is True
    assert st.get("previous_status") == "indexed"
    assert st.get("stale_reason") == "space"

    write_meta(idx, model_name="old-model")
    monkeypatch.setenv("READER3_EMBED_MODEL", "new-model")
    st2 = idx.status()
    assert st2.get("stale") is True
    assert st2.get("stale_reason") == "model_name"


# ------------------------------------------------------------- 反向哨兵


def test_s3_当前格式的索引仍然原样报indexed(books_dir: Path) -> None:
    """S3（反向哨兵）— 过度修复必须在这里红：合格的当前索引一个字段都不许被改写。L3 / S2"""
    idx = make_index(books_dir)
    meta = write_meta(idx, chunk_count=7)

    st = idx.status()
    assert st == meta
    assert st["status"] == "indexed"
    assert st["chunk_count"] == 7
    assert idx.is_indexed() is True
    assert st.get("stale") is None


# ------------------------------------------------------------- 一致性属性


@pytest.mark.parametrize(
    "case,overrides,env_model",
    [
        ("当前格式", {}, TEST_MODEL),
        ("存量_无space键", {"space": _MISSING}, TEST_MODEL),
        ("space值不符", {"space": "l2"}, TEST_MODEL),
        ("换了模型", {"model_name": "old-model"}, "new-model"),
        ("meta说自己没索引完", {"status": "indexing"}, TEST_MODEL),
        ("chunk_count为零", {"chunk_count": 0}, TEST_MODEL),
    ],
)
def test_s4_状态串与is_indexed在任何meta下都不打架(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch,
    case: str, overrides: Dict[str, Any], env_model: str,
) -> None:
    """S4（承重）— 断的是**两个公开方法之间的属性**，不是某个具体串。

    ``status()["status"] == "indexed"`` 与 ``is_indexed()`` 必须永远同真同假：
    前者决定界面上那个绿色徽标，后者决定 ``semantic_search`` 抛不抛。
    界面说「已索引」而搜索说「没索引」是本工作项要消灭的那个矛盾。L3 / S2
    """
    idx = make_index(books_dir)
    write_meta(idx, **overrides)
    monkeypatch.setenv("READER3_EMBED_MODEL", env_model)

    reported = idx.status()["status"]
    assert (reported == "indexed") == idx.is_indexed(), (
        f"{case}: status() 报 {reported!r}，is_indexed() 却是 {idx.is_indexed()}"
    )


def test_s4b_没有meta时两边都说没索引(books_dir: Path) -> None:
    """S4b — 一致性属性在「压根没索引过」这一端的回归保护。L2 / S1"""
    idx = make_index(books_dir)
    assert idx.status()["status"] == "not_indexed"
    assert idx.is_indexed() is False


# ------------------------------------------------------------- 端到端 / 既有降级


class _FakeCollection:
    def __init__(self) -> None:
        self.store: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    def upsert(self, ids=None, documents=None, metadatas=None, **kw: Any) -> None:
        for i, d, m in zip(list(ids or []), list(documents or []), list(metadatas or [])):
            self.store[i] = (d, m)

    def delete(self, ids=None, **kw: Any) -> None:
        for i in list(ids or []):
            self.store.pop(i, None)

    def get(self, **kw: Any) -> Dict[str, Any]:
        held = list(self.store)
        return {"ids": held, "documents": [], "metadatas": []}


class _FakeChapter:
    def __init__(self, title: str, text: str) -> None:
        self.title = title
        self.text = text


class _FakeBook:
    def __init__(self) -> None:
        self.spine = [_FakeChapter("第一章", "甲" * 200)]


class _FakeEmbedFn:
    def __init__(self, model_name: str = "", **kw: Any) -> None:
        self.model_name = model_name


def test_s7_刚建好的索引立刻被status报成indexed(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S7（反向哨兵）— ``index_book()`` 写下的 meta 必须被 ``status()`` 认成 indexed。

    否则「建完索引界面还是 Not indexed」，用户会无限重建。L2 / S2
    """
    monkeypatch.setattr(vector_search, "_require_semantic_deps", lambda: (object(), _FakeEmbedFn))
    idx = make_index(books_dir)
    collection = _FakeCollection()
    monkeypatch.setattr(idx, "_client_and_collection", lambda *a, **kw: (object(), collection))
    monkeypatch.setattr(idx, "_load_book", lambda *a, **kw: _FakeBook())

    meta = idx.index_book()
    st = idx.status()

    assert st["status"] == "indexed"
    assert st["chunk_count"] == meta["chunk_count"] == 1
    assert idx.is_indexed() is True


def test_s8_meta读不出来时仍然是unknown(books_dir: Path) -> None:
    """S8 — 既有降级的回归保护：别在收口一致性的时候把它冲掉。L2 / S1"""
    idx = make_index(books_dir)
    os.makedirs(idx.chroma_path, exist_ok=True)
    with open(idx.meta_path, "w", encoding="utf-8") as f:
        f.write("{ 这不是 json")

    st = idx.status()
    assert st["status"] == "unknown"
    assert idx.is_indexed() is False


def test_s9_没有meta时报的是当前生效的模型名(books_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S9 — ``status()`` 里的模型名跟 ``is_indexed()`` 比对用的是同一个来源。L2 / S1"""
    idx = make_index(books_dir)
    monkeypatch.setenv("READER3_EMBED_MODEL", "another-model")
    assert idx.status()["model_name"] == "another-model"

    monkeypatch.delenv("READER3_EMBED_MODEL", raising=False)
    assert idx.status()["model_name"] == vector_search.MODEL_NAME
