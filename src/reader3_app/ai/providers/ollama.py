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
    # Accept either http://host:11434 or http://host:11434/v1 in config.
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base.rstrip("/")


def _post_json(url: str, *, payload: Dict[str, Any], timeout_s: int) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not (body or "").strip():
                return int(resp.status), {}
            try:
                parsed = json.loads(body)
            except Exception:  # noqa: BLE001 - 第 2 档：响应体不是 JSON 时原样塞进 error.message，痕迹在返回值里
                parsed = {"error": {"message": body}}
            return int(resp.status), parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if getattr(e, "fp", None) else ""
        try:
            parsed = json.loads(body or "{}")
        except Exception:  # noqa: BLE001 - 第 2 档：错误响应体不是 JSON 时原样塞进 error.message，痕迹在返回值里
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
    url = base + "/api/chat"

    chat_messages: List[Dict[str, Any]] = []
    if system:
        chat_messages.append({"role": "system", "content": system})
    for m in messages or []:
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = str(m.get("content") or "")
        chat_messages.append({"role": role, "content": content})

    payload: Dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "options": {"num_predict": max(64, min(int(max_tokens), 4096))},
    }

    status, resp = _post_json(url, payload=payload, timeout_s=timeout_s)
    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        if msg is None:
            msg = str(resp.get("message") or "")
        raise RuntimeError(msg or f"Ollama API error ({status})")

    msg = resp.get("message") or {}
    if not isinstance(msg, dict):
        msg = {}
    text = str(msg.get("content") or "")
    finish_reason = str(resp.get("done_reason") or "stop")

    model_out = str(resp.get("model") or model)
    token_count = None
    if resp.get("eval_count") is not None:
        try:
            token_count = int(resp.get("eval_count"))
        except Exception:  # noqa: BLE001 - 第 3 档：eval_count 解析失败只让 token_count 为空，它是遥测，不是回答内容
            token_count = None

    return ProviderResponse(
        text=text.strip(),
        model=model_out,
        finish_reason=finish_reason,
        token_count=token_count,
    )
