"""WI-5 fakes for the verify-reader3 control CLI: fake `uv` / `npm` lane runners.

Contract: `.claude/tdd-guardian/tests-20261002-170349-WI-4-5-6.md` section 0 item 5,
read through the unified contract U4 (every fake logs to `tmp_path/fakelog/<name>.jsonl`)
and U8 (WI-5 owns this file; the base helper is not edited).

`fake_runners(tmp_path, scripts=...)` writes executables `uv` and `npm` into
`tmp_path/runner-bin/`. Each one appends `{"name", "argv", "cwd", "pid"}` to
`tmp_path/fakelog/runners.jsonl` (`argv` is the full `sys.argv`, so `argv[1:]` is what a
real runner would receive), prints `FAKE-<name>-OUT <argv>` to stdout, then applies the
first script entry whose `name` matches and whose `contains` is a substring of
`" ".join(argv[1:])`: it sleeps `sleep_s`, writes `stderr`, and exits with `exit`.
Without a matching entry it exits 0. Every fake kills itself after 120 s, and its
command line names `tmp_path`, so `reap_fakes` can kill it at teardown.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from verify_control_support import _read_jsonl, _write_exe, base_env

_FAKE_RUNNER = r'''
import json, os, signal, sys, time
CFG = json.loads(__CFG__)
NAME = CFG["name"]
signal.alarm(120)
os.makedirs(CFG["log_dir"], exist_ok=True)
with open(os.path.join(CFG["log_dir"], "runners.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"name": NAME, "argv": sys.argv, "cwd": os.getcwd(), "pid": os.getpid()}) + "\n")
print("FAKE-%s-OUT %s" % (NAME, json.dumps(sys.argv[1:])))
sys.stdout.flush()
rest = " ".join(sys.argv[1:])
for entry in CFG["scripts"]:
    if entry.get("name", NAME) != NAME:
        continue
    if entry.get("contains") is not None and entry["contains"] not in rest:
        continue
    if entry.get("sleep_s"):
        time.sleep(float(entry["sleep_s"]))
    if entry.get("stderr"):
        sys.stderr.write(entry["stderr"] + "\n")
        sys.stderr.flush()
    sys.exit(int(entry.get("exit", 0)))
sys.exit(0)
'''


def fake_runners(tmp_path: Path, *, scripts: Iterable[Dict[str, Any]] = ()) -> Path:
    """Write fake `uv` and `npm`; return the bin dir to put first on `PATH`."""
    log_dir = Path(tmp_path) / "fakelog"
    log_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = Path(tmp_path) / "runner-bin"
    for name in ("uv", "npm"):
        cfg = {"name": name, "log_dir": str(log_dir), "scripts": list(scripts)}
        _write_exe(bin_dir / name, _FAKE_RUNNER.replace("__CFG__", repr(json.dumps(cfg))))
    return bin_dir


def runner_log_path(tmp_path: Path) -> Path:
    return Path(tmp_path) / "fakelog" / "runners.jsonl"


def runner_calls(tmp_path: Path) -> List[Dict[str, Any]]:
    """The runner argv log; `[]` when absent (assert absence separately where it matters)."""
    return _read_jsonl(runner_log_path(tmp_path))


def lane_env(tmp_path: Path, *, scripts: Iterable[Dict[str, Any]] = ()) -> Dict[str, str]:
    """LANE-ENV: `base_env` plus the fake runners first on `PATH` (the real `PATH` after them)."""
    env = base_env(tmp_path)
    bin_dir = fake_runners(tmp_path, scripts=scripts)
    env["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return env
