"""WI-11 —— K-1a：契约 K1 那七个宿主元素的**前置条件正向证据**。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-11（最高权威，条数与断言层级
以它为准：两条用例，L2）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0.5「`baseline-1b`
对 K1 / K6 / W-5 的现状特征化」表的 K1 行、§4 的 K-1a 行。契约 K1 的唯一定义处：
`docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md`。
七个宿主之所以**全都**能用 testid 定位（`anno-color-row` 与 `note-tooltip` 原本没有），
是 `docs/adr/0014-bounded-testid-enumeration.md` 落地的结果。

**这两条测的不是同一件事，缺任何一条另一条都不成立。**

  * 第一条断「七个宿主元素在 DOM 上」——`AnnotationUI` 构造函数里那七次 `getElementById`
    的取值前提。它**单独**看确实贴着 L2 的下限（「模板里有七个字符串」），所以矩阵把它和
    下一条钉成一对。
  * 第二条断「`init()` 真的跑完了」——七个都在、但 `init()` 因别的原因在第一行 return
    时（`contentEl` 拿不到就是一例），第一条绿、第二条红。这就是把「前置条件成立」和
    「真的初始化了」分开的全部价值。

**为什么 1b 阶段断的是「在场」而不是「缺失时响亮失败」。** 任务书 §0.5 的分工：今天的
行为写进 `baseline_1b`，期望的行为以 skip 形态挂在 `acceptance_4b1`。K1 契约的价值是
「把静默变响亮」，而那个响亮 **4B.1 才实现**——`init()` 第一行今天是
`if (!this.contentEl || !this.toolbar) return;`，一声不吭。1b 阶段就断它，等于把一条要等
生产代码改完才可能绿的用例混进 1b 的退出门槛，和 R13 修掉的那个依赖环是同一个形状。
**响亮失败那一半是 K-1b**，由 WI-17（Wave 7）以 skip 形态落到 `tests/e2e/acceptance_4b1/`，
两条用例的分工写在任务书 §4 的 K-1a / K-1b 两行。

**它到底防什么。** 任务书 §0.5 原文：「任何人改模板删掉那七个 id 之一时它变红，而这正是
4B.2 外壳重写最可能干的事」。4B.2 要重写 `reader.html` 的整个外壳；那次重写里删掉一个
`id=` 或改一个 `data-testid=`，今天没有任何东西会响——`getElementById` 返回 `null`，
`init()` 静默 return，标注功能整体失灵而页面照常渲染。本模块就是那次重写的绊线。

**为什么第一条不用 `@pytest.mark.parametrize`。** 参数化会把它收成 7 个 item，而矩阵
§WI-11 明写「七条断言，**一个用例**」，条数表也据此把 WI-11 记为 2 个 item——
`baseline_1b` 的期望条数只在 `scripts/lint_e2e_groups.py` 的 `EXPECTED_BASELINE_ITEMS`
定义一次（Wave 6 收口后的实测值，变更史写在那个文件头；这里**不复述数字**，抄一份就是
第二个定义处，而两份必然漂移）。参数化本要换的是
「失败消息一眼看出少了哪个」，这里改用**一次收齐全部异常再报**拿到同样的东西，且比参数化
更强：七个一起丢时参数化报七条红，本条一次把七个都列出来。

**为什么七元组是写死的字面量，不从模板 grep。** 任务书 §0 第五条纪律：守恒断言的基准
必须是字面量。从 `reader.html` 派生期望值等于拿运行期读到的值比运行期读到的值——模板一改
断言永远绿，而「模板被改了」恰恰是本模块唯一要抓的事。`_HOST_COUNT = 7` 同理：只有一个
写死的下界，才拦得住「顺手从元组里删一行」这种把断言悄悄削成六条的改法。

**与 `tests/e2e/test_testid_dom_uniqueness.py` 的分工。**
`test_reader_bounded_testids_each_resolve_to_exactly_one_node` 断的是阅读页上有界 testid 的
**唯一性**，本模块断的是这七个的**在场**。两者不重复：唯一性判据对「一个都没有」是盲的
——`count() == 0` 不构成「重复」，一个被删掉的 testid 在那条用例里连一组都进不去。该模块
是分组白名单里（`UNGROUPED_E2E_MODULES`）唯一与本 WI 相邻的东西，所以在这里点名，免得
后来者以为两边可以合并。

------------------------------------------------------------------------------
定向破坏实录（2026-09-03，五处，全部已还原）
------------------------------------------------------------------------------
特征化用例没有红相位（任务书 §0 第四条纪律）：被测行为早已上线数月，红不可得。替代
证据是**定向破坏本文件里的期望值**——**不碰生产代码**，逐条打靶。下面每一格的失败输出
都是从 `uv run pytest … --browser chromium` 的 `E ` 行**逐字抄下来**的，不是预测。

| # | 破坏点（全在本文件内） | 逐字失败输出（判据行） | 它证明了什么 |
|---|---|---|---|
| D1 | `_HOSTS` 第 4 行的 testid `"rd-note-editor-input"` → `"rd-note-editor-textarea"` | `AssertionError: 契约 K1 的宿主元素在 /read/smoke_data/0 上不是恰好一个：` ／ `    - rd-note-editor-textarea（annotations.js 取 getElementById('note-editor-text') → this.noteTextarea）：count() == 0，元素不在 DOM 上` | 七元表逐个咬住各自那一个 testid，且失败消息一眼指出**是哪个宿主没了**、它在 `annotations.js` 里对应哪次取值——这正是 4B.2 删掉一个 id 时读者需要的信息 |
| D2 | 从 `_HOSTS` 删掉 `rd-note-tooltip` 那一行，`_HOST_COUNT` 保持 `7` | `AssertionError: 契约 K1 的宿主是七个，本表只有 6 个 —— 有人从 _HOSTS 里删了行？七个的唯一定义处是 annotation-host-contracts.md 的 K1` ／ `assert 6 == 7` | 「顺手从表里删一行」这条**静默削弱**的路径被堵死。附带实测：同时把 `_HOST_COUNT` 也改成 `6` 时它**转绿**——所以这道闸拦的不是「改不动」，是「改它必须是两处显式动作」，而两处一起改的人骗不了自己 |
| D3 | 行为证据里选区**之前**的 `to_be_hidden()` → `to_be_visible()` | `AssertionError: Locator expected to be visible` ／ `Actual value: hidden` ／ `- waiting for get_by_test_id("rd-anno-toolbar")` ／ `  14 × locator resolved to <div role="toolbar" aria-hidden="true" id="annotation-toolbar" data-testid="rd-anno-toolbar">…</div>` | 工具条初始态**确实是隐藏的**（且解析到的正是那个 `id=annotation-toolbar` 的宿主），所以选区之后那次 `to_be_visible()` 断的是一次真实的**状态迁移**，不是「这个元素存在」的同义反复 |
| D4 | 行为证据里选区**之后**的 `to_be_visible()` → `to_be_hidden()` | `AssertionError: Locator expected to be hidden` ／ `Actual value: visible` ／ `  14 × locator resolved to <div role="toolbar" aria-hidden="true" class="is-visible" id="annotation-toolbar" data-testid="rd-anno-toolbar">…</div>` | 选区之后工具条**真的**可见了（`class="is-visible"` 被挂上），即 `init()` 没有在第一行 return——它把 `selectionchange` / `mouseup` 的监听装上了。这一条才是「测 init」与「测元素存在」的分界 |
| D5 | 点击的按钮 `rd-anno-type-marker` → `rd-anno-type-wavy`，期望值仍留 `marker` | `AssertionError: 落库的 type 是 'wavy'，不是按下的那个按钮对应的 'marker'：`handleAction` 的 action 名与模板 `data-action` 取值失配？完整条目：{'id': 'eec0d14e-…', 'chapter_index': 0, 'type': 'wavy', 'color': 'yellow', 'quote': 'Alpha prose', …, 'cfi': None, …}` | 工具条那圈按钮的事件委托是**逐按钮**生效的，不是「随便点一下都会写一条」；`type` 判据在区分等价类，不是恒真 |

D3 与 D4 是一对：只做 D4 的话，一份「工具条从来就可见」的实现也能让它绿；加上 D3，两侧
各钉一端，中间那次迁移才被夹住。

**D6（2026-09-05 追加，这一枪打的是判据本身而不是期望值）**：经 `page.route` 把
`/read/smoke_data/0` 的响应体里 `id="note-editor-text" data-testid="rd-note-editor-input"`
改写成只剩 `data-testid=...`（`src/` 未动，改写命中数核对为 1）。实测——

* 页内 `document.getElementById('note-editor-text')` 返回 **`None`**，即 `AnnotationUI` 的
  `this.noteTextarea` 拿到 null，笔记编辑器整条取值链断掉；
* **旧判据（只按 testid 定位）七个 testid 仍各 `count() == 1`，全绿**；
* 新判据逐字失败输出：`AssertionError: 契约 K1 的宿主元素在 /read/smoke_data/0 上不满足
  「testid 与 id 各恰好一个且同属一个节点」：` ／ `  - [id] #note-editor-text（annotations.js
  取 getElementById('note-editor-text') → this.noteTextarea）：count() == 0，getElementById
  会返回 null`。

这一枪坐实了模块 docstring 开头那句自述（「任何人改模板删掉那七个 id 之一时它变红」）在
旧写法下**并不成立**：4B.2 的外壳重写只要保留 testid、丢掉 id，本模块原样全绿。

D5 的失败输出里 `'cfi': None` 顺带复现了任务书 §0.6 跨波欠账第 6 行记录的生产缺陷——
`epub-renderer.js` 存进 `currentContents` 的是 epub.js 的 view 而不是 `Contents`，
`cfiFromRange` 不存在，于是 `annotations.js` 里那道守卫永假、锚定 100% 走纯文本。
**本 WI 只记录，不修**：1b 是迁移前的安全网，不是行为变更窗口。

------------------------------------------------------------------------------
本模块**没有**新增任何本该上收到 `helpers.py` 的辅助函数
------------------------------------------------------------------------------
两条用例全部由 `helpers.py` 的 `open_reader` / `select_in_frame` / `read_notes` /
`assert_roundtrip` 拼出来，一个私有 helper 都没写。`_HOSTS` 与 `_HOST_COUNT` 是本 WI 的
**判据本身**（契约 K1 的七元集），不是可复用的动作——把它搬进 `helpers.py` 只会让「谁在断
这七个」失去唯一的落点。任务书 §0.6 的共享文件授权制：本波没有任何 WI 被授权改
`helpers.py` / `conftest.py` / `scripts/lint_e2e_groups.py`，本模块一行未动。
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    assert_roundtrip,
    open_reader,
    read_notes,
    select_in_frame,
)

pytestmark = pytest.mark.baseline_1b


#: 契约 K1 的七个宿主，`(testid, annotations.js 里的 getElementById 实参, 赋给哪个字段)`。
#:
#: 三列都是**字面量**，一个都不从模板或 JS 里派生（任务书 §0 第五条纪律）。前两列**都参与
#: 定位**（见用例里的三重判据），第三列只进失败消息：一条「rd-note-editor-input 不在 DOM 上」
#: 对读者的价值，远不如「rd-note-editor-input（`annotations.js` 取
#: `getElementById("note-editor-text")` → `this.noteTextarea`）不在 DOM 上」——后者直接告诉他
#: 改模板会打断哪一条取值链。
#:
#: testid 名字取自 ADR-0014（`anno-color-row` 与 `note-tooltip` 两个宿主的 testid 是那批
#: 补上的，`id=` 一个没动，因为生产端走的是 `getElementById`）；`id` 那一列取自契约 K1
#: 的七元枚举。两列同时改错才可能骗过这张表，而它们分处两份文档。
_HOSTS: Tuple[Tuple[str, str, str], ...] = (
    ("rd-anno-toolbar", "annotation-toolbar", "this.toolbar"),
    ("rd-anno-colors", "anno-color-row", "this.colorRow"),
    ("rd-note-editor", "note-editor", "this.noteEditor"),
    ("rd-note-editor-input", "note-editor-text", "this.noteTextarea"),
    ("rd-note-editor-primary", "note-editor-save", "this.noteSave"),
    ("rd-note-editor-cancel", "note-editor-cancel", "this.noteCancel"),
    ("rd-note-tooltip", "note-tooltip", "this.tooltip"),
)

#: 七，写死。`len(_HOSTS)` 会跟着表一起缩水，那样「从表里删一行」就成了一次静默削弱。
#: 契约 K1 的七元枚举是闭合的，改它要先改 `annotation-host-contracts.md`。
_HOST_COUNT = 7


def test_k1a_seven_annotation_host_elements_are_present(
    page: Page, live_server: str
) -> None:
    """K-1a（S2，七元素集合的完备枚举 / L2 DOM 存在性）：七个宿主逐个 `count() == 1`。

    **本条只锁前置条件。** 元素缺失时的**响亮失败**（`console.error` ＋ 降级标记置位）属
    `acceptance_4b1` 的 **K-1b**，由 WI-17 以 skip 形态落到 `tests/e2e/acceptance_4b1/`；
    两条的分工见任务书 §4 的 K-1a / K-1b 两行与 §0.5 的现状特征化表。今天的 `init()` 第一行
    是静默 return，所以 1b 阶段能断的只有「前置条件成立」这一半——反过来断会造出一条要等
    4B.1 改完生产代码才可能绿的门槛用例。

    **不要求可见，只要求附着在 DOM 上。** 工具条初始 `aria-hidden="true"` 且 CSS 是
    `display: none`（`.is-visible` 才 `display: flex`），笔记编辑器与 tooltip 同理。断
    `to_be_visible()` 在这里是**错的判据**，不是更严的判据：它会把「初始就该藏着」这个正确
    行为报成红。

    **为什么是 `== 1` 而不是 `>= 1`。** `getByTestId()` 在 strict 模式下命中多个直接抛，
    所以「重复」和「缺失」一样是坏的。判据取等号，两个方向都咬住。渲染后 DOM 的**唯一性**
    另有专门的护栏（`tests/e2e/test_testid_dom_uniqueness.py::test_reader_bounded_testids_each_resolve_to_exactly_one_node`）
    ——那一条对 `count() == 0` 是盲的（零个不构成重复），本条正好补上它看不见的那一侧。

    **为什么每个宿主要断三次（testid ／ id ／ 两者同一节点）。** 本条的契约原文是「`annotations.js`
    构造函数里那七次 `getElementById` 拿得到东西」，而 `getElementById` 认的是 **`id`**，不是
    `data-testid`。只按 testid 定位时，一次「把 `id="note-editor-text"` 删掉、`data-testid` 原样
    留着」的模板改动**不会红**——七个 testid 照旧各命中一个节点，而七次 `getElementById` 全部
    返回 `null`，`init()` 第一行静默 return。这正是本模块自称要拦的那件事（模块 docstring：
    「任何人改模板删掉那七个 id 之一时它变红」），却恰好是旧写法的盲区（定向破坏 D6 实测：
    旧写法对着一个被剥掉 id 的模板**全绿**）。三次分别是：

      1. `data-testid` 恰好命中一个节点——用例侧的定位口径（ADR-0014）；
      2. `#id` 恰好命中一个节点——生产侧 `getElementById` 的取值口径；
      3. 带该 testid 的那个节点，`id` 属性**逐字**等于 `_HOSTS` 记的 `dom_id`——否则两个口径
         各自成立却落在**两个不同的节点**上（把 testid 挪到别的元素、或另起一个同 id 的空 div），
         而那时生产拿到的仍不是浮层本身。

    自检：这条**单独**确实接近存在性断言，不孤立成立。下一条
    `test_k1a_selection_opens_toolbar_proving_init_ran` 是它的行为证据，两条必须同在；
    缺了行为证据，本条只证明了「模板里有七个字符串」。
    """
    assert len(_HOSTS) == _HOST_COUNT, (
        f"契约 K1 的宿主是七个，本表只有 {len(_HOSTS)} 个 —— 有人从 _HOSTS 里删了行？"
        "七个的唯一定义处是 annotation-host-contracts.md 的 K1"
    )

    open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    # 一次收齐全部异常再报，而不是遇到第一个就 assert：4B.2 的外壳重写很可能一次删掉
    # 好几个宿主，逐个 assert 只会让人修一个再红一次，来回七轮。
    anomalies = []
    for testid, dom_id, field in _HOSTS:
        chain = f"annotations.js 取 getElementById({dom_id!r}) → {field}"
        by_testid = page.get_by_test_id(testid)
        # lint-e2e-selectors: allow —— 本条的契约原文是「生产那七次 getElementById 拿得到东西」，
        # id 是**被断言的对象本身**，不是定位手段；ADR-0014 管的是「用什么定位元素」。
        # 换成 data-testid 定位正是本条 2026-09-05 审计要修的那个洞（定向破坏 D6）。
        by_id = page.locator(f"#{dom_id}")  # lint-e2e-selectors: allow
        n_testid, n_id = by_testid.count(), by_id.count()

        if n_testid != 1:
            why = "元素不在 DOM 上" if n_testid == 0 else "同一个 testid 命中多个节点，strict 模式必抛"
            anomalies.append(f"  - [testid] {testid}（{chain}）：count() == {n_testid}，{why}")
        if n_id != 1:
            why = (
                "getElementById 会返回 null"
                if n_id == 0
                else "同一个 id 出现在多个节点上，getElementById 只取文档序第一个"
            )
            anomalies.append(f"  - [id] #{dom_id}（{chain}）：count() == {n_id}，{why}")
        if n_testid == 1 and n_id == 1:
            actual_id = by_testid.get_attribute("id")  # lint-e2e-selectors: allow
            if actual_id != dom_id:
                anomalies.append(
                    f"  - [错位] {testid}（{chain}）：带该 testid 的节点 id 是 {actual_id!r}，"
                    f"不是 {dom_id!r} —— testid 与 id 落在了两个不同的节点上，"
                    "用例定位到的和生产取到的不是同一个元素"
                )

    assert not anomalies, (
        f"契约 K1 的宿主元素在 /read/{BOOK_ID}/0 上不满足「testid 与 id 各恰好一个且同属一个节点」：\n"
        + "\n".join(anomalies)
        + "\n缺一个就会让 AnnotationUI 的构造函数拿到 null；若缺的是 annotation-toolbar，"
        "`init()` 第一行直接静默 return，标注功能整体失灵而页面照常渲染。"
        "\n注意 `getElementById` 认的是 id 而不是 data-testid：只删 id、留着 testid 的改法"
        "对纯 testid 判据是隐形的，这就是本条同时按两种口径定位的理由。"
    )


def test_k1a_selection_opens_toolbar_proving_init_ran(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-1a 的行为证据（S1 / L2）：选区唤出工具条，且工具条上的动作委托真的生效。

    **它补上上一条证明不了的那一半。** 七个元素都在，`init()` 仍可能在第一行
    `if (!this.contentEl || !this.toolbar) return;` 掉头就走——`contentEl` 拿不到就是一例，
    而那个分支**一声不吭**。上一条对此完全盲：模板里那七个字符串照样在。本条走一遍真实
    的用户动作，工具条从隐藏变可见，只可能是因为 `init()` 把 `selectionchange` / `mouseup`
    的监听装上了。

    **为什么不去探 `window.Reader3AnnotationUI`。** 那是个**假证人**：入口处的写法是
    `ui.init(); window.Reader3AnnotationUI = ui;`——赋值在 `init()` 返回**之后**，无论
    `init()` 是跑完了还是在第一行 return，那个全局都一样存在。断它等于断「脚本被求值过」。

    **为什么选区之前先断一次隐藏。** 只断「选区之后可见」的话，一个「工具条从来就可见」
    的实现也能让它绿。两端各钉一次，中间那次**状态迁移**才被夹住。定向破坏 D3 / D4 就是
    分别打这两端的。

    **为什么还要点一下 marker 并断落库。** 矩阵 §WI-11 要求本条复用 K-2 的一个 action：
    「工具条可见」只证明监听装上了，证明不了工具条自己那圈按钮的**事件委托**装上了——
    `toolbarListenersBound` 那条路径与打开工具条的那条是分开的。收尾用共享的
    `assert_roundtrip`（任务书 §0 的往返纪律 ＋ 第四条纪律要求的终态复断），不在本模块里
    另写一份等待逻辑。

    **选区与标注都做在全新的一条选区上。** 任务书列在案的已知生产缺陷 #9（对**已存在**的
    wavy / underline 标注按另一个颜色时，`clearExistingAnnotationMarks()` 的
    `parent.normalize()` 会让 `currentRange` 塌缩，`DELETE 204 → POST 400 → 该选区一条不剩`）
    只在「已有标注上再动一次」时触发；本条从零起、只按一次 marker，踩不到它。本模块**不修**
    该缺陷（1b 是迁移前的安全网，不是行为变更窗口）。

    K-1b（4B.1）在这里的对偶：把 `annotation-toolbar` 移除后重载，断言明确的 `console.error`
    与降级标记置位。见 `tests/e2e/acceptance_4b1/`（WI-17 交付）与任务书 §4 的 K-1b 行。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    toolbar = page.get_by_test_id("rd-anno-toolbar")
    expect(toolbar).to_be_hidden()

    select_in_frame(frame, CH0_QUOTE)
    expect(toolbar).to_be_visible()

    page.get_by_test_id("rd-anno-type-marker").click()

    assert_roundtrip(
        page, e2e_books_dir, BOOK_ID, CH0_QUOTE, CH0_ANCHOR, expected_type="marker"
    )
