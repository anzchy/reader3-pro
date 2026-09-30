"""WI-3: read-back validation, then an ordered atomic commit with book.pkl last.

Law (all-or-nothing, marker last): the visible ``book.pkl`` always unpickles to a
complete ``Book``; it is the last path in ``output_dir`` to change; a validation
failure leaves ``output_dir`` as the identity; a crash after the artifacts but
before the marker still leaves the old marker loadable and a clean re-run
converges.
"""

from __future__ import annotations

import copy
import errno
import fcntl
import os
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bookdir import make_seeded_book_dir, seed_user_files, staging_leftovers, user_subset
from epub_builder import IMAGE_BYTES_V2, MARKER_V1, MARKER_V2, sha256_of
from reader3_app import reader3
from reader3_app.ai.books import ensure_book_uuid
from reader3_app.reader3 import Book, process_epub


def load_pkl(out: Path) -> Book:
    with open(out / "book.pkl", "rb") as f:
        return pickle.load(f)


def marker_of(book: Book) -> str:
    joined = " ".join(c.text for c in book.spine)
    assert MARKER_V1 in joined or MARKER_V2 in joined
    return MARKER_V2 if MARKER_V2 in joined else MARKER_V1


def assert_consistent(out: Path, epub_v1: Path, epub_v2: Path, context: str = "") -> str:
    """The visible book.pkl must agree with the artifacts committed beside it.

    "The old marker is still loadable" is a weaker property than "the old book
    is intact", and the gap between them is exactly what marker-last ordering
    exists to close: a directory holding v1's pickle next to v2's EPUB and
    images renders text that disagrees with the EPUB and 404s on every image
    the old pickle references. Whichever version is visible, it must be
    visible in all three artifacts at once.
    """
    book = load_pkl(out)
    marker = marker_of(book)
    for rel in set(book.images.values()):
        assert (out / rel).is_file(), (
            f"{context}: visible book.pkl references a missing image {rel}"
        )
    expected_epub = epub_v1 if marker == MARKER_V1 else epub_v2
    assert sha256_of(out / "book.epub") == sha256_of(expected_epub), (
        f"{context}: book.pkl says {marker} but book.epub is the other version"
    )
    committed_images = sorted(os.listdir(out / "images"))
    assert committed_images == sorted({Path(v).name for v in book.images.values()}), (
        f"{context}: images/ holds {committed_images}, not what book.pkl declares"
    )
    return marker


class ReplaceRecorder:
    """Wraps ``os.replace``: records every (src, dst) and can fail on demand."""

    def __init__(self, fail_on_nth=None, fail_when_dst_endswith=None):
        self.calls = []
        self.real = os.replace
        self.fail_on_nth = fail_on_nth
        self.fail_when_dst_endswith = fail_when_dst_endswith

    def __call__(self, src, dst, *a, **kw):
        self.calls.append((str(src), str(dst)))
        n = len(self.calls)
        if self.fail_when_dst_endswith and str(dst).endswith(self.fail_when_dst_endswith):
            raise OSError(errno.EIO, "injected I/O error")
        if self.fail_on_nth is not None and n == self.fail_on_nth:
            raise OSError(errno.EIO, "injected I/O error")
        return self.real(src, dst, *a, **kw)


def test_reprocess_v1_to_v2_refreshes_epub_images_and_spine_text(
    seeded_book_dir: Path, epub_v2: Path
):
    """L3 / S2 - preserving user data must not degrade into changing nothing."""
    out = seeded_book_dir
    returned = process_epub(str(epub_v2), str(out))

    assert sha256_of(out / "book.epub") == sha256_of(epub_v2)
    assert (out / "images" / "cover.png").read_bytes() == IMAGE_BYTES_V2

    for book in (returned, load_pkl(out)):
        joined = " ".join(c.text for c in book.spine)
        assert MARKER_V2 in joined
        assert MARKER_V1 not in joined


def test_book_uuid_is_identical_before_and_after_reprocess(
    seeded_book_dir: Path, books_dir: Path, epub_v2: Path, snapshot
):
    """L2 + L3 / S1 - the UUID survives because the file is never touched."""
    out = seeded_book_dir
    uuid_before = ensure_book_uuid(str(books_dir), "sample_data")
    meta_before = snapshot(out)["ai_meta.json"]

    process_epub(str(epub_v2), str(out))

    assert ensure_book_uuid(str(books_dir), "sample_data") == uuid_before
    assert snapshot(out)["ai_meta.json"] == meta_before
    assert not (out / "ai_meta.json.tmp").exists()


def test_book_pkl_is_the_last_path_committed(seeded_book_dir: Path, epub_v2: Path, monkeypatch):
    """L4 / S1 - the ordering invariant that makes every crash point benign."""
    out = seeded_book_dir
    rec = ReplaceRecorder()
    monkeypatch.setattr(reader3.os, "replace", rec)

    process_epub(str(epub_v2), str(out))

    committed = [dst for _, dst in rec.calls if Path(dst).parent == out]
    assert committed, "nothing was committed into the output directory"
    assert Path(committed[-1]).name == "book.pkl"
    assert committed.count(str(out / "book.pkl")) == 1
    assert str(out / "book.epub") in committed[:-1]
    assert str(out / "images") in committed[:-1]


@pytest.mark.parametrize(
    "corruption",
    [
        "truncated_pkl",
        "not_a_book",
        "truncated_epub",
        "missing_epub",
        "truncated_image",
        "missing_image",
    ],
)
def test_validation_failure_leaves_output_dir_untouched(
    corruption, seeded_book_dir: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S3 - silent corruption must be caught by read-back, before any swap.

    Every artifact the commit publishes is covered, images included: a
    validation step that only reads back ``book.pkl`` and ``book.epub`` happily
    publishes a book whose images are truncated or absent.
    """
    out = seeded_book_dir
    before = snapshot(out)

    if corruption == "truncated_pkl":
        # No exception raised: only a genuine read-back check can catch this.
        def truncating_dump(obj, f, *a, **kw):
            f.write(pickle.dumps(obj)[:64])

        monkeypatch.setattr(reader3.pickle, "dump", truncating_dump)
        offender = "book.pkl"
    elif corruption == "not_a_book":
        # A perfectly valid pickle of the wrong type: unpickling succeeds, so
        # only a type check catches it.
        def wrong_type_dump(obj, f, *a, **kw):
            f.write(pickle.dumps({"spine": ["looks", "plausible"]}))

        monkeypatch.setattr(reader3.pickle, "dump", wrong_type_dump)
        offender = "book.pkl"
    elif corruption == "truncated_epub":
        import shutil as _shutil

        real_copy2 = _shutil.copy2

        def truncating_copy2(src, dst, *a, **kw):
            result = real_copy2(src, dst, *a, **kw)
            os.truncate(dst, 32)
            return result

        monkeypatch.setattr(reader3.shutil, "copy2", truncating_copy2)
        offender = "book.epub"
    else:
        # Damage a staged artifact after it is written but before validation
        # runs. pickle.dump is the last staged write, a real seam in between.
        real_dump = pickle.dump
        relative = "book.epub" if corruption == "missing_epub" else "images/cover.png"

        def damaging_dump(obj, f, *a, **kw):
            victim = Path(f.name).parent / relative
            assert victim.exists(), f"expected a staged {relative} beside {f.name}"
            if corruption == "truncated_image":
                os.truncate(victim, 3)
            else:
                os.unlink(victim)
            return real_dump(obj, f, *a, **kw)

        monkeypatch.setattr(reader3.pickle, "dump", damaging_dump)
        offender = os.path.basename(relative)

    with pytest.raises(reader3.ArtifactValidationError) as ei:
        process_epub(str(epub_v2), str(out))

    assert offender in str(ei.value)
    assert snapshot(out) == before
    assert staging_leftovers(out) == []
    assert marker_of(load_pkl(out)) == MARKER_V1


class FsyncRecorder:
    """Wraps ``os.fsync``: counts calls and can fail on the nth."""

    def __init__(self, fail_on_nth=None):
        self.count = 0
        self.real = os.fsync
        self.fail_on_nth = fail_on_nth

    def __call__(self, fd):
        self.count += 1
        if self.fail_on_nth is not None and self.count == self.fail_on_nth:
            raise OSError(errno.ENOSPC, "no space left on device")
        return self.real(fd)


def test_a_failed_fsync_at_any_durability_point_leaves_a_consistent_book(
    books_dir: Path, epub_v1: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S5 - bounded-exhaustive sweep over every os.fsync failure point.

    K is measured, never hardcoded. Hardcoding it to the staged-write fsyncs
    would only ever exercise the phase where nothing has been committed yet and
    rollback is trivially correct; the interesting points are the two directory
    fsyncs inside the commit, on either side of the marker.
    """
    probe_out = make_seeded_book_dir(books_dir, epub_v1, name="fprobe_data")
    probe = FsyncRecorder()
    monkeypatch.setattr(reader3.os, "fsync", probe)
    process_epub(str(epub_v2), str(probe_out))
    monkeypatch.undo()
    k = probe.count
    assert k >= 5, f"expected fsyncs for epub, images, pkl and both dirs, saw {k}"

    for n in range(1, k + 1):
        out = make_seeded_book_dir(books_dir, epub_v1, name=f"fsweep{n}_data")
        before = user_subset(snapshot(out))
        full_before = snapshot(out)

        monkeypatch.setattr(reader3.os, "fsync", FsyncRecorder(fail_on_nth=n))
        with pytest.raises(OSError):
            process_epub(str(epub_v2), str(out))
        monkeypatch.undo()

        assert user_subset(snapshot(out)) == before, f"user data changed at fsync {n}"
        assert staging_leftovers(out) == [], f"staging left behind at fsync {n}"
        marker = assert_consistent(out, epub_v1, epub_v2, context=f"fsync {n}")

        if marker == MARKER_V1:
            # Nothing was published, so the directory must be the identity.
            assert snapshot(out) == full_before, f"a rolled-back run mutated out at fsync {n}"

        process_epub(str(epub_v2), str(out))
        assert_consistent(out, epub_v1, epub_v2, context=f"re-run after fsync {n}")
        assert marker_of(load_pkl(out)) == MARKER_V2, f"re-run did not converge after {n}"
        assert user_subset(snapshot(out)) == before


def test_crash_before_marker_keeps_old_pkl_loadable_and_rerun_converges(
    seeded_book_dir: Path, epub_v1: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S1 - the marker is the commit point; a crash before it is recoverable."""
    out = seeded_book_dir
    user_before = user_subset(snapshot(out))

    rec = ReplaceRecorder(fail_when_dst_endswith="book.pkl")
    monkeypatch.setattr(reader3.os, "replace", rec)

    with pytest.raises(OSError):
        process_epub(str(epub_v2), str(out))

    assert marker_of(load_pkl(out)) == MARKER_V1
    # The old marker being loadable is not enough: the whole old book must
    # still be there, EPUB and images included.
    assert assert_consistent(out, epub_v1, epub_v2, context="crash before marker") == MARKER_V1
    assert user_subset(snapshot(out)) == user_before
    assert staging_leftovers(out) == []

    monkeypatch.undo()
    process_epub(str(epub_v2), str(out))

    assert_consistent(out, epub_v1, epub_v2, context="after re-run")
    assert marker_of(load_pkl(out)) == MARKER_V2
    assert sha256_of(out / "book.epub") == sha256_of(epub_v2)
    assert user_subset(snapshot(out)) == user_before
    assert staging_leftovers(out) == []
    assert [p for p in snapshot(out) if p.endswith(".tmp")] == []


def test_user_data_and_marker_survive_every_replace_crash_point(
    books_dir: Path, epub_v1: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S5 - bounded-exhaustive sweep over every os.replace crash point.

    K is measured by a recording pass, never hardcoded: a future implementation
    with more commit steps automatically gets more crash points.
    """
    probe_out = make_seeded_book_dir(books_dir, epub_v1, name="probe_data")
    probe = ReplaceRecorder()
    monkeypatch.setattr(reader3.os, "replace", probe)
    process_epub(str(epub_v2), str(probe_out))
    monkeypatch.undo()
    k = len(probe.calls)
    assert k >= 3, f"expected at least epub/images/pkl replaces, saw {probe.calls}"

    for n in range(1, k + 1):
        out = make_seeded_book_dir(books_dir, epub_v1, name=f"sweep{n}_data")
        before = user_subset(snapshot(out))

        rec = ReplaceRecorder(fail_on_nth=n)
        monkeypatch.setattr(reader3.os, "replace", rec)
        with pytest.raises(OSError):
            process_epub(str(epub_v2), str(out))
        monkeypatch.undo()

        assert user_subset(snapshot(out)) == before, f"user data changed at crash point {n}"
        book = load_pkl(out)
        assert isinstance(book, Book)
        assert book.spine
        assert staging_leftovers(out) == [], f"staging left behind at crash point {n}"
        # Loadable is not enough - the marker and the artifacts beside it must
        # describe the same version of the book.
        assert_consistent(out, epub_v1, epub_v2, context=f"crash point {n}")

        process_epub(str(epub_v2), str(out))
        assert_consistent(out, epub_v1, epub_v2, context=f"re-run after crash point {n}")
        assert marker_of(load_pkl(out)) == MARKER_V2, f"re-run did not converge after {n}"
        assert user_subset(snapshot(out)) == before


def make_shape(shape: str, books_dir: Path, epub_v1: Path, name: str) -> Path:
    """Build a book directory in one of the four states a commit can start from."""
    out = books_dir / name
    if shape == "absent":
        return out
    if shape == "user_only":
        out.mkdir(parents=True)
        seed_user_files(out)
        return out
    out = make_seeded_book_dir(books_dir, epub_v1, name=name)
    if shape == "missing_epub":
        (out / "book.epub").unlink()
    elif shape == "missing_images":
        shutil.rmtree(out / "images")
    return out


@pytest.mark.parametrize("shape", ["absent", "user_only", "missing_epub", "missing_images"])
def test_a_failed_commit_is_the_identity_even_when_an_artifact_was_absent(
    shape, books_dir: Path, epub_v1: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S5 - rollback must remove what it added, not only restore what it moved.

    Recording an undo entry only for artifacts that already existed makes the
    rollback asymmetric, and the asymmetry is reachable: a commit interrupted
    while ``book.epub`` was absent leaves the new one sitting beside the old
    ``book.pkl`` - the half-published mixture again, in a narrower doorway. With
    no marker at all it leaves a stray artifact that no later run ever
    validates. Either way the failed run must be the identity on its own
    directory, not only on the user's files.
    """
    probe_out = make_shape(shape, books_dir, epub_v1, f"{shape}_probe_data")
    probe = ReplaceRecorder()
    monkeypatch.setattr(reader3.os, "replace", probe)
    process_epub(str(epub_v2), str(probe_out))
    monkeypatch.undo()
    k = len(probe.calls)
    assert k >= 3, f"{shape}: expected at least epub/images/pkl replaces, saw {probe.calls}"

    for n in range(1, k + 1):
        out = make_shape(shape, books_dir, epub_v1, f"{shape}_n{n}_data")
        full_before = snapshot(out)

        monkeypatch.setattr(reader3.os, "replace", ReplaceRecorder(fail_on_nth=n))
        with pytest.raises(OSError):
            process_epub(str(epub_v2), str(out))
        monkeypatch.undo()

        assert staging_leftovers(out) == [], f"{shape}: staging left behind at point {n}"
        after = snapshot(out)
        if (out / "book.pkl").is_file() and marker_of(load_pkl(out)) == MARKER_V2:
            # The marker landed, so the transaction is over: the whole new book
            # must be visible and coherent.
            assert_consistent(out, epub_v1, epub_v2, context=f"{shape} point {n}")
        else:
            assert after == full_before, (
                f"{shape}: the rolled-back run at point {n} did not restore the "
                f"directory - added {sorted(set(after) - set(full_before))}, "
                f"lost {sorted(set(full_before) - set(after))}"
            )

        process_epub(str(epub_v2), str(out))
        assert_consistent(out, epub_v1, epub_v2, context=f"{shape} re-run after {n}")


def test_an_unrepairable_commit_failure_is_reported_and_does_not_mask_its_cause(
    seeded_book_dir: Path, epub_v2: Path, monkeypatch, capsys
):
    """L4 / S3 - the one outcome the commit cannot repair must not be silent.

    Swallowing the restore error keeps the original exception intact, which is
    right, but on its own it hides the only case where the directory really is
    left inconsistent. The operator has to be told which paths to look at; a run
    that reports "no space left on device" and nothing else gives them no reason
    to suspect the book is broken.

    The assertion deliberately looks for a multi-word phrase on stderr rather
    than a keyword: pytest names its tmp directory after the test function, so
    every path this run prints already contains the test's own vocabulary, and a
    single-word check would pass against the directory name alone.
    """
    out = seeded_book_dir
    real_replace = os.replace

    def replace_that_fails_the_commit_and_its_undo(src, dst, *a, **kw):
        # Fail publishing the new images/, then fail putting the old one back.
        if str(dst) == str(out / "images"):
            raise OSError(errno.ENOSPC, "no space left on device")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(reader3.os, "replace", replace_that_fails_the_commit_and_its_undo)

    with pytest.raises(OSError) as ei:
        process_epub(str(epub_v2), str(out))
    monkeypatch.undo()

    assert ei.value.errno == errno.ENOSPC, "the failed undo must not mask the real cause"
    err = capsys.readouterr().err
    assert "could not restore" in err, f"a failed rollback was not reported; stderr was {err!r}"
    assert str(out / "images") in err, f"the report does not name the path; stderr was {err!r}"


def a_reaped_pid() -> int:
    """A pid belonging to a process that has certainly exited and been reaped.

    Deliberately not a large constant: ``pid_max`` is 99998 on macOS but can be
    raised to 4194304 on Linux, so "999999 can never exist" is a host-specific
    assumption, and a test whose premise silently stops holding on CI is worse
    than no test.
    """
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


def test_orphan_staging_dir_is_cleared_and_run_succeeds(
    seeded_book_dir: Path, epub_v2: Path, snapshot
):
    """L3 / S2 - leftovers from a crashed run must not break or pollute the next one."""
    out = seeded_book_dir
    user_before = user_subset(snapshot(out))

    foreign = Path(f"{out}.staging-{a_reaped_pid()}")
    (foreign / "images").mkdir(parents=True)
    (foreign / "junk.bin").write_bytes(os.urandom(2048))
    same_pid = Path(f"{out}.staging-{os.getpid()}")
    (same_pid / "images").mkdir(parents=True)
    (same_pid / "images" / "stale.png").write_bytes(b"stale")

    process_epub(str(epub_v2), str(out))

    assert staging_leftovers(out) == []
    assert sorted(os.listdir(out / "images")) == ["cover.png", "new_plate.png"]
    assert marker_of(load_pkl(out)) == MARKER_V2
    assert user_subset(snapshot(out)) == user_before


def test_a_live_concurrent_run_is_refused_not_trampled(
    seeded_book_dir: Path, epub_v2: Path, snapshot
):
    """L4 / S3 - cleanup must not delete a staging directory still being written.

    Liveness is proved by a lock the owner still holds, not by the pid in the
    directory name: ``flock`` is released by the kernel when the owner dies, so
    it cannot go stale, whereas a pid can be recycled onto an unrelated process.
    """
    out = seeded_book_dir
    before = snapshot(out)

    rival = Path(f"{out}.staging-{a_reaped_pid()}")
    (rival / "images").mkdir(parents=True)
    (rival / "book.epub").write_bytes(b"a rival run is mid-build")
    # A different open file description, so flock conflicts even in-process.
    lock_fd = os.open(rival / reader3._LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(RuntimeError, match="already processing"):
            process_epub(str(epub_v2), str(out))

        assert (rival / "book.epub").read_bytes() == b"a rival run is mid-build"
        assert snapshot(out) == before
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        shutil.rmtree(rival)


def test_a_dead_runs_staging_dir_is_cleared_even_if_its_pid_was_recycled(
    seeded_book_dir: Path, epub_v2: Path, snapshot
):
    """L4 / S3 - a stale lock must never become a permanent refusal.

    Inferring liveness from the pid in the name turns a SIGKILLed run into a
    book that can never be reprocessed again: once the OS recycles that pid onto
    any unrelated process, every future run refuses. The lock is the authority,
    and nobody holds this one.
    """
    out = seeded_book_dir
    user_before = user_subset(snapshot(out))

    # A pid that is alive and has nothing to do with this book - which is
    # precisely what a recycled pid looks like from the outside.
    recycled = Path(f"{out}.staging-{os.getppid()}")
    (recycled / "images").mkdir(parents=True)
    (recycled / reader3._LOCK_NAME).touch()
    (recycled / "junk.bin").write_bytes(b"debris from a killed run")

    process_epub(str(epub_v2), str(out))

    assert staging_leftovers(out) == []
    assert marker_of(load_pkl(out)) == MARKER_V2
    assert user_subset(snapshot(out)) == user_before


def test_first_run_creates_complete_directory_when_output_dir_absent(
    books_dir: Path, epub_v1: Path, snapshot
):
    """L3 / S1 - the existing-directory logic must not break a brand new book."""
    out = books_dir / "sample_data"
    assert not out.exists()

    process_epub(str(epub_v1), str(out))

    assert sorted(snapshot(out)) == [
        "book.epub",
        "book.pkl",
        "images/",
        "images/cover.png",
        "images/oldplate.png",
    ]
    assert sha256_of(out / "book.epub") == sha256_of(epub_v1)
    loaded = load_pkl(out)
    assert len(loaded.spine) == 3
    # `order` is the raw EPUB spine index; only require it to be monotonic.
    orders = [c.order for c in loaded.spine]
    assert all(b > a for a, b in zip(orders, orders[1:])), orders
    # 018 WI-2 amendment: `.locks/` is the book-lock dir (ADR-0015 contract item 1), not a book.
    assert sorted(n for n in os.listdir(books_dir) if n != ".locks") == ["sample_data"]


def test_zero_chapter_book_fails_validation_and_leaves_prior_book_intact(
    seeded_book_dir: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S3 - an empty spine is corruption, not a valid book to publish.

    Without this, a parser regression that yields zero chapters commits a
    technically-well-formed but useless ``book.pkl`` over a good one.
    """
    out = seeded_book_dir
    before = snapshot(out)

    # A real seam: the parsed EPUB declares no spine at all, so the chapter loop
    # produces nothing. Everything else (metadata, images, TOC) still succeeds.
    real_read_epub = reader3.epub.read_epub

    def spineless_read_epub(path, *a, **kw):
        parsed = real_read_epub(path, *a, **kw)
        parsed.spine = []
        return parsed

    monkeypatch.setattr(reader3.epub, "read_epub", spineless_read_epub)

    with pytest.raises(ValueError, match="spine"):
        process_epub(str(epub_v2), str(out))

    assert snapshot(out) == before
    assert staging_leftovers(out) == []
    assert marker_of(load_pkl(out)) == MARKER_V1


def test_marker_referencing_an_unstaged_image_fails_validation(
    seeded_book_dir: Path, epub_v2: Path, snapshot, monkeypatch
):
    """L4 / S3 - the marker may not promise an image the commit will not deliver.

    This is the guard against a divergence between ``Book.images`` and what the
    filename sanitiser actually wrote (a collision, say). Without it the commit
    publishes a book whose images 404.
    """
    out = seeded_book_dir
    before = snapshot(out)
    real_dump = pickle.dump

    def dump_with_a_phantom_image(obj, f, *a, **kw):
        clone = copy.copy(obj)
        clone.images = {**obj.images, "phantom.png": "images/phantom.png"}
        return real_dump(clone, f, *a, **kw)

    monkeypatch.setattr(reader3.pickle, "dump", dump_with_a_phantom_image)

    with pytest.raises(reader3.ArtifactValidationError, match="phantom.png"):
        process_epub(str(epub_v2), str(out))

    assert snapshot(out) == before
    assert staging_leftovers(out) == []


@pytest.mark.parametrize("phase", ["first_run", "reprocess", "images_to_none"])
def test_epub_with_no_images_commits_and_reprocesses(
    phase, books_dir: Path, epub_v1: Path, epub_imageless: Path, snapshot
):
    """L3 / S3 - a plain-text book has an empty images/ dir, and still commits.

    The commit must not depend on a staged ``images/`` having contents; an
    implementation that only swaps a non-empty directory strands this case
    half-committed.
    """
    if phase == "first_run":
        out = books_dir / "plain_data"
        process_epub(str(epub_imageless), str(out))
    elif phase == "reprocess":
        out = books_dir / "plain_data"
        process_epub(str(epub_imageless), str(out))
        process_epub(str(epub_imageless), str(out))
    else:
        out = make_seeded_book_dir(books_dir, epub_v1, name="plain_data")
        user_before = user_subset(snapshot(out))
        process_epub(str(epub_imageless), str(out))
        assert user_subset(snapshot(out)) == user_before

    assert (out / "images").is_dir()
    assert os.listdir(out / "images") == []
    book = load_pkl(out)
    assert book.images == {}
    assert marker_of(book) == MARKER_V2
    assert sha256_of(out / "book.epub") == sha256_of(epub_imageless)
    assert staging_leftovers(out) == []
