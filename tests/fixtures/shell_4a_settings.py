"""013 WI-12 (4A.2 settings page) shared helpers for `tests/e2e/shell_4a/test_settings_*.py`.

Group directories cannot hold a `conftest.py` (see `scripts/lint_e2e_groups.py`), so the
helpers live here, next to `shell_4a_fixtures.py`. `tests/fixtures/` is on `sys.path`
through `tests/conftest.py`.

What is here:

    SETTINGS_PATH / PROVIDERS / SET_*          page constants (no selectors are built here)
    sandbox_settings_path(books_dir)           the `ai_settings.json` the live server reads
    preserved_settings(path)                   restore that file's bytes (or absence) afterwards
    write_settings(path, data)                 write a sandbox config for one test
    RequestLog                                 records every request a page sends after `start()`
    ATTR_RECORDER_JS / attr_history(page, tid) `aria-busy` / `disabled` transitions per testid
    open_settings(context, base_url)           a settings page, loaded and rendered

**Why the sandbox file is restored and not just deleted.** `load_ai_settings()` re-reads
the file on every request, so a test that saves a provider leaves that provider saved for
every later test in the session. The frozen `ai_settings_ollama` fixture deletes the file on
teardown; a test that mutates settings without it must put back exactly what it found.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.sync_api import expect

SETTINGS_PATH = "/settings"
PROVIDERS: Tuple[str, ...] = ("anthropic", "openai", "gemini", "ollama", "openrouter")
KEYED_PROVIDERS: Tuple[str, ...] = ("anthropic", "openai", "gemini", "openrouter")

#: The two IndexedDB stores the settings page clears (legacy `settings.js` names).
IDB_NAME = "reader3_ai_assistant"
IDB_VERSION = 1

#: Key names and fill values go through constants: `lint_e2e_selectors.py` treats the first
#: string literal of `.press(` / `.fill(` as a selector.
KEY_TAB = "Tab"
KEY_SHIFT_TAB = "Shift+Tab"
KEY_ESCAPE = "Escape"
KEY_SPACE = "Space"
KEY_ENTER = "Enter"
KEY_ARROW_RIGHT = "ArrowRight"


def sandbox_settings_path(books_dir: Path) -> Path:
    """The file `_server_env` points `READER3_AI_SETTINGS` at (same rule as `ai_settings_ollama`)."""
    return (books_dir.parent / "ai_settings.json").resolve()


@contextmanager
def preserved_settings(path: Path) -> Iterator[Path]:
    """Yield `path`; afterwards restore its exact bytes, or its absence."""
    before: Optional[bytes] = path.read_bytes() if path.exists() else None
    try:
        yield path
    finally:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)


def write_settings(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def all_disabled_settings() -> Dict[str, Any]:
    """FD-18: every provider present and disabled ("no providers" = none enabled, user ruling)."""
    return {
        "default_provider": "anthropic",
        "providers": {name: {"enabled": False} for name in PROVIDERS},
    }


class RequestLog:
    """Every request the page sends once `start()` has been called: `(method, path)`."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._on = False
        self.items: List[Tuple[str, str]] = []
        page.on("request", self._record)

    def _record(self, request: Any) -> None:
        if self._on:
            self.items.append((request.method, urlparse(request.url).path))

    def start(self) -> "RequestLog":
        self.items.clear()
        self._on = True
        return self

    def matching(self, method: str, path: str) -> List[Tuple[str, str]]:
        return [i for i in self.items if i == (method, path)]


#: Records every change of `aria-busy` or `disabled` on an element with a testid, as
#: `[testid, data-provider|null, attribute, new value|null]`. Installed as an init script so
#: it sees the page from the first mutation on.
ATTR_RECORDER_JS = r"""
(() => {
  window.__r3Attr = [];
  const start = () => {
    new MutationObserver((records) => {
      for (const r of records) {
        const el = r.target;
        if (!(el instanceof Element) || !el.hasAttribute("data-testid")) continue;
        window.__r3Attr.push([
          el.getAttribute("data-testid"),
          el.getAttribute("data-provider"),
          r.attributeName,
          el.getAttribute(r.attributeName),
        ]);
      }
    }).observe(document.documentElement, {
      subtree: true, attributes: true, attributeFilter: ["aria-busy", "disabled"],
    });
  };
  if (document.documentElement) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
"""


def attr_history(page: Any, testid: str, attribute: str, provider: Optional[str] = None) -> List[Optional[str]]:
    rows = page.evaluate("() => window.__r3Attr || []")
    return [r[3] for r in rows if r[0] == testid and r[2] == attribute and (provider is None or r[1] == provider)]


def open_settings(context: Any, base_url: str) -> Any:
    """A settings page with its provider cards rendered (the TS entry has run)."""
    page = context.new_page()
    page.goto(base_url + SETTINGS_PATH, wait_until="load")
    expect(page.get_by_test_id("set-screen")).to_have_count(1)
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(PROVIDERS))
    return page

