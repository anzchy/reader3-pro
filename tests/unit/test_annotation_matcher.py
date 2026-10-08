"""012 WI-2b.1: the strict, whitespace-blind annotation matcher (matrix cases M1-01 … M1-13).

``match_resolution(chapter_text, prefix, quote, suffix)`` removes every ``str.isspace``
character from both sides (``"".join(s.split())``), joins prefix + quote + suffix
*before* stripping, counts overlapping occurrences, and classifies 0 / 1 / >=2 as
unmatched / resolved / ambiguous. An empty quote after stripping is unmatched. There is
no fallback to the bare quote.

Invisible characters are written as Python escapes, never pasted literally.
"""

from __future__ import annotations

from typing import List, Tuple

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from reader3_app.models.annotations import match_resolution

ALL_WS: List[str] = [chr(i) for i in range(0x110000) if chr(i).isspace()]


def _w(x: str) -> str:
    return "".join(x.split())


def _oracle(h: str, p: str, q: str, s: str) -> str:
    hay = _w(h)
    needle = _w(p + q + s)
    n = sum(hay.startswith(needle, i) for i in range(len(hay) + 1)) if needle else 0
    if _w(q) == "" or n == 0:
        return "unmatched"
    return "resolved" if n == 1 else "ambiguous"


# M1-01 -------------------------------------------------------------------------------


def test_m1_01_exactly_one_occurrence_is_resolved() -> None:
    assert match_resolution("alpha QUOTE-ONE beta.", "alpha ", "QUOTE-ONE", " beta") == "resolved"


# M1-02 -------------------------------------------------------------------------------


@pytest.mark.parametrize("haystack", ["x Q y. x Q y.", "x Q y. x Q y. x Q y."])
def test_m1_02_two_and_three_occurrences_are_ambiguous(haystack: str) -> None:
    assert match_resolution(haystack, "x ", "Q", " y") == "ambiguous"


# M1-03 -------------------------------------------------------------------------------


@pytest.mark.parametrize("haystack", ["nothing here", ""])
def test_m1_03_zero_occurrences_is_unmatched(haystack: str) -> None:
    assert match_resolution(haystack, "", "QUOTE", "") == "unmatched"


# M1-04 -------------------------------------------------------------------------------


def test_m1_04_overlapping_occurrences_count() -> None:
    assert match_resolution("aaa", "", "aa", "") == "ambiguous"


# M1-05 -------------------------------------------------------------------------------


def test_m1_05_strict_unique_quote_with_non_adjacent_context_is_unmatched() -> None:
    haystack = "alpha CHANGED beta QUOTE-ONE tail"
    assert haystack.count("QUOTE-ONE") == 1
    assert match_resolution(haystack, "alpha ", "QUOTE-ONE", " beta") == "unmatched"


# M1-06 -------------------------------------------------------------------------------


@pytest.mark.parametrize("quote", ["", " ", "\n\t", "　"])
def test_m1_06_empty_or_whitespace_quote_is_unmatched_even_when_context_matches(quote: str) -> None:
    assert match_resolution("alpha beta", "alpha", quote, "beta") == "unmatched"


# M1-07 -------------------------------------------------------------------------------


def test_m1_07_empty_context_means_the_needle_is_the_quote() -> None:
    assert match_resolution("one Q two", "", "Q", "") == "resolved"
    assert match_resolution("one Q two Q", "", "Q", "") == "ambiguous"


# M1-08 -------------------------------------------------------------------------------

# (haystack, quote, separator characters that must be str.isspace, expected)
_WS_TABLE: List[Tuple[str, str, str, str]] = [
    ("word 1 end", "word1", " ", "resolved"),
    ("word1 end", "word 1", " ", "resolved"),
    ("word 1", "word 1", "  ", "resolved"),
    ("第一　章", "第一章", "　", "resolved"),
    ("a\nb", "a b", "\n ", "resolved"),
    ("a\tb", "ab", "\t", "resolved"),
    ("a\r\nb", "ab", "\r\n", "resolved"),
    ("a b", "a b", "  ", "resolved"),
    ("a b", "ab", " ", "resolved"),
    ("a\x0bb", "a b", "\x0b ", "resolved"),
    ("a b", "ab", " ", "resolved"),
    ("word​1", "word1", "", "unmatched"),
]


@pytest.mark.parametrize(("haystack", "quote", "seps", "expected"), _WS_TABLE, ids=lambda v: ascii(v))
def test_m1_08_whitespace_equivalence_table(haystack: str, quote: str, seps: str, expected: str) -> None:
    for c in seps:
        assert c.isspace(), ascii(c)
    assert match_resolution(haystack, "", quote, "") == expected


def test_m1_08_zero_width_space_is_not_whitespace() -> None:
    assert not "​".isspace()


# M1-09 -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("haystack", "prefix", "quote", "suffix"),
    [("thecat sat", "the ", "cat", ""), ("a b c", "a", "b", "c")],
)
def test_m1_09_needle_is_joined_before_stripping(haystack: str, prefix: str, quote: str, suffix: str) -> None:
    assert match_resolution(haystack, prefix, quote, suffix) == "resolved"


# M1-10 -------------------------------------------------------------------------------

_SMALL = "ab \n"


@settings(max_examples=150, deadline=None)
@given(
    h=st.text(_SMALL, max_size=12),
    p=st.text(_SMALL, max_size=3),
    q=st.text(_SMALL, max_size=3),
    s=st.text(_SMALL, max_size=3),
)
def test_m1_10_oracle_property_over_a_small_alphabet(h: str, p: str, q: str, s: str) -> None:
    result = match_resolution(h, p, q, s)
    assert result == _oracle(h, p, q, s)
    assert result != "accepted"


# M1-11 -------------------------------------------------------------------------------


def test_m1_11_all_ws_is_the_complete_isspace_set() -> None:
    for c in ("\x0b", "\x1c", "\x85", " ", " ", "　"):
        assert c in ALL_WS, ascii(c)


@st.composite
def _with_ws(draw: st.DrawFn, base: str) -> str:
    out = base
    for _ in range(draw(st.integers(0, 3))):
        idx = draw(st.integers(0, len(out)))
        ws = draw(st.text(st.sampled_from(ALL_WS), min_size=1, max_size=3))
        out = out[:idx] + ws + out[idx:]
    return out


@settings(max_examples=100, deadline=None)
@given(data=st.data(), base=st.tuples(*[st.text("ab", max_size=6) for _ in range(4)]))
def test_m1_11_whitespace_insertion_never_changes_the_result(
    data: st.DataObject, base: Tuple[str, str, str, str]
) -> None:
    h, p, q, s = base
    h2, p2, q2, s2 = (data.draw(_with_ws(x)) for x in base)
    assert match_resolution(h, p, q, s) == match_resolution(h2, p2, q2, s2)


# M1-12 -------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    left=st.text("abc ", max_size=4),
    right=st.text("abc ", max_size=4),
    p=st.text("abc ", max_size=2),
    q=st.text("abc ", min_size=1, max_size=3),
    s=st.text("abc ", max_size=2),
)
def test_m1_12_duplicating_a_resolved_haystack_gives_ambiguous(
    left: str, right: str, p: str, q: str, s: str
) -> None:
    h = left + p + q + s + right
    assume(match_resolution(h, p, q, s) == "resolved")
    assert match_resolution(h + h, p, q, s) == "ambiguous"
    assert match_resolution(h + " " + h, p, q, s) == "ambiguous"


# M1-13 -------------------------------------------------------------------------------

_FIXED: List[Tuple[str, str, str, str]] = [
    ("alpha QUOTE-ONE beta.", "alpha ", "QUOTE-ONE", " beta"),
    ("x Q y. x Q y.", "x ", "Q", " y"),
    ("nothing here", "", "QUOTE", ""),
    ("aaa", "", "aa", ""),
    ("alpha CHANGED beta QUOTE-ONE tail", "alpha ", "QUOTE-ONE", " beta"),
    ("alpha beta", "alpha", " ", "beta"),
    ("one Q two", "", "Q", ""),
    ("word 1", "", "word 1", ""),
    ("word​1", "", "word1", ""),
    ("thecat sat", "the ", "cat", ""),
]


def test_m1_13_purity_inputs_unchanged_and_repeat_calls_equal() -> None:
    snapshot = [tuple(t) for t in _FIXED]
    first: List[str] = []
    second: List[str] = []
    for a, b in zip(_FIXED[0::2], _FIXED[1::2]):
        first.append(match_resolution(*a))
        first.append(match_resolution(*b))
        second.append(match_resolution(*a))
        second.append(match_resolution(*b))
    assert first == second
    assert first == [_oracle(*t) for pair in zip(_FIXED[0::2], _FIXED[1::2]) for t in pair]
    assert [tuple(t) for t in _FIXED] == snapshot
