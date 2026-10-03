"""Incremental Server-Sent Events parser for the reader3 `/api/ai/question` stream.

Bytes are buffered until a blank line completes a frame, so a UTF-8 character split
across reads is decoded whole. Comment lines (`:` prefix) are ignored, multiple `data:`
lines are joined with a newline, and the data is parsed as JSON when it is JSON (the
raw text is kept otherwise, so the caller can report it).
"""

import json
import re

_BLANK = re.compile(rb"\r\n\r\n|\n\n|\r\r")


class SSEParser:
    def __init__(self):
        self._buf = b""

    def feed(self, data):
        self._buf += data
        out = []
        while True:
            m = _BLANK.search(self._buf)
            if m is None:
                return out
            block, self._buf = self._buf[: m.start()], self._buf[m.end():]
            ev = _frame(block)
            if ev is not None:
                out.append(ev)

    def close(self):
        block, self._buf = self._buf, b""
        ev = _frame(block)
        return [] if ev is None else [ev]


def _frame(block):
    event, data = None, []
    for raw in re.split(rb"\r\n|\n|\r", block):
        line = raw.decode("utf-8", "replace")
        if not line or line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "event":
            event = value
        elif name == "data":
            data.append(value)
    if not data:
        return None
    text = "\n".join(data)
    try:
        value = json.loads(text)
    except ValueError:
        value = text
    return (event or "message", value)
