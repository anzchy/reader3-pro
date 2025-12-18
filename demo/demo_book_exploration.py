"""
Demo script to explore book.pkl data structure and demonstrate RAG search
Based on explore_book.ipynb notebook
"""

import pickle
import re
from collections import Counter
from pathlib import Path
import sys

# Add repo src/ to path to import reader3_app
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

# Import Book class so pickle can deserialize
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry

print("=" * 70)
print("📚 Book Data Exploration Demo - The Cold Start Problem")
print("=" * 70)

# 1. Load book.pkl
# Get the script's directory and construct path relative to it
script_dir = Path(__file__).parent
book_path = script_dir.parent / "The-Cold-Start-Problem_data" / "book.pkl"
print(f"\n📖 Loading book from: {book_path}")

with open(book_path, 'rb') as f:
    book = pickle.load(f)

print(f"✅ Book loaded successfully!")
print(f"Type: {type(book).__name__}")

# 2. Explore book metadata
print("\n" + "=" * 70)
print("📊 Book Metadata:")
print("=" * 70)
print(f"Title: {book.metadata.title}")
print(f"Authors: {', '.join(book.metadata.authors)}")
print(f"Publisher: {book.metadata.publisher}")
print(f"Language: {book.metadata.language}")
print(f"Identifiers: {book.metadata.identifiers}")
print()
print(f"📄 Total Chapters (Spine): {len(book.spine)}")
print(f"🗂️ TOC Entries: {len(book.toc)}")
print(f"🖼️ Images: {len(book.images)}")

# 3. Chapter structure analysis
print("\n" + "=" * 70)
print("📑 Chapter Analysis:")
print("=" * 70)

total_text_length = 0
chapter_stats = []

for i, chapter in enumerate(book.spine):
    text_len = len(chapter.text)
    total_text_length += text_len
    word_count = len(chapter.text.split())

    chapter_stats.append({
        'order': chapter.order,
        'title': chapter.title,
        'chars': text_len,
        'words': word_count
    })

# Display first 10 chapters
print(f"\nFirst 10 Chapters:")
for stat in chapter_stats[:10]:
    print(f"  [{stat['order']:2d}] {stat['title'][:50]:50s} | {stat['words']:,} words")

print(f"\n📊 Statistics:")
print(f"  Total text length: {total_text_length:,} characters")
print(f"  Total words: {sum(s['words'] for s in chapter_stats):,}")
print(f"  Average chapter length: {total_text_length // len(book.spine):,} characters")

# 4. Content preview
print("\n" + "=" * 70)
print("📖 First Chapter Preview:")
print("=" * 70)

first_chapter = book.spine[0]
print(f"Title: {first_chapter.title}")
print(f"ID: {first_chapter.id}")
print(f"\nFirst 500 characters:")
print("-" * 70)
print(first_chapter.text[:500])
print("...")

# 5. Simple keyword search
print("\n" + "=" * 70)
print("🔍 Keyword Search Demo:")
print("=" * 70)

def search_keyword(book, keyword: str, case_sensitive: bool = False):
    """Search for keywords in the book"""
    results = []

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(keyword), flags)

    for chapter in book.spine:
        matches = list(pattern.finditer(chapter.text))

        for i, match in enumerate(matches):
            start = match.start()
            end = match.end()

            # Extract context
            context_start = max(0, start - 50)
            context_end = min(len(chapter.text), end + 50)

            context = chapter.text[context_start:context_end]

            results.append({
                'chapter': chapter.title,
                'chapter_order': chapter.order,
                'occurrence': i,
                'position': start,
                'context': context,
                'match': chapter.text[start:end]
            })

    return results

# Test search
search_term = "network"
print(f"Searching for: '{search_term}'")

results = search_keyword(book, search_term)
print(f"\nFound {len(results)} occurrences\n")

# Show first 5 results
for i, result in enumerate(results[:5], 1):
    print(f"[{i}] Chapter {result['chapter_order']}: {result['chapter']}")
    print(f"    Context: ...{result['context']}...")
    print()

# 6. Word frequency analysis
print("=" * 70)
print("📊 Word Frequency Analysis:")
print("=" * 70)

def get_word_frequency(book, top_n: int = 20):
    """Get most common words in the book"""
    all_text = " ".join([chapter.text for chapter in book.spine])

    # Extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', all_text.lower())

    # Filter stop words
    stop_words = {'the', 'and', 'for', 'that', 'this', 'with', 'was', 'are',
                  'have', 'from', 'not', 'but', 'they', 'you', 'can', 'will',
                  'their', 'has', 'had', 'been', 'than', 'more', 'when', 'which'}

    words = [w for w in words if w not in stop_words]

    return Counter(words).most_common(top_n)

print("\nTop 20 Most Frequent Words:")
print("-" * 70)

word_freq = get_word_frequency(book, top_n=20)

for word, count in word_freq:
    bar = '█' * (count // 100)
    print(f"{word:15s} {count:5d} {bar}")

print("\n" + "=" * 70)
print("✅ Basic exploration complete!")
print("\nFor RAG semantic search, run the Jupyter notebook:")
print("  jupyter notebook explore_book.ipynb")
print("\nRAG requires ChromaDB and sentence-transformers (~420MB model download)")
print("Install with: uv add chromadb sentence-transformers")
print("=" * 70)
