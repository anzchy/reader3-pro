# Tasks: 002 AI Reading Assistant

This checklist turns `spec.md` + `plan.md` + `data-model.md` + `contracts/*.yaml` into implementation tasks. Keep tasks small, dependency-ordered, and mark completed items with `[x]`.

## Phase 0 — Repo & Config Wiring

- [ ] Add `config/ai_settings.json` to `.gitignore` (repo-local, secrets not committed)
- [ ] Add `config/ai_settings.example.json` (safe example, no keys)
- [ ] Implement config loader/saver for `config/ai_settings.json` (defaults when missing)
- [ ] Add `book_uuid` mapping support:
  - [ ] Read/write `books/{book_folder}/ai_meta.json` with stable `book_uuid`
  - [ ] Create `book_uuid → book_folder` resolver (scan `books/*_data/` on startup or lazy-cache)

## Phase 1 (P1) — MVP: RAG Q&A + Summary (Single Provider)

### Backend API (FastAPI)

- [ ] Implement `POST /api/ai/summary/{book_uuid}` (contracts: `contracts/ai-api.yaml`)
  - [ ] Support `summary_type` (`overview|highlights|background|full`) + `force_regenerate`
  - [ ] Return provider/model metadata + `from_cache` flag (cache can be frontend-side for v1)
- [ ] Implement `POST /api/ai/question/{book_uuid}` (non-streaming first)
  - [ ] Accept `conversation_history` (max 50) from client
  - [ ] Return `retrieval_sources` with chapter/title/order for citations
- [ ] Implement `POST /api/ai/rag/retrieve` (internal helper endpoint)
  - [ ] Load `books/{book_folder}/chroma_db/` and retrieve top-k passages
  - [ ] Provide stable chapter references for UI citations
- [ ] Add minimal request queueing (max 1 in-flight per book+provider) to avoid overlapping responses

### RAG Retrieval

- [ ] Reuse existing ChromaDB index from `001-search-features` (`books/{book_folder}/chroma_db/`)
- [ ] Define chunk → chapter mapping strategy (store/recover `chapter_order` + `chapter_title`)
- [ ] Add fallback behavior when index missing:
  - [ ] Clear error message prompting user to index the book
  - [ ] Optional: basic keyword fallback (no embeddings) if desired

### Provider (P1 default)

- [ ] Implement one provider end-to-end (recommend: Anthropic) behind a small interface:
  - [ ] `generate_summary(...)`
  - [ ] `answer_question(...)`
- [ ] Enforce: API keys are backend-held; never returned to browser

### Reader UI (templates + static JS)

- [ ] Add “AI” button to `templates/reader.html` header toolbar
- [ ] Add floating AI panel (right side) matching `spec.md` layout:
  - [ ] Quick actions: `全书总结`, `书籍亮点`, `背景解读`
  - [ ] Message list + input (Enter to send)
  - [ ] Provider indicator (provider + model)
- [ ] Provide `book_uuid` to the page (data attribute or inline JSON) so JS calls `/api/ai/*/{book_uuid}`
- [ ] Implement minimal frontend state (in-memory) + “Clear conversation”

### IndexedDB Persistence (P1)

- [ ] Implement IndexedDB schema (per `data-model.md`):
  - [ ] `conversations` store (keyed by conversation UUID; indexed by `book_uuid` + `provider`)
  - [ ] `summaries` store (cache key: `{book_uuid}:{provider}:{model}`)
- [ ] Persist/restore:
  - [ ] Per-book + per-provider conversation thread
  - [ ] Cached summary per provider/model

### Manual Acceptance (P1)

- [ ] US-001: AI button opens panel; “全书总结” returns within target time on cloud provider
- [ ] US-002: Ask question → answer includes citations (`retrieval_sources`)
- [ ] US-007: Refresh page → conversation restored for the same book/provider

## Phase 2 (P2) — Multi-Provider + Settings + Streaming

### Settings API (FastAPI)

- [ ] Implement Settings endpoints (contracts: `contracts/settings-api.yaml`)
  - [ ] `GET /api/settings`
  - [ ] `PUT /api/settings`
  - [ ] `GET /api/settings/providers`
  - [ ] `GET/PUT/DELETE /api/settings/providers/{provider_name}`
  - [ ] `POST /api/settings/providers/{provider_name}/test`
- [ ] Persist settings + keys server-side in `config/ai_settings.json`
- [ ] Return `api_key_configured` boolean only (never the key)

### Settings UI (Web)

- [ ] Add a Settings page entry point (link/button) and a Settings page UI
- [ ] Providers tab:
  - [ ] Provider enable/disable toggle + default provider selection
  - [ ] Cloud providers: API key input (never displayed after save; show configured state)
  - [ ] Model selection + timeout/retry settings
  - [ ] Test connection button (uses `/api/settings/providers/{provider_name}/test`)
- [ ] Data tab:
  - [ ] Clear local conversation cache (IndexedDB)
  - [ ] Clear summary cache (IndexedDB)

### Ollama Proxy API (FastAPI)

- [ ] Implement:
  - [ ] `GET /api/ollama/status` (probe configured base_url)
  - [ ] `GET /api/ollama/models` (proxy to `/api/tags`)

### Providers (P2)

- [ ] Add remaining providers behind the same interface (OpenAI, Gemini, OpenRouter, Ollama)
- [ ] Ollama:
  - [ ] Use OpenAI-compatible API if possible (`base_url=http://localhost:11434/v1/`)
  - [ ] No API key required; UI should show “No API key required”
  - [ ] Settings UI: show running status + “Refresh Models” (calls `/api/ollama/status` + `/api/ollama/models`)

### Streaming (SSE)

- [ ] Add streaming option for `POST /api/ai/question/{book_uuid}?stream=true`
- [ ] Implement SSE parsing/rendering in the UI (chunk/done/error events)
- [ ] Add “Stop” button to cancel generation

### Provider Switching UX

- [ ] Provider dropdown in panel header
- [ ] Switching provider changes the active thread (history persists per provider)
- [ ] Optional warning if switching mid-response

### Suggested Questions

- [ ] Implement `POST /api/ai/suggested-questions/{book_uuid}` (no `api_key` in request)
- [ ] UI: show 3–5 suggested questions after answers; click to send

### Retrieval Routing (Long-Context vs RAG)

- [ ] Implement routing per `research.md`:
  - [ ] Prefer long-context for supported models (heuristic by model name and/or provider metadata)
  - [ ] Fallback to RAG (top-k passages) for typical context windows
  - [ ] Enforce max context size and friendly errors/timeouts (esp. Ollama)

### Export / Import

- [ ] Settings export/import:
  - [ ] `GET /api/settings/export` excludes API keys
  - [ ] `POST /api/settings/import` merges settings (keys re-entered manually)
- [ ] Conversation export:
  - [ ] Export current book+provider thread to JSON/text (client-side)

### Manual Acceptance (P2)

- [ ] Provider switching works across all providers with no crashes
- [ ] Ollama:
  - [ ] Status check + model list work
  - [ ] Offline Q&A works end-to-end
- [ ] Streaming shows incremental tokens and can be canceled

## Phase 3 (P3) — Polish, Limits, and Hardening

- [ ] Add basic rate limit (spec: ~1 request / 2s per user) + friendly error messages
- [ ] Add quota/cleanup policy for IndexedDB (warn at ~80%; clear old data)
- [ ] Improve citations UI (chapter link/scroll-to if feasible)
- [ ] Accessibility: keyboard navigation, focus trapping, ARIA labels
- [ ] Mobile layout rules (panel behavior on tablet/mobile)
- [ ] Search within conversation (local-only, basic keyword highlight)

## Documentation

- [ ] Update `README.md` with:
  - [ ] How AI works (RAG + citations)
  - [ ] Ollama setup steps + offline usage
  - [ ] How to configure providers via `config/ai_settings.json`
