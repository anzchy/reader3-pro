"""013 WI-9 A9.4 (case C9.18): dependency-cruiser runs with zero rules and really cruises the TS.

Zero rules is the WI-9 state (WI-14 fills them). "Zero rules and passes" is only worth
something if the tool actually parsed the sources: a wrong path cruises nothing and also
passes. So besides rc and the empty `forbidden` array, every `.ts` file under
`frontend/src/` must appear among the cruised modules, and none of the cruised
dependencies may be unresolved (an alias depcruise cannot follow shows up as
`couldNotResolve`).

Needs Node and `npm ci`; missing either fails. Child processes are time-bounded.
"""

from __future__ import annotations

import json

import frontend_host as fh

DEPCRUISE_TIMEOUT_S = 180
CONFIG_NAME = ".dependency-cruiser.cjs"


def test_depcruise_zero_rules_passes() -> None:
    fh.require_node_toolchain()
    assert (fh.REPO_ROOT / CONFIG_NAME).is_file(), f"{CONFIG_NAME} missing at the repo root"

    cfg = fh.run(
        ["node", "-e", f"process.stdout.write(JSON.stringify(require('./{CONFIG_NAME}').forbidden ?? null))"],
        cwd=fh.REPO_ROOT,
        timeout=60,
    )
    assert cfg.returncode == 0, fh.describe(cfg)
    assert json.loads(cfg.stdout) == [], f"forbidden must be an explicit empty array, got {cfg.stdout!r}"

    proc = fh.run(
        ["npx", "--no-install", "depcruise", "--config", CONFIG_NAME, "frontend/src", "--output-type", "json"],
        cwd=fh.REPO_ROOT,
        timeout=DEPCRUISE_TIMEOUT_S,
    )
    assert proc.returncode == 0, fh.describe(proc)
    report = json.loads(proc.stdout)

    ts_files = sorted(p.relative_to(fh.REPO_ROOT).as_posix() for p in fh.FE_SRC.rglob("*.ts"))
    assert ts_files, "frontend/src has no .ts files"
    cruised = {m["source"] for m in report["modules"]}
    assert set(ts_files) <= cruised, f"not cruised: {sorted(set(ts_files) - cruised)}"
    assert report["summary"]["totalCruised"] >= len(ts_files), report["summary"]

    unresolved = [
        (m["source"], d["module"])
        for m in report["modules"]
        for d in m.get("dependencies", [])
        if d.get("couldNotResolve")
    ]
    assert unresolved == [], f"depcruise could not resolve: {unresolved}"
    assert report["summary"]["violations"] == [], report["summary"]["violations"]
