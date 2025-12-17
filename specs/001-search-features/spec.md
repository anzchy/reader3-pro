# Feature Specification: Search Functionality

**Feature Branch**: `001-search-features`
**Created**: 2025-12-17
**Status**: Draft
**Input**: User description: "我想要在目前项目基础上增加两个功能： 1.在 library 页面（也就是包含所有的 epub 封面信息）增加一个 search box，可以进行full context search between all the epub files, probably using rags or other technology. 2.for every opened epubs,add search box in the upper-left sidebar. so that I can search all of the related words in the file."

## Clarifications

### Session 2025-12-17

- Q: What is `book_id` in routes/APIs? → A: Use the existing identifier used by the app routes: the processed folder name ending in `_data` (e.g., `dracula_data`)
- Q: When search terms are highlighted in reader HTML content, how should malicious input like `<script>alert('xss')</script>` be handled to prevent XSS? → A: Escape all HTML entities in search terms before highlighting (convert `<` to `&lt;`, etc.) - prevents script injection while allowing all text searches
- Q: When users search for very common words like "the", "a", "is" that appear thousands of times, how should the system handle performance and usability? → A: Limit results to first 1000 occurrences with message "Showing first 1000 of [total] results" - balances performance with functionality
- Q: When searching across multiple books in the library, if some books fail to search (corrupted data, missing files, processing errors) while others succeed, how should results be presented? → A: Show partial results with error indicator "Results from 8 of 10 books (2 failed)" - transparent and non-blocking
- Q: When the same search term appears multiple times on a single displayed chapter/page, how should highlighting and scrolling work? → A: Highlight all occurrences; scroll to the clicked result's occurrence (fallback: first) - predictable navigation with full visibility
- Q: When users search for terms with special characters, punctuation, or diacritics (e.g., "café", "naïve", "re-design"), how should matching work across different languages? → A: Normalize for Latin scripts (strip diacritics: café→cafe), exact match for other scripts (Chinese, etc.) - balanced approach for multi-language support

## User Scenarios & Testing *(mandatory)*

### User Story 1 - In-Book Keyword Search (Priority: P1)

A user is reading an EPUB book and wants to quickly find all occurrences of specific words or phrases within that book. They type a search term in the sidebar search box and instantly see a list of all matching locations with surrounding context. Clicking any result jumps directly to that location in the book with the search term highlighted.

**Why this priority**: This is the most immediately valuable feature for users actively reading a book. It enables quick reference lookup, fact-checking, and navigation within a single book without external tools. This can be implemented independently without requiring cross-book infrastructure.

**Independent Test**: Can be fully tested by opening any book, entering a search term (e.g., "vampire"), and verifying that all occurrences are listed with context and clicking a result navigates to the correct chapter with highlighting.

**Acceptance Scenarios**:

1. **Given** a user is reading a book, **When** they enter a search term in the sidebar search box, **Then** the system displays all matching occurrences with chapter titles and surrounding text context

2. **Given** search results are displayed, **When** the user clicks a specific result, **Then** the reader navigates to the correct chapter and scrolls to that exact occurrence (not just the chapter), with visual highlighting

3. **Given** a user enters a search term, **When** no matches are found, **Then** the system displays a clear "No results found for '[term]'" message

4. **Given** a user has performed a search, **When** they clear the search box or submit an empty/whitespace query, **Then** the results panel closes and highlighting is removed

5. **Given** a user enters a multi-word phrase, **When** searching, **Then** the system finds exact phrase matches (not just individual words)

---

### User Story 2 - Cross-Book Library Search (Priority: P2)

A user has multiple EPUB books in their library and wants to search across all books simultaneously to find which books contain specific topics, names, or concepts. They enter a search term on the library page and see results grouped by book, showing relevant passages from each book that contains the term.

**Why this priority**: This feature enables research workflows across multiple books, helping users discover connections between books and locate information without manually searching each book individually. This builds on the in-book search infrastructure but requires cross-book indexing.

**Independent Test**: Can be tested by adding multiple books to the library, entering a search term on the library page, and verifying that results from all matching books are displayed with book titles, authors, and relevant passages (and book covers if available).

**Acceptance Scenarios**:

1. **Given** a user is on the library page with multiple books, **When** they enter a search term in the library search box, **Then** the system displays results grouped by book with title, author, and matching passages (and book cover if available)

2. **Given** search results are displayed, **When** the user clicks on a specific result passage, **Then** the system opens that book to the exact occurrence (chapter + occurrence) and highlights it

3. **Given** a user performs a library search, **When** results contain multiple matches from the same book, **Then** the system shows up to 3 most relevant passages per book with a "Show more" option

4. **Given** a user enters a search term, **When** the search is in progress, **Then** the system displays a loading indicator

5. **Given** library search results are displayed, **When** the user sorts by relevance or book title, **Then** the results reorder accordingly

6. **Given** a user has performed a library search, **When** they clear the search box or submit an empty/whitespace query, **Then** the search results are cleared and the default library view is shown

---

### User Story 3 - Semantic Cross-Book Search (Priority: P3)

A user wants to find books that discuss concepts related to their search term, even if they don't contain the exact words. They enter a search query like "immortality" and the system returns passages about eternal life, undeath, vampirism, and other semantically related concepts using RAG or embedding-based search.

**Why this priority**: This enhances research capabilities by understanding meaning rather than just matching keywords. It's valuable for academic research and deep topic exploration but requires more complex infrastructure (embeddings, vector search).

**Independent Test**: Can be tested by searching for a concept (e.g., "fear") and verifying that results include passages about "terror," "dread," "anxiety" and other semantically related terms, not just exact matches.

**Acceptance Scenarios**:

1. **Given** a user performs a library search with semantic search enabled, **When** they enter a search term, **Then** the system returns results that match the semantic meaning, not just exact keyword matches

2. **Given** semantic search results are displayed, **When** the user hovers over or clicks an info icon, **Then** the system explains why each passage was matched (e.g., "Related concept: eternal life")

3. **Given** a user has both keyword and semantic search options, **When** they toggle between modes, **Then** the results update to reflect the selected search type

4. **Given** semantic search is processing, **When** embeddings are not yet generated for a book, **Then** the system indicates which books are still being indexed

---

### Edge Cases

- **Resolved**: When a user searches for very common words (e.g., "the", "a") that appear thousands of times, system limits display to first 1000 results with notification message (see FR-008a)
- **Resolved**: How does the system handle special characters, punctuation, or diacritics in search terms? - Normalize diacritics for Latin scripts, exact match for non-Latin scripts (FR-009)
- What happens when searching in books with very large chapters (100+ pages)?
- How does the system perform when the library contains 50+ books?
- **Resolved**: What happens when a user enters an empty search query? - Treated as "clear search" (FR-010)
- How are search results handled when books contain HTML entities or formatting codes?
- What happens when a user performs multiple rapid searches in succession?
- **Resolved**: How does highlighting work when the same word appears multiple times on the same page? - Highlight all occurrences; scroll to the clicked result's occurrence (fallback: first) (FR-005, FR-011)

## Requirements *(mandatory)*

### Functional Requirements

#### In-Book Search (P1)

- **FR-001**: System MUST provide a search input field in the reader sidebar that is always visible when viewing a book
- **FR-002**: System MUST search through all chapter text content (the `text` field of `ChapterContent` objects) within the current book
- **FR-003**: System MUST display search results in a scrollable list showing: chapter title, surrounding context, and match position
- **FR-004**: System MUST support case-insensitive search by default with an option for case-sensitive search
- **FR-005**: System MUST highlight ALL occurrences of search terms visually when displaying chapter content after clicking a search result, and scroll to the selected occurrence (fallback: first occurrence)
- **FR-006**: System MUST support exact phrase search when the user enters multi-word queries
- **FR-007**: System MUST provide a way to clear search results and remove highlighting
- **FR-008**: System MUST show match count (e.g., "23 results found") alongside search results
- **FR-008a**: System MUST limit displayed results to first 1000 occurrences when total matches exceed 1000, displaying message "Showing first 1000 of [total] results" to inform users of truncation
- **FR-009**: System MUST handle searches across books with different languages and character sets by normalizing diacritics in Latin-script text (café→cafe, naïve→naive) while preserving exact character matching for non-Latin scripts (Chinese, Japanese, Korean, Arabic, Cyrillic, etc.)
- **FR-010**: System MUST treat empty/whitespace-only queries as "clear search" (no search performed)
- **FR-011**: System MUST navigate to the exact occurrence represented by a clicked result (not just the chapter)
- **FR-012**: System MUST extract a context window around each match and truncate consistently for display (20 words before/after if the chapter text contains whitespace; otherwise 40 characters before/after)
- **FR-012a**: System MUST escape all HTML entities in search terms before applying highlighting to prevent XSS attacks (convert `<` to `&lt;`, `>` to `&gt;`, `&` to `&amp;`, quotes to `&quot;` and `&#39;`)

#### Cross-Book Library Search (P2)

- **FR-013**: System MUST provide a search input field on the library page above or beside the book grid
- **FR-014**: System MUST search across all processed books in the `*_data/` directories
- **FR-015**: System MUST display results grouped by book with book metadata (title, author, and cover if available; otherwise show a placeholder)
- **FR-016**: System MUST show up to 3 most relevant matching passages per book with surrounding context
- **FR-017**: System MUST allow users to expand results to see more matches from the same book
- **FR-018**: System MUST link from search results directly to the exact occurrence in the book (chapter + occurrence), with highlighting
- **FR-019**: System MUST indicate when search is in progress with a loading state
- **FR-020**: System MUST support sorting results by relevance score or alphabetically by book title
- **FR-021**: System MUST limit search result display to prevent performance issues (e.g., maximum 100 total results)
- **FR-022**: For keyword search, "relevance" MUST be defined and consistent as: exact phrase hits (desc) > total hit count (desc) > earliest occurrence position (asc)
- **FR-022a**: System MUST display partial results when some books fail to search, showing success count and failure count (e.g., "Results from 8 of 10 books (2 failed)") and continue to display available results

#### Semantic Search (P3)

- **FR-023**: System MUST provide an option to toggle between keyword search and semantic search modes
- **FR-024**: System MUST build and store semantic representations of book content to enable semantic search
- **FR-025**: System MUST find semantically related passages even when exact keywords don't match
- **FR-026**: System MUST provide relevance scoring for semantic search results
- **FR-027**: System MUST indicate to users which books have been indexed for semantic search and which are pending
- **FR-028**: System MUST allow reindexing of books when content changes
- **FR-029**: System MUST explain semantic matches to users (e.g., "Related concept: [similar term]")

#### Performance & UX

- **FR-030**: System MUST return in-book search results within 500ms for books up to 500 pages
- **FR-031**: System MUST return library search results within 2 seconds for libraries up to 50 books
- **FR-032**: System MUST debounce search input to avoid excessive searches while typing (recommended: 300ms delay)
- **FR-033**: System MUST preserve the user's prior reading location (at minimum: chapter index) when navigating to a search result so the user can return via browser Back
- **FR-034**: System MUST handle gracefully when books have no searchable text content
- **FR-035**: System MUST truncate very long search result contexts to prevent UI overflow
- **FR-036**: System MUST persist search query and results in session-scoped client state to maintain search context during navigation within the application

### Key Entities

- **Search Result**: Represents a single match containing book ID, chapter index, occurrence index within chapter, surrounding context text, and relevance score
- **Search Index**: Represents searchable content extracted from books, including chapter text, metadata, and (for semantic search) embeddings
- **Search Query**: Represents user search parameters including term, search mode (keyword/semantic/exact), case sensitivity, and target scope (single book/all books)
- **Highlight Range**: Represents text ranges to be visually highlighted in the reader, containing start position, end position, and highlight style

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can find any word or phrase within a book and see all occurrences in under 1 second
- **SC-002**: Users can navigate from a search result to the exact location in the book in under 2 seconds
- **SC-003**: Library search returns results from all books in under 3 seconds for libraries with up to 50 books
- **SC-004**: 90% of users successfully find information using search on their first attempt without needing external tools
- **SC-005**: Search highlighting makes found terms immediately visible without requiring manual scanning of the page
- **SC-006**: Semantic search (when implemented) surfaces relevant passages that keyword search misses, increasing discovery by at least 25%
- **SC-007**: Users can perform research across multiple books without needing to open and search each book individually
- **SC-008**: Search functionality works correctly for books in multiple languages (English, Chinese, etc.)

## Assumptions

- **Assumption 1**: Books are already processed and have the `text` field populated in `ChapterContent` objects (plain text without HTML)
- **Assumption 2**: Users primarily search in their native language matching the book's language (no cross-language search required initially)
- **Assumption 3**: Search highlighting uses simple CSS styling without requiring modification of book HTML structure
- **Assumption 4**: For semantic search, using a lightweight local embedding approach is acceptable for self-hosted deployment
- **Assumption 5**: Users are willing to wait for initial indexing of books for semantic search (one-time cost per book)
- **Assumption 6**: Case-insensitive search is the default user expectation for general reading
- **Assumption 7**: The library size will typically be under 100 books for self-hosted individual use
