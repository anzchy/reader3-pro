# Implementation Plan: AI Reading Assistant

**Branch**: `002-ai-assistant` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-ai-assistant/spec.md`

## Summary

Implement an AI-powered reading assistant for EPUB books that provides intelligent summarization and conversational Q&A using RAG (Retrieval-Augmented Generation) technology. The feature adds an "AI" button to the reader interface that opens a floating chat panel, supporting multiple AI providers (Claude, OpenAI, Gemini, Ollama, OpenRouter) with persistent conversation history and secure API key storage. The UI closely matches the reference design from Google NotebookLM with quick action buttons (全书总结, 书籍亮点, 背景解读) and suggested questions.

**Technical Approach**: Leverage existing ChromaDB vector embeddings from 001-search-features for RAG, implement browser-side IndexedDB for persistent storage (conversations, cached summaries), store AI provider API keys on the server (self-hosted single-user), support long-context models by optionally sending large chapter/book context directly (fallback to RAG retrieval for other models), and queue concurrent requests for sequential processing.

## Technical Context

**Language/Version**: Python 3.10+ (backend), JavaScript ES6+ (frontend)
**Primary Dependencies**:
- Backend: FastAPI, ChromaDB (existing), sentence-transformers (existing)
- Frontend: IndexedDB API (browser built-in)
- AI Providers: anthropic SDK, openai SDK, google-generativeai SDK, ollama Python client

**Storage**:
- IndexedDB (browser): Conversation history, cached summaries
- Filesystem (server): Provider configuration + API keys (local config file, not committed)
- ChromaDB (existing): Vector embeddings for RAG retrieval
- Filesystem: book.pkl files (existing)

**Testing**: pytest for backend, manual testing for frontend (no JS test framework per Simplicity principle)

**Target Platform**: Web browser (Chrome/Firefox/Safari latest), Python 3.10+ server

**Project Type**: Web application (FastAPI backend + vanilla JavaScript frontend)

**Performance Goals**:
- Initial summary generation: <10 seconds (cloud providers), <20 seconds (Ollama) (SC-001)
- Q&A responses: <5 seconds @ 95th percentile (cloud), <10 seconds (Ollama) (SC-002)
- RAG retrieval: <500ms for semantic search
- UI responsiveness: <100ms for panel open/close
- Ollama first token latency: 150-400ms (model dependent)
- Ollama throughput: 18-60 tokens/sec (hardware dependent)

**Constraints**:
- Context window limits: use RAG retrieval by default; allow long-context models to consume larger chapter/book context directly
- IndexedDB storage: ~50MB typical (browser dependent, warn at 80% quota)
- AI API timeouts: 30 seconds (cloud), 60 seconds (Ollama for local inference)
- Book size: Target <500 pages, handle up to 1000+ via chunking
- **Ollama hardware requirements (recommended)**:
  - RAM: 32GB minimum, 64GB recommended
  - GPU: 24GB VRAM (NVIDIA RTX 3090) or Apple M2 32GB unified memory
  - Storage: 20-50GB for models (qwen3:32b = 19.8GB, qwen3:8b = 4.5GB)

**Scale/Scope**:
- Single-user self-hosted deployment
- ~10-50 books in library
- ~100-500 messages per conversation
- 5 AI provider integrations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Data Structures First ✅

**Compliance**: All entities defined as Python dataclasses in spec.md Key Entities section:
- `AIConversation`: Persistent chat session with message history
- `AIMessage`: Single message with timestamp, role, content
- `AIProviderConfig`: AI provider configuration (API keys stored server-side)
- `BookSummary`: Cached summary with metadata
- `AISettings`: Global configuration

**Action**: Define these dataclasses in `ai_models.py` before implementation.

### Principle II: Simplicity Over Engineering ⚠️ JUSTIFIED COMPLEXITY

**Potential Violation**: Adding IndexedDB and request queueing

**Justification**:
- IndexedDB is browser built-in (no dependency), required for persistent storage (clarification Q3)
- Request queueing is simple in-memory queue (no framework), required for UX (clarification Q4)
- NO new Python backend frameworks - using existing FastAPI

**Verdict**: Justified - complexity comes from requirements, not over-engineering.

### Principle III: File-Based State Management ⚠️ DEVIATION

**Deviation**: Conversation history stored in IndexedDB (browser), not filesystem

**Justification**:
- Conversations are session-specific, user-specific data (not book metadata)
- Browser storage is appropriate for client-side state
- Maintains file-based storage for books (`book.pkl` unchanged)
- Aligns with self-hosted, single-user model

**Verdict**: Acceptable deviation - different data lifecycle from books.

### Principle IV: HTML Content Sanitization ✅

**Compliance**: No new HTML from user input. AI responses are text-only, displayed in pre-sanitized containers. Existing `clean_html_content()` protects book content.

### Principle V: Path Security ✅

**Compliance**: No new file path operations. All API calls use book IDs (validated against existing books), no filesystem traversal from user input.

### Principle VI: Explicit Over Implicit ✅

**Compliance**: All clarifications documented in spec.md Clarifications section. Type hints required for all new functions. Comments explain long-context vs RAG retrieval behavior and queueing logic.

### Principle VII: Performance Through Caching ✅

**Compliance**:
- Summary caching in IndexedDB (FR-028)
- Reuses existing ChromaDB embeddings (FR-020)
- No premature optimization - profile before adding complexity

### Architecture Standards: Two-Step Processing ✅

**Compliance**:
- EPUB processing (`reader3.py`) unchanged
- Web server (`server.py`) adds new API endpoints
- No mixing of processing and serving
- Stateless server design maintained

**GATE RESULT**: ✅ PASS with justified complexity. Proceed to Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/002-ai-assistant/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Phase 0 output (to be created)
├── data-model.md        # Phase 1 output (to be created)
├── quickstart.md        # Phase 1 output (to be created)
├── contracts/           # Phase 1 output (to be created)
│   ├── ai-api.yaml      # AI assistant API endpoints
│   └── settings-api.yaml # Settings page API endpoints
└── tasks.md             # Phase 2 output (/speckit.tasks - not created by plan)
```

### Source Code (repository root)

```text
# Web application structure (FastAPI backend + vanilla JS frontend)

# Backend (Python)
ai_service.py            # NEW: AI provider integrations, request handling
ai_models.py             # NEW: Dataclasses for AI entities
rag_service.py           # NEW: RAG chunking, retrieval logic
server.py                # MODIFIED: Add AI and settings endpoints

# Frontend (JavaScript)
static/
├── ai-panel.js          # NEW: AI chat interface logic
├── ai-panel.css         # NEW: AI panel styling
├── settings.js          # NEW: Settings page logic
├── settings.css         # NEW: Settings page styling
└── indexeddb-manager.js # NEW: IndexedDB persistence layer

templates/
├── reader.html          # MODIFIED: Add AI button, include ai-panel.js/css
├── settings.html        # NEW: Settings page template
└── library.html         # MODIFIED: Add settings link in header

# Testing (optional per constitution)
tests/
└── contract/
    ├── test_ai_api.py   # NEW: Test AI endpoints
    └── test_rag.py      # NEW: Test RAG chunking/retrieval
```

**Structure Decision**: Maintains existing single-project web application structure. New AI functionality added as modules alongside existing search features. No new directories or architectural changes - follows Reader3 Pro's flat, simple structure.

## Complexity Tracking

### Justified Complexity

| Component | Complexity | Justification | Mitigation |
|-----------|-----------|---------------|------------|
| IndexedDB persistence | Browser API with async operations | Required for persistent storage across sessions (clarification Q3) | Use simple wrapper class, document all operations |
| Multi-provider AI integration | 5 different SDK patterns | User requirement for provider flexibility (FR-012) | Abstract common interface, document each provider's quirks |
| Request queueing | In-memory queue + state machine | Required for conversation flow (clarification Q4, FR-018a) | Simple FIFO queue, max 10 pending requests |

### Avoided Complexity

- ❌ No React/Vue framework - vanilla JS per Simplicity principle
- ❌ No backend database - IndexedDB handles client state
- ❌ No WebSocket real-time - polling sufficient for AI responses
- ❌ No service workers - not needed for current scope
- ❌ No OAuth flows - API keys stored server-side per self-hosted model

## Phase 0: Research & Design Questions

### Research Tasks

1. **AI Provider SDK Integration Patterns**
   - **Question**: What are the best practices for integrating multiple AI provider SDKs in Python?
   - **Scope**: anthropic, openai, google-generativeai, ollama clients
   - **Output**: Common interface pattern, error handling strategies
   - **Reference**: Each provider's official Python SDK documentation

2. **RAG Chunking Strategy Validation**
   - **Question**: When should we use long-context (whole-book / multi-chapter) vs RAG retrieval?
   - **Scope**: Heuristics for context size, provider capability flags, retrieval accuracy trade-offs
   - **Output**: Implementation approach for `rag_service.py` routing (long-context vs RAG)
   - **Reference**: Provider context window docs, RAG best practices

3. **IndexedDB Best Practices**
   - **Question**: What are the recommended patterns for IndexedDB schema design and transaction management?
   - **Scope**: Schema versioning, index design, quota management
   - **Output**: Database schema for conversations and cached summaries
   - **Reference**: MDN IndexedDB guide, Dexie.js patterns (for reference only, not dependency)

4. **Streaming Response Handling**
   - **Question**: What is the pattern for handling streaming AI responses in JavaScript?
   - **Scope**: Server-Sent Events vs polling, incremental UI updates
   - **Output**: Implementation strategy for FR-017 (streaming responses)
   - **Reference**: OpenAI streaming examples, FastAPI SSE documentation

### Design Decisions (from clarifications)

| Decision | Chosen Approach | Alternatives Considered | Rationale |
|----------|-----------------|------------------------|-----------|
| Retrieval Strategy | Long-context when supported, else RAG | Always RAG / Always full-book | Best quality for long-context models, predictable fallback for others |
| API Key Storage | Server-side config (no browser keys) | Browser keys / Env-only | Keeps secrets off the browser; simplest for self-hosted single-user |
| Conversation Persistence | IndexedDB + on-disk JSON per book | IndexedDB only / Server DB | Portable, debuggable, and keeps filesystem as source of truth |
| Concurrent Requests | Sequential queue | Block UI / Parallel execution / Debouncing | Maintains conversation flow (Q4) |
| Summary Caching | IndexedDB keyed by `book_uuid` + provider | In-memory / localStorage / Server files | Persistent, per-provider cache separation |

## Phase 1: Data Model & Contracts

### Entities (to be detailed in data-model.md)

**Core Entities** (from spec.md Key Entities):

1. **AIConversation**
   - Fields: id (UUID), book_uuid (UUID), messages (List[AIMessage]), provider (str), last_updated (datetime)
   - Storage: IndexedDB table `conversations` (browser cache) + `books/{book_folder}/ai_conversations/{conversation_id}.json` (server-side, portable)
   - Lifecycle: Created on first AI panel open per book, persists indefinitely, manually clearable

2. **AIMessage**
   - Fields: id (UUID), conversation_id (UUID), role (user/assistant), content (str), timestamp (datetime), metadata (dict)
   - Storage: Embedded in AIConversation.messages (denormalized)
   - Validation: role in ['user', 'assistant'], content max 100KB

3. **AIProviderConfig**
   - Fields: name (str), base_url (str), model_name (str), enabled (bool), timeout (int)
   - Storage: Server-side local config (API keys never returned to browser)

4. **BookSummary**
   - Fields: book_uuid (UUID), content (dict), provider (str), generated_at (datetime), cache_expiration (datetime)
   - Storage: IndexedDB table `summaries`, indexed by book_uuid
   - Structure: content = {overview: str, highlights: List[str], background: str}

5. **AISettings**
   - Fields: default_provider (str), providers (List[AIProvider]), preferences (dict)
   - Storage: Server-side local config (plus optional browser-only UI prefs)
   - Preferences: {show_timestamps: bool, auto_suggest_questions: bool}

### API Endpoints (to be detailed in contracts/)

**AI Assistant API** (`/api/ai/*`):

1. `POST /api/ai/summary/{book_uuid}` - Generate book summary
2. `POST /api/ai/question/{book_uuid}` - Ask question about book
3. `POST /api/ai/rag/retrieve` - Retrieve relevant passages (internal)

**Settings API** (`/api/settings/*`):

1. `GET /api/settings` - Load all settings
2. `PUT /api/settings/providers/{provider_name}` - Update provider config
3. `POST /api/settings/providers/{provider_name}/test` - Test connection
4. `GET /api/settings/providers` - List available providers

**Ollama Proxy API** (`/api/ollama/*`):
1. `GET /api/ollama/models` - List downloaded Ollama models (proxy to Ollama /api/tags)
2. `GET /api/ollama/status` - Check if Ollama server is running

**Design Principles**:
- RESTful conventions
- JSON request/response bodies
- Standard HTTP status codes (200, 400, 401, 500)
- Authentication: None (localhost self-hosted)
- Rate limiting: None (single-user)

## Phase 2: Implementation Phases (Task Breakdown)

*Note: Detailed tasks generated by `/speckit.tasks` command, not by `/speckit.plan`*

### Recommended Phase Grouping

**Phase 1 (P1): MVP - Core AI Summary & Q&A**
- Implement RAG chunking and retrieval
- Add AI button to reader interface
- Create floating AI panel with chat interface
- Integrate one AI provider (Claude as default)
- IndexedDB persistence for conversations
- Basic error handling

**Phase 2 (P2): Multi-Provider Support**
- Add remaining AI provider integrations (OpenAI, Gemini, **Ollama**, OpenRouter)
- **Ollama integration** (P1 priority):
  - Implement OllamaProvider class using OpenAI-compatible API
  - Add model selection dropdown (qwen3:32b, qwen3:8b, qwen2.5-1m:14b)
  - Connection testing and health checks
  - Error handling for server not running / model not found
- Implement provider selector dropdown
- Provider-specific error handling and fallbacks

**Phase 3 (P3): Settings & Polish**
- Create Settings page
- Persist provider configs and API keys on the server (local config file)
- Add quick action buttons (全书总结, 书籍亮点, 背景解读)
- Implement suggested questions feature
- Summary caching in IndexedDB
- UI polish to match reference design

## Post-Phase 1 Constitution Re-Check

*To be filled after Phase 1 (data model + contracts) completion*

### Data Structure Compliance

- [ ] All entities defined as typed dataclasses in `ai_models.py`
- [ ] IndexedDB schema documented with migrations
- [ ] API contracts use explicit request/response schemas
- [ ] No implicit state or magic values

### Complexity Justification Review

- [ ] IndexedDB usage remains simple (no complex transactions)
- [ ] No new frameworks or architectural patterns introduced
- [ ] All complexity traceable to functional requirements

### Security Validation

- [ ] API keys never returned to the browser
- [ ] No XSS vectors in AI response display
- [ ] Book ID validation prevents path traversal
- [ ] Error messages don't leak sensitive information

**GATE RESULT**: [To be filled after Phase 1]

## Dependencies & Integration Points

### Existing System Dependencies

1. **ChromaDB** (from 001-search-features)
   - Integration point: Reuse vector embeddings for RAG retrieval
   - Assumption: Embeddings already generated for all indexed books (Assumption 2, 4)
   - Risk: If embeddings missing, fallback to basic text extraction (FR-025)

2. **book.pkl Structure** (reader3.py)
   - Integration point: Extract chapter text for RAG chunking
   - Dependency: `ChapterContent.text` field contains clean plain text
   - No changes required: Read-only access to existing data

3. **FastAPI Server** (server.py)
   - Integration point: Add new API routes for AI and settings
   - Modification: Import ai_service.py, add route handlers
   - Compatibility: New routes don't conflict with existing search/reader routes

### External Dependencies (New)

1. **AI Provider SDKs**
   ```toml
   # Cloud providers
   anthropic~=0.40.0         # Claude Sonnet/Opus 4
   openai~=1.54.0            # GPT-4o, GPT-4 Turbo
   google-generativeai~=0.8.0 # Gemini Pro/Ultra

   # Local provider 🆕
   ollama~=0.6.0             # Local LLM runtime (QWEN models)
                             # Note: Ollama server installed separately
                             # via `brew install ollama` (macOS)
   ```
   - Rationale: Official SDKs provide best support and streaming capabilities
   - **Ollama setup**:
     - Python client: `ollama~=0.6.0` (pip package)
     - Ollama server: Installed system-wide (`brew install ollama`)
     - Models: Downloaded via `ollama pull qwen3:32b` (~20GB each)
   - Alternative: Direct HTTP requests (more complex, no streaming)

2. **Browser APIs** (No install required)
   - IndexedDB API (Storage)
   - Fetch API (AJAX requests)
   - Supported: Chrome 88+, Firefox 87+, Safari 14+

### Ollama Local Provider Integration 🆕

**Priority**: P1 (High) - Implements US-003 from spec.md

**Value Proposition**:
- Zero API costs (free local inference)
- 100% data privacy (content never leaves machine)
- Offline capability (no internet required)
- Excellent Chinese language support (QWEN models)

**Technical Architecture**:

```python
# ai_service.py - Ollama Provider Implementation
from openai import AsyncOpenAI  # Ollama uses OpenAI-compatible API

class OllamaProvider:
    """Local AI provider using Ollama + QWEN models"""

    def __init__(self, model_name: str = "qwen3:32b", base_url: str = "http://localhost:11434/v1/"):
        # Reuse OpenAI client for API compatibility
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key="ollama"  # Required but ignored by Ollama
        )
        self.model_name = model_name
        self.is_local = True
        self.requires_api_key = False

    async def chat(self, messages: List[dict], stream: bool = True):
        """Same interface as cloud providers"""
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=stream
        )

        if stream:
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            return response.choices[0].message.content
```

**Implementation Effort**: 8-10 hours total
- Provider class: 2h (reuses OpenAI interface)
- Settings UI: 1h (model selector, connection test)
- API endpoints: 1h (`/api/ollama/models`, `/api/ollama/status`)
- Error handling: 1h (server not running, model missing)
- Testing: 2h (offline operation, model switching)
- Documentation: 1h (`README.md` setup guide)

**Recommended Models**:
1. **qwen3:32b** (Primary) - 19.8GB
   - Best quality, Chinese/English bilingual
   - Context: 128K tokens
   - Speed: ~20-25 tok/s on RTX 3090

2. **qwen3:8b** (Fast) - 4.5GB
   - 2-3x faster responses
   - Good for simple questions
   - Speed: ~50-60 tok/s on M2

3. **qwen2.5-1m:14b** (Long Context) - 8.2GB
   - 1M token context (full books)
   - No chunking needed for summaries
   - Speed: ~30-40 tok/s

**User Setup Flow**:
1. Install Ollama: `brew install ollama` (macOS)
2. Download model: `ollama pull qwen3:32b` (~20GB, one-time)
3. Verify: `curl http://localhost:11434/api/tags`
4. In Reader3 Pro Settings: Select "Ollama" provider, choose model
5. Test connection → Start chatting offline!

**Integration Points**:
- **Backend**: `ai_service.py` adds `OllamaProvider` class
- **Frontend**: Settings UI adds Ollama section with model dropdown
- **API**: New endpoints for health check and model listing
- **Error Handling**: Graceful fallback to cloud if Ollama unavailable

**Performance Expectations**:
- First response: 150-400ms (faster than cloud with no network latency)
- Throughput: 18-60 tok/s (hardware dependent)
- Total response (200 tokens): 4-10 seconds (acceptable for local inference)
- Memory: 20-65GB (model + quantization dependent)

**Testing Strategy**:
1. Unit tests: Ollama provider interface compatibility
2. Integration tests: Health check, model listing, chat
3. Offline test: Disconnect network, verify full functionality
4. Performance test: Compare with cloud providers (quality + speed)
5. Error scenarios: Server not running, model missing, insufficient memory

---

### Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| ChromaDB embeddings missing | Medium | High | Implement fallback to basic text extraction (FR-025) |
| IndexedDB quota exceeded | Low | Medium | Monitor usage, warn at 80%, provide clear function (Edge Case) |
| AI provider API changes | Medium | Medium | Abstract common interface, version-pin SDKs |
| Browser incompatibility | Low | High | Document supported browsers, graceful degradation |
| Streaming response failures | Medium | Low | Fall back to non-streaming responses (Assumption 7) |
| **Ollama server not running** 🆕 | **Medium** | **Medium** | Show clear setup instructions, fallback to cloud provider |
| **Ollama model not downloaded** 🆕 | **Medium** | **Medium** | Display download command (`ollama pull qwen3:32b`), check `/api/tags` |
| **Insufficient GPU memory** 🆕 | **Low** | **Medium** | Suggest smaller model (qwen3:8b), CPU fallback (slow but works) |
| **Ollama version incompatibility** 🆕 | **Low** | **Low** | Pin ollama client version, document required Ollama server version |

## Acceptance Criteria

### From Success Criteria (spec.md)

1. **SC-001**: ✅ Initial summary < 10 seconds
   - Test: Time from AI button click to summary display
   - Pass threshold: 90% of attempts under 10s

2. **SC-002**: ✅ Q&A responses < 5 seconds (95th percentile)
   - Test: Measure response time for 100 test questions
   - Pass threshold: 95th percentile under 5s

3. **SC-003**: ✅ 85% relevance accuracy
   - Test: Manual spot-checking of 20 Q&A pairs per book
   - Pass threshold: 17/20 (85%) deemed relevant by reviewer

4. **SC-004**: ✅ Provider switching without errors
   - Test: Switch between all 5 providers mid-conversation
   - Pass threshold: No errors, responses from correct provider

5. **SC-005**: ✅ 90% UI match to reference design
   - Test: Side-by-side visual comparison of 10 UI elements
   - Pass threshold: 9/10 elements match (spacing, colors, typography)

6. **SC-006**: ✅ Conversation persistence
   - Test: Close panel, refresh page, reopen - history intact
   - Pass threshold: All messages restored correctly

7. **SC-007**: ✅ Settings validation
   - Test: Save/load API credentials for all 5 providers
   - Pass threshold: All credentials persist and validate

8. **SC-008**: ✅ Graceful error handling
   - Test: Trigger API failures (wrong key, timeout, network error)
   - Pass threshold: Clear error messages, recovery suggestions shown

9. **SC-009**: ✅ No documentation needed
   - Test: New user completes workflow without help
   - Pass threshold: 90% task completion rate in user testing

10. **SC-010**: ✅ Multilingual support
    - Test: Books in English and Chinese
    - Pass threshold: Summaries and Q&A work for both languages

11. **SC-011**: ✅ Ollama setup and offline operation 🆕
    - Test: User installs Ollama, downloads qwen3:32b, runs first query
    - Pass threshold: Complete setup in <10 minutes, works 100% offline

12. **SC-012**: ✅ Ollama performance acceptable 🆕
    - Test: Compare response quality and speed vs. cloud providers
    - Pass threshold: Quality ≥80% of cloud, speed <10s for 200-token responses

### Definition of Done

- [ ] All functional requirements implemented (including Ollama provider support)
- [ ] All 12 success criteria (SC-001 to SC-012) pass acceptance tests
- [ ] Phase 1 (P1) user stories fully functional end-to-end
- [ ] Ollama provider works 100% offline with zero API costs
- [ ] All edge cases documented with implemented behaviors
- [ ] Constitution check passes post-implementation
- [ ] Code reviewed against constitution principles
- [ ] `README.md` updated with AI feature + Ollama setup documentation

## Next Steps

1. **Run Phase 0 Research** (this command)
   - Execute research tasks listed above
   - Generate `research.md` with findings
   - Resolve all "NEEDS CLARIFICATION" items

2. **Run Phase 1 Design** (this command)
   - Generate `data-model.md` with detailed entity schemas
   - Generate `contracts/ai-api.yaml` and `contracts/settings-api.yaml`
   - Generate `quickstart.md` for developers

3. **Run Phase 2 Tasks** (separate command: `/speckit.tasks`)
   - Generate dependency-ordered task list
   - Break down into granular implementation steps
   - Assign priorities and estimates

4. **Implementation** (manual)
   - Follow task sequence from `tasks.md`
   - Commit frequently with constitution-compliant messages
   - Test against acceptance criteria
   - Update documentation

---

**Plan Status**: ✅ Phase 0 & Phase 1 ready to execute
**Generated By**: `/speckit.plan` command
**Last Updated**: 2025-12-18
