"""012 WI-1.3: the validators and the three-state classifier.

``validate_stat(book_dir)`` / ``validate_full(gen_dir, manifest)`` / ``classify(book_dir, *, full)``.

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.3" (cases K-01 .. K-32).

Laws (policy-core):
- purity and idempotence: classifying never changes the tree, and repeated calls agree (K-26, S5);
- monotone strictness: full ``valid`` implies stat ``valid`` (K-26, S4);
- metamorphic insensitivity to user data, stray files, sibling staging, tmp, non-current canonical
  gens and non-canonical gen names (K-27, S6);
- version ceiling: ``format_version > FORMAT_VERSION`` is ``corrupt``, never ``valid`` (K-10).

Symlinks are never followed: a symlinked ``manifest.json`` / ``gen`` / ``gen/{g}`` / ``images`` / artifact
is ``corrupt`` even when everything it points at is byte-identical (F-04, F-05, A10).

Not covered here, by design: the ``collect_garbage`` clauses of K-31/K-32 belong to WI-1.5 (GC is not
implemented yet); K-07 is the full publisher *layout* built by hand because ``publish`` is WI-1.6.
Update (WI-1.5): those GC clauses are now appended to K-31/K-32, in both GC modes (recovery,
``min_manifest_age_s=None``; sweep, ``RETAIN_S``), plus a variant of each with an orphan gen and a tmp.
"""
from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from book_format_helpers import EXTRACTOR_VERSION, FINGERPRINT
from reader3_app.book_format import (
    CHAPTERS,
    EPUB,
    FORMAT_VERSION,
    GEN_DIR,
    IMAGES,
    MANIFEST,
    MANIFEST_TMP,
    PKL,
    RETAIN_S,
    ArtifactEntry,
    BookFormatError,
    BookManifest,
    ChapterRecord,
    ManifestMetadata,
    ManifestTocEntry,
    ReadbackError,
    classify,
    collect_garbage,
    manifest_from_bytes,
    manifest_to_bytes,
    validate_full,
    validate_stat,
    write_chapters,
)


def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- builders

IMAGE_FILES: dict[str, bytes] = {"cover.png": b"PNG-cover\x00\xff", "图.jpg": b"JPG-\xe5\x9b\xbe-bytes"}
USER_DATA: dict[str, bytes] = {
    "notes.json": b"[]",
    "notes.json.lock": b"",
    "ai_meta.json": b'{"book_uuid": "u"}',
    "ai_conversations/c1.json": b"{}",
    "chroma_db/index_meta.json": b"{}",
    "chroma_db/x.bin": b"\x00\x01",
}


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_gen(gen_dir: Path, g: int, *, tag: str = "v1", images: bool = True, pkl: bool = True) -> BookManifest:
    """Write a complete generation directory and return the manifest describing it (not written to disk)."""
    gen_dir.mkdir(parents=True)
    chapters = [
        ChapterRecord(
            id=f"c{i}",
            href=f"Text/c{i}.xhtml",
            title=f"第{i}章",
            content=f"<p>{tag} 第一章 café 🜁 line\n{i}</p>",
            text=f"{tag} 第一章 café 🜁 line\n{i}",
            order=i,
        )
        for i in range(3)
    ]
    entries, size, sha = write_chapters(gen_dir / CHAPTERS, chapters)
    files: dict[str, bytes] = {EPUB: b"EPUB-" + tag.encode()}
    if pkl:
        files[PKL] = b"PKL-" + tag.encode()
    if images:
        for name, data in IMAGE_FILES.items():
            files[f"{IMAGES}/{name}"] = data + tag.encode()
    for rel, data in files.items():
        _write(gen_dir / rel, data)
    artifacts = [ArtifactEntry(path=CHAPTERS, size_bytes=size, sha256=sha)]
    artifacts += [ArtifactEntry(path=rel, size_bytes=len(data), sha256=_sha(data)) for rel, data in files.items()]
    return BookManifest(
        format_version=FORMAT_VERSION,
        generation=g,
        metadata=ManifestMetadata(
            title="Dracula 第一",
            language="en",
            authors=("Bram Stoker",),
            description=None,
            publisher=None,
            date=None,
            identifiers=(),
            subjects=(),
        ),
        toc=(ManifestTocEntry(title="One", href="Text/c0.xhtml", file_href="Text/c0.xhtml", anchor="", children=()),),
        images={f"{IMAGES}/{n}": (f"OEBPS/{n}",) for n in IMAGE_FILES} if images else {},
        source_file="dracula.epub",
        processed_at="2026-10-08T00:00:00+00:00",
        book_version="1",
        chapters=entries,
        chapters_size_bytes=size,
        chapters_sha256=sha,
        artifacts=tuple(sorted(artifacts, key=lambda a: a.path)),
        book_fingerprint=FINGERPRINT,
        extractor_version=EXTRACTOR_VERSION,
    )


def build_valid(book_dir: Path, *, g: int = 1, images: bool = True, pkl: bool = True) -> BookManifest:
    """The publisher's layout: ``gen/{g}/`` complete, then ``manifest.json`` last."""
    book_dir.mkdir(parents=True, exist_ok=True)
    m = write_gen(book_dir / GEN_DIR / str(g), g, images=images, pkl=pkl)
    (book_dir / MANIFEST).write_bytes(manifest_to_bytes(m))
    return m


def build_by_hand(book_dir: Path) -> None:
    """A valid book written with plain ``json`` and no ``book_format`` writer: g=7, no pkl, no images."""
    gen = book_dir / GEN_DIR / "7"
    gen.mkdir(parents=True)
    lines = [
        json.dumps({"id": i, "href": f"{i}.html", "title": i, "content": f"<p>{i}</p>", "text": i, "order": n},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
        for n, i in enumerate(["前言", "one"])
    ]
    body = b"".join(line + b"\n" for line in lines)
    (gen / CHAPTERS).write_bytes(body)
    (gen / EPUB).write_bytes(b"hand-epub")
    chapters, offset = [], 0
    for n, line in enumerate(lines):
        cid = json.loads(line)["id"]
        chapters.append({"id": cid, "href": f"{cid}.html", "order": n, "offset_bytes": offset,
                         "length_bytes": len(line), "sha256": _sha(line)})
        offset += len(line) + 1
    doc = {
        "format_version": 1,
        "generation": 7,
        "metadata": {"title": "T", "language": "zh", "authors": [], "description": None, "publisher": None,
                     "date": None, "identifiers": [], "subjects": []},
        "toc": [],
        "images": {},
        "source_file": "t.epub",
        "processed_at": "x",
        "book_version": "1",
        "chapters": chapters,
        "chapters_size_bytes": len(body),
        "chapters_sha256": _sha(body),
        "artifacts": [
            {"path": CHAPTERS, "size_bytes": len(body), "sha256": _sha(body)},
            {"path": EPUB, "size_bytes": 9, "sha256": _sha(b"hand-epub")},
        ],
        "book_fingerprint": FINGERPRINT,
        "extractor_version": EXTRACTOR_VERSION,
    }
    (book_dir / MANIFEST).write_text(json.dumps(doc), encoding="utf-8")


def add_user_data(book_dir: Path) -> None:
    for rel, data in USER_DATA.items():
        _write(book_dir / rel, data)


def flip_byte(path: Path, index: int = 0) -> None:
    data = bytearray(path.read_bytes())
    data[index % len(data)] ^= 0x01
    path.write_bytes(bytes(data))


def rewrite_manifest(book_dir: Path, **changes: Any) -> None:
    doc = json.loads((book_dir / MANIFEST).read_bytes())
    doc.update(changes)
    (book_dir / MANIFEST).write_text(json.dumps(doc), encoding="utf-8")


def tree(root: Path) -> dict[str, tuple[Any, ...]]:
    """``lstat``-based snapshot including ``root`` itself; never follows a link (dangling ones included)."""
    out: dict[str, tuple[Any, ...]] = {}
    if not os.path.lexists(root):
        return out

    def one(full: str, rel: str) -> None:
        st_ = os.lstat(full)
        if stat.S_ISLNK(st_.st_mode):
            out[rel] = ("link", os.readlink(full), st_.st_mtime_ns, st_.st_ino)
        elif stat.S_ISDIR(st_.st_mode):
            out[rel + "/"] = ("dir", st_.st_mtime_ns, st_.st_ino)
        else:
            with open(full, "rb") as fh:
                out[rel] = ("file", _sha(fh.read()), st_.st_size, st_.st_mtime_ns, st_.st_ino)

    one(str(root), ".")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            one(full, os.path.relpath(full, root))
    return out


def both(book_dir: Path) -> tuple[str, str]:
    return classify(book_dir, full=False), classify(book_dir, full=True)


# --------------------------------------------------------------------------- K-01 .. K-24 table


def _k01(base: Path) -> Path:
    return base / "absent_data"


def _k02(base: Path) -> Path:
    d = base / "b_data"
    d.mkdir(parents=True)
    return d


def _k03(base: Path) -> Path:
    d = _k02(base)
    add_user_data(d)
    return d


def _k04(base: Path) -> Path:
    d = _k03(base)
    _write(d / PKL, b"legacy-pkl")
    _write(d / EPUB, b"legacy-epub")
    _write(d / IMAGES / "a.png", b"legacy-png")
    return d


def _k05(base: Path) -> Path:
    d = base / "b_data"
    build_valid(d)
    os.replace(d / MANIFEST, d / MANIFEST_TMP)
    return d


def _k06(base: Path) -> Path:
    d = base / "b_data"
    build_valid(d)
    (d / MANIFEST).unlink()
    return d


def _k07(base: Path) -> Path:
    d = base / "b_data"
    build_valid(d)
    add_user_data(d)
    return d


def _k08(base: Path) -> Path:
    d = base / "b_data"
    d.mkdir(parents=True)
    build_by_hand(d)
    return d


def _k09(base: Path) -> Path:
    d = _k07(base)
    data = (d / MANIFEST).read_bytes()
    (d / MANIFEST).write_bytes(data[: len(data) // 2])
    return d


def _k10(base: Path) -> Path:
    d = _k07(base)
    rewrite_manifest(d, format_version=FORMAT_VERSION + 1)
    return d


def _k11(base: Path) -> Path:
    d = _k07(base)
    rewrite_manifest(d, generation="1")
    return d


def _k12(base: Path) -> Path:
    d = _k07(base)
    shutil.rmtree(d / GEN_DIR / "1")
    return d


def _k13(base: Path) -> Path:
    d = _k12(base)
    (d / GEN_DIR / "1").write_bytes(b"not a dir")
    return d


def _k14(base: Path) -> Path:
    d = _k07(base)
    outside = base / "outside"
    outside.mkdir()
    os.replace(d / GEN_DIR / "1", outside / "gen1_copy")
    os.symlink(outside / "gen1_copy", d / GEN_DIR / "1")
    return d


def _k15(base: Path) -> Path:
    d = _k07(base)
    (d / GEN_DIR / "1" / EPUB).unlink()
    return d


def _k16(base: Path) -> Path:
    d = _k07(base)
    with open(d / GEN_DIR / "1" / IMAGES / "cover.png", "ab") as fh:
        fh.write(b"+")
    return d


def _k17(base: Path) -> Path:
    d = _k07(base)
    flip_byte(d / GEN_DIR / "1" / CHAPTERS, 5)
    return d


def _k18(base: Path) -> Path:
    d = _k07(base)
    flip_byte(d / GEN_DIR / "1" / EPUB, 2)
    return d


def _k19(base: Path) -> Path:
    d = _k07(base)
    _write(d / GEN_DIR / "1" / IMAGES / "extra.png", b"extra")
    return d


def _k20(base: Path) -> Path:
    d = _k07(base)
    (d / MANIFEST).unlink()
    (d / MANIFEST).mkdir()
    return d


def _k21(base: Path) -> Path:
    d = _k07(base)
    (d / GEN_DIR / "1" / EPUB).unlink()
    (d / GEN_DIR / "1" / EPUB).mkdir()
    return d


def _k23(base: Path) -> Path:
    d = _k07(base)
    (d / MANIFEST).unlink()
    os.symlink(base / "nowhere.json", d / MANIFEST)
    return d


def _k23b(base: Path) -> Path:
    d = _k07(base)
    outside = base / "outside"
    outside.mkdir()
    os.replace(d / MANIFEST, outside / MANIFEST)
    os.symlink(outside / MANIFEST, d / MANIFEST)
    return d


def _k24(base: Path) -> Path:
    d = base / "b_data"
    _write(d, b"a file, not a book dir")
    return d


MISSING, CORRUPT, VALID = "missing", "corrupt", "valid"

TABLE: list[tuple[str, Callable[[Path], Path], tuple[str, str]]] = [
    ("K-01 absent", _k01, (MISSING, MISSING)),
    ("K-02 empty", _k02, (MISSING, MISSING)),
    ("K-03 user-data only", _k03, (MISSING, MISSING)),
    ("K-04 flat legacy", _k04, (MISSING, MISSING)),
    ("K-05 tmp only", _k05, (MISSING, MISSING)),
    ("K-06 gen only", _k06, (MISSING, MISSING)),
    ("K-07 valid publisher layout", _k07, (VALID, VALID)),
    ("K-08 valid hand-built", _k08, (VALID, VALID)),
    ("K-09 manifest truncated", _k09, (CORRUPT, CORRUPT)),
    ("K-10 format_version+1", _k10, (CORRUPT, CORRUPT)),
    ("K-11 generation str", _k11, (CORRUPT, CORRUPT)),
    ("K-12 gen/g missing", _k12, (CORRUPT, CORRUPT)),
    ("K-13 gen/g regular file", _k13, (CORRUPT, CORRUPT)),
    ("K-14 gen/g symlink", _k14, (CORRUPT, CORRUPT)),
    ("K-15 artifact missing", _k15, (CORRUPT, CORRUPT)),
    ("K-16 image size+1", _k16, (CORRUPT, CORRUPT)),
    ("K-17 chapters same-size flip", _k17, (VALID, CORRUPT)),
    ("K-18 epub same-size flip", _k18, (VALID, CORRUPT)),
    ("K-19 extra image", _k19, (VALID, CORRUPT)),
    ("K-20 manifest is a dir", _k20, (CORRUPT, CORRUPT)),
    ("K-21 artifact is a dir", _k21, (CORRUPT, CORRUPT)),
    ("K-23 manifest dangling symlink", _k23, (CORRUPT, CORRUPT)),
    ("K-23b manifest symlink to valid", _k23b, (CORRUPT, CORRUPT)),
    ("K-24 book_dir is a file", _k24, (MISSING, MISSING)),
]


@pytest.mark.parametrize(("make", "expected"), [(m, e) for _, m, e in TABLE], ids=[i for i, _, _ in TABLE])
def test_directory_state_table(tmp_path: Path, make: Callable[[Path], Path], expected: tuple[str, str]) -> None:
    book = make(tmp_path)
    before = tree(tmp_path)
    assert both(book) == expected
    assert tree(tmp_path) == before, "classify must not create, delete or modify anything"


@pytest.mark.parametrize("bump", [1, 2, 1000])
def test_any_higher_format_version_is_corrupt_never_valid(tmp_path: Path, bump: int) -> None:
    d = _k07(tmp_path)
    rewrite_manifest(d, format_version=FORMAT_VERSION + bump)
    assert both(d) == (CORRUPT, CORRUPT)


ARTIFACT_KINDS = [CHAPTERS, EPUB, PKL, f"{IMAGES}/cover.png", f"{IMAGES}/图.jpg"]


@pytest.mark.parametrize("rel", ARTIFACT_KINDS)
def test_k22_artifact_symlinked_to_identical_file_is_corrupt(tmp_path: Path, rel: str) -> None:
    d = _k07(tmp_path)
    target = d / GEN_DIR / "1" / rel
    outside = tmp_path / "outside"
    outside.mkdir()
    copy = outside / Path(rel).name
    os.replace(target, copy)
    os.symlink(copy, target)
    assert target.read_bytes() == copy.read_bytes()  # the link resolves to identical bytes
    before = tree(tmp_path)
    assert both(d) == (CORRUPT, CORRUPT)
    assert tree(tmp_path) == before


def test_k17_k18_stat_returns_manifest_while_full_raises(tmp_path: Path) -> None:
    for name, make in (("k17", _k17), ("k18", _k18)):
        d = make(tmp_path / name)
        m = validate_stat(d)
        assert m == manifest_from_bytes((d / MANIFEST).read_bytes())
        with pytest.raises(BookFormatError):
            validate_full(d / GEN_DIR / str(m.generation), m)


# --------------------------------------------------------------------------- K-25


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes")
def test_k25_permission_denied_manifest_is_corrupt_not_missing(tmp_path: Path) -> None:
    d = _k07(tmp_path)
    os.chmod(d / MANIFEST, 0)
    try:
        assert both(d) == (CORRUPT, CORRUPT)
    finally:
        os.chmod(d / MANIFEST, 0o644)


# --------------------------------------------------------------------------- K-26 purity / idempotence / monotone

MUTATIONS = ["delete", "truncate", "flip", "append", "extra_image", "stray", "manifest_flip", "manifest_delete",
             "tmp"]


def _gen_files(gen: Path) -> list[Path]:
    return sorted(p for p in gen.rglob("*") if p.is_file() and not p.is_symlink())


def _mutate(d: Path, op: str, pick: int, amount: int) -> None:
    gen = d / GEN_DIR / "1"
    files = _gen_files(gen) if gen.is_dir() else []
    target = files[pick % len(files)] if files else None
    if op == "delete" and target is not None:
        target.unlink()
    elif op == "truncate" and target is not None:
        size = target.stat().st_size
        with open(target, "r+b") as fh:
            fh.truncate(amount % (size + 1))
    elif op == "flip" and target is not None and target.stat().st_size:
        flip_byte(target, amount)
    elif op == "append" and target is not None:
        with open(target, "ab") as fh:
            fh.write(b"x" * (1 + amount % 3))
    elif op == "extra_image" and gen.is_dir():
        _write(gen / IMAGES / f"extra{amount}.png", b"extra")
    elif op == "stray":
        _write(d / f"stray{amount}.txt", b"stray")
    elif op == "manifest_flip" and (d / MANIFEST).is_file():
        flip_byte(d / MANIFEST, amount)
    elif op == "manifest_delete" and (d / MANIFEST).exists():
        (d / MANIFEST).unlink()
    elif op == "tmp":
        _write(d / MANIFEST_TMP, b'{"format_version": 1}')


@props(80)
@given(
    muts=st.lists(
        st.tuples(st.sampled_from(MUTATIONS), st.integers(0, 50), st.integers(0, 10_000)), min_size=1, max_size=4
    )
)
def test_k26_purity_idempotence_and_monotone_strictness(muts: list[tuple[str, int, int]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "b_data"
        build_valid(d)
        for op, pick, amount in muts:
            _mutate(d, op, pick, amount)
        before = tree(Path(tmp))
        results = [classify(d, full=False), classify(d, full=True), classify(d, full=False), classify(d, full=True)]
        assert tree(Path(tmp)) == before
        assert set(results) <= {MISSING, CORRUPT, VALID}
        assert results[0] == results[2] and results[1] == results[3]
        if results[1] == VALID:
            assert results[0] == VALID
        if not os.path.lexists(d / MANIFEST):
            assert results[:2] == [MISSING, MISSING]


# --------------------------------------------------------------------------- K-27 metamorphic

BASES: dict[str, Callable[[Path], Path]] = {"K-07": _k07, "K-10": _k10, "K-15": _k15, "K-17": _k17, "K-03": _k03}
EXTRAS = ["user", "stray", "tmp", "junk_gen", "valid_gen", "noncanonical", "sibling_staging"]


def _add_extra(base: Path, d: Path, kind: str) -> None:
    if kind == "user":
        add_user_data(d)
    elif kind == "stray":
        _write(d / "README.txt", b"stray")
    elif kind == "tmp":
        _write(d / MANIFEST_TMP, b"half a manif")
    elif kind == "junk_gen":
        _write(d / GEN_DIR / "9" / "junk.bin", b"junk")
    elif kind == "valid_gen":
        write_gen(d / GEN_DIR / "5", 5, tag="other")
    elif kind == "noncanonical":
        for name in ("01", "abc", "1.tmp", "0"):
            _write(d / GEN_DIR / name / CHAPTERS, b"nope")
    elif kind == "sibling_staging":
        _write(base / f"{d.name}.staging-4242" / EPUB, b"debris")


@props(60)
@given(base=st.sampled_from(sorted(BASES)), extras=st.sets(st.sampled_from(EXTRAS), min_size=1))
def test_k27_debris_and_user_data_never_change_the_classification(base: str, extras: set[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pristine = BASES[base](Path(tmp) / "pristine")
        expected = both(pristine)
        root = Path(tmp) / "decorated"
        d = BASES[base](root)
        for kind in sorted(extras):
            _add_extra(root, d, kind)
        assert both(d) == expected


def test_k27_pristine_bases_have_the_table_states(tmp_path: Path) -> None:
    """Anchor for K-27: its oracle is not vacuous (the five bases span all three states)."""
    states = {name: both(make(tmp_path / name)) for name, make in BASES.items()}
    assert states == {
        "K-07": (VALID, VALID),
        "K-10": (CORRUPT, CORRUPT),
        "K-15": (CORRUPT, CORRUPT),
        "K-17": (VALID, CORRUPT),
        "K-03": (MISSING, MISSING),
    }


# --------------------------------------------------------------------------- K-28 stat never opens gen files


def _record_opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def rec_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(os.fspath(file) if not isinstance(file, int) else f"<fd {file}>")
        return real_open(file, *args, **kwargs)

    def rec_io_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(os.fspath(file) if not isinstance(file, int) else f"<fd {file}>")
        return real_io_open(file, *args, **kwargs)

    def rec_os_open(path: Any, *args: Any, **kwargs: Any) -> int:
        seen.append(os.fspath(path))
        return real_os_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", rec_open)
    monkeypatch.setattr(io, "open", rec_io_open)
    monkeypatch.setattr(os, "open", rec_os_open)
    return seen


def test_k28_stat_mode_opens_only_the_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _k07(tmp_path)
    seen = _record_opens(monkeypatch)
    result = classify(d, full=False)
    monkeypatch.undo()
    assert result == VALID
    resolved = {os.path.realpath(p) for p in seen}
    assert resolved == {os.path.realpath(d / MANIFEST)}
    assert not any(GEN_DIR in Path(os.path.relpath(p, os.path.realpath(d))).parts for p in resolved)


def test_k28_control_full_mode_does_open_chapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _k07(tmp_path)
    seen = _record_opens(monkeypatch)
    result = classify(d, full=True)
    monkeypatch.undo()
    assert result == VALID
    assert os.path.realpath(d / GEN_DIR / "1" / CHAPTERS) in {os.path.realpath(p) for p in seen}


# --------------------------------------------------------------------------- K-29 / K-30 validators


def test_k29_validate_stat_returns_the_parsed_manifest_and_full_accepts(tmp_path: Path) -> None:
    d = tmp_path / "b_data"
    m = build_valid(d)
    got = validate_stat(d)
    assert got == m
    assert got == manifest_from_bytes((d / MANIFEST).read_bytes())
    assert validate_full(d / GEN_DIR / str(got.generation), got) is None


def test_k29_validate_stat_accepts_the_hand_built_book(tmp_path: Path) -> None:
    d = _k08(tmp_path)
    m = validate_stat(d)
    assert (m.generation, [a.path for a in m.artifacts]) == (7, [CHAPTERS, EPUB])
    validate_full(d / GEN_DIR / "7", m)


def test_k30_validate_full_against_an_unwritten_manifest(tmp_path: Path) -> None:
    d = tmp_path / "b_data"
    gen = d / GEN_DIR / "5"
    m = write_gen(gen, 5)
    assert not (d / MANIFEST).exists()
    validate_full(gen, m)  # publisher step 6: passes as built
    assert classify(d, full=True) == MISSING  # an unwritten manifest is still no book

    _write(gen / IMAGES / "extra.png", b"extra")
    with pytest.raises(ReadbackError):
        validate_full(gen, m)
    (gen / IMAGES / "extra.png").unlink()
    validate_full(gen, m)

    (gen / PKL).unlink()
    with pytest.raises(ReadbackError):
        validate_full(gen, m)


def test_validate_stat_on_corrupt_gen_raises_a_format_error(tmp_path: Path) -> None:
    for name, make in (("k12", _k12), ("k15", _k15), ("k16", _k16), ("k14", _k14)):
        d = make(tmp_path / name)
        with pytest.raises(BookFormatError):
            validate_stat(d)


# --------------------------------------------------------------------------- K-31 / K-32


def test_k31_gen_symlinked_to_a_valid_outside_copy_is_corrupt(tmp_path: Path) -> None:
    d = _k07(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.replace(d / GEN_DIR, outside / "gen_copy")
    os.symlink(outside / "gen_copy", d / GEN_DIR)
    assert (d / GEN_DIR / "1" / EPUB).is_file()  # every artifact still resolves through the link
    before = tree(tmp_path)
    assert both(d) == (CORRUPT, CORRUPT)
    assert tree(tmp_path) == before
    assert_gc_deletes_nothing(d, tmp_path, before)


def test_k32_images_dir_symlinked_is_corrupt(tmp_path: Path) -> None:
    d = _k07(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.replace(d / GEN_DIR / "1" / IMAGES, outside / "images_copy")
    os.symlink(outside / "images_copy", d / GEN_DIR / "1" / IMAGES)
    assert (d / GEN_DIR / "1" / IMAGES / "cover.png").is_file()
    before = tree(tmp_path)
    assert both(d) == (CORRUPT, CORRUPT)
    assert tree(tmp_path) == before
    assert_gc_deletes_nothing(d, tmp_path, before)



def assert_gc_deletes_nothing(d: Path, root: Path, before: dict[str, tuple[Any, ...]]) -> None:
    """WI-1.5 GC clause of K-31/K-32: recovery and sweep mode both report corrupt and delete nothing."""
    for kwargs in ({"min_manifest_age_s": None}, {"min_manifest_age_s": RETAIN_S, "now": 4_000_000_000.0}):
        result = collect_garbage(d, **kwargs)
        assert (result.state, result.deleted) == ("corrupt", ()), kwargs
        assert tree(root) == before, kwargs


def test_k31_gc_with_orphan_and_tmp_deletes_nothing(tmp_path: Path) -> None:
    d = _k07(tmp_path)
    (d / GEN_DIR / "9").mkdir()
    (d / GEN_DIR / "9" / CHAPTERS).write_bytes(b"orphan")
    (d / MANIFEST_TMP).write_bytes(b"tmp")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.replace(d / GEN_DIR, outside / "gen_copy")
    os.symlink(outside / "gen_copy", d / GEN_DIR)
    before = tree(tmp_path)
    assert_gc_deletes_nothing(d, tmp_path, before)


def test_k32_gc_with_orphan_and_tmp_deletes_nothing(tmp_path: Path) -> None:
    d = _k07(tmp_path)
    (d / GEN_DIR / "9").mkdir()
    (d / GEN_DIR / "9" / CHAPTERS).write_bytes(b"orphan")
    (d / MANIFEST_TMP).write_bytes(b"tmp")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.replace(d / GEN_DIR / "1" / IMAGES, outside / "images_copy")
    os.symlink(outside / "images_copy", d / GEN_DIR / "1" / IMAGES)
    before = tree(tmp_path)
    assert_gc_deletes_nothing(d, tmp_path, before)


# ---------------------------------------------------------- WI-1.10 B5: an unsearchable book dir


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores mode bits")
def test_wi110_b5_classify_on_unsearchable_book_dir_is_corrupt(tmp_path: Path) -> None:
    """B5 (failure, S3, Level 1): the manifest cannot be lstat'ed (EACCES): corrupt in both modes, never missing."""
    book = tmp_path / "x_data"
    build_valid(book)
    assert both(book) == ("valid", "valid")
    os.chmod(book, 0o600)
    try:
        states = (classify(book, full=False), classify(book, full=True))
    finally:
        os.chmod(book, 0o755)
    assert states == ("corrupt", "corrupt")
    assert both(book) == ("valid", "valid")
