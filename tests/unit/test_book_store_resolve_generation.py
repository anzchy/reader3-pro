"""012 WI-4a.1: ``book_store.resolve_generation``, the shared silent core, and ``_read_nofollow``'s fstat.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4a.md`` section ``## WI-4a.1``, cases RG-01 … RG-10 and RG-09b.
Rulings: the plan's "Coordinator rulings 2026-10-09 (WI-4a)" (OQ-1(a), OQ-2(b), OQ-3, OQ-5).

Laws pinned here:

* ``resolve_generation`` raises ``BookCorrupt`` iff ``book_format.classify(dir, full=False)`` is ``"corrupt"``
  (one ERROR per call, pinned wording) and otherwise returns that state; ``storage_format`` equals the
  classification and is silent. Neither carries state between calls.
* On valid, ``manifest`` / ``manifest_key`` / ``gen_dir`` come from one read of one manifest file, and the key is
  that file's ``(st_ino, st_mtime_ns, st_size)`` (the fstat of the fd the bytes came from).
* Single source (OQ-1(a)): ``book_store`` owns no classification ladder; ``book_format`` owns one, and
  ``classify`` delegates to it (RG-09 / RG-09b, structural on purpose: a faithful copy is behaviourally invisible).

Every case runs on real files under ``tmp_path``. The only patches are delegating spies, by literal string.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
import logging
import os
import pickle
import shutil
import typing
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from book_format_helpers import MANIFEST, REPAIRABLE, SCENARIOS, build_repairable, setup_scenario, snapshot
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from test_storage_format import CORRUPT_SHAPES, MISSING_ROWS, build_corrupt, build_missing
from wi2b_world import FP_A, pkl_book
from wi4a_world import BAD_IDS, G, book_obj, gen_book_pkl, outcome

from reader3_app import book_format, book_store

TEXTS = ["a", "b"]
BC = book_format.BookCorrupt


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


def resolver() -> Callable[[str, str], Any]:
    """``book_store.resolve_generation``, with both WI-4a.1 names asserted present.

    ``hasattr`` plus an ``assert`` rather than a bare attribute access, so the pre-implementation red is a
    counted assertion carrying a sentence, not an ``AttributeError`` traceback.
    """
    missing = [n for n in ("resolve_generation", "ResolvedGeneration") if not hasattr(book_store, n)]
    assert not missing, (
        f"reader3_app.book_store is missing {missing}. WI-4a.1 adds `resolve_generation(book_id, books_dir)` "
        "returning a frozen `ResolvedGeneration(state, book_dir, gen_dir, manifest, manifest_key)`."
    )
    return book_store.resolve_generation  # type: ignore[no-any-return]


def errors(caplog: pytest.LogCaptureFixture) -> list:
    """ERROR-or-worse records from every logger (a second ERROR from any module is the forbidden double log)."""
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def blob(title: str = G, texts: list[str] = TEXTS, fp: str = FP_A) -> bytes:
    return pickle.dumps(book_obj(title, texts, fp))


def ident(path: Path) -> tuple[int, int, int]:
    s = os.lstat(path)
    return (s.st_ino, s.st_mtime_ns, s.st_size)


# --------------------------------------------------------------------------- RG-01 valid example


def test_rg_01_valid_fields_equal_the_published_manifest_and_the_stat_triple(books: Path) -> None:
    resolve = resolver()
    assert gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob()) == 1
    assert gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v2") == 2
    mpath = books / G / MANIFEST
    s = os.lstat(mpath)
    before = snapshot(books / G)

    r = resolve(G, str(books))

    assert snapshot(books / G) == before, "resolve_generation must not write"
    assert type(r).__name__ == "ResolvedGeneration"
    assert dataclasses.is_dataclass(r)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(r, "state", "x")
    assert r.state == "valid"
    assert r.book_dir == os.path.join(str(books), G)
    assert r.gen_dir == os.path.join(str(books), G, "gen", "2")
    assert r.manifest.generation == 2
    assert r.manifest.book_fingerprint == FP_A
    assert r.manifest == book_format.manifest_from_bytes(mpath.read_bytes())
    assert r.manifest_key == (s.st_ino, s.st_mtime_ns, s.st_size)
    hints = typing.get_type_hints(book_store.resolve_generation)
    assert {"return", "book_id", "books_dir"} <= set(hints), hints


# --------------------------------------------------------------------------- RG-02 missing


@pytest.mark.parametrize("row", MISSING_ROWS + ["books-dir-absent"])
def test_rg_02_missing_gives_all_optionals_none(
    tmp_path: Path, books: Path, row: str, caplog: pytest.LogCaptureFixture
) -> None:
    resolve = resolver()
    books_dir = books
    if row == "books-dir-absent":
        books_dir, bid = tmp_path / "no_books", G
    else:
        bid = build_missing(row, books)
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    r = resolve(bid, str(books_dir))

    assert r.state == "missing"
    assert r.gen_dir is None
    assert r.manifest is None
    assert r.manifest_key is None
    assert r.book_dir == os.path.join(str(books_dir), bid)
    assert caplog.records == []
    if row in ("absent-dir", "books-dir-absent"):
        assert not os.path.lexists(books_dir / bid), "resolve_generation must not create the book dir"


# --------------------------------------------------------------------------- RG-03 corrupt


RG03_SHAPES = CORRUPT_SHAPES + ["manifest-is-symlink"]


def build_rg03(shape: str, tmp_path: Path, books: Path) -> str:
    if shape == "manifest-is-symlink":
        gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob())
        target = tmp_path / "outside-manifest.json"
        shutil.copyfile(books / G / MANIFEST, target)
        os.unlink(books / G / MANIFEST)
        os.symlink(target, books / G / MANIFEST)
        return G
    return build_corrupt(shape, tmp_path, books, flat_pkl=False)


def _assert_corrupt_twice(resolve: Callable[[str, str], Any], bid: str, books: Path, tmp_path: Path,
                          caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    exc = outcome(resolve, bid, str(books))
    assert isinstance(exc, BC), f"expected BookCorrupt, got {exc!r}"
    assert bid in str(exc)
    assert str(books) not in str(exc)
    assert str(tmp_path) not in str(exc)
    assert [(r.name, r.getMessage()) for r in errors(caplog)] == [("reader3_app.book_store", pinned(bid))]
    again = outcome(resolve, bid, str(books))
    assert isinstance(again, BC), f"second call: expected BookCorrupt, got {again!r}"
    assert len(errors(caplog)) == 2, "one ERROR per call: not memoized, not deduplicated"


@pytest.mark.parametrize("shape", RG03_SHAPES)
def test_rg_03_corrupt_raises_with_one_pinned_error_and_clean_message(
    tmp_path: Path, books: Path, shape: str, caplog: pytest.LogCaptureFixture
) -> None:
    resolve = resolver()
    bid = build_rg03(shape, tmp_path, books)
    assert os.path.lexists(books / bid / MANIFEST), f"builder for {shape!r} did not build books/{bid}/manifest.json"
    before = snapshot(books / bid)

    _assert_corrupt_twice(resolve, bid, books, tmp_path, caplog)

    assert snapshot(books / bid) == before, "the resolver does not repair"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignores directory modes")
def test_rg_03b_unreadable_lstat_manifest_is_corrupt(
    tmp_path: Path, books: Path, caplog: pytest.LogCaptureFixture
) -> None:
    resolve = resolver()
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob())
    assert (books / G).is_dir()
    os.chmod(books / G, 0)
    try:
        _assert_corrupt_twice(resolve, G, books, tmp_path, caplog)
    finally:
        os.chmod(books / G, 0o755)


# --------------------------------------------------------------------------- RG-04 traversal ids


@pytest.mark.parametrize("bad", BAD_IDS)
def test_rg_04_traversal_ids_raise_before_any_filesystem_access(
    tmp_path: Path, books: Path, bad: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve = resolver()
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob())
    seen: list[Any] = []
    real = {"lstat": os.lstat, "stat": os.stat, "open": os.open}

    def spy(name: str) -> Callable[..., Any]:
        def wrapped(path: Any, *a: Any, **kw: Any) -> Any:
            seen.append(os.fspath(path) if isinstance(path, (str, os.PathLike)) else path)
            return real[name](path, *a, **kw)
        return wrapped

    with monkeypatch.context() as mp:
        mp.setattr("os.lstat", spy("lstat"))
        mp.setattr("os.stat", spy("stat"))
        mp.setattr("os.open", spy("open"))
        got = outcome(resolve, bad, str(books))
        got_fmt = outcome(book_store.storage_format, bad, str(books))

    assert isinstance(got, ValueError), f"resolve_generation({bad!r}): expected ValueError, got {got!r}"
    assert isinstance(got_fmt, ValueError), f"storage_format({bad!r}): expected ValueError, got {got_fmt!r}"
    touched = [p for p in seen if isinstance(p, str) and p.startswith(str(tmp_path))]
    assert touched == [], f"filesystem touched before the id was refused: {touched}"


# --------------------------------------------------------------------------- RG-05 property


_EX = itertools.count()
DAMAGE: list[Any] = [None] + sorted(REPAIRABLE) + ["manifest-is-dir", "manifest-unlinked", "dir-absent"]


def _damage(book: Path, damage: str | None) -> None:
    if damage is None:
        return
    manifest = book / MANIFEST
    if damage == "manifest-is-dir":
        book.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(manifest):
            os.unlink(manifest)
        manifest.mkdir()
    elif damage == "manifest-unlinked":
        if os.path.lexists(manifest):
            os.unlink(manifest)
    elif damage == "dir-absent":
        if os.path.lexists(book):
            shutil.rmtree(book)
    else:  # pragma: no cover - a typo in DAMAGE must not pass
        raise AssertionError(damage)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=st.sampled_from(SCENARIOS), damage=st.sampled_from(DAMAGE))
def test_rg_05_storage_format_resolve_and_classify_agree(tmp_path: Path, scenario: str, damage: Any) -> None:
    resolve = resolver()
    base = tmp_path / f"ex{next(_EX)}"
    base.mkdir()
    if damage in REPAIRABLE:
        book = build_repairable(damage, base)
    else:
        book = setup_scenario(scenario, base)
        _damage(book, damage)
    books_dir = str(base / "books")
    d = base / "books" / "sample_data"
    assert book == d
    c = book_format.classify(str(d), full=False)

    assert book_store.storage_format("sample_data", books_dir) == c
    assert book_store.storage_format("sample_data", books_dir) == c
    r = outcome(resolve, "sample_data", books_dir)
    if c == "corrupt":
        assert isinstance(r, BC), f"{scenario}/{damage}: classify says corrupt, resolve gave {r!r}"
        return
    assert not isinstance(r, BaseException), f"{scenario}/{damage}: classify says {c}, resolve raised {r!r}"
    assert r.state == c
    assert (r.manifest is not None) == (c == "valid")
    if c == "valid":
        assert r.manifest_key == ident(d / MANIFEST)
        assert r.manifest == book_format.manifest_from_bytes((d / MANIFEST).read_bytes())
        assert r.gen_dir == str(d / "gen" / str(r.manifest.generation))
    else:
        assert (r.gen_dir, r.manifest_key) == (None, None)


# --------------------------------------------------------------------------- RG-06 no memo


def test_rg_06_republish_corrupt_and_delete_are_visible_on_the_next_call(
    books: Path, caplog: pytest.LogCaptureFixture
) -> None:
    resolve = resolver()
    caplog.set_level(logging.DEBUG)
    formats: list[str] = []
    error_counts: list[int] = []

    def step() -> Any:
        before = len(errors(caplog))
        formats.append(book_store.storage_format(G, str(books)))
        out = outcome(resolve, G, str(books))
        error_counts.append(len(errors(caplog)) - before)
        return out

    assert gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v1") == 1
    r1 = step()
    assert gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v2") == 2
    r2 = step()
    tmp = books / G / "manifest.json.rg06"
    tmp.write_bytes(b"{")
    os.replace(tmp, books / G / MANIFEST)
    r3 = step()
    assert gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v3") == 3
    r4 = step()
    os.unlink(books / G / MANIFEST)
    r5 = step()

    assert not isinstance(r1, BaseException) and r1.manifest.generation == 1, r1
    assert not isinstance(r2, BaseException) and r2.manifest.generation == 2, r2
    assert isinstance(r3, BC), f"step 3: expected BookCorrupt, got {r3!r}"
    assert not isinstance(r4, BaseException) and r4.manifest.generation == 3, r4
    assert r4.manifest_key != r2.manifest_key
    assert not isinstance(r5, BaseException) and r5.state == "missing", r5
    assert formats == ["valid", "valid", "corrupt", "valid", "missing"]
    assert error_counts == [0, 0, 1, 0, 0]


# --------------------------------------------------------------------------- RG-07 (optional) same-mtime republish


def test_rg_07_same_mtime_republish_changes_the_key_via_st_ino(books: Path) -> None:
    resolve = resolver()
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v1")
    k1 = resolve(G, str(books)).manifest_key
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob(), tag="v2")
    mpath = books / G / MANIFEST
    os.utime(mpath, ns=(k1[1], k1[1]))
    s = os.lstat(mpath)
    assert s.st_mtime_ns == k1[1], "precondition: the forced mtime held"
    if s.st_size == k1[2]:
        assert s.st_ino != k1[0], "precondition: os.replace gave the manifest a new inode"

    r = resolve(G, str(books))

    assert r.manifest_key != k1
    assert r.manifest.generation == 2


# --------------------------------------------------------------------------- RG-08 silence


def test_rg_08_storage_format_is_silent_in_every_state(
    tmp_path: Path, books: Path, caplog: pytest.LogCaptureFixture
) -> None:
    resolve = resolver()
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob())
    pkl_book(books, "flat_data", TEXTS)
    corrupt_dirs = []
    for i, shape in enumerate(["garbage", "format-v2", "manifest-is-dir"]):
        cb = tmp_path / f"corrupt_books_{i}"
        cb.mkdir()
        assert build_corrupt(shape, tmp_path, cb, flat_pkl=False) == G
        corrupt_dirs.append(str(cb))
    caplog.set_level(logging.DEBUG)
    caplog.clear()

    states = [book_store.storage_format(G, str(books)), book_store.storage_format("flat_data", str(books))]
    states += [book_store.storage_format(G, cb) for cb in corrupt_dirs]
    r_valid = resolve(G, str(books))
    r_missing = resolve("flat_data", str(books))

    assert states == ["valid", "missing", "corrupt", "corrupt", "corrupt"]
    assert (r_valid.state, r_missing.state) == ("valid", "missing")
    assert [(r.name, r.levelname, r.getMessage()) for r in caplog.records] == []


# --------------------------------------------------------------------------- RG-09 / RG-09b structural


def _module_funcs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _bare_calls(fn: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _closure(funcs: dict[str, ast.FunctionDef], roots: typing.Iterable[str]) -> set[str]:
    """``roots`` plus every module-level function in ``funcs`` they reach by bare-name call, transitively."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        stack.extend(_bare_calls(funcs[name]))
    return seen


def _type_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    out: set[str] = set()
    for p in parts:
        if isinstance(p, ast.Name):
            out.add(p.id)
        elif isinstance(p, ast.Attribute):
            out.add(p.attr)
    return out


def _try_names(t: ast.Try) -> set[str]:
    names: set[str] = set()
    for h in t.handlers:
        names |= _type_names(h.type)
    return names


def _is_attr_call(node: ast.AST, owner: str, attr: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == owner and node.func.attr == attr)


def _resolve_path() -> tuple[dict[str, ast.FunctionDef], set[str], ast.Module]:
    bs = ast.parse(inspect.getsource(book_store))
    funcs = _module_funcs(bs)
    roots = ("resolve_generation", "storage_format")
    assert set(roots) <= set(funcs), f"book_store must define {roots} at module level"
    return funcs, _closure(funcs, roots), bs


def test_rg_09_book_store_owns_no_classification_ladder() -> None:
    resolver()
    funcs, path, _ = _resolve_path()
    forbidden_handlers = {"FileNotFoundError", "NotADirectoryError", "OSError", "BookFormatError"}
    for name in sorted(path):
        fn = funcs[name]
        for node in ast.walk(fn):
            if isinstance(node, ast.ExceptHandler):
                caught = _type_names(node.type) & forbidden_handlers
                assert not caught, f"book_store.{name} catches {sorted(caught)}: that is classify's ladder"
            assert not _is_attr_call(node, "os", "lstat"), f"book_store.{name} calls os.lstat"
            assert not _is_attr_call(node, "book_format", "validate_stat"), f"book_store.{name} calls validate_stat"
            assert not _is_attr_call(node, "book_format", "classify"), f"book_store.{name} calls classify"


READERS = {"validate_stat", "_read_manifest", "_read_nofollow"}
STATE_NAMES = {"BookState", "MISSING", "CORRUPT", "VALID"}


def test_rg_09b_book_format_owns_exactly_one_ladder_and_classify_delegates_to_it() -> None:
    resolver()
    bf = ast.parse(inspect.getsource(book_format))
    FUNCS = _module_funcs(bf)
    bs_funcs, path, bs = _resolve_path()

    # Discover F: the one book_format function book_store's resolve path calls.
    imported = {a.asname or a.name for n in bs.body if isinstance(n, ast.ImportFrom)
                and n.module == "book_format" and n.level == 1 for a in n.names}
    found: set[str] = set()
    for name in path:
        for node in ast.walk(bs_funcs[name]):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "book_format"
                    and f.attr in FUNCS):
                found.add(f.attr)
            elif isinstance(f, ast.Name) and f.id in imported and f.id in FUNCS:
                found.add(f.id)
    assert len(found) == 1, f"book_store's resolve path must call exactly one book_format core, found {found}"
    (F,) = found

    def reaches(fn: str, targets: set[str]) -> bool:
        return bool(_closure(FUNCS, _bare_calls(FUNCS[fn])) & targets) or bool(_bare_calls(FUNCS[fn]) & targets)

    def pair_try(fn: str) -> bool:
        return any(isinstance(t, ast.Try) and {"FileNotFoundError", "NotADirectoryError"} <= _try_names(t)
                   for t in ast.walk(FUNCS[fn]))

    # (a) classify delegates to F and keeps no ladder of its own.
    classify = FUNCS["classify"]
    assert F in _bare_calls(classify), f"classify must call the shared core {F!r}"
    loud_trys = []
    for t in ast.walk(classify):
        if not isinstance(t, ast.Try):
            continue
        names = _try_names(t)
        assert not names & {"FileNotFoundError", "NotADirectoryError"}, "classify still catches the missing pair"
        if names & {"OSError", "BookFormatError"}:
            body_calls = _bare_calls(ast.Module(body=t.body, type_ignores=[]))
            assert not body_calls & ({F} | READERS), f"classify's OSError try reads the manifest: {body_calls}"
            assert not any(_is_attr_call(n, "os", "lstat") for b in t.body for n in ast.walk(b)), \
                "classify's OSError try calls os.lstat"
            loud_trys.append(t)

    # (e) at most one such try, and it wraps exactly one statement whose only call is validate_full(...).
    assert len(loud_trys) <= 1, f"classify may keep one (BookFormatError, OSError) try, found {len(loud_trys)}"
    for t in loud_trys:
        assert len(t.body) == 1, f"classify's validate_full try must hold one statement, holds {len(t.body)}"
        calls = [n for n in ast.walk(t.body[0]) if isinstance(n, ast.Call)]
        assert len(calls) == 1 and isinstance(calls[0].func, ast.Name) and calls[0].func.id == "validate_full", \
            f"the only call in classify's try must be validate_full(...), found {[ast.dump(c.func) for c in calls]}"

    # (b) every other function that catches the pair and reads the manifest is F or something F calls.
    S = {f for f in FUNCS if pair_try(f) and reaches(f, READERS)}
    # (c) _gc_decide is exempt by name: it decides what GC may delete (under the EX lock, ADR-0016 safe GC) and
    # returns a GcResult / deletion plan; it does not classify a book for the read path, and it predates 4a.
    # Renaming it fails this test loudly, and the exemption is then updated deliberately, with a reason.
    S -= {"_gc_decide", "classify"}
    reach_f = _closure(FUNCS, [F])
    assert S <= {F} | reach_f, f"a second classification ladder outside the core {F!r}: {sorted(S - reach_f)}"

    # (d) the exemption holds only while _gc_decide does not answer a storage state.
    gc = FUNCS["_gc_decide"]
    for ret in (n for n in ast.walk(gc) if isinstance(n, ast.Return) and n.value is not None):
        assert not (isinstance(ret.value, ast.Constant) and ret.value.value in {"missing", "corrupt", "valid"}), \
            "_gc_decide returns a bare storage state"
        refs = {n.id for n in ast.walk(ret.value) if isinstance(n, ast.Name)}
        refs |= {n.attr for n in ast.walk(ret.value) if isinstance(n, ast.Attribute)}
        assert not refs & STATE_NAMES, f"_gc_decide returns a storage-state name: {refs & STATE_NAMES}"
    ann = gc.returns
    assert ann is None or not (isinstance(ann, ast.Name) and ann.id == "BookState") and not (
        isinstance(ann, ast.Constant) and ann.value == "BookState"), "_gc_decide is annotated -> BookState"


# --------------------------------------------------------------------------- RG-10 key = identity of the parsed file


@pytest.mark.parametrize("row", ["before-open", "after-read"])
def test_rg_10_manifest_key_is_the_identity_of_the_file_actually_parsed(
    books: Path, row: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve = resolver()
    gen_book_pkl(books, G, texts=TEXTS, fp=FP_A, pkl=blob())
    a_path = books / G / MANIFEST
    b_path = books / G / "manifest.json.next"
    b_path.write_bytes(a_path.read_bytes())
    sa = os.lstat(a_path)
    os.utime(b_path, ns=(sa.st_mtime_ns + 10**9, sa.st_mtime_ns + 10**9))
    id_a, id_b = ident(a_path), ident(b_path)
    assert id_a != id_b
    done: list[int] = []

    def swap() -> None:
        if not done:
            os.replace(b_path, a_path)
            done.append(1)

    if row == "before-open":
        real_read = book_format._read_nofollow

        def read(path: Any, *a: Any, **kw: Any) -> Any:
            if str(path).endswith("manifest.json"):
                swap()
            return real_read(path, *a, **kw)

        monkeypatch.setattr("reader3_app.book_format._read_nofollow", read)
    else:
        real_parse = book_format.manifest_from_bytes

        def parse(data: Any, *a: Any, **kw: Any) -> Any:
            swap()
            return real_parse(data, *a, **kw)

        monkeypatch.setattr("reader3_app.book_format.manifest_from_bytes", parse)

    r = resolve(G, str(books))

    assert done == [1], "the swap never happened: the trigger point moved"
    assert os.lstat(a_path).st_ino == id_b[0]
    assert r.state == "valid"
    assert r.manifest.generation == 1
    assert r.manifest_key == (id_b if row == "before-open" else id_a)
