"""017 WI-3（审计 #6）——**旧记录不许让 ETag 每读一次就变一次**。

`Annotation.from_dict` 是磁盘那一侧**唯一**的反序列化入口（`notes_service.load_annotations`
是它唯一的调用者）。它对两个字段做了「缺了就现编一个」的兜底：

    id=str(data.get("id") or str(uuid4()))
    created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat())

而 `notes_service.annotations_version()`（＝ 对外的 ETag）哈希的是**每条记录 `to_dict()`
之后的规范 JSON**，这两个字段都在里面。于是一条 `notes.json` 里缺 `created_at` 或缺 `id`
的旧记录会让 ETag **每次 load 都不一样**：

    GET  /api/notes/… → ETag: X        （这次 load 现编了一个时间戳）
    PUT  … If-Match: X                 （客户端原样送回 X）
      ↳ 写锁里重新 load → 版本算成 Y ≠ X → 409

客户端拿着 409 里带回来的「当前版本」重试，下一次 load 又现编一个新的——**它永远追不上**。
这本书从此写不进任何东西，而界面上只看得到一个反复弹出的冲突对话框。

本文件先把这条死循环钉成断言，再要求 `from_dict` 在**哈希之前**把旧记录规范化成确定值：

* `created_at` 缺失 → `""`。这是一句老实话：我们不知道它是什么时候建的，就不要现编一个
  「刚刚」。它只被用作排序的次级键（`routers/notes.py:125`、`:186`），`""` 排最前，
  代价是已知且有界的；`web/server.py:921` 早就在用同一个值。
* `id` 缺失 → 对「**序号 ＋ 本条记录的规范 JSON**」取 `uuid5`。只取内容是不够的：两条
  逐字节相同的无 id 记录会塌成同一个 id，而 `delete_annotation_and_version` 是按
  `a.id != note_id` 过滤的——删一条会把两条一起删掉。序号把它们分开。

**已有值一个字节都不许动**（L4/L5）：规范化只填空，不重写。写新标注的路径走的是
`Annotation(...)` 构造器（`routers/notes.py:265`），它的 `default_factory` 逐字不变
（L6）——本次改动只落在「从磁盘读回来」这一侧。

断言级别：
    L2  单个可观测值（一次 load 的 ETag、一个字段的字面量）
    L3  一串操作之后的终态（两次 load 的 ETag 相等；一次条件写的结局）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from reader3_app import notes_service
from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import NOTES_FILENAME, NOTES_SCHEMA_VERSION

BOOK_ID = "legacy_notes_data"

#: 一条**完整**的旧记录。各条用例从它身上删字段，删哪个就测哪个。
BASE_RECORD: Dict[str, Any] = {
    "id": "11111111-2222-3333-4444-555555555555",
    "book_id": BOOK_ID,
    "chapter_index": 0,
    "type": "marker",
    "color": "yellow",
    "quote": "LEGACY-QUOTE-SENTINEL",
    "prefix": "",
    "suffix": "",
    "position": 10,
    "cfi": None,
    "note_text": "旧记录的正文",
    "created_at": "2024-01-02T03:04:05+00:00",
    "orphaned": False,
}


def _write_notes(books_dir: Path, records: List[Dict[str, Any]]) -> Path:
    """把 `records` 逐字写进 notes.json —— 故意绕开 `save_annotations`。

    `save_annotations` 写的是 `to_dict()`，字段一个不缺，永远造不出本文件要测的那种
    旧记录。要复现「盘上就是缺字段」，只能自己拼 JSON。
    """
    folder = books_dir / BOOK_ID
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / NOTES_FILENAME
    path.write_text(
        json.dumps(
            {"schema_version": NOTES_SCHEMA_VERSION, "annotations": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _record_without(field: str) -> Dict[str, Any]:
    rec = dict(BASE_RECORD)
    rec.pop(field)
    return rec


def _version(books_dir: Path) -> str:
    return notes_service.annotations_version(
        notes_service.load_annotations(str(books_dir), BOOK_ID)
    )


# ---------------------------------------------------------------------------
# L1 / L3 —— 缺 created_at
# ---------------------------------------------------------------------------


def test_L1_缺created_at的记录反复读出来的版本号必须一致(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("created_at")])

    versions = {_version(tmp_path) for _ in range(5)}

    assert len(versions) == 1, (
        "缺 created_at 的旧记录每次 load 都算出不同的 ETag："
        f"5 次读出了 {len(versions)} 个版本 {sorted(versions)}。"
        "客户端送回来的 If-Match 永远对不上，这本书从此写不进去。"
    )


def test_L2_缺created_at时补出来的值是空串而不是现在的时间(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("created_at")])

    (ann,) = notes_service.load_annotations(str(tmp_path), BOOK_ID)

    assert ann.created_at == "", (
        f"缺 created_at 应补成空串（「不知道」），实得 {ann.created_at!r}。"
        "补一个「刚刚」既不真实，也不确定。"
    )


def test_L3_带着刚读到的版本去条件更新缺created_at的记录必须写得进去(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("created_at")])

    # 这就是一次真实的 GET → PUT：客户端拿到的 ETag，原样作为 If-Match 送回来。
    etag = _version(tmp_path)

    updated, _new_version = notes_service.update_annotation_and_version(
        str(tmp_path),
        BOOK_ID,
        BASE_RECORD["id"],
        "客户端写进来的新正文",
        if_match=etag,
    )

    assert updated is not None, "条件更新没找到目标记录"
    assert updated.note_text == "客户端写进来的新正文"

    (on_disk,) = notes_service.load_annotations(str(tmp_path), BOOK_ID)
    assert on_disk.note_text == "客户端写进来的新正文", "写成功了但盘上不是新正文"


# ---------------------------------------------------------------------------
# L1' / L3' —— 缺 id
# ---------------------------------------------------------------------------


def test_L4_缺id的记录反复读出来的版本号必须一致(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("id")])

    versions = {_version(tmp_path) for _ in range(5)}

    assert len(versions) == 1, (
        f"缺 id 的旧记录 5 次读出了 {len(versions)} 个版本 {sorted(versions)}"
    )


def test_L5_缺id的记录反复读出来的id也必须一致(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("id")])

    ids = {notes_service.load_annotations(str(tmp_path), BOOK_ID)[0].id for _ in range(5)}

    assert len(ids) == 1, f"同一条无 id 记录读出了 {len(ids)} 个不同的 id：{sorted(ids)}"


def test_L6_带着刚读到的版本去条件更新缺id的记录必须写得进去(tmp_path: Path) -> None:
    _write_notes(tmp_path, [_record_without("id")])

    loaded = notes_service.load_annotations(str(tmp_path), BOOK_ID)
    note_id = loaded[0].id
    etag = notes_service.annotations_version(loaded)

    updated, _new_version = notes_service.update_annotation_and_version(
        str(tmp_path), BOOK_ID, note_id, "补了 id 之后写进来的正文", if_match=etag
    )

    assert updated is not None, "条件更新没找到目标记录——补出来的 id 两次 load 之间变了"
    (on_disk,) = notes_service.load_annotations(str(tmp_path), BOOK_ID)
    assert on_disk.note_text == "补了 id 之后写进来的正文"


def test_L7_两条逐字节相同的无id记录不许塌成同一个id(tmp_path: Path) -> None:
    twin = _record_without("id")
    _write_notes(tmp_path, [dict(twin), dict(twin)])

    a, b = notes_service.load_annotations(str(tmp_path), BOOK_ID)

    assert a.id != b.id, (
        f"两条无 id 记录被补成了同一个 id {a.id!r}；"
        "delete_annotation_and_version 按 id 过滤，删一条会把两条一起删掉。"
    )


# ---------------------------------------------------------------------------
# 护栏：规范化只填空，不重写
# ---------------------------------------------------------------------------


def test_L8_已有的created_at与id一个字节都不许动(tmp_path: Path) -> None:
    _write_notes(tmp_path, [dict(BASE_RECORD)])

    (ann,) = notes_service.load_annotations(str(tmp_path), BOOK_ID)

    assert ann.created_at == BASE_RECORD["created_at"]
    assert ann.id == BASE_RECORD["id"]


def test_L9_新建标注的构造器行为逐字不变(tmp_path: Path) -> None:
    """本次改动只落在「从磁盘读回来」那一侧，不许殃及新建。"""
    a = Annotation(book_id=BOOK_ID, quote="新建的标注")
    b = Annotation(book_id=BOOK_ID, quote="新建的标注")

    assert a.id != b.id, "两条新建标注拿到了同一个 id"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", a.created_at), (
        f"新建标注的 created_at 不再是 ISO 时间戳：{a.created_at!r}"
    )


def test_L10_全字段齐全时版本号本来就稳定(tmp_path: Path) -> None:
    """反向护栏：若这条也红，说明不稳定性另有来源，不是本 WI 修的那个。"""
    _write_notes(tmp_path, [dict(BASE_RECORD)])

    assert len({_version(tmp_path) for _ in range(3)}) == 1
