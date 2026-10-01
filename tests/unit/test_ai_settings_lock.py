"""018 WI-3 / WI-1: ``ai_settings_transaction`` -- the global settings lock.

Matrix cases R3-1-09 .. R3-1-12, R3-1-14 .. R3-1-16
(``.claude/tdd-guardian/tests-20261001-114124.md``). R3-1-13 lives in
``test_settings_file_permissions.py`` beside the other 0600 cases.

Law: at most one holder is inside the context for a given settings directory at
any time, across threads (each with its own ``open()``) and across processes.
The lock is ``dirname(path)/.ai_settings.lock``, created 0600, held with
``fcntl.flock(LOCK_EX)``, released on every exit path and never unlinked.
``handle.revision()`` is ``settings_revision`` of the bytes on disk *at call
time*, not a value cached on entry.

Every case passes an explicit ``tmp_path`` settings path, and an autouse
``chdir`` into ``tmp_path`` backs that up: the default path is the relative
``config/ai_settings.json``, so a forgotten argument lands in tmp, not in the
developer's ``config/``. The one case that looks at the real repo (R3-1-16)
only asks git whether a path is ignored; it neither creates nor locks it.
"""

from __future__ import annotations

import fcntl
import itertools
import json
import multiprocessing as mp
import os
import shutil
import stat
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from ai_settings_lock_worker import rmw_under_transaction
from reader3_app.ai.config import (
    AiSettingsError,
    AiSettingsTransaction,
    ai_settings_transaction,
    default_settings_dict,
    load_ai_settings,
    save_ai_settings,
    settings_revision,
)

LOCK_NAME = ".ai_settings.lock"


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


@pytest.fixture(autouse=True)
def _cwd_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _default_umask():
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    d = tmp_path / "cfg"
    d.mkdir()
    return d / "ai_settings.json"


def _try_lock(lock: Path) -> bool:
    """Try ``LOCK_EX|LOCK_NB`` on a fresh open file description. True if acquired."""
    fd = os.open(lock, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    finally:
        os.close(fd)


# --------------------------------------------------------------------------
# R3-1-09 -- S2: lock file location, mode and persistence
# --------------------------------------------------------------------------


def test_lock_file_is_0600_beside_settings_and_never_unlinked(settings_path: Path) -> None:
    cfg = settings_path.parent
    lock = cfg / LOCK_NAME
    assert not lock.exists() and not settings_path.exists()

    with ai_settings_transaction(str(settings_path)):
        assert lock.exists(), "the lock file must sit beside the settings file"
        assert _mode(lock) == 0o600, f"lock file mode {_mode(lock):#o}"
        assert set(os.listdir(cfg)) == {LOCK_NAME}

    assert lock.exists(), "the lock file must never be unlinked"
    assert _mode(lock) == 0o600
    assert not settings_path.exists(), "entering the transaction must not create the settings file"
    assert set(os.listdir(cfg)) == {LOCK_NAME}


# --------------------------------------------------------------------------
# R3-1-10 -- S3: lock released when the body raises
# --------------------------------------------------------------------------


def test_lock_released_after_exception(settings_path: Path) -> None:
    lock = settings_path.parent / LOCK_NAME
    with pytest.raises(RuntimeError) as exc:
        with ai_settings_transaction(str(settings_path)):
            raise RuntimeError("boom")

    assert exc.value.args == ("boom",)
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises BlockingIOError if still held
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    assert lock.exists()


# --------------------------------------------------------------------------
# R3-1-11 -- S2: the lock is actually held while inside (anti-no-op)
# --------------------------------------------------------------------------


def test_lock_is_held_inside_the_context(settings_path: Path) -> None:
    lock = settings_path.parent / LOCK_NAME
    with ai_settings_transaction(str(settings_path)):
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)

    assert _try_lock(lock) is True, "the lock is still held after the context exited"


# --------------------------------------------------------------------------
# R3-1-12 -- S5: handle.revision() tracks the bytes on disk inside the transaction
# --------------------------------------------------------------------------


def test_handle_revision_reflects_current_bytes(settings_path: Path) -> None:
    p = str(settings_path)
    with ai_settings_transaction(p) as h:
        step0 = h.revision()
        assert step0 == settings_revision(None)

        save_ai_settings(default_settings_dict(), path=p)
        step1 = h.revision()
        assert step1 == settings_revision(settings_path.read_bytes())
        assert step1 != step0

        s = default_settings_dict()
        s["preferences"]["theme"] = "dark"
        save_ai_settings(s, path=p)
        step2 = h.revision()
        assert step2 == settings_revision(settings_path.read_bytes())
        assert step2 != step1


# --------------------------------------------------------------------------
# R3-1-14 -- S5: thread mutual exclusion via ordered events
# --------------------------------------------------------------------------


def test_threads_are_serialized(settings_path: Path) -> None:
    p = str(settings_path)
    seq = itertools.count()
    seq_lock = threading.Lock()
    record: Dict[str, int] = {}
    errors: List[BaseException] = []

    a_in = threading.Event()
    release_a = threading.Event()
    b_entered = threading.Event()

    def next_seq() -> int:
        with seq_lock:
            return next(seq)

    def thread_a() -> None:
        try:
            with ai_settings_transaction(p):
                a_in.set()
                release_a.wait(5)
                record["a_exit_seq"] = next_seq()
        except BaseException as e:  # pragma: no cover - surfaced below
            errors.append(e)

    def thread_b() -> None:
        try:
            with ai_settings_transaction(p):
                record["b_enter_seq"] = next_seq()
                b_entered.set()
        except BaseException as e:  # pragma: no cover - surfaced below
            errors.append(e)

    ta = threading.Thread(target=thread_a, daemon=True)
    ta.start()
    assert a_in.wait(5), "thread A never entered the transaction"

    tb = threading.Thread(target=thread_b, daemon=True)
    tb.start()
    try:
        assert not b_entered.wait(0.3), "thread B entered while thread A held the transaction"
    finally:
        release_a.set()
    assert b_entered.wait(5), "thread B never entered after A released"

    ta.join(5)
    tb.join(5)
    assert not ta.is_alive() and not tb.is_alive()
    assert errors == []
    assert record["a_exit_seq"] < record["b_enter_seq"], record


# --------------------------------------------------------------------------
# R3-1-15 -- S5: cross-process conservation of N disjoint updates
# --------------------------------------------------------------------------

PROVIDERS = ("anthropic", "openai", "gemini", "ollama", "openrouter")
ITERATIONS = 20
JOIN_TIMEOUT_S = 60


def test_processes_conserve_all_updates(settings_path: Path) -> None:
    p = str(settings_path)
    save_ai_settings(default_settings_dict(), path=p)

    ctx = mp.get_context("spawn")
    start = ctx.Event()
    procs = [
        ctx.Process(target=rmw_under_transaction, args=(p, prov, i, ITERATIONS, start))
        for i, prov in enumerate(PROVIDERS)
    ]
    for proc in procs:
        proc.start()
    start.set()
    for proc in procs:
        proc.join(JOIN_TIMEOUT_S)

    alive = [proc.pid for proc in procs if proc.is_alive()]
    for proc in procs:
        if proc.is_alive():
            proc.kill()
    assert not alive, f"child writer(s) did not finish within {JOIN_TIMEOUT_S}s: {alive}"
    assert [proc.exitcode for proc in procs] == [0] * len(PROVIDERS)

    with open(settings_path, encoding="utf-8") as f:
        on_disk = json.load(f)
    got = {prov: on_disk["providers"][prov]["model_name"] for prov in PROVIDERS}
    want = {prov: f"w{i}-{ITERATIONS - 1}" for i, prov in enumerate(PROVIDERS)}
    assert got == want, "a locked read-modify-write lost another writer's update"
    assert _mode(settings_path) == 0o600
    leftovers = [n for n in os.listdir(settings_path.parent) if n.startswith(".ai_settings.") and n.endswith(".tmp")]
    assert leftovers == []
    # Sanity: the file round-trips through the public loader.
    assert load_ai_settings(path=p)["providers"]["ollama"]["model_name"] == want["ollama"]


# --------------------------------------------------------------------------
# R3-1-16 -- S1: .gitignore covers the repo lock file
# --------------------------------------------------------------------------


def _git() -> Optional[str]:
    return shutil.which("git")


def test_repo_lock_path_is_git_ignored(repo_root: Path) -> None:
    git = _git()
    if git is None:
        pytest.skip("git is not installed")
    inside = subprocess.run(
        [git, "rev-parse", "--is-inside-work-tree"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not inside a git work tree")

    proc = subprocess.run(
        [git, "check-ignore", "-q", "config/.ai_settings.lock"],
        cwd=repo_root,
        timeout=10,
    )
    assert proc.returncode == 0, "config/.ai_settings.lock is not git-ignored"


# --------------------------------------------------------------------------
# 018 WI-3 review fix-up M1: the lock cannot be created
#
# A writer must fail with an AiSettingsError that names the lock path (the app
# maps it to the named 500). A reader that opts in with ``lock_optional=True``
# falls back to an unlocked read: os.replace already makes that read consistent.
# --------------------------------------------------------------------------


@pytest.fixture
def unwritable_dir(settings_path: Path):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write permission")
    settings_path.write_bytes(b'{"preferences": {"theme": "dark"}}')
    cfg = settings_path.parent
    os.chmod(cfg, 0o500)
    try:
        yield cfg
    finally:
        os.chmod(cfg, 0o700)


def test_lock_creation_failure_raises_ai_settings_error_naming_the_lock(settings_path: Path, unwritable_dir: Path) -> None:
    lock = unwritable_dir / LOCK_NAME
    entered = False
    with pytest.raises(AiSettingsError) as exc:
        with ai_settings_transaction(str(settings_path)):
            entered = True
    assert entered is False
    assert str(lock) in str(exc.value)
    assert isinstance(exc.value.__cause__, OSError)
    assert not lock.exists()


def test_lock_directory_creation_failure_raises_ai_settings_error(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"")
    target = blocker / "cfg" / "ai_settings.json"
    with pytest.raises(AiSettingsError) as exc:
        with ai_settings_transaction(str(target)):
            pass  # pragma: no cover - must not be reached
    assert str(blocker / "cfg" / LOCK_NAME) in str(exc.value)


def test_lock_optional_falls_back_to_an_unlocked_read(settings_path: Path, unwritable_dir: Path) -> None:
    raw = settings_path.read_bytes()
    with ai_settings_transaction(str(settings_path), lock_optional=True) as h:
        assert h.read_raw() == raw
        assert h.revision() == settings_revision(raw)
    assert not (unwritable_dir / LOCK_NAME).exists()


def test_lock_optional_still_locks_when_it_can(settings_path: Path) -> None:
    lock = settings_path.parent / LOCK_NAME
    with ai_settings_transaction(str(settings_path), lock_optional=True):
        assert _try_lock(lock) is False, "lock_optional must still hold the lock when it can be created"
    assert _try_lock(lock) is True


# --------------------------------------------------------------------------
# 018 WI-3 coverage fix-up: read_raw turns an OSError into a named AiSettingsError
# --------------------------------------------------------------------------


def test_read_raw_on_a_directory_raises_ai_settings_error_naming_the_path(tmp_path: Path) -> None:
    target = tmp_path / "ai_settings.json"
    target.mkdir()
    with pytest.raises(AiSettingsError) as exc:
        AiSettingsTransaction(str(target)).read_raw()
    assert str(target) in str(exc.value)
    assert isinstance(exc.value.__cause__, OSError)
