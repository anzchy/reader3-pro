"""Shared pieces of the Q2 commit prototype: format, readback, classifier, hooks, fsync.

Pure stdlib. Nothing here knows which commit mechanism (A journal / B generation)
is in use except :func:`classify`, which has to resolve artifact paths per layout.
Nothing here parses an EPUB either: the "book" is a fixed fake with a version tag.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, ContextManager, Dict, Iterator, List, Optional, Tuple

FORMAT_VERSION = 1
MANIFEST = "manifest.json"
CHAPTERS = "chapters.jsonl"
EPUB = "book.epub"
PKL = "book.pkl"
IMAGES = "images"
GEN = "gen"
USER_FILES = ("notes.json", "ai_meta.json")
IMAGE_NAMES = ("cover.png", "fig-1.png")
OLD, NEW = "v1", "v2"


class ReadbackError(ValueError):
    """A staged or live artifact does not match what the manifest says."""


class SameDeviceError(RuntimeError):
    """The staging parent is not on the book directory's device; refuse before step 1."""


class InjectedCrash(RuntimeError):
    """Raised by :func:`hook` in ``raise`` mode."""


# ---------------------------------------------------------------- hooks / crash injection

Observer = Callable[[str, str, str], None]
_local = threading.local()  # observers and the in-process crash spec are per thread


def _observers() -> List[Observer]:
    return _local.__dict__.setdefault("observers", [])


def set_crash(spec: Optional[str]) -> None:
    """In-process equivalent of ``PROTO_CRASH`` (so threads never mutate os.environ)."""
    _local.crash = spec


@contextmanager
def observing(fn: Observer) -> Iterator[None]:
    _observers().append(fn)
    try:
        yield
    finally:
        _observers().remove(fn)


def hook(mech: str, step: str, when: str) -> None:
    """Called before and after every publish and recovery step.

    ``PROTO_CRASH=<mech>:<step>:<before|after>:<kill|raise>`` turns one call into a crash.
    """
    for fn in list(_observers()):
        fn(mech, step, when)
    spec = getattr(_local, "crash", None) or os.environ.get("PROTO_CRASH")
    if not spec:
        return
    m, s, w, mode = spec.split(":", 3)
    if (m, s, w) != (mech, step, when):
        return
    if mode == "kill":
        os._exit(137)
    raise InjectedCrash(spec)


def stepper(mech: str) -> Callable[[str], ContextManager[None]]:
    @contextmanager
    def step(name: str) -> Iterator[None]:
        hook(mech, name, "before")
        yield
        hook(mech, name, "after")

    return step


# ---------------------------------------------------------------- fsync / file helpers


def durable_fsync(fd: int) -> None:
    """``os.fsync`` by default; ``F_FULLFSYNC`` on macOS when PROTO_FULLFSYNC=1.

    macOS ``fsync(2)`` hands data to the drive but does not ask it to flush its
    cache; only ``fcntl(F_FULLFSYNC)`` does. Default tests use plain fsync so the
    fsync-order audit (which wraps ``os.fsync``) sees every barrier.
    """
    if os.environ.get("PROTO_FULLFSYNC") == "1" and hasattr(fcntl, "F_FULLFSYNC"):
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:
            pass  # some filesystems refuse F_FULLFSYNC on a directory fd
    os.fsync(fd)


def fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        durable_fsync(fd)
    finally:
        os.close(fd)


def fsync_tree(root: str) -> None:
    """fsync every file, then every directory bottom-up (children before parents)."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in sorted(filenames):
            fsync_path(os.path.join(dirpath, name))
        fsync_path(dirpath)


def write_bytes(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discard(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


def rmdir_if_empty(path: str) -> None:
    try:
        os.rmdir(path)
    except (FileNotFoundError, OSError):
        pass


def assert_same_device(staging_parent: str, book_dir: str) -> None:
    """The enforcer of the same-parent invariant: rename(2) only works within one device."""
    a, b = os.stat(staging_parent).st_dev, os.stat(book_dir).st_dev
    if a != b:
        raise SameDeviceError(f"staging parent is on device {a}, book dir on {b}")


# ---------------------------------------------------------------- the fake book


@dataclass
class Contents:
    tag: str
    chapters: List[dict]
    epub: bytes
    pkl: bytes
    images: Dict[str, bytes] = field(default_factory=dict)


def artifact_bytes(kind: str, tag: str, payload: str = "") -> bytes:
    return f"{kind}|{tag}|{payload}".encode()


def tag_of(data: bytes) -> str:
    parts = data.split(b"|")
    return parts[1].decode() if len(parts) >= 3 else ""


def book_contents(tag: str, images: bool = True) -> Contents:
    """Deterministic fake book. Non-ASCII text so byte offsets differ from char offsets."""
    chapters = [
        {"id": f"ch{i}", "order": i, "text": f"Chapter {i} {tag} -- 第{i}章 café naïve {'ü' * i}"}
        for i in range(1, 4)
    ]
    imgs = {n: artifact_bytes("IMG", tag, n * 8) for n in IMAGE_NAMES} if images else {}
    pkl = artifact_bytes("PKL", tag, "images=" + ",".join(sorted(imgs)))
    return Contents(tag, chapters, artifact_bytes("EPUB", tag, "x" * 64), pkl, imgs)


def write_artifacts(root: str, c: Contents) -> None:
    """book.epub, book.pkl and images/ into ``root`` (no fsync)."""
    write_bytes(os.path.join(root, EPUB), c.epub)
    write_bytes(os.path.join(root, PKL), c.pkl)
    if c.images:
        os.mkdir(os.path.join(root, IMAGES))
        for name, data in sorted(c.images.items()):
            write_bytes(os.path.join(root, IMAGES, name), data)


def artifact_shas(c: Contents) -> Dict[str, str]:
    shas = {EPUB: sha256(c.epub), PKL: sha256(c.pkl)}
    for name, data in c.images.items():
        shas[f"{IMAGES}/{name}"] = sha256(data)
    return shas


# ---------------------------------------------------------------- chapters.jsonl + manifest


def write_chapters(path: str, chapters: List[dict]) -> dict:
    """ADR-0007 steps 1+3: write lines, record per-chapter offset/length/sha + whole file."""
    whole = hashlib.sha256()
    entries, offset = [], 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        for ch in chapters:
            line = json.dumps(ch, ensure_ascii=False, sort_keys=True).encode()
            data = line + b"\n"
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            entries.append({"id": ch["id"], "order": ch["order"], "offset_bytes": offset,
                            "length_bytes": len(line), "sha256": sha256(line)})
            whole.update(data)
            offset += len(data)
    finally:
        os.close(fd)
    return {"chapters": entries, "chapters_size_bytes": offset, "chapters_sha256": whole.hexdigest()}


def build_manifest(tag: str, chapters_meta: dict, shas: Dict[str, str], **extra: object) -> bytes:
    doc = {"format_version": FORMAT_VERSION, "version": tag, "artifacts": shas, **chapters_meta, **extra}
    return json.dumps(doc, sort_keys=True, indent=1).encode() + b"\n"


def validate_book(manifest: dict, root: str, chapters_name: str = CHAPTERS) -> None:
    """ADR-0007 step 6 readback, also the reader-side validity check. Raises ReadbackError."""
    try:
        if manifest["format_version"] != FORMAT_VERSION:
            raise ReadbackError("unknown format_version")
        tag = manifest["version"]
        with open(os.path.join(root, chapters_name), "rb") as f:
            whole = f.read()
            if len(whole) != manifest["chapters_size_bytes"] or sha256(whole) != manifest["chapters_sha256"]:
                raise ReadbackError("chapters size/sha mismatch")
            for e in manifest["chapters"]:
                f.seek(e["offset_bytes"])
                raw = f.read(e["length_bytes"])
                if len(raw) != e["length_bytes"] or sha256(raw) != e["sha256"]:
                    raise ReadbackError(f"chapter {e['id']} hash mismatch")
                obj = json.loads(raw.decode("utf-8"))
                if obj["id"] != e["id"] or obj["order"] != e["order"] or tag not in obj["text"]:
                    raise ReadbackError(f"chapter {e['id']} id/order/tag mismatch")
        listed_images = set()
        for rel, digest in manifest["artifacts"].items():
            data = read_bytes(os.path.join(root, rel))
            if sha256(data) != digest or tag_of(data) != tag:
                raise ReadbackError(f"{rel} sha/tag mismatch")
            if rel.startswith(IMAGES + "/"):
                listed_images.add(rel.split("/", 1)[1])
        img_dir = os.path.join(root, IMAGES)
        if (os.path.lexists(img_dir) or listed_images) and set(os.listdir(img_dir)) != listed_images:
            raise ReadbackError("images/ does not match manifest")
    except (OSError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadbackError(f"{type(exc).__name__}: {exc}") from exc


def read_chapter(manifest: dict, root: str, chapter_id: str) -> dict:
    """What a reader does: seek by offset/length, verify hash, parse."""
    e = next(x for x in manifest["chapters"] if x["id"] == chapter_id)
    with open(os.path.join(root, CHAPTERS), "rb") as f:
        f.seek(e["offset_bytes"])
        raw = f.read(e["length_bytes"])
    if sha256(raw) != e["sha256"]:
        raise ReadbackError(chapter_id)
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------- classifier


def _legacy_state(book_dir: str) -> str:
    """Flat book.pkl + book.epub + the images the pkl names, all one tag (ADR-0009 missing -> pkl)."""
    try:
        pkl = read_bytes(os.path.join(book_dir, PKL))
        tag = tag_of(pkl)
        if tag_of(read_bytes(os.path.join(book_dir, EPUB))) != tag:
            return "corrupt"
        names = [n for n in pkl.decode().split("images=", 1)[1].split(",") if n]
        for n in names:
            if tag_of(read_bytes(os.path.join(book_dir, IMAGES, n))) != tag:
                return "corrupt"
    except (OSError, IndexError, UnicodeDecodeError):
        return "corrupt"
    return "old-valid" if tag == OLD else "pkl-only-new"


def resolve_root(book_dir: str, layout: str, manifest: dict) -> str:
    if layout == "A":
        return book_dir
    return os.path.join(book_dir, GEN, str(int(manifest["generation"])))


def load_manifest(book_dir: str) -> Optional[dict]:
    path = os.path.join(book_dir, MANIFEST)
    if not os.path.lexists(path):
        return None
    return json.loads(read_bytes(path).decode("utf-8"))


def classify(book_dir: str, layout: str) -> Tuple[str, int]:
    """How a reader opens the directory -> (state, residue).

    state: missing | old-valid | new-valid | corrupt | pkl-only-new (a new pkl
    visible through the missing->pkl fallback before any manifest committed).
    residue: entries beyond the expected set for that state.
    """
    if not os.path.isdir(book_dir):
        return "missing", 0
    user = set(USER_FILES)
    try:
        manifest = load_manifest(book_dir)
    except (OSError, ValueError):
        return "corrupt", 0
    gen_extra = 0
    if manifest is None:
        if os.path.lexists(os.path.join(book_dir, PKL)):
            state, expected = _legacy_state(book_dir), {PKL, EPUB, IMAGES}
        else:
            state, expected = "missing", set()
    else:
        try:
            root = resolve_root(book_dir, layout, manifest)
            validate_book(manifest, root)
        except (ReadbackError, KeyError, TypeError, ValueError):
            return "corrupt", 0
        state = "old-valid" if manifest["version"] == OLD else "new-valid"
        has_images = any(k.startswith(IMAGES + "/") for k in manifest["artifacts"])
        payload = {CHAPTERS, EPUB, PKL} | ({IMAGES} if has_images else set())
        if layout == "A":
            expected = {MANIFEST} | payload
        else:
            expected = {MANIFEST, GEN}
            gens = set(os.listdir(os.path.join(book_dir, GEN)))
            gen_extra = len(gens - {str(manifest["generation"])})
            gen_extra += len(set(os.listdir(root)) - payload)
    residue = len(set(os.listdir(book_dir)) - expected - user) + gen_extra
    return state, residue


# ---------------------------------------------------------------- snapshots


def snapshot_files(paths: List[str]) -> Dict[str, Tuple[bytes, int, int]]:
    out = {}
    for p in paths:
        if os.path.lexists(p):
            st = os.stat(p)
            out[p] = (read_bytes(p), st.st_ino, st.st_mtime_ns)
    return out


def snapshot_tree(root: str) -> Dict[str, tuple]:
    """relpath -> (bytes, ino, mtime_ns) for files, ('dir', ino) for dirs.

    Directory mtimes are deliberately excluded: creating and removing the staging
    (or gen/<g>) entry inside the book dir necessarily bumps the parent's mtime.
    """
    out: Dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            p = os.path.join(dirpath, d)
            out[os.path.relpath(p, root)] = ("dir", os.stat(p).st_ino)
        for n in filenames:
            p = os.path.join(dirpath, n)
            st = os.stat(p)
            out[os.path.relpath(p, root)] = (read_bytes(p), st.st_ino, st.st_mtime_ns)
    return out


def tree_bytes(root: str) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for n in files:
            total += os.lstat(os.path.join(dirpath, n)).st_size
    return total
