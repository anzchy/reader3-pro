from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from .types import ProviderResponse

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _post_json(url: str, *, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: int) -> Tuple[int, Dict[str, Any]]:
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
        except Exception:
            parsed = {"error": {"message": body or str(e)}}
        return int(getattr(e, "code", 500) or 500), parsed


def _extract_text(resp: Dict[str, Any]) -> str:
    content = resp.get("content")
    if isinstance(content, list) and content:
        first = content[0] or {}
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    return str(resp.get("output_text") or resp.get("text") or "").strip()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def anthropic_messages(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    timeout_s: int,
) -> ProviderResponse:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": max(100, min(int(max_tokens), 4000)),
        "system": system,
        "messages": messages,
    }

    started = time.perf_counter()
    status, resp = _post_json(ANTHROPIC_MESSAGES_URL, headers=headers, payload=payload, timeout_s=timeout_s)
    _ = time.perf_counter() - started

    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        raise RuntimeError(msg or f"Anthropic API error ({status})")

    text = _extract_text(resp)
    finish_reason = str(resp.get("stop_reason") or "stop")
    model_out = str(resp.get("model") or model)
    token_count = None
    usage = resp.get("usage")
    if isinstance(usage, dict) and usage.get("output_tokens") is not None:
        try:
            token_count = int(usage.get("output_tokens"))
        except Exception:
            token_count = None
    if token_count is None:
        token_count = _estimate_tokens(text)

    return ProviderResponse(
        text=text,
        model=model_out,
        finish_reason=finish_reason,
        token_count=token_count,
    )
