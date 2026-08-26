"""The Unicode corpus, and the one assertion this whole branch exists to enable.

``test_astral_*`` below is the alarm bell described in
tasks/008-test-safety-net.md §3: Python offsets count code points, JavaScript
offsets count UTF-16 code units, and Phase 4 intends to hand server-computed
``ranges`` straight to a browser ``Range``. Every ASCII test agrees with both
readings, so nothing else in this repository would notice.

The rest characterise ``search_service._normalize_with_map``. Several record
behaviour that is arguably wrong -- duplicate spans from casefold expansion, a
match span that stops short of a trailing combining mark, decomposed CJK that
never matches its composed form. Those are marked at the case. Nothing here
asks for a production change; 008 records the present, 011 decides.
"""

from __future__ import annotations

import unicodedata

import pytest

import unicode_corpus as uc
from reader3_app.search_service import _normalize_with_map, search_text


def normalize(text: str):
    return _normalize_with_map(text, case_sensitive=False)


def find(haystack: str, needle: str):
    return search_text(haystack, needle, case_sensitive=False, max_results=10)


# --- the code point / code unit divergence --------------------------------


def test_astral_prefix_makes_the_two_offset_units_disagree_at_the_match_start():
    """L2 - the inequality Phase 4 will trip over, asserted as an inequality.

    Two astral characters sit before the hit, so the same logical position is
    16 in Python and 18 in a browser. Slicing with the wrong unit does not
    error; it returns neighbouring words, which is how this ships unnoticed.
    """
    haystack = uc.ASTRAL_HAYSTACK
    spans = find(haystack, uc.ASTRAL_NEEDLE)
    assert len(spans) == 1
    start, end = spans[0]

    assert start == uc.ASTRAL_NEEDLE_CODE_POINT_START
    assert uc.code_unit_offset(haystack, start) == uc.ASTRAL_NEEDLE_CODE_UNIT_START
    assert start != uc.code_unit_offset(haystack, start)

    # Python's answer is right. A browser handed the same numbers is not.
    assert haystack[start:end] == "caf\u00e9"
    assert uc.slice_by_code_units(haystack, start, end) != haystack[start:end]
    assert uc.slice_by_code_units(haystack, start, end) == "e ca"


def test_astral_inside_the_match_moves_the_end_offset_even_when_the_start_agrees():
    """L2 - an off-by-N correction applied only to ``start`` is still wrong.

    Here the prefix is pure ASCII, so the start offsets agree and a naive fix
    looks correct -- but the needle itself contains a non-BMP letter, so the
    end offsets differ by one and the highlight runs a character short.
    """
    haystack = uc.ASTRAL_INSIDE_HAYSTACK
    (start, end), = find(haystack, uc.ASTRAL_INSIDE_NEEDLE)

    assert uc.code_unit_offset(haystack, start) == start
    assert uc.code_unit_offset(haystack, end) == end + 1
    assert uc.slice_by_code_units(haystack, start, end) != haystack[start:end]


@pytest.mark.parametrize("sample", uc.BMP_ONLY_SAMPLES, ids=lambda s: repr(s))
def test_bmp_samples_count_the_same_in_both_units(sample: str):
    """L2 - the control group. Without it the divergence test proves nothing."""
    assert uc.code_unit_length(sample) == len(sample)


@pytest.mark.parametrize("sample", uc.ASTRAL_SAMPLES, ids=lambda s: repr(s))
def test_astral_samples_count_differently_in_the_two_units(sample: str):
    """L2 - every astral sample must actually contain an astral character."""
    assert uc.code_unit_length(sample) > len(sample)
    assert any(ord(ch) > 0xFFFF for ch in sample)


# --- normalisation forms ---------------------------------------------------


def test_nfc_and_nfd_spellings_are_different_strings_that_normalise_alike():
    """L2 - the pair must stay a pair; NFC-ing the source file would kill it."""
    assert uc.NFC_CAFE != uc.NFD_CAFE
    assert len(uc.NFC_CAFE) == 4 and len(uc.NFD_CAFE) == 5
    assert unicodedata.normalize("NFC", uc.NFD_CAFE) == uc.NFC_CAFE

    assert normalize(uc.NFC_CAFE)[0] == normalize(uc.NFD_CAFE)[0] == "cafe"


def test_matching_a_decomposed_word_returns_a_span_that_excludes_its_accent():
    """L2 - pinned behaviour: the highlight stops one character short.

    The combining acute is dropped during normalisation, so no normalised index
    maps to it and the span ends before it. Extracting ``text[start:end]``
    yields ``cafe``; the orphaned U+0301 that follows re-attaches to whatever
    the renderer puts next. An annotation stored from this span round-trips to
    a different string than the user selected.
    """
    (start, end), = find(uc.NFD_SENTENCE, uc.NFC_CAFE)

    assert uc.NFD_SENTENCE[start:end] == "cafe"
    assert unicodedata.combining(uc.NFD_SENTENCE[end]) != 0


# --- casefold expansion ----------------------------------------------------


def test_casefold_expansion_keeps_the_index_map_aligned_with_the_normalised_text():
    """L2 - one entry per normalised character, both 's' pointing at the 'ß'."""
    normalized, index_map = normalize(uc.SHARP_S_WORD)

    assert normalized == uc.SHARP_S_CASEFOLDED
    assert len(normalized) == len(uc.SHARP_S_WORD) + 1
    assert len(index_map) == len(normalized)
    assert index_map == [0, 1, 2, 3, 4, 4, 5]


def test_casefold_expansion_yields_duplicate_spans_for_a_single_glyph():
    """L2 - pinned behaviour: 'Straße' reports three matches for 's', not two.

    Both halves of the expanded 'ss' map back to the one 'ß', so the same
    span is emitted twice. ``occurrence_index`` in a SearchResult therefore
    counts normalised positions, not glyphs, and "match 3 of 3" points at the
    same characters as match 2.
    """
    spans = find(uc.SHARP_S_WORD, "s")

    assert spans == [(0, 1), (4, 5), (4, 5)]
    assert len(spans) == 3
    assert len(set(spans)) == 2


# --- script-dependent behaviour -------------------------------------------


def test_turkish_dotted_i_normalises_shorter_than_pythons_own_casefold():
    """L2 - the Latin path strips the combining dot that ``str.casefold`` adds."""
    normalized, _ = normalize(uc.TURKISH_DOTTED_I_WORD)

    assert normalized == "istanbul"
    assert uc.TURKISH_DOTTED_I_WORD.casefold() == "i\u0307stanbul"
    assert normalized != uc.TURKISH_DOTTED_I_WORD.casefold()
    assert find(uc.TURKISH_DOTTED_I_WORD, "istanbul") == [(0, 8)]


def test_turkish_dotless_i_is_left_alone():
    """L2 - 'ı' has no diacritic to strip, so it must survive as itself."""
    normalized, _ = normalize(uc.TURKISH_DOTLESS_I_WORD)

    assert normalized == "i\u0131rmak"
    assert "\u0131" in normalized


def test_greek_final_sigma_folds_but_greek_accents_do_not_strip():
    """L2 - pinned behaviour: diacritic stripping is Latin-only (FR-009).

    Case folding converges the two spellings on 'σ', so an all-caps heading and
    a mixed-case body mention *almost* match -- and then the accented 'ύ' keeps
    them apart. A Greek reader searching from the heading finds nothing.
    """
    upper, _ = normalize(uc.GREEK_UPPER)
    mixed, _ = normalize(uc.GREEK_MIXED)

    assert upper == "\u03bf\u03b4\u03c5\u03c3\u03c3\u03b5\u03c5\u03c3"
    assert mixed == "\u03bf\u03b4\u03c5\u03c3\u03c3\u03b5\u03cd\u03c3"
    assert upper.endswith("\u03c3") and mixed.endswith("\u03c3")  # final sigma folded
    assert upper != mixed  # the accent did not
    assert find(uc.GREEK_MIXED, uc.GREEK_UPPER) == []


# --- combining marks on non-Latin bases ------------------------------------


def test_combining_mark_on_a_kana_base_survives_normalisation_unchanged():
    """L2 - the mark is only stripped inside a Latin run, and kana is not Latin."""
    normalized, index_map = normalize(uc.KANA_COMBINING)

    assert normalized == uc.KANA_COMBINING
    assert len(index_map) == len(uc.KANA_COMBINING)
    assert unicodedata.combining(uc.KANA_COMBINING[1]) != 0


def test_decomposed_kana_never_matches_its_composed_spelling():
    """L2 - pinned behaviour: there is no NFC pass, so the two forms are strangers.

    ``がっこう`` typed on a Mac (decomposed) and the same word inside a book
    (composed) are different strings all the way through search. This is the
    CJK counterpart of the café/cafe case that FR-009 does handle.
    """
    assert uc.KANA_COMBINING != uc.KANA_PRECOMPOSED
    assert unicodedata.normalize("NFC", uc.KANA_COMBINING) == uc.KANA_PRECOMPOSED
    assert find(uc.KANA_COMBINING, uc.KANA_PRECOMPOSED) == []


def test_a_variation_selector_is_preserved_and_does_not_block_the_bare_match():
    """L2 - U+FE0F is not combining, so it stays; the bare heart still matches."""
    normalized, _ = normalize(uc.HEART_WITH_VS)

    assert normalized == uc.HEART_WITH_VS
    assert unicodedata.combining(uc.HEART_WITH_VS[1]) == 0
    assert find(uc.HEART_WITH_VS, uc.HEART_WITHOUT_VS) == [(0, 1)]
