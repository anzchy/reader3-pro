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
the dependency graph permits several legal orders and they do not cost the same. Its status column
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
| M4a-债 — library routes not tied to the new format | `018-library-routes` | migration | 🚧 In progress **(2026-10-01: branch open with commits; WI-1 / WI-2 done, rebased onto `e3dde84`, WI-3 onward in progress — on the critical path to 012; order in the progress dashboard. Reviewed 2026-09-26, Q1–Q12 all ruled; Q10 / WI-8 amended 2026-09-30: `--append` is refused under `GITHUB_ACTIONS`, otherwise unless `git merge-base --is-ancestor HEAD origin/master` succeeds.) — 2026-09-26 ruling D1: takes 013-deferred debts #51 / #56 / #58 / #53 plus a per-book write-coordination contract, and the closing reconciliation of 009 debt #31 (the CI `e2e` job already exists since 2026-09-20; CI runs never append to the soak ledger); runs before 012 (it was scheduled into the soak wait; since the 2026-09-28 batch rule there is no multi-week wait left). Rationale lives in `tasks/012-storage-format.md` §6 D1. 018 WI-1 (2026-09-30) rewrote the 009 debt-table owner column for #51 / #53 / #56 / #58 to 018 and generalised `test_track_d_ledger.py` to `012|018 debt #N`, prefix equal to the owner's branch number.** |
| M1b/M2-债 — frozen-set debt window | `019-frozen-set-debts` | migration | ✅ Merged (PR #29) **— merged 2026-10-01, merge commit `eda9694` (branch tip `d31f53d`). Paid 009 #49 (partly) / #50 / #62 and 017 finding #10; opened 009 #65–#68. No task file — payments are recorded in the 009 / 017 debt tables. Changed `suite_hash` (value in `soak-log.md`); the 012 pre-start batch covers it.** |
| ⟂ — debug-state getter | `020-debug-state` | standalone plan `docs/plans/20260928-debug-state-getter.md` | ✅ Merged (PR #30) **— merged 2026-10-01, merge commit `40e807d` (branch tip `7fc0dbf`). `Reader3Epub.getDebugState()` read-only state surface; opened 009 #63 (owner 014 WI-19). No frozen-set change.** |
| ⟂ — E2E lock as an fcntl wrapper | `021-e2e-lock` | migration (§9 row; no task file) | ✅ Merged (PR #32) **— merged 2026-10-01, merge commit `e3dde84` (branch tip `f9b3d1f`). The e2e lane `command` now runs through `scripts/e2e_lock.py` (fcntl lock on `~/.cache/reader3-e2e.flock`, kernel-released on exit; BUSY exits 75; bypassed under `GITHUB_ACTIONS`). Retires the hand-managed mkdir lock. No frozen-set change.** |
| ⟂ — feature-ledger Summary Evidence validation | `022-ledger-evidence` | migration (§9 row; no task file) | ✅ Merged (PR #31) **— merged 2026-10-01, merge commit `ebf4ad7` (branch tip `7ce1bed`). `build_feature_ledger.py --check` now validates the Summary `Evidence` cell against Rule 7 (form only, not existence); rows F-001 / F-004 / F-012 / F-015 / F-019 / F-029 corrected with verified evidence. No frozen-set change.** |
| M1b-债 — frozen-set prep before the 012 start check | `023-frozen-set-prep` | migration (§9 row; no task file — payments in the 009 debt table #65–#68) | Allocated (2026-10-01) **— sole frozen-set owner this round; merges after 018 and recounts the `lint_e2e_groups.py` constants on rebase.** |
| ⟂ — 012 Q2 commit-mechanism prototype | `024-q2-commit-prototype` | migration (§9 row; no task file) | Allocated (2026-10-01) **— artifacts only under `tasks/evidence/q2-commit-prototype/`; never `src/`. Ruling and the ADR superseding ADR-0007 stay with the maintainer / 012.** |
| M3 — storage migration | `012-storage-format` | migration | Tasks drafted **(review in progress: D1, Q1–Q6 ruled, Q7+ open (§6); branch not opened. Blocked by 018 not yet merged and by the 012 start check — a fresh 10/10 batch on the exact `commit` 012 branches from, with mechanism gate item 1 first-passing on that same `commit` (2026-09-30 ruling, defined only in §7 of `plan-tech-stack-migration.md`, "012 开工核验"); entry conditions in `tasks/012-storage-format.md` §1, gate F in §4.) Keeps #35 / #54 / #55 and, as its last wave, #57 (acceptance requires new-format output) and #52 (needs the generation swap).** |
| M4a — TS shell + settings + library | `013-ts-frontend-shell` | **frontend** | ✅ Merged (PR #25) **— merged 2026-09-26, merge commit `1ec5ff7`. Work items WI-9 – WI-13 plus the Track D implementation items; the reader-side and backend-dependent halves are pinned to 014 (WI-16 / WI-16b) and 012 debts #51–#58 (#51 / #53 / #56 / #58 re-assigned to 018 on 2026-09-26).** |
| M4b — TS reader | `014-ts-frontend-reader` | **frontend** | WI-14 – WI-19 (incl. inserted WI-16b, library-side deferred acceptance) |
| M5 — launch + PWA | `015-launch-experience` | migration (CLI) ＋ **frontend** (PWA) | Allocated / WI-20 |

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
018 merged, then a fresh batch on the exact `commit` it branches from, with mechanism gate item 1
first-passing on that same `commit` and item 3 re-run only if `suite_hash` changed (§7 "012 开工核验").
Before 018 comes a frozen-set debt window (009 #49 / #50, 017 finding #10, the PR #28 leftover);
its branch number is allocated in §9 when it opens.** History, condensed: on
2026-09-21 fixing a real data-loss bug (009 debt #9) required re-judging a frozen test, so the
ledger and all three of §7's **mechanism-challenge gates** were reset together — a deliberate,
recorded trade. Against the new hash, items 1 (clean Linux) and 3 (random collection order)
re-passed; item 2 (CPU pressure) measured FAIL on 2026-09-23, was attributed to a test-fixture
fault in frozen `helpers.py` (not a product defect), and on **2026-09-24 was downgraded by
maintainer ruling to non-blocking / record-only** — downgraded, not passed (its fix is 009 debt
#49). Under the 2026-09-28 rule, item 1 must re-pass on the final candidate `commit` and item 3
must hold for the current `suite_hash`; item 2 stays record-only.
The ruling lives in §7 of `plan-tech-stack-migration.md` (below discipline 3); results, the
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
