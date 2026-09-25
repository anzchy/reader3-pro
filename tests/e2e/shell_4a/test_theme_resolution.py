"""013 WI-10 A10.2-A10.8 (C10.09-C10.12, C10.14) and FA-03 / FA-04 (C10.20): the token
layer resolves in the browser, on the real pages, for every chrome x reading combination.

The two axes are set directly on `<html>` (see `shell_4a_theme` for why the stamp is not
used here). Reading-axis tokens are resolved on the reader shell (`rd-shell`, which
carries `.reader-shell`); chrome tokens on `<html>` / `<body>`.

Each page is opened once per module and re-themed in place: custom-property resolution
is synchronous on `getComputedStyle`, so no reload is needed between combinations, and a
reload would only add the FOUC stamp as a second variable.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

import pytest
import shell_4a_fixtures as s4
import shell_4a_theme as th
from conftest import BOOK_ID
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

ROOT_TESTID: Dict[str, str] = {"library": "lib-shell", "reader": "rd-shell", "settings": "set-screen"}


class Pages:
    def __init__(self, context: Any, base_url: str) -> None:
        self._context = context
        self._base = base_url
        self._pages: Dict[str, Any] = {}

    def get(self, name: str) -> Any:
        if name not in self._pages:
            page = self._context.new_page()
            page.goto(self._base + s4.page_path(name, BOOK_ID), wait_until="load")
            expect(page.get_by_test_id(ROOT_TESTID[name])).to_have_count(1)
            self._pages[name] = page
        return self._pages[name]


@pytest.fixture(scope="module")
def pages(browser: Any, live_server: str) -> Iterator[Pages]:
    context = s4.new_gated_context(browser)
    try:
        yield Pages(context, live_server)
    finally:
        context.close()


def set_axes(page: Any, chrome: str, reading: str) -> None:
    page.evaluate(th.SET_AXES_JS, [chrome, reading])


def shell(page: Any) -> Any:
    return page.get_by_test_id("rd-shell")


def resolve(locator: Any, names: List[str]) -> Dict[str, str]:
    return locator.evaluate(th.RESOLVE_JS, names)


def resolve_colors(locator: Any, names: List[str]) -> Dict[str, str]:
    return locator.evaluate(th.RESOLVE_COLOR_JS, names)


def body_colors(page: Any) -> Tuple[str, str]:
    return tuple(
        page.locator("body").evaluate(  # lint-e2e-selectors: allow —— <body> 本身就是被测对象（A10.3 / A10.8 判的是 body 背景）
            "(b) => { const cs = getComputedStyle(b); return [cs.backgroundColor, cs.color]; }"
        )
    )


def _combo_id(combo: Tuple[str, str]) -> str:
    return f"{combo[0]}-{combo[1]}"


# ---------------------------------------------------------------------------
# A10.2 / C10.09
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("combo", th.COMBOS, ids=_combo_id)
def test_all_tokens_resolve(pages: Pages, combo: Tuple[str, str]) -> None:
    names = th.dist_token_names()
    assert len(names) >= 60, f"the built CSS defines only {len(names)} --r3-* tokens"
    for required in (*th.READING_TOKENS, *th.STATUS_TOKENS, "--r3-bg", "--r3-text"):
        assert required in names, f"{required} is not defined by the built CSS"
    page = pages.get("reader")
    set_axes(page, *combo)
    values = resolve(shell(page), names)
    empty = sorted(n for n, v in values.items() if v == "")
    assert empty == []
    bad_triplets = sorted(n for n, v in values.items() if n.endswith("-rgb") and not th.triplet_ok(v))
    assert bad_triplets == []


# ---------------------------------------------------------------------------
# A10.3 / C10.12
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reading", th.READINGS)
def test_dark_chrome_contrast(pages: Pages, reading: str) -> None:
    page = pages.get("reader")
    tuples: Dict[str, Tuple[str, str, str, str]] = {}
    for chrome in ("light", "dark"):
        for r in (reading, "auto"):
            set_axes(page, chrome, r)
            bg, fg = body_colors(page)
            tok = resolve_colors(page.locator("body"), ["--r3-text", "--r3-bg"])  # lint-e2e-selectors: allow —— chrome token 在 body 上解析
            tuples[f"{chrome}/{r}"] = (bg, fg, tok["--r3-text"], tok["--r3-bg"])
    dark = tuples[f"dark/{reading}"]
    # 用户裁定 2026-09-24: "the body background changes under dark chrome" is verified per
    # migrated page -- settings in WI-12, library in WI-13, reader pinned to 014 WI-16.
    # Unmigrated pages keep their legacy --dedao-* colours as literals, so the legacy reader
    # <body> stays light here by design (otherwise an OS dark preference turns the legacy
    # pages half-dark; see test_dark_os_legacy_unchanged.py). The token contrast and the
    # same-result-for-every-reading-theme parts are still checked in this WI.
    ratio = th.contrast(dark[2], dark[3])
    assert ratio >= 4.5, f"dark --r3-text on --r3-bg is {ratio:.2f}"
    assert th.contrast(dark[1], dark[0]) >= 4.5, "the body's own dark text/background pair"
    # The chrome block must not be scoped under the reading axis.
    assert dark == tuples["dark/auto"]


# ---------------------------------------------------------------------------
# A10.4 / A10.5
# ---------------------------------------------------------------------------
STATUS_AND_SUBTLE: List[str] = [
    *th.STATUS_TOKENS,
    *(f"{n}-subtle" for n in th.STATUS_TOKENS),
]


def test_status_tokens_defined(pages: Pages) -> None:
    page = pages.get("reader")
    missing: List[str] = []
    for combo in th.COMBOS:
        set_axes(page, *combo)
        values = resolve(shell(page), STATUS_AND_SUBTLE)
        missing += [f"{_combo_id(combo)}:{n}" for n, v in values.items() if v == ""]
    assert missing == []


def test_hl_rgb_triplets(pages: Pages) -> None:
    page = pages.get("reader")
    names = [f"--r3-hl-{c}-rgb" for c in th.MARKER_COLORS]
    bad: List[str] = []
    for combo in th.COMBOS:
        set_axes(page, *combo)
        values = resolve(shell(page), names)
        bad += [f"{_combo_id(combo)}:{n}={v!r}" for n, v in values.items() if not th.triplet_ok(v)]
    assert bad == []


# ---------------------------------------------------------------------------
# A10.6 / C10.10
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("paper", th.ABSOLUTE_PAPERS)
def test_paper_absolute(pages: Pages, paper: str) -> None:
    page = pages.get("reader")
    names = list(th.READING_TOKENS)
    by_chrome = {}
    for chrome in th.CHROMES:
        set_axes(page, chrome, paper)
        by_chrome[chrome] = (resolve(shell(page), names), resolve_colors(shell(page), names[:3]))
    assert by_chrome["light"] == by_chrome["dark"]
    # Non-vacuity: under auto the same names DO differ between the chromes, so equality
    # above is a property of the paper rule, not of tokens that never vary.
    set_axes(page, "light", "auto")
    auto_light = resolve(shell(page), names)
    set_axes(page, "dark", "auto")
    assert resolve(shell(page), names) != auto_light


# ---------------------------------------------------------------------------
# A10.7 / C10.11
# ---------------------------------------------------------------------------
def test_auto_follows_chrome(pages: Pages) -> None:
    page = pages.get("reader")
    html = page.locator("html")  # lint-e2e-selectors: allow —— :root 的值就是被比较的一侧
    out = {}
    for chrome in th.CHROMES:
        set_axes(page, chrome, "auto")
        out[chrome] = (
            resolve_colors(shell(page), ["--r3-page-bg"])["--r3-page-bg"],
            resolve_colors(html, ["--r3-page-bg"])["--r3-page-bg"],
        )
    assert out["light"][0] != out["dark"][0]
    for chrome in th.CHROMES:
        assert out[chrome][0] == out[chrome][1], f"auto under {chrome} is not the :root value"


# ---------------------------------------------------------------------------
# A10.8 / C10.14
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page_name", ["library", "settings"])
def test_reading_axis_does_not_leak(pages: Pages, page_name: str) -> None:
    page = pages.get(page_name)
    backgrounds = []
    for reading in th.READINGS:
        set_axes(page, "light", reading)
        backgrounds.append(body_colors(page)[0])
    assert th.unique(backgrounds) == 1, backgrounds


# ---------------------------------------------------------------------------
# FA-03 / FA-04 (C10.20)
# ---------------------------------------------------------------------------
def test_paper_ink_and_status_contrast(pages: Pages) -> None:
    page = pages.get("reader")
    failures: List[str] = []
    pairs = [("light", "auto"), ("dark", "auto"), *(("light", p) for p in th.ABSOLUTE_PAPERS)]
    assert len(pairs) == 6
    for chrome, reading in pairs:
        set_axes(page, chrome, reading)
        v = resolve_colors(shell(page), ["--r3-page-bg", "--r3-page-ink", "--r3-page-quiet"])
        ink = th.contrast(v["--r3-page-ink"], v["--r3-page-bg"])
        quiet = th.contrast(v["--r3-page-quiet"], v["--r3-page-bg"])
        if ink < 4.5:
            failures.append(f"{chrome}/{reading}: ink {ink:.2f}")
        if quiet < 3:
            failures.append(f"{chrome}/{reading}: quiet {quiet:.2f}")
    for chrome in th.CHROMES:
        set_axes(page, chrome, "auto")
        v = resolve_colors(page.locator("html"), [*STATUS_AND_SUBTLE, "--r3-bg", "--r3-surface"])  # lint-e2e-selectors: allow —— chrome token 在 :root 上解析
        for status in th.STATUS_TOKENS:
            for ground in ("--r3-bg", "--r3-surface", f"{status}-subtle"):
                r = th.contrast(v[status], v[ground])
                if r < 4.5:
                    failures.append(f"{chrome}: {status} on {ground} {r:.2f}")
    assert failures == []
