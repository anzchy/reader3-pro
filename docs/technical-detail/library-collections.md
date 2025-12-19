# Library Collections (004)

## Overview

Collections are user-defined groupings of processed book folders (e.g. `dracula_data`) used by the Library UI for scoping and bulk actions.

## Storage

- **File**: `config/library_collections.json` (gitignored)
- **Write strategy**: atomic write (temp file + `os.replace`)
- **Schema version**: `1`

Top-level shape:

```json
{
  "schema_version": 1,
  "collections": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Science Fiction",
      "created_at": "2025-12-19T10:00:00+00:00",
      "book_ids": ["dune_data", "foundation_data"]
    }
  ]
}
```

## API Endpoints

- `GET /api/collections` → list collections
- `POST /api/collections` → create
- `GET /api/collections/{collection_id}` → get
- `PUT /api/collections/{collection_id}` → rename
- `POST /api/collections/{collection_id}/books` → add/remove books
- `DELETE /api/collections/{collection_id}` → delete

## Scope Strings (Library UI)

- `all`
- `format:epub`
- `format:pdf` (placeholder; PDFs not supported yet)
- `collection:<uuid>`

These scopes are used by:

- Library UI filtering
- `GET /api/library/stats?scope=...`

## Validation & Security

- Collection names are validated server-side (length + allowed characters) and rendered safely.
- Book IDs are treated as folder names and validated to prevent path traversal.

