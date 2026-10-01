---
name: coordinate-bindings
description: >-
  Reader3 Pro bindings for the user-level /coordinate skill: where units, lanes, frozen paths,
  locks, allocation, extra standing orders and close-out write-backs are defined in this repo.
  Read by /coordinate from the main checkout while running parallel implementor sessions here.
user-invocable: false
---

# Reader3 Pro: coordinate bindings

<!-- Install at .claude/skills/coordinate-bindings/SKILL.md (checked in). Pointers only: each fact
     lives at the linked site. Per-program facts (dirty files, branch numbers, row assignments)
     go in that program's protocol.md, never here. -->

## DEFINITION_SITES
Load `plan-and-branch-map` first; its "Where documents live" is the authority. Three unit shapes:
- **Migration task file:** `docs/plans/20260816-tech-stack-migration/tasks/<nnn>-*.md`.
- **Frontend WI:** `### WI-N` headings in §4 of
  `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` (no task files).
- **Debt window or standalone plan:** no task file. The unit is its rows in the debt tables, or a
  standalone `docs/plans/*.md` plan. Its milestone-table row names which.

Execution order: the progress dashboard named in `plan-and-branch-map`.

## GATE_SOURCE
- Gate tool: tdd-guardian (core `references/tdd-guardian.md`). Lanes, commands, gates and
  timeouts: `.claude/tdd-guardian/config.json`.
- Supplementary checks (lint, types, size gates, ledger drift): `CLAUDE.md` "Tests and Checks".
- Build each brief's VERIFY from those two files at dispatch time. Per-worktree setup before the
  first lane: `uv sync`, `npm ci`.

## FROZEN_SOURCE
- Definition: `docs/plans/20260816-tech-stack-migration/tasks/soak-log.md`, header and its
  "`suite_hash` 的取法" section.
- Second key: `HASH_COVERED_PATHS` in `scripts/soak_run.py` (must match; never edit one alone).
- Any byte changed there changes `suite_hash`. `protocol.md` names at most one owner per program;
  every other unit gets an empty-diff check at CP2 and CP3.

## LOCKS
- **E2E lane.** `scripts/e2e_lock.py`, an fcntl wrapper that the e2e lane `command` in
  `.claude/tdd-guardian/config.json` points at (core `references/shared-lock.md`, preferred form).
  **Built** (021, PR #32, `e3dde84`). Lock file `~/.cache/reader3-e2e.flock` (override:
  `READER3_E2E_LOCK`); the kernel releases it when the run ends, so no session ever needs `rm`.
  `scripts/e2e_lock.py status` prints `FREE` (rc 0) or `HELD <owner>` (rc 1). A held lock makes the
  lane exit 75 (`BUSY <owner>`): an environment failure, never a code verdict. Re-run when free.
  Under `GITHUB_ACTIONS` it runs unlocked.
- The old mkdir lock (`~/.cache/reader3-e2e.lock`, a directory) is retired. A branch based before
  `e3dde84` still uses it until it rebases. Its release may be denied by a peer's permissions; a
  denial goes to the user.

## ALLOCATION
`plan-and-branch-map` "Branch naming" (numbers come only from §9 of the migration plan).

## EXTRA_ORDERS
Appended to the core defaults:
1. Never run `ruff format` (`CLAUDE.md` "Tests and Checks").
2. Load `plan-and-branch-map` before touching `docs/plans/`.
3. Never run `scripts/soak_run.py --append` from a unit branch. Soak rules: §7 of
   `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md`.

## CLOSEOUT
- [ ] Milestone table and dashboard: `plan-and-branch-map` (status semantics are defined there).
- [ ] Feature ledger: `CLAUDE.md` "Feature Ledger".
- [ ] Debt tables in `tasks/009-e2e-annotations.md` and `tasks/017-audit-followup.md`: close paid
      rows; add new debts with owner and location.
- [ ] Soak log: only as §7's soak rules allow.

## Known conflict points (seed the conflict map)
- **Debt-table rows** are assigned per unit in `protocol.md`. Example: 018 and 019 both edit rows
  of the 009 table.
- **Count constants** in `scripts/lint_e2e_groups.py` and `tests/unit/test_e2e_group_guard.py`:
  the branch that merges second rebases and recounts.
- **Milestone table and dashboard** are written ONLY by the coordinator, at four moments:
  allocation, first accepted CP (🚧 "branch exists with commits"), merge (✅) and close. Units own
  only their task file's status line and their assigned debt rows.
- **Coordinator commits on `master`** use pathspec only (`git commit -- <paths>`): the main
  checkout may hold the user's uncommitted edits.
