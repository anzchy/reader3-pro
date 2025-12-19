import os
import pickle
import logging
import time
import json
import asyncio
import threading
import urllib.request
import urllib.error
import html
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..ai.books import BookUuidResolver
from ..ai.conversations import (
    ConversationMessage as DiskConversationMessage,
    ConversationThread as DiskConversationThread,
    delete_conversation_multi as delete_disk_conversation_multi,
    list_conversations_combined as list_disk_conversations_combined,
    load_conversation_combined as load_disk_conversation_combined,
    save_conversation_multi as save_disk_conversation_multi,
)
from ..ai.config import (
    default_settings_dict,
    get_provider_api_key,
    get_provider_settings,
    load_ai_settings,
    save_ai_settings,
)
from ..ai.config import get_provider_base_url
from ..ai.providers.anthropic import anthropic_messages
from ..ai.providers.gemini import gemini_generate_content
from ..ai.providers.ollama import ollama_chat_completions
from ..ai.providers.openai import openai_chat_completions
from ..ai.providers.openrouter import openrouter_chat_completions
from ..ai.queue import AIRequestQueueManager
from ..ai.rag import retrieve_passages
from ..ai.routing import (
    book_token_stats,
    build_full_book_context,
    build_multi_chapter_context,
    choose_routing,
    provider_context_window,
    unique_chapter_orders_from_passages,
)
from ..reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from ..search_service import (
    SearchQuery,
    SearchScope,
    SearchMode,
    list_book_ids,
    search_book,
    search_library,
    highlight_ranges_for_chapter,
)
from ..vector_search import BookVectorIndex
from ..models.annotations import Annotation
from ..notes_service import (
    NOTES_SCHEMA_VERSION,
    add_annotation as add_note_annotation,
    delete_annotation as delete_note_annotation,
    load_annotations as load_note_annotations,
    save_annotations as save_note_annotations,
)

app = FastAPI()

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("reader3.search")
ai_logger = logging.getLogger("reader3.ai")

# Where are the book folders located?
BOOKS_DIR = os.environ.get("READER3_BOOKS_DIR", "books")
os.makedirs(BOOKS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

book_uuid_resolver = BookUuidResolver(BOOKS_DIR)
ai_queue = AIRequestQueueManager(max_pending=10)


def _project_root_dir_from_books_dir() -> str:
    return os.path.dirname(os.path.abspath(BOOKS_DIR))

def _library_ui_mode() -> str:
    mode = (os.environ.get("READER3_LIBRARY_UI") or "modern").strip().lower()
    return mode if mode in {"modern", "classic"} else "modern"

def _library_template_name() -> str:
    if _library_ui_mode() == "classic":
        classic = TEMPLATES_DIR / "library_classic.html"
        if classic.exists():
            return "library_classic.html"
    return "library.html"

@app.on_event("startup")
async def _startup_scan_books() -> None:
    # Ensure stable UUID mapping exists for all processed books.
    book_uuid_resolver.scan()

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
            module = "reader3_app.reader3"
        if module == "reader3" and name in self._REMAP:
            module = "reader3_app.reader3"
        return super().find_class(module, name)

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(os.path.join(BOOKS_DIR, item)):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine)
                    })

    return templates.TemplateResponse(
        _library_template_name(),
        {"request": request, "books": books, "library_ui_mode": _library_ui_mode()},
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

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

    book_uuid = book_uuid_resolver.book_uuid_for_folder(book_id)
    cover_image = None
    try:
        images_dir = os.path.join(BOOKS_DIR, book_id, "images")
        if os.path.isdir(images_dir):
            candidates = [f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))]
            preferred = [f for f in candidates if "cover" in f.lower() or "title" in f.lower()]
            pick_from = preferred or candidates
            if pick_from:
                cover_image = sorted(pick_from, key=lambda x: (len(x), x.lower()))[0]
    except Exception:
        cover_image = None
    cover_url = f"/read/{book_id}/images/{cover_image}" if cover_image else None
    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "book_uuid": book_uuid,
        "cover_url": cover_url,
        "ai_default_provider": _ui_default_provider(),
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


def _collapse_ws(text: str) -> str:
    return " ".join(str(text or "").split())


def _annotation_matches_chapter_text(chapter_text: str, ann: Annotation) -> bool:
    hay = _collapse_ws(chapter_text)
    if not hay:
        return False

    quote = _collapse_ws(ann.quote)
    if not quote:
        return False

    combo = _collapse_ws(f"{ann.prefix}{ann.quote}{ann.suffix}")
    if combo and combo in hay:
        return True
    return quote in hay


def _refresh_orphaned_annotations(book_id: str, book: Book, annotations: list[Annotation]) -> list[Annotation]:
    changed = False
    chapter_text_by_index: dict[int, str] = {}

    for ann in annotations:
        if ann.orphaned:
            continue
        if ann.chapter_index < 0 or ann.chapter_index >= len(book.spine):
            ann.orphaned = True
            changed = True
            continue
        if ann.chapter_index not in chapter_text_by_index:
            chapter_text_by_index[ann.chapter_index] = book.spine[ann.chapter_index].text or ""
        if not _annotation_matches_chapter_text(chapter_text_by_index[ann.chapter_index], ann):
            ann.orphaned = True
            changed = True

    if changed:
        save_note_annotations(BOOKS_DIR, book_id, annotations)

    return [a for a in annotations if not a.orphaned]


class CreateAnnotationRequest(BaseModel):
    type: str = Field(..., description="marker|wavy|underline|note")
    color: Optional[str] = Field(default=None, description="yellow|green|pink|blue (marker/note only)")
    quote: str
    prefix: str = ""
    suffix: str = ""
    position: Optional[int] = None
    note_text: Optional[str] = None


@app.get("/api/notes/{book_id}")
async def api_get_book_notes(book_id: str):
    safe_book_id = _validate_book_id(book_id)
    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    annotations = load_note_annotations(BOOKS_DIR, safe_book_id)
    active = _refresh_orphaned_annotations(safe_book_id, book, annotations)

    by_chapter: dict[int, list[Annotation]] = {}
    for ann in active:
        by_chapter.setdefault(ann.chapter_index, []).append(ann)

    def _sort_key(a: Annotation):
        return (a.position is None, a.position or 0, a.created_at, a.id)

    annotations_by_chapter = []
    total_count = 0
    for chapter_index in sorted(by_chapter.keys()):
        items = sorted(by_chapter[chapter_index], key=_sort_key)
        chapter_title = book.spine[chapter_index].title if 0 <= chapter_index < len(book.spine) else ""

        summaries = []
        for a in items:
            quote = a.quote if len(a.quote) <= 200 else a.quote[:197] + "..."
            note_text = html.unescape(a.note_text) if a.note_text is not None else None
            if note_text is not None and len(note_text) > 200:
                note_text = note_text[:197] + "..."
            summaries.append(
                {
                    "id": a.id,
                    "type": a.type,
                    "color": a.color,
                    "quote": quote,
                    "note_text": note_text,
                    "position": a.position,
                    "created_at": a.created_at,
                }
            )

        annotations_by_chapter.append(
            {
                "chapter_index": chapter_index,
                "chapter_title": chapter_title,
                "count": len(items),
                "annotations": summaries,
            }
        )
        total_count += len(items)

    return {
        "schema_version": NOTES_SCHEMA_VERSION,
        "book_id": safe_book_id,
        "total_count": total_count,
        "annotations_by_chapter": annotations_by_chapter,
    }


@app.get("/api/notes/{book_id}/{chapter_index}")
async def api_get_chapter_notes(book_id: str, chapter_index: int):
    safe_book_id = _validate_book_id(book_id)
    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    annotations = load_note_annotations(BOOKS_DIR, safe_book_id)
    active = _refresh_orphaned_annotations(safe_book_id, book, annotations)
    items = [a for a in active if a.chapter_index == chapter_index]
    items.sort(key=lambda a: (a.position is None, a.position or 0, a.created_at, a.id))

    out = []
    for a in items:
        d = a.to_dict()
        if d.get("note_text") is not None:
            d["note_text"] = html.unescape(str(d["note_text"]))
        out.append(d)

    return {
        "book_id": safe_book_id,
        "chapter_index": chapter_index,
        "count": len(items),
        "annotations": out,
    }


@app.post("/api/notes/{book_id}/{chapter_index}", status_code=201)
async def api_create_annotation(book_id: str, chapter_index: int, payload: CreateAnnotationRequest):
    safe_book_id = _validate_book_id(book_id)
    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    ann_type = str(payload.type or "").strip().lower()
    if ann_type not in ("marker", "wavy", "underline", "note"):
        raise HTTPException(status_code=400, detail="Invalid type")

    color = payload.color
    if ann_type in ("wavy", "underline"):
        color = None
    else:
        if not color:
            color = "yellow"
        if color not in ("yellow", "green", "pink", "blue"):
            raise HTTPException(status_code=400, detail="Invalid color")

    note_text = payload.note_text
    if ann_type == "note":
        if note_text is None or not str(note_text).strip():
            raise HTTPException(status_code=400, detail="note_text is required for type=note")
        note_text = html.escape(str(note_text))
    else:
        note_text = None

    quote = str(payload.quote or "")
    if not quote.strip():
        raise HTTPException(status_code=400, detail="quote is required")

    prefix = str(payload.prefix or "")
    suffix = str(payload.suffix or "")
    if len(prefix) > 50:
        prefix = prefix[-50:]
    if len(suffix) > 50:
        suffix = suffix[:50]

    position = payload.position
    if position is not None:
        try:
            position = int(position)
        except Exception:
            position = None
    if position is not None and position < 0:
        position = 0

    annotation = Annotation(
        book_id=safe_book_id,
        chapter_index=chapter_index,
        type=ann_type,  # type: ignore[arg-type]
        color=color,  # type: ignore[arg-type]
        quote=quote,
        prefix=prefix,
        suffix=suffix,
        position=position,
        note_text=note_text,
        orphaned=False,
    )

    saved = add_note_annotation(BOOKS_DIR, annotation)
    return {"id": saved.id, "created_at": saved.created_at, "message": "Annotation created successfully"}


@app.delete("/api/notes/{book_id}/{chapter_index}/{note_id}", status_code=204)
async def api_delete_annotation(book_id: str, chapter_index: int, note_id: str):
    safe_book_id = _validate_book_id(book_id)
    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=400, detail="Invalid chapter_index")

    ok = delete_note_annotation(BOOKS_DIR, safe_book_id, note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return Response(status_code=204)


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

class AIMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    conversation_id: Optional[str] = None
    metadata: Optional[dict] = None


class AISummaryRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    max_tokens: int = 2000


class AIQuestionRequest(BaseModel):
    question: str
    provider: str
    model: Optional[str] = None
    conversation_history: list[AIMessage] = Field(default_factory=list)
    rag_k: int = 5
    max_tokens: int = 1000


class AIRagRequest(BaseModel):
    book_uuid: str
    query: str
    k: int = 5
    min_similarity: float = 0.5


SUPPORTED_AI_PROVIDERS = {"anthropic", "openai", "gemini", "ollama", "openrouter"}


def _provider_requires_api_key(provider_name: str) -> bool:
    return provider_name in {"anthropic", "openai", "gemini", "openrouter"}


def _ui_default_provider() -> str:
    settings = load_ai_settings()
    configured = str(settings.get("default_provider") or "").strip().lower()

    def provider_is_usable(name: str) -> bool:
        if name not in SUPPORTED_AI_PROVIDERS:
            return False
        provider = get_provider_settings(name, settings=settings)
        if not provider.enabled:
            return False
        if _provider_requires_api_key(name) and not get_provider_api_key(name, settings=settings):
            return False
        return True

    if configured and provider_is_usable(configured):
        return configured

    # Prefer a local/offline provider when available so the UI works out-of-the-box.
    for candidate in ("ollama", "anthropic", "openai", "gemini", "openrouter"):
        if provider_is_usable(candidate):
            return candidate

    # Fallback: return a supported provider even if it isn't usable, so the UI can still render.
    return configured if configured in SUPPORTED_AI_PROVIDERS else "anthropic"


def _get_provider_runtime(
    provider_from_request: str,
    model_from_request: Optional[str],
) -> tuple[str, Optional[str], str, str, int]:
    settings = load_ai_settings()
    provider_name = (provider_from_request or settings.get("default_provider") or "anthropic").strip().lower()
    if provider_name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")

    provider = get_provider_settings(provider_name, settings=settings)
    if not provider.enabled:
        raise HTTPException(status_code=503, detail="AI provider is disabled in settings")

    api_key: Optional[str] = None
    if _provider_requires_api_key(provider_name):
        api_key = get_provider_api_key(provider_name, settings=settings)
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=f"{provider_name} API key not configured. Create config/ai_settings.json (see config/ai_settings.example.json).",
            )

    base_url = get_provider_base_url(provider_name, settings=settings) or provider.base_url or ""
    model = (model_from_request or provider.model_name).strip()
    return provider_name, api_key, base_url, model, provider.timeout_s


def _call_provider(
    provider_name: str,
    *,
    api_key: Optional[str],
    base_url: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    timeout_s: int,
):
    if provider_name == "anthropic":
        assert api_key is not None
        return anthropic_messages(
            api_key=api_key,
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "gemini":
        assert api_key is not None
        return gemini_generate_content(
            api_key=api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "ollama":
        return ollama_chat_completions(
            base_url=base_url or "http://localhost:11434",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "openai":
        assert api_key is not None
        return openai_chat_completions(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider_name == "openrouter":
        assert api_key is not None
        return openrouter_chat_completions(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


def _conversation_id_from_history(history: list[AIMessage]) -> Optional[str]:
    for m in history or []:
        cid = str(m.conversation_id or "").strip()
        if cid:
            return cid
    return None


def _save_conversation_snapshot(
    *,
    book_uuid: str,
    book_folder: str,
    conversation_id: str,
    provider: str,
    model: str,
    history: list[AIMessage],
    assistant_message: Optional[DiskConversationMessage] = None,
) -> None:
    messages: list[DiskConversationMessage] = []
    for m in history or []:
        role = str(m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        msg_id = str(m.id or "").strip()
        if not msg_id:
            continue
        messages.append(
            DiskConversationMessage(
                id=msg_id,
                role=role,
                content=str(m.content or ""),
                timestamp=str(m.timestamp or ""),
                metadata=dict(m.metadata or {}),
            )
        )
    if assistant_message is not None:
        messages.append(assistant_message)
    thread = DiskConversationThread(
        schema_version=1,
        book_uuid=str(book_uuid),
        book_folder=book_folder,
        conversation_id=conversation_id,
        provider=provider,
        model=model,
        created_at="",
        last_updated="",
        messages=messages,
    )
    settings = load_ai_settings()
    save_disk_conversation_multi(
        BOOKS_DIR,
        thread=thread,
        project_conversations_root=_project_conversations_root(settings),
        storage_mode=_conversation_disk_storage_mode(settings),
    )


def _provider_default_base_url(provider_name: str) -> str:
    provider_name = (provider_name or "").strip().lower()
    if provider_name == "anthropic":
        return "https://api.anthropic.com"
    if provider_name == "openai":
        return "https://api.openai.com/v1"
    if provider_name == "gemini":
        return "https://generativelanguage.googleapis.com"
    if provider_name == "ollama":
        return "http://localhost:11434"
    if provider_name == "openrouter":
        return "https://openrouter.ai/api/v1"
    return ""


def _public_provider_config(provider_name: str, *, settings: dict) -> dict:
    provider = get_provider_settings(provider_name, settings=settings)
    base_url = get_provider_base_url(provider_name, settings=settings) or provider.base_url or _provider_default_base_url(provider_name)
    api_key_configured = False
    if _provider_requires_api_key(provider_name):
        api_key_configured = bool(get_provider_api_key(provider_name, settings=settings))
    return {
        "name": provider_name,
        "api_key_configured": api_key_configured,
        "base_url": base_url,
        "model_name": provider.model_name,
        "enabled": provider.enabled,
        "timeout": provider.timeout_s,
        "max_retries": provider.max_retries,
    }


def _public_settings_response(settings: dict) -> dict:
    provider_list = []
    for name in ("anthropic", "openai", "gemini", "ollama", "openrouter"):
        if name not in SUPPORTED_AI_PROVIDERS:
            continue
        provider_list.append(_public_provider_config(name, settings=settings))

    prefs_default = (default_settings_dict().get("preferences") or {}).copy()
    prefs = (settings.get("preferences") or {}).copy()
    prefs_default.update(prefs)
    return {
        "default_provider": str(settings.get("default_provider") or "anthropic").strip().lower(),
        "providers": provider_list,
        "preferences": prefs_default,
    }


def _conversation_disk_storage_mode(settings: dict) -> str:
    prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
    mode = str((prefs or {}).get("conversation_disk_storage") or "per_book").strip().lower()
    if mode not in ("per_book", "project_root", "both"):
        return "per_book"
    return mode


def _project_conversations_root(settings: dict) -> Optional[str]:
    prefs = settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {}
    rel = str((prefs or {}).get("conversation_project_root_dir") or "conversations").strip()
    if not rel:
        rel = "conversations"
    if os.path.isabs(rel):
        return None
    rel_norm = os.path.normpath(rel)
    if rel_norm.startswith(".."):
        return None
    return os.path.join(_project_root_dir_from_books_dir(), rel_norm)


def _settings_update_provider(
    provider_name: str,
    *,
    settings: dict,
    patch: dict,
) -> dict:
    provider_name = provider_name.strip().lower()
    if provider_name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    providers = dict(settings.get("providers") or {})
    base = dict(providers.get(provider_name) or {})
    for key in ("enabled", "model_name", "base_url", "timeout", "timeout_s", "max_retries"):
        if key in patch:
            base[key] = patch.get(key)
    if "api_key" in patch:
        base["api_key"] = str(patch.get("api_key") or "").strip()
    providers[provider_name] = base
    settings["providers"] = providers
    return settings


def _http_get_json(url: str, *, timeout_s: int = 3) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(body or "{}")
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


def _ollama_root_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base.rstrip("/")

def _ollama_openai_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        return base
    return base + "/v1"

def _sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@app.get("/api/settings")
async def api_get_settings():
    settings = load_ai_settings()
    return _public_settings_response(settings)


class UpdateSettingsRequest(BaseModel):
    default_provider: Optional[str] = None
    preferences: Optional[dict] = None


@app.put("/api/settings")
async def api_put_settings(body: UpdateSettingsRequest):
    settings = load_ai_settings()
    updated = dict(settings or {})
    if body.default_provider is not None:
        provider = str(body.default_provider or "").strip().lower()
        if provider and provider not in SUPPORTED_AI_PROVIDERS:
            raise HTTPException(status_code=400, detail="Invalid default_provider")
        updated["default_provider"] = provider or updated.get("default_provider") or "anthropic"
    if body.preferences is not None:
        prefs_default = (default_settings_dict().get("preferences") or {}).copy()
        prefs_patch = body.preferences if isinstance(body.preferences, dict) else {}
        merged = dict(prefs_default)
        merged.update({k: v for k, v in prefs_patch.items() if v is not None})
        updated["preferences"] = merged

    save_ai_settings(updated)
    return _public_settings_response(load_ai_settings())


@app.get("/api/settings/providers")
async def api_list_settings_providers():
    providers = []
    defaults = default_settings_dict()
    default_providers = defaults.get("providers") or {}
    for name in ("anthropic", "openai", "gemini", "ollama", "openrouter"):
        if name not in SUPPORTED_AI_PROVIDERS:
            continue
        p = default_providers.get(name) or {}
        providers.append(
            {
                "name": name,
                "display_name": {
                    "anthropic": "Anthropic Claude",
                    "openai": "OpenAI",
                    "gemini": "Google Gemini",
                    "ollama": "Ollama (Local)",
                    "openrouter": "OpenRouter",
                }.get(name, name),
                "description": {
                    "ollama": "Local AI provider via Ollama (offline-capable)",
                    "openrouter": "Unified API for many models/providers",
                }.get(name, ""),
                "default_base_url": str(p.get("base_url") or _provider_default_base_url(name) or "").strip(),
                "default_model": str(p.get("model_name") or "").strip(),
                "supported_features": {
                    "streaming": True,
                    "function_calling": False,
                    "vision": False,
                },
                "documentation_url": {
                    "anthropic": "https://docs.anthropic.com",
                    "openai": "https://platform.openai.com/docs",
                    "gemini": "https://ai.google.dev",
                    "ollama": "https://ollama.com",
                    "openrouter": "https://openrouter.ai/docs",
                }.get(name, ""),
            }
        )
    return {"providers": providers}


@app.get("/api/settings/providers/{provider_name}")
async def api_get_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = load_ai_settings()
    return _public_provider_config(name, settings=settings)


def _settings_export_payload(settings: dict) -> dict:
    exported: dict = {
        "default_provider": str(settings.get("default_provider") or "anthropic").strip().lower(),
        "preferences": settings.get("preferences") if isinstance(settings.get("preferences"), dict) else {},
        "providers": {},
    }
    providers = settings.get("providers") if isinstance(settings.get("providers"), dict) else {}
    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        safe_cfg = dict(cfg)
        safe_cfg.pop("api_key", None)
        exported["providers"][str(name).strip().lower()] = safe_cfg
    return exported


@app.get("/api/settings/export")
async def api_settings_export():
    settings = load_ai_settings()
    return _settings_export_payload(settings)


@app.post("/api/settings/import")
async def api_settings_import(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    existing = load_ai_settings()
    updated = dict(existing or {})

    if "default_provider" in body:
        dp = str(body.get("default_provider") or "").strip().lower()
        if dp and dp in SUPPORTED_AI_PROVIDERS:
            updated["default_provider"] = dp

    if isinstance(body.get("preferences"), dict):
        prefs_default = (default_settings_dict().get("preferences") or {}).copy()
        prefs_default.update(existing.get("preferences") if isinstance(existing.get("preferences"), dict) else {})
        prefs_default.update({k: v for k, v in body.get("preferences").items() if v is not None})
        updated["preferences"] = prefs_default

    existing_providers = existing.get("providers") if isinstance(existing.get("providers"), dict) else {}
    merged_providers = dict(existing_providers)
    incoming_providers = body.get("providers") if isinstance(body.get("providers"), dict) else {}
    for name, patch in incoming_providers.items():
        pname = str(name or "").strip().lower()
        if pname not in SUPPORTED_AI_PROVIDERS:
            continue
        base = dict(merged_providers.get(pname) or {})
        if isinstance(patch, dict):
            for key in ("enabled", "model_name", "base_url", "timeout", "timeout_s", "max_retries"):
                if key in patch:
                    base[key] = patch.get(key)
        # API keys are never imported.
        merged_providers[pname] = base
    updated["providers"] = merged_providers

    save_ai_settings(updated)
    return _public_settings_response(load_ai_settings())


class UpdateProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None


@app.put("/api/settings/providers/{provider_name}")
async def api_put_provider(provider_name: str, body: UpdateProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    patch: dict[str, Any] = {}
    if body.api_key is not None:
        patch["api_key"] = body.api_key
    if body.base_url is not None:
        patch["base_url"] = str(body.base_url or "").strip()
    if body.model_name is not None:
        patch["model_name"] = str(body.model_name or "").strip()
    if body.enabled is not None:
        patch["enabled"] = bool(body.enabled)
    if body.timeout is not None:
        patch["timeout_s"] = int(body.timeout)
        patch["timeout"] = int(body.timeout)
    if body.max_retries is not None:
        patch["max_retries"] = int(body.max_retries)

    settings = load_ai_settings()
    updated = _settings_update_provider(name, settings=settings, patch=patch)
    save_ai_settings(updated)
    return _public_provider_config(name, settings=load_ai_settings())


@app.delete("/api/settings/providers/{provider_name}", status_code=204)
async def api_delete_provider(provider_name: str):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")
    settings = load_ai_settings()
    providers = dict(settings.get("providers") or {})
    providers.pop(name, None)
    settings["providers"] = providers
    save_ai_settings(settings)
    return None


class TestProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


@app.post("/api/settings/providers/{provider_name}/test")
async def api_test_provider(provider_name: str, body: TestProviderRequest):
    name = (provider_name or "").strip().lower()
    if name not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not found")

    settings = load_ai_settings()
    provider_cfg = get_provider_settings(name, settings=settings)
    api_key = body.api_key if body.api_key is not None else get_provider_api_key(name, settings=settings)
    base_url = str(body.base_url or "").strip() if body.base_url is not None else (get_provider_base_url(name, settings=settings) or provider_cfg.base_url or "")
    model = str(body.model_name or "").strip() if body.model_name is not None else provider_cfg.model_name

    if _provider_requires_api_key(name) and not api_key:
        raise HTTPException(status_code=401, detail="API key not configured")

    system = "You are a connectivity test. Reply with a single word: OK."
    messages = [{"role": "user", "content": "OK"}]

    started = time.perf_counter()
    try:
        resp = await run_in_threadpool(
            _call_provider,
            name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            system=system,
            messages=messages,
            max_tokens=16,
            timeout_s=min(10, provider_cfg.timeout_s),
        )
    except Exception as e:
        return {
            "success": False,
            "provider": name,
            "message": str(e),
            "details": {"model": model, "latency_ms": int((time.perf_counter() - started) * 1000)},
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": True,
        "provider": name,
        "message": "OK",
        "details": {"model": resp.model, "latency_ms": latency_ms},
    }


@app.get("/api/ollama/status")
async def api_ollama_status():
    settings = load_ai_settings()
    base_url = get_provider_base_url("ollama", settings=settings) or get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _ollama_root_base_url(base_url)
    try:
        info = _http_get_json(root + "/api/version", timeout_s=2)
        return {"running": True, "base_url": root, "version": info.get("version")}
    except Exception as e:
        return {"running": False, "base_url": root, "error": str(e)}


@app.get("/api/ollama/models")
async def api_ollama_models():
    settings = load_ai_settings()
    base_url = get_provider_base_url("ollama", settings=settings) or get_provider_settings("ollama", settings=settings).base_url or "http://localhost:11434"
    root = _ollama_root_base_url(base_url)
    try:
        tags = _http_get_json(root + "/api/tags", timeout_s=4)
        models = tags.get("models") if isinstance(tags, dict) else None
        if not isinstance(models, list):
            models = []
        out = []
        for m in models:
            if not isinstance(m, dict):
                continue
            out.append(
                {
                    "name": str(m.get("name") or ""),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                    "details": m.get("details") or {},
                }
            )
        return {"models": out, "base_url": root}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/ai/conversations/{book_uuid}")
async def api_ai_list_conversations(book_uuid: str, provider: Optional[str] = None):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    settings = load_ai_settings()
    threads = list_disk_conversations_combined(
        BOOKS_DIR,
        book_folder=book_folder,
        book_uuid=str(book_uuid),
        provider=provider,
        project_conversations_root=_project_conversations_root(settings),
    )
    return {"book_uuid": str(book_uuid), "provider": (provider or "").strip().lower() or None, "conversations": threads}


@app.get("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_get_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        thread = load_disk_conversation_combined(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return thread.to_dict()


class SaveConversationRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    messages: list[AIMessage] = Field(default_factory=list)


@app.put("/api/ai/conversations/{book_uuid}/{conversation_id}")
async def api_ai_put_conversation(book_uuid: str, conversation_id: str, body: SaveConversationRequest):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    provider = (body.provider or "").strip().lower()
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    msgs: list[DiskConversationMessage] = []
    for m in body.messages or []:
        role = (m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        msg_id = str(m.id or "").strip()
        if not msg_id:
            continue
        msgs.append(
            DiskConversationMessage(
                id=msg_id,
                role=role,
                content=str(m.content or ""),
                timestamp=str(m.timestamp or ""),
                metadata=dict(m.metadata or {}),
            )
        )

    thread = DiskConversationThread(
        schema_version=1,
        book_uuid=str(book_uuid),
        book_folder=book_folder,
        conversation_id=str(conversation_id),
        provider=provider,
        model=str(body.model or ""),
        created_at=str(body.created_at or ""),
        last_updated=str(body.last_updated or ""),
        messages=msgs,
    )
    try:
        settings = load_ai_settings()
        save_disk_conversation_multi(
            BOOKS_DIR,
            thread=thread,
            project_conversations_root=_project_conversations_root(settings),
            storage_mode=_conversation_disk_storage_mode(settings),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/api/ai/conversations/{book_uuid}/{conversation_id}", status_code=204)
async def api_ai_delete_conversation(book_uuid: str, conversation_id: str):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        delete_disk_conversation_multi(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None


def _conversation_to_text(thread: dict) -> str:
    lines = []
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        label = "User" if role == "user" else "Assistant"
        content = str(m.get("content") or "").rstrip()
        lines.append(f"{label}: {content}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _conversation_to_markdown(thread: dict) -> str:
    book_uuid = str(thread.get("book_uuid") or "").strip()
    provider = str(thread.get("provider") or "").strip()
    model = str(thread.get("model") or "").strip()
    conv_id = str(thread.get("conversation_id") or "").strip()
    created_at = str(thread.get("created_at") or "").strip()
    last_updated = str(thread.get("last_updated") or "").strip()

    out = [
        "# AI Conversation",
        "",
        f"- book_uuid: `{book_uuid}`",
        f"- conversation_id: `{conv_id}`",
        f"- provider: `{provider}`",
        f"- model: `{model}`",
        f"- created_at: `{created_at}`",
        f"- last_updated: `{last_updated}`",
        "",
        "---",
        "",
    ]
    msgs = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        title = "User" if role == "user" else "Assistant"
        ts = str(m.get("timestamp") or "").strip()
        content = str(m.get("content") or "").rstrip()
        out.append(f"## {title}")
        if ts:
            out.append(f"- time: `{ts}`")
            out.append("")
        out.append(content or "")
        out.append("")
    return "\n".join(out).strip() + "\n"


@app.get("/api/ai/conversations/{book_uuid}/{conversation_id}/export")
async def api_ai_export_conversation(book_uuid: str, conversation_id: str, format: str = "json"):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        settings = load_ai_settings()
        thread = load_disk_conversation_combined(
            BOOKS_DIR,
            book_folder=book_folder,
            book_uuid=str(book_uuid),
            conversation_id=conversation_id,
            project_conversations_root=_project_conversations_root(settings),
        ).to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    fmt = str(format or "json").strip().lower()
    if fmt == "json":
        return thread
    if fmt in ("text", "txt"):
        body = _conversation_to_text(thread)
        return Response(content=body, media_type="text/plain; charset=utf-8")
    if fmt in ("md", "markdown"):
        body = _conversation_to_markdown(thread)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    raise HTTPException(status_code=400, detail="Invalid format (use json|text|md)")


def _summary_prompt(summary_type: str) -> str:
    st = (summary_type or "full").strip().lower()
    if st not in {"overview", "highlights", "background", "full"}:
        st = "full"
    if st == "overview":
        return "只生成 overview（2-3 段），其余字段可以留空。"
    if st == "highlights":
        return "只生成 highlights（5-10 条要点，每条 1-2 句），其余字段可以留空。"
    if st == "background":
        return "只生成 background（2-4 段：作者/时代/意义/背景），其余字段可以留空。"
    return "生成 overview（2-3 段）、highlights（5-10 条）、background（2-4 段）。"


def _parse_summary_payload(text: str, *, summary_type: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"overview": "", "highlights": [], "background": ""}
    try:
        payload = __import__("json").loads(raw)
        if isinstance(payload, dict):
            overview = str(payload.get("overview") or "")
            background = str(payload.get("background") or "")
            highlights_raw = payload.get("highlights") or []
            highlights = [str(x) for x in highlights_raw] if isinstance(highlights_raw, list) else []
            return {"overview": overview, "highlights": highlights, "background": background}
    except Exception:
        pass

    st = (summary_type or "full").strip().lower()
    if st == "highlights":
        lines = [ln.strip(" \t-•*") for ln in raw.splitlines() if ln.strip()]
        highlights = [ln for ln in lines if ln][:10]
        return {"overview": "", "highlights": highlights, "background": ""}
    if st == "background":
        return {"overview": "", "highlights": [], "background": raw}
    return {"overview": raw, "highlights": [], "background": ""}


@app.post("/api/ai/rag/retrieve")
async def api_ai_rag_retrieve(body: AIRagRequest):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(body.book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        passages, retrieval_time_ms = retrieve_passages(
            book_folder,
            books_dir=BOOKS_DIR,
            query=body.query,
            k=body.k,
            min_similarity=body.min_similarity,
        )
        return {"passages": passages, "retrieval_time_ms": retrieval_time_ms}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/summary/{book_uuid}")
async def api_ai_summary(
    request: Request,
    book_uuid: str,
    body: AISummaryRequest,
    summary_type: str = "full",
    force_regenerate: bool = False,  # cache is frontend-side for v1
):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")

    provider_name, api_key, base_url, model, timeout_s = _get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    async def _do() -> dict:
        book = load_book_cached(book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = book_token_stats(book)
        decision = choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        ai_logger.debug(
            "summary routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

        try:
            passages, retrieval_time_ms = retrieve_passages(
                book_folder,
                books_dir=BOOKS_DIR,
                query="Summarize the entire book: main ideas, structure, themes, and key takeaways.",
                k=12,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        routing_meta: dict[str, Any] = {"mode": decision.mode, "provider_context_window": int(ctx_window)}
        if decision.mode == "full_book":
            context = build_full_book_context(book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, used_orders = build_multi_chapter_context(book, chapter_orders=orders, budget_tokens=decision.budget_tokens)
            routing_meta["chapters"] = used_orders
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
        system = (
            "你是 Reader3 的 AI 阅读助手。默认用中文回答（如果用户明确用英文提问，则用英文）。"
            "请基于提供的书籍内容生成总结。"
            "严格输出 JSON，且仅输出 JSON。"
            "JSON 格式：{"
            '"overview": string, '
            '"highlights": string[], '
            '"background": string'
            "}。"
            + _summary_prompt(summary_type)
        )
        user = f"书籍内容（用于总结）：\n{context}\n"
        try:
            resp = await run_in_threadpool(
                _call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                ai_logger.debug(
                    "summary fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于总结）：\n{rag_context}\n"
                resp = await run_in_threadpool(
                    _call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[{"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        payload = _parse_summary_payload(resp.text, summary_type=summary_type)
        return {
            "book_uuid": str(book_uuid),
            "content": payload,
            "provider": provider_name,
            "model": resp.model,
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "token_count": resp.token_count,
            "from_cache": False,
            "metadata": {
                "retrieval_time_ms": retrieval_time_ms,
                "finish_reason": resp.finish_reason,
                "routing": routing_meta,
            },
        }

    return await ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="summary",
        fn=_do,
    )


@app.post("/api/ai/question/{book_uuid}")
async def api_ai_question(request: Request, book_uuid: str, body: AIQuestionRequest, stream: bool = False):
    try:
        book_folder = book_uuid_resolver.folder_for_book_uuid(book_uuid)
    except Exception:
        raise HTTPException(status_code=404, detail="Book not found")

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="question too long (max 1000 chars)")

    provider_name, api_key, base_url, model, timeout_s = _get_provider_runtime(body.provider, body.model)
    queue_key = f"{book_uuid}:{provider_name}"

    if stream:
        lease = await ai_queue.acquire(
            queue_key,
            request=request,
            timeout_s=float(timeout_s),
            request_label="question",
        )

        book = load_book_cached(book_folder)
        if not book:
            await ai_queue.release(lease)
            raise HTTPException(status_code=404, detail="Book not found")

        try:
            passages, retrieval_time_ms = retrieve_passages(
                book_folder,
                books_dir=BOOKS_DIR,
                query=question,
                k=body.rag_k,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            await ai_queue.release(lease)
            raise HTTPException(status_code=400, detail=str(e))

        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = book_token_stats(book)
        decision = choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        ai_logger.debug(
            "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=1",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )
        if decision.mode == "full_book":
            context = build_full_book_context(book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, _used = build_multi_chapter_context(book, chapter_orders=orders, budget_tokens=decision.budget_tokens)
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
        history = (body.conversation_history or [])[-50:]
        chat_history = []
        for m in history:
            role = (m.role or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            chat_history.append({"role": role, "content": content})

        system = (
            "你是 Reader3 的 AI 阅读助手。"
            "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
            "回答要清晰、简洁。"
        )
        user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

        message_id = str(__import__("uuid").uuid4())
        started = time.perf_counter()
        answer_parts: list[str] = []
        conversation_id = _conversation_id_from_history(history)

        async def event_gen():
            q: asyncio.Queue[dict] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def push(evt: dict) -> None:
                try:
                    q.put_nowait(evt)
                except Exception:
                    pass

            def worker_ollama() -> None:
                url = _ollama_root_base_url(base_url or "http://localhost:11434") + "/api/chat"
                chat_messages = []
                if system:
                    chat_messages.append({"role": "system", "content": system})
                chat_messages.extend([*chat_history, {"role": "user", "content": user}])
                payload = {
                    "model": model,
                    "messages": chat_messages,
                    "stream": True,
                    "options": {"num_predict": max(64, min(int(body.max_tokens), 4096))},
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, method="POST")
                req.add_header("Content-Type", "application/json")
                req.add_header("Accept", "application/json")

                model_out = model
                finish_reason = "stop"
                try:
                    with urllib.request.urlopen(req, timeout=int(timeout_s)) as resp:
                        while True:
                            line = resp.readline()
                            if not line:
                                break
                            raw = line.strip()
                            if not raw:
                                continue
                            try:
                                obj = json.loads(raw.decode("utf-8", errors="replace") or "{}")
                            except Exception:
                                continue
                            if not isinstance(obj, dict):
                                continue
                            if obj.get("model"):
                                model_out = str(obj.get("model") or model_out)
                            msg = obj.get("message")
                            if isinstance(msg, dict):
                                delta = msg.get("content")
                                if delta:
                                    loop.call_soon_threadsafe(push, {"type": "chunk", "delta": str(delta)})
                            if obj.get("done") is True:
                                finish_reason = str(obj.get("done_reason") or finish_reason)
                                break
                    loop.call_soon_threadsafe(push, {"type": "done", "model": model_out, "finish_reason": finish_reason})
                except Exception as e:
                    loop.call_soon_threadsafe(push, {"type": "error", "message": str(e)})

            async def worker_non_stream() -> None:
                try:
                    resp = await run_in_threadpool(
                        _call_provider,
                        provider_name,
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                        system=system,
                        messages=[*chat_history, {"role": "user", "content": user}],
                        max_tokens=body.max_tokens,
                        timeout_s=timeout_s,
                    )
                except Exception as e:
                    await q.put({"type": "error", "message": str(e)})
                    return
                await q.put({"type": "chunk", "delta": resp.text})
                await q.put({"type": "done", "model": resp.model, "finish_reason": resp.finish_reason})

            try:
                yield _sse_event(
                    "meta",
                    {
                        "message_id": message_id,
                        "retrieval_sources": passages,
                        "metadata": {"retrieval_time_ms": retrieval_time_ms, "provider": provider_name},
                    },
                )

                if provider_name == "ollama":
                    threading.Thread(target=worker_ollama, daemon=True).start()
                else:
                    asyncio.create_task(worker_non_stream())

                while True:
                    if request is not None and await request.is_disconnected():
                        yield _sse_event("error", {"message": "Client disconnected"})
                        return
                    if time.monotonic() >= lease.deadline:
                        yield _sse_event("error", {"message": "AI request timed out"})
                        return
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                    et = str(evt.get("type") or "")
                    if et == "chunk":
                        delta = str(evt.get("delta") or "")
                        answer_parts.append(delta)
                        yield _sse_event("chunk", {"delta": delta})
                        continue
                    if et == "done":
                        generation_time_ms = int((time.perf_counter() - started) * 1000)
                        if conversation_id:
                            ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
                            answer_text = "".join(answer_parts)
                            await run_in_threadpool(
                                _save_conversation_snapshot,
                                book_uuid=str(book_uuid),
                                book_folder=book_folder,
                                conversation_id=conversation_id,
                                provider=provider_name,
                                model=str(evt.get("model") or model),
                                history=history,
                                assistant_message=DiskConversationMessage(
                                    id=message_id,
                                    role="assistant",
                                    content=answer_text,
                                    timestamp=ts,
                                    metadata={
                                        "retrieval_sources": passages,
                                        "provider": provider_name,
                                    },
                                ),
                            )
                        yield _sse_event(
                            "done",
                            {
                                "model": str(evt.get("model") or model),
                                "finish_reason": str(evt.get("finish_reason") or "stop"),
                                "metadata": {
                                    "retrieval_time_ms": retrieval_time_ms,
                                    "generation_time_ms": generation_time_ms,
                                    "provider": provider_name,
                                },
                            },
                        )
                        return
                    if et == "error":
                        yield _sse_event("error", {"message": str(evt.get("message") or "AI request failed")})
                        return
            finally:
                await ai_queue.release(lease)

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    async def _do() -> dict:
        book = load_book_cached(book_folder)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        try:
            passages, retrieval_time_ms = retrieve_passages(
                book_folder,
                books_dir=BOOKS_DIR,
                query=question,
                k=body.rag_k,
                min_similarity=0.35,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        ctx_window = provider_context_window(provider_name, model)
        book_tokens, max_chapter_tokens = book_token_stats(book)
        decision = choose_routing(
            provider_ctx_window=ctx_window,
            book_tokens=book_tokens,
            max_chapter_tokens=max_chapter_tokens,
        )
        ai_logger.debug(
            "question routing book_uuid=%s provider=%s model=%s mode=%s book_tokens=%s ctx_window=%s stream=0",
            str(book_uuid),
            provider_name,
            model,
            decision.mode,
            int(book_tokens),
            int(ctx_window),
        )

        routing_meta: dict[str, Any] = {"mode": decision.mode, "provider_context_window": int(ctx_window)}
        if decision.mode == "full_book":
            context = build_full_book_context(book, budget_tokens=decision.budget_tokens)
        elif decision.mode == "multi_chapter":
            orders = unique_chapter_orders_from_passages(passages, limit=8)
            context, used_orders = build_multi_chapter_context(book, chapter_orders=orders, budget_tokens=decision.budget_tokens)
            routing_meta["chapters"] = used_orders
        else:
            context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])

        history = (body.conversation_history or [])[-50:]
        anthropic_history = []
        for m in history:
            role = (m.role or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            anthropic_history.append({"role": role, "content": content})

        system = (
            "你是 Reader3 的 AI 阅读助手。"
            "只基于提供的书籍内容回答与书相关的问题；如果内容不足以回答，请明确说明需要更多上下文。"
            "回答要清晰、简洁。"
        )
        user = f"书籍内容（用于回答）：\n{context}\n\n问题：{question}\n"

        started = time.perf_counter()
        try:
            resp = await run_in_threadpool(
                _call_provider,
                provider_name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                system=system,
                messages=[*anthropic_history, {"role": "user", "content": user}],
                max_tokens=body.max_tokens,
                timeout_s=timeout_s,
            )
        except Exception as e:
            if decision.mode in ("full_book", "multi_chapter"):
                ai_logger.debug(
                    "question fallback to rag book_uuid=%s provider=%s error=%s",
                    str(book_uuid),
                    provider_name,
                    str(e),
                )
                rag_context = "\n\n".join([f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}" for p in passages])
                rag_user = f"书籍片段（用于回答）：\n{rag_context}\n\n问题：{question}\n"
                resp = await run_in_threadpool(
                    _call_provider,
                    provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    system=system,
                    messages=[*anthropic_history, {"role": "user", "content": rag_user}],
                    max_tokens=body.max_tokens,
                    timeout_s=timeout_s,
                )
                routing_meta["mode"] = "rag_fallback"
            else:
                raise
        generation_time_ms = int((time.perf_counter() - started) * 1000)

        msg_id = str(__import__("uuid").uuid4())
        conversation_id = _conversation_id_from_history(body.conversation_history or [])
        if conversation_id:
            ts = __import__("datetime").datetime.utcnow().isoformat() + "Z"
            await run_in_threadpool(
                _save_conversation_snapshot,
                book_uuid=str(book_uuid),
                book_folder=book_folder,
                conversation_id=conversation_id,
                provider=provider_name,
                model=resp.model,
                history=(body.conversation_history or [])[-50:],
                assistant_message=DiskConversationMessage(
                    id=msg_id,
                    role="assistant",
                    content=resp.text,
                    timestamp=ts,
                    metadata={
                        "retrieval_sources": passages,
                        "provider": provider_name,
                    },
                ),
            )
        return {
            "answer": resp.text,
            "message_id": msg_id,
            "retrieval_sources": passages,
            "metadata": {
                "token_count": resp.token_count,
                "model": resp.model,
                "finish_reason": resp.finish_reason,
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "provider": provider_name,
                "routing": routing_meta,
            },
        }

    return await ai_queue.run(
        queue_key,
        request=request,
        timeout_s=float(timeout_s),
        request_label="question",
        fn=_do,
    )

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

def main() -> int:
    import uvicorn

    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
