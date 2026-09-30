"""关掉的选区工具条必须保持关着，不得在 epub.js 的下一拍 `selected` 里自己弹回来。

**它守的是什么。** `annotations.js` 的 `handleRenditionSelection()` 处理 epub.js 的
`selected` 事件。它曾经无条件地 ``removeAllRanges(); addRange(range)``——这一写本身又触发
iframe 的 `selectionchange`，epub.js 250ms 去抖之后再 emit 一次 `selected`，只要选区不是
折叠态就无限循环（实测记在 `helpers.select_in_frame` 的 docstring 第 2 条）。每一拍都走
`handleSelectionRange()` → `openToolbarAt()`，于是任何**保留选区**的关闭路径——Copy、
Ask AI、Escape、在外层页面按下鼠标——关掉的工具条都会在 ~250ms 后重新出现。冻结用例
`test_k2_copy_action_puts_the_selected_text_on_the_clipboard` 的 soak 抖动就是这个。

**判据为什么是「一段时间里重开次数 == 0」而不是一次 `not_to_be_visible()`。**
`expect(...).not_to_be_visible()` 会重试：只要它的某一次轮询落在「已关、下一拍还没到」
那 250ms 里，它就绿——正是冻结用例抖动的成因。本文件在关闭之后给工具条挂一个
`MutationObserver`，数 `is-visible` 被重新加回来的次数，观察窗口
`OBSERVE_MS` 覆盖 epub.js 至少三拍去抖（250ms 一拍）。「没有发生某件事」只能用一段时间
窗来断言，这里的 `wait_for_timeout` 是判据的一部分，不是等待条件。

**两个时机为什么都要。**
* ``after_first_tick``：先等 epub.js 对这次选区的第一拍 `selected` 跑完（`lastSelectionAt`
  刷新到选区建立之后）再关。此后若还有 `selected`，只可能来自自激循环——这一支单独钉住
  「循环停了」。
* ``before_first_tick``：选区一建好立刻关，此时 epub.js 对**用户自己那次选区**的那一拍
  还在路上。这一拍到点时选区没变，工具条也不该因此回来。

**Copy 额外断言选区还在。** 修法不许靠「清空选区」来掐断循环：用户按下 Copy 之后手上的
选区应当保持原样。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_QUOTE,
    SELECTION_TIMEOUT_MS,
    open_reader,
    select_in_frame,
)

pytestmark = pytest.mark.baseline_1b

#: 关闭之后的观察窗口。epub.js 的 `selected` 去抖是 250ms 一拍，900ms 覆盖三拍以上。
OBSERVE_MS = 900

#: Escape 关工具条走的是外层 document 上 `toolbar.js` 的 keydown 监听。
KEY_ESCAPE = "Escape"

#: 关闭之后工具条允许被重新打开的次数。
EXPECTED_REOPENS = 0

#: 在工具条上挂观察器，数 `is-visible` 从无到有的次数。
_WATCH_REOPENS_JS = """(el) => {
  window.__toolbarReopens = 0;
  let wasVisible = el.classList.contains('is-visible');
  new MutationObserver(() => {
    const now = el.classList.contains('is-visible');
    if (now && !wasVisible) window.__toolbarReopens += 1;
    wasVisible = now;
  }).observe(el, { attributes: true, attributeFilter: ['class'] });
}"""


def _close_toolbar(page: Page, how: str) -> None:
    if how == "copy":
        page.get_by_test_id("rd-anno-copy").click()
    elif how == "ask_ai":
        page.get_by_test_id("rd-anno-ask").click()
    elif how == "escape":
        page.keyboard.press(KEY_ESCAPE)
    elif how == "outer_mousedown":
        # 外层页面上一个无交互的元素：章号指示。落点在 iframe 与工具条之外。
        page.get_by_test_id("rd-chapter-count").click()
    else:  # pragma: no cover - 参数表之外的取值
        raise AssertionError(how)


@pytest.mark.parametrize("timing", ["after_first_tick", "before_first_tick"])
@pytest.mark.parametrize("how", ["copy", "ask_ai", "escape", "outer_mousedown"])
def test_closed_selection_toolbar_does_not_reopen_by_itself(
    page: Page, live_server: str, e2e_books_dir: Path, how: str, timing: str
) -> None:
    """选中 → 工具条出现 → 用 ``how`` 关掉 → ``OBSERVE_MS`` 内工具条一次都不重开。

    什么改动会让它红：`handleRenditionSelection()` 在选区未变时仍重写选区（自激循环回来）、
    或者 epub.js 对未变选区的那一拍又把已被用户关掉的工具条打开。
    """
    if how == "copy":
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server)

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    toolbar = page.get_by_test_id("rd-anno-toolbar")

    select_in_frame(frame, CH0_QUOTE)
    selected_at = page.evaluate("() => Date.now()")
    expect(toolbar).to_be_visible()

    if timing == "after_first_tick":
        page.wait_for_function(
            "(t0) => (window.Reader3AnnotationUI?.lastSelectionAt || 0) >= t0",
            arg=selected_at,
            timeout=SELECTION_TIMEOUT_MS,
        )

    _close_toolbar(page, how)
    expect(toolbar).not_to_be_visible()

    if timing == "before_first_tick":
        last = page.evaluate("() => window.Reader3AnnotationUI?.lastSelectionAt || 0")
        assert last < selected_at, (
            "关闭动作落地时 epub.js 的第一拍已经跑过了，本参数化项测到的不是「第一拍之前关」"
        )

    toolbar.evaluate(_WATCH_REOPENS_JS)
    page.wait_for_timeout(OBSERVE_MS)

    reopens = page.evaluate("() => window.__toolbarReopens")
    assert reopens == EXPECTED_REOPENS, (
        f"经 {how}（{timing}）关掉的工具条在 {OBSERVE_MS}ms 内又被打开了 {reopens} 次"
    )
    expect(toolbar).not_to_be_visible()

    if how == "copy":
        still_selected = frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
            "() => String(document.getSelection() || '')"
        )
        assert still_selected == CH0_QUOTE, (
            f"Copy 之后 iframe 里的选区是 {still_selected!r}，不是原来的 {CH0_QUOTE!r}——"
            "修法不许靠清空选区来掐断循环"
        )
