"""Shared helpers for the 018 WI-5 delete tests (matrix §0.3, `tests-20261002-170000-wi5.md`).

Written at the WI-5a red, extended additively by 5b / 5c. Nothing here imports
``reader3_app.library_delete`` at import time: every use goes through ``ld()``,
which is called inside a test or a fixture. That keeps the whole lane collectable
while the module does not exist yet (the red is then an ``ImportError`` raised
inside each test, never a collection error).

Workers that run in a spawned or ``subprocess`` child (``_probe_worker``,
``crash_child_main``, ``sweep_child_main``) live at module level and take only
picklable / string arguments. Every wait is bounded.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno as _errno
import importlib
import json
import os
import pickle
import shutil
import signal
import stat
import subprocess
import sys
import threading
import uuid as _uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pytest

from book_lock_workers import CHILD_WAIT_S, Child, Holder, outcome, write_result  # noqa: F401 - re-exported

FIXTURES_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- module access


LD_MODULE = "reader3_app.library_delete"


def ld_present() -> bool:
    """Whether ``reader3_app.library_delete`` exists, without importing it."""
    import importlib.util

    return importlib.util.find_spec(LD_MODULE) is not None


def ld():
    """``reader3_app.library_delete``, imported lazily (inside tests only).

    At red the module does not exist. Instead of letting the import raise (whose
    message the red-receipt classifier reads as an environment failure), the test
    fails with a plain ``RED:`` message. Deliberately not inside an ``except``: no
    exception context is chained into the report. Tests that spawn a child
    interpreter call this in the parent *before* spawning.
    """
    if not ld_present():
        pytest.fail(f"RED: {LD_MODULE} is not implemented", pytrace=False)
    return importlib.import_module(LD_MODULE)


# --------------------------------------------------------------------------- fixed values


class _Absent:
    def __repr__(self) -> str:
        return "ABSENT"


#: Sentinel: "omit this key / this file entirely".
ABSENT = _Absent()

CID_FRESH = "11111111-1111-4111-8111-111111111111"
CID_COLLIDE = "22222222-2222-4222-8222-222222222222"
CID_3 = "33333333-3333-4333-8333-333333333333"
ZERO_UUID = "00000000-0000-4000-8000-000000000000"

U = "aaaaaaaa-0000-4000-8000-00000000000a"
U2 = "aaaaaaaa-0000-4000-8000-0000000000a2"
V = "bbbbbbbb-0000-4000-8000-00000000000b"
W = "cccccccc-0000-4000-8000-00000000000c"

D_OLD = "2026-09-01T00:00:00Z"
D_MID = "2026-09-02T00:00:00Z"
D_NEW = "2026-09-03T00:00:00Z"

#: The EX acquire never waits (matrix §0.1), so this only bounds SH waits.
PROBE_BUDGET_S = 0.3

#: Bounded wait for any subprocess this file starts.
SUBPROCESS_TIMEOUT_S = 120.0


# --------------------------------------------------------------------------- books


def _book_object(folder: str, title: str, body: str):
    from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry

    href = "text/c0.xhtml"
    return Book(
        metadata=BookMetadata(title=title, language="en", authors=["Tester"], identifiers=[f"urn:{folder}"]),
        spine=[ChapterContent(id="c0", href=href, title="One", content=f"<p>{body}</p>", text=body, order=0)],
        toc=[TOCEntry(title="One", href=href, file_href=href, anchor="")],
        images={},
        source_file=f"{folder}.epub",
        processed_at="2026-09-01T00:00:00",
    )


def write_book_pkl(book_dir: Path, *, title: str, body: str) -> Path:
    path = Path(book_dir) / "book.pkl"
    with open(path, "wb") as f:
        pickle.dump(_book_object(Path(book_dir).name, title, body), f)
    return path


def make_book(
    books_dir,
    folder: str,
    *,
    title: str = "Alpha",
    body: str = "AAAA alpha",
    book_uuid: Any = ABSENT,
    convs: Iterable[Tuple[str, bytes]] = (),
    chroma: bool = False,
) -> Path:
    """A complete ``{folder}`` under ``books_dir``.

    ``book_uuid``: a ``str`` (written as ``{"book_uuid": s}``), a raw ``dict`` (dumped
    as is), raw ``bytes`` (written verbatim) or ``ABSENT`` (no ``ai_meta.json``).
    ``convs``: ``(filename, bytes)`` pairs from ``conv()`` / ``raw_conv()``.
    """
    d = Path(books_dir) / folder
    d.mkdir(parents=True)
    write_book_pkl(d, title=title, body=body)
    meta = d / "ai_meta.json"
    if isinstance(book_uuid, bytes):
        meta.write_bytes(book_uuid)
    elif isinstance(book_uuid, dict):
        meta.write_text(json.dumps(book_uuid), encoding="utf-8")
    elif isinstance(book_uuid, str):
        meta.write_text(json.dumps({"book_uuid": book_uuid}), encoding="utf-8")
    convs = list(convs)
    if convs:
        cdir = d / "ai_conversations"
        cdir.mkdir()
        for name, payload in convs:
            (cdir / name).write_bytes(payload)
    if chroma:
        (d / "chroma_db").mkdir()
    return d


def conv_payload(cid: str, last_updated: Any, text: str, *, own_uuid: Any = ABSENT, conversation_id: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"schema_version": 1}
    if own_uuid is not ABSENT:
        payload["book_uuid"] = own_uuid
    payload["book_folder"] = "a_data"
    payload["conversation_id"] = cid if conversation_id is None else conversation_id
    payload["provider"] = "stub"
    payload["model"] = ""
    payload["created_at"] = "2026-08-01T00:00:00Z"
    if last_updated is not ABSENT:
        payload["last_updated"] = last_updated
    payload["messages"] = [
        {"id": f"m-{cid[:8]}", "role": "user", "content": text, "timestamp": "2026-08-01T00:00:00Z", "metadata": {}}
    ]
    return payload


def conv(cid: str, last_updated: Any, text: str, *, own_uuid: Any = ABSENT) -> Tuple[str, bytes]:
    """One valid conversation file. ``last_updated`` may be ``ABSENT``, ``None`` or a non-string."""
    return (f"{cid}.json", json.dumps(conv_payload(cid, last_updated, text, own_uuid=own_uuid)).encode("utf-8"))


def raw_conv(name: str, payload: bytes) -> Tuple[str, bytes]:
    return (name, payload)


def put_file(path: Path, payload: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


# --------------------------------------------------------------------------- collections


def default_collections_path(books_dir) -> Path:
    """Q6: ``collections_service.collections_path(dirname(books_dir))``."""
    return Path(os.path.dirname(os.path.abspath(str(books_dir)))) / "config" / "library_collections.json"


def write_collections(path, mapping: Dict[str, List[str]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "collections": [
            {"id": cid, "name": cid, "created_at": "2026-08-01T00:00:00Z", "book_ids": list(ids)}
            for cid, ids in mapping.items()
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read_collections(path) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {c["id"]: list(c["book_ids"]) for c in raw["collections"]}


# --------------------------------------------------------------------------- trees and state


def tree_bytes(path, *, exclude: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """``relpath -> bytes`` for files, ``"<dir>"`` for dirs, ``("link", target)`` for symlinks.

    ``None`` when ``path`` does not exist. ``exclude`` names top-level entries to skip.
    """
    root = Path(path)
    if not os.path.lexists(root):
        return None
    if root.is_symlink():
        return {".": ("link", os.readlink(root))}
    if root.is_file():
        return {".": root.read_bytes()}
    excluded = set(exclude)
    out: Dict[str, Any] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in excluded]
            filenames = [f for f in filenames if f not in excluded]
        for name in dirnames:
            full = os.path.join(dirpath, name)
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            out[rel] = ("link", os.readlink(full)) if os.path.islink(full) else "<dir>"
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            out[rel] = ("link", os.readlink(full)) if os.path.islink(full) else Path(full).read_bytes()
    return out


def file_bytes(path) -> Optional[bytes]:
    p = Path(path)
    return p.read_bytes() if p.is_file() else None


def observable_state(books_dir, conv_root, collections_path=None) -> Dict[str, Any]:
    """Everything a user can observe after a delete: books (minus ``.locks``), R, collections."""
    coll = default_collections_path(books_dir) if collections_path is None else Path(collections_path)
    return {
        "books": tree_bytes(books_dir, exclude=(".locks",)),
        "conv": tree_bytes(conv_root) if conv_root is not None else None,
        "collections": file_bytes(coll),
    }


def dot_entries(books_dir) -> List[str]:
    """Every top-level dot-name in ``books_dir`` except ``.locks``."""
    return sorted(n for n in os.listdir(books_dir) if n.startswith(".") and n != ".locks")


def tombstones(books_dir) -> List[str]:
    m = ld()
    return sorted(n for n in os.listdir(books_dir) if m.parse_tombstone(n) is not None)


def intents(books_dir) -> List[str]:
    m = ld()
    return sorted(n for n in os.listdir(books_dir) if m.parse_intent(n) is not None)


def listing(books_dir) -> List[str]:
    from reader3_app import search_service

    return list(search_service.list_book_ids(str(books_dir)))


# --------------------------------------------------------------------------- intents / tombstones


def make_intent(folder: str, *, pid: int = 77, token: str = "abcdef12", mode: bool, uuid: Optional[str], root, coll):
    return ld().DeleteIntent(
        folder=folder,
        pid=pid,
        token=token,
        delete_conversations=mode,
        book_uuid=uuid,
        conversation_root=None if root is None else str(root),
        collections_path=str(coll),
    )


def paired(
    books_dir,
    folder: str,
    *,
    mode: bool,
    uuid: Optional[str],
    root,
    coll,
    pid: int = 77,
    token: str = "abcdef12",
    **book_kw: Any,
) -> SimpleNamespace:
    """``make_book`` + ``write_intent`` + ``commit_tombstone`` (the F-11 construction)."""
    m = ld()
    make_book(books_dir, folder, **book_kw)
    intent = make_intent(folder, pid=pid, token=token, mode=mode, uuid=uuid, root=root, coll=coll)
    m.write_intent(str(books_dir), intent)
    m.commit_tombstone(str(books_dir), intent)
    books = Path(books_dir)
    return SimpleNamespace(
        tomb=books / m.tombstone_name(folder, pid, token),
        intent=books / m.intent_name(folder, pid, token),
        obj=intent,
    )


def intent_json(folder: str, *, pid: int, token: str, mode: bool, uuid: Any, root: Any, coll: Any) -> bytes:
    """A hand-written intent file body (the 7 keys of §0.2)."""
    return json.dumps(
        {
            "folder": folder,
            "pid": pid,
            "token": token,
            "delete_conversations": mode,
            "book_uuid": uuid,
            "conversation_root": root,
            "collections_path": coll,
        }
    ).encode("utf-8")


def report_dict(report) -> Dict[str, List[str]]:
    return {f.name: list(getattr(report, f.name)) for f in dataclasses.fields(report)}


EMPTY_REPORT = {"finalized": [], "orphan_intents": [], "conserved": [], "busy": [], "unreadable": [], "failed": []}


# --------------------------------------------------------------------------- worlds


@dataclasses.dataclass
class World:
    root: Path
    books: Path
    R: Path
    coll: Path

    def delete(self, folder: str = "a_data", *, mode: bool, root: Any = "R"):
        conv_root = str(self.R) if root == "R" else (None if root is None else str(root))
        return ld().delete_book(
            str(self.books),
            folder,
            delete_conversations=mode,
            conversation_root=conv_root,
            collections_path=str(self.coll),
        )

    def sweep(self):
        return ld().sweep(str(self.books))

    def state(self) -> Dict[str, Any]:
        return observable_state(self.books, self.R, self.coll)


def new_world(root) -> World:
    root = Path(root)
    books = root / "books"
    books.mkdir(parents=True, exist_ok=True)
    return World(root=root, books=books, R=root / "convroot", coll=default_collections_path(books))


def f1_world(root) -> World:
    """The F-1 fixture: ``a_data`` (U) with CID_FRESH + CID_COLLIDE, an older ``R/U/CID_COLLIDE``,
    collections ``{c1:[a_data,b_data], c2:[a_data]}``, and a live ``b_data`` (V)."""
    w = new_world(root)
    make_book(
        w.books,
        "a_data",
        title="Alpha",
        body="AAAA alpha",
        book_uuid=U,
        convs=[conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide-book")],
    )
    make_book(w.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V)
    put_file(w.R / U / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_OLD, "collide-existing")[1])
    write_collections(w.coll, {"c1": ["a_data", "b_data"], "c2": ["a_data"]})
    return w


# --------------------------------------------------------------------------- step hook


class _Crash(BaseException):
    """Test-only crash emulation: a ``BaseException`` raised from the step hook."""


class StepRecorder:
    """Installed as ``library_delete._STEP_HOOK``. Records every step; optional per-step action.

    ``crash_at=("conv_published", 2)`` raises ``_Crash`` at the 2nd ``conv_published``.
    ``on_step(name, nth)`` runs at every step (after recording).
    """

    def __init__(self, *, crash_at: Optional[Tuple[str, int]] = None, on_step: Optional[Callable[[str, int], None]] = None):
        self.steps: List[str] = []
        self.crash_at = crash_at
        self.on_step = on_step

    def __call__(self, name: str) -> None:
        self.steps.append(name)
        nth = self.steps.count(name)
        if self.on_step is not None:
            self.on_step(name, nth)
        if self.crash_at is not None and self.crash_at == (name, nth):
            raise _Crash(f"{name}#{nth}")


def install_hook(monkeypatch: pytest.MonkeyPatch, recorder: Optional[Callable[[str], None]]) -> None:
    monkeypatch.setattr(ld(), "_STEP_HOOK", recorder)


def parse_point(point: str) -> Optional[Tuple[str, int]]:
    """``"conv_published#2" -> ("conv_published", 2)``; ``"none" -> None``."""
    if point == "none":
        return None
    if "#" in point:
        name, nth = point.split("#")
        return (name, int(nth))
    return (point, 1)


# --------------------------------------------------------------------------- invalidator isolation


def isolate_invalidators(monkeypatch: pytest.MonkeyPatch):
    """§0.2: a private copy of the registry; server registrations survive, test ones are dropped.

    Call it inside the test body (not only through the fixture) so that, at red, the
    ``ModuleNotFoundError`` from ``ld()`` is a test failure rather than a setup error.
    """
    m = ld()
    importlib.import_module("reader3_app.web.server")  # W5-23 note: server registrations land before the copy
    monkeypatch.setattr(m, "_INVALIDATORS", list(m._INVALIDATORS))
    return m


@pytest.fixture
def isolated_invalidators(monkeypatch: pytest.MonkeyPatch):
    """Fixture form of ``isolate_invalidators`` (for use once the module exists)."""
    return isolate_invalidators(monkeypatch)


class InvalidatorRecorder:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Optional[str]]] = []

    def __call__(self, folder: str, uuid: Optional[str]) -> None:
        self.calls.append((folder, uuid))


# --------------------------------------------------------------------------- acquire spy


def acquire_spy(monkeypatch: pytest.MonkeyPatch, *, before: Callable[[], None], when: Callable[[str, Optional[str], str], bool]) -> List[int]:
    """Wrap ``book_lock.acquire``: run ``before()`` once, the first time ``when(folder, holder, mode)``
    holds, then delegate. Returns a list that gets ``1`` appended when it fired."""
    from reader3_app import book_lock

    real = book_lock.acquire
    fired: List[int] = []

    def wrapper(books_dir, book_folder, *args, **kwargs):
        mode = kwargs.get("mode", book_lock.SHARED)
        holder = kwargs.get("holder")
        if not fired and when(book_folder, holder, mode):
            fired.append(1)
            before()
        return real(books_dir, book_folder, *args, **kwargs)

    monkeypatch.setattr(book_lock, "acquire", wrapper)
    return fired


# --------------------------------------------------------------------------- syscall observation / faults


def fd_path(fd: int) -> str:
    """The realpath of an open fd."""
    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
        return os.path.realpath(raw.split(b"\0", 1)[0].decode())
    return os.path.realpath(os.readlink(f"/proc/self/fd/{fd}"))


def resolve(path, dir_fd: Optional[int] = None) -> str:
    """``realpath(dirname) / basename`` (works for a path that does not exist yet)."""
    p = os.fsdecode(os.fspath(path))
    if dir_fd is not None and not os.path.isabs(p):
        p = os.path.join(fd_path(dir_fd), p)
    p = os.path.abspath(p)
    return os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))


class SyscallLog:
    """Observer of ``os.fsync`` / ``replace`` / ``rename`` / ``link`` / ``unlink`` / ``rmdir``.

    Each event is appended *after* the real call returns:
    ``("fsync", path, size, is_dir)``, ``("replace"|"rename"|"link", src, dst)``,
    ``("unlink"|"rmdir", path)``. Paths are realpaths.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: List[Tuple[Any, ...]] = []
        self._guard = threading.Lock()
        real_fsync, real_replace, real_rename = os.fsync, os.replace, os.rename
        real_link, real_unlink, real_rmdir = os.link, os.unlink, os.rmdir

        def fsync(fd):
            try:
                st = os.fstat(fd)
                path = fd_path(fd)
            except OSError:
                st, path = None, None
            real_fsync(fd)
            self._add(("fsync", path, None if st is None else st.st_size, None if st is None else stat.S_ISDIR(st.st_mode)))

        def two(kind, real):
            def wrapped(src, dst, *a, **kw):
                s = resolve(src, kw.get("src_dir_fd"))
                d = resolve(dst, kw.get("dst_dir_fd"))
                out = real(src, dst, *a, **kw)
                self._add((kind, s, d))
                return out

            return wrapped

        def one(kind, real):
            def wrapped(path, *a, **kw):
                p = resolve(path, kw.get("dir_fd"))
                out = real(path, *a, **kw)
                self._add((kind, p))
                return out

            return wrapped

        monkeypatch.setattr(os, "fsync", fsync)
        monkeypatch.setattr(os, "replace", two("replace", real_replace))
        monkeypatch.setattr(os, "rename", two("rename", real_rename))
        monkeypatch.setattr(os, "link", two("link", real_link))
        monkeypatch.setattr(os, "unlink", one("unlink", real_unlink))
        monkeypatch.setattr(os, "rmdir", one("rmdir", real_rmdir))

    def _add(self, ev: Tuple[Any, ...]) -> None:
        with self._guard:
            self.events.append(ev)

    def index(self, pred: Callable[[Tuple[Any, ...]], bool], start: int = 0) -> int:
        for i in range(start, len(self.events)):
            if pred(self.events[i]):
                return i
        return -1


class Fault:
    """A delegating ``os.<name>`` (``replace`` / ``rename``) that raises ``OSError(err)``
    while ``armed`` and ``when(src_realpath, dst_realpath)`` holds."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str, when: Callable[[str, str], bool], err: int = _errno.EIO) -> None:
        self.armed = True
        self.hits: List[Tuple[str, str]] = []
        real = getattr(os, name)

        def wrapped(src, dst, *a, **kw):
            s = resolve(src, kw.get("src_dir_fd"))
            d = resolve(dst, kw.get("dst_dir_fd"))
            if self.armed and when(s, d):
                self.hits.append((s, d))
                raise OSError(err, os.strerror(err), d)
            return real(src, dst, *a, **kw)

        monkeypatch.setattr(os, name, wrapped)


def under(path, root) -> bool:
    r = os.path.realpath(str(root))
    p = os.path.realpath(str(path)) if os.path.exists(str(path)) else str(path)
    return p == r or p.startswith(r + os.sep)


# --------------------------------------------------------------------------- cross-process lock probe


def _probe_worker(books_dir: str, book_folder: str, mode: str, budget: float, result_path: str) -> None:
    from reader3_app import book_lock

    try:
        with book_lock.acquire(books_dir, book_folder, mode=mode, holder="search", budget=budget):
            pass
    except book_lock.BookLockBusy as exc:
        write_result(result_path, {"outcome": "busy", "category": getattr(exc, "holder_category", None)})
        return
    except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
        write_result(result_path, {"outcome": f"error:{type(exc).__name__}:{exc}", "category": None})
        return
    write_result(result_path, {"outcome": "acquired", "category": None})


def probe_lock(books_dir, folder: str, mode: str) -> Tuple[str, Optional[str]]:
    """Try ``mode`` on ``folder`` from a spawned child: ``("acquired", None)`` or ``("busy", category)``.

    Cross-process on purpose: an in-process probe would hit ``BookLockReentry``.
    """
    import tempfile

    tmp = tempfile.mkdtemp(prefix="probe-")
    try:
        path = os.path.join(tmp, f"probe-{_uuid.uuid4().hex}.json")
        child = Child(_probe_worker, (str(books_dir), folder, mode, PROBE_BUDGET_S, path), path).start()
        got = child.wait_result()
        child.reap()
        assert got is not None, "the probe child never reported"
        return (got["outcome"], got.get("category"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- resolver / chroma identity


def warm(resolver, folder: str, uuid: str) -> None:
    """Warm ``resolver`` with ``folder -> uuid``.

    By lookup when the folder exists on disk with that uuid; by direct registration
    otherwise (a tombstoned folder can no longer be looked up).
    """
    meta = Path(resolver.books_dir) / folder / "ai_meta.json"
    if meta.is_file():
        assert resolver.book_uuid_for_folder(folder) == uuid
    else:
        with resolver._lock:
            resolver._register(folder, uuid)
    assert resolver._folder_to_uuid[folder] == uuid


@pytest.fixture
def chroma_env(monkeypatch: pytest.MonkeyPatch):
    """Telemetry off for chromadb; the shared system cache cleared before and after."""
    from chromadb.api.shared_system_client import SharedSystemClient

    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    SharedSystemClient.clear_system_cache()
    yield
    with contextlib.suppress(Exception):
        SharedSystemClient.clear_system_cache()


PROBE_EMBEDDING = [0.125] * 8


class IdentityProbe:
    """§0.3: a warmed resolver entry plus a live chromadb client on ``chroma_path``."""

    def __init__(self, resolver, folder: str, uuid: str, chroma_path) -> None:
        import chromadb

        self.resolver = resolver
        self.folder = folder
        self.uuid = uuid
        self.chroma_path = os.path.realpath(str(chroma_path))
        os.makedirs(self.chroma_path, exist_ok=True)
        warm(resolver, folder, uuid)
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection("identity_probe", embedding_function=None)
        self.collection.add(ids=["1"], embeddings=[PROBE_EMBEDDING], documents=["probe"])
        self.assert_untouched()

    def query_ids(self) -> List[str]:
        got = self.collection.query(query_embeddings=[PROBE_EMBEDDING], n_results=1)
        return list(got["ids"][0])

    def assert_untouched(self) -> None:
        from chromadb.api.shared_system_client import SharedSystemClient

        r = self.resolver
        assert r._folder_to_uuid.get(self.folder) == self.uuid, (
            f"resolver forward map changed: {self.folder} -> {r._folder_to_uuid.get(self.folder)!r}"
        )
        assert r._uuid_to_folder.get(self.uuid) == self.folder, (
            f"resolver reverse map changed: {self.uuid} -> {r._uuid_to_folder.get(self.uuid)!r}"
        )
        assert self.chroma_path in SharedSystemClient._identifier_to_system, (
            f"the chroma system for {self.chroma_path} was retired"
        )
        assert self.query_ids() == ["1"]


# --------------------------------------------------------------------------- server seams


def server_module():
    from reader3_app.web import server

    return server


def seat_resolver(monkeypatch: pytest.MonkeyPatch, books_dir):
    """A fresh resolver on ``books_dir``, installed at the ``server.book_uuid_resolver`` seam."""
    from reader3_app.ai.books import BookUuidResolver

    server = server_module()
    resolver = BookUuidResolver(str(books_dir))
    monkeypatch.setattr(server, "book_uuid_resolver", resolver)
    return resolver


def resolver_maps(resolver) -> Tuple[Dict[str, str], Dict[str, str]]:
    return (dict(resolver._folder_to_uuid), dict(resolver._uuid_to_folder))


# --------------------------------------------------------------------------- SCHEMA_KINDS (F-11, D-8)

#: ``(id, class, expected reason)``. W5-17 / AMB-13: ``bad_target`` is unreadable.
SCHEMA_KINDS: List[Tuple[str, str, Optional[str]]] = [
    ("syntax", "unreadable", "json"),
    ("array", "unreadable", "not_object"),
    ("traversal_cid", "unreadable", "conversation_id"),
    ("bad_filename", "unreadable", "filename"),
    ("unresolvable_uuid", "unreadable", "uuid"),
    ("bad_target", "unreadable", "target"),
    ("bad_target_array", "unreadable", "target"),  # CP2 M2 / W5-21: an existing target that parses but is not an object
    ("no_last_updated", "readable", None),
    ("int_last_updated", "readable", None),
]
SCHEMA_KIND_IDS = [k[0] for k in SCHEMA_KINDS]
UNREADABLE_KINDS = [k for k in SCHEMA_KINDS if k[1] == "unreadable"]
UNREADABLE_KIND_IDS = [k[0] for k in UNREADABLE_KINDS]

#: CP2 L3 / W5-17: ``null`` and ``""`` ``last_updated`` are readable too (they key as ``""``).
#: Kept out of ``SCHEMA_KINDS`` so the recorded parametrize lists stay as they were.
READABLE_LU_KINDS: List[Tuple[str, str, Optional[str]]] = [
    ("null_last_updated", "readable", None),
    ("empty_last_updated", "readable", None),
]
READABLE_LU_KIND_IDS = [k[0] for k in READABLE_LU_KINDS]


def schema_kind_layout(kind: str, *, n_valid: int = 3) -> SimpleNamespace:
    """The per-kind fixture differences.

    ``convs``: the book's conversation files (``n_valid`` valid ones -- F-11 uses 3, D-8 uses 2 --
    plus the extra entry);
    ``uuid_null``: the intent / ai_meta has no valid uuid; ``bad_target``: bytes for
    ``R/U/CID_COLLIDE.json`` (else the older valid copy); ``bad_name``: the basename
    a refusal / WARNING must name (``None`` for readable kinds).
    """
    fresh_own: Any = ABSENT
    extra: Optional[Tuple[str, bytes]] = None
    uuid_null = False
    target = conv(CID_COLLIDE, D_OLD, "collide-existing")[1]
    bad_name: Optional[str] = f"{ZERO_UUID}.json"
    if kind == "syntax":
        extra = raw_conv(f"{ZERO_UUID}.json", b"{trunc")
    elif kind == "array":
        extra = raw_conv(f"{ZERO_UUID}.json", b"[]")
    elif kind == "traversal_cid":
        extra = raw_conv(
            f"{ZERO_UUID}.json",
            json.dumps(conv_payload(ZERO_UUID, D_MID, "traversal", conversation_id="../../x")).encode(),
        )
    elif kind == "bad_filename":
        body = conv_payload(ZERO_UUID, D_MID, "bad filename")
        del body["conversation_id"]
        extra = raw_conv("notauuid.json", json.dumps(body).encode())
        bad_name = "notauuid.json"
    elif kind == "unresolvable_uuid":
        uuid_null = True
        fresh_own = V
        bad_name = f"{CID_COLLIDE}.json"
    elif kind == "bad_target":
        target = b"{x"
        bad_name = f"{CID_COLLIDE}.json"
    elif kind == "bad_target_array":
        target = b"[]"
        bad_name = f"{CID_COLLIDE}.json"
    elif kind == "null_last_updated":
        extra = conv(ZERO_UUID, None, "null dated")
        bad_name = None
    elif kind == "empty_last_updated":
        extra = conv(ZERO_UUID, "", "empty dated")
        bad_name = None
    elif kind == "no_last_updated":
        extra = conv(ZERO_UUID, ABSENT, "undated")
        bad_name = None
    elif kind == "int_last_updated":
        extra = conv(ZERO_UUID, 7, "int dated")
        bad_name = None
    else:  # pragma: no cover - a typo in a parametrize id
        raise AssertionError(kind)
    convs = [
        conv(CID_FRESH, D_MID, "fresh", own_uuid=fresh_own),
        conv(CID_COLLIDE, D_NEW, "collide-book"),
        conv(CID_3, D_MID, "third"),
    ][:n_valid]
    if extra is not None:
        convs.append(extra)
    return SimpleNamespace(convs=convs, uuid_null=uuid_null, target=target, bad_name=bad_name, extra=extra)


# --------------------------------------------------------------------------- subprocess children (CR-1, F-7, H-1, B-6a)


def child_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["ANONYMIZED_TELEMETRY"] = "False"
    env.pop("READER3_BOOKS_DIR", None)
    return env


def child_code(call: str) -> str:
    return (
        "import sys; "
        f"sys.path.insert(0, {str(FIXTURES_DIR)!r}); "
        "import delete_world; "
        f"delete_world.{call}(*sys.argv[1:])"
    )


def popen_child(call: str, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", child_code(call), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_env(),
    )


def finish(proc: subprocess.Popen, timeout: float = SUBPROCESS_TIMEOUT_S) -> Tuple[int, str, str]:
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=10)
        return (-999, out.decode(errors="replace"), err.decode(errors="replace"))
    return (proc.returncode, out.decode(errors="replace"), err.decode(errors="replace"))


def _die(sentinel: str, tag: str) -> None:
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write(tag)
        f.flush()
        os.fsync(f.fileno())
    os.kill(os.getpid(), signal.SIGKILL)


def crash_child_main(books: str, conv_root: str, coll: str, mode: str, kill_point: str, sentinel: str) -> None:
    """CR-1 child: install the hook, ``delete_book``, SIGKILL itself at ``kill_point``."""
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    m = importlib.import_module(LD_MODULE)
    counts: Dict[str, int] = {}
    target = None if kill_point == "rmtree_partial" else parse_point(kill_point)

    def arm_partial() -> None:
        real_unlink, real_rmdir = os.unlink, os.rmdir

        def kill_after(real):
            def wrapped(*a, **kw):
                real(*a, **kw)
                _die(sentinel, kill_point)

            return wrapped

        os.unlink = kill_after(real_unlink)  # type: ignore[assignment]
        os.rmdir = kill_after(real_rmdir)  # type: ignore[assignment]

    def hook(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1
        if kill_point == "rmtree_partial":
            if name == "conv_done":
                arm_partial()
            return
        if target == (name, counts[name]):
            _die(sentinel, kill_point)

    m._STEP_HOOK = hook
    m.delete_book(
        books,
        "a_data",
        delete_conversations=(mode == "true"),
        conversation_root=conv_root,
        collections_path=coll,
    )
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("completed")


def sweep_child_main(books: str, out_path: str) -> None:
    """Sweep in a fresh interpreter; record the report and any ``reader3_app.web*`` module loaded."""
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    m = importlib.import_module(LD_MODULE)
    report = m.sweep(books)
    web = sorted(n for n in sys.modules if n == "reader3_app.web" or n.startswith("reader3_app.web."))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"report": report_dict(report), "web": web}, f)


# --------------------------------------------------------------------------- 5c: EX holder that renames (C-9(b))


def hold_ex_rename_release(
    books_dir: str, folder: str, away: str, rename_after_s: float, release_after_s: float, ready_evt, result_path: str
) -> None:
    """Take EX (``delete``) on ``folder``, signal ready, rename it to ``away`` after
    ``rename_after_s``, then release ``release_after_s`` after acquiring."""
    import time

    from reader3_app import book_lock

    try:
        with book_lock.acquire(books_dir, folder, mode=book_lock.EXCLUSIVE, holder="delete"):
            started = time.monotonic()
            ready_evt.set()
            time.sleep(rename_after_s)
            os.rename(os.path.join(books_dir, folder), os.path.join(books_dir, away))
            time.sleep(max(0.0, release_after_s - (time.monotonic() - started)))
    except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
        write_result(result_path, {"outcome": f"error:{type(exc).__name__}:{exc}"})
        ready_evt.set()
        return
    write_result(result_path, {"outcome": "released"})


def hold_ex_rename_on_go(books_dir: str, folder: str, away: str, ready_evt, go_evt, result_path: str) -> None:
    """Take EX (``delete``) on ``folder``, signal ready, wait for ``go`` (bounded), rename it to
    ``away``, release. No sleeps: the parent decides when the rename happens (audit 20261007 #16).
    ``outcome`` is ``released``, or ``no-go`` if ``go`` never came (renamed anyway, so the parent
    is never left blocked on the lock)."""
    from reader3_app import book_lock

    try:
        with book_lock.acquire(books_dir, folder, mode=book_lock.EXCLUSIVE, holder="delete"):
            ready_evt.set()
            went = go_evt.wait(30.0)
            os.rename(os.path.join(books_dir, folder), os.path.join(books_dir, away))
    except BaseException as exc:  # noqa: BLE001 - the outcome is the observation
        write_result(result_path, {"outcome": f"error:{type(exc).__name__}:{exc}"})
        ready_evt.set()
        return
    write_result(result_path, {"outcome": "released" if went else "no-go"})
