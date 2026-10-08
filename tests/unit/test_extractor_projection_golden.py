"""012 WI-2a.4: the golden extractor projection that tells a reviewer when to bump ``reader3.EXTRACTOR_VERSION``.

Matrix: ``.claude/tdd-guardian/tests-20261008-234253.md`` section "WI-2a.4" (cases G4-01 .. G4-09).

The golden ``tests/unit/snapshots/extractor_projection.json`` records, for every ``ELIGIBLE`` corpus builder, the
annotation-relevant projection ``[[href, order, sha256(chapter.text)], ...]`` -- a hash of the *extracted text*, not of
the raw bytes -- plus the ``extractor_version`` it was recorded at.

Q13 (2): the golden detects a projection change; it is not the only bump criterion. So the golden's version must not
exceed the code's (``<=``), and equality is NOT required.

R7: regeneration is manual only, never from a test run::

    uv run python -m tests.unit.test_extractor_projection_golden --regenerate

Law (G4-02): comparator non-vacuity -- for every projection-changing mutation, ``projection_mismatch`` is non-empty and
names the book and chapter; ``projection_mismatch(golden, golden) == []``.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import pytest

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
if str(_FIXTURES) not in sys.path:  # `python -m tests.unit....` does not run tests/conftest.py
    sys.path.insert(0, str(_FIXTURES))

import epub_corpus as ec  # noqa: E402
from reader3_app import reader3  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent / "snapshots" / "extractor_projection.json"
REGEN_CMD = "uv run python -m tests.unit.test_extractor_projection_golden --regenerate"
BUMP_RULE = (
    "projection changed — review; if annotation-relevant, bump reader3.EXTRACTOR_VERSION and regenerate the golden"
)

ELIGIBLE: Tuple[str, ...] = (
    "build_bad_encoding",
    "build_cjk",
    "build_diacritics",
    "build_empty_chapters",
    "build_epub2",
    "build_epub3",
    "build_illustrated",
    "build_malformed_toc",
    "build_missing_toc_epub3",
    "build_spine_toc_maze",
)
EXCLUDED: Dict[str, str] = {
    "build_missing_toc_epub2": "raises on processing: empty NCX navMap -> TypeError in parse_toc_recursive",
    "build_no_documents": "raises on processing: process_epub refuses an empty spine (ArtifactValidationError)",
    "build_huge_epub": "unit-lane time budget: one multi-megabyte chapter; its extraction is not a distinct shape",
    "write_not_a_zip": "raises on processing: not a zip archive, nothing to extract",
    "write_truncated_epub": "not a standalone builder: needs source=, and a truncated zip raises on processing",
    "build_without_container": "raises on processing: no META-INF/container.xml, ebooklib cannot open it",
}

Projection = List[List[Any]]  # [[href, order, sha256(text)], ...]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _project(book: reader3.Book) -> Projection:
    return [[c.href, c.order, _sha(c.text)] for c in book.spine]


def live_projection(epub_path: Path) -> Projection:
    """Process ``epub_path`` with the real pipeline into a throwaway dir and project its chapters."""
    with tempfile.TemporaryDirectory() as d:
        book = reader3.process_epub(str(epub_path), os.path.join(d, "book_data"))
    return _project(book)


def build_live(root: Path) -> Dict[str, Projection]:
    return {name: live_projection(getattr(ec, name)(root / f"{name}.epub")) for name in ELIGIBLE}


def projection_mismatch(live: Mapping[str, Projection], golden: Mapping[str, Projection]) -> List[str]:
    """[] when equal; otherwise one line per differing book or chapter, naming the book and the href."""
    lines: List[str] = []
    for book in sorted(set(live) | set(golden)):
        if book not in live:
            lines.append(f"{book}: in the golden, missing from the live projection")
            continue
        if book not in golden:
            lines.append(f"{book}: in the live projection, missing from the golden")
            continue
        a, b = list(live[book]), list(golden[book])
        if len(a) != len(b):
            lines.append(f"{book}: {len(a)} live chapters != {len(b)} golden chapters")
        for i in range(max(len(a), len(b))):
            la = a[i] if i < len(a) else None
            gb = b[i] if i < len(b) else None
            if la != gb:
                lines.append(f"{book} chapter {i}: live {la!r} != golden {gb!r}")
    return lines


def mismatch_report(lines: Sequence[str]) -> str:
    return f"{BUMP_RULE}\n  regenerate with: {REGEN_CMD}\n" + "\n".join(lines)


def _dump_golden(data: Mapping[str, Any]) -> str:
    """Deterministic text: sorted keys, one chapter row per line, trailing newline."""
    books = data["books"]
    out = ["{", '  "books": {']
    names = sorted(books)
    for n, name in enumerate(names):
        rows = [json.dumps(row, ensure_ascii=False) for row in books[name]]
        sep = "," if n < len(names) - 1 else ""
        if rows:
            out.append(f"    {json.dumps(name)}: [")
            out.extend(f"      {row}{',' if r < len(rows) - 1 else ''}" for r, row in enumerate(rows))
            out.append(f"    ]{sep}")
        else:
            out.append(f"    {json.dumps(name)}: []{sep}")
    out += ["  },", f'  "extractor_version": {json.dumps(data["extractor_version"])}', "}"]
    return "\n".join(out) + "\n"


def _write_golden(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_golden(data), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None, golden_path: Path = GOLDEN_PATH) -> int:
    parser = argparse.ArgumentParser(prog="test_extractor_projection_golden", description=__doc__.splitlines()[0])
    parser.add_argument("--regenerate", action="store_true", help="rewrite the golden from the current extractor")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.regenerate:
        print(f"refusing to write without --regenerate; usage: {REGEN_CMD}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as d:
        books = build_live(Path(d))
    _write_golden(golden_path, {"extractor_version": reader3.EXTRACTOR_VERSION, "books": books})
    print(f"wrote {golden_path} ({len(books)} books, extractor_version {reader3.EXTRACTOR_VERSION})")
    return 0


# --------------------------------------------------------------------------- fixtures


def _file_state(path: Path) -> Optional[Tuple[str, int, int, int]]:
    if not path.exists():
        return None
    st = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns, st.st_ino)


@pytest.fixture(scope="module", autouse=True)
def _golden_untouched() -> Iterator[None]:
    """G4-07: no test or fixture in this module writes (or creates) the golden."""
    before = _file_state(GOLDEN_PATH)
    yield
    assert _file_state(GOLDEN_PATH) == before, f"a test run wrote {GOLDEN_PATH}; only `{REGEN_CMD}` may"


def _load_golden() -> Optional[Dict[str, Any]]:
    if not GOLDEN_PATH.is_file():
        return None
    data: Dict[str, Any] = json.loads(GOLDEN_PATH.read_bytes())
    return data


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, reader3.Book]:
    """Every ELIGIBLE builder, built and processed once per module."""
    root = tmp_path_factory.mktemp("golden_corpus")
    out: Dict[str, reader3.Book] = {}
    for name in ELIGIBLE:
        path = getattr(ec, name)(root / "epubs" / f"{name}.epub")
        out[name] = reader3.process_epub(str(path), str(root / "books" / f"{name}_data"))
    return out


@pytest.fixture(scope="module")
def live(corpus: Dict[str, reader3.Book]) -> Dict[str, Projection]:
    return {name: _project(book) for name, book in corpus.items()}


def _golden_or_fail() -> Dict[str, Any]:
    golden = _load_golden()
    assert golden is not None, f"golden {GOLDEN_PATH} is missing; generate it with `{REGEN_CMD}`"
    return golden


# --------------------------------------------------------------------------- G4-01 / G4-09


def test_g4_01_live_projection_equals_the_golden(live: Dict[str, Projection]) -> None:
    golden = _golden_or_fail()
    lines = projection_mismatch(live, golden["books"])
    assert lines == [], mismatch_report(lines)


def test_g4_09_golden_is_the_file_and_is_anchored(corpus: Dict[str, reader3.Book]) -> None:
    assert GOLDEN_PATH.is_file(), f"golden {GOLDEN_PATH} is missing; generate it with `{REGEN_CMD}`"
    golden = _golden_or_fail()
    assert golden == json.loads(GOLDEN_PATH.read_bytes())

    book = corpus["build_epub2"]
    inline = [[c.href, c.order, hashlib.sha256(c.text.encode()).hexdigest()] for c in book.spine]
    assert len(inline) >= 1
    assert golden["books"]["build_epub2"] == inline
    assert golden["books"]["build_epub2"][0][:2] == ["text/one.xhtml", 0]


# --------------------------------------------------------------------------- G4-02 comparator non-vacuity


def _mutations(books: Dict[str, Projection]) -> Iterator[Tuple[str, str, Optional[str], Dict[str, Projection]]]:
    """Yield (mutation, book, affected href or None, mutated deep copy) for every applicable site."""
    for name in sorted(books):
        rows = books[name]
        for i, row in enumerate(rows):
            m = copy.deepcopy(books)
            digest = m[name][i][2]
            m[name][i][2] = ("0" if digest[0] != "0" else "1") + digest[1:]
            yield "text_char", name, row[0], m

            m = copy.deepcopy(books)
            m[name][i][1] += 1
            yield "order_shift", name, row[0], m

            m = copy.deepcopy(books)
            del m[name][i]
            yield "drop_chapter", name, row[0], m
        for i in range(len(rows) - 1):
            if rows[i][0] == rows[i + 1][0]:
                continue
            m = copy.deepcopy(books)
            m[name][i][0], m[name][i + 1][0] = m[name][i + 1][0], m[name][i][0]
            yield "swap_hrefs", name, rows[i][0], m
        m = copy.deepcopy(books)
        m[name].append(["text/injected.xhtml", len(rows), _sha("injected")])
        yield "add_chapter", name, "text/injected.xhtml", m

        m = copy.deepcopy(books)
        del m[name]
        yield "drop_book", name, None, m
    m = copy.deepcopy(books)
    m["build_phantom"] = [["text/c1.xhtml", 0, _sha("phantom")]]
    yield "extra_book", "build_phantom", None, m


MUTATIONS = ("text_char", "swap_hrefs", "order_shift", "drop_chapter", "add_chapter", "drop_book", "extra_book")


def test_g4_02_comparator_accepts_the_identity() -> None:
    golden = _golden_or_fail()
    assert projection_mismatch(golden["books"], copy.deepcopy(golden["books"])) == []


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_g4_02_comparator_detects_each_known_mutation(mutation: str) -> None:
    golden = _golden_or_fail()
    books = golden["books"]
    sites = [s for s in _mutations(books) if s[0] == mutation]
    assert sites, f"non-vacuity: {mutation} found no site in the golden"
    if mutation == "swap_hrefs":
        assert any(len(rows) >= 2 for rows in books.values())
    for _, name, href, mutated in sites:
        lines = projection_mismatch(mutated, books)
        assert lines, f"{mutation} on {name} ({href}) went undetected"
        assert any(name in line for line in lines), (mutation, name, lines)
        if href is not None:
            assert any(name in line and href in line for line in lines), (mutation, name, href, lines)
        assert BUMP_RULE in mismatch_report(lines)


# --------------------------------------------------------------------------- G4-03 extractor-level non-vacuity


def test_g4_03_changed_extractor_is_detected_through_real_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    golden = _golden_or_fail()
    real = reader3.extract_plain_text
    monkeypatch.setattr(reader3, "extract_plain_text", lambda soup: real(soup) + "​")  # fault injection

    names = ("build_epub2", "build_cjk")
    patched = {n: live_projection(getattr(ec, n)(tmp_path / f"{n}.epub")) for n in names}
    lines = projection_mismatch(patched, {n: golden["books"][n] for n in names})

    assert lines, "a changed extractor went undetected: the golden is vacuous"
    for n in names:
        assert any(n in line for line in lines), (n, lines)


# --------------------------------------------------------------------------- G4-04 .. G4-06 guards


def test_g4_04_golden_version_does_not_exceed_the_code_version() -> None:
    golden = _golden_or_fail()
    v = golden["extractor_version"]
    assert type(v) is int
    # Q13 (2): <=, not ==. A bump without a projection change is allowed.
    assert 0 < v <= reader3.EXTRACTOR_VERSION, (v, reader3.EXTRACTOR_VERSION)


def _all_builders() -> set[str]:
    return {
        n
        for n, f in inspect.getmembers(ec, inspect.isfunction)
        if f.__module__ == ec.__name__ and n.startswith(("build_", "write_"))
    }


def test_g4_05_corpus_partition_covers_every_builder() -> None:
    all_builders = _all_builders()
    assert len(all_builders) >= len(ELIGIBLE) + 1
    covered = set(ELIGIBLE) | set(EXCLUDED)
    assert covered == all_builders, f"unclassified or stale: {sorted(covered ^ all_builders)}"
    assert set(ELIGIBLE) & set(EXCLUDED) == set()
    assert all(isinstance(r, str) and r.strip() for r in EXCLUDED.values())


def test_g4_06_golden_books_equal_eligible_exactly() -> None:
    golden = _golden_or_fail()
    assert set(golden["books"]) == set(ELIGIBLE)


# --------------------------------------------------------------------------- G4-07 / G4-08 regeneration (R7)


def test_g4_07_golden_exists_and_was_not_created_by_the_run() -> None:
    # The autouse `_golden_untouched` fixture enforces "not written" at module teardown; a missing golden fails here.
    assert GOLDEN_PATH.is_file(), f"golden {GOLDEN_PATH} is missing; generate it with `{REGEN_CMD}`"
    assert _file_state(GOLDEN_PATH) is not None


def test_g4_08a_main_without_regenerate_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "g.json"
    assert main([], golden_path=target) != 0
    assert not target.exists()


def test_g4_08b_main_with_regenerate_writes_the_live_projection(
    tmp_path: Path, live: Dict[str, Projection]
) -> None:
    target = tmp_path / "g.json"
    assert main(["--regenerate"], golden_path=target) == 0
    written = json.loads(target.read_bytes())
    assert written == {"extractor_version": reader3.EXTRACTOR_VERSION, "books": live}
    assert target.read_text(encoding="utf-8").endswith("}\n")


def _is_main_guard(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in node.test.comparators)
    )


def _calls_with_scope(tree: ast.Module) -> Iterator[Tuple[ast.Call, Tuple[ast.AST, ...]]]:
    def walk(node: ast.AST, scope: Tuple[ast.AST, ...]) -> Iterator[Tuple[ast.Call, Tuple[ast.AST, ...]]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                yield child, scope
            yield from walk(child, scope + (child,))

    yield from walk(tree, ())


def _callee(call: ast.Call) -> Optional[str]:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_g4_08c_writer_is_reachable_only_from_main_and_the_main_guard() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    writer_calls, main_calls, file_writes = [], [], []
    for call, scope in _calls_with_scope(tree):
        funcs = [s.name for s in scope if isinstance(s, ast.FunctionDef)]
        guarded = any(_is_main_guard(s) for s in scope)
        callee = _callee(call)
        if callee == "_write_golden":
            writer_calls.append((call.lineno, funcs, guarded))
        elif callee == "main":
            kw = {k.arg: k.value for k in call.keywords}
            main_calls.append((call.lineno, funcs, guarded, kw))
        elif callee in ("write_text", "write_bytes", "dump"):
            file_writes.append((call.lineno, funcs))

    assert writer_calls, "non-vacuity: the scan found no call to _write_golden"
    assert all(funcs == ["main"] and not guarded for _, funcs, guarded in writer_calls), writer_calls
    assert all(funcs == ["_write_golden"] for _, funcs in file_writes), file_writes
    assert any(guarded and not funcs for _, funcs, guarded, _ in main_calls), "no `if __name__ == '__main__'` call"
    for lineno, funcs, guarded, kw in main_calls:
        if guarded:
            continue
        # Outside the guard, main may only run against an explicit, non-real golden path.
        target = kw.get("golden_path")
        assert target is not None, f"line {lineno}: main() called from {funcs} without golden_path="
        assert not (isinstance(target, ast.Name) and target.id == "GOLDEN_PATH"), f"line {lineno}"
        assert all(f.startswith("test_") for f in funcs), (lineno, funcs)


if __name__ == "__main__":
    raise SystemExit(main())
