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
`_install_put_gate()` 在页面里把 `window.fetch` 上发往 notes 的 PUT 扣住，等测试
调 `_release_put()` 才放它去走真正的 `fetch`。扣住请求是这条缺陷**唯一**的观察窗：
不把那次写停在半空，「在飞期间点另一个按钮」这件事根本没有时间发生。

**为什么不用两个浏览器上下文**（`acceptance_2a/test_deg_s5_write_conflict.py` 那样）：
那一条测的是「服务端会不会 409、对话框形态对不对、两支的去向对不对」，需要两个真
用户；本文件测的是同一个用户在**一个**对话框上的两次点击之间发生了什么，第二个
上下文只会带来无关的时序。

**落址：白名单，不是 `baseline_1b`**（同 WI-5）。迁进冻结目录会改 `suite_hash`
并把 soak 计数清零。到期条件：下一次本来就要动 `baseline_1b/` 的改动里一并迁入，
同批撤掉 `UNGROUPED_E2E_MODULES` 里的条目并把条数加进 `EXPECTED_BASELINE_ITEMS`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    open_reader,
    read_notes,
    seed_notes,
    wait_for_note_text,
)

#: 三版正文，两两不同——否则「最后留下的是谁」不可判定。
NOTE_BASE = "起点：两边都从这一版出发"
NOTE_REMOTE = "远端那版（由旁路写入，服务端版本因此前进）"
NOTE_LOCAL = "本地那版（用户在编辑器里改的，还没写出去）"

#: 第 3 条用例往编辑器里塞的哨兵。它的唯一用处是**证否**：一次属于过期冲突的回调
#: 若还去收尾，`settleConflict()` 会拿 `c.localText` 覆盖 textarea，哨兵就没了。
SENTINEL = "哨兵：这一格不许被过期的回调覆盖"

DIALOG_TESTID = "rd-conflict-dialog"
KEEP_MINE_TESTID = "rd-conflict-keep-mine"
TAKE_REMOTE_TESTID = "rd-conflict-take-remote"
EDITOR_INPUT_TESTID = "rd-note-editor-input"

#: 诊断环（`window.Reader3NotesDiag`）里这两个 op。它们是「拒绝」与「丢弃」这两件
#: 事**唯一**留得下痕迹的地方：两者都不改屏幕，只看 DOM 是分不出「守卫挡住了」和
#: 「代码压根没跑到」的。
OP_BUSY = "conflict-busy"
OP_STALE = "conflict-stale"

#: 单飞的全部意义：在飞期间无论点多少次，发出去的写**恰好一次**。
EXPECTED_INFLIGHT_WRITES = 1


def _seed_note(books_dir: Path) -> str:
    """预置一条带正文的 note，返回它的 id。"""
    seed_notes(
        books_dir,
        BOOK_ID,
        [
            {
                "chapter_index": 0,
                "type": "note",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "prefix": "",
                "suffix": ".",
                "position": 0,
                "note_text": NOTE_BASE,
            }
        ],
    )
    (landed,) = read_notes(books_dir, BOOK_ID)
    return str(landed["id"])


def _pin_if_match(page: Page, etag: str) -> None:
    """把**下一次** notes PUT 的 `If-Match` 钉成 `etag`，然后自己下岗。

    为什么需要这一手：客户端的版本号是**事件驱动**刷新的（`reader3:content:rendered`
    等三个事件 → 80ms 去抖 → 重新 GET notes → 吸收新 ETag）。旁路写之后若恰好有一次
    这样的刷新落下来，客户端就学到了新版本，保存不再冲突，对话框不出现——实测
    连跑两遍，一遍造出了冲突，一遍四条用例全卡在「对话框没出现」。那是**时序**决定的，
    与本文件要测的东西无关，却会把它变成一个掷硬币的用例。

    钉住的只是「客户端出发时手里是哪一版」，**不是**冲突本身：409 仍由服务端的乐观
    并发真发出来，响应体仍是 `routers/notes.py::_conflict` 那一份。而且钉之前先把
    客户端自己带的那个值记下来（`sawClientEtag`），调用方会断言它非空——客户端**确实**
    在参与乐观并发，这一点不许被这道稳定化手脚糊掉。

    「客户端带的 If-Match 对不对」是 `acceptance_2a/test_deg_s5_write_conflict.py`
    的判据，那条用两个真上下文跑，不在本文件的射程里。
    """
    page.evaluate(
        """(etag) => {
          const real = window.fetch.bind(window);
          const pin = { etag: etag, armed: true, sawClientEtag: null };
          window.__r3PinIfMatch = pin;
          window.fetch = function (input, init) {
            const url = String((input && input.url) || input || "");
            const method = String((init && init.method) || "GET").toUpperCase();
            if (pin.armed && method === "PUT" && url.includes("/api/notes/") && init && init.headers) {
              pin.sawClientEtag = init.headers["If-Match"] ?? null;
              init.headers["If-Match"] = pin.etag;
              pin.armed = false;
            }
            return real(input, init);
          };
        }""",
        etag,
    )


def _open_conflict(page: Page, live_server: str, books_dir: Path) -> str:
    """造一场**真的** 409 并把对话框开在屏幕上，返回那条 note 的 id。

    步骤与 DEG-S5 同构，只是「另一个用户」换成了一次绕过页面的 API 写：
    读到版本 v1 → 旁路写把服务端推到 v2 → 页面拿着 v1 保存 ⇒ 服务端 409。

    旁路写必须发生在**编辑器已经打开之后**：打开编辑器只点 DOM，不重新拉 notes。
    而「页面手里仍是 v1」这件事由 `_pin_if_match` 钉住，理由见那个函数。
    """
    note_id = _seed_note(books_dir)
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)
    mark.click()
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_have_attribute("aria-hidden", "false")

    chapter_url = f"{live_server}/api/notes/{BOOK_ID}/0"
    before = page.request.get(chapter_url)
    assert before.ok, f"读不到当前版本（{before.status}）"
    base_etag = before.headers.get("etag")
    assert base_etag, f"GET notes 没带 ETag，乐观并发的前提就不成立：{before.headers}"

    bypass = page.request.put(
        f"{chapter_url}/{note_id}",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"note_text": NOTE_REMOTE}),
    )
    assert bypass.ok, f"旁路写没成功（{bypass.status}），服务端版本没前进，造不出冲突"
    wait_for_note_text(books_dir, BOOK_ID, note_id, NOTE_REMOTE)

    _pin_if_match(page, base_etag)
    page.get_by_test_id(EDITOR_INPUT_TESTID).fill(NOTE_LOCAL)
    page.get_by_test_id("rd-note-editor-primary").click()

    dialog = page.get_by_test_id(DIALOG_TESTID)
    expect(dialog).to_be_visible()
    saw = page.evaluate("() => window.__r3PinIfMatch.sawClientEtag")
    assert isinstance(saw, str) and saw, (
        "那次保存自己没带 If-Match——客户端没在参与乐观并发，"
        "这场 409 是被钉出来的，不作数"
    )
    assert NOTE_LOCAL in dialog.inner_text(), "对话框里没有本地那版，冲突造歪了"
    assert NOTE_REMOTE in dialog.inner_text(), "对话框里没有远端那版，冲突造歪了"
    return note_id


def _install_put_gate(page: Page) -> None:
    """把发往 notes 的 PUT 扣在半空：记下来，等 `_release_put()` 才真发。

    扣住的那次调用返回一个**永不自己落地**的 Promise，所以 `resolveConflict()` 停在
    `await` 上——这正是缺陷所在的那个窗口。放行时走的是原来的 `fetch`，拿回来的是
    一个真的 `Response`（`resp.ok` / `ETag` 都是真的），因此放行之后的路径一字未改。
    """
    page.evaluate(
        """() => {
          const real = window.fetch.bind(window);
          const gate = { held: [], release: null, released: 0 };
          window.__r3PutGate = gate;
          window.fetch = function (input, init) {
            const url = String((input && input.url) || input || "");
            const method = String((init && init.method) || (input && input.method) || "GET");
            if (url.includes("/api/notes/") && method.toUpperCase() === "PUT") {
              gate.held.push(url);
              return new Promise((resolve, reject) => {
                gate.release = () => {
                  gate.released += 1;
                  real(input, init).then(resolve, reject);
                };
              });
            }
            return real(input, init);
          };
        }"""
    )


def _held_writes(page: Page) -> int:
    return int(page.evaluate("() => (window.__r3PutGate?.held || []).length"))


def _wait_for_held_write(page: Page) -> None:
    page.wait_for_function("() => (window.__r3PutGate?.held || []).length > 0")


def _release_put(page: Page) -> None:
    released = page.evaluate(
        """() => {
          const gate = window.__r3PutGate;
          if (!gate || typeof gate.release !== "function") return false;
          gate.release();
          return true;
        }"""
    )
    assert released, "闸上没有扣住的写可以放行——那次 PUT 根本没发出来"


def _diag_ops(page: Page) -> List[str]:
    entries: List[Dict[str, Any]] = page.evaluate(
        "() => (window.Reader3NotesDiag?.entries?.() || [])"
    )
    return [str(e.get("op")) for e in entries]


def _enable(page: Page, testid: str) -> None:
    """把按钮的 `disabled` 抹掉——**故意**拆掉第 1 层防线。"""
    selector = f'[data-testid="{testid}"]'
    page.evaluate(
        """(sel) => {
          const btn = document.querySelector(sel);
          if (!btn) throw new Error("按钮不在页面上：" + sel);
          btn.disabled = false;
          btn.removeAttribute("disabled");
        }""",
        selector,
    )


def _editor_text(page: Page) -> str:
    selector = f'[data-testid="{EDITOR_INPUT_TESTID}"]'
    return str(page.evaluate("(sel) => document.querySelector(sel).value", selector))


def _set_editor_text(page: Page, text: str) -> None:
    selector = f'[data-testid="{EDITOR_INPUT_TESTID}"]'
    page.evaluate(
        "([sel, v]) => { document.querySelector(sel).value = v; }",
        [selector, text],
    )


def test_保留我的还在飞时两个出口都不可点(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """第 1 层：提交期间两个按钮都 `disabled`，放行之后又都放开。"""
    note_id = _open_conflict(page, live_server, e2e_books_dir)
    _install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    _wait_for_held_write(page)

    expect(page.get_by_test_id(KEEP_MINE_TESTID)).to_be_disabled()
    expect(page.get_by_test_id(TAKE_REMOTE_TESTID)).to_be_disabled()

    _release_put(page)
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert _editor_text(page) == NOTE_LOCAL


def test_就算按钮被重新启用在飞期间的第二次点击也一次都不算(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """第 2 层：`disabled` 被抹掉之后，守卫仍然挡住重复点击与另一个出口。

    这条同时钉住两件事：再点「保留我的」**不许**再发一次写；点「采用远端」不许
    在别人还在飞的时候把冲突收掉——缺陷态下正是这一下让用户的选择被反转。
    """
    note_id = _open_conflict(page, live_server, e2e_books_dir)
    _install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    _wait_for_held_write(page)

    _enable(page, KEEP_MINE_TESTID)
    _enable(page, TAKE_REMOTE_TESTID)
    page.get_by_test_id(KEEP_MINE_TESTID).click()
    page.get_by_test_id(TAKE_REMOTE_TESTID).click()

    assert _held_writes(page) == EXPECTED_INFLIGHT_WRITES, (
        f"在飞期间又发出了写：闸上扣住 {_held_writes(page)} 次，"
        f"期望 {EXPECTED_INFLIGHT_WRITES} 次"
    )
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_visible()
    ops = _diag_ops(page)
    assert ops.count(OP_BUSY) == 2, f"两次被拒的点击没有各留一条 {OP_BUSY}：{ops}"

    _release_put(page)
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert _editor_text(page) == NOTE_LOCAL, (
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
    note_id = _open_conflict(page, live_server, e2e_books_dir)
    _install_put_gate(page)

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    _wait_for_held_write(page)

    page.evaluate("() => { window.Reader3AnnotationUI.pendingConflict = null; }")
    _set_editor_text(page, SENTINEL)

    _release_put(page)
    page.wait_for_function(
        """(op) => (window.Reader3NotesDiag?.entries?.() || []).some((e) => e.op === op)""",
        arg=OP_STALE,
    )

    assert _editor_text(page) == SENTINEL, (
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
    note_id = _open_conflict(page, live_server, e2e_books_dir)

    page.get_by_test_id(KEEP_MINE_TESTID).click()

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_LOCAL)
    assert _editor_text(page) == NOTE_LOCAL

    expect(page.get_by_test_id(KEEP_MINE_TESTID)).to_be_enabled()
    expect(page.get_by_test_id(TAKE_REMOTE_TESTID)).to_be_enabled()

    ops = _diag_ops(page)
    assert OP_BUSY not in ops and OP_STALE not in ops, (
        f"没有并发干扰的一次收尾却报了守卫：{ops}"
    )
