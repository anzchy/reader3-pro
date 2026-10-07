"""018 WI-5a: ``library_delete.sweep`` (matrix cases S-1, S-1b, S-2 .. S-6).

Lock contention is always cross-process (``Holder`` / ``probe_lock`` spawn a child):
an in-process re-acquire would hit ``BookLockReentry`` instead. Every holder is
released in a ``finally``.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile

import pytest
from delete_world import (
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    EMPTY_REPORT,
    U,
    U2,
    Holder,
    StepRecorder,
    acquire_spy,
    conv,
    install_hook,
    ld,
    make_book,
    make_intent,
    new_world,
    paired,
    probe_lock,
    put_file,
    raw_conv,
    read_collections,
    report_dict,
    tree_bytes,
    write_collections,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# =========================================================================== S-1

S1_KINDS = [
    "live",
    "decoy",
    "paired_false_none",
    "paired_false_dated",
    "paired_false_undated",
    "paired_true_none",
    "paired_true_convs",
    "bad_conv",
    "intent_only",
    "tomb_only_none",
    "tomb_only_convs",
    "corrupt_paired",
    "corrupt_orphan",
    "tmp",
]


def _s1_uuid(i: int) -> str:
    return f"{i:08d}-0000-4000-8000-0000000000aa"


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(kinds=st.lists(st.sampled_from(S1_KINDS), max_size=8))
def test_s1_sweep_classification_is_total_and_touches_nothing_else(tmp_path, kinds):
    """S-1: every entry lands in exactly its field; live books, decoys, conserved tombstones, .tmp untouched."""
    m = ld()
    w = new_world(tempfile.mkdtemp(dir=tmp_path))
    (w.books / ".locks").mkdir(exist_ok=True)
    expect = {k: [] for k in EMPTY_REPORT}
    keep = []  # top-level names that must stay byte-identical

    for i, kind in enumerate(kinds):
        folder = f"f{i}_data"
        uid = _s1_uuid(i)
        tomb = m.tombstone_name(folder, 77, "abcdef12")
        intent = m.intent_name(folder, 77, "abcdef12")
        if kind == "live":
            make_book(w.books, folder, book_uuid=uid)
            keep.append(folder)
        elif kind == "decoy":
            decoy = f".{folder}.deleted-1_data"
            put_file(w.books / decoy / "book.txt", b"decoy")
            keep.append(decoy)
        elif kind.startswith("paired_") or kind == "bad_conv":
            mode = kind.startswith("paired_true")
            convs = []
            if kind in ("paired_false_dated", "paired_true_convs", "bad_conv"):
                convs = [conv(CID_FRESH, D_MID, "dated")]
            elif kind == "paired_false_undated":
                convs = [conv(CID_FRESH, None, "undated")]
            if kind == "bad_conv":
                convs.append(raw_conv(f"{CID_COLLIDE}.json", b"{trunc"))
            paired(w.books, folder, mode=mode, uuid=uid, root=w.R, coll=w.coll, book_uuid=uid, convs=convs)
            if kind == "bad_conv":
                expect["conserved"].append(tomb)
                keep.append(tomb)
            else:
                expect["finalized"].append(tomb)
        elif kind == "intent_only":
            make_book(w.books, folder, book_uuid=uid)
            m.write_intent(str(w.books), make_intent(folder, mode=False, uuid=uid, root=w.R, coll=w.coll))
            expect["orphan_intents"].append(intent)
            keep.append(folder)
        elif kind.startswith("tomb_only"):
            convs = [conv(CID_FRESH, D_MID, "dated")] if kind == "tomb_only_convs" else []
            make_book(w.books, folder, book_uuid=uid, convs=convs)
            os.rename(w.books / folder, w.books / tomb)
            expect["conserved"].append(tomb)
            keep.append(tomb)
        elif kind == "corrupt_paired":
            make_book(w.books, folder, book_uuid=uid)
            os.rename(w.books / folder, w.books / tomb)
            put_file(w.books / intent, b"{not json")
            expect["conserved"].append(tomb)
            expect["unreadable"].append(intent)
            keep.extend([tomb, intent])
        elif kind == "corrupt_orphan":
            put_file(w.books / intent, b"{not json")
            expect["orphan_intents"].append(intent)
        elif kind == "tmp":
            name = f"{intent}.tmp"
            put_file(w.books / name, b"partial")
            keep.append(name)
        else:  # pragma: no cover
            raise AssertionError(kind)

    before = {name: tree_bytes(w.books / name) for name in keep}

    report = w.sweep()

    got = report_dict(report)
    assert {k: sorted(v) for k, v in got.items()} == {k: sorted(v) for k, v in expect.items()}
    assert got["busy"] == [] and got["failed"] == []
    for name in keep:
        assert tree_bytes(w.books / name) == before[name], name
    for name in expect["finalized"] + expect["orphan_intents"]:
        assert not os.path.lexists(w.books / name), name


# =========================================================================== S-1b


def test_s1b_pairing_is_by_full_triple(tmp_path):
    """S-1b: a legacy ``.a_data.deleted-77`` never pairs with ``...-88-abcdef12.intent.json``."""
    m = ld()
    w = new_world(tmp_path / "w")
    legacy = ".a_data.deleted-77"
    make_book(w.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh", own_uuid=U)])
    os.rename(w.books / "a_data", w.books / legacy)
    m.write_intent(str(w.books), make_intent("a_data", pid=88, token="abcdef12", mode=False, uuid=U, root=w.R, coll=w.coll))
    intent = m.intent_name("a_data", 88, "abcdef12")
    make_book(w.books, "a_data", title="Alpha 2", book_uuid=U2)
    write_collections(w.coll, {"c1": ["a_data"]})
    r_before = tree_bytes(w.R)
    tomb_before = tree_bytes(w.books / legacy)
    live_before = tree_bytes(w.books / "a_data")
    coll_before = w.coll.read_bytes()

    report = w.sweep()

    assert report.conserved == [legacy]
    assert tree_bytes(w.books / legacy) == tomb_before
    assert report.orphan_intents == [intent]
    assert not (w.books / intent).exists()
    assert tree_bytes(w.R) == r_before
    assert tree_bytes(w.books / "a_data") == live_before
    assert w.coll.read_bytes() == coll_before


# =========================================================================== S-2


def test_s2_sweep_with_held_lock_is_busy_not_partial(tmp_path):
    """S-2: SH "conversations" held on a_data -> busy, nothing changes; after release -> finalized."""
    from reader3_app import book_lock

    w = new_world(tmp_path / "w")
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "x")])
    make_book(w.books, "a_data", title="Alpha 2", book_uuid=U2)
    write_collections(w.coll, {"C": ["a_data"]})
    live_before = tree_bytes(w.books / "a_data")
    state_before = w.state()

    holder = Holder(str(w.books), "a_data", book_lock.SHARED, "conversations", str(tmp_path))
    holder.start()
    try:
        first = w.sweep()
        assert sorted(first.busy) == sorted([p.tomb.name, p.intent.name])
        assert first.finalized == [] and first.conserved == []
        assert w.state() == state_before
    finally:
        holder.release()

    second = w.sweep()
    assert second.finalized == [p.tomb.name]
    assert read_collections(w.coll) == {"C": ["a_data"]}
    assert tree_bytes(w.books / "a_data") == live_before


# =========================================================================== S-3

S3_DELETE_WINDOW = [
    "committed",
    "fin_collections",
    "fin_caches",
    "conv_published",
    "conv_published",
    "conv_done",
    "rmtree_done",
    "intent_removed",
]
S3_SWEEP_WINDOW = S3_DELETE_WINDOW[1:]
S3_CONVS = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")]


@pytest.mark.parametrize("entry", ["sweep", "delete_book"])
def test_s3_the_lock_is_held_for_the_whole_finalization(tmp_path, monkeypatch, entry):
    """S-3: at every step of the finalization a cross-process SH probe is busy with category "delete"."""
    w = new_world(tmp_path / "w")
    window = S3_SWEEP_WINDOW if entry == "sweep" else S3_DELETE_WINDOW
    if entry == "sweep":
        paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=S3_CONVS)
    else:
        make_book(w.books, "a_data", book_uuid=U, convs=S3_CONVS)

    probes = []

    def on_step(name, nth):
        if name in window:
            probes.append((name, probe_lock(w.books, "a_data", "shared")))

    install_hook(monkeypatch, StepRecorder(on_step=on_step))

    if entry == "sweep":
        w.sweep()
    else:
        w.delete(mode=False)

    assert [name for name, _ in probes] == window
    assert [outcome for _, outcome in probes] == [("busy", "delete")] * len(window)


# =========================================================================== S-4


def _s4_world(tmp_path):
    m = ld()
    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U)
    m.write_intent(str(w.books), make_intent("a_data", mode=False, uuid=U, root=w.R, coll=w.coll))
    intent = w.books / m.intent_name("a_data", 77, "abcdef12")
    return w, intent


def test_s4a_orphan_intent_removal_takes_the_ex_lock(tmp_path):
    """S-4(a): EX "delete" held -> the orphan intent is busy and identical; after release -> removed."""
    from reader3_app import book_lock

    w, intent = _s4_world(tmp_path)
    book_before = tree_bytes(w.books / "a_data")
    intent_before = intent.read_bytes()

    holder = Holder(str(w.books), "a_data", book_lock.EXCLUSIVE, "delete", str(tmp_path))
    holder.start()
    try:
        first = w.sweep()
        assert first.busy == [intent.name]
        assert first.orphan_intents == []
        assert intent.read_bytes() == intent_before
        assert tree_bytes(w.books / "a_data") == book_before
    finally:
        holder.release()

    second = w.sweep()
    assert second.orphan_intents == [intent.name]
    assert not intent.exists()
    assert tree_bytes(w.books / "a_data") == book_before


def test_s4b_orphan_intent_removal_is_exclusive_not_shared(tmp_path):
    """S-4(b): SH "search" held -> busy, the intent is identical."""
    from reader3_app import book_lock

    w, intent = _s4_world(tmp_path)
    intent_before = intent.read_bytes()

    holder = Holder(str(w.books), "a_data", book_lock.SHARED, "search", str(tmp_path))
    holder.start()
    try:
        report = w.sweep()
        assert report.busy == [intent.name]
        assert report.orphan_intents == []
        assert intent.read_bytes() == intent_before
    finally:
        holder.release()


# =========================================================================== S-5


def test_s5a_sweep_reclassifies_after_acquiring_becomes_paired(tmp_path, monkeypatch):
    """S-5(a): the entry commits between listing and acquiring -> finalized, never an orphan."""
    m = ld()
    convs = [conv(CID_FRESH, D_MID, "fresh")]

    ref = new_world(tmp_path / "ref")
    make_book(ref.books, "a_data", book_uuid=U, convs=convs)
    ref.delete(mode=False)
    expected = ref.state()

    w = new_world(tmp_path / "w")
    make_book(w.books, "a_data", book_uuid=U, convs=convs)
    intent_path = m.write_intent(str(w.books), make_intent("a_data", mode=False, uuid=U, root=w.R, coll=w.coll))
    tomb = m.tombstone_name("a_data", 77, "abcdef12")

    fired = acquire_spy(
        monkeypatch,
        before=lambda: m.commit_tombstone(str(w.books), m.read_intent(intent_path)),
        when=lambda folder, holder, mode: holder == "delete" and folder == "a_data",
    )

    report = w.sweep()

    assert fired == [1]
    assert report.finalized == [tomb]
    assert report.orphan_intents == []
    assert w.state() == expected
    assert (w.R / U / f"{CID_FRESH}.json").is_file()


def test_s5b_sweep_reclassifies_after_acquiring_vanishes(tmp_path, monkeypatch, caplog):
    """S-5(b): the entry vanishes between listing and acquiring -> no field, no exception logged."""
    caplog.set_level(logging.DEBUG)
    w = new_world(tmp_path / "w")
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U)

    def vanish():
        shutil.rmtree(p.tomb)
        os.unlink(p.intent)

    fired = acquire_spy(monkeypatch, before=vanish, when=lambda folder, holder, mode: holder == "delete" and folder == "a_data")

    report = w.sweep()

    assert fired == [1]
    assert report_dict(report) == EMPTY_REPORT
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR or r.exc_info]


# =========================================================================== S-6

UA = "aaaaaaaa-1111-4000-8000-0000000000a1"
UB = "bbbbbbbb-1111-4000-8000-0000000000b1"


def test_s6_one_failing_tombstone_does_not_block_others(tmp_path, monkeypatch, caplog):
    """S-6: R/UA is a regular file -> a fails, b finalizes; a later delete_book is not blocked by a."""
    caplog.set_level(logging.DEBUG)
    m = ld()
    w = new_world(tmp_path / "w")
    put_file(w.R / UA, b"not a directory")
    conv_a = conv(CID_FRESH, D_MID, "a's conversation")
    conv_b = conv(CID_COLLIDE, D_MID, "b's conversation")
    pa = paired(w.books, "a_data", mode=False, uuid=UA, root=w.R, coll=w.coll, book_uuid=UA, convs=[conv_a])
    pb = paired(w.books, "b_data", mode=False, uuid=UB, root=w.R, coll=w.coll, book_uuid=UB, convs=[conv_b])
    make_book(w.books, "c_data", book_uuid=U)
    a_tomb_before, a_intent_before = tree_bytes(pa.tomb), pa.intent.read_bytes()

    report = w.sweep()

    assert report.failed == [pa.tomb.name]
    assert report.finalized == [pb.tomb.name]
    assert tree_bytes(pa.tomb) == a_tomb_before
    assert pa.intent.read_bytes() == a_intent_before
    assert (w.R / UB / conv_b[0]).read_bytes() == conv_b[1]
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(pa.tomb.name in msg for msg in errors), errors

    reports = []
    real_sweep = m.sweep

    def recording_sweep(*a, **kw):
        out = real_sweep(*a, **kw)
        reports.append(out)
        return out

    monkeypatch.setattr(m, "sweep", recording_sweep)

    w.delete("c_data", mode=True)

    assert not (w.books / "c_data").exists()
    assert len(reports) == 1
    assert reports[0].failed == [pa.tomb.name]

