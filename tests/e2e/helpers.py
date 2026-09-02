"""E2E 共享 helpers —— 全套 W / R / K 用例只从这里取选区、读写 `notes.json`、换算几何。

八个函数，一个都不许在用例里各写一遍：

    select_in_frame(frame, quote, occurrence=0)   §1 的程序化选区标准路径
    read_notes(books_dir, book_id)                读回 notes.json 的 list[dict]
    seed_notes(books_dir, book_id, annotations)   预置标注（R-3 / R-6 / DEG-S1 用）
    viewport_rect_of_selection(page, frame)       iframe 内 rect → 视口坐标
    open_reader(page, base_url, book_id, i, txt)  打开阅读器并等到 iframe 里有正文
    wait_for_notes(books_dir, book_id, count)     等落库稳定到 count 条
    assert_roundtrip(page, books_dir, book_id, …) §0 的「刷新 → 高亮回到同一段文字」收尾
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
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Sequence, Union

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
    ``editingNoteId`` 清成 null。笔记编辑类用例（W-4 / W-7）若观察到编辑态被莫名
    重置，根因在这里，不在用例。
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


def assert_roundtrip(
    page: "Page",
    books_dir: PathLike,
    book_id: str,
    quote: str,
    anchor: str,
    expected_type: str,
) -> Dict[str, Any]:
    """§0 的往返断言，全部创建路径用例共用的收尾：**刷新** → 高亮回到同一段文字上。

    顺序是刻意的：先读盘（此时页面还没刷新，读到的是服务端真的写下去的东西），再刷新，
    再断 DOM。反过来先刷新再读盘的话，「盘上没有但 JS 还记得」这个失败态会被刷新动作
    自己抹掉，而那正是本纪律要抓的东西。
    """
    from playwright.sync_api import expect

    records = wait_for_notes(books_dir, book_id, 1)
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
    assert len(settled) == 1, (
        f"终态不是恰好 1 条，而是 {len(settled)} 条——一次创建动作写了不止一条："
        f"{settled}"
    )
    assert settled[0]["id"] == record["id"], (
        f"终态那条的 id 与落库时读到的不是同一条：{settled[0]['id']} != {record['id']}"
    )
    return record


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
