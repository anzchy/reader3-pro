from __future__ import annotations

import os
import re
import time
import unicodedata
import html
import logging
from array import array
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Optional, List, Tuple, Dict, Union

from .book_store import _book_pkl_path, load_book_cached
# 不再 import safe_pickle：反序列化只经 book_store（011 §4）。占位保留行号：本文件多处 docstring 按行号引用。

logger = logging.getLogger("reader3.search")


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SearchScope(str, Enum):
    CURRENT_BOOK = "current_book"
    ALL_BOOKS = "all_books"


@dataclass
class SearchQuery:
    term: str
    mode: SearchMode = SearchMode.KEYWORD
    scope: SearchScope = SearchScope.CURRENT_BOOK
    case_sensitive: bool = False
    max_results: int = 1000
    book_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.max_results < 1:
            self.max_results = 1
        if self.max_results > 1000:
            self.max_results = 1000
        self.term = self.term or ""


@dataclass
class SearchResult:
    book_id: str
    book_title: str
    book_author: str
    chapter_title: str
    chapter_order: int
    occurrence_index: int
    match_text: str
    context_before: str
    context_after: str
    position: int
    relevance_score: float = 0.0
    match_explanation: Optional[str] = None
    mode: Optional[str] = None


@dataclass
class SearchResultSet:
    query: SearchQuery
    results: List[SearchResult] = field(default_factory=list)
    total_matches: int = 0
    searched_books: int = 0
    failed_books: List[str] = field(default_factory=list)
    unindexed_books: List[str] = field(default_factory=list)
    is_truncated: bool = False
    execution_time_ms: float = 0.0
    grouped_by_book: Dict[str, List[SearchResult]] = field(default_factory=dict)
    index_status_by_book: Dict[str, str] = field(default_factory=dict)
    status_override: Optional[str] = None

    def status_message(self) -> str:
        if self.status_override:
            return self.status_override
        if not self.query.term.strip():
            return "Cleared"
        if self.failed_books:
            ok = max(0, self.searched_books - len(self.failed_books))
            return f"Results from {ok} of {self.searched_books} books ({len(self.failed_books)} failed)"
        if self.query.scope == SearchScope.ALL_BOOKS and self.unindexed_books and self.query.mode != SearchMode.KEYWORD:
            indexed = max(0, self.searched_books - len(self.unindexed_books))
            return f"Results from {indexed} indexed books ({len(self.unindexed_books)} not indexed)"
        if self.query.scope == SearchScope.CURRENT_BOOK:
            return f"Found {self.total_matches} results"
        return f"Found {self.total_matches} results across {self.searched_books} books"


def escape_for_highlighting(term: str) -> str:
    return html.escape(term or "", quote=True)


def validate_search_term(term: str) -> str:
    trimmed = (term or "").strip()
    if len(trimmed) > 500:
        raise ValueError("Search term too long (max 500 characters)")
    return trimmed


def truncate_context(text: str, max_len: int = 150) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return f"{text[:half]}…{text[-half:]}"


def _is_latin_base_char(ch: str) -> bool:
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


def _normalize_with_map(text: str, *, case_sensitive: bool) -> Tuple[str, array]:
    """
    Returns (normalized_text, index_map), where index_map[i] is the original index
    for normalized_text[i].

    - Case-insensitive matching uses Unicode casefold (may expand chars), while keeping a map.
    - Diacritic stripping is applied only to Latin runs (FR-009).

    The map is an ``array("I")``, not a ``list[int]`` (011 WI-9). One entry per
    normalised character means a three-million-character book holds three
    million entries, and a list pays for a pointer *and* a boxed int per entry;
    the array stores the raw 32-bit offsets and measured ~9x smaller on the
    140k-character mixed sample in tests/unit/test_normalize_index_map_container.py.
    Consumers only ever call ``len()`` and index forward, which `array` answers
    identically -- and `array[i]` returns a plain `int`, so the spans built from
    it serialise exactly as before.

    Note the container's one sharp edge: C guarantees `unsigned int` is only >=2
    bytes. On a platform where `array("I").itemsize` were 2, an offset above
    65535 would raise OverflowError here rather than wrap silently. That is
    asserted against, not assumed; see the itemsize case in the same test file.
    """
    normalized_chars: List[str] = []
    index_map = array("I")
    in_latin_run = False

    for original_index, ch in enumerate(text):
        if unicodedata.combining(ch):
            if in_latin_run:
                continue
            normalized_chars.append(ch)
            index_map.append(original_index)
            continue

        if _is_latin_base_char(ch):
            in_latin_run = True
            decomposed = unicodedata.normalize("NFD", ch)
            base = "".join(c for c in decomposed if not unicodedata.combining(c))
            to_emit = base if case_sensitive else base.casefold()
            for out_ch in to_emit:
                normalized_chars.append(out_ch)
                index_map.append(original_index)
            continue

        in_latin_run = False
        to_emit = ch if case_sensitive else ch.casefold()
        for out_ch in to_emit:
            normalized_chars.append(out_ch)
            index_map.append(original_index)

    return "".join(normalized_chars), index_map


def _normalize_query(term: str, *, case_sensitive: bool) -> str:
    normalized, _ = _normalize_with_map(term, case_sensitive=case_sensitive)
    return normalized


def _has_whitespace(text: str) -> bool:
    return bool(re.search(r"\s", text))


def extract_context(text: str, start: int, end: int) -> Tuple[str, str]:
    """
    FR-012: 20 words before/after if whitespace exists, else 40 chars before/after.
    """
    if not text:
        return "", ""

    if _has_whitespace(text):
        word_spans = [m.span() for m in re.finditer(r"\S+", text)]
        if not word_spans:
            return "", ""

        word_index = 0
        for i, (ws, we) in enumerate(word_spans):
            if ws <= start < we:
                word_index = i
                break

        start_word = max(0, word_index - 20)
        end_word_excl = min(len(word_spans), word_index + 21)

        ctx_start = word_spans[start_word][0]
        ctx_end = word_spans[end_word_excl - 1][1]
        return truncate_context(text[ctx_start:start].strip()), truncate_context(text[end:ctx_end].strip())

    ctx_start = max(0, start - 40)
    ctx_end = min(len(text), end + 40)
    return truncate_context(text[ctx_start:start].strip()), truncate_context(text[end:ctx_end].strip())


def search_text(
    text: str,
    term: str,
    *,
    case_sensitive: bool,
    max_results: int,
) -> List[Tuple[int, int]]:
    trimmed = validate_search_term(term)
    if not trimmed:
        return []

    normalized_text, index_map = _normalize_with_map(text, case_sensitive=case_sensitive)
    normalized_term = _normalize_query(trimmed, case_sensitive=case_sensitive)
    if not normalized_term:
        return []

    pattern = re.escape(normalized_term)
    matches: List[Tuple[int, int]] = []

    for m in re.finditer(pattern, normalized_text):
        if len(matches) >= max_results:
            break
        start_n, end_n = m.span()
        if start_n >= len(index_map) or end_n - 1 >= len(index_map):
            continue
        start_o = index_map[start_n]
        end_o = index_map[end_n - 1] + 1
        matches.append((start_o, end_o))

    return matches


def list_book_ids(books_dir: str) -> List[str]:
    result: List[str] = []
    if not os.path.exists(books_dir):
        return result
    for item in os.listdir(books_dir):
        if not item.endswith("_data"):
            continue
        if not os.path.isdir(os.path.join(books_dir, item)):
            continue
        if not os.path.exists(_book_pkl_path(item, books_dir)):
            continue
        result.append(item)
    return sorted(result)


def _find_spans_with_map(
    normalized_text: str,
    index_map: array,
    normalized_term: str,
    *,
    max_spans: int,
) -> Tuple[List[Tuple[int, int]], int]:
    pattern = re.escape(normalized_term)
    spans: List[Tuple[int, int]] = []
    total = 0
    for m in re.finditer(pattern, normalized_text):
        total += 1
        if len(spans) >= max_spans:
            continue
        start_n, end_n = m.span()
        if start_n >= len(index_map) or end_n - 1 >= len(index_map):
            continue
        start_o = index_map[start_n]
        end_o = index_map[end_n - 1] + 1
        spans.append((start_o, end_o))
    return spans, total


@lru_cache(maxsize=4)
def load_book_index(book_id: str, books_dir: str, *, case_sensitive: bool) -> "BookIndex":
    book = load_book_cached(book_id, books_dir)
    author = ", ".join(getattr(getattr(book, "metadata", None), "authors", []) or [])
    title = getattr(getattr(book, "metadata", None), "title", book_id)

    chapters: List[ChapterIndex] = []
    for chapter_order, chapter in enumerate(getattr(book, "spine", []) or []):
        original_text = getattr(chapter, "text", "") or ""
        normalized_text, index_map = _normalize_with_map(original_text, case_sensitive=case_sensitive)
        chapters.append(
            ChapterIndex(
                chapter_title=getattr(chapter, "title", f"Section {chapter_order + 1}"),
                chapter_order=chapter_order,
                normalized_text=normalized_text,
                index_map=index_map,
            )
        )
    return BookIndex(book_id=book_id, book_title=title, book_author=author, chapters=chapters)


def _semantic_results_for_book(
    book_id: str,
    *,
    title: str,
    author: str,
    term: str,
    books_dir: str,
    n_results: int,
) -> List[SearchResult]:
    from .vector_search import BookVectorIndex

    idx = BookVectorIndex(book_id, books_dir=books_dir)
    semantic_hits = idx.semantic_search(term, n_results=n_results)

    out: List[SearchResult] = []
    for s in semantic_hits:
        snippet = truncate_context((s.text or "").strip(), max_len=150)
        out.append(
            SearchResult(
                book_id=book_id,
                book_title=title,
                book_author=author,
                chapter_title=s.chapter_title or f"Section {s.chapter_order + 1}",
                chapter_order=s.chapter_order,
                occurrence_index=0,
                match_text=snippet,
                context_before="",
                context_after="",
                position=s.chunk_start,
                relevance_score=s.similarity_score,
                match_explanation=f"Semantic match (similarity {s.similarity_score:.2f})",
                mode=SearchMode.SEMANTIC.value,
            )
        )
    return out


def search_book(book_id: str, query: SearchQuery, *, books_dir: str) -> SearchResultSet:
    start_time = time.perf_counter()
    trimmed = validate_search_term(query.term)
    if not trimmed:
        return SearchResultSet(query=query, searched_books=1, execution_time_ms=0.0)

    book = load_book_cached(book_id, books_dir)
    author = ", ".join(getattr(getattr(book, "metadata", None), "authors", []) or [])
    title = getattr(getattr(book, "metadata", None), "title", book_id)

    spine = getattr(book, "spine", []) or []
    if spine and all(not (getattr(ch, "text", "") or "").strip() for ch in spine):
        elapsed = (time.perf_counter() - start_time) * 1000
        return SearchResultSet(
            query=query,
            results=[],
            total_matches=0,
            searched_books=1,
            failed_books=[],
            unindexed_books=[],
            is_truncated=False,
            execution_time_ms=elapsed,
            grouped_by_book={},
            status_override="No searchable content in this book",
        )

    if query.mode == SearchMode.SEMANTIC:
        results = _semantic_results_for_book(
            book_id,
            title=title,
            author=author,
            term=trimmed,
            books_dir=books_dir,
            n_results=min(50, query.max_results),
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        return SearchResultSet(
            query=query,
            results=results,
            total_matches=len(results),
            searched_books=1,
            failed_books=[],
            unindexed_books=[],
            is_truncated=len(results) >= query.max_results,
            execution_time_ms=elapsed,
            grouped_by_book={},
        )

    index = load_book_index(book_id, books_dir, case_sensitive=query.case_sensitive)
    normalized_term = _normalize_query(trimmed, case_sensitive=query.case_sensitive)

    results: List[SearchResult] = []
    total_matches = 0
    for chapter_info in index.chapters:
        chapter = spine[chapter_info.chapter_order]
        chapter_text = getattr(chapter, "text", "") or ""
        spans, count = _find_spans_with_map(
            chapter_info.normalized_text,
            chapter_info.index_map,
            normalized_term,
            max_spans=max(0, query.max_results - len(results)),
        )
        total_matches += count

        for occurrence_index, (start, end) in enumerate(spans):
            match_text = chapter_text[start:end]
            context_before, context_after = extract_context(chapter_text, start, end)
            results.append(
                SearchResult(
                    book_id=book_id,
                    book_title=title,
                    book_author=author,
                    chapter_title=chapter_info.chapter_title,
                    chapter_order=chapter_info.chapter_order,
                    occurrence_index=occurrence_index,
                    match_text=match_text,
                    context_before=context_before,
                    context_after=context_after,
                    position=start,
                    relevance_score=0.0,
                    mode=SearchMode.KEYWORD.value,
                )
            )
            if len(results) >= query.max_results:
                break

    if query.mode == SearchMode.HYBRID and query.term.strip():
        try:
            semantic = _semantic_results_for_book(
                book_id,
                title=title,
                author=author,
                term=trimmed,
                books_dir=books_dir,
                n_results=10,
            )
            for r in semantic:
                if len(results) >= query.max_results:
                    break
                results.append(r)
            total_matches += len(semantic)
        except Exception as e:  # noqa: BLE001 - 第 2 档：语义检索不可用时仍返回关键词结果，降级已 log 到 info
            logger.info("hybrid semantic unavailable for %s: %s", book_id, e)

    elapsed = (time.perf_counter() - start_time) * 1000
    return SearchResultSet(
        query=query,
        results=results,
        total_matches=total_matches,
        searched_books=1,
        failed_books=[],
        unindexed_books=[],
        is_truncated=(total_matches > len(results)),
        execution_time_ms=elapsed,
        grouped_by_book={},
    )


def _book_sort_key(
    *,
    query_term: str,
    total_hit_count: int,
    earliest_position_key: int,
) -> Tuple[int, int, int]:
    is_phrase = bool(re.search(r"\s", query_term.strip()))
    exact_phrase_hits = total_hit_count if is_phrase else 0
    return (exact_phrase_hits, total_hit_count, -earliest_position_key)


def search_library(
    query: SearchQuery,
    *,
    books_dir: str,
    max_results_per_book: int,
    max_total_results: int,
    sort_by: str,
) -> Tuple[SearchResultSet, List[str]]:
    """
    Returns (result_set, book_order).
    """
    start_time = time.perf_counter()
    trimmed = validate_search_term(query.term)
    if not trimmed:
        return SearchResultSet(query=query, searched_books=0, execution_time_ms=0.0), []

    book_ids = list_book_ids(books_dir)
    searched_books = len(book_ids)

    grouped: Dict[str, List[SearchResult]] = {}
    book_meta: Dict[str, Tuple[str, str]] = {}
    book_stats: Dict[str, Tuple[int, int]] = {}  # book_id -> (total_hits, earliest_key)
    book_semantic_top: Dict[str, float] = {}
    failed: List[str] = []
    unindexed: List[str] = []
    index_status_by_book: Dict[str, str] = {}

    if query.mode != SearchMode.KEYWORD:
        from .vector_search import BookVectorIndex

        for bid in book_ids:
            try:
                status = BookVectorIndex(bid, books_dir=books_dir).status().get("status", "unknown")
            except Exception:  # noqa: BLE001 - 第 3 档：索引状态探测失败只影响 UI 上的一个标签，返回值 'unknown' 本身就是痕迹；搜索不依赖它
                status = "unknown"
            index_status_by_book[bid] = str(status)

    for book_id in book_ids:
        try:
            book = load_book_cached(book_id, books_dir)
            author = ", ".join(getattr(getattr(book, "metadata", None), "authors", []) or [])
            title = getattr(getattr(book, "metadata", None), "title", book_id)
            book_meta[book_id] = (title, author)

            if query.mode == SearchMode.SEMANTIC:
                try:
                    semantic = _semantic_results_for_book(
                        book_id,
                        title=title,
                        author=author,
                        term=trimmed,
                        books_dir=books_dir,
                        n_results=max_results_per_book,
                    )
                except RuntimeError as e:
                    msg = str(e)
                    if "dependencies are not installed" in msg:
                        raise
                    unindexed.append(book_id)
                    continue
                if not semantic:
                    continue
                grouped[book_id] = semantic
                book_semantic_top[book_id] = max((r.relevance_score for r in semantic), default=0.0)
                book_stats[book_id] = (len(semantic), 0)
                continue

            # keyword (and hybrid keyword base)
            index = load_book_index(book_id, books_dir, case_sensitive=query.case_sensitive)
            normalized_term = _normalize_query(trimmed, case_sensitive=query.case_sensitive)
            total_hits = 0
            earliest_key: Optional[int] = None
            results_for_book: List[SearchResult] = []

            for chapter_info in index.chapters:
                chapter = getattr(book, "spine", [])[chapter_info.chapter_order]
                chapter_text = getattr(chapter, "text", "") or ""
                spans, count = _find_spans_with_map(
                    chapter_info.normalized_text,
                    chapter_info.index_map,
                    normalized_term,
                    max_spans=max(0, max_results_per_book - len(results_for_book)),
                )
                if count <= 0:
                    continue
                total_hits += count
                if earliest_key is None and spans:
                    earliest_key = chapter_info.chapter_order * 1_000_000 + spans[0][0]

                for occurrence_index, (start, end) in enumerate(spans):
                    match_text = chapter_text[start:end]
                    context_before, context_after = extract_context(chapter_text, start, end)
                    results_for_book.append(
                        SearchResult(
                            book_id=book_id,
                            book_title=title,
                            book_author=author,
                            chapter_title=chapter_info.chapter_title,
                            chapter_order=chapter_info.chapter_order,
                            occurrence_index=occurrence_index,
                            match_text=match_text,
                            context_before=context_before,
                            context_after=context_after,
                            position=start,
                            relevance_score=0.0,
                            mode=SearchMode.KEYWORD.value,
                        )
                    )
                    if len(results_for_book) >= max_results_per_book:
                        break

            if query.mode == SearchMode.HYBRID:
                try:
                    semantic = _semantic_results_for_book(
                        book_id,
                        title=title,
                        author=author,
                        term=trimmed,
                        books_dir=books_dir,
                        n_results=max(1, max_results_per_book - len(results_for_book)),
                    )
                    for r in semantic:
                        if len(results_for_book) >= max_results_per_book:
                            break
                        results_for_book.append(r)
                    total_hits += len(semantic)
                except RuntimeError as e:
                    msg = str(e)
                    if "dependencies are not installed" in msg:
                        logger.info("hybrid deps missing: %s", msg)
                    else:
                        unindexed.append(book_id)
                except Exception as e:  # noqa: BLE001 - 第 2 档：同 461，单本书的语义检索不可用不该让整次搜索失败，已 log 到 info
                    logger.info("hybrid semantic unavailable for %s: %s", book_id, e)

            if total_hits <= 0:
                continue
            grouped[book_id] = results_for_book
            book_stats[book_id] = (total_hits, earliest_key or 0)
        except Exception:  # noqa: BLE001 - 第 2 档：单本书搜索失败记进 failed 列表，痕迹在响应体里
            failed.append(book_id)

    def sort_key_for_book(book_id: str) -> Tuple:
        title, author = book_meta.get(book_id, (book_id, ""))
        total_hits, earliest_key = book_stats.get(book_id, (0, 0))
        if sort_by == "book_title":
            return (title.lower(),)
        if sort_by == "book_author":
            return (author.lower(), title.lower())
        if query.mode == SearchMode.SEMANTIC:
            return (book_semantic_top.get(book_id, 0.0),)
        return _book_sort_key(query_term=trimmed, total_hit_count=total_hits, earliest_position_key=earliest_key)

    reverse_relevance = sort_by == "relevance"
    book_order = sorted(grouped.keys(), key=sort_key_for_book, reverse=reverse_relevance)

    flat_results: List[SearchResult] = []
    for book_id in book_order:
        for r in grouped.get(book_id, []):
            if len(flat_results) >= max_total_results:
                break
            flat_results.append(r)
        if len(flat_results) >= max_total_results:
            break

    elapsed = (time.perf_counter() - start_time) * 1000
    result_set = SearchResultSet(
        query=query,
        results=flat_results,
        total_matches=sum(book_stats.get(bid, (0, 0))[0] for bid in grouped.keys()),
        searched_books=searched_books,
        failed_books=failed,
        unindexed_books=unindexed,
        is_truncated=(len(flat_results) >= max_total_results),
        execution_time_ms=elapsed,
        grouped_by_book={bid: grouped[bid] for bid in book_order},
        index_status_by_book=index_status_by_book,
    )
    return result_set, book_order


def _utf16_offset(text: str, code_point_index: int) -> int:
    """Translate a Python code-point index into a UTF-16 code-unit index.

    Python string indices count **code points**; the browser's DOM Range API
    counts **UTF-16 code units**. A non-BMP character (emoji, CJK Extension B+
    ideograph, historic script) is one code point but two code units, so any
    such character before a match pushes the two systems apart by one unit
    each. Without this translation a highlight drifts left in exactly the
    books a Chinese-language reader is most likely to open.
    """
    return len(text[:code_point_index].encode("utf-16-le")) // 2


def highlight_ranges_for_chapter(
    book_id: str,
    chapter_order: int,
    *,
    search_term: str,
    occurrence_index: Optional[int],
    case_sensitive: bool,
    books_dir: str,
) -> Tuple[List[Dict[str, Union[int, str]]], int, Optional[int]]:
    """Locate `search_term` in one chapter and return highlight ranges.

    Every range carries the same span twice, in two different units:

    - ``start`` / ``end`` — **code-point** offsets into ``chapter.text``, i.e.
      plain Python string indices. These are the historical fields; the current
      frontend still consumes them, so they are kept byte-for-byte as they were.
    - ``start_utf16`` / ``end_utf16`` — **UTF-16 code-unit** offsets over the
      same text. These are what a browser needs: ``String.prototype.length``,
      ``Range.setStart`` and DOM text-node offsets are all counted in UTF-16
      code units. New frontend code should read these two and ignore the pair
      above.

    The two pairs are equal for text that is entirely inside the BMP and differ
    by one unit per non-BMP character at or before the offset.
    """
    trimmed = validate_search_term(search_term)
    if not trimmed:
        return [], 0, None

    book = load_book_cached(book_id, books_dir)
    spine = getattr(book, "spine", []) or []
    if chapter_order < 0 or chapter_order >= len(spine):
        raise IndexError("chapter out of range")

    chapter = spine[chapter_order]
    index = load_book_index(book_id, books_dir, case_sensitive=case_sensitive)
    normalized_term = _normalize_query(trimmed, case_sensitive=case_sensitive)
    chapter_info = next((c for c in index.chapters if c.chapter_order == chapter_order), None)
    if not chapter_info or not normalized_term:
        matches = []
    else:
        matches, _ = _find_spans_with_map(
            chapter_info.normalized_text,
            chapter_info.index_map,
            normalized_term,
            max_spans=1000,
        )

    chapter_text = getattr(chapter, "text", "") or ""
    # All-BMP text (plain ASCII, ordinary Hanzi) has identical offsets in both
    # systems, so skip the per-offset re-encoding for the common case.
    all_bmp = len(chapter_text.encode("utf-16-le")) // 2 == len(chapter_text)

    ranges: List[Dict[str, Union[int, str]]] = []
    for i, (start, end) in enumerate(matches):
        ranges.append(
            {
                # Code-point offsets: the existing contract, read by today's frontend.
                "start": start,
                "end": end,
                # UTF-16 code-unit offsets: what DOM Range / String.length expect.
                "start_utf16": start if all_bmp else _utf16_offset(chapter_text, start),
                "end_utf16": end if all_bmp else _utf16_offset(chapter_text, end),
                "style": "search-match",
                "occurrence_index": i,
            }
        )

    selected = occurrence_index if occurrence_index is not None else 0
    if not matches:
        selected = None
    elif selected < 0 or selected >= len(matches):
        selected = 0
    return ranges, len(matches), selected


@dataclass
class ChapterIndex:
    chapter_title: str
    chapter_order: int
    normalized_text: str
    #: ``array("I")`` of original-text offsets, one per normalised character
    #: (011 WI-9). Indexed and len()'d only -- never mutated, never sliced.
    index_map: array


@dataclass
class BookIndex:
    book_id: str
    book_title: str
    book_author: str
    chapters: List[ChapterIndex] = field(default_factory=list)
