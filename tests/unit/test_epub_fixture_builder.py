"""WI-1: the synthetic EPUB builder and the filesystem snapshot helper.

These two helpers carry every later assertion in the lane, so they are pinned
here. If the snapshot stops discriminating a same-bytes rewrite from an
untouched file, every "user data survived" case downstream passes vacuously.
"""

from __future__ import annotations

import os
from pathlib import Path

import ebooklib
from ebooklib import epub

from epub_builder import (
    IMAGE_BYTES_V1,
    IMAGE_BYTES_V2,
    MARKER_V1,
    MARKER_V2,
    sha256_of,
    snapshot_tree,
)
from reader3_app.reader3 import process_epub


def test_builder_yields_three_spine_docs_one_image_and_two_toc_roots(
    epub_v1: Path, books_dir: Path, capsys
):
    """L2 / S1 - the fixture is a real book, not a shell that silently degrades."""
    raw = epub.read_epub(str(epub_v1))
    documents = [i for i in raw.get_items() if i.get_type() == ebooklib.ITEM_DOCUMENT]
    images = [i for i in raw.get_items() if i.get_type() == ebooklib.ITEM_IMAGE]

    assert len(documents) == 3  # nav + 2 chapters
    assert len(images) == 2
    assert raw.toc  # non-empty, so get_fallback_toc is not exercised

    book = process_epub(str(epub_v1), str(books_dir / "builder_data"))
    out = capsys.readouterr().out
    assert "Warning: Empty TOC" not in out

    # 'old plate.png' exercises the filename sanitiser: the map keeps the raw
    # EPUB name as key, the value points at the sanitised on-disk name.
    assert book.images == {
        "images/cover.png": "images/cover.png",
        "cover.png": "images/cover.png",
        "images/old plate.png": "images/oldplate.png",
        "old plate.png": "images/oldplate.png",
    }
    assert len(book.spine) == 3
    assert len(book.toc) == 2


def test_v1_and_v2_differ_in_chapter_text_image_bytes_and_epub_sha256(
    epub_v1: Path, epub_v2: Path, books_dir: Path
):
    """L2 / S2 - the v1/v2 pair is the discriminator for every refresh assertion."""
    assert sha256_of(epub_v1) != sha256_of(epub_v2)
    assert IMAGE_BYTES_V1 != IMAGE_BYTES_V2

    b1 = process_epub(str(epub_v1), str(books_dir / "one_data"))
    b2 = process_epub(str(epub_v2), str(books_dir / "two_data"))

    assert any(MARKER_V1 in c.text for c in b1.spine)
    assert not any(MARKER_V2 in c.text for c in b1.spine)
    assert any(MARKER_V2 in c.text for c in b2.spine)
    assert not any(MARKER_V1 in c.text for c in b2.spine)

    assert (books_dir / "one_data" / "images" / "cover.png").read_bytes() != (
        books_dir / "two_data" / "images" / "cover.png"
    ).read_bytes()

    # v1 carries a plate that v2 drops, and v2 carries one v1 never had.
    assert sorted(os.listdir(books_dir / "one_data" / "images")) == ["cover.png", "oldplate.png"]
    assert sorted(os.listdir(books_dir / "two_data" / "images")) == ["cover.png", "new_plate.png"]


def test_snapshot_detects_rewrite_even_when_bytes_are_identical(tmp_path: Path):
    """L3 / S6 - same content is not the same as untouched."""
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_bytes(b"same bytes")
    (root / "b.txt").write_bytes(b"same bytes")

    before = snapshot_tree(root)

    # Rewrite b.txt with identical bytes the way the implementation will:
    # tmp file in the same directory, then os.replace.
    tmp = root / "b.txt.tmp"
    tmp.write_bytes(b"same bytes")
    os.replace(tmp, root / "b.txt")

    after = snapshot_tree(root)

    assert after["a.txt"] == before["a.txt"]
    assert after["b.txt"][0] == before["b.txt"][0]  # sha256 equal
    assert after["b.txt"] != before["b.txt"]  # but inode/mtime say it was replaced
