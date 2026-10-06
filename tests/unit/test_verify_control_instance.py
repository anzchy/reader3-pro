"""WI-1 instance cases (`up`, `doctor`, `down`) for the verify-reader3 control CLI.

Matrix: `.claude/tdd-guardian/tests-20261002-170349-WI-1.md`, its addendum and the
round 2 file. Each test name or comment carries its case id (WI1-Cnn).

Every CLI run uses `base_env(tmp_path)`: sandboxes land in `tmp_path/tmp`, the pointer in
`tmp_path/evidence`. The venv executables are fakes except in WI1-C66, the one real start.
"""

from __future__ import annotations

import glob
import hashlib
import itertools
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from verify_control_support import (  # noqa: F401 (autouse fixtures are imported for effect)
    CONTROL_PY,
    CONTROL_REL,
    REPO,
    TRY_PREFIX,
    alive,
    base_env,
    fake_browse,
    fake_repo,
    fake_venv,
    free_port,
    lstart,
    make_stub_script,
    pointer,
    listener_pids,
    port_bindable,
    real_evidence_untouched,
    reap_fakes,
    register_pid,
    rewrite_state,
    run_cli,
    snapshot_tree,
    spawn,
    wait_dead,
    wait_listening,
    wait_until,
    write_instance,
)
from verify_control import http_client, state

# Every case here spawns a child process: the verify-control lane, not the unit lane.
pytestmark = pytest.mark.verify_control_live

EPOCH = "Thu Jan  1 00:00:00 1970"
FIXTURES = REPO / "tests" / "fixtures"
MODEL_DIR = "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"


def _build_epub2(path):
    if str(FIXTURES) not in sys.path:
        sys.path.insert(0, str(FIXTURES))
    from epub_corpus import build_epub2

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return Path(build_epub2(path))


def _up(env, *args, script=CONTROL_PY, cwd=None, timeout=30):
    code, e, err = run_cli(["up", *args], env, timeout, script=script, cwd=cwd)
    assert code == 0 and e["ok"] is True, (e, err)
    return e["data"]


def _sandboxes(env):
    return sorted(p for p in os.listdir(env["TMPDIR"]) if p.startswith("verify-reader3."))


def _evidence(env):
    return sorted(os.listdir(env["VERIFY_READER3_EVIDENCE_ROOT"]))


def _ptr_bytes(env):
    return pointer(env).read_bytes()


def _popen_cli(argv, env, script=CONTROL_PY):
    return subprocess.Popen(
        [sys.executable, str(script), *[str(a) for a in argv]],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=env["TMPDIR"],
        start_new_session=True,
        text=True,
    )


def _communicate(proc, timeout=30):
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        pytest.fail(f"CLI did not exit within {timeout}s\n{out}\n{err}")
    assert out.count("\n") == 1 and out.endswith("\n"), (out, err)
    return proc.returncode, json.loads(out), err


def _linked_worktree(tmp_path):
    R = fake_repo(tmp_path)
    M = tmp_path / "main"
    (R / ".git").write_text(f"gitdir: {M}/.git/worktrees/x\n", encoding="utf-8")
    (M / "books" / "tmp").mkdir(parents=True)
    return R, M


# ---------------------------------------------------------------------------
# WI1-C28: FIFO canary
# ---------------------------------------------------------------------------


def test_c28_fifo_canary_across_up_doctor_down(tmp_path):  # WI1-C28
    R = fake_repo(tmp_path)
    os.mkfifo(R / "config" / "ai_settings.json")
    cwd = tmp_path / "work"
    (cwd / "config").mkdir(parents=True)
    os.mkfifo(cwd / "config" / "ai_settings.json")
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    script = R / CONTROL_REL
    d = _up(env, script=script, cwd=cwd)
    code, e, _ = run_cli(["doctor"], env, 30, script=script, cwd=cwd)
    assert code == 0 and e["ok"] is True, e
    code, e, _ = run_cli(["down"], env, 30, script=script, cwd=cwd)
    assert code == 0 and e["ok"] is True, e
    want = d["sandbox"] + "/ai_settings.json"
    assert os.path.isabs(want)
    for name in ("reader3", "reader3-server", "python"):
        calls = fv.calls(name)
        assert calls, name
        for c in calls:
            assert c["env"]["READER3_AI_SETTINGS"] == want, name
    for fifo in (R / "config" / "ai_settings.json", cwd / "config" / "ai_settings.json"):
        assert stat.S_ISFIFO(os.lstat(fifo).st_mode)


# ---------------------------------------------------------------------------
# WI1-C30 .. C43: up
# ---------------------------------------------------------------------------


def test_c30_up_with_fakes_env_argv_cwd_state_pointer(tmp_path):  # WI1-C30 (amended)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path) | {
        "READER3_TOKEN": "leak-token",
        "READER3_LIBRARY_UI": "classic",
        "READER3_EMBED_MODEL": "evil-model",
        "READER3_ALLOWED_HOSTS": "evil.invalid",
        "READER3_PORT": "1",
    }
    code, e, err = run_cli(["up", "--corpus", "smoke"], env)
    assert code == 0 and e["ok"] is True and e["command"] == "up", (e, err)
    d = e["data"]
    sbx = d["sandbox"]
    assert os.path.dirname(sbx) == os.path.realpath(env["TMPDIR"])
    assert os.path.basename(sbx).startswith("verify-reader3.")
    assert sbx == os.path.realpath(sbx)
    assert d["books_dir"] == sbx + "/books" and d["ai_settings"] == sbx + "/ai_settings.json"
    port = d["port"]
    assert d["base_url"] == f"http://127.0.0.1:{port}"
    assert http_client.validate_base_url(d["base_url"]) == port
    assert port != 8123 and 1024 <= port <= 65535
    assert d["books"] == ["smoke_data"]
    assert d["state"] == sbx + "/state.json" and d["log"] == sbx + "/server.log"
    srv = fv.calls("reader3-server")
    assert len(srv) == 1
    assert srv[0]["argv"][1:] == ["--port", str(port)]
    assert srv[0]["pid"] == d["pid"]
    assert srv[0]["cwd"] == sbx
    sandbox_pair = {"READER3_BOOKS_DIR": d["books_dir"], "READER3_AI_SETTINGS": d["ai_settings"]}
    assert {k: v for k, v in srv[0]["env"].items() if k.startswith("READER3_")} == sandbox_pair
    assert "READER3_TOKEN" not in srv[0]["env_keys"]
    ing = fv.calls("reader3")
    assert len(ing) == 1
    assert ing[0]["argv"][1:] == [sbx + "/smoke.epub"]
    assert ing[0]["cwd"] == sbx
    assert {k: v for k, v in ing[0]["env"].items() if k.startswith("READER3_")} == sandbox_pair
    s = state.read(d["state"])
    assert s["pid"] == d["pid"] and s["pid_start"] == lstart(d["pid"])
    assert s["port"] == port and s["base_url"] == d["base_url"]
    assert s["token"] is None and s["stub_pid"] is None and s["stub_pid_start"] is None
    assert s["repo"] == str(REPO)
    assert stat.S_IMODE(os.stat(d["state"]).st_mode) == 0o600
    state.load(d["state"], repo=REPO)
    assert json.loads(pointer(env).read_text()) == {"state": d["state"]}
    assert _evidence(env) == ["instance.json"]
    assert alive(d["pid"])
    run_cli(["down"], env)


def test_c31_smoke_corpus_is_the_real_build_epub2(tmp_path):  # WI1-C31
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    _up(env, "--corpus", "smoke")
    ref = _build_epub2(tmp_path / "ref" / "ref.epub")
    call = fv.calls("reader3")[0]
    assert call["zip_namelist"] == zipfile.ZipFile(ref).namelist()
    assert call["mimetype"] == "application/epub+zip"
    assert call["zip_namelist"][0] == "mimetype"
    run_cli(["down"], env)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_c32_repeatable_epub_order_and_books_listing(tmp_path):  # WI1-C32
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    a = _build_epub2(tmp_path / "src" / "a.epub")
    n = tmp_path / "src" / "nopkl.epub"
    shutil.copy(a, n)
    sha = (_sha(a), _sha(n))
    d = _up(env, "--epub", str(a), "--epub", str(n))
    assert d["books"] == ["a_data", "smoke_data"]
    assert [c["argv"][1] for c in fv.calls("reader3")] == [
        d["sandbox"] + "/smoke.epub",
        os.path.realpath(a),
        os.path.realpath(n),
    ]
    assert os.path.isdir(d["books_dir"] + "/.locks")
    assert os.path.isdir(d["books_dir"] + "/nopkl_data")
    assert (_sha(a), _sha(n)) == sha
    run_cli(["down"], env)


def test_c33_missing_epub_refused_before_anything(tmp_path):  # WI1-C33
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    missing = tmp_path / "nope.epub"
    code, e, _ = run_cli(["up", "--epub", str(missing)], env)
    assert (code, e["error"]["code"]) == (1, "epub_missing")
    assert str(missing) in e["error"]["message"]
    assert fv.calls("reader3") == []
    assert os.listdir(env["TMPDIR"]) == []
    assert not pointer(env).exists()


def test_c34_ingest_failure_leaves_nothing(tmp_path):  # WI1-C34
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    b = _build_epub2(tmp_path / "src" / "bad.epub")
    code, e, _ = run_cli(["up", "--epub", str(b)], env)
    assert (code, e["error"]["code"]) == (1, "ingest_failed")
    assert "bad.epub" in e["error"]["message"] and "FAKE-INGEST-FAIL" in e["error"]["message"]
    assert fv.calls("reader3-server") == []
    assert _sandboxes(env) == []
    assert not pointer(env).exists()


def test_c35_server_exits_at_startup(tmp_path):  # WI1-C35
    fv = fake_venv(tmp_path, server="exit")
    env = base_env(tmp_path)
    r = run_cli(["up"], env)
    code, e, _ = r
    assert (code, e["error"]["code"]) == (1, "server_exited")
    assert "FAKE-STARTUP-BOOM" in e["error"]["message"]
    assert r.elapsed_s < 10
    assert wait_dead(fv.calls("reader3-server")[0]["pid"], 2)
    assert _sandboxes(env) == []
    assert not pointer(env).exists()


@pytest.mark.parametrize("server", ["hang", "ignore_term_hang"])
def test_c36_health_never_answers_startup_timeout(tmp_path, server):  # WI1-C36
    fv = fake_venv(tmp_path, server=server)
    env = base_env(tmp_path) | {"VERIFY_READER3_HEALTH_TIMEOUT_S": "2", "VERIFY_READER3_KILL_GRACE_S": "1"}
    r = run_cli(["up"], env, timeout=30)
    code, e, _ = r
    assert (code, e["error"]["code"]) == (1, "startup_timeout")
    assert r.elapsed_s < 12
    assert wait_dead(fv.calls("reader3-server")[0]["pid"], 2)
    assert any(q["path"] == "/api/health" for q in fv.requests())
    assert _sandboxes(env) == []
    assert not pointer(env).exists()


def test_c37_port_in_use_then_explicit_port_honoured(tmp_path):  # WI1-C37
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    P = s.getsockname()[1]
    try:
        code, e, _ = run_cli(["up", "--port", str(P)], env)
        assert (code, e["error"]["code"]) == (1, "port_in_use")
        assert str(P) in e["error"]["message"]
        assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
        assert _sandboxes(env) == []
    finally:
        s.close()
    d = _up(env, "--port", str(P))
    assert d["port"] == P
    assert fv.calls("reader3-server")[0]["argv"][1:] == ["--port", str(P)]
    run_cli(["down"], env)


C38_ROWS = [(srv, extra, "full") for srv, extra in itertools.product(["serve", "exit", "hang"], [False, True])] + [
    ("serve", False, "none"),
    ("serve", False, "no_server"),
]


@pytest.mark.parametrize("server,bad,venv", C38_ROWS, ids=[f"{s}-{'bad' if b else 'plain'}-{v}" for s, b, v in C38_ROWS])
def test_c38_outcome_law(tmp_path, server, bad, venv):  # WI1-C38 (amended, plus C77's listing law)
    env = base_env(tmp_path) | {"VERIFY_READER3_HEALTH_TIMEOUT_S": "2", "VERIFY_READER3_KILL_GRACE_S": "1"}
    fv = None
    if venv != "none":
        fv = fake_venv(tmp_path, server=server)
        if venv == "no_server":
            (fv.bin / "reader3-server").unlink()
    extra = ["--epub", str(_build_epub2(tmp_path / "src" / "bad.epub"))] if bad else []
    before = sorted(os.listdir(env["TMPDIR"]))
    code, e, _ = run_cli(["up", *extra], env)
    ok = e["ok"]
    assert ok == (server == "serve" and not bad and venv == "full")
    if venv != "full":
        assert e["error"]["code"] == "venv_missing"
    calls_srv = fv.calls("reader3-server") if fv else []
    live = [c["pid"] for c in calls_srv if alive(c["pid"])]
    sbx = sorted(glob.glob(os.path.join(env["TMPDIR"], "verify-reader3.*")))
    ptr = pointer(env)
    claim = Path(env["VERIFY_READER3_EVIDENCE_ROOT"]) / "instance.claim"
    if ok:
        assert ptr.exists() and live == [e["data"]["pid"]] and len(sbx) == 1
        assert json.loads(ptr.read_text())["state"].startswith(os.path.realpath(sbx[0]))
        run_cli(["down"], env)
    else:
        assert not ptr.exists() and live == [] and sbx == []
        assert sorted(os.listdir(env["TMPDIR"])) == before
    assert claim.exists() is False
    if venv != "full" and fv is not None:
        assert fv.calls("reader3") == []


def _race_round(env, fv):
    n_ing, n_srv = len(fv.calls("reader3")), len(fv.calls("reader3-server"))
    procs = [_popen_cli(["up"], env), _popen_cli(["up"], env)]
    return n_ing, n_srv, [_communicate(p) for p in procs]


def _assert_one_winner(env, fv, n_ing, n_srv, results):
    winners = [r for r in results if r[1]["ok"]]
    losers = [r for r in results if not r[1]["ok"]]
    assert len(winners) == 1 and len(losers) == 1, results
    w = winners[0][1]["data"]
    rc, le, _ = losers[0]
    assert rc == 3 and le["error"]["code"] == "refused_instance_running", le
    assert le["error"]["try"] == TRY_PREFIX + "down"
    assert len(fv.calls("reader3")) - n_ing == 1
    assert len(fv.calls("reader3-server")) - n_srv == 1
    assert [c["pid"] for c in fv.calls("reader3-server") if alive(c["pid"])] == [w["pid"]]
    assert json.loads(pointer(env).read_text()) == {"state": w["state"]}
    assert len(_sandboxes(env)) == 1
    assert _evidence(env) == ["instance.json"]
    return w, le


def test_c39_two_concurrent_ups_leave_one_instance(tmp_path):  # WI1-C39 (amended)
    fv = fake_venv(tmp_path, slow_ingest_s=1.0)
    env = base_env(tmp_path)
    for _ in range(3):
        n_ing, n_srv, results = _race_round(env, fv)
        _assert_one_winner(env, fv, n_ing, n_srv, results)
        code, e, _ = run_cli(["down"], env)
        assert code == 0, e
    # round 4: sequential loser
    n_ing, n_srv = len(fv.calls("reader3")), len(fv.calls("reader3-server"))
    a = _popen_cli(["up"], env)
    assert wait_until(lambda: len(fv.calls("reader3-server")) > n_srv, timeout=10)
    b = _popen_cli(["up"], env)
    results = [_communicate(a), _communicate(b)]
    w, le = _assert_one_winner(env, fv, n_ing, n_srv, results)
    assert results[0][1]["ok"] is True
    assert str(a.pid) in le["error"]["message"] or w["state"] in le["error"]["message"]
    run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["direct", "symlink"])
def test_c40_tempdir_inside_repo_books_refused(tmp_path, variant):  # WI1-C40
    R = fake_repo(tmp_path)
    (R / "books" / "tmp").mkdir()
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    if variant == "direct":
        env["TMPDIR"] = str(R / "books" / "tmp")
    else:
        (tmp_path / "tlink").symlink_to(R / "books" / "tmp")
        env["TMPDIR"] = str(tmp_path / "tlink")
    code, e, _ = run_cli(["up"], env, script=R / CONTROL_REL, cwd=tmp_path)
    assert (code, e["error"]["code"]) == (3, "refused_books_dir")
    assert os.path.realpath(R / "books") in e["error"]["message"]
    assert os.listdir(R / "books" / "tmp") == []
    assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
    assert not pointer(env).exists()


def test_c41_tampered_state_naming_repo_books(tmp_path):  # WI1-C41
    R = fake_repo(tmp_path)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    script = R / CONTROL_REL
    d = _up(env, script=script)
    rewrite_state(d["state"], books_dir=str(R / "books" / "x_data"))
    n0 = len(fv.requests())
    ptr0 = _ptr_bytes(env)
    for cmd in ("doctor", "down"):
        code, e, _ = run_cli([cmd], env, script=script)
        assert (code, e["error"]["code"]) == (3, "refused_books_dir"), (cmd, e)
    assert len(fv.requests()) == n0
    assert alive(d["pid"])
    assert os.path.isdir(d["sandbox"])
    assert _ptr_bytes(env) == ptr0
    assert os.listdir(R / "books") == []
    rewrite_state(d["state"], books_dir=d["books_dir"])
    run_cli(["down"], env, script=script)


def test_c42_pointer_names_live_instance(tmp_path):  # WI1-C42
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    ptr0 = _ptr_bytes(env)
    code, e, _ = run_cli(["up"], env)
    assert (code, e["error"]["code"]) == (3, "refused_instance_running")
    assert d["state"] in e["error"]["message"]
    assert e["error"]["try"] == TRY_PREFIX + "down"
    assert len(fv.calls("reader3")) == 1 and len(fv.calls("reader3-server")) == 1
    assert alive(d["pid"])
    assert _ptr_bytes(env) == ptr0
    assert len(_sandboxes(env)) == 1
    run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["missing_state", "dead_pid"])
def test_c43_stale_pointer_replaced_old_sandbox_kept(tmp_path, variant):  # WI1-C43
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    old = None
    if variant == "missing_state":
        pointer(env).write_text(json.dumps({"state": str(tmp_path / "gone" / "state.json")}), encoding="utf-8")
    else:
        p = spawn(["sleep", "60"], tmp_path)
        old = write_instance(env, pid=p.pid, port=1).parent
        p.kill()
        p.wait(10)
    d = _up(env)
    assert json.loads(pointer(env).read_text()) == {"state": d["state"]}
    if old is not None:
        assert old.is_dir()
    run_cli(["down"], env)


# ---------------------------------------------------------------------------
# WI1-C44: proxy env never redirects
# ---------------------------------------------------------------------------


def test_c44_proxy_env_never_redirects_health(tmp_path):  # WI1-C44
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    for k in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]:
        env[k] = "http://127.0.0.1:9"
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    env["VERIFY_READER3_HEALTH_TIMEOUT_S"] = "5"
    d = _up(env)
    code, e, _ = run_cli(["doctor"], env)
    assert e["data"]["health"] == 200, e
    health = [q for q in fv.requests() if q["path"] == "/api/health"]
    assert health
    for q in health:
        h = {k.lower(): v for k, v in q["headers"].items()}
        assert h["host"] == f"127.0.0.1:{d['port']}"
        assert "origin" not in h and "x-reader3-token" not in h
    run_cli(["down"], env)


# ---------------------------------------------------------------------------
# WI1-C45 .. C53, C69, C71, C74: doctor
# ---------------------------------------------------------------------------

C45_ROWS = [
    ("a", None, True, True, True),
    ("b", {"chromadb": True, "sentence_transformers": False}, True, False, True),
    ("c", {"chromadb": False, "sentence_transformers": True}, True, False, True),
    ("d", None, False, True, False),
]


@pytest.mark.parametrize("row,probe,hf_dir,exp_extra,exp_model", C45_ROWS, ids=[r[0] for r in C45_ROWS])
def test_c45_doctor_healthy_with_probe_variants(tmp_path, row, probe, hf_dir, exp_extra, exp_model):  # WI1-C45
    fv = fake_venv(tmp_path, probe=probe)
    env = base_env(tmp_path)
    if hf_dir:
        (tmp_path / "hf" / "hub" / MODEL_DIR).mkdir(parents=True)
    d = _up(env)
    code, e, _ = run_cli(["doctor"], env)
    assert code == 0 and e["ok"] is True, e
    g = e["data"]
    assert g["pid_alive"] is True and g["pid_identity"] is True and g["listener_is_ours"] is True
    assert g["listener_check"] == "ours" and g["health"] == 200 and g["extra_probe"] == "ok"
    assert g["extra_installed"] is exp_extra and g["model_cached"] is exp_model
    if row == "a":
        assert g["hint"] is None
    elif row in ("b", "c"):
        assert "uv sync" in g["hint"]
    else:
        assert "model" in g["hint"]
    last = fv.calls("python")[-1]
    assert last["argv"][1] == "-c"
    assert {k: v for k, v in last["env"].items() if k.startswith("READER3_")} == {
        "READER3_BOOKS_DIR": d["books_dir"],
        "READER3_AI_SETTINGS": d["ai_settings"],
    }
    run_cli(["down"], env)


def test_c46_hung_probe_is_bounded(tmp_path):  # WI1-C46
    fv = fake_venv(tmp_path, probe="hang")
    env = base_env(tmp_path)
    _up(env)
    env["VERIFY_READER3_PROBE_TIMEOUT_S"] = "1"
    r = run_cli(["doctor"], env)
    code, e, _ = r
    assert code == 0, e
    assert e["data"]["extra_installed"] is False and e["data"]["extra_probe"] == "timeout"
    assert e["data"]["hint"]
    assert r.elapsed_s < 10
    assert wait_dead(fv.calls("python")[-1]["pid"], 2)
    run_cli(["down"], env)


def test_c47_listener_is_someone_else(tmp_path):  # WI1-C47
    P = free_port()
    fv = fake_venv(tmp_path, server="no_listen")
    A = spawn([fv.bin / "reader3-server", "--port", str(P)], tmp_path)
    fv2 = fake_venv(tmp_path / "other", server="serve")
    B = spawn([fv2.bin / "reader3-server", "--port", str(P)], tmp_path)
    assert wait_listening(B.pid, P)
    assert wait_until(lambda: len(fv.calls("reader3-server")) == 1)
    env = base_env(tmp_path)
    write_instance(env, pid=A.pid, port=P)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"]) == (1, "port_not_ours"), e
    g = e["data"]
    assert g["pid_identity"] is True and g["listener_is_ours"] is False
    assert g["listener_check"] == "other" and g["listener_pid"] == B.pid
    assert alive(A.pid) and alive(B.pid)


def test_c48_no_instance_dead_instance_pid_not_ours(tmp_path):  # WI1-C48
    env = base_env(tmp_path)
    P = free_port()
    code, e, _ = run_cli(["doctor"], env)  # (a)
    assert (code, e["error"]["code"], e["error"]["try"]) == (1, "no_instance", TRY_PREFIX + "up")
    p = spawn(["sleep", "60"], tmp_path)  # (b)
    write_instance(env, pid=p.pid, port=P)
    p.kill()
    p.wait(10)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"]) == (1, "instance_dead")
    assert e["error"]["try"].startswith(TRY_PREFIX + "up")
    q = spawn(["sleep", "60"], tmp_path)  # (c)
    write_instance(env, pid=q.pid, port=P)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"]) == (1, "pid_not_ours")
    assert e["data"]["pid_alive"] is True and e["data"]["pid_identity"] is False
    assert alive(q.pid)


def test_c49_health_500_is_health_failed(tmp_path):  # WI1-C49
    P = free_port()
    fv = fake_venv(tmp_path, server="health_500")
    A = spawn([fv.bin / "reader3-server", "--port", str(P)], tmp_path)
    assert wait_listening(A.pid, P)
    env = base_env(tmp_path)
    write_instance(env, pid=A.pid, port=P)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"]) == (1, "health_failed"), e
    assert e["data"]["health"] == 500 and e["data"]["listener_is_ours"] is True


def test_c50_lsof_unavailable_fails_closed(tmp_path):  # WI1-C50
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    _up(env)
    pbin = tmp_path / "pbin"
    pbin.mkdir()
    (pbin / "ps").symlink_to(shutil.which("ps"))
    code, e, _ = run_cli(["doctor"], env | {"PATH": str(pbin)})
    assert (code, e["error"]["code"]) == (1, "listener_unavailable"), e
    g = e["data"]
    assert g["listener_check"] == "unavailable" and g["listener_is_ours"] is None and g["health"] == 200
    run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["alive", "dead"])
def test_c51_stub_pid_alive_or_dead(tmp_path, variant):  # WI1-C51 (amended)
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    s = spawn([sys.executable, make_stub_script(tmp_path)], tmp_path)
    assert wait_until(lambda: "ai_stub_runner.py" in (lstart(s.pid) and _cmd(s.pid)))
    rewrite_state(d["state"], stub_pid=s.pid, stub_pid_start=lstart(s.pid))
    if variant == "dead":
        s.kill()
        s.wait(10)
    code, e, _ = run_cli(["doctor"], env)
    if variant == "alive":
        assert code == 0 and e["data"]["stub_alive"] is True, e
        assert alive(s.pid)
    else:
        assert (code, e["error"]["code"]) == (1, "stub_dead")
        assert e["data"]["stub_alive"] is False
    rewrite_state(d["state"], stub_pid=None, stub_pid_start=None)
    run_cli(["down"], env)


def _cmd(pid):
    res = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    return res.stdout


@pytest.mark.parametrize("variant", ["present", "absent"])
def test_c52_browse_presence_reported_never_executed(tmp_path, variant):  # WI1-C52
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    _up(env)
    if variant == "present":
        fake_browse(tmp_path, {"status": [{"stdout": "ok", "exit": 0}]})
    else:
        env["VERIFY_READER3_BROWSE"] = str(tmp_path / "nope" / "browse")
    code, e, _ = run_cli(["doctor"], env)
    assert code == 0 and e["ok"] is True, e
    assert e["data"]["browse"] == {"path": env["VERIFY_READER3_BROWSE"], "present": variant == "present"}
    assert not (tmp_path / "fakelog" / "browse.jsonl").exists()
    run_cli(["down"], env)


def test_c53_doctor_is_read_only_and_idempotent(tmp_path):  # WI1-C53
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    sp, pp = Path(d["state"]), pointer(env)
    before = (sp.read_bytes(), sp.stat().st_mtime_ns, pp.read_bytes(), pp.stat().st_mtime_ns)
    envelopes = [run_cli(["doctor"], env)[1] for _ in range(3)]
    assert envelopes[0] == envelopes[1] == envelopes[2]
    assert (sp.read_bytes(), sp.stat().st_mtime_ns, pp.read_bytes(), pp.stat().st_mtime_ns) == before
    assert alive(d["pid"]) and len(fv.calls("reader3-server")) == 1
    run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["foreign_cmd", "recycled_start", "control"])
def test_c69_doctor_stub_identity(tmp_path, variant):  # WI1-C69
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    if variant == "foreign_cmd":
        x = spawn(["sleep", "60"], tmp_path)
        rewrite_state(d["state"], stub_pid=x.pid, stub_pid_start=lstart(x.pid))
    else:
        x = spawn([sys.executable, make_stub_script(tmp_path)], tmp_path)
        assert wait_until(lambda: "ai_stub_runner.py" in _cmd(x.pid))
        start = EPOCH if variant == "recycled_start" else lstart(x.pid)
        rewrite_state(d["state"], stub_pid=x.pid, stub_pid_start=start)
    code, e, _ = run_cli(["doctor"], env)
    if variant == "control":
        assert code == 0 and e["data"]["stub_alive"] is True, e
    else:
        assert (code, e["error"]["code"]) == (1, "stub_dead"), e
        g = e["data"]
        assert g["stub_alive"] is False and g["stub_pid"] == x.pid
        assert g["health"] == 200 and g["pid_identity"] is True
    assert alive(x.pid) and alive(d["pid"])
    rewrite_state(d["state"], stub_pid=None, stub_pid_start=None)
    run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["other_port", "foreign_host", "down"])
def test_c71_tampered_base_url_refused_before_any_request(tmp_path, variant):  # WI1-C71
    P, Q = free_port(), free_port()
    while Q == P:
        Q = free_port()
    fv = fake_venv(tmp_path, server="health_500")
    A = spawn([fv.bin / "reader3-server", "--port", str(P)], tmp_path)
    fv2 = fake_venv(tmp_path / "other", server="serve")
    B = spawn([fv2.bin / "reader3-server", "--port", str(Q)], tmp_path)
    assert wait_listening(A.pid, P) and wait_listening(B.pid, Q)
    env = base_env(tmp_path)
    S = write_instance(env, pid=A.pid, port=P)
    bad = "http://example.invalid:80" if variant == "foreign_host" else f"http://127.0.0.1:{Q}"
    rewrite_state(S, base_url=bad)
    ptr0 = _ptr_bytes(env)
    r = run_cli(["down" if variant == "down" else "doctor"], env)
    code, e, _ = r
    assert (code, e["error"]["code"]) == (3, "refused_url"), e
    assert bad in e["error"]["message"]
    if variant == "foreign_host":
        assert r.elapsed_s < 5
    assert fv2.requests() == [] and fv.requests() == []
    assert alive(A.pid) and alive(B.pid)
    assert S.parent.is_dir()
    assert _ptr_bytes(env) == ptr0


def test_c74_pid_ours_but_nothing_listening(tmp_path):  # WI1-C74
    P = free_port()
    fv = fake_venv(tmp_path, server="no_listen")
    A = spawn([fv.bin / "reader3-server", "--port", str(P)], tmp_path)
    assert wait_until(lambda: len(fv.calls("reader3-server")) == 1)
    env = base_env(tmp_path)
    write_instance(env, pid=A.pid, port=P)
    code, e, _ = run_cli(["doctor"], env)
    assert (code, e["error"]["code"]) == (1, "port_not_ours"), e
    g = e["data"]
    assert g["pid_alive"] is True and g["pid_identity"] is True
    assert g["listener_check"] == "none" and g["listener_is_ours"] is False and g["listener_pid"] is None
    assert g["health"] is None
    assert alive(A.pid) and fv.requests() == []


# ---------------------------------------------------------------------------
# WI1-C54 .. C62: down
# ---------------------------------------------------------------------------


def test_c54_down_stops_ours_keeps_evidence_no_symlink_follow(tmp_path):  # WI1-C54
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    ev = tmp_path / "evidence" / "20261002-170349-F-018"
    ev.mkdir()
    (ev / "a.txt").write_text("keep")
    out = tmp_path / "outside"
    out.mkdir()
    (out / "sentinel").write_text("x")
    (Path(d["books_dir"]) / "escape").symlink_to(out)
    code, e, _ = run_cli(["down"], env)
    assert code == 0, e
    g = e["data"]
    assert g["killed"] is True and g["signal"] == "TERM" and g["removed_sandbox"] is True
    assert g["pointer_cleared"] is True and g["already_stopped"] is False
    assert not alive(d["pid"])
    assert not os.path.exists(d["sandbox"])
    assert not pointer(env).exists()
    assert (ev / "a.txt").read_text() == "keep"
    assert (out / "sentinel").exists()
    assert port_bindable(d["port"])


def test_c55_sigterm_ignored_escalates_to_kill(tmp_path):  # WI1-C55
    fake_venv(tmp_path, server="ignore_term")
    env = base_env(tmp_path)
    d = _up(env)
    env["VERIFY_READER3_KILL_GRACE_S"] = "1"
    r = run_cli(["down"], env)
    code, e, _ = r
    assert code == 0 and e["data"]["signal"] == "KILL", e
    assert r.elapsed_s < 8
    assert not alive(d["pid"]) and not os.path.exists(d["sandbox"])


@pytest.mark.parametrize("variant", ["foreign_sleep", "recycled_lstart", "wrong_port", "no_ps"])
def test_c56_identity_refusal(tmp_path, variant):  # WI1-C56 (amended)
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    if variant == "foreign_sleep":
        pid = spawn(["sleep", "60"], tmp_path).pid
        S = write_instance(env, pid=pid, port=free_port())
        sandbox = S.parent
    else:
        d = _up(env)
        pid, S, sandbox = d["pid"], Path(d["state"]), Path(d["sandbox"])
        if variant == "recycled_lstart":
            rewrite_state(S, pid_start=EPOCH)
        elif variant == "wrong_port":
            rewrite_state(S, port=d["port"] + 1, base_url=f"http://127.0.0.1:{d['port'] + 1}")
    (sandbox / "s").write_text("s")
    ptr0 = _ptr_bytes(env)
    run_env = env
    if variant == "no_ps":
        lbin = tmp_path / "lbin"
        lbin.mkdir()
        (lbin / "lsof").symlink_to(shutil.which("lsof"))
        run_env = env | {"PATH": str(lbin)}
    code, e, _ = run_cli(["down"], run_env)
    assert (code, e["error"]["code"]) == (3, "refused_pid_identity"), e
    assert str(pid) in e["error"]["message"]
    os.kill(pid, 0)
    assert (sandbox / "s").exists()
    assert _ptr_bytes(env) == ptr0
    if variant != "foreign_sleep":
        if variant == "wrong_port":
            rewrite_state(S, port=d["port"], base_url=d["base_url"])
        elif variant == "recycled_lstart":
            rewrite_state(S, pid_start=lstart(pid))
        run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["ours", "ours_via_write_instance", "foreign", "recycled"])
def test_c57_stub_identity_in_down(tmp_path, variant):  # WI1-C57 (amended)
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    if variant == "foreign":
        s = spawn(["sleep", "60"], tmp_path)
    else:
        s = spawn([sys.executable, make_stub_script(tmp_path)], tmp_path)
        assert wait_until(lambda: "ai_stub_runner.py" in _cmd(s.pid))
    if variant == "ours_via_write_instance":
        write_instance(env, pid=d["pid"], port=d["port"], sandbox=d["sandbox"], stub_pid=s.pid)
    else:
        start = EPOCH if variant == "recycled" else lstart(s.pid)
        rewrite_state(d["state"], stub_pid=s.pid, stub_pid_start=start)
    ptr0 = _ptr_bytes(env)
    code, e, _ = run_cli(["down"], env)
    if variant.startswith("ours"):
        assert code == 0, e
        assert e["data"]["stub_killed"] is True and e["data"]["stub_pid"] == s.pid
        assert wait_dead(s.pid, 2) and not alive(d["pid"])
        assert not os.path.exists(d["sandbox"])
    else:
        assert (code, e["error"]["code"]) == (3, "refused_pid_identity"), e
        assert str(s.pid) in e["error"]["message"]
        assert alive(s.pid) and alive(d["pid"])
        assert os.path.isdir(d["sandbox"]) and _ptr_bytes(env) == ptr0
        rewrite_state(d["state"], stub_pid=None, stub_pid_start=None)
        run_cli(["down"], env)


@pytest.mark.parametrize("variant", ["notours", "nested", "symlink", "tmpdir", "other_tmpdir"])
def test_c58_sandbox_shape_refusal(tmp_path, variant):  # WI1-C58
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    T = Path(env["TMPDIR"])
    run_env = env
    if variant == "notours":
        target = T / "notours"
        target.mkdir()
    elif variant == "nested":
        target = T / "sub" / "verify-reader3.x"
        target.mkdir(parents=True)
    elif variant == "symlink":
        (tmp_path / "victim").mkdir()
        (tmp_path / "victim" / "s").write_text("v")
        target = T / "verify-reader3.link"
        target.symlink_to(tmp_path / "victim")
    elif variant == "tmpdir":
        target = T
    else:
        target = Path(d["sandbox"])
        (tmp_path / "tmp2").mkdir()
        run_env = env | {"TMPDIR": str(tmp_path / "tmp2")}
    if variant != "symlink":
        (target / "s").write_text("s")
    if variant != "other_tmpdir":
        rewrite_state(d["state"], sandbox=str(target))
    ptr0 = _ptr_bytes(env)
    code, e, _ = run_cli(["down"], run_env)
    assert (code, e["error"]["code"]) == (3, "refused_sandbox_shape"), e
    assert (target / "s").exists()
    if variant == "symlink":
        assert (tmp_path / "victim" / "s").exists()
    assert alive(d["pid"]) and _ptr_bytes(env) == ptr0
    rewrite_state(d["state"], sandbox=d["sandbox"])
    run_cli(["down"], env)


def test_c59_dry_run_reports_and_changes_nothing(tmp_path):  # WI1-C59
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    ptr0 = _ptr_bytes(env)
    code, e, _ = run_cli(["down", "--dry-run"], env)
    assert code == 0, e
    g = e["data"]
    assert g["dry_run"] is True and g["would_kill"] == [d["pid"]] and g["would_remove"] == d["sandbox"]
    assert g["killed"] is False and g["removed_sandbox"] is False
    assert alive(d["pid"]) and os.path.isdir(d["sandbox"]) and _ptr_bytes(env) == ptr0
    code, e, _ = run_cli(["down"], env)
    assert code == 0 and e["data"]["killed"] is True


def test_c60_dead_server_sandbox_present(tmp_path):  # WI1-C60
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    os.kill(d["pid"], signal.SIGKILL)
    assert wait_dead(d["pid"])
    code, e, _ = run_cli(["down"], env)
    assert code == 0, e
    g = e["data"]
    assert g["already_stopped"] is True and g["killed"] is False
    assert g["removed_sandbox"] is True and g["pointer_cleared"] is True
    assert not os.path.exists(d["sandbox"]) and not pointer(env).exists()


def test_c61_down_is_idempotent(tmp_path):  # WI1-C61
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    runs = [run_cli(["down"], env) for _ in range(2)]
    snap = snapshot_tree(tmp_path)
    runs.append(run_cli(["down"], env))
    assert runs[0][0] == 0 and runs[0][1]["data"]["killed"] is True
    for code, e, _ in runs[1:]:
        assert code == 0 and e["data"]["already_stopped"] is True and e["data"]["removed_sandbox"] is False
    assert runs[1][1] == runs[2][1]
    for argv, extra in ((["down", "--state", d["state"]], {}), (["down"], {"VERIFY_READER3_STATE": d["state"]})):
        code, e, _ = run_cli(argv, env | extra)
        assert code == 0 and e["data"]["already_stopped"] is True, e
    assert snapshot_tree(tmp_path) == snap


@pytest.mark.parametrize("variant", ["victim", "tmpdir", "nested", "other_tmpdir", "dangling"])
def test_c62_dead_server_tampered_sandbox_refused(tmp_path, variant):  # WI1-C62, C62(e)
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    d = _up(env)
    os.kill(d["pid"], signal.SIGKILL)
    assert wait_dead(d["pid"])
    ptr0 = _ptr_bytes(env)
    T = Path(env["TMPDIR"])
    run_env = env
    target = None
    if variant == "victim":
        target = tmp_path / "victim"
        target.mkdir()
    elif variant == "tmpdir":
        target = T
    elif variant == "nested":
        target = T / "sub" / "verify-reader3.x"
        target.mkdir(parents=True)
    elif variant == "other_tmpdir":
        (tmp_path / "tmp2").mkdir()
        run_env = env | {"TMPDIR": str(tmp_path / "tmp2")}
        (Path(d["sandbox"]) / "s").write_text("s")
    else:
        target = T / "verify-reader3.dl"
        target.symlink_to(tmp_path / "nowhere")
    if target is not None and variant != "dangling":
        (target / "s").write_text("s")
    listing = set(os.listdir(T))
    if target is not None:
        rewrite_state(d["state"], sandbox=str(target))
    code, e, _ = run_cli(["down"], run_env)
    assert (code, e["error"]["code"]) == (3, "refused_sandbox_shape"), e
    if variant == "dangling":
        assert os.path.lexists(target)
    elif target is not None:
        assert (target / "s").exists()
    else:
        assert (Path(d["sandbox"]) / "s").exists()
    assert set(os.listdir(T)) >= listing
    assert os.path.isdir(d["sandbox"]) and os.path.exists(d["state"])
    assert _ptr_bytes(env) == ptr0


# ---------------------------------------------------------------------------
# WI1-C63(d), C64(d), C78: protected roots through the CLI
# ---------------------------------------------------------------------------


def test_c63d_tempdir_in_symlinked_books_root(tmp_path):  # WI1-C63 (d)
    R = fake_repo(tmp_path)
    (R / "books").rmdir()
    (tmp_path / "ext_lib" / "tmp").mkdir(parents=True)
    (R / "books").symlink_to(tmp_path / "ext_lib")
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    env["TMPDIR"] = str(tmp_path / "ext_lib" / "tmp")
    code, e, _ = run_cli(["up"], env, script=R / CONTROL_REL, cwd=tmp_path)
    assert (code, e["error"]["code"]) == (3, "refused_books_dir"), e
    assert os.listdir(tmp_path / "ext_lib" / "tmp") == []
    assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
    assert os.listdir(tmp_path / "evidence") == []


@pytest.mark.parametrize("variant", ["d1", "d2", "d3"])
def test_c64d_linked_worktree_tempdir_refused(tmp_path, variant):  # WI1-C64 (d1)-(d3)
    R, M = _linked_worktree(tmp_path)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    if variant == "d2":
        (tmp_path / "mlink").symlink_to(M / "books" / "tmp")
        env["TMPDIR"] = str(tmp_path / "mlink")
    else:
        env["TMPDIR"] = str(M / "books" / "tmp")
    if variant == "d3":
        (M / ".git" / "worktrees" / "x").mkdir(parents=True)
    code, e, _ = run_cli(["up"], env, script=R / CONTROL_REL, cwd=tmp_path)
    assert (code, e["error"]["code"]) == (3, "refused_books_dir"), e
    assert os.path.realpath(M / "books") in e["error"]["message"]
    assert os.listdir(M / "books" / "tmp") == []
    assert fv.calls("reader3") == [] and fv.calls("reader3-server") == []
    assert os.listdir(tmp_path / "evidence") == []


def test_c64d4_recorded_books_dir_in_main_checkout(tmp_path):  # WI1-C64 (d4, round 2 amended)
    R, M = _linked_worktree(tmp_path)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    script = R / CONTROL_REL
    d = _up(env, script=script)
    rewrite_state(d["state"], books_dir=str(M / "books" / "x_data"))
    ptr0 = _ptr_bytes(env)
    n0 = len(fv.requests())
    for cmd in ("doctor", "down"):
        code, e, _ = run_cli([cmd], env, script=script)
        assert (code, e["error"]["code"]) == (3, "refused_books_dir"), (cmd, e)
    assert alive(d["pid"]) and os.path.isdir(d["sandbox"])
    assert _ptr_bytes(env) == ptr0 and len(fv.requests()) == n0
    rewrite_state(d["state"], books_dir=d["books_dir"])
    run_cli(["down"], env, script=script)


@pytest.mark.parametrize("which", ["main", "worktree"])
def test_c78_evidence_root_inside_protected_books(tmp_path, which):  # WI1-C78
    R, M = _linked_worktree(tmp_path)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    ev = (M if which == "main" else R) / "books" / "ev"
    env["VERIFY_READER3_EVIDENCE_ROOT"] = str(ev)
    snaps = (snapshot_tree(M / "books"), snapshot_tree(R / "books"))
    for argv in (["up", "--corpus", "smoke"], ["doctor"], ["down"]):
        code, e, _ = run_cli(argv, env, script=R / CONTROL_REL, cwd=tmp_path)
        assert (code, e["error"]["code"]) == (3, "refused_books_dir"), (argv, e)
    assert not os.path.lexists(ev)
    assert fv.calls("reader3") == []
    assert os.listdir(env["TMPDIR"]) == []
    assert (snapshot_tree(M / "books"), snapshot_tree(R / "books")) == snaps


# ---------------------------------------------------------------------------
# WI1-C65: claim
# ---------------------------------------------------------------------------


def _bind_listen():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s


@pytest.mark.parametrize("kind", ["exit", "hang", "bad_epub", "port_in_use"])
def test_c65_claim_released_on_every_failure(tmp_path, kind):  # WI1-C65 (a)-(d)
    env = base_env(tmp_path)
    sock = None
    argv = ["up"]
    run_env = env
    if kind == "exit":
        fake_venv(tmp_path, server="exit")
        expected = "server_exited"
    elif kind == "hang":
        fake_venv(tmp_path, server="hang")
        run_env = env | {"VERIFY_READER3_HEALTH_TIMEOUT_S": "2", "VERIFY_READER3_KILL_GRACE_S": "1"}
        expected = "startup_timeout"
    elif kind == "bad_epub":
        fake_venv(tmp_path)
        argv = ["up", "--epub", str(_build_epub2(tmp_path / "src" / "bad.epub"))]
        expected = "ingest_failed"
    else:
        fake_venv(tmp_path)
        sock = _bind_listen()
        argv = ["up", "--port", str(sock.getsockname()[1])]
        expected = "port_in_use"
    code, e, _ = run_cli(argv, run_env)
    assert (code, e["error"]["code"]) == (1, expected), e
    assert _evidence(env) == []
    fake_venv(tmp_path, server="serve")
    if sock is not None:
        sock.close()
        d = _up(env, *argv[1:])
    else:
        d = _up(env)
    assert _evidence(env) == ["instance.json"]
    assert json.loads(pointer(env).read_text())["state"] == d["state"]
    assert alive(d["pid"])
    run_cli(["down"], env)


def test_c65e_sigkilled_claimer_is_taken_over(tmp_path):  # WI1-C65 (e)
    fv = fake_venv(tmp_path, slow_ingest_s=30)
    env = base_env(tmp_path)
    c = _popen_cli(["up"], env)
    assert wait_until(lambda: len(fv.calls("reader3")) > 0, timeout=10)
    assert (tmp_path / "evidence" / "instance.claim").exists()
    os.kill(c.pid, signal.SIGKILL)
    c.wait(10)
    c.stdout.close()
    c.stderr.close()
    fake_venv(tmp_path)
    d = _up(env)
    assert len(_sandboxes(env)) == 2
    assert json.loads(pointer(env).read_text())["state"] == d["state"]
    assert _evidence(env) == ["instance.json"]
    run_cli(["down"], env)


def _plant_claim(env, pid, start):
    p = Path(env["VERIFY_READER3_EVIDENCE_ROOT"]) / "instance.claim"
    p.write_text(json.dumps({"pid": pid, "pid_start": start}), encoding="utf-8")


def _dead_pid(tmp_path):
    p = spawn(["sleep", "60"], tmp_path)
    p.kill()
    p.wait(10)
    return p.pid


@pytest.mark.parametrize("variant", ["dead", "alive_not_ours"])
def test_c65f_planted_stale_claim(tmp_path, variant):  # WI1-C65 (f1), (f2)
    fake_venv(tmp_path)
    env = base_env(tmp_path)
    x = None
    if variant == "dead":
        _plant_claim(env, _dead_pid(tmp_path), EPOCH)
    else:
        x = spawn(["sleep", "60"], tmp_path)
        _plant_claim(env, x.pid, lstart(x.pid))
    d = _up(env)
    assert _evidence(env) == ["instance.json"]
    if x is not None:
        assert alive(x.pid)
    assert alive(d["pid"])
    run_cli(["down"], env)


def test_c65f3_stale_claim_concurrent_takeover(tmp_path):  # WI1-C65 (f3)
    fv = fake_venv(tmp_path, slow_ingest_s=1.0)
    env = base_env(tmp_path)
    for _ in range(3):
        _plant_claim(env, _dead_pid(tmp_path), EPOCH)
        n_ing, n_srv, results = _race_round(env, fv)
        _assert_one_winner(env, fv, n_ing, n_srv, results)
        run_cli(["down"], env)


# ---------------------------------------------------------------------------
# WI1-C66: the one real start
# ---------------------------------------------------------------------------

FETCH = r"""
import sys, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for url in sys.argv[1:]:
    with opener.open(url, timeout=10) as r:
        body = r.read().decode("utf-8", "replace")
        marks = [m for m in ('data-testid="lib-main"', 'data-testid="rd-shell"') if m in body]
        print("%d\t%d\t%s" % (r.status, len(body), ",".join(marks)))
"""


def _server_env_text(pid):
    if sys.platform.startswith("linux"):
        return Path(f"/proc/{pid}/environ").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    res = subprocess.run(["ps", "eww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    return res.stdout


def test_c66_real_reader3_and_server_lifecycle(tmp_path):  # WI1-C66
    vbin = Path(sys.executable).parent
    assert (vbin / "reader3").exists() and (vbin / "reader3-server").exists(), (
        f"real reader3/reader3-server not found next to {sys.executable}; run the lane with `uv run`"
    )
    env = base_env(tmp_path) | {
        "VERIFY_READER3_VENV_BIN": str(vbin),
        "READER3_TOKEN": "leak-token",
        "READER3_LIBRARY_UI": "classic",
    }
    try:
        code, e, err = run_cli(["up", "--corpus", "smoke"], env, timeout=60)
        assert code == 0 and e["ok"] is True, (e, err)
        d = e["data"]
        register_pid(d["pid"], tmp_path, d["sandbox"])
        assert d["books"] == ["smoke_data"]
        assert os.path.isfile(d["books_dir"] + "/smoke_data/book.pkl")
        assert _evidence(env) == ["instance.json"]
        assert state.read(d["state"])["stub_pid_start"] is None
        res = subprocess.run(
            [sys.executable, "-c", FETCH, d["base_url"] + "/", d["base_url"] + "/read/smoke_data/0"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        lines = [ln.split("\t") for ln in res.stdout.splitlines()]
        assert len(lines) == 2, (res.stdout, res.stderr)
        assert lines[0][0] == "200" and 'data-testid="lib-main"' in lines[0][2]
        assert lines[1][0] == "200" and 'data-testid="rd-shell"' in lines[1][2]
        senv = _server_env_text(d["pid"])
        assert f"READER3_BOOKS_DIR={d['sandbox']}/books" in senv
        assert f"READER3_AI_SETTINGS={d['sandbox']}/ai_settings.json" in senv
        assert "READER3_TOKEN=" not in senv and "READER3_LIBRARY_UI=" not in senv
        code, e, _ = run_cli(["doctor"], env, timeout=30)
        assert code == 0, e
        g = e["data"]
        assert g["health"] == 200 and g["listener_is_ours"] is True and g["pid_identity"] is True
        assert isinstance(g["extra_installed"], bool) and isinstance(g["model_cached"], bool)
        # WI4-C47: the real server's access log carries the marker probes and the write between them.
        from verify_control import access_log

        probe = (
            "import http.client, sys\n"
            "port = int(sys.argv[1])\n"
            "for m, p, b in (('GET', '/api/health?verify-marker=wi4probe-begin', None),\n"
            "                ('POST', '/api/notes/smoke_data/0', b'{}'),\n"
            "                ('GET', '/api/health?verify-marker=wi4probe-end', None)):\n"
            "    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)\n"
            "    c.request(m, p, body=b, headers={'Content-Type': 'application/json'})\n"
            "    c.getresponse().read()\n"
            "    c.close()\n"
        )
        subprocess.run([sys.executable, "-c", probe, str(d["port"])], check=True, timeout=20)
        slog = Path(d["sandbox"]) / "server.log"

        def _c47_slice():
            try:
                return access_log.slice_between(slog.read_text(encoding="utf-8").splitlines(), "wi4probe")
            except access_log.AccessLogError:
                return None

        assert wait_until(lambda: _c47_slice() is not None, timeout=1, step=0.05), slog.read_text(encoding="utf-8")[-2000:]
        c47_writes = _c47_slice()["writes"]
        assert len(c47_writes) == 1 and c47_writes[0]["method"] == "POST", c47_writes
        assert type(c47_writes[0]["status"]) is int
        assert any("?verify-marker=wi4probe-begin" in ln for ln in slog.read_text(encoding="utf-8").splitlines())
        # WI-9 / H1: the probe that is asserted empty after `down` must see the live server first.
        assert d["pid"] in listener_pids(d["port"]), (d["pid"], d["port"])
        code, e, _ = run_cli(["down"], env, timeout=30)
        assert code == 0 and e["data"]["killed"] is True, e
        assert wait_dead(d["pid"], 2)
        assert not os.path.exists(d["sandbox"]) and not pointer(env).exists()
        # Orchestrator ruling after red (2026-10-02): a plain bind fails for 2*MSL (30 s on macOS)
        # because the test's own urllib fetches leave server-side TIME_WAIT entries. The law is
        # "nothing listens on the port after down", so assert that directly.
        assert wait_until(lambda: listener_pids(d["port"]) == [], timeout=3, step=0.1)
        assert (tmp_path / "evidence").is_dir()
    finally:
        if pointer(env).exists():
            run_cli(["down"], env, timeout=30)


# ---------------------------------------------------------------------------
# WI1-C67, C77: interrupts and conservation
# ---------------------------------------------------------------------------

C67_ROWS = list(itertools.product(["SIGTERM", "SIGINT", "SIGHUP"], ["health", "health_ignore_term", "ingest"]))


def _start_interruptible_up(tmp_path, phase):
    env = base_env(tmp_path)
    if phase == "health":
        fv = fake_venv(tmp_path, server="hang")
        env["VERIFY_READER3_HEALTH_TIMEOUT_S"] = "60"
        wait_name = "reader3-server"
    elif phase == "health_ignore_term":
        fv = fake_venv(tmp_path, server="ignore_term_hang")
        env["VERIFY_READER3_HEALTH_TIMEOUT_S"] = "60"
        wait_name = "reader3-server"
    else:
        fv = fake_venv(tmp_path, slow_ingest_s=30)
        wait_name = "reader3"
    c = _popen_cli(["up"], env)
    assert wait_until(lambda: len(fv.calls(wait_name)) > 0, timeout=10)
    return env, fv, c


@pytest.mark.parametrize("sig,phase", C67_ROWS, ids=[f"{s}-{p}" for s, p in C67_ROWS])
def test_c67_signal_during_startup_is_interrupted(tmp_path, sig, phase):  # WI1-C67 (round 2: + SIGHUP)
    env, fv, c = _start_interruptible_up(tmp_path, phase)
    t0 = time.monotonic()
    os.kill(c.pid, getattr(signal, sig))
    try:
        out, err = c.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(c.pid, signal.SIGKILL)
        c.communicate()
        pytest.fail("up did not exit within 5 s of the signal")
    dt = time.monotonic() - t0
    assert dt < 5.0 and c.returncode == 1, (out, err)
    assert out.count("\n") == 1 and out.endswith("\n"), (out, err)
    e = json.loads(out)
    assert e["ok"] is False and e["command"] == "up"
    assert e["error"]["code"] == "interrupted" and e["error"]["try"].startswith(TRY_PREFIX)
    for name in ("reader3-server", "reader3"):
        for call in fv.calls(name):
            assert wait_dead(call["pid"], 1.0), (name, call["pid"])
    assert _sandboxes(env) == []
    assert os.listdir(tmp_path / "evidence") == []
    if phase == "ingest":
        assert fv.calls("reader3-server") == []


C77_MODES = ["exit", "hang", "bad_epub", "port_in_use", "venv_missing", "sigterm"]


@pytest.mark.parametrize("mode", C77_MODES)
def test_c77_failed_up_removes_only_its_own_sandbox(tmp_path, mode):  # WI1-C77
    env = base_env(tmp_path)
    T = Path(env["TMPDIR"])
    (T / "verify-reader3.keep").mkdir()
    (T / "verify-reader3.keep" / "s").write_text("s")
    bystander = write_instance(env, pid=_dead_pid(tmp_path), port=1).parent
    (bystander / "s").write_text("s")
    pointer(env).unlink()
    snaps = (snapshot_tree(T / "verify-reader3.keep"), snapshot_tree(bystander))
    listing = sorted(os.listdir(T))
    sock = None
    argv = ["up"]
    run_env = env
    if mode == "exit":
        fake_venv(tmp_path, server="exit")
        expected = "server_exited"
    elif mode == "hang":
        fake_venv(tmp_path, server="hang")
        run_env = env | {"VERIFY_READER3_HEALTH_TIMEOUT_S": "2", "VERIFY_READER3_KILL_GRACE_S": "1"}
        expected = "startup_timeout"
    elif mode == "bad_epub":
        fake_venv(tmp_path)
        argv = ["up", "--epub", str(_build_epub2(tmp_path / "src" / "bad.epub"))]
        expected = "ingest_failed"
    elif mode == "port_in_use":
        fake_venv(tmp_path)
        sock = _bind_listen()
        argv = ["up", "--port", str(sock.getsockname()[1])]
        expected = "port_in_use"
    elif mode == "venv_missing":
        expected = "venv_missing"
    else:
        expected = "interrupted"
    try:
        if mode == "sigterm":
            fv = fake_venv(tmp_path, server="hang")
            env["VERIFY_READER3_HEALTH_TIMEOUT_S"] = "60"
            c = _popen_cli(["up"], env)
            assert wait_until(lambda: len(fv.calls("reader3-server")) > 0, timeout=10)
            os.kill(c.pid, signal.SIGTERM)
            _, e, _ = _communicate(c, timeout=5)
        else:
            _, e, _ = run_cli(argv, run_env)
    finally:
        if sock is not None:
            sock.close()
    assert e["error"]["code"] == expected, e
    assert (snapshot_tree(T / "verify-reader3.keep"), snapshot_tree(bystander)) == snaps
    assert sorted(os.listdir(T)) == listing


# ---------------------------------------------------------------------------
# WI1-C68, C73(b), C75, C79
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["no_venv", "server_unlinked", "server_not_exec"])
def test_c68_venv_missing_before_anything(tmp_path, variant):  # WI1-C68
    env = base_env(tmp_path)
    vbin = tmp_path / "venv" / "bin"
    fv = None
    if variant != "no_venv":
        fv = fake_venv(tmp_path)
        if variant == "server_unlinked":
            (fv.bin / "reader3-server").unlink()
        else:
            os.chmod(fv.bin / "reader3-server", 0o644)
    runs = [["up"]]
    if variant == "server_unlinked":
        runs.append(["up", "--corpus", "smoke", "--epub", str(_build_epub2(tmp_path / "src" / "good.epub"))])
    for argv in runs:
        code, e, _ = run_cli(argv, env)
        assert (code, e["error"]["code"]) == (1, "venv_missing"), e
        assert e["error"]["try"].startswith(TRY_PREFIX)
        msg = e["error"]["message"]
        assert str(vbin / "reader3-server") in msg
        if variant == "no_venv":
            assert str(vbin / "reader3") + " " in msg or str(vbin / "reader3") + "," in msg or msg.count(
                str(vbin / "reader3")
            ) >= 2
        else:
            assert msg.count(str(vbin / "reader3")) == 1
        assert os.listdir(env["TMPDIR"]) == []
        assert os.listdir(tmp_path / "evidence") == []
        if fv is not None:
            assert fv.calls("reader3") == []


def test_c73b_missing_sandbox_tolerance_through_cli(tmp_path):  # WI1-C73 (b)
    env = base_env(tmp_path)
    T2 = Path(env["TMPDIR"])
    s = tmp_path / "s.json"
    good = {
        "sandbox": str(T2 / "verify-reader3.gone"),
        "books_dir": str(T2 / "verify-reader3.gone") + "/books",
        "ai_settings": str(T2 / "verify-reader3.gone") + "/ai_settings.json",
        "log": str(T2 / "verify-reader3.gone") + "/server.log",
        "port": 50000,
        "base_url": "http://127.0.0.1:50000",
        "pid": _dead_pid(tmp_path),
        "pid_start": EPOCH,
        "argv": [],
        "token": None,
        "stub_pid": None,
        "stub_pid_start": None,
        "stub_port": None,
        "repo": str(REPO),
    }
    s.write_text(json.dumps(good), encoding="utf-8")
    raw = s.read_bytes()
    code, e, _ = run_cli(["down", "--state", str(s)], env)  # (b1)
    assert code == 0, e
    g = e["data"]
    assert g["already_stopped"] is True and g["removed_sandbox"] is False and g["killed"] is False
    code, e, _ = run_cli(["doctor", "--state", str(s)], env)  # (b2)
    assert (code, e["error"]["code"]) == (3, "refused_sandbox_shape")
    assert e["error"]["try"] == TRY_PREFIX + "down"
    assert s.read_bytes() == raw
    fv = fake_venv(tmp_path)
    state.write_pointer(tmp_path / "evidence", s)  # (b3)
    d = _up(env)
    assert json.loads(pointer(env).read_text()) == {"state": d["state"]}
    run_cli(["down"], env)
    (tmp_path / "victim").mkdir()  # (b4)
    (tmp_path / "victim" / "s").write_text("v")
    (T2 / "verify-reader3.l").symlink_to(tmp_path / "victim")
    link = str(T2 / "verify-reader3.l")
    s.write_text(
        json.dumps(good | {"sandbox": link, "books_dir": link + "/books", "ai_settings": link + "/ai_settings.json", "log": link + "/server.log"}),
        encoding="utf-8",
    )
    state.write_pointer(tmp_path / "evidence", s)
    ptr0 = _ptr_bytes(env)
    n_ing = len(fv.calls("reader3"))
    listing = sorted(os.listdir(T2))
    code, e, _ = run_cli(["up"], env)
    assert (code, e["error"]["code"]) == (3, "refused_sandbox_shape"), e
    assert str(pointer(env)) in e["error"]["message"] and str(s) in e["error"]["message"]
    assert len(fv.calls("reader3")) == n_ing
    assert sorted(os.listdir(T2)) == listing
    assert (tmp_path / "victim" / "s").exists()
    assert _ptr_bytes(env) == ptr0
    assert not (tmp_path / "evidence" / "instance.claim").exists()


def test_c75_symlinked_tmpdir_records_resolved_sandbox(tmp_path):  # WI1-C75
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path)
    (tmp_path / "tmplink").symlink_to(tmp_path / "tmp")
    env["TMPDIR"] = str(tmp_path / "tmplink")
    assert os.path.realpath(env["TMPDIR"]) != env["TMPDIR"]
    d = _up(env)
    assert d["sandbox"] == os.path.realpath(d["sandbox"])
    assert os.path.dirname(d["sandbox"]) == os.path.realpath(tmp_path / "tmp")
    assert not d["sandbox"].startswith(str(tmp_path / "tmplink"))
    assert state.read(d["state"])["sandbox"] == d["sandbox"]
    assert d["books_dir"] == d["sandbox"] + "/books"
    code, e, _ = run_cli(["down"], env)
    assert code == 0, e
    g = e["data"]
    assert g["sandbox"] == d["sandbox"] and g["removed_sandbox"] is True and g["killed"] is True
    assert os.listdir(tmp_path / "tmp") == []
    assert os.path.islink(tmp_path / "tmplink")
    assert not pointer(env).exists()
    assert fv.calls("reader3-server")[0]["cwd"] == d["sandbox"]


def test_c79_server_child_forced_offline(tmp_path):  # WI1-C79 (subprocess half)
    fv = fake_venv(tmp_path)
    env = base_env(tmp_path) | {"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"}
    _up(env, "--corpus", "smoke")
    srv_env = fv.calls("reader3-server")[0]["env"]
    assert srv_env["HF_HUB_OFFLINE"] == "1" and srv_env["TRANSFORMERS_OFFLINE"] == "1"
    run_cli(["down"], env)
