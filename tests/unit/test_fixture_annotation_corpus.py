"""The annotation-anchoring corpus proves each case is actually hard.

Anchoring is quote + 50 characters of context, matched against chapter text.
Every case here is a way that match can go wrong, and each one is only useful
while it stays wrong in the specific way it claims: a "crosses an inline
boundary" quote that quietly became contained in one text node, or a "repeated"
quote that stopped repeating, would still be exercised by every downstream test
and would still pass.

The offsets in ``annotation_corpus`` are also pinned against the real
``extract_plain_text``, because they were computed from it. If whitespace
collapsing changes, this file is where that is discovered.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from bs4 import BeautifulSoup, NavigableString

import annotation_corpus as ac
from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import (
    add_annotation,
    delete_annotation,
    load_annotations,
    save_annotations,
)
from reader3_app.reader3 import clean_html_content, extract_plain_text, process_epub


def text_of(html: str) -> str:
    return extract_plain_text(clean_html_content(BeautifulSoup(html, "html.parser")))


def text_nodes(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [str(n) for n in soup.descendants if isinstance(n, NavigableString)]


@pytest.mark.parametrize("case", ac.ALL_CASES, ids=lambda c: c.key)
def test_declared_text_matches_what_reader3_actually_extracts(case: ac.AnchorCase):
    """L2 - the offsets in this corpus are only meaningful while this holds."""
    assert text_of(case.html) == case.text


@pytest.mark.parametrize("case", ac.ALL_CASES, ids=lambda c: c.key)
def test_every_annotation_in_the_corpus_is_constructible(case: ac.AnchorCase):
    """L2 - a payload the model rejects would make its case unreachable."""
    for payload in case.annotations:
        ann = Annotation.from_dict(dict(payload))
        assert ann.book_id == ac.BOOK_ID
        assert ann.quote == payload["quote"]


def test_split_node_quote_exists_in_no_single_dom_text_node():
    """L2 - the defining property: assembling it needs more than one node."""
    case = ac.SPLIT_NODES
    quote = str(case.annotations[0]["quote"])

    assert quote in case.text
    assert not any(quote in node for node in text_nodes(case.html))
    assert "<em>" in case.html


def test_cross_paragraph_quote_spans_a_block_boundary():
    """L2 - present in the chapter text, absent from either paragraph alone."""
    case = ac.CROSS_PARAGRAPH
    quote = str(case.annotations[0]["quote"])
    soup = BeautifulSoup(case.html, "html.parser")
    paragraphs = [p.get_text(separator=" ") for p in soup.find_all("p")]

    assert len(paragraphs) == 2
    assert quote in case.text
    assert not any(quote in p for p in paragraphs)


def test_repeated_quote_is_ambiguous_alone_and_unique_with_its_prefix():
    """L2 - if context did not disambiguate, the case would not be a case."""
    case = ac.REPEATED
    payload = case.annotations[0]
    quote = str(payload["quote"])
    prefix = str(payload["prefix"])

    assert ac.occurrences(case.text, quote) == ac.REPEATED_OCCURRENCES
    assert ac.occurrences(case.text, prefix + quote) == 1

    # And it selects the middle one, not the first or the last.
    assert case.text.index(prefix + quote) + len(prefix) == ac.span_of(
        case, quote, occurrence=1
    )[0]


def test_overlapping_annotations_really_overlap():
    """L2 - two spans that merely abutted would exercise nothing."""
    case = ac.OVERLAPPING
    left, right = case.annotations
    ls, le = ac.span_of(case, str(left["quote"]))
    rs, re_ = ac.span_of(case, str(right["quote"]))

    assert ls < rs < le < re_
    overlap = case.text[rs:le]
    assert overlap == "brown fox"


def test_stacked_annotations_share_one_span_across_four_types():
    """L3 - four types, one range, and all four survive a save/load round trip."""
    case = ac.STACKED
    spans = {ac.span_of(case, str(a["quote"])) for a in case.annotations}
    types = [a["type"] for a in case.annotations]

    assert len(spans) == 1
    assert sorted(types) == ["marker", "note", "underline", "wavy"]


def test_stacked_annotations_round_trip_through_notes_service(books_dir: Path):
    """L3 - persistence keeps all four, distinguishable, and deletes one at a time."""
    case = ac.STACKED
    saved = [Annotation.from_dict(dict(p)) for p in case.annotations]
    save_annotations(str(books_dir), ac.BOOK_ID, saved)

    loaded = load_annotations(str(books_dir), ac.BOOK_ID)
    assert [a.id for a in loaded] == [a.id for a in saved]
    assert {a.type for a in loaded} == {"marker", "underline", "wavy", "note"}
    assert {a.quote for a in loaded} == {ac.STACKED_QUOTE}
    assert [a.color for a in loaded] == ["yellow", "green", "pink", "blue"]

    assert delete_annotation(str(books_dir), ac.BOOK_ID, "ann-stacked-wavy") is True
    remaining = load_annotations(str(books_dir), ac.BOOK_ID)
    assert [a.type for a in remaining] == ["marker", "underline", "note"]


def test_long_context_is_truncated_towards_the_quote(books_dir: Path):
    """L2 - which 50 characters survive is the property, not that 50 survive.

    The half adjacent to the quote is the half that disambiguates, so prefix
    keeps its tail and suffix keeps its head. Truncating the other way would
    leave two fields that look populated and identify nothing.
    """
    payload = dict(ac.LONG_CONTEXT.annotations[0])
    assert len(str(payload["prefix"])) == 80
    assert len(str(payload["suffix"])) == 80

    stored = add_annotation(str(books_dir), Annotation.from_dict(payload))

    assert stored.prefix == ac.LONG_PREFIX[-50:]
    assert stored.suffix == ac.LONG_SUFFIX[:50]
    assert ac.LONG_CONTEXT.text.index(stored.prefix + "MIDDLE") == 30

    reloaded = load_annotations(str(books_dir), ac.BOOK_ID)
    assert [a.prefix for a in reloaded] == [ac.LONG_PREFIX[-50:]]


def test_stale_text_case_makes_every_stored_quote_unfindable():
    """L2 - the "orphan" input: same annotations, re-processed chapter."""
    before, after = ac.STALE_TEXT_BEFORE, ac.STALE_TEXT_AFTER

    assert before.annotations == after.annotations
    quote = str(before.annotations[0]["quote"])

    assert ac.occurrences(before.text, quote) == ac.REPEATED_OCCURRENCES
    assert ac.occurrences(after.text, quote) == 0
    # The surrounding context is intact, so this is a changed chapter, not a
    # different one -- exactly the case where re-anchoring should be possible
    # and a naive exact-match orphans the note instead.
    assert str(before.annotations[0]["prefix"]) in after.text


def test_stale_spine_case_moves_a_stored_chapter_index_onto_different_text():
    """L2 - the silent failure: the index still resolves, to the wrong chapter."""
    index = int(ac.STALE_SPINE_ANNOTATION["chapter_index"])
    quote = str(ac.STALE_SPINE_ANNOTATION["quote"])

    assert ac.SPINE_ORDER_BEFORE[index] == quote
    assert ac.SPINE_ORDER_AFTER[index] != quote
    assert quote in ac.SPINE_ORDER_AFTER  # still in the book, just not there
    assert ac.SPINE_ORDER_AFTER.index(quote) == 2


def test_the_corpus_survives_a_real_epub_round_trip(tmp_path: Path, books_dir: Path):
    """L3 - the offsets hold after processing, not only in the fixture module.

    Anchoring runs against ``ChapterContent.text`` as published in ``book.pkl``.
    Asserting the corpus only against ``extract_plain_text`` would skip
    everything ``process_epub`` does in between.
    """
    path = ac.build_chapter_epub(tmp_path / "anchors.epub")
    book = process_epub(str(path), str(books_dir / "anchors_data"))

    assert [c.text for c in book.spine] == [c.text for c in ac.ALL_CASES]

    repeated_index = ac.ALL_CASES.index(ac.REPEATED)
    chapter = book.spine[repeated_index]
    assert chapter.text.count(ac.REPEATED_QUOTE) == ac.REPEATED_OCCURRENCES
    start, end = ac.span_of(ac.REPEATED, ac.REPEATED_QUOTE, occurrence=1)
    assert chapter.text[start:end] == ac.REPEATED_QUOTE
