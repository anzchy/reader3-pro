"""REG-1 part 3 (013 WI-9, C9.27-C9.28): `notes_service` save/load round-trip.

Existing coverage this does not duplicate (R-2 check): the stacked-annotation
round-trip in `test_fixture_annotation_corpus.py` is example-based and corpus-only;
`test_annotation_context_truncation.py` checks truncation at construction;
`test_notes_no_annotation_loss.py` covers failure modes. None of them runs a
generated round-trip over all 13 fields, checks the byte fixed point, or pins
`position=0`.

Hypothesis runs inside `tempfile.TemporaryDirectory` rather than `tmp_path`: a
function-scoped fixture is shared across examples and trips Hypothesis' health check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

import annotation_strategies as ast_
from hypothesis import example, given, settings

from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import annotations_version, load_annotations, save_annotations

BOOK_FOLDER = "b_data"

_CJK_QUOTE = "山重水复疑无路"
_CJK_PREFIX_80 = ("柳暗花明又一村" * 12)[:80]

EXAMPLES: List[List[Annotation]] = [
    [Annotation(book_id="b_data", quote="zero", position=0, created_at="")],
    [
        Annotation(
            book_id="书_1",
            quote=_CJK_QUOTE,
            prefix=_CJK_PREFIX_80,
            suffix=_CJK_PREFIX_80,
            created_at="2026-09-24T00:00:00+00:00",
        )
    ],
    [Annotation(book_id="b_data", quote="uncoloured", type="wavy", color=None)],
    [],
]


def _save_and_load(root: Path, anns: List[Annotation]) -> List[Annotation]:
    (root / BOOK_FOLDER).mkdir(exist_ok=True)
    save_annotations(str(root), BOOK_FOLDER, anns)
    return load_annotations(str(root), BOOK_FOLDER)


@settings(max_examples=150, deadline=None)
@given(ast_.annotation_lists)
@example(EXAMPLES[0])
@example(EXAMPLES[1])
@example(EXAMPLES[2])
@example(EXAMPLES[3])
def test_c9_27_save_then_load_preserves_every_annotation_in_order(anns: List[Annotation]) -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        loaded = _save_and_load(root, anns)
        assert (root / BOOK_FOLDER / "notes.json").is_file()
        assert [a.to_dict() for a in loaded] == [a.to_dict() for a in anns]


@settings(max_examples=150, deadline=None)
@given(ast_.annotation_lists)
@example(EXAMPLES[0])
@example(EXAMPLES[1])
@example(EXAMPLES[3])
def test_c9_28_save_of_load_is_a_byte_fixed_point(anns: List[Annotation]) -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        notes = root / BOOK_FOLDER / "notes.json"
        loaded = _save_and_load(root, anns)
        b1 = notes.read_bytes()
        save_annotations(str(root), BOOK_FOLDER, loaded)
        b2 = notes.read_bytes()
        assert b1 == b2
        assert annotations_version(load_annotations(str(root), BOOK_FOLDER)) == annotations_version(anns)
