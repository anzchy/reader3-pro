"""WI-4b: what the real gstack browse binary prints, which the WI-4 fakes did not model.

Captured live in the WI-7 sandbox proof (`tests/unit/fixtures/verify_control/browse_*_real.txt`):

* A - page-content commands (`attrs`, ...) wrap stdout in an UNTRUSTED EXTERNAL CONTENT
  envelope, and a missing element is rc=0 with `Element not found: <selector>` inside it;
* B - gstack's `js` wraps any code containing the token `await` (multi-line, or with `;` or a
  keyword) as `(async()=>{\\n<code>\\n})()` with no return, so the result is lost;
* D - real `network` lines carry `?ms` durations and negative sizes.

C (the `book index` offline hint) lives with the other `book index` cases in
`test_verify_control_books_api.py`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from verify_control_fakes_access import fake_access_server, fake_browse, read_argv_log, stop_server
from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    REPO,
    TRY_PREFIX,
    base_env,
    make_state,
    real_evidence_untouched,
    reap_fakes,
    run_cli,
)
from verify_control import access_log, browse, cmd_reader

FIX = REPO / "tests" / "unit" / "fixtures" / "verify_control"
ATTRS_REAL = (FIX / "browse_attrs_real.txt").read_text(encoding="utf-8")
ATTRS_MISSING_REAL = (FIX / "browse_attrs_missing_real.txt").read_text(encoding="utf-8")
NETWORK_REAL = (FIX / "browse_network_real.txt").read_text(encoding="utf-8")
PKG = REPO / ".claude" / "skills" / "verify-reader3" / "scripts" / "verify_control"
REAL_ATTRS = {
    "type": "button", "class": "rt-btn is-active", "id": "reader-notes-toggle",
    "data-testid": "rd-rail-notes", "title": "Notes",
}
BEGIN = "--- BEGIN UNTRUSTED EXTERNAL CONTENT (source: {src}) ---"
END = "--- END UNTRUSTED EXTERNAL CONTENT ---"


def wrap(payload: str, src: str = "http://127.0.0.1:62429/read/smoke_data/0") -> str:
    """The envelope exactly as gstack prints it (see the real fixtures)."""
    return BEGIN.format(src=src) + "\n" + payload + "\n" + END + "\n"


def _unwrap(text: str) -> str:
    if not hasattr(browse, "unwrap"):
        pytest.fail("verify_control.browse has no unwrap(out) yet")
    return browse.unwrap(text)


# ---------------------------------------------------------------------------
# A: the untrusted-content envelope
# ---------------------------------------------------------------------------


def test_a1_fixture_is_the_wrapped_form():  # WI-4b A1 (guards the fixture itself)
    assert ATTRS_REAL.startswith("--- BEGIN UNTRUSTED EXTERNAL CONTENT (source: http://")
    assert ATTRS_REAL.rstrip("\n").endswith(END)
    assert wrap(json.dumps(REAL_ATTRS, indent=2)) == ATTRS_REAL


def test_a2_unwrap_real_attrs_sample():  # WI-4b A2
    inner = _unwrap(ATTRS_REAL)
    assert json.loads(inner) == REAL_ATTRS
    assert "UNTRUSTED" not in inner and "source:" not in inner


def test_a3_unwrap_real_missing_sample():  # WI-4b A3
    assert _unwrap(ATTRS_MISSING_REAL).strip() == 'Element not found: [data-testid="nope-missing"]'


@pytest.mark.parametrize(
    "text",
    [
        json.dumps(REAL_ATTRS),
        json.dumps(REAL_ATTRS) + "\n",
        "",
        "http://127.0.0.1:62429/read/smoke_data/0\n",
        BEGIN.format(src="http://x/") + "\n{}\n",  # a BEGIN without its END is not an envelope
        "{}\n" + END + "\n",  # an END without its BEGIN is not an envelope
        "prefix\n" + wrap("{}"),  # the envelope must start the output
    ],
    ids=["bare-json", "bare-json-nl", "empty", "url", "begin-only", "end-only", "not-leading"],
)
def test_a4_unwrap_passes_unwrapped_text_through_unchanged(text):  # WI-4b A4
    assert _unwrap(text) == text


def test_a5_source_url_is_never_payload():  # WI-4b A5
    src = 'http://127.0.0.1:1/read/x?q={"evil":1}) ---'
    inner = _unwrap(wrap('{"a": "1"}', src=src))
    assert json.loads(inner) == {"a": "1"}
    assert "evil" not in inner


_payload = st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters="\r\n\x0b\x0c\x1c\x1d\x1e\x85  "), max_size=40)


@settings(deadline=None, max_examples=200)
@given(st.lists(_payload, min_size=1, max_size=6), st.from_regex(r"https?://[a-z0-9.:/_?=&-]{1,40}", fullmatch=True))
def test_a6_unwrap_round_trip_property(lines, src):  # WI-4b A6
    payload = "\n".join(lines)
    if END in payload.split("\n"):
        return
    assert _unwrap(wrap(payload, src=src)) == payload


class Inert(NamedTuple):
    env: Dict[str, str]
    base: str
    log: Path
    argv_log: Path


@pytest.fixture
def servers():
    procs: List[Any] = []
    yield procs
    for p in procs:
        stop_server(p)


SEED = ["INFO:     Started server process [4242]", "INFO:     Application startup complete."]


def inert_env(tmp_path, servers, attrs) -> Inert:
    log = tmp_path / "srvlog" / "server.log"
    port, proc = fake_access_server(tmp_path, log, seed_lines=SEED)
    servers.append(proc)
    base = f"http://127.0.0.1:{port}"
    sp = make_state(tmp_path, base_url=base, port=port, log=log, pid=proc.pid)
    fb = fake_browse(tmp_path, [
        {"sub": "url", "contains": None, "responses": [{"stdout": base + "/read/smoke_data/0\n"}]},
        {"sub": "attrs", "contains": None, "responses": attrs},
        {"sub": "click", "contains": None, "responses": [{}]},
    ])
    env = base_env(tmp_path) | {"VERIFY_READER3_STATE": str(sp), "FAKE_BROWSE_BASE_URL": base}
    return Inert(env, base, log, fb.argv_log)


ARGV = ["ui", "inert", "--testid", "rd-rail-notes", "--settle", "0.1"]


def test_a7_wrapped_attrs_identical_is_inert(tmp_path, servers):  # WI-4b A7
    ie = inert_env(tmp_path, servers, [{"stdout": ATTRS_REAL}])
    code, e, _ = run_cli(ARGV + ["--expect", "inert"], ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["attrs_before"] == REAL_ATTRS and d["attrs_after"] == REAL_ATTRS
    assert d["requests"] == [] and d["url_changed"] is False and d["inert"] is True
    assert [a[0] for a in read_argv_log(ie.argv_log)] == ["url", "attrs", "click", "url", "attrs"]


def test_a8_wrapped_attrs_differ_is_active(tmp_path, servers):  # WI-4b A8
    after = dict(REAL_ATTRS, **{"class": "rt-btn"})
    ie = inert_env(tmp_path, servers, [{"stdout": ATTRS_REAL}, {"stdout": wrap(json.dumps(after, indent=2))}])
    code, e, _ = run_cli(ARGV + ["--expect", "inert"], ie.env)
    assert code == 1, e
    assert e["error"]["code"] == "unexpected_inertness"
    d = e["data"]
    assert d["attrs_before"] == REAL_ATTRS and d["attrs_after"] == after
    assert d["requests"] == [] and d["url_changed"] is False and d["inert"] is False


def test_a9_element_not_found_is_testid_not_found(tmp_path, servers):  # WI-4b A9
    missing = ATTRS_MISSING_REAL.replace("nope-missing", "rd-rail-notes")
    ie = inert_env(tmp_path, servers, [{"stdout": missing}])
    code, e, _ = run_cli(ARGV, ie.env)
    assert code == 1, e
    assert e["ok"] is False and e["data"] is None
    assert set(e["error"]) == {"code", "message", "try"}
    assert e["error"]["code"] == "testid_not_found"
    assert "rd-rail-notes" in e["error"]["message"]
    assert "UNTRUSTED" not in e["error"]["message"]
    assert e["error"]["try"] == TRY_PREFIX + "reader state"
    assert [a[0] for a in read_argv_log(ie.argv_log)] == ["url", "attrs"]
    assert "verify-marker" not in ie.log.read_text(encoding="utf-8")


def test_a10_wrapped_non_json_is_still_browse_failed(tmp_path, servers):  # WI-4b A10
    ie = inert_env(tmp_path, servers, [{"stdout": wrap("not json at all")}])
    code, e, _ = run_cli(ARGV, ie.env)
    assert code == 1, e
    assert e["error"]["code"] == "browse_failed"
    assert "rd-rail-notes" in e["error"]["message"]
    assert "click" not in [a[0] for a in read_argv_log(ie.argv_log)]


# ---------------------------------------------------------------------------
# B: no `await` in anything sent to `browse js`
# ---------------------------------------------------------------------------

COVERED = {"STATE_JS", "TOOLBAR_JS", "build_select_js", "SELECT_FN"}


def _snippets() -> Dict[str, str]:
    return {
        "STATE_JS": cmd_reader.STATE_JS,
        "TOOLBAR_JS": cmd_reader.TOOLBAR_JS,
        "SELECT_FN": cmd_reader.SELECT_FN,
        "build_select_js": cmd_reader.build_select_js("Alpha prose.", 0),
    }


def _gstack_has_await(code: str) -> bool:
    """Port of gstack browse `hasAwait` (src/read-commands.ts)."""
    stripped = re.sub(r"//.*$", "", code, flags=re.M)
    stripped = re.sub(r"/\*[\s\S]*?\*/", "", stripped)
    return re.search(r"\bawait\b", stripped) is not None


def test_b1_every_js_payload_in_the_package_is_covered():  # WI-4b B1
    found = set()
    for path in sorted(PKG.glob("*.py")):
        for m in re.finditer(r'\[\s*"js"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)', path.read_text(encoding="utf-8")):
            found.add(m.group(1))
    assert found, "no `browse js` call sites found; has the package moved?"
    assert found <= COVERED, found - COVERED


@pytest.mark.parametrize("name", sorted(_snippets()))
def test_b2_no_await_no_async_in_js_payloads(name):  # WI-4b B2
    code = _snippets()[name]
    assert not _gstack_has_await(code), f"{name} would be wrapped by gstack and lose its result"
    assert re.search(r"\basync\b", code) is None, name


_HARNESS = r"""
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
// gstack browse src/read-commands.ts, verbatim logic
function hasAwait(c) {
  const stripped = c.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  return /\bawait\b/.test(stripped);
}
function needsBlockWrapper(c) {
  const trimmed = c.trim();
  if (trimmed.split('\n').length > 1) return true;
  if (/\b(const|let|var|function|class|return|throw|if|for|while|switch|try)\b/.test(trimmed)) return true;
  if (trimmed.includes(';')) return true;
  return false;
}
function wrapForEvaluate(c) {
  if (!hasAwait(c)) return c;
  const trimmed = c.trim();
  return needsBlockWrapper(trimmed) ? `(async()=>{\n${c}\n})()` : `(async()=>(${trimmed}))()`;
}
const events = [];
const nodes = [{ data: "Intro. Alpha " }, { data: "prose. Tail." }];
const sel = {
  range: null,
  removeAllRanges() { events.push("removeAllRanges"); this.range = null; },
  addRange(r) { events.push("addRange"); this.range = r; },
  toString() {
    const r = this.range;
    if (!r) return "";
    if (r.sn === r.en) return r.sn.data.slice(r.so, r.eo);
    return r.sn.data.slice(r.so) + r.en.data.slice(0, r.eo);
  },
};
class MouseEvent { constructor(type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); } }
const doc = {
  createTreeWalker(root, what) {
    let i = -1;
    return { currentNode: null, nextNode() { i += 1; this.currentNode = nodes[i] || null; return i < nodes.length; } };
  },
  createRange() { return { setStart(n, o) { this.sn = n; this.so = o; }, setEnd(n, o) { this.en = n; this.eo = o; } }; },
  getSelection() { return sel; },
  dispatchEvent(ev) { events.push("dispatch:" + ev.type + ":" + ev.bubbles); return true; },
  defaultView: { MouseEvent },
};
doc.body = { ownerDocument: doc };
globalThis.document = doc;
globalThis.NodeFilter = { SHOW_TEXT: 4 };
const t0 = Date.now();
globalThis.window = { parent: { Reader3AnnotationUI: { lastSelectionAt: t0 } } };
const wrapped = wrapForEvaluate(code);
const out = { verbatim: wrapped === code, events };
process.on("unhandledRejection", (e) => { out.unhandled = String((e && e.message) || e); });
Promise.resolve()
  .then(() => {
    const value = (0, eval)(wrapped);
    out.thenable = !!value && typeof value.then === "function";
    return value;
  })
  .then((v) => { out.result = v === undefined ? "<undefined>" : v; }, (e) => { out.error = String((e && e.message) || e); })
  .then(() => { out.elapsed_ms = Date.now() - t0; process.stdout.write(JSON.stringify(out)); });
"""


def _node(tmp_path: Path, js: str) -> Dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH; the static B2 check still covers the await token")
    (tmp_path / "harness.js").write_text(_HARNESS, encoding="utf-8")
    (tmp_path / "code.js").write_text(js, encoding="utf-8")
    res = subprocess.run([node, str(tmp_path / "harness.js"), str(tmp_path / "code.js")],
                         capture_output=True, text=True, timeout=30, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_b4_node_select_script_returns_its_result(tmp_path):  # WI-4b B4
    out = _node(tmp_path, cmd_reader.build_select_js("Alpha prose.", 0))
    assert out.get("error") is None, out
    assert out["verbatim"] is True
    assert out["thenable"] is True
    assert out["result"] == {"text": "Alpha prose.", "occurrences": 1}
    assert out["events"] == ["removeAllRanges", "addRange", "dispatch:mouseup:true"]
    assert out["elapsed_ms"] >= 150  # the debounce window (120 + 40 ms) was drained first


@pytest.mark.parametrize(
    "text,occ,needle",
    [("Zeta", 0, 'select_in_frame: text not found in chapter: "Zeta"'),
     ("Alpha prose.", 3, "select_in_frame: occurrence 3 requested")],
    ids=["missing-text", "bad-occurrence"],
)
def test_b5_node_select_script_failures_surface(tmp_path, text, occ, needle):  # WI-4b B5
    out = _node(tmp_path, cmd_reader.build_select_js(text, occ))
    assert out["verbatim"] is True
    assert needle in (out.get("error") or ""), out
    assert "addRange" not in out["events"]


# ---------------------------------------------------------------------------
# D: real `$B network` output
# ---------------------------------------------------------------------------


def test_d1_parse_real_network_capture():  # WI-4b D1
    assert "(?ms, 69B)" in NETWORK_REAL and "-244B" in NETWORK_REAL
    got = access_log.parse_browse_network(NETWORK_REAL, "http://127.0.0.1:62429")
    assert got == [
        {"method": "GET", "path": "/api/library/stats?scope=all", "status": 200},
        {"method": "GET", "path": "/api/collections", "status": 200},
        {"method": "GET", "path": "/api/index/smoke_data/status", "status": 200},
        {"method": "GET", "path": "/api/notes/smoke_data/0", "status": 200},
        {"method": "GET", "path": "/api/notes/smoke_data/0", "status": 200},
        {"method": "GET", "path": "/api/notes/smoke_data", "status": 200},
    ]

