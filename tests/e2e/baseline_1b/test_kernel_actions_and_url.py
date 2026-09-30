"""WI-9 —— K-2 / K-6a：工具条 `data-action` 的取值域，与「URL 里的章号」的落库一致性。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-9（最高权威）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §4 K-2 行、§5 K-6a 行、
§0 六条写作纪律、§1「iframe 内建选区的标准路径」。契约原文：
`docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K2 / K6。

本模块守两条定律：

* **K2（取值域闭合）**——`button[data-action]` 的取值是一个**七元集**
  （`copy` / `marker` / `wavy` / `underline` / `delete` / `note` / `ask_ai`），
  每个取值到「可观察结果」的映射是**全函数**：七个按钮各按一次，七次都必须有东西真的
  发生。
* **K6（章号一致性）**——落库的 `chapter_index` **恒等于 URL 路径里的那个数**，且在
  `syncLocationToUrl()` 用 `history.replaceState` 改址之后仍然成立。

--------------------------------------------------------------------------------
为什么 K-2 的每一条判据都落在「标注真的产生 / 删除 / 改色」上，一条都不许写成
「按钮可见」或「按钮可点」
--------------------------------------------------------------------------------
契约 K2 点名的失效形态是：**按钮被重设计换成 `<div>`，或者 `data-action` 被改名** →
`annotations.js` 里那个 `e.target.closest("button[data-action]")` 匹配不到 →
`handleAction` 压根不被调用 → **点击什么也没发生，控制台干干净净**。
在这种形态下，「按钮存在」「按钮可见」「按钮可点」三条统统是绿的。所以那三条断言在
本模块里的价值恰好是零——它们**永远不会因为契约被破坏而变红**。判据必须落在按钮**之后**
的那一段链路上：盘上多了一条记录、少了一条记录、剪贴板里有了那段文字、`window` 上派发过
那个事件。K-1a（`rd-anno-*` 的存在性与唯一性）是 WI-11 的活，本模块不重复。

--------------------------------------------------------------------------------
为什么每个 action 都从**一次全新的选区**开始（每条用例各自 `page.goto`）
--------------------------------------------------------------------------------
已知缺陷 #9：在同一页上对同一段文字连续按两个类型键，`toggleAnnotation` 的异色分支会
`DELETE 204 → POST 400（quote is required）`，标注净归零。也就是说，「在一页上把七个键
挨个按一遍」测到的不是七个 action，而是缺陷 #9 的连锁反应。七条用例各自开页、各自建选区，
是把这七个取值**互相隔离**的唯一可靠办法——`clear_selection_and_drain` 只清选区，清不掉
`currentAnnotationMeta` 与页面上已经画出来的 `<mark>`。

--------------------------------------------------------------------------------
`copy` 没有降级：剪贴板是真读的
--------------------------------------------------------------------------------
任务书允许在 `navigator.clipboard` 授权不稳时降级到「工具条关闭」（L4），并要求写明弱在
哪里。**本模块没有用这条降级**：headless chromium 下 `grant_permissions(["clipboard-read",
"clipboard-write"], origin=live_server)` 在用例内授予即可（不动 conftest），
`navigator.clipboard.readText()` 稳定返回选中文本。判据因此是 L5 的「剪贴板内容 == 选中文本」，
而不是 L4 的「工具条关了」。保留一条附带的「工具条关了」断言，是因为它证明的是**另一件事**：
`copySelection()` 末尾的 `closeSelectionToolbarIfOpen()` 跑到了——剪贴板那条只能证明
`writeText` 跑到了，两条合起来才覆盖 `copySelection` 的整个函数体。

--------------------------------------------------------------------------------
为什么站内翻章走 TOC 行，而不是 `rd-page-next`
--------------------------------------------------------------------------------
任务书 §2 与矩阵 §B 都写死了：**`rd-page-prev` / `rd-page-next` 完全不可用**——
`.nav-zone-left/right` 的 CSS 是 `display: none`（注释写明 keyboard-only），且只有 legacy
`js/pagination.js` 绑定它们，而 `reader.html` **不加载那个文件**。Playwright 点
`display:none` 的元素只会在 actionability 上超时 30s，测不出任何东西。
（计划稿 `.claude/tdd-guardian/plan-20260901-122813.md` 的 WI-9 段落里还写着
`rd-page-next`，那一处已被矩阵推翻，见交付报告。）
站内翻章因此走 TOC 行：`[data-testid="rd-toc-row"][data-file-href="…"]` → `findAndGo()`
→ `Reader3Epub.displaySectionIndex()` → `syncLocationToUrl()` 的 `history.replaceState`。

--------------------------------------------------------------------------------
定向破坏证据（第四条纪律：特征化测试没有红阶段，用「破坏自己用例的期望值」代替）
--------------------------------------------------------------------------------
下表每一行都是**真跑出来的**，不是预测。破坏的一律是**本文件里的期望值**，一次只动一处，
从不改生产代码（第四条纪律明令禁止用改坏 `src/` 来伪造红）。每行三件事：破坏点、
**逐字**失败输出、恢复核验。七处全部恢复之后，本文件是 `git status` 里唯一的新增，
没有任何既有文件被本模块改动过（`helpers.py` / `conftest.py` / `lint_e2e_groups.py` 一行未动）。

| # | 破坏点 | 逐字失败输出（节选到判据那一行） | 恢复核验 |
|---|--------|--------------------------------|----------|
| 1 | `test_k2_type_actions_*` 的参数表里 `wavy` 那一行的期望 type 改成 `"marker"` | `AssertionError: 按下 rd-anno-type-wavy 之后落库的 type 是 'wavy'，不是期望的 'marker'。` + `assert 'wavy' == 'marker'` | 改回 `"wavy"` 后该参数化项恢复 pass |
| 2 | `copy` 用例的剪贴板期望改成 `CH0_QUOTE + "X"` | `AssertionError: 剪贴板里是 'Alpha prose'，不是选中的 'Alpha proseX'。` + `assert 'Alpha prose' == 'Alpha proseX'` | 改回 `CH0_QUOTE` 后恢复 pass |
| 3 | `note` 用例把 `aria-hidden` 的期望值 `"false"` 改成 `"true"` | `AssertionError: Locator expected to have attribute 'true'` / `Actual value: false` / `14 × locator resolved to <div role="dialog" id="note-editor" class="is-visible" aria-hidden="false" data-testid="rd-note-editor">…</div>` | 改回 `"false"` 后恢复 pass |
| 4 | `delete` 用例把 `K2_EXPECTED_AFTER_DELETE` 从 `0` 改成 `1` | `AssertionError: Locator expected to have count '1'` / `Actual value: 0` / `waiting for locator("[data-testid=\"rd-viewport\"] iframe").content_frame.get_by_test_id("rd-anno-span")` | 改回 `0` 后恢复 pass |
| 5 | `ask_ai` 用例把期望的事件名 `reader3:ai:ask` 改成 `reader3:ai:asked` | `TimeoutError: Page.wait_for_function: Timeout 8000ms exceeded.` （监听器换了名字就再也收不到 detail） | 改回 `reader3:ai:ask` 后恢复 pass |
| 6 | K-6a 直接进入把断言写成 `chapter_index == 0`（即「默认值也能过」的那个退化） | `AssertionError: 直接进入 /read/smoke_data/1 建的标注，落库 chapter_index 是 1，不是 URL 里的 0。` + `assert 1 == 0` | 改回 `chapter_index` 参数后三个参数化项全部恢复 pass |
| 7 | 站内翻章用例把 `K6_EXPECTED_IN_URL_CHAPTER` 从 `1` 改成 `2` | `TimeoutError: Page.wait_for_function: Timeout 8000ms exceeded.`（等的是 pathname 变成 `/read/cjk_data/2`，而 TOC 行点的是第 1 章） | 改回 `1` 后恢复 pass |

第 4 行的红点值得说一句：把基线改成 `1` 之后，`wait_for_notes(..., 1)` **没有**超时——它在
第一次轮询就抢到了「删除请求还没落盘」的那个瞬时状态，于是红点落到了后面「刷新后 iframe 里
`<mark>` 计数」的那条上。这恰好说明：这条用例真正的判据是**刷新之后重建的 DOM 与盘上的内容**，
不是那次等待。任务书 §0 把「断言 DELETE 请求发生过」列为反例，同理，「等到某个瞬时计数」
也不构成判据。

第 6 行是这张表里最重要的一行：它证明**「非零章」这个前提本身是被测出来的**。
`Annotation.chapter_index` 的默认值是 `0`（`src/reader3_app/models/annotations.py`），
所以任何在第 0 章上做的 K-6a 断言都是空转——`chapter_index` 从来没被 URL 决定过也照样绿。
本模块的三组直接进入参数因此全部取非零章。

--------------------------------------------------------------------------------
第五条纪律：守恒基线一律是**字面量**
--------------------------------------------------------------------------------
`K2_EXPECTED_AFTER_CREATE = 1` / `K2_EXPECTED_AFTER_DELETE = 0` /
`K6_EXPECTED_IN_URL_CHAPTER = 1` 都是写死的数，不是从被测源头（`read_notes(...)` 的长度、
`Reader3Ctx.chapterIndex`、`page.url` 的解析结果）切出来的。切出来的基线在被测对象整体
失效时会跟着一起变，于是断言恒成立。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID, BOOK_ID_CJK  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    CH1_ANCHOR,
    CH1_QUOTE,
    SELECTION_TIMEOUT_MS,
    open_reader,
    pathname_is,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# 字面量基线（第五条纪律：不许从被测源头切）
# ---------------------------------------------------------------------------

#: 一次成功的创建之后，`notes.json` 恰好 1 条。写 `== 1` 而不是 `>= 1`：
#: `toggleAnnotation` 的删旧建新分支里有两次落库动作，`>=` 会放过「一次点击写两条」。
K2_EXPECTED_AFTER_CREATE = 1

#: 一次成功的删除之后，`notes.json` 恰好 0 条。写 `== 0` 而不是 `< 1`：
#: 删除路径唯一的旁观者就是被删那条本身，0 是这条用例里唯一正确的数。
K2_EXPECTED_AFTER_DELETE = 0

#: 预置给 `delete` 用例的那条标注。id 写死是为了让 `<mark>` 能按
#: `data-annotation-id` 精确点到——ADR-0014 把 `data-annotation-id` 列进了判别位闭合清单。
K2_DELETE_TARGET_ID = "k2-delete-target"

#: 写进 note 编辑器的正文。带中文与空格，能顺带证明落库没有做多余的转义/截断。
K2_NOTE_TEXT = "K2 便签正文 via rd-anno-note"

#: `ask_ai` 那一条特意跑在**第 1 章**：事件 detail 里的 `chapter_index` 若在第 0 章上断言，
#: 与 `getReaderContext()` 完全失效时的回退值撞在一起，断言就是空转。
K2_ASK_CHAPTER = 1

#: CJK 语料（`tests/fixtures/epub_corpus.py` 的 `CJK_SENTENCES`）：三章各一句。
#: 取第 1 / 第 2 章，避开第 0 章那个与默认值重合的退化点。
CJK_CH1_QUOTE = "喫茶店"
CJK_CH1_ANCHOR = "彼女は喫茶店で本を読んでいた。"
CJK_CH2_QUOTE = "커피"
CJK_CH2_ANCHOR = "커피를 마시며 기다렸다."

#: 站内翻章要点的那一行 TOC 对应的 spine 文件名。`data-file-href` 是 `findAndGo()` 的入参，
#: 也是 TOC 行上唯一稳定的判别位（ADR-0014 的判别位闭合清单里就有它）。
#: 它是**输入**——CJK 语料里 `text/c2.xhtml` 是第 1 章（`Doc` 从 c1 起编号，spine 从 0 起数）。
K6_TURN_TO_HREF = "text/c2.xhtml"

#: 翻章之后 URL 里应当出现的章号，也是标注该落到的那一章。它是**期望值**，
#: 与上面那个输入分开写：两者一旦合成一个常量，「点了 c2 就断言 c2」会退化成同义反复。
K6_EXPECTED_IN_URL_CHAPTER = 1

#: 第 0 章在翻章用例结束时应当**一条都没有**。
K6_EXPECTED_IN_CHAPTER_0 = 0


# ---------------------------------------------------------------------------
# 本模块自用的小工具
#
# 三个里的 `_pathname_is` 已于 Wave 3.5 上收为 `helpers.pathname_is`（任务书 §0.6 欠账 #13），
# 剩下两段 JS 常量留在本模块内：它们各自只服务一条用例（K-2 的 ask_ai、K-6a 的翻章哨兵），
# 没有第二个模块会要。`_served_annotations` 同理——全仓只有本模块调它，不构成重复。
# ---------------------------------------------------------------------------

#: 在**选区建立之前**装一次性监听器，把 `reader3:ai:ask` 的 detail 存到 window 上。
#: 必须先装后点：`askAi()` 里的 `dispatchEvent` 是同步的，点完再装必然错过。
_ASK_LISTENER_JS = """() => {
  window.__k2AskDetail = null;
  window.addEventListener(
    'reader3:ai:ask',
    (e) => { window.__k2AskDetail = e.detail; },
    { once: true },
  );
}"""

#: 在翻章之前给 window 打一个标记。`history.replaceState` 不换 document，标记会活下来；
#: 一旦哪天翻章退化成整页跳转，document 重建，标记消失，这条断言会红。
_RELOAD_SENTINEL_JS = "() => { window.__k6NoReload = true; }"


def _served_annotations(page: Page, base_url: str, book_id: str, chapter: int) -> List[Dict[str, Any]]:
    """`GET /api/notes/{book}/{chapter}` 交出的那一章的标注。

    走服务端而不是直接读盘，是因为这两者证明的不是一回事：`read_notes` 证明「落库的字段
    对」，本函数证明「服务端按章过滤的结果也对」。K6 的失效形态里有一种是字段写对了但
    过滤按别的键做，只读盘看不出来。
    """
    resp = page.request.get(f"{base_url}/api/notes/{book_id}/{chapter}")
    assert resp.ok, f"GET /api/notes/{book_id}/{chapter} 不是 2xx：{resp.status}"
    return resp.json()["annotations"]


# ---------------------------------------------------------------------------
# K-2：七个 data-action 逐个按一遍，判据一律落在「结果」上
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_testid,expected_type",
    [
        pytest.param("rd-anno-type-marker", "marker", id="marker"),
        pytest.param("rd-anno-type-wavy", "wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", "underline", id="underline"),
    ],
)
def test_k2_type_actions_create_an_annotation_of_that_type(
    page: Page,
    live_server: str,
    e2e_books_dir: Path,
    action_testid: str,
    expected_type: str,
) -> None:
    """K-2（S2，取值域三元 · L5 落库判据）：`marker` / `wavy` / `underline` 各按一次。

    这三个取值走 `handleAction` 的**创建**支（`marker` 经 `toggleMarkerAnnotation`，
    另两个经 `toggleAnnotation`），可观察结果是同一个：`notes.json` 多出恰好一条、
    且 `type` 等于按下的那个键。

    **判据为什么是 `type` 而不只是「多了一条」。** 契约 K2 说的是「取值到结果的映射是
    **全函数**」，全函数的反面不只是「某个取值没反应」，还有「三个取值映到同一个结果」
    ——`handleAction` 里那三行 `if (action === …)` 只要有一行的 type 传错，条数断言照样绿。
    把 type 钉死，才是在测那个映射本身。

    什么改动会让它红：`data-action` 改名、按钮换成非 `<button>` 标签（`closest()` 落空）、
    `handleAction` 的分派表少一支、或者 `type` 在传递途中被写成常量。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(action_testid).click()

    records = wait_for_notes(e2e_books_dir, BOOK_ID, K2_EXPECTED_AFTER_CREATE, page=page)
    assert records[0]["type"] == expected_type, (
        f"按下 {action_testid} 之后落库的 type 是 {records[0]['type']!r}，"
        f"不是期望的 {expected_type!r}。"
    )
    assert records[0]["quote"] == CH0_QUOTE, (
        f"落库的 quote 是 {records[0]['quote']!r}，不是选中的 {CH0_QUOTE!r}——"
        "按钮的 action 分派对了，但传下去的选区不是这一次选的那段"
    )


def test_k2_copy_action_puts_the_selected_text_on_the_clipboard(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-2 `copy`（S1 · L5 剪贴板判据）：按下之后剪贴板里就是选中的那段文字。

    `copySelection()` 只做三件事：从 iframe 的 `contentWindow.getSelection()` 取字符串、
    `navigator.clipboard.writeText`、`closeSelectionToolbarIfOpen()`。本条把第二件与第三件
    分别钉住：只钉剪贴板，工具条不关也绿；只钉工具条，写进剪贴板的是空串也绿。

    **权限在用例内授予，不动 conftest。** `grant_permissions` 作用在 `page.context` 上，
    origin 取 `live_server`（fixture 给的正是带端口的 base URL）。没有这一句时
    `readText()` 会以 `NotAllowedError` 抛出，而不是返回空串——所以这句本身也是有判据的。

    什么改动会让它红：`copy` 这个 `data-action` 改名、`copySelection` 改成读外层
    document 的 selection（iframe 里的选区在外层是空的，剪贴板会变成空串）、
    或者末尾那次关工具条被删掉。
    """
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server)

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-copy").click()

    clipboard = page.evaluate("() => navigator.clipboard.readText()")
    assert clipboard == CH0_QUOTE, (
        f"剪贴板里是 {clipboard!r}，不是选中的 {CH0_QUOTE!r}。"
    )

    # 第二件事：`closeSelectionToolbarIfOpen()` 也跑到了。与剪贴板那条互不覆盖。
    expect(page.get_by_test_id("rd-anno-toolbar")).not_to_be_visible()


def test_k2_note_action_opens_the_editor_and_the_save_lands_a_note_record(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-2 `note`（S1 · L5 落库判据）：按下 → 编辑器 `aria-hidden` 翻成 `"false"` → 存 → 落一条 `type=note`。

    `note` 是七个取值里唯一**不直接落库**的那个：`openNoteEditor()` 只开面板，落库要等
    `rd-note-editor-primary`。所以本条的可观察结果分两段——面板真的开了（`aria-hidden`
    从 `"true"` 翻到 `"false"`），以及存下去之后盘上真的多了一条 `type=note`。

    **为什么断 `aria-hidden` 而不是 `to_be_visible()`。** 两者在今天同时成立，但它们的
    失效形态不同：`is-visible` 那个 class 掉了会让可见性断言红，而 `aria-hidden` 忘了翻
    只会让屏幕阅读器把整个编辑器当成不存在——后者不影响像素，只有属性断言抓得住。
    W-4（`test_write_note_editor.py`）守的是可见性那一半，本条补的是属性这一半。

    什么改动会让它红：`note` 这个 `data-action` 改名、`openNoteEditor` 不再翻
    `aria-hidden`、或者保存分支把 `type` 写成了 `marker`。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    editor = page.get_by_test_id("rd-note-editor")
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    expect(editor).to_have_attribute("aria-hidden", "true")

    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()

    expect(editor).to_have_attribute("aria-hidden", "false")

    page.get_by_test_id("rd-note-editor-input").fill(K2_NOTE_TEXT)
    page.get_by_test_id("rd-note-editor-primary").click()

    records = wait_for_notes(e2e_books_dir, BOOK_ID, K2_EXPECTED_AFTER_CREATE, page=page)
    assert records[0]["type"] == "note", (
        f"经 rd-anno-note 存下的那条 type 是 {records[0]['type']!r}，不是 'note'"
    )
    assert records[0]["note_text"] == K2_NOTE_TEXT, (
        f"落库的 note_text 是 {records[0]['note_text']!r}，不是填进去的 {K2_NOTE_TEXT!r}"
    )


def test_k2_delete_action_removes_the_clicked_annotation_from_disk(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-2 `delete`（S1 · L5 落库判据）：点中 `<mark>` → 按 Delete → 刷新后盘上一条不剩。

    `delete` 是七个取值里唯一**要求先有标注**的那个，所以起点用 `seed_notes` 预置一条，
    而不是先按 marker 再按 delete——后者会把「创建这一支坏了」与「删除这一支坏了」混成
    同一个红。

    **为什么收尾要刷新。** `deleteCurrentAnnotation` 末尾会 `loadAndRender()` 重绘，那次
    重绘用的是服务端返回后重新拉的列表，但页面 JS 状态从未清零。刷新是唯一能把
    「JS 里已经忘了」与「盘上真的没了」分开的动作（任务书 §0 把「断言 DELETE 请求发生过」
    列为反例）。

    什么改动会让它红：`delete` 这个 `data-action` 改名、`onAnnotationClick` 不再把
    metadata 收进 `currentAnnotationMeta`（Delete 拿不到 id，静默 return）、
    或者服务端 204 了但没落盘。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": K2_DELETE_TARGET_ID,
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )
    before = read_notes(e2e_books_dir, BOOK_ID)
    assert [a["id"] for a in before] == [K2_DELETE_TARGET_ID], f"预置没落对：{before}"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    target = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{K2_DELETE_TARGET_ID}"]'
    )
    expect(target).to_have_text(CH0_QUOTE)
    target.click()

    # 工具条开了才有 Delete 可点。这一断不是凑数：`onAnnotationClick` 首行遇到非
    # `mark.annotation` 就静默 return，之后的 click 报出来的会是 Playwright 的
    # actionability 超时，而不是「点击没落在标注上」。
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-delete").click()

    wait_for_notes(e2e_books_dir, BOOK_ID, K2_EXPECTED_AFTER_DELETE, page=page)
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(K2_EXPECTED_AFTER_DELETE)
    assert read_notes(e2e_books_dir, BOOK_ID) == [], (
        f"刷新后盘上还有：{read_notes(e2e_books_dir, BOOK_ID)}"
    )


def test_k2_ask_ai_action_dispatches_the_event_and_the_panel_receives_the_quote(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-2 `ask_ai`（S1 · L5 事件 detail + 面板内容判据）：事件真的派发了，面板真的收到了。

    **不断言 AI 的回答**——那要出网，且答案不确定。`askAi()` 的整个可观察行为就两件事：
    往 `window` 上派发 `reader3:ai:ask`（K4 六个事件名之一），以及把
    `closeSelectionToolbarIfOpen()` 跑掉；`ai.js` 那侧监听到之后开面板、把引文填进输入框。
    本条把这条链的两端都钉住：detail 的内容（发出去的东西对）与输入框的值（收到的东西对）。

    **为什么输入框那条必须用 `expect(...).to_have_value(...)` 而不是 `input_value()`。**
    `ai.js` 的 `handleAskEvent` 在填值之前 `await` 了 `loadPreferences()` /
    `restoreConversation()`，所以点击刚返回时输入框**还是空的**（spike 实测：
    `AI INPUT: ''` 而 `AI PANEL HIDDEN: false`）。同步读会稳定读到空串，得到一条永远红的
    用例；`expect` 会自动重试到超时。

    **为什么跑在第 1 章。** detail 里的 `chapter_index` 来自 `getReaderContext()`，
    而它在完全失效时的回退值就是 0；在第 0 章上断言 `== 0` 是空转。

    什么改动会让它红：`ask_ai` 这个 `data-action` 改名、事件名改掉（K4 的契约面）、
    detail 的字段改名、或者 `ai.js` 不再把引文写进输入框。
    """
    frame = open_reader(page, live_server, BOOK_ID, K2_ASK_CHAPTER, CH1_ANCHOR)

    # 先装监听器再建选区：`dispatchEvent` 是同步的，点完再装必然错过。
    page.evaluate(_ASK_LISTENER_JS)

    select_in_frame(frame, CH1_QUOTE)
    page.get_by_test_id("rd-anno-ask").click()

    page.wait_for_function(
        "() => window.__k2AskDetail !== null", timeout=SELECTION_TIMEOUT_MS
    )
    detail = page.evaluate("() => window.__k2AskDetail")

    assert detail["quote"] == CH1_QUOTE, (
        f"reader3:ai:ask 的 detail.quote 是 {detail['quote']!r}，不是选中的 {CH1_QUOTE!r}"
    )
    assert detail["chapter_index"] == K2_ASK_CHAPTER, (
        f"detail.chapter_index 是 {detail['chapter_index']!r}，"
        f"不是当前章 {K2_ASK_CHAPTER}——`getReaderContext()` 退回默认值了？"
    )
    assert detail["book_id"] == BOOK_ID, (
        f"detail.book_id 是 {detail['book_id']!r}，不是 {BOOK_ID!r}"
    )

    # 另一端：`ai.js` 收到了，面板开了，引文填进去了。
    expect(page.get_by_test_id("rd-ai-panel")).to_have_attribute("aria-hidden", "false")
    expect(page.get_by_test_id("rd-ai-input")).to_have_value(re.compile(re.escape(CH1_QUOTE)))


# ---------------------------------------------------------------------------
# K-6a：落库的 chapter_index 恒等于 URL 里的那个数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "book_id,chapter_index,quote,anchor",
    [
        pytest.param(BOOK_ID, 1, CH1_QUOTE, CH1_ANCHOR, id="epub2-ch1"),
        pytest.param(BOOK_ID_CJK, 1, CJK_CH1_QUOTE, CJK_CH1_ANCHOR, id="cjk-ch1"),
        pytest.param(BOOK_ID_CJK, 2, CJK_CH2_QUOTE, CJK_CH2_ANCHOR, id="cjk-ch2"),
    ],
)
def test_k6a_direct_entry_stamps_the_chapter_from_the_url(
    page: Page,
    live_server: str,
    e2e_books_dir: Path,
    book_id: str,
    chapter_index: int,
    quote: str,
    anchor: str,
) -> None:
    """K-6a（S2，取值域 · L5）：直接进入 `/read/{book}/{N}` 建标注，落库的 `chapter_index == N`。

    **三组参数为什么全是非零章。** `Annotation.chapter_index` 的默认值是 `0`
    （`src/reader3_app/models/annotations.py`），`getReaderContext()` 的回退分支也解析不出
    章号时给 0。在第 0 章上做这条断言，等于「默认值恰好等于期望值」——`chapter_index`
    整条传递链断掉也照样绿。取 1 / 1 / 2 三组，把这个空转堵死。

    **两本书为什么都要。** `smoke_data` 是 EPUB2 两章，`cjk_data` 是三章且正文全是多字节
    ——章号解析走的是 URL 路径而不是正文，但 `getReaderContext()` 的另一条支路读的是
    `Reader3Ctx`，那是模板渲染出来的。两本不同结构的书各走一遍，才覆盖到「第二章」与
    「第三章」两个不同的 spine 位置。

    **为什么还要问一次服务端。** 盘上的字段对，和服务端按章过滤的结果对，是两件事：
    K6 有一种失效形态是字段写对了但 `GET /api/notes/{book}/{N}` 按别的键筛，只读盘看不出来。
    反向那一问（第 0 章必须是空的）是这条断言的另一半——只问「第 N 章有」的话，
    一个「无论问哪章都把全书交出来」的实现照样绿。

    什么改动会让它红：`getReaderContext()` 的 pathname 解析写错、`Reader3Ctx.chapterIndex`
    不再由模板注入、`POST /api/notes/{book}/{chapter}` 的路径参数被忽略而改用请求体里的值。
    """
    assert read_notes(e2e_books_dir, book_id) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, book_id, chapter_index, anchor)
    select_in_frame(frame, quote)
    page.get_by_test_id("rd-anno-type-marker").click()

    records = wait_for_notes(e2e_books_dir, book_id, K2_EXPECTED_AFTER_CREATE, page=page)
    assert records[0]["chapter_index"] == chapter_index, (
        f"直接进入 /read/{book_id}/{chapter_index} 建的标注，"
        f"落库 chapter_index 是 {records[0]['chapter_index']}，不是 URL 里的 {chapter_index}。"
    )

    served = _served_annotations(page, live_server, book_id, chapter_index)
    assert [a["id"] for a in served] == [records[0]["id"]], (
        f"GET /api/notes/{book_id}/{chapter_index} 交出的是 {[a['id'] for a in served]}，"
        f"不是刚建的那条 {records[0]['id']!r}"
    )
    other = _served_annotations(page, live_server, book_id, 0)
    assert other == [], (
        f"GET /api/notes/{book_id}/0 也交出了 {other}——"
        "要么章号没落对，要么服务端根本没按章过滤"
    )


def test_k6a_in_page_chapter_turn_stamps_the_new_chapter(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-6a 站内翻章（S3，状态迁移 · L5）：`replaceState` 改址之后，落库的章号跟着改。

    这是本模块最重要的一条。直接进入那三条测的是「首屏渲染时章号对」，而 SPA 式改址是
    另一条完全不同的路径：`findAndGo()` → `Reader3Epub.displaySectionIndex()` →
    `syncLocationToUrl()` 的 `history.replaceState`。**document 从头到尾没有重建**，
    所以 `Reader3Ctx.chapterIndex`（模板渲染时注入的常量）与 URL 里的数**有可能分道扬镳**
    ——这正是 K6 契约要守的那个不变式，也是首屏那三条永远测不到的地方。

    **翻章为什么不用 `rd-page-next`。** 任务书 §2 与矩阵 §B 都写死了它完全不可用：
    `.nav-zone-left/right` 是 `display: none`，且只有 legacy `js/pagination.js` 绑定它们，
    而 `reader.html` 不加载那个文件。点它只会得到 30s 的 actionability 超时。

    **翻完为什么要把 TOC 抽屉关掉。** `toolbar.js` 在 document 上装了一个捕获阶段的
    click 监听，命中忽略名单之外的目标时会关掉所有面板并 `preventDefault()`。
    抽屉开着时去点工具条，这一脚会和标注工具条自己的 click 处理抢同一次事件；关掉抽屉
    把这个不确定性整个移出用例，剩下的红就只可能来自章号本身。

    **等的是什么。** 等的是 `new URL(location.href).pathname === "/read/cjk_data/1"`——
    不是 `page.url.endswith("/1")`。TOC 行是 `<a href="#">`，浏览器跑完 onclick 之后仍会把
    `#` 追加上去，最终 URL 是 `…/read/cjk_data/1#`；用整串匹配会 30s 超时（spike 实测踩过）。

    什么改动会让它红：`syncLocationToUrl` 不再改址、`findAndGo` 定位到别的 spine 项、
    或者 `getReaderContext()` 在改址之后仍旧交出旧章号（那正是缺陷形态本身）。
    """
    assert read_notes(e2e_books_dir, BOOK_ID_CJK) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID_CJK, 0, "他在咖啡館裡等了很久。")
    page.evaluate(_RELOAD_SENTINEL_JS)

    page.get_by_test_id("rd-rail-toc").click()
    page.locator(
        f'[data-testid="rd-toc-row"][data-file-href="{K6_TURN_TO_HREF}"]'
    ).click()

    pathname_is(page, f"/read/{BOOK_ID_CJK}/{K6_EXPECTED_IN_URL_CHAPTER}")

    # 整页跳转会把这个标记连同 document 一起扔掉。它还在，说明改址走的确实是
    # `history.replaceState`——这一条是「站内翻章」这个前提本身的判据。
    assert page.evaluate("() => window.__k6NoReload === true"), (
        "翻章之后 window 上的哨兵没了：这次不是 replaceState，是整页跳转，"
        "本条测的那个不变式（不重建 document 也要章号一致）已经不存在了"
    )

    page.get_by_test_id("rd-rail-toc").click()  # 关抽屉，理由见 docstring
    expect(frame.locator("body")).to_contain_text(CJK_CH1_ANCHOR)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板

    select_in_frame(frame, CJK_CH1_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()

    records = wait_for_notes(e2e_books_dir, BOOK_ID_CJK, K2_EXPECTED_AFTER_CREATE, page=page)
    assert records[0]["chapter_index"] == K6_EXPECTED_IN_URL_CHAPTER, (
        f"站内翻到第 {K6_EXPECTED_IN_URL_CHAPTER} 章之后建的标注，落库 chapter_index 是 "
        f"{records[0]['chapter_index']}，不是 URL 里的 {K6_EXPECTED_IN_URL_CHAPTER}。"
        "改址走的是 replaceState，`Reader3Ctx.chapterIndex` 是首屏注入的常量——"
        "两者一旦分家，就是这条断言要抓的那个缺陷"
    )
    assert records[0]["quote"] == CJK_CH1_QUOTE, (
        f"落库的 quote 是 {records[0]['quote']!r}，不是第 {K6_EXPECTED_IN_URL_CHAPTER} 章里选的 "
        f"{CJK_CH1_QUOTE!r}——章号对了但选区来自旧章的正文？"
    )

    served_zero = _served_annotations(page, live_server, BOOK_ID_CJK, 0)
    assert len(served_zero) == K6_EXPECTED_IN_CHAPTER_0, (
        f"翻章之后第 0 章还有 {len(served_zero)} 条：{served_zero}。"
        "标注被记在了翻章前的那一章上"
    )
