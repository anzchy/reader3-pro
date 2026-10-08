"""Shared fixture module for 012 WI-2b (matrix: .claude/tdd-guardian/tests-20261009-wi2b.md).

Not a test file and not frozen. It is built up one work item at a time:

- WI-2b.1: the record builders, the raw ``notes.json`` seeder and the readers the
  A1 / M1 cases need -- ``rec``, ``legacy_rec``, ``seed_notes``, ``disk``,
  ``version_on_disk``, the fingerprints and the Q13 standard texts.
- WI-2b.2: the book builders ``publish_gen``, ``write_book_pkl``, ``gen_book`` and
  ``pkl_book`` (self-checks in ``test_notes_fingerprint_advance.py``).
- WI-2b.4: ``gen_inputs`` (``publish_gen``'s inputs, for a publish under an EX lock the test
  already holds), ``flip_chapter_byte``, ``post_counts``, ``FakeClock`` and ``run_in_worker``
  (self-checks in ``test_notes_rebind.py``).

``seed_notes`` writes raw JSON and never goes through ``save_annotations``, so a test
can put on disk exactly the bytes it means to (the ``_write_raw`` pattern in
``test_notes_fingerprint_key.py``).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pickle
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from book_format_helpers import FINGERPRINT, make_inputs

from reader3_app import book_format, book_lock, notes_service
from reader3_app.book_format import ChapterRecord
from reader3_app.reader3 import Book, BookMetadata, ChapterContent

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


# --------------------------------------------------------------------------- book builders (WI-2b.2)


def _chapter_href(i: int) -> str:
    return f"Text/c{i}.xhtml"


def gen_inputs(texts: List[str], fp: str, tag: str) -> book_format.PublishInputs:
    """The ``PublishInputs`` ``publish_gen`` publishes: one chapter per text, ``order`` = position."""
    return dataclasses.replace(
        make_inputs(tag, book_fingerprint=fp, images=False, pkl=False),
        chapters=tuple(
            ChapterRecord(id=f"c{i}", href=_chapter_href(i), title=f"T{i}", content=f"<p>{t}</p>", text=t, order=i)
            for i, t in enumerate(texts)
        ),
    )


def publish_gen(books_dir: Any, folder: str, texts: List[str], fp: str, tag: str) -> int:
    """Publish one real generation of ``texts`` under the EX book lock; return its number."""
    inputs = gen_inputs(texts, fp, tag)
    book_dir = Path(books_dir) / folder
    book_dir.mkdir(parents=True, exist_ok=True)
    with book_lock.acquire(str(books_dir), folder, mode=book_lock.EXCLUSIVE, holder="import"):
        return book_format.publish(book_dir, inputs)


def write_book_pkl(books_dir: Any, folder: str, texts: List[str], fp: Optional[str]) -> Path:
    """Pickle a real ``Book`` whose spine carries ``texts``; ``book.book_fingerprint = fp``."""
    book = Book(
        metadata=BookMetadata(title=folder, language="en"),
        spine=[
            ChapterContent(id=f"c{i}", href=_chapter_href(i), title=f"T{i}", content=f"<p>{t}</p>", text=t, order=i)
            for i, t in enumerate(texts)
        ],
        toc=[],
        images={},
        source_file=f"{folder}.epub",
        processed_at="2026-10-09T00:00:00+00:00",
    )
    # Set after construction so this works before WI-2b.3 adds the field to Book.
    setattr(book, "book_fingerprint", fp)
    path = Path(books_dir) / folder / "book.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(book))
    return path


def gen_book(books_dir: Any, folder: str, texts: List[str], fp: str, tag: str = "A") -> int:
    """A generation book: ``publish_gen`` then a matching ``book.pkl`` (same texts, same fp)."""
    g = publish_gen(books_dir, folder, texts, fp, tag)
    write_book_pkl(books_dir, folder, texts, fp)
    return g


def pkl_book(books_dir: Any, folder: str, texts: List[str]) -> Path:
    """A pkl-only book: no generation, so ``book_store.book_fingerprint`` is ``None``."""
    return write_book_pkl(books_dir, folder, texts, None)


# --------------------------------------------------------------------------- rebind helpers (WI-2b.4)


def flip_chapter_byte(book_dir: Any, index: int = 1) -> None:
    """Flip one byte inside chapter ``index``'s record of ``chapters.jsonl``, keeping the file size.

    ``validate_stat`` still passes (it checks sizes only); ``read_chapter`` of that record fails its sha256.
    """
    manifest = book_format.validate_stat(book_dir)
    entry = manifest.chapters[index]
    path = Path(book_dir) / book_format.GEN_DIR / str(manifest.generation) / book_format.CHAPTERS
    pos = entry.offset_bytes + entry.length_bytes // 2
    with open(path, "r+b") as fh:
        fh.seek(pos)
        byte = fh.read(1)
        fh.seek(pos)
        fh.write(bytes([byte[0] ^ 0x01]))


def post_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """The counts ruling as an oracle: post-rebind ``resolution`` of every non-orphaned record, zeros absent."""
    return dict(Counter(r["resolution"] for r in records if not r["orphaned"]))


class FakeClock:
    """``book_lock``'s two documented time seams, driven by fake time: ``sleep(dt)`` adds ``dt`` to ``now``."""

    START = 1000.0
    RUNAWAY_S = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = self.START
        self.sleeps = 0

    def monotonic(self) -> float:
        with self._lock:
            return self.now

    def sleep(self, dt: float) -> None:
        assert dt >= 0, dt
        with self._lock:
            self.now += dt
            self.sleeps += 1
            if self.now > self.START + self.RUNAWAY_S:
                raise AssertionError("fake clock runaway")

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakeClock":
        monkeypatch.setattr("reader3_app.book_lock._monotonic", self.monotonic)
        monkeypatch.setattr("reader3_app.book_lock._sleep", self.sleep)
        return self


WORKER_JOIN_S = 10.0


def run_in_worker(fn: Callable[[], Any]) -> Tuple[Any, Optional[BaseException]]:
    """Run ``fn`` on a fresh thread; return ``(result, exception)``. The thread must finish within 10 s."""
    out: Dict[str, Any] = {}

    def target() -> None:
        try:
            out["result"] = fn()
        except BaseException as exc:  # handed back to the caller, which asserts on it
            out["exc"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(WORKER_JOIN_S)
    assert not t.is_alive(), "worker did not finish within its join timeout"
    return out.get("result"), out.get("exc")
