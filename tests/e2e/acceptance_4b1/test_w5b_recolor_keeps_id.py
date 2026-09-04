"""WI-17 —— W-5b：改色后颜色变为 green、**`id` 不变**、该段文字上仍**恰好一条**（`acceptance_4b1`，skip，参数化 ×3）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「W-5b（R1 修改）」。任务书 §3 的
W-5b 行、§0.5「W-5 为什么也落在这里（2026-09-01 裁定）」、§0.6 跨波欠账 **#9**。期望行为的落地定义在前端计划
`plan-frontend-ui-refactor.md` 的 WI-14。

**Law（S5，身份守恒）**：「改色」是对**同一条**标注的一次原地更新——`id` 不变、`type` 不变、`quote` 不变、
`color` 变为所点的色、该段文字上标注总数不变。

**为什么必须是三条参数。** `marker` 走 `toggleMarkerAnnotation`，`wavy` / `underline` 走 `toggleAnnotation`，
**是两份独立实现**。4B.1 要改的是两处，只写一条等于只给其中一处买了期望行为的证据。

**⚠️ 阻塞者：跨波欠账 #9——改色 wavy / underline 今天会静默丢数据。** `toggleAnnotation` 的异色分支先
`await deleteAnnotations(anyIds)`，其中的 `loadAndRender()` 重绘会 `normalize()` 文本节点，把 `currentRange`
塌成空 range，紧接着的 `createAnnotation` 带着空 `quote` 吃一个 400——净结果 `DELETE 204 → POST 400 →
该选区一条不剩`（W-5a-③ 特征化了它）。**4B.1 必须先修掉 #9，再解本模块的 skip**：否则 `wavy` /
`underline` 两个参数连「有一条标注在」都不成立，红的会是「0 条」而不是「id 变了」，把人指向错的地方。
`marker` 那一支今天不丢数据但会**另加一条**（W-5a-②），本条在它上面红在「2 条」。

**4B.1 配对关系（Gap 10，必须在两边 docstring 各写一次；W-5a 那边在
`baseline_1b/test_write_recolor_and_delete.py`）：**

| W-5b 参数 | 对应的 W-5a 支 | 4B.1 同 commit 动作 |
|---|---|---|
| `marker` | W-5a-② | 解开本参数的 skip；W-5a-② 改判或转出 |
| `wavy` | W-5a-③[wavy] | 同上 |
| `underline` | W-5a-③[underline] | 同上 |

**W-5a-⓪（同色重按 = 删除）不在这张表里**：4B.1 改的是异色分支，同色分支的 toggle-off 语义不变，
那一支在 4B.1 之后**应当保持绿**。W-5a-⓪ 的旁观条断言对 4B.1 的改法有约束力：若顺手把
`getExistingAnnotationIds` 的候选集从「选区命中」放宽成「整章同 type 同 color」，W-5a-⓪ 会红——那是正确
的红，不得靠删旁观条来「修」它。

**为什么用 `seed_notes` 预置一条带字面量 id 的标注，而不是从 UI 建。** §0 第五条纪律：守恒断言的基准必须是
字面量。从 UI 建再读回 id，`after["id"] == before["id"]` 是拿运行期读到的值比运行期读到的值——实现把整条
记录换掉、只要换得一致就照样绿。`W5B_TARGET_ID` 写死，「id 变成了别的」在失败消息里就是一个人能认出的字面量。

**解 skip 的顺序**：修 #9 ⇒ 4B.1 把两处异色分支改成原地改色（PUT，不删不建）⇒ 删本文件 skip 行 ⇒
`-m acceptance_4b1` ⇒ 同一 commit 里按上表处置 W-5a-② / ③。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_INDEX,
    CH0_QUOTE,
    NOTES_WAIT_S,
    open_ch0,
    read_notes,
    seed_notes,
    select_in_frame,
)

pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1：『改色保 id』要前端计划 WI-14 把两处异色分支改成原地更新才存在；"
            "且必须先修掉跨波欠账 #9（wavy/underline 异色重按静默丢数据），否则两个参数连一条标注都剩不下。"
            "到期动作：修 #9 → 落地原地改色 → 删本行，并在同一 commit 按 docstring 的配对表处置 W-5a-②/③。"
        )
    ),
]

#: 预置那条的 id / 颜色 / 创建时间全是字面量（§0 第五条纪律）。id 带参数名，三个参数互不相撞。
W5B_TARGET_ID_PREFIX = "wi17-w5b-target-"
SEED_COLOR = "yellow"
SEED_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: 要点的色板与期望落库的颜色。必须与 `SEED_COLOR` 不同，否则本条测的是同色分支（W-5a-⓪）。
SWATCH_TESTID = "rd-anno-color-green"
EXPECTED_COLOR = "green"

#: 改色之后该段文字上应当恰好一条——字面量基准。`>= 1` 对「另加一条」（今天的 marker 分支）也绿。
EXPECTED_COUNT_AFTER_RECOLOR = 1


def _wait_for_color(books_dir: Path, book_id: str, note_id: str, color: str) -> Dict[str, Any]:
    """等 `note_id` 那条的 `color` 变成 `color`。等的是被改的那个量，不是条数（条数在原地更新下不变）。"""
    deadline = time.monotonic() + NOTES_WAIT_S
    while time.monotonic() < deadline:
        for r in read_notes(books_dir, book_id):
            if r.get("id") == note_id and r.get("color") == color:
                return r
        time.sleep(0.05)
    final = read_notes(books_dir, book_id)
    current: Optional[Dict[str, Any]] = next((r for r in final if r.get("id") == note_id), None)
    if current is None:
        raise AssertionError(
            f"{NOTES_WAIT_S}s 后 id={note_id!r} 已经不在 notes.json 里——改色被实现成了「删掉再建」"
            f"（或欠账 #9 的丢数据路径）。现存：{[r.get('id') for r in final]}，共 {len(final)} 条"
        )
    raise AssertionError(f"{NOTES_WAIT_S}s 内 {note_id} 的 color 没有变成 {color!r}，当前 {current!r}")


@pytest.mark.parametrize(
    "action_testid,anno_type",
    [
        pytest.param("rd-anno-type-marker", "marker", id="marker"),
        pytest.param("rd-anno-type-wavy", "wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", "underline", id="underline"),
    ],
)
def test_w5b_recolor_keeps_id_and_leaves_exactly_one_annotation(
    page: Page, live_server: str, e2e_books_dir: Path, action_testid: str, anno_type: str
) -> None:
    """W-5b（S5 / L2）：预置 yellow 的 T → 选中同段 → 点 green → 重按 T → 刷新 ⇒ 1 条、id 同、color green、type 同、DOM 一个 `<mark>` 只带这个 id。"""
    target_id = W5B_TARGET_ID_PREFIX + anno_type
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": target_id,
                "chapter_index": CH0_INDEX,
                "type": anno_type,
                "color": SEED_COLOR,
                "quote": CH0_QUOTE,
                "created_at": SEED_CREATED_AT,
            }
        ],
    )
    before = read_notes(e2e_books_dir, BOOK_ID)
    assert [r["id"] for r in before] == [target_id], f"预置没落对：{before}"
    assert before[0]["color"] != EXPECTED_COLOR, "预置色与目标色相同，本条会退化成同色分支（W-5a-⓪）"

    frame = open_ch0(page, live_server, expected_marks=1)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(SWATCH_TESTID).click()
    page.get_by_test_id(action_testid).click()

    _wait_for_color(e2e_books_dir, BOOK_ID, target_id, EXPECTED_COLOR)

    # ---- 刷新到确定的终态再断（§0 第四条纪律：轮询到期望值不是终态）----------------------
    frame = open_ch0(page, live_server, expected_marks=EXPECTED_COUNT_AFTER_RECOLOR)
    after: List[Dict[str, Any]] = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == EXPECTED_COUNT_AFTER_RECOLOR, (
        f"改色 {anno_type} 之后该章应恰好 {EXPECTED_COUNT_AFTER_RECOLOR} 条，实际 {len(after)} 条：{after}\n"
        "    2 条 ⇒ 走了「换支笔再画一遍」（今天的 marker 分支，W-5a-②）；0 条 ⇒ 欠账 #9 的丢数据路径（W-5a-③）"
    )
    record = after[0]
    assert record["id"] == target_id, (
        f"改色之后 id 变了：{record['id']!r} != {target_id!r}——改色被实现成了「删了重建」，这正是本条要拦的"
    )
    assert record["color"] == EXPECTED_COLOR, f"落库的 color 是 {record['color']!r}，不是所点的 {EXPECTED_COLOR!r}"
    assert record["type"] == anno_type, f"改色顺手把 type 从 {anno_type!r} 改成了 {record['type']!r}"
    assert record["quote"] == CH0_QUOTE, f"改色顺手把 quote 从 {CH0_QUOTE!r} 改成了 {record['quote']!r}"
    assert record["created_at"] == SEED_CREATED_AT, (
        f"created_at 从 {SEED_CREATED_AT!r} 变成了 {record['created_at']!r}——原地更新不该动创建时间"
    )

    # ---- DOM 侧：该段文字上恰好一个 `<mark>`，且只携带这一个 id ----------------------------
    span = frame.get_by_test_id("rd-anno-span")
    expect(span).to_have_count(EXPECTED_COUNT_AFTER_RECOLOR)
    expect(span).to_have_text(CH0_QUOTE)
    raw_ids = span.evaluate("(el) => el.dataset.annotationIds")
    assert json.loads(raw_ids) == [target_id], (
        f"<mark> 携带的 id 列表是 {raw_ids}，期望恰好 [{target_id!r}]——两条重合时会合并进同一个 <mark>，靠计数看不出来"
    )
