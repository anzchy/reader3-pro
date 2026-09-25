"""013 WI-12 A12.6-A12.8 (C12.04-C12.06), FB-S10, plus the settings half of WI-10 A10.3.

The appearance section has the chrome axis only: a `radiogroup` 「界面明暗」 with three radios
`set-appearance-scheme-{system,light,dark}`. Storage semantics (PLAN :1027, matrix gap 12):

* selecting any option writes it to `reader3.ui.colorScheme`, `"system"` included;
* an absent key reads as system, and reading never writes;
* system removes `data-theme` from `<html>`; light / dark set it;
* `data-reading-theme` (the reader's paper axis) is never touched from settings.

Seeding goes through a once-per-tab init script (a `sessionStorage` flag), so a reload inside
the test sees what the page wrote, not the seed again.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, List, Optional, Tuple

import pytest
import shell_4a_fixtures as s4
import shell_4a_settings as ss
import shell_4a_theme as th
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

SCHEMES = ("system", "light", "dark")
GROUP_NAME = "界面明暗"
ARIA_CHECKED = "aria-checked"

STATE_JS = """(key) => [
  document.documentElement.dataset.theme ?? null,
  localStorage.getItem(key),
  document.documentElement.dataset.readingTheme ?? null,
]"""

BODY_COLORS_JS = """() => {
  const cs = getComputedStyle(document.body);
  return [cs.backgroundColor, cs.color];
}"""


def seed_once(color_scheme: Optional[str], reading: Optional[str]) -> str:
    """Seed both keys on the first load of the tab only."""
    body = th.storage_init_script(color_scheme, reading)
    return (
        "(() => { try { if (sessionStorage.getItem('wi12-seeded')) return; "
        "sessionStorage.setItem('wi12-seeded', '1'); } catch (e) { return; }\n"
        + body
        + "\n})();"
    )


@pytest.fixture
def make_page(browser: Any, live_server: str) -> Iterator[Any]:
    contexts: List[Any] = []

    def _make(color_scheme: Optional[str] = None, reading: Optional[str] = None, seed: bool = False) -> Any:
        scripts = [seed_once(color_scheme, reading)] if seed else []
        context = s4.new_gated_context(browser, init_scripts=scripts)
        contexts.append(context)
        return ss.open_settings(context, live_server)

    try:
        yield _make
    finally:
        for c in contexts:
            c.close()


def _state(page: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return tuple(page.evaluate(STATE_JS, th.COLOR_SCHEME_KEY))


def _checked(page: Any) -> List[str]:
    group = page.get_by_role("radiogroup", name=GROUP_NAME)
    return [
        s for s in SCHEMES
        if group.get_by_test_id(f"set-appearance-scheme-{s}").get_attribute(ARIA_CHECKED) == "true"
    ]


def _assert_selected(page: Any, scheme: str, reading: str) -> None:
    theme, stored, reading_attr = _state(page)
    assert theme == (None if scheme == "system" else scheme), f"data-theme={theme!r} for {scheme}"
    assert stored == scheme, f"localStorage={stored!r} for {scheme}"
    assert reading_attr == reading, f"data-reading-theme changed to {reading_attr!r}"
    assert _checked(page) == [scheme]


# ---------------------------------------------------------------------------
# A12.6 / C12.04 / FB-S10
# ---------------------------------------------------------------------------
def test_radiogroup_default(make_page: Any) -> None:
    page = make_page()
    group = page.get_by_role("radiogroup", name=GROUP_NAME)
    expect(group).to_have_count(1)
    expect(group.get_by_role("radio")).to_have_count(3)
    expect(group.get_by_role("radio", checked=True)).to_have_count(1)
    expect(page.get_by_test_id("set-appearance-scheme-system")).to_have_attribute("aria-checked", "true")
    theme, stored, _ = _state(page)
    assert stored is None, "rendering the default must not write the scheme key"
    assert theme is None


# ---------------------------------------------------------------------------
# A12.7 (per scheme) and C12.05 (the sequence)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("scheme", SCHEMES)
def test_scheme_selection_side_effects(make_page: Any, scheme: str) -> None:
    start = "light" if scheme == "dark" else "dark"
    page = make_page(start, "sepia", seed=True)
    _assert_selected(page, start, "sepia")
    page.get_by_test_id(f"set-appearance-scheme-{scheme}").click()
    _assert_selected(page, scheme, "sepia")
    page.reload(wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    _assert_selected(page, scheme, "sepia")


def test_scheme_sequence_consistent(make_page: Any) -> None:
    page = make_page("dark", "sepia", seed=True)
    _assert_selected(page, "dark", "sepia")
    for scheme in ("system", "light", "dark", "system"):
        page.get_by_test_id(f"set-appearance-scheme-{scheme}").click()
        _assert_selected(page, scheme, "sepia")
    before = (_state(page), _checked(page))
    page.reload(wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    assert (_state(page), _checked(page)) == before, "reload changed the appearance state"
    # keyboard: focus the checked radio, ArrowRight moves to and selects the next one
    page.get_by_test_id("set-appearance-scheme-system").focus()
    page.keyboard.press(ss.KEY_ARROW_RIGHT)
    _assert_selected(page, "light", "sepia")
    expect(page.get_by_test_id("set-appearance-scheme-light")).to_be_focused()


# ---------------------------------------------------------------------------
# A12.8 / C12.06
# ---------------------------------------------------------------------------
def test_no_paper_controls(make_page: Any) -> None:
    page = make_page()
    n = page.evaluate("() => document.querySelectorAll('[data-testid^=\"rd-pref-theme-\"]').length")  # lint-e2e-selectors: allow —— A12.8 / R-9：前缀扫描本身就是断言（设置页上 rd-pref-theme-* 必须为 0 个），是 DOM 计数不是定位
    assert n == 0, f"{n} reading-paper controls on the settings page"
    expect(page.get_by_role("radiogroup", name=GROUP_NAME).get_by_role("radio")).to_have_count(3)


# ---------------------------------------------------------------------------
# WI-10 A10.3, settings half (user ruling 2026-09-24): dark chrome changes the body
# ---------------------------------------------------------------------------
def test_dark_chrome_changes_body_background(make_page: Any) -> None:
    page = make_page("light", None, seed=True)
    light_bg, light_fg = page.evaluate(BODY_COLORS_JS)
    assert th.contrast(light_fg, light_bg) >= 4.5, (light_fg, light_bg)
    page.get_by_test_id("set-appearance-scheme-dark").click()
    dark_bg, dark_fg = page.evaluate(BODY_COLORS_JS)
    assert dark_bg != light_bg, f"dark chrome left the body background at {dark_bg}"
    assert th.contrast(dark_fg, dark_bg) >= 4.5, json.dumps([dark_fg, dark_bg])
    tokens = page.evaluate(
        """() => { const p = document.createElement("span"); document.body.appendChild(p);
          p.style.color = "var(--r3-bg)"; const bg = getComputedStyle(p).color;
          p.style.color = "var(--r3-text)"; const fg = getComputedStyle(p).color; p.remove();
          return [bg, fg]; }"""
    )
    assert [dark_bg, dark_fg] == tokens, "the settings body must paint --r3-bg / --r3-text"
