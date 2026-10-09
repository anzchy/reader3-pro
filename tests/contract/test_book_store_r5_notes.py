"""012 WI-4a.3 R5-06 [contract]: the notes skip rule (ADR-0019) compares against the R-5 stamped fingerprint.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4a.md`` section ``## WI-4a.3``, case R5-06. It mirrors WI-2b's
V2-12 (``tests/unit/test_notes_fingerprint_advance.py``): notes stamped with the book's fingerprint, one note
anchored on text that is present and one on text that is absent, then ``GET /api/notes/{book}``.

Row ``gen``: the manifest says ``FP_A``, the generation's ``book.pkl`` was pickled with ``"STALE"`` and the flat
``book.pkl`` (kept so the book stays listed) with ``None``. Only the R-5 stamp makes the loaded Book's fingerprint
``FP_A``, so only the stamp lets the notes (stamped ``FP_A``) agree and orphan marking run.
Row ``flat``: a pkl-only book and ``None`` notes; the stamp makes the Book ``None`` whatever was pickled.
"""

from __future__ import annotations

import json
import pickle
from typing import Any, Dict, Optional

import pytest
from wi2b_world import FP_A, rec, seed_notes
from wi4a_world import book_obj, flat_pkl, gen_book_pkl

from conftest import World
from reader3_app import book_format, notes_service

TEXTS = ["alpha beta", "gamma"]


def _persisted(world: World, folder: str) -> Dict[str, Any]:
    data = json.loads((world.books_dir / folder / notes_service.NOTES_FILENAME).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return {a["id"]: a for a in data["annotations"]}


@pytest.mark.parametrize(
    "row, flat_fp",
    [("gen", None), ("flat", None), ("flat", "STALE")],
    ids=["gen", "flat-pickled-none", "flat-pickled-stale"],
)
def test_r5_06_notes_get_marks_orphans_on_the_stamped_fingerprint(
    world: World, row: str, flat_fp: Optional[str]
) -> None:
    folder = f"r5{row[0]}_data"
    books = world.books_dir
    notes_fp: Optional[str]
    if row == "gen":
        gen_book_pkl(books, folder, texts=TEXTS, fp=FP_A, pkl=pickle.dumps(book_obj(folder, TEXTS, "STALE")))
        assert book_format.classify(books / folder, full=False) == "valid"
        notes_fp = FP_A
    else:
        notes_fp = None
    flat_pkl(books, folder, book_obj(folder, TEXTS, flat_fp))
    seed_notes(
        books / folder,
        [
            rec("n1", 0, "alpha", book_id=folder, bound=notes_fp, evaluated=notes_fp),
            rec("n2", 0, "zzz-absent", book_id=folder, bound=notes_fp, evaluated=notes_fp),
        ],
        fp=notes_fp,
    )

    got = world.client.get(f"/api/notes/{folder}")

    assert got.status_code == 200, got.text
    listed = [a["id"] for ch in got.json()["annotations_by_chapter"] for a in ch["annotations"]]
    assert listed == ["n1"], listed
    persisted = _persisted(world, folder)
    assert persisted["n2"]["orphaned"] is True
    assert persisted["n1"]["orphaned"] is False
