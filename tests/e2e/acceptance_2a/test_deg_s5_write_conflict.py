"""WI-17 —— DEG-S5：notes 写冲突时**明确提示、二选一、不得静默丢写**（`acceptance_2a`，skip，一条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「DEG-S5」。任务书 §7「DEG-S5 写冲突 UI
—— 随 Phase 2a」、§0.5 表（激活阶段 = **Phase 2a**，与 notes 乐观并发同批）。设计规格 §6.4 DEG-S5 行：
「冲突提示 + 『保留我的 / 采用远端』二选一，**不得静默丢写**。这是唯一一条会真正丢用户数据的降级」；
§6.4 设计要求 2（`role="alertdialog"`）与 3（**DEG-S5 不可关闭**——必须做出选择）。前端计划 WI-6
「DEG-S5 写冲突对话框」的 testid 与验收（零关闭路径、Esc 不关、遮罩不关、本地改动任一分支都不丢）。

**冲突怎么制造**：两个浏览器上下文 A、B 对同一本书同一章同一条笔记做「读 → 改 → 写」，让 B 拿着过期版本写。

1. A 建一条 note（正文 `NOTE_A0`），落库 1 条，记 id。
2. B 打开同一章（此时 B 读到的是 A0 版本，随后 B 不再刷新）。
3. A 把该条改成 `NOTE_A1` 并保存 ⇒ 服务端版本前进。
4. B 拿着过期版本把同一条改成 `NOTE_B` 并保存 ⇒ 乐观并发拒绝 ⇒ B 看到冲突对话框。

**两个出口各跑一场全新的冲突。** 原先只跑「保留我的」，「采用远端」只被 `to_have_count(1)`
**数了一下**——一个没接处理器的按钮、或一个接错了、把本地改动悄悄丢掉的处理器，都能让那条断言
通过。而「采用远端」恰恰是这条降级里唯一会**按用户意愿**丢弃一版文本的分支：它没被走过一遍，
等于 DEG-S5 的一半从来没有规格。现在 `CONFLICT_BRANCHES` 里每一支各造一场冲突，跑完把那条笔记
从 UI 上删掉（`wait_for_notes(..., 0)`），下一支从空盘重新开始——**不是接着上一场的残局**。

**为什么是一个 `for` 而不是 `parametrize`。** 组条数是划分律的一部分：
`scripts/lint_e2e_groups.py` 的 `EXPECTED_ACCEPTANCE_PER_DIR["acceptance_2a"] == 1`，参数化会
把它变成 2，而那个常量同时被守卫与台账消费。判据的强度不该靠改条数常量买。

**断言分五段**（每一支各来一遍）：(a) 对话框形态——`role=alertdialog`、两个出口各恰好一个、
没有关闭按钮、Esc 与遮罩点击都关不掉；(a′) **两版正文都摆在对话框里**——「不得静默丢写」的
可观测面是：被放弃的那一版必须先让用户看见；(b) **对话框开着的时候盘上仍是 A1**（B 的写没有
静默盖掉 A 的，A 的也没有被 B 的覆盖）；(c) 点下那一支之后：对话框消失、盘上变成该支承诺的那
一版、仍是同一条 id、总数仍为 1；(d) **本地那版的去向由该支的承诺决定**——「保留我的」必须真的
发出一次带本地正文的写请求（只关对话框、不写服务端的实现，会在下一次刷新时把用户的字变回远端版，
而那正是静默丢写），「采用远端」则**一条带本地正文的写都不许有**（本地那版是被放弃的，不是被
再写一遍）；(d′) **不刷新**，B 的界面此刻就得是该支承诺的那一版——「采用远端」不写盘，所以盘上
那条判据对「只关了个对话框」的实现是空的，活性只能从 B 自己的视图上看；(e) 刷新之后两个上下文
看到的也都是该支承诺的那一版。

**为什么第二个上下文要自己装一遍出网闸。** `conftest.context` 那个 fixture 只作用于 pytest-playwright
给的那一个 context；`browser.new_context()` 造出来的第二个没有它，`reader.html` 头部那组 Google Fonts
`<link>` 会让 `load` 事件挂满 30s。所以这里对第二个 context 复刻同一条规则（非本机 http(s) 一律 abort）。

**今天为什么必须 skip**：`notes_service` 是 load → 改 → 整章回写，没有版本号、没有 409、没有对话框——B 的
写会**静默覆盖** A1，(b) 红在「盘上是 B 不是 A1」。这正是 DEG-S5 要消灭的那种坏法，2a 落地乐观并发之前
它是事实，不是缺陷报告。

**解 skip 的顺序**：2a 落地 notes 乐观并发（版本号 / 409）与 `ConflictDialog` ⇒ 核对三个 testid ⇒
删本文件 skip 行 ⇒ `-m acceptance_2a`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, NamedTuple, Sequence
from urllib.parse import urlparse

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Request,
    expect,
)

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_INDEX,
    CH0_QUOTE,
    open_ch0,
    open_reader_settled,
    read_notes,
    select_in_frame,
    wait_for_note_text,
    wait_for_notes,
)

pytestmark = [
    pytest.mark.acceptance_2a,
]

#: 三个版本的笔记正文，全是字面量；三者两两不同，否则「谁盖了谁」不可判定。
NOTE_A0 = "A 的初稿"
NOTE_A1 = "A 的修订版"
NOTE_B = "B 基于初稿的修改"

#: 前端计划 WI-6 的三个 testid。关闭按钮按 Modal 的通式 `*-close`——它**必须不存在**。
DIALOG_TESTID = "rd-conflict-dialog"
KEEP_MINE_TESTID = "rd-conflict-keep-mine"
TAKE_REMOTE_TESTID = "rd-conflict-take-remote"
CLOSE_TESTID = "rd-conflict-dialog-close"

#: 键名放在变量里，而不是内联成字面量实参：选择器 lint 的 LOCATOR_CALL_RE 扫的是原始文本，
#: `keyboard` 的按键调用一旦直接跟一个字符串字面量，就会被当成一处选择器扫到并报「含非
#: data-* 属性选择器的部分」。那是误报，但放行它要写一条 allow 注释；换成常量则连误报都没有。
#: 同理，本行以上不得复写那个调用的字面形态——注释里的写法一样会被正则扫到。
ESCAPE_KEY = "Escape"

#: 同上，`.get_attribute(...)` 的实参也会被那条正则扫成选择器，所以属性名与取值也走常量。
EDITOR_TESTID = "rd-note-editor"
ARIA_HIDDEN_ATTR = "aria-hidden"
ARIA_SHOWN = "false"

#: 冲突前后该章都应恰好一条——字面量基准。
EXPECTED_NOTE_COUNT = 1

#: 一轮跑完把这条笔记删干净；下一支从空盘重新造一场冲突，不接上一场的残局。
EMPTY_NOTE_COUNT = 0

#: 判「本地那版有没有真的被写到服务端」时认哪些请求。方法集合取宽而不取窄：
#: 该判据要区分的是「发没发出带本地正文的写」，不是「用了哪个动词」——把动词钉死会
#: 让一个用 PATCH 实现的重试从判据里漏过去。
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
NOTES_API_FRAGMENT = "/api/notes"


class ConflictBranch(NamedTuple):
    """冲突对话框的一个出口，连同它对用户作出的**承诺**。

    两支的差别只有「谁活下来」与「本地那版该不该被写出去」，其余（形态、不可关闭、
    冲突期间盘上仍是 A1、选完之后条数与 id 不变）两支逐字相同——所以它们共用
    `_run_conflict_round`，而不是各写一遍。
    """

    #: 失败消息里的短名，用规格里的中文原词，出错时不用回来查 testid 对应哪一支。
    key: str
    #: 出口按钮的 testid。
    exit_testid: str
    #: 选完这一支之后盘上该是哪一版正文。
    settled_text: str
    #: 该支是否承诺保住本地那版。决定「带本地正文的写请求」该有还是**一条都不许有**。
    keeps_local: bool


#: 顺序有意：先跑保守的那支（保留我的），再跑会丢弃一版文本的那支（采用远端）。
#: 前者失败时后者的结论没意义，先跑的失败消息更靠近根因。
CONFLICT_BRANCHES = (
    ConflictBranch("保留我的", KEEP_MINE_TESTID, NOTE_B, True),
    ConflictBranch("采用远端", TAKE_REMOTE_TESTID, NOTE_A1, False),
)

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@pytest.fixture
def other_context(browser: Browser) -> Iterator[BrowserContext]:
    """第二个浏览器上下文（用户 B），带与 `conftest.context` 同款的出网闸。"""
    ctx = browser.new_context()

    def _gate(route, request) -> None:  # type: ignore[no-untyped-def]
        parsed = urlparse(request.url)
        if parsed.scheme not in ("http", "https") or parsed.hostname in _LOCAL_HOSTS:
            route.continue_()
        else:
            route.abort()

    ctx.route("**/*", _gate)
    try:
        yield ctx
    finally:
        ctx.close()


def _click_awaiting_write(page: Page, locator, what: str) -> None:  # type: ignore[no-untyped-def]
    """点下去，并且**先把这次写的响应等到手**，再让调用方去轮询磁盘。

    `wait_for_notes()` / `wait_for_note_text()` 是纯 Python 的 sleep 轮询：整个窗口里一次都
    没调进 Playwright。而同步 Playwright 的 route 回调是 Python 函数，只在主协程调进
    Playwright 时才被派发——`conftest` 给每个 context 都挂了一道 `**/*` 的出网闸，于是
    **每一个**请求都要过这样一个回调。点完按钮直接去轮盘，这次写就卡在回调上跑不动，
    轮询等满超时：**产品行为完全正确也会红**。这正是 #43 那族 flake 的机制（审计 #8）。

    这里刻意不限定方法名：从这个按钮出去的、发往 notes API 的那次写就是「相关的写」，
    把它写死成 POST/PUT 只会在实现换方法时把一条真断言变成挂死。
    """
    try:
        with page.expect_response(
            lambda r: r.request.method.upper() in WRITE_METHODS and NOTES_API_FRAGMENT in r.url
        ):
            locator.click()
    except PlaywrightError as exc:
        raise AssertionError(
            f"{what}：点下去之后没等到发往 {NOTES_API_FRAGMENT} 的写响应"
            f"（{type(exc).__name__}）——这一步没把用户的字交到服务端"
        ) from None


def _open_note_editor_on_mark(page: Page, frame, note_id: str) -> None:  # type: ignore[no-untyped-def]
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)
    mark.click()
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_have_attribute("aria-hidden", "false")


def _writes_carrying(requests: Sequence[Request], text: str) -> List[str]:
    """`requests` 里**带着 `text` 正文发往 notes API 的写**，返回 `METHOD url` 便于打印。

    判「本地那版有没有到服务端」只能看这个：对话框关掉、盘上变成 B，这两件事一个
    乐观地只改前端内存的实现也做得到，下一次刷新才把用户的字变回远端版——那正是
    「静默丢写」的实际形状，而它发生在断言之后。
    """
    hits: List[str] = []
    for request in requests:
        if request.method.upper() not in WRITE_METHODS:
            continue
        if NOTES_API_FRAGMENT not in request.url:
            continue
        if text in (request.post_data or ""):
            hits.append(f"{request.method} {request.url}")
    return hits


def _run_conflict_round(
    page: Page,
    page_b: Page,
    live_server: str,
    books_dir: Path,
    branch: ConflictBranch,
) -> None:
    """造一场全新的冲突，走 `branch` 这个出口，跑完把笔记删回空盘。"""
    assert read_notes(books_dir, BOOK_ID) == [], (
        f"「{branch.key}」这一轮的起点不是空的：上一轮的清场没做干净，"
        f"后面「盘上是谁」的判据会被残局污染"
    )

    # ---- 1. A 建一条 note ------------------------------------------------------------------
    frame_a = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame_a, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()
    page.get_by_test_id("rd-note-editor-input").fill(NOTE_A0)
    _click_awaiting_write(page, page.get_by_test_id("rd-note-editor-primary"), "A 建 A0")
    records = wait_for_notes(books_dir, BOOK_ID, EXPECTED_NOTE_COUNT)
    note_id = str(records[0]["id"])
    assert records[0]["note_text"] == NOTE_A0

    # ---- 2. B 打开同一章，读到 A0 版本，此后不再刷新 ------------------------------------------
    frame_b = open_reader_settled(
        page_b, live_server, BOOK_ID, CH0_INDEX, CH0_ANCHOR, expected_marks=1
    )

    # ---- 3. A 改成 A1 并保存（服务端版本前进）------------------------------------------------
    frame_a = open_ch0(page, live_server, expected_marks=1)
    _open_note_editor_on_mark(page, frame_a, note_id)
    page.get_by_test_id("rd-note-editor-input").fill(NOTE_A1)
    _click_awaiting_write(page, page.get_by_test_id("rd-note-editor-primary"), "A 改成 A1")
    wait_for_note_text(books_dir, BOOK_ID, note_id, NOTE_A1)

    # ---- 4. B 拿着过期版本写 B ⇒ 冲突 -------------------------------------------------------
    _open_note_editor_on_mark(page_b, frame_b, note_id)
    page_b.get_by_test_id("rd-note-editor-input").fill(NOTE_B)
    page_b.get_by_test_id("rd-note-editor-primary").click()

    dialog = page_b.get_by_test_id(DIALOG_TESTID)
    expect(dialog).to_be_visible()

    # (a) 形态：alertdialog、两个出口各一、零关闭路径。
    expect(dialog).to_have_attribute("role", "alertdialog")
    expect(dialog.get_by_test_id(KEEP_MINE_TESTID)).to_have_count(1)
    expect(dialog.get_by_test_id(TAKE_REMOTE_TESTID)).to_have_count(1)
    expect(dialog.get_by_test_id(CLOSE_TESTID)).to_have_count(0)
    page_b.keyboard.press(ESCAPE_KEY)
    expect(dialog).to_be_visible()
    page_b.mouse.click(2, 2)  # 视口左上角：对话框之外的遮罩区域
    expect(dialog).to_be_visible()

    # (a′) 两版正文都摆在对话框里。「不得静默丢写」的可观测面就是这一条：无论用户选哪一支，
    #      被放弃的那一版必须**先让他看见**——只写「有冲突，二选一」而不显示内容的对话框，
    #      是在让人闭着眼睛丢自己的字。
    dialog_text = dialog.inner_text()
    assert NOTE_B in dialog_text, f"对话框里没有本地那版 {NOTE_B!r}：{dialog_text!r}"
    assert NOTE_A1 in dialog_text, f"对话框里没有远端那版 {NOTE_A1!r}：{dialog_text!r}"

    # (b) 对话框开着时，盘上仍是 A1：B 的过期写没有静默盖掉它，A 的也没有被丢。
    on_disk = read_notes(books_dir, BOOK_ID)
    assert len(on_disk) == EXPECTED_NOTE_COUNT, f"冲突期间条数变了：{on_disk}"
    assert on_disk[0]["id"] == note_id
    assert on_disk[0]["note_text"] == NOTE_A1, (
        f"对话框开着时盘上已经是 {on_disk[0]['note_text']!r}，期望仍是 {NOTE_A1!r}"
        "——过期写被静默接受了（last-write-wins）"
    )

    # (c)(d) 点这一支。点之前挂上请求监听：这一支到底有没有把本地那版写出去，
    #        是它与「只关了个对话框」的唯一分辨点。
    issued: List[Request] = []

    def _record(request: Request) -> None:
        issued.append(request)

    page_b.on("request", _record)
    try:
        dialog.get_by_test_id(branch.exit_testid).click()
        expect(dialog).to_be_hidden()
        final = wait_for_note_text(books_dir, BOOK_ID, note_id, branch.settled_text)
    finally:
        page_b.remove_listener("request", _record)

    assert final["id"] == note_id, (
        f"「{branch.key}」之后 id 变了：{final['id']!r} != {note_id!r}"
        "——更新被实现成了删了重建，引用这条笔记的一切（书签、导出）都断了"
    )
    settled = read_notes(books_dir, BOOK_ID)
    assert len(settled) == EXPECTED_NOTE_COUNT, (
        f"「{branch.key}」之后条数不是 {EXPECTED_NOTE_COUNT}：{settled}"
    )
    assert [r["note_text"] for r in settled] == [branch.settled_text]

    # (d) 本地那版的去向，由这一支的承诺决定，两个方向都断。
    local_writes = _writes_carrying(issued, NOTE_B)
    if branch.keeps_local:
        assert local_writes, (
            f"点了「{branch.key}」却没有任何一条带 {NOTE_B!r} 的写请求发往 {NOTES_API_FRAGMENT}"
            "：这一支承诺保住本地改动，就必须真的重试到服务端。只改前端内存、只关对话框的"
            f"实现，会在下一次刷新时把用户的字变回 {NOTE_A1!r}——盘上此刻恰好是 B，"
            "只说明这次断言早于那次刷新。"
        )
    else:
        assert not local_writes, (
            f"点了「{branch.key}」却把本地那版写了出去：{local_writes}。"
            "这一支的语义是**放弃**本地改动、采用远端，不是再写一遍——"
            "一个会写的实现说明这个按钮接错了处理器。"
        )

    # (d′) **不刷新**，B 自己的界面此刻就必须是这一版。这一条是「采用远端」唯一的活性判据：
    #      一个只把对话框关掉、内存里仍留着被放弃那版的实现，盘上恰好是对的（这一支本就不写盘），
    #      刷新之后更看不出来——露馅要等到 B 下一次保存，把那版又推上去，而那时用户以为自己
    #      早就放弃了它。所以断在刷新之前。
    if page_b.get_by_test_id(EDITOR_TESTID).get_attribute(ARIA_HIDDEN_ATTR) != ARIA_SHOWN:
        _open_note_editor_on_mark(page_b, frame_b, note_id)
    expect(page_b.get_by_test_id("rd-note-editor-input")).to_have_value(branch.settled_text)

    # (e) 刷新之后两个上下文看到的也都是这一版；顺便把笔记删掉，给下一支清场。
    frame_b = open_reader_settled(
        page_b, live_server, BOOK_ID, CH0_INDEX, CH0_ANCHOR, expected_marks=1
    )
    _open_note_editor_on_mark(page_b, frame_b, note_id)
    expect(page_b.get_by_test_id("rd-note-editor-input")).to_have_value(branch.settled_text)

    frame_a = open_ch0(page, live_server, expected_marks=1)
    mark = frame_a.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)

    mark.click()
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    _click_awaiting_write(page, page.get_by_test_id("rd-anno-delete"), "清场删除")
    wait_for_notes(books_dir, BOOK_ID, EMPTY_NOTE_COUNT)


def test_deg_s5_concurrent_note_edit_shows_conflict_dialog_and_loses_nothing(
    page: Page, other_context: BrowserContext, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S5（S3 / L2）：过期版本的写被拒 ⇒ alertdialog、两个出口、不可关闭；盘上仍是最新版；**两个出口各走一遍全新的冲突**，每一支都要兑现它对本地那版的承诺。"""
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    page_b = other_context.new_page()
    for branch in CONFLICT_BRANCHES:
        _run_conflict_round(page, page_b, live_server, e2e_books_dir, branch)
