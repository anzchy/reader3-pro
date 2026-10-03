"""`doctor`: read-only health report for the recorded instance. Writes nothing."""

import http.client
import json
import os
import re

from verify_control import http_client, paths, procs
from verify_control.envelope import success
from verify_control.instance_common import SERVER_MARK, STUB_MARK, fail, is_exe, knob, load, resolve, run, setup

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EXTRA_HINT = "semantic extra not installed: run `uv sync --extra semantic` to enable semantic search"
MODEL_HINT = "embedding model not cached: the first semantic index run downloads the model"
PROBE = (
    "import importlib.util, json\n"
    "print(json.dumps({m: importlib.util.find_spec(m) is not None for m in ('chromadb', 'sentence_transformers')}))\n"
)


def _model_name(repo):
    try:
        with open(os.path.join(str(repo), "src", "reader3_app", "vector_search.py"), encoding="utf-8") as f:
            m = re.search(r"^MODEL_NAME\s*=\s*[\"']([^\"']+)[\"']", f.read(), re.M)
        return m.group(1) if m else DEFAULT_MODEL
    except OSError:
        return DEFAULT_MODEL


def _probe(repo, s):
    py = paths.venv_bin(os.environ, repo) / "python"
    timeout = knob("VERIFY_READER3_PROBE_TIMEOUT_S", 10)
    try:
        res = procs.run([py, "-c", PROBE], env=procs.sandbox_env(s["sandbox"], token=s["token"]),
                        cwd=s["sandbox"], timeout=timeout)
    except OSError:
        return False, "error"
    if res.timed_out:
        return False, "timeout"
    try:
        found = json.loads(res.stdout.strip().splitlines()[-1])
        return bool(found["chromadb"] and found["sentence_transformers"]), "ok"
    except (ValueError, KeyError, TypeError, IndexError):
        return False, "error"


def _listener(pid, port):
    status, pids = procs.listeners(port)
    if status == "unavailable":
        return "unavailable", None, None
    if not pids:
        return "none", False, None
    if pid in pids:
        return "ours", True, pid
    return "other", False, pids[0]


def _health(base_url):
    try:
        return http_client.request(base_url, "GET", "/api/health", timeout=5)[0]
    except (OSError, http.client.HTTPException):
        return None


def _doctor_verdict(g):
    if not g["pid_alive"]:
        return "instance_dead", f"server pid {g['pid']} is not running", "up"
    if not g["pid_identity"]:
        return "pid_not_ours", f"pid {g['pid']} is not this instance's reader3-server", "down"
    if g["listener_check"] == "unavailable":
        return "listener_unavailable", "lsof is not on PATH; cannot tell who listens on the port", "doctor"
    if g["listener_check"] in ("none", "other"):
        return "port_not_ours", f"port {g['port']} listener is {g['listener_check']}", "down"
    if g["health"] != 200:
        return "health_failed", f"/api/health returned {g['health']}", "down"
    if g["stub_pid"] is not None and not g["stub_alive"]:
        return "stub_dead", f"AI stub pid {g['stub_pid']} is not running or not ours", "down"
    return None


def cmd_doctor(ns):
    def body():
        repo, _, ptr = setup("doctor")
        sp = resolve("doctor", ns, ptr)
        if sp is None or not os.path.lexists(sp):
            raise fail("doctor", "no_instance", "no running instance is recorded", "up")
        s = load("doctor", sp, repo)
        pid, port = s["pid"], s["port"]
        pid_alive = procs.alive(pid)
        identity = pid_alive and procs.pid_is_ours(pid, s["pid_start"], SERVER_MARK, port=port)
        check, ours, lpid = _listener(pid, port)
        health = _health(s["base_url"]) if identity and check in ("ours", "unavailable") else None
        extra, probe = _probe(repo, s)
        hf = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
        model = os.path.isdir(os.path.join(hf, "hub", "models--sentence-transformers--" + _model_name(repo)))
        stub_pid = s["stub_pid"]
        stub_alive = None if stub_pid is None else (
            procs.alive(stub_pid) and procs.pid_is_ours(stub_pid, s["stub_pid_start"], STUB_MARK))
        browse = paths.browse_path(os.environ)
        g = {
            "pid": pid, "pid_alive": pid_alive, "pid_identity": identity, "port": port,
            "listener_is_ours": ours, "listener_pid": lpid, "listener_check": check, "health": health,
            "extra_installed": extra, "extra_probe": probe, "model_cached": model,
            "hint": EXTRA_HINT if not extra else MODEL_HINT if not model else None,
            "browse": {"path": browse, "present": is_exe(browse)},
            "stub_pid": stub_pid, "stub_alive": stub_alive,
        }
        verdict = _doctor_verdict(g)
        if verdict is not None:
            raise fail("doctor", verdict[0], verdict[1], verdict[2], data=g)
        return success("doctor", g)

    return run("doctor", body)
