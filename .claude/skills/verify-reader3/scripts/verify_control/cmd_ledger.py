"""`lane FEATURE` and `map check` against the feature ledger.

`lane F-NNN` reads the row's Tests entries, sorts them into pytest / e2e / vitest
(`ledger.classify`) and runs each selected runner once, as an argv list with no shell,
bounded by `--timeout`, from the repo root, logging to `<evidence>/lane-<runner>.log`.
Every selected runner runs even after one fails. A real run needs an open evidence
folder; `--dry-run` only reports the argv. The error code is the worst outcome:
`lane_failed` (a non-zero exit that is not a lock BUSY) over `lane_timeout` over
`lane_busy` (exit 75 with a `BUSY ` stderr line from `scripts/e2e_lock.py`).
"""

import argparse
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from verify_control import evidence, instance_common, ledger, map_check, procs
from verify_control.envelope import success
from verify_control.registry import add, group

# Re-exported for callers and tests: the classifier, the argv builder, the command checker.
classify = ledger.classify
build_argv = ledger.build_argv
check_command_line = map_check.check_command_line

# The one function that starts a lane child. Looked up at call time so it can be replaced.
spawn = procs.run

BUSY_EXIT = 75
DEFAULT_TIMEOUT_S = 1800.0


def _root(ns, repo):
    return Path(os.path.abspath(ns.root)) if getattr(ns, "root", None) else Path(repo)


def _setup(cmd, ns):
    repo, ev_root, _ = instance_common.setup(cmd)
    evidence.guard_root(ev_root, getattr(ns, "root", None))
    return repo, ev_root, _root(ns, repo)


def _features(cmd, root):
    try:
        return ledger.load_features(root)
    except ledger.LedgerError as exc:
        raise instance_common.fail(cmd, "ledger_invalid", exc.message, "map check") from None


def _is_busy(result):
    return result.exit == BUSY_EXIT and any(ln.startswith("BUSY ") for ln in (result.stderr or "").splitlines())


def _write_log(log, fid, runner, argv, result, duration):
    head = (f"=== lane {fid} {runner} at {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
            f"argv: {argv!r}\n")
    tail = f"=== exit {result.exit} timed_out {result.timed_out} after {duration:.2f}s\n"
    with open(log, "a", encoding="utf-8", errors="replace") as f:
        f.write(head + "--- stdout ---\n" + (result.stdout or "") + "\n--- stderr ---\n" + (result.stderr or "") + "\n" + tail)


def _run_one(fid, runner, argv, root, evdir, timeout):
    log = Path(evdir) / f"lane-{runner}.log"
    t0 = time.monotonic()
    try:
        result = spawn(argv, env=dict(os.environ), cwd=os.path.realpath(str(root)), timeout=timeout)
    except OSError as exc:
        result = procs.RunResult(127, "", f"could not start {argv[0]}: {exc}", False, 0)
    duration = float(time.monotonic() - t0)
    _write_log(log, fid, runner, argv, result, duration)
    return {"runner": runner, "argv": argv, "exit": None if result.timed_out else result.exit,
            "duration_s": duration, "log": str(log), "timed_out": bool(result.timed_out), "busy": _is_busy(result)}


def _outcome(runs):
    """`(code, run)` of the worst run, or None when every run passed."""
    for code, pred in (("lane_failed", lambda r: not r["timed_out"] and not r["busy"] and r["exit"] != 0),
                       ("lane_timeout", lambda r: r["timed_out"]),
                       ("lane_busy", lambda r: r["busy"])):
        hit = next((r for r in runs if pred(r)), None)
        if hit is not None:
            return code, hit
    return None


def _lane(ns):
    cmd = "lane"
    fid = ns.feature
    repo, ev_root, root = _setup(cmd, ns)
    features = _features(cmd, root)
    row = features.get(fid)
    if row is None:
        raise instance_common.fail(cmd, "unknown_feature", f"{fid} is not a row of the feature ledger", "map check")
    entries = list(row.get("tests") or [])
    if not entries:
        raise instance_common.fail(cmd, "no_tests", f"{fid} lists no tests in the ledger", "map check")
    cls = ledger.classify(entries, root)
    selected = ledger.RUNNERS if ns.runner == "all" else (ns.runner,)
    chosen = [r for r in selected if cls[r]]
    if not chosen:
        what = "runnable" if ns.runner == "all" else ns.runner
        raise instance_common.fail(cmd, "no_tests", f"{fid} has no {what} tests that exist in this checkout",
                                   f"lane {fid} --dry-run")
    data = {"feature": fid, "classification": cls, "runs": [], "skipped": cls["skipped"], "evidence_dir": None}
    try:
        cur = evidence.current(ev_root)
    except evidence.EvidenceError as exc:
        raise instance_common.fail(cmd, exc.code, exc.message, "evidence show") from None
    if cur is not None:
        data["evidence_dir"] = str(cur[0])
    if ns.dry_run:
        data["runs"] = [{"runner": r, "argv": ledger.build_argv(r, cls[r]), "exit": None, "duration_s": None,
                         "log": None, "timed_out": False, "busy": False} for r in chosen]
        return success(cmd, data)
    if cur is None:
        raise instance_common.fail(cmd, "no_evidence", "a real lane run needs an open evidence folder",
                                   f"evidence start {fid}")
    data["runs"] = [_run_one(fid, r, ledger.build_argv(r, cls[r]), root, cur[0], ns.timeout) for r in chosen]
    worst = _outcome(data["runs"])
    if worst is None:
        return success(cmd, data)
    code, run = worst
    msg = f"{fid}: the {run['runner']} run " + ("timed out" if run["timed_out"] else f"exited {run['exit']}")
    raise instance_common.fail(cmd, code, msg + f"; see {run['log']}", f"lane {fid} --runner {run['runner']}", data=data)


def _map_check(ns):
    cmd = "map check"
    _, _, root = _setup(cmd, ns)
    features = _features(cmd, root)
    data = map_check.check(root, features, ledger.is_absent)
    if data["problems"] or data["dead_commands"]:
        msg = f"{len(data['problems'])} map problem(s), {len(data['dead_commands'])} dead command(s)"
        raise instance_common.fail(cmd, "map_invalid", msg, "map check", data=data)
    return success(cmd, data)


def _seconds(v):
    """`--timeout`: a finite float > 0 (0, negatives, nan and inf would reach `procs.run`)."""
    try:
        s = float(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--timeout {v!r} is not a number") from None
    if not (math.isfinite(s) and s > 0):
        raise argparse.ArgumentTypeError(f"--timeout {v!r} must be a finite number of seconds > 0")
    return s


def _wrap(cmd, fn):
    def handler(ns):
        return instance_common.run(cmd, lambda: fn(ns))

    return handler


def register(subparsers):
    handlers = {}
    p = add(subparsers, "lane", help="run the ledger's tests for one feature, runner by runner",
            examples=("lane F-011", "lane F-018 --runner e2e", "lane F-020 --dry-run"),
            handlers=handlers, handler=_wrap("lane", _lane))
    p.add_argument("feature", type=evidence.feature_id, help="feature id, e.g. F-011")
    p.add_argument("--runner", choices=("pytest", "e2e", "vitest", "all"), default="all",
                   help="which runner to run (default all, in the order pytest, e2e, vitest)")
    p.add_argument("--dry-run", action="store_true", help="only report the classification and argv")
    p.add_argument("--timeout", type=_seconds, default=DEFAULT_TIMEOUT_S, metavar="S",
                   help="per-run timeout in seconds (default 1800)")
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    m = group(subparsers, "map", help="feature-to-check map", subcommands=("check",), examples=("map check",))
    p = add(m, "map check", help="check the feature map against the ledger and its commands against the parser",
            examples=("map check",), handlers=handlers, handler=_wrap("map check", _map_check))
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    return handlers
