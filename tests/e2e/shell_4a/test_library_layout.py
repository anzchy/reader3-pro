"""013 WI-13 A13.1-A13.3 (C13.01-C13.04): the library's three-column shell.

* 1440x900: sidebar / main / right panel are all visible, disjoint, in that order, and each
  column's `min-width` is `0px` (a long title cannot push a column wider than its track).
* 390x844: the sidebar and the right panel are drawers behind `lib-topbar-mobile-menu` and
  `lib-topbar-mobile-insights`; once opened, `lib-sidebar-create-collection` and the right
  panel's content are reachable (geometry + visibility + hit-test + trial click). The book grid
  has two tracks.
* 1024x768: the right panel is a drawer; `aria-expanded` follows its visibility over three
  open/close pairs and focus moves inside when it opens.
* No horizontal overflow at any of the three viewports, even with very long titles, and every
  card stays inside the grid.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

COLUMNS = ("lib-sidebar", "lib-main", "lib-insights")
LONG = "Supercalifragilisticexpialidocious-" * 8


@pytest.fixture
def open_at(browser: Any, live_server: str) -> Iterator[Any]:
    contexts: List[Any] = []

    def _open(viewport: Dict[str, int]) -> Any:
        context = s4.new_gated_context(browser)
        contexts.append(context)
        page = sl.open_library(context, live_server)
        page.set_viewport_size(viewport)
        return page

    try:
        yield _open
    finally:
        for c in contexts:
            c.close()


def test_three_columns_visible_min_width_zero_at_1440(open_at: Any) -> None:
    page = open_at(sl.VIEWPORT_DESKTOP)
    rects = []
    for tid in COLUMNS:
        loc = page.get_by_test_id(tid)
        expect(loc).to_be_visible()
        min_width, width = loc.evaluate(sl.MIN_WIDTH_JS)
        assert min_width == "0px", f"{tid} min-width is {min_width}"
        assert width > 0, f"{tid} has no width"
        rects.append(sl.rect(loc))
    for (a, b) in zip(rects, rects[1:]):
        assert a[2] <= b[0] + 1, f"columns overlap or are out of order: {rects}"


def test_mobile_drawers_make_targets_reachable(open_at: Any) -> None:
    page = open_at(sl.VIEWPORT_MOBILE)
    menu = page.get_by_test_id("lib-topbar-mobile-menu")
    sl.assert_reachable(page, menu, "mobile menu toggle")
    expect(menu).to_have_attribute("aria-expanded", "false")
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")
    sl.assert_reachable(page, page.get_by_test_id("lib-sidebar-create-collection"), "create collection")
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "false")

    insights = page.get_by_test_id("lib-topbar-mobile-insights")
    sl.assert_reachable(page, insights, "mobile insights toggle")
    insights.click()
    expect(insights).to_have_attribute("aria-expanded", "true")
    panel = page.get_by_test_id("lib-right-panel")
    expect(panel).to_be_visible()
    left, top, right, bottom, _ = sl.rect(panel)
    vw = sl.VIEWPORT_MOBILE["width"]
    assert left >= -2 and right <= vw + 2, f"right panel content {left}..{right} is outside 0..{vw}"
    sl.assert_reachable(page, page.get_by_test_id("lib-panel-tab-search"), "right panel search tab")
    sl.assert_reachable(page, page.get_by_test_id("lib-panel-refresh-stats"), "right panel refresh")
    insights.click()

    tracks = page.get_by_test_id("lib-book-grid").evaluate(sl.GRID_TRACKS_JS)
    assert tracks == 2, f"the book grid has {tracks} tracks at 390"


def test_tablet_right_drawer_state_and_focus(open_at: Any) -> None:
    page = open_at(sl.VIEWPORT_TABLET)
    toggle = page.get_by_test_id("lib-topbar-mobile-insights")
    panel = page.get_by_test_id("lib-right-panel")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(panel).to_be_hidden()
    expect(page.get_by_test_id("lib-sidebar")).to_be_visible()
    for _ in range(3):
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(panel).to_be_visible()
        assert page.evaluate(sl.FOCUS_INSIDE_JS, "lib-right-panel"), "focus did not move into the drawer"
        sl.assert_reachable(page, page.get_by_test_id("lib-panel-tab-chat"), "drawer tab")
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(panel).to_be_hidden()


@pytest.mark.parametrize("viewport", sl.VIEWPORTS, ids=lambda v: f"{v['width']}x{v['height']}")
def test_no_horizontal_overflow_with_long_titles(open_at: Any, viewport: Dict[str, int]) -> None:
    page = open_at(viewport)
    page.evaluate(sl.LONG_TITLES_JS, LONG)
    scroll_w, client_w = page.evaluate(sl.NO_H_OVERFLOW_JS)
    assert scroll_w <= client_w, f"document overflows horizontally: {scroll_w} > {client_w}"
    assert page.evaluate(sl.CARDS_OUTSIDE_TRACK_JS) == []
    page.get_by_test_id("lib-toolbar-view-list").click()
    expect(page.get_by_test_id("lib-book-table")).to_be_visible()
    scroll_w, client_w = page.evaluate(sl.NO_H_OVERFLOW_JS)
    assert scroll_w <= client_w, f"list view overflows the document: {scroll_w} > {client_w}"
