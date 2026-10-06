"""`up`, `doctor`, `down`: start, inspect and stop one sandboxed reader3 server.

`up` builds a fresh `verify-reader3.*` sandbox in the temp dir, ingests the smoke corpus
(plus any `--epub`), starts `reader3-server --port N` there and waits for `/api/health`.
Only one `up` runs at a time (the claim). `down` stops only processes whose identity
matches the state file, and removes only a sandbox-shaped directory.
"""

import http.client
import os
import shutil
import signal
import socket
import tempfile
import time

from verify_control import cmd_ai, cmd_books, corpus, http_client, paths, procs, state
from verify_control.envelope import success
from verify_control.instance_common import SERVER_MARK, STUB_MARK, Fail, fail, is_exe, knob, load, resolve, run, setup
from verify_control.instance_doctor import cmd_doctor
from verify_control.registry import add

INGEST_TIMEOUT_S = 600.0
_INTERRUPT_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


# --------------------------------------------------------------------------- up


def _port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pick_port():
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        finally:
            s.close()
        if port != 8123 and 1024 <= port <= 65535:
            return port


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def _ignore_interrupts():
    for sig in (signal.SIGINT, *_INTERRUPT_SIGNALS):
        signal.signal(sig, signal.SIG_IGN)


def _tail(path, n=2000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _preflight(ns, repo):
    for flag, hook, ctx in ((ns.stale_index, cmd_books.seed_stale_index, ns), (ns.ai_stub, cmd_ai.start_stub, None)):
        if flag:
            env = hook("preflight", ctx)
            if env is not None:
                raise Fail(env)
    vbin = paths.venv_bin(os.environ, repo)
    missing = [str(vbin / n) for n in ("reader3", "reader3-server") if not is_exe(vbin / n)]
    if missing:
        raise fail("up", "venv_missing", "missing or not executable: " + ", ".join(missing) + "; run `uv sync`", "doctor")
    epubs = []
    for e in ns.epub or []:
        if not os.path.isfile(e):
            raise fail("up", "epub_missing", f"--epub {e} does not exist", "up --help")
        epubs.append(os.path.realpath(e))
    for cand in paths.temp_candidates(os.environ):
        paths.guard_books_dir(cand, repo)
    tmp = paths.temp_root(os.environ)
    paths.guard_books_dir(tmp, repo)
    port = ns.port if ns.port is not None else _pick_port()
    if not _port_free(port):
        raise fail("up", "port_in_use", f"127.0.0.1:{port} is in use", "up")
    return vbin, epubs, tmp, port



def _check_pointer(ptr, repo):
    try:
        sp = state.read_pointer(ptr)
    except state.StateError:
        return
    if sp is None or not os.path.lexists(sp):
        return
    ctx = f"pointer {ptr} names state {sp}: "
    try:
        old = state.load(sp, repo=repo, allow_missing_sandbox=True)
    except state.StateError:
        return
    except paths.GuardRefusal as exc:
        raise fail("up", exc.code, ctx + exc.message, "down") from None
    pid = old["pid"]
    if pid is not None and procs.alive(pid) and procs.pid_is_ours(pid, old["pid_start"], SERVER_MARK, port=old["port"]):
        raise fail("up", "refused_instance_running", f"an instance is running (pid {pid}, state {sp})", "down")


def _ingest(vbin, sandbox, epub):
    res = procs.run([vbin / "reader3", epub], env=procs.sandbox_env(sandbox), cwd=sandbox, timeout=INGEST_TIMEOUT_S)
    if res.exit != 0 or res.timed_out:
        why = "timed out" if res.timed_out else f"exit {res.exit}"
        raise fail("up", "ingest_failed", f"ingest of {epub} failed ({why}): {res.stderr[-2000:]}", "up")


def _books(books_dir):
    try:
        names = os.listdir(books_dir)
    except OSError:
        return []
    return sorted(n for n in names if n.endswith("_data") and os.path.isfile(os.path.join(books_dir, n, "book.pkl")))


def _wait_health(proc, base_url, log, grace):
    deadline = time.monotonic() + knob("VERIFY_READER3_HEALTH_TIMEOUT_S", 60)
    while True:
        if proc.poll() is not None:
            raise fail("up", "server_exited", f"server exited with {proc.returncode}; log tail: {_tail(log)}", "up")
        left = deadline - time.monotonic()
        if left <= 0:
            stuck = "" if procs.stop_child(proc, grace) else f"; server pid {proc.pid} survived SIGKILL"
            raise fail("up", "startup_timeout", f"/api/health did not answer 200{stuck}; log tail: {_tail(log)}", "up")
        try:
            status, _, _ = http_client.request(base_url, "GET", "/api/health", timeout=max(0.1, min(1.0, left)))
            if status == 200:
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.1)


def _start(ns, repo, ev_root, ptr, vbin, epubs, tmp, port):
    grace = knob("VERIFY_READER3_KILL_GRACE_S", 10)
    sandbox = os.path.realpath(tempfile.mkdtemp(prefix=paths.SANDBOX_PREFIX, dir=tmp))
    proc = None
    stub_ctx, stub = ({"sandbox": sandbox, "repo": str(repo)} if ns.ai_stub else None), {}
    try:
        books_dir, log = sandbox + "/books", sandbox + "/server.log"
        os.mkdir(books_dir)
        smoke = corpus.build_smoke(sandbox + "/smoke.epub", repo)
        for epub in [str(smoke), *epubs]:
            _ingest(vbin, sandbox, epub)
        if ns.stale_index:
            env = cmd_books.seed_stale_index("seed", {"sandbox": sandbox, "books_dir": books_dir})
            if env is not None:
                raise Fail(env)
        if stub_ctx is not None:
            stub = cmd_ai.start_stub("start", stub_ctx) or {}
            if "ok" in stub:
                raise Fail(stub)
        argv = [str(vbin / "reader3-server"), "--port", str(port)]
        proc = procs.spawn_logged(argv, env=procs.sandbox_env(sandbox), cwd=sandbox, log_path=log)
        ident = procs.read_identity(proc.pid)
        base_url = f"http://127.0.0.1:{port}"
        _wait_health(proc, base_url, log, grace)
        st = {
            "sandbox": sandbox, "books_dir": books_dir, "ai_settings": sandbox + "/ai_settings.json",
            "port": port, "base_url": base_url, "pid": proc.pid, "pid_start": ident.lstart if ident else None,
            "argv": argv, "log": log, "token": None, "stub_pid": None, "stub_pid_start": None,
            "stub_port": None, "repo": str(repo),
        }
        st.update(stub)
        state_path = sandbox + "/state.json"
        state.write(state_path, st)
        state.write_pointer(ev_root, state_path)
    except BaseException as exc:  # noqa: BLE001 - every failure, interrupts included, removes what up made
        _ignore_interrupts()
        if proc is not None:
            procs.stop_child(proc, min(grace, 2.0) if isinstance(exc, KeyboardInterrupt) else grace)
        if stub_ctx is not None:
            cmd_ai.stop_stub(stub_ctx)
        shutil.rmtree(sandbox, ignore_errors=True)
        raise
    keys = ("sandbox", "books_dir", "ai_settings", "port", "base_url", "pid", "pid_start", "log")
    return success("up", {**{k: st[k] for k in keys}, "state": state_path, "books": _books(books_dir), **stub})


def cmd_up(ns):
    for sig in _INTERRUPT_SIGNALS:
        signal.signal(sig, _raise_interrupt)

    def body():
        repo, ev_root, ptr = setup("up")
        vbin, epubs, tmp, port = _preflight(ns, repo)
        ev_root.mkdir(parents=True, exist_ok=True)
        claim = state.Claim(ev_root)
        me = procs.read_identity(os.getpid())
        if not claim.acquire({"pid": os.getpid(), "pid_start": me.lstart if me else None}):
            holder = claim.holder() or {}
            raise fail("up", "refused_instance_running",
                        f"another up (pid {holder.get('pid')}) holds {claim.path}", "down")
        try:
            _check_pointer(ptr, repo)
            return _start(ns, repo, ev_root, ptr, vbin, epubs, tmp, port)
        finally:
            claim.release()

    return run("up", body)


# --------------------------------------------------------------------------- down


def cmd_down(ns):
    def body():
        repo, ev_root, ptr = setup("down")
        sp = resolve("down", ns, ptr)
        d = {"dry_run": ns.dry_run, "pid": None, "killed": False, "signal": None, "stub_pid": None,
             "stub_killed": False, "sandbox": None, "removed_sandbox": False, "pointer_cleared": False,
             "already_stopped": True, "would_kill": [], "would_remove": None}
        names_sp = sp is not None and _pointer_names(ptr, sp)
        if sp is None or not os.path.lexists(sp):
            if names_sp and not ns.dry_run:
                d["pointer_cleared"] = state.clear_pointer(ev_root)
            return success("down", d)
        s = load("down", sp, repo, allow_missing=True)
        sandbox = s["sandbox"]
        d.update(pid=s["pid"], stub_pid=s["stub_pid"], sandbox=sandbox)
        present = os.path.lexists(sandbox)
        if present and not paths.sandbox_deletable(sandbox, paths.temp_root(os.environ)):
            raise fail("down", "refused_sandbox_shape",
                        f"{sandbox} is not a verify-reader3.* directory inside the temp dir", "down --dry-run")
        live = []
        for pid, start, mark, port in ((s["pid"], s["pid_start"], SERVER_MARK, s["port"]),
                                       (s["stub_pid"], s["stub_pid_start"], STUB_MARK, None)):
            if pid is not None and procs.alive(pid):
                if not procs.pid_is_ours(pid, start, mark, port=port):
                    raise fail("down", "refused_pid_identity",
                                f"pid {pid} is alive but is not this instance's {mark}; not killing it", "doctor")
                live.append(pid)
        d.update(already_stopped=not live, would_kill=live, would_remove=sandbox if present else None)
        if ns.dry_run:
            return success("down", d)
        grace = knob("VERIFY_READER3_KILL_GRACE_S", 10)
        if s["stub_pid"] in live:
            procs.terminate(s["stub_pid"], grace)
            d["stub_killed"] = not procs.alive(s["stub_pid"])
        if s["pid"] in live:
            d["signal"] = procs.terminate(s["pid"], grace)
            d["killed"] = not procs.alive(s["pid"])
        if present:
            shutil.rmtree(os.path.realpath(sandbox))
            d["removed_sandbox"] = True
        if names_sp:
            d["pointer_cleared"] = state.clear_pointer(ev_root)
        return success("down", d)

    return run("down", body)


def _pointer_names(ptr, sp):
    try:
        named = state.read_pointer(ptr)
    except state.StateError:
        return False
    return named is not None and os.path.abspath(named) == os.path.abspath(sp)


# --------------------------------------------------------------------------- parsers


def _port(text):
    import argparse

    if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"invalid port {text!r} (1-65535)")
    return int(text)


def register(subparsers):
    handlers = {}
    p = add(subparsers, "up", help="start a sandboxed reader3 server",
            examples=("up", "up --corpus smoke --epub ./some.epub", "up --port 50123"),
            handlers=handlers, handler=cmd_up)
    p.add_argument("--port", type=_port, help="port on 127.0.0.1 (default: a free port, never 8123)")
    p.add_argument("--epub", action="append", help="extra EPUB to ingest (repeatable)")
    p.add_argument("--corpus", choices=("smoke",), default=None, help="built-in corpus to ingest")
    p.add_argument("--ai-stub", action="store_true", help="also start the offline AI stub")
    p.add_argument("--stale-index", action="store_true", help="seed a stale semantic index")
    p = add(subparsers, "doctor", help="check the running instance", examples=("doctor",),
            handlers=handlers, handler=cmd_doctor)
    p.add_argument("--state", help="state file (default: the recorded instance)")
    p = add(subparsers, "down", help="stop the instance and remove its sandbox",
            examples=("down", "down --dry-run"), handlers=handlers, handler=cmd_down)
    p.add_argument("--state", help="state file (default: the recorded instance)")
    p.add_argument("--dry-run", action="store_true", help="report what would happen; change nothing")
    return handlers
