"""012 WI-4c.3b: ``highlight_ranges_for_chapter`` addresses a chapter by its ADR-0016 order.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c3.md`` r2, cases HL-01..HL-05 (service level). Binding: the plan's
"Coordinator rulings 2026-10-09 (WI-4c.3)" -- a negative / gap / past-the-end order is not a chapter
(``IndexError``, which the route maps to 404); ``BookCorrupt`` propagates untouched (central 500, DP-7); L-F holds
over non-blank terms only and a blank term is pinned separately (HL-04).

Books are real flat pickles in a tmp ``books/`` (``wi4c3_world.book`` / ``G``); no doubles. The book strategy and
the term pool are SO-02's (imported from ``test_search_order``, not copied).

Green-first by design: HL-03 (gapless characterization; literals captured before the 3b change, see the case) and
HL-04 (blank-first guard). HL-01, HL-02 and HL-05 are red against the 4c.3a commit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from test_search_order import _term_pool, books_st
from wi4c3_world import NOMATCH, G, book, fresh

from reader3_app import book_format, search_service
from reader3_app.search_service import SearchQuery


@pytest.fixture
def books(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    b = tmp_path / "books"
    b.mkdir()
    monkeypatch.chdir(tmp_path)
    with fresh():
        yield b


def _hl(folder: str, books: Path, n: int, term: str, occ: Optional[int] = None, cs: bool = False) -> Any:
    return search_service.highlight_ranges_for_chapter(
        folder, n, search_term=term, occurrence_index=occ, case_sensitive=cs, books_dir=str(books)
    )


def _R(s: int, e: int, i: int, s16: Optional[int] = None, e16: Optional[int] = None) -> Dict[str, Any]:
    return {
        "start": s, "end": e,
        "start_utf16": s if s16 is None else s16, "end_utf16": e if e16 is None else e16,
        "style": "search-match", "occurrence_index": i,
    }


# --------------------------------------------------------------------------- strategies


@st.composite
def round_trip_case(draw: Any) -> Tuple[List[int], List[str], str, bool]:
    """SO-02's books; the repeated-term variant forces >= 2 ``foo`` into one drawn chapter."""
    orders, texts = draw(books_st())
    if draw(st.booleans()):
        i = draw(st.integers(0, len(orders) - 1))
        extra = draw(st.lists(st.just("foo"), min_size=2, max_size=4))
        texts = list(texts)
        texts[i] = texts[i] + " " + " ".join(extra)
    term = draw(st.sampled_from([t for t in _term_pool(len(orders)) if t != NOMATCH]))
    return orders, texts, term, draw(st.booleans())


@st.composite
def membership_case(draw: Any) -> Tuple[List[int], List[str], str, bool]:
    orders, texts = draw(books_st())
    return orders, texts, draw(st.sampled_from(_term_pool(len(orders)))), draw(st.booleans())


# --------------------------------------------------------------------------- HL-01 (L-E, S5)


@settings(max_examples=50, deadline=None)
@example(case=([0, 2], ["foo foo", "foo"], "foo", False))
@example(case=([1, 3], ["chap-0-end foo", "chap-1-end FOO foo foo"], "foo", False))
@given(case=round_trip_case())
def test_hl_01_every_keyword_hit_round_trips_through_highlight(case: Tuple[List[int], List[str], str, bool]) -> None:
    orders, texts, term, cs = case
    with tempfile.TemporaryDirectory() as d, fresh():
        b = Path(d) / "books"
        book(b, "rt_data", texts, orders)
        rs = search_service.search_book(
            "rt_data", SearchQuery(term=term, case_sensitive=cs, max_results=1000), books_dir=str(b)
        )
        per_chapter: Dict[int, int] = {}
        for h in rs.results:
            assert h.chapter_order in orders, (h.chapter_order, orders)
            per_chapter[h.chapter_order] = per_chapter.get(h.chapter_order, 0) + 1
        totals: Dict[int, int] = {}
        for h in rs.results:
            ranges, total, selected = _hl("rt_data", b, h.chapter_order, term, h.occurrence_index, cs)
            r = ranges[h.occurrence_index]
            assert (r["start"], r["end"]) == (h.position, h.position + len(h.match_text)), h
            assert selected == h.occurrence_index, h
            assert total == per_chapter[h.chapter_order], h
            totals[h.chapter_order] = total
        assert sum(totals.values()) == rs.total_matches


# --------------------------------------------------------------------------- HL-02 (L-F, S4)


@settings(max_examples=50, deadline=None)
@example(case=([1, 3], ["chap-0-end foo", "chap-1-end foo"], "foo", False))
@example(case=([0, 2], ["chap-0-end foo", "chap-1-end foo bar"], "chap-1-end", False))
@given(case=membership_case())
def test_hl_02_highlight_resolves_exactly_the_member_orders(case: Tuple[List[int], List[str], str, bool]) -> None:
    orders, texts, term, cs = case
    members = set(orders)
    with tempfile.TemporaryDirectory() as d, fresh():
        b = Path(d) / "books"
        book(b, "mb_data", texts, orders)
        for n in range(-3, max(orders) + 4):
            if n in members:
                t = texts[orders.index(n)]
                m = search_service.search_text(t, term, case_sensitive=cs, max_results=1000)
                ranges, total, selected = _hl("mb_data", b, n, term, None, cs)
                assert [(r["start"], r["end"]) for r in ranges] == m, n
                assert (total, selected) == (len(m), 0 if m else None), n
            else:
                with pytest.raises(IndexError) as exc:
                    _hl("mb_data", b, n, term, None, cs)
                assert str(exc.value) == "chapter out of range", n


# --------------------------------------------------------------------------- HL-03 (gapless characterization)

# Literals captured with the pre-3b ``highlight_ranges_for_chapter`` (HEAD de99cbc, i.e. 4c.3a, which did not touch
# the highlight path for a gapless book), cross-checked by hand against the texts below. Never regenerate them from
# the code under test.
HL03_EXPECTED: List[Tuple[str, int, str, Optional[int], Any]] = [
    ("c1_data", 0, "cafe", 2, ([_R(3, 7, 0), _R(19, 23, 1), _R(24, 28, 2)], 3, 2)),
    ("c3_data", 1, "foo", 1, ([_R(6, 9, 0), _R(10, 13, 1)], 2, 1)),
    ("c5_data", 1, "foo", None, ([_R(1, 4, 0, 2, 5), _R(6, 9, 1, 8, 11)], 2, 0)),
    ("c5_data", 4, "foo", 9, ([_R(3, 6, 0)], 1, 0)),
]


def test_hl_03_gapless_highlight_is_unchanged(books: Path) -> None:
    book(books, "c1_data", ["Le café est fermé. café CAFÉ"], None)
    book(books, "c3_data", ["alpha café beta", "gamma foo foo", "delta cafe"], None)
    book(books, "c5_data", ["日本語の本 foo", "\U00020000foo\U00020000 foo", "foo", "none here", "末尾 foo"], None)
    for bid, n, term, occ, expected in HL03_EXPECTED:
        assert _hl(bid, books, n, term, occ) == expected, (bid, n, term, occ)
    with pytest.raises(IndexError):
        _hl("c5_data", books, 5, "foo")


# --------------------------------------------------------------------------- HL-04 (blank term, guard)


@pytest.mark.parametrize("term", ["", "   ", "\t\n"], ids=["empty", "spaces", "tab-newline"])
def test_hl_04_blank_term_is_empty_before_any_chapter_resolution(books: Path, term: str) -> None:
    G(books, "g02_data", [0, 2])
    book(books, "x21_data", ["uniq-a", "uniq-b"], [2, 1])
    for bid, n in (("g02_data", 1), ("g02_data", -1), ("g02_data", 3), ("x21_data", 1)):
        assert _hl(bid, books, n, term) == ([], 0, None), (bid, n)


# --------------------------------------------------------------------------- HL-05 (corrupt, S3)


@pytest.mark.parametrize("folder, orders", [("x21_data", [2, 1]), ("x00_data", [0, 0])], ids=["x21", "x00"])
@pytest.mark.parametrize("n", [0, 1, 2])
def test_hl_05_corrupt_orders_raise_bookcorrupt_not_indexerror(
    books: Path, folder: str, orders: List[int], n: int
) -> None:
    book(books, folder, ["uniq-a", "uniq-b"], orders)
    with pytest.raises(Exception) as exc:
        _hl(folder, books, n, "uniq")
    assert type(exc.value) is book_format.BookCorrupt, (folder, n, type(exc.value).__name__)
