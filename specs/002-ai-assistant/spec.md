# Feature Specification: AI Reading Assistant

**Feature ID**: 002-ai-assistant
**Status**: Planning
**Priority**: P1 (High)
**Target Version**: 2.0.0
**Owner**: Jack Cheng
**Created**: 2025-12-18
**Last Updated**: 2025-12-18

---

## Table of Contents

1. [Overview](#overview)
2. [User Stories](#user-stories)
3. [Functional Requirements](#functional-requirements)
4. [Non-Functional Requirements](#non-functional-requirements)
5. [AI Provider Support](#ai-provider-support)
6. [Technical Architecture](#technical-architecture)
7. [UI/UX Design](#uiux-design)
8. [Data Model](#data-model)
9. [API Endpoints](#api-endpoints)
10. [Security Considerations](#security-considerations)
11. [Success Criteria](#success-criteria)
12. [Out of Scope](#out-of-scope)

---

## Overview

### Problem Statement

Users reading EPUB books in Reader3 Pro lack intelligent assistance for:
- Understanding complex book content
- Getting quick summaries without reading entire chapters
- Asking questions about characters, themes, and plot points
- Extracting key insights and highlights

### Solution

Implement an AI-powered reading assistant that provides:
- **Book Summarization**: Generate intelligent summaries (overview, highlights, background)
- **Conversational Q&A**: Ask questions and get context-aware answers using RAG
- **Multi-Provider Support**: Choose from cloud (Claude, OpenAI, Gemini, OpenRouter) or **local (Ollama)** AI models
- **Privacy Options**: Use local models (Ollama + QWEN) for 100% offline operation with zero API costs

### Key Benefits

- 📚 **Deeper Understanding**: AI helps extract insights from complex texts
- 🚀 **Time Saving**: Get summaries without reading entire books
- 💬 **Interactive Learning**: Ask questions and get instant answers
- 🔒 **Privacy Control**: Use local models (Ollama) for complete data privacy
- 💰 **Cost Flexibility**: Choose between cloud APIs or free local inference
- 🌐 **Offline Capable**: Ollama provider works without internet connection

---

## User Stories

### US-001: Quick Book Summary (P1)
**As a** reader
**I want to** click an "AI" button and see a summary of the current book
**So that** I can quickly understand the main themes without reading everything

**Acceptance Criteria**:
- AI button appears in reader interface header
- Clicking opens floating chat panel with quick action buttons
- "全书总结" (Full Summary) button generates 2-3 paragraph overview
- Summary appears within 10 seconds
- Summary persists across page refreshes

---

### US-002: Ask Questions About Book (P1)
**As a** reader
**I want to** ask questions about the book content in natural language
**So that** I can get specific answers without searching manually

**Acceptance Criteria**:
- Chat input field accepts questions in Chinese or English
- AI retrieves relevant passages using RAG
- Answers cite specific chapters/sections
- Conversation history maintained across sessions
- Response time <5 seconds at 95th percentile

**Example Questions**:
- "Who is the main character?"
- "Summarize chapter 5"
- "What are the key themes in this book?"
- "Explain the ending"

---

### US-003: Use Local AI Models (P1) 🆕
**As a** privacy-conscious reader
**I want to** use local AI models (Ollama + QWEN) instead of cloud APIs
**So that** my book content never leaves my computer and I pay zero API costs

**Acceptance Criteria**:
- Settings page shows "Ollama (Local)" as a provider option
- User can select from downloaded Ollama models (qwen3:32b, qwen3:8b, etc.)
- Connection test verifies Ollama server is running
- All Q&A and summaries work offline using local model
- Response quality comparable to cloud providers for Chinese/English books
- Clear UI indication when using local vs. cloud provider

**Technical Notes**:
- Requires Ollama installed (`brew install ollama` on macOS)
- Models downloaded via `ollama pull qwen3:32b` (~20GB)
- No API key needed for local models
- Fallback to cloud providers if Ollama unavailable

---

### US-004: Switch AI Providers (P2)
**As a** user
**I want to** choose which AI provider powers my reading assistant
**So that** I can use my preferred service or local models based on needs

**Acceptance Criteria**:
- Settings page lists all 5 providers: Anthropic (Claude), OpenAI (GPT), Google (Gemini), **Ollama (Local)**, OpenRouter
- Each provider shows configuration options (API key for cloud, model selection for local)
- Can switch providers mid-conversation without data loss
- Default provider setting persists
- **Ollama provider shows "No API key required" label**

---

### US-005: Key Highlights Extraction (P1)
**As a** reader
**I want to** see 5-10 key highlights or insights from the book
**So that** I can quickly understand important takeaways

**Acceptance Criteria**:
- "书籍亮点" (Book Highlights) quick action button
- Returns 5-10 bullet points
- Each highlight is 1-2 sentences
- Highlights cached for repeated access

---

### US-006: Background Information (P2)
**As a** reader
**I want to** learn about the book's context (author, historical background, significance)
**So that** I can better appreciate the work

**Acceptance Criteria**:
- "背景解读" (Background) quick action button
- Returns author bio, publication context, literary significance
- Formatted as readable paragraphs
- Cites external knowledge (not just book content)

---

### US-007: Conversation Persistence (P1)
**As a** user
**I want to** my conversation history saved automatically
**So that** I can continue where I left off after closing the browser

**Acceptance Criteria**:
- All messages stored in browser IndexedDB (per-browser cache)
- Conversations also saved on disk per book as JSON files under `books/{book_folder}/` (portable between browsers/machines)
- Conversation restored on panel reopen
- Can manually clear conversation
- Separate conversations per book
- **Works offline for Ollama conversations**

---

### US-009: Multiple Chat Threads per Book (P2)
**As a** reader
**I want to** start a new chat thread for the same book
**So that** each thread stays short and does not bloat context for the model

**Acceptance Criteria**:
- AI panel shows a list of previous chat threads for the current book + provider
- A "New chat" button creates a fresh thread without deleting old threads
- Switching threads preserves each thread’s message history
- Each thread is stored separately (IndexedDB + book folder JSON)

---

### US-008: Suggested Questions (P2)
**As a** reader
**I want to** see AI-generated suggested follow-up questions
**So that** I can explore the book more deeply

**Acceptance Criteria**:
- 3-5 suggested questions appear after each AI response
- Questions contextually relevant to conversation
- Clicking suggested question sends it automatically
- Can be disabled in settings

---

## Functional Requirements

### FR-001: AI Button in Reader Interface (P1)
The reader interface shall display an "AI" button (🤖 icon) in the header toolbar.

### FR-002: Floating Chat Panel (P1)
Clicking the AI button shall open a floating chat panel overlaying the reader content.

**Panel Components**:
- Header with title "AI Reading Assistant" and close button
- Quick action buttons (全书总结, 书籍亮点, 背景解读)
- Message history area with scrolling
- Text input field with send button
- **Provider indicator showing current AI model (e.g., "🤖 Ollama: QWEN 3 32B" or "☁️ Claude Sonnet 4")**

### FR-003: Book Summarization (P1)
The system shall generate AI summaries with three components:
- **Overview**: 2-3 paragraph high-level summary
- **Highlights**: 5-10 key insights as bullet points
- **Background**: Author context and literary significance

### FR-004: RAG-Based Q&A (P1)
The system shall answer questions using Retrieval-Augmented Generation:
1. Retrieve top 3-5 most relevant text chunks using semantic search (ChromaDB)
2. Send retrieved context + question to AI provider
3. Return answer with source citations (chapter numbers)

### FR-005: Conversation History (P1)
The system shall maintain conversation state:
- Store all messages (user + assistant) in IndexedDB
- Load conversation on panel open
- Preserve history across browser sessions
- **Separate storage for cloud vs. local (Ollama) conversations**

### FR-006: Multi-Provider Support (P1)
The system shall support 5 AI providers:

1. **Anthropic Claude** (Cloud)
   - Models: claude-sonnet-4, claude-opus-4
   - API Key required
   - 1M token context window

2. **OpenAI GPT** (Cloud)
   - Models: gpt-4-turbo-preview, gpt-4o
   - API Key required
   - 128K token context window

3. **Google Gemini** (Cloud)
   - Models: gemini-pro, gemini-ultra
   - API Key required
   - 1-2M token context window

4. **Ollama (Local)** 🆕 (P1)
   - Models: qwen3:32b, qwen3:8b, qwen2.5-1m:14b, qwen2.5-coder:32b
   - **No API Key required**
   - Runs 100% offline
   - Context window: 128K-1M tokens (model dependent)
   - Base URL: `http://localhost:11434` (configurable)
   - Requires Ollama installed locally

5. **OpenRouter** (Cloud)
   - Proxy to multiple providers
   - API Key required
   - Variable context windows

### FR-007: Ollama Provider Configuration (P1) 🆕
The Settings page shall provide Ollama-specific options:

**Configuration Fields**:
- **Base URL**: Default `http://localhost:11434`, allow custom ports
- **Model Selection**: Dropdown populated from `/api/tags` endpoint
  - qwen3:32b (Recommended - Best quality, 19.8GB)
  - qwen3:8b (Fast - Quick responses, 4.5GB)
  - qwen3:4b (Lightweight - Low memory, 2.2GB)
  - qwen2.5-1m:14b (Long context - 1M tokens, 8.2GB)
  - Custom models shown if user downloaded others
- **Enable/Disable**: Toggle Ollama provider
- **Connection Test**: Button to verify Ollama server running
- **Model Download Guide**: Link to Ollama installation instructions

**UI Indicators**:
- Green dot: Ollama server reachable
- Red dot: Ollama not running (show setup instructions)
- Model size displayed next to each model option

### FR-008: API Key Management (P2)
The system shall securely manage API keys (backend-held):
- Store provider API keys on the **server** for this self-hosted, single-user instance (never return keys to the browser)
- Support environment variables as an alternative for development/deployment
- **Ollama provider: No API key field shown (local authentication not needed)**

### FR-009: Provider Switching (P2)
Users shall switch providers without losing conversation:
- Provider selector dropdown in chat panel header
- **Smooth transition from cloud to Ollama (or vice versa)**
- Warning if switching mid-conversation
- Conversation history preserved (each provider keeps its own thread; switching shows that provider’s history)

### FR-010: Quick Action Buttons (P1)
Three quick action buttons shall appear above chat input:
- **全书总结** (Full Summary): Generate complete summary
- **书籍亮点** (Highlights): Extract key insights
- **背景解读** (Background): Provide context

### FR-011: Streaming Responses (P2)
AI responses shall stream incrementally:
- Display text as it's generated (token by token)
- Show typing indicator during generation
- Stop button to cancel generation
- **Works for both cloud and Ollama providers**

### FR-012: Suggested Questions (P2)
After each AI response, display 3-5 suggested follow-up questions:
- Generated based on conversation context
- Clickable to auto-send
- Refreshable with "More suggestions" button

### FR-013: Summary Caching (P1)
Generated summaries shall be cached:
- Store in IndexedDB by `book_uuid`
- Reuse cached summary if available
- Force regenerate option
- **Cache separately for each provider (Ollama vs. cloud may differ)**

### FR-014: Error Handling (P1)
The system shall gracefully handle errors:

**Cloud Provider Errors**:
- Invalid API key → Show setup instructions
- Rate limit → Display wait time, suggest retry
- Network timeout → Retry with exponential backoff
- Service unavailable → Suggest alternative provider

**Ollama Errors** 🆕:
- Server not running → Show installation guide with `brew install ollama` command
- Model not found → Show download command (`ollama pull qwen3:32b`)
- Insufficient memory → Suggest smaller model (qwen3:8b)
- Connection refused → Check if server running on correct port

### FR-015: Mobile Responsiveness (P3)
Chat panel shall adapt to screen sizes:
- Desktop: Floating panel (400px width)
- Tablet: Slide-in panel (50% width)
- Mobile: Full-screen overlay

### FR-016: Multilingual Support (P1)
The system shall support Chinese and English:
- UI labels in Chinese with English fallbacks
- AI understands and responds in both languages
- **Ollama QWEN models optimized for Chinese/English bilingual tasks**

### FR-017: Conversation Management (P2)
The UI shall support multiple conversation threads per book and provider.

**Requirements**:
- Show conversation thread list in AI panel (most recent first)
- Provide a "New chat" action that creates a new thread
- Limit model context usage by only sending the active thread’s recent messages
- Persist each thread to disk as JSON under the book folder

Users shall manage conversation history:
- Clear conversation button
- Export conversation to text/JSON
- Search within conversation
- **Separate management for cloud vs. Ollama conversations**

### FR-018: Performance Optimizations (P2)
The system shall optimize performance:
- Lazy load AI panel resources
- Debounce user input (300ms)
- Request queue (max 1 concurrent AI call)
- Cancel pending requests on new input

### FR-019: Settings Page (P2)
A dedicated Settings page shall provide:
- Provider configuration (API keys, model selection)
- Default provider selection
- UI preferences (theme, timestamps, suggestions)
- **Ollama setup guide and status dashboard**
- Export/import settings backup

### FR-020: RAG Retrieval Configuration (P3)
Advanced users shall configure RAG settings:
- Number of chunks to retrieve (default: 5)
- Similarity threshold (default: 0.5)
- Chunk size (default: 1000 tokens)
- **Works identically for cloud and local providers**

---

## Non-Functional Requirements

### NFR-001: Response Time (SC-002)
- 95th percentile Q&A response time: <5 seconds (cloud providers)
- **Ollama response time: <10 seconds (acceptable for local inference)**
- Summary generation: <10 seconds (cloud), <20 seconds (Ollama)

### NFR-002: Accuracy (SC-003)
- RAG retrieval relevance: ≥85% (manual spot-checking)
- Answer accuracy: ≥85% correct based on book content
- **Ollama accuracy: ≥80% (slightly lower acceptable for local models)**

### NFR-003: Availability
- Client-side chat panel: 100% (offline capable for Ollama)
- Cloud API dependency: Accept provider outages
- **Ollama fallback: Automatic retry or switch to cloud provider**

### NFR-004: Security
- API keys stored **server-side** in `config/ai_settings.json` (gitignored) with restrictive permissions (e.g. `chmod 600`)
- API keys are never returned to the browser (only `api_key_configured: true/false`)
- HTTPS-only for cloud API calls
- **Ollama: Local HTTP acceptable (localhost)**
- No API keys in logs or console

### NFR-005: Browser Compatibility
- Chrome 88+
- Firefox 87+
- Safari 14+
- No IE support

### NFR-006: Storage Efficiency
- IndexedDB quota usage <50MB typical
- Warn at 80% quota
- Auto-cleanup old conversations (>30 days)

### NFR-007: Accessibility
- Keyboard navigation (Tab, Enter, Esc)
- Screen reader support (ARIA labels)
- Focus management

### NFR-008: Internationalization
- UI supports zh-CN and en-US
- Date/time formatting based on locale
- **Model selection shows sizes in GB (universal)**

---

## AI Provider Support

### Provider Comparison Matrix

| Feature | Anthropic Claude | OpenAI GPT | Google Gemini | **Ollama (Local)** 🆕 | OpenRouter |
|---------|-----------------|------------|---------------|---------------------|------------|
| **API Key Required** | ✅ Yes | ✅ Yes | ✅ Yes | **❌ No** | ✅ Yes |
| **Internet Required** | ✅ Yes | ✅ Yes | ✅ Yes | **❌ No (Offline)** | ✅ Yes |
| **Cost** | $0.015/1k tokens | $0.01/1k tokens | $0.0005/1k tokens | **Free** | Variable |
| **Context Window** | 1M tokens | 128K tokens | 1-2M tokens | **128K-1M tokens** | Variable |
| **Chinese Support** | Good | Good | Good | **Excellent (QWEN)** | Variable |
| **Response Speed** | ~5s | ~4s | ~6s | **~10s (32B model)** | Variable |
| **Streaming** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Privacy** | Cloud | Cloud | Cloud | **100% Local** | Cloud |
| **Setup Complexity** | API Key | API Key | API Key | **Install Ollama** | API Key |

### Ollama Provider Details 🆕

**Recommended Models**:
1. **qwen3:32b** (Primary) - 19.8GB
   - Best quality for general Q&A
   - Chinese/English bilingual
   - 128K context window
   - ~20-25 tokens/sec on RTX 3090

2. **qwen3:8b** (Fast) - 4.5GB
   - 2-3x faster responses
   - Good quality for simple questions
   - Lower memory requirements
   - ~50-60 tokens/sec on M2

3. **qwen2.5-1m:14b** (Long Context) - 8.2GB
   - 1M token context (entire book)
   - Best for full-book summaries
   - No chunking needed
   - ~30-40 tokens/sec

**Hardware Requirements**:
- **Minimum**: 32GB RAM, 20GB disk space (CPU inference slow)
- **Recommended**: 64GB RAM, 24GB VRAM GPU, 50GB SSD
- **Optimal**: RTX 4090 or Apple M2/M3 with 32GB+ unified memory

**Installation**:
```bash
# macOS
brew install ollama

# Download model
ollama pull qwen3:32b

# Verify
curl http://localhost:11434/api/tags
```

**Performance Expectations**:
- First token latency: 150-400ms (model dependent)
- Throughput: 18-60 tokens/sec (hardware dependent)
- Total response time (200 tokens): 4-10 seconds
- Memory usage: 20-65GB (model + quantization dependent)

---

## Technical Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (Frontend)                      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Reader UI    │  │ AI Panel UI  │  │ Settings UI  │      │
│  │ (reader.html)│  │ (ai-panel.js)│  │(settings.html)│      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │  IndexedDB      │                        │
│                   │  - Conversations│                        │
│                   │  - Summaries    │                        │
│                   └─────────────────┘                        │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS/HTTP
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   FastAPI Server (Backend)                   │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ ai_service.py│  │ rag_service  │  │ server.py    │      │
│  │ (Providers)  │  │ (ChromaDB)   │  │ (API Routes) │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                  │                                 │
│         │         ┌────────▼────────┐                        │
│         │         │  Local Config   │                        │
│         │         │  - Provider keys│                        │
│         │         │  - Provider cfg │                        │
│         │         └─────────────────┘                        │
│         │         ┌────────▼────────┐                        │
│         │         │  ChromaDB       │                        │
│         │         │  (Vector Store) │                        │
│         │         │  + Embeddings   │                        │
│         │         └─────────────────┘                        │
│         │                                                     │
│         │                                                     │
│  ┌──────▼────────────────────────────────────────────┐      │
│  │         AI Provider Abstraction Layer             │      │
│  │                                                    │      │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐  │      │
│  │  │Anthropic│ │ OpenAI │ │ Gemini │ │ **Ollama**│  │      │
│  │  │ Client │ │ Client │ │ Client │ │ **Client**│  │      │
│  │  └───┬────┘ └───┬────┘ └───┬────┘ └────┬─────┘  │      │
│  └──────┼──────────┼──────────┼────────────┼────────┘      │
└─────────┼──────────┼──────────┼────────────┼───────────────┘
          │ HTTPS    │ HTTPS    │ HTTPS      │ HTTP (Local)
          │          │          │            │
┌─────────▼──────┐ ┌─▼────────┐ ┌─▼────────┐ ┌▼──────────────┐
│ Anthropic API  │ │OpenAI API│ │Gemini API│ │**Ollama Server**│
│ (Cloud)        │ │ (Cloud)  │ │ (Cloud)  │ │**(localhost)** │
│ $0.015/1k tok  │ │$0.01/1k │ │$0.0005/1k│ │  **FREE**      │
└────────────────┘ └──────────┘ └──────────┘ │  **Offline**   │
                                              │qwen3:32b/8b/... │
                                              └─────────────────┘
```

### Component Responsibilities

**Frontend**:
- `ai-panel.js`: Chat UI, message rendering, streaming display
- `indexeddb-manager.js`: Persistent storage wrapper (conversations + summary cache)
- `settings.js`: Provider configuration, **Ollama connection testing**

**Backend**:
- `ai_service.py`: Multi-provider abstraction, request routing, **Ollama client**
- `rag_service.py`: Semantic search, chunk retrieval
- `server.py`: API endpoints, request validation

**External**:
- ChromaDB: Vector storage (existing from 001-search-features)
- AI Providers: Claude, OpenAI, Gemini, **Ollama (local)**, OpenRouter

---

## UI/UX Design

### AI Button

**Location**: Reader header, right side (next to search icon)
**Icon**: 🤖 emoji or robot SVG
**Behavior**:
- Default state: Gray
- Active (panel open): Blue highlight
- **Processing**: Pulsing animation
- **Ollama active**: Green dot indicator (offline capable)

### Chat Panel Layout

```
┌─────────────────────────────────────────┐
│ AI Reading Assistant              [×]   │  ← Header
│ ☁️ Claude Sonnet 4  [▼]                 │  ← Provider selector
├─────────────────────────────────────────┤
│ [全书总结] [书籍亮点] [背景解读]          │  ← Quick actions
├─────────────────────────────────────────┤
│                                         │
│  💬 User: What is this book about?     │  ← Message history
│                                         │
│  🤖 AI: This book explores...          │
│     (Source: Chapter 1, 3)             │
│                                         │
│  💬 User: Tell me more...              │
│                                         │
│  🤖 AI: [Streaming response...]        │
│                                         │
│  ┌─ Suggested Questions ──────────┐   │
│  │ • What are the main themes?    │   │
│  │ • Who is the antagonist?       │   │
│  └────────────────────────────────┘   │
│                                         │
├─────────────────────────────────────────┤
│ [Type your question...]          [🔍]  │  ← Input
└─────────────────────────────────────────┘
```

**Panel Dimensions**:
- Desktop: 400px width, 600px height
- Mobile: Full screen
- Position: Fixed right, top 64px

**Ollama UI Enhancements** 🆕:
- Provider selector shows "🤖 Ollama: QWEN 3 32B" with offline badge
- Green dot next to provider name when connected
- Model name clickable to show details (context window, size)
- Connection status: "✅ Running locally" or "⚠️ Not connected"

### Settings Page

**Tabs**:
1. **Providers**: Configure AI services
2. **Preferences**: UI settings
3. **Data**: Export/import, clear cache

**Ollama Provider Section** 🆕:
```
┌─────────────────────────────────────────────────┐
│ Ollama (Local AI)                          [ON] │
├─────────────────────────────────────────────────┤
│                                                 │
│ Status: ✅ Connected (http://localhost:11434)  │
│                                                 │
│ Model:  [qwen3:32b ▼]                          │
│         Size: 19.8GB | Context: 128K tokens    │
│                                                 │
│ Base URL: [http://localhost:11434          ]  │
│                                                 │
│ [Test Connection] [Refresh Models]             │
│                                                 │
│ Available Models:                               │
│ • qwen3:32b (19.8GB) - Recommended             │
│ • qwen3:8b (4.5GB) - Faster                    │
│ • qwen2.5-1m:14b (8.2GB) - Long context        │
│                                                 │
│ Don't have Ollama?                              │
│ [📥 Installation Guide] [🔗 Download]          │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Data Model

See [data-model.md](./data-model.md) for complete schemas.

**Key Entities**:
1. `AIConversation`: Chat session per book
2. `AIMessage`: Single message (user/assistant)
3. `AIProviderConfig`: Provider config (API keys stored server-side)
4. `BookSummary`: Cached summary
5. `AISettings`: Global preferences

**Book Identity (UUID)**:
- This feature uses a stable `book_uuid` (UUID) for all AI endpoints and persistence.
- The reader route may still use the existing folder-based id; the server MUST provide `book_uuid` to the reader UI for API calls.
- Recommended storage: `books/{book_folder}/ai_meta.json` containing `{ "book_uuid": "..." }`.
- If the file is missing, the server SHOULD generate a new UUID once and persist it, so future sessions remain stable.

---

## API Endpoints

See OpenAPI specs:
- [contracts/ai-api.yaml](./contracts/ai-api.yaml)
- [contracts/settings-api.yaml](./contracts/settings-api.yaml)
- [contracts/ollama-api.yaml](./contracts/ollama-api.yaml)

**Core Endpoints**:

```
POST /api/ai/summary/{book_uuid}
  - Generate book summary
  - Provider: Specified in request body

POST /api/ai/question/{book_uuid}
  - Answer question with RAG
  - Supports streaming (SSE)

POST /api/ai/rag/retrieve
  - Internal RAG retrieval

GET /api/settings/providers
  - List available providers

POST /api/settings/providers/ollama/test 🆕
  - Test Ollama connection
  - Returns available models
  - Response: {status: "ok", models: ["qwen3:32b", ...]}
```

**Ollama-Specific Endpoints** 🆕:
```
GET /api/ollama/models   - List downloaded Ollama models (proxy /api/tags)
GET /api/ollama/status   - Check if Ollama server is running
```

---

## Security Considerations

### API Key Storage (Backend-held)
- API keys are stored on the server for this self-hosted, single-user instance.
- The browser never receives API keys; APIs only return `api_key_configured: true/false`.
- Keys SHOULD be stored in `config/ai_settings.json` (gitignored) with restricted permissions (e.g. chmod 600), or via environment variables.

### Data Privacy
- **Cloud Providers**: Book content sent to third-party APIs
- **Ollama**: 100% local processing, content never leaves machine
- User informed of privacy implications in Settings
- Clear labeling: "☁️ Cloud" vs "🤖 Local" badges

### Network Security
- HTTPS is used between the server and cloud providers.
- **Ollama**: HTTP acceptable for localhost communication
- CORS headers properly configured
- No API keys in URL parameters

### Input Validation
- Sanitize user questions (XSS prevention)
- Validate `book_uuid` exists in the local library mapping
- Rate limiting: 1 request per 2 seconds per user
- **Ollama**: Validate model names against `/api/tags` response

---

## Success Criteria

### SC-001: Summary Performance
**Target**: Initial summary generation <10 seconds (cloud), <20 seconds (Ollama)
**Measurement**: Time from button click to full summary display
**Threshold**: 90% of requests meet target

### SC-002: Q&A Response Time
**Target**: <5 seconds at 95th percentile (cloud), <10 seconds (Ollama)
**Measurement**: Time from Enter press to answer completion
**Threshold**: 95th percentile under target

### SC-003: Answer Relevance
**Target**: ≥85% accuracy (cloud), ≥80% (Ollama)
**Measurement**: Manual review of 20 Q&A pairs per book
**Threshold**: 17/20 (cloud), 16/20 (Ollama) deemed relevant

### SC-004: Provider Switching
**Target**: Zero errors when switching providers mid-conversation
**Measurement**: Test switching between all 5 providers
**Threshold**: All combinations work without data loss

### SC-005: UI Fidelity
**Target**: 90% visual match to reference design
**Measurement**: Side-by-side comparison of 10 UI elements
**Threshold**: 9/10 elements match spacing, colors, typography

### SC-006: Conversation Persistence
**Target**: 100% conversation restored after page refresh
**Measurement**: Close panel, refresh, reopen
**Threshold**: All messages restored correctly

### SC-007: Settings Validation
**Target**: API credentials saved and validated for all 5 providers
**Measurement**: Save/load test for each provider
**Threshold**: All 5 providers persist correctly

### SC-008: Error Handling
**Target**: Clear error messages with recovery suggestions
**Measurement**: Trigger errors (wrong key, timeout, network down, **Ollama not running**)
**Threshold**: User can resolve issue from error message alone

### SC-009: Usability
**Target**: New user completes workflow without documentation
**Measurement**: User testing with 5 new users
**Threshold**: 90% task completion rate

### SC-010: Multilingual Support
**Target**: Works for English and Chinese books
**Measurement**: Test with 5 EN + 5 CN books
**Threshold**: Summaries and Q&A work for both languages

### SC-011: Ollama Setup 🆕
**Target**: User can set up Ollama and run first query in <10 minutes
**Measurement**: Timed setup from installation guide
**Threshold**: 80% of users complete setup successfully

### SC-012: Offline Operation 🆕
**Target**: Ollama provider works 100% offline
**Measurement**: Disconnect internet, run Q&A with Ollama
**Threshold**: All features work without network

---

## Out of Scope

The following features are explicitly excluded from v1.0:

### ❌ Not Included
- **Multi-user support**: Single-user self-hosted only
- **Real-time collaboration**: No shared conversations
- **Custom model fine-tuning**: Use pre-trained models only
- **Voice input/output**: Text-only interface
- **Image analysis**: Text content only (no OCR on book images)
- **Cross-book comparison**: Single book context per conversation
- **Annotation integration**: Separate from existing highlight feature
- **Mobile apps**: Web browser only
- **Backend conversation storage**: Client-side only (IndexedDB)
- **AI model training**: No usage data collection for training

### 🔮 Future Considerations (v2.0+)
- Plugin system for custom AI providers
- Export conversation as PDF/EPUB
- Voice-to-text question input
- Multi-book semantic search
- Reading progress tracking with AI insights
- Personalized reading recommendations

---

## Appendix

### A. Reference Design
**Source**: Google NotebookLM (https://notebooklm.google.com)
**Key UI Elements**:
- Floating chat panel (right side)
- Quick action buttons (top of panel)
- Suggested questions (after responses)
- Clean, minimal design with focus on content

### B. Glossary
- **RAG**: Retrieval-Augmented Generation (semantic search + LLM)
- **ChromaDB**: Vector database for embeddings
- **Ollama**: Local LLM runtime (like Docker for AI models)
- **QWEN**: Alibaba's open-source multilingual LLM family
- **IndexedDB**: Browser-native key-value storage
- **SSE**: Server-Sent Events (streaming protocol)

### C. Related Documents
- [plan.md](./plan.md): Implementation roadmap
- [research.md](./research.md): Technical research findings
- [data-model.md](./data-model.md): Detailed data schemas
- [extension-evaluation.md](./extension-evaluation.md): Ollama integration evaluation
- [quickstart.md](./quickstart.md): Developer setup guide

---

**Document Version**: 1.0
**Last Updated**: 2025-12-18
**Status**: ✅ Approved for Implementation
