"""018 WI-2 — ``process_epub`` takes EX; ``reader3 --index`` takes SH.

Cases W2-41..W2-45, W2-52 and W2-55 of ``.claude/tdd-guardian/tests-20260930-111748.md``.

Law:
  * at most one import runs per book;
  * EX is held from before any staging or output dir is touched until after the
    publish renames complete;
  * a refused import touches nothing, fresh book or existing;
  * the CLI and HTTP reindex share one lock, and a CLI refusal exits non-zero naming
    the holder (no traceback).
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

import pytest

from book_lock_workers import (
    CHILD_TIMEOUT_S,
    CHILD_WAIT_S,
    Child,
    Holder,
    outcome,
    process_epub_paused,
    process_epub_paused_at_publish,
    process_epub_run,
    spawn_ctx,
    try_exclusive,
)
from epub_builder import snapshot_tree
from reader3_app import book_lock, notes_service, reader3
from reader3_app.models.annotations import Annotation

BOOK = "x_data"
V1_TITLE = "Version One Book"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _stagings(books: Path) -> list:
    return sorted(p for p in os.listdir(books) if p.startswith(f"{BOOK}.staging"))


def _load(book_dir: Path):
    with open(book_dir / "book.pkl", "rb") as f:
        return pickle.load(f)


@pytest.fixture
def published(books_dir: Path, epub_v1: Path) -> Path:
    reader3.process_epub(str(epub_v1), str(books_dir / BOOK))
    return books_dir / BOOK


# --------------------------------------------------------------------------- process_epub


def test_w2_43_concurrent_imports_of_one_book_have_exactly_one_winner(
    books_dir: Path, tmp_path: Path, epub_v1: Path
) -> None:
    out = str(books_dir / BOOK)
    ctx = spawn_ctx()
    paused, go = ctx.Event(), ctx.Event()
    p1 = str(tmp_path / "import-1.json")
    c1 = Child(process_epub_paused, (str(epub_v1), out, paused, go, p1), p1).start()
    try:
        assert paused.wait(CHILD_WAIT_S), f"child 1 never reached the build step (exitcode={c1.proc.exitcode})"
        p2 = str(tmp_path / "import-2.json")
        c2 = Child(process_epub_run, (str(epub_v1), out, p2), p2).start()
        r2 = c2.wait_result(CHILD_WAIT_S)
        code2 = c2.reap(CHILD_TIMEOUT_S)
        stagings_at_refusal = _stagings(books_dir)
    finally:
        go.set()
    r1 = c1.wait_result(CHILD_WAIT_S)
    code1 = c1.reap(CHILD_TIMEOUT_S)

    assert outcome(r2) == "busy:import", r2
    assert r2["type"] == "BookLockBusy"
    assert outcome(r1) == "acquired", r1
    assert r1["title"] == V1_TITLE
    assert _load(books_dir / BOOK).metadata.title == V1_TITLE
    assert len(stagings_at_refusal) == 1, stagings_at_refusal
    assert _stagings(books_dir) == []
    assert (code1, code2) == (0, 0)


def test_w2_52_ex_is_held_through_the_publish_step(books_dir: Path, tmp_path: Path, epub_v1: Path) -> None:
    out = str(books_dir / BOOK)
    ctx = spawn_ctx()
    publishing, go = ctx.Event(), ctx.Event()
    p1 = str(tmp_path / "import.json")
    c1 = Child(process_epub_paused_at_publish, (str(epub_v1), out, publishing, go, p1), p1).start()
    try:
        assert publishing.wait(CHILD_WAIT_S), f"child 1 never reached publish (exitcode={c1.proc.exitcode})"
        p2 = str(tmp_path / "delete.json")
        c2 = Child(try_exclusive, (str(books_dir), BOOK, "delete", p2), p2).start()
        r2 = c2.wait_result(CHILD_WAIT_S)
        code2 = c2.reap(CHILD_TIMEOUT_S)

        err = None
        try:
            notes_service.add_annotation_and_version(
                str(books_dir),
                Annotation(book_id=BOOK, chapter_index=0, quote="Q"),
                deadline=book_lock._monotonic() + 0.3,
            )
        except book_lock.BookLockBusy as exc:
            err = exc
    finally:
        go.set()
    r1 = c1.wait_result(CHILD_WAIT_S)
    code1 = c1.reap(CHILD_TIMEOUT_S)

    assert outcome(r2) == "busy:import", r2
    assert err is not None, "a notes writer got in during publish"
    assert err.holder_category == "import"
    assert outcome(r1) == "acquired", r1
    assert _load(books_dir / BOOK).metadata.title == V1_TITLE
    assert not (books_dir / BOOK / notes_service.NOTES_FILENAME).exists()
    assert (code1, code2) == (0, 0)


def test_w2_44_import_refused_by_a_shared_holder_leaves_the_book_byte_identical(
    published: Path, books_dir: Path, tmp_path: Path, epub_v1: Path
) -> None:
    h0 = snapshot_tree(published)
    with Holder(str(books_dir), BOOK, "shared", "reindex", str(tmp_path)):
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            reader3.process_epub(str(epub_v1), str(published))
        elapsed = time.monotonic() - t0
    assert info.value.holder_category == "reindex"
    assert elapsed < 0.25
    assert snapshot_tree(published) == h0
    assert _stagings(books_dir) == []


def test_w2_55_a_refused_fresh_import_leaves_no_directory(books_dir: Path, tmp_path: Path, epub_v1: Path) -> None:
    (books_dir / ".locks").mkdir()
    holder = Holder(str(books_dir), BOOK, "exclusive", "delete", str(tmp_path)).start()
    try:
        t0 = time.monotonic()
        with pytest.raises(book_lock.BookLockBusy) as info:
            reader3.process_epub(str(epub_v1), str(books_dir / BOOK))
        elapsed = time.monotonic() - t0
        listing = sorted(os.listdir(books_dir))
    finally:
        code = holder.release()
    assert info.value.holder_category == "delete"
    assert elapsed < 0.25
    assert listing == [".locks"]
    assert code == 0


def test_w2_45_a_fresh_import_creates_the_book_and_the_lock_persists(
    books_dir: Path, tmp_path: Path, epub_v1: Path
) -> None:
    reader3.process_epub(str(epub_v1), str(books_dir / BOOK))
    assert _load(books_dir / BOOK).metadata.title == V1_TITLE
    assert (books_dir / ".locks" / f"{BOOK}.lock").exists()

    path = str(tmp_path / "after.json")
    child = Child(try_exclusive, (str(books_dir), BOOK, "delete", path), path).start()
    got = child.wait_result(CHILD_WAIT_S)
    assert child.reap(CHILD_TIMEOUT_S) == 0
    assert outcome(got) == "acquired", got


# --------------------------------------------------------------------------- CLI --index


def test_w2_41_cli_index_refused_exits_nonzero_naming_the_holder(
    published: Path, books_dir: Path, tmp_path: Path
) -> None:
    env = dict(os.environ)
    env["READER3_BOOKS_DIR"] = str(books_dir)
    env["ANONYMIZED_TELEMETRY"] = "False"
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        proc = subprocess.run(
            [sys.executable, "-m", "reader3_app.reader3", "--index", BOOK],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    assert proc.returncode != 0, proc.stdout
    assert "import" in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    assert not (published / "chroma_db").exists()


def test_w2_42_in_process_cli_index_refused_is_a_systemexit_naming_the_holder(
    published: Path, books_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("READER3_BOOKS_DIR", str(books_dir))
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    with Holder(str(books_dir), BOOK, "exclusive", "import", str(tmp_path)):
        with pytest.raises(SystemExit) as info:
            reader3.main(["--index", BOOK])
    assert isinstance(info.value.code, str), info.value.code
    assert "import" in info.value.code
    assert not (published / "chroma_db").exists()
