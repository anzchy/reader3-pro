"""012 WI-4b.1 (b): the ADR-0016 L86 flat-path ratchet (matrix ``.claude/tdd-guardian/tests-20261009-wi4b1.md``,
cases B1-30..B1-39, rev 2 + R-RATCHET + OA-1/2/5 + adversary round 2 ruling).

What it counts. ``scan`` parses every ``*.py`` under ``src/reader3_app`` -- except exactly the root
``book_store.py`` and ``book_format.py`` (OA-2) -- and counts, per ``(relpath, qualname, literal)``:

- every ``str`` constant (including the constant parts of an f-string and constants nested in its
  expressions) in which ``book.pkl``, ``book.epub`` or ``images`` is a whole path segment, splitting on ``/`` and
  ``os.sep`` and dropping empty segments -- one hit per matching segment;
- ``_book_pkl_path`` as a Name, an Attribute, an import alias, or a Name bound by
  ``from ...book_store import _book_pkl_path as x``;
- ``book_format.PKL`` / ``EPUB`` / ``IMAGES`` as an Attribute on a Name bound to the ``reader3_app.book_format``
  module, as an import alias from that module, or as a Name that alias binds.

Docstrings (the first statement of a module, class or function, when it is an ``Expr`` wrapping a ``str``
constant) are skipped (OA-5); comments never reach the AST. Qualnames follow CPython's ``__qualname__``
(``<module>``, ``C.m``, ``f.<locals>.g``; lambdas and comprehensions are not scopes), except that decorator
expressions belong to the pseudo-scope ``{qualname}.<decorator>`` (adversary round 2, gap 3a).

This ratchet is a tripwire, not a proof. Out of scope, by ruling (R-RATCHET, adversary round 2):
string concatenation (``"book." + "pkl"``), string-keyed ``getattr(book_format, "PKL")``, rebinding through an
intermediate variable (``p = book_format.PKL`` is a hit, later uses of ``p`` are not), a bare-import dotted
receiver (``import reader3_app.book_format`` then ``reader3_app.book_format.PKL``), and a segment carrying
trailing punctuation (``book.pkl)``).

Each later sub-item (4b.2-4b.5, WI-3.1) deletes its own ``ALLOWLIST_ENTRIES`` and ``REQUIRED_ROWS`` in the same
commit; the ratchet only tightens.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

Key = Tuple[str, str, str]

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ROOT = REPO_ROOT / "src" / "reader3_app"

LITERALS: Tuple[str, ...] = ("book.pkl", "book.epub", "images")
PKL_PATH = "_book_pkl_path"
FORMAT_CONSTS: FrozenSet[str] = frozenset({"PKL", "EPUB", "IMAGES"})
EXCLUDED: FrozenSet[str] = frozenset({"book_store.py", "book_format.py"})
_SEPS: FrozenSet[str] = frozenset({"/", os.sep})
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

OWNERS: FrozenSet[str] = frozenset({"4b.2", "4b.3", "4b.4", "4b.5", "WI-3.1", "permanent", "url"})

# --------------------------------------------------------------------------- scan / diff


def _segments(value: str) -> List[str]:
    parts = [value]
    for sep in _SEPS:
        parts = [piece for chunk in parts for piece in chunk.split(sep)]
    return [p for p in parts if p]


def _package_of(rel_to_pkg_parent: PurePosixPath) -> List[str]:
    return list(rel_to_pkg_parent.parts[:-1])


def _resolve_from(node: ast.ImportFrom, package: List[str]) -> str:
    if node.level == 0:
        return node.module or ""
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else list(package)
    return ".".join(base + ([node.module] if node.module else []))


class _Bindings:
    """Module-wide import bindings (not scope-aware: "bound in the same module", §0)."""

    def __init__(self, tree: ast.Module, package: List[str]) -> None:
        self.format_module: Set[str] = set()
        self.format_consts: Dict[str, str] = {}
        self.pkl_names: Set[str] = set()
        self.format_aliases: Set[int] = set()  # id() of alias nodes that import PKL/EPUB/IMAGES
        fmt = f"{package[0]}.book_format" if package else "reader3_app.book_format"
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = _resolve_from(node, package)
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if f"{mod}.{alias.name}" == fmt:
                        self.format_module.add(bound)
                    elif mod == fmt and alias.name in FORMAT_CONSTS:
                        self.format_consts[bound] = f"book_format.{alias.name}"
                        self.format_aliases.add(id(alias))
                    elif mod.split(".")[-1] == "book_store" and alias.name == PKL_PATH:
                        self.pkl_names.add(bound)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == fmt and alias.asname:
                        self.format_module.add(alias.asname)


class _Visitor:
    def __init__(self, rel: str, bindings: _Bindings) -> None:
        self.rel = rel
        self.b = bindings
        self.hits: Counter = Counter()
        self.trace: List[Tuple[Key, ast.AST]] = []  # (key, producing node), one per hit
        self._node: Optional[ast.AST] = None

    def _add(self, qual: str, literal: str) -> None:
        self.hits[(self.rel, qual, literal)] += 1
        assert self._node is not None
        self.trace.append(((self.rel, qual, literal), self._node))

    def _hit(self, node: ast.AST, qual: str) -> None:
        self._node = node
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for seg in _segments(node.value):
                if seg in LITERALS:
                    self._add(qual, seg)
        elif isinstance(node, ast.Name):
            if node.id == PKL_PATH or node.id in self.b.pkl_names:
                self._add(qual, PKL_PATH)
            elif node.id in self.b.format_consts:
                self._add(qual, self.b.format_consts[node.id])
        elif isinstance(node, ast.Attribute):
            if node.attr == PKL_PATH:
                self._add(qual, PKL_PATH)
            elif (
                node.attr in FORMAT_CONSTS
                and isinstance(node.value, ast.Name)
                and node.value.id in self.b.format_module
            ):
                self._add(qual, f"book_format.{node.attr}")
        elif isinstance(node, ast.alias):
            if node.name == PKL_PATH:
                self._add(qual, PKL_PATH)
            elif id(node) in self.b.format_aliases:
                self._add(qual, f"book_format.{node.name}")

    def body(self, stmts: List[ast.stmt], qual: str, kind: str) -> None:
        first = stmts[0] if stmts else None
        for stmt in stmts:
            if (
                stmt is first
                and isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                continue  # docstring (OA-5)
            self.walk(stmt, qual, kind)

    def walk(self, node: ast.AST, qual: str, kind: str) -> None:
        if isinstance(node, _DEFS):
            if kind == "module":
                own = node.name
            elif kind == "class":
                own = f"{qual}.{node.name}"
            else:
                own = f"{qual}.<locals>.{node.name}"
            for dec in node.decorator_list:
                self.walk(dec, f"{own}.<decorator>", "function")
            if isinstance(node, ast.ClassDef):
                for expr in [*node.bases, *node.keywords]:
                    self.walk(expr, own, "class")
                self.body(node.body, own, "class")
            else:
                self.walk(node.args, own, "function")
                if node.returns is not None:
                    self.walk(node.returns, own, "function")
                self.body(node.body, own, "function")
            return
        self._hit(node, qual)
        for child in ast.iter_child_nodes(node):
            self.walk(child, qual, kind)


def _in_scope(root: Path) -> List[Path]:
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if "__pycache__" in rel.parts or rel.as_posix() in EXCLUDED or not path.is_file():
            continue
        out.append(path)
    return out


def scan(root: Path) -> Counter:
    """``Counter[(relpath, qualname, literal)]`` over ``root`` (an ``.../src/reader3_app`` tree).

    Relpaths are POSIX, relative to ``root.parents[1]`` (the repo root for the real tree).
    """
    root = Path(root)
    found: Counter = Counter()
    for path in _in_scope(root):
        found.update(_visit_file(root, path).hits)
    return found


def _visit_file(root: Path, path: Path) -> _Visitor:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(root.parents[1]).as_posix()
    visitor = _Visitor(rel, _Bindings(tree, _package_of(PurePosixPath(path.relative_to(root.parent).as_posix()))))
    visitor.body(tree.body, "<module>", "module")
    return visitor


def diff(found: Counter, allow: Counter) -> Tuple[Counter, Counter]:
    """``(unexpected, stale)`` == ``(found - allow, allow - found)`` (Counter subtraction: exact counts)."""
    return found - allow, allow - found


# --------------------------------------------------------------------------- the allowlist (OA-3)

_R3 = "src/reader3_app/reader3.py"
_RD = "src/reader3_app/web/routers/reader.py"
_URLS = "src/reader3_app/web/urls.py"
_LIB = "src/reader3_app/web/routers/library.py"
_SS = "src/reader3_app/search_service.py"
_VS = "src/reader3_app/vector_search.py"

#: Built from the scan output at d4c4f90 and reviewed against the plan's owner table (OA-3).
#: ``(relpath, qualname, literal, count, owner)``; one key may carry several owners (``DOCUMENTED_MIXED``).
ALLOWLIST_ENTRIES: List[Tuple[str, str, str, int, str]] = [
    # reader3.py -- the writer and legacy loader; WI-3.1 shrinks these (R-RATCHET).
    (_R3, "<module>", "book.epub", 1, "WI-3.1"),
    (_R3, "<module>", "images", 1, "WI-3.1"),
    (_R3, "_parked_asides", "book.pkl", 1, "WI-3.1"),
    (_R3, "_validate_staged_artifacts", "book.pkl", 1, "WI-3.1"),
    (_R3, "_validate_staged_artifacts", "book.epub", 1, "WI-3.1"),
    (_R3, "_commit_staged_artifacts", "book.epub", 2, "WI-3.1"),
    (_R3, "_commit_staged_artifacts", "images", 2, "WI-3.1"),
    (_R3, "_commit_staged_artifacts", "book.pkl", 2, "WI-3.1"),
    (_R3, "process_epub", "images", 1, "WI-3.1"),
    (_R3, "process_epub", "book.pkl", 1, "WI-3.1"),
    (_R3, "_build_into_staging", "book.epub", 1, "WI-3.1"),
    (_R3, "_build_into_staging", "images", 1, "WI-3.1"),
    (_R3, "_build_into_staging", "book.pkl", 1, "WI-3.1"),
    (_R3, "save_to_pickle", "book.pkl", 1, "WI-3.1"),
    (_R3, "main", "book.pkl", 1, "4b.4"),
    # web/routers/reader.py -- the resource routes (4b.2) and their URL literals (url, not a filesystem path).
    (_RD, "serve_epub.<decorator>", "book.epub", 1, "url"),
    (_RD, "serve_epub", "book.epub", 2, "4b.2"),
    (_RD, "read_chapter", "images", 1, "4b.2"),
    (_RD, "read_chapter", "book.epub", 1, "4b.2"),
    (_RD, "read_chapter", "book.epub", 1, "url"),
    (_RD, "serve_image.<decorator>", "images", 1, "url"),
    (_RD, "serve_image", "images", 1, "4b.2"),
    # web/urls.py -- the cover URL builder.
    (_URLS, "cover_url", "images", 1, "url"),
    # search_service.py
    (_SS, "<module>", "_book_pkl_path", 1, "4b.5"),
    (_SS, "list_book_ids", "_book_pkl_path", 1, "4b.5"),
    (_SS, "load_book_index", "_book_pkl_path", 1, "4b.3"),
    # vector_search.py
    (_VS, "BookVectorIndex._load_book", "book.pkl", 1, "4b.4"),
]


def _sum(rows: List[Tuple[str, str, str, int, str]]) -> Counter:
    out: Counter = Counter()
    for rel, qual, lit, count, _owner in rows:
        out[(rel, qual, lit)] += count
    return out


ALLOWLIST: Counter = _sum(ALLOWLIST_ENTRIES)

#: Keys that legitimately carry more than one owner. B1-38(g). Reason for the one entry: L96's flat epub read
#: (4b.2) + the ``/read/{id}/book.epub`` URL literal (url) share ``read_chapter``'s scope. Row B2-MIXED (owned
#: by 4b.2) moves that URL literal out and changes this to ``set()`` explicitly.
DOCUMENTED_MIXED: Set[Key] = {(_RD, "read_chapter", "book.epub")}

#: B1-30b: written by READING the source (matrix designer, round 2), not from ``scan``. Decorator hits re-keyed
#: per the adversary round 2 ruling (gap 3a). Exact for reader3.py, reader.py, urls.py, library.py; a subset for
#: search_service.py and vector_search.py.
REQUIRED_ROWS: List[Tuple[str, str, str, int, str]] = [
    (_R3, "<module>", "book.epub", 1, "WI-3.1"),  # l.331 _KNOWN_ASIDES value
    (_R3, "<module>", "images", 1, "WI-3.1"),  # l.332
    (_R3, "_parked_asides", "book.pkl", 1, "WI-3.1"),  # l.322
    (_R3, "_validate_staged_artifacts", "book.pkl", 1, "WI-3.1"),  # l.554
    (_R3, "_validate_staged_artifacts", "book.epub", 1, "WI-3.1"),  # l.571
    (_R3, "_commit_staged_artifacts", "book.epub", 2, "WI-3.1"),  # l.643, 662
    (_R3, "_commit_staged_artifacts", "images", 2, "WI-3.1"),  # l.644, 663
    (_R3, "_commit_staged_artifacts", "book.pkl", 2, "WI-3.1"),  # l.669 x2
    (_R3, "process_epub", "images", 1, "WI-3.1"),  # l.789
    (_R3, "process_epub", "book.pkl", 1, "WI-3.1"),  # l.800, inside the f-string's FormattedValue
    (_R3, "_build_into_staging", "book.epub", 1, "WI-3.1"),  # l.815
    (_R3, "_build_into_staging", "images", 1, "WI-3.1"),  # l.841 f"images/{safe_fname}"
    (_R3, "_build_into_staging", "book.pkl", 1, "WI-3.1"),  # l.922
    (_R3, "save_to_pickle", "book.pkl", 1, "WI-3.1"),  # l.939
    (_R3, "main", "book.pkl", 1, "4b.4"),  # l.1007
    (_RD, "serve_epub.<decorator>", "book.epub", 1, "url"),  # l.27
    (_RD, "serve_epub", "book.epub", 2, "4b.2"),  # l.31, 34
    (_RD, "read_chapter", "images", 1, "4b.2"),  # l.86
    (_RD, "read_chapter", "book.epub", 1, "4b.2"),  # l.96
    (_RD, "read_chapter", "book.epub", 1, "url"),  # l.105
    (_RD, "serve_image.<decorator>", "images", 1, "url"),  # l.113
    (_RD, "serve_image", "images", 1, "4b.2"),  # l.124
    (_URLS, "cover_url", "images", 1, "url"),  # l.20
    (_SS, "<module>", "_book_pkl_path", 1, "4b.5"),  # l.15
    (_SS, "list_book_ids", "_book_pkl_path", 1, "4b.5"),  # l.259
    (_SS, "load_book_index", "_book_pkl_path", 1, "4b.3"),  # l.397
    (_VS, "BookVectorIndex._load_book", "book.pkl", 1, "4b.4"),  # l.122
]
REQUIRED: Counter = _sum(REQUIRED_ROWS)
FULLY_READ: Tuple[str, ...] = (_R3, _RD, _URLS, _LIB)

#: B1-38(f): the owner multiset over the FULL allowlist, confirmed against the scan before red.
FULL_OWNER_MULTISET: Counter = Counter({"WI-3.1": 17, "4b.2": 5, "url": 4, "4b.4": 2, "4b.5": 2, "4b.3": 1})


def _owners(rows: List[Tuple[str, str, str, int, str]]) -> Counter:
    out: Counter = Counter()
    for _rel, _qual, _lit, count, owner in rows:
        out[owner] += count
    return out


def _explain(keys: Counter) -> str:
    owners: Dict[Key, List[str]] = {}
    for rel, qual, lit, count, owner in ALLOWLIST_ENTRIES:
        owners.setdefault((rel, qual, lit), []).append(f"{owner} x{count}")
    none = ["(none -- not allowlisted)"]
    return "\n".join(f"  {k} x{v}  owner: {owners.get(k, none)}" for k, v in sorted(keys.items()))


# --------------------------------------------------------------------------- tree helpers


def _copy_real(tmp: Path) -> Path:
    dst = tmp / "src" / "reader3_app"
    shutil.copytree(REAL_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def _tree(tmp: Path, files: Dict[str, str]) -> Path:
    root = tmp / "src" / "reader3_app"
    for rel, source in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _one(tmp: Path, rel: str, source: str) -> Counter:
    return scan(_tree(tmp, {rel: source}))


# --------------------------------------------------------------------------- B1-30 / B1-30b


def test_b1_30_real_tree_equals_the_allowlist() -> None:
    """B1-30 -- FUTURE TRIPWIRE (L2/S1): it pins today's tree; it turns red on the next new flat-path access, or
    when a sub-item forgets to shrink its entries. Not evidence that 4b.1's behaviour is correct."""
    found = scan(REAL_ROOT)
    unexpected, stale = diff(found, ALLOWLIST)
    assert (unexpected, stale) == (Counter(), Counter()), (
        f"unexpected (not allowlisted):\n{_explain(unexpected)}\nstale (allowlisted, no longer found):\n"
        f"{_explain(stale)}"
    )
    assert all(rel.startswith("src/reader3_app/") for rel, _q, _l in found), sorted(found)


def test_b1_30b_required_keys_are_found_independently_of_scan() -> None:
    """B1-30b -- L1/L2, S6: a hand-written oracle (REQUIRED) kills a scan that under-reports, against which an
    allowlist built from the scan's own output would be silent."""
    found = scan(REAL_ROOT)
    assert found & REQUIRED == REQUIRED, REQUIRED - found
    for f in FULLY_READ:
        got = Counter({k: v for k, v in found.items() if k[0] == f})
        want = Counter({k: v for k, v in REQUIRED.items() if k[0] == f})
        assert got == want, (f, got - want, want - got)
    assert ALLOWLIST & REQUIRED == REQUIRED, REQUIRED - ALLOWLIST
    assert Counter({k: v for k, v in found.items() if k[0] == _LIB}) == Counter()


# --------------------------------------------------------------------------- B1-31 / B1-32 / B1-32b


def test_b1_31_leg1_module_level_injection_is_unexpected(tmp_path: Path) -> None:
    """B1-31 leg 1 -- L2/S6."""
    before = scan(REAL_ROOT)
    root = _copy_real(tmp_path)
    lib = root / "web" / "routers" / "library.py"
    lib.write_text(lib.read_text(encoding="utf-8") + '\nX = os.path.join(d, "book.pkl")\n', encoding="utf-8")
    unexpected, stale = diff(scan(root), ALLOWLIST)
    assert unexpected == Counter({(_LIB, "<module>", "book.pkl"): 1})
    assert stale == Counter()
    assert scan(REAL_ROOT) == before


def test_b1_31_leg2_injection_inside_library_view_is_attributed_to_it(tmp_path: Path) -> None:
    """B1-31 leg 2 -- L2/S6: qualname-blind scanners fail this."""
    before = scan(REAL_ROOT)
    root = _copy_real(tmp_path)
    lib = root / "web" / "routers" / "library.py"
    lines = lib.read_text(encoding="utf-8").splitlines(keepends=True)
    tree = ast.parse("".join(lines))
    view = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "library_view"]
    assert len(view) == 1
    anchor = [
        i for i in range(view[0].lineno - 1, view[0].end_lineno or 0) if lines[i].strip() == "books = []"
    ]
    assert len(anchor) == 1, "library_view must still contain exactly one `books = []` line"
    indent = lines[anchor[0]][: len(lines[anchor[0]]) - len(lines[anchor[0]].lstrip())]
    lines.insert(anchor[0] + 1, f"{indent}_probe = 'images/cover.jpg'\n")
    lib.write_text("".join(lines), encoding="utf-8")
    unexpected, stale = diff(scan(root), ALLOWLIST)
    assert unexpected == Counter({(_LIB, "library_view", "images"): 1})
    assert stale == Counter()
    assert scan(REAL_ROOT) == before


def _rewriteable_nodes(root: Path, key: Key) -> List[ast.AST]:
    """The AST nodes that produce ``key``'s hits, when every one can be rewritten by span: a str Constant outside
    any f-string (Python 3.10 gives f-string parts no usable positions), a Name, or an Attribute, on one line.
    Returns [] if any producing node is not of that kind."""
    path = root.parents[1] / key[0]
    visitor = _visit_file(root, path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    in_fstring = {
        (c.lineno, c.col_offset, getattr(c, "value", None))
        for n in ast.walk(tree)
        if isinstance(n, ast.JoinedStr)
        for c in ast.walk(n)
        if isinstance(c, ast.Constant)
    }
    nodes = [node for k, node in visitor.trace if k == key]
    for node in nodes:
        if not isinstance(node, (ast.Constant, ast.Name, ast.Attribute)):
            return []
        if isinstance(node, ast.Constant) and (node.lineno, node.col_offset, node.value) in in_fstring:
            return []
        if node.lineno != node.end_lineno:
            return []
    return nodes


def _rewrite_span(path: Path, node: ast.AST, replacement: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    i = node.lineno - 1  # type: ignore[attr-defined]
    raw = lines[i].encode("utf-8")
    start, end = node.col_offset, node.end_col_offset  # type: ignore[attr-defined]
    lines[i] = (raw[:start] + replacement.encode("utf-8") + raw[end:]).decode("utf-8")
    path.write_text("".join(lines), encoding="utf-8")


def test_b1_32_a_fully_stale_entry_is_reported(tmp_path: Path) -> None:
    """B1-32 -- L2/S6. The victim is chosen dynamically: the first count-1 allowlisted key outside reader3.py
    whose single occurrence can be rewritten by span (see ``_rewriteable_nodes``)."""
    root = _copy_real(tmp_path)
    victim: Optional[Tuple[Key, ast.AST]] = None
    for key, count in ALLOWLIST.items():
        if count != 1 or key[0] == _R3:
            continue
        nodes = _rewriteable_nodes(root, key)
        if len(nodes) == 1:
            victim = (key, nodes[0])
            break
    assert victim is not None, "no count-1 allowlisted key outside reader3.py could be rewritten"
    key, node = victim
    _rewrite_span(root.parents[1] / key[0], node, '"x"')
    unexpected, stale = diff(scan(root), ALLOWLIST)
    assert stale == Counter({key: 1})
    assert unexpected == Counter()


def test_b1_32b_partial_staleness_two_to_one(tmp_path: Path) -> None:
    """B1-32b -- L1/S2: kills a presence-only (set) stale check."""
    key = ("src/reader3_app/m.py", "f", "book.pkl")
    allow = Counter({key: 2})
    root = _tree(tmp_path, {"m.py": 'def f():\n    a = "book.pkl"\n    b = "book.pkl"\n'})
    assert diff(scan(root), allow) == (Counter(), Counter())
    (root / "m.py").write_text('def f():\n    a = "book.pkl"\n    b = "x"\n', encoding="utf-8")
    unexpected, stale = diff(scan(root), allow)
    assert stale == Counter({key: 1})
    assert unexpected == Counter()


# --------------------------------------------------------------------------- B1-33 scope


def test_b1_33_excluded_files_by_exact_relpath(tmp_path: Path) -> None:
    """B1-33 -- L2/S2: kills a basename-only exclusion (OA-2)."""
    root = _tree(
        tmp_path,
        {
            "book_store.py": 'p = "book.pkl"\n',
            "book_format.py": 'd = "images"\n',
            "sub/book_store.py": 'p = "book.pkl"\n',
            "a.py": 'e = "book.epub"\n',
        },
    )
    assert scan(root) == Counter(
        {
            ("src/reader3_app/sub/book_store.py", "<module>", "book.pkl"): 1,
            ("src/reader3_app/a.py", "<module>", "book.epub"): 1,
        }
    )


# --------------------------------------------------------------------------- B1-34 segment matching

_A = "src/reader3_app/a.py"


def _in_f(body: str) -> str:
    return "def f(d, n):\n" + "".join(f"    {line}\n" for line in body.splitlines())


B1_34_ROWS = [
    (1, _in_f('p = f"{d}/book.pkl"'), {("f", "book.pkl"): 1}),
    (2, _in_f('p = f"images/{n}"'), {("f", "images"): 1}),
    (3, _in_f('p = "images/" + n'), {("f", "images"): 1}),
    (4, 'p = "images/cover.jpg"\n', {("<module>", "images"): 1}),
    (5, 'p = "/book.epub"\n', {("<module>", "book.epub"): 1}),
    (6, "p = 'book.pkl'\n", {("<module>", "book.pkl"): 1}),
    (7, 'p = "book.pkl.tmp"\n', {}),
    (8, 'p = "images_dir"\n', {}),
    (9, 'def g():\n    """see books/x/book.pkl"""\n    return 1\n', {}),
    (10, '"""see books/x/book.pkl"""\n', {}),
    (11, 'class C:\n    """see books/x/book.pkl"""\n', {}),
    (12, 's = """see books/x/book.pkl"""\n', {("<module>", "book.pkl"): 1}),
    (13, 'x = 1\n"""see books/x/book.pkl"""\n', {("<module>", "book.pkl"): 1}),
    (14, 'q = "x"  # see books/x/book.pkl\n', {}),
    (15, _in_f('p = os.path.join(d, "images", "book.pkl")'), {("f", "images"): 1, ("f", "book.pkl"): 1}),
    (16, 'p = "a/images/b/images"\n', {("<module>", "images"): 2}),
    (17, _in_f("p = f\"{d}/{'book.epub'}\""), {("f", "book.epub"): 1}),
    (18, 'p = "book." + "pkl"\n', {}),
    (19, 'p = f"(expected {d}/book.pkl)"\n', {}),
    (21, 'def g(d):\n    os.remove(os.path.join(d, "book.pkl"))\n', {("g", "book.pkl"): 1}),
    (22, 'os.remove("x/images")\n', {("<module>", "images"): 1}),
]


@pytest.mark.parametrize("row,source,expected", B1_34_ROWS, ids=[f"row{r[0]}" for r in B1_34_ROWS])
def test_b1_34_segment_matching(tmp_path: Path, row: int, source: str, expected: Dict[Tuple[str, str], int]) -> None:
    """B1-34 -- L1/S2-S6: one equivalence-class edge of R-RATCHET per row (rows 9-13, 21, 22: OA-5's boundary)."""
    assert _one(tmp_path, "a.py", source) == Counter({(_A, q, lit): n for (q, lit), n in expected.items()})


def test_b1_34_row20_non_py_and_pycache_are_not_scanned(tmp_path: Path) -> None:
    """B1-34 row 20 -- L1/S2."""
    root = _tree(tmp_path, {"__pycache__/x.py": 'p = "book.pkl"\n', "notes.txt": 'p = "book.pkl"\n'})
    assert scan(root) == Counter()


# --------------------------------------------------------------------------- B1-34b qualnames

_Q = "src/reader3_app/q.py"
_PRELUDE = "def route(p):\n    return lambda fn: fn\n"
_Q_BODY = '''async def af():
    return "book.pkl"
class C:
    K = "images"
    def m(self):
        return "book.epub"
    async def am(self):
        return "book.pkl"
def f():
    def g():
        return "book.pkl"
    h = lambda: "images"
    return ["book.epub" for _ in ()]
@route("/x/book.epub")
def r(p="images"):
    return 1
'''


def _import(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_b1_34b_qualname_attribution(tmp_path: Path) -> None:
    """B1-34b -- L1/S2. Decorator hit re-keyed to ``r.<decorator>`` per the adversary round 2 ruling (gap 3a)."""
    root = _tree(tmp_path, {"q.py": _PRELUDE + _Q_BODY})
    found = scan(root)
    assert found == Counter(
        {
            (_Q, "af", "book.pkl"): 1,
            (_Q, "C", "images"): 1,
            (_Q, "C.m", "book.epub"): 1,
            (_Q, "C.am", "book.pkl"): 1,
            (_Q, "f.<locals>.g", "book.pkl"): 1,
            (_Q, "f", "images"): 1,
            (_Q, "f", "book.epub"): 1,
            (_Q, "r.<decorator>", "book.epub"): 1,
            (_Q, "r", "images"): 1,
        }
    )
    module = _import(root / "q.py", "wi4b1_ratchet_q")
    quals = {q for _rel, q, _lit in found}
    for obj in (module.af, module.C.m, module.C.am):
        assert obj.__qualname__ in quals, (obj.__qualname__, quals)
    variant = _tree(tmp_path / "v", {"q2.py": 'def f():\n    def g():\n        return "book.pkl"\n    return g\n'})
    g = _import(variant / "q2.py", "wi4b1_ratchet_q2").f()
    assert scan(variant) == Counter({("src/reader3_app/q2.py", g.__qualname__, "book.pkl"): 1})
    assert g.__qualname__ == "f.<locals>.g"


B1_34B_DECORATOR_ROWS = [
    (
        "function",
        '@route("/x/book.epub")\ndef r(d):\n    return os.path.join(d, "book.epub")\n',
        {("r.<decorator>", "book.epub"): 1, ("r", "book.epub"): 1},
    ),
    (
        "method",
        'class C:\n    @route("/x/images")\n    def m(self):\n        return "images/a.png"\n',
        {("C.m.<decorator>", "images"): 1, ("C.m", "images"): 1},
    ),
]


@pytest.mark.parametrize("name,source,expected", B1_34B_DECORATOR_ROWS, ids=[r[0] for r in B1_34B_DECORATOR_ROWS])
def test_b1_34b_decorators_get_their_own_scope(
    tmp_path: Path, name: str, source: str, expected: Dict[Tuple[str, str], int]
) -> None:
    """B1-34b decorator rows (adversary round 2, gap 3a) -- L1/S2; the method row proves the qualname path."""
    assert _one(tmp_path, "q.py", source) == Counter({(_Q, q, lit): n for (q, lit), n in expected.items()})


# --------------------------------------------------------------------------- B1-34c identifier forms

_PA = "src/reader3_app/pkg/a.py"
B1_34C_ROWS = [
    (
        1,
        "from .. import book_format\ndef f(d): return os.path.join(d, book_format.PKL)\n",
        {("f", "book_format.PKL"): 1},
    ),
    (2, "from .. import book_format as bf\nx = bf.IMAGES\n", {("<module>", "book_format.IMAGES"): 1}),
    (
        3,
        "from ..book_format import EPUB\ndef f(): return EPUB\n",
        {("<module>", "book_format.EPUB"): 1, ("f", "book_format.EPUB"): 1},
    ),
    (4, "from ..book_format import PKL as P\ny = P\n", {("<module>", "book_format.PKL"): 2}),
    (5, "from reader3_app import book_format\nz = book_format.EPUB\n", {("<module>", "book_format.EPUB"): 1}),
    (6, "from .. import book_store\ndef f(b, d): return book_store._book_pkl_path(b, d)\n", {("f", PKL_PATH): 1}),
    (
        7,
        "from ..book_store import _book_pkl_path as bpp\ndef f(b, d): return bpp(b, d)\n",
        {("<module>", PKL_PATH): 1, ("f", PKL_PATH): 1},
    ),
    (
        8,
        "from ..book_store import _book_pkl_path\ndef f(b, d): return _book_pkl_path(b, d)\n",
        {("<module>", PKL_PATH): 1, ("f", PKL_PATH): 1},
    ),
    (9, "import other\nw = other.PKL\n", {}),
    (10, 'PKL = "x"\nw = PKL\n', {}),
    (11, 'from .. import book_format\nv = getattr(book_format, "PKL")\n', {}),
    (12, "import reader3_app.book_format as bf\nx = bf.PKL\n", {("<module>", "book_format.PKL"): 1}),
    (13, "import reader3_app.book_format\nx = reader3_app.book_format.PKL\n", {}),  # pinned: NOT detected
]


@pytest.mark.parametrize("row,source,expected", B1_34C_ROWS, ids=[f"row{r[0]}" for r in B1_34C_ROWS])
def test_b1_34c_identifier_forms(tmp_path: Path, row: int, source: str, expected: Dict[Tuple[str, str], int]) -> None:
    """B1-34c -- L1/S2-S6. Rows 11 and 13 are out of scope and pinned as 0 hits (tripwire, not proof)."""
    assert _one(tmp_path, "pkg/a.py", source) == Counter({(_PA, q, lit): n for (q, lit), n in expected.items()})


# --------------------------------------------------------------------------- B1-35 / B1-36


def test_b1_35_line_number_independence(tmp_path: Path) -> None:
    """B1-35 -- L2/S6 metamorphic: kills a line-number-keyed allowlist."""
    root = _copy_real(tmp_path)
    for path in _in_scope(root):
        path.write_text("\n" * 5 + path.read_text(encoding="utf-8"), encoding="utf-8")
    shifted = scan(root)
    assert shifted == scan(REAL_ROOT)
    assert diff(shifted, ALLOWLIST) == (Counter(), Counter())


def _statement_holding(root: Path, key: Key) -> Optional[ast.stmt]:
    """The innermost non-def statement containing ``key``'s single producing node (None if ``key`` has != 1)."""
    path = root.parents[1] / key[0]
    nodes = [node for k, node in _visit_file(root, path).trace if k == key]
    if len(nodes) != 1:
        return None
    best: Optional[ast.stmt] = None
    for stmt in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(stmt, ast.stmt) or isinstance(stmt, _DEFS):
            continue
        if any(
            type(sub) is type(nodes[0]) and (sub.lineno, sub.col_offset) == (nodes[0].lineno, nodes[0].col_offset)
            for sub in ast.walk(stmt)
            if hasattr(sub, "lineno")
        ):
            if best is None or (stmt.end_lineno or 0) - stmt.lineno <= (best.end_lineno or 0) - best.lineno:
                best = stmt
    return best


def test_b1_36_a_duplicated_allowlisted_statement_is_an_excess_hit(tmp_path: Path) -> None:
    """B1-36 -- L2/S2: kills a set-keyed allowlist. Target: vector_search's ``_load_book`` return; once 4b.4
    removes it, the first remaining count-1 key outside reader3.py whose statement is in a plain function."""
    root = _copy_real(tmp_path)
    preferred = (_VS, "BookVectorIndex._load_book", "book.pkl")
    candidates = [preferred] if ALLOWLIST.get(preferred) == 1 else []
    candidates += [k for k, c in ALLOWLIST.items() if c == 1 and k[0] != _R3 and k != preferred]
    for key in candidates:
        if key[1] == "<module>" or key[1].endswith(".<decorator>"):
            continue
        path = root.parents[1] / key[0]
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        stmt = _statement_holding(root, key)
        if stmt is None:
            continue
        block = lines[stmt.lineno - 1 : stmt.end_lineno]
        path.write_text("".join(lines[: stmt.end_lineno] + block + lines[stmt.end_lineno :]), encoding="utf-8")
        break
    else:
        pytest.fail("no duplicable count-1 allowlisted key")
    if key == preferred:
        assert key == (_VS, "BookVectorIndex._load_book", "book.pkl")
    unexpected, stale = diff(scan(root), ALLOWLIST)
    assert unexpected == Counter({key: 1})
    assert stale == Counter()


# --------------------------------------------------------------------------- B1-37 additivity (Hypothesis)

_FILES = ("m0.py", "pkg/n1.py", "book_store.py", "sub/book_store.py")
_SLOTS = ("<module>", "f", "C.m")
_TEMPLATES = {
    'v = "book.pkl"': "book.pkl",
    "v = 'book.epub'": "book.epub",
    'v = f"{x}/images"': "images",
    'v = "/book.epub"': "book.epub",
    "v = _book_pkl_path": PKL_PATH,
}


def _build(files: List[str], injections: List[Tuple[str, str, str]]) -> Dict[str, str]:
    out = {}
    for rel in files:
        mine = [(slot, tpl) for f, slot, tpl in injections if f == rel]
        mod = [tpl for slot, tpl in mine if slot == "<module>"]
        fn = [tpl for slot, tpl in mine if slot == "f"]
        meth = [tpl for slot, tpl in mine if slot == "C.m"]
        src = "x = 1\n" + "".join(f"{t}\n" for t in mod)
        src += "def f():\n" + "".join(f"    {t}\n" for t in fn) + "    pass\n"
        src += "class C:\n    def m(self):\n" + "".join(f"        {t}\n" for t in meth) + "        pass\n"
        out[rel] = src
    return out


@st.composite
def _trees(draw):
    files = draw(st.lists(st.sampled_from(_FILES), min_size=1, max_size=4, unique=True))
    injections = draw(
        st.lists(
            st.tuples(st.sampled_from(files), st.sampled_from(_SLOTS), st.sampled_from(sorted(_TEMPLATES))),
            max_size=6,
        )
    )
    return files, injections


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(tree=_trees())
def test_b1_37_additivity_over_synthetic_trees(tree: Tuple[List[str], List[Tuple[str, str, str]]]) -> None:
    """B1-37 -- L2/S4: scan(T + I) == scan(T) + keys(I). Kills a hardcoded ALLOWLIST, first-hit-per-file and
    qualname-blind scanners."""
    files, injections = tree
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), _build(files, injections))
        expected = Counter(
            (f"src/reader3_app/{rel}", slot, _TEMPLATES[tpl]) for rel, slot, tpl in injections if rel != "book_store.py"
        )
        assert scan(root) == expected


# --------------------------------------------------------------------------- B1-38 owners


def test_b1_38_owner_vocabulary_and_multisets() -> None:
    """B1-38 (a)-(g) -- L1/S1, anchored to REQUIRED (d)/(e) so it is more than the allowlist checking itself."""
    # (a)
    assert {owner for *_k, owner in ALLOWLIST_ENTRIES} <= OWNERS
    for rel, qual, lit, count, owner in ALLOWLIST_ENTRIES:
        assert count >= 1, (rel, qual, lit, count)
        # (b)
        if owner == "WI-3.1":
            assert rel == _R3, (rel, qual, lit)
        # (c)
        if owner == "url":
            assert lit in ("images", "book.epub"), (rel, qual, lit)
            assert rel.startswith("src/reader3_app/web/"), (rel, qual, lit)
    # (d)
    for key in REQUIRED:
        want = Counter({o: c for r, q, lit, c, o in REQUIRED_ROWS if (r, q, lit) == key})
        got = Counter({o: c for r, q, lit, c, o in ALLOWLIST_ENTRIES if (r, q, lit) == key})
        assert got == want, (key, got, want)
    assert Counter(
        {o: c for r, q, lit, c, o in ALLOWLIST_ENTRIES if (r, q, lit) == (_RD, "serve_epub", "book.epub")}
    ) == Counter({"4b.2": 2})
    # (e)
    assert _owners(REQUIRED_ROWS) == Counter(
        {"WI-3.1": 17, "4b.4": 2, "4b.2": 5, "url": 4, "4b.5": 2, "4b.3": 1, "permanent": 0}
    )
    # (f)
    assert _owners(ALLOWLIST_ENTRIES) == FULL_OWNER_MULTISET
    # (g) one owner per key, except DOCUMENTED_MIXED -- which must not quietly grow.
    owners_per_key: Dict[Key, Set[str]] = {}
    for rel, qual, lit, _count, owner in ALLOWLIST_ENTRIES:
        owners_per_key.setdefault((rel, qual, lit), set()).add(owner)
    mixed = {k for k, owners in owners_per_key.items() if len(owners) > 1}
    assert mixed == DOCUMENTED_MIXED, mixed ^ DOCUMENTED_MIXED
    assert DOCUMENTED_MIXED == {("src/reader3_app/web/routers/reader.py", "read_chapter", "book.epub")}


# --------------------------------------------------------------------------- B1-39


def test_b1_39_scan_is_deterministic_and_read_only() -> None:
    """B1-39 -- L2/S2."""
    paths = _in_scope(REAL_ROOT)
    assert paths, "scan scope is empty"
    before = {p: p.stat().st_mtime_ns for p in paths}
    first, second = scan(REAL_ROOT), scan(REAL_ROOT)
    assert first == second
    assert {p: p.stat().st_mtime_ns for p in paths} == before

