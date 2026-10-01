"""fsync-order audit: wrap os.open / os.fsync / os.replace / os.rename and check the barriers.

Default mode (plain os.fsync). This proves ordering only -- not that the disk honoured it.
"""
import os
import sys

import pytest

from proto import common as c
from proto import harness as h


def _trace(monkeypatch, book):
    events, fds = [], {}
    real_open, real_fsync, real_replace, real_rename = os.open, os.fsync, os.replace, os.rename
    rel = lambda p: os.path.relpath(os.fspath(p), book)  # noqa: E731

    def o(path, *a, **kw):
        fd = real_open(path, *a, **kw)
        fds[fd] = rel(path)
        return fd

    def fs(fd):
        events.append(("fsync", fds.get(fd, "?")))
        real_fsync(fd)

    def rn(real):
        def fn(src, dst, *a, **kw):
            events.append(("rename", rel(src), rel(dst)))
            real(src, dst, *a, **kw)
        return fn

    monkeypatch.setattr(os, "open", o)
    monkeypatch.setattr(os, "fsync", fs)
    monkeypatch.setattr(os, "replace", rn(real_replace))
    monkeypatch.setattr(os, "rename", rn(real_rename))
    return events


def _first(events, pred):
    return next(i for i, e in enumerate(events) if pred(e))


@pytest.mark.parametrize("scenario", ["S0", "S1", "S2", "S3"])
def test_q2_fsync_order_a(tmp_path, monkeypatch, scenario):
    book = h.setup("A", scenario, str(tmp_path))
    events = _trace(monkeypatch, book)
    h.MECH["A"]["publish"](book, c.book_contents(c.NEW))
    renames = [i for i, e in enumerate(events) if e[0] == "rename"]
    j = _first(events, lambda e: e[0] == "rename" and e[2] == ".publish-journal.json")
    jtmp = events[j][1]
    a8 = renames[renames.index(j) + 1]
    assert ("fsync", jtmp) in events[:j]                     # journal content durable before it appears
    assert ("fsync", ".") in events[j:a8]                    # journal's dir entry durable before a8
    # every staged payload file fsynced before the journal (hence before any live rename)
    staged = {e[1] for e in events if e[0] == "rename" and e[1].startswith(".staging") and "/aside/" not in e[1]}
    for s in staged - {jtmp}:
        if os.path.basename(s) != "images":
            assert ("fsync", s) in events[:j], s
    # after every rename, before the next one (or before return): the destination dir and the
    # book dir are fsynced. A source dir inside staging is garbage after commit and is not required.
    for k, i in enumerate(renames):
        nxt = renames[k + 1] if k + 1 < len(renames) else len(events)
        _, src, dst = events[i]
        for d in {os.path.dirname(dst) or ".", "."}:
            assert ("fsync", d) in events[i + 1:nxt], (events[i], d)
    commit = _first(events, lambda e: e[0] == "rename" and e[2] == "manifest.json")
    assert commit == renames[-1]


@pytest.mark.parametrize("scenario", ["S0", "S1", "S2", "S3"])
def test_q2_fsync_order_b(tmp_path, monkeypatch, scenario):
    book = h.setup("B", scenario, str(tmp_path))
    events = _trace(monkeypatch, book)
    h.MECH["B"]["publish"](book, c.book_contents(c.NEW))
    renames = [e for e in events if e[0] == "rename"]
    assert renames == [("rename", "manifest.json.tmp", "manifest.json")]
    b8 = events.index(renames[0])
    g = c.load_manifest(book)["generation"]
    gdir = os.path.join(c.GEN, str(g))
    must = {gdir, c.GEN, "."}
    for dirpath, dirs, files in os.walk(os.path.join(book, gdir)):
        must.add(os.path.relpath(dirpath, book))
        must.update(os.path.relpath(os.path.join(dirpath, f), book) for f in files)
    synced = {e[1] for e in events[:b8] if e[0] == "fsync"}
    assert must <= synced, must - synced
    assert ("fsync", "manifest.json.tmp") in events[:b8]
    assert ("fsync", ".") in events[b8 + 1:]


@pytest.mark.skipif(sys.platform != "darwin", reason="F_FULLFSYNC is macOS-only")
@pytest.mark.parametrize("mech", ["A", "B"])
def test_q2_durable_fsync_uses_full_fsync_on_macos(tmp_path, monkeypatch, mech):
    import fcntl

    calls = []
    real = fcntl.fcntl
    monkeypatch.setenv("PROTO_FULLFSYNC", "1")
    monkeypatch.setattr(fcntl, "fcntl", lambda fd, op, *a: calls.append(op) or real(fd, op, *a))
    book = h.setup(mech, "S1", str(tmp_path))
    h.MECH[mech]["publish"](book, c.book_contents(c.NEW))
    assert calls and set(calls) == {fcntl.F_FULLFSYNC}
    assert c.classify(book, mech) == ("new-valid", 0)
