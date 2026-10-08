"""012 WI-1.4: the read-only classifier for legacy pre-012 sibling ``<book>.staging-<pid>`` directories.

``classify_legacy_staging(book_dir) -> LegacyStagingReport`` / ``resolve_legacy_staging(book_dir)``.

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.4" (cases L-01 .. L-11).

Laws (policy-core):
- classify is read-only and its groups are an exact, deterministic partition of the own-named
  leftovers (L-01, L-02: S2/S4);
- resolve is all-or-nothing over the debris and idempotent (L-03 S5, L-04 S3, L-05 S4).

Snapshots here use a local ``lstat``-based walker instead of the shared ``snapshot`` fixture: the
shared one ``os.stat``s every entry, which follows symlinks and raises on a dangling one, and L-02 /
L-11 put symlinks in the tree on purpose. "Identical" still means sha256, size, mtime_ns and inode.
"""
from __future__ import annotations

import errno
import glob
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader3_app import book_format
from reader3_app.book_format import (
    BookFormatError,
    LegacyStagingRefused,
    classify_legacy_staging,
    resolve_legacy_staging,
)

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

Snap = Dict[str, Tuple[Any, ...]]


# --------------------------------------------------------------------------- helpers


def lsnapshot(root: str | os.PathLike[str]) -> Snap:
    """``relpath -> (kind, sha256|target, size, mtime_ns, inode, mode)`` for everything under ``root``.

    Never follows a symlink (records its target text instead) and does not descend into a directory it
    cannot list (the directory's own ``lstat`` is still recorded). ``root`` itself is not recorded, so
    removing a child (which bumps the parent's mtime) shows only as the child's absence.
    """
    snap: Snap = {}

    def walk(path: str, rel: str) -> None:
        try:
            names = sorted(os.listdir(path))
        except PermissionError:
            return
        for name in names:
            full = os.path.join(path, name)
            key = f"{rel}{name}"
            st_ = os.lstat(full)
            if stat.S_ISLNK(st_.st_mode):
                snap[key] = ("link", os.readlink(full), st_.st_size, st_.st_mtime_ns, st_.st_ino, st_.st_mode)
            elif stat.S_ISDIR(st_.st_mode):
                snap[key + "/"] = ("dir", "", 0, st_.st_mtime_ns, st_.st_ino, st_.st_mode)
                walk(full, key + "/")
            else:
                with open(full, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                snap[key] = ("file", digest, st_.st_size, st_.st_mtime_ns, st_.st_ino, st_.st_mode)

    walk(os.fspath(root), "")
    return snap


def _write(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _user_data(book: Path) -> None:
    _write(book / "notes.json", b'{"notes": []}')
    _write(book / "ai_meta.json", b'{"book_uuid": "u"}')
    _write(book / "ai_conversations" / "c1.json", b"{}")


def _debris_with_files(path: Path) -> None:
    _write(path / "book.epub", b"EPUB-new")
    _write(path / "images" / "a.png", b"PNG")
    # A nested *.superseded name (an image) must never count as a parked aside.
    _write(path / "images" / "x.superseded", b"IMG")


def _parked(path: Path) -> None:
    _write(path / "book.pkl", b"PKL-new")
    _write(path / "book.epub.superseded", b"EPUB-old")
    _write(path / "images.superseded" / "a.png", b"PNG-old")


def make_fixture(books: Path, *, parked: bool = True) -> Dict[str, Path]:
    """The WI-1.4 shared fixture under ``books/`` (created with its parents)."""
    books.mkdir(parents=True, exist_ok=True)
    book = books / "sample_data"
    book.mkdir()
    _user_data(book)
    paths = {
        "book": book,
        "111": books / "sample_data.staging-111",
        "222": books / "sample_data.staging-222",
        "333": books / "sample_data.staging-333",
        "lookalike_data": books / "sample_data.staging-1_data",
        "lookalike_backup": books / "sample_data.staging-backup",
        "neighbour": books / "sample_data2_data",
    }
    _debris_with_files(paths["111"])
    paths["222"].mkdir()
    if parked:
        _parked(paths["333"])
    else:
        del paths["333"]
    # Look-alikes deliberately carry parked-looking content: if they were ever classified they would
    # refuse, and if they were ever deleted the user's notes would go with them.
    _user_data(paths["lookalike_data"])
    _parked(paths["lookalike_backup"])
    _user_data(paths["neighbour"])
    return paths


def _s(*paths: Path | str) -> List[str]:
    return [os.path.abspath(p) for p in paths]


def _without(snap: Snap, *prefixes: str) -> Snap:
    return {k: v for k, v in snap.items() if not any(k == p or k.startswith(p + "/") for p in prefixes)}


# --------------------------------------------------------------------------- L-01


def test_l01_mixed_fixture_exact_groups_and_read_only(tmp_path: Path) -> None:
    books = tmp_path / "books"
    p = make_fixture(books)
    before = lsnapshot(tmp_path)

    report = classify_legacy_staging(p["book"])

    assert list(report.debris) == _s(p["111"], p["222"])
    assert list(report.parked) == _s(p["333"])
    assert list(report.uninspectable) == []
    assert lsnapshot(tmp_path) == before


def test_l01_report_is_deterministic(tmp_path: Path) -> None:
    p = make_fixture(tmp_path / "books")
    assert classify_legacy_staging(p["book"]) == classify_legacy_staging(p["book"])


# --------------------------------------------------------------------------- generator (L-02, L-05, L-10)

KINDS_PLAIN = ("empty", "files", "pkl_superseded", "pkl_only", "superseded_only", "regular_file")
KINDS_LINK = ("symlink_dir", "symlink_file", "symlink_dangling")
NON_DIGIT_SUFFIXES = ("backup", "1_data", "12a", "x1", "", "1.5", "-3", " 7", "7 ")


def _suffix() -> st.SearchStrategy[str]:
    return st.one_of(st.integers(min_value=1, max_value=999999).map(str), st.sampled_from(NON_DIGIT_SUFFIXES))


def _materialise(base: Path, entries: List[Tuple[str, str]]) -> Path:
    """Build ``base/books/bk_data`` plus one ``bk_data.staging-<suffix>`` sibling per entry."""
    books = base / "books"
    books.mkdir(parents=True, exist_ok=True)
    book = books / "bk_data"
    book.mkdir()
    _user_data(book)
    outside = base / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    _parked(outside / "dir")
    _write(outside / "file.txt", b"outside")
    for suffix, kind in entries:
        sib = books / f"bk_data.staging-{suffix}"
        if kind == "empty":
            sib.mkdir()
        elif kind == "files":
            _debris_with_files(sib)
        elif kind == "pkl_superseded":
            _parked(sib)
        elif kind == "pkl_only":
            _write(sib / "book.pkl", b"PKL")
            _write(sib / "book.epub", b"EPUB")
        elif kind == "superseded_only":
            _write(sib / "book.epub.superseded", b"EPUB-old")
        elif kind == "regular_file":
            _write(sib, b"not a directory")
        elif kind == "symlink_dir":
            os.symlink(outside / "dir", sib)
        elif kind == "symlink_file":
            os.symlink(outside / "file.txt", sib)
        elif kind == "symlink_dangling":
            os.symlink(outside / "nothing-here", sib)
        else:  # pragma: no cover - generator and builder share KINDS
            raise AssertionError(kind)
    return book


def _expected(book: Path, entries: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {"debris": [], "parked": [], "uninspectable": []}
    for suffix, kind in entries:
        if not (suffix.isascii() and suffix.isdigit()):
            continue
        path = os.path.abspath(f"{book}.staging-{suffix}")
        if kind in ("regular_file",) + KINDS_LINK:
            groups["uninspectable"].append(path)
        elif kind == "pkl_superseded":
            groups["parked"].append(path)
        else:
            groups["debris"].append(path)
    return {k: sorted(v) for k, v in groups.items()}


def _groups(report: book_format.LegacyStagingReport) -> Dict[str, List[str]]:
    return {"debris": list(report.debris), "parked": list(report.parked), "uninspectable": list(report.uninspectable)}


entries_strategy = st.lists(
    st.tuples(_suffix(), st.sampled_from(KINDS_PLAIN + KINDS_LINK)), min_size=0, max_size=6, unique_by=lambda e: e[0]
)


# --------------------------------------------------------------------------- L-02


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=entries_strategy)
def test_l02_partition_property_over_generated_leftovers(entries: List[Tuple[str, str]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = _materialise(Path(tmp), entries)
        before = lsnapshot(tmp)

        report = classify_legacy_staging(book)

        expected = _expected(book, entries)
        assert _groups(report) == expected
        # Exact partition: no own-named entry is in two groups, and none is missing.
        flat = [*report.debris, *report.parked, *report.uninspectable]
        assert len(flat) == len(set(flat))
        assert sorted(flat) == sorted(sum(expected.values(), []))
        assert lsnapshot(tmp) == before


@pytest.mark.parametrize("name", ["sample_data.staging-\u0663", "sample_data.staging-\u00b2",
                                  "sample_data.staging-1.staging-2"])
def test_l02b_only_exact_ascii_pid_names_are_own_staging(tmp_path: Path, name: str) -> None:
    """Added case (not in the matrix): the own-name rule is ``<book>.staging-<ASCII digits>`` exactly.

    A real staging dir always ends in ``os.getpid()``, so a non-ASCII digit (``str.isdigit`` is true for
    U+0663 and U+00B2) or a second ``.staging-`` segment cannot be ours; it is ignored, never deleted.
    Narrower than reader3's ``rsplit(...).isdigit()``, which is why L-10's generator avoids these names.
    """
    p = make_fixture(tmp_path / "books", parked=False)
    stranger = tmp_path / "books" / name
    _debris_with_files(stranger)
    before = lsnapshot(stranger)

    report = classify_legacy_staging(p["book"])
    assert os.path.abspath(stranger) not in [*report.debris, *report.parked, *report.uninspectable]

    resolve_legacy_staging(p["book"])
    assert lsnapshot(stranger) == before
    assert not os.path.lexists(p["111"])


# --------------------------------------------------------------------------- L-03


def test_l03_resolver_debris_only_removes_exactly_the_debris_and_is_idempotent(tmp_path: Path) -> None:
    books = tmp_path / "books"
    p = make_fixture(books, parked=False)
    before = lsnapshot(books)

    resolve_legacy_staging(p["book"])

    assert not os.path.lexists(p["111"])
    assert not os.path.lexists(p["222"])
    after_first = lsnapshot(books)
    assert after_first == _without(before, "sample_data.staging-111", "sample_data.staging-222")

    resolve_legacy_staging(p["book"])

    assert lsnapshot(books) == after_first


# --------------------------------------------------------------------------- L-04


def test_l04_parked_plus_debris_refuses_with_recovery_lines_and_deletes_nothing(tmp_path: Path) -> None:
    books = tmp_path / "books"
    p = make_fixture(books)
    before = lsnapshot(tmp_path)

    with pytest.raises(LegacyStagingRefused) as excinfo:
        resolve_legacy_staging(p["book"])

    assert isinstance(excinfo.value, BookFormatError)
    message = str(excinfo.value)
    book_abs = os.path.abspath(p["book"])
    staging = os.path.abspath(p["333"])
    assert f"{staging}/book.epub.superseded -> {book_abs}/book.epub" in message
    assert f"{staging}/images.superseded -> {book_abs}/images" in message
    assert book_abs in message
    assert lsnapshot(tmp_path) == before
    assert os.path.isdir(p["111"]) and os.path.isdir(p["222"])


# --------------------------------------------------------------------------- L-05


def _parked_and_debris() -> st.SearchStrategy[List[Tuple[str, str]]]:
    digits = st.integers(min_value=1, max_value=999999).map(str)
    return st.tuples(
        st.lists(st.tuples(digits, st.just("pkl_superseded")), min_size=1, max_size=3),
        st.lists(st.tuples(digits, st.sampled_from(("empty", "files", "pkl_only", "superseded_only"))), min_size=1,
                 max_size=3),
    ).map(lambda pair: pair[0] + pair[1]).filter(lambda es: len({s for s, _ in es}) == len(es))


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=_parked_and_debris())
def test_l05_classification_completes_before_any_deletion(entries: List[Tuple[str, str]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = _materialise(Path(tmp), entries)
        before = lsnapshot(tmp)

        with pytest.raises(LegacyStagingRefused):
            resolve_legacy_staging(book)

        assert lsnapshot(tmp) == before


# --------------------------------------------------------------------------- L-06


@pytest.mark.skipif(IS_ROOT, reason="root bypasses directory permissions")
def test_l06_uninspectable_leftover_refuses_and_names_it(tmp_path: Path) -> None:
    books = tmp_path / "books"
    p = make_fixture(books, parked=False)
    locked = books / "sample_data.staging-444"
    _write(locked / "book.pkl", b"PKL")
    locked.chmod(0)
    try:
        before = lsnapshot(tmp_path)

        report = classify_legacy_staging(p["book"])
        assert list(report.uninspectable) == _s(locked)
        assert list(report.debris) == _s(p["111"], p["222"])
        assert list(report.parked) == []

        with pytest.raises(LegacyStagingRefused) as excinfo:
            resolve_legacy_staging(p["book"])
        message = str(excinfo.value)
        assert os.path.abspath(locked) in message
        assert errno.errorcode[errno.EACCES] in message
        assert lsnapshot(tmp_path) == before
        assert os.path.isdir(p["111"]) and os.path.isdir(p["222"])
    finally:
        locked.chmod(0o755)


# --------------------------------------------------------------------------- L-07


def _vanishing_listing(monkeypatch: pytest.MonkeyPatch, victim: Path) -> List[str]:
    """Passthrough over ``os.listdir`` / ``os.scandir`` that really deletes ``victim`` just before listing it."""
    real_listdir, real_scandir, real_rmtree = os.listdir, os.scandir, shutil.rmtree
    fired: List[str] = []

    def maybe_vanish(path: Any) -> None:
        if isinstance(path, int) or path is None:
            return
        if os.path.abspath(os.fspath(path)) == os.path.abspath(victim) and not fired:
            fired.append(os.fspath(path))
            monkeypatch.setattr(os, "listdir", real_listdir)
            monkeypatch.setattr(os, "scandir", real_scandir)
            real_rmtree(victim)
            monkeypatch.setattr(os, "listdir", listdir)
            monkeypatch.setattr(os, "scandir", scandir)

    def listdir(path: Any = ".") -> Any:
        maybe_vanish(path)
        return real_listdir(path)

    def scandir(path: Any = ".") -> Any:
        maybe_vanish(path)
        return real_scandir(path)

    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(os, "scandir", scandir)
    return fired


def test_l07_leftover_vanishing_mid_scan_is_skipped_by_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = make_fixture(tmp_path / "books", parked=False)
    fired = _vanishing_listing(monkeypatch, p["222"])

    report = classify_legacy_staging(p["book"])

    assert fired, "the race passthrough never fired: the classifier did not list the leftover"
    assert list(report.debris) == _s(p["111"])
    assert list(report.uninspectable) == []
    assert list(report.parked) == []


def test_l07_leftover_vanishing_mid_scan_does_not_fail_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = make_fixture(tmp_path / "books", parked=False)
    fired = _vanishing_listing(monkeypatch, p["222"])

    resolve_legacy_staging(p["book"])

    assert fired
    assert not os.path.lexists(p["111"])
    assert not os.path.lexists(p["222"])
    assert os.path.isdir(p["book"]) and os.path.isfile(p["book"] / "notes.json")


# --------------------------------------------------------------------------- L-08


def test_l08_glob_metacharacters_in_book_name(tmp_path: Path) -> None:
    books = tmp_path / "books"
    books.mkdir(parents=True)
    book = books / "a[1]*_data"
    book.mkdir()
    _user_data(book)
    own = books / "a[1]*_data.staging-7"
    _debris_with_files(own)
    # Every neighbour below matches the UNescaped pattern ``a[1]*_data.staging-*``.
    neighbours = [books / "a1_data.staging-7", books / "a1x_data.staging-8", books / "a1_y_data.staging-9"]
    for n in neighbours:
        _debris_with_files(n)
    (books / "a1_data").mkdir()
    assert sorted(glob.glob(f"{book}.staging-*")) != [str(own)]  # the hazard is real
    before = lsnapshot(books)

    report = classify_legacy_staging(book)
    assert list(report.debris) == _s(own)
    assert list(report.parked) == [] and list(report.uninspectable) == []

    resolve_legacy_staging(book)

    assert not os.path.lexists(own)
    assert lsnapshot(books) == _without(before, own.name)
    for n in neighbours:
        assert os.path.isfile(n / "book.epub")


# --------------------------------------------------------------------------- L-09


def test_l09_trailing_slash_and_relative_paths_give_the_same_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    books = tmp_path / "books"
    p = make_fixture(books)
    expected = {"debris": _s(p["111"], p["222"]), "parked": _s(p["333"]), "uninspectable": []}

    assert _groups(classify_legacy_staging(str(p["book"]) + "/")) == expected

    monkeypatch.chdir(books)
    assert _groups(classify_legacy_staging("sample_data")) == expected
    assert _groups(classify_legacy_staging("./sample_data/")) == expected


# --------------------------------------------------------------------------- L-10 (delete in WI-3)

# delete in WI-3: this parity test pins the new classifier to reader3's legacy helpers, which WI-3
# deletes together with this test. Restricted to non-symlink kinds: reader3's helpers predate L-11
# (they follow a symlinked leftover, and skip a dangling one as "vanished").


def _reader3_groups(book: Path) -> Dict[str, Any]:
    from reader3_app import reader3

    normalized = os.path.normpath(os.fspath(book))
    groups: Dict[str, Any] = {"debris": [], "parked": [], "uninspectable": [], "asides": []}
    for leftover in sorted(glob.glob(f"{glob.escape(normalized)}.staging-*")):
        if not reader3._is_own_staging_name(leftover):
            continue
        try:
            asides = reader3._parked_asides(leftover)
        except FileNotFoundError:
            continue
        except OSError:
            groups["uninspectable"].append(os.path.abspath(leftover))
            continue
        if asides:
            groups["parked"].append(os.path.abspath(leftover))
            groups["asides"].append((os.path.abspath(leftover), tuple(asides)))
        else:
            groups["debris"].append(os.path.abspath(leftover))
    return groups


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    entries=st.lists(
        st.tuples(_suffix(), st.sampled_from(KINDS_PLAIN)), min_size=0, max_size=6, unique_by=lambda e: e[0]
    )
)
def test_l10_parity_with_reader3_helpers(entries: List[Tuple[str, str]]) -> None:  # delete in WI-3
    with tempfile.TemporaryDirectory() as tmp:
        book = _materialise(Path(tmp), entries)

        report = classify_legacy_staging(book)
        legacy = _reader3_groups(book)

        assert _groups(report) == {k: legacy[k] for k in ("debris", "parked", "uninspectable")}
        assert list(report.asides) == legacy["asides"]


# --------------------------------------------------------------------------- L-11


def _link_to_outside_dir(outside: Path) -> Path:
    target = outside / "outside"
    _parked(target)
    _write(target / "keep.txt", b"keep")
    return target


def _link_to_outside_file(outside: Path) -> Path:
    target = outside / "outside-file.txt"
    _write(target, b"outside file")
    return target


def _link_dangling(outside: Path) -> Path:
    outside.mkdir(parents=True, exist_ok=True)
    return outside / "does-not-exist"


@pytest.mark.parametrize(
    "make_target",
    [_link_to_outside_dir, _link_to_outside_file, _link_dangling],
    ids=["a-dir-looks-parked", "b-file", "c-dangling"],
)
def test_l11_symlinked_staging_sibling_is_uninspectable_and_never_followed(
    tmp_path: Path, make_target: Callable[[Path], Path]
) -> None:
    books = tmp_path / "books"
    p = make_fixture(books, parked=False)
    shutil.rmtree(p["222"])
    outside = tmp_path / "elsewhere"
    target = make_target(outside)
    link = books / "sample_data.staging-555"
    os.symlink(target, link)
    before = lsnapshot(tmp_path)

    report = classify_legacy_staging(p["book"])
    assert list(report.uninspectable) == _s(link)
    assert list(report.parked) == []
    assert list(report.debris) == _s(p["111"])

    with pytest.raises(LegacyStagingRefused) as excinfo:
        resolve_legacy_staging(p["book"])
    assert os.path.abspath(link) in str(excinfo.value)

    assert os.path.islink(link)
    assert os.readlink(link) == str(target)
    assert os.path.isdir(p["111"])
    assert lsnapshot(tmp_path) == before


# ---------------------------------------------------------- WI-1.10 B6: refusal text for the unsettled shapes


def test_wi110_b6_unknown_aside_is_listed_for_inspection_and_kept(tmp_path: Path) -> None:
    """B6 (failure, S3, Level 1): an aside this program never parks is not mapped; its leftover is kept."""
    books = tmp_path / "books"
    book = books / "sample_data"
    book.mkdir(parents=True)
    leftover = books / "sample_data.staging-55"
    _write(leftover / "book.pkl", b"PKL-new")
    _write(leftover / "notes.json.superseded", b"[]")
    before = lsnapshot(tmp_path)
    with pytest.raises(LegacyStagingRefused) as excinfo:
        resolve_legacy_staging(book)
    message = str(excinfo.value)
    aside = os.path.join(os.path.abspath(leftover), "notes.json.superseded")
    assert f"    {aside} is not a file this program parks; inspect it by hand" in message.splitlines()
    assert f"    keep {os.path.abspath(leftover)} until resolved" in message.splitlines()
    assert "then delete" not in message
    assert " -> " not in message
    assert lsnapshot(tmp_path) == before


@pytest.mark.parametrize("live_present", [True, False])
def test_wi110_b6_live_file_is_removed_before_the_aside_moves_back(tmp_path: Path, live_present: bool) -> None:
    """B6 (failure, S3, Level 1): with book.epub live, `remove <book>/book.epub` precedes the move line."""
    books = tmp_path / "books"
    book = books / "sample_data"
    book.mkdir(parents=True)
    if live_present:
        _write(book / "book.epub", b"EPUB-mixed")
    leftover = books / "sample_data.staging-56"
    _write(leftover / "book.pkl", b"PKL-new")
    _write(leftover / "book.epub.superseded", b"EPUB-old")
    before = lsnapshot(tmp_path)
    with pytest.raises(LegacyStagingRefused) as excinfo:
        resolve_legacy_staging(book)
    lines = str(excinfo.value).splitlines()
    live = os.path.join(os.path.abspath(book), "book.epub")
    move = f"    {os.path.join(os.path.abspath(leftover), 'book.epub.superseded')} -> {live}"
    remove = f"    remove {live}"
    assert move in lines
    if live_present:
        assert remove in lines and lines.index(remove) == lines.index(move) - 1
    else:
        assert remove not in lines
    assert f"    then delete {os.path.abspath(leftover)}" in lines
    assert lsnapshot(tmp_path) == before
