"""013 WI-12 A12.2 / FB-S05 (C12.01) and FP-15 (C12.02): per-action destructive dialogs.

Each destructive action `set-data-X` (X = reindex / conversations / cache) opens its own
native `<dialog>` `set-modal-X` (user ruling D10: per-action dialogs, ADR-0014 and the
prototype's `MODAL_TESTIDS`).

What "one request" means per action:

* conversations / cache clear an IndexedDB store in this browser (`conversations` /
  `summaries`, the legacy `settings.js` stores). The effect is counted at the storage API:
  `IDBObjectStore.prototype.clear` is wrapped by an init script, and the seeded record must
  survive cancel and be gone after primary.
* reindex: user ruling D11 (2026-09-25) defers the server-effect half (backend debt "bulk
  reindex route"). Its primary shows a visible 「暂不支持」 line and sends 0 requests.

Network requests are counted from the moment the page is rendered: none of the three
actions may touch the network, on any path.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
import shell_4a_fixtures as s4
import shell_4a_settings as ss
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

ACTIONS = ("reindex", "conversations", "cache")
STORE = {"conversations": "conversations", "cache": "summaries"}
KEY_PATH = {"conversations": "id", "cache": "cache_key"}

#: Wraps IDBObjectStore.clear so every call is recorded by store name.
CLEAR_COUNTER_JS = r"""
(() => {
  window.__r3Clears = [];
  const orig = IDBObjectStore.prototype.clear;
  IDBObjectStore.prototype.clear = function (...args) {
    window.__r3Clears.push(this.name);
    return orig.apply(this, args);
  };
})();
"""

#: Opens the assistant DB with the schema the app uses, puts one record, returns the count.
SEED_JS = r"""
async ([name, version, store, keyPath]) => {
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open(name, version);
    req.onupgradeneeded = () => {
      const d = req.result;
      if (!d.objectStoreNames.contains("conversations")) {
        const s = d.createObjectStore("conversations", { keyPath: "id" });
        s.createIndex("book_uuid", "book_uuid", { unique: false });
        s.createIndex("book_uuid_provider", ["book_uuid", "provider"], { unique: false });
      }
      if (!d.objectStoreNames.contains("summaries")) {
        const s = d.createObjectStore("summaries", { keyPath: "cache_key" });
        s.createIndex("book_uuid", "book_uuid", { unique: false });
      }
    };
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
  });
  const record = { book_uuid: "wi12-seed", provider: "ollama" };
  record[keyPath] = "wi12-seed-record";
  await new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return true;
}
"""

COUNT_JS = r"""
async ([name, version, store]) => {
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open(name, version);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
  });
  const n = await new Promise((resolve, reject) => {
    const req = db.transaction(store, "readonly").objectStore(store).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return n;
}
"""

#: Counts the dialog's tabbable controls; the count sizes the Tab loop below.
FOCUSABLE_COUNT_JS = "(el) => el.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select, textarea').length"  # lint-e2e-selectors: allow —— FP-15：数弹层里可 Tab 到的控件个数，用来定 Tab 次数，不是定位
TRIPLE_CLICK_JS = "(el) => { el.click(); el.click(); el.click(); }"
CONTAINS_FOCUS_JS = "(el) => el.contains(document.activeElement) && document.activeElement !== el"


@pytest.fixture
def settings_page(browser: Any, live_server: str) -> Iterator[Any]:
    context = s4.new_gated_context(browser, init_scripts=[CLEAR_COUNTER_JS])
    try:
        yield ss.open_settings(context, live_server)
    finally:
        context.close()


def _store_count(page: Any, action: str) -> int:
    return page.evaluate(COUNT_JS, [ss.IDB_NAME, ss.IDB_VERSION, STORE[action]])


def _clears(page: Any) -> list:
    return page.evaluate("() => window.__r3Clears")


# ---------------------------------------------------------------------------
# A12.2 / C12.01
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("action", ACTIONS)
def test_destructive_confirm(settings_page: Any, action: str) -> None:
    page = settings_page
    if action in STORE:
        page.evaluate(SEED_JS, [ss.IDB_NAME, ss.IDB_VERSION, STORE[action], KEY_PATH[action]])
        assert _store_count(page, action) == 1
    log = ss.RequestLog(page).start()

    trigger = page.get_by_test_id(f"set-data-{action}")
    modal = page.get_by_test_id(f"set-modal-{action}")
    trigger.click()
    expect(modal).to_be_visible()
    for other in ACTIONS:
        if other != action:
            expect(page.get_by_test_id(f"set-modal-{other}")).to_be_hidden()
    expect(page.get_by_test_id(f"set-modal-{action}-body")).to_be_visible()

    page.get_by_test_id(f"set-modal-{action}-cancel").click()
    expect(modal).to_be_hidden()
    assert _clears(page) == [], "cancel must not clear anything"
    assert log.items == [], f"cancel sent requests: {log.items}"
    if action in STORE:
        assert _store_count(page, action) == 1, "cancel must leave the stored record"

    trigger.click()
    expect(modal).to_be_visible()
    page.get_by_test_id(f"set-modal-{action}-primary").evaluate(TRIPLE_CLICK_JS)
    expect(modal).to_be_hidden()

    if action == "reindex":
        # D11: deferred server effect; a visible "not supported" line, nothing sent.
        expect(page.get_by_text("暂不支持")).to_be_visible()
        assert _clears(page) == []
    else:
        expect(page.get_by_text("已清除")).to_be_visible()
        assert _clears(page) == [STORE[action]], "three clicks on primary must clear exactly once"
        assert _store_count(page, action) == 0, "the store must be empty after primary"
    assert log.items == [], f"{action} sent requests: {log.items}"


# ---------------------------------------------------------------------------
# FP-15 / C12.02
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("action", ACTIONS)
def test_dismiss_trap_and_focus_return(settings_page: Any, action: str) -> None:
    page = settings_page
    log = ss.RequestLog(page).start()
    trigger = page.get_by_test_id(f"set-data-{action}")
    modal = page.get_by_test_id(f"set-modal-{action}")

    # Esc
    trigger.click()
    expect(modal).to_be_visible()
    page.keyboard.press(ss.KEY_ESCAPE)
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()

    # backdrop: a point outside the dialog box, which a modal dialog's backdrop covers
    trigger.click()
    expect(modal).to_be_visible()
    box = modal.bounding_box()
    assert box is not None and box["x"] > 4 and box["y"] > 4, box
    page.mouse.click(2, 2)
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()

    # the close button
    trigger.click()
    expect(modal).to_be_visible()
    page.get_by_test_id(f"set-modal-{action}-close").click()
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()

    # focus trap: Tab N+1 times, then Shift+Tab N+1 times, focus never leaves the dialog
    trigger.click()
    expect(modal).to_be_visible()
    n = modal.evaluate(FOCUSABLE_COUNT_JS)
    assert n >= 3, f"set-modal-{action} has only {n} focusable controls"
    assert modal.evaluate(CONTAINS_FOCUS_JS), "focus did not move into the dialog on open"
    for key in (ss.KEY_TAB, ss.KEY_SHIFT_TAB):
        for i in range(n + 1):
            page.keyboard.press(key)
            assert modal.evaluate(CONTAINS_FOCUS_JS), f"{key} #{i + 1} moved focus out of set-modal-{action}"
    page.keyboard.press(ss.KEY_ESCAPE)
    expect(modal).to_be_hidden()
    expect(trigger).to_be_focused()

    assert _clears(page) == []
    assert log.items == [], f"dismissing set-modal-{action} sent requests: {log.items}"
