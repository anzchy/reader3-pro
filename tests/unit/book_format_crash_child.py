"""012 WI-1.8: the child process of the real-SIGKILL crash matrix (Y-01 .. Y-04).

Not collected by pytest (the name does not match ``test_*.py``); importing it has no side effects. The parent
(``test_book_format_crash_matrix.py``) builds the scenario tree, then runs::

    subprocess.run([sys.executable, CHILD, json_spec], env=child_env(), timeout=30)

``json_spec`` keys:

- ``mode``: ``"publish"`` runs ``publish(book, make_inputs(tag), create=create)``; ``"gc"`` runs
  ``collect_garbage(book)``.
- ``book``, ``create``, ``tag``: the target and the inputs (``make_inputs`` from ``book_format_helpers``).
- ``kill_at``: the 0-based index of the ``_crash_point`` call to kill at; ``-1`` never kills.
- ``marker``: a file outside the book tree. At the kill point the child appends one line
  ``"{mode} {idx} {step} {when}"``, fsyncs it, then sends itself ``SIGKILL`` (a real kernel kill: no ``finally``,
  no context-manager exit, no ``atexit``).
- ``finally_sentinel`` / ``atexit_sentinel`` (optional): files the child writes from a ``finally`` block around
  the run and from an ``atexit`` handler; a real kill leaves both absent (Y-03).

Stdout carries ``file <book_format.__file__>`` first (flushed before any kill), and ``result <value>`` on a run
that was not killed.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import sys
from typing import Any


def _append_fsynced(path: str, line: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_sentinel(path: str, what: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(what)


def run(spec: dict[str, Any]) -> None:
    from book_format_helpers import make_inputs
    from reader3_app import book_format

    print(f"file {book_format.__file__}", flush=True)
    mode: str = spec["mode"]
    kill_at: int = spec["kill_at"]
    marker: str = spec["marker"]
    calls = [0]

    def crash_point(step: str, when: str) -> None:
        idx = calls[0]
        calls[0] += 1
        if idx == kill_at:
            _append_fsynced(marker, f"{mode} {idx} {step} {when}")
            os.kill(os.getpid(), signal.SIGKILL)

    book_format._crash_point = crash_point  # type: ignore[assignment]

    atexit_sentinel = spec.get("atexit_sentinel")
    if atexit_sentinel:
        atexit.register(_write_sentinel, atexit_sentinel, "atexit ran")
    finally_sentinel = spec.get("finally_sentinel")
    try:
        if mode == "publish":
            g = book_format.publish(spec["book"], make_inputs(spec["tag"]), create=bool(spec["create"]))
            print(f"result {g}", flush=True)
        elif mode == "gc":
            res = book_format.collect_garbage(spec["book"])
            print(f"result {res.state} {len(res.deleted)}", flush=True)
        else:
            raise SystemExit(f"unknown mode {mode!r}")
    finally:
        if finally_sentinel:
            _write_sentinel(finally_sentinel, "finally ran")


if __name__ == "__main__":
    run(json.loads(sys.argv[1]))
