---
name: audit-findings-triage
description: >-
  How to re-verify and then triage a code-audit findings list (usually produced by Codex via
  /cc-suite:audit) into Must fix / Should fix / Could fix / Won't fix. Load this whenever you are
  handed audit findings and asked what to fix, how to prioritise them, whether the severities are
  right, or to apply MoSCoW to them — and before running /cc-suite:audit-fix or opening a fix
  branch off an audit. Also load when asked "这些 findings 哪些必须修", "severity 准不准", or
  "筛出 must fix".
---

# Auditing the audit: verify severity first, classify second

An audit hands you an external model's *claims*. The severity column is that model's opinion,
formed without running the suite, without the plan folders, and without knowing which files are
frozen. Two jobs follow, in this order, and the second is worthless without the first:

1. **Re-verify.** Decide what is actually true, and what the true blast radius is.
2. **Classify.** Decide what this round of work will fix.

Do not fix anything while triaging. Triage produces a list; fixing is a separate branch that goes
through `/tdd-guardian:workflow`.

## Input

The findings file written by `/cc-suite:audit`: `.cc-suite/audits/audit-{timestamp}-findings.md`.
If the audit only printed findings inline, write the file first — triage output has to land
somewhere durable, and a long session will compact away an inline table.

## Step 1 — Re-verify each finding

Severity as reported is a hypothesis. Assign every finding one of four verification tags, and
write the tag plus the evidence into the finding's `Finding` cell as a leading `[...]` note:

| Tag | What it took to earn it |
|---|---|
| `verified` | Reproduced, or the exact code path read end to end and the claim holds literally. Name the command or the line numbers. |
| `plausible` | The code path supports it, but the triggering condition was not produced. Say which condition is missing. |
| `disputed` | The code behaves as reported, but the behaviour is intended. Cite the ADR, docstring, or design note that says so. |
| `false` | The claim does not hold against the code. Say what the auditor misread. |

**Verify in this order, and stop early only when the cheap check settles it:**

- Every `Critical` and `High`.
- Every `Medium` that claims a *product* defect (not a test-quality defect).
- Any finding whose fix would touch the frozen set, because that fix is expensive enough that a
  wrong premise must be caught before it is scheduled.
- Test-quality findings that claim "this test passes on a broken implementation" are cheap to
  check: mutate the implementation in memory and run the one test. Do it rather than guessing.

**Then adjust the severity**, and say in the row that you did:

- **Down** when the defect needs conditions that do not occur in normal single-process use — a
  second worker, a concurrent CLI writer, a third simultaneous edit.
- **Down** when it predates the audited change and the audited change neither introduced nor
  worsened it — unless the new work's correctness now *depends* on it, in which case it keeps its
  severity and gets said so explicitly.
- **Up** when it makes a guarantee the audited branch itself advertises come out false. That is
  the one thing the external model cannot weigh, because it never read the plan.

Duplicates across audit batches merge into one row; record which batches reported it.

## Step 2 — Name the timebox before classifying

MoSCoW answers "what must be in *this* release". With no release named, everything drifts to
Must. So first state what the container is: which branch the fixes land on, and roughly how large
it may get.

If the fixes need a new branch, its number comes from §9 of
`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` and nowhere else — load
`plan-and-branch-map` first. If the audited PR is already merged, fixes never go back onto the
merged branch; they go on a new one off `master`.

## Step 3 — Classify on three axes

Never classify on severity alone. For each finding answer:

- **A. Reachable?** Does normal single-process use trigger it, or does it need an unusual
  deployment or an unlikely interleaving?
- **B. Does it falsify a claim?** Does it make something this branch, its task file, or its tests
  assert to be true actually false? A test that passes on a broken implementation falsifies a
  claim just as much as a product bug does — the claim is "this behaviour is now guarded".
- **C. What does the fix cost?** Specifically: does it touch the frozen set
  (`tests/e2e/baseline_1b/**`, `tests/e2e/conftest.py`, `helpers.py`, `test_harness_smoke.py`,
  `tests/fixtures/{epub_corpus,epub_zip,ai_stub}.py`, `tests/conftest.py`)? Any byte there changes
  `suite_hash`, so no passed soak batch covers the suite any more: a fresh 10-run batch and a re-run
  of mechanism gate item 3 (random collection order) are needed before 012 can start (batch rule,
  `plan-tech-stack-migration.md` §7; 012 gate F). Since 2026-09-28 that is ~10–15 min, not weeks —
  still a real cost, not a reset of accumulated progress. See `tasks/soak-log.md` for the current
  value and batch status.

Then:

| Bucket | Rule |
|---|---|
| **Must** | `verified` **and** (reachable in normal use **or** falsifies a claim the branch makes). Plus anything that breaks a lane, a standalone collection, or an entrypoint — those block the next branch's work. |
| **Should** | Real but conditional: needs a rare interleaving or a second process; flaky or hang-prone tests; tests that guard this branch's own claims but pass on a broken implementation; explicit rule violations (AGENTS.md exemptions, the documentation-update rule). |
| **Could** | Lint/scanner precision, coverage gaps with no known live defect behind them, unused imports, comments and docs that contradict the code. Cheap, and nothing breaks if they wait. |
| **Won't (this round)** | Any fix that requires editing the frozen set; anything `disputed` or `false`. Both need an explicit written reason — this is the bucket that gets abused. |

### Conditional Must

A finding that would clearly be Must if true, but is only `plausible`, enters as
**"Must, pending repro"**. Its first work item is the reproduction, and the result promotes it to
Must or demotes it to Should. Do not let an unreproduced claim sit in Must silently; do not demote
it just because reproducing it is work.

### Won't-fix leaves a receipt

When a real defect goes to Won't because the fix would touch the frozen set, say what covers it
instead — usually a new test in an unfrozen module, folded into some Must item's fix. "We are not
fixing it and nothing watches it" is a different, much worse answer, and must be stated as such
rather than blurred into the first one.

### Do not shrink the list to fit

If Must + Should is larger than the timebox, report the size and say so. Scaling down is the
user's decision, not yours. Silently pushing items to Could to make the branch look tractable
destroys the only signal the audit produced.

## Step 4 — Persist and report

Add a `Triage` column to the findings table holding `must` | `must-pending-repro` | `should` |
`could` | `wont`. Leave the existing `Status` column alone — `Status` tracks whether a fix
happened, `Triage` tracks whether one was scheduled; collapsing them loses the distinction between
"we decided not to" and "we have not got to it".

Report to the user:

1. Whether MoSCoW fits here, and the two rules it needs (timebox, three axes) — do not present the
   classification as if severity alone produced it.
2. Counts per bucket, and the total, so they add up to the findings count.
3. Must and Should in full, each with the one-line reason it is there.
4. Could summarised by kind, not enumerated.
5. Won't itemised with its reason each — this is the list they most need to disagree with.
6. Any severity you changed in step 1, with the evidence.
7. The size of Must + Should, and what opening the fix branch would need (branch number, and
   whether the audited PR is already merged).

## Rules

1. Verification precedes classification. A bucket assigned to an unverified High is guesswork
   wearing a process.
2. Never put a frozen-set edit in Must. Escalate the trade-off to the user instead.
3. Never mark `disputed` without citing the thing that documents the intent.
4. Triage writes to the findings file only. No source or test files change.
5. The external auditor can be wrong, and saying so is part of the job — but so is saying when it
   was right about something the repo's own tests missed.
