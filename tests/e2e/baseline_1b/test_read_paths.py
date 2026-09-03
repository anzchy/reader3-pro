"""WI-12 —— R-1 / R-2 / R-3：读路径基础（书库进入、三种章节导航、章节过滤）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-12（最高权威，用例条数与断言
层级以它为准）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §2（读路径用例
R-1…R-6）、§0（六条写作纪律）、§0.6（波次编排，本模块属 Wave 3）。

**读路径为什么排在写路径之后。** W 系列（WI-3…WI-8）已经把「iframe 内程序化建选区」这条
共享路径跑通并沉淀进 `helpers.py`；R 系列不再需要造选区，只是在同一条渲染链上加断言。

三条用例守的两条律（矩阵原文）：

* **导航机制无关性** —— 三种导航机制到达第 N 章后，`(URL 里的章号, iframe 内渲染的正文)`
  这一对必须相同。任何一种机制单独测都可能掩盖另一种的静默错位。
* **章节过滤是一个全函数** —— 渲染出的标注集合恒等于「`chapter_index == 当前章` 的那些
  条目」，**与 quote 在别章是否也能匹配上无关**。

-------------------------------------------------------------------------------
为什么每条判据不是摆设
-------------------------------------------------------------------------------

**R-1 断的是正文文本，不是「iframe 存在」。** `assert iframe is not None` 在一本空白书上
照样绿；「iframe body 含 `Alpha prose.`」不会。反向那半句
（不含 `Beta prose.`）同样不可省：书卡的 `href` 若指向错的 spine 下标，正向那半句还是红，
但**指向错的书**时正向也可能碰巧绿——所以 URL 的 path 要单独逐字断一次。

**R-2 的每个机制都断 URL 与正文两项，还外加一项「导航的性质」。**

* 只断 URL 会放过「地址变了但内容没换」；
* 只断正文会放过 K6 点名的「静默存错章」；
* 而两项都断**仍然**放过第三种假绿：`rd-chapter-next` 是带 `href` 兜底的 `<a>`，
  `epub-renderer.js` 给它绑的 `click` + `preventDefault()` 一旦坏掉，浏览器会**整页加载**
  到同一个地址，URL 与正文两项全绿而站内导航其实已经死了。这正是矩阵裁决 4 不让 R-4 用
  这两个按钮的理由。本模块的处理不是回避它，而是把「是不是整页加载」变成第三项判据：
  导航前在 `window` 上放一个哨兵，导航后读回来——站内导航时它还在，整页加载时它没了。
  于是三个参数不是「三条通往同一个 URL 的路」，而是**两条站内、一条整页**的三个不同性质。

**R-3 比对 `textContent`，不是数量（§2 原文）。** 「有 N 个 `<mark>`」在高亮画错位置时照样
绿。同时数量那一半也不能丢：文本集合等值对「同一段文字渲染了两遍」是盲的。两者一起断，
才是矩阵列的 (1)(2)。

**R-3 的第二条 seed 故意不在当前章，且它的 quote 在当前章文本里可匹配。** 少了后半句，
「渲染了所有标注」这个错误实现照样能过——它被送进 `render()` 之后 `findRange` 找不到，
于是仍然只有一个 `<mark>`。矩阵 Gap 2 记的就是这个：旧形态的 B 用 `quote="Beta prose"`，
那个串在第 0 章不存在，用例对着一个坏实现是绿的。现在 B 用 `quote="prose"`——`epub_corpus`
的两章正文分别是 `Alpha prose.` 与 `Beta prose.`，**token `prose` 两章都有**，第 0 章的
连续文本轴 `"OneAlpha prose."` 上必然命中 `[9, 14)`。过滤一旦失效，第 0 章一定多出一个
`<mark>`，没有任何巧合可以掩盖。

**R-3 的两条 seed 都写 `cfi=None`。** `AnnotationRenderer.render()` 的第一步是
`annotations.filter(ann => ann?.cfi)`，这批直接 `range.extractContents()/insertNode`，
`findRange` 一次都不会被调用（矩阵 §E）。更要命的是 CFI 跨章无效，一条 ch1 的 CFI 在 ch0
的文档里解析失败后**恰好什么都不渲染**——「过滤失效」这个失败模式会被这个巧合掩盖。
`cfi=None` 是把用例逼回文本回退路径的故障注入，不是图省事。

顺带一提**欠账 6**（`docs/plans/.../009-e2e-annotations.md` §0.6 跨波欠账表）：
`epub-renderer.js` 存进 `currentContents` 的是 epub.js 的 **view** 而不是 `Contents`，
`cfiFromRange` 不存在，`annotations.js` 里那道守卫**永假**，于是**经 UI 创建的标注 `cfi`
恒为 `null`，全部锚定实际都走纯文本路径**。也就是说 R-3 的 `cfi=None` 今天并不是一个人为
的特例，而是全仓唯一活着的那条路径；`render()` 的 CFI 分支今天是死代码（欠账 8）。本模块
只记录，不修——1b 是迁移前的安全网，不是行为变更窗口。

-------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-03，十枪全部已还原）**
-------------------------------------------------------------------------------

本模块三条都是**特征化用例**——被测行为上线数月，红不可得，`tdd-guardian` 的红收据在这里
必然记成 green 并判 `SEPARATION-BROKEN`，成因是「实现早于规格」。§0 第四条纪律因此明令
**不得靠破坏生产代码伪造红**，替代证据是定向破坏**用例自己的期望值**，逐条打靶，每处留档
三样：破坏点、逐字失败输出、还原核验。下表各行的失败输出全部逐字抄自 pytest 的 `E` 行，
**没有一行是预测**；`src/` 与 `designs/` 一行未动，每枪打完都用 `diff` 与打靶前的副本核对过
（十次全部 CLEAN）。

| # | 破坏点（改的都是本文件的期望值） | 失败输出（逐字） | 它证明了哪一条判据不是摆设 |
|---|---|---|---|
| D1 | R-1 的 `SMOKE_BOOK_TITLE` → `"Nineteen Twenty Three"`（两步，见下方详录） | `AssertionError: 语料书名变了：'Nineteen Twenty Two' != 'Nineteen Twenty Three'。R-1 靠 Read {书名} 这个 ARIA 名点进书卡，改语料要一起改这里。` ／ `assert 'Nineteen Twenty Two' == 'Nineteen Twenty Three'`；放宽探针后 `playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.` ／ 调用日志 `waiting for … get_by_role("link", name="Read Nineteen Twenty Three")` | 书卡的 ARIA 名就是这本书的名字——定位不到就点不进去 |
| D2 | R-1 的 URL 期望 `CH0_PATH` → `"/read/smoke_data/1"` | `AssertionError: 从书库点进来落在 '/read/smoke_data/0'，不是期望的 '/read/smoke_data/1'。book-card 的 href 形状变了？` ／ `assert '/read/smoke_data/0' == '/read/smoke_data/1'` | 「从书库点进去落在第 0 章」这条 URL 判据 |
| D3 | R-1 末尾的 `not_to_contain_text(CH1_ANCHOR)` → `to_contain_text(CH1_ANCHOR)` | `AssertionError: Locator expected to contain text 'Beta prose.'` ／ `Actual value: OneAlpha prose.` ／ 调用日志 `14 × locator resolved to <body>…</body>` `- unexpected value "OneAlpha prose.` | 第 0 章渲染的**只是**第 0 章：反向那半句真在区分两章，不是恒真 |
| D4 | R-2 的 URL 期望 `CH1_PATH` → `CH0_PATH`（正则与逐字 `assert` 两处一起改） | `AssertionError: Page URL expected to be 're.compile('/read/smoke_data/0(?:[#?].*)?$')'` ／ `Actual value: http://127.0.0.1:54246/read/smoke_data/1` ／ 调用日志 `Expect "to_have_url" with timeout 5000ms` `14 × locator resolved to <html lang="en">…</html>`；TOC 那一支的 `Actual value` 末尾多一个 `#`。三个参数**全部**红（`3 failed`） | URL 与正文两项**不是互相掩护**：正文那两行全程没红，URL 这一项自己咬住了章号 |
| D4′ | 同 D4，但在**调整断言顺序之前**跑的第一枪 | `1 failed, 2 passed`——只有 `direct-url` 红 | **这一枪改了用例本身**：当时 URL 断言排在正文之前，而 `syncLocationToUrl` 写在 `epub-renderer.js` 的 `rendered` 回调里，站内换章时 `page.url` 在那一瞬**确实还是** `/read/smoke_data/0`，于是错的期望反而绿。据此把顺序改成「先正文、后 URL」，重跑即 D4 的三红。没有这一枪，两支站内导航的 URL 判据会长期停在一个可被时序吸收的位置 |
| D5 | R-2 的正文期望 `CH1_ANCHOR` → `CH0_ANCHOR`（`_reader_frame` 与 `not_to_contain_text` 两行互换） | `AssertionError: Locator expected to contain text 'Alpha prose.'` ／ `Actual value: TwoBeta prose.` ／ `Aria snapshot: - heading "Two" [level=1] - paragraph: Beta prose.` | 同 D4 的另一侧：URL 那两行全程绿，正文这一项自己咬住了渲染内容 |
| D6 | R-2 `direct-url` 那一支的 `expects_full_page_load` → `False` | `AssertionError: 导航后 window.__wi12_navigation_probe 是 None，期望站内导航把它留着（'wi12-set-before-navigation'）。这一支被判为站内导航，但它整页加载了——…` ／ `assert None == 'wi12-set-before-navigation'`（`1 failed, 2 passed`） | 「导航的性质」这第三项判据真在分辨整页 vs 站内 |
| D7 | R-2 `chapter-next` / `toc-row` 两支的 `expects_full_page_load` → `True` | `AssertionError: 导航后 window.__wi12_navigation_probe 还在（'wi12-set-before-navigation'），期望整页加载把它冲掉。这一支被判为整页加载，但它是站内导航` ／ `assert 'wi12-set-before-navigation' is None`（`2 failed, 1 passed`，两支各红一次） | 同 D6 的反向：哨兵不是恒真也不是恒假，三个参数确实是**两条站内、一条整页** |
| D8 | **R-3 的核心靶**：把「跨章条目不被渲染」的期望整体反过来——`R3_EXPECTED_MARK_TEXTS` → `["Alpha ", "prose"]`、`R3_EXPECTED_MARK_IDS` → 两个 id 都在、`R3_ID_OTHER not in scan["html"]` → `in` | `AssertionError: Locator expected to have text '['Alpha ', 'prose']'` ／ `Actual value: ['Alpha prose']` ／ 调用日志 `Expect "to_have_text" with timeout 5000ms` `14 × locator resolved to 1 element` | 这条断言**真的在测章节过滤**，不是恒真：今天第 0 章的 DOM 里**只有一个** `<mark>`、文本恰是 `'Alpha prose'`，把期望翻过来当场红 |
| D9 | R-3 第 (4) 项 API 佐证的期望 `[R3_ID_CURRENT]` → `[R3_ID_CURRENT, R3_ID_OTHER]` | `assert ['wi12-r3-current-chapter'] == ['wi12-r3-cur...ther-chapter']` ／ `Right contains one more item: 'wi12-r3-other-chapter'` | 服务端那一项是独立的一道：`GET /api/notes/smoke_data/0` 今天确实只交出本章那一条，(1)(2)(3) 与 (4) 能分辨「服务端丢了过滤」与「`loadAndRender` 渲错了」 |

**D1 详录**（它比其余各条多一步，值得单列）：先只改 `SMOKE_BOOK_TITLE`，红的是语料探针
`_assert_corpus_unchanged`——这正是探针存在的意义：它把失败点从「点不到那个链接，超时 30s」
提前到一句说得清的话。把探针一并放宽（`assert True or …`）之后再跑，才拿到真正的主判据
失败，即 30 秒定位超时。调用日志里那半行完整形态是
`waiting for locator(…lib-book-card…lib 复合选择器…).get_by_role("link", name="Read Nineteen Twenty Three")`；
其中定位器串在 pytest 输出里带转义引号，原样抄进本文件会被 `scripts/lint_e2e_selectors.py`
扫成一个畸形选择器而报违规，故此处只留可读的那一段，形状未改。

**为什么 D8 是本模块最该打的那一靶。** R-3 的三条 DOM 断言说的都是「今天渲染了什么」——
一个「渲染全部标注」的实现在**语料不配合**时也能让它们绿（旧形态就栽在这里）。只有把期望
翻过来跑一次，才能确认今天的绿不是「B 恰好匹配不上」而是「B 被过滤掉了」。翻过来之后以
`Actual value: ['Alpha prose']` 红，说明第 0 章的 DOM 里确实只有本章那一条。
（注：`['Alpha ', 'prose']` 这个两段形状是**矩阵推演的**「过滤失效后 `buildSegments`
把重叠区切开」的形状，本模块没有、也不应该为了看它一眼去改生产代码。）

**为什么 D4 / D5 必须分开打两枪。** 它们证明的不是同一件事：一起改会同时红，看不出来是
哪一项在承重。分开之后可以确认「URL 变了但内容没换」与「内容对了但地址错了」两种失败各自
都有人接得住——这正是矩阵要求「每次都断两项」的全部内容。而 D4′ 说明这两项**还有顺序要求**。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from epub_corpus import EPUB2_TITLE  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH1_ANCHOR,
    open_reader,
    read_notes,
    seed_notes,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# 坐标：全部写成字面量（§0 第五条纪律）
# ---------------------------------------------------------------------------
#
# 期望值不从被测源头（`epub_corpus` 的语料常量、`conftest` 的 BOOK_ID）切出来：从同一个
# 源头切出期望值，语料一改断言跟着改，永远绿。下面 `_assert_corpus_unchanged` 是**另一
# 回事**——它不参与判据，只在语料被改动时把失败点从「点不到链接，超时 30s」提前到一句说得
# 清的话。参照 `test_write_cjk_boundary.py` 里 `CJK_CH0_QUOTE` 那一段的做法。

#: 书库 fixture 的第一本书的目录名。R-1 的复合选择器与三条 URL 期望都咬着它。
SMOKE_BOOK_ID = "smoke_data"

#: `build_epub2` 的书名。R-1 靠 `Read {书名}` 这个 ARIA 名点进书卡里的链接
#: ——书卡本身用 `[data-testid="lib-book-card"][data-book-id="…"]` 定位
#: （`data-book-id` 在 ADR-0014 的闭合清单内），卡内那个 `<a>` 只有 `aria-label`。
SMOKE_BOOK_TITLE = "Nineteen Twenty Two"

#: 两章的 URL path，逐字。**不写成 f-string 拼 BOOK_ID**：K6 要断的正是这个形状本身。
CH0_PATH = "/read/smoke_data/0"
CH1_PATH = "/read/smoke_data/1"

#: 第 1 章那一行 TOC 的 `data-file-href`（`reader3.py` 把 NCX 的 href 去掉锚点后原样存下）。
#: `data-file-href` 在 lint 的闭合清单内，见 `scripts/lint_e2e_selectors.py`。
CH1_FILE_HREF = "text/two.xhtml"


# ---------------------------------------------------------------------------
# R-2 的第三项判据：这次导航是站内的，还是整页加载
# ---------------------------------------------------------------------------
#
# 挂在 `window` 上的哨兵。整页加载会换掉整个 JS 全局环境，哨兵随之消失；站内导航
# （`displaySectionIndex` + `history.replaceState`）不会。见模块 docstring 里
# 「R-2 的每个机制都断 URL 与正文两项，还外加一项」那一段。
NAV_PROBE = "__wi12_navigation_probe"
NAV_PROBE_VALUE = "wi12-set-before-navigation"


# ---------------------------------------------------------------------------
# R-3 的 seed
# ---------------------------------------------------------------------------
#
# id 与 created_at 写死（§0 第五条纪律）：让 `seed_notes` 生成随机 uuid 的话，
# 「B 有没有被渲染」这条判据只能拿两串谁也不认识的 uuid 互相比，失败消息里看不出人话。

R3_ID_CURRENT = "wi12-r3-current-chapter"
R3_ID_OTHER = "wi12-r3-other-chapter"
R3_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: A：本章那一条。`prefix`/`suffix` 全空 ⇒ `findRange` 只剩 `indexOf(quote)` 一条路。
R3_CURRENT_QUOTE = "Alpha prose"

#: B：**故意不在当前章**的那一条，且它的 quote 在当前章文本里**可匹配**。
#: 第 0 章的连续文本轴是 `"OneAlpha prose."`，`indexOf("prose")` 命中 `[9, 14)`。
#: 过滤一旦失效，第 0 章一定多出一个 `<mark>`——见模块 docstring 与矩阵 Gap 2。
R3_OTHER_QUOTE = "prose"

#: 期望：第 0 章渲染出的 `<mark>` 文本序列。**独立写一遍字面量，不写 `[R3_CURRENT_QUOTE]`。**
#: 这条判据的输入与期望是同一段文字（往返形状），从输入派生期望等于拿自己比自己——
#: 两侧同步变，用例照样绿。分开写之后，D8 那一枪才打得下去。
R3_EXPECTED_MARK_TEXTS = ["Alpha prose"]

#: 期望：DOM 里出现过的 annotation id 的并集。B 的 id 不在其中，这是最直接的那条判据
#: ——不依赖文本形状，只问「B 有没有被渲染」。
R3_EXPECTED_MARK_IDS = {R3_ID_CURRENT}


def _assert_corpus_unchanged() -> None:
    """语料与 fixture 常量没被改过。**这不是判据，是诊断**。

    本模块把语料的书名、两章正文里的 token 抄成了字面量。抄本与原本分家时，真正的失败点
    在别处（R-1 是「点不到 `Read …` 那个链接」的 30s 超时，R-3 是「一个 `<mark>` 都没有」），
    正确但要读三层才明白。先在这里说清楚。

    反过来，**不能**用这些常量直接派生期望值：那样语料一改期望值跟着改，「书卡指到别的书」
    「B 的 quote 在本章不再可匹配」这类缺陷就再也不会红（§0 第五条纪律）。
    """
    assert BOOK_ID == SMOKE_BOOK_ID, (
        f"fixture 书库的第一本改名了：{BOOK_ID!r} != {SMOKE_BOOK_ID!r}。"
        f"本模块三条 URL 期望（{CH0_PATH} / {CH1_PATH}）都是照着它写死的，要一起改。"
    )
    assert EPUB2_TITLE == SMOKE_BOOK_TITLE, (
        f"语料书名变了：{EPUB2_TITLE!r} != {SMOKE_BOOK_TITLE!r}。"
        f"R-1 靠 `Read {{书名}}` 这个 ARIA 名点进书卡，改语料要一起改这里。"
    )
    assert R3_OTHER_QUOTE in CH0_ANCHOR and R3_OTHER_QUOTE in CH1_ANCHOR, (
        f"token {R3_OTHER_QUOTE!r} 不再是两章共有的了"
        f"（第 0 章 {CH0_ANCHOR!r}，第 1 章 {CH1_ANCHOR!r}）。"
        "R-3 的全部力量来自「跨章那一条在本章也匹配得上」——共有性一没，"
        "「渲染了所有标注」的错误实现就又能让这条用例绿了（矩阵 Gap 2）。"
    )


# ---------------------------------------------------------------------------
# 读 DOM
# ---------------------------------------------------------------------------

# 为什么用 `dataset.annotationIds` 而不是 `getAttribute("data-annotation-ids")`：
# 后者会被 `scripts/lint_e2e_selectors.py` 的 `LOCATOR_CALL_RE` 当成一处选择器扫到
# （它匹配 `.getAttribute(` 后面那个字符串实参），报「含非 data-* 属性选择器的部分」。
# 那是一次误报，但让它误报再逐行放行，等于把这条 lint 的信噪比往下拉。
# 同样的取舍写在 `test_write_overlap_and_disambiguation.py` 的 `_SCAN_MARKS_JS` 旁边。
_SCAN_ANNOTATIONS_JS = r"""
() => {
  const body = document.body;
  const marks = Array.from(body.querySelectorAll('[data-testid="rd-anno-span"]'));
  return {
    texts: marks.map((m) => m.textContent),
    // 每个 `<mark>` 的 id 列表原样带回；解析不出来就把生串交给 Python 侧报，别在这里吞。
    ids: marks.map((m) => m.dataset.annotationIds || null),
    // 「B 的 id 不出现在 DOM 的任何位置」这条判据要的是整份 HTML，不只是 `<mark>` 上那些
    // 属性——一个把 id 写进别的属性、或写进注释里的实现，同样算「渲染了 B」。
    html: body.innerHTML,
  };
}
"""


def _scan_annotations(frame: Any) -> Dict[str, Any]:
    """iframe 内全部 `rd-anno-span` 的文本、id 列表，外加 body 的整份 HTML。"""
    return frame.locator("body").evaluate(_SCAN_ANNOTATIONS_JS)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板


def _mark_id_union(scan: Dict[str, Any]) -> set:
    """所有 `<mark>` 的 `data-annotation-ids` 并集。解析失败当场抛，不吞。"""
    union: set = set()
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
        union |= set(parsed)
    return union


def _reader_frame(page: "Page", expect_text: str) -> Any:
    """已经在阅读器页面上时，等到 iframe 里真的有正文，产出 `FrameLocator`。

    与 `helpers.open_reader` 的区别只有一处：**它不 `goto`**。R-1 是从书库点进来的、
    R-2 有两支是站内换章，两者都已经在页面上了，再 `goto` 一次就把被测的那次导航
    冲掉了——用例会绿，但它证明的是 `goto` 能用，不是那个按钮能用。

    （**该不该上收到 `helpers.py`**：见本模块提交时的报告。Wave 3 没有任何 WI 被授权改
    共享文件，所以它先住在这里。）
    """
    expect(page.get_by_test_id("rd-shell")).to_be_visible()
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    expect(frame.locator("body")).to_contain_text(expect_text)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    return frame


# ---------------------------------------------------------------------------
# R-1
# ---------------------------------------------------------------------------


def test_r1_library_card_opens_reader_showing_this_books_prose(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """R-1（S1，L3 真服务端到端）：书库 → 点书卡 → 阅读器渲染出**这本书第 0 章的正文**。

    比 `test_harness_smoke.py` 那条多一步：smoke 直接 `goto` 阅读器地址，本条从 `/` 出发
    点进去，因此额外覆盖了「书卡的跳转 URL 形状」这一段——`library.html` 的
    `href="/read/{{ book.id }}/0"` 与 K6 的 URL 形状是同一件事的两侧。

    三项判据，缺一个都有具体的坏实现能全绿：

      1. **URL 的 path 逐字等于** `/read/smoke_data/0`。书卡指到别的书或别的下标时红。
         `endswith("/0")` 这类弱形式不行——`/read/second_data/0` 也以 `/0` 结尾。
      2. **iframe 正文含 `Alpha prose.`**。`assert iframe is not None` 在一本空白书上照样
         绿（矩阵「自检」原文），断正文文本不会。
      3. **iframe 正文不含 `Beta prose.`**。少了它，一个「把整本书一次渲染完」的实现会让
         (2) 绿——而那正是 spine 顺序或分章渲染坏掉时最可能的形状。

    自检：把 `library.html` 的 `href` 改成 `/read/{{ book.id }}/1` ⇒ (1)(3) 红；
    把 `process_epub` 产出的 spine 倒序 ⇒ (2)(3) 红。没有「返回预期值」的捷径能让它绿
    ——判据落在**另一个进程渲染出来的 DOM** 与浏览器自己的地址栏上。
    """
    _assert_corpus_unchanged()

    page.goto(f"{live_server}/")
    card = page.locator(f'[data-testid="lib-book-card"][data-book-id="{SMOKE_BOOK_ID}"]')
    expect(card).to_be_visible()

    # 卡内那个 `<a>` 没有自己的 testid，只有 `aria-label="Read {{ book.title }}"`。
    # ARIA role/name 是选择器政策里与 testid 并列的那一半（任务书 §1），不是退让。
    card.get_by_role("link", name=f"Read {SMOKE_BOOK_TITLE}").click()

    frame = _reader_frame(page, CH0_ANCHOR)

    actual_path = urlparse(page.url).path
    assert actual_path == CH0_PATH, (
        f"从书库点进来落在 {actual_path!r}，不是期望的 {CH0_PATH!r}。"
        "book-card 的 href 形状变了？"
    )
    expect(frame.locator("body")).not_to_contain_text(CH1_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板


# ---------------------------------------------------------------------------
# R-2
# ---------------------------------------------------------------------------


def _nav_via_chapter_next(page: "Page", base_url: str) -> None:
    """机制 1：`rd-chapter-next`。

    模板里它是 `<a href="/read/{id}/{next}">`，但 `epub-renderer.js` 给 `#next-chapter-link`
    绑了 `click` + `preventDefault()` → `displaySectionIndex`，**今天是站内导航**
    （矩阵文末 §B 的实测，覆盖了生成计划里「整页导航」那句）。`href` 是兜底：事件链坏掉时
    浏览器会整页加载到同一个地址，URL 与正文两项都不会红——这条假绿由本用例的第三项判据
    （`NAV_PROBE`）接住。
    """
    page.get_by_test_id("rd-chapter-next").click()


def _nav_via_toc_row(page: "Page", base_url: str) -> None:
    """机制 2：TOC 行 → `findAndGo()` → `displaySectionIndex`，站内。

    先点 `rd-rail-toc` 打开面板：`#toc-mode` 初始 `aria-hidden="true"` 且靠
    `translateX(-100%)` 停在屏外，不打开就点不到里面的行。
    TOC 行用 `[data-testid="rd-toc-row"][data-file-href="…"]` 定位——`rd-toc-row` 是
    Jinja 宏渲出的 N 个同名节点，判别位 `data-file-href` 在 ADR-0014 的闭合清单内。
    """
    page.get_by_test_id("rd-rail-toc").click()
    page.locator(
        f'[data-testid="rd-toc-row"][data-file-href="{CH1_FILE_HREF}"]'
    ).click()


def _nav_via_direct_url(page: "Page", base_url: str) -> None:
    """机制 3：直接 URL 进入。三种里**唯一真正的整页加载**。

    它测的是服务端那一侧：`/read/{book}/{chapter}` 这条路由自己就得把第 1 章交出来，
    不能只在站内换章时才对。K6 的 URL 形状是双向的——地址栏能写进去，也能被写出来。
    """
    page.goto(f"{base_url}{CH1_PATH}")


@pytest.mark.parametrize(
    "navigate,expects_full_page_load",
    [
        pytest.param(_nav_via_chapter_next, False, id="chapter-next"),
        pytest.param(_nav_via_toc_row, False, id="toc-row"),
        pytest.param(_nav_via_direct_url, True, id="direct-url"),
    ],
)
def test_r2_three_navigation_mechanisms_reach_chapter_one(
    page: Page,
    live_server: str,
    e2e_books_dir: Path,
    navigate: Callable[["Page", str], None],
    expects_full_page_load: bool,
) -> None:
    """R-2（S4，「今天真实存在的导航机制」这个有界域上的性质）：三种机制各断一次。

    **域是有界的，且这三个就是全部**（矩阵 §WI-12 的机制表，实测后的版本）：

      1. `rd-chapter-next` —— 站内（`<a href>` 被 `preventDefault` 拦下）；
      2. TOC 行 —— 站内（`findAndGo` → `displaySectionIndex`）；
      3. 直接 URL —— 整页加载。

    **`rd-page-prev` / `rd-page-next` 不在域里，且任何机制清单里都不许出现**：
    `.nav-zone-left/right` 的 CSS 是 `display: none`（注释写明 keyboard-only），
    且只有 legacy `js/pagination.js` 绑定它们，而 `reader.html` 不加载那个文件。
    Playwright 点 `display:none` 元素会在 actionability 上超时——那是一条永远红、
    且红得毫无信息量的用例。

    三项判据（前两项是任务书对本条的验收要求，第三项是本模块加的）：

      * **URL 的 path 逐字等于** `/read/smoke_data/1`。只断正文会放过 K6 点名的
        「静默存错章」——内容换了但地址没跟上，深链、刷新、标注落库的 `chapter_index`
        全都跟着错。
      * **iframe 正文含 `Beta prose.` 且不含 `Alpha prose.`**。只断 URL 会放过
        「地址变了但内容没换」——`history.replaceState` 与 `rendition.display` 是两件事，
        `epub-renderer.js` 把它们写在同一个 `rendered` 回调里，但那是实现细节不是保证。
      * **导航的性质**：站内那两支要求哨兵活下来，整页那一支要求它被冲掉。没有这一项，
        三个参数就退化成「三条通往同一个 URL 的路」，而机制 1 的 `href` 兜底会让事件链
        整个死掉都测不出来（矩阵裁决 4 不让 R-4 用它，正是这个理由）。

    **断言顺序是判据的一部分：先正文，后 URL。** `syncLocationToUrl` 写在
    `epub-renderer.js` 的 `rendered` 回调里，站内换章时它比 `click()` 返回晚；
    先断 URL 的话，`page.url` 在那一瞬还停在 `/read/smoke_data/0`。定向破坏 D4 实测到了
    这件事：把期望 URL 改成隔壁章号后，只有整页那一支红，两支站内的反而「通过」了，
    因为它们当时读到的确实还是旧地址。先用正文把渲染等出来，URL 才是稳定态。

    URL 那一项写成正则 ＋ 逐字两步：`expect(page).to_have_url` 自动重试兜住残余抖动，
    随后那句 `assert` 才给出一个人能一眼认出的字面量。正则里的 `(?:[#?].*)?` 不是放宽：
    TOC 行是 `<a href="#">`，点击会给地址栏留一个空 hash，而 `syncLocationToUrl` 只改
    `pathname`，hash 原样留着——path 那一项仍然是逐字等号。
    """
    _assert_corpus_unchanged()

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    expect(frame.locator("body")).not_to_contain_text(CH1_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    page.evaluate(f"window.{NAV_PROBE} = {json.dumps(NAV_PROBE_VALUE)}")
    navigate(page, live_server)

    frame = _reader_frame(page, CH1_ANCHOR)
    expect(frame.locator("body")).not_to_contain_text(CH0_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    expect(page).to_have_url(re.compile(re.escape(CH1_PATH) + r"(?:[#?].*)?$"))
    actual_path = urlparse(page.url).path
    assert actual_path == CH1_PATH, (
        f"导航后 URL 的 path 是 {actual_path!r}，不是期望的 {CH1_PATH!r}"
    )

    survived = page.evaluate(f"window.{NAV_PROBE} ?? null")
    if expects_full_page_load:
        assert survived is None, (
            f"导航后 window.{NAV_PROBE} 还在（{survived!r}），期望整页加载把它冲掉。"
            "这一支被判为整页加载，但它是站内导航"
        )
    else:
        assert survived == NAV_PROBE_VALUE, (
            f"导航后 window.{NAV_PROBE} 是 {survived!r}，"
            f"期望站内导航把它留着（{NAV_PROBE_VALUE!r}）。"
            "这一支被判为站内导航，但它整页加载了"
            "——`epub-renderer.js` 里那个 `preventDefault()` 没跑到，"
            "浏览器按 `<a href>` 兜底整页加载到了同一个地址，URL 与正文两项因此都不会红"
        )


# ---------------------------------------------------------------------------
# R-3
# ---------------------------------------------------------------------------


def test_r3_only_current_chapter_annotations_are_rendered(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """R-3（S3，命名的失败模式：**章节过滤失效**）：`<mark>` 落在预期的那段文字上。

    seed 两条，两条都 `cfi=None`（理由见模块 docstring 「为什么都写 cfi=None」）：

      * **A** `chapter_index=0`, `quote="Alpha prose"` —— 本章那一条；
      * **B** `chapter_index=1`, `quote="prose"` —— **故意不在当前章**，而它的 quote
        在当前章文本里**匹配得上**（第 0 章连续文本轴 `"OneAlpha prose."`，`indexOf`
        命中 `[9, 14)`）。

    B 的构造是这条用例的全部力量。`quote="Beta prose"` 那种写法（旧形态）在过滤完全失效
    时也只会得到一个 `<mark>`，因为 `findRange` 在第 0 章找不到它——用例对着一个坏实现
    是绿的。`prefix`/`suffix` 全空则让 `findRange` 只剩 `indexOf(quote)` 一条路（非空时
    它会先试 `prefix+quote+suffix` 的组合串，找不到再回退，结论相同但推理链更长、更容易
    被人误删）。**过滤一旦失效，第 0 章一定多出一个 `<mark>`，没有巧合可以掩盖。**

    四条判据：

      1. `<mark>` 的**文本序列** == `["Alpha prose"]`。§2 原文「比对 `textContent`，
         不是数量」——「有 1 个 `<mark>`」在高亮画错位置时照样绿。
      2. `<mark>` 的**数量** == 1。与 (1) 一起断：集合等值对「同一段文字渲染了两遍」
         是盲的。（`to_have_text` 收列表时同时管住顺序与条数，下面那句 `assert` 是把
         数量单独写出来，好让失败消息直接说人话。）
      3. 所有 `data-annotation-ids` 的并集 == `{A 的 id}`，且 **B 的 id 不出现在 body
         的整份 HTML 里**。这是最直接的那条：不依赖文本形状，只问「B 有没有被渲染」。
      4. API 层佐证：`GET /api/notes/smoke_data/0` 只有一条且是 A。它把「过滤在服务端」
         与「过滤在客户端」分开——(1)(2)(3) 红而 (4) 绿，说明服务端交对了、
         `loadAndRender` 渲错了；两边一起红，说明服务端的 `chapter_index` 过滤失效。

    过滤失效时的具体形状（矩阵「自检」原文）：B 进入渲染 ⇒ `findRange("prose")` 命中
    `[9, 14)` ⇒ 与 A 的 `[3, 14)` 重叠 ⇒ `buildSegments` 切成 `[3,9)` 与 `[9,14)` 两段 ⇒
    文本序列变成 `["Alpha ", "prose"]`、id 并集变成两个 ⇒ (1)(2)(3) 全红。
    这个两段形状是矩阵推演出来的；D8 那一枪实测到的是它的反面——今天第 0 章只有一个
    `<mark>`、文本是 `'Alpha prose'`，所以本条判据有咬合而不是恒真（见模块 docstring 的破坏表）。
    """
    _assert_corpus_unchanged()
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": R3_ID_CURRENT,
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": R3_CURRENT_QUOTE,
                "prefix": "",
                "suffix": "",
                "cfi": None,
                "created_at": R3_CREATED_AT,
            },
            {
                "id": R3_ID_OTHER,
                "chapter_index": 1,
                "type": "marker",
                "color": "yellow",
                "quote": R3_OTHER_QUOTE,
                "prefix": "",
                "suffix": "",
                "cfi": None,
                "created_at": R3_CREATED_AT,
            },
        ],
    )
    seeded_ids = {a["id"] for a in read_notes(e2e_books_dir, BOOK_ID)}
    assert seeded_ids == {R3_ID_CURRENT, R3_ID_OTHER}, (
        f"seed 没有原样落盘：{seeded_ids}。两条都要在，否则「跨章那一条不被渲染」"
        "就退化成「它压根不存在」——那是一句恒真"
    )

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    spans = frame.get_by_test_id("rd-anno-span")
    # `to_have_text` 收列表时会自动等待——刷新后的高亮要等 `loadAndRender()` 跑完才挂上。
    # 它同时管住条数与顺序，是 (1)(2) 两条判据的自动重试形态。
    expect(spans).to_have_text(R3_EXPECTED_MARK_TEXTS)

    scan = _scan_annotations(frame)
    assert scan["texts"] == R3_EXPECTED_MARK_TEXTS, (
        f"第 0 章渲染出的 `<mark>` 文本序列是 {scan['texts']!r}，"
        f"不是期望的 {R3_EXPECTED_MARK_TEXTS!r}。"
        f"若它是 ['Alpha ', 'prose']，那就是章节过滤失效：跨章那条 "
        f"（quote={R3_OTHER_QUOTE!r}）被送进了 `findRange`，与本章那条重叠后被切成两段"
    )
    assert len(scan["texts"]) == len(R3_EXPECTED_MARK_TEXTS), (
        f"第 0 章有 {len(scan['texts'])} 个 `rd-anno-span`，"
        f"不是期望的 {len(R3_EXPECTED_MARK_TEXTS)} 个：{scan['texts']!r}"
    )

    id_union = _mark_id_union(scan)
    assert id_union == R3_EXPECTED_MARK_IDS, (
        f"DOM 里出现的 annotation id 并集是 {id_union}，不是期望的 {R3_EXPECTED_MARK_IDS}"
    )
    assert R3_ID_OTHER not in scan["html"], (
        f"跨章那一条的 id（{R3_ID_OTHER!r}）出现在第 0 章的 body HTML 里 —— 它被渲染了。"
        "`loadAndRender` 取的是全书标注，还是服务端的 chapter_index 过滤失效了？"
    )

    resp = page.request.get(f"{live_server}/api/notes/{BOOK_ID}/0")
    assert resp.ok, f"GET /api/notes/{BOOK_ID}/0 不是 2xx：{resp.status}"
    served: List[Dict[str, Any]] = resp.json()["annotations"]
    assert [a["id"] for a in served] == [R3_ID_CURRENT], (
        f"服务端为第 0 章交出的是 {[a['id'] for a in served]}，"
        f"不是期望的 {[R3_ID_CURRENT]}。这一项与上面三项一起看：都红说明过滤在服务端就丢了，"
        "只有上面红说明服务端交对了而 `loadAndRender` 渲错了"
    )
