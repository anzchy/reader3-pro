from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from .types import ProviderResponse

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def _post_json(
    url: str,
    *,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout_s: int,
) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(body or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if getattr(e, "fp", None) else ""
        try:
            parsed = json.loads(body or "{}")
        except Exception:  # noqa: BLE001 - 第 2 档：错误响应体不是 JSON 时原样塞进 error.message，痕迹在返回值里
            parsed = {"error": {"message": body or str(e)}}
        return int(getattr(e, "code", 500) or 500), parsed


def _extract_text(resp: Dict[str, Any]) -> str:
    choices = resp.get("choices") or []
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        return str(msg.get("content") or "").strip()
    return ""


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


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
    url = (base_url or "https://api.openai.com/v1").strip().rstrip("/") + "/chat/completions"
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
    status, resp = _post_json(url, headers=headers, payload=payload, timeout_s=timeout_s)
    _ = time.perf_counter() - started

    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        raise RuntimeError(msg or f"OpenAI API error ({status})")

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
        token_count = _estimate_tokens(text)

    return ProviderResponse(
        text=text,
        model=model_out,
        finish_reason=finish_reason,
        token_count=token_count,
    )

