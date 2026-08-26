"""009 harness spike 的唯一一条 smoke。

**它回答的问题只有一个**：Playwright 在这个仓库能不能稳定起来，一次冷启动多久。
不是用例清单的第一条，也不是 K1–K6 里任何一条的实现——那些属于 009 正式开工，
见 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`。

**为什么落在 iframe 里，而不是「首页 200」。** 这套 E2E 将来所有的写路径都要穿过
epub.js 的 iframe——选区建在 child frame 里，工具条在外层。如果 Playwright 进不去
那个 iframe，整份任务骨架都得重写。「首页能打开」不回答这个问题，进 iframe 读到
正文才回答。
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]


def test_playwright_reaches_epubjs_iframe_content(page: Page, live_server: str) -> None:
    page.goto(f"{live_server}/read/{BOOK_ID}/0")

    # 外层壳先到位，再谈 iframe：壳都没有的话，下面的等待会白等满超时，
    # 报出来的也是「找不到 frame」而不是「页面根本没渲染」。
    expect(page.get_by_test_id("rd-shell")).to_be_visible()

    # epub.js 把 iframe 建在 #epub-viewer 里。正文取自 build_epub2 的第一章。
    chapter = page.frame_locator("#epub-viewer iframe").locator("body")
    expect(chapter).to_contain_text("Alpha prose.")
