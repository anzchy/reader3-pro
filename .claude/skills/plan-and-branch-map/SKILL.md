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
| [`docs/plans/20260816-tech-stack-migration/`](docs/plans/20260816-tech-stack-migration/README.md) | Backend layering, storage format, test net + CI, **branch numbering** | 007, 008, 009, 011, 012, 015 (CLI) |
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
| M4a-债 — library routes not tied to the new format | `018-library-routes` | migration | Tasks drafted **(skeleton 2026-09-26, under review.) — 2026-09-26 ruling D1: takes 013-deferred debts #51 / #56 / #58 / #53 plus a per-book write-coordination contract, and the closing reconciliation of 009 debt #31 (the CI `e2e` job already exists since 2026-09-20; CI runs never append to the soak ledger); runs during the soak wait, before 012. Rationale lives in `tasks/012-storage-format.md` §6 D1. The 009 debt-table owner column and `test_track_d_ledger.py` still say 012 until 018 kicks off and rewrites them in one batch.** |
| M3 — storage migration | `012-storage-format` | migration | Tasks drafted **(skeleton 2026-09-26, under review; still blocked by soak). Keeps #35 / #54 / #55 and, as its last wave, #57 (acceptance requires new-format output) and #52 (needs the generation swap).** |
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
`2747100dadf6` is void). Two consequences you need before touching anything: **Phase 3 / 012 is
still blocked — now only by the soak count (≥10 runs / ≥5 workdays).** History, condensed: on
2026-09-21 fixing a real data-loss bug (009 debt #9) required re-judging a frozen test, so the
ledger and all three of §7's **mechanism-challenge gates** were reset together — a deliberate,
recorded trade. Against the new hash, items 1 (clean Linux) and 3 (random collection order)
re-passed; item 2 (CPU pressure) measured FAIL on 2026-09-23, was attributed to a test-fixture
fault in frozen `helpers.py` (not a product defect), and on **2026-09-24 was downgraded by
maintainer ruling to non-blocking / record-only** — downgraded, not passed (its fix is 009 debt
#49). So the mechanism gates no longer block 012; the soak ledger was **not** reset by that ruling.
The ruling lives in §7 of `plan-tech-stack-migration.md` (below discipline 3); results, the
attribution evidence ("第 2 项归因"), and the current count live only in `soak-log.md` — do not
restate them. Waiting alone will not clear the count: it needs `soak --append` runs on `master`.
And **any byte changed under
`tests/e2e/baseline_1b/**`, `tests/e2e/conftest.py`, `helpers.py`, `test_harness_smoke.py`, or the
four `tests/fixtures/` files resets that count to zero** — docstrings included. Progress and the
frozen value are defined only in
[`tasks/soak-log.md`](docs/plans/20260816-tech-stack-migration/tasks/soak-log.md); do not restate
them elsewhere.

"Allocated" means the number is reserved but no branch exists yet. "Tasks drafted" means
`docs/plans/20260816-tech-stack-migration/tasks/{branch}.md` exists. "WI-n – WI-m" means the
work items live in `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` §4;
frontend branches have no task files.

### Shipped features (implemented; see code, not specs)

Keyword + semantic search · multi-provider AI with RAG · 3-pane library with collections and bulk
indexing · Dedao-style UI · full-screen paginated reader with annotations.
