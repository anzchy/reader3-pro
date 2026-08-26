"""WI-8: preferences the user already saved must never be reset to factory values.

Two halves of one loss path, read and write:

* **Read** (`ai/config._merge_defaults`): `providers` gets a two-level merge,
  `preferences` gets none -- `merged.update(...)` replaces the whole block. A
  file holding `{"preferences": {"theme": "dark"}}` therefore loses
  `conversation_disk_storage`, `max_conversation_length` and
  `conversation_project_root_dir` on the way in, which silently changes where
  chat transcripts are written.
* **Write** (`web/server.api_put_settings`): the route loads the existing
  settings on its first line and then throws them away, rebuilding
  `preferences` from `default_settings_dict()` plus the incoming patch. A
  front-end that sends `{"preferences": {"theme": "dark"}}` resets every other
  preference **on disk**. `/api/settings/import` in the same file already does
  it correctly (defaults -> existing -> patch).

The load-bearing cases (P2, P4) assert the values **on disk**, read back with
`json.load`. The HTTP response is not evidence here: it is
`_public_settings_response(load_ai_settings())`, and both of those re-fill
defaults, so a preference that was wiped from the file but happens to equal its
default is invisible in the response body. The finding is about the persisted
copy.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 the on-disk `preferences` block, key by key, across a full cycle

Every case writes under ``tmp_path``. The developer's real
``config/ai_settings.json`` is fenced by md5 in an autouse fixture below --
``DEFAULT_SETTINGS_PATH`` is a *default argument* bound at import time, so
setting ``READER3_AI_SETTINGS`` alone does not redirect anything that is already
imported; the fixtures below redirect what the code actually consults.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from reader3_app.ai import config as ai_config
from reader3_app.ai.config import default_settings_dict, load_ai_settings


@pytest.fixture(autouse=True)
def _never_touch_the_real_settings_file(repo_root: Path):
    """The real ``config/ai_settings.json`` must be unchanged before and after."""
    real = repo_root / "config" / "ai_settings.json"

    def fingerprint() -> tuple:
        if not real.exists():
            return (False, None)
        return (True, hashlib.md5(real.read_bytes()).hexdigest())

    before = fingerprint()
    yield
    assert fingerprint() == before, f"a test touched the real settings file: {real}"


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every path the settings code could resolve to, at once."""
    path = tmp_path / "config" / "ai_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("READER3_AI_SETTINGS", str(path))
    # Read at import time into a module global *and* frozen into the default
    # argument of load/save; rebinding the global is not enough on its own,
    # which is why the route fixture below also rebinds the functions.
    monkeypatch.setattr(ai_config, "DEFAULT_SETTINGS_PATH", str(path))
    return path


def _write_settings_file(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _prefs_on_disk(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["preferences"]


@pytest.fixture
def client(settings_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A TestClient whose settings I/O is bound to ``settings_path``.

    ``server`` imported ``load_ai_settings``/``save_ai_settings`` by name and
    calls them with no arguments, so the tmp path is bound here with
    ``functools.partial`` -- the real implementations still run, which matters
    because the read-side merge under test lives inside ``load_ai_settings``.

    The startup hook is aimed at an empty directory: it calls
    ``ensure_book_uuid`` on every folder in ``books/``, and no test may write
    into the developer's real library.
    """
    from fastapi.testclient import TestClient

    from reader3_app.web import server

    monkeypatch.setattr(
        server, "load_ai_settings", functools.partial(ai_config.load_ai_settings, path=str(settings_path))
    )
    monkeypatch.setattr(
        server, "save_ai_settings", functools.partial(ai_config.save_ai_settings, path=str(settings_path))
    )
    monkeypatch.setattr(
        server.book_uuid_resolver, "books_dir", str(settings_path.parent / "no-books-here")
    )

    with TestClient(server.app, base_url="http://127.0.0.1") as c:
        yield c


FULL_PREFS_PATCH = {
    "theme": "dark",
    "max_conversation_length": 42,
    "show_timestamps": False,
    "auto_suggest_questions": True,
    "streaming_enabled": True,
    "conversation_disk_storage": "both",
    "conversation_project_root_dir": "conversations",
}


# --------------------------------------------------------------------------
# P1 -- L2/S1: a partial preferences block must not evict the defaults
# --------------------------------------------------------------------------

def test_partial_preferences_file_keeps_the_default_keys(settings_path: Path) -> None:
    _write_settings_file(settings_path, {"preferences": {"theme": "dark"}})

    prefs = load_ai_settings(path=str(settings_path))["preferences"]

    assert prefs["theme"] == "dark"
    assert prefs["conversation_disk_storage"] == "per_book"
    assert prefs["max_conversation_length"] == 500
    assert prefs["conversation_project_root_dir"] == "conversations"


# --------------------------------------------------------------------------
# P2 -- L3/S2: LOAD-BEARING. Reading must not change where chats are stored.
# --------------------------------------------------------------------------

def test_reading_a_partial_preferences_file_does_not_change_the_storage_mode(
    settings_path: Path,
) -> None:
    """P1 proves the defaults survive; this proves the user's value survives too.

    Both directions in one case, so that a "merge" that got the precedence
    backwards -- defaults winning over the file -- cannot pass by keeping every
    key present.
    """
    _write_settings_file(
        settings_path,
        {"preferences": {"conversation_disk_storage": "both", "theme": "dark"}},
    )

    prefs = load_ai_settings(path=str(settings_path))["preferences"]

    assert prefs["conversation_disk_storage"] == "both", (
        "the user asked for 'both'; a read that hands back 'per_book' silently "
        "moves every future transcript to a different location"
    )
    assert prefs["streaming_enabled"] is True, (
        "a default key was evicted by the file's partial preferences block"
    )


# --------------------------------------------------------------------------
# P3 -- L2/S1: a one-key PUT patch must not disturb the other preferences
# --------------------------------------------------------------------------

def test_single_key_put_patch_leaves_the_other_preferences_alone(client) -> None:
    first = client.put("/api/settings", json={"preferences": dict(FULL_PREFS_PATCH)})
    assert first.status_code == 200
    assert first.json()["preferences"]["max_conversation_length"] == 42

    resp = client.put("/api/settings", json={"preferences": {"theme": "light"}})

    assert resp.status_code == 200
    prefs = resp.json()["preferences"]
    assert prefs["theme"] == "light"
    assert prefs["max_conversation_length"] == 42
    assert prefs["show_timestamps"] is False


# --------------------------------------------------------------------------
# P4 -- L3/S2: LOAD-BEARING. After that patch, the file itself is unchanged
#              except for the one key that was patched.
# --------------------------------------------------------------------------

def test_after_a_single_key_patch_the_other_preferences_on_disk_are_untouched(
    client, settings_path: Path
) -> None:
    """P3 only inspects the response body, which re-fills defaults on the way
    out. This reads ``ai_settings.json`` back and compares key by key, because
    the finding is about the *persisted* preferences being reset."""
    client.put("/api/settings", json={"preferences": dict(FULL_PREFS_PATCH)})
    snapshot = _prefs_on_disk(settings_path)
    assert snapshot["max_conversation_length"] == 42, "precondition: the non-default value is on disk"

    client.put("/api/settings", json={"preferences": {"theme": "light"}})

    after = _prefs_on_disk(settings_path)
    assert after["theme"] == "light"
    for key, expected in snapshot.items():
        if key == "theme":
            continue
        assert after.get(key) == expected, (
            f"preferences.{key} on disk changed from {expected!r} to {after.get(key)!r} "
            "after a patch that only mentioned 'theme'"
        )
    assert set(after) >= set(snapshot), (
        f"keys vanished from the saved preferences: {sorted(set(snapshot) - set(after))}"
    )


# --------------------------------------------------------------------------
# P5 -- L2/S1: a default_provider-only patch must not touch preferences at all
# --------------------------------------------------------------------------

def test_default_provider_patch_leaves_preferences_untouched_on_disk(
    client, settings_path: Path
) -> None:
    client.put("/api/settings", json={"preferences": dict(FULL_PREFS_PATCH)})
    snapshot = _prefs_on_disk(settings_path)

    resp = client.put("/api/settings", json={"default_provider": "openai"})
    assert resp.status_code == 200

    after = _prefs_on_disk(settings_path)
    for key, expected in snapshot.items():
        assert after.get(key) == expected, (
            f"preferences.{key} on disk changed from {expected!r} to {after.get(key)!r} "
            "after a patch that carried no preferences at all"
        )
    assert set(after) == set(snapshot)
    assert default_settings_dict()["preferences"].keys() <= after.keys(), (
        "the saved preferences lost keys that every fresh install has"
    )
