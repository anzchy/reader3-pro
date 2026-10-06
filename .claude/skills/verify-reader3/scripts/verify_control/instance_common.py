"""Helpers shared by `up`, `doctor` and `down`: failure plumbing, knobs, state loading."""

import os

from verify_control import paths, state
from verify_control.envelope import TRY_PREFIX, failure

SERVER_MARK, STUB_MARK = "reader3-server", "ai_stub_runner.py"


class Fail(Exception):
    def __init__(self, env):
        super().__init__(env["error"]["code"])
        self.env = env


def fail(cmd, code, message, tail, data=None):
    return Fail(failure(cmd, code, message, TRY_PREFIX + tail, data=data))


def knob(name, default):
    return paths.env_float(os.environ, name, default)


def setup(cmd):
    """Repo, evidence root (guarded first) and pointer path for any command."""
    repo = paths.repo_root()
    ev_root = paths.evidence_root(os.environ, repo)
    paths.guard_books_dir(str(ev_root), repo)
    return repo, ev_root, ev_root / state.POINTER_NAME


def resolve(cmd, ns, pointer, *, use_env=True):
    env = os.environ if use_env else {}
    try:
        return state.resolve(getattr(ns, "state", None), env, pointer)
    except state.StateError as exc:
        raise fail(cmd, exc.code, exc.message, "down") from None


def load(cmd, sp, repo, *, allow_missing=False, context=""):
    try:
        return state.load(sp, repo=repo, allow_missing_sandbox=allow_missing)
    except state.StateError as exc:
        raise fail(cmd, exc.code, exc.message, "down --dry-run") from None
    except paths.GuardRefusal as exc:
        raise fail(cmd, exc.code, context + exc.message, "down") from None


def run(cmd, body):
    try:
        return body()
    except Fail as f:
        return f.env
    except paths.GuardRefusal as exc:
        return failure(cmd, exc.code, exc.message, TRY_PREFIX + "doctor")


def is_exe(p):
    return os.path.isfile(p) and os.access(p, os.X_OK)
