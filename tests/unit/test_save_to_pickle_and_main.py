"""WI-4: save_to_pickle is atomic, and main() publishes the marker exactly once.

Law: ``pickle.load(open(out/"book.pkl","rb"))`` observed at any instant returns a
complete ``Book``; after a successful ``save_to_pickle`` that book has the same
spine ids and order as the argument; a CLI run flips the marker once.
"""

from __future__ import annotations

import errno
import glob
import os
import pickle
import shutil
from pathlib import Path

import pytest

from bookdir import staging_leftovers, user_subset
from epub_builder import MARKER_V1, MARKER_V2, sha256_of
from reader3_app import reader3
from reader3_app.reader3 import Book, process_epub, save_to_pickle


def load_pkl(out: Path) -> Book:
    with open(out / "book.pkl", "rb") as f:
        return pickle.load(f)


def joined_text(book: Book) -> str:
    return " ".join(c.text for c in book.spine)


def test_save_to_pickle_failure_preserves_prior_pkl_and_leaves_no_tmp(
    seeded_book_dir: Path, epub_v2: Path, books_dir: Path, snapshot, monkeypatch
):
    """L4 / S1 - today's open(..., 'wb') truncates the good pkl before writing."""
    out = seeded_book_dir
    v2_book = process_epub(str(epub_v2), str(books_dir / "other_data"))
    pkl_before = snapshot(out)["book.pkl"]

    def denied(*_a, **_kw):
        raise OSError(errno.ENOSPC, "no space left on device")

    monkeypatch.setattr(reader3.pickle, "dump", denied)
    with pytest.raises(OSError):
        save_to_pickle(v2_book, str(out))
    monkeypatch.undo()

    assert snapshot(out)["book.pkl"] == pkl_before
    assert sorted(glob.glob(str(out / "book.pkl*"))) == [str(out / "book.pkl")]
    assert MARKER_V1 in joined_text(load_pkl(out))


def test_no_reader_observes_a_partial_pkl_during_save(
    seeded_book_dir: Path, epub_v2: Path, books_dir: Path, monkeypatch
):
    """L4 / S6 - the old, complete book stays visible for the whole write."""
    out = seeded_book_dir
    v2_book = process_epub(str(epub_v2), str(books_dir / "other_data"))

    observations = []
    replaced = {"done": False}
    real_dump = pickle.dump
    real_fsync = os.fsync
    real_replace = os.replace

    def observe(stage):
        if replaced["done"]:
            return
        with open(out / "book.pkl", "rb") as f:
            observations.append((stage, joined_text(pickle.load(f))))

    def probing_dump(obj, f, *a, **kw):
        observe("before-dump")
        return real_dump(obj, f, *a, **kw)

    def probing_fsync(fd):
        observe("at-fsync")
        return real_fsync(fd)

    def probing_replace(src, dst, *a, **kw):
        result = real_replace(src, dst, *a, **kw)
        if str(dst).endswith("book.pkl"):
            replaced["done"] = True
        return result

    monkeypatch.setattr(reader3.pickle, "dump", probing_dump)
    monkeypatch.setattr(reader3.os, "fsync", probing_fsync)
    monkeypatch.setattr(reader3.os, "replace", probing_replace)

    save_to_pickle(v2_book, str(out))
    monkeypatch.undo()

    assert observations, "no observation was taken during the write"
    for stage, text in observations:
        assert MARKER_V1 in text, f"a partial or new book was visible at {stage}"
    assert MARKER_V2 in joined_text(load_pkl(out))
    assert not (out / "book.pkl.tmp").exists()


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_committed_pkl_round_trips_to_same_spine_ids_and_order(
    version, books_dir: Path, epub_v1: Path, epub_v2: Path
):
    """L2 / S2 - the committed marker loads with the shape existing readers use."""
    src = epub_v1 if version == "v1" else epub_v2
    out = books_dir / "sample_data"
    book = process_epub(str(src), str(out))

    loaded = load_pkl(out)

    assert isinstance(loaded, Book)
    assert [c.id for c in loaded.spine] == [c.id for c in book.spine]
    # `order` is the raw index into the EPUB spine, not a renumbering: assert it
    # round-trips unchanged and stays monotonic, never that it equals range(n).
    orders = [c.order for c in loaded.spine]
    assert orders == [c.order for c in book.spine]
    assert all(b > a for a, b in zip(orders, orders[1:])), orders
    assert loaded.images == book.images
    assert [t.href for t in loaded.toc] == [t.href for t in book.toc]
    assert loaded.metadata == book.metadata


def test_main_preserves_user_paths_and_refreshes_artifacts(
    seeded_book_dir: Path, books_dir: Path, epub_v2: Path, tmp_path: Path, snapshot,
    monkeypatch, capsys
):
    """L3 / S1 - the real CLI entry point over a populated book directory."""
    out = seeded_book_dir
    source = tmp_path / "sample.epub"
    shutil.copy2(epub_v2, source)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))
    monkeypatch.chdir(tmp_path)
    before = user_subset(snapshot(out))

    rc = reader3.main([str(source)])
    printed = capsys.readouterr().out

    assert rc == 0
    assert user_subset(snapshot(out)) == before
    assert sha256_of(out / "book.epub") == sha256_of(epub_v2)
    assert MARKER_V2 in joined_text(load_pkl(out))
    assert "Physical Files (Spine): 4" in printed
    assert "TOC Root Items: 3" in printed
    assert "Images extracted: 4" in printed  # 2 images x (full name + basename)


def test_main_publishes_book_pkl_exactly_once(
    seeded_book_dir: Path, books_dir: Path, epub_v2: Path, tmp_path: Path, snapshot,
    monkeypatch
):
    """L4 / S1 - readers see exactly one flip of the marker per run.

    The identity recorded is the full ``(sha256, size, mtime_ns, inode)`` tuple,
    not just the inode: an in-place truncating rewrite after the replace would
    keep the inode and slip past an inode-only check.
    """
    out = seeded_book_dir
    source = tmp_path / "sample.epub"
    shutil.copy2(epub_v2, source)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))
    monkeypatch.chdir(tmp_path)

    old_pkl = snapshot(out)["book.pkl"]
    real_replace = os.replace
    marker_commits = []

    def recording_replace(src, dst, *a, **kw):
        result = real_replace(src, dst, *a, **kw)
        if str(dst) == str(out / "book.pkl"):
            marker_commits.append(snapshot(out)["book.pkl"])
        return result

    monkeypatch.setattr(reader3.os, "replace", recording_replace)
    assert reader3.main([str(source)]) == 0
    monkeypatch.undo()

    assert len(marker_commits) == 1, f"marker flipped {len(marker_commits)} times"
    # The bytes published by that single replace are the bytes readers end up with:
    # nothing rewrote book.pkl afterwards, in place or otherwise.
    assert snapshot(out)["book.pkl"] == marker_commits[0]
    assert marker_commits[0] != old_pkl
    assert MARKER_V2 in joined_text(load_pkl(out))
    assert not (out / "book.pkl.tmp").exists()


@pytest.mark.parametrize(
    "argv,message",
    [([], "Usage: reader3"), (["definitely-not-here.epub"], "File not found.")],
)
def test_main_refuses_bad_input_before_creating_anything(
    argv, message, books_dir: Path, tmp_path: Path, monkeypatch
):
    """L2 / S1 - the CLI's two refusal paths must refuse, not half-run."""
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as ei:
        reader3.main(argv)

    assert message in str(ei.value)
    assert sorted(os.listdir(books_dir)) == []
    assert glob.glob(str(books_dir / "*.staging-*")) == []


def test_main_writes_nothing_outside_books_dir(
    books_dir: Path, epub_v2: Path, tmp_path: Path, repo_root: Path, snapshot, monkeypatch
):
    """L3 / S1 - staging stays beside the book; nothing leaks into cwd or the real library."""
    source = tmp_path / "sample.epub"
    shutil.copy2(epub_v2, source)
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))
    monkeypatch.chdir(tmp_path)

    def outside(snap):
        return {k: v for k, v in snap.items() if not k.startswith("books/")}

    # The real library is not re-checked here: the autouse fence in
    # tests/unit/conftest.py already compares it recursively around every test,
    # and a top-level listdir + mtime pair reads as protection while being blind
    # to exactly the intra-directory damage this feature exists to prevent.
    before = outside(snapshot(tmp_path))

    assert reader3.main([str(source)]) == 0

    assert outside(snapshot(tmp_path)) == before
    assert glob.glob(str(books_dir / "*.staging-*")) == []
    assert staging_leftovers(books_dir / "sample_data") == []
