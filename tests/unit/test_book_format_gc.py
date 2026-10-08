"""012 WI-1.5: safe GC and recovery, ``collect_garbage(book_dir, *, min_manifest_age_s=None, now=None)``.

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.5" (cases G-01 .. G-13).

Laws (policy-core):
- conservation: every root entry other than ``gen/`` and ``manifest.json.tmp`` is byte-, inode- and
  mtime_ns-identical after GC, and so is the current generation of a valid book (G-04, S5);
- zero deletion on corrupt, a symlinked or non-directory ``gen`` included (G-02, G-07, G-08, S3);
- idempotence (F-02): the tree after a second run equals the tree after the first, and the second
  ``GcResult.deleted == ()`` (G-05, S5);
- postcondition: a valid book old enough to sweep keeps exactly ``{current}`` canonical gens and no tmp;
  GC never creates a manifest, so a valid-looking tmp is never rolled forward (G-04, G-10b).

"Canonical" is exactly ``re.fullmatch(r"[1-9][0-9]*", name, flags=re.ASCII)`` on the ``str`` entry name
(adversary round 2, B4), the predicate the publisher (WI-1.6) shares for its ``g`` computation.

Fixtures are the publisher's *layout* built by hand, because ``publish`` is WI-1.6. Repoint them at
``publish`` there: ``build_book`` (G-01/G-02/G-06/G-06b/G-09/G-12/G-13 bases) and the generator's
``valid`` base. G-12b's publish-branch half (S0u, S1, S3, S4, S5, R-unparse) belongs to WI-1.6.

G-12b listing journal (pinned): ``os.listdir``, ``os.scandir``, ``os.walk``, ``glob.glob``, ``glob.iglob``,
``pathlib.Path.iterdir``, ``pathlib.Path.glob``, ``pathlib.Path.rglob``. Every argument (a path, a
``PathLike``, a relative path, or an int fd via ``os.fstat``) is resolved at call time to ``(st_dev, st_ino)``.
"""
from __future__ import annotations

import dataclasses
import glob
import hashlib
import logging
import os
import pathlib
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

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
    BookManifest,
    ChapterRecord,
    GcResult,
    ManifestMetadata,
    ManifestTocEntry,
    classify,
    collect_garbage,
    is_canonical_gen_name,
    manifest_to_bytes,
    validate_full,
    write_chapters,
)

LOGGER = "reader3_app.book_format"
NOW = 1_800_000_000.0
NOW_NS = 1_800_000_000 * 10**9
CANON_RE = r"[1-9][0-9]*"


def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def oracle_canonical(name: str) -> bool:
    return re.fullmatch(CANON_RE, name, flags=re.ASCII) is not None


# --------------------------------------------------------------------------- builders (publisher layout by hand)

USER_DATA: dict[str, bytes] = {
    "notes.json": b"[]",
    "notes.json.lock": b"",
    "ai_meta.json": b'{"book_uuid": "u"}',
    "ai_conversations/c1.json": b"{}",
    "chroma_db/index_meta.json": b"{}",
    "chroma_db/x.bin": b"\x00\x01",
}
LEGACY_FLAT: dict[str, bytes] = {PKL: b"legacy-pkl", EPUB: b"legacy-epub", "images/a.png": b"legacy-png"}
STRAY: dict[str, bytes] = {"README.txt": b"stray user file"}
NONCANON_NAMES = ("01", "tmp", ".DS_Store", "-3", "2a", "７", "400\n", "0", "+4", " 5")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_gen(gen_dir: Path, g: int, *, tag: str = "v1") -> BookManifest:
    """A complete generation directory (chapters, epub, pkl, two images); returns its manifest (not written)."""
    gen_dir.mkdir(parents=True)
    chapters = [
        ChapterRecord(
            id=f"c{i}", href=f"Text/c{i}.xhtml", title=f"第{i}章",
            content=f"<p>{tag} 第一章 café 🜁 line\n{i}</p>", text=f"{tag} 第一章 café 🜁 line\n{i}", order=i,
        )
        for i in range(3)
    ]
    entries, size, sha = write_chapters(gen_dir / CHAPTERS, chapters)
    files = {EPUB: b"EPUB-" + tag.encode(), PKL: b"PKL-" + tag.encode(), f"{IMAGES}/cover.png": b"PNG-" + tag.encode(),
             f"{IMAGES}/图.jpg": b"JPG-" + tag.encode()}
    for rel, data in files.items():
        _write(gen_dir / rel, data)
    artifacts = [ArtifactEntry(path=CHAPTERS, size_bytes=size, sha256=sha)]
    artifacts += [ArtifactEntry(path=rel, size_bytes=len(data), sha256=_sha(data)) for rel, data in files.items()]
    return BookManifest(
        format_version=FORMAT_VERSION,
        generation=g,
        metadata=ManifestMetadata(title="Dracula 第一", language="en", authors=("Bram Stoker",), description=None,
                                  publisher=None, date=None, identifiers=(), subjects=()),
        toc=(ManifestTocEntry(title="One", href="Text/c0.xhtml", file_href="Text/c0.xhtml", anchor="", children=()),),
        images={f"{IMAGES}/cover.png": ("OEBPS/cover.png",), f"{IMAGES}/图.jpg": ("OEBPS/图.jpg",)},
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


def add_files(book: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        _write(book / rel, data)


def add_orphan(book: Path, n: int | str) -> None:
    """A partial generation a killed publish leaves behind."""
    _write(book / GEN_DIR / str(n) / CHAPTERS, b"partial junk " + str(n).encode())


def build_book(
    book: Path, *, current: int = 2, previous: tuple[int, ...] = (1,), orphans: tuple[int, ...] = (3,),
    tmp: bool = True, user: bool = True, stray: bool = True, legacy: bool = False,
) -> BookManifest:
    """A valid book in the publisher's layout: complete ``gen/{current}``, manifest last."""
    book.mkdir(parents=True, exist_ok=True)
    for g in previous:
        write_gen(book / GEN_DIR / str(g), g, tag=f"v{g}")
    m = write_gen(book / GEN_DIR / str(current), current, tag=f"v{current}")
    for n in orphans:
        add_orphan(book, n)
    if tmp:
        (book / MANIFEST_TMP).write_bytes(b'{"half": "written')
    if user:
        add_files(book, USER_DATA)
    if stray:
        add_files(book, STRAY)
    if legacy:
        add_files(book, LEGACY_FLAT)
    (book / MANIFEST).write_bytes(manifest_to_bytes(m))
    return m


def rewrite_manifest(book: Path, raw: bytes) -> None:
    (book / MANIFEST).write_bytes(raw)


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


def sub(snap: dict[str, tuple[Any, ...]], prefix: str) -> dict[str, tuple[Any, ...]]:
    """The entries of ``snap`` at or under ``prefix`` (a relative path, no trailing slash)."""
    return {k: v for k, v in snap.items() if k in (prefix, prefix + "/") or k.startswith(prefix + "/")}


def error_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno >= logging.ERROR]


# --------------------------------------------------------------------------- corruptions (G-02)


def _move_out(src: Path, outside: Path) -> Path:
    outside.mkdir(parents=True, exist_ok=True)
    dst = outside / (src.name + "_moved")
    os.replace(src, dst)
    return dst


def c_unparseable(book: Path, outside: Path) -> None:
    rewrite_manifest(book, b'{"format_version": 1, ')


def c_version(book: Path, outside: Path) -> None:
    newer = f'"format_version": {FORMAT_VERSION + 1}'.encode()
    raw = (book / MANIFEST).read_bytes().replace(b'"format_version": 1', newer)
    rewrite_manifest(book, raw)


def c_generation_str(book: Path, outside: Path) -> None:
    rewrite_manifest(book, (book / MANIFEST).read_bytes().replace(b'"generation": 2', b'"generation": "2"'))


def c_gen_g_missing(book: Path, outside: Path) -> None:
    shutil.rmtree(book / GEN_DIR / "2")


def c_gen_g_file(book: Path, outside: Path) -> None:
    shutil.rmtree(book / GEN_DIR / "2")
    (book / GEN_DIR / "2").write_bytes(b"not a dir")


def c_gen_g_symlink(book: Path, outside: Path) -> None:
    os.symlink(_move_out(book / GEN_DIR / "2", outside), book / GEN_DIR / "2")


def c_artifact_missing(book: Path, outside: Path) -> None:
    (book / GEN_DIR / "2" / EPUB).unlink()


def c_artifact_size(book: Path, outside: Path) -> None:
    with open(book / GEN_DIR / "2" / EPUB, "ab") as fh:
        fh.write(b"+")


def c_artifact_symlink(book: Path, outside: Path) -> None:
    os.symlink(_move_out(book / GEN_DIR / "2" / EPUB, outside), book / GEN_DIR / "2" / EPUB)


def c_manifest_dir(book: Path, outside: Path) -> None:
    (book / MANIFEST).unlink()
    _write(book / MANIFEST / "inner.txt", b"x")


def c_manifest_dangling(book: Path, outside: Path) -> None:
    (book / MANIFEST).unlink()
    os.symlink(outside / "nowhere.json", book / MANIFEST)


def c_gen_symlink(book: Path, outside: Path) -> None:
    os.symlink(_move_out(book / GEN_DIR, outside), book / GEN_DIR)


def c_gen_file(book: Path, outside: Path) -> None:
    shutil.rmtree(book / GEN_DIR)
    (book / GEN_DIR).write_bytes(b"gen is a file")


CORRUPTIONS: dict[str, tuple[Callable[[Path, Path], None], str]] = {
    # kind: (mutation, a substring the ERROR log must carry to name the failed check)
    "unparseable": (c_unparseable, "not JSON"),
    "version_plus_1": (c_version, "format_version"),
    "generation_str": (c_generation_str, "generation"),
    "gen_g_missing": (c_gen_g_missing, "gen/2/"),
    "gen_g_file": (c_gen_g_file, "gen/2/"),
    "gen_g_symlink": (c_gen_g_symlink, "gen/2/"),
    "artifact_missing": (c_artifact_missing, EPUB),
    "artifact_size": (c_artifact_size, EPUB),
    "artifact_symlink": (c_artifact_symlink, EPUB),
    "manifest_dir": (c_manifest_dir, MANIFEST),
    "manifest_dangling": (c_manifest_dangling, MANIFEST),
    "gen_symlink": (c_gen_symlink, "gen/ is not a real directory"),
    "gen_file": (c_gen_file, "gen/ is not a real directory"),
}


# --------------------------------------------------------------------------- GcResult and the canonical predicate


def test_gc_result_is_a_frozen_dataclass_with_the_pinned_fields() -> None:
    r = GcResult("valid", ("gen/1",), ())
    assert [f.name for f in dataclasses.fields(GcResult)] == ["state", "deleted", "skipped"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.state = "corrupt"  # type: ignore[misc]
    assert r == GcResult(state="valid", deleted=("gen/1",), skipped=())


@pytest.mark.parametrize(
    "name, expected",
    [("1", True), ("2", True), ("10", True), ("9007199254740993", True),
     ("0", False), ("01", False), ("-3", False), ("+3", False), ("2a", False), ("７", False),
     ("١", False), ("400\n", False), (" 4", False), ("4 ", False), ("", False), ("1_000", False),
     ("tmp", False), (".DS_Store", False)],
)
def test_canonical_gen_name_examples(name: str, expected: bool) -> None:
    assert is_canonical_gen_name(name) is expected


@props(300)
@given(st.one_of(st.text(max_size=6), st.from_regex(CANON_RE, fullmatch=True), st.integers(0, 10**6).map(str)))
def test_canonical_gen_name_equals_the_b4_predicate(name: str) -> None:
    assert is_canonical_gen_name(name) is oracle_canonical(name)


# --------------------------------------------------------------------------- G-01 / G-03


def test_g01_valid_book_collects_older_and_newer_orphans_and_the_tmp(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    before = tree(book)
    result = collect_garbage(book, min_manifest_age_s=None)
    assert result == GcResult("valid", ("gen/1", "gen/3", MANIFEST_TMP), ())
    after = tree(book)
    assert sorted(os.listdir(book / GEN_DIR)) == ["2"]
    assert not os.path.lexists(book / MANIFEST_TMP)
    assert sub(after, "gen/2") == sub(before, "gen/2")
    for rel in [*USER_DATA, *STRAY, MANIFEST, "chroma_db", "ai_conversations"]:
        assert sub(after, rel) == sub(before, rel), rel
    assert classify(book, full=True) == "valid"


def test_g03_no_manifest_collects_gens_and_tmp_and_keeps_legacy_and_user_data(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    book.mkdir()
    add_files(book, {**USER_DATA, **STRAY, **LEGACY_FLAT})
    write_gen(book / GEN_DIR / "1", 1)
    add_orphan(book, 4)
    (book / MANIFEST_TMP).write_bytes(b"{}")
    before = tree(book)
    result = collect_garbage(book)
    assert result == GcResult("missing", ("gen/1", "gen/4", MANIFEST_TMP), ())
    after = tree(book)
    assert (book / GEN_DIR).is_dir() and os.listdir(book / GEN_DIR) == []
    kept = {k: v for k, v in before.items() if not k.startswith("gen") and k not in (MANIFEST_TMP, "./")}
    assert {k: after[k] for k in kept} == kept
    assert set(after) == set(kept) | {"./", "gen/"}
    assert not os.path.lexists(book / MANIFEST)


# --------------------------------------------------------------------------- G-02


@pytest.mark.parametrize("kind", sorted(CORRUPTIONS))
def test_g02_every_corrupt_condition_deletes_nothing_and_logs_error(
    tmp_path: Path, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    book = tmp_path / "b_data"
    build_book(book, orphans=(3, 9))
    mutate, keyword = CORRUPTIONS[kind]
    mutate(book, tmp_path / "outside")
    assert classify(book, full=False) == "corrupt"  # the fixture really is corrupt
    before = tree(tmp_path)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = collect_garbage(book, min_manifest_age_s=None)
    assert (result.state, result.deleted) == ("corrupt", ())
    assert tree(tmp_path) == before
    msgs = error_records(caplog)
    assert any(str(book) in m and keyword in m for m in msgs), msgs


def test_g02_permission_denied_manifest_deletes_nothing_and_logs_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores mode 000")
    book = tmp_path / "b_data"
    build_book(book, orphans=(3, 9))
    before = tree(tmp_path)  # the snapshot reads file bytes, so take it while the manifest is readable
    os.chmod(book / MANIFEST, 0)
    try:
        with caplog.at_level(logging.INFO, logger=LOGGER):
            result = collect_garbage(book)
    finally:
        os.chmod(book / MANIFEST, 0o644)  # chmod moves ctime only; the snapshot compares mtime_ns, inode, bytes
    assert (result.state, result.deleted) == ("corrupt", ())
    assert tree(tmp_path) == before
    msgs = error_records(caplog)
    assert any(str(book) in m and "Permission denied" in m for m in msgs), msgs


# --------------------------------------------------------------------------- G-04 / G-05 / G-12b generator

BASE_KINDS = ("valid", "nomanifest", "absent", *(f"corrupt:{k}" for k in sorted(CORRUPTIONS)))


@st.composite
def gc_scenarios(draw: st.DrawFn) -> dict[str, Any]:
    return {
        "base": draw(st.sampled_from(BASE_KINDS)),
        "previous": draw(st.booleans()),
        "orphans": draw(st.sets(st.integers(3, 14), max_size=3)),
        "noncanon": draw(st.sets(st.sampled_from(NONCANON_NAMES), max_size=4)),
        "noncanon_is_dir": draw(st.booleans()),
        "user": draw(st.sets(st.sampled_from(sorted(USER_DATA)))),
        "stray": draw(st.booleans()),
        "legacy": draw(st.booleans()),
        "tmp": draw(st.booleans()),
    }


def materialise(td: Path, sc: dict[str, Any]) -> Path:
    book = td / "b_data"
    base: str = sc["base"]
    if base == "absent":
        return book
    book.mkdir()
    if base == "nomanifest":
        if sc["previous"]:
            write_gen(book / GEN_DIR / "1", 1)
        (book / GEN_DIR).mkdir(exist_ok=True)
    else:
        build_book(book, previous=(1,) if sc["previous"] else (), orphans=(), tmp=False, user=False, stray=False)
    for n in sorted(sc["orphans"]):
        add_orphan(book, n)
    for name in sorted(sc["noncanon"]):
        if sc["noncanon_is_dir"]:
            _write(book / GEN_DIR / name / "keep.bin", b"keep " + name.encode())
        else:
            _write(book / GEN_DIR / name, b"keep " + name.encode())
    add_files(book, {k: USER_DATA[k] for k in sc["user"]})
    if sc["stray"]:
        add_files(book, STRAY)
    if sc["legacy"]:
        add_files(book, LEGACY_FLAT)
    if sc["tmp"]:
        (book / MANIFEST_TMP).write_bytes(b"tmp junk")
    if base.startswith("corrupt:"):
        CORRUPTIONS[base.split(":", 1)[1]][0](book, td / "outside")
    return book


def check_gc_outcome(
    book: Path, base: str, before: dict[str, tuple[Any, ...]], after: dict[str, tuple[Any, ...]], result: GcResult
) -> None:
    """The G-04 conservation checks over a snapshot of the book's *parent* (outside targets included)."""
    bk = book.name
    if base == "absent":
        assert result == GcResult("missing", (), ())
        assert after == before and not os.path.lexists(book)
        return
    if base.startswith("corrupt:"):
        assert (result.state, result.deleted) == ("corrupt", ())
        assert after == before
        return
    assert result.state == ("valid" if base == "valid" else "missing")
    assert list(result.deleted) == sorted(result.deleted)
    for d in result.deleted:
        assert d == MANIFEST_TMP or (d.startswith("gen/") and oracle_canonical(d[len("gen/"):])), d
        assert sub(before, f"{bk}/{d}") and not sub(after, f"{bk}/{d}"), d
    assert "gen/2" not in result.deleted
    gone = {k for k in before if k not in after}
    assert all(any(k in sub(before, f"{bk}/{d}") for d in result.deleted) for k in gone), gone
    assert set(after) <= set(before), set(after) - set(before)  # nothing created, no manifest rolled forward
    changed = {k for k in after if after[k] != before[k]}
    assert changed <= {f"{bk}/", f"{bk}/gen/"}, changed  # only the two parent directories' mtimes move
    assert not os.path.lexists(book / MANIFEST_TMP)
    survivors = set(os.listdir(book / GEN_DIR))
    canonical_left = {n for n in survivors if oracle_canonical(n)}
    assert canonical_left == ({"2"} if base == "valid" else set())
    if base == "nomanifest":
        assert not os.path.lexists(book / MANIFEST)


@props(80)
@given(gc_scenarios())
def test_g04_conservation_across_every_gc_outcome(sc: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as raw:
        td = Path(raw)
        book = materialise(td, sc)
        before = tree(td)
        result = collect_garbage(book, min_manifest_age_s=None)
        check_gc_outcome(book, sc["base"], before, tree(td), result)
        if sc["base"] in ("valid", "nomanifest"):
            assert set(result.skipped) == {f"gen/{n}" for n in sc["noncanon"]}


@props(50)
@given(gc_scenarios())
def test_g05_gc_is_idempotent(sc: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as raw:
        td = Path(raw)
        book = materialise(td, sc)
        first = collect_garbage(book)
        after_first = tree(td)
        second = collect_garbage(book)
        assert tree(td) == after_first
        assert second.deleted == ()
        assert second.state == first.state


# --------------------------------------------------------------------------- G-06 / G-06b


def test_g06_non_canonical_names_are_left_and_symlinked_entries_are_unlinked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    book = tmp_path / "b_data"
    build_book(book, previous=(), orphans=(), tmp=False)
    gen = book / GEN_DIR
    for d in ("01", "tmp", "-3", "2a"):
        _write(gen / d / "keep.bin", d.encode())
    _write(gen / ".DS_Store", b"finder")
    _write(gen / "７", b"full-width seven")
    outside_dir, outside_file = tmp_path / "outside_dir", tmp_path / "outside_file"
    _write(outside_dir / "precious.png", b"precious")
    outside_file.write_bytes(b"precious file")
    os.symlink(outside_dir, gen / "7")
    os.symlink(outside_file, gen / "8")
    before = tree(tmp_path)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = collect_garbage(book)
    noncanon = sorted(f"gen/{n}" for n in ("01", "tmp", ".DS_Store", "-3", "2a", "７"))
    assert result == GcResult("valid", ("gen/7", "gen/8"), tuple(noncanon))
    after = tree(tmp_path)
    assert not os.path.lexists(gen / "7") and not os.path.lexists(gen / "8")
    for rel in [*noncanon, "gen/2"]:
        assert sub(after, f"b_data/{rel}") == sub(before, f"b_data/{rel}"), rel
    assert sub(after, "outside_dir") == sub(before, "outside_dir")
    assert sub(after, "outside_file") == sub(before, "outside_file")
    logged = " ".join(r.getMessage() for r in caplog.records if r.name == LOGGER)
    assert all(n in logged for n in noncanon), logged


def test_g06b_nested_symlinks_inside_collected_gens_are_removed_never_followed(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    build_book(book, previous=(), orphans=(), tmp=False)
    outside_dir, outside_file = tmp_path / "outside_dir", tmp_path / "outside_file"
    _write(outside_dir / "precious.png", b"precious")
    outside_file.write_bytes(b"precious epub")
    for g in ("1", "3"):
        d = book / GEN_DIR / g
        _write(d / CHAPTERS, b"regular chapters " + g.encode())
        os.symlink(outside_dir, d / IMAGES)
        os.symlink(outside_file, d / EPUB)
    before = tree(tmp_path)
    result = collect_garbage(book, min_manifest_age_s=None)
    assert result == GcResult("valid", ("gen/1", "gen/3"), ())
    after = tree(tmp_path)
    assert not os.path.lexists(book / GEN_DIR / "1") and not os.path.lexists(book / GEN_DIR / "3")
    assert sub(after, "outside_dir") == sub(before, "outside_dir")
    assert sub(after, "outside_file") == sub(before, "outside_file")
    assert sub(after, "b_data/gen/2") == sub(before, "b_data/gen/2")


# --------------------------------------------------------------------------- G-07 / G-08


@pytest.mark.parametrize("with_manifest", [False, True])
def test_g07_symlinked_gen_is_corrupt_and_never_traversed(
    tmp_path: Path, with_manifest: bool, caplog: pytest.LogCaptureFixture
) -> None:
    book = tmp_path / "b_data"
    book.mkdir()
    elsewhere = tmp_path / "elsewhere"
    m = write_gen(elsewhere / "2", 2)
    _write(elsewhere / "1" / CHAPTERS, b"old")
    _write(elsewhere / "precious.txt", b"precious")
    os.symlink(elsewhere, book / GEN_DIR)
    (book / MANIFEST_TMP).write_bytes(b"tmp")
    add_files(book, USER_DATA)
    if with_manifest:
        (book / MANIFEST).write_bytes(manifest_to_bytes(m))
    before = tree(tmp_path)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = collect_garbage(book)
    assert (result.state, result.deleted) == ("corrupt", ())
    assert tree(tmp_path) == before
    assert any(str(book) in msg for msg in error_records(caplog))


@pytest.mark.parametrize("with_manifest", [False, True])
def test_g08_gen_regular_file_is_corrupt_with_zero_deletions(
    tmp_path: Path, with_manifest: bool, caplog: pytest.LogCaptureFixture
) -> None:
    book = tmp_path / "b_data"
    book.mkdir()
    (book / GEN_DIR).write_bytes(b"gen is a file")
    (book / MANIFEST_TMP).write_bytes(b"tmp")
    add_files(book, USER_DATA)
    if with_manifest:
        m = write_gen(tmp_path / "scratch" / "1", 1)
        (book / MANIFEST).write_bytes(manifest_to_bytes(m))
    before = tree(tmp_path)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = collect_garbage(book)
    assert (result.state, result.deleted) == ("corrupt", ())
    assert tree(tmp_path) == before
    assert any(str(book) in msg for msg in error_records(caplog))


# --------------------------------------------------------------------------- G-09 / G-10 / G-10b


@pytest.mark.parametrize(
    "delta_ns, collects",
    [(10 * 10**9, False), (299_999 * 10**6, False), (300 * 10**9, True), (300_001 * 10**6, True), (400 * 10**9, True)],
)
def test_g09_age_guard_boundaries(tmp_path: Path, delta_ns: int, collects: bool) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    t = NOW_NS - delta_ns
    os.utime(book / MANIFEST, ns=(t, t))
    before = tree(book)
    result = collect_garbage(book, min_manifest_age_s=RETAIN_S, now=NOW)
    if collects:
        assert result == GcResult("valid", ("gen/1", "gen/3", MANIFEST_TMP), ())
        assert sorted(os.listdir(book / GEN_DIR)) == ["2"]
    else:
        assert result == GcResult("valid", (), ())
        assert tree(book) == before


def test_g09_no_age_guard_collects_a_young_manifest(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    os.utime(book / MANIFEST, ns=(NOW_NS - 10**9, NOW_NS - 10**9))
    result = collect_garbage(book, min_manifest_age_s=None, now=NOW)
    assert result == GcResult("valid", ("gen/1", "gen/3", MANIFEST_TMP), ())


def test_g09_age_guard_still_reports_corruption_first(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    c_artifact_missing(book, tmp_path / "outside")
    os.utime(book / MANIFEST, ns=(NOW_NS - 10**9, NOW_NS - 10**9))
    before = tree(book)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = collect_garbage(book, min_manifest_age_s=RETAIN_S, now=NOW)
    assert result.state == "corrupt" and result.deleted == ()
    assert tree(book) == before
    assert error_records(caplog)


def test_g10_age_guard_does_not_apply_without_a_manifest(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    book.mkdir()
    write_gen(book / GEN_DIR / "1", 1)
    (book / MANIFEST_TMP).write_bytes(b"tmp")
    result = collect_garbage(book, min_manifest_age_s=RETAIN_S, now=NOW)
    assert result == GcResult("missing", ("gen/1", MANIFEST_TMP), ())
    assert not os.path.lexists(book / GEN_DIR / "1")


def test_g10b_a_valid_looking_tmp_is_never_rolled_forward(tmp_path: Path) -> None:
    book = tmp_path / "b_data"
    book.mkdir()
    add_files(book, USER_DATA)
    m = write_gen(book / GEN_DIR / "1", 1)
    (book / MANIFEST_TMP).write_bytes(manifest_to_bytes(m))
    validate_full(book / GEN_DIR / "1", m)  # the tmp really would validate: what a p5..p8 kill leaves
    user_before = {k: v for k, v in tree(book).items() if k.split("/")[0] in {p.split("/")[0] for p in USER_DATA}}
    result = collect_garbage(book, min_manifest_age_s=None)
    assert result == GcResult("missing", ("gen/1", MANIFEST_TMP), ())
    assert not os.path.lexists(book / MANIFEST)
    assert classify(book, full=True) == "missing"
    after = tree(book)
    assert {k: after[k] for k in user_before} == user_before


# --------------------------------------------------------------------------- G-11


@pytest.mark.parametrize("parent_present", [True, False])
def test_g11_absent_book_dir_is_a_no_op_and_nothing_is_created(tmp_path: Path, parent_present: bool) -> None:
    parent = tmp_path / ("books" if parent_present else "no_such_parent")
    if parent_present:
        parent.mkdir()
    book = parent / "b_data"
    before = tree(tmp_path)
    result = collect_garbage(book)
    assert result == GcResult("missing", (), ())
    assert not os.path.lexists(book)
    assert os.path.lexists(parent) is parent_present
    assert tree(tmp_path) == before


# --------------------------------------------------------------------------- G-12 / G-12b journal


def _identity(arg: Any) -> tuple[int, int] | None:
    try:
        st_ = os.fstat(arg) if isinstance(arg, int) else os.stat(arg)
    except (OSError, TypeError, ValueError):
        return None
    return st_.st_dev, st_.st_ino


class ListingJournal:
    """Recording passthroughs over every listing API in the module docstring; the real call still happens."""

    def __init__(self, mp: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, Any, tuple[int, int] | None]] = []
        orig_listdir, orig_scandir, orig_walk = os.listdir, os.scandir, os.walk
        orig_glob, orig_iglob = glob.glob, glob.iglob
        orig_iterdir, orig_pglob, orig_rglob = pathlib.Path.iterdir, pathlib.Path.glob, pathlib.Path.rglob

        def rec(kind: str, arg: Any) -> None:
            self.calls.append((kind, arg, _identity(arg)))

        def listdir(path: Any = ".") -> Any:
            rec("listdir", path)
            return orig_listdir(path)

        def scandir(path: Any = ".") -> Any:
            rec("scandir", path)
            return orig_scandir(path)

        def walk(top: Any, *a: Any, **k: Any) -> Iterator[Any]:
            rec("walk", top)
            return orig_walk(top, *a, **k)

        def _glob_dir(pattern: Any, k: dict[str, Any]) -> Any:
            root = k.get("root_dir")
            head = os.path.dirname(os.fspath(pattern)) or "."
            return os.path.join(root, head) if root is not None else head

        def glob_(pattern: Any, *a: Any, **k: Any) -> Any:
            rec("glob", _glob_dir(pattern, k))
            return orig_glob(pattern, *a, **k)

        def iglob(pattern: Any, *a: Any, **k: Any) -> Any:
            rec("iglob", _glob_dir(pattern, k))
            return orig_iglob(pattern, *a, **k)

        def iterdir(self_: pathlib.Path) -> Any:
            rec("Path.iterdir", self_)
            return orig_iterdir(self_)

        def pglob(self_: pathlib.Path, *a: Any, **k: Any) -> Any:
            rec("Path.glob", self_)
            return orig_pglob(self_, *a, **k)

        def rglob(self_: pathlib.Path, *a: Any, **k: Any) -> Any:
            rec("Path.rglob", self_)
            return orig_rglob(self_, *a, **k)

        mp.setattr(os, "listdir", listdir)
        mp.setattr(os, "scandir", scandir)
        mp.setattr(os, "walk", walk)
        mp.setattr(glob, "glob", glob_)
        mp.setattr(glob, "iglob", iglob)
        mp.setattr(pathlib.Path, "iterdir", iterdir)
        mp.setattr(pathlib.Path, "glob", pglob)
        mp.setattr(pathlib.Path, "rglob", rglob)


def test_g12_the_book_root_is_never_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    journal = ListingJournal(monkeypatch)
    result = collect_garbage(book)
    monkeypatch.undo()
    assert result == GcResult("valid", ("gen/1", "gen/3", MANIFEST_TMP), ())
    root = os.path.realpath(book)
    listed = [os.path.realpath(a) for _, a, _ in journal.calls if not isinstance(a, int)]
    assert root not in listed, journal.calls
    assert (book / "README.txt").read_bytes() == STRAY["README.txt"]


@props(30)
@given(gc_scenarios())
def test_g12b_root_listing_guard_by_inode_identity_over_every_gc_kind(sc: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as raw:
        td = Path(raw)
        book = materialise(td, sc)
        root_id = _identity(book)
        before = tree(td)
        with pytest.MonkeyPatch.context() as mp:
            journal = ListingJournal(mp)
            result = collect_garbage(book, min_manifest_age_s=None)
        check_gc_outcome(book, sc["base"], before, tree(td), result)
        if root_id is not None:
            assert all(ident != root_id for _, _, ident in journal.calls), journal.calls


# --------------------------------------------------------------------------- G-13


def test_g13_gc_fsyncs_gen_and_the_book_dir_after_the_last_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "b_data"
    build_book(book)
    gen_id, book_id = _identity(book / GEN_DIR), _identity(book)
    events: list[tuple[str, Any]] = []
    orig_fsync, orig_unlink, orig_rmdir = os.fsync, os.unlink, os.rmdir

    def fsync(fd: int) -> None:
        events.append(("fsync", _identity(fd)))
        orig_fsync(fd)

    def unlink(path: Any, *a: Any, **k: Any) -> None:
        events.append(("unlink", path))
        orig_unlink(path, *a, **k)

    def rmdir(path: Any, *a: Any, **k: Any) -> None:
        events.append(("rmdir", path))
        orig_rmdir(path, *a, **k)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "unlink", unlink)
    monkeypatch.setattr(os, "rmdir", rmdir)
    result = collect_garbage(book)
    monkeypatch.undo()
    assert result == GcResult("valid", ("gen/1", "gen/3", MANIFEST_TMP), ())
    deletions = [i for i, (kind, _) in enumerate(events) if kind in ("unlink", "rmdir")]
    assert deletions, events
    synced_after = {ident for kind, ident in events[deletions[-1] + 1:] if kind == "fsync"}
    assert gen_id in synced_after and book_id in synced_after, events


# ---------------------------------------------------------- WI-1.10 B4 / B5: GC on odd shapes and unreadable dirs


def test_wi110_b4_gc_on_a_regular_file_is_missing_and_a_no_op(tmp_path: Path) -> None:
    """B4 (guard, S3, Level 1+2): book_dir is a regular file: GcResult("missing", (), ()), file untouched."""
    book = tmp_path / "x_data"
    book.write_bytes(b"not a book")
    before = tree(tmp_path)
    assert collect_garbage(book) == GcResult("missing", (), ())
    assert tree(tmp_path) == before


@pytest.mark.parametrize("previous", [(), (1,)], ids=["nothing-else", "with-previous"])
def test_wi110_b4_tmp_directory_is_skipped_never_deleted(tmp_path: Path, previous: tuple[int, ...]) -> None:
    """B4 (guard, S3, Level 1+2): a manifest.json.tmp directory stays, is reported skipped; nothing else changes."""
    book = tmp_path / "x_data"
    build_book(book, previous=previous, orphans=(), tmp=False)
    _write(book / MANIFEST_TMP / "inner.bin", b"keep me")
    before = tree(book)
    result = collect_garbage(book)
    expect_deleted = tuple(f"{GEN_DIR}/{g}" for g in previous)
    assert result == GcResult("valid", expect_deleted, (MANIFEST_TMP,))
    after = tree(book)
    assert sub(after, MANIFEST_TMP) == sub(before, MANIFEST_TMP)
    for rel in expect_deleted:
        assert sub(after, rel) == {}
    rest = {k: v for k, v in before.items() if k not in (".", f"{GEN_DIR}/") and not any(
        k == d or k.startswith(d + "/") for d in expect_deleted)}
    assert {k: v for k, v in after.items() if k in rest} == rest
    assert collect_garbage(book) == GcResult("valid", (), (MANIFEST_TMP,))


_root_only = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores mode bits")


@_root_only
def test_wi110_b5_gc_on_unsearchable_book_dir_is_corrupt_and_deletes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """B5 (failure, S3, Level 1+2): EACCES on the book dir (0o600): corrupt, ERROR, nothing deleted."""
    book = tmp_path / "x_data"
    build_book(book)  # previous gen/1, orphan gen/3 and a stale tmp: all would be collected if GC ran
    before = tree(book)
    caplog.set_level(logging.ERROR, logger=LOGGER)
    os.chmod(book, 0o600)
    try:
        result = collect_garbage(book)
    finally:
        os.chmod(book, 0o755)
    assert result == GcResult("corrupt", (), ())
    assert error_records(caplog)
    assert tree(book) == before


@_root_only
def test_wi110_b5_gc_on_unlistable_gen_is_corrupt_and_deletes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """B5 (failure, S3, Level 1+2): valid manifest but gen/ is 0o300 (no read): corrupt, nothing deleted."""
    book = tmp_path / "x_data"
    build_book(book)
    before = tree(book)
    caplog.set_level(logging.ERROR, logger=LOGGER)
    os.chmod(book / GEN_DIR, 0o300)
    try:
        result = collect_garbage(book)
    finally:
        os.chmod(book / GEN_DIR, 0o755)
    assert result == GcResult("corrupt", (), ())
    assert any("cannot be listed" in m for m in error_records(caplog)), error_records(caplog)
    assert tree(book) == before
