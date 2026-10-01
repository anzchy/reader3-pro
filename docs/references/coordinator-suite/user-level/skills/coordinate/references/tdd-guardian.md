# Checkpoints under tdd-guardian

Use this file only when the bindings' GATE_SOURCE names tdd-guardian. Readiness and workflow rules
are the global *TDD Guardian* rule in `~/.claude/CLAUDE.md`; this file maps them to checkpoints.

| CP | Peer runs, in its worktree | Evidence in the report |
|---|---|---|
| CP0 | `/tdd-guardian:status` | its output: config enabled, lanes runnable |
| CP1 | `:plan`, then `:design-tests`; `tdd-spec-adversary` for a risky unit | the work items and the test matrix |
| CP2 | `:gate` for the commit-gated lanes | the lane results at HEAD |
| CP3 | `:gate` for the push-gated lanes, then `:review`; `:audit-coverage` when the definition site requires it | the lane results at HEAD and the review findings |

- Which lane belongs to which gate comes from the project's tdd-guardian config, read at dispatch
  time. Never from this file.
- Lane state is per worktree and not committed. It is evidence for the peer's own worktree only;
  the coordinator's acceptance still rests on its own re-run at the SHA (`checkpoint-verifier`).
- Freshness is the tool's business. Do not reason from `gateFreshnessMinutes`: verdicts are keyed
  to the SHA and re-run.
