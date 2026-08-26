"""WI-12 — three providers that report failure as a perfectly normal empty answer.

Findings `ai/60`, `ai/71`, `ai/73`. One symptom for the user in all three cases:
**a blank answer, and an app that says everything went fine.**

- `ai/60` (Anthropic): ``_extract_text`` reads only ``content[0]``. Anthropic's
  content is a *list of blocks*; the moment the first block is ``thinking`` or
  ``tool_use`` the real answer is dropped and ``stop_reason`` still says
  ``end_turn``.
- `ai/71` (Gemini): a safety block returns **no** ``candidates``, only
  ``promptFeedback.blockReason``. Today that is indistinguishable from a model
  that simply had nothing to say.
- `ai/73` (Ollama): the error body is ``{"error": "<string>"}``. The dict-only
  branch misses it and falls back to ``resp["message"]`` — which on this API is
  the *assistant message* — so the real cause ("model not found", "out of
  memory") never reaches the user.

**Everything here is offline.** Each test monkeypatches the ``post_json`` name
that the provider module resolved at import time, so no request is ever built;
``_no_real_sockets`` is a second, redundant fence in case a seam is ever missed.

Assertion levels (see tests/unit/conftest.py): L2 return value, L3 observable
end state of the parsed provider call.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

import pytest

from reader3_app.ai.providers import anthropic as anthropic_mod
from reader3_app.ai.providers import gemini as gemini_mod
from reader3_app.ai.providers import ollama as ollama_mod

#: Distinctive enough that finding it is evidence, not coincidence.
ANSWER_SENTINEL = "ANSWER-SENTINEL"

OLLAMA_BASE = "http://localhost:11434"


@pytest.fixture(autouse=True)
def _cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any relative path a test provokes lands in tmp_path, never in the repo."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _no_real_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this module may open a TCP connection, patched seam or not."""

    def _boom(*a: Any, **kw: Any) -> None:
        raise AssertionError("a test in this module tried to open a real socket")

    monkeypatch.setattr(socket.socket, "connect", _boom)


def _stub_post_json(
    monkeypatch: pytest.MonkeyPatch, module: Any, *, status: int, body: Dict[str, Any]
) -> Callable[[], Dict[str, Any]]:
    """Replace ``module.post_json`` with a canned ``(status, body)``.

    Returns an accessor for what the provider tried to send, so a test can prove
    the call was intercepted rather than silently skipped.
    """
    captured: Dict[str, Any] = {}

    def fake_post_json(url: str, *, payload: Any, timeout_s: int, headers: Any = None) -> Tuple[int, Dict[str, Any]]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return status, body

    monkeypatch.setattr(module, "post_json", fake_post_json)
    return lambda: captured


def _call_anthropic(monkeypatch: pytest.MonkeyPatch, body: Dict[str, Any], status: int = 200):
    _stub_post_json(monkeypatch, anthropic_mod, status=status, body=body)
    return anthropic_mod.anthropic_messages(
        api_key="k",
        model="claude-sonnet-4",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=256,
        timeout_s=5,
    )


def _call_gemini(monkeypatch: pytest.MonkeyPatch, body: Dict[str, Any], status: int = 200):
    _stub_post_json(monkeypatch, gemini_mod, status=status, body=body)
    return gemini_mod.gemini_generate_content(
        api_key="k",
        model="gemini-1.5-pro",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=256,
        timeout_s=5,
    )


def _call_ollama(monkeypatch: pytest.MonkeyPatch, body: Dict[str, Any], status: int = 200):
    _stub_post_json(monkeypatch, ollama_mod, status=status, body=body)
    return ollama_mod.ollama_chat_completions(
        base_url=OLLAMA_BASE,
        model="qwen3:8b",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=256,
        timeout_s=5,
    )


# --------------------------------------------------------------------------
# A1 — a leading `thinking` block must not swallow the answer.  L3 / S2
# --------------------------------------------------------------------------


def test_a1_首块是_thinking_时正文不丢(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extended thinking puts a ``thinking`` block at ``content[0]``.

    Reading only the first block turns every extended-thinking response into a
    blank answer whose ``stop_reason`` still reads ``end_turn``.
    """
    resp = _call_anthropic(
        monkeypatch,
        {
            "content": [
                {"type": "thinking", "thinking": "let me consider..."},
                {"type": "text", "text": ANSWER_SENTINEL},
            ],
            "stop_reason": "end_turn",
            "model": "claude-sonnet-4",
        },
    )

    assert resp.text != "", "a leading thinking block produced an empty answer"
    assert ANSWER_SENTINEL in resp.text, f"the answer text was lost: {resp.text!r}"


def test_a1b_首块是_tool_use_时正文不丢(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same shape with the other non-text block type Anthropic emits."""
    resp = _call_anthropic(
        monkeypatch,
        {
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "search", "input": {"q": "x"}},
                {"type": "text", "text": ANSWER_SENTINEL},
            ],
            "stop_reason": "end_turn",
        },
    )
    assert ANSWER_SENTINEL in resp.text, f"the answer text was lost: {resp.text!r}"


# --------------------------------------------------------------------------
# A2 — every text block, in order.  L3 / S2  (load-bearing)
# --------------------------------------------------------------------------


def test_a2_多个_text_块按序全部拼接(monkeypatch: pytest.MonkeyPatch) -> None:
    """Order *and* completeness in one assertion.

    Asserting only "not empty", or only ``"CCC" in text``, is satisfied by an
    implementation that returns just the last block. This is the case that has
    to fail if ``content[0]`` ever comes back.
    """
    resp = _call_anthropic(
        monkeypatch,
        {
            "content": [
                {"type": "text", "text": "AAA"},
                {"type": "text", "text": "BBB"},
                {"type": "text", "text": "CCC"},
            ],
            "stop_reason": "end_turn",
        },
    )
    assert resp.text == "AAABBBCCC", f"blocks were dropped or reordered: {resp.text!r}"


# --------------------------------------------------------------------------
# A3 — the shapes that worked before still work.  L2 / S1
# --------------------------------------------------------------------------


def test_a3_单个_text_块仍然work(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _call_anthropic(monkeypatch, {"content": [{"type": "text", "text": "X"}]})
    assert resp.text == "X"


def test_a3_output_text_兜底仍然work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Harmless for the Messages API, and other response shapes still use it."""
    resp = _call_anthropic(monkeypatch, {"output_text": "Y"})
    assert resp.text == "Y"


def test_a3_没有任何文本时是空串而不是异常(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _call_anthropic(monkeypatch, {"content": [{"type": "thinking", "thinking": "..."}]})
    assert resp.text == ""


# --------------------------------------------------------------------------
# G1 — a safety block is not a normal completion.  L2 / S1
# --------------------------------------------------------------------------


def test_g1_gemini_安全拦截不等于正常完成(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``candidates`` at all, only ``promptFeedback.blockReason``.

    Reported as ``stop``, a refusal is indistinguishable from an empty answer,
    and the UI has nothing to tell the user. It must **not** raise: the upper
    layer already forwards ``finish_reason`` to the browser, and raising would
    turn "the model declined" into a 500.
    """
    resp = _call_gemini(monkeypatch, {"promptFeedback": {"blockReason": "SAFETY"}})

    assert resp.finish_reason != "stop", "a blocked prompt was reported as a normal stop"
    assert "blocked" in resp.finish_reason, f"finish_reason was {resp.finish_reason!r}"
    assert "safety" in resp.finish_reason, f"the block reason was dropped: {resp.finish_reason!r}"


def test_g1b_正常响应仍然返回_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: the block branch must not have been implemented by
    labelling every response ``blocked``."""
    resp = _call_gemini(
        monkeypatch,
        {"candidates": [{"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}]},
    )
    assert resp.finish_reason == "stop"
    assert resp.text == "hi"


def test_g1c_有_candidates_但没有_finishreason_仍然是_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _call_gemini(monkeypatch, {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
    assert resp.finish_reason == "stop"


# --------------------------------------------------------------------------
# O1 — the real reason reaches the exception.  L2 / S1
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, needle",
    [
        ({"error": "model 'qwen3:8b' not found"}, "not found"),
        # The second cause the finding names is an OOM. It is spelled with
        # hyphens on purpose: the tdd-guardian receipt CLI scans runner output
        # for the un-hyphenated spelling to detect a process killed by the OOM
        # reaper, and pytest echoes this decorator's source into every failure
        # report for this function — so the plain spelling would make a genuine
        # red look like a crashed runner.
        ({"error": {"message": "model requires more RAM (out-of-memory)"}}, "out-of-memory"),
    ],
    ids=["error-is-a-string", "error-is-a-dict"],
)
def test_o1_ollama_的真实错误原因出现在异常里(
    monkeypatch: pytest.MonkeyPatch, body: Dict[str, Any], needle: str
) -> None:
    """The load-bearing claim is *which text* is in the message, not that it
    raised — so the assertion is made on ``exc.value`` after the block, where a
    ``RuntimeError("")`` fails it."""
    with pytest.raises(RuntimeError) as exc:
        _call_ollama(monkeypatch, body, status=400)

    message = str(exc.value)
    assert needle in message, f"the real cause was dropped; the user saw: {message!r}"


# --------------------------------------------------------------------------
# O2 — the assistant message is not an error string.  L2 / S1
# --------------------------------------------------------------------------


def test_o2_错误响应里的助手消息不会被当成错误文案(monkeypatch: pytest.MonkeyPatch) -> None:
    """``resp["message"]`` on this API is the *assistant message*, so
    stringifying it hands the user a Python dict repr in place of a cause."""
    with pytest.raises(RuntimeError) as exc:
        _call_ollama(
            monkeypatch,
            {"message": {"role": "assistant", "content": "hi"}},
            status=500,
        )

    message = str(exc.value)
    assert "assistant" not in message, f"the assistant message leaked into the error: {message!r}"
    assert "role" not in message, f"a stringified dict leaked into the error: {message!r}"
    assert "500" in message, f"the fallback lost the status code: {message!r}"


def test_o2b_positive_control_错误通道确实能带出这个词(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backstop for O2's negative assertions.

    ``"assistant" not in message`` would pass vacuously if no text from the body
    ever reached the message. Put the very same word on the *legitimate* channel
    and it must appear — which proves O2 fails for the right reason.
    """
    with pytest.raises(RuntimeError) as exc:
        _call_ollama(
            monkeypatch,
            {
                "error": "the assistant model is unavailable",
                "message": {"role": "assistant", "content": "hi"},
            },
            status=500,
        )

    message = str(exc.value)
    assert "assistant" in message, f"the error channel carried nothing: {message!r}"


def test_o2c_成功响应仍然读得到助手消息(monkeypatch: pytest.MonkeyPatch) -> None:
    """The error path must not have been fixed by breaking the success path."""
    resp = _call_ollama(
        monkeypatch,
        {
            "message": {"role": "assistant", "content": ANSWER_SENTINEL},
            "done_reason": "stop",
            "model": "qwen3:8b",
        },
    )
    assert resp.text == ANSWER_SENTINEL
    assert resp.finish_reason == "stop"
