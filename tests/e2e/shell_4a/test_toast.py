"""013 WI-11 acceptance 4 / 4a, real-browser half of the Toast (C11.07, C11.08, C11.15).

The fe-unit half (C11.06, C11.14) lives in `frontend/tests/shared/toast.test.ts` and runs under
jsdom with fake timers. These cases run the built library bundle in Chromium, with the real CSS
cascade feeding `--r3-dwell-toast` into the real `showToast`.

* C11.07: under no-preference, N is read from the computed token (never a constant); two toasts
  raised at the same instant leave exactly one `lib-toast`, which is present at N-250 and gone at
  N+250.
* C11.08 (acceptance 4a, the reason acceptance 4 exists): under `emulate_media(reduced_motion=
  "reduce")` the raw `--r3-dwell-toast` is byte-equal to its no-preference value and is not a
  zero time, while `--r3-duration-normal` really did drop to zero (so the emulation is proven live
  and the equality is not vacuous); the toast still stays N ms. Zero is judged as a time, not as
  the spelling `0ms`: the build minifies `0ms` to `0s`.
* C11.15: a token overridden after load (1500ms, 7000ms) moves the real dwell with it, which kills
  both a constant equal to the default and a value read once at module load.

The toast is raised by the one settings-free UI path that calls `showToast`: creating a
collection in the library (`lib-toast`, ADR-0013 prefix; settings has no toast, ruling D9).
Time is driven by Playwright's clock: installed before load (time flows naturally), paused just
before the trigger so the toast's mount instant is known exactly, then advanced with `run_for`.
Collections created here are deleted in `finally`.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

DWELL_TOKEN = "--r3-dwell-toast"
DURATION_TOKEN = "--r3-duration-normal"
TOKEN_JS = "(name) => getComputedStyle(document.documentElement).getPropertyValue(name)"
NOW_JS = "() => Date.now()"
TIME_RE = re.compile(r"^(\d*\.?\d+)(ms|s)$")  # minified forms too: `.3s`, `4s`
MARGIN_MS = 250
NO_PREFERENCE = "no-preference"
REDUCE = "reduce"
NAME_PREFIX = "WI11 toast"


@pytest.fixture
def ctx(browser: Any, live_server: str) -> Iterator[Any]:
    context = s4.new_gated_context(browser)
    context.clock.install()
    try:
        yield context
    finally:
        _delete_collections(context, live_server)
        context.close()


def _delete_collections(context: Any, live_server: str) -> None:
    listing = context.request.get(live_server + "/api/collections").json()
    items = listing.get("collections", listing) if isinstance(listing, dict) else listing
    for c in items:
        if str(c.get("name", "")).startswith(NAME_PREFIX):
            context.request.delete(f"{live_server}/api/collections/{c['id']}")


def _token(page: Any, name: str) -> str:
    return page.evaluate(TOKEN_JS, name)


def _ms(raw: str) -> int:
    m = TIME_RE.match(raw.strip())
    assert m, f"not a CSS time: {raw!r}"
    return round(float(m.group(1)) * (1000 if m.group(2) == "s" else 1))


def _pause(page: Any) -> None:
    page.clock.pause_at(page.evaluate(NOW_JS) + 1000)


def _raise_toast(page: Any, name: str) -> Any:
    page.get_by_test_id("lib-sidebar-create-collection").click()
    expect(page.get_by_test_id("lib-modal-create-collection")).to_be_visible()
    page.get_by_test_id("lib-collection-name-input").fill(name)
    page.get_by_test_id("lib-modal-create-collection-primary").click()
    toast = page.get_by_test_id("lib-toast")
    expect(toast).to_contain_text(name)
    expect(page.get_by_test_id("lib-modal-create-collection")).to_be_hidden()
    return toast


def _assert_dwell(page: Any, toast: Any, n: int) -> None:
    page.clock.run_for(n - MARGIN_MS)
    expect(toast).to_have_count(1)
    expect(toast).to_be_visible()
    page.clock.run_for(2 * MARGIN_MS)
    expect(toast).to_have_count(0)


# ---------------------------------------------------------------------------
# C11.07
# ---------------------------------------------------------------------------
def test_toast_dwell_is_the_token_and_single_container(ctx: Any, live_server: str) -> None:
    page = sl.open_library(ctx, live_server)
    page.emulate_media(reduced_motion=NO_PREFERENCE)
    n = _ms(_token(page, DWELL_TOKEN))
    assert n > 2 * MARGIN_MS, f"dwell {n}ms is too short to sample at N-{MARGIN_MS}"
    _pause(page)
    _raise_toast(page, f"{NAME_PREFIX} first")
    toast = _raise_toast(page, f"{NAME_PREFIX} second")
    expect(toast).to_have_count(1)
    expect(toast).not_to_contain_text("first")
    _assert_dwell(page, toast, n)


# ---------------------------------------------------------------------------
# C11.08 (acceptance 4a)
# ---------------------------------------------------------------------------
def test_toast_dwell_survives_reduced_motion(ctx: Any, live_server: str) -> None:
    page = sl.open_library(ctx, live_server)
    page.emulate_media(reduced_motion=NO_PREFERENCE)
    dwell_default = _token(page, DWELL_TOKEN)
    duration_default = _token(page, DURATION_TOKEN)
    page.emulate_media(reduced_motion=REDUCE)
    dwell_reduce = _token(page, DWELL_TOKEN)
    duration_reduce = _token(page, DURATION_TOKEN)
    # The emulation is live: the transition family really collapsed. Values are compared as
    # times, not spellings: the build minifies `0ms` to `0s` and `4000ms` to `4s`, so a literal
    # "0ms" check would pass against a zeroed token.
    assert _ms(duration_default) > 0, duration_default
    assert _ms(duration_reduce) == 0, duration_reduce
    # The dwell did not follow it: byte-equal to the no-preference value, and not zero.
    assert dwell_reduce == dwell_default, (dwell_default, dwell_reduce)
    n = _ms(dwell_reduce)
    assert n != 0, f"{DWELL_TOKEN} is zero under reduced motion: {dwell_reduce!r}"
    assert n > 2 * MARGIN_MS, f"dwell {n}ms under reduced motion"
    _pause(page)
    toast = _raise_toast(page, f"{NAME_PREFIX} reduced")
    _assert_dwell(page, toast, n)


# ---------------------------------------------------------------------------
# C11.15
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("override_ms", [1500, 7000])
def test_toast_dwell_tracks_overridden_token(ctx: Any, live_server: str, override_ms: int) -> None:
    page = sl.open_library(ctx, live_server)
    page.add_style_tag(content=f":root{{{DWELL_TOKEN}:{override_ms}ms !important}}")
    assert _ms(_token(page, DWELL_TOKEN)) == override_ms
    _pause(page)
    toast = _raise_toast(page, f"{NAME_PREFIX} {override_ms}")
    _assert_dwell(page, toast, override_ms)
