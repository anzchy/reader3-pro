<!--
Sync Impact Report:
Version change: [none] → 1.0.0
Modified principles: Initial constitution creation
Added sections:

  - I. Data Structures First
  - II. Simplicity Over Engineering
  - III. File-Based State Management
  - IV. HTML Content Sanitization
  - V. Path Security
  - VI. Explicit Over Implicit
  - VII. Performance Through Caching
  - Architecture Standards section
  - Python Development Standards section
  - Security Requirements section
Removed sections: None
Templates requiring updates:
    ✅ .specify/templates/plan-template.md (reviewed - compatible with constitution)
    ✅ .specify/templates/spec-template.md (reviewed - compatible with constitution)
    ✅ .specify/templates/tasks-template.md (reviewed - compatible with constitution)
Follow-up TODOs: None
-->

# Reader3 Pro Constitution

## Core Principles

### I. Data Structures First

**Definition**: All application logic MUST be built on well-defined, strongly-typed data structures using Python dataclasses.

**Rules**:
- Every domain entity MUST be defined as a `@dataclass` with explicit type annotations
- Data structures MUST be defined before any code that manipulates them
- Serialization format (currently pickle) MUST be abstracted behind clear interfaces
- No implicit state - all data MUST flow through defined structures
- Comments MUST explain the semantic meaning and relationships of data fields

**Rationale**: The two-step architecture (processing → serving) depends on clear serialization boundaries. Explicit dataclasses provide type safety, self-documentation, and make the separation between EPUB processing and web serving explicit. This prevents architectural drift and makes migration to databases straightforward.

**Examples**:
- ✅ `@dataclass class Book` with typed fields for metadata, spine, toc, images
- ✅ `@dataclass class ChapterContent` with explicit order, href, content separation
- ❌ Using dictionaries or dynamic attributes for domain entities
- ❌ Mixing processing logic with data structure definitions

### II. Simplicity Over Engineering

**Definition**: Code MUST remain minimal, direct, and focused only on the current requirements. No speculative features, abstractions, or architectural complexity without proven need.

**Rules**:
- YAGNI (You Aren't Gonna Need It) is the default - only implement what's explicitly required
- No design patterns, abstractions, or frameworks beyond FastAPI/BeautifulSoup/ebooklib
- No dependency injection, service locators, or complex object hierarchies
- Keep functions small, focused, and independently testable
- When adding features: prove the need first, implement the simplest solution, resist the temptation to generalize

**Rationale**: As stated in README.md, "Code is ephemeral now and libraries are over." Reader3 Pro is intentionally simple and maintainable by LLMs. Over-engineering reduces clarity and makes the codebase harder to modify. The project's strength is its simplicity - it should remain a clear example of "vibes coding" with LLMs.

**Examples**:
- ✅ `load_book()` with `lru_cache` - simple, effective caching
- ✅ Filesystem-based library management - no database until proven necessary
- ❌ Adding ORM, repository pattern, or abstraction layers
- ❌ Creating plugin systems or extensibility frameworks
- ❌ Implementing user authentication before it's actually needed

### III. File-Based State Management

**Definition**: The filesystem IS the database. All persistent state MUST be stored as discrete `{bookname}_data/` directories containing serialized objects and extracted resources.

**Rules**:
- Each processed EPUB MUST create a single `{bookname}_data/` directory
- Directory MUST contain: `book.pkl` (serialized Book object) and `images/` subdirectory
- Library scanning MUST use glob patterns (`*_data/`) - no manifest files or indices
- Book deletion MUST be accomplished by deleting the directory
- No shared state files, global configuration, or cross-book indices
- When migrating to databases: maintain this logical isolation (one book = one record set)

**Rationale**: Filesystem state makes the system transparent, debuggable, and resistant to corruption. Users can inspect, backup, or delete books by operating on directories. This matches the project's philosophy of simplicity and makes the system stateless (web server can be restarted without loss).

**Examples**:
- ✅ `dracula_data/book.pkl` and `dracula_data/images/pic001.jpg`
- ✅ Deleting `dracula_data/` removes the book from library
- ❌ Maintaining a `library.db` or `books.json` index
- ❌ Storing metadata outside book directories

### IV. HTML Content Sanitization

**Definition**: All HTML content extracted from EPUBs MUST be sanitized to remove executable code while preserving readable structure.

**Rules**:
- `clean_html_content()` MUST remove: `<script>`, `<style>`, `<iframe>`, event handlers
- MUST preserve: semantic HTML (headings, paragraphs, lists), links, images
- Plain text extraction (`ChapterContent.text`) MUST strip ALL HTML for LLM consumption
- Image paths MUST be rewritten to match server routes (`images/{filename}`)
- NO user-generated HTML should ever bypass sanitization
- Consider BeautifulSoup's `get_text()` for text extraction, manual stripping for content display

**Rationale**: EPUBs are user-provided archives containing arbitrary HTML. Without sanitization, malicious EPUBs could execute JavaScript in the reader interface. The project's stated use case (copying to LLMs) requires clean text, making sanitization both a security requirement and a feature necessity.

**Examples**:
- ✅ Removing `<script>alert('XSS')</script>` from chapter content
- ✅ Stripping `onclick="..."` attributes from elements
- ❌ Serving raw EPUB HTML without cleaning
- ❌ Allowing `<iframe>` elements in chapter display

### V. Path Security

**Definition**: All file path operations involving user-controlled input (book IDs, image names) MUST be sanitized to prevent directory traversal attacks.

**Rules**:
- Image serving MUST use `os.path.basename()` to strip directory components
- Book ID lookups MUST validate against enumerated directory list (glob results)
- Never construct paths directly from URL parameters without validation
- Use Path objects (`pathlib.Path`) for safer path manipulation
- When accepting filenames: validate against allowlist patterns (e.g., `[a-zA-Z0-9_.-]+`)
- Log all rejected path access attempts

**Rationale**: The image serving endpoint `/read/{book_id}/images/{image_name}` is vulnerable to path traversal if not properly sanitized. An attacker could request `../../etc/passwd` without basename sanitization. This is currently flagged in CLAUDE.md as requiring review for production use.

**Examples**:
- ✅ `os.path.basename(image_name)` ensures only filename, no path traversal
- ✅ Validating `book_id` against known `*_data/` directories
- ❌ `Path(book_id) / 'images' / image_name` without validation
- ❌ Trusting user input in file paths

### VI. Explicit Over Implicit

**Definition**: Code MUST favor explicit, verbose clarity over clever brevity. Every architectural decision, data structure relationship, and non-obvious operation MUST be documented.

**Rules**:
- Critical distinctions (like spine vs TOC) MUST be commented in code and documentation
- Type hints MUST be used on all function signatures and dataclass fields
- Magic numbers or string literals MUST be named constants
- Function names MUST clearly describe what they do (e.g., `clean_html_content` not `clean`)
- Comments MUST explain "why" not "what" - the code shows what, comments explain rationale

**Rationale**: The project is designed for LLM interaction - explicit code is easier for both humans and LLMs to understand and modify correctly. The spine/TOC distinction is architecturally critical but subtle; making it explicit prevents bugs during feature additions.

**Examples**:
- ✅ Comments explaining spine (reading order) vs TOC (navigation hierarchy)
- ✅ `ChapterContent` with explicit `order: int` field for spine position
- ✅ Type-annotated function signatures: `def load_book(book_id: str) -> Book:`
- ❌ Using indices without explaining what they represent
- ❌ Implicit assumptions about HTML structure

### VII. Performance Through Caching

**Definition**: Performance optimizations MUST use simple, proven patterns (caching, lazy loading) before considering architectural changes.

**Rules**:
- Use Python stdlib caching (`functools.lru_cache`) for expensive operations
- `load_book()` MUST remain cached with appropriate `maxsize` for deployment scale
- Document cache invalidation strategy when adding mutating operations
- Profile before optimizing - measure, don't guess
- Acceptable performance targets: <500ms page load, <100ms navigation
- When caching is insufficient: consider pagination before architectural rewrites

**Rationale**: The `lru_cache(maxsize=10)` on book loading is sufficient for the current use case (self-hosted, single user). Premature optimization would complicate the codebase. When scaling requirements emerge, the constitution guides toward proven patterns (CDN, larger cache) before suggesting database migration.

**Examples**:
- ✅ `@lru_cache(maxsize=10)` on `load_book()`
- ✅ Measuring load times before adding complexity
- ❌ Implementing Redis caching without measuring need
- ❌ Rewriting to async without profiling

## Architecture Standards

### Two-Step Processing Model

The application MUST maintain architectural separation between:

**Step 1: EPUB Processing (`reader3.py`)**
- Stateless script: takes EPUB file → produces `{bookname}_data/` directory
- Pure data transformation - no server dependencies
- Handles: parsing, cleaning, structure extraction, serialization
- Must be runnable independently via `uv run reader3.py <file.epub>`

**Step 2: Web Server (`server.py`)**
- Stateless server: loads pre-processed books on demand
- No EPUB processing during request handling
- Handles: routing, template rendering, caching, static file serving
- Must be restartable without data loss

**Critical invariant**: Processing and serving MUST remain decoupled. The server never modifies `book.pkl` files.

### Template Architecture

Jinja2 templates MUST follow this structure:

**`library.html`**: Grid view of all books
- Displays: covers, titles, authors from metadata
- Links to: `/read/{book_id}/0` (first spine item)

**`reader.html`**: Reading interface
- Left sidebar: Recursive TOC navigation (uses `render_toc()` macro)
- Center panel: Current spine item content
- Bottom nav: Previous/Next spine navigation
- JavaScript: Maps TOC clicks → spine indices via href lookup

**Template requirements**:
- Use template inheritance for shared layout
- All static assets (CSS/JS) MUST be inlined or served from `/static`
- No external CDN dependencies without explicit justification
- Mobile-responsive by default

### Dependency Management

Dependencies MUST be managed via `uv` with these constraints:

- Core dependencies: `beautifulsoup4`, `ebooklib`, `fastapi`, `jinja2`, `uvicorn`
- Version pinning: Use `>=` for minor version flexibility
- New dependencies require justification: what problem does it solve? Why can't stdlib/existing deps handle it?
- NO frontend frameworks (React, Vue) without architectural discussion - keep it simple
- Python version: `>=3.10` for dataclass and type hint features

## Python Development Standards

### Code Style

- Follow PEP 8 with Black formatting (line length: 100 characters)
- Use type hints on all function signatures and class attributes
- Imports: stdlib → third-party → local (separated by blank lines)
- Docstrings: Google-style for public APIs, inline comments for complex logic

### Error Handling

- Use appropriate exception types - don't catch broad `Exception` without reraising
- FastAPI routes: raise `HTTPException` with appropriate status codes
- File operations: catch `FileNotFoundError`, `PermissionError` specifically
- EPUB processing: fail fast with clear error messages (don't produce corrupt `book.pkl`)
- Log errors before raising when context would be lost

### Testing Philosophy

Testing is OPTIONAL for this project. When tests ARE added:

- Focus on contract tests (public API behavior) over unit tests
- Test data transformations (EPUB → Book structure) not trivial getters
- Use `pytest` as test runner
- Test directory structure: `tests/contract/`, `tests/integration/`
- Mock filesystem operations, not library code
- Don't test framework code (FastAPI, BeautifulSoup) - trust them

### Logging

- Use Python stdlib `logging` module - no third-party loggers
- Log levels: DEBUG (trace execution), INFO (book processing events), WARNING (sanitization removals), ERROR (failures)
- Include context: book IDs, file paths, operation names
- When adding features: log state transitions and user actions for debugging

## Security Requirements

### Input Validation

- EPUB files: Validate file magic bytes (PK\x03\x04 for ZIP), reject if invalid
- File sizes: Reject EPUBs >100MB (configurable constant)
- Filenames: Sanitize to prevent path traversal when creating `{bookname}_data/`
- URL parameters: Validate all IDs against enumerated safe values

### Content Security

- HTML sanitization: Remove scripts, iframes, event handlers (see Principle IV)
- Image serving: Basename validation, no directory traversal (see Principle V)
- No user authentication currently - assume trusted local environment
- When adding auth: use proven libraries (e.g., `python-jose`, `passlib`), never roll crypto

### Deployment Considerations

Current deployment model: `127.0.0.1:8123` (localhost only)

For production deployment:
- MUST add authentication before exposing to internet
- MUST serve behind reverse proxy (nginx/Caddy) with rate limiting
- MUST use HTTPS with valid certificates
- MUST implement file upload size limits and MIME type validation
- SHOULD implement CSRF protection (FastAPI middleware)
- SHOULD add security headers (CSP, X-Frame-Options, etc.)

## Governance

### Authority

This constitution supersedes all other development guidance. When conflicts arise between this document and other templates/specifications, the constitution takes precedence.

### Amendment Process

1. Amendments MUST be proposed with rationale and impact analysis
2. Version bumps follow semantic versioning:
   - **MAJOR**: Principle removal/redefinition, architectural breaking changes
   - **MINOR**: New principles, expanded guidance, new requirement sections
   - **PATCH**: Clarifications, typo fixes, example additions
3. After amendment: update dependent templates (plan, spec, tasks) for consistency
4. Sync Impact Report MUST be included as HTML comment at top of constitution

### Compliance

- All specifications MUST include Constitution Check section validating principle adherence
- Pull requests SHOULD reference which principles guided implementation decisions
- When violating principles: MUST justify in Complexity Tracking table with rationale
- Unjustified complexity or principle violations MUST be rejected in code review

### Living Document

- Review this constitution when:
  - Starting major architectural changes (e.g., database migration)
  - Adding cross-cutting concerns (auth, search, annotations)
  - Project scales beyond original assumptions (multi-user, >100 books)
- Update examples to reflect current codebase patterns
- Remove outdated constraints when requirements genuinely change

### Runtime Guidance

For development-time guidance and examples, refer to:
- `CLAUDE.md` - Project overview, commands, architecture deep-dive
- `README.md` - Quick start and project philosophy
- `reader3-enhancement-workflow.md` - Planned feature roadmap
- `search-features-workflow.md` - Search implementation plans



## Commit & Pull Request Guidelines

- Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`,  `docs: ...`, `refactor: ...`); keep commits scoped and readable.
- PRs should summarize the change, link issues/tasks, and include screenshots or Markdown diffs for UI or output changes.
- Note which tests were run and call out follow-ups or known gaps.



**Version**: 1.0.0 | **Ratified**: 2025-12-17 | **Last Amended**: 2025-12-17
