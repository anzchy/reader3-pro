"""012 WI-4a.3: R-5, every Book-producing load path stamps ``Book.book_fingerprint`` from storage truth.

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4a.md`` section ``## WI-4a.3``, cases R5-01 … R5-05, R5-07 … R5-09,
plus DF-23b (deferred here from WI-4a.2: its fingerprint leg needs the stamp). R5-06 is the ``[contract]`` sibling
``tests/contract/test_book_store_r5_notes.py``. Rulings: the plan's "Coordinator rulings 2026-10-09 (WI-4a)".

Laws pinned here:

* For any Book ``b`` returned by ``book_store.load_book_cached`` / ``book_store.load_book`` /
  ``search_service.load_book_cached`` / ``server.load_book_cached``, ``b.book_fingerprint`` is the manifest's
  fingerprint when the book is a valid generation and ``None`` otherwise -- whatever the pickle carried. "The
  manifest" is the snapshot the producing call resolved, so content and stamp come from one manifest read.
* No returned object is mutated after its first return: a warm hit performs zero ``__setattr__`` on the Book.

``load_book_metadata`` returns a ``BookMetadataView``, not a Book, so R-5 is N/A to it (R5-07 pins that).
Every case runs on real files under ``tmp_path``; the only patches are delegating spies and one fault injector,
by literal string.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import logging
import pickle
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from wi2b_world import FP_A, FP_B
from wi4a_world import G, book_obj, flat_pkl, gen_book_pkl, outcome

from reader3_app import book_format, book_store, search_service
from reader3_app.web import server

PKL = book_format.PKL
TEXTS = ["alpha", "beta gamma"]
STALE = "STALE"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROPS = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


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


def gen_stale(books: Path, folder: str, *, fp: str = FP_A, pickled: Optional[str] = STALE, title: str = "GEN",
              texts: List[str] = TEXTS, tag: str = "v1") -> int:
    """A generation whose manifest fingerprint is ``fp`` and whose declared ``book.pkl`` carries ``pickled``."""
    return gen_book_pkl(books, folder, texts=texts, fp=fp, pkl=pickle.dumps(book_obj(title, texts, pickled)), tag=tag)


def errors(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def producers(books: Path, monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Callable[[str], Any]]]:
    """The four Book producers (``test_storage_format.entry_points`` extended with the server wrapper)."""
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(books))
    d = str(books)
    return [
        ("book_store.load_book_cached", lambda b: book_store.load_book_cached(b, d)),
        ("book_store.load_book", lambda b: book_store.load_book(b, d)),
        ("search_service.load_book_cached", lambda b: search_service.load_book_cached(b, d)),
        ("server.load_book_cached", lambda b: server.load_book_cached(b)),
    ]


class SetattrSpy:
    """Delegating spy on ``Book.__setattr__``: records ``(id(self), name)`` and calls ``object.__setattr__``."""

    def __init__(self) -> None:
        self.calls: List[Tuple[int, str]] = []

    def install(self, mp: pytest.MonkeyPatch) -> "SetattrSpy":
        def spy(obj: Any, name: str, value: Any) -> None:
            self.calls.append((id(obj), name))
            object.__setattr__(obj, name, value)

        mp.setattr("reader3_app.reader3.Book.__setattr__", spy)
        return self


# --------------------------------------------------------------------------- R5-01


STATES = ["gen-stale", "flat-stale", "flat-noattr"]
PRODUCER_NAMES = ["book_store.load_book_cached", "book_store.load_book", "search_service.load_book_cached",
                  "server.load_book_cached"]


def build_state(books: Path, state: str) -> Tuple[str, Optional[str]]:
    """Build ``state`` under ``books``; return ``(book_id, expected fingerprint)``."""
    if state == "gen-stale":
        gen_stale(books, G)
        assert not (books / G / PKL).exists(), "gen-stale has no flat pkl"
        return G, FP_A
    if state == "flat-stale":
        flat_pkl(books, "flat_data", book_obj("FLAT", TEXTS, STALE))
        return "flat_data", None
    book = book_obj("FLAT", TEXTS, drop_fp=True)
    assert "book_fingerprint" not in vars(book), "flat-noattr models a pre-R-5 pickle"
    flat_pkl(books, "flat_data", book)
    return "flat_data", None


@pytest.mark.parametrize("producer", PRODUCER_NAMES)
@pytest.mark.parametrize("state", STATES)
def test_r5_01_every_producer_returns_the_storage_fingerprint(
    books: Path, monkeypatch: pytest.MonkeyPatch, state: str, producer: str
) -> None:
    bid, expected = build_state(books, state)
    fn = dict(producers(books, monkeypatch))[producer]
    book_store.load_book_cached.cache_clear()

    got = outcome(fn, bid)

    assert not isinstance(got, BaseException), f"{producer} raised {got!r}"
    assert got is not None, f"{producer} returned None"
    assert got.metadata.title == ("GEN" if state == "gen-stale" else "FLAT")
    assert got.book_fingerprint == expected, f"{producer} on {state}: {got.book_fingerprint!r} != {expected!r}"


# --------------------------------------------------------------------------- R5-02

_EXAMPLE = itertools.count()
SAME = object()


@PROPS
@given(
    form=st.sampled_from(["gen", "flat"]),
    manifest_fp=st.text("0123456789abcdef", min_size=64, max_size=64),
    pickled=st.none() | st.text(max_size=20) | st.just(SAME),
)
def test_r5_02_property_fingerprint_equals_storage_truth(
    books: Path, form: str, manifest_fp: str, pickled: Any
) -> None:
    folder = f"p{next(_EXAMPLE)}_data"
    pickled_fp = manifest_fp if pickled is SAME else pickled
    if form == "gen":
        gen_stale(books, folder, fp=manifest_fp, pickled=pickled_fp)
    else:
        flat_pkl(books, folder, book_obj("FLAT", TEXTS, pickled_fp))

    got = book_store.load_book(folder, str(books))

    expected = manifest_fp if form == "gen" else None
    assert got.book_fingerprint == expected, (form, pickled_fp, got.book_fingerprint)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- R5-03


def test_r5_03_republish_never_restamps_the_previous_object(books: Path) -> None:
    gen_stale(books, G, fp=FP_A, pickled=FP_A, title="A")
    a = book_store.load_book(G, str(books))

    gen_stale(books, G, fp=FP_B, pickled=FP_B, title="B", tag="v2")
    b = book_store.load_book(G, str(books))

    assert a is not b
    assert (a.metadata.title, b.metadata.title) == ("A", "B")  # type: ignore[attr-defined]
    assert a.book_fingerprint == FP_A  # type: ignore[attr-defined]
    assert b.book_fingerprint == FP_B  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- R5-04


@pytest.mark.parametrize("form", ["gen", "flat"])
def test_r5_04_cold_stamps_once_and_a_warm_hit_mutates_nothing(
    books: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    if form == "gen":
        gen_stale(books, G)
        bid, expected = G, FP_A
    else:
        flat_pkl(books, "flat_data", book_obj("FLAT", TEXTS, STALE))
        bid, expected = "flat_data", None
    spy = SetattrSpy().install(monkeypatch)

    x = book_store.load_book_cached(bid, str(books))
    cold = list(spy.calls)
    before = (id(x), x.book_fingerprint)  # type: ignore[attr-defined]
    y = book_store.load_book_cached(bid, str(books))
    warm = spy.calls[len(cold):]

    assert cold == [(id(x), "book_fingerprint")], cold
    assert warm == [], warm
    assert y is x
    assert (id(y), y.book_fingerprint) == before == (id(x), expected)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- R5-05


def _assigns_fingerprint(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "book_fingerprint" and isinstance(node.ctx, ast.Store):
            return True
        if isinstance(node, ast.Call) and len(node.args) >= 2:
            func = node.func
            named = (isinstance(func, ast.Name) and func.id == "setattr") or (
                isinstance(func, ast.Attribute) and func.attr == "__setattr__"
            )
            arg = node.args[1]
            if named and isinstance(arg, ast.Constant) and arg.value == "book_fingerprint":
                return True
    return False


def test_r5_05_only_book_store_assigns_book_fingerprint() -> None:
    src = REPO_ROOT / "src" / "reader3_app"
    files = sorted(src.rglob("*.py"))
    assert len(files) > 20, f"scan found too few modules under {src}"

    offenders = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in files
        if _assigns_fingerprint(ast.parse(p.read_text(encoding="utf-8"), filename=str(p)))
    }

    assert offenders == {"src/reader3_app/book_store.py"}, offenders


def test_r5_05_scanner_flags_each_assignment_shape() -> None:
    """The scanner itself: each assignment shape it claims to catch is caught, and the field declaration is not."""
    caught = [
        "b.book_fingerprint = fp",
        "b.book_fingerprint += fp",
        "b.book_fingerprint: str = fp",
        "setattr(b, 'book_fingerprint', fp)",
        "object.__setattr__(b, 'book_fingerprint', fp)",
    ]
    ignored = [
        "class Book:\n    book_fingerprint: Optional[str] = None",
        "x = b.book_fingerprint",
        "getattr(b, 'book_fingerprint', None)",
        "f(book_fingerprint=fp)",
    ]
    assert [s for s in caught if not _assigns_fingerprint(ast.parse(s))] == []
    assert [s for s in ignored if _assigns_fingerprint(ast.parse(s))] == []


# --------------------------------------------------------------------------- R5-07


def test_r5_07_load_book_metadata_carries_no_fingerprint(books: Path) -> None:
    gen_stale(books, G)

    view = book_store.load_book_metadata(G, str(books))

    assert isinstance(view, book_store.BookMetadataView)
    assert view.title == "GEN"
    assert not hasattr(view, "book_fingerprint")
    assert [f.name for f in dataclasses.fields(view)] == ["book_id", "title", "authors"]
    assert "R-5" in (book_store.load_book_metadata.__doc__ or ""), "the docstring must state R-5 is N/A"


# --------------------------------------------------------------------------- R5-08


@pytest.mark.parametrize("form", ["gen", "flat"])
def test_r5_08_a_failing_stamp_is_not_masked_as_corrupt(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, form: str
) -> None:
    if form == "gen":
        gen_stale(books, G)
        bid = G
    else:
        flat_pkl(books, "flat_data", book_obj("FLAT", TEXTS, STALE))
        bid = "flat_data"

    def boom(obj: Any, name: str, value: Any) -> None:
        if name == "book_fingerprint":
            raise RuntimeError("STAMP-SENTINEL")
        object.__setattr__(obj, name, value)

    monkeypatch.setattr("reader3_app.reader3.Book.__setattr__", boom)
    caplog.set_level(logging.DEBUG)

    exc = outcome(book_store.load_book_cached, bid, str(books))

    assert type(exc) is RuntimeError, f"expected the stamp's RuntimeError, got {exc!r}"
    assert "STAMP-SENTINEL" in str(exc)
    assert errors(caplog) == [], [r.getMessage() for r in errors(caplog)]
    assert book_store.load_book_cached.cache_info().currsize == 0


# --------------------------------------------------------------------------- R5-09


def test_r5_09_concurrent_cold_loads_never_observe_the_pickled_value(books: Path) -> None:
    gen_stale(books, G)
    barrier = threading.Barrier(2)
    seen: Dict[int, Tuple[Any, Any]] = {}
    failures: List[BaseException] = []

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=10)
            got = book_store.load_book_cached(G, str(books))
            seen[i] = (got, got.book_fingerprint)  # type: ignore[attr-defined]
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert failures == []
    assert sorted(seen) == [0, 1]
    assert [seen[i][1] for i in (0, 1)] == [FP_A, FP_A]
    assert [seen[i][0].book_fingerprint for i in (0, 1)] == [FP_A, FP_A]


# --------------------------------------------------------------------------- DF-23b


def test_df_23b_republish_mid_load_serves_one_manifest_snapshot(
    books: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gen_stale(books, G, fp=FP_A, pickled=STALE, title="G1", texts=["one"])
    real = book_store.load_book_file
    paths: List[str] = []
    fired: List[bool] = []

    def wrapper(path: Any, *a: Any, **kw: Any) -> Any:
        paths.append(str(path))
        if not fired:
            fired.append(True)
            gen_stale(books, G, fp=FP_B, pickled=STALE, title="G2", texts=["two"], tag="v2")
        return real(path, *a, **kw)

    monkeypatch.setattr("reader3_app.book_store.load_book_file", wrapper)
    caplog.set_level(logging.DEBUG)

    x = book_store.load_book_cached(G, str(books))
    manifest = book_format.manifest_from_bytes((books / G / book_format.MANIFEST).read_bytes())
    assert manifest.generation == 2, "the republish must have landed mid-load"
    assert (books / G / book_format.GEN_DIR / "1" / PKL).is_file(), "gen/1 must survive the mid-load publish"

    assert paths == [str(books / G / book_format.GEN_DIR / "1" / PKL)]
    assert x.metadata.title == "G1"  # type: ignore[attr-defined]
    assert [c.text for c in x.spine] == ["one"]  # type: ignore[attr-defined]
    assert x.book_fingerprint == FP_A  # type: ignore[attr-defined]

    y = book_store.load_book_cached(G, str(books))

    assert y is not x
    assert y.metadata.title == "G2"  # type: ignore[attr-defined]
    assert y.book_fingerprint == FP_B  # type: ignore[attr-defined]
    assert x.book_fingerprint == FP_A  # type: ignore[attr-defined]
    assert errors(caplog) == []
