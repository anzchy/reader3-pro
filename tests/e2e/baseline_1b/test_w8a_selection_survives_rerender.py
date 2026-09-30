"""#44 的确定性回归闸 —— 一次标注重绘不得让手上的选区作废。

**它守的是什么。** 用户选中一段文字、工具条弹出来、还没来得及按下高亮，这时后台
的标注重绘落地了：`AnnotationRenderer.applySegments`
（`src/reader3_app/web/static/js/annotations.js`）用
``entry.node.parentNode.replaceChild(frag, entry.node)`` 把被标注段落的原文本节点
**整个换掉**。

这里有一个**反直觉的中间环节，本用例存在的理由就在这一环**：被换掉的节点里的
Range 边界点**不会失效**。DOM 规范规定它**上浮到父元素**，offset 变成被移除子节点
的索引。于是 `AnnotationUI.currentRange` 的端点不再是文本节点、而是一个元素节点，
`offsetFromNode` 走进它的 **element 分支**，**静默返回一个错误的偏移**——不是 `null`。
`createAnnotation` 于是把 `quote` 算成空串、照样把 POST 发出去、服务端 400 拒收，
而返回值从来没人检查。**界面表现得与成功一模一样，盘上什么都没有。**

**这条推断曾经写错过，是探针推翻的。**最初记的病因是「`offsetFromNode` 找不到节点
⇒ 返回 `null` ⇒ `createAnnotation` 提前 return」。一次收控制台的探针证明那条分支
**根本没被走到**。留着这段话是为了记住：两种写法在「盘上少一条」这个唯一可观测面上
完全一致，只有把请求序列和控制台一起收下来才能分开。

**它与 W-8a 是什么关系。** W-8a
（`test_write_overlap_and_disambiguation.py`）在 GitHub Actions 上三跑三红、在本地
十次 soak ＋ 三个随机 seed 全绿，红的形状恒为「8.0s 内 notes.json 没有稳定到 2 条，
实际 1 条」，落了 A、没落 B（欠账 #44）。病因就是上面这条，而 A/B 的不对称是
**构造保证**的，不是运气：

* 建 A 的那一页盘上 0 条 ⇒ `render()` 里的 ``if (!textAnnotations.length) return;``
  提前返回 ⇒ **DOM 一个字节没动** ⇒ A 的选区怎么放都不会失效。
* 建 B 的那一页盘上已有 A ⇒ `render()` **必然**走到 `applySegments` ⇒ **必然**替换
  文本节点。于是只剩一个问题：替换落在 `[mouseup, click]` 这段窗口里没有。

W-8a 等那次重绘**自己**发生，所以它在快机器上赢、在 2 vCPU 的 runner 上输——一条
靠时序的赌。本用例把重绘**同步地造出来**（`page.evaluate` 直接调 `loadAndRender`
并 await 它），因此在任何机器上都走同一条路径：修复前必红，修复后必绿。
这正是 W-8a 缺的那个缺口。

**它与 W-5a-③ 是两个机制，不要合并。** 本条照的是「端点上浮到父元素」——端点
**离开**了文本节点。W-5a-③（`test_write_recolor_and_delete.py`）照的是 `normalize()`
把相邻文本节点**并成一个**、两个端点落到同一偏移上——端点**还在**文本节点里，只是
选区塌成了一个点。两者都让 `quote` 变成空串，但判据不同：前者靠「端点还锚不锚在
索引里的文本节点上」认出来，后者靠「算出来的两个偏移相不相等」认出来。一个修法
盖不住另一个，2026-09-21 实测过（只修前者时，W-5a-③ 那条路仍然丢数据）。

**落址。** 按内容它属于 `baseline_1b`（W-8a 家族，写路径），2026-09-21 随 W-5a-③
的改判一并迁入——那一次 `suite_hash` 本来就要变，把它和这次变动合并，省掉第二次清零。
在此之前它暂驻 `scripts/lint_e2e_groups.py` 的 `UNGROUPED_E2E_MODULES` 白名单，
并在那里留了到期条件；到期动作已执行，白名单条目已撤。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    open_reader,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b

#: 与 W-8a 同一对 quote，故意不换：本条要复现的就是那条用例的失败现场。
SEEDED_QUOTE = "Alpha pro"
NEW_QUOTE = "prose"

#: `"Alpha prose."` 里 `"prose"` 的偏移。W-8a 的 docstring 已经把这条性质写明并依赖：
#: `buildTextIndex` 不排除 `<mark>` 内的文本节点，所以重绘把段落切成两个文本节点之后，
#: 偏移轴仍然连续。本条顺带把它钉成断言——修法正是靠这条不变量才成立的。
NEW_QUOTE_POSITION = 9

#: 重绘之后盘上应当有的条数，**字面量基准**（模块族的第五条写作纪律）。`>= 1` 对
#: 「一条都没新增」也绿，而那正是本条要照的缺陷。
EXPECTED_AFTER_RERENDER = 2


def test_标注重绘之后手上的选区仍然能写成标注(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """选区建好 → **强制一次重绘** → 按 wavy ⇒ 第二条必须落盘。

    断言分三段，抓的不是同一件事：

    (a) **条数到 2** —— 丢写的唯一可观测面。缺陷态下 `createAnnotation` 发出去的是
        一个空 `quote` 的 POST，被服务端 400 拒收而返回值没人检查，所以除了盘上少
        一条之外，外部看不出任何异常。
    (b) **两条的 quote 是那两个** —— 挡住「把已有那条改掉冒充新增」的实现：
        它同样能让条数变成 2（改一条再加一条），却丢了 A。
    (c) **新那条的 position 是 9** —— 挡住「回退到一个过期偏移」的修法。
        修法允许在活取失败时回落到选区落定那一刻算好的快照，前提是偏移轴对重绘
        不变；这条断言就是那个前提的现场检验。position 若漂了，说明回退拿的是
        一个与当前文档对不上的坐标，那种「写进去了但位置是错的」比不写更坏。

    三条都是实测过会咬人的：2026-09-21 分别把 `rangeAnchoredIn` 改成恒真、把快照
    偏移整体 +1，(a) 与 (c) 各自当场红（后者留下 `quote='rose', position=10`）。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": SEEDED_QUOTE,
                "prefix": "One",
                "suffix": "se.\n",
                "position": 3,
            }
        ],
    )
    assert len(read_notes(e2e_books_dir, BOOK_ID)) == 1, "预置没生效：起点不是 1 条"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    select_in_frame(frame, NEW_QUOTE)
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()

    # 把竞态造出来，不等它自己发生。await 它，所以返回时 DOM 替换**已经落地**——
    # 这一行就是 W-8a 在 CI 上输掉的那场赛跑，在这里被写成了确定的先后。
    page.evaluate(
        "async () => { await window.Reader3AnnotationUI.renderer.loadAndRender(); }"
    )

    page.get_by_test_id("rd-anno-type-wavy").click()

    landed = wait_for_notes(e2e_books_dir, BOOK_ID, EXPECTED_AFTER_RERENDER, page=page)

    by_quote = {r["quote"]: r for r in landed}
    assert set(by_quote) == {SEEDED_QUOTE, NEW_QUOTE}, (
        f"两条的 quote 不是 {SEEDED_QUOTE!r} / {NEW_QUOTE!r}：{landed}"
    )
    assert by_quote[NEW_QUOTE]["position"] == NEW_QUOTE_POSITION, (
        f"新那条落在 position={by_quote[NEW_QUOTE]['position']}，应当是 "
        f"{NEW_QUOTE_POSITION}——回退用的偏移与当前文档对不上，"
        "写进去了但位置是错的，比不写更坏"
    )
