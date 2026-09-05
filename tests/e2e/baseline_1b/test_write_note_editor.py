"""WI-5 —— W-4 / W-7：笔记的**创建**与**编辑保存**，写路径上唯一走 note-editor 的两条。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-5（最高权威）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §3（W-4 / W-7）、
§0 三条写作纪律 ＋ 第四条「特征化用例的可失败性证据」、§0.6（本模块是 Wave 1 的全部产出）。

**两条测的不是同一条链，尽管它们共用一个浮层。**

    W-4  选区 → `rd-anno-note` → `openNoteEditor()`（`editingNoteId = null`）
         → `saveNote()` 走**新建**分支 → `POST /api/notes/{book}/{chapter}`
    W-7  点已有 `<mark>` → `onAnnotationClick` → `openNoteEditorWithExisting()`
         （`editingNoteId = <id>`）→ `saveNote()` 走**更新**分支
         → `PUT /api/notes/{book}/{chapter}/{id}`

分岔点只有 `editingNoteId` 一个布尔式判断（`saveNote` 的 `if (this.editingNoteId)`）。
所以 W-7 的**全部**价值在于「它确实走了另一支，且那一支是原地改」——这就是矩阵给它定的
**更新守恒律**：编辑一条笔记改变的只有内容，`id` 不变、条目总数不变、**同章其余条目
逐字节不变**。三个合取项缺一条，就有一个具体的坏实现能全绿：

    缺「id 不变」        ⇒ 「DELETE 掉再 POST 一条新的」全绿
    缺「总数不变」        ⇒ 「整章清空再写请求里那一条」全绿
    缺「旁观条逐字节不变」 ⇒ 同上；条数对得上不代表内容没被动过

**【R2 交叉指针】W-7 的旁观条与 WI-6 的 W-5a-⓪ 是同一个构造，两条都不是冗余。**
两边的旁观条都是 `quote="One"`、同章（chapter 0 的 `<h1>One</h1>`）、与目标条
**不相邻不重叠**。但它们各自扣住的是**不同函数上的同一类缺陷**：

  * **本模块的 W-7** 守的是**服务端**：`PUT /api/notes/{book}/{chapter}/{note_id}` →
    `notes_service.update_annotation`。这条链是 load 整章 → 改一条 → `save_annotations`
    **整章回写**。回写路径上少带一条，同章别的标注就没了，而 HTTP 200 照样返回。
  * **WI-6 的 W-5a-⓪**（同色重按 = 差集删除，Wave 2 落地，**本模块写作时尚不存在**）守的是
    **客户端**：`toggleMarkerAnnotation` → `getExistingMarkerIds` 的**候选集**。那里的
    退化方向是「选区命中」放宽成「整章同 type 同 color」——放宽之后重按一次 marker 会把
    旁观条一起删掉。

  换句话说：把 W-7 删了，服务端整章回写的漏条没人管；把 W-5a-⓪ 删了，客户端候选集放宽
  没人管。两条各自能红在对方绿的地方。WI-6 落地时会写回指向本条的反向指针（任务书 §0.6
  纪律 5）；本条按**用例 id ＋ WI 号**引用它，不猜文件名。

**关于「刷新后再断一次终态」（§0 第四条纪律里 WI-4 实测出来的那个坑）。**
`wait_for_notes` 一观察到期望条数就返回，读到的可能是中间态。两条都靠
`assert_roundtrip` 在 `page.reload()` **之后**再断一次条数来收口。W-7 还多一层麻烦：
PUT 改的是**内容**，条数从头到尾不变，等条数会立刻带着**旧内容**返回——所以它先用
`wait_for_note_text` 等在被改的那个量上，再进 `assert_roundtrip`。

**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-03，七处全部已还原）。**
本模块两条都是特征化用例——被测行为上线数月，红不可得，所以不伪造红，改用定向破坏留档。
每一处只打**一个**判据，不是把函数挖空：挖空只能证明断言不空转，证不了「这一条断言拦的是
它自己那件事」。

| # | 破坏点 | 失败输出（节选，逐字抄自 pytest） | 它证明了哪一条判据不是摆设 |
|---|---|---|---|
| A | `annotations.js` `showTooltip()` 删掉 `this.tooltip.textContent = text;`（浮层照样加 `is-visible`，只是空的） | W-4 红：`AssertionError: Locator expected to have text 'first note body' / Actual value: / - unexpected value ""`；W-7 绿 | tooltip 断的是**内容**。`to_be_visible()` 在这个破坏下仍然绿——可见性不构成通过条件 |
| B | `notes-panel.js` 把 `noteEl.textContent = noteText` 改成 `""` | W-4 **越过**了 tooltip 那条判据（`expect(tooltip).to_have_text(W4_NOTE_TEXT)`），红在面板那条上（`expect(item).to_contain_text(W4_NOTE_TEXT)`）：`Locator expected to contain text 'first note body' / Actual value: Alpha prose`；W-7 同样红在面板那句 | 两条读回渠道**互不覆盖**。tooltip 全对，面板照样能坏——只断一条就会放过这半边 |
| C | `annotations.js` `saveNote()` 首行插 `this.editingNoteId = null;`（把 PUT 逼回 POST） | W-7 红：`8.0s 内 wi5-w7-target-note 的 note_text 没有变成 'new body'`；**W-4 绿**（1 passed） | `editingNoteId` 那一支是真的被走到的，且 W-4 覆盖不到它——两条不是同一条链 |
| D1 | `notes_service.update_annotation` 改成「删了重建」：新 `uuid` ＋ 新 `created_at`，同章其余条目原样保留，**条数不变** | W-7 红：`8.0s 后 id='wi5-w7-target-note' 这一条**已经不在 notes.json 里了**…现存的 id：['e7b5b206-…', 'wi5-w7-bystander-marker']` | 「`id` 不变」。注意条数与旁观条在这个破坏下**全对**——只断这两项的矩阵会全绿 |
| D2 | 同上函数，保留 `id`，只把 `created_at` 重置成 `now()` | W-7 红：`目标条的 created_at 变了：'2026-01-01T00:00:00+00:00' → '2026-09-02T16:36:26.521089+00:00'` | 「`created_at` 不变」。这是「删了重建」在**保住 id 之后**唯一还藏不住的地方 |
| E1 | 同上函数，`save_annotations(books_dir, book_id, [ann])`——整章只回写命中的那一条 | W-7 红：`8.0s 内 notes.json 没有稳定到 2 条，实际 1 条` | 「条目总数不变」 |
| E2 | 同上函数，去掉 `if ann.id == note_id` 守卫，正文写给**每一条**——条数不变、目标条也确实改对了 | W-7 红：`编辑目标笔记时动到了同章的另一条标注 … Differing items: {'note_text': 'new body'} != {'note_text': None}` | 「旁观条整字典相等」。E1 那条（数条数）在这个破坏下是绿的 |

**D1 顺手暴露了一个 helper 缺陷，已修。** `wait_for_note_text` 原先把每轮看到的记录存进
`seen`，超时打印 `seen`——于是 D1 报成「note_text 没变成 X，当前是 <旧记录>」，而那条旧
记录此刻**已经不在盘上**。把人指向「PUT 没生效」，真相是「PUT 生效了但换了 id」。现在
超时后重读一次，分「id 没了」与「id 在但内容不对」两种情况报（见 `helpers.py`）。

**D1 还暴露了选择器 lint 的一个盲区，已修。** `scripts/lint_e2e_selectors.py` 的正则不许
引号前带前缀，于是**用 f-string 拼出来的 locator 实参一处都没被扫到**；而带判别位的复合
选择器（ADR-0014）要插一个运行期 id，天然全是 f-string。补上前缀后扫描面从 14 处升到
20 处，本模块的 5 处与 `helpers.py` 的 1 处才真正进了 lint 的视野。
（顺带一提：本段原先在这里贴了一个 f-string locator 的**字面例子**，补完 lint 之后它自己
被扫成了违规——正好说明补的这一刀落在了实处。）

七处破坏的还原核验一律是 `git diff --quiet <被破坏的文件>` 退出 0；生产代码在本
模块落地时**逐字节还原**（`git diff -- src/` 为空）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    assert_bystanders_unchanged,
    assert_roundtrip,
    open_reader,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_note_text,
)

pytestmark = pytest.mark.baseline_1b

#: W-4 落库的笔记正文。不含任何 HTML 元字符是刻意的：服务端 POST 时 `html.escape`、
#: GET 时 `html.unescape`，带元字符会让「盘上的值」与「渲染出来的值」不同解，而本条要断的
#: 是两条读回渠道**彼此**一致，不是转义往返——转义往返有它自己的地方（W-9 的多字节边界
#: 与 `tests/unit/` 的 notes 端点用例）。
W4_NOTE_TEXT = "first note body"

#: W-7 的目标条与旁观条。id / created_at 都写死，因为**守恒律断的正是它们没变**——
#: 让 `seed_notes` 生成随机 uuid 与「此刻」，断言就只能拿运行期读到的值去比运行期读到的值，
#: 那是一句同义反复。写死之后，「id 变成别的」在失败消息里是一个人能一眼认出的字面量。
W7_TARGET_ID = "wi5-w7-target-note"
W7_BYSTANDER_ID = "wi5-w7-bystander-marker"
W7_OLD_BODY = "old body"
W7_NEW_BODY = "new body"

#: 旁观条的 quote。`<h1>One</h1>` 的全部内容，与目标条的 `Alpha prose`（在 `<p>` 里）
#: **不相邻不重叠**——重叠的话 `AnnotationRenderer.render()` 的分段会把两条合进同一个
#: `<mark>`，「旁观条的高亮还在」就退化成「目标条的高亮还在」。
#: 与 WI-6 的 W-5a-⓪ 同构，见模块 docstring 的 R2 交叉指针。
W7_BYSTANDER_QUOTE = "One"


def _by_id(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(r["id"]): r for r in records}


def test_w4_new_note_reads_back_through_both_channels(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-4（S5，往返不变式）：新建笔记 → 刷新 → **两条读回渠道**都拿到同一段正文。

    链路：选区 → `rd-anno-note` → `openNoteEditor()` → `rd-note-editor-input` →
    `rd-note-editor-primary` → `saveNote()` 的**新建**分支 → `createAnnotation`
    → `POST /api/notes/{book}/{chapter}`。

    **为什么两条渠道要在同一条用例里断，而不是拆成两条。** 它们共享全部前置动作（建选区、
    开编辑器、填字、保存、刷新），拆开等于把最贵的一段（一次冷加载 + 一次刷新）付两遍；
    而两条断言不会互相掩盖失败——各自的失败消息会点名是哪条渠道断的。

    **为什么必须两条都断。** 它们是 `note_text` 的两个**独立消费方**，走的是两条不相交
    的代码路径：

      * iframe 内的 `<mark data-note-text>` → `onHover` → `showTooltip` → `rd-note-tooltip`
        （`annotations.js`，数据来自 `GET /api/notes/{book}/{chapter}`）；
      * 外层 Notes 面板的 `rd-notes-item` → `notes-panel.js` 的 `loadAndRender`
        （数据来自 `GET /api/notes/{book}`，另一个端点、另一套摘要逻辑、另一处
        `html.unescape`）。

    只断面板会放过「tooltip 整条通路坏掉」；只断 tooltip 会放过「面板整条通路坏掉」。

    **tooltip 断的是内容，不是可见性。** `expect(...).to_be_visible()` 单独**不构成
    通过条件**——`showTooltip` 先 `textContent = text` 再 `classList.add("is-visible")`，
    把 `textContent` 那行删掉之后浮层照样可见，只是空的。这与 §0「几何断言」纪律是同一条
    要求的两种形态：断「元素存在/可见」等于没断。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()

    # 编辑器开了才有地方填字。这一断不是凑数：`openNoteEditor()` 首行是
    # `if (!this.currentRange || !this.noteEditor) return;`，静默 return 之后
    # 下面的 fill 会以「元素不可见」超时，报出来的是 Playwright 的超时而不是「编辑器没开」。
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    page.get_by_test_id("rd-note-editor-input").fill(W4_NOTE_TEXT)
    page.get_by_test_id("rd-note-editor-primary").click()

    # 往返收尾：落库 → 刷新 → `<mark>` 覆盖的文本回到选中的那一段 → 终态仍是恰好 1 条。
    # `expected_type="note"` 而不是 "marker"：`saveNote` 的新建分支写死了 type=note，
    # 这一条同时钉住「Add Note 按钮没有退化成一次普通高亮」。
    record = assert_roundtrip(
        page, e2e_books_dir, BOOK_ID, CH0_QUOTE, CH0_ANCHOR, expected_type="note"
    )
    note_id = str(record["id"])

    # --- 渠道 (c)：盘上的原始 JSON -------------------------------------------
    settled = read_notes(e2e_books_dir, BOOK_ID)
    assert len(settled) == 1, f"终态不是恰好 1 条：{settled}"
    assert settled[0]["type"] == "note", f"落库的 type 不是 note：{settled[0]}"
    assert settled[0]["note_text"] == W4_NOTE_TEXT, (
        f"盘上的 note_text 是 {settled[0]['note_text']!r}，不是填进编辑器的 "
        f"{W4_NOTE_TEXT!r}（服务端 POST 时 html.escape，本条正文不含元字符，应当等值）"
    )

    # --- 渠道 (b)：iframe 内 hover `<mark>` → 外层 tooltip ---------------------
    # 判别位 `data-annotation-id` 在 ADR-0014 的闭合清单内。这里其实只有一个 `<mark>`，
    # 带上判别位是为了让失败消息说清楚「是哪一条的高亮没出现」。
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    tooltip = page.get_by_test_id("rd-note-tooltip")
    assert tooltip.text_content() == "", (
        f"hover 之前 tooltip 就已经有文本 {tooltip.text_content()!r}——"
        "本条后面那句「hover 之后有文本」会因此恒真，先在这里拦下来"
    )
    mark.hover()
    # to_have_text 会等：`onHover` → `showTooltip` 是同步的，但 hover 本身要等元素稳定。
    expect(tooltip).to_have_text(W4_NOTE_TEXT)
    assert tooltip.text_content() == W4_NOTE_TEXT, (
        f"tooltip 的文本是 {tooltip.text_content()!r}，不是 {W4_NOTE_TEXT!r}。"
        "（通路：mark[data-note-text] → onHover → showTooltip；任一环断掉都落在这里）"
    )

    # --- 渠道 (a)：Notes 面板 -------------------------------------------------
    # 放在最后：面板是覆盖整屏的浮层，先开它会挡住上面那次 hover。
    page.get_by_test_id("rd-rail-notes").click()
    item = page.locator(f'[data-testid="rd-notes-item"][data-note-id="{note_id}"]')
    expect(item).to_contain_text(W4_NOTE_TEXT)
    # 面板条目同时展示引文，一并断掉：只断正文的话，「面板把每条都渲成同一段文字」这种
    # 坏法会绿——它在只有一条笔记时看不出来。
    expect(item).to_contain_text(CH0_QUOTE)


def test_w7_editing_a_note_changes_its_body_and_nothing_else(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-7（S5，**更新守恒律**）：改正文 → `id` / `created_at` / 基数 / 旁观条全不变。

    链路：预置两条同章标注 → 点 iframe 内目标 `<mark>` → `onAnnotationClick` →
    `openNoteEditorWithExisting`（置 `editingNoteId`）→ 改文本 → `rd-note-editor-primary`
    → `saveNote()` 的**更新**分支 → `PUT /api/notes/{book}/{chapter}/{id}` →
    `notes_service.update_annotation`。

    **旁观条断的是整字典等值，不是挑几个字段。**
    `assert after_bystander == before_bystander` —— 挑字段的写法（比对 id / quote / color
    …）会漏掉**下一个被加进 schema 的字段**：`Annotation` 今天有 13 个字段，012 还要动
    它。整字典等值不需要随 schema 演化而维护，这是它相对「更严」之外的第二个理由。

    **为什么旁观条是 marker 而不是第二条 note。** 两条都是 note 的话，
    `AnnotationRenderer.segmentStyle` 会给两个 `<mark>` 都挂上 `data-note-text`，
    「点中的是目标那条」与「点中的是旁观那条」在 DOM 上不再可分。type 不同则
    `onAnnotationClick` 里 `meta.find((item) => item.type === "note")` 的分支被真的走过一遍。

    **编辑态在这条路上不会被那个 ~250ms 自持循环打掉（2026-09-02 WI-5 实测）。**
    任务书 §0.6 担心的是：`select_in_frame` 返回后 `handleRenditionSelection` 会以
    ~250ms 一拍重新触发，而 `handleSelectionRange` 会把 `editingNoteId` 清成 null。
    实测在本条这条路上**循环根本没起来**——`openNoteEditorWithExisting` 末尾的
    `noteTextarea.focus()` 把焦点移出 iframe，iframe 内的选区当场折叠，而 epub.js 的
    `selected` 只在非折叠 range 上 emit。采样证据（rendition `selected` 事件 0 次、
    `lastSelectionAt` 恒 0、`editingNoteId` 2s 内恒为目标 id）记在
    `tests/e2e/helpers.py` 的 `select_in_frame` docstring 里，那里是这条时序事实的唯一
    定义处。**所以本条不加任何 sleep、不加重试、不需要新的 drain helper。**
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": W7_TARGET_ID,
                "chapter_index": 0,
                "type": "note",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "note_text": W7_OLD_BODY,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": W7_BYSTANDER_ID,
                "chapter_index": 0,
                "type": "marker",
                "color": "blue",
                "quote": W7_BYSTANDER_QUOTE,
                "created_at": "2026-01-01T00:00:01+00:00",
            },
        ],
    )
    before = _by_id(read_notes(e2e_books_dir, BOOK_ID))
    assert set(before) == {W7_TARGET_ID, W7_BYSTANDER_ID}, f"预置没落对：{before}"
    before_target = before[W7_TARGET_ID]

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    target_mark = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{W7_TARGET_ID}"]'
    )
    expect(target_mark).to_have_text(CH0_QUOTE)
    target_mark.click()

    # 编辑器带着**旧正文**打开，才说明走的是 `openNoteEditorWithExisting` 而不是
    # `openNoteEditor`。两者都会让编辑器可见，只有 textarea 的初值能把它们分开——
    # 而这正是 `editingNoteId` 有没有被置上的唯一可观测代理。
    editor_input = page.get_by_test_id("rd-note-editor-input")
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    expect(editor_input).to_have_value(W7_OLD_BODY)

    editor_input.fill(W7_NEW_BODY)
    page.get_by_test_id("rd-note-editor-primary").click()

    # 等在**被改的那个量**上。等条数在这里等不到任何东西：PUT 不改条数，
    # `wait_for_notes(..., 2)` 会在第一次轮询就带着旧正文返回（helpers 里写了理由）。
    wait_for_note_text(e2e_books_dir, BOOK_ID, W7_TARGET_ID, W7_NEW_BODY)

    # 往返收尾 + 「刷新后终态仍是恰好 2 条」。expected_count=2 是本条给出的等号右边，
    # 不是「至少 2 条」。
    record = assert_roundtrip(
        page,
        e2e_books_dir,
        BOOK_ID,
        CH0_QUOTE,
        CH0_ANCHOR,
        expected_type="note",
        expected_count=2,
    )
    assert record["id"] == W7_TARGET_ID, (
        f"往返回来的目标条 id 是 {record['id']!r}，不是预置的 {W7_TARGET_ID!r}——"
        "更新分支变成了「删了重建」"
    )

    after = _by_id(read_notes(e2e_books_dir, BOOK_ID))

    # (1) 基数不变
    assert len(after) == 2, f"编辑一条笔记之后不是 2 条，而是 {len(after)} 条：{after}"

    # (2) 目标条：内容变了，身份没变
    after_target = after[W7_TARGET_ID]
    assert after_target["note_text"] == W7_NEW_BODY, (
        f"目标条的 note_text 是 {after_target['note_text']!r}，不是 {W7_NEW_BODY!r}"
    )
    assert after_target["id"] == before_target["id"], (
        f"目标条的 id 变了：{before_target['id']!r} → {after_target['id']!r}（删了重建？）"
    )
    assert after_target["created_at"] == before_target["created_at"], (
        f"目标条的 created_at 变了：{before_target['created_at']!r} → "
        f"{after_target['created_at']!r}。改内容不该重置创建时间——这是「DELETE + POST」"
        "那个坏实现唯一藏不住的地方"
    )

    # (3) 旁观条：整字典逐字段相等。走共用 helper 而不是就地写一行 `assert a == b`——
    #     漏写这条判据**不会红**，所以它必须机器可查，而机器只认得一个共用的名字
    #     （`tests/unit/test_e2e_bystander_discipline.py`：凡传 expected_count > 1 的模块
    #     必须调用它至少一次）。就地 assert 是 grep 不到的。
    assert_bystanders_unchanged(
        list(before.values()), list(after.values()), changed_ids={W7_TARGET_ID}
    )

    # (4) 旁观条的高亮还在 iframe 里，且覆盖的仍是它自己那段文字
    bystander_mark = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{W7_BYSTANDER_ID}"]'
    )
    expect(bystander_mark).to_have_text(W7_BYSTANDER_QUOTE)

    # (5) Notes 面板读回新值。面板是另一个端点（`GET /api/notes/{book}`）、另一套摘要
    # 逻辑，盘上对了不代表这里对。放最后，理由同 W-4：它是覆盖整屏的浮层。
    page.get_by_test_id("rd-rail-notes").click()
    item = page.locator(f'[data-testid="rd-notes-item"][data-note-id="{W7_TARGET_ID}"]')
    expect(item).to_contain_text(W7_NEW_BODY)
    assert W7_OLD_BODY not in (item.text_content() or ""), (
        f"Notes 面板里还留着旧正文 {W7_OLD_BODY!r}：{item.text_content()!r}"
    )
