"""018 WI-5a: intent, commit and the ``delete_book`` orchestrator.

Matrix cases I-1 .. I-4, T-1, D-1 .. D-9 (incl. D-7b), V-1, H-1, H-2, H-3.
``reader3_app.library_delete`` is imported lazily through ``ld()``; new attributes
(``server._stats_generation`` etc.) are read at call time.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from delete_world import (
    ABSENT,
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    READABLE_LU_KIND_IDS,
    READABLE_LU_KINDS,
    SCHEMA_KIND_IDS,
    SCHEMA_KINDS,
    SUBPROCESS_TIMEOUT_S,
    U,
    V,
    Fault,
    Holder,
    IdentityProbe,
    InvalidatorRecorder,
    StepRecorder,
    SyscallLog,
    acquire_spy,
    chroma_env,  # noqa: F401 - fixture
    child_env,
    conv,
    dot_entries,
    f1_world,
    install_hook,
    intents,
    isolate_invalidators,
    ld,
    listing,
    make_book,
    make_intent,
    new_world,
    paired,
    probe_lock,
    put_file,
    read_collections,
    resolver_maps,
    schema_kind_layout,
    seat_resolver,
    server_module,
    tombstones,
    tree_bytes,
    under,
    warm,
    write_collections,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "reader3_app"

EXPECTED_STEPS = (
    "swept",
    "locked",
    "intent_written",
    "committed",
    "fin_collections",
    "fin_caches",
    "conv_published",
    "conv_done",
    "rmtree_done",
    "intent_removed",
)


def _reader3_messages(caplog, min_level=logging.DEBUG):
    return [r.getMessage() for r in caplog.records if r.name.startswith("reader3") and r.levelno >= min_level]


def _files(tree):
    return {k: v for k, v in (tree or {}).items() if v != "<dir>"}


def _outside_r_and_books(root):
    tree = tree_bytes(root) or {}
    return {k: v for k, v in tree.items() if not (k == "books" or k.startswith("books/") or k == "convroot" or k.startswith("convroot/"))}


def _book_text(books, folder="a_data"):
    from reader3_app import book_store

    return book_store.load_book_cached(folder, str(books)).spine[0].text


def _search_hits(books, term, folder="a_data"):
    from reader3_app import search_service

    return search_service.search_book(folder, search_service.SearchQuery(term=term), books_dir=str(books)).results


def _warm_caches(books, folder="a_data"):
    from reader3_app import book_store, search_service

    book_store.load_book_cached(folder, str(books))
    search_service.load_book_index(folder, str(books), case_sensitive=False)


def _recreate(books, folder, old_stat, *, body, title="Alpha", book_uuid=U):
    make_book(books, folder, title=title, body=body, book_uuid=book_uuid)
    pkl = Path(books) / folder / "book.pkl"
    assert pkl.stat().st_size == old_stat.st_size, "precondition: the re-created book.pkl must have an equal size"
    os.utime(pkl, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert pkl.stat().st_mtime_ns == old_stat.st_mtime_ns


# =========================================================================== I-1

_PATH_SEG = st.from_regex(r"[A-Za-z0-9 é中Ü]{1,12}", fullmatch=True)
_ABS_PATH = st.lists(_PATH_SEG, min_size=1, max_size=3).map(lambda parts: "/" + "/".join(parts))


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    folder=st.from_regex(r"[A-Za-z0-9 ._\-é中]{1,40}_data", fullmatch=True),
    pid=st.integers(min_value=0, max_value=2**31),
    token=st.from_regex(r"[0-9a-f]{8}", fullmatch=True),
    mode=st.booleans(),
    uuid=st.one_of(st.none(), st.uuids(version=4).map(str)),
    root=st.one_of(st.none(), _ABS_PATH),
    coll=_ABS_PATH.map(lambda p: p + "/library_collections.json"),
)
def test_i1_intent_round_trips_every_field(tmp_path, folder, pid, token, mode, uuid, root, coll):
    """I-1: read_intent(write_intent(d, x)) == x; the filename and the 7 JSON keys are pinned."""
    m = ld()
    books = Path(tempfile.mkdtemp(dir=tmp_path))
    x = m.DeleteIntent(
        folder=folder,
        pid=pid,
        token=token,
        delete_conversations=mode,
        book_uuid=uuid,
        conversation_root=root,
        collections_path=coll,
    )

    path = m.write_intent(str(books), x)

    assert Path(path).name == m.intent_name(folder, pid, token)
    assert m.read_intent(path) == x
    raw = json.loads(Path(path).read_bytes())
    assert set(raw) == {
        "folder",
        "pid",
        "token",
        "delete_conversations",
        "book_uuid",
        "conversation_root",
        "collections_path",
    }
    assert sorted(n for n in os.listdir(books) if n != ".locks") == [m.intent_name(folder, pid, token)]


# =========================================================================== I-2


def test_i2_intent_write_failure_leaves_no_intent_and_no_temp(tmp_path, monkeypatch):
    """I-2: EIO on the intent's publish -> OSError, and nothing is left in books_dir."""
    m = ld()
    books = tmp_path / "books"
    books.mkdir()
    f_replace = Fault(monkeypatch, "replace", lambda s, d: m.INTENT_RE.match(os.path.basename(d)) is not None)
    f_rename = Fault(monkeypatch, "rename", lambda s, d: m.INTENT_RE.match(os.path.basename(d)) is not None)

    with pytest.raises(OSError):
        m.write_intent(str(books), make_intent("a_data", mode=False, uuid=U, root=tmp_path / "R", coll=tmp_path / "c.json"))

    assert f_replace.hits or f_rename.hits, "the intent publish was never attempted"
    assert [n for n in os.listdir(books) if n != ".locks"] == []


# =========================================================================== I-3


def test_i3_intent_is_durable_and_book_untouched_at_the_commit_rename(tmp_path, monkeypatch):
    """I-3: fsync(tmp at full size) < replace(intent) < fsync(books dir) < rename(book -> tombstone)."""
    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    before = tree_bytes(w.books / "a_data")
    log = SyscallLog(monkeypatch)
    seen = []

    def spy_for(name):
        inner = getattr(os, name)

        def wrapped(src, dst, *a, **kw):
            if m.TOMBSTONE_RE.match(os.path.basename(os.fsdecode(dst))):
                names = intents(w.books)
                obj = m.read_intent(w.books / names[0]) if len(names) == 1 else None
                seen.append(
                    {
                        "via": name,
                        "dst": os.path.basename(os.fsdecode(dst)),
                        "intents": names,
                        "intent": obj,
                        "intent_bytes": (w.books / names[0]).read_bytes() if len(names) == 1 else None,
                        "book_untouched": tree_bytes(w.books / "a_data") == before,
                    }
                )
            return inner(src, dst, *a, **kw)

        return wrapped

    monkeypatch.setattr(os, "rename", spy_for("rename"))
    monkeypatch.setattr(os, "replace", spy_for("replace"))

    w.delete(mode=False)

    assert len(seen) == 1, seen
    commit = seen[0]
    assert len(commit["intents"]) == 1, "exactly one intent must exist at the commit rename"
    assert commit["intent"].folder == "a_data"
    assert commit["book_untouched"]
    parsed = m.parse_tombstone(commit["dst"])
    assert parsed[1:] == (commit["intent"].pid, commit["intent"].token)

    books_real = os.path.realpath(w.books)
    intent_real = os.path.join(books_real, commit["intents"][0])
    tomb_real = os.path.join(books_real, commit["dst"])
    i_pub = log.index(lambda e: e[0] in ("replace", "rename", "link") and e[2] == intent_real)
    assert i_pub >= 0, "the intent was not published by replace/rename/link"
    tmp = log.events[i_pub][1]
    fsyncs = [k for k in range(i_pub) if log.events[k][0] == "fsync" and log.events[k][1] == tmp]
    assert fsyncs, "the intent temp file was never fsynced before its publish"
    assert log.events[fsyncs[-1]][2] == len(commit["intent_bytes"])
    i_commit = log.index(lambda e: e[0] in ("rename", "replace") and e[2] == tomb_real)
    assert i_commit > i_pub
    dir_fsync = log.index(lambda e: e[0] == "fsync" and e[1] == books_real and e[3] is True, i_pub + 1)
    assert i_pub < dir_fsync < i_commit, "no directory fsync of books_dir between the intent publish and the commit"


# =========================================================================== I-4


def _i4_base(tmp_path):
    return {
        "folder": "a_data",
        "pid": 77,
        "token": "abcdef12",
        "delete_conversations": False,
        "book_uuid": U,
        "conversation_root": str(tmp_path / "R"),
        "collections_path": str(tmp_path / "config" / "library_collections.json"),
    }


I4_VARIANTS = ["a-empty", "b-not-json", "c-no-collections-path", "d-traversal-uuid", "e-relative-root"]


@pytest.mark.parametrize("variant", I4_VARIANTS)
def test_i4_unreadable_intent_is_reported_not_raised(tmp_path, variant):
    """I-4: (a)(b)(c)(e) raise IntentUnreadable; (d) reads with book_uuid None; the bytes never change."""
    m = ld()
    books = tmp_path / "books"
    books.mkdir()
    body = _i4_base(tmp_path)
    if variant == "a-empty":
        payload = b""
    elif variant == "b-not-json":
        payload = b"{not json"
    else:
        if variant == "c-no-collections-path":
            del body["collections_path"]
        elif variant == "d-traversal-uuid":
            body["book_uuid"] = "../etc"
        elif variant == "e-relative-root":
            body["conversation_root"] = "convs"
        payload = json.dumps(body).encode("utf-8")
    path = put_file(books / m.intent_name("a_data", 77, "abcdef12"), payload)

    if variant == "d-traversal-uuid":
        got = m.read_intent(path)
        assert got.book_uuid is None
    else:
        with pytest.raises(m.IntentUnreadable):
            m.read_intent(path)
    assert path.read_bytes() == payload


# =========================================================================== T-1


def test_t1a_commit_renames_to_the_paired_tombstone(tmp_path):
    """T-1(a): the commit renames the folder to ``tombstone_name(...)``, bytes intact."""
    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "x")])
    before = tree_bytes(w.books / "a_data")
    intent = make_intent("a_data", mode=False, uuid=U, root=w.R, coll=w.coll)
    m.write_intent(str(w.books), intent)

    m.commit_tombstone(str(w.books), intent)

    tomb = w.books / m.tombstone_name("a_data", 77, "abcdef12")
    assert tree_bytes(tomb) == before
    assert not (w.books / "a_data").exists()


def test_t1b_commit_of_a_missing_source_is_book_gone(tmp_path):
    """T-1(b): the folder vanished before the commit -> exactly BookGone, no tombstone."""
    from reader3_app.book_lock import BookGone

    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    intent = make_intent("a_data", mode=False, uuid=U, root=w.R, coll=w.coll)
    m.write_intent(str(w.books), intent)
    shutil.rmtree(w.books / "a_data")

    with pytest.raises(FileNotFoundError) as exc_info:
        m.commit_tombstone(str(w.books), intent)

    assert type(exc_info.value) is BookGone
    assert tombstones(w.books) == []


# =========================================================================== D-1


def _d1_world(tmp_path):
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")])
    put_file(w.R / U / "old.json", b'{"old": true}')
    write_collections(w.coll, {"c1": ["a_data", "b_data"]})
    return w


@pytest.mark.parametrize("mode", [False, True], ids=["a-false", "b-true"])
def test_d1_delete_book_happy_path_both_modes(tmp_path, monkeypatch, mode):
    """D-1: the book is gone, no dot-names, collections cleaned; the hook sequence equals STEPS."""
    w = _d1_world(tmp_path)
    rec = StepRecorder()
    install_hook(monkeypatch, rec)

    w.delete(mode=mode)

    assert "a_data" not in listing(w.books)
    assert not (w.books / "a_data").exists()
    assert dot_entries(w.books) == []
    assert read_collections(w.coll) == {"c1": ["b_data"]}
    if mode:
        assert not (w.R / U).exists()
        expected = [s for s in EXPECTED_STEPS if s != "conv_published"]
    else:
        assert sorted(os.listdir(w.R / U)) == sorted([f"{CID_FRESH}.json", f"{CID_COLLIDE}.json", "old.json"])
        expected = list(EXPECTED_STEPS[:6]) + ["conv_published", "conv_published"] + list(EXPECTED_STEPS[7:])
    assert rec.steps == expected


# =========================================================================== D-2


def test_d2a_lock_busy_leaves_everything_untouched(tmp_path, monkeypatch, chroma_env):  # noqa: F811
    """D-2(a): SH "reindex" held -> BookLockBusy("reindex"); book, intents, resolver, chroma untouched."""
    from reader3_app import book_lock

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    write_collections(w.coll, {"c1": ["a_data"]})
    resolver = seat_resolver(monkeypatch, w.books)
    probe = IdentityProbe(resolver, "a_data", U, w.books / "a_data" / "chroma_db")
    before = tree_bytes(w.books / "a_data")
    coll_before = w.coll.read_bytes()

    holder = Holder(str(w.books), "a_data", book_lock.SHARED, "reindex", str(tmp_path))
    try:
        holder.start()
        with pytest.raises(book_lock.BookLockBusy) as exc_info:
            w.delete(mode=False)
    finally:
        holder.release()

    assert exc_info.value.holder_category == "reindex"
    assert tree_bytes(w.books / "a_data") == before
    assert dot_entries(w.books) == []
    assert w.coll.read_bytes() == coll_before
    probe.assert_untouched()


def test_d2b_missing_folder_is_book_gone(tmp_path):
    """D-2(b): no such folder -> BookGone; no intent, no tombstone, collections identical."""
    from reader3_app.book_lock import BookGone

    w = new_world(tmp_path / "w")
    write_collections(w.coll, {"c1": ["a_data"]})
    coll_before = w.coll.read_bytes()

    with pytest.raises(FileNotFoundError) as exc_info:
        w.delete(mode=False)

    assert type(exc_info.value) is BookGone
    assert dot_entries(w.books) == []
    assert w.coll.read_bytes() == coll_before


def test_d2c_folder_removed_before_the_lock_is_book_gone(tmp_path, monkeypatch):
    """D-2(c): the folder vanishes at ``swept`` -> the in-lock recheck raises BookGone; nothing left."""
    from reader3_app.book_lock import BookGone

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    write_collections(w.coll, {"c1": ["a_data"]})
    coll_before = w.coll.read_bytes()

    def on_step(name, nth):
        if name == "swept":
            shutil.rmtree(w.books / "a_data")

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    with pytest.raises(FileNotFoundError) as exc_info:
        w.delete(mode=False)

    assert type(exc_info.value) is BookGone
    assert dot_entries(w.books) == []
    assert w.coll.read_bytes() == coll_before


# =========================================================================== D-3

D3_ROWS = {
    # row: (has conversations, root is R, ai_meta, mode, expected)
    "a": (True, False, U, False, "conversation_root"),
    "b": (True, True, "../x", False, "book_uuid"),
    "c": (True, True, "not-a-uuid", False, "book_uuid"),
    "d": (False, False, U, False, "delete"),
    "e": (False, True, "../x", False, "delete"),
    "f": (True, False, U, True, "delete"),
    "g": (True, True, "../x", True, "delete"),
    "h": (True, True, ABSENT, False, "book_uuid"),
    "i": (True, True, b"{not json", False, "book_uuid"),
    "j": (True, True, {"book_uuid": 7}, False, "book_uuid"),
}


@pytest.mark.parametrize("row", list(D3_ROWS))
def test_d3_refusals_before_commit_point_leave_book_byte_identical(tmp_path, monkeypatch, caplog, chroma_env, row):  # noqa: F811
    """D-3: the in-lock refusals (Q2/Q3) leave everything identical; the other rows delete."""
    caplog.set_level(logging.DEBUG)
    m = ld()
    has_convs, root_is_r, meta, mode, expected = D3_ROWS[row]
    w = new_world(tmp_path / "w")
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")] if has_convs else []
    make_book(w.books, "a_data", book_uuid=meta, convs=convs)
    write_collections(w.coll, {"c1": ["a_data"]})
    resolver = seat_resolver(monkeypatch, w.books)
    probe = IdentityProbe(resolver, "a_data", U, w.books / "a_data" / "chroma_db") if meta == U and expected != "delete" else None
    before = tree_bytes(w.books / "a_data")
    coll_before = w.coll.read_bytes()
    maps_before = resolver_maps(resolver)
    root = "R" if root_is_r else None

    if expected != "delete":
        with pytest.raises(m.DeleteRefused) as exc_info:
            w.delete(mode=mode, root=root)
        assert exc_info.value.reason == expected
        assert tree_bytes(w.books / "a_data") == before
        if row == "h":
            assert not (w.books / "a_data" / "ai_meta.json").exists()
        if row == "i":
            assert (w.books / "a_data" / "ai_meta.json").read_bytes() == b"{not json"
        assert dot_entries(w.books) == []
        assert w.coll.read_bytes() == coll_before
        assert probe_lock(w.books, "a_data", "exclusive") == ("acquired", None)
        assert resolver_maps(resolver) == maps_before
        if probe is not None:
            probe.assert_untouched()
        return

    w.delete(mode=mode, root=root)

    assert "a_data" not in listing(w.books)
    assert dot_entries(w.books) == []
    if row == "f":
        assert any("conversation root" in msg.lower() for msg in _reader3_messages(caplog, logging.WARNING))
    if row == "g":
        assert any("book_uuid" in msg for msg in _reader3_messages(caplog))
    if row in ("f", "g"):
        assert not (w.R.parent / "x").exists()
        assert not (w.R / "x").exists()


# =========================================================================== D-4


def test_d4_failure_after_commit_point_is_left_for_sweep(tmp_path, monkeypatch, caplog):
    """D-4: EIO on the first publish -> returns, logs ERROR, tombstone + intent left for the sweep."""
    from reader3_app.book_lock import BookGone

    caplog.set_level(logging.DEBUG)
    ref = f1_world(tmp_path / "ref")
    ref.delete(mode=False)
    expected = ref.state()

    w = f1_world(tmp_path / "w")
    _warm_caches(w.books)
    old_stat = os.stat(w.books / "a_data" / "book.pkl")
    fault = Fault(monkeypatch, "replace", lambda s, d: under(d, w.R))

    w.delete(mode=False)

    assert fault.hits, "the injected EIO never fired"
    assert _reader3_messages(caplog, logging.ERROR), "no ERROR was logged"
    assert "a_data" not in listing(w.books)
    assert len(tombstones(w.books)) == 1
    assert len(intents(w.books)) == 1

    with pytest.raises(FileNotFoundError) as exc_info:
        w.delete(mode=False)
    assert type(exc_info.value) is BookGone

    _recreate(w.books, "a_data", old_stat, body="BBBB bravo")
    assert _book_text(w.books) == "BBBB bravo"
    # The re-created book is removed again so the final sweep sees no live same-name
    # book (law 7 would otherwise legitimately keep the collections entry).
    shutil.rmtree(w.books / "a_data")

    fault.armed = False
    w.sweep()
    assert w.state() == expected


def _fault_books_dir_fsync_after_commit(monkeypatch, books):
    """A delegating ``os.fsync`` that raises EIO on a directory fsync of ``books`` once a tombstone
    is in it -- i.e. the commit rename succeeded and only its durability step fails. The intent's
    own ``books`` fsync (no tombstone yet) goes through."""
    import errno

    from delete_world import fd_path

    m = ld()
    real = os.fsync
    books_real = os.path.realpath(books)
    hits = []
    armed = [True]

    def fsync(fd):
        try:
            path = fd_path(fd)
        except OSError:
            path = None
        if armed[0] and path == books_real and any(m.parse_tombstone(n) for n in os.listdir(books_real)):
            hits.append(path)
            raise OSError(errno.EIO, os.strerror(errno.EIO), path)
        return real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return hits, armed


def test_d4b_dir_fsync_failure_after_commit_rename_is_past_the_commit_point(tmp_path, monkeypatch, caplog):
    """D-4b (audit 20261007 #3 / #14, FX37-1): the commit rename succeeds, the ``books_dir`` fsync
    after it raises EIO -> ``delete_book`` returns (Q-F: past the commit point), logs ERROR, the
    caches are invalidated (folder-scoped invalidator called, book cache cleared), the book is gone;
    the tombstone + intent are left for the sweep, which then finishes it to the reference state."""
    from reader3_app import book_store

    caplog.set_level(logging.DEBUG)
    ref = f1_world(tmp_path / "ref")
    ref.delete(mode=False)
    expected = ref.state()

    w = f1_world(tmp_path / "w")
    m = isolate_invalidators(monkeypatch)
    rec = InvalidatorRecorder()
    m.register_invalidator(rec, folder_scoped=True)
    _warm_caches(w.books)
    assert book_store.load_book_cached.cache_info().currsize >= 1
    hits, armed = _fault_books_dir_fsync_after_commit(monkeypatch, w.books)

    err = None
    try:
        w.delete(mode=False)
    except Exception as exc:  # noqa: BLE001 - the outcome is the observation
        err = exc

    assert {
        "error": None if err is None else type(err).__name__,
        "fault_fired": bool(hits),
        "logged_error": bool(_reader3_messages(caplog, logging.ERROR)),
        "listed": "a_data" in listing(w.books),
        "invalidated": ("a_data", U) in rec.calls,
        "book_cache": book_store.load_book_cached.cache_info().currsize,
        "tombstones": len(tombstones(w.books)),
        "intents": len(intents(w.books)),
    } == {
        "error": None,
        "fault_fired": True,
        "logged_error": True,
        "listed": False,
        "invalidated": True,
        "book_cache": 0,
        "tombstones": 1,
        "intents": 1,
    }

    armed[0] = False
    w.sweep()
    assert w.state() == expected


# =========================================================================== D-5


def test_d5_pre_commit_failure_keeps_book_collections_and_intent_is_swept(tmp_path, monkeypatch):
    """D-5: EIO on the commit rename -> OSError; nothing changed, caches kept; the sweep drops the intent."""
    from reader3_app import book_store

    m = ld()
    w = f1_world(tmp_path / "w")
    before = tree_bytes(w.books / "a_data")
    r_before = tree_bytes(w.R)
    _warm_caches(w.books)
    fault = Fault(monkeypatch, "rename", lambda s, d: m.TOMBSTONE_RE.match(os.path.basename(d)) is not None)
    Fault(monkeypatch, "replace", lambda s, d: m.TOMBSTONE_RE.match(os.path.basename(d)) is not None)

    with pytest.raises(OSError):
        w.delete(mode=False)

    assert tree_bytes(w.books / "a_data") == before
    assert tombstones(w.books) == []
    assert "a_data" in read_collections(w.coll)["c1"]
    assert tree_bytes(w.R) == r_before
    assert book_store.load_book_cached.cache_info().currsize >= 1

    fault.armed = False
    w.sweep()
    assert intents(w.books) == []


# =========================================================================== D-6


def _d6_world(tmp_path):
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    make_book(w.books, "x_data", book_uuid=V)
    uy = "99999999-0000-4000-8000-0000000000f9"
    p = paired(w.books, "y_data", mode=False, uuid=uy, root=w.R, coll=w.coll, book_uuid=uy, convs=[conv(CID_FRESH, D_MID, "y")])
    return w, p, uy


def test_d6a_delete_sweeps_unrelated_tombstones_first(tmp_path, monkeypatch):
    """D-6(a): at ``swept`` y's entries are gone and published; a_data is then deleted."""
    w, p, uy = _d6_world(tmp_path)
    at_swept = {}

    def on_step(name, nth):
        if name == "swept":
            at_swept["dots"] = dot_entries(w.books)
            at_swept["published"] = (w.R / uy / f"{CID_FRESH}.json").is_file()

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    w.delete(mode=False)

    assert p.tomb.name not in at_swept["dots"] and p.intent.name not in at_swept["dots"]
    assert at_swept["published"]
    assert not (w.books / "a_data").exists()
    assert "a_data" not in listing(w.books)


def test_d6b_busy_unrelated_tombstone_does_not_block_the_delete(tmp_path):
    """D-6(b): SH "search" on y_data -> a_data is deleted anyway; y's tombstone untouched."""
    from reader3_app import book_lock

    w, p, uy = _d6_world(tmp_path)
    tomb_before = tree_bytes(p.tomb)

    holder = Holder(str(w.books), "y_data", book_lock.SHARED, "search", str(tmp_path))
    try:
        holder.start()
        w.delete(mode=False)
    finally:
        holder.release()

    assert not (w.books / "a_data").exists()
    assert tree_bytes(p.tomb) == tomb_before


# =========================================================================== D-7 / D-7b


def _thread(book_uuid=U):
    from reader3_app.ai.conversations import ConversationThread

    return ConversationThread(
        schema_version=1, book_uuid=book_uuid, book_folder="a_data", conversation_id=CID_FRESH, provider="stub"
    )


def test_d7_conversation_arriving_before_sweep_is_seen(tmp_path, monkeypatch):
    """D-7: a conversation saved at ``swept`` makes the root-None false-mode delete refuse."""
    from reader3_app.ai import conversations

    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    after_hook = {}

    def on_step(name, nth):
        if name == "swept":
            conversations.save_conversation(str(w.books), thread=_thread())
            after_hook["tree"] = tree_bytes(w.books / "a_data")

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    with pytest.raises(m.DeleteRefused) as exc_info:
        w.delete(mode=False, root=None)

    assert exc_info.value.reason == "conversation_root"
    assert tree_bytes(w.books / "a_data") == after_hook["tree"]
    assert dot_entries(w.books) == []


def test_d7b_conversation_arriving_between_sweep_and_lock_is_seen(tmp_path, monkeypatch):
    """D-7b: a conversation saved just before the EX acquire is seen by the in-lock check."""
    from reader3_app.ai import conversations

    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    before = tree_bytes(w.books / "a_data")
    resolver = seat_resolver(monkeypatch, w.books)
    warm(resolver, "a_data", U)
    maps_before = resolver_maps(resolver)

    fired = acquire_spy(
        monkeypatch,
        before=lambda: conversations.save_conversation(str(w.books), thread=_thread()),
        when=lambda folder, holder, mode: holder == "delete" and folder == "a_data",
    )

    with pytest.raises(m.DeleteRefused) as exc_info:
        w.delete(mode=False, root=None)

    assert fired == [1]
    assert exc_info.value.reason == "conversation_root"
    conv_file = w.books / "a_data" / "ai_conversations" / f"{CID_FRESH}.json"
    assert conv_file.is_file()
    after = tree_bytes(w.books / "a_data")
    assert {k: v for k, v in after.items() if not k.startswith("ai_conversations")} == before
    assert dot_entries(w.books) == []
    assert resolver_maps(resolver) == maps_before


# =========================================================================== D-8


def _d8_world(tmp_path, monkeypatch, kind):
    w = new_world(tmp_path / "w")
    layout = schema_kind_layout(kind, n_valid=2)
    put_file(w.R / U / f"{CID_COLLIDE}.json", layout.target)
    meta = ABSENT if kind == "unresolvable_uuid" else U
    make_book(w.books, "a_data", book_uuid=meta, convs=layout.convs)
    write_collections(w.coll, {"c1": ["a_data"]})
    resolver = seat_resolver(monkeypatch, w.books)
    probe = IdentityProbe(resolver, "a_data", U, w.books / "a_data" / "chroma_db")
    return w, layout, probe


@pytest.mark.parametrize(("kind", "klass", "reason"), SCHEMA_KINDS, ids=SCHEMA_KIND_IDS)
def test_d8a_unreadable_conversation_refuses_before_commit(tmp_path, monkeypatch, chroma_env, kind, klass, reason):  # noqa: F811
    """D-8(a): false mode pre-scans in the lock; unreadable kinds refuse, readable kinds (W5-17) delete."""
    m = ld()
    w, layout, probe = _d8_world(tmp_path, monkeypatch, kind)
    book_before = tree_bytes(w.books / "a_data")
    r_before = tree_bytes(w.R)
    coll_before = w.coll.read_bytes()
    outside_before = _outside_r_and_books(w.root)

    if klass == "unreadable":
        with pytest.raises(m.DeleteRefused) as exc_info:
            w.delete(mode=False)
        if kind == "unresolvable_uuid":
            assert exc_info.value.reason == "book_uuid"
        else:
            assert exc_info.value.reason == "conversation_unreadable"
            assert exc_info.value.path == layout.bad_name
        assert "a_data" in listing(w.books)
        assert tree_bytes(w.books / "a_data") == book_before
        assert dot_entries(w.books) == []
        assert tree_bytes(w.R) == r_before
        assert w.coll.read_bytes() == coll_before
        assert _outside_r_and_books(w.root) == outside_before
        probe.assert_untouched()
        assert probe_lock(w.books, "a_data", "exclusive") == ("acquired", None)
        return

    w.delete(mode=False)

    assert "a_data" not in listing(w.books)
    assert dot_entries(w.books) == []
    assert _files(tree_bytes(w.R)) == {f"{U}/{name}": payload for name, payload in layout.convs}
    assert read_collections(w.coll) == {"c1": []}


@pytest.mark.parametrize("kind", SCHEMA_KIND_IDS)
def test_d8b_true_mode_skips_the_prescan(tmp_path, monkeypatch, chroma_env, kind):  # noqa: F811
    """D-8(b): true mode never pre-scans -> every kind deletes and R/U is removed."""
    w, layout, probe = _d8_world(tmp_path, monkeypatch, kind)

    w.delete(mode=True)

    assert "a_data" not in listing(w.books)
    assert not (w.books / "a_data").exists()
    assert (w.R / U).exists() == (kind == "unresolvable_uuid")  # W5-23: no uuid on disk -> R/U is kept


def test_d8b_unresolvable_uuid_keeps_project_root_and_warns(tmp_path, monkeypatch, caplog, chroma_env):  # noqa: F811
    """D-8(b), W5-23: true mode with no uuid on disk -> book deleted, R byte-identical (R/U kept, no R/V
    created for the file's own uuid V), and a WARNING names book_uuid (as F-5(c))."""
    caplog.set_level(logging.DEBUG)
    w, layout, probe = _d8_world(tmp_path, monkeypatch, "unresolvable_uuid")
    r_before = tree_bytes(w.R)

    w.delete(mode=True)

    assert "a_data" not in listing(w.books)
    assert not (w.books / "a_data").exists()
    assert tree_bytes(w.R) == r_before
    assert not (w.R / V).exists()
    assert any("book_uuid" in msg for msg in _reader3_messages(caplog, logging.WARNING)), _reader3_messages(caplog)


# =========================================================================== D-9


@pytest.mark.parametrize("exit_path", ["i-collections-eio", "ii-finalize-conserves"])
def test_d9_post_commit_invalidation_does_not_depend_on_reaching_fin_caches(tmp_path, monkeypatch, caplog, exit_path):
    """D-9: both early exits after the commit still clear the caches and bump the stats generation."""
    from reader3_app import book_store, search_service

    caplog.set_level(logging.DEBUG)
    server = server_module()
    ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", body="AAAA alpha", book_uuid=U)
    make_book(w.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    write_collections(w.coll, {"c1": ["a_data", "b_data"]})
    _warm_caches(w.books)
    assert _search_hits(w.books, "alpha")
    old_stat = os.stat(w.books / "a_data" / "book.pkl")
    g0 = getattr(server, "_stats_generation")

    if exit_path.startswith("i-"):
        coll_real = os.path.realpath(w.coll)
        Fault(monkeypatch, "replace", lambda s, d: d == coll_real)
    else:

        def on_step(name, nth):
            if name == "committed":
                tomb = w.books / tombstones(w.books)[0]
                put_file(tomb / "ai_conversations" / "00000000-0000-4000-8000-000000000000.json", b"{trunc")

        install_hook(monkeypatch, StepRecorder(on_step=on_step))

    w.delete(mode=False)

    assert book_store.load_book_cached.cache_info().currsize == 0
    assert search_service.load_book_index.cache_info().currsize == 0
    assert getattr(server, "_stats_generation") > g0
    assert _reader3_messages(caplog, logging.WARNING), "the early exit was not logged"

    if exit_path.startswith("ii-"):
        tomb_name = tombstones(w.books)[0]
        intent_name = intents(w.books)[0]
        tomb_before = tree_bytes(w.books / tomb_name)
        intent_before = (w.books / intent_name).read_bytes()

    install_hook(monkeypatch, None)
    _recreate(w.books, "a_data", old_stat, body="BBBB bravo")
    assert _book_text(w.books) == "BBBB bravo"
    assert _search_hits(w.books, "alpha") == []

    if exit_path.startswith("ii-"):
        report = w.sweep()
        assert report.conserved == [tomb_name]
        assert tree_bytes(w.books / tomb_name) == tomb_before
        assert (w.books / intent_name).read_bytes() == intent_before


# =========================================================================== V-1


@pytest.mark.parametrize("mode", [False, True], ids=["false", "true"])
def test_v1_service_level_visibility_at_every_step(tmp_path, monkeypatch, mode):
    """V-1: before ``committed`` both books are listed (title "Alpha"); from ``committed`` on, only b_data."""
    from reader3_app import book_store

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", title="Alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
    make_book(w.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    seen = []

    def on_step(name, nth):
        ids = listing(w.books)
        title = book_store.load_book_cached("a_data", str(w.books)).metadata.title if "a_data" in ids else None
        seen.append((name, ids, title))

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    w.delete(mode=mode)

    names = [s[0] for s in seen]
    assert "committed" in names
    cut = names.index("committed")
    for name, ids, title in seen[:cut]:
        assert (ids, title) == (["a_data", "b_data"], "Alpha"), name
    for name, ids, title in seen[cut:]:
        assert ids == ["b_data"], name
    assert sorted(set(names)) == sorted(set(EXPECTED_STEPS) - ({"conv_published"} if mode else set()))


# =========================================================================== H-1


def _assigns_step_hook(node) -> bool:
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    for t in targets:
        if isinstance(t, ast.Name) and t.id == "_STEP_HOOK":
            return True
        if isinstance(t, ast.Attribute) and t.attr == "_STEP_HOOK":
            return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr":
        args = node.args
        if len(args) >= 2 and isinstance(args[1], ast.Constant) and args[1].value == "_STEP_HOOK":
            return True
    return False


def test_h1_step_hook_is_inert_in_production():
    """H-1: a fresh interpreter sees ``_STEP_HOOK is None`` and the pinned STEPS; nothing in src sets it."""
    ld()  # red guard in the parent, before any child is spawned
    code = (
        "import json, reader3_app.library_delete as m; "
        "print(json.dumps({'hook_is_none': m._STEP_HOOK is None, 'steps': list(m.STEPS)}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S, env=child_env()
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got == {"hook_is_none": True, "steps": list(EXPECTED_STEPS)}

    module_path = SRC_DIR / "library_delete.py"
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = set()
        if path == module_path:
            for stmt in tree.body:
                value = getattr(stmt, "value", None)
                if (
                    isinstance(stmt, (ast.Assign, ast.AnnAssign))
                    and _assigns_step_hook(stmt)
                    and isinstance(value, ast.Constant)
                    and value.value is None
                ):
                    allowed.add(id(stmt))
        for node in ast.walk(tree):
            if _assigns_step_hook(node) and id(node) not in allowed:
                offenders.append(f"{path.relative_to(SRC_DIR)}:{node.lineno}")
    assert offenders == []

    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    env_reads = [
        n.lineno
        for n in ast.walk(tree)
        if (isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv", "environb"))
        or (isinstance(n, ast.Name) and n.id in ("environ", "getenv"))
    ]
    assert env_reads == []


# =========================================================================== H-2


def _h2_expected(mode):
    ge1 = ">=1"
    rows = [
        ("swept", True, False, False, True, 1, ge1, True),
        ("locked", True, False, False, True, 1, ge1, True),
        ("intent_written", True, False, True, True, 1, ge1, True),
        ("committed", False, True, True, True, 1, ge1, True),
        ("fin_collections", False, True, True, False, 1, ge1, True),
        ("fin_caches", False, True, True, False, 1, 0, False),
        ("conv_published#1", False, True, True, False, 2, 0, False),
        ("conv_published#2", False, True, True, False, 2, 0, False),
        ("conv_done", False, True, True, False, 2, 0, False),
        ("rmtree_done", False, False, True, False, 2, 0, False),
        ("intent_removed", False, False, False, False, 2, 0, False),
    ]
    if not mode:
        return rows
    out = []
    for row in rows:
        if row[0].startswith("conv_published"):
            continue
        if row[0] in ("conv_done", "rmtree_done", "intent_removed"):
            row = row[:5] + (0,) + row[6:]
        out.append(row)
    return out


@pytest.mark.parametrize("mode", [False, True], ids=["false", "true"])
def test_h2_hooks_fire_where_they_claim(tmp_path, monkeypatch, mode):
    """H-2: the exact state table observed at every step (F-1 fixture, publish sorted by filename)."""
    from reader3_app import book_store

    w = f1_world(tmp_path / "w")
    resolver = seat_resolver(monkeypatch, w.books)
    warm(resolver, "a_data", U)
    book_store.load_book_cached("a_data", str(w.books))
    rows = []

    def on_step(name, nth):
        label = f"{name}#{nth}" if name == "conv_published" else name
        r_u = w.R / U
        r_count = len([n for n in os.listdir(r_u) if (r_u / n).is_file()]) if r_u.is_dir() else 0
        cur = book_store.load_book_cached.cache_info().currsize
        in_coll = any("a_data" in ids for ids in read_collections(w.coll).values())
        rows.append(
            (
                label,
                "a_data" in listing(w.books),
                bool(tombstones(w.books)),
                bool(intents(w.books)),
                in_coll,
                r_count,
                ">=1" if cur >= 1 else cur,
                "a_data" in resolver._folder_to_uuid,
            )
        )

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    w.delete(mode=mode)

    assert rows == _h2_expected(mode)


# =========================================================================== H-3


def test_h3a_isolated_registry_is_restored(tmp_path, monkeypatch):
    """H-3(a): an invalidator registered inside a patched registry is gone after the context."""
    m = ld()
    before = list(m._INVALIDATORS)
    rec = InvalidatorRecorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(m, "_INVALIDATORS", list(m._INVALIDATORS))
        m.register_invalidator(rec, folder_scoped=True)
    assert m._INVALIDATORS == before

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    w.delete(mode=False)

    assert rec.calls == []


def test_h3b_unregister_removes_the_invalidator(tmp_path, monkeypatch):
    """H-3(b): ``register_invalidator`` returns an unregister callable that works."""
    m = isolate_invalidators(monkeypatch)
    rec2 = InvalidatorRecorder()
    unregister = m.register_invalidator(rec2, folder_scoped=False)
    assert callable(unregister)
    unregister()

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    w.delete(mode=False)

    assert rec2.calls == []


def test_h3c_server_forget_folder_is_resolved_at_call_time(tmp_path, monkeypatch):
    """H-3(c): a resolver installed at the seam after import is the one ``forget_folder`` reaches."""
    server_module()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    r2 = seat_resolver(monkeypatch, w.books)
    warm(r2, "a_data", U)

    w.delete(mode=False)

    assert "a_data" not in r2._folder_to_uuid


# =========================================================================== CP2 additions (WI-5 test-review gaps)
#
# Additive only: the recorded cases above are unchanged.


def test_d8b_unresolvable_uuid_leaves_the_files_own_uuid_dir_untouched(tmp_path, monkeypatch, chroma_env):  # noqa: F811
    """D-8(b) (CP2 L1, W5-23): with no uuid on disk, true mode must not touch ``R/V`` (V is a
    conversation file's own uuid). ``R/V/x.json`` is seeded first, so "no R/V afterwards" cannot
    pass vacuously: R/V -- and R as a whole -- stay byte-identical."""
    w, layout, probe = _d8_world(tmp_path, monkeypatch, "unresolvable_uuid")
    put_file(w.R / V / "x.json", b'{"x": 1}')
    rv_before = tree_bytes(w.R / V)
    r_before = tree_bytes(w.R)

    w.delete(mode=True)

    assert "a_data" not in listing(w.books)
    assert not (w.books / "a_data").exists()
    assert tree_bytes(w.R / V) == rv_before
    assert (w.R / V / "x.json").read_bytes() == b'{"x": 1}'
    assert tree_bytes(w.R) == r_before


@pytest.mark.parametrize(("kind", "klass", "reason"), READABLE_LU_KINDS, ids=READABLE_LU_KIND_IDS)
def test_d8a_null_and_empty_last_updated_are_readable(tmp_path, monkeypatch, chroma_env, kind, klass, reason):  # noqa: F811
    """D-8(a) (CP2 L3, W5-17): ``last_updated: null`` and ``""`` pass the in-lock pre-scan and delete."""
    w, layout, probe = _d8_world(tmp_path, monkeypatch, kind)

    w.delete(mode=False)

    assert "a_data" not in listing(w.books)
    assert dot_entries(w.books) == []
    assert _files(tree_bytes(w.R)) == {f"{U}/{name}": payload for name, payload in layout.convs}
    assert len(layout.convs) == 3
    assert read_collections(w.coll) == {"c1": []}
