# AI Reading Assistant (002) — Developer Quickstart

**Date**: 2025-12-18  
**Prereqs**: Read [spec.md](./spec.md), [plan.md](./plan.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

This quickstart focuses on **what needs to exist** for 002 to work in this repo:

- Books live under `books/*_data/`
- Semantic retrieval reuses the existing per-book ChromaDB index (`books/{book_folder}/chroma_db/`)
- AI provider API keys are **backend-held** (server-side config/env), never stored in the browser
- AI endpoints use **`book_uuid`** (UUID) — the server maps UUID ↔ book folder

---

## 0) Install + run the base app

```bash
uv sync
uv run server.py
```

Open `http://127.0.0.1:8123`.

---

## 1) Add a new EPUB (from scratch)

```bash
uv run reader3.py path/to/book.epub
```

This creates `books/{basename}_data/` containing:

- `book.pkl`
- `images/`

---

## 2) Ensure semantic index exists (for RAG mode)

Index a single book:

```bash
uv run reader3.py --index The-Cold-Start-Problem_data
```

Index all books:

```bash
for d in books/*_data; do
  uv run reader3.py --index "$(basename "$d")"
done
```

You should see `books/*_data/chroma_db/` created per indexed book.

---

## 3) Configure AI providers (server-side)

002 is designed so that **API keys never reach the browser**. You can support either:

### Option A — Environment variables (simple for development)

```bash
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

### Option B — Local config file (recommended for a Settings UI)

Create `config/ai_settings.json` (gitignored) and have the server load it:

```json
{
  "default_provider": "anthropic",
  "providers": {
    "anthropic": { "enabled": true, "model_name": "claude-sonnet-4", "api_key": "..." },
    "ollama": { "enabled": true, "base_url": "http://localhost:11434", "model_name": "qwen3:32b" }
  }
}
```

The Settings page (if implemented) should call `contracts/settings-api.yaml` endpoints to update this server-side config.

---

## 4) Ollama (local, offline)

Install + run Ollama:

```bash
brew install ollama
ollama serve
ollama pull qwen3:32b
curl http://localhost:11434/api/tags
```

002 should use backend proxy endpoints (see `contracts/ollama-api.yaml`) to check status and list models:

- `GET /api/ollama/status`
- `GET /api/ollama/models`

---

## 5) How the AI panel gets the current book (UUID mapping)

The reader URL uses the existing folder-based id (e.g. `/read/{book_folder}/{chapter_index}`), but AI endpoints use `book_uuid`.

Recommended wiring:

1. Server resolves `book_folder -> book_uuid` (from a local mapping or per-book sidecar metadata).
2. Server injects `book_uuid` into `templates/reader.html` so frontend JS can call:
   - `POST /api/ai/summary/{book_uuid}`
   - `POST /api/ai/question/{book_uuid}`

Recommended storage:
- `books/{book_folder}/ai_meta.json` containing `{ "book_uuid": "..." }`

---

## 6) Manual smoke checks

- Open any book in the reader
- Open AI panel
- Generate “全书总结”
- Ask a question and verify it returns:
  - an `answer`
  - `retrieval_sources` (in RAG mode)
- Switch provider (cloud ↔ ollama) and verify:
  - request succeeds
  - conversation persists in IndexedDB
