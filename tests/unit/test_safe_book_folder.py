"""WI-7 — 服务层的 ``..`` / ``.`` 逃逸：四个模块把未校验的 book 名拼进路径。

宪法第 5 条要求 book id 必须校验。今天只有 ``web/server.py`` 的 ``_validate_book_id``
拿枚举列表兜住了路由层；``ai.books``、``ai.conversations``、``notes_service``、
``vector_search`` 都是可被 CLI、脚本、以及 011 重构后的新调用图直接调用的公开面，
而它们自己这一层是漏的（前两者的 ``os.path.basename(x) == x`` 判据放行 ``.``/``..``/``""``，
后两者一次校验都没有）。

承重断言（T2、T4）断的是**库根之外的磁盘状态逐字节未变**，不是「抛了没」——
一个先写文件再抛 ValueError 的实现必须在这里变红。

Assertion levels (同本 lane 的既有约定, 见 tests/unit/conftest.py):
    L2 返回值，或单个 on-disk 字段
    L3 整棵树的可观察终态
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Tuple

import pytest

from reader3_app import notes_service
from reader3_app.ai import books as ai_books
from reader3_app.ai import conversations as ai_conversations
from reader3_app.models.annotations import Annotation
from reader3_app.vector_search import BookVectorIndex


# ---------------------------------------------------------------- helpers


def tree_bytes(root: Path) -> Dict[str, Tuple[str, bytes | None]]:
    """``{相对路径: (kind, 内容)}``，递归，文件读的是**字节**。

    只比名字不够：``ensure_book_uuid`` 的越权写有可能落在一个已存在的文件上
    （覆盖而非新建），目录列表分毫不动。逐字节比对才断得住「先写后抛」。
    """
    out: Dict[str, Tuple[str, bytes | None]] = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            full = os.path.join(dirpath, name)
            out[os.path.relpath(full, root).replace(os.sep, "/")] = ("dir", None)
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, "rb") as f:
                    out[rel] = ("file", f.read())
            except OSError:
                out[rel] = ("file", b"<unreadable>")
    return out


def diff(before: Dict[str, Tuple[str, bytes | None]], after: Dict[str, Tuple[str, bytes | None]]):
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    return {"added": added, "removed": removed, "changed": changed}


@pytest.fixture
def escape_lab(tmp_path: Path) -> Path:
    """``tmp_path/books`` 是库根；``tmp_path`` 本身就是「库根之外」。

    库根外先放一个有内容的文件，好让「覆盖」和「新建」两种越权都可被断出。
    """
    books = tmp_path / "books"
    books.mkdir()
    (tmp_path / "outside_marker.txt").write_text("do not touch me", encoding="utf-8")
    return books


# ---------------------------------------------------------------- T1 (L2/S1)


REJECTED = ["", ".", "..", "../x", "a/b", "a\\b", "a\x00b"]
ACCEPTED = ["dracula_data", "x", "带中文的书_data"]


@pytest.mark.parametrize("bad", REJECTED)
def test_t1_safe_book_folder_rejects_traversal_values(bad: str) -> None:
    """L2/S1: 逐值拒绝，且消息里带上被拒的值（人要能从日志里看出是哪一个）。"""
    from reader3_app.safe_paths import safe_book_folder

    with pytest.raises(ValueError) as excinfo:
        safe_book_folder(bad)

    assert repr(bad) in str(excinfo.value), (
        f"ValueError 没有带上被拒的值 {bad!r}：{excinfo.value!s}"
    )


@pytest.mark.parametrize("good", ACCEPTED)
def test_t1_safe_book_folder_returns_ordinary_names_unchanged(good: str) -> None:
    """L2/S1: 正常书名原样返回——校验不许顺手改写调用方的 id。"""
    from reader3_app.safe_paths import safe_book_folder

    assert safe_book_folder(good) == good


# ---------------------------------------------------------------- T2 (L3/S2)


@pytest.mark.parametrize("bad", ["..", ".", "../evil"])
def test_t2_ensure_book_uuid_never_writes_outside_the_library_root(
    escape_lab: Path, tmp_path: Path, bad: str
) -> None:
    """L3/S2 **承重**：不只是「抛了」，是根外和根内的磁盘状态逐字节没动。

    T1 只证明 helper 会抛。这条证明调用点真的用上了它，且不是「先写后抛」——
    ``ensure_book_uuid`` 今天对 ``".."`` 会往 ``books/../ai_meta.json`` 落一个
    新 uuid，对 ``"."`` 会往 ``books/ai_meta.json`` 落一个。
    """
    before_outside = tree_bytes(tmp_path)
    before_inside = tree_bytes(escape_lab)

    with pytest.raises(ValueError):
        ai_books.ensure_book_uuid(str(escape_lab), bad)

    after_outside = tree_bytes(tmp_path)
    after_inside = tree_bytes(escape_lab)

    assert after_outside == before_outside, (
        f"库根之外被改动了: {diff(before_outside, after_outside)}"
    )
    assert after_inside == before_inside, (
        f"库根之内被改动了: {diff(before_inside, after_inside)}"
    )


# ---------------------------------------------------------------- T3 (L3/S2)


def _thread(book_folder: str) -> ai_conversations.ConversationThread:
    return ai_conversations.ConversationThread(
        schema_version=1,
        book_uuid="11111111-1111-4111-8111-111111111111",
        book_folder=book_folder,
        conversation_id="22222222-2222-4222-8222-222222222222",
        provider="anthropic",
    )


def test_t3_conversations_dir_refuses_to_escape(escape_lab: Path, tmp_path: Path) -> None:
    """L3/S2: ``_conversations_dir(books, "..")`` 今天返回 ``books/../ai_conversations``。"""
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError):
        ai_conversations._conversations_dir(str(escape_lab), "..")

    assert tree_bytes(tmp_path) == before, "路径解析不该有任何副作用"


def test_t3_save_conversation_refuses_to_escape(escape_lab: Path, tmp_path: Path) -> None:
    """L3/S2: ``save_conversation`` 今天会 mkdir + 落 json 到库根之外。"""
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError):
        ai_conversations.save_conversation(str(escape_lab), thread=_thread(".."))

    after = tree_bytes(tmp_path)
    assert after == before, f"库根之外被改动了: {diff(before, after)}"


def test_t3_delete_conversation_refuses_to_escape(escape_lab: Path, tmp_path: Path) -> None:
    """L3/S2: 删除路径同样要拒——它今天走的是根外的 ``os.remove``。

    根外先摆一个正好同名的会话文件，证明拒绝发生在 ``os.remove`` 之前。
    """
    victim_dir = tmp_path / ai_conversations.CONVERSATIONS_DIRNAME
    victim_dir.mkdir()
    victim = victim_dir / "22222222-2222-4222-8222-222222222222.json"
    victim.write_text(json.dumps({"messages": ["precious"]}), encoding="utf-8")

    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError):
        ai_conversations.delete_conversation(
            str(escape_lab),
            book_folder="..",
            conversation_id="22222222-2222-4222-8222-222222222222",
        )

    after = tree_bytes(tmp_path)
    assert victim.exists(), "库根之外的会话文件被删掉了"
    assert after == before, f"库根之外被改动了: {diff(before, after)}"


# ---------------------------------------------------------------- T4 (L3/S2)


def _annotation(book_id: str, quote: str) -> Annotation:
    return Annotation(book_id=book_id, chapter_index=0, type="marker", quote=quote)


def test_t4_notes_service_refuses_to_read_or_overwrite_outside_the_root(
    escape_lab: Path, tmp_path: Path
) -> None:
    """L3/S2 **承重**：四处里唯一今天完全没有校验的写入路径，写的是不可再生的标注。

    ``_notes_path(books, "..")`` = ``books/../notes.json``。``add_annotation`` 是
    load → append → save 整份文件，所以一次越权写就把根外那份覆盖掉。
    """
    outside_notes = tmp_path / notes_service.NOTES_FILENAME
    payload = {
        "schema_version": notes_service.NOTES_SCHEMA_VERSION,
        "book_id": "someone_elses_data",
        "annotations": [
            _annotation("someone_elses_data", "第一条不可再生的标注").to_dict(),
            _annotation("someone_elses_data", "第二条不可再生的标注").to_dict(),
        ],
    }
    outside_notes.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md5_before = hashlib.md5(outside_notes.read_bytes()).hexdigest()

    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError):
        notes_service.load_annotations(str(escape_lab), "..")

    with pytest.raises(ValueError):
        notes_service.add_annotation(str(escape_lab), _annotation("..", "入侵者"))

    md5_after = hashlib.md5(outside_notes.read_bytes()).hexdigest()
    after = tree_bytes(tmp_path)

    assert md5_after == md5_before, "库根之外的 notes.json 被改写了"
    assert after == before, f"库根之外被改动了: {diff(before, after)}"


# ---------------------------------------------------------------- T5 (L2/S1)


def test_t5_book_vector_index_rejects_at_construction(escape_lab: Path, tmp_path: Path) -> None:
    """L2/S1: 构造时就抛，不是等到 ``index_book`` 才抛。

    ``index_book(force_reindex=True)`` 对 ``chroma_path`` 走 ``shutil.rmtree``；
    ``BookVectorIndex("..", books_dir=books)`` 的 chroma_path 是 ``books/../chroma_db``。
    在构造处拒绝，比在 rmtree 前一行拒绝少一个可绕过的窗口。
    """
    doomed = tmp_path / "chroma_db"
    doomed.mkdir()
    (doomed / "chroma.sqlite3").write_bytes(b"not really a database")

    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError):
        BookVectorIndex("..", books_dir=str(escape_lab))

    after = tree_bytes(tmp_path)
    assert after == before, f"构造函数产生了副作用: {diff(before, after)}"


# ------------------------------------------------- T2/T4 的自证：状态断言必须可达
#
# 上面的 T2、T4 把 `pytest.raises` 放在状态比对之前，所以「守卫被删掉」这种改坏
# 方式红在 DID NOT RAISE 上——状态断言根本没跑到。那样断的是「抛了没」，不是
# WI-7 真正要保的东西。下面两条把异常吞掉，无论抛不抛都比一遍磁盘：删掉
# `safe_book_folder` 的 `..` 分支时，它们红的内容是**库根之外多出了文件**。


def test_t2_disk_state_is_the_assertion_not_the_exception(
    escape_lab: Path, tmp_path: Path
) -> None:
    """L3/S2 承重：``ensure_book_uuid`` 无论如何都不许在库根之外留下痕迹。"""
    before = tree_bytes(tmp_path)

    with contextlib.suppress(ValueError):
        ai_books.ensure_book_uuid(str(escape_lab), "..")

    after = tree_bytes(tmp_path)
    assert after == before, f"库根之外被改动了: {diff(before, after)}"


def test_t4_disk_state_is_the_assertion_not_the_exception(
    escape_lab: Path, tmp_path: Path
) -> None:
    """L3/S2 承重：根外那份 notes.json 的字节必须原封不动。"""
    outside_notes = tmp_path / notes_service.NOTES_FILENAME
    outside_notes.write_text(
        json.dumps(
            {
                "schema_version": notes_service.NOTES_SCHEMA_VERSION,
                "book_id": "someone_elses_data",
                "annotations": [_annotation("someone_elses_data", "不可再生").to_dict()],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    md5_before = hashlib.md5(outside_notes.read_bytes()).hexdigest()
    before = tree_bytes(tmp_path)

    with contextlib.suppress(ValueError):
        notes_service.add_annotation(str(escape_lab), _annotation("..", "入侵者"))

    after = tree_bytes(tmp_path)
    assert hashlib.md5(outside_notes.read_bytes()).hexdigest() == md5_before, (
        "库根之外的 notes.json 被改写了"
    )
    assert after == before, f"库根之外被改动了: {diff(before, after)}"
