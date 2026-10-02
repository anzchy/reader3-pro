"""`book_store.pick_cover_image(book_id, books_dir)` — the one cover picker (018 WI-4, Q-C).

The rules are lifted byte-for-byte from the inline picker in
``web/routers/library.py:library_view`` so that ``GET /`` and ``GET /api/library``
cannot disagree about a book's cover.

**Law** (total-order argmin). Let E = regular, non-dot files directly in
``{books_dir}/{book_id}/images``; P = {e in E : "cover" or "title" in e.lower()};
pool = P if P else E. The result is ``None`` iff E is empty or listing fails;
otherwise it is in pool and ``key(result) <= key(e)`` for every e in pool, with
``key = (len, lower)``. With names unique under ``lower()`` the argmin is unique,
so the result does not depend on listing order. It never raises.

The helper is resolved through ``picker()`` inside each test body, not imported at
module scope: before the green commit the name does not exist, and a module-level
import would turn this whole file into a collection error instead of a counted
red per case.
"""

from __future__ import annotations

import importlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

BOOK_ID = "cover_probe_data"


def picker() -> Callable[[str, str], Optional[str]]:
    module = importlib.import_module("reader3_app.book_store")
    assert hasattr(module, "pick_cover_image"), (
        "reader3_app.book_store has no pick_cover_image. 018 WI-4 (Q-C) extracts the "
        "cover picker from library_view into book_store.pick_cover_image(book_id, books_dir) "
        "-> Optional[str] (the file name, not a URL)."
    )
    return module.pick_cover_image


def _images(books_dir: Path, files=(), dirs=()) -> Path:
    images = books_dir / BOOK_ID / "images"
    images.mkdir(parents=True)
    for name in files:
        (images / name).write_bytes(b"img")
    for name in dirs:
        (images / name).mkdir()
    return images


def test_prefers_cover_named_file(tmp_path: Path):
    """T4-U1 — L1/S1."""
    pick = picker()
    _images(tmp_path, files=("a.png", "cover.jpg", "zz.gif"))
    assert pick(BOOK_ID, str(tmp_path)) == "cover.jpg"


def test_title_named_file_counts_as_preferred(tmp_path: Path):
    """T4-U2 — L1/S2: the second member of the preferred class, case-folded."""
    pick = picker()
    _images(tmp_path, files=("a.png", "Title_Page.PNG"))
    assert pick(BOOK_ID, str(tmp_path)) == "Title_Page.PNG"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param(("bbbb.png", "aa.png", "ccc.png"), "aa.png", id="length-first"),
        pytest.param(("B.png", "a.png"), "a.png", id="equal-length-case-insensitive"),
        pytest.param(("my_cover.jpg", "cover.jpg"), "cover.jpg", id="preferred-tier-sorted-too"),
    ],
)
def test_fallback_sorted_by_length_then_lowercase(tmp_path: Path, files, expected):
    """T4-U3 — L1/S2: both tie-break tiers."""
    pick = picker()
    _images(tmp_path, files=files)
    assert pick(BOOK_ID, str(tmp_path)) == expected


def test_dotfiles_directories_and_broken_links_excluded(tmp_path: Path):
    """T4-U4 — L1/S2: each excluded kind carries a name that would otherwise win."""
    pick = picker()
    images = _images(tmp_path, files=(".cover.jpg", "zzz_title_x.png"), dirs=("cover",))
    try:
        # A dangling link named like a cover: `isfile` follows it and finds nothing.
        os.symlink(str(images / "c.jpg"), str(images / "cover.png"))
    except (OSError, NotImplementedError):
        pass  # platform without symlink permission: the other two kinds still bite
    assert pick(BOOK_ID, str(tmp_path)) == "zzz_title_x.png"

    other = tmp_path / "only_excluded"
    other_images = other / BOOK_ID / "images"
    other_images.mkdir(parents=True)
    (other_images / ".a").write_bytes(b"x")
    (other_images / "dir_a").mkdir()
    assert pick(BOOK_ID, str(other)) is None


def test_missing_or_empty_images_dir_returns_none(tmp_path: Path):
    """T4-U5 — L1+L2/S2: four empty/absent edges, and no directory is created."""
    pick = picker()

    no_images = tmp_path / "a"
    (no_images / BOOK_ID).mkdir(parents=True)
    assert pick(BOOK_ID, str(no_images)) is None
    assert not (no_images / BOOK_ID / "images").exists()

    empty = tmp_path / "b"
    (empty / BOOK_ID / "images").mkdir(parents=True)
    assert pick(BOOK_ID, str(empty)) is None

    absent = tmp_path / "c"
    absent.mkdir()
    assert pick(BOOK_ID, str(absent)) is None
    assert not (absent / BOOK_ID).exists()

    images_is_file = tmp_path / "d"
    (images_is_file / BOOK_ID).mkdir(parents=True)
    (images_is_file / BOOK_ID / "images").write_bytes(b"not a directory")
    assert pick(BOOK_ID, str(images_is_file)) is None


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores mode 000")
def test_unreadable_images_dir_returns_none(tmp_path: Path):
    """T4-U6 — L1/S3: listing raises PermissionError, which is not FileNotFoundError."""
    pick = picker()
    images = _images(tmp_path, files=("cover.jpg",))
    os.chmod(images, 0o000)
    try:
        assert pick(BOOK_ID, str(tmp_path)) is None
    finally:
        os.chmod(images, 0o700)


_NAME = st.one_of(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
        min_size=1,
        max_size=14,
    ),
    st.sampled_from(["cover.jpg", "Cover.png", "title.gif", ".cover.jpg", "TITLEPAGE.jpeg"]),
).filter(lambda n: n not in (".", ".."))

_ENTRIES = st.lists(
    st.tuples(_NAME, st.sampled_from(["file", "dir"])),
    max_size=8,
    unique_by=lambda t: t[0].lower(),
)


def test_cover_choice_is_the_argmin_of_the_documented_order():
    """T4-U7 — L1/S4: the result is the argmin of (len, lower) over the right pool.

    E, P and pool are computed from the generated spec, never from ``os.listdir``,
    so the oracle shares nothing with the implementation's own listing.
    """
    pick = picker()

    @settings(max_examples=60, deadline=None)
    @given(entries=_ENTRIES)
    def check(entries):
        root = tempfile.mkdtemp(prefix="cover-argmin-")
        try:
            images = Path(root) / BOOK_ID / "images"
            images.mkdir(parents=True)
            for name, kind in entries:
                if kind == "file":
                    (images / name).write_bytes(b"x")
                else:
                    (images / name).mkdir()

            e_set = [n for n, k in entries if k == "file" and not n.startswith(".")]
            preferred = [n for n in e_set if "cover" in n.lower() or "title" in n.lower()]
            pool = preferred or e_set

            result = pick(BOOK_ID, root)
            if not e_set:
                assert result is None
                return
            assert result in pool, (result, pool)
            assert all(
                (len(result), result.lower()) <= (len(e), e.lower()) for e in pool
            ), (result, pool)
            assert pick(BOOK_ID, root) == result
        finally:
            shutil.rmtree(root, ignore_errors=True)

    check()
