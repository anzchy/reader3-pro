# Models & Caches (HuggingFace / Ollama)

## Ollama model storage

By default, Ollama stores models in a user-managed location (Ollama-managed). For portable/offline project setups, you can point Ollama at a project folder:

```bash
mkdir -p models/ollama
export OLLAMA_MODELS="$PWD/models/ollama"
ollama pull qwen3:8b
```

## HuggingFace model cache (SentenceTransformers / embeddings)

The semantic index uses a SentenceTransformers embedding model. The first run downloads the model and caches it.

Default cache location:
- macOS / Linux: `~/.cache/huggingface/hub/`
- Windows: `%USERPROFILE%\\.cache\\huggingface\\hub\\`

### Portable cache inside the repo (recommended for offline copying)

```bash
mkdir -p models/huggingface
HF_HOME="$PWD/models/huggingface" uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### Fully offline mode (no HuggingFace network calls)

```bash
export HF_HOME="$PWD/models/huggingface"
export TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1
export READER3_EMBED_MODEL="$PWD/models/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/<snapshot-id>"
```

Then re-index the book if needed.
