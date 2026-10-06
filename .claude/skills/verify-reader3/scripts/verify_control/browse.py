"""The one door to the gstack `browse` binary: an allowlist, a bounded runner, typed errors.

Only the subcommands in `ALLOWED` may be spawned (ruling 2). `eval` is never allowed: it
runs a JS *file*, so it would let a caller smuggle arbitrary code past this wrapper. The
`ui inert -- <args>` passthrough relaxes the allowlist to "anything but eval".

Every call is bounded by `VERIFY_READER3_BROWSE_TIMEOUT_S` (default 30 s). A call that
overruns has its whole process group killed before the error is raised.

Page-content commands (`attrs`, `text`, ...) print their payload inside gstack's
UNTRUSTED EXTERNAL CONTENT envelope; `unwrap` strips it. `js`, `url` and `network` are bare.
"""

import math
import os
import re
import signal
import subprocess
from pathlib import Path

from verify_control import procs

ALLOWED = frozenset({"js", "frame", "url", "attrs", "network", "wait", "click", "screenshot"})
FORBIDDEN = frozenset({"eval"})
DEFAULT_TIMEOUT_S = 30.0
STDERR_TAIL = 2000
_BEGIN = re.compile(r"--- BEGIN UNTRUSTED EXTERNAL CONTENT(?: \(source: .*\))? ---")
_END = "--- END UNTRUSTED EXTERNAL CONTENT ---"


class BrowseRefused(Exception):
    """A subcommand outside the allowlist; nothing was spawned."""

    code = "refused_browse_command"

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BrowseError(Exception):
    """`browse_missing` (no executable) or `browse_failed` (non-zero exit or timeout)."""

    def __init__(self, code, message, *, stderr="", timed_out=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stderr = stderr
        self.timed_out = timed_out


def knob(name, default, env=None):
    """A hidden positive-float knob; anything unparsable or non-positive is the default."""
    raw = (os.environ if env is None else env).get(name)
    try:
        v = float(raw) if raw is not None else float(default)
    except (TypeError, ValueError):
        return float(default)
    return v if math.isfinite(v) and v > 0 else float(default)


def locate(env):
    """The browse binary: `VERIFY_READER3_BROWSE`, else gstack's default under `$HOME`."""
    override = env.get("VERIFY_READER3_BROWSE")
    if override:
        return Path(override)
    return Path(env.get("HOME", "")) / ".claude" / "skills" / "gstack" / "browse" / "dist" / "browse"


def check_subcommand(sub, *, passthrough=False):
    if sub in FORBIDDEN:
        raise BrowseRefused(f"browse subcommand {sub!r} is refused: it runs arbitrary JS files")
    if passthrough:
        if not isinstance(sub, str) or not sub:
            raise BrowseRefused("an empty browse subcommand is refused")
        return
    if sub not in ALLOWED:
        raise BrowseRefused(f"browse subcommand {sub!r} is not one of {sorted(ALLOWED)}")


def unwrap(out):
    """The payload inside gstack's untrusted-content envelope; any other text unchanged.

    The envelope counts only when its BEGIN line opens the output and its END line closes it,
    so the `source:` URL on the BEGIN line is never part of the payload.
    """
    lines = out.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if len(lines) >= 2 and _BEGIN.fullmatch(lines[0].rstrip("\r")) and lines[-1].rstrip("\r") == _END:
        return "\n".join(lines[1:-1])
    return out


def _missing(path):
    return BrowseError(
        "browse_missing",
        f"gstack browse binary not found or not executable at {path}; install gstack browse "
        "or point VERIFY_READER3_BROWSE at the binary",
    )


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run(args, *, passthrough=False, timeout=None):
    """Run `browse <args>`; return its stdout (utf-8, errors replaced) or raise."""
    args = [str(a) for a in args]
    check_subcommand(args[0] if args else "", passthrough=passthrough)
    env = dict(os.environ)
    path = locate(env)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        raise _missing(path)
    limit = timeout if timeout is not None else knob("VERIFY_READER3_BROWSE_TIMEOUT_S", DEFAULT_TIMEOUT_S)
    try:
        proc = subprocess.Popen(
            [str(path), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=os.getcwd(), start_new_session=True,
        )
    except OSError:
        raise _missing(path) from None
    try:
        out, err = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = procs.drain(proc, text=False)
        raise BrowseError(
            "browse_failed", f"browse {args[0]} timed out after {limit:g}s and was killed",
            stderr=err.decode("utf-8", errors="replace"), timed_out=True,
        ) from None
    except BaseException:  # noqa: BLE001 - kill the child on any interrupt, then re-raise
        _kill_group(proc)
        procs.drain(proc, text=False)
        raise
    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = stderr.strip()[-STDERR_TAIL:] or "(no stderr)"
        raise BrowseError("browse_failed", f"browse {args[0]} exited {proc.returncode}: {tail}", stderr=stderr)
    return stdout
