---
name: plan-and-branch-map
description: >-
  Where Reader3 Pro's planning documents live, which branch number to allocate next, and the
  authoritative milestone/branch status table. Load this BEFORE opening a new branch, allocating
  a branch number, writing or editing anything under docs/plans/ or docs/adr/, deciding which
  milestone to work on next, or reading anything under specs/. Also load when asked "what should
  I work on next", "which branch is this", or anything about ADRs vs plans.
---

# Reader3 Pro — planning documents and branch map

**The spec-kit framework is no longer used.** `.specify/` and the `/speckit.*` commands were
removed on 2026-08-16. Do not attempt to invoke them.

<example>
user: "I want to fix the F-018 Marker-then-Add-Note bug. Which branch number do I use?"
assistant: "Numbers come only from §9 of `plan-tech-stack-migration.md`, so I'll check whether it
already allocates one there. If not, I'll add the row in §9 first, mirror it in the milestone
table below, and take the slot that `20260824-frontend-backend-plan-progress.md` gives it in the
execution order — I won't name a number that isn't in §9."
<commentary>
A branch-number question: the answer comes from the one allocation site, never from guessing
the next integer.
</commentary>
</example>

### Where documents live

| Directory | Contents | Lifecycle |
|---|---|---|
| `docs/plans/{date}-{topic}/` | One self-contained body of planning work: plans, specs, contracts, review records, per-branch task lists | Living until the work ships |
| `docs/plans/*.md` | Standalone plans that aren't part of a larger effort | Living |
| `docs/adr/` | Architecture decision records — the **why** behind long-lived constraints, one file per decision ([index](docs/adr/README.md), admission rule in [ADR-0000](docs/adr/0000-use-adrs.md)) | **Survives** the archival of `docs/plans/`; never edited after Accepted, only superseded |
| `specs/_archive/` | Historical spec-kit records for shipped features | **Frozen. Code is authoritative. Never implement from here.** |
| `designs/` | Design references and executable prototypes | Living |

**ADRs are not plans.** A plan compares options and tracks execution; an ADR records the outcome that must outlive the plan. When an ADR becomes the sole definition site of a rule, the plan section it came from keeps its heading and becomes a one-line link (「搬，不抄」). Read the Accepted ADRs before touching a data model, a public interface, or anything that crosses modules; to go against one, write a superseding ADR first.

**A planning effort is one folder.** Everything a plan needs to be read and executed —
the plan itself, its design spec, its interface contracts, its review record, and its work
items — lives together under one dated folder. Don't scatter these across `docs/`, `specs/`,
and `docs/contracts/`; a reader who opens the folder should need nothing outside it except
the code and `designs/`.

**Two folders may split one effort, but never one fact.** When an effort is large enough to
split (as the 007–015 work is), each folder carries a 「权威范围」 table naming the facts it
defines. The tables must not overlap, and every other mention of a fact links to its one
definition instead of restating it — restating is how the two copies drift apart.

There are two active efforts today, and they are two halves of one program:

| Folder | Half | Branches |
|---|---|---|
| [`docs/plans/20260816-tech-stack-migration/`](docs/plans/20260816-tech-stack-migration/README.md) | Backend layering, storage format, test net + CI, **branch numbering** | 007, 008, 009, 011, 012, 015 (CLI); debt-payment branches 016, 017, 018, 019 (the 2026-09-30 frozen-set debt window) |
| [`docs/plans/20260817-frontend-ui-refactor/`](docs/plans/20260817-frontend-ui-refactor/README.md) | Design system, degradation states, `annotations.js` split, frontend TDD matrix | 010, 013, 014, 015 (PWA) |

**Which branch to open next** is a third fact, owned by neither folder:
[`docs/plans/20260824-frontend-backend-plan-progress.md`](docs/plans/20260824-frontend-backend-plan-progress.md)
is the progress dashboard and **the sole definition site for the execution order**. The two plan
folders define *dependencies* (who waits on whom); that file defines *sequence* (who goes first) —
the dependency graph permits more than one legal order and they do not cost the same. Its status column
mirrors the milestone table below; when they disagree, the table below wins.

Start at either `README.md`. Each folder holds **exactly one plan document** —
`plan-tech-stack-migration.md` and `plan-frontend-ui-refactor.md` respectively. (The migration
folder used to carry a second plan, `plan-ui-migration-sequencing.md`; it was merged into
`plan-tech-stack-migration.md` on 2026-08-17 with its section numbers preserved, and deleted.)
The frontend folder has **no `tasks/` directory** — its work items are `### WI-N:` headings
inside `plan-frontend-ui-refactor.md` so that `/tdd-guardian:workflow` can consume them directly.

`specs/` now contains only `_archive/`. It holds 171 unchecked `- [ ]` items that all describe
already-shipped or abandoned work. See [`specs/_archive/README.md`](specs/_archive/README.md)
before reading anything in there — `003-add-book-notes` in particular describes an annotation
system that was never built that way (the shipped one came from `006-hot-fix`).

### Branch naming

`{number}-{short-name}`. **Numbers are allocated in one place only**: §9 of
[`plan-tech-stack-migration.md`](docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md).
Do not invent a new number without updating that table.

| Milestone | Branch | Plan folder | Status |
|---|---|---|---|
| M0 — Phase 0 contracts + hygiene | `007-hygiene-and-contracts` | migration | ✅ Merged (PR #18) |
| M1 — tests + CI + API freeze | `008-test-safety-net` | migration | ✅ Merged (PR #19) |
| M1b — Playwright E2E | `009-e2e-annotations` | migration | ✅ Merged (PR #20) |
| M1b-债 — settings apply order | `016-settings-apply-order` | migration | ✅ Merged (PR #21) |
| MD — design degradation states | `010-design-degradation-states` | **frontend** | ✅ Merged (PR #24) **— merged 2026-09-24, merge commit `671f580` (branch tip `4fb33c9`: all nine exit gates green after rulings D-2 / D-5 / D-6 / D-8). Work items are WI-1 – WI-8 in the frontend plan.** |
| M2 — backend refactor | `011-backend-refactor` | migration | ✅ Merged (PR #22) **— merged 2026-09-22 with 9 ✅ ＋ 1 ⚠️: gate #7 was partial, its blocking formally revoked rather than passed. CI on `4af73cc` was green (tests 35733667011, lint 35733681164), which retired the earlier "green only on the local profile" qualifier.** |
| M2-债 — audit follow-up | `017-audit-followup` | migration | ✅ Merged (PR #23) **— merged 2026-09-23, merge commit `6df5026`. The 22 must/should findings from the post-merge audit of PR #22. Three lanes re-run green on the merge head before merging. This does NOT retire 011's ⚠️: that gate is #7 (bench C1), whose remaining half is debt #35 and lands in 012.** |
| M4a-债 — library routes not tied to the new format | `018-library-routes` | migration | ✅ Merged (PR #33 + PR #37) **— first slice WI-1 – WI-3 merged 2026-10-01 as PR #33, merge commit `c08317b` (branch tip `42c0728`): debt-owner rewrite, the per-book write lock (ADR-0015, Accepted 2026-10-02), and #51 settings revision check. Second slice WI-4 – WI-8 merged 2026-10-07 as PR #37, merge commit `74384b1` (branch tip `b6025ba`): #56 list route, #58 delete (ADR-0018 Accepted), #53 export, #31 CI reconciliation, `--append` hard block; paid 009 #53 / #56 / #58, opened 009 #72 (owner 014) / #73. Ledger F-035 / F-036 accepted (live-passed). Merge facts for both slices live in `tasks/018-library-routes.md` §8. Scope ruling D1 lives in `tasks/012-storage-format.md` §6.** |
| M1b/M2-债 — frozen-set debt window | `019-frozen-set-debts` | migration | ✅ Merged (PR #29) **— merged 2026-10-01, merge commit `eda9694` (branch tip `d31f53d`). Paid 009 #49 (partly) / #50 / #62 and 017 finding #10; opened 009 #65–#68. No task file — payments are recorded in the 009 / 017 debt tables. Changed `suite_hash` (value in `soak-log.md`); the 012 pre-start batch covers it.** |
| ⟂ — debug-state getter | `020-debug-state` | standalone plan `docs/plans/20260928-debug-state-getter.md` | ✅ Merged (PR #30) **— merged 2026-10-01, merge commit `40e807d` (branch tip `7fc0dbf`). `Reader3Epub.getDebugState()` read-only state surface; opened 009 #63 (owner 014 WI-19). No frozen-set change.** |
| ⟂ — E2E lock as an fcntl wrapper | `021-e2e-lock` | migration (§9 row; no task file) | ✅ Merged (PR #32) **— merged 2026-10-01, merge commit `e3dde84` (branch tip `f9b3d1f`). The e2e lane `command` now runs through `scripts/e2e_lock.py` (fcntl lock on `~/.cache/reader3-e2e.flock`, kernel-released on exit; BUSY exits 75; bypassed under `GITHUB_ACTIONS`). Retires the hand-managed mkdir lock. No frozen-set change.** |
| ⟂ — feature-ledger Summary Evidence validation | `022-ledger-evidence` | migration (§9 row; no task file) | ✅ Merged (PR #31) **— merged 2026-10-01, merge commit `ebf4ad7` (branch tip `7ce1bed`). `build_feature_ledger.py --check` now validates the Summary `Evidence` cell against Rule 7 (form only, not existence); rows F-001 / F-004 / F-012 / F-015 / F-019 / F-029 corrected with verified evidence. No frozen-set change.** |
| M1b-债 — frozen-set prep before the 012 start check | `023-frozen-set-prep` | migration (§9 row; no task file — payments in the 009 debt table #65–#68) | ✅ Merged (PR #34) **— merged 2026-10-02, merge commit `cc8ad27` (branch tip `b75d1a5`), after 018. Paid 009 #65 / #66 / #67 and the High half of #68. Changed `suite_hash` on purpose (value in `soak-log.md`); the 012 start check batch covers it.** |
| ⟂ — 012 Q2 commit-mechanism prototype | `024-q2-commit-prototype` | migration (§9 row; no task file) | ✅ Merged (PR #35) **— merged 2026-10-02, merge commit `94dd1e0` (branch tip `15df015`). Artifacts only under `tasks/evidence/q2-commit-prototype/`; no `src/` change. The maintainer ruled B (generation directory + single pointer); the superseding ADR is ADR-0016 (Proposed, flips with 012).** |
| ⟂ — verify-reader3 control CLI + Feature Map | `025-verify-control` | migration (§9 row; no task file) | ✅ Merged (PR #36) **— merged 2026-10-06, merge commit `55da172` (branch tip `b133ea1`). `control.py` (stdlib only, one JSON envelope per command) replaces the three shell scripts of the `verify-reader3` skill; a per-`F-NNN` Feature Map lives under its `references/features/` (F-009 / F-011 / F-013 / F-018 / F-020 live-passed). Ledger row F-018 and audit entries 2026-10-03 / 2026-10-04; opened 009 #70 (owner 014) and #71 (next AI-related branch). Lane split: `verify_control_live` marker, new commit-gated `verify-control` lane. No `src/` change, no frozen-set change.** |
| M3 — storage migration | `012-storage-format` | migration | Tasks drafted **(review complete: D1 and Q1–Q13 all ruled, 2026-10-02 (§6); branch not opened. Before it opens: the 012 start check in §7 of `plan-tech-stack-migration.md` ("012 开工核验"); entry conditions in `tasks/012-storage-format.md` §1. The open question whether 012 may open before 018 WI-4 – WI-8 merge is moot: 018 merged in full 2026-10-07 (PR #37, `74384b1`), so 018's #56 route that 012 WI-5 / WI-10 build on is on `master`.) Keeps #35 / #54 / #55 and, as its last wave, #57 and #52.** |
| M4a — TS shell + settings + library | `013-ts-frontend-shell` | **frontend** | ✅ Merged (PR #25) **— merged 2026-09-26, merge commit `1ec5ff7`. Work items WI-9 – WI-13 plus the Track D implementation items; the reader-side and backend-dependent halves are pinned to 014 (WI-16 / WI-16b) and 012 debts #51–#58 (#51 / #53 / #56 / #58 re-assigned to 018 on 2026-09-26).** |
| M4b — TS reader | `014-ts-frontend-reader` | **frontend** | WI-14 – WI-19 (incl. inserted WI-16b, library-side deferred acceptance) |
| M5 — launch + PWA | `015-launch-experience` | migration (CLI) ＋ **frontend** (PWA) | ~~Allocated~~ Tasks drafted (CLI half) / WI-20 **— ⬛ 2026-10-02: `tasks/015-launch-experience.md` written for the CLI half; review complete, §6 fully ruled (Q16 is owned by WI-20, not ruled there); branch not opened. Its data-home rule is ADR-0017 (Proposed, flips to Accepted when the CLI half merges). Entry condition: 014 merged (§1 of the task file). The PWA half is unchanged: WI-20 in the frontend plan.** |

"✅ Merged" means the branch is on `master` and its phase is closed; the merge facts (PR, merge
commit, CI run) are defined in that branch's task file, not here. "🔨 Done on branch, not merged"
means every exit gate in that branch's task file is met and the work is committed, but nothing is
on `master` yet — downstream branches must still base off it, not off `master`. "🚧 In progress"
means the branch exists and carries commits, but its exit gates are not all met — this state was
missing until 2026-09-01, which is how 009 kept reading as "Tasks drafted" with six commits on it.
M1b's two gates are both met: **G1** on 2026-09-05 (unlocks Phase 4A / 013) and **G2** on
2026-09-06. `suite_hash` was **re-frozen** at `1e868c7bf811` on 2026-09-21 (prior value
`2747100dadf6` is void). Two consequences you need before touching anything: **the soak gate is now a batch rule —
one declared batch of exactly 10 consecutive first-try green full runs on a single `commit` /
`suite_hash` / browser / os / lock (no calendar span; rule adopted 2026-09-28, replacing ≥10 runs /
≥5 workdays; defined in §7 of `plan-tech-stack-migration.md`). A batch has passed (see
`soak-log.md`), but since the 2026-09-30 ruling no earlier batch admits 012 by itself: 012 needs
the start check in §7 ("012 开工核验") on the exact `commit` it branches from. 019 and 023 changed
`suite_hash`, so that check includes mechanism gate item 3.** History, condensed: on
2026-09-21 fixing a real data-loss bug (009 debt #9) required re-judging a frozen test, so the
ledger and all three of §7's **mechanism-challenge gates** were reset together — a deliberate,
recorded trade. Against the new hash, items 1 (clean Linux) and 3 (random collection order)
re-passed; item 2 (CPU pressure) measured FAIL on 2026-09-23, was attributed to a test-fixture
fault in frozen `helpers.py` (not a product defect), and on **2026-09-24 was downgraded by
maintainer ruling to non-blocking / record-only** — downgraded, not passed (its fix is 009 debt
#49). Under the 2026-09-28 rule, item 1 must re-pass on the final candidate `commit` and item 3
must hold for the current `suite_hash`. On **2026-10-08 a further maintainer ruling retired item 2**:
it is no longer run or recorded (items 1 and 3 still block; restoring it needs a new ruling).
Both rulings live in §7 of `plan-tech-stack-migration.md` (below discipline 3); results, the
attribution evidence ("第 2 项归因"), batch declarations and verdicts live only in `soak-log.md` —
do not restate them. Verdicts are scripted: `uv run python scripts/soak_run.py --verdict <batch ID>`
(exit 0 = PASS). `--append` requires the whole working tree clean, so batches run in a clean
detached worktree of the SHA under test with `--ledger` pointing back at the main ledger.
And **any byte changed under
`tests/e2e/baseline_1b/**`, `tests/e2e/conftest.py`, `helpers.py`, `test_harness_smoke.py`, or the
four `tests/fixtures/` files changes `suite_hash`, so no earlier batch covers the suite any more —
a fresh 10-run batch (plus a re-run of mechanism gate item 3) is needed** (docstrings included).
Since 2026-09-28 that costs ~10–15 min, not weeks, and 012's gate F allows such changes as long as
the batch is re-run. Progress and the
frozen value are defined only in
[`tasks/soak-log.md`](docs/plans/20260816-tech-stack-migration/tasks/soak-log.md); do not restate
them elsewhere.

"Allocated" means the number is reserved but no branch exists yet. "Tasks drafted" means
`docs/plans/20260816-tech-stack-migration/tasks/{branch}.md` exists. "WI-n – WI-m" means the
work items live in `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` §4;
frontend branches have no task files.

### Shipped features (implemented; see code, not specs)

See the feature ledger [`docs/feature-ledger.md`](../../../docs/feature-ledger.md) — the single
definition site. When a milestone here flips to ✅ Merged, update the ledger in the same write-back.

**Not covered here:** triaging audit findings (`audit-findings-triage`), running two or more branches
in parallel (`/coordinate`, with this repo's `coordinate-bindings`), and proving a feature in the
running app (`verify-reader3`).
