"""Hypothesis strategies for `Annotation` (013 WI-9, REG-1 parts 3 and 4: C9.27-C9.30).

Every annotation is built by the real `Annotation(...)` constructor, so values the
constructor normalises (color None -> "yellow", prefix/suffix truncated to 50,
negative position clamped to 0) are generated on purpose and must round-trip in
their normalised form. Field domains follow the matrix, case C9.27.
"""

from __future__ import annotations

from datetime import timezone
from typing import get_args

from hypothesis import strategies as st

from reader3_app.models.annotations import Annotation, AnnotationType, MarkerColor

#: ASCII, CJK, full-width punctuation, emoji, and the characters JSON and HTML
#: escaping care about.
_ALPHABET = st.one_of(
    st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF),
    st.sampled_from(list("，。「」【】")),
    st.characters(min_codepoint=0x1F300, max_codepoint=0x1F5FF),
    st.sampled_from(["\n", '"', "\\", "<", "&"]),
)

_BOOK_ID_ALPHABET = st.one_of(
    st.sampled_from(list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")),
    st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF),
)

ids = st.one_of(st.uuids(version=4).map(str), st.text(_ALPHABET, min_size=1, max_size=40))
book_ids = st.text(_BOOK_ID_ALPHABET, min_size=1, max_size=40)
chapter_indices = st.integers(min_value=0, max_value=500)
types = st.sampled_from(get_args(AnnotationType))
colors = st.one_of(st.none(), st.sampled_from(get_args(MarkerColor)))
quotes = st.text(_ALPHABET, min_size=1, max_size=200)
contexts = st.text(_ALPHABET, min_size=0, max_size=80)
positions = st.one_of(st.none(), st.just(0), st.integers(min_value=-5, max_value=10**6))
cfis = st.one_of(
    st.none(),
    st.builds(
        lambda n, m: f"epubcfi(/6/{n}!/4/{m})",
        st.integers(min_value=0, max_value=10_000),
        st.integers(min_value=0, max_value=10_000),
    ),
)
note_texts = st.one_of(st.none(), st.text(_ALPHABET, min_size=0, max_size=300))
created_ats = st.one_of(
    st.datetimes(timezones=st.just(timezone.utc)).map(lambda d: d.isoformat()),
    st.just(""),
)

annotations = st.builds(
    Annotation,
    id=ids,
    book_id=book_ids,
    chapter_index=chapter_indices,
    type=types,
    color=colors,
    quote=quotes,
    prefix=contexts,
    suffix=contexts,
    position=positions,
    cfi=cfis,
    note_text=note_texts,
    created_at=created_ats,
    orphaned=st.booleans(),
)

annotation_lists = st.lists(annotations, min_size=0, max_size=20)
