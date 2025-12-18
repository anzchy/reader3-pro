from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

from .types import ProviderResponse


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        raise ValueError("Gemini model_name is required")
    if m.startswith("models/"):
        return m
    return "models/" + m


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
    candidates = resp.get("candidates") or []
    if isinstance(candidates, list) and candidates:
        fr = candidates[0].get("finishReason")
        if isinstance(fr, str) and fr:
            return fr.lower()
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
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    m = _normalize_model(model)

    url = (
        base
        + "/v1beta/"
        + urllib.parse.quote(m, safe="/")
        + ":generateContent?"
        + urllib.parse.urlencode({"key": api_key})
    )

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

    status, resp = _post_json(url, payload=payload, timeout_s=timeout_s)
    if status >= 400:
        msg = None
        err = resp.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        raise RuntimeError(msg or f"Gemini API error ({status})")

    return ProviderResponse(
        text=_extract_text(resp),
        model=model,
        finish_reason=_finish_reason(resp),
        token_count=None,
    )

