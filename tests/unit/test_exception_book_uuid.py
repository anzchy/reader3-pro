"""WI-4: `ensure_book_uuid()` must never overwrite an ai_meta.json it cannot read.

`book_uuid` is the key every AI conversation is filed under. The old code read
the file through a blanket `except Exception: return None` and parsed the stored
uuid under `except Exception: pass`, so a corrupt or unreadable ai_meta.json was
indistinguishable from a missing one: the next call minted a fresh uuid, wrote it
over the file, and the user's entire conversation history became unreachable --
silently, at startup, with no way back because the old uuid was just deleted.

The rule this lane pins down: when the file exists but cannot be understood,
fail loudly and **leave the bytes alone**. A human can fix a file they can still
read; they cannot recover a uuid that was overwritten.

Assertion levels (see tests/unit/conftest.py):
    L2 return value
    L3 the file's bytes before and after
    L4 fault injection -- corrupt / malformed / unreadable metadata
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from uuid import UUID

import pytest

from reader3_app.ai.books import BookUuidResolver, ensure_book_uuid


def _write_meta(books_dir: Path, folder: str, raw: str) -> Path:
    d = books_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ai_meta.json"
    p.write_text(raw, encoding="utf-8")
    return p


def test_missing_meta_gets_a_fresh_uuid_written_atomically(books_dir: Path) -> None:
    """L2/L3: the only case in which writing a new uuid is correct."""
    (books_dir / "dracula_data").mkdir()

    got = ensure_book_uuid(str(books_dir), "dracula_data")

    written = json.loads((books_dir / "dracula_data" / "ai_meta.json").read_text("utf-8"))
    assert written["book_uuid"] == got == str(UUID(got))
    assert not (books_dir / "dracula_data" / "ai_meta.json.tmp").exists()


def test_existing_uuid_is_returned_and_the_file_is_left_alone(books_dir: Path) -> None:
    """L3: the stable-identity guarantee, stated as bytes on disk."""
    p = _write_meta(
        books_dir,
        "dracula_data",
        json.dumps({"book_uuid": "9f6a1e2c-0000-4000-8000-000000000001", "note": "keep me"}),
    )
    before = p.read_bytes()

    got = ensure_book_uuid(str(books_dir), "dracula_data")

    assert got == "9f6a1e2c-0000-4000-8000-000000000001"
    assert p.read_bytes() == before


def test_malformed_uuid_raises_and_does_not_clobber_the_file(books_dir: Path) -> None:
    """L4: a uuid we cannot parse is a fault, not an invitation to mint a new one."""
    p = _write_meta(books_dir, "dracula_data", json.dumps({"book_uuid": "not-a-uuid"}))
    before = p.read_bytes()

    with pytest.raises(ValueError) as excinfo:
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert "ai_meta.json" in str(excinfo.value)
    assert p.read_bytes() == before


def test_corrupt_json_raises_and_does_not_clobber_the_file(books_dir: Path) -> None:
    """L4: a half-written file is exactly when the old code destroyed the mapping."""
    p = _write_meta(books_dir, "dracula_data", '{"book_uuid": "9f6a1e2c-000')
    before = p.read_bytes()

    with pytest.raises(ValueError) as excinfo:
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert "ai_meta.json" in str(excinfo.value)
    assert p.read_bytes() == before


def test_meta_that_is_not_an_object_raises(books_dir: Path) -> None:
    """L4: valid JSON of the wrong shape is still "I cannot read this"."""
    p = _write_meta(books_dir, "dracula_data", json.dumps(["9f6a1e2c"]))
    before = p.read_bytes()

    with pytest.raises(ValueError):
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert p.read_bytes() == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the permission bits")
def test_unreadable_meta_raises_oserror(books_dir: Path) -> None:
    """L4: a permissions problem is an operator's problem, not a new uuid."""
    p = _write_meta(
        books_dir,
        "dracula_data",
        json.dumps({"book_uuid": "9f6a1e2c-0000-4000-8000-000000000001"}),
    )
    before = p.read_bytes()
    p.chmod(0o000)
    try:
        with pytest.raises(OSError):
            ensure_book_uuid(str(books_dir), "dracula_data")
    finally:
        p.chmod(0o600)

    assert p.read_bytes() == before


def test_scan_skips_a_broken_book_and_says_which(
    books_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """L4: one unreadable book must not cost the whole library its startup scan.

    The scan runs on server startup. Propagating here would turn a single corrupt
    file into "the app will not boot", so this is the one place allowed to keep
    going -- and only with the folder named in a warning.
    """
    caplog.set_level(logging.DEBUG, logger="reader3.ai")
    (books_dir / "healthy_data").mkdir()
    broken = _write_meta(books_dir, "broken_data", '{"book_uuid": "9f6a1e2c-000')
    before = broken.read_bytes()

    resolver = BookUuidResolver(str(books_dir))
    resolver.scan()

    healthy_uuid = resolver.book_uuid_for_folder("healthy_data")
    assert resolver.folder_for_book_uuid(healthy_uuid) == "healthy_data"
    assert broken.read_bytes() == before
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name.startswith("reader3.ai") and r.levelno >= logging.WARNING
    ]
    assert any("broken_data" in m for m in warnings), (
        f"the skipped book was not named in any warning: {warnings}"
    )
