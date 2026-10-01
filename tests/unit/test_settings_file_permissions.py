"""WI-29: an ``ai_settings.json`` that already exists must be tightened to 0600.

WI-4 rewrote ``save_ai_settings`` as ``tempfile.mkstemp`` + ``os.replace``.
``mkstemp`` creates its file 0600 and ``os.replace`` keeps the *tmp* file's
permission bits, so a **newly created** settings file is already 0600. That half
works, and Y2 below is the regression fence for it.

The other half does not. "``os.replace`` keeps the tmp file's bits" is exactly
why an **existing** file is never tightened: replace does not consult, and does
not preserve, the destination's mode -- but a file created before the WI-4 fix
(this developer's own ``config/ai_settings.json`` is ``-rw-r--r--`` right now)
stays world-readable until the user happens to press save. That file holds
provider API keys in plaintext. Y1 is the load-bearing case: it pins the *mode*,
via ``stat.S_IMODE``, not "the call did not raise".

Y4 pins the other side of the fix. The tightening belongs in the **write** path
only. Doing it in ``load_ai_settings`` would look like a faster fix -- every
read would repair the file -- and it is the same mistake as ``web/C11`` (a GET
that writes to disk): a read with a side effect. The cost of keeping reads pure
is a delay, not a hole: a pre-existing 0644 file stays 0644 until the next save.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 the file's mode *and* bytes across a whole call

Every case runs under ``tmp_path`` and passes ``path=`` explicitly. Two further
fences, both deliberate rather than redundant: an autouse ``chdir`` into
``tmp_path`` (``DEFAULT_SETTINGS_PATH`` is a *relative* path bound at import
time, so a forgotten ``path=`` would land on the developer's real keys), and an
autouse check that the real ``config/ai_settings.json`` is byte- and
mode-identical afterwards -- the fix under test is itself a ``chmod``, so
"nothing was written" is no longer a strong enough fence on its own.

``umask`` is set explicitly: ``mkstemp`` is unaffected by it, but a file this
module creates with ``open()`` is, so "0644 by default" is not an assumption
worth making.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from reader3_app.ai.config import (
    ai_settings_transaction,
    default_settings_dict,
    load_ai_settings,
    save_ai_settings,
)


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def _fixed_umask():
    """Pin the umask, then put the developer's own back.

    Only matters for the files *this module* creates by hand; ``mkstemp`` opens
    with an explicit 0600 and does not go through the umask. Pinned anyway so
    that ``chmod(0o644)`` below starts from a known state on any machine.
    """
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


@pytest.fixture(autouse=True)
def _never_write_outside_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Backstop for a forgotten ``path=``.

    ``DEFAULT_SETTINGS_PATH`` is ``config/ai_settings.json`` -- relative, and
    bound at import time as a default argument. With cwd inside ``tmp_path`` a
    slip creates ``tmp_path/config/ai_settings.json`` instead of touching the
    developer's keys.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _never_touch_the_real_settings_file(repo_root: Path):
    """The real settings file must come out byte- *and* mode-identical.

    The mode half is not decoration: the change under test is a ``chmod``, and a
    test that leaked onto the real file could silently rewrite its permissions
    while leaving every byte intact.
    """
    real = repo_root / "config" / "ai_settings.json"

    def snapshot():
        if not real.exists():
            return (False, None, None)
        return (True, real.read_bytes(), stat.S_IMODE(os.stat(real).st_mode))

    before = snapshot()
    yield
    after = snapshot()
    assert after[0] == before[0], f"a test created or deleted the real settings file: {real}"
    assert after[1] == before[1], f"a test rewrote the real settings file: {real}"
    assert after[2] == before[2], (
        f"a test changed the permissions of the real settings file: {real} "
        f"({before[2]!r} -> {after[2]!r})"
    )


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    d = tmp_path / "userconfig"
    d.mkdir()
    return d / "ai_settings.json"


def _settings_with_keys() -> dict:
    s = default_settings_dict()
    s["providers"]["anthropic"]["api_key"] = "sk-REAL-ANTHROPIC"
    s["providers"]["openai"]["api_key"] = "sk-REAL-OPENAI"
    return s


# --------------------------------------------------------------------------
# Y1 -- L3/S2: THE load-bearing case. A file that predates the fix gets
# tightened by the next save, and the assertion is on the mode bits.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "existing_mode",
    [
        pytest.param(0o644, id="world-readable"),
        pytest.param(0o664, id="group-writable"),
        pytest.param(0o666, id="world-writable"),
    ],
)
def test_existing_loose_settings_file_is_tightened_to_0600_on_save(
    settings_path: Path, existing_mode: int
) -> None:
    settings_path.write_text(json.dumps(default_settings_dict()), encoding="utf-8")
    os.chmod(settings_path, existing_mode)
    assert _mode(settings_path) == existing_mode, "precondition: the file starts loose"

    save_ai_settings(_settings_with_keys(), path=str(settings_path))

    assert _mode(settings_path) == 0o600, (
        "a settings file created before the fix holds plaintext API keys readable "
        f"by every user on the machine; saving must tighten it, got "
        f"{_mode(settings_path):#o}"
    )


# --------------------------------------------------------------------------
# Y2 -- L2/S1: regression fence for what WI-4 already bought.
# --------------------------------------------------------------------------

def test_newly_created_settings_file_is_0600(settings_path: Path) -> None:
    assert not settings_path.exists()

    save_ai_settings(_settings_with_keys(), path=str(settings_path))

    assert _mode(settings_path) == 0o600, (
        f"a freshly written credential file must not be readable by others, got "
        f"{_mode(settings_path):#o}"
    )


# --------------------------------------------------------------------------
# Y3 -- L2/S1: tightening the mode must not disturb the contents.
# --------------------------------------------------------------------------

def test_tightening_permissions_does_not_damage_the_contents(settings_path: Path) -> None:
    settings_path.write_text(json.dumps(default_settings_dict()), encoding="utf-8")
    os.chmod(settings_path, 0o644)
    written = _settings_with_keys()

    save_ai_settings(written, path=str(settings_path))

    assert load_ai_settings(path=str(settings_path)) == written, (
        "the file read back after a save must be exactly what was saved"
    )
    assert json.loads(settings_path.read_text(encoding="utf-8")) == written


# --------------------------------------------------------------------------
# Y4 -- L3/S2: load is a read. The repair belongs to the write path only.
# --------------------------------------------------------------------------

def test_load_ai_settings_leaves_permissions_and_bytes_alone(settings_path: Path) -> None:
    settings_path.write_text(json.dumps(_settings_with_keys()), encoding="utf-8")
    os.chmod(settings_path, 0o644)
    mode_before, md5_before = _mode(settings_path), _md5(settings_path)

    load_ai_settings(path=str(settings_path))

    assert _mode(settings_path) == mode_before, (
        "load_ai_settings must not chmod: a read that repairs the file on the way "
        "past is the web/C11 bug (a GET that writes to disk). A pre-existing loose "
        f"file is tightened by the next *save*, not by being read; got "
        f"{_mode(settings_path):#o}"
    )
    assert _md5(settings_path) == md5_before, "load_ai_settings must not rewrite the file"


def test_load_ai_settings_of_a_missing_file_creates_nothing(settings_path: Path) -> None:
    """The same rule at the other end: reading an absent file writes no file."""
    assert not settings_path.exists()

    load_ai_settings(path=str(settings_path))

    assert not settings_path.exists(), "load_ai_settings must not create the settings file"


# --------------------------------------------------------------------------
# R3-1-13 (018 WI-3) -- S2: a save inside the settings transaction stays 0600.
# The lock is held around the write; nothing about holding it may loosen the
# credential file, and the lock file beside it is 0600 too.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pre_state", ["absent", "existing-0644"])
def test_save_inside_transaction_keeps_0600(settings_path: Path, pre_state: str) -> None:
    if pre_state == "existing-0644":
        settings_path.write_text(json.dumps(default_settings_dict()), encoding="utf-8")
        os.chmod(settings_path, 0o644)
        assert _mode(settings_path) == 0o644, "precondition: the file starts loose"
    else:
        assert not settings_path.exists()

    with ai_settings_transaction(str(settings_path)):
        save_ai_settings(default_settings_dict(), path=str(settings_path))

    assert _mode(settings_path) == 0o600, f"got {_mode(settings_path):#o}"
    lock = settings_path.parent / ".ai_settings.lock"
    assert _mode(lock) == 0o600, f"lock file mode {_mode(lock):#o}"
