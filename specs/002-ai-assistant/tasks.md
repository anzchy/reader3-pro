# Tasks: 002 AI Reading Assistant

This checklist turns `spec.md` + `plan.md` + `data-model.md` + `contracts/*.yaml` into implementation tasks. Keep tasks small, dependency-ordered, and mark completed items with `[x]`.

## Phase 0 — Prerequisites & Config Setup

**Note**: This phase handles repository setup before MVP implementation. See plan.md Phase 0 for research outputs (research.md, contracts/).

- [x] Add `config/ai_settings.json` to `.gitignore` (repo-local, secrets not committed)
- [x] Add `config/ai_settings.example.json` (safe example, no keys)
- [x] Implement config loader/saver for `config/ai_settings.json` (defaults when missing)
- [x] Add `book_uuid` mapping support:
  - [x] Read/write `books/{book_folder}/ai_meta.json` with stable `book_uuid`
  - [x] Create `book_uuid → book_folder` resolver (scan `books/*_data/` on startup or lazy-cache)

## Phase 1 (P1) — MVP: RAG Q&A + Summary (Single Provider)

### Backend API (FastAPI)

- [x] Implement `POST /api/ai/summary/{book_uuid}` (contracts: `contracts/ai-api.yaml`)
  - [x] Support `summary_type` (`overview|highlights|background|full`) + `force_regenerate`
  - [x] Return provider/model metadata + `from_cache` flag (cache can be frontend-side for v1)
- [x] Implement `POST /api/ai/question/{book_uuid}` (non-streaming first)
  - [x] Accept `conversation_history` (max 50) from client
  - [x] Return `retrieval_sources` with chapter/title/order for citations
- [x] Implement `POST /api/ai/rag/retrieve` (internal helper endpoint)
  - [x] Load `books/{book_folder}/chroma_db/` and retrieve top-k passages
  - [x] Provide stable chapter references for UI citations
- [x] Implement request queueing for conversation flow:
  - [x] Queue data structure: In-memory FIFO queue per `{book_uuid}:{provider}` key
  - [x] Max 1 concurrent request per book+provider (subsequent requests wait)
  - [x] Max 10 pending requests in queue (11th request returns 429 Too Many Requests)
  - [x] Request timeout: 30s for cloud providers, 60s for Ollama
  - [x] Queue cleanup: Remove stale requests after timeout (log + return 504 Gateway Timeout)
  - [x] Response handling: Dequeue on completion/error, process next queued request
  - [x] Edge case: Client disconnect cancels request and dequeues

### RAG Retrieval

- [x] Reuse existing ChromaDB index from `001-search-features` (`books/{book_folder}/chroma_db/`)
- [x] Define chunk → chapter mapping strategy (store/recover `chapter_order` + `chapter_title`)
- [x] Add fallback behavior when index missing:
  - [x] Clear error message prompting user to index the book
  - [x] Optional: basic keyword fallback (no embeddings) if desired

### Provider (P1 default)

- [ ] Implement one provider end-to-end (recommend: Anthropic) behind a small interface:
  - [ ] `generate_summary(...)`
  - [ ] `answer_question(...)`
- [x] Enforce: API keys are backend-held; never returned to browser

### Reader UI (templates + static JS)

- [x] Add "AI" button to `templates/reader.html` header toolbar
- [x] Add floating AI panel (right side) matching `spec.md` layout:
  - [x] Quick actions: `全书总结`, `书籍亮点`, `背景解读`
  - [x] Message list + input (Enter to send)
  - [x] Provider indicator (provider + model)
- [x] Provide `book_uuid` to the page (data attribute or inline JSON) so JS calls `/api/ai/*/{book_uuid}`
- [x] Implement minimal frontend state (in-memory) + "Clear conversation"

### IndexedDB Persistence (P1)

- [x] Implement IndexedDB schema (per `data-model.md`):
  - [x] `conversations` store (keyed by conversation UUID; indexed by `book_uuid` + `provider`)
  - [x] `summaries` store (cache key: `{book_uuid}:{provider}:{model}`)
- [x] Persist/restore:
  - [x] Per-book + per-provider conversation thread
  - [x] Cached summary per provider/model

### Manual Acceptance (P1)

- [ ] US-001: AI button opens panel; "全书总结" returns within target time on cloud provider
- [ ] US-002: Ask question → answer includes citations (`retrieval_sources`)
- [ ] US-007: Refresh page → conversation restored for the same book/provider

## Phase 2 (P2) — Multi-Provider + Settings + Streaming

### Settings API (FastAPI)

- [x] Implement Settings endpoints (contracts: `contracts/settings-api.yaml`)
  - [x] `GET /api/settings`
  - [x] `PUT /api/settings`
  - [x] `GET /api/settings/providers`
  - [x] `GET/PUT/DELETE /api/settings/providers/{provider_name}`
  - [x] `POST /api/settings/providers/{provider_name}/test`
- [x] Persist settings + keys server-side in `config/ai_settings.json`
- [x] Return `api_key_configured` boolean only (never the key)

### Settings UI (Web)

- [x] Add a Settings page entry point (link/button) and a Settings page UI
- [x] Providers tab:
  - [x] Provider enable/disable toggle + default provider selection
  - [x] Cloud providers: API key input (never displayed after save; show configured state)
  - [x] Model selection + timeout/retry settings
  - [x] Test connection button (uses `/api/settings/providers/{provider_name}/test`)
- [x] Data tab:
  - [x] Clear local conversation cache (IndexedDB)
  - [x] Clear summary cache (IndexedDB)

### Ollama Proxy API (FastAPI)

- [x] Implement:
  - [x] `GET /api/ollama/status` (probe configured base_url)
  - [x] `GET /api/ollama/models` (proxy to `/api/tags`)

### Providers (P2)

- [ ] Define abstract provider interface with method signatures in `ai_service.py`:
  - [ ] `async def generate_summary(book_uuid: str, summary_type: str) -> str`
  - [ ] `async def answer_question(book_uuid: str, question: str, context: List[str]) -> str`
  - [ ] `async def stream_answer(book_uuid: str, question: str, context: List[str]) -> AsyncIterator[str]`
  - [ ] Provider metadata: `name`, `model_name`, `context_window`, `is_local`, `requires_api_key`
- [ ] Add remaining providers behind the same interface (OpenAI, Gemini, OpenRouter, Ollama)
- [ ] Ollama provider implementation:
  - [ ] Use OpenAI-compatible API if possible (`base_url=http://localhost:11434/v1/`)
  - [ ] No API key required; UI should show "No API key required"
  - [ ] Settings UI: show running status + "Refresh Models" (calls `/api/ollama/status` + `/api/ollama/models`)
  - [ ] Ollama UI indicators:
    - [ ] Add provider selector badge showing "🤖 Ollama: QWEN 3 32B" with offline icon
    - [ ] Green/red dot indicator for connection status (running vs not running)
    - [ ] "No API key required" label in settings provider config
    - [ ] Model size display (GB) next to each model in dropdown
  - [ ] Ollama status display:
    - [ ] "✅ Running locally" when connected to http://localhost:11434
    - [ ] "⚠️ Not connected" with setup instructions when unreachable
    - [ ] Installation guide link (brew install ollama + model download commands)
  - [ ] Offline badge in AI panel header when Ollama provider active

### Streaming (SSE)

- [x] Backend streaming support:
  - [x] Add streaming option for `POST /api/ai/question/{book_uuid}?stream=true`
  - [x] Implement SSE response format (data: event chunks)
  - [x] Handle stream errors (timeout, provider failure) with proper SSE error events
- [x] Frontend streaming UI:
  - [x] Implement SSE EventSource parser (chunk/done/error events)
  - [x] Token-by-token rendering (append to message bubble incrementally)
  - [x] Typing indicator (animated "..." while waiting for first token)
  - [x] "Stop" button to cancel generation (abort SSE connection + backend cleanup)
  - [x] Streaming state management (disable input during generation)
  - [x] Error display for mid-stream failures (show partial response + error message)

### Provider Switching UX

- [ ] Provider dropdown in panel header (shows current: "☁️ Claude Sonnet 4" or "🤖 Ollama: QWEN 3 32B")
- [ ] Implement per-provider conversation thread separation:
  - [ ] IndexedDB schema: conversation keyed by `{book_uuid}:{provider}:{model}`
  - [ ] When switching provider: save current thread to IndexedDB, load target provider's thread
  - [ ] Display thread continuity: "Switching to OpenAI (5 messages) from Claude (12 messages)"
  - [ ] Empty thread for new provider/model combination starts fresh
- [ ] Mid-response switching protection:
  - [ ] Detect if AI response is streaming (generation in progress)
  - [ ] Show warning modal: "Response in progress. Switch now and lose partial response?"
  - [ ] Cancel/Confirm buttons (Confirm aborts stream, saves partial response, switches provider)

### Suggested Questions

- [ ] Implement `POST /api/ai/suggested-questions/{book_uuid}` (no `api_key` in request)
- [ ] UI: show 3–5 suggested questions after answers; click to send

### Retrieval Routing (Long-Context vs RAG)

- [ ] Implement routing logic in `rag_service.py`:
  - [ ] Define context window thresholds per provider (Claude: 1M tokens, GPT-4: 128K, Gemini: 2M, Ollama: model-dependent)
  - [ ] Calculate book/chapter token count (use tiktoken or approximate: chars/4)
  - [ ] Decision heuristics:
    - [ ] If book_tokens < (provider_context_window * 0.5): use long-context (send full book)
    - [ ] If chapter_tokens < (provider_context_window * 0.3): use multi-chapter context
    - [ ] Else: use RAG retrieval (top-k passages, default k=5)
  - [ ] Model name pattern matching for long-context detection:
    - [ ] Claude models with "claude-" → check context_window metadata
    - [ ] Gemini "gemini-1.5-pro" → 2M tokens
    - [ ] Ollama "qwen2.5-1m" → 1M tokens (parse from model name)
  - [ ] Log routing decision (DEBUG level): "Using long-context for book_uuid={uuid}, tokens={count}, provider={name}"
  - [ ] Fallback to RAG on provider timeout (long-context requests may be slower)

### Export / Import

- [ ] Settings export/import:
  - [ ] `GET /api/settings/export` excludes API keys
  - [ ] `POST /api/settings/import` merges settings (keys re-entered manually)
- [ ] Conversation export:
  - [ ] Frontend: Export current book+provider thread to JSON format (client-side download)
  - [ ] Frontend: Export current book+provider thread to plain text format (client-side download)
  - [ ] Backend (optional): `GET /api/ai/conversations/{book_uuid}/export?provider={name}&format=json|text`

### Manual Acceptance (P2)

- [ ] Provider switching works across all providers with no crashes
- [ ] Ollama:
  - [ ] Status check + model list work
  - [ ] Offline Q&A works end-to-end
- [ ] Streaming shows incremental tokens and can be canceled

## Phase 3 (P3) — Polish, Limits, and Hardening

- [ ] Add basic rate limit (spec: ~1 request / 2s per user) + friendly error messages
- [ ] Add quota/cleanup policy for IndexedDB (warn at ~80%; clear old data)
- [ ] Improve citations UI:
  - [ ] Make chapter references clickable links
  - [ ] Determine behavior: scroll to chapter start or attempt passage-level scroll (acceptance criteria TBD)
  - [ ] Highlight cited passage if chapter order + position available
- [ ] Accessibility:
  - [ ] Keyboard navigation (Tab through panel, Enter to send, Esc to close)
  - [ ] Focus trapping when panel open (Tab stays within panel)
  - [ ] ARIA labels for buttons, inputs, status indicators
  - [ ] Screen reader announcements for AI responses
- [ ] Mobile layout rules:
  - [ ] Responsive breakpoints: Desktop (>1024px), Tablet (768-1024px), Mobile (<768px)
  - [ ] Desktop: Floating panel (400px width, right side)
  - [ ] Tablet: Slide-in panel (50% width, overlay with backdrop)
  - [ ] Mobile: Full-screen overlay (100% width/height, slide up animation)
- [ ] Search within conversation (local-only, basic keyword highlight)
- [ ] Browser compatibility validation:
  - [ ] Test on Chrome 88+, Firefox 87+, Safari 14+
  - [ ] Verify IndexedDB, Fetch API, EventSource support
  - [ ] Document unsupported browsers (IE, older versions)
- [ ] IndexedDB storage monitoring:
  - [ ] Estimate current usage via `navigator.storage.estimate()`
  - [ ] Show storage usage in Settings → Data tab
  - [ ] Warning banner at 80% quota
  - [ ] Auto-cleanup: Conversations older than 30 days (configurable)

## Documentation

- [x] Update `README.md` with:
  - [x] How AI works (RAG + citations)
  - [x] Ollama setup steps + offline usage
  - [x] How to configure providers via `config/ai_settings.json`
- [x] Update `CLAUDE.md` with AI feature section:
  - [x] AI assistant commands and endpoints
  - [x] Provider configuration guide
  - [x] Troubleshooting common issues (Ollama not running, API key errors)

## New Requirements: Multi-Chat + On-Disk Storage

- [x] Add on-disk conversation storage under `books/{book_folder}/ai_conversations/` (JSON per conversation)
- [ ] (Optional) Add project-root conversation mirror under `conversations/{book_uuid}/` (configurable via `preferences.conversation_disk_storage`)
- [x] Add Conversation APIs:
  - [x] `GET /api/ai/conversations/{book_uuid}?provider=...` (list threads)
  - [x] `GET /api/ai/conversations/{book_uuid}/{conversation_id}` (load thread)
  - [x] `PUT /api/ai/conversations/{book_uuid}/{conversation_id}` (save thread)
  - [x] `DELETE /api/ai/conversations/{book_uuid}/{conversation_id}` (optional)
- [x] Update AI panel UI:
  - [x] Add thread list UI (show history)
  - [x] Add "New chat" button (creates new thread without deleting history)
  - [x] Persist thread changes to disk JSON via Conversation APIs
