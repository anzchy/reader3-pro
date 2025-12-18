import os
import pickle
import logging
import time
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
from vector_search import BookVectorIndex

app = FastAPI()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("reader3.search")

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
            try:
                book = _Reader3Unpickler(f).load()
            except Exception:
                f.seek(0)
                book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None


class _Reader3Unpickler(pickle.Unpickler):
    _REMAP = {"Book", "BookMetadata", "ChapterContent", "TOCEntry"}

    def find_class(self, module: str, name: str):  # type: ignore[override]
        if module == "__main__" and name in self._REMAP:
            module = "reader3"
        return super().find_class(module, name)

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


@app.get("/api/search/library")
async def api_search_library(
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results_per_book: int = 3,
    max_total_results: int = 100,
    sort_by: str = "relevance",
):
    started = time.perf_counter()
    try:
        query_obj = SearchQuery(
            term=q,
            mode=SearchMode(mode),
            scope=SearchScope.ALL_BOOKS,
            case_sensitive=case_sensitive,
            max_results=1000,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    max_results_per_book = max(1, min(int(max_results_per_book), 10))
    max_total_results = max(1, min(int(max_total_results), 1000))
    if sort_by not in ("relevance", "book_title", "book_author"):
        raise HTTPException(status_code=400, detail="Invalid sort_by")

    try:
        result_set, book_order = search_library(
            query_obj,
            books_dir=BOOKS_DIR,
            max_results_per_book=max_results_per_book,
            max_total_results=max_total_results,
            sort_by=sort_by,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result_set.execution_time_ms > 2000:
        logger.warning(
            "slow library search (%.1fms) mode=%s books=%s",
            result_set.execution_time_ms,
            query_obj.mode.value,
            result_set.searched_books,
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
            "term": query_obj.term,
            "mode": query_obj.mode.value,
            "scope": query_obj.scope.value,
        },
        "results": [r.__dict__ for r in result_set.results],
        "grouped_by_book": {bid: [r.__dict__ for r in result_set.grouped_by_book.get(bid, [])] for bid in book_order},
        "book_order": book_order,
        "book_metadata": book_metadata,
        "index_status_by_book": result_set.index_status_by_book,
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "unindexed_books": result_set.unindexed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms or ((time.perf_counter() - started) * 1000),
        "status_message": result_set.status_message(),
    }


@app.get("/api/search/{book_id}")
async def api_search_book(
    book_id: str,
    q: str = "",
    mode: str = "keyword",
    case_sensitive: bool = False,
    max_results: int = 1000,
):
    safe_book_id = _validate_book_id(book_id)
    started = time.perf_counter()
    try:
        query_obj = SearchQuery(
            term=q,
            mode=SearchMode(mode),
            scope=SearchScope.CURRENT_BOOK,
            case_sensitive=case_sensitive,
            max_results=max_results,
            book_id=safe_book_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result_set = search_book(safe_book_id, query_obj, books_dir=BOOKS_DIR)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result_set.execution_time_ms > 500:
        logger.info(
            "slow in-book search (%.1fms) book=%s mode=%s",
            result_set.execution_time_ms,
            safe_book_id,
            query_obj.mode.value,
        )

    return {
        "query": {
            "term": query_obj.term,
            "mode": query_obj.mode.value,
            "scope": query_obj.scope.value,
            "case_sensitive": query_obj.case_sensitive,
            "max_results": query_obj.max_results,
            "book_id": query_obj.book_id,
        },
        "results": [r.__dict__ for r in result_set.results],
        "total_matches": result_set.total_matches,
        "searched_books": result_set.searched_books,
        "failed_books": result_set.failed_books,
        "unindexed_books": result_set.unindexed_books,
        "is_truncated": result_set.is_truncated,
        "execution_time_ms": result_set.execution_time_ms or ((time.perf_counter() - started) * 1000),
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


class IndexRequest(BaseModel):
    force_reindex: bool = False


@app.post("/api/index/{book_id}")
async def api_index_book(book_id: str, body: IndexRequest):
    safe_book_id = _validate_book_id(book_id)
    try:
        idx = BookVectorIndex(safe_book_id, books_dir=BOOKS_DIR)
        status = idx.index_book(force_reindex=body.force_reindex)
        return status
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/index/{book_id}/status")
async def api_index_status(book_id: str):
    safe_book_id = _validate_book_id(book_id)
    try:
        idx = BookVectorIndex(safe_book_id, books_dir=BOOKS_DIR)
        return idx.status()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
