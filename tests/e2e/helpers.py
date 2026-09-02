"""E2E 共享 helpers —— 全套 W / R / K 用例只从这里取选区、读写 `notes.json`、换算几何。

四个函数，一个都不许在用例里各写一遍：

    select_in_frame(frame, quote, occurrence=0)   §1 的程序化选区标准路径
    read_notes(books_dir, book_id)                读回 notes.json 的 list[dict]
    seed_notes(books_dir, book_id, annotations)   预置标注（R-3 / R-6 / DEG-S1 用）
    viewport_rect_of_selection(page, frame)       iframe 内 rect → 视口坐标

**为什么集中在一处。** 这些断言的耦合面是**生产代码的实现细节**——工具条的 class 名、
`mouseup` 监听挂在哪个 document 上、`notes.json` 的顶层形状。散到 38 个用例里，
改一次生产代码就要改 38 处；集中在这里，改一处。

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
