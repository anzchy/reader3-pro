"""WI-10: `save_conversation_multi()` must never write nothing and report success.

The site was::

    if mode in ("per_book", "both"):        save_conversation(...)
    if project_conversations_root and mode in ("project_root", "both"):  save_project_conversation(...)

With ``mode="project_root"`` and a falsy ``project_conversations_root`` neither
branch is entered and the function returns ``None``. The caller -- every turn of
an AI conversation -- takes that as "saved". The whole thread is gone, with no
exception and no log line. That combination is not hypothetical: it is exactly
the state WI-8's read-side preference-loss bug produced
(``conversation_disk_storage="project_root"`` with an empty
``conversation_project_root_dir``).

The judgment this lane applies: 「读不懂的用户数据不许当成「没有」。」 A write that
silently does nothing is the same class of defect as a silent overwrite --
raising is acceptable, silently succeeding is not.

Assertion levels (see tests/unit/conftest.py):
    L2 return value, or a single field of on-disk state
    L3 whole-tree observable end state
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from reader3_app.ai.conversations import (
    ConversationMessage,
    ConversationThread,
    load_conversation,
    load_project_conversation,
    save_conversation_multi,
)

BOOK_UUID = "9f6a1e2c-0000-4000-8000-000000000001"
BOOK_FOLDER = "dracula_data"
CONVERSATION_ID = "3b1f0d64-0000-4000-8000-0000000000aa"
SENTINEL = "谁把德古拉请进屋里的？"

# The two preference keys that can disagree with each other, named as the user
# sees them in config/ai_settings.json (ai/config.py:41-42).
MODE_KEY = "conversation_disk_storage"
ROOT_KEY = "conversation_project_root_dir"

# Every falsy-or-blank root the read side can hand us. "   " matters: an empty
# text input in /settings arrives as whitespace, not as "".
MISSING_ROOTS = [None, "", "   "]


@pytest.fixture(autouse=True)
def _relative_paths_resolve_inside_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep any relative root the code resolves inside the tree we assert on.

    Found while watching this file fail: with root="   " the pre-fix code reached
    ``os.path.abspath("   ")``, which is *cwd*-relative, and wrote a real
    conversation into a blank-named directory in the repo root. Chdir'ing makes
    that escape land under ``tmp_path``, where ``_json_files`` sees it -- so the
    strays are caught by the assertions instead of littering the working tree.
    """
    monkeypatch.chdir(tmp_path)


def _thread() -> ConversationThread:
    return ConversationThread(
        schema_version=1,
        book_uuid=BOOK_UUID,
        book_folder=BOOK_FOLDER,
        conversation_id=CONVERSATION_ID,
        provider="ollama",
        model="llama3",
        messages=[
            ConversationMessage(
                id="m1",
                role="user",
                content=SENTINEL,
                timestamp="2026-08-24T00:00:00Z",
            )
        ],
    )


def _seed_book(books_dir: Path) -> Path:
    """018 WI-2 amendment: the book exists, with the identity the thread names.

    Contract item 5: writers no longer create the book dir. Contract item 6: a
    per-book save re-checks ``thread.book_uuid`` against ``ai_meta.json`` in the lock.
    """
    meta = books_dir / BOOK_FOLDER / "ai_meta.json"  # 018 contract items 5 + 6
    meta.parent.mkdir(parents=True)  # 018 contract item 5: the book dir pre-exists
    meta.write_text(json.dumps({"book_uuid": BOOK_UUID}), encoding="utf-8")  # 018 contract item 6
    return meta


def _json_files(root: Path) -> List[str]:
    """Every ``.json`` anywhere under ``root``, as sorted relative paths."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.json"))


def _save(books_dir: Path, **kwargs: Any) -> Optional[BaseException]:
    """Call the unit under test and return what the *caller* observes.

    ``None`` means the call reported success. Deliberately not ``pytest.raises``:
    that construct short-circuits every assertion written after it, and it fails
    on the wrong exception *type* rather than on the actual damage. Here the
    damage -- an empty disk -- has to be asserted unconditionally, whether the
    implementation raised, returned, or blew up in some third way.
    """
    try:
        save_conversation_multi(str(books_dir), thread=_thread(), **kwargs)
    except BaseException as exc:  # noqa: BLE001 - the outcome *is* the observation
        return exc
    return None


def _outcome(err: Optional[BaseException], tmp_path: Path) -> Dict[str, Any]:
    """The pair that decides whether this defect is present.

    ``written`` is the whole observable end state, not a return value; nothing
    the implementation says about itself can fake it.
    """
    return {
        "json_files_on_disk": _json_files(tmp_path),
        "caller_told": type(err).__name__ if err is not None else None,
    }


# --------------------------------------------------------------------------
# C1: project_root mode with no root -> raise, naming both settings
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", MISSING_ROOTS, ids=["none", "empty", "blank"])
def test_project_root_mode_without_a_root_is_rejected(books_dir: Path, root) -> None:
    """L2: the caller is told, and told *which two settings* disagree."""
    err = _save(books_dir, storage_mode="project_root", project_conversations_root=root)

    assert isinstance(err, ValueError), (
        f"expected ValueError for storage_mode='project_root' with root={root!r}, got {err!r}"
    )
    message = str(err)
    assert MODE_KEY in message, f"error message does not name the storage-mode setting: {message!r}"
    assert ROOT_KEY in message, f"error message does not name the root-dir setting: {message!r}"
    assert "project_root" in message, f"error message does not name the offending mode: {message!r}"


# --------------------------------------------------------------------------
# C2: the core assertion -- nothing on disk AND nobody told is the defect
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", MISSING_ROOTS, ids=["none", "empty", "blank"])
def test_a_turn_is_never_both_unwritten_and_unreported(books_dir: Path, tmp_path: Path, root) -> None:
    """L3 (**core**): the whole tmp tree, paired with what the caller heard.

    The harm in the finding is "believed saved, actually gone". Asserting only
    that something raised cannot tell "refused and said so" apart from "wrote
    half of it and then threw". Both halves are pinned in one comparison:

      * ``json_files_on_disk == []`` -- not one byte was written, so the raise
        is a refusal up front and not an apology after the fact;
      * ``caller_told == "ValueError"`` -- the turn's disappearance reached the
        caller.

    Delete the guard and this goes red as ``caller_told: None`` beside an empty
    disk: the conversation is nowhere to be found and nobody was told.
    """
    err = _save(books_dir, storage_mode="project_root", project_conversations_root=root)

    assert _outcome(err, tmp_path) == {"json_files_on_disk": [], "caller_told": "ValueError"}


def test_the_same_turn_lands_on_disk_once_the_root_is_supplied(books_dir: Path, tmp_path: Path) -> None:
    """L3 (**core**, other half): with a real root the turn is readable back.

    Without this, "raise on everything" would pass the case above. The assertion
    is on parsed file content at the expected path, never on a return value.
    """
    project_root = tmp_path / "conversations"

    err = _save(books_dir, storage_mode="project_root", project_conversations_root=str(project_root))

    assert err is None, f"a well-configured project_root save must not raise, got {err!r}"

    expected = project_root / BOOK_UUID / f"{CONVERSATION_ID}.json"
    assert _json_files(tmp_path) == [expected.relative_to(tmp_path).as_posix()]

    payload = json.loads(expected.read_text(encoding="utf-8"))
    assert [m["content"] for m in payload["messages"]] == [SENTINEL]

    reloaded = load_project_conversation(
        str(project_root),
        book_uuid=BOOK_UUID,
        book_folder=BOOK_FOLDER,
        conversation_id=CONVERSATION_ID,
    )
    assert [m.content for m in reloaded.messages] == [SENTINEL]


# --------------------------------------------------------------------------
# C3: "both" with no root -- half a success is not a success
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", MISSING_ROOTS, ids=["none", "empty", "blank"])
def test_both_mode_without_a_root_writes_neither_half(books_dir: Path, tmp_path: Path, root) -> None:
    """L3: the per-book half must not land either.

    A caller that asked for two copies and got one has no way to learn which one
    is missing, so "wrote per_book, skipped project_root, returned None" is the
    same defect wearing a hat.
    """
    err = _save(books_dir, storage_mode="both", project_conversations_root=root)

    assert _outcome(err, tmp_path) == {"json_files_on_disk": [], "caller_told": "ValueError"}
    assert ROOT_KEY in str(err), f"error message does not name the root-dir setting: {str(err)!r}"


# --------------------------------------------------------------------------
# C4: per_book never needed a root -- do not over-fix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", MISSING_ROOTS, ids=["none", "empty", "blank"])
def test_per_book_mode_ignores_the_missing_root(books_dir: Path, tmp_path: Path, root) -> None:
    """L2: per_book writes to the book folder and has no use for a project root."""
    meta = _seed_book(books_dir)  # 018 contract items 5 + 6
    meta_bytes = meta.read_bytes()  # 018 contract items 5 + 6
    err = _save(books_dir, storage_mode="per_book", project_conversations_root=root)

    assert err is None, f"per_book does not use project_conversations_root, got {err!r}"

    expected = books_dir / BOOK_FOLDER / "ai_conversations" / f"{CONVERSATION_ID}.json"
    assert _json_files(tmp_path) == sorted(
        [meta.relative_to(tmp_path).as_posix(), expected.relative_to(tmp_path).as_posix()]
    )
    assert meta.read_bytes() == meta_bytes

    reloaded = load_conversation(
        str(books_dir),
        book_folder=BOOK_FOLDER,
        book_uuid=BOOK_UUID,
        conversation_id=CONVERSATION_ID,
    )
    assert [m.content for m in reloaded.messages] == [SENTINEL]


# --------------------------------------------------------------------------
# C5: an unrecognised mode still falls back -- but not in silence
# --------------------------------------------------------------------------


def test_unrecognised_mode_falls_back_to_per_book_and_says_so(
    books_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """L2: a typo'd mode writes to the default location and leaves a WARNING.

    Falling back to per_book writes the data somewhere real, so it is not this
    finding's damage and must not become a 500 on every AI turn. Silence is the
    part that is unacceptable: the operator needs something to grep for when a
    user asks why their conversations are not in the project root.
    """
    meta = _seed_book(books_dir)  # 018 contract items 5 + 6
    meta_bytes = meta.read_bytes()  # 018 contract items 5 + 6
    with caplog.at_level(logging.WARNING, logger="reader3.ai.conversations"):
        err = _save(books_dir, storage_mode="projekt_root", project_conversations_root=None)

    assert err is None, f"a misspelled mode must not raise, got {err!r}"

    expected = books_dir / BOOK_FOLDER / "ai_conversations" / f"{CONVERSATION_ID}.json"
    assert _json_files(tmp_path) == sorted(
        [meta.relative_to(tmp_path).as_posix(), expected.relative_to(tmp_path).as_posix()]
    )
    assert meta.read_bytes() == meta_bytes

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("projekt_root" in m for m in warnings), (
        f"no WARNING naming the rejected mode value; captured: {warnings!r}"
    )


def test_suppressed_exception_helper_matches_direct_call(books_dir: Path, tmp_path: Path) -> None:
    """L2: the helper above is not hiding a pass -- the raise is real.

    Guards the test file itself: if `_save` ever swallowed a genuinely
    successful call, every core assertion would become vacuous.
    """
    with contextlib.suppress(Exception):
        save_conversation_multi(
            str(books_dir),
            thread=_thread(),
            storage_mode="project_root",
            project_conversations_root=None,
        )

    assert _json_files(tmp_path) == []
