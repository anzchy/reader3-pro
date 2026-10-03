---
name: verify-reader3
description: >-
  Live verification of Reader3 Pro (FastAPI + epub.js reader) in its real web UI: start a
  sandboxed reader3-server on a free port with a throwaway books dir and a sandbox AI settings
  file through the control.py CLI, drive it with gstack /browse, and keep screenshots,
  getDebugState() JSON and side-effect read-backs as evidence. Use when proving a
  docs/feature-ledger.md F-NNN `Confirm` step, or a UI change, in the running app rather than
  in tests. Never touches books/ or config/ai_settings.json.
---

# verify-reader3: prove it in the running app

Five stages: Launch, Doctor, Drive, Evidence, Cleanup. Run them in order. Helpers and Gotchas
follow. Per-feature recipes live in the Feature Map,
[`references/features/README.md`](references/features/README.md): read the map file for your
F-NNN before you start.

Everything goes through one CLI, run from the repo root (this worktree):
`python3 .claude/skills/verify-reader3/scripts/control.py --help` lists the commands. Each command prints
exactly one JSON line, `{ok, command, data, error}`. Exit codes: 0 ok, 1 failure, 2 usage
error, 3 refusal (`error.code` starts with `refused_`). On failure, `error.try` is the next
command to run. Agent Bash calls share no shell state, and the CLI needs none: `up` records
the instance in `.claude/verify-evidence/instance.json`, and every later command reads it
from there (or from `--state PATH`). Commands that run with no instance (evidence, lane,
map check) do not need it.

<example>
user: "Prove F-018's Confirm step in the real app."
assistant: "I'll read `references/features/F-018.md`, run `control.py up --corpus smoke` and
`control.py doctor`, open the book with `$B`, wait with `control.py reader state --wait 15`,
select text with `control.py reader select "Alpha prose."`, pick Marker, then make a fresh selection and Add
Note → Save (the toolbar closes after Marker; see Gotchas), and read `notes.json` back with
`control.py fs cat books/smoke_data/notes.json`. Every sub-step matches the row, so `control.py evidence result PASS --note "selection emulated via reader select"`
closes it; had one not matched, the verdict would be DEVIATES. The evidence folder survives `control.py down`."
<commentary>
A ledger Confirm step to prove against the running app, not in tests: every stage runs, and
the evidence survives cleanup.
</commentary>
</example>

`$B` below is the gstack browse binary, `~/.claude/skills/gstack/browse/dist/browse`. Load the
`browse` skill once for its full command list. The CLI finds the same binary itself
(override: `VERIFY_READER3_BROWSE`).

## Launch

```bash
python3 .claude/skills/verify-reader3/scripts/control.py up --corpus smoke
python3 .claude/skills/verify-reader3/scripts/control.py up --corpus smoke --epub ./some.epub   # plus a real EPUB, read only
python3 .claude/skills/verify-reader3/scripts/control.py up --corpus smoke --ai-stub            # plus the offline AI stub (F-013)
```

`up` does what `tests/e2e/conftest.py` does for the e2e lane (`_free_port`, `_server_env`,
`e2e_books_dir`, `live_server`):

- It makes a fresh `verify-reader3.*` sandbox under the temp dir, with `books/`,
  `ai_settings.json` (path only) and `server.log` inside it.
- The server child gets no inherited `READER3_*` variable. A stray `READER3_TOKEN` would make
  every write return 401. It gets `READER3_BOOKS_DIR` and `READER3_AI_SETTINGS` pointing into
  the sandbox (absolute) before it starts. `server.py:102` reads the books dir at import
  time. If `READER3_AI_SETTINGS` were unset, the server would fall back to the relative
  `config/ai_settings.json`, the developer's file with real API keys. The sandbox settings
  file does not need to exist: a missing file means default settings with no keys.
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are always set.
- `--corpus smoke` ingests the synthetic book **`smoke_data`**, built by
  `tests/fixtures/epub_corpus.build_epub2`: chapter 0 is "One / Alpha prose.", chapter 1 is
  "Two / Beta prose.". It has one page per chapter. To test page turns, add a real
  multi-page EPUB with `--epub` (repeatable); each is ingested as `<basename>_data`.
- The port is a free one unless `--port` is given. The server log goes to a file, never a
  pipe (a full pipe blocks uvicorn). `up` polls `/api/health` for up to 60 s.
- `data` carries `sandbox`, `books_dir`, `ai_settings`, `port`, `base_url`, `pid`,
  `pid_start`, `log`, `state` and `books`. Use `base_url` wherever a ledger Confirm step says
  `http://127.0.0.1:8123`, and an id from `books` for `{book_id}`.
- Only one instance per checkout: `up` refuses (`refused_instance_running`) while the
  recorded one is alive. Run `down` first.

A failed or interrupted `up` stops what it started and removes only the sandbox it made.

## Doctor

**(a) Before driving:** confirm the server you started is the one answering.

```bash
python3 .claude/skills/verify-reader3/scripts/control.py doctor
```

It checks that the recorded PID is alive and is our `reader3-server` (command line, port and
start time all match), that `lsof` shows that PID listening on the port, and that
`/api/health` returns 200. It also reports the semantic extra (`extra_installed`,
`model_cached`, `hint`), whether the browse binary is present, and the stub PID if one is
recorded. Any failed check is `ok:false` with its own code (`no_instance`, `instance_dead`,
`pid_not_ours`, `port_not_ours`, `listener_unavailable` when `lsof` is missing, `health_failed`,
`stub_dead`). Stop then: you might be talking to someone else's server.

**(b) After you reach a reader page** (`/read/{book_id}/{n}`): `/api/health` only means
FastAPI is up. It says nothing about epub.js. Wait until the reader reports ready:

```bash
$B wait '[data-testid="rd-viewport"] iframe'
python3 .claude/skills/verify-reader3/scripts/control.py reader state --wait 15
```

`reader state` returns `window.Reader3Epub.getDebugState()` (contract v1) as `data`. With
`--wait` it polls until `ready` is true, or fails with `reader_not_ready` and
`data.last_state`. On a page that is not a reader page it fails at once with
`not_reader_page`: `getDebugState()` exists only on reader pages.

## Drive

Use gstack `/browse` (`$B`) for navigation and clicks, and the CLI for the steps that are
easy to get wrong by hand. Ledger `Confirm` steps hardcode `http://127.0.0.1:8123` and
`{book_id}`. Substitute `base_url` and a real id from `up`.

**Prefer `data-testid` handles** (the ones `tests/e2e/helpers.py` uses), qualified so that
each one matches exactly one node:

| Surface | Handle |
|---|---|
| Library book card | `[data-testid="lib-book-card"][data-book-id="smoke_data"]` (bare testid matches N cards) |
| Reader shell / iframe | `rd-shell`, `[data-testid="rd-viewport"] iframe` |
| Progress pill | `rd-page-indicator` (text `当前阅读至 N%`) |
| Rail | `rd-rail-toc`, `rd-rail-search`, `rd-rail-notes`, `rd-rail-font`, `rd-rail-ai`; back arrow has no testid: `a[title="Back to Library"]` |
| TOC | `rd-toc-panel`, `rd-toc-filter`, `rd-toc-row` |
| Selection toolbar | `rd-anno-toolbar` (open = class `is-visible`), `rd-anno-color-{yellow,green,pink,blue}`, `rd-anno-type-{marker,wavy,underline}`, `rd-anno-note`, `rd-anno-copy`, `rd-anno-delete`, `rd-anno-ask` |
| Note editor | `rd-note-editor`, `rd-note-editor-input`, `rd-note-editor-primary` (Save) |
| Notes panel | `rd-notes-panel`, `rd-notes-copy-all`, `rd-notes-review` |

Patterns that worked (take `BASE_URL` from `up`'s `data.base_url`):

```bash
$B viewport 1280x800
$B goto "$BASE_URL/"
$B wait '[data-testid="lib-main"]'
$B click '[data-testid="lib-book-card"][data-book-id="smoke_data"]'
python3 .claude/skills/verify-reader3/scripts/control.py reader state --wait 15
$B press ArrowRight
python3 .claude/skills/verify-reader3/scripts/control.py reader state
```

`$B press` sends keys to the page (ArrowLeft, PageUp, PageDown, ArrowUp, ArrowDown likewise).
`reader state` then shows `section.index`, `progress.sectionPage` and the rest of the state.

**Selecting text.** `browse` has no mouse-drag command, and its `cdp` allowlist has no
`Input.*`. `reader select` does what `tests/e2e/helpers.py::select_in_frame` does: it enters
the epub.js iframe, sets a DOM Selection on the exact text, fires the release event, always
switches back with `frame main` (even when the script fails), then polls the toolbar from the
outer page:

```bash
python3 .claude/skills/verify-reader3/scripts/control.py reader select "Alpha prose."
python3 .claude/skills/verify-reader3/scripts/control.py reader select "Alpha" --occurrence 1
```

`data` is `{selected, toolbar_visible}`. Text that is not in the chapter, or an occurrence out
of range, is `select_failed`: stop, and do not run the next commands. This is the only
allowed emulation; label it as such in the evidence. Everything after it (toolbar, editor,
Save) must be real `$B click`s.

**Did a click do anything?** For stub rows (a button with no handler), measure it instead of
eyeballing it:

```bash
python3 .claude/skills/verify-reader3/scripts/control.py ui inert --testid rd-notes-review --expect inert
python3 .claude/skills/verify-reader3/scripts/control.py ui inert --settle 1.0 -- press ArrowRight
```

`ui inert` clicks `[data-testid="ID"]` (or runs one browse command after `--`; `eval` is
refused) and reports `requests[]` (every `/api/*` request the action caused), `writes[]` (the
non-GET subset), `url_before` / `url_after` / `url_changed`, `attrs_before` / `attrs_after`,
`inert` and `mechanism`. `inert` is true only when there was no `/api` request, the URL did not
change and the element's attributes are equal. `--expect inert|active` turns a mismatch into
`unexpected_inertness`. A testid that is not on the current page is `testid_not_found` (nothing
is clicked); check `reader state` or `$B url` first.

How it measures (the Step 0 mechanism, `access_log`): it sends
`GET /api/health?verify-marker=<uuid4>-begin` before the action and `...-end` after the
`--settle` wait (default 1.0 s), waits for each marker line to appear in the sandbox server's
own uvicorn access log (`server.log`, read from the byte offset taken before the begin
marker), and keeps the `/api` and `/api/...` lines strictly between the two markers. A marker
that is not logged within 2 s is `marker_missing`. `--mechanism network` is the explicit
fallback: it clears and then reads `$B network` and keeps this `base_url`'s `/api` entries
(status may be `null` while pending). Limits are in Gotchas.

## Evidence

Use one folder per F-NNN per run, under `.claude/verify-evidence/` (gitignored, kept after
`down`):

```bash
python3 .claude/skills/verify-reader3/scripts/control.py evidence start F-018
python3 .claude/skills/verify-reader3/scripts/control.py evidence add --browse-screenshot 02-toolbar
python3 .claude/skills/verify-reader3/scripts/control.py fs cat books/smoke_data/notes.json
python3 .claude/skills/verify-reader3/scripts/control.py evidence result PASS
python3 .claude/skills/verify-reader3/scripts/control.py evidence result DEVIATES --note "sub-step 2: Marker closes the toolbar; Add Note needed a fresh selection"
```

- `evidence start` makes `<UTC YYYYMMDD-HHMMSS>-F-NNN` (suffix `-2`, `-3` on a clash) and
  records it as the open folder in `.claude/verify-evidence/current.json`. There is one open
  folder at a time and `evidence result` / `evidence add` / `lane` always write into it, so
  write the verdict before you `evidence start` the next feature; a folder left without
  `result.txt` has to be closed by hand.
- `evidence add FILE` copies a regular file in and never overwrites (`evidence_exists`). It
  refuses anything under either checkout's `books/` and either checkout's
  `config/ai_settings.json` (`refused_path`). To keep a sandbox read-back, pass the absolute
  sandbox path from `up`'s `books_dir`, for example `<books_dir>/smoke_data/notes.json`.
- `evidence add --browse-screenshot NAME` saves `NAME.png` via `$B screenshot`. Number the
  names in action order (`01-library`, `02-toolbar`, ...).
- `evidence show` lists the open folder.

Proof standards:
- **Real user path.** Get into the reader by clicking, not with `goto /read/...`, when the
  step says "click". Use no internal setters, no `window.Reader3*` mutators, no test endpoints.
  The only allowed emulation is `reader select` (the text-selection step), and you must label
  it as such.
- **Action plus resulting state.** Capture a screenshot and/or a `reader state` read after
  each step that changes something.
- **Side effects.** Read persisted state back from the sandbox with `fs cat`
  (`books/<id>/notes.json` for annotations, `ai_settings.json` for settings) or `fs stat` (for
  file modes). Do not trust the UI alone.
- **`result.txt`** in the run folder holds the verdict, one of PASS / FAIL / SKIPPED /
  DEVIATES, written by `evidence result` (each call replaces the previous one). Put the
  sub-step that decided it and the artifact names in `--note`. A Confirm step that does not
  match actual behaviour is DEVIATES. Record it there and in the ledger Audit log. Never
  silently rewrite the row.

## Cleanup

```bash
python3 .claude/skills/verify-reader3/scripts/control.py down --dry-run
python3 .claude/skills/verify-reader3/scripts/control.py down
python3 .claude/skills/verify-reader3/scripts/control.py evidence show
```

`down` kills **only** the recorded PIDs, and only when each one's command line, port and start
time still match (`refused_pid_identity` otherwise): TERM first, then KILL after 10 s. It never
kills by process name. It removes the sandbox only when it is a `verify-reader3.*` directory
directly under the temp dir (`refused_sandbox_shape` otherwise), clears the instance pointer
and leaves the evidence alone. With nothing running it is `ok:true`, `already_stopped:true`.
`--dry-run` reports `would_kill` and `would_remove` and changes nothing. The gstack browse
daemon is shared and left running. `evidence show` confirms the evidence folder survived.

## Helpers

Not stages, but used inside them. Every one reads the recorded instance unless noted.

```bash
python3 .claude/skills/verify-reader3/scripts/control.py fs ls books
python3 .claude/skills/verify-reader3/scripts/control.py fs stat ai_settings.json
python3 .claude/skills/verify-reader3/scripts/control.py api GET /api/health
python3 .claude/skills/verify-reader3/scripts/control.py api GET "/api/search/smoke_data?q=cafe" --expect 200
python3 .claude/skills/verify-reader3/scripts/control.py ai ask "Who is the narrator?" --book smoke_data
python3 .claude/skills/verify-reader3/scripts/control.py book add --epub ./some.epub
python3 .claude/skills/verify-reader3/scripts/control.py book index smoke_data
python3 .claude/skills/verify-reader3/scripts/control.py lane F-011 --dry-run
python3 .claude/skills/verify-reader3/scripts/control.py lane F-011 --runner pytest
python3 .claude/skills/verify-reader3/scripts/control.py map check
```

- `fs ls|stat|cat PATH`: read-only views of the sandbox. `PATH` is relative to the sandbox;
  anything that resolves outside it is `refused_path`. `fs cat` caps at 256 KiB.
- `api METHOD PATH`: one request to the sandbox server with `http.client` (no proxy, no
  redirects). Options `--json` (inline or `@file` inside the sandbox or the evidence root),
  `--header`, `--if-match`, `--expect STATUS`, `--timeout`, `--dry-run`. `data` has `status`,
  `headers` (`content-type`, `etag`, `location`), `body` and `elapsed_ms`. Use it instead of
  `curl` for ledger lines that `curl` the API.
- `ai ask QUESTION --book ID`: posts to `/api/ai/question/<book_uuid>?stream=true` and parses
  the SSE stream. `--concurrency N` (1-8) runs N in parallel; `--gate` drives the stub's gate
  and needs `up --ai-stub`.
- `book add --epub FILE` ingests one more EPUB; `book index ID` builds the semantic index. It
  needs the semantic extra, and without `--allow-download` it skips when the model is not
  cached (`skipped: "model_not_cached"`). If it fails with `OfflineModeIsEnabled` even though
  the model is cached, the `try` line already says `--allow-download`; see Gotchas.
- `lane F-NNN` (no instance needed) runs the ledger row's Tests, sorted into pytest, e2e
  (through `scripts/e2e_lock.py`) and vitest, as argv lists from the repo root, bounded by
  `--timeout` (default 1800 s). Logs go to `lane-<runner>.log` in the open evidence folder, so
  run `evidence start` first; `--dry-run` only prints the argv. Exit 75 with a `BUSY ` line is
  `lane_busy` (another e2e run holds the lock).
- `map check` (no instance needed) checks the Feature Map against the ledger and parses every
  control.py line quoted in this file and the map files with the real parser. Run it after
  editing any of them.

**Tokens.** `up` has no `--token` flag: the sandbox server always runs with no
`READER3_TOKEN` (state `token: null`), and the CLI strips any inherited one. The plumbing for a
token exists: when a state carries one, `api` and `ai ask` send it as `X-Reader3-Token`. But
the browser frontend's fetches do not carry the token (`server.py:138`, a known limit of the
008 token), so under a token every UI write would get 401. Prove UI paths token-free; a
token-protected API can only be exercised through `api` / `ai ask`.

Hidden environment knobs (not in `--help`): `VERIFY_READER3_BROWSE` (browse binary),
`VERIFY_READER3_STATE` (state file), `VERIFY_READER3_EVIDENCE_ROOT`, `VERIFY_READER3_VENV_BIN`
(default `.venv/bin`), `VERIFY_READER3_BROWSE_TIMEOUT_S` (default 30),
`VERIFY_READER3_TOOLBAR_WAIT_S` (3), `VERIFY_READER3_MARKER_WAIT_S` (2). Timeouts in seconds:
`VERIFY_READER3_HEALTH_TIMEOUT_S` (60, `up` waiting for `/api/health`),
`VERIFY_READER3_KILL_GRACE_S` (10, SIGTERM to SIGKILL), `VERIFY_READER3_PROBE_TIMEOUT_S` (10,
doctor's health probe), `VERIFY_READER3_INGEST_TIMEOUT_S` (600, `book add`),
`VERIFY_READER3_INDEX_TIMEOUT_S` (1800, `book index`), `VERIFY_READER3_STUB_READY_TIMEOUT_S`
(10, the stub's startup wait). `VERIFY_READER3_STUB_MODULE` points the stub runner at a different
stub file and executes it: it exists for the unit tests, so leave it unset.

## Gotchas

- **Google Fonts.** The `<head>` of both `reader.html` and `library.html` links
  `fonts.googleapis.com`/`fonts.gstatic.com`. The e2e `context` fixture
  (`tests/e2e/conftest.py`, around line 290) aborts every non-local request. gstack `/browse`
  does not. On a machine without access, `load` can hang for 30 s. Do not rely on `load`:
  after `goto`/`click`, `$B wait` on a specific element (`lib-main`, `rd-viewport iframe`),
  then run Doctor (b). These font requests show up in `$B network`, never in the server log.
- **`/api/health` ≠ reader ready.** Health 200 arrives long before epub.js renders. Use
  `reader state --wait`.
- **`$B frame` is sticky** across calls. A main-page selector after `frame <iframe>` times out
  (5 s each, and the failures cascade). `reader select` always restores `frame main`; after
  any manual `$B frame '...iframe'`, run `$B frame main` yourself before touching the outer page.
- **Ambiguous selectors fail.** `$B wait '[data-testid="lib-book-card"]'` errors with
  "matched multiple elements". Add `[data-book-id=…]`.
- **The progress pill is per section.** `当前阅读至 N%` is `progress.sectionPercent`, so a
  one-page section reads 100%. Book-level progress is `bookPercent`, which is always null today.
- **First-render page total is stale** (#63). Section 6 of a real book reported
  `sectionPage.total=5`, then 7 after one page turn.
- **The toolbar closes after Marker/Wavy/Underline** (PR #28). Reopening it by clicking the
  `mark.annotation` and then pressing Add Note does not attach to that mark: it saved a new
  `type: note` whose quote was only the first character (2/2, 2026-10-01) or was rejected by
  the `create-empty-quote` guard with no request sent (2/2, 2026-10-03). That is 009 debt #70;
  the ledger's F-018 Confirm no longer asks for it. To add a note, use a fresh selection →
  Add Note.
- **The notes panel covers the rail at 1280×720.** With the panel open, `rd-rail-notes` sits
  under `.notes-body` (panel z 40, rail z 30), so `$B click` on it times out after 5 s and a
  user cannot click it either. Close the panel another way (reload, or navigate) and note it.
- **Offline sandbox versus transformers 4.57.3.** The sandbox server and `book index` run
  with `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`. This transformers version calls the Hub
  for a tokenizer check even when the model is cached, so under offline mode it raises
  `OfflineModeIsEnabled`: `book index` fails (`index_failed`, retry with `--allow-download`,
  which only lifts offline for that one child), and inside the server every semantic path
  (`/api/search/<id>?mode=semantic`, `ai ask` against an **indexed** book) answers 500. `ai
  ask` against an unindexed book takes the keyword fallback and works; the fallback matches the
  whole question as a substring of a chapter, so ask with words that are in the text.
- **No `await` in `$B js` code, including selected text.** gstack wraps any multi-line `js`
  that contains the token `await` in an async block without a return, so the output is empty.
  `reader select` and the state/toolbar probes are written without it, but the needle is part
  of the command string: a quote containing the word "await" still trips it (`select_failed`
  with an empty result). Pick another substring. The same applies to `ui inert -- js ...`.
- **Curly quotes in a selection needle** (`’`) did not survive the shell → raw `$B js` round
  trip (NOT FOUND). `reader select` passes the needle as JSON-escaped data, never inside the
  script text, which should avoid this, but that is not yet proven live: pick an ASCII
  substring when you can.
- **Read side effects from the sandbox files** (`fs cat books/<id>/notes.json`): they are the
  persisted truth the API serves. A compound command mixing `$B` and `curl` was refused by the
  permission layer once; `fs` and `api` avoid that.
- **`ui inert` limits (`access_log`).** Any other client's `/api` request between the markers
  counts as caused by the action, so keep other tabs and pollers off the sandbox while
  measuring. Requests to external hosts and to non-`/api` routes (page loads, assets) are not
  in `requests[]`; a navigation shows up only as `url_changed`. A write that lands after the
  `--settle` window is missed: raise `--settle` for slow handlers.
