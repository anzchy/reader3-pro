"""012 WI-4c.1: ``chapter_index`` means ``order`` (ADR-0016) in ``book_store`` and in rebind (D-b).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi4c1.md`` cases CO-00 … CO-23 (no CO-20), with the binding
coordinator rulings on DP-1..DP-7 and DP-4b and the adversary rounds 1 and 2 applied. CO-05 / CO-06 (the R4-06
rule-12 flips) live in ``test_book_store_current_generation.py``.

The laws:
- L1: for strictly increasing ``orders``, ``find_chapter(book, n) is dict(zip(orders, spine)).get(n)`` for every
  int ``n``; ``load_chapter`` is the same through ``load_book_cached`` and raises ``ChapterNotFound`` on a miss;
  ``CurrentGeneration.chapter_text(o)`` reads the manifest entry whose ``order`` is ``o``.
- L3: ``neighbour_orders(book, n)`` is ``(max{x < n}, min{x > n})`` with ``None`` for an empty side.
- L5: a gen book's Book and its manifest carry the same orders, and both read paths agree.
- Q5: orders that are not ``>= 0`` and strictly increasing raise ``BookCorrupt`` from every entry point.
- Rebind (R-3 follow-up 1): same-order lookup only; a gap or past-the-end note is ``unmatched`` with
  ``evaluated = current``, never orphaned, every binding field byte-identical. A non-strict manifest is
  "cannot judge" (DP-4 / DP-4b): nothing written, ``fingerprint=None``.
- No mutation of the cached Book and no cache besides the one ``lru_cache`` (R5-04 extended).

Every case uses real files under ``tmp_path`` / ``tempfile``, real ``book_format.publish`` under the real EX lock,
the real ``safe_pickle`` loader and the real ``load_book_cached``. The only monkeypatches are delegating
``__setattr__`` spies (CO-09).
"""

from __future__ import annotations

import collections
import dataclasses
import itertools
import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from book_format_helpers import REPAIRABLE, snapshot
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from wi2b_world import (
    ABSENT,
    FP_A,
    FP_B,
    RESOLUTIONS,
    _book,
    disk,
    publish_gen,
    rec,
    seed_notes,
    version_on_disk,
    write_book_pkl,
)
from wi4a_world import gen_book_pkl

from reader3_app import book_format, book_store, notes_service
from reader3_app.models.annotations import match_resolution
from reader3_app.reader3 import ChapterContent

G = "g_data"
TEXTS2 = ["t0 zero", "t1 one"]
KEY = notes_service.NOTES_FINGERPRINT_KEY
NON_BINDING = ("resolution", "evaluated_fingerprint")
_COUNTER = itertools.count()


def _api(name: str) -> Any:
    """The 4a pattern: a missing symbol is a counted assertion failure, not an import error."""
    assert hasattr(book_store, name), f"book_store.{name} does not exist yet"
    return getattr(book_store, name)


def _binding_raw(record: Dict[str, Any]) -> Dict[str, Any]:
    """Every key except the two rebind may write (R-3 follow-up 1); compared as raw notes.json JSON values."""
    return {k: v for k, v in record.items() if k not in NON_BINDING}


def _same_raw(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every relative path resolves under tmp_path (never a real books/ dir); the one cache is cold both ways."""
    monkeypatch.chdir(tmp_path)
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]
    yield
    book_store.load_book_cached.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def books(tmp_path: Path) -> Path:
    out = tmp_path / "books"
    out.mkdir()
    return out


def _store(form: str, books_dir: Path, bid: str, texts: List[str], orders: List[int]) -> None:
    if form == "flat":
        write_book_pkl(books_dir, bid, texts, None, orders=orders)
    else:
        publish_gen(books_dir, bid, texts, FP_A, "A", orders=orders)


def _set_manifest_order(book_dir: Path, index: int, order: int) -> None:
    """Hand-edit ``manifest.chapters[index].order`` through the canonical serializer (``chapters.jsonl`` untouched)."""
    path = Path(book_dir) / "manifest.json"
    m = book_format.manifest_from_bytes(path.read_bytes())
    chapters = list(m.chapters)
    chapters[index] = dataclasses.replace(chapters[index], order=order)
    path.write_bytes(book_format.manifest_to_bytes(dataclasses.replace(m, chapters=tuple(chapters))))


# --------------------------------------------------------------------------- CO-00 (fixture self-check)


def test_co_00_helper_orders_reach_manifest_and_gen_book_and_default_is_unchanged(books: Path) -> None:
    def gen_orders(folder: str) -> Tuple[List[int], List[int]]:
        m = book_format.validate_stat(books / folder)
        gen_dir = books / folder / book_format.GEN_DIR / str(m.generation)
        spine = pickle.loads((gen_dir / book_format.PKL).read_bytes()).spine
        return [e.order for e in m.chapters], [c.order for c in spine]

    publish_gen(books, "o_data", ["a", "b", "c"], FP_A, "A", orders=[0, 2, 5])
    publish_gen(books, "d_data", ["a", "b"], FP_A, "A")
    write_book_pkl(books, "f_data", ["a", "b"], None, orders=[1, 3])

    assert gen_orders("o_data") == ([0, 2, 5], [0, 2, 5])
    assert gen_orders("d_data") == ([0, 1], [0, 1])
    assert [c.order for c in pickle.loads((books / "f_data" / "book.pkl").read_bytes()).spine] == [1, 3]


# --------------------------------------------------------------------------- CO-01 (A5 example table)

FORMS = ["flat", "gen"]


@pytest.mark.parametrize("form", FORMS)
def test_co_01_a5_on_orders_0_2(books: Path, form: str) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    not_found = _api("ChapterNotFound")
    _store(form, books, "a_data", TEXTS2, [0, 2])
    d = str(books)
    before = snapshot(books / "a_data")

    c = load_chapter("a_data", d, 2)
    assert (c.id, c.href, c.text, c.order) == ("c1", "Text/c1.xhtml", "t1 one", 2)
    assert load_chapter("a_data", d, 0).id == "c0"
    with pytest.raises(not_found):
        load_chapter("a_data", d, 1)
    assert chapter_count("a_data", d) == 2
    assert snapshot(books / "a_data") == before


@pytest.mark.parametrize("form", FORMS)
def test_co_01_a5_on_orders_1_3(books: Path, form: str) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    not_found = _api("ChapterNotFound")
    _store(form, books, "b_data", TEXTS2, [1, 3])
    d = str(books)

    assert load_chapter("b_data", d, 1).id == "c0"
    assert load_chapter("b_data", d, 3).id == "c1"
    for n in (0, 2):
        with pytest.raises(not_found):
            load_chapter("b_data", d, n)
    assert chapter_count("b_data", d) == 2


@pytest.mark.parametrize("form", FORMS)
def test_co_01_a5_on_an_empty_book(books: Path, form: str) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters, not_found = _api("iter_chapters"), _api("ChapterNotFound")
    _store(form, books, "e_data", [], [])
    d = str(books)

    assert chapter_count("e_data", d) == 0
    with pytest.raises(not_found):
        load_chapter("e_data", d, 0)
    assert list(iter_chapters("e_data", d)) == []


# --------------------------------------------------------------------------- CO-02 (ChapterNotFound)


def _check_not_found_message(msg: Any, bid: str, n: int, books_dir: Path) -> None:
    assert isinstance(msg, str), msg
    assert repr(bid) in msg, msg
    assert str(n) in msg, msg
    assert "secret-dir-XYZ" not in msg, msg
    assert str(books_dir) not in msg, msg


def test_co_02_chapter_not_found_type_and_message_from_every_raise_site(tmp_path: Path) -> None:
    not_found, load_chapter = _api("ChapterNotFound"), _api("load_chapter")
    assert issubclass(not_found, KeyError)
    assert not issubclass(not_found, book_format.BookFormatError)
    books_dir = tmp_path / "secret-dir-XYZ" / "books"
    books_dir.mkdir(parents=True)
    write_book_pkl(books_dir, "cnf_data", TEXTS2, None, orders=[0, 2])
    publish_gen(books_dir, "cnf_gen_data", TEXTS2, FP_A, "A", orders=[0, 2])
    before = snapshot(books_dir)

    for bid in ("cnf_data", "cnf_gen_data"):
        for n in (1, -1, 3, 10**9):
            with pytest.raises(not_found) as ei:
                load_chapter(bid, str(books_dir), n)
            _check_not_found_message(ei.value.args[0], bid, n, books_dir)

    g = book_store.current_generation("cnf_gen_data", str(books_dir))
    assert g is not None
    with pytest.raises(not_found) as ei:
        g.chapter_text(1)
    _check_not_found_message(ei.value.args[0], "cnf_gen_data", 1, books_dir)
    assert snapshot(books_dir) == before


# --------------------------------------------------------------------------- CO-03 / CO-04 (pure L1, L3)

SORTED_UNIQUE_60 = st.lists(st.integers(0, 60), max_size=12, unique=True).map(sorted)


@settings(max_examples=200, deadline=None)
@given(xs=SORTED_UNIQUE_60)
@example(xs=[0, 2])
@example(xs=[1, 3])
@example(xs=[])
@example(xs=[0, 1, 2])
def test_co_03_find_chapter_against_a_model_oracle(xs: List[int]) -> None:
    find_chapter, chapter_orders = _api("find_chapter"), _api("chapter_orders")
    book = _book("p_data", [f"t{i}-{x}" for i, x in enumerate(xs)], None, orders=xs)
    m = dict(zip(xs, book.spine))

    assert chapter_orders(book, book_id="p_data") == tuple(xs)
    for n in range(-3, (max(xs) if xs else 0) + 4):
        got = find_chapter(book, n, book_id="p_data")
        if n in m:
            assert got is m[n], (xs, n)
        else:
            assert got is None, (xs, n)


@settings(max_examples=200, deadline=None)
@given(xs=SORTED_UNIQUE_60)
@example(xs=[0, 2])
@example(xs=[1, 3])
@example(xs=[])
@example(xs=[0, 1, 2])
@example(xs=[7])
def test_co_04_neighbour_orders_against_brute_force(xs: List[int]) -> None:
    neighbour_orders = _api("neighbour_orders")
    book = _book("p_data", [f"t{i}" for i in range(len(xs))], None, orders=xs)

    for n in range(-3, (max(xs) if xs else 0) + 4):
        expected = (max((x for x in xs if x < n), default=None), min((x for x in xs if x > n), default=None))
        assert neighbour_orders(book, n, book_id="p_data") == expected, (xs, n)
    if xs:
        assert neighbour_orders(book, xs[0], book_id="p_data")[0] is None
        assert neighbour_orders(book, xs[-1], book_id="p_data")[1] is None


# --------------------------------------------------------------------------- CO-14 / CO-16 (Q5, DP-5)


@settings(max_examples=200, deadline=None)
@given(xs=st.lists(st.integers(0, 20), max_size=8))
@example(xs=[1, 1])
@example(xs=[2, 1])
@example(xs=[0, 2, 2])
@example(xs=[0, 3, 1])
def test_co_14_chapter_orders_raises_iff_not_strictly_increasing(xs: List[int]) -> None:
    chapter_orders, find_chapter = _api("chapter_orders"), _api("find_chapter")
    neighbour_orders = _api("neighbour_orders")
    book = _book("q_data", [f"t{i}" for i in range(len(xs))], None, orders=xs)
    strict = all(a < b for a, b in zip(xs, xs[1:]))

    if strict:
        assert chapter_orders(book, book_id="q_data") == tuple(xs)
        return
    with pytest.raises(book_format.BookCorrupt) as ei:
        chapter_orders(book, book_id="q_data")
    assert "'q_data'" in str(ei.value)
    assert not isinstance(ei.value, KeyError)
    with pytest.raises(book_format.BookCorrupt):
        find_chapter(book, xs[0], book_id="q_data")
    with pytest.raises(book_format.BookCorrupt):
        neighbour_orders(book, xs[0], book_id="q_data")


@pytest.mark.parametrize("orders", [[-1, 2], [-5]])
def test_co_16_a_negative_order_is_corrupt_in_the_pure_helpers(orders: List[int]) -> None:
    chapter_orders, find_chapter = _api("chapter_orders"), _api("find_chapter")
    neighbour_orders = _api("neighbour_orders")
    book = _book("n_data", [f"t{i}" for i in range(len(orders))], None, orders=orders)

    for call in (
        lambda: chapter_orders(book, book_id="n_data"),
        lambda: find_chapter(book, -1, book_id="n_data"),
        lambda: neighbour_orders(book, 2, book_id="n_data"),
    ):
        with pytest.raises(book_format.BookCorrupt) as ei:
            call()
        assert "'n_data'" in str(ei.value)


def test_co_16_a_negative_order_is_corrupt_through_every_a5_entry_point(books: Path) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters = _api("iter_chapters")
    write_book_pkl(books, "n_data", ["a", "b"], None, orders=[-1, 2])
    d = str(books)

    for call in (
        lambda: load_chapter("n_data", d, 2),
        lambda: chapter_count("n_data", d),
        lambda: next(iter(iter_chapters("n_data", d))),
    ):
        with pytest.raises(book_format.BookCorrupt) as ei:
            call()
        assert "'n_data'" in str(ei.value)


# --------------------------------------------------------------------------- CO-11 / CO-12 (iter_chapters, A5-L1)


@pytest.mark.parametrize(
    ("form", "orders"),
    [("flat", [0, 2, 5]), ("flat", [0, 1, 2]), ("flat", []), ("gen", [0, 2, 5])],
)
def test_co_11_iter_chapters_yields_order_chapter_pairs_by_identity(books: Path, form: str, orders: List[int]) -> None:
    iter_chapters, chapter_orders = _api("iter_chapters"), _api("chapter_orders")
    bid = f"i_{form}_data"
    _store(form, books, bid, [f"x{i}" for i in range(len(orders))], orders)
    d = str(books)
    b = book_store.load_book_cached(bid, d)

    pairs = list(iter_chapters(bid, d))

    assert [o for o, _ in pairs] == orders
    assert len(pairs) == len(b.spine)  # type: ignore[attr-defined]
    assert all(c is s for (_, c), s in zip(pairs, b.spine))  # type: ignore[attr-defined]
    assert [o for o, _ in pairs] == list(chapter_orders(b, book_id=bid))
    assert [o for o, _ in pairs] == [c.order for _, c in pairs]
    assert list(iter_chapters(bid, d)) == pairs


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    xs=st.lists(st.integers(0, 40), max_size=8, unique=True).map(sorted),
    form=st.sampled_from(FORMS),
)
@example(xs=[0, 2], form="flat")
@example(xs=[0, 2], form="gen")
@example(xs=[1, 3], form="flat")
@example(xs=[1, 3], form="gen")
def test_co_12_a5_against_a_model_on_stored_books(books: Path, xs: List[int], form: str) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters, not_found = _api("iter_chapters"), _api("ChapterNotFound")
    bid = f"p{next(_COUNTER)}_data"
    _store(form, books, bid, [f"t{i}-{x}" for i, x in enumerate(xs)], xs)
    d = str(books)
    b = book_store.load_book_cached(bid, d)
    m = dict(zip(xs, b.spine))  # type: ignore[attr-defined]

    for n in range(-2, (max(xs) if xs else 0) + 3):
        if n in m:
            assert load_chapter(bid, d, n) is m[n]
        else:
            with pytest.raises(not_found):
                load_chapter(bid, d, n)
    assert chapter_count(bid, d) == len(xs)
    pairs = list(iter_chapters(bid, d))
    expected = list(m.items())
    assert [o for o, _ in pairs] == [o for o, _ in expected]
    assert all(c is e for (_, c), (_, e) in zip(pairs, expected))


# --------------------------------------------------------------------------- CO-13 (Q5 through every function)

NONSTRICT = {"dup": ([0, 2, 2], ["a", "b", "c"]), "desc": ([3, 1], ["a", "b"])}


def _check_corrupt(exc: BaseException, bid: str) -> None:
    assert isinstance(exc, book_format.BookCorrupt), repr(exc)
    assert repr(bid) in str(exc), str(exc)
    assert "secret-dir-XYZ" not in str(exc), str(exc)
    assert not isinstance(exc, KeyError)


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("state", sorted(NONSTRICT))
def test_co_13_a_non_strict_book_is_corrupt_through_every_function(tmp_path: Path, state: str, form: str) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters, find_chapter = _api("iter_chapters"), _api("find_chapter")
    neighbour_orders, chapter_orders = _api("neighbour_orders"), _api("chapter_orders")
    orders, texts = NONSTRICT[state]
    books_dir = tmp_path / "secret-dir-XYZ" / "books"
    books_dir.mkdir(parents=True)
    bid = f"c_{state}_{form}_data"
    if form == "flat":
        write_book_pkl(books_dir, bid, texts, None, orders=orders)
    else:
        gen_book_pkl(books_dir, bid, texts=texts, fp=FP_A, pkl=pickle.dumps(_book(bid, texts, FP_A, orders=orders)))
    d = str(books_dir)
    before = snapshot(books_dir / bid)
    b = book_store.load_book_cached(bid, d)  # loading does not judge orders
    assert [c.order for c in b.spine] == orders  # type: ignore[attr-defined]

    probes = sorted(set(orders) | {1 if state == "dup" else 2, -1, 99})
    calls = [lambda n=n: load_chapter(bid, d, n) for n in probes]
    calls += [lambda: chapter_count(bid, d), lambda: chapter_orders(b, book_id=bid)]
    calls += [lambda n=n: find_chapter(b, n, book_id=bid) for n in probes]
    calls += [lambda n=n: neighbour_orders(b, n, book_id=bid) for n in probes]
    for call in calls:
        for _ in range(2):  # a second identical call raises again
            with pytest.raises(book_format.BookCorrupt) as ei:
                call()
            _check_corrupt(ei.value, bid)

    with pytest.raises(book_format.BookCorrupt) as ei:
        next(iter(iter_chapters(bid, d)))
    _check_corrupt(ei.value, bid)
    yielded: List[Any] = []
    with pytest.raises(book_format.BookCorrupt):
        for pair in iter_chapters(bid, d):
            yielded.append(pair)
    assert yielded == []  # DP-3 ruling: nothing is yielded before the raise
    assert book_store.load_book_cached(bid, d) is b
    assert snapshot(books_dir / bid) == before


# --------------------------------------------------------------------------- CO-21 (loader failures propagate)


def test_co_21_loader_failures_propagate_and_are_never_chapter_not_found(books: Path, tmp_path: Path) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters, not_found = _api("iter_chapters"), _api("ChapterNotFound")
    publish_gen(books, G, TEXTS2, FP_A, "A")
    outside = tmp_path / "outside"
    outside.mkdir()
    REPAIRABLE["R-unparse"][0](books / G, outside)
    d = str(books)

    cases = [("nope_data", FileNotFoundError), (G, book_format.BookCorrupt), ("../escape_data", ValueError)]
    for bid, expected in cases:
        for call in (
            lambda: load_chapter(bid, d, 0),
            lambda: chapter_count(bid, d),
            lambda: next(iter(iter_chapters(bid, d))),
        ):
            with pytest.raises(expected) as ei:
                call()
            assert not isinstance(ei.value, not_found), (bid, repr(ei.value))


# --------------------------------------------------------------------------- CO-19 (freshness)


def test_co_19_a_rewritten_book_is_seen_by_the_next_a5_call(books: Path) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters, not_found = _api("iter_chapters"), _api("ChapterNotFound")
    write_book_pkl(books, "f_data", ["a", "b"], None, orders=[0, 2])
    d = str(books)
    assert chapter_count("f_data", d) == 2
    assert load_chapter("f_data", d, 2).text == "b"

    write_book_pkl(books, "f_data", ["x", "y", "z"], None, orders=[1, 3, 4])

    assert chapter_count("f_data", d) == 3
    assert load_chapter("f_data", d, 4).text == "z"
    with pytest.raises(not_found):
        load_chapter("f_data", d, 0)
    assert [o for o, _ in iter_chapters("f_data", d)] == [1, 3, 4]


# --------------------------------------------------------------------------- CO-07 (L5 gen/flat agreement)


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(xs=st.lists(st.integers(0, 30), min_size=1, max_size=6, unique=True).map(sorted))
@example(xs=[0, 2])
@example(xs=[1, 3])
@example(xs=[0, 2, 5])
def test_co_07_gen_book_manifest_load_chapter_and_chapter_text_agree(books: Path, xs: List[int]) -> None:
    load_chapter, not_found = _api("load_chapter"), _api("ChapterNotFound")
    bid = f"p{next(_COUNTER)}_data"
    texts = [f"text-{i}-{x}" for i, x in enumerate(xs)]
    publish_gen(books, bid, texts, FP_A, "A", orders=xs)
    d = str(books)
    b = book_store.load_book_cached(bid, d)
    manifest_orders = [e.order for e in book_format.validate_stat(books / bid).chapters]
    assert [c.order for c in b.spine] == manifest_orders == xs  # type: ignore[attr-defined]
    g = book_store.current_generation(bid, d)
    assert g is not None

    for n in range(-1, max(xs) + 3):
        if n in xs:
            assert load_chapter(bid, d, n).text == g.chapter_text(n) == texts[xs.index(n)]
        else:
            with pytest.raises(not_found):
                load_chapter(bid, d, n)
            with pytest.raises(not_found):
                g.chapter_text(n)
            assert not g.has_chapter(n)


# --------------------------------------------------------------------------- CO-09 / CO-23 (no mutation, no memo)


class SetattrSpy:
    """Delegating spy on ``__setattr__``: records ``(type, id(self), name)`` and calls ``object.__setattr__``."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, int, str]] = []

    def install(self, mp: pytest.MonkeyPatch) -> "SetattrSpy":
        def spy(obj: Any, name: str, value: Any) -> None:
            self.calls.append((type(obj).__name__, id(obj), name))
            object.__setattr__(obj, name, value)

        mp.setattr("reader3_app.reader3.Book.__setattr__", spy)
        mp.setattr("reader3_app.reader3.ChapterContent.__setattr__", spy)
        return self


def _container_sizes() -> Dict[str, int]:
    return {k: len(v) for k, v in vars(book_store).items() if isinstance(v, (dict, set, list))}


def _lru_wrappers() -> int:
    seen = set()
    for v in vars(book_store).values():
        info = getattr(v, "cache_info", None)
        if callable(info):
            seen.add(id(getattr(info, "__self__", v)))
    return len(seen)


@pytest.mark.parametrize(("form", "orders"), [("gen", [0, 2, 5]), ("flat", [1, 3])])
def test_co_09_a_thousand_calls_neither_mutate_the_cached_book_nor_add_a_cache(
    books: Path, monkeypatch: pytest.MonkeyPatch, form: str, orders: List[int]
) -> None:
    find_chapter, neighbour_orders = _api("find_chapter"), _api("neighbour_orders")
    chapter_orders, load_chapter = _api("chapter_orders"), _api("load_chapter")
    chapter_count, iter_chapters = _api("chapter_count"), _api("iter_chapters")
    not_found = _api("ChapterNotFound")
    bid = f"m_{form}_data"
    _store(form, books, bid, [f"x{i}" for i in range(len(orders))], orders)
    d = str(books)
    b = book_store.load_book_cached(bid, d)
    before = pickle.dumps(b)
    h0 = book_store.load_book_cached.cache_info()  # type: ignore[attr-defined]
    sizes0 = _container_sizes()
    spy = SetattrSpy().install(monkeypatch)

    a5_calls = 0
    for i in range(1000):
        n = (i % 9) - 1  # cycles over range(-1, 8)
        find_chapter(b, n, book_id=bid)
        neighbour_orders(b, n, book_id=bid)
        chapter_orders(b, book_id=bid)
        try:
            load_chapter(bid, d, n)
        except not_found:
            pass
        chapter_count(bid, d)
        list(iter_chapters(bid, d))
        a5_calls += 3
    info = book_store.load_book_cached.cache_info()  # type: ignore[attr-defined]

    assert spy.calls == []
    assert info.misses == h0.misses
    assert info.hits - h0.hits == a5_calls
    assert _container_sizes() == sizes0
    assert _lru_wrappers() == 1
    assert book_store.load_book_cached(bid, d) is b
    assert pickle.dumps(book_store.load_book_cached(bid, d)) == before


def test_co_23_the_pure_helpers_have_no_memo() -> None:
    chapter_orders, find_chapter = _api("chapter_orders"), _api("find_chapter")
    neighbour_orders = _api("neighbour_orders")
    book = _book("m_data", ["a", "b"], None, orders=[0, 2])
    assert chapter_orders(book, book_id="m_data") == (0, 2)

    book.spine.append(ChapterContent(id="c9", href="Text/c9.xhtml", title="T9", content="<p>z</p>", text="z", order=5))

    assert chapter_orders(book, book_id="m_data") == (0, 2, 5)
    assert find_chapter(book, 5, book_id="m_data") is book.spine[2]
    assert neighbour_orders(book, 2, book_id="m_data") == (0, 5)


# --------------------------------------------------------------------------- CO-17 (non-Book flat pickle)


def test_co_17_leg_a_a_plain_dict_pickle_passes_through_unstamped(books: Path) -> None:
    orig = {"b": 2, "a": 1}
    (books / "nb_data").mkdir()
    (books / "nb_data" / "book.pkl").write_bytes(pickle.dumps(orig))

    got = book_store.load_book_cached("nb_data", str(books))

    assert got == orig
    assert list(got) == ["b", "a"]  # type: ignore[call-overload]
    assert not hasattr(got, "book_fingerprint")
    assert book_store.load_book_cached("nb_data", str(books)) is got


def test_co_17_leg_b_an_ordered_dict_pickle_is_refused_by_the_allow_list(books: Path) -> None:
    (books / "od_data").mkdir()
    (books / "od_data" / "book.pkl").write_bytes(pickle.dumps(collections.OrderedDict([("b", 2), ("a", 1)])))
    size0 = book_store.load_book_cached.cache_info().currsize  # type: ignore[attr-defined]

    with pytest.raises(pickle.UnpicklingError, match="collections.OrderedDict"):
        book_store.load_book_cached("od_data", str(books))
    assert book_store.load_book_cached.cache_info().currsize == size0  # type: ignore[attr-defined]


def test_co_17_leg_c_a5_on_a_non_book_pickle_is_book_corrupt(books: Path) -> None:
    load_chapter, chapter_count = _api("load_chapter"), _api("chapter_count")
    iter_chapters = _api("iter_chapters")
    (books / "nb_data").mkdir()
    (books / "nb_data" / "book.pkl").write_bytes(pickle.dumps({"b": 2, "a": 1}))
    d = str(books)

    for call in (
        lambda: load_chapter("nb_data", d, 0),
        lambda: chapter_count("nb_data", d),
        lambda: next(iter(iter_chapters("nb_data", d))),
    ):
        with pytest.raises(book_format.BookCorrupt) as ei:
            call()
        assert "'nb_data'" in str(ei.value)


# --------------------------------------------------------------------------- CO-10 (docstring contract)


def test_co_10_docstrings_say_order_and_no_longer_say_by_position() -> None:
    names = ("load_chapter", "chapter_count", "iter_chapters", "find_chapter")
    docs = {name: _api(name).__doc__ or "" for name in names}
    docs["CurrentGeneration"] = book_store.CurrentGeneration.__doc__ or ""
    docs["rebind_annotations"] = notes_service.rebind_annotations.__doc__ or ""

    for name, doc in docs.items():
        assert "order" in doc, name
    for name in ("load_chapter", "chapter_count"):
        assert "gap is not a chapter" in docs[name], name
    assert "not an index bound" in docs["chapter_count"]
    for name in ("CurrentGeneration", "rebind_annotations"):
        assert "by position" not in docs[name], name
    assert "never orphaned" in docs["rebind_annotations"]


# --------------------------------------------------------------------------- CO-08 (rebind triad, R-3 follow-up 1)


def test_co_08_rebind_reads_by_order_and_gap_and_past_end_notes_keep_every_binding_field(books: Path) -> None:
    publish_gen(books, G, ["first ALPHA-ONLY here", "second BETA-ONLY here"], FP_A, "A", orders=[0, 2])
    seeded = [
        rec("r2", 2, "BETA-ONLY", book_id=G, resolution="unmatched", bound=None, evaluated=None),
        rec("g1", 1, "BETA-ONLY", "second ", " here", book_id=G, resolution="resolved", bound=FP_B,
            evaluated=FP_B, chapter_href="Text/gap.xhtml"),
        rec("p9", 9, "BETA-ONLY", book_id=G, resolution="resolved", bound=FP_B, evaluated=FP_B,
            chapter_href="Text/end.xhtml"),
        rec("x2", 2, "ALPHA-ONLY", book_id=G, resolution="unmatched", bound=None, evaluated=None),
    ]
    seed_notes(books / G, seeded, fp=ABSENT)
    seeded_by_id = {r["id"]: r for r in seeded}

    res = notes_service.rebind_annotations(str(books), G)

    after = {r["id"]: r for r in disk(books / G)[2]["annotations"]}
    assert res.fingerprint == FP_A
    assert after["r2"]["resolution"] == "resolved"
    assert after["r2"]["bound_fingerprint"] == after["r2"]["evaluated_fingerprint"] == FP_A
    for nid in ("g1", "p9", "x2"):
        assert after[nid]["resolution"] == "unmatched", nid
        assert after[nid]["evaluated_fingerprint"] == FP_A, nid
        assert after[nid]["orphaned"] is False, nid
        assert _same_raw(_binding_raw(after[nid]), _binding_raw(seeded_by_id[nid])), nid
    assert after["g1"]["bound_fingerprint"] == FP_B
    assert after["g1"]["chapter_href"] == "Text/gap.xhtml"
    assert res.counts == {"resolved": 1, "unmatched": 3}


# --------------------------------------------------------------------------- CO-18 (rebind oracle, property)

NoteDraw = Tuple[int, str, str, Optional[str], str]


@st.composite
def _rebind_world(draw: Any) -> Tuple[List[int], List[NoteDraw]]:
    orders = draw(st.lists(st.integers(0, 12), min_size=1, max_size=4, unique=True).map(sorted))
    k = draw(st.integers(1, 5))
    notes = [
        (
            draw(st.integers(0, max(orders) + 2)),
            draw(st.sampled_from([f"UNIQ{j}" for j in range(len(orders))])),
            draw(st.sampled_from([r for r in RESOLUTIONS if r != "accepted"])),
            draw(st.sampled_from([None, FP_B])),
            draw(st.sampled_from(["", "Text/h.xhtml"])),
        )
        for _ in range(k)
    ]
    return orders, notes


@settings(max_examples=15, deadline=None)
@given(world=_rebind_world())
@example(world=([0, 2], [(1, "UNIQ1", "unmatched", None, "")]))
@example(world=([0, 2], [(2, "UNIQ1", "unmatched", None, ""), (1, "UNIQ1", "unmatched", None, "")]))
def test_co_18_rebind_same_order_oracle_and_conservation(world: Tuple[List[int], List[NoteDraw]]) -> None:
    orders, notes = world
    texts = [f"c{i} UNIQ{i} body" for i in range(len(orders))]
    m = dict(zip(orders, texts))
    seeded = [
        rec(f"n{k}", ci, q, book_id=G, resolution=res, bound=bound, evaluated=None, chapter_href=href)
        for k, (ci, q, res, bound, href) in enumerate(notes)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        books_dir = Path(tmp)
        publish_gen(books_dir, G, texts, FP_A, "A", orders=orders)
        seed_notes(books_dir / G, seeded, fp=ABSENT)

        res = notes_service.rebind_annotations(str(books_dir), G)

        parsed = disk(books_dir / G)[2]
    after = {r["id"]: r for r in parsed["annotations"]}
    for s in seeded:
        a, ci = after[s["id"]], s["chapter_index"]
        expected = match_resolution(m[ci], "", s["quote"], "") if ci in m else "unmatched"
        assert a["resolution"] == expected, (orders, s)
        assert a["evaluated_fingerprint"] == FP_A
        assert a["orphaned"] is False
        if ci not in m:
            assert _same_raw(_binding_raw(a), _binding_raw(s)), (orders, s)
        else:
            assert a["bound_fingerprint"] == (FP_A if expected == "resolved" else s["bound_fingerprint"])
            strip = ("bound_fingerprint",)
            assert _same_raw(
                {k: v for k, v in _binding_raw(a).items() if k not in strip},
                {k: v for k, v in _binding_raw(s).items() if k not in strip},
            )
    assert res.advanced == all(r["resolution"] == "resolved" for r in after.values())
    assert (KEY in parsed) == res.advanced


# --------------------------------------------------------------------------- CO-15 (DP-4, round 2, DP-4b)


def _nonstrict_manifest_book(books_dir: Path, edit: Tuple[int, int]) -> None:
    publish_gen(books_dir, G, ["ALPHA-ONLY a", "b", "c FIVE"], FP_A, "A", orders=[0, 2, 5])
    _set_manifest_order(books_dir / G, *edit)
    book_format.validate_stat(books_dir / G)  # precondition: the hand edit still passes the stat-level check


def _assert_cannot_judge(books_dir: Path, before: Tuple[bytes, int]) -> None:
    res = notes_service.rebind_annotations(str(books_dir), G)
    assert res.fingerprint is None
    assert res.advanced is False
    assert disk(books_dir / G)[:2] == before
    assert res.version == version_on_disk(str(books_dir), G)


def _check_corrupt_no_path(exc: BaseException, books_dir: Path) -> None:
    assert repr(G) in str(exc), str(exc)
    assert str(books_dir) not in str(exc), str(exc)


def test_co_15_a_duplicate_order_manifest_is_refused_so_rebind_cannot_judge(books: Path) -> None:
    _nonstrict_manifest_book(books, (1, 0))  # [0, 0, 5]
    seed_notes(books / G, [rec("n", 0, "ALPHA-ONLY", book_id=G, resolution="unmatched", bound=None,
                                evaluated=None)], fp=ABSENT)
    before = disk(books / G)[:2]

    g = book_store.current_generation(G, str(books))
    assert g is not None
    assert hasattr(g, "has_chapter")
    with pytest.raises(book_format.BookCorrupt) as ei:
        g.has_chapter(0)
    _check_corrupt_no_path(ei.value, books)
    with pytest.raises(book_format.BookCorrupt) as ei:
        g.chapter_text(0)
    _check_corrupt_no_path(ei.value, books)
    _assert_cannot_judge(books, before)


@pytest.mark.parametrize("ci", [1, 5, 9])
@pytest.mark.parametrize(("shape", "edit"), [("dup", (1, 0)), ("desc", (1, 7))])
def test_co_15_round2_strictness_does_not_depend_on_the_queried_order(
    books: Path, shape: str, edit: Tuple[int, int], ci: int
) -> None:
    _nonstrict_manifest_book(books, edit)  # dup = [0, 0, 5]; desc = [0, 7, 5]
    seed_notes(books / G, [rec("n", ci, "FIVE", book_id=G, resolution="unmatched", bound=None,
                                evaluated=None)], fp=ABSENT)
    before = disk(books / G)[:2]

    g = book_store.current_generation(G, str(books))
    assert g is not None
    assert hasattr(g, "has_chapter")
    for n in (1, 5, 9):
        with pytest.raises(book_format.BookCorrupt):
            g.has_chapter(n)
    with pytest.raises(book_format.BookCorrupt):
        g.chapter_text(5)
    _assert_cannot_judge(books, before)


def test_co_15_dp4b_empty_notes_on_a_duplicate_order_manifest_do_not_advance(books: Path) -> None:
    _nonstrict_manifest_book(books, (1, 0))
    seed_notes(books / G, [], fp=ABSENT)
    before = disk(books / G)[:2]

    _assert_cannot_judge(books, before)


def test_co_15_dp4b_all_accepted_and_bound_notes_on_a_duplicate_order_manifest_do_not_advance(books: Path) -> None:
    _nonstrict_manifest_book(books, (1, 0))
    seed_notes(
        books / G,
        [
            rec("a1", 0, "ALPHA-ONLY", book_id=G, resolution="accepted", bound=FP_A, evaluated=FP_A),
            rec("a2", 5, "FIVE", book_id=G, resolution="accepted", bound=FP_A, evaluated=FP_A),
        ],
        fp=ABSENT,
    )
    before = disk(books / G)[:2]

    _assert_cannot_judge(books, before)


# --------------------------------------------------------------------------- CO-22 (FR-1 pin, characterization)


def test_co_22_a_negative_chapter_index_cannot_reach_rebind(books: Path) -> None:
    publish_gen(books, G, TEXTS2, FP_A, "A", orders=[0, 2])
    seed_notes(books / G, [rec("neg", -1, "t0", book_id=G)], fp=ABSENT)
    raw = (books / G / notes_service.NOTES_FILENAME).read_bytes()

    with pytest.raises(notes_service.NotesFileError):
        notes_service.rebind_annotations(str(books), G)
    assert (books / G / notes_service.NOTES_FILENAME).read_bytes() == raw
    assert os.path.exists(books / G / notes_service.NOTES_FILENAME)
