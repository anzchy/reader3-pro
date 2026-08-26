"""009 harness spike 的唯一一条 smoke。

**它回答的问题只有一个**：Playwright 在这个仓库能不能稳定起来，一次冷启动多久。
不是用例清单的第一条，也不是 K1–K6 里任何一条的实现——那些属于 009 正式开工，
见 `docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`。

**为什么落在 iframe 里，而不是「首页 200」。** 这套 E2E 将来所有的写路径都要穿过
epub.js 的 iframe——选区建在 child frame 里，工具条在外层。如果 Playwright 进不去
那个 iframe，整份任务骨架都得重写。「首页能打开」不回答这个问题，进 iframe 读到
正文才回答。

**关于下面两处 `lint-e2e-selectors: allow`。** iframe 边界正是 testid 契约的尽头，
而且是永久的尽头，不是偷懒：iframe 元素由 epub.js 在运行时创建，它的 document 是
**用户那本书自己的** XHTML。两边都不是我们的模板，谁都插不进 `data-testid`。
所以这两行放行不是「以后补」，是「这里没有别的写法」——也因此，放行只到 iframe
的 body 为止，body 之内一律回到 testid 与 ARIA。
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]


def test_playwright_reaches_epubjs_iframe_content(page: Page, live_server: str) -> None:
    page.goto(f"{live_server}/read/{BOOK_ID}/0")

    # 外层壳先到位，再谈 iframe：壳都没有的话，下面的等待会白等满超时，
    # 报出来的也是「找不到 frame」而不是「页面根本没渲染」。
    expect(page.get_by_test_id("rd-shell")).to_be_visible()

    # epub.js 把 iframe 建在 rd-viewport 里。正文取自 build_epub2 的第一章。
    # 选择器写成字面量而不是提到模块级常量：常量会让 lint 的正则扫不到，
    # 那是一条**看不见的**绕过，比显式放行糟得多。
    frame = page.frame_locator('[data-testid="rd-viewport"] iframe')  # lint-e2e-selectors: allow —— iframe 元素由 epub.js 运行时创建，插不进 testid
    chapter = frame.locator("body")  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    expect(chapter).to_contain_text("Alpha prose.")
