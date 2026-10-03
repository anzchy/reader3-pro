"""Repo location, the protected roots, and the guards that keep every command off them.

Two kinds of thing are never touched: a `books/` root (the user's real library), in this
checkout and, for a linked worktree, in the main checkout; and the plaintext key file
`config/ai_settings.json` under the same two roots. The guards decide by realpath,
`stat` and `samefile`. They never open the key file.
"""

import io
import os
import stat
import tempfile
from pathlib import Path

GUARDED_CONFIG_REL = ("config", "ai_settings.json")
SANDBOX_PREFIX = "verify-reader3."
_GITFILE_MAX = 4096


class GuardRefusal(Exception):
    """A refusal: `code` starts with `refused_`; the message names the offending path."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def repo_root():
    """Realpath of the checkout this package lives in (five levels above this file)."""
    return Path(os.path.realpath(Path(os.path.abspath(__file__)).parents[5]))


def _read_gitfile(git):
    # io.FileIO: a bounded raw read of `<repo>/.git` only, after stat says it is a
    # regular file (never a FIFO, never the key file).
    with io.FileIO(str(git), "r") as f:
        return f.read(_GITFILE_MAX)


def main_checkout(repo):
    """The main checkout of a linked worktree, or None. Never spawns, never raises."""
    try:
        git = Path(repo) / ".git"
        if not stat.S_ISREG(os.stat(git).st_mode):
            return None
        lines = _read_gitfile(git).decode("utf-8").splitlines()
        if not lines:
            return None
        first = lines[0].strip()
        if not first.startswith("gitdir:"):
            return None
        gitdir = first[len("gitdir:"):].strip()
        if not gitdir:
            return None
        gd = Path(os.path.normpath(os.path.join(os.path.abspath(repo), gitdir)))
        if gd.name and gd.parent.name == "worktrees" and gd.parent.parent.name == ".git":
            return gd.parent.parent.parent
        return None
    except Exception:  # noqa: BLE001 - contract: an unreadable or odd .git means "no main checkout"
        return None


def checkout_roots(repo=None):
    repo = repo_root() if repo is None else Path(repo)
    roots = [repo]
    main = main_checkout(repo)
    if main is not None:
        roots.append(main)
    return roots


def protected_books_roots(repo=None):
    return [Path(os.path.abspath(r / "books")) for r in checkout_roots(repo)]


def _samefile(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _under_root(real, root):
    if os.path.exists(root):
        cur = real
        while True:
            if os.path.exists(cur) and _samefile(cur, root):
                return True
            parent = os.path.dirname(cur)
            if parent == cur:
                return False
            cur = parent
    rr = os.path.realpath(root)
    return real == rr or real.startswith(rr.rstrip(os.sep) + os.sep)


def books_root_hit(path, repo=None):
    real = os.path.realpath(path)
    for root in protected_books_roots(repo):
        if _under_root(real, str(root)):
            return root
    return None


def guard_books_dir(books_dir, repo=None):
    """Return realpath(books_dir), or raise refused_books_dir if it is under a books root."""
    real = os.path.realpath(books_dir)
    root = books_root_hit(books_dir, repo)
    if root is not None:
        raise GuardRefusal(
            "refused_books_dir",
            f"{real} is inside the protected books root {os.path.realpath(root)}; "
            "verify-reader3 only ever works in a temp sandbox",
        )
    return real


def is_guarded_source(path, repo=None):
    """True iff `path` is under a books root or is the key file of either checkout."""
    if books_root_hit(path, repo) is not None:
        return True
    try:
        st_path = os.stat(path)
    except OSError:
        st_path = None
    real = os.path.realpath(path)
    for root in checkout_roots(repo):
        cfg = os.path.join(str(root), *GUARDED_CONFIG_REL)
        try:
            st_cfg = os.stat(cfg)
        except OSError:
            st_cfg = None
        if st_cfg is not None and st_path is not None:
            if (st_cfg.st_dev, st_cfg.st_ino) == (st_path.st_dev, st_path.st_ino):
                return True
        elif st_cfg is None and real == os.path.realpath(cfg):
            return True
    return False


def sandbox_deletable(path, tempdir):
    """True iff `path` is an existing `verify-reader3.*` dir directly inside `tempdir`."""
    if not isinstance(path, str) or not os.path.isabs(path):
        return False
    r = os.path.realpath(path)
    rt = os.path.realpath(tempdir)
    return (
        os.path.isdir(r)
        and os.path.basename(r).startswith(SANDBOX_PREFIX)
        and _samefile(os.path.dirname(r), rt)
        and r != rt
    )


def evidence_root(env, repo=None):
    v = env.get("VERIFY_READER3_EVIDENCE_ROOT")
    if v:
        return Path(os.path.abspath(v))
    return (repo_root() if repo is None else Path(repo)) / ".claude" / "verify-evidence"


def venv_bin(env, repo=None):
    v = env.get("VERIFY_READER3_VENV_BIN")
    if v:
        return Path(os.path.abspath(v))
    return (repo_root() if repo is None else Path(repo)) / ".venv" / "bin"


def browse_path(env):
    v = env.get("VERIFY_READER3_BROWSE")
    if v:
        return v
    return os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")


def temp_candidates(env):
    """The env temp dirs `tempfile` would consult, in its order (TMPDIR, TEMP, TMP)."""
    return [env[n] for n in ("TMPDIR", "TEMP", "TMP") if env.get(n)]


def temp_root(env):
    """Realpath of the temp dir, without `tempfile.gettempdir()`'s write probe."""
    for cand in temp_candidates(env):
        if os.path.isdir(cand):
            return os.path.realpath(cand)
    return os.path.realpath(tempfile.gettempdir())


def env_float(env, name, default):
    try:
        return float(env.get(name, default))
    except (TypeError, ValueError):
        return float(default)
