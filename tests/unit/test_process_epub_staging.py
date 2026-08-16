"""WI-2: regenerated artifacts go to a sibling staging dir; output_dir is never wiped.

Law (fixed point): for every user-owned path, ``(sha256, size, mtime_ns, inode)``
is unchanged after *every* outcome of a run. ``process_epub`` is the identity on
the user-owned subtree.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import pickle
import shutil
from pathlib import Path

import ebooklib
import pytest
from ebooklib import epub
from hypothesis import given, settings
from hypothesis import strategies as st

from bookdir import USER_PATHS, staging_leftovers, user_subset
from epub_builder import sha256_of
from reader3_app import reader3
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry, process_epub

SEGMENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=8)


@pytest.mark.parametrize("shape", ["abs", "rel", "trailing_sep", "nested"])
def test_staging_dir_is_created_beside_output_dir(
    shape, books_dir: Path, epub_v1: Path, monkeypatch
):
    """L2 / S3 - staging must be a sibling, whatever shape the caller passes."""
    monkeypatch.chdir(books_dir.parent)
    if shape == "abs":
        output_dir = str(books_dir / "sample_data")
    elif shape == "rel":
        output_dir = os.path.join("books", "sample_data")
    elif shape == "trailing_sep":
        output_dir = os.path.join("books", "sample_data") + os.sep
    else:
        output_dir = os.path.join("books", "a", "b", "sample_data")

    # Pre-create the destination with a user file in it, so the "no staging
    # inside the output directory" assertion below has something to be wrong
    # about; against an absent directory it could never fail.
    existing = Path(os.path.normpath(output_dir))
    existing.mkdir(parents=True)
    (existing / "notes.json").write_text('{"notes": []}', encoding="utf-8")

    seen = {}
    real_copy2 = shutil.copy2

    def recording_copy2(src, dst, *a, **kw):
        # Observed at a real seam, mid-run: the staging dir exists right now.
        target = os.path.normpath(output_dir)
        seen["parent"] = sorted(os.listdir(os.path.dirname(target) or "."))
        seen["inside_output"] = sorted(os.listdir(target)) if os.path.isdir(target) else []
        return real_copy2(src, dst, *a, **kw)

    monkeypatch.setattr(reader3.shutil, "copy2", recording_copy2)
    process_epub(str(epub_v1), output_dir)

    target = os.path.normpath(output_dir)
    base = os.path.basename(target)
    staged = [n for n in seen["parent"] if n.startswith(f"{base}.staging-")]
    assert len(staged) == 1, f"expected exactly one sibling staging dir, saw {seen['parent']}"
    assert seen["inside_output"] == ["notes.json"], (
        f"mid-run the output dir held {seen['inside_output']}: it must contain only the "
        "user's files, with nothing staged inside it"
    )
    assert staging_leftovers(Path(target)) == []
    assert (existing / "notes.json").read_text(encoding="utf-8") == '{"notes": []}'


@settings(max_examples=50, deadline=None)
@given(
    segments=st.lists(SEGMENT, min_size=1, max_size=4),
    absolute=st.booleans(),
    trailing=st.booleans(),
)
def test_staging_path_parent_equals_output_parent_property(segments, absolute, trailing):
    """L2 / S4 - the sibling property holds for arbitrary path shapes."""
    p = os.path.join(*segments)
    if absolute:
        p = os.sep + p
    if trailing:
        p = p + os.sep

    s = reader3._staging_dir(p)
    norm = os.path.normpath(p)

    assert os.path.dirname(s) == os.path.dirname(norm)
    assert os.path.basename(s).startswith(os.path.basename(norm) + ".staging-")
    assert s != norm
    assert not s.startswith(norm + os.sep)


def test_reprocess_leaves_all_four_user_paths_bytewise_and_inode_identical(
    seeded_book_dir: Path, epub_v2: Path, snapshot
):
    """L3 / S6 - the central law, asserted over the whole user subtree."""
    before = user_subset(snapshot(seeded_book_dir))
    assert set(before) == set(USER_PATHS), "the fixture must seed all four user-owned paths"

    process_epub(str(epub_v2), str(seeded_book_dir))

    after_full = snapshot(seeded_book_dir)
    assert user_subset(after_full) == before

    # Nothing invented, nothing of the user's removed.
    assert set(after_full) - set(before) == {
        "book.pkl",
        "book.epub",
        "images/",
        "images/cover.png",
        "images/new_plate.png",
    }


def test_committed_epub_and_images_match_source_and_book_images_map(
    books_dir: Path, epub_v1: Path, epub_v2: Path
):
    """L3 / S2 - the committed artifacts really are the source's bytes."""
    out = books_dir / "sample_data"

    for src, expected_files in (
        (epub_v1, ["cover.png", "oldplate.png"]),
        (epub_v2, ["cover.png", "new_plate.png"]),
    ):
        book = process_epub(str(src), str(out))

        assert sha256_of(out / "book.epub") == sha256_of(src)
        assert sorted(os.listdir(out / "images")) == sorted(expected_files)

        raw = epub.read_epub(str(src))
        image_items = [i for i in raw.get_items() if i.get_type() == ebooklib.ITEM_IMAGE]
        assert len(image_items) == 2
        # One committed file per ITEM_IMAGE, with that item's exact bytes.
        assert len(set(book.images.values())) == len(image_items)
        for item in image_items:
            rel = book.images[item.get_name()]
            assert (out / rel).read_bytes() == item.get_content()


def test_reprocess_drops_images_absent_from_the_new_epub(
    seeded_book_dir: Path, epub_v2: Path
):
    """L3 / S2 - book.pkl stays the sole authority on what the book contains."""
    out = seeded_book_dir
    assert sorted(os.listdir(out / "images")) == ["cover.png", "oldplate.png"]

    process_epub(str(epub_v2), str(out))

    assert sorted(os.listdir(out / "images")) == ["cover.png", "new_plate.png"]
    assert not (out / "images" / "oldplate.png").exists()
    with open(out / "book.pkl", "rb") as f:
        committed = pickle.load(f)
    assert set(committed.images.values()) == {"images/cover.png", "images/new_plate.png"}


def test_reprocess_does_not_touch_sibling_book_directories(
    seeded_book_dir: Path, books_dir: Path, epub_v1: Path, epub_v2: Path, snapshot
):
    """L3 / S2 - the blast radius is one directory, prefix collisions included."""
    from bookdir import make_seeded_book_dir

    decoys = {
        "sample_data_old": make_seeded_book_dir(books_dir, epub_v1, name="sample_data_old"),
        "other_data": make_seeded_book_dir(books_dir, epub_v1, name="other_data"),
    }
    before = {name: snapshot(path) for name, path in decoys.items()}

    process_epub(str(epub_v2), str(seeded_book_dir))

    assert {name: snapshot(path) for name, path in decoys.items()} == before
    assert sorted(os.listdir(books_dir)) == ["other_data", "sample_data", "sample_data_old"]


def test_failed_epub_copy_raises_and_commits_nothing(
    seeded_book_dir: Path, epub_v2: Path, snapshot
):
    """L4 / S1 - a failed EPUB copy aborts instead of publishing a book with no EPUB."""
    before = snapshot(seeded_book_dir)

    def denied(*_a, **_kw):
        raise OSError(errno.EACCES, "denied")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3.shutil, "copy2", denied)
        with pytest.raises(OSError) as ei:
            process_epub(str(epub_v2), str(seeded_book_dir))

    assert ei.value.errno == errno.EACCES
    assert snapshot(seeded_book_dir) == before
    assert staging_leftovers(seeded_book_dir) == []


def test_book_dataclass_fields_and_pickle_protocol_are_unchanged(
    books_dir: Path, epub_v1: Path
):
    """L2 / S3 - the storage contract is frozen; this fix must not widen it."""
    out = books_dir / "sample_data"
    book = process_epub(str(epub_v1), str(out))

    assert [f.name for f in dataclasses.fields(Book)] == [
        "metadata",
        "spine",
        "toc",
        "images",
        "source_file",
        "processed_at",
        "version",
    ]
    assert [f.name for f in dataclasses.fields(ChapterContent)] == [
        "id",
        "href",
        "title",
        "content",
        "text",
        "order",
    ]
    assert [f.name for f in dataclasses.fields(TOCEntry)] == [
        "title",
        "href",
        "file_href",
        "anchor",
        "children",
    ]
    assert [f.name for f in dataclasses.fields(BookMetadata)] == [
        "title",
        "language",
        "authors",
        "description",
        "publisher",
        "date",
        "identifiers",
        "subjects",
    ]

    pkl_bytes = (out / "book.pkl").read_bytes()
    assert pkl_bytes[:2] == b"\x80" + bytes([pickle.DEFAULT_PROTOCOL])
    assert book.version == "3.0"
