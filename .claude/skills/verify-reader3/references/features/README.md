# Feature Map

One file per ledger row (`docs/feature-ledger.md`, `F-NNN`), saying how to prove that row's
Confirm step in the running app with control.py and `$B`. Read the row's file before you
start; [`../../SKILL.md`](../../SKILL.md) has the stages, helpers and general gotchas.

| File | Ledger row | Status |
|---|---|---|
| [F-009.md](F-009.md) | Paginated epub.js reader | accepted |
| [F-011.md](F-011.md) | Keyword search | accepted |
| [F-013.md](F-013.md) | AI Q&A + summary | accepted |
| [F-018.md](F-018.md) | Annotations + notes | partial |
| [F-020.md](F-020.md) | Settings page + API | accepted |

Rows without a file are not mapped yet. Rows whose ledger status is `absent` never get one.

## The four-H2 rule

Every map file is named `F-NNN.md` and:

1. starts with an H1 whose first word is its id, e.g. `# F-018 Annotations + notes`;
2. links its ledger row as `[F-NNN](../../../../../docs/feature-ledger.md)`, and that is the
   first link to the ledger in the file;
3. has exactly these four H2 sections, in this order, and no others:
   - `Sub-features`: the row's claims, one bullet each, paraphrased from the ledger;
   - `How to get to it (user POV)`: the clicks a user makes, from the library page;
   - `Driving it with control.py and $B`: the commands, each control.py line on one line
     (no `\` continuations), using only flags that exist;
   - `Gotchas`: where the ledger Confirm text and the sandbox disagree, and what to do.

Every file must also be listed in this README. After any edit, run:

```bash
python3 .claude/skills/verify-reader3/scripts/control.py map check
```

It fails (`map_invalid`) on a malformed file and on any quoted control.py line that the
real parser rejects (`dead_commands`).

## Debts

Open findings from the 2026-10-03 TDD review of branch 025 (`.claude/tdd-guardian/review-20261003-final.md`),
deferred on purpose. Line numbers are as of the commit that added this table.

| Id | What | Where | Why deferred |
|---|---|---|---|
| M1 | Every red receipt carries `implementation-already-present`: at WI-1's red, 24 non-test files (control.py, the `verify_control` modules, the deleted shell scripts) were already modified, so each red partly ran against existing code. Weaker red evidence, not broken separation. | `.claude/tdd-guardian/receipts.json` (first at :3394; 8 occurrences) | Historical: the receipts record what happened and cannot be re-taken after green. Re-recording would forge them. Only a fresh red on new work fixes it. |
| M2 | The configured coverage gate does not measure this code: the unit lane runs `--cov=src/reader3_app`, nothing under `scripts/verify_control/` is counted, and most cases reach it only through a subprocess. | `.claude/tdd-guardian/config.json:15` (unit lane `command`); the verify-control lane has `coverage: "none"` | Needs subprocess-aware coverage (`coverage run` in the children plus a combine step) and a threshold decision. A one-off subprocess-aware audit measured 91.88% lines / 87.98% branches (`coverage-20261003-audit.md`), so nothing urgent is hidden. |
| L5 | `paths.browse_path` resolves the default browse binary with `os.path.expanduser` (reads the process's `HOME`), `browse.locate` with `env["HOME"]` from the env it is given. They disagree when `HOME` is overridden in that env. | `scripts/verify_control/paths.py:170-174` vs `scripts/verify_control/browse.py:62-67` | Known drift with no live symptom: every caller (`browse.run`, `evidence.py:211`, `instance_doctor.py:99`) passes `os.environ`, so both read the same `HOME` in practice. Fixing it means picking one rule and re-pinning the tests that set `HOME`. |
| L7 | `STUB_ROWS = []` leaves WI1-C13 with no parameters (collected as skipped) and makes WI1-C10's loop over stub rows do nothing; only its trailing `up --bogus` row runs. | `tests/unit/test_verify_control_core.py:380-381` (C10 at :385, C13 at :471) | The rows were scaffolding: each WI deleted its own once its command existed, so empty is the finished state. Deleting C13 or rewriting C10 changes recorded specifications and needs its own ruling. |
