# Q2 commit-mechanism prototype: evidence report

Branch `024-q2-commit-prototype`. Evidence for 012 §6 **Q2**: with `manifest.json` already ruled the
commit marker (written last), how does a multi-artifact publish commit atomically and recover after a
crash? Two candidates were built and crash-tested side by side:

- **A**: keep the flat layout and add a persistent recovery journal.
- **B**: build each publish into a generation directory, then atomically swap one pointer. The root
  `manifest.json` is that pointer.

Also gives advice on **Q8** (where the writer lives). This is evidence, not the ruling: the Q2 cell and
the ADR superseding ADR-0007 stay with the maintainer.

## 1. Purpose and scope

- Throwaway, stdlib-only prototype. It does not import `src/` or `reader3_app`; nothing under `src/`,
  `tests/` or `docs/adr/` was changed.
- The "book" is a fixed fake carrying a version tag `v1`/`v2`:
  - a 3-chapter `chapters.jsonl` with non-ASCII text, so byte offsets differ from character offsets;
  - `book.epub`;
  - `images/` with 2 files;
  - `book.pkl`, written as the dual-write peer. It is **not** the marker.
- The user-owned `notes.json` and `ai_meta.json` sit in the book dir. Every cell checks they are byte-,
  inode- and `mtime_ns`-identical afterwards.
- Out of scope: real EPUB parsing, Chroma, the ADR-0015 locks (assumed held, see §8), power-cut testing
  (see §11).

## 2. How to run

```bash
uv run pytest docs/plans/20260816-tech-stack-migration/tasks/evidence/q2-commit-prototype -q
# -> 89 passed, 3 skipped   (~12 s; the 3 skips need PROTO_REAL_XDEV_DIR, see dim 5)
uv run python docs/plans/20260816-tech-stack-migration/tasks/evidence/q2-commit-prototype/gen_matrix.py
# rewrites MATRIX.md; byte-identical on rerun (checked with cmp). test_q2_matrix_is_current fails if stale.
```

The run is not collected by the normal lanes (`testpaths = ["tests"]`; the unit lane still collects
2693). Optional env vars:

- `PROTO_FULLFSYNC=1`: `durable_fsync` uses `F_FULLFSYNC`.
- `PROTO_REAL_XDEV_DIR=<dir on another volume>`: runs the real cross-device tests. The prototype never
  creates or mounts a volume.

### Files

| path | role |
|---|---|
| `proto/common.py` | Shared: format writer (per-chapter `offset_bytes`/`length_bytes`/`sha256` plus whole-file size/sha), manifest, readback validator, the reader-side classifier, hooks, fsync helpers, same-device check |
| `proto/mech_a_journal.py` | Mechanism A |
| `proto/generation_core.py` + `proto/mech_b_generation.py` | Mechanism B: generic core plus the book-specific spec |
| `proto/fake_index.py` | Fake WI-7 index driven by the same `generation_core` |
| `proto/harness.py`, `proto/cli.py` | Crash harness. Real `os._exit(137)` crashes run in `python -S` subprocesses |
| `gen_matrix.py` → `MATRIX.md` | Deterministic matrix generator |
| `test_q2_*.py`, `conftest.py` | Tests |

**Crash injection.** Every step calls `hook(mech, step, "before"|"after")`, and so does every recovery
step. A crash is selected with `PROTO_CRASH=<mech>:<step>:<before|after>:<kill|raise>`.

## 3. Step mapping onto ADR-0007 Decision Outcome 1–8

012 WI-1 defines the eight steps only as "按 ADR-0007 八步落盘", so ADR-0007 Decision Outcome 1–8 is
the definition site. Step 3 (record offsets/hashes) is bookkeeping during steps 1–2, not a separate I/O
point.

### A (flat, journal)

Staged files go in `<book>/.staging/<txid>/`; the journal is `<book>/.publish-journal.json`.

| step | action | ADR-0007 |
|---|---|---|
| a1 | write staging `chapters.jsonl.tmp`, recording offsets and hashes | 1 + 3 |
| a2 | fsync it | 2 |
| a3 | stage `book.epub`, `images/`, `book.pkl`; fsync the files, the staging dirs and `.staging/` | (2, generalised) |
| a4 | write `manifest.json.tmp` in staging (carries `txid`) | 4 |
| a5 | fsync it | 5 |
| a6 | full readback from disk: seek each chapter, JSON parse, id/order/hash, whole-file size/sha, every artifact's sha and tag, the `images/` set. On failure: rmtree staging and raise; live is untouched | 6 |
| a7 | journal `{txid, staging, new_manifest_sha, artifacts:[{name, live, aside, existed}]}`: tmp → fsync → rename → fsync staging + book dir | *new* |
| a8.\<artifact\> | rename live → `aside/` (if it existed) + fsync both dirs | 7, gap 1 |
| a9.\<artifact\> | rename staged → live + fsync the dirs | 7 (generalised to 4 artifacts) |
| **a10** | `os.replace` manifest → fsync book dir. **COMMIT POINT** | 8 |
| a11 | unlink the journal → fsync | *new* |
| a12 | rmtree staging (including the asides) | cleanup |

`recover_a`:

1. **No journal:** remove `.staging/*`.
2. **Journal present:** compare the live manifest's sha with `new_manifest_sha` (and its `txid`, see F1).
   - **They match:** roll forward. The asides go with staging.
   - **They differ:** roll back in reverse order. An artifact that `existed` gets `aside → live` if the
     aside is still there. An artifact that did not exist is unlinked or rmtree'd if present.
3. **Unlink the journal last**, then clean staging.

The in-process exception path calls the same `recover_a`. If the rollback itself fails, the journal stays
for a later `recover_a`.

### B (generation + pointer)

| step | action | ADR-0007 |
|---|---|---|
| b1 | `mkdir gen/<g>` (g = max(existing gens, manifest.generation) + 1); write `chapters.jsonl` with offsets | 1 + 3 |
| b2 | fsync it | 2 |
| b3 | write epub, images, pkl into `gen/<g>`; fsync | (2) |
| b4 | write `<book>/manifest.json.tmp` with `generation = g` | 4 |
| b5 | fsync it | 5 |
| b6 | readback against `gen/<g>`. On failure: rmtree `gen/<g>`, unlink the tmp, raise | 6 |
| b7 | fsync the `gen/<g>` tree, `gen/` and the book dir. This durability barrier **replaces** ADR step 7; there is no chapters replace | 7 |
| **b8** | `os.replace` manifest → fsync book dir. **COMMIT POINT** | 8 |
| b9 | GC: rmtree every `gen/*` except g | cleanup |
| b10 | only over a legacy flat book: remove the now-unreferenced flat `book.epub`, `images/`, `book.pkl` | (ADR-0009 migration) |

`recover_b`:

1. Read the generation from the manifest. An unreadable manifest **raises**, so nothing is GC'd under it.
2. Remove every `gen/*` the manifest does not name.
3. Unlink `manifest.json.tmp`.
4. If the manifest names a generation and legacy flat files remain, remove them.

## 4. Crash matrix summary

Full rows are in [MATRIX.md](MATRIX.md): 1567 cells, every one PASS. Across all cells: **0 corrupt final
states, 0 residue, 0 user-file changes**.

| mech | mode | cells | missing | old-valid | new-valid | test node (`test_q2_crash_matrix.py::`) |
|---|---|---|---|---|---|---|
| A | kill (`os._exit(137)` in a subprocess) | 180 | 62 | 93 | 25 | `test_q2_cells[A-kill-S0..S3]` |
| A | raise (in-process exception, own rollback) | 180 | 62 | 93 | 25 | `test_q2_cells[A-raise-*]` |
| A | raise+undofail k=1 / k=2 (k-th restore rename → `EIO`; a fresh process recovers) | 46 / 40 | 0 | 86 | 0 | `test_q2_cells[A-raise+undofail{1,2}-S1..S3]` |
| A | recoverykill (kill publish, then kill recover at each of its points, then recover) | 552 | 0 | 504 | 48 | `test_q2_cells[A-recoverykill-S1,S2]` |
| A | exdev-simulated (n-th rename raises `EXDEV`) | 40 | 12 | 28 | 0 | `test_q2_cells[A-exdev-simulated-*]` |
| B | kill | 92 | 30 | 45 | 17 | `test_q2_cells[B-kill-*]` |
| B | raise | 92 | 30 | 45 | 17 | `test_q2_cells[B-raise-*]` |
| B | recoverykill | 304 | 0 | 240 | 64 | `test_q2_cells[B-recoverykill-S1,S3]` |
| B | exdev-simulated | 5 | 2 | 3 | 0 | `test_q2_cells[B-exdev-simulated-*]` |
| B-core (WI-7 fake index) | kill | 36 | 15 missing / 15 fp-old / 6 fp-new | | | `test_q2_cells[B-core(index)-kill-I-*]` |

Scenarios:

- **S0:** first publish into a dir that does not exist.
- **S0u:** first publish into a dir holding only user files.
- **S1:** v1 (with epub and images) → v2.
- **S2:** v1 had **no** `images/`.
- **S3:** first publish over a legacy flat-pkl book.

Coverage checks:

- `test_q2_every_crash_point_is_covered` asserts that kill and raise each hit every hook point the publish
  reaches (A: 36 per scenario; B: 18, or 20 for S3).
- `test_q2_no_corrupt_no_residue_user_intact` is the global gate.
- `judge()` also seek-reads every chapter of every `new-valid` cell
  (`test_q2_every_new_valid_cell_passed_the_seek_check`, `test_q2_seek_every_chapter_by_offset[A,B]`).

**Step 6** (`test_q2_step6_readback.py`, 16 cases): a flipped byte in the staged chapters, or a wrong
`offset_bytes`, fails the readback. The whole book dir then comes back byte-, inode- and
`mtime_ns`-identical for A and B across S0u/S1/S2/S3. Directory mtimes are excluded, because staging and
`gen/<g>` are created and removed inside the book dir.

**Negative controls** (`test_q2_findings_and_controls.py`) show the classifier catches real damage:

- A SIGKILL at `a9.images:after` with no recovery classifies as `corrupt`. That is today's
  in-memory-undo situation.
- A recovery that does not remove "artifacts that didn't exist before" leaves the S2 dir `corrupt`.

## 5. Comparison

**1. A consistent version from every crash point.**

- Both mechanisms land in the allowed state from every crash point: 1567/1567 cells.
- For an *unlocked concurrent reader* (liveview, informational) they differ sharply:
  - **A:** the dir reads `corrupt` at 16 of 36 hook points in S1/S2 (`a8.chapters.jsonl:after` through
    `a10:before`), because files are moved aside one by one under the old manifest.
  - **A in S0/S3:** the new `book.pkl` is live before the manifest (`pkl-only-new`), so a reader on the
    ADR-0009 `missing → book.pkl` path sees v2 before the commit point.
  - **A in S3:** the legacy book transiently reads `missing` (8 points).
  - **B:** never anything but `missing`/`old`/`new`. See `test_q2_liveview_b_is_snapshot_consistent` and
    `test_q2_liveview_a_exposes_transient_states`.

**2. "Rollback failed to discard artifacts that didn't exist before" (Q2 / 009 #59).**

- Today's `_commit_staged_artifacts` (`reader3.py:611`) keeps its undo only in memory. `_restore`
  (`reader3.py:598`) is right in-process, but a SIGKILL skips it. The next run can only *refuse*, via
  `_clear_staging_dirs` (`:432`) and `_parked_asides` (`:301`). It cannot tell that a new `images/` beside
  an old marker is foreign.
- **A** records `existed:false` durably in the journal, so a fresh process removes the stray artifact.
  Cells S2 kill/raise/recoverykill and raise+undofail k=1,2 all end `old-valid` with residue 0.
- **B** has no such state at all: the new `images/` only ever exists inside an unreferenced `gen/<g>`,
  which is garbage by definition.
- B's analogue of undofail is a failed in-process cleanup. It leaves only garbage, and readers still see
  `old-valid` (`test_q2_b_failed_cleanup_is_only_garbage[b3,b6,b8]`).

**3. Recovery runs before staging cleanup.**

- **A:** publish calls `recover_a` before creating new staging. The journal is unlinked (r3) before
  staging is removed (r4), so a kill between them leaves "no journal + staging", which is harmless
  garbage.
- **B:** the pointer is read (r1) before GC (r2). An unreadable pointer raises, so nothing is ever GC'd
  under a corrupt manifest.
- Killing recover at every one of its own steps and re-running it converged in all 552 (A) and 304 (B)
  recoverykill cells.

**4. Shape-similarity to WI-7.**

- One `generation_core.publish_generation`/`recover_generations` drives both the book (pointer
  `manifest.json`, gens in `gen/`) and the fake index (pointer `index_meta.json`, gens in `collections/`).
- `generation_core` contains the **only** `os.replace(` in either
  (`test_q2_book_and_index_share_one_core`).
- The index survives a kill at each of its 18 hook points, from both an empty and an old start, with
  residue 0 (36 cells).
- A's journal has no counterpart in WI-7, which would still need its own pointer swap.

**5. EXDEV (simulated) and the ADR-0007 error.**

- **What actually happens across devices:** `rename(2)` and `os.replace` raise `OSError(EXDEV)`. Only
  `shutil.move` falls back to a copy.
- **Simulated cells:** in every `exdev-simulated` cell the publish raised `EXDEV` and the dir ended at
  the pre-publish state. `shutil.move/copy/copy2/copyfile/copytree` were patched to fail the cell and
  never fired. All EXDEV evidence here is **simulated**.
- **Rename surface:** A makes 2 + 2×(existing artifacts) renames per publish, which is 10 in S1. B makes
  exactly **one**, the pointer (`test_q2_exdev_surface`).
- **The ADR error:** ADR-0007 states the wrong "degrades to copy" claim in **four** places. Lines **25,
  52 and 78** were already known. `grep -n 拷贝 docs/adr/0007-crash-safe-publish-protocol.md` also hits
  **line 67** ("协议不覆盖跨文件系统的 `books/` 部署（那退化为拷贝语义…）").
- **Proposed replacement wording** for the superseding ADR:
  > `rename(2)`/`os.replace` 只在同一文件系统内成立；跨设备时它**不退化为拷贝**，而是直接抛 `OSError(EXDEV)`（会退化为拷贝的是 `shutil.move`，本协议禁用它）。协议因此要求 staging（A：`<book>_data/.staging/`；B：`<book>_data/gen/`）建在书目录**内部**，并在第 1 步之前断言 `os.stat(staging_parent).st_dev == os.stat(book_dir).st_dev`，不等即拒绝发布、目录不动。跨卷部署下发布失败而不损坏，不是静默降级。
- **The enforcer** is twofold:
  1. Staging and generations are created inside `<book>_data/`.
  2. `common.assert_same_device` runs before step 1. It refused before any step hook fired in
     `test_q2_same_device_check_refuses_before_step1[A,B]` (`st_dev` patched). Real cross-device runs
     are `test_q2_real_exdev_*`, which skip unless `PROTO_REAL_XDEV_DIR` is set.
- **Today's gap:** `_staging_dir` (`reader3.py:205`) makes a *sibling* `<book>_data.staging-<pid>` in
  `books/`. If `<book>_data` is a symlink or mount point onto another volume, staging sits on the
  `books/` volume and every replace raises `EXDEV`. No `st_dev` check exists in `src/` today (grep finds
  none).

**6. Dependence on staging naming.**

- Today, ownership is inferred from names: the `.staging-<digits>` suffix, `_is_own_staging_name`
  (`reader3.py:280`), plus pid and flock (`_staging_dir_is_owned` `:252`, `_acquire_staging_lock` `:219`).
- **A** uses a fixed location (`.staging/`). The transaction's identity is the `txid` *inside the
  journal*. No name is parsed.
- **B** needs no naming rule at all: whatever the pointer does not name is garbage.
- Both retire the "`sample_data.staging-1_data` looks like staging" hazard, because staging is no longer
  a sibling in `books/`.

**7. fsync points (macOS/Linux).**

- The audit (`test_q2_fsync_order_a/b[S0..S3]`) wraps `os.open`, `os.fsync`, `os.replace` and `os.rename`.
- **A:**
  - The journal content is fsynced before its rename.
  - The book dir is fsynced after that rename, and before the first a8 rename.
  - Every staged payload file is fsynced before the journal.
  - After every rename, the destination dir and the book dir are fsynced before the next rename.
  - The manifest is the last rename.
- **B:**
  - Every file and dir of `gen/<g>`, plus `gen/` and the book dir, is fsynced before b8.
  - `manifest.json.tmp` is fsynced before b8.
  - The book dir is fsynced after b8.
- **Audit finding:** the first draft of the A audit also demanded a source-dir fsync after a10, which the
  code does not do. It is unnecessary, because the source is staging and staging is garbage once the
  commit lands. The rule was narrowed and documented in the test.
- **Linux:** directory entries are durable only after an fsync of the directory.
- **macOS:** `fsync(2)` does **not** flush the drive cache; only `fcntl(F_FULLFSYNC)` does.
  `durable_fsync` uses it when `PROTO_FULLFSYNC=1` and falls back for fds that refuse it.
  `test_q2_durable_fsync_uses_full_fsync_on_macos[A,B]` shows that every barrier routes through
  `F_FULLFSYNC`. The fallback branch was not exercised: no fd refused `F_FULLFSYNC` in that run.
- **Cost:** A has about 2 fsyncs per rename × 10 renames. B has 1 tree barrier and 1 pointer.

**8. Code size and complexity** (MATRIX "Code size"; non-blank, non-comment, non-docstring lines).

| | code lines | if-branches in recovery functions |
|---|---|---|
| A (`mech_a_journal.py`) | 142 | 9 |
| B (`mech_b_generation.py` 39 + `generation_core.py` 95) | 134 | 8 (1 + 7) |
| shared (`common.py`) | 269 | 0 |

Raw size is close; what differs is the *kind* of state:

- **A's recovery** has a decision (forward or back) and a per-artifact × existed × aside-present table,
  and it needs a per-transaction identity (F1).
- **B's recovery** is "keep what the pointer names". 95 of B's lines are reused verbatim by WI-7.

For comparison, today's protocol in `reader3.py` (lines 178–720, including docstrings) is about 540
lines and still cannot recover.

**9. Reader-side cost (weighed fairly).**

- **A keeps the flat layout.** `grep -rn "book\.pkl\|book\.epub\|\"images\"\|'images'" src/reader3_app
  --include='*.py' | grep -v reader3_app/reader3.py` gives **29 hits in 8 files**. About 9 are live path
  constructions; the rest are comments and docstrings. The live sites are:
  - `web/routers/reader.py:27`, `:78`, `:88`, `:96`, `:115`
  - `web/routers/library.py:48`
  - `book_store.py:63`
  - `vector_search.py:109`

  Under A they all keep working unchanged, including epub.js's `GET /read/{id}/book.epub`
  (`reader.py:23-30`, `FileResponse(<book>/book.epub)`). This is A's real advantage.
- **Under B every one of those sites must resolve through the manifest.** For `/read/{id}/book.epub`:
  1. The route reads `<book>/manifest.json`, which is small and can be cached on its stat
     (`st_ino`, `st_mtime_ns`) the way `book_store` caches today.
  2. It takes `generation`.
  3. It serves `gen/<g>/book.epub`.
  4. With no manifest, it falls back to the flat legacy `book.epub` (ADR-0009 `missing`).

  Starlette's `FileResponse` ETag is derived from the resolved file's mtime and size, so it changes per
  generation, which is correct. Optionally, a generation-scoped URL (`/read/{id}/g/{g}/book.epub`) would
  make responses immutable and cacheable.
- **Hazard under B: GC vs. an in-flight reader.** A request that resolved g just before the pointer flip
  can hit b9's rmtree between resolving and `open()`. That gives a 404 or 500, not wrong bytes. An
  already-open file keeps streaming, because POSIX keeps unlinked inodes alive. ADR-0015 already lists
  "`FileResponse` streaming while the book is deleted" as not guaranteed. Mitigations:
  - retry once on `FileNotFoundError` after re-reading the manifest; or
  - defer GC of g-1 to the next publish's start (one generation of extra disk).
- **A has the mirror-image hazard, and it is worse.** During a8–a9 the *path itself* is missing or mixed
  for every reader, not only in-flight ones (dim 1). With ADR-0015's readers-take-no-lock rule, A exposes
  its corrupt window to normal page loads.
- **`book.pkl` under B** lives inside the generation. Only unmigrated books keep a flat pkl, read via
  ADR-0009 `missing → pkl`. 012 WI-4 already plans a format-agnostic `book_store`, so B's resolution cost
  lands in a module 012 is building anyway. `vector_search._load_book` is routed through it in WI-7.

**10. Disk peak** (book dir bytes, file sizes only; MATRIX "Disk usage").

| | S1 before | S1 peak | after |
|---|---|---|---|
| A | 1663 | 3978 | 1663 |
| B | 1636 | 3194 | 1636 (after GC) |

- Both peak at roughly old + new during the window. A moves the old version aside (rename, no copy) and
  drops it at a12; B keeps `gen/<old>` until b9.
- A's extra bytes are the journal and the manifest tmp, which is noise at real book sizes.
- B's first-publish peak equals its final size (S0: 1558 → 1558), because nothing is staged twice.

## 6. Findings

- **F1 (A, real flaw, fixed in the prototype).** A decides "committed?" by comparing the live manifest's
  sha with the journal's `new_manifest_sha`. If a book is republished with byte-identical content, the
  old and new manifests are equal. A kill mid-window is then misread as committed: recovery rolls
  *forward*, deletes the asides, and leaves a `corrupt` book.
  - The prototype embeds `txid` in the manifest, which makes the identity per-transaction.
  - `test_q2_finding_a_commit_identity_must_be_per_transaction[False-corrupt]` keeps the failing
    evidence; `[True-new-valid]` shows the fix.
  - B is immune, because `generation` is unique per publish.
- **F2 (A, liveview).** Unlocked readers see `corrupt` or `missing` states, and `pkl-only-new`, during
  a8–a10 (dim 1). This is not a crash-safety failure; it is a concurrency exposure inherent to a flat
  layout.
- **F3 (ADR-0007).** The "degrades to copy" text appears on 4 lines (25, 52, 67, 78), not 3.
- **F4 (S0 half-born dir).** See §7. Both mechanisms can leave a dir that today's scan would enumerate.

## 7. S0 half-born dir and the library scan

A first publish creates `<book>_data/` before the commit point. After a crash, A can leave the dir with
only `.staging/` (plus a journal), and B with only `gen/` (plus `manifest.json.tmp`). Both classify as
`missing` (`test_q2_s0_half_born_dir_classifies_missing`). Recovery then leaves an empty dir, and an empty
`_data` dir is not a book either.

Today's scan sites:

- `web/routers/library.py:39-43` lists every `*_data` directory and calls `load_book_cached`. It skips a
  half-born dir silently only because a missing `book.pkl` returns `None` (`web/server.py:397`, "Absence
  is silent").
- `ai/books.py:225` and `search_service.py:255` (`list_book_ids`, which requires `book.pkl` at `:259`)
  scan the same way.

**The rule the scan must become:** a `*_data` dir with **no `manifest.json` and no `book.pkl`** is not a
book; skip it silently. Neither a staging dir nor a `gen/` is ever evidence of a book. With
`manifest.json` present, the book is `valid` or loudly `corrupt` (ADR-0007), never skipped.

## 8. Ownership and lock semantics

Today three functions answer "is this leftover staging dir someone else's live run?" (line numbers
verified on this branch):

- `_acquire_staging_lock` (`reader3.py:219`) flocks `<staging>/.lock`.
- `_staging_dir_is_owned` (`:252`) probes that lock, with a pid fallback.
- `_is_own_staging_name` (`:280`) guards against `*_data.staging-*` name collisions.

**Assumption, for both A and B:** every publisher (import, migrate, upload, reprocess) holds the ADR-0015
**exclusive** book lock at `books/.locks/{book}.lock` for the whole publish, recovery included. Under that
lock there is no "someone else's live run", so the ownership question disappears.

- **A** replaces the three functions with a fixed staging location, the journal's `txid` naming the one
  in-flight transaction, and the rule "no journal ⇒ everything under `.staging/` is garbage".
- **B** replaces them with "every `gen/*` not named by `manifest.json` is garbage".

**Failure mode if that lock were absent** (stated, not built or tested):

- **Under A:** a second publisher's start-of-run `recover_a` would read the first publisher's live
  journal, see a manifest that does not match yet, and **roll back an in-flight transaction**, moving
  asides back under the first writer.
- **Under B:** a second publisher's `recover_generations` would rmtree the first's not-yet-referenced
  `gen/<g>` mid-build. Two pointer flips race and the last writer wins. B's next-generation choice is
  also not atomic without the lock.

Both are safe *only* under ADR-0015's exclusive lock. B fails slightly more benignly: a lost build, never
mixed live files.

## 9. Recommendation: **B (generation directory + single pointer)**

Three reasons:

1. **Snapshot consistency for lock-free readers.** ADR-0015 makes readers take no lock. B never exposes
   anything but old or new (0 transient states in liveview). A exposes 16/36 `corrupt` points per
   republish, plus `pkl-only-new` and a vanishing legacy book.
2. **One commit rename, and recovery that is plain GC.**
   - One `EXDEV` surface instead of 10.
   - No forward/back decision.
   - No per-artifact × existed table.
   - No transaction-identity trap (F1).
   - The "artifact that didn't exist before" class disappears structurally instead of being handled.
3. **One core for the book and WI-7.** `generation_core` is already exercised by the fake index (36
   cells), and WI-7 needs a generation swap regardless.

The cost is honest and bounded:

- About 9 live path sites, `/read/{id}/book.epub` included, must resolve through the manifest. 012 WI-4's
  `book_store` is the natural home.
- The GC-vs-in-flight-reader window needs a retry-once on `FileNotFoundError`, or GC deferred by one
  publish.

A would be the right choice only if touching reader paths were off the table, and even then A's liveview
windows would remain. This choice fixes the long-lived on-disk layout, so the maintainer may want a
second opinion before writing the superseding ADR.

## 10. Q8 advice: add `src/reader3_app/book_format.py`

What the prototype needed outside the two mechanisms clustered into `common.py`:

- the chapters writer with offsets;
- manifest build;
- readback validation;
- the reader-side three-state classifier;
- fsync helpers;
- the same-device check.

That is 269 code lines with **no** dependence on EPUB parsing (`ebooklib`/`bs4`). By contrast:

- `reader3.py` is already 956 lines centred on EPUB parsing.
- The classifier and readback are consumed by readers (`book_store`, the `storage_format()` three-state
  check), not by the EPUB parser.
- The generation core is consumed by `vector_search` (WI-7).

Keeping the writer in `reader3.py` next to `save_to_pickle` would make readers and the indexer import the
EPUB-parsing module, and with it `ebooklib`/`bs4`, just to reach format code. Recommended split:

- **`book_format.py`:** format, manifest, readback, classifier, and the B publish/recover (about 39 lines
  of book-specific spec).
- **`generation_core.py`** (or a section of `book_format.py`): imported by both `book_format` and
  `vector_search`.
- **`reader3.py`:** keeps parsing; its `process_epub` calls `book_format.publish(...)`. The legacy
  `save_to_pickle` stays beside it until pickle sunset.

## 11. What the prototype does NOT prove

- **Power-loss durability.** The fsync audit proves *ordering*, not that the disk honoured it.
  - No measurement on a real HFS+/APFS power cut, nor on ext4.
  - Drive-cache behaviour was not measured.
  - `F_FULLFSYNC` is exercised only as a code path.
- **Real `EXDEV` on a second volume.** EXDEV is simulated only. The real tests skip without
  `PROTO_REAL_XDEV_DIR`, and no volume was created or mounted.
- **Concurrency.** Nothing ran against real concurrent readers or the ADR-0015 locks, which are assumed
  held. Liveview samples state *between* steps from the same thread, not a reader racing a rename.
- **Integration cost in `src/`.** The reader path resolution (dim 9), the scan rule (§7) and the
  `book_store` changes are estimated, not built.
- **Chroma.** The WI-7 index is a fake. Chroma's own on-disk behaviour, collection naming and
  multi-process access are untested.
- **Scale.** Disk-peak numbers come from a ~1.6 KB fixture. Only the shape (old + new during the window)
  transfers; the absolute bytes are dominated by metadata.
- **Out-of-protocol damage.** Disk corruption and external edits are covered only as far as the
  classifier reporting `corrupt`. No repair path exists or is proposed.
- **Python and kill semantics.** The tests ran on Python 3.10 / macOS (darwin). The kill is `os._exit(137)`
  inside the process, not an external `SIGKILL`. That is equivalent for on-disk state.
