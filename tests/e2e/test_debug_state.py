"""020 WI-2——`Reader3Epub.getDebugState()` 在真实 epub.js ＋ 真实 Chromium 里说的是真话。

契约定义处是 `docs/plans/20260928-debug-state-getter.md` §3（接口契约 v1），用例矩阵是
`.claude/tdd-guardian/tests-20260930-113500.md` 的 E1–E4。fe-unit 道
（`frontend/tests/legacy/epub-renderer-debug-state.test.ts`）用 `ePub` 桩把每个字段的
算法钉死；jsdom 没有排版引擎，那一侧永远看不到真的 `displayed.page`、真的 CFI、真的
`<mark>`。本文件就是那些桩的**配对真路径**：

* **E1** 首屏身份：打开第 1 章（非 0，才分得清「真值」和「缺省 0」），`section.index`、
  `requestedIndex`、`href`、CFI 形状、`spineCount` 都来自真实渲染。
* **E2** 翻页是一次状态迁移：`sectionPage.page` 恰好 +1、`cfi.start` 变了（不断言 `total` 不变，见 E2 注释），
  同时 pill 文本与 `sectionPercent` 同口径（U19 的真浏览器半边）。
* **E3** 一次真实保存：`renderedIds` 恰好 +1，服务端列表里多出新 id，`diag` 条数守恒
  （diag 只记失败，所以**不**断言 `ok == true`，见 spec F6）。
* **E4** 只读：每一次探针调用前后，iframe `body.innerHTML` 长度不变、`location.href`
  不变、没有任何 `reader3:*` 事件，结果可以无损走一趟 JSON。

**两个本地小工具，不进 `helpers.py`。** `helpers.py` 属于 soak 冻结面（`suite_hash`），
而且 notes 等待那一块正在另一条分支上改（#49）。所以这里只从 `helpers` 读几个**公开**
名字（`open_reader`、`select_in_frame`、`http_json` 与 smoke 书的坐标常量），等待与探针
都写在本文件：

* `_probe(page)` 在**一次同步** `evaluate` 里量长度 → 调 getter → 再量长度。同一轮事件
  循环里渲染插不进来，所以「前后长度相等」测的是 getter 本身，不是运气。
* `_wait_state(page, predicate_js)` 包一层 `wait_for_function`，超时时把最后一次 getter
  的 JSON 原样带进 `AssertionError`（评审 D8）——等不到的时候，第一眼就该看到状态。

**落址：`UNGROUPED_E2E_MODULES` 白名单，且没有到期条件。** 它是给工具（agent、E2E）用的
观测面，和 `test_testid_dom_uniqueness.py` 一样与 009 的各组正交，不是某个组欠着的
`baseline_1b` 用例。soak 跑的是 `-m baseline_1b`，本文件不在其中。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from conftest import BOOK_ID, BOOK_ID_REPEAT  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    http_json,
    open_reader,
    select_in_frame,
)

#: spec §3 的契约版本号。
CONTRACT_VERSION = 1

#: 等 getter 满足条件的上限。spec 风险表：`wait_for_function` 轮询、5s 超时。
WAIT_MS = 5000

#: E1 打开的章号。取 1 而不是 0：`section.index == 0` 分不清「真的渲染了第 0 章」和
#: 「字段根本没写、停在缺省值」。
E1_CHAPTER = 1

#: E2 的视口。宽必须 ≥ 600：`epub-renderer.js` 在 `innerWidth < 600` 时切到
#: `scrolled-doc`，那里没有分页，`displayed` 的页码无从谈起（spec F6d）。高度压到 360
#: 是为了让 `repeat_data` 那一章（1950 字符）确定地排出多页——推算见 E2 的 docstring。
E2_VIEWPORT = {"width": 640, "height": 360}
E2_CHAPTER = 0

#: 翻下一页的键。宿主页 `document` 上的 keydown（`handleNavKey`）把它交给
#: `rendition.next()`。写成常量而不是字面量：选择器 lint 会把 `press` 调用的字符串
#: 字面量实参当选择器扫（与 `test_selection_toolbar_stays_closed.py` 的 `KEY_ESCAPE` 同理）。
KEY_NEXT_PAGE = "ArrowRight"

#: E3 保存用的工具条按钮。
MARKER_BUTTON_TESTID = "rd-anno-type-marker"

#: E3 等的那次写请求。
NOTES_API_MARKER = "/api/notes/"

#: E3 读 diag 时的上限。缺省 20 条会把「条数守恒」截成一句空话（环里恰好 ≥ 20 条时，
#: 多一条失败也还是 20），取契约允许的最大值 100。
DIAG_LIMIT_MAX = 100

#: 探针期间监听的全部 `reader3:*` 事件（生产代码里 `window.dispatchEvent` 出现过的每一个）。
READER3_EVENTS = (
    "reader3:chapter:change",
    "reader3:content:rendered",
    "reader3:content:click",
    "reader3:escape",
    "reader3:annotations:updated",
    "reader3:ai:ask",
)

#: 一次同步探针：量长度 → 调 getter → 再量长度，期间数 `reader3:*` 事件。
#: 整段不 await，渲染与它之间没有交错的机会。
_PROBE_JS = """([events, opts]) => {
  const api = window.Reader3Epub;
  let fired = 0;
  const onEvent = () => { fired += 1; };
  events.forEach((name) => window.addEventListener(name, onEvent));
  try {
    const rootBefore = api.getContentRoot();
    const lenBefore = rootBefore ? rootBefore.innerHTML.length : -1;
    const hrefBefore = window.location.href;
    const s = opts === null ? api.getDebugState() : api.getDebugState(opts);
    const rootAfter = api.getContentRoot();
    const lenAfter = rootAfter ? rootAfter.innerHTML.length : -1;
    const hrefAfter = window.location.href;
    return { s, json: JSON.stringify(s), lenBefore, lenAfter, hrefBefore, hrefAfter, events: fired };
  } finally {
    events.forEach((name) => window.removeEventListener(name, onEvent));
  }
}"""

#: 超时时取最后一次状态。getter 缺席或抛错都要说出来，不许让诊断本身再抛一次。
_LAST_STATE_JS = """() => {
  const api = window.Reader3Epub;
  if (!api || typeof api.getDebugState !== "function") return "<window.Reader3Epub.getDebugState 不存在>";
  try {
    return JSON.stringify(api.getDebugState());
  } catch (e) {
    return "<getDebugState 抛错：" + String(e) + ">";
  }
}"""

def _assert_read_only(probe: Dict[str, Any], where: str) -> None:
    """E4 的判据，逐条探针执行。"""
    assert probe["lenBefore"] > 0, (
        f"[{where}] 探针时 iframe 还没有正文（lenBefore={probe['lenBefore']}）——"
        "前后都是 -1 也会「相等」，这条探针什么都没测"
    )
    assert probe["lenAfter"] == probe["lenBefore"], (
        f"[{where}] getDebugState 改了 iframe 正文：innerHTML 长度 "
        f"{probe['lenBefore']} → {probe['lenAfter']}"
    )
    assert probe["hrefAfter"] == probe["hrefBefore"], (
        f"[{where}] getDebugState 改了地址：{probe['hrefBefore']} → {probe['hrefAfter']}"
    )
    assert probe["events"] == 0, f"[{where}] getDebugState 期间派发了 {probe['events']} 个 reader3:* 事件"
    s = probe["s"]
    # 两条都要：Playwright 的结构化序列化能带回 NaN / Infinity / undefined，JSON 不能。
    # 页面里 `JSON.stringify` 的产物解回来必须与结构化序列化带回来的完全一致。
    assert json.loads(probe["json"]) == s, (
        f"[{where}] getDebugState 的结果不是纯 JSON 值：结构化 {s!r}，JSON {probe['json']}"
    )
    assert json.loads(json.dumps(s)) == s, f"[{where}] getDebugState 的结果走不通 JSON 往返：{s!r}"


def _probe(page: Page, where: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """同步探针一次，当场执行 E4 的只读判据，返回 getter 的结果。

    判据只在这里执行：每条用例的每一次探针都当场断言，没有模块级汇总再复核一遍——
    通过了的探针再判一次不可能红，那一遍复核什么都测不到。
    """
    probe = page.evaluate(_PROBE_JS, [list(READER3_EVENTS), opts])
    _assert_read_only(probe, where)
    return probe["s"]


def _wait_state(page: Page, predicate_js: str, timeout: int = WAIT_MS) -> None:
    """轮询 getter，直到 `predicate_js(s)` 为真；超时时带上最后一次 getter 的 JSON。"""
    expression = f"""() => {{
      const api = window.Reader3Epub;
      if (!api || typeof api.getDebugState !== "function") return false;
      return !!({predicate_js})(api.getDebugState());
    }}"""
    try:
        page.wait_for_function(expression, timeout=timeout)
    except PlaywrightTimeoutError:
        last = page.evaluate(_LAST_STATE_JS)
        raise AssertionError(
            f"{timeout}ms 内 getDebugState 没有满足 `{predicate_js}`；最后一次状态：{last}"
        ) from None


def test_e1_first_render_reports_identity_cfi_shape_and_href(page: Page, live_server: str) -> None:
    """E1（S1 / L3）：打开第 1 章，等到 `ready` ⇒ 身份、CFI 形状与 href 都来自真实渲染。

    什么改动会让它红：`section.index` 读成缺省 0 或 `ctx.chapterIndex` 以外的来源、
    `requestedIndex` 被 `rendered` 改写（F6b）、`cfi` 不再是 epub.js 的 `epubcfi(…)`、
    `href` 不再取 `location.start.href`、或者 `bookPercent` 在 v1 里提前有了值。
    """
    page.goto(f"{live_server}/read/{BOOK_ID}/{E1_CHAPTER}")
    _wait_state(page, "s => s.ready === true")
    s = _probe(page, "E1 ready")

    assert s["v"] == CONTRACT_VERSION, f"契约版本不是 v{CONTRACT_VERSION}：{s}"
    assert s["section"]["index"] == E1_CHAPTER, f"渲染的章号不对：{s['section']}"
    assert s["section"]["requestedIndex"] == E1_CHAPTER, f"请求的章号不对：{s['section']}"
    assert s["cfi"] is not None, f"ready 之后 cfi 仍是 null：{s}"
    assert s["cfi"]["start"].startswith("epubcfi("), f"cfi.start 不是 epub.js 的 CFI：{s['cfi']}"
    assert s["cfi"]["end"].startswith("epubcfi("), f"cfi.end 不是 epub.js 的 CFI：{s['cfi']}"
    href = s["section"]["href"]
    assert isinstance(href, str) and href != "", f"section.href 不是非空字符串：{s['section']}"
    spine_count = s["section"]["spineCount"]
    assert isinstance(spine_count, int) and spine_count >= 2, (
        f"smoke 书至少两章，spineCount 却是 {spine_count!r}"
    )
    assert s["progress"]["bookPercent"] is None, f"v1 的 bookPercent 必须恒为 null：{s['progress']}"
    assert s["errors"] == [], f"正常首屏不该有任何字段报错：{s['errors']}"


def test_e2_page_turn_advances_section_page_by_exactly_one(page: Page, live_server: str) -> None:
    """E2（S5 / L3 ＋ L2）：翻一页 ⇒ `sectionPage.page` 恰好 +1，`cfi.start` 变了。

    **为什么 640×360 下 `repeat_data` 第 0 章必然多页。** 宽 640 ≥ 600，走 paginated。
    视口容器高 `100vh − 40px − 40px` = 280px，注入的正文样式再占去上 40px / 下 60px 的
    内边距，每页可排正文约 180px；缺省字号 17px × 行高 1.9 ≈ 32px 一行，每页 5 行上下。
    左右各 80px 边距，行宽约 480px，衬线 17px 一行约 55–60 字符；1950 字符 ≈ 33–36 行
    ≈ 6–7 页（纸面推算；2026-09-30 实测首帧报 total=3、翻页后 4，仍 ≥ 2）。它是一条
    **断言**而不是 skip：一旦被布局或语料改动推翻，用例必须当场红，而不是悄悄什么都不测。

    什么改动会让它红：`sectionPage` 不再取 `location.start.displayed`、getter 读到的是
    过期快照、pill 与 getter 不再共用 `sectionProgressOf`。
    """
    page.set_viewport_size(E2_VIEWPORT)
    page.goto(f"{live_server}/read/{BOOK_ID_REPEAT}/{E2_CHAPTER}")
    _wait_state(page, "s => s.ready === true && s.progress.sectionPage !== null")
    s0 = _probe(page, "E2 翻页前")

    page0 = s0["progress"]["sectionPage"]
    assert page0["total"] >= 2 and page0["page"] < page0["total"], (
        f"E2 前提不成立：视口 {E2_VIEWPORT['width']}×{E2_VIEWPORT['height']} 下 "
        f"{BOOK_ID_REPEAT} 第 {E2_CHAPTER} 章是 page {page0['page']} / total {page0['total']}，"
        "没有下一页可翻。请调小 E2_VIEWPORT 的高度（宽必须保持 ≥ 600）或换一个更长的章节，"
        "不要改成 skip"
    )

    page.keyboard.press(KEY_NEXT_PAGE)
    _wait_state(
        page,
        f"s => s.progress.sectionPage !== null && s.progress.sectionPage.page === {page0['page']} + 1",
    )
    s1 = _probe(page, "E2 翻页后")

    page1 = s1["progress"]["sectionPage"]
    assert page1["page"] == page0["page"] + 1, f"翻一页不是恰好 +1：{page0} → {page1}"
    # 不断言 total 不变：first-render displayed.total can be stale (pre-reflow); see 020 WI-3
    # debt note。实测 2026-09-30，640×360、repeat_data 第 0 章：{page:1,total:3} → {page:2,total:4}，
    # 3/3 次一致。归属 014 WI-19（进度口径重定义）。
    assert s1["cfi"]["start"] != s0["cfi"]["start"], (
        f"页码变了而 cfi.start 没变——位置快照不是同一份：{s0['cfi']} → {s1['cfi']}"
    )
    assert s1["section"]["index"] == s0["section"]["index"], (
        f"章内翻页换了章：{s0['section']} → {s1['section']}"
    )
    assert s0["errors"] == [] and s1["errors"] == [], f"翻页前后不该有字段报错：{s0['errors']} / {s1['errors']}"

    pill = page.get_by_test_id("rd-page-indicator").text_content()
    assert pill == f"当前阅读至 {s1['progress']['sectionPercent']}%", (
        f"pill 与 getter 不同口径：pill {pill!r}，sectionPercent {s1['progress']['sectionPercent']!r}"
    )


def test_e3_real_save_increments_rendered_ids_and_conserves_diag(page: Page, live_server: str) -> None:
    """E3（S5 / L3 ＋ L2）：一次真实保存 ⇒ `renderedIds` 恰好 +1、服务端多出新 id、diag 条数不变。

    `diag` 只记录写失败（spec F6），所以成功保存的证据是「条数没增」，**不是**最后一条
    `ok == true`。服务端列表用 `http_json` 直接问：它不经过浏览器上下文，不受任何路由影响。

    什么改动会让它红：`renderedIds` 不再按 `data-annotation-ids` 去重计数、getter 读到
    的是渲染前的旧文档、或者一次成功保存在诊断环里留下了记录。
    """
    notes_url = f"{live_server}/api/notes/{BOOK_ID}/0"
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    _wait_state(page, "s => s.ready === true && s.annotations !== null")
    s0 = _probe(page, "E3 保存前", {"diagLimit": DIAG_LIMIT_MAX})

    assert s0["diagAvailable"] is True, f"annotations.js 已加载，诊断环却不可用：{s0}"
    n0 = s0["annotations"]["renderedIds"]
    d0 = len(s0["diag"])
    assert d0 < DIAG_LIMIT_MAX, f"诊断环已满 {d0} 条，条数守恒在截断下无从判断"
    ids_before = {a["id"] for a in http_json(notes_url)["annotations"]}

    select_in_frame(frame, CH0_QUOTE)
    with page.expect_response(lambda r: r.request.method == "POST" and NOTES_API_MARKER in r.url):
        page.get_by_test_id(MARKER_BUTTON_TESTID).click()
    _wait_state(page, f"s => s.annotations !== null && s.annotations.renderedIds === {n0} + 1")
    s1 = _probe(page, "E3 保存后", {"diagLimit": DIAG_LIMIT_MAX})

    assert s1["annotations"]["renderedIds"] == n0 + 1, f"保存后 renderedIds 不是 +1：{s0['annotations']} → {s1['annotations']}"
    assert s1["annotations"]["marks"] >= 1, f"保存后 iframe 里没有 mark：{s1['annotations']}"
    ids_after = {a["id"] for a in http_json(notes_url)["annotations"]}
    new_ids = ids_after - ids_before
    assert len(new_ids) == 1, f"服务端应当恰好多出一条标注：保存前 {sorted(ids_before)}，保存后 {sorted(ids_after)}"
    assert len(s1["diag"]) == d0, f"一次成功保存在诊断环里留下了记录：{s0['diag']} → {s1['diag']}"
    assert s1["errors"] == [], f"保存后不该有字段报错：{s1['errors']}"


def test_e4_get_debug_state_is_read_only_in_every_probed_state(page: Page, live_server: str) -> None:
    """E4（S5 / L2）：连调两次结果相同，两次探针都满足只读判据。

    自己的小流程：`smoke_data` 第 0 章，等 `ready`，背靠背探两次。E1–E3 的探针（翻页前后、
    保存前后）不在这里复核：只读判据在 `_probe` 里当场执行，每一次探针都已各自断言过。

    什么改动会让它红：getter 调了 `rendition.display/next/prev`、`currentLocation()`、
    往正文里写东西、派发事件，或者返回了带 NaN / undefined / 函数的值。
    """
    page.goto(f"{live_server}/read/{BOOK_ID}/0")
    _wait_state(page, "s => s.ready === true && s.annotations !== null")
    first = _probe(page, "E4 第一次")
    second = _probe(page, "E4 第二次")

    assert second == first, f"背靠背两次调用结果不同：{first} vs {second}"
