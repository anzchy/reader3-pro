"""A synthetic library of N books, for the §6 "TTFB x library size" benchmark.

Twenty is not a round number chosen for looks. ``web.server.load_book_cached``
is ``@lru_cache(maxsize=10)`` and ``search_service.load_book_index`` is
``maxsize=12`` (it was 4 until 011 WI-8/C1 resized it to "six books in hand x
two case flags"); a library at or below either bound turns the benchmark into a
measurement of cache hits, which is the opposite of what the benchmark is for.
The count therefore has to exceed both, and
``tests/unit/test_fixture_synthetic_library.py`` asserts it against the real
``cache_parameters()`` rather than against a copy of the numbers -- so raising a
maxsize in production turns the fixture red instead of quietly neutering it.

Books are pickled directly rather than driven through ``process_epub``. Two
reasons: twenty EPUB round trips cost seconds in a lane budgeted at two, and
the benchmark measures the *read* path, which only ever sees ``book.pkl``.
"""

from __future__ import annotations

import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Union

from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry

PathLike = Union[str, "os.PathLike[str]"]

#: Above both cache bounds (10 and 12) with room to spare, and small enough that
#: building the whole library stays well inside the unit lane's time budget. The
#: margin over the index bound is now eight books rather than sixteen; WI-8 left
#: it deliberately, because the benchmark needs the library to outrun the cache
#: and a bound that grew to meet the library would delete the measurement.
DEFAULT_BOOK_COUNT = 20

_FILLER = "The tide went out and the boats leaned over in the mud, one after another. "


def book_marker(index: int) -> str:
    """A token that appears in exactly one book of the library."""
    return f"SYNTHMARK{index:03d}"


def chapter_marker(book_index: int, chapter_index: int) -> str:
    """A token that appears in exactly one chapter of one book."""
    return f"{book_marker(book_index)}C{chapter_index:02d}"


def make_book(
    index: int, *, chapters: int = 8, chapter_chars: int = 2000
) -> Book:
    """A ``Book`` whose every chapter carries a globally unique marker."""
    spine: List[ChapterContent] = []
    toc: List[TOCEntry] = []
    for order in range(chapters):
        marker = chapter_marker(index, order)
        body = (_FILLER * (chapter_chars // len(_FILLER) + 1))[:chapter_chars]
        text = f"{marker} {body}"
        href = f"text/chap{order:02d}.xhtml"
        spine.append(
            ChapterContent(
                id=f"c{order}",
                href=href,
                title=f"Section {order + 1}",
                content=f"<h1>Section {order + 1}</h1><p>{text}</p>",
                text=text,
                order=order,
            )
        )
        toc.append(
            TOCEntry(title=f"Chapter {order + 1}", href=href, file_href=href, anchor="")
        )

    return Book(
        metadata=BookMetadata(
            title=f"Synthetic Book {index:02d}",
            language="en",
            authors=[f"Author {index:02d}"],
            identifiers=[f"urn:uuid:reader3-synth-{index:03d}"],
        ),
        spine=spine,
        toc=toc,
        images={"images/cover.png": "images/cover.png", "cover.png": "images/cover.png"},
        source_file=f"synth{index:02d}.epub",
        processed_at=datetime(2026, 8, 24, 0, 0, 0).isoformat(),
    )


def make_synthetic_library(
    books_dir: PathLike,
    *,
    count: int = DEFAULT_BOOK_COUNT,
    chapters: int = 8,
    chapter_chars: int = 2000,
    prefix: str = "synth",
) -> Tuple[Path, ...]:
    """Create ``count`` complete ``{prefix}NN_data`` directories under ``books_dir``.

    The post-condition is asserted here rather than in each caller, for the same
    reason ``bookdir.make_seeded_book_dir`` asserts its seeding: a benchmark
    that silently ran against three books instead of twenty would report a
    number that looks fine and means nothing.
    """
    root = Path(books_dir)
    root.mkdir(parents=True, exist_ok=True)

    created: List[Path] = []
    for index in range(count):
        out = root / f"{prefix}{index:02d}_data"
        (out / "images").mkdir(parents=True, exist_ok=True)
        (out / "images" / "cover.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + book_marker(index).encode("ascii") * 2
        )
        with open(out / "book.pkl", "wb") as f:
            pickle.dump(
                make_book(index, chapters=chapters, chapter_chars=chapter_chars), f
            )
        created.append(out)

    published = sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name.endswith("_data") and (p / "book.pkl").is_file()
    )
    assert len(published) == count, (
        f"synthetic library should hold {count} published books, found "
        f"{len(published)}: {published}"
    )
    return tuple(created)
