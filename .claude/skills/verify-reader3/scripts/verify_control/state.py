"""The instance state file, the pointer to it, and the single-`up` claim.

State lives in `<sandbox>/state.json`; the pointer `<evidence_root>/instance.json` holds
`{"state": <abs path>}`. Resolution order: `--state`, then `VERIFY_READER3_STATE`, then
the pointer. `load` re-checks every recorded path before any command acts on it.
"""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from verify_control import paths
from verify_control.http_client import validate_base_url

KEYS = (
    "sandbox", "books_dir", "ai_settings", "port", "base_url", "pid", "pid_start", "argv",
    "log", "token", "stub_pid", "stub_pid_start", "stub_port", "repo",
)
_STR = ("sandbox", "books_dir", "ai_settings", "log", "repo", "base_url")
_OPT_INT = ("port", "pid", "stub_pid", "stub_port")
_OPT_STR = ("pid_start", "token", "stub_pid_start")
POINTER_NAME = "instance.json"
CLAIM_NAME = "instance.claim"


class StateError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check(d, where):
    def bad(why):
        raise StateError("bad_state", f"{where}: {why}")

    if not isinstance(d, dict):
        bad("not a JSON object")
    missing = [k for k in KEYS if k not in d]
    if missing:
        bad(f"missing keys {missing}")
    for k in _STR:
        if not isinstance(d[k], str):
            bad(f"{k} must be a string")
    for k in _OPT_INT:
        if d[k] is not None and not _is_int(d[k]):
            bad(f"{k} must be an integer or null")
    for k in _OPT_STR:
        if d[k] is not None and not isinstance(d[k], str):
            bad(f"{k} must be a string or null")
    if not isinstance(d["argv"], list) or not all(isinstance(a, str) for a in d["argv"]):
        bad("argv must be a list of strings")
    if d["stub_pid"] is not None and d["stub_pid_start"] is None:
        bad("stub_pid is set but stub_pid_start is not")
    return d


def atomic_write_json(path, obj):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".vc.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=True)
        os.replace(tmp, path)
    except BaseException:  # noqa: BLE001 - remove the temp file on any failure, then re-raise
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def write(path, d):
    atomic_write_json(path, _check(dict(d), str(path)))


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as exc:
        raise StateError("bad_state", f"{path}: unreadable state ({exc})") from None
    return _check(d, str(path))


def _shape(msg):
    return paths.GuardRefusal("refused_sandbox_shape", msg)


def load(path, *, repo, allow_missing_sandbox=False):
    """Read and vet a state file: books guard, sandbox shape, tied paths, then URL."""
    d = read(path)
    sbx = d["sandbox"]
    paths.guard_books_dir(d["books_dir"], repo)
    paths.guard_books_dir(os.path.join(sbx, "books"), repo)
    where = f"state {path}: sandbox {sbx!r}"
    if not os.path.isabs(sbx):
        raise _shape(f"{where} is not absolute")
    if allow_missing_sandbox and not os.path.lexists(sbx):
        pass
    elif os.path.islink(sbx) or not os.path.isdir(sbx):
        raise _shape(f"{where} is a symlink, missing or not a directory")
    if not os.path.basename(sbx).startswith(paths.SANDBOX_PREFIX):
        raise _shape(f"{where} is not a {paths.SANDBOX_PREFIX}* directory")
    for key, suffix in (("log", "/server.log"), ("ai_settings", "/ai_settings.json"), ("books_dir", "/books")):
        if d[key] != sbx + suffix:
            raise _shape(f"{where}: {key} {d[key]!r} is not {sbx + suffix!r}")
    if validate_base_url(d["base_url"]) != d["port"]:
        raise paths.GuardRefusal("refused_url", f"base_url {d['base_url']!r} does not match port {d['port']!r}")
    return d


def pointer_path(env, repo):
    return paths.evidence_root(env, repo) / POINTER_NAME


def write_pointer(root, state_path):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root / POINTER_NAME, {"state": os.path.abspath(str(state_path))})


def clear_pointer(root):
    try:
        os.unlink(Path(root) / POINTER_NAME)
        return True
    except FileNotFoundError:
        return False


def read_pointer(pointer):
    if not os.path.lexists(pointer):
        return None
    try:
        with open(pointer, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError) as exc:
        raise StateError("bad_pointer", f"pointer {pointer} is unreadable ({exc})") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("state"), str) or not obj["state"]:
        raise StateError("bad_pointer", f"pointer {pointer} has no state path")
    return obj["state"]


def resolve(cli_state, env, pointer):
    if cli_state:
        return cli_state
    if env.get("VERIFY_READER3_STATE"):
        return env["VERIFY_READER3_STATE"]
    return read_pointer(pointer)


class Claim:
    """`<evidence_root>/instance.claim` under a non-blocking flock; unlinked on release."""

    def __init__(self, root):
        self.path = Path(root) / CLAIM_NAME
        self.fd = None

    def acquire(self, owner):
        """True on success, False when another live process holds the claim."""
        while True:
            fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return False
            try:
                same = os.fstat(fd).st_ino == os.stat(str(self.path)).st_ino
            except FileNotFoundError:
                same = False
            if not same:
                os.close(fd)
                continue
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps(owner).encode("utf-8"))
            self.fd = fd
            return True

    def holder(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def release(self):
        if self.fd is None:
            return
        try:
            os.unlink(str(self.path))
        except FileNotFoundError:
            pass
        os.close(self.fd)
        self.fd = None
