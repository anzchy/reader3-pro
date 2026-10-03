"""Out-of-process runner for the frozen `OllamaStub` (`up --ai-stub`).

Run as `python ai_stub_runner.py --state-dir D --gate`. It starts the stub in gate mode,
writes `D/stub.ready.json` = {"port", "pid"}, then polls `D` every 50 ms:

* `gate.release` sets the gate, `gate.arm` clears it; each file is deleted once consumed,
  so the gate is a last-op-wins register (WI3-C08);
* `stub.stats.json` is rewritten atomically whenever the stub's counters change.

SIGTERM, SIGINT and SIGHUP write the final stats and exit 0 without joining the stub's
handler threads (a held request must not keep the process alive). The runner also exits
when `D` disappears. The stub module is `<repo>/tests/fixtures/ai_stub.py`, or the file
named by the hidden knob `VERIFY_READER3_STUB_MODULE` (it must exist).
"""

import argparse
import importlib.util
import json
import os
import signal
import sys
import time
from pathlib import Path

READY_FILE = "stub.ready.json"
STATS_FILE = "stub.stats.json"
GATE_RELEASE_FILE = "gate.release"
GATE_ARM_FILE = "gate.arm"
LOG_FILE = "runner.log"
STUB_MODULE_KNOB = "VERIFY_READER3_STUB_MODULE"
POLL_S = 0.05

_stop = []


def _atomic(path, obj):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _load_stub_module():
    override = os.environ.get(STUB_MODULE_KNOB)
    if override:
        path = Path(override)
        if not path.is_file():
            raise SystemExit(f"ai_stub_runner: {STUB_MODULE_KNOB}={override} does not exist")
    else:
        path = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "ai_stub.py"
    spec = importlib.util.spec_from_file_location("verify_reader3_ai_stub", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stats(stub):
    with stub._lock:
        return {
            "request_count": stub.request_count,
            "completed": bool(stub.completed),
            "gate_released_by_render": bool(stub.gate_released_by_render),
            "gate_timed_out": bool(stub.gate_timed_out),
            "payloads": len(stub.payloads),
            "gate_set": stub.gate.is_set(),
        }


def _consume(path):
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ai_stub_runner.py")
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--gate", action="store_true")
    ns = ap.parse_args(argv)
    d = ns.state_dir
    mod = _load_stub_module()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda signum, frame: _stop.append(signum))
    stub = mod.OllamaStub(gate_mode=ns.gate)
    stub.start()
    last = _stats(stub)
    _atomic(os.path.join(d, STATS_FILE), last)
    _atomic(os.path.join(d, READY_FILE), {"port": stub.port, "pid": os.getpid()})
    while not _stop and os.path.isdir(d):
        if _consume(os.path.join(d, GATE_ARM_FILE)):
            stub.gate.clear()
        if _consume(os.path.join(d, GATE_RELEASE_FILE)):
            stub.gate.set()
        now = _stats(stub)
        if now != last:
            _atomic(os.path.join(d, STATS_FILE), now)
            last = now
        time.sleep(POLL_S)
    if os.path.isdir(d):
        _atomic(os.path.join(d, STATS_FILE), _stats(stub))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
