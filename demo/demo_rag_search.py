"""
Demo script for RAG-based semantic search on book content
Requires: chromadb, sentence-transformers
"""

import pickle
import sys
from pathlib import Path

# Add parent directory to path to import reader3
sys.path.insert(0, str(Path(__file__).parent.parent))

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry

try:
    import chromadb
    from chromadb.utils import embedding_functions
    print("✅ ChromaDB is available!\n")
except ImportError:
    print("⚠️ ChromaDB not installed. Run: uv add chromadb sentence-transformers")
    print("This will download ~420MB embedding model on first run.")
    exit(1)

print("=" * 70)
print("🔍 RAG Semantic Search Demo - The Cold Start Problem")
print("=" * 70)

# Load book
# Get the script's directory and construct path relative to it
script_dir = Path(__file__).parent
book_path = script_dir.parent / "The-Cold-Start-Problem_data" / "book.pkl"
print(f"\n📖 Loading book from: {book_path}")

with open(book_path, 'rb') as f:
    book = pickle.load(f)

print(f"✅ Book loaded: {book.metadata.title}")
print(f"   Chapters: {len(book.spine)}")

# Initialize ChromaDB client
print("\n📊 Initializing ChromaDB...")
client = chromadb.Client()

# Use multilingual embedding model
print("🤖 Loading embedding model: paraphrase-multilingual-MiniLM-L12-v2")
print("   (This may take a moment on first run - downloading ~420MB model)")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)

# Create collection
print("\n📊 Creating vector collection...")
collection = client.create_collection(
    name="book_chapters",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

print("✅ Collection created!")

# Index chapters
print("\n🔄 Indexing chapters... (this may take a minute)")

documents = []
metadatas = []
ids = []

for chapter in book.spine:
    # Use first 2000 characters for demo
    text_chunk = chapter.text[:2000] if len(chapter.text) > 2000 else chapter.text

    # Skip empty chapters
    if not text_chunk.strip():
        continue

    chunk_id = f"chapter_{chapter.order}"

    documents.append(text_chunk)
    metadatas.append({
        "chapter_id": chapter.id,
        "chapter_title": chapter.title,
        "chapter_order": chapter.order,
        "full_length": len(chapter.text)
    })
    ids.append(chunk_id)

# Add to collection
collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)

print(f"✅ Indexed {len(documents)} chapters!")

# Perform semantic search
print("\n" + "=" * 70)
print("🔍 Semantic Search Examples:")
print("=" * 70)

queries = [
    "How do companies solve the cold start problem?",
    "What are network effects?",
    "Examples of successful product launches"
]

for query in queries:
    print(f"\n📝 Query: '{query}'")
    print("-" * 70)

    results = collection.query(
        query_texts=[query],
        n_results=3,
        include=['documents', 'metadatas', 'distances']
    )

    print(f"\nTop 3 Most Relevant Chapters:\n")
    for i in range(len(results['ids'][0])):
        metadata = results['metadatas'][0][i]
        distance = results['distances'][0][i]
        similarity = 1 - distance  # Convert distance to similarity

        print(f"[{i+1}] Chapter {metadata['chapter_order']}: {metadata['chapter_title']}")
        print(f"    Similarity: {similarity:.3f}")
        print(f"    Preview: {results['documents'][0][i][:150]}...")
        print()

print("=" * 70)
print("✅ RAG semantic search demo complete!")
print("\nThis demonstrates how AI assistants can find relevant content")
print("even when the exact keywords don't match your query.")
print("=" * 70)
