"""WI-14 —— R-6b：表现层变更之后，**存下来的那条 CFI 仍然解得回同一段文字**。

skip 形态，`acceptance_4b1` 组。矩阵：`.claude/tdd-guardian/tests-20260901-224500.md`
§WI-14 的**断言 a**。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0.5（分组定性）、
§0.6 跨波欠账 **#6**（本条的阻塞者）与 **#8**、§2 的 2026-09-03「R-6 拆 a / b」裁定。

**阻塞者：跨波欠账 #6 —— `cfi` 恒为 `null`。**
`epub-renderer.js` 在 `rendered` 回调里把 epub.js 传来的 **view** 当作 `Contents` 存进
`currentContents`。`IframeView` 有 `.document`，所以样式注入、点击、翻页全都照常工作，
唯独**没有 `cfiFromRange`**；于是 `annotations.js` 里
`typeof contents.cfiFromRange === "function"` 这个卫语句**永假**，写库时 `cfi` 一律落
`null`。连带地，`AnnotationRenderer.render()` 里那条按 CFI 定位的分支今天是死代码
（欠账 #8）。

所以本模块的三条今天**不是失败，是无对象**：没有任何一条生产产出的记录带 CFI，
「重解析存储的 CFI」这句话没有主语。§0.5 对这种情况的定性是明确的——写期望行为，
不写在 `baseline-1b` 里，而是放进 `acceptance-*` 挂 skip，与欠账 #6 的修复同期解开。

-------------------------------------------------------------------------------
**它与 `baseline_1b/test_read_presentation_anchoring.py`（R-6a）是什么关系**
-------------------------------------------------------------------------------
同一条 Law（**呈现变换下的锚定不变性**）的两条独立通道：

* **R-6a（今天绿）**：纯文本锚定。表现层变了之后，`rd-anno-span` 覆盖的文本仍等于
  `quote`。这是今天真实生效的那条路，护住迁移的也是它。
* **R-6b（本模块，skip）**：CFI 锚定。表现层变了之后，把**磁盘上存的那条 CFI** 重新
  解析成 Range，`range.toString()` 仍等于 `quote`。

两条都必须存在，因为它们能**分别地**坏掉：文本锚定靠 `indexOf(quote)`，对 DOM 结构的
变化免疫但对重复文本敏感；CFI 锚定记的是**节点路径 + 偏移**，对重复文本免疫但只要
表现层变更动了 DOM 结构（插节点、拆文本节点、包 `<span>`）就会**指到别处去，而且不报错**
——它会安静地解析出一个别的 Range。R-6a 那条通道看不见这种坏法：`<mark>` 是文本锚定
画上去的，CFI 指哪儿它一无所知。

-------------------------------------------------------------------------------
**为什么标注是**从 UI 建**的，而不是 `seed_notes` 预置**
-------------------------------------------------------------------------------
本模块**必须**用 `select_in_frame` + `rd-anno-type-marker` 走一遍真实创建路径，让 CFI 是
**生产自己生成**的那一串。手写一个 CFI 进 `notes.json` 在技术上做得到（`ePub.CFI` 是独立
解析器，多半解得开），但那样断的是「我手写的 CFI 能被 epub.js 解析」——一句关于
`ePub.CFI` 的断言，不是关于我们生产代码的断言。欠账 #6 兑付的正是**生成**那一端，
所以生成必须在被测范围内。

`stored_cfi is not None` 那句断言因此不是防御性代码，是**本模块的解锁条件**：它红着的
那一天就是欠账 #6 还没兑付；它一变绿，下面三步才有意义。解 skip 的人应当先单独确认这一句
能过，再去看 `toString()` 那一句。

-------------------------------------------------------------------------------
**兑付时怎么解开这三条**
-------------------------------------------------------------------------------
1. 欠账 #6 修好（`currentContents` 存真正的 `Contents`，或另给一条拿得到 `cfiFromRange`
   的路），确认新建标注的 `cfi` 不再是 `null`。
2. 删掉模块级 `pytest.mark.skip`，跑本模块。
3. 条数常量**不必再改**：欠账 **#14** 已由 WI-17 结清，`scripts/lint_e2e_groups.py` 的
   `EXPECTED_ACCEPTANCE_PER_DIR["acceptance_4b1"]` 按 8 计（R-6b 3 ＋ K-1b ＋ K-6b ＋ W-5b 3），
   解 skip 只是让这三条从 skipped 变 passed，不改收集条数。
4. 若第 1 步之后 `range.toString()` 与 `quote` 对不上（差空白、差首尾一两个字符），
   那是**真红**：CFI 的 `toRange` 与我们建它时用的 Range 之间存在偏移，别改期望值去迁就，
   先看 `annotations.js` 建 CFI 时传的是不是同一个 Range。

-------------------------------------------------------------------------------
**给解 skip 的人的三条实测前情**（全部来自 R-6a 那一侧，2026-09-04）
-------------------------------------------------------------------------------
* **`±` 四个按钮的可访问名是 `−`（U+2212）与 `+`，不是中文 `title`。** 任务书和矩阵写的
  `减小字号` / `放大字号` / `减小间距` / `增大间距` 一个都匹配不上（accname 取内容，
  `title` 只是兜底）。而且两个容器里的四个按钮**共用同一对名字**，不按容器 testid 限定
  作用域会解析出 2 个节点、strict 模式当场抛。完整实测见 R-6a 模块 docstring 「实测订正一」。
* **四个主题格子今天是纯装饰**（模板自己的 CSS 写着 `/* Theme selector (UI only for v1) */`
  与 `cursor: not-allowed`），全仓无监听器。所以 `theme-four-states` 这一项在兑付前
  **没有刺激**，解 skip 时它可能会「因为什么都没发生所以过了」——那不算数。
* **字号 / 间距的改动落到 iframe 上慢一拍**（`applySettings()` 先跑、`saveSettings()` 后写，
  而 CSS 是从 localStorage 读的）。所以这两项各点**两步**才真的发生了一次重排；只点一步
  时页面根本没动，本模块的判据会空转。这是生产缺陷，§0.5 只记录不修。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    open_ch0,
    open_font_popover,
    select_in_frame,
    wait_for_notes,
)

#: 组标记 ＋ 模块级 skip。skip 挂在**模块级**而不是逐条：三条被同一个欠账挡住，
#: 逐条挂会让「阻塞者是同一个」这件事在三处各写一遍，兑付时漏删一处就是一条静默跳过。
pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1（与跨波欠账 #6 的修复同期）：`cfi` 恒为 null——`epub-renderer.js` 把 epub.js 的 "
            "view 当作 Contents 存进 currentContents，`cfiFromRange` 不存在，`annotations.js` 的卫语句"
            "永假，所以生产从未产出过带 CFI 的记录，本组三条今天无对象（不是失败）。"
            "到期动作：兑付欠账 #6 后删本行；条数常量 EXPECTED_ACCEPTANCE_PER_DIR['acceptance_4b1'] 已按 8 计"
            "（欠账 #14 由 WI-17 结清），不必再改。"
        )
    ),
]

#: 期望：重解析出来的 Range 覆盖的文本。**独立写一遍字面量**，不写 `CH0_QUOTE`
#: （§0 第五条纪律）：输入与期望同源就等于拿自己比自己，两侧一起改照样绿。
R6B_EXPECTED_RANGE_TEXT = "Alpha prose"


# ---------------------------------------------------------------------------
# 表现层控件的抓手（与 R-6a 同源，见本模块 docstring 末节的三条实测前情）
# ---------------------------------------------------------------------------
THEME_TESTIDS: Tuple[str, ...] = (
    "rd-pref-theme-paper",
    "rd-pref-theme-sepia",
    "rd-pref-theme-green",
    "rd-pref-theme-night",
)

#: `−` 是 **U+2212 MINUS SIGN**，不是 ASCII `-`。欠账 #15 兑付（给这四个按钮各一个
#: testid）之后，这两个常量连同 `_click_stepper` 一起删。
DECREASE_BUTTON_NAME = "−"
INCREASE_BUTTON_NAME = "+"

SIZE_CONTAINER = "rd-pref-size"
LEADING_CONTAINER = "rd-pref-leading"


def _click_theme(testid: str) -> Callable[[Page], None]:
    def _apply(page: Page) -> None:
        page.get_by_test_id(testid).click()

    return _apply


def _click_stepper(container_testid: str, button_name: str) -> Callable[[Page], None]:
    def _apply(page: Page) -> None:
        page.get_by_test_id(container_testid).get_by_role(
            "button", name=button_name, exact=True
        ).click()

    return _apply


@dataclass(frozen=True)
class PresentationChange:
    """一项表现层参数，连同「怎么施加它」。与 R-6a 的同名结构体形状一致。

    **刻意不从 `baseline_1b` 那个模块 import**：两个目录下都没有 `__init__.py`
    （`.gitkeep` 里写明了原因），跨目录的裸模块 import 只有在两个目录**同时被收集**时
    才碰巧成立；单跑 `pytest tests/e2e/acceptance_4b1` 会 ImportError。这点重复换来的是
    本模块单独可跑。
    """

    param_id: str
    label: str
    steps: Tuple[Tuple[str, Callable[[Page], None]], ...]


R6B_CHANGES: Tuple[PresentationChange, ...] = (
    PresentationChange(
        param_id="theme-four-states",
        label="主题四态（白色 / 黄色 / 护眼 / 夜间）",
        steps=tuple(
            (f"主题→{testid}", _click_theme(testid)) for testid in THEME_TESTIDS
        ),
    ),
    PresentationChange(
        param_id="font-size-plus-minus",
        label="字号 ±（相对当前值，不依赖具体档位数）",
        steps=(
            ("字号 −（减小一档）", _click_stepper(SIZE_CONTAINER, DECREASE_BUTTON_NAME)),
            ("字号 +（放大一档）", _click_stepper(SIZE_CONTAINER, INCREASE_BUTTON_NAME)),
        ),
    ),
    PresentationChange(
        param_id="paragraph-spacing-plus-minus",
        # UI 标签是「段落间距」，容器 testid 是 `rd-pref-leading`。矩阵管它叫「行距」
        # ——模板里没有叫这个名字的控件。
        label="段落间距 ±（相对当前值，不依赖具体档位数）",
        steps=(
            (
                "段落间距 −（减小一档）",
                _click_stepper(LEADING_CONTAINER, DECREASE_BUTTON_NAME),
            ),
            (
                "段落间距 +（增大一档）",
                _click_stepper(LEADING_CONTAINER, INCREASE_BUTTON_NAME),
            ),
        ),
    ),
)


#: 在**顶层页面**上下文里重解析 CFI。`window.ePub` 是 reader.html 加载的 epub.js，
#: `Reader3Epub.getContentDocument()` 给出 iframe 的 document——`CFI.toRange(doc)` 要的
#: 正是标注所在的那个文档。这里不写任何 CSS 选择器，所以不需要 lint 放行。
_REANCHOR_JS = (
    "(cfi) => {"
    " const doc = window.Reader3Epub.getContentDocument();"
    " if (!doc) return { ok: false, why: 'getContentDocument() 返回 null' };"
    " const range = new window.ePub.CFI(cfi).toRange(doc);"
    " if (!range) return { ok: false, why: 'CFI.toRange() 返回 null（路径指向了不存在的节点）' };"
    " return { ok: true, text: range.toString() };"
    "}"
)


@pytest.mark.parametrize(
    "change",
    R6B_CHANGES,
    ids=[change.param_id for change in R6B_CHANGES],
)
def test_r6b_stored_cfi_still_resolves_to_the_quote_after_presentation_change(
    page: Page, live_server: str, e2e_books_dir: Path, change: PresentationChange
) -> None:
    """R-6b（期望行为，skip）：改表现层参数后，存储的 CFI 重解析出的 Range 仍是 `quote`。

    设计规格 §6.0 判定标准断言 C 的 **CFI 侧**。文本侧（今天绿）在
    `tests/e2e/baseline_1b/test_read_presentation_anchoring.py`。为什么这条今天无对象、
    以及兑付时的四步解锁顺序，见模块 docstring。

    三步判据：

      1. **解锁条件**：走一遍真实创建路径之后，落库那条记录的 `cfi` 不是 `None`。
         今天必红（欠账 #6）。这一句红着的时候，下面两步说的都不是关于生产的事。
      2. 每施加一步表现层变更，就用 `window.ePub.CFI` 把**磁盘上那一串**重新解析成 Range。
         解不出来（`toRange` 返 `null`）即红——CFI 的节点路径被表现层变更打断了。
      3. `range.toString() == R6B_EXPECTED_RANGE_TEXT`（**字面量**）。这条才是 Law：
         CFI 最坏的坏法不是解析失败，是**安安静静解析到了别的地方**，只有比对文本抓得住。

    第 (2)(3) 步**每一步之后都做**，不是做完所有步骤再做一次：「第二次点击把 CFI 指飞了」
    在只断终态的写法里是不可见的。
    """
    frame = open_ch0(page, live_server)

    # ---- 走真实创建路径，让 CFI 是生产自己生成的那一串（理由见模块 docstring）----
    select_in_frame(frame, CH0_QUOTE)
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-type-marker").click()

    records = wait_for_notes(e2e_books_dir, BOOK_ID, 1)
    record = records[0]
    stored_cfi = record.get("cfi")

    # ---- 解锁条件：欠账 #6 兑付前，这一句就是本模块红的地方 ----
    assert stored_cfi is not None, (
        "落库那条标注的 `cfi` 是 None——生产没有生成 CFI，本条无对象。\n"
        "    这正是跨波欠账 #6：`currentContents` 里存的是 epub.js 的 view 而不是 "
        "`Contents`，没有 `cfiFromRange`，`annotations.js` 的卫语句永假。\n"
        "    修好 #6 之前不要动本模块的其余部分；修好之后这一句应当先单独变绿。\n"
        f"    完整条目：{record}"
    )

    open_font_popover(page)

    for step_label, apply_step in change.steps:
        apply_step(page)
        page.wait_for_load_state("networkidle")

        result: Dict[str, object] = page.evaluate(_REANCHOR_JS, stored_cfi)

        assert result.get("ok"), (
            f"施加「{step_label}」之后，存储的 CFI 解析不回一个 Range 了。\n"
            f"    原因：{result.get('why')}\n"
            f"    CFI：{stored_cfi!r}\n"
            f"    参数：{change.label}\n"
            "    表现层变更改动了 DOM 结构（插节点 / 拆文本节点 / 包 span），"
            "把 CFI 记的节点路径打断了。"
        )
        assert result.get("text") == R6B_EXPECTED_RANGE_TEXT, (
            f"施加「{step_label}」之后，存储的 CFI 仍然解析得出 Range，"
            f"但它覆盖的文本是 {result.get('text')!r}，期望恒为 "
            f"{R6B_EXPECTED_RANGE_TEXT!r}。\n"
            f"    CFI：{stored_cfi!r}\n"
            f"    参数：{change.label}\n"
            "    ——这是 CFI 最坏的那种坏法：不报错，安静地指到了别的地方。"
        )
