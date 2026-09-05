r"""WI-15 —— X-2a / X-2b / X-2c：书库导航、侧栏范围过滤、集合创建与切换。
外加 **X-2d**（2026-09-05 追加，审计发现 #60）：选择态的作用域。

（本 docstring 是 **raw 字符串**：S5 那一行誊抄的失败输出里含 `\\s`，而表格里的
`\|` 是 Markdown 的转义竖线——两者都必须逐字保留，非 raw 会让 Python 把它们吃掉
并抛 `DeprecationWarning: invalid escape sequence`。）

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-15（最高权威，用例条数与断言
层级以它为准，含 §WI-15 的两条修订【R1】【R2】）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §6（X 系列）、
§0（六条写作纪律）、§0.5（本模块属 `baseline-1b`）、§0.6（波次编排，本模块属 Wave 4）。

**X-2d 不在矩阵里，这是有意的偏离，理由必须写清楚**：矩阵是「用例条数以它为准」的权威，
而 X-2d 的来源不是矩阵，是 **009 分支自己的审计发现 #60**——本分支改了
`library.js` 的 `syncSelectionForBookId`（裸的 `[data-book-id="…"]` → 限定到
`.book-card` / `.book-row`），而 009 的契约是「安全网，不是行为变更窗口」。一条**没有
判据守着的生产语义变更**留在一个专门用来立判据的分支上，是这套安全网最不该出现的形状。
所以本条不是「矩阵漏了一个场景」，是「本分支欠了一条自己的证据」。它的完整理由见下面
的「X-2d 为什么存在」一节。

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
X-2d 为什么存在（审计发现 #60，2026-09-05）
-------------------------------------------------------------------------------
009 分支对 `library.js` 做了两处**耦合**的改动：

1. `LIB_BOOK_STATUS_TESTID`（4 个名字）拆成 `LIB_BOOK_GRID_STATUS_TESTID` ＋
   `LIB_BOOK_ROW_STATUS_TESTID`（8 个名字），且 `setStatusForBook` 现在把
   `data-book-id` 也挂到**状态 pill 自己身上**。原因是生产模板同时渲染 `.book-card` 与
   `.book-row`（靠 CSS 显隐），同一本书贡献两个 pill，共用一个 testid 字面量必撞
   Playwright 的 strict 模式。**这一半已经有判据**：
   `tests/e2e/test_testid_dom_uniqueness.py` 的动态哨兵。
2. `syncSelectionForBookId` 从裸的 `qsa('[data-book-id="…"]')` 改成限定到
   `.book-card` / `.book-row`。**这一半原本一条判据都没有**——而它是被 (1) 逼出来的：
   pill 一旦带上 `data-book-id`，裸选择器就会把 pill 也选中，给它挂 `is-selected`
   并去找一个不存在的 `.select-checkbox`。

生产代码自己的注释承认了这件事的性质：「今天没有可见后果，只是因为两条 `is-selected` 的
CSS 规则恰好限定了作用域——那是巧合，不是保证」。那两条规则是
`library.css:406` 的 `.book-card.is-selected` 与 `:568` 的 `.books-table tbody tr.is-selected`，
两条都带元素限定，所以一个挂在 `<span class="status-pill">` 上的 `is-selected` 今天不画任何
像素。**「今天不画像素」不是判据能断的东西，也不是明天还成立的东西**：那两条选择器里的
`.book-card` / `tbody tr` 一旦在 Phase 4 的重设计里被松成 `.is-selected`（这是重设计里极
常见的一步），状态 pill 就会当场跟着卡片一起变色，而没有任何测试会红。

所以 X-2d 断的**不是**「pill 长什么样」，是**作用域本身**：`is-selected` 这个类在一次选择
里落到了**哪些**节点上。判据写成闭集等值（下面 `_book_id_nodes` 的用法），不是逐个 pill 的
点名——点名式断言只覆盖今天存在的 pill，闭集式断言把「将来新增的、也带 `data-book-id` 的
任何节点」一并纳入：新节点若被错误地标成选中，红的是 X-2d，而不是三个月后某次重设计。

**X-2d 只加一条 item**（`EXPECTED_BASELINE_ITEMS` 65 → 66，两处常量与 soak 台账同步）。
选择态的正向与反向（选中／取消）在同一条里做往返，不拆成两条参数化：它们共享同一段
建场（进选择模式、等状态 pill 落定），拆开等于把那段建场跑两遍买同一个信号。

-------------------------------------------------------------------------------
可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-04 六处 ＋ 2026-09-05 一处，全部已还原）
-------------------------------------------------------------------------------
本模块四条用例全是特征化用例——被测行为上线数月，**红不可得**。下表每一行是一次**真的
跑过**的定向破坏：改一处生产代码 → 只跑受影响的那一条 → 逐字抄回失败输出 → 还原 →
`git diff --stat -- src/` 无输出（前六次逐次核验，全部为空；后三次 S5／S5b／S5c 根本没有
落盘到 `src/`，手法见表下的说明）。

| # | 破坏点（每次只动一处） | 失败输出（逐字） | 它证明了哪条判据不是摆设 |
|---|---|---|---|
| S1 | `reader.html` 右侧工具条 `<a href="/" class="rt-btn" title="Back to Library">` → `href="/settings"` | `AssertionError: 返回后的书库：书卡节点总数应恒等于语料本数（过滤只挂 hidden，不删节点）` ／ `Expected value: '4'` ／ `Actual value: 0` ／ `14 × locator resolved to 0 elements` | X-2a **返回那一程**：往返回来必须是一个真的列得出四本书的书库，不是「导航发生过」 |
| S2 | `library.html` 的 `lib-sidebar-scope-pdf` 去掉 `disabled` | `AssertionError: format:pdf 是尚未支持的格式，侧栏按钮必须是 disabled` ／ `Actual value: enabled` ／ `resolved to <button … data-scope="format:pdf" … data-testid="lib-sidebar-scope-pdf">` | X-2b 边界的**前一半**：`disabled` 这个状态本身被断住了 |
| S2b | 同上，但换成 `disabled` → `aria-disabled="true"` | `AssertionError: format:pdf …必须是 disabled` ／ `Actual value: enabled` ／ `resolved to <button … aria-disabled="true" …>` | **一条被证伪的猜测，留档**：原以为 Playwright 的 `to_be_disabled()` 会认 `aria-disabled`，于是这一改能让前一半假绿。实测**不认**——该按钮显式写了 `role="listitem"`，`aria-disabled` 只对少数原生可禁用角色生效。所以「用 aria 冒充 disabled」这条假绿路径在本页上根本不存在，S2c 才是让后一半独立发言的那次 |
| S2c | 生产：同 S2（去掉 `disabled`）；**用例**：临时删掉 `to_be_disabled()` 那一行，好让后一半独立发言 | `AssertionError: 强行点过 format:pdf 之后（范围应仍是 format:epub）：cjk_data 应可见（期望可见集合 ['cjk_data', 'repeat_data', 'second_data', 'smoke_data']）` ／ `Actual value: hidden` | X-2b 边界的**后一半**：`click(force=True)` 之后范围**没有**变成 `format:pdf`。这一半不是前一半的复述——它断的是「点不动」，前一半断的是「标着不可点」 |
| S3 | `library.js` 的 `matchesScope` 里 `return fmt === state.scope.slice("format:".length);` → `return false;` | `AssertionError: 范围 format:epub：cjk_data 应可见（期望可见集合 ['cjk_data', 'repeat_data', 'second_data', 'smoke_data']）` ／ `Actual value: hidden` | X-2b 等价类 2：`format:epub` 下断的是与**字面量常量**的集合等值，不是「和上一屏一样」 |
| S4 | `library.js` 的 add-to-collection picker 回调里 `const add = Array.from(state.selectedBookIds);` → `const add = [];`（即矩阵自检点名的那个坏实现：**建了集合但没把书加进去**） | `AssertionError: 加书之后 library_collections.json 里该集合的 book_ids 应当恰好是 ['smoke_data']，实际 []` ／ `assert [] == ['smoke_data']` ／ `Right contains one more item: 'smoke_data'` | X-2c 的**持久化侧**：磁盘上真的写进了那一本 |
| S4b | 生产：同 S4；**用例**：临时删掉上面那条持久化断言，好让 DOM 侧独立发言 | `AssertionError: 切到新集合的范围下：smoke_data 应可见（期望可见集合 ['smoke_data']）` ／ `Actual value: hidden` | X-2c 的 **DOM 侧**：切到该集合后列表里**有**那一本。一条只断「侧栏出现了集合名」的用例在 S4 下会全绿——本行是它不会的证据 |
| S5 | `library.js` 的 `syncSelectionForBookId` 回退成审计之前的裸选择器：``qsa(`.book-card[data-book-id="${escaped}"], .book-row[data-book-id="${escaped}"]`)`` → ``qsa(`[data-book-id="${escaped}"]`)`` | `AssertionError: 状态 pill 不是选择的对象，不该被标成 is-selected` ／ `Expected value: 're.compile('(^\|\\s)is-selected(\\s\|$)')'` ／ `Actual value: status-pill is-not-indexed is-selected` ／ `14 × locator resolved to <span data-status="loading" data-book-id="smoke_data" class="status-pill is-not-indexed is-selected" data-testid="lib-book-grid-status-not-indexed">Not indexed</span>` | X-2d 判据 5：**这正是审计发现 #60 点名的那次回归**。判据 2（卡片与行确实被标上了）在这次破坏下**全绿**——所以排他那一半不是它的复述 |
| S5b | 生产：同 S5；**用例**：临时摘掉判据 5 那两条 `not_to_have_class`，好让闭集断言独立发言 | `AssertionError: 选中态只应落在书卡与列表行上，实测挂着 is-selected 的是 ['lib-book-card', 'lib-book-grid-status-not-indexed', 'lib-book-row', 'lib-book-row-status-not-indexed']。多出状态 pill ⇒ syncSelectionForBookId 的选择器没有限定到 .book-card / .book-row` ／ `At index 1 diff: 'lib-book-grid-status-not-indexed' != 'lib-book-row'` | X-2d 判据 3（闭集）：它**独立于**判据 5 也能抓到同一次回归，且失败消息把两个越界节点的 testid 直接列了出来 |
| S5c | `library.js` 的 `el.classList.toggle("is-selected", selected);` → `el.classList.add("is-selected");`（「加得上、去不掉」） | `AssertionError: 取消勾选后 .book-card 应摘掉 is-selected` ／ `Actual value: book-card is-selected` ／ `14 × locator resolved to <article … data-testid="lib-book-card" class="book-card is-selected" …>` | X-2d 判据 4：往返的**反向**那一半不是搭头。判据 1／2／3／5 在这次破坏下全绿（选中那一刻的作用域完全正确），只有取消那一程红 |

S2c、S4b 与 S5b 各自额外动了**用例自己**的一行（删掉／摘掉排在前面的那条断言），因为那几条
判据被前一条短路了，不删就永远轮不到它说话。三次都在同一轮内按备份逐字节还原，`diff` 无输出。

**S5 / S5b / S5c 的破坏手法与前面六次不同，这是硬性约束不是偏好**：009 分支的核心不变式是
`git diff --quiet -- src/` 必须通过，所以这三次**一个字节都没有碰 `src/`**。做法是
`page.route("**/static/library.js", …)`：从磁盘读出真实的 `library.js`、在内存里做字符串
替换、`route.fulfill()` 把改过的内容当作响应体喂给浏览器。锚点串先 `assert ... in source`
——锚点对不上时这次运行当场判废，而不是「替换了个寂寞然后报绿」。承载破坏的是一个临时
模块 `test_zz_tmp_sabotage_60.py`（`import` 本模块的 X-2d 函数、装好 route 再直接调它，
**被测断言逐字是同一份**），跑完即删；因此它没有进入任何条数常量。

-------------------------------------------------------------------------------
Wave 4 留在原地、Wave 5 已上收进 `helpers.py` 的东西（欠账 #25）
-------------------------------------------------------------------------------
`assert_visible_book_ids`、`read_collections` / `collections_file`、`http_json` /
`delete_collections_with_prefix` 都是**书库页**的通用件，不是本模块特有的构造。Wave 4 没有任何
WI 被授权改 `tests/e2e/helpers.py`（§0.6 纪律 2），所以当时照欠账 #13 的先例留在模块内；
Wave 5 的 WI-10 一次上收，断言文本原样，只改了名字与住址。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple
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

#: X-2d：语料四本都没建过向量索引，所以状态解析完之后两个 pill 都落在 `not_indexed` 上。
#: 写死这两个 testid 字面量（而不是从 `library.js` 反推）是刻意的——它们正是本分支改动
#: 的那一半，用被测源头生成期望值等于什么都没断。同一对字面量也被
#: `tests/e2e/test_testid_dom_uniqueness.py` 的 `DYNAMIC_SENTINELS` 钉着，两处相互印证。
GRID_STATUS_TESTID = "lib-book-grid-status-not-indexed"
ROW_STATUS_TESTID = "lib-book-row-status-not-indexed"

#: X-2d 的**反空转绊线**：一本书在书库页上贡献的、带 `data-book-id` 判别位的全部节点。
#: 这条期望值是「排他断言还有主体可断」的证据——两个 pill 若哪天不再带 `data-book-id`
#: （即本分支改动的那一半被回退），红的是这条绊线，而不是让排他断言悄悄变成空转。
#: 值按 `data-testid` 排序，`sorted()` 的口径。
BOOK_ID_BEARING_TESTIDS = [
    "lib-book-card",
    GRID_STATUS_TESTID,
    "lib-book-row",
    ROW_STATUS_TESTID,
]

#: 选中态那个 class。断 class 用**词边界正则**而不是 `to_have_class("is-selected")`：
#: 后者要求 class 属性**逐字**等于给定字符串，而 `.book-card` 上还有别的 class，
#: 一个「顺带多加了一个 class」的实现会让它红在与本条无关的地方。
SELECTED_CLASS_RE = re.compile(r"(^|\s)is-selected(\s|$)")

#: 取「带 `data-book-id=bookId` 的每个节点，及它此刻是否挂着 `is-selected`」。
#:
#: 为什么走 `page.evaluate` 而不是四个 `expect(...).not_to_have_class(...)`：点名式断言
#: 只能覆盖**今天存在**的那四个节点，而本条要断的是**作用域**——「除了卡片与列表行，
#: 没有别的节点被标成选中」。闭集形态把将来新增的、同样带 `data-book-id` 的节点自动纳入。
#: 失败消息里直接列出越界节点的 testid，不用再去 DOM 里翻。
#:
#: 时序上不需要重试：`check()` 返回时 change 回调已同步跑完，且下面每次调用它之前都先有
#: 一条会重试的 `expect(...)` 把 DOM 等到位了。
_BOOK_ID_NODES_JS = (
    "(bookId) => Array.from(document.querySelectorAll('[data-book-id]'))"  # lint-e2e-selectors: allow —— 本条断的就是「谁带着 data-book-id」这个全集，按 testid 收窄就把待证的越界节点排除在样本外了；这是 JS 侧的一次全集扫描，不是 Playwright 定位
    ".filter((el) => el.getAttribute('data-book-id') === bookId)"  # lint-e2e-selectors: allow —— 这是**读属性值**，不是选择器；lint 的 `getAttribute` 规则本为 Playwright 的 `locator.get_attribute()` 而设，在这条 JS 片段里是误报
    ".map((el) => ["
    "  el.getAttribute('data-testid') || ('<' + el.tagName.toLowerCase() + '>'),"  # lint-e2e-selectors: allow —— 同上，读属性值；这一行正是把越界节点的 testid 取出来印进失败消息的地方
    "  el.classList.contains('is-selected'),"
    "])"
)


def _book_id_nodes(page: Page, book_id: str) -> Dict[str, bool]:
    """`{data-testid: 是否挂着 is-selected}`，覆盖该书在页面上的**全部**判别位节点。"""
    pairs: List[Tuple[str, bool]] = page.evaluate(_BOOK_ID_NODES_JS, book_id)
    nodes = {str(testid): bool(selected) for testid, selected in pairs}
    assert len(nodes) == len(pairs), (
        f"同一个 data-testid 在 {book_id} 上出现了多次：{pairs!r}。"
        "本 helper 按 testid 建字典，重名会静默吞掉一个节点，排他断言随之变弱。"
    )
    return nodes


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


# ---------------------------------------------------------------------------
# X-2d 选择态只落在书卡与列表行上，不落在状态 pill 上（审计发现 #60）
# ---------------------------------------------------------------------------


def test_x2d_selection_marks_only_book_cards_and_rows_not_status_pills(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """X-2d（S4，L2，**往返 ＋ 排他**）：勾选一本书 → `is-selected` 恰好落在它的卡片与列表行上；取消 → 全部退回。

    来源不是矩阵，是本分支的审计发现 #60；为什么它必须存在、为什么写成闭集而不是点名，
    见模块 docstring 的「X-2d 为什么存在」一节。

    **Law（选择态的作用域）**：对任一 `bookId`，
    `{挂着 is-selected 的节点} ∩ {带 data-book-id=bookId 的节点}` 在选中后恒等于
    `{.book-card, .book-row}`，在取消后恒等于 `∅`。这条律是一个**等式**，不是「卡片被标上
    了」这种单向包含——单向包含正是那条被审计抓住的裸选择器能满足的形状。

    五项判据，每一项都有具体的坏实现能让其余四项全绿：

      1. **反空转绊线**：该书的判别位节点集合 == `BOOK_ID_BEARING_TESTIDS`（卡片、列表行、
         两个状态 pill，共四个）。这一项排在所有断言之前，因为后面每一条排他断言的**主体**
         都由它提供：`setStatusForBook` 若不再给 pill 挂 `data-book-id`，判据 3 会退化成
         「对两个不存在的节点断了它们不选中」——永远绿，且绿得毫无意义。红在这一项上时，
         报的是「pill 不带判别位了」，而不是一句含糊的通过。
      2. **正向**：勾选后 `.book-card` 与 `.book-row` 各自挂上 `is-selected`，且**两边的
         复选框都是 checked**。只断卡片的话，一个「只同步当前视图」的实现全绿——而
         `syncSelectionForBookId` 恰好是同时喂两个视图的那个函数。
      3. **排他（本条的靶心）**：选中态的节点集合**恰好**是 `{lib-book-card, lib-book-row}`。
         这是唯一一条会被审计点名的那次回归打红的判据——裸的
         `qsa('[data-book-id="…"]')` 会让两个状态 pill 一起挂上 `is-selected`，集合变成四个。
         判据 2 在那次回归下**照样全绿**（卡片和行确实被标上了），所以这一项不是它的复述。
      4. **反向（往返的另一半）**：取消勾选后选中态集合回到 `∅`，两个复选框都回到 unchecked，
         而绊线（判据 1）里的四个节点一个不少。一个「加得上、去不掉」的实现（例如
         `classList.toggle(cls, selected)` 写成 `classList.add(cls)`）只在这一项上红。
      5. **两个 pill 逐个断 `not_to_have_class`**。这一条与判据 3 有重叠，保留是因为它给的是
         Playwright 自带重试的那种断言：`_book_id_nodes` 是一次性快照，若将来 `is-selected`
         的挂载变成异步（比如挪进 `requestAnimationFrame`），快照会读到一个还没写上的中间
         态并**假绿**；`expect(...).not_to_have_class` 在那种实现下会在整个超时窗口里持续
         校验，从而把假绿变成红。两条一起才既有闭集又有时序韧性。

    **为什么先等状态 pill 落定再进选择模式。** 页面初渲染时 pill 是
    `class="status-pill is-loading"`，既没有 testid 也没有 `data-book-id`（`setStatusForBook`
    在状态 XHR 回来之后才两者一起挂上，见 `library.js` 顶部注释「判别位跟着 testid 一起走」）。
    不等的话，判据 1 会在一个只有两个节点的快照上红，报的是竞态而不是行为。

    **列表行的复选框用 class 定位，卡片的用 ARIA role**，这处不对称是有原因的：
    `.book-row` 住在 `#library-list-view` 里，而那个 `<section>` 在网格视图下带 `hidden`
    属性，整棵子树因此不在可访问性树上——`get_by_role("checkbox")` 在它上面解析出 0 个节点。
    行内那个 `<input>` 又没有自己的 testid（它是本条要断的**属性语义**的载体，不是定位锚点），
    所以只剩 class 一条路，按选择器政策的转义口径显式放行并写明理由。卡片那边可访问性树
    完好，就仍走 ARIA——不因为一处必须转义而把另一处也降级。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    page.goto(f"{live_server}{LIBRARY_PATH}")
    assert_visible_book_ids(page, ALL_BOOK_IDS, where="X-2d 起点的书库")

    card = page.locator(f'[data-testid="lib-book-card"][data-book-id="{SMOKE_BOOK_ID}"]')
    row = page.locator(f'[data-testid="lib-book-row"][data-book-id="{SMOKE_BOOK_ID}"]')
    grid_pill = page.locator(
        f'[data-testid="{GRID_STATUS_TESTID}"][data-book-id="{SMOKE_BOOK_ID}"]'
    )
    row_pill = page.locator(
        f'[data-testid="{ROW_STATUS_TESTID}"][data-book-id="{SMOKE_BOOK_ID}"]'
    )

    # ---- 判据 1：反空转绊线（必须排在最前，它给后面的排他断言提供主体）----------
    # 先把两个 pill 等到位：状态 XHR 回来之前它们既无 testid 也无 data-book-id。
    expect(grid_pill, "网格视图的状态 pill 应带 testid ＋ data-book-id 判别位").to_have_count(1)
    expect(row_pill, "列表视图的状态 pill 应带 testid ＋ data-book-id 判别位").to_have_count(1)

    before = _book_id_nodes(page, SMOKE_BOOK_ID)
    assert sorted(before) == BOOK_ID_BEARING_TESTIDS, (
        f"带 data-book-id={SMOKE_BOOK_ID!r} 的节点实测是 {sorted(before)!r}，"
        f"期望 {BOOK_ID_BEARING_TESTIDS!r}。少了状态 pill 就意味着下面的排他断言没有主体可断"
        "（会退化成对不存在的节点断言，永远绿）。"
    )
    assert not any(before.values()), (
        f"进选择模式之前不该有任何节点挂着 is-selected，实测 {before!r}"
    )

    # ---- 进选择模式并勾选 -------------------------------------------------
    page.get_by_test_id("lib-toolbar-select-mode").click()
    expect(page.get_by_test_id("lib-bulk-bar")).to_be_visible()

    card_checkbox = card.get_by_role("checkbox")
    # `.book-row` 在网格视图下住在一个 hidden 的 <section> 里、不在可访问性树上，
    # ARIA 定位解析不到；行内复选框自身也没有 testid。理由详见本函数 docstring 末段。
    row_checkbox = row.locator(".select-checkbox")  # lint-e2e-selectors: allow —— 见 docstring：hidden 子树上 get_by_role 解析为 0，且该 <input> 无 testid
    card_checkbox.check()

    # ---- 判据 2：正向 ------------------------------------------------------
    expect(card, "勾选后 .book-card 应挂上 is-selected").to_have_class(SELECTED_CLASS_RE)
    expect(row, "勾选后 .book-row 应挂上 is-selected（两个视图同时在 DOM 里）").to_have_class(
        SELECTED_CLASS_RE
    )
    expect(card_checkbox, "勾选后网格视图的复选框应为 checked").to_be_checked()
    expect(row_checkbox, "勾选后列表视图的复选框应被同步成 checked").to_be_checked()

    # ---- 判据 5：两个 pill 逐个断（带重试，补闭集快照的时序盲区）--------------
    expect(grid_pill, "状态 pill 不是选择的对象，不该被标成 is-selected").not_to_have_class(
        SELECTED_CLASS_RE
    )
    expect(row_pill, "状态 pill 不是选择的对象，不该被标成 is-selected").not_to_have_class(
        SELECTED_CLASS_RE
    )

    # ---- 判据 3：排他（靶心）----------------------------------------------
    selected_nodes = _book_id_nodes(page, SMOKE_BOOK_ID)
    assert sorted(selected_nodes) == BOOK_ID_BEARING_TESTIDS, (
        f"勾选之后判别位节点集合变了：实测 {sorted(selected_nodes)!r}，期望 "
        f"{BOOK_ID_BEARING_TESTIDS!r}"
    )
    assert sorted(k for k, v in selected_nodes.items() if v) == ["lib-book-card", "lib-book-row"], (
        "选中态只应落在书卡与列表行上，实测挂着 is-selected 的是 "
        f"{sorted(k for k, v in selected_nodes.items() if v)!r}。"
        "多出状态 pill ⇒ syncSelectionForBookId 的选择器没有限定到 .book-card / .book-row。"
    )

    # ---- 判据 4：反向（往返的另一半）--------------------------------------
    card_checkbox.uncheck()

    expect(card, "取消勾选后 .book-card 应摘掉 is-selected").not_to_have_class(SELECTED_CLASS_RE)
    expect(row, "取消勾选后 .book-row 应摘掉 is-selected").not_to_have_class(SELECTED_CLASS_RE)
    expect(card_checkbox, "取消勾选后网格视图的复选框应为 unchecked").not_to_be_checked()
    expect(row_checkbox, "取消勾选后列表视图的复选框应被同步成 unchecked").not_to_be_checked()

    after = _book_id_nodes(page, SMOKE_BOOK_ID)
    assert sorted(after) == BOOK_ID_BEARING_TESTIDS, (
        f"取消勾选之后判别位节点集合变了：实测 {sorted(after)!r}，期望 {BOOK_ID_BEARING_TESTIDS!r}"
    )
    assert sorted(k for k, v in after.items() if v) == [], (
        f"取消勾选后不该有任何节点还挂着 is-selected，实测 {sorted(k for k, v in after.items() if v)!r}"
    )
