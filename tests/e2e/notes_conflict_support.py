"""DEG-S5 冲突对话框的共用夹具（017 WI-6 / WI-7）。

这里只有**怎么把一场真的写冲突摆到屏幕上**，以及怎么把那次写扣在半空。判据一条都
不在这里——它们分别在 `test_conflict_resolution_single_flight.py`（同一时刻只许有一次
收尾在飞）与 `test_conflict_settled_text_keeps_its_base_etag.py`（收尾之后编辑器里那一版
和它的令牌必须还绑在一起）里。

不是测试模块（文件名不以 `test_` 开头），所以不贡献 item，分组守卫的三个数不受影响。
放在这里而不是 `helpers.py`：后者在**冻结集**里，动一个字节会改 `suite_hash` 并把 soak
计数清零。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

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

DIALOG_TESTID = "rd-conflict-dialog"
KEEP_MINE_TESTID = "rd-conflict-keep-mine"
TAKE_REMOTE_TESTID = "rd-conflict-take-remote"
EDITOR_INPUT_TESTID = "rd-note-editor-input"
EDITOR_SAVE_TESTID = "rd-note-editor-primary"


def note_record(quote: str, note_text: str, position: int) -> Dict[str, Any]:
    """一条可以被 `seed_notes` 吃下去的 note 记录。"""
    return {
        "chapter_index": 0,
        "type": "note",
        "color": "yellow",
        "quote": quote,
        "prefix": "",
        "suffix": "",
        "position": position,
        "note_text": note_text,
    }


def seed_note(books_dir: Path, records: Sequence[Dict[str, Any]] | None = None) -> List[str]:
    """预置若干条 note（默认一条，正文 `NOTE_BASE`），按落盘顺序返回 id。"""
    if records is None:
        records = [note_record(CH0_QUOTE, NOTE_BASE, 0)]
    seed_notes(books_dir, BOOK_ID, list(records))
    return [str(r["id"]) for r in read_notes(books_dir, BOOK_ID)]


def chapter_url(live_server: str) -> str:
    return f"{live_server}/api/notes/{BOOK_ID}/0"


def bypass_write(page: Page, live_server: str, books_dir: Path, note_id: str, text: str) -> None:
    """绕过页面直接改一次那条笔记——「另一处」的写，服务端版本因此前进。

    不带 `If-Match`（它是可选的，ADR-0011），所以这一写**必然**被接受：本 helper 的
    作用是把服务端推到下一版，不是去测乐观并发。
    """
    resp = page.request.put(
        f"{chapter_url(live_server)}/{note_id}",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"note_text": text}),
    )
    assert resp.ok, f"旁路写没成功（{resp.status}），服务端版本没前进"
    wait_for_note_text(books_dir, BOOK_ID, note_id, text, page=page)


def read_etag(page: Page, live_server: str) -> str:
    resp = page.request.get(chapter_url(live_server))
    assert resp.ok, f"读不到当前版本（{resp.status}）"
    etag = resp.headers.get("etag")
    assert etag, f"GET notes 没带 ETag，乐观并发的前提就不成立：{resp.headers}"
    return etag


def open_note_editor(page: Page, frame, note_id: str) -> None:  # type: ignore[no-untyped-def]
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).not_to_have_count(0)
    mark.click()
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_have_attribute("aria-hidden", "false")


def pin_if_match(page: Page, etag: str) -> None:
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


@dataclass(frozen=True)
class ConflictSetup:
    """一场已经摆在屏幕上的冲突：那条 note 的 id，与页面出发时手里的那一版。"""

    note_id: str
    base_etag: str
    extra_ids: Sequence[str] = ()


def open_conflict(
    page: Page,
    live_server: str,
    books_dir: Path,
    *,
    extra_notes: Sequence[Dict[str, Any]] = (),
) -> ConflictSetup:
    """造一场**真的** 409 并把对话框开在屏幕上。

    步骤与 DEG-S5 同构，只是「另一个用户」换成了一次绕过页面的 API 写：
    读到版本 v1 → 旁路写把服务端推到 v2 → 页面拿着 v1 保存 ⇒ 服务端 409。

    旁路写必须发生在**编辑器已经打开之后**：打开编辑器只点 DOM，不重新拉 notes。
    而「页面手里仍是 v1」这件事由 `pin_if_match` 钉住，理由见那个函数。

    `extra_notes` 用来额外预置几条互不相干的标注——调用方想验证「客户端**自己**对别的
    标注的写不该引发误冲突」时需要它们。
    """
    records = [note_record(CH0_QUOTE, NOTE_BASE, 0), *extra_notes]
    ids = seed_note(books_dir, records)
    note_id, extra_ids = ids[0], tuple(ids[1:])

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)
    open_note_editor(page, frame, note_id)

    base_etag = read_etag(page, live_server)
    bypass_write(page, live_server, books_dir, note_id, NOTE_REMOTE)

    pin_if_match(page, base_etag)
    page.get_by_test_id(EDITOR_INPUT_TESTID).fill(NOTE_LOCAL)
    page.get_by_test_id(EDITOR_SAVE_TESTID).click()

    dialog = page.get_by_test_id(DIALOG_TESTID)
    expect(dialog).to_be_visible()
    saw = page.evaluate("() => window.__r3PinIfMatch.sawClientEtag")
    assert isinstance(saw, str) and saw, (
        "那次保存自己没带 If-Match——客户端没在参与乐观并发，"
        "这场 409 是被钉出来的，不作数"
    )
    text = dialog.inner_text()
    assert NOTE_LOCAL in text, "对话框里没有本地那版，冲突造歪了"
    assert NOTE_REMOTE in text, "对话框里没有远端那版，冲突造歪了"
    return ConflictSetup(note_id=note_id, base_etag=base_etag, extra_ids=extra_ids)


def install_put_gate(page: Page) -> None:
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


def held_writes(page: Page) -> int:
    return int(page.evaluate("() => (window.__r3PutGate?.held || []).length"))


def wait_for_held_write(page: Page) -> None:
    page.wait_for_function("() => (window.__r3PutGate?.held || []).length > 0")


def release_put(page: Page) -> None:
    released = page.evaluate(
        """() => {
          const gate = window.__r3PutGate;
          if (!gate || typeof gate.release !== "function") return false;
          gate.release();
          return true;
        }"""
    )
    assert released, "闸上没有扣住的写可以放行——那次 PUT 根本没发出来"


def diag_ops(page: Page) -> List[str]:
    entries: List[Dict[str, Any]] = page.evaluate(
        "() => (window.Reader3NotesDiag?.entries?.() || [])"
    )
    return [str(e.get("op")) for e in entries]


def enable(page: Page, testid: str) -> None:
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


def editor_text(page: Page) -> str:
    selector = f'[data-testid="{EDITOR_INPUT_TESTID}"]'
    return str(page.evaluate("(sel) => document.querySelector(sel).value", selector))


def set_editor_text(page: Page, text: str) -> None:
    selector = f'[data-testid="{EDITOR_INPUT_TESTID}"]'
    page.evaluate(
        "([sel, v]) => { document.querySelector(sel).value = v; }",
        [selector, text],
    )


def install_notes_get_counter(page: Page) -> None:
    """数「对 notes 的 GET 回来了几次」。

    收尾（`settleConflict`）会顺手 `loadAndRender()`，那一次 GET 正是把全局版本号换掉的
    地方。要判断「收尾之后的保存带的是哪一版」，就必须先等那次 GET **落地**——否则保存
    可能抢在它前面发出去，于是撞不撞 409 由时序决定，用例变成掷硬币。
    """
    page.evaluate(
        """() => {
          const real = window.fetch.bind(window);
          const counter = { done: 0 };
          window.__r3NotesGets = counter;
          window.fetch = function (input, init) {
            const url = String((input && input.url) || input || "");
            const method = String((init && init.method) || "GET").toUpperCase();
            const p = real(input, init);
            if (method === "GET" && url.includes("/api/notes/")) {
              p.then(() => { counter.done += 1; }, () => { counter.done += 1; });
            }
            return p;
          };
        }"""
    )


def notes_gets(page: Page) -> int:
    return int(page.evaluate("() => window.__r3NotesGets?.done ?? 0"))


def wait_for_notes_gets(page: Page, at_least: int) -> None:
    page.wait_for_function(
        "(n) => (window.__r3NotesGets?.done ?? 0) >= n",
        arg=at_least,
    )


def save_editor(page: Page) -> None:
    page.get_by_test_id(EDITOR_SAVE_TESTID).click()
