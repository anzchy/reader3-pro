"""Helpers for seeding and inspecting a ``books/{name}_data/`` directory in tests."""

from __future__ import annotations

import glob as _glob
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

CONVERSATION_ID = "11111111-2222-3333-4444-555555555555"

#: Everything in a book directory that the user owns and that the staging/swap
#: feature exists to protect. Directory entries are included so a
#: deleted-and-recreated directory is caught too.
USER_PATHS: Tuple[str, ...] = (
    "notes.json",
    "ai_meta.json",
    "ai_conversations/",
    f"ai_conversations/{CONVERSATION_ID}.json",
    "chroma_db/",
    "chroma_db/chroma.sqlite3",
)


def seed_user_files(out: Path) -> None:
    """Write the four user-owned paths with fixed, recognisable content."""
    (out / "notes.json").write_text(
        json.dumps({"notes": [{"id": "note-1", "quote": "precious highlight"}]}),
        encoding="utf-8",
    )
    (out / "ai_meta.json").write_text(
        json.dumps({"book_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}, indent=2),
        encoding="utf-8",
    )
    conv = out / "ai_conversations"
    conv.mkdir(exist_ok=True)
    (conv / f"{CONVERSATION_ID}.json").write_text(
        json.dumps({"id": CONVERSATION_ID, "messages": [{"role": "user", "content": "hi"}]}),
        encoding="utf-8",
    )
    chroma = out / "chroma_db"
    chroma.mkdir(exist_ok=True)
    (chroma / "chroma.sqlite3").write_bytes(b"SQLite format 3\x00" + b"pretend-index" * 32)


def make_seeded_book_dir(books_dir: Path, source_epub: Path, name: str = "sample_data") -> Path:
    """Process ``source_epub`` into ``books_dir/name`` then seed the user files.

    The precondition is asserted here rather than in each test: ``user_subset``
    filters with ``if p in snap``, so a seeding helper that silently stopped
    writing would make every "the user's data survived" assertion downstream
    compare ``{} == {}`` and pass vacuously.
    """
    from epub_builder import snapshot_tree
    from reader3_app import reader3

    out = books_dir / name
    reader3.process_epub(str(source_epub), str(out))
    seed_user_files(out)

    seeded = snapshot_tree(out)
    assert set(user_subset(seeded)) == set(USER_PATHS), (
        f"fixture failed to seed the user-owned paths: "
        f"missing {sorted(set(USER_PATHS) - set(seeded))}"
    )
    assert "book.pkl" in seeded, "fixture did not produce a book.pkl to supersede"
    return out


def user_subset(snap: Dict[str, Tuple]) -> Dict[str, Tuple]:
    return {p: snap[p] for p in USER_PATHS if p in snap}


def staging_leftovers(out: Path | str) -> List[str]:
    # glob.escape for the same reason the implementation needs it: a book folder
    # is named after the EPUB file and may legally contain '*', '?' or '['.
    normalized = os.path.normpath(str(out))
    return sorted(_glob.glob(f"{_glob.escape(normalized)}.staging-*"))


# --- damaged book directories (group 4: "scale and failure") ---------------
#
# A book directory can be broken in ways no EPUB can express, because the
# damage happens after processing: a half-synced cloud folder, a killed
# reindex, a user deleting what looked like a redundant copy of their book.
# The loaders all key a book's existence on book.pkl, so each of these is a
# different answer to "the marker is there, now what?".


def break_book_pkl(out: Path | str) -> Path:
    """Overwrite ``book.pkl`` with bytes that are not a pickle at all."""
    path = Path(out) / "book.pkl"
    path.write_bytes(b"\x80\x05not-a-pickle-at-all")
    return path


def truncate_book_pkl(out: Path | str, *, keep: int = 32) -> Path:
    """Keep the first ``keep`` bytes of a real pickle: a valid opcode prefix, no STOP.

    Distinct from :func:`break_book_pkl` on purpose -- garbage fails at the
    first opcode, a truncation fails only after the loader has already
    allocated part of the object graph.
    """
    path = Path(out) / "book.pkl"
    path.write_bytes(path.read_bytes()[:keep])
    return path


def remove_book_epub(out: Path | str) -> Path:
    """Delete ``book.epub``, leaving ``book.pkl`` claiming the book is published.

    This is the shape the reader actually breaks in: the library page still
    lists the book (it only looks for the marker) and epub.js then 404s.
    """
    path = Path(out) / "book.epub"
    path.unlink()
    return path
