"""018 WI-5b: the sweep entry points (matrix cases B-6b, B-7, B-8, B-9; ruled Q6, W5-18).

Law:
- The sweep runs at server startup and at the start of ``process_epub``.
- ``reader3`` does not import web modules.
- ``process_epub`` never imports over a remaining same-name tombstone.

B-6b is green at red (``reader3`` imports no web module today); it guards the 5b
wiring and is excluded from the WI-5b receipt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from delete_world import (
    CID_FRESH,
    D_MID,
    SUBPROCESS_TIMEOUT_S,
    U,
    V,
    W,
    ZERO_UUID,
    Holder,
    child_env,
    conv,
    dot_entries,
    finish,
    intent_json,
    ld,
    make_book,
    new_world,
    paired,
    popen_child,
    put_file,
    raw_conv,
    read_collections,
    seat_resolver,
    tree_bytes,
    write_book_pkl,
    write_collections,
)
from epub_corpus import build_epub2
from reader3_app import book_lock
from reader3_app.web import server

WEB_MODULES = "sorted(n for n in sys.modules if n == 'reader3_app.web' or n.startswith('reader3_app.web.'))"

B6B_CODE = f"import json, sys; import reader3_app.reader3; print(json.dumps({WEB_MODULES}))"

B7_CODE = (
    "import json, sys; "
    "from reader3_app.reader3 import process_epub; "
    "process_epub(sys.argv[1], sys.argv[2]); "
    f"print(json.dumps({WEB_MODULES}))"
)

TOMB_NAME = ".dracula_data.deleted-77-abcdef12"


def _web_list(stdout: str) -> Any:
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


# =========================================================================== B-6b


def test_b6b_reader3_import_graph_has_no_web():
    """B-6b: a fresh interpreter importing ``reader3_app.reader3`` loads no ``reader3_app.web*``."""
    proc = subprocess.run(
        [sys.executable, "-c", B6B_CODE], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S, env=child_env()
    )

    assert proc.returncode == 0, proc.stderr[-3000:]
    assert _web_list(proc.stdout) == []


# =========================================================================== B-7


def test_b7_process_epub_sweeps_before_import(tmp_path):
    """B-7: ``process_epub`` finalizes every pending tombstone (same name and other) before importing,
    publishes the false-mode conversation, imports, and loads no web module."""
    ld()  # red guard in the parent, before the child is spawned
    w = new_world(tmp_path / "w")
    c1 = conv(CID_FRESH, D_MID, "c1 turn")
    pd = paired(w.books, "dracula_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[c1])
    po = paired(w.books, "other_data", mode=True, uuid=V, root=w.R, coll=w.coll, book_uuid=V, pid=78, token="0123abcd")
    epub = build_epub2(tmp_path / "dracula.epub")

    proc = subprocess.run(
        [sys.executable, "-c", B7_CODE, str(epub), str(w.books / "dracula_data")],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        env=child_env(),
    )

    assert proc.returncode == 0, proc.stderr[-3000:]
    assert {
        "dracula_tomb": pd.tomb.exists(),
        "dracula_intent": pd.intent.exists(),
        "other_tomb": po.tomb.exists(),
        "other_intent": po.intent.exists(),
        "dot_entries": dot_entries(w.books),
        "published": (w.R / U / c1[0]).read_bytes() == c1[1] if (w.R / U / c1[0]).is_file() else None,
        "book_pkl": (w.books / "dracula_data" / "book.pkl").is_file(),
        "web": _web_list(proc.stdout),
    } == {
        "dracula_tomb": False,
        "dracula_intent": False,
        "other_tomb": False,
        "other_intent": False,
        "dot_entries": [],
        "published": True,
        "book_pkl": True,
        "web": [],
    }


# =========================================================================== B-8


@pytest.fixture
def startup_world(tmp_path, monkeypatch):
    """A books dir under ``proj/``, the ``BOOKS_DIR`` / resolver / settings seams patched.

    The settings name ``convB``: an intent recording ``convA`` must win (B-8(b)).
    """
    w = new_world(tmp_path / "proj")
    monkeypatch.setattr(server, "BOOKS_DIR", str(w.books))
    seat_resolver(monkeypatch, w.books)

    def _settings(*_a: Any, **_kw: Any) -> Dict[str, Any]:
        return {
            "preferences": {
                "conversation_disk_storage": "project_root",
                "conversation_project_root_dir": "convB",
            }
        }

    monkeypatch.setattr(server, "load_ai_settings", _settings)
    server.load_book_cached.cache_clear()
    try:
        yield w
    finally:
        server.load_book_cached.cache_clear()


def _start_server() -> None:
    with TestClient(app=server.app, base_url="http://127.0.0.1"):
        pass


def test_b8a_server_startup_sweeps_paired_and_orphan(startup_world):
    """B-8(a): startup finalizes a paired tombstone and removes an orphan intent; the live book is identical."""
    w = startup_world
    m = ld()
    p = paired(w.books, "a_data", mode=True, uuid=U, root=w.R, coll=w.coll, book_uuid=U)
    make_book(w.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    write_collections(w.coll, {"c1": ["a_data", "b_data"]})
    orphan = w.books / m.intent_name("c_data", 79, "feedbeef")
    orphan.write_bytes(
        intent_json("c_data", pid=79, token="feedbeef", mode=True, uuid=W, root=str(w.R), coll=str(w.coll))
    )
    live_before = tree_bytes(w.books / "b_data")
    assert sorted(dot_entries(w.books)) == sorted([p.tomb.name, p.intent.name, orphan.name])

    _start_server()

    assert {
        "dot_entries": dot_entries(w.books),
        "collections": read_collections(w.coll),
        "live": tree_bytes(w.books / "b_data") == live_before,
    } == {
        "dot_entries": [],
        "collections": {"c1": ["b_data"]},
        "live": True,
    }


def test_b8b_server_startup_uses_the_intent_root_not_settings(startup_world):
    """B-8(b): the intent records ``convA`` while settings say ``convB`` -> the conversation lands in convA."""
    w = startup_world
    conv_a = w.root / "convA"
    conv_b = w.root / "convB"
    c1 = conv(CID_FRESH, D_MID, "kept turn")
    p = paired(w.books, "a_data", mode=False, uuid=U, root=conv_a, coll=w.coll, book_uuid=U, convs=[c1])

    _start_server()

    target = conv_a / U / c1[0]
    assert {
        "tomb": p.tomb.exists(),
        "intent": p.intent.exists(),
        "convA": target.read_bytes() == c1[1] if target.is_file() else None,
        "convB": os.path.lexists(conv_b),
    } == {"tomb": False, "intent": False, "convA": True, "convB": False}


def test_b8c_server_startup_invalidates_caches_after_a_crashed_delete(startup_world):
    """B-8(c): a child is SIGKILLed at ``committed`` after the parent warmed its caches; startup sweeps;
    ``a_data`` is re-created with an equal ``book.pkl`` stat -> the parent reads the new content."""
    w = startup_world
    ld()  # red guard in the parent, before the child is spawned
    make_book(w.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U)
    pkl = w.books / "a_data" / "book.pkl"
    old = os.stat(pkl)
    assert server.load_book_cached("a_data").spine[0].text == "AAAA alpha"

    sentinel = w.root / "sentinel.txt"
    proc = popen_child("crash_child_main", str(w.books), str(w.R), str(w.coll), "true", "committed", str(sentinel))
    rc, _out, err = finish(proc)
    assert sentinel.read_text(encoding="utf-8") == "committed", (rc, err[-3000:])
    assert not (w.books / "a_data").exists()

    _start_server()

    (w.books / "a_data").mkdir()
    write_book_pkl(w.books / "a_data", title="Alpha", body="ZZZZ zzzzz")
    os.utime(pkl, ns=(old.st_atime_ns, old.st_mtime_ns))
    new = os.stat(pkl)
    assert (new.st_mtime_ns, new.st_size) == (old.st_mtime_ns, old.st_size)

    assert {
        "dot_entries": dot_entries(w.books),
        "text": server.load_book_cached("a_data").spine[0].text,
    } == {"dot_entries": [], "text": "ZZZZ zzzzz"}


# =========================================================================== B-9


def _cli() -> Path:
    exe = Path(sys.executable).parent / "reader3"
    if not exe.is_file():
        pytest.fail(f"the reader3 console script is not installed next to {sys.executable}", pytrace=False)
    return exe


@pytest.mark.parametrize("state", ["busy", "conserved_bad_conversation", "conserved_no_intent", "failed"])
def test_b9_process_epub_refuses_over_remaining_same_name_tombstone(tmp_path, state):
    """B-9 (G10, W5-18): a ``dracula_data`` tombstone the sweep cannot clear (busy / conserved / failed)
    makes the CLI refuse: non-zero exit, stderr names the tombstone, nothing imported, entries intact."""
    ld()  # red guard in the parent, before the child is spawned
    w = new_world(tmp_path / "w")
    valid = conv(CID_FRESH, D_MID, "dracula turn")
    convs = [valid]
    if state == "conserved_bad_conversation":
        convs = [valid, raw_conv(f"{ZERO_UUID}.json", b"{trunc")]
    if state == "failed":
        put_file(w.R / U, b"not a directory")
    p = paired(w.books, "dracula_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)
    assert p.tomb.name == TOMB_NAME
    if state == "conserved_no_intent":
        p.intent.unlink()
    tomb_before = tree_bytes(p.tomb)
    intent_before = p.intent.read_bytes() if p.intent.exists() else None
    epub = build_epub2(tmp_path / "dracula.epub")
    env = child_env()
    env["READER3_BOOKS_DIR"] = str(w.books)

    holder = None
    if state == "busy":
        holder = Holder(str(w.books), "dracula_data", book_lock.SHARED, "search", str(tmp_path))
        holder.start()
    try:
        proc = subprocess.Popen(
            [str(_cli()), str(epub)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(tmp_path)
        )
        rc, _out, err = finish(proc)
    finally:
        if holder is not None:
            holder.release()

    assert {
        "exit_nonzero": rc != 0,
        "stderr_names_tomb": TOMB_NAME in err,
        "imported": os.path.lexists(w.books / "dracula_data"),
        "tomb_intact": tree_bytes(p.tomb) == tomb_before,
        "intent": p.intent.read_bytes() if p.intent.exists() else None,
    } == {
        "exit_nonzero": True,
        "stderr_names_tomb": True,
        "imported": False,
        "tomb_intact": True,
        "intent": intent_before,
    }, f"rc={rc} stderr tail: {err[-1500:]}"
