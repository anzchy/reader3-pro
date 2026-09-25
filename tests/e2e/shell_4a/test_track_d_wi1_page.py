"""013 WI-13 hosts Track-D WI-1 #1 and #3 on the real library page (C13.26, reduced by D12).

The library raises its DEG-S2 banner (warn) from a real stale status. DEG-S3 / DEG-S4 are
deferred by ruling D12, so the page cannot raise a danger banner in 013; for row 1 the danger
tone is read from the same built bundle through `DANGER_TONE_PROBE_JS`, which builds a root
with the component's own class contract (the contract itself is asserted in
`frontend/tests/components/degrade-banner.test.ts`: "danger variants carry the danger
modifier"). That probe is the one mock boundary here.

* WI-1 #1: warn and danger `border-color` differ, neither is transparent; each border equals
  its own foreground and resolves to its tone token (warn -> `--r3-warning`, danger ->
  `--r3-error`), and neither is the accent.
* WI-1 #3: the banner's text is carried by exactly one live region (the banner itself), not
  re-announced through `lib-live-region`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
from conftest import BOOK_ID_REPEAT
from playwright.sync_api import expect

pytestmark = [pytest.mark.shell_4a, pytest.mark.track_d_013]

TRANSPARENT = ("transparent", "rgba(0, 0, 0, 0)")
S2_PHRASE = "索引已过期"


@pytest.fixture
def stale_page(browser: Any, live_server: str, e2e_books_dir: Path) -> Iterator[Any]:
    context = s4.new_gated_context(browser)
    try:
        with sl.index_meta(e2e_books_dir, {BOOK_ID_REPEAT: "stale"}):
            page = sl.open_library(context, live_server)
            page.get_by_test_id("lib-panel-tab-search").click()
            expect(page.get_by_test_id("lib-degrade-s2")).to_be_visible()
            yield page
    finally:
        context.close()


def test_warn_and_danger_borders_differ_and_follow_tone(stale_page: Any) -> None:
    """[track_d_013 WI-1#1] warn and danger border colours differ, neither transparent."""
    page = stale_page
    warn_border, warn_fg, warn_style, _ = page.get_by_test_id("lib-degrade-s2").evaluate(sl.BORDER_JS)
    danger_border, danger_fg, danger_style = page.evaluate(sl.DANGER_TONE_PROBE_JS)
    assert warn_style != "none" and danger_style != "none", (warn_style, danger_style)
    assert warn_border not in TRANSPARENT and danger_border not in TRANSPARENT
    assert warn_border != danger_border, f"both tones paint {warn_border}"
    assert warn_border == warn_fg and danger_border == danger_fg, "border must equal the tone foreground"
    warning, error, accent = (page.evaluate(sl.RESOLVE_TOKEN_COLOR_JS, n) for n in ("--r3-warning", "--r3-error", "--r3-accent"))
    assert warn_border == warning, (warn_border, warning)
    assert danger_border == error, (danger_border, error)
    assert accent not in (warn_border, danger_border)


def test_banner_text_in_one_live_region(stale_page: Any) -> None:
    """[track_d_013 WI-1#3] the degrade copy is carried by one live region, not re-announced."""
    page = stale_page
    assert page.evaluate(sl.LIVE_REGIONS_WITH_TEXT_JS, S2_PHRASE) == 1
    expect(page.get_by_test_id("lib-live-region")).not_to_contain_text(S2_PHRASE)
    banner = page.get_by_test_id("lib-degrade-s2")
    expect(banner).to_have_attribute("role", "status")
