"""REG-1 (013 WI-9): snapshot values do not depend on the OS the capture ran on.

Chromium on macOS serialises the computed `font-family` token `BlinkMacSystemFont`
as `"system-ui"`; Chromium on Linux keeps the literal name. The committed snapshot
was captured on macOS, so C9.38's independent capture on the Linux CI runner
differed at exactly the three settings testids whose 671f580 stack names
`BlinkMacSystemFont`. `snapshot_values` canonicalises the alias so both sides of
every snapshot comparison speak the same form.

Unit lane: pure data in, pure data out; no browser.
"""

from __future__ import annotations

import shell_4a_fixtures as s4

MAC = '-apple-system, "system-ui", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
LINUX = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'


def _capture(font_family: str, color: str = "rgb(0, 0, 0)") -> s4.Capture:
    return {
        "settings": {
            "set-screen": {
                "count": 1,
                "v": {"font-family": font_family, "color": color},
                "p": {},
            }
        }
    }


def test_linux_and_macos_serialisations_give_equal_snapshot_values() -> None:
    assert s4.snapshot_values(_capture(LINUX)) == s4.snapshot_values(_capture(MAC))


def test_the_canonical_form_is_the_one_the_committed_snapshot_already_holds() -> None:
    values = s4.snapshot_values(_capture(LINUX))
    assert values["settings"]["set-screen"]["font-family"] == MAC


def test_only_font_family_is_rewritten() -> None:
    values = s4.snapshot_values(_capture(LINUX, color="BlinkMacSystemFont"))
    assert values["settings"]["set-screen"]["color"] == "BlinkMacSystemFont"


def test_a_stack_without_the_alias_is_untouched() -> None:
    stack = '-apple-system, "Helvetica Neue", Arial, sans-serif'
    assert s4.snapshot_values(_capture(stack))["settings"]["set-screen"]["font-family"] == stack


def test_a_testid_that_did_not_match_once_stays_none() -> None:
    capture: s4.Capture = {"settings": {"set-screen": {"count": 0, "v": None, "p": None}}}
    assert s4.snapshot_values(capture) == {"settings": {"set-screen": None}}


def test_the_committed_snapshot_holds_no_platform_literal() -> None:
    raw = s4.DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert "BlinkMacSystemFont" not in raw
