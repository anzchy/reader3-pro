"""018 WI-5a: ``plan_publish`` / ``finalize_tombstone`` (matrix cases F-1 .. F-15).

Every finalize here is reached through the public entry points ``delete_book`` and
``sweep`` (the finalizer itself runs under the sweep's EX lock). The module under
test is imported lazily via ``ld()`` so the lane collects while it does not exist.
"""

from __future__ import annotations

import ast
import errno
import json
import logging
import os
import tempfile
from pathlib import Path

import pytest
from delete_world import (
    ABSENT,
    CID_3,
    CID_COLLIDE,
    CID_FRESH,
    D_MID,
    D_NEW,
    D_OLD,
    EMPTY_REPORT,
    READABLE_LU_KIND_IDS,
    READABLE_LU_KINDS,
    SCHEMA_KIND_IDS,
    SCHEMA_KINDS,
    U,
    U2,
    UNREADABLE_KIND_IDS,
    V,
    W,
    Fault,
    IdentityProbe,
    InvalidatorRecorder,
    StepRecorder,
    SyscallLog,
    _Crash,
    chroma_env,  # noqa: F401 - fixture
    conv,
    dot_entries,
    f1_world,
    finish,
    install_hook,
    intent_json,
    isolate_invalidators,
    ld,
    listing,
    make_book,
    new_world,
    paired,
    parse_point,
    popen_child,
    put_file,
    read_collections,
    report_dict,
    resolver_maps,
    schema_kind_layout,
    seat_resolver,
    server_module,
    tree_bytes,
    under,
    warm,
    write_collections,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


def _reader3_records(caplog, level=None):
    return [
        r
        for r in caplog.records
        if r.name.startswith("reader3") and (level is None or r.levelno == level)
    ]


def _messages(caplog, level=None):
    return [r.getMessage() for r in _reader3_records(caplog, level)]


def _files(tree):
    """Only the file entries of a ``tree_bytes`` result (``{}`` for a missing tree)."""
    return {k: v for k, v in (tree or {}).items() if v != "<dir>"}


# =========================================================================== F-1

F1_FALSE = [
    "committed",
    "fin_collections",
    "fin_caches",
    "conv_published#1",
    "conv_published#2",
    "conv_done",
    "rmtree_done",
    "intent_removed",
    "none",
]
F1_TRUE = [p for p in F1_FALSE if not p.startswith("conv_published")]
F1_RUNS = [(False, k, j) for k in F1_FALSE for j in F1_FALSE] + [(True, k, j) for k in F1_TRUE for j in F1_TRUE]
F1_IDS = [f"{'true' if mode else 'false'}-k={k}-j={j}" for mode, k, j in F1_RUNS]


@pytest.mark.parametrize(("mode", "k", "j"), F1_RUNS, ids=F1_IDS)
def test_f1_finalize_is_idempotent_under_every_crash_prefix(tmp_path, monkeypatch, mode, k, j):
    """F-1: crash at k in the delete, crash at j in a sweep, then a clean sweep == one clean delete."""
    m = ld()
    ref = f1_world(tmp_path / "ref")
    ref.delete(mode=mode)
    expected = ref.state()

    w = f1_world(tmp_path / "work")
    install_hook(monkeypatch, StepRecorder(crash_at=parse_point(k)))
    if k == "none":
        w.delete(mode=mode)
    else:
        with pytest.raises(_Crash):
            w.delete(mode=mode)

    m._STEP_HOOK = StepRecorder(crash_at=parse_point(j))
    try:
        w.sweep()
    except _Crash:
        pass
    m._STEP_HOOK = None

    w.sweep()
    assert w.state() == expected

    again = w.sweep()
    assert report_dict(again) == EMPTY_REPORT
    assert w.state() == expected


# =========================================================================== F-2

F2_CIDS = [
    "0a1b2c3d-0000-4000-8000-000000000001",
    "0a1b2c3d-0000-4000-8000-000000000002",
    "0a1b2c3d-0000-4000-8000-000000000003",
    "0a1b2c3d-0000-4000-8000-000000000004",
    "0a1b2c3d-0000-4000-8000-000000000005",
    "0a1b2c3d-0000-4000-8000-000000000006",
]
F2_LU_POOL = [D_OLD, D_MID, D_MID, D_NEW, ABSENT, None, "", 7]
F2_OWN_POOL = [U, V, ABSENT, "malformed", "../x"]


def _oracle_key(value):
    """Test-side key, written from §0.2: a str keys as itself, anything else (missing too) as ""."""
    return value if isinstance(value, str) else ""


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    book_convs=st.lists(
        st.tuples(st.sampled_from(F2_CIDS), st.sampled_from(F2_LU_POOL), st.sampled_from(F2_OWN_POOL)),
        unique_by=lambda t: t[0],
        max_size=6,
    ),
    existing=st.dictionaries(
        st.tuples(st.sampled_from([U, V]), st.sampled_from(F2_CIDS)),
        st.sampled_from(F2_LU_POOL),
        max_size=8,
    ),
)
def test_f2_conservation_newer_last_updated_wins_and_nothing_is_lost(tmp_path, book_convs, existing):
    """F-2: per cid the larger key wins at R/{own V else U}; a tie keeps the existing bytes."""
    w = new_world(tempfile.mkdtemp(dir=tmp_path))
    expected = {}
    existing_lu = {}
    for (target, cid), lu in existing.items():
        name, payload = conv(cid, lu, f"existing-{target[:8]}-{cid[-4:]}")
        put_file(w.R / target / name, payload)
        expected[f"{target}/{name}"] = payload
        existing_lu[(target, cid)] = lu

    convs = [conv(cid, lu, f"book-{cid[-4:]}", own_uuid=own) for cid, lu, own in book_convs]
    write_collections(w.coll, {"c1": ["a_data"]})
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)

    for (cid, lu, own), (name, payload) in zip(book_convs, convs):
        target = V if own == V else U
        key = f"{target}/{name}"
        if (target, cid) not in existing_lu or _oracle_key(lu) > _oracle_key(existing_lu[(target, cid)]):
            expected[key] = payload

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert report.conserved == []
    assert report.failed == []
    assert not p.tomb.exists()
    got = _files(tree_bytes(w.R))
    assert got == expected
    if w.R.exists():
        assert set(os.listdir(w.R)) <= {U, V}


# =========================================================================== F-3


def test_f3a_publish_follows_a_symlinked_root(tmp_path):
    """F-3(a): R is a symlink -> files land in its target; R stays a symlink."""
    w = new_world(tmp_path / "w")
    other = tmp_path / "other_tmp" / "convs"
    other.mkdir(parents=True)
    w.R.symlink_to(other, target_is_directory=True)
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")]
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert w.R.is_symlink()
    for name, payload in convs:
        assert (other / U / name).read_bytes() == payload


def test_f3b_publish_never_renames_across_directories(tmp_path, monkeypatch):
    """F-3(b): a rename/replace whose parent dirs differ raises EXDEV; the finalize still succeeds."""
    w = new_world(tmp_path / "w")
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")]
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)

    def cross(s, d):
        return os.path.dirname(s) != os.path.dirname(d)

    rename_fault = Fault(monkeypatch, "rename", cross, errno.EXDEV)
    replace_fault = Fault(monkeypatch, "replace", cross, errno.EXDEV)

    report = w.sweep()

    assert rename_fault.hits == [] and replace_fault.hits == [], "a cross-directory rename was attempted"
    assert report.finalized == [p.tomb.name]
    for name, payload in convs:
        assert (w.R / U / name).read_bytes() == payload


# =========================================================================== F-4


def test_f4_rmtree_waits_for_every_publish(tmp_path, monkeypatch):
    """F-4: ENOSPC on the 2nd publish -> ``failed``, tombstone + intent kept; next sweep finalizes."""
    w = new_world(tmp_path / "w")
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_MID, "collide"), conv(CID_3, D_MID, "third")]
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)
    book_convs_before = tree_bytes(p.tomb / "ai_conversations")
    intent_before = p.intent.read_bytes()

    seen = []

    def second_under_r(s, d):
        if under(d, w.R):
            seen.append(d)
            return len(seen) == 2
        return False

    fault = Fault(monkeypatch, "replace", second_under_r, errno.ENOSPC)

    first = w.sweep()

    assert fault.hits, "the injected ENOSPC never fired"
    assert p.tomb.name in first.failed
    assert p.tomb.name not in first.finalized
    assert p.tomb.name not in first.conserved
    assert p.tomb.is_dir()
    assert p.intent.read_bytes() == intent_before
    assert tree_bytes(p.tomb / "ai_conversations") == book_convs_before

    fault.armed = False
    second = w.sweep()

    assert second.finalized == [p.tomb.name]
    for name, payload in convs:
        assert (w.R / U / name).read_bytes() == payload


# =========================================================================== F-5


def _f5_world(tmp_path):
    w = new_world(tmp_path / "w")
    put_file(w.R / U / "x.json", b'{"x": 1}')
    put_file(w.R / W / "y.json", b'{"y": 1}')
    return w


F5_CONVS = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide")]


def test_f5a_mode_true_removes_this_uuid_only(tmp_path):
    """F-5(a): true mode, root R, uuid U -> R/U gone, R/W untouched, tombstone gone."""
    w = _f5_world(tmp_path)
    w_before = tree_bytes(w.R / W)
    p = paired(w.books, "a_data", mode=True, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=F5_CONVS)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert not (w.R / U).exists()
    assert tree_bytes(w.R / W) == w_before
    assert not p.tomb.exists()


def test_f5b_mode_true_without_root_skips_and_warns(tmp_path, caplog):
    """F-5(b): true mode, root None -> tombstone gone, R/U/x.json kept, WARNING "conversation root"."""
    caplog.set_level(logging.DEBUG)
    w = _f5_world(tmp_path)
    p = paired(w.books, "a_data", mode=True, uuid=U, root=None, coll=w.coll, book_uuid=U, convs=F5_CONVS)

    w.sweep()

    assert not p.tomb.exists()
    assert (w.R / U / "x.json").read_bytes() == b'{"x": 1}'
    assert any("conversation root" in msg.lower() for msg in _messages(caplog, logging.WARNING)), _messages(caplog)


def test_f5c_mode_true_without_uuid_skips_and_logs(tmp_path, caplog):
    """F-5(c): true mode, uuid None -> tombstone gone, R/U/x.json kept, the log names book_uuid."""
    caplog.set_level(logging.DEBUG)
    w = _f5_world(tmp_path)
    p = paired(w.books, "a_data", mode=True, uuid=None, root=w.R, coll=w.coll, book_uuid=U, convs=F5_CONVS)

    w.sweep()

    assert not p.tomb.exists()
    assert (w.R / U / "x.json").read_bytes() == b'{"x": 1}'
    assert any("book_uuid" in msg for msg in _messages(caplog)), _messages(caplog)


# =========================================================================== F-6

F6_VARIANTS = ["a-convs-no-intent", "b-no-convs-no-intent", "c-corrupt-intent", "d-live-same-name"]


@pytest.mark.parametrize("variant", F6_VARIANTS)
def test_f6_intentless_tombstone_is_always_conserved_without_side_effects(
    tmp_path, monkeypatch, caplog, chroma_env, variant  # noqa: F811
):
    """F-6: an intent-less (or corrupt-intent) tombstone is conserved with no side effect, every sweep."""
    caplog.set_level(logging.DEBUG)
    m = isolate_invalidators(monkeypatch)
    w = new_world(tmp_path / "w")
    tomb_name = m.tombstone_name("a_data", 77, "abcdef12")
    intent_name = m.intent_name("a_data", 77, "abcdef12")
    convs = F5_CONVS if variant.startswith("a-") else ()
    make_book(w.books, "a_data", book_uuid=U, convs=convs)
    os.rename(w.books / "a_data", w.books / tomb_name)
    if variant.startswith("c-"):
        put_file(w.books / intent_name, b"{not json")
    write_collections(w.coll, {"c1": ["a_data"]})

    resolver = seat_resolver(monkeypatch, w.books)
    probe = None
    if variant.startswith("d-"):
        make_book(w.books, "a_data", book_uuid=U)
        probe = IdentityProbe(resolver, "a_data", U, w.books / "a_data" / "chroma_db")
    else:
        warm(resolver, "a_data", U)

    rec = InvalidatorRecorder()
    m.register_invalidator(rec, folder_scoped=True)
    m.register_invalidator(rec, folder_scoped=False)

    tomb_before = tree_bytes(w.books / tomb_name)
    intent_before = (w.books / intent_name).read_bytes() if variant.startswith("c-") else None
    coll_before = w.coll.read_bytes()

    for n in range(3):
        caplog.clear()
        report = w.sweep()
        assert report.conserved == [tomb_name], f"sweep {n}"
        assert report.finalized == []
        if variant.startswith("c-"):
            assert report.unreadable == [intent_name]
            assert (w.books / intent_name).read_bytes() == intent_before
        assert tree_bytes(w.books / tomb_name) == tomb_before
        assert w.coll.read_bytes() == coll_before
        assert resolver._folder_to_uuid["a_data"] == U
        assert rec.calls == []
        warnings = _reader3_records(caplog, logging.WARNING)
        assert len(warnings) == 1, [r.getMessage() for r in warnings]
        if probe is not None:
            probe.assert_untouched()


# =========================================================================== F-7


def _f7_crash_at_commit(monkeypatch, root):
    w = new_world(root)
    conv_a = root / "convA"
    make_book(w.books, "a_data", book_uuid=U, convs=[conv(CID_FRESH, D_MID, "c1")])
    install_hook(monkeypatch, StepRecorder(crash_at=("committed", 1)))
    with pytest.raises(_Crash):
        ld().delete_book(
            str(w.books),
            "a_data",
            delete_conversations=False,
            conversation_root=str(conv_a),
            collections_path=str(w.coll),
        )
    ld()._STEP_HOOK = None
    return w, conv_a


def _f7_settings_point_at_conv_b(monkeypatch, w):
    from reader3_app.web import server
    monkeypatch.setattr(server, "BOOKS_DIR", str(w.books))
    settings_b = {"preferences": {"conversation_project_root_dir": "convB"}}
    monkeypatch.setattr(server, "load_ai_settings", lambda *a, **k: settings_b)
    assert server._project_conversations_root(server.load_ai_settings()) == str(w.root / "convB")


def test_f7_finalizer_uses_intent_paths_after_settings_change(tmp_path, monkeypatch):
    """F-7 (in process): the sweep publishes to the intent's convA, never to the settings' convB."""
    w, conv_a = _f7_crash_at_commit(monkeypatch, tmp_path / "w")
    _f7_settings_point_at_conv_b(monkeypatch, w)

    ld().sweep(str(w.books))

    assert (conv_a / U / f"{CID_FRESH}.json").is_file()
    assert not (w.root / "convB").exists()


def test_f7_subprocess_sweep_loads_no_web_module(tmp_path, monkeypatch):
    """F-7 (subprocess): a fresh-interpreter sweep finalizes to convA and imports no reader3_app.web*."""
    ld()  # red guard in the parent, before any child is spawned
    w, conv_a = _f7_crash_at_commit(monkeypatch, tmp_path / "w")
    out = tmp_path / "sweep.json"

    rc, stdout, stderr = finish(popen_child("sweep_child_main", str(w.books), str(out)))

    assert rc == 0, stderr[-2000:]
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["web"] == []
    assert (conv_a / U / f"{CID_FRESH}.json").is_file()
    assert not (w.root / "convB").exists()


# =========================================================================== F-8


def test_f8_publish_is_durable_at_final_size(tmp_path, monkeypatch):
    """F-8: fsync(tmp at final size) < replace < fsync(dst dir) < first unlink inside the tombstone."""
    w = new_world(tmp_path / "w")
    put_file(w.R / U / f"{CID_COLLIDE}.json", conv(CID_COLLIDE, D_OLD, "collide-existing")[1])
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_NEW, "collide-book"), conv(CID_3, D_MID, "third")]
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)
    tomb_real = os.path.realpath(p.tomb)
    log = SyscallLog(monkeypatch)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    r_u_real = os.path.realpath(w.R / U)
    expected_dsts = {os.path.join(r_u_real, name) for name, _ in convs}
    first_unlink = log.index(lambda e: e[0] in ("unlink", "rmdir") and e[1].startswith(tomb_real + os.sep))
    assert first_unlink >= 0, "no removal inside the tombstone was observed"

    replaced = set()
    for i, ev in enumerate(log.events):
        if ev[0] not in ("replace", "rename", "link") or ev[2] not in expected_dsts:
            continue
        src, dst = ev[1], ev[2]
        replaced.add(dst)
        final_size = len(Path(dst).read_bytes())
        fsyncs = [
            k for k in range(i) if log.events[k][0] == "fsync" and log.events[k][1] == src and log.events[k][3] is False
        ]
        assert fsyncs, f"no fsync of the temp file {src} before its replace"
        assert log.events[fsyncs[-1]][2] == final_size, f"{src} fsynced at the wrong size"
        dir_fsync = log.index(
            lambda e, parent=os.path.dirname(dst): e[0] == "fsync" and e[1] == parent and e[3] is True, i + 1
        )
        assert dir_fsync > i, f"no directory fsync of {os.path.dirname(dst)} after the replace"
        assert dir_fsync < first_unlink, "the tombstone removal began before the publish was durable"
        assert i < first_unlink
    assert replaced == expected_dsts


def _observe_mkdir(monkeypatch, log: SyscallLog) -> None:
    """Add ``("mkdir", realpath)`` events to ``log`` (``os.makedirs`` reaches ``os.mkdir`` too)."""
    from delete_world import resolve

    real_mkdir = os.mkdir

    def mkdir(path, *a, **kw):
        p = resolve(path, kw.get("dir_fd"))
        out = real_mkdir(path, *a, **kw)
        log._add(("mkdir", p))
        return out

    monkeypatch.setattr(os, "mkdir", mkdir)


@pytest.mark.parametrize("absent", ["root-and-uuid", "uuid-only"])
def test_f8b_publish_makes_every_created_directory_durable(tmp_path, monkeypatch, absent):
    """F-8b (audit 20261007 #2 / #13, FX37-2): when the publish has to create ``R`` and/or ``R/U``,
    each created directory's parent is fsynced after that directory is made and before the first
    removal inside the tombstone -- otherwise power loss can drop the new entry, and with it the
    only copy of the conversations."""
    w = new_world(tmp_path / "w")
    if absent == "uuid-only":
        w.R.mkdir()
    assert not os.path.lexists(w.R / U)
    convs = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_3, D_MID, "third")]
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=convs)
    tomb_real = os.path.realpath(p.tomb)
    log = SyscallLog(monkeypatch)
    _observe_mkdir(monkeypatch, log)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert (w.R / U / f"{CID_FRESH}.json").is_file()
    first_unlink = log.index(lambda e: e[0] in ("unlink", "rmdir") and e[1].startswith(tomb_real + os.sep))
    assert first_unlink >= 0, "no removal inside the tombstone was observed"

    r_real = os.path.join(os.path.realpath(w.R.parent), w.R.name)
    created = [r_real, os.path.join(r_real, U)] if absent == "root-and-uuid" else [os.path.join(r_real, U)]
    observed = {}
    for d in created:
        made = log.index(lambda e, d=d: e[0] == "mkdir" and e[1] == d)
        synced = (
            -1
            if made < 0
            else log.index(lambda e, parent=os.path.dirname(d): e[0] == "fsync" and e[1] == parent and e[3] is True, made + 1)
        )
        observed[d] = {"made": made >= 0, "parent_fsynced_after": synced > made, "before_tomb_removal": 0 <= synced < first_unlink}
    assert observed == {d: {"made": True, "parent_fsynced_after": True, "before_tomb_removal": True} for d in created}


# =========================================================================== F-9


def test_f9a_hand_written_false_intent_with_no_root_is_conserved(tmp_path, caplog):
    """F-9(a): false mode, root null, uuid U, 2 conversations -> conserved, nothing created."""
    caplog.set_level(logging.DEBUG)
    m = ld()
    w = new_world(tmp_path / "w")
    write_collections(w.coll, {"c1": ["a_data"]})
    make_book(w.books, "a_data", book_uuid=U, convs=F5_CONVS)
    tomb = w.books / m.tombstone_name("a_data", 77, "abcdef12")
    intent = w.books / m.intent_name("a_data", 77, "abcdef12")
    put_file(intent, intent_json("a_data", pid=77, token="abcdef12", mode=False, uuid=U, root=None, coll=str(w.coll)))
    os.rename(w.books / "a_data", tomb)
    tomb_before, intent_before, coll_before = tree_bytes(tomb), intent.read_bytes(), w.coll.read_bytes()
    root_before = sorted(os.listdir(w.root))

    report = w.sweep()

    assert report.conserved == [tomb.name]
    assert tree_bytes(tomb) == tomb_before
    assert intent.read_bytes() == intent_before
    assert w.coll.read_bytes() == coll_before
    assert sorted(os.listdir(w.root)) == root_before
    assert not w.R.exists()
    assert any("conversation root" in msg.lower() for msg in _messages(caplog)), _messages(caplog)


def test_f9b_false_intent_with_unresolvable_uuid_is_conserved(tmp_path, caplog):
    """F-9(b): false mode, root R, uuid null, no own uuids -> conserved, R never created."""
    caplog.set_level(logging.DEBUG)
    m = ld()
    w = new_world(tmp_path / "w")
    write_collections(w.coll, {"c1": ["a_data"]})
    make_book(w.books, "a_data", book_uuid=U, convs=F5_CONVS)
    tomb = w.books / m.tombstone_name("a_data", 77, "abcdef12")
    intent = w.books / m.intent_name("a_data", 77, "abcdef12")
    put_file(intent, intent_json("a_data", pid=77, token="abcdef12", mode=False, uuid=None, root=str(w.R), coll=str(w.coll)))
    os.rename(w.books / "a_data", tomb)
    tomb_before, intent_before, coll_before = tree_bytes(tomb), intent.read_bytes(), w.coll.read_bytes()

    report = w.sweep()

    assert report.conserved == [tomb.name]
    assert tree_bytes(tomb) == tomb_before
    assert intent.read_bytes() == intent_before
    assert w.coll.read_bytes() == coll_before
    assert not w.R.exists()
    assert any("uuid" in msg.lower() for msg in _messages(caplog, logging.WARNING)), _messages(caplog)


# =========================================================================== F-10


def test_f10_finalizer_cleans_the_collections_file_named_in_the_intent(tmp_path):
    """F-10: the intent's collections_path is cleaned; the default file is byte-identical."""
    w = new_world(tmp_path / "w")
    alt = tmp_path / "alt" / "colls.json"
    write_collections(alt, {"c1": ["a_data", "b_data"]})
    write_collections(w.coll, {"d1": ["a_data"]})
    default_before = w.coll.read_bytes()
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=alt, book_uuid=U)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert read_collections(alt) == {"c1": ["b_data"]}
    assert w.coll.read_bytes() == default_before


# =========================================================================== F-11


def _f11_world(tmp_path, monkeypatch, kind, *, mode):
    w = new_world(tmp_path / "w")
    layout = schema_kind_layout(kind)
    put_file(w.R / U / f"{CID_COLLIDE}.json", layout.target)
    write_collections(w.coll, {"c1": ["a_data"]})
    uuid = None if (layout.uuid_null and mode is False) else U
    p = paired(w.books, "a_data", mode=mode, uuid=uuid, root=w.R, coll=w.coll, book_uuid=U, convs=layout.convs)
    resolver = seat_resolver(monkeypatch, w.books)
    warm(resolver, "a_data", U)
    return w, layout, p, resolver


def _outside_r_and_books(root):
    tree = tree_bytes(root) or {}
    return {k: v for k, v in tree.items() if not (k == "books" or k.startswith("books/") or k == "convroot" or k.startswith("convroot/"))}


@pytest.mark.parametrize(("kind", "klass", "reason"), SCHEMA_KINDS, ids=SCHEMA_KIND_IDS)
def test_f11_schema_kinds_unreadable_conserve_readable_publish(tmp_path, monkeypatch, caplog, kind, klass, reason):
    """F-11 leg (i): unreadable kinds conserve with no effect; readable kinds (W5-17) publish."""
    caplog.set_level(logging.DEBUG)
    w, layout, p, resolver = _f11_world(tmp_path, monkeypatch, kind, mode=False)
    r_before = tree_bytes(w.R)
    outside_before = _outside_r_and_books(w.root)
    tomb_before, intent_before, coll_before = tree_bytes(p.tomb), p.intent.read_bytes(), w.coll.read_bytes()
    maps_before = resolver_maps(resolver)

    if klass == "unreadable":
        states = []
        for n in range(2):
            caplog.clear()
            report = w.sweep()
            assert report.conserved == [p.tomb.name], f"sweep {n}"
            assert report.finalized == []
            assert tree_bytes(w.R) == r_before
            assert _outside_r_and_books(w.root) == outside_before
            assert tree_bytes(p.tomb) == tomb_before
            assert p.intent.read_bytes() == intent_before
            assert w.coll.read_bytes() == coll_before
            assert resolver_maps(resolver) == maps_before
            assert any(layout.bad_name in msg for msg in _messages(caplog, logging.WARNING)), _messages(caplog)
            states.append(w.state())
        assert states[0] == states[1]
        return

    report = w.sweep()
    assert report.finalized == [p.tomb.name]
    expected = {f"{U}/{name}": payload for name, payload in layout.convs}
    assert _files(tree_bytes(w.R)) == expected
    assert len(expected) == 4
    assert not p.tomb.exists()
    assert not p.intent.exists()
    assert read_collections(w.coll) == {"c1": []}
    assert not any(
        ("unreadable" in msg.lower() or "conserv" in msg.lower()) for msg in _messages(caplog, logging.WARNING)
    ), _messages(caplog)
    assert report_dict(w.sweep()) == EMPTY_REPORT


@pytest.mark.parametrize("kind", UNREADABLE_KIND_IDS)
def test_f11_true_mode_never_prescans(tmp_path, monkeypatch, caplog, kind):
    """F-11 leg (ii): the same unreadable tombstone in true mode is finalized; R/U is removed."""
    caplog.set_level(logging.DEBUG)
    w, layout, p, resolver = _f11_world(tmp_path, monkeypatch, kind, mode=True)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert not (w.R / U).exists()
    assert not p.tomb.exists()
    assert not any(
        ("unreadable" in msg.lower() or "conserv" in msg.lower()) for msg in _messages(caplog, logging.WARNING)
    ), _messages(caplog)


# =========================================================================== F-12


def test_f12_live_same_name_book_is_untouched_by_finalize(tmp_path, monkeypatch, caplog, chroma_env):  # noqa: F811
    """F-12: a live re-imported a_data (U2) survives the old tombstone's finalize untouched."""
    caplog.set_level(logging.DEBUG)
    m = ld()
    server_module()  # the server's call-time registrations are part of the setup
    w = new_world(tmp_path / "w")
    p = paired(
        w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")]
    )
    make_book(w.books, "a_data", title="Alpha 2", body="AAAA again", book_uuid=U2)
    write_collections(w.coll, {"C": ["a_data"]})
    resolver = seat_resolver(monkeypatch, w.books)
    probe = IdentityProbe(resolver, "a_data", U2, w.books / "a_data" / "chroma_db")
    live_before = tree_bytes(w.books / "a_data")
    coll_before = w.coll.read_bytes()

    results = []
    real_finalize = m.finalize_tombstone

    def spy(*a, **kw):
        out = real_finalize(*a, **kw)
        results.append(out)
        return out

    monkeypatch.setattr(m, "finalize_tombstone", spy)

    first = w.sweep()

    assert first.finalized == [p.tomb.name]
    assert [r.live_same_name for r in results] == [True]
    assert not p.tomb.exists()
    assert not p.intent.exists()
    assert (w.R / U / f"{CID_FRESH}.json").is_file()
    assert read_collections(w.coll) == {"C": ["a_data"]}
    assert w.coll.read_bytes() == coll_before
    assert any("live" in msg.lower() for msg in _messages(caplog)), _messages(caplog)

    for n in range(2):
        if n == 1:
            assert report_dict(w.sweep()) == EMPTY_REPORT
        assert resolver._folder_to_uuid["a_data"] == U2
        assert resolver._uuid_to_folder[U2] == "a_data"
        probe.assert_untouched()
        assert tree_bytes(w.books / "a_data") == live_before


# =========================================================================== F-13


def _f13_world(tmp_path):
    w = new_world(tmp_path / "w")
    write_collections(w.coll, {"c1": ["a_data"]})
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U)
    return w, p


def test_f13a_live_check_trusts_the_listing_not_book_pkl(tmp_path, monkeypatch):
    """F-13(a): a live a_data/book.pkl the listing does not report -> collections are cleaned."""
    from reader3_app import search_service

    w, p = _f13_world(tmp_path)
    make_book(w.books, "a_data", book_uuid=U2)
    monkeypatch.setattr(search_service, "list_book_ids", lambda books_dir: [])

    w.sweep()

    assert read_collections(w.coll) == {"c1": []}


def test_f13b_live_check_is_the_listing_predicate(tmp_path, monkeypatch, caplog):
    """F-13(b): no a_data on disk, but the listing reports it -> collections kept, logged."""
    from reader3_app import search_service

    caplog.set_level(logging.DEBUG)
    w, p = _f13_world(tmp_path)
    monkeypatch.setattr(search_service, "list_book_ids", lambda books_dir: ["a_data"])

    w.sweep()

    assert read_collections(w.coll) == {"c1": ["a_data"]}
    assert _messages(caplog), "no log line for the live same-name skip"


def test_f13c_library_delete_reads_the_listing_by_module_attribute():
    """F-13(c): no "book.pkl" constant; ``search_service.list_book_ids`` is an attribute access."""
    source = Path(ld().__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("book.pkl" in c for c in constants)
    assert any(
        isinstance(n, ast.Attribute)
        and n.attr == "list_book_ids"
        and isinstance(n.value, ast.Name)
        and n.value.id == "search_service"
        for n in ast.walk(tree)
    )


# =========================================================================== F-14

F14_CONVS = [conv(CID_FRESH, D_MID, "fresh"), conv(CID_COLLIDE, D_MID, "collide"), conv(CID_3, D_MID, "third")]


def test_f14a_prescan_and_finalize_both_consume_plan_publish(tmp_path, monkeypatch):
    """F-14(a): a raising ``plan_publish`` refuses the delete and conserves the sweep."""
    m = ld()

    def raising(*a, **kw):
        raise m.ConversationUnreadable("x.json", "json")

    monkeypatch.setattr(m, "plan_publish", raising)

    w = new_world(tmp_path / "w")
    write_collections(w.coll, {"c1": ["a_data"]})
    make_book(w.books, "a_data", book_uuid=U, convs=F14_CONVS)
    book_before = tree_bytes(w.books / "a_data")
    with pytest.raises(m.DeleteRefused) as exc_info:
        w.delete(mode=False)
    assert exc_info.value.reason == "conversation_unreadable"
    assert exc_info.value.path == "x.json"
    assert tree_bytes(w.books / "a_data") == book_before
    assert dot_entries(w.books) == []

    w2 = new_world(tmp_path / "w2")
    p = paired(w2.books, "a_data", mode=False, uuid=U, root=w2.R, coll=w2.coll, book_uuid=U, convs=F14_CONVS)
    report = w2.sweep()
    assert report.conserved == [p.tomb.name]


def test_f14b_publish_loop_iterates_plan_publish_only(tmp_path, monkeypatch):
    """F-14(b): ``plan_publish`` returning only CID_3 -> R holds only R/U/CID_3.json."""
    m = ld()
    real = m.plan_publish

    def only_cid3(*a, **kw):
        return [item for item in real(*a, **kw) if Path(item.src).name == f"{CID_3}.json"]

    w = new_world(tmp_path / "w")
    paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=F14_CONVS)
    monkeypatch.setattr(m, "plan_publish", only_cid3)

    w.sweep()

    assert sorted(_files(tree_bytes(w.R))) == [f"{U}/{CID_3}.json"]


# =========================================================================== F-15

D = D_OLD
F15_ROWS = {
    # row: (E last_updated, T last_updated, winner)
    "a-E-undated-T-dated": (ABSENT, D, "T"),
    "b-E-dated-T-undated": (D, ABSENT, "E"),
    "c-both-undated": (ABSENT, ABSENT, "E"),
    "d-E-int7-T-dated": (7, D, "T"),
}


@pytest.mark.parametrize("row", list(F15_ROWS))
def test_f15_undated_copy_is_oldest_in_a_collision(tmp_path, row):
    """F-15: an undated / non-string copy keys as ""; a tie keeps the incumbent (strict >)."""
    e_lu, t_lu, winner = F15_ROWS[row]
    w = new_world(tmp_path / "w")
    e_bytes = conv(CID_COLLIDE, e_lu, "existing copy E")[1]
    t_name, t_bytes = conv(CID_COLLIDE, t_lu, "book copy T")
    put_file(w.R / U / t_name, e_bytes)
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[(t_name, t_bytes)])

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert (w.R / U / t_name).read_bytes() == (t_bytes if winner == "T" else e_bytes)


def test_f15a_delete_path_dated_copy_beats_undated_incumbent(tmp_path):
    """F-15(a) on the delete path: delete_book(false) returns and leaves the same R as the sweep leg."""
    w = new_world(tmp_path / "w")
    e_bytes = conv(CID_COLLIDE, ABSENT, "existing copy E")[1]
    t_name, t_bytes = conv(CID_COLLIDE, D, "book copy T")
    put_file(w.R / U / t_name, e_bytes)
    make_book(w.books, "a_data", book_uuid=U, convs=[(t_name, t_bytes)])

    w.delete(mode=False)

    assert "a_data" not in listing(w.books)
    assert dot_entries(w.books) == []
    assert _files(tree_bytes(w.R)) == {f"{U}/{t_name}": t_bytes}



# =========================================================================== CP2 additions (WI-5 test-review gaps)
#
# Additive only: the recorded cases above are unchanged. Each block names the CP2 gap and ruling.


# --------------------------------------------------------------------------- M1: F-15, the BOOK copy is the non-string 7 (W5-22)

F15_INT_BOOK_ROWS = {
    # row: (E last_updated, T last_updated, winner). T = 7 keys as "", the oldest value.
    "i-E-dated-T-int7": (D, 7, "E"),
    "ii-E-undated-T-int7": (ABSENT, 7, "E"),  # "" vs "": a tie keeps the incumbent (strict >)
}


@pytest.mark.parametrize("row", list(F15_INT_BOOK_ROWS))
def test_f15_non_string_book_copy_keys_as_oldest(tmp_path, row):
    """F-15 (CP2 M1, W5-22): a book copy dated ``7`` keys as "" on the book side too, so the
    existing copy wins against a dated incumbent and on the "" tie. Kills a mutation that keys
    the book side with ``str(raw or "")`` ("7" sorts above "2026...") and the existing side with lu_key."""
    e_lu, t_lu, winner = F15_INT_BOOK_ROWS[row]
    w = new_world(tmp_path / "w")
    e_bytes = conv(CID_COLLIDE, e_lu, "existing copy E")[1]
    t_name, t_bytes = conv(CID_COLLIDE, t_lu, "book copy T")
    put_file(w.R / U / t_name, e_bytes)
    p = paired(w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[(t_name, t_bytes)])

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert report.failed == []
    assert (w.R / U / t_name).read_bytes() == (t_bytes if winner == "T" else e_bytes)
    assert not p.tomb.exists()
    assert not p.intent.exists()


# --------------------------------------------------------------------------- M2: bad_target_array (W5-21)


def test_f11_bad_target_array_is_conserved_never_failed(tmp_path, monkeypatch, caplog):
    """F-11 (CP2 M2, W5-21): an existing ``R/U/CID_COLLIDE.json`` that is valid JSON but ``[]``
    is unreadable -> the tombstone is conserved (never ``failed``), tombstone + intent + R kept, every sweep."""
    caplog.set_level(logging.DEBUG)
    w, layout, p, resolver = _f11_world(tmp_path, monkeypatch, "bad_target_array", mode=False)
    assert (w.R / U / f"{CID_COLLIDE}.json").read_bytes() == b"[]"
    r_before = tree_bytes(w.R)
    tomb_before, intent_before, coll_before = tree_bytes(p.tomb), p.intent.read_bytes(), w.coll.read_bytes()
    maps_before = resolver_maps(resolver)

    for n in range(2):
        caplog.clear()
        report = w.sweep()
        assert report.failed == [], f"sweep {n}: {report_dict(report)}"
        assert report.conserved == [p.tomb.name], f"sweep {n}: {report_dict(report)}"
        assert report.finalized == []
        assert tree_bytes(w.R) == r_before
        assert tree_bytes(p.tomb) == tomb_before
        assert p.intent.read_bytes() == intent_before
        assert w.coll.read_bytes() == coll_before
        assert resolver_maps(resolver) == maps_before
        assert any(f"{CID_COLLIDE}.json" in msg for msg in _messages(caplog, logging.WARNING)), _messages(caplog)


# --------------------------------------------------------------------------- M3: live same-name book + unreadable conversation (W5-16, law 7)


@pytest.mark.parametrize("kind", UNREADABLE_KIND_IDS)
def test_f12_live_same_name_with_unreadable_conversation_is_conserved(
    tmp_path, monkeypatch, caplog, chroma_env, kind  # noqa: F811
):
    """F-12 x F-11 (CP2 M3, W5-16 / law 7): a live re-imported a_data (U2) does NOT turn a failed
    pre-scan into a finalize. W5-13 applies: R byte-identical, tombstone + intent kept, no collections /
    resolver / chroma / invalidator effect, the live book untouched -- on every sweep."""
    caplog.set_level(logging.DEBUG)
    m = isolate_invalidators(monkeypatch)
    w = new_world(tmp_path / "w")
    layout = schema_kind_layout(kind)
    put_file(w.R / U / f"{CID_COLLIDE}.json", layout.target)
    write_collections(w.coll, {"C": ["a_data"]})
    uuid = None if layout.uuid_null else U
    p = paired(w.books, "a_data", mode=False, uuid=uuid, root=w.R, coll=w.coll, book_uuid=U, convs=layout.convs)
    make_book(w.books, "a_data", title="Alpha 2", body="AAAA again", book_uuid=U2)
    assert "a_data" in listing(w.books), "precondition: the same-name book is live"
    resolver = seat_resolver(monkeypatch, w.books)
    probe = IdentityProbe(resolver, "a_data", U2, w.books / "a_data" / "chroma_db")

    scoped, global_ = InvalidatorRecorder(), InvalidatorRecorder()
    m.register_invalidator(scoped, folder_scoped=True)
    m.register_invalidator(global_, folder_scoped=False)

    r_before = tree_bytes(w.R)
    tomb_before, intent_before, coll_before = tree_bytes(p.tomb), p.intent.read_bytes(), w.coll.read_bytes()
    live_before = tree_bytes(w.books / "a_data")
    outside_before = _outside_r_and_books(w.root)

    for n in range(2):
        caplog.clear()
        report = w.sweep()
        assert report.conserved == [p.tomb.name], f"sweep {n}: {report_dict(report)}"
        assert report.finalized == []
        assert report.failed == []
        assert tree_bytes(w.R) == r_before
        assert _outside_r_and_books(w.root) == outside_before
        assert tree_bytes(p.tomb) == tomb_before
        assert p.intent.read_bytes() == intent_before
        assert w.coll.read_bytes() == coll_before
        assert read_collections(w.coll) == {"C": ["a_data"]}
        assert scoped.calls == [] and global_.calls == []
        assert resolver._folder_to_uuid["a_data"] == U2
        assert resolver._uuid_to_folder[U2] == "a_data"
        probe.assert_untouched()
        assert tree_bytes(w.books / "a_data") == live_before
        assert any(layout.bad_name in msg for msg in _messages(caplog, logging.WARNING)), _messages(caplog)


# --------------------------------------------------------------------------- L2: F-12 still runs the global invalidation (W5-16)


def _warm_live_caches(books, folder="a_data"):
    from reader3_app import book_store, search_service

    book_store.load_book_cached(folder, str(books))
    search_service.load_book_index(folder, str(books), case_sensitive=False)
    assert book_store.load_book_cached.cache_info().currsize >= 1
    assert search_service.load_book_index.cache_info().currsize >= 1


def test_f12_live_same_name_still_runs_global_invalidation(tmp_path, monkeypatch, caplog):
    """F-12 (CP2 L2, W5-16): with a live same-name book the finalizer skips only the folder-scoped
    effects; the global ones (book / index caches, non-folder-scoped invalidators incl. the server's
    stats generation) still run."""
    from reader3_app import book_store, search_service

    caplog.set_level(logging.DEBUG)
    m = isolate_invalidators(monkeypatch)
    server = server_module()
    w = new_world(tmp_path / "w")
    p = paired(
        w.books, "a_data", mode=False, uuid=U, root=w.R, coll=w.coll, book_uuid=U, convs=[conv(CID_FRESH, D_MID, "fresh")]
    )
    make_book(w.books, "a_data", title="Alpha 2", body="AAAA again", book_uuid=U2)
    write_collections(w.coll, {"C": ["a_data"]})
    resolver = seat_resolver(monkeypatch, w.books)
    warm(resolver, "a_data", U2)

    scoped, global_ = InvalidatorRecorder(), InvalidatorRecorder()
    m.register_invalidator(scoped, folder_scoped=True)
    m.register_invalidator(global_, folder_scoped=False)
    _warm_live_caches(w.books)
    g0 = getattr(server, "_stats_generation")

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert read_collections(w.coll) == {"C": ["a_data"]}
    assert global_.calls == [("a_data", U)]
    assert scoped.calls == []
    assert book_store.load_book_cached.cache_info().currsize == 0
    assert search_service.load_book_index.cache_info().currsize == 0
    assert getattr(server, "_stats_generation") > g0
    assert resolver._folder_to_uuid["a_data"] == U2


# --------------------------------------------------------------------------- L3: null / "" last_updated are readable kinds (W5-17)


@pytest.mark.parametrize(("kind", "klass", "reason"), READABLE_LU_KINDS, ids=READABLE_LU_KIND_IDS)
def test_f11_null_and_empty_last_updated_are_readable(tmp_path, monkeypatch, caplog, kind, klass, reason):
    """F-11 leg (i) (CP2 L3, W5-17): ``last_updated: null`` and ``""`` publish like the other readable kinds."""
    caplog.set_level(logging.DEBUG)
    w, layout, p, resolver = _f11_world(tmp_path, monkeypatch, kind, mode=False)

    report = w.sweep()

    assert report.finalized == [p.tomb.name]
    assert report.conserved == [] and report.failed == []
    expected = {f"{U}/{name}": payload for name, payload in layout.convs}
    assert _files(tree_bytes(w.R)) == expected
    assert len(expected) == 4
    assert not p.tomb.exists()
    assert not p.intent.exists()
    assert read_collections(w.coll) == {"c1": []}
    assert not any(
        ("unreadable" in msg.lower() or "conserv" in msg.lower()) for msg in _messages(caplog, logging.WARNING)
    ), _messages(caplog)
    assert report_dict(w.sweep()) == EMPTY_REPORT
