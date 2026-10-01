"""WI-3: a ``BookUuidResolver`` cache hit agrees with ``ai_meta.json`` on disk.

The resolver used to trust its two dicts forever. Delete ``x_data`` and
reprocess the book (or restore a different one under the same folder name) and
the cached uuid kept answering: the old uuid still resolved to a folder that now
held another book, and every AI conversation attached to the wrong identity.
Nothing raised.

So every assertion below compares the resolver against the *disk*, never
against its private dicts. Two rules from ADR-0003 run through all of it:

* a file that already holds a valid uuid is never rewritten, not even to
  canonicalise its spelling (``st_ino``/``st_mtime_ns``/sha unchanged);
* a file that cannot be read is refused, never overwritten with a fresh uuid.

Real files under ``tmp_path``, no mocks. Every threaded call is bounded
(``run_bounded``): the repo has no pytest-timeout, so a fix that takes the
non-reentrant ``_lock`` twice must fail red, not hang the lane.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from reader3_app.ai.books import AI_META_FILENAME, BookUuidResolver
from reader3_app.web import server

JOIN_TIMEOUT_S = 10.0
X = "x_data"

CORRUPTIONS: Dict[str, str] = {
    "invalid_json": "{",
    "non_object": "[1]",
    "non_string_uuid": '{"book_uuid": 7}',
    "non_uuid_string": '{"book_uuid": "not-a-uuid"}',
}


# --------------------------------------------------------------------------- #
# helpers
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


def run_bounded(fn: Callable[[], Any], timeout: float = JOIN_TIMEOUT_S) -> Any:
    b = _Bounded(fn).start().settle(timeout)
    if b.exc is not None:
        raise b.exc
    return b.result


def _u() -> str:
    return str(uuid.uuid4())


def _meta(folder: Path) -> Path:
    return folder / AI_META_FILENAME


def _write_meta(folder: Path, payload: Any) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = _meta(folder)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    p.write_text(text, encoding="utf-8")
    return p


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _st(path: Path) -> Tuple[int, int, str]:
    s = path.stat()
    return (s.st_ino, s.st_mtime_ns, _sha(path))


def _recreate(books: Path, name: str, payload: Any = None) -> Path:
    folder = books / name
    shutil.rmtree(folder)
    folder.mkdir()
    (folder / "book.pkl").write_bytes(b"new-book-bytes")
    if payload is not None:
        _write_meta(folder, payload)
    return folder


def _scratch(folder: Path) -> List[str]:
    return sorted(n for n in os.listdir(folder) if n.endswith(".tmp"))


@pytest.fixture
def books(tmp_path: Path) -> Path:
    d = tmp_path / "books"
    d.mkdir()
    return d


def _warm(books: Path, u1: str, name: str = X) -> BookUuidResolver:
    folder = books / name
    folder.mkdir(exist_ok=True)
    (folder / "book.pkl").write_bytes(b"old-book-bytes")
    _write_meta(folder, {"book_uuid": u1})
    r = BookUuidResolver(str(books))
    assert r.book_uuid_for_folder(name) == u1
    assert r.folder_for_book_uuid(u1) == name
    return r


# --------------------------------------------------------------------------- #
# book_uuid_for_folder
# --------------------------------------------------------------------------- #


def test_c1_recreated_with_new_uuid_returns_new_uuid_without_rewriting(books: Path) -> None:
    u1, u2 = _u(), _u()
    r = _warm(books, u1)
    folder = _recreate(books, X, {"book_uuid": u2})
    st0 = _st(_meta(folder))

    assert r.book_uuid_for_folder(X) == u2
    assert _st(_meta(folder)) == st0


def test_c3_recreated_without_meta_mints_fresh_uuid_equal_to_disk(books: Path) -> None:
    u1 = _u()
    r = _warm(books, u1)
    folder = _recreate(books, X)
    assert not _meta(folder).exists()

    v = r.book_uuid_for_folder(X)
    assert v != u1
    assert json.loads(_meta(folder).read_text(encoding="utf-8"))["book_uuid"] == v
    st1 = _st(_meta(folder))

    assert r.book_uuid_for_folder(X) == v
    assert _st(_meta(folder)) == st1
    assert _scratch(folder) == []


def test_c4_deleted_folder_raises_is_not_resurrected_and_degrades(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    u1 = _u()
    r = _warm(books, u1)
    shutil.rmtree(books / X)
    listing0 = sorted(os.listdir(books))
    monkeypatch.setattr(server, "book_uuid_resolver", r)

    with pytest.raises(OSError):
        r.book_uuid_for_folder(X)
    assert not (books / X).exists()
    assert sorted(os.listdir(books)) == listing0

    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    assert not (books / X).exists()
    assert sorted(os.listdir(books)) == listing0

    assert server._book_uuid_or_none(X) is None
    assert not (books / X).exists()
    assert sorted(os.listdir(books)) == listing0


@pytest.mark.parametrize("repair_kind", ["same_as_cached", "new"])
@pytest.mark.parametrize("corruption", sorted(CORRUPTIONS))
def test_c5_corrupt_after_cache_is_refused_without_writing_then_repair_resolves(
    books: Path, monkeypatch: pytest.MonkeyPatch, corruption: str, repair_kind: str
) -> None:
    u1 = _u()
    r = _warm(books, u1)
    monkeypatch.setattr(server, "book_uuid_resolver", r)
    folder = books / X
    meta = _write_meta(folder, CORRUPTIONS[corruption])
    st0 = _st(meta)
    listing0 = sorted(os.listdir(folder))

    with pytest.raises(ValueError):
        r.book_uuid_for_folder(X)
    assert _st(meta) == st0
    assert sorted(os.listdir(folder)) == listing0

    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    assert _st(meta) == st0
    assert sorted(os.listdir(folder)) == listing0

    assert server._book_uuid_or_none(X) is None
    assert _st(meta) == st0
    assert sorted(os.listdir(folder)) == listing0

    repair = u1 if repair_kind == "same_as_cached" else _u()
    _write_meta(folder, {"book_uuid": repair})
    st_rep = _st(meta)
    assert r.book_uuid_for_folder(X) == repair
    assert r.folder_for_book_uuid(repair) == X
    assert _st(meta) == st_rep


def test_c6_meta_without_uuid_after_cache_takes_miss_path_and_keeps_keys(books: Path) -> None:
    u1 = _u()
    r = _warm(books, u1)
    folder = books / X
    _write_meta(folder, {"indexed_at": 1724})

    v = r.book_uuid_for_folder(X)
    assert v != u1
    assert json.loads(_meta(folder).read_text(encoding="utf-8")) == {"indexed_at": 1724, "book_uuid": v}
    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)


def test_c7_unreadable_meta_after_cache_propagates_without_minting(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores file permissions")
    u1 = _u()
    r = _warm(books, u1)
    monkeypatch.setattr(server, "book_uuid_resolver", r)
    folder = books / X
    meta = _meta(folder)
    ino0, sha0 = meta.stat().st_ino, _sha(meta)
    listing0 = sorted(os.listdir(folder))

    os.chmod(meta, 0)
    try:
        with pytest.raises(PermissionError):
            r.book_uuid_for_folder(X)
        assert server._book_uuid_or_none(X) is None
    finally:
        os.chmod(meta, stat.S_IRUSR | stat.S_IWUSR)
    assert meta.stat().st_ino == ino0
    assert _sha(meta) == sha0
    assert sorted(os.listdir(folder)) == listing0


def test_c8_unchanged_disk_hits_are_stable_and_read_only(books: Path) -> None:
    u1 = _u()
    r = _warm(books, u1)
    folder = books / X
    st0 = _st(_meta(folder))
    listing0 = sorted(os.listdir(folder))

    forward = []
    reverse = []
    for _ in range(50):
        forward.append(r.book_uuid_for_folder(X))
        reverse.append(r.folder_for_book_uuid(u1))

    assert forward == [u1] * 50
    assert reverse == [X] * 50
    assert _st(_meta(folder)) == st0
    assert sorted(os.listdir(folder)) == listing0


SPELLINGS: Dict[str, Callable[[str], str]] = {
    "padded_upper": lambda u: f"  {u.upper()}  ",
    "hex": lambda u: uuid.UUID(u).hex,
    "braced": lambda u: "{" + u + "}",
}


@pytest.mark.parametrize("spelling", sorted(SPELLINGS))
def test_c13_non_canonical_spelling_is_canonicalised_on_every_hit_never_rewritten(
    books: Path, spelling: str
) -> None:
    encode = SPELLINGS[spelling]
    u1, u2 = _u(), _u()
    folder = books / X
    meta = _write_meta(folder, {"book_uuid": encode(u1)})
    st0 = _st(meta)
    listing0 = sorted(os.listdir(folder))

    r = BookUuidResolver(str(books))
    w = r.book_uuid_for_folder(X)
    assert u1 == str(uuid.UUID(u1))
    assert w == u1

    forward = []
    reverse = []
    for _ in range(10):
        forward.append(r.book_uuid_for_folder(X))
        reverse.append(r.folder_for_book_uuid(u1))
        reverse.append(r.folder_for_book_uuid(u1.upper()))
    assert forward == [u1] * 10
    assert reverse == [X] * 20
    assert _st(meta) == st0
    assert sorted(os.listdir(folder)) == listing0

    _write_meta(folder, {"book_uuid": encode(u2)})
    st2 = _st(meta)
    assert r.book_uuid_for_folder(X) == u2
    assert r.folder_for_book_uuid(u2.upper()) == X
    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    assert _st(meta) == st2


# --------------------------------------------------------------------------- #
# folder_for_book_uuid
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("order", ["reverse_first", "forward_first"])
def test_c2_recreated_with_new_uuid_reverse_lookup_in_both_orders(books: Path, order: str) -> None:
    u1, u2 = _u(), _u()
    r = _warm(books, u1)
    folder = _recreate(books, X, {"book_uuid": u2})
    st0 = _st(_meta(folder))

    if order == "reverse_first":
        with pytest.raises(KeyError):
            r.folder_for_book_uuid(u1)
        assert r.folder_for_book_uuid(u2) == X
        assert r.book_uuid_for_folder(X) == u2
    else:
        assert r.book_uuid_for_folder(X) == u2
        with pytest.raises(KeyError):
            r.folder_for_book_uuid(u1)
        assert r.folder_for_book_uuid(u2) == X
    assert _st(_meta(folder)) == st0


def test_c9_moved_folder_is_rediscovered(books: Path) -> None:
    u1 = _u()
    r = _warm(books, u1)
    os.rename(books / X, books / "y_data")
    st0 = _st(_meta(books / "y_data"))

    assert r.folder_for_book_uuid(u1) == "y_data"
    assert r.book_uuid_for_folder("y_data") == u1
    with pytest.raises(OSError):
        r.book_uuid_for_folder(X)
    assert not (books / X).exists()
    assert _st(_meta(books / "y_data")) == st0


def test_c10_concurrent_invalidation_after_recreate(books: Path) -> None:
    u1, u2 = _u(), _u()
    r = _warm(books, u1)
    folder = _recreate(books, X, {"book_uuid": u2})
    st0 = _st(_meta(folder))
    barrier = threading.Barrier(8, timeout=5)

    def forward() -> str:
        barrier.wait()
        return r.book_uuid_for_folder(X)

    def reverse() -> str:
        barrier.wait()
        return r.folder_for_book_uuid(u1)

    workers = [_Bounded(forward, name=f"fwd{i}") for i in range(4)]
    workers += [_Bounded(reverse, name=f"rev{i}") for i in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.settle()

    fwd_outcomes = [(type(w.exc).__name__ if w.exc else "ok", w.result) for w in workers[:4]]
    rev_outcomes = [type(w.exc).__name__ if w.exc else "ok" for w in workers[4:]]
    assert fwd_outcomes == [("ok", u2)] * 4
    assert rev_outcomes == ["KeyError"] * 4

    assert run_bounded(lambda: r.folder_for_book_uuid(u2)) == X
    assert run_bounded(lambda: r.book_uuid_for_folder(X)) == u2
    assert _st(_meta(folder)) == st0
    assert _scratch(folder) == []


# --------------------------------------------------------------------------- #
# model-based: the resolver agrees with a disk oracle after every step
# --------------------------------------------------------------------------- #

NAMES = ["a_data", "b_data", "c_data"]


class ResolverVsDisk(RuleBasedStateMachine):
    """Model per existing folder: ``("corrupt", sha)``, ``("valid", uuid, ino, mtime_ns)``
    or ``("pending",)`` (no meta, or meta without a uuid key)."""

    def __init__(self) -> None:
        super().__init__()
        self.root = Path(tempfile.mkdtemp(prefix="w3c11-"))
        self.books = self.root / "books"
        self.books.mkdir()
        self.r = BookUuidResolver(str(self.books))
        self.model: Dict[str, Tuple[Any, ...]] = {}
        self.seen: List[str] = []

    def teardown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # -- oracle helpers -------------------------------------------------- #

    def _held(self) -> set:
        return {s[1] for s in self.model.values() if s[0] == "valid"}

    def _pick_uuid(self, data: st.DataObject) -> str:
        free = [u for u in self.seen if u not in self._held()]
        if free and data.draw(st.booleans(), label="reuse"):
            return data.draw(st.sampled_from(free), label="reused")
        u = _u()
        self.seen.append(u)
        return u

    def _track_valid(self, name: str, u: str) -> None:
        s = _meta(self.books / name).stat()
        self.model[name] = ("valid", u, s.st_ino, s.st_mtime_ns)

    def _disk_uuid(self, name: str) -> Optional[str]:
        p = _meta(self.books / name)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            raw = data.get("book_uuid") if isinstance(data, dict) else None
            return str(uuid.UUID(raw.strip())) if isinstance(raw, str) and raw.strip() else None
        except (ValueError, AttributeError):
            return None

    def _refresh_pending(self) -> None:
        # A query may legitimately mint for a folder with no uuid (miss path, or
        # scan()). That is the only transition out of "pending".
        for name, s in list(self.model.items()):
            if s[0] == "pending":
                u = self._disk_uuid(name)
                if u is not None:
                    self.seen.append(u)
                    self._track_valid(name, u)

    # -- mutations ------------------------------------------------------- #

    @rule(name=st.sampled_from(NAMES), kind=st.sampled_from(["uuid", "none", "no_uuid_key"]), data=st.data())
    def create(self, name: str, kind: str, data: st.DataObject) -> None:
        if name in self.model:
            return
        folder = self.books / name
        folder.mkdir()
        (folder / "book.pkl").write_bytes(b"pkl")
        if kind == "uuid":
            u = self._pick_uuid(data)
            _write_meta(folder, {"book_uuid": u})
            self._track_valid(name, u)
        elif kind == "no_uuid_key":
            _write_meta(folder, {"indexed_at": 1})
            self.model[name] = ("pending",)
        else:
            self.model[name] = ("pending",)

    @rule(name=st.sampled_from(NAMES))
    def delete(self, name: str) -> None:
        if name not in self.model:
            return
        shutil.rmtree(self.books / name)
        del self.model[name]

    @rule(name=st.sampled_from(NAMES), kind=st.sampled_from(sorted(CORRUPTIONS)))
    def corrupt(self, name: str, kind: str) -> None:
        if name not in self.model:
            return
        p = _write_meta(self.books / name, CORRUPTIONS[kind])
        self.model[name] = ("corrupt", _sha(p))

    @rule(name=st.sampled_from(NAMES), data=st.data())
    def repair(self, name: str, data: st.DataObject) -> None:
        if name not in self.model:
            return
        if self.model[name][0] == "valid":
            del self.model[name]  # drop its uuid from _held() before picking
            self.model[name] = ("pending",)
        u = self._pick_uuid(data)
        _write_meta(self.books / name, {"book_uuid": u})
        self._track_valid(name, u)

    @rule(src=st.sampled_from(NAMES), dst=st.sampled_from(NAMES))
    def move(self, src: str, dst: str) -> None:
        if src not in self.model or dst in self.model:
            return
        os.rename(self.books / src, self.books / dst)
        self.model[dst] = self.model.pop(src)

    # -- queries --------------------------------------------------------- #

    @precondition(lambda self: bool(self.model))
    @rule(data=st.data())
    def forward(self, data: st.DataObject) -> None:
        name = data.draw(st.sampled_from(sorted(self.model)), label="forward")
        state = self.model[name]
        if state[0] == "corrupt":
            with pytest.raises((ValueError, OSError)):
                run_bounded(lambda: self.r.book_uuid_for_folder(name))
        else:
            got = run_bounded(lambda: self.r.book_uuid_for_folder(name))
            assert got == self._disk_uuid(name)
        self._refresh_pending()

    @rule(data=st.data())
    def reverse(self, data: st.DataObject) -> None:
        pool = self.seen + [_u()]
        u = data.draw(st.sampled_from(pool), label="reverse")
        try:
            got: Optional[str] = run_bounded(lambda: self.r.folder_for_book_uuid(u))
        except KeyError:
            got = None
        self._refresh_pending()
        holders = [n for n in self.model if self._disk_uuid(n) == u]
        assert len(holders) <= 1
        assert got == (holders[0] if holders else None)

    # -- invariants ------------------------------------------------------ #

    @invariant()
    def disk_matches_model(self) -> None:
        for name, s in self.model.items():
            p = _meta(self.books / name)
            if s[0] == "corrupt":
                assert _sha(p) == s[1], f"{name}: a corrupt file was written"
            elif s[0] == "valid":
                st_ = p.stat()
                assert self._disk_uuid(name) == s[1]
                assert (st_.st_ino, st_.st_mtime_ns) == (s[2], s[3]), f"{name}: a valid file was rewritten"


ResolverVsDisk.TestCase.settings = settings(max_examples=40, stateful_step_count=20, deadline=None)
test_c11_resolver_agrees_with_disk_oracle = ResolverVsDisk.TestCase


# --------------------------------------------------------------------------- #
# folder_for_book_uuid: the post-scan candidate is validated too
# --------------------------------------------------------------------------- #
#
# A thread paused inside ``_load_folder`` (between ``ensure_book_uuid`` and
# ``_register``) can land a registration after another thread's ``scan()`` but
# before its post-scan lookup. That registration was read from a file that has
# since changed, and the post-scan lookup used to return it unchecked.
#
# c14, c16 and c17 hook the private ``scan`` / ``_register`` / ``_uuid_on_disk``
# on the instance to place that late registration deterministically. This is the
# accepted exception to "don't mock your own modules": the race window cannot be
# hit reliably any other way. c15 is the real-thread pair.


def _one_shot_scan(r: BookUuidResolver, after: Callable[[], None]) -> None:
    """Replace ``r.scan`` once: run the real scan, then ``after``, then restore."""

    def hooked() -> None:
        del r.scan  # type: ignore[method-assign]
        BookUuidResolver.scan(r)
        after()

    r.scan = hooked  # type: ignore[method-assign]


def _late_register(r: BookUuidResolver, folder: str, u: str) -> Callable[[], None]:
    def go() -> None:
        with r._lock:
            r._register(folder, u)

    return go


@pytest.mark.parametrize("disk", ["rewritten"] + sorted(CORRUPTIONS))
@pytest.mark.parametrize("start", ["warm", "cold"])
def test_c14_late_registration_is_not_returned(books: Path, start: str, disk: str) -> None:
    """Private hook on ``scan`` (accepted exception, see block comment): after
    the real scan, a stale ``X -> u1`` lands as a paused thread would land it."""
    u1, u2 = _u(), _u()
    folder = books / X
    if start == "warm":
        r = _warm(books, u1)
    else:
        folder.mkdir()
        (folder / "book.pkl").write_bytes(b"old-book-bytes")
        _write_meta(folder, {"book_uuid": u1})
        r = BookUuidResolver(str(books))
    meta = _write_meta(folder, {"book_uuid": u2} if disk == "rewritten" else CORRUPTIONS[disk])
    st0 = _st(meta)
    listing0 = sorted(os.listdir(folder))

    _one_shot_scan(r, _late_register(r, X, u1))
    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    assert u1 not in r._uuid_to_folder
    assert "scan" not in vars(r)

    if disk == "rewritten":
        assert r.folder_for_book_uuid(u2) == X
        assert r.book_uuid_for_folder(X) == u2
    else:
        with pytest.raises(KeyError):
            r.folder_for_book_uuid(u1)
        with pytest.raises(ValueError):
            r.book_uuid_for_folder(X)

    assert _st(meta) == st0
    assert sorted(os.listdir(folder)) == listing0
    assert _scratch(folder) == []


def test_c15_real_threads_late_registration(books: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real threads, public calls only. The wrappers add blocking and nothing else."""
    import reader3_app.ai.books as books_mod

    u1 = _u()
    folder = books / X
    folder.mkdir()
    (folder / "book.pkl").write_bytes(b"old-book-bytes")
    meta = _write_meta(folder, {"book_uuid": u1})
    r = BookUuidResolver(str(books))

    a_read = threading.Event()
    release_a = threading.Event()
    real_ensure = books_mod.ensure_book_uuid

    def paused_ensure(books_dir: str, book_folder: str, **kwargs: Any) -> str:
        # **kwargs: the resolver passes ``deadline=`` through (018 WI-2 #23).
        got = real_ensure(books_dir, book_folder, **kwargs)
        if threading.current_thread().name == "A":
            a_read.set()
            release_a.wait(timeout=5)
        return got

    monkeypatch.setattr(books_mod, "ensure_book_uuid", paused_ensure)

    a = _Bounded(lambda: r.book_uuid_for_folder(X), name="A").start()
    assert a_read.wait(timeout=5), "thread A never reached ensure_book_uuid"

    _write_meta(folder, "{")
    st_c = _st(meta)

    def release_and_join_a() -> None:
        release_a.set()
        a.settle()

    _one_shot_scan(r, release_and_join_a)
    b = _Bounded(lambda: r.folder_for_book_uuid(u1), name="B").start().settle()

    assert isinstance(b.exc, KeyError), f"B got result={b.result!r} exc={b.exc!r}"
    assert a.exc is None and a.result == u1

    with pytest.raises(KeyError):
        run_bounded(lambda: r.folder_for_book_uuid(u1))
    with pytest.raises(ValueError):
        r.book_uuid_for_folder(X)
    assert _st(meta) == st_c
    assert _scratch(folder) == []


def test_c16_fresh_entry_survives_invalidation(books: Path) -> None:
    """Private hooks on ``scan`` and ``_uuid_on_disk`` (accepted exception, see
    block comment). Between the validation read and the delete, another writer
    re-registers ``u1`` to a folder that really holds it."""
    u1, u2 = _u(), _u()
    y = "y_book"  # not *_data: scan() can never rediscover it
    meta_x = _write_meta(books / X, {"book_uuid": u2})
    meta_y = _write_meta(books / y, {"book_uuid": u1})
    st_x, st_y = _st(meta_x), _st(meta_y)
    r = BookUuidResolver(str(books))

    _one_shot_scan(r, _late_register(r, X, u1))

    def spy(book_folder: str) -> Optional[str]:
        if book_folder == X:
            del r._uuid_on_disk  # type: ignore[method-assign]
            with r._lock:
                r._register(y, u1)
        return BookUuidResolver._uuid_on_disk(r, book_folder)

    r._uuid_on_disk = spy  # type: ignore[method-assign]

    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    assert "_uuid_on_disk" not in vars(r), "the post-scan candidate was never validated"
    assert r._uuid_to_folder[u1] == y

    assert r.folder_for_book_uuid(u1) == y
    assert _st(meta_x) == st_x
    assert _st(meta_y) == st_y
    assert _scratch(books / X) == []
    assert _scratch(books / y) == []


def test_c17_folder_gone_before_validation(books: Path) -> None:
    """Private hook on ``scan`` (accepted exception, see block comment): the
    folder is deleted, then the stale registration lands, before validation."""
    u1, u2 = _u(), _u()
    r = _warm(books, u1)
    _write_meta(books / X, {"book_uuid": u2})
    listing: List[List[str]] = []

    def gone_then_late() -> None:
        shutil.rmtree(books / X)
        listing.append(sorted(os.listdir(books)))
        with r._lock:
            r._register(X, u1)

    _one_shot_scan(r, gone_then_late)

    def unchanged() -> None:
        assert not (books / X).exists()
        assert sorted(os.listdir(books)) == listing[0]

    with pytest.raises(KeyError) as ei:
        r.folder_for_book_uuid(u1)
    assert not isinstance(ei.value, OSError)
    assert u1 not in r._uuid_to_folder
    unchanged()

    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u1)
    unchanged()
    with pytest.raises(KeyError):
        r.folder_for_book_uuid(u2)
    unchanged()

    with pytest.raises(FileNotFoundError):
        r.book_uuid_for_folder(X)
    unchanged()


class ResolverVsDiskLate(ResolverVsDisk):
    """``ResolverVsDisk`` plus late stale registrations before a reverse lookup."""

    @rule(name=st.sampled_from(NAMES), data=st.data())
    def reverse_after_late_registration(self, name: str, data: st.DataObject) -> None:
        # u is held by no folder on disk, so "no holder" is the oracle's answer.
        pool = [s for s in self.seen if s not in self._held()] + [_u()]
        u = data.draw(st.sampled_from(pool), label="late")
        _one_shot_scan(self.r, _late_register(self.r, name, u))
        try:
            got: Optional[str] = run_bounded(lambda: self.r.folder_for_book_uuid(u))
        except KeyError:
            got = None
        self._refresh_pending()
        assert got is None, f"returned {got!r} for {u}, which no folder holds on disk"


ResolverVsDiskLate.TestCase.settings = settings(max_examples=40, stateful_step_count=20, deadline=None)
test_c18_resolver_agrees_with_disk_under_late_registration = ResolverVsDiskLate.TestCase
