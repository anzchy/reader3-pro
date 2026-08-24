"""WI-2: `_parse_summary_payload()` must tell prose apart from a real failure.

The site used to be `except Exception: pass`, so *every* failure of
`json.loads()` was read as "the model answered in prose" and the raw reply was
handed back as the overview. A blown recursion limit on a pathological reply
therefore reached the user as a summary made of brackets, with nothing in the
log to say so.

Assertion levels (see tests/unit/conftest.py):
    L2 return value
    L4 fault injection -- a parse that fails for a reason other than "not JSON"
"""

from __future__ import annotations

import json
import logging

import pytest

from reader3_app.web import server


def _ai_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "reader3.ai"]


def test_prose_reply_falls_back_to_text_and_leaves_a_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L2: a non-JSON reply still degrades to text, but the degradation is visible."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    out = server._parse_summary_payload("This book is about a ship.", summary_type="full")

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
        server._parse_summary_payload(raw, summary_type="full")


def test_json_object_reply_is_parsed_into_its_three_fields() -> None:
    """L2: the happy path the narrowing must not disturb."""
    raw = json.dumps(
        {"overview": "o", "highlights": ["a", "b"], "background": "bg"},
        ensure_ascii=False,
    )

    assert server._parse_summary_payload(raw, summary_type="full") == {
        "overview": "o",
        "highlights": ["a", "b"],
        "background": "bg",
    }


def test_json_array_reply_falls_back_and_says_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L2: valid JSON that is not an object is a different failure than bad JSON."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    out = server._parse_summary_payload('["a", "b"]', summary_type="highlights")

    assert out == {"overview": "", "highlights": ['["a", "b"]'], "background": ""}
    messages = [r.getMessage() for r in _ai_records(caplog) if r.levelno == logging.DEBUG]
    assert any("list" in m for m in messages), (
        f"a non-object JSON reply left no trace naming what came back: {messages}"
    )


def test_empty_reply_returns_empty_fields() -> None:
    """L2: an empty reply is not an error and must not log or raise."""
    assert server._parse_summary_payload("   ", summary_type="full") == {
        "overview": "",
        "highlights": [],
        "background": "",
    }
