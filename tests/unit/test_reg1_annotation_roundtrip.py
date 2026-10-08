"""REG-1 part 4 (013 WI-9, C9.29-C9.30): `Annotation` serialisation round-trip.

Law: `Annotation.from_dict(a.to_dict()) == a`, and `to_dict` covers every model field --
the 13 original ones plus the 4 additive keys of 012 WI-2b.1 (ADR-0019; ADR-0011 allows
additive keys). Their own round-trip and D-5 coercion are in test_annotation_resolution_fields.py.
"""

from __future__ import annotations

import dataclasses

import annotation_corpus as ac
import annotation_strategies as ast_
import pytest
from hypothesis import example, given, settings

from reader3_app.models.annotations import Annotation

THIRTEEN_FIELDS = frozenset(
    {
        "id", "book_id", "chapter_index", "type", "color", "quote", "prefix", "suffix",
        "position", "cfi", "note_text", "created_at", "orphaned",
    }
)
#: 012 WI-2b.1 additive fields (ADR-0019).
WI2B_FIELDS = frozenset({"resolution", "bound_fingerprint", "evaluated_fingerprint", "chapter_href"})
MODEL_FIELDS = THIRTEEN_FIELDS | WI2B_FIELDS


def test_the_model_has_exactly_the_thirteen_fields() -> None:
    assert {f.name for f in dataclasses.fields(Annotation)} == MODEL_FIELDS


@settings(max_examples=300, deadline=None)
@given(ast_.annotations)
@example(Annotation(book_id="b", quote="q", position=0, created_at=""))
@example(Annotation(book_id="b", quote="q", color=None, type="note", note_text=""))
def test_c9_29_from_dict_of_to_dict_is_identity_over_generated(a: Annotation) -> None:
    d = a.to_dict()
    assert set(d) == MODEL_FIELDS
    assert Annotation.from_dict(d) == a


@pytest.mark.parametrize(
    "raw",
    [ann for case in ac.ALL_CASES for ann in case.annotations],
    ids=lambda r: str(r["id"]),
)
def test_c9_29_from_dict_of_to_dict_is_identity_over_the_corpus(raw: dict) -> None:
    a = Annotation(**raw)
    d = a.to_dict()
    assert set(d) == MODEL_FIELDS
    assert Annotation.from_dict(d) == a


def test_c9_30_truncation_and_clamping_are_stable_across_the_round_trip() -> None:
    a = Annotation(book_id="b", quote="q", prefix="p" * 50 + "P", suffix="S" + "s" * 50, position=-1)
    assert a.prefix == "p" * 49 + "P"
    assert a.suffix == "S" + "s" * 49
    assert len(a.prefix) == 50 and len(a.suffix) == 50
    assert a.position == 0
    back = Annotation.from_dict(a.to_dict())
    assert (back.prefix, back.suffix, back.position) == (a.prefix, a.suffix, 0)
    assert back == a
