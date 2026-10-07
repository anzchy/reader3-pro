"""018 WI-6, unit U2: the export-only conversation reader (matrix cases R1 .. R10).

``conversations.read_conversation_threads(directory) -> (threads, unreadable_stems)``.

**Law (L-part).** Let S be the stems of the regular ``*.json`` files in ``directory``
(minus any that vanish between listing and open). The readable threads' ids and the
unreadable stems partition S: disjoint, no duplicates. Each thread equals
``json.loads(bytes)`` of its file. Readable means UTF-8 JSON, a top-level object and a
``conversation_id`` that ``_safe_conversation_id`` accepts. A per-file ``OSError`` other
than ``FileNotFoundError`` is unreadable. A missing or non-directory path is
``([], [])``; a directory-level error during listing propagates.

Every R-case starts with ``fn = cr()``: before the reader exists that is a ``RED:``
failure, never an ``AttributeError``. R8 is a regression guard on the *existing* silent
reader and is green at red by design.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from delete_world import (
    ABSENT,
    CID_3,
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    D_OLD,
    U,
    ZERO_UUID,
    conv,
    conv_payload,
    put_file,
)
from export_world import EACCES_SKIP, cr, deny, same_dir
from reader3_app.ai import conversations

SUMMARY_KEYS = {"conversation_id", "provider", "model", "created_at", "last_updated", "message_count", "title"}


def _payload_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _no_cid_payload() -> bytes:
    body = conv_payload(ZERO_UUID, D_MID, "missing cid")
    del body["conversation_id"]
    return _payload_bytes(body)


#: The bad file per R3 kind: ``(file name, bytes)``. ``file_eacces`` is a *valid* file made
#: unreadable by mode bits (set up separately).
BAD_KINDS: Dict[str, Tuple[str, bytes]] = {
    "syntax": (f"{ZERO_UUID}.json", b"{trunc"),
    "top_array": (f"{ZERO_UUID}.json", b"[]"),
    "non_utf8": (f"{ZERO_UUID}.json", b"\xff\xfe\x00bad"),
    "traversal_cid": (f"{ZERO_UUID}.json", _payload_bytes(conv_payload(ZERO_UUID, D_MID, "t", conversation_id="../../x"))),
    "missing_cid": (f"{ZERO_UUID}.json", _no_cid_payload()),
    "int_cid": (f"{ZERO_UUID}.json", _payload_bytes(conv_payload(ZERO_UUID, D_MID, "t", conversation_id=7))),
    "empty_file": (f"{ZERO_UUID}.json", b""),
    "bad_filename": ("notauuid.json", b"{x"),
}

#: R8: the kinds the existing silent reader skips today (see the module docstring of the
#: report: for traversal_cid / missing_cid / int_cid the old reader still lists a summary,
#: so "== [CID_FRESH]" would be false at HEAD for them -- they are not part of R8).
SILENT_SKIP_KINDS = ["syntax", "top_array", "non_utf8", "empty_file", "bad_filename"]


def _seed_r3(d: Path, kind: str) -> Tuple[Path, bytes]:
    d.mkdir(parents=True, exist_ok=True)
    name, payload = conv(CID_FRESH, D_MID, "fresh")
    put_file(d / name, payload)
    bad_name, bad = BAD_KINDS[kind]
    path = put_file(d / bad_name, bad)
    return path, bad


# --------------------------------------------------------------------------- R1


def test_r1_missing_path_or_non_directory_is_empty(tmp_path: Path) -> None:
    """R1: a missing path and a regular file are both ``([], [])``."""
    fn = cr()
    threads, unreadable = fn(str(tmp_path / "nope"))
    assert (threads, unreadable) == ([], [])
    f = put_file(tmp_path / "f.json", b"{}")
    threads, unreadable = fn(str(f))
    assert (threads, unreadable) == ([], [])


# --------------------------------------------------------------------------- R2


def test_r2_valid_files_are_exact_raw_dicts_unknown_keys_kept(tmp_path: Path) -> None:
    """R2: each thread is ``json.loads`` of its file, unknown keys included."""
    fn = cr()
    files: Dict[str, bytes] = {}
    for name, payload in (conv(CID_FRESH, D_MID, "a"), conv(CID_COLLIDE, D_NEW, "b")):
        files[name] = payload
    extra = conv_payload(CID_3, D_OLD, "c")
    extra["x_future_field"] = {"nested": [1]}
    files[f"{CID_3}.json"] = _payload_bytes(extra)
    for name, payload in files.items():
        put_file(tmp_path / name, payload)

    threads, unreadable = fn(str(tmp_path))

    key = lambda t: str(t.get("conversation_id"))  # noqa: E731
    assert sorted(threads, key=key) == sorted((json.loads(b) for b in files.values()), key=key)
    assert unreadable == []
    assert [t for t in threads if t["conversation_id"] == CID_3][0]["x_future_field"] == {"nested": [1]}
    assert {n: (tmp_path / n).read_bytes() for n in files} == files


# --------------------------------------------------------------------------- R3


@pytest.mark.parametrize("kind", list(BAD_KINDS))
def test_r3_bad_file_is_listed_siblings_still_read(tmp_path: Path, kind: str) -> None:
    """R3: the bad file's stem is in ``unreadable``; the valid sibling is still a thread."""
    fn = cr()
    path, bad = _seed_r3(tmp_path / "convs", kind)
    threads, unreadable = fn(str(tmp_path / "convs"))
    expected_stem = "notauuid" if kind == "bad_filename" else ZERO_UUID
    assert unreadable == [expected_stem]
    assert [t["conversation_id"] for t in threads] == [CID_FRESH]
    assert path.read_bytes() == bad


@EACCES_SKIP
def test_r3_file_eacces_is_unreadable_not_silent(tmp_path: Path) -> None:
    """R3 row file_eacces: a per-file PermissionError is unreadable, never skipped silently."""
    fn = cr()
    d = tmp_path / "convs"
    name, payload = conv(CID_FRESH, D_MID, "fresh")
    put_file(d / name, payload)
    zname, zpayload = conv(ZERO_UUID, D_MID, "locked")
    zpath = put_file(d / zname, zpayload)
    with deny(zpath):
        threads, unreadable = fn(str(d))
    assert unreadable == [ZERO_UUID]
    assert [t["conversation_id"] for t in threads] == [CID_FRESH]


# --------------------------------------------------------------------------- R4


def test_r4_non_json_files_and_subdirectories_are_ignored(tmp_path: Path) -> None:
    """R4: only regular ``*.json`` files directly in the directory are considered."""
    fn = cr()
    name, payload = conv(CID_FRESH, D_MID, "fresh")
    put_file(tmp_path / name, payload)
    put_file(tmp_path / "README", b"hello")
    put_file(tmp_path / f"{CID_3}.json.bak", conv(CID_3, D_MID, "bak")[1])
    put_file(tmp_path / f"{CID_3}.JSON", conv(CID_3, D_MID, "upper")[1])
    put_file(tmp_path / "sub" / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_MID, "nested")[1])
    (tmp_path / f"{CID_COLLIDE}.json").mkdir()

    threads, unreadable = fn(str(tmp_path))

    assert threads == [conv_payload(CID_FRESH, D_MID, "fresh")]
    assert unreadable == []


# --------------------------------------------------------------------------- R5 / R6


def _wrap_listing(monkeypatch: pytest.MonkeyPatch, target: Path, on_list) -> List[str]:
    """Wrap ``os.listdir`` and ``os.scandir``: for ``target``, run ``on_list(real, path)``."""
    real_listdir = os.listdir
    real_scandir = os.scandir
    hits: List[str] = []

    def listdir(path: Any = ".") -> Any:
        if same_dir(path, target):
            hits.append("listdir")
            return on_list(real_listdir, path, "listdir")
        return real_listdir(path)

    def scandir(path: Any = ".") -> Any:
        if same_dir(path, target):
            hits.append("scandir")
            return on_list(real_scandir, path, "scandir")
        return real_scandir(path)

    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(os, "scandir", scandir)
    return hits


def test_r5_directory_vanishing_during_listing_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R5: the directory is removed as it is listed -> ``FileNotFoundError`` propagates."""
    fn = cr()
    d = tmp_path / "convs"
    name, payload = conv(CID_FRESH, D_MID, "fresh")
    put_file(d / name, payload)

    def on_list(real, path, _kind):
        shutil.rmtree(d, ignore_errors=True)
        return real(path)

    hits = _wrap_listing(monkeypatch, d, on_list)
    with pytest.raises(FileNotFoundError):
        fn(str(d))
    assert hits, "positive control: the reader never listed the directory through os.listdir/os.scandir"


class _ScandirStandIn:
    """What ``os.scandir`` returns, over an already-materialised list of entries."""

    def __init__(self, entries: List[Any]) -> None:
        self._entries = entries

    def __enter__(self) -> "_ScandirStandIn":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def __iter__(self):
        return iter(self._entries)

    def close(self) -> None:
        return None


def test_r6_single_file_vanishing_after_listing_is_omitted_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6 (W6-5): a file listed, then gone before open, is neither a thread nor unreadable."""
    fn = cr()
    d = tmp_path / "convs"
    for name, payload in (conv(CID_FRESH, D_MID, "fresh"), conv(CID_3, D_MID, "third")):
        put_file(d / name, payload)
    victim = d / f"{CID_3}.json"

    def on_list(real, path, kind):
        if kind == "listdir":
            names = list(real(path))
            if victim.exists():
                victim.unlink()
            return names
        with real(path) as it:
            entries = list(it)
        if victim.exists():
            victim.unlink()
        return _ScandirStandIn(entries)

    hits = _wrap_listing(monkeypatch, d, on_list)
    threads, unreadable = fn(str(d))
    assert hits, "positive control: the reader never listed the directory through os.listdir/os.scandir"
    assert [t["conversation_id"] for t in threads] == [CID_FRESH]
    assert unreadable == []


# --------------------------------------------------------------------------- R7

R7_KINDS = [
    "valid",
    "syntax",
    "top_array",
    "non_utf8",
    "traversal_cid",
    "missing_cid",
    "int_cid",
    "empty",
    "non_json_name",
    "subdir",
]


def _r7_build(d: Path, entries: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Build one directory; return the expected partition."""
    valid: Dict[str, Dict[str, Any]] = {}
    bad: List[str] = []
    for stem, kind in entries:
        path = d / f"{stem}.json"
        if kind == "valid":
            payload = conv_payload(stem, D_MID, f"text-{stem}")
            path.write_bytes(_payload_bytes(payload))
            valid[stem] = payload
        elif kind == "syntax":
            path.write_bytes(b"{trunc")
            bad.append(stem)
        elif kind == "top_array":
            path.write_bytes(b"[]")
            bad.append(stem)
        elif kind == "non_utf8":
            path.write_bytes(b"\xff\xfe\x00bad")
            bad.append(stem)
        elif kind == "traversal_cid":
            path.write_bytes(_payload_bytes(conv_payload(stem, D_MID, "t", conversation_id="../../x")))
            bad.append(stem)
        elif kind == "missing_cid":
            body = conv_payload(stem, D_MID, "m")
            del body["conversation_id"]
            path.write_bytes(_payload_bytes(body))
            bad.append(stem)
        elif kind == "int_cid":
            path.write_bytes(_payload_bytes(conv_payload(stem, D_MID, "i", conversation_id=7)))
            bad.append(stem)
        elif kind == "empty":
            path.write_bytes(b"")
            bad.append(stem)
        elif kind == "non_json_name":
            (d / f"{stem}.txt").write_bytes(_payload_bytes(conv_payload(stem, D_MID, "txt")))
        elif kind == "subdir":
            path.mkdir()
        else:  # pragma: no cover - strategy typo
            raise AssertionError(kind)
    return {"valid": valid, "bad": bad}


_R7_ENTRIES = st.lists(st.uuids(), unique=True, max_size=8).flatmap(
    lambda stems: st.tuples(*[st.tuples(st.just(str(s)), st.sampled_from(R7_KINDS)) for s in stems])
)


def test_r7_partition_law_over_generated_directories() -> None:
    """R7 (S5): threads' ids and unreadable stems partition the ``*.json`` regular-file stems."""
    fn = cr()

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(entries=_R7_ENTRIES)
    def check(entries: Tuple[Tuple[str, str], ...]) -> None:
        d = Path(tempfile.mkdtemp(prefix="r7-"))
        try:
            expected = _r7_build(d, list(entries))
            threads, unreadable = fn(str(d))
            ids = [t["conversation_id"] for t in threads]
            assert len(ids) == len(set(ids)), ids
            assert len(unreadable) == len(set(unreadable)), unreadable
            assert not (set(ids) & set(unreadable))
            json_stems = {p.name[:-5] for p in d.iterdir() if p.name.endswith(".json") and p.is_file()}
            assert set(ids) | set(unreadable) == json_stems
            assert set(ids) == set(expected["valid"])
            assert set(unreadable) == set(expected["bad"])
            for t in threads:
                assert t == expected["valid"][t["conversation_id"]]
        finally:
            shutil.rmtree(d, ignore_errors=True)

    check()


# --------------------------------------------------------------------------- R8


@pytest.mark.parametrize("kind", SILENT_SKIP_KINDS)
def test_r8_the_silent_reader_is_unchanged(tmp_path: Path, kind: str) -> None:
    """R8: ``_list_conversations_from_dir`` and ``list_conversations_combined`` still skip
    silently (no exception, only the valid id) -- green at red by design (regression guard)."""
    books = tmp_path / "books"
    d = books / "a_data" / "ai_conversations"
    _seed_r3(d, kind)

    summaries = conversations._list_conversations_from_dir(str(d))
    assert [s["conversation_id"] for s in summaries] == [CID_FRESH]
    assert all(set(s) == SUMMARY_KEYS for s in summaries)

    combined = conversations.list_conversations_combined(str(books), book_folder="a_data", book_uuid=U)
    assert [s["conversation_id"] for s in combined] == [CID_FRESH]


# --------------------------------------------------------------------------- R9


@pytest.mark.parametrize(
    "lu",
    [None, "", 7, ABSENT],
    ids=["null", "empty", "int", "absent"],
)
def test_r9_odd_last_updated_values_are_readable(tmp_path: Path, lu: Any) -> None:
    """R9: ``last_updated`` is not validated by the reader."""
    fn = cr()
    name, payload = conv(ZERO_UUID, lu, "odd")
    put_file(tmp_path / name, payload)
    threads, unreadable = fn(str(tmp_path))
    assert threads == [json.loads(payload)]
    assert unreadable == []


# --------------------------------------------------------------------------- R10


@EACCES_SKIP
def test_r10_unreadable_directory_raises_permission_error(tmp_path: Path) -> None:
    """R10 (R-4): a chmod-0 directory raises ``PermissionError``; never ``([], [])``."""
    fn = cr()
    d = tmp_path / "convs"
    name, payload = conv(CID_FRESH, D_MID, "fresh")
    put_file(d / name, payload)
    with deny(d):
        with pytest.raises(PermissionError):
            fn(str(d))
