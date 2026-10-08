"""WI-2a.6: ``save_annotations`` carries the top-level ``book_fingerprint`` key.

012 puts a ``book_fingerprint`` beside ``annotations`` in ``notes.json``; DEG-S1
(``deg_assertions.make_notes_stale``) already writes one. Every mutating path is
load -> modify -> ``save_annotations`` the whole file, and before 2a.6 that save
rebuilt the payload from ``{schema_version, book_id, annotations}`` alone -- the
first highlight after a stale-marking silently erased the marking.

The law (matrix N6): for every mutator and every str value ``v``, a file holding
``book_fingerprint == v`` holds exactly ``v`` afterwards; a file without the key
stays without it (R5: no initial stamping in 2a); the key never affects the parsed
annotations or ``annotations_version``.

Seeds are written as RAW JSON, never through ``save_annotations``, so the oracle
does not share code with the unit under test. The new names (``NOTES_FINGERPRINT_KEY``,
``KEEP``, the ``book_fingerprint`` kwarg) are reached through ``getattr`` / an
explicit signature assertion, so a missing name fails as an assertion, not an
import or a TypeError.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import deg_assertions  # type: ignore[import-not-found]
from deg_assertions import DEG_S1_ANNOTATION, STALE_FINGERPRINT  # type: ignore[import-not-found]
from reader3_app import notes_service
from reader3_app.models.annotations import Annotation

BOOK_ID = "b_data"
KEY = "book_fingerprint"
JOIN_TIMEOUT_S = 10.0

_MISSING = object()

st_hex64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
st_key_value = st.one_of(st_hex64, st.just(STALE_FINGERPRINT), st.text(max_size=40))


@pytest.fixture(autouse=True)
def _work_inside_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every relative path in this module resolves under tmp_path, never books/."""
    monkeypatch.chdir(tmp_path)


def _seed_record(**overrides: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = dict(DEG_S1_ANNOTATION)
    record["book_id"] = BOOK_ID
    record.update(overrides)
    return record


def _write_raw(books_dir: Path, records: List[Dict[str, Any]], key_value: Any = _MISSING) -> Path:
    book_dir = books_dir / BOOK_ID
    book_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"schema_version": 1, "book_id": BOOK_ID, "annotations": records}
    if key_value is not _MISSING:
        payload[KEY] = key_value
    path = book_dir / "notes.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_raw(books_dir: Path) -> Dict[str, Any]:
    data = json.loads((books_dir / BOOK_ID / "notes.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _new_annotation(ann_id: str) -> Annotation:
    return Annotation(id=ann_id, book_id=BOOK_ID, chapter_index=0, quote=f"quote {ann_id}")


# ---------------------------------------------------------------------------
# Mutators: each applies one change and returns a non-vacuity check on the result.
# ---------------------------------------------------------------------------

SEED_ID = str(DEG_S1_ANNOTATION["id"])


def _check_added(data: Dict[str, Any]) -> None:
    assert [a["id"] for a in data["annotations"]] == [SEED_ID, "n6-added"]


def _check_updated(data: Dict[str, Any]) -> None:
    assert [a.get("note_text") for a in data["annotations"]] == ["n6 edited"]


def _check_deleted(data: Dict[str, Any]) -> None:
    assert data["annotations"] == []


def _check_refreshed(data: Dict[str, Any]) -> None:
    assert [a.get("orphaned") for a in data["annotations"]] == [True]


def _mark_first_orphaned(anns: List[Annotation]) -> bool:
    anns[0].orphaned = True
    return True


MUTATORS: Dict[str, tuple[Callable[[str], Any], Callable[[Dict[str, Any]], None]]] = {
    "add_annotation_and_version": (
        lambda d: notes_service.add_annotation_and_version(d, _new_annotation("n6-added")),
        _check_added,
    ),
    "update_annotation_and_version": (
        lambda d: notes_service.update_annotation_and_version(d, BOOK_ID, SEED_ID, "n6 edited"),
        _check_updated,
    ),
    "delete_annotation_and_version": (
        lambda d: notes_service.delete_annotation_and_version(d, BOOK_ID, SEED_ID),
        _check_deleted,
    ),
    "refresh_annotations_and_version": (
        lambda d: notes_service.refresh_annotations_and_version(d, BOOK_ID, _mark_first_orphaned),
        _check_refreshed,
    ),
    "add_annotation": (
        lambda d: notes_service.add_annotation(d, _new_annotation("n6-added")),
        _check_added,
    ),
    "update_annotation": (
        lambda d: notes_service.update_annotation(d, BOOK_ID, SEED_ID, "n6 edited"),
        _check_updated,
    ),
    "delete_annotation": (
        lambda d: notes_service.delete_annotation(d, BOOK_ID, SEED_ID),
        _check_deleted,
    ),
}


# ---------------------------------------------------------------------------
# N6-01
# ---------------------------------------------------------------------------


def test_n6_01_constants_agree_and_schema_version_unchanged() -> None:
    assert getattr(notes_service, "NOTES_FINGERPRINT_KEY", None) == deg_assertions.NOTES_FINGERPRINT_KEY
    assert deg_assertions.NOTES_FINGERPRINT_KEY == "book_fingerprint"
    assert notes_service.NOTES_SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# N6-02 (property, S5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutator_name", sorted(MUTATORS))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(value=st_key_value)
def test_n6_02_every_mutator_preserves_the_key(mutator_name: str, value: str) -> None:
    mutate, check = MUTATORS[mutator_name]
    with tempfile.TemporaryDirectory() as tmp:
        books_dir = Path(tmp)
        _write_raw(books_dir, [_seed_record()], value)

        mutate(str(books_dir))

        data = _read_raw(books_dir)
        check(data)
        assert KEY in data, f"{mutator_name} dropped the {KEY!r} key"
        assert data[KEY] == value


# ---------------------------------------------------------------------------
# N6-03 (R5: no key in, no key out)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutator_name", sorted(MUTATORS))
def test_n6_03_file_without_key_stays_without_it(tmp_path: Path, mutator_name: str) -> None:
    mutate, check = MUTATORS[mutator_name]
    books_dir = tmp_path / "books"
    _write_raw(books_dir, [_seed_record()])

    mutate(str(books_dir))

    data = _read_raw(books_dir)
    check(data)
    assert KEY not in data


def test_n6_03_fresh_book_save_writes_no_key(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)

    notes_service.save_annotations(str(books_dir), BOOK_ID, [_new_annotation("n6-fresh")])

    data = _read_raw(books_dir)
    assert [a["id"] for a in data["annotations"]] == ["n6-fresh"]
    assert KEY not in data


# ---------------------------------------------------------------------------
# N6-04 (metamorphic, S4)
# ---------------------------------------------------------------------------

st_annotation_records = st.lists(
    st.builds(
        lambda i, text: _seed_record(id=f"n6-ann-{i}", note_text=text),
        st.integers(min_value=0, max_value=10_000),
        st.one_of(st.none(), st.text(max_size=20)),
    ),
    max_size=5,
    unique_by=lambda r: r["id"],
)


@settings(max_examples=40, deadline=None)
@given(records=st_annotation_records, value=st_key_value)
def test_n6_04_load_ignores_the_key(records: List[Dict[str, Any]], value: str) -> None:
    with tempfile.TemporaryDirectory() as with_tmp, tempfile.TemporaryDirectory() as without_tmp:
        with_dir, without_dir = Path(with_tmp), Path(without_tmp)
        _write_raw(with_dir, records, value)
        _write_raw(without_dir, records)

        loaded_with = notes_service.load_annotations(str(with_dir), BOOK_ID)
        loaded_without = notes_service.load_annotations(str(without_dir), BOOK_ID)

        assert [a.to_dict() for a in loaded_with] == [a.to_dict() for a in loaded_without]
        assert [a.id for a in loaded_with] == [r["id"] for r in records]
        assert notes_service.annotations_version(loaded_with) == notes_service.annotations_version(loaded_without)


# ---------------------------------------------------------------------------
# N6-05 (the real DEG fixture path)
# ---------------------------------------------------------------------------


def test_n6_05_make_notes_stale_survives_a_later_add(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    deg_assertions.make_notes_stale(books_dir, BOOK_ID)

    notes_service.add_annotation_and_version(str(books_dir), _new_annotation("n6-second"))

    data = _read_raw(books_dir)
    assert {a["id"] for a in data["annotations"]} == {SEED_ID, "n6-second"}
    assert data.get(KEY) == STALE_FINGERPRINT


# ---------------------------------------------------------------------------
# N6-06 (corrupt or non-dict existing file: no carry, save succeeds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("existing", [b"{not json", b"[]", b'"str"', b""], ids=["bad-json", "list", "str", "empty"])
def test_n6_06_corrupt_existing_file_save_succeeds_without_carry(tmp_path: Path, existing: bytes) -> None:
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    (books_dir / BOOK_ID / "notes.json").write_bytes(existing)
    ann = _new_annotation("n6-over-corrupt")

    notes_service.save_annotations(str(books_dir), BOOK_ID, [ann])

    assert _read_raw(books_dir) == {"schema_version": 1, "book_id": BOOK_ID, "annotations": [ann.to_dict()]}


# ---------------------------------------------------------------------------
# N6-07 (KEEP / str / None)
# ---------------------------------------------------------------------------


def _require_kwarg() -> object:
    """Assert the 2b contract surface exists; return KEEP. Fails as an assertion, never a TypeError."""
    params = inspect.signature(notes_service.save_annotations).parameters
    assert "book_fingerprint" in params, "save_annotations has no book_fingerprint parameter"
    keep = getattr(notes_service, "KEEP", _MISSING)
    assert keep is not _MISSING, "notes_service.KEEP is not defined"
    return keep


def test_n6_07_book_fingerprint_is_keyword_only_defaulting_to_keep() -> None:
    keep = _require_kwarg()
    param = inspect.signature(notes_service.save_annotations).parameters["book_fingerprint"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is keep


@pytest.mark.parametrize(
    ("existing", "arg", "expected"),
    [
        ("old", "KEEP", "old"),
        (_MISSING, "KEEP", _MISSING),
        ("old", "new", "new"),
        (_MISSING, "new", "new"),
        ("old", None, _MISSING),
        (_MISSING, None, _MISSING),
    ],
    ids=["keep-old", "keep-absent", "new-over-old", "new-over-absent", "none-over-old", "none-over-absent"],
)
def test_n6_07_kwarg_semantics(tmp_path: Path, existing: Any, arg: Optional[str], expected: Any) -> None:
    keep = _require_kwarg()
    books_dir = tmp_path / "books"
    _write_raw(books_dir, [_seed_record()], existing)
    value = keep if arg == "KEEP" else arg

    notes_service.save_annotations(str(books_dir), BOOK_ID, [_new_annotation("n6-kw")], book_fingerprint=value)

    data = _read_raw(books_dir)
    assert [a["id"] for a in data["annotations"]] == ["n6-kw"]
    assert data.get(KEY, _MISSING) == expected
    assert data.get(KEY, _MISSING) is not None, "null must never be written"


# ---------------------------------------------------------------------------
# N6-08 (atomic write unchanged under a failed replace)
# ---------------------------------------------------------------------------


def test_n6_08_failed_replace_leaves_seed_bytes_and_no_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    books_dir = tmp_path / "books"
    path = _write_raw(books_dir, [_seed_record()], STALE_FINGERPRINT)
    before = path.read_bytes()
    listing_before = sorted(os.listdir(books_dir / BOOK_ID))

    def boom(src: str, dst: str) -> None:
        raise OSError("n6-08 injected replace failure")

    monkeypatch.setattr(notes_service.os, "replace", boom)

    with pytest.raises(OSError, match="n6-08 injected"):
        notes_service.add_annotation_and_version(str(books_dir), _new_annotation("n6-lost"))

    assert path.read_bytes() == before
    leftovers = [n for n in os.listdir(books_dir / BOOK_ID) if n.startswith(".notes.") and n.endswith(".tmp")]
    assert leftovers == []
    assert [n for n in sorted(os.listdir(books_dir / BOOK_ID)) if n not in listing_before] in ([], ["notes.json.lock"])


# ---------------------------------------------------------------------------
# N6-09 (concurrent adds)
# ---------------------------------------------------------------------------


def test_n6_09_concurrent_adds_preserve_key_and_both_annotations(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    _write_raw(books_dir, [_seed_record()], STALE_FINGERPRINT)
    barrier = threading.Barrier(2)
    errors: List[BaseException] = []

    def writer(ann_id: str) -> None:
        try:
            barrier.wait(timeout=JOIN_TIMEOUT_S)
            notes_service.add_annotation_and_version(str(books_dir), _new_annotation(ann_id))
        except BaseException as e:  # noqa: BLE001 - surfaced through the errors list below
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in ("n6-t1", "n6-t2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
    assert not any(t.is_alive() for t in threads), "a writer is wedged"
    assert errors == []

    data = _read_raw(books_dir)
    assert {a["id"] for a in data["annotations"]} == {SEED_ID, "n6-t1", "n6-t2"}
    assert data.get(KEY) == STALE_FINGERPRINT


# ---------------------------------------------------------------------------
# N6-10 (structural: every src/ caller holds the notes lock)
# ---------------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "reader3_app"

#: The enclosing functions allowed to call save_annotations. Literal on purpose.
ALLOWED_CALLERS = {
    "refresh_annotations_and_version",
    "add_annotation_and_version",
    "delete_annotation_and_version",
    "update_annotation_and_version",
}


def _is_save_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return name == "save_annotations"


def _is_notes_write_with(node: ast.AST) -> bool:
    if not isinstance(node, ast.With):
        return False
    for item in node.items:
        ctx = item.context_expr
        if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Name) and ctx.func.id == "_notes_write":
            return True
    return False


def _find_calls(tree: ast.AST) -> List[tuple[Optional[str], bool, int]]:
    """(enclosing function, inside a ``with _notes_write(...)``, line) for every save_annotations call."""
    found: List[tuple[Optional[str], bool, int]] = []

    def visit(node: ast.AST, func: Optional[str], locked: bool) -> None:
        if _is_save_call(node):
            found.append((func, locked, node.lineno))  # type: ignore[attr-defined]
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name, False)
            else:
                visit(child, func, locked or _is_notes_write_with(node))

    visit(tree, None, False)
    return found


def test_n6_10_every_src_caller_is_locked_inside_notes_service() -> None:
    files = sorted(SRC_ROOT.rglob("*.py"))
    assert files, f"no source files under {SRC_ROOT}"
    calls: Dict[str, List[tuple[Optional[str], bool, int]]] = {}
    for path in files:
        found = _find_calls(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if found:
            calls[str(path.relative_to(SRC_ROOT))] = found

    assert set(calls) == {"notes_service.py"}, f"save_annotations called outside notes_service: {calls}"
    sites = calls["notes_service.py"]
    assert len(sites) == 4
    for func, locked, line in sites:
        assert func in ALLOWED_CALLERS, f"line {line}: save_annotations called from {func!r}"
        assert locked, f"line {line}: save_annotations in {func} is not inside `with _notes_write(...)`"
