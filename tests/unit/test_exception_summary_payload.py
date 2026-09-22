"""WI-2: `_parse_summary_payload()` must tell prose apart from a real failure.

The site used to be `except Exception: pass`, so *every* failure of
`json.loads()` was read as "the model answered in prose" and the raw reply was
handed back as the overview. A blown recursion limit on a pathological reply
therefore reached the user as a summary made of brackets, with nothing in the
log to say so.

Assertion levels (see tests/unit/conftest.py):
    L2 return value
    L4 fault injection -- a parse that fails for a reason other than "not JSON"

011 WI-4 之后 `_parse_summary_payload` 从 `web/server.py` 搬到了
`web/routers/ai/summary.py`。这里跟着改的只有**取函数的地方**——这是个纯函数，
没有 monkeypatch 接缝，改导入不会掩盖任何接缝被搬断的情况。
"""

from __future__ import annotations

import json
import logging

import pytest

from reader3_app.web.routers.ai import summary as summary_router


def _ai_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "reader3.ai"]


@pytest.fixture(autouse=True)
def _work_in_tmp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing here writes files, but a relative path that appears later must not
    be able to resolve into the repository -- least of all into ``books/``."""
    monkeypatch.chdir(tmp_path)


def test_prose_reply_falls_back_to_text_and_leaves_a_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L2: a non-JSON reply still degrades to text, but the degradation is visible."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    out = summary_router._parse_summary_payload("This book is about a ship.", summary_type="full")

    assert out == {
        "overview": "This book is about a ship.",
        "highlights": [],
        "background": "",
    }
    messages = [r.getMessage() for r in _ai_records(caplog) if r.levelno == logging.DEBUG]
    assert any("JSON" in m and "full" in m for m in messages), (
        f"falling back to text left no debug trace naming the summary type: {messages}"
    )


def test_pathological_nesting_is_not_mistaken_for_prose() -> None:
    """L4: RecursionError is not "the model answered in prose" -- it must surface."""
    depth = 5000
    raw = "[" * depth + "]" * depth

    with pytest.raises(RecursionError):
        summary_router._parse_summary_payload(raw, summary_type="full")


def test_json_object_reply_is_parsed_into_its_three_fields() -> None:
    """L2: the happy path the narrowing must not disturb."""
    raw = json.dumps(
        {"overview": "o", "highlights": ["a", "b"], "background": "bg"},
        ensure_ascii=False,
    )

    assert summary_router._parse_summary_payload(raw, summary_type="full") == {
        "overview": "o",
        "highlights": ["a", "b"],
        "background": "bg",
    }


def test_json_array_reply_falls_back_and_says_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L2: valid JSON that is not an object is a different failure than bad JSON."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    out = summary_router._parse_summary_payload('["a", "b"]', summary_type="highlights")

    assert out == {"overview": "", "highlights": ['["a", "b"]'], "background": ""}
    messages = [r.getMessage() for r in _ai_records(caplog) if r.levelno == logging.DEBUG]
    assert any("list" in m for m in messages), (
        f"a non-object JSON reply left no trace naming what came back: {messages}"
    )


def test_empty_reply_returns_empty_fields(caplog: pytest.LogCaptureFixture) -> None:
    """L2: an empty reply is not an error and must not log or raise.

    "must not log" is asserted, not just asserted-in-prose. Every other case in
    this module reads ``caplog``, so leaving this one unchecked reads like a
    deliberate exemption -- and it hides the change that matters here: an empty
    reply is the *ordinary* outcome of a provider that returned nothing, so a
    warning on this path fires on a loop and buries the real degradations
    (``not JSON``, ``not an object``) that the rest of this module pins down.
    """
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    out = summary_router._parse_summary_payload("   ", summary_type="full")

    assert out == {"overview": "", "highlights": [], "background": ""}
    assert _ai_records(caplog) == [], (
        "the empty-reply path is not a degradation and must leave the ai log alone: "
        f"{[(r.levelname, r.getMessage()) for r in _ai_records(caplog)]}"
    )
