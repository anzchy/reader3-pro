"""WI-9 (C2): `_normalize_with_map`'s index map becomes an `array("I")`.

What changes and what must not
------------------------------
`search_service._normalize_with_map` returns `(normalized_text, index_map)`,
where `index_map[i]` is the index into the ORIGINAL text of the character that
produced `normalized_text[i]`. Today that map is a `list[int]`: one Python int
object per character, ~28 bytes of object plus 8 bytes of pointer, so a
three-million-character book pays around a hundred megabytes for what is a
vector of small non-negative integers. `array("I")` stores the same values in
four bytes each and still answers `len()` and `map[i]`.

The values themselves are load-bearing in a way the container is not:
`highlight_ranges_for_chapter()` turns them into the spans a browser paints on
the page, so an off-by-one here is a highlight drawn over the wrong words. Two
kinds of test guard that, and they guard it from opposite directions:

* The **differential** cases below compare the live implementation against
  `_reference_normalize_with_map`, a verbatim copy of the pre-WI-9 code kept in
  this file as the judge. They are trivially green while the two are the same
  code -- their value arrives the moment the production side changes, as proof
  that nothing moved. They are NOT evidence of a red-first ordering, and are
  not claimed as such.
* The **container** cases (`test_index_map_is_...`, `test_index_map_itemsize_...`)
  assert the new type directly and do fail against the old list. Those are the
  recorded red.

Why the corpus looks the way it does: three normalisation paths can drift
without changing the LENGTH of the output, so a length-only check would pass
while every offset after the drift is wrong -- casefold expansion in the Latin
branch (`ß` -> `ss`), a combining mark dropped inside a Latin run, and the same
mark KEPT outside one (kana). Each has samples here, under both
`case_sensitive` settings, since that flag selects two different mappings.

No disk I/O: the one public-path case stubs the book loader, the same way
`test_highlight_utf16_offsets.py` does.
"""

from __future__ import annotations

import sys
import unicodedata
from array import array
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

import epub_corpus as ec
import unicode_corpus as uc
from reader3_app import search_service
from reader3_app.search_service import (
    _find_spans_with_map,
    _normalize_query,
    _normalize_with_map,
    search_text,
)


# --------------------------------------------------------------------------
# The judge: `_normalize_with_map` exactly as it stood before WI-9 (HEAD
# 04a6839, src/reader3_app/search_service.py:120-156), copied verbatim apart
# from calling the module's `_is_latin_base_char` rather than redefining it.
# This is the reference the new implementation is diffed against; do not
# "improve" it, and do not re-sync it with production -- the moment it tracks
# the code under test it stops being a judge of anything.
# --------------------------------------------------------------------------
def _reference_normalize_with_map(text: str, *, case_sensitive: bool) -> Tuple[str, List[int]]:
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

        if search_service._is_latin_base_char(ch):
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


# --- corpus ----------------------------------------------------------------

#: CJK from the frozen EPUB corpus (read only; that file is in the suite hash).
CJK_SAMPLES: Tuple[str, ...] = (
    (ec.CJK_TITLE,) + ec.CJK_SENTENCES + ("".join(ec.CJK_SENTENCES), ec.CJK_SEARCH_TERM)
)

#: Both spellings of every diacritic pair: the accented form exercises the
#: Latin stripping branch, the ASCII form is its control.
DIACRITIC_SAMPLES: Tuple[str, ...] = tuple(w for pair in ec.DIACRITIC_PAIRS for w in pair)

DIFFERENTIAL_CORPUS: Tuple[str, ...] = (
    uc.NORMALIZE_DIFFERENTIAL_SAMPLES + CJK_SAMPLES + DIACRITIC_SAMPLES
)

CASE_FLAGS = (False, True)


def _ids(sample: str) -> str:
    return repr(sample)[:60]


# --- the container itself (these are the cases that fail against a list) ----


def test_index_map_is_an_unsigned_int_array_not_a_list():
    """L1 - the point of WI-9, asserted on the type rather than on a byte count.

    `array("I")` is what makes the memory win possible AND what keeps
    `len(map)` / `map[i]` working for `_find_spans_with_map`. Asserting
    `isinstance` before touching `.typecode` matters: against the old list the
    failure must be an assertion, not an AttributeError.
    """
    _, index_map = _normalize_with_map(uc.PLAIN_ASCII, case_sensitive=False)

    assert isinstance(index_map, array), (
        f"index_map should be array('I'), got {type(index_map).__name__}"
    )
    assert index_map.typecode == "I"
    assert len(index_map) == len(uc.PLAIN_ASCII)
    assert index_map[0] == 0
    assert index_map[len(index_map) - 1] == len(uc.PLAIN_ASCII) - 1


def test_index_map_itemsize_is_wide_enough_for_a_real_books_offsets():
    """L1 - a 2-byte `unsigned int` would raise OverflowError past 65535.

    The C standard only requires `unsigned int` to be at least 2 bytes, and
    `array` raises rather than wrapping, so on such a platform every chapter
    longer than 65535 characters would blow up at index time. A novel chapter
    clears that easily, so the guard is a real one, not a formality: the text
    below is deliberately longer than 65536 characters.
    """
    text = "a" * 70_000
    normalized, index_map = _normalize_with_map(text, case_sensitive=False)

    assert isinstance(index_map, array), (
        f"index_map should be array('I'), got {type(index_map).__name__}"
    )
    assert index_map.itemsize >= 4, (
        f"array('I') is {index_map.itemsize} bytes wide on this platform; offsets "
        "above 65535 would raise OverflowError. Use a wider typecode."
    )
    assert len(normalized) == 70_000
    assert len(index_map) == 70_000
    assert index_map[65_536] == 65_536
    assert index_map[69_999] == 69_999


def test_empty_text_yields_an_empty_array_not_an_empty_list():
    """L1 - the degenerate input still has to carry the new container type."""
    normalized, index_map = _normalize_with_map("", case_sensitive=False)

    assert normalized == ""
    assert isinstance(index_map, array), (
        f"index_map should be array('I'), got {type(index_map).__name__}"
    )
    assert len(index_map) == 0
    assert list(index_map) == []


# --- differential: the offsets must not move -------------------------------


@pytest.mark.parametrize("case_sensitive", CASE_FLAGS, ids=lambda f: f"cs={f}")
@pytest.mark.parametrize("sample", DIFFERENTIAL_CORPUS, ids=_ids)
def test_normalised_text_and_index_map_match_the_pre_wi9_implementation(
    sample: str, case_sensitive: bool
):
    """L1 - element-by-element equality with the old code, both case paths.

    Length equality alone is not enough and is asserted only as a precondition:
    casefold expansion and combining-mark removal can cancel out, leaving a map
    of the right size whose every entry after the drift points one character
    wrong.
    """
    ref_text, ref_map = _reference_normalize_with_map(sample, case_sensitive=case_sensitive)
    new_text, new_map = _normalize_with_map(sample, case_sensitive=case_sensitive)

    assert new_text == ref_text
    assert len(new_map) == len(ref_map)
    assert list(new_map) == list(ref_map)
    for i in range(len(ref_map)):
        assert new_map[i] == ref_map[i], (
            f"index_map[{i}] drifted: {new_map[i]} != {ref_map[i]} for {sample!r}"
        )


@pytest.mark.parametrize("case_sensitive", CASE_FLAGS, ids=lambda f: f"cs={f}")
@pytest.mark.parametrize("sample", DIFFERENTIAL_CORPUS, ids=_ids)
def test_every_entry_is_a_valid_non_decreasing_offset_into_the_original(
    sample: str, case_sensitive: bool
):
    """L1 - the invariant `_find_spans_with_map` relies on, stated directly.

    Spans are built as `(map[start], map[end - 1] + 1)`, which is only a span
    at all if the map never runs backwards and never points past the text.
    """
    _, index_map = _normalize_with_map(sample, case_sensitive=case_sensitive)

    previous = -1
    for i in range(len(index_map)):
        value = index_map[i]
        assert 0 <= value < len(sample)
        assert value >= previous
        previous = value


@pytest.mark.parametrize("case_sensitive", CASE_FLAGS, ids=lambda f: f"cs={f}")
def test_casefold_expansion_still_points_both_halves_at_the_one_original_char(
    case_sensitive: bool,
):
    """L1 - the expansion path pinned by value, not only by differential.

    `ß` -> `ss` when folding; with `case_sensitive=True` no folding happens and
    the map is the identity. Both are written out so the two paths cannot be
    confused for one another.
    """
    normalized, index_map = _normalize_with_map(uc.SHARP_S_WORD, case_sensitive=case_sensitive)

    if case_sensitive:
        assert normalized == uc.SHARP_S_WORD
        assert list(index_map) == [0, 1, 2, 3, 4, 5]
    else:
        assert normalized == uc.SHARP_S_CASEFOLDED
        assert list(index_map) == [0, 1, 2, 3, 4, 4, 5]


@pytest.mark.parametrize("case_sensitive", CASE_FLAGS, ids=lambda f: f"cs={f}")
def test_non_latin_casefold_expansion_points_every_piece_at_one_original_char(
    case_sensitive: bool,
):
    """L1 - the branch no sample reached: multi-character folding of a NON-Latin char.

    Why this case exists, measured rather than assumed. Every expanding sample
    in this suite until now (`ß` -> `ss`, `ﬀ` -> `ff`) is named "LATIN ..." and
    therefore takes the Latin branch of `_normalize_with_map`. The branch at the
    end of that function -- everything else -- had only single-character samples
    (CJK, kana), so its `for out_ch in to_emit` loop turned exactly once and an
    off-by-one *inside* the loop could not show. With that loop sabotaged to emit
    `original_index + k` for the k-th character, all 193 cases across this file
    and `test_fixture_unicode_corpus.py` stayed green.

    The maps are hard-coded, not diffed against `_reference_normalize_with_map`:
    the reference is a copy of the same algorithm, so it cannot catch an error
    both copies would make. Two code points with different expansion factors
    (3 and 2) mean a hard-wired factor of 2 is caught too, and each sits between
    ordinary characters so the offsets that FOLLOW the expansion are pinned --
    the usual symptom of this bug is every later index shifted by the surplus.
    """
    # The premise: these really do expand, and really are not Latin.
    assert len(uc.GREEK_IOTA_DIALYTIKA_TONOS.casefold()) == 3
    assert len(uc.ARMENIAN_LIGATURE_MEN_NOW.casefold()) == 2
    assert not search_service._is_latin_base_char(uc.GREEK_IOTA_DIALYTIKA_TONOS)
    assert not search_service._is_latin_base_char(uc.ARMENIAN_LIGATURE_MEN_NOW)

    greek_text, greek_map = _normalize_with_map(
        uc.GREEK_TRIPLE_EXPANSION_RUN, case_sensitive=case_sensitive
    )
    armenian_text, armenian_map = _normalize_with_map(
        uc.ARMENIAN_DOUBLE_EXPANSION_RUN, case_sensitive=case_sensitive
    )
    mixed_text, mixed_map = _normalize_with_map(
        uc.NON_LATIN_EXPANSION_MIX, case_sensitive=case_sensitive
    )

    if case_sensitive:
        # No folding happens at all, so `to_emit` is one character and every map
        # is the identity. Stated separately because it is a different mapping,
        # not a weaker version of the one below.
        assert greek_text == uc.GREEK_TRIPLE_EXPANSION_RUN
        assert list(greek_map) == [0, 1, 2]
        assert armenian_text == uc.ARMENIAN_DOUBLE_EXPANSION_RUN
        assert list(armenian_map) == [0, 1, 2]
        assert mixed_text == uc.NON_LATIN_EXPANSION_MIX
        assert list(mixed_map) == list(range(len(uc.NON_LATIN_EXPANSION_MIX)))
        return

    # Three normalised characters all pointing at index 1, and 'β' still at 2 --
    # not pushed to 4 by the two surplus characters in front of it.
    assert len(greek_text) == 5
    assert list(greek_map) == [0, 1, 1, 1, 2]

    # The same shape with a factor of 2 instead of 3.
    assert len(armenian_text) == 4
    assert list(armenian_map) == [0, 1, 1, 2]

    # Both factors in one pass, with CJK between them: "αΐβ 咖啡 աﬓբ".
    assert len(uc.NON_LATIN_EXPANSION_MIX) == 10
    assert len(mixed_text) == 13
    assert list(mixed_map) == [0, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 8, 9]


def test_a_combining_mark_is_dropped_in_a_latin_run_and_kept_outside_one():
    """L1 - the two opposite branches, in one string, checked by offset.

    `LATIN_THEN_KANA_COMBINING` is `abc` + kana + combining mark + `def`. The
    mark survives because its base is not Latin; the acute in `NFD_CAFE` does
    not, because its base is.
    """
    kana_text, kana_map = _normalize_with_map(
        uc.LATIN_THEN_KANA_COMBINING, case_sensitive=False
    )
    assert kana_text == uc.LATIN_THEN_KANA_COMBINING
    assert list(kana_map) == list(range(len(uc.LATIN_THEN_KANA_COMBINING)))

    latin_text, latin_map = _normalize_with_map(uc.NFD_CAFE, case_sensitive=False)
    assert latin_text == "cafe"
    assert list(latin_map) == [0, 1, 2, 3]
    assert len(uc.NFD_CAFE) == 5  # the combining acute at index 4 has no entry


def test_a_leading_combining_mark_is_emitted_with_its_own_offset():
    """L1 - boundary: the mark arrives before any Latin run has opened."""
    normalized, index_map = _normalize_with_map(uc.LEADING_COMBINING, case_sensitive=False)

    assert normalized == uc.LEADING_COMBINING
    assert list(index_map) == [0, 1, 2, 3]


@pytest.mark.parametrize("sample", CJK_SAMPLES, ids=_ids)
def test_cjk_maps_one_to_one_through_both_case_settings(sample: str):
    """L1 - CJK takes the general branch: no folding, no stripping, identity map."""
    folded_text, folded_map = _normalize_with_map(sample, case_sensitive=False)
    exact_text, exact_map = _normalize_with_map(sample, case_sensitive=True)

    assert exact_text == sample
    assert list(exact_map) == list(range(len(sample)))
    assert len(folded_map) == len(folded_text)
    assert list(folded_map) == list(_reference_normalize_with_map(sample, case_sensitive=False)[1])


# --- the public paths that consume the map ---------------------------------


@pytest.mark.parametrize(
    "haystack,needle,case_sensitive",
    [
        (uc.SHARP_S_WORD, "s", False),
        (uc.NFD_SENTENCE, uc.NFC_CAFE, False),
        (uc.ASTRAL_HAYSTACK, uc.ASTRAL_NEEDLE, False),
        ("".join(ec.CJK_SENTENCES), ec.CJK_SEARCH_TERM, False),
        (uc.MIXED_SCRIPT_RUN, "straße", False),
        (uc.MIXED_SCRIPT_RUN, "Straße", True),
        (uc.PLAIN_ASCII, "THE", False),
        (uc.PLAIN_ASCII, "THE", True),
    ],
    ids=lambda v: repr(v)[:30],
)
def test_search_text_spans_are_identical_to_the_pre_wi9_implementation(
    haystack: str, needle: str, case_sensitive: bool
):
    """L2 - offsets as the caller sees them, computed twice and compared.

    The reference spans are derived from the reference map by the same span
    arithmetic production uses, so any difference is the map, not the search.
    """
    import re

    ref_text, ref_map = _reference_normalize_with_map(haystack, case_sensitive=case_sensitive)
    ref_term = _reference_normalize_with_map(needle, case_sensitive=case_sensitive)[0]
    expected: List[Tuple[int, int]] = []
    for m in re.finditer(re.escape(ref_term), ref_text):
        start_n, end_n = m.span()
        if start_n >= len(ref_map) or end_n - 1 >= len(ref_map):
            continue
        expected.append((ref_map[start_n], ref_map[end_n - 1] + 1))

    actual = search_text(haystack, needle, case_sensitive=case_sensitive, max_results=1000)

    assert actual == expected
    for start, end in actual:
        assert 0 <= start < end <= len(haystack)


def test_search_text_span_values_are_plain_ints_not_numpy_like_objects():
    """L2 - `array` yields real Python ints, so the JSON payload is unchanged.

    The spans end up in a FastAPI response; a value that merely compares equal
    to an int but serialises differently would pass every `==` above and still
    break the wire format.
    """
    (start, end), = search_text(uc.NFD_SENTENCE, uc.NFC_CAFE, case_sensitive=False, max_results=10)

    assert type(start) is int
    assert type(end) is int


def test_find_spans_with_map_accepts_the_array_container():
    """L1 - the one internal consumer, called directly with the new type."""
    normalized, index_map = _normalize_with_map(uc.SHARP_S_WORD, case_sensitive=False)
    term = _normalize_query("s", case_sensitive=False)

    spans, total = _find_spans_with_map(normalized, index_map, term, max_spans=10)

    assert spans == [(0, 1), (4, 5), (4, 5)]
    assert total == 3


# --- highlight_ranges_for_chapter: the offsets that reach the browser ------


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
) -> Tuple[List[Dict[str, Any]], int, Optional[int]]:
    book = _FakeBook(spine=[_FakeChapter(text=text)])
    monkeypatch.setattr(search_service, "load_book_cached", lambda book_id, books_dir: book)
    search_service.load_book_index.cache_clear()
    try:
        return search_service.highlight_ranges_for_chapter(
            "wi9_fake_data",
            0,
            search_term=term,
            occurrence_index=None,
            case_sensitive=case_sensitive,
            books_dir="/dev/null/reader3-wi9-no-such-books-dir",
        )
    finally:
        search_service.load_book_index.cache_clear()


def test_highlight_ranges_over_cjk_are_the_offsets_recorded_before_the_change(
    monkeypatch: pytest.MonkeyPatch,
):
    """L2 - end-to-end through `ChapterIndex`, with the numbers written out.

    Hard-coded rather than recomputed: a reference-vs-reference comparison
    cannot catch a change that happens to affect both sides, and these are the
    exact integers a browser would receive.
    """
    text = ec.CJK_SENTENCES[0]  # 他在咖啡館裡等了很久。
    ranges, total, selected = _ranges_for(monkeypatch, text, ec.CJK_SEARCH_TERM)

    assert total == 1
    assert selected == 0
    assert ranges[0]["start"] == 2
    assert ranges[0]["end"] == 4
    assert ranges[0]["start_utf16"] == 2
    assert ranges[0]["end_utf16"] == 4
    assert text[2:4] == ec.CJK_SEARCH_TERM


def test_highlight_ranges_survive_a_casefold_expansion_before_the_match(
    monkeypatch: pytest.MonkeyPatch,
):
    """L2 - 'ß' expands to two normalised chars, so a naive map shifts by one.

    The word after it is what the reader asked for; if the expansion is not
    folded back through the map, the highlight lands one character left.
    """
    text = "Straße und Gasse"
    ranges, total, _ = _ranges_for(monkeypatch, text, "Gasse")

    assert total == 1
    assert ranges[0]["start"] == 11
    assert ranges[0]["end"] == 16
    assert text[11:16] == "Gasse"


def test_highlight_ranges_after_an_astral_character_keep_both_unit_systems(
    monkeypatch: pytest.MonkeyPatch,
):
    """L2 - the code-point / UTF-16 divergence must survive the container swap."""
    ranges, total, _ = _ranges_for(monkeypatch, uc.ASTRAL_HAYSTACK, uc.ASTRAL_NEEDLE)

    assert total == 1
    assert ranges[0]["start"] == uc.ASTRAL_NEEDLE_CODE_POINT_START
    assert ranges[0]["start_utf16"] == uc.ASTRAL_NEEDLE_CODE_UNIT_START
    assert ranges[0]["start"] != ranges[0]["start_utf16"]


# --- the memory claim, measured rather than asserted from a plan ----------


def _deep_size_of_list(values: List[int]) -> int:
    """List container plus every int object it points at.

    `sys.getsizeof(list)` counts the pointer array only. Small ints are
    interned and shared, so this over-counts them; offsets into a real book run
    into the millions and are not interned, which is the case that matters.
    """
    return sys.getsizeof(values) + sum(sys.getsizeof(v) for v in values)


def test_the_array_map_costs_a_fraction_of_the_list_map():
    """L1 - the reason WI-9 exists, measured in this process.

    The threshold is deliberately loose (a third). The real ratio on CPython
    3.10/x86-64 is far better than that; a tight bound would go red on a build
    with different int or pointer sizes and prove nothing about the change.
    """
    text = "咖啡" * 40_000 + "Straße" * 10_000  # 140k characters

    _, ref_map = _reference_normalize_with_map(text, case_sensitive=False)
    _, new_map = _normalize_with_map(text, case_sensitive=False)

    assert len(new_map) == len(ref_map)
    list_bytes = _deep_size_of_list(ref_map)
    array_bytes = sys.getsizeof(new_map)

    assert array_bytes * 3 < list_bytes, (
        f"array map used {array_bytes} bytes, list map {list_bytes}; "
        "the container change is not paying for itself"
    )
