# Technical Details (Index)

This directory collects implementation notes and “where things live” references that tend to get lost in chat history.

## Contents

- Storage & data locations: `docs/technical-detail/storage-and-data-locations.md`
- AI providers & privacy (what gets sent to cloud APIs): `docs/technical-detail/ai-providers-and-privacy.md`
- AI response speed tuning (Ollama/local): `docs/technical-detail/ai-speed-optimization.md`
- Models & caches (HuggingFace / Ollama / offline notes): `docs/technical-detail/models-and-caches.md`
- Export / import (settings, conversation export formats): `docs/technical-detail/export-import.md`

## Update Rule (project convention)

When we add/modify any “record-like” behavior (e.g. where data is stored, new files/folders created, new env vars, new endpoints that persist state), update the relevant doc(s) in this directory.
