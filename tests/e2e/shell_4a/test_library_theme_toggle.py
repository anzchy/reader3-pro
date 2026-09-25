"""013 WI-13 A13.8 (C13.08, C13.09, C13.33) and the library half of WI-10 A10.3.

`lib-theme-toggle` cycles the chrome scheme system -> light -> dark -> system on the same key
the settings page writes (`reader3.ui.colorScheme`). Its accessible name says the current
state: 「界面明暗：跟随系统 / 浅色 / 深色」. Absent key == system, and rendering never writes;
a click to system writes "system" (PLAN :1027, matrix gap 12).

A10.3 (library half): the library body paints `--r3-bg` / `--r3-text`, so dark chrome changes
the body background, with >= 4.5 contrast in both schemes.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
import shell_4a_settings as ss
import shell_4a_theme as th
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

LABEL = {"system": "界面明暗：跟随系统", "light": "界面明暗：浅色", "dark": "界面明暗：深色"}
ORDER = ("system", "light", "dark")
ARIA_LABEL = "aria-label"

STATE_JS = """(key) => [document.documentElement.dataset.theme ?? null, localStorage.getItem(key)]"""
BODY_COLORS_JS = """() => { const cs = getComputedStyle(document.body); return [cs.backgroundColor, cs.color]; }"""


def seed_once(color_scheme: Optional[str]) -> str:
    body = th.storage_init_script(color_scheme, None)
    return (
        "(() => { try { if (sessionStorage.getItem('wi13-seeded')) return; "
        "sessionStorage.setItem('wi13-seeded', '1'); } catch (e) { return; }\n" + body + "\n})();"
    )


@pytest.fixture
def make_context(browser: Any) -> Iterator[Any]:
    contexts: List[Any] = []

    def _make(color_scheme: Optional[str] = None, seed: bool = False) -> Any:
        context = s4.new_gated_context(browser, init_scripts=[seed_once(color_scheme)] if seed else [])
        contexts.append(context)
        return context

    try:
        yield _make
    finally:
        for c in contexts:
            c.close()


def _norm(v: Optional[str]) -> str:
    return "system" if v is None else v


def _observe(page: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    theme, stored = page.evaluate(STATE_JS, th.COLOR_SCHEME_KEY)
    return theme, stored, page.get_by_test_id("lib-theme-toggle").get_attribute(ARIA_LABEL)


@pytest.mark.parametrize("start", [None, "system", "light", "dark"], ids=["absent", "system", "light", "dark"])
def test_three_clicks_return_to_start(make_context: Any, live_server: str, start: Optional[str]) -> None:
    page = sl.open_library(make_context(start, seed=start is not None), live_server, wait_status=False)
    toggle = page.get_by_test_id("lib-theme-toggle")
    expect(toggle).to_have_count(1)
    theme0, stored0, label0 = _observe(page)
    assert stored0 == start, "rendering wrote the scheme key"
    assert label0 == LABEL[_norm(start)]
    assert theme0 == (None if _norm(start) == "system" else start)
    seen = []
    for _ in range(3):
        toggle.click()
        theme, stored, label = _observe(page)
        assert stored is not None, "a click left the key absent"
        assert label == LABEL[stored]
        assert theme == (None if stored == "system" else stored)
        seen.append(stored)
    i = ORDER.index(_norm(start))
    assert seen == [ORDER[(i + k) % 3] for k in (1, 2, 3)], seen
    assert len(set(seen)) == 3
    assert _norm(seen[-1]) == _norm(start)
    if start is None:
        assert seen[-1] == "system"


def test_absent_key_renders_system_on_both_surfaces(make_context: Any, live_server: str) -> None:
    context = make_context()
    page = sl.open_library(context, live_server, wait_status=False)
    theme, stored, label = _observe(page)
    assert theme is None and stored is None
    assert label == LABEL["system"]
    settings = ss.open_settings(context, live_server)
    expect(settings.get_by_test_id("set-appearance-scheme-system")).to_have_attribute("aria-checked", "true")
    for other in ("light", "dark"):
        expect(settings.get_by_test_id(f"set-appearance-scheme-{other}")).to_have_attribute("aria-checked", "false")
    assert settings.evaluate(STATE_JS, th.COLOR_SCHEME_KEY)[1] is None, "a surface wrote the key on load"


def test_settings_choice_is_shown_by_library_and_back(make_context: Any, live_server: str) -> None:
    context = make_context()
    settings = ss.open_settings(context, live_server)
    settings.get_by_test_id("set-appearance-scheme-dark").click()
    page = sl.open_library(context, live_server, wait_status=False)
    assert _observe(page) == ("dark", "dark", LABEL["dark"])
    page.get_by_test_id("lib-theme-toggle").click()
    assert _observe(page) == (None, "system", LABEL["system"])
    settings.reload(wait_until="load")
    expect(settings.get_by_test_id("set-appearance-scheme-system")).to_have_attribute("aria-checked", "true")


def test_dark_chrome_changes_library_body(make_context: Any, live_server: str) -> None:
    """WI-10 A10.3, library half."""
    page = sl.open_library(make_context("light", seed=True), live_server, wait_status=False)
    light_bg, light_fg = page.evaluate(BODY_COLORS_JS)
    assert th.contrast(light_fg, light_bg) >= 4.5, (light_fg, light_bg)
    toggle = page.get_by_test_id("lib-theme-toggle")
    toggle.click()  # light -> dark
    assert _observe(page)[0] == "dark"
    dark_bg, dark_fg = page.evaluate(BODY_COLORS_JS)
    assert dark_bg != light_bg, f"dark chrome left the library body at {dark_bg}"
    assert th.contrast(dark_fg, dark_bg) >= 4.5, (dark_fg, dark_bg)
    tokens = [page.evaluate(sl.RESOLVE_TOKEN_COLOR_JS, n) for n in ("--r3-bg", "--r3-text")]
    assert [dark_bg, dark_fg] == tokens, "the library body must paint --r3-bg / --r3-text"
