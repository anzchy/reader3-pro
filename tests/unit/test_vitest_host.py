"""013 WI-9 A9.8 / A9.15 (cases C9.19-C9.21): the Vitest + jsdom host is real.

Three claims, each able to go red on its own:

- C9.19 a green `npm test` ran at least one test (a `passWithNoTests` host with an
  empty include glob would exit 0 having specified nothing);
- C9.20 a seeded failing spec turns both `npm test` and the fe-unit lane command
  from `.claude/tdd-guardian/config.json` red (a lane written as `npm test || true`
  would not);
- C9.21 Vite and Vitest resolve every alias key to the same place, and retargeting the
  alias at its single definition moves both (a copy of the alias map pasted into
  `vitest.config.ts` would drift).

Needs Node and `npm ci`. Missing either is a failure, not a skip (see
`frontend_host.require_node_toolchain`). Every child process is time-bounded.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontend_host as fh

CONFIG = fh.REPO_ROOT / ".claude" / "tdd-guardian" / "config.json"
VITEST_TIMEOUT_S = 180
PROBE_TIMEOUT_S = 180

#: The one real module every alias check resolves through.
ALIAS_KEY = "@shared"
ALIAS_PROBE_SPEC = "@shared/boot"


def _vitest_json(workspace: Path, report: Path):
    proc = fh.run(
        ["npm", "test", "--", "--reporter=json", f"--outputFile={report}"],
        cwd=workspace,
        timeout=VITEST_TIMEOUT_S,
    )
    data = json.loads(report.read_text()) if report.is_file() else None
    return proc, data


def _fe_unit_lane() -> dict:
    lanes = json.loads(CONFIG.read_text())["lanes"]
    matches = [lane for lane in lanes if lane["name"] == "fe-unit"]
    assert len(matches) == 1, f"expected exactly one fe-unit lane, found {[lane['name'] for lane in lanes]}"
    return matches[0]


def test_green_run_nonempty(tmp_path: Path) -> None:
    """C9.19: `npm test` in R passes with numTotalTests >= 1 and numFailedTests == 0."""
    fh.require_node_toolchain()
    proc, data = _vitest_json(fh.REPO_ROOT, tmp_path / "r.json")
    assert proc.returncode == 0, fh.describe(proc)
    assert data is not None, "vitest wrote no JSON report\n" + fh.describe(proc)
    assert data["numFailedTests"] == 0, data
    assert data["numTotalTests"] >= 1, f"green run specified nothing: {data['numTotalTests']} tests"


def test_seeded_failure_goes_red(tmp_path: Path) -> None:
    """C9.20 / A9.15: one seeded failing spec -> `npm test` and the fe-unit lane both rc != 0."""
    fh.require_node_toolchain()
    lane = _fe_unit_lane()
    assert "taskCompleted" in lane["gateOn"] and "commit" in lane["gateOn"], lane["gateOn"]

    ws = fh.make_workspace(tmp_path / "ws")
    seed = ws / "frontend" / "tests" / "seed.fail.test.ts"
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text(
        'import { expect, it } from "vitest";\n'
        'it("seeded failure", () => {\n  expect(1).toBe(2);\n});\n'
    )

    proc, data = _vitest_json(ws, tmp_path / "seeded.json")
    assert proc.returncode != 0, "seeded failing spec did not turn npm test red\n" + fh.describe(proc)
    assert data is not None, fh.describe(proc)
    assert data["numFailedTests"] == 1, data

    lane_proc = fh.run(lane["command"], cwd=ws, timeout=VITEST_TIMEOUT_S, shell=True)
    assert lane_proc.returncode != 0, (
        f"fe-unit lane command {lane['command']!r} stayed green on a seeded failure\n" + fh.describe(lane_proc)
    )


PROBE = r"""
import { createServer } from "vite";
import { createVitest } from "vitest/node";

const [key, spec] = process.argv.slice(2);

function aliasTarget(config) {
  const entries = Array.isArray(config.resolve.alias)
    ? config.resolve.alias
    : Object.entries(config.resolve.alias).map(([find, replacement]) => ({ find, replacement }));
  const hits = entries.filter((e) => e.find === key);
  return hits.length === 1 ? hits[0].replacement : `<${hits.length} entries for ${key}>`;
}

async function resolveWith(server) {
  const env = server.environments?.client ?? null;
  const container = env ? env.pluginContainer : server.pluginContainer;
  const hit = await container.resolveId(spec, undefined);
  return hit ? hit.id : null;
}

const vite = await createServer({
  configFile: "frontend/vite.config.ts",
  logLevel: "silent",
  server: { middlewareMode: true, hmr: false, ws: false },
});
const viteOut = { target: aliasTarget(vite.config), resolved: await resolveWith(vite) };
await vite.close();

const vitest = await createVitest("test", { config: "frontend/vitest.config.ts", watch: false }, { logLevel: "silent" });
const vitestServer = vitest.vite ?? vitest.getRootProject().vite;
const vitestOut = { target: aliasTarget(vitestServer.config), resolved: await resolveWith(vitestServer) };
await vitest.close();

process.stdout.write("\n@@PROBE@@" + JSON.stringify({ vite: viteOut, vitest: vitestOut }) + "\n");
process.exit(0);
"""


def _probe(ws: Path) -> dict:
    script = ws / "alias-probe.mjs"
    script.write_text(PROBE)
    proc = fh.run(["node", str(script), ALIAS_KEY, ALIAS_PROBE_SPEC], cwd=ws, timeout=PROBE_TIMEOUT_S)
    assert proc.returncode == 0, fh.describe(proc)
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@PROBE@@")]
    assert len(marker) == 1, fh.describe(proc)
    return json.loads(marker[0][len("@@PROBE@@"):])


def _real(p: str | None) -> str | None:
    return None if p is None else str(Path(p).resolve())


def test_alias_shared(tmp_path: Path) -> None:
    """C9.21: Vite and Vitest agree on the alias, and a retarget at its one definition moves both."""
    fh.require_node_toolchain()

    ws = fh.make_workspace(tmp_path / "ws")
    before = _probe(ws)
    want_dir = ws / "frontend" / "src" / "shared"
    for side in ("vite", "vitest"):
        assert _real(before[side]["target"]) == str(want_dir.resolve()), before
        assert _real(before[side]["resolved"]) == str((want_dir / "boot.ts").resolve()), before
    assert before["vite"] == before["vitest"], before

    # Metamorphic companion: move the alias at its single definition only.
    alt = ws / "frontend" / "src" / "shared_alt"
    alt.mkdir()
    (alt / "boot.ts").write_text((want_dir / "boot.ts").read_text())
    tsconfig_path = ws / "tsconfig.json"
    tsconfig = json.loads(tsconfig_path.read_text())
    paths = tsconfig["compilerOptions"]["paths"]
    assert f"{ALIAS_KEY}/*" in paths, paths
    paths[f"{ALIAS_KEY}/*"] = ["frontend/src/shared_alt/*"]
    tsconfig_path.write_text(json.dumps(tsconfig, indent=2) + "\n")

    after = _probe(ws)
    for side in ("vite", "vitest"):
        assert _real(after[side]["target"]) == str(alt.resolve()), after
        assert _real(after[side]["resolved"]) == str((alt / "boot.ts").resolve()), after
