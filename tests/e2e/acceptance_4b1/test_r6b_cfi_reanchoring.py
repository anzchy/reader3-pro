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
⚠️ **刺激必须自证：一步「施加」如果什么都没动，它的绿不算数**（2026-09-05 审计发现 #53）
-------------------------------------------------------------------------------
本节是本模块 2026-09-05 唯一一次结构性改动的全部理由，改它之前先读完。

审计发现 #53 点的是一句空洞：**「表现层变了之后 CFI 仍解得回同一段文字」这句断言，在
表现层根本没变的时候是恒真的**。本模块此前的写法是「点一下 → `wait_for_load_state` →
解析 CFI → 比对文本」，从头到尾没有任何一句在读**呈现本身**。于是三类东西可以毫发无伤
地穿过它：

1. **坏掉的步进器**——按钮被谁 `stopPropagation` 掉了、handler 抛在第一行、`disabled`
   卡在边界（字号 14…24、间距 1.5…2.5，撞到边界时按钮真的会 `disabled`）。点击照常发生、
   照常返回，CFI 当然还解得回原文，因为 DOM 一个字节都没动过。
2. **今天就是纯装饰的主题四态**（下面「实测前情」第二条）：全仓无监听器，点四下等于点了
   四下空气。它贡献的那条绿是纯粹的空转。
3. **慢一拍的字号 / 间距**（第三条）：只点一步时改动落不到 iframe 上，那一步的 CFI 断言
   同样是对着一张没动过的页面做的。

改法有两条，本模块**两条都用**，因为它们各自覆盖上面不同的行：

* **对「应当能动」的参数（字号 / 间距）**：把一步「施加」重新定义成**自证的刺激**——
  `_apply_until_moved()` 先读一份 iframe body 的 computed style 作基线，然后**点一下、
  轮询到它变了为止**；`STIMULUS_MAX_CLICKS` 次之内没变就抛，消息点名基线值、当前值、
  点了几下。这一句排在 CFI 两句断言的**前面**：没有它先说话，后面那两句就没有主语。
  顺带地，它把「慢一拍」从一条要靠人记住的注记变成了**运行期自适应**——今天第一步要点
  两下、第二步一下（数据见第三条），欠账 #22 修好之后各一下，用例不必跟着改。
  ⚠️ 别把它换回「固定点两下再断终态」：第二步（`+`）从**已经偏移过的**基线出发，一下就
  变，固定两下反而会绕回原值，判据当场自欺。
* **对「今天动不了」的主题四态**：**显式排除在 Law 之外**（`excluded_because` 字段），
  不假装它在守什么。这一条参数今天只做一件事——断言那四个格子**仍然是死的**
  （施加完四步，`color` / `backgroundColor` 一个字节没动）。它**不跑 CFI 那两句**：
  跑了也只是再产出一条「没发生的变更没能弄坏 CFI」的空绿，而那正是发现 #53 说的那种
  绿。排除是**写在数据里、进失败消息**的，不是藏在一个悄悄什么都不做的刺激里。
  **4A 把主题接上电的那一天，这条排除守卫会红——那是正确的红**：改法是把
  `excluded_because` 置 `None`（该参数自动并入上面那条自证刺激的路径），不是删守卫。

**这一次改动没有删掉、也没有放宽任何一句既有断言。** `stored_cfi is not None`、
`result["ok"]`、`result["text"] == R6B_EXPECTED_RANGE_TEXT` 三句逐字仍在，只是前面多了一句
「刺激真的发生过」的前置条件。唯一的减法是主题那条参数不再执行后两句——而按 R-6a 的定向
破坏 S1 实测，它执行的那两句在今天**可证明地是空的**（一发能让另外两条参数全红的子弹，
打在主题上是绿的）。

-------------------------------------------------------------------------------
**兑付时怎么解开这三条**
-------------------------------------------------------------------------------
1. 欠账 #6 修好（`currentContents` 存真正的 `Contents`，或另给一条拿得到 `cfiFromRange`
   的路），确认新建标注的 `cfi` 不再是 `null`。
2. 删掉模块级 `pytest.mark.skip`，跑本模块。
3. 条数常量**不必再改**：欠账 **#14** 已由 WI-17 结清，`scripts/lint_e2e_groups.py` 的
   `EXPECTED_ACCEPTANCE_PER_DIR["acceptance_4b1"]` 按 8 计（R-6b 3 ＋ K-1b ＋ K-6b ＋ W-5b 3），
   解 skip 只是让这三条从 skipped 变 passed，不改收集条数。**主题那条走的是排除路径**
   （上一节），它变绿证明的是「四个格子仍然是死的」，不是「CFI 扛住了主题切换」——
   别把它读成后者。
4. 若第 1 步之后 `range.toString()` 与 `quote` 对不上（差空白、差首尾一两个字符），
   那是**真红**：CFI 的 `toRange` 与我们建它时用的 Range 之间存在偏移，别改期望值去迁就，
   先看 `annotations.js` 建 CFI 时传的是不是同一个 Range。
5. 若红在 `_apply_until_moved` 那一句（「点了 N 下，iframe 上的 … 一个字节没动」），
   **先别看 CFI**：那是表现层通道自己断了（按钮改了标记、accname 变了、值撞到 14/24 或
   1.5/2.5 的边界、慢一拍恶化成慢两拍）。此时 CFI 那两句就算绿也不作数。

-------------------------------------------------------------------------------
**给解 skip 的人的三条实测前情**（全部来自 R-6a 那一侧，2026-09-04）
-------------------------------------------------------------------------------
* **`±` 四个按钮的可访问名是 `−`（U+2212）与 `+`，不是中文 `title`。** 任务书和矩阵写的
  `减小字号` / `放大字号` / `减小间距` / `增大间距` 一个都匹配不上（accname 取内容，
  `title` 只是兜底）。而且两个容器里的四个按钮**共用同一对名字**，不按容器 testid 限定
  作用域会解析出 2 个节点、strict 模式当场抛。完整实测见 R-6a 模块 docstring 「实测订正一」。
* **四个主题格子今天是纯装饰**（模板自己的 CSS 写着 `/* Theme selector (UI only for v1) */`
  与 `cursor: not-allowed`），全仓无监听器。所以 `theme-four-states` 这一项在兑付前
  **没有刺激**——本模块因此把它**显式排除**在 Law 之外（见上一节），而不是让它「因为什么
  都没发生所以过了」。
* **字号 / 间距的改动落到 iframe 上慢一拍**（`applySettings()` 先跑、`saveSettings()` 后写，
  而 CSS 是从 localStorage 读的）。R-6a 实测（间距连点 `−−++`，base 1.9 × 17px = 32.3px）::

      base            lineHeight 32.3px
      减小间距 #1     lineHeight 32.3px   ← 没动
      减小间距 #2     lineHeight 30.6px   ← 这才是 #1 的 1.8
      增大间距 #1     lineHeight 28.9px   ← 这是 #2 的 1.7
      增大间距 #2     lineHeight 30.6px

  这是生产缺陷（用户点一下没反应），§0.5 只记录不修，欠账 **#22** 兑付。R-6a 的应对是把
  「一档」写死成两步；**本模块不复制那个写法**——`_apply_until_moved()` 点到动为止，于是
  今天第一步自然点两下、第二步（从已偏移的基线出发）一下就够，欠账 #22 修好之后各一下，
  本模块一个字都不用改。**不要在这里跟着 R-6a 改成固定两步**：第二步固定两下会绕回原值。

-------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-05，改动全部已还原）**
-------------------------------------------------------------------------------
本模块是 skip 形态，**跑它什么都不证明**——所以这一轮不是「跑一遍看看绿不绿」。做法：
把本模块里那个**同一个函数对象** import 进一个临时模块（模块级 `pytestmark` 属于原模块，
不随函数过来，于是它在临时模块里真的会跑），子弹一律打在 `page.add_init_script` 上。
**`src/` 一行没改**（收工时 `git diff --quiet -- src/` 无输出），模块级 skip 已复位。

因为解锁条件 `stored_cfi is not None` 今天必红（欠账 #6），每一发前面都要先垫一发
**U（unblock）**：把 `Reader3Epub.getContents()` 的返回值包一层，补上
`cfiFromRange = (r) => new ePub.CFI(r, section.cfiBase).toString()`。**U 是脚手架，不是判据**
——见下面 D2 的脚注，它造出来的那一串与欠账 #6 真兑付后 `Contents.cfiFromRange` 产出的
不是同一个东西。

| # | 破坏点 | 结果 | 它证明了什么 |
|---|---|---|---|
| U | init script：给 `getContents()` 的返回值补 `cfiFromRange` | `stored_cfi is not None` 转绿 | 只是解锁，让子弹能打到本节要证的那几句上 |
| D0 | **HEAD 那一版**（`git show HEAD:… > zz_old53.py`）分别在「有 D1 子弹」与「无 D1 子弹」下各跑一次 | **两次输出逐字相同**（`3 failed`，同一条 `IndexSizeError`，同一行） | 发现 #53 的本体：**旧版对这发子弹完全不可见**——步进器是死是活，它的判决一个字节都不变 |
| D1 | U ＋ init script：document 捕获相位吃掉 `rd-pref-size` / `rd-pref-leading` 里的 click（**坏掉的步进器**） | `1 passed, 2 failed`，两条**红在新加的那一句**上；`theme` 走排除路径照常 passed | 新守卫真的咬住「点了但什么都没动」。同一发子弹在 D0 里是隐形的 |
| D2 | 只有 U（**真步进器**） | `_apply_until_moved` **一次都没抛**；红转移到既有的 `page.evaluate(_REANCHOR_JS, …)` | 守卫不是恒红：真控件过得去，且后面红的不是我加的那一句 |
| D3 | init script：给 `rd-pref-theme-night` 挂一个真的会改 iframe body `color` 的监听器（**把主题接上电**） | `theme-four-states` **红在排除守卫**上 | 那条排除是**活的闹钟**，不是一句注释：控件一接上电它当场喊 |

**D1 逐字输出**（`theme-four-states` 同一轮 passed）::

    E       AssertionError: 施加「字号 −（减小一档）」时，刺激没有发生：连点 3 下之后，iframe body 上的 ['fontSize'] 仍然是 {'fontSize': '17px'}，与点之前一个字节不差。
    E           参数：字号 ±（相对当前值，不依赖具体档位数）
    E           这一步什么都没施加到被测的那一层上，所以它后面那两句 CFI 断言即使全绿也不作数
    E           （「表现层变了之后 CFI 仍解得回原文」在表现层根本没变时是一句恒真）。
    E           排查顺序：控件的抓手（accname / 容器 testid）变了？handler 抛了？值撞到边界被 disabled 了
    E           （字号 14…24、间距 1.5…2.5）？还是「慢一拍」恶化成了慢 3 拍以上（欠账 #22）？
    E       AssertionError: 施加「段落间距 −（减小一档）」时，刺激没有发生：连点 3 下之后，iframe body 上的 ['lineHeight'] 仍然是 {'lineHeight': '32.3px'}，与点之前一个字节不差。
    E           参数：段落间距 ±（相对当前值，不依赖具体档位数）
    …（后四行与上一条同）
    2 failed, 1 passed

**D2 的正面证据**（单跑 `_apply_until_moved` 驱动全部四步刺激，把 before → after 打出来；
`-s` 实测输出逐字）::

    [probe] theme-four-states: 排除路径，跳过刺激驱动
    [probe] font-size-plus-minus / 字号 −（减小一档）: {'fontSize': '17px'} -> {'fontSize': '16px'}
    [probe] font-size-plus-minus / 字号 +（放大一档）: {'fontSize': '16px'} -> {'fontSize': '15px'}
    [probe] paragraph-spacing-plus-minus / 段落间距 −（减小一档）: {'lineHeight': '28.5px'} -> {'lineHeight': '30.4px'}
    [probe] paragraph-spacing-plus-minus / 段落间距 +（增大一档）: {'lineHeight': '30.4px'} -> {'lineHeight': '28.8px'}

**四步全部真的动了**，而且这份读数正是「点到动为止」优于「固定两步」的实证：`−` 那一步要
点两下（第一下落的是旧值，慢一拍），`+` 那一步从**已经偏移过的**基线出发，一下就变——
固定两下会把它推回原处，判据当场自欺。（`lineHeight` 的基线是 28.5px 而不是 R-6a 记的
32.3px，因为探针在同一页上先跑完了字号那一组，行高 = 15px × 1.9。这恰恰是这两个参数写成
「相对当前值」而不是绝对档位的理由。）

**D2 的红在哪里**：走完刺激之后，`page.evaluate(_REANCHOR_JS, stored_cfi)` 抛
``IndexSizeError: Failed to execute 'setEnd' on 'Range': There is no child at offset 11``。
**这一行是本模块既有的代码，不是我加的**，而且这条红属于**脚手架 U**，不属于生产：U 是在
`render()` 把 quote 包进 `<mark>` **之前**用 live range 造的 CFI，包完之后那条节点路径自然
指不回去。**解 skip 的人不要把它当成已知失败**——欠账 #6 真兑付后要在真的 `Contents` 上
重测一遍，那正是上面「兑付时怎么解开这三条」第 4、5 步说的事。

**D3 逐字输出**::

    E       AssertionError: 参数「主题四态（白色 / 黄色 / 护眼 / 夜间）」被声明为**今天排除在 Law 之外**，但施加完 4 步之后 iframe body 上的 ['color', 'backgroundColor'] 变了。
    E             变更前：{'color': 'rgb(51, 51, 51)', 'backgroundColor': 'rgba(0, 0, 0, 0)'}
    E             变更后：{'color': 'rgb(1, 2, 3)', 'backgroundColor': 'rgba(0, 0, 0, 0)'}
    E             排除理由（本参数的 `excluded_because`）：四个主题格子今天是纯装饰（…）
    E             ——控件被接上电了。这是**正确的红**：改法是把该项的 `excluded_because` 置 None，

四发子弹各自单跑、逐次还原；临时模块与 `zz_old53.py` 已删，`git diff --quiet -- src/` 无输出，
模块级 skip 在位，`tests/e2e/acceptance_4b1 --collect-only` 仍为 8 条。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import pytest
from playwright.sync_api import FrameLocator, Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    content_style,
    open_ch0,
    open_font_popover,
    select_in_frame,
    wait_for_notes,
)

#: 组标记 ＋ 模块级 skip。skip 挂在**模块级**而不是逐条：三条被同一个欠账挡住，
#: 逐条挂会让「阻塞者是同一个」这件事在三处各写一遍，兑付时漏删一处就是一条静默跳过。
#: （`scripts/lint_e2e_groups.py` 的 skip 轴静态检查也只认这一处：本模块里再出现第二个
#: skip 构造——包括 `pytest.param(marks=pytest.mark.skip(...))`——分组闸当场红。主题四态
#: 那条参数因此走**数据字段**排除，不走 marker，见 docstring「刺激必须自证」一节。）
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


#: 主题四态今天被**排除在 Law 之外**的理由，一个字符串常量。它进失败消息，也是给
#: 4A 的兑付指令：接上电之后把 `excluded_because` 置 `None`，该参数自动并入自证刺激路径。
THEME_EXCLUSION_REASON = (
    "四个主题格子今天是纯装饰（模板 CSS 自称 `/* Theme selector (UI only for v1) */`、"
    "`cursor: not-allowed`，全仓无监听器），点它们不产生任何表现层变更。"
    "让它跑 CFI 那两句只会得到一条『没发生的变更没能弄坏 CFI』的空绿（审计发现 #53），"
    "所以本参数今天只断『那四个格子仍然是死的』。4A 接上电时：把 excluded_because 置 None。"
)


# ---------------------------------------------------------------------------
# 刺激自证的三个旋钮（审计发现 #53）
# ---------------------------------------------------------------------------

#: 一步刺激最多点几下。**上界不是随手取的**：`reader.html` 的字号钳在 14…24（默认 17）、
#: 间距钳在 1.5…2.5（默认 1.9），到边界时 `applySettings()` 会把按钮置 `disabled`，
#: 而点一个 disabled 的按钮在 Playwright 里表现为 30s 可操作性超时——一条离原因很远的红。
#: 3 下从默认值出发撞不到任何一侧边界，同时给「慢一拍」（需要 2 下）留了一下的余量。
STIMULUS_MAX_CLICKS = 3

#: 单次点击之后等呈现变化的上限。`applySettings()` → `applyThemeSettings()` →
#: `ensureContentStyles()` 是**同步**跑完的，所以会变的话在 `.click()` 返回时就已经变了；
#: 这一段窗口是给「哪天有人把它改成异步」留的余量，不是预期路径。
STIMULUS_SETTLE_TIMEOUT_MS = 1000

#: 轮询节拍。用 `page.wait_for_timeout` 而不是 `time.sleep`：同步 API 只有在等 Playwright
#: 自己的操作时才把浏览器那边的事件泵到本进程（与 `helpers.wait_for_write_activity_settled`
#: 同款理由）。
STIMULUS_POLL_INTERVAL_MS = 25


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
class PresentationStep:
    """一步表现层刺激：一个中文步骤名 ＋ **一次**点击。

    「一次点击」是刻意的：一步刺激实际要点几下由 `_apply_until_moved()` 在运行期决定
    （点到呈现真的动了为止）。把「慢一拍要点两下」写死进步骤表，等于把一个生产缺陷
    （欠账 #22）焊进用例——它修好那天用例反而要改，而且第二步固定两下会绕回原值。
    """

    label: str
    click: Callable[[Page], None]


@dataclass(frozen=True)
class PresentationChange:
    """一项表现层参数，连同「怎么施加它」「施加之后 iframe 上应当动什么」。

    **刻意不从 `baseline_1b` 那个模块 import**：两个目录下都没有 `__init__.py`
    （`.gitkeep` 里写明了原因），跨目录的裸模块 import 只有在两个目录**同时被收集**时
    才碰巧成立；单跑 `pytest tests/e2e/acceptance_4b1` 会 ImportError。这点重复换来的是
    本模块单独可跑。（形状与 R-6a 的同名结构体**已不再一致**：R-6a 的 `stimulus_moves:
    bool` 在这里换成了 `excluded_because: str | None`——两个字段的真值面相同，但这里要的
    是那个「为什么」的字符串，它要进失败消息。）
    """

    #: pytest 的参数 id，ASCII——node id 要能在命令行里直接打出来。
    param_id: str
    #: 中文名，只进失败消息。
    label: str
    #: 施加步骤。**每一步之后都要断一次 Law**，不是做完再断一次：
    #: 「第二次点击把 CFI 指飞了」在只断终态的写法里是不可见的。
    steps: Tuple[PresentationStep, ...]
    #: 这组步骤应当在 iframe body 上改变的 computed style 属性。刺激自证读的就是它。
    stimulus_props: Tuple[str, ...]
    #: `None` ⇒ 本参数今天必须**真的**改变 `stimulus_props`，否则红（审计发现 #53）。
    #: 非 `None` ⇒ 本参数今天被**显式排除**在 Law 之外，字符串是理由，会进失败消息；
    #: 该参数改为只断「控件仍然是死的」，不跑 CFI 那两句。
    excluded_because: Optional[str] = None


R6B_CHANGES: Tuple[PresentationChange, ...] = (
    PresentationChange(
        param_id="theme-four-states",
        label="主题四态（白色 / 黄色 / 护眼 / 夜间）",
        steps=tuple(
            PresentationStep(f"主题→{testid}", _click_theme(testid))
            for testid in THEME_TESTIDS
        ),
        # 主题若被接上电，最先动的就是这两项（`buildContentCss` 里的 `--reader-text`
        # 与 body 背景）。今天它们纹丝不动，所以本参数走排除路径。
        stimulus_props=("color", "backgroundColor"),
        excluded_because=THEME_EXCLUSION_REASON,
    ),
    PresentationChange(
        param_id="font-size-plus-minus",
        label="字号 ±（相对当前值，不依赖具体档位数）",
        steps=(
            PresentationStep(
                "字号 −（减小一档）", _click_stepper(SIZE_CONTAINER, DECREASE_BUTTON_NAME)
            ),
            PresentationStep(
                "字号 +（放大一档）", _click_stepper(SIZE_CONTAINER, INCREASE_BUTTON_NAME)
            ),
        ),
        stimulus_props=("fontSize",),
    ),
    PresentationChange(
        param_id="paragraph-spacing-plus-minus",
        # UI 标签是「段落间距」，容器 testid 是 `rd-pref-leading`。矩阵管它叫「行距」
        # ——模板里没有叫这个名字的控件。
        label="段落间距 ±（相对当前值，不依赖具体档位数）",
        steps=(
            PresentationStep(
                "段落间距 −（减小一档）",
                _click_stepper(LEADING_CONTAINER, DECREASE_BUTTON_NAME),
            ),
            PresentationStep(
                "段落间距 +（增大一档）",
                _click_stepper(LEADING_CONTAINER, INCREASE_BUTTON_NAME),
            ),
        ),
        stimulus_props=("lineHeight",),
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


# ---------------------------------------------------------------------------
# 刺激自证（审计发现 #53：断「CFI 扛住了表现层变更」之前，先证明表现层真的变了）
# ---------------------------------------------------------------------------


def _poll_until_style_changes(
    page: Page,
    frame: FrameLocator,
    props: Tuple[str, ...],
    baseline: Dict[str, str],
) -> Optional[Dict[str, str]]:
    """轮询 iframe body 的 `props`，等到它**不等于** `baseline`；等不到返回 `None`。

    等的是一个可观测条件，不是 sleep：变了就立刻返回，没变就在 `STIMULUS_SETTLE_TIMEOUT_MS`
    到点后交回 `None`，由调用方决定是再点一下还是抛。
    """
    deadline = time.monotonic() + STIMULUS_SETTLE_TIMEOUT_MS / 1000
    while True:
        current = content_style(frame, props)
        if current != baseline:
            return current
        if time.monotonic() > deadline:
            return None
        page.wait_for_timeout(STIMULUS_POLL_INTERVAL_MS)


def _apply_until_moved(
    page: Page,
    frame: FrameLocator,
    change: PresentationChange,
    step: PresentationStep,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """施加一步刺激，**点到 iframe 上的呈现真的变了为止**，返回 `(变更前, 变更后)`。

    `STIMULUS_MAX_CLICKS` 下之内没能让 `change.stimulus_props` 动一个字节 ⇒ 抛。
    这一句必须排在 CFI 两句断言的**前面**：它不成立时，那两句是在一张没动过的页面上做
    的恒真判断（审计发现 #53）。

    「点到动为止」同时是「慢一拍」（欠账 #22）的运行期解——今天 `−` 那一步要点两下、`+`
    那一步（从已经偏移过的基线出发）一下就够；欠账兑付后各一下。两种形态本函数都过，
    用例不必跟着改。
    """
    before = content_style(frame, change.stimulus_props)
    for _ in range(STIMULUS_MAX_CLICKS):
        step.click(page)
        after = _poll_until_style_changes(page, frame, change.stimulus_props, before)
        if after is not None:
            return before, after

    raise AssertionError(
        f"施加「{step.label}」时，刺激没有发生：连点 {STIMULUS_MAX_CLICKS} 下之后，"
        f"iframe body 上的 {list(change.stimulus_props)} 仍然是 {before}，与点之前一个字节不差。\n"
        f"    参数：{change.label}\n"
        "    这一步什么都没施加到被测的那一层上，所以它后面那两句 CFI 断言即使全绿也不作数\n"
        "    （「表现层变了之后 CFI 仍解得回原文」在表现层根本没变时是一句恒真）。\n"
        "    排查顺序：控件的抓手（accname / 容器 testid）变了？handler 抛了？值撞到边界被 disabled 了\n"
        "    （字号 14…24、间距 1.5…2.5）？还是「慢一拍」恶化成了慢 3 拍以上（欠账 #22）？"
    )


def _assert_excluded_control_is_still_inert(
    page: Page, frame: FrameLocator, change: PresentationChange
) -> None:
    """被排除的参数今天唯一要断的事：施加完全部步骤之后，呈现**仍然一个字节没动**。

    它是那条排除的**到期闹钟**。控件哪天被接上电，这一句就红——那是正确的红，改法见
    失败消息与 `excluded_because` 里写的兑付指令，不是删掉本守卫（守卫一删，这条参数就
    退回静默空转，正是审计发现 #53 点名的形态）。
    """
    before = content_style(frame, change.stimulus_props)
    for step in change.steps:
        step.click(page)
    # 这一句通常立刻返回（表现层变更不重新拉 `/api/notes/`）。留着它，是为了让「哪天有人
    # 把重绘接到主题上」表现为一次确定的等待，而不是一次竞态。
    page.wait_for_load_state("networkidle")
    after = content_style(frame, change.stimulus_props)

    assert after == before, (
        f"参数「{change.label}」被声明为**今天排除在 Law 之外**，但施加完 "
        f"{len(change.steps)} 步之后 iframe body 上的 {list(change.stimulus_props)} 变了。\n"
        f"    变更前：{before}\n    变更后：{after}\n"
        f"    排除理由（本参数的 `excluded_because`）：{change.excluded_because}\n"
        "    ——控件被接上电了。这是**正确的红**：改法是把该项的 `excluded_because` 置 None，\n"
        "      让它并入 `_apply_until_moved` 的自证刺激路径并复核 CFI 那两句，\n"
        "      不是删掉本守卫。"
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
    以及兑付时的五步解锁顺序，见模块 docstring。

    四步判据：

      1. **解锁条件**：走一遍真实创建路径之后，落库那条记录的 `cfi` 不是 `None`。
         今天必红（欠账 #6）。这一句红着的时候，下面三步说的都不是关于生产的事。
      2. **刺激自证**（审计发现 #53，排在 CFI 之前是本条判据的全部意义）：每一步「施加」
         都要在 iframe 上留下可观测的痕迹——`_apply_until_moved()` 点到 `stimulus_props`
         真的变了为止，点不动就抛。没有它，一个坏掉的步进器（handler 抛了、点击被吞了、
         值撞到边界被 disabled）会让 (3)(4) 变成对着一张没动过的页面做的两句恒真。
      3. 每施加一步表现层变更，就用 `window.ePub.CFI` 把**磁盘上那一串**重新解析成 Range。
         解不出来（`toRange` 返 `null`）即红——CFI 的节点路径被表现层变更打断了。
      4. `range.toString() == R6B_EXPECTED_RANGE_TEXT`（**字面量**）。这条才是 Law：
         CFI 最坏的坏法不是解析失败，是**安安静静解析到了别的地方**，只有比对文本抓得住。

    第 (2)(3)(4) 步**每一步之后都做**，不是做完所有步骤再做一次：「第二次点击把 CFI 指飞了」
    在只断终态的写法里是不可见的。

    **被排除的参数走另一条路**（今天只有主题四态）：它不跑 (3)(4)，只断「控件仍然是死的」
    ——理由与到期动作见模块 docstring「刺激必须自证」一节和 `THEME_EXCLUSION_REASON`。
    """
    frame = open_ch0(page, live_server)

    # ---- 走真实创建路径，让 CFI 是生产自己生成的那一串（理由见模块 docstring）----
    select_in_frame(frame, CH0_QUOTE)
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-type-marker").click()

    records = wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
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

    # ---- 被排除的参数：只断「控件仍然是死的」，不拿空刺激去喂 Law ----
    if change.excluded_because is not None:
        _assert_excluded_control_is_still_inert(page, frame, change)
        return

    for step in change.steps:
        # (2) 刺激自证，先于 CFI 说话。抛在这里 ⇒ 下面两句根本不该被执行。
        style_before, style_after = _apply_until_moved(page, frame, change, step)
        page.wait_for_load_state("networkidle")

        result: Dict[str, object] = page.evaluate(_REANCHOR_JS, stored_cfi)

        assert result.get("ok"), (
            f"施加「{step.label}」之后，存储的 CFI 解析不回一个 Range 了。\n"
            f"    原因：{result.get('why')}\n"
            f"    CFI：{stored_cfi!r}\n"
            f"    参数：{change.label}\n"
            f"    这一步的刺激是真的（{list(change.stimulus_props)}：{style_before} → {style_after}），\n"
            "    所以这条红说的是生产：表现层变更改动了 DOM 结构（插节点 / 拆文本节点 / 包 span），"
            "把 CFI 记的节点路径打断了。"
        )
        assert result.get("text") == R6B_EXPECTED_RANGE_TEXT, (
            f"施加「{step.label}」之后，存储的 CFI 仍然解析得出 Range，"
            f"但它覆盖的文本是 {result.get('text')!r}，期望恒为 "
            f"{R6B_EXPECTED_RANGE_TEXT!r}。\n"
            f"    CFI：{stored_cfi!r}\n"
            f"    参数：{change.label}\n"
            f"    这一步的刺激是真的（{list(change.stimulus_props)}：{style_before} → {style_after}）。\n"
            "    ——这是 CFI 最坏的那种坏法：不报错，安静地指到了别的地方。"
        )
