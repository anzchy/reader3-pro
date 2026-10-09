"""012 WI-4c.3a: keyword search and the semantic boundary emit ``chapter_order`` as the ADR-0016 order.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c3.md`` r2, cases SO-01..SO-10, SO-06P, SO-07E/H/P/R/T. Binding:
the plan's "Coordinator rulings 2026-10-09 (WI-4c.3)" -- one position->order helper at all four semantic sites,
out-of-range positions dropped (never clamped, never raw), the cross-book ranking key stays positional (SO-05),
title fallback ``Section {spine_position + 1}``. Pre-red adjustment (coordinator side): SO-07R puts book B on
orders ``[1, 3]`` so its position-0 hit must come out as order 1.

Books are real flat pickles in a tmp ``books/`` (``wi4c3_world.book`` / ``G``). The only double is
``reader3_app.vector_search.BookVectorIndex`` (ChromaDB plus the embedding model), paired with SO-10, which runs
real ChromaDB on a real gap EPUB with only the embedding function replaced.

Green-first by design (characterization at ``b0583da``): SO-04, SO-08, SO-09. Every other case here is red there.
"""

from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
from unittest import mock

import pytest
from gap_epub import SVG, XHTML, GapItem, build_gap_epub
from hypothesis import example, given, settings
from hypothesis import strategies as st
from wi4c2_world import text
from wi4c3_world import (
    NOMATCH,
    SITE_IDS,
    SITES,
    G,
    QueryHashEmbedder,
    VecStub,
    VecStubByBook,
    book,
    dump,
    fresh,
    model_hits,
    relabel,
    relabel_lib,
)
from wi4c3_so04_expected import EXPECTED

from reader3_app import book_store, reader3, search_service, vector_search
from reader3_app.search_service import SearchMode, SearchQuery, SearchScope

KEYWORD, SEMANTIC, HYBRID = SearchMode.KEYWORD, SearchMode.SEMANTIC, SearchMode.HYBRID
TOKENS = ["foo", "bar", "café", "日本", "\U00020000x", "FOO"]
VEC = "reader3_app.vector_search.BookVectorIndex"


@pytest.fixture
def books(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    b = tmp_path / "books"
    b.mkdir()
    monkeypatch.chdir(tmp_path)
    with fresh():
        yield b


def _search(folder: str, books: Path, term: str, **kw: Any) -> Any:
    return search_service.search_book(folder, SearchQuery(term=term, **kw), books_dir=str(books))


def _library(books: Path, term: str, *, mode: SearchMode = KEYWORD, mpb: int = 10, mtr: int = 1000,
             sort_by: str = "relevance", cs: bool = False) -> Tuple[Any, List[str]]:
    return search_service.search_library(
        SearchQuery(term=term, mode=mode, scope=SearchScope.ALL_BOOKS, case_sensitive=cs),
        books_dir=str(books),
        max_results_per_book=mpb,
        max_total_results=mtr,
        sort_by=sort_by,
    )


# --------------------------------------------------------------------------- strategies


@st.composite
def books_st(draw: Any, max_n: int = 8) -> Tuple[List[int], List[str]]:
    n = draw(st.integers(1, max_n))
    orders = sorted(draw(st.lists(st.integers(0, 40), min_size=n, max_size=n, unique=True)))
    texts = [f"chap-{i}-end " + " ".join(draw(st.lists(st.sampled_from(TOKENS), max_size=6))) for i in range(n)]
    return orders, texts


def _term_pool(n: int) -> List[str]:
    return [f"chap-{i}-end" for i in range(n)] + ["foo", "cafe", "日本", "\U00020000", NOMATCH]


@st.composite
def keyword_case(draw: Any) -> Tuple[List[int], List[str], str, bool]:
    orders, texts = draw(books_st())
    return orders, texts, draw(st.sampled_from(_term_pool(len(orders)))), draw(st.booleans())


@st.composite
def relabel_book_case(draw: Any) -> Tuple[Any, ...]:
    orders, texts = draw(books_st())
    n = len(orders)
    term = draw(st.sampled_from(_term_pool(n)))
    positions = draw(st.lists(st.integers(0, n - 1), max_size=5))
    return (
        orders, texts, term, draw(st.booleans()), draw(st.integers(1, 6)),
        draw(st.sampled_from([KEYWORD, HYBRID])), positions,
    )


@st.composite
def relabel_lib_case(draw: Any) -> Tuple[Any, ...]:
    shelf = draw(st.lists(books_st(max_n=5), min_size=2, max_size=3))
    by_book: Dict[str, List[Tuple[int, float]]] = {}
    for k, (orders, _) in enumerate(shelf):
        pairs = st.tuples(st.integers(0, len(orders) - 1), st.floats(0, 1))
        by_book[f"b{k}_data"] = draw(st.lists(pairs, max_size=4))
    term = draw(st.sampled_from(["foo", "bar", "chap-0-end", "chap-1-end"]))
    mode = draw(st.sampled_from([KEYWORD, HYBRID]))
    return shelf, term, draw(st.booleans()), draw(st.integers(1, 4)), draw(st.integers(1, 10)), mode, by_book


@st.composite
def filter_map_case(draw: Any) -> Tuple[List[int], List[int], int]:
    orders, _ = draw(books_st(max_n=6))
    positions = draw(st.lists(st.integers(-3, max(orders) + 3), max_size=10))
    return orders, positions, draw(st.integers(0, len(SITES) - 1))


# --------------------------------------------------------------------------- index build (SO-06, SO-06P, SO-09)


def test_so_06_index_pairs_each_order_with_its_spine_position(books: Path) -> None:
    book(books, "i134_data", ["a-one", "b-two", "c-three"], [1, 3, 4])
    idx = search_service.load_book_index("i134_data", str(books), case_sensitive=False)
    got = [(c.chapter_order, getattr(c, "spine_position", None), c.chapter_title, c.normalized_text)
           for c in idx.chapters]
    assert got == [(1, 0, "T0", "a-one"), (3, 1, "T1", "b-two"), (4, 2, "T2", "c-three")]


@settings(max_examples=40, deadline=None)
@example(case=([0, 2], ["chap-0-end foo", "chap-1-end café FOO"], False))
@given(case=st.tuples(books_st(), st.booleans()).map(lambda t: (t[0][0], t[0][1], t[1])))
def test_so_06p_index_alignment_over_generated_order_sets(case: Tuple[List[int], List[str], bool]) -> None:
    orders, texts, cs = case
    with tempfile.TemporaryDirectory() as d, fresh():
        b = Path(d) / "books"
        book(b, "a_data", texts, orders)
        idx = search_service.load_book_index("a_data", str(b), case_sensitive=cs)
        assert [(c.chapter_order, getattr(c, "spine_position", None)) for c in idx.chapters] == list(
            zip(orders, range(len(orders)))
        )
        assert [c.normalized_text for c in idx.chapters] == [
            search_service._normalize_with_map(t, case_sensitive=cs)[0] for t in texts
        ]


def test_so_09_title_fallback_is_the_spine_position_not_the_order(books: Path) -> None:
    pkl = book(books, "nt13_data", ["x", "y"], [1, 3])
    loaded = pickle.loads(pkl.read_bytes())
    for ch in loaded.spine:
        delattr(ch, "title")
    pkl.write_bytes(pickle.dumps(loaded))
    idx = search_service.load_book_index("nt13_data", str(books), case_sensitive=False)
    assert [c.chapter_title for c in idx.chapters] == ["Section 1", "Section 2"]


# --------------------------------------------------------------------------- search_book keyword (SO-01..SO-04)


@pytest.mark.parametrize(
    "folder, orders, term, expected",
    [
        ("g02_data", [0, 2], "uniq-2-end", [(2, "T1", "uniq-2-end", 16, 0)]),
        ("g02_data", [0, 2], "text-of-order", [(0, "T0", "text-of-order", 0, 0), (2, "T1", "text-of-order", 0, 0)]),
        ("g13_data", [1, 3], "text-of-order", [(1, "T0", "text-of-order", 0, 0), (3, "T1", "text-of-order", 0, 0)]),
        ("g13_data", [1, 3], "uniq-3-end", [(3, "T1", "uniq-3-end", 16, 0)]),
    ],
    ids=["g02-uniq2", "g02-all", "g13-all", "g13-uniq3"],
)
def test_so_01_keyword_hits_carry_the_order(
    books: Path, folder: str, orders: List[int], term: str, expected: List[Tuple[Any, ...]]
) -> None:
    G(books, folder, orders)
    rs = _search(folder, books, term)
    got = [(r.chapter_order, r.chapter_title, r.match_text, r.position, r.occurrence_index) for r in rs.results]
    assert (got, rs.total_matches) == (expected, len(expected))


@settings(max_examples=50, deadline=None)
@example(case=([0, 2], ["chap-0-end foo", "chap-1-end foo bar"], "foo", False))
@example(case=([1, 3], ["chap-0-end foo", "chap-1-end FOO foo"], "foo", False))
@given(case=keyword_case())
def test_so_02_keyword_hits_match_the_order_model(case: Tuple[List[int], List[str], str, bool]) -> None:
    orders, texts, term, cs = case
    with tempfile.TemporaryDirectory() as d, fresh():
        b = Path(d) / "books"
        book(b, "p_data", texts, orders)
        rs = _search("p_data", b, term, case_sensitive=cs, max_results=1000)
        expected = model_hits(orders, texts, term, cs)
        assert [(h.chapter_order, h.position, h.match_text) for h in rs.results] == expected
        assert rs.total_matches == len(expected)
        loaded = book_store.load_book_cached("p_data", str(b))
        for h in rs.results:
            ch = book_store.find_chapter(loaded, h.chapter_order, book_id="p_data")
            assert ch is not None, h.chapter_order
            assert ch.text[h.position : h.position + len(h.match_text)] == h.match_text


@settings(max_examples=40, deadline=None)
@example(case=([0, 2], ["chap-0-end foo", "chap-1-end bar"], "chap-1-end", False, 6, HYBRID, [1]))
@given(case=relabel_book_case())
def test_so_03a_search_book_is_the_flat_twin_relabelled(case: Tuple[Any, ...]) -> None:
    orders, texts, term, cs, max_results, mode, positions = case
    with tempfile.TemporaryDirectory() as d, fresh(), mock.patch(VEC, VecStub(positions)):
        gap, flat = Path(d) / "gap" / "books", Path(d) / "flat" / "books"
        book(gap, "m_data", texts, orders)
        book(flat, "m_data", texts, list(range(len(orders))))
        q = dict(case_sensitive=cs, max_results=max_results, mode=mode)
        got = dump(_search("m_data", gap, term, **q))
        twin = dump(_search("m_data", flat, term, **q))
        assert got == relabel(twin, orders)


def test_so_04_gapless_responses_are_byte_identical_to_b0583da(books: Path) -> None:
    book(books, "c1_data", ["Le café est fermé. café CAFÉ"], None)
    book(books, "c3_data", ["alpha café beta", "gamma foo foo", "delta cafe"], None)
    book(books, "c5_data", ["日本語の本 foo", "\U00020000foo\U00020000 foo", "foo", "none here", "末尾 foo"], None)
    calls = {"c1_cafe": ("c1_data", "cafe", 1000), "c3_cafe": ("c3_data", "cafe", 1000),
             "c5_foo_3": ("c5_data", "foo", 3), "c5_foo_all": ("c5_data", "foo", 1000)}
    for key, (bid, term, m) in calls.items():
        assert dump(_search(bid, books, term, max_results=m)) == EXPECTED[key], key
    for s in ("relevance", "book_title", "book_author"):
        rs, order = _library(books, "foo", mpb=2, mtr=3, sort_by=s)
        assert (dump(rs), order) == EXPECTED[f"lib_{s}"], s
    # Semantic leg (OQ-1 iii): every stubbed position is in range for its book.
    by_book = {"c1_data": [(0, 0.5)], "c3_data": [(0, 0.5), (1, 0.49), (2, 0.48)],
               "c5_data": [(0, 0.5), (1, 0.49), (2, 0.48)]}
    with mock.patch(VEC, VecStubByBook(by_book)):
        assert dump(_search("c3_data", books, "foo", mode=SEMANTIC)) == EXPECTED["c3_sem"]
        assert dump(_search("c3_data", books, "foo", mode=HYBRID)) == EXPECTED["c3_hyb"]
        rs, order = _library(books, "foo", mode=SEMANTIC, mpb=2, mtr=3)
        assert (dump(rs), order) == EXPECTED["lib_sem"]


# --------------------------------------------------------------------------- search_library (SO-03b, SO-05)


@settings(max_examples=40, deadline=None)
@example(case=(
    [([0, 2], ["chap-0-end foo", "chap-1-end bar"]), ([0, 1], ["chap-0-end", "chap-1-end foo"])],
    "chap-1-end", False, 4, 10, HYBRID, {"b0_data": [(1, 0.5)], "b1_data": []},
))
@given(case=relabel_lib_case())
def test_so_03b_search_library_is_the_flat_twin_relabelled(case: Tuple[Any, ...]) -> None:
    shelf, term, cs, mpb, mtr, mode, by_book = case
    with tempfile.TemporaryDirectory() as d, fresh(), mock.patch(VEC, VecStubByBook(by_book)):
        gap, flat = Path(d) / "gap" / "books", Path(d) / "flat" / "books"
        orders_by_book = {}
        for k, (orders, texts) in enumerate(shelf):
            orders_by_book[f"b{k}_data"] = orders
            book(gap, f"b{k}_data", texts, orders)
            book(flat, f"b{k}_data", texts, list(range(len(orders))))
        rs_gap, order_gap = _library(gap, term, mode=mode, mpb=mpb, mtr=mtr, cs=cs)
        rs_flat, order_flat = _library(flat, term, mode=mode, mpb=mpb, mtr=mtr, cs=cs)
        assert order_gap == order_flat
        assert dump(rs_gap) == relabel_lib(dump(rs_flat), orders_by_book)


def test_so_05_ranking_key_stays_positional_while_the_emitted_order_moves(books: Path) -> None:
    book(books, "rank_z_data", ["alpha", "RANKTERM rest"], [0, 5])
    book(books, "rank_b_data", ["alpha", "beta", "RANKTERM rest"], [0, 1, 2])
    rs, order = _library(books, "RANKTERM", mpb=3, mtr=100)
    assert order == ["rank_z_data", "rank_b_data"]
    assert rs.grouped_by_book["rank_z_data"][0].chapter_order == 5
    assert rs.grouped_by_book["rank_b_data"][0].chapter_order == 2


# --------------------------------------------------------------------------- semantic boundary (SO-07*)


@pytest.mark.parametrize("site", [s for _, s in SITES], ids=SITE_IDS)
def test_so_07_every_site_translates_and_drops_out_of_range_positions(
    books: Path, monkeypatch: pytest.MonkeyPatch, site: Any
) -> None:
    G(books, "g02_data", [0, 2])
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([0, 1, 2, -1, 7]))
    out = site(books, "g02_data")
    assert out.hits == [(0, "sem-pos-0", 100, "semantic"), (2, "sem-pos-1", 101, "semantic")]
    assert out.count == 2
    assert [r.chapter_title for r in out.semantic] == ["Section 1", "Section 2"]
    if out.book_order is None and out.rs.query.mode == SEMANTIC:
        assert out.rs.is_truncated is False


@pytest.mark.parametrize("site", [SITES[1][1], SITES[3][1]], ids=[SITES[1][0], SITES[3][0]])
def test_so_07h_hybrid_keyword_hit_is_not_translated_twice(
    books: Path, monkeypatch: pytest.MonkeyPatch, site: Any
) -> None:
    G(books, "g02_data", [0, 2])
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([1]))
    out = site(books, "g02_data", "uniq-2-end")
    got = [(r.chapter_order, r.match_text, r.mode) for r in out.results]
    assert got == [(2, "uniq-2-end", "keyword"), (2, "sem-pos-1", "semantic")]
    assert out.count == 2


@pytest.mark.parametrize("site", [s for _, s in SITES], ids=SITE_IDS)
def test_so_07e_all_positions_out_of_range_leave_nothing(
    books: Path, monkeypatch: pytest.MonkeyPatch, site: Any
) -> None:
    G(books, "g02_data", [0, 2])
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([2, -1, 9]))
    out = site(books, "g02_data")
    assert (out.hits, out.count) == ([], 0)
    if out.book_order is not None:
        assert "g02_data" not in out.rs.grouped_by_book
        assert "g02_data" not in out.book_order


def test_so_07r_library_semantic_ranking_and_count_use_the_translated_list(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    G(books, "sa_data", [0, 2])
    G(books, "sb_data", [1, 3])  # pre-red adjustment: B's position-0 hit must come out as order 1
    stub = VecStubByBook({"sa_data": [(7, 0.9), (0, 0.1)], "sb_data": [(0, 0.5)]})
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", stub)
    rs, order = _library(books, NOMATCH, mode=SEMANTIC)
    assert order == ["sb_data", "sa_data"]
    assert rs.total_matches == 2
    assert [(r.chapter_order, r.relevance_score) for r in rs.grouped_by_book["sa_data"]] == [(0, 0.1)]
    assert [(r.chapter_order, r.relevance_score) for r in rs.grouped_by_book["sb_data"]] == [(1, 0.5)]


def test_so_07t_book_semantic_count_and_truncation_use_the_translated_list(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    G(books, "g02_data", [0, 2])
    monkeypatch.setattr("reader3_app.vector_search.BookVectorIndex", VecStub([0, 7]))
    rs = _search("g02_data", books, NOMATCH, mode=SEMANTIC, max_results=2)
    assert ([r.chapter_order for r in rs.results], rs.total_matches, rs.is_truncated) == ([0], 1, False)


@settings(max_examples=50, deadline=None)
@example(case=([0, 2], [0, 1, 2, -1], 0))
@example(case=([0, 2], [0, 1, 2, -1], 3))
@example(case=([1, 3], [1, 0, 2], 1))
@example(case=([1, 3], [1, 0, 2], 2))
@given(case=filter_map_case())
def test_so_07p_filter_map_law_at_every_site(case: Tuple[List[int], List[int], int]) -> None:
    orders, positions, site_i = case
    keep = [p for p in positions if 0 <= p < len(orders)]
    with tempfile.TemporaryDirectory() as d, fresh(), mock.patch(VEC, VecStub(positions)):
        b = Path(d) / "books"
        book(b, "fm_data", [f"chap-{i}-end foo" for i in range(len(orders))], orders)
        out = SITES[site_i][1](b, "fm_data")
        assert out.hits == [(orders[p], f"sem-pos-{p}", 100 + p, "semantic") for p in keep]
        assert out.count == len(keep)
        if out.book_order is not None and not keep:
            assert "fm_data" not in out.rs.grouped_by_book


# --------------------------------------------------------------------------- SO-10 (paired integration)


def test_so_10_real_chromadb_on_a_gap_epub_emits_only_member_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.setattr("reader3_app.vector_search._build_embedding_function", lambda factory: QueryHashEmbedder())
    epub = build_gap_epub(tmp_path / "g.epub", [
        GapItem("a", "a.xhtml", XHTML, "CH-A-MARKER"),
        GapItem("p", "p.svg", SVG, "GAP-PAGE-MARKER"),
        GapItem("b", "b.xhtml", XHTML, "CH-B-MARKER"),
    ])
    books = tmp_path / "books"
    books.mkdir()
    reader3.process_epub(str(epub), str(books / "gap_data"))
    with fresh():
        loaded = book_store.load_book_cached("gap_data", str(books))
        assert book_store.chapter_orders(loaded, book_id="gap_data") == (0, 2)
        vector_search.BookVectorIndex("gap_data", books_dir=str(books)).index_book()
        for name, site in SITES:
            out = site(books, "gap_data", "CH-B-MARKER")
            assert {o for o, _, _, _ in out.hits} == {0, 2}, (name, out.hits)
            for r in out.semantic:
                ch = book_store.find_chapter(loaded, r.chapter_order, book_id="gap_data")
                assert ch is not None and r.match_text in ch.text, (name, r.chapter_order, r.match_text)
            assert [r.chapter_order for r in out.semantic if "CH-B-MARKER" in r.match_text] == [2], name
            if name.endswith("hybrid"):
                kw = [r.chapter_order for r in out.results if r.mode == "keyword"]
                assert kw == [2], (name, kw)


# --------------------------------------------------------------------------- SO-08 (no memo, no mutation)

MEMOS_AT_BASE = (
    {"_load_book_index_for_stat", "load_book_cached", "load_book_index"},
    {"_load_book_for_stat", "load_book_cached"},
)


def _memos() -> Tuple[set, set]:
    return (
        {n for n, v in vars(search_service).items() if hasattr(v, "cache_info")},
        {n for n, v in vars(book_store).items() if hasattr(v, "cache_info")},
    )


def test_so_08_repeated_searches_leave_the_book_and_the_memo_set_unchanged(books: Path) -> None:
    G(books, "g02_data", [0, 2])
    b0 = book_store.load_book_cached("g02_data", str(books))
    before = pickle.dumps(b0)
    keys0 = [set(vars(c)) for c in b0.spine]
    memos0 = _memos()
    dumps, marks = [], []
    for i in range(100):
        if i % 2 == 0:
            dumps.append(dump(_search("g02_data", books, "text-of-order")))
        else:
            marks.append(search_service.highlight_ranges_for_chapter(
                "g02_data", 0, search_term="uniq-0-end", occurrence_index=None, case_sensitive=False,
                books_dir=str(books),
            ))
    assert all(d == dumps[0] for d in dumps) and len(dumps) == 50
    assert all(m == marks[0] for m in marks) and len(marks) == 50
    assert book_store.load_book_cached("g02_data", str(books)) is b0
    assert pickle.dumps(b0) == before
    assert [set(vars(c)) for c in b0.spine] == keys0
    assert search_service.load_book_index.cache_info().misses == 1  # type: ignore[attr-defined]
    assert _memos() == memos0 == MEMOS_AT_BASE
    assert os.path.exists(books / "g02_data" / "book.pkl")
    assert text(0) in b0.spine[0].text
