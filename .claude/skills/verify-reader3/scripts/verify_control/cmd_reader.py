"""`reader state`, `reader select` and `ui inert`, all through the gstack browse wrapper.

`reader state` reads `window.Reader3Epub.getDebugState()` (contract v1). `reader select`
mirrors `tests/e2e/helpers.py::select_in_frame` steps 1-3 inside the reader iframe, always
returns to the main frame, then polls the annotation toolbar from the outer page.
`ui inert` lives in `ui_inert.py`.
"""

import json
import math
import time

from verify_control import browse
from verify_control.envelope import TRY_PREFIX, failure, success
from verify_control.registry import add, group
from verify_control.ui_inert import cmd_inert, compute_inert, valid_testid  # noqa: F401 - re-exported

OWNER = "WI-4"
STATE_JS = "JSON.stringify(window.Reader3Epub.getDebugState())"
IFRAME = '[data-testid="rd-viewport"] iframe'
TOOLBAR_JS = (
    "(() => { const b = document.querySelector('[data-testid=\"rd-anno-toolbar\"]'); "
    'return !!(b && b.classList.contains("is-visible")); })()'
)
STATE_POLL_S = 0.25
TOOLBAR_POLL_S = 0.2
DEBOUNCE_MS, SLACK_MS, SELECT_TIMEOUT_MS = 120, 40, 8000

# Steps 1-3 of `_SELECT_JS` in tests/e2e/helpers.py, run inside the reader iframe. The
# arguments arrive as one JSON array appended by `build_select_js`; the text of this
# function never depends on the needle. Selection is cleared first and the debounce window
# drained, then the range is installed and the release event dispatched in one synchronous
# turn, exactly as the e2e helper does and for the same reason.
# The function must not be async and must not contain the `await` token: gstack's `js`
# wraps such code in a block-bodied async IIFE with no return, which discards the result.
# The drain is therefore a promise chain; Playwright awaits the returned promise.
SELECT_FN = """([quote, occurrence, debounceMs, slackMs, timeoutMs]) => {
  const body = document.body;
  const doc = body.ownerDocument;
  const win = doc.defaultView;
  const sel = doc.getSelection();
  const ui = () => window.parent.Reader3AnnotationUI || null;
  const lastSelectionAt = () => { const u = ui(); return u ? (u.lastSelectionAt || 0) : 0; };
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let text = "";
  while (walker.nextNode()) {
    nodes.push([walker.currentNode, text.length]);
    text += walker.currentNode.data;
  }
  const hits = [];
  for (let i = text.indexOf(quote); i !== -1; i = text.indexOf(quote, i + 1)) hits.push(i);
  if (!hits.length) {
    throw new Error("select_in_frame: text not found in chapter: " + JSON.stringify(quote) +
      " (body has " + text.length + " chars, starts " + JSON.stringify(text.slice(0, 80)) + ")");
  }
  const which = occurrence < 0 ? hits.length + occurrence : occurrence;
  if (which < 0 || which >= hits.length) {
    throw new Error("select_in_frame: occurrence " + occurrence + " requested but " +
      JSON.stringify(quote) + " occurs " + hits.length + " time(s)");
  }
  const start = hits[which];
  const end = start + quote.length;
  const locate = (pos, isEnd) => {
    for (const [node, base] of nodes) {
      const limit = base + node.data.length;
      if (isEnd ? pos <= limit : pos < limit) return [node, pos - base];
    }
    const [node, base] = nodes[nodes.length - 1];
    return [node, pos - base];
  };
  const range = doc.createRange();
  const [startNode, startOffset] = locate(start, false);
  const [endNode, endOffset] = locate(end, true);
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  sel.removeAllRanges();
  const deadline = Date.now() + timeoutMs;
  const drain = () => {
    const age = Date.now() - lastSelectionAt();
    if (age >= debounceMs + slackMs) {
      sel.addRange(range);
      doc.dispatchEvent(new win.MouseEvent("mouseup", { bubbles: true }));
      return { text: sel.toString(), occurrences: hits.length };
    }
    if (Date.now() > deadline) {
      throw new Error("select_in_frame: debounce window did not drain within " + timeoutMs + "ms (age=" + age + "ms)");
    }
    return new Promise((r) => setTimeout(r, Math.max(10, debounceMs + slackMs - age))).then(drain);
  };
  return Promise.resolve().then(drain);
}"""


def build_select_js(text, occurrence):
    """`(SELECT_FN)(<json args>)`; ensure_ascii keeps U+2028 and friends escaped."""
    args = json.dumps([text, occurrence, DEBOUNCE_MS, SLACK_MS, SELECT_TIMEOUT_MS], ensure_ascii=True)
    return "(" + SELECT_FN + ")(" + args + ")"


class _Fail(Exception):
    def __init__(self, env):
        super().__init__(env["error"]["code"])
        self.env = env


def _fail(cmd, code, message, tail, data=None):
    return _Fail(failure(cmd, code, message, TRY_PREFIX + tail, data=data))


def _from_browse(cmd, exc, what=""):
    prefix = f"{what}: " if what else ""
    return _fail(cmd, exc.code, prefix + exc.message, "doctor")


def _run(cmd, body):
    try:
        return body()
    except _Fail as f:
        return f.env
    except browse.BrowseRefused as exc:
        return failure(cmd, exc.code, exc.message, TRY_PREFIX + "--help")


# ---------------------------------------------------------------------------
# reader state
# ---------------------------------------------------------------------------

NOT_READER = ("no reader debug state on this page: window.Reader3Epub.getDebugState() is not available; "
              "check where the browser is with `$B url` and open a /read/<book>/<n> page")


def _read_state(cmd):
    try:
        out = browse.run(["js", STATE_JS])
    except browse.BrowseError as exc:
        if exc.code == "browse_failed" and not exc.timed_out and (
                "getDebugState" in exc.stderr or "Reader3Epub" in exc.stderr):
            raise _fail(cmd, "not_reader_page", NOT_READER, "reader state --wait 15") from None
        raise _from_browse(cmd, exc) from None
    raw = out.strip()
    if raw in ("", "null", "undefined"):
        raise _fail(cmd, "not_reader_page", NOT_READER, "reader state --wait 15")
    try:
        st = json.loads(raw)
    except ValueError:
        raise _fail(cmd, "bad_debug_state", f"debug state is not JSON: {raw[:200]!r}", "reader state") from None
    if not isinstance(st, dict):
        raise _fail(cmd, "bad_debug_state", f"debug state is not an object: {raw[:200]!r}", "reader state")
    v = st.get("v")
    if type(v) is not int or v != 1:
        raise _fail(cmd, "bad_debug_state", f"debug state has v={v!r}; this CLI understands v=1 only",
                    "reader state")
    return st


def _nonneg_float(raw):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v >= 0 else None


def cmd_state(ns):
    cmd = "reader state"

    def body():
        wait = None
        if ns.wait is not None:
            wait = _nonneg_float(ns.wait)
            if wait is None:
                return failure(cmd, "usage", f"--wait must be a non-negative number of seconds, got {ns.wait!r}",
                               TRY_PREFIX + "reader state --help")
        st = _read_state(cmd)
        if wait is None:
            return success(cmd, st)
        deadline = time.monotonic() + wait
        while st.get("ready") is not True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise _fail(cmd, "reader_not_ready", f"reader not ready after {wait:g}s", "reader state --wait 15",
                            data={"last_state": st})
            time.sleep(min(STATE_POLL_S, left))
            st = _read_state(cmd)
        return success(cmd, st)

    return _run(cmd, body)


# ---------------------------------------------------------------------------
# reader select
# ---------------------------------------------------------------------------


def _select_in_frame(cmd, text, occ):
    try:
        browse.run(["frame", IFRAME])
    except browse.BrowseError as exc:
        raise _from_browse(cmd, exc, "entering the reader iframe failed") from None
    try:
        out = browse.run(["js", build_select_js(text, occ)])
    except browse.BrowseError as exc:
        if exc.code == "browse_failed" and not exc.timed_out:
            raise _fail(cmd, "select_failed", exc.message, "reader state") from None
        raise _from_browse(cmd, exc, "select script") from None
    try:
        res = json.loads(out.strip())
    except ValueError:
        res = None
    if not isinstance(res, dict) or not isinstance(res.get("text"), str):
        raise _fail(cmd, "select_failed", f"select script returned {out.strip()[:200]!r}", "reader state")
    return res["text"]


def _frame_main(cmd):
    try:
        browse.run(["frame", "main"])
    except browse.BrowseError as exc:
        return _from_browse(cmd, exc, "frame main failed; the browser may still be inside the reader iframe")
    return None


def _toolbar_visible():
    deadline = time.monotonic() + browse.knob("VERIFY_READER3_TOOLBAR_WAIT_S", 3)
    while True:
        try:
            if browse.run(["js", TOOLBAR_JS]).strip() == "true":
                return True
        except browse.BrowseError:
            pass
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        time.sleep(min(TOOLBAR_POLL_S, left))


def cmd_select(ns):
    cmd = "reader select"

    def body():
        occ = 0
        if ns.occurrence is not None:
            raw = ns.occurrence.strip()
            if not raw.isdigit() or not raw.isascii():
                return failure(cmd, "usage", f"--occurrence must be a non-negative integer, got {ns.occurrence!r}",
                               TRY_PREFIX + "reader select --help")
            occ = int(raw)
        err = restore = None
        selected = None
        try:
            selected = _select_in_frame(cmd, ns.text, occ)
        except _Fail as f:
            err = f
        finally:
            restore = _frame_main(cmd)
        if err is not None:
            raise err
        if restore is not None:
            raise restore
        return success(cmd, {"selected": selected, "toolbar_visible": _toolbar_visible()})

    return _run(cmd, body)


def register(subparsers):
    handlers = {}
    reader = group(subparsers, "reader", help="read and drive the reader page", subcommands=("state", "select"),
                   examples=("reader state", "reader select Alpha"))
    p = add(reader, "reader state", help="print the reader debug state",
            examples=("reader state", "reader state --wait 15"), handlers=handlers, handler=cmd_state)
    p.add_argument("--wait", help="poll until the reader reports ready, up to this many seconds")
    p = add(reader, "reader select", help="select text in the reader and check the annotation toolbar",
            examples=("reader select Alpha", 'reader select "Alpha prose." --occurrence 1'),
            handlers=handlers, handler=cmd_select)
    p.add_argument("text", help="text to select (exact, within the current chapter)")
    p.add_argument("--occurrence", help="0-based occurrence of the text (default 0)")
    ui = group(subparsers, "ui", help="UI checks", subcommands=("inert",), examples=("ui inert --testid lib-main",))
    p = add(ui, "ui inert", help="measure whether an action on the page caused any API request or visible change",
            examples=("ui inert --testid lib-main", "ui inert --testid rd-notes-review --expect inert",
                      "ui inert --settle 1.0 -- press ArrowRight"),
            handlers=handlers, handler=cmd_inert)
    p.add_argument("--testid", help="data-testid of the element to click")
    p.add_argument("--expect", help="inert or active; a mismatch fails with unexpected_inertness")
    p.add_argument("--settle", help="seconds to wait after the action (default 1.0)")
    p.add_argument("--mechanism", help="access_log (default) or network")
    p.add_argument("action", nargs="*", help="after --: a browse command to run instead of a click")
    return handlers
