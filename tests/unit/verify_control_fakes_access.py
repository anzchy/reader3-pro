"""WI-4 fakes for the verify-reader3 control CLI tests (owned by WI-4, per U8).

* `fake_access_server` - a child HTTP server that writes uvicorn-format access lines;
* `fake_browse` - the base helper's fake browse binary plus the `http_async` response key
  (WI-4/5/6 addendum A0.1);
* `read_argv_log`, `read_argv_entries` - the fake browse argv log;
* `decode_select_args` - the prefix-slicing decoder of amended WI4-C24.

Every child here is bounded (`signal.alarm`) and registered for `reap_fakes`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

import verify_control_support as support
from verify_control_support import FakeBrowse, spawn

READY_WAIT_S = 5.0

# ---------------------------------------------------------------------------
# fake access server
# ---------------------------------------------------------------------------

_ACCESS_SERVER = r'''
import json, os, re, signal, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
CFG = json.loads(sys.argv[1])
signal.alarm(120)
LOG = CFG["log"]
SIDE = CFG["side"]
DROP = re.compile(CFG["drop"]) if CFG["drop"] else None
LOCK = threading.Lock()
REASON = {200: "OK", 201: "Created"}

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _any(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        status = 201 if self.command == "POST" else 200
        body = b"{}"
        self.send_response(status, REASON[status])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True
        if DROP is not None and DROP.search(self.path):
            return
        line = 'INFO:     127.0.0.1:%d - "%s %s HTTP/1.1" %d %s' % (
            self.client_address[1], self.command, self.path, status, REASON[status])
        with LOCK:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
            with open(SIDE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"line": line, "t": time.time()}) + "\n")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _any

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
tmp = CFG["ready"] + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"port": srv.server_address[1], "pid": os.getpid()}, f)
os.replace(tmp, CFG["ready"])
srv.serve_forever()
'''


def fake_access_server(
    tmp_path: Path,
    log_path: Path,
    *,
    seed_lines: Sequence[str] = (),
    drop_log_regex: Optional[str] = None,
) -> Tuple[int, "subprocess.Popen[bytes]"]:
    """Start the child server; return `(port, proc)` once its ready file exists (<= 5 s)."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for line in seed_lines:
            f.write(line + "\n")
    fakelog = Path(tmp_path) / "fakelog"
    fakelog.mkdir(parents=True, exist_ok=True)
    ready = fakelog / "access.ready.json"
    cfg = {
        "log": str(log_path),
        "side": str(fakelog / "access.jsonl"),
        "drop": drop_log_regex,
        "ready": str(ready),
    }
    proc = spawn([sys.executable, "-c", _ACCESS_SERVER, json.dumps(cfg)], tmp_path)
    deadline = time.monotonic() + READY_WAIT_S
    while time.monotonic() < deadline:
        if ready.exists():
            info = json.loads(ready.read_text(encoding="utf-8"))
            return int(info["port"]), proc
        if proc.poll() is not None:
            break
        time.sleep(0.02)
    stop_server(proc)
    pytest.fail(f"fake access server did not become ready within {READY_WAIT_S}s")


def stop_server(proc: "subprocess.Popen[bytes]") -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def access_side_log(tmp_path: Path) -> List[Dict[str, Any]]:
    """`{"line", "t"}` for every line the fake access server logged, in order."""
    return support._read_jsonl(Path(tmp_path) / "fakelog" / "access.jsonl")


# ---------------------------------------------------------------------------
# fake browse with `http_async`
# ---------------------------------------------------------------------------

_ASYNC_SRC = r'''
import http.client, json, os, signal, sys, time
from urllib.parse import urlsplit
signal.alarm(60)
CFG = json.loads(sys.argv[1])
with open(CFG["pids"], "a", encoding="utf-8") as f:
    f.write("%d\n" % os.getpid())
t0 = time.time()
u = urlsplit(CFG["base_url"])
for item in sorted(CFG["items"], key=lambda i: float(i.get("delay_s", 0))):
    wait = t0 + float(item.get("delay_s", 0)) - time.time()
    if wait > 0:
        time.sleep(wait)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    sent_at = time.time()
    try:
        conn.request(item["method"], item["path"])
        status = conn.getresponse().status
    finally:
        conn.close()
    with open(CFG["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"method": item["method"], "path": item["path"], "status": status, "sent_at": sent_at}) + "\n")
'''

_ASYNC_HOOK = '''    if resp.get("http_async"):
        import subprocess
        _payload = json.dumps({
            "base_url": os.environ.get("FAKE_BROWSE_BASE_URL", ""),
            "items": resp["http_async"],
            "log": os.path.join(LOG_DIR, "browse_async.jsonl"),
            "pids": os.path.join(LOG_DIR, "browse.pids"),
        })
        subprocess.Popen([sys.executable, "-c", __ASYNC__, _payload], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''

_ANCHOR = '    sys.exit(int(resp.get("exit", 0)))\n'


def fake_browse(tmp_path: Path, rules: Any = ()) -> FakeBrowse:
    """The base `fake_browse`, with the response-replay step extended by `http_async`."""
    fb = support.fake_browse(tmp_path, rules)
    src = support._FAKE_BROWSE
    assert src.count(_ANCHOR) == 1, "base fake browse changed shape; update the http_async hook"
    hook = _ASYNC_HOOK.replace("__ASYNC__", repr(_ASYNC_SRC))
    src = src.replace(_ANCHOR, hook + _ANCHOR)
    if isinstance(rules, dict):
        rules = [{"sub": k, "contains": None, "responses": list(v)} for k, v in rules.items()]
    cfg = {"log_dir": str(Path(tmp_path) / "fakelog"), "rules": list(rules)}
    support._write_exe(fb.path, src.replace("__CFG__", repr(json.dumps(cfg))))
    return fb


def async_log(tmp_path: Path) -> List[Dict[str, Any]]:
    return support._read_jsonl(Path(tmp_path) / "fakelog" / "browse_async.jsonl")


# ---------------------------------------------------------------------------
# argv log and select decoding
# ---------------------------------------------------------------------------


def read_argv_entries(path: Path) -> List[Dict[str, Any]]:
    return support._read_jsonl(Path(path))


def read_argv_log(path: Path) -> List[List[str]]:
    """Every logged browse argv (program path excluded); `[]` when the log is absent."""
    return [e["argv"] for e in read_argv_entries(path)]


def decode_select_args(js: str) -> Any:
    """Amended WI4-C24: slice off `"(" + SELECT_FN + ")("` and the final `)`; no regex."""
    from verify_control import cmd_reader

    prefix = "(" + cmd_reader.SELECT_FN + ")("
    assert js.startswith(prefix) and js.endswith(")"), js[:200]
    return json.loads(js[len(prefix):-1])


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
