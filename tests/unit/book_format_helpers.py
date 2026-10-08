"""Shared helpers for the ``book_format`` publish and crash-matrix tests (012 WI-1.6, reused by WI-1.7/1.8).

Not collected by pytest (the name does not match ``test_*.py``); importing it has no side effects.
Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md``, "Shared test infrastructure".

- ``make_inputs`` / ``expected_gen_files``: the deterministic tagged inputs (non-ASCII chapters, tagged bytes).
- ``setup_scenario``: S0, S0u, S1..S5 under ``<base>/books/sample_data``.
- ``REPAIRABLE`` / ``build_repairable``: the repairable corrupt shapes of P-20b.
- ``snapshot``: an ``lstat`` tree snapshot (never follows a link; dangling links included).
- ``HookRecorder``: replaces ``book_format._crash_point``; records, runs per-point actions, injects a crash.
- ``SyscallJournal``: recording passthroughs (the real call always happens) over the syscalls the mock policy
  names, every path / fd argument resolved at call time to ``(st_dev, st_ino)``. Journalled APIs:
  ``builtins.open``/``io.open``, ``os.open``, ``os.fsync``, ``os.mkdir``, ``os.replace``, ``os.rename``,
  ``os.unlink``, ``os.remove``, ``os.rmdir``, ``os.link``, ``os.symlink``, ``os.listdir``, ``os.scandir``,
  ``os.walk``, ``glob.glob``, ``glob.iglob``, ``pathlib.Path.iterdir``/``glob``/``rglob``.
"""
from __future__ import annotations

import builtins
import errno
import glob
import hashlib
import io
import json
import os
import pathlib
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pytest

from reader3_app import book_format
from reader3_app.book_format import (
    CHAPTERS,
    EPUB,
    GEN_DIR,
    IMAGES,
    MANIFEST,
    MANIFEST_TMP,
    PKL,
    BookManifest,
    ChapterRecord,
    ManifestMetadata,
    ManifestTocEntry,
    PublishInputs,
    classify,
    is_canonical_gen_name,
    read_chapter,
    validate_stat,
)

_os_stat = os.stat
_os_lstat = os.lstat
_os_fstat = os.fstat

# --------------------------------------------------------------------------- inputs

TAG_TEXT = "第一章 café 🜁 line"
METADATA = ManifestMetadata(
    title="Dracula 第一", language="en", authors=("Bram Stoker",), description=None,
    publisher=None, date=None, identifiers=(), subjects=(),
)
TOC = (ManifestTocEntry(title="One", href="Text/c0.xhtml", file_href="Text/c0.xhtml", anchor="", children=()),)
IMAGE_ORIGINS: dict[str, tuple[str, ...]] = {"cover.png": ("OEBPS/cover.png",), "图.jpg": ("OEBPS/图.jpg",)}
FINGERPRINT = hashlib.sha256(b"book_format_helpers book_fingerprint").hexdigest()
"""The default ``book_fingerprint`` every test-built manifest / input carries (012 WI-2a.2)."""
EXTRACTOR_VERSION = 1
"""The default ``extractor_version`` every test-built manifest / input carries (012 WI-2a.2)."""


def make_chapters(tag: str, n: int = 3) -> tuple[ChapterRecord, ...]:
    return tuple(
        ChapterRecord(
            id=f"c{i}", href=f"Text/c{i}.xhtml", title=f"第{i}章",
            content=f"<p>{tag} {TAG_TEXT}\n{i}</p>", text=f"{tag} {TAG_TEXT}\n{i}", order=i,
        )
        for i in range(n)
    )


def make_inputs(
    tag: str, *, images: bool = True, pkl: bool = True, n_chapters: int = 3,
    image_bytes: Optional[dict[str, bytes]] = None, book_fingerprint: str = FINGERPRINT,
    extractor_version: int = EXTRACTOR_VERSION,
) -> PublishInputs:
    """The tagged inputs: ``EPUB-<tag>``, ``PKL-<tag>``, ``cover.png``=``PNG-<tag>``, ``图.jpg``=``JPG-<tag>``."""
    t = tag.encode()
    if image_bytes is None:
        image_bytes = {"cover.png": b"PNG-" + t, "图.jpg": b"JPG-" + t}
    return PublishInputs(
        metadata=METADATA,
        toc=TOC,
        chapters=make_chapters(tag, n_chapters),
        source_file="dracula.epub",
        processed_at="2026-10-08T00:00:00+00:00",
        book_version="1",
        book_fingerprint=book_fingerprint,
        extractor_version=extractor_version,
        epub=b"EPUB-" + t,
        images=dict(image_bytes) if images else {},
        image_origins={n: IMAGE_ORIGINS.get(n, ()) for n in image_bytes} if images else {},
        pkl=b"PKL-" + t if pkl else None,
    )


def expected_gen_files(inputs: PublishInputs) -> set[str]:
    files = {CHAPTERS}
    if inputs.epub is not None:
        files.add(EPUB)
    if inputs.pkl is not None:
        files.add(PKL)
    files |= {f"{IMAGES}/{n}" for n in inputs.images}
    return files


# --------------------------------------------------------------------------- scenario builders

USER_DATA: dict[str, bytes] = {
    "notes.json": b"[]",
    "notes.json.lock": b"",
    "ai_meta.json": b'{"book_uuid": "u"}',
    "ai_conversations/c1.json": b"{}",
    "chroma_db/index_meta.json": b"{}",
    "chroma_db/x.bin": b"\x00\x01",
}
STRAY: dict[str, bytes] = {"README.txt": b"stray user file"}
LEGACY_FLAT: dict[str, bytes] = {PKL: b"legacy-pkl", EPUB: b"legacy-epub", "images/a.png": b"legacy-png"}
USER_ROOT_ENTRIES = frozenset({"notes.json", "notes.json.lock", "ai_meta.json", "ai_conversations", "chroma_db",
                               "README.txt"})

BOOK_NAME = "sample_data"
SCENARIOS = ("S0", "S0u", "S1", "S2", "S3", "S4", "S5")
G_NEW = {"S0": 1, "S0u": 1, "S1": 3, "S2": 2, "S3": 1, "S4": 10, "S5": 10}
"""The generation ``publish(make_inputs("v2"))`` commits over each scenario (pinned law 2)."""
PREV_TAG = {"S1": "v1", "S2": "v1", "S4": "v1"}
"""The tag the current generation of each valid scenario carries."""


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def add_files(book: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        write_file(book / rel, data)


def add_user_data(book: Path) -> None:
    add_files(book, USER_DATA)
    add_files(book, STRAY)


def book_path(base: Path) -> Path:
    books = Path(base) / "books"
    books.mkdir(parents=True, exist_ok=True)
    return books / BOOK_NAME


def add_orphan(book: Path, n: int | str) -> None:
    """A partial generation a killed publish leaves behind."""
    write_file(book / GEN_DIR / str(n) / CHAPTERS, b"partial junk " + str(n).encode())


def add_stale_tmp(book: Path, data: bytes = b'{"half": "written') -> None:
    (book / MANIFEST_TMP).write_bytes(data)


def add_debris(book: Path) -> Path:
    """A pre-012 sibling staging directory holding ``book.epub`` and no ``book.pkl``: plain debris."""
    sib = book.parent / f"{book.name}.staging-4242"
    write_file(sib / EPUB, b"debris epub")
    return sib


def add_parked(book: Path) -> Path:
    """A pre-012 sibling staging directory that parks the previous ``book.epub``: publish must refuse."""
    sib = book.parent / f"{book.name}.staging-777"
    write_file(sib / PKL, b"staged pkl")
    write_file(sib / "book.epub.superseded", b"the only copy")
    return sib


def setup_scenario(name: str, base: Path) -> Path:
    """Build scenario ``name`` under ``<base>/books``; return the book directory (absent for S0)."""
    book = book_path(base)
    if name == "S0":
        return book
    book.mkdir()
    add_user_data(book)
    if name == "S0u":
        return book
    if name in ("S1", "S4", "S5"):
        book_format.publish(book, make_inputs("v0"))
        book_format.publish(book, make_inputs("v1"))
    elif name == "S2":
        book_format.publish(book, make_inputs("v1", images=False))
    elif name == "S3":
        add_files(book, LEGACY_FLAT)
    else:
        raise ValueError(f"unknown scenario {name!r}")
    if name == "S4":
        add_orphan(book, 9)
        add_stale_tmp(book)
        add_debris(book)
    if name == "S5":
        os.unlink(book / GEN_DIR / "2" / IMAGES / "cover.png")
        add_orphan(book, 9)
    return book


# --------------------------------------------------------------------------- repairable corrupt shapes (P-20b)


def _load_manifest_doc(book: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((book / MANIFEST).read_bytes())
    return doc


def _dump_manifest_doc(book: Path, doc: dict[str, Any]) -> None:
    (book / MANIFEST).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _edit_manifest(book: Path, edit: Callable[[dict[str, Any]], None]) -> None:
    doc = _load_manifest_doc(book)
    edit(doc)
    _dump_manifest_doc(book, doc)


def _r_unparse(book: Path, outside: Path) -> None:
    raw = (book / MANIFEST).read_bytes()
    (book / MANIFEST).write_bytes(raw[: len(raw) // 2])


def _r_nover(book: Path, outside: Path) -> None:
    _edit_manifest(book, lambda d: d.pop("format_version"))


def _r_lowver(book: Path, outside: Path) -> None:
    _edit_manifest(book, lambda d: d.__setitem__("format_version", 0))


def _r_gen_str(book: Path, outside: Path) -> None:
    _edit_manifest(book, lambda d: d.__setitem__("generation", "2"))


def _r_gen_missing(book: Path, outside: Path) -> None:
    shutil.rmtree(book / GEN_DIR / "2")


def _r_gen_file(book: Path, outside: Path) -> None:
    shutil.rmtree(book / GEN_DIR / "2")
    (book / GEN_DIR / "2").write_bytes(b"not a generation")


def _r_gen_link(book: Path, outside: Path) -> None:
    copy = outside / "gen2_copy"
    shutil.copytree(book / GEN_DIR / "2", copy)
    shutil.rmtree(book / GEN_DIR / "2")
    os.symlink(copy, book / GEN_DIR / "2")


def _r_art_missing(book: Path, outside: Path) -> None:
    os.unlink(book / GEN_DIR / "2" / EPUB)


def _r_art_size(book: Path, outside: Path) -> None:
    with open(book / GEN_DIR / "2" / IMAGES / "cover.png", "ab") as fh:
        fh.write(b"+")


def _r_art_link(book: Path, outside: Path) -> None:
    copy = outside / "epub_copy"
    shutil.copyfile(book / GEN_DIR / "2" / EPUB, copy)
    os.unlink(book / GEN_DIR / "2" / EPUB)
    os.symlink(copy, book / GEN_DIR / "2" / EPUB)


def _r_man_link(book: Path, outside: Path) -> None:
    target = outside / "manifest.json"
    shutil.copyfile(book / MANIFEST, target)
    os.unlink(book / MANIFEST)
    os.symlink(target, book / MANIFEST)


def _r_man_dangling(book: Path, outside: Path) -> None:
    os.unlink(book / MANIFEST)
    os.symlink(outside / "no-such-manifest.json", book / MANIFEST)


def _r_high_gen(book: Path, outside: Path) -> None:
    _r_art_missing(book, outside)
    _edit_manifest(book, lambda d: d.__setitem__("generation", 50))


REPAIRABLE: dict[str, tuple[Callable[[Path, Path], None], int]] = {
    "R-unparse": (_r_unparse, 10),
    "R-nover": (_r_nover, 10),
    "R-lowver": (_r_lowver, 10),
    "R-gen-str": (_r_gen_str, 10),
    "R-gen-missing": (_r_gen_missing, 10),
    "R-gen-file": (_r_gen_file, 10),
    "R-gen-link": (_r_gen_link, 10),
    "R-art-missing": (_r_art_missing, 10),
    "R-art-size": (_r_art_size, 10),
    "R-art-link": (_r_art_link, 10),
    "R-man-link": (_r_man_link, 10),
    "R-man-dangling": (_r_man_dangling, 10),
    "R-high-gen": (_r_high_gen, 51),
}
"""Shape id -> (mutation over the repair base, expected repair generation)."""

MANIFEST_PARSES = frozenset({"R-gen-missing", "R-gen-file", "R-gen-link", "R-art-missing", "R-art-size",
                             "R-art-link", "R-high-gen"})
"""Shapes whose ``manifest.json`` is a regular file the strict parser accepts (a readable generation)."""


def build_repairable(shape: str, base: Path) -> Path:
    """S1 + user data + orphan ``gen/9`` + non-canonical ``gen/tmp/``, then the shape's corruption."""
    book = setup_scenario("S1", base)
    add_orphan(book, 9)
    write_file(book / GEN_DIR / "tmp" / "scratch.bin", b"non-canonical")
    outside = Path(base) / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    REPAIRABLE[shape][0](book, outside)
    return book


# --------------------------------------------------------------------------- snapshots and checks


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path | str, *, dir_mtimes: bool = True) -> dict[str, tuple[Any, ...]]:
    """``lstat`` snapshot including ``root`` itself (key ``"."``): files by sha/size/mtime_ns/inode, links by
    target/mtime_ns/inode, directories by mtime_ns/inode (mtime omitted when ``dir_mtimes`` is false)."""
    out: dict[str, tuple[Any, ...]] = {}
    if not os.path.lexists(root):
        return out

    def one(full: str, rel: str) -> None:
        st_ = _os_lstat(full)
        if stat.S_ISLNK(st_.st_mode):
            out[rel] = ("link", os.readlink(full), st_.st_mtime_ns, st_.st_ino)
        elif stat.S_ISDIR(st_.st_mode):
            out[rel + "/"] = ("dir", st_.st_mtime_ns, st_.st_ino) if dir_mtimes else ("dir", st_.st_ino)
        else:
            with open(full, "rb") as fh:
                out[rel] = ("file", _sha(fh.read()), st_.st_size, st_.st_mtime_ns, st_.st_ino,
                            stat.S_IMODE(st_.st_mode))

    one(str(root), ".")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            one(full, os.path.relpath(full, root))
    return out


def sub(snap: dict[str, tuple[Any, ...]], prefix: str) -> dict[str, tuple[Any, ...]]:
    """The entries of ``snap`` at or under ``prefix`` (a relative path, no trailing slash)."""
    return {k: v for k, v in snap.items() if k in (prefix, prefix + "/") or k.startswith(prefix + "/")}


def without(snap: dict[str, tuple[Any, ...]], *prefixes: str) -> dict[str, tuple[Any, ...]]:
    drop: set[str] = set()
    for p in prefixes:
        drop |= set(sub(snap, p))
    return {k: v for k, v in snap.items() if k not in drop}


def root_entries(book: Path) -> set[str]:
    return set(os.listdir(book)) if os.path.isdir(book) else set()


def canonical_gens(book: Path) -> set[int]:
    gen = Path(book) / GEN_DIR
    if not os.path.isdir(gen) or os.path.islink(gen):
        return set()
    return {int(n) for n in os.listdir(gen) if is_canonical_gen_name(n)}


def gen_file_set(gen_dir: Path) -> tuple[set[str], set[str]]:
    """(relative regular-file paths, relative directory paths) under ``gen_dir``."""
    files: set[str] = set()
    dirs: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(gen_dir):
        for d in dirnames:
            dirs.add(os.path.relpath(os.path.join(dirpath, d), gen_dir))
        for f in filenames:
            files.add(os.path.relpath(os.path.join(dirpath, f), gen_dir))
    return files, dirs


def assert_valid_with(book: Path, tag: str) -> BookManifest:
    """Full-mode ``valid``, and every chapter / artifact of the current generation carries ``tag`` only."""
    assert classify(book, full=True) == "valid"
    m = validate_stat(book)
    gen_dir = Path(book) / GEN_DIR / str(m.generation)
    for entry in m.chapters:
        rec = read_chapter(gen_dir, entry)
        assert rec.text.startswith(f"{tag} "), (entry.id, rec.text)
    for art in m.artifacts:
        if art.path == CHAPTERS:
            continue
        data = (gen_dir / art.path).read_bytes()
        assert data.endswith(b"-" + tag.encode()), (art.path, data)
    return m


# --------------------------------------------------------------------------- injection


class InjectedCrash(BaseException):
    """Test-local crash; deliberately not an ``Exception``."""


def _eio() -> OSError:
    return OSError(errno.EIO, "injected EIO")


def _nomem() -> BaseException:
    exc_type: type[BaseException] = getattr(builtins, "Memory" + "Error")
    return exc_type("injected")


INJECTED_KINDS: dict[str, Callable[[], BaseException]] = {
    "kbint": KeyboardInterrupt,
    "eio": _eio,
    "nomem": _nomem,
    "crash": InjectedCrash,
}
"""Pre-commit exception kinds (P-14); built through a factory so their names stay out of test sources."""

Point = tuple[str, str]


class HookRecorder:
    """Stands in for ``book_format._crash_point``: records each call, runs per-point actions, may raise."""

    def __init__(self, *, crash_at: int | None = None, exc: Callable[[], BaseException] = InjectedCrash) -> None:
        self.calls: list[Point] = []
        self.actions: dict[Point, Callable[[], None]] = {}
        self.crash_at = crash_at
        self.exc = exc
        self.raised: BaseException | None = None

    def on(self, step: str, when: str, fn: Callable[[], None]) -> "HookRecorder":
        self.actions[(step, when)] = fn
        return self

    def __call__(self, step: str, when: str) -> None:
        self.calls.append((step, when))
        action = self.actions.get((step, when))
        if action is not None:
            action()
        if self.crash_at is not None and len(self.calls) - 1 == self.crash_at:
            self.raised = self.exc()
            raise self.raised

    def steps(self) -> set[str]:
        return {s for s, _ in self.calls}


def install_hooks(mp: pytest.MonkeyPatch, rec: Callable[[str, str], None]) -> None:
    mp.setattr(book_format, "_crash_point", rec)


def dry_run_points(scenario: str, base: Path, inputs: Optional[PublishInputs] = None, **kw: Any) -> list[Point]:
    """The ordered hook points one uninterrupted ``publish(v2)`` reaches over a fresh ``scenario``."""
    book = setup_scenario(scenario, base)
    rec = HookRecorder()
    with pytest.MonkeyPatch.context() as mp:
        install_hooks(mp, rec)
        book_format.publish(book, inputs or make_inputs("v2"), **kw)
    return rec.calls


# --------------------------------------------------------------------------- syscall journal

Ident = tuple[int, int]


@dataclass
class Ev:
    kind: str
    path: Optional[str] = None
    ident: Optional[Ident] = None
    parent: Optional[Ident] = None
    name: Optional[str] = None
    mode: Optional[str] = None
    flags: Optional[int] = None
    size: Optional[int] = None
    is_dir: bool = False
    creates: bool = False
    src: Optional[str] = None
    point: Optional[Point] = None


def _ident(target: Any, dir_fd: Optional[int] = None, *, follow: bool = True) -> Optional[Ident]:
    try:
        if isinstance(target, int):
            st_ = _os_fstat(target)
        elif follow:
            st_ = _os_stat(target, dir_fd=dir_fd)
        else:
            st_ = _os_lstat(target, dir_fd=dir_fd)
    except (OSError, TypeError, ValueError):
        return None
    return (st_.st_dev, st_.st_ino)


def _str_path(p: Any) -> Optional[str]:
    if isinstance(p, int):
        return None
    p = os.fspath(p)
    return os.fsdecode(p) if isinstance(p, bytes) else p


def _abs(p: Any, dir_fd: Optional[int] = None) -> Optional[str]:
    s = _str_path(p)
    if s is None or (dir_fd is not None and not os.path.isabs(s)):
        return None
    a = os.path.abspath(s)
    return os.path.join(os.path.realpath(os.path.dirname(a)), os.path.basename(a))


def _parent(p: Any, dir_fd: Optional[int] = None) -> Optional[Ident]:
    s = _str_path(p)
    if s is None:
        return None
    head = os.path.dirname(s)
    if dir_fd is not None and not os.path.isabs(s):
        return _ident(head, dir_fd) if head else _ident(dir_fd)
    return _ident(os.path.dirname(os.path.abspath(s)))


def _name(p: Any) -> Optional[str]:
    s = _str_path(p)
    return os.path.basename(s) if s is not None else None


class SyscallJournal:
    """One ordered event log of hook calls plus recording passthroughs; every call still goes through."""

    LISTING = ("listdir", "scandir", "walk", "glob", "iglob", "iterdir", "path.glob", "path.rglob")

    def __init__(self, inner: Optional[Callable[[str, str], None]] = None) -> None:
        self.events: list[Ev] = []
        self.inner = inner

    # ---- queries
    def index_of(self, step: str, when: str) -> int:
        for i, ev in enumerate(self.events):
            if ev.kind == "hook" and ev.point == (step, when):
                return i
        raise AssertionError(f"hook {(step, when)} never reached")

    def of(self, *kinds: str) -> list[tuple[int, Ev]]:
        return [(i, ev) for i, ev in enumerate(self.events) if ev.kind in kinds]

    # ---- install
    def install(self, mp: pytest.MonkeyPatch) -> "SyscallJournal":
        rec = self.events.append
        real_open = builtins.open
        real = {n: getattr(os, n) for n in ("open", "fsync", "mkdir", "replace", "rename", "unlink", "remove",
                                             "rmdir", "link", "symlink", "listdir", "scandir", "walk")}
        real_glob, real_iglob = glob.glob, glob.iglob
        real_iterdir, real_pglob, real_prglob = pathlib.Path.iterdir, pathlib.Path.glob, pathlib.Path.rglob

        def hook(step: str, when: str) -> None:
            rec(Ev("hook", point=(step, when)))
            if self.inner is not None:
                self.inner(step, when)

        def j_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            fobj = real_open(file, mode, *args, **kwargs)
            try:
                ident = _ident(fobj.fileno())
            except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
                ident = None
            creates = any(c in mode for c in "wxa")
            rec(Ev("open", path=_abs(file), ident=ident, parent=_parent(file), name=_name(file), mode=mode,
                   creates=creates))
            return fobj

        def j_os_open(path: Any, flags: int, mode: int = 0o777, *, dir_fd: Optional[int] = None) -> int:
            fd: int = real["open"](path, flags, mode, dir_fd=dir_fd)
            rec(Ev("os.open", path=_abs(path, dir_fd), ident=_ident(fd), parent=_parent(path, dir_fd),
                   name=_name(path), flags=flags, creates=bool(flags & os.O_CREAT)))
            return fd

        def j_fsync(fd: Any) -> None:
            n = fd if isinstance(fd, int) else fd.fileno()
            try:
                st_ = _os_fstat(n)
                rec(Ev("fsync", ident=(st_.st_dev, st_.st_ino), size=st_.st_size, is_dir=stat.S_ISDIR(st_.st_mode)))
            except OSError:
                rec(Ev("fsync"))
            real["fsync"](fd)

        def j_mkdir(path: Any, mode: int = 0o777, *, dir_fd: Optional[int] = None) -> None:
            real["mkdir"](path, mode, dir_fd=dir_fd)
            rec(Ev("mkdir", path=_abs(path, dir_fd), ident=_ident(path, dir_fd, follow=False),
                   parent=_parent(path, dir_fd), name=_name(path), creates=True))

        def mover(kind: str) -> Callable[..., None]:
            def j_move(src: Any, dst: Any, *, src_dir_fd: Optional[int] = None,
                       dst_dir_fd: Optional[int] = None) -> None:
                rec(Ev(kind, path=_abs(dst, dst_dir_fd), ident=_ident(src, src_dir_fd, follow=False),
                       parent=_parent(dst, dst_dir_fd), name=_name(dst), src=_abs(src, src_dir_fd)))
                real[kind](src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
            return j_move

        def remover(kind: str) -> Callable[..., None]:
            def j_remove(path: Any, *, dir_fd: Optional[int] = None) -> None:
                rec(Ev(kind, path=_abs(path, dir_fd), ident=_ident(path, dir_fd, follow=False),
                       parent=_parent(path, dir_fd), name=_name(path)))
                real[kind](path, dir_fd=dir_fd)
            return j_remove

        def j_link(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
            rec(Ev("link", path=_abs(dst), parent=_parent(dst), name=_name(dst), src=_abs(src)))
            real["link"](src, dst, *args, **kwargs)

        def j_symlink(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
            rec(Ev("symlink", path=_abs(dst), parent=_parent(dst), name=_name(dst), src=str(src)))
            real["symlink"](src, dst, *args, **kwargs)

        def lister(kind: str) -> Callable[..., Any]:
            def j_list(*args: Any, **kwargs: Any) -> Any:
                target = args[0] if args else kwargs.get("path", kwargs.get("top", "."))
                target = "." if target is None else target
                rec(Ev(kind, path=_abs(target) if not isinstance(target, int) else None, ident=_ident(target)))
                return real[kind](*args, **kwargs)
            return j_list

        def globber(kind: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def j_glob(pathname: Any, *args: Any, **kwargs: Any) -> Any:
                head = os.path.dirname(os.fspath(pathname)) or "."
                rec(Ev(kind, path=_abs(head), ident=_ident(head)))
                return fn(pathname, *args, **kwargs)
            return j_glob

        def path_lister(kind: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def j_plist(self_: pathlib.Path, *args: Any, **kwargs: Any) -> Any:
                rec(Ev(kind, path=_abs(self_), ident=_ident(self_)))
                return fn(self_, *args, **kwargs)
            return j_plist

        mp.setattr(book_format, "_crash_point", hook)
        mp.setattr(builtins, "open", j_open)
        mp.setattr(io, "open", j_open)
        mp.setattr(os, "open", j_os_open)
        mp.setattr(os, "fsync", j_fsync)
        mp.setattr(os, "mkdir", j_mkdir)
        mp.setattr(os, "replace", mover("replace"))
        mp.setattr(os, "rename", mover("rename"))
        mp.setattr(os, "unlink", remover("unlink"))
        mp.setattr(os, "remove", remover("remove"))
        mp.setattr(os, "rmdir", remover("rmdir"))
        mp.setattr(os, "link", j_link)
        mp.setattr(os, "symlink", j_symlink)
        mp.setattr(os, "listdir", lister("listdir"))
        mp.setattr(os, "scandir", lister("scandir"))
        mp.setattr(os, "walk", lister("walk"))
        mp.setattr(glob, "glob", globber("glob", real_glob))
        mp.setattr(glob, "iglob", globber("iglob", real_iglob))
        mp.setattr(pathlib.Path, "iterdir", path_lister("iterdir", real_iterdir))
        mp.setattr(pathlib.Path, "glob", path_lister("path.glob", real_pglob))
        mp.setattr(pathlib.Path, "rglob", path_lister("path.rglob", real_prglob))
        return self


def iter_files(root: Path) -> Iterator[Path]:
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            yield Path(dirpath) / f
