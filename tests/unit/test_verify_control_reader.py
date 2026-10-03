"""WI-4: `reader state`, `reader select`, `ui inert` and their pure parts.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-4-5-6.md` (WI4-C01 - C48), its
addendum (C49 - C55, amended C24 and C32) and `tests-20261002-170349-round2.md` (amended
C49). Every case id is in the test name. Network-touching cases run the CLI and every fake
as bounded child processes; in-process cases are pure functions only. WI4-C47 lives in
WI-1's real-start test (`test_verify_control_instance.py::test_c66_...`).
"""

from __future__ import annotations

import importlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from verify_control_fakes_access import (
    access_side_log,
    async_log,
    decode_select_args,
    fake_access_server,
    fake_browse,
    read_argv_entries,
    read_argv_log,
    stop_server,
)
from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    REPO,
    TRY_PREFIX,
    base_env,
    make_state,
    real_evidence_untouched,
    reap_fakes,
    run_cli,
    wait_until,
)
from verify_control import cmd_reader

ALLOWED = {"js", "frame", "url", "attrs", "network", "wait", "click", "screenshot"}
IFRAME = '[data-testid="rd-viewport"] iframe'
SELECTOR = '[data-testid="rd-notes-review"]'
STALE = 'INFO:     127.0.0.1:50001 - "POST /api/notes/smoke_data/0 HTTP/1.1" 201 Created'
SEED = ["INFO:     Started server process [4242]", "INFO:     Application startup complete.", STALE]
ATTRS = {"data-testid": "rd-notes-review", "class": "rd-notes-review"}
POST_NOTE = {"method": "POST", "path": "/api/notes/smoke_data/0", "status": 201}
GET_NOTE = {"method": "GET", "path": "/api/notes/smoke_data/0", "status": 200}
SAMPLE = REPO / "tests" / "unit" / "fixtures" / "verify_control" / "browse_network_sample.txt"
PASSTHROUGH_TESTS = ("passthrough", "c43", "c50")


def _mod(name: str) -> Any:
    """Import `verify_control.<name>`; a missing module is a test failure, not a collection error."""
    mod = None
    try:
        mod = importlib.import_module("verify_control." + name)
    except ImportError:
        pass
    if mod is None:
        pytest.fail(f"verify_control.{name} does not exist yet")
    return mod


def _attr(obj: Any, name: str) -> Any:
    if not hasattr(obj, name):
        pytest.fail(f"{getattr(obj, '__name__', obj)} has no {name}")
    return getattr(obj, name)


def acc(method: str, path: str, status: int = 200, reason: str = "OK", port: int = 50002) -> str:
    return f'INFO:     127.0.0.1:{port} - "{method} {path} HTTP/1.1" {status} {reason}'


def marker(u: str, which: str) -> str:
    return acc("GET", f"/api/health?verify-marker={u}-{which}")


def _fail_shape(e: Dict[str, Any], code: str) -> None:
    assert e["ok"] is False, e
    assert e["error"]["code"] == code, e
    assert set(e["error"]) == {"code", "message", "try"}
    assert e["error"]["try"].startswith(TRY_PREFIX)
    assert ".claude/skills/verify-reader3/scripts/control.py" in e["error"]["try"]


# ---------------------------------------------------------------------------
# WI4-C48: no browse invocation in this module ever used `eval`
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _never_eval(tmp_path, request):  # WI4-C48
    yield
    log = tmp_path / "fakelog" / "browse.jsonl"
    if not log.exists():
        return
    entries = read_argv_log(log)
    assert all(not a or a[0] != "eval" for a in entries), entries
    passthrough = any(t in request.node.name for t in PASSTHROUGH_TESTS)
    for a in entries:
        assert a and (a[0] in ALLOWED or (passthrough and a[0] == "press")), a


@pytest.fixture
def servers():
    procs: List[Any] = []
    yield procs
    for p in procs:
        stop_server(p)


# ---------------------------------------------------------------------------
# access_log: parse_access_line, slice_between (WI4-C01 - C11)
# ---------------------------------------------------------------------------


def test_c01_parse_observed_uvicorn_line():  # WI4-C01
    al = _mod("access_log")
    r = al.parse_access_line('INFO:     127.0.0.1:57087 - "GET /api/notes/smoke_data/0 HTTP/1.1" 200 OK')
    assert dict(r) == {"method": "GET", "path": "/api/notes/smoke_data/0", "status": 200}
    assert type(r["status"]) is int


@pytest.mark.parametrize(
    "line,path",
    [
        (
            'INFO:     127.0.0.1:57090 - "GET /api/health?verify-marker=3f2a-begin HTTP/1.1" 200 OK',
            "/api/health?verify-marker=3f2a-begin",
        ),
        (
            'INFO:     127.0.0.1:57090 - "GET /api/search/smoke_data?q=caf%C3%A9&occurrence=2 HTTP/1.1" 200 OK',
            "/api/search/smoke_data?q=caf%C3%A9&occurrence=2",
        ),
    ],
)
def test_c02_query_string_kept_verbatim(line, path):  # WI4-C02
    assert _mod("access_log").parse_access_line(line)["path"] == path


NOISE = [
    "INFO:     Started server process [4242]",
    "INFO:     Application startup complete.",
    "WARNING:  Invalid HTTP request received.",
    "Traceback (most recent call last):",
    "",
    'INFO:     127.0.0.1:1 - "GET /api/x HTTP/1.1" 2OO OK',
    'INFO:     127.0.0.1:1 - "get /api/x HTTP/1.1" 200 OK',
]


@pytest.mark.parametrize("line", NOISE)
def test_c03_non_access_lines_are_not_requests(line):  # WI4-C03
    assert _mod("access_log").parse_access_line(line) is None


def test_c04_slice_between_markers():  # WI4-C04
    lines = [
        "INFO:     Started server process [1]",
        acc("POST", "/api/notes/smoke_data/0", 201, "Created"),
        marker("u1", "begin"),
        acc("GET", "/read/smoke_data/book.epub"),
        acc("GET", "/static/js/epub-renderer.js"),
        acc("GET", "/api/notes/smoke_data/0"),
        marker("zz", "begin"),
        acc("POST", "/api/notes/smoke_data/0", 201, "Created"),
        marker("u1", "end"),
        acc("PUT", "/api/notes/smoke_data/0/n1"),
    ]
    r = _mod("access_log").slice_between(lines, "u1")
    assert r["requests"] == [GET_NOTE, POST_NOTE]
    assert r["writes"] == [POST_NOTE]


def test_c05_api_segment_boundary():  # WI4-C05
    inner = [
        acc("GET", "/apiary/x"), acc("GET", "/api-docs"), acc("GET", "/api"), acc("GET", "/api/"),
        acc("GET", "/api/health"), acc("POST", "/api?x=1", 201, "Created"), acc("GET", "/API/notes"),
    ]
    r = _mod("access_log").slice_between([marker("u1", "begin"), *inner, marker("u1", "end")], "u1")
    assert [x["path"] for x in r["requests"]] == ["/api", "/api/", "/api/health", "/api?x=1"]
    assert r["writes"] == [{"method": "POST", "path": "/api?x=1", "status": 201}]


@pytest.mark.parametrize(
    "lines,which",
    [
        ([marker("u1", "begin"), acc("POST", "/api/x", 201, "Created")], "end"),  # (a) begin only
        ([acc("POST", "/api/x", 201, "Created"), marker("u1", "end")], "begin"),  # (b) end only
        ([marker("u1", "end"), acc("POST", "/api/x", 201, "Created"), marker("u1", "begin")], None),  # (c)
        ([marker("zz", "begin"), acc("POST", "/api/x", 201, "Created"), marker("zz", "end")], None),  # (d)
    ],
    ids=["a-begin-only", "b-end-only", "c-misordered", "d-neither"],
)
def test_c06_missing_or_misordered_marker(lines, which):  # WI4-C06
    al = _mod("access_log")
    with pytest.raises(al.AccessLogError) as ei:
        al.slice_between(lines, "u1")
    assert ei.value.code == "marker_missing"
    assert "u1" in str(ei.value)
    if which:
        assert which in str(ei.value)
    else:
        assert "begin" in str(ei.value) or "end" in str(ei.value)


@pytest.mark.parametrize(
    "lines",
    [
        [marker("u1", "begin"), marker("u1", "begin"), marker("u1", "end")],
        [marker("u1", "begin"), marker("u1", "end"), marker("u1", "end")],
    ],
    ids=["a-two-begins", "b-two-ends"],
)
def test_c07_duplicate_uuid_rejected(lines):  # WI4-C07
    al = _mod("access_log")
    with pytest.raises(al.AccessLogError) as ei:
        al.slice_between(lines, "u1")
    assert ei.value.code == "marker_duplicate"


def test_c08_adjacent_markers_empty_slice():  # WI4-C08
    w = acc("POST", "/api/notes/smoke_data/0", 201, "Created")
    r = _mod("access_log").slice_between([w, marker("u1", "begin"), marker("u1", "end"), w], "u1")
    assert r["requests"] == [] and r["writes"] == []


def test_c09_write_is_literally_non_get():  # WI4-C09
    inner = [
        acc("HEAD", "/api/health"), acc("OPTIONS", "/api/notes/smoke_data/0"), acc("PATCH", "/api/x"),
        acc("DELETE", "/api/notes/smoke_data/0/n1"), acc("GET", "/api/library"),
    ]
    r = _mod("access_log").slice_between([marker("u1", "begin"), *inner, marker("u1", "end")], "u1")
    assert [x["method"] for x in r["requests"]] == ["HEAD", "OPTIONS", "PATCH", "DELETE", "GET"]
    assert [x["method"] for x in r["writes"]] == ["HEAD", "OPTIONS", "PATCH", "DELETE"]


METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
PATHS = [
    "/api/notes/smoke_data/0", "/api/library", "/static/a.css", "/read/smoke_data/book.epub",
    "/api/health?verify-marker=zz-begin", "/api/health", "/apiary",
]
STATUSES = [200, 201, 204, 404, 409, 500]
_item = st.one_of(
    st.sampled_from(NOISE).map(lambda n: ("noise", n)),
    st.tuples(st.sampled_from(METHODS), st.sampled_from(PATHS), st.sampled_from(STATUSES)).map(
        lambda t: ("access", *t)
    ),
)


def _render(item) -> str:
    if item[0] == "noise":
        return item[1]
    return acc(item[1], item[2], item[3], "X")


def _expected(item) -> bool:
    if item[0] != "access":
        return False
    p = item[2]
    head = p.split("?", 1)[0]
    return (head == "/api" or head.startswith("/api/")) and "verify-marker=" not in p


@st.composite
def _log(draw):
    items = draw(st.lists(_item, max_size=40))
    i = draw(st.integers(0, len(items)))
    j = draw(st.integers(i, len(items)))
    lines = (
        [_render(x) for x in items[:i]] + [marker("u1", "begin")] + [_render(x) for x in items[i:j]]
        + [marker("u1", "end")] + [_render(x) for x in items[j:]]
    )
    oracle = [{"method": x[1], "path": x[2], "status": x[3]} for x in items[i:j] if _expected(x)]
    return lines, oracle


def _is_subsequence(sub, seq) -> bool:
    k = 0
    for x in seq:
        if k < len(sub) and sub[k] == x:
            k += 1
    return k == len(sub)


@settings(deadline=None, max_examples=200)
@given(_log())
def test_c10_slicer_property(gen):  # WI4-C10
    lines, oracle = gen
    r = _mod("access_log").slice_between(lines, "u1")
    assert r["requests"] == oracle
    assert r["writes"] == [x for x in oracle if x["method"] != "GET"]
    assert _is_subsequence(r["writes"], r["requests"])
    for x in r["requests"] + r["writes"]:
        assert "verify-marker=" not in x["path"]
        assert x["path"] == "/api" or x["path"].startswith(("/api/", "/api?"))


@settings(deadline=None, max_examples=200)
@given(_log(), st.lists(_item, max_size=15), st.lists(_item, max_size=15))
def test_c11_slice_stable_under_growth(gen, prefix, suffix):  # WI4-C11
    lines, _ = gen
    al = _mod("access_log")
    base = al.slice_between(lines, "u1")
    assert al.slice_between([_render(x) for x in prefix] + lines, "u1") == base
    assert al.slice_between(lines + [_render(x) for x in suffix], "u1") == base


# ---------------------------------------------------------------------------
# browse.py (WI4-C12 - C17)
# ---------------------------------------------------------------------------


def test_c12_eval_refused_before_spawning(tmp_path, monkeypatch):  # WI4-C12
    fb = fake_browse(tmp_path, {"eval": [{"stdout": "x"}]})
    monkeypatch.setenv("VERIFY_READER3_BROWSE", str(fb.path))
    br = _mod("browse")
    with pytest.raises(_attr(br, "BrowseRefused")) as ei:
        br.run(["eval", "/tmp/x.js"])
    assert ei.value.code == "refused_browse_command"
    assert not fb.argv_log.exists()


@settings(deadline=None, max_examples=200)
@given(st.text(max_size=12) | st.sampled_from(sorted(ALLOWED) + ["eval", "EVAL", "eval ", "goto", "cdp", "js\n"]))
def test_c13_allowlist_property(s):  # WI4-C13
    br = _mod("browse")
    oracle = {"js", "frame", "url", "attrs", "network", "wait", "click", "screenshot"}
    if s in oracle:
        br.check_subcommand(s)
    else:
        with pytest.raises(br.BrowseRefused):
            br.check_subcommand(s)


@pytest.mark.parametrize("variant", ["a-absent", "b-not-executable"])
def test_c14_missing_binary_gives_browse_missing(tmp_path, variant):  # WI4-C14
    x = tmp_path / "nope"
    if variant == "b-not-executable":
        x.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        os.chmod(x, 0o644)
    code, e, _ = run_cli(["reader", "state"], base_env(tmp_path) | {"VERIFY_READER3_BROWSE": str(x)})
    assert code == 1
    _fail_shape(e, "browse_missing")
    assert "VERIFY_READER3_BROWSE" in e["error"]["message"]
    assert str(x) in e["error"]["message"]
    assert e["error"]["try"] == TRY_PREFIX + "doctor"


def test_c15_nonzero_exit_gives_browse_failed_with_stderr(tmp_path):  # WI4-C15
    fb = fake_browse(tmp_path, {"js": [{"exit": 1, "stderr": "boom-stderr-7f3"}]})
    code, e, _ = run_cli(["reader", "state"], base_env(tmp_path))
    assert code == 1
    _fail_shape(e, "browse_failed")
    assert "boom-stderr-7f3" in e["error"]["message"]
    assert len(read_argv_log(fb.argv_log)) == 1


def test_c16_browse_timeout_kills_child(tmp_path):  # WI4-C16
    fake_browse(tmp_path, {"js": [{"sleep_s": 20}]})
    t0 = time.monotonic()
    code, e, _ = run_cli(["reader", "state"], base_env(tmp_path) | {"VERIFY_READER3_BROWSE_TIMEOUT_S": "1"})
    assert time.monotonic() - t0 < 10
    assert code == 1
    _fail_shape(e, "browse_failed")
    assert "timed out" in e["error"]["message"].lower()
    pids = [int(x) for x in (tmp_path / "fakelog" / "browse.pids").read_text().split()]
    assert pids
    for pid in pids:
        assert wait_until(lambda pid=pid: not _alive(pid), timeout=2), pid


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_c17_default_binary_path(tmp_path):  # WI4-C17
    br = _mod("browse")
    assert br.locate({"HOME": str(tmp_path)}) == tmp_path / ".claude/skills/gstack/browse/dist/browse"
    assert br.locate({"HOME": str(tmp_path), "VERIFY_READER3_BROWSE": "/x/y"}) == Path("/x/y")


# ---------------------------------------------------------------------------
# reader state (WI4-C18 - C23, C55)
# ---------------------------------------------------------------------------


def S(ready: bool, idx: int, v: Any = 1) -> Dict[str, Any]:
    return {
        "v": v,
        "ready": ready,
        "cfi": None,
        "section": {"index": idx, "href": None, "requestedIndex": 0, "spineCount": 2},
        "progress": {"sectionPage": None, "sectionPercent": None, "spinePercent": None, "bookPercent": None},
        "annotations": None,
        "diag": [],
        "diagAvailable": False,
        "errors": [],
    }


def _js(*states: Any) -> Dict[str, List[Dict[str, Any]]]:
    return {"js": [{"stdout": s if isinstance(s, str) else json.dumps(s)} for s in states]}


def _assert_state_argv(argv: List[str]) -> None:
    assert argv[0] == "js" and len(argv) == 2
    assert "getDebugState" in argv[1] and "JSON.stringify" in argv[1]


def test_c18_polls_until_ready_returns_third_state(tmp_path):  # WI4-C18
    fb = fake_browse(tmp_path, _js(S(False, 0), S(False, 1), S(True, 2)))
    code, e, _ = run_cli(["reader", "state", "--wait", "10"], base_env(tmp_path))
    assert code == 0, e
    assert e["data"] == S(True, 2)
    argv = read_argv_log(fb.argv_log)
    assert len(argv) == 3
    for a in argv:
        _assert_state_argv(a)


def test_c19_without_wait_single_read(tmp_path):  # WI4-C19
    fb = fake_browse(tmp_path, _js(S(False, 0)))
    code, e, _ = run_cli(["reader", "state"], base_env(tmp_path))
    assert code == 0, e
    assert e["data"] == S(False, 0)
    assert len(read_argv_log(fb.argv_log)) == 1


@pytest.mark.parametrize(
    "stdout", [json.dumps(S(True, 0, v=2)), "not json", '{"ready": true}', "[1,2]"], ids=["a-v2", "b-text", "c-no-v", "d-list"]
)
def test_c20_invalid_debug_state(tmp_path, stdout):  # WI4-C20
    fb = fake_browse(tmp_path, _js(stdout))
    code, e, _ = run_cli(["reader", "state", "--wait", "2"], base_env(tmp_path))
    assert code == 1
    _fail_shape(e, "bad_debug_state")
    if stdout.startswith('{"v": 2'):
        assert "v" in e["error"]["message"]
        assert len(read_argv_log(fb.argv_log)) == 1


def test_c21_wait_timeout_reader_not_ready(tmp_path):  # WI4-C21
    fb = fake_browse(tmp_path, _js(S(False, 5)))
    r = run_cli(["reader", "state", "--wait", "1"], base_env(tmp_path))
    code, e, _ = r
    assert code == 1
    _fail_shape(e, "reader_not_ready")
    assert e["data"]["last_state"] == S(False, 5)
    assert 1.0 <= r.elapsed_s < 8.0
    assert len(read_argv_log(fb.argv_log)) >= 2


@pytest.mark.parametrize(
    "resp",
    [
        {"stdout": "null", "exit": 0},
        {"exit": 1, "stderr": "TypeError: Cannot read properties of undefined (reading 'getDebugState')"},
    ],
    ids=["a-null", "b-typeerror"],
)
def test_c22_not_reader_page(tmp_path, resp):  # WI4-C22
    fake_browse(tmp_path, {"js": [resp]})
    code, e, _ = run_cli(["reader", "state"], base_env(tmp_path))
    assert code == 1
    _fail_shape(e, "not_reader_page")
    assert "$B url" in e["error"]["message"]
    assert e["error"]["try"] == TRY_PREFIX + "reader state --wait 15"


@pytest.mark.parametrize("value", ["-1", "soon"])
def test_c23_bad_wait_is_usage(tmp_path, value):  # WI4-C23
    fb = fake_browse(tmp_path, _js(S(True, 0)))
    code, e, _ = run_cli(["reader", "state", "--wait", value], base_env(tmp_path))
    assert code == 2
    _fail_shape(e, "usage")
    assert not fb.argv_log.exists()


def test_c55_null_state_under_wait_fails_fast(tmp_path):  # WI4-C55
    fb = fake_browse(tmp_path, {"js": [{"stdout": "null", "exit": 0}]})
    r = run_cli(["reader", "state", "--wait", "2"], base_env(tmp_path))
    code, e, _ = r
    assert code == 1
    _fail_shape(e, "not_reader_page")
    assert e["error"]["try"] == TRY_PREFIX + "reader state --wait 15"
    assert r.elapsed_s < 1.5
    argv = read_argv_log(fb.argv_log)
    assert len(argv) == 1
    _assert_state_argv(argv[0])


# ---------------------------------------------------------------------------
# build_select_js, reader select (WI4-C24 - C31, C51, C52)
# ---------------------------------------------------------------------------

SELECT_OK = {"stdout": json.dumps({"text": "Alpha prose.", "occurrences": 1})}


def select_rules(*, frame_iframe=None, frame_main=None, select=None, toolbar=None):
    return [
        {"sub": "frame", "contains": "rd-viewport", "responses": [frame_iframe or {}]},
        {"sub": "frame", "contains": "main", "responses": [frame_main or {}]},
        {"sub": "js", "contains": "mouseup", "responses": [select or SELECT_OK]},
        {"sub": "js", "contains": "rd-anno-toolbar", "responses": [toolbar or {"stdout": "true"}]},
    ]


def _is_select(a: List[str]) -> bool:
    return a[0] == "js" and "mouseup" in a[1]


def _is_toolbar(a: List[str]) -> bool:
    return a[0] == "js" and "rd-anno-toolbar" in a[1]


@settings(deadline=None, max_examples=200)
@given(st.text(min_size=1, max_size=60), st.integers(-5, 5))
@example('He said "hi"', 0)
@example("it’s", 1)
@example("a\\b", 0)
@example("</script>", 0)
@example("x\ny", 0)
@example("\u0000", 0)
@example("${x}`", 0)
@example(")([", 0)
@example("])", 0)
@example(" ", 0)
def test_c24_needle_round_trip(text, occurrence):  # WI4-C24 (amended)
    build = _attr(cmd_reader, "build_select_js")
    js = build(text, occurrence)
    prefix = "(" + _attr(cmd_reader, "SELECT_FN") + ")("
    assert decode_select_args(js) == [text, occurrence, 120, 40, 8000]
    assert js[len(prefix):-1].isascii()


def test_c25_select_js_timing_contract():  # WI4-C25
    js = _attr(cmd_reader, "build_select_js")("Alpha prose.", 0)
    for token in ("createTreeWalker", "removeAllRanges", "addRange", 'MouseEvent("mouseup"'):
        assert token in js
    assert "new " in js
    assert js.index("removeAllRanges") < js.index("addRange") < js.index("mouseup")
    assert "await" not in js[js.index("addRange("): js.index("mouseup")]


def test_c26_select_success_argv_order(tmp_path):  # WI4-C26
    fb = fake_browse(tmp_path, select_rules())
    code, e, _ = run_cli(["reader", "select", "Alpha prose.", "--occurrence", "0"], base_env(tmp_path))
    assert code == 0, e
    assert e["data"] == {"selected": "Alpha prose.", "toolbar_visible": True}
    argv = read_argv_log(fb.argv_log)
    assert argv[:3] == [["frame", IFRAME], ["js", cmd_reader.build_select_js("Alpha prose.", 0)], ["frame", "main"]]
    assert len(argv) >= 4
    for a in argv[3:]:
        assert _is_toolbar(a) and not _is_select(a), a


def test_c27_select_js_fails_frame_main_last(tmp_path):  # WI4-C27
    bad = {"exit": 1, "stderr": 'Error: select_in_frame: 章内找不到 "Zeta"'}
    fb = fake_browse(tmp_path, select_rules(select=bad))
    code, e, _ = run_cli(["reader", "select", "Zeta"], base_env(tmp_path))
    assert code == 1
    _fail_shape(e, "select_failed")
    assert "章内找不到" in e["error"]["message"]
    argv = read_argv_log(fb.argv_log)
    assert argv == [["frame", IFRAME], ["js", cmd_reader.build_select_js("Zeta", 0)], ["frame", "main"]]


@pytest.mark.parametrize("point", ["i-frame", "ii-select-exit", "iii-select-timeout", "iv-toolbar-exit"])
def test_c28_restore_invariant_every_failure_point(tmp_path, point):  # WI4-C28
    kw: Dict[str, Any] = {}
    env = base_env(tmp_path) | {"VERIFY_READER3_TOOLBAR_WAIT_S": "1"}
    if point == "i-frame":
        kw["frame_iframe"] = {"exit": 1, "stderr": "Frame not found"}
    elif point == "ii-select-exit":
        kw["select"] = {"exit": 1, "stderr": "Error: boom"}
    elif point == "iii-select-timeout":
        kw["select"] = {"sleep_s": 20}
        env["VERIFY_READER3_BROWSE_TIMEOUT_S"] = "1"
    else:
        kw["toolbar"] = {"exit": 1, "stderr": "toolbar-broke"}
    fb = fake_browse(tmp_path, select_rules(**kw))
    code, e, _ = run_cli(["reader", "select", "Alpha prose."], env)
    argv = read_argv_log(fb.argv_log)
    last_iframe = max(i for i, a in enumerate(argv) if a == ["frame", IFRAME])
    mains = [i for i, a in enumerate(argv) if a == ["frame", "main"]]
    assert mains and max(mains) > last_iframe, argv
    if point == "iv-toolbar-exit":
        assert code == 0, e
        assert e["data"]["toolbar_visible"] is False
    else:
        assert code == 1, e
        assert e["ok"] is False
        assert argv[-1] == ["frame", "main"], argv
    if point == "iii-select-timeout":
        sel_pids = [x["pid"] for x in read_argv_entries(fb.argv_log) if _is_select(x["argv"])]
        assert sel_pids
        for pid in sel_pids:
            assert wait_until(lambda pid=pid: not _alive(pid), timeout=2), pid


def test_c29_toolbar_never_visible_reported(tmp_path):  # WI4-C29
    fb = fake_browse(tmp_path, select_rules(toolbar={"stdout": "false"}))
    r = run_cli(["reader", "select", "Alpha prose."], base_env(tmp_path) | {"VERIFY_READER3_TOOLBAR_WAIT_S": "1"})
    code, e, _ = r
    assert code == 0, e
    assert e["data"] == {"selected": "Alpha prose.", "toolbar_visible": False}
    assert r.elapsed_s < 8
    argv = read_argv_log(fb.argv_log)
    main_at = argv.index(["frame", "main"])
    tb = [i for i, a in enumerate(argv) if _is_toolbar(a)]
    assert len(tb) >= 2 and all(i > main_at for i in tb)


def test_c30_frame_main_failure(tmp_path):  # WI4-C30
    fb = fake_browse(tmp_path, select_rules(frame_main={"exit": 1, "stderr": "frame-main-broke"}))
    code, e, _ = run_cli(["reader", "select", "Alpha prose."], base_env(tmp_path))
    assert code == 1
    _fail_shape(e, "browse_failed")
    assert "frame main" in e["error"]["message"]
    assert not any(_is_toolbar(a) for a in read_argv_log(fb.argv_log))


def test_c31_awkward_needle_reaches_browse_intact(tmp_path):  # WI4-C31
    needle = 'it’s "x"\nz'
    fb = fake_browse(tmp_path, select_rules())
    code, e, _ = run_cli(["reader", "select", needle], base_env(tmp_path))
    assert code == 0, e
    sel = [a for a in read_argv_log(fb.argv_log) if _is_select(a)]
    assert len(sel) == 1 and len(sel[0]) == 2
    assert decode_select_args(sel[0][1]) == [needle, 0, 120, 40, 8000]


@pytest.mark.parametrize("variant", ["a-wired", "b-negative", "c-not-int"])
def test_c51_occurrence_wired_selected_from_page(tmp_path, variant):  # WI4-C51
    page = {"stdout": json.dumps({"text": "Alpha (page)", "occurrences": 3})}
    fb = fake_browse(tmp_path, select_rules(select=page))
    occ = {"a-wired": "2", "b-negative": "-1", "c-not-int": "two"}[variant]
    code, e, _ = run_cli(["reader", "select", "Alpha", "--occurrence", occ], base_env(tmp_path))
    if variant == "a-wired":
        assert code == 0, e
        assert e["data"] == {"selected": "Alpha (page)", "toolbar_visible": True}
        sel = [a for a in read_argv_log(fb.argv_log) if _is_select(a)]
        assert len(sel) == 1 and len(sel[0]) == 2
        assert decode_select_args(sel[0][1]) == ["Alpha", 2, 120, 40, 8000]
    else:
        assert code == 2
        _fail_shape(e, "usage")
        assert not fb.argv_log.exists()


def _suffix(t: str, n: int) -> str:
    return json.dumps([t, n, 120, 40, 8000], ensure_ascii=True) + ")"


@settings(deadline=None, max_examples=200)
@given(st.text(max_size=80), st.text(max_size=80), st.integers(0, 50), st.integers(0, 50))
@example('"', "Alpha", 0, 0)
@example("\\", "Alpha", 0, 0)
@example("x\ny", "Alpha", 0, 0)
@example("</script>", "Alpha", 0, 0)
@example(" ", "Alpha", 0, 0)
@example(" ", "Alpha", 0, 0)
@example("${a}`", "Alpha", 0, 0)
@example("*/", "Alpha", 0, 0)
@example("'); alert(1); ('", "Alpha", 0, 0)
def test_c52_needle_never_enters_function_body(a, b, k, j):  # WI4-C52
    build = _attr(cmd_reader, "build_select_js")
    fn = _attr(cmd_reader, "SELECT_FN")
    js_a, js_b = build(a, k), build(b, j)
    assert js_a.endswith(_suffix(a, k)) and js_b.endswith(_suffix(b, j))
    assert js_a[: -len(_suffix(a, k))] == js_b[: -len(_suffix(b, j))] == "(" + fn + ")("
    assert _suffix(a, k).isascii()
    if a == " ":
        assert "\\u2028" in js_a and " " not in js_a


# ---------------------------------------------------------------------------
# ui inert (WI4-C32 - C46, C49, C50, C53, C54)
# ---------------------------------------------------------------------------


class Inert(NamedTuple):
    env: Dict[str, str]
    port: int
    base: str
    log: Path
    argv_log: Path


def inert_env(tmp_path, servers, *, click=None, url=None, attrs=None, extra=(), drop=None) -> Inert:
    log = tmp_path / "srvlog" / "server.log"
    port, proc = fake_access_server(tmp_path, log, seed_lines=SEED, drop_log_regex=drop)
    servers.append(proc)
    base = f"http://127.0.0.1:{port}"
    sp = make_state(tmp_path, base_url=base, port=port, log=log, pid=proc.pid)
    rules = list(extra) + [
        {"sub": "url", "contains": None, "responses": url or [{"stdout": base + "/read/smoke_data/0"}]},
        {"sub": "attrs", "contains": None, "responses": attrs or [{"stdout": json.dumps(ATTRS)}]},
        {"sub": "click", "contains": None, "responses": click or [{}]},
    ]
    fb = fake_browse(tmp_path, rules)
    env = base_env(tmp_path) | {"VERIFY_READER3_STATE": str(sp), "FAKE_BROWSE_BASE_URL": base}
    return Inert(env, port, base, log, fb.argv_log)


def http(*pairs) -> Dict[str, Any]:
    return {"http": [{"method": m, "path": p} for m, p in pairs]}


INERT_ARGV = ["ui", "inert", "--testid", "rd-notes-review", "--settle", "0.2"]
MARK_RE = re.compile(r"verify-marker=([^\s&]+)-(begin|end)")


def _marks(log: Path):
    return MARK_RE.findall(log.read_text(encoding="utf-8"))


def _subs(argv_log: Path) -> List[str]:
    return [a[0] for a in read_argv_log(argv_log)]


def test_c32_nothing_happened_inert(tmp_path, servers):  # WI4-C32 (amended)
    ie = inert_env(tmp_path, servers)
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    url = ie.base + "/read/smoke_data/0"
    assert e["data"] == {
        "testid": "rd-notes-review", "requests": [], "writes": [],
        "url_before": url, "url_after": url, "url_changed": False,
        "attrs_before": ATTRS, "attrs_after": ATTRS, "inert": True, "mechanism": "access_log",
    }
    marks = _marks(ie.log)
    assert len(marks) == 2 and marks[0][0] == marks[1][0]
    assert [m[1] for m in marks] == ["begin", "end"]
    assert STALE in ie.log.read_text(encoding="utf-8")
    assert _subs(ie.argv_log) == ["url", "attrs", "click", "url", "attrs"]
    argv = read_argv_log(ie.argv_log)
    assert argv[2] == ["click", SELECTOR]
    assert argv[1] == ["attrs", SELECTOR] and argv[4] == ["attrs", SELECTOR]


def test_c33_get_only_not_inert_no_writes(tmp_path, servers):  # WI4-C33
    ie = inert_env(tmp_path, servers, click=[http(("GET", "/api/notes/smoke_data/0"))])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["requests"] == [GET_NOTE] and d["writes"] == []
    assert d["url_changed"] is False and d["inert"] is False
    lines = ie.log.read_text(encoding="utf-8").splitlines()
    b = next(i for i, ln in enumerate(lines) if "-begin" in ln)
    en = next(i for i, ln in enumerate(lines) if "-end" in ln)
    assert any('"GET /api/notes/smoke_data/0 ' in ln for ln in lines[b + 1:en])


def test_c34_a_write_happened(tmp_path, servers):  # WI4-C34
    ie = inert_env(tmp_path, servers, click=[http(("GET", "/api/notes/smoke_data/0"), ("POST", "/api/notes/smoke_data/0"))])
    code, e, _ = run_cli(INERT_ARGV + ["--expect", "active"], ie.env)
    assert code == 0, e
    assert e["data"]["requests"] == [GET_NOTE, POST_NOTE]
    assert e["data"]["writes"] == [POST_NOTE]
    assert e["data"]["inert"] is False


def test_c35_url_changed_no_request(tmp_path, servers):  # WI4-C35
    ie = inert_env(tmp_path, servers, url=[{"stdout": "PLACEHOLDER"}])
    base = ie.base
    fake_browse(tmp_path, [
        {"sub": "url", "contains": None, "responses": [{"stdout": base + "/read/smoke_data/0"}, {"stdout": base + "/read/smoke_data/1"}]},
        {"sub": "attrs", "contains": None, "responses": [{"stdout": json.dumps(ATTRS)}]},
        {"sub": "click", "contains": None, "responses": [{}]},
    ])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["requests"] == []
    assert d["url_before"].endswith("/0") and d["url_after"].endswith("/1")
    assert d["url_changed"] is True and d["inert"] is False


def test_c36_attrs_changed_no_request(tmp_path, servers):  # WI4-C36
    a0 = {"class": "rd-rail-btn", "aria-pressed": "false"}
    a1 = {"class": "rd-rail-btn is-active", "aria-pressed": "true"}
    ie = inert_env(tmp_path, servers, attrs=[{"stdout": json.dumps(a0)}, {"stdout": json.dumps(a1)}])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["requests"] == [] and d["url_changed"] is False
    assert d["attrs_before"] == a0 and d["attrs_after"] == a1
    assert d["inert"] is False


def test_c37_attr_key_order_is_not_a_change(tmp_path, servers):  # WI4-C37
    ie = inert_env(tmp_path, servers, attrs=[{"stdout": '{"a":"1","b":"2"}'}, {"stdout": '{"b":"2","a":"1"}'}])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    assert e["data"]["inert"] is True


def test_c38_assets_and_markers_never_in_requests(tmp_path, servers):  # WI4-C38
    assets = ["/static/css/reader.css", "/read/smoke_data/book.epub", "/read/smoke_data/images/a.png", "/favicon.ico"]
    ie = inert_env(tmp_path, servers, click=[http(*[("GET", p) for p in assets])])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    assert e["data"]["requests"] == [] and e["data"]["inert"] is True
    for r in e["data"]["requests"] + e["data"]["writes"]:
        assert "verify-marker" not in r["path"]
    lines = ie.log.read_text(encoding="utf-8").splitlines()
    b = next(i for i, ln in enumerate(lines) if "-begin" in ln)
    en = next(i for i, ln in enumerate(lines) if "-end" in ln)
    between = lines[b + 1:en]
    for p in assets:
        assert any(f'"GET {p} ' in ln for ln in between), p
    assert len(_marks(ie.log)) == 2


@pytest.mark.parametrize("variant", ["i-inert-expect-active", "ii-write-expect-inert"])
def test_c39_expect_mismatch(tmp_path, servers, variant):  # WI4-C39
    if variant.startswith("i-"):
        ie = inert_env(tmp_path, servers)
        expect = "active"
    else:
        ie = inert_env(tmp_path, servers, click=[http(("GET", "/api/notes/smoke_data/0"), ("POST", "/api/notes/smoke_data/0"))])
        expect = "inert"
    code, e, _ = run_cli(INERT_ARGV + ["--expect", expect], ie.env)
    assert code == 1
    _fail_shape(e, "unexpected_inertness")
    if variant.startswith("i-"):
        assert e["data"]["inert"] is True and e["data"]["requests"] == []
    else:
        assert e["data"]["writes"][0] == POST_NOTE


@pytest.mark.parametrize("has_request", [False, True])
@pytest.mark.parametrize("url_same", [False, True])
@pytest.mark.parametrize("attrs_same", [False, True])
def test_c40_compute_inert_truth_table(has_request, url_same, attrs_same):  # WI4-C40
    fn = _attr(cmd_reader, "compute_inert")
    reqs = [{"method": "GET", "path": "/api/x", "status": 200}] if has_request else []
    got = fn(reqs, "/read/a/0", "/read/a/0" if url_same else "/read/a/1", {"c": "x"}, {"c": "x"} if attrs_same else {"c": "y"})
    assert got is ((not has_request) and url_same and attrs_same)


def test_c41_element_not_found_no_markers_no_click(tmp_path, servers):  # WI4-C41
    ie = inert_env(tmp_path, servers, attrs=[{"exit": 1, "stderr": "no element matches selector"}])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 1
    _fail_shape(e, "browse_failed")
    assert "rd-notes-review" in e["error"]["message"]
    assert "verify-marker" not in ie.log.read_text(encoding="utf-8")
    assert "click" not in _subs(ie.argv_log)


def test_c42_end_marker_never_logged(tmp_path, servers):  # WI4-C42
    ie = inert_env(tmp_path, servers, drop=r"verify-marker=.*-end")
    r = run_cli(INERT_ARGV, ie.env | {"VERIFY_READER3_MARKER_WAIT_S": "1"})
    code, e, _ = r
    assert code == 1
    _fail_shape(e, "marker_missing")
    assert r.elapsed_s < 8
    assert [m[1] for m in _marks(ie.log)] == ["begin"]


def test_c43_passthrough_form(tmp_path, servers):  # WI4-C43
    press = {"sub": "press", "contains": None, "responses": [http(("GET", "/api/notes/smoke_data/0"))]}
    ie = inert_env(tmp_path, servers, extra=[press])
    code, e, _ = run_cli(["ui", "inert", "--settle", "0.2", "--", "press", "ArrowRight"], ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["testid"] is None and d["attrs_before"] is None and d["attrs_after"] is None
    assert d["requests"] == [GET_NOTE] and d["inert"] is False
    argv = read_argv_log(ie.argv_log)
    assert argv.count(["press", "ArrowRight"]) == 1
    urls = [i for i, a in enumerate(argv) if a[0] == "url"]
    k = argv.index(["press", "ArrowRight"])
    assert len(urls) == 2 and urls[0] < k < urls[1]
    assert "attrs" not in [a[0] for a in argv]


def test_c44_passthrough_eval_refused(tmp_path, servers):  # WI4-C44
    ie = inert_env(tmp_path, servers)
    code, e, _ = run_cli(["ui", "inert", "--", "eval", "/tmp/x.js"], ie.env)
    assert code == 3
    _fail_shape(e, "refused_browse_command")
    assert all(a[0] != "eval" for a in read_argv_log(ie.argv_log))
    assert _marks(ie.log) == []


@pytest.mark.parametrize("testid", ['x"],body[a', ""], ids=["selector-breaker", "empty"])
def test_c45_testid_validation(tmp_path, testid):  # WI4-C45
    fb = fake_browse(tmp_path, {})
    code, e, _ = run_cli(["ui", "inert", "--testid", testid], base_env(tmp_path))
    assert code == 2
    _fail_shape(e, "usage")
    assert not fb.argv_log.exists()


def test_c46_fallback_parses_network_capture():  # WI4-C46
    al = _mod("access_log")
    text = SAMPLE.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" in text
    got = al.parse_browse_network(text, base_url="http://127.0.0.1:59881")
    assert got == [
        {"method": "GET", "path": "/api/notes/smoke_data/0", "status": 200},
        {"method": "POST", "path": "/api/notes/smoke_data/0", "status": 201},
        {"method": "GET", "path": "/api/library?sort=title", "status": None},
    ]
    assert all("googleapis" not in r["path"] for r in got)


def _line_index(lines: List[str], needle: str) -> int:
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, (needle, lines)
    return hits[0]


@pytest.mark.parametrize(
    "settle,delay,captured",
    [("2.0", 1.5, True), ("0.2", 1.5, False), ("1.0", 0.4, True)],
    ids=["a-settle-above-default", "b-settle-below-delay", "c-original"],
)
def test_c49_settle_window_captures_delayed_write(tmp_path, servers, settle, delay, captured):  # WI4-C49 (round 2)
    click = [{"stdout": "", "exit": 0, "http_async": [{"method": "POST", "path": "/api/notes/smoke_data/0", "delay_s": delay}]}]
    ie = inert_env(tmp_path, servers, click=click)
    r = run_cli(["ui", "inert", "--testid", "rd-notes-review", "--settle", settle], ie.env)
    code, e, _ = r
    assert code == 0 and e["ok"] is True, e
    assert r.elapsed_s >= float(settle)
    assert wait_until(lambda: len(async_log(tmp_path)) == 1, timeout=5)
    sent = async_log(tmp_path)
    assert sent[0]["method"] == "POST" and sent[0]["status"] == 201
    side = access_side_log(tmp_path)
    lines = [x["line"] for x in side]
    begins = [m for m in MARK_RE.findall("\n".join(lines)) if m[1] == "begin"]
    assert len(begins) == 1, lines
    u = begins[0][0]
    b = _line_index(lines, f"verify-marker={u}-begin")
    en = _line_index(lines, f"verify-marker={u}-end")
    post = _line_index(lines, '"POST /api/notes/smoke_data/0 ')
    if captured:
        assert e["data"]["writes"] == [POST_NOTE]
        assert e["data"]["requests"] == e["data"]["writes"]
        assert e["data"]["inert"] is False
        assert b < post < en
    else:
        assert e["data"]["writes"] == []
        assert sent[0]["sent_at"] > side[en]["t"]
        assert post > en


@pytest.mark.parametrize("variant", ["a-wrapper", "b-passthrough", "c-wrapper-expect-inert"])
def test_c50_action_failure_is_not_inertness(tmp_path, servers, variant):  # WI4-C50
    if variant == "b-passthrough":
        press = {"sub": "press", "contains": None, "responses": [{"exit": 1, "stderr": "press-broke-91c"}]}
        ie = inert_env(tmp_path, servers, extra=[press])
        argv = ["ui", "inert", "--settle", "0.2", "--", "press", "ArrowRight"]
        action = ["press", "ArrowRight"]
    else:
        ie = inert_env(tmp_path, servers, click=[{"exit": 1, "stderr": "element not clickable"}])
        argv = INERT_ARGV + (["--expect", "inert"] if variant.startswith("c-") else [])
        action = ["click", SELECTOR]
    code, e, _ = run_cli(argv, ie.env)
    assert code == 1
    _fail_shape(e, "browse_failed")
    assert e["data"] is None
    if variant == "b-passthrough":
        assert "press-broke-91c" in e["error"]["message"]
    else:
        assert "rd-notes-review" in e["error"]["message"]
        assert "element not clickable" in e["error"]["message"]
    assert [m[1] for m in _marks(ie.log)] == ["begin"]
    assert read_argv_log(ie.argv_log)[-1] == action


def test_c53_marker_uuid_fresh_per_run(tmp_path, servers):  # WI4-C53
    ie = inert_env(tmp_path, servers, click=[http(("POST", "/api/notes/smoke_data/0")), {}])
    code1, e1, _ = run_cli(INERT_ARGV, ie.env)
    code2, e2, _ = run_cli(INERT_ARGV, ie.env)
    assert code1 == 0 and code2 == 0, (e1, e2)
    assert e1["data"]["writes"] == [POST_NOTE] and e1["data"]["inert"] is False
    assert e2["data"]["writes"] == [] and e2["data"]["requests"] == [] and e2["data"]["inert"] is True
    marks = _marks(ie.log)
    assert len(marks) == 4
    (u1, k1), (u1b, k2), (u2, k3), (u2b, k4) = marks
    assert (k1, k2, k3, k4) == ("begin", "end", "begin", "end")
    assert u1 == u1b and u2 == u2b and u1 != u2
    uuid.UUID(u1)
    uuid.UUID(u2)


def test_c54_hash_only_url_change_counts(tmp_path, servers):  # WI4-C54
    ie = inert_env(tmp_path, servers)
    before = ie.base + "/read/smoke_data/0"
    after = ie.base + "/read/smoke_data/0#epubcfi(/6/4)"
    fake_browse(tmp_path, [
        {"sub": "url", "contains": None, "responses": [{"stdout": before}, {"stdout": after}]},
        {"sub": "attrs", "contains": None, "responses": [{"stdout": json.dumps(ATTRS)}]},
        {"sub": "click", "contains": None, "responses": [{}]},
    ])
    code, e, _ = run_cli(INERT_ARGV, ie.env)
    assert code == 0, e
    d = e["data"]
    assert d["requests"] == []
    assert d["url_before"] == before and d["url_after"] == after
    assert d["url_changed"] is True and d["inert"] is False


@settings(deadline=None, max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sampled_from(["", "x y", "a/b", "é", "a.b", "-" * 3]))
def test_c45b_testid_regex_inprocess(bad):  # WI4-C45 (in-process companion: the validator itself)
    fn = _attr(cmd_reader, "valid_testid")
    ok = re.fullmatch(r"[A-Za-z0-9_-]+", bad) is not None
    assert fn(bad) is ok
