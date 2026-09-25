"""013 WI-12 A12.3 DOM half (C12.09): every testid the settings page renders is `set-`
prefixed, canonical, and exists in the prototype.

Scanned with a dialog open, so the dialog's own testids are part of the rendered set. The
expected list is the page's contract (prototype `settings.jsx` / `components.jsx` plus the
D10 appearance radios); the check is a superset, so the page may carry more `set-` names as
long as each is canonical and comes from the prototype.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Set

import pytest
import shell_4a_fixtures as s4
import shell_4a_settings as ss
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE_DIR = REPO_ROOT / "designs" / "reader-pro-next"
CANONICAL = re.compile(r"^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$")

EXPECTED: Set[str] = {
    "set-screen", "set-topbar", "set-brand", "set-topbar-back-to-library", "set-live-region",
    "set-provider-card", "set-provider-toggle", "set-provider-model", "set-provider-url",
    "set-provider-key", "set-provider-save", "set-provider-test", "set-provider-result",
    "set-provider-refresh-models", "set-provider-ollama-hint",
    "set-rag-chunks", "set-rag-context", "set-rag-embedding",
    "set-appearance-scheme-system", "set-appearance-scheme-light", "set-appearance-scheme-dark",
    "set-data-reindex", "set-data-conversations", "set-data-cache",
    "set-export-json", "set-export-settings",
    *(f"set-modal-{a}{part}" for a in ("reindex", "conversations", "cache")
      for part in ("", "-body", "-close", "-cancel", "-primary")),
}


#: The whole-DOM scan is the assertion itself (A12.3 DOM half), not a locator.
SCAN_JS = "() => Array.from(document.querySelectorAll('[data-testid]'), (e) => e.dataset.testid)"  # lint-e2e-selectors: allow —— A12.3：全 DOM testid 扫描本身就是被测对象，不是定位


def _prototype_names() -> Set[str]:
    names: Set[str] = set()
    for path in PROTOTYPE_DIR.glob("*.jsx"):
        names.update(re.findall(r'"(set-[a-z0-9-]+)"', path.read_text(encoding="utf-8")))
    return names


def test_rendered_testids_prefixed(browser: Any, live_server: str) -> None:
    context = s4.new_gated_context(browser)
    try:
        page = ss.open_settings(context, live_server)
        page.get_by_test_id("set-data-conversations").click()
        expect(page.get_by_test_id("set-modal-conversations")).to_be_visible()
        rendered = set(page.evaluate(SCAN_JS))
    finally:
        context.close()
    bad = sorted(n for n in rendered if not n.startswith("set-") or not CANONICAL.match(n))
    assert bad == [], f"non-set / non-canonical testids on the settings page: {bad}"
    missing = sorted(EXPECTED - rendered)
    assert missing == [], f"expected settings testids not rendered: {missing}"
    prototype = _prototype_names()
    assert EXPECTED <= prototype, sorted(EXPECTED - prototype)
    unknown = sorted(rendered - prototype)
    assert unknown == [], f"rendered testids that are not in the prototype: {unknown}"
