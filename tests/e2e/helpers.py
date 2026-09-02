"""E2E 共享 helpers —— 全套 W / R / K 用例只从这里取选区、读写 `notes.json`、换算几何。

十个函数，一个都不许在用例里各写一遍：

    select_in_frame(frame, quote, occurrence=0)   §1 的程序化选区标准路径
    read_notes(books_dir, book_id)                读回 notes.json 的 list[dict]
    seed_notes(books_dir, book_id, annotations)   预置标注（R-3 / R-6 / DEG-S1 用）
    viewport_rect_of_selection(page, frame)       iframe 内 rect → 视口坐标
    open_reader(page, base_url, book_id, i, txt)  打开阅读器并等到 iframe 里有正文
    wait_for_notes(books_dir, book_id, count)     等落库稳定到 count 条
    wait_for_note_text(books_dir, book_id, id, s) 等某条的 note_text 变成 s（PUT 路径用）
    assert_roundtrip(page, books_dir, book_id, …) §0 的「刷新 → 高亮回到同一段文字」收尾
    assert_bystanders_unchanged(before, after, ids) 没碰过的条目逐字段原样（§0 第六条纪律）
    clear_selection_and_drain(page, frame)        清选区并等去抖窗口排空

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
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Collection,
    Dict,
    List,
    Mapping,
    Sequence,
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
CH0_QUOTE = "Alpha prose"
CH0_ANCHOR = "Alpha prose."
CH1_QUOTE = "Beta prose"
CH1_ANCHOR = "Beta prose."


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


def open_reader(
    page: "Page", base_url: str, book_id: str, chapter_index: int, expect_text: str
) -> "FrameLocator":
    """打开阅读器并等到 iframe 里真的有正文。

    先等外层壳，再等 iframe：壳都没有的话，下面的等待会白等满超时，报出来的是
    「找不到 frame」而不是「页面根本没渲染」——smoke 里已经付过一次这个学费。
    """
    from playwright.sync_api import expect

    page.goto(f"{base_url}/read/{book_id}/{chapter_index}")
    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(expect_text)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    return frame


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

    W-1（真实拖选）用来在「量完几何」与「开始拖」之间把场地清干净。`select_in_frame`
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
# notes.json
# ---------------------------------------------------------------------------


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


def wait_for_notes(books_dir: PathLike, book_id: str, count: int) -> List[Dict[str, Any]]:
    """等 `notes.json` 稳定到 `count` 条，超时即红并把实际内容打出来。

    这不是「重试掩盖 flaky」：落库是异步的（fetch → 服务端原子写），不等就是在断言一个
    还没发生的事件。等的是**一个确定的终态**，不是「多试几次也许就成了」——终态不对时它
    照样红，且把实际条目原样贴出来。

    ⚠️ 它一观察到 `len == count` 就返回，所以读到的可能是**中间态**：若一次动作写了两次，
    50ms 的轮询有一定概率正好落在两次写之间的窗口里。要断「恰好 N 条」必须在一个确定的
    终态上再断一次（`assert_roundtrip` 就是在刷新之后补的那一次）。
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


def wait_for_note_text(
    books_dir: PathLike, book_id: str, note_id: str, expected_text: str
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
    """
    deadline = time.monotonic() + NOTES_WAIT_S
    while time.monotonic() < deadline:
        for record in read_notes(books_dir, book_id):
            if record.get("id") == note_id:
                if record.get("note_text") == expected_text:
                    return record
                break
        time.sleep(0.05)

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
    """
    from playwright.sync_api import expect

    records = wait_for_notes(books_dir, book_id, expected_count)
    record = _pick_target(records, quote, expected_type)
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

    frame_el = page.locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    box = frame_el.bounding_box()
    if box is None:
        raise AssertionError("viewport_rect_of_selection: iframe 元素没有 bounding box（还没渲染？）")

    return {
        "left": inner["left"] + box["x"],
        "right": inner["right"] + box["x"],
        "top": inner["top"] + box["y"],
        "bottom": inner["bottom"] + box["y"],
        "width": inner["width"],
        "height": inner["height"],
    }
