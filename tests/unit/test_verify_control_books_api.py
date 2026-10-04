"""WI-2 cases for the verify-reader3 control CLI: `fs`, `api`, `book add|index`, `up --stale-index`.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-2-3.md`, its addendum and the round 2
file (precedence: round 2 > index > addendum > part file). Each test carries its case id.

Socket rule: the test process never connects. Every CLI run that touches the network goes
through `run_cli` (a child), and every server is a child (`recording_server`). In-process
cases call pure functions on real tmp files only.

Ownership notes: the `ai ask` halves of WI2-C43, WI2-C44, WI2-C46 (part B) and WI2-C49
need WI-3's command and its SSE fake, so they live with WI-3; this module covers the
`api` / `fs` halves.
"""

from __future__ import annotations

import importlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from verify_control_fakes_http import (  # noqa: F401 (the autouse finalizer is imported for effect)
    CANARY_CONTENT,
    CANARY_NAME,
    REPLICA_KEY,
    mkfifo_outside,
    outside_dir,
    recording_server,
    stop_recorders,
)
from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    REPO,
    base_env,
    fake_venv,
    real_evidence_untouched,
    reap_fakes,
    rewrite_state,
    run_cli,
    snapshot_tree,
    spawn,
    wait_until,
    write_state,
)
from verify_control.paths import GuardRefusal

TOKEN = "tok-SECRET-9"
CAP = 262144
BODY_CAP = 65536
HYP = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def _seam(module, name):
    """The declared seam `module.name`; a missing one is an assertion failure, not an import error."""
    assert importlib.util.find_spec(module) is not None, f"module {module} does not exist yet"
    mod = importlib.import_module(module)
    assert hasattr(mod, name), f"{module} has no {name} yet"
    return getattr(mod, name)


def confine(root, rel):
    return _seam("verify_control.fs_view", "confine")(root, rel)


def build_url(base, path):
    return _seam("verify_control.cmd_api", "build_url")(base, path)


def check_headers(hs):
    return _seam("verify_control.cmd_api", "check_headers")(hs)


def parse_summary(text):
    return _seam("verify_control.cmd_books", "parse_summary")(text)


def parse_indexed(text, book_id):
    return _seam("verify_control.cmd_books", "parse_indexed")(text, book_id)


def seed_stale_index(book_dir):
    return _seam("verify_control.corpus", "seed_stale_index")(book_dir)


def _brief(r):
    """Failure diagnostics: exit, ok, error code. Not the message: the receipt classifier reads
    argparse's usage text in a red run as an environment failure."""
    err = r.envelope.get("error") or {}
    return f"exit={r.exit_code} ok={r.envelope.get('ok')} code={err.get('code')}"


def _ok(r):
    __tracebackhide__ = True
    rc, ok, brief = r.exit_code, r.envelope.get("ok"), _brief(r)
    assert rc == 0 and ok is True, brief
    return r.envelope["data"]


def _err(r, exit_code, code):
    __tracebackhide__ = True
    e = r.envelope
    got = (r.exit_code, e.get("ok"), (e.get("error") or {}).get("code"))
    assert got == (exit_code, False, code), _brief(r)
    assert e["error"]["try"].startswith("python3 ") and "control.py" in e["error"]["try"]
    return e


def _absent(r, *needles):
    for n in needles:
        assert n not in r.stdout and n not in r.stderr, n


def _hdrs(req, name):
    return [v for k, v in req["headers"] if k == name]


# ---------------------------------------------------------------------------
# WI2-C01 to C04: confine
# ---------------------------------------------------------------------------


def _confine_tree(tmp_path):
    sbx = tmp_path / "verify-reader3.abc"
    out = tmp_path / "outside"
    (out / "config").mkdir(parents=True)
    (out / CANARY_NAME).write_text(CANARY_CONTENT)
    (out / "config" / "ai_settings.json").write_text(REPLICA_KEY)
    (sbx / "books" / "smoke_data").mkdir(parents=True)
    (sbx / "books" / "smoke_data" / "book.pkl").write_bytes(b"")
    (sbx / "a").mkdir()
    (sbx / "notes.txt").write_text("hello")
    (sbx / "link_in").symlink_to(sbx / "books")
    (sbx / "link_out").symlink_to(out)
    (sbx / "chain2").symlink_to(out)
    (sbx / "chain1").symlink_to(sbx / "chain2")
    (sbx / "cfg_link").symlink_to(out / "config" / "ai_settings.json")
    (tmp_path / "verify-reader3.abcEVIL").mkdir()
    (tmp_path / "verify-reader3.abcEVIL" / "secret.txt").write_text("s")
    (tmp_path / "alias").symlink_to(sbx)
    return sbx, out


def _rp(p):
    return Path(os.path.realpath(p))


def test_wi2_c01_accepted_relative_paths_resolve_to_realpath(tmp_path):  # WI2-C01
    sbx, _ = _confine_tree(tmp_path)
    cases = {
        "notes.txt": sbx / "notes.txt",
        "books/smoke_data/book.pkl": sbx / "books" / "smoke_data" / "book.pkl",
        "a/../notes.txt": sbx / "notes.txt",
        ".": sbx,
        "books/../notes.txt": sbx / "notes.txt",
    }
    for rel, expected in cases.items():
        assert confine(sbx, rel) == _rp(expected), rel


@pytest.mark.parametrize("rel", [
    "../outside/" + CANARY_NAME,
    "/etc/hosts",
    "ABS-INSIDE",
    "link_out/" + CANARY_NAME,
    "link_out",
    "chain1",
    "cfg_link",
    "../verify-reader3.abcEVIL/secret.txt",
    "books/../../outside",
])
def test_wi2_c02_every_escape_form_is_refused(tmp_path, rel):  # WI2-C02
    sbx, _ = _confine_tree(tmp_path)
    if rel == "ABS-INSIDE":
        rel = str(sbx / "notes.txt")
    with pytest.raises(GuardRefusal) as ei:
        confine(sbx, rel)
    assert ei.value.code == "refused_path"


def test_wi2_c03_in_sandbox_symlinks_and_alias_root(tmp_path):  # WI2-C03
    sbx, _ = _confine_tree(tmp_path)
    alias = tmp_path / "alias"
    assert confine(sbx, "link_in/smoke_data/book.pkl") == _rp(sbx / "books" / "smoke_data" / "book.pkl")
    assert confine(alias, "notes.txt") == _rp(sbx / "notes.txt")
    with pytest.raises(GuardRefusal) as ei:
        confine(alias, "../outside")
    assert ei.value.code == "refused_path"


_SEGS = st.sampled_from(["notes.txt", "books", "smoke_data", "..", ".", "link_in", "link_out", "chain1",
                         "cfg_link", "missing", "a"])


def test_wi2_c04_property_accept_iff_realpath_inside(tmp_path):  # WI2-C04
    sbx, _ = _confine_tree(tmp_path)
    root = os.path.realpath(sbx)

    @HYP
    @given(segs=st.lists(_SEGS, min_size=1, max_size=6), lead=st.booleans())
    def prop(segs, lead):
        p = ("/" if lead else "") + "/".join(segs)
        if lead:
            with pytest.raises(GuardRefusal) as ei:
                confine(sbx, p)
            assert ei.value.code == "refused_path"
            return
        r = os.path.realpath(os.path.join(root, p))
        inside = r == root or r.startswith(root + os.sep)
        if inside:
            assert confine(sbx, p) == Path(r), p
        else:
            with pytest.raises(GuardRefusal) as ei:
                confine(sbx, p)
            assert ei.value.code == "refused_path", p

    prop()


# ---------------------------------------------------------------------------
# WI2-C05 to C08, C48: fs
# ---------------------------------------------------------------------------


@pytest.mark.verify_control_live
def test_wi2_c05_ls_stat_cat_inside_the_sandbox(tmp_path):  # WI2-C05
    fx = write_state(tmp_path)
    os.chmod(fx.sandbox / "ai_settings.json", 0o600)
    notes = fx.sandbox / "notes.txt"
    notes.write_text("hello\n")
    before = os.stat(notes).st_mtime_ns
    d = _ok(run_cli(["fs", "cat", "notes.txt"], fx.env, timeout=15))
    assert d == {"path": "notes.txt", "size": 6, "content": "hello\n", "truncated": False}
    d = _ok(run_cli(["fs", "stat", "ai_settings.json"], fx.env, timeout=15))
    assert (d["type"], d["mode"], d["size"]) == ("file", "0600", 2)
    d = _ok(run_cli(["fs", "ls", "books"], fx.env, timeout=15))
    assert [e["name"] for e in d["entries"]] == ["smoke_data"]
    assert d["entries"][0]["type"] == "dir"
    assert os.stat(notes).st_mtime_ns == before


@pytest.mark.verify_control_live
def test_wi2_c06_cat_cap_is_exactly_256_kib(tmp_path):  # WI2-C06
    fx = write_state(tmp_path)
    (fx.sandbox / "at_cap.bin").write_bytes(b"x" * CAP)
    (fx.sandbox / "over_cap.bin").write_bytes(b"x" * (CAP + 1))
    d = _ok(run_cli(["fs", "cat", "at_cap.bin"], fx.env, timeout=15))
    assert (len(d["content"]), d["truncated"], d["size"]) == (CAP, False, CAP)
    d = _ok(run_cli(["fs", "cat", "over_cap.bin"], fx.env, timeout=15))
    assert (len(d["content"]), d["truncated"], d["size"]) == (CAP, True, CAP + 1)


@pytest.mark.verify_control_live
def test_wi2_c07_refusals_never_read_the_forbidden_file(tmp_path):  # WI2-C07
    fx = write_state(tmp_path)
    out = outside_dir(tmp_path)
    pipe = mkfifo_outside(tmp_path, "pipe")
    (fx.sandbox / "link_fifo").symlink_to(pipe)
    (fx.sandbox / "link_out").symlink_to(out)
    (fx.sandbox / "cfg_link").symlink_to(out / "config" / "ai_settings.json")
    runs = [
        ["fs", "cat", "link_fifo"],
        ["fs", "cat", "../outside/pipe"],
        ["fs", "ls", "link_out"],
        ["fs", "ls", "../outside"],
        ["fs", "cat", str(out / CANARY_NAME)],
        ["fs", "stat", "cfg_link"],
    ]
    for argv in runs:
        r = run_cli(argv, fx.env, timeout=10)
        _err(r, 3, "refused_path")
        _absent(r, "CANARY-outside-7f3", CANARY_CONTENT, REPLICA_KEY)


@pytest.mark.verify_control_live
def test_wi2_c08_missing_in_sandbox_path(tmp_path):  # WI2-C08
    fx = write_state(tmp_path)
    e = _err(run_cli(["fs", "cat", "nope.txt"], fx.env, timeout=15), 1, "not_found")
    assert "nope.txt" in e["error"]["message"]
    assert not (fx.sandbox / "nope.txt").exists()


@pytest.mark.verify_control_live
def test_wi2_c48a_fifo_and_directory_are_not_a_file(tmp_path):  # WI2-C48(a)
    fx = write_state(tmp_path)
    os.mkfifo(fx.sandbox / "pipe")
    r = run_cli(["fs", "cat", "pipe"], fx.env, timeout=10)
    e = _err(r, 1, "not_a_file")
    assert "pipe" in e["error"]["message"] and r.elapsed_s < 5
    assert (fx.sandbox / "pipe").exists()
    e = _err(run_cli(["fs", "cat", "books"], fx.env, timeout=10), 1, "not_a_file")
    assert "books" in e["error"]["message"]


@pytest.mark.verify_control_live
def test_wi2_c48b_sibling_prefix_escape_at_the_cli(tmp_path):  # WI2-C48(b)
    fx = write_state(tmp_path)
    evil = fx.sandbox.parent / (fx.sandbox.name + "EVIL")
    evil.mkdir()
    (evil / "secret.txt").write_text("SECRET-EVIL-41c")
    before = snapshot_tree(evil)
    for argv in (["fs", "cat", f"../{fx.sandbox.name}EVIL/secret.txt"], ["fs", "ls", f"../{fx.sandbox.name}EVIL"]):
        r = run_cli(argv, fx.env, timeout=10)
        _err(r, 3, "refused_path")
        _absent(r, "SECRET-EVIL-41c", "secret.txt")
    assert snapshot_tree(evil) == before


_RSS_WRAPPER = (
    "import json, resource, subprocess, sys\n"
    "r = subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL, capture_output=True, timeout=60)\n"
    "rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n"
    "rss = rss if sys.platform == 'darwin' else rss * 1024\n"
    "print(json.dumps({'rc': r.returncode, 'out': r.stdout.decode(), 'err': r.stderr.decode(), 'rss': rss}))\n"
)


@pytest.mark.verify_control_live
def test_wi2_c48c_cat_reads_a_1gib_sparse_file_with_bounded_memory(tmp_path):  # WI2-C48(c), round 2
    fx = write_state(tmp_path)
    huge = fx.sandbox / "huge.bin"
    huge.write_bytes(b"x" * (CAP + 16))
    os.truncate(huge, 2**30)
    cli = [sys.executable, str(REPO / ".claude/skills/verify-reader3/scripts/control.py"), "fs", "cat", "huge.bin"]
    res = subprocess.run([sys.executable, "-c", _RSS_WRAPPER, *cli], env=fx.env, cwd=fx.env["TMPDIR"],
                         capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
    assert res.returncode == 0, res.stderr
    w = json.loads(res.stdout)
    assert w["rc"] == 0, w["err"]
    d = json.loads(w["out"])["data"]
    assert d["truncated"] is True and len(d["content"]) == CAP and d["content"] == "x" * CAP
    assert d["size"] == 2**30
    assert w["rss"] < 512 * 2**20, w["rss"]


# ---------------------------------------------------------------------------
# WI2-C09 to C11: build_url, check_headers
# ---------------------------------------------------------------------------

B = "http://127.0.0.1:8123"


@pytest.mark.parametrize("path", ["/api/library", "/", "/api/search?q=caf%C3%A9&x=1", "/api/search?q=a@b",
                                  "/%2F%2Fevil/x"])
def test_wi2_c09_accepted_paths(path):  # WI2-C09
    assert build_url(B, path) == B + path


@pytest.mark.parametrize("path", ["http://evil/", "HTTP://127.0.0.1:8123/api", "https://127.0.0.1:8123/", "//evil/x",
                                  "///evil", "\\\\evil\\x", "/\\evil", "api/library", "", "/@evil",
                                  "/x\r\nHost: evil", "/x y", "/x\x00"])
def test_wi2_c10_refused_url_forms(path):  # WI2-C10
    with pytest.raises(GuardRefusal) as ei:
        build_url(B, path)
    assert ei.value.code == "refused_url"


@pytest.mark.parametrize("h", [["Host: evil"], ["host : evil"], ["HOST:evil"], ["Origin: http://evil"],
                               ["X-A: 1\r\nHost: evil"], ["NoColon"]])
def test_wi2_c10_refused_header_forms(h):  # WI2-C10
    with pytest.raises(GuardRefusal) as ei:
        check_headers(h)
    assert ei.value.code == "refused_url"


def test_wi2_c10_header_control():  # WI2-C10 control
    assert check_headers(["X-Trace: t1"]) == [("X-Trace", "t1")]


_PREFIXES = st.sampled_from(["/", "//", "http:", "https://", "\\", "/@", "/\\", "@", "/x?", "HTTP://"])


@HYP
@given(s=st.one_of(st.text(max_size=40), st.builds(lambda a, b: a + b, _PREFIXES, st.text(max_size=30))),
       port=st.integers(1024, 65535))
def test_wi2_c11_property_host_and_port_preserved_or_refused(s, port):  # WI2-C11
    base = f"http://127.0.0.1:{port}"
    try:
        u = build_url(base, s)
    except GuardRefusal as exc:
        assert exc.code == "refused_url"
        return
    assert u == base + s
    parts = urlsplit(u)
    assert parts.hostname == "127.0.0.1" and parts.port == port
    assert s.startswith("/") and not s.startswith("//")


# ---------------------------------------------------------------------------
# WI2-C12 to C22, C45, C49: api
# ---------------------------------------------------------------------------


@pytest.mark.verify_control_live
def test_wi2_c12_get_with_token_header_sent_no_origin_body_parsed(tmp_path):  # WI2-C12
    rec = recording_server(tmp_path, {"GET /api/library": {
        "status": 200, "headers": {"Content-Type": "application/json", "ETag": '"lib-1"', "X-Other": "y"},
        "body": '{"books":["smoke_data"]}'}})
    fx = write_state(tmp_path, base_url=rec.base_url, token=TOKEN)
    r = run_cli(["api", "GET", "/api/library"], fx.env, timeout=15)
    d = _ok(r)
    assert d["status"] == 200 and d["body"] == {"books": ["smoke_data"]}
    assert d["headers"] == {"content-type": "application/json", "etag": '"lib-1"'}
    assert d["expect_ok"] is None
    assert isinstance(d["elapsed_ms"], int) and d["elapsed_ms"] >= 0
    _absent(r, TOKEN)
    reqs = rec.requests()
    assert len(reqs) == 1
    q = reqs[0]
    assert (q["method"], q["target"]) == ("GET", "/api/library")
    assert _hdrs(q, "x-reader3-token") == [TOKEN]
    assert _hdrs(q, "origin") == []
    assert _hdrs(q, "host") == [f"127.0.0.1:{rec.port}"]


@pytest.mark.verify_control_live
def test_wi2_c13_no_token_configured_no_token_header(tmp_path):  # WI2-C13
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url, token=None)
    assert _ok(run_cli(["api", "GET", "/api/library"], fx.env, timeout=15))["status"] == 200
    (q,) = rec.requests()
    assert _hdrs(q, "x-reader3-token") == [] and _hdrs(q, "origin") == []


@pytest.mark.verify_control_live
def test_wi2_c14_post_json_file_if_match_header_inline_and_evidence_file(tmp_path):  # WI2-C14
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    (fx.sandbox / "req.json").write_text(json.dumps({"note": "α", "n": 1}, ensure_ascii=False), encoding="utf-8")
    ev = Path(fx.env["VERIFY_READER3_EVIDENCE_ROOT"]) / "ev"
    ev.mkdir(parents=True)
    (ev / "body.json").write_text('{"z":true}')
    runs = [
        (["api", "POST", "/api/notes/smoke_data", "--json", "@req.json", "--if-match", '"v1"',
          "--header", "X-Trace: t1"], fx.sandbox),
        (["api", "PUT", "/api/x", "--json", '{"a":[1,2]}'], None),
        (["api", "PATCH", "/api/y", "--json", "@" + str(ev / "body.json")], None),
    ]
    for argv, cwd in runs:
        assert _ok(run_cli(argv, fx.env, timeout=15, cwd=cwd))["status"] == 200
    post, put, patch = rec.requests()
    assert post["method"] == "POST" and json.loads(post["body"]) == {"note": "α", "n": 1}
    assert _hdrs(post, "content-type")[0].startswith("application/json")
    assert _hdrs(post, "if-match") == ['"v1"'] and _hdrs(post, "x-trace") == ["t1"]
    assert _hdrs(post, "origin") == []
    assert put["method"] == "PUT" and json.loads(put["body"]) == {"a": [1, 2]}
    assert patch["method"] == "PATCH" and json.loads(patch["body"]) == {"z": True}


def _status_routes():
    return {
        "GET /c": {"status": 409, "headers": {"Content-Type": "application/json"}, "body": '{"detail":"conflict"}'},
        "GET /nf": {"status": 404, "headers": {"Content-Type": "application/json"}, "body": '{"detail":"Not Found"}'},
        "GET /boom": {"status": 500, "headers": {"Content-Type": "application/json"}, "body": '{"detail":"x"}'},
        "GET /hang": {"status": 200, "headers": {"Content-Type": "application/json"}, "body": "{}", "delay_s": 10},
    }


@pytest.mark.verify_control_live
def test_wi2_c15_expect_semantics_and_no_retry(tmp_path):  # WI2-C15
    rec = recording_server(tmp_path, _status_routes())
    fx = write_state(tmp_path, base_url=rec.base_url)
    r = run_cli(["api", "GET", "/c", "--expect", "200"], fx.env, timeout=15)
    e = _err(r, 1, "unexpected_status")
    assert "200" in e["error"]["message"] and "409" in e["error"]["message"]
    assert e["data"]["status"] == 409 and e["data"]["expect_ok"] is False
    assert _ok(run_cli(["api", "GET", "/c", "--expect", "409"], fx.env, timeout=15))["expect_ok"] is True
    d = _ok(run_cli(["api", "GET", "/nf"], fx.env, timeout=15))
    assert d["status"] == 404 and d["expect_ok"] is None
    assert _ok(run_cli(["api", "GET", "/boom"], fx.env, timeout=15))["status"] == 500
    assert [q["target"] for q in rec.requests()] == ["/c", "/c", "/nf", "/boom"]


@pytest.mark.verify_control_live
def test_wi2_c16_body_truncation_boundary_and_elapsed(tmp_path):  # WI2-C16
    rec = recording_server(tmp_path, {
        "GET /t64": {"status": 200, "headers": {"Content-Type": "text/plain"}, "body": "y" * BODY_CAP},
        "GET /t65": {"status": 200, "headers": {"Content-Type": "text/plain"}, "body": "y" * (BODY_CAP + 1)},
        "GET /slow": {"status": 200, "headers": {"Content-Type": "application/json"}, "body": "{}", "delay_s": 0.25},
    })
    fx = write_state(tmp_path, base_url=rec.base_url)
    d = _ok(run_cli(["api", "GET", "/t64"], fx.env, timeout=15))
    assert d["body"] == "y" * BODY_CAP and d["body_truncated"] is False
    d = _ok(run_cli(["api", "GET", "/t65"], fx.env, timeout=15))
    assert len(d["body"]) == BODY_CAP and d["body_truncated"] is True
    assert _ok(run_cli(["api", "GET", "/slow"], fx.env, timeout=15))["elapsed_ms"] >= 250
    assert len(rec.requests()) == 3


def _c17_runs(evil_port):
    return [
        ["api", "GET", "http://evil/"],
        ["api", "GET", f"http://127.0.0.1:{evil_port}/x"],
        ["api", "GET", f"//127.0.0.1:{evil_port}/x"],
        ["api", "GET", "/x", "--header", "Host:evil"],
        ["api", "GET", "/x", "--header", f"host : 127.0.0.1:{evil_port}"],
        ["api", "POST", "/x", "--header", "Origin: http://evil", "--json", "{}"],
        ["api", "GET", "/x", "--header", "X-A: 1\r\nHost: evil"],
    ]


@pytest.mark.verify_control_live
def test_wi2_c17_url_host_origin_crlf_refusals_open_no_connection(tmp_path):  # WI2-C17 (amended)
    rec, evil = recording_server(tmp_path), recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    for argv in _c17_runs(evil.port):
        _err(run_cli(argv, fx.env, timeout=10), 3, "refused_url")
    assert rec.requests() == [] and evil.requests() == []
    assert _ok(run_cli(["api", "GET", "/x", "--header", "X-A: 1"], fx.env, timeout=10))["status"] == 200
    (q,) = rec.requests()
    assert _hdrs(q, "x-a") == ["1"] and _hdrs(q, "host") == [f"127.0.0.1:{rec.port}"]


@pytest.mark.verify_control_live
def test_wi2_c18_proxy_env_cannot_redirect(tmp_path):  # WI2-C18
    rec, proxy = recording_server(tmp_path), recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    env = {k: v for k, v in fx.env.items() if k not in ("NO_PROXY", "no_proxy")}
    env.update(HTTP_PROXY=proxy.base_url, http_proxy=proxy.base_url, ALL_PROXY=proxy.base_url)
    assert _ok(run_cli(["api", "GET", "/api/library"], env, timeout=15))["status"] == 200
    assert len(rec.requests()) == 1 and proxy.requests() == []


@pytest.mark.verify_control_live
def test_wi2_c49_proxy_environment_has_no_effect_api_half(tmp_path):  # WI2-C49 (api half; ai ask is WI-3)
    rec, evil = recording_server(tmp_path), recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url, token=TOKEN)
    env = dict(fx.env, NO_PROXY="", no_proxy="")
    for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env[k] = evil.base_url
    assert _ok(run_cli(["api", "GET", "/x"], env, timeout=15))["status"] == 200
    assert evil.requests() == [] and len(rec.requests()) == 1


@pytest.mark.verify_control_live
def test_wi2_c19_json_file_outside_is_refused_without_reading(tmp_path):  # WI2-C19
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    out = outside_dir(tmp_path)
    pipe = mkfifo_outside(tmp_path, "pipe")
    (fx.sandbox / "esc.json").symlink_to(out / CANARY_NAME)
    runs = [
        (["api", "POST", "/x", "--json", "@" + str(pipe)], None),
        (["api", "POST", "/x", "--json", "@../outside/pipe"], fx.sandbox),
        (["api", "POST", "/x", "--json", "@esc.json"], fx.sandbox),
        (["api", "POST", "/x", "--json", "@" + str(out / CANARY_NAME)], None),
    ]
    for argv, cwd in runs:
        r = run_cli(argv, fx.env, timeout=10, cwd=cwd)
        _err(r, 3, "refused_path")
        _absent(r, CANARY_CONTENT)
    assert rec.requests() == []


@pytest.mark.verify_control_live
def test_wi2_c20_dry_run_connects_nowhere_and_redacts_token(tmp_path):  # WI2-C20
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url, token=TOKEN)
    runs = [
        ["api", "POST", "/api/notes/smoke_data", "--json", '{"a":1}', "--if-match", '"v1"', "--dry-run"],
        ["api", "DELETE", "/api/notes/smoke_data/n1", "--dry-run"],
        ["api", "GET", "/api/library", "--dry-run"],
    ]
    results = [run_cli(argv, fx.env, timeout=15) for argv in runs]
    for r in results:
        assert _ok(r)["dry_run"] is True
        _absent(r, TOKEN)
    req = results[0].envelope["data"]["request"]
    assert req["method"] == "POST"
    assert req["url"] == f"http://127.0.0.1:{rec.port}/api/notes/smoke_data"
    names = {h.lower() for h in req["header_names"]}
    assert names >= {"x-reader3-token", "content-type", "if-match"} and "origin" not in names
    assert req["body"] == {"a": 1}
    assert rec.requests() == []


@pytest.mark.verify_control_live
def test_wi2_c21a_connection_refused(tmp_path):  # WI2-C21(a)
    dead = recording_server(tmp_path)
    dead.stop()
    fx = write_state(tmp_path, base_url=dead.base_url)
    e = _err(run_cli(["api", "GET", "/api/health"], fx.env, timeout=15), 1, "connect_failed")
    assert "control.py doctor" in e["error"]["try"]


@pytest.mark.verify_control_live
def test_wi2_c21b_request_timeout(tmp_path):  # WI2-C21(b)
    rec = recording_server(tmp_path, _status_routes())
    fx = write_state(tmp_path, base_url=rec.base_url)
    r = run_cli(["api", "GET", "/hang", "--timeout", "1"], fx.env, timeout=10)
    _err(r, 1, "timeout")
    assert r.elapsed_s < 5
    assert [q["target"] for q in rec.requests()] == ["/hang"]


@pytest.mark.verify_control_live
@pytest.mark.parametrize("argv", [["api", "FROB", "/x"], ["api", "POST", "/x", "--json", "{bad"], ["api", "GET"]])
def test_wi2_c22_usage_errors_send_nothing(tmp_path, argv):  # WI2-C22
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    r = run_cli(argv, fx.env, timeout=10)
    assert (r.exit_code, r.envelope["error"]["code"]) == (2, "usage")
    assert r.stdout.count("\n") == 1
    assert rec.requests() == []


@pytest.mark.verify_control_live
def test_wi2_c45_redirects_are_reported_never_followed(tmp_path):  # WI2-C45
    evil = recording_server(tmp_path)
    rec = recording_server(tmp_path, {
        "GET /r": {"status": 302, "headers": {"Location": f"{evil.base_url}/stolen", "Content-Type": "text/plain"},
                   "body": ""},
        "POST /r7": {"status": 307, "headers": {"Location": f"{evil.base_url}/stolen7", "Content-Type": "text/plain"},
                     "body": ""},
    })
    fx = write_state(tmp_path, base_url=rec.base_url, token=TOKEN)
    d = _ok(run_cli(["api", "GET", "/r"], fx.env, timeout=15))
    assert d["status"] == 302 and d["headers"]["location"] == f"{evil.base_url}/stolen" and d["expect_ok"] is None
    e = _err(run_cli(["api", "GET", "/r", "--expect", "200"], fx.env, timeout=15), 1, "unexpected_status")
    assert e["data"]["status"] == 302 and e["data"]["expect_ok"] is False
    d = _ok(run_cli(["api", "POST", "/r7", "--json", '{"a":1}'], fx.env, timeout=15))
    assert d["status"] == 307 and d["headers"]["location"] == f"{evil.base_url}/stolen7"
    assert [q["target"] for q in rec.requests()] == ["/r", "/r", "/r7"]
    assert evil.requests() == []


# ---------------------------------------------------------------------------
# WI2-C43, C44, C46: tampered state, token never leaks (api / fs halves)
# ---------------------------------------------------------------------------


def _c43_tampers(evil_port):
    return [
        (f"http://localhost.evil:{evil_port}", evil_port),
        ("http://10.0.0.5:1", 1),
        ("https://127.0.0.1:1", 1),
        (f"http://u@127.0.0.1:{evil_port}", evil_port),
        (f"http://127.0.0.1:{evil_port}/pfx", evil_port),
        (f"http://localhost:{evil_port}", evil_port),
        ("http://127.0.0.1", 80),
        (f"http://127.0.0.1:{evil_port}?q=1", evil_port),
    ]


@pytest.mark.verify_control_live
def test_wi2_c43_tampered_base_url_is_refused_before_connect(tmp_path):  # WI2-C43 (round 2; api half)
    rec, evil = recording_server(tmp_path), recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    for url, port in _c43_tampers(evil.port):
        rewrite_state(fx.state_path, base_url=url, port=port)
        r = run_cli(["api", "GET", "/x"], fx.env, timeout=10)
        _err(r, 3, "refused_url")
        assert r.elapsed_s < 5, url
    assert evil.requests() == [] and rec.requests() == []
    rewrite_state(fx.state_path, base_url=evil.base_url, port=evil.port)
    assert _ok(run_cli(["api", "GET", "/x"], fx.env, timeout=10))["status"] == 200
    assert [q["target"] for q in evil.requests()] == ["/x"]


@pytest.mark.verify_control_live
def test_wi2_c44_tampered_sandbox_is_refused_before_any_read(tmp_path):  # WI2-C44 (round 2; fs and api halves)
    rec = recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url)
    out = outside_dir(tmp_path)
    pipe = mkfifo_outside(tmp_path, "pipe")
    link = tmp_path / "verify-reader3.link"
    link.symlink_to(tmp_path)

    def snap():
        s = snapshot_tree(fx.sandbox)
        s.pop("state.json", None)
        return s, snapshot_tree(out)

    before = snap()
    for sval in (str(tmp_path), "/", str(link)):
        rewrite_state(fx.state_path, sandbox=sval)
        runs = [
            ["fs", "cat", os.path.relpath(out / CANARY_NAME, sval)],
            ["fs", "cat", os.path.relpath(pipe, sval)],
            ["api", "POST", "/x", "--json", "@" + str(out / CANARY_NAME)],
            ["api", "POST", "/x", "--json", "@" + str(pipe)],
        ]
        for argv in runs:
            r = run_cli(argv, fx.env, timeout=10)
            _err(r, 3, "refused_sandbox_shape")
            _absent(r, CANARY_CONTENT)
            if argv[0] == "fs":
                _absent(r, "CANARY-outside-7f3")
    assert rec.requests() == []
    assert snap() == before


@pytest.mark.verify_control_live
def test_wi2_c46_token_never_leaks_on_api_failure_paths(tmp_path):  # WI2-C46 part A (part B is WI-3)
    rec, evil = recording_server(tmp_path, _status_routes()), recording_server(tmp_path)
    fx = write_state(tmp_path, base_url=rec.base_url, token=TOKEN)
    runs = [(["api", "GET", "/c", "--expect", "200"], "unexpected_status")]
    runs += [(argv, "refused_url") for argv in _c17_runs(evil.port)]
    runs.append((["api", "GET", "/hang", "--timeout", "1"], "timeout"))
    for argv, code in runs:
        r = run_cli(argv, fx.env, timeout=10)
        assert (r.envelope.get("error") or {}).get("code") == code, (argv, _brief(r))
        _absent(r, TOKEN)
    hang = [q for q in rec.requests() if q["target"] == "/hang"]
    assert len(hang) == 1 and _hdrs(hang[0], "x-reader3-token") == [TOKEN]
    dead = recording_server(tmp_path)
    dead.stop()
    rewrite_state(fx.state_path, base_url=dead.base_url, port=dead.port)
    r = run_cli(["api", "GET", "/api/health"], fx.env, timeout=10)
    assert r.envelope["error"]["code"] == "connect_failed"
    _absent(r, TOKEN)
    rewrite_state(fx.state_path, base_url=f"http://localhost:{evil.port}", port=evil.port)
    r = run_cli(["api", "GET", "/x"], fx.env, timeout=10)
    assert r.envelope["error"]["code"] == "refused_url"
    _absent(r, TOKEN)
    assert evil.requests() == []


# ---------------------------------------------------------------------------
# WI2-C23 to C25: parsers
# ---------------------------------------------------------------------------

SUMMARY = ("Loading /x/a.epub...\nExtracting images...\nSaved structured data to /s/a_data/book.pkl\n\n"
           "--- Summary ---\nTitle: Dracula: A Novel\nAuthors: Bram Stoker, Anon\nPhysical Files (Spine): 27\n"
           "TOC Root Items: 3\nImages extracted: 0\n")
SUMMARY_DICT = {"title": "Dracula: A Novel", "authors": ["Bram Stoker", "Anon"], "spine_files": 27,
                "toc_root_items": 3, "images_extracted": 0}
INDEXED = "Indexed smoke_data: 7 chunks using paraphrase-multilingual-MiniLM-L12-v2\n"


def test_wi2_c23_summary_and_index_line_examples():  # WI2-C23
    assert parse_summary(SUMMARY) == SUMMARY_DICT
    assert parse_summary(SUMMARY.replace("Authors: Bram Stoker, Anon", "Authors: "))["authors"] == []
    assert parse_summary("no summary here\n") is None
    assert parse_indexed("Indexed smoke_data: 12 chunks using paraphrase-multilingual-MiniLM-L12-v2\n",
                         "smoke_data") == {"chunks": 12, "model": "paraphrase-multilingual-MiniLM-L12-v2"}
    assert parse_indexed("Indexed smoke_data: 0 chunks using sentence-transformers/x y\n", "smoke_data") == {
        "chunks": 0, "model": "sentence-transformers/x y"}
    assert parse_indexed("Loading...\n", "smoke_data") is None


_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp")), min_size=1, max_size=40)


@HYP
@given(t=_TEXT.filter(lambda s: s == s.strip()),
       a=st.lists(_TEXT.filter(lambda s: ", " not in s and s.strip() and s == s.strip()), max_size=4),
       s=st.integers(0, 10_000), r=st.integers(0, 10_000), i=st.integers(0, 10_000))
def test_wi2_c24_property_summary_round_trip(t, a, s, r, i):  # WI2-C24
    text = ("Loading x\n" + "\n--- Summary ---\n" + f"Title: {t}\n" + f"Authors: {', '.join(a)}\n"
            + f"Physical Files (Spine): {s}\n" + f"TOC Root Items: {r}\n" + f"Images extracted: {i}\n")
    assert parse_summary(text) == {"title": t, "authors": a, "spine_files": s, "toc_root_items": r,
                                   "images_extracted": i}


@HYP
@given(book_id=st.from_regex(r"[A-Za-z0-9 ._-]{1,20}_data", fullmatch=True), n=st.integers(0, 10**6),
       model=st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp")), min_size=1,
                     max_size=60).filter(lambda s: s == s.strip()))
def test_wi2_c25_property_index_line_round_trip(book_id, n, model):  # WI2-C25
    stdout = "Loading\n" + f"Indexed {book_id}: {n} chunks using {model}\n"
    assert parse_indexed(stdout, book_id) == {"chunks": n, "model": model}


# ---------------------------------------------------------------------------
# WI2-C26 to C29: book add
# ---------------------------------------------------------------------------

LEAKS = {"READER3_TOKEN": "leak", "READER3_LIBRARY_UI": "classic", "READER3_EMBED_MODEL": "evil-model"}
OFFLINE_KEYS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")


def _book_setup(tmp_path, **venv_kw):
    fv = fake_venv(tmp_path, writes=False, **venv_kw)
    fx = write_state(tmp_path)
    env = {k: v for k, v in fx.env.items() if k not in OFFLINE_KEYS}
    env.update(LEAKS)
    assert env["VERIFY_READER3_VENV_BIN"] == str(fv.bin)
    return fv, fx, env


def _r3(env_dict):
    return {k: v for k, v in env_dict.items() if k.startswith("READER3_")}


def _sandbox_r3(fx):
    return {"READER3_BOOKS_DIR": str(fx.books_dir), "READER3_AI_SETTINGS": str(fx.sandbox / "ai_settings.json")}


@pytest.mark.verify_control_live
def test_wi2_c26_add_sandbox_env_abs_epub_sandbox_cwd_summary(tmp_path):  # WI2-C26
    fv, fx, env = _book_setup(tmp_path)
    fv.script({"add": {"stdout": SUMMARY, "stderr": "", "exit": 0}})
    epub = tmp_path / "src" / "My Book.v2.epub"
    epub.parent.mkdir()
    epub.write_bytes(b"PK")
    d = _ok(run_cli(["book", "add", "--epub", "src/My Book.v2.epub"], env, timeout=15, cwd=tmp_path))
    assert d["book_id"] == "My Book.v2_data"
    assert d["summary"] == SUMMARY_DICT
    (call,) = fv.calls("reader3")
    assert call["argv"][1:] == [str(epub.resolve())]
    assert call["cwd"] == str(fx.sandbox)
    assert _r3(call["env"]) == _sandbox_r3(fx)


@pytest.mark.verify_control_live
def test_wi2_c27_add_dry_run_spawns_nothing(tmp_path):  # WI2-C27
    fv, fx, env = _book_setup(tmp_path)
    epub = tmp_path / "src" / "a.epub"
    epub.parent.mkdir()
    epub.write_bytes(b"PK")
    d = _ok(run_cli(["book", "add", "--epub", str(epub), "--dry-run"], env, timeout=15))
    assert d["dry_run"] is True
    assert d["argv"] == [str(fv.bin / "reader3"), str(epub.resolve())]
    assert d["env_keys"] == ["READER3_AI_SETTINGS", "READER3_BOOKS_DIR"]
    assert d["book_id"] == "a_data"
    assert fv.calls("reader3") == [] and fv.calls("python") == []


@pytest.mark.verify_control_live
def test_wi2_c28_add_failure_modes(tmp_path):  # WI2-C28
    fv, fx, env = _book_setup(tmp_path)
    epub = tmp_path / "a.epub"
    epub.write_bytes(b"PK")
    _err(run_cli(["book", "add", "--epub", str(tmp_path / "missing.epub")], env, timeout=15), 1, "epub_not_found")
    assert fv.calls("reader3") == []
    fv.script({"add": {"stdout": "", "stderr": "smoke_data is held by reader3-server (pid 4242)\n", "exit": 1}})
    e = _err(run_cli(["book", "add", "--epub", str(epub)], env, timeout=15), 1, "add_failed")
    assert "held by reader3-server (pid 4242)" in e["error"]["message"]
    assert len(fv.calls("reader3")) == 1
    fv.script({"add": {"stdout": "Loading x\n", "stderr": "", "exit": 0}})
    e = _err(run_cli(["book", "add", "--epub", str(epub)], env, timeout=15), 1, "add_failed")
    assert "Summary" in e["error"]["message"]
    assert len(fv.calls("reader3")) == 2


@pytest.mark.verify_control_live
def test_wi2_c29_guard1_at_the_book_call_sites(tmp_path):  # WI2-C29
    fv, fx, env = _book_setup(tmp_path)
    rewrite_state(fx.state_path, books_dir=str(REPO / "books"))
    epub = tmp_path / "a.epub"
    epub.write_bytes(b"PK")
    for argv in (["book", "add", "--epub", str(epub)], ["book", "index", "smoke_data"]):
        _err(run_cli(argv, env, timeout=10), 3, "refused_books_dir")
    assert fv.calls("reader3") == [] and fv.calls("python") == []


# ---------------------------------------------------------------------------
# WI2-C30 to C38, C47: book index
# ---------------------------------------------------------------------------


def _model_dir():
    vs = importlib.import_module("reader3_app.vector_search")
    return f"models--sentence-transformers--{vs.MODEL_NAME}"


def _cache(tmp_path):
    d = tmp_path / "hf" / "hub" / _model_dir()
    d.mkdir(parents=True)
    return d


@pytest.mark.verify_control_live
def test_wi2_c30_branch_a_extra_missing_short_circuits(tmp_path):  # WI2-C30
    fv, fx, env = _book_setup(tmp_path, extra_installed=False)
    _cache(tmp_path)
    d = _ok(run_cli(["book", "index", "smoke_data"], env, timeout=15))
    assert d["extra_installed"] is False
    assert "uv sync --extra semantic" in d["hint"]
    assert d.get("spawned") is False
    assert len(fv.calls("python")) == 1 and fv.calls("reader3") == []


@pytest.mark.verify_control_live
def test_wi2_c31_branch_b_model_not_cached(tmp_path):  # WI2-C31
    fv, fx, env = _book_setup(tmp_path)
    d = _ok(run_cli(["book", "index", "smoke_data"], env, timeout=15))
    assert d["extra_installed"] is True and d["model_cached"] is False
    assert d["skipped"] == "model_not_cached" and "--allow-download" in d["hint"]
    assert fv.calls("reader3") == []


@pytest.mark.verify_control_live
def test_wi2_c32_branch_c_real_run_offline_env_parsed(tmp_path):  # WI2-C32
    fv, fx, env = _book_setup(tmp_path)
    _cache(tmp_path)
    fv.script({"index": {"stdout": INDEXED, "stderr": "", "exit": 0}})
    d = _ok(run_cli(["book", "index", "smoke_data"], env, timeout=15))
    assert (d["chunks"], d["model"], d["offline"]) == (7, "paraphrase-multilingual-MiniLM-L12-v2", True)
    (call,) = fv.calls("reader3")
    assert call["argv"][1:] == ["--index", "smoke_data"]
    assert call["env"]["HF_HUB_OFFLINE"] == "1" and call["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert _r3(call["env"]) == _sandbox_r3(fx)
    assert call["cwd"] == str(fx.sandbox)


@pytest.mark.verify_control_live
def test_wi2_c33_allow_download_runs_without_offline_env(tmp_path):  # WI2-C33
    fv, fx, env = _book_setup(tmp_path)
    fv.script({"index": {"stdout": INDEXED, "stderr": "", "exit": 0}})
    d = _ok(run_cli(["book", "index", "smoke_data", "--allow-download"], env, timeout=15))
    assert d["chunks"] == 7 and d["offline"] is False
    (call,) = fv.calls("reader3")
    assert "HF_HUB_OFFLINE" not in call["env_keys"] and "TRANSFORMERS_OFFLINE" not in call["env_keys"]


@pytest.mark.verify_control_live
def test_wi2_c34_hf_cache_location_precedence(tmp_path):  # WI2-C34
    fv, fx, env = _book_setup(tmp_path)
    fv.script({"index": {"stdout": INDEXED, "stderr": "", "exit": 0}})
    home = tmp_path / "home"
    (home / ".cache" / "huggingface" / "hub" / _model_dir()).mkdir(parents=True)
    env_a = {k: v for k, v in env.items() if k != "HF_HOME"}
    env_a["HOME"] = str(home)
    d = _ok(run_cli(["book", "index", "smoke_data"], env_a, timeout=15))
    assert d["model_cached"] is True and len(fv.calls("reader3")) == 1
    (tmp_path / "hf_empty").mkdir()
    env_b = dict(env_a, HF_HOME=str(tmp_path / "hf_empty"))
    d = _ok(run_cli(["book", "index", "smoke_data"], env_b, timeout=15))
    assert d["skipped"] == "model_not_cached" and len(fv.calls("reader3")) == 1


@pytest.mark.verify_control_live
@pytest.mark.parametrize("extra,cached,allow", list(itertools.product([False, True], repeat=3)))
def test_wi2_c35_exhaustive_decision_table(tmp_path, extra, cached, allow):  # WI2-C35
    fv, fx, env = _book_setup(tmp_path, extra_installed=extra)
    fv.script({"index": {"stdout": INDEXED, "stderr": "", "exit": 0}})
    if cached:
        _cache(tmp_path)
    argv = ["book", "index", "smoke_data"] + (["--allow-download"] if allow else [])
    _ok(run_cli(argv, env, timeout=15))
    spawned = extra and (cached or allow)
    offline = spawned and not allow
    calls = fv.calls("reader3")
    assert len(calls) == int(spawned)
    if spawned:
        for k in OFFLINE_KEYS:
            assert (k in calls[0]["env_keys"]) == offline
    assert len(fv.calls("python")) == 1


@pytest.mark.verify_control_live
@pytest.mark.parametrize("script,needle", [
    ({"stdout": "", "stderr": "smoke_data is held by reader3-server (pid 4242)\n", "exit": 1}, "held by reader3-server"),
    ({"stdout": "", "stderr": "Book not found or not processed: smoke_data (expected /s/books/smoke_data/book.pkl)\n",
      "exit": 1}, "Book not found or not processed"),
    ({"stdout": "Loading\n", "stderr": "", "exit": 0}, "Indexed"),
])
def test_wi2_c36_index_failure_mapping(tmp_path, script, needle):  # WI2-C36
    fv, fx, env = _book_setup(tmp_path)
    _cache(tmp_path)
    fv.script({"index": script})
    e = _err(run_cli(["book", "index", "smoke_data"], env, timeout=15), 1, "index_failed")
    assert needle in e["error"]["message"]
    assert len(fv.calls("reader3")) == 1
    assert e["error"]["try"] == "python3 .claude/skills/verify-reader3/scripts/control.py doctor"


OFFLINE_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "transformers/tokenization_utils_base.py", line 2421, in _patch_mistral_regex\n'
    "huggingface_hub.errors.OfflineModeIsEnabled: Cannot reach https://huggingface.co/api/models/x: "
    "offline mode is enabled. To disable it, please unset the `HF_HUB_OFFLINE` environment variable.\n"
)


@pytest.mark.verify_control_live
@pytest.mark.parametrize("stream", ["stderr", "stdout"])
def test_wi4b_c1_offline_mode_failure_points_at_allow_download(tmp_path, stream):  # WI-4b C1
    fv, fx, env = _book_setup(tmp_path)
    _cache(tmp_path)
    fv.script({"index": {"stdout": "", "stderr": "", stream: OFFLINE_TRACE, "exit": 1}})
    e = _err(run_cli(["book", "index", "smoke_data"], env, timeout=15), 1, "index_failed")
    assert e["error"]["try"] == (
        "python3 .claude/skills/verify-reader3/scripts/control.py book index smoke_data --allow-download"
    )
    first = e["error"]["message"].split("\n", 1)[0]
    assert "offline mode" in first.lower() and "cached" in first.lower()
    assert e["error"]["message"].startswith(first)
    assert len(fv.calls("reader3")) == 1
    assert fv.calls("reader3")[0]["env"]["HF_HUB_OFFLINE"] == "1"


@pytest.mark.verify_control_live
def test_wi4b_c2_offline_error_under_allow_download_keeps_doctor(tmp_path):  # WI-4b C2
    fv, fx, env = _book_setup(tmp_path)
    fv.script({"index": {"stdout": "", "stderr": OFFLINE_TRACE, "exit": 1}})
    e = _err(run_cli(["book", "index", "smoke_data", "--allow-download"], env | {"HF_HUB_OFFLINE": "1"}, timeout=15),
             1, "index_failed")
    assert e["error"]["try"] == "python3 .claude/skills/verify-reader3/scripts/control.py doctor"
    assert "--allow-download" not in e["error"]["try"]


@pytest.mark.verify_control_live
def test_wi2_c37_index_dry_run_spawns_neither_probe_nor_reader3(tmp_path):  # WI2-C37
    fv, fx, env = _book_setup(tmp_path)
    _cache(tmp_path)
    d = _ok(run_cli(["book", "index", "smoke_data", "--dry-run"], env, timeout=15))
    assert d["dry_run"] is True
    assert d["argv"] == [str(fv.bin / "reader3"), "--index", "smoke_data"]
    assert d["env_keys"] == ["HF_HUB_OFFLINE", "READER3_AI_SETTINGS", "READER3_BOOKS_DIR", "TRANSFORMERS_OFFLINE"]
    assert fv.calls("python") == [] and fv.calls("reader3") == []


@pytest.mark.verify_control_live
def test_wi2_c38_book_id_confinement_and_missing_book(tmp_path):  # WI2-C38
    fv, fx, env = _book_setup(tmp_path)
    for bid in ("../x", "a/b", "/abs_data"):
        _err(run_cli(["book", "index", bid], env, timeout=10), 3, "refused_path")
    _err(run_cli(["book", "index", "nope_data"], env, timeout=10), 1, "book_not_found")
    assert fv.calls("python") == [] and fv.calls("reader3") == []


@pytest.mark.verify_control_live
@pytest.mark.parametrize("parent,allow,want", [
    ({"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"}, False, ("1", "1")),
    ({"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"}, True, ("0", "0")),
    ({"HF_HUB_OFFLINE": "0"}, False, ("1", "1")),
])
def test_wi2_c47_offline_env_is_forced_not_defaulted(tmp_path, parent, allow, want):  # WI2-C47
    fv, fx, env = _book_setup(tmp_path)
    _cache(tmp_path)
    fv.script({"index": {"stdout": INDEXED, "stderr": "", "exit": 0}})
    env.update(parent)
    argv = ["book", "index", "smoke_data"] + (["--allow-download"] if allow else [])
    d = _ok(run_cli(argv, env, timeout=15))
    assert d["chunks"] == 7 and d["offline"] is (not allow)
    (call,) = fv.calls("reader3")
    assert call["argv"][1:] == ["--index", "smoke_data"]
    assert (call["env"].get("HF_HUB_OFFLINE"), call["env"].get("TRANSFORMERS_OFFLINE")) == want


# ---------------------------------------------------------------------------
# WI2-C39 to C42: stale seed
# ---------------------------------------------------------------------------

META_KEYS = {"book_id", "status", "chunk_count", "model_name", "space", "indexed_at"}


@pytest.mark.verify_control_live
def test_wi2_c39_importing_vector_search_does_not_import_chromadb():  # WI2-C39
    env = {k: v for k, v in os.environ.items() if k != "READER3_EMBED_MODEL"}
    code = ("import sys, reader3_app.vector_search as v; "
            "print(sorted(m for m in ('chromadb','sentence_transformers','torch') if m in sys.modules))")
    res = subprocess.run([sys.executable, "-c", code], timeout=30, capture_output=True, text=True, env=env,
                         stdin=subprocess.DEVNULL)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "[]"


@pytest.fixture
def no_semantic(monkeypatch):
    monkeypatch.delenv("READER3_EMBED_MODEL", raising=False)
    monkeypatch.setitem(sys.modules, "chromadb", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    return importlib.import_module("reader3_app.vector_search")


def _assert_seed(meta, vs):
    assert set(meta) == META_KEYS
    assert (meta["book_id"], meta["status"], meta["chunk_count"]) == ("smoke_data", "indexed", 1)
    assert meta["model_name"] == "verify-reader3/foreign-model"
    assert meta["space"] == vs.SPACE == "cosine"
    assert datetime.fromisoformat(meta["indexed_at"]).tzinfo is not None
    assert vs.BookVectorIndex._stale_reason(meta) == "model_name"
    assert vs.BookVectorIndex._stale_reason({**meta, "model_name": vs.MODEL_NAME}) is None


def test_wi2_c40_seed_is_exactly_model_name_stale(tmp_path, no_semantic):  # WI2-C40
    book = tmp_path / "books" / "smoke_data"
    book.mkdir(parents=True)
    seed_stale_index(book)
    path = book / "chroma_db" / "index_meta.json"
    assert path.is_file()
    _assert_seed(json.loads(path.read_text()), no_semantic)


def test_wi2_c41_real_status_reports_stale_model_name(tmp_path, no_semantic):  # WI2-C41
    book = tmp_path / "books" / "smoke_data"
    book.mkdir(parents=True)
    seed_stale_index(book)
    s = no_semantic.BookVectorIndex("smoke_data", books_dir=str(tmp_path / "books")).status()
    assert (s["status"], s["stale"], s["stale_reason"]) == ("not_indexed", True, "model_name")
    assert s["indexed_model_name"] == "verify-reader3/foreign-model"
    assert (s["chunk_count"], s["indexed_chunk_count"]) == (0, 1)
    assert s["model_name"] == no_semantic.MODEL_NAME


@pytest.mark.verify_control_live
def test_wi2_c42_up_stale_index_seeds_opt_in_and_needs_corpus(tmp_path, no_semantic):  # WI2-C42
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    try:
        d = _ok(run_cli(["up", "--corpus", "smoke", "--stale-index"], env, timeout=30))
        meta = Path(d["sandbox"]) / "books" / "smoke_data" / "chroma_db" / "index_meta.json"
        _assert_seed(json.loads(meta.read_text()), no_semantic)
    finally:
        run_cli(["down"], env, timeout=30)
    tb = tmp_path / "b"
    fake_venv(tb)
    env_b = base_env(tb)
    try:
        d = _ok(run_cli(["up", "--corpus", "smoke"], env_b, timeout=30))
        assert not (Path(d["sandbox"]) / "books" / "smoke_data" / "chroma_db" / "index_meta.json").exists()
    finally:
        run_cli(["down"], env_b, timeout=30)
    tc = tmp_path / "c"
    fvc = fake_venv(tc)
    r = run_cli(["up", "--stale-index"], base_env(tc), timeout=15)
    assert (r.exit_code, r.envelope["error"]["code"]) == (2, "usage")
    assert fvc.calls("reader3-server") == [] and fvc.calls("reader3") == []
    assert fv.calls("reader3-server")


# ---------------------------------------------------------------------------
# WI-9: review follow-ups (finding M4, untested error codes)
# ---------------------------------------------------------------------------


@pytest.mark.verify_control_live
def test_wi9_1_fs_ls_on_a_regular_file_is_not_a_directory(tmp_path):  # WI-9 / M4
    """Review finding M4: `fs ls` on a regular file must report `not_a_directory` (fs_view.py)."""
    fx = write_state(tmp_path)
    (fx.sandbox / "notes.txt").write_text("plain file", encoding="utf-8")
    r = run_cli(["fs", "ls", "notes.txt"], fx.env, timeout=15)
    e = _err(r, 1, "not_a_directory")
    assert isinstance(e["error"]["try"], str) and e["error"]["try"].strip()
    assert "notes.txt" in e["error"]["message"] and "not a directory" in e["error"]["message"]
    assert e["data"] is None
    assert (fx.sandbox / "notes.txt").read_text(encoding="utf-8") == "plain file"


_GARBAGE_SERVER = r'''
import os, signal, socket, sys

signal.alarm(120)
port_file = sys.argv[1]
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(4)
tmp = port_file + ".tmp"
with open(tmp, "w") as f:
    f.write(str(srv.getsockname()[1]))
os.replace(tmp, port_file)
while True:
    conn, _ = srv.accept()
    conn.settimeout(10)
    buf = b""
    try:
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        conn.sendall(b"garbage\r\n")
    except OSError:
        pass
    finally:
        conn.close()
'''


def _garbage_server(tmp_path):
    """A child that answers every request with `garbage\\r\\n` (not an HTTP status line), then closes."""
    script = tmp_path / "garbage_server.py"
    script.write_text(_GARBAGE_SERVER, encoding="utf-8")
    port_file = tmp_path / "garbage_port"
    proc = spawn([sys.executable, script, port_file], tmp_path)
    assert wait_until(lambda: port_file.exists() or proc.poll() is not None, timeout=10)
    assert proc.poll() is None, f"garbage server exited {proc.returncode}"
    return proc, int(port_file.read_text())


@pytest.mark.verify_control_live
def test_wi9_2_api_malformed_http_response_is_bad_response(tmp_path):  # WI-9 / M4
    """Review finding M4: a listener that answers with a non-HTTP status line yields `bad_response` (cmd_api.py)."""
    proc, port = _garbage_server(tmp_path)
    try:
        fx = write_state(tmp_path, base_url=f"http://127.0.0.1:{port}")
        r = run_cli(["api", "GET", "/api/library"], fx.env, timeout=15)
        e = _err(r, 1, "bad_response")
        assert isinstance(e["error"]["try"], str) and e["error"]["try"].strip()
        msg = e["error"]["message"]
        assert "malformed" in msg and f"127.0.0.1:{port}/api/library" in msg
        assert e["data"] is None
    finally:
        proc.kill()
        proc.wait(5)
