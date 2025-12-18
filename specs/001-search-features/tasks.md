# Tasks: Search Functionality

**Input**: Design documents from `/specs/001-search-features/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/search-api.yaml

**Tests**: No automated test tasks included (not explicitly requested in spec.md). Manual validation tasks are included (see T071).

**Organization**: Tasks are grouped by user story (P1: In-Book Keyword Search, P2: Cross-Book Library Search, P3: Semantic Search) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are at repository root (single-project structure per plan.md)

---

## Phase 1: Setup (Semantic Search Only, Optional)

**Purpose**: Install semantic-search dependencies. Keyword search (US1/US2) does not require this phase.

- [x] T001 [US3] Install ChromaDB and sentence-transformers dependencies via `uv add chromadb sentence-transformers`
- [x] T002 [US3] Download embedding model (paraphrase-multilingual-MiniLM-L12-v2) using `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"`
- [x] T003 [US3] Verify dependencies are installed correctly with `python -c "import chromadb; import sentence_transformers; print('OK')"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core search data structures and utilities that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete (but Phase 1 is not required for keyword-only work)

- [x] T004 Create search_service.py and implement SearchMode enum (KEYWORD, SEMANTIC, HYBRID) and SearchScope enum (CURRENT_BOOK, ALL_BOOKS)
- [x] T005 [P] Implement SearchQuery dataclass in search_service.py with validation in __post_init__ (FR-010: empty term handling)
- [x] T006 [P] Implement SearchResult dataclass in search_service.py with all required fields per data-model.md
- [x] T007 [P] Implement SearchResultSet dataclass in search_service.py with get_status_message() method (FR-022a: partial failure messaging)
- [x] T008 Implement normalize_for_search() function in search_service.py (FR-009: Latin diacritic normalization, preserve non-Latin)
- [x] T009 Implement extract_context() function in search_service.py (FR-012: 20 words or 40 chars before/after match)
- [x] T010 Implement escape_for_highlighting() function in search_service.py (FR-012a: HTML entity escaping for XSS prevention)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - In-Book Keyword Search (Priority: P1) 🎯 MVP

**Goal**: Enable users to search for words/phrases within a currently open book and navigate to exact occurrences with highlighting

**Independent Test**: Open any processed book (e.g., dracula_data), enter search term in sidebar, verify all occurrences are listed with context, click result to jump to chapter with highlighting at exact occurrence

### Backend Implementation (User Story 1)

- [x] T011 [P] [US1] Implement search_text() function in search_service.py (FR-002, FR-004: keyword matching with case-insensitive default, FR-008a: limit to max_results)
- [x] T012 [US1] Implement search_book() function in search_service.py (FR-001 to FR-012: load book.pkl, search all chapters, extract context, calculate relevance, return SearchResultSet)
- [x] T013 [US1] Add GET /api/search/{book_id} endpoint in server.py (maps to search_book(), accepts q, mode, case_sensitive, max_results query params)
- [x] T014 [US1] Add request validation and error handling (400 for invalid params, 404 for book not found, 500 for internal errors) in /api/search/{book_id} endpoint
- [x] T015 [US1] Add POST /api/highlight/{book_id}/{chapter_order} endpoint in server.py (FR-005: generate HighlightRange objects for all occurrences in chapter)
- [x] T016 [US1] Implement highlight range generation logic with XSS-safe escaping in /api/highlight endpoint (FR-012a: escape search term, FR-011: return selected_occurrence_index for scrolling)

### Frontend Implementation (User Story 1)

- [x] T017 [P] [US1] Create static/search.css with styles for search box, results list, search-match highlighting, result-snippet display
- [x] T018 [US1] Update templates/reader.html to add search box div in sidebar with input field, search button, clear button (FR-001: always visible)
- [x] T019 [US1] Update templates/reader.html to add search results container div with status message and scrollable results list (FR-003: chapter title, context, match position)
- [x] T020 [US1] Create static/search.js with SearchUI class initialization (extract book_id from URL path)
- [x] T021 [US1] Implement performSearch() method in static/search.js (FR-032: debounce 300ms, fetch /api/search/{book_id}, display results or "No results found" message per FR-003 scenario 3)
- [x] T022 [US1] Implement displayResults() method in static/search.js (FR-003: render result items with chapter title, context snippet with <mark> tags, click handler for navigation)
- [x] T023 [US1] Implement clearSearch() method in static/search.js (FR-007, FR-010: clear input, hide results, remove highlighting from chapter content)
- [x] T024 [US1] Implement result click navigation in static/search.js (FR-011: redirect to /read/{book_id}/{chapter_order}?q={term}&occurrence={index} for exact occurrence)
- [x] T025 [US1] Add chapter highlighting logic in static/search.js (FR-005: fetch /api/highlight endpoint, apply <mark> tags to all occurrences, scroll to selected occurrence or first as fallback)
- [x] T026 [US1] Link static/search.js and static/search.css in templates/reader.html before closing </body> tag

**Checkpoint**: User Story 1 (In-Book Keyword Search) is fully functional and independently testable. Users can search within a book, see all results with context, and navigate to exact highlighted occurrences.

---

## Phase 4: User Story 2 - Cross-Book Library Search (Priority: P2)

**Goal**: Enable users to search across all books in library simultaneously from library page, see results grouped by book, and jump to exact locations

**Independent Test**: From library page with multiple processed books, enter search term in library search box, verify results from all matching books grouped by title/author with 3 top passages each, click passage to open book at exact occurrence

### Backend Implementation (User Story 2)

- [ ] T027 [P] [US2] Implement SearchIndex dataclass in search_service.py with books dict and last_updated timestamp
- [ ] T028 [P] [US2] Implement ChapterIndex dataclass in search_service.py (normalized_text for fast matching, original_text for context extraction)
- [ ] T029 [P] [US2] Implement BookIndex dataclass in search_service.py with from_book_pkl() classmethod (loads book.pkl, builds ChapterIndex list)
- [ ] T030 [US2] Implement SearchIndex.build_from_library() classmethod in search_service.py (FR-014: scan *_data/ directories, build index for all books, handle partial failures per FR-022a)
- [x] T031 [US2] Implement search_library() function in search_service.py (FR-013 to FR-022a: search across all indexed books, group results by book_id, apply max_results_per_book limit, sort by relevance/title/author)
- [x] T032 [US2] Add GET /api/search/library endpoint in server.py (accepts q, mode, max_results_per_book, max_total_results, sort_by query params, returns SearchResultSet with grouped_by_book populated)
- [x] T033 [US2] Implement relevance scoring for library search (FR-022: exact phrase hits desc, total hit count desc, earliest occurrence position asc) in search_library() function
- [x] T034 [US2] Add error handling for partial book failures in search_library() (FR-022a: populate failed_books array, continue with successful results)

### Frontend Implementation (User Story 2)

- [x] T035 [P] [US2] Update templates/library.html to add library search box div above/beside book grid with input field and search button (FR-013: prominent placement)
- [x] T036 [US2] Update templates/library.html to add library search results container div with status message and book-grouped results (FR-015: show book metadata - title, author, cover if available)
- [x] T037 [US2] Create static/library-search.js with LibrarySearchUI class initialization
- [x] T038 [US2] Implement performLibrarySearch() method in static/library-search.js (FR-019: show loading indicator, fetch /api/search/library, display results grouped by book, FR-010: clear on empty query)
- [x] T039 [US2] Implement displayLibraryResults() method in static/library-search.js (FR-015: render each book section with title/author/cover, FR-016: show up to 3 passages per book with "Show more" button)
- [x] T040 [US2] Implement result passage click navigation in static/library-search.js (FR-018: redirect to /read/{book_id}/{chapter_order}?q={term}&occurrence={index} for exact highlighted occurrence)
- [x] T041 [US2] Implement sort control in static/library-search.js (FR-020: toggle between relevance, book_title, book_author, re-fetch with sort_by param)
- [x] T042 [US2] Link static/library-search.js in templates/library.html before closing </body> tag

**Checkpoint**: User Story 2 (Cross-Book Library Search) is fully functional and independently testable. Users can search across entire library, see grouped results from all matching books, and navigate to exact occurrences in any book.

---

## Phase 5: User Story 3 - Semantic Cross-Book Search (Priority: P3)

**Goal**: Enable users to find semantically related passages across library using embeddings (e.g., search "immortality" finds "eternal life", "undeath", "vampirism")

**Independent Test**: Search for concept like "fear" in library with semantic mode enabled, verify results include passages about "terror", "dread", "anxiety" (not just exact "fear" matches), click to navigate with match explanation

### Backend Implementation (User Story 3)

- [x] T043 [P] [US3] Create vector_search.py and implement SemanticSearchResult dataclass with chunk_id, chapter metadata, similarity_score fields
- [x] T044 [P] [US3] Implement BookVectorIndex class in vector_search.py with __init__ (setup ChromaDB client, paraphrase-multilingual-MiniLM-L12-v2 embedding function, chroma_path in `{book_id}/chroma_db/` where `book_id` is a `*_data` folder)
- [x] T045 [US3] Implement is_indexed() method in BookVectorIndex (FR-027: check if indexed meta exists)
- [x] T046 [US3] Implement _chunk_text() method in BookVectorIndex (split large chapters into ~1000 char chunks for better retrieval granularity)
- [x] T047 [US3] Implement index_book() method in BookVectorIndex (FR-024, FR-028: load book.pkl, chunk chapters, generate embeddings, upsert to ChromaDB collection with force_reindex option)
- [x] T048 [US3] Implement semantic_search() method in BookVectorIndex (FR-025: query ChromaDB with user term, return top n_results ranked by similarity, format as SemanticSearchResult objects)
- [x] T049 [US3] Implement _format_results() helper in BookVectorIndex (FR-026: convert ChromaDB distances to similarity scores 0-1, populate metadata)
- [x] T050 [US3] Add indexing CLI support in reader3.py (add --index <book_id> argument, call BookVectorIndex.index_book() for specified book)
- [x] T051 [US3] Add POST /api/index/{book_id} endpoint in server.py (FR-024: trigger indexing for book, accept force_reindex in request body)
- [x] T052 [US3] Add GET /api/index/{book_id}/status endpoint in server.py (FR-027: return IndexStatus with book_id, status enum, chunk_count, model_name, indexed_at timestamp)
- [x] T053 [US3] Integrate semantic search into search_book() function (when mode=SEMANTIC, use BookVectorIndex.semantic_search() instead of keyword search_text())
- [x] T054 [US3] Integrate semantic search into search_library() function (when mode=SEMANTIC, iterate books and call BookVectorIndex.semantic_search() for each, aggregate results)

### Frontend Implementation (User Story 3)

- [x] T055 [P] [US3] Update templates/reader.html to add search mode toggle (keyword/semantic/hybrid) in sidebar search box (FR-023: radio buttons or dropdown)
- [x] T056 [P] [US3] Update templates/library.html to add search mode toggle in library search box (FR-023: consistent with reader.html)
- [x] T057 [US3] Add mode parameter to fetch calls in static/search.js performSearch() method (pass selected mode to /api/search/{book_id}?mode={keyword|semantic|hybrid})
- [x] T058 [US3] Add mode parameter to fetch calls in static/library-search.js performLibrarySearch() method
- [x] T059 [US3] Add indexing status indicator in static/search.js (FR-027: check /api/index/{book_id}/status before semantic search, show "Not indexed - indexing required" message with index button)
- [x] T060 [US3] Add indexing status indicator in static/library-search.js for multi-book view (FR-027: show which books are indexed, pending, or failed)
- [x] T061 [US3] Implement semantic match explanation display in static/search.js (FR-029: show why passage matched with "Related concept: [term]" on hover or info icon click)
- [x] T062 [US3] Implement semantic match explanation display in static/library-search.js

**Checkpoint**: User Story 3 (Semantic Cross-Book Search) is fully functional and independently testable. Users can search by meaning/concepts, see semantically related passages, understand why matches were found, and navigate to exact locations.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements, validation, and documentation that affect multiple user stories

- [x] T063 [P] Add input validation for search terms in search_service.py (max length, regex injection prevention per constitution security principle)
- [x] T064 [P] Add book_id validation against enumerated *_data/ directories in server.py endpoints (FR path security, prevent traversal attacks)
- [x] T065 [P] Add performance logging for search operations (execution_time_ms tracking, log slow queries >2s for library search per FR-031)
- [x] T066 Add graceful degradation when books have no searchable text (FR-034: return empty results with clear message "No searchable content in this book")
- [x] T067 Add UI truncation for very long result contexts (FR-035: limit to 150 chars per SearchResult.get_display_snippet() in data model)
- [x] T068 Implement search state persistence in sessionStorage (FR-036: save query and results during navigation, restore on back button)
- [x] T069 [P] Add CSS responsive design for search UI on mobile/tablet viewports
- [x] T070 [P] Update CLAUDE.md with search functionality usage instructions (how to index books, use search modes, performance tips)
- [ ] T071 Validate against quickstart.md instructions (run all manual test steps from quickstart, verify behavior matches documentation)
- [x] T072 Add error messages for common failure scenarios (book not found, indexing failed, ChromaDB not installed, timeout exceeded)
- [x] T073 Optimize search performance with @lru_cache for frequently searched terms (FR-030: <500ms in-book, FR-031: <2s library) per constitution caching principle

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately (required only for US3)
- **Foundational (Phase 2)**: No dependencies - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User Story 1 (In-Book Search) can proceed independently after Foundational
  - User Story 2 (Library Search) can proceed independently after Foundational
  - User Story 3 (Semantic Search) can proceed independently after Foundational
- **Polish (Phase 6)**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1) - In-Book Keyword Search**: Can start after Foundational (Phase 2) - No dependencies on other stories - INDEPENDENT
- **User Story 2 (P2) - Cross-Book Library Search**: Can start after Foundational (Phase 2) - Uses same SearchQuery/SearchResult structures - INDEPENDENT (can test with just keyword search)
- **User Story 3 (P3) - Semantic Search**: Can start after Foundational (Phase 2) - Extends existing search endpoints with mode parameter - INDEPENDENT (adds semantic mode to US1/US2)

### Within Each User Story

- Backend tasks before frontend tasks (endpoints must exist before UI can call them)
- Data structures (dataclasses) before functions that use them
- Core search logic before API endpoints
- API endpoints before UI JavaScript
- HTML templates before JavaScript files that reference DOM elements
- All parallelizable tasks marked [P] can run simultaneously

### Parallel Opportunities

**Phase 1 (Setup)**: All 3 tasks can run in parallel
**Phase 2 (Foundational)**: T005, T006, T007 (dataclasses) can run in parallel after T004 (enums)
**Phase 3 (User Story 1)**:
  - Backend: T011 (search_text) can be parallel with T012 (search_book) if working on different sections
  - Frontend: T017 (CSS) parallel with T018-T019 (HTML templates), all before T020-T026 (JS)
**Phase 4 (User Story 2)**:
  - Backend: T027, T028, T029 (dataclasses) can all run in parallel
  - Frontend: T035, T036 (HTML) can run in parallel before T037-T042 (JS)
**Phase 5 (User Story 3)**:
  - Backend: T043, T044 (dataclasses/init) can run in parallel
  - Frontend: T055, T056 (mode toggles) can run in parallel before integration tasks
**Phase 6 (Polish)**: T063, T064, T065, T069, T070 can all run in parallel

**Cross-Story Parallelization**: After Phase 2 completion, User Stories 1, 2, and 3 can be worked on in parallel by different developers or tackled sequentially by priority.

---

## Parallel Example: User Story 1 Backend

```bash
# These tasks can run in parallel (different code sections):
Task T011: Implement search_text() function (pure utility function)
Task T013: Add GET /api/search/{book_id} endpoint skeleton (FastAPI route)

# Then sequentially:
Task T012: Implement search_book() (uses search_text from T011)
Task T014: Add error handling to endpoint (completes T013)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only) - Recommended

1. Complete Phase 1: Setup (T001-T003) - ~5 minutes
2. Complete Phase 2: Foundational (T004-T010) - ~1 hour (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (T011-T026) - ~3-4 hours
4. **STOP and VALIDATE**:
   - Open processed book (e.g., dracula_data)
   - Search for common term (e.g., "vampire")
   - Verify all results listed with chapter context
   - Click result, verify navigation to exact highlighted occurrence
5. **MVP COMPLETE** - Deploy/demo in-book keyword search

**Total MVP Effort**: ~4-5 hours for complete in-book keyword search functionality

### Incremental Delivery

1. **Foundation** (Phases 1-2) → Data structures and utilities ready
2. **MVP** (Phase 3) → Test independently → **Deploy/Demo** - In-Book Keyword Search working
3. **Enhanced** (Phase 4) → Test independently → **Deploy/Demo** - Library-wide search added
4. **Advanced** (Phase 5) → Test independently → **Deploy/Demo** - Semantic search enabled
5. **Production** (Phase 6) → Polish, validate, optimize → **Final Release**

Each phase adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers after Foundational phase:

1. **Team completes Setup + Foundational together** (Phases 1-2)
2. Once Foundational is done:
   - **Developer A**: User Story 1 (In-Book Search) - T011-T026
   - **Developer B**: User Story 2 (Library Search) - T027-T042
   - **Developer C**: User Story 3 (Semantic Search) - T043-T062
3. Stories complete and integrate independently
4. Integration testing: Verify mode toggle switches between keyword (US1/US2) and semantic (US3)

---

## Performance & Quality Gates

### Performance Targets (from spec.md FR-030, FR-031)

- **In-book keyword search**: <500ms for books up to 500 pages (validate with T071)
- **Library-wide search**: <2s for libraries up to 50 books (validate with T071)
- **Semantic search**: <1s single book, <3s library-wide (validate after T054)
- **Debouncing**: 300ms delay (implemented in T021, T038)

### Security Checklist (Constitution Principles IV, V)

- ✅ T010: HTML entity escaping for XSS prevention (FR-012a)
- ✅ T064: Book ID validation against enumerated directories (path traversal prevention)
- ✅ T063: Regex injection prevention in search terms

### Quality Validation (before Phase 6 completion)

- [ ] All search modes (keyword, semantic) work for both in-book and library scopes
- [ ] Empty query handling (FR-010: clear search) works consistently
- [ ] Partial failure messaging (FR-022a) displays correctly for library search
- [ ] Result count limiting (FR-008a: 1000 max) and truncation messaging works
- [ ] Highlighting works for all occurrences with exact scroll-to-occurrence (FR-005, FR-011)
- [ ] Multilingual search (English + Chinese) works with correct diacritic normalization (FR-009)

---

## Notes

- **[P] tasks** = different files or independent code sections, no dependencies, can run in parallel
- **[Story] label** = Maps task to specific user story (US1, US2, US3) for traceability
- **Automated tests excluded**: No automated test tasks generated (not explicitly requested in spec.md); use T071 for manual verification
- **File structure**: Single-project at repository root (search_service.py, vector_search.py, server.py, templates/, static/)
- **Commit strategy**: Commit after each task or logical group (e.g., all dataclasses, all endpoints)
- **Checkpoints**: Stop after each user story phase to validate independently before proceeding
- **Avoid**: Cross-story dependencies that break independence, vague task descriptions, same-file edit conflicts

---

## Total Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 7 tasks (BLOCKING)
- **Phase 3 (User Story 1 - P1)**: 16 tasks - **MVP SCOPE**
- **Phase 4 (User Story 2 - P2)**: 16 tasks
- **Phase 5 (User Story 3 - P3)**: 20 tasks
- **Phase 6 (Polish)**: 11 tasks

**Total**: 73 tasks

**MVP Scope (Phases 1-3)**: 26 tasks (~4-5 hours)
**Full Feature (All Phases)**: 73 tasks (~20-25 hours)
