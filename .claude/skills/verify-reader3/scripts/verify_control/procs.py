"""Child processes: the sandbox env, bounded runs, identity checks, listeners, signals.

Every spawn goes through `subprocess.Popen` with stdin closed and a new session, so a
timeout or an interrupt can kill the whole process group. Identity is never a bare pid:
a pid is ours only if its command line, its `--port` and its start time all match.
"""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import NamedTuple, Optional

OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


class RunResult(NamedTuple):
    exit: int
    stdout: str
    stderr: str
    timed_out: bool
    pid: int


class Identity(NamedTuple):
    command: str
    lstart: str


def sandbox_env(sandbox, *, token=None, parent=None):
    """The child env: no inherited READER3_*, sandbox paths injected, HF forced offline."""
    src = os.environ if parent is None else parent
    env = {k: v for k, v in src.items() if not k.startswith("READER3_")}
    books = Path(sandbox) / "books"
    env["READER3_BOOKS_DIR"] = str(books)
    env["READER3_AI_SETTINGS"] = str((books.parent / "ai_settings.json").resolve())
    if token:
        env["READER3_TOKEN"] = token
    env.update(OFFLINE)
    return env


def _kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def run(argv, *, env, cwd, timeout):
    proc = subprocess.Popen(
        [str(a) for a in argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(cwd),
        start_new_session=True,
        text=True,
        errors="replace",
        shell=False,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return RunResult(proc.returncode, out, err, False, proc.pid)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return RunResult(proc.returncode if proc.returncode is not None else -9, out, err, True, proc.pid)
    except BaseException:  # noqa: BLE001 - kill the child group on any interrupt, then re-raise
        _kill_group(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise


def spawn_logged(argv, *, env, cwd, log_path):
    """Start a long-lived child in its own session with stdout+stderr to `log_path`."""
    with open(log_path, "ab") as log:
        return subprocess.Popen(
            [str(a) for a in argv],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(cwd),
            start_new_session=True,
            shell=False,
        )


def _ps_field(field, pid):
    ps = shutil.which("ps")
    if ps is None:
        return None
    try:
        res = subprocess.run(
            [ps, "-o", f"{field}=", "-p", str(int(pid))],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    out = res.stdout.strip()
    return out or None


def read_identity(pid) -> Optional[Identity]:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    command = _ps_field("command", pid)
    lstart = _ps_field("lstart", pid)
    if command is None or lstart is None:
        return None
    return Identity(command, lstart)


def pid_is_ours(pid, pid_start, expect_substr, *, port=None):
    """Marker token by basename, the adjacent `--port <port>` pair, and equal lstart."""
    ident = read_identity(pid)
    if ident is None or not pid_start or ident.lstart != pid_start:
        return False
    tokens = ident.command.split()
    if not any(os.path.basename(t) == expect_substr for t in tokens):
        return False
    if port is not None:
        pairs = zip(tokens, tokens[1:])
        if not any(a == "--port" and b == str(port) for a, b in pairs):
            return False
    return True


def alive(pid):
    """True iff the pid exists and is not a zombie."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat_field = _ps_field("stat", pid)
    return not (stat_field or "").startswith("Z")


def wait_gone(pid, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def terminate(pid, grace):
    """TERM the group, wait `grace`, then KILL. Return the last signal sent."""
    _kill_group(pid, signal.SIGTERM)
    if wait_gone(pid, grace):
        return "TERM"
    _kill_group(pid, signal.SIGKILL)
    wait_gone(pid, 2.0)
    return "KILL"


def stop_child(proc, grace):
    """Stop a Popen child we own: TERM, wait, KILL, reap."""
    if proc.poll() is not None:
        return
    _kill_group(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    _kill_group(proc.pid, signal.SIGKILL)
    proc.wait()


def listeners(port):
    """('unavailable', []) without lsof; else ('ok', [pids listening on 127.0.0.1:port])."""
    lsof = shutil.which("lsof")
    if lsof is None:
        return "unavailable", []
    try:
        res = subprocess.run(
            [lsof, "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable", []
    pids = sorted({int(x) for x in res.stdout.split() if x.isdigit()})
    return "ok", pids
