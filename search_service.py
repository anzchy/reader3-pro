from __future__ import annotations

import os
import pickle
import re
import time
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Optional, List, Tuple, Dict


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


@dataclass
class SearchResultSet:
    query: SearchQuery
    results: List[SearchResult] = field(default_factory=list)
    total_matches: int = 0
    searched_books: int = 0
    failed_books: List[str] = field(default_factory=list)
    is_truncated: bool = False
    execution_time_ms: float = 0.0
    grouped_by_book: Dict[str, List[SearchResult]] = field(default_factory=dict)

    def status_message(self) -> str:
        if not self.query.term.strip():
            return "Cleared"
        if self.failed_books:
            ok = max(0, self.searched_books - len(self.failed_books))
            return f"Results from {ok} of {self.searched_books} books ({len(self.failed_books)} failed)"
        if self.query.scope == SearchScope.CURRENT_BOOK:
            return f"Found {self.total_matches} results"
        return f"Found {self.total_matches} results across {self.searched_books} books"


def _is_latin_base_char(ch: str) -> bool:
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


def _normalize_with_map(text: str, *, case_sensitive: bool) -> Tuple[str, List[int]]:
    """
    Returns (normalized_text, index_map), where index_map[i] is the original index
    for normalized_text[i].

    - Case-insensitive matching uses Unicode casefold (may expand chars), while keeping a map.
    - Diacritic stripping is applied only to Latin runs (FR-009).
    """
    normalized_chars: List[str] = []
    index_map: List[int] = []
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
        return text[ctx_start:start].strip(), text[end:ctx_end].strip()

    ctx_start = max(0, start - 40)
    ctx_end = min(len(text), end + 40)
    return text[ctx_start:start].strip(), text[end:ctx_end].strip()


def search_text(
    text: str,
    term: str,
    *,
    case_sensitive: bool,
    max_results: int,
) -> List[Tuple[int, int]]:
    trimmed = (term or "").strip()
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


def _book_pkl_path(book_id: str, books_dir: str) -> str:
    return os.path.join(books_dir, book_id, "book.pkl")


@lru_cache(maxsize=10)
def load_book_cached(book_id: str, books_dir: str) -> object:
    path = _book_pkl_path(book_id, books_dir)
    with open(path, "rb") as f:
        return pickle.load(f)


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


def search_book(book_id: str, query: SearchQuery, *, books_dir: str) -> SearchResultSet:
    start_time = time.time()
    trimmed = query.term.strip()
    if not trimmed:
        return SearchResultSet(query=query, searched_books=1, execution_time_ms=0.0)

    book = load_book_cached(book_id, books_dir)
    author = ", ".join(getattr(getattr(book, "metadata", None), "authors", []) or [])
    title = getattr(getattr(book, "metadata", None), "title", book_id)

    results: List[SearchResult] = []
    total_matches = 0

    for chapter_order, chapter in enumerate(getattr(book, "spine", [])):
        matches = search_text(
            getattr(chapter, "text", "") or "",
            trimmed,
            case_sensitive=query.case_sensitive,
            max_results=query.max_results,
        )
        total_matches += len(matches)

        for occurrence_index, (start, end) in enumerate(matches):
            if len(results) >= query.max_results:
                break
            chapter_text = getattr(chapter, "text", "") or ""
            match_text = chapter_text[start:end]
            context_before, context_after = extract_context(chapter_text, start, end)
            results.append(
                SearchResult(
                    book_id=book_id,
                    book_title=title,
                    book_author=author,
                    chapter_title=getattr(chapter, "title", f"Section {chapter_order + 1}"),
                    chapter_order=chapter_order,
                    occurrence_index=occurrence_index,
                    match_text=match_text,
                    context_before=context_before,
                    context_after=context_after,
                    position=start,
                    relevance_score=0.0,
                )
            )

        if len(results) >= query.max_results:
            break

    elapsed = (time.time() - start_time) * 1000
    return SearchResultSet(
        query=query,
        results=results,
        total_matches=total_matches,
        searched_books=1,
        failed_books=[],
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
    start_time = time.time()
    trimmed = query.term.strip()
    if not trimmed:
        return SearchResultSet(query=query, searched_books=0, execution_time_ms=0.0), []

    book_ids = list_book_ids(books_dir)
    searched_books = len(book_ids)

    grouped: Dict[str, List[SearchResult]] = {}
    book_meta: Dict[str, Tuple[str, str]] = {}
    book_stats: Dict[str, Tuple[int, int]] = {}  # book_id -> (total_hits, earliest_key)
    failed: List[str] = []

    for book_id in book_ids:
        try:
            book = load_book_cached(book_id, books_dir)
            author = ", ".join(getattr(getattr(book, "metadata", None), "authors", []) or [])
            title = getattr(getattr(book, "metadata", None), "title", book_id)
            book_meta[book_id] = (title, author)

            total_hits = 0
            earliest_key: Optional[int] = None
            results_for_book: List[SearchResult] = []

            for chapter_order, chapter in enumerate(getattr(book, "spine", [])):
                chapter_text = getattr(chapter, "text", "") or ""
                matches = search_text(
                    chapter_text,
                    trimmed,
                    case_sensitive=query.case_sensitive,
                    max_results=1000,
                )
                if not matches:
                    continue

                total_hits += len(matches)
                if earliest_key is None:
                    earliest_key = chapter_order * 1_000_000 + matches[0][0]

                for occurrence_index, (start, end) in enumerate(matches):
                    if len(results_for_book) >= max_results_per_book:
                        break
                    match_text = chapter_text[start:end]
                    context_before, context_after = extract_context(chapter_text, start, end)
                    results_for_book.append(
                        SearchResult(
                            book_id=book_id,
                            book_title=title,
                            book_author=author,
                            chapter_title=getattr(chapter, "title", f"Section {chapter_order + 1}"),
                            chapter_order=chapter_order,
                            occurrence_index=occurrence_index,
                            match_text=match_text,
                            context_before=context_before,
                            context_after=context_after,
                            position=start,
                            relevance_score=0.0,
                        )
                    )

            if total_hits <= 0:
                continue

            grouped[book_id] = results_for_book
            book_stats[book_id] = (total_hits, earliest_key or 0)
        except Exception:
            failed.append(book_id)

    def sort_key_for_book(book_id: str) -> Tuple:
        title, author = book_meta.get(book_id, (book_id, ""))
        total_hits, earliest_key = book_stats.get(book_id, (0, 0))
        if sort_by == "book_title":
            return (title.lower(),)
        if sort_by == "book_author":
            return (author.lower(), title.lower())
        return _book_sort_key(query_term=trimmed, total_hit_count=total_hits, earliest_position_key=earliest_key)

    book_order = sorted(grouped.keys(), key=sort_key_for_book, reverse=(sort_by == "relevance"))

    flat_results: List[SearchResult] = []
    for book_id in book_order:
        for r in grouped.get(book_id, []):
            if len(flat_results) >= max_total_results:
                break
            flat_results.append(r)
        if len(flat_results) >= max_total_results:
            break

    elapsed = (time.time() - start_time) * 1000
    result_set = SearchResultSet(
        query=query,
        results=flat_results,
        total_matches=sum(book_stats.get(bid, (0, 0))[0] for bid in grouped.keys()),
        searched_books=searched_books,
        failed_books=failed,
        is_truncated=(len(flat_results) >= max_total_results),
        execution_time_ms=elapsed,
        grouped_by_book={bid: grouped[bid] for bid in book_order},
    )
    return result_set, book_order


def highlight_ranges_for_chapter(
    book_id: str,
    chapter_order: int,
    *,
    search_term: str,
    occurrence_index: Optional[int],
    case_sensitive: bool,
    books_dir: str,
) -> Tuple[List[Dict[str, int | str]], int, Optional[int]]:
    trimmed = (search_term or "").strip()
    if not trimmed:
        return [], 0, None

    book = load_book_cached(book_id, books_dir)
    spine = getattr(book, "spine", []) or []
    if chapter_order < 0 or chapter_order >= len(spine):
        raise IndexError("chapter out of range")

    chapter = spine[chapter_order]
    chapter_text = getattr(chapter, "text", "") or ""
    matches = search_text(
        chapter_text,
        trimmed,
        case_sensitive=case_sensitive,
        max_results=1000,
    )

    ranges: List[Dict[str, int | str]] = []
    for i, (start, end) in enumerate(matches):
        ranges.append(
            {
                "start": start,
                "end": end,
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

