"""012 WI-1.2: the ``chapters.jsonl`` writer and its seek reader (``write_chapters`` / ``read_chapter``).

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.2" (cases C-01 .. C-10).

Laws (policy-core S4/S5):
- seek round-trip: ``read_chapter(gen, entries[i]) == chapters[i]`` for every i (C-01);
- contiguity conservation: ``offset[0] == 0``, ``offset[i+1] == offset[i] + length[i] + 1``,
  ``sum(length + 1) == size == getsize`` and the newline count equals the chapter count (C-01, C-03, C-04);
- hash integrity, file-level and per line, computed from the raw bytes independently of the reader (C-01, C-10).

Every tamper (flipped byte, shifted offset, wrong length, truncation, forged id/order) raises
``ChapterReadError`` and never yields another chapter's content (C-06 .. C-09).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader3_app.book_format import (
    CHAPTERS,
    BookFormatError,
    ChapterIndexEntry,
    ChapterReadError,
    ChapterRecord,
    read_chapter,
    write_chapters,
)


def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- generators

# Separators and escapes that must never split a record, plus NUL, quote, backslash and non-BMP.
_TRICKY = ["\n", "\r", "\r\n", " ", " ", "\x00", '"', "\\", "🜁", "第一章", "café", "\U0001f600"]

st_text = st.one_of(
    st.text(max_size=40),
    st.lists(st.one_of(st.sampled_from(_TRICKY), st.text(max_size=5)), max_size=12).map("".join),
)


@st.composite
def st_chapters(draw: st.DrawFn, max_size: int = 50) -> list[ChapterRecord]:
    ids = draw(st.lists(st_text, max_size=max_size, unique=True))
    out: list[ChapterRecord] = []
    for i, cid in enumerate(ids):
        out.append(
            ChapterRecord(
                id=cid,
                href=draw(st_text),
                title=draw(st_text),
                content=draw(st_text),
                text=draw(st_text),
                order=draw(st.one_of(st.just(i), st.integers(min_value=0, max_value=2**31))),
            )
        )
    return out


def _gen_dir(base: Path) -> Path:
    gen = base / "gen" / "1"
    gen.mkdir(parents=True)
    return gen


def _five(tmp_path: Path) -> tuple[Path, list[ChapterRecord], tuple[ChapterIndexEntry, ...], int]:
    gen = _gen_dir(tmp_path)
    chapters = [
        ChapterRecord(
            id=f"ch{i}",
            href=f"text/ch{i}.xhtml",
            title=f"第{i}章",
            content=f"<p>第{i}章 café 🜁\nline {i}</p>",
            text=f"第{i}章 café 🜁\nline {i}",
            order=i,
        )
        for i in range(5)
    ]
    entries, size, _ = write_chapters(gen / CHAPTERS, chapters)
    return gen, chapters, tuple(entries), size


# --------------------------------------------------------------------------- C-01 law


def _check_laws(gen: Path, chapters: list[ChapterRecord]) -> None:
    path = gen / CHAPTERS
    entries, size, sha = write_chapters(path, chapters)
    raw = path.read_bytes()

    assert len(entries) == len(chapters)
    assert size == len(raw) == os.path.getsize(path)
    assert sha == _sha(raw)
    assert raw.count(b"\n") == len(chapters)

    expected_offset = 0
    for ch, entry in zip(chapters, entries, strict=True):
        assert isinstance(entry, ChapterIndexEntry)
        assert entry.offset_bytes == expected_offset
        assert (entry.id, entry.href, entry.order) == (ch.id, ch.href, ch.order)
        expected_offset = entry.offset_bytes + entry.length_bytes + 1
        assert read_chapter(gen, entry) == ch
    assert expected_offset == size
    assert sum(e.length_bytes + 1 for e in entries) == size


@props(150)
@given(chapters=st_chapters())
def test_c01_seek_round_trip_contiguity_and_integrity(chapters: list[ChapterRecord]) -> None:
    """C-01 (property, S5, Level 1+2): every chapter reads back by seek; offsets are conserved; hashes match."""
    with tempfile.TemporaryDirectory() as tmp:
        _check_laws(_gen_dir(Path(tmp)), chapters)


# --------------------------------------------------------------------------- C-02 .. C-05


def test_c02_only_lf_terminates_a_record(tmp_path: Path) -> None:
    """C-02 (boundary, S2, Level 2): embedded CR/LF, U+2028/U+2029 and non-BMP text never split a record."""
    gen = _gen_dir(tmp_path)
    texts = ["a\nb", "x y z\r", "🜁" * 1000]
    chapters = [
        ChapterRecord(id=f"c{i}", href=f"h{i}.xhtml", title=t, content=t, text=t, order=i)
        for i, t in enumerate(texts)
    ]
    entries, size, _ = write_chapters(gen / CHAPTERS, chapters)
    raw = (gen / CHAPTERS).read_bytes()

    assert raw.count(b"\n") == 3
    lines = raw.split(b"\n")
    assert lines[-1] == b""
    assert [json.loads(line.decode("utf-8")) for line in lines[:-1]] == [dataclasses.asdict(c) for c in chapters]
    assert " ".encode() in raw  # ensure_ascii=False: the separator is stored raw, not as \\u2028
    assert " ".encode() in raw
    assert "🜁".encode() in raw
    assert [e.length_bytes for e in entries] == [len(line) for line in lines[:-1]]
    assert size == len(raw)


def test_c03_empty_chapter_list(tmp_path: Path) -> None:
    """C-03 (boundary, S2, Level 1+2): no chapters gives an empty file, size 0 and the empty-file sha."""
    gen = _gen_dir(tmp_path)
    entries, size, sha = write_chapters(gen / CHAPTERS, [])
    assert (tuple(entries), size, sha) == ((), 0, _sha(b""))
    assert (gen / CHAPTERS).is_file()
    assert (gen / CHAPTERS).read_bytes() == b""


def test_c04_single_chapter_with_empty_strings(tmp_path: Path) -> None:
    """C-04 (boundary, S2, Level 1): one all-empty record sits at offset 0 and fills the file minus the newline."""
    gen = _gen_dir(tmp_path)
    ch = ChapterRecord(id="", href="", title="", content="", text="", order=0)
    entries, size, sha = write_chapters(gen / CHAPTERS, [ch])
    (entry,) = entries
    assert entry.offset_bytes == 0
    assert size == entry.length_bytes + 1 == os.path.getsize(gen / CHAPTERS)
    assert sha == _sha((gen / CHAPTERS).read_bytes())
    assert read_chapter(gen, entry) == ch


@props(50)
@given(chapters=st_chapters())
def test_c05_determinism(chapters: list[ChapterRecord]) -> None:
    """C-05 (determinism, S5, Level 2): the same input written twice gives identical bytes and returns."""
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a.jsonl"
        b = Path(tmp) / "b.jsonl"
        ra = write_chapters(a, chapters)
        rb = write_chapters(b, chapters)
        assert ra == rb
        raw = a.read_bytes()
        assert raw == b.read_bytes()
        for ch, line in zip(chapters, raw.split(b"\n")[:-1], strict=True):
            canonical = json.dumps(dataclasses.asdict(ch), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            assert line == canonical.encode("utf-8")


# --------------------------------------------------------------------------- C-06 .. C-09 tamper


def _others_read(
    gen: Path, chapters: list[ChapterRecord], entries: tuple[ChapterIndexEntry, ...], skip: set[int]
) -> None:
    for i, (ch, entry) in enumerate(zip(chapters, entries, strict=True)):
        if i not in skip:
            assert read_chapter(gen, entry) == ch


@pytest.mark.parametrize("where", ["first", "middle", "last"])
def test_c06_byte_flip_inside_chapter_k(tmp_path: Path, where: str) -> None:
    """C-06 (failure, S3, Level 1): a flipped byte in chapter 2 fails only chapter 2, as ChapterReadError."""
    gen, chapters, entries, _ = _five(tmp_path)
    e = entries[2]
    pos = {"first": e.offset_bytes, "middle": e.offset_bytes + e.length_bytes // 2,
           "last": e.offset_bytes + e.length_bytes - 1}[where]
    path = gen / CHAPTERS
    raw = bytearray(path.read_bytes())
    raw[pos] ^= 0x01
    path.write_bytes(bytes(raw))

    with pytest.raises(ChapterReadError) as info:
        read_chapter(gen, e)
    assert isinstance(info.value, ValueError)
    assert isinstance(info.value, BookFormatError)
    _others_read(gen, chapters, entries, skip={2})


@pytest.mark.parametrize(
    "change",
    ["offset+1", "offset-1", "length+1", "length-1", "offset=size+10", "offset=-1", "length=-1"],
)
def test_c07_wrong_offset_or_length(tmp_path: Path, change: str) -> None:
    """C-07 (failure, S3, Level 1): a shifted offset or wrong length raises ChapterReadError and nothing else."""
    gen, chapters, entries, size = _five(tmp_path)
    e = entries[2]
    forged = {
        "offset+1": dataclasses.replace(e, offset_bytes=e.offset_bytes + 1),
        "offset-1": dataclasses.replace(e, offset_bytes=e.offset_bytes - 1),
        "length+1": dataclasses.replace(e, length_bytes=e.length_bytes + 1),
        "length-1": dataclasses.replace(e, length_bytes=e.length_bytes - 1),
        "offset=size+10": dataclasses.replace(e, offset_bytes=size + 10),
        "offset=-1": dataclasses.replace(e, offset_bytes=-1),
        "length=-1": dataclasses.replace(e, length_bytes=-1),
    }[change]
    with pytest.raises(ChapterReadError):
        read_chapter(gen, forged)
    _others_read(gen, chapters, entries, skip=set())


def test_c07_truncated_file(tmp_path: Path) -> None:
    """C-07 (failure, S3, Level 1): a file cut inside chapter 4 fails chapter 4; chapters 0..3 still read."""
    gen, chapters, entries, _ = _five(tmp_path)
    path = gen / CHAPTERS
    path.write_bytes(path.read_bytes()[: entries[4].offset_bytes + 3])
    with pytest.raises(ChapterReadError):
        read_chapter(gen, entries[4])
    _others_read(gen, chapters, entries, skip={4})


@props(50)
@given(chapters=st_chapters().filter(lambda cs: len(cs) >= 2), data=st.data())
def test_c08_never_another_chapters_content(chapters: list[ChapterRecord], data: st.DataObject) -> None:
    """C-08 (failure, S4, Level 1): an entry pointing at line j but claiming chapter k (k != j) is rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        gen = _gen_dir(Path(tmp))
        entries, _, _ = write_chapters(gen / CHAPTERS, chapters)
        j = data.draw(st.integers(0, len(chapters) - 1))
        k = data.draw(st.integers(0, len(chapters) - 1).filter(lambda x: x != j))
        forged = dataclasses.replace(entries[j], id=entries[k].id, order=entries[k].order)
        with pytest.raises(ChapterReadError):
            read_chapter(gen, forged)


@pytest.mark.parametrize("field,value", [("id", "other"), ("order", 7)])
def test_c09_entry_id_or_order_differs_from_line(tmp_path: Path, field: str, value: Any) -> None:
    """C-09 (guard, S3, Level 1): an index entry whose id or order disagrees with the line raises."""
    gen, _, entries, _ = _five(tmp_path)
    forged = dataclasses.replace(entries[2], **{field: value})
    with pytest.raises(ChapterReadError):
        read_chapter(gen, forged)


# --------------------------------------------------------------------------- C-10


@props(50)
@given(chapters=st_chapters())
def test_c10_line_hashes_from_raw_bytes(chapters: list[ChapterRecord]) -> None:
    """C-10 (property, S4, Level 2): each entry's sha is the sha of its raw byte span; the next byte is LF."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / CHAPTERS
        entries, _, _ = write_chapters(path, chapters)
        raw = path.read_bytes()
        for e in entries:
            span = raw[e.offset_bytes : e.offset_bytes + e.length_bytes]
            assert e.sha256 == _sha(span)
            assert b"\n" not in span
            assert raw[e.offset_bytes + e.length_bytes : e.offset_bytes + e.length_bytes + 1] == b"\n"


# ---------------------------------------------------------- WI-1.10 A2: never through a symlink, never over a file


def test_wi110_a2_existing_file_at_target_is_refused_and_unchanged(tmp_path: Path) -> None:
    """A2 (guard, S3, Level 2): write_chapters creates exclusively; an existing file is never truncated."""
    path = tmp_path / CHAPTERS
    path.write_bytes(b"previous bytes")
    before = os.lstat(path)
    with pytest.raises(FileExistsError):
        write_chapters(path, [ChapterRecord(id="a", href="a.xhtml", title="A", content="<p/>", text="", order=0)])
    assert path.read_bytes() == b"previous bytes"
    assert os.lstat(path).st_ino == before.st_ino


@pytest.mark.parametrize("dangling", [False, True], ids=["live-target", "dangling"])
def test_wi110_a2_symlink_at_target_is_never_followed(tmp_path: Path, dangling: bool) -> None:
    """A2 (guard, S3, Level 2): a symlink at the target raises; its target is neither written nor created."""
    target = tmp_path / "outside.bin"
    if not dangling:
        target.write_bytes(b"outside data")
    link = tmp_path / CHAPTERS
    os.symlink(target, link)
    with pytest.raises(OSError):
        write_chapters(link, [ChapterRecord(id="a", href="a.xhtml", title="A", content="<p/>", text="", order=0)])
    assert os.path.islink(link) and os.readlink(link) == str(target)
    if dangling:
        assert not os.path.lexists(target)
    else:
        assert target.read_bytes() == b"outside data"


def test_wi110_a2_new_file_mode_matches_the_other_artifacts(tmp_path: Path) -> None:
    """A2 (success, S1, Level 2): chapters.jsonl is created 0o644 under the umask, like every _write_new artifact."""
    umask = os.umask(0)
    os.umask(umask)
    path = tmp_path / CHAPTERS
    entries, size, _ = write_chapters(path, [ChapterRecord(id="a", href="a", title="", content="", text="", order=0)])
    assert os.stat(path).st_mode & 0o777 == 0o644 & ~umask
    assert size == os.path.getsize(path) and len(entries) == 1


# ---------------------------------------------------------- WI-1.10 B1: malformed lines with a matching sha


def _crafted(tmp_path: Path, line: bytes) -> tuple[Path, ChapterIndexEntry]:
    gen = _gen_dir(tmp_path)
    (gen / CHAPTERS).write_bytes(line + b"\n")
    return gen, ChapterIndexEntry(id="a", href="a.xhtml", order=0, offset_bytes=0, length_bytes=len(line),
                                  sha256=_sha(line))


_GOOD_FIELDS: dict[str, Any] = {"id": "a", "href": "a.xhtml", "title": "A", "content": "<p/>", "text": "", "order": 0}


@pytest.mark.parametrize(
    "line,needle",
    [
        (b"not json at all", "not a JSON record"),
        (b"\xff\xfe\x00", "not a JSON record"),
        (b"[1]", "record is not an object"),
        (b'"a string"', "record is not an object"),
        (json.dumps({**_GOOD_FIELDS, "order": True}).encode(), "field 'order'"),
        (json.dumps({**_GOOD_FIELDS, "order": "0"}).encode(), "field 'order'"),
        (json.dumps({k: v for k, v in _GOOD_FIELDS.items() if k != "order"}).encode(), "field 'order'"),
        (json.dumps({**_GOOD_FIELDS, "title": None}).encode(), "field 'title'"),
    ],
    ids=["non-json", "non-utf8", "array", "string", "order-true", "order-str", "order-missing", "title-null"],
)
def test_wi110_b1_malformed_line_with_matching_sha_is_a_chapter_read_error(
    tmp_path: Path, line: bytes, needle: str
) -> None:
    """B1 (failure, S3, Level 1): the span hashes correctly but is not a record; the error is ChapterReadError."""
    gen, entry = _crafted(tmp_path, line)
    with pytest.raises(ChapterReadError, match=needle) as ei:
        read_chapter(gen, entry)
    assert isinstance(ei.value, BookFormatError)


def test_wi110_b1_well_formed_crafted_line_reads_back(tmp_path: Path) -> None:
    """B1 control (success, S1, Level 1): the same crafting with a valid record reads back as that record."""
    gen, entry = _crafted(tmp_path, json.dumps(_GOOD_FIELDS).encode())
    assert read_chapter(gen, entry) == ChapterRecord(**_GOOD_FIELDS)


def test_wi110_a2_large_file_crosses_the_write_buffer(tmp_path: Path) -> None:
    """A2 (boundary, S2, Level 2): more than one write block (> 1 MiB) is written whole and in order."""
    big = "第" * 200_000  # 600 000 UTF-8 bytes per record: three records cross the 1 MiB flush twice
    chapters = [ChapterRecord(id=f"c{i}", href=f"c{i}", title="", content=big, text=f"{i}", order=i) for i in range(5)]
    gen = _gen_dir(tmp_path)
    entries, size, sha = write_chapters(gen / CHAPTERS, chapters)
    raw = (gen / CHAPTERS).read_bytes()
    assert size == len(raw) > 2 * (1 << 20)
    assert sha == _sha(raw)
    assert [read_chapter(gen, e) for e in entries] == chapters
