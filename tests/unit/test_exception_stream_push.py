"""WI-3: the SSE producer must not drop an answer chunk in silence.

`api_ai_question()`'s streaming path pushed provider chunks onto a queue through
a closure that was `try: q.put_nowait(evt) / except Exception: pass`. Anything
that went wrong there -- a full queue, a closed loop, a queue that is not a
queue -- deleted a piece of the user's answer, which then got persisted into the
conversation as if the model had said exactly that much.

The closure body now lives in `server._push_event()` so the failure modes can be
stated as assertions instead of only being reachable through a live LLM stream.

Assertion levels (see tests/unit/conftest.py):
    L2 return value / queue contents
    L4 fault injection on the queue
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

import pytest

from reader3_app.web import server


def test_event_reaches_the_queue() -> None:
    """L2: the ordinary path still delivers, and says it delivered."""

    async def scenario() -> tuple[bool, Dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue()
        delivered = server._push_event(q, {"type": "chunk", "delta": "hello"})
        return delivered, q.get_nowait()

    delivered, evt = asyncio.run(scenario())

    assert delivered is True
    assert evt == {"type": "chunk", "delta": "hello"}


def test_dropped_chunk_is_reported_not_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L4: a full queue means the user's answer lost a piece -- that must be logged."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")

    async def scenario() -> bool:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        server._push_event(q, {"type": "chunk", "delta": "kept"})
        return server._push_event(q, {"type": "chunk", "delta": "lost"})

    delivered = asyncio.run(scenario())

    assert delivered is False
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == "reader3.ai" and r.levelno >= logging.WARNING
    ]
    assert any("chunk" in m for m in warnings), (
        f"a dropped stream event left no warning naming its type: {warnings}"
    )


def test_a_broken_queue_is_not_mistaken_for_backpressure() -> None:
    """L4: anything other than QueueFull is a bug here and must surface."""

    class _ClosedLoopQueue:
        def put_nowait(self, evt: Dict[str, Any]) -> None:
            raise RuntimeError("Event loop is closed")

    with pytest.raises(RuntimeError):
        server._push_event(_ClosedLoopQueue(), {"type": "done", "model": "m"})
