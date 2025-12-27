# AI Response Speed Optimization (Ollama / Local)

Most “slow” AI responses come from:
1) large prompts (RAG context + chat history), and/or
2) long generations (high `max_tokens`), and/or
3) a large/slower model.

## Tune `rag_k` and `max_tokens`

These values are currently sent by the frontend in the request payloads.

- Q&A request knobs:
  - `rag_k`: `src/reader3_app/web/static/ai.js` (search for `rag_k: 5`)
  - `max_tokens`: `src/reader3_app/web/static/ai.js` (search for `max_tokens: 1000`)
- Summary request knob:
  - `max_tokens`: `src/reader3_app/web/static/ai.js` (search for `max_tokens: 2000`)
- Backend fallback defaults (only used if the client doesn’t send values):
  - `src/reader3_app/web/server.py` (`AIQuestionRequest` / `AISummaryRequest`)

Practical presets:
- Faster Q&A: `rag_k=3`, `max_tokens=384` or `512`
- Balanced Q&A: `rag_k=5`, `max_tokens=768`
- Faster summaries: `max_tokens=800`–`1200`

## Reduce chat history window (context bloat)

- The client currently sends the last ~50 messages: `src/reader3_app/web/static/ai.js` (search for `slice(-50)`).
- Use **New chat** for a fresh thread to keep context smaller.

## Use a faster local model

Smaller models are dramatically faster on the same machine:
- Fast: `qwen3:4b`, `llama3.2:3b`
- Balanced: `qwen2.5:7b` / `qwen3:8b`
- Higher quality (slower): `qwen2.5:14b`

Update `config/ai_settings.json` → `providers.ollama.model_name`, restart `reader3-server`.

## Streaming (`stream=true`) and perceived speed

Streaming improves perceived latency (text appears earlier) but doesn’t necessarily increase tokens/sec.

- Backend: `POST /api/ai/question/{book_uuid}?stream=true` (SSE), see `src/reader3_app/web/server.py`
- Frontend: enabled via Settings, see `src/reader3_app/web/static/ai.js`

## macOS GPU acceleration notes (Apple Silicon)

Ollama on Apple Silicon typically uses Metal automatically when running the native `arm64` build.

- Check binary arch: `file "$(which ollama)"`
- If Ollama runs under Rosetta (`x86_64`), performance is much worse—use the native arm64 build instead.
