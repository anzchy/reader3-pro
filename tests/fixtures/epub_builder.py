"""Synthetic EPUB builder for the unit lane.

Builds small, deterministic EPUBs with ebooklib so tests never have to read a
real book out of ``books/``. Two variants (v1 / v2) differ in chapter text and
in image bytes, which is what makes "the artifacts were actually refreshed"
observable — ``Book.processed_at`` changes on every run, so pickle bytes alone
prove nothing.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

from ebooklib import epub

IMAGE_NAME = "images/cover.png"

# Two distinct fake PNG payloads. Content only has to be stable and distinct;
# nothing in the pipeline decodes it.
IMAGE_BYTES_V1 = b"\x89PNG\r\n\x1a\n" + b"VARIANT-ONE" * 4
IMAGE_BYTES_V2 = b"\x89PNG\r\n\x1a\n" + b"VARIANT-TWO-DIFFERENT-LENGTH" * 3
PLATE_BYTES_V1 = b"\x89PNG\r\n\x1a\n" + b"OLD-PLATE" * 5
PLATE_BYTES_V2 = b"\x89PNG\r\n\x1a\n" + b"NEW-PLATE" * 7

#: v1 carries a plate whose name the sanitiser rewrites ("old plate.png" ->
#: "oldplate.png"); v2 replaces it with a differently named one. The pair is
#: what makes "images absent from the new EPUB are dropped" observable.
IMAGES_V1 = {IMAGE_NAME: IMAGE_BYTES_V1, "images/old plate.png": PLATE_BYTES_V1}
IMAGES_V2 = {IMAGE_NAME: IMAGE_BYTES_V2, "images/new_plate.png": PLATE_BYTES_V2}


def build_epub(
    path: str | os.PathLike[str],
    *,
    title: str = "Test Book",
    chapter_texts: Sequence[str] = ("Body text one.", "Body text two."),
    images: Mapping[str, bytes] | None = None,
    identifier: str = "urn:uuid:reader3-test-book-0001",
) -> Path:
    """Write a minimal but structurally complete EPUB to ``path``.

    The result has ``len(chapter_texts)`` document spine entries plus the nav
    document, ``len(images)`` images, and a real (non-empty) TOC, so
    ``process_epub`` does not silently fall back to ``get_fallback_toc``.
    Pass ``images={}`` for a plain-text book with no illustrations at all.
    """
    if images is None:
        images = IMAGES_V1

    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    book.set_language("en")
    book.add_author("Ada Tester")

    for n, (name, payload) in enumerate(images.items(), start=1):
        book.add_item(
            epub.EpubItem(
                uid=f"img{n}",
                file_name=name,
                media_type="image/png",
                content=payload,
            )
        )

    first_image = next(iter(images), None)
    chapters: List[epub.EpubHtml] = []
    for i, body in enumerate(chapter_texts, start=1):
        chapter = epub.EpubHtml(title=f"Chapter {i}", file_name=f"chap_{i}.xhtml", lang="en")
        img_tag = f"<img src='{first_image}'/>" if first_image else ""
        chapter.content = (
            f"<html><body><h1>Chapter {i}</h1>"
            f"<p>{body}</p>"
            f"{img_tag}"
            "</body></html>"
        )
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *chapters]

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out), book)
    return out


MARKER_V1 = "MARKER-V1"
MARKER_V2 = "MARKER-V2"


def build_v1(path: str | os.PathLike[str]) -> Path:
    return build_epub(
        path,
        title="Version One Book",
        chapter_texts=(
            f"Alpha prose {MARKER_V1}.",
            f"Beta prose {MARKER_V1}.",
        ),
        images=IMAGES_V1,
    )


def build_v2(path: str | os.PathLike[str]) -> Path:
    """Same book identity, different content: extra chapter, new text, new images.

    The extra chapter makes "the spine was refreshed" observable by length as
    well as by marker text, and dropping ``old plate.png`` in favour of
    ``new_plate.png`` makes "images absent from the new EPUB are dropped"
    observable at all.
    """
    return build_epub(
        path,
        title="Version Two Book",
        chapter_texts=(
            f"Gamma prose {MARKER_V2}.",
            f"Delta prose {MARKER_V2}.",
            f"Epsilon prose only in {MARKER_V2}.",
        ),
        images=IMAGES_V2,
    )


def build_imageless(path: str | os.PathLike[str], *, marker: str = MARKER_V2) -> Path:
    """A plain-text book: no ITEM_IMAGE at all, no <img> tags."""
    return build_epub(
        path,
        title="Plain Text Book",
        chapter_texts=(f"Only prose {marker}.", f"Still only prose {marker}."),
        images={},
    )


# --- filesystem snapshots -------------------------------------------------


def sha256_of(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def snapshot_tree(root: str | os.PathLike[str]) -> Dict[str, Tuple[str, int, int, int]]:
    """Map ``relpath -> (sha256, size, mtime_ns, inode)`` for every file under root.

    Directories appear as ``relpath + "/"`` mapped to
    ``("<dir>", 0, st_mtime_ns, st_ino)`` so a vanished, recreated or merely
    re-linked directory shows up in a diff. Recording inode and
    mtime_ns is what lets a test tell "identical content" from "never touched".
    """
    snap: Dict[str, Tuple[str, int, int, int]] = {}
    root_path = Path(root)
    if not root_path.exists():
        return snap
    for dirpath, dirnames, filenames in os.walk(root_path):
        for d in dirnames:
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, root_path)
            st = os.stat(full)
            snap[rel.replace(os.sep, "/") + "/"] = ("<dir>", 0, st.st_mtime_ns, st.st_ino)
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root_path).replace(os.sep, "/")
            st = os.stat(full)
            snap[rel] = (sha256_of(full), st.st_size, st.st_mtime_ns, st.st_ino)
    return snap
