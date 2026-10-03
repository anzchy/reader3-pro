"""WI-3 cases for the verify-reader3 control CLI: `sse`, the stub runner, `up --ai-stub`, `ai ask`.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-2-3.md`, its addendum and the round 2
file (precedence: round 2 > index > addendum > part file). Each test carries its case id.
This module also holds the `ai ask` halves of WI2-C43, WI2-C44, WI2-C46 (part B) and WI2-C49.

Socket rule: the test process never connects. Every network case runs the CLI via `run_cli`;
the fake SSE server, the stub runner and every client are bounded child processes.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from verify_control_fakes_sse import (  # noqa: F401 (autouse fixture imported for effect)
    CHAT_CLIENT,
    DELTAS,
    DONE,
    FULL_TEXT,
    GET_CLIENT,
    META,
    RUNNER_PY,
    child_client,
    child_client_popen,
    fake_sse_server,
    pid_recording_stub_module,
    sse_frame,
    stop_fake_sse,
)
from verify_control_support import (  # noqa: F401 (autouse fixtures imported for effect)
    CONTROL_PY,
    EPOCH_LSTART,
    FIXED_UUID,
    alive,
    base_env,
    fake_venv,
    lstart,
    pointer,
    real_evidence_untouched,
    reap_fakes,
    register_pid,
    rewrite_state,
    run_cli,
    snapshot_tree,
    spawn,
    wait_dead,
    wait_until,
    write_instance,
    write_state,
)
from verify_control.ai_stub_runner import GATE_ARM_FILE, GATE_RELEASE_FILE, READY_FILE, STATS_FILE
from verify_control.sse import SSEParser
from reader3_app.web.routers.ai import chat

TOKEN = "tok-SECRET-9"
FULL_EVENTS = ["meta", "chunk", "chunk", "chunk", "chunk", "done"]
PARTIAL = "".join(DELTAS[:-1])
TARGET = f"/api/ai/question/{FIXED_UUID}?stream=true"


def _err(r, exit_code, code):
    e = r.envelope
    assert (r.exit_code, e["ok"], e["error"]["code"]) == (exit_code, False, code), (e, r.stderr)
    assert e["error"]["try"].startswith("python3 "), e
    return e


def _ok(r):
    e = r.envelope
    assert r.exit_code == 0 and e["ok"] is True, (e, r.stderr)
    return e["data"]


def _ask(fx, *args, timeout=30):
    return run_cli(["ai", "ask", *args], fx.env, timeout=timeout)


def _setup(tmp_path, *, stub=True, token=None, ipc=None, **kw):
    """write_state first (creates the sandbox), then the fake on `<sandbox>/ai_stub`, then point state at it."""
    fx = write_state(tmp_path, token=token)
    fake = fake_sse_server(tmp_path, fx.stub_dir, ipc=stub if ipc is None else ipc, **kw)
    changes = {"base_url": fake.base_url, "port": fake.port}
    if stub:
        fx.stub_dir.mkdir(exist_ok=True)
        changes.update(stub_pid=fake.pid, stub_pid_start=lstart(fake.pid), stub_port=fake.port)
    rewrite_state(fx.state_path, **changes)
    return fx, fake


def _ipc_files(fx):
    return [n for n in (GATE_ARM_FILE, GATE_RELEASE_FILE) if (fx.stub_dir / n).exists()]


def _hdrs(req, name):
    return [v for k, v in req["headers"] if k == name]


def _absent(r, text):
    assert text not in r.stdout and text not in r.stderr


# ---------------------------------------------------------------------------
# WI3-C01 to C06: the SSE parser
# ---------------------------------------------------------------------------


def _parse(pieces, close=True):
    p = SSEParser()
    out = [x for piece in pieces for x in p.feed(piece)]
    return out + (p.close() if close else [])


def test_wi3_c01_full_real_format_stream_in_one_feed():  # WI3-C01
    frames = [("meta", META)] + [("chunk", {"delta": d}) for d in DELTAS] + [("done", DONE)]
    blob = b"".join(chat._sse_event(e, d) for e, d in frames)
    assert _parse([blob]) == frames


@pytest.mark.parametrize(
    "raw, expected",
    [
        (b'event: x\ndata: {"a":\ndata: 1}\n\n', [("x", {"a": 1})]),  # (a)
        (b'event:y\ndata:{"b":2}\n\n', [("y", {"b": 2})]),  # (b)
        (b": keep-alive\n\nevent: z\ndata: 3\n\n", [("z", 3)]),  # (c)
        (b"event: w\r\ndata: 4\r\n\r\n", [("w", 4)]),  # (d)
        (b"data: 5\n\n", [("message", 5)]),  # (e)
    ],
    ids=["a-multiline", "b-nospace", "c-comment", "d-crlf", "e-noevent"],
)
def test_wi3_c02_sse_grammar_edges(raw, expected):  # WI3-C02
    assert _parse([raw]) == expected


def test_wi3_c03_cjk_frame_split_at_every_byte_offset():  # WI3-C03
    f = chat._sse_event("chunk", {"delta": "是第一章的"})
    for k in range(1, len(f)):
        assert _parse([f[:k], f[k:]]) == [("chunk", {"delta": "是第一章的"})], k


def test_wi3_c04_trailing_frame_and_non_json():  # WI3-C04
    p = SSEParser()
    assert p.feed(b'event: done\ndata: {"model":"m"}') == []  # (a)
    assert p.close() == [("done", {"model": "m"})]
    assert SSEParser().feed(b"event: chunk\ndata: not-json\n\n") == [("chunk", "not-json")]  # (b)
    assert SSEParser().feed(b'event: chunk\ndata: {"delta":"a"}\n') == []  # (c)


_json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=20),
    lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=5), c, max_size=3),
    max_leaves=8,
)
_events = st.lists(st.tuples(st.from_regex(r"[a-z_]{1,12}", fullmatch=True), _json_values), max_size=8)


def _cut(blob, points):
    pts = [0] + sorted(points) + [len(blob)]
    return [blob[a:b] for a, b in zip(pts, pts[1:])]


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data(), events=_events)
def test_wi3_c05_round_trip_under_arbitrary_chunking(data, events):  # WI3-C05 (S5 + S6)
    blob = b"".join(chat._sse_event(e, d) for e, d in events)
    cuts = st.lists(st.integers(0, len(blob)), max_size=10)
    one = _parse(_cut(blob, data.draw(cuts)))
    two = _parse(_cut(blob, data.draw(cuts)))
    assert one == [tuple(x) for x in events]
    assert one == two


@settings(max_examples=150, deadline=None)
@given(event=st.from_regex(r"[a-z_]{1,12}", fullmatch=True), value=_json_values)
def test_wi3_c06_fake_encoder_equals_real_sse_event(event, value):  # WI3-C06
    assert sse_frame(event, value) == chat._sse_event(event, value)


def test_wi3_c27b_comment_lines_are_ignored_across_feeds():  # WI3-C27 (b)
    m = chat._sse_event("meta", META)
    ch = chat._sse_event("chunk", {"delta": "a"})
    p = SSEParser()
    assert p.feed(b": ka\n\n" * 3) == [] and p.close() == []
    want = [("meta", META), ("chunk", {"delta": "a"})]
    assert _parse([m + b": ka\n\n" + b": ka\n\n" + ch]) == want
    assert _parse([m[:7], m[7:] + b": k", b"a\n\n" + ch]) == want


# ---------------------------------------------------------------------------
# WI3-C07 to C09: the stub runner (real frozen OllamaStub, separate process)
# ---------------------------------------------------------------------------


def _read_json_retry(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            time.sleep(0.05)
    pytest.fail(f"{path} never became readable JSON within {timeout}s")


@pytest.fixture
def runner(tmp_path):
    d = tmp_path / "ai_stub"
    d.mkdir()
    log = open(tmp_path / "runner.stderr", "wb")
    proc = subprocess.Popen(
        [sys.executable, str(RUNNER_PY), "--state-dir", str(d), "--gate"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
    )
    log.close()
    register_pid(proc.pid, tmp_path, "ai_stub_runner.py")
    ok = wait_until(lambda: (d / READY_FILE).exists() or proc.poll() is not None, timeout=10)
    try:
        assert ok and proc.poll() is None, (tmp_path / "runner.stderr").read_text(errors="replace")
        yield proc, d, _read_json_retry(d / READY_FILE)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)


def _stats(d):
    return _read_json_retry(d / STATS_FILE)


def test_wi3_c07_runner_lifecycle(runner):  # WI3-C07
    proc, d, ready = runner
    assert set(ready) == {"port", "pid"} and ready["pid"] == proc.pid
    assert isinstance(ready["port"], int) and ready["port"] > 0
    client = child_client_popen(CHAT_CLIENT, ready["port"])
    try:
        assert wait_until(lambda: _stats(d)["request_count"] == 1, timeout=5)
        assert client.poll() is None
        (d / GATE_RELEASE_FILE).touch()
        out, err = client.communicate(timeout=5)
        assert wait_until(lambda: not (d / GATE_RELEASE_FILE).exists(), timeout=1)
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(5)
    lines = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    assert "".join(ln["message"]["content"] for ln in lines if "message" in ln) == "".join(DELTAS), err
    assert lines[-1]["done"] is True
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=5) == 0
    assert _stats(d) == {
        "request_count": 1, "completed": True, "gate_released_by_render": True,
        "gate_timed_out": False, "payloads": 1, "gate_set": True,
    }


def test_wi3_c08_gate_ipc_register_law(runner):  # WI3-C08
    _, d, _ = runner
    assert _stats(d)["gate_set"] is False
    steps = [(GATE_RELEASE_FILE, True), (GATE_RELEASE_FILE, True), (GATE_ARM_FILE, False),
             (GATE_ARM_FILE, False), (GATE_RELEASE_FILE, True)]
    for name, want in steps:
        (d / name).touch()
        assert wait_until(lambda: not (d / name).exists() and _stats(d)["gate_set"] is want, timeout=1), (name, want)


def test_wi3_c09_sigterm_while_request_held(runner):  # WI3-C09
    proc, d, ready = runner
    client = child_client_popen(CHAT_CLIENT, ready["port"])
    try:
        assert wait_until(lambda: _stats(d)["request_count"] == 1, timeout=5)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=5) == 0
        s = _stats(d)
        assert (s["request_count"], s["completed"], s["gate_released_by_render"]) == (1, False, False)
        client.wait(timeout=5)
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(5)


# ---------------------------------------------------------------------------
# WI3-C10 to C13, C28, C30: `up --ai-stub` and `down`
# ---------------------------------------------------------------------------


def _sandboxes(env):
    return sorted(p for p in os.listdir(env["TMPDIR"]) if p.startswith("verify-reader3."))


def _up_stub(tmp_path, env):
    old = os.umask(0)
    try:
        r = run_cli(["up", "--corpus", "smoke", "--ai-stub"], env, timeout=30)
    finally:
        os.umask(old)
    d = _ok(r)
    if d.get("stub_pid"):
        register_pid(d["stub_pid"], tmp_path, "ai_stub_runner.py")
    return d


def test_wi3_c10_up_ai_stub_settings_and_live_stub(tmp_path):  # WI3-C10
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up_stub(tmp_path, env)
    try:
        sbx = d["sandbox"]
        s = json.loads(Path(d["state"]).read_text(encoding="utf-8"))
        port = s["stub_port"]
        settings_path = Path(sbx) / "ai_settings.json"
        assert json.loads(settings_path.read_text(encoding="utf-8")) == {
            "default_provider": "ollama",
            "preferences": {"streaming_enabled": True},
            "providers": {"ollama": {"enabled": True, "base_url": f"http://127.0.0.1:{port}",
                                     "model_name": "stub-model", "timeout_s": 10, "max_retries": 0}},
        }
        assert stat.S_IMODE(os.stat(settings_path).st_mode) == 0o600
        assert json.loads((Path(sbx) / "ai_stub" / READY_FILE).read_text())["port"] == port
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(s["stub_pid"])],
                             capture_output=True, text=True, timeout=10).stdout
        assert "ai_stub_runner.py" in cmd
        assert s["stub_pid_start"] == lstart(s["stub_pid"])
        g = child_client(GET_CLIENT, port, "/x", timeout=10)
        assert g.stdout.splitlines()[0] == "404" and "stub only serves POST /api/chat" in g.stdout
        srv = fv.calls("reader3-server")[0]
        assert srv["env"]["READER3_AI_SETTINGS"] == str(settings_path)
        assert srv["settings_existed_at_start"] is True
    finally:
        run_cli(["down"], env)


def test_wi3_c11_down_kills_server_and_stub(tmp_path):  # WI3-C11
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up_stub(tmp_path, env)
    s = json.loads(Path(d["state"]).read_text(encoding="utf-8"))
    assert s["stub_pid"] and alive(s["stub_pid"])
    _ok(run_cli(["down"], env, timeout=30))
    assert wait_dead(s["pid"], 10) and wait_dead(s["stub_pid"], 10)
    assert not os.path.exists(d["sandbox"])


def test_wi3_c12_down_refuses_foreign_stub_pid(tmp_path):  # WI3-C12
    env = base_env(tmp_path)
    sleeper = spawn(["sleep", "60"], tmp_path)
    t = subprocess.Popen(["true"])
    t.wait(5)
    write_instance(env, pid=t.pid, pid_start=EPOCH_LSTART, port=9, stub_pid=sleeper.pid)
    r = run_cli(["down"], env, timeout=30)
    _err(r, 3, "refused_pid_identity")
    assert sleeper.poll() is None


def test_wi3_c13_runner_fails_to_start(tmp_path):  # WI3-C13
    fv = fake_venv(tmp_path)
    bad = tmp_path / "bad_stub.py"
    bad.write_text('raise ImportError("boom-stub-import")\n', encoding="utf-8")
    env = base_env(tmp_path) | {"VERIFY_READER3_STUB_MODULE": str(bad)}
    r = run_cli(["up", "--corpus", "smoke", "--ai-stub"], env, timeout=30)
    e = _err(r, 1, "stub_failed")
    assert "boom-stub-import" in e["error"]["message"]
    assert r.elapsed_s < 15
    assert fv.calls("reader3-server") == []
    assert not pointer(env).exists()
    pat = f"ai_stub_runner.py --state-dir {os.path.realpath(env['TMPDIR'])}"
    assert subprocess.run(["pgrep", "-f", pat], capture_output=True, timeout=10).returncode == 1
    assert _sandboxes(env) == []


def _assert_runner_gone(rec, env):
    R = rec.record()
    assert R is not None, "the runner never imported the stub module"
    assert wait_until(lambda: lstart(R["pid"]) != R["lstart"], timeout=10, step=0.1)
    D = R["argv"][R["argv"].index("--state-dir") + 1]
    assert subprocess.run(["pgrep", "-f", D], capture_output=True, timeout=10).returncode == 1
    assert not os.path.exists(os.path.dirname(D))
    assert _sandboxes(env) == []
    assert not pointer(env).exists()
    return R


def _kill_recorded(rec):
    R = rec.record()
    if R and lstart(R["pid"]) == R["lstart"]:
        try:
            os.kill(R["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.mark.parametrize("server", ["exit", "hang"])
def test_wi3_c28_runner_not_orphaned_when_server_fails(tmp_path, server):  # WI3-C28 (a) exit, (b) hang
    rec = pid_recording_stub_module(tmp_path)
    fv = fake_venv(tmp_path, server=server)
    env = base_env(tmp_path) | {"VERIFY_READER3_STUB_MODULE": str(rec.module_path)}
    if server == "hang":
        env |= {"VERIFY_READER3_HEALTH_TIMEOUT_S": "2", "VERIFY_READER3_KILL_GRACE_S": "1"}
    try:
        r = run_cli(["up", "--corpus", "smoke", "--ai-stub"], env, timeout=30)
        if server == "exit":
            e = _err(r, 1, "server_exited")
            assert "FAKE-STARTUP-BOOM" in e["error"]["message"]
        else:
            _err(r, 1, "startup_timeout")
        assert r.elapsed_s < 15
        _assert_runner_gone(rec, env)
        srv = fv.calls("reader3-server")
        assert srv and srv[0]["settings_existed_at_start"] is True
        assert wait_dead(srv[0]["pid"], 5)
    finally:
        _kill_recorded(rec)


@pytest.mark.parametrize("variant", ["timeout", "sigterm"])
def test_wi3_c30_runner_never_ready_is_not_orphaned(tmp_path, variant):  # WI3-C30 (a) timeout, (b) SIGTERM
    rec = pid_recording_stub_module(tmp_path, hang=True)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path) | {
        "VERIFY_READER3_STUB_MODULE": str(rec.module_path),
        "VERIFY_READER3_STUB_READY_TIMEOUT_S": "2" if variant == "timeout" else "20",
        "VERIFY_READER3_KILL_GRACE_S": "1",
    }
    try:
        if variant == "timeout":
            r = run_cli(["up", "--corpus", "smoke", "--ai-stub"], env, timeout=30)
            _err(r, 1, "stub_failed")
            assert r.elapsed_s < 15
        else:
            proc = subprocess.Popen(
                [sys.executable, str(CONTROL_PY), "up", "--corpus", "smoke", "--ai-stub"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=env["TMPDIR"], start_new_session=True, text=True,
            )
            register_pid(proc.pid, tmp_path, "control.py")
            try:
                assert wait_until(lambda: rec.record() is not None, timeout=15)
                proc.send_signal(signal.SIGTERM)
                out, err = proc.communicate(timeout=15)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
            e = json.loads(out)
            assert (proc.returncode, e["error"]["code"]) == (1, "interrupted"), (e, err)
        _assert_runner_gone(rec, env)
        assert fv.calls("reader3-server") == []
    finally:
        _kill_recorded(rec)


# ---------------------------------------------------------------------------
# WI3-C14 to C29: `ai ask`
# ---------------------------------------------------------------------------


def test_wi3_c14_concurrency_two_ungated(tmp_path):  # WI3-C14 (amended)
    fx, fake = _setup(tmp_path, mode="stream", chunk_delay_s=0.2)
    d = _ok(_ask(fx, "Who is Alpha?", "--book", "smoke_data", "--concurrency", "2"))
    assert d["book_uuid"] == FIXED_UUID and len(d["results"]) == 2
    for res in d["results"]:
        assert (res["status"], res["events"], res["text"], res["errors"]) == (200, FULL_EVENTS, FULL_TEXT, [])
    assert d["stub_stats"]["request_count"] == 2
    reqs, s = fake.requests(), fake.summary()
    assert len(reqs) == 2
    for q in reqs:
        assert q["target"] == TARGET
        body = json.loads(q["body"])
        assert body["question"] == "Who is Alpha?" and body["provider"] == "ollama"
        assert _hdrs(q, "origin") == [] and q["held"] is False and q["gate_set_at_accept"] is True
    assert s["max_concurrent"] == 2
    assert (s["release_seen_count"], s["arm_seen_count"]) == (1, 0)
    assert s["release_seen_at"] < min(q["t_accept"] for q in reqs)


@pytest.mark.parametrize("n", [1, 3, 4])
def test_wi3_c15_conservation_across_n(tmp_path, n):  # WI3-C15 (amended)
    fx, fake = _setup(tmp_path, mode="stream")
    d = _ok(_ask(fx, "q", "--book", "smoke_data", "--concurrency", str(n)))
    assert len(d["results"]) == n
    assert sorted(r["index"] for r in d["results"]) == list(range(n))
    assert all(r["text"] == FULL_TEXT for r in d["results"])
    assert d["stub_stats"]["request_count"] == n
    assert len(fake.requests()) == n


@pytest.mark.parametrize("delay", [1.0, 2.5])
def test_wi3_c16_release_after_every_first_delta(tmp_path, delay):  # WI3-C16 (amended)
    fx, fake = _setup(tmp_path, mode="gate", gate_timeout_s=5, first_chunk_delay_s={1: delay})
    d = _ok(_ask(fx, "q", "--book", "smoke_data", "--concurrency", "2", "--gate", "release-after-first-delta"))
    assert {k: d["gate"][k] for k in ("mode", "released")} == {"mode": "release-after-first-delta", "released": True}
    for res in d["results"]:
        assert res["events"] == FULL_EVENTS and res["text"] == FULL_TEXT
    S, reqs = fake.summary(), fake.requests()
    assert (S["arm_seen_count"], S["release_seen_count"]) == (1, 1)
    assert all(q["arm_seen_before_accept"] is True and q["gate_set_at_accept"] is False for q in reqs)
    assert S["release_seen_at"] is not None
    assert S["streams_holding_at_release"] == 2
    assert all(q["t_first_chunk"] < S["release_seen_at"] for q in reqs)
    r1 = next(q for q in reqs if q["index"] == 1)
    assert S["release_seen_at"] - r1["t_accept"] >= delay - 0.1
    assert S["release_seen_at"] - max(q["t_first_chunk"] for q in reqs) < 0.5


def test_wi3_c17_gate_hold_never_released(tmp_path):  # WI3-C17
    fx, fake = _setup(tmp_path, mode="gate", gate_timeout_s=1.5, split_frames=True)
    d = _ok(_ask(fx, "q", "--book", "smoke_data", "--concurrency", "2", "--gate", "hold"))
    assert d["gate"]["released"] is False
    for res in d["results"]:
        assert res["events"] == ["meta", "chunk", "chunk", "chunk", "done"] and res["text"] == PARTIAL
    assert fake.summary()["release_seen_at"] is None
    assert not (fx.stub_dir / GATE_RELEASE_FILE).exists()


def test_wi3_c18_timeout_partial_results_bounded_exit(tmp_path):  # WI3-C18
    fx, _ = _setup(tmp_path, mode="hang")
    r = _ask(fx, "q", "--book", "smoke_data", "--concurrency", "2", "--timeout", "2", timeout=10)
    e = _err(r, 1, "ai_timeout")
    assert len(e["data"]["results"]) == 2
    for res in e["data"]["results"]:
        assert res["events"] == ["meta", "chunk"] and res["text"] == "Alpha "
    assert r.elapsed_s < 6


@pytest.mark.parametrize("mode", ["error", "http404", "badjson"])
def test_wi3_c19_error_event_http_error_bad_chunk(tmp_path, mode):  # WI3-C19 (a) error, (b) http404, (c) badjson
    fx, fake = _setup(tmp_path, mode=mode)
    e = _err(_ask(fx, "q", "--book", "smoke_data"), 1, "ai_failed")
    res = e["data"]["results"][0]
    if mode == "error":
        assert res["events"] == ["meta", "error"] and res["errors"] == ["AI request timed out"]
    elif mode == "http404":
        assert res["status"] == 404 and "Book not found" in res["errors"][0]
    else:
        assert any("chunk" in x for x in res["errors"]), res
    assert len(fake.requests()) == 1


def test_wi3_c20_dry_run_sends_nothing_touches_no_ipc(tmp_path):  # WI3-C20 (amended)
    fx, fake = _setup(tmp_path, mode="gate")
    S0 = fake.summary()
    m0 = fake.stats_path.stat().st_mtime_ns
    d = _ok(_ask(fx, "q", "--book", "smoke_data", "--concurrency", "2", "--gate", "hold", "--dry-run"))
    assert d["dry_run"] is True
    req = {"method": "POST", "url": f"{fake.base_url}{TARGET}", "body": {"question": "q", "provider": "ollama"}}
    assert d["requests"] == [req] * 2
    assert fake.requests() == []
    assert fake.stats()["request_count"] == 0 and fake.stats_path.stat().st_mtime_ns == m0
    assert (S0["arm_seen_count"], S0["release_seen_count"]) == (0, 0)
    S1 = fake.summary()
    assert (S1["arm_seen_count"], S1["release_seen_count"]) == (0, 0)
    (fx.stub_dir / GATE_RELEASE_FILE).touch()  # positive control: the observer counts a late write
    assert wait_until(lambda: fake.summary()["release_seen_count"] == 1, timeout=1)


@pytest.mark.parametrize("book", ["../x", "a/b", "/abs", "evil_data"])
def test_wi3_c21_book_confinement(tmp_path, book):  # WI3-C21
    fx, fake = _setup(tmp_path, mode="stream")
    outside = tmp_path / "outside" / "evil_book"
    outside.mkdir(parents=True)
    os.mkfifo(outside / "ai_meta.json")
    (fx.books_dir / "evil_data").symlink_to(outside)
    r = _ask(fx, "q", "--book", book, timeout=10)
    _err(r, 3, "refused_path")
    assert fake.requests() == [] and _ipc_files(fx) == []


@pytest.mark.parametrize("variant", ["deleted", "traversal", "not_json", "int"])
def test_wi3_c22_missing_or_invalid_book_uuid(tmp_path, variant):  # WI3-C22 (a)-(d)
    fx, fake = _setup(tmp_path, mode="stream")
    meta = fx.books_dir / "smoke_data" / "ai_meta.json"
    content = {
        "traversal": json.dumps({"book_uuid": "../../api/settings?x="}),
        "not_json": "not json",
        "int": json.dumps({"book_uuid": 7}),
    }
    if variant == "deleted":
        meta.unlink()
    else:
        meta.write_text(content[variant], encoding="utf-8")
    before = None if variant == "deleted" else meta.read_bytes()
    e = _err(_ask(fx, "q", "--book", "smoke_data", timeout=10), 1, "no_book_uuid")
    assert "control.py" in e["error"]["try"]
    assert fake.requests() == []
    if variant == "deleted":
        assert not meta.exists()
    else:
        assert meta.read_bytes() == before


def test_wi3_c23_gate_without_stub_and_plain_ask_without_stub(tmp_path):  # WI3-C23
    fx, fake = _setup(tmp_path, stub=False, mode="stream")
    _err(_ask(fx, "q", "--book", "smoke_data", "--gate", "hold"), 1, "no_stub")  # (a)
    assert fake.requests() == []
    d = _ok(_ask(fx, "q", "--book", "smoke_data"))  # (b)
    assert d["stub_stats"] is None and len(d["results"]) == 1 and d["results"][0]["text"] == FULL_TEXT
    assert len(fake.requests()) == 1
    assert not fx.stub_dir.exists()


def test_wi3_c24_stub_that_does_not_consume_arm(tmp_path):  # WI3-C24
    fx, fake = _setup(tmp_path, mode="stream", ipc=False)
    r = _ask(fx, "q", "--book", "smoke_data", "--gate", "hold", timeout=10)
    _err(r, 1, "stub_unresponsive")
    assert r.elapsed_s < 5
    assert fake.requests() == []


@pytest.mark.parametrize("n", [0, 9, 8])
def test_wi3_c25_concurrency_bounds(tmp_path, n):  # WI3-C25
    fx, fake = _setup(tmp_path, mode="stream")
    r = _ask(fx, "q", "--book", "smoke_data", "--concurrency", str(n))
    if n == 8:
        assert len(_ok(r)["results"]) == 8 and len(fake.requests()) == 8
    else:
        _err(r, 2, "usage")
        assert fake.requests() == []


@pytest.mark.parametrize("style", ["clean", "abort"])
def test_wi3_c26_stream_without_done_is_failure(tmp_path, style):  # WI3-C26
    fx, fake = _setup(tmp_path, stub=False, mode="truncated", truncate_style=style)
    e = _err(_ask(fx, "q", "--book", "smoke_data", timeout=15), 1, "ai_failed")
    assert "done" in e["error"]["message"]
    res = e["data"]["results"]
    assert len(res) == 1
    assert (res[0]["events"], res[0]["text"], res[0]["status"]) == (["meta", "chunk"], "Alpha ", 200)
    assert any("done" in x for x in res[0]["errors"])
    assert len(fake.requests()) == 1


def test_wi3_c27a_timeout_is_an_overall_deadline(tmp_path):  # WI3-C27 (a)
    fx, fake = _setup(tmp_path, mode="trickle", trickle_interval_s=0.5)
    r = _ask(fx, "q", "--book", "smoke_data", "--concurrency", "2", "--timeout", "2", timeout=10)
    e = _err(r, 1, "ai_timeout")
    assert r.elapsed_s < 6
    res = e["data"]["results"]
    assert len(res) == 2
    for x in res:
        assert x["events"] == ["meta"] and x["text"] == ""
        assert not any(ev in ("", ":", "ka") for ev in x["events"])
    assert len(fake.requests()) == 2


@pytest.mark.parametrize("n", [3, 4, 8])
def test_wi3_c29_concurrency_really_is_n(tmp_path, n):  # WI3-C29
    fx, fake = _setup(tmp_path, mode="stream", chunk_delay_s=0.2)
    r = _ask(fx, "q", "--book", "smoke_data", "--concurrency", str(n))
    d = _ok(r)
    assert len(d["results"]) == n and all(x["text"] == FULL_TEXT for x in d["results"])
    assert r.elapsed_s < 2 * 1.2 + 3
    reqs = fake.requests()
    assert fake.summary()["max_concurrent"] == n and len(reqs) == n
    assert max(q["t_accept"] for q in reqs) < min(q["t_end"] for q in reqs)


# ---------------------------------------------------------------------------
# WI2-C43, C44, C46 (part B), C49: the `ai ask` halves
# ---------------------------------------------------------------------------


def test_wi2_c43_ai_ask_tampered_base_url_refused(tmp_path):  # WI2-C43 (round 2; ai ask half)
    fx, rec = _setup(tmp_path, stub=False, mode="stream")
    evil = fake_sse_server(tmp_path, tmp_path / "evilstub", ipc=False)
    p = evil.port
    tampers = [
        (f"http://localhost.evil:{p}", p), ("http://10.0.0.5:1", 1), ("https://127.0.0.1:1", 1),
        (f"http://u@127.0.0.1:{p}", p), (f"http://127.0.0.1:{p}/pfx", p), (f"http://localhost:{p}", p),
        ("http://127.0.0.1", 80), (f"http://127.0.0.1:{p}?q=1", p),
    ]
    for url, port in tampers:
        rewrite_state(fx.state_path, base_url=url, port=port)
        r = _ask(fx, "q", "--book", "smoke_data", timeout=10)
        _err(r, 3, "refused_url")
        assert r.elapsed_s < 5, url
    assert evil.requests() == [] and rec.requests() == []
    rewrite_state(fx.state_path, base_url=evil.base_url, port=evil.port)
    _ok(_ask(fx, "q", "--book", "smoke_data", timeout=10))
    assert [q["target"] for q in evil.requests()] == [TARGET]


def test_wi2_c44_ai_ask_tampered_sandbox_refused(tmp_path):  # WI2-C44 (round 2; ai ask half)
    fx, rec = _setup(tmp_path, stub=False, mode="stream")
    link = tmp_path / "verify-reader3.link"
    link.symlink_to(tmp_path)
    before = snapshot_tree(fx.books_dir)
    for sval in (str(tmp_path), "/", str(link)):
        rewrite_state(fx.state_path, sandbox=sval)
        _err(_ask(fx, "q", "--book", "smoke_data", timeout=10), 3, "refused_sandbox_shape")
    assert rec.requests() == []
    assert snapshot_tree(fx.books_dir) == before


@pytest.mark.parametrize("variant", ["b1", "b2", "b3", "b4"])
def test_wi2_c46_token_sent_and_never_leaked_by_ai_ask(tmp_path, variant):  # WI2-C46 part B
    mode = {"b1": "stream", "b2": "hang", "b3": "http404", "b4": "stream"}[variant]
    fx, fake = _setup(tmp_path, stub=False, token=TOKEN, mode=mode)
    args = {"b1": [], "b2": ["--timeout", "2"], "b3": [], "b4": ["--dry-run"]}[variant]
    r = _ask(fx, "q", "--book", "smoke_data", *args, timeout=10)
    _absent(r, TOKEN)
    reqs = fake.requests()
    if variant == "b1":
        _ok(r)
        assert len(reqs) == 1
    elif variant == "b2":
        _err(r, 1, "ai_timeout")
    elif variant == "b3":
        _err(r, 1, "ai_failed")
    else:
        assert _ok(r)["dry_run"] is True
        assert reqs == []
    for q in reqs:
        assert _hdrs(q, "x-reader3-token") == [TOKEN]
    if variant in ("b2", "b3"):
        assert reqs


def test_wi2_c49_proxy_env_has_no_effect_on_ai_ask(tmp_path):  # WI2-C49 (ai ask half)
    fx, fake = _setup(tmp_path, stub=False, token=TOKEN, mode="stream")
    evil = fake_sse_server(tmp_path, tmp_path / "evilstub", ipc=False)
    env = dict(fx.env)
    for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env[k] = evil.base_url
    env["NO_PROXY"] = env["no_proxy"] = ""
    _ok(run_cli(["ai", "ask", "q", "--book", "smoke_data"], env, timeout=15))
    assert evil.requests() == []
    assert len(fake.requests()) == 1
