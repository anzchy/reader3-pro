"""013 WI-12 A12.4 / FV-08 (C12.07) and the settings half of FV-15 (C12.08).

The §5.0 tolerance is 2 px. FV-15 is shared with WI-13 (plan C-16); this file asserts the
settings page's half only.

C12.08 runs with a 200-character ollama model name in the sandbox config, so the one value the
server echoes back that has no natural length bound is as long as it plausibly gets. The
sandbox file is restored afterwards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import shell_4a_fixtures as s4
import shell_4a_settings as ss
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

TOLERANCE = 2
MOBILE = {"width": 390, "height": 844}
VIEWPORTS: Dict[str, Dict[str, int]] = {
    "390x844": MOBILE,
    "768x1024": {"width": 768, "height": 1024},
    "1440x900": {"width": 1440, "height": 900},
}
LONG_MODEL = "m" * 200

OVERFLOW_JS = """() => [
  document.documentElement.scrollWidth, document.body.scrollWidth, window.innerWidth,
]"""


def test_ollama_enabled_in_viewport(browser: Any, live_server: str) -> None:
    context = s4.new_gated_context(browser)
    try:
        page = context.new_page()
        page.set_viewport_size(MOBILE)
        page.goto(live_server + ss.SETTINGS_PATH, wait_until="load")
        toggle = page.locator('[data-testid="set-provider-toggle"][data-provider="ollama"]')
        expect(toggle).to_be_visible()
        toggle.scroll_into_view_if_needed()
        box = toggle.bounding_box()
        assert box is not None
        assert box["x"] + box["width"] <= MOBILE["width"] + TOLERANCE, box
        assert box["x"] >= -TOLERANCE, box
        width = page.evaluate("() => window.innerWidth")
        assert width == MOBILE["width"]
    finally:
        context.close()


@pytest.mark.parametrize("viewport", list(VIEWPORTS), ids=list(VIEWPORTS))
def test_no_horizontal_overflow(browser: Any, live_server: str, e2e_books_dir: Path, viewport: str) -> None:
    path = ss.sandbox_settings_path(e2e_books_dir)
    with ss.preserved_settings(path):
        ss.write_settings(path, {"providers": {"ollama": {"enabled": True, "model_name": LONG_MODEL}}})
        context = s4.new_gated_context(browser)
        try:
            page = context.new_page()
            page.set_viewport_size(VIEWPORTS[viewport])
            page.goto(live_server + ss.SETTINGS_PATH, wait_until="load")
            expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
            model = page.locator('[data-testid="set-provider-model"][data-provider="ollama"]')
            expect(model).to_have_value(LONG_MODEL)
            doc_w, body_w, inner = page.evaluate(OVERFLOW_JS)
            assert doc_w <= inner and body_w <= inner, f"{viewport}: scrollWidth {doc_w}/{body_w} > {inner}"
        finally:
            context.close()
