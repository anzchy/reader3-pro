from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List

from ._http import post_json, validated_url
from .types import ProviderHTTPError, ProviderResponse


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        raise ValueError("Gemini model_name is required")
    if m.startswith("models/"):
        return m
    return "models/" + m


def _extract_text(resp: Dict[str, Any]) -> str:
    candidates = resp.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if isinstance(parts, list) and parts:
        texts = []
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                texts.append(p["text"])
        return "".join(texts).strip()
    return ""


def _finish_reason(resp: Dict[str, Any]) -> str:
    """安全拦截不是正常完成（finding `ai/71`）。

    Gemini 被安全策略拦下时**不返回 `candidates`**，只给 `promptFeedback.blockReason`。
    原来这里硬编码返回 `"stop"`，于是「模型拒答」和「模型确实没话说」在返回值里一模一样，
    前端没有任何依据能告诉用户发生了什么。

    **不抛**：上层已有把 `finish_reason` 透给前端的通路，抛会把「模型拒答」变成 500。
    """
    candidates = resp.get("candidates") or []
    if isinstance(candidates, list) and candidates:
        fr = candidates[0].get("finishReason")
        if isinstance(fr, str) and fr:
            return fr.lower()
        return "stop"

    # 没有 candidates 才看 promptFeedback：有 candidates 时它讲的是别的事。
    feedback = resp.get("promptFeedback")
    if isinstance(feedback, dict):
        reason = feedback.get("blockReason")
        if isinstance(reason, str) and reason.strip():
            return f"blocked:{reason.strip().lower()}"
    return "stop"


def gemini_generate_content(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    timeout_s: int,
    base_url: str = DEFAULT_BASE_URL,
) -> ProviderResponse:
    base = validated_url(base_url or None, default=DEFAULT_BASE_URL)
    m = _normalize_model(model)

    url = base + "/v1beta/" + urllib.parse.quote(m, safe="/") + ":generateContent"

    # key 走头，不走 query。查询串会被沿途每一层——反向代理、CDN、公司出口网关——
    # 写进访问日志，而 Google 本来就支持这个头（finding ai/70）。
    headers = {"x-goog-api-key": api_key}

    contents: List[Dict[str, Any]] = []
    for msg in messages or []:
        role = str(msg.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(
            {
                "role": gemini_role,
                "parts": [{"text": str(msg.get("content") or "")}],
            }
        )

    payload: Dict[str, Any] = {
        "contents": contents or [{"role": "user", "parts": [{"text": ""}]}],
        "generationConfig": {
            "maxOutputTokens": max(64, min(int(max_tokens), 8192)),
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    status, resp = post_json(url, payload=payload, headers=headers, timeout_s=timeout_s)
    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        raise ProviderHTTPError(msg or f"Gemini API error ({status})", status=status)

    return ProviderResponse(
        text=_extract_text(resp),
        model=model,
        finish_reason=_finish_reason(resp),
        token_count=None,
    )

