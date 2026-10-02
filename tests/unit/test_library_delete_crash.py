"""018 WI-5a: the crash matrix (matrix case CR-1, law 5).

Each of the 22 kill points runs ``delete_book`` in a real child interpreter that
SIGKILLs itself at that step (``delete_world.crash_child_main``); the parent then
sweeps in a fresh child (``sweep_child_main``) and compares the trees.

The children are launched in parallel by one module-scoped fixture, which only
spawns subprocesses and never imports ``reader3_app.library_delete`` itself; the
in-process reference delete happens inside each test. At red the fixture spawns
nothing and every node fails on the ``ld()`` guard it calls first.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest
from delete_world import (
    SUBPROCESS_TIMEOUT_S,
    f1_world,
    finish,
    ld,
    ld_present,
    observable_state,
    popen_child,
    probe_lock,
)

FALSE_POINTS = [
    "swept",
    "locked",
    "intent_written",
    "committed",
    "fin_collections",
    "fin_caches",
    "conv_published#1",
    "conv_published#2",
    "conv_done",
    "rmtree_partial",
    "rmtree_done",
    "intent_removed",
]
TRUE_POINTS = [p for p in FALSE_POINTS if not p.startswith("conv_published")]
CASES = [("false", p) for p in FALSE_POINTS] + [("true", p) for p in TRUE_POINTS]
CASE_IDS = [f"{mode}-{point}" for mode, point in CASES]
PRE_COMMIT = {"swept", "locked", "intent_written"}

assert len(CASES) == 22


@pytest.fixture(scope="module")
def crash_runs(tmp_path_factory):
    """Launch all 22 crash children in parallel, then a sweep child for each one that died."""
    if not ld_present():
        # Red: spawn nothing. Each test then fails on the ``ld()`` guard it calls first.
        yield None
        return
    base = tmp_path_factory.mktemp("cr1")
    runs = {}
    procs = []
    try:
        for mode, point in CASES:
            tag = f"{mode}-{point}".replace("#", "_")
            w = f1_world(base / tag)
            sentinel = base / f"{tag}.sentinel"
            runs[(mode, point)] = {"world": w, "before": observable_state(w.books, w.R, w.coll), "sentinel": sentinel}
            proc = popen_child("crash_child_main", str(w.books), str(w.R), str(w.coll), mode, point, str(sentinel))
            procs.append(proc)
            runs[(mode, point)]["proc"] = proc
        for key, run in runs.items():
            rc, out, err = finish(run["proc"], SUBPROCESS_TIMEOUT_S)
            run["crash"] = (rc, out, err)
            run["tag"] = run["sentinel"].read_text(encoding="utf-8") if run["sentinel"].is_file() else None

        sweeps = {}
        for key, run in runs.items():
            if run["crash"][0] != -signal.SIGKILL:
                continue
            out_path = base / f"{key[0]}-{key[1].replace('#', '_')}.sweep.json"
            run["sweep_out"] = out_path
            proc = popen_child("sweep_child_main", str(run["world"].books), str(out_path))
            procs.append(proc)
            sweeps[key] = proc
        for key, proc in sweeps.items():
            rc, out, err = finish(proc, SUBPROCESS_TIMEOUT_S)
            run = runs[key]
            run["sweep"] = (rc, out, err)
            out_path = run["sweep_out"]
            run["sweep_result"] = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else None
        yield runs
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.communicate(timeout=10)
                except Exception:  # noqa: BLE001 - best-effort reap in teardown
                    pass


def _reference_state(tmp_path, mode):
    ref = f1_world(Path(tmp_path) / "ref")
    ref.delete(mode=(mode == "true"))
    return ref.state()


@pytest.mark.parametrize(("mode", "point"), CASES, ids=CASE_IDS)
def test_cr1_sigkill_at_every_step_then_sweep_converges(tmp_path, crash_runs, mode, point):
    """CR-1: SIGKILL at ``point`` then a fresh-process sweep -> before-state (pre-commit) or a clean delete."""
    ld()  # red guard: the fixture spawned no child when the module is missing
    expected_after = _reference_state(tmp_path, mode)
    run = crash_runs[(mode, point)]
    rc, out, err = run["crash"]

    assert rc == -signal.SIGKILL, f"the crash child exited {rc} instead of dying at {point}: {err[-3000:]}"
    assert run["tag"] == point, f"the crash child died at {run['tag']!r}, expected {point!r}"

    s_rc, s_out, s_err = run["sweep"]
    assert s_rc == 0, f"the sweep child failed: {s_err[-3000:]}"
    report = run["sweep_result"]["report"]
    w = run["world"]

    if point in PRE_COMMIT:
        assert observable_state(w.books, w.R, w.coll) == run["before"]
        assert sorted(n for n in os.listdir(w.books) if n.startswith(".") and n != ".locks") == []
        if point == "intent_written":
            assert len(report["orphan_intents"]) == 1, report
            parsed = ld().parse_intent(os.path.basename(report["orphan_intents"][0]))
            assert parsed is not None and parsed[0] == "a_data"
    else:
        assert observable_state(w.books, w.R, w.coll) == expected_after

    assert probe_lock(w.books, "a_data", "exclusive") == ("acquired", None)
