"""013 WI-13 functional rows of the library slice (C13.13-C13.16, feasible parts; lib-toast).

* C13.13: creating a collection is single-flight (three fast clicks -> one POST), and success
  is confirmed by `lib-toast` naming the collection; bulk index with nothing selected is
  disabled and sends nothing.
* C13.14: select-all selects every visible book (and only those under a filter); select-none
  clears; the select-mode toggle reports `aria-pressed`.
* C13.15: grid/list view toggles are pressed exclusively and change what is shown; sort
  reorders the visible cards A->Z in both views (FB-L10); one search request per settled query; clear empties results.
* C13.16: Enter and Space on a card's "Read" link both open the reader; exactly one `main`;
  the first heading is an h1; the library nav link carries `aria-current="page"`.

Deferred / blocked, not tested here: FB-L01-03 (upload, chooser, dropzone) and FB-L18
(delete book) have no routes (reported as blockers).
"""

from __future__ import annotations

import re
import time
from typing import Any, Iterator

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
import shell_4a_settings as ss
from conftest import BOOK_ID, E2E_BOOK_IDS
from epub_corpus import EPUB2_TITLE, EPUB3_TITLE
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

TOAST_NAME = "WI13 toast collection"
FILTER_ONE = "three point"  # matches only EPUB3_TITLE
H1 = "H1"


@pytest.fixture
def page(browser: Any, live_server: str) -> Iterator[Any]:
    context = s4.new_gated_context(browser)
    try:
        yield sl.open_library(context, live_server)
    finally:
        context.close()


def _checked(page: Any, testid: str) -> int:
    # SEPARATION-BROKEN (013 WI-13, coordinator-approved): `include_hidden=True` added after the
    # red. The frozen baseline hides filtered-out cards with the `hidden` attribute, and a role
    # locator skips hidden elements by default, so the original line timed out on the first
    # filtered card whatever the implementation did. The intent is unchanged: count the check
    # state of every card, visible or not, so "select-all selected hidden books" can still fail.
    return sum(
        1
        for card in page.get_by_test_id(testid).all()
        if card.get_by_role("checkbox", include_hidden=True).is_checked()
    )


# ---------------------------------------------------------------------------
# C13.13 + lib-toast
# ---------------------------------------------------------------------------
def test_create_collection_single_flight_and_toast(page: Any, live_server: str) -> None:
    log = ss.RequestLog(page)
    try:
        page.get_by_test_id("lib-sidebar-create-collection").click()
        expect(page.get_by_test_id("lib-modal-create-collection")).to_be_visible()
        page.get_by_test_id("lib-collection-name-input").fill(TOAST_NAME)
        log.start()
        primary = page.get_by_test_id("lib-modal-create-collection-primary")
        primary.evaluate("(b) => { b.click(); b.click(); b.click(); }")
        toast = page.get_by_test_id("lib-toast")
        expect(toast).to_be_visible()
        expect(toast).to_contain_text(TOAST_NAME)
        posts = [i for i in log.items if i == ("POST", "/api/collections")]
        assert len(posts) == 1, f"create collection sent {len(posts)} POSTs"
    finally:
        listing = page.request.get(live_server + "/api/collections").json()
        items = listing.get("collections", listing) if isinstance(listing, dict) else listing
        for c in items:
            if c.get("name") == TOAST_NAME:
                page.request.delete(f"{live_server}/api/collections/{c['id']}")


def test_bulk_index_disabled_without_selection_sends_nothing(page: Any) -> None:
    page.get_by_test_id("lib-toolbar-select-mode").click()
    bulk = page.get_by_test_id("lib-bulk-index")
    expect(bulk).to_be_disabled()
    log = ss.RequestLog(page).start()
    bulk.click(force=True)
    page.wait_for_timeout(300)
    assert [i for i in log.items if i[1].startswith("/api/index/") and i[0] == "POST"] == []


# ---------------------------------------------------------------------------
# C13.14
# ---------------------------------------------------------------------------
def test_selection_projections(page: Any) -> None:
    mode = page.get_by_test_id("lib-toolbar-select-mode")
    expect(mode).to_have_attribute("aria-pressed", "false")
    mode.click()
    expect(mode).to_have_attribute("aria-pressed", "true")
    page.get_by_test_id("lib-bulk-select-all").click()
    assert _checked(page, "lib-book-card") == len(E2E_BOOK_IDS)
    page.get_by_test_id("lib-bulk-select-all").click()
    assert _checked(page, "lib-book-card") == len(E2E_BOOK_IDS), "select-all is not idempotent"
    page.get_by_test_id("lib-bulk-select-none").click()
    assert _checked(page, "lib-book-card") == 0
    page.get_by_test_id("lib-toolbar-filter").fill(FILTER_ONE)
    assert len(page.evaluate(sl.VISIBLE_CARD_TITLES_JS)) == 1
    page.get_by_test_id("lib-bulk-select-all").click()
    assert _checked(page, "lib-book-card") == 1, "select-all selected hidden books"
    mode.click()
    expect(mode).to_have_attribute("aria-pressed", "false")


# ---------------------------------------------------------------------------
# C13.15
# ---------------------------------------------------------------------------
def test_view_toggle_is_exclusive_and_changes_display(page: Any) -> None:
    grid_btn = page.get_by_test_id("lib-toolbar-view-grid")
    list_btn = page.get_by_test_id("lib-toolbar-view-list")
    expect(grid_btn).to_have_attribute("aria-pressed", "true")
    expect(list_btn).to_have_attribute("aria-pressed", "false")
    expect(page.get_by_test_id("lib-book-grid")).to_be_visible()
    expect(page.get_by_test_id("lib-book-table")).to_be_hidden()
    list_btn.click()
    expect(grid_btn).to_have_attribute("aria-pressed", "false")
    expect(list_btn).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("lib-book-grid")).to_be_hidden()
    expect(page.get_by_test_id("lib-book-table")).to_be_visible()
    grid_btn.click()
    expect(grid_btn).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("lib-book-grid")).to_be_visible()


LOCALE_SORT_JS = "(titles) => [...titles].sort((a, b) => a.localeCompare(b))"


def test_sort_changes_visible_order(page: Any) -> None:
    """FB-L10: the sort control really reorders the cards (A->Z by title, the legacy action)."""
    before = page.evaluate(sl.VISIBLE_CARD_TITLES_JS)
    want = page.evaluate(LOCALE_SORT_JS, before)
    assert before != want, f"server order is already A->Z, the check would be vacuous: {before}"
    page.get_by_test_id("lib-toolbar-sort").click()
    after = page.evaluate(sl.VISIBLE_CARD_TITLES_JS)
    assert after == want, (before, after)
    page.get_by_test_id("lib-toolbar-view-list").click()
    rows = [r.get_attribute(sl.DATA_TITLE) for r in page.get_by_test_id("lib-book-row").all()]
    assert rows == want, f"list view order diverged from grid: {rows}"


def test_search_debounced_single_request_and_clear(page: Any) -> None:
    page.get_by_test_id("lib-panel-tab-search").click()
    log = ss.RequestLog(page).start()
    # SEPARATION-BROKEN (013 WI-13, coordinator-approved): the query was "twenty", which occurs
    # only in a book title; the frozen corpus's chapter text is "Alpha prose." / "Beta prose.",
    # so the frozen API answered 0 hits for any implementation. "prose" is in the chapter text.
    # The rendered-hit assertion is kept and tightened to "at least one"; the single-request
    # and clear assertions below are unchanged.
    page.get_by_test_id("lib-search-input").press_sequentially("prose", delay=20)
    hits = page.get_by_test_id("lib-search-hit")
    expect(hits.first).to_be_visible()
    assert hits.count() >= 1, "no search hit rendered for a word in the corpus chapter text"
    time.sleep(0.5)
    searches = [i for i in log.items if i[1] == "/api/search/library"]
    assert len(searches) == 1, f"{len(searches)} search requests for one settled query"
    page.get_by_test_id("lib-search-clear").click()
    expect(page.get_by_test_id("lib-search-input")).to_have_value("")
    expect(hits).to_have_count(0)


# ---------------------------------------------------------------------------
# C13.16
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", [sl.KEY_ENTER, sl.KEY_SPACE])
def test_card_link_keyboard_activation(page: Any, key: str) -> None:
    link = page.get_by_role("link", name=f"Read {EPUB2_TITLE}")
    link.focus()
    with page.expect_navigation():
        page.keyboard.press(key)
    assert re.search(rf"/read/{BOOK_ID}/0$", page.url), page.url


def test_landmarks_heading_and_current_nav(page: Any) -> None:
    headings, mains = page.evaluate(sl.LANDMARKS_JS)
    assert mains == 1, f"{mains} main landmarks"
    assert headings and headings[0] == H1, f"first heading is {headings[:1]}"
    assert sum(1 for h in headings if h == H1) == 1
    expect(page.get_by_test_id("lib-topbar-nav-library")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("lib-topbar-nav-settings")).not_to_have_attribute("aria-current", "page")
    expect(page.get_by_role("link", name=f"Read {EPUB3_TITLE}")).to_have_count(1)
