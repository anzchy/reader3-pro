"""013 WI-13 A13.7 (C13.05, minus the load-failed branch deferred by ruling D12).

Law: exactly one data state is shown per scenario.

    scenario        cards   lib-empty   lib-filter-empty
    normal          N       hidden      hidden
    filter-empty    0 vis   hidden      visible
    empty library   0       visible     hidden

The empty library is a second server of this worktree over an empty books dir (the session
library is shared and must keep its four books).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
from conftest import E2E_BOOK_IDS, _server_env
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

NO_MATCH = "zz-no-book-has-this-title-zz"
CLEARED = ""


def _visible_cards(page: Any) -> int:
    return len(page.evaluate(sl.VISIBLE_CARD_TITLES_JS))


def test_normal_and_filter_empty(browser: Any, live_server: str) -> None:
    context = s4.new_gated_context(browser)
    try:
        page = sl.open_library(context, live_server)
        assert _visible_cards(page) == len(E2E_BOOK_IDS)
        expect(page.get_by_test_id("lib-empty")).to_be_hidden()
        expect(page.get_by_test_id("lib-filter-empty")).to_be_hidden()

        page.get_by_test_id("lib-toolbar-filter").fill(NO_MATCH)
        expect(page.get_by_test_id("lib-filter-empty")).to_be_visible()
        expect(page.get_by_test_id("lib-empty")).to_be_hidden()
        assert _visible_cards(page) == 0

        page.get_by_test_id("lib-toolbar-filter").fill(CLEARED)
        expect(page.get_by_test_id("lib-filter-empty")).to_be_hidden()
        assert _visible_cards(page) == len(E2E_BOOK_IDS)
    finally:
        context.close()


def test_empty_library(browser: Any, tmp_path: Path) -> None:
    empty = tmp_path / "books"
    empty.mkdir()
    env = s4.base_server_env(s4.REPO_ROOT, _server_env(empty))
    with s4.base_worktree_server(s4.REPO_ROOT, env, tmp_path / "logs") as base_url:
        context = s4.new_gated_context(browser)
        try:
            page = sl.open_library(context, base_url, wait_status=False)
            expect(page.get_by_test_id("lib-empty")).to_be_visible()
            expect(page.get_by_test_id("lib-filter-empty")).to_be_hidden()
            expect(page.get_by_test_id("lib-book-card")).to_have_count(0)
            expect(page.get_by_test_id("lib-theme-toggle")).to_have_count(1)
        finally:
            context.close()
