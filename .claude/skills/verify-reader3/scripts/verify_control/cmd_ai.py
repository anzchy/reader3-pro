"""`ai ask` and the `up --ai-stub` hooks.

`up --ai-stub` starts `ai_stub_runner.py` (the frozen `OllamaStub` in its own process),
waits for its ready file, then writes the sandbox `ai_settings.json` (0600) pointing the
`ollama` provider at it, all before the server starts.

`ai ask` POSTs `/api/ai/question/<book_uuid>?stream=true` N times in parallel and parses
each SSE stream. With a stub recorded, it drives the gate through the runner's files:
ungated asks release first; `--gate` arms first and must see the arm consumed within 2 s.
"""

import argparse
import json
import os
import re
import stat
import sys
import time
import uuid

from verify_control import ai_stream, procs, state
from verify_control.ai_stub_runner import GATE_ARM_FILE, GATE_RELEASE_FILE, LOG_FILE, READY_FILE, STATS_FILE
from verify_control.envelope import success
from verify_control.instance_common import fail, knob, load, resolve, run, setup
from verify_control.registry import add, group

OWNER = "WI-3"
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_stub_runner.py")
STUB_DIR = "ai_stub"
READY_KNOB = "VERIFY_READER3_STUB_READY_TIMEOUT_S"
IPC_WAIT_S = 2.0
RELEASE_SETTLE_S = 0.1
SMALL_FILE_CAP = 65536
GATES = ("hold", "release-after-first-delta")
_BOOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", re.ASCII)


# ------------------------------------------------------------------ up --ai-stub


def _tail(path, n=2000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _read_ready(d, pid):
    try:
        with open(os.path.join(d, READY_FILE), encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(doc, dict) and doc.get("pid") == pid and isinstance(doc.get("port"), int):
        return doc
    return None


def _settings(port):
    return {
        "default_provider": "ollama",
        "preferences": {"streaming_enabled": True},
        "providers": {"ollama": {"enabled": True, "base_url": f"http://127.0.0.1:{port}",
                                 "model_name": "stub-model", "timeout_s": 10, "max_retries": 0}},
    }


def start_stub(phase, ctx):
    """`up --ai-stub` hook. At "preflight" there is nothing to check. At "start" (sandbox in
    `ctx`) spawn the runner, wait for ready, write the settings, and return the state fields
    stub_pid, stub_pid_start, stub_port. A failure returns an envelope; `ctx["proc"]` is set
    before any wait so `stop_stub` can kill the runner after an interrupt."""
    if phase != "start":
        return None
    sandbox = ctx["sandbox"]
    d = os.path.join(sandbox, STUB_DIR)
    os.mkdir(d, 0o700)
    log = os.path.join(d, LOG_FILE)
    argv = [sys.executable, RUNNER, "--state-dir", d, "--gate"]
    proc = procs.spawn_logged(argv, env=procs.sandbox_env(sandbox), cwd=sandbox, log_path=log)
    ctx["proc"] = proc
    limit = knob(READY_KNOB, 10)
    deadline = time.monotonic() + limit
    while True:
        ready = _read_ready(d, proc.pid)
        if ready is not None:
            break
        if proc.poll() is not None:
            return fail("up", "stub_failed", f"stub runner exited with {proc.returncode} before ready; "
                        f"log tail: {_tail(log)}", "up --ai-stub").env
        if time.monotonic() > deadline:
            stop_stub(ctx)
            return fail("up", "stub_failed", f"stub runner not ready within {limit:g}s; log tail: {_tail(log)}",
                        "up --ai-stub").env
        time.sleep(0.05)
    ident = procs.read_identity(proc.pid)
    state.atomic_write_json(os.path.join(sandbox, "ai_settings.json"), _settings(ready["port"]))
    return {"stub_pid": proc.pid, "stub_pid_start": ident.lstart if ident else None, "stub_port": ready["port"]}


def stop_stub(ctx):
    """Undo `start_stub` when `up` fails after it ran: stop the runner it spawned."""
    proc = (ctx or {}).get("proc")
    if proc is not None:
        procs.stop_child(proc, min(knob("VERIFY_READER3_KILL_GRACE_S", 10), 2.0))
    return None


# ------------------------------------------------------------------ ai ask


def _read_small(path):
    """Read a regular file (checked with stat first, so a FIFO is never opened), capped."""
    st = os.stat(path)
    if not stat.S_ISREG(st.st_mode):
        raise OSError(f"{path} is not a regular file")
    with open(path, "rb") as f:
        return f.read(SMALL_FILE_CAP)


def _book_dir(st, book):
    books = os.path.realpath(st["books_dir"])
    if not _BOOK.fullmatch(book or "") or book in (".", ".."):
        raise fail("ai ask", "refused_path", f"--book {book!r} is not a plain book folder name", "books")
    real = os.path.realpath(os.path.join(books, book))
    if os.path.dirname(real) != books:
        raise fail("ai ask", "refused_path", f"--book {book!r} resolves outside the sandbox books dir", "books")
    if not os.path.isdir(real):
        raise fail("ai ask", "book_not_found", f"no book folder {book!r} in the sandbox", "books")
    meta = os.path.join(real, "ai_meta.json")
    if os.path.lexists(meta) and os.path.dirname(os.path.realpath(meta)) != real:
        raise fail("ai ask", "refused_path", f"{book}/ai_meta.json resolves outside the book folder", "books")
    return meta


def _book_uuid(meta, book):
    why = None
    try:
        doc = json.loads(_read_small(meta).decode("utf-8"))
        value = doc.get("book_uuid") if isinstance(doc, dict) else None
        if isinstance(value, str) and str(uuid.UUID(value)) == value:
            return value
        why = "has no canonical book_uuid"
    except FileNotFoundError:
        why = "does not exist"
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        why = f"is unreadable ({type(exc).__name__})"
    raise fail("ai ask", "no_book_uuid", f"{book}/ai_meta.json {why}; the CLI never writes one",
               f"fs cat books/{book}/ai_meta.json")


def _provider(st):
    try:
        doc = json.loads(_read_small(st["ai_settings"]).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return "ollama"
    value = doc.get("default_provider") if isinstance(doc, dict) else None
    return value if isinstance(value, str) and value else "ollama"


def _stub_dir(st):
    d = os.path.join(st["sandbox"], STUB_DIR)
    if os.path.islink(d) or not os.path.isdir(d):
        raise fail("ai ask", "stub_unresponsive", f"stub dir {d} is missing or not a directory", "doctor")
    return d


def _signal(d, name):
    """Write one IPC file and wait for the runner to consume it; remove it on timeout."""
    path = os.path.join(d, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    deadline = time.monotonic() + IPC_WAIT_S
    while os.path.lexists(path):
        if time.monotonic() > deadline:
            try:
                os.unlink(path)
            except FileNotFoundError:
                return True
            raise fail("ai ask", "stub_unresponsive", f"the stub runner did not consume {name} within "
                       f"{IPC_WAIT_S:g}s", "doctor")
        time.sleep(0.01)
    return True


def _stats(d):
    time.sleep(0.12)  # the real runner refreshes its stats file every 50 ms
    try:
        doc = json.loads(_read_small(os.path.join(d, STATS_FILE)).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _ask(ns):
    t0 = time.monotonic()
    repo, _ev_root, ptr = setup("ai ask")
    st = load("ai ask", resolve("ai ask", ns, ptr), repo)
    meta = _book_dir(st, ns.book)
    book_uuid = _book_uuid(meta, ns.book)
    provider = _provider(st)
    stub = st["stub_pid"] is not None
    if ns.gate and not stub:
        raise fail("ai ask", "no_stub", "--gate needs the AI stub; none is recorded in state", "up --ai-stub")
    path = f"/api/ai/question/{book_uuid}?stream=true"
    body = {"question": ns.question, "provider": provider}
    data = {"book": ns.book, "book_uuid": book_uuid, "provider": provider, "concurrency": ns.concurrency}
    if ns.dry_run:
        req = {"method": "POST", "url": st["base_url"] + path, "body": body}
        return success("ai ask", {**data, "dry_run": True, "requests": [dict(req) for _ in range(ns.concurrency)]})
    d = _stub_dir(st) if stub else None
    released = False
    if stub:
        released = _signal(d, GATE_ARM_FILE if ns.gate else GATE_RELEASE_FILE) and not ns.gate
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if st.get("token"):
        headers["X-Reader3-Token"] = st["token"]
    port = st["port"]
    runner = ai_stream.Run(port, path, body, headers, ns.concurrency, read_timeout=ns.timeout + 5)
    deadline = time.monotonic() + ns.timeout
    gate = {"mode": ns.gate, "released": released}
    seen = []

    def on_poll():
        # Release once every stream has shown its first delta, after a short settle so the
        # server side has finished its write of that delta before the gate opens.
        if ns.gate != "release-after-first-delta" or gate["released"] or not runner.all_have_first_delta():
            return
        seen.append(time.monotonic())
        if seen[-1] - seen[0] >= RELEASE_SETTLE_S:
            gate["released"] = _signal(d, GATE_RELEASE_FILE)

    runner.start()
    finished = runner.wait(deadline, on_poll)
    if not finished:
        runner.freeze(f"timed out after {ns.timeout:g}s")
    results = runner.results()
    data.update({"gate": gate, "results": results, "stub_stats": _stats(d) if stub else None,
                 "dry_run": False, "timed_out": not finished, "elapsed_ms": int((time.monotonic() - t0) * 1000)})
    if not finished:
        raise fail("ai ask", "ai_timeout", f"not every stream finished within {ns.timeout:g}s", "doctor", data)
    bad = [r for r in results if r["status"] != 200 or r["errors"]]
    if bad:
        first = bad[0]["errors"][0] if bad[0]["errors"] else f"HTTP {bad[0]['status']}"
        raise fail("ai ask", "ai_failed", f"{len(bad)} of {len(results)} streams failed: {first}", "doctor", data)
    return success("ai ask", data)


def cmd_ask(ns):
    return run("ai ask", lambda: _ask(ns))


def _concurrency(v):
    try:
        n = int(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--concurrency {v!r} is not an integer") from None
    if not 1 <= n <= 8:
        raise argparse.ArgumentTypeError(f"--concurrency {n} is outside 1-8")
    return n


def _seconds(v):
    try:
        s = float(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--timeout {v!r} is not a number") from None
    if not 0 < s <= 3600:
        raise argparse.ArgumentTypeError(f"--timeout {s:g} is outside (0, 3600]")
    return s


def register(subparsers):
    handlers = {}
    ai = group(subparsers, "ai", help="ask the sandbox AI assistant", subcommands=("ask",),
               examples=('ai ask "Who is the narrator?" --book smoke_data',))
    p = add(ai, "ai ask", help="ask one question about a sandbox book",
            examples=('ai ask "Who is the narrator?" --book smoke_data',
                      'ai ask "q" --book smoke_data --concurrency 2 --gate release-after-first-delta',
                      'ai ask "q" --book smoke_data --dry-run'),
            handlers=handlers, handler=cmd_ask)
    p.add_argument("question", help="the question text")
    p.add_argument("--book", required=True, help="book folder, e.g. smoke_data")
    p.add_argument("--concurrency", type=_concurrency, default=1, help="parallel streams, 1-8 (default 1)")
    p.add_argument("--gate", choices=GATES, help="drive the stub gate (needs up --ai-stub)")
    p.add_argument("--timeout", type=_seconds, default=30.0, help="overall deadline in seconds (default 30)")
    p.add_argument("--dry-run", action="store_true", help="print the requests; send nothing")
    p.add_argument("--state", help="state file (default: the recorded instance)")
    return handlers
