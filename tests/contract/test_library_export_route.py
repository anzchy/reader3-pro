"""018 WI-6: ``GET /api/library/export`` (matrix cases E1 .. E22, E16b, H2, H3).

**Law (U1).**
- L-cons: every enumerated book becomes exactly one readable entry, one error entry, or
  is skipped (it vanished).
- L-order: entries follow ``list_book_ids``.
- L-ro: the export is read-only and idempotent (no lock, no write, no uuid mint).
- L-sec: no chapter text and no secret, in either mode.
- L-cont: the default entry is the include entry minus ``conversations`` and minus the
  conversation-component errors.
- L-dedupe: one copy per cid, the copy with the greatest ``last_updated`` key
  (non-strings key as ``""``).
- L-err: under include, the ``conversation_id``s in ``component_errors`` are exactly the
  unreadable stems of both reachable sources (set semantics).
- L-grammar: ``include`` is exactly one value, ``conversations`` case-insensitively.

**Law (U4, H2/H3).** For a book with a valid ``ai_meta.json``, the export entry projected
to the WI-4 fields equals its ``GET /api/library`` entry; error entries are equal.

Every case that expects 200 goes through ``export()`` / ``library()``, which assert the
status first, so before the route exists the red is ``405 == 200`` (the DELETE route's
path matches) -- never a KeyError. Every spy is installed through ``_require`` (a
``RED:`` failure when the name is missing).

Books are created *after* the client has started, so the startup uuid scan never mints
into a fixture whose ``ai_meta.json`` is the point of the case.
"""

from __future__ import annotations

import collections
import errno
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import bookdir
import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from book_lock_workers import Holder, _interpose_acquire_counting
from delete_world import (
    ABSENT,
    CID_3,
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    D_OLD,
    U,
    V,
    W,
    ZERO_UUID,
    World,
    conv,
    conv_payload,
    make_book,
    new_world,
    put_file,
    raw_conv,
    seat_resolver,
)
from export_world import (
    CONTENT_DISPOSITION,
    EACCES_SKIP,
    EXPORT_KEYS,
    EXPORT_READER,
    EXPORT_ROUTE,
    INCLUDE_DETAIL,
    by_cid,
    cids,
    counting,
    deny,
    entry_of,
    export,
    library,
    notes_json,
    notes_record,
    project,
    raising_for,
    rehome,
    same_dir,
    stat_tree,
    valid_notes,
    vanish_wrapper,
    walk_keys,
    without,
    xe,
)
from reader3_app import book_lock, book_store, notes_service, search_service
from reader3_app.ai import conversations
from reader3_app.web import server
from reader3_app.web.routers import library_books

from conftest import BOOK_ID, UNIQUE_TERM
from conftest import World as ContractWorld

BASE_URL = "http://127.0.0.1"
SECRET = "sk-fixture-not-a-real-key"
CONV_ERR = {"component": "conversations"}
NOTES_ERR = {"component": "annotations"}
STORAGES = ["per_book", "project_root", "both"]
MODES = [None, "conversations"]
MODE_IDS = ["default", "include"]


def conv_err(cid: str) -> Dict[str, str]:
    return {"component": "conversations", "conversation_id": cid}


# --------------------------------------------------------------------------- fixture


@dataclass
class ExportWorld:
    w: World
    client: TestClient
    prefs: Dict[str, Any]

    @property
    def books(self) -> Path:
        return self.w.books

    @property
    def R(self) -> Path:
        return self.w.R

    def settings_with(self, *, root_dir: Optional[str] = None, storage: Optional[str] = None) -> None:
        """Change what the patched ``load_ai_settings`` returns (it reads ``prefs`` per call)."""
        if root_dir is not None:
            self.prefs["conversation_project_root_dir"] = root_dir
        if storage is not None:
            self.prefs["conversation_disk_storage"] = storage


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def ew(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ExportWorld]:
    """A books dir under ``proj/``; the conversation root setting is ``convroot`` (= ``w.R``)."""
    w = new_world(tmp_path / "proj")
    monkeypatch.setattr(server, "BOOKS_DIR", str(w.books))
    seat_resolver(monkeypatch, w.books)
    prefs: Dict[str, Any] = {"conversation_disk_storage": "per_book", "conversation_project_root_dir": "convroot"}

    def _settings(*_a: Any, **_kw: Any) -> Dict[str, Any]:
        from reader3_app.ai.config import default_settings_dict

        settings_ = default_settings_dict()
        settings_["preferences"] = {**(settings_.get("preferences") or {}), **prefs}
        return settings_

    monkeypatch.setattr(server, "load_ai_settings", _settings)
    _clear_caches()
    try:
        with TestClient(app=server.app, base_url=BASE_URL) as client:
            yield ExportWorld(w=w, client=client, prefs=prefs)
    finally:
        _clear_caches()


# --------------------------------------------------------------------------- helpers


def _put_conversation(client: TestClient, book_uuid: str, cid: str, text: str) -> None:
    resp = client.put(
        f"/api/ai/conversations/{book_uuid}/{cid}",
        json={
            "provider": "anthropic",
            "model": "m",
            "created_at": "2026-08-01T00:00:00Z",
            "last_updated": D_MID,
            "messages": [{"id": f"m-{cid[:8]}", "role": "user", "content": text, "timestamp": D_MID, "metadata": {}}],
        },
    )
    assert resp.status_code == 200, f"precondition: PUT conversation -> {resp.status_code} {resp.text[:300]}"


def _post_note(client: TestClient) -> None:
    resp = client.post(
        f"/api/notes/{BOOK_ID}/0",
        json={"type": "note", "color": "green", "quote": "traveller", "note_text": "seeded"},
    )
    assert resp.status_code == 201, f"precondition: POST note -> {resp.status_code} {resp.text[:300]}"


def _conv_error_stems(entry: Dict[str, Any]) -> List[str]:
    return [
        c["conversation_id"]
        for c in entry["component_errors"]
        if c.get("component") == "conversations" and "conversation_id" in c
    ]


def _a_dir(ew: ExportWorld) -> Path:
    return ew.books / "a_data"


def _per_book(ew: ExportWorld, folder: str) -> Path:
    return ew.books / folder / "ai_conversations"


def _warnings_naming(caplog: pytest.LogCaptureFixture, needle: str) -> List[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING and needle in r.getMessage()]


def _bytes_or_none(path: Path) -> Optional[bytes]:
    return path.read_bytes() if path.exists() else None


# =========================================================================== E1


def test_e1_default_export_has_no_conversations_even_when_they_exist(world: ContractWorld) -> None:
    """E1: default mode -> attachment JSON, envelope exactly {"books"}, no conversations at any depth."""
    _put_conversation(world.client, world.book_uuid, CID_FRESH, "CONVMARKER-default")
    r = export(world.client)
    assert r.headers["content-type"].split(";")[0].strip() == "application/json"
    assert r.headers["content-disposition"] == CONTENT_DISPOSITION
    body = r.json()
    assert set(body) == {"books"}
    assert len(body["books"]) == 1
    assert "conversations" not in set(walk_keys(body))
    assert "CONVMARKER-default" not in r.text
    assert body["books"][0]["component_errors"] == []


# =========================================================================== E2


def test_e2_readable_entry_is_library_entry_plus_annotations(world: ContractWorld) -> None:
    """E2: export entry == GET /api/library entry + annotations + component_errors."""
    _post_note(world.client)
    exp = export(world.client).json()
    lib = library(world.client).json()
    annotations = [a.to_dict() for a in notes_service.load_annotations(server.BOOKS_DIR, BOOK_ID)]
    assert exp["books"][0] == {**lib["books"][0], "annotations": annotations, "component_errors": []}
    assert exp["books"][0]["annotations"][0]["quote"] == "traveller"
    assert exp["books"][0]["cover_url"] == f"/read/{BOOK_ID}/images/cover.jpg"


# =========================================================================== E3


def _e3_tree(ew: ExportWorld) -> None:
    make_book(
        ew.books,
        "a_data",
        title="Alpha",
        body="AAAA alpha",
        book_uuid=U,
        convs=[conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide-book")],
    )
    put_file(ew.R / U / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_OLD, "collide-root-old")[1])
    put_file(ew.R / U / f"{CID_3}.json", conv(CID_3, D_MID, "root-only")[1])
    make_book(ew.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V, convs=[conv(CID_COLLIDE, D_OLD, "b-book-old")])
    put_file(ew.R / V / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_NEW, "b-root-new")[1])


def test_e3_include_exports_both_sources_deduped_newer_wins_in_every_storage_mode(ew: ExportWorld) -> None:
    """E3 (W6-2): raw full threads from both sources, newer copy wins either way, for all storages."""
    _e3_tree(ew)
    bodies: Dict[str, Any] = {}
    for mode in STORAGES:
        ew.settings_with(storage=mode)
        body = export(ew.client, "conversations").json()
        a = entry_of(body, "a_data")
        b = entry_of(body, "b_data")
        assert by_cid(a["conversations"]) == by_cid(
            [
                conv_payload(CID_FRESH, D_MID, "fresh"),
                conv_payload(CID_COLLIDE, D_NEW, "collide-book"),
                conv_payload(CID_3, D_MID, "root-only"),
            ]
        ), mode
        assert b["conversations"] == [conv_payload(CID_COLLIDE, D_NEW, "b-root-new")], mode
        assert a["component_errors"] == [] and b["component_errors"] == [], mode
        for e in body["books"]:
            e["conversations"] = by_cid(e["conversations"])
        bodies[mode] = body
    assert bodies["per_book"] == bodies["project_root"] == bodies["both"]


# =========================================================================== E4 / E5


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e4_no_chapter_text_in_the_body(world: ContractWorld, include: Optional[str]) -> None:
    """E4: the chapter's unique term never appears, in either mode."""
    _post_note(world.client)
    _put_conversation(world.client, world.book_uuid, CID_FRESH, "CONVMARKER-e4")
    r = export(world.client, include)
    assert UNIQUE_TERM.lower() not in r.text.lower()


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e5_no_secret_in_the_body(world: ContractWorld, include: Optional[str]) -> None:
    """E5: no API key value, no api-key-like key, no ``providers`` key -- at any depth."""
    _put_conversation(world.client, world.book_uuid, CID_FRESH, "CONVMARKER-e5")
    r = export(world.client, include)
    body = r.json()
    assert SECRET not in r.text
    keys = list(walk_keys(body))
    assert not any(re.fullmatch(r"api[_-]?key", k, re.I) for k in keys), keys
    assert "providers" not in keys


# =========================================================================== E6


def _corrupt_pkl(book_dir: Path, kind: str) -> None:
    pkl = book_dir / "book.pkl"
    if kind == "garbage":
        bookdir.break_book_pkl(book_dir)
    elif kind == "empty":
        pkl.write_bytes(b"")
    elif kind == "truncated":
        bookdir.truncate_book_pkl(book_dir, keep=32)
    elif kind == "directory":
        pkl.unlink()
        pkl.mkdir()
    else:  # pragma: no cover - parametrize typo
        raise AssertionError(kind)


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("kind", ["garbage", "empty", "truncated", "directory"])
def test_e6_unreadable_pickle_is_the_exact_error_entry_and_nothing_else_is_read(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, kind: str, include: Optional[str]
) -> None:
    """E6: a corrupt book.pkl -> {"book_id", "error": "unreadable"}; no notes / conversations /
    uuid read for it, and no ai_meta.json minted."""
    make_book(ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "f")])
    c_dir = make_book(ew.books, "c_data", book_uuid=ABSENT, convs=[raw_conv("x.json", b"{trunc")])
    notes_json(c_dir, b"[]")
    _corrupt_pkl(c_dir, kind)

    n = counting(monkeypatch, notes_service, "load_annotations")
    c = counting(monkeypatch, conversations, EXPORT_READER)
    u = counting(monkeypatch, book_lock, "read_book_uuid")

    body = export(ew.client, include).json()

    n_a = [a for a in n if a[1] == "a_data"]
    u_a = [a for a in u if a[1] == "a_data"]
    c_a = [a for a in c if "a_data" in str(a[0])]
    assert n_a, "positive control: notes_service.load_annotations was never called for a_data"
    assert u_a, "positive control: book_lock.read_book_uuid was never called for a_data"
    if include:
        assert c_a, f"positive control: conversations.{EXPORT_READER} was never called for a_data"
    assert entry_of(body, "c_data") == {"book_id": "c_data", "error": "unreadable"}
    assert [a for a in n if a[1] == "c_data"] == []
    assert [a for a in u if a[1] == "c_data"] == []
    assert [a for a in c if "c_data" in str(a[0])] == []
    assert not (c_dir / "ai_meta.json").exists()


# =========================================================================== E7

E7_BOOK_VANISH = ["metadata", "notes_before", "notes_race", "convs_before", "after_reads", "convs_raise"]
E7_SOURCE_VANISH = {
    "root_dir_vanish": CID_3,
    "book_convdir_vanish": CID_FRESH,
    "root_dir_vanish_raise": CID_3,
    "book_convdir_vanish_raise": CID_FRESH,
}


def _fnf(path: Path):
    return lambda: FileNotFoundError(errno.ENOENT, "gone", str(path))


def _notes_race(path: Path):
    def make() -> BaseException:
        exc = notes_service.NotesFileError(f"{path} could not be read (gone)")
        exc.__cause__ = FileNotFoundError(errno.ENOENT, "gone", str(path))
        return exc

    return make


def _e7_inject(ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, row: str) -> List[Any]:
    b_dir = ew.books / "b_data"
    b_convs = b_dir / "ai_conversations"
    b_root = ew.R / V
    is_b_meta = lambda *a: a[0] == "b_data"  # noqa: E731
    is_b_notes = lambda *a: a[1] == "b_data"  # noqa: E731
    is_b_book_src = lambda *a: same_dir(a[0], b_convs)  # noqa: E731
    is_b_root_src = lambda *a: same_dir(a[0], b_root)  # noqa: E731
    is_b_any_src = lambda *a: same_dir(a[0], b_convs) or same_dir(a[0], b_root)  # noqa: E731
    if row == "metadata":
        return vanish_wrapper(monkeypatch, book_store, "load_book_metadata", b_dir, only_if=is_b_meta)
    if row == "notes_before":
        return vanish_wrapper(monkeypatch, notes_service, "load_annotations", b_dir, only_if=is_b_notes)
    if row == "notes_race":
        return vanish_wrapper(
            monkeypatch, notes_service, "load_annotations", b_dir, only_if=is_b_notes, raise_=_notes_race(b_dir / "notes.json")
        )
    if row == "convs_before":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_dir, only_if=is_b_book_src)
    if row == "after_reads":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_dir, when="after", only_if=is_b_any_src, nth=2)
    if row == "convs_raise":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_dir, only_if=is_b_book_src, raise_=_fnf(b_convs))
    if row == "root_dir_vanish":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_root, only_if=is_b_root_src)
    if row == "book_convdir_vanish":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_convs, only_if=is_b_book_src)
    if row == "root_dir_vanish_raise":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_root, only_if=is_b_root_src, raise_=_fnf(b_root))
    if row == "book_convdir_vanish_raise":
        return vanish_wrapper(monkeypatch, conversations, EXPORT_READER, b_convs, only_if=is_b_book_src, raise_=_fnf(b_convs))
    raise AssertionError(row)  # pragma: no cover


@pytest.mark.parametrize("row", E7_BOOK_VANISH + list(E7_SOURCE_VANISH))
def test_e7_vanished_book_is_skipped_vanished_source_dir_is_not(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, row: str
) -> None:
    """E7: a book removed mid-export is skipped; a conversation *source dir* removed mid-export
    only loses that source's threads (no error, book kept)."""
    make_book(ew.books, "a_data", title="Alpha", body="AAAA alpha", book_uuid=U)
    b_dir = make_book(ew.books, "b_data", title="Beta", body="BBBB beta", book_uuid=V, convs=[conv(CID_FRESH, D_MID, "b-book")])
    notes_json(b_dir, valid_notes("b_data", 1))
    put_file(ew.R / V / f"{CID_3}.json", conv(CID_3, D_MID, "b-root")[1])
    make_book(ew.books, "c_data", title="Gamma", body="CCCC gamma", book_uuid=W)

    base = export(ew.client, "conversations").json()
    base_by_id = {e["book_id"]: e for e in base["books"]}
    assert sorted(cids(base_by_id["b_data"]["conversations"])) == sorted([CID_FRESH, CID_3])

    fired = _e7_inject(ew, monkeypatch, row)
    body = export(ew.client, "conversations").json()
    assert fired, f"positive control: the {row} injection never fired"
    ids = [e["book_id"] for e in body["books"]]

    if row in E7_BOOK_VANISH:
        assert ids == ["a_data", "c_data"]
        assert entry_of(body, "a_data") == base_by_id["a_data"]
        assert entry_of(body, "c_data") == base_by_id["c_data"]
        return

    assert ids == ["a_data", "b_data", "c_data"]
    assert entry_of(body, "a_data") == base_by_id["a_data"]
    assert entry_of(body, "c_data") == base_by_id["c_data"]
    gone = E7_SOURCE_VANISH[row]
    base_b = base_by_id["b_data"]
    expected_b = {**base_b, "conversations": by_cid([t for t in base_b["conversations"] if t["conversation_id"] != gone])}
    b = dict(entry_of(body, "b_data"))
    b["conversations"] = by_cid(b["conversations"])
    assert b == expected_b
    assert b["component_errors"] == []


# =========================================================================== E8 / E9

E8_NOTES = {
    "syntax": b"{trunc",
    "top_array": b"[]",
    "schema_999": b'{"schema_version":999,"annotations":[]}',
    "schema_bool": b'{"schema_version":true,"annotations":[]}',
    "schema_str": b'{"schema_version":"1","annotations":[]}',
    "annotations_not_list": b'{"schema_version":1,"annotations":{}}',
    "bad_record": b'{"schema_version":1,"annotations":[{"id":1}]}',
    # 审计 20261007 #4 / #17（FX37-4）：非 UTF-8 是 UnicodeDecodeError，不是 JSONDecodeError；
    # 下面三条是 json.loads 读得进、JSONResponse 却渲染不出的记录（孤立代理项、非有限数）。
    "non_utf8": b"\xff\xfe\x00bad",
}


def _notes_with(**fields: str) -> bytes:
    """One otherwise valid record whose ``fields`` are spliced in as raw JSON text."""
    record = json.dumps(notes_record("a_data"))
    for key, raw in fields.items():
        record = record[:-1] + f', "{key}": {raw}' + "}"
    return b'{"schema_version":1,"annotations":[' + record.encode("ascii") + b"]}"


E8_NOTES.update(
    {
        "lone_surrogate": _notes_with(note_text='"\\ud800"'),
        "nan_position": _notes_with(position="NaN"),
        "overflow_position": _notes_with(position="1e309"),
    }
)


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("kind", list(E8_NOTES))
def test_e8_bad_notes_file_is_null_plus_component_error_file_untouched(
    ew: ExportWorld, kind: str, include: Optional[str]
) -> None:
    """E8: every NotesFileError branch -> annotations null + [{"component": "annotations"}]."""
    a_dir = make_book(ew.books, "a_data", book_uuid=U)
    path = notes_json(a_dir, E8_NOTES[kind])
    entry = entry_of(export(ew.client, include).json(), "a_data")
    lib = entry_of(library(ew.client).json(), "a_data")
    assert entry["annotations"] is None
    assert entry["component_errors"] == [NOTES_ERR]
    assert project(entry) == lib
    assert path.read_bytes() == E8_NOTES[kind]


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("kind", ["absent", "json_null", "empty_annotations"])
def test_e9_notes_boundaries_are_not_errors(ew: ExportWorld, kind: str, include: Optional[str]) -> None:
    """E9: absent / ``null`` / empty annotations list -> [] and no component error."""
    a_dir = make_book(ew.books, "a_data", book_uuid=U)
    if kind == "json_null":
        notes_json(a_dir, b"null")
    elif kind == "empty_annotations":
        notes_json(a_dir, b'{"schema_version":1,"annotations":[]}')
    entry = entry_of(export(ew.client, include).json(), "a_data")
    assert entry["annotations"] == []
    assert entry["component_errors"] == []
    if kind == "absent":
        assert not (a_dir / "notes.json").exists()


# =========================================================================== E10


def _no_cid() -> bytes:
    body = conv_payload(ZERO_UUID, D_MID, "t")
    del body["conversation_id"]
    return json.dumps(body).encode()


E10_BODIES = {
    "syntax": b"{trunc",
    "top_array": b"[]",
    "non_utf8": b"\xff\xfe\x00bad",
    "traversal_cid": json.dumps(conv_payload(ZERO_UUID, D_MID, "t", conversation_id="../../x")).encode(),
    "missing_cid": _no_cid(),
    "int_cid": json.dumps(conv_payload(ZERO_UUID, D_MID, "t", conversation_id=7)).encode(),
}


def _raw_conv_body(**fields: str) -> bytes:
    """A valid ZERO_UUID thread with ``fields`` spliced in as raw JSON text (FX37-5)."""
    text = json.dumps(conv_payload(ZERO_UUID, D_MID, "t"))
    for key, raw in fields.items():
        text = text[:-1] + f', "{key}": {raw}' + "}"
    return text.encode("utf-8")


#: Audit #5 / #19 (FX37-5): parse fine, but ``JSONResponse`` would refuse to render them.
E10_BODIES.update(
    {
        "nan": _raw_conv_body(x="NaN"),
        "infinity": _raw_conv_body(x="Infinity"),
        "neg_infinity": _raw_conv_body(x="-Infinity"),
        "overflow_1e309": _raw_conv_body(x="1e309"),
        "lone_surrogate": _raw_conv_body(title='"\\ud800"'),
        "nested_message_surrogate": _raw_conv_body(messages='[{"role": "user", "content": "\\udfff"}]'),
    }
)


def _e10_base(ew: ExportWorld) -> Path:
    a_dir = make_book(ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
    put_file(ew.R / U / f"{CID_3}.json", conv(CID_3, D_MID, "root")[1])
    return a_dir


@pytest.mark.parametrize("kind", list(E10_BODIES))
@pytest.mark.parametrize("source", ["per_book", "project_root"])
def test_e10_unreadable_conversation_file_is_listed_never_skipped(ew: ExportWorld, source: str, kind: str) -> None:
    """E10 (W6-9): a bad file in either source -> one per-stem component error; the rest exported."""
    a_dir = _e10_base(ew)
    bad_dir = a_dir / "ai_conversations" if source == "per_book" else ew.R / U
    bad = put_file(bad_dir / f"{ZERO_UUID}.json", E10_BODIES[kind])

    entry = entry_of(export(ew.client, "conversations").json(), "a_data")
    assert entry["component_errors"] == [conv_err(ZERO_UUID)]
    assert sorted(cids(entry["conversations"])) == sorted([CID_FRESH, CID_3])
    assert bad.read_bytes() == E10_BODIES[kind]

    default = entry_of(export(ew.client).json(), "a_data")
    assert default["component_errors"] == []


@pytest.mark.parametrize("row", ["bad_book_good_root", "good_book_bad_root", "bad_both"])
def test_e10_cross_source_unreadable_rows(ew: ExportWorld, row: str) -> None:
    """E10 cross-source rows: a readable copy never suppresses the other copy's error; the
    error is listed once even when both copies are bad."""
    a_dir = _e10_base(ew)
    book_path = a_dir / "ai_conversations" / f"{ZERO_UUID}.json"
    root_path = ew.R / U / f"{ZERO_UUID}.json"
    if row == "bad_book_good_root":
        put_file(book_path, b"{trunc")
        put_file(root_path, conv(ZERO_UUID, D_OLD, "root-good")[1])
    elif row == "good_book_bad_root":
        put_file(book_path, conv(ZERO_UUID, D_OLD, "book-good")[1])
        put_file(root_path, b"{trunc")
    else:
        put_file(book_path, b"{trunc")
        put_file(root_path, b"{trunc")

    entry = entry_of(export(ew.client, "conversations").json(), "a_data")
    assert entry["component_errors"] == [conv_err(ZERO_UUID)]
    zero = [t for t in entry["conversations"] if t["conversation_id"] == ZERO_UUID]
    if row == "bad_book_good_root":
        assert zero == [conv_payload(ZERO_UUID, D_OLD, "root-good")]
    elif row == "good_book_bad_root":
        assert zero == [conv_payload(ZERO_UUID, D_OLD, "book-good")]
    else:
        assert zero == []
    assert sorted(cids(entry["conversations"])) == sorted([CID_FRESH, CID_3] + ([] if row == "bad_both" else [ZERO_UUID]))


# =========================================================================== E11


@pytest.mark.parametrize("lu", [None, "", 7, ABSENT], ids=["null", "empty", "int", "absent"])
def test_e11_odd_but_readable_last_updated_is_exported_not_an_error(ew: ExportWorld, lu: Any) -> None:
    """E11: null / "" / int / absent last_updated are readable; non-strings key as "" in the dedupe."""
    make_book(ew.books, "a_data", book_uuid=U, convs=[conv(ZERO_UUID, lu, "odd"), conv(CID_FRESH, D_MID, "fresh")])
    with_twin = lu is None or lu == 7
    if with_twin:
        put_file(ew.R / U / f"{ZERO_UUID}.json", conv(ZERO_UUID, D_OLD, "root-old")[1])

    entry = entry_of(export(ew.client, "conversations").json(), "a_data")
    assert entry["component_errors"] == []
    zero = conv_payload(ZERO_UUID, D_OLD, "root-old") if with_twin else conv_payload(ZERO_UUID, lu, "odd")
    assert by_cid(entry["conversations"]) == by_cid([zero, conv_payload(CID_FRESH, D_MID, "fresh")])


# =========================================================================== E12a / E12b

E12_OK_WITH = ["include=conversations", "include=CONVERSATIONS", "include=Conversations"]
E12_OK_WITHOUT: List[Optional[str]] = [None, "foo=bar"]
E12_BAD = [
    "include=",
    "include=conv",
    "include=true",
    "include=conversations,annotations",
    "include=conversations&include=conversations",
    "include=conversations&include=",
    "include=%20conversations",
]


@pytest.mark.parametrize("raw", E12_OK_WITH)
def test_e12a_include_grammar_200_with_conversations(world: ContractWorld, raw: str) -> None:
    """E12a: case-insensitive ``conversations`` turns conversations on."""
    entry = export(world.client, raw_query=raw).json()["books"][0]
    assert "conversations" in entry


@pytest.mark.parametrize("raw", E12_OK_WITHOUT, ids=["no_query", "foo_bar"])
def test_e12a_include_grammar_200_without_conversations(world: ContractWorld, raw: Optional[str]) -> None:
    """E12a: no ``include`` (unrelated params ignored) -> no conversations key."""
    entry = export(world.client, raw_query=raw).json()["books"][0]
    assert "conversations" not in entry


@pytest.mark.parametrize("raw", E12_BAD)
def test_e12a_include_grammar_400(world: ContractWorld, raw: str) -> None:
    """E12a: everything else is 400 with the exact detail."""
    r = world.client.get(f"{EXPORT_ROUTE}?{raw}")
    assert r.status_code == 400, (r.status_code, r.text[:300])
    assert r.json() == {"detail": INCLUDE_DETAIL}


_E12B_VALUES = st.text(max_size=20) | st.sampled_from(
    ["conversations", "CONVERSATIONS", "conversationS", "converſations", "conversations\u0000"]
)


def test_e12b_include_grammar_law_over_arbitrary_text(ew: ExportWorld) -> None:
    """E12b (S5): status == 200 iff v.lower() == "conversations", else 400 + exact detail."""
    export(ew.client)  # fails fast (and named) before the route exists

    @settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(v=_E12B_VALUES)
    def check(v: str) -> None:
        r = ew.client.get(EXPORT_ROUTE, params={"include": v})
        expected = 200 if v.lower() == "conversations" else 400
        assert r.status_code == expected, (v, r.status_code, r.text[:200])
        if expected == 200:
            assert "books" in r.json()
        else:
            assert r.json() == {"detail": INCLUDE_DETAIL}

    check()


# =========================================================================== E13


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e13_enumeration_failure_is_a_500(ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, include: Optional[str]) -> None:
    """E13 (D19): the enumeration raising is the one 500 (positive control: it was reached)."""
    make_book(ew.books, "a_data", book_uuid=U)
    hits: List[Any] = []

    def boom(*args: Any, **kwargs: Any) -> List[str]:
        hits.append(args)
        raise OSError(errno.EIO, "boom")

    monkeypatch.setattr(search_service, "list_book_ids", boom)
    monkeypatch.setattr(library_books, "list_book_ids", boom)
    monkeypatch.setattr(xe(), "list_book_ids", boom, raising=False)
    client = TestClient(app=server.app, base_url=BASE_URL, raise_server_exceptions=False)
    url = EXPORT_ROUTE if include is None else f"{EXPORT_ROUTE}?include={include}"
    r = client.get(url)
    assert r.status_code == 500, (r.status_code, r.text[:300])
    assert hits, "positive control: the export enumerated through a binding this test did not patch"


@EACCES_SKIP
@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e13_contrast_every_per_book_fault_at_once_is_still_200(ew: ExportWorld, include: Optional[str]) -> None:
    """E13 contrast row: E6 + E8 + E10 + E16b faults together never make a 500."""
    make_book(ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
    c_dir = make_book(ew.books, "c_data", book_uuid=ABSENT)
    bookdir.break_book_pkl(c_dir)
    d_dir = make_book(ew.books, "d_data", book_uuid=V)
    notes_json(d_dir, b"{trunc")
    make_book(ew.books, "e_data", book_uuid=W, convs=[raw_conv(f"{ZERO_UUID}.json", b"{trunc")])
    f_dir = make_book(ew.books, "f_data", book_uuid=ABSENT, convs=[conv(CID_FRESH, D_MID, "locked")])
    with deny(f_dir / "ai_conversations"):
        body = export(ew.client, include).json()
    assert [e["book_id"] for e in body["books"]] == ["a_data", "c_data", "d_data", "e_data", "f_data"]


# =========================================================================== E14


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e14_no_lock_no_write_no_mint_and_works_under_a_held_ex_lock(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, include: Optional[str]
) -> None:
    """E14 (W6-1): export takes no book lock, writes nothing, mints no uuid -- and so is
    unaffected by another process holding the book's EX lock."""
    a_dir = make_book(ew.books, "a_data", title="Alpha", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
    put_file(ew.R / U / f"{CID_3}.json", conv(CID_3, D_MID, "root")[1])
    notes_json(a_dir, valid_notes("a_data", 1))
    b_dir = make_book(ew.books, "b_data", title="Beta", book_uuid=ABSENT)

    with Holder(str(ew.books), "a_data", book_lock.EXCLUSIVE, "delete", str(tmp_path)), Holder(
        str(ew.books), "b_data", book_lock.EXCLUSIVE, "delete", str(tmp_path)
    ):
        snap = (stat_tree(ew.books), stat_tree(ew.R))
        with _interpose_acquire_counting(monkeypatch, lambda: None) as calls:
            body = export(ew.client, include).json()
            again = export(ew.client, include).json()
        after = (stat_tree(ew.books), stat_tree(ew.R))

    assert calls == []
    assert body == again
    a = entry_of(body, "a_data")
    assert a["title"] == "Alpha" and a["book_uuid"] == U
    assert len(a["annotations"]) == 1
    assert a["component_errors"] == []
    if include:
        assert by_cid(a["conversations"]) == by_cid([conv_payload(CID_FRESH, D_MID, "fresh"), conv_payload(CID_3, D_MID, "root")])
    assert entry_of(body, "b_data")["book_uuid"] is None
    assert not (b_dir / "ai_meta.json").exists()
    assert after == snap


# =========================================================================== E15


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("noise", [False, True], ids=["empty", "noise_only"])
def test_e15_empty_library(ew: ExportWorld, noise: bool, include: Optional[str]) -> None:
    """E15: no ``*_data`` books -> 200 {"books": []} with the attachment header."""
    if noise:
        put_file(ew.books / "notes.txt", b"not a book")
        (ew.books / "junk").mkdir()
        (ew.books / ".locks").mkdir()
    r = export(ew.client, include)
    assert r.json() == {"books": []}
    assert r.headers["content-disposition"] == CONTENT_DISPOSITION


# =========================================================================== E16 / E16b


@pytest.mark.parametrize("row", ["absolute_rel", "dotdot_rel", "root_eacces", "absent_dir"])
def test_e16_project_root_unresolvable_or_unreadable(ew: ExportWorld, tmp_path: Path, row: str) -> None:
    """E16 (W6-4): root unresolvable / unreadable -> per-book threads + a whole-source error;
    an absent R/{uuid} is not an error."""
    if row == "root_eacces" and os.geteuid() == 0:
        pytest.skip("root ignores mode bits")
    make_book(ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
    fresh_only = [conv_payload(CID_FRESH, D_MID, "fresh")]
    if row == "absolute_rel":
        put_file(tmp_path / "abs" / U / f"{CID_3}.json", conv(CID_3, D_MID, "DECOY-abs")[1])
        ew.settings_with(root_dir=str(tmp_path / "abs"))
    elif row == "dotdot_rel":
        put_file(ew.w.root / "escape" / U / f"{CID_3}.json", conv(CID_3, D_MID, "DECOY-dotdot")[1])
        ew.settings_with(root_dir="../escape")

    if row == "root_eacces":
        put_file(ew.R / U / f"{CID_3}.json", conv(CID_3, D_MID, "root")[1])
        with deny(ew.R / U):
            inc = entry_of(export(ew.client, "conversations").json(), "a_data")
            dflt = entry_of(export(ew.client).json(), "a_data")
    else:
        inc = entry_of(export(ew.client, "conversations").json(), "a_data")
        dflt = entry_of(export(ew.client).json(), "a_data")

    assert inc["conversations"] == fresh_only
    assert inc["component_errors"] == ([] if row == "absent_dir" else [CONV_ERR])
    assert dflt["component_errors"] == []


@EACCES_SKIP
@pytest.mark.parametrize("row", ["dir_eacces", "file_eacces"])
def test_e16b_per_book_source_unreadable_entry_kept_error_reported(ew: ExportWorld, row: str) -> None:
    """E16b (R-4): a per-book PermissionError keeps the entry (and the root threads) and is
    reported -- whole-source for the directory, per-stem for one file."""
    if row == "dir_eacces":
        a_dir = make_book(ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")])
        put_file(ew.R / U / f"{CID_3}.json", conv(CID_3, D_MID, "root")[1])
        target = a_dir / "ai_conversations"
    else:
        a_dir = make_book(
            ew.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_MID, "locked")]
        )
        target = a_dir / "ai_conversations" / f"{CID_COLLIDE}.json"
    notes_json(a_dir, valid_notes("a_data", 1))
    lib = entry_of(library(ew.client).json(), "a_data")

    with deny(target):
        inc = entry_of(export(ew.client, "conversations").json(), "a_data")
        dflt = entry_of(export(ew.client).json(), "a_data")

    assert project(inc) == lib
    assert len(inc["annotations"]) == 1
    if row == "dir_eacces":
        assert inc["conversations"] == [conv_payload(CID_3, D_MID, "root")]
        assert inc["component_errors"] == [CONV_ERR]
    else:
        assert inc["conversations"] == [conv_payload(CID_FRESH, D_MID, "fresh")]
        assert inc["component_errors"] == [conv_err(CID_COLLIDE)]
    assert dflt["component_errors"] == []


# =========================================================================== E17 / E18


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("raw_uuid", ["not-a-uuid", "../convroot-escape"])
def test_e17_malformed_uuid_is_unresolvable_for_the_project_root(
    ew: ExportWorld, caplog: pytest.LogCaptureFixture, raw_uuid: str, include: Optional[str]
) -> None:
    """E17 (W6-1, W6-4, R-1): a malformed uuid is exported as null + WARNING and is never used
    as a path segment (the decoy under R/<raw> is not exported)."""
    a_dir = make_book(ew.books, "a_data", book_uuid={"book_uuid": raw_uuid}, convs=[conv(CID_FRESH, D_MID, "fresh")])
    put_file(ew.R / "not-a-uuid" / f"{CID_3}.json", conv(CID_3, D_MID, "DECOY-must-not-export")[1])
    put_file(ew.R / raw_uuid / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_MID, "DECOY-must-not-export")[1])
    meta = (a_dir / "ai_meta.json").read_bytes()

    caplog.set_level(logging.WARNING)
    caplog.clear()
    r = export(ew.client, include)
    entry = entry_of(r.json(), "a_data")

    assert entry["book_uuid"] is None
    warned = _warnings_naming(caplog, "a_data")
    if include:
        assert entry["conversations"] == [conv_payload(CID_FRESH, D_MID, "fresh")]
        assert entry["component_errors"] == [CONV_ERR]
        assert "DECOY-must-not-export" not in r.text
        assert len(warned) >= 1, [rec.getMessage() for rec in caplog.records]
    else:
        assert entry["component_errors"] == []
        assert len(warned) == 1, [rec.getMessage() for rec in caplog.records]
    assert (a_dir / "ai_meta.json").read_bytes() == meta


E18_ROWS = {
    "absent": ABSENT,
    "corrupt_bytes": b"{nope",
    "non_dict": b"[1]",
    "non_str": {"book_uuid": 7},
    "valid_control": U,
}


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
@pytest.mark.parametrize("row", list(E18_ROWS))
def test_e18_read_book_uuid_none_is_null_plus_warning_file_untouched(
    ew: ExportWorld, caplog: pytest.LogCaptureFixture, row: str, include: Optional[str]
) -> None:
    """E18 (W6-1, R-2): every ``read_book_uuid -> None`` branch -> null + WARNING, ai_meta.json
    untouched; under include a present-but-unreadable ai_meta.json is a whole-source error."""
    a_dir = make_book(ew.books, "a_data", book_uuid=E18_ROWS[row])
    meta_path = a_dir / "ai_meta.json"
    before = _bytes_or_none(meta_path)

    caplog.set_level(logging.WARNING)
    caplog.clear()
    entry = entry_of(export(ew.client, include).json(), "a_data")
    warned = _warnings_naming(caplog, "a_data")

    if row == "valid_control":
        assert entry["book_uuid"] == U
        assert warned == [], [rec.getMessage() for rec in warned]
        assert entry["component_errors"] == []
    else:
        assert entry["book_uuid"] is None
        assert len(warned) >= 1, [rec.getMessage() for rec in caplog.records]
        if include and row != "absent":
            assert entry["component_errors"] == [CONV_ERR]
        else:
            assert entry["component_errors"] == []
    assert _bytes_or_none(meta_path) == before


# =========================================================================== layouts (E19 .. E21, H2)

POOL = [CID_FRESH, CID_COLLIDE, CID_3, ZERO_UUID]
LU_CHOICES: List[Any] = [D_OLD, D_MID, D_NEW, None, ABSENT, 7]
BAD_BODIES = [b"{trunc", b"[]", E10_BODIES["traversal_cid"]]
VANISH = {"vanish_meta", "vanish_notes", "vanish_convs"}
IMAGE_NAMES = ["cover.jpg", "title.png", "a.gif", "page01.jpeg"]


def _book_spec(kinds: List[str], *, uuid_always: bool) -> Any:
    return st.fixed_dictionaries(
        {
            "kind": st.sampled_from(kinds),
            "has_uuid": st.just(True) if uuid_always else st.booleans(),
            "notes": st.sampled_from(["absent", "valid", "bad"]),
            "book_threads": st.dictionaries(st.sampled_from(POOL), st.sampled_from(LU_CHOICES), max_size=3),
            "root_threads": st.dictionaries(st.sampled_from(POOL), st.sampled_from(LU_CHOICES), max_size=3),
            "book_bad": st.none() | st.sampled_from(POOL),
            "root_bad": st.none() | st.sampled_from(POOL),
            "bad_body": st.sampled_from(BAD_BODIES),
            "images": st.lists(st.sampled_from(IMAGE_NAMES), unique=True, max_size=2),
        }
    )


def layouts(kinds: List[str], *, uuid_always: bool = False) -> Any:
    names = st.lists(st.from_regex(r"[a-z]{1,6}_data", fullmatch=True), unique=True, max_size=6)
    books = names.flatmap(
        lambda ns: st.tuples(*[st.tuples(st.just(n), _book_spec(kinds, uuid_always=uuid_always)) for n in ns])
    )
    return st.tuples(books, st.sampled_from(STORAGES))


def _uuid_for(n: int) -> str:
    return f"{n + 1:08x}-0000-4000-8000-{n + 1:012x}"


def _build_layout(proj: Path, books_spec: Tuple[Tuple[str, Dict[str, Any]], ...]) -> Dict[str, Dict[str, Any]]:
    """Build the tree; return, per book: kind, uuid, unreadable stems per source, token."""
    books = proj / "books"
    R = proj / "convroot"
    books.mkdir(parents=True, exist_ok=True)
    model: Dict[str, Dict[str, Any]] = {}
    for n, (name, spec) in enumerate(books_spec):
        uuid_ = _uuid_for(n) if spec["has_uuid"] else None
        files: Dict[str, bytes] = {}
        for cid, lu in spec["book_threads"].items():
            files[f"{cid}.json"] = conv(cid, lu, f"{name}-book-{cid}")[1]
        if spec["book_bad"] is not None:
            files[f"{spec['book_bad']}.json"] = spec["bad_body"]
        if spec["kind"] == "vanish_convs" and not files:
            files[f"{CID_FRESH}.json"] = conv(CID_FRESH, D_MID, f"{name}-book-keep")[1]
        bdir = make_book(
            books,
            name,
            title=f"T{n}",
            body=f"CHAPTERTOKEN{n}",
            book_uuid=uuid_ if uuid_ else ABSENT,
            convs=sorted(files.items()),
        )
        if spec["kind"] == "corrupt_pkl":
            bookdir.break_book_pkl(bdir)
        if spec["notes"] == "valid":
            notes_json(bdir, valid_notes(name, 1 + n % 2))
        elif spec["notes"] == "bad":
            notes_json(bdir, b"{trunc")
        for img in spec["images"]:
            put_file(bdir / "images" / img, b"img")
        root_bad: set = set()
        if uuid_:
            for cid, lu in spec["root_threads"].items():
                put_file(R / uuid_ / f"{cid}.json", conv(cid, lu, f"{name}-root-{cid}")[1])
            if spec["root_bad"] is not None:
                put_file(R / uuid_ / f"{spec['root_bad']}.json", spec["bad_body"])
                root_bad = {spec["root_bad"]}
        model[name] = {
            "kind": spec["kind"],
            "uuid": uuid_,
            "book_bad": {spec["book_bad"]} if spec["book_bad"] is not None else set(),
            "root_bad": root_bad,
            "token": f"CHAPTERTOKEN{n}",
            "dir": bdir,
        }
    return model


def _install_vanish(mp: pytest.MonkeyPatch, model: Dict[str, Dict[str, Any]]) -> None:
    for name, m in model.items():
        bdir = m["dir"]
        if m["kind"] == "vanish_meta":
            vanish_wrapper(mp, book_store, "load_book_metadata", bdir, only_if=lambda *a, _n=name: a[0] == _n)
        elif m["kind"] == "vanish_notes":
            vanish_wrapper(mp, notes_service, "load_annotations", bdir, only_if=lambda *a, _n=name: a[1] == _n)
        elif m["kind"] == "vanish_convs":
            src = bdir / "ai_conversations"
            vanish_wrapper(mp, conversations, EXPORT_READER, bdir, only_if=lambda *a, _s=src: same_dir(a[0], _s))


def _prefs(storage: str) -> Dict[str, Any]:
    return {"conversation_disk_storage": storage, "conversation_project_root_dir": "convroot"}


LAYOUT_SETTINGS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


# =========================================================================== E19


def test_e19_conservation_order_read_only_no_text_error_conservation(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E19 (S5, main law) over generated libraries, both modes."""
    export(ew.client)  # fails fast (and named) before the route exists

    @LAYOUT_SETTINGS
    @given(layout=layouts(["ok", "corrupt_pkl", "vanish_meta", "vanish_notes", "vanish_convs"]))
    def check(layout: Any) -> None:
        books_spec, storage = layout
        proj = Path(tempfile.mkdtemp(prefix="e19-"))
        try:
            with monkeypatch.context() as mp:
                model = _build_layout(proj, books_spec)
                books, R = proj / "books", proj / "convroot"
                rehome(mp, books, _prefs(storage))
                start = search_service.list_book_ids(str(books))
                expected_ids = [b for b in start if model[b]["kind"] not in VANISH]
                vanish_names = [b for b in model if model[b]["kind"] in VANISH]
                before = (without(stat_tree(books), vanish_names), stat_tree(R))
                _install_vanish(mp, model)

                runs = {}
                for mode in ["conversations", "conversations", None, None]:
                    runs.setdefault(mode, []).append(export(ew.client, mode))
                for name in vanish_names:
                    assert not model[name]["dir"].exists(), f"positive control: {name} never vanished"

                for mode, (r1, r2) in runs.items():
                    assert r1.content == r2.content, mode
                    body = r1.json()
                    ids = [e["book_id"] for e in body["books"]]
                    assert ids == expected_ids, (mode, ids, expected_ids)
                    for n_ in range(len(books_spec)):
                        assert f"CHAPTERTOKEN{n_}" not in r1.text
                    for e in body["books"]:
                        m = model[e["book_id"]]
                        if m["kind"] == "corrupt_pkl":
                            assert e == {"book_id": e["book_id"], "error": "unreadable"}
                            continue
                        assert "error" not in e
                        keys = set(EXPORT_KEYS) | ({"conversations"} if mode else set())
                        assert set(e) == keys, (mode, sorted(e))
                        if mode:
                            stems = _conv_error_stems(e)
                            assert set(stems) == m["book_bad"] | m["root_bad"], (e["book_id"], stems)
                            dicts = [json.dumps(c, sort_keys=True) for c in e["component_errors"]]
                            assert len(dicts) == len(set(dicts)), e["component_errors"]
                after = (without(stat_tree(books), vanish_names), stat_tree(R))
                assert after == before
        finally:
            _clear_caches()
            shutil.rmtree(proj, ignore_errors=True)

    check()


# =========================================================================== E20


def _strip_conversation_data(entry: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in entry.items() if k != "conversations"}
    if "component_errors" in out:
        out["component_errors"] = [c for c in out["component_errors"] if c.get("component") != "conversations"]
    return out


def test_e20_containment_include_only_adds_conversation_data(ew: ExportWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    """E20 (S5): default entry == include entry minus conversations and conversation errors."""
    export(ew.client)  # fails fast (and named) before the route exists

    @LAYOUT_SETTINGS
    @given(layout=layouts(["ok", "corrupt_pkl"]))
    def check(layout: Any) -> None:
        books_spec, storage = layout
        proj = Path(tempfile.mkdtemp(prefix="e20-"))
        try:
            with monkeypatch.context() as mp:
                _build_layout(proj, books_spec)
                rehome(mp, proj / "books", _prefs(storage))
                d = export(ew.client).json()
                i = export(ew.client, "conversations").json()
                assert len(d["books"]) == len(i["books"])
                assert "conversations" not in set(walk_keys(d))
                for de, ie in zip(d["books"], i["books"]):
                    assert _strip_conversation_data(ie) == de
                    if "error" not in ie:
                        assert "conversations" in ie
                        assert not [c for c in de["component_errors"] if c.get("component") == "conversations"]
        finally:
            _clear_caches()
            shutil.rmtree(proj, ignore_errors=True)

    check()


# =========================================================================== E21

_E21_LU: List[Any] = [D_OLD, D_MID, D_NEW, None, "", 7, ABSENT]
_E21_COPY = st.tuples(st.sampled_from(_E21_LU), st.integers(0, 19).map(lambda x: x < 3))
_E21_CID = st.tuples(st.sampled_from(["none", "book", "root", "both"]), _E21_COPY, _E21_COPY)


def _lu_key(x: Any) -> str:
    return x if isinstance(x, str) else ""


def test_e21_dedupe_law_one_copy_per_cid_max_last_updated_every_storage(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E21 (S5): one copy per cid; the greater-key copy wins; a bad copy is reported while the
    readable one is exported; independent of ``conversation_disk_storage``."""
    export(ew.client)  # fails fast (and named) before the route exists

    @LAYOUT_SETTINGS
    @given(spec=st.tuples(*[_E21_CID for _ in POOL]), storage=st.sampled_from(STORAGES))
    def check(spec: Tuple[Any, ...], storage: str) -> None:
        proj = Path(tempfile.mkdtemp(prefix="e21-"))
        try:
            with monkeypatch.context() as mp:
                books, R = proj / "books", proj / "convroot"
                books.mkdir(parents=True)
                book_files: List[Tuple[str, bytes]] = []
                readable: Dict[str, Dict[str, Any]] = {}
                bad: set = set()
                for cid, (presence, book_copy, root_copy) in zip(POOL, spec):
                    for source, (lu, is_bad) in (("book", book_copy), ("root", root_copy)):
                        if presence not in (source, "both"):
                            continue
                        payload = b"{trunc" if is_bad else conv(cid, lu, f"{cid}-{source}")[1]
                        if source == "book":
                            book_files.append((f"{cid}.json", payload))
                        else:
                            put_file(R / U / f"{cid}.json", payload)
                        if is_bad:
                            bad.add(cid)
                        else:
                            readable.setdefault(cid, {})[source] = conv_payload(cid, lu, f"{cid}-{source}")
                            readable[cid][source + "_lu"] = lu
                make_book(books, "a_data", book_uuid=U, convs=book_files)
                rehome(mp, books, _prefs(storage))

                entry = entry_of(export(ew.client, "conversations").json(), "a_data")
                got = entry["conversations"]
                counts = collections.Counter(cids(got))
                assert all(v == 1 for v in counts.values()), counts
                assert set(counts) == set(readable)
                assert set(_conv_error_stems(entry)) == bad
                for t in got:
                    copies = readable[t["conversation_id"]]
                    if "book" in copies and "root" in copies:
                        kb, kr = _lu_key(copies["book_lu"]), _lu_key(copies["root_lu"])
                        if kb != kr:
                            assert t == copies["book" if kb > kr else "root"]
                        else:
                            # W6-11: on equal keys the project-root copy wins (W5 F-15 tie rule).
                            assert t == copies["root"]
                    else:
                        assert t == copies["book" if "book" in copies else "root"]
        finally:
            _clear_caches()
            shutil.rmtree(proj, ignore_errors=True)

    check()


@pytest.mark.parametrize("storage", STORAGES)
@pytest.mark.parametrize("lu", ["2026-01-01T00:00:00", None], ids=["equal_str", "both_null"])
def test_e21_tie_project_root_copy_wins(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, storage: str, lu: Any
) -> None:
    """E21-tie (W6-11): same cid, equal ``last_updated`` in both sources -> exactly the
    project-root copy is exported, in every storage mode (deterministic, not hypothesis-drawn)."""
    proj = Path(tempfile.mkdtemp(prefix="e21tie-"))
    try:
        with monkeypatch.context() as mp:
            books, R = proj / "books", proj / "convroot"
            books.mkdir(parents=True)
            cid = POOL[0]
            put_file(R / U / f"{cid}.json", conv(cid, lu, f"{cid}-root")[1])
            make_book(books, "a_data", book_uuid=U, convs=[(f"{cid}.json", conv(cid, lu, f"{cid}-book")[1])])
            rehome(mp, books, _prefs(storage))
            entry = entry_of(export(ew.client, "conversations").json(), "a_data")
            assert entry["conversations"] == [conv_payload(cid, lu, f"{cid}-root")]
            assert entry["component_errors"] == []
    finally:
        _clear_caches()
        shutil.rmtree(proj, ignore_errors=True)


# =========================================================================== E22


@pytest.mark.parametrize("include", MODES, ids=MODE_IDS)
def test_e22_idempotence_on_a_rich_fixed_tree(ew: ExportWorld, include: Optional[str]) -> None:
    """E22: two exports of the same tree are byte-equal (no timestamps); headers equal but date."""
    _e3_tree(ew)
    notes_json(ew.books / "b_data", E8_NOTES["bad_record"])
    put_file(_per_book(ew, "a_data") / f"{ZERO_UUID}.json", b"{trunc")
    r1 = export(ew.client, include)
    r2 = export(ew.client, include)
    assert r1.content == r2.content
    h1 = {k: v for k, v in r1.headers.items() if k.lower() != "date"}
    h2 = {k: v for k, v in r2.headers.items() if k.lower() != "date"}
    assert h1 == h2


# =========================================================================== H2 / H3


def test_h2_library_and_export_agree_over_generated_libraries(ew: ExportWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    """H2 (U4, S5): project(export entry) == library entry; error entries equal."""
    export(ew.client)  # fails fast (and named) before the route exists

    @LAYOUT_SETTINGS
    @given(layout=layouts(["ok", "corrupt_pkl"], uuid_always=True))
    def check(layout: Any) -> None:
        books_spec, storage = layout
        proj = Path(tempfile.mkdtemp(prefix="h2-"))
        try:
            with monkeypatch.context() as mp:
                _build_layout(proj, books_spec)
                rehome(mp, proj / "books", _prefs(storage))
                lib = library(ew.client).json()
                exp = export(ew.client).json()
                assert [project(e) if "error" not in e else e for e in exp["books"]] == lib["books"]
        finally:
            _clear_caches()
            shutil.rmtree(proj, ignore_errors=True)

    check()


@pytest.mark.parametrize("exc_kind", ["value_error", "book_gone"])
def test_h3_both_routes_honour_the_load_book_metadata_seam(
    ew: ExportWorld, monkeypatch: pytest.MonkeyPatch, exc_kind: str
) -> None:
    """H3: a ValueError for b -> the same error entry in both routes; BookGone -> b absent from both."""
    make_book(ew.books, "a_data", title="Alpha", book_uuid=U)
    make_book(ew.books, "b_data", title="Beta", book_uuid=V)
    make_book(ew.books, "c_data", title="Gamma", book_uuid=W)

    def make_exc() -> BaseException:
        if exc_kind == "value_error":
            return ValueError("metadata unreadable (injected)")
        return book_lock.BookGone(errno.ENOENT, "gone", str(ew.books / "b_data"))

    fired = raising_for(monkeypatch, book_store, "load_book_metadata", lambda *a: a[0] == "b_data", make_exc)
    exp = export(ew.client).json()
    assert fired, "positive control: the export never loaded metadata through book_store.load_book_metadata"
    lib = library(ew.client).json()

    for body in (exp, lib):
        ids = [e["book_id"] for e in body["books"]]
        if exc_kind == "value_error":
            assert ids == ["a_data", "b_data", "c_data"]
            assert entry_of(body, "b_data") == {"book_id": "b_data", "error": "unreadable"}
        else:
            assert ids == ["a_data", "c_data"]
        assert entry_of(body, "a_data")["title"] == "Alpha"
        assert entry_of(body, "c_data")["title"] == "Gamma"
    assert [project(e) if "error" not in e else e for e in exp["books"]] == lib["books"]
