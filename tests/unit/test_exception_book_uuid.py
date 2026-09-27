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

from reader3_app.ai import books as books_module
from reader3_app.ai.books import BookUuidResolver, ensure_book_uuid


#: Pre-seeded so the scan case has an identity it did not have to mint, and can
#: therefore say which uuid it expects instead of only "some uuid".
HEALTHY_UUID = "9f6a1e2c-0000-4000-8000-0000000000aa"


@pytest.fixture(autouse=True)
def _work_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``books_dir`` is already under ``tmp_path``; this fences the relative
    paths -- a bare ``books/`` default would otherwise resolve into the repo."""
    monkeypatch.chdir(tmp_path)


def _write_meta(books_dir: Path, folder: str, raw: str) -> Path:
    d = books_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ai_meta.json"
    p.write_text(raw, encoding="utf-8")
    return p


def _crash_midway(obj, fp, **kwargs):
    """A ``json.dump`` that gets a plausible prefix out and then dies.

    The prefix matters: a dump that raises before writing anything cannot tell a
    truncating writer apart from an atomic one.
    """
    fp.write('{\n  "book_uuid": "9f6a1e2c-000')
    raise RuntimeError("simulated: disk full")


def test_missing_meta_gets_a_fresh_uuid_written_atomically(books_dir: Path) -> None:
    """L2/L3: the only case in which writing a new uuid is correct."""
    (books_dir / "dracula_data").mkdir()

    got = ensure_book_uuid(str(books_dir), "dracula_data")

    written = json.loads((books_dir / "dracula_data" / "ai_meta.json").read_text("utf-8"))
    assert written["book_uuid"] == got == str(UUID(got))
    assert not (books_dir / "dracula_data" / "ai_meta.json.tmp").exists()


def test_a_crash_while_minting_leaves_no_ai_meta_at_all(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4: atomicity stated as "what a crash leaves behind", not as "no .tmp".

    "no leftover ai_meta.json.tmp" is a claim about tidiness, and a writer that
    is not atomic at all satisfies it perfectly: a plain ``open(path, "w")`` plus
    ``json.dump`` never creates a temporary file either. What separates the two
    is a crash *during* the write. The truncating writer leaves a partial
    ai_meta.json on disk -- and a partial ai_meta.json is precisely the
    unreadable state every other case in this module refuses to mint over, so
    the non-atomic writer manufactures the fault the module exists to survive.
    """
    d = books_dir / "dracula_data"
    d.mkdir()
    monkeypatch.setattr(books_module.json, "dump", _crash_midway)

    with pytest.raises(RuntimeError, match="simulated"):
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert sorted(os.listdir(d)) == [], (
        "a crashed mint must leave the book folder exactly as it found it, but it left: "
        f"{sorted(os.listdir(d))}"
    )


def test_a_crash_while_adding_a_uuid_leaves_the_old_bytes_intact(
    books_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4: the other half of the same guarantee -- a file that already exists.

    Adding a uuid to metadata that has none is a read-modify-write over a file
    holding keys nobody else can reproduce. If the write is not atomic, a crash
    here does not lose a uuid the book never had; it loses whatever else the file
    was carrying, and replaces it with bytes that no longer parse.
    """
    p = _write_meta(books_dir, "dracula_data", json.dumps({"note": "keep me"}))
    before = p.read_bytes()
    monkeypatch.setattr(books_module.json, "dump", _crash_midway)

    with pytest.raises(RuntimeError, match="simulated"):
        ensure_book_uuid(str(books_dir), "dracula_data")

    assert p.read_bytes() == before, "the existing metadata was truncated in place"
    assert sorted(os.listdir(p.parent)) == ["ai_meta.json"], (
        f"the failed write left a temporary file behind: {sorted(os.listdir(p.parent))}"
    )


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
    books_dir: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4: one unreadable book must not cost the whole library its startup scan.

    The scan runs on server startup. Propagating here would turn a single corrupt
    file into "the app will not boot", so this is the one place allowed to keep
    going -- and only with the folder named in a warning.
    """
    caplog.set_level(logging.DEBUG, logger="reader3.ai")
    _write_meta(books_dir, "healthy_data", json.dumps({"book_uuid": HEALTHY_UUID}))
    broken = _write_meta(books_dir, "broken_data", '{"book_uuid": "9f6a1e2c-000')
    before = broken.read_bytes()

    resolver = BookUuidResolver(str(books_dir))
    resolver.scan()

    # `book_uuid_for_folder` resolves lazily on a miss, so asking it straight
    # after `scan()` cannot tell "the scan resolved the healthy book" from "the
    # scan skipped every book and the lazy miss path quietly covered for it" --
    # which is exactly the regression this case has to catch. A hit validates
    # against ai_meta.json on disk (a rewritten file must win, or a re-imported
    # book keeps its predecessor's uuid), so the old "rewrite, expect the stale
    # uuid" probe no longer separates the two. The miss path is what does:
    # only a cache the scan itself filled can answer without reaching it.
    miss_path_calls: list[str] = []

    def _no_miss_path(books_dir_arg: str, folder: str) -> str:
        miss_path_calls.append(folder)
        return ensure_book_uuid(books_dir_arg, folder)

    monkeypatch.setattr(books_module, "ensure_book_uuid", _no_miss_path)

    assert resolver.book_uuid_for_folder("healthy_data") == HEALTHY_UUID
    assert miss_path_calls == [], (
        "scan() did not resolve the healthy book; the answer came from the lazy miss path"
    )
    assert resolver.folder_for_book_uuid(HEALTHY_UUID) == "healthy_data"
    assert broken.read_bytes() == before
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name.startswith("reader3.ai") and r.levelno >= logging.WARNING
    ]
    assert any("broken_data" in m for m in warnings), (
        f"the skipped book was not named in any warning: {warnings}"
    )
