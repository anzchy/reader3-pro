"""WI-2: collections read-modify-write is serialised, and the publish is durable.

All four mutators in ``collections_service`` are load -> mutate -> save of the
whole ``config/library_collections.json``. Without a lock across the three steps
two writers each read N collections and each write their own N', and the disk
keeps whichever renamed last: an added book vanishes, a deleted collection comes
back, two collections share a name. Nothing raises. So the load-bearing
assertions below read the file back; "did it raise" is never enough on its own.

How the races are manufactured
------------------------------
A pass-through spy on ``collections_service.save_collections`` parks each
writer at a ``Barrier`` between its load and its save. Without the lock both
writers arrive and the rendezvous happens; with the lock the second writer is
parked on the lock and can never arrive, so the barrier times out and breaks.
That broken barrier is itself the evidence of mutual exclusion (W2-C1).

Every mutator call in a concurrency case is bounded (``JOIN_TIMEOUT_S``): the
repo has no pytest-timeout, so a lock taken twice must fail red, not hang the
lane. Every child interpreter carries ``timeout=60``.

Cases W2-C1..C11 follow ``.claude/tdd-guardian/tests-20260926-154111.md``.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import itertools
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader3_app import collections_service as cs
from reader3_app.collections_service import Collection

JOIN_TIMEOUT_S = 10.0
BARRIER_TIMEOUT_S = 0.5
LOCK_NAME = "library_collections.json.lock"
DATA_NAME = "library_collections.json"
ALPHABET = [f"b{i}_data" for i in range(6)]


# --------------------------------------------------------------------------- #
# Bounded threads
# --------------------------------------------------------------------------- #


class _Bounded:
    """A thread running ``fn`` whose outcome is collected, never lost."""

    def __init__(self, fn: Callable[[], Any], name: Optional[str] = None) -> None:
        self.result: Any = None
        self.exc: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)

    def _run(self, fn: Callable[[], Any]) -> None:
        try:
            self.result = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised or inspected by the test
            self.exc = e

    def start(self) -> "_Bounded":
        self.thread.start()
        return self

    def settle(self, timeout: float = JOIN_TIMEOUT_S) -> "_Bounded":
        self.thread.join(timeout)
        if self.thread.is_alive():
            pytest.fail(f"hung: thread {self.thread.name} still alive after {timeout}s")
        return self


def _outcome(b: _Bounded) -> str:
    """Thread outcome as a type name only.

    Failure output stays free of ``strerror`` text: the red of the fixed-tmp-name
    bug is an ENOENT, and its message would otherwise read like a missing runner.
    """
    return "ok" if b.exc is None else type(b.exc).__name__


def run_bounded(fn: Callable[[], Any], timeout: float = JOIN_TIMEOUT_S) -> Any:
    b = _Bounded(fn).start().settle(timeout)
    if b.exc is not None:
        raise b.exc
    return b.result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _PauseSpy:
    """Pass-through wrapper on ``save_collections`` that parks at a barrier first."""

    def __init__(self, real: Callable[..., None], parties: int = 2) -> None:
        self.real = real
        self.barrier = threading.Barrier(parties)
        self.broke = False
        self.arrivals = 0
        self._guard = threading.Lock()
        self.before_save: Optional[Callable[[], None]] = None
        self.after_save: Optional[Callable[[], None]] = None

    def __call__(self, path: Path, collections: list[Collection]) -> None:
        with self._guard:
            self.arrivals += 1
        try:
            self.barrier.wait(timeout=BARRIER_TIMEOUT_S)
        except threading.BrokenBarrierError:
            self.broke = True
        if self.before_save is not None:
            self.before_save()
        self.real(path, collections)
        if self.after_save is not None:
            self.after_save()


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return cs.collections_path(str(tmp_path))


@pytest.fixture
def pause_spy(monkeypatch: pytest.MonkeyPatch) -> _PauseSpy:
    spy = _PauseSpy(cs.save_collections)
    monkeypatch.setattr(cs, "save_collections", spy)
    return spy


# --------------------------------------------------------------------------- #
# W2-C1 lost update
# --------------------------------------------------------------------------- #


def test_c1_concurrent_updates_keep_both_adds(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = cs.create_collection(path, name="Shelf")
    spy = _PauseSpy(cs.save_collections)
    monkeypatch.setattr(cs, "save_collections", spy)

    t1 = _Bounded(lambda: cs.update_collection_books(path, c.id, add=["a_data"]), name="T1").start()
    t2 = _Bounded(lambda: cs.update_collection_books(path, c.id, add=["b_data"]), name="T2").start()
    t1.settle()
    t2.settle()

    assert [_outcome(t1), _outcome(t2)] == ["ok", "ok"]
    got = cs.get_collection(path, c.id)
    assert got is not None
    assert sorted(got.book_ids) == ["a_data", "b_data"]
    assert spy.arrivals == 2
    assert spy.broke is True, "both saves were pending at once: no mutual exclusion"


# --------------------------------------------------------------------------- #
# W2-C2 delete vs update/rename never resurrects
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("racer", ["update", "rename"])
def test_c2_delete_is_never_resurrected(path: Path, pause_spy: _PauseSpy, racer: str) -> None:
    c = cs.create_collection(path, name="Doomed")
    delete_saved = threading.Event()

    def before() -> None:
        if threading.current_thread().name == "racer":
            delete_saved.wait(timeout=BARRIER_TIMEOUT_S)

    def after() -> None:
        if threading.current_thread().name == "deleter":
            delete_saved.set()

    pause_spy.before_save = before
    pause_spy.after_save = after

    if racer == "update":
        racer_fn: Callable[[], Any] = lambda: cs.update_collection_books(path, c.id, add=["x_data"])
    else:
        racer_fn = lambda: cs.rename_collection(path, c.id, name="Renamed")

    t_del = _Bounded(lambda: cs.delete_collection(path, c.id), name="deleter").start()
    t_racer = _Bounded(racer_fn, name="racer").start()
    t_del.settle()
    t_racer.settle()

    assert _outcome(t_del) == "ok"
    assert cs.get_collection(path, c.id) is None
    assert cs.load_collections(path) == []

    succeeded = t_racer.exc is None and isinstance(t_racer.result, Collection)
    if succeeded:
        if racer == "update":
            assert t_racer.result.book_ids == ["x_data"]
        else:
            assert t_racer.result.name == "Renamed"
    raised_keyerror = isinstance(t_racer.exc, KeyError)
    assert succeeded != raised_keyerror, _outcome(t_racer)


# --------------------------------------------------------------------------- #
# W2-C3 duplicate-name race
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pair",
    [
        ("create:Reading", "create:Reading"),
        ("create:Reading", "create:reading"),
        ("rename:Reading", "create:Reading"),
    ],
)
def test_c3_duplicate_name_race_has_one_winner(
    path: Path, monkeypatch: pytest.MonkeyPatch, pair: tuple[str, str]
) -> None:
    alpha = cs.create_collection(path, name="Alpha") if pair[0].startswith("rename") else None
    spy = _PauseSpy(cs.save_collections)
    monkeypatch.setattr(cs, "save_collections", spy)

    def op(spec: str) -> Callable[[], Collection]:
        kind, name = spec.split(":")
        if kind == "create":
            return lambda: cs.create_collection(path, name=name)
        assert alpha is not None
        return lambda: cs.rename_collection(path, alpha.id, name=name)

    threads = [_Bounded(op(s), name=f"op{i}").start() for i, s in enumerate(pair)]
    for t in threads:
        t.settle()

    errors = [t.exc for t in threads if t.exc is not None]
    winners = [t.result for t in threads if t.exc is None]
    assert sorted(_outcome(t) for t in threads) == ["ValueError", "ok"]
    assert "already exists" in str(errors[0])
    assert len(winners) == 1
    r = winners[0]

    on_disk = cs.load_collections(path)
    assert [c.name.lower() for c in on_disk].count("reading") == 1
    (reading,) = [c for c in on_disk if c.name.lower() == "reading"]
    assert reading.id == r.id


# --------------------------------------------------------------------------- #
# W2-C4 every mutator honours a real external flock, and reloads inside it
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("op", ["create", "rename", "delete", "update"])
def test_c4_every_mutator_honours_flock_and_reloads(path: Path, op: str) -> None:
    a = cs.create_collection(path, name="Alpha")

    fns: dict[str, Callable[[], Any]] = {
        "create": lambda: cs.create_collection(path, name="Beta"),
        "rename": lambda: cs.rename_collection(path, a.id, name="Renamed"),
        "delete": lambda: cs.delete_collection(path, a.id),
        "update": lambda: cs.update_collection_books(path, a.id, add=["x_data"]),
    }

    lock_path = path.parent / LOCK_NAME
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    t: Optional[_Bounded] = None
    z = Collection(id=str(uuid.uuid4()), name="Zeta", created_at="2026-01-01T00:00:00+00:00", book_ids=[])
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        sha0 = _sha(path)
        t = _Bounded(fns[op], name=f"mutator-{op}").start()
        t.thread.join(0.3)
        assert t.thread.is_alive(), f"{op} did not wait for the lock holder"
        assert _sha(path) == sha0
        # Another process's committed write, made while the lock is held.
        cs.save_collections(path, cs.load_collections(path) + [z])
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    t.settle()

    assert _outcome(t) == "ok"
    if op == "delete":
        assert t.result is None
    else:
        assert isinstance(t.result, Collection)

    on_disk = {c.name: c for c in cs.load_collections(path)}
    assert "Zeta" in on_disk, "mutator loaded before blocking and wrote Z away"
    if op == "create":
        assert "Beta" in on_disk and "Alpha" in on_disk
    elif op == "rename":
        assert "Renamed" in on_disk and "Alpha" not in on_disk
    elif op == "delete":
        assert "Alpha" not in on_disk
    else:
        assert on_disk["Alpha"].book_ids == ["x_data"]


# --------------------------------------------------------------------------- #
# W2-C5 linearizability property
# --------------------------------------------------------------------------- #


def _apply(ids: list[str], op: tuple[list[str], list[str]]) -> list[str]:
    add, remove = op
    out = list(ids)
    for b in add:
        if b not in out:
            out.append(b)
    return [b for b in out if b not in set(remove)]


_ids = st.lists(st.sampled_from(ALPHABET), unique=True, max_size=len(ALPHABET))
_op = st.tuples(
    st.lists(st.sampled_from(ALPHABET), unique=True, max_size=3),
    st.lists(st.sampled_from(ALPHABET), unique=True, max_size=2),
)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(initial=_ids, ops=st.lists(_op, min_size=2, max_size=4))
def test_c5_concurrent_batches_are_linearizable(
    tmp_path: Path, initial: list[str], ops: list[tuple[list[str], list[str]]]
) -> None:
    root = tempfile.mkdtemp(dir=tmp_path)
    p = cs.collections_path(root)
    c = cs.create_collection(p, name="Prop")
    cs.update_collection_books(p, c.id, add=initial)

    real = cs.save_collections
    start = threading.Barrier(len(ops), timeout=5)

    def delayed(path_: Path, cols: list[Collection]) -> None:
        time.sleep(0.003)
        real(path_, cols)

    def worker(op: tuple[list[str], list[str]]) -> Callable[[], Collection]:
        def run() -> Collection:
            start.wait()
            return cs.update_collection_books(p, c.id, add=op[0], remove=op[1])

        return run

    cs.save_collections = delayed  # type: ignore[assignment]
    try:
        threads = [_Bounded(worker(op)).start() for op in ops]
        for t in threads:
            t.settle()
    finally:
        cs.save_collections = real  # type: ignore[assignment]

    assert [_outcome(t) for t in threads] == ["ok"] * len(ops)

    got = cs.get_collection(p, c.id)
    assert got is not None
    final = got.book_ids

    candidates = []
    for perm in itertools.permutations(ops):
        ids = list(initial)
        for op in perm:
            ids = _apply(ids, op)
        candidates.append(ids)
    assert final in candidates, (final, initial, ops)

    never_removed_adds = {b for op in ops for b in op[0] if all(b not in o[1] for o in ops)}
    assert never_removed_adds <= set(final)


# --------------------------------------------------------------------------- #
# W2-C6 cross-process
# --------------------------------------------------------------------------- #

_CHILD = """
import sys
from pathlib import Path
from reader3_app import collections_service as cs
path, cid, k, m = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
for i in range(m):
    cs.update_collection_books(path, cid, add=[f"p{k}_{i}_data"])
"""


def test_c6_two_processes_conserve_every_add(path: Path) -> None:
    m = 40
    c = cs.create_collection(path, name="Cross")
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(path), c.id, str(k), str(m)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for k in (0, 1)
    ]
    outs = []
    try:
        for p in procs:
            outs.append(p.communicate(timeout=60))
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=60)

    got = cs.get_collection(path, c.id)
    assert got is not None
    expected = {f"p{k}_{i}_data" for k in (0, 1) for i in range(m)}
    assert len(set(got.book_ids)) == 2 * m
    assert set(got.book_ids) == expected
    for p, (_, err) in zip(procs, outs):
        assert p.returncode == 0, err


# --------------------------------------------------------------------------- #
# W2-C7 failing mutators release the lock and leave the file unchanged
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("klass", ["a", "b", "c", "d", "e"])
def test_c7_failing_mutator_releases_lock_and_leaves_file(path: Path, klass: str) -> None:
    a = cs.create_collection(path, name="Alpha")
    original = path.read_bytes()

    if klass == "e":
        path.write_text("{", encoding="utf-8")
    sha0 = _sha(path)

    cases: dict[str, tuple[Callable[[], Any], type[BaseException]]] = {
        "a": (lambda: cs.delete_collection(path, "missing"), KeyError),
        "b": (lambda: cs.rename_collection(path, "missing", name="N"), KeyError),
        "c": (lambda: cs.create_collection(path, name="bad/name"), ValueError),
        "d": (lambda: cs.update_collection_books(path, a.id, add=["../x"]), ValueError),
        "e": (lambda: cs.create_collection(path, name="Other"), cs.CollectionsFileError),
    }
    fn, exc_type = cases[klass]
    with pytest.raises(exc_type):
        run_bounded(fn)
    assert _sha(path) == sha0

    if klass == "e":
        path.write_bytes(original)
    after = run_bounded(lambda: cs.create_collection(path, name="After"))
    assert isinstance(after, Collection)
    assert set(os.listdir(path.parent)) <= {DATA_NAME, LOCK_NAME}


# --------------------------------------------------------------------------- #
# W2-C8 serialisation failure mid-write
# --------------------------------------------------------------------------- #


def test_c8_partial_write_failure_leaves_old_file_and_no_scratch(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = cs.create_collection(path, name="Alpha")
    sha0 = _sha(path)
    listing0 = set(os.listdir(path.parent))

    def broken_dump(obj: Any, f: Any, *args: Any, **kwargs: Any) -> None:
        f.write('{"schema_version": 1, "coll')
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(cs.json, "dump", broken_dump)
    with pytest.raises(OSError) as ei:
        run_bounded(lambda: cs.update_collection_books(path, a.id, add=["x_data"]))
    assert ei.value.errno == errno.ENOSPC
    monkeypatch.undo()

    assert _sha(path) == sha0
    assert set(os.listdir(path.parent)) == listing0 | {LOCK_NAME}
    after = run_bounded(lambda: cs.create_collection(path, name="After"))
    assert isinstance(after, Collection)


# --------------------------------------------------------------------------- #
# W2-C9 publish ordering
# --------------------------------------------------------------------------- #


def test_c9_fsync_file_before_replace_and_dir_after(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = Collection(id=str(uuid.uuid4()), name="Alpha", created_at="2026-01-01T00:00:00+00:00", book_ids=[])
    events: list[tuple[str, ...]] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd: Any) -> None:
        fileno = fd if isinstance(fd, int) else fd.fileno()
        kind = "dir" if stat.S_ISDIR(os.fstat(fileno).st_mode) else "file"
        events.append(("fsync", kind))
        real_fsync(fd)

    def spy_replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        events.append(("replace", os.fspath(src), os.fspath(dst)))
        real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)
    cs.save_collections(path, [a])
    monkeypatch.undo()

    replaces = [i for i, e in enumerate(events) if e[0] == "replace" and e[2] == str(path)]
    assert len(replaces) == 1, events
    ri = replaces[0]
    assert ("fsync", "file") in events[:ri], events
    assert ("fsync", "dir") in events[ri + 1 :], events
    src = events[ri][1]
    assert Path(src).parent == path.parent
    assert src != str(path) + ".tmp"


# --------------------------------------------------------------------------- #
# W2-C10 round-trip and exact on-disk schema
# --------------------------------------------------------------------------- #

_NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.&()"
_collection = st.builds(
    Collection,
    id=st.uuids().map(str),
    name=st.text(alphabet=_NAME_CHARS, min_size=1, max_size=60),
    created_at=st.datetimes(timezones=st.just(timezone.utc)).map(lambda d: d.isoformat()),
    book_ids=st.lists(
        st.from_regex(r"[a-z0-9]{1,8}", fullmatch=True).map(lambda s: s + "_data"), unique=True, max_size=5
    ),
)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(cols=st.lists(_collection, max_size=5))
def test_c10_round_trip_and_exact_schema(tmp_path: Path, cols: list[Collection]) -> None:
    p = cs.collections_path(tempfile.mkdtemp(dir=tmp_path))
    cs.save_collections(p, cols)
    assert cs.load_collections(p) == cols
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw == {"schema_version": 1, "collections": [c.to_dict() for c in cols]}
    assert set(raw) == {"schema_version", "collections"}


# --------------------------------------------------------------------------- #
# W2-C11 fresh install
# --------------------------------------------------------------------------- #


def test_c11_fresh_install_only_new_path_is_lock_file(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    p = cs.collections_path(str(project))
    config = project / "config"
    assert not config.exists()
    expected = [DATA_NAME, LOCK_NAME]

    c = cs.create_collection(p, name="One")
    assert sorted(os.listdir(config)) == expected
    cs.rename_collection(p, c.id, name="Two")
    assert sorted(os.listdir(config)) == expected
    cs.update_collection_books(p, c.id, add=["x_data"])
    assert sorted(os.listdir(config)) == expected
    cs.delete_collection(p, c.id)
    assert sorted(os.listdir(config)) == expected
