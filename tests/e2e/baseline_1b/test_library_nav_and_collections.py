"""WI-15 —— X-2a / X-2b / X-2c：书库导航、侧栏范围过滤、集合创建与切换。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-15（最高权威，用例条数与断言
层级以它为准，含 §WI-15 的两条修订【R1】【R2】）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §6（X 系列）、
§0（六条写作纪律）、§0.5（本模块属 `baseline-1b`）、§0.6（波次编排，本模块属 Wave 4）。

矩阵为本模块定的 **Law（集合成员的往返与排他）**：把一本书加进集合 C 之后，C 的书目列表
**含**它，且其他集合／范围下的列表按定义不含它。「集合名出现在侧栏」不是这条律的证据。
这条律覆盖 **X-2a 与 X-2c**；**X-2b 不在这条律之下**，它自己的「No law: 域退化」写在
`test_x2b_...` 的 docstring 里（矩阵【R1】）。

-------------------------------------------------------------------------------
为什么每条判据不是摆设
-------------------------------------------------------------------------------

**书目断言一律断「哪几本可见」，不断「可见几本」。** `applyFilters()` 的实现是给不匹配的
卡片挂 `hidden` 属性（`setHidden`），全部四张卡片**始终留在 DOM 里**。所以
`to_have_count(4)` 对「过滤把 A 藏了、把 B 放出来」这种换位错误完全是盲的。本模块统一走
`helpers.assert_visible_book_ids`：先断卡片总数等于语料本数，再对**每一本**逐个断
visible／hidden。这两半合起来才是集合等值——少了前一半，多渲一张陌生卡片不会红；少了
后一半，任何换位都不会红。

**四本的本数从 `conftest.E2E_BOOK_IDS` 派生，不写字面量 4**（矩阵 §WI-15 X-2a 原文
「不硬编码——WI-3 之后是四本」，任务书 §0.6 同款约定）。再加一本语料时该红的是
「书库条数」这条判据本身，而不是「加语料」这个动作。

**X-2a 的返回那一程不能只断 URL。** 「回到 `/`」和「回到一个能列出全部四本书的书库」是两
件事：服务端 `_scan_books` 坏掉时 URL 照样是 `/`，页面却是 `lib-empty`。所以返回后重跑一次
`helpers.assert_visible_book_ids`，并且把它排在 URL 断言**之前**——先断可观测的渲染结果，再断
地址栏（任务书 §0.6 跨波欠账 #12 的顺序要求；本条虽是整页导航、不受那条竞态影响，但顺序
统一比按情况分岔可靠）。

**X-2c 断的是「该集合下有哪几本书」，不是「侧栏出现了集合名」**（矩阵「自检」原文：
只断后者的话，一个「建了集合但没把书加进去」的实现全绿）。本条同时断三样：
(1) 集合范围下可见集合 == `{smoke_data}`，其余三本 hidden；(2) 切回 `all` 后四本全回来；
(3) **刷新页面之后重做 (1)**——落库 → 刷新 → 同一状态回来，这是纪律一（往返断言）要求的
那一半，也是「持久化文件真的写对了」的唯一正向证据。

-------------------------------------------------------------------------------
X-2c 的清理为什么在 fixture 的 finalizer 里，且为什么是**模块级** fixture
-------------------------------------------------------------------------------
`live_server` 与 `e2e_books_dir` 都是 session 级共享的，集合又落在
`{books_dir.parent}/config/library_collections.json`——**一条残留集合会跨用例、跨模块地
留在侧栏里**。写在用例末尾的清理在用例中途失败时根本不会执行，所以清理必须挂在 fixture
的 finalizer 上（矩阵「清理要求」原文）。矩阵【R2】追加的那一层理由更要紧：残留还会污染
`tests/e2e/test_testid_dom_uniqueness.py` 的 `library_page`（侧栏多出
`lib-sidebar-collection` 节点），而那个模块**不在任何组 marker 之下**，009 的门槛不保护
它——清理因此是跨模块的必需品，不只是本条的卫生。

**但 fixture 不能写进 `tests/e2e/conftest.py`**（任务书 §0.6 执行纪律 2：共享文件一波至多
授权一个 WI 改，本波的授权不在 WI-15 手上），**也不能新建
`tests/e2e/baseline_1b/conftest.py`**——组目录里一旦有 `conftest.py`，`tests/e2e/` 根目录
就不再是 `rootdir` 之外唯一被插进 `sys.path` 的位置，`test_harness_smoke.py` 与
`test_testid_dom_uniqueness.py` 依赖的裸模块导入（`from conftest import BOOK_ID`）会断。
所以它是**本文件里的模块级 fixture**。

清理的两条性质，缺一条都还是 flaky 源：

* **名字带每次唯一的后缀**（`uuid4().hex[:8]`）——上一轮被 SIGKILL 掉的进程若留下同名集合，
  固定名字会让新一轮撞上一个「已存在」的 409，而红的地方与被测行为无关。
* **finalizer 幂等**——按前缀扫，删已经不存在的集合返回 404，按成功处理。用例根本没走到
  创建那一步（更早的断言先红了）时，清理必须是一次空转，而不是又一条错误。

-------------------------------------------------------------------------------
可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-04，六处全部已还原）
-------------------------------------------------------------------------------
本模块三条用例全是特征化用例——被测行为上线数月，**红不可得**。下表每一行是一次**真的
跑过**的定向破坏：改一处生产代码 → 只跑受影响的那一条 → 逐字抄回失败输出 → 还原 →
`git diff --stat -- src/` 无输出（六次逐次核验，全部为空）。

| # | 破坏点（每次只动一处） | 失败输出（逐字） | 它证明了哪条判据不是摆设 |
|---|---|---|---|
| S1 | `reader.html` 右侧工具条 `<a href="/" class="rt-btn" title="Back to Library">` → `href="/settings"` | `AssertionError: 返回后的书库：书卡节点总数应恒等于语料本数（过滤只挂 hidden，不删节点）` ／ `Expected value: '4'` ／ `Actual value: 0` ／ `14 × locator resolved to 0 elements` | X-2a **返回那一程**：往返回来必须是一个真的列得出四本书的书库，不是「导航发生过」 |
| S2 | `library.html` 的 `lib-sidebar-scope-pdf` 去掉 `disabled` | `AssertionError: format:pdf 是尚未支持的格式，侧栏按钮必须是 disabled` ／ `Actual value: enabled` ／ `resolved to <button … data-scope="format:pdf" … data-testid="lib-sidebar-scope-pdf">` | X-2b 边界的**前一半**：`disabled` 这个状态本身被断住了 |
| S2b | 同上，但换成 `disabled` → `aria-disabled="true"` | `AssertionError: format:pdf …必须是 disabled` ／ `Actual value: enabled` ／ `resolved to <button … aria-disabled="true" …>` | **一条被证伪的猜测，留档**：原以为 Playwright 的 `to_be_disabled()` 会认 `aria-disabled`，于是这一改能让前一半假绿。实测**不认**——该按钮显式写了 `role="listitem"`，`aria-disabled` 只对少数原生可禁用角色生效。所以「用 aria 冒充 disabled」这条假绿路径在本页上根本不存在，S2c 才是让后一半独立发言的那次 |
| S2c | 生产：同 S2（去掉 `disabled`）；**用例**：临时删掉 `to_be_disabled()` 那一行，好让后一半独立发言 | `AssertionError: 强行点过 format:pdf 之后（范围应仍是 format:epub）：cjk_data 应可见（期望可见集合 ['cjk_data', 'repeat_data', 'second_data', 'smoke_data']）` ／ `Actual value: hidden` | X-2b 边界的**后一半**：`click(force=True)` 之后范围**没有**变成 `format:pdf`。这一半不是前一半的复述——它断的是「点不动」，前一半断的是「标着不可点」 |
| S3 | `library.js` 的 `matchesScope` 里 `return fmt === state.scope.slice("format:".length);` → `return false;` | `AssertionError: 范围 format:epub：cjk_data 应可见（期望可见集合 ['cjk_data', 'repeat_data', 'second_data', 'smoke_data']）` ／ `Actual value: hidden` | X-2b 等价类 2：`format:epub` 下断的是与**字面量常量**的集合等值，不是「和上一屏一样」 |
| S4 | `library.js` 的 add-to-collection picker 回调里 `const add = Array.from(state.selectedBookIds);` → `const add = [];`（即矩阵自检点名的那个坏实现：**建了集合但没把书加进去**） | `AssertionError: 加书之后 library_collections.json 里该集合的 book_ids 应当恰好是 ['smoke_data']，实际 []` ／ `assert [] == ['smoke_data']` ／ `Right contains one more item: 'smoke_data'` | X-2c 的**持久化侧**：磁盘上真的写进了那一本 |
| S4b | 生产：同 S4；**用例**：临时删掉上面那条持久化断言，好让 DOM 侧独立发言 | `AssertionError: 切到新集合的范围下：smoke_data 应可见（期望可见集合 ['smoke_data']）` ／ `Actual value: hidden` | X-2c 的 **DOM 侧**：切到该集合后列表里**有**那一本。一条只断「侧栏出现了集合名」的用例在 S4 下会全绿——本行是它不会的证据 |

S2c 与 S4b 各自额外动了**用例自己**的一行（删掉排在前面的那条断言），因为那两条判据被前一条
短路了，不删就永远轮不到它说话。两次都在同一轮内按备份逐字节还原，`diff` 无输出。

-------------------------------------------------------------------------------
Wave 4 留在原地、Wave 5 已上收进 `helpers.py` 的东西（欠账 #25）
-------------------------------------------------------------------------------
`assert_visible_book_ids`、`read_collections` / `collections_file`、`http_json` /
`delete_collections_with_prefix` 都是**书库页**的通用件，不是本模块特有的构造。Wave 4 没有任何
WI 被授权改 `tests/e2e/helpers.py`（§0.6 纪律 2），所以当时照欠账 #13 的先例留在模块内；
Wave 5 的 WI-10 一次上收，断言文本原样，只改了名字与住址。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterator, List, Set
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID, E2E_BOOK_IDS  # type: ignore[import-not-found]
from epub_corpus import EPUB2_TITLE  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    assert_corpus_unchanged,
    assert_visible_book_ids,
    delete_collections_with_prefix,
    pathname_is,
    read_collections,
    reader_frame,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# 期望值（§0 第五条纪律：守恒断言的「动作前」一侧必须是写死的字面量）
# ---------------------------------------------------------------------------

#: X-2a / X-2c 用的那本书，逐字。**不写成 `BOOK_ID`**：`BOOK_ID` 是「fixture 书库的第一本」
#: 这个角色，本模块要的是「就是 smoke_data 这本」。两者今天相等，由下面的绊线守着。
SMOKE_BOOK_ID = "smoke_data"
SMOKE_BOOK_TITLE = EPUB2_TITLE

#: 第 0 章的正文探针与 URL，逐字。URL **不写成 f-string 拼 book id**——K6 要断的正是这个
#: 形状本身，用被测源头去生成期望值等于什么都没断。
CH0_ANCHOR = "Alpha prose."
CH1_ANCHOR = "Beta prose."
CH0_PATH = "/read/smoke_data/0"
LIBRARY_PATH = "/"

#: 语料四本全是 EPUB（`conftest.E2E_BOOKS` 的四个 builder：`build_epub2` / `build_epub3` /
#: `build_cjk` / `build_huge_epub`），因此 `format:epub` 下的可见集合与 `all` 相同。
#: 这不是巧合而是**域退化**——见 X-2b 的 docstring。
ALL_BOOK_IDS: Set[str] = set(E2E_BOOK_IDS)

#: X-2c 建出来的集合名前缀。只用字母数字与下划线，是为了绕开
#: `collections_service._NAME_RE` 的一处**实测怪癖**：它的模式是
#: `^[A-Za-z0-9 _\\\\-\\\\.&()]+$`，字符类里那两处双反斜杠让 `-` 落成了「反斜杠到反斜杠」
#: 的区间端点，于是**连字符实际被拒**（`"a-b"` 不合法），反倒放行了反斜杠。
#: 这是生产侧的一处小缺陷，本波按 §0.5「特征化今天的行为」不修，已在回报里点名；
#: 用例这边只要不去踩它——名字里一个连字符都不带。
COLLECTION_NAME_PREFIX = "wi15_x2c_"


#: 绊线（喂给 `helpers.assert_corpus_unchanged`）：本模块的字面量期望值与 fixture 语料脱钩时，
#: 报「语料改名了」而不是「没找到」。
CORPUS_CHECKS = (
    (
        BOOK_ID,
        SMOKE_BOOK_ID,
        f"fixture 书库的第一本改名了：{BOOK_ID!r} != {SMOKE_BOOK_ID!r}。"
        "本模块的 CH0_PATH 等字面量需要跟着改。",
    ),
    (
        SMOKE_BOOK_ID in ALL_BOOK_IDS,
        True,
        f"{SMOKE_BOOK_ID!r} 不在 E2E_BOOK_IDS={sorted(ALL_BOOK_IDS)!r} 里",
    ),
    (len(ALL_BOOK_IDS), len(E2E_BOOK_IDS), "E2E_BOOK_IDS 里有重复的书库目录名"),
)


@pytest.fixture
def x2c_collection_name(live_server: str) -> Iterator[str]:
    """产出一个**本次调用唯一**的集合名，并在 finalizer 里把它删干净。

    为什么是 finalizer 而不是用例末尾、为什么是模块级 fixture 而不是 `conftest.py`：
    见模块 docstring 的「X-2c 的清理为什么……」一节。

    前后各扫一次：**前置**清掉上一轮硬崩留下的同前缀残留（否则第一条断言就在一个脏侧栏上
    做判断），**后置**清掉本轮自己建的。只做后置的话，一次 SIGKILL 会把脏状态永久留给
    同一个 session 里后面的每一条用例和 `test_testid_dom_uniqueness.py`。
    """
    delete_collections_with_prefix(live_server, COLLECTION_NAME_PREFIX)
    name = f"{COLLECTION_NAME_PREFIX}{uuid.uuid4().hex[:8]}"
    try:
        yield name
    finally:
        delete_collections_with_prefix(live_server, COLLECTION_NAME_PREFIX)


# ---------------------------------------------------------------------------
# X-2a 书库 ↔ 阅读器往返导航
# ---------------------------------------------------------------------------


def test_x2a_library_to_reader_and_back_round_trip(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """X-2a（S1，L3）：书库 → 点书卡进阅读器 → 点「返回书库」→ 书目原样回来。

    **Law（集合成员的往返与排他）在这一条上的形态**：往返一圈之后书库列出的
    `data-book-id` 集合必须与出发前**逐个相同**，而基准是写死在 `conftest.E2E_BOOK_IDS`
    里的常量，不是出发前从页面上读回来的值（§0 第五条纪律：两边同源的比较永远绿）。

    四项判据，每一项都有具体的坏实现能让其余三项全绿：

      1. **出发前**可见书卡集合 == 四本。书库扫描坏掉时红。
      2. 进入后 URL 的 path **逐字**等于 `/read/smoke_data/0`。书卡的 `href` 指到别的书或
         别的下标时红；`endswith("/0")` 这类弱形式不行——`/read/second_data/0` 也满足。
      3. iframe 正文含 `Alpha prose.` 且**不含** `Beta prose.`。`assert iframe is not None`
         在一本空白书上照样绿；反向那半句挡的是「把整本书一次渲染完」。
      4. **返回后**可见书卡集合仍 == 四本，且 pathname == `/`。只断 URL 会放过
         「回到了 `/` 但书库是空的」——服务端 `_scan_books` 坏掉正是这个形状。

    **返回那一程用的是 ARIA 可访问名，不是 testid。** `reader.html` 右侧工具条的返回链接是
    `<a href="/" class="rt-btn" title="Back to Library">` ＋ 一个纯 `<svg>` 子节点，**没有
    `data-testid`**，可访问名只能由 `title` 兜底。ARIA role/name 是选择器政策里与 testid
    并列的那一半（任务书 §1），所以这合规——但它与欠账 #15 是同一种脆：文案一改本条即断，
    且断的时候报的是「找不到元素」而不是「文案改了」。**这一处该在 4A 补 testid**，回报里
    已点名。

    **本条不进 iframe 里做任何结构断言，所以不受欠账 #16（一次加载跑两遍
    `loadAndRender()`）影响。** 那条竞态伤的是「夹在两遍重绘之间装上的 live range」，
    而这里只有 `reader_frame` 的 `to_contain_text` ——正文文本在两遍重绘之间不变，
    `expect` 自带重试，没有可被 `normalize()` 折叠的东西。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    page.goto(f"{live_server}{LIBRARY_PATH}")
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="出发前的书库")

    card = page.locator(f'[data-testid="lib-book-card"][data-book-id="{SMOKE_BOOK_ID}"]')
    # 卡内那个 `<a>` 没有自己的 testid，只有 `aria-label="Read {{ book.title }}"`。
    card.get_by_role("link", name=f"Read {SMOKE_BOOK_TITLE}").click()

    frame = reader_frame(page, CH0_ANCHOR)
    actual_path = urlparse(page.url).path
    assert actual_path == CH0_PATH, (
        f"从书库点进来落在 {actual_path!r}，不是期望的 {CH0_PATH!r}。book-card 的 href 形状变了？"
    )
    expect(frame.locator("body")).not_to_contain_text(CH1_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    # 右侧工具条的返回链接：无 testid，可访问名由 title 兜底（见 docstring）。
    page.get_by_role("link", name="Back to Library").click()

    # 先断渲染结果、再断地址栏（任务书 §0.6 欠账 #12 的顺序要求）。
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="返回后的书库")
    pathname_is(page, LIBRARY_PATH)


# ---------------------------------------------------------------------------
# X-2b 侧栏范围切换后书目列表内容正确
# ---------------------------------------------------------------------------


def test_x2b_sidebar_scope_switch_yields_the_right_book_list(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """X-2b（S2，L2，**boundary**）：`all` / `format:epub` / `format:pdf` 三个范围取值的等价类枚举。

    **No law: 域退化** —— 四本语料**全是 EPUB**，`format:pdf` 恒为 `disabled`。因此
    「范围 → 书目集合」这个映射在本套件的语料下只有一个非退化取值，没有可断的守恒／往返／
    单调关系。本条是**等价类枚举**，不是性质。将来有人加入一本 PDF 语料时，本条是第一处
    需要从 S2 升级成真正性质（`⋃ scopes = all` 且各 scope 两两不交）的地方。
    （矩阵 §WI-15【R1】原文；这一句被要求写进本 docstring，正因为它记录的是一条**今天断不
    出来**的性质——不写下来的话，下一个读这条用例的人只会看见「两次断言结果一样」，
    并合理地怀疑其中一次是多余的。）

    三个等价类各自断什么：

      * **`all`**：可见集合 == 四本。这是页面初始态，同时也是后两项的对照基准。
      * **`format:epub`**：可见集合 == 四本（域退化：四本都是 epub）。判据仍然不是
        「和刚才一样」——`helpers.assert_visible_book_ids` 断的是与**字面量常量**
        `ALL_BOOK_IDS` 的集合等值，所以一个「format 过滤按 title 匹配」的实现照样红。
      * **`format:pdf`**：**边界，断它 disabled 且点不动，而不是跳过它**（矩阵原文）。
        两半：`to_be_disabled()`，以及 `click(force=True)` 之后可见集合**没有变化**。
        后一半才是「点不动」的正向证据——`disabled` 属性掉了但监听器还在的实现会让前一半
        绿、后一半红；反过来，属性还在但被 JS 强行激活的实现会让后一半红。
        为什么这个「没有变化」不空转：此刻处在 `format:epub` 下、四本全可见，而一旦
        `format:pdf` 真的生效，`matchesScope` 会把四本**全部**隐藏——差别是 4 对 0，
        不是一个需要显微镜的差别。

    `click(force=True)` 是有意的：`force` 跳过 Playwright 自己的 actionability 检查，
    让鼠标事件真的落到那个坐标上，于是被测的是**浏览器对 disabled 表单控件的原生行为**
    （不派发 click）＋ 应用没有给它别的激活路径。不加 `force` 的话 Playwright 会先在
    actionability 上超时，那证明的是 Playwright 的检查工作正常，不是应用的行为。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    page.goto(f"{live_server}{LIBRARY_PATH}")

    # 等价类 1：all（初始态）
    expect(page.get_by_test_id("lib-sidebar-scope-all")).to_be_visible()
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="范围 all")

    # 等价类 2：format:epub
    page.get_by_test_id("lib-sidebar-scope-epub").click()
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="范围 format:epub")

    # 等价类 3：format:pdf —— 边界，断 disabled 且点不动
    pdf_scope = page.get_by_test_id("lib-sidebar-scope-pdf")
    expect(pdf_scope, "format:pdf 是尚未支持的格式，侧栏按钮必须是 disabled").to_be_disabled()
    pdf_scope.click(force=True)
    assert_visible_book_ids(
        page, ALL_BOOK_IDS, where="强行点过 format:pdf 之后（范围应仍是 format:epub）"
    )


# ---------------------------------------------------------------------------
# X-2c 集合创建 → 加书 → 切换后列表内容正确且只在该集合里
# ---------------------------------------------------------------------------


def test_x2c_collection_scope_lists_exactly_the_added_book(
    page: Page, live_server: str, e2e_books_dir: Path, x2c_collection_name: str
) -> None:
    """X-2c（S5，L2，**round-trip + 排他**）：建集合 → 把 `smoke_data` 加进去 → 切过去，列表恰好是那一本。

    **Law（集合成员的往返与排他）**：加进集合 C 之后，C 的书目列表**含**它，且其他范围下
    的列表按定义不含它。「集合名出现在侧栏」不是这条律的证据——矩阵的自检原文：只断侧栏
    出现了集合名的话，一个「建了集合但没把书加进去」的实现全绿。本条因此一次都没有断过
    「侧栏有这个名字」，断的全是**书目列表的内容**。

    五项判据：

      1. 切到集合范围后可见集合 == `{smoke_data}`，**其余三本 hidden**。
         「建了但没加书」⇒ 0 本可见 ⇒ 红；「加书没生效、过滤退化成 all」⇒ 4 本可见 ⇒ 红。
      2. **持久化文件**里该集合的 `book_ids` == `["smoke_data"]`。DOM 对了而磁盘没写，
         或者磁盘写了别的书，(1) 有可能被前端的内存态掩盖；这一项直接读
         `library_collections.json`（`server._collections_file_path` 的口径），
         是「文件系统即数据库」那条原则下的终态证据。
      3. 切回 `all` 后四本全回来。排他性不是「别的书消失了」——它们只是被这个范围过滤掉，
         换个范围必须原样在。少了这一项，一个「加进集合时把别的书从书库里删了」的实现
         能让 (1) 全绿。
      4. **刷新页面之后重做 (1)**。这是纪律一（往返断言）的那一半：落库 → 刷新 → 状态回到
         同一处。刷新前的 (1) 只证明前端内存态自洽，刷新后的才证明它真的落了盘并被
         服务端重新渲染了出来。
      5. 集合名带**每次唯一的后缀**，且由 fixture 的 finalizer 删除。见模块 docstring。

    **加书走的是真实 UI 路径**，不是直接打 API：选择模式 → 勾书卡的复选框 →
    `lib-bulk-collection` → 在 `lib-add-to-collection-select` 里点该集合。矩阵的
    「Refactor that would break this」列的是「集合成员的持久化格式改变／集合过滤失效」，
    两者都在这条链上。

    **集合行与 picker 里的按钮都没有自己的 testid**，只有集合名文本。两处都用
    `get_by_role("button", name=…)`，且都**先用 testid 把范围收窄**——侧栏那处收窄到
    `[data-testid="lib-sidebar-collection"][data-collection-id="…"]`（ADR-0014 闭合清单里的
    `data-collection-id`），弹层那处收窄到 `lib-add-to-collection-select`。不收窄的话，
    同一个集合名在侧栏和弹层里各有一个同名按钮，strict 模式必抛。

    ⚠️ **生产缺陷（本条特征化，未修）**：`library.js` 的 `setSelectMode` 给 `<body>` 加的是
    `select-mode`，而 `library.html` 的样式表键的是 `.selection-mode .select-checkbox`，
    两个名字对不上，于是**选择模式下复选框的 `opacity` 仍是 0**，只有 `.book-card:hover`
    那条规则能把它显出来。Playwright 视 `opacity: 0` 为可见、且点击前会先 hover，所以本条
    照常通过——但真人用触屏或键盘时，选择模式没有任何视觉反馈。已在回报里点名，按 §0.5
    「特征化今天的行为」不在本波修。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    assert read_collections(e2e_books_dir) == [] or all(
        not str(c.get("name") or "").startswith(COLLECTION_NAME_PREFIX)
        for c in read_collections(e2e_books_dir)
    ), "清理 fixture 的前置扫描没生效：起点上还有同前缀的残留集合"

    page.goto(f"{live_server}{LIBRARY_PATH}")
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="建集合前的书库")

    # ---- 建集合 ----------------------------------------------------------
    page.get_by_test_id("lib-sidebar-create-collection").click()
    expect(page.get_by_test_id("lib-modal-create-collection")).to_be_visible()
    page.get_by_test_id("lib-collection-name-input").fill(x2c_collection_name)
    page.get_by_test_id("lib-modal-create-collection-primary").click()
    expect(page.get_by_test_id("lib-modal-create-collection")).to_be_hidden()

    created = [
        c for c in read_collections(e2e_books_dir) if c.get("name") == x2c_collection_name
    ]
    assert len(created) == 1, (
        f"创建之后 library_collections.json 里应恰好有 1 个名为 {x2c_collection_name!r} 的集合，"
        f"实际 {len(created)} 个：{read_collections(e2e_books_dir)!r}"
    )
    collection_id = str(created[0]["id"])
    assert created[0].get("book_ids") == [], (
        f"刚建出来的集合应当是空的，实际 book_ids={created[0].get('book_ids')!r}"
    )

    # ---- 把 smoke_data 加进去（走真实 UI 路径）----------------------------
    page.get_by_test_id("lib-toolbar-select-mode").click()
    expect(page.get_by_test_id("lib-bulk-bar")).to_be_visible()

    card = page.locator(f'[data-testid="lib-book-card"][data-book-id="{SMOKE_BOOK_ID}"]')
    card.get_by_role("checkbox").check()

    add_btn = page.get_by_test_id("lib-bulk-collection")
    expect(add_btn, "勾了一本书之后「Add to collection」应当可用").to_be_enabled()
    add_btn.click()

    picker = page.get_by_test_id("lib-add-to-collection-select")
    expect(picker).to_be_visible()
    picker.get_by_role("button", name=x2c_collection_name).click()
    expect(page.get_by_test_id("lib-modal-add-to-collection")).to_be_hidden()

    # 判据 2：持久化文件的终态
    def _persisted_book_ids() -> List[str]:
        for c in read_collections(e2e_books_dir):
            if str(c.get("id")) == collection_id:
                return [str(x) for x in (c.get("book_ids") or [])]
        return []

    expect(page.get_by_test_id("lib-modal-add-to-collection")).to_be_hidden()
    assert _persisted_book_ids() == [SMOKE_BOOK_ID], (
        f"加书之后 library_collections.json 里该集合的 book_ids 应当恰好是 "
        f"[{SMOKE_BOOK_ID!r}]，实际 {_persisted_book_ids()!r}"
    )

    # ---- 判据 1：切到集合范围 --------------------------------------------
    collection_row = page.locator(
        f'[data-testid="lib-sidebar-collection"][data-collection-id="{collection_id}"]'
    )
    expect(collection_row).to_be_visible()
    collection_row.get_by_role("button", name=x2c_collection_name).click()
    assert_visible_book_ids(page, {SMOKE_BOOK_ID}, where="切到新集合的范围下")

    # ---- 判据 3：切回 all --------------------------------------------------
    page.get_by_test_id("lib-sidebar-scope-all").click()
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="从集合切回 all")

    # ---- 判据 4：刷新之后重做判据 1（往返）--------------------------------
    page.reload()
    collection_row_after = page.locator(
        f'[data-testid="lib-sidebar-collection"][data-collection-id="{collection_id}"]'
    )
    expect(collection_row_after).to_be_visible()
    collection_row_after.get_by_role("button", name=x2c_collection_name).click()
    assert_visible_book_ids(page, {SMOKE_BOOK_ID}, where="刷新后再切到该集合（往返断言）")
