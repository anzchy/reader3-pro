"""WI-14 —— R-6a：切换表现层参数之后，既有标注仍然锚在**同一段文字**上。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-14（**该节的 CFI 前提已作废，
四个可访问名也全部对不上，见下**）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §2 的 R-6a 行、
§0.5 的分组表、§0.6 跨波欠账 #6 / #15 / #16、§8「一个不成组的例外」。

**Law（呈现变换下的锚定不变性）**：对表现层参数的任意取值，`rd-anno-span` 覆盖的文本恒等于
标注的 `quote`。它一次性杀掉所有「锚定其实依赖布局 / 行盒 / 列宽」的实现。

-------------------------------------------------------------------------------
**为什么这里只有文本侧，没有 CFI 侧（R-6 在 2026-09-03 拆成 a / b）**
-------------------------------------------------------------------------------
矩阵 §WI-14 写于 09-01，它要求预置一条**含 `cfi`** 的标注，并断言「用 `window.ePub.CFI`
重解析存储的 CFI，`range.toString() == quote`」。两天后 WI-7 把这个前提证伪了：任务书
跨波欠账 #6 实测 **`cfi` 恒为 `null`**——`epub-renderer.js` 在 `rendered` 回调里把 epub.js
传来的 **view** 当作 `Contents` 存进 `currentContents`，`IframeView` 有 `.document` 所以样式
注入 / 点击 / 翻页全都照常，唯独没有 `cfiFromRange`，于是 `annotations.js` 里
`typeof contents.cfiFromRange === "function"` 这个卫语句**永假**。

技术上手写一个 CFI 进 `notes.json` 是做得到的，`ePub.CFI` 是独立解析器，多半解得开。
**问题是它跑起来在特征化什么**：一条生产永远不会产生的记录，走一条生产永远不会执行的分支
（欠账 #8 认定 `AnnotationRenderer.render()` 的 CFI 分支今天是死代码）。按 §0.5 的定性，
那不是安全网，是在写期望行为——期望行为归 `acceptance-4b1`。

所以 **CFI 侧（矩阵的断言 a）在 `tests/e2e/acceptance_4b1/test_r6b_cfi_reanchoring.py`**，
skip 形态，与欠账 #6 的修复同期解开。本模块只留**文本侧（断言 b）**，走今天真实生效的
纯文本锚定路径——**这条才是护住迁移的那条**。本模块的 seed 因此显式写 `cfi=None`，与生产
今天产出的记录逐字段同形；换成 `cfi="epubcfi(...)"` 会让本模块悄悄改测另一条分支。

-------------------------------------------------------------------------------
**参数化的结构要求：参数是「一次表现层变更 ＋ 它的施加方式」**
-------------------------------------------------------------------------------
矩阵三条 Case 共有的结构要求，也是本模块最容易被后人改坏的地方：`R6A_CHANGES` 的每一项
是一个 `PresentationChange`，断言主体只有一份。4B.3 的**正文栏宽**届时只是往
`R6A_CHANGES` 里加**第四项**，不新开组、不改断言主体、不动
`EXPECTED_BASELINE_ITEMS`（任务书 §8「一个不成组的例外」，且 4B.3 的退出门槛点名了
「R-6a 的栏宽参数已启用并绿灯」）。谁要把这三条拆成三个独立函数，先读那一节。

-------------------------------------------------------------------------------
⚠️ **实测订正一：`±` 四个按钮的可访问名不是中文 title，是 `−` 与 `+`**
-------------------------------------------------------------------------------
任务书欠账 #15、§2 的「真实抓手」注、以及矩阵 §WI-14 都写着这四个按钮「只能靠中文 `title`
提供的可访问名定位」，并列出 `减小字号` / `放大字号` / `减小间距` / `增大间距`。
**这四个名字一个都匹配不上**（2026-09-04 实测，chromium 1234）：

    COUNT rd-pref-size    name='减小字号' -> 0
    COUNT rd-pref-size    name='放大字号' -> 0
    COUNT rd-pref-size    name='−'        -> 1
    COUNT rd-pref-size    name='+'        -> 1
    COUNT rd-pref-leading name='减小间距' -> 0
    COUNT rd-pref-leading name='增大间距' -> 0
    COUNT rd-pref-leading name='−'        -> 1
    COUNT rd-pref-leading name='+'        -> 1

成因是 accname 算法本身：`<button title="减小字号">−</button>` 的名字取自**内容**
（accname 2F），`title` 只是 2I 的兜底，内容非空时轮不到它。模板里四个按钮的内容分别是
`−`（**U+2212 MINUS SIGN，不是 ASCII 连字符**）与 `+`。

这条订正把欠账 #15 的**脆点换了一个位置**，而且换到了更坏的位置：

* 欠账 #15 说「中文文案一改本条即断」——**不会**。改 `title` 对本模块毫无影响。
* 真正的脆点是那两个字形：`−` 一旦被换成 ASCII `-`，或按钮改用图标，本条即断。
* 更要紧的是**两个容器里的四个按钮共用同一对名字**。所以
  `get_by_role("button", name="−")` 在整页上解析出 **2 个**节点，strict 模式当场抛。
  容器 testid 的 `get_by_test_id(...).get_by_role(...)` 作用域**不是让失败消息更好看，
  是让这条定位成立的必要条件**。

欠账 #15 的**兑付条件不变**：4A 欠这四个按钮各一个 testid（与 ADR-0014 的命名规则一致）；
兑付之后本模块改用 `get_by_test_id`，`DECREASE_BUTTON_NAME` / `INCREASE_BUTTON_NAME` 两个
常量连同这一节一起删掉。**兑付前请把欠账 #15 的描述按本节改掉**——照它今天的写法去修
（「给中文 title 加稳定性」）修不到点子上。

-------------------------------------------------------------------------------
⚠️ **实测订正二：四个主题格子今天是纯装饰，本参数因此没有刺激**
-------------------------------------------------------------------------------
`rd-pref-theme-paper` / `-sepia` / `-green` / `-night` 是 `<div>`（不是 `<button>`，所以用
`get_by_test_id`，不是 `get_by_role("button")`），**全仓没有任何监听器绑在它们身上**：
`reader.html` 与 `static/js/*.js` 里 grep `theme-option` / `rd-pref-theme` 只命中 CSS 与
这四行标记本身。模板自己的 CSS 也写明了：

    /* Theme selector (UI only for v1) */
    .theme-option { … cursor: not-allowed; opacity: 0.6; }

实测四次点击（2026-09-04）：iframe body 的 `color` 与 `backgroundColor` 一个字节都没动，
`is-active` 仍在 `-paper` 上，父节点 `outerHTML` 逐字相同。

**后果必须写下来，否则下一个人会以为这条参数在守什么**：`theme-four-states` 这一项今天
**没有刺激**——它点四下、什么都不发生、然后断言标注没变。定向破坏 S1（见下表）实测到
了这件事：一发能让另外两条参数全红的子弹，打在主题这条上是绿的。

它仍然留在参数表里，不是凑数：结构要求（上面那一节）要的是「表现层变更」这个**参数轴**，
主题是这个轴上第一个会被接上的取值。为了不让它静默空转，本模块给每个参数加了一项
`stimulus_moves` 的**前置守卫**：主题这条断言的是「今天点它，iframe 的呈现**不变**」。
**4A 把主题接上电的那一天，这条守卫会红——那是正确的红**，改法是把
`stimulus_moves` 翻成 `True` 并复核 Law 那一半仍然绿，不是删掉守卫。

登记为新欠账（见本模块的回报）：四个主题格子要么接上电，要么连同 testid 一起删——形态与
欠账 #11 的 `rd-page-prev` / `rd-page-next` 完全相同（有 testid、有样式、永久不起作用）。

-------------------------------------------------------------------------------
⚠️ **实测订正三：字号 / 间距的改动落到 iframe 上要慢一拍（生产缺陷，未修）**
-------------------------------------------------------------------------------
`reader.html` 的字号 / 间距处理器是：

    fontSize--;
    applySettings();   // → Reader3Epub.applyThemeSettings() → ensureContentStyles()
    saveSettings();    // ← 新值到这一行才写进 localStorage

而 `epub-renderer.js` 的 `buildContentCss()` 是从 **localStorage** 读
`reader3-font-settings` 的。于是每次注进 iframe 的 CSS 都是**上一档**的值。实测
（2026-09-04，间距连点 −−++，base 1.9 × 17px = 32.3px）：

    base            lineHeight 32.3px
    减小间距 #1     lineHeight 32.3px   ← 没动
    减小间距 #2     lineHeight 30.6px   ← 这才是 #1 的 1.8
    增大间距 #1     lineHeight 28.9px   ← 这是 #2 的 1.7
    增大间距 #2     lineHeight 30.6px

字号同形：第一次点「减小字号」外层读数 17→16，iframe 仍是 17px；第二次点才变成 16px。
**这是生产缺陷（用户点一下没反应），不是本模块的构造问题**，§0.5 明令只记录不修。

它对本模块有一个具体后果：**「一档」的参数必须是两步（`−` 再 `+`），不能只点一步。**
只点一步时 iframe 的呈现根本不变，`stimulus_moves=True` 那条守卫会红——而它红得有道理，
因为那一步确实什么都没施加到被测的那一层上。两步之后 iframe 停在「差一档」的位置
（字号 16px / 间距 1.8），是一次**真实发生过**的重排。

-------------------------------------------------------------------------------
**加载期的双重重绘（欠账 #16）：为什么 `_open_ch0` 要等网络静默**
-------------------------------------------------------------------------------
一次页面加载会跑**两遍** `loadAndRender()`——`annotations.js` 在 `onContentsReady` 里当场
一次，外加 `reader3:content:rendered` 触发的 80ms 去抖第二次。第二遍先
`clearExistingAnnotationMarks()` → `normalize()`，再重建**数量完全相同**的 `<mark>`，所以
「等 `<mark>` 数量到位」这个判据在结构上看不见它。完整实测记在
`tests/e2e/baseline_1b/test_write_recolor_and_delete.py` 的 `_open_ch0` docstring 里
（那是它的定义处，本模块不复述）。

**本模块直接暴露在这个窗口下**：它开章 → 读 `<mark>` 文本 → 开始交互。所以本模块的
`_open_ch0` 照抄同一条纪律——`to_have_count(1)` → `wait_for_load_state("networkidle")` →
再 `to_have_count(1)`。等的是可观测条件，不是 sleep。

**表现层变更本身不触发重绘**（实测）：`applyThemeSettings()` 只是同步改写 iframe 里那个
`#reader3-epub-theme` 的 `<style>`，既不重新 `fetch /api/notes/`，也不碰 `<mark>`。
每步之后仍然各等一次 `networkidle`，是为了让「哪天有人把重绘接到主题上」表现为一次
确定的等待，而不是一次竞态。

-------------------------------------------------------------------------------
**期望值是字面量（§0 第五条纪律）**
-------------------------------------------------------------------------------
矩阵原文写「记录其 `<mark>` 文本 → 每次切换后断言不变」。照字面写就是拿**运行期读回来的
值**当守恒断言的基准，正是 §0 第五条纪律点名的反例：两边同源，实现把整条记录换成别的
东西、只要换得一致，它照样绿。

本模块的写法是：`R6A_EXPECTED_MARK_TEXT` 写死字面量 → 开章后**先断起点等于它**（前置
条件，失败即说明 seed 或渲染在起跑线上就错了）→ 之后每一步都断等于**同一个字面量**。
「记录再比对」的语义一点没丢，只是基准从运行期读数换成了写在用例里的常量。
同理 `R6A_ID` / `R6A_CREATED_AT` 也写死，失败消息里于是是人认得出的名字，而不是两串 uuid。

-------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-04，改动全部已还原）**
-------------------------------------------------------------------------------
本条是特征化用例——被测行为上线数月，**红不可得**。S1 打在生产代码上（改完当场还原），
S2 打在用例自己的期望值上。两次都实跑，下面是**逐字**转录的输出。

| # | 破坏点 | 结果 | 它证明了什么 |
|---|---|---|---|
| S0 | `ensureContentStyles` 首行加 `doc.body.innerHTML = doc.body.innerHTML;`（简报字面建议的那一发） | **三条全绿——这一发打不动本条** | 见下方「S0 为什么是绿的」。它不是本条的可失败性证据，是一条关于 `<mark>` 的真实性质 |
| S1 | `ensureContentStyles` 首行改成把 iframe 里所有 `<mark>` 就地拆掉（保留文字、删掉标记），即「`applyThemeSettings` 重建了内容却没重绘标注」 | **font-size / paragraph-spacing 红，theme 绿** | Law 的判据真的咬住「重排之后 `<mark>` 还在不在」；**同时证明 theme 这条参数今天没有刺激**——同一发子弹打不动它 |
| S2 | `R6A_EXPECTED_MARK_TEXT` 由 `"Alpha prose"` 改成 `"Alpha pros"` | **三条全红** | 三个参数各自的断言都不空转，包括没有刺激的 theme 那条（它至少证明自己在读真的 DOM，而不是在比两个常量） |

**S0 为什么是绿的（一条值得记下来的性质）**：`innerHTML` 的往返是**序列化再解析**，
`<mark data-testid="rd-anno-span">` 会被原样写进字符串、再原样解析回来。所以「重建 DOM」
并不等于「丢掉标注」——只要重建的输入是**当前** DOM 而不是章节原始 XHTML，标注是活得下来
的。真正会丢标注的重建是从原始内容重新渲染。S1 因此改成直接拆掉 `<mark>`，那才是
「重建内容却没重绘标注」的可观测等价物。

**S1 逐字输出**（`theme-four-states` 同一轮 passed）::

    E           AssertionError: 施加「字号 −（减小一档）」之后，iframe 里的 `rd-anno-span` 由 1 个变成 0 个。
    E                 表现层变更把标注整个抹掉了——`applyThemeSettings` 重建了 iframe 内容却没有重绘标注？
    E                 参数：字号 ±（相对当前值，不依赖具体档位数）
    E           assert 0 == 1
    E            +  where 0 = count()
    E            +    where count = <Locator frame=<Frame name= url='http://127.0.0.1:63484/read/smoke_data/0'> selector='[data-testid="rd-viewport"] iframe >> internal:control=enter-frame >> internal:testid=[data-testid="rd-anno-span"s]'>.count
    E           AssertionError: 施加「段落间距 −（减小一档）」之后，iframe 里的 `rd-anno-span` 由 1 个变成 0 个。
    E                 表现层变更把标注整个抹掉了——`applyThemeSettings` 重建了 iframe 内容却没有重绘标注？
    E                 参数：段落间距 ±（相对当前值，不依赖具体档位数）
    E           assert 0 == 1
    E            +  where 0 = count()
    E            +    where count = <Locator frame=<Frame name= url='http://127.0.0.1:63484/read/smoke_data/0'> selector='[data-testid="rd-viewport"] iframe >> internal:control=enter-frame >> internal:testid=[data-testid="rd-anno-span"s]'>.count
    2 failed, 1 passed in 3.45s

注意两条都红在**第一步**（`−`）而不是第二步：拆 `<mark>` 是在 `ensureContentStyles` 里做的，
它每次点击都跑，与「实测订正三」那个慢一拍的缺陷无关——慢一拍的是**样式值**，不是这次调用
本身发不发生。

**S2 逐字输出**::

    E       AssertionError: 起跑线就不对：第 0 章的 `rd-anno-span` 覆盖的文本是 'Alpha prose'，期望 'Alpha pros'。这不是表现层变更造成的——一次表现层动作都还没施加。seed 的 quote（'Alpha prose'）与 R6A_EXPECTED_MARK_TEXT 对不上，或 `render()` 的分段算错了。
    E       assert 'Alpha prose' == 'Alpha pros'
    E         - Alpha pros
    E         + Alpha prose
    E         ?           +
    3 failed in 3.08s

三次破坏各自单跑、逐次还原；还原后 `git diff --stat -- src/ designs/ scripts/
tests/e2e/conftest.py tests/e2e/helpers.py` 无输出，本模块复跑 3 passed。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple

import pytest
from playwright.sync_api import FrameLocator, Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    open_reader,
    seed_notes,
)

pytestmark = pytest.mark.baseline_1b


CH0_INDEX = 0

# ---------------------------------------------------------------------------
# seed（§0 第五条纪律：id / created_at / 期望文本全部写死）
# ---------------------------------------------------------------------------

#: 预置那条标注的 id。写死而不是让 `seed_notes` 生成 uuid：失败消息里要出现一个人认得出
#: 的名字，而不是一串谁也不认识的十六进制。
R6A_ID = "wi14-r6a-anchor"

R6A_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: `prefix` / `suffix` 全空 ⇒ `findRange` 只剩 `indexOf(quote)` 一条路，锚定链上少一个
#: 会自己纠错的环节。第 0 章的连续文本轴是 `"OneAlpha prose."`，`"Alpha prose"` 唯一命中。
R6A_QUOTE = CH0_QUOTE

#: 期望：`<mark>` 覆盖的文本。**独立写一遍字面量，不写 `R6A_QUOTE`。**
#: 这条判据的输入与期望是同一段文字（往返形状），从输入派生期望等于拿自己比自己——
#: 两侧同步变，用例照样绿；S2 那一枪也就打不下去了。
R6A_EXPECTED_MARK_TEXT = "Alpha prose"

#: 起跑线上应当只有这一个 `<mark>`。多一个就说明 seed 或 `render()` 的分段出了问题，
#: 而那种情况下 `text_content()` 会直接抛 strict violation，报出来的东西离原因很远。
R6A_EXPECTED_MARK_COUNT = 1


# ---------------------------------------------------------------------------
# 表现层控件的抓手
# ---------------------------------------------------------------------------
#
# 主题四态有 testid，且是 `<div>` 不是 `<button>`（模块 docstring「实测订正二」）。
THEME_TESTIDS: Tuple[str, ...] = (
    "rd-pref-theme-paper",
    "rd-pref-theme-sepia",
    "rd-pref-theme-green",
    "rd-pref-theme-night",
)

#: 字号与段落间距的 ± 按钮**没有 testid**（欠账 #15，4A 兑付），只能靠 ARIA 可访问名。
#: 名字来自按钮**内容**，不是中文 `title`——完整实测与成因见模块 docstring「实测订正一」。
#: `−` 是 **U+2212 MINUS SIGN**，不是 ASCII `-`。
DECREASE_BUTTON_NAME = "−"
INCREASE_BUTTON_NAME = "+"

#: 两个 ± 对的**容器** testid。限定作用域不是为了让失败消息好看：两个容器里的四个按钮
#: 共用同一对可访问名，不限定容器时 `get_by_role("button", name="−")` 在整页上解析出
#: 2 个节点，strict 模式当场抛。
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


# ---------------------------------------------------------------------------
# 参数：一次表现层变更 ＋ 它的施加方式
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresentationChange:
    """一项表现层参数，连同「怎么施加它」与「施加之后 iframe 上应当动什么」。

    4B.3 的正文栏宽届时是本表的**第四项**，不是新开的一组用例（任务书 §8「一个不成组的
    例外」）。加它的时候只需要填这五个字段，断言主体一个字都不用动。
    """

    #: pytest 的参数 id，ASCII——node id 要能在命令行里直接打出来。
    param_id: str
    #: 中文名，只进失败消息。
    label: str
    #: 施加步骤，`(步骤名, 施加函数)`。**每一步之后都要断一次 Law**，不是做完再断一次：
    #: 「第二次点击把标注弄丢了」在只断终态的写法里是不可见的。
    steps: Tuple[Tuple[str, Callable[[Page], None]], ...]
    #: 这组步骤应当在 iframe body 上改变的 computed style 属性。
    stimulus_props: Tuple[str, ...]
    #: 这组步骤今天到底动不动得了上面那些属性。**这是前置守卫，不是 Law 的一部分**：
    #: 它防的是「参数静默空转」——主题四态今天就是空转的（实测订正二）。
    stimulus_moves: bool


R6A_CHANGES: Tuple[PresentationChange, ...] = (
    PresentationChange(
        param_id="theme-four-states",
        label="主题四态（白色 / 黄色 / 护眼 / 夜间）",
        steps=tuple(
            (f"主题→{testid}", _click_theme(testid)) for testid in THEME_TESTIDS
        ),
        # 主题若被接上电，最先动的就是这两项（`buildContentCss` 里的 `--reader-text`
        # 与 body 背景）。今天它们纹丝不动。
        stimulus_props=("color", "backgroundColor"),
        stimulus_moves=False,
    ),
    PresentationChange(
        param_id="font-size-plus-minus",
        label="字号 ±（相对当前值，不依赖具体档位数）",
        steps=(
            ("字号 −（减小一档）", _click_stepper(SIZE_CONTAINER, DECREASE_BUTTON_NAME)),
            ("字号 +（放大一档）", _click_stepper(SIZE_CONTAINER, INCREASE_BUTTON_NAME)),
        ),
        stimulus_props=("fontSize",),
        stimulus_moves=True,
    ),
    PresentationChange(
        param_id="paragraph-spacing-plus-minus",
        # UI 上的标签是「段落间距」，容器 testid 是 `rd-pref-leading`。矩阵管它叫「行距」
        # ——别沿用，模板里没有叫这个名字的控件，照它去找会找不到。
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
        stimulus_props=("lineHeight",),
        stimulus_moves=True,
    ),
)


# ---------------------------------------------------------------------------
# 本模块私有的三个 helper
# ---------------------------------------------------------------------------
#
# 三个都**刻意留在模块内**：本波（Wave 4）没有任何 WI 被授权改 `tests/e2e/helpers.py`
# （任务书 §0.6 纪律 2：一波至多一个）。哪个该上收、上收的理由是什么，写在本模块的回报里，
# 按欠账 #13 的成例交给下一个被授权改 helpers 的 WI。


def _open_ch0(page: Page, base_url: str) -> FrameLocator:
    """打开第 0 章，等到**两遍**加载期重绘都跑完。

    判据与理由的定义处是 `test_write_recolor_and_delete.py` 的 `_open_ch0` docstring
    （欠账 #16）：一次加载跑两遍 `loadAndRender()`，两遍之后 `<mark>` 数量**完全相同**，
    所以计数断言看不见第二遍；第二遍唯一的外部可观测事件是它那次 `/api/notes/` fetch，
    因此判据是网络静默。数量断言在静默前后各断一次——断的是同一件事，只是第二次断在一个
    不会再变的状态上。
    """
    frame = open_reader(page, base_url, BOOK_ID, CH0_INDEX, CH0_ANCHOR)
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(R6A_EXPECTED_MARK_COUNT)
    page.wait_for_load_state("networkidle")
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(R6A_EXPECTED_MARK_COUNT)
    return frame


def _open_font_popover(page: Page) -> None:
    """点 `rd-rail-font` 打开字体面板，并等它真的可见。

    三个参数的控件都住在这个面板里。面板对**面板内部**的点击不关闭
    （`reader.html` 的 document click 处理器判的是 `popup.contains(e.target)`），所以整条
    用例只开一次；一步一开会把「上一步是不是把面板关掉了」这件事藏进重开动作里。
    """
    page.get_by_test_id("rd-rail-font").click()
    expect(page.get_by_test_id("rd-font-popover")).to_be_visible()


_CONTENT_STYLE_JS = (
    "(body, props) => { const c = getComputedStyle(body); const out = {};"
    " for (const p of props) out[p] = c[p]; return out; }"
)


def _content_style(frame: FrameLocator, props: Tuple[str, ...]) -> Dict[str, str]:
    """iframe body 上那几项 computed style。**只用于前置守卫，不是 Law 的判据。**

    读的是「表现层变更有没有真的落到被测的那一层上」。没有它，一个像主题四态那样**根本
    没有监听器**的控件会让整条参数静默空转——点四下、什么都不发生、然后断言标注没变。
    """
    return frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
        _CONTENT_STYLE_JS, list(props)
    )


# ---------------------------------------------------------------------------
# R-6a
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    R6A_CHANGES,
    ids=[change.param_id for change in R6A_CHANGES],
)
def test_r6a_presentation_change_keeps_the_annotation_on_the_same_text(
    page: Page, live_server: str, e2e_books_dir: Path, change: PresentationChange
) -> None:
    """R-6a（S4，**呈现变换下的锚定不变性**）：改表现层参数，`<mark>` 仍覆盖同一段文字。

    设计规格 §6.0 判定标准的断言 C 的**文本侧**。CFI 侧（断言 a）在
    `tests/e2e/acceptance_4b1/test_r6b_cfi_reanchoring.py`，skip 形态——理由见模块
    docstring 第一节（欠账 #6：`cfi` 恒为 `null`）。

    **seed 的 `cfi` 显式写 `None`**，与生产今天产出的记录逐字段同形。这不是省事：写一个
    手搓的 CFI 进去，本条就会去走 `AnnotationRenderer.render()` 里那条**今天是死代码**的
    分支（欠账 #8），于是它特征化的不再是生产的行为。

    三条判据，前两条**每一步之后**都断：

      1. `rd-anno-span` 恰好 1 个。表现层变更把标注整个抹掉时，这一条先响——比让
         `text_content()` 在 strict 模式上抛出来离原因近得多。
      2. 它覆盖的文本 == `R6A_EXPECTED_MARK_TEXT`（**字面量**，§0 第五条纪律）。这是 Law。
         「差一个字」「偏移了一位」都在这里显形，而「有 1 个 `<mark>`」对它们全是盲的。
      3. 前置守卫（每个参数一次，不是每步一次）：这组步骤在 iframe 上引起的呈现变化，
         与 `change.stimulus_moves` 声明的一致。它防的是参数静默空转——主题四态今天就是
         空转的，而空转的参数会让 (1)(2) 变成对着一张没动过的页面做的两句恒真。
         **每个参数一次**是因为字号 / 间距有「慢一拍」的生产缺陷（模块 docstring 实测
         订正三）：第一步落到 iframe 上的是**旧值**，逐步断会红在一个与锚定无关的地方。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": R6A_ID,
                "chapter_index": CH0_INDEX,
                "type": "marker",
                "color": "yellow",
                "quote": R6A_QUOTE,
                "prefix": "",
                "suffix": "",
                # 与生产今天产出的记录同形。见本函数 docstring 第二段。
                "cfi": None,
                "created_at": R6A_CREATED_AT,
            }
        ],
    )

    frame = _open_ch0(page, live_server)
    span = frame.get_by_test_id("rd-anno-span")

    # 起跑线：一次表现层动作都还没施加，此时就不对的话，后面每一步的红都指错方向。
    assert span.count() == R6A_EXPECTED_MARK_COUNT, (
        f"起跑线就不对：第 0 章有 {span.count()} 个 `rd-anno-span`，"
        f"期望 {R6A_EXPECTED_MARK_COUNT} 个。seed 的那条（id={R6A_ID!r}）没渲染出来，"
        "或者 `render()` 把它切成了多段。"
    )
    assert span.text_content() == R6A_EXPECTED_MARK_TEXT, (
        f"起跑线就不对：第 0 章的 `rd-anno-span` 覆盖的文本是 {span.text_content()!r}，"
        f"期望 {R6A_EXPECTED_MARK_TEXT!r}。这不是表现层变更造成的——一次表现层动作都还没施加。"
        f"seed 的 quote（{R6A_QUOTE!r}）与 R6A_EXPECTED_MARK_TEXT 对不上，"
        "或 `render()` 的分段算错了。"
    )

    before_style = _content_style(frame, change.stimulus_props)

    _open_font_popover(page)

    for step_label, apply_step in change.steps:
        apply_step(page)
        # 表现层变更本身不重新拉 `/api/notes/`（实测），所以这一句通常立刻返回。留着它，
        # 是为了让「哪天有人把重绘接到主题上」表现为一次确定的等待，而不是一次竞态。
        page.wait_for_load_state("networkidle")

        assert span.count() == R6A_EXPECTED_MARK_COUNT, (
            f"施加「{step_label}」之后，iframe 里的 `rd-anno-span` 由 "
            f"{R6A_EXPECTED_MARK_COUNT} 个变成 {span.count()} 个。\n"
            "    表现层变更把标注整个抹掉了——`applyThemeSettings` 重建了 iframe 内容却没有"
            "重绘标注？\n"
            f"    参数：{change.label}"
        )
        assert span.text_content() == R6A_EXPECTED_MARK_TEXT, (
            f"施加「{step_label}」之后，`rd-anno-span` 覆盖的文本变成了 "
            f"{span.text_content()!r}，期望恒为 {R6A_EXPECTED_MARK_TEXT!r}。\n"
            "    锚定跟着布局漂了——纯文本锚定本不该依赖行盒 / 列宽 / 字号。\n"
            f"    参数：{change.label}"
        )

    after_style = _content_style(frame, change.stimulus_props)
    moved = after_style != before_style
    assert moved == change.stimulus_moves, (
        f"前置守卫：参数「{change.label}」施加完 {len(change.steps)} 步之后，iframe body 上的 "
        f"{list(change.stimulus_props)} "
        f"{'变了' if moved else '没变'}，而本参数声明的是 "
        f"{'会变' if change.stimulus_moves else '不会变'}。\n"
        f"    变更前：{before_style}\n    变更后：{after_style}\n"
        "    ——若是主题这条转为「变了」：4A 把四个主题格子接上电了。这是**正确的红**，\n"
        "      改法是把该项的 `stimulus_moves` 翻成 True 并复核上面 Law 那一半仍然绿，\n"
        "      不是删掉本守卫（守卫一删，这条参数就退回静默空转，见模块 docstring 订正二）。\n"
        "    ——若是字号 / 间距这条转为「没变」：表现层通道断了，此时上面那两条 Law 断言\n"
        "      正在对着一张没动过的页面空转，它们的绿不作数。"
    )
