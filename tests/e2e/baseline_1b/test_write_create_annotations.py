"""WI-4 —— W-1 / W-2 / W-3：marker / wavy / underline 的创建，写路径的地基。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-4。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §3（写路径用例）、
§0「往返断言」纪律、§1「iframe 内建选区的标准路径」。

**这三条测的是同一条链**：选区 → 工具条 → `data-action` 按钮 → `commands` →
`POST /api/notes/{book}/{chapter}` → 刷新 → iframe 内 `<mark>` 复现。

**为什么收尾动作一律是「刷新页面」。** 任务书 §0 把「断言 `POST /api/notes/*` 发生过」
明确列为反例：写侧的四个接触面里有四个坏了不报错，请求发出去和数据落到盘上、再从盘上
被正确解析回同一段文字，是三件不同的事。前两件在不刷新的页面上分辨不出来——`createAnnotation`
末尾会 `loadAndRender()` 重绘一次，那次重绘用的是**服务端返回后重新拉取的**列表，但整个
过程里页面 JS 状态从未清零。刷新是唯一能把「JS 里还记得」与「盘上真的有」分开的动作。

**为什么 `<mark>` 的判据是 `textContent`，不是数量。** 任务书 §3 W-1 行写死了这一点：
一条「有 1 个 `<mark>`」的断言在高亮画错位置时照样绿。数量那一半的判据落在 `notes.json`
上（恰好 1 条），两边合起来才是矩阵第一定律说的「写入—重载往返守恒」。

**为什么 `notes.json` 的条数写 `== 1` 而不是 `>= 1`。** `>= 1` 会放过「一次点击写两条」
——`toggleAnnotation` 的删旧建新分支里恰好有两次落库动作，写成 `>=` 时那条分支即使把
「删」漏掉也不会红。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
from playwright.sync_api import FrameLocator, Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    SELECTION_DEBOUNCE_MS,
    SELECTION_DEBOUNCE_SLACK_MS,
    SELECTION_TIMEOUT_MS,
    read_notes,
    select_in_frame,
    viewport_rect_of_selection,
)

pytestmark = pytest.mark.baseline_1b


# 等落库。点完按钮到文件出现之间隔着一次网络往返 + 一次原子写。
NOTES_WAIT_S = 8.0

# 第 0 章 `<h1>One</h1><p>Alpha prose.</p>`，第 1 章 `<h1>Two</h1><p>Beta prose.</p>`
# （`tests/fixtures/epub_corpus.py` 的 `build_epub2`）。两条 quote 都**不含句点**：
# 句点留在选区之外，是为了让「选区边界选对了没有」在断言里可分辨——若拖选或程序化选区
# 多吃一个字符，`quote` 会变成 `Alpha prose.`，往返断言当场红。
CH0_QUOTE = "Alpha prose"
CH0_ANCHOR = "Alpha prose."
CH1_QUOTE = "Beta prose"
CH1_ANCHOR = "Beta prose."


def _open_reader(
    page: Page, base_url: str, book_id: str, chapter_index: int, expect_text: str
) -> FrameLocator:
    """打开阅读器并等到 iframe 里真的有正文。

    与 `test_harness_helpers.py` 里的同名函数是同一段逻辑。**刻意不抽到 `helpers.py`**：
    那个文件是 WI-3 记录在案的规格文件，且它自己的 docstring 写明它只放四个选区/落库/几何
    helper。为了省 6 行而去改一份已冻结的共享文件，代价是整套 baseline 的 `suite_hash`
    失效、soak 计数清零——那比这点重复贵得多。
    """
    page.goto(f"{base_url}/read/{book_id}/{chapter_index}")
    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(expect_text)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    return frame


def _wait_for_notes(books_dir: Path, book_id: str, count: int) -> List[Dict[str, Any]]:
    """等 `notes.json` 稳定到 `count` 条，超时即红并把实际内容打出来。

    这不是「重试掩盖 flaky」：落库是异步的（fetch → 服务端原子写），不等就是在断言一个
    还没发生的事件。等的是**一个确定的终态**，不是「多试几次也许就成了」——终态不对时它
    照样红，且把实际条目原样贴出来。
    """
    deadline = time.monotonic() + NOTES_WAIT_S
    seen: List[Dict[str, Any]] = []
    while time.monotonic() < deadline:
        seen = read_notes(books_dir, book_id)
        if len(seen) == count:
            return seen
        time.sleep(0.05)
    raise AssertionError(
        f"{NOTES_WAIT_S}s 内 notes.json 没有稳定到 {count} 条，实际 {len(seen)} 条：{seen}"
    )


def _assert_roundtrip(
    page: Page,
    books_dir: Path,
    quote: str,
    anchor: str,
    expected_type: str,
) -> Dict[str, Any]:
    """§0 的往返断言，三条用例共用的收尾：**刷新** → 高亮回到同一段文字上。

    顺序是刻意的：先读盘（此时页面还没刷新，读到的是服务端真的写下去的东西），再刷新，
    再断 DOM。反过来先刷新再读盘的话，「盘上没有但 JS 还记得」这个失败态会被刷新动作
    自己抹掉，而那正是本纪律要抓的东西。
    """
    records = _wait_for_notes(books_dir, BOOK_ID, 1)
    record = records[0]
    assert record["type"] == expected_type, (
        f"落库的 type 是 {record['type']!r}，不是按下的那个按钮对应的 {expected_type!r}："
        f"`handleAction` 的 action 名与模板 `data-action` 取值失配？完整条目：{record}"
    )
    assert record["quote"] == quote, (
        f"落库的 quote 是 {record['quote']!r}，不是选中的 {quote!r}。"
        f"（生产端取 `buildTextIndex(...).text.slice(s, e)`，多吃/少吃一个字符都会在这里显形）"
    )

    page.reload()
    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(anchor)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    span = frame.get_by_test_id("rd-anno-span")
    # `to_have_text` 会自动等待——刷新后的高亮要等 `loadAndRender()` 跑完才挂上。
    # 用它而不是先 `to_be_visible()` 再取值：后者会在「`<mark>` 已挂但文本错」时先绿一次，
    # 把失败推迟到下一行，报出来的诊断信息也更差。
    expect(span).to_have_text(quote)
    assert span.text_content() == quote, (
        f"刷新后 `<mark>` 覆盖的文本是 {span.text_content()!r}，不是创建时选中的 {quote!r}"
    )

    # 「恰好 1 条」要在**终态**再断一次，上面 `_wait_for_notes` 那次不算数。
    #
    # 2026-09-02 实测：给 `createAnnotation` 加一次重复 POST（两次写相隔 7ms）后跑三条，
    # 结果是 **2 红 1 绿**——wavy 那条绿了。两个原因叠在一起：
    #   1. `_wait_for_notes` 一观察到 `len == 1` 就返回，50ms 的轮询有一定概率正好落在
    #      两次写之间的窗口里，把中间态当成终态；
    #   2. DOM 侧兜不住：两条**完全重合**的标注在 `render()` 的分段里合并成一个 `<mark>`，
    #      所以 strict 模式不会因为「两个 rd-anno-span」而报错。
    # 于是「一次点击写两条」这条缺陷在原写法下是**概率性漏检**，而不确定性正是 G2 禁的东西。
    # 刷新已经完成，第二次写早就落盘了，此刻读到的就是终态。
    settled = read_notes(books_dir, BOOK_ID)
    assert len(settled) == 1, (
        f"终态不是恰好 1 条，而是 {len(settled)} 条——一次创建动作写了不止一条："
        f"{settled}"
    )
    assert settled[0]["id"] == record["id"], (
        f"终态那条的 id 与落库时读到的不是同一条：{settled[0]['id']} != {record['id']}"
    )
    return record


def _clear_selection_and_drain(page: Page, frame: FrameLocator) -> None:
    """清掉 iframe 内的选区，并等 `onSelection` 的去抖窗口排空。

    W-1 专用。`select_in_frame` 返回之后，`handleRenditionSelection` 的自持循环会以
    ~250ms 一拍持续刷新 `lastSelectionAt`（`helpers.select_in_frame` 的 docstring 记了实测
    时序）；此时直接拖选，我们的 `mouseup` 有约 120/250 的概率落进 :695 的守卫里被丢掉。
    清空选区让 epub.js 那一侧当场停手（它的 `selected` 只在非折叠 range 上触发），窗口才会
    真的开始变老。

    **这不是 sleep，也不是重试**：等的是一个可观测的条件（`lastSelectionAt` 的年龄），
    等不到就抛。任务书 §1 点名过「遇到间歇性失败先怀疑这条循环，不要加 sleep 或重试掩盖」
    ——排空窗口正是那条注记里给出的正解。
    """
    frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
        "() => { const s = document.getSelection(); if (s) s.removeAllRanges(); }"
    )
    page.wait_for_function(
        "(minAge) => Date.now() - (window.Reader3AnnotationUI?.lastSelectionAt || 0) >= minAge",
        arg=SELECTION_DEBOUNCE_MS + SELECTION_DEBOUNCE_SLACK_MS,
        timeout=SELECTION_TIMEOUT_MS,
    )


def test_w1_real_mouse_drag_creates_marker_and_survives_reload(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-1（S5，往返不变式）：**真实鼠标拖选** → Marker → 刷新 → 高亮回到同一段文字。

    **全表唯一一条拖选 smoke。** 拖选是 CI 头号 flaky 源，而 flaky 会把 Phase 3 的 soak
    计数清零，所以其余 30 余条一律走 `select_in_frame` 的程序化路径。留这一条，是因为
    程序化路径绕开了浏览器原生的 selection 生成：`mouseup` 是我们自己 dispatch 的，
    `Selection` 是我们自己 `addRange` 的。真实拖选是唯一能证明「用户真的这么操作时这条链
    也通」的动作——它坏掉而程序化路径还绿，恰恰是这套 E2E 最该报警的一天。

    **坐标怎么来的，以及为什么这不违反「全程无 `page.evaluate` 建选区」。**
    先用 `select_in_frame` 选一次、量出视口矩形、**再把选区清掉**，然后用 `page.mouse` 在那个
    矩形上重新拖一遍。被断言的那个选区**完全由 `page.mouse` 产生**——程序化的那次只用来
    取几何，且在按下鼠标之前就已经不存在了。矩阵禁的是「用 evaluate 造出被断言的那个选区」，
    不是禁用 evaluate 读坐标；这一段写在这里，免得后来者照着它去写第二条「拖选」用例。

    自检：把 `annotations.js` 的 `createAnnotation` 换成空函数，刷新后没有 `<mark>` → 红；
    后端接了请求但不落盘，刷新后同样没有 `<mark>` → 红。没有任何「返回预期值」的捷径能让
    它绿——判据落在**另一个进程写下的文件**与**刷新后重建的 DOM**上。

    flaky 预案（矩阵写死）：若 G2 的三次零 flaky 因本条不过，动作是把它移出 `baseline_1b`
    （另挂一个不计入 soak 的 marker），**不是加重试也不是加等待**。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = _open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    select_in_frame(frame, CH0_QUOTE)
    rect = viewport_rect_of_selection(page, frame)
    _clear_selection_and_drain(page, frame)

    # 起点 left+1 / 终点 right-1：矩形的两个竖边正落在 "A" 的左沿与 "e" 的右沿上，
    # 往内缩 1px 仍在同一个字形内，而浏览器的插入点吸附取的是**离得最近的字符边界**
    # ——1px 远小于半个字宽，所以吸附结果与压在边上一致，且不会因为亚像素舍入越到隔壁字符。
    y = (rect["top"] + rect["bottom"]) / 2
    page.mouse.move(rect["left"] + 1, y)
    page.mouse.down()
    # 中途多走一步：一次性从起点跳到终点，某些平台上会被当成没有移动过的点击。
    page.mouse.move((rect["left"] + rect["right"]) / 2, y)
    page.mouse.move(rect["right"] - 1, y)
    page.mouse.up()

    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-type-marker").click()

    _assert_roundtrip(page, e2e_books_dir, CH0_QUOTE, CH0_ANCHOR, expected_type="marker")


@pytest.mark.parametrize(
    "action_testid,expected_type",
    [
        pytest.param("rd-anno-type-wavy", "wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", "underline", id="underline"),
    ],
)
def test_w2_w3_programmatic_selection_creates_typed_annotation(
    page: Page,
    live_server: str,
    e2e_books_dir: Path,
    action_testid: str,
    expected_type: str,
) -> None:
    """W-2 / W-3（S2，取值域等价类）：`toggleAnnotation` 那一支的两个 type 各走一次。

    `handleAction` 把三个按钮分成两支：`marker` 走 `toggleMarkerAnnotation`（W-1 已覆盖），
    `wavy` / `underline` 走 `toggleAnnotation`。本条参数化的是**后一支的取值域**——两个值
    各一次，不多不少。第三个值（`note`）不在这里，它走 `openNoteEditor`，是 W-4。

    条数断言写 `== 1` 而不是 `>= 1`：`toggleAnnotation` 的新建分支之前有一段「同类型异色
    就先删旧」的逻辑，写成 `>=` 时那段逻辑退化成「只建不删」也不会红。

    ------------------------------------------------------------------------
    **那条 ~250ms 自持循环，在本条里的实测表现**（2026-09-02，chromium 1234）
    ------------------------------------------------------------------------
    任务书 §1 警告：`select_in_frame` 返回后循环会重新起来并重置 `currentRange`，
    「点工具条按钮必须够快」。**循环确实存在**——探针（本章 `Beta prose`，每 30ms 采一次
    `Reader3AnnotationUI.lastSelectionAt`）测到它在 `select_in_frame` 返回后的
    **269 / 509 / 773 / 1033 / 1270 / 1536ms** 各刷新一次，即约 260ms 一拍，1.6s 内不收敛。

    但**「够快」这个要求在创建路径上是宽松的，宽松到不需要任何特殊写法**，两个实测支撑：

      1. `select_in_frame` 返回到 `click()` 返回之间实测 **30ms**，而循环的第一拍在 269ms
         ——点击整个落在第一拍之前，`currentRange` 根本还没被碰过；
      2. 更重要的是，即使落在拍子之后也无妨：整段 1.6s 采样里 `currentRange.toString()`
         的取值集合恒为 `{'Beta prose'}`。那次重置写回的是**同一段文字**解析出来的等价
         range（`handleRenditionSelection` 拿的是 epub.js 给的 `cfiRange`，而选区没变），
         所以 `createAnnotation` 算出的 start/end 不变。

    会被那条循环真正打坏的是**编辑态**（`handleRenditionSelection` 把 `editingNoteId`
    清成 null），也就是 W-4 / W-7 那类「建好选区后还要再操作一步」的用例；创建路径只读
    `currentRange`，对重置免疫。

    所以这里**不加任何 sleep、不加重试**——`select_in_frame` 返回即点击，是最短路径。
    若将来这条真的间歇红了，正解仍是缩短选区与点击之间的间隔或在点击前确认 `currentRange`，
    不是往这里塞等待。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = _open_reader(page, live_server, BOOK_ID, 1, CH1_ANCHOR)

    select_in_frame(frame, CH1_QUOTE)
    page.get_by_test_id(action_testid).click()

    _assert_roundtrip(page, e2e_books_dir, CH1_QUOTE, CH1_ANCHOR, expected_type=expected_type)
