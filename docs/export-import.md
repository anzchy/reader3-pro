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
