"""012 WI-2b.1: the four additive ``Annotation`` fields (matrix cases A1-01 … A1-07).

``resolution`` / ``bound_fingerprint`` / ``evaluated_fingerprint`` / ``chapter_href``,
their constant defaults, and the D-5 coercion ``from_dict`` applies to bad on-disk values.
The ETag (``annotations_version``) hashes ``to_dict()``, so every default must be a
constant: a synthesized one would move the ETag on every load.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from wi2b_world import (
    FP_A,
    FP_B,
    NEW_4,
    OLD_13,
    RESOLUTIONS,
    disk,
    legacy_rec,
    rec,
    seed_notes,
)

from reader3_app import notes_service
from reader3_app.models.annotations import Annotation

_FP_VALUES = st.none() | st.text(max_size=70) | st.from_regex(r"[0-9a-f]{64}", fullmatch=True)


@st.composite
def _annotations(draw: Any) -> Annotation:
    return Annotation(
        book_id=draw(st.from_regex(r"[a-z]{1,8}_data", fullmatch=True)),
        chapter_index=draw(st.integers(0, 50)),
        quote=draw(st.text(min_size=1).filter(str.strip)),
        prefix=draw(st.text(max_size=80)),
        suffix=draw(st.text(max_size=80)),
        resolution=draw(st.sampled_from(list(RESOLUTIONS))),
        bound_fingerprint=draw(_FP_VALUES),
        evaluated_fingerprint=draw(_FP_VALUES),
        chapter_href=draw(st.text(max_size=40)),
        orphaned=draw(st.booleans()),
    )


# A1-01 -------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(a=_annotations())
def test_a1_01_round_trip_law_over_generated_annotations(a: Annotation) -> None:
    d = a.to_dict()
    assert Annotation.from_dict(d).to_dict() == d
    assert set(d) == OLD_13 | NEW_4


# A1-02 -------------------------------------------------------------------------------


def test_a1_02_legacy_13_key_record_loads_with_constant_defaults() -> None:
    raw = legacy_rec("n1", 0, "QUOTE-ONE")
    assert set(raw) == OLD_13
    a = Annotation.from_dict(raw)
    assert a.resolution == "resolved"
    assert a.bound_fingerprint is None
    assert a.evaluated_fingerprint is None
    assert a.chapter_href == ""
    out = a.to_dict()
    assert {k: out[k] for k in OLD_13} == raw


# A1-03 -------------------------------------------------------------------------------


def test_a1_03_constructor_defaults_without_the_new_arguments() -> None:
    a = Annotation(book_id="b_data", chapter_index=0, type="marker", color="yellow", quote="q")
    assert (a.resolution, a.bound_fingerprint, a.evaluated_fingerprint, a.chapter_href) == (
        "resolved",
        None,
        None,
        "",
    )


# A1-04 -------------------------------------------------------------------------------


def test_a1_04_same_legacy_file_same_version_and_stable_after_normalization(tmp_path: Any) -> None:
    books = tmp_path / "books"
    folder = "wi2b_data"
    book = books / folder
    seed_notes(book, [legacy_rec("n1", 0, "QUOTE-ONE"), legacy_rec("n2", 1, "other")])

    load1 = notes_service.load_annotations(str(books), folder)
    load2 = notes_service.load_annotations(str(books), folder)
    assert notes_service.annotations_version(load1) == notes_service.annotations_version(load2)

    notes_service.save_annotations(str(books), folder, load1)
    load3 = notes_service.load_annotations(str(books), folder)
    assert notes_service.annotations_version(load3) == notes_service.annotations_version(load1)

    _, _, parsed = disk(book)
    assert parsed is not None
    records = parsed["annotations"]
    assert len(records) == 2
    for r in records:
        assert set(r) == OLD_13 | NEW_4
        assert r["resolution"] == "resolved"
        assert r["bound_fingerprint"] is None
        assert r["evaluated_fingerprint"] is None
        assert r["chapter_href"] == ""


# A1-05 -------------------------------------------------------------------------------

_COERCION_ROWS = [
    ("resolution", "bogus", "unmatched"),
    ("resolution", 5, "unmatched"),
    ("resolution", "", "unmatched"),
    ("resolution", "Resolved", "unmatched"),
    ("resolution", [], "unmatched"),
    ("resolution", None, "resolved"),
    *[
        (key, value, expected)
        for key in ("bound_fingerprint", "evaluated_fingerprint")
        for value, expected in ((123, None), ({}, None), ([], None), (True, None), (1.5, None), ("x", "x"))
    ],
    ("chapter_href", 5, ""),
    ("chapter_href", None, ""),
]


@pytest.mark.parametrize(("key", "value", "expected"), _COERCION_ROWS, ids=lambda v: repr(v))
def test_a1_05_d5_coercion_row(key: str, value: Any, expected: Any) -> None:
    raw = legacy_rec("n1", 0, "QUOTE-ONE")
    raw[key] = value
    a = Annotation.from_dict(raw)
    assert getattr(a, key) == expected
    assert type(getattr(a, key)) is type(expected)


def test_a1_05_load_keeps_every_coerced_record(tmp_path: Any) -> None:
    books = tmp_path / "books"
    folder = "wi2b_data"
    records = []
    for i, (key, value, _expected) in enumerate(_COERCION_ROWS):
        raw = legacy_rec(f"n{i}", 0, "QUOTE-ONE")
        raw[key] = value
        records.append(raw)
    seed_notes(books / folder, records)

    loaded = notes_service.load_annotations(str(books), folder)

    assert len(loaded) == len(records)
    for a, (key, _value, expected) in zip(loaded, _COERCION_ROWS):
        assert getattr(a, key) == expected


# A1-06 -------------------------------------------------------------------------------


@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_a1_06_each_valid_resolution_survives_load(resolution: str) -> None:
    d = rec("n1", 0, "QUOTE-ONE", resolution=resolution, bound=FP_A, evaluated=FP_B, chapter_href="Text/c0.xhtml")
    a = Annotation.from_dict(d)
    assert a.resolution == resolution
    assert a.bound_fingerprint == FP_A
    assert a.evaluated_fingerprint == FP_B
    assert a.chapter_href == "Text/c0.xhtml"


# A1-07 -------------------------------------------------------------------------------

_GARBAGE = (
    st.none()
    | st.integers()
    | st.text(max_size=10)
    | st.lists(st.integers(), max_size=2)
    | st.dictionaries(st.text(max_size=2), st.integers(), max_size=1)
    | st.booleans()
)


@settings(max_examples=40, deadline=None)
@given(res=_GARBAGE, bound=_GARBAGE, evaluated=_GARBAGE, href=_GARBAGE)
def test_a1_07_coerced_load_is_a_fixpoint(res: Any, bound: Any, evaluated: Any, href: Any) -> None:
    d = rec("n1", 0, "QUOTE-ONE", resolution=res, bound=bound, evaluated=evaluated, chapter_href=href)
    a1 = Annotation.from_dict(d)
    assert Annotation.from_dict(a1.to_dict()).to_dict() == a1.to_dict()
    assert a1.resolution in set(RESOLUTIONS)
    assert a1.bound_fingerprint is None or isinstance(a1.bound_fingerprint, str)
    assert a1.evaluated_fingerprint is None or isinstance(a1.evaluated_fingerprint, str)
    assert isinstance(a1.chapter_href, str)
