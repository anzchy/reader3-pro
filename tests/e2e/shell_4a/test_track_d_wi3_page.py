"""013 WI-13 hosts Track-D WI-3 #2-#4, #6, #7 on the real library page (C13.18, C13.19).

Status is driven through the real `GET /api/index/{id}/status` by writing each book's
`chroma_db/index_meta.json` (`shell_4a_library.index_meta`); nothing on that path is mocked.
Two rounds cover the six states over the four session books:

    round A: indexed / indexing / error / stale
    round B: not_indexed / unknown (out-of-enum status "bogus") / unknown (unreadable meta) / not_indexed

Only `POST /api/index/{id}` is intercepted in C13.19 (real indexing needs the embedding model
and egress); the handler also writes an up-to-date meta, which is what a real rebuild leaves
behind, so the page's follow-up status fetch sees the book as indexed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
from conftest import BOOK_ID, BOOK_ID_2, BOOK_ID_CJK, BOOK_ID_REPEAT
from playwright.sync_api import expect

pytestmark = [pytest.mark.shell_4a, pytest.mark.track_d_013]

ARIA_BUSY = "aria-busy"

ROUND_A = {BOOK_ID: "indexed", BOOK_ID_2: "indexing", BOOK_ID_CJK: "error", BOOK_ID_REPEAT: "stale"}
ROUND_B = {BOOK_ID: "not_indexed", BOOK_ID_2: "raw:bogus", BOOK_ID_CJK: "unknown", BOOK_ID_REPEAT: "not_indexed"}


def _expected(state: str) -> str:
    return "unknown" if state.startswith("raw:") else state


@pytest.fixture
def context(browser: Any) -> Iterator[Any]:
    ctx = s4.new_gated_context(browser)
    try:
        yield ctx
    finally:
        ctx.close()


def _pill(page: Any, view: str, state: str, book_id: str) -> Any:
    table = sl.GRID_STATUS_TESTIDS if view == "grid" else sl.ROW_STATUS_TESTIDS
    return page.locator(f'[data-testid="{table[state]}"][data-book-id="{book_id}"]')


def _render_round(context: Any, live_server: str, books_dir: Path, statuses: Dict[str, str]) -> Dict[str, str]:
    """{book_id: grid testid} for one round, after asserting pill text in both views."""
    seen: Dict[str, str] = {}
    with sl.index_meta(books_dir, statuses):
        page = sl.open_library(context, live_server)
        for book_id, raw in statuses.items():
            state = _expected(raw)
            for view in ("grid", "row"):
                pill = _pill(page, view, state, book_id)
                expect(pill, f"{book_id} {view} pill for {raw}").to_have_count(1)
                expect(pill).to_have_text(sl.STATUS_LABELS[state])
            seen[book_id] = sl.GRID_STATUS_TESTIDS[state]
        page.close()
    return seen


def test_six_states_render_six_distinct_testids(context: Any, live_server: str, e2e_books_dir: Path) -> None:
    """[track_d_013 WI-3#2] five real states plus unknown render six distinct testids."""
    a = _render_round(context, live_server, e2e_books_dir, ROUND_A)
    b = _render_round(context, live_server, e2e_books_dir, ROUND_B)
    ids = set(a.values()) | set(b.values())
    assert ids == set(sl.GRID_STATUS_TESTIDS.values()), sorted(ids)
    assert len(ids) == 6


def test_out_of_enum_status_is_unknown_not_not_indexed(context: Any, live_server: str, e2e_books_dir: Path) -> None:
    """[track_d_013 WI-3#3] an out-of-enum status renders 「状态未知」, never the not-indexed text."""
    errors: List[str] = []
    with sl.index_meta(e2e_books_dir, {BOOK_ID_2: "raw:bogus", BOOK_ID_CJK: "unknown"}):
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(live_server + sl.LIBRARY_PATH, wait_until="load")
        page.wait_for_function(sl.ALL_PILLS_RESOLVED_JS)
        for book_id in (BOOK_ID_2, BOOK_ID_CJK):
            pill = _pill(page, "grid", "unknown", book_id)
            expect(pill).to_have_text("状态未知")
            assert "未索引" not in (pill.text_content() or "")
            expect(_pill(page, "grid", "not_indexed", book_id)).to_have_count(0)
    assert errors == [], f"the page threw on an unknown status: {errors}"


def test_unknown_offers_no_start_index(context: Any, live_server: str, e2e_books_dir: Path) -> None:
    """[track_d_013 WI-3#4] no 「开始索引」 action for an unknown book (a not-indexed one has it)."""
    with sl.index_meta(e2e_books_dir, ROUND_B):
        page = sl.open_library(context, live_server)
        page.get_by_test_id("lib-toolbar-view-list").click()
        for book_id in ROUND_B:
            row = page.locator(f'[data-testid="lib-book-row"][data-book-id="{book_id}"]')
            starts = row.get_by_role("button", name=re.compile(r"^开始索引"))
            want = 1 if ROUND_B[book_id] == "not_indexed" else 0
            expect(starts, f"{book_id} ({ROUND_B[book_id]})").to_have_count(want)


def test_s2_banner_inside_search_panel_with_border(context: Any, live_server: str, e2e_books_dir: Path) -> None:
    """[track_d_013 WI-3#6] a stale book raises lib-degrade-s2 at the top of the search panel, bordered."""
    with sl.index_meta(e2e_books_dir, {BOOK_ID_REPEAT: "stale"}):
        page = sl.open_library(context, live_server)
        page.get_by_test_id("lib-panel-tab-search").click()
        banner = page.get_by_test_id("lib-degrade-s2")
        expect(banner).to_have_count(1)
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("索引已过期")
        assert page.evaluate(sl.CONTAINS_JS, ["lib-panel-search", "lib-degrade-s2"]), "banner is not in the search panel"
        border, _, style, width = banner.evaluate(sl.BORDER_JS)
        assert style != "none" and width != "0px", (style, width)
        assert border not in ("transparent", "rgba(0, 0, 0, 0)"), border
        expect(page.get_by_test_id("lib-degrade-s2-reindex")).to_have_count(1)


def test_s2_reindex_single_flight(context: Any, live_server: str, e2e_books_dir: Path) -> None:
    """[track_d_013 WI-3#7] three fast clicks on lib-degrade-s2-reindex send one rebuild request."""
    posts: List[Dict[str, Any]] = []
    held: List[Any] = []

    def _handle(route: Any, request: Any) -> None:
        if request.method != "POST":
            route.continue_()
            return
        posts.append({"path": request.url, "body": json.loads(request.post_data or "{}")})
        held.append(route)  # answered later from the test body: the request stays in flight

    with sl.index_meta(e2e_books_dir, {BOOK_ID_REPEAT: "stale"}):
        page = sl.open_library(context, live_server)
        page.get_by_test_id("lib-panel-tab-search").click()
        live_before = page.get_by_test_id("lib-live-region").text_content() or ""
        page.route(f"**/api/index/{BOOK_ID_REPEAT}", _handle)
        button = page.get_by_test_id("lib-degrade-s2-reindex")
        button.evaluate("(b) => { b.click(); b.click(); b.click(); }")
        expect(button).to_have_attribute(ARIA_BUSY, "true")
        page.wait_for_timeout(300)
        assert len(posts) == 1, f"{len(posts)} rebuild requests while the first is in flight"
        assert posts[0]["body"] == {"force_reindex": True}
        # what a real rebuild leaves behind, then the response
        meta = e2e_books_dir / BOOK_ID_REPEAT / "chroma_db" / "index_meta.json"
        meta.write_text(sl._meta_for(BOOK_ID_REPEAT, "indexed"), encoding="utf-8")
        held[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"book_id": BOOK_ID_REPEAT, "status": "indexed", "chunk_count": 7}),
        )
        expect(page.get_by_test_id("lib-degrade-s2")).to_have_count(0)
        assert len(posts) == 1
        live_after = page.get_by_test_id("lib-live-region").text_content() or ""
        assert live_after and live_after != live_before, "the rebuild was not announced"
        expect(_pill(page, "grid", "indexed", BOOK_ID_REPEAT)).to_have_count(1)
