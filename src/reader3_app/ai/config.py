from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


DEFAULT_SETTINGS_PATH = os.environ.get("READER3_AI_SETTINGS", os.path.join("config", "ai_settings.json"))
EXAMPLE_SETTINGS_PATH = os.path.join("config", "ai_settings.example.json")


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    enabled: bool
    model_name: str
    api_key_configured: bool
    timeout_s: int


def default_settings_dict() -> Dict[str, Any]:
    return {
        "default_provider": "anthropic",
        "providers": {
            "anthropic": {
                "enabled": True,
                "model_name": "claude-sonnet-4-20250514",
                "api_key": "",
                "timeout_s": 30,
            }
        },
    }


def _merge_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = default_settings_dict()
    merged.update({k: v for k, v in (settings or {}).items() if k != "providers"})
    providers: Dict[str, Any] = dict(merged.get("providers") or {})
    for name, provider in (settings.get("providers") or {}).items():
        base = dict(providers.get(name) or {})
        base.update(provider or {})
        providers[name] = base
    merged["providers"] = providers
    return merged


def load_ai_settings(path: str = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return default_settings_dict()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return default_settings_dict()
        return _merge_defaults(raw)
    except Exception:
        return default_settings_dict()


def save_ai_settings(settings: Dict[str, Any], path: str = DEFAULT_SETTINGS_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_provider_settings(
    provider_name: Optional[str],
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> ProviderSettings:
    settings = settings or load_ai_settings()
    provider_name = (provider_name or settings.get("default_provider") or "anthropic").strip()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}

    enabled = bool(provider.get("enabled", True))
    model_name = str(provider.get("model_name") or "").strip()
    timeout_s = int(provider.get("timeout_s") or 30)
    api_key = provider.get("api_key")

    if not model_name:
        raise ValueError(f"Provider {provider_name} missing model_name")

    api_key_configured = bool(str(api_key or "").strip())
    return ProviderSettings(
        name=provider_name,
        enabled=enabled,
        model_name=model_name,
        api_key_configured=api_key_configured,
        timeout_s=max(1, min(timeout_s, 300)),
    )


def get_provider_api_key(
    provider_name: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    settings = settings or load_ai_settings()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}
    api_key = str(provider.get("api_key") or "").strip()
    return api_key or None
