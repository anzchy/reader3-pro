# AI Providers & Privacy (What Gets Sent Where)

## Local vs cloud

- **Local (Ollama)**: all prompts/context stay on your machine (Reader3 server → Ollama on `localhost`).
- **Cloud providers** (Anthropic/OpenAI/Gemini/OpenRouter): the server sends a request over HTTPS to the provider API. Any included context leaves your machine.

## What content is sent to a cloud provider?

In this project, Q&A/summary are implemented as **RAG** by default:

1. Server retrieves top‑k relevant chunks from the local index at `books/{book_id}/chroma_db/`
   - `book_id` is the processed folder name (e.g. `dracula_data`) under `books/`
2. Server builds a prompt using:
   - your question
   - recent chat history (client sends it)
   - retrieved book chunks (citations)
3. Server calls the provider API and returns the answer

This means:
- It typically sends **a handful of excerpts**, not the entire book.
- Those excerpts + your question + recent conversation **do** leave your machine when using cloud providers.

If you want **zero book content** leaving your computer, use the Ollama provider.

## What controls “how much text is sent”?

Primary knobs:
- `rag_k`: number of retrieved chunks included in the prompt
- Chat history window: how many recent messages are sent each turn
- Chunking strategy: chunk size/overlap when building the index (requires re-index)

Where these are currently controlled:
- Client request payloads: `src/reader3_app/web/static/ai.js` (search for `rag_k`, `slice(-50)`, `max_tokens`)
- Index chunking: `src/reader3_app/vector_search.py` (`_chunk_text(...)`)

## Provider endpoints (server)

- Q&A: `POST /api/ai/question/{book_uuid}`
- Summary: `POST /api/ai/summary/{book_uuid}`

See implementation: `src/reader3_app/web/server.py`
