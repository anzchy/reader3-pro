# reader 3 Pro

![reader3](reader3.png)

A lightweight, self-hosted EPUB reader that lets you read through EPUB books one chapter at a time. This makes it very easy to copy paste the contents of a chapter to an LLM, to read along. Basically - get epub books (e.g. [Project Gutenberg](https://www.gutenberg.org/) has many), open them up in this reader, copy paste text around to your favorite LLM, and read together and along.

This project is an enhanced version (thus add `pro` to repo name) of Andrie Karpathy's reader3 project.



## How It Works

#### Reader

1. `src/reader3_app/reader3.py` parses an `.epub`, cleans HTML, extracts plain text, and writes a `books/{bookname}_data/` folder.
2. The folder contains `book.pkl` (a pickled `Book` dataclass) and `images/` (extracted assets).
3. `src/reader3_app/web/server.py` serves the Library + Reader UI and reads chapters from `book.pkl` one spine item at a time.

#### Search (Keyword + RAG/Semantic)

- **Keyword search** scans `ChapterContent.text` with Latin diacritic normalization (e.g. `café` → `cafe`) and returns matches with context.
- **Semantic search** is a lightweight local RAG-style retrieval:
  - Indexing chunks each chapter into ~1000-character passages (with overlap), embeds them using `sentence-transformers`, and stores vectors in ChromaDB under `{book_id}/chroma_db/`.
  - Searching embeds your query and retrieves the most similar passages (even without exact keyword matches).

## Project Structure

```text
.
├── src/
│   └── reader3_app/
│       ├── reader3.py              # EPUB processing + (optional) CLI indexing
│       ├── search_service.py       # Keyword + library search logic
│       ├── vector_search.py        # ChromaDB indexing + semantic retrieval
│       ├── ai/                     # AI assistant backend modules
│       └── web/
│           ├── server.py           # FastAPI app
│           ├── templates/          # Jinja templates (library.html, reader.html)
│           └── static/             # JS/CSS for search + AI UI
├── config/
│   └── ai_settings.example.json    # Example AI config (copy to ai_settings.json)
├── specs/                  # Feature specs + tasks (search lives in specs/001-search-features/)
└── books/                  # Generated per-book folders (ignored by git)
    └── *_data/             # One folder per book (book.pkl, images/, chroma_db/)
```



## How to Use 

#### Setup

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## AI Assistant (Anthropic / Ollama)

The AI panel uses the `default_provider` from `config/ai_settings.json` (editable via the web Settings page at `/settings` or by editing the file directly).

1) Copy the example config:

```bash
cp config/ai_settings.example.json config/ai_settings.json
```

2) Make sure the book is indexed for semantic retrieval (required for RAG summary/Q&A citations):

```bash
# 无需带./books/dracula_data
uv run reader3 --index dracula_data
# 成功后后显示：Indexed the-power-broker_data: 4556 chunks using paraphrase-multilingual-MiniLM-L12-v2
```

3) Start the server:

```bash
uv run reader3-server
```

Open a book, click the **AI** button on the right toolbar, and use quick actions or chat.

### Chat History + New Chat

- The AI panel shows a per-book, per-provider chat history list.
- Use **New chat** to start a fresh thread (keeps older threads for reference).
- Conversations are stored in two places:
  - Browser cache: IndexedDB (`reader3_ai_assistant`)
  - On disk (portable): `books/{book_id}/ai_conversations/{conversation_id}.json`

### Use Anthropic (Claude)

Edit `config/ai_settings.json`:

- Set `default_provider` to `"anthropic"`
- Set `providers.anthropic.enabled` to `true`
- Fill `providers.anthropic.api_key`
- Optionally change `providers.anthropic.model_name`

Restart `reader3-server` after changing the config.



#### Anthropic进行AI问答的原理：

 在这个项目里调用流程是这样的（选 anthropic 时）：

1. 浏览器把问题发到本地服务：POST /api/ai/question/{book_uuid}（见 `src/reader3_app/web/server.py`）
2. 服务端先在本地做 RAG 检索：从 books/<book>_data/chroma_db/ 里用向量相似度找 top‑k 段落（见 `src/reader3_app/ai/rag.py:9`、`src/reader3_app/vector_search.py:36`）

3. 把这些段落拼成 context，再加上你的 question 和 conversation_history，组装成 Anthropic 的 messages 请求体（见 `src/reader3_app/web/server.py`）

4. 通过 HTTPS POST https://api.anthropic.com/v1/messages 发给 Anthropic（见 `src/reader3_app/ai/providers/anthropic.py:51`），拿到生成结果后返回前端



 “会发出去多少书的内容”取决于检索参数：

 \- 问答默认 rag_k=5（最多 20），每个 chunk 默认约 1000 字符左右（见 `src/reader3_app/vector_search.py:100`）

 \- “全书总结”会取更多片段：固定取 k=12（见 `src/reader3_app/web/server.py`）

 \- 所以通常是“若干段摘录”，不是整本书；但这些摘录确实会离开本机发送到 Anthropic（再加上你的提问/历史消息）

 如果你不希望任何书籍内容发送到第三方 API，就只用 ollama（本地生成）；不要选 anthropic/gemini。



### Use Ollama (offline / local)

1) Install and start Ollama:

- macOS: `brew install ollama`
- Start: `ollama serve`

2) Download a model into this repo’s `models/` directory (recommended):

```bash
mkdir -p models/ollama
export OLLAMA_MODELS="$PWD/models/ollama"
ollama pull qwen3:8b
```

3) Edit `config/ai_settings.json`:

- Set `default_provider` to `"ollama"`
- Set `providers.ollama.enabled` to `true`
- Set `providers.ollama.base_url` to `"http://localhost:11434"`
- Set `providers.ollama.model_name` to the model you pulled (e.g. `"qwen3:8b"`)

Restart `reader3-server`, then use the AI panel normally.



#### Add a New EPUB (from scratch)

Download an EPUB (e.g. [Dracula EPUB3](https://www.gutenberg.org/ebooks/345)) and run:

```bash
uv run reader3 ./books/dracula.epub
```

This creates `books/dracula_data/`, which registers the book to your local library. Then start the server:

```bash
uv run reader3-server
```

Visit [localhost:8123](http://localhost:8123/) to see your Library. To remove a book, delete its `books/*_data/` folder.

If you already have `*_data/` folders at repo root, move them into `books/`:

```bash
mkdir -p books
find . -maxdepth 1 -type d -name '*_data' -print0 | xargs -0 -I{} mv "{}" books/
```

#### (Optional) Manual Setup: Semantic Search Dependencies (Phase 1)

Keyword search works out of the box. Semantic search needs the extra dependencies and an embedding model:

```bash
uv add chromadb sentence-transformers
uv run python -c "import chromadb, sentence_transformers; print('OK')"
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

The model download is large (~420MB) and is cached by HuggingFace after the first run.

默认会下载到 HuggingFace 的缓存目录：

 \- macOS / Linux：`~/.cache/huggingface/hub/`

 \- Windows：`%USERPROFILE%\.cache\huggingface\hub\`



#### model可以放在两个地方：

1. **单机开发最省事（默认推荐）**

   放在用户缓存：~/.cache/huggingface/hub/（macOS/Linux）或 %USERPROFILE%\.cache\huggingface\hub\（Windows）。优点是不

   用管路径，所有项目共用。

2. **需要“可搬运/离线部署”更推荐**

   放在项目外的固定目录，比如仓库根目录下的 models/huggingface/（并加入 .gitignore），用环境变量把缓存指过去：

```
mkdir -p models/huggingface
HF_HOME="$PWD/models/huggingface" uv run python -c "from sentence_transformers import SentenceTransformer;
SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

 这样模型会落在 models/huggingface/hub/，拷贝整个 models/ 就能离线复用。

如果你希望 **完全离线**（不触发任何 HuggingFace API 调用），建议把模型路径指向本地 snapshot 目录：

```bash
export HF_HOME="$PWD/models/huggingface"
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
export READER3_EMBED_MODEL="$PWD/models/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/86741b4e3f5cb7765a600d3a3d55a0f6a6cb443d"
```

#### Index a Book (Semantic Search)

You can index from the Library UI (the button appears when a book is “Not indexed”), or via CLI:

```bash
uv run reader3 --index dracula_data
```

This writes a per-book vector store to `books/dracula_data/chroma_db/`.



## How to Optimize AI Response Speed using Ollama

Most “slow” AI responses come from (1) long prompts (RAG context + chat history) and/or (2) long generations (high `max_tokens`) and/or (3) a large/slower model.

### Tune `rag_k` and `max_tokens`

These values are currently hard-coded in the frontend request payloads (so changing backend defaults alone won’t help).

- Q&A request knobs:
  - `rag_k`: `src/reader3_app/web/static/ai.js` (search for `rag_k: 5`)
  - `max_tokens`: `src/reader3_app/web/static/ai.js` (search for `max_tokens: 1000`)
- Summary request knob:
  - `max_tokens`: `src/reader3_app/web/static/ai.js` (search for `max_tokens: 2000`)
- Backend fallback defaults (only used if the client doesn’t send values):
  - `src/reader3_app/web/server.py` (`AIQuestionRequest` / `AISummaryRequest`)

Practical presets (start here):
- Faster Q&A: `rag_k=3`, `max_tokens=384` or `512`
- Balanced Q&A: `rag_k=5`, `max_tokens=768`
- Faster summaries: `max_tokens=800`–`1200` (quality may drop vs `2000`)

### Use a faster local model

On the same machine, smaller models are dramatically faster:
- Fast: `qwen3:4b`, `llama3.2:3b`
- Balanced: `qwen2.5:7b` / `qwen3:8b`
- Higher quality (slower): `qwen2.5:14b`

Update `config/ai_settings.json` → `providers.ollama.model_name`, restart `reader3-server`.

### Reduce prompt size (RAG + history)

- Reduce chat history sent each turn: `src/reader3_app/web/static/ai.js` (search for `slice(-50)`).
- Reduce chunk size / overlap for indexing (requires re-index): `src/reader3_app/vector_search.py` (`_chunk_text(chunk_size=1000, overlap=120)`).

### About `stream=true` (perceived speed)

Ollama supports streaming token output, which improves perceived latency (text appears earlier), but does not necessarily increase tokens/sec.

- Backend supports SSE streaming for Q&A: `POST /api/ai/question/{book_uuid}?stream=true` (see `src/reader3_app/web/server.py`).
- Frontend uses streaming when enabled in Settings (see `src/reader3_app/web/static/ai.js`), and shows a **Stop** button to abort the request.

### macOS GPU acceleration notes (Apple Silicon)

Ollama on Apple Silicon typically uses Metal (integrated GPU) automatically when running the native `arm64` build.
- If Ollama is running under Rosetta (`x86_64`), performance is much worse—install the native arm64 version instead.



## How to Search

### Reader (in-book)

Open any book. Click the **search button** in the right-side vertical toolbar to open the search drawer, type your query, then press **Enter**.

- **Mode**: `keyword` (exact) / `semantic` (meaning) / `hybrid` (mix)
- Click a result to jump to that chapter. Keyword results highlight all occurrences and scroll to the selected match.
- Use **×** to clear results/highlights. Toggle **Case sensitive** as needed.

You can also deep-link to a highlighted chapter/occurrence:

`/read/{book_id}/{chapter_index}?q=your+term&occurrence=0`

Where `book_id` is the processed folder name (e.g. `dracula_data`).

### Library (cross-book)

On the Library page, use **Search across your library…** to search across all processed books (`*_data/`).

- Results are grouped by book; click a passage to open the book at the matching chapter/occurrence.
- Use **Sort** (relevance/title/author), **Case**, and **Mode**.
- In semantic/hybrid mode, each book shows its index status; click **Index** to build vectors if needed.



## License

MIT
