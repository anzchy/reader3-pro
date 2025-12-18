# Storage & Data Locations

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

## RAG index (ChromaDB)

- **Per book**: `books/{book_id}/chroma_db/`
- This is created by indexing (Library UI or `uv run reader3 --index {book_id}`).
