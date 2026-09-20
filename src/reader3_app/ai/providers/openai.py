from __future__ import annotations

import time
from typing import Any, Dict, List

from ._http import estimate_tokens, post_json, validated_url
from .types import ProviderHTTPError, ProviderResponse

DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_CHAT_COMPLETIONS_URL = DEFAULT_BASE_URL + "/chat/completions"


def _extract_text(resp: Dict[str, Any]) -> str:
    choices = resp.get("choices") or []
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        return str(msg.get("content") or "").strip()
    return ""


def openai_chat_completions(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    timeout_s: int,
) -> ProviderResponse:
    url = validated_url(base_url or None, default=DEFAULT_BASE_URL) + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    openai_messages: List[Dict[str, Any]] = []
    if system:
        openai_messages.append({"role": "system", "content": system})
    for m in messages or []:
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = str(m.get("content") or "")
        openai_messages.append({"role": role, "content": content})

    payload: Dict[str, Any] = {
        "model": model,
        "messages": openai_messages,
        "stream": False,
        "max_tokens": max(64, min(int(max_tokens), 4096)),
    }

    started = time.perf_counter()
    status, resp = post_json(url, headers=headers, payload=payload, timeout_s=timeout_s)
    _ = time.perf_counter() - started

    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        raise ProviderHTTPError(msg or f"OpenAI API error ({status})", status=status)

    text = _extract_text(resp)
    finish_reason = "stop"
    choices = resp.get("choices") or []
    if isinstance(choices, list) and choices:
        finish_reason = str(choices[0].get("finish_reason") or "stop")

    model_out = str(resp.get("model") or model)
    token_count = None
    usage = resp.get("usage")
    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
        try:
            token_count = int(usage.get("completion_tokens"))
        except Exception:  # noqa: BLE001 - 第 3 档：token_count 解析失败退回估算值；它是遥测，不是回答内容
            token_count = None
    if token_count is None:
        token_count = estimate_tokens(text)

    return ProviderResponse(
        text=text,
        model=model_out,
        finish_reason=finish_reason,
        token_count=token_count,
    )

