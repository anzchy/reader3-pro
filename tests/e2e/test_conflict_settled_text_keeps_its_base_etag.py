"""017 WI-7（审计 #4）——收尾放进编辑器的那一版，必须连着它自己的令牌。

**缺陷**：`settleConflict()` 把某一版正文写回 textarea，紧接着 `loadAndRender()` 去读
一次 notes，而那次读会把全局 `notesEtag` 换成**服务端此刻**的版本。两件事对不上时就出
事：「采用远端」放进编辑器的是 409 那一刻的远端正文（记作 R1），可如果 409 之后、用户
点下「采用远端」之前，第三方又写了一版（R2），收尾时那次读吸收的是 R2 的令牌。于是编辑
器里是 **R1 的正文**、手里是 **R2 的令牌**——用户在 R1 上继续改、按保存，服务端一看令牌
是最新的就收下了，**R2 无声无息地没了**。乐观并发在这条路径上被绕了过去。

**修法**：给「正在编辑的这一版」单独钉一个基准令牌 `notesEditBaseEtag`，由收尾时设定
——采用远端钉 409 体里报来的那一版（正文就是从那儿来的），保留我的钉自己那次写回来的
那一版（正文就是那次写上去的）。编辑保存优先用这个钉子，而不是被读路径刷新过的全局值。

三条边界，各由一条用例守着，少一条这个钉子就会从「修好一个洞」变成「换一个洞」：

1. 钉子必须**真的**拦下上面那条静默覆盖（用例一）。
2. 钉子必须跟着**自己的写**前进——保留我的成功之后紧接着再保存一次，不许 409（用例二）。
   把两支都钉成「409 体里的那一版」是最顺手的写法，而它会让保留我的之后的每一次保存都
   撞上自己刚写出去的版本。
3. 钉子必须**随编辑会话结束而消失**（用例四）。一个不清的钉子会让这个页面此后**每一次**
   笔记编辑都撞 409——一次冲突之后整页作废，比原来的缺陷更响。

用例三是不带第三方的对照：没人来抢的时候，收尾之后的保存必须照旧成功。

**冲突与第三方的写都是真的**，只有「什么时候读完」被测量（不是被改写）：
`notes_conflict_support.install_notes_get_counter()` 只在 notes 的 GET 回来时记一笔数，
用例据此等收尾那次读**落地**之后再保存。不等的话，保存可能抢在读前面发出去，撞不撞 409
由时序决定——那样的红绿都不作数。

**落址：白名单，不是 `baseline_1b`**（同 WI-5 / WI-6）。迁进冻结目录会改 `suite_hash`
并把 soak 计数清零。到期条件：下一次本来就要动 `baseline_1b/` 的改动里一并迁入，同批撤掉
`UNGROUPED_E2E_MODULES` 里的条目并把条数加进 `EXPECTED_BASELINE_ITEMS`。
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    read_notes,
    reader_frame,
    wait_for_note_text,
)
from notes_conflict_support import (  # type: ignore[import-not-found]
    DIALOG_TESTID,
    EDITOR_INPUT_TESTID,
    KEEP_MINE_TESTID,
    NOTE_REMOTE,
    TAKE_REMOTE_TESTID,
    bypass_write,
    editor_text,
    install_notes_get_counter,
    notes_gets,
    open_conflict,
    open_note_editor,
    save_editor,
    wait_for_notes_gets,
)

#: 409 之后才落地的第三版——用户在屏幕上从没见过它，正是它会被静默盖掉。
NOTE_THIRD = "第三版：409 之后、用户点下出口之前，别处又写了一次"

#: 收尾之后用户接着敲的字。
NOTE_AFTER = "收尾之后用户接着改的那一版"
NOTE_AFTER_2 = "再改一次"


def _fill_and_save(page: Page, text: str) -> None:
    page.get_by_test_id(EDITOR_INPUT_TESTID).fill(text)
    save_editor(page)


def _note_text(books_dir: Path, note_id: str) -> str:
    for ann in read_notes(books_dir, BOOK_ID):
        if str(ann.get("id")) == note_id:
            return str(ann.get("note_text") or "")
    raise AssertionError(f"盘上找不到这条笔记：{note_id}")


def test_采用远端之后的保存不许盖掉用户没见过的第三版(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """核心：编辑器里是 R1，服务端已经是 R2，这时候保存必须撞 409。

    顺序是缺陷成立的全部条件：409 已经发生（对话框开着，远端那版定格在 R1）→ 第三方写
    R2 → 用户点「采用远端」，以为自己接受的是「最新的那一版」，实际接受的是 R1 → 收尾那
    次读把令牌换成了 R2 的。此后用户在 R1 上改的任何字，保存出去都会把 R2 抹掉，而且抹得
    悄无声息：没有对话框、没有提示，两个版本的差异直接消失。

    所以判据有两条，缺一不可：**看得见**的那条——冲突对话框必须再开一次，且摆出来的远端
    正文是 R2（用户第一次有机会看见它）；**盘上**的那条——R2 必须还在，没有被用户那版盖掉。
    """
    setup = open_conflict(page, live_server, e2e_books_dir)
    note_id = setup.note_id

    bypass_write(page, live_server, e2e_books_dir, note_id, NOTE_THIRD)

    install_notes_get_counter(page)
    before = notes_gets(page)
    page.get_by_test_id(TAKE_REMOTE_TESTID).click()

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    assert editor_text(page) == NOTE_REMOTE, (
        "「采用远端」放进编辑器的不是 409 那一刻的远端正文，前提就不成立"
    )
    # 等收尾那次读**落地**：缺陷正是在这一刻把令牌换成 R2 的。不等的话，下面那次保存
    # 可能带着旧令牌抢先发出去，于是红绿由时序决定。
    wait_for_notes_gets(page, before + 1)

    _fill_and_save(page, NOTE_AFTER)

    dialog = page.get_by_test_id(DIALOG_TESTID)
    expect(dialog).to_be_visible()
    assert NOTE_THIRD in dialog.inner_text(), (
        "冲突对话框摆出来的远端正文不是第三版——那么用户仍然没机会看见它"
    )
    assert _note_text(e2e_books_dir, note_id) == NOTE_THIRD, (
        "第三版被静默盖掉了：编辑器里那一版配着一个更新的令牌写了出去"
    )


def test_保留我的成功之后紧接着再保存一次不许误冲突(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """钉子要跟着**自己的写**走。

    「保留我的」成功之后，编辑器里躺的是刚刚写上去的那一版，盘上也是它——两边一致，
    下一次保存没有任何理由冲突。把两支都钉成「409 体里报来的那一版」是最顺手的写法，
    它能让用例一变绿，却会让这里每一次保存都撞上自己刚写出去的版本：用户会在一个
    没有任何第三方参与的编辑里反复看见冲突对话框。
    """
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id

    page.get_by_test_id(KEEP_MINE_TESTID).click()
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()

    _fill_and_save(page, NOTE_AFTER)

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_AFTER)


def test_没有第三方时采用远端之后的保存照旧成功(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """对照：没人来抢的时候，收尾之后的保存必须照旧落盘。

    没有这条，「所有保存一律 409」也能让用例一变绿。
    """
    note_id = open_conflict(page, live_server, e2e_books_dir).note_id

    install_notes_get_counter(page)
    before = notes_gets(page)
    page.get_by_test_id(TAKE_REMOTE_TESTID).click()
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_notes_gets(page, before + 1)

    _fill_and_save(page, NOTE_AFTER)

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_AFTER)


def test_钉子不许活过这一轮编辑(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """一个不清的钉子会让这一页此后**每一次**笔记编辑都撞 409。

    场景是完全正常的一次使用：冲突收掉、编辑器关掉（这一轮编辑结束），别处又改了一版，
    页面照常刷新学到了新版本，用户重新点开这条笔记去改。此刻页面手里的就是最新版本，
    保存没有任何理由冲突——除非上一轮留下的那个钉子还在，把一个早就过期的版本当成基准
    带了出去。那样的话，一次冲突之后整个页面的笔记编辑就全废了，比原来的缺陷更响。

    这里的刷新是**主动催**出来再等它落地的（`reader3:annotations:updated` 正是应用自己
    用的那个刷新信号），不是碰运气等某次重绘：等不到确定的刷新，这条用例就会在「页面到底
    学到新版本没有」上掷硬币。
    """
    setup = open_conflict(page, live_server, e2e_books_dir)
    note_id = setup.note_id

    install_notes_get_counter(page)
    before = notes_gets(page)
    page.get_by_test_id(TAKE_REMOTE_TESTID).click()
    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_notes_gets(page, before + 1)

    # 这一轮编辑到此结束。
    page.get_by_test_id("rd-note-editor-cancel").click()
    expect(page.get_by_test_id("rd-note-editor")).to_have_attribute("aria-hidden", "true")

    bypass_write(page, live_server, e2e_books_dir, note_id, NOTE_THIRD)
    before = notes_gets(page)
    page.evaluate(
        "() => window.dispatchEvent(new CustomEvent('reader3:annotations:updated'))"
    )
    wait_for_notes_gets(page, before + 1)

    frame = reader_frame(page, CH0_ANCHOR)
    open_note_editor(page, frame, note_id)
    assert editor_text(page) == NOTE_THIRD, "重新打开的编辑器里不是盘上那一版，前提不成立"

    _fill_and_save(page, NOTE_AFTER_2)

    expect(page.get_by_test_id(DIALOG_TESTID)).to_be_hidden()
    wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, NOTE_AFTER_2)
