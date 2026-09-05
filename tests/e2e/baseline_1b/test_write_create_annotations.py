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

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    CH1_ANCHOR,
    CH1_QUOTE,
    assert_roundtrip,
    frame_box,
    open_reader,
    read_notes,
    select_in_frame,
)

pytestmark = pytest.mark.baseline_1b

# `open_reader` / `wait_for_notes` / `assert_roundtrip` / `clear_selection_and_drain`
# 以及 `CH*_QUOTE` / `CH*_ANCHOR` 都在 `tests/e2e/helpers.py`（Wave 0 上收，任务书 §0.6）。
# 本模块此前那段「刻意不抽到 helpers.py」的注记已随之作废——理由见 helpers.py 的模块 docstring。


# ---------------------------------------------------------------------------
# 量 quote 的矩形，**全程不碰 Selection**
# ---------------------------------------------------------------------------
#
# `helpers.viewport_rect_of_selection` 读的是**当前选区**的矩形，所以调它之前必须先有一个
# 选区；W-1 原先为此先跑一次 `select_in_frame`。那条路有一个致命的副作用：`select_in_frame`
# 会派发 mouseup、跑完 `onSelection` → `handleSelectionRange`，于是 `Reader3AnnotationUI`
# 的 `currentRange` 被装上「Alpha prose」、工具条进入 `is-visible`。随后 `clear_selection_and_drain`
# 只清 iframe 里的 `Selection`，**清不掉这两样**——`currentRange` 与工具条照旧留着。
# 后果：一条**彻底坏掉**的真实拖选路径（比如 `onSelection` 整个不再被调用）在原写法下照样
# 全绿，因为 `handleAction("marker")` 读的是那个残留的 `currentRange`，它恰好等于我们想要的
# 那段文字。W-1 的全部意义（「用户真的这么拖时这条链也通」）在那种实现下**一个字都没测到**。
#
# 所以本模块自己建一个**游离 Range**（`doc.createRange()`，从不 `sel.addRange`）来取几何：
# 游离 Range 不触发 `selectionchange`，epub.js 的 `selected` 不 emit，`onSelection` 不跑，
# `currentRange` 与工具条都保持初态。这样「拖之前 currentRange 必须是 null」才断得成立，
# 而那条断言正是把「被断言的选区完全由 page.mouse 产生」从一句注释变成一个判据的东西。
#
# 不上收到 `helpers.py`：那是共享面，本波三条 WI 并行开工时改它要动别人的等待纪律；
# 而这段只有 W-1 一处需要——全表唯一一条真实拖选用例。
_QUOTE_RECT_JS = r"""
(body, quote) => {
  const doc = body.ownerDocument;
  // TreeWalker 拼连续文本轴，与 helpers._SELECT_JS / 生产端 buildTextIndex 同一口径：
  // 跨元素边界的 quote 也定位得到，且偏移与生产端对得上。
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let text = "";
  while (walker.nextNode()) {
    nodes.push([walker.currentNode, text.length]);
    text += walker.currentNode.data;
  }
  const start = text.indexOf(quote);
  if (start === -1) {
    throw new Error(
      "_quote_viewport_rect: 章内找不到 " + JSON.stringify(quote) +
      "（body 文本 " + text.length + " 字符，开头 " + JSON.stringify(text.slice(0, 80)) + "）"
    );
  }
  const end = start + quote.length;
  const locate = (pos, isEnd) => {
    for (const [node, base] of nodes) {
      const limit = base + node.data.length;
      if (isEnd ? pos <= limit : pos < limit) return [node, pos - base];
    }
    const [node, base] = nodes[nodes.length - 1];
    return [node, pos - base];
  };
  const range = doc.createRange();
  const [startNode, startOffset] = locate(start, false);
  const [endNode, endOffset] = locate(end, true);
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  // 只读矩形，**绝不** doc.getSelection().addRange(range)：一旦装进 Selection，
  // selectionchange 就会把 epub.js 的 selected 拍起来，本函数的全部意义随之消失。
  const r = range.getBoundingClientRect();
  if (!r.width || !r.height) {
    throw new Error("_quote_viewport_rect: Range 矩形是空的（宽 " + r.width + " 高 " + r.height + "）");
  }
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
}
"""

#: 拖之前 `Reader3AnnotationUI` 必须处于的状态。`currentRange` 读成字符串（`null` 时给
#: `None`），因为 Range 对象跨不过 `page.evaluate` 的序列化边界。
_UI_STATE_JS = r"""
() => {
  const ui = window.Reader3AnnotationUI;
  if (!ui) return { hasUi: false, currentRange: null, editingNoteId: null };
  return {
    hasUi: true,
    currentRange: ui.currentRange ? String(ui.currentRange.toString()) : null,
    editingNoteId: ui.editingNoteId == null ? null : String(ui.editingNoteId),
  };
}
"""


def _quote_viewport_rect(page: Page, frame, quote: str) -> dict:
    """`quote` 那一段文字在**外层视口**坐标里的矩形，不经过任何选区。

    换算与 `helpers.viewport_rect_of_selection` 同形（iframe 内 rect ＋ `frame_box` 偏移），
    差别只有一处、而那一处是本条用例的全部要害：矩形取自一个**游离 Range**，不是当前选区。
    """
    inner = frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
        _QUOTE_RECT_JS, quote
    )
    box = frame_box(page)
    return {
        "left": inner["left"] + box["x"],
        "right": inner["right"] + box["x"],
        "top": inner["top"] + box["y"],
        "bottom": inner["bottom"] + box["y"],
    }


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
    用 `_quote_viewport_rect` 量出那段文字的视口矩形，再用 `page.mouse` 在矩形上拖一遍。
    量矩形走的是一个**游离 `Range`**（`createRange` 之后只读 `getBoundingClientRect`，从不
    `addRange`），所以它不派发 `selectionchange`、不惊动 epub.js 的 `selected`、不跑
    `onSelection`——被断言的那个选区**完全由 `page.mouse` 产生**。矩阵禁的是「用 evaluate
    造出被断言的那个选区」，不是禁用 evaluate 读坐标；这一段写在这里，免得后来者照着它去
    写第二条「拖选」用例。

    **拖之前那两条断言不是仪式。** 本条曾经先跑一次 `select_in_frame` 取几何、再
    `clear_selection_and_drain` 清场。那个写法有个洞：`clear_selection_and_drain` 只清
    iframe 里的 `Selection`，`Reader3AnnotationUI.currentRange` 和已经 `is-visible` 的工具条
    **都留着**，而它们恰好就是 `handleAction("marker")` 真正读的东西。于是「`onSelection`
    整个不再被调用」这种把真实拖选彻底打断的实现，在旧写法下照样全绿——W-1 想证的那件事
    一个字都没测到（该洞由 009 审计 F3 报出）。现在几何改从游离 Range 取，并在按下鼠标前
    显式断言 `currentRange is None`、工具条不可见：这两条把「被断言的选区完全由 `page.mouse`
    产生」从一句注释变成了一个判据。

    自检：把 `annotations.js` 的 `createAnnotation` 换成空函数，刷新后没有 `<mark>` → 红；
    后端接了请求但不落盘，刷新后同样没有 `<mark>` → 红。没有任何「返回预期值」的捷径能让
    它绿——判据落在**另一个进程写下的文件**与**刷新后重建的 DOM**上。

    flaky 预案（矩阵写死）：若 G2 的三次零 flaky 因本条不过，动作是把它移出 `baseline_1b`
    （另挂一个不计入 soak 的 marker），**不是加重试也不是加等待**。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    rect = _quote_viewport_rect(page, frame, CH0_QUOTE)

    # 拖之前的初态判据：没有它，一条「onSelection 根本没跑」的实现也能靠残留状态蒙混过关。
    before = page.evaluate(_UI_STATE_JS)
    assert before["hasUi"], (
        "window.Reader3AnnotationUI 不存在——annotations.js 没挂上，下面全部判据都是空的"
    )
    assert before["currentRange"] is None, (
        f"按下鼠标之前 currentRange 已经是 {before['currentRange']!r}。"
        "量矩形那一步惊动了选区链路，本条就退化成「读残留状态」，测不到真实拖选"
    )
    expect(page.get_by_test_id("rd-anno-toolbar")).not_to_be_visible()

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

    assert_roundtrip(page, e2e_books_dir, BOOK_ID, CH0_QUOTE, CH0_ANCHOR, expected_type="marker")


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

    frame = open_reader(page, live_server, BOOK_ID, 1, CH1_ANCHOR)

    select_in_frame(frame, CH1_QUOTE)
    page.get_by_test_id(action_testid).click()

    assert_roundtrip(
        page, e2e_books_dir, BOOK_ID, CH1_QUOTE, CH1_ANCHOR, expected_type=expected_type
    )
