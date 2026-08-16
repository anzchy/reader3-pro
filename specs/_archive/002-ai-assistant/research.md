# Research Findings: AI Reading Assistant (002)

**Date**: 2025-12-18  
**Status**: Phase 0 Complete  
**References**: [spec.md](./spec.md), [plan.md](./plan.md), [data-model.md](./data-model.md)

This document captures research decisions aligned with the chosen options:

- **Book identity**: AI uses `book_uuid` (UUID)
- **API keys**: stored on the **server** (backend-held)
- **Retrieval**: **long-context when supported**, otherwise **RAG** (ChromaDB)

---

## 1) Multi-provider integration pattern (backend)

### Decision

Use a small provider abstraction in Python with a common interface:

- `generate_summary(book_context, ...) -> SummaryPayload`
- `answer(question, context, history, ...) -> AnswerPayload`
- Optional streaming support where available

### Rationale

- Keeps provider-specific quirks isolated
- Allows consistent error handling + retries
- Makes switching providers a UI-level decision (same backend contract)

### Notes

- **Ollama** can be called either via:
  - OpenAI-compatible endpoint (`http://localhost:11434/v1/...`) using the OpenAI SDK, or
  - native `/api/chat` calls
- Prefer the simplest approach that supports streaming reliably.

---

## 2) Retrieval routing: long-context vs RAG (ChromaDB)

### Decision

Use two modes:

1. **Long-context mode** (preferred when supported):
   - For models with very large context windows (e.g. `qwen2.5-1m:*`), send large context directly:
     - whole book text if it fits, else a large multi-chapter excerpt
2. **RAG mode** (default):
   - Retrieve top-k passages from existing per-book ChromaDB index (`books/{book_folder}/chroma_db/`)
   - Provide retrieved passages + citations to the LLM

### Rationale

- Long-context mode improves global summarization quality (less “lost context”)
- RAG keeps latency and token usage reasonable for typical models

### Practical heuristic (suggested)

- If provider model name indicates “long context” (e.g. contains `-1m`), enable long-context mode.
- Otherwise use RAG mode with `k=5` passages.

---

## 3) Chunking/index compatibility

### Decision

Reuse the existing semantic index from `001-search-features`:

- Chunking is character-based (current implementation): ~1000 chars with overlap
- Stored per book under `books/{book_folder}/chroma_db/`

### Rationale

- Avoids re-indexing and duplicate vector stores
- Keeps the system filesystem-based and self-contained

---

## 4) Server-side settings + secrets

### Decision

Store provider API keys on the server (never in the browser):

- Use a local config file (recommended) or environment variables
- Settings API endpoints update provider configs and persist them server-side

### Rationale

- Keeps secrets out of IndexedDB/browser storage
- Matches self-hosted single-user deployment assumptions
- Simplifies threat model (no client-side crypto complexity)

---

## 5) Streaming responses

### Decision

Support streaming in the UI where possible. Recommended transport:

- **SSE** (Server-Sent Events) from backend to browser, with provider streaming underneath

Fallback:

- Non-streaming response (single JSON payload) when provider/stack doesn’t support streaming

---

## 6) Book UUID mapping

### Decision

AI endpoints use `book_uuid` (UUID) and the server maps to `book_folder`.

Recommended implementation:

- Per-book sidecar metadata file under `books/{book_folder}/ai_meta.json` containing `{ "book_uuid": "..." }`

Optional optimization:

- A global mapping file (e.g. `books/book_index.json`) built by scanning `books/*_data/` for faster startup

---

## 7) Risks / gotchas

- Long-context mode can exceed memory/time limits on local models; add timeouts and show helpful errors.
- RAG quality depends heavily on index quality; ensure books are indexed before expecting good citations.
- UUID mapping must be stable; if you regenerate UUIDs, cached conversations/summaries won’t match.
