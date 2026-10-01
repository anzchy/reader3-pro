#!/usr/bin/env python3
"""Run a command (the e2e lane) under an exclusive, non-blocking fcntl lock.

Purpose: at most one e2e run at a time across every session and worktree of this
user. A second attempt does not queue — it exits 75 immediately and names the holder.

Usage::

    e2e_lock.py -- <cmd...>     run <cmd> while holding the lock
    e2e_lock.py status          report FREE / HELD without taking the lock

Lock path: ``$READER3_E2E_LOCK`` if set and non-empty, else ``~/.cache/reader3-e2e.flock``
(derived from ``Path.home()``, i.e. ``$HOME``). The ``.flock`` name deliberately differs
from the legacy mkdir lock, which is a *directory* at ``~/.cache/reader3-e2e.lock``.
Missing parent directories are created. The lock file is never unlinked (unlinking
reopens the unlink-then-flock race) and never truncated before the lock is held.

Owner line, written after the lock is taken and **before** the child is spawned::

    session=<s> sha=<sha> start=<epoch> pid=<wrapper pid>

``<s>`` is ``$READER3_E2E_SESSION`` with every whitespace character replaced by ``_``
(``-`` if unset or empty). ``<sha>`` is ``git rev-parse HEAD`` of the repo this script
lives in (bounded timeout; ``unknown`` on any failure). The line is written with
pwrite → ftruncate → fsync, so a rewrite never leaves the file empty and a shorter
line never leaves the tail of a longer one.

Exit codes:

    ===========================================  ====  ==================================
    situation                                     rc    output
    ===========================================  ====  ==================================
    child exited normally with k                  k     —
    child killed by signal N                      128+N —  (no re-raise on the wrapper)
    lock held by someone else                     75    ``BUSY <owner line>`` on stderr
    ``status``, lock free / file missing          0     ``FREE`` on stdout
    ``status``, lock held                         1     ``HELD <owner line>`` on stdout
    usage error                                   2     usage on stderr
    lock path is a directory (run and status)     2     stderr names the path + rmdir fix
    cmd not found                                 127   stderr
    cmd not executable / cannot exec              126   stderr
    ``GITHUB_ACTIONS`` non-empty, run mode        k     lock file never opened or created
    ===========================================  ====  ==================================

A child that itself exits 75 or 2 is indistinguishable by rc alone; callers tell BUSY
apart by the ``BUSY `` stderr prefix. If the holder's file is empty (only possible in
the instant of a brand-new file's first acquire) the reader retries briefly, then says
``(owner unknown)``. ``status`` ignores ``GITHUB_ACTIONS``; its probe briefly takes the
lock, so a real acquirer racing that instant gets a spurious (safe) BUSY.

The lock fd is not inheritable (PEP 446 default, kept on purpose): if the wrapper is
SIGKILLed the kernel releases the lock even while the orphaned child keeps running.

Signals: once the child is about to be spawned, SIGINT and SIGTERM sent to the wrapper
are forwarded to the child only (``Popen.send_signal``, never the process group), every
time, and the wrapper keeps waiting — it never exits before the child, so the lock is held
for the child's whole lifetime. A signal arriving before the spawn keeps default behavior
(the wrapper dies; the kernel releases the lock). An inherited SIG_IGN for either signal is
reset to SIG_DFL before spawning, so the child starts with default dispositions. A child
killed by signal N maps to rc 128+N; the wrapper never re-raises it on itself.

Known limitation (decision D-1): the child stays in the wrapper's process group, so a
harness that kills the group still reaches the e2e server tree. The cost is that a
terminal ^C reaches the child twice — once directly from the tty and once forwarded by
the wrapper — and pytest treats a second ^C as a hard abort, which can cut
``live_server`` teardown short. ``start_new_session`` would avoid that, but would let a
group SIGKILL of the wrapper orphan the child in its own session.

POSIX only, stdlib only.
"""

from __future__ import annotations

import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

LOCK_ENV = "READER3_E2E_LOCK"
SESSION_ENV = "READER3_E2E_SESSION"
DEFAULT_LOCK_NAME = "reader3-e2e.flock"

EXIT_HELD = 1
EXIT_USAGE = 2
EXIT_BUSY = 75
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127

FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM)

GIT_TIMEOUT_S = 5.0
OWNER_READ_TRIES = 10
OWNER_READ_PAUSE_S = 0.05
_SHA_RE = re.compile(r"[0-9a-f]{40}")

USAGE = "usage: e2e_lock.py -- <cmd...>\n       e2e_lock.py status\n"


def _err(msg: str) -> None:
    sys.stderr.write(msg if msg.endswith("\n") else msg + "\n")
    sys.stderr.flush()


def lock_path() -> Path:
    override = os.environ.get(LOCK_ENV, "")
    if override:
        return Path(override)
    return Path.home() / ".cache" / DEFAULT_LOCK_NAME


def _directory_error(path: Path) -> int:
    _err(
        f"e2e_lock: lock path {path} is a directory, not a file. It looks like a leftover "
        f"legacy mkdir lock. If no e2e run is using it, remove it with: rmdir {path}"
    )
    return EXIT_USAGE


def _session() -> str:
    raw = os.environ.get(SESSION_ENV, "")
    cleaned = "".join("_" if c.isspace() else c for c in raw)
    return cleaned or "-"


def _head_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and _SHA_RE.fullmatch(sha) else "unknown"


def _owner_line() -> bytes:
    line = f"session={_session()} sha={_head_sha()} start={int(time.time())} pid={os.getpid()}\n"
    return line.encode("utf-8", "backslashreplace")


def _write_owner(fd: int, data: bytes) -> None:
    os.pwrite(fd, data, 0)
    os.ftruncate(fd, len(data))
    os.fsync(fd)


def _read_owner(fd: int) -> str:
    """First line of the holder's file; brief bounded retry if it is empty."""
    for attempt in range(OWNER_READ_TRIES):
        size = os.fstat(fd).st_size
        if size:
            first = os.pread(fd, size, 0).split(b"\n", 1)[0]
            if first:
                return first.decode("utf-8", "replace")
        if attempt + 1 < OWNER_READ_TRIES:
            time.sleep(OWNER_READ_PAUSE_S)
    return "(owner unknown)"


def _exit_code(returncode: int) -> int:
    return returncode if returncode >= 0 else 128 - returncode


def _spawn_and_wait(cmd: list[str]) -> int:
    """Spawn ``cmd`` in this process group, forward SIGINT/SIGTERM to it, return its mapped rc."""
    child: Optional[subprocess.Popen[bytes]] = None

    def _forward(signum: int, _frame: object) -> None:
        if child is None:
            # Not spawned yet (or spawn failed): behave as if no handler existed — die of
            # the signal; the kernel releases the lock with our fd.
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
            return
        # Child only — never killpg / kill(0, …). Every signal is forwarded; the handler is
        # never reverted and never exits, so the wrapper (and the lock) outlive the child.
        child.send_signal(signum)

    for signum in FORWARDED_SIGNALS:
        # An inherited SIG_IGN would survive exec into the child; reset it first (F5).
        if signal.getsignal(signum) is signal.SIG_IGN:
            signal.signal(signum, signal.SIG_DFL)
        signal.signal(signum, _forward)

    try:
        child = subprocess.Popen(cmd)
    except (FileNotFoundError, NotADirectoryError) as exc:
        _err(f"e2e_lock: command not found: {cmd[0]} ({exc.strerror})")
        return EXIT_NOT_FOUND
    except OSError as exc:
        _err(f"e2e_lock: cannot execute: {cmd[0]} ({exc.strerror})")
        return EXIT_NOT_EXECUTABLE
    # PEP 475: wait() is retried after a handler runs, so forwarding never ends the wait.
    return _exit_code(child.wait())


def run(cmd: list[str]) -> int:
    if os.environ.get("GITHUB_ACTIONS"):
        return _spawn_and_wait(cmd)

    path = lock_path()
    if path.is_dir():
        return _directory_error(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    except IsADirectoryError:
        return _directory_error(path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _err(f"BUSY {_read_owner(fd)}")
            return EXIT_BUSY
        _write_owner(fd, _owner_line())
        return _spawn_and_wait(cmd)
    finally:
        os.close(fd)


def status() -> int:
    path = lock_path()
    if path.is_dir():
        return _directory_error(path)
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except FileNotFoundError:
        print("FREE")
        return 0
    except IsADirectoryError:
        return _directory_error(path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"HELD {_read_owner(fd)}")
            return EXIT_HELD
        fcntl.flock(fd, fcntl.LOCK_UN)
        print("FREE")
        return 0
    finally:
        os.close(fd)


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["status"]:
        return status()
    if len(args) >= 2 and args[0] == "--":
        return run(args[1:])
    _err(USAGE)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
