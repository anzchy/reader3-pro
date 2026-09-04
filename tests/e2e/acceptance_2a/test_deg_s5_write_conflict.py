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

**断言分三段**：(a) 对话框形态——`role=alertdialog`、两个出口各恰好一个、没有关闭按钮、Esc 与遮罩点击都
关不掉；(b) **对话框开着的时候盘上仍是 A1**（B 的写没有静默盖掉 A 的，A 的也没有被 B 的覆盖）；
(c) B 选「保留我的」之后盘上变成 B、仍是同一条 id、总数仍为 1、对话框消失。

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
from typing import Iterator
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

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
    pytest.mark.skip(
        reason=(
            "激活阶段 2a：notes 乐观并发（版本号 / 409）与 ConflictDialog 是 Phase 2a 的产物，"
            "今天 notes_service 是整章回写、后写者静默覆盖前写者。"
            "到期动作：核对 rd-conflict-* 三个 testid 后删本行。"
        )
    ),
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

#: 冲突前后该章都应恰好一条——字面量基准。
EXPECTED_NOTE_COUNT = 1

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


def _open_note_editor_on_mark(page: Page, frame, note_id: str) -> None:  # type: ignore[no-untyped-def]
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)
    mark.click()
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_have_attribute("aria-hidden", "false")


def test_deg_s5_concurrent_note_edit_shows_conflict_dialog_and_loses_nothing(
    page: Page, other_context: BrowserContext, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S5（S3 / L2）：过期版本的写被拒 ⇒ alertdialog、两个出口、不可关闭；盘上仍是最新版；选「保留我的」后原地变成 B。"""
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    # ---- 1. A 建一条 note ------------------------------------------------------------------
    frame_a = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame_a, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()
    page.get_by_test_id("rd-note-editor-input").fill(NOTE_A0)
    page.get_by_test_id("rd-note-editor-primary").click()
    records = wait_for_notes(e2e_books_dir, BOOK_ID, EXPECTED_NOTE_COUNT)
    note_id = str(records[0]["id"])
    assert records[0]["note_text"] == NOTE_A0

    # ---- 2. B 打开同一章，读到 A0 版本，此后不再刷新 ------------------------------------------
    page_b = other_context.new_page()
    frame_b = open_reader_settled(page_b, live_server, BOOK_ID, CH0_INDEX, CH0_ANCHOR, expected_marks=1)

    # ---- 3. A 改成 A1 并保存（服务端版本前进）------------------------------------------------
    frame_a = open_ch0(page, live_server, expected_marks=1)
    _open_note_editor_on_mark(page, frame_a, note_id)
    page.get_by_test_id("rd-note-editor-input").fill(NOTE_A1)
    page.get_by_test_id("rd-note-editor-primary").click()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_A1)

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

    # (b) 对话框开着时，盘上仍是 A1：B 的过期写没有静默盖掉它，A 的也没有被丢。
    on_disk = read_notes(e2e_books_dir, BOOK_ID)
    assert len(on_disk) == EXPECTED_NOTE_COUNT, f"冲突期间条数变了：{on_disk}"
    assert on_disk[0]["id"] == note_id
    assert on_disk[0]["note_text"] == NOTE_A1, (
        f"对话框开着时盘上已经是 {on_disk[0]['note_text']!r}，期望仍是 {NOTE_A1!r}——过期写被静默接受了（last-write-wins）"
    )

    # (c) B 选「保留我的」⇒ 同一条原地变成 B，总数不变，对话框消失。
    dialog.get_by_test_id(KEEP_MINE_TESTID).click()
    expect(dialog).to_be_hidden()
    final = wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_B)
    assert final["id"] == note_id
    settled = read_notes(e2e_books_dir, BOOK_ID)
    assert len(settled) == EXPECTED_NOTE_COUNT, f"「保留我的」之后条数不是 {EXPECTED_NOTE_COUNT}：{settled}"
    assert [r["note_text"] for r in settled] == [NOTE_B]

    # 刷新 A：A 看到的也是 B 的版本，仍是同一条。
    frame_a = open_ch0(page, live_server, expected_marks=1)
    expect(
        frame_a.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    ).to_have_text(CH0_QUOTE)
