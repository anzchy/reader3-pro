"""The versioned, parser-neutral book format (012 WI-1, ADR-0009 / ADR-0016).

This module owns the on-disk format of a processed book: the root ``manifest.json``
pointer, the ``gen/{g}/`` generation layout and the ``chapters.jsonl`` index it
describes. It is stdlib-only and must never import ``reader3_app.reader3``,
``ebooklib`` or ``bs4`` (012 section 6 Q8): readers and the indexer need the format,
not the EPUB parser.

Field freeze (012 section 6 Q7): the field set of :class:`BookManifest` and the
dataclasses it nests is defined here, in code, and frozen by
``tests/unit/snapshots/book_manifest_schema.json``. Adding an optional field (one
with a default) needs no ``FORMAT_VERSION`` bump; removing, renaming, retyping or
changing the meaning of a field requires one. A manifest whose ``format_version``
is above :data:`FORMAT_VERSION` is rejected by the parser, so the book classifies
``corrupt``, never ``valid``.

``book_uuid`` is deliberately absent (Q3: it lives in ``ai_meta.json`` only).
"""
from __future__ import annotations

import dataclasses
import errno
import glob
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import time
import types
import typing
from dataclasses import dataclass
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- constants

FORMAT_VERSION = 1
"""The manifest format this code reads and writes. See the module docstring for the bump rule."""

MANIFEST = "manifest.json"
MANIFEST_TMP = "manifest.json.tmp"
CHAPTERS = "chapters.jsonl"
GEN_DIR = "gen"
EPUB = "book.epub"
PKL = "book.pkl"
IMAGES = "images"

ROOT_USER_DATA: tuple[str, ...] = ("notes.json", "notes.json.lock", "ai_meta.json", "ai_conversations", "chroma_db")
"""The closed list of root entries that are user data: never in a generation, never collected (ADR-0016 amendment 2)."""

RETAIN_S = 300
"""Seconds a superseded generation is kept before a sweep may collect it (ADR-0016)."""

MAX_GENERATION = 2**53
"""Largest generation the parser accepts (inclusive); keeps ``g`` exact in every JSON reader."""

_FIXED_ARTIFACTS = frozenset({CHAPTERS, EPUB, PKL})
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


# --------------------------------------------------------------------------- exceptions


class BookFormatError(Exception):
    """Base of every format-level failure a caller may want to catch as one."""


class ManifestError(ValueError, BookFormatError):
    """``manifest.json`` bytes are not a manifest this code can trust. Raised for every parse rejection."""


class ChapterReadError(ValueError, BookFormatError):
    """A ``chapters.jsonl`` record does not match its manifest index entry."""


class BookCorrupt(BookFormatError):
    """The book directory is in a state publish refuses to write over.

    Read paths raise it too: ``book_store`` loaders raise it for a corrupt ``manifest.json`` (012 WI-3.2).
    """


class ReadbackError(BookFormatError):
    """A written artifact does not read back as what the manifest records."""


class LegacyStagingRefused(BookFormatError):
    """A legacy sibling staging directory cannot be safely resolved."""


class CrossDeviceError(OSError):
    """The generation and the book directory are not on one device; the commit rename cannot be atomic."""

    def __init__(self, message: str, filename: str | None = None) -> None:
        if filename is None:
            super().__init__(errno.EXDEV, message)
        else:
            super().__init__(errno.EXDEV, message, filename)


# --------------------------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class ManifestMetadata:
    """Format-side copy of ``reader3.BookMetadata`` (this module must not import reader3)."""

    title: str
    language: str
    authors: tuple[str, ...]
    description: str | None
    publisher: str | None
    date: str | None
    identifiers: tuple[str, ...]
    subjects: tuple[str, ...]


@dataclass(frozen=True)
class ManifestTocEntry:
    """Format-side copy of ``reader3.TOCEntry``."""

    title: str
    href: str
    file_href: str
    anchor: str
    children: tuple[ManifestTocEntry, ...]


@dataclass(frozen=True)
class ChapterRecord:
    """One line of ``chapters.jsonl`` (ADR-0009): format-side copy of ``reader3.ChapterContent``."""

    id: str
    href: str
    title: str
    content: str
    text: str
    order: int


@dataclass(frozen=True)
class ChapterIndexEntry:
    """Where one chapter's line sits in ``chapters.jsonl``; ``length_bytes`` excludes the newline."""

    id: str
    href: str
    order: int
    offset_bytes: int
    length_bytes: int
    sha256: str


@dataclass(frozen=True)
class ArtifactEntry:
    """One file of a generation. ``path`` is relative to ``gen/{g}``: a fixed name or ``images/<basename>``."""

    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class BookManifest:
    """The root pointer and table of contents of one published generation.

    ``images`` maps each ``images/<basename>`` artifact path to the original EPUB
    paths that resolved to it (``reader3.Book.images`` inverted, so it survives the
    many-to-one mapping). Its key set equals the set of image artifact paths.
    """

    format_version: int
    generation: int
    metadata: ManifestMetadata
    toc: tuple[ManifestTocEntry, ...]
    images: dict[str, tuple[str, ...]]
    source_file: str
    processed_at: str
    book_version: str
    chapters: tuple[ChapterIndexEntry, ...]
    chapters_size_bytes: int
    chapters_sha256: str
    artifacts: tuple[ArtifactEntry, ...]
    # Added as required without bumping FORMAT_VERSION: format not yet released —
    # no v1 manifest exists outside this branch.
    book_fingerprint: str
    extractor_version: int


# --------------------------------------------------------------------------- serialisation


def _to_json(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_json(v) for v in value]
    return value


def manifest_to_bytes(manifest: BookManifest) -> bytes:
    """Canonical bytes: sorted keys, raw UTF-8, two-space indent, one trailing newline. Byte-deterministic."""
    text = json.dumps(_to_json(manifest), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": "))
    return (text + "\n").encode("utf-8")


# --------------------------------------------------------------------------- parsing


def _fail(where: str, why: str) -> typing.NoReturn:
    raise ManifestError(f"{where or '<root>'}: {why}")


def _parse_int(value: Any, where: str) -> int:
    # bool is an int subclass; True must never pass as 1.
    if type(value) is not int:
        _fail(where, f"expected int, got {type(value).__name__}")
    if value < 0:
        _fail(where, "must not be negative")
    return value


def _parse_str(value: Any, where: str) -> str:
    if type(value) is not str:
        _fail(where, f"expected string, got {type(value).__name__}")
    return value


def _parse_value(tp: Any, value: Any, where: str) -> Any:
    if tp is int:
        return _parse_int(value, where)
    if tp is str:
        return _parse_str(value, where)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return _parse_dataclass(tp, value, where)
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is typing.Union or origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        (inner,) = [a for a in args if a is not type(None)]
        return _parse_value(inner, value, where)
    if origin is tuple:
        if type(value) is not list:
            _fail(where, f"expected array, got {type(value).__name__}")
        return tuple(_parse_value(args[0], item, f"{where}[{i}]") for i, item in enumerate(value))
    if origin is dict:
        if type(value) is not dict:
            _fail(where, f"expected object, got {type(value).__name__}")
        return {
            _parse_value(args[0], k, f"{where} key"): _parse_value(args[1], v, f"{where}[{k!r}]")
            for k, v in value.items()
        }
    raise TypeError(f"unsupported manifest field type {tp!r}")  # a schema bug, not a data error


def _parse_dataclass(cls: type, value: Any, where: str) -> Any:
    if type(value) is not dict:
        _fail(where, f"expected object, got {type(value).__name__}")
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        sub = f"{where}.{f.name}" if where else f.name
        if f.name in value:
            kwargs[f.name] = _parse_value(hints[f.name], value[f.name], sub)
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            _fail(sub, "required key missing")
        # Keys the schema does not know are ignored (Q7: a same-version optional addition stays readable).
    return cls(**kwargs)


def is_legal_artifact_path(path: str) -> bool:
    """True iff ``path`` names a file directly inside ``gen/{g}``: a fixed name or ``images/<basename>``."""
    if path in _FIXED_ARTIFACTS:
        return True
    prefix = IMAGES + "/"
    if not path.startswith(prefix):
        return False
    name = path[len(prefix):]
    return bool(name) and name not in (".", "..") and not any(c in name for c in "/\\\x00")


def _check_sha(value: str, where: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        _fail(where, "must be 64 lowercase hex characters")


def _check_manifest(m: BookManifest) -> None:
    if not 1 <= m.format_version <= FORMAT_VERSION:
        _fail("format_version", f"{m.format_version} is not a version this code knows (1..{FORMAT_VERSION})")
    if not 1 <= m.generation <= MAX_GENERATION:
        _fail("generation", f"must be in 1..2**53, got {m.generation}")
    _check_sha(m.chapters_sha256, "chapters_sha256")
    _check_sha(m.book_fingerprint, "book_fingerprint")

    artifacts: dict[str, ArtifactEntry] = {}
    for i, art in enumerate(m.artifacts):
        where = f"artifacts[{i}]"
        if not is_legal_artifact_path(art.path):
            _fail(f"{where}.path", f"illegal artifact path {art.path!r}")
        if art.path in artifacts:
            _fail(f"{where}.path", f"duplicate artifact path {art.path!r}")
        _check_sha(art.sha256, f"{where}.sha256")
        artifacts[art.path] = art

    chapters_art = artifacts.get(CHAPTERS)
    if chapters_art is None:
        _fail("artifacts", f"no {CHAPTERS} artifact")
    if chapters_art.size_bytes != m.chapters_size_bytes:
        _fail("chapters_size_bytes", f"disagrees with the {CHAPTERS} artifact")
    if chapters_art.sha256 != m.chapters_sha256:
        _fail("chapters_sha256", f"disagrees with the {CHAPTERS} artifact")

    for key in m.images:
        if not key.startswith(IMAGES + "/") or not is_legal_artifact_path(key):
            _fail("images", f"illegal image path {key!r}")
    image_artifacts = {p for p in artifacts if p.startswith(IMAGES + "/")}
    if set(m.images) != image_artifacts:
        _fail("images", "image map and image artifacts disagree")

    seen_ids: set[str] = set()
    expected_offset = 0
    for i, ch in enumerate(m.chapters):
        where = f"chapters[{i}]"
        if ch.id in seen_ids:
            _fail(f"{where}.id", f"duplicate chapter id {ch.id!r}")
        seen_ids.add(ch.id)
        _check_sha(ch.sha256, f"{where}.sha256")
        if ch.offset_bytes != expected_offset:
            _fail(f"{where}.offset_bytes", f"expected {expected_offset} (chapters must be contiguous from 0)")
        expected_offset = ch.offset_bytes + ch.length_bytes + 1
    if expected_offset != m.chapters_size_bytes:
        _fail("chapters", f"records end at {expected_offset}, not at chapters_size_bytes {m.chapters_size_bytes}")


def manifest_from_bytes(data: bytes) -> BookManifest:
    """Strictly parse manifest bytes. Every rejection raises :class:`ManifestError`, nothing else."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"not UTF-8: {exc}") from None
    try:
        obj = json.loads(text)  # a leading BOM is rejected here
    except (ValueError, RecursionError) as exc:
        raise ManifestError(f"not JSON: {exc}") from None
    if type(obj) is not dict:
        _fail("", f"top level must be an object, got {type(obj).__name__}")
    try:
        manifest = _parse_dataclass(BookManifest, obj, "")
    except RecursionError:
        raise ManifestError("manifest nesting too deep") from None
    _check_manifest(manifest)
    return typing.cast(BookManifest, manifest)


# --------------------------------------------------------------------------- book fingerprint

EXTRACTOR_VERSION_UNKNOWN = 0
"""Reserved ``extractor_version`` for books whose extractor is not known (WI-6 migration). ``EXTRACTOR_VERSION``
itself lives in ``reader3``: this module takes the version as a parameter and never imports the extractor."""


def _fingerprint_payload(epub_sha256: str, spine: Sequence[tuple[str, int, str]], extractor_version: int) -> bytes:
    """The canonical bytes the fingerprint hashes. JSON quoting makes them decodable, hence injective."""
    _check_sha(_parse_str(epub_sha256, "epub_sha256"), "epub_sha256")
    items: list[list[Any]] = []
    for i, item in enumerate(spine):  # positional: the spine is never sorted
        where = f"spine[{i}]"
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            _fail(where, "expected (href, order, sha256)")
        href, order, sha = item
        _parse_str(href, f"{where}.href")
        _parse_int(order, f"{where}.order")
        _check_sha(_parse_str(sha, f"{where}.sha256"), f"{where}.sha256")
        items.append([href, order, sha])
    _parse_int(extractor_version, "extractor_version")
    payload = {"epub_sha256": epub_sha256, "spine": items, "extractor_version": extractor_version}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def compute_book_fingerprint(epub_sha256: str, spine: Sequence[tuple[str, int, str]], extractor_version: int) -> str:
    """sha256 hex of ``(epub_sha256, spine, extractor_version)``; ``spine`` is ``(href, order, raw_xhtml_sha256)``.

    Pure: no clock, filesystem or environment. Malformed input raises :class:`ManifestError` rather than hashing.
    """
    return hashlib.sha256(_fingerprint_payload(epub_sha256, spine, extractor_version)).hexdigest()


# --------------------------------------------------------------------------- chapters.jsonl


_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_READ_CHUNK = 1 << 20

_CHAPTER_FIELDS: dict[str, type] = {"id": str, "href": str, "title": str, "content": str, "text": str, "order": int}


def _chapter_line(chapter: ChapterRecord) -> bytes:
    """Canonical line bytes, newline excluded: raw UTF-8, sorted keys, compact separators.

    ``json.dumps`` escapes ``\\n``/``\\r``/control characters, so the only raw ``b"\\n"`` in the
    file is the record terminator; U+2028/U+2029 stay raw and are not line breaks to a byte reader.
    """
    text = json.dumps(dataclasses.asdict(chapter), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def write_chapters(
    path: str | os.PathLike[str], chapters: Sequence[ChapterRecord]
) -> tuple[tuple[ChapterIndexEntry, ...], int, str]:
    """Write ``chapters.jsonl`` at ``path``; return ``(index entries, file size, file sha256)``.

    Offsets, lengths and hashes come from the in-memory line bytes, so the index describes exactly
    what was written. The file is created like every other artifact (:func:`_write_new`): exclusive,
    write-only, mode ``0o644``, never through a symlink, so an existing file or link at ``path`` raises
    (``FileExistsError``) and is left untouched. It is fsynced before it is closed.
    """
    entries: list[ChapterIndexEntry] = []
    whole = hashlib.sha256()
    offset = 0
    pending = bytearray()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o644)
    try:
        for chapter in chapters:
            line = _chapter_line(chapter)
            entries.append(
                ChapterIndexEntry(
                    id=chapter.id,
                    href=chapter.href,
                    order=chapter.order,
                    offset_bytes=offset,
                    length_bytes=len(line),
                    sha256=hashlib.sha256(line).hexdigest(),
                )
            )
            pending += line
            pending += b"\n"
            whole.update(line)
            whole.update(b"\n")
            offset += len(line) + 1
            if len(pending) >= _READ_CHUNK:
                _write_all(fd, bytes(pending))
                pending.clear()
        _write_all(fd, bytes(pending))
        os.fsync(fd)
    finally:
        os.close(fd)
    return tuple(entries), offset, whole.hexdigest()


def _write_all(fd: int, data: bytes) -> None:
    """``os.write`` until every byte of ``data`` is written (a short write is not an error)."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def read_chapter(gen_dir: str | os.PathLike[str], entry: ChapterIndexEntry) -> ChapterRecord:
    """Seek-read one record of ``gen_dir/chapters.jsonl`` and check it against its index entry.

    Raises :class:`ChapterReadError` when the span is out of range or short, is not followed by the
    newline terminator, fails its sha256, does not parse as a record, or names a different
    ``id``/``href``/``order`` than ``entry``. A missing file surfaces as the ``OSError`` it is.
    """
    where = f"{CHAPTERS} record {entry.id!r}"
    if entry.offset_bytes < 0 or entry.length_bytes < 0:
        raise ChapterReadError(f"{where}: negative offset or length")
    with open(os.path.join(gen_dir, CHAPTERS), "rb") as fh:
        fh.seek(entry.offset_bytes)
        data = fh.read(entry.length_bytes + 1)
    if len(data) != entry.length_bytes + 1:
        raise ChapterReadError(f"{where}: short read ({len(data)} of {entry.length_bytes + 1} bytes)")
    line, terminator = data[:-1], data[-1:]
    if terminator != b"\n":
        raise ChapterReadError(f"{where}: record is not newline-terminated at its recorded length")
    if hashlib.sha256(line).hexdigest() != entry.sha256:
        raise ChapterReadError(f"{where}: sha256 mismatch")
    try:
        obj = json.loads(line.decode("utf-8"))
    except (ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise ChapterReadError(f"{where}: not a JSON record: {exc}") from None
    if type(obj) is not dict:
        raise ChapterReadError(f"{where}: record is not an object")
    for name, tp in _CHAPTER_FIELDS.items():
        if type(obj.get(name)) is not tp:  # exact type: bool never passes as int
            raise ChapterReadError(f"{where}: field {name!r} missing or not {tp.__name__}")
    record = ChapterRecord(**{name: obj[name] for name in _CHAPTER_FIELDS})
    if (record.id, record.href, record.order) != (entry.id, entry.href, entry.order):
        raise ChapterReadError(f"{where}: line holds id/href/order {(record.id, record.href, record.order)!r}")
    return record



# --------------------------------------------------------------------------- validators and classifier

BookState = typing.Literal["missing", "corrupt", "valid"]
"""ADR-0007's three read states, with ADR-0016's generation checks folded into ``corrupt``."""


def _lstat_present(path: str, what: str) -> os.stat_result:
    """``lstat`` that reports an absent path as :class:`ReadbackError`; other ``OSError``s propagate."""
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        raise ReadbackError(f"{what} is missing: {path}") from None


def _require_real_dir(path: str, what: str) -> None:
    """``path`` must be a directory itself, never a symlink to one (``lstat``, never follow)."""
    if not stat.S_ISDIR(_lstat_present(path, what).st_mode):
        raise ReadbackError(f"{what} is not a real directory (file or symlink): {path}")


def _read_nofollow(path: str) -> bytes:
    """Read a regular file without following a final symlink and without going through ``open()``."""
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ReadbackError(f"not a regular file: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(fd, _READ_CHUNK):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _sha256_nofollow(path: str) -> tuple[int, str]:
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ReadbackError(f"not a regular file: {path}")
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(fd, _READ_CHUNK):
            digest.update(chunk)
            size += len(chunk)
        return size, digest.hexdigest()
    finally:
        os.close(fd)


def _read_manifest(book_dir: str | os.PathLike[str]) -> BookManifest:
    path = os.path.join(book_dir, MANIFEST)
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ManifestError(f"{MANIFEST} is not a regular file (directory or symlink)")
    try:
        data = _read_nofollow(path)
    except ReadbackError as exc:  # swapped for a non-file between lstat and open
        raise ManifestError(str(exc)) from None
    return manifest_from_bytes(data)


def _check_artifacts_stat(gen_dir: str, manifest: BookManifest) -> None:
    """Every recorded artifact is a regular file (never a symlink, nor under one) of its recorded size."""
    if any(a.path.startswith(IMAGES + "/") for a in manifest.artifacts):
        _require_real_dir(os.path.join(gen_dir, IMAGES), f"{IMAGES}/")
    for art in manifest.artifacts:
        st = _lstat_present(os.path.join(gen_dir, art.path), f"artifact {art.path!r}")
        if not stat.S_ISREG(st.st_mode):
            raise ReadbackError(f"artifact {art.path!r} is not a regular file (directory or symlink)")
        if st.st_size != art.size_bytes:
            raise ReadbackError(f"artifact {art.path!r} is {st.st_size} bytes, manifest records {art.size_bytes}")


def validate_stat(book_dir: str | os.PathLike[str]) -> BookManifest:
    """The stat-only check (ADR-0016 amendment 3); returns the parsed manifest.

    ``manifest.json`` is a regular file that parses with a known ``format_version`` and an int
    ``generation``; ``gen`` and ``gen/{g}`` are real directories; every recorded artifact is a regular
    file whose size matches. Only the manifest's contents are read. Symlinks are never followed.

    Raises :class:`ManifestError` for the manifest, :class:`ReadbackError` for the generation, and
    ``OSError`` (``FileNotFoundError`` when the manifest is absent) for anything the OS refuses.
    """
    manifest = _read_manifest(book_dir)
    gen_root = os.path.join(book_dir, GEN_DIR)
    _require_real_dir(gen_root, f"{GEN_DIR}/")
    gen_dir = os.path.join(gen_root, str(manifest.generation))
    _require_real_dir(gen_dir, f"{GEN_DIR}/{manifest.generation}/")
    _check_artifacts_stat(gen_dir, manifest)
    return manifest


def validate_full(gen_dir: str | os.PathLike[str], manifest: BookManifest) -> None:
    """Content check of one generation against ``manifest`` (which need not be on disk yet: publish step 6).

    Adds to the stat checks: the sha256 of every artifact (``chapters.jsonl`` included), a
    :func:`read_chapter` of every index entry, and that the files in ``images/`` are exactly the
    manifest's image set. Raises :class:`ReadbackError` / :class:`ChapterReadError`, or ``OSError``.
    """
    gen = os.fspath(gen_dir)
    _require_real_dir(gen, "generation directory")
    _check_artifacts_stat(gen, manifest)
    images_dir = os.path.join(gen, IMAGES)
    on_disk: set[str] = set()
    if os.path.lexists(images_dir):
        _require_real_dir(images_dir, f"{IMAGES}/")
        on_disk = {f"{IMAGES}/{name}" for name in os.listdir(images_dir)}
    if on_disk != set(manifest.images):
        extra, absent = sorted(on_disk - set(manifest.images)), sorted(set(manifest.images) - on_disk)
        raise ReadbackError(f"{IMAGES}/ differs from the manifest: extra {extra}, missing {absent}")
    for art in manifest.artifacts:
        size, sha = _sha256_nofollow(os.path.join(gen, art.path))
        if (size, sha) != (art.size_bytes, art.sha256):
            raise ReadbackError(f"artifact {art.path!r} does not match its recorded size and sha256")
    for entry in manifest.chapters:
        read_chapter(gen, entry)


def classify(book_dir: str | os.PathLike[str], *, full: bool) -> BookState:
    """Classify a book directory as ``missing`` / ``corrupt`` / ``valid``. Read-only; never follows a symlink.

    ``missing``: ``book_dir`` is absent (or not a directory) or ``manifest.json`` does not ``lexists``;
    ``gen/``, ``manifest.json.tmp`` and flat legacy files are never evidence of a book. ``corrupt``: the
    manifest exists but cannot be read (any ``OSError``), is not a regular file, does not parse, or the
    generation fails :func:`validate_stat` (and, when ``full``, :func:`validate_full`). ``valid`` otherwise.
    """
    try:
        os.lstat(os.path.join(book_dir, MANIFEST))
    except (FileNotFoundError, NotADirectoryError):
        return "missing"
    except OSError:
        return "corrupt"
    try:
        manifest = validate_stat(book_dir)
        if full:
            validate_full(os.path.join(book_dir, GEN_DIR, str(manifest.generation)), manifest)
    except (BookFormatError, OSError):
        return "corrupt"
    return "valid"


# --------------------------------------------------------------------------- legacy pre-012 sibling staging
#
# Before 012 a publish built its artifacts in a sibling ``<book>.staging-<pid>`` and swapped them in with a
# rename-aside commit (``reader3._commit_staged_artifacts``). ADR-0016 retires that protocol but keeps a
# read-only classifier for what it may have left behind, until sunset. No pid / flock ownership probe is
# ported: under the caller's EX book lock there is no other in-flight run (ADR-0016, REPORT section 8).

_STAGING_INFIX = ".staging-"
_STAGING_SUFFIX_RE = re.compile(r"[0-9]+")
_SUPERSEDED = ".superseded"

_KNOWN_ASIDES: dict[str, str] = {"book.epub.superseded": EPUB, "images.superseded": IMAGES}
"""The only asides the legacy commit ever created, each mapped to the live path it was moved out of."""


@dataclass(frozen=True)
class LegacyStagingReport:
    """Read-only classification of the pre-012 ``<book>.staging-<pid>`` siblings of one book.

    Every path is absolute and each group is sorted. ``parked``: holds ``book.pkl`` plus at least one
    top-level ``*.superseded`` entry, i.e. a run died inside the legacy commit window and the asides are the
    only copy of the previously published files. ``uninspectable``: could not be listed, or is not a real
    directory (a regular file, or a symlink, which is never followed). ``debris``: everything else.
    ``asides`` pairs each parked path with its sorted aside names; ``errors`` pairs each uninspectable path
    with an operator-searchable description (``"EACCES: Permission denied"``).
    """

    debris: tuple[str, ...]
    parked: tuple[str, ...]
    uninspectable: tuple[str, ...]
    asides: tuple[tuple[str, tuple[str, ...]], ...] = ()
    errors: tuple[tuple[str, str], ...] = ()


def _describe_os_error(exc: OSError) -> str:
    name = errno.errorcode.get(exc.errno) if exc.errno is not None else None
    if name and exc.strerror:
        return f"{name}: {exc.strerror}"
    return str(exc)


def classify_legacy_staging(book_dir: str | os.PathLike[str]) -> LegacyStagingReport:
    """Classify the legacy sibling staging directories of ``book_dir``. Strictly read-only.

    Only ``<book>.staging-<ASCII digits>`` is ours (the legacy code named them after ``os.getpid()``); a
    real book folder always ends in ``_data``, so ``sample_data.staging-1_data`` or a user's
    ``sample_data.staging-backup`` is never listed, let alone deleted. The book name is ``glob.escape``d
    because a folder named after an EPUB may contain ``*``, ``?`` or ``[``. A leftover that vanishes between
    the glob and its listing is skipped. Nothing is followed: a symlinked leftover is uninspectable.
    """
    base = os.path.abspath(os.fspath(book_dir))
    prefix = base + _STAGING_INFIX
    debris: list[str] = []
    parked: list[tuple[str, tuple[str, ...]]] = []
    uninspectable: list[tuple[str, str]] = []
    for leftover in sorted(glob.glob(glob.escape(base) + _STAGING_INFIX + "*")):
        if not leftover.startswith(prefix) or not _STAGING_SUFFIX_RE.fullmatch(leftover[len(prefix):]):
            continue
        try:
            st_ = os.lstat(leftover)
        except FileNotFoundError:
            continue
        except OSError as exc:
            uninspectable.append((leftover, _describe_os_error(exc)))
            continue
        if stat.S_ISLNK(st_.st_mode):
            uninspectable.append((leftover, "symbolic link; not followed"))
            continue
        try:
            names = os.listdir(leftover)
        except FileNotFoundError:
            continue
        except OSError as exc:
            uninspectable.append((leftover, _describe_os_error(exc)))
            continue
        asides = tuple(sorted(n for n in names if n.endswith(_SUPERSEDED))) if PKL in names else ()
        if asides:
            parked.append((leftover, asides))
        else:
            debris.append(leftover)
    return LegacyStagingReport(
        debris=tuple(debris),
        parked=tuple(path for path, _ in parked),
        uninspectable=tuple(path for path, _ in uninspectable),
        asides=tuple(parked),
        errors=tuple(uninspectable),
    )


def _refusal_message(book_dir: str, report: LegacyStagingReport) -> str:
    """Manual recovery steps, one ``src -> dst`` line per move that is safe to follow mechanically.

    Ported from ``reader3._unlanded_commit_message``: a move is written only for a known aside that exactly
    one leftover parks; competing candidates and unrecognised ``*.superseded`` names are listed for
    inspection, never mapped onto a live path, and their directory is marked to be kept.
    """
    if report.parked:
        lines = [
            f"refusing to publish {book_dir}: a pre-012 run was killed while swapping in a new version, so "
            f"{book_dir} may be a mixed old/new version. The previous version's files are parked in the "
            "staging directory below and are their only copy. Put them back by hand, in this order:",
        ]
    else:
        lines = [
            f"refusing to publish {book_dir}: a pre-012 staging directory could not be inspected, so there is "
            "no telling whether it holds the previous version's files. Nothing was changed. Resolve it by hand:",
        ]
    candidates: dict[str, list[str]] = {}
    for leftover, asides in report.asides:
        for aside in asides:
            if aside in _KNOWN_ASIDES:
                candidates.setdefault(aside, []).append(os.path.join(leftover, aside))
    for aside, paths in sorted(candidates.items()):
        if len(paths) > 1:
            lines.append(
                f"  {os.path.join(book_dir, _KNOWN_ASIDES[aside])} was parked by more than one earlier run; "
                "inspect every candidate and choose one to put back by hand:"
            )
            lines.extend(f"    candidate: {path}" for path in paths)
    for leftover, asides in report.asides:
        lines.append(f"  from {leftover}:")
        settled = True
        for aside in asides:
            aside_path = os.path.join(leftover, aside)
            live_name = _KNOWN_ASIDES.get(aside)
            if live_name is None:
                lines.append(f"    {aside_path} is not a file this program parks; inspect it by hand")
                settled = False
            elif len(candidates[aside]) > 1:
                lines.append(f"    {aside_path} is one of the candidates listed above")
                settled = False
            else:
                live = os.path.join(book_dir, live_name)
                if os.path.lexists(live):
                    lines.append(f"    remove {live}")
                lines.append(f"    {aside_path} -> {live}")
        lines.append(f"    then delete {leftover}" if settled else f"    keep {leftover} until resolved")
    for leftover, error in report.errors:
        lines.append(f"  inspect {leftover} by hand; it may hold the only copy of the published version ({error})")
    lines.append(f"Publishing {book_dir} is refused until that is done.")
    return "\n".join(lines)


def resolve_legacy_staging(book_dir: str | os.PathLike[str]) -> LegacyStagingReport:
    """Publish preflight for legacy sibling staging; the caller holds the EX book lock.

    Classifies every leftover first. If anything is parked or uninspectable, raises
    :class:`LegacyStagingRefused` with manual recovery steps and touches nothing, the debris included.
    Otherwise removes exactly the debris (each verified a real directory by ``lstat``; ``rmtree`` never
    follows a symlink inside it) and returns the report it acted on. Idempotent.
    """
    base = os.path.abspath(os.fspath(book_dir))
    report = classify_legacy_staging(base)
    if report.parked or report.uninspectable:
        raise LegacyStagingRefused(_refusal_message(base, report))
    for leftover in report.debris:
        # Parity with reader3._clear_staging_dirs: debris holds nothing anyone needs, so a partial removal
        # is left for the next preflight rather than failing the publish.
        shutil.rmtree(leftover, ignore_errors=True)
    return report


# --------------------------------------------------------------------------- safe GC and recovery (WI-1.5)
#
# ADR-0016 "safe GC": recovery *is* GC. Only ``gen/*`` and ``manifest.json`` / ``manifest.json.tmp`` are ever
# enumerated or deleted; the book root is never listed, so the closed list of user data (ROOT_USER_DATA), stray
# files and legacy flat files are untouched by construction. reader3's ``_remove_legacy`` is deliberately not
# ported. Nothing is ever rolled forward: a tmp, however valid it looks, is unlinked, never promoted.

_CANONICAL_GEN_RE = re.compile(r"[1-9][0-9]*", flags=re.ASCII)


def is_canonical_gen_name(name: str) -> bool:
    """The one predicate for a generation directory name, shared by GC and the publisher's ``g`` computation.

    Exactly ``re.fullmatch(r"[1-9][0-9]*", name, flags=re.ASCII)`` on the ``str`` entry name: no leading zero,
    sign, whitespace, trailing newline or non-ASCII digit. ``int()`` must never be applied to a raw name.
    """
    return type(name) is str and _CANONICAL_GEN_RE.fullmatch(name) is not None


@dataclass(frozen=True)
class GcResult:
    """What one :func:`collect_garbage` run decided and did.

    ``state`` is the book's state as GC judged it. ``deleted`` holds the removed entries (``gen/<n>`` and
    ``manifest.json.tmp``) and ``skipped`` the non-canonical ``gen/*`` entries left alone; both are sorted
    paths relative to the book directory.
    """

    state: BookState
    deleted: tuple[str, ...]
    skipped: tuple[str, ...]


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _gc_corrupt(book: str, reason: str) -> GcResult:
    logger.error("collect_garbage: book %s is corrupt, nothing deleted: %s", book, reason)
    return GcResult("corrupt", (), ())


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def collect_garbage(
    book_dir: str | os.PathLike[str], *, min_manifest_age_s: float | None = None, now: float | None = None
) -> GcResult:
    """Recovery and GC of one book directory; the caller holds the EX book lock (ADR-0015).

    - ``book_dir`` absent (or not a real directory): a no-op reporting ``missing``; nothing is created.
    - Corruption is decided first, before any deletion. ``gen`` that is a symlink or not a directory, a
      ``manifest.json`` that exists but fails :func:`validate_stat`, or any ``OSError`` while deciding: the book
      is ``corrupt``, an ERROR names the book and the failed check, and nothing at all is deleted.
    - No ``manifest.json``: every canonical ``gen/<n>`` is unreferenced and is deleted, then the tmp. The age
      guard does not apply.
    - Valid manifest: if ``min_manifest_age_s`` is set (sweep mode, :data:`RETAIN_S`) and the manifest's mtime is
      newer than ``now - min_manifest_age_s``, nothing is deleted. Otherwise every canonical ``gen/<n>`` other
      than the current generation (orphans newer than current included) is deleted, then the tmp.

    Non-canonical ``gen/*`` names are never deleted (they are reported in ``skipped`` and logged). A symlinked
    ``gen/*`` entry is unlinked, never followed, and ``rmtree`` never follows a link inside a collected
    generation. After any deletion ``gen/`` and the book directory are fsynced. Idempotent.
    """
    _crash_point("gc.validate", "before")
    result = _gc_decide(os.fspath(book_dir), min_manifest_age_s, now)
    _crash_point("gc.validate", "after")
    if isinstance(result, GcResult):
        return result
    return _gc_delete(*result)


_GcPlan = tuple[str, BookState, typing.Optional[os.stat_result], list[str], tuple[str, ...]]


def _gc_decide(book: str, min_manifest_age_s: float | None, now: float | None) -> GcResult | _GcPlan:
    """GC's read-only half: a final :class:`GcResult` when nothing may be deleted, else the deletion plan."""
    try:
        book_st = os.lstat(book)
    except (FileNotFoundError, NotADirectoryError):
        return GcResult("missing", (), ())
    if not stat.S_ISDIR(book_st.st_mode):
        return GcResult("missing", (), ())

    manifest_path = os.path.join(book, MANIFEST)
    gen_root = os.path.join(book, GEN_DIR)
    try:
        os.lstat(manifest_path)
        has_manifest = True
    except FileNotFoundError:
        has_manifest = False
    except OSError as exc:
        return _gc_corrupt(book, f"{MANIFEST} cannot be inspected: {_describe(exc)}")

    current: str | None = None
    if has_manifest:
        try:
            manifest = validate_stat(book)
        except (BookFormatError, OSError) as exc:
            return _gc_corrupt(book, _describe(exc))
        current = str(manifest.generation)
        if min_manifest_age_s is not None:
            when = time.time() if now is None else now
            try:
                mtime_ns = os.lstat(manifest_path).st_mtime_ns
            except OSError as exc:
                return _gc_corrupt(book, f"{MANIFEST} vanished during GC: {_describe(exc)}")
            if when - mtime_ns / 1e9 < min_manifest_age_s:
                return GcResult("valid", (), ())
    state: BookState = "valid" if has_manifest else "missing"

    try:
        gen_st: os.stat_result | None = os.lstat(gen_root)
    except FileNotFoundError:
        gen_st = None
    except OSError as exc:
        return _gc_corrupt(book, f"{GEN_DIR}/ cannot be inspected: {_describe(exc)}")
    if gen_st is not None and not stat.S_ISDIR(gen_st.st_mode):
        return _gc_corrupt(book, f"{GEN_DIR}/ is not a real directory (file or symlink): {gen_root}")

    names: list[str] = []
    if gen_st is not None:
        try:
            names = sorted(os.listdir(gen_root))
        except OSError as exc:
            return _gc_corrupt(book, f"{GEN_DIR}/ cannot be listed: {_describe(exc)}")
    victims = [n for n in names if is_canonical_gen_name(n) and n != current]
    skipped = tuple(sorted(f"{GEN_DIR}/{n}" for n in names if not is_canonical_gen_name(n)))
    if skipped:
        logger.warning("collect_garbage: %s: left non-canonical entries alone: %s", book, ", ".join(skipped))
    return book, state, gen_st, victims, skipped


def _gc_delete(
    book: str, state: BookState, gen_st: os.stat_result | None, victims: list[str], skipped: tuple[str, ...]
) -> GcResult:
    """GC's deleting half, run only after :func:`_gc_decide` judged the book ``valid`` or ``missing``."""
    gen_root = os.path.join(book, GEN_DIR)
    deleted: list[str] = []
    for name in victims:
        path = os.path.join(gen_root, name)
        try:
            entry_st = os.lstat(path)
        except FileNotFoundError:
            continue
        _crash_point("gc.delete", "before")
        if stat.S_ISDIR(entry_st.st_mode):
            shutil.rmtree(path)  # never follows a symlink inside the tree
        else:
            os.unlink(path)  # a symlink (to a dir or a file) or a stray file: the link itself, never its target
        _crash_point("gc.delete", "after")
        deleted.append(f"{GEN_DIR}/{name}")

    tmp_path = os.path.join(book, MANIFEST_TMP)
    try:
        tmp_st: os.stat_result | None = os.lstat(tmp_path)
    except FileNotFoundError:
        tmp_st = None
    if tmp_st is not None:
        if stat.S_ISDIR(tmp_st.st_mode):
            logger.warning("collect_garbage: %s: %s is a directory; left alone", book, MANIFEST_TMP)
            skipped = tuple(sorted((*skipped, MANIFEST_TMP)))
        else:
            _crash_point("gc.tmp", "before")
            os.unlink(tmp_path)
            _crash_point("gc.tmp", "after")
            deleted.append(MANIFEST_TMP)

    if deleted:
        if gen_st is not None:
            _fsync_dir(gen_root)
        _fsync_dir(book)
    return GcResult(state, tuple(sorted(deleted)), skipped)


# --------------------------------------------------------------------------- publisher (WI-1.6)

PUBLISH_HOOKS: tuple[str, ...] = (
    "p0", "p0.legacy", "gc.validate", "gc.delete", "gc.tmp",
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p8.fsync",
)
"""Every step name :func:`_crash_point` is called with, in publish order; each is bracketed ``before``/``after``."""


def _crash_point(step: str, when: str) -> None:
    """No-op seam bracketing every publish / GC step; tests replace it. Never driven by the environment."""


Source = typing.Union[bytes, bytearray, str, "os.PathLike[str]"]
"""Artifact content: the bytes themselves, or a path read in bounded blocks."""


class PublishInputError(ValueError, BookFormatError):
    """:class:`PublishInputs` that cannot be published; raised before any filesystem effect."""


@dataclass(frozen=True)
class PublishInputs:
    """Everything one publish writes into a new generation.

    ``images`` maps an image *basename* to its content; ``image_origins`` maps the same basename to the
    original EPUB paths that resolved to it (the manifest ``images`` map); a basename without origins
    records ``()``. Every sha256 is computed from these sources, never from the written file.
    """

    metadata: ManifestMetadata
    toc: tuple[ManifestTocEntry, ...]
    chapters: tuple[ChapterRecord, ...]
    source_file: str
    processed_at: str
    book_version: str
    # Added as required without bumping FORMAT_VERSION: format not yet released —
    # no v1 manifest exists outside this branch.
    book_fingerprint: str
    extractor_version: int
    epub: Source | None = None
    images: typing.Mapping[str, Source] = dataclasses.field(default_factory=dict)
    image_origins: typing.Mapping[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    pkl: Source | None = None


def _validate_inputs(inputs: PublishInputs) -> None:
    """Reject inputs that cannot be published, before any filesystem effect (matrix A5)."""
    seen: set[str] = set()
    prev_order = -1  # ``order`` is the raw EPUB spine index: >= 0, strictly increasing, gaps legal, never renumbered
    for i, ch in enumerate(inputs.chapters):
        if type(ch) is not ChapterRecord:
            raise PublishInputError(f"chapters[{i}] is not a ChapterRecord")
        for name, tp in _CHAPTER_FIELDS.items():
            if type(getattr(ch, name)) is not tp:
                raise PublishInputError(f"chapters[{i}].{name} must be {tp.__name__}")
        if ch.id in seen:
            raise PublishInputError(f"duplicate chapter id {ch.id!r}")
        seen.add(ch.id)
        if ch.order <= prev_order:
            raise PublishInputError(
                f"chapters[{i}].order is {ch.order}; orders must be non-negative and strictly increasing"
                f" (previous: {prev_order if i else 'none'})"
            )
        prev_order = ch.order
    for name in inputs.images:
        if type(name) is not str or not is_legal_artifact_path(f"{IMAGES}/{name}"):
            raise PublishInputError(f"illegal image basename {name!r}")
    unknown = set(inputs.image_origins) - set(inputs.images)
    if unknown:
        raise PublishInputError(f"image_origins names images that are not published: {sorted(unknown)}")
    for what, src in (("epub", inputs.epub), ("pkl", inputs.pkl), *inputs.images.items()):
        if src is not None and not isinstance(src, (bytes, bytearray, str, os.PathLike)):
            raise PublishInputError(f"{what}: a source is bytes or a path, got {type(src).__name__}")
    # Schema problems in metadata / toc / strings surface here, with placeholder sizes and hashes.
    zero = "0" * 64
    placeholders = {CHAPTERS: (0, zero), **{f"{IMAGES}/{n}": (0, zero) for n in inputs.images}}
    try:
        manifest_from_bytes(manifest_to_bytes(_build_manifest(inputs, 1, (), 0, zero, placeholders)))
    except (ManifestError, TypeError, ValueError, RecursionError) as exc:
        raise PublishInputError(f"inputs do not form a valid manifest: {exc}") from None


def _build_manifest(
    inputs: PublishInputs, g: int, entries: tuple[ChapterIndexEntry, ...], chapters_size: int, chapters_sha: str,
    written: dict[str, tuple[int, str]],
) -> BookManifest:
    return BookManifest(
        format_version=FORMAT_VERSION,
        generation=g,
        metadata=inputs.metadata,
        toc=tuple(inputs.toc),
        images={f"{IMAGES}/{n}": tuple(inputs.image_origins.get(n, ())) for n in inputs.images},
        source_file=inputs.source_file,
        processed_at=inputs.processed_at,
        book_version=inputs.book_version,
        chapters=entries,
        chapters_size_bytes=chapters_size,
        chapters_sha256=chapters_sha,
        artifacts=tuple(
            ArtifactEntry(path=path, size_bytes=size, sha256=sha) for path, (size, sha) in sorted(written.items())
        ),
        book_fingerprint=inputs.book_fingerprint,
        extractor_version=inputs.extractor_version,
    )


def _source_chunks(src: Source) -> typing.Iterator[bytes]:
    if isinstance(src, (bytes, bytearray)):
        yield bytes(src)
        return
    with open(src, "rb") as fh:
        while chunk := fh.read(_READ_CHUNK):
            yield chunk


def _write_new(path: str, chunks: typing.Iterable[bytes]) -> tuple[int, str]:
    """Create ``path`` (exclusive, write-only, never through a symlink), write, fsync, close.

    Size and sha256 are taken from the bytes handed to ``write``, never from the file.
    """
    digest, size = hashlib.sha256(), 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o644)
    try:
        for chunk in chunks:
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    return size, digest.hexdigest()


def _higher_version(raw: bytes) -> bool:
    """The refusal predicate (matrix A4): a JSON object whose ``format_version`` is an int above ours."""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False
    if type(obj) is not dict:
        return False
    version = obj.get("format_version")
    return type(version) is int and version > FORMAT_VERSION


def _probe_root(book: str) -> tuple[int, str]:
    """Step 0's read-only decision. Returns ``(next generation, path)`` where path is ``normal`` or
    ``repair``; raises for the refusal shapes. Never lists the book root."""
    book_st = os.lstat(book)
    if not stat.S_ISDIR(book_st.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "book directory is not a directory", book)

    manifest_path = os.path.join(book, MANIFEST)
    raw: bytes | None = None
    try:
        man_st: os.stat_result | None = os.lstat(manifest_path)
    except FileNotFoundError:
        man_st = None
    if man_st is not None:
        if stat.S_ISDIR(man_st.st_mode):
            raise BookCorrupt(f"{manifest_path} is a directory; refusing to publish over it")
        if stat.S_ISREG(man_st.st_mode):
            try:
                raw = _read_nofollow(manifest_path)
            except (OSError, ReadbackError) as exc:
                logger.warning("publish: %s cannot be read (%s); repairing", manifest_path, _describe(exc))
    if raw is not None and _higher_version(raw):
        raise BookCorrupt(f"{manifest_path} has a format_version newer than {FORMAT_VERSION}; refusing to publish")
    readable: int | None = None
    if raw is not None:
        try:
            readable = manifest_from_bytes(raw).generation
        except ManifestError:
            readable = None

    gen_root = os.path.join(book, GEN_DIR)
    try:
        gen_st: os.stat_result | None = os.lstat(gen_root)
    except FileNotFoundError:
        gen_st = None
    names: list[str] = []
    if gen_st is not None:
        if not stat.S_ISDIR(gen_st.st_mode):
            raise BookCorrupt(f"{gen_root} is not a real directory (file or symlink); refusing to publish")
        if gen_st.st_dev != book_st.st_dev:
            raise CrossDeviceError(f"{gen_root} is on a different filesystem from {book}", gen_root)
        names = os.listdir(gen_root)
    try:
        tmp_st = os.lstat(os.path.join(book, MANIFEST_TMP))
    except FileNotFoundError:
        tmp_st = None
    if tmp_st is not None and stat.S_ISDIR(tmp_st.st_mode):
        raise BookCorrupt(f"{os.path.join(book, MANIFEST_TMP)} is a directory; refusing to publish")

    canonical = [int(n) for n in names if is_canonical_gen_name(n)]
    g = max([*canonical, readable or 0, 0]) + 1
    if g > MAX_GENERATION:
        raise BookCorrupt(f"{book}: the next generation {g} would exceed 2**53; refusing to publish")
    state = classify(book, full=False)
    return g, ("repair" if state == "corrupt" else "normal")


def publish(book_dir: str | os.PathLike[str], inputs: PublishInputs, *, create: bool = False) -> int:
    """Publish ``inputs`` as a new generation of ``book_dir`` (ADR-0016 steps 0-8); return its number.

    The caller holds the EX book lock. Inputs are validated before any filesystem effect
    (:class:`PublishInputError`). ``create=True`` makes ``book_dir`` itself (never its parent).

    Step 0 refuses with no write at all on a ``manifest.json`` with a newer ``format_version`` or that is a
    directory, a ``gen`` that is a symlink or not a directory, or a next generation above ``2**53``
    (:class:`BookCorrupt`), and on a ``gen`` on another device (:class:`CrossDeviceError`). The next
    generation is ``max(canonical gen/* names, readable manifest generation) + 1``, decided before GC.
    A stat-``corrupt`` book is repaired: GC is skipped and no prior ``gen/*`` entry is touched.

    Every size and sha256 comes from the source. Before the commit ``os.replace`` any exception removes what
    this call created and propagates unchanged; after it nothing is rolled back. That includes the book
    directory itself when ``create=True`` made it (step 0, legacy preflight and GC failures too): it is
    ``rmdir``-ed, never ``rmtree``-d, and a directory that already existed is never removed.
    """
    _validate_inputs(inputs)
    book = os.fspath(book_dir)
    _crash_point("p0", "before")
    made_book = False
    if create:
        try:
            os.mkdir(book)
            made_book = True
        except FileExistsError:
            pass
    gen_root = os.path.join(book, GEN_DIR)
    tmp_path = os.path.join(book, MANIFEST_TMP)
    gen_dir = gen_root  # replaced by gen/{g} once step 0 decides g; only used when made_gen
    made_root = made_gen = made_tmp = committed = False
    try:
        g, path = _probe_root(book)
        _crash_point("p0", "after")

        _crash_point("p0.legacy", "before")
        resolve_legacy_staging(book)
        _crash_point("p0.legacy", "after")

        if path == "normal":
            if collect_garbage(book).state == "corrupt":
                raise BookCorrupt(f"{book} turned corrupt during publish GC")
        else:
            logger.warning("publish: %s is corrupt; repairing as generation %d without GC", book, g)

        gen_dir = os.path.join(gen_root, str(g))
        _crash_point("p1", "before")
        if not os.path.lexists(gen_root):
            os.mkdir(gen_root)
            made_root = True
        os.mkdir(gen_dir)
        made_gen = True
        _crash_point("p1", "after")

        _crash_point("p2", "before")
        entries, ch_size, ch_sha = write_chapters(os.path.join(gen_dir, CHAPTERS), inputs.chapters)
        written: dict[str, tuple[int, str]] = {CHAPTERS: (ch_size, ch_sha)}
        _crash_point("p2", "after")

        _crash_point("p3", "before")
        if inputs.epub is not None:
            written[EPUB] = _write_new(os.path.join(gen_dir, EPUB), _source_chunks(inputs.epub))
        if inputs.images:
            os.mkdir(os.path.join(gen_dir, IMAGES))
            for name, src in inputs.images.items():
                rel = f"{IMAGES}/{name}"
                written[rel] = _write_new(os.path.join(gen_dir, IMAGES, name), _source_chunks(src))
        if inputs.pkl is not None:
            written[PKL] = _write_new(os.path.join(gen_dir, PKL), _source_chunks(inputs.pkl))
        _crash_point("p3", "after")

        _crash_point("p4", "before")
        manifest = _build_manifest(inputs, g, entries, ch_size, ch_sha, written)
        data = manifest_to_bytes(manifest)
        manifest_from_bytes(data)  # never commit a manifest our own reader rejects
        try:
            os.unlink(tmp_path)  # a stale tmp (step 0 refused a directory one); consumed, never promoted
        except FileNotFoundError:
            pass
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o644)
        made_tmp = True
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        _crash_point("p4", "after")

        _crash_point("p5", "before")
        fd = os.open(tmp_path, os.O_WRONLY | _O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        _crash_point("p5", "after")

        _crash_point("p6", "before")
        try:
            validate_full(gen_dir, manifest)
        except (ChapterReadError, ManifestError) as exc:
            raise ReadbackError(f"generation {g} failed read-back: {exc}") from exc
        if _read_nofollow(tmp_path) != data:
            raise ReadbackError(f"{tmp_path} does not hold the manifest just written")
        _crash_point("p6", "after")

        _crash_point("p7", "before")
        if inputs.images:
            _fsync_dir(os.path.join(gen_dir, IMAGES))
        _fsync_dir(gen_dir)
        _fsync_dir(gen_root)
        _fsync_dir(book)
        if create:
            _fsync_dir(os.path.dirname(os.path.abspath(book)))
        _crash_point("p7", "after")

        _crash_point("p8", "before")
        try:
            os.replace(tmp_path, os.path.join(book, MANIFEST))
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                raise CrossDeviceError(f"commit rename crosses filesystems in {book}", tmp_path) from exc
            raise
        committed = True
        _crash_point("p8", "after")
    except BaseException:
        if not committed:
            _cleanup_uncommitted(tmp_path if made_tmp else None, gen_dir if made_gen else None,
                                 gen_root if made_root else None, book if made_book else None)
        raise

    _crash_point("p8.fsync", "before")
    _fsync_dir(book)
    _crash_point("p8.fsync", "after")
    return g


def _cleanup_uncommitted(
    tmp_path: str | None, gen_dir: str | None, gen_root: str | None, book: str | None
) -> None:
    """Best-effort removal of what an uncommitted publish created; failures are logged, never raised.

    ``book`` (the directory ``create=True`` made) is only ever ``rmdir``-ed, last: anything left inside it,
    a cleanup leftover or a file someone else put there, keeps it, and is logged rather than deleted.
    """
    if tmp_path is not None:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.error("publish cleanup: cannot remove %s: %s", tmp_path, _describe(exc))
    if gen_dir is not None:
        try:
            shutil.rmtree(gen_dir)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.error("publish cleanup: cannot remove %s: %s", gen_dir, _describe(exc))
    if gen_root is not None:
        try:
            os.rmdir(gen_root)
        except OSError as exc:
            logger.error("publish cleanup: cannot remove %s: %s", gen_root, _describe(exc))
    if book is not None:
        try:
            os.rmdir(book)
        except OSError as exc:
            logger.error("publish cleanup: cannot remove the book directory this call created %s: %s",
                         book, _describe(exc))
