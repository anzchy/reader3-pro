"""WI-3 的 e2e lane 四条：helper 自证、隔离自证、几何同解、语料扩容。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-3。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0 三条写作纪律、
§1「iframe 内建选区的标准路径」。

**为什么这四条必须在 e2e lane 而不是别处。** 判据是「真协作者坏掉时本用例还会不会绿」：
被测的是 `Selection` 不能跨 browsing context 这件事本身、`annotations.js` 绑在
`contentDocument` 上的 `mouseup`、以及浏览器算出来的几何。任何一段用桩替掉，用例就
不再能失败。第五条（`seed_notes` 往返）恰恰相反——纯文件系统，所以它在 unit lane，
见 `tests/unit/test_e2e_helpers_notes_roundtrip.py`。

**这四条是地基，不是叶子。** W/R 系列 30 余条用例全部通过 `helpers.select_in_frame`
建选区、通过 `helpers.read_notes` 断落库。helper 若是错的，那 30 余条会以一个与被测物
无关的原因红（或者更糟：以一个与被测物无关的原因绿）。所以 helper 的能力在这里被
逐条证明，而不是藏在它们的失败里。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import pytest
from playwright.sync_api import Page, expect

from conftest import (  # type: ignore[import-not-found]
    BOOK_ID,
    BOOK_ID_CJK,
    BOOK_ID_REPEAT,
    E2E_BOOKS,
    REPEAT_BOOK_NEEDLE,
)
from helpers import (  # type: ignore[import-not-found]
    open_reader,
    read_notes,
    select_in_frame,
    viewport_rect_of_selection,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b


# 一条选区的四个边与「参考实现」的四个边最多差这么多。1px 不是容差品味，是矩阵写死的
# 判据：iframe 纵向偏移在本布局下 ≥40px（`.pagination-container { padding-top: 40px }`），
# 1px 的阈值对它足够灵敏。
#
# 只有本文件用它，所以它留在这里：它是几何同解那一条的判据，不是共享路径的一部分。
# （`open_reader` / `wait_for_notes` / `NOTES_WAIT_S` 已在 Wave 0 上收进 `helpers.py`，
# 见任务书 §0.6。）
RECT_EPS_PX = 1.0


# 域的边界写在这里，不写在断言里。五个值，四种取词形态 + 一种跨节点形态。
# 【R1 新增的第五个值】的理由：W-8b 的分段渲染依赖 `buildTextIndex` 把多个文本节点
# 视作一条连续偏移轴。helper 若只会在**单个** `Text` 节点内建 Range，W-8b 会以一个与
# 被测物无关的原因红。这个能力必须在 helper 自己的用例里被证明。
SELECTION_DOMAIN = [
    # (id, book_id, chapter, quote, occurrence, 页面上必须先出现的文字, 该 quote 至少出现几次, 是否要求跨节点)
    pytest.param(BOOK_ID, 0, "Alpha prose", 0, "Alpha prose.", 1, False, id="epub2-latin-phrase"),
    pytest.param(BOOK_ID_CJK, 0, "咖啡館", 0, "他在咖啡館裡等了很久。", 1, False, id="cjk-mid-sentence"),
    pytest.param(BOOK_ID_REPEAT, 0, "the mast swung", 0, REPEAT_BOOK_NEEDLE, 2, False, id="repeated-first"),
    pytest.param(BOOK_ID_REPEAT, 0, "the mast swung", -1, REPEAT_BOOK_NEEDLE, 2, False, id="repeated-last"),
    # "OneAlpha prose." —— `<h1>One</h1><p>Alpha prose.</p>` 的 textContent，中间没有
    # 空白（`epub_zip.py` 的 `<body>{doc.body}</body>` 是逐字插入）。"neAlpha" 因此
    # 横跨 h1 与 p 两个文本节点。
    pytest.param(BOOK_ID, 0, "neAlpha", 0, "Alpha prose.", 1, True, id="across-element-boundary"),
]

_PROBE_JS = """
(_el, [quote, occurrence]) => {
  // 第一个形参是 Playwright 传进来的元素句柄（Locator.evaluate 的固定契约），
  // 这里用不上；实参从第二个形参解构。
  const body = document.body;
  const doc = body.ownerDocument;
  // 期望偏移从 body.textContent 上用 indexOf 独立算出来，不问被测代码要。
  // 被测代码用的是 TreeWalker 上的累加偏移；两边同解才说明「选对了哪一处」。
  const t = body.textContent;
  const hits = [];
  for (let i = t.indexOf(quote); i !== -1; i = t.indexOf(quote, i + 1)) hits.push(i);
  const want = hits.length ? hits[occurrence < 0 ? hits.length + occurrence : occurrence] : null;

  const sel = doc.getSelection();
  if (!sel || sel.rangeCount < 1) {
    return { text: null, startOffset: null, sameContainer: null, hitCount: hits.length, expectedOffset: want };
  }
  const r = sel.getRangeAt(0);
  // 实际偏移用 Range 克隆量出来（body 起点 → 选区起点的文本长度），这是与 indexOf
  // 完全不同的一条路。两条路都错到同一个数上，才可能骗过这条断言。
  const pre = doc.createRange();
  pre.setStart(body, 0);
  pre.setEnd(r.startContainer, r.startOffset);
  return {
    text: sel.toString(),
    // `Range.toString()` 与 `Selection.toString()` 不是同一个东西，且**只在跨块元素时
    // 分岔**：前者拼接 Text 节点的 data，后者走渲染文本序列化，会在块级边界插一个换行。
    // 生产端 `createAnnotation` 用的是 `buildTextIndex(...).text.slice(s, e)`，也就是
    // 拼接语义 —— 与 `Range.toString()` 同解，与 `Selection.toString()` 在跨块时不同解。
    rangeText: r.toString(),
    startOffset: pre.toString().length,
    sameContainer: r.startContainer === r.endContainer,
    hitCount: hits.length,
    expectedOffset: want,
  };
}
"""


@pytest.mark.parametrize(
    "book_id,chapter,quote,occurrence,anchor_text,min_hits,must_cross_nodes", SELECTION_DOMAIN
)
def test_select_in_frame_builds_the_requested_selection(
    page: Page,
    live_server: str,
    book_id: str,
    chapter: int,
    quote: str,
    occurrence: int,
    anchor_text: str,
    min_hits: int,
    must_cross_nodes: bool,
) -> None:
    """S4：在五个取词形态上，`select_in_frame` 都建出**请求的那一处**选区。

    三层断言，各答一个不同的问题：
      * `getSelection().toString() == quote` —— 选对了**什么字**；
      * 起点偏移 == 该 occurrence 的偏移 —— 选对了**哪一处**（"重复文本本" 那两个参数
        值全靠这一层区分，第一处和末次出现的文本是一模一样的）；
      * `rd-anno-toolbar` 可见 —— iframe 里的 `mouseup` 真的走到了外层的
        `annotations.js`。这一层是 W 系列的前提：工具条不开，后面没有任何按钮可点。

    自检：把 helper 换成「只 dispatch mouseup 不建 Range」，前两层双红；换成
    「只在单个文本节点内建 Range」，第五个参数红而前四个绿——这正是加那个参数的理由。
    """
    frame = open_reader(page, live_server, book_id, chapter, anchor_text)

    select_in_frame(frame, quote, occurrence=occurrence)

    probe = frame.locator("body").evaluate(_PROBE_JS, [quote, occurrence])  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    assert probe["hitCount"] >= min_hits, (
        f"语料变了：{book_id} 第 {chapter} 章里 {quote!r} 只出现 {probe['hitCount']} 次，"
        f"本参数值要求至少 {min_hits} 次。occurrence={occurrence} 的语义会退化。"
    )
    # 逐字判据用 Range 语义，因为**那才是生产端落库的那个 quote**：`createAnnotation`
    # 取 `buildTextIndex(...).text.slice(s, e)`（annotations.js:990），而 `buildTextIndex`
    # 是纯 `text += node.nodeValue` 的 Text 节点拼接（:54-76）；复制/AI 那条路径取
    # `currentRange.toString()`（:1038）。**两条生产路径都不经过 `Selection.toString()`。**
    assert probe["rangeText"] == quote, (
        f"Range 覆盖的文本是 {probe['rangeText']!r}，不是请求的 {quote!r}"
    )
    # Selection 侧只证明「选区确实装进了 Selection 对象」——没装进去的话 toString 为空、
    # 工具条也不会开。这里不能要求逐字相等：`Selection.toString()` 走的是渲染文本序列化，
    # **跨块级边界会插换行**。实测 quote="neAlpha"（横跨 h1 与 p）得到 'ne\nAlpha'。
    # 矩阵第一定律原本把判据写成 `getSelection().toString() == quote`，与它自己在 R1 加的
    # 跨块参数值互斥——那条判据测的是一个生产端不使用的量。判据已改（用户 2026-09-02 裁定），
    # 对另外四个不跨块的参数值，本行与旧断言完全等价。
    assert probe["text"].replace("\n", "") == quote, (
        f"Selection 里的文本去掉块边界换行后是 {probe['text'].replace(chr(10), '')!r}，"
        f"不是请求的 {quote!r}（原始值 {probe['text']!r}）"
    )
    assert probe["startOffset"] == probe["expectedOffset"], (
        f"选区落在偏移 {probe['startOffset']}，但 {quote!r} 的第 {occurrence} 次出现在 "
        f"{probe['expectedOffset']}（共 {probe['hitCount']} 处）"
    )
    if must_cross_nodes:
        assert probe["sameContainer"] is False, (
            "这个参数值的全部意义就是跨文本节点。startContainer === endContainer 说明它"
            "退化成了普通单节点取词，参数白加。"
        )
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()


def test_notes_isolation_gives_every_round_the_same_initial_state(
    page: Page, live_server: str, e2e_books_dir: Path, notes_isolation: Any
) -> None:
    """S5：状态复位不变式。同一段「选区 → marker → 落库」跑两轮，两轮起点相同。

    `live_server` 与 `e2e_books_dir` 都是 session 级共享的，而 W 系列会创建和删除标注。
    没有隔离就有跨用例污染，而污染的表现正是 flaky——flaky 会把 Phase 3 的 soak 计数
    清零。这条断的不是「隔离 fixture 存在」，是「复位真的发生了」。

    两轮之间必须**刷新页面**，不只是复位文件：`toggleMarkerAnnotation` 走
    `getExistingMarkerIds()` 查的是 DOM 里的 `<mark>`，页面不刷新的话第二轮会命中
    第一轮留下的高亮而走进删除分支，于是「第二轮什么都没发生」和「第二轮成功创建」
    在文件长度上看起来一样。两轮 id 不同这一条把它们分开。

    自检：删掉隔离 fixture 的清理动作，第二轮的「初始为空」立刻红。
    """
    ids: List[str] = []
    for round_no in (1, 2):
        if round_no > 1:
            notes_isolation.reset()

        assert read_notes(e2e_books_dir, BOOK_ID) == [], f"第 {round_no} 轮起点不是空的"

        frame = open_reader(page, live_server, BOOK_ID, 0, "Alpha prose.")
        select_in_frame(frame, "Alpha prose")
        page.get_by_test_id("rd-anno-type-marker").click()

        records = wait_for_notes(e2e_books_dir, BOOK_ID, 1)
        assert records[0]["quote"] == "Alpha prose"
        ids.append(records[0]["id"])

    assert ids[0] != ids[1], (
        "两轮拿到同一个 id：第二轮没有真的写过一次，只是第一轮的记录还在。"
        f"ids={ids}"
    )


def test_the_next_case_starts_from_an_empty_notes_file(e2e_books_dir: Path) -> None:
    """紧跟在上一条之后：上一条留下了一条标注，这条看到的必须是空的。

    上一条用例内部的复位是它**自己**调的，所以它证明不了 fixture 的 teardown 存在。
    这条证明。它按文件内定义顺序紧跟其后（pytest 按定义顺序收集），单独跑时会平凡地
    绿——它的价值只在整文件运行里，这一点不隐瞒。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == []


_REFERENCE_RECT_JS = """
(frameEl) => {
  // 参考实现：契约 K3 的换算，一次 evaluate 里全部在浏览器侧算完。
  // 它与 helper 走的是**两条不同的路** —— helper 用 Playwright 的 bounding_box()
  // 取 iframe 偏移、用 frame.evaluate 取 range rect，这里用同一个元素句柄的
  // getBoundingClientRect() 加 contentWindow.getSelection()。
  const fr = frameEl.getBoundingClientRect();
  const sel = frameEl.contentWindow.getSelection();
  if (!sel || sel.rangeCount < 1) return null;
  const r = sel.getRangeAt(0).getBoundingClientRect();
  return {
    left: r.left + fr.left,
    top: r.top + fr.top,
    right: r.right + fr.left,
    bottom: r.bottom + fr.top,
    frameLeft: fr.left,
    frameTop: fr.top,
  };
}
"""


def test_viewport_rect_of_selection_agrees_with_an_independent_reference(
    page: Page, live_server: str
) -> None:
    """S5：一致性律——helper 与参考实现对「iframe 内 rect → 视口坐标」必须同解。

    **为什么参考实现写在用例里，而不是让 helper 去调生产的 `offsetRect`。**
    若 helper 直接调 `offsetRect`，生产端漏加 iframe 偏移这个缺陷会在 K-3b 的两侧
    **同时**发生并互相抵消，K-3b 恒绿——那正是这条要防的东西。两份独立实现是刻意的。

    **可失败性集中在 Y 轴。**（矩阵 §0 的 R2 布局事实）未开 TOC 时 `.reader-layout`
    是 flex 行，`#toc-mode` 离屏不占位，`#reader` / `#main` / `.content-container` /
    `#epub-viewer` / iframe 一路 `width: 100%` 且 `padding: 0` ⇒ `frame_rect.left ≈ 0`；
    纵向有 `.pagination-container { padding-top: 40px }` ⇒ `frame_rect.top ≥ 40`。
    所以「helper 忘了加 iframe 偏移」是一个**纯 Y 轴信号**，1px 阈值对 40px 足够灵敏。
    不要以为 X 方向也会红——那是假的。

    自检：把 helper 里的 iframe 偏移去掉，`top` / `bottom` 两个边立刻差出一个
    `frame_rect.top`。
    """
    frame = open_reader(page, live_server, BOOK_ID, 0, "Alpha prose.")
    select_in_frame(frame, "Alpha prose")

    frame_el = page.locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    reference = frame_el.evaluate(_REFERENCE_RECT_JS)
    assert reference is not None, "参考实现读不到 iframe 内的选区"

    # 元断言：这条用例的可失败性靠的是纵向偏移真的存在。它若为 0，helper 漏加偏移也
    # 不会被发现，用例就退化成一句同义反复。
    assert reference["frameTop"] >= 40, (
        f"iframe 纵向偏移只有 {reference['frameTop']}px，本条用例失去了可失败性"
        "（布局变了？见矩阵 §0 的 R2 布局事实）"
    )

    actual = viewport_rect_of_selection(page, frame)
    for edge in ("left", "top", "right", "bottom"):
        assert abs(actual[edge] - reference[edge]) < RECT_EPS_PX, (
            f"{edge} 边差了 {actual[edge] - reference[edge]:.2f}px："
            f"helper={actual[edge]:.2f} 参考={reference[edge]:.2f}；"
            f"iframe 偏移是 left={reference['frameLeft']:.2f} top={reference['frameTop']:.2f}"
        )


def test_library_lists_every_book_the_corpus_fixture_builds(page: Page, live_server: str) -> None:
    """S2：书库条数从 2 变 4 —— `lib-book-card` 多节点判别位的分支被真的走过。

    条数**从 fixture 常量取**，不写字面量。再加一本书而没更新 `E2E_BOOKS`，红的应该是
    这里；把 4 焊死，红的会是「再加一本书」这个动作本身，而修法与被改的东西无关。

    与它配套的两条护栏在别处、且都不改一行：`test_harness_smoke.py`（只读 BOOK_ID）
    与 `test_testid_dom_uniqueness.py`（书库页有界 testid 的唯一性——书库从两本变四本
    是它最可能被误伤的一次改动，而它今天不在任何组 marker 之下，没有别处会替它说话）。
    """
    page.goto(f"{live_server}/")
    expect(page.get_by_test_id("lib-book-card")).to_have_count(len(E2E_BOOKS))
