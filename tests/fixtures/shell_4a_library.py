"""013 WI-13 (4A.4 library page slice) shared helpers for `tests/e2e/shell_4a/test_library_*.py`
and `tests/e2e/shell_4a/test_track_d_wi{1,3}_page.py`.

Group directories cannot hold a `conftest.py` (see `scripts/lint_e2e_groups.py`), so the helpers
live here, next to `shell_4a_settings.py`. `tests/fixtures/` is on `sys.path` through
`tests/conftest.py`.

What is here:

    LIBRARY_PATH / VIEWPORTS / STATUS_*          page constants (no selectors are built here)
    index_meta(books_dir, statuses)             write `chroma_db/index_meta.json` per book, then
                                                remove exactly what was written (the session
                                                library is shared; the baseline expects every
                                                book `not_indexed`)
    open_library(context, base_url)             a library page with every status pill resolved
    in_viewport / hit_test / column_of          geometry and hit-testing probes (JS strings)

**Why meta files and not a mock.** `GET /api/index/{id}/status` derives every one of the six
states from the file `BookVectorIndex.status()` reads: absent -> not_indexed, unreadable ->
unknown, `status` passed through for indexing / error, a model-name mismatch -> stale. Writing
the file drives the real route; only `POST /api/index/{id}` (real indexing needs the embedding
model and egress) is intercepted, and each test that does so says so.
"""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Tuple

from playwright.sync_api import expect

from reader3_app.vector_search import MODEL_NAME, SPACE

LIBRARY_PATH = "/"
SETTINGS_PATH = "/settings"

VIEWPORT_MOBILE: Dict[str, int] = {"width": 390, "height": 844}
VIEWPORT_TABLET: Dict[str, int] = {"width": 1024, "height": 768}
VIEWPORT_DESKTOP: Dict[str, int] = {"width": 1440, "height": 900}
VIEWPORTS: Tuple[Dict[str, int], ...] = (VIEWPORT_MOBILE, VIEWPORT_TABLET, VIEWPORT_DESKTOP)

#: The six states the library renders (ruling D12 / C8): five real server states plus unknown.
STATES: Tuple[str, ...] = ("not_indexed", "indexing", "indexed", "error", "stale", "unknown")

#: Production bounded tables (ruling D12, C8 naming): literal names, one per (view, state).
GRID_STATUS_TESTIDS: Mapping[str, str] = {
    "not_indexed": "lib-book-grid-status-not-indexed",
    "indexing": "lib-book-grid-status-indexing",
    "indexed": "lib-book-grid-status-indexed",
    "error": "lib-book-grid-status-error",
    "stale": "lib-book-grid-status-stale",
    "unknown": "lib-book-grid-status-unknown",
}
ROW_STATUS_TESTIDS: Mapping[str, str] = {
    "not_indexed": "lib-book-row-status-not-indexed",
    "indexing": "lib-book-row-status-indexing",
    "indexed": "lib-book-row-status-indexed",
    "error": "lib-book-row-status-error",
    "stale": "lib-book-row-status-stale",
    "unknown": "lib-book-row-status-unknown",
}

#: The visible labels (Track-D WI-3 #3: unknown reads 「状态未知」 and is not the not-indexed text).
STATUS_LABELS: Mapping[str, str] = {
    "not_indexed": "未索引",
    "indexing": "索引中…",
    "indexed": "已索引",
    "error": "索引失败",
    "stale": "索引已过期",
    "unknown": "状态未知",
}

#: Key names go through constants: `lint_e2e_selectors.py` treats the first string literal of
#: `.press(` as a selector.
KEY_TAB = "Tab"
KEY_ENTER = "Enter"
KEY_SPACE = "Space"


def _meta_for(book_id: str, state: str) -> str:
    base: Dict[str, Any] = {
        "book_id": book_id,
        "chunk_count": 7,
        "model_name": MODEL_NAME,
        "space": SPACE,
        "indexed_at": "2026-09-25T00:00:00+00:00",
    }
    if state == "indexed":
        return json.dumps({**base, "status": "indexed"})
    if state == "indexing":
        return json.dumps({**base, "status": "indexing", "chunk_count": None})
    if state == "error":
        return json.dumps({**base, "status": "error", "chunk_count": None})
    if state == "stale":
        # an index built by another embedding model: the route reports not_indexed + stale:true
        return json.dumps({**base, "status": "indexed", "model_name": "retired-model-v0"})
    if state == "unknown":
        return "{ this is not json"
    if state.startswith("raw:"):
        # an out-of-enum status the server passes through verbatim (Track-D WI-3 #3)
        return json.dumps({**base, "status": state[len("raw:"):]})
    raise ValueError(f"no meta for state {state!r}")


@contextmanager
def index_meta(books_dir: Path, statuses: Mapping[str, str]) -> Iterator[None]:
    """Write one `index_meta.json` per book (state `not_indexed` writes nothing).

    Only a `chroma_db/` directory this helper created is removed afterwards; one that existed
    before is left exactly as it was apart from the meta file, which is restored.
    """
    created: List[Path] = []
    restored: List[Tuple[Path, bytes]] = []
    try:
        for book_id, state in statuses.items():
            if state == "not_indexed":
                continue
            chroma = books_dir / book_id / "chroma_db"
            meta = chroma / "index_meta.json"
            if chroma.exists():
                if meta.exists():
                    restored.append((meta, meta.read_bytes()))
            else:
                chroma.mkdir(parents=True)
                created.append(chroma)
            meta.write_text(_meta_for(book_id, state), encoding="utf-8")
        yield
    finally:
        for path in created:
            shutil.rmtree(path, ignore_errors=True)
        for path, data in restored:
            path.write_bytes(data)


#: Resolves once every book card's grid pill carries a status testid (the status fetch is done).
ALL_PILLS_RESOLVED_JS = """() => {
  const cards = [...document.querySelectorAll('[data-testid="lib-book-card"]')];
  return cards.length > 0 && cards.every((card) => {
    const id = card.getAttribute("data-book-id");
    return [...document.querySelectorAll('[data-book-id]')].some((el) =>
      el !== card && card.contains(el) &&
      (el.getAttribute("data-testid") || "").startsWith("lib-book-grid-status-") &&
      el.getAttribute("data-book-id") === id);
  });
}"""


def open_library(context: Any, base_url: str, *, wait_status: bool = True) -> Any:
    page = context.new_page()
    page.goto(base_url + LIBRARY_PATH, wait_until="load")
    expect(page.get_by_test_id("lib-shell")).to_have_count(1)
    if wait_status:
        page.wait_for_function(ALL_PILLS_RESOLVED_JS)
    return page


#: [left, top, right, bottom, visible-by-CSS] of a located element.
RECT_JS = """(el) => {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return [r.left, r.top, r.right, r.bottom, cs.visibility !== "hidden" && cs.display !== "none"];
}"""

#: True when the element at the centre of `el` is `el` or one of its descendants.
HIT_TEST_JS = """(el) => {
  const r = el.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return hit !== null && el.contains(hit);
}"""


def rect(locator: Any) -> Tuple[float, float, float, float, bool]:
    return tuple(locator.evaluate(RECT_JS))


def assert_reachable(page: Any, locator: Any, what: str, slack: float = 2.0) -> None:
    """Geometry, visibility, hit-test and actionability together (C13.02)."""
    expect(locator, f"{what} is not visible").to_be_visible()
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    left, top, right, bottom, shown = rect(locator)
    assert shown, f"{what} is hidden by CSS"
    assert left >= -slack and top >= -slack and right <= vw + slack and bottom <= vh + slack, (
        f"{what} rect {(left, top, right, bottom)} is outside the {vw}x{vh} viewport"
    )
    assert locator.evaluate(HIT_TEST_JS), f"{what} is covered at its centre"
    locator.click(trial=True, timeout=3000)


#: No horizontal overflow at the document level.
NO_H_OVERFLOW_JS = """() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"""

#: Replace the title text of every book card and row with `text` (C13.04 long content). No
#: selector: the text nodes equal to the card's own title are rewritten in place.
LONG_TITLES_JS = """(text) => {
  for (const el of document.querySelectorAll('[data-testid="lib-book-card"], [data-testid="lib-book-row"]')) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const title = (el.getAttribute("data-title") || "").trim();
    let node;
    while ((node = walker.nextNode())) {
      if (title && node.nodeValue.trim().toLowerCase() === title) node.nodeValue = text;
    }
  }
}"""


#: Every `data-testid` value rendered on the page, in document order (C13.12).
RENDERED_TESTIDS_JS = """() => [...document.querySelectorAll('[data-testid]')].map((el) => el.getAttribute('data-testid'))"""

#: `[min-width, width]` of a located element (C13.01).
MIN_WIDTH_JS = """(el) => [getComputedStyle(el).minWidth, el.getBoundingClientRect().width]"""

#: Number of tracks in a grid container's resolved `grid-template-columns`.
GRID_TRACKS_JS = """(el) => getComputedStyle(el).gridTemplateColumns.split(/\\s+/).filter(Boolean).length"""

#: `[border-top-color, color, border-top-style, border-top-width]` of a located element.
BORDER_JS = """(el) => { const cs = getComputedStyle(el);
  return [cs.borderTopColor, cs.color, cs.borderTopStyle, cs.borderTopWidth]; }"""

#: Colour a CSS custom property resolves to on this page (through a probe's `color`).
RESOLVE_TOKEN_COLOR_JS = """(name) => { const p = document.createElement('span');
  document.body.appendChild(p); p.style.color = `var(${name})`;
  const v = getComputedStyle(p).color; p.remove(); return v; }"""

#: The DegradeBanner's danger tone as the built CSS paints it (WI-1 #1). The library page can
#: raise only the warn banner in 013 (DEG-S3 is deferred by D12), so the danger root is built
#: here with the component's own class contract (asserted in degrade-banner.test.ts:
#: `r3-degrade-banner r3-degrade-banner--danger`) inside the live page and its bundle, then
#: removed. Returns `[border-top-color, color, border-top-style]`.
DANGER_TONE_PROBE_JS = """() => { const s = document.createElement('section');
  s.className = 'r3-degrade-banner r3-degrade-banner--danger';
  s.setAttribute('aria-hidden', 'true');
  document.body.appendChild(s); const cs = getComputedStyle(s);
  const out = [cs.borderTopColor, cs.color, cs.borderTopStyle]; s.remove(); return out; }"""

#: How many `aria-live` regions (the element itself carrying `aria-live`, or `role=status`
#: / `role=alert`, which imply it) have text containing `needle` (WI-1 #3).
LIVE_REGIONS_WITH_TEXT_JS = """(needle) => [...document.querySelectorAll('[aria-live], [role="status"], [role="alert"]')]
  .filter((el) => (el.getAttribute('aria-live') || 'polite') !== 'off')
  .filter((el) => (el.textContent || '').includes(needle)).length"""

#: True when `outer` (testid) contains `inner` (testid).
CONTAINS_JS = """([outer, inner]) => { const o = document.querySelector(`[data-testid="${outer}"]`);
  const i = document.querySelector(`[data-testid="${inner}"]`); return !!(o && i && o.contains(i)); }"""

#: The element that has focus is inside the element with testid `id`.
FOCUS_INSIDE_JS = """(id) => { const o = document.querySelector(`[data-testid="${id}"]`);
  return !!(o && document.activeElement && o.contains(document.activeElement)); }"""

#: The attribute that carries a card's / row's title (lower-cased, for filter and sort).
DATA_TITLE = "data-title"

#: Titles (`data-title`) of the book cards that are shown, in visual (DOM) order.
VISIBLE_CARD_TITLES_JS = """() => [...document.querySelectorAll('[data-testid="lib-book-card"]')]
  .filter((el) => !el.hidden && el.getClientRects().length > 0).map((el) => el.getAttribute('data-title'))"""

#: `[tagName, textContent]` of every heading in document order, and the number of `main` landmarks.
LANDMARKS_JS = """() => [[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) => h.tagName),
  document.querySelectorAll('main, [role="main"]').length]"""

#: Per-card overflow: cards whose rect leaves their grid container horizontally.
CARDS_OUTSIDE_TRACK_JS = """() => { const g = document.querySelector('[data-testid="lib-book-grid"]');
  if (!g || g.getClientRects().length === 0) return [];
  const gr = g.getBoundingClientRect();
  return [...g.querySelectorAll('[data-testid="lib-book-card"]')].filter((c) => {
    const r = c.getBoundingClientRect(); return r.left < gr.left - 1 || r.right > gr.right + 1; })
    .map((c) => c.getAttribute('data-book-id')); }"""
