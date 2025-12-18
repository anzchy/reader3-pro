from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from .types import ProviderResponse


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        return base
    return base + "/v1"


def _post_json(url: str, *, payload: Dict[str, Any], timeout_s: int) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
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


def ollama_chat_completions(
    *,
    base_url: str,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    timeout_s: int,
) -> ProviderResponse:
    base = _normalize_base_url(base_url)
    url = base + "/chat/completions"

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
        "stream": True,
    }

    # Some Ollama models ignore these fields, but they are safe to pass.
    try:
        payload["max_tokens"] = max(64, min(int(max_tokens), 4096))
    except Exception:
        payload["max_tokens"] = 1024

    status, resp = _post_json(url, payload=payload, timeout_s=timeout_s)
    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        if msg is None:
            msg = str(resp.get("message") or "")
        raise RuntimeError(msg or f"Ollama API error ({status})")

    choices = resp.get("choices") or []
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        text = str(msg.get("content") or "")
        finish_reason = str(choices[0].get("finish_reason") or "stop")
    else:
        text = ""
        finish_reason = "stop"

    model_out = str(resp.get("model") or model)
    token_count = None
    usage = resp.get("usage")
    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
        try:
            token_count = int(usage.get("completion_tokens"))
        except Exception:
            token_count = None

    return ProviderResponse(
        text=text.strip(),
        model=model_out,
        finish_reason=finish_reason,
        token_count=token_count,
    )

