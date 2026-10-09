"""Shared fixture module for 012 WI-4c.3 (matrix: .claude/tdd-guardian/tests-20261009-wi4c3.md r2, "helpers").

Not a test file and not frozen. No behaviour of its own; reviewed with the tests that import it:

- ``fresh()`` -- the cache context every Hypothesis example runs in (both loader caches and the index cache).
- ``book(books, folder, texts, orders)`` -- a flat-pkl book via ``wi2b_world.write_book_pkl`` (``toc=True``):
  chapter titles ``T{i}`` (positional), book title = folder. ``G`` is ``wi4c2_world.order_book`` (texts
  ``text(o)``).
- ``dump`` / ``relabel`` / ``relabel_lib`` -- the L-B metamorphic relation's two sides.
- ``model_hits`` -- the independent keyword oracle: ``search_service.search_text`` per chapter, paired with the
  chapter's order. It shares the normaliser but none of the chapter addressing 4c.3 changes.
- ``VecStubByBook`` / ``VecStub`` -- doubles for ``reader3_app.vector_search.BookVectorIndex`` (ChromaDB plus the
  embedding model): they return *positional* hits, exactly as the real index stores them before WI-7.
- ``SITES`` -- the four semantic call sites (book/library x semantic/hybrid) as callables.
- ``QueryHashEmbedder`` -- ``book_lock_workers.HashEmbedder`` plus ``embed_query`` (copied from
  ``test_vector_read_path.py``; ``tests/conftest.py`` is frozen).
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple

from book_lock_workers import HashEmbedder
from wi2b_world import write_book_pkl
from wi4c2_world import clear_caches, order_book

from reader3_app import search_service
from reader3_app.search_service import SearchMode, SearchQuery, SearchResult, SearchScope
from reader3_app.vector_search import SemanticSearchResult

G = order_book
NOMATCH = "zzz-nomatch"


@contextlib.contextmanager
def fresh() -> Iterator[None]:
    clear_caches()
    search_service.load_book_index.cache_clear()  # type: ignore[attr-defined]
    try:
        yield
    finally:
        clear_caches()
        search_service.load_book_index.cache_clear()  # type: ignore[attr-defined]


def book(books: Any, folder: str, texts: List[str], orders: Optional[List[int]], *, toc: bool = True) -> Path:
    return write_book_pkl(books, folder, texts, None, orders=orders, toc=toc)


def dump(rs: Any) -> Dict[str, Any]:
    d = dataclasses.asdict(rs)
    d.pop("execution_time_ms", None)
    return d


def _relabel_list(items: List[Dict[str, Any]], orders_for: Callable[[Dict[str, Any]], Sequence[int]]) -> None:
    for r in items:
        r["chapter_order"] = orders_for(r)[r["chapter_order"]]


def relabel(d: Dict[str, Any], orders: Sequence[int]) -> Dict[str, Any]:
    out = copy.deepcopy(d)
    _relabel_list(out["results"], lambda r: orders)
    for rs in out["grouped_by_book"].values():
        _relabel_list(rs, lambda r: orders)
    return out


def relabel_lib(d: Dict[str, Any], orders_by_book: Dict[str, Sequence[int]]) -> Dict[str, Any]:
    out = copy.deepcopy(d)
    _relabel_list(out["results"], lambda r: orders_by_book[r["book_id"]])
    for rs in out["grouped_by_book"].values():
        _relabel_list(rs, lambda r: orders_by_book[r["book_id"]])
    return out


def model_hits(orders: Sequence[int], texts: Sequence[str], term: str, cs: bool) -> List[Tuple[int, int, str]]:
    return [
        (o, s, t[s:e])
        for o, t in zip(orders, texts)
        for (s, e) in search_service.search_text(t, term, case_sensitive=cs, max_results=1000)
    ]


def _vec_stub(lookup: Callable[[str], List[Tuple[int, float]]], titles: Optional[Dict[int, str]]) -> type:
    class _VecStub:
        def __init__(self, book_id: str, *, books_dir: str = ".") -> None:
            self.book_id = book_id
            self.books_dir = books_dir

        def status(self) -> Dict[str, Any]:
            return {"status": "indexed"}

        def semantic_search(self, term: str, *, n_results: int = 10) -> List[SemanticSearchResult]:
            return [
                SemanticSearchResult(
                    book_id=self.book_id,
                    chapter_order=p,
                    chapter_title=(titles or {}).get(p, ""),
                    chunk_id=f"c{p}-k0",
                    chunk_index=0,
                    chunk_start=100 + p,
                    chunk_end=110 + p,
                    text=f"sem-pos-{p}",
                    similarity_score=sc,
                )
                for p, sc in lookup(self.book_id)[:n_results]
            ]

    return _VecStub


def VecStubByBook(by_book: Dict[str, List[Tuple[int, float]]], *, titles: Optional[Dict[int, str]] = None) -> type:
    """A ``BookVectorIndex`` double: ``by_book[folder]`` is that book's ``(position, similarity)`` hits."""
    return _vec_stub(lambda book_id: by_book.get(book_id, []), titles)


def VecStub(positions: List[int], *, titles: Optional[Dict[int, str]] = None) -> type:
    """``VecStubByBook`` answering the same positions for every book, similarity ``0.5 - p / 100``."""
    hits = [(p, 0.5 - p / 100) for p in positions]
    return _vec_stub(lambda book_id: hits, titles)


class SiteOut(NamedTuple):
    hits: List[Tuple[int, str, int, Optional[str]]]
    count: int
    semantic: List[SearchResult]
    results: List[SearchResult]
    book_order: Optional[List[str]]
    rs: Any


def _semantic_only(results: List[SearchResult]) -> List[SearchResult]:
    return [r for r in results if r.mode == "semantic"]


def _out(results: List[SearchResult], semantic: List[SearchResult], rs: Any, order: Optional[List[str]]) -> SiteOut:
    hits = [(r.chapter_order, r.match_text, r.position, r.mode) for r in semantic]
    return SiteOut(hits, rs.total_matches, semantic, results, order, rs)


def _book_site(mode: SearchMode) -> Callable[..., SiteOut]:
    def run(books: Any, folder: str, term: str = NOMATCH) -> SiteOut:
        rs = search_service.search_book(folder, SearchQuery(term=term, mode=mode), books_dir=str(books))
        sem = rs.results if mode == SearchMode.SEMANTIC else _semantic_only(rs.results)
        return _out(rs.results, sem, rs, None)

    return run


def _lib_site(mode: SearchMode) -> Callable[..., SiteOut]:
    def run(books: Any, folder: str, term: str = NOMATCH) -> SiteOut:
        rs, order = search_service.search_library(
            SearchQuery(term=term, mode=mode, scope=SearchScope.ALL_BOOKS),
            books_dir=str(books),
            max_results_per_book=10,
            max_total_results=1000,
            sort_by="relevance",
        )
        got = rs.grouped_by_book.get(folder, [])
        sem = got if mode == SearchMode.SEMANTIC else _semantic_only(got)
        return _out(got, sem, rs, order)

    return run


SITES: List[Tuple[str, Callable[..., SiteOut]]] = [
    ("book-semantic", _book_site(SearchMode.SEMANTIC)),
    ("book-hybrid", _book_site(SearchMode.HYBRID)),
    ("lib-semantic", _lib_site(SearchMode.SEMANTIC)),
    ("lib-hybrid", _lib_site(SearchMode.HYBRID)),
]
SITE_IDS = [name for name, _ in SITES]


class QueryHashEmbedder(HashEmbedder):
    """``HashEmbedder`` that can also embed a query (chromadb 1.3.7's ``collection.query`` calls ``embed_query``)."""

    def embed_query(self, input: List[str]) -> List[List[float]]:  # noqa: A002 - chromadb's protocol name
        return self(input)
