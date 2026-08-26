"""Group 4, second half: a book directory damaged *after* it was published.

No EPUB can express these. The archive was fine, processing succeeded, and then
a cloud sync half-wrote the folder, a reindex was killed, or a user deleted what
looked like a redundant copy of their own book. Every loader in the codebase
keys a book's existence on ``book.pkl`` being present, so each helper here is a
different answer to "the marker is there, now what?".

The two ``load_book_cached`` functions answer it differently, which is the point
of ``test_the_two_loaders_disagree`` below.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

import bookdir
import synthetic_library as sl
from reader3_app import search_service
from reader3_app.web import server as web_server


@pytest.fixture
def published(books_dir: Path) -> Path:
    """One small, complete, freshly published book directory."""
    (out,) = sl.make_synthetic_library(books_dir, count=1, chapters=2, chapter_chars=200)
    (out / "book.epub").write_bytes(b"PK\x03\x04" + b"pretend-epub" * 8)
    return out


@pytest.fixture(autouse=True)
def _clear_loader_caches():
    search_service.load_book_cached.cache_clear()
    web_server.load_book_cached.cache_clear()
    yield
    search_service.load_book_cached.cache_clear()
    web_server.load_book_cached.cache_clear()


def test_break_book_pkl_leaves_a_file_that_fails_at_the_first_opcode(published: Path):
    """L2 - the damage must be real damage, and the marker must survive it."""
    path = bookdir.break_book_pkl(published)

    assert path == published / "book.pkl"
    assert path.is_file() and path.stat().st_size > 0
    with pytest.raises(pickle.UnpicklingError, match="invalid load key"):
        pickle.loads(path.read_bytes())


def test_truncate_book_pkl_fails_later_than_a_garbage_file_does(published: Path):
    """L2 - a valid prefix with no STOP; distinct from garbage on purpose.

    Garbage dies before the loader allocates anything. A truncation dies after
    it has started building the object graph, which is the failure mode that
    leaves half-initialised state behind in loaders less careful than these.
    """
    original = (published / "book.pkl").read_bytes()
    path = bookdir.truncate_book_pkl(published, keep=32)

    assert path.read_bytes() == original[:32]
    assert len(original) > 32
    assert path.read_bytes()[:1] == b"\x80"  # still a real pickle protocol header
    with pytest.raises(pickle.UnpicklingError, match="truncated"):
        pickle.loads(path.read_bytes())


def test_remove_book_epub_keeps_the_marker_the_library_scan_looks_for(published: Path):
    """L3 - the book stays listed and still loads; only the reader breaks.

    ``server.library_view`` (server.py:170) lists a directory on ``_data`` plus
    a loadable ``book.pkl``; ``/read/{book_id}/book.epub`` (server.py:477) is a
    separate existence check. This fixture is the state where the first passes
    and the second 404s.
    """
    path = bookdir.remove_book_epub(published)

    assert not path.exists()
    assert (published / "book.pkl").is_file()
    assert published.name.endswith("_data")

    book = search_service.load_book_cached(published.name, str(published.parent))
    assert book.metadata.title == "Synthetic Book 00"


@pytest.mark.parametrize("damage", ["garbage", "truncated"], ids=["garbage", "truncated"])
def test_the_two_loaders_disagree_about_a_corrupt_book_pkl(
    published: Path, monkeypatch: pytest.MonkeyPatch, damage: str
):
    """L4 - pinned behaviour: fault injection recording a real asymmetry.

    Same file, same corruption, two answers: ``search_service`` raises and any
    cross-book search dies on the one bad book, while ``web.server`` swallows
    it and the book silently disappears from the library. Recorded as current
    behaviour; 011 decides which one is correct.
    """
    if damage == "garbage":
        bookdir.break_book_pkl(published)
    else:
        bookdir.truncate_book_pkl(published)

    with pytest.raises(pickle.UnpicklingError):
        search_service.load_book_cached(published.name, str(published.parent))

    monkeypatch.setattr(web_server, "BOOKS_DIR", str(published.parent))
    assert web_server.load_book_cached(published.name) is None


def test_a_missing_book_pkl_is_the_one_case_both_loaders_agree_on(
    published: Path, monkeypatch: pytest.MonkeyPatch
):
    """L4 - the control: absence is handled, corruption is not."""
    (published / "book.pkl").unlink()

    monkeypatch.setattr(web_server, "BOOKS_DIR", str(published.parent))
    assert web_server.load_book_cached(published.name) is None

    with pytest.raises(FileNotFoundError):
        search_service.load_book_cached(published.name, str(published.parent))
