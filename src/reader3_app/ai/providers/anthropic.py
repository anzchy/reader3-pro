from __future__ import annotations

import time
from typing import Any, Dict, List

from ._http import estimate_tokens, post_json
from .types import ProviderResponse

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _extract_text(resp: Dict[str, Any]) -> str:
    """把 content 里**所有**文本块按序拼起来（finding `ai/60`）。

    Anthropic 的 `content` 是块列表，不是「一个块」。开了 extended thinking 或者带工具时，
    `content[0]` 是 `thinking` / `tool_use`，没有 `"text"` 键——只读第 0 块就会漏掉真正的回答，
    然后落到下面那两个键上：`output_text` / `text` 在 Messages API 上根本不存在，于是返回空串，
    而 `stop_reason` 还是 `"end_turn"`。用户看到一片空白，app 报告一切正常。

    写法照抄同 repo 的 `gemini._extract_text`——那份从一开始就是对的。
    """
    content = resp.get("content")
    if isinstance(content, list) and content:
        texts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
        if texts:
            return "".join(texts).strip()
    # 兜底留着：对别的响应形状无害，对 Messages API 是死键。
    return str(resp.get("output_text") or resp.get("text") or "").strip()


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
    status, resp = post_json(ANTHROPIC_MESSAGES_URL, headers=headers, payload=payload, timeout_s=timeout_s)
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
