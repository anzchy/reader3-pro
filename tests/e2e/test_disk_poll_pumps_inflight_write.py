"""009 欠账 #49（019 WI-2，修订 A1 的 WI2-E2）：盘上轮询期间，在途的写必须出得了门。

**它钉的是机制本身，不是某条业务路径。** `tests/e2e/conftest.py` 给每个 context 挂了
`**/*` 出网闸，同步 Playwright 的 route 回调只在主线程调进 Playwright 时才被派发。旧的
`wait_for_notes` 用 `time.sleep(0.05)` 轮询盘，整个 8s 窗口里一次都不调进 Playwright——
于是一次**在轮询开始之后才发出**的写，卡在闸的回调上出不了门，轮询等满 8s 判超时：
产品行为完全正确也会红。v6 归因臂里「上线前排队 8007–8151ms」的慢请求簇就是这个形状。

**构造。** 选中 `CH0_QUOTE`，用 `setTimeout(…, 200)` 让浏览器在 200ms 之后自己调真的
`createAnnotation`（不 await），然后**中间不做任何 Playwright 调用**，直接进
`wait_for_notes(..., page=page)`。写请求因此一定落在轮询窗口之内：
- 轮询里泵浏览器（`page.wait_for_timeout`）⇒ 出网闸被服务，1 条落盘，绿；
- 轮询里 `time.sleep` ⇒ 请求一直排队，`AssertionError("8.0s 内 notes.json 没有稳定到 1 条，
  实际 0 条：[]")`。这是 019 WI-2 在旧循环体上记下的红回执。

**为什么单独成一个模块、不并进 W6-C8。** W6-C8 断的是 `createAnnotation` 各出口的报告流；
把这条机制判据混进去，任何一条红都说不清是哪一边坏了。

**落址：`tests/e2e/` 根，不带组 marker，登记在 `UNGROUPED_E2E_MODULES`。** 理由同白名单里
其他几条：`scripts/soak_run.py` 的 `HASH_COVERED_PATHS` 不覆盖根下的新文件，放这里不额外
移动 `suite_hash`。
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    open_ch0,
    select_in_frame,
    wait_for_notes,
)

#: 浏览器侧 200ms 之后自己发起一次真的建（marker 黄）。**不 await**：evaluate 立刻返回，
#: 写请求落在接下来那段盘上轮询的窗口里。
_CREATE_LATER_JS = """() => {
  setTimeout(
    () => window.Reader3AnnotationUI.createAnnotation({ type: "marker", color: "yellow" }),
    200
  );
}"""


def test_disk_poll_lets_a_write_started_during_the_poll_reach_disk(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.evaluate(_CREATE_LATER_JS)
    # 中间不许插任何 Playwright 调用：那一下会顺手把出网闸服务掉，机制就测不到了。
    records = wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    assert len(records) == 1, records
    assert records[0]["quote"] == CH0_QUOTE, records
