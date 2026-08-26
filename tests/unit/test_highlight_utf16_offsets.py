"""WI-20: highlight offsets must be published in BOTH code-point and UTF-16 units.

Why this file exists
--------------------
`highlight_ranges_for_chapter()` returns match offsets that the browser feeds
into a DOM `Range`. Python string indices count **code points**; DOM ranges
count **UTF-16 code units**. Every non-BMP character (emoji, CJK Extension B+
ideographs, historic scripts) occupies ONE code point but TWO UTF-16 units, so
a single such character anywhere before -- or inside -- a match shifts the
rendered highlight. This is a Chinese-language reader; extension-area
ideographs are not exotic.

The contract under test: the range dicts keep their existing code-point
`start`/`end` (the frontend has not migrated yet -- that is 010/013) and gain
`start_utf16`/`end_utf16` alongside them.

No disk I/O, no fixture book, no `books/` access: the book loader is
monkeypatched with an in-memory stub, so what is exercised here is the pure
offset arithmetic on a string we control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from reader3_app import search_service

BOOKS_DIR_NEVER_TOUCHED = "/dev/null/reader3-wi20-no-such-books-dir"


@dataclass
class _FakeChapter:
    text: str
    title: str = "Chapter One"
    order: int = 0


@dataclass
class _FakeMetadata:
    title: str = "Fake Book"
    authors: List[str] = field(default_factory=lambda: ["Nobody"])


@dataclass
class _FakeBook:
    spine: List[_FakeChapter]
    metadata: _FakeMetadata = field(default_factory=_FakeMetadata)
    toc: List[Any] = field(default_factory=list)


def _ranges_for(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    term: str,
    *,
    case_sensitive: bool = False,
    occurrence_index: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[int]]:
    """Run the real highlight path over `text`, with the loader stubbed out."""
    book = _FakeBook(spine=[_FakeChapter(text=text)])
    monkeypatch.setattr(search_service, "load_book_cached", lambda book_id, books_dir: book)
    search_service.load_book_index.cache_clear()
    try:
        return search_service.highlight_ranges_for_chapter(
            "wi20_fake_data",
            0,
            search_term=term,
            occurrence_index=occurrence_index,
            case_sensitive=case_sensitive,
            books_dir=BOOKS_DIR_NEVER_TOUCHED,
        )
    finally:
        search_service.load_book_index.cache_clear()


def _utf16_units(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


# --------------------------------------------------------------------------
# U1 -- load-bearing: a non-BMP character BEFORE the match shifts the UTF-16
# offset by an exact, named amount.
# --------------------------------------------------------------------------


def test_u1_emoji_prefix_shifts_utf16_start_by_exactly_two(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "\U0001F30D\U0001F30DabcTARGETdef"  # two earth-globe emoji, each 2 UTF-16 units
    assert len(text[:5]) == 5, "sanity: Python counts the two emoji as one code point each"
    assert _utf16_units(text[:5]) == 7, "sanity: the same prefix is 7 UTF-16 units"

    ranges, total, selected = _ranges_for(monkeypatch, text, "TARGET")

    assert total == 1
    assert selected == 0
    assert len(ranges) == 1
    r = ranges[0]

    # Concrete numbers on both sides. An implementation that merely returns
    # "something different from `start`" (e.g. start + 1) must fail here.
    assert r["start"] == 5
    assert r["end"] == 11
    assert r["start_utf16"] == 7
    assert r["end_utf16"] == 13
    assert r["start_utf16"] - r["start"] == 2
    assert r["end_utf16"] - r["end"] == 2


# --------------------------------------------------------------------------
# U2 -- a non-BMP character INSIDE the match: end_utf16 must cover all of it,
# and the UTF-16 slice must decode back to exactly the matched substring.
# --------------------------------------------------------------------------


def test_u2_non_bmp_inside_match_widens_only_the_utf16_span(monkeypatch: pytest.MonkeyPatch) -> None:
    needle = "a\U0001F30Db"  # 3 code points, 4 UTF-16 units
    text = "prefix " + needle + " suffix"

    ranges, total, _selected = _ranges_for(monkeypatch, text, needle)

    assert total == 1
    r = ranges[0]

    assert r["end"] - r["start"] == 3
    assert r["end_utf16"] - r["start_utf16"] == 4

    # The numbers being plausible is not enough: cut the raw UTF-16 buffer with
    # the published offsets and require the bytes to decode to the match itself.
    buf = text.encode("utf-16-le")
    sliced = buf[r["start_utf16"] * 2 : r["end_utf16"] * 2].decode("utf-16-le")
    assert sliced == needle
    assert text[r["start"] : r["end"]] == needle


def test_u2b_second_match_after_a_non_bmp_match_still_slices_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offsets accumulate correctly across several matches, not just the first."""
    needle = "\U00020BB7字"  # CJK Ext-B ideograph (non-BMP) + a BMP hanzi
    text = "开头" + needle + "中间" + needle + "结尾"

    ranges, total, _selected = _ranges_for(monkeypatch, text, needle)

    assert total == 2
    assert len(ranges) == 2

    buf = text.encode("utf-16-le")
    for i, r in enumerate(ranges):
        assert r["occurrence_index"] == i
        assert text[r["start"] : r["end"]] == needle
        assert buf[r["start_utf16"] * 2 : r["end_utf16"] * 2].decode("utf-16-le") == needle

    # The second occurrence sits after one non-BMP char, so its drift is larger.
    assert ranges[0]["start_utf16"] - ranges[0]["start"] == 0
    assert ranges[1]["start_utf16"] - ranges[1]["start"] == 1


# --------------------------------------------------------------------------
# U3 -- pure-BMP text: the two unit systems agree (regression guard).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,term",
    [
        pytest.param("hello TARGET world, hello again", "TARGET", id="ascii"),
        pytest.param("第一章：目标文字在此处", "目标", id="bmp-cjk"),
        pytest.param("café TARGET naïve", "TARGET", id="bmp-latin-accents"),
    ],
)
def test_u3_bmp_only_text_keeps_both_offset_systems_identical(
    monkeypatch: pytest.MonkeyPatch, text: str, term: str
) -> None:
    ranges, total, _selected = _ranges_for(monkeypatch, text, term)

    assert total >= 1
    assert ranges
    for r in ranges:
        assert r["start_utf16"] == r["start"]
        assert r["end_utf16"] == r["end"]


# --------------------------------------------------------------------------
# U4 -- the pre-existing code-point fields survive unchanged; 010/013 have not
# migrated the frontend yet, so nothing may be renamed or removed.
# --------------------------------------------------------------------------


def test_u4_existing_code_point_fields_and_shape_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "alpha TARGET beta TARGET gamma"

    ranges, total, selected = _ranges_for(monkeypatch, text, "TARGET", occurrence_index=1)

    assert total == 2
    assert selected == 1
    assert len(ranges) == 2

    first, second = ranges
    assert first["start"] == text.index("TARGET")
    assert first["end"] == text.index("TARGET") + len("TARGET")
    assert second["start"] == text.rindex("TARGET")
    assert second["end"] == text.rindex("TARGET") + len("TARGET")

    for i, r in enumerate(ranges):
        assert r["style"] == "search-match"
        assert r["occurrence_index"] == i
        assert set(r.keys()) == {
            "start",
            "end",
            "style",
            "occurrence_index",
            "start_utf16",
            "end_utf16",
        }
        for key in ("start", "end", "start_utf16", "end_utf16"):
            assert isinstance(r[key], int)


def test_u4b_no_match_returns_no_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    ranges, total, selected = _ranges_for(monkeypatch, "\U0001F30D nothing to find here", "TARGET")

    assert ranges == []
    assert total == 0
    assert selected is None
