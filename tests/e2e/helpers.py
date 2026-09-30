"""E2E 共享 helpers —— 全套 W / R / K 用例只从这里取选区、读写 `notes.json`、换算几何。

二十七个函数，一个都不许在用例里各写一遍：

    select_in_frame(frame, quote, occurrence=0)   §1 的程序化选区标准路径
    read_notes(books_dir, book_id)                读回 notes.json 的 list[dict]
    seed_notes(books_dir, book_id, annotations)   预置标注（R-3 / R-6 / DEG-S1 用）
    viewport_rect_of_selection(page, frame)       iframe 内 rect → 视口坐标
    reader_frame(page, expect_text)               已在阅读器页上时等到 iframe 里有正文
    open_reader(page, base_url, book_id, i, txt)  goto ＋ reader_frame
    pathname_is(page, expected)                   等 URL 的 pathname 变成 expected
    scan_marks(frame)                             iframe 内 `<mark>` 的两种视图 ＋ body HTML
    mark_id_union(scan)                           所有 `<mark>` 的 annotation id 并集
    wait_for_notes(books_dir, book_id, count, page=)     等落库稳定到 count 条（轮询期间泵浏览器）
    wait_for_note_text(books_dir, book_id, id, s, page=) 等某条的 note_text 变成 s（PUT 路径用）
    wait_for_write_activity_settled(page)          等 `/api/notes/` 的请求真的停下来
    assert_roundtrip(page, books_dir, book_id, …) §0 的「刷新 → 高亮回到同一段文字」收尾
    assert_bystanders_unchanged(before, after, ids) 没碰过的条目逐字段原样（§0 第六条纪律）
    clear_selection_and_drain(page, frame)        清选区并等去抖窗口排空
    settle_marks(page, frame, n)                  等加载期两遍重绘落定：`<mark>` 到位且网络静默
    open_reader_settled(page, base_url, …)        open_reader ＋ settle_marks / networkidle
    open_ch0(page, base_url, expected_marks=…)    smoke 书第 0 章 ＋ 上一条（三个模块曾各抄一份）
    open_font_popover(page)                       点 `rd-rail-font` 并等面板可见
    content_style(frame, props)                   iframe body 的几项 computed style（前置守卫用）
    frame_box(page)                               iframe 元素的视口矩形（几何用例的偏移来源）
    assert_corpus_unchanged(*checks)              语料绊线：(actual, expected, message) 逐项比对
    assert_visible_book_ids(page, ids, where=…)   书库页「哪几本可见」的集合等值
    collections_file(books_dir)                   集合持久化文件的沙箱内路径
    read_collections(books_dir)                   读回集合列表（文件不存在 ⇒ []）
    http_json(url, method=…)                      打被测服务的一次裸 HTTP 调用
    delete_collections_with_prefix(base_url, p)   按名字前缀清掉集合（幂等）

**为什么集中在一处。** 这些断言的耦合面是**生产代码的实现细节**——工具条的 class 名、
`mouseup` 监听挂在哪个 document 上、`notes.json` 的顶层形状。散到 38 个用例里，
改一次生产代码就要改 38 处；集中在这里，改一处。

**后四个是 2026-09-02 的 Wave 0 上收进来的**（任务书 §0.6）。它们原先是 `baseline_1b/`
下两个模块里的私有函数，其中 `open_reader` 与 `wait_for_notes` **已经各有两份**。
剩下的九条写路径 WI 会分三波并行开工，而这四个函数是每一条都要压的那条共享路径：
重复两份时只是重复，三个 agent 同时改就会变成三份各自漂移的版本，合并时**只留下一份，
另外两条用例静默改变了它们等待的对象**。上收是把这个失败态在扇出之前消掉，不是为了省行数。
（`test_write_create_annotations.py` 里那段「刻意不抽到 helpers.py」的旧注记随之作废：
它权衡的是「省 6 行 vs 清零 soak 计数」，而 soak 计数要到 G2 才开始数，此刻清零无代价。）

**Wave 1（WI-5）在这里改了两处**，两处都是「更新路径」逼出来的，创建路径一个字没动：
`assert_roundtrip` 多了 `expected_count`（默认 1，三个既有调用点行为不变），新增
`wait_for_note_text`（PUT 改的是内容不是条数，等条数等不到任何东西）。理由分别写在
两个函数自己的 docstring 里。

**Wave 3.5（2026-09-03）上收了四个 Wave 3 产出的私有 helper**（任务书 §0.6 跨波欠账 #13），
一次纯搬家，没有一条断言改过：`reader_frame`（`open_reader` 去掉 `goto` 的那一半，`open_reader`
现在**委托给它**，两处等 iframe 的逻辑只剩一份）、`pathname_is`（等解析后的 pathname，
理由见它自己的 docstring）、`scan_marks` ＋ `mark_id_union`（`test_read_paths.py` 的
`_scan_annotations` / `_mark_id_union` 与 `test_write_overlap_and_disambiguation.py` 的
`_scan_marks` **已经重复**，合并成一个返回两种视图的扫描器）。上收的理由与 Wave 0 同形：
Wave 4 有三条 WI 并行开工，三条都要点进来 / 站内导航 / 数 `<mark>`，重复两份时只是重复，
三个 agent 同时改就会漂成三份。

**Wave 5（2026-09-04，WI-10）兑付了任务书 §0.6 跨波欠账 #25**：Wave 4 三条并行 WI 各自留下的
私有 helper 一次上收，一条断言的文本都没改，只改了名字与住址。`open_ch0` 之前**已经重复三份**
（`test_write_recolor_and_delete.py` / `test_read_presentation_anchoring.py` /
`acceptance_4b1/test_r6b_cfi_reanchoring.py`），而它背着欠账 #16 的等待纪律——每复制一份就多一处
会悄悄退化的等待；WI-13 的 `_settled` 是同一条纪律的又一次转写。现在那条纪律只住在 `settle_marks`
一处，`open_ch0` / `open_reader_settled` 都委托给它。四个模块各自的 `_assert_corpus_unchanged`
**不是同一个函数**（各查各的字面量），上收的是它们共有的形状——「一组 (实际值, 期望值, 消息)
逐项比对，不等即抛」——消息文本原样留在各模块的 `CORPUS_CHECKS` 里；这样做的代价是那几条
`assert` 不再经过 pytest 的断言改写（少一行 `assert a == b` 的自动展开），换来的是一个 grep 得到
的名字（§0 第六条纪律）。`frame_box` 是本波新增：K-3 的三条几何用例都要 iframe 的视口偏移，
`viewport_rect_of_selection` 原先自己取，现在委托过来，同一个 locator 只写一次。

**这个文件不属于任何一个组 marker，但它在 `suite_hash` 的覆盖面内**
（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md` 的哈希命令点名了它）：
改它等于改整套 baseline 的内容，soak 计数应当随之清零。

**关于下面几处 `lint-e2e-selectors: allow`。** 全部落在 iframe 边界这一类行上，一处都
没有别的。iframe 元素由 epub.js 在运行时创建，它的 document 是**用户那本书自己的**
XHTML——两边都不是我们的模板，谁都插不进 `data-testid`。放行只到 iframe 的 body 为止；
body 之内（包括外层文档里的工具条）一律回到 testid。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from playwright.sync_api import FrameLocator, Page

# `tests/e2e/helpers.py` 也被 unit lane 按文件路径加载（`tests/unit/
# test_e2e_helpers_notes_roundtrip.py`），所以模块级不许 import playwright：
# 那条用例不需要浏览器，也不该因为浏览器依赖装歪而红在一个与它无关的地方。

PathLike = Union[str, Path]

NOTES_FILENAME = "notes.json"

#: `annotations.js` 的去抖窗口（`onSelection()` 里的 `Date.now() - this.lastSelectionAt < 120`）。
#: 写成常量而不是字面量，是因为下面 `select_in_frame` 的整个时序都架在这个数上，
#: 生产端一改，红的应该是一处而不是三处。
SELECTION_DEBOUNCE_MS = 120

#: 去抖窗口之外再留的余量。epub.js 的 `selected` 是 ~250ms 一拍（实测，见下），
#: 这点余量只是防止我们卡在窗口边界上。
SELECTION_DEBOUNCE_SLACK_MS = 40

#: 各段等待的硬上限。超过就抛，带诊断，不静默继续——一个「等不到就往下走」的 helper
#: 会把「工具条没开」变成后面某条断言的莫名其妙的红。
SELECTION_TIMEOUT_MS = 8000

#: 等落库的硬上限。写路径是 fetch，点完按钮到文件出现之间隔着一次网络往返 + 一次原子写。
#: `wait_for_notes` 的默认上限，两个模块里原本各有一份同值的 `NOTES_WAIT_S`。
NOTES_WAIT_S = 8.0

#: 标注读写端点的 URL 特征。`wait_for_write_activity_settled` 用它挑出「与标注有关的那些
#: 请求」——书页自己的静态资源、epub.js 的分章抓取都不算写活动。
NOTES_ENDPOINT_MARKER = "/api/notes/"

#: 「写活动排空」的静默窗口：这么久之内没有新的 `/api/notes/` 请求、且没有在途的，
#: 才算这次动作发完了。取 500ms 是与 Playwright `networkidle` 的判定窗口同一个数量级
#: （它也是「500ms 无网络连接」），不是拍脑袋——理由见 `wait_for_write_activity_settled`。
WRITE_SETTLE_QUIET_MS = 500


# ---------------------------------------------------------------------------
# `smoke_data` 语料的坐标（`tests/fixtures/epub_corpus.py` 的 `build_epub2`）
# ---------------------------------------------------------------------------
#
# 第 0 章 `<h1>One</h1><p>Alpha prose.</p>`，第 1 章 `<h1>Two</h1><p>Beta prose.</p>`。
# 两条 quote 都**不含句点**：句点留在选区之外，是为了让「选区边界选对了没有」在断言里
# 可分辨——若拖选或程序化选区多吃一个字符，`quote` 会变成 `Alpha prose.`，往返断言当场红。
# ANCHOR 那两个则相反，**含**句点，因为它们的用途是 `to_contain_text` 的到位探针。
#
# 放在这里而不是各模块自己写一份：这是**共享 fixture 书的事实**，Wave 2 之后有三条 WI
# 会同时需要它。三份字面量各自演化的表现，是其中两条用例静默地测了另一段文字。
CH0_INDEX = 0
CH0_QUOTE = "Alpha prose"
CH0_ANCHOR = "Alpha prose."
CH1_QUOTE = "Beta prose"
CH1_ANCHOR = "Beta prose."


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


def reader_frame(page: "Page", expect_text: str) -> "FrameLocator":
    """**已经在阅读器页面上**时，等到 iframe 里真的有正文，产出 `FrameLocator`。

    先等外层壳，再等 iframe：壳都没有的话，下面的等待会白等满超时，报出来的是
    「找不到 frame」而不是「页面根本没渲染」——smoke 里已经付过一次这个学费。

    **与 `open_reader` 的区别只有一处：它不 `goto`。** 凡是「点进来」的用例（R-1 从书库点
    书卡）或站内导航的用例（R-2 的 `rd-chapter-next` 与 TOC 行两支）都必须走这一半：再
    `goto` 一次就把被测的那次导航冲掉了——用例会绿，但它证明的是 `goto` 能用，不是那个按钮
    能用。`open_reader` 反过来**委托给本函数**，等 iframe 的逻辑因此只有一份。
    """
    from playwright.sync_api import expect

    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(expect_text)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    return frame


def open_reader(
    page: "Page", base_url: str, book_id: str, chapter_index: int, expect_text: str
) -> "FrameLocator":
    """`goto` 到 `/read/{book_id}/{chapter_index}`，再等到 iframe 里真的有正文。

    等待那一半在 `reader_frame` 里，本函数只多一个 `goto`。**直接进入**的用例用这个；
    「点进来」或站内导航的用例用 `reader_frame`。
    """
    page.goto(f"{base_url}/read/{book_id}/{chapter_index}")
    return reader_frame(page, expect_text)


def pathname_is(page: "Page", expected: str) -> None:
    """等 URL 的 **pathname** 变成 `expected`，并把它作为断言。

    **为什么不用 `page.wait_for_url("**/read/cjk_data/1")`。** TOC 行是
    `<a href="#" onclick="findAndGo(…)">`，浏览器在跑完 onclick 之后还是会把 `#` 追加到
    地址上，最终 URL 是 `…/read/cjk_data/1#`。glob 匹配的是整串，`#` 一挂上去就永远不匹配，
    表现是 30s 超时而不是「章号不对」——这条弯路在 spike 阶段真的踩到过一次。
    比对 `new URL(location.href).pathname` 天然把 hash 与 query 排除在外。

    ⚠️ **URL 落后于渲染，所以本函数不能第一个断**（任务书 §0.6 跨波欠账 #12）。
    `syncLocationToUrl()` 跑在 epub.js 的 `rendered` 回调里，站内导航（`rd-chapter-next`、
    TOC 行）点完的那一刻地址栏还是**旧章号**。WI-12 的定向破坏 D4′ 实测到这件事：把 URL
    期望改成隔壁章号，两个站内分支照样绿——它们读到的确实还是旧地址；把顺序调成
    「先断正文、再断 URL」之后，同一发子弹三条全红。所以站内导航的用例要先用
    `reader_frame(page, 期望正文)` 把渲染等出来，再调本函数。本函数自己会重试到超时，
    这一点不改变上面那条顺序要求：先断 URL 就是在一个陈旧状态上做判断。
    """
    page.wait_for_function(
        "(want) => new URL(window.location.href).pathname === want",
        arg=expected,
        timeout=SELECTION_TIMEOUT_MS,
    )


# ---------------------------------------------------------------------------
# 选区
# ---------------------------------------------------------------------------

# 三段 JS 合成一个函数：定位 quote 的第 occurrence 次出现 → 写入 iframe 的 Selection
# → 在 iframe document 上派发 mouseup。全程在 child frame 内做，因为 Selection 不能跨
# browsing context（任务书 §1）。
_SELECT_JS = r"""
async (_el, [quote, occurrence, debounceMs, slackMs, timeoutMs]) => {
  const body = document.body;
  const doc = body.ownerDocument;
  const win = doc.defaultView;
  const sel = doc.getSelection();
  const ui = () => window.parent.Reader3AnnotationUI || null;
  const toolbar = () =>
    window.parent.document.querySelector('[data-testid="rd-anno-toolbar"]');

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const lastSelectionAt = () => { const u = ui(); return u ? (u.lastSelectionAt || 0) : 0; };

  // --- 1. 把 body 的文本节点串成一条连续偏移轴 ---------------------------------
  // 用 TreeWalker 而不是「找到包含 quote 的那个文本节点」：后者建不出跨元素边界的
  // Range，而 W-8b 的分段渲染恰恰要跨。这条能力在
  // tests/e2e/baseline_1b/test_harness_helpers.py 的第五个参数值上被单独证明。
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let text = "";
  while (walker.nextNode()) {
    nodes.push([walker.currentNode, text.length]);
    text += walker.currentNode.data;
  }

  const hits = [];
  for (let i = text.indexOf(quote); i !== -1; i = text.indexOf(quote, i + 1)) hits.push(i);
  if (!hits.length) {
    throw new Error(
      "select_in_frame: 章内找不到 " + JSON.stringify(quote) +
      "（body 文本 " + text.length + " 字符，开头 " + JSON.stringify(text.slice(0, 80)) + "）"
    );
  }
  const which = occurrence < 0 ? hits.length + occurrence : occurrence;
  if (which < 0 || which >= hits.length) {
    throw new Error(
      "select_in_frame: 请求第 " + occurrence + " 次出现，但 " +
      JSON.stringify(quote) + " 只出现 " + hits.length + " 次"
    );
  }
  const start = hits[which];
  const end = start + quote.length;

  // 起点要落在节点**内部**（pos < base+len），终点允许落在节点**末尾**（pos <= base+len）。
  // 两个判据不同不是笔误：起点若取到上一个节点的末尾，Range 起点就在错误的元素里，
  // 而 `handleSelectionRange` 的 `contentEl.contains(within)` 判断会因此漂移。
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

  // --- 2. 先清空选区，再等去抖窗口排空 ----------------------------------------
  // 这两步的理由是实测出来的，见本文件下方 select_in_frame 的 docstring：
  // 只要 iframe 里有一个未折叠的选区，epub.js 与 annotations.js 会以 ~250ms 一拍
  // 互相喂招，`lastSelectionAt` 永远是新的，于是「等它安静下来」永远等不到。
  // 清空选区会让 epub.js 那一侧当场停手（它的 selected 只在非折叠 range 上触发），
  // 之后 `lastSelectionAt` 才会真的开始变老。
  sel.removeAllRanges();
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const age = Date.now() - lastSelectionAt();
    if (age >= debounceMs + slackMs) break;
    if (Date.now() > deadline) {
      throw new Error(
        "select_in_frame: " + timeoutMs + "ms 内去抖窗口没有排空（age=" + age + "ms）。" +
        "清空选区应当让 epub.js 停止 selected 循环——它没停，说明那条循环的触发条件变了"
      );
    }
    await sleep(Math.max(10, debounceMs + slackMs - age));
  }

  // --- 3. 装选区 + 派发 mouseup，同一个同步 turn 里做完 -------------------------
  // 中间不许 await：一旦让出，epub.js 的 selectionchange 定时器就可能先跑，
  // 把 `lastSelectionAt` 刷新成刚才，我们紧随其后的 mouseup 就落进 120ms 窗口被丢掉。
  sel.addRange(range);
  doc.dispatchEvent(new win.MouseEvent("mouseup", { bubbles: true }));

  // --- 4. 等工具条 --------------------------------------------------------------
  for (;;) {
    const bar = toolbar();
    if (bar && bar.classList.contains("is-visible")) break;
    if (Date.now() > deadline) {
      throw new Error(
        "select_in_frame: " + timeoutMs + "ms 内 rd-anno-toolbar 没有进入 is-visible。" +
        "选区文本=" + JSON.stringify(sel.toString()) + " rangeCount=" + sel.rangeCount +
        " Reader3AnnotationUI=" + (ui() ? "present" : "absent")
      );
    }
    await sleep(10);
  }

  return { text: sel.toString(), startOffset: start, occurrences: hits.length };
}
"""


def select_in_frame(frame: "FrameLocator", quote: str, occurrence: int = 0) -> None:
    """在 epub.js 的 iframe 里选中 ``quote`` 的第 ``occurrence`` 次出现，并打开工具条。

    任务书 §1 的标准路径：child frame 内 ``document.createRange()`` → 写入 iframe 的
    Selection → 在 iframe document 上派发 ``mouseup``。真实鼠标拖选全表只保留 W-1 一条，
    其余一律走这里——拖选在 CI 上是头号 flaky 源，而 flaky 会把 soak 计数清零。

    ``occurrence`` 支持负数（``-1`` = 末次出现），W-10 的「同章重复文本消歧」靠它。

    ------------------------------------------------------------------------
    **那 120ms 去抖窗口，实测是什么样的**（2026-09-02，chromium 1234）
    ------------------------------------------------------------------------
    `annotations.js` 的 ``onSelection()`` 里有
    ``if (Date.now() - this.lastSelectionAt < 120) return;``，而 ``lastSelectionAt``
    **不是在 ``onSelection`` 里赋值的**，是在 ``handleRenditionSelection``（epub.js 自己的
    ``selected`` 事件回调）里。所以这 120ms 从来不是「mouseup 之后要等」，而是
    「epub.js 的 selected 刚跑过的话，紧随其后的 mouseup 会被丢掉」。

    实测到的三件事，前两件是我原先没料到的：

    1. **光是写入 Selection 就足以打开工具条。** 不派发任何 mouseup，`selectionchange`
       会让 epub.js 在 **~285ms** 后 fire ``selected`` → ``handleRenditionSelection``
       → 工具条打开。所以「工具条开了」并不证明我们的 mouseup 被处理过。
    2. **只要选区还在，这件事会无限循环，~250ms 一拍。** 实测 ``lastSelectionAt`` 在
       t=285 / 547 / 808 / 1066 / 1304 / 1564ms 逐拍刷新，不收敛。成因是
       ``handleRenditionSelection`` 自己会 ``removeAllRanges(); addRange(range)``，
       这又触发一次 ``selectionchange``，epub.js 于是再排一拍——生产代码里的一个
       自激循环。**后果：任何「等到 lastSelectionAt 安静下来」的写法都永远等不到**，
       而盲目派发的 mouseup 会有大约 120/250 ≈ 一半的概率落进窗口里被丢掉。
    3. **清空选区会让这个循环当场停手。** ``removeAllRanges()`` 之后
       ``lastSelectionAt`` 的年龄单调增长，1.4s 内再无更新（epub.js 的 ``selected``
       只在非折叠 range 上触发）。

    所以 helper 的时序是：**先清空选区 → 等去抖窗口排空 → 在同一个同步 turn 里装上
    新选区并派发 mouseup**。第三步不许中途 await：一旦让出，epub.js 可能先手把
    ``lastSelectionAt`` 刷新成「刚刚」，我们的 mouseup 就白派发了。实测这样做时，
    ``onSelection()`` 是**同步**跑完的——工具条在派发 mouseup 的那一行就已经可见
    （t=1ms），远早于 epub.js 的第一拍（t≈289ms）。

    这条时序**只写在这里**。让 38 条用例各写一遍 `sleep(150)`，等于把一个会变的
    生产实现细节复制 38 份。

    **留给 W 系列的一条已知事实**：本函数返回之后，那个 ~250ms 的循环会重新开始，
    每一拍都会重设 ``currentRange``（由 CFI 解析回来的等价 range）并把
    ``editingNoteId`` 清成 null（``handleSelectionRange`` 的倒数第三行）。

    ⚠️ **但编辑态实际上打不着——2026-09-02 WI-5 实测，覆盖上面这条推断的后半句。**
    任务书 §0.6 把 WI-5 单独排一波，就是要回答「编辑态用例需不需要一个新的
    drain/settle helper」。答案是**不需要**，而理由不是「点得够快」：

    * **W-7（点已有 ``<mark>`` 进编辑态）**：``onAnnotationClick`` 先
      ``removeAllRanges(); addRange(selectNodeContents(mark))``，随后
      ``openNoteEditorWithExisting`` 末尾的 ``this.noteTextarea.focus()`` 把焦点移到
      **外层文档**的 textarea 上，iframe 内的选区**当场塌成折叠态**。实测采样：
      t=60ms 时 ``selection.toString() == "Alpha prose"``，t=81ms 起恒为 ``""``。
      epub.js 的 ``selected`` 只在非折叠 range 上 emit，于是那一拍到点时什么都不发——
      整段 2s 采样里 rendition ``selected`` 事件 **0 次**、``lastSelectionAt`` 恒为
      **0**、``editingNoteId`` 恒为目标 id。**循环根本没起来，不是我们跑赢了它。**
    * **W-4（程序化选区 → Add Note）**：焦点从头到尾没进过 iframe，所以 textarea 的
      focus 不清选区，循环照跑（实测 ``lastSelectionAt`` 在 t=261 / 521ms 各刷新一拍）。
      但这一支的 ``editingNoteId`` 本来就该是 null（``openNoteEditor`` 首行就置 null），
      而 ``currentRange`` 在整段采样里恒为 ``"Alpha prose"``——与 WI-4 在
      ``test_write_create_annotations.py`` 里量到的结论一致。

    合起来：**两条编辑/笔记路径都不需要额外的排空动作**。Wave 2 之后再有用例碰
    ``editingNoteId``，先照这条结论走；真要变，变的会是 ``openNoteEditorWithExisting``
    末尾那个 ``focus()``，而不是这里的时序。
    """
    body = frame.locator("body")  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    body.evaluate(
        _SELECT_JS,
        [
            quote,
            occurrence,
            SELECTION_DEBOUNCE_MS,
            SELECTION_DEBOUNCE_SLACK_MS,
            SELECTION_TIMEOUT_MS,
        ],
    )


def clear_selection_and_drain(page: "Page", frame: "FrameLocator") -> None:
    """清掉 iframe 内的选区，并等 `onSelection` 的去抖窗口排空。

    **当前无调用方（2026-09-05 审计 #3 之后）。** W-1 曾用它在「量完几何」与「开始拖」之间
    清场，但那条路本身就是洞：它清选区、却清不掉 `Reader3AnnotationUI.currentRange`，于是
    一条完全坏掉的真实拖选路径仍能拿陈旧的程序化 range 把标注建出来。W-1 改成用**游离
    range**（`doc.createRange()`，从不 `addRange`）量几何，压根不触发 `onSelection`，也就
    不需要事后清场。保留本函数是因为 `test_write_create_annotations.py` 与
    `test_kernel_actions_and_url.py` 的散文仍引它解释那条被废弃的旧路；真要删，连同那两处
    散文一起删。

    以下是它原本的时序理由，仍然属实：`select_in_frame`
    返回之后，`handleRenditionSelection` 的自持循环会以 ~250ms 一拍持续刷新
    `lastSelectionAt`（时序实测记在上面 `select_in_frame` 的 docstring 里）；此时直接
    拖选，我们的 `mouseup` 有约 120/250 的概率落进 `annotations.js:695` 的守卫里被丢掉。
    清空选区让 epub.js 那一侧当场停手（它的 `selected` 只在非折叠 range 上触发），窗口
    才会真的开始变老。

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


# ---------------------------------------------------------------------------
# 页面：等加载期的双重重绘落定（任务书 §0.6 欠账 #16 的等待纪律，**唯一定义处**）
# ---------------------------------------------------------------------------


def settle_marks(page: "Page", frame: "FrameLocator", expected_marks: int) -> None:
    """等到标注重绘**全部**落定：`<mark>` 数量到位，且网络静默。

    ⚠️ **光等 `<mark>` 数量不够：一次页面加载会跑两遍 `loadAndRender()`。**
    实测（2026-09-03，chromium，`test_write_recolor_and_delete.py` 约四成 flaky 的根因）：
    `annotations.js` 的模块尾部对同一次章节加载挂了**两个互相独立的重绘触发器**——

      1. `Reader3Epub.onContentsReady(...)` 回调里**当场**调一次 `ui.renderer.loadAndRender()`；
      2. `window.addEventListener("reader3:content:rendered", scheduleRefresh)`，而
         `scheduleRefresh` 是一个 **80ms 去抖**的 `loadAndRender()`；
         `epub-renderer.js` 在 `rendered` 里必发 `reader3:content:rendered`。

    于是每次开章都有**第二遍**重绘，落在第一遍之后约 80ms ＋ 一个 `/api/notes/` 往返。
    第二遍照样跑 `clearExistingAnnotationMarks()` → `parent.normalize()`，把 `<mark>` 拆掉、
    合并文本节点，**再按同样的数据重建出数量完全相同的 `<mark>`**。所以 `to_have_count`
    在第一遍就已经满足，结构上看不见第二遍。两类用例各有各的受害方式：

    * **建选区的用例**：紧接着 `select_in_frame` 装上的 live `Range` 会在第二遍的
      `normalize()` 里被就地折叠成空 range（实测 `range.toString() === ""`），
      `getExistingAnnotationIds` 一条都找不到 ⇒ `toggleAnnotation` 一次 DELETE 都不发，
      直接走 `createAnnotation` 并带着空 `quote` 吃一个 400。
    * **只读快照的用例**（`scan_marks` 是一次性快照，不像 `expect()` 会自动重试）：
      两遍之间有一个 `<mark>` 被拆光的窗口，快照落进去就是 `texts == []`、`ids` 空集，
      判据会以一种和真缺陷无法区分的形状红。

    **判据取「网络静默」而不是别的**：第二遍重绘唯一的外部可观测事件就是它那次 notes
    fetch，而 80ms 的去抖窗口远小于 `networkidle` 的 500ms 判定窗口，所以这次 fetch 一定
    落在窗口内、一定会把它顶开；`render()` 又是在 `resp.json()` 之后**同步**跑完的，远早于
    那 500ms 结束。`networkidle` 落定 ⇒ 两遍重绘都已经跑完。这不是 sleep——等不到静默会
    超时而红，等到了就是一个确定的终态。

    `expected_marks == 0` 那一支其实不受影响（没有 `<mark>` 可拆），但判据统一写在这里比
    按参数分岔可靠——「这一次到底有没有 mark」不该是调用点要想的事。数量断言在静默前后各
    断一次——断的是同一件事，只是第二次断在一个不会再变的状态上。

    合并自 `test_read_chapter_change_and_search.py` 的 `_settled` 与三份 `_open_ch0` 的
    等待段（任务书 §0.6 欠账 #25）。
    """
    from playwright.sync_api import expect

    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(expected_marks)
    page.wait_for_load_state("networkidle")
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(expected_marks)


def open_reader_settled(
    page: "Page",
    base_url: str,
    book_id: str,
    chapter_index: int,
    expect_text: str,
    *,
    expected_marks: Optional[int] = None,
) -> "FrameLocator":
    """`open_reader` ＋ 等两遍加载期重绘跑完（见 `settle_marks`）。

    ``expected_marks`` 给了就走 `settle_marks`（计数 → 静默 → 计数）；不给只等网络静默——
    那是「本章有几条标注不是本用例关心的事」时的形态（R-6b 与 K-3 的几何用例都是这样）。
    """
    frame = open_reader(page, base_url, book_id, chapter_index, expect_text)
    if expected_marks is None:
        page.wait_for_load_state("networkidle")
    else:
        settle_marks(page, frame, expected_marks)
    return frame


def open_ch0(
    page: "Page", base_url: str, *, expected_marks: Optional[int] = None
) -> "FrameLocator":
    """打开（或刷新）smoke 书的第 0 章，并**等到重绘全部落定**。

    等这一下不是防御性等待，是必需的前置条件：`getAnnotationMetaForRange` 需要 DOM 里真的
    有 `<mark>`；而第二遍 `loadAndRender()` 的重绘会拆 `<mark>` 并 `normalize()` 文本节点，
    任何早于它建好的选区都会在那一刻失效（完整推导在 `settle_marks` 的 docstring）。

    `BOOK_ID` 从 `conftest` 里**函数内**取：本文件被 unit lane 按路径加载，模块级不能碰
    `conftest`（理由见文件头）；而 smoke 书的目录名只该有一个定义处，这里不抄第二份。
    """
    from conftest import BOOK_ID  # type: ignore[import-not-found]

    return open_reader_settled(
        page, base_url, BOOK_ID, CH0_INDEX, CH0_ANCHOR, expected_marks=expected_marks
    )


def open_font_popover(page: "Page") -> None:
    """点 `rd-rail-font` 打开字体面板，并等它真的可见。

    三个表现层参数的控件都住在这个面板里。面板对**面板内部**的点击不关闭
    （`reader.html` 的 document click 处理器判的是 `popup.contains(e.target)`），所以整条
    用例只开一次；一步一开会把「上一步是不是把面板关掉了」这件事藏进重开动作里。
    """
    from playwright.sync_api import expect

    page.get_by_test_id("rd-rail-font").click()
    expect(page.get_by_test_id("rd-font-popover")).to_be_visible()


_CONTENT_STYLE_JS = (
    "(body, props) => { const c = getComputedStyle(body); const out = {};"
    " for (const p of props) out[p] = c[p]; return out; }"
)


def content_style(frame: "FrameLocator", props: Sequence[str]) -> Dict[str, str]:
    """iframe body 上那几项 computed style。**只用于前置守卫，不是 Law 的判据。**

    读的是「表现层变更有没有真的落到被测的那一层上」。没有它，一个像主题四态那样**根本
    没有监听器**的控件会让整条参数静默空转——点四下、什么都不发生、然后断言标注没变。
    """
    return frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
        _CONTENT_STYLE_JS, list(props)
    )


def frame_box(page: "Page") -> Dict[str, float]:
    """epub.js 那个 iframe 元素的视口矩形（Playwright `bounding_box()`，键是 x/y/width/height）。

    它是 K-3 全部几何换算的偏移来源：`annotations.js` 的 `offsetRect` 把 iframe 内 rect 加上
    `frameEl.getBoundingClientRect()`，这里用 Playwright 的 `bounding_box()` 独立取同一个量。
    未开 TOC 时实测 `{x: 0, y: 40, width: 1280, height: 640}`（1280×720 视口）：横向偏移是 **0**，
    纵向偏移来自 `.pagination-container { padding-top: 40px }`。
    """
    frame_el = page.locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    box = frame_el.bounding_box()
    if box is None:
        raise AssertionError("frame_box: iframe 元素没有 bounding box（还没渲染？）")
    return box


# ---------------------------------------------------------------------------
# 读 DOM：iframe 内的 `<mark>`
# ---------------------------------------------------------------------------

# **为什么在 evaluate 里读 `dataset.annotationIds`，而不是 `getAttribute("data-annotation-ids")`。**
# 后者会被 `scripts/lint_e2e_selectors.py` 的 `LOCATOR_CALL_RE` 当成一处选择器扫到——它匹配
# `.getAttribute(` 后面那个字符串实参，于是把属性名当成选择器，报「含非 data-* 属性选择器
# 的部分」。那是一次**误报**，但让它误报再逐行 `# lint-e2e-selectors: allow`，等于拿这条 lint
# 的信噪比去换一行方便；`dataset` 是等价 API，更便宜。
#
# 这个取舍原先在 `test_read_paths.py` 与 `test_write_overlap_and_disambiguation.py` **各写
# 了一遍**（两处都是各自独立发现的）。编码在这里一次，是为了下一个要数 `<mark>` 的模块不必
# 第三次重新发现它——它一旦被重新发现，多半是在「为什么 lint 红了」那一步，而不是在读注释。
_SCAN_MARKS_JS = r"""
() => {
  const body = document.body;
  const doc = body.ownerDocument;

  // --- 视图一：body 文本轴 ＋ 逐文本节点的分段 --------------------------------
  // 位置一律用「body 文本里的字符偏移」表达，绝不用「第几个 `<mark>`」：章内只有一个
  // `<mark>` 时，「第 0 个 `<mark>` 的文本等于 quote」是一句恒真，一个「永远高亮第一处」
  // 的实现照样绿（W-10 靠偏移把它咬住）。
  //
  // 走 TreeWalker(SHOW_TEXT) 而不是 `body.textContent`：两者在今天的语料上同解，但前者与
  // 生产端 `buildTextIndex` 的取文本方式一致，不会因为将来有人往 body 里注入 `<style>`
  // 而两边错位。
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const marks = [];
  let text = "";
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const start = text.length;
    text += node.data;
    const parent = node.parentElement;
    // `closest` 取的是**最内层**的那个 `<mark>`：applySegments 产出的三段是兄弟节点，
    // 各含一个文本节点，于是这里一个文本节点恰好对应一段，顺序即 DOM 顺序。
    const host = parent ? parent.closest('[data-testid="rd-anno-span"]') : null;
    if (!host) continue;
    let ids = null;
    try {
      ids = JSON.parse(host.dataset.annotationIds || "[]");
    } catch (err) {
      ids = null;  // 解析不出来就交给 Python 侧报，别在这里吞掉
    }
    marks.push({ text: node.data, start, end: start + node.data.length, ids,
                 raw: host.dataset.annotationIds });
  }

  // --- 视图二：逐 `<mark>` 元素 -------------------------------------------------
  // 与视图一的分段不是一回事：视图一按文本节点切，视图二按元素数。R-3 的「文本序列 ==
  // ['Alpha prose']」要的是后者——「同一段文字渲染了两遍」在元素数上显形，在分段上不一定。
  const spans = Array.from(body.querySelectorAll('[data-testid="rd-anno-span"]'));

  return {
    text,
    marks,
    texts: spans.map((m) => m.textContent),
    // 每个 `<mark>` 的 id 列表原样带回；解析不出来就把生串交给 Python 侧报，别在这里吞。
    ids: spans.map((m) => m.dataset.annotationIds || null),
    // 「某个 id 不出现在 DOM 的任何位置」这条判据要的是整份 HTML，不只是 `<mark>` 上那些
    // 属性——一个把 id 写进别的属性、或写进注释里的实现，同样算「渲染了它」。
    html: body.innerHTML,
  };
}
"""


def scan_marks(frame: "FrameLocator") -> Dict[str, Any]:
    """iframe 内 `rd-anno-span` 的**两种视图**，外加 body 的整份 HTML。

    返回::

        {
          "text":  str,                 # body 的连续文本轴（TreeWalker(SHOW_TEXT) 拼起来的）
          "marks": [{"text", "start", "end", "ids", "raw"}, …],   # 逐文本节点的分段，DOM 顺序
          "texts": [str, …],            # 逐 `<mark>` 元素的 textContent
          "ids":   [str | None, …],     # 逐 `<mark>` 元素的 `data-annotation-ids` 生串
          "html":  str,                 # body.innerHTML
        }

    ``marks`` 里的 ``start`` / ``end`` 是在 ``text`` 上的字符偏移；重叠标注被
    ``applySegments`` 切成的每一段各占一项。``texts`` / ``ids`` 则是**按元素**数，
    两种视图在「一个 `<mark>` 含多个文本节点」时会分叉——所以两种都带回来，由调用方按
    自己的判据挑，而不是在这里替它选一个。

    合并自 `test_read_paths.py` 的 `_scan_annotations` 与
    `test_write_overlap_and_disambiguation.py` 的 `_scan_marks`（任务书 §0.6 欠账 #13）。
    """
    return frame.locator("body").evaluate(_SCAN_MARKS_JS)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板


def mark_id_union(scan: Dict[str, Any]) -> Set[str]:
    """所有 `<mark>` 的 `data-annotation-ids` 并集（按元素，即 ``scan["ids"]``）。解析失败当场抛，不吞。

    **形状必须是「字符串数组」，不是「任何 JSON」**（2026-09-05 审计 D1）。早先的写法是
    `json.loads(raw)` 之后直接 `set(parsed)`，而 `set()` 对**字典**取的是它的**键**——于是
    一个把属性写成 ``{"a1": 0, "a2": 0}`` 的生产实现（对象而不是数组）会让每一条读路径
    判据照常绿，因为并集恰好等于那几个 id。契约是数组（`annotations.js` 写的是
    `JSON.stringify(ids)`，`ids` 是一个 `Array<string>`），所以这里把契约本身断出来：
    不是数组 ⇒ 抛，元素不是字符串 ⇒ 抛，两条消息都点名**实际服务到 DOM 上的那一串**。

    这条守卫钉在 `tests/unit/test_e2e_helpers_notes_roundtrip.py`（unit lane，纯 Python）。
    """
    union: Set[str] = set()
    for raw in scan["ids"]:
        if raw is None:
            raise AssertionError(
                "某个 `rd-anno-span` 上没有 `data-annotation-ids`。"
                "`render()` / `applySegments` 改过这个属性的写法？"
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"`data-annotation-ids` 不是合法 JSON：{raw!r}（{exc}）"
            ) from exc
        if not isinstance(parsed, list):
            raise AssertionError(
                f"`data-annotation-ids` 必须是 JSON **数组**，实际服务到 DOM 上的是一个 "
                f"{type(parsed).__name__}：{raw!r}。"
                "（`set()` 对字典取的是键，所以一个键恰好是那些 id 的对象会静默地骗过并集判据。）"
            )
        bad = [item for item in parsed if not isinstance(item, str)]
        if bad:
            raise AssertionError(
                f"`data-annotation-ids` 数组里有非字符串元素 {bad!r}，实际服务到 DOM 上的是 {raw!r}。"
                "（id 是字符串；数字/None/嵌套结构进了并集之后，后面的集合比对会以一种"
                "与真缺陷无法区分的形状红。）"
            )
        union |= set(parsed)
    return union


# ---------------------------------------------------------------------------
# notes.json
# ---------------------------------------------------------------------------


def wait_for_write_activity_settled(
    page: "Page",
    *,
    quiet_ms: int = WRITE_SETTLE_QUIET_MS,
    timeout_ms: int = SELECTION_TIMEOUT_MS,
) -> int:
    """等到页面**不再发标注写请求**：`quiet_ms` 内没有新的 `/api/notes/`，且没有在途的。
    返回这段观察期内看到的请求数（做诊断用）。

    **为什么不是 `page.wait_for_load_state("networkidle")`**（2026-09-05 实测，这条是本函数
    存在的全部理由）。`networkidle` 是一个**文档生命周期事件**：它对当前文档只到达一次，
    此后页面里再发多少 `fetch` 都不会把它重新打开。实测在阅读器页上点完「marker」之后立刻
    调它，**0.001s 就返回**，而那一刻 `notes.json` 里还是 **0 条**——它连本次点击的那一次写
    都没等到，更不用说等一次延迟补发。`settle_marks` 里那一处仍然有效，因为它紧跟在
    `goto` 之后，等的是**新文档**第一次到达 networkidle。两处不能互相替代。

    所以这里自己数：从 Playwright 的 `request` / `requestfinished` / `requestfailed` 事件
    里挑出 URL 含 `/api/notes/` 的那些，维护「在途数」与「最后一次活动的时刻」，等到
    在途为 0 且静默超过 `quiet_ms`。它观察的是**网络层**，而不是 `window.fetch`——一个
    在页面加载时就把 `fetch` 抓在手里的重复写会绕过任何 JS 层的探针，绕不过这里。

    **这不是 sleep。** 判据是一个可观测条件（「在途为 0 且静默 `quiet_ms`」），循环里的
    50ms 只是轮询节拍（与 `wait_for_notes` 同款），等不到就抛。静默窗口本身是有限的，
    所以它挡的是「延迟到 `quiet_ms` 以内补发」的重复写；比这更长的延迟没有任何有界等待
    能覆盖，那属于 soak 的时间尺度，不属于一条用例的收尾。
    """
    marker = NOTES_ENDPOINT_MARKER
    state = {"inflight": 0, "seen": 0, "last": time.monotonic()}

    def _started(request: Any) -> None:
        if marker in request.url:
            state["inflight"] += 1
            state["seen"] += 1
            state["last"] = time.monotonic()

    def _ended(request: Any) -> None:
        if marker in request.url:
            state["inflight"] = max(0, state["inflight"] - 1)
            state["last"] = time.monotonic()

    page.on("request", _started)
    page.on("requestfinished", _ended)
    page.on("requestfailed", _ended)
    try:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            quiet_s = time.monotonic() - state["last"]
            if state["inflight"] == 0 and quiet_s >= quiet_ms / 1000:
                return int(state["seen"])
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"{timeout_ms}ms 内 {marker} 的请求没有停下来："
                    f"在途 {state['inflight']} 个，本段观察共 {state['seen']} 次请求。"
                    "（页面在反复重发写请求？）"
                )
            # `wait_for_timeout` 而不是 `time.sleep`：同步 API 只有在等 Playwright 自己的
            # 操作时才会把浏览器那边的事件泵到本进程，纯 Python 的 sleep 收不到上面那三个
            # 回调，静默判据会因此永远成立。
            page.wait_for_timeout(50)
    finally:
        page.remove_listener("request", _started)
        page.remove_listener("requestfinished", _ended)
        page.remove_listener("requestfailed", _ended)


def _notes_path(books_dir: PathLike, book_id: str) -> Path:
    return Path(books_dir) / book_id / NOTES_FILENAME


def read_notes(books_dir: PathLike, book_id: str) -> List[Dict[str, Any]]:
    """读回一本书的标注，``list[dict]``。

    文件不存在 ⇒ ``[]``。这是 `notes_service.load_annotations` 唯一会返回空列表的
    合法状态，也是隔离 fixture 的缺省态；在这里对它抛错，会逼每个调用点包一层
    try，而那层 try 迟早会把真正的读失败一起吞掉。

    读的是**原始 JSON**，不经过 `Annotation.from_dict`：用例要断的是磁盘上到底写了
    什么（比如「``color`` 字段确实是 green」），而 `from_dict` 会给缺省值补默认——
    补完之后「写对了」和「没写但默认值恰好对」就分不开了。
    """
    path = _notes_path(books_dir, book_id)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["annotations"])


def wait_for_notes(
    books_dir: PathLike, book_id: str, count: int, *, page: "Page"
) -> List[Dict[str, Any]]:
    """等 `notes.json` 稳定到 `count` 条，超时即红并把实际内容打出来。

    这不是「重试掩盖 flaky」：落库是异步的（fetch → 服务端原子写），不等就是在断言一个
    还没发生的事件。等的是**一个确定的终态**，不是「多试几次也许就成了」——终态不对时它
    照样红，且把实际条目原样贴出来。

    ⚠️ 它一观察到 `len == count` 就返回，所以读到的可能是**中间态**：若一次动作写了两次，
    50ms 的轮询有一定概率正好落在两次写之间的窗口里。要断「恰好 N 条」必须在一个确定的
    终态上再断一次（`assert_roundtrip` 就是在刷新之后补的那一次）。

    **轮询节拍是 `page.wait_for_timeout(50)`，不是 `time.sleep`（009 #49，019 WI-2）。**
    同步 Playwright 的 route 回调只在主线程调进 Playwright 时才被派发，而 conftest 给每个
    context 挂了 `**/*` 出网闸：纯 Python 的 sleep 轮询期间，那次写卡在闸的回调上出不了门，
    8s 等满判超时——v6 归因臂「上线前排队 8007–8151ms」的慢请求簇就是它。`page` 因此是
    **必填、仅限关键字**：漏传是 TypeError，不会静默退回 sleep。8s 的预算不变（row 49：
    不许只把 8s 调大）。机制用例：`tests/e2e/test_disk_poll_pumps_inflight_write.py`。
    """
    deadline = time.monotonic() + NOTES_WAIT_S
    seen: List[Dict[str, Any]] = []
    while time.monotonic() < deadline:
        seen = read_notes(books_dir, book_id)
        if len(seen) == count:
            return seen
        page.wait_for_timeout(50)
    raise AssertionError(
        f"{NOTES_WAIT_S}s 内 notes.json 没有稳定到 {count} 条，实际 {len(seen)} 条：{seen}"
    )


def wait_for_note_text(
    books_dir: PathLike, book_id: str, note_id: str, expected_text: str, *, page: "Page"
) -> Dict[str, Any]:
    """等 ``note_id`` 那一条的 ``note_text`` 变成 ``expected_text``，返回该条。

    **为什么 `wait_for_notes` 在更新路径上等不到东西。** 它等的是**条数**，而
    PUT `/api/notes/{book}/{chapter}/{id}` 是原地改一条：条数从头到尾不变，所以
    `wait_for_notes(..., 2)` 会在第一次轮询就带着**旧内容**返回。那正是 §0 第四条纪律
    点名的「把中间态当成终态」——只不过这一次中间态和终态的**长度相同**，连概率性都
    谈不上，是必然读到旧值。判据必须落在被改的那个量上。

    等的仍然是一个确定的终态，不是重试：读不到就抛，并把**超时那一刻**盘上的样子贴出来。

    **超时诊断读的是当下，不是最后一次看见。** 早先的写法把每次轮询看到的那条存进
    `seen`，超时再打印 `seen`——于是「更新被实现成删了重建」这种缺陷会报成
    「note_text 没有变成 X，当前是 <旧记录>」，而那条旧记录**此刻根本已经不在盘上了**。
    2026-09-03 的定向破坏（WI-5 的 D1）就是这么被误导了一轮：失败消息把人指向「PUT 没生效」，
    真相是「PUT 生效了，但换了个 id」。超时后重读一次，分两种情况报。

    W-9（CJK 上重复一遍 W-7）与今后任何走 PUT 的用例都压这条路径，所以它在 helpers 里，
    不在某个用例模块里。

    轮询节拍与 `wait_for_notes` 同为 `page.wait_for_timeout(50)`（理由见那里的 docstring）。
    """
    deadline = time.monotonic() + NOTES_WAIT_S
    while time.monotonic() < deadline:
        for record in read_notes(books_dir, book_id):
            if record.get("id") == note_id:
                if record.get("note_text") == expected_text:
                    return record
                break
        page.wait_for_timeout(50)

    final = read_notes(books_dir, book_id)
    current = next((r for r in final if r.get("id") == note_id), None)
    if current is None:
        raise AssertionError(
            f"{NOTES_WAIT_S}s 后 id={note_id!r} 这一条**已经不在 notes.json 里了**——"
            "更新路径把「改一条」实现成了「删掉再建一条新的」。"
            f"现存的 id：{[r.get('id') for r in final]}"
        )
    raise AssertionError(
        f"{NOTES_WAIT_S}s 内 {note_id} 的 note_text 没有变成 {expected_text!r}，"
        f"当前是 {current!r}"
    )


def seed_notes(books_dir: PathLike, book_id: str, annotations: Sequence[Any]) -> None:
    """预置一批标注，落成**生产代码认得的** `notes.json`。

    ``annotations`` 可以是 `Annotation` 实例，也可以是 dict（dict 里缺 ``book_id``
    时用参数补上）。

    **为什么调生产的 `save_annotations`，而不是自己 `json.dump`。**
    `notes.json` 的顶层是一个**对象**
    （``{"schema_version": …, "book_id": …, "annotations": [...]}``），不是裸数组。
    helper 若图省事写成裸数组，`load_annotations` 会以 `NotesFileError` 拒绝整份文件，
    于是每一个 notes 端点 500 —— 而用例侧看到的表现只是「R-3 / R-6 / DEG-S1 莫名其妙
    地红」，离真正的原因隔着一整条请求链。走生产的写入口，这种漂移在定义上不可能发生。

    这条往返恒等钉在 `tests/unit/test_e2e_helpers_notes_roundtrip.py`（unit lane，
    不需要浏览器）。
    """
    from reader3_app.models.annotations import Annotation
    from reader3_app.notes_service import save_annotations

    records: List[Annotation] = []
    for item in annotations:
        if isinstance(item, Annotation):
            records.append(item)
            continue
        if isinstance(item, Mapping):
            data = dict(item)
            data.setdefault("book_id", book_id)
            records.append(Annotation.from_dict(data))
            continue
        raise TypeError(f"seed_notes 只收 Annotation 或 dict，收到 {type(item).__name__}")

    _notes_path(books_dir, book_id).parent.mkdir(parents=True, exist_ok=True)
    save_annotations(str(books_dir), book_id, records)


# ---------------------------------------------------------------------------
# 往返
# ---------------------------------------------------------------------------


def _pick_target(
    records: List[Dict[str, Any]], quote: str, expected_type: str
) -> Dict[str, Any]:
    """从落库列表里挑出「本次动作针对的那一条」。

    **单条时原样返回 `records[0]`，一个字段都不看。** 这是刻意的：W-1 / W-2 / W-3 依赖
    `assert_roundtrip` 里那两条逐字段诊断（「落库的 type 是 X 不是 Y」「落库的 quote 是
    X 不是 Y」）。若这里先按 type 过滤，一个「按了 wavy 却写成 underline」的缺陷会变成
    「找不到匹配的条目」——同样红，但把人指向错的地方。

    多条时才按 (quote, type) 挑，且要求**恰好一个**匹配：挑不出唯一的一条，说明用例给的
    坐标本身就不能定位到目标，此刻抛比后面断在错的条目上强。
    """
    if len(records) == 1:
        return records[0]
    matches = [r for r in records if r.get("quote") == quote and r.get("type") == expected_type]
    if len(matches) != 1:
        raise AssertionError(
            f"在 {len(records)} 条落库记录里，quote={quote!r} 且 type={expected_type!r} 的"
            f"有 {len(matches)} 条（要求恰好 1 条）。完整列表：{records}"
        )
    return matches[0]


def assert_roundtrip(
    page: "Page",
    books_dir: PathLike,
    book_id: str,
    quote: str,
    anchor: str,
    expected_type: str,
    expected_count: int = 1,
) -> Dict[str, Any]:
    """§0 的往返断言，全部写路径用例共用的收尾：**刷新** → 高亮回到同一段文字上。

    顺序是刻意的：先读盘（此时页面还没刷新，读到的是服务端真的写下去的东西），再刷新，
    再断 DOM。反过来先刷新再读盘的话，「盘上没有但 JS 还记得」这个失败态会被刷新动作
    自己抹掉，而那正是本纪律要抓的东西。

    ``expected_count`` 是**本章应当存在的标注总数**，默认 1 —— 也就是创建路径用例的
    今日行为，W-1 / W-2 / W-3 三个调用点一个字都不用改。W-7（编辑已有笔记，同章还有一条
    旁观标注）传 2。**它不是「至少几条」**：终态断的仍是等号，只是等号右边由调用方给出。

    ⚠️ ``expected_count > 1`` 时本函数只保证「目标那条往返成功、总数没变」。**同章其他
    条目有没有被顺手改掉，这里不管**——那是调用方要断的守恒律（见 W-7 的整字典等值）。
    把旁观条的判据塞进这里会让它对每个调用点都变成一句恒真。

    ------------------------------------------------------------------------
    **刷新之前必须先等写活动排空**（2026-09-05 审计 D2）
    ------------------------------------------------------------------------
    本函数存在的第二个理由，是下面那句「终态恰好 N 条」——它要抓的是「一次动作写了不止
    一条」。而 2026-09-05 之前，`wait_for_notes` 一看到中间态就返回，紧接着就
    `page.reload()`：**导航会把页面上还没发出的那次重复写整个取消掉**（pending 的
    `setTimeout` 连同它的 `fetch` 随旧文档一起销毁）。于是一条「点一下，稍后再补发一次
    POST」的缺陷，会因为我们刷新得够快而**在盘上从未出现过第二条**，判据照常绿——
    这个函数在它最该咬人的那一类缺陷上恰好是盲的。

    修法是在刷新之前等 `wait_for_write_activity_settled(page)`：`/api/notes/` 的请求在途数
    归零、且静默满 500ms。重复写全都表现为一次多余的 `/api/notes/` 往返，只要它落在这个
    窗口内就会把窗口顶开，我们于是等到它落盘之后才刷新，随后那句
    `len(...) == expected_count` 当场红。

    ⚠️ **这里不能用 `page.wait_for_load_state("networkidle")`**——2026-09-05 实测它在这个
    位置 0.001s 就返回（`networkidle` 是文档生命周期事件，对当前文档只到达一次，页面之后
    再发多少 fetch 都不会重开它），那一刻盘上还是 0 条。完整实测记在
    `wait_for_write_activity_settled` 的 docstring 里。

    静默之后**在刷新前先断一次条数**，而不是只留刷新后那一次：两次断的是同一件事，但前
    一次断在「刷新还没来得及抹掉任何东西」的时刻上，失败消息因此能把人指向写路径本身。
    刷新后那一次照旧保留——它多守一件事：刷新期间的重绘不许再补写一条。
    """
    from playwright.sync_api import expect

    records = wait_for_notes(books_dir, book_id, expected_count, page=page)
    record = _pick_target(records, quote, expected_type)
    assert record["type"] == expected_type, (
        f"落库的 type 是 {record['type']!r}，不是按下的那个按钮对应的 {expected_type!r}："
        f"`handleAction` 的 action 名与模板 `data-action` 取值失配？完整条目：{record}"
    )
    assert record["quote"] == quote, (
        f"落库的 quote 是 {record['quote']!r}，不是选中的 {quote!r}。"
        f"（生产端取 `buildTextIndex(...).text.slice(s, e)`，多吃/少吃一个字符都会在这里显形）"
    )

    # 见上面 docstring 末节：先等写活动排空，再刷新。顺序反过来，刷新会替一个「延迟补发
    # 第二次写」的缺陷把证据销毁。
    requests_seen = wait_for_write_activity_settled(page)
    before_reload = read_notes(books_dir, book_id)
    assert len(before_reload) == expected_count, (
        f"写活动排空之后、刷新之前，盘上不是恰好 {expected_count} 条，而是 {len(before_reload)} 条——"
        f"这次动作发了不止一次写（`wait_for_notes` 读到的是中间态；本次收尾期间观察到 "
        f"{requests_seen} 次 {NOTES_ENDPOINT_MARKER} 请求）：{before_reload}"
    )

    page.reload()
    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(anchor)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    if expected_count == 1:
        # 不带判别位是刻意的：strict 模式下「章内冒出第二个 `<mark>`」会当场报
        # strict violation，而那正是「一次动作写了不止一条」在 DOM 侧的表现之一。
        span = frame.get_by_test_id("rd-anno-span")
    else:
        # 本章预期就有多个 `<mark>`，strict 单例判据在这里是错的判据，不是更严的判据。
        # 判别位 `data-annotation-id` 在 ADR-0014 的闭合清单内（见 lint_e2e_selectors）。
        target_id = record["id"]
        span = frame.locator(
            f'[data-testid="rd-anno-span"][data-annotation-id="{target_id}"]'
        )
    # `to_have_text` 会自动等待——刷新后的高亮要等 `loadAndRender()` 跑完才挂上。
    # 用它而不是先 `to_be_visible()` 再取值：后者会在「`<mark>` 已挂但文本错」时先绿一次，
    # 把失败推迟到下一行，报出来的诊断信息也更差。
    expect(span).to_have_text(quote)
    assert span.text_content() == quote, (
        f"刷新后 `<mark>` 覆盖的文本是 {span.text_content()!r}，不是创建时选中的 {quote!r}"
    )

    # 「恰好 1 条」要在**终态**再断一次，上面 `wait_for_notes` 那次不算数。
    #
    # 2026-09-02 实测：给 `createAnnotation` 加一次重复 POST（两次写相隔 7ms）后跑三条，
    # 结果是 **2 红 1 绿**——wavy 那条绿了。两个原因叠在一起：
    #   1. `wait_for_notes` 一观察到 `len == 1` 就返回，50ms 的轮询有一定概率正好落在
    #      两次写之间的窗口里，把中间态当成终态；
    #   2. DOM 侧兜不住：两条**完全重合**的标注在 `render()` 的分段里合并成一个 `<mark>`，
    #      所以 strict 模式不会因为「两个 rd-anno-span」而报错。
    # 于是「一次点击写两条」这条缺陷在原写法下是**概率性漏检**，而不确定性正是 G2 禁的东西。
    # 刷新已经完成，第二次写早就落盘了，此刻读到的就是终态。
    settled = read_notes(books_dir, book_id)
    assert len(settled) == expected_count, (
        f"终态不是恰好 {expected_count} 条，而是 {len(settled)} 条——"
        f"一次动作写了不止一条，或顺手删掉了别的：{settled}"
    )
    settled_target = _pick_target(settled, quote, expected_type)
    assert settled_target["id"] == record["id"], (
        f"终态那条的 id 与落库时读到的不是同一条：{settled_target['id']} != {record['id']}"
    )
    return record


def assert_bystanders_unchanged(
    before: Sequence[Dict[str, Any]],
    after: Sequence[Dict[str, Any]],
    changed_ids: Collection[str],
) -> None:
    """断「这次动作没碰过的条目」**逐字段原样还在**。`changed_ids` 是本次动作允许动的那些 id。

    **为什么它不在 `assert_roundtrip` 里。** 那个函数是所有写路径用例共用的收尾，而
    「同章还有哪些条目、其中哪些该变」是每条用例各自的事——塞进共用收尾就得对每个调用点
    都成立，那它只能退化成一句恒真。分开之后，本函数的每次调用都由调用方给出「哪些该变」，
    这个参数正是它不空转的原因。

    **为什么值得单独一个函数，而不是各用例写一行 `assert a == b`。** 漏写它**不会红**：
    用例照样全绿，只是少测了一整类缺陷（服务端整章回写漏条、客户端候选集放宽误删）。
    静默失效的规则必须机器可查——`tests/unit/test_e2e_bystander_discipline.py` 就是查它的，
    规则是「凡传 `expected_count > 1` 的模块必须调用本函数至少一次」。有了共用的名字，
    这条检查才写得出来；各写各的 `assert` 是 grep 不到的。

    **整字典等值，不挑字段。** 挑字段（比对 id / quote / color …）会漏掉**下一个被加进
    schema 的字段**：`Annotation` 今天 13 个字段，012 还要动它。整字典等值不需要随 schema
    演化而维护——这是它相对「更严」之外的第二个理由。

    **没有旁观条时直接抛。** 一次「零条旁观」的调用是静默空转，而空转正是本函数要防的
    那件事本身；此时抛出来比绿着强。
    """
    changed = {str(i) for i in changed_ids}
    before_by_id = {str(r["id"]): r for r in before}
    after_by_id = {str(r["id"]): r for r in after}

    bystanders = sorted(set(before_by_id) - changed)
    if not bystanders:
        raise AssertionError(
            f"没有旁观条可断：before 里的 id 是 {sorted(before_by_id)}，"
            f"而 changed_ids 是 {sorted(changed)}——两者相减为空。"
            "这次调用什么都没断到（预置漏了旁观条？changed_ids 写宽了？）"
        )

    for bid in bystanders:
        if bid not in after_by_id:
            raise AssertionError(
                f"旁观条 id={bid!r} 在动作之后**没了**。它不在 changed_ids "
                f"({sorted(changed)}) 里，本不该被这次动作碰到。\n"
                f"  现存的 id：{sorted(after_by_id)}\n"
                "（写路径多是「load 整章 → 改一条 → 整章回写」，回写漏带条目时 HTTP 照样 200）"
            )
        if after_by_id[bid] != before_by_id[bid]:
            raise AssertionError(
                f"旁观条 id={bid!r} 被动过了。它不在 changed_ids "
                f"({sorted(changed)}) 里，本该逐字段原样。\n"
                f"  动作前：{before_by_id[bid]}\n"
                f"  动作后：{after_by_id[bid]}"
            )


# ---------------------------------------------------------------------------
# 几何
# ---------------------------------------------------------------------------

_SELECTION_RECT_JS = r"""
() => {
  const sel = document.getSelection();
  if (!sel || sel.rangeCount < 1) return null;
  const r = sel.getRangeAt(0).getBoundingClientRect();
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom,
           width: r.width, height: r.height };
}
"""


def viewport_rect_of_selection(page: "Page", frame: "FrameLocator") -> Dict[str, float]:
    """iframe 内当前选区的矩形，换算到**外层视口**坐标。

    等价于 `annotations.js` 的 ``offsetRect(range.getBoundingClientRect(), frameEl)``
    ——但是**另一份独立实现**，这一点是刻意的，不是巧合：

        若本函数改成直接调用生产的 ``offsetRect``，生产端「漏加 iframe 偏移」这个
        缺陷会在 K-3b 的两侧**同时**发生并互相抵消，K-3b 于是恒绿。K-3 的全部结论都
        架在这条换算上，所以它必须由一份与被测代码无关的实现来对照。

    这里走的路和生产端不同：range rect 由 **frame 内**的 evaluate 取，iframe 偏移由
    **Playwright 的 ``bounding_box()``** 取（视口坐标，与 ``getBoundingClientRect()``
    在未滚动的阅读器布局下同解）。生产端则是同一个 JS 上下文里两次
    ``getBoundingClientRect()``。

    **这条换算的可失败性集中在 Y 轴。** 未开 TOC 时 ``.reader-layout`` 是 flex 行，
    ``#toc-mode`` 离屏不占位，``#reader`` / ``#main`` / ``.content-container`` /
    ``#epub-viewer`` / iframe 一路 ``width: 100%`` 且 ``padding: 0``，所以
    ``frame_rect.left ≈ 0``；纵向则有 ``.pagination-container { padding-top: 40px }``，
    ``frame_rect.top ≥ 40``。漏加偏移是一个**纯 Y 轴信号**，X 方向的任何容差都抓不到它。
    """
    body = frame.locator("body")  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    inner = body.evaluate(_SELECTION_RECT_JS)
    if inner is None:
        raise AssertionError(
            "viewport_rect_of_selection: iframe 内没有选区。先调 select_in_frame()。"
        )

    box = frame_box(page)

    return {
        "left": inner["left"] + box["x"],
        "right": inner["right"] + box["x"],
        "top": inner["top"] + box["y"],
        "bottom": inner["bottom"] + box["y"],
        "width": inner["width"],
        "height": inner["height"],
    }


# ---------------------------------------------------------------------------
# 语料绊线
# ---------------------------------------------------------------------------


def assert_corpus_unchanged(*checks: Tuple[Any, Any, str]) -> None:
    """语料绊线：每一项是 ``(actual, expected, message)``，``actual != expected`` 即抛 ``message``。

    **这不是判据，是诊断。** 各模块把语料里的句子 / 书名 / token 抄成了字面量（§0 第五条
    纪律：期望值不得从语料派生，否则语料一改期望值跟着改，永远绿）。抄本与原本分家时，
    真正的失败点在三层之外（`select_in_frame` 的「章内找不到 …」、R-1 的 30s 超时、R-3 的
    「一个 `<mark>` 都没有」），正确但要读三层才明白。绊线把失败点提前到用例第一行，并把人
    直接指到语料上。

    四个模块原先各有一份 `_assert_corpus_unchanged`，**查的东西各不相同**，共有的只是这个
    形状。所以上收的是形状，消息文本原样留在各模块的 `CORPUS_CHECKS` 里（欠账 #25）。
    """
    for actual, expected, message in checks:
        if actual != expected:
            raise AssertionError(message)


# ---------------------------------------------------------------------------
# 书库页：可见书目
# ---------------------------------------------------------------------------


def assert_visible_book_ids(page: "Page", expected_visible: Set[str], *, where: str) -> None:
    """断言「书库页上**可见**的书卡恰好是 `expected_visible` 这几本」。

    两半合起来才是集合等值，缺哪一半都有具体的坏实现能全绿：

      1. `lib-book-card` 的**总数**恒等于语料本数——`applyFilters` 只挂 `hidden` 属性，
         从不删节点，所以总数是一个与范围无关的不变量。少了这一半，一个「多渲了一张
         陌生书卡」的实现不会红。
      2. 语料里的**每一本**逐个断 visible／hidden。少了这一半，「把 A 藏了、把 B 放出来」
         这种换位错误不会红——它连总数都不改。

    本数从 `E2E_BOOK_IDS` 派生，不写字面量 4（矩阵 §WI-15 X-2a 原文）。`E2E_BOOK_IDS`
    从 `conftest` 里**函数内**取，理由同 `open_ch0`。
    """
    from conftest import E2E_BOOK_IDS  # type: ignore[import-not-found]
    from playwright.sync_api import expect

    all_book_ids: Set[str] = set(E2E_BOOK_IDS)
    cards = page.locator('[data-testid="lib-book-card"]')
    expect(cards, f"{where}：书卡节点总数应恒等于语料本数（过滤只挂 hidden，不删节点）").to_have_count(
        len(E2E_BOOK_IDS)
    )
    for book_id in sorted(all_book_ids):
        card = page.locator(f'[data-testid="lib-book-card"][data-book-id="{book_id}"]')
        expect(card, f"{where}：{book_id} 的书卡应恰好有 1 个节点").to_have_count(1)
        if book_id in expected_visible:
            expect(card, f"{where}：{book_id} 应可见（期望可见集合 {sorted(expected_visible)}）").to_be_visible()
        else:
            expect(card, f"{where}：{book_id} 应被隐藏（期望可见集合 {sorted(expected_visible)}）").to_be_hidden()


# ---------------------------------------------------------------------------
# 集合：读盘与清理
# ---------------------------------------------------------------------------


def collections_file(books_dir: PathLike) -> Path:
    """集合的持久化文件。

    路径口径来自 `server._collections_file_path`：`collections_path(project_root)`，
    而 `project_root == dirname(BOOKS_DIR)`。**沙箱内**——`e2e_books_dir` 是
    `tmp/e2e*/books`，所以这里是 `tmp/e2e*/config/library_collections.json`，
    与开发者真实仓库根下的 `config/` 无关。
    """
    return Path(books_dir).parent / "config" / "library_collections.json"


def read_collections(books_dir: PathLike) -> List[Dict[str, Any]]:
    """读持久化文件里的集合列表。文件不存在＝一个集合都没有（缺省态是「不存在」）。"""
    path = collections_file(books_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [dict(c) for c in (data.get("collections") or [])]


def http_json(url: str, *, method: str = "GET") -> Any:
    """打被测服务的一次裸 HTTP 调用。

    不带 `Origin` / `Sec-Fetch-Site`：`server._is_cross_site` 对空 `Origin` 明确放行
    （「curl／原生客户端：刻意放行」），且 e2e 的服务不设 `READER3_TOKEN`。
    """
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
    return json.loads(body) if body else None


def delete_collections_with_prefix(base_url: str, prefix: str) -> None:
    """把名字以 `prefix` 开头的集合全删掉。**幂等**，且不因失败中断。

    按前缀扫而不是按某一个 id 删：用例可能在「已创建、还没读到 id」之间失败，也可能上一轮
    被 SIGKILL 掉而留下别的后缀。404（已经没了）按成功处理——finalizer 报错会掩盖用例自己
    的失败原因。
    """
    try:
        data = http_json(f"{base_url}/api/collections")
    except (urllib.error.URLError, OSError):
        return
    for col in (data or {}).get("collections") or []:
        if not str(col.get("name") or "").startswith(prefix):
            continue
        try:
            http_json(f"{base_url}/api/collections/{col['id']}", method="DELETE")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
