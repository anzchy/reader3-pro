"""013 WI-10 A10.9 (C10.15, C10.22): the FOUC stamp over the whole storage domain.

The stamp maps (stored `reader3.ui.colorScheme`, stored `reader3.reader.theme`) to the
two `<html>` attributes. Oracle: `shell_4a_theme.expected_stamp` -- `data-theme` absent
for absent / `system` / anything unknown, else the stored value; `data-reading-theme`
`auto` for absent / unknown, else the stored value.

Two samples per (page, storage row), 3 pages x 25 rows:

* **C10.15, at DOMContentLoaded** -- a capturing listener registered by an init script.
  This alone does NOT catch a stamp moved into a `type=module` / `defer` script: those
  also run before DOMContentLoaded.
* **C10.22, at `<body>` insertion and at the first stylesheet** -- a MutationObserver
  registered BEFORE the storage seeding. The parser performs a microtask checkpoint
  before it runs any parser-inserted script, so the observer's records are delivered
  before a late stamp could run; a module / defer / body-end stamp therefore leaves the
  unstamped values in `__atBody`. The first `<link rel=stylesheet>` sample is the
  timeline half: the stamp must already have run when CSS starts arriving.

No uncaught page error on any row, including pages without a reader shell.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

import pytest
import shell_4a_fixtures as s4
import shell_4a_theme as th
from conftest import BOOK_ID

pytestmark = pytest.mark.shell_4a

PAGES = ("library", "reader", "settings")

DCL_SAMPLER = """(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const h = document.documentElement;
    window.__atDCL = [h.dataset.theme ?? null, h.dataset.readingTheme ?? null];
  }, { capture: true, once: true });
})();"""

BODY_SAMPLER = """(() => {
  const sample = () => {
    const h = document.documentElement;
    return h ? [h.dataset.theme ?? null, h.dataset.readingTheme ?? null] : [null, null];
  };
  const isSheet = (n) => n.nodeName === "LINK" && n.relList.contains("stylesheet");
  const obs = new MutationObserver((records) => {
    for (const rec of records) {
      for (const n of rec.addedNodes) {
        if (window.__atFirstSheet === undefined && isSheet(n)) window.__atFirstSheet = sample();
        if (window.__atBody === undefined && n === document.body) window.__atBody = sample();
      }
    }
    if (window.__atBody !== undefined && window.__atFirstSheet !== undefined) obs.disconnect();
  });
  obs.observe(document, { childList: true, subtree: true });
})();"""


def _row_id(row: tuple) -> str:
    return f"{row[0]}|{row[1]}"


def _run_rows(
    browser: Any,
    base_url: str,
    page_name: str,
    before: List[str],
    after: List[str],
    expr: str,
    expected_of: Callable[[List[Optional[str]]], Any],
) -> List[str]:
    """Load the page once per storage row (fresh context each); return mismatches and page errors.

    Init scripts run in registration order: `before`, then the storage seeding, then `after`.
    """
    problems: List[str] = []
    for cs, rd in th.STORAGE_ROWS:
        expected = expected_of(th.expected_stamp(cs, rd))
        context = s4.new_gated_context(
            browser, init_scripts=[*before, th.storage_init_script(cs, rd), *after]
        )
        try:
            page = context.new_page()
            errors: List[str] = []
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            page.goto(base_url + s4.page_path(page_name, BOOK_ID), wait_until="load")
            got = page.evaluate(expr)
            if got != expected:
                problems.append(f"{_row_id((cs, rd))}: {got!r} != expected {expected!r}")
            if errors:
                problems.append(f"{_row_id((cs, rd))}: page errors {errors}")
        finally:
            context.close()
    return problems


@pytest.mark.parametrize("page_name", PAGES)
def test_stamp_at_dom_content_loaded(browser: Any, live_server: str, page_name: str) -> None:
    problems = _run_rows(
        browser, live_server, page_name, [], [DCL_SAMPLER], "window.__atDCL", lambda e: e
    )
    assert problems == []


@pytest.mark.parametrize("page_name", PAGES)
def test_stamp_before_body_and_stylesheets(browser: Any, live_server: str, page_name: str) -> None:
    # The observer is registered BEFORE the storage seeding (matrix C10.22).
    problems = _run_rows(
        browser,
        live_server,
        page_name,
        [BODY_SAMPLER],
        [],
        "[window.__atBody === undefined ? 'observer-did-not-fire' : window.__atBody,"
        " window.__atFirstSheet === undefined ? 'no-stylesheet' : window.__atFirstSheet]",
        lambda e: [e, e],
    )
    assert problems == []
