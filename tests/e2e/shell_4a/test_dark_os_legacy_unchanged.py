"""013 WI-10 follow-up: under an OS dark preference with no stored theme, the legacy
library and reader pages render exactly as they did at the REG-1 base commit.

At `671f580` no legacy stylesheet, template or script reacts to
`prefers-color-scheme`, so those pages look the same under a dark OS as under a light
one. WI-10 adds the token layer, whose system-dark rule switches the `--r3-*` colours.
If a legacy `--dedao-*` colour variable were repointed at a `--r3-*` token, the
unmigrated pages would turn half-dark on a dark OS. This test catches that: it compares
the REG-1 testid set under emulated dark with an independent capture from a `671f580`
worktree under the same emulation, the same way C9.38 captures its base.

Settings is left out on purpose: its migration (WI-13) owns its dark behaviour. The
reader stays in scope until 014.

Non-vacuity: the emulation must actually be seen by the page (`matchMedia` matches),
and the dark system rule must be in force on the live page (`--r3-bg` resolves to the
dark chrome value). Without that, "equal to base" could hold only because the
emulation or the token layer is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import shell_4a_fixtures as s4
from conftest import BOOK_ID, _server_env
from helpers import CH0_ANCHOR, reader_frame

pytestmark = pytest.mark.shell_4a

# 013 WI-13 migrated the library page (its dark behaviour is now owned by the token layer, and
# A10.3 checks its contrast), so only the reader remains legacy here until 014.
PAGES = ("reader",)
READY = {"reader": lambda page: reader_frame(page, CH0_ANCHOR)}
DARK_PROBE_JS = """() => [
  matchMedia("(prefers-color-scheme: dark)").matches,
  document.documentElement.dataset.theme ?? null,
  getComputedStyle(document.documentElement).getPropertyValue("--r3-bg").trim(),
]"""


def _testids() -> Dict[str, List[str]]:
    return {name: list(s4.REG1_TESTIDS[name]) for name in PAGES}


def test_dark_os_legacy_pages_equal_base_capture(
    browser: Any, live_server: str, e2e_books_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    context = s4.new_gated_context(browser, color_scheme="dark")
    try:
        page = context.new_page()
        page.goto(live_server + s4.page_path("library", BOOK_ID), wait_until="load")
        matches, stamped, bg = page.evaluate(DARK_PROBE_JS)
    finally:
        context.close()
    assert matches is True, "the dark OS emulation did not reach the page"
    assert stamped is None, "no stored theme, so the stamp must leave data-theme absent"
    assert bg.lower() == "#0b1220", f"the system-dark token rule is not in force (--r3-bg={bg!r})"

    live = s4.snapshot_values(
        s4.capture_all(browser, live_server, BOOK_ID, _testids(), ready_by_page=READY, color_scheme="dark")
    )

    root = tmp_path_factory.mktemp("dark-os-base")
    with s4.base_worktree(s4.BASE_COMMIT, root / "base") as worktree:
        env = s4.base_server_env(worktree, _server_env(e2e_books_dir))
        assert s4.served_module_file(worktree, env).is_relative_to(worktree.resolve())
        with s4.base_worktree_server(worktree, env, root / "logs") as base_url:
            base = s4.snapshot_values(
                s4.capture_all(browser, base_url, BOOK_ID, _testids(), ready_by_page=READY, color_scheme="dark")
            )
    assert all(v is not None for p in base.values() for v in p.values()), "a testid did not match at the base"
    diffs = sorted(s4.diff_against(base, live))
    assert diffs == [], f"under a dark OS the legacy pages differ from {s4.BASE_COMMIT} at: {diffs}"
