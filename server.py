import os
import pickle
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from search_service import (
    SearchQuery,
    SearchScope,
    SearchMode,
    list_book_ids,
    search_book,
    search_library,
    highlight_ranges_for_chapter,
)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Where are the book folders located?
BOOKS_DIR = "."

app.mount("/static", StaticFiles(directory="static"), name="static")

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(item):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine)
                    })

    return templates.TemplateResponse("library.html", {"request": request, "books": books})

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx
    })

def _validate_book_id(book_id: str) -> str:
    safe = os.path.basename(book_id)
    if safe != book_id:
        raise HTTPException(status_code=400, detail="Invalid book_id")
    if safe not in set(list_book_ids(BOOKS_DIR)):
        raise HTTPException(status_code=404, detail="Book not found")
    return safe


@app.get("/api/search/{book_id}")
async def api_search_book(
    book_id: str,
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results: int = 1000,
):
    safe_book_id = _validate_book_id(book_id)
    query = SearchQuery(
        term=q,
        mode=SearchMode(mode),
        scope=SearchScope.CURRENT_BOOK,
        case_sensitive=case_sensitive,
        max_results=max_results,
        book_id=safe_book_id,
    )

    if query.mode != SearchMode.KEYWORD:
        raise HTTPException(status_code=400, detail="Only keyword search is implemented in this build")

    try:
        result_set = search_book(safe_book_id, query, books_dir=BOOKS_DIR)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Book not found")

    return {
        "query": {
            "term": query.term,
            "mode": query.mode.value,
            "scope": query.scope.value,
            "case_sensitive": query.case_sensitive,
            "max_results": query.max_results,
            "book_id": query.book_id,
        },
        "results": [r.__dict__ for r in result_set.results],
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms,
        "status_message": result_set.status_message(),
    }


@app.get("/api/search/library")
async def api_search_library(
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results_per_book: int = 3,
    max_total_results: int = 100,
    sort_by: str = "relevance",
):
    query = SearchQuery(
        term=q,
        mode=SearchMode(mode),
        scope=SearchScope.ALL_BOOKS,
        case_sensitive=case_sensitive,
        max_results=1000,
    )

    if query.mode != SearchMode.KEYWORD:
        raise HTTPException(status_code=400, detail="Only keyword search is implemented in this build")

    max_results_per_book = max(1, min(int(max_results_per_book), 10))
    max_total_results = max(1, min(int(max_total_results), 1000))
    if sort_by not in ("relevance", "book_title", "book_author"):
        raise HTTPException(status_code=400, detail="Invalid sort_by")

    result_set, book_order = search_library(
        query,
        books_dir=BOOKS_DIR,
        max_results_per_book=max_results_per_book,
        max_total_results=max_total_results,
        sort_by=sort_by,
    )

    book_metadata = {}
    for book_id in book_order:
        results = result_set.grouped_by_book.get(book_id, [])
        if not results:
            continue
        book_metadata[book_id] = {
            "book_id": book_id,
            "title": results[0].book_title,
            "author": results[0].book_author,
        }

    return {
        "query": {
            "term": query.term,
            "mode": query.mode.value,
            "scope": query.scope.value,
        },
        "results": [r.__dict__ for r in result_set.results],
        "grouped_by_book": {bid: [r.__dict__ for r in result_set.grouped_by_book.get(bid, [])] for bid in book_order},
        "book_order": book_order,
        "book_metadata": book_metadata,
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms,
        "status_message": result_set.status_message(),
    }


class HighlightRequest(BaseModel):
    search_term: str
    occurrence_index: Optional[int] = None
    case_sensitive: bool = False


@app.post("/api/highlight/{book_id}/{chapter_order}")
async def api_highlight(book_id: str, chapter_order: int, body: HighlightRequest):
    safe_book_id = _validate_book_id(book_id)
    try:
        ranges, total_matches, selected = highlight_ranges_for_chapter(
            safe_book_id,
            int(chapter_order),
            search_term=body.search_term,
            occurrence_index=body.occurrence_index,
            case_sensitive=body.case_sensitive,
            books_dir=BOOKS_DIR,
        )
    except IndexError:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return {
        "ranges": ranges,
        "total_matches": total_matches,
        "selected_occurrence_index": selected,
    }

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
