"""012 WI-1.1: the book manifest schema, its canonical serialisation, and its strict parser.

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.1" (cases M-01 .. M-17).

Laws (policy-core S4/S5):
- round-trip: ``manifest_from_bytes(manifest_to_bytes(m)) == m`` (M-01);
- canonical idempotence: ``manifest_to_bytes(manifest_from_bytes(b)) == b`` for canonical ``b`` (M-02);
- total error type: every byte string yields a ``BookManifest`` or a ``ManifestError``, nothing else (M-03).

The field set is frozen by ``tests/unit/snapshots/book_manifest_schema.json`` (012 section 6 Q7).
"""
from __future__ import annotations

import copy
import dataclasses
import errno
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import types
import typing
from pathlib import Path
from typing import Any, Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from book_format_helpers import setup_scenario
from deg_assertions import STALE_FINGERPRINT  # type: ignore[import-not-found]
from reader3_app import book_format as bf
from reader3_app.book_format import (
    FORMAT_VERSION,
    ArtifactEntry,
    BookManifest,
    ChapterIndexEntry,
    ManifestError,
    ManifestMetadata,
    ManifestTocEntry,
    classify,
    manifest_from_bytes,
    manifest_to_bytes,
)

SNAPSHOT = Path(__file__).parent / "snapshots" / "book_manifest_schema.json"
SCHEMA_CLASS_NAMES = (
    "ArtifactEntry",
    "BookManifest",
    "ChapterIndexEntry",
    "ChapterRecord",
    "ManifestMetadata",
    "ManifestTocEntry",
)
Q7_RULE = (
    "Q7 (012 section 6): adding an optional field (one with a default) needs no FORMAT_VERSION bump; "
    "removing, renaming, retyping or changing the meaning of a field requires a FORMAT_VERSION bump. "
    "Update tests/unit/snapshots/book_manifest_schema.json in the same change."
)
HEX = "0123456789abcdef"
LEGAL_FIXED = ("chapters.jsonl", "book.epub", "book.pkl")
MAX_GENERATION = 2**53
EXAMPLE_FINGERPRINT = "5f" * 32
NEW_FIELDS = ("book_fingerprint", "extractor_version")



def props(max_examples: int) -> Any:
    return settings(
        deadline=None,
        max_examples=max_examples,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )


# --------------------------------------------------------------------------- generators


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_text = st.text(max_size=12)
_hex64 = st.text(alphabet=HEX, min_size=64, max_size=64)
_safe_basename = st.text(
    alphabet=st.characters(blacklist_characters="/\\\x00", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=10,
).filter(lambda s: s not in (".", ".."))


def _toc_level(depth: int, min_size: int = 0) -> st.SearchStrategy[tuple[ManifestTocEntry, ...]]:
    children = _toc_level(depth - 1) if depth > 0 else st.just(())
    entry = st.builds(
        ManifestTocEntry,
        title=_text,
        href=_text,
        file_href=_text,
        anchor=_text,
        children=children,
    )
    return st.lists(entry, min_size=min_size, max_size=4).map(tuple)


@st.composite
def st_manifest(draw: Any, min_toc: int = 0, min_chapters: int = 0, min_images: int = 0) -> BookManifest:
    """An internally consistent manifest under every F-03 rule."""
    metadata = ManifestMetadata(
        title=draw(_text),
        language=draw(_text),
        authors=tuple(draw(st.lists(_text, max_size=3))),
        description=draw(st.none() | _text),
        publisher=draw(st.none() | _text),
        date=draw(st.none() | _text),
        identifiers=tuple(draw(st.lists(_text, max_size=3))),
        subjects=tuple(draw(st.lists(_text, max_size=3))),
    )
    toc = draw(_toc_level(3, min_size=min_toc))

    n = draw(st.integers(min_chapters, 30))
    ids = draw(st.lists(_text, min_size=n, max_size=n, unique=True))
    lengths = draw(st.lists(st.integers(0, 5000), min_size=n, max_size=n))
    chapters = []
    offset = 0
    for i, (cid, length) in enumerate(zip(ids, lengths)):
        chapters.append(
            ChapterIndexEntry(
                id=cid,
                href=draw(_text),
                order=draw(st.integers(0, 10_000)) if draw(st.booleans()) else i,
                offset_bytes=offset,
                length_bytes=length,
                sha256=draw(_hex64),
            )
        )
        offset += length + 1
    size = offset
    chapters_sha = draw(_hex64)

    names = draw(st.lists(_safe_basename, min_size=min_images, max_size=5, unique=True))
    images = {"images/" + name: tuple(draw(st.lists(_text, max_size=2))) for name in names}

    artifacts = [ArtifactEntry(path="chapters.jsonl", size_bytes=size, sha256=chapters_sha)]
    for fixed in ("book.epub", "book.pkl"):
        if draw(st.booleans()):
            artifacts.append(
                ArtifactEntry(path=fixed, size_bytes=draw(st.integers(0, 2**40)), sha256=draw(_hex64))
            )
    for key in images:
        artifacts.append(ArtifactEntry(path=key, size_bytes=draw(st.integers(0, 2**40)), sha256=draw(_hex64)))
    artifacts = draw(st.permutations(artifacts))

    return BookManifest(
        format_version=FORMAT_VERSION,
        generation=draw(st.integers(1, MAX_GENERATION)),
        metadata=metadata,
        toc=toc,
        images=images,
        source_file=draw(_text),
        processed_at=draw(_text),
        book_version=draw(_text),
        chapters=tuple(chapters),
        chapters_size_bytes=size,
        chapters_sha256=chapters_sha,
        artifacts=tuple(artifacts),
        book_fingerprint=draw(_hex64),
        extractor_version=draw(st.integers(0, 2**31)),
    )


def example_manifest() -> BookManifest:
    """A fixed, consistent manifest: three chapters, two images, epub and pkl, a two-level TOC."""
    lines = [b'{"id":"c0"}', "第一章 café 🜁".encode("utf-8"), b"third"]
    chapters = []
    offset = 0
    for i, line in enumerate(lines):
        chapters.append(
            ChapterIndexEntry(
                id=f"c{i}",
                href=f"part{i}.html",
                order=i,
                offset_bytes=offset,
                length_bytes=len(line),
                sha256=_sha(line),
            )
        )
        offset += len(line) + 1
    whole = b"\n".join(lines) + b"\n"
    assert len(whole) == offset
    images = {"images/cover.png": ("OEBPS/cover.png", "cover.png"), "images/图.jpg": ("OEBPS/图.jpg",)}
    artifacts = (
        ArtifactEntry("chapters.jsonl", len(whole), _sha(whole)),
        ArtifactEntry("book.epub", 11, _sha(b"EPUB-")),
        ArtifactEntry("book.pkl", 7, _sha(b"PKL-")),
        ArtifactEntry("images/cover.png", 3, _sha(b"PNG")),
        ArtifactEntry("images/图.jpg", 4, _sha(b"JPG")),
    )
    toc = (
        ManifestTocEntry(
            title="Part I",
            href="part0.html",
            file_href="part0.html",
            anchor="",
            children=(ManifestTocEntry("Ch 1", "part1.html#a", "part1.html", "a", ()),),
        ),
    )
    return BookManifest(
        format_version=FORMAT_VERSION,
        generation=2,
        metadata=ManifestMetadata(
            title="Dracula",
            language="en",
            authors=("Bram Stoker",),
            description=None,
            publisher="Archibald",
            date=None,
            identifiers=("urn:x",),
            subjects=(),
        ),
        toc=toc,
        images=images,
        source_file="dracula.epub",
        processed_at="2026-10-08T00:00:00",
        book_version="3.0",
        chapters=tuple(chapters),
        chapters_size_bytes=len(whole),
        chapters_sha256=_sha(whole),
        artifacts=artifacts,
        book_fingerprint=EXAMPLE_FINGERPRINT,
        extractor_version=1,
    )


def example_json() -> dict[str, Any]:
    """The JSON object of :func:`example_manifest`, as the serialiser emits it."""
    obj = json.loads(manifest_to_bytes(example_manifest()))
    assert isinstance(obj, dict)
    return obj


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _artifact(obj: dict[str, Any], path: str) -> dict[str, Any]:
    for art in obj["artifacts"]:
        if art["path"] == path:
            return art
    raise AssertionError(f"no artifact {path!r} in {obj['artifacts']!r}")


def _parse_outcome(data: bytes) -> BookManifest | ManifestError:
    try:
        return manifest_from_bytes(data)
    except ManifestError as exc:
        return exc


# --------------------------------------------------------------------------- M-01 .. M-03: laws


@props(200)
@given(st_manifest())
def test_m01_round_trip_and_byte_determinism(m: BookManifest) -> None:
    b = manifest_to_bytes(m)
    assert isinstance(b, bytes)
    assert manifest_from_bytes(b) == m
    assert manifest_to_bytes(m) == b


@props(100)
@given(st_manifest())
def test_m02_canonical_form_is_a_fixed_point(m: BookManifest) -> None:
    b = manifest_to_bytes(m)
    assert manifest_to_bytes(manifest_from_bytes(b)) == b
    text = b.decode("utf-8")  # strict: raises if b is not valid UTF-8
    expected = json.dumps(json.loads(b), sort_keys=True, ensure_ascii=False, indent=2, separators=(",", ": "))
    assert b == (expected + "\n").encode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    for ch in m.metadata.title:
        if ord(ch) > 127:
            assert ch.encode("utf-8") in b, f"{ch!r} is escaped instead of raw UTF-8"


def test_m02_non_ascii_text_appears_raw() -> None:
    b = manifest_to_bytes(example_manifest())
    assert "images/图.jpg".encode("utf-8") in b
    assert b"\\u" not in b


def _json_paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    out = [prefix]
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_json_paths(v, prefix + (k,)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_json_paths(v, prefix + (i,)))
    return out


def _get(node: Any, path: tuple[Any, ...]) -> Any:
    for step in path:
        node = node[step]
    return node


@st.composite
def mutated_json(draw: Any) -> bytes:
    m = draw(st_manifest())
    obj = json.loads(manifest_to_bytes(m))
    kind = draw(st.sampled_from(["delete", "replace", "wrap"]))
    if kind == "wrap":
        return _dump([obj])
    paths = [p for p in _json_paths(obj) if p]
    path = draw(st.sampled_from(paths))
    parent = _get(obj, path[:-1])
    if kind == "delete":
        del parent[path[-1]]
    else:
        parent[path[-1]] = copy.deepcopy(draw(st.sampled_from([None, True, "x", [], {}, 1.5, -1])))
    return _dump(obj)


@props(300)
@given(st.one_of(st.binary(max_size=512), mutated_json()))
def test_m03_total_error_type(data: bytes) -> None:
    try:
        result = manifest_from_bytes(data)
    except ManifestError as exc:
        assert isinstance(exc, ValueError)
        assert isinstance(exc, bf.BookFormatError)
    else:
        assert isinstance(result, BookManifest)


# --------------------------------------------------------------------------- M-04 .. M-08: guards


def _snapshot() -> dict[str, Any]:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _required(cls_name: str) -> list[str]:
    return [f["name"] for f in _snapshot()["classes"][cls_name] if not f["has_default"]]


def _required_key_paths() -> list[tuple[Any, ...]]:
    paths: list[tuple[Any, ...]] = [(name,) for name in _required("BookManifest")]
    paths += [("metadata", name) for name in _required("ManifestMetadata")]
    paths += [("toc", 0, name) for name in _required("ManifestTocEntry")]
    paths += [("chapters", 0, name) for name in _required("ChapterIndexEntry")]
    paths += [("artifacts", 0, name) for name in _required("ArtifactEntry")]
    return paths


def test_m04_required_key_list_is_not_empty() -> None:
    paths = _required_key_paths()
    assert ("format_version",) in paths and ("artifacts", 0, "sha256") in paths
    assert len(paths) == 14 + 8 + 5 + 6 + 3


@props(150)
@given(st_manifest(min_toc=1, min_chapters=1), st.data())
def test_m04_every_required_key_is_required(m: BookManifest, data: st.DataObject) -> None:
    obj = json.loads(manifest_to_bytes(m))
    path = data.draw(st.sampled_from(_required_key_paths()))
    parent = _get(obj, path[:-1])
    assert path[-1] in parent, f"serialiser does not emit required key {path!r}"
    del parent[path[-1]]
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


_MISSING = object()


@pytest.mark.parametrize(
    "value",
    [FORMAT_VERSION + 1, FORMAT_VERSION + 1000, 0, -1, True, False, "1", 1.0, None, _MISSING],
    ids=lambda v: "missing" if v is _MISSING else repr(v),
)
def test_m05_format_version_rejects(value: Any) -> None:
    obj = example_json()
    if value is _MISSING:
        del obj["format_version"]
    else:
        obj["format_version"] = value
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


def test_m05_format_version_current_parses() -> None:
    obj = example_json()
    obj["format_version"] = FORMAT_VERSION
    parsed = manifest_from_bytes(_dump(obj))
    assert type(parsed.format_version) is int
    assert parsed.format_version == FORMAT_VERSION == 1


@pytest.mark.parametrize(
    "value",
    [MAX_GENERATION + 1, 0, -3, True, 1.0, "2", None, _MISSING],
    ids=lambda v: "missing" if v is _MISSING else repr(v),
)
def test_m06_generation_rejects(value: Any) -> None:
    obj = example_json()
    if value is _MISSING:
        del obj["generation"]
    else:
        obj["generation"] = value
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


@pytest.mark.parametrize("value", [1, MAX_GENERATION])
def test_m06_generation_bounds_parse(value: int) -> None:
    obj = example_json()
    obj["generation"] = value
    parsed = manifest_from_bytes(_dump(obj))
    assert type(parsed.generation) is int
    assert parsed.generation == value


_NUMERIC_SITES: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]], str]] = [
    ("order", lambda o: o["chapters"][0], "order"),
    ("offset_bytes", lambda o: o["chapters"][1], "offset_bytes"),
    ("length_bytes", lambda o: o["chapters"][2], "length_bytes"),
    ("size_bytes", lambda o: _artifact(o, "book.epub"), "size_bytes"),
]


@pytest.mark.parametrize("site", _NUMERIC_SITES, ids=lambda s: s[0])
@pytest.mark.parametrize("value", [True, -1, 1.5, "3"], ids=repr)
def test_m07_numeric_fields_reject_bool_negative_non_int(site: Any, value: Any) -> None:
    obj = example_json()
    _name, locate, key = site
    locate(obj)[key] = value
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


_BAD_SHAS = ["xyz", "a" * 63, "a" * 65, "A" * 64, "ABCDEF" + "0" * 58]


@pytest.mark.parametrize("bad", _BAD_SHAS, ids=["xyz", "hex63", "hex65", "upper64", "mixed64"])
@pytest.mark.parametrize("site", ["chapter", "artifact", "chapters_sha256"])
def test_m07_sha_must_be_lowercase_64_hex(site: str, bad: str) -> None:
    obj = example_json()
    if site == "chapter":
        obj["chapters"][0]["sha256"] = bad
    elif site == "artifact":
        _artifact(obj, "book.epub")["sha256"] = bad
    else:
        # Both redundant copies agree, so only the format rule can reject it.
        obj["chapters_sha256"] = bad
        _artifact(obj, "chapters.jsonl")["sha256"] = bad
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


def test_m07_chapters_size_bytes_bool_rejected() -> None:
    obj = example_json()
    obj["chapters_size_bytes"] = True
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


def test_m07_bool_size_rejected_even_when_redundant_copies_agree() -> None:
    """``True == 1`` in Python: a size field with no consistency rule can only be rejected by the type check."""
    obj = example_json()
    _artifact(obj, "book.pkl")["size_bytes"] = True
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


_KNOWN_KEYS = {f["name"] for fl in _snapshot()["classes"].values() for f in fl}


@props(100)
@given(
    st_manifest(min_chapters=1),
    st.sampled_from(["top", "metadata", "chapter", "artifact"]),
    st.text(min_size=1, max_size=10).filter(lambda k: k not in _KNOWN_KEYS),
    st.none() | st.booleans() | st.integers() | st.text(max_size=5) | st.lists(st.integers(), max_size=3),
)
def test_m08_unknown_keys_ignored(m: BookManifest, where: str, key: str, value: Any) -> None:
    obj = json.loads(manifest_to_bytes(m))
    target = {
        "top": obj,
        "metadata": obj["metadata"],
        "chapter": obj["chapters"][0],
        "artifact": obj["artifacts"][0],
    }[where]
    target[key] = value
    parsed = manifest_from_bytes(_dump(obj))
    assert parsed == m
    assert manifest_to_bytes(parsed) == manifest_to_bytes(m)


# --------------------------------------------------------------------------- M-09 / M-10: path guards

_BAD_PATHS = [
    "../x",
    "/etc/passwd",
    "images/../../x",
    "images/a/b.png",
    "images/",
    "",
    "unknown.bin",
    "images/..",
    "images/.",
    "./chapters.jsonl",
    "chapters.jsonl/",
    "images\\..\\x",
    "images/a\x00.png",
    "gen/1/book.epub",
]


def _set_artifact_path(obj: dict[str, Any], path: str) -> None:
    """Put ``path`` on the epub artifact; mirror it into images when it looks like one, so only the guard rejects."""
    _artifact(obj, "book.epub")["path"] = path
    if path.startswith("images/"):
        obj["images"][path] = []


def _set_image_key(obj: dict[str, Any], path: str) -> None:
    """Rename the cover image in both the images map and its artifact, keeping them consistent."""
    obj["images"][path] = obj["images"].pop("images/cover.png")
    _artifact(obj, "images/cover.png")["path"] = path


@pytest.mark.parametrize("bad", _BAD_PATHS, ids=repr)
@pytest.mark.parametrize("role", ["artifact", "image_key"])
def test_m09_path_guards(role: str, bad: str) -> None:
    obj = example_json()
    (_set_artifact_path if role == "artifact" else _set_image_key)(obj, bad)
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


@pytest.mark.parametrize("role", ["artifact", "image_key"])
def test_m09_control_unicode_image_path_parses(role: str) -> None:
    obj = example_json()
    if role == "artifact":
        del obj["images"]["images/图.jpg"]
        obj["artifacts"] = [a for a in obj["artifacts"] if a["path"] != "images/图.jpg"]
        _set_artifact_path(obj, "images/图.jpg")
    else:
        del obj["images"]["images/图.jpg"]
        obj["artifacts"] = [a for a in obj["artifacts"] if a["path"] != "images/图.jpg"]
        _set_image_key(obj, "images/图.jpg")
    parsed = manifest_from_bytes(_dump(obj))
    assert "images/图.jpg" in parsed.images
    assert "images/图.jpg" in {a.path for a in parsed.artifacts}


_LEGAL_SAMPLE = ["images/a", "images/图", "images/a.b", "images/..a", "images/.a"]


@props(300)
@given(st.text(alphabet="./\\a图\x00", max_size=12) | st.sampled_from(_LEGAL_SAMPLE))
def test_m10_accepted_paths_stay_inside_the_generation(path: str) -> None:
    obj = example_json()
    _set_artifact_path(obj, path)
    outcome = _parse_outcome(_dump(obj))
    if isinstance(outcome, ManifestError):
        return
    assert path in {a.path for a in outcome.artifacts}
    joined = posixpath.normpath(posixpath.join("/g", path))
    assert joined.startswith("/g/")
    assert path in LEGAL_FIXED or re.fullmatch(r"images/[^/\\\x00]+", path)
    assert path not in (".", "..") and posixpath.basename(path) not in (".", "..")
    assert posixpath.normpath(path) == path


def test_m10_backslash_name_is_rejected() -> None:
    obj = example_json()
    _set_artifact_path(obj, "images/\\")
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


# --------------------------------------------------------------------------- M-11: malformed bytes


def _malformed_inputs() -> list[tuple[str, bytes]]:
    valid = manifest_to_bytes(example_manifest())
    return [
        ("empty", b""),
        ("not-json", b"not json"),
        ("array", b"[1,2]"),
        ("null", b"null"),
        ("bad-utf8", b"\xff\xfe{}"),
        ("invalid-utf8-inside", b'{"title": "\xc3\x28"}'),
        ("truncated", valid[: len(valid) // 2]),
        ("bom", b"\xef\xbb\xbf" + valid),
        ("nan", b'{"format_version": NaN}'),
        ("deep", b"[" * 50_000 + b"]" * 50_000),
    ]


@pytest.mark.parametrize("data", [d for _, d in _malformed_inputs()], ids=[n for n, _ in _malformed_inputs()])
def test_m11_malformed_bytes(data: bytes) -> None:
    with pytest.raises(ManifestError):
        manifest_from_bytes(data)


def test_m11_valid_control_parses() -> None:
    assert manifest_from_bytes(manifest_to_bytes(example_manifest())) == example_manifest()


# --------------------------------------------------------------------------- M-12: consistency rules


def _r_size(o: dict[str, Any]) -> None:
    _artifact(o, "chapters.jsonl")["size_bytes"] += 1


def _r_sha(o: dict[str, Any]) -> None:
    _artifact(o, "chapters.jsonl")["sha256"] = "0" * 64


def _r_size_top(o: dict[str, Any]) -> None:
    o["chapters_size_bytes"] += 1


def _r_dup_path(o: dict[str, Any]) -> None:
    o["artifacts"].append(dict(_artifact(o, "book.epub")))


def _r_no_chapters_artifact(o: dict[str, Any]) -> None:
    o["artifacts"] = [a for a in o["artifacts"] if a["path"] != "chapters.jsonl"]


def _r_gap(o: dict[str, Any]) -> None:
    o["chapters"][1]["offset_bytes"] += 1


def _r_overlap(o: dict[str, Any]) -> None:
    o["chapters"][2]["offset_bytes"] -= 1


def _r_last_short(o: dict[str, Any]) -> None:
    o["chapters"][-1]["length_bytes"] += 1


def _r_offset0(o: dict[str, Any]) -> None:
    for ch in o["chapters"]:
        ch["offset_bytes"] += 1
    o["chapters_size_bytes"] += 1
    _artifact(o, "chapters.jsonl")["size_bytes"] += 1


def _r_dup_id(o: dict[str, Any]) -> None:
    o["chapters"][1]["id"] = o["chapters"][0]["id"]


def _r_image_without_artifact(o: dict[str, Any]) -> None:
    o["images"]["images/extra.png"] = []


def _r_artifact_without_image(o: dict[str, Any]) -> None:
    del o["images"]["images/cover.png"]


def _r_empty_book_nonzero_size(o: dict[str, Any]) -> None:
    o["chapters"] = []


_RULES = {
    "a-size": _r_size,
    "a-size-top": _r_size_top,
    "a'-sha": _r_sha,
    "b-dup-path": _r_dup_path,
    "c-no-chapters-artifact": _r_no_chapters_artifact,
    "d-gap": _r_gap,
    "d-overlap": _r_overlap,
    "d'-last-not-at-size": _r_last_short,
    "d''-offset0": _r_offset0,
    "d'-zero-chapters-nonzero-size": _r_empty_book_nonzero_size,
    "e-dup-id": _r_dup_id,
    "f-image-without-artifact": _r_image_without_artifact,
    "f'-artifact-without-image": _r_artifact_without_image,
}


@pytest.mark.parametrize("rule", list(_RULES.values()), ids=list(_RULES))
def test_m12_consistency_rules(rule: Callable[[dict[str, Any]], None]) -> None:
    obj = example_json()
    manifest_from_bytes(_dump(obj))  # control: the unmodified object parses
    rule(obj)
    with pytest.raises(ManifestError):
        manifest_from_bytes(_dump(obj))


@props(80)
@given(st_manifest(), st.data())
def test_m12p_single_field_perturbation_rejected(m: BookManifest, data: st.DataObject) -> None:
    options = ["chapters_size_bytes", "chapters_sha256"]
    if m.chapters:
        options += ["offset_bytes", "length_bytes"]
    if len(m.artifacts) >= 2:
        options.append("artifact_path")
    if m.images:
        options.append("image_key")
    which = data.draw(st.sampled_from(options))

    if which == "chapters_size_bytes":
        new = data.draw(st.integers(0, 2**40).filter(lambda v: v != m.chapters_size_bytes))
        bad = dataclasses.replace(m, chapters_size_bytes=new)
    elif which == "chapters_sha256":
        new_sha = data.draw(_hex64.filter(lambda v: v != m.chapters_sha256))
        bad = dataclasses.replace(m, chapters_sha256=new_sha)
    elif which in ("offset_bytes", "length_bytes"):
        i = data.draw(st.integers(0, len(m.chapters) - 1))
        old = getattr(m.chapters[i], which)
        new = data.draw(st.integers(0, 2**40).filter(lambda v: v != old))
        chapters = list(m.chapters)
        chapters[i] = dataclasses.replace(chapters[i], **{which: new})
        bad = dataclasses.replace(m, chapters=tuple(chapters))
    elif which == "artifact_path":
        i, j = data.draw(st.lists(st.integers(0, len(m.artifacts) - 1), min_size=2, max_size=2, unique=True))
        artifacts = list(m.artifacts)
        artifacts[i] = dataclasses.replace(artifacts[i], path=artifacts[j].path)
        bad = dataclasses.replace(m, artifacts=tuple(artifacts))
    else:
        old_key = data.draw(st.sampled_from(sorted(m.images)))
        new_name = data.draw(_safe_basename.filter(lambda n: "images/" + n not in m.images))
        images = dict(m.images)
        images["images/" + new_name] = images.pop(old_key)
        bad = dataclasses.replace(m, images=images)

    with pytest.raises(ManifestError):
        manifest_from_bytes(manifest_to_bytes(bad))


# --------------------------------------------------------------------------- M-13 .. M-15: schema snapshot


def _type_str(tp: Any) -> str:
    if tp is type(None):
        return "None"
    origin = typing.get_origin(tp)
    if origin is typing.Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        return " | ".join(_type_str(a) for a in typing.get_args(tp))
    if origin is not None:
        args = typing.get_args(tp)
        parts = ["..." if a is Ellipsis else _type_str(a) for a in args]
        return f"{origin.__name__}[{', '.join(parts)}]"
    if isinstance(tp, type):
        return tp.__name__
    return str(tp)


def schema_of(classes: dict[str, type], format_version: int) -> dict[str, Any]:
    """Walk the manifest dataclasses: (name, annotated type, has_default) in declaration order."""
    out: dict[str, Any] = {}
    for name, cls in classes.items():
        hints = typing.get_type_hints(cls, globalns=vars(bf))
        out[name] = [
            {
                "has_default": f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING,
                "name": f.name,
                "type": _type_str(hints[f.name]),
            }
            for f in dataclasses.fields(cls)
        ]
    return {"classes": out, "format_version": format_version}


def schema_mismatch(live: dict[str, Any], snapshot: dict[str, Any]) -> str | None:
    """None when equal; otherwise a message with the diff and the Q7 rule."""
    if live == snapshot:
        return None
    lines = []
    if live.get("format_version") != snapshot.get("format_version"):
        lines.append(
            f"format_version: live {live.get('format_version')!r} != snapshot {snapshot.get('format_version')!r}"
        )
    live_classes, snap_classes = live.get("classes", {}), snapshot.get("classes", {})
    for cls in sorted(set(live_classes) | set(snap_classes)):
        a, b = live_classes.get(cls), snap_classes.get(cls)
        if a != b:
            live_s, snap_s = json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False)
            lines.append(f"{cls}:\n  live:     {live_s}\n  snapshot: {snap_s}")
    return "manifest schema differs from the snapshot:\n" + "\n".join(lines) + "\n" + Q7_RULE


def _live_classes() -> dict[str, type]:
    return {name: getattr(bf, name) for name in SCHEMA_CLASS_NAMES}


def test_m13_live_schema_equals_snapshot() -> None:
    live = schema_of(_live_classes(), bf.FORMAT_VERSION)
    problem = schema_mismatch(live, _snapshot())
    assert problem is None, problem


def test_m13_schema_classes_are_frozen_dataclasses() -> None:
    for name, cls in _live_classes().items():
        assert dataclasses.is_dataclass(cls), name
        params = cls.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen, f"{name} must be frozen"


def test_m14_snapshot_version_and_excluded_fields() -> None:
    snap = _snapshot()
    assert snap["format_version"] == FORMAT_VERSION == 1, Q7_RULE
    names = [f["name"] for fields in snap["classes"].values() for f in fields]
    assert "book_uuid" not in names
    assert {"book_fingerprint", "extractor_version"} <= set(names)
    assert set(snap["classes"]) == set(SCHEMA_CLASS_NAMES)


def _mutated_artifact_entry(change: str) -> type:
    base = [("path", str), ("size_bytes", int), ("sha256", str)]
    if change == "added":
        fields: list[Any] = base + [("extra", str)]
    elif change == "removed":
        fields = base[:2]
    elif change == "renamed":
        fields = [("relpath", str), base[1], base[2]]
    else:  # retyped
        fields = [base[0], ("size_bytes", str), base[2]]
    return dataclasses.make_dataclass("ArtifactEntry", fields, frozen=True)


@pytest.mark.parametrize("change", ["added", "removed", "renamed", "retyped"])
def test_m15_snapshot_guard_is_not_vacuous(change: str) -> None:
    before = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    classes = _live_classes()
    classes["ArtifactEntry"] = _mutated_artifact_entry(change)
    problem = schema_mismatch(schema_of(classes, bf.FORMAT_VERSION), _snapshot())
    assert problem is not None
    assert "FORMAT_VERSION" in problem and "optional" in problem
    assert "ArtifactEntry" in problem
    assert hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == before


def test_m15_version_drift_is_reported() -> None:
    problem = schema_mismatch(schema_of(_live_classes(), bf.FORMAT_VERSION + 1), _snapshot())
    assert problem is not None and "format_version" in problem and "FORMAT_VERSION" in problem


# --------------------------------------------------------------------------- M-16: import hygiene


def test_m16_import_pulls_in_no_parser_modules() -> None:
    code = (
        "import sys, json\n"
        "import reader3_app.book_format\n"
        "print(json.dumps(sorted(m for m in ('reader3_app.reader3', 'ebooklib', 'bs4') if m in sys.modules)))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONSTARTUP"}
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]"


# --------------------------------------------------------------------------- M-17: exception hierarchy


def test_m17_exception_hierarchy() -> None:
    base = bf.BookFormatError
    assert base.__bases__ == (Exception,)
    for name in ("BookCorrupt", "ReadbackError", "LegacyStagingRefused"):
        cls = getattr(bf, name)
        assert issubclass(cls, base), name
        assert not issubclass(cls, ValueError), name
        assert not issubclass(cls, OSError), name
    for name in ("ManifestError", "ChapterReadError"):
        cls = getattr(bf, name)
        assert issubclass(cls, ValueError) and issubclass(cls, base), name
    cross = bf.CrossDeviceError
    assert issubclass(cross, OSError)
    assert not issubclass(cross, base)
    assert bf.CrossDeviceError("gen/3 is on another device").errno == errno.EXDEV
    assert isinstance(bf.CrossDeviceError("x", "/b/manifest.json"), OSError)
    assert bf.CrossDeviceError("x", "/b/manifest.json").filename == "/b/manifest.json"

    six = [getattr(bf, n) for n in (
        "BookCorrupt", "ReadbackError", "LegacyStagingRefused", "ManifestError", "ChapterReadError", "CrossDeviceError",
    )]
    for a in six:
        for b in six:
            if a is not b:
                assert not issubclass(a, b), f"{a.__name__} must not subclass {b.__name__}"


# --------------------------------------------------------------------------- constants (plan WI-1.1)


def test_constants() -> None:
    assert bf.FORMAT_VERSION == 1
    assert (bf.MANIFEST, bf.MANIFEST_TMP, bf.CHAPTERS) == ("manifest.json", "manifest.json.tmp", "chapters.jsonl")
    assert (bf.GEN_DIR, bf.EPUB, bf.PKL, bf.IMAGES) == ("gen", "book.epub", "book.pkl", "images")
    assert set(bf.ROOT_USER_DATA) == {"notes.json", "notes.json.lock", "ai_meta.json", "ai_conversations", "chroma_db"}
    assert len(bf.ROOT_USER_DATA) == 5
    assert bf.RETAIN_S == 300


# ---------------------------------------------------------- WI-1.10 B7: deep TOC nesting is a ManifestError


def _deep_toc_manifest(depth: int) -> bytes:
    """example_json with a single TOC chain ``depth`` entries deep (JSON nesting about 2 * depth + 2)."""
    obj = example_json()
    obj["toc"] = "__TOC__"
    opener = b'{"title":"t","href":"h","file_href":"h","anchor":"","children":['
    chain = opener * depth + b"]}" * depth
    return _dump(obj).replace(b'"__TOC__"', b"[" + chain + b"]")


def test_wi110_b7_deep_toc_is_manifest_error_never_recursion_error() -> None:
    """B7 (property over a depth sweep, S4, Level 1): every depth parses or raises ManifestError, nothing else.

    The sweep must include depths json.loads accepts but the dataclass parser cannot finish, so the guarded
    ``RecursionError`` -> ``ManifestError`` path is really taken, and shallow depths that round-trip.
    """
    outcomes: dict[int, str] = {}
    for depth in [*range(1, 60, 7), *range(60, 520, 20)]:
        raw = _deep_toc_manifest(depth)
        try:
            m = manifest_from_bytes(raw)
        except ManifestError as exc:
            outcomes[depth] = str(exc)
            continue
        chain_len, node = 0, m.toc
        while node:
            chain_len, node = chain_len + 1, node[0].children
        assert chain_len == depth
        outcomes[depth] = "ok"
    assert outcomes[1] == "ok"
    assert any(o == "manifest nesting too deep" for o in outcomes.values()), outcomes
    for depth, o in outcomes.items():
        assert o == "ok" or o == "manifest nesting too deep" or o.startswith("not JSON"), (depth, o)
    assert manifest_from_bytes(_deep_toc_manifest(1)) == manifest_from_bytes(_deep_toc_manifest(1))


# ---------------------------------------------------------------------- WI-2a.2: book_fingerprint / extractor_version
#
# Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md`` section "WI-2a.2" (M2-01 .. M2-04, M2-09).


@props(200)
@given(st_manifest())
def test_m2_01_round_trip_preserves_fingerprint_fields(m: BookManifest) -> None:
    """M2-01 (property, S4, Level 1): both new fields survive the round trip; a failure names the field."""
    obj = json.loads(manifest_to_bytes(m))
    assert obj["book_fingerprint"] == m.book_fingerprint
    assert obj["extractor_version"] == m.extractor_version
    back = manifest_from_bytes(manifest_to_bytes(m))
    assert back.book_fingerprint == m.book_fingerprint
    assert back.extractor_version == m.extractor_version
    assert back == m


def _corrupt_published_book(tmp_path: Path, edit: Callable[[dict[str, Any]], None]) -> Path:
    """A valid published book whose root manifest is then rewritten with ``edit`` applied."""
    book = setup_scenario("S1", tmp_path)
    assert classify(book, full=True) == "valid"
    obj = json.loads((book / bf.MANIFEST).read_bytes())
    edit(obj)
    (book / bf.MANIFEST).write_bytes(_dump(obj))
    return book


@pytest.mark.parametrize("key", NEW_FIELDS)
def test_m2_02_deleting_a_new_key_is_corrupt(tmp_path: Path, key: str) -> None:
    """M2-02 (guard, S2, Level 2 + 1): each new key is required; its absence is a named ManifestError / corrupt."""
    obj = example_json()
    assert key in obj, f"serialiser does not emit {key!r}"
    del obj[key]
    with pytest.raises(ManifestError, match="required key missing") as ei:
        manifest_from_bytes(_dump(obj))
    assert key in str(ei.value)
    assert (key,) in _required_key_paths()
    book = _corrupt_published_book(tmp_path, lambda o: o.pop(key))
    assert classify(book, full=False) == "corrupt"


_BAD_NEW_FIELD_VALUES: list[tuple[str, Any]] = [
    ("book_fingerprint", "A" * 64),
    ("book_fingerprint", "a" * 63),
    ("book_fingerprint", "a" * 65),
    ("book_fingerprint", 123),
    ("book_fingerprint", None),
    ("book_fingerprint", STALE_FINGERPRINT),
    ("extractor_version", -1),
    ("extractor_version", True),
    ("extractor_version", "1"),
    ("extractor_version", 1.5),
    ("extractor_version", None),
]


@pytest.mark.parametrize("key,value", _BAD_NEW_FIELD_VALUES, ids=lambda v: repr(v))
def test_m2_03_invalid_new_field_values_are_corrupt(tmp_path: Path, key: str, value: Any) -> None:
    """M2-03 (guard, S2, Level 2): a malformed fingerprint or extractor version is a ManifestError naming it."""
    obj = example_json()
    obj[key] = value
    with pytest.raises(ManifestError) as ei:
        manifest_from_bytes(_dump(obj))
    assert key in str(ei.value)
    book = _corrupt_published_book(tmp_path, lambda o: o.__setitem__(key, value))
    assert classify(book, full=False) == "corrupt"


def test_m2_04_extractor_version_zero_is_accepted() -> None:
    """M2-04 (boundary, S3, Level 1): 0 is the reserved "unknown" extractor version and parses."""
    obj = example_json()
    obj["extractor_version"] = 0
    parsed = manifest_from_bytes(_dump(obj))
    assert type(parsed.extractor_version) is int
    assert parsed.extractor_version == 0
    assert parsed.book_fingerprint == EXAMPLE_FINGERPRINT


def test_m2_09_snapshot_records_new_fields_as_required() -> None:
    """M2-09 (success, S1, Level 1): both new fields are required in the snapshot; the version stays 1."""
    fields = {f["name"]: f for f in _snapshot()["classes"]["BookManifest"]}
    assert fields["book_fingerprint"] == {"has_default": False, "name": "book_fingerprint", "type": "str"}
    assert fields["extractor_version"] == {"has_default": False, "name": "extractor_version", "type": "int"}
    assert _snapshot()["format_version"] == FORMAT_VERSION == 1
    assert "book_uuid" not in fields
    live = {f.name: f for f in dataclasses.fields(BookManifest)}
    for name in NEW_FIELDS:
        assert name in live, f"BookManifest has no field {name!r}"
        assert live[name].default is dataclasses.MISSING and live[name].default_factory is dataclasses.MISSING
