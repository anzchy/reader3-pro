"""`book_store.load_book` / `load_book_metadata` — the 012 granularity seam (011 §4, WI-4).

One law governs every case in this file:

    **projection consistency — a homomorphism, not a round trip.**
    For every book `b` in every `books_dir` `d`:

        load_book_metadata(b, d) == project(load_book(b, d), b)

    where `project` is exactly the expression the call sites already run
    (`search_service.py`'s `load_book_index`, `server.library_view`):
    `title = getattr(getattr(book, "metadata", None), "title", b)`,
    `authors = tuple(getattr(getattr(book, "metadata", None), "authors", []) or [])`,
    `book_id = b`.

It is *not* a round trip: nothing here claims the view can be turned back into a
`Book`. It claims that the small view and the big object agree on the fields
they share, over every book, for as long as the seam exists. That is the
contract `012-storage-format` inherits: when the body stops unpickling and
starts reading a `manifest.json`, W4-C1 is the test that says whether the new
storage still tells the truth — and it can say so without a single caller
changing.

Two corollaries ride along, and each has its own case because the law alone
does not imply them:

* **Same cache.** The metadata view goes through the one mtime-keyed cache, so a
  rewritten `book.pkl` invalidates it too and reading both views costs one
  unpickle. W4-C3's *control* leg is the half that catches a private
  `lru_cache` on the seam — the freshness leg alone would still pass.
* **No new swallow.** A metadata view *looks* like something that ought to
  degrade gracefully, which is exactly why W4-C4 exists. Degradation for the
  user lives in the server wrapper (D1-a); a second policy here would give 012
  two things to preserve instead of one.

`book_store` is imported through `seam()` inside each test body rather than at
module scope: before WI-4 lands, a top-level `from ... import load_book_metadata`
turns the whole file into a *collection error*, which reports as an error with
no test counts and is indistinguishable from a broken runner. Resolved in the
body, the pre-implementation red is a counted assertion failure naming the three
absent objects in a sentence.

Assertion rungs (L1-L4) and spec levels (S1-S6) follow
`.claude/tdd-guardian/tests-20260907T073506Z.md` §0.1-§0.2.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import itertools
import os
import pickle
import typing
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from synthetic_library import make_book, make_synthetic_library

#: Same alphabet as `test_book_store.py:47`: a book id that reaches the loader in
#: production is `listdir` output already filtered by `_validate_book_id_path_safe`.
SEGMENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=8)

#: An explicit constant, never the clock (§0.4 rule 1).
BASE_NS = 1_700_000_000_000_000_000

#: One fresh directory per hypothesis example, so two examples that happen to
#: generate the same `book_id` can never collide in the shared cache.
_EXAMPLE_COUNTER = itertools.count()

#: Phrases that would turn the docstring into a promise about *work done* rather
#: than about *values returned*. The seam's whole purpose is that 012 may change
#: how much of the file it touches; a docstring that pledges a small read would
#: make the storage swap a documented breaking change. Checked by W4-C6.
COST_PROMISES = (
    "byte",
    "cheap",
    "faster",
    "without reading",
    "does not read",
    "never reads",
    "only reads",
    "o(1)",
    "constant time",
    "lightweight",
)


def seam():
    """The module under test, with the three WI-4 names asserted present.

    `hasattr` plus an `assert` rather than a bare attribute access, so that the
    pre-implementation red is a *counted assertion* carrying a sentence rather
    than an `AttributeError` traceback the red-run classifiers read as a broken
    environment.
    """
    module = importlib.import_module("reader3_app.book_store")
    missing = [
        name
        for name in ("load_book", "load_book_metadata", "BookMetadataView")
        if not hasattr(module, name)
    ]
    assert not missing, (
        f"reader3_app.book_store is missing {missing}. WI-4 adds the 012 granularity "
        "seam: `load_book(book_id, books_dir)` (the full read) and "
        "`load_book_metadata(book_id, books_dir) -> BookMetadataView` (the projection), "
        "both through the one mtime-keyed cache."
    )
    return module


def project(book, book_id: str):
    """The call sites' own expression, copied verbatim from `search_service.py`.

    Kept as a function so that every case measures the view against *this*, not
    against a hand-written expectation that could drift from production.
    """
    title = getattr(getattr(book, "metadata", None), "title", book_id)
    authors = tuple(getattr(getattr(book, "metadata", None), "authors", []) or [])
    return book_id, title, authors


def one_book(books_dir: Path, *, count: int = 1):
    """A minimal synthetic library. Small chapters: this lane is budgeted in seconds."""
    return make_synthetic_library(books_dir, count=count, chapters=2, chapter_chars=200)


# ==========================================================================
# W4-C1 — the law itself
# ==========================================================================


@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=40,
    deadline=None,
)
@given(
    title=st.text(max_size=40),
    authors=st.lists(
        st.one_of(
            st.text(min_size=1, max_size=20),
            st.sampled_from(["Smith, Jr.", "de la Cruz"]),
        ),
        max_size=3,
    ),
    stem=SEGMENT,
)
def test_the_metadata_view_is_a_projection_of_the_full_book(
    books_dir: Path, count_unpickles, rewrite_book_pkl, title, authors, stem
):
    """L2 / S4 (W4-C1) - the view equals the projection of the full read, for every book.

    The law is universally quantified over books, so the case is too. A
    comma-carrying author is deliberately reachable: `", ".join(...)` is
    presentation and belongs at the call site, and a pre-joined string would be
    lossy for "Smith, Jr." — which is why `authors` stays a sequence.

    `count_unpickles == 1` across *both* calls is the same-cache corollary,
    asserted here rather than inferred from the miss column.
    """
    module = seam()
    example = next(_EXAMPLE_COUNTER)

    book_id = f"{stem}_data"
    root = books_dir / f"ex{example}"
    (root / book_id).mkdir(parents=True)
    book = make_book(0, chapters=1, chapter_chars=100)
    book.metadata.title = title
    book.metadata.authors = list(authors)
    rewrite_book_pkl(root / book_id, book, mtime_ns=BASE_NS + example * 1_000_000)

    module.load_book_cached.cache_clear()
    count_unpickles.reset()

    full = module.load_book(book_id, str(root))
    view = module.load_book_metadata(book_id, str(root))

    expected_id, expected_title, expected_authors = project(full, book_id)
    assert view.book_id == expected_id
    assert view.title == expected_title
    assert tuple(view.authors) == expected_authors
    assert tuple(view.authors) == tuple(book.metadata.authors)
    assert view.title == book.metadata.title
    # The call-site expression, unchanged. This is what `library_view` renders.
    assert ", ".join(view.authors) == ", ".join(book.metadata.authors)

    assert set(dataclasses.asdict(view)) == {"book_id", "title", "authors"}, (
        "the view carries exactly the three projected fields; a fourth would be a "
        "field 012's manifest.json has to reproduce for no caller's benefit"
    )
    assert count_unpickles.count == 1, (
        f"reading the full book and its metadata view cost {count_unpickles.count} "
        "unpickles; the same-cache corollary says one"
    )


# ==========================================================================
# W4-C2 — degradation, exactly as the call sites already degrade
# ==========================================================================


@pytest.mark.parametrize("shape", ["metadata_none", "authors_empty", "title_empty"])
def test_a_book_with_no_metadata_degrades_the_way_the_call_sites_already_do(
    books_dir: Path, merged_loader_cache, rewrite_book_pkl, shape
):
    """L2 / S3 (W4-C2) - exhaustive over the shapes the `getattr` chain can meet.

    The third leg is the load-bearing one: an empty title stays empty. `getattr`
    finds the attribute, so `""` is a real empty title and not the absent-metadata
    fallback. Pinning it stops a well-meaning `or book_id` from sneaking in and
    silently renaming every untitled book after its directory.
    """
    module = seam()
    book_id = "shape_data"
    (books_dir / book_id).mkdir(parents=True)

    book = make_book(0, chapters=1, chapter_chars=100)
    if shape == "metadata_none":
        book.metadata = None
    elif shape == "authors_empty":
        book.metadata.title = "Has A Title"
        book.metadata.authors = []
    else:
        book.metadata.title = ""
        book.metadata.authors = ["Solo Author"]
    rewrite_book_pkl(books_dir / book_id, book, mtime_ns=BASE_NS + 7_000_000)

    view = module.load_book_metadata(book_id, str(books_dir))

    if shape == "metadata_none":
        assert view.title == book_id, "absent metadata falls back to the book id"
        assert tuple(view.authors) == ()
    elif shape == "authors_empty":
        assert view.title == "Has A Title"
        assert tuple(view.authors) == ()
        assert ", ".join(view.authors) == ""
    else:
        assert view.title == "", (
            "an empty title is a real empty title, not the book_id fallback: "
            "`getattr` found the attribute, so no `or book_id` may intervene"
        )
        assert tuple(view.authors) == ("Solo Author",)


# ==========================================================================
# W4-C3 — one cache, one stat key, for both views
# ==========================================================================


def test_the_metadata_view_is_invalidated_by_the_same_stat_key(
    books_dir: Path, merged_loader_cache, count_unpickles, rewrite_book_pkl
):
    """L3 / S2 (W4-C3) - the freshness leg *and* its negative control.

    The control leg is what catches a `load_book_metadata` that grew its own
    `lru_cache`: freshness would still pass (the private cache would be cold on
    the first call after the rewrite), but the shared cache's `hits` column
    would not move, because the private memo would answer before the shared
    cache ever saw the call.
    """
    module = seam()
    dirs = one_book(books_dir)
    book_id = "synth00_data"

    original = make_book(0, chapters=1, chapter_chars=100)
    original.metadata.title = "Original"
    rewrite_book_pkl(dirs[0], original, mtime_ns=BASE_NS + 1_000_000)
    module.load_book_cached.cache_clear()
    count_unpickles.reset()

    first = module.load_book_metadata(book_id, str(books_dir))
    assert first.title == "Original"
    assert count_unpickles.count == 1

    # --- freshness leg -----------------------------------------------------
    retitled = make_book(0, chapters=1, chapter_chars=100)
    retitled.metadata.title = "Retitled"
    rewrite_book_pkl(dirs[0], retitled, mtime_ns=BASE_NS + 2_000_000)

    second = module.load_book_metadata(book_id, str(books_dir))
    assert second.title == "Retitled", (
        "the metadata view must be invalidated by the same (mtime_ns, size) key the "
        "full read uses; a view that survives a republish is 012's bug to inherit"
    )
    assert count_unpickles.count == 2, "exactly one extra unpickle for the rewrite leg"

    # --- negative control: no mutation, no new read ------------------------
    hits_before = module.load_book_cached.cache_info().hits
    third = module.load_book_metadata(book_id, str(books_dir))

    assert third == second, "an unchanged file must produce an equal view"
    assert count_unpickles.count == 2, (
        f"the unchanged second read cost {count_unpickles.count - 2} extra unpickles; "
        "it must cost zero"
    )
    assert module.load_book_cached.cache_info().hits == hits_before + 1, (
        "the second call did not reach the shared cache. A private lru_cache on "
        "load_book_metadata would look exactly like this: zero extra unpickles, but "
        "the shared cache's hit column never moves"
    )


# ==========================================================================
# W4-C4 — the seam adds no new swallow
# ==========================================================================


@pytest.mark.parametrize("damage", ["garbage", "truncated", "missing_pkl", "missing_dir"])
def test_the_seam_adds_no_new_swallow(
    books_dir: Path, merged_loader_cache, damage
):
    """L4 / S3 (W4-C4) - same damage enumeration as W1-C6, same exceptions out.

    The tempting wrong implementation is a `try/except -> BookMetadataView(book_id,
    book_id, ())` "graceful" seam, because a metadata view *looks* like something
    that should degrade. It must not: `library_view`'s degradation lives in the
    server wrapper (D1-a), and duplicating it here hands 012 two policies to
    preserve instead of one.

    The exception *types* are compared against each other, not asserted
    independently, so "the same as `load_book`" is what is checked rather than
    "each happens to match a name I typed twice".
    """
    import bookdir

    module = seam()
    dirs = one_book(books_dir)

    if damage == "garbage":
        bookdir.break_book_pkl(dirs[0])
        book_id, expected = "synth00_data", pickle.UnpicklingError
    elif damage == "truncated":
        bookdir.truncate_book_pkl(dirs[0], keep=32)
        book_id, expected = "synth00_data", pickle.UnpicklingError
    elif damage == "missing_pkl":
        (Path(dirs[0]) / "book.pkl").unlink()
        book_id, expected = "synth00_data", FileNotFoundError
    else:
        book_id, expected = "no_such_book_data", FileNotFoundError

    def capture(fn, label):
        try:
            result = fn(book_id, str(books_dir))
        except Exception as exc:
            return exc
        pytest.fail(
            f"{label} returned {result!r} instead of raising on {damage!r}. The seam "
            "must not swallow: deciding what the user sees belongs to the web layer "
            "(D1-a), which has a status code to spend"
        )

    full_exc = capture(module.load_book, "load_book")
    view_exc = capture(module.load_book_metadata, "load_book_metadata")

    assert type(view_exc) is type(full_exc), (
        f"load_book raised {type(full_exc).__name__} but load_book_metadata raised "
        f"{type(view_exc).__name__} on {damage!r}: the seam changed the error contract"
    )
    assert type(full_exc) is expected


# ==========================================================================
# W4-C5 — load_book is the cached loader, not a second read path
# ==========================================================================


def test_load_book_is_the_cached_loader(
    books_dir: Path, merged_loader_cache, count_unpickles
):
    """L1+L2 / S1 (W4-C5) - identity is nice, the shared-cache leg is mandatory.

    An alias satisfies both legs. A `load_book` that opened the file itself would
    satisfy neither, and the behavioural leg is the one that says so even if the
    alias is later replaced by a thin wrapper.
    """
    module = seam()
    one_book(books_dir)
    book_id = "synth00_data"
    module.load_book_cached.cache_clear()
    count_unpickles.reset()

    a = module.load_book(book_id, str(books_dir))
    b = module.load_book_cached(book_id, str(books_dir))

    assert a is b, "load_book must return the cached loader's object, not a fresh read"
    assert count_unpickles.count == 1, (
        f"load_book + load_book_cached cost {count_unpickles.count} unpickles; "
        "load_book acquiring its own read path is exactly what this forbids"
    )


# ==========================================================================
# W4-C6 — a dataclass, explicitly annotated, documenting its successor
# ==========================================================================


def test_the_metadata_view_is_a_dataclass_with_explicit_annotations(books_dir: Path):
    """L1 / S1 (W4-C6) - a structural fact, and openly so.

    Constitution: Data Structures First / Explicit Over Implicit. `isinstance` of
    `dict`/`tuple` is checked as well as `is_dataclass`, because a `NamedTuple`
    is a dataclass-shaped thing that would slip past the looser check and hand
    012 a positional contract nobody meant to promise.
    """
    module = seam()
    one_book(books_dir)
    view = module.load_book_metadata("synth00_data", str(books_dir))

    assert dataclasses.is_dataclass(view)
    assert not isinstance(view, (dict, tuple)), (
        "the view must be a dataclass, not a dict or a NamedTuple: a positional or "
        "key-addressed shape is a contract 012 would have to reproduce exactly"
    )
    assert [f.name for f in dataclasses.fields(view)] == ["book_id", "title", "authors"]

    for name in ("load_book", "load_book_metadata"):
        fn = getattr(module, name)
        hints = typing.get_type_hints(fn)
        assert "return" in hints, f"{name} has no return annotation"
        code = fn.__code__
        params = code.co_varnames[: code.co_argcount]
        missing = [p for p in params if p not in hints]
        assert not missing, f"{name} has unannotated parameters: {missing}"

    doc = module.load_book_metadata.__doc__ or ""
    assert "012" in doc and "manifest" in doc, (
        "load_book_metadata's docstring must name its successor: 012 replaces the "
        "body with a manifest.json read. Without that line 012 lands on an "
        "undocumented seam and has to rediscover why it exists"
    )
    assert "full read" in doc.lower(), (
        "the docstring must say it is a full read *today*, so nobody reads the small "
        "return type as a small read"
    )
    lowered = doc.lower()
    promised = [phrase for phrase in COST_PROMISES if phrase in lowered]
    assert not promised, (
        f"load_book_metadata's docstring promises something about the work it does: "
        f"{promised}. The contract is about values, not cost — that freedom is the "
        "entire point of the seam"
    )


# ==========================================================================
# W4-C7 — the seam's callers are an explicit allowlist (018 WI-4, Q-A)
# ==========================================================================


def mentions_of(source: str, target: str) -> int:
    """Every AST node that spells ``target`` as a name, attribute or definition.

    AST and not grep for the reason `test_direct_urlopen_call_sites.py` gives:
    the module docstring of `book_store.py` will discuss `load_book_metadata` in
    prose, and prose is not a node. A regex lock would count it and then need an
    exception for the one file that is allowed to mention it anyway.
    """
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == target:
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == target:
            count += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target:
            count += 1
        elif isinstance(node, ast.alias) and target in (node.name, node.asname):
            count += 1
    return count


def _defines_function(source: str, name: str) -> bool:
    """这个模块的**顶层**是否定义了叫 `name` 的（异步）函数。

    只看顶层：嵌套定义不是「定义点」，一个闭包里同名的局部函数不该把闸引过去。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


#: Every module allowed to mention ``load_book_metadata``: its definition site,
#: and ``GET /api/library`` — the first sanctioned caller (018 second slice §6
#: Q-A). A third caller is a decision, not a drive-by: it edits this set with a
#: stated reason.
SEAM_CALLER_ALLOWLIST = frozenset(
    {
        "src/reader3_app/book_store.py",
        "src/reader3_app/web/routers/library_books.py",
    }
)

LIBRARY_BOOKS_ROUTER = "src/reader3_app/web/routers/library_books.py"


def test_seam_callers_are_the_allowlist(repo_root: Path):
    """L1 / S3 (W4-C7, 018 WI-4 T4-U8) - exhaustive AST walk over every module under src/reader3_app/.

    Renamed from ``test_no_production_call_site_uses_the_new_seam_yet``. Stated
    spec change: Q-A makes the ``GET /api/library`` router the first sanctioned
    caller of the seam, so "only the definition site mentions it" no longer
    holds. What replaced it: the mentioning set is a subset of
    ``SEAM_CALLER_ALLOWLIST`` **and** the router is actually in it — a router
    that reads ``book.pkl`` / ``load_book_cached`` directly, bypassing the seam,
    is not a mentioner and turns this red.

    C5 — migrating `library_view` onto the metadata view — is still deferred to
    012 by §7; the (b) half below is unchanged.
    """
    src = repo_root / "src" / "reader3_app"
    mentioning = {}
    library_view_still_calls_the_full_loader = False
    library_view_defined_in = None

    for path in sorted(src.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        count = mentions_of(source, "load_book_metadata")
        if count:
            mentioning[str(path.relative_to(repo_root))] = count
        # 2026-09-19（011 WI-4）：原本这里写死 `path.name == "server.py"`。
        # `library_view` 搬到 `web/routers/library.py` 之后那个条件永远不成立，
        # 于是这条闸会以「C5 被提前做了」的名义报红——而 C5 根本没动。
        # 改成按**定义点**找：谁定义了 library_view 就看谁，搬家不影响判据。
        # 调用写法从 `load_book_cached(item)` 变成 `_server.load_book_cached(item)`，
        # 子串仍然命中，这正是 `_server.` 形状想要的效果。
        if _defines_function(source, "library_view"):
            assert library_view_defined_in is None, (
                f"library_view 有两个定义点：{library_view_defined_in} 与 "
                f"{path.relative_to(repo_root)}。这条闸只认一个。"
            )
            library_view_defined_in = path.relative_to(repo_root)
            library_view_still_calls_the_full_loader = "load_book_cached(item)" in source

    assert library_view_defined_in is not None, (
        "全 src/ 里没有任何模块定义 library_view。它被改名或删掉了，"
        "这条闸就量不到东西了——量不到判红，不判跳过。"
    )

    assert set(mentioning) <= SEAM_CALLER_ALLOWLIST, (
        f"load_book_metadata is mentioned outside the allowlist: "
        f"{sorted(set(mentioning) - SEAM_CALLER_ALLOWLIST)} (all mentions: {mentioning}). "
        "C5 belongs to 012; if you are doing it now, update this test and the plan."
    )
    assert LIBRARY_BOOKS_ROUTER in mentioning, (
        f"{LIBRARY_BOOKS_ROUTER} does not call load_book_metadata "
        f"(exists: {(repo_root / LIBRARY_BOOKS_ROUTER).is_file()}; mentions: {mentioning}). "
        "GET /api/library must read titles through the 012 seam, not book.pkl / "
        "load_book_cached directly (018 WI-4, Q-A)."
    )
    assert library_view_still_calls_the_full_loader, (
        f"{library_view_defined_in} 里的 library_view 不再调用 load_book_cached(item)。"
        "C5 belongs to 012; if you are doing it now, update this test and the plan."
    )


#: Names that belong to the pickle layer. The router answers "what is this book
#: called" through the seam; reaching any of these means it would keep working
#: unchanged after 012 swaps the storage format, i.e. it bypassed the seam.
PICKLE_LAYER_NAMES = frozenset(
    {
        "load_book_cached",
        "load_book_file",
        "load_book",
        "_load_book_for_stat",
        "pickle",
        "Reader3Unpickler",
    }
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the Constant nodes that are module/class/function docstrings.

    Prose is not a node that reads anything: a docstring saying "never opens
    book.pkl" is documentation, not a read path.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def test_library_books_router_never_touches_pickle_layer(repo_root: Path):
    """L1 / S2 (018 WI-4 T4-U9) - AST scan of the GET /api/library router.

    The allowlist guard above proves the router *does* call the seam; this one
    proves it calls *nothing else* underneath it — no ``_server.load_book_cached``
    fallback, no ``book_store.load_book(...)`` for the title, no hand-built
    ``book.pkl`` path.
    """
    path = repo_root / LIBRARY_BOOKS_ROUTER
    assert path.is_file(), (
        f"{LIBRARY_BOOKS_ROUTER} does not exist. 018 WI-4 adds GET /api/library there."
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)

    touched: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in PICKLE_LAYER_NAMES:
            touched.append(f"name {node.id} (line {node.lineno})")
        elif isinstance(node, ast.Attribute) and node.attr in PICKLE_LAYER_NAMES:
            touched.append(f"attribute .{node.attr} (line {node.lineno})")
        elif isinstance(node, ast.alias) and (
            node.name.split(".")[-1] in PICKLE_LAYER_NAMES
            or node.name.split(".")[0] in PICKLE_LAYER_NAMES
            or (node.asname or "") in PICKLE_LAYER_NAMES
        ):
            touched.append(f"import {node.name}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "book.pkl" in node.value
            and id(node) not in docstrings
        ):
            touched.append(f"string constant {node.value!r} (line {node.lineno})")

    assert not touched, (
        f"{LIBRARY_BOOKS_ROUTER} reaches the pickle layer directly: {touched}. "
        "It must go through book_store.load_book_metadata only."
    )
