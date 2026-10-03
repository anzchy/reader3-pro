"""Shared harness for the verify-reader3 control CLI tests (WI-1 owns this file).

Contract: `.claude/tdd-guardian/tests-20261002-170349.md` U3-U8 and the WI-1 part file
section 0.3 (plus its addendum section 2). Later work items add their own fakes in their
own helper files and never edit this one.

Isolation rules every helper keeps:
* nothing here names the real `books/` or `config/` of the repo;
* every fake child exits by itself within 120 s and logs its pid so `reap_fakes` can
  kill it at teardown, and `reap_fakes` only kills a pid whose `ps` command line still
  names this test's tmp dir (or the argv the test registered), so a recycled foreign pid
  is never touched.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTROL_REL = Path(".claude/skills/verify-reader3/scripts/control.py")
SCRIPTS_DIR = REPO / CONTROL_REL.parent
CONTROL_PY = REPO / CONTROL_REL
CLI_TIMEOUT_S = 30.0
TRY_PREFIX = "python3 .claude/skills/verify-reader3/scripts/control.py "
FIXED_UUID = "0b7c6f1e-2f43-4a7e-9d1a-3c5e8f9a1b2c"
EPOCH_LSTART = "Thu Jan  1 00:00:00 1970"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_control  # noqa: E402,F401  (the package must be importable for every module)

_STRIP_EXACT = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "HF_HOME"}

# pid -> (tmp_path, marker) registered by `spawn` / `register_pid`.
_SPAWNED: Dict[int, Tuple[str, str]] = {}


# ---------------------------------------------------------------------------
# run_cli
# ---------------------------------------------------------------------------


class RunResult(tuple):
    """`(exit_code, envelope, stderr)` plus `.stdout` and `.elapsed_s`."""

    def __new__(cls, exit_code: int, envelope: Any, stderr: str, stdout: str, elapsed_s: float):
        self = super().__new__(cls, (exit_code, envelope, stderr))
        self.exit_code = exit_code
        self.envelope = envelope
        self.stderr = stderr
        self.stdout = stdout
        self.elapsed_s = elapsed_s
        return self


def _communicate(argv: List[str], env: Dict[str, str], timeout: float, cwd: Any, stdin: Any) -> Tuple[int, str, str, float]:
    t0 = time.monotonic()
    proc = subprocess.Popen(
        argv,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(cwd),
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        out, err = proc.communicate()
        pytest.fail(
            f"child did not exit within {timeout:g}s: {argv}\n--- stdout ---\n{out}\n--- stderr ---\n{err}"
        )
    return proc.returncode, out, err, time.monotonic() - t0


def run_cli(
    argv: Iterable[Any],
    env: Dict[str, str],
    timeout: float = CLI_TIMEOUT_S,
    *,
    cwd: Any = None,
    script: Any = CONTROL_PY,
    stdin: Any = subprocess.DEVNULL,
) -> RunResult:
    """Run the CLI; assert stdout is exactly one JSON object plus one newline."""
    cmd = [sys.executable, str(script), *[str(a) for a in argv]]
    rc, out, err, dt = _communicate(cmd, env, timeout, cwd if cwd is not None else env["TMPDIR"], stdin)
    shape_ok = out.endswith("\n") and out.count("\n") == 1
    doc: Any = None
    if shape_ok:
        try:
            doc = json.loads(out)
        except ValueError:
            shape_ok = False
    if not shape_ok or not isinstance(doc, dict):
        pytest.fail(
            "stdout is not exactly one JSON object followed by one newline "
            f"(expected exactly one JSON document)\n--- stdout ---\n{out!r}\n--- stderr ---\n{err}"
        )
    return RunResult(rc, doc, err, out, dt)


def run_cli_raw(
    argv: Iterable[Any],
    env: Dict[str, str],
    timeout: float = CLI_TIMEOUT_S,
    *,
    cwd: Any = None,
    script: Any = CONTROL_PY,
) -> "subprocess.CompletedProcess[str]":
    cmd = [sys.executable, str(script), *[str(a) for a in argv]]
    rc, out, err, _ = _communicate(cmd, env, timeout, cwd if cwd is not None else env["TMPDIR"], subprocess.DEVNULL)
    return subprocess.CompletedProcess(cmd, rc, out, err)


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------


def base_env(tmp_path: Path) -> Dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("READER3_", "VERIFY_READER3_")) and k.upper() not in _STRIP_EXACT
    }
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp_path / "tmp")
    env["VERIFY_READER3_EVIDENCE_ROOT"] = str(tmp_path / "evidence")
    env["VERIFY_READER3_VENV_BIN"] = str(tmp_path / "venv" / "bin")
    env["VERIFY_READER3_BROWSE"] = str(tmp_path / "browse-bin" / "browse")
    env["HF_HOME"] = str(tmp_path / "hf")
    return env


# ---------------------------------------------------------------------------
# fake venv
# ---------------------------------------------------------------------------

_FAKE_COMMON = r'''
import json, os, signal, sys, time
CFG = json.loads(__CFG__)
NAME = CFG["name"]
signal.alarm(120)
LOG_DIR = CFG["log_dir"]
os.makedirs(LOG_DIR, exist_ok=True)
_SHOWN = ("READER3_", "VERIFY_READER3_", "HF_", "TRANSFORMERS_")

def append(fname, obj):
    with open(os.path.join(LOG_DIR, fname), "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

def log(extra=None):
    line = {
        "argv": sys.argv, "cwd": os.getcwd(), "pid": os.getpid(), "ts": time.time(),
        "env_keys": sorted(os.environ),
        "env": {k: v for k, v in os.environ.items() if k.startswith(_SHOWN)},
    }
    line.update(extra or {})
    append(NAME + ".jsonl", line)
'''

_FAKE_READER3 = r'''
import zipfile
args = sys.argv[1:]
mode = "index" if "--index" in args else "add"
epub = None if mode == "index" or not args else args[0]
extra = {"mode": mode}
if epub:
    try:
        with zipfile.ZipFile(epub) as z:
            extra["zip_namelist"] = z.namelist()
            extra["mimetype"] = z.read("mimetype").decode("ascii", "replace")
    except Exception as exc:  # noqa: BLE001 - a fake: report, never crash before logging
        extra["zip_error"] = repr(exc)
log(extra)
script = {}
sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reader3.script.json")
if os.path.exists(sp):
    with open(sp, encoding="utf-8") as f:
        script = json.load(f)
if CFG["slow_ingest_s"]:
    time.sleep(CFG["slow_ingest_s"])
spec = script.get(mode)
if spec is not None:
    sys.stdout.write(spec.get("stdout", ""))
    sys.stderr.write(spec.get("stderr", ""))
    code = int(spec.get("exit", 0))
    if code != 0 or not CFG["writes"] or mode != "add":
        sys.exit(code)
stem = os.path.splitext(os.path.basename(epub or "book"))[0]
if CFG["reader3"] == "fail" or stem.startswith("bad"):
    print("FAKE-INGEST-FAIL " + str(epub), file=sys.stderr)
    sys.exit(1)
if mode == "add" and CFG["writes"]:
    books = os.environ["READER3_BOOKS_DIR"]
    os.makedirs(os.path.join(books, stem + "_data"), exist_ok=True)
    os.makedirs(os.path.join(books, ".locks"), exist_ok=True)
    if not stem.startswith("nopkl"):
        open(os.path.join(books, stem + "_data", "book.pkl"), "wb").close()
print("--- Summary ---")
print("Title: fake " + stem)
print("Physical Files (Spine): 2")
sys.exit(0)
'''

_FAKE_SERVER = r'''
import socket, threading
mode = CFG["server"]
port = int(sys.argv[sys.argv.index("--port") + 1])
log({"settings_existed_at_start": os.path.exists(os.environ.get("READER3_AI_SETTINGS", "\0"))})
if mode in ("ignore_term", "ignore_term_hang"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == "exit":
    print("FAKE-STARTUP-BOOM", file=sys.stderr)
    sys.exit(3)
if mode == "no_listen":
    while True:
        time.sleep(1)
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(16)
held = []
_lock = threading.Lock()

def handle(conn):
    conn.settimeout(5)
    buf = b""
    try:
        while b"\r\n\r\n" not in buf and len(buf) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
    except OSError:
        pass
    head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    lines = head.split("\r\n")
    parts = lines[0].split(" ") if lines and lines[0] else ["", ""]
    headers = {}
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            headers[k.strip()] = v.strip()
    with _lock:
        append("server-requests.jsonl", {"method": parts[0], "path": parts[1] if len(parts) > 1 else "", "headers": headers})
    if mode in ("hang", "ignore_term_hang"):
        held.append(conn)
        return
    path = parts[1] if len(parts) > 1 else ""
    if path == "/api/health":
        status, body = ("500 Internal Server Error", b'{"status":"error"}') if mode == "health_500" else ("200 OK", b'{"status":"ok"}')
    else:
        status, body = "404 Not Found", b'{"detail":"Not Found"}'
    try:
        conn.sendall(("HTTP/1.1 %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % (status, len(body))).encode() + body)
        conn.settimeout(3)
        while conn.recv(4096):
            pass
    except OSError:
        pass
    conn.close()

while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
'''

_FAKE_PYTHON = r'''
import importlib.util
log()
probe = CFG["probe"]
if probe == "hang":
    time.sleep(60)
    sys.exit(0)
if sys.argv[1:2] == ["-c"]:
    present = dict(probe or {"chromadb": True, "sentence_transformers": True})
    if not CFG["extra_installed"]:
        present = {"chromadb": False, "sentence_transformers": False}
    _real = importlib.util.find_spec

    def find_spec(name, package=None):
        if name in present:
            return _real("json") if present[name] else None
        return _real(name, package)

    importlib.util.find_spec = find_spec
    code = sys.argv[2]
    sys.argv = ["-c", *sys.argv[3:]]
    exec(compile(code, "<string>", "exec"), {"__name__": "__main__"})
    sys.exit(0)
sys.exit(0)
'''


class FakeVenv:
    def __init__(self, root: Path):
        self.root = root
        self.bin = root / "venv" / "bin"
        self.log_dir = root / "fakelog"

    def calls(self, name: str) -> List[Dict[str, Any]]:
        return _read_jsonl(self.log_dir / f"{name}.jsonl")

    def requests(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.log_dir / "server-requests.jsonl")

    def script(self, spec: Dict[str, Any]) -> Path:
        path = self.bin / "reader3.script.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def fake_venv(
    tmp_path: Path,
    *,
    server: str = "serve",
    reader3: str = "ok",
    probe: Any = None,
    slow_ingest_s: float = 0.0,
    writes: bool = True,
    extra_installed: bool = True,
) -> FakeVenv:
    fv = FakeVenv(Path(tmp_path))
    fv.log_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "log_dir": str(fv.log_dir),
        "server": server,
        "reader3": reader3,
        "probe": probe,
        "slow_ingest_s": float(slow_ingest_s),
        "writes": bool(writes),
        "extra_installed": bool(extra_installed),
    }
    for name, body in (("reader3", _FAKE_READER3), ("reader3-server", _FAKE_SERVER), ("python", _FAKE_PYTHON)):
        cfg = dict(base, name=name)
        common = _FAKE_COMMON.replace("__CFG__", repr(json.dumps(cfg)))
        _write_exe(fv.bin / name, common + body)
    return fv


# ---------------------------------------------------------------------------
# fake browse
# ---------------------------------------------------------------------------


class FakeBrowse(NamedTuple):
    path: Path
    argv_log: Path


_FAKE_BROWSE = r'''
import http.client, json, os, sys, time
from urllib.parse import urlsplit
CFG = json.loads(__CFG__)
LOG_DIR = CFG["log_dir"]
os.makedirs(LOG_DIR, exist_ok=True)
args = sys.argv[1:]
with open(os.path.join(LOG_DIR, "browse.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": args, "cwd": os.getcwd(), "pid": os.getpid()}) + "\n")
with open(os.path.join(LOG_DIR, "browse.pids"), "a", encoding="utf-8") as f:
    f.write("%d\n" % os.getpid())
sub = args[0] if args else ""
rest = " ".join(args[1:])
for i, rule in enumerate(CFG["rules"]):
    if rule.get("sub") != sub:
        continue
    if rule.get("contains") is not None and rule["contains"] not in rest:
        continue
    counter = os.path.join(LOG_DIR, "browse.counter.%d" % i)
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as f:
        f.write(str(n + 1))
    responses = rule.get("responses") or [{}]
    resp = responses[min(n, len(responses) - 1)]
    if resp.get("sleep_s"):
        time.sleep(float(resp["sleep_s"]))
    base = os.environ.get("FAKE_BROWSE_BASE_URL", "")
    for item in resp.get("http") or []:
        u = urlsplit(base)
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
        try:
            conn.request(item["method"], item["path"])
            conn.getresponse().read()
        finally:
            conn.close()
    k = resp.get("write_arg_file")
    if k is not None:
        with open(args[int(k)], "wb") as f:
            f.write(b"\x89PNGfake")
    sys.stdout.write(resp.get("stdout", ""))
    sys.stderr.write(resp.get("stderr", ""))
    sys.stdout.flush()
    sys.exit(int(resp.get("exit", 0)))
sys.exit(0)
'''


def fake_browse(tmp_path: Path, rules: Any = ()) -> FakeBrowse:
    """Write the fake gstack browse binary at `tmp_path/browse-bin/browse`.

    `rules` is a list of `{"sub", "contains", "responses"}` or the shorthand
    `{sub: [responses]}` (rules with `contains=None`).
    """
    if isinstance(rules, dict):
        rules = [{"sub": k, "contains": None, "responses": list(v)} for k, v in rules.items()]
    log_dir = Path(tmp_path) / "fakelog"
    log_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"log_dir": str(log_dir), "rules": list(rules)}
    path = Path(tmp_path) / "browse-bin" / "browse"
    _write_exe(path, _FAKE_BROWSE.replace("__CFG__", repr(json.dumps(cfg))))
    return FakeBrowse(path, log_dir / "browse.jsonl")


# ---------------------------------------------------------------------------
# repos, states
# ---------------------------------------------------------------------------


def fake_repo(tmp_path: Path) -> Path:
    root = Path(tmp_path) / "fakerepo"
    dest = root / CONTROL_REL.parent
    shutil.copytree(SCRIPTS_DIR, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "fixtures").symlink_to(REPO / "tests" / "fixtures")
    (root / "books").mkdir()
    (root / "config").mkdir()
    return root


def lstart(pid: int) -> str:
    res = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    return res.stdout.strip()


def _atomic_json(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".h.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_instance(
    env: Dict[str, str],
    *,
    pid: Optional[int],
    port: Optional[int],
    sandbox: Any = None,
    books_dir: Any = None,
    stub_pid: Optional[int] = None,
    stub_pid_start: Optional[str] = None,
    token: Optional[str] = None,
    pid_start: Optional[str] = None,
    base_url: Optional[str] = None,
    **overrides: Any,
) -> Path:
    """Write a valid state.json (inside the sandbox) and the pointer; return the state path."""
    if sandbox is None:
        sandbox = os.path.realpath(tempfile.mkdtemp(prefix="verify-reader3.", dir=env["TMPDIR"]))
    sandbox = str(sandbox)
    if books_dir is None:
        books_dir = sandbox + "/books"
        os.makedirs(books_dir, exist_ok=True)
    if pid_start is None and pid is not None:
        pid_start = lstart(pid)
    if stub_pid_start is None and stub_pid is not None:
        stub_pid_start = lstart(stub_pid)
    if base_url is None:
        base_url = f"http://127.0.0.1:{port}"
    data = {
        "sandbox": sandbox,
        "books_dir": str(books_dir),
        "ai_settings": sandbox + "/ai_settings.json",
        "port": port,
        "base_url": base_url,
        "pid": pid,
        "pid_start": pid_start,
        "argv": [],
        "log": sandbox + "/server.log",
        "token": token,
        "stub_pid": stub_pid,
        "stub_pid_start": stub_pid_start,
        "stub_port": None,
        "repo": str(REPO),
    }
    data.update(overrides)
    state_path = Path(sandbox) / "state.json"
    _atomic_json(state_path, data)
    ev = Path(env["VERIFY_READER3_EVIDENCE_ROOT"])
    ev.mkdir(parents=True, exist_ok=True)
    _atomic_json(ev / "instance.json", {"state": str(state_path)})
    return state_path


def rewrite_state(state_path: Any, **changes: Any) -> None:
    path = Path(state_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        assert key in data, f"rewrite_state: {key!r} is not a state key"
        data[key] = value
    _atomic_json(path, data)


class StateFx(NamedTuple):
    sandbox: Path
    books_dir: Path
    state_path: Path
    stub_dir: Path
    env: Dict[str, str]


def _port_of(base_url: str) -> Optional[int]:
    tail = base_url.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else None


def write_state(
    tmp_path: Path,
    *,
    base_url: str = "http://127.0.0.1:9",
    token: Optional[str] = None,
    books: Iterable[str] = ("smoke_data",),
    book_uuid: str = FIXED_UUID,
    stub_pid: Optional[int] = None,
    stub_port: Optional[int] = None,
) -> StateFx:
    env = base_env(tmp_path)
    state_path = write_instance(
        env,
        pid=os.getpid(),
        port=_port_of(base_url),
        base_url=base_url,
        token=token,
        stub_pid=stub_pid,
        stub_port=stub_port,
    )
    sandbox = state_path.parent
    books_dir = sandbox / "books"
    for book in books:
        (books_dir / book).mkdir(parents=True, exist_ok=True)
        (books_dir / book / "book.pkl").write_bytes(b"")
        (books_dir / book / "ai_meta.json").write_text(json.dumps({"book_uuid": book_uuid}), encoding="utf-8")
    settings = sandbox / "ai_settings.json"
    settings.write_text("{}", encoding="utf-8")
    os.chmod(settings, 0o600)
    return StateFx(sandbox, books_dir, state_path, sandbox / "ai_stub", dict(env, VERIFY_READER3_STATE=str(state_path)))


def make_state(tmp_path: Path, *, base_url: str, port: Any = None, log: Any, pid: int) -> Path:
    """WI-4's state builder. `port` is derived from `base_url` (round 2, RR11).

    The recorded `log` must be `<sandbox>/server.log` (RR2), so when the caller's log
    lives elsewhere that name is a symlink to it.
    """
    env = base_env(tmp_path)
    state_path = write_instance(env, pid=pid, port=_port_of(base_url), base_url=base_url)
    recorded = state_path.parent / "server.log"
    if os.path.abspath(str(log)) != str(recorded):
        recorded.symlink_to(os.path.abspath(str(log)))
    return state_path


# ---------------------------------------------------------------------------
# filesystem and process utilities
# ---------------------------------------------------------------------------


def snapshot_tree(path: Any) -> Dict[str, tuple]:
    root = Path(path)
    if not os.path.lexists(root):
        return {}
    out: Dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", st.st_size, st.st_mtime_ns, st.st_ino, os.readlink(full))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir", st.st_size, st.st_mtime_ns, st.st_ino)
            else:
                out[rel] = ("file", st.st_size, st.st_mtime_ns, st.st_ino)
    return out


def spawn(argv: Iterable[Any], tmp_path: Path) -> "subprocess.Popen[bytes]":
    args = [str(a) for a in argv]
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _SPAWNED[proc.pid] = (str(tmp_path), " ".join(args))
    return proc


def register_pid(pid: int, tmp_path: Path, marker: str) -> None:
    """Ask `reap_fakes` to kill `pid` at teardown if its command still contains `marker`."""
    _SPAWNED[int(pid)] = (str(tmp_path), marker)


def _ps(field: str, pid: int) -> str:
    try:
        res = subprocess.run(["ps", "-o", f"{field}=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip()


def alive(pid: Optional[int]) -> bool:
    """True iff `pid` exists and is not a zombie (reaps our own exited children)."""
    if not pid or pid <= 0:
        return False
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _ps("stat", pid).startswith("Z")


def wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def wait_until(pred: Any, timeout: float = 10.0, step: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(step)
    return bool(pred())


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    return port if port != 8123 else free_port()


def listener_pids(port: int) -> List[int]:
    res = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True, timeout=10
    )
    return [int(x) for x in res.stdout.split() if x.isdigit()]


def wait_listening(pid: int, port: int, timeout: float = 5.0) -> bool:
    return wait_until(lambda: pid in listener_pids(port), timeout=timeout, step=0.1)


def port_bindable(port: int, timeout: float = 3.0) -> bool:
    """Plain bind (no SO_REUSEADDR) succeeds within `timeout` (loopback close lingers ~0.5 s)."""

    def attempt() -> bool:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    return wait_until(attempt, timeout=timeout, step=0.1)


def make_stub_script(tmp_path: Path) -> Path:
    """A stand-in `ai_stub_runner.py` that just sleeps (the real runner is WI-3)."""
    path = Path(tmp_path) / "stubbin" / "ai_stub_runner.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    return path


def pointer(env: Dict[str, str]) -> Path:
    return Path(env["VERIFY_READER3_EVIDENCE_ROOT"]) / "instance.json"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _fake_pids(tmp_path: Path) -> List[int]:
    pids: List[int] = []
    for log in list(tmp_path.rglob("fakelog/*.jsonl")) + list(tmp_path.rglob("fakelog/*.pids")):
        try:
            text = log.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.isdigit():
                pids.append(int(line))
                continue
            try:
                pid = json.loads(line).get("pid")
            except (ValueError, AttributeError):
                continue
            if isinstance(pid, int):
                pids.append(pid)
    return pids


@pytest.fixture(autouse=True)
def reap_fakes(tmp_path: Path):
    yield
    names = {str(tmp_path), os.path.realpath(tmp_path)}
    for pid in set(_fake_pids(tmp_path)):
        cmd = _ps("command", pid)
        if cmd and any(n in cmd for n in names):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    for pid, (owner, marker) in list(_SPAWNED.items()):
        if owner != str(tmp_path):
            continue
        cmd = _ps("command", pid)
        if cmd and (marker in cmd or any(n in cmd for n in names)):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        _SPAWNED.pop(pid, None)


def _shallow(root: Path) -> Tuple[bool, Dict[str, Tuple[int, int, int]]]:
    if not root.exists():
        return False, {}
    tree: Dict[str, Tuple[int, int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            tree[os.path.relpath(full, root)] = (st.st_size, st.st_mtime_ns, st.st_ino)
    return True, tree


@pytest.fixture(autouse=True)
def real_evidence_untouched():
    root = REPO / ".claude" / "verify-evidence"
    before = _shallow(root)
    yield
    assert _shallow(root) == before, f"{root} changed during the test"


evidence_fence = real_evidence_untouched
