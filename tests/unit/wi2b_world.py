"""Shared fixture module for 012 WI-2b (matrix: .claude/tdd-guardian/tests-20261009-wi2b.md).

Not a test file and not frozen. It is built up one work item at a time:

- WI-2b.1 (this revision): the record builders, the raw ``notes.json`` seeder and the
  readers the A1 / M1 cases need -- ``rec``, ``legacy_rec``, ``seed_notes``, ``disk``,
  ``version_on_disk``, the fingerprints and the Q13 standard texts.
- Later WIs add, per the matrix's "Shared fixture module" section: ``publish_gen``,
  ``write_book_pkl``, ``gen_book``, ``pkl_book``, ``flip_chapter_byte``, ``post_counts``,
  ``FakeClock`` and ``run_in_worker``, each with the self-check the matrix names.

``seed_notes`` writes raw JSON and never goes through ``save_annotations``, so a test
can put on disk exactly the bytes it means to (the ``_write_raw`` pattern in
``test_notes_fingerprint_key.py``).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from book_format_helpers import FINGERPRINT

from reader3_app import notes_service

#: Generation A's fingerprint: the one ``book_format_helpers.make_inputs`` publishes with.
FP_A: str = FINGERPRINT
#: A second, different fingerprint (generation B).
FP_B: str = hashlib.sha256(b"wi2b generation B").hexdigest()

#: The 13 keys ``Annotation.to_dict`` emitted before WI-2b.1.
OLD_13: frozenset = frozenset(
    {
        "id",
        "book_id",
        "chapter_index",
        "type",
        "color",
        "quote",
        "prefix",
        "suffix",
        "position",
        "cfi",
        "note_text",
        "created_at",
        "orphaned",
    }
)
#: The 4 additive keys WI-2b.1 adds.
NEW_4: frozenset = frozenset({"resolution", "bound_fingerprint", "evaluated_fingerprint", "chapter_href"})

RESOLUTIONS: Tuple[str, ...] = ("resolved", "ambiguous", "unmatched", "accepted")

DEFAULT_BOOK_ID = "wi2b_data"
CREATED_AT = "2026-10-09T00:00:00Z"


class _Absent:
    def __repr__(self) -> str:
        return "ABSENT"


#: ``seed_notes(..., fp=ABSENT)``: write no top-level fingerprint key at all.
ABSENT = _Absent()

# Standard texts (matrix "Standard texts").
Q13_A: List[str] = [
    "alpha QUOTE-ONE beta. gamma QUOTE-TWO delta.",
    "chapter one only text",
    "chapter two only text",
]
Q13_B: List[str] = [
    "alpha QUOTE-ONE beta. gamma QUOTE-TWO delta. gamma QUOTE-TWO delta.",
    "chapter one only text",
    "chapter two only text",
]


def legacy_rec(
    nid: str,
    ci: int,
    quote: str,
    prefix: str = "",
    suffix: str = "",
    *,
    orphaned: bool = False,
    book_id: str = DEFAULT_BOOK_ID,
) -> Dict[str, Any]:
    """A raw record in the pre-WI-2b.1 form: exactly the 13 old keys."""
    return {
        "id": nid,
        "book_id": book_id,
        "chapter_index": ci,
        "type": "marker",
        "color": "yellow",
        "quote": quote,
        "prefix": prefix,
        "suffix": suffix,
        "position": None,
        "cfi": None,
        "note_text": None,
        "created_at": CREATED_AT,
        "orphaned": orphaned,
    }


def rec(
    nid: str,
    ci: int,
    quote: str,
    prefix: str = "",
    suffix: str = "",
    *,
    resolution: Any = "resolved",
    bound: Any = None,
    evaluated: Any = None,
    orphaned: bool = False,
    chapter_href: Any = "",
    book_id: str = DEFAULT_BOOK_ID,
) -> Dict[str, Any]:
    """A raw 17-key record: the 13 old keys plus the 4 WI-2b.1 keys."""
    out = legacy_rec(nid, ci, quote, prefix, suffix, orphaned=orphaned, book_id=book_id)
    out["resolution"] = resolution
    out["bound_fingerprint"] = bound
    out["evaluated_fingerprint"] = evaluated
    out["chapter_href"] = chapter_href
    return out


def seed_notes(book_dir: Path, records: List[Dict[str, Any]], fp: Any = ABSENT) -> Path:
    """Write ``notes.json`` as raw JSON, bypassing ``save_annotations``."""
    book_dir = Path(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"schema_version": notes_service.NOTES_SCHEMA_VERSION, "annotations": records}
    if fp is not ABSENT:
        payload[notes_service.NOTES_FINGERPRINT_KEY] = fp
    path = book_dir / notes_service.NOTES_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def disk(book_dir: Path) -> Tuple[bytes, int, Optional[Dict[str, Any]]]:
    """``(bytes, st_mtime_ns, parsed)`` of ``notes.json``."""
    path = Path(book_dir) / notes_service.NOTES_FILENAME
    raw = path.read_bytes()
    return raw, os.stat(path).st_mtime_ns, json.loads(raw.decode("utf-8"))


def version_on_disk(books_dir: str, folder: str) -> str:
    return notes_service.annotations_version(notes_service.load_annotations(str(books_dir), folder))
