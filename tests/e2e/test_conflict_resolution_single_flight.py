"""017 WI-6（审计 #5）——冲突对话框同一时刻只许有一次收尾在飞。

**缺陷**：`annotations.js` 的 `resolveConflict()` 在「保留我的」那次 PUT 还没回来时，
两个出口按钮都还能点。点「采用远端」会**立刻** `settleConflict(c, c.remoteText)`
收尾，而那个还在飞的 PUT 回来之后仍然走到 `settleConflict(c, c.localText)`——
把用户**最后**作出的选择反了过来。用户看见的顺序是「我选了远端 → 界面变成远端 →
界面自己又变回本地」，而盘上是本地那版。DEG-S5 的承诺是「二选一，选完算数」，
这条路径让「算数」失效；再点一次「保留我的」还会再发一次写。

**修法三层，各自独立**：

1. `setConflictBusy(true)` 把两个出口一起 `disabled`——把「点不动」摆到屏幕上，
   这是给人看的那一层。
2. `resolveConflict()` 开头的单飞守卫（`conflictSubmitting`）——按钮的 `disabled`
   是一条 DOM 属性，任何一次重绘、任何一个绕过按钮的调用（`Reader3AnnotationUI
   .resolveConflict(...)` 是公开的）都能越过它；守卫在函数里，越不过去。
3. 写回来之后的**身份核对**（`this.pendingConflict !== c`）——一次回调只能收尾
   它当初出发时的那一场冲突。前两层挡的是「新的调用进不来」，这一层挡的是
   「回来的这一次还能不能算数」，方向相反，谁也替不了谁。

**四条用例按「拆掉一层，看下一层接不接得住」排**：第 1 条只用第 1 层（按钮真的
`disabled`）；第 2 条**在页面里把 `disabled` 抹掉**再点——第 1 层被拆了，断的是
第 2 层；第 3 条把 `pendingConflict` 换掉——前两层都不参与，断的是第 3 层；
第 4 条是护栏：没有并发干扰时，「保留我的」必须照旧写盘、照旧收尾、按钮照旧放开，
否则「全程 disabled、永不收尾」也能让前三条全绿。

**冲突是真的，不是桩的。** 409 由服务端的乐观并发真发出来：页面加载时客户端拿到
版本 v1，随后本测试用 `page.request` 绕过页面直接写一次（`If-Match` 可选，这一写
被接受），服务端版本前进到 v2；页面再拿着 v1 保存就撞上真的 409，响应体就是
`routers/notes.py::_conflict` 那一份。**被桩住的只有「写请求什么时候回来」**——
`notes_conflict_support.install_put_gate()` 在页面里把 `window.fetch` 上发往 notes 的 PUT 扣住，等测试
调 `release_put()` 才放它去走真正的 `fetch`。扣住请求是这条缺陷**唯一**的观察窗：
不把那次写停在半空，「在飞期间点另一个按钮」这件事根本没有时间发生。

**为什么不用两个浏览器上下文**（`acceptance_2a/test_deg_s5_write_conflict.py` 那样）：
那一条测的是「服务端会不会 409、对话框形态对不对、两支的去向对不对」，需要两个真
用户；本文件测的是同一个用户在**一个**对话框上的两次点击之间发生了什么，第二个
上下文只会带来无关的时序。

**造冲突、扣写的那些手脚住在 `notes_conflict_support.py`**（非 `test_` 开头，不贡献
item），与 WI-7 的 `test_conflict_settled_text_keeps_its_base_etag.py` 共用；判据只在本文件。

**落址：白名单，不是 `baseline_1b`**（同 WI-5）。迁进冻结目录会改 `suite_hash`
并把 soak 计数清零。到期条件：下一次本来就要动 `baseline_1b/` 的改动里一并迁入，
同批撤掉 `UNGROUPED_E2E_MODULES` 里的条目并把条数加进 `EXPECTED_BASELINE_ITEMS`。
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import wait_for_note_text  # type: ignore[import-not-found]
from notes_conflict_support import (  # type: ignore[import-not-found]
    DIALOG_TESTID,
    KEEP_MINE_TESTID,
    NOTE_LOCAL,
    TAKE_REMOTE_TESTID,
    diag_ops,
    editor_text,
    enable,
    held_writes,
    install_put_gate,
    open_conflict,
    release_put,
    set_editor_text,
    wait_for_held_write,
)

#: 写进 textarea 的哨兵：只要收尾真的执行过，它就会被 `c.localText` 盖掉。
SENTINEL = "哨兵：这串字只有收尾被执行时才会消失"

#: 诊断环里这两个 op 是本条缺陷的两处拒绝点，见模块文档的第 2、3 层。
OP_BUSY = "conflict-busy"
OP_STALE = "conflict-stale"

#: 一场收尾**只许**有一次写在飞。
EXPECTED_INFLIGHT_WRITES = 1


def test_保留我的还在飞时两个出口都不可点(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """第 1 层：提交期间两个按钮都 `disabled`，放行之后又都放开。"""
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id
    install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    wait_for_held_write(page)

    expect(page.get_by_test_id(KEEP_MINE_TESTID)).to_be_disabled()
    expect(page.get_by_test_id(TAKE_REMOTE_TESTID)).to_be_disabled()

    release_put(page)
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert editor_text(page) == NOTE_LOCAL


def test_就算按钮被重新启用在飞期间的第二次点击也一次都不算(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """第 2 层：`disabled` 被抹掉之后，守卫仍然挡住重复点击与另一个出口。

    这条同时钉住两件事：再点「保留我的」**不许**再发一次写；点「采用远端」不许
    在别人还在飞的时候把冲突收掉——缺陷态下正是这一下让用户的选择被反转。
    """
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id
    install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    wait_for_held_write(page)

    enable(page, KEEP_MINE_TESTID)
    enable(page, TAKE_REMOTE_TESTID)
    page.get_by_test_id(KEEP_MINE_TESTID).click()
    page.get_by_test_id(TAKE_REMOTE_TESTID).click()

    assert held_writes(page) == EXPECTED_INFLIGHT_WRITES, (
        f"在飞期间又发出了写：闸上扣住 {held_writes(page)} 次，"
        f"期望 {EXPECTED_INFLIGHT_WRITES} 次"
    )
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_visible()
    ops = diag_ops(page)
    assert ops.count(OP_BUSY) == 2, f"两次被拒的点击没有各留一条 {OP_BUSY}：{ops}"

    release_put(page)
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert editor_text(page) == NOTE_LOCAL, (
        "在飞期间那次「采用远端」把冲突收掉了，界面落在远端那版——"
        "用户点下「保留我的」之后的写反而不算数了"
    )


def test_回来的写属于已经过期的冲突时不许再收尾(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """第 3 层：出发时的那场冲突已经不在了，回来的这一次只记账，不碰界面。

    前两层挡的是「新的调用进不来」，挡不住「回来的这一次」。这里把
    `pendingConflict` 换掉（任何一条未来会在写飞行期间清空或替换它的路径都长这样），
    再放行：收尾若照旧执行，`settleConflict()` 会用 `c.localText` 盖掉 textarea，
    哨兵就没了。盘上仍是本地那版——那次写**确实**落地了，我们拒绝的是替它宣告收尾，
    不是假装它没发生。
    """
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id
    install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    wait_for_held_write(page)

    page.evaluate("() => { window.Reader3AnnotationUI.pendingConflict = null; }")
    set_editor_text(page, SENTINEL)

    release_put(page)
    page.wait_for_function(
        """(op) => (window.Reader3NotesDiag?.entries?.() || []).some((e) => e.op === op)""",
        arg=OP_STALE,
    )

    assert editor_text(page) == SENTINEL, (
        "一次属于已过期冲突的回调仍然收了尾，把编辑器里的字盖掉了"
    )
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)


def test_没有并发干扰时保留我的照旧写盘收尾并放开按钮(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """护栏：单飞不许买成「永远在飞」。

    前三条全是「某一次点击**不**生效」，一个把两个按钮永久 `disabled`、永不收尾的
    实现能让它们全绿。这一条反过来钉住正常那条路：一次「保留我的」必须真的写盘、
    关对话框、把本地那版放回编辑器，并且把两个出口**放开**——下一场冲突还要用它们。
    """
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id

    page.get_by_test_id(KEEP_MINE_TESTID).click()

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert editor_text(page) == NOTE_LOCAL

    expect(page.get_by_test_id(KEEP_MINE_TESTID)).to_be_enabled()
    expect(page.get_by_test_id(TAKE_REMOTE_TESTID)).to_be_enabled()

    ops = diag_ops(page)
    assert OP_BUSY not in ops and OP_STALE not in ops, (
        f"没有并发干扰的一次收尾却报了守卫：{ops}"
    )
