# 📚 Reader3 Pro - Book Exploration Demos

This directory contains demonstration scripts and notebooks for exploring EPUB book data structures using "The Cold Start Problem" as an example.

## 📂 Files

### 1. `explore_book.ipynb` - Interactive Jupyter Notebook
Comprehensive 10-section notebook for interactive book exploration:
- Load and inspect book.pkl structure
- Metadata and chapter analysis
- Keyword search with context
- RAG-based semantic search using ChromaDB
- Word frequency analysis
- Export analysis to JSON

**Run it**:
```bash
cd demo
jupyter notebook explore_book.ipynb
```

### 2. `demo_book_exploration.py` - Basic Analysis Script
Standalone Python script demonstrating basic book analysis without ML dependencies:
- Metadata extraction (title, author, ISBN, etc.)
- Chapter statistics (word count, character count)
- Keyword search (finds 1,549 occurrences of "network")
- Word frequency analysis (top 20 words)

**Run it**:
```bash
python demo/demo_book_exploration.py
# or
cd demo
python demo_book_exploration.py
```

### 3. `demo_rag_search.py` - RAG Semantic Search Demo
Advanced demonstration of RAG-based semantic search:
- Vector embeddings using `paraphrase-multilingual-MiniLM-L12-v2`
- ChromaDB integration for vector storage
- Semantic search with similarity scores
- Example queries showing intelligent content retrieval

**Requirements**: ChromaDB and sentence-transformers (already installed)

**Run it**:
```bash
python demo/demo_rag_search.py
# or
cd demo
python demo_rag_search.py
```

### 4. `BOOK_EXPLORATION_DEMO.md` - Complete Documentation
Detailed documentation with:
- Demo results and statistics
- Sample outputs from all scripts
- Technical notes on ChromaDB integration
- Performance metrics
- Next steps for AI assistant feature

## 🎯 Quick Start

### Run Basic Demo (No ML Dependencies)
```bash
python demo/demo_book_exploration.py
```

### Run RAG Semantic Search
```bash
python demo/demo_rag_search.py
```

### Open Interactive Notebook
```bash
jupyter notebook demo/explore_book.ipynb
```

## 📊 What You'll Learn

### Book Data Structure
- How EPUB books are processed and stored in `book.pkl`
- Spine vs TOC (linear reading vs hierarchical navigation)
- Metadata structure (title, authors, publisher, ISBN)
- Chapter content (HTML and plain text versions)
- Image handling and path mappings

### Search Capabilities

**Keyword Search**:
- Fast exact matching with regex
- Case-sensitive/insensitive options
- Context extraction (±50 characters around match)
- Perfect for known terms

**RAG Semantic Search**:
- Understands meaning, not just keywords
- Finds relevant content without exact matches
- 384-dimensional embeddings
- Cosine similarity scoring
- Natural language queries

### Example Results

**Book**: The Cold Start Problem by Andrew Chen

**Statistics**:
- 51 chapters
- 102,196 words
- 624,146 characters
- 38 images

**Keyword Search**: "network" → 1,549 occurrences

**Semantic Search Examples**:
- "How do companies solve the cold start problem?" → Found Chapter 8 (68.9% similarity)
- "What are network effects?" → Found Chapter 5 (87.3% similarity)
- "Examples of successful product launches" → Found Chapter 15 (52.9% similarity)

**Top Words**: network (1,108), product (615), users (540), new (477)

## 🔧 Technical Details

### Dependencies
All dependencies are already installed via `uv`:
- `pickle` - Serialize/deserialize book data
- `chromadb` - Vector database for RAG
- `sentence-transformers` - Embedding model
- `jupyter` - Interactive notebooks

### Embedding Model
- **Model**: paraphrase-multilingual-MiniLM-L12-v2
- **Dimensions**: 384
- **Size**: ~420MB (cached after first download)
- **Cache**: `~/.cache/huggingface/hub/` (macOS/Linux)
- **Languages**: Multilingual support (English, Chinese, etc.)

### Performance
- **Book Loading**: Instant (pickle deserialization)
- **Keyword Search**: <1 second for thousands of matches
- **Vector Indexing**: ~1 minute for 48 chapters
- **Semantic Search**: <1 second per query (after indexing)

## 🚀 Use Cases

These demos demonstrate the foundation for the upcoming **002-ai-assistant** feature:

1. **AI Book Summary** (P1):
   - Extract chapter text for LLM context
   - Use RAG to retrieve relevant passages
   - Generate intelligent summaries

2. **Multi-Provider Support** (P2):
   - Send book context to Claude, OpenAI, Gemini, Ollama, OpenRouter
   - Support different AI models

3. **Q&A with Books** (P1):
   - Use semantic search to find relevant content
   - Provide context to AI for accurate answers
   - Maintain conversation history

4. **Settings Configuration** (P3):
   - Configure API keys for different providers
   - Select default AI model
   - Adjust search parameters

## 📖 Further Reading

- **Feature Spec**: `../specs/002-ai-assistant/spec.md`
- **Search Implementation**: `../search_service.py`
- **Book Processing**: `../reader3.py`
- **Project Guide**: `../CLAUDE.md`

## 💡 Experiment Ideas

Use the Jupyter notebook (Section 10) to try:
- Compare text similarity between chapters
- Extract keywords and themes
- Generate AI summaries using API calls
- Create knowledge graphs
- Analyze writing style
- Track character mentions
- Build chapter recommendation system

Have fun exploring! 🎉
