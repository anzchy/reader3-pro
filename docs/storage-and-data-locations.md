# Storage & Data Locations

## Book folder naming

In this document, `book_id` refers to the processed folder name (e.g. `dracula_data`) stored under `books/`.

## Browser storage (IndexedDB)

- **DB name**: `reader3_ai_assistant`
- **Object stores**:
  - `conversations` (chat threads per book/provider)
  - `summaries` (cached summaries)
- **Note**: IndexedDB is stored under the browser’s profile directory and keyed by site origin (e.g. `http://127.0.0.1:8123`). It is **not** stored inside this repo.

### macOS physical locations (typical)

- Chrome: `~/Library/Application Support/Google/Chrome/Default/IndexedDB/`
- Edge: `~/Library/Application Support/Microsoft Edge/Default/IndexedDB/`
- Brave: `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/IndexedDB/`
- Firefox: `~/Library/Application Support/Firefox/Profiles/<profile>/storage/default/<origin>/idb/`
- Safari: `~/Library/Containers/com.apple.Safari/Data/Library/WebKit/WebsiteData/IndexedDB/`

### How to inspect (recommended)

- Chrome/Edge/Brave DevTools → **Application** → **IndexedDB** → `reader3_ai_assistant`
- Safari → Develop menu → Web Inspector → Storage

## Browser storage (localStorage)

The UI stores small UI preferences in localStorage:

- `reader3.library.viewMode`: `grid` or `list`
- `reader3.library.rightPanelCollapsed`: `true` or `false` for the right panel state
- `reader3.library.bulkIndexingActive`: `true` while bulk indexing is running (used to show an interrupted hint after reload)
- `reader3.ai.model.{book_uuid}.{provider}`: last selected AI model per book/provider
- `reader3.ai.activeConversation.{book_uuid}.{provider}`: active AI conversation id per book/provider
- `reader3-ai-panel-width`: AI sidebar width in pixels (reader view)
- `reader3-font-settings`: JSON `{ "fontSize": number, "lineHeight": number }` for reader font settings

## Browser storage (sessionStorage)

Search panels persist the last query and results for the current tab:

- `reader3.search.reader.{book_id}`: JSON `{ q, caseSensitive, mode, results, statusMessage }`
- `reader3.search.library`: JSON `{ payload, q, caseSensitive, sortBy, mode }`

## Server-side on-disk storage (conversations)

The AI assistant persists chat threads as JSON on disk so they are portable between browsers/machines.

### Default (per-book)

- **Directory**: `books/{book_id}/ai_conversations/`
- **Files**: `books/{book_id}/ai_conversations/{conversation_id}.json`

Each file corresponds to one chat thread (conversation id is a UUID).

### Optional mirror (project root)

If enabled, the server also writes a mirror copy:

- **Directory**: `conversations/{book_uuid}/`
- **Files**: `conversations/{book_uuid}/{conversation_id}.json`

Enable via `config/ai_settings.json`:

```json
{
  "preferences": {
    "conversation_disk_storage": "project_root",
    "conversation_project_root_dir": "conversations"
  }
}
```

Valid values for `conversation_disk_storage`:
- `per_book` (default)
- `project_root`
- `both`

`conversations/` is ignored by git via `.gitignore`.

## Server-side settings file

- AI settings (including provider API keys): `config/ai_settings.json` (gitignored)
- Example template: `config/ai_settings.example.json`

## Server-side library collections (004)

User-defined Collections are persisted on disk as a gitignored JSON file:

- **File**: `config/library_collections.json` (gitignored)
- **Owner**: server (FastAPI); written via Collections API endpoints (see spec `004-library-bulk-indexing`)
- **Schema**: `{ schema_version: 1, collections: [...] }`

## RAG index (ChromaDB)

- **Per book**: `books/{book_id}/chroma_db/`
- This is created by indexing (Library UI or `uv run reader3 --index {book_id}`).

## Processed book assets

The EPUB ingestion pipeline writes processed outputs per book:

- **Pickled book**: `books/{book_id}/book.pkl` (parsed spine + metadata)
- **Original EPUB copy**: `books/{book_id}/book.epub` (source file for epub.js rendering, served at `/read/{book_id}/book.epub`)
- **Extracted images**: `books/{book_id}/images/`

## Reader rendering sources

- Frontend reader renders content from `book.epub` via epub.js (iframe).
- Backend uses `book.pkl` for metadata, TOC/spine structure, search indexing, and notes grouping.

## Book notes & annotations (003)

Persistent highlights/underlines/notes are stored per book as JSON.

- **File**: `books/{book_id}/notes.json`
- **Schema**: `{ schema_version: 1, book_id, annotations: [...] }`
- **Annotation fields**: `quote`, `prefix`, `suffix`, `position`, optional `cfi` (epub.js anchor), optional `color` (marker/underline/wavy)

### Related API endpoints

- `GET /api/notes/{book_id}` (all notes for a book, grouped by chapter)
- `GET /api/notes/{book_id}/{chapter_index}` (notes for one chapter)
- `POST /api/notes/{book_id}/{chapter_index}` (create annotation)
- `PUT /api/notes/{book_id}/{chapter_index}/{note_id}` (update a note's `note_text`)
- `DELETE /api/notes/{book_id}/{chapter_index}/{note_id}` (delete annotation; optional in v1)

### Write contract: optimistic concurrency (011 WI-5a)

Versions travel in headers: `ETag` out, `If-Match` in.

- **The version is per book, not per note or per chapter.** It is computed over the whole
  `annotations` list, so *any* write to the book advances it. Both GET routes return the same
  value; a client only ever needs to keep one.
- **Every route that touches notes returns an `ETag`** — both GETs, `POST` (201), `PUT` (200)
  and `DELETE` (204, header only). It is a strong ETag: the bare version quoted, e.g. `"7f3a…"`.
  Clients echo it back verbatim.
- **`If-Match` is optional.** A request without it is byte-for-byte what it was before optimistic
  concurrency existed — same status, same body. That is how ADR-0011 (API v1 freeze) is honoured
  here, and why `tests/contract` did not change. A request *with* it buys a real
  compare-and-swap, performed inside the book-level write lock — never in the route, or two
  requests would both pass the check and then overwrite each other in turn.
- **409 on a stale `If-Match`**, with a body the conflict UI needs:

  ```json
  { "detail": "Annotation version conflict", "etag": "\"<current version>\"", "annotation": { … } }
  ```

  `annotation` is the server's **current** copy of that note, with `note_text` HTML-unescaped
  the same way GET returns it — the dialog has to show the user what someone actually typed.
  It is `null` when there is no such single record to show (creating an annotation via `POST`).
  Without it the client can only display its own version, and the user would be choosing blind.

The browser half of this contract lives in `static/js/annotations.js`: the last seen `ETag`
is remembered and sent on every write; a conflict raises the DEG-S5 dialog (keep mine / take
remote) instead of silently discarding either version. Note that the text currently *shown* in
the editor is pinned to the version it came from, separately from the last `ETag` merely read —
otherwise a settled conflict could be saved against a newer version and silently overwrite it.
