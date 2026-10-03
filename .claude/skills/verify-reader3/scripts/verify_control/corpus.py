"""The smoke corpus: the repo's own EPUB 2 fixture, built fresh into the sandbox."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from verify_control import paths


def build_smoke(dest, repo=None):
    """Write `smoke.epub` with `tests/fixtures/epub_corpus.build_epub2`; return its path."""
    fixtures = str((paths.repo_root() if repo is None else Path(repo)) / "tests" / "fixtures")
    if fixtures not in sys.path:
        sys.path.insert(0, fixtures)
    from epub_corpus import build_epub2

    return Path(build_epub2(Path(dest)))


FOREIGN_MODEL = "verify-reader3/foreign-model"


def seed_stale_index(book_dir):
    """Write `<book_dir>/chroma_db/index_meta.json` that is stale for exactly one reason:
    its model_name is not the configured one (status, space and chunk count all look indexed)."""
    book_dir = Path(book_dir)
    meta = {
        "book_id": book_dir.name,
        "status": "indexed",
        "chunk_count": 1,
        "model_name": FOREIGN_MODEL,
        "space": "cosine",
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    db = book_dir / "chroma_db"
    db.mkdir(parents=True, exist_ok=True)
    tmp = db / "index_meta.json.tmp"
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp, db / "index_meta.json")
    return db / "index_meta.json"
