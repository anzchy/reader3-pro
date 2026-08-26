"""WI-26: ``book.pkl`` must not be an unrestricted deserialization surface.

Three copies of a "restricted unpickler, falling back to ``pickle.load``"
existed (``search_service``, ``vector_search``, ``web/server``). The fallback
line made the restriction decorative: a crafted ``book.pkl`` whose
``__reduce__`` names anything at all fails the restricted pass and is then
handed straight to the default loader, which calls it.

**Scope**: this file does not test the pickle *format* — replacing pickle is
``012-storage-format``. It tests that the restricted unpickler is the only
loader, and that its allow-list is an allow-list.

**Payload safety rule (hard)**: the malicious pickle in this module may only
append a string to :data:`SIDE_EFFECTS`, a list defined right here. It does not
touch the filesystem, spawn a process, open a socket, import a non-stdlib
module, or call ``os.system`` / ``eval`` with any real effect. The ``os.system``
and ``builtins.eval`` cases in P2 are hand-built streams that *name* the
callable and then STOP — the callable is never on the stack as a call, so even
a completely permissive ``find_class`` would not invoke it.

Assertion levels (see `.claude/tdd-guardian/plan-20260824T074825Z.md`):
    L1 wiring — P4 only
    L3 whole observable end state (side effects + returned object)
"""

from __future__ import annotations

import ast
import contextlib
import pickle
from pathlib import Path
from typing import Any, Callable, List, Tuple

import pytest

from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry, process_epub

# --------------------------------------------------------------------------
# The payload. Read the module docstring before changing anything below.
# --------------------------------------------------------------------------

SIDE_EFFECTS: List[str] = []


def _record_side_effect(tag: str) -> str:
    """The *only* thing a malicious pickle in this file is allowed to reach.

    Appending to a list is observable, reversible, and harmless. It stands in
    for the arbitrary call an attacker actually gets; if this runs, so would
    ``subprocess.run``.
    """
    SIDE_EFFECTS.append(tag)
    return tag


class _EvilBook:
    """Pickles into a stream that calls :func:`_record_side_effect` on load."""

    def __reduce__(self):
        return (_record_side_effect, ("PWNED",))


def _evil_pickle_bytes() -> bytes:
    return pickle.dumps(_EvilBook(), protocol=4)


def _global_ref_pickle(module: str, name: str) -> bytes:
    """A protocol-0 stream that *names* ``module.name`` and stops.

    GLOBAL pushes the object; STOP returns it. Nothing is ever called, so this
    is safe to point at ``os.system``. ``find_class`` is still invoked with
    exactly ``(module, name)``, which is the thing under test.
    """
    return b"c" + module.encode("utf-8") + b"\n" + name.encode("utf-8") + b"\n" + b"."


@pytest.fixture(autouse=True)
def _clean_sentinel():
    SIDE_EFFECTS.clear()
    yield
    SIDE_EFFECTS.clear()


# --------------------------------------------------------------------------
# The two production load paths, parameterized.
# --------------------------------------------------------------------------


def _load_via_search_service(books_dir: Path, book_id: str) -> Any:
    from reader3_app import search_service

    search_service.load_book_cached.cache_clear()
    try:
        return search_service.load_book_cached(book_id, str(books_dir))
    finally:
        search_service.load_book_cached.cache_clear()


def _load_via_vector_search(books_dir: Path, book_id: str) -> Any:
    from reader3_app.vector_search import BookVectorIndex

    return BookVectorIndex(book_id, books_dir=str(books_dir))._load_book()


LOADERS: List[Tuple[str, Callable[[Path, str], Any]]] = [
    ("search_service", _load_via_search_service),
    ("vector_search", _load_via_vector_search),
]
LOADER_PARAMS = pytest.mark.parametrize(
    "load_book", [pytest.param(fn, id=name) for name, fn in LOADERS]
)


def _plant(books_dir: Path, book_id: str, payload: bytes) -> None:
    d = books_dir / book_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "book.pkl").write_bytes(payload)


# --------------------------------------------------------------------------
# P0 — the payload is genuinely dangerous
# --------------------------------------------------------------------------


def test_payload_would_execute_under_the_default_loader():
    """L3 / S2 — without this, P1 could pass because the payload is inert.

    This is the one place the side effect is allowed to happen: it proves the
    stream really does carry a call, so P1's ``SIDE_EFFECTS == []`` is a claim
    about the loader rather than about a harmless byte string.
    """
    payload = _evil_pickle_bytes()
    assert SIDE_EFFECTS == []

    pickle.loads(payload)

    assert SIDE_EFFECTS == ["PWNED"], (
        "the payload no longer carries a call; every assertion below is vacuous"
    )


# --------------------------------------------------------------------------
# P1 — the side effect does not happen (load-bearing)
# --------------------------------------------------------------------------


@LOADER_PARAMS
def test_malicious_book_pkl_has_no_side_effect(
    load_book, books_dir: Path, monkeypatch, tmp_path: Path
):
    """L3 / S2 — the core assertion: the crafted call never ran.

    Deliberately not ``pytest.raises``. What is being asserted is that nothing
    executed, and a "execute first, raise afterwards" implementation passes a
    raises-check while failing the user. The load is wrapped in ``suppress``
    precisely so the exception cannot mask the sentinel assertion.
    """
    monkeypatch.chdir(tmp_path)
    _plant(books_dir, "evil_data", _evil_pickle_bytes())

    with contextlib.suppress(Exception):
        load_book(books_dir, "evil_data")

    assert SIDE_EFFECTS == [], (
        "a crafted book.pkl executed its payload during load: "
        f"{SIDE_EFFECTS!r}"
    )


# --------------------------------------------------------------------------
# P2 — anything off the allow-list is refused
# --------------------------------------------------------------------------


OFF_LIST = [
    ("os", "system"),
    ("builtins", "eval"),
    ("reader3_app.web.server", "app"),
]


@pytest.mark.parametrize("module,name", [pytest.param(m, n, id=f"{m}.{n}") for m, n in OFF_LIST])
@LOADER_PARAMS
def test_class_outside_the_allow_list_is_rejected(
    load_book, module: str, name: str, books_dir: Path, monkeypatch, tmp_path: Path
):
    """L3 / S2 — ``find_class`` is an allow-list, not a remap plus a shrug."""
    monkeypatch.chdir(tmp_path)
    book_id = "offlist_data"
    _plant(books_dir, book_id, _global_ref_pickle(module, name))

    with pytest.raises(pickle.UnpicklingError):
        load_book(books_dir, book_id)

    assert SIDE_EFFECTS == []


@pytest.mark.parametrize("module,name", [pytest.param(m, n, id=f"{m}.{n}") for m, n in OFF_LIST])
def test_unpickler_itself_rejects_off_list_globals(module: str, name: str):
    """L3 / S2 — the same refusal at the unpickler, independent of any caller."""
    from reader3_app import safe_pickle

    import io

    with pytest.raises(pickle.UnpicklingError):
        safe_pickle.Reader3Unpickler(io.BytesIO(_global_ref_pickle(module, name))).load()

    assert SIDE_EFFECTS == []


# --------------------------------------------------------------------------
# P3 — the four legitimate classes still load (regression protection)
# --------------------------------------------------------------------------


def _sample_book() -> Book:
    return Book(
        metadata=BookMetadata(title="Sample", language="en", authors=["A. Author"]),
        spine=[
            ChapterContent(
                id="c1", href="c1.html", title="One", content="<p>one</p>", text="one", order=0
            )
        ],
        toc=[TOCEntry(title="One", href="c1.html", file_href="c1.html", anchor="")],
        images={},
        source_file="sample.epub",
        processed_at="2026-08-25T00:00:00",
    )


@LOADER_PARAMS
def test_real_generated_book_pkl_still_loads(
    load_book, books_dir: Path, epub_v1: Path, monkeypatch, tmp_path: Path
):
    """L3 / S2 — without this, an empty allow-list would also be green."""
    monkeypatch.chdir(tmp_path)
    expected = process_epub(str(epub_v1), str(books_dir / "real_data"))

    loaded = load_book(books_dir, "real_data")

    assert loaded is not None
    assert len(loaded.spine) == len(expected.spine) == 3
    assert loaded.spine[0].title == expected.spine[0].title
    assert loaded.spine[0].text == expected.spine[0].text
    assert loaded.metadata.title == expected.metadata.title
    assert [t.title for t in loaded.toc] == [t.title for t in expected.toc]


@pytest.mark.parametrize("legacy_module", ["__main__", "reader3"])
@LOADER_PARAMS
def test_legacy_module_paths_still_load(
    load_book, legacy_module: str, books_dir: Path, monkeypatch, tmp_path: Path
):
    """L3 / S2 — the existing ``_REMAP`` behaviour survives the tightening.

    Protocol 2 writes GLOBAL as newline-delimited text, so the module path can
    be rewritten in the byte stream to reproduce a pickle made by running
    ``reader3.py`` as a script.
    """
    monkeypatch.chdir(tmp_path)
    raw = pickle.dumps(_sample_book(), protocol=2)
    legacy = raw.replace(b"creader3_app.reader3\n", b"c" + legacy_module.encode() + b"\n")
    assert legacy != raw, "the rewrite did not fire; the fixture proves nothing"
    _plant(books_dir, "legacy_data", legacy)

    loaded = load_book(books_dir, "legacy_data")

    assert len(loaded.spine) == 1
    assert loaded.spine[0].title == "One"
    assert loaded.spine[0].text == "one"
    assert loaded.metadata.title == "Sample"
    assert loaded.toc[0].file_href == "c1.html"


def test_all_four_dataclasses_are_on_the_allow_list():
    """L3 / S2 — names the four explicitly, so dropping one cannot pass."""
    import io

    from reader3_app import safe_pickle

    for name in ("Book", "BookMetadata", "ChapterContent", "TOCEntry"):
        stream = io.BytesIO(_global_ref_pickle("reader3_app.reader3", name))
        assert safe_pickle.Reader3Unpickler(stream).load().__name__ == name


# --------------------------------------------------------------------------
# P4 — one unpickler, three call sites
# --------------------------------------------------------------------------


CALL_SITES = [
    "src/reader3_app/search_service.py",
    "src/reader3_app/vector_search.py",
    "src/reader3_app/web/server.py",
]


@pytest.mark.parametrize("rel", CALL_SITES)
def test_call_sites_import_safe_pickle_and_define_no_unpickler(rel: str, repo_root: Path):
    """L1 / S1 — wiring. Three copies of a security check is three chances to fix two."""
    tree = ast.parse((repo_root / rel).read_text(encoding="utf-8"))

    imports_safe_pickle = any(
        (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[-1] == "safe_pickle")
        or (
            isinstance(n, ast.Import)
            and any(a.name.split(".")[-1] == "safe_pickle" for a in n.names)
        )
        for n in ast.walk(tree)
    )
    assert imports_safe_pickle, f"{rel} does not import safe_pickle"

    local_unpicklers = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
        and any(
            isinstance(b, ast.Attribute) and b.attr == "Unpickler" for b in n.bases
        )
    ]
    assert local_unpicklers == [], f"{rel} still defines its own unpickler: {local_unpicklers}"
