from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional


DEFAULT_SETTINGS_PATH = os.environ.get("READER3_AI_SETTINGS", os.path.join("config", "ai_settings.json"))
EXAMPLE_SETTINGS_PATH = os.path.join("config", "ai_settings.example.json")


class AiSettingsError(RuntimeError):
    """Raised when ai_settings.json exists but cannot be understood."""


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
    merged.update({k: v for k, v in (settings or {}).items() if k not in ("providers", "preferences")})

    # preferences 和 providers 一样要两级合并。整块 update 的话，磁盘上一份
    # {"preferences": {"theme": "dark"}} 会让 conversation_disk_storage 等键当场
    # 消失——不是回退到默认值，是从这份 settings 里没了，于是「读—改—写」的下一次
    # 保存把用户设过的落盘模式永久抹掉。默认打底，文件里的值优先。
    incoming_prefs = (settings or {}).get("preferences")
    if isinstance(incoming_prefs, dict):
        prefs: Dict[str, Any] = dict(merged.get("preferences") or {})
        prefs.update(incoming_prefs)
        merged["preferences"] = prefs
    elif "preferences" in (settings or {}):
        # 不是 dict 就照原样带上，不在这里新增校验：本函数只管不丢。
        merged["preferences"] = incoming_prefs

    providers: Dict[str, Any] = dict(merged.get("providers") or {})
    for name, provider in (settings.get("providers") or {}).items():
        base = dict(providers.get(name) or {})
        base.update(provider or {})
        providers[name] = base
    merged["providers"] = providers
    return merged


def _read_settings_file(path: str) -> Optional[Dict[str, Any]]:
    """读 ai_settings.json：不存在返回 None，**读不懂就抛**。

    这两件事以前都返回默认值，于是调用方无法分辨「用户还没配过 key」和
    「用户的 key 我读不出来」，把后者也当成前者去覆盖——前端显示「未配置」，
    用户重填一个 provider 保存，其余 provider 的 API key 全没了且不报错。同
    ``ensure_book_uuid`` 的先例：读不懂的用户数据不许当成「没有」。500 是可恢复
    的，删掉用户的密钥不是。OSError（权限、坏盘）同理。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        raise AiSettingsError(
            f"{path} is not valid JSON ({e}); refusing to treat it as an empty "
            "configuration -- fix or delete the file"
        ) from e
    except OSError as e:
        raise AiSettingsError(
            f"{path} exists but could not be read ({e}); refusing to treat it as an "
            "empty configuration -- fix or delete the file"
        ) from e
    if not isinstance(raw, dict):
        raise AiSettingsError(
            f"{path} is not a JSON object (got {type(raw).__name__}); refusing to treat "
            "it as an empty configuration -- fix or delete the file"
        )
    return raw


def load_ai_settings(path: str = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    raw = _read_settings_file(path)
    if raw is None:
        # 文件不存在是合法的首次运行状态，不是损坏。把它一并收进抛错，
        # 就是拿一个假 bug 换一个真 bug。
        return default_settings_dict()
    return _merge_defaults(raw)


def save_ai_settings(settings: Dict[str, Any], path: str = DEFAULT_SETTINGS_PATH) -> None:
    # 纵深防御：目标已存在但读不出来时拒写。load_ai_settings() 已经拦了
    # 「读—改—写」那条路，但不经过 load 直接构造 settings 的调用方也不该有
    # 能力把一份我们读不懂的凭据文件抹掉。
    _read_settings_file(path)

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    # 原子写：tmp + os.replace，同 ensure_book_uuid / conversations。
    #
    # 但 tmp 名字用 tempfile.mkstemp(dir=目标同目录) 而**不是** books.py 那种固定的
    # f"{path}.tmp"。这次偏离仓库既有写法是故意的，不是不一致：这个文件装的是
    # 凭据，两个并发写手（两个标签页同时保存设置）抢同一个固定 tmp 名本身就是一条
    # 凭据损坏路径，而 mkstemp 只多一行。顺带的好处：mkstemp 建文件时就是 0600。
    fd, tmp_path = tempfile.mkstemp(prefix=".ai_settings.", suffix=".tmp", dir=directory)
    try:
        try:
            # fdopen 接管 fd，with 退出时关闭它；只有 fdopen 自己抛了，fd 才还在我们手上。
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with handle as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        # 写到一半失败：旧文件一字未动，顺手把半截 tmp 清掉，不在凭据旁边留残片。
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
