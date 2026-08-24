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
    base_url: str
    api_key_configured: bool
    timeout_s: int
    max_retries: int


def default_settings_dict() -> Dict[str, Any]:
    return {
        "default_provider": "anthropic",
        "preferences": {
            "show_timestamps": True,
            "auto_suggest_questions": True,
            "streaming_enabled": True,
            "max_conversation_length": 500,
            # On-disk chat storage:
            # - per_book: books/{book_folder}/ai_conversations/{conversation_id}.json
            # - project_root: {project_root}/conversations/{book_uuid}/{conversation_id}.json
            # - both: write to both locations
            "conversation_disk_storage": "per_book",
            "conversation_project_root_dir": "conversations",
            "theme": "auto",
        },
        "providers": {
            "anthropic": {
                "enabled": True,
                "model_name": "claude-sonnet-4-20250514",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "openai": {
                "enabled": False,
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "gemini": {
                "enabled": False,
                "model_name": "gemini-1.5-pro",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
            "ollama": {
                "enabled": False,
                "base_url": "http://localhost:11434",
                "model_name": "qwen3:8b",
                "timeout_s": 60,
                "max_retries": 0,
            },
            "openrouter": {
                "enabled": False,
                "base_url": "https://openrouter.ai/api/v1",
                "model_name": "openai/gpt-4o-mini",
                "api_key": "",
                "timeout_s": 30,
                "max_retries": 3,
            },
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
    except Exception:  # noqa: BLE001 - FIXME(011): 无正当理由——坏掉的 ai_settings.json 被静默换成默认值，随后一次 save 就把用户的 API key 覆盖掉，和 ensure_book_uuid 的旧 bug 同一类
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
    timeout_s_raw = provider.get("timeout_s")
    if timeout_s_raw is None:
        timeout_s_raw = provider.get("timeout")
    timeout_s = int(timeout_s_raw or (60 if provider_name == "ollama" else 30))
    max_retries = int(provider.get("max_retries") or 0)
    base_url = str(provider.get("base_url") or "").strip()
    api_key = provider.get("api_key")

    if not model_name:
        raise ValueError(f"Provider {provider_name} missing model_name")

    api_key_configured = bool(str(api_key or "").strip())
    return ProviderSettings(
        name=provider_name,
        enabled=enabled,
        model_name=model_name,
        base_url=base_url,
        api_key_configured=api_key_configured,
        timeout_s=max(1, min(timeout_s, 300)),
        max_retries=max(0, min(max_retries, 10)),
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


def get_provider_base_url(
    provider_name: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    settings = settings or load_ai_settings()
    providers: Dict[str, Any] = settings.get("providers") or {}
    provider: Dict[str, Any] = providers.get(provider_name) or {}
    base_url = str(provider.get("base_url") or "").strip()
    return base_url or None
