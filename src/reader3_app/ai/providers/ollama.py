from __future__ import annotations

from typing import Any, Dict, List

from ._http import post_json, validated_url
from .types import ProviderResponse

DEFAULT_BASE_URL = "http://localhost:11434"


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = DEFAULT_BASE_URL
    # Accept either http://host:11434 or http://host:11434/v1 in config.
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base.rstrip("/")


def _error_message(status: int, resp: Dict[str, Any]) -> str:
    """从错误体里取出真正的原因（finding `ai/73`）。

    Ollama 的错误体是 `{"error": "<字符串>"}`，不是 `{"error": {"message": ...}}`。
    原来只判 dict，于是「model not found」「out-of-memory」这类唯一有用的信息全部落空，
    再回落到 `resp["message"]`——那在这个 API 上是**助手消息 dict**，于是用户拿到的是
    一个 stringify 过的 `{'role': 'assistant', ...}`。两种串味都在这里收口：
    两种 `error` 形状都认，助手消息一概不认，取不到就说实话报状态码。
    """
    err = resp.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()
    if isinstance(err, dict):
        detail = err.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return f"Ollama API error ({status})"


def ollama_chat_completions(
    *,
    base_url: str,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    timeout_s: int,
) -> ProviderResponse:
    base = validated_url(_normalize_base_url(base_url) or None, default=DEFAULT_BASE_URL)
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

    status, resp = post_json(url, payload=payload, timeout_s=timeout_s)
    if status >= 400:
        raise RuntimeError(_error_message(status, resp))

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
