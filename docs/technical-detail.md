# Technical Details (Index)

This directory collects implementation notes and “where things live” references that tend to get lost in chat history.

## Contents

- Storage & data locations: `docs/storage-and-data-locations.md`
- Library collections (004): `docs/library-collections.md`
- AI providers & privacy (what gets sent to cloud APIs): `docs/ai-providers-and-privacy.md`
- AI response speed tuning (Ollama/local): `docs/ai-speed-optimization.md`
- Models & caches (HuggingFace / Ollama / offline notes): `docs/models-and-caches.md`
- Export / import (settings, conversation export formats): `docs/export-import.md`

## Recent updates

- EPUB renderer now stores the original file at `books/{book_id}/book.epub` (details in storage & data locations).
- Reader rendering now uses epub.js in an iframe (`/static/js/epub-renderer.js`), with `book.pkl` reserved for metadata/TOC/search.
- Annotations now support an optional `cfi` anchor field and color for underline/wavy (details in storage & data locations).

## Update Rule (project convention)

When we add/modify any “record-like” behavior (e.g. where data is stored, new files/folders created, new env vars, new endpoints that persist state), update the relevant doc(s) in this directory.
