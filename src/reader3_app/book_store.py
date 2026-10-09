"""The one cached reader of ``book.pkl``, keyed on the file's stat.

Before this module there were two loaders — ``search_service.load_book_cached``
and ``web.server.load_book_cached`` — each an ``@lru_cache`` over
``(book_id, books_dir)``. Two consequences, and the second is the bug:

1. **Two caches.** The same book was unpickled once per module, so a warm
   library cost twice the memory it needed to and the reader and the search
   path could hold two different ``Book`` objects for one file.
2. **Neither cache could see a republish.** ``(book_id, books_dir)`` says
   nothing about the file's *content*, so reprocessing an EPUB left every
   already-read book frozen at its old contents until the process restarted.

The key here is ``(book_id, books_dir, st_mtime_ns, st_size)``. That is not a
content fingerprint and is not meant to be one: a rewrite that lands inside one
filesystem tick with the same byte count is invisible, which is the accepted
trade recorded in the plan's §4.2 (a content hash would re-read the whole file
on every request, which is the cost the cache exists to avoid).

Three decisions worth knowing before editing this file:

* **``books_dir`` is not normalized into the key.** ``"books"`` and
  ``"./books"`` are two entries. Production always passes the identical
  ``server.BOOKS_DIR`` string, so the duplicate never happens there, and
  normalizing would alter the path construction that
  ``tests/contract/test_read_chapter_traversal.py`` guards.
  ``test_book_store.py`` records this as characterization: a future normalizer
  has to turn it red deliberately.
* **This module raises.** Corrupt bytes raise ``pickle.UnpicklingError``, an
  absent file raises ``FileNotFoundError`` from the ``os.stat`` before any
  ``open()``, and (012 WI-3.2) a corrupt ``manifest.json`` raises
  ``book_format.BookCorrupt`` before the pickle is touched. It does not swallow and never returns ``None``: a loader that
  answers ``None`` for "corrupt" and for "absent" alike forces every caller to
  re-derive which one happened. Deciding what the *user* sees is the web
  layer's job, at the boundary that has a status code to spend. (The loaders
  only: ``book_fingerprint`` answers ``None`` for "cannot judge" by ruling —
  see its docstring.)
* **It imports nothing from ``reader3_app.web``.** Reaching for
  ``server.BOOKS_DIR`` from here would be both an import cycle and a violation
  of the namespace rule in ``tests/unit/test_server_patch_seam_ownership.py``.
  The caller passes the directory.

The stat-then-load sequence is not atomic, and deliberately so. Two threads
missing the same key both unpickle, and one of the two results is discarded —
the cost is a duplicated read on a cold key, and the alternative is a lock held
across file I/O on a path that runs under ``run_in_threadpool``. The bound is
pinned by a test rather than left to be rediscovered.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from . import book_format
from .safe_paths import safe_book_folder
from .safe_pickle import load_book_file

logger = logging.getLogger(__name__)


def _book_pkl_path(book_id: str, books_dir: str) -> str:
    """Where a book's pickle lives, with ``books_dir`` preserved verbatim.

    No ``abspath``, no ``normpath``, no trailing-separator cleanup — see the
    module docstring on why the caller's spelling survives into the cache key.
    """
    return os.path.join(books_dir, book_id, "book.pkl")


@lru_cache(maxsize=10)
def _load_book_for_stat(
    book_id: str, books_dir: str, st_mtime_ns: int, st_size: int
) -> Any:
    """The memoized half. ``st_mtime_ns`` and ``st_size`` are key material only.

    They are read by the caller, not here: recomputing the stat inside the
    cached function would defeat the point, since the memo is consulted before
    the body ever runs.
    """
    return load_book_file(_book_pkl_path(book_id, books_dir))


def storage_format(book_id: str, books_dir: str) -> book_format.BookState:
    """``"missing"`` / ``"corrupt"`` / ``"valid"`` for one book (012 WI-3.2). Read-only, silent, never cached.

    ``safe_book_folder`` runs first, so an unsafe id raises its ``ValueError`` before any filesystem read; the
    verdict itself is ``book_format.classify(..., full=False)`` and is never re-implemented here. Not memoized
    on purpose: a manifest can go bad without its stat changing (a removed generation), and the loaders below
    ask this question on every call, outside the stat-keyed cache.
    """
    folder = safe_book_folder(book_id)
    return book_format.classify(os.path.join(books_dir, folder), full=False)


def _refuse_corrupt(book_id: str, books_dir: str) -> None:
    """Raise ``BookCorrupt`` (logging exactly one ERROR) when the book's ``manifest.json`` is corrupt.

    ``missing`` and ``valid`` both fall through to the flat ``book.pkl`` (WI-3.2 Q1: ``valid`` keeps reading the
    flat pickle until WI-4a). ``corrupt`` never falls back: a book whose manifest exists but cannot be trusted is
    answered loudly rather than served from a pickle that may be stale.
    """
    if storage_format(book_id, books_dir) == "corrupt":
        logger.error("book %r: manifest.json is corrupt; refusing to serve the flat book.pkl", book_id)
        raise book_format.BookCorrupt(f"book {book_id!r}: storage is corrupt")


def load_book_cached(book_id: str, books_dir: str) -> object:
    """Return the ``Book`` in ``{books_dir}/{book_id}/book.pkl``, or raise.

    One ``os.stat`` per call is the price of freshness — roughly a microsecond
    against the tens of milliseconds an unpickle of a real book costs. Reads of
    an unchanged file return the ``is``-identical object every time.

    012 WI-3.2: every call first asks :func:`storage_format`, outside the cache.
    An unsafe ``book_id`` raises ``ValueError``; a corrupt manifest raises
    ``book_format.BookCorrupt`` after one ERROR log, without reading the pickle.
    """
    _refuse_corrupt(book_id, books_dir)
    stat_result = os.stat(_book_pkl_path(book_id, books_dir))
    return _load_book_for_stat(
        book_id, books_dir, stat_result.st_mtime_ns, stat_result.st_size
    )


# The cache surface belongs to the public name, because that is the name every
# caller and every test holds. These are the inner cache's own bound methods,
# not wrappers: `load_book_cached.cache_clear()` clears the one real cache, and
# `cache_info()` counts the one real set of hits and misses. Nothing is
# memoized above this line, so those counters describe every call.
load_book_cached.cache_clear = _load_book_for_stat.cache_clear  # type: ignore[attr-defined]
load_book_cached.cache_info = _load_book_for_stat.cache_info  # type: ignore[attr-defined]
load_book_cached.cache_parameters = _load_book_for_stat.cache_parameters  # type: ignore[attr-defined]


# --- the 012 granularity seam ----------------------------------------------
#
# `012-storage-format` wants to answer "what is this book called" without
# unpickling a whole `Book`. It cannot do that while every caller holds the one
# name `load_book_cached`, because then the storage change and the call-site
# change are the same commit. So the two questions get two names *now*, both
# served by the one loader, and 012 changes what sits under
# `load_book_metadata` without touching a caller. Its one consumer is
# `web/routers/library_books.py` (`GET /api/library`, 018 WI-4 Q-A), and
# `tests/unit/test_book_store_metadata_seam.py` locks that allowlist.


@dataclass(frozen=True)
class BookMetadataView:
    """The three fields a library listing needs, and nothing else.

    ``authors`` stays a sequence. ``", ".join(...)`` is presentation, it already
    lives at the call sites, and a pre-joined string is lossy for an author
    named ``"Smith, Jr."``. Frozen because it is a value: two views of the same
    book compare equal, which is what lets a freshness test say "unchanged file,
    equal view" without reaching for identity.
    """

    book_id: str
    title: str
    authors: tuple[str, ...]


def load_book(book_id: str, books_dir: str) -> object:
    """The full read, under the name that says so. Delegates, never re-reads.

    A second name, not a second read path: it forwards to ``load_book_cached``
    and returns that object, so there is one cache and nothing that can drift in
    behind it. The name exists so a caller can say *which* of the two questions
    it is asking — the whole book, or just its listing fields.

    Written as a delegating ``def`` rather than the shorter
    ``load_book = load_book_cached``. The alias is a module-level rebind of a
    patch-seam name, which is the import-time-capture shape
    ``tests/unit/test_server_patch_seam_ownership.py``'s Check C exists to
    refuse: it launders a listed name into an unlisted one, so a
    ``monkeypatch.setattr(book_store, "load_book_cached", ...)`` would silently
    miss every call that arrived through ``load_book``. The ``def`` resolves the
    name at call time and keeps the seam whole.
    """
    return load_book_cached(book_id, books_dir)


def load_book_metadata(book_id: str, books_dir: str) -> BookMetadataView:
    """The library-listing view of a book: title, authors, id.

    **A full read today.** The body calls ``load_book_cached`` and projects three
    fields off the result, so the whole pickle is loaded and the shared,
    mtime-keyed cache is what keeps a second call from touching the file again.
    That is on purpose: ``012-storage-format`` replaces this body with a
    ``manifest.json`` read, and this seam exists so that swap can happen without
    a single call site changing.

    The contract is therefore about *values*, not about work. It promises the
    same ``title`` and ``authors`` the full ``Book`` carries and the same
    freshness key; it promises nothing about how much of the file it touches,
    and no caller may assume otherwise. ``test_book_store_metadata_seam.py``'s
    projection property is the contract 012's new body has to keep passing.

    Degradation mirrors the existing call sites (``search_service.load_book_index``
    and ``server.library_view``) exactly, ``getattr`` chain included: absent
    metadata falls back to ``book_id`` for the title and to empty ``authors``,
    while an *empty* title stays empty — ``getattr`` found the attribute, so
    there is nothing to fall back from.

    It does not swallow. A corrupt or absent ``book.pkl`` raises out of here
    exactly as it does out of ``load_book``; deciding what the user sees is the
    web layer's job, at the boundary that has a status code to spend (D1-a).
    """
    book = load_book_cached(book_id, books_dir)
    return BookMetadataView(
        book_id=book_id,
        title=getattr(getattr(book, "metadata", None), "title", book_id),
        authors=tuple(getattr(getattr(book, "metadata", None), "authors", []) or []),
    )


def pick_cover_image(book_id: str, books_dir: str) -> Optional[str]:
    """The file name of a book's cover thumbnail, or ``None``. Never raises.

    The one cover picker (018 WI-4, Q-C), lifted byte-for-byte from the inline
    picker that ``library_view`` used to carry, so ``GET /`` and
    ``GET /api/library`` cannot disagree. Candidates are the regular, non-dot
    files directly in ``{books_dir}/{book_id}/images``; names containing
    ``cover`` or ``title`` (case-folded) are preferred when any exist; the winner
    is the minimum under ``(len, lower)``. Returns a file name, not a URL — the
    URL shape is the web layer's.
    """
    cover_image = None
    try:
        images_dir = os.path.join(books_dir, book_id, "images")
        if os.path.isdir(images_dir):
            candidates = [
                f
                for f in os.listdir(images_dir)
                if os.path.isfile(os.path.join(images_dir, f)) and not f.startswith(".")
            ]
            preferred = [f for f in candidates if "cover" in f.lower() or "title" in f.lower()]
            pick_from = preferred or candidates
            if pick_from:
                cover_image = sorted(pick_from, key=lambda x: (len(x), x.lower()))[0]
    except Exception:  # noqa: BLE001 - 第 3 档：封面挑选失败只影响一张缩略图，书本身照常打开
        cover_image = None
    return cover_image


# --- the stored book fingerprint (012 WI-2a.5, ruling R2) -------------------

#: ``(books_dir, book_id)`` pairs already warned about. It gates the log line
#: only, never the read: a repaired manifest is read again on the next call.
_FINGERPRINT_WARNED: set[tuple[str, str]] = set()


def book_fingerprint(book_id: str, books_dir: str) -> Optional[str]:
    """The current generation's stored ``manifest.book_fingerprint``, or ``None``.

    Read, never recomputed: the value comes from ``book_format.validate_stat``
    (a stat-level check of the generation plus a parse of ``manifest.json``).

    ``None`` means "cannot judge" — not stale — and covers two states:

    * **missing**: no ``manifest.json`` (a pkl-only book, an empty or absent
      directory). Silent, or every pre-012 book would log on every call.
    * **corrupt**: any ``BookFormatError`` or other ``OSError``. Logs ONE
      WARNING per ``(books_dir, book_id)``, not one per call. Failing loudly on
      corrupt is ``storage_format``'s job (WI-3), not this layer's.

    The id goes through ``safe_book_folder`` before any path is built, so a
    traversal id raises ``ValueError`` instead of reading outside
    ``books_dir``. ``load_book`` / ``load_book_cached`` / ``load_book_metadata``
    never call this: a fingerprint cannot block a book from opening.
    """
    book_dir = os.path.join(books_dir, safe_book_folder(book_id))
    try:
        manifest = book_format.validate_stat(book_dir)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (book_format.BookFormatError, OSError) as exc:
        key = (books_dir, book_id)
        if key not in _FINGERPRINT_WARNED:
            _FINGERPRINT_WARNED.add(key)
            logger.warning("book %r: manifest unreadable, fingerprint unknown: %s", book_id, exc)
        return None
    return manifest.book_fingerprint


# --- the current generation, for rebind (012 WI-2b.4) ------------------------


@dataclass(frozen=True)
class CurrentGeneration:
    """One published generation, as rebind reads it: fingerprint, chapter count, lazy chapter texts.

    ``chapter_text(i)`` reads ``manifest.chapters[i]`` **by position**, never by its ``order`` field
    (plan R-3; WI-3 must keep position aligned with ``Book.spine[i]``). Each call is one seek-read
    through ``book_format.read_chapter`` and raises what it raises (``ChapterReadError`` / ``OSError``):
    a chapter that cannot be read is "cannot judge", which only the caller can turn into a no-op.
    """

    fingerprint: str
    chapter_count: int
    gen_dir: str
    entries: tuple[book_format.ChapterIndexEntry, ...]

    def chapter_text(self, index: int) -> str:
        return book_format.read_chapter(self.gen_dir, self.entries[index]).text


def current_generation(book_id: str, books_dir: str) -> Optional[CurrentGeneration]:
    """The current generation, or ``None`` exactly where :func:`book_fingerprint` is ``None``.

    Missing (no manifest, no directory) and corrupt (any ``BookFormatError`` / ``OSError`` from
    ``validate_stat``) are both "cannot judge". Silent here: :func:`book_fingerprint` already owns the
    one-per-book warning for a corrupt manifest. Read-only; nothing is read beyond the stat check until
    a chapter's text is asked for. The id goes through ``safe_book_folder`` first (ADR-0012).
    """
    book_dir = os.path.join(books_dir, safe_book_folder(book_id))
    try:
        manifest = book_format.validate_stat(book_dir)
    except (book_format.BookFormatError, OSError):
        return None
    gen_dir = os.path.join(book_dir, book_format.GEN_DIR, str(manifest.generation))
    return CurrentGeneration(manifest.book_fingerprint, len(manifest.chapters), gen_dir, manifest.chapters)
