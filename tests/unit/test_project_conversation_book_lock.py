"""018 WI-5b: the project-root conversation writer holds the book lock (ADR-0018, ruled W5-11).

Matrix cases B-1, B-2, B-3, B-4 of ``tests-20261002-170000-wi5.md``.

Law: no project-root file is written for book ``f`` unless the writer holds SH ``f``
(``conversations``) and the resource lock, and ``f`` exists with the thread's uuid.
In ``both`` mode there is exactly one ``conversations`` acquisition.

Every outcome is captured as an exception *type name* and compared in one dict, so
a red shows the whole observation at once and never quotes an OS error message
(the red-receipt tool reads the ENOENT phrase as a broken runner).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from delete_world import (
    CID_FRESH,
    D_MID,
    D_OLD,
    U,
    U2,
    Holder,
    conv,
    install_hook,
    ld,
    make_book,
    new_world,
    probe_lock,
    put_file,
)
from reader3_app import book_lock
from reader3_app.ai import conversations
from reader3_app.ai.conversations import ConversationMessage, ConversationThread

FOLDER = "a_data"
JOIN_TIMEOUT_S = 30.0
TEXT = "project-root turn"


def _thread(book_uuid: str = U, folder: str = FOLDER, cid: str = CID_FRESH) -> ConversationThread:
    return ConversationThread(
        schema_version=conversations.SCHEMA_VERSION,
        book_uuid=book_uuid,
        book_folder=folder,
        conversation_id=cid,
        provider="stub",
        messages=[ConversationMessage(id="m-1", role="user", content=TEXT, timestamp="2026-10-02T00:00:00+00:00")],
    )


def _run(fn: Callable[[], Any]) -> Optional[BaseException]:
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
        return exc
    return None


def _name(exc: Optional[BaseException]) -> str:
    return "None" if exc is None else type(exc).__name__


def _same_dir(path: Any, directory: Path) -> bool:
    """Whether ``path`` names an entry directly inside ``directory`` (realpaths; ``path`` may not exist)."""
    p = os.path.abspath(os.fsdecode(os.fspath(path)))
    return os.path.realpath(os.path.dirname(p)) == os.path.realpath(str(directory))


def _project_file(R: Path, uuid: str = U, cid: str = CID_FRESH) -> Path:
    return R / uuid / f"{cid}.json"


def _per_book_file(books: Path, folder: str = FOLDER, cid: str = CID_FRESH) -> Path:
    return books / folder / "ai_conversations" / f"{cid}.json"


def _interpose_project_replace(monkeypatch, project_dir: Path, action: Callable[[], None]) -> List[int]:
    """A delegating ``os.replace``: the first replace landing in ``project_dir`` runs ``action`` first."""
    real = os.replace
    fired: List[int] = []

    def replace(src, dst, *a, **kw):
        if not fired and _same_dir(dst, project_dir):
            fired.append(1)
            action()
        return real(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", replace)
    return fired


# =========================================================================== B-1


def test_b1_project_save_runs_under_the_book_lock(tmp_path, monkeypatch):
    """B-1: at the project-root ``os.replace`` a cross-process EX probe is busy("conversations")."""
    w = new_world(tmp_path / "w")
    make_book(w.books, FOLDER, book_uuid=U)
    probes: List[Tuple[str, Optional[str]]] = []
    fired = _interpose_project_replace(
        monkeypatch, w.R / U, lambda: probes.append(probe_lock(w.books, FOLDER, book_lock.EXCLUSIVE))
    )

    err = _run(lambda: conversations.save_project_conversation(str(w.R), thread=_thread(), books_dir=str(w.books)))

    target = _project_file(w.R)
    assert {
        "error": _name(err),
        "fired": fired,
        "probe": probes,
        "file": target.is_file(),
    } == {
        "error": "None",
        "fired": [1],
        "probe": [("busy", "conversations")],
        "file": True,
    }
    assert conversations.load_project_conversation(
        str(w.R), book_uuid=U, book_folder=FOLDER, conversation_id=CID_FRESH
    ).messages[0].content == TEXT


# =========================================================================== B-2


def test_b2_project_save_outcomes_gone_changed_busy(tmp_path):
    """B-2: (a) folder missing -> BookGone, R/U not created; (b) re-created with U2 -> BookChanged;
    (c) EX "delete" held -> BookLockBusy("delete") after the full SH budget. Nothing is written."""
    observed: Dict[str, Any] = {}

    # (a) gone
    wa = new_world(tmp_path / "a")
    err = _run(lambda: conversations.save_project_conversation(str(wa.R), thread=_thread(), books_dir=str(wa.books)))
    observed["gone"] = (_name(err), os.path.lexists(wa.R / U), os.path.lexists(wa.books / FOLDER))

    # (b) changed
    wb = new_world(tmp_path / "b")
    make_book(wb.books, FOLDER, book_uuid=U2)
    err = _run(lambda: conversations.save_project_conversation(str(wb.R), thread=_thread(), books_dir=str(wb.books)))
    observed["changed"] = (_name(err), os.path.lexists(wb.R / U))

    # (c) busy
    wc = new_world(tmp_path / "c")
    make_book(wc.books, FOLDER, book_uuid=U)
    holder = Holder(str(wc.books), FOLDER, book_lock.EXCLUSIVE, "delete", str(tmp_path))
    holder.start()
    try:
        t0 = time.monotonic()
        err = _run(
            lambda: conversations.save_project_conversation(str(wc.R), thread=_thread(), books_dir=str(wc.books))
        )
        elapsed = time.monotonic() - t0
    finally:
        holder.release()
    observed["busy"] = (
        _name(err),
        getattr(err, "holder_category", None),
        elapsed >= book_lock.BUDGET_S - 0.2,
        os.path.lexists(wc.R / U),
    )

    assert observed == {
        "gone": ("BookGone", False, False),
        "changed": ("BookChanged", False),
        "busy": ("BookLockBusy", "delete", True, False),
    }, f"busy elapsed={elapsed:.3f}s"


# =========================================================================== B-3


def test_b3_both_mode_is_one_acquisition_and_project_write_is_locked(tmp_path, monkeypatch):
    """B-3 (G13): ``both`` takes one ``conversations`` acquisition, and the project write is inside it:
    at the project-root replace an EX probe is busy and an in-process ``delete_book(true)`` is refused."""
    w = new_world(tmp_path / "w")
    make_book(w.books, FOLDER, book_uuid=U)
    m = ld()

    real_acquire = book_lock.acquire
    counted: List[int] = []

    def counting_acquire(books_dir, book_folder, *args, **kwargs):
        if book_folder == FOLDER and kwargs.get("holder") == "conversations":
            counted.append(1)
        return real_acquire(books_dir, book_folder, *args, **kwargs)

    monkeypatch.setattr(book_lock, "acquire", counting_acquire)

    probes: List[Tuple[str, Optional[str]]] = []
    delete_box: Dict[str, Any] = {}

    def at_project_replace() -> None:
        probes.append(probe_lock(w.books, FOLDER, book_lock.EXCLUSIVE))

        def body() -> None:
            try:
                m.delete_book(
                    str(w.books),
                    FOLDER,
                    delete_conversations=True,
                    conversation_root=str(w.R),
                    collections_path=str(w.coll),
                )
            except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
                delete_box["error"] = exc

        t = threading.Thread(target=body, daemon=True)
        t.start()
        t.join(JOIN_TIMEOUT_S)
        delete_box["alive"] = t.is_alive()

    fired = _interpose_project_replace(monkeypatch, w.R / U, at_project_replace)

    err = _run(
        lambda: conversations.save_conversation_multi(
            str(w.books), thread=_thread(), project_conversations_root=str(w.R), storage_mode="both"
        )
    )

    assert {
        "save": _name(err),
        "acquisitions": len(counted),
        "fired": fired,
        "probe": probes,
        "delete": (_name(delete_box.get("error")), delete_box.get("alive")),
        "a_data": (w.books / FOLDER).is_dir(),
        "per_book": _per_book_file(w.books).is_file(),
        "project": _project_file(w.R).is_file(),
    } == {
        "save": "None",
        "acquisitions": 1,
        "fired": [1],
        "probe": [("busy", "conversations")],
        "delete": ("BookLockBusy", False),
        "a_data": True,
        "per_book": True,
        "project": True,
    }


# =========================================================================== B-4


def test_b4_delete_vs_project_save_ordering(tmp_path):
    """B-4 (D15): (a) delete first, then a project save -> BookGone and R/U absent;
    (b) EX held during ``both`` -> BookLockBusy and neither file written."""
    observed: Dict[str, Any] = {}

    # (a) delete_book(true) then a late project-root save
    wa = new_world(tmp_path / "a")
    make_book(wa.books, FOLDER, book_uuid=U)
    wa.delete(FOLDER, mode=True)
    assert not (wa.books / FOLDER).exists()
    err = _run(lambda: conversations.save_project_conversation(str(wa.R), thread=_thread(), books_dir=str(wa.books)))
    observed["delete_then_save"] = (_name(err), os.path.lexists(wa.R / U))

    # (b) a Holder holds EX during save_conversation_multi(both)
    wb = new_world(tmp_path / "b")
    make_book(wb.books, FOLDER, book_uuid=U)
    holder = Holder(str(wb.books), FOLDER, book_lock.EXCLUSIVE, "delete", str(tmp_path))
    holder.start()
    try:
        err = _run(
            lambda: conversations.save_conversation_multi(
                str(wb.books), thread=_thread(), project_conversations_root=str(wb.R), storage_mode="both"
            )
        )
    finally:
        holder.release()
    observed["held_during_both"] = (
        _name(err),
        _per_book_file(wb.books).exists(),
        os.path.lexists(wb.R / U),
    )

    assert observed == {
        "delete_then_save": ("BookGone", False),
        "held_during_both": ("BookLockBusy", False, False),
    }


# =========================================================================== B-5 .. B-7 (audit 20261007 #1, FX37-3)
#
# Law: a single-conversation delete runs under SH ``conversations`` on the book folder
# (plain ``acquire``, no existence recheck) plus the conversations resource lock, so it
# cannot interleave with a book delete's EX section (commit rename .. finalizer publish),
# yet still works on an orphan whose book folder is gone.


def _delete_multi(w, cid: str = CID_FRESH) -> None:
    conversations.delete_conversation_multi(
        str(w.books), book_folder=FOLDER, book_uuid=U, conversation_id=cid, project_conversations_root=str(w.R)
    )


def test_b5_conversation_delete_waits_for_an_in_flight_book_delete(tmp_path, monkeypatch):
    """B-5: a project-root conversation DELETE landing between the commit rename and the finalizer's
    publish waits for the book delete instead of running inside that window; afterwards the
    conversation is gone from the project root -- the finalizer's republish does not resurrect it."""
    w = new_world(tmp_path / "w")
    make_book(w.books, FOLDER, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "per-book copy")])
    put_file(_project_file(w.R), conv(CID_FRESH, D_OLD, "project copy")[1])

    paused, go = threading.Event(), threading.Event()

    def hook(name: str) -> None:
        if name == "committed":
            paused.set()
            go.wait(JOIN_TIMEOUT_S)

    install_hook(monkeypatch, hook)
    box: Dict[str, Any] = {}

    def deleter() -> None:
        box["delete"] = _run(lambda: w.delete(FOLDER, mode=False))

    def conv_deleter() -> None:
        box["conv"] = _run(lambda: _delete_multi(w))

    td = threading.Thread(target=deleter, daemon=True)
    td.start()
    assert paused.wait(JOIN_TIMEOUT_S), "the book delete never reached its commit point"
    tc = threading.Thread(target=conv_deleter, daemon=True)
    tc.start()
    tc.join(0.3)
    finished_inside_window = not tc.is_alive()
    go.set()
    td.join(JOIN_TIMEOUT_S)
    tc.join(JOIN_TIMEOUT_S)

    assert {
        "delete": _name(box.get("delete")),
        "conv": _name(box.get("conv")),
        "alive": (td.is_alive(), tc.is_alive()),
        "conv_delete_ran_inside_the_window": finished_inside_window,
        "project": _project_file(w.R).exists(),
        "a_data": (w.books / FOLDER).exists(),
    } == {
        "delete": "None",
        "conv": "None",
        "alive": (False, False),
        "conv_delete_ran_inside_the_window": False,
        "project": False,
        "a_data": False,
    }


def test_b6_orphan_conversation_stays_deletable(tmp_path):
    """B-6: after a ``delete_conversations=false`` book delete the conversation is an orphan under
    ``R/U``; deleting it succeeds (no ``BookGone``), removes it, and never recreates the book folder."""
    w = new_world(tmp_path / "w")
    make_book(w.books, FOLDER, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "kept")])
    w.delete(FOLDER, mode=False)
    assert _project_file(w.R).is_file(), "precondition: the delete published the orphan"

    err = _run(lambda: _delete_multi(w))

    assert {
        "error": _name(err),
        "project": _project_file(w.R).exists(),
        "a_data": os.path.lexists(w.books / FOLDER),
    } == {"error": "None", "project": False, "a_data": False}


def _interpose_remove(monkeypatch, targets: List[Path], action: Callable[[Path], None]) -> List[str]:
    """A delegating ``os.remove``: each removal of a path in ``targets`` runs ``action(path)`` first."""
    real = os.remove
    wanted = {os.path.realpath(str(t)) for t in targets}
    seen: List[str] = []

    def remove(path, *a, **kw):
        p = os.path.realpath(os.fsdecode(os.fspath(path)))
        if p in wanted:
            seen.append(os.path.basename(os.path.dirname(p)))
            action(Path(p))
        return real(path, *a, **kw)

    monkeypatch.setattr(os, "remove", remove)
    return seen


def test_b7_conversation_delete_runs_under_the_book_lock(tmp_path, monkeypatch):
    """B-7: at each ``os.remove`` (per-book copy, then project copy) a cross-process EX probe is
    busy("conversations"); an EX "delete" holder makes the delete ``BookLockBusy`` and removes nothing."""
    observed: Dict[str, Any] = {}

    wa = new_world(tmp_path / "a")
    make_book(wa.books, FOLDER, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "per-book copy")])
    put_file(_project_file(wa.R), conv(CID_FRESH, D_MID, "project copy")[1])
    probes: List[Tuple[str, Optional[str]]] = []
    seen = _interpose_remove(
        monkeypatch,
        [_per_book_file(wa.books), _project_file(wa.R)],
        lambda _p: probes.append(probe_lock(wa.books, FOLDER, book_lock.EXCLUSIVE)),
    )
    err = _run(lambda: _delete_multi(wa))
    observed["locked"] = (
        _name(err),
        seen,
        probes,
        _per_book_file(wa.books).exists(),
        _project_file(wa.R).exists(),
    )
    monkeypatch.undo()

    wb = new_world(tmp_path / "b")
    make_book(wb.books, FOLDER, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "per-book copy")])
    put_file(_project_file(wb.R), conv(CID_FRESH, D_MID, "project copy")[1])
    holder = Holder(str(wb.books), FOLDER, book_lock.EXCLUSIVE, "delete", str(tmp_path))
    holder.start()
    try:
        err = _run(lambda: _delete_multi(wb))
    finally:
        holder.release()
    observed["busy"] = (
        _name(err),
        getattr(err, "holder_category", None),
        _per_book_file(wb.books).exists(),
        _project_file(wb.R).exists(),
    )

    assert observed == {
        "locked": (
            "None",
            ["ai_conversations", U],
            [("busy", "conversations"), ("busy", "conversations")],
            False,
            False,
        ),
        "busy": ("BookLockBusy", "delete", True, True),
    }
