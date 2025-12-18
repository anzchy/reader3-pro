# Repository Guidelines

## Project Structure

- `reader3.py`: EPUB ingestion + conversion into a pickled `Book` (`book.pkl`) and extracted `images/`.
- `server.py`: FastAPI app that serves the library + reader UI on `http://127.0.0.1:8123`.
- `templates/`: Jinja2 HTML templates (`library.html`, `reader.html`).
- `specs/`: Feature specs and checklists (source of truth for acceptance behavior).
- Generated/ignored: `books/*_data/` (processed books), `.venv/`, and typically `*.epub` (see `.gitignore`).

## Build, Test, and Development Commands

This repo uses `uv` for dependency management and execution.

- Install deps: `uv sync`
- Process a book (creates `<book>_data/`): `uv run reader3.py path/to/book.epub`
- Run the web server: `uv run server.py`

If you need a clean re-process, delete the corresponding `*_data/` folder and rerun `reader3.py`.

## Coding Style & Naming

- Python: 4-space indentation, keep functions small and readable, prefer explicit names over abbreviations.
- Types/data: extend the existing `@dataclass` models (`Book`, `ChapterContent`, `TOCEntry`) instead of introducing parallel structures.
- Files: keep top-level scripts focused (`reader3.py` for parsing, `server.py` for web). Template changes belong in `templates/`.

## Testing Guidelines

There is no automated test suite currently. Validate changes by:

1. Running `uv run reader3.py <epub>` and confirming `*_data/book.pkl` and `*_data/images/` are created.
2. Running `uv run server.py` and exercising library + reader flows in the browser.
3. Using `specs/` acceptance scenarios when implementing new features (e.g., search).

## Commit & Pull Request Guidelines

Git history currently contains only `init commit`, so no strict convention exists. Use:

- Short, imperative commit messages (e.g., “Add in-book search UI”).
- One logical change per commit when possible.

- Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`,  `docs: ...`, `refactor: ...`); keep commits scoped and readable.
- Note which tests were run and call out follow-ups or known gaps.

For PRs: include a clear description, link relevant `specs/` docs/issues, and add screenshots for template/UI changes.PRs should summarize the change, link issues/tasks, and include screenshots or Markdown diffs for UI or output changes.



## Security & Data Notes

- `book.pkl` is loaded via `pickle`; only process trusted EPUBs and avoid accepting untrusted uploads without hardening.
- Don’t commit generated `*_data/` outputs or large binaries unless explicitly intended.
