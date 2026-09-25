"""013 WI-13 A13.6 (C13.12): the rendered library testids are canonical `lib-` names, every
one the frozen baseline references is rendered, and the new controls of the slice exist.

The baseline references are read from the frozen sources themselves (string literals in
`tests/e2e/baseline_1b/**` and `tests/e2e/helpers.py`), so a rename in the template shows up
here as a difference, not as a silent miss.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Set

import pytest
import shell_4a_fixtures as s4
import shell_4a_library as sl

pytestmark = pytest.mark.shell_4a

REPO = Path(__file__).resolve().parents[3]
CANONICAL = re.compile(r"^lib-[a-z0-9]+(?:-[a-z0-9]+)*$")
BASELINE_SOURCES = [REPO / "tests" / "e2e" / "helpers.py", *sorted((REPO / "tests" / "e2e" / "baseline_1b").glob("*.py"))]
SEED_COLLECTION = "WI13 testid seed"
NEW_IN_SLICE = (
    "lib-theme-toggle",
    "lib-toolbar-view-grid",
    "lib-toolbar-view-list",
    "lib-right-panel",
    "lib-topbar-mobile-menu",
    "lib-topbar-mobile-insights",
    "lib-filter-empty",
)


def _baseline_refs() -> Set[str]:
    refs: Set[str] = set()
    for p in BASELINE_SOURCES:
        refs |= set(re.findall(r"[\"'](lib-[a-z0-9-]+)[\"']", p.read_text(encoding="utf-8")))
    return refs


def test_rendered_testids_canonical_and_cover_baseline(browser: Any, live_server: str) -> None:
    context = s4.new_gated_context(browser)
    seeded_id = None
    try:
        # `lib-sidebar-collection` only renders for an existing collection: seed one, then load.
        made = context.request.post(live_server + "/api/collections", data={"name": SEED_COLLECTION})
        assert made.ok, made.text()
        seeded = made.json()
        seeded_id = (seeded.get("collection") or seeded).get("id")
        page = sl.open_library(context, live_server)
        rendered = page.evaluate(sl.RENDERED_TESTIDS_JS)
    finally:
        if seeded_id:
            context.request.delete(f"{live_server}/api/collections/{seeded_id}")
        context.close()
    bad = sorted({t for t in rendered if not CANONICAL.match(t)})
    assert bad == [], f"non-canonical testids on the library page: {bad}"
    refs = _baseline_refs()
    assert len(refs) >= 10, f"baseline literal scan looks vacuous: {sorted(refs)}"
    missing = sorted(refs - set(rendered))
    assert missing == [], f"baseline references not rendered: {missing}"
    absent = [t for t in NEW_IN_SLICE if t not in rendered]
    assert absent == [], f"slice controls missing: {absent}"
    singles = [t for t in NEW_IN_SLICE if rendered.count(t) != 1]
    assert singles == [], f"slice controls not rendered exactly once: {singles}"
