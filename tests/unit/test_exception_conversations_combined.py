"""WI-5: `list_conversations_combined()` must not lose the project-root half quietly.

The site was `try: items.extend(list_project_conversations(...)) / except
Exception: pass`. Every reason the project-root store could fail -- an
unreadable directory, a bad root path, a book_uuid that is not a uuid -- came
out the same way: a shorter list. The user sees half of their conversation
history and is told nothing; the operator has nothing to grep for.

Assertion levels (see tests/unit/conftest.py):
    L2 return value
    L4 fault injection on the project-root store
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from reader3_app.ai.conversations import list_conversations_combined

BOOK_UUID = "9f6a1e2c-0000-4000-8000-000000000001"


def _write_conversation(directory: Path, cid: str, *, last_updated: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{cid}.json"
    p.write_text(
        json.dumps(
            {
                "conversation_id": cid,
                "provider": "ollama",
                "model": "llama3",
                "created_at": "2026-08-01T00:00:00Z",
                "last_updated": last_updated,
                "messages": [{"role": "user", "content": text}],
            }
        ),
        encoding="utf-8",
    )
    return p


def _per_book_dir(books_dir: Path) -> Path:
    return books_dir / "dracula_data" / "ai_conversations"


def _project_dir(tmp_path: Path) -> Path:
    return tmp_path / "conversations" / BOOK_UUID


@pytest.fixture(autouse=True)
def _work_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both stores are addressed by absolute path; the chdir fences the third
    store -- a relative default that would land in the repository's own books/."""
    monkeypatch.chdir(tmp_path)


def test_both_stores_are_merged(books_dir: Path, tmp_path: Path) -> None:
    """L2: the feature itself -- one list, both origins, newest first."""
    _write_conversation(
        _per_book_dir(books_dir),
        "11111111-0000-4000-8000-000000000001",
        last_updated="2026-08-01T00:00:00Z",
        text="from the book folder",
    )
    _write_conversation(
        _project_dir(tmp_path),
        "22222222-0000-4000-8000-000000000002",
        last_updated="2026-08-02T00:00:00Z",
        text="from the project root",
    )

    out = list_conversations_combined(
        str(books_dir),
        book_folder="dracula_data",
        book_uuid=BOOK_UUID,
        project_conversations_root=str(tmp_path / "conversations"),
    )

    assert [it["title"] for it in out] == ["from the project root", "from the book folder"]


@pytest.mark.parametrize("newer_store", ["project", "per_book"])
def test_the_newer_copy_of_a_shared_id_wins(
    books_dir: Path, tmp_path: Path, newer_store: str
) -> None:
    """L2: dedupe keeps the later last_updated, whichever store it came from.

    Both directions, because one direction cannot tell the rule apart from its
    most likely corruption. Project-root entries are appended after the per-book
    ones, so "keep the later ``last_updated``" and "whatever arrived last wins"
    agree on every case where the project-root copy is the newer one. They
    disagree only here, in the other direction -- and there the second rule
    resurrects a stale copy over an edit the user just made through the per-book
    store, which is the same silent history loss this module exists to stop.
    """
    cid = "33333333-0000-4000-8000-000000000003"
    stores = {"per_book": _per_book_dir(books_dir), "project": _project_dir(tmp_path)}
    older_store = "per_book" if newer_store == "project" else "project"

    _write_conversation(
        stores[older_store],
        cid,
        last_updated="2026-08-01T00:00:00Z",
        text=f"stale in the {older_store} store",
    )
    _write_conversation(
        stores[newer_store],
        cid,
        last_updated="2026-08-09T00:00:00Z",
        text=f"fresh in the {newer_store} store",
    )

    out = list_conversations_combined(
        str(books_dir),
        book_folder="dracula_data",
        book_uuid=BOOK_UUID,
        project_conversations_root=str(tmp_path / "conversations"),
    )

    assert [it["title"] for it in out] == [f"fresh in the {newer_store} store"]


def test_a_book_uuid_that_is_not_a_uuid_raises(books_dir: Path, tmp_path: Path) -> None:
    """L4: a caller bug used to look exactly like "no project conversations"."""
    _write_conversation(
        _per_book_dir(books_dir),
        "11111111-0000-4000-8000-000000000001",
        last_updated="2026-08-01T00:00:00Z",
        text="from the book folder",
    )

    with pytest.raises(ValueError):
        list_conversations_combined(
            str(books_dir),
            book_folder="dracula_data",
            book_uuid="not-a-uuid",
            project_conversations_root=str(tmp_path / "conversations"),
        )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the permission bits")
def test_unreadable_project_store_degrades_with_a_warning(
    books_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """L4: an I/O failure may degrade the list, but it may not do so in silence."""
    caplog.set_level(logging.DEBUG, logger="reader3.ai")
    _write_conversation(
        _per_book_dir(books_dir),
        "11111111-0000-4000-8000-000000000001",
        last_updated="2026-08-01T00:00:00Z",
        text="from the book folder",
    )
    project_dir = _project_dir(tmp_path)
    _write_conversation(
        project_dir,
        "22222222-0000-4000-8000-000000000002",
        last_updated="2026-08-02T00:00:00Z",
        text="from the project root",
    )
    project_dir.chmod(0o000)
    try:
        out = list_conversations_combined(
            str(books_dir),
            book_folder="dracula_data",
            book_uuid=BOOK_UUID,
            project_conversations_root=str(tmp_path / "conversations"),
        )
    finally:
        project_dir.chmod(0o700)

    assert [it["title"] for it in out] == ["from the book folder"]
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name.startswith("reader3.ai") and r.levelno >= logging.WARNING
    ]
    assert any(BOOK_UUID in m for m in warnings), (
        f"half the history vanished without a warning naming the book: {warnings}"
    )
