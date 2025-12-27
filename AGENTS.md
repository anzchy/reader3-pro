# Repository Guidelines

## Project Structure

- `src/reader3_app/reader3.py`: EPUB ingestion + conversion into `books/<book_id>_data/` (pickled `Book` in `book.pkl`, original `book.epub`, extracted `images/`).
- `src/reader3_app/web/server.py`: FastAPI app (library + reader UI, plus JSON APIs) on `http://127.0.0.1:8123`.
- `src/reader3_app/web/templates/`: Jinja2 templates (`library.html`, `reader.html`, `settings.html`).
- `src/reader3_app/web/static/`: UI assets (search, settings, AI assistant JS/CSS).
- `src/reader3_app/search_service.py`: Library + in-book search (query parsing, highlighting, API helpers).
- `src/reader3_app/vector_search.py`: Vector/RAG indexing and retrieval (ChromaDB).
- `src/reader3_app/notes_service.py`: Per-book notes/annotations persistence (`notes.json`) + helpers.
- `src/reader3_app/models/`: Shared dataclasses/models (e.g. annotations schema).
- `src/reader3_app/ai/`: AI assistant orchestration (providers, routing, RAG, disk conversations).
- `config/`: Runtime settings (notably `config/ai_settings.json` is gitignored; see `config/ai_settings.example.json`).
- `books/`: Local library root; processed books live in `books/<book_id>_data/` (may contain `book.pkl`, `book.epub`, `images/`, `ai_conversations/`, `chroma_db/`, `notes.json`).
- `specs/`: Feature specs + checklists + API contracts (source of truth for acceptance behavior).
- `docs/`: Data locations, settings, and persistence details.
- Generated/ignored (see `.gitignore`): `books/*_data/`, `.venv/`, `conversations/`, and typically `*.epub`.

## Build, Test, and Development Commands

This repo uses `uv` for dependency management and execution.

- Install deps: `uv sync`
- Process a book (creates `books/<book>_data/`): `uv run reader3 path/to/book.epub`
- Index a processed book for vector/RAG search: `uv run reader3 --index <book_id>` (e.g. `dracula_data`)
- Run the web server: `uv run reader3-server`

If you need a clean re-process, delete the corresponding `books/*_data/` folder and rerun `reader3`.

You can override the default `books/` directory via `READER3_BOOKS_DIR`.

## Coding Style & Naming

- Python: 4-space indentation, keep functions small and readable, prefer explicit names over abbreviations.
- Types/data: extend the existing `@dataclass` models (`Book`, `ChapterContent`, `TOCEntry`) instead of introducing parallel structures.
- Files: keep modules focused (`reader3_app/reader3.py` for parsing, `reader3_app/web/server.py` for web). Template changes belong in `reader3_app/web/templates/`.

## Testing Guidelines

There is no automated test suite currently. Validate changes by:

1. Running `uv run reader3 <epub>` and confirming `books/*_data/book.pkl` and `books/*_data/images/` are created.
2. Running `uv run reader3-server` and exercising library + reader flows in the browser.
3. Using `specs/` acceptance scenarios when implementing new features (e.g., search).

## Commit & Pull Request Guidelines

Git history currently contains only `init commit`, so no strict convention exists. Use:

- Short, imperative commit messages (e.g., “Add in-book search UI”).
- One logical change per commit when possible.
- Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs: ...`, `refactor: ...`); keep commits scoped and readable.
- Note which tests were run and call out follow-ups or known gaps.

For PRs: include a clear description, link relevant `specs/` docs/issues, and add screenshots or Markdown diffs for UI/output changes.

## Security & Data Notes

- `book.pkl` is loaded via `pickle`; only process trusted EPUBs and avoid accepting untrusted uploads without hardening.
- Don’t commit generated `*_data/` outputs or large binaries unless explicitly intended.

## Documentation Rule (Technical Details)

- When adding/changing any “record-like” behavior (data storage locations, new persisted files/folders, new env vars, new endpoints that persist state), update the technical docs:
  - `docs/technical-detail.md`
  - and the relevant page(s) under `docs/`
