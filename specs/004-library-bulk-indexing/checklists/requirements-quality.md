# Requirements Quality Checklist: Library UI Reorg + Bulk Indexing (004)

**Purpose**: Validate requirements completeness, clarity, consistency, and traceability for `004-library-bulk-indexing`.
**Created**: 2025-12-19
**Feature**: `specs/004-library-bulk-indexing/spec.md`

**Defaults used**: Depth = Standard; Audience = PR reviewer; Focus = UX + API/persistence quality.

## Scope, Terminology, Traceability

- [ ] CHK001 Are all new concepts explicitly defined (Library “scope”, “collection”, “indexed”, “chunks”, “sections”)? [Spec §FR-001, Spec §FR-002, Spec §FR-013, Spec §FR-016]
- [ ] CHK002 Is there a single canonical term for “section” vs “chapter” and used consistently throughout? [Consistency, Spec §FR-002]
- [ ] CHK003 Are all MUST statements paired with objective, testable criteria (avoid vague adjectives)? [Measurability, Spec §FR-001]
- [ ] CHK004 Are out-of-scope items explicitly listed and aligned with plan assumptions (e.g., PDF ingestion, multi-book chat)? [Spec §Out of Scope, Spec §FR-018]
- [ ] CHK005 Do requirements include stable identifiers or section references for traceability (FR/NFR numbers referenced by UI/API sections)? [Traceability, Spec §Requirements]

## Library UI Layout & Views (UX Requirements Quality)

- [ ] CHK006 Are the Library layouts (image/grid vs list) specified beyond “exists” (information density, required fields per view)? [Spec §FR-004, Spec §FR-006, Spec §FR-007]
- [ ] CHK007 Is the placement and role separation of “Find books…” (title/author filter) vs cross-book content search explicitly specified to avoid ambiguity? [Gap]
- [ ] CHK008 Are default view mode and persistence semantics precisely specified (key name, scope, precedence, reset behavior)? [Spec §FR-005]
- [ ] CHK009 Are empty states specified for “no books”, “no results”, and “no collections”? [Gap]
- [ ] CHK010 Are visual/interaction states specified for disabled UI (PDF filter disabled + tooltip content)? [Spec §FR-007a]

## Selection & Bulk Actions (UX + Flow Completeness)

- [ ] CHK011 Is “selection mode” behavior specified (how selection is indicated, how selection interacts with navigation, how to exit selection mode)? [Spec §FR-008]
- [ ] CHK012 Are “Select all” and “Clear selection” semantics defined in the presence of scope filters and search filters? [Spec §FR-009]
- [ ] CHK013 Are bulk-action availability rules specified (when “Index selected” / “Add to collection” appears/enables)? [Spec §FR-010, Spec §FR-014]
- [ ] CHK014 Are partial-failure outcomes specified for bulk indexing (how many errors shown, whether retry is allowed, what is shown after completion)? [Spec §FR-012]
- [ ] CHK015 Are idempotency expectations stated for “Index selected” (re-index behavior, force reindex flags, repeated calls)? [Gap]

## Index Status, Counts, and Error Surfaces

- [ ] CHK016 Are index status states fully enumerated and consistent across library list/grid, search panel badges, and dashboard counts? [Consistency, Spec §FR-001, Spec §FR-016]
- [ ] CHK017 Is the source-of-truth for chunk counts defined (status endpoint vs index endpoint response) and conflict resolution specified? [Gap]
- [ ] CHK018 Are error messages and their UX surfaces specified (where errors appear, whether they persist, and any guidance text)? [Gap]
- [ ] CHK019 Are section count rules specified (e.g., `spine` length vs TOC entries; handling for empty/hidden chapters)? [Spec §FR-002]

## Collections (Persistence + API Requirements Quality)

- [ ] CHK020 Is the collections storage format and schema versioning specified (fields, IDs, uniqueness rules, and migration strategy)? [Spec §FR-015, Gap]
- [ ] CHK021 Are collection identity and naming constraints specified (allowed characters, max length, uniqueness, case sensitivity)? [Gap]
- [ ] CHK022 Are conflict scenarios specified (simultaneous edits, missing book ids, deleted books still referenced by collection)? [Gap]
- [ ] CHK023 Are API requirements specified for collections endpoints (request/response shapes, status codes, error formats)? [Gap]
- [ ] CHK024 Are persistence locations documented in technical docs as required (and aligned with gitignore)? [Gap]

## Dashboard Stats API (Aggregation Requirements Quality)

- [ ] CHK025 Are dashboard stats fields fully specified (definitions for indexed_percent rounding, chunk/section totals, and “indexed” criteria)? [Spec §FR-016]
- [ ] CHK026 Is `scope` encoding specified unambiguously and consistently used across UI filters and API? [Spec §FR-016a]
- [ ] CHK027 Are error/empty behaviors specified for stats API (unknown scope, unknown collection id, partial indexing data missing)? [Gap]
- [ ] CHK028 Are rate/latency expectations specified for stats API to avoid UI regressions on large libraries? [Gap]

## Search (Cross-Book Content Search vs Library Filter)

- [ ] CHK029 Are keyword/semantic/hybrid mode behaviors clearly distinguished, including indexing prerequisites and user messaging when not indexed? [Spec §FR-001, Spec §Out of Scope]
- [ ] CHK030 Are responsibilities between the library page and search panel specified (what data each uses; whether search modifies the book list)? [Gap]

## Chat (Library Panel)

- [ ] CHK031 Is the single-book chat selection requirement precise (input selector, default selection, behavior when no books available)? [Spec §FR-017]
- [ ] CHK032 Are the disabled/coming-soon states for all-books/collection chat explicitly specified (label text, tooltip/disabled reasoning)? [Spec §FR-018]

## Non-Functional, Security, and Privacy (Requirements Quality)

- [ ] CHK033 Are performance constraints stated for initial library render and subsequent status/stats updates (e.g., number of requests avoided, acceptable delay)? [Spec §NFR-002, Gap]
- [ ] CHK034 Are security/privacy constraints stated for the new persisted collections file (trust model, exposure via API, access control assumptions)? [Gap]
- [ ] CHK035 Are logging/observability expectations defined for long-running bulk indexing (what to log, user-facing progress vs server logs)? [Gap]

## Notes

- This checklist evaluates **requirements quality**, not implementation correctness.
- Use `[Gap]` items to drive targeted spec updates before implementation work expands.
