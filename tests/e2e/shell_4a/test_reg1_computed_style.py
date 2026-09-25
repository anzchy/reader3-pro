"""REG-1 part 2 (013 WI-9, C9.24-C9.26, C9.38, C9.39): the computed-style baseline.

The snapshot `tests/fixtures/snapshots/reg1_computed_style.json` pins nine computed
properties (`shell_4a_fixtures.REG1_PROPS`) of every snapshotted testid on the
library, reader and settings pages, as rendered by the untouched `671f580`
templates and static CSS. Later work items (WI-12, WI-13) may change a value only
by listing it in `reg1_allowed_diffs.json`.

Capture procedure
-----------------
1. Commit 1 of WI-9 adds only the test module, the fixture helper and the snapshot.
2. Capture deliberately, on templates/static that equal HEAD:

       REG1_REGENERATE=1 uv run pytest tests/e2e/shell_4a/test_reg1_computed_style.py --browser chromium

   `write_snapshot` refuses when `git status` shows the templates or static tree
   dirty, and refuses when any snapshotted testid does not match exactly once.
   Without `REG1_REGENERATE=1` nothing is ever written; a missing snapshot fails
   (C9.26). `REG1_SNAPSHOT_PATH` overrides the file location.
3. The JSON records `base_commit` (HEAD's full sha), `source_tree` (the tree hashes
   of `src/reader3_app/web/templates` and `.../static` at HEAD), the testid list per
   page, the property whitelist, the viewport (1440x900), `reduced_motion="reduce"`
   and the values.
4. Capture protocol (matrix header note 6): each page in a fresh context; `goto`
   waits for `load`; the reader additionally waits until the epub.js iframe shows
   chapter 0's text; then `document.fonts.ready`, two rAF ticks, any finite
   animation finished, two more rAF ticks; only then is computed style read.

Every context installs the same egress gate as `tests/e2e/conftest.py::context`, so
the Google Fonts request is aborted and the fallback font stack is what is pinned,
on every machine alike.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest
import shell_4a_fixtures as s4
from conftest import BOOK_ID, _server_env
from helpers import CH0_ANCHOR, reader_frame

pytestmark = pytest.mark.shell_4a

READY: Dict[str, Callable[[Any], Any]] = {"reader": lambda page: reader_frame(page, CH0_ANCHOR)}


def _declared_testids() -> Dict[str, List[str]]:
    return {name: list(s4.REG1_TESTIDS[name]) for name in s4.REG1_PAGE_NAMES}


@pytest.fixture(scope="module")
def reg1_snapshot(browser: Any, live_server: str) -> Callable[[], Dict[str, Any]]:
    """Resolve the snapshot inside the test body, so a missing file is a test failure.

    Resolved once per module; a failed resolution is not cached, so each dependent
    test reports it.
    """
    cache: Dict[str, Dict[str, Any]] = {}

    def _capture() -> Dict[str, Any]:
        cap = s4.capture_all(browser, live_server, BOOK_ID, _declared_testids(), ready_by_page=READY)
        return s4.snapshot_values(cap)

    def _get() -> Dict[str, Any]:
        if "doc" not in cache:
            cache["doc"] = s4.resolve_snapshot(_capture)
        return cache["doc"]

    return _get


def test_c9_24_live_values_equal_snapshot_up_to_the_allowed_diffs(
    browser: Any, live_server: str, reg1_snapshot: Callable[[], Dict[str, Any]]
) -> None:
    snapshot = reg1_snapshot()
    assert snapshot["testids"] == _declared_testids(), (
        "the snapshot's testid list differs from shell_4a_fixtures.REG1_TESTIDS"
    )
    assert snapshot["properties"] == list(s4.REG1_PROPS)
    assert snapshot["viewport"] == s4.VIEWPORT
    assert snapshot["reduced_motion"] == s4.REDUCED_MOTION

    live = s4.snapshot_values(
        s4.capture_all(browser, live_server, BOOK_ID, snapshot["testids"], ready_by_page=READY)
    )
    actual = s4.diff_against(snapshot["values"], live)
    allowed = s4.load_allowed_diffs()
    assert actual == allowed, (
        f"unlisted diffs (changed but not in reg1_allowed_diffs.json): {sorted(actual - allowed)}\n"
        f"stale allowed diffs (listed but no longer differ): {sorted(allowed - actual)}"
    )


def test_c9_25_two_captures_in_fresh_contexts_are_identical(browser: Any, live_server: str) -> None:
    first = s4.capture_all(browser, live_server, BOOK_ID, _declared_testids(), ready_by_page=READY)
    second = s4.capture_all(browser, live_server, BOOK_ID, _declared_testids(), ready_by_page=READY)
    assert first == second


def test_c9_26_missing_snapshot_fails_without_the_regenerate_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "none.json"
    monkeypatch.setenv(s4.SNAPSHOT_PATH_ENV, str(target))
    monkeypatch.delenv(s4.REGENERATE_ENV, raising=False)
    captured: List[bool] = []

    def _capture() -> Dict[str, Any]:
        captured.append(True)
        return {}

    with pytest.raises(pytest.fail.Exception) as info:
        s4.resolve_snapshot(_capture)
    assert "REG1_REGENERATE" in str(info.value)
    assert captured == [], "a capture ran although regeneration was not requested"
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_c9_38_independent_capture_from_a_base_worktree_equals_the_snapshot(
    browser: Any,
    e2e_books_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
    reg1_snapshot: Callable[[], Dict[str, Any]],
) -> None:
    snapshot = reg1_snapshot()
    root = tmp_path_factory.mktemp("reg1-base")
    css_files = [
        p
        for p in s4.git(
            "ls-tree", "-r", "--name-only", s4.BASE_COMMIT, "--", s4.SOURCE_TREE_PATHS["static"]
        ).splitlines()
        if p.endswith(".css")
    ]
    assert css_files, f"no stylesheet under {s4.SOURCE_TREE_PATHS['static']} at {s4.BASE_COMMIT}"

    with s4.base_worktree(s4.BASE_COMMIT, root / "base") as worktree:
        env = s4.base_server_env(worktree, _server_env(e2e_books_dir))
        module_file = s4.served_module_file(worktree, env)
        assert module_file.is_relative_to(worktree.resolve()), (
            f"the base server would import {module_file}, not the {s4.BASE_COMMIT} worktree's code"
        )
        with s4.base_worktree_server(worktree, env, root / "logs") as base_url:
            static_prefix = s4.SOURCE_TREE_PATHS["static"] + "/"
            for rel in css_files:
                served = s4.fetch_bytes(f"{base_url}/static/{rel[len(static_prefix):]}")
                assert served == s4.git_show_bytes(s4.BASE_COMMIT, rel), (
                    f"the base server does not serve {s4.BASE_COMMIT}:{rel}"
                )
            fresh = s4.snapshot_values(
                s4.capture_all(
                    browser, base_url, BOOK_ID, snapshot["testids"], ready_by_page=READY
                )
            )
    assert not (root / "base").exists(), "the base worktree was not removed"
    assert fresh == snapshot["values"], (
        f"committed snapshot differs from an independent {s4.BASE_COMMIT} capture at: "
        f"{sorted(s4.diff_against(snapshot['values'], fresh))}"
    )


def test_c9_39_every_snapshotted_element_is_author_styled(browser: Any, live_server: str) -> None:
    testids = _declared_testids()
    p0 = s4.capture_all(browser, live_server, BOOK_ID, testids, ready_by_page=READY)
    p1 = s4.capture_all(browser, live_server, BOOK_ID, testids, ready_by_page=READY, p1=True)
    assert s4.non_reactive(p0, p1) == set(), "snapshotted testids unmoved by removing first-party CSS"
    assert s4.colour_reactive_pages(p0, p1) == set(s4.REG1_PAGE_NAMES), (
        "a page where no snapshotted color/background-color depends on first-party CSS"
    )


def test_c9_39_selftest_a_bare_injected_wrapper_is_reported(browser: Any, live_server: str) -> None:
    listed = s4.load_selftest_list()
    assert listed == [*s4.REG1_TESTIDS["library"], s4.SELFTEST_TESTID], (
        "reg1_selftest_unstyled.json must be the library list plus the self-test wrapper"
    )
    testids = {"library": listed}
    inject = [s4.SELFTEST_INJECT_JS]
    p0 = s4.capture_all(browser, live_server, BOOK_ID, testids, init_scripts=inject)
    p1 = s4.capture_all(browser, live_server, BOOK_ID, testids, p1=True, init_scripts=inject)
    assert s4.non_reactive(p0, p1) == {("library", s4.SELFTEST_TESTID)}
