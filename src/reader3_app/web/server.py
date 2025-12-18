import os
import pickle
import logging
import time
from pathlib import Path
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..ai.books import BookUuidResolver
from ..ai.config import get_provider_api_key, get_provider_settings, load_ai_settings
from ..ai.config import get_provider_base_url
from ..ai.providers.anthropic import anthropic_messages
from ..ai.providers.gemini import gemini_generate_content
from ..ai.providers.ollama import ollama_chat_completions
from ..ai.queue import AIRequestQueueManager
from ..ai.rag import retrieve_passages
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

app = FastAPI()

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("reader3.search")

# Where are the book folders located?
BOOKS_DIR = os.environ.get("READER3_BOOKS_DIR", "books")
os.makedirs(BOOKS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

book_uuid_resolver = BookUuidResolver(BOOKS_DIR)
ai_queue = AIRequestQueueManager(max_pending=10)

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

    book_uuid = book_uuid_resolver.book_uuid_for_folder(book_id)
    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "book_uuid": book_uuid,
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


SUPPORTED_AI_PROVIDERS = {"anthropic", "gemini", "ollama"}


def _provider_requires_api_key(provider_name: str) -> bool:
    return provider_name in {"anthropic", "gemini"}


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
    for candidate in ("ollama", "anthropic", "gemini"):
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
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


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
        context = "\n\n".join(
            [
                f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}"
                for p in passages
            ]
        )
        system = (
            "你是 Reader3 的 AI 阅读助手。默认用中文回答（如果用户明确用英文提问，则用英文）。"
            "请基于提供的书籍片段生成总结。"
            "严格输出 JSON，且仅输出 JSON。"
            "JSON 格式：{"
            '"overview": string, '
            '"highlights": string[], '
            '"background": string'
            "}。"
            + _summary_prompt(summary_type)
        )
        user = f"书籍片段（用于总结）：\n{context}\n"
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
async def api_ai_question(request: Request, book_uuid: str, body: AIQuestionRequest):
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

    async def _do() -> dict:
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
        context = "\n\n".join(
            [
                f"[{p['chapter_order'] + 1}] {p['chapter_title']}\n{p['text']}"
                for p in passages
            ]
        )

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
            "只基于提供的书籍片段回答与书相关的问题；如果片段不足以回答，请明确说明需要更多上下文。"
            "回答要清晰、简洁。"
        )
        user = f"书籍片段（用于回答）：\n{context}\n\n问题：{question}\n"

        started = time.perf_counter()
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
        generation_time_ms = int((time.perf_counter() - started) * 1000)

        msg_id = str(__import__("uuid").uuid4())
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
