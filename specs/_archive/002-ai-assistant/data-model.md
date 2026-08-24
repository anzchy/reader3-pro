# Data Model: AI Reading Assistant

**Feature**: 002-ai-assistant | **Date**: 2025-12-18  
**References**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [contracts/](./contracts/)

## Overview

This document defines the data structures for the AI Reading Assistant feature, including:

- Backend entities (Python) used by API endpoints
- Server-side provider configuration (API keys are stored on the server)
- Frontend persistence (IndexedDB) for conversation + summary cache

This aligns with decisions:

- **Book identity**: AI endpoints use **`book_uuid`** (UUID) — stable and URL-safe.
- **API keys**: **backend-held** — browser never receives API keys.
- **Retrieval**: **long-context when supported**, otherwise RAG retrieval via existing ChromaDB index.

---

## Identifiers

### `book_uuid` (UUID)

- Used by all AI endpoints: `/api/ai/*/{book_uuid}`
- Used as the primary key for conversation + summary caches

### `book_folder` (string, internal)

- Existing Reader3 book folder name (e.g. `The-Cold-Start-Problem_data`) stored under `books/`
- Used by the server to locate `books/{book_folder}/book.pkl`
- Not used in AI endpoint URLs (may contain spaces/parentheses)

**Mapping requirement**: the server must be able to map `book_uuid → book_folder` (e.g. via a local mapping file or a per-book sidecar metadata file).
Recommended: a per-book sidecar file at `books/{book_folder}/ai_meta.json` containing `{ "book_uuid": "..." }`.

---

## Backend (Python) Entities

These are data contracts for API requests/responses. The server is responsible for:

- Loading the book content from `books/{book_folder}/book.pkl`
- Loading provider configuration + secrets (API keys) locally
- Calling provider SDKs and returning text responses

### 1) `AIMessage`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

@dataclass
class AIMessage:
    id: UUID = field(default_factory=uuid4)
    role: str = "user"  # "user" | "assistant"
    content: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Validation**
- `role` in `{user, assistant}`
- `content` non-empty for user messages
- `content` max size should be bounded (e.g. 100KB) to avoid IndexedDB blowups

### 2) `ConversationContext`

The backend is stateless regarding conversation; the frontend sends recent history (bounded) with each request.

```python
from dataclasses import dataclass, field
from typing import List
from uuid import UUID

@dataclass
class ConversationContext:
    conversation_id: UUID
    book_uuid: UUID
    messages: List[AIMessage] = field(default_factory=list)  # last N messages only
```

### 3) `RetrievalSource`

```python
from dataclasses import dataclass

@dataclass
class RetrievalSource:
    chapter_order: int
    chapter_title: str
    text: str
    similarity: float  # 0..1
```

### 4) `SummaryPayload`

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SummaryPayload:
    overview: str
    highlights: List[str]
    background: str
    themes: Optional[List[str]] = None
    key_concepts: Optional[List[str]] = None
```

---

## Server-Side Provider Configuration (Backend-held secrets)

### `AIProviderConfig` (safe to return)

```python
from dataclasses import dataclass

@dataclass
class AIProviderConfig:
    name: str  # anthropic|openai|gemini|ollama|openrouter
    base_url: str
    model_name: str
    enabled: bool = True
    timeout_s: int = 30
    max_retries: int = 3
```

### `AIProviderSecret` (never returned to browser)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class AIProviderSecret:
    name: str
    api_key: Optional[str] = None  # None for ollama
```

### Local config file format (example)

The server stores provider configs and secrets in a repo-local file (NOT committed to git):

- `config/ai_settings.json`

```json
{
  "default_provider": "anthropic",
  "providers": {
    "anthropic": { "enabled": true, "model_name": "claude-sonnet-4", "api_key": "..." },
    "openai": { "enabled": false, "model_name": "gpt-4o", "api_key": "..." },
    "gemini": { "enabled": false, "model_name": "gemini-pro", "api_key": "..." },
    "openrouter": { "enabled": false, "model_name": "anthropic/claude-sonnet-4", "api_key": "..." },
    "ollama": { "enabled": true, "base_url": "http://localhost:11434", "model_name": "qwen3:32b" }
  }
}
```

**Security**
- API keys must never be returned by settings endpoints
- File should be readable only by the user running the server (e.g. chmod 600)

---

## Frontend Persistence (IndexedDB)

### Database

- Name: `reader3_ai_assistant`
- Version: 1

### Store 1: `conversations`

**Key points**
- Keyed by `id` (conversation UUID)
- Indexed by `book_uuid`

```ts
interface ConversationRecord {
  id: string; // UUID
  book_uuid: string; // UUID
  provider: string;
  created_at: string; // ISO
  last_updated: string; // ISO
  messages: MessageRecord[];
}

interface MessageRecord {
  id: string; // UUID
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO
  metadata?: {
    model?: string;
    token_count?: number;
    retrieval_sources?: Array<{
      chapter_order: number;
      chapter_title: string;
      text: string;
      similarity: number;
    }>;
  };
}
```

### Store 2: `summaries`

Because summaries vary by provider/model, use a composite cache key:

- `cache_key = "{book_uuid}:{provider}:{model_name}"`

```ts
interface SummaryRecord {
  cache_key: string;
  book_uuid: string; // UUID
  provider: string;
  model: string;
  generated_at: string; // ISO
  content: {
    overview: string;
    highlights: string[];
    background: string;
    themes?: string[];
    key_concepts?: string[];
  };
}
```

---

## Validation & Limits (recommended)

- Conversation history sent to backend: keep last **N=50** messages
- Summary cache: store per provider/model; allow manual “regenerate”
- Question length: 1..1000 chars

---

## Notes on Retrieval Routing (long-context vs RAG)

The backend chooses one of two modes per request:

1) **Long-context mode** (preferred when supported): provide larger context (whole book or large multi-chapter excerpt) to the model.
2) **RAG mode**: retrieve top-k passages via ChromaDB and send only those to the model.

The exact heuristic is implementation-defined; the contract only requires that both modes are supported and predictable.
