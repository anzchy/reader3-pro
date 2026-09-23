"""`/settings`、`/api/settings/*`、`/api/ollama/*` —— 设置页与 provider 配置。

拆自 `web/server.py`（011 WI-4）。**路由正文一字未改**，改的只有三类引用：
`@app.x` → `@router.x`，接缝与 `server` 私有 helper 改走 `_server.` 属性访问。

**`/api/ollama/*` 归这里是一个判断，不是显然的事**（011 §5 要求写明）：它服务的是
设置页的 provider 探测——两条路由都只在 `/settings` 的 provider 卡片里被调用，
拿的是 base_url 和模型清单，不碰任何一本书。归 `ai` 也说得通（它探的是 LLM 后端），
但那样 `ai` 组会背上一个与对话、RAG、摘要都无关的 HTTP 探针。

`POST /api/settings/providers/{name}/test` 同理归这里：它是设置页的「测试连接」按钮，
落点是 `_call_provider`——也就是说**这个文件里有一条真实的 LLM 出口**。
`_call_provider` 必须走 `_server._call_provider`，这不是风格问题：它是全进程唯一的
provider 出口（ADR-0006），接缝一旦被旁路，那些「保证零真实外发」的测试会把
明文 API key 打到真 provider 上。本文件里所有 `ai.config` 的取值一律走 `_server.`，
包括 OWNERSHIP 名单没收录的 `get_provider_settings` / `get_provider_api_key` /
`default_settings_dict`——名单是最小集，这里按同一条规矩从严。

留在 `server` 的私有 helper：`_public_settings_response`、`_public_provider_config`、
`_settings_update_provider`、`_provider_default_base_url`、`_provider_requires_api_key`、
`_ollama_root_base_url`、`SUPPORTED_AI_PROVIDERS`、`templates`。
"""
from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


router: APIRouter = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    return _server.templates.TemplateResponse(request, "settings.html", {})


@router.get("/api/settings")
async def api_get_settings():
    settings = _server.load_ai_settings()
    return _server._public_settings_response(settings)


class UpdateSettingsRequest(BaseModel):
    default_provider: Optional[str] = None
    preferences: Optional[dict] = None


@router.put("/api/settings")
async def api_put_settings(body: UpdateSettingsRequest):
    settings = _server.load_ai_settings()
    updated = dict(settings or {})
    if body.default_provider is not None:
        provider = str(body.default_provider or "").strip().lower()
        if provider and provider not in _server.SUPPORTED_AI_PROVIDERS:
            raise HTTPException(status_code=400, detail="Invalid default_provider")
        updated["default_provider"] = provider or updated.get("default_provider") or "anthropic"
    if body.preferences is not None:
        # 现存 → 补丁，同 /api/settings/import。**不要**从 _server.default_settings_dict()
        # 重新起头：settings 已经过 _merge_defaults，默认值就在里面，再引一次默认
        # 只会把用户存过的其它偏好按出厂值写回磁盘——前端发一个 {"theme": "dark"}
        # 就够把落盘模式、会话上限一起重置掉。
        existing_prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
        prefs_patch = body.preferences if isinstance(body.preferences, dict) else {}
        merged = dict(existing_prefs)
        merged.update({k: v for k, v in prefs_patch.items() if v is not None})
        updated["preferences"] = merged

    _server.save_ai_settings(updated)
    return _server._public_settings_response(_server.load_ai_settings())


@router.get("/api/settings/providers")
async def api_list_settings_providers():
    providers = []
    defaults = _server.default_settings_dict()
    default_providers = defaults.get("providers") or {}
    for name in ("anthropic", "openai", "gemini", "ollama", "openrouter"):
        if name not in _server.SUPPORTED_AI_PROVIDERS:
            continue
        p = default_providers.get(name) or {}
        providers.append(
            {
                "name": name,
                "display_name": {
                    "anthropic": "Anthropic Claude",
                    "openai": "OpenAI",
                    "gemini": "Google Gemini",
                    "ollama": "Ollama (Local)",
                    "openrouter": "OpenRouter",
                }.get(name, name),
                "description": {
                    "ollama": "Local AI provider via Ollama (offline-capable)",
                    "openrouter": "Unified API for many models/providers",
                }.get(name, ""),
                "default_base_url": str(p.get("base_url") or _server._provider_default_base_url(name) or "").strip(),
                "default_model": str(p.get("model_name") or "").strip(),
                "supported_features": {
                    "streaming": True,
                    "function_calling": False,
                    "vision": False,
                },
                "documentation_url": {
                    "anthropic": "https://docs.anthropic.com",
                    "openai": "https://platform.openai.com/docs",
                    "gemini": "https://ai.google.dev",
                    "ollama": "https://ollama.com",
                    "openrouter": "https://openrouter.ai/docs",
                }.get(name, ""),
            }
        )
    return {"providers": providers}


@router.get("/api/settings/providers/{provider_name}")
async def api_get_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in _server.SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = _server.load_ai_settings()
    return _server._public_provider_config(name, settings=settings)


def _settings_export_payload(settings: dict) -> dict:
    exported: dict = {
        "default_provider": str(settings.get("default_provider") or "anthropic").strip().lower(),
        "preferences": settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {},
        "providers": {},
    }
    providers = settings.get("providers") if isinstance(settings.get("providers"), dict) else {}
    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        safe_cfg = dict(cfg)
        safe_cfg.pop("api_key", None)
        exported["providers"][str(name).strip().lower()] = safe_cfg
    return exported


@router.get("/api/settings/export")
async def api_settings_export():
    settings = _server.load_ai_settings()
    return _settings_export_payload(settings)


@router.post("/api/settings/import")
async def api_settings_import(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    existing = _server.load_ai_settings()
    updated = dict(existing or {})

    if "default_provider" in body:
        dp = str(body.get("default_provider") or "").strip().lower()
        if dp and dp in _server.SUPPORTED_AI_PROVIDERS:
            updated["default_provider"] = dp

    if isinstance(body.get("preferences"), dict):
        prefs_default = (_server.default_settings_dict().get("preferences") or {}).copy()
        prefs_default.update(existing.get("preferences") if isinstance(existing.get("preferences"), dict) else {})
        prefs_default.update({k: v for k, v in body.get("preferences").items() if v is not None})
        updated["preferences"] = prefs_default

    existing_providers = existing.get("providers") if isinstance(existing.get("providers"), dict) else {}
    merged_providers = dict(existing_providers)
    incoming_providers = body.get("providers") if isinstance(body.get("providers"), dict) else {}
    for name, patch in incoming_providers.items():
        pname = str(name or "").strip().lower()
        if pname not in _server.SUPPORTED_AI_PROVIDERS:
            continue
        base = dict(merged_providers.get(pname) or {})
        if isinstance(patch, dict):
            for key in ("enabled", "model_name", "base_url", "timeout", "timeout_s", "max_retries"):
                if key in patch:
                    base[key] = patch.get(key)
        # API keys are never imported.
        merged_providers[pname] = base
    updated["providers"] = merged_providers

    _server.save_ai_settings(updated)
    return _server._public_settings_response(_server.load_ai_settings())


class UpdateProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None


@router.put("/api/settings/providers/{provider_name}")
async def api_put_provider(provider_name: str, body: UpdateProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in _server.SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    patch: dict[str, Any] = {}
    if body.api_key is not None:
        patch["api_key"] = body.api_key
    if body.base_url is not None:
        patch["base_url"] = str(body.base_url or "").strip()
    if body.model_name is not None:
        patch["model_name"] = str(body.model_name or "").strip()
    if body.enabled is not None:
        patch["enabled"] = bool(body.enabled)
    if body.timeout is not None:
        patch["timeout_s"] = int(body.timeout)
        patch["timeout"] = int(body.timeout)
    if body.max_retries is not None:
        patch["max_retries"] = int(body.max_retries)

    settings = _server.load_ai_settings()
    updated = _server._settings_update_provider(name, settings=settings, patch=patch)
    _server.save_ai_settings(updated)
    return _server._public_provider_config(name, settings=_server.load_ai_settings())


@router.delete("/api/settings/providers/{provider_name}", status_code=204)
async def api_delete_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in _server.SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = _server.load_ai_settings()
    providers = dict(settings.get("providers") or {})
    providers.pop(name, None)
    settings["providers"] = providers
    _server.save_ai_settings(settings)
    return None


class TestProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


@router.post("/api/settings/providers/{provider_name}/test")
async def api_test_provider(provider_name: str, body: TestProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in _server.SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    settings = _server.load_ai_settings()
    provider_cfg = _server.get_provider_settings(name, settings=settings)
    stored_base_url = _server.get_provider_base_url(name, settings=settings) or provider_cfg.base_url or ""
    requested_base_url = str(body.base_url or "").strip() if body.base_url is not None else None
    base_url = stored_base_url if requested_base_url is None else requested_base_url
    model = str(body.model_name or "").strip() if body.model_name is not None else provider_cfg.model_name

    # 换了 endpoint 就必须自带 key（finding web/C2）。
    #
    # 这条路由没有鉴权（web/C1），所以「请求只给 base_url、key 从盘上取」等于：
    # 本机任意进程、或者一个做 DNS rebinding 的网页，只要 POST 一次就能让服务器
    # 把用户存着的真 key 发到它指定的地址去。回落必须在**发请求之前**断掉——
    # 挪到发完之后再报 400，状态码看着一样，key 已经出去了。
    if requested_base_url is not None and requested_base_url.rstrip("/") != stored_base_url.rstrip("/") and not body.api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "This request supplies a different base_url than the one in settings, so it must "
                "also supply its own api_key. The stored API key is never sent to an endpoint "
                "chosen by the request."
            ),
        )

    api_key = body.api_key if body.api_key is not None else _server.get_provider_api_key(name, settings=settings)

    if _server._provider_requires_api_key(name) and not api_key:
        raise HTTPException(status_code=401, detail="API key not configured")

    system = "You are a connectivity test. Reply with a single word: OK."
    messages = [{"role": "user", "content": "OK"}]

    started = time.perf_counter()
    try:
        resp = await run_in_threadpool(
            _server._call_provider,
            name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            system=system,
            messages=messages,
            max_tokens=16,
            timeout_s=min(10, provider_cfg.timeout_s),
            # 连通性自测**显式不重试**，哪怕 settings 里 max_retries 是 10。
            # 用户点了「测试」就是要立刻知道通不通：退避三轮会把一个 2 秒的失败变成 8 秒，
            # 还会把「偶发抖动」伪装成「连得通」——而这条路由存在的意义正是把抖动报出来。
            max_retries=0,
        )
    except Exception as e:  # noqa: BLE001 - 第 2 档：连通性自测的返回值就是 success/message，失败原因原样交给前端
        return {
            "success": False,
            "provider": name,
            "message": str(e),
            "details": {"model": model, "latency_ms": int((time.perf_counter() - started) * 1000)},
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": True,
        "provider": name,
        "message": "OK",
        "details": {"model": resp.model, "latency_ms": latency_ms},
    }


@router.get("/api/ollama/status")
async def api_ollama_status():
    settings = _server.load_ai_settings()
    base_url = _server.get_provider_base_url("ollama", settings=settings) or _server.get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _server._ollama_root_base_url(base_url)
    try:
        info = _server._http_get_json(root + "/api/version", timeout_s=2)
        return {"running": True, "base_url": root, "version": info.get("version")}
    except Exception as e:  # noqa: BLE001 - 第 2 档：ollama 探活的返回值就是 running/error，失败原因原样交给前端
        return {"running": False, "base_url": root, "error": str(e)}


@router.get("/api/ollama/models")
async def api_ollama_models():
    settings = _server.load_ai_settings()
    base_url = _server.get_provider_base_url("ollama", settings=settings) or _server.get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _server._ollama_root_base_url(base_url)
    try:
        tags = _server._http_get_json(root + "/api/tags", timeout_s=4)
        models = tags.get("models") if isinstance(tags, dict) else None
        if not isinstance(models, list):
            models = []
        out = []
        for m in models:
            if not isinstance(m, dict):
                continue
            out.append(
                {
                    "name": str(m.get("name") or ""),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                    "details": m.get("details") or {},
                }
            )
        return {"models": out, "base_url": root}
    except Exception as e:  # noqa: BLE001 - 第 2 档：HTTP 边界，转译成 503 且 detail 带上原因
        raise HTTPException(status_code=503, detail=str(e))

# ---------------------------------------------------------------------------
# 017 WI-1（审计 #7）——**这一行必须留在文件末尾**，在 `router` 与所有路由都定义完之后。
#
# `server` 在它自己的文件末尾要取 `routers.<本模块>.router` 这个**属性**来 include。
# 如果本模块在顶部就导入 `server`，而本进程又是从本模块开始导入的，那么 `server` 会在
# 本模块只执行到第 1 行的时候跑完整个文件体，然后去取一个还不存在的 `router`：
#     AttributeError: partially initialized module ... has no attribute 'router'
# 把导入挪到末尾，`router` 就已经在模块命名空间里，`server` 取得到，环自己解开。
#
# 这不影响打桩接缝：`_server.X` 仍是**调用时**解析属性，`monkeypatch.setattr(server, …)`
# 照常生效。绑的依旧是模块对象，不是属性——规矩见 `routers/__init__.py` 的 docstring。
# ---------------------------------------------------------------------------
from .. import server as _server  # noqa: E402
