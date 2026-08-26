"""WI-4: a settings file we cannot read must never be reported as "no keys", and
never overwritten.

`ai_settings.json` is where every provider API key lives. The old code read it
through `except Exception: return default_settings_dict()`, so a file that
existed but could not be parsed was indistinguishable from a file that was never
written: the settings page showed "not configured", the user retyped one
provider and pressed save, and `save_ai_settings` -- a plain `open(path, "w")`,
non-atomic, unlike `ensure_book_uuid` and the conversation store which both do
tmp + `os.replace` -- flattened the whole file with defaults. Every other
provider's key was gone, with no error anywhere.

The rule this module pins down is the one `ensure_book_uuid` already follows:
**user data we cannot read is not "absent"**. A 500 is recoverable; a deleted
API key is not.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 the file's bytes before and after a whole read-modify-write cycle
    L4 fault injection -- corrupt file, crash midway through the write

Every case writes under ``tmp_path`` and passes ``path=`` explicitly; the real
``config/ai_settings.json`` is fenced by ``_never_touch_the_real_settings_file``
below, because a test that leaked onto it would do the exact damage under test.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from reader3_app.ai import config as ai_config
from reader3_app.ai.config import (
    AiSettingsError,
    default_settings_dict,
    load_ai_settings,
    save_ai_settings,
)

#: The key the user already had. Asserted as raw bytes on disk, so that
#: "the file was rewritten but happens to still contain the string" cannot pass.
REAL_KEY = "sk-REAL"

#: Appended to a *valid* document. The original text stays in the file, readable
#: by a human -- which is the whole point: a person can fix this, they cannot
#: un-delete a key.
CORRUPTING_SUFFIX = "\n}}] <- trailing garbage, this file is no longer JSON\n"


@pytest.fixture(autouse=True)
def _never_touch_the_real_settings_file(repo_root: Path):
    """The real ``config/ai_settings.json`` must be byte-identical afterwards.

    ``DEFAULT_SETTINGS_PATH`` is a *default argument*, bound at import time, so a
    test that forgets ``path=`` silently operates on the developer's own keys.
    """
    real = repo_root / "config" / "ai_settings.json"
    before = (real.exists(), real.read_bytes() if real.exists() else None)
    yield
    after = (real.exists(), real.read_bytes() if real.exists() else None)
    assert after == before, f"a test touched the real settings file: {real}"


@pytest.fixture
def settings_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def settings_path(settings_dir: Path) -> Path:
    return settings_dir / "ai_settings.json"


def _settings_with_real_keys() -> dict:
    s = default_settings_dict()
    s["providers"]["anthropic"]["api_key"] = REAL_KEY
    s["providers"]["openai"]["api_key"] = "sk-OTHER-REAL"
    return s


# --------------------------------------------------------------------------
# A1 -- L2/S1: a file that exists but cannot be read is an error, not a default
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("{ not json", id="invalid-json"),
        pytest.param('[{"providers": {}}]', id="top-level-list"),
        pytest.param('"just a string"', id="top-level-string"),
    ],
)
def test_unreadable_settings_file_raises_and_names_the_file(settings_path: Path, raw: str) -> None:
    settings_path.write_text(raw, encoding="utf-8")

    with pytest.raises(AiSettingsError) as exc:
        load_ai_settings(path=str(settings_path))

    assert str(settings_path) in str(exc.value), (
        "the error must name the file, or the user has no way to find what to fix"
    )


# --------------------------------------------------------------------------
# A2 -- L3/S2: THE load-bearing case. One read-modify-write over a corrupt file
#              must not cost the user a single key.
# --------------------------------------------------------------------------

def test_one_read_modify_write_over_a_corrupt_file_loses_no_api_key(settings_path: Path) -> None:
    """The finding itself: corrupt file -> UI says "not configured" -> user saves -> keys gone.

    This asserts *data*, deliberately, not "an exception was raised". A version
    that raised from the wrong place, or swallowed the raise and rewrote the file
    anyway, would still have to keep ``sk-REAL``.
    """
    settings_path.write_text(
        json.dumps(_settings_with_real_keys(), indent=2, ensure_ascii=False) + CORRUPTING_SUFFIX,
        encoding="utf-8",
    )
    before = settings_path.read_bytes()
    assert REAL_KEY.encode() in before, "precondition: the key is on disk before we start"

    returned = None
    raised = None
    try:
        settings = load_ai_settings(path=str(settings_path))
        returned = settings
        # Exactly what the settings page does next: the user, told they have no
        # key, types one for a *different* provider and presses save.
        settings.setdefault("providers", {}).setdefault("openai", {})["api_key"] = "sk-JUST-TYPED"
        save_ai_settings(settings, path=str(settings_path))
    except AiSettingsError as e:
        raised = e

    after = settings_path.read_bytes()

    # (1) the write half: the bytes are untouched. Byte equality, not a substring
    # check -- "the key survived but another provider's did not" is still loss.
    assert after == before, (
        "a read-modify-write cycle rewrote a settings file it could not read; "
        f"{REAL_KEY} is {'still present' if REAL_KEY.encode() in after else 'GONE FROM THE FILE'}"
    )
    assert REAL_KEY.encode() in after

    # (2) the read half: load never described a file that holds a key as a
    # configuration that has none. That description is what makes the next save
    # destructive, wherever that save happens to live.
    if returned is not None:
        got = ((returned.get("providers") or {}).get("anthropic") or {}).get("api_key")
        assert got == REAL_KEY, (
            f"load_ai_settings() returned providers.anthropic.api_key={got!r} while the file on "
            f"disk still holds {REAL_KEY!r} -- the key was dropped on the read side, and the very "
            "next save is what makes that permanent"
        )

    # (3) and, having established the data is safe: the caller was told.
    assert raised is not None, "the corruption must surface as AiSettingsError, not as silence"


# --------------------------------------------------------------------------
# A3 -- L2/S1: a missing file is a legal first run, not damage
# --------------------------------------------------------------------------

def test_missing_settings_file_still_returns_defaults(settings_path: Path) -> None:
    assert not settings_path.exists()

    got = load_ai_settings(path=str(settings_path))

    assert got == default_settings_dict()
    assert not settings_path.exists(), "reading must not create the file"


# --------------------------------------------------------------------------
# A4 -- L3/S2: defence in depth for callers that never went through load
# --------------------------------------------------------------------------

def test_save_refuses_to_overwrite_a_file_it_cannot_read(settings_path: Path) -> None:
    settings_path.write_text(
        json.dumps(_settings_with_real_keys(), indent=2) + CORRUPTING_SUFFIX, encoding="utf-8"
    )
    before = settings_path.read_bytes()

    hand_built = default_settings_dict()
    hand_built["providers"]["gemini"]["api_key"] = "sk-JUST-TYPED"

    with pytest.raises(AiSettingsError) as exc:
        save_ai_settings(hand_built, path=str(settings_path))

    assert str(settings_path) in str(exc.value)
    assert settings_path.read_bytes() == before, (
        "save must leave an unreadable file exactly as it found it"
    )


# --------------------------------------------------------------------------
# A5 -- L3/L4/S2: the write is atomic
# --------------------------------------------------------------------------

def test_a_normal_save_lands_and_leaves_no_temporary_file(
    settings_dir: Path, settings_path: Path
) -> None:
    settings_path.write_text(json.dumps(_settings_with_real_keys(), indent=2), encoding="utf-8")

    updated = _settings_with_real_keys()
    updated["providers"]["gemini"]["api_key"] = "sk-GEMINI"
    save_ai_settings(updated, path=str(settings_path))

    assert json.loads(settings_path.read_text("utf-8")) == updated
    assert sorted(os.listdir(settings_dir)) == ["ai_settings.json"], (
        "a temporary file was left next to the credentials"
    )


def test_a_crash_midway_through_the_write_leaves_the_old_file_intact(
    settings_dir: Path, settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4: the half-written case. A direct ``open(path, "w")`` truncates first."""
    settings_path.write_text(json.dumps(_settings_with_real_keys(), indent=2), encoding="utf-8")
    before = settings_path.read_bytes()

    def boom(obj, fp, **kwargs):
        fp.write('{"providers": {"anthr')  # a plausible truncated write
        raise RuntimeError("simulated: disk full")

    monkeypatch.setattr(ai_config.json, "dump", boom)

    with pytest.raises(RuntimeError, match="simulated"):
        save_ai_settings(default_settings_dict(), path=str(settings_path))

    assert settings_path.read_bytes() == before, "the old settings were truncated in place"
    assert sorted(os.listdir(settings_dir)) == ["ai_settings.json"], (
        "the failed write left a temporary file behind"
    )


# --------------------------------------------------------------------------
# A6 -- L2/S1: the ~14 call sites are covered by one exception handler
# --------------------------------------------------------------------------

def test_ai_settings_error_becomes_a_500_that_names_the_file(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from reader3_app.web import server

    message = f"{settings_path} is not valid JSON; fix or delete the file"

    def boom(*args, **kwargs):
        raise AiSettingsError(message)

    monkeypatch.setattr(server, "load_ai_settings", boom)

    # raise_server_exceptions=False so that an *unhandled* AiSettingsError also
    # produces a 500 -- the assertion below then fails on the thing that matters
    # (the response does not say which file), not on a re-raised traceback.
    client = TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    resp = client.get("/api/settings")

    assert resp.status_code == 500
    body = resp.text
    assert str(settings_path) in body, (
        "the 500 must name the file the user has to fix; a bare 'Internal Server Error' "
        "sends them to the server log for a problem that is entirely in their config"
    )
