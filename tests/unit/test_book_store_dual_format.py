"""012 WI-4a.2: the dual-format loaders ``load_book_cached`` / ``load_book`` / ``load_book_metadata``.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4a.md`` section ``## WI-4a.2``, cases DF-01, DF-01p, DF-02 … DF-23
(DF-04 optional, included). DF-14 / DF-14b live in ``tests/contract/test_storage_format_routes.py``. DF-23b lives
in ``test_book_store_r5.py`` (WI-4a.3), because its fingerprint leg needs the R-5 stamp.
Rulings: the plan's "Coordinator rulings 2026-10-09 (WI-4a)" (D-a, OQ-3, OQ-4, OQ-6).

Laws pinned here:

* Read-your-publishes over manifest identity: a valid book is the content of ``gen/{g}/book.pkl`` for the manifest
  identity current at call time; an unchanged identity gives the ``is``-same object and no unpickle, a changed one
  exactly one new unpickle.
* Corrupt storage raises ``BookCorrupt`` on every call, warm or cold, with exactly one ERROR.
* A valid manifest whose gen pkl is unreadable (or not a ``Book``) raises ``BookCorrupt`` on every cold call, with
  one ERROR naming the book and the exception type only, and never reads or stats the flat pkl (D-a).
* ``MemoryError`` is never mapped. Missing is today's behaviour. One root-manifest read per load call.
* Metamorphic: the same content stored flat or as a generation loads to equal Books.

Every case runs on real files under ``tmp_path``. The only patches are delegating spies and fault injectors, by
literal string.
"""

from __future__ import annotations

import itertools
import logging
import os
import pickle
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pytest
from book_format_helpers import INJECTED_KINDS, MANIFEST
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from wi2b_world import FP_A, gen_inputs
from wi4a_world import (
    G,
    NONBOOK_PKL,
    REFUSED_PKL,
    Counters,
    ManifestIO,
    book_obj,
    flat_pkl,
    flip_first_byte,
    gen_book_pkl,
    outcome,
)

from reader3_app import book_format, book_lock, book_store, safe_pickle, search_service
from reader3_app.reader3 import BookMetadata
from reader3_app.web import server

BC = book_format.BookCorrupt
PKL = book_format.PKL
TEXTS = ["alpha", "beta gamma", ""]
BASE_NS = 1_700_000_000_000_000_000
PROPS = settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def pinned(bid: str) -> str:
    return f"book {bid!r}: manifest.json is corrupt; refusing to load"


# --------------------------------------------------------------------------- fixtures and local helpers


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path resolves under tmp_path, never a real books/ dir."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _empty_loader_cache() -> Iterator[None]:
    book_store.load_book_cached.cache_clear()
    yield
    book_store.load_book_cached.cache_clear()


@pytest.fixture
def books(tmp_path: Path) -> Path:
    out = tmp_path / "books"
    out.mkdir()
    return out


def gen(books: Path, folder: str, title: str, texts: List[str] = TEXTS, *, fp: str = FP_A, tag: str = "v1",
        authors: Optional[List[str]] = None) -> int:
    """A generation whose declared ``book.pkl`` is a real pickled ``Book`` titled ``title``; return g."""
    bk = book_obj(title, texts, fp)
    if authors is not None:
        bk.metadata.authors = list(authors)
    return gen_book_pkl(books, folder, texts=texts, fp=fp, pkl=pickle.dumps(bk), tag=tag)


def flat(books: Path, folder: str, title: str, texts: List[str] = TEXTS) -> Path:
    return flat_pkl(books, folder, book_obj(title, texts))


def gen_pkl(books: Path, folder: str = G, g: int = 1) -> Path:
    return books / folder / book_format.GEN_DIR / str(g) / PKL


def publish_undeclared(books: Path, folder: str = G) -> int:
    """A generation published from ``wi2b_world.gen_inputs`` as-is: ``pkl=False``, so no gen ``book.pkl``."""
    book_dir = books / folder
    book_dir.mkdir(parents=True, exist_ok=True)
    with book_lock.acquire(str(books), folder, mode=book_lock.EXCLUSIVE, holder="import"):
        return book_format.publish(book_dir, gen_inputs(TEXTS, FP_A, "v1"))


def errors(caplog: pytest.LogCaptureFixture) -> list:
    """Every ERROR-or-worse record, from any logger (a second ERROR anywhere is the double log OQ-3 forbids)."""
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def info() -> Any:
    return book_store.load_book_cached.cache_info()


def spine_rows(book: Any) -> List[Tuple[Any, ...]]:
    return [(c.text, c.content, c.title, c.href, c.order) for c in book.spine]


class FileRecorder:
    """Delegating wrapper on ``book_store.load_book_file``: records each path and any exception it raised."""

    def __init__(self) -> None:
        self.paths: List[str] = []
        self.raised: List[BaseException] = []

    def install(self, mp: pytest.MonkeyPatch) -> "FileRecorder":
        real = safe_pickle.load_book_file

        def recording(path: str) -> Any:
            self.paths.append(str(path))
            try:
                return real(path)
            except BaseException as exc:
                self.raised.append(exc)
                raise

        mp.setattr("reader3_app.book_store.load_book_file", recording)
        return self


def hygiene(r: logging.LogRecord, *secrets: str) -> None:
    """The emitted record (message plus any traceback a handler would append) carries none of ``secrets``."""
    formatted = logging.Formatter("%(message)s").format(r)
    for s in secrets:
        assert s, "an empty secret makes the `not in` check vacuous"
        assert s not in formatted, (s, formatted)
    assert r.exc_info is None, "logger.exception / exc_info=True would emit the inner message and paths"


# --------------------------------------------------------------------------- equivalence (DF-01, DF-01p)


def test_df_01_flat_and_gen_load_to_item_by_item_equal_books(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bk = book_obj("Same Title", TEXTS)
    flat_pkl(books, "flat_data", bk)
    gen_book_pkl(books, "gen_data", texts=TEXTS, fp=FP_A, pkl=pickle.dumps(bk))
    c = Counters().install(monkeypatch)
    d = str(books)

    x = outcome(book_store.load_book, "flat_data", d)
    y = outcome(book_store.load_book, "gen_data", d)

    assert not isinstance(y, BaseException), f"gen-only book raised {type(y).__name__}: {y}"
    assert len(x.spine) == len(y.spine) == 3
    assert spine_rows(x) == spine_rows(y)
    assert x.metadata.title == y.metadata.title == "Same Title"
    assert c.paths == [str(books / "flat_data" / PKL), str(gen_pkl(books, "gen_data"))]


_DF01P = itertools.count()


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    texts=st.lists(st.text(max_size=40), min_size=1, max_size=5),
    title=st.text(max_size=30),
    authors=st.lists(st.text(min_size=1, max_size=10), max_size=2),
)
def test_df_01p_property_storage_form_does_not_change_content(
    tmp_path: Path, texts: List[str], title: str, authors: List[str]
) -> None:
    books = tmp_path / f"ex{next(_DF01P)}" / "books"
    books.mkdir(parents=True)
    bk = book_obj(title, texts)
    bk.metadata.authors = list(authors)
    flat_pkl(books, "flat_data", bk)
    gen_book_pkl(books, "gen_data", texts=texts, fp=FP_A, pkl=pickle.dumps(bk))
    d = str(books)
    book_store.load_book_cached.cache_clear()
    try:
        x = book_store.load_book("flat_data", d)
        y = outcome(book_store.load_book, "gen_data", d)
        assert not isinstance(y, BaseException), f"gen-only book raised {type(y).__name__}"
        assert spine_rows(x) == spine_rows(y)
        assert (x.metadata.title, x.metadata.authors) == (y.metadata.title, y.metadata.authors)  # type: ignore
        vx = book_store.load_book_metadata("flat_data", d)
        vy = book_store.load_book_metadata("gen_data", d)
        assert (vx.title, tuple(vx.authors)) == (vy.title, tuple(vy.authors))
    finally:
        book_store.load_book_cached.cache_clear()


# --------------------------------------------------------------------------- cache key (DF-02 … DF-05)


def test_df_02_warm_identity_on_gen(books: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen(books, G, "GEN")
    c = Counters().install(monkeypatch)
    d = str(books)
    i0 = info()

    a = outcome(book_store.load_book_cached, G, d)
    b = outcome(book_store.load_book_cached, G, d)

    assert not isinstance(a, BaseException), f"gen-only book raised {type(a).__name__}"
    assert b is a
    i1 = info()
    assert (i1.misses - i0.misses, i1.hits - i0.hits) == (1, 1)
    assert i1.currsize == 1
    assert c.raw == 1


def test_df_03_republish_invalidates(books: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen(books, G, "OLD")
    c = Counters().install(monkeypatch)
    d = str(books)
    i0 = info()

    a = outcome(book_store.load_book_cached, G, d)
    gen(books, G, "NEW", tag="v2")
    b = outcome(book_store.load_book_cached, G, d)

    assert not isinstance(a, BaseException) and not isinstance(b, BaseException), (a, b)
    assert b.metadata.title == "NEW"
    assert b is not a
    assert a.metadata.title == "OLD"
    assert info().misses - i0.misses == 2
    assert c.raw == 2


def test_df_04_same_mtime_republish_still_invalidates(books: Path) -> None:
    gen(books, G, "OLD")
    d = str(books)
    a = outcome(book_store.load_book_cached, G, d)
    m0 = os.stat(books / G / MANIFEST)

    gen(books, G, "NEW", tag="v2")
    os.utime(books / G / MANIFEST, ns=(m0.st_mtime_ns, m0.st_mtime_ns))
    m1 = os.stat(books / G / MANIFEST)
    assert m1.st_mtime_ns == m0.st_mtime_ns
    b = outcome(book_store.load_book_cached, G, d)

    assert not isinstance(b, BaseException), b
    assert b.metadata.title == "NEW"
    assert b is not a


def test_df_05_delete_and_reimport_at_the_same_g_does_not_serve_the_old_entry(books: Path) -> None:
    """Titles are ``FIRST1`` / ``SECOND`` (equal length) so the declared pkl size, and so the manifest size, match."""
    g1 = gen(books, G, "FIRST1")
    d = str(books)
    a = outcome(book_store.load_book_cached, G, d)
    m_a = book_format.validate_stat(books / G)
    s_a = os.stat(books / G / MANIFEST)

    shutil.rmtree(books / G)
    g2 = gen(books, G, "SECOND")
    m_b = book_format.validate_stat(books / G)
    s_b = os.stat(books / G / MANIFEST)

    assert (g1, m_a.book_fingerprint) == (g2, m_b.book_fingerprint) == (1, FP_A)
    ident_a = (s_a.st_ino, s_a.st_mtime_ns, s_a.st_size)
    ident_b = (s_b.st_ino, s_b.st_mtime_ns, s_b.st_size)
    assert ident_a != ident_b, "inode reuse plus same mtime on this filesystem: the manifest identities collide"
    b = outcome(book_store.load_book_cached, G, d)
    assert not isinstance(b, BaseException), b
    assert b.metadata.title == "SECOND"
    assert b is not a


# --------------------------------------------------------------------------- unreadable gen pkl (DF-06 … DF-09)


DF06_ROWS = ["flipped", "refused", "undeclared-absent"]


def _build_df06(books: Path, row: str) -> None:
    if row == "flipped":
        gen(books, G, "GEN")
        flip_first_byte(gen_pkl(books))
    elif row == "refused":
        gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=REFUSED_PKL)
    elif row == "undeclared-absent":
        publish_undeclared(books)
    else:  # pragma: no cover - a typo in the row list must not pass
        raise AssertionError(row)
    flat(books, G, "FLAT")
    assert book_store.storage_format(G, str(books)) == "valid"


@pytest.mark.parametrize("row", DF06_ROWS)
def test_df_06_cold_unreadable_gen_pkl_is_book_corrupt_chained_one_error_nothing_cached(
    tmp_path: Path, books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, row: str
) -> None:
    _build_df06(books, row)
    rec = FileRecorder().install(monkeypatch)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    d = str(books)

    exc = outcome(book_store.load_book_cached, G, d)

    assert type(exc) is BC, f"expected BookCorrupt, got {exc!r}"
    assert rec.raised, "the gen pkl read raised nothing"
    inner = rec.raised[-1]
    assert exc.__cause__ is inner
    errs = errors(caplog)
    assert len(errs) == 1, [r.getMessage() for r in errs]
    r = errs[0]
    assert r.name == "reader3_app.book_store"
    assert repr(G) in r.getMessage()
    assert type(inner).__name__ in r.getMessage()
    assert str(inner)
    hygiene(r, str(books), str(tmp_path), str(inner))
    assert G in str(exc) and str(books) not in str(exc)
    assert info().currsize == 0
    assert str(books / G / PKL) not in rec.paths

    caplog.clear()
    again = outcome(book_store.load_book_cached, G, d)
    assert type(again) is BC
    assert len(errors(caplog)) == 1
    assert len(rec.raised) == 2


def test_df_07_warm_hit_after_a_stat_invisible_flip_serves_the_cached_book(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accepted behaviour, pinned once (plan WI-4a.2, ruling D-a): generations are immutable; a stat-invisible
    change is not observed. A same-size byte flip of the declared gen pkl keeps the manifest identity, so the warm
    entry is served. DF-06's ``flipped`` row shows the same bytes on a cold cache raise ``BookCorrupt``."""
    gen(books, G, "GEN")
    c = Counters().install(monkeypatch)
    d = str(books)
    a = outcome(book_store.load_book_cached, G, d)
    assert not isinstance(a, BaseException), a
    raw0 = c.raw

    flip_first_byte(gen_pkl(books))
    assert book_store.storage_format(G, d) == "valid"
    b = book_store.load_book_cached(G, d)

    assert b is a
    assert c.raw == raw0


def _df08_damage(books: Path, damage: str) -> None:
    if damage == "rmtree-gen":
        shutil.rmtree(books / G / book_format.GEN_DIR / "1")
    elif damage == "unlink-gen-pkl":
        os.unlink(gen_pkl(books))
    elif damage == "resize-gen-pkl":
        with open(gen_pkl(books), "ab") as fh:
            fh.write(b"\x00")
    else:  # pragma: no cover
        raise AssertionError(damage)


@pytest.mark.parametrize("damage", ["rmtree-gen", "unlink-gen-pkl", "resize-gen-pkl"])
def test_df_08_warm_plus_stat_visible_damage_raises_on_the_next_call_entry_not_evicted(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, damage: str
) -> None:
    gen(books, G, "GEN")
    c = Counters().install(monkeypatch)
    d = str(books)
    a = outcome(book_store.load_book_cached, G, d)
    assert not isinstance(a, BaseException), a
    assert info().currsize == 1
    raw0 = c.raw
    m0 = os.stat(books / G / MANIFEST)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    _df08_damage(books, damage)
    m1 = os.stat(books / G / MANIFEST)
    assert (m1.st_ino, m1.st_mtime_ns, m1.st_size) == (m0.st_ino, m0.st_mtime_ns, m0.st_size)
    exc = outcome(book_store.load_book_cached, G, d)

    assert type(exc) is BC, exc
    assert [r.getMessage() for r in errors(caplog)] == [pinned(G)]
    assert info().currsize == 1
    assert c.raw == raw0


DF09_ROWS = ["gen-ok", "gen-garbage", "gen-absent", "gen-refused"]


@pytest.mark.parametrize("row", DF09_ROWS)
def test_df_09_migrated_book_never_falls_back_to_the_flat_pkl(
    books: Path, monkeypatch: pytest.MonkeyPatch, row: str
) -> None:
    if row == "gen-ok":
        gen(books, G, "GEN")
    elif row == "gen-garbage":
        gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=b"\x00" * 64)
    elif row == "gen-absent":
        publish_undeclared(books)
    else:
        gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=REFUSED_PKL)
    flat(books, G, "FLAT")
    c = Counters().install(monkeypatch)
    stats: List[str] = []
    real_stat = os.stat

    def stat_spy(path: Any, *a: Any, **kw: Any) -> Any:
        stats.append(os.fspath(path) if isinstance(path, (str, os.PathLike)) else repr(path))
        return real_stat(path, *a, **kw)

    with monkeypatch.context() as mp:
        mp.setattr("reader3_app.book_store.os.stat", stat_spy)
        got = outcome(book_store.load_book_cached, G, str(books))

    if row == "gen-ok":
        assert not isinstance(got, BaseException), got
        assert got.metadata.title == "GEN"
    else:
        assert type(got) is BC, got
    flat_path = str(books / G / PKL)
    assert flat_path not in c.paths, c.paths
    assert flat_path not in stats, stats


# --------------------------------------------------------------------------- properties (DF-10, DF-11)


_DF10 = itertools.count()
OPS = st.lists(st.tuples(st.sampled_from(["read", "republish", "flat_rewrite"]), st.integers(0, 4)),
               min_size=1, max_size=10)


@PROPS
@given(forms=st.lists(st.booleans(), min_size=5, max_size=5), ops=OPS)
def test_df_10_property_mixed_flat_gen_schedule_freshness_and_identity(
    tmp_path: Path, forms: List[bool], ops: List[Tuple[str, int]]
) -> None:
    books = tmp_path / f"ex{next(_DF10)}" / "books"
    books.mkdir(parents=True)
    d = str(books)
    tick = itertools.count(1)
    model: Dict[int, Tuple[int, str]] = {}  # book -> (identity version, expected title)

    def write_flat(i: int, title: str) -> None:
        p = flat(books, f"b{i}_data", title)
        ns = BASE_NS + next(tick)
        os.utime(p, ns=(ns, ns))

    for i, is_gen in enumerate(forms):
        if is_gen:
            gen(books, f"b{i}_data", f"g{i}v0")
            model[i] = (0, f"g{i}v0")
        else:
            write_flat(i, f"f{i}v0")
            model[i] = (0, f"f{i}v0")

    book_store.load_book_cached.cache_clear()
    seen: Dict[Tuple[int, int], Any] = {}
    reads = 0
    try:
        with pytest.MonkeyPatch.context() as mp:
            c = Counters().install(mp)
            i0 = info()
            for k, (op, i) in enumerate(ops):
                ver, title = model[i]
                if op == "read":
                    reads += 1
                    got = outcome(book_store.load_book_cached, f"b{i}_data", d)
                    assert not isinstance(got, BaseException), (i, got)
                    assert got.metadata.title == title, (i, got.metadata.title, title)
                    if (i, ver) in seen:
                        assert got is seen[(i, ver)]
                    seen[(i, ver)] = got
                elif op == "republish":
                    if forms[i]:
                        new = f"g{i}v{ver + 1}"
                        gen(books, f"b{i}_data", new, tag=f"t{k}")
                        model[i] = (ver + 1, new)
                else:
                    if forms[i]:
                        write_flat(i, f"ignored{k}")  # a flat pkl next to a valid manifest is never read
                    else:
                        new = f"f{i}v{ver + 1}"
                        write_flat(i, new)
                        model[i] = (ver + 1, new)
            i1 = info()
            assert c.raw == len(seen)
            assert (i1.hits - i0.hits) + (i1.misses - i0.misses) == reads
    finally:
        book_store.load_book_cached.cache_clear()


_DF11 = itertools.count()


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(perm=st.permutations(list(range(12))), extra=st.lists(st.integers(0, 11), max_size=18))
def test_df_11_cache_bound_holds_across_mixed_key_shapes(tmp_path: Path, perm: List[int], extra: List[int]) -> None:
    books = tmp_path / f"ex{next(_DF11)}" / "books"
    books.mkdir(parents=True)
    d = str(books)
    for i in range(12):
        if i % 2:
            gen(books, f"b{i}_data", f"T{i}")
        else:
            flat(books, f"b{i}_data", f"T{i}")
    book_store.load_book_cached.cache_clear()
    try:
        for i in list(perm) + list(extra):
            got = outcome(book_store.load_book_cached, f"b{i}_data", d)
            assert not isinstance(got, BaseException), (i, got)
            assert got.metadata.title == f"T{i}"
            assert info().currsize <= 10
        assert book_store.load_book_cached.cache_parameters()["maxsize"] == 10
        assert server.load_book_cached.cache_parameters()["maxsize"] == 10  # type: ignore[attr-defined]
    finally:
        book_store.load_book_cached.cache_clear()


# --------------------------------------------------------------------------- state never cached (DF-12)


def test_df_12_storage_state_is_never_cached(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gen(books, G, "GEN")
    d = str(books)
    a = outcome(book_store.load_book_cached, G, d)
    assert not isinstance(a, BaseException), a
    manifest = books / G / MANIFEST
    m = manifest.read_bytes()
    st0 = os.stat(manifest)
    c = Counters().install(monkeypatch)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    with open(manifest, "r+b") as fh:
        fh.write(b"x" * len(m))
    bad = outcome(book_store.load_book_cached, G, d)
    assert type(bad) is BC, bad
    assert [r.getMessage() for r in errors(caplog)] == [pinned(G)]

    with open(manifest, "r+b") as fh:
        fh.write(m)
    os.utime(manifest, ns=(st0.st_atime_ns, st0.st_mtime_ns))
    back = book_store.load_book_cached(G, d)

    assert back is a
    assert c.raw == 0


# --------------------------------------------------------------------------- server wrapper (DF-13)


@pytest.mark.parametrize("row", ["unreadable-gen-pkl", "corrupt-manifest", "control-flat-garbage"])
def test_df_13_server_wrapper_passes_book_corrupt_through(
    books: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, row: str
) -> None:
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(books))
    if row == "unreadable-gen-pkl":
        gen(books, G, "GEN")
        flip_first_byte(gen_pkl(books))
    elif row == "corrupt-manifest":
        gen(books, G, "GEN")
        (books / G / MANIFEST).write_bytes(b"{ not json")
    else:
        (books / G).mkdir()
        (books / G / PKL).write_bytes(b"\x80\x05not-a-pickle-at-all")
    capsys.readouterr()

    got = outcome(server.load_book_cached, G)
    out = capsys.readouterr().out

    if row == "control-flat-garbage":
        assert got is None
        assert "Error loading book" in out
    else:
        assert type(got) is BC, got
        assert "Error loading book" not in out


# --------------------------------------------------------------------------- metadata and entry points


def test_df_15_load_book_metadata_on_gen(books: Path) -> None:
    gen(books, G, "GT", authors=["A1", "A2"])
    gen(books, "bad_data", "GEN")
    flip_first_byte(gen_pkl(books, "bad_data"))
    d = str(books)

    view = outcome(book_store.load_book_metadata, G, d)
    bad = outcome(book_store.load_book_metadata, "bad_data", d)

    assert not isinstance(view, BaseException), view
    assert (view.book_id, view.title, tuple(view.authors)) == (G, "GT", ("A1", "A2"))
    assert type(bad) is BC, bad


def test_df_16_all_entry_points_share_one_object_for_a_gen_book(
    books: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gen(books, G, "GEN")
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(books))
    c = Counters().install(monkeypatch)
    d = str(books)

    got = [
        outcome(book_store.load_book, G, d),
        outcome(book_store.load_book_cached, G, d),
        outcome(search_service.load_book_cached, G, d),
        outcome(server.load_book_cached, G),
    ]

    assert not isinstance(got[0], BaseException) and got[0] is not None, got
    assert all(x is got[0] for x in got), got
    assert c.raw == 1


def _entry_points() -> List[Tuple[str, Callable[[str, str], Any]]]:
    return [
        ("book_store.load_book", lambda b, d: book_store.load_book(b, d)),
        ("book_store.load_book_cached", lambda b, d: book_store.load_book_cached(b, d)),
        ("book_store.load_book_metadata", lambda b, d: book_store.load_book_metadata(b, d)),
        ("search_service.load_book_cached", lambda b, d: search_service.load_book_cached(b, d)),
    ]


@pytest.mark.parametrize("entry", range(4), ids=[n for n, _ in _entry_points()])
@pytest.mark.parametrize("row", ["corrupt-manifest", "unreadable-gen-pkl"])
def test_df_17_one_load_call_logs_exactly_one_error(
    books: Path, caplog: pytest.LogCaptureFixture, row: str, entry: int
) -> None:
    gen(books, G, "GEN")
    if row == "corrupt-manifest":
        (books / G / MANIFEST).write_bytes(b"{ not json")
    else:
        flip_first_byte(gen_pkl(books))
    name, call = _entry_points()[entry]
    book_store.load_book_cached.cache_clear()
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    exc = outcome(call, G, str(books))

    assert type(exc) is BC, (name, exc)
    msgs = [r.getMessage() for r in errors(caplog)]
    assert len(msgs) == 1, (name, msgs)
    if row == "corrupt-manifest":
        assert msgs == [pinned(G)]
    else:
        assert "UnpicklingError" in msgs[0] and repr(G) in msgs[0], msgs
        assert msgs[0] != pinned(G)


# --------------------------------------------------------------------------- OQ-4 breadth (DF-18 … DF-20)


def test_df_18_memory_error_propagates_unmapped(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gen(books, G, "GEN")
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    def nomem(f: Any) -> Any:
        raise INJECTED_KINDS["nomem"]()

    with monkeypatch.context() as mp:
        mp.setattr("reader3_app.safe_pickle.safe_load", nomem)
        exc = outcome(book_store.load_book_cached, G, str(books))

    assert type(exc).__name__ == "MemoryError", exc
    assert not isinstance(exc, BC)
    assert errors(caplog) == []
    assert info().currsize == 0


@pytest.mark.parametrize("make", [lambda: ValueError("SECRET-INNER-TEXT /abs/path"), lambda: KeyError("SECRET-KEY")],
                         ids=["ValueError", "KeyError"])
def test_df_19_cause_chain_and_d3_message_shape_on_an_arbitrary_inner_exception(
    tmp_path: Path, books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    make: Callable[[], BaseException],
) -> None:
    gen(books, G, "GEN")
    inner = make()
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    def boom(f: Any) -> Any:
        raise inner

    monkeypatch.setattr("reader3_app.safe_pickle.safe_load", boom)
    exc = outcome(book_store.load_book_cached, G, str(books))

    assert type(exc) is BC, exc
    assert exc.__cause__ is inner
    errs = errors(caplog)
    assert len(errs) == 1, [r.getMessage() for r in errs]
    r = errs[0]
    assert type(inner).__name__ in r.getMessage() and repr(G) in r.getMessage()
    hygiene(r, "SECRET", "/abs/path", str(books), str(tmp_path))
    assert "SECRET" not in str(exc)


@pytest.mark.parametrize("payload", [NONBOOK_PKL, pickle.dumps(BookMetadata(title="x", language="en"))],
                         ids=["dict", "BookMetadata"])
def test_df_20_unpickled_non_book_is_book_corrupt(
    books: Path, caplog: pytest.LogCaptureFixture, payload: bytes
) -> None:
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=payload)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    got = outcome(book_store.load_book_cached, G, str(books))

    assert type(got) is BC, f"expected BookCorrupt, got {got!r}"
    errs = errors(caplog)
    assert len(errs) == 1 and repr(G) in errs[0].getMessage(), [r.getMessage() for r in errs]
    assert info().currsize == 0


# --------------------------------------------------------------------------- concurrency and transitions


def test_df_21_concurrent_cold_loads_of_a_gen_book(books: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen(books, G, "GEN")
    c = Counters().install(monkeypatch)
    d = str(books)
    barrier = threading.Barrier(2)
    results: List[Any] = [None, None]

    def worker(k: int) -> None:
        barrier.wait(timeout=10)
        results[k] = outcome(book_store.load_book_cached, G, d)

    threads = [threading.Thread(target=worker, args=(k,), daemon=True) for k in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
        assert not t.is_alive()

    for r in results:
        assert not isinstance(r, BaseException) and r is not None, results
        assert r.metadata.title == "GEN"
    assert 1 <= c.raw <= 2
    assert info().currsize == 1
    third = book_store.load_book_cached(G, d)
    assert any(third is r for r in results)


def test_df_22_state_transitions_missing_to_valid_and_back(books: Path) -> None:
    flat(books, G, "FLAT")
    d = str(books)
    i0 = info()

    first = book_store.load_book_cached(G, d)
    assert first.metadata.title == "FLAT"  # type: ignore[attr-defined]
    gen(books, G, "GEN")
    second = outcome(book_store.load_book_cached, G, d)
    assert not isinstance(second, BaseException), second
    assert second.metadata.title == "GEN"

    (books / G / MANIFEST).unlink()
    third = book_store.load_book_cached(G, d)
    assert third is first
    assert info().misses - i0.misses == 2


# --------------------------------------------------------------------------- one manifest read per call (DF-23)


def _df23_points() -> List[Tuple[str, Callable[[str, str], Any]]]:
    return _entry_points() + [("server.load_book_cached", lambda b, d: server.load_book_cached(b))]


@pytest.mark.parametrize("entry", range(5), ids=[n for n, _ in _df23_points()])
@pytest.mark.parametrize("temp", ["cold", "warm"])
@pytest.mark.parametrize("state", ["valid", "missing"])
def test_df_23_one_root_manifest_read_per_load_call(
    books: Path, monkeypatch: pytest.MonkeyPatch, state: str, temp: str, entry: int
) -> None:
    if state == "valid":
        book_id = G
        gen_book_pkl(books, G, texts=["v"], fp=FP_A, pkl=pickle.dumps(book_obj("GEN", ["v"], FP_A)))
        want = "GEN"
    else:
        book_id = "flat_data"
        flat_pkl(books, book_id, book_obj("FLAT", ["f"]))
        want = "FLAT"
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(books))
    name, call = _df23_points()[entry]
    d = str(books)
    if temp == "warm":
        outcome(call, book_id, d)
    else:
        book_store.load_book_cached.cache_clear()

    with monkeypatch.context() as mp:
        m = ManifestIO().install(mp)
        got = outcome(call, book_id, d)

    counts = (m.calls, m.returned, m.lstats)
    title = getattr(got, "title", None) if name.endswith("metadata") else getattr(
        getattr(got, "metadata", None), "title", None)
    assert title == want, (name, got, counts)
    if state == "valid":
        assert (m.calls, m.returned) == (1, 1), counts
    else:
        assert m.calls + m.lstats == 1 and m.returned == 0, counts
