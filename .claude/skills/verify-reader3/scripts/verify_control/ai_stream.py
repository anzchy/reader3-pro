"""Concurrent SSE streams for `ai ask`, under one overall deadline.

Each stream is a daemon thread with its own `http.client.HTTPConnection` to 127.0.0.1
(never urllib: no proxy, no redirect following). The caller's thread polls the shared
state, drives the `release-after-first-delta` gate, and at the deadline shuts the
sockets down and freezes the partial results. Headers are sent, never reported.
"""

import http.client
import json
import socket
import threading
import time

from verify_control.sse import SSEParser

READ_SIZE = 65536
ERROR_BODY_CAP = 4096
POLL_S = 0.02


class Stream:
    def __init__(self, index):
        self.index = index
        self.status = None
        self.events = []
        self.text = ""
        self.errors = []
        self.done = False
        self.error_event = False
        self.first_delta = False
        self.finished = False
        self.sock = None

    def result(self):
        return {"index": self.index, "status": self.status, "events": list(self.events),
                "text": self.text, "errors": list(self.errors)}


class Run:
    """N streams of one POST. `wait(deadline, on_poll)` returns True if every stream finished."""

    def __init__(self, port, path, body, headers, n, read_timeout):
        self.port, self.path, self.headers = port, path, headers
        self.body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.read_timeout = read_timeout
        self.streams = [Stream(i) for i in range(n)]
        self.cond = threading.Condition()
        self.frozen = False

    def start(self):
        for s in self.streams:
            threading.Thread(target=self._worker, args=(s,), daemon=True, name=f"ai-ask-{s.index}").start()

    def all_have_first_delta(self):
        with self.cond:
            return all(s.first_delta or s.finished for s in self.streams)

    def wait(self, deadline, on_poll=None):
        while True:
            with self.cond:
                if all(s.finished for s in self.streams):
                    return True
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.cond.wait(min(POLL_S, left))
            if on_poll is not None:
                on_poll()

    def freeze(self, note):
        """Stop recording, mark unfinished streams with `note`, and unblock their sockets."""
        with self.cond:
            self.frozen = True
            socks = []
            for s in self.streams:
                if not s.finished:
                    s.errors.append(note)
                    if s.sock is not None:
                        socks.append(s.sock)
        for sock in socks:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def results(self):
        with self.cond:
            return [s.result() for s in self.streams]

    # ------------------------------------------------------------------ worker

    def _mutate(self, fn):
        with self.cond:
            if not self.frozen:
                fn()
            self.cond.notify_all()

    def _worker(self, s):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.read_timeout)
        broken = None
        try:
            conn.connect()
            self._mutate(lambda: setattr(s, "sock", conn.sock))
            conn.request("POST", self.path, body=self.body, headers=self.headers)
            resp = conn.getresponse()
            self._mutate(lambda: setattr(s, "status", resp.status))
            if resp.status != 200:
                detail = _error_detail(resp.read(ERROR_BODY_CAP))
                self._mutate(lambda: s.errors.append(f"HTTP {resp.status}: {detail}"))
                return
            parser = SSEParser()
            while True:
                try:
                    data = resp.read1(READ_SIZE)
                except (http.client.HTTPException, OSError) as exc:
                    broken = f"{type(exc).__name__}: {exc}"
                    break
                if not data:
                    break
                for ev in parser.feed(data):
                    self._mutate(lambda ev=ev: self._handle(s, *ev))
            for ev in parser.close():
                self._mutate(lambda ev=ev: self._handle(s, *ev))
        except (http.client.HTTPException, OSError) as exc:
            broken = f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()
            self._mutate(lambda: self._finish(s, broken))

    @staticmethod
    def _handle(s, event, data):
        s.events.append(event)
        if event == "chunk":
            if isinstance(data, dict) and isinstance(data.get("delta"), str):
                s.text += data["delta"]
                s.first_delta = True
            else:
                s.errors.append(f"chunk event data is not a delta object: {str(data)[:120]!r}")
        elif event == "error":
            s.error_event = True
            msg = data.get("message") if isinstance(data, dict) else None
            s.errors.append(str(msg if msg is not None else data))
        elif event == "done":
            s.done = True

    @staticmethod
    def _finish(s, broken):
        if s.status == 200 and not s.done and not s.error_event:
            s.errors.append("stream ended without a done event" + (f" ({broken})" if broken else ""))
        elif broken and s.status is None:
            s.errors.append(broken)
        s.finished = True


def _error_detail(raw):
    text = raw.decode("utf-8", "replace")
    try:
        doc = json.loads(text)
    except ValueError:
        return text[:500]
    if isinstance(doc, dict) and "detail" in doc:
        return str(doc["detail"])[:500]
    return text[:500]
