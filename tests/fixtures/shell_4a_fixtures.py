"""REG-1 (013 WI-9, acceptance A9.10) shared helpers for `tests/e2e/shell_4a/`.

Group directories cannot hold a `conftest.py` or `__init__.py` (see
`scripts/lint_e2e_groups.py`), so the helpers live here, following the
`deg_assertions.py` precedent. Test modules wrap them in their own module-level
fixtures. `tests/fixtures/` is put on `sys.path` by `tests/conftest.py`.

What is here:

    REG1_PROPS / REG1_TESTIDS / REG1_PAGE_NAMES   what the snapshot covers
    page_path(page_name, book_id)                 URL path per page
    new_gated_context(browser, p1=..., ...)       a fresh browser context with the egress gate
    capture_page(context, base_url, ...)          one capture under the header-note-6 protocol
    snapshot_values(capture)                      raw values in snapshot shape
    diff_against(expected, actual)                itemised (page, testid, prop) diff set
    non_reactive(p0, p1)                          pairs whose own-signature did not move
    colour_reactive_pages(p0, p1)                 pages where some color/background moved
    snapshot_path() / load_snapshot() / write_snapshot()
    base_worktree(commit, dest) / base_worktree_server(...)

**Why a separate context helper instead of the `page` fixture.** The frozen
`tests/e2e/conftest.py::context` fixture carries the egress gate but not the
capture's viewport (1440x900) or `reduced_motion="reduce"`, and C9.39 needs a
second, perturbed context in the same test. Every context made here installs its
own copy of the same gate: without it the Google Fonts `<link>` blocks `load`.

**Why "own signature" for C9.39.** Inherited properties (color, font-*,
line-height) of an element with no author rule of its own still change when its
ancestors lose their CSS, so a raw P0-vs-P1 comparison would call a bare wrapper
"styled". For those five properties the signature records `<inherit>` when the
element's computed value equals its parent's, so only a value the element does
not simply inherit counts as its own. Non-inherited properties are compared raw.
The self-test case proves the check can fail: a bare injected
`<div data-testid="lib-selftest-wrapper">` must be reported, and only it.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "tests" / "fixtures" / "snapshots"
DEFAULT_SNAPSHOT_PATH = SNAPSHOT_DIR / "reg1_computed_style.json"
ALLOWED_DIFFS_PATH = SNAPSHOT_DIR / "reg1_allowed_diffs.json"
SELFTEST_LIST_PATH = SNAPSHOT_DIR / "reg1_selftest_unstyled.json"

#: The commit the baseline must describe: the untouched templates and static CSS.
BASE_COMMIT = "671f580"
#: The two trees whose hashes the snapshot records (`source_tree`).
SOURCE_TREE_PATHS: Dict[str, str] = {
    "templates": "src/reader3_app/web/templates",
    "static": "src/reader3_app/web/static",
}

REGENERATE_ENV = "REG1_REGENERATE"
SNAPSHOT_PATH_ENV = "REG1_SNAPSHOT_PATH"

VIEWPORT: Dict[str, int] = {"width": 1440, "height": 900}
REDUCED_MOTION = "reduce"

#: The nine-property whitelist.
REG1_PROPS: Tuple[str, ...] = (
    "color",
    "background-color",
    "font-family",
    "font-size",
    "font-weight",
    "line-height",
    "padding",
    "border-radius",
    "display",
)
INHERITED_PROPS = frozenset({"color", "font-family", "font-size", "font-weight", "line-height"})
COLOUR_PROPS = ("color", "background-color")

REG1_PAGE_NAMES: Tuple[str, ...] = ("library", "reader", "settings")

#: Snapshotted testids per page. Selection rule, applied mechanically on 671f580:
#: every testid that renders exactly once on the page (C9.24 needs count == 1), minus
#: the ones whose own signature does not change when first-party CSS is removed
#: (C9.39). Excluded as not author-styled: `lib-live-region`, `lib-search-results`,
#: `rd-ai-panel-resizer`, `rd-viewport`. Excluded as multi-instance: `lib-book-card`,
#: `lib-book-row`, `rd-toc-row`, and the per-provider `set-provider-*` family.
REG1_TESTIDS: Dict[str, Tuple[str, ...]] = {
    "library": (
        "lib-add-to-collection-select", "lib-book-grid", "lib-book-table", "lib-brand",
        "lib-bulk-bar", "lib-bulk-collection", "lib-bulk-index", "lib-bulk-select-all",
        "lib-bulk-select-none", "lib-chat-input", "lib-chat-scope", "lib-chat-send",
        "lib-chat-stop", "lib-chat-thread", "lib-collection-name-input", "lib-index-errors",
        "lib-insights", "lib-insights-collapse", "lib-main", "lib-modal-add-books",
        "lib-modal-add-books-close", "lib-modal-add-books-primary",
        "lib-modal-add-to-collection", "lib-modal-add-to-collection-cancel",
        "lib-modal-add-to-collection-close", "lib-modal-create-collection",
        "lib-modal-create-collection-cancel", "lib-modal-create-collection-close",
        "lib-modal-create-collection-primary", "lib-modal-index-errors",
        "lib-modal-index-errors-close", "lib-modal-index-errors-primary", "lib-panel-chat",
        "lib-panel-dashboard", "lib-panel-refresh-stats", "lib-panel-search",
        "lib-panel-tab-chat", "lib-panel-tab-dashboard", "lib-panel-tab-search",
        "lib-search-case", "lib-search-clear", "lib-search-input", "lib-search-mode",
        "lib-search-sort", "lib-shell", "lib-sidebar", "lib-sidebar-create-collection",
        "lib-sidebar-scope-all", "lib-sidebar-scope-epub", "lib-sidebar-scope-pdf",
        "lib-toolbar-filter", "lib-toolbar-select-mode", "lib-toolbar-sort", "lib-topbar",
        "lib-topbar-add-books", "lib-topbar-nav-library", "lib-topbar-nav-settings",
    ),
    "reader": (
        "rd-ai-clear", "rd-ai-export", "rd-ai-history-list", "rd-ai-input", "rd-ai-new",
        "rd-ai-panel", "rd-ai-panel-close", "rd-ai-send", "rd-ai-stop", "rd-ai-thread",
        "rd-anno-ask", "rd-anno-color-blue", "rd-anno-color-green", "rd-anno-color-pink",
        "rd-anno-color-yellow", "rd-anno-colors", "rd-anno-copy", "rd-anno-delete",
        "rd-anno-note", "rd-anno-toolbar", "rd-anno-type-marker", "rd-anno-type-underline",
        "rd-anno-type-wavy", "rd-chapter-count", "rd-chapter-nav", "rd-chapter-next",
        "rd-conflict-dialog", "rd-conflict-keep-mine", "rd-conflict-take-remote", "rd-error",
        "rd-font-popover", "rd-note-editor", "rd-note-editor-cancel", "rd-note-editor-input",
        "rd-note-editor-primary", "rd-note-tooltip", "rd-notes-copy-all", "rd-notes-panel",
        "rd-notes-review", "rd-page-indicator", "rd-page-next", "rd-page-prev",
        "rd-pref-font-hei", "rd-pref-font-kai", "rd-pref-font-song", "rd-pref-font-system",
        "rd-pref-leading", "rd-pref-size", "rd-pref-theme-green", "rd-pref-theme-night",
        "rd-pref-theme-paper", "rd-pref-theme-sepia", "rd-rail", "rd-rail-ai", "rd-rail-font",
        "rd-rail-notes", "rd-rail-search", "rd-rail-toc", "rd-search-index-status",
        "rd-search-input", "rd-search-mode", "rd-search-panel", "rd-search-panel-close",
        "rd-search-results", "rd-shell", "rd-stage", "rd-toc-filter", "rd-toc-panel",
    ),
    "settings": (
        "set-data-cache", "set-data-conversations", "set-export-settings", "set-screen",
        "set-topbar", "set-topbar-back-to-library",
    ),
}

SELFTEST_TESTID = "lib-selftest-wrapper"

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Header note 6: `load` (awaited by `goto`), then `document.fonts.ready`, then two
#: rAF ticks. Finite animations are then awaited and two more ticks taken; under
#: `reduced_motion="reduce"` that is normally a no-op, and it keeps a transition that
#: survives reduced motion from being sampled mid-flight.
#:
#: For each requested testid it returns the match count, the element's computed
#: values (`v`) and its parent's (`p`), the latter only to build the own signature.
CAPTURE_JS = r"""
async ({props, testids}) => {
  await document.fonts.ready;
  const raf = () => new Promise((r) => requestAnimationFrame(() => r()));
  await raf(); await raf();
  const finite = document.getAnimations().filter((a) => {
    const t = a.effect && a.effect.getComputedTiming();
    return t && Number.isFinite(t.endTime);
  });
  await Promise.all(finite.map((a) => a.finished.catch(() => null)));
  await raf(); await raf();
  const out = {};
  for (const tid of testids) {
    const els = document.querySelectorAll('[data-testid="' + CSS.escape(tid) + '"]');
    if (els.length !== 1) { out[tid] = {count: els.length, v: null, p: null}; continue; }
    const el = els[0];
    const cs = getComputedStyle(el);
    const ps = el.parentElement ? getComputedStyle(el.parentElement) : null;
    const v = {}, p = {};
    for (const k of props) {
      v[k] = cs.getPropertyValue(k);
      p[k] = ps ? ps.getPropertyValue(k) : null;
    }
    out[tid] = {count: 1, v, p};
  }
  return out;
}
"""

#: P1: strip inline author styles once the DOM is ready (and again at `load`, for
#: anything a script added in between). Stylesheet requests are aborted by the route.
STRIP_AUTHOR_STYLES_JS = r"""
(() => {
  const strip = () => {
    document.querySelectorAll('style').forEach((s) => s.remove());
    document.querySelectorAll('link[rel="stylesheet"]').forEach((s) => s.remove());
    document.querySelectorAll('[style]').forEach((e) => e.removeAttribute('style'));
  };
  document.addEventListener('DOMContentLoaded', strip);
  window.addEventListener('load', strip);
})();
"""

#: C9.39 self-test: a bare wrapper with no author rule matching it, top frame only.
SELFTEST_INJECT_JS = r"""
(() => {
  if (window.top !== window) return;
  document.addEventListener('DOMContentLoaded', () => {
    const d = document.createElement('div');
    d.setAttribute('data-testid', 'lib-selftest-wrapper');
    d.textContent = 'selftest';
    document.body.appendChild(d);
  });
})();
"""

Capture = Dict[str, Dict[str, Dict[str, Any]]]  # page -> testid -> {count, v, p}
DiffItem = Tuple[str, str, str]  # (page, testid, prop | "__presence__")


def page_path(page_name: str, book_id: str) -> str:
    return {
        "library": "/",
        "reader": f"/read/{book_id}/0",
        "settings": "/settings",
    }[page_name]


def _is_first_party_stylesheet(parsed_path: str, resource_type: str) -> bool:
    return resource_type == "stylesheet" or (
        parsed_path.startswith("/static/") and parsed_path.endswith(".css")
    )


def new_gated_context(
    browser: Any,
    *,
    p1: bool = False,
    init_scripts: Sequence[str] = (),
    blocked: Optional[List[str]] = None,
    color_scheme: Optional[str] = None,
) -> Any:
    """A fresh context at the capture viewport, with the same egress gate as conftest.

    `color_scheme` ("dark" / "light") emulates the OS preference; None leaves
    Playwright's default, which every capture before 013 WI-10's dark-OS check used.

    `p1=True` additionally aborts first-party stylesheets and strips `<style>` and
    `style=`. Aborted external URLs are appended to `blocked` when given, so a caller
    can tell a gate-induced console error from a real one.
    """
    options: Dict[str, Any] = {"viewport": dict(VIEWPORT), "reduced_motion": REDUCED_MOTION}
    if color_scheme is not None:
        options["color_scheme"] = color_scheme
    context = browser.new_context(**options)

    def _gate(route: Any, request: Any) -> None:
        parsed = urlparse(request.url)
        local = parsed.scheme not in ("http", "https") or parsed.hostname in _LOCAL_HOSTS
        if not local:
            if blocked is not None:
                blocked.append(request.url)
            route.abort()
            return
        if p1 and parsed.scheme in ("http", "https") and _is_first_party_stylesheet(
            parsed.path, request.resource_type
        ):
            route.abort()
            return
        route.continue_()

    context.route("**/*", _gate)
    if p1:
        context.add_init_script(STRIP_AUTHOR_STYLES_JS)
    for script in init_scripts:
        context.add_init_script(script)
    return context


def capture_page(
    context: Any,
    base_url: str,
    page_name: str,
    book_id: str,
    testids: Sequence[str],
    *,
    ready: Optional[Callable[[Any], Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Open one page in `context`, wait per header note 6, return the raw capture."""
    page = context.new_page()
    try:
        page.goto(base_url + page_path(page_name, book_id), wait_until="load")
        if ready is not None:
            ready(page)
        return page.evaluate(CAPTURE_JS, {"props": list(REG1_PROPS), "testids": list(testids)})
    finally:
        page.close()


def capture_all(
    browser: Any,
    base_url: str,
    book_id: str,
    testids_by_page: Mapping[str, Sequence[str]],
    *,
    ready_by_page: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    p1: bool = False,
    init_scripts: Sequence[str] = (),
    color_scheme: Optional[str] = None,
) -> Capture:
    """One capture per page, each page in its own fresh context."""
    out: Capture = {}
    for page_name, testids in testids_by_page.items():
        context = new_gated_context(
            browser, p1=p1, init_scripts=init_scripts, color_scheme=color_scheme
        )
        try:
            ready = (ready_by_page or {}).get(page_name)
            out[page_name] = capture_page(
                context, base_url, page_name, book_id, testids, ready=ready
            )
        finally:
            context.close()
    return out


#: Chromium on macOS serialises the computed `font-family` token `BlinkMacSystemFont`
#: as `"system-ui"`; on Linux it keeps the literal. The committed snapshot was taken
#: on macOS, so the macOS form is canonical (tests/unit/test_reg1_font_family_canonical.py).
_FONT_FAMILY_ALIASES: Tuple[Tuple[str, str], ...] = (("BlinkMacSystemFont", '"system-ui"'),)


def _canonical(values: Dict[str, str]) -> Dict[str, str]:
    family = values.get("font-family")
    if family is None:
        return values
    for literal, canonical in _FONT_FAMILY_ALIASES:
        family = family.replace(literal, canonical)
    return {**values, "font-family": family}


def snapshot_values(capture: Capture) -> Dict[str, Dict[str, Optional[Dict[str, str]]]]:
    """Values in snapshot shape; `None` for a testid that did not match exactly once.

    Raw except for `_canonical`, which folds platform-specific `font-family` aliases.
    """
    return {
        page: {
            tid: (_canonical(entry["v"]) if entry["count"] == 1 else None)
            for tid, entry in entries.items()
        }
        for page, entries in capture.items()
    }


def diff_against(
    expected: Mapping[str, Mapping[str, Optional[Mapping[str, str]]]],
    actual: Mapping[str, Mapping[str, Optional[Mapping[str, str]]]],
) -> Set[DiffItem]:
    """Itemised differences. A testid missing on either side is `__presence__`, never skipped."""
    diffs: Set[DiffItem] = set()
    for page in set(expected) | set(actual):
        exp_page = expected.get(page, {})
        act_page = actual.get(page, {})
        for tid in set(exp_page) | set(act_page):
            e = exp_page.get(tid)
            a = act_page.get(tid)
            if e is None or a is None:
                diffs.add((page, tid, "__presence__"))
                continue
            for prop in set(e) | set(a):
                if e.get(prop) != a.get(prop):
                    diffs.add((page, tid, prop))
    return diffs


def own_signature(entry: Mapping[str, Any]) -> Optional[Dict[str, str]]:
    if entry.get("count") != 1:
        return None
    v, p = entry["v"], entry["p"] or {}
    return {
        k: ("<inherit>" if k in INHERITED_PROPS and p.get(k) == v[k] else v[k]) for k in REG1_PROPS
    }


def non_reactive(p0: Capture, p1: Capture) -> Set[Tuple[str, str]]:
    """`(page, testid)` pairs whose own signature is identical with and without first-party CSS.

    A testid that does not match exactly once in either capture is reported too: an
    element that is not there cannot be shown to be author-styled.
    """
    out: Set[Tuple[str, str]] = set()
    for page, entries in p0.items():
        for tid, entry in entries.items():
            s0 = own_signature(entry)
            s1 = own_signature(p1.get(page, {}).get(tid, {}))
            if s0 is None or s1 is None or s0 == s1:
                out.add((page, tid))
    return out


def colour_reactive_pages(p0: Capture, p1: Capture) -> Set[str]:
    """Pages where at least one testid's raw `color` or `background-color` differs P0 vs P1."""
    pages: Set[str] = set()
    for page, entries in p0.items():
        for tid, entry in entries.items():
            other = p1.get(page, {}).get(tid)
            if entry.get("count") != 1 or not other or other.get("count") != 1:
                continue
            if any(entry["v"][k] != other["v"][k] for k in COLOUR_PROPS):
                pages.add(page)
                break
    return pages


# ---------------------------------------------------------------------------
# Snapshot files
# ---------------------------------------------------------------------------


def snapshot_path() -> Path:
    override = os.environ.get(SNAPSHOT_PATH_ENV)
    return Path(override) if override else DEFAULT_SNAPSHOT_PATH


def regenerate_requested() -> bool:
    return os.environ.get(REGENERATE_ENV) == "1"


def load_snapshot(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read the snapshot. A missing file fails the test; it is never created here."""
    path = snapshot_path() if path is None else path
    if not path.exists():
        pytest.fail(
            f"REG-1 snapshot {path} does not exist. It is never created implicitly: capture it "
            f"deliberately on the untouched {BASE_COMMIT} templates with "
            f"{REGENERATE_ENV}=1 uv run pytest tests/e2e/shell_4a/test_reg1_computed_style.py "
            "--browser chromium",
            pytrace=False,
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_snapshot(capture_values: Callable[[], Mapping[str, Any]]) -> Dict[str, Any]:
    """The only way a test obtains the snapshot.

    With `REG1_REGENERATE=1`, `capture_values()` runs and its result is written to
    `snapshot_path()` first. Without it, nothing is captured and nothing is written;
    a missing file fails.
    """
    path = snapshot_path()
    if regenerate_requested():
        write_snapshot(path, capture_values())
    return load_snapshot(path)


def load_allowed_diffs() -> Set[DiffItem]:
    raw = json.loads(ALLOWED_DIFFS_PATH.read_text(encoding="utf-8"))
    return {(str(p), str(t), str(k)) for p, t, k in raw["allowed"]}


def load_selftest_list() -> List[str]:
    raw = json.loads(SELFTEST_LIST_PATH.read_text(encoding="utf-8"))
    return list(raw["library"])


def git(*args: str, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}\n"
            f"REG-1 needs commit {BASE_COMMIT} in the object store; a shallow clone "
            "(actions/checkout default fetch-depth 1) does not have it."
        )
    return proc.stdout.strip()


def git_show_bytes(commit: str, rel_path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{commit}:{rel_path}"],
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git show {commit}:{rel_path} failed: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def write_snapshot(path: Path, values: Mapping[str, Any]) -> None:
    """Write the snapshot, refusing when the captured trees are not the committed ones.

    The metadata is what C9.23 checks and what C9.38 re-derives independently: HEAD's
    full sha and the tree hashes of the templates and static directories at HEAD.
    """
    missing = sorted(
        f"{page}/{tid}" for page, entries in values.items() for tid, v in entries.items() if v is None
    )
    if missing:
        raise RuntimeError(
            f"Refusing to write the REG-1 snapshot: not exactly one match for {missing}."
        )
    dirty = git("status", "--porcelain", "--", *SOURCE_TREE_PATHS.values())
    if dirty:
        raise RuntimeError(
            "Refusing to write the REG-1 snapshot: templates/static differ from HEAD, so the "
            f"capture would describe no commit.\n{dirty}"
        )
    doc = {
        "schema": 1,
        "base_commit": git("rev-parse", "HEAD"),
        "source_tree": {k: git("rev-parse", f"HEAD:{p}") for k, p in SOURCE_TREE_PATHS.items()},
        "viewport": dict(VIEWPORT),
        "reduced_motion": REDUCED_MOTION,
        "properties": list(REG1_PROPS),
        "pages": {name: page_path(name, "{book_id}") for name in REG1_PAGE_NAMES},
        "testids": {name: list(REG1_TESTIDS[name]) for name in REG1_PAGE_NAMES},
        "values": values,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# C9.38: an independent checkout of the base commit, served by its own process
# ---------------------------------------------------------------------------


@contextmanager
def base_worktree(commit: str, dest: Path) -> Iterator[Path]:
    """`git worktree add --detach dest commit`; `git worktree remove --force` on the way out."""
    git("worktree", "add", "--detach", str(dest), commit)
    try:
        yield dest
    finally:
        git("worktree", "remove", "--force", str(dest))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def base_server_env(worktree: Path, server_env: Mapping[str, str]) -> Dict[str, str]:
    env = dict(server_env)
    env["PYTHONPATH"] = str(worktree / "src")
    return env


def served_module_file(worktree: Path, env: Mapping[str, str]) -> Path:
    """Which `reader3_app.web.server` the base server's interpreter actually imports."""
    proc = subprocess.run(
        [sys.executable, "-c", "import reader3_app.web.server as s; print(s.__file__)"],
        cwd=worktree,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"cannot import the base server module: {proc.stderr[-2000:]}")
    return Path(proc.stdout.strip()).resolve()


@contextmanager
def base_worktree_server(
    worktree: Path, env: Mapping[str, str], log_dir: Path, *, startup_timeout_s: float = 60
) -> Iterator[str]:
    """Serve `worktree`'s own code: uvicorn from the worktree cwd with its `src` first on the path.

    Same recipe as `deg_assertions.pickle_fallback_server` (free port, poll `/api/health`,
    log to a file) but without `READER3_ALLOW_PICKLE`, and with a cwd, which that launcher
    does not take. Failures raise `RuntimeError`; they never skip.
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    cmd = [sys.executable, "-m", "uvicorn", "reader3_app.web.server:app", "--port", str(port)]
    log_path = Path(log_dir) / f"reg1-base-server-{port}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("w", encoding="utf-8")

    def _tail(limit: int = 4000) -> str:
        log_fh.flush()
        return log_path.read_text(encoding="utf-8", errors="replace")[-limit:]

    try:
        server = subprocess.Popen(
            cmd, cwd=worktree, env=dict(env), stdout=log_fh, stderr=subprocess.STDOUT, text=True
        )
    except OSError as exc:
        log_fh.close()
        raise RuntimeError(f"REG-1 base server cannot start: {cmd} -> {exc}") from exc
    try:
        deadline = time.monotonic() + startup_timeout_s
        ready = False
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(
                    f"REG-1 base server exited at startup (rc={server.returncode}):\n{_tail()}"
                )
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                    if r.status == 200:
                        ready = True
                        break
            except (urllib.error.URLError, ConnectionError, OSError):
                # Not listening yet; the only action is to wait.
                time.sleep(0.1)
        if not ready:
            raise RuntimeError(f"REG-1 base server not ready in {startup_timeout_s}s:\n{_tail()}")
        yield base
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        log_fh.close()


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read()
