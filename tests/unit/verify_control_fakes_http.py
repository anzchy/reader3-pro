"""WI-2 fakes for the verify-reader3 control CLI tests (not collected: no `test_` prefix).

Contract: `.claude/tdd-guardian/tests-20261002-170349-WI-2-3.md` section 0.7 (A4, A7, A8)
and the WI-2/3 addendum H8. The base helper `verify_control_support.py` is not edited.

* `recording_server(tmp_path, routes=None)`: a stdlib `ThreadingHTTPServer` child on
  `127.0.0.1:0` that logs every request (method, raw target, headers as `[lower, value]`
  pairs, latin-1 body) to a JSONL file *before* it answers, then answers from `routes`.
  Route headers go to the wire verbatim (a 3xx route's `Location` included, H8).
* `outside_dir(tmp_path)`: a directory beside the sandboxes `write_state` creates
  (`tmp_path/tmp/outside`), holding the canary file and a `config/ai_settings.json` replica.
* `mkfifo_outside(tmp_path, name)`: a FIFO with no writer in that directory. Opening it for
  reading blocks forever, so a CLI that reads before it checks hangs and `run_cli` fails.
* `child_client` / `child_client_popen`: run a `python -c` script as a bounded child.

The test process itself never connects: every server here is a child process, and the
helper only waits for the port file the child writes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from verify_control_support import _read_jsonl, spawn

CANARY_NAME = "CANARY-outside-7f3.txt"
CANARY_CONTENT = "CANARY-CONTENT-7f3"
REPLICA_KEY = "sk-REPLICA-CANARY"
READY_WAIT_S = 10.0

_LIVE: List["Recorder"] = []

_SERVER_SRC = r'''
import json, os, signal, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

signal.alarm(120)
port_file, log_path, routes_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(routes_path, encoding="utf-8") as f:
    ROUTES = json.load(f)
LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n > 0 else b""
        entry = {
            "method": self.command,
            "target": self.path,
            "headers": [[k.lower(), v] for k, v in self.headers.items()],
            "body": body.decode("latin-1"),
        }
        with LOCK:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        route = ROUTES.get(self.command + " " + self.path.split("?", 1)[0])
        if route is None:
            route = {"status": 200, "headers": {"Content-Type": "application/json"}, "body": '{"ok": true}'}
        if route.get("delay_s"):
            time.sleep(float(route["delay_s"]))
        payload = route.get("body", "")
        data = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
        try:
            self.send_response(int(route.get("status", 200)))
            for k, v in (route.get("headers") or {"Content-Type": "application/json"}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
tmp = port_file + ".tmp"
with open(tmp, "w") as f:
    f.write(str(srv.server_address[1]))
os.replace(tmp, port_file)
srv.serve_forever()
'''


class Recorder:
    """A running recording server child: `.port`, `.base_url`, `.requests()`, `.stop()`."""

    def __init__(self, proc: "subprocess.Popen[bytes]", port: int, log: Path):
        self.proc = proc
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.log = log

    def requests(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.log)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)


def recording_server(tmp_path: Path, routes: Optional[Dict[str, Dict[str, Any]]] = None) -> Recorder:
    """Start a recording server child; wait at most 10 s for its port file."""
    base = Path(tmp_path) / "recsrv"
    base.mkdir(parents=True, exist_ok=True)
    n = len(list(base.glob("server-*.py")))
    script = base / f"server-{n}.py"
    script.write_text(_SERVER_SRC, encoding="utf-8")
    port_file, log = base / f"port-{n}", base / f"requests-{n}.jsonl"
    routes_file = base / f"routes-{n}.json"
    routes_file.write_text(json.dumps(routes or {}), encoding="utf-8")
    proc = spawn([sys.executable, script, port_file, log, routes_file], tmp_path)
    deadline = time.monotonic() + READY_WAIT_S
    while not port_file.exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            proc.wait(5)
            pytest.fail(f"recording server did not start (exit {proc.returncode})")
        time.sleep(0.02)
    rec = Recorder(proc, int(port_file.read_text()), log)
    _LIVE.append(rec)
    return rec


@pytest.fixture(autouse=True)
def stop_recorders():
    """Finalizer for every recorder a test started: terminate, wait 5, kill, wait 5."""
    yield
    while _LIVE:
        _LIVE.pop().stop()


def outside_dir(tmp_path: Path) -> Path:
    """`tmp_path/tmp/outside`: a sibling of every `write_state` sandbox, with the canaries."""
    out = Path(tmp_path) / "tmp" / "outside"
    (out / "config").mkdir(parents=True, exist_ok=True)
    (out / CANARY_NAME).write_text(json.dumps({"c": CANARY_CONTENT}), encoding="utf-8")
    replica = out / "config" / "ai_settings.json"
    replica.write_text(json.dumps({"providers": {"anthropic": {"api_key": REPLICA_KEY}}}), encoding="utf-8")
    return out


def mkfifo_outside(tmp_path: Path, name: str) -> Path:
    out = Path(tmp_path) / "tmp" / "outside"
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    os.mkfifo(path)
    return path


def child_client(script: str, *args: Any, timeout: float = 15) -> "subprocess.CompletedProcess[str]":
    cmd = [sys.executable, "-c", script, *[str(a) for a in args]]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"child client did not exit within {timeout:g}s\n{exc.stdout!r}\n{exc.stderr!r}")


def child_client_popen(script: str, *args: Any) -> "subprocess.Popen[str]":
    cmd = [sys.executable, "-c", script, *[str(a) for a in args]]
    return subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
