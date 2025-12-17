# Feature Specification: AI Reading Assistant

**Feature Branch**: `002-ai-assistant`
**Created**: 2025-12-18
**Status**: Draft
**Input**: User description: "创建新的 002-add-ai-summary branch，添加功能：我希望在 reader.html，也就是每个书籍打开后，页面右边搜索 button 下方增加一个 ai button，显示`AI`字样，点击后，同样弹出右边悬浮窗，用于调用大模型（可选 Claude, OpenAI, Openrouter,Gemini，Ollama 等模型）对当前的书籍进行 AI summary，并进行提问等总结。如图所示，要求 UI 完整复刻截图。总结，就是实现 Google notebooklm 功能，利用 RAG 技术对全文进行索引，然后总结。要求大模型可选配置多种模型，后续可能需要有单独的 Setting 页面用于配置大模型的 api 等选项。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI Book Summary Generation (Priority: P1)

A user opens an EPUB book and wants to get an AI-generated summary of the entire book or specific sections. They click the "AI" button in the sidebar, which opens a chat interface. The AI assistant automatically analyzes the book content using RAG technology and presents a comprehensive summary with key themes, main points, and chapter highlights. The user can then ask follow-up questions about the book content.

**Why this priority**: This is the core value proposition - providing intelligent book summarization and Q&A capabilities similar to Google NotebookLM. This delivers immediate value for users who want to quickly understand book content or find specific information through conversational AI interaction.

**Independent Test**: Can be fully tested by opening any processed book, clicking the "AI" button, verifying the sidebar panel opens with AI summary functionality, and confirming that the assistant generates a coherent summary of the book. Delivers standalone value without requiring other features.

**Acceptance Scenarios**:

1. **Given** a user is reading a book, **When** they click the "AI" button in the sidebar, **Then** a floating panel appears on the right side with AI chat interface showing a welcome message and initial book summary
2. **Given** the AI panel is open, **When** the system generates the book summary, **Then** the summary displays with organized sections (全书总结/书籍亮点/背景解读) matching the reference UI
3. **Given** a book summary is displayed, **When** the user types a question in the input field and submits, **Then** the AI responds with a contextually relevant answer based on the book content
4. **Given** the AI chat interface is active, **When** the user asks questions, **Then** the conversation history is displayed with clear visual distinction between user questions and AI responses
5. **Given** the AI panel is open, **When** the user clicks outside the panel or a close button, **Then** the panel closes and the conversation state is preserved for re-opening

---

### User Story 2 - Multi-Provider AI Model Selection (Priority: P2)

A user wants to choose which AI model provider to use for book analysis (Claude, OpenAI, Gemini, Ollama, or OpenRouter). They access a model selection dropdown in the AI panel header and can switch between available providers. Each provider offers different capabilities, response styles, and performance characteristics. The system validates API availability and provides clear feedback when a provider is not configured.

**Why this priority**: This enables flexibility and user choice, allowing users to leverage their preferred AI provider or switch based on availability, cost, or quality preferences. It's essential for production use but not required for initial testing of the AI functionality.

**Independent Test**: Can be tested by opening the AI panel, selecting different model providers from the dropdown, sending test questions, and verifying that responses come from the selected provider. Delivers value by enabling user choice and avoiding vendor lock-in.

**Acceptance Scenarios**:

1. **Given** the AI panel is open, **When** the user clicks the model selector dropdown in the header, **Then** all configured AI providers are listed (Claude, OpenAI, Gemini, Ollama, OpenRouter)
2. **Given** the model selector is open, **When** the user selects a different AI provider, **Then** subsequent AI requests use the selected provider and the UI updates to show the active provider
3. **Given** a user selects an AI provider, **When** that provider's API is not configured or unavailable, **Then** the system displays a clear error message with instructions to configure the provider in settings
4. **Given** multiple AI providers are configured, **When** one provider fails or times out, **Then** the system suggests switching to an alternative provider without losing the conversation context
5. **Given** the user has selected a provider, **When** they close and reopen the AI panel, **Then** the previously selected provider remains active

---

### User Story 3 - Settings Page for API Configuration (Priority: P3)

A user wants to configure API keys and settings for different AI model providers. They navigate to a dedicated Settings page where they can enter API keys, set default models, configure timeout values, and test connections for each provider. The settings are securely stored and validated before being saved.

**Why this priority**: This provides the infrastructure for managing multiple AI providers but is not required for users who only use one provider with API keys set via environment variables. It's important for long-term usability but can be deferred initially.

**Independent Test**: Can be tested by navigating to the Settings page, entering API keys for different providers, saving configurations, and verifying that the AI panel successfully uses the configured credentials. Delivers value by eliminating the need for manual configuration files or environment variables.

**Acceptance Scenarios**:

1. **Given** a user accesses the Settings page, **When** the page loads, **Then** a form displays with input fields for each AI provider (API key, base URL, model name, timeout)
2. **Given** the Settings form is displayed, **When** the user enters an API key and clicks "Test Connection", **Then** the system validates the credentials and displays success or error feedback
3. **Given** valid API keys are entered, **When** the user clicks "Save", **Then** the settings are securely stored and a confirmation message appears
4. **Given** settings are saved, **When** the user returns to the reader and opens the AI panel, **Then** the configured providers are available for selection
5. **Given** the user has configured multiple providers, **When** they set a default provider in settings, **Then** the AI panel opens with that provider pre-selected

---

### User Story 4 - Suggested Questions and Quick Actions (Priority: P3)

Based on the reference UI, users see suggested questions or conversation starters at the bottom of the AI chat interface (e.g., "日本案例对中国的教育体系有何借鉴?"). Clicking these suggestions automatically sends the question to the AI. The system also provides quick action buttons for common tasks like "全书总结" (Full Book Summary), "书籍亮点" (Key Highlights), and "背景解读" (Background Analysis).

**Why this priority**: This enhances discoverability and reduces friction for users who are unsure what questions to ask. It's a UX enhancement that can be added after core functionality is working.

**Independent Test**: Can be tested by opening the AI panel and verifying that suggested questions appear at the bottom, clicking them sends the question, and quick action buttons trigger appropriate AI responses. Delivers value by improving user engagement.

**Acceptance Scenarios**:

1. **Given** the AI panel is open, **When** the initial summary is displayed, **Then** 2-3 contextually relevant suggested questions appear as clickable pills at the bottom
2. **Given** suggested questions are displayed, **When** the user clicks a suggestion, **Then** the question is automatically sent to the AI and a response is generated
3. **Given** the AI panel header, **When** displayed, **Then** three quick action buttons (全书总结, 书籍亮点, 背景解读) are visible
4. **Given** a user clicks a quick action button, **When** the action is triggered, **Then** the AI generates a specialized response focused on that specific aspect of the book
5. **Given** the conversation progresses, **When** the user scrolls through chat history, **Then** new suggested questions appear based on the current conversation context

---

### Edge Cases

- What happens when the AI model API call times out or fails (network error, rate limit, invalid API key)?
- How does the system handle very large books (1000+ pages) that may exceed context window limits?
- What happens when a user switches books while the AI panel is open with an active conversation?
- How does the system handle concurrent AI requests if a user sends multiple questions rapidly?
- What happens when the book content is not yet indexed for RAG (fresh upload)?
- How does the AI panel respond when the user's screen resolution is small (mobile/tablet)?
- What happens if the AI response is excessively long and exceeds display limits?
- How does the system handle books in non-English languages (Chinese, Japanese, etc.)?
- What happens when a user tries to use the AI feature but no API keys are configured?

## Requirements *(mandatory)*

### Functional Requirements

#### UI Requirements

- **FR-001**: System MUST display an "AI" button in the reader sidebar, positioned below the search button
- **FR-002**: AI button MUST be clearly labeled with "AI" text and visually distinct from other sidebar controls
- **FR-003**: System MUST open a floating panel on the right side of the screen when the AI button is clicked, matching the reference UI design
- **FR-004**: AI panel MUST display a header with the title "AI 问书" and a model selector dropdown
- **FR-005**: AI panel MUST include a chat interface with scrollable message history showing user questions and AI responses
- **FR-006**: System MUST visually distinguish between user messages and AI responses (different styling/alignment)
- **FR-007**: AI panel MUST include an input field at the bottom with placeholder text "提出问题，获得来自书籍的解答..."
- **FR-008**: System MUST display quick action buttons (全书总结, 书籍亮点, 背景解读) in the AI panel header
- **FR-009**: System MUST show suggested questions as clickable pills at the bottom of the chat interface
- **FR-010**: AI panel MUST be closable via a close button or clicking outside the panel area
- **FR-011**: System MUST preserve conversation state when the panel is closed and reopened within the same session

#### AI Model Integration

- **FR-012**: System MUST support multiple AI model providers: Claude (Anthropic), OpenAI, Google Gemini, Ollama (local), and OpenRouter
- **FR-013**: System MUST provide a model selector dropdown in the AI panel header allowing users to switch providers
- **FR-014**: System MUST validate API availability for the selected provider before sending requests
- **FR-015**: System MUST display clear error messages when an AI provider is unavailable or misconfigured
- **FR-016**: System MUST handle API request failures gracefully with retry logic and fallback suggestions
- **FR-017**: System MUST support streaming responses for providers that offer it (display text as it's generated)
- **FR-018**: System MUST timeout requests after a reasonable duration (30 seconds default) and inform the user

#### RAG and Content Processing

- **FR-019**: System MUST use RAG (Retrieval-Augmented Generation) technology to index and query book content
- **FR-020**: System MUST leverage existing vector embeddings from the search feature (ChromaDB) if available
- **FR-021**: System MUST extract and index relevant book sections for efficient AI query processing
- **FR-022**: System MUST provide book context (title, author, chapter information) to the AI model in each request
- **FR-023**: System MUST limit the amount of book content sent to the AI model based on context window limitations
- **FR-024**: System MUST retrieve the most relevant book passages for each user question using semantic search
- **FR-025**: System MUST handle books that are not yet indexed by initiating indexing or using basic text extraction

#### Summary Generation

- **FR-026**: System MUST automatically generate an initial book summary when the AI panel is first opened for a book
- **FR-027**: AI summary MUST include sections for: full book overview, key highlights, and background/context analysis
- **FR-028**: System MUST cache generated summaries to avoid regenerating on every panel open
- **FR-029**: System MUST allow users to request specialized summaries via quick action buttons
- **FR-030**: Summary generation MUST respect the selected AI model provider and use its capabilities

#### Conversation Management

- **FR-031**: System MUST maintain conversation history for the duration of the reading session
- **FR-032**: System MUST display conversation history in chronological order with clear timestamps
- **FR-033**: System MUST allow users to ask follow-up questions that reference previous conversation context
- **FR-034**: System MUST provide a way to clear conversation history and start fresh
- **FR-035**: System MUST save conversation history per book (switching books starts a new conversation)

#### Settings and Configuration

- **FR-036**: System MUST provide a Settings page accessible from the library or reader interface
- **FR-037**: Settings page MUST include configuration forms for each AI provider (API key, base URL, model name, timeout)
- **FR-038**: Settings page MUST provide a "Test Connection" button for each provider to validate credentials
- **FR-039**: System MUST securely store API keys (encrypted or in secure storage, not plain text in localStorage)
- **FR-040**: Settings page MUST allow users to set a default AI provider that is pre-selected when opening the AI panel
- **FR-041**: System MUST validate required settings before allowing AI functionality to be used
- **FR-042**: Settings page MUST provide clear instructions for obtaining API keys from each provider

### Key Entities

- **AIConversation**: Represents a chat session between the user and AI for a specific book, containing message history, selected model provider, and book context
- **AIMessage**: Represents a single message in the conversation (user question or AI response), with timestamp, role (user/assistant), content, and optional metadata
- **AIProvider**: Represents configuration for a specific AI model provider (name, API key, base URL, model name, enabled status, timeout settings)
- **BookSummary**: Represents a cached AI-generated summary for a book, including overview, highlights, background sections, generation timestamp, and provider used
- **AISettings**: Represents global AI configuration including default provider, API credentials for all providers, and user preferences

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can open the AI panel and receive an initial book summary within 10 seconds of clicking the AI button
- **SC-002**: Users can ask questions about book content and receive relevant AI responses within 5 seconds (95th percentile)
- **SC-003**: AI responses accurately reference book content with at least 85% relevance as measured by user feedback or spot-checking
- **SC-004**: Users can switch between AI providers and receive responses from the selected provider without errors
- **SC-005**: 90% of AI panel UI elements match the reference design screenshot (spacing, layout, colors, typography)
- **SC-006**: Conversation history is preserved when closing and reopening the AI panel during the same reading session
- **SC-007**: Settings page successfully validates and saves API credentials for all supported providers
- **SC-008**: System gracefully handles AI provider failures with clear error messages and recovery suggestions
- **SC-009**: Users can complete the entire workflow (open panel, get summary, ask questions) without needing technical documentation
- **SC-010**: AI feature works correctly for books in multiple languages (English and Chinese minimum)

## Assumptions

- **Assumption 1**: Users have basic familiarity with AI chat interfaces (ChatGPT, Claude, etc.)
- **Assumption 2**: Vector embeddings for books are already generated by the existing search feature (Phase 5 from 001-search-features)
- **Assumption 3**: Users are willing to provide their own AI provider API keys (no built-in free tier)
- **Assumption 4**: The existing ChromaDB vector storage can be reused for RAG queries without re-indexing
- **Assumption 5**: Average book size is under 500 pages, fitting within typical AI model context windows with summarization
- **Assumption 6**: Self-hosted deployment means API keys can be stored locally without complex encryption requirements (user responsibility)
- **Assumption 7**: Streaming responses are a nice-to-have; initial implementation can use non-streaming APIs
- **Assumption 8**: Users will primarily use one or two AI providers, not frequently switching between all five
