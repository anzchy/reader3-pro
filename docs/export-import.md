# Export / Import

## Settings export/import

The server stores provider settings in `config/ai_settings.json` (gitignored). Export/import is designed to **exclude API keys**.

- Export (no keys): `GET /api/settings/export`
- Import (merge; keys not imported): `POST /api/settings/import`

Notes:
- Import merges into the current settings.
- API keys are never imported; re-enter them in the Settings UI after import.

## Conversation export (per thread)

Conversations are multi-threaded per book+provider. Export targets a specific `conversation_id`.

- Endpoint: `GET /api/ai/conversations/{book_uuid}/{conversation_id}/export?format=...`
- Formats:
  - `json`: raw thread JSON (same schema as on-disk `ai_conversations/*.json`)
  - `text`: simple transcript (`User:` / `Assistant:`)
  - `md`: Markdown transcript with metadata header

The Reader UI includes an **Export** control in the AI panel header.

## Library export (018 WI-6)

One JSON download of the whole library. The route is in `src/reader3_app/web/routers/library_export.py`.

- Endpoint: `GET /api/library/export` (default: no conversations) or `GET /api/library/export?include=conversations`
- Response: `200`, a single JSON body (not streamed, no size cap) with `Content-Disposition: attachment; filename="reader3-library.json"`
- Body: `{"books": [...]}` and nothing else (no `exported_at`, no `schema_version`). Order = `search_service.list_book_ids`, the same order as `GET /api/library`.
- Chapter text is never exported: the EPUB is the source of the text, and this export is not a backup.

### Entries

A readable book is the same entry `GET /api/library` returns (`book_id`, `title`, `authors`, `cover_url`, `book_uuid`, built by the same function), plus:

- `annotations`: list of `Annotation.to_dict()` objects from `notes.json`; `null` if `notes.json` cannot be read. A book with no `notes.json` has `[]`.
- `component_errors`: always present, may be `[]`. Shapes:
  - `{"component": "annotations"}`: `notes.json` is unreadable.
  - `{"component": "conversations", "conversation_id": "<file stem>"}`: one conversation file is unreadable (non-UTF-8, bad JSON, not an object, invalid `conversation_id`, or a per-file `OSError`). Reported once even if both sources have a bad copy.
  - `{"component": "conversations"}`: a whole conversation source could not be read: the project root cannot be resolved, a source directory raises a non-`FileNotFoundError` `OSError` (e.g. permission denied), or `ai_meta.json` exists but has no valid uuid. A source directory that does not exist is not an error.
- `conversations`: only with `?include=conversations`. Thread objects exactly as stored on disk (unknown keys kept, timestamps not back-filled, messages included).

A book whose `book.pkl` cannot be read is exactly `{"book_id": "...", "error": "unreadable"}`: no annotations, conversations, uuid or `component_errors` are read for it.

### `include` grammar

- Absent → no conversations.
- Exactly one value, case-insensitive `conversations` → conversations included.
- Anything else (empty value, repeated parameter, comma list, other words) → `400 {"detail": "include must be \"conversations\""}`.

### Conversation sources and dedupe

Sources follow what is on disk, not the current conversation storage mode:

1. Per-book: `books/{book_id}/ai_conversations/`, always read.
2. Project-root: `{project conversations root}/{book_uuid}/` (default root `conversations/`), read when the root resolves and the book has a valid uuid.

The same `conversation_id` in both sources is exported once: the copy with the strictly newer `last_updated` wins (a non-string value compares as `""`); on a tie the project-root copy wins. The file stem is the conversation's identity; a payload `conversation_id` that differs from the file name is not reconciled yet (deferred).

### Read-only

The export takes no book lock and never mints a uuid: `book_uuid` comes from `book_lock.read_book_uuid`. A book whose `ai_meta.json` is absent, unreadable, or holds a malformed uuid is exported with `book_uuid: null` and a server WARNING. (For an absent file `GET /api/library` would mint one, so the two can differ in this field.) A malformed uuid is never used to build a project-root path, so that source is unresolvable for the book; with `include=conversations` and an `ai_meta.json` that exists but cannot be used, the entry carries `{"component": "conversations"}`. An absent `ai_meta.json` adds no error.

### Books that change during the export

- A book that vanishes after enumeration (directory gone while its entry is read) is skipped, not reported.
- A single conversation file that vanishes between listing and reading is silently left out while the book is still there.
- Only a failure to enumerate the library itself is a `500`. Every other failure is per entry or per component, as above.

### UI

The Settings page **导出书库 JSON** button requests the default export (no conversations) and downloads it as `reader3-library.json`. Success shows 「书库已导出。」; failure shows 「导出书库失败：…」. There is no UI toggle for `include=conversations` yet (deferred to 014 or later); use the endpoint directly.
