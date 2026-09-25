"""REG-1 part 1 (013 WI-9, C9.22): the three pages boot cleanly.

For each page: no console error and no page error, the root testid resolves to
exactly one node, and one content equality holds.

**Which console errors are ignored, and why only those.** The egress gate aborts
every non-local request, which today means the Google Fonts `<link>` in
`library.html` and `reader.html`. Chromium logs each abort as
`Failed to load resource: net::ERR_FAILED` whose location is the aborted URL. An
error is ignored only when its location URL is one this test's own gate aborted.
Any other console error fails, including a failed load of a local resource.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

import pytest
import shell_4a_fixtures as s4
from conftest import BOOK_ID
from helpers import CH0_ANCHOR, http_json, reader_frame
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

ROOT_TESTID: Dict[str, str] = {
    "library": "lib-shell",
    "reader": "rd-shell",
    "settings": "set-screen",
}


def _library_content(page: Any, base_url: str) -> None:
    total = http_json(f"{base_url}/api/library/stats?fresh=true")["books_total"]
    assert total >= 1, "the e2e library holds books; an empty API count proves nothing"
    expect(page.get_by_test_id("lib-book-card")).to_have_count(total)


def _reader_content(page: Any, base_url: str) -> None:
    frame = reader_frame(page, CH0_ANCHOR)
    text = frame.locator("body").inner_text()  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
    assert text.strip(), "the reader iframe rendered no text"


def _settings_content(page: Any, base_url: str) -> None:
    providers = http_json(f"{base_url}/api/settings/providers")
    names = providers["providers"]
    assert len(names) >= 1, "the providers API lists no provider"
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(names))


CONTENT_CHECK: Dict[str, Callable[[Any, str], None]] = {
    "library": _library_content,
    "reader": _reader_content,
    "settings": _settings_content,
}


@pytest.mark.parametrize("page_name", s4.REG1_PAGE_NAMES)
def test_c9_22_page_boots_without_errors_with_root_testid_and_content(
    browser: Any, live_server: str, page_name: str
) -> None:
    blocked: List[str] = []
    context = s4.new_gated_context(browser, blocked=blocked)
    try:
        page = context.new_page()
        console_errors: List[Dict[str, str]] = []
        page_errors: List[str] = []
        page.on(
            "console",
            lambda m: console_errors.append({"text": m.text, "url": m.location.get("url", "")})
            if m.type == "error"
            else None,
        )
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(live_server + s4.page_path(page_name, BOOK_ID), wait_until="load")
        expect(page.get_by_test_id(ROOT_TESTID[page_name])).to_have_count(1)
        CONTENT_CHECK[page_name](page, live_server)

        blocked_set = set(blocked)
        unexplained = [e for e in console_errors if e["url"] not in blocked_set]
        assert unexplained == [], (
            f"{page_name}: console errors not caused by the egress gate: {unexplained}"
        )
        assert page_errors == [], f"{page_name}: uncaught page errors: {page_errors}"
    finally:
        context.close()
