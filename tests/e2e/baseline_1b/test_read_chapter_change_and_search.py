"""WI-13 —— R-4 站内翻章后重绘 / R-5 阅读页内搜索命中高亮。

任务书 §2 的 R 系列两条，组 `baseline_1b`，共 3 个用例（R-5 参数化 ×2：拉丁语 / CJK）。
两条各自守一个契约点：

  * **R-4 → K4**「换章要重绘标注」。它是一条**状态转移不变式**：换章是全量替换，换章后
    DOM 里的标注集合恒等于新章的标注集合。旧章残留与全部消失是同一条律的两个失败方向。
  * **R-5 → K5**「`getContentRoot()` / `onContentsReady()`」。`search.js` 是 K5 的**第二个
    消费方**（第一个是 `annotations.js`）。标注那一侧有整套 W 系列兜着，搜索这一侧
    **只有本条**。

两条共同的写法纪律（§0）——

**几何/结构断言写成等号，不写「非空」。** `<mark>` 个数、命中条数、id 集合全部断等号：
「> 0」对「把整本书每段都当成命中」也是绿的。

**期望值全是字面量，且与输入分开写两遍**（§0 第五条）。`R4_EXPECTED_MARK_TEXT` 不写成
`R4_QUOTE`、`R5_EXPECTED_MARK_CJK` 不写成 `R5_TERM_CJK`：输入与期望同源时两侧会一起变，
用例照样绿。`created_at` 与 annotation id 也写死，不用随机 uuid——本模块的判别位就是 id，
两串谁也不认识的 uuid 互比时失败消息里读不出发生了什么。

**先断正文，后断 URL**（§0.6 跨波欠账 #12）。`syncLocationToUrl()` 跑在 epub.js 的
`rendered` 回调里，点击返回的那一刻地址栏还是旧值。**任何情况下不读同步的 `page.url`。**

**URL 一律用 `helpers.pathname_is`，不用 `page.wait_for_url`**（欠账 #13）。站内导航的入口
是 `<a href="#">`，导航后 URL 尾巴上挂着一个 `#`，glob 匹配整串、永不命中、白烧 30 秒。

**`rd-page-prev` / `rd-page-next` 一次都没出现**（欠账 #11、矩阵更正 §B）：那两块导航区
CSS 是 `display: none`，全仓 live 的 JS 无任何绑定——唯一绑定在 `reader.html` **不加载**的
legacy `js/pagination.js` 里，点它只会等到 actionability 超时。

**选择器**：默认只用 `data-testid` 与 ARIA。三处例外，每一处都在行内写了
`# lint-e2e-selectors: allow` 与理由：`rd-viewport` 的 `frame_locator`（lint 明文豁免）、
iframe 内用户那本书自己的 `body`、以及 `search.js` 运行时插进那本书 XHTML 的
`mark.search-match`。**没有用 `frame.evaluate` 去绕开 lint**——`scripts/lint_e2e_selectors.py`
的 docstring 把那种做法称为「看不见的绕过，比显式放行糟得多」。TOC 行用的复合选择器
`[data-testid="rd-toc-row"][data-file-href="…"]` 走 ADR-0014 的闭合判别位清单。

**载入期竞态**：一次章节加载会跑两遍 `loadAndRender()`，中间有一个 `<mark>` 被拆光的窗口。
所有一次性快照（`scan_marks`）都必须在 `helpers.settle_marks()` 之后取，理由见它的 docstring
（本模块原先的 `_settled` 已于 Wave 5 上收，欠账 #25）。

破坏证据见两个用例各自的 docstring；其中一枪**没打响**，那条负面结果连同它暴露的护栏缺口
一起记在 R-4 的破坏表末尾。

引用规则：用符号名与 testid 定位，不写代码行号。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID, BOOK_ID_CJK  # type: ignore[import-not-found]
from epub_corpus import CJK_SEARCH_TERM  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH1_ANCHOR,
    assert_corpus_unchanged,
    mark_id_union,
    open_reader,
    pathname_is,
    reader_frame,
    scan_marks,
    seed_notes,
    settle_marks,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# R-4 的坐标：全部字面量（§0 第五条纪律）
# ---------------------------------------------------------------------------
#
# id 与 created_at 写死，不让 seed 侧生成随机 uuid：本条用例的**唯一判别位就是 id**
# （两条 seed 的 quote 故意相同），拿两串谁也不认识的 uuid 互相比时，失败消息里看不出是
# 「旧章那条残留了」还是「新章那条没渲出来」。

R4_ID_CH0 = "wi13-r4-chapter-zero"
R4_ID_CH1 = "wi13-r4-chapter-one"
R4_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: 两条 seed **共用**的 quote。`epub_corpus.build_epub2` 的两章正文分别是 `Alpha prose.`
#: 与 `Beta prose.`，token `prose` 两章都在——这正是矩阵 R1 重构要的构造，见 R-4 docstring。
R4_QUOTE = "prose"

#: 期望：`<mark>` 覆盖的文本。**独立写一遍字面量，不写 `[R4_QUOTE]`。** 输入与期望同源时
#: 两侧会一起变，用例照样绿。
R4_EXPECTED_MARK_TEXT = "prose"

#: 期望：翻章前 / 翻章后 DOM 里出现过的 annotation id 的并集。同样独立写字面量。
R4_EXPECTED_IDS_CH0 = {"wi13-r4-chapter-zero"}
R4_EXPECTED_IDS_CH1 = {"wi13-r4-chapter-one"}

#: 期望：任一时刻 iframe 内应当渲出的 `<mark>` 个数。断等号而不是断非空。
R4_EXPECTED_MARK_COUNT = 1

#: 翻到的那一章的 URL path，逐字。不写成 f-string 拼 `BOOK_ID`——K6 要断的正是这个形状。
R4_CH1_PATH = "/read/smoke_data/1"

#: 第 1 章那一行 TOC 的 `data-file-href`。该属性在 ADR-0014 的闭合清单内，见
#: `scripts/lint_e2e_selectors.py` 的 `ALLOWED_DISCRIMINATORS`。
R4_CH1_FILE_HREF = "text/two.xhtml"

#: 挂在 `window` 上的哨兵，判定「这次翻章是站内的还是整页加载」。整页加载会换掉整个 JS
#: 全局环境，哨兵随之消失。构造同 R-2（`test_read_paths.py` 的 `NAV_PROBE`）。
R4_NAV_PROBE = "__wi13_navigation_probe"
R4_NAV_PROBE_VALUE = "wi13-set-before-toc-click"


# ---------------------------------------------------------------------------
# R-5 的坐标
# ---------------------------------------------------------------------------
#
# 两个参数各自的检索词与期望高亮文本**分开写两遍**，理由同 R4_EXPECTED_MARK_TEXT。

R5_TERM_EN = "Alpha"
R5_EXPECTED_MARK_EN = "Alpha"

#: CJK 检索词。它是 `咖啡館` 的**子串**——这正是无空格语言与拉丁语在检索上分岔的地方，
#: 也是本条参数化 ×2 的全部理由。语料侧的定义在 `epub_corpus.CJK_SEARCH_TERM`，由
#: `CORPUS_CHECKS` 钉住，见其注释。
R5_TERM_CJK = "咖啡"
R5_EXPECTED_MARK_CJK = "咖啡"

#: 两本书的落点章 / 起点章正文探针。起点章**故意不含检索词**。
R5_CJK_CH0_ANCHOR = "他在咖啡館裡等了很久。"
R5_CJK_CH1_ANCHOR = "彼女は喫茶店で本を読んでいた。"

R5_EN_TARGET_PATH = "/read/smoke_data/0"
R5_CJK_TARGET_PATH = "/read/cjk_data/0"

#: 两本语料里检索词都只出现一次，而 `search.js` 的 `renderResults` 是**逐次出现**出结果的
#: （每条带自己的 `occurrence`），所以是 1 而不是「> 0」。断等号：「> 0」对「把整本书每段都
#: 当成命中」也是绿的。iframe 内的高亮个数同理。
R5_EXPECTED_HITS = 1
R5_EXPECTED_MARK_COUNT = 1

#: `.press()` 的键名。写成常量不是为了绕 lint —— 见调用点那一行的显式放行注释。
ENTER = "Enter"


#: 语料探针（喂给 `helpers.assert_corpus_unchanged`）：**不参与判据**，只把失败点提前。
#:
#: R-5 的 CJK 参数只有在检索词确实是 `咖啡館` 的子串时，才在测「无空格语言」这件事。
#: 语料常量一旦被改，主判据的表现是「搜不到命中，命中计数断言超时」——一句说不清原因的
#: 话。这里先响一次，把人指到 `epub_corpus.CJK_SEARCH_TERM` 上。
CORPUS_CHECKS = (
    (
        CJK_SEARCH_TERM,
        R5_TERM_CJK,
        f"CJK 语料的检索词变了：`epub_corpus.CJK_SEARCH_TERM` 现在是 {CJK_SEARCH_TERM!r}，"
        f"本模块按 {R5_TERM_CJK!r} 写死了期望。改语料要一起改这里",
    ),
)


def _seed_two_chapters(books_dir: Path) -> None:
    """两条 seed，**quote 相同、章号不同、id 不同**，两条都 `cfi=None`。

    `cfi=None` 是故障注入不是图省事：`AnnotationRenderer.render()` 的第一步是按 `cfi` 分流，
    带 CFI 的那批直接走 range 插入，`buildTextIndex → findRange → buildSegments` 一次都不会
    被调用（矩阵 §E）。更要命的是 **CFI 跨章无效**——一条 ch1 的 CFI 在 ch0 的文档里解析
    失败后恰好什么都不渲染，于是「章节过滤失效」这个失败模式会被这个巧合整个掩盖。
    """
    seed_notes(
        books_dir,
        BOOK_ID,
        [
            {
                "id": R4_ID_CH0,
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": R4_QUOTE,
                "prefix": "",
                "suffix": "",
                "cfi": None,
                "created_at": R4_CREATED_AT,
            },
            {
                "id": R4_ID_CH1,
                "chapter_index": 1,
                "type": "marker",
                "color": "yellow",
                "quote": R4_QUOTE,
                "prefix": "",
                "suffix": "",
                "cfi": None,
                "created_at": R4_CREATED_AT,
            },
        ],
    )


# ---------------------------------------------------------------------------
# R-4
# ---------------------------------------------------------------------------


def test_r4_chapter_change_repaints_with_only_the_new_chapters_annotations(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """R-4（状态转移不变式）：站内翻章后新章高亮正确，且旧章一条都不残留。

    **律**：换章是一次**全量替换**——换章后 DOM 里的标注集合恒等于新章的标注集合。两个
    方向缺一不可：K4 点名的失败模式既可能表现为「旧章残留」，也可能表现为「全部消失」，
    只断一个方向会放过另一个。

    **判别位是 id，不是文本（矩阵 §WI-13 的 R1 重构）。** 两条 seed 的 quote 故意都写
    `prose`：语料两章正文分别是 `Alpha prose.` 与 `Beta prose.`，token `prose` 两章都在，
    所以**渲染出来的文本在两章完全相同**，`data-annotation-ids` 成为唯一能分辨 A 与 B 的
    东西。用文本作判别位（旧形态 A=`Alpha prose` / B=`Beta prose`）时「旧章残留」那一半
    几乎不可能被触发——旧章的 `<mark>` 是**旧文档**的一部分，随文档一起消失，无论重绘逻辑
    对不对。换成同 quote 异 id 之后：

      * 重绘正确 ⇒ ids == `{idB}`；
      * 换章时取了全书标注 ⇒ 两条覆盖的文本完全重合，`buildSegments` 会合并成**一个**挂
        两个 id 的 span ⇒ ids ⊇ `{idA, idB}` ⇒ 红（注意 `<mark>` **计数**那一项在这里是
        **盲**的，仍旧是 1 个——这正是为什么文本项与 ids 项都要断）；
      * 换章后压根没重绘 ⇒ 一个 `<mark>` 都没有 ⇒ 红。

    **必须站内翻章，且不用 `rd-chapter-next`（矩阵裁决 4）。** 那两个按钮今天确实被
    `epub-renderer.js` 拦成了站内导航，但它们是 `<a href>`：事件链一旦坏掉、
    `preventDefault` 没跑，浏览器会按 `href` **整页加载**，新章高亮照样出现，
    **本条会绿而 `reader3:chapter:change` 一次都没被派发**。TOC 行是 `<a href="#">`，
    没有这条兜底。

    ⚠️ 但 TOC 行也不是完全没有退路：`findAndGo()` 在 `Reader3Epub.displaySectionIndex`
    缺席时会退回 `window.location.href`。所以本条**照 R-2 的成例加了哨兵那一项**——翻章前
    在 `window` 上放一个值，翻章后读回来。站内导航留得住它，整页加载会把它冲掉。没有这一
    项，那条 JS 兜底会让「事件链死了」以另一种形状假绿。

    **`rd-page-prev` / `rd-page-next` 不许出现**（任务书 §0.6 欠账 #11、矩阵更正 §B）：
    那两块导航区的 CSS 是 `display: none`，全仓 live 的 JS 无任何绑定——唯一的绑定在
    `reader.html` **不加载**的 legacy `js/pagination.js` 里。点它只会等到 actionability
    超时。

    **断言顺序：先正文，后 URL**（欠账 #12）。`syncLocationToUrl()` 跑在 epub.js 的
    `rendered` 回调里，点完 TOC 行的那一刻地址栏还是旧章号。URL 那一项用 `pathname_is`，
    不用 `page.wait_for_url` 的 glob——TOC 行是 `<a href="#">`，导航后 URL 尾巴上挂着一个
    `#`，glob 匹配整串，永不命中、白烧 30 秒。

    定向破坏（§0 第四条纪律）。以下 `E` 行全部是**实跑转录**，不是预测。生产侧的两枪
    （D3/D4/D5）用 `page.route` 改写**发给浏览器的响应体**，没有动 `src/` 一个字节——本波
    三个 agent 共用一个 worktree，就地改生产文件会让兄弟 agent 正在跑的用例假红。

    | # | 破坏点 | 观察到的红 |
    |---|---|---|
    | D1 | `R4_EXPECTED_IDS_CH1` 改成 `{"wi13-r4-chapter-zero"}` | `AssertionError: 翻章后渲染出的 id 集合是 {'wi13-r4-chapter-one'}，期望 {'wi13-r4-chapter-zero'}` / `assert {'wi13-r4-chapter-one'} == {'wi13-r4-chapter-zero'}` —— `1 failed, 2 passed` |
    | D2 | `assert R4_ID_CH0 not in after["html"]` 改成 `in` | `AssertionError: 旧章那条（'wi13-r4-chapter-zero'）仍出现在翻章后的 body HTML 里。…` / `assert 'wi13-r4-chapter-zero' in '<h1>Two</h1><p>Beta <mark class="annotation …" data-annotation-id="wi13-r4-chapter-one" …>prose</mark>.</p>'` —— `1 failed, 2 passed` |
    | D3 | **章节过滤失效**：route 改写 `/api/notes/**` 的响应，把第 0 章那条并进第 1 章的列表 | `AssertionError: 翻章后渲染出的 id 集合是 {'wi13-r4-chapter-one', 'wi13-r4-chapter-zero'}，期望 {'wi13-r4-chapter-one'}` / `Extra items in the left set: 'wi13-r4-chapter-zero'` —— `1 failed, 2 passed` |
    | D4 | route 改写 `annotations.js`，把 `if (window.Reader3Epub && window.Reader3Epub.onContentsReady) {` 改成 `if (false) {` | `AssertionError: Locator expected to have count '1'  Actual value: 0` / `14 × locator resolved to 0 elements` —— `1 failed, 2 passed` |
    | D5 | 翻章前 `delete window.Reader3Epub.displaySectionIndex`，逼 `findAndGo()` 走 `window.location.href` 兜底 | `AssertionError: 翻章后 window.__wi13_navigation_probe 是 None，…` / `assert None == 'wi13-set-before-toc-click'` —— `1 failed, 2 passed` |

    **D3 是本条构造的全部理由，值得单独说。** 它红在 id 那一项上，而它前面的
    `settle_marks(…, 1)`（`<mark>` **计数**）和 `after["texts"] == ["prose"]`（**文本**）
    **全都绿着过去了**——两条 annotation 覆盖同一段文字，`buildSegments` 把它们合并成了
    **一个**挂两个 id 的 span。也就是说：计数与文本这两项对「换章时取了全书标注」是**结构
    性失明**的，只有 `data-annotation-ids` 能看见。这就是矩阵 R1 重构要求两条 seed 用同一
    个 `quote` 的原因。

    **D5 同样值得单独说。** 它红在哨兵那一项上，而 `<mark>` 计数、文本、id 集合、
    `pathname_is` —— **前面每一项都是绿的**。整页加载会把新章正确渲染出来，URL 也是对的；
    唯一的差别只有 JS 全局环境被换掉。没有哨兵这一项，「站内导航彻底坏掉、退化成整页跳转」
    这件事在本条里完全不可见。

    ⚠️ **一枪没打响，记在这里（§0.5：如实记录今天的行为，不修）。** 最早的 D3 设计是 route
    改写 `annotations.js`、把 `window.addEventListener("reader3:chapter:change", scheduleRefresh);`
    整行换成注释。加了计数探针确认 route **确实命中、目标串确实存在、确实被替换掉**之后，
    本条仍然 `3 passed`。原因是 `scheduleRefresh` 被**三个**事件冗余地挂着
    （`reader3:content:rendered` / `reader3:chapter:change` / `reader3:annotations:updated`），
    外加一条独立的 `Reader3Epub.onContentsReady` 回调；拆掉其中任何**一根**线，换章重绘照常
    发生。结论：**本条今天护住的是「换章后重绘这件事发生了」这个可观测行为，而不是
    `reader3:chapter:change` 这一根具体的线**——K4 那根线单独断掉，今天没有任何 e2e 用例会
    红。这是一条待记账的护栏缺口，不是本波要修的东西。
    """
    _seed_two_chapters(e2e_books_dir)

    # --- 翻章前：第 0 章只有 A ------------------------------------------------
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    settle_marks(page, frame, R4_EXPECTED_MARK_COUNT)
    before = scan_marks(frame)
    assert before["texts"] == [R4_EXPECTED_MARK_TEXT], (
        f"翻章前第 0 章的 `<mark>` 文本序列是 {before['texts']!r}，"
        f"期望 {[R4_EXPECTED_MARK_TEXT]!r}"
    )
    assert mark_id_union(before) == R4_EXPECTED_IDS_CH0, (
        f"翻章前第 0 章渲染出的 id 集合是 {mark_id_union(before)!r}，"
        f"期望 {R4_EXPECTED_IDS_CH0!r}——这是翻章后那次断言的基线，"
        "它不成立的话「翻章后变成了 idB」什么也证明不了"
    )

    # --- 站内翻章：TOC 行 -----------------------------------------------------
    page.evaluate(f'window.{R4_NAV_PROBE} = "{R4_NAV_PROBE_VALUE}"')
    page.get_by_test_id("rd-rail-toc").click()
    page.locator(  # rd-toc-row 是 Jinja 宏渲出的 N 个同名节点，判别位见 ADR-0014
        f'[data-testid="rd-toc-row"][data-file-href="{R4_CH1_FILE_HREF}"]'
    ).click()

    # --- 翻章后：第 1 章只有 B，A 一个字都不剩 --------------------------------
    frame = reader_frame(page, CH1_ANCHOR)
    expect(frame.locator("body")).not_to_contain_text(CH0_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    settle_marks(page, frame, R4_EXPECTED_MARK_COUNT)

    after = scan_marks(frame)
    assert after["texts"] == [R4_EXPECTED_MARK_TEXT], (
        f"翻章后第 1 章的 `<mark>` 文本序列是 {after['texts']!r}，"
        f"期望 {[R4_EXPECTED_MARK_TEXT]!r}。空列表 ⇒ 换章后压根没重绘"
    )
    assert mark_id_union(after) == R4_EXPECTED_IDS_CH1, (
        f"翻章后渲染出的 id 集合是 {mark_id_union(after)!r}，期望 {R4_EXPECTED_IDS_CH1!r}。"
        f"含 {R4_ID_CH0!r} ⇒ 换章时取了全书标注，章节过滤失效；"
        "为空 ⇒ 换章后重绘整个没发生（挂在 `scheduleRefresh` 上的三个事件与 "
        "`Reader3Epub.onContentsReady` 那条回调**全部**失效，或内容根没换到新文档上）"
    )
    assert R4_ID_CH0 not in after["html"], (
        f"旧章那条（{R4_ID_CH0!r}）仍出现在翻章后的 body HTML 里。这一项不看文本形状、"
        "不看属性名，只问「A 有没有被渲染进这一章」——一个把 id 写进别的属性甚至注释里的"
        f"实现同样算渲染了它。\n  body HTML：{after['html']!r}"
    )

    pathname_is(page, R4_CH1_PATH)

    survived = page.evaluate(f"window.{R4_NAV_PROBE} ?? null")
    assert survived == R4_NAV_PROBE_VALUE, (
        f"翻章后 window.{R4_NAV_PROBE} 是 {survived!r}，"
        f"期望站内导航把它留着（{R4_NAV_PROBE_VALUE!r}）。它没了 ⇒ 这次翻章是**整页加载**"
        "——`findAndGo()` 在 `Reader3Epub.displaySectionIndex` 缺席时会退回 "
        "`window.location.href`，而整页加载会让新章高亮照样出现，上面几项因此都不会红"
    )


# ---------------------------------------------------------------------------
# R-5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "book_id,start_chapter,start_anchor,term,expected_mark,target_path,target_anchor",
    [
        pytest.param(
            BOOK_ID,
            1,
            CH1_ANCHOR,
            R5_TERM_EN,
            R5_EXPECTED_MARK_EN,
            R5_EN_TARGET_PATH,
            CH0_ANCHOR,
            id="latin",
        ),
        pytest.param(
            BOOK_ID_CJK,
            1,
            R5_CJK_CH1_ANCHOR,
            R5_TERM_CJK,
            R5_EXPECTED_MARK_CJK,
            R5_CJK_TARGET_PATH,
            R5_CJK_CH0_ANCHOR,
            id="cjk",
        ),
    ],
)
def test_r5_in_reader_search_highlights_the_hit_inside_the_iframe(
    page: Page,
    live_server: str,
    e2e_books_dir: Path,
    book_id: str,
    start_chapter: int,
    start_anchor: str,
    term: str,
    expected_mark: str,
    target_path: str,
    target_anchor: str,
) -> None:
    """R-5（有空格语言 vs 无空格语言的分词边界）：命中高亮出现在 **iframe 里**。

    **这条是 K5 的唯一护栏。** 契约明记 `search.js` 是 `getContentRoot()` /
    `onContentsReady()` 的**第二个消费方**（第一个是 `annotations.js`）。K5 一旦断裂，
    标注那一侧有整套 W 系列接着，搜索这一侧只有本条。

    **两个参数不是「跑两本书」，是两种分词形态。** 拉丁语侧的 `Alpha` 是一个**完整单词**；
    CJK 侧的 `咖啡` 是长词 `咖啡館` 的**子串**——无空格语言与有空格语言在检索上的分岔就在
    这里。只跑拉丁语侧会放过一个「按空格切词后整词匹配」的实现：它在英文上完全正确，在
    中文上一条都搜不到。

    **为什么起点章故意不含检索词。** 两本书都从第 1 章进入，而检索词只在第 0 章。于是
    「点命中 → 落到第 0 章 → 高亮出现」整条链都被走过一遍；若起点就是命中章，一个「从来
    不导航、只在当前章高亮」的实现照样绿。

    **为什么高亮那两项必须在 `frame` 里定位，不能在外层页面上。** `renderResults` 给结果
    面板里的每条片段也插了 `mark.search-match`。在外层文档上找同一个选择器**一定**能找到，
    且文本恰好就是检索词——那是一句恒真，它证明的只是「面板渲染了片段」。矩阵的自检说得
    很直白：只断「结果条数 > 0」会放过「面板出结果但 iframe 内不高亮」，而那正是 K5 断裂
    的表现形态。判据必须落在 iframe 这一侧。

    **`mark.search-match` 为什么允许用 class 定位。** 它由 `search.js` 的 `applyHighlights`
    在运行时插进**用户那本书自己的 XHTML**，既不在我们的模板里、也没有任何一处能给它加
    `data-testid`。所以那一行带显式的 `# lint-e2e-selectors: allow` 并写明理由。
    **没有改用 `frame.evaluate` 去绕开 lint**——`scripts/lint_e2e_selectors.py` 的 docstring
    把那种做法称为「看不见的绕过，比显式放行糟得多」。

    **断言顺序：先正文，后 URL**（欠账 #12，同 R-4）。这一支虽然走的是整页加载
    （点击回调赋 `window.location.href`），顺序仍照统一纪律写。

    定向破坏（§0 第四条纪律）。以下 `E` 行全部是**实跑转录**，不是预测。D7 用 `page.route`
    改写发给浏览器的 `search.js` 响应体，没有动 `src/`（理由同 R-4 的破坏表）。

    | # | 破坏点 | 观察到的红 |
    |---|---|---|
    | D6 | `R5_EXPECTED_MARK_CJK` 改成 `"咖啡館"` | `AssertionError: Locator expected to have text '咖啡館'  Actual value: 咖啡` / `14 × locator resolved to <mark class="search-match search-current">咖啡</mark>` —— `1 failed, 2 passed`（**只红 cjk 一支，latin 仍绿**，两支参数各自独立） |
    | D7 | route 改写 `search.js`，给 `applyHighlights(container, term, caseSensitive) {` 后面塞一句 `return [];` | `AssertionError: Locator expected to have count '1'  Actual value: 0` / `14 × locator resolved to 0 elements` —— `2 failed, 1 passed` |
    | D8 | `CORPUS_CHECKS`（当时还是 `_assert_corpus_unchanged`）的期望侧改成 `"咖啡館"` | `AssertionError: CJK 语料的检索词变了：`epub_corpus.CJK_SEARCH_TERM` 现在是 '咖啡'…` / `assert '咖啡' == '咖啡館'` —— 探针先响，人被直接指到语料上 |

    **D7 就是矩阵点名的那个失败模式，值得单独说。** 它两支参数一起红，而红点全部落在
    **iframe 内**那两项上——它前面的 `expect(hits).to_have_count(1)`（结果面板命中数）
    **是绿的**。也就是说 D7 复现的正是「面板出结果、iframe 内不高亮」：一个只断「结果条数
    > 0」的用例在 D7 下会**全绿放过**。判据必须落在 iframe 这一侧，这里有实跑的证据。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    open_reader(page, live_server, book_id, start_chapter, start_anchor)

    page.get_by_test_id("rd-rail-search").click()
    search_input = page.get_by_test_id("rd-search-input")
    search_input.fill(term)
    # `performSearch()` 只挂在 Enter 的 keydown 上，`fill()` 自己不触发任何检索。
    search_input.press(ENTER)  # lint-e2e-selectors: allow —— "Enter" 是键名不是选择器；lint 的 `.press(` 规则把第一个字符串实参当选择器扫，这里是误报。显式放行好过换个写法悄悄躲开

    hits = page.get_by_test_id("rd-search-hit")
    expect(hits).to_have_count(R5_EXPECTED_HITS)
    hits.click()

    frame = reader_frame(page, target_anchor)
    pathname_is(page, target_path)

    hit_marks = frame.locator("mark.search-match")  # lint-e2e-selectors: allow —— applyHighlights 运行时插进用户那本书的 XHTML，插不进 testid
    expect(hit_marks).to_have_count(R5_EXPECTED_MARK_COUNT)
    expect(hit_marks).to_have_text(expected_mark)
