"""WI-3 fakes for the verify-reader3 control CLI: the fake SSE server and friends.

Contract: `.claude/tdd-guardian/tests-20261002-170349-WI-2-3.md` section 0.7 (A5, A6, A8)
and its addendum H1-H7. Not collected (no `test_` prefix).

* `sse_frame` is a literal copy of `chat._sse_event`; WI3-C06 pins it to the real one.
* `fake_sse_server` is a child process: the test process never connects (socket rule).
  It emulates the runner's half of the gate IPC on `stub_dir`, with the file names
  imported from `verify_control.ai_stub_runner` so they cannot drift.
* `pid_recording_stub_module` writes a stub module (the Q11 knob target) that records
  the importing process's pid and start time and re-exports the frozen `OllamaStub`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

import pytest

from verify_control_support import REPO, SCRIPTS_DIR, register_pid

RUNNER_PY = SCRIPTS_DIR / "verify_control" / "ai_stub_runner.py"
DELTAS = ("Alpha ", "是第一章的", "第一个", "词。")
FULL_TEXT = "".join(DELTAS)
META = {
    "message_id": "00000000-0000-4000-8000-000000000001",
    "retrieval_sources": [],
    "metadata": {"retrieval_time_ms": 3, "provider": "ollama"},
}
DONE = {
    "model": "stub-model",
    "finish_reason": "stop",
    "metadata": {"retrieval_time_ms": 3, "generation_time_ms": 12, "provider": "ollama"},
}


def sse_frame(event: str, data: Any) -> bytes:
    """Copy of `reader3_app.web.routers.ai.chat._sse_event` (chat.py:62-64)."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# fake SSE server (child process)
# ---------------------------------------------------------------------------

_FAKE_SSE_SRC = r'''
import json, os, signal, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
CFG = json.loads(sys.argv[1])
signal.alarm(120)
sys.path.insert(0, CFG["scripts_dir"])
from verify_control.ai_stub_runner import GATE_ARM_FILE, GATE_RELEASE_FILE, STATS_FILE

DELTAS = CFG["deltas"]
META = CFG["meta"]
DONE = CFG["done"]
MODE = CFG["mode"]
D = CFG["stub_dir"]
FIRST_DELAY = {int(k): float(v) for k, v in (CFG["first_chunk_delay_s"] or {}).items()}
LOCK = threading.Lock()
GATE = threading.Event()
REQS = []
INFLIGHT = set()
SUMMARY = {"max_concurrent": 0, "release_seen_at": None, "arm_seen_count": 0,
           "release_seen_count": 0, "streams_holding_at_release": None}
STATS = {"request_count": 0, "completed": False, "gate_released_by_render": False,
         "gate_timed_out": False, "payloads": 0, "gate_set": False}


def frame(event, data):
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def flush_reqs():
    atomic(CFG["log"], "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in REQS))


def flush_summary():
    atomic(CFG["summary"], json.dumps(SUMMARY))


def flush_stats():
    if CFG["ipc"]:
        atomic(os.path.join(D, STATS_FILE), json.dumps(STATS))


def ipc_loop():
    arm = os.path.join(D, GATE_ARM_FILE)
    rel = os.path.join(D, GATE_RELEASE_FILE)
    while True:
        if os.path.exists(arm):
            os.unlink(arm)
            with LOCK:
                GATE.clear()
                STATS["gate_set"] = False
                SUMMARY["arm_seen_count"] += 1
                flush_stats(); flush_summary()
        if os.path.exists(rel):
            os.unlink(rel)
            with LOCK:
                GATE.set()
                STATS["gate_set"] = True
                SUMMARY["release_seen_count"] += 1
                if SUMMARY["release_seen_at"] is None:
                    SUMMARY["release_seen_at"] = time.monotonic()
                    holding = [REQS[i] for i in INFLIGHT if REQS[i]["t_first_chunk"] is not None]
                    SUMMARY["streams_holding_at_release"] = len(holding)
                    for r in holding:
                        r["streams_holding_at_release"] = len(holding)
                    flush_reqs()
                flush_stats(); flush_summary()
        time.sleep(0.02)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        return

    def raw(self, b):
        self.wfile.write(b"%x\r\n" % len(b) + b + b"\r\n")
        self.wfile.flush()

    def send_frame(self, fr):
        if CFG["split_frames"]:
            hi = [i for i, c in enumerate(fr) if c >= 0x80]
            cut = hi[0] + 1 if hi else max(1, len(fr) // 2)
            self.raw(fr[:cut]); time.sleep(0.01)
            self.raw(fr[cut:]); time.sleep(0.01)
        else:
            self.raw(fr)

    def chunk(self, rec, d):
        first = rec["t_first_chunk"] is None
        if first and rec["index"] in FIRST_DELAY:
            time.sleep(FIRST_DELAY[rec["index"]])
        if CFG["chunk_delay_s"]:
            time.sleep(CFG["chunk_delay_s"])
        self.send_frame(frame("chunk", {"delta": d}))
        if first:
            with LOCK:
                rec["t_first_chunk"] = time.monotonic()
                flush_reqs()

    def end(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def json_reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self):
        self.close_connection = True
        self.json_reply(404, {"detail": "Not Found"})

    def do_POST(self):
        self.close_connection = True
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        with LOCK:
            rec = {"index": len(REQS), "target": self.path,
                   "headers": [[k.lower(), v] for k, v in self.headers.items()],
                   "body": body.decode("utf-8", "replace"), "t_accept": time.monotonic(),
                   "t_first_chunk": None, "t_end": None, "held": False,
                   "arm_seen_before_accept": SUMMARY["arm_seen_count"] > 0,
                   "gate_set_at_accept": GATE.is_set(), "streams_holding_at_release": None}
            REQS.append(rec)
            INFLIGHT.add(rec["index"])
            SUMMARY["max_concurrent"] = max(SUMMARY["max_concurrent"], len(INFLIGHT))
            STATS["request_count"] += 1
            STATS["payloads"] += 1
            flush_reqs(); flush_summary(); flush_stats()
        try:
            self.serve(rec)
        except OSError:
            pass
        finally:
            with LOCK:
                rec["t_end"] = time.monotonic()
                INFLIGHT.discard(rec["index"])
                flush_reqs(); flush_summary()

    def serve(self, rec):
        if not self.path.startswith("/api/ai/question/"):
            self.json_reply(404, {"detail": "Not Found"})
            return
        if MODE == "http404":
            self.json_reply(404, {"detail": "Book not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.flush()
        self.send_frame(frame("meta", META))
        if MODE == "stream":
            for d in DELTAS:
                self.chunk(rec, d)
            self.send_frame(frame("done", DONE))
        elif MODE == "gate":
            for d in DELTAS[:-1]:
                self.chunk(rec, d)
            released = GATE.is_set()
            if not released:
                with LOCK:
                    rec["held"] = True
                    flush_reqs()
                released = GATE.wait(CFG["gate_timeout_s"])
            if released:
                self.chunk(rec, DELTAS[-1])
            with LOCK:
                STATS["gate_released_by_render"] = released
                STATS["gate_timed_out"] = not released
                STATS["completed"] = released
                flush_stats()
            self.send_frame(frame("done", DONE))
        elif MODE == "hang":
            self.chunk(rec, DELTAS[0])
            while True:
                time.sleep(1)
        elif MODE == "error":
            self.send_frame(frame("error", {"message": "AI request timed out"}))
        elif MODE == "badjson":
            self.raw(b"event: chunk\ndata: not-json\n\n")
            self.send_frame(frame("done", DONE))
        elif MODE == "truncated":
            self.chunk(rec, DELTAS[0])
            if CFG["truncate_style"] == "abort":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
        elif MODE == "trickle":
            while True:
                self.raw(b": ka\n\n")
                time.sleep(CFG["trickle_interval_s"])
        self.end()


srv = ThreadingHTTPServer.__new__(ThreadingHTTPServer)
ThreadingHTTPServer.request_queue_size = 64
srv.__init__(("127.0.0.1", 0), H)
srv.daemon_threads = True
if CFG["ipc"]:
    os.makedirs(D, exist_ok=True)
    flush_stats()
    threading.Thread(target=ipc_loop, daemon=True).start()
flush_summary()
atomic(CFG["port_file"], str(srv.server_address[1]))
srv.serve_forever()
'''


def _read_json(path: Path) -> Any:
    for _ in range(50):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except ValueError:
            time.sleep(0.02)
    raise AssertionError(f"{path} never became valid JSON")


class FakeSSE:
    def __init__(self, proc: "subprocess.Popen[bytes]", port: int, root: Path, stub_dir: Path):
        self.proc = proc
        self.pid = proc.pid
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.root = root
        self.stub_dir = Path(stub_dir)

    @property
    def stats_path(self) -> Path:
        from verify_control.ai_stub_runner import STATS_FILE

        return self.stub_dir / STATS_FILE

    def requests(self) -> List[Dict[str, Any]]:
        path = self.root / "requests.jsonl"
        for _ in range(50):
            try:
                text = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return []
            try:
                return [json.loads(ln) for ln in text.splitlines() if ln.strip()]
            except ValueError:
                time.sleep(0.02)
        raise AssertionError(f"{path} never became valid JSONL")

    def summary(self) -> Dict[str, Any]:
        return _read_json(self.root / "summary.json")

    def stats(self) -> Optional[Dict[str, Any]]:
        return _read_json(self.stats_path)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)


_LIVE: List[FakeSSE] = []


def fake_sse_server(
    tmp_path: Path,
    stub_dir: Any,
    *,
    mode: str = "stream",
    chunk_delay_s: float = 0.0,
    gate_timeout_s: float = 1.5,
    ipc: bool = True,
    split_frames: bool = True,
    truncate_style: str = "clean",
    trickle_interval_s: float = 0.5,
    first_chunk_delay_s: Optional[Dict[int, float]] = None,
) -> FakeSSE:
    n = len(list(Path(tmp_path).glob("fakesse*")))
    root = Path(tmp_path) / f"fakesse{n}"
    root.mkdir(parents=True)
    script = root / "fake_sse_server.py"
    script.write_text(_FAKE_SSE_SRC, encoding="utf-8")
    cfg = {
        "scripts_dir": str(SCRIPTS_DIR), "stub_dir": str(stub_dir), "mode": mode,
        "chunk_delay_s": float(chunk_delay_s), "gate_timeout_s": float(gate_timeout_s), "ipc": bool(ipc),
        "split_frames": bool(split_frames), "truncate_style": truncate_style,
        "trickle_interval_s": float(trickle_interval_s),
        "first_chunk_delay_s": {str(k): v for k, v in (first_chunk_delay_s or {}).items()},
        "deltas": list(DELTAS), "meta": META, "done": DONE,
        "log": str(root / "requests.jsonl"), "summary": str(root / "summary.json"),
        "port_file": str(root / "port"),
    }
    errlog = open(root / "stderr.log", "wb")
    proc = subprocess.Popen(
        [sys.executable, str(script), json.dumps(cfg)],
        stdin=subprocess.DEVNULL, stdout=errlog, stderr=errlog, start_new_session=True,
    )
    errlog.close()
    register_pid(proc.pid, tmp_path, str(script))
    fake = FakeSSE(proc, 0, root, Path(stub_dir))
    _LIVE.append(fake)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if (root / "port").exists() and (root / "summary.json").exists():
            fake.port = int((root / "port").read_text())
            fake.base_url = f"http://127.0.0.1:{fake.port}"
            return fake
        if proc.poll() is not None:
            break
        time.sleep(0.02)
    fake.stop()
    pytest.fail("fake SSE server did not start:\n" + (root / "stderr.log").read_text(errors="replace"))


@pytest.fixture(autouse=True)
def stop_fake_sse():
    yield
    while _LIVE:
        _LIVE.pop().stop()


# ---------------------------------------------------------------------------
# stub modules for the Q11 knob (VERIFY_READER3_STUB_MODULE)
# ---------------------------------------------------------------------------

_RECORDING_STUB = r'''
import importlib.util, json, os, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_lst = subprocess.run(["ps", "-o", "lstart=", "-p", str(os.getpid())], capture_output=True, text=True,
                      timeout=10).stdout.strip()
_tmp = os.path.join(_HERE, "record.json.tmp")
with open(_tmp, "w") as f:
    json.dump({"pid": os.getpid(), "lstart": _lst, "argv": sys.argv}, f)
os.replace(_tmp, os.path.join(_HERE, "record.json"))
if __HANG__:
    time.sleep(3600)
_spec = importlib.util.spec_from_file_location("_frozen_ai_stub", __FROZEN__)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
OllamaStub = _mod.OllamaStub
DELTAS = _mod.DELTAS
STUB_GATE_TIMEOUT = _mod.STUB_GATE_TIMEOUT
'''


class StubRecorder(NamedTuple):
    module_path: Path
    record_path: Path

    def record(self) -> Optional[Dict[str, Any]]:
        return _read_json(self.record_path)


def pid_recording_stub_module(tmp_path: Path, *, hang: bool = False) -> StubRecorder:
    """H7. With `hang=True` the module records itself and then sleeps an hour (WI3-C30)."""
    d = Path(tmp_path) / "stubmod"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "recording_stub.py"
    src = _RECORDING_STUB.replace("__HANG__", repr(bool(hang)))
    src = src.replace("__FROZEN__", repr(str(REPO / "tests" / "fixtures" / "ai_stub.py")))
    path.write_text(src, encoding="utf-8")
    return StubRecorder(path, d / "record.json")


# ---------------------------------------------------------------------------
# child clients (the test process never connects)
# ---------------------------------------------------------------------------


def child_client(script: str, *args: Any, timeout: float = 15) -> "subprocess.CompletedProcess[str]":
    argv = [sys.executable, "-c", script, *[str(a) for a in args]]
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"child client did not exit within {timeout}s: {exc.stdout!r} {exc.stderr!r}")


def child_client_popen(script: str, *args: Any) -> "subprocess.Popen[str]":
    argv = [sys.executable, "-c", script, *[str(a) for a in args]]
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            stdin=subprocess.DEVNULL, start_new_session=True)


CHAT_CLIENT = r'''
import http.client, json, sys
conn = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=15)
body = json.dumps({"model": "stub-model", "messages": [{"role": "user", "content": "q"}], "stream": True})
conn.request("POST", "/api/chat", body=body, headers={"Content-Type": "application/json"})
resp = conn.getresponse()
while True:
    line = resp.readline()
    if not line:
        break
    sys.stdout.write(line.decode("utf-8"))
    sys.stdout.flush()
'''

GET_CLIENT = r'''
import http.client, sys
conn = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=10)
conn.request("GET", sys.argv[2])
resp = conn.getresponse()
print(resp.status)
print(resp.read().decode("utf-8", "replace"))
'''
