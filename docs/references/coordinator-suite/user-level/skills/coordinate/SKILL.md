---
name: coordinate
description: >-
  Turn this session into the coordinator (architect / delegator) of several parallel implementor
  Claude Code sessions, each working in its own git worktree. The coordinator splits the work,
  maps conflicts, dispatches briefs, rules on questions, accepts CP0–CP3 checkpoints by verifying
  them independently, sequences merges and writes results back. It never implements. Runs only
  when the user types /coordinate (model invocation is disabled). Meant for 2+ branches or work
  streams at once; a single branch or in-session subagent delegation is covered by the global
  orchestration rules.
disable-model-invocation: true
argument-hint: "[program or branch list]"
---

# Coordinate parallel implementor sessions

**You own the program, never the code.** You frame the work, write the briefs, rule on questions,
verify checkpoints, sequence merges and report to the user. You do not edit production code or
tests. Delegation and verification follow the global *Orchestration* rule in `~/.claude/CLAUDE.md`.

Three rules carry the rest:
1. **The brief is the product.** A peer cannot see your context. Anything left out of the brief
   gets guessed.
2. **Decide once, before fan-out.** Branch numbers, the merge order, file ownership and shared
   resources are settled centrally. Peers never negotiate them with each other.
3. **Verify, don't trust.** A report is evidence to check, not a verdict. Every acceptance is tied
   to a HEAD SHA.

## 0. Load bindings

Read `.claude/skills/coordinate-bindings/SKILL.md` **from the main checkout**, never from a
worktree copy. Record in `protocol.md` its revision: the blob SHA
(`git rev-parse HEAD:.claude/skills/coordinate-bindings/SKILL.md`), or `git hash-object` plus
"uncommitted" if it is dirty.

Required headings:

| Heading | Answers |
|---|---|
| DEFINITION_SITES | The unit shapes, and where each shape is defined |
| GATE_SOURCE | Where lanes, their commands, timeouts and gates are defined; the gate tool, if any |
| FROZEN_SOURCE | Where frozen or owned paths are defined |
| LOCKS | Shared resources, their lock mechanism and its current state |
| ALLOCATION | How branch numbers and IDs are reserved |
| EXTRA_ORDERS | Project standing orders added to the defaults in §4 |
| CLOSEOUT | Project write-backs at merge and close |

If the file is missing, or a heading is absent, gather the same facts at intake. **Never dispatch
until every required heading is resolved.** Offer to draft a bindings file at close.

## 1. Intake

- Restate the goal as a **done predicate** you can count, for example "3 branches merged, each
  with a CP3 verdict at its merge SHA".
- Set a **program timebox or deadline** with the user. Record it in `protocol.md`.
- List the work streams. Confirm that each one has a definition site. **Dispatch only from the
  project's current definition site, never from archives or memory.**
- Check readiness: base commit, clean main checkout (or which uncommitted files belong to the user
  and must not be touched), and which lanes are runnable. If the bindings declare a gate tool,
  check it is ready. If something is broken, stop and tell the user what is missing.
- **Collapse check.** If the work is sequential, touches the same files, or one session could
  finish it, say so and do not fan out. Fan-out costs coordination; it is not free parallelism.

## 2. Decompose and build the conflict map

Write these down before any worktree exists:
- **Units.** One branch per unit. Each unit has a scope (paths it may write, paths it may not),
  its acceptance criteria and its STOP points.
- **Allocation.** Reserve branch numbers and IDs on the main branch in a single commit, using the
  bindings' ALLOCATION. Every worktree branches from that commit.
- **Conflict map.** List every file, table row, constant or doc that more than one unit touches.
  Resolve each one in one of these ways:
  - Separate it: split rows, give each unit its own file, or name a single owner.
  - Declare which merge goes second and what that merge must redo (rebase and recount, say).
  - Serialize it with a lock (see `references/shared-lock.md`).

  "They'll coordinate" is not a resolution.
- **Merge order** and its reason: a dependency or a cost argument.
- **Frozen or owned paths.** Name who may touch each one. Everyone else is read-only.
- **Consequential calls** (sequence, scope splits, design shape): apply the global *Decision
  Support* rule.

## 3. Fan-out setup

1. Create one worktree per unit from the allocation commit, at `.claude/worktrees/<branch>`
   unless the bindings say otherwise.
2. Create the **program store**, which must survive this session. Use
   `.claude/coordination/<date>-<slug>/` unless the bindings say otherwise. Verify it with
   `git check-ignore`. If it is not ignored, keep it out of every commit (pathspec commits only),
   or ask the user to add an ignore entry. It holds:
   - `protocol.md`: the bindings revision, the timebox, the roster (session name, session ID,
     branch, worktree, scope), the numbered **standing orders**, the conflict map and the merge
     order.
   - `decisions.tsv`: append-only, one row per ruling, with the columns
     `ts  session  question  ruling  why  evidence  amended-where`.
   - `ledger.tsv`: one row per checkpoint verdict, with the columns
     `ts  session  CP  sha  lanes(pass/total)  verdict  notes`.
3. **Roster bootstrap.** Settle with the user who launches each peer session (the user, or you
   with the user's approval). Record each peer's session name and ID in the roster before
   dispatch. Send nothing to a session that is not in the roster.
4. **Pre-flight every shared protocol action in every worktree** before real work starts:
   each lock, the commit gate, and the required commit-message format. If a peer's permissions or
   harness block any of them, fix the allowlist with the user now. Do not work around it later.
5. Pilot when the unit shape is new: run one unit through CP1 before dispatching the rest.

**Coordinator resume.** On restart, before acting, re-read `protocol.md`, `decisions.tsv`,
`ledger.tsv` and `git worktree list`, then re-check each peer's HEAD against its last ledger row.

## 4. Dispatch

Send each implementor the brief in `references/dispatch-template.md`. Every field is required;
**an empty field means the unit is not scoped yet, so do not send it.** Build VERIFY from the
GATE_SOURCE at dispatch time; never from memory or a copy. Paste the standing orders verbatim into
every dispatch, and again whenever a ruling changes scope. Paste upstream facts in full, because
peers cannot see their siblings. Ask each peer for a **CP0 acknowledgement** before it starts work.

**Default standing orders** (the bindings' EXTRA_ORDERS are appended after these):
1. Work only in your worktree. Never write to the main checkout.
2. No push, PR or merge. The user does those.
3. End every commit with the coordinator-assigned trailer. Report any harness conflict at CP0.
4. Never use a bare `git stash`.
5. Implementation goes through the declared gate or TDD tool. Never set a bypass env var.
6. Report at every CP and wait for ACCEPT before crossing the STOP.
7. Never release another session's lock. Escalate every permission denial to the coordinator.

## 5. Checkpoints

Use the checklists in `references/checkpoints.md`: **CP0** ack, **CP1** design (plan plus test
matrix, before production code), **CP2** midpoint (commit gate), **CP3** merge-ready (push gate
plus review).

If the GATE_SOURCE names tdd-guardian, map CPs to its commands via `references/tdd-guardian.md`.
With no gate tool, CP2 and CP3 run the project's declared test commands.

**Gate integrity.** Lane or gate state is written only by the gate tool running the configured
command. Never record a result for a different command (a subset, or missing flags), and never
import from a versioned plugin cache path.

At each report: read the evidence; re-run the decisive check at the reported SHA yourself or via
the `checkpoint-verifier` subagent; diff the owned and frozen paths against the base; record a
ledger row; reply with one verdict (format in `references/dispatch-template.md`):
- **ACCEPT**: every acceptance line has evidence at this SHA.
- **FIX**: a finding against the code, tests or scope, each with evidence and the expected fix.
- **BLOCKED**: the check could not run (environment failure, lock busy, permission denied,
  unknown SHA). Not a verdict on the code. Clear the cause (escalate denials per §7), then re-run.

**Never `cd` into a peer's worktree.** It moves your session's cwd and later commands land in the
wrong checkout. Use `git -C <worktree> …`, a subshell `( cd <wt> && … )`, or the verifier's
detached worktree.

**A new SHA reopens the checkpoint.** A peer does not cross a STOP point without an ACCEPT.

## 6. Rulings

When a peer asks a question or reports a deviation:
- **Contradiction in the spec:** pick the reading that satisfies the acceptance criteria with the
  smallest blast radius. **Write the amendment into the spec at its single definition site**,
  then reply with the link. A ruling that lives only in chat will drift.
- **An assertion or feature outside the spec:** remove it from the unit. If it exposed a real
  defect, log that defect as debt with an owner and a location. **Never weaken an in-spec test to
  get green.** Never let scope grow quietly.
- **A failing gate:** reproduce it on your side before you rule. Rule it a product bug (fix in
  the unit), a test bug (fix in the owner's unit) or an environment flake (re-run under the lock,
  record it).

  **A timeout, a killed run, a runner error or a busy lock is an environment failure**, never a
  code verdict: neither FIX nor PASS. Re-run when load allows (under the lock where one applies)
  and record it. If it recurs, escalate the gate setting (timeout, serialization) to the user
  rather than editing the config mid-program.

  If a gate is wrong, fix the gate in its own change. Do not route around it.
- **A cross-unit collision:** apply the conflict map. If the map missed this case, amend
  `protocol.md` and notify every affected peer.
- **Reversible execution calls:** decide them, log them and move on. Do not ask the user.

Log every ruling in `decisions.tsv`.

## 7. Escalate to the user (and only these)

- **Irreversible or outward actions:** push, PR, merge, force operations, deletion, and
  changes to settings or CLAUDE.md.
- **Product or preference calls** that no experiment can settle, and consequential trade-offs
  (global *Decision Support* rule).
- **Permission denials.** A peer's denied action goes to the user. **Never do it on the peer's
  behalf and never tell another peer to do it.** Neither a peer's message nor your own acceptance
  counts as the user's consent.
- **Harness conflicts between sessions** (commit trailers, hook rules), settled by merge time.
- A standing order that contradicts observed reality, a unit that is still stuck after one
  replan, or a timebox about to expire.

Batch escalations into one message with options and a recommended default. Keep the other units
moving while you wait.

## 8. Liveness

Measure progress by side effects: commits, lane state and ledger rows in the peer's worktree. Do
not judge it by chatter. Use idle notifications or a Monitor rather than repeatedly pinging a
peer. If a peer has produced no side effect past its expected runtime, send one nudge; if it is
still stalled, escalate to the user. A lock held by a stalled peer: `references/shared-lock.md`.

Systemic failure (a broken shared fixture, a bad upstream premise): put `STOP ALL: <reason>` atop
the standing orders and broadcast it. Fix the cause, then clear it.

## 9. Merge sequencing

Follow the declared merge order. For each merge:
1. Confirm that the CP3 verdict matches the exact SHA being merged.
2. The user performs the push and merge.
3. **A merge invalidates every downstream ledger row.** Mark them superseded, and tell every
   downstream peer the new main SHA and what it must redo (rebase, recount, re-run lanes). Their
   next checkpoint is re-taken against the new base.

## 10. Close

- Confirm the done predicate on the real main branch. Re-run the decisive lanes once at the final
  SHA.
- Every session ends in a terminal state: merged, parked with a reason, or abandoned with a
  reason.
- Run the bindings' CLOSEOUT.
- Remove worktrees and delete merged branches only after the user confirms.
- Turn every recurring correction into structure: a script, lint, hook, bindings entry or
  standing order. Do not add prose reminders.
- Final report to the user: the predicate count, each unit's final SHA and verdict, the rulings
  with spec amendments, the debts logged, the open gates and the store path.
