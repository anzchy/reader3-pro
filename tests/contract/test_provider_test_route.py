"""WI-11 / `web/C2` — ``POST /api/settings/providers/{name}/test`` must never send
the key stored on disk to a URL the request picked.

Today the route takes ``base_url`` from the request body and, when the body omits
``api_key``, falls back to the one in ``config/ai_settings.json``. Combined with
`web/C1` (the route has no authentication) any process on the machine — or a page
doing DNS rebinding — can name its own endpoint and be handed the user's key.

The core case is E6, and it is deliberately *not* a status-code assertion. Moving
the 400 to after the outbound call would leave E5 green while the key had already
left the building. E6 asserts on the arguments of the call itself.

**No network.** ``server._call_provider`` is the process's only route to an LLM
and the ``world`` fixture already stubs it; every test here replaces that stub
with a recording spy, so nothing reaches urllib at all.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from reader3_app.ai.providers.types import ProviderResponse
from reader3_app.web import server

from conftest import World

#: The key on disk. Nothing else in the repo contains this string, so finding it
#: in a recorded call is unambiguous evidence of exfiltration.
STORED_KEY = "sk-STORED-SENTINEL"

STORED_BASE_URL = "https://api.openai.com/v1"

#: ``.invalid`` is reserved by RFC 2606 and can never resolve, so even a total
#: failure of the stubbing below cannot reach a real host.
EVIL_BASE_URL = "http://evil.invalid/v1"


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def stored_openai(world: World) -> World:
    """Put a real-looking openai key on the isolated settings file.

    ``world`` seeds anthropic only; ``_merge_defaults`` would fill openai in with
    an empty key, and an empty key cannot be exfiltrated.
    """
    world.settings_path.write_text(
        json.dumps(
            {
                "default_provider": "openai",
                "providers": {
                    "openai": {
                        "enabled": True,
                        "model_name": "gpt-fixture",
                        "base_url": STORED_BASE_URL,
                        "api_key": STORED_KEY,
                        "timeout_s": 5,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return world


@pytest.fixture
def provider_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every argument of every outbound provider call."""
    calls: list[dict[str, Any]] = []

    def spy(provider_name: str, **kwargs: Any) -> ProviderResponse:
        calls.append({"provider_name": provider_name, **kwargs})
        return ProviderResponse(text="OK", model="gpt-fixture", finish_reason="stop", token_count=1)

    monkeypatch.setattr(server, "_call_provider", spy)
    return calls


# --------------------------------------------------------------------------
# E5 — changing the endpoint without bringing a key is a 400.  L2 / S1
# --------------------------------------------------------------------------


def test_e5_换了_endpoint_又不带_key_直接_400(
    stored_openai: World, provider_calls: list[dict[str, Any]]
) -> None:
    client: TestClient = stored_openai.client
    resp = client.post("/api/settings/providers/openai/test", json={"base_url": EVIL_BASE_URL})

    assert resp.status_code == 400, resp.text
    detail = str(resp.json().get("detail", "")).lower()
    assert "base_url" in detail, f"the 400 does not say which field caused it: {detail}"
    assert "api_key" in detail or "api key" in detail, (
        f"the 400 does not tell the caller to supply its own key: {detail}"
    )


def test_e5_换了_endpoint_并自带_key_时照常放行(
    stored_openai: World, provider_calls: list[dict[str, Any]]
) -> None:
    """The rule is "never fall back", not "never allow a custom endpoint" — a
    self-hosted gateway with its own key is the feature this route exists for."""
    client: TestClient = stored_openai.client
    resp = client.post(
        "/api/settings/providers/openai/test",
        json={"base_url": EVIL_BASE_URL, "api_key": "sk-CALLER-SUPPLIED"},
    )

    assert resp.status_code == 200, resp.text
    assert len(provider_calls) == 1
    assert provider_calls[0]["api_key"] == "sk-CALLER-SUPPLIED"
    assert STORED_KEY not in json.dumps(provider_calls, default=repr)


# --------------------------------------------------------------------------
# E6 — CORE: the stored key never appears in a call to a request-named URL.
# L3 / S2
# --------------------------------------------------------------------------


def test_e6_盘上的_key_绝不出现在发往请求指定_url_的调用里(
    stored_openai: World, provider_calls: list[dict[str, Any]]
) -> None:
    """The load-bearing assertion of WI-11.

    ``contextlib.suppress`` rather than ``pytest.raises``: this must stay red
    when the guard is deleted outright, and it must fail on *the key having been
    sent*, not on some exception type. Both assertions below run unconditionally
    whatever the route did.
    """
    client: TestClient = stored_openai.client

    with contextlib.suppress(Exception):
        client.post("/api/settings/providers/openai/test", json={"base_url": EVIL_BASE_URL})

    assert provider_calls == [], (
        "the route made an outbound call to a request-supplied endpoint: " f"{provider_calls}"
    )

    recorded = json.dumps(provider_calls, default=repr)
    assert STORED_KEY not in recorded, (
        "the API key stored on disk was passed to a call aimed at the request's own "
        f"base_url: {recorded}"
    )


# --------------------------------------------------------------------------
# E7 — regression: leaving base_url alone changes nothing.  L2 / S1
# --------------------------------------------------------------------------


def test_e7_不给_base_url_时行为不变(
    stored_openai: World, provider_calls: list[dict[str, Any]]
) -> None:
    client: TestClient = stored_openai.client
    resp = client.post("/api/settings/providers/openai/test", json={"model_name": "x"})

    assert resp.status_code == 200, resp.text
    assert len(provider_calls) == 1
    assert provider_calls[0]["api_key"] == STORED_KEY
    assert provider_calls[0]["base_url"] == STORED_BASE_URL
    assert provider_calls[0]["model"] == "x"


def test_e7_base_url_等于盘上存的值时行为不变(
    stored_openai: World, provider_calls: list[dict[str, Any]]
) -> None:
    """The settings page posts the form back verbatim, base_url included. If
    "same value" counted as "changed", saving a key and testing it would 400."""
    client: TestClient = stored_openai.client
    resp = client.post("/api/settings/providers/openai/test", json={"base_url": STORED_BASE_URL})

    assert resp.status_code == 200, resp.text
    assert len(provider_calls) == 1
    assert provider_calls[0]["api_key"] == STORED_KEY
