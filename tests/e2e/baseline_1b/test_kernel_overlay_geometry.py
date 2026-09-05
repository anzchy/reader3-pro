"""WI-10 —— K-3：三个浮层的坐标系（祖先链前置条件 ＋ 矩形几何）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-10（**R1 / R2 修订为准**）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §4 K-3 行、§0 六条纪律
（尤其第四条「特征化用例的可失败性证据」）、§0.6 Wave 5 独占的理由。契约原文：
`docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K3
——六条契约里唯一被标「最高危」的一条：**浮层照常出现、位置错，`toBeVisible()` 会通过**。

**Law（定位前置条件是一个合取式，两项缺一不可）**：对 `rd-anno-toolbar` / `rd-note-editor` /
`rd-note-tooltip` 三个浮层，(i) 自身 `getComputedStyle(el).position === "fixed"`；(ii) 祖先链上
零「包含块制造者」（`transform` / `filter` / `backdrop-filter` / `perspective` / `contain` /
`will-change` 中任一非默认值）。`offsetRect()` 算出的是**视口坐标**，只有 (i) 成立时 `left/top`
才按视口解释，只有 (ii) 成立时 fixed 的包含块才是视口。任一项破，浮层可见、位置错。
(ii) 的判据照抄契约的 `containingBlockAncestor(el)`（下面 `_CONTAINING_BLOCK_JS`），**不重写**
——重写等于把规范复制一份，两份会漂移。

四条用例、六个收集项：K-3a ×3（参数化，三个浮层的**唤出方式不同**，所以是三条不是一条循环）、
K-3b、K-3b′、K-3c。

-------------------------------------------------------------------------------
本布局的一条事实，三条几何用例都按它分轴表述（矩阵 R2 Gap B）
-------------------------------------------------------------------------------
未开 TOC 时 **`frame_rect.left == 0`、`frame_rect.top == 40`**（2026-09-04 实测，1280×720 视口，
`helpers.frame_box` 返回 `{x: 0, y: 40, width: 1280, height: 640}`）：`#toc-mode` 离屏 fixed、
`#reader` / `#main` / `.content-container` / `#epub-viewer` / iframe 一路 `width: 100%` 且
`padding: 0`；纵向的 40 来自 `.pagination-container { padding-top: 40px }`。
因此 **`offsetRect` 漏加 iframe 偏移是一个纯 Y 轴信号**。

**K-3b 只在 Y 轴上携带「`offsetRect` 漏加 iframe 偏移」的信号。** 本布局下 iframe 的横向偏移
是 0，所以任何 X 容差都抓不到那个缺陷；X 轴断的是另一件事——工具条是否**居中于选区**。
谁若把 `Y_TOL` 放大到 40 以上，本条对该缺陷即失明，请连同这句话一起改。

**已知盲区**：把 `offsetRect` 里 `frameRect.left` 那一项删掉，**两轴都不动**（偏移是 0）——
本模块抓不到它。由 WI-3 的「helper 与生产各自独立换算」那条（`viewport_rect_of_selection`
的 docstring）在 `< 1px` 的阈值上兜底。

-------------------------------------------------------------------------------
容差与常量的取值依据
-------------------------------------------------------------------------------
* **`X_TOL = 2`（精确值，不是容差）**：`openToolbarAt` 写 `left = Math.round(x)` 再
  `translate(-50%, -100%)`，所以 `toolbar_center_x - selection_center_x` 只余 `Math.round` 的
  ≤ 0.5 与 `getBoundingClientRect` 的亚像素。实测差值 0.0–0.5。模块级元断言 `X_TOL <= 2`
  记录的是这个精确性。
* **`Y_TOL = 20`**：正确实现下 `toolbar.bottom == selection.top - 12`（`y = rect.top - 12` ＋
  `translate(…, -100%)`），故 `Y_TOL` 需 `> 12`；漏加 iframe 纵向偏移会让 `toolbar.bottom`
  偏 ≥ 40，故 `Y_TOL` 需 `< frame_rect.top`。`12 < Y_TOL < 40` 非空，取 20；
  `Y_TOL < frame_rect.top` 在用例里对着实测的 `frame_box` 断一次。
* **`MIN_DELTA_X = 60` / `MIN_DELTA_Y = 40`**（K-3b′）：两个选区若太近，`Δ ≈ 0`，差分断言退化成
  `0 ≈ 0`，对「工具条固定在屏幕中央」的实现也绿。元断言 `X_TOL < MIN_DELTA_X`、
  `Y_TOL < MIN_DELTA_Y`。实测 s1→s2 的 Δx = 355.8、Δy = 226.1。
* **`GAP_TOL = 6`（K-3c，与 `X_TOL` 不同源）**：笔记编辑器是**另一套定位代码**
  （`openNoteEditor`）：`transform: translate(0, 0)`、`x = rect.right + 12`（放不下时翻到左侧
  `rect.left - 320 - 12`）、`y = rect.top`，**没有 `-50%` 的居中变换**。它的 X 判据是「间距
  ≈ 12」而不是「居中」，所以不能复用 `X_TOL = 2`；`GAP_TOL = 6` 覆盖 12px 间距的取整与边界
  翻转。**断的是「该在的那一侧」，不是「两侧之一」**：哪一侧由 `_editor_fits_right()` 从视口
  几何算出（与生产的翻转条件同一个式子），再对那一侧的间距单独取等；写成析取式会放过
  「右优先 → 左优先」的策略反转（S6 实测）。三条几何用例的常量**不要合并成一个**。

**禁止事项**：`toolbarHalfWidth = 200`、`clamp(…, 60, …)`、`editorWidth = 320` 这些生产常数
**不得进入输出断言**（change-tax 反模式：重构一改常数，几十条断言跟着改）。它们只出现在下面
`_TOOLBAR_*` / `_EDITOR_*` 那组**前置条件**常量里——那里它们是「哪些输入是合法的」的定义。

-------------------------------------------------------------------------------
选区为什么取在 `repeat_data` 而不是 `smoke_data`（矩阵 §WI-10「选区取在视口中段」的实测订正）
-------------------------------------------------------------------------------
`handleSelectionRange` 的两行：`x = clamp(rect.left + rect.width/2, 220, W - 220)`、
`y = clamp(rect.top - 12, 60, H - 20)`。无 clamp 带是 **`selection_center_x ∈ [220, W-220]`**、
**`selection.top ∈ [72, H-8]`**（矩阵 R2 修正：clamp 作用在 `rect.top - 12` 上，旧带
`y ∈ [60, H-20]` 漏掉了 `-12` 的预减）。选区靠边时 clamp 生效，关系断言会假红，而假红就是 flaky。

`smoke_data` 第 0 章的正文 `Alpha prose` **不在这个带里**：实测选区中心 x = 130.3 < 220，
工具条中心被钉在 220（clamp 下界）。所以几何用例全部取 `repeat_data`（`build_huge_epub`，
25 遍同一句话，一页排满 1280 宽），`deck` 第 6 次出现在 (cx 379.2, top 179.9)、`lamp` 第 22 次
出现在 (cx 735.0, top 406.0)，都在带内且离带边界 ≥ 150px。带外不 skip、`pytest.fail`：语料是
固定的，落不进这个带说明语料或视口尺寸变了，那是要修的事，不是要跳过的事。

-------------------------------------------------------------------------------
K-3a 的可失败性：两条纸面验证配方 ＋ 一处实测订正
-------------------------------------------------------------------------------
这是纸面验证，不自动化：自动改样式再改回来会污染 session 级页面，而污染正是 flaky 的来源。

* **打破 (ii)**：给 **`<body>`** 临时加 `transform: translateZ(0)` ⇒ 三个 K-3a 的 (ii) 必红，
  消息打出 `<BODY id='' data-testid=''> 命中属性 ['transform']`。
  ⚠️ 计划稿写的是「给 `rd-shell` 加」——**那不会红**：三个浮层都是 `<body>` 的直接子元素
  （契约 K3「挂载位置规则」第 1 种），`rd-shell`（`.reader-layout`）是它们的**兄弟**，不是祖先。
  下面破坏表 S1′ 实测：注入 `[data-testid="rd-shell"] { transform: translateZ(0) }` 后 6/6 仍绿。
  这同时说明本条防的不是假想的失败模式：`#toc-mode` / `#reader-search-drawer` / `#reader-ai-panel`
  都用 `translateX(±100%)` 做抽屉动画，它们今天是浮层的同级；任何一次「把浮层挪进抽屉容器里」
  或「把浮层挪进 `rd-shell`、再给 `rd-shell` 加毛玻璃」的重构都会立刻触发 (ii)。
* **打破 (i)**：把 `#annotation-toolbar` 的 `position` 临时改成 `absolute` ⇒ K-3a[toolbar] 的 (i)
  必红（旧形态只有 (ii)，对此是盲的——祖先链依然干净）。

-------------------------------------------------------------------------------
定向破坏实录（§0 第四条纪律；全部经 `page.route` 改写响应体，`src/` 一个字节没动）
-------------------------------------------------------------------------------
本模块是特征化用例，红本来就不可得（收据必然记成 green）。替代证据是逐条打靶：每条用例至少一次
破坏，留档破坏点 / 实际失败输出 / 还原核验。破坏走 `page.route` 改写 `annotations.js` /
`reader.html` 的响应体（迁移计划 §5 的工程实践），一次性脚本用完即删。

（破坏表见本 docstring 末尾 `SABOTAGE_LOG`。）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple

import pytest
from playwright.sync_api import FrameLocator, Page, expect

from conftest import BOOK_ID, BOOK_ID_REPEAT  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    frame_box,
    open_ch0,
    open_reader_settled,
    seed_notes,
    select_in_frame,
    viewport_rect_of_selection,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# 容差（取值依据见模块 docstring）
# ---------------------------------------------------------------------------

#: X 轴的**精确值**：工具条中心与选区中心之差只余 `Math.round` 与亚像素。
X_TOL = 2.0
#: Y 轴容差：`12 < Y_TOL < frame_rect.top(40)`。放大到 40 以上本模块对「漏加 iframe 偏移」失明。
Y_TOL = 20.0
#: K-3b′ 两个选区之间的最小位移——差分断言不退化成 `0 ≈ 0` 的前提。
MIN_DELTA_X = 60.0
MIN_DELTA_Y = 40.0
#: K-3c 的间距容差，与 `X_TOL` 不同源（编辑器不居中，贴在选区右侧 12px）。
GAP_TOL = 6.0
#: 编辑器与选区的**关系参数**：「贴在右侧 12px」是被断的关系本身，不是 clamp 常数。
EDITOR_GAP_PX = 12.0

# 模块级元断言（矩阵 R2 原文）。
assert X_TOL <= 2
assert X_TOL < MIN_DELTA_X
assert Y_TOL < MIN_DELTA_Y

# ---------------------------------------------------------------------------
# 前置条件常量：只用来算「无 clamp 带」，**绝不进入输出断言**
# ---------------------------------------------------------------------------
#
# 来源 `annotations.js` `handleSelectionRange`：
#   x = clamp(rect.left + rect.width/2, 20 + 200, W - 20 - 200)
#   y = clamp(rect.top - 12, 60, H - 20)
# 与 `openNoteEditor`：editorWidth = 320、editorHeight = 180、边距 20、间距 12。
_TOOLBAR_HALF_WIDTH = 200.0
_VIEWPORT_EDGE = 20.0
_TOOLBAR_Y_FLOOR = 60.0
_TOOLBAR_LIFT = 12.0
_EDITOR_WIDTH = 320.0
_EDITOR_HEIGHT = 180.0


# ---------------------------------------------------------------------------
# 语料坐标
# ---------------------------------------------------------------------------

#: `repeat_data` 第 0 章的到位探针（`_HUGE_SENTENCE` 的开头）。
REPEAT_ANCHOR = "The lamp guttered"
REPEAT_CHAPTER = 0

#: K-3b / K-3c / K-3b′ 的 s1：`deck` 第 6 次出现。实测 (cx 379.2, top 179.9)，带内。
S1_QUOTE, S1_OCCURRENCE = "deck", 6
#: K-3b′ 的 s2：`lamp` 第 22 次出现。实测 (cx 735.0, top 406.0)，带内，与 s1 的 Δ 远超 MIN_DELTA。
S2_QUOTE, S2_OCCURRENCE = "lamp", 22

#: K-3a 的 tooltip 参数要一条预置的 note（`cfi=None`，与生产今天产出的记录同形，欠账 #6）。
K3A_NOTE_ID = "wi10-k3a-tooltip-note"
K3A_NOTE_TEXT = "K-3a tooltip 载荷"
K3A_CREATED_AT = "2026-01-01T00:00:00+00:00"
K3A_EXPECTED_MARKS = 1


# ---------------------------------------------------------------------------
# 契约判据：照抄 annotation-host-contracts.md K3「机器判据」，不重写
# ---------------------------------------------------------------------------

# 外层是我们的包装：命中时把祖先的身份与六项 computed 一起带回来，失败消息才能说清楚
# 「是哪个祖先、哪个属性」。**判定本身只由契约那段代码做**；六项 computed 只是诊断载荷。
_CONTAINING_BLOCK_JS = r"""
(el) => {
  // ---- 以下逐字来自 annotation-host-contracts.md §K3「机器判据」 ----
  // 返回第一个会为 position:fixed 造出新包含块的祖先，没有则 null
  function containingBlockAncestor(el) {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.transform !== "none") return p;
      if (s.filter !== "none") return p;
      if (s.backdropFilter && s.backdropFilter !== "none") return p;
      if (s.perspective !== "none") return p;
      if (/\b(layout|paint|strict|content)\b/.test(s.contain)) return p;
      if (/\b(transform|filter|perspective)\b/.test(s.willChange)) return p;
    }
    return null;
  }
  // ---- 契约代码到此为止 ----
  const p = containingBlockAncestor(el);
  if (!p) return null;
  const s = getComputedStyle(p);
  return {
    tagName: p.tagName,
    id: p.id || "",
    testid: p.dataset.testid || "",
    computed: {
      "transform": s.transform,
      "filter": s.filter,
      "backdrop-filter": s.backdropFilter,
      "perspective": s.perspective,
      "contain": s.contain,
      "will-change": s.willChange,
    },
  };
}
"""

#: 诊断用的默认值表——只用来在消息里圈出「哪几项非默认」，**不是判据**（判据在上面的契约代码里）。
_CSS_DEFAULTS: Dict[str, Tuple[str, ...]] = {
    "transform": ("none",),
    "filter": ("none",),
    "backdrop-filter": ("none", ""),
    "perspective": ("none",),
    "contain": ("none",),
    "will-change": ("auto",),
}


# ---------------------------------------------------------------------------
# 几何小工具
# ---------------------------------------------------------------------------


def _center_x(box: Dict[str, float]) -> float:
    """Playwright `bounding_box()`（x/y/width/height）或选区 rect（left/…/width）的水平中心。"""
    left = box["x"] if "x" in box else box["left"]
    return left + box["width"] / 2


def _bottom(box: Dict[str, float]) -> float:
    top = box["y"] if "y" in box else box["top"]
    return top + box["height"]


def _visible_box(page: Page, testid: str) -> Dict[str, float]:
    el = page.get_by_test_id(testid)
    expect(el).to_be_visible()
    box = el.bounding_box()
    assert box is not None, f"{testid} 可见但没有 bounding box"
    return box


def _require_toolbar_band(page: Page, sel: Dict[str, float], label: str) -> None:
    """前置条件：选区落在 `handleSelectionRange` 的**无 clamp 带**内。带外 `pytest.fail`，不 skip。"""
    vp = page.viewport_size
    assert vp is not None
    w, h = float(vp["width"]), float(vp["height"])
    x_lo, x_hi = _VIEWPORT_EDGE + _TOOLBAR_HALF_WIDTH, w - _VIEWPORT_EDGE - _TOOLBAR_HALF_WIDTH
    top_lo, top_hi = _TOOLBAR_Y_FLOOR + _TOOLBAR_LIFT, h - _VIEWPORT_EDGE + _TOOLBAR_LIFT
    cx = _center_x(sel)
    if not (x_lo <= cx <= x_hi):
        pytest.fail(
            f"{label}：选区中心 x = {cx:.1f} 不在无 clamp 带 [{x_lo:.0f}, {x_hi:.0f}] 内"
            f"（视口 {w:.0f}×{h:.0f}，选区 {sel}）。语料或视口尺寸变了——修语料坐标，不要放宽容差"
        )
    if not (top_lo <= sel["top"] <= top_hi):
        pytest.fail(
            f"{label}：选区 top = {sel['top']:.1f} 不在无 clamp 带 [{top_lo:.0f}, {top_hi:.0f}] 内"
            f"（视口 {w:.0f}×{h:.0f}，选区 {sel}）。语料或视口尺寸变了——修语料坐标，不要放宽容差"
        )


def _editor_fits_right(page: Page, sel: Dict[str, float]) -> bool:
    """生产在这个视口 ＋ 这个选区下**应当**选右侧吗？

    判据逐字对应 `openNoteEditor` 的翻转条件 `if (x + editorWidth > innerWidth - 20)`
    （`x = rect.right + 12`），只是写成了它的否定式。K-3c 的侧别断言与本模块的前置条件
    带都从这一个函数取值：两处若各写一份，「该选哪侧」与「哪侧放得下」会各自漂移。
    """
    vp = page.viewport_size
    assert vp is not None
    return sel["right"] + EDITOR_GAP_PX + _EDITOR_WIDTH <= float(vp["width"]) - _VIEWPORT_EDGE


def _require_editor_band(page: Page, sel: Dict[str, float], label: str) -> None:
    """前置条件：编辑器至少有一侧放得下，且纵向不触发 `openNoteEditor` 的下移 / clamp。"""
    vp = page.viewport_size
    assert vp is not None
    w, h = float(vp["width"]), float(vp["height"])
    fits_right = _editor_fits_right(page, sel)
    fits_left = sel["left"] - EDITOR_GAP_PX - _EDITOR_WIDTH >= _VIEWPORT_EDGE
    if not (fits_right or fits_left):
        pytest.fail(
            f"{label}：编辑器左右两侧都放不下（选区 {sel}，视口 {w:.0f}×{h:.0f}），"
            "`openNoteEditor` 会走 clamp 分支，关系断言无意义——修语料坐标"
        )
    y_lo, y_hi = _VIEWPORT_EDGE, h - _EDITOR_HEIGHT - _VIEWPORT_EDGE
    if not (y_lo <= sel["top"] <= y_hi):
        pytest.fail(
            f"{label}：选区 top = {sel['top']:.1f} 不在编辑器的无 clamp 带 [{y_lo:.0f}, {y_hi:.0f}] 内"
            f"（视口 {w:.0f}×{h:.0f}）——修语料坐标"
        )


def _select(page: Page, frame: FrameLocator, quote: str, occurrence: int, label: str) -> Dict[str, float]:
    """建选区 → 换算到视口坐标 → 断无 clamp 带。返回视口坐标下的选区矩形。"""
    select_in_frame(frame, quote, occurrence)
    sel = viewport_rect_of_selection(page, frame)
    _require_toolbar_band(page, sel, label)
    return sel


# ---------------------------------------------------------------------------
# K-3a：三个浮层各断两项前置条件（参数化 ×3）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlaySummon:
    """一个浮层 ＋ 把它唤出来的方式。三个浮层的唤出方式不同，所以是三条而不是一条循环。"""

    param_id: str
    testid: str
    summon: Callable[[Page, FrameLocator], None]


def _summon_toolbar(page: Page, frame: FrameLocator) -> None:
    select_in_frame(frame, CH0_QUOTE)
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()


def _summon_note_editor(page: Page, frame: FrameLocator) -> None:
    _summon_toolbar(page, frame)
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()


def _summon_tooltip(page: Page, frame: FrameLocator) -> None:
    # 判别位 `data-annotation-id` 在 ADR-0014 的闭合清单内；这里只有一个 `<mark>`，带上它是让
    # 失败消息说清楚「是哪一条的高亮没出现」。
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{K3A_NOTE_ID}"]')
    expect(mark).to_have_count(1)
    mark.hover()
    expect(page.get_by_test_id("rd-note-tooltip")).to_have_text(K3A_NOTE_TEXT)


K3A_OVERLAYS = (
    OverlaySummon("toolbar", "rd-anno-toolbar", _summon_toolbar),
    OverlaySummon("note-editor", "rd-note-editor", _summon_note_editor),
    OverlaySummon("tooltip", "rd-note-tooltip", _summon_tooltip),
)


@pytest.mark.parametrize("overlay", K3A_OVERLAYS, ids=[o.param_id for o in K3A_OVERLAYS])
def test_k3a_overlay_is_fixed_and_has_no_containing_block_ancestor(
    page: Page, live_server: str, e2e_books_dir: Path, overlay: OverlaySummon
) -> None:
    """K-3a（S3，L4）：浮层唤出之后，(i) 自身 `position: fixed`，(ii) 祖先链无包含块制造者。

    **两条断言顺序固定：先 (i) 后 (ii)。** 两者是独立的失败模式：把浮层改成 `position: absolute`
    并给它一个定位父级，祖先链依然干净、(ii) 全绿，坐标却改按最近定位祖先解释；反之给祖先加
    `will-change: transform`，(i) 依然是 fixed，包含块却换了。契约 K3 明写：两种情形下
    `toBeVisible()` **都会通过**。

    (i) **必须在浮层已被唤出之后取**——`display:none` 的元素 computed style 仍可读，但改成在
    唤出前读会掩盖「唤出时被 JS 改了 position」的情形。L4 而非 1–3：被测的就是「浏览器算出来的
    样式状态」，没有更高的可观察物。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": K3A_NOTE_ID,
                "chapter_index": 0,
                "type": "note",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "prefix": "",
                "suffix": "",
                "cfi": None,
                "note_text": K3A_NOTE_TEXT,
                "created_at": K3A_CREATED_AT,
            }
        ],
    )
    frame = open_ch0(page, live_server, expected_marks=K3A_EXPECTED_MARKS)
    overlay.summon(page, frame)

    handle = page.get_by_test_id(overlay.testid).element_handle()
    assert handle is not None, f"{overlay.testid} 不在 DOM 上"

    # (i) 自身 position: fixed —— 唤出之后取
    position = page.evaluate("el => getComputedStyle(el).position", handle)
    assert position == "fixed", (
        f"{overlay.testid} 唤出后的 computed position 是 {position!r}，不是 'fixed'。"
        "`offsetRect` 产出的是视口坐标，只有 position:fixed 才按视口解释 left/top；"
        "改成 absolute 之后浮层照常可见、位置全错，而祖先链检查对此一无所知（矩阵 R1 Gap 6）"
    )

    # (ii) 祖先链无包含块制造者 —— 契约的 containingBlockAncestor(el) === null
    hit = page.evaluate(_CONTAINING_BLOCK_JS, handle)
    if hit is not None:
        computed = hit["computed"]
        offending = [name for name, value in computed.items() if value not in _CSS_DEFAULTS[name]]
        pytest.fail(
            f"{overlay.testid} 的祖先链上有包含块制造者："
            f"<{hit['tagName']} id={hit['id']!r} data-testid={hit['testid']!r}> "
            f"命中属性 {offending}；该祖先六项 computed = {computed}。"
            "position:fixed 的浮层会以它为包含块，offsetRect 的视口坐标从此按它解释——"
            "浮层照常可见、位置错，toBeVisible() 会通过（契约 K3）"
        )


# ---------------------------------------------------------------------------
# K-3b：工具条矩形 vs 选区矩形——X 轴精确、Y 轴带 iframe 偏移灵敏度的容差
# ---------------------------------------------------------------------------


def test_k3b_toolbar_is_centred_on_and_sits_just_above_the_selection(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-3b（S3，L2）：工具条中心 x 与选区中心 x 之差 ≤ `X_TOL`；工具条底边落在选区顶边 ± `Y_TOL`。

    **本条只在 Y 轴上携带「`offsetRect` 漏加 iframe 偏移」的信号**（模块 docstring）。它是唯一断
    **绝对**对位的用例——K-3b′ 是差分，偏移在差分里抵消。两条互补，都要留。

    选区取在视口中段，避开 `handleSelectionRange` 的 clamp 分支（`_require_toolbar_band`）。
    """
    frame = open_reader_settled(page, live_server, BOOK_ID_REPEAT, REPEAT_CHAPTER, REPEAT_ANCHOR)

    # 元断言：Y 容差必须小于 iframe 的纵向偏移，否则「漏加偏移」在本条上看不见。
    fb = frame_box(page)
    assert Y_TOL < fb["y"], (
        f"Y_TOL = {Y_TOL} 不小于 iframe 的纵向偏移 frame_rect.top = {fb['y']}（frame_box = {fb}）。"
        "本条对「offsetRect 漏加 iframe 偏移」即失明——布局变了就同步改 Y_TOL 与模块 docstring"
    )

    sel = _select(page, frame, S1_QUOTE, S1_OCCURRENCE, "K-3b")
    toolbar = _visible_box(page, "rd-anno-toolbar")

    # X 轴（精确）：工具条居中于选区。
    dx = _center_x(toolbar) - _center_x(sel)
    assert abs(dx) <= X_TOL, (
        f"工具条中心 x 与选区中心 x 相差 {dx:+.2f}px，超出 X_TOL = {X_TOL}"
        f"（工具条 {toolbar}，选区 {sel}）。openToolbarAt 的 translate(-50%) 被改了？"
    )

    # Y 轴（容差）：工具条底边贴在选区顶边上方。
    bottom = _bottom(toolbar)
    assert sel["top"] - Y_TOL <= bottom <= sel["top"] + Y_TOL, (
        f"工具条底边 y = {bottom:.2f} 不在选区顶边 {sel['top']:.2f} ± {Y_TOL} 内"
        f"（差 {bottom - sel['top']:+.2f}px；工具条 {toolbar}，选区 {sel}，iframe 偏移 {fb}）。"
        "偏 ≈ frame_rect.top 时是 offsetRect 漏加了 iframe 纵向偏移"
    )


# ---------------------------------------------------------------------------
# K-3b′：平移协变——选区移动多少，工具条跟着移动多少
# ---------------------------------------------------------------------------


def test_k3b_prime_toolbar_displacement_equals_selection_displacement(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-3b′（S5，L2）：对同一页上的两个选区 s1、s2，`Δtoolbar ≈ Δselection`。

    K-3b 只断了「定位是选区位置的函数」在**一个点**上的值；本条断它**随选区变化**。一个
    「工具条永远贴在视口顶部中央」的实现 ⇒ `ΔT = 0`、`ΔS ≠ 0` ⇒ 红；`handleSelectionRange`
    把整段落的 rect 而不是选区的 rect 传给 `openToolbarAt` ⇒ 单点可能都在容差内、差分明显不同
    ⇒ 红（K-3b 对后者是盲的）。反过来，一个「漏加 iframe 偏移」的实现在本条上**绿**（偏移在
    差分里抵消）而在 K-3b 的 Y 轴上红——这正是两条并存的理由。

    前置条件先断：两个选区都在无 clamp 带内，且 `|ΔS| ≥ MIN_DELTA`（否则退化成 `0 ≈ 0`）。
    """
    frame = open_reader_settled(page, live_server, BOOK_ID_REPEAT, REPEAT_CHAPTER, REPEAT_ANCHOR)

    s1 = _select(page, frame, S1_QUOTE, S1_OCCURRENCE, "K-3b′ s1")
    t1 = _visible_box(page, "rd-anno-toolbar")

    # `select_in_frame` 自己先清选区、等去抖窗口排空，再在同一个同步回合里装新选区 ＋ mouseup。
    s2 = _select(page, frame, S2_QUOTE, S2_OCCURRENCE, "K-3b′ s2")
    t2 = _visible_box(page, "rd-anno-toolbar")

    ds_x = _center_x(s2) - _center_x(s1)
    ds_y = s2["top"] - s1["top"]
    if abs(ds_x) < MIN_DELTA_X:
        pytest.fail(
            f"K-3b′ 前置条件：两个选区的中心 x 只差 {ds_x:+.1f}px（< MIN_DELTA_X = {MIN_DELTA_X}），"
            f"差分断言会退化成 0 ≈ 0（s1 {s1}，s2 {s2}）——换语料坐标"
        )
    if abs(ds_y) < MIN_DELTA_Y:
        pytest.fail(
            f"K-3b′ 前置条件：两个选区的 top 只差 {ds_y:+.1f}px（< MIN_DELTA_Y = {MIN_DELTA_Y}），"
            f"差分断言会退化成 0 ≈ 0（s1 {s1}，s2 {s2}）——换语料坐标"
        )

    dt_x = _center_x(t2) - _center_x(t1)
    dt_y = _bottom(t2) - _bottom(t1)
    assert abs(dt_x - ds_x) <= X_TOL, (
        f"工具条中心 x 移动了 {dt_x:+.2f}px，选区中心 x 移动了 {ds_x:+.2f}px，差 {dt_x - ds_x:+.2f}px"
        f" > X_TOL = {X_TOL}（t1 {t1}，t2 {t2}，s1 {s1}，s2 {s2}）。工具条不再随选区横向移动"
    )
    assert abs(dt_y - ds_y) <= Y_TOL, (
        f"工具条底边移动了 {dt_y:+.2f}px，选区顶边移动了 {ds_y:+.2f}px，差 {dt_y - ds_y:+.2f}px"
        f" > Y_TOL = {Y_TOL}（t1 {t1}，t2 {t2}，s1 {s1}，s2 {s2}）。工具条不再随选区纵向移动"
    )


# ---------------------------------------------------------------------------
# K-3c：笔记编辑器打开后的矩形落在选区旁边
# ---------------------------------------------------------------------------


def test_k3c_note_editor_opens_beside_the_selection(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-3c（S1，L2）：`rd-note-editor` 贴在选区**右侧** `EDITOR_GAP_PX`（放不下时翻到左侧）、顶边对齐。

    `openNoteEditor` 与 `openToolbarAt` 是**两套定位代码**，改任一套只会打断对应的一条——这正是
    它们各一条用例的理由。X 判据是「间距 ≈ 12」而不是「居中」，所以容差是 `GAP_TOL` 而不是
    `X_TOL`（模块 docstring）；且是**先算该选哪侧、再只断那一侧**，不是「两侧任一成立即可」的
    析取式——析取式对「右优先被改成左优先」这条策略反转是盲的（`_editor_fits_right` 旁的注释）。
    选区矩形在点按钮**之前**取：编辑器按点击时刻的
    `currentRange` 定位，而 `noteTextarea.focus()` 之后 iframe 的程序化选区实测仍在
    （`test_write_note_editor.py` W-4 的实测），两者同解，先取只是让因果顺序在代码里可读。
    """
    frame = open_reader_settled(page, live_server, BOOK_ID_REPEAT, REPEAT_CHAPTER, REPEAT_ANCHOR)

    sel = _select(page, frame, S1_QUOTE, S1_OCCURRENCE, "K-3c")
    _require_editor_band(page, sel, "K-3c")

    page.get_by_test_id("rd-anno-note").click()
    editor = _visible_box(page, "rd-note-editor")

    right_gap = editor["x"] - sel["right"]
    left_gap = sel["left"] - (editor["x"] + editor["width"])

    # 先从视口几何算出生产**应当**选哪一侧，再只断那一侧。写成
    # `abs(right_gap - 12) <= GAP_TOL or abs(left_gap - 12) <= GAP_TOL` 的析取式是失效的：
    # 右侧明明放得下时它照样接受落在左侧的编辑器，于是「右优先、放不下才翻左」这条策略被
    # 反转（`openNoteEditor` 改成 `let x = rect.left - editorWidth - 12` 起手）也一样绿。
    # 析取式唯一能拦的只剩「两侧都不贴」，而那是比策略反转弱得多的一件事。
    fits_right = _editor_fits_right(page, sel)
    expected_side = "右侧" if fits_right else "左侧"
    gap = right_gap if fits_right else left_gap
    other_gap = left_gap if fits_right else right_gap
    assert abs(gap - EDITOR_GAP_PX) <= GAP_TOL, (
        f"编辑器应贴在选区**{expected_side}**（本选区在 {page.viewport_size} 视口下"
        f"{'右侧放得下' if fits_right else '右侧放不下，须翻到左侧'}），"
        f"实测该侧间距 {gap:+.2f}px，期望 ≈ {EDITOR_GAP_PX} ± {GAP_TOL}"
        f"（另一侧间距 {other_gap:+.2f}px；编辑器 {editor}，选区 {sel}）。"
        "openNoteEditor 的 x = rect.right + 12 / 翻左分支被改了？"
        "另一侧间距若恰好 ≈ 12，说明右优先的回退策略被反转了"
    )
    dy = editor["y"] - sel["top"]
    assert abs(dy) <= GAP_TOL, (
        f"编辑器顶边与选区顶边相差 {dy:+.2f}px > GAP_TOL = {GAP_TOL}（编辑器 {editor}，选区 {sel}）。"
        "openNoteEditor 的 y = rect.top 被改了？"
    )


# ---------------------------------------------------------------------------
# 定向破坏实录（§0 第四条纪律）——由 WI-10 交付时填写，见模块 docstring
# ---------------------------------------------------------------------------

SABOTAGE_LOG = """
2026-09-04，chromium 1280×720，六次破坏 × 六个收集项 = 36 次运行（另 1 次祖先链探针），
全部经一次性模块 `tests/e2e/test_zz_sabotage_wi10.py` 的 `page.route` 改写响应体，改写命中次数
逐次核对（命中数 != 期望即抛，不让「改写没生效」冒充证据）。结果 9 红 / 27 绿，红的分布如下。
还原核验：一次性模块已删；`git status --short` 只剩本 WI 的文件；`git diff --quiet -- src/` 退出 0。

| # | 破坏点（改写目标） | 红 | 绿 | 失败输出摘录 |
|---|---|---|---|---|
| S1 | `reader.html` `</head>` 前注入 `body{transform:translateZ(0)}` | K-3a ×3（(ii)） | K-3b / K-3b′ / K-3c | `Failed: rd-anno-toolbar 的祖先链上有包含块制造者：<BODY id='' data-testid=''> 命中属性 ['transform']；该祖先六项 computed = {'transform': 'matrix(1, 0, 0, 1, 0, 0)', 'filter': 'none', …}`（note-editor / tooltip 同形）。三条几何用例**全绿**——body 恰好在原点、与视口同尺寸，坐标数值碰巧不变，这正是契约 K3 说的「静默」 |
| S1′ | 同上，但注入到 `[data-testid="rd-shell"]` | — | 6/6 全绿 | 无红。`rd-shell` 不是三个浮层的祖先（探针实测祖先链 = `['BODY', 'HTML']`），计划稿「给 rd-shell 加 transform 后必红」的配方对今天的 DOM 不成立，纸面配方已改为 `<body>` |
| S2 | `reader.html` `#annotation-toolbar { position: fixed;` → `position: absolute;` | K-3a[toolbar]（(i)） | 其余 5 条 | `AssertionError: rd-anno-toolbar 唤出后的 computed position 是 'absolute'，不是 'fixed'。…（矩阵 R1 Gap 6）`。祖先链 (ii) 依然干净、几何三条依然绿（没有定位父级时 absolute 也按初始包含块解释）——旧形态对此是盲的，R1 加 (i) 的理由 |
| S3 | `annotations.js` `offsetRect` 删掉 `frameRect.top` 两项（top / bottom） | K-3b（Y） / K-3c（Y） | **K-3b′ 绿**、K-3a ×3 | K-3b：`工具条底边 y = 128.00 不在选区顶边 179.89 ± 20.0 内（差 -51.89px；…iframe 偏移 {'x': 0, 'y': 40, …}）`；K-3c：`编辑器顶边与选区顶边相差 -39.89px > GAP_TOL = 6.0`。**K-3b′ 保持绿**：偏移在差分里抵消——这就是 K-3b 与 K-3b′ 必须并存的实证 |
| S4 | `annotations.js` `openToolbarAt` 的 `style.left = Math.round(x)px` → 固定 `"640px"` | K-3b（X） / K-3b′（X） | K-3a ×3 / K-3c | K-3b：`工具条中心 x 与选区中心 x 相差 +260.77px，超出 X_TOL = 2.0`；K-3b′：`工具条中心 x 移动了 +0.00px，选区中心 x 移动了 +355.79px，差 -355.79px > X_TOL = 2.0` |
| S5 | `annotations.js` `let x = rect.right + 12;` → `+ 60`（两处：`openNoteEditor` 与 `openNoteEditorWithExisting`） | **仅 K-3c** | 其余 5 条 | `编辑器既不贴在选区右侧（间距 +59.72px）也不贴在左侧（间距 -411.83px），期望其一 ≈ 12.0 ± 6.0` |

**S6（2026-09-05 追加，打的是 K-3c 的 X 判据本身）**：`page.route` 把 `annotations.js` 里两处
`let x = rect.right + 12;` 改写成 `let x = rect.left - editorWidth - 12;`（`openNoteEditor` 与
`openNoteEditorWithExisting`，命中数核对为 2；`src/` 未动），即把「右优先、放不下才翻左」的
回退策略**整个反转**成「左优先」。实测同一份几何下：

* 旧的析取式 `abs(right_gap-12) <= GAP_TOL or abs(left_gap-12) <= GAP_TOL` —— **绿**
  （`right_gap = -364.28`、`left_gap = +12.17`，第二项成立）；
* 现在的写法 —— 红，逐字输出：`AssertionError: 编辑器应贴在选区**右侧**（本选区在
  {'width': 1280, 'height': 720} 视口下右侧放得下），实测该侧间距 -364.28px，期望 ≈ 12.0 ± 6.0
  （另一侧间距 +12.17px；编辑器 {'x': 31, 'y': 180, …}，选区 {'left': 363.17, 'right': 395.28, …}）`。

析取式能拦的只剩「两侧都不贴」；策略反转它一声不响，而 4B.2 的浮层重写正是最可能顺手把
「先试右侧」写成「先试左侧」的地方。

每条用例各自被哪一枪咬住：K-3a[toolbar] ← S1 / S2；K-3a[note-editor] ← S1；K-3a[tooltip] ← S1；
K-3b ← S3（Y）/ S4（X）；K-3b′ ← S4；K-3c ← S3（Y）/ S5（X 间距）/ S6（X 侧别）。S3 与 S4 合起来把 K-3b 的两轴
分别打红，证明两轴断的不是同一件事；S3 上 K-3b 红而 K-3b′ 绿、S4 上两条同红，证明差分用例既
不是绝对用例的子集也不是它的替代。
"""
