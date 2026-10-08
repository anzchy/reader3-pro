"""012 WI-1.7: the crash-injection matrix (gate 3), in-process raise kind, plus the matrix definition.

Matrix: ``.claude/tdd-guardian/tests-20261008-152720.md`` section "WI-1.7" (X-01 .. X-04). The SIGKILL kind
(Y-01 .. Y-05, ``test_kill_cells``) is WI-1.8 and reuses the table, the rules and the judges below.

Law: snapshot consistency at every crash point, plus convergence after a re-run. Assertion levels are the
policy-core Level 1-7 scale; spec levels are S1-S6 (not the L1-L4 legend of ``tests/unit/conftest.py``).

Gate-3 table
------------
Rows are the hook points of one uninterrupted ``publish(make_inputs("v2"))`` in publish order. Columns are
the scenarios of ``book_format_helpers.setup_scenario``. A cell is the number of times that run reaches the
point (``.`` = never). ``POINTS[s]`` is read from this table: walk the rows in order; a step whose ``before``
and ``after`` rows carry count k contributes k consecutive ``(before, after)`` pairs. Each (scenario, idx) of
``POINTS[s]`` is one cell **per injection kind**: raise (WI-1.7, ``test_raise_cells``) and SIGKILL (WI-1.8,
``test_kill_cells``). Cell ids are ``{scenario}-{idx}-{step}-{when}``. A point counts as committed iff its
index is at or after ``("p8","after")``. ``test_matrix_docstring_matches_reached_points`` re-derives the table
from dry runs, so an undocumented hook or a missing cell fails.

<!-- gate3-table -->
| point              | S0 | S0u | S1 | S2 | S3 | S4 | S5 |
|--------------------|----|-----|----|----|----|----|----|
| p0 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p0 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p0.legacy before   | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p0.legacy after    | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| gc.validate before | 1  | 1   | 1  | 1  | 1  | 1  | .  |
| gc.validate after  | 1  | 1   | 1  | 1  | 1  | 1  | .  |
| gc.delete before   | .  | .   | 1  | .  | .  | 2  | .  |
| gc.delete after    | .  | .   | 1  | .  | .  | 2  | .  |
| gc.tmp before      | .  | .   | .  | .  | .  | 1  | .  |
| gc.tmp after       | .  | .   | .  | .  | .  | 1  | .  |
| p1 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p1 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p2 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p2 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p3 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p3 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p4 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p4 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p5 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p5 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p6 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p6 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p7 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p7 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p8 before          | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p8 after           | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p8.fsync before    | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
| p8.fsync after     | 1  | 1   | 1  | 1  | 1  | 1  | 1  |
<!-- /gate3-table -->

Per kind: S0 24, S0u 24, S1 26, S2 24, S3 24, S4 30, S5 22 cells (174). ``g_new[s]`` is 1, 1, 3, 2, 1, 10 and
10 for S0 ... S5 (``book_format_helpers.G_NEW``; S4 = 10 per the pinned law 2). S0 is published with
``create=True`` (the book directory is absent), every other scenario with ``create=False``.

Scenarios: S0 absent; S0u user data only; S1 previous plus current gen (``gen/1``, ``gen/2``); S2 one gen and
no images before; S3 legacy flat files, no manifest; S4 = S1 plus an orphan ``gen/9`` newer than current, a
stale ``manifest.json.tmp`` and a sibling debris staging dir; S5 = S1 with ``gen/2/images/cover.png`` deleted
plus an orphan ``gen/9`` (a repairable corrupt start).

Judgment rules (copied from the matrix)
---------------------------------------
- **① State membership.**
  - For S0-S4: ``classify(full=True) ∈ {missing, valid}``.
  - **For S5:** ``classify(full=True) ∈ {corrupt, valid}``, where ``corrupt`` is the *starting* state, which
    pre-commit cells legitimately observe. No third state ever appears, and S5 never classifies ``missing``.
- **② No mixed tags.**
  - Before commit:
    - S0/S0u: ``missing``;
    - S3: ``missing``, with the flat files identical;
    - S1/S2/S4: ``valid`` with v1 everywhere;
    - **S5:** ``corrupt``, **with unchanged bytes**: every path that existed at the start (manifest,
      ``gen/1/**``, ``gen/2/**``, ``gen/9/**``, user data) is identical. The only new paths allowed are
      ``gen/10/**`` and ``manifest.json.tmp``; in raise cells after cleanup, neither is allowed.
  - At or after commit: ``valid`` with v2 for every scenario. **For S5 additionally**, ``g == 10``, and
    ``gen/1``, ``gen/2`` and ``gen/9`` are still present and identical, because repair never GCs.
- **②′ Per-point leftover content (A11).** The reference is a fresh run of the same scenario with an
  uninterrupted ``publish(v2)``. In the kill kind it is checked on the post-kill tree. In the raise kind the
  injecting hook checks the live tree **before** it raises, because cleanup removes the residue afterwards.
  For a crash at point P, with ``G = gen/{g_new[s]}``:
  - P ≥ ``("p1","after")``: ``G`` exists and is a real directory (not a symlink);
  - P ≥ ``("p2","after")``: ``G/chapters.jsonl`` exists with size equal to the reference's
    ``chapters_size_bytes`` and the reference sha;
  - P ≥ ``("p3","after")``: ``G/book.epub``, ``G/book.pkl`` and every ``G/images/*`` exist with bytes equal to
    the reference (``b"EPUB-v2"``, ``b"PKL-v2"``, ``b"PNG-v2"``, ``b"JPG-v2"``);
  - P ≥ ``("p5","after")`` and before commit: ``manifest.json.tmp`` exists,
    ``manifest_from_bytes(tmp).generation == g_new[s]``, and its bytes **equal the reference committed
    ``manifest.json`` bytes**;
  - P < ``("p1","after")`` (including all ``gc.*`` and ``p0*`` points): ``G`` does not exist.
- **③ Convergence.** After the crash, re-run ``publish(v2)`` and compare with a reference run (a fresh
  scenario plus an uninterrupted ``publish(v2)``):
  - full classification is ``valid``;
  - the manifests are equal modulo ``generation``;
  - the current-gen tree bytes are equal (relative path plus sha);
  - there are at most 2 canonical gens, no tmp, and no gen above current;
  - closed-list and legacy flat files are identical to the pre-crash snapshot;
  - the retained previous gen's contents are not compared.
- **For S5, ③ has two steps.**
  - The re-run must succeed, with full ``valid`` and v2.
    - A crash before commit leaves the book corrupt, so the re-run is again a repair. It keeps every
      pre-existing ``gen/*``, including any partial ``gen/10`` residue from a kill, and picks
      ``g = max(on-disk) + 1``.
    - A crash after commit leaves the book valid, so the re-run takes the normal path with GC.
  - A **follow-up** ``publish(v2)`` must then satisfy the standard ③ definition above. The S5 reference is
    fresh S5, then ``publish(v2)``, then ``publish(v2)``.

Implementation notes for the raise kind (not part of the copied rules):
- "Identical" is the ``book_format_helpers.snapshot`` (``lstat``) equality: sha, size, mtime_ns, inode and
  mode for files. For the S5 "unchanged bytes" rule the directory mtimes of the book root and ``gen/`` are
  exempt (creating then removing ``gen/10`` and the tmp touches them); their inodes still must match.
- The injected exception rotates over ``INJECTED_KINDS`` by ``idx`` (``KeyboardInterrupt``, ``OSError(EIO)``,
  the out-of-memory error, ``InjectedCrash``), one kind per cell, so every kind lands in every scenario without
  multiplying the cell count. The kill kind is WI-1.8's real ``SIGKILL``.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

import test_book_format_publish as pub
from book_format_helpers import (
    G_NEW,
    INJECTED_KINDS,
    PREV_TAG,
    SCENARIOS,
    HookRecorder,
    Point,
    add_debris,
    add_stale_tmp,
    assert_valid_with,
    canonical_gens,
    dry_run_points,
    install_hooks,
    make_inputs,
    setup_scenario,
    snapshot,
    sub,
    write_file,
)
from reader3_app import book_format
from reader3_app.book_format import (
    CHAPTERS,
    GEN_DIR,
    MANIFEST,
    MANIFEST_TMP,
    PUBLISH_HOOKS,
    BookCorrupt,
    BookManifest,
    classify,
    manifest_from_bytes,
    validate_stat,
)

COMMIT: Point = ("p8", "after")

# =========================================================================== the matrix definition


def parse_gate3_table(doc: str) -> tuple[list[Point], dict[str, list[Point]]]:
    """(the table's rows in order, ``POINTS[s]`` per scenario column) from the module docstring table."""
    block = doc.split("<!-- gate3-table -->", 1)[1].split("<!-- /gate3-table -->", 1)[0]
    lines = [ln.strip() for ln in block.strip().splitlines()]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    columns = header[1:]
    rows: list[Point] = []
    counts: dict[str, list[int]] = {c: [] for c in columns}
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        step, when = cells[0].split()
        rows.append((step, when))
        for col, cell in zip(columns, cells[1:]):
            counts[col].append(0 if cell == "." else int(cell))
    points: dict[str, list[Point]] = {}
    for col in columns:
        seq: list[Point] = []
        i = 0
        while i < len(rows):
            step, when = rows[i]
            k = counts[col][i]
            if when == "before" and i + 1 < len(rows) and rows[i + 1] == (step, "after"):
                if k != counts[col][i + 1]:
                    raise ValueError(f"{col}: {step} before/after counts differ")
                seq.extend([(step, "before"), (step, "after")] * k)
                i += 2
            else:
                seq.extend([(step, when)] * k)
                i += 1
        points[col] = seq
    return rows, points


TABLE_ROWS, POINTS = parse_gate3_table(__doc__ or "")
"""The documented matrix; every parametrised cell below is derived from it, nothing from a live run."""

RAISE_CELLS: list[tuple[str, int, str, str]] = [
    (s, idx, step, when) for s in SCENARIOS for idx, (step, when) in enumerate(POINTS[s])
]


def cell_id(s: str, idx: int, step: str, when: str) -> str:
    return f"{s}-{idx}-{step}-{when}"


RAISE_CELL_IDS: list[str] = [cell_id(*c) for c in RAISE_CELLS]
KIND_ORDER: tuple[str, ...] = tuple(INJECTED_KINDS)


def publish_kw(s: str) -> dict[str, Any]:
    return {"create": s == "S0"}


def commit_idx(s: str) -> int:
    return POINTS[s].index(COMMIT)


# =========================================================================== references and judges


@dataclass(frozen=True)
class Reference:
    """A fresh scenario plus an uninterrupted ``publish(v2)`` (``once``); for S5 also the follow-up (``conv``)."""

    manifest_bytes: bytes
    manifest: BookManifest
    gen_bytes: dict[str, bytes]
    conv_manifest: BookManifest
    conv_tree: dict[str, tuple[Any, ...]]


def gen_tree(gen_dir: Path) -> dict[str, tuple[Any, ...]]:
    """Relative path -> (kind, sha / target) of a generation: the byte content, never inode or mtime."""
    out: dict[str, tuple[Any, ...]] = {}
    for rel, entry in snapshot(gen_dir).items():
        if rel in (".", "./"):
            continue
        out[rel] = (entry[0],) if entry[0] == "dir" else entry[:2]
    return out


def build_reference(s: str, base: Path) -> Reference:
    book = setup_scenario(s, base)
    g = book_format.publish(book, make_inputs("v2"), **publish_kw(s))
    assert g == G_NEW[s]
    raw = (book / MANIFEST).read_bytes()
    gen_dir = book / GEN_DIR / str(g)
    gen_bytes = {
        os.path.relpath(os.path.join(d, f), gen_dir): Path(d, f).read_bytes()
        for d, _dirs, files in os.walk(gen_dir) for f in files
    }
    if s == "S5":
        g = book_format.publish(book, make_inputs("v2"))
    conv = validate_stat(book)
    return Reference(raw, manifest_from_bytes(raw), gen_bytes, conv, gen_tree(book / GEN_DIR / str(g)))


@pytest.fixture(scope="module")
def references(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Reference]:
    cache: dict[str, Reference] = {}

    def get(s: str) -> Reference:
        if s not in cache:
            cache[s] = build_reference(s, tmp_path_factory.mktemp(f"ref-{s}"))
        return cache[s]

    return get


def leftover_problems(book: Path, s: str, idx: int, ref: Reference) -> list[str]:
    """Rule ②′ on the live tree at the crash point ``POINTS[s][idx]``; an empty list is a pass."""
    pts = POINTS[s]
    g_new = G_NEW[s]
    gen = book / GEN_DIR / str(g_new)
    tmp = book / MANIFEST_TMP
    probs: list[str] = []
    if idx < pts.index(("p1", "after")):
        if os.path.lexists(gen):
            probs.append(f"{gen} exists before p1.after")
        return probs
    try:
        gst = os.lstat(gen)
    except FileNotFoundError:
        return [f"{gen} missing at/after p1.after"]
    if not stat.S_ISDIR(gst.st_mode):
        return [f"{gen} is not a real directory"]
    if idx >= pts.index(("p2", "after")):
        ch = gen / CHAPTERS
        data = ch.read_bytes() if ch.is_file() else None
        if data is None or len(data) != ref.manifest.chapters_size_bytes:
            probs.append(f"{CHAPTERS} size differs from the reference")
        elif data != ref.gen_bytes[CHAPTERS]:
            probs.append(f"{CHAPTERS} sha differs from the reference")
    if idx >= pts.index(("p3", "after")):
        files = {
            os.path.relpath(os.path.join(d, f), gen) for d, _dirs, fs in os.walk(gen) for f in fs
        }
        if files != set(ref.gen_bytes):
            probs.append(f"gen files {sorted(files)} != reference {sorted(ref.gen_bytes)}")
        for rel, want in ref.gen_bytes.items():
            if (gen / rel).is_file() and (gen / rel).read_bytes() != want:
                probs.append(f"{rel} bytes differ from the reference")
    if pts.index(("p5", "after")) <= idx < commit_idx(s):
        if not os.path.isfile(tmp):
            probs.append("manifest.json.tmp missing at/after p5.after")
        else:
            raw = tmp.read_bytes()
            if manifest_from_bytes(raw).generation != g_new:
                probs.append("tmp generation differs from g_new")
            if raw != ref.manifest_bytes:
                probs.append("tmp bytes differ from the reference committed manifest")
    if idx >= commit_idx(s):
        if (book / MANIFEST).read_bytes() != ref.manifest_bytes:
            probs.append("committed manifest bytes differ from the reference")
        if os.path.lexists(tmp):
            probs.append("tmp still present after commit")
    return probs


def closed_list(book: Path) -> dict[str, tuple[Any, ...]]:
    """Closed-list user data plus the stray root file (``pub.user_snap``) and, for S3, the legacy flat files."""
    return {**pub.user_snap(book), **pub.legacy_snap(book)}


def s5_start_paths(snap: dict[str, tuple[Any, ...]]) -> dict[str, tuple[Any, ...]]:
    """An S5 snapshot with the root and ``gen/`` directory mtimes dropped (their inodes are kept)."""
    out = dict(snap)
    for key in ("./", f"{GEN_DIR}/"):
        if key in out:
            out[key] = (out[key][0], out[key][-1])
    return out


def assert_converged(book: Path, ref: Reference, start_closed: dict[str, tuple[Any, ...]]) -> None:
    """Rule ③ (the standard form)."""
    assert classify(book, full=True) == "valid"
    m = validate_stat(book)
    assert dataclasses.replace(m, generation=0) == dataclasses.replace(ref.conv_manifest, generation=0)
    assert gen_tree(book / GEN_DIR / str(m.generation)) == ref.conv_tree
    gens = canonical_gens(book)
    assert len(gens) <= 2, gens
    assert max(gens) == m.generation, gens
    assert not os.path.lexists(book / MANIFEST_TMP)
    assert closed_list(book) == start_closed


# =========================================================================== X-01 raise cells


@pytest.mark.parametrize("s,idx,step,when", RAISE_CELLS, ids=RAISE_CELL_IDS)
def test_raise_cells(
    tmp_path: Path, references: Callable[[str], Reference], s: str, idx: int, step: str, when: str
) -> None:
    """X-01: raise at the idx-th hook call; judge ①②②′ immediately and ③ after re-running. Level 1+2, S5."""
    ref = references(s)
    book = setup_scenario(s, tmp_path)
    start = snapshot(book)
    start_closed = closed_list(book)
    kind = KIND_ORDER[idx % len(KIND_ORDER)]
    committed = idx >= commit_idx(s)
    g_new = G_NEW[s]

    rec = HookRecorder(crash_at=idx, exc=INJECTED_KINDS[kind])
    verdict: dict[str, list[str]] = {}

    def judge() -> None:
        if len(rec.calls) - 1 == idx:
            verdict["leftover"] = leftover_problems(book, s, idx, ref)

    rec.on(step, when, judge)
    with pytest.raises(BaseException) as ei:
        with pytest.MonkeyPatch.context() as mp:
            install_hooks(mp, rec)
            book_format.publish(book, make_inputs("v2"), **publish_kw(s))

    # The crash landed exactly where the cell says, and it is the injected exception that propagated.
    assert rec.raised is not None and ei.value is rec.raised, (kind, rec.calls)
    assert rec.calls[-1] == (step, when) and len(rec.calls) == idx + 1, rec.calls
    # ②′, evaluated by the injecting hook on the live tree before it raised.
    assert verdict.get("leftover") == [], verdict

    # ① state membership.
    state = classify(book, full=True)
    allowed = {"corrupt", "valid"} if s == "S5" else {"missing", "valid"}
    assert state in allowed, state

    # ② no mixed tags.
    now = snapshot(book)
    if committed:
        m = assert_valid_with(book, "v2")
        assert m.generation == g_new
        if s == "S5":
            for g_old in ("1", "2", "9"):
                prefix = f"{GEN_DIR}/{g_old}"
                assert sub(now, prefix) and sub(now, prefix) == sub(start, prefix)
    else:
        assert not os.path.lexists(book / GEN_DIR / str(g_new))
        if idx >= POINTS[s].index(("p1", "before")):
            assert not os.path.lexists(book / MANIFEST_TMP)
        if s in ("S0", "S0u", "S3"):
            assert state == "missing"
        elif s == "S5":
            assert state == "corrupt"
            assert s5_start_paths(now) == s5_start_paths(start)
        else:
            assert state == "valid"
            assert_valid_with(book, PREV_TAG[s])
            assert sub(now, MANIFEST) == sub(start, MANIFEST)
            prev = f"{GEN_DIR}/{validate_stat(book).generation}"
            assert sub(now, prev) == sub(start, prev)
    # Closed-list root data (and S3's legacy flat files) identical in every cell.
    assert closed_list(book) == start_closed

    # ③ convergence after a re-run with the same inputs and no cleanup in between.
    g_rerun = book_format.publish(book, make_inputs("v2"), **publish_kw(s))
    if s == "S5":
        assert_valid_with(book, "v2")
        after_rerun = snapshot(book)
        if committed:
            assert g_rerun == g_new + 1
        else:
            assert g_rerun == g_new  # a repair again: max(on-disk) + 1 with gen/10 cleaned up
            for g_old in ("1", "2", "9"):
                prefix = f"{GEN_DIR}/{g_old}"
                assert sub(after_rerun, prefix) == sub(start, prefix)
        assert closed_list(book) == start_closed
        book_format.publish(book, make_inputs("v2"))
    assert_converged(book, ref, start_closed)


# =========================================================================== X-02 / X-03 meta-tests


def _fresh_dry_runs(base: Path) -> dict[str, list[Point]]:
    return {s: dry_run_points(s, base / f"dry-{s}", **publish_kw(s)) for s in SCENARIOS}


def test_matrix_docstring_matches_reached_points(tmp_path: Path) -> None:
    """X-02: the docstring table equals what fresh dry runs reach, row for row and cell for cell. Level 1, S2."""
    reached = _fresh_dry_runs(tmp_path)
    union = {p for pts in reached.values() for p in pts}
    assert set(TABLE_ROWS) == union
    assert len(TABLE_ROWS) == len(set(TABLE_ROWS)), "a documented row appears twice"
    assert list(POINTS) == list(SCENARIOS), "one column per scenario, S5 included"
    for s in SCENARIOS:
        assert set(POINTS[s]) == set(reached[s]), s
        assert POINTS[s] == reached[s], s
    for step in PUBLISH_HOOKS:
        assert (step, "before") in union and (step, "after") in union, step
    assert {step for step, _ in union} == set(PUBLISH_HOOKS)


def _assert_ids_cover_reached(ids: list[str], reached: dict[str, list[Point]]) -> None:
    expected = [cell_id(s, idx, step, when) for s in SCENARIOS for idx, (step, when) in enumerate(reached[s])]
    assert len(ids) == len(set(ids)), "duplicate cell id"
    assert sorted(ids) == sorted(expected)
    assert len(ids) == sum(len(p) for p in reached.values())
    pattern = re.compile(r"(S0u|S[0-5])-(\d+)-([a-z0-9.]+)-(before|after)")
    per_cell = {}
    for i in ids:
        mt = pattern.fullmatch(i)
        assert mt is not None, i
        per_cell[(mt.group(1), int(mt.group(2)))] = (mt.group(3), mt.group(4))
    for s in SCENARIOS:
        for idx, p in enumerate(reached[s]):
            assert per_cell[(s, idx)] == p, (s, idx)


def _parametrised_ids(fn: Callable[..., Any]) -> list[str]:
    marks = [m for m in getattr(fn, "pytestmark", []) if m.name == "parametrize"]
    assert len(marks) == 1
    ids = marks[0].kwargs["ids"]
    assert len(ids) == len(marks[0].args[1])
    return list(ids)


def test_every_point_is_reached_by_both_kinds(tmp_path: Path) -> None:
    """X-03, raise half: exactly one raise cell per reached (scenario, idx). Level 1, S2.

    The kill half is ``test_every_point_is_reached_by_kill_kind``.
    """
    reached = _fresh_dry_runs(tmp_path)
    assert _parametrised_ids(test_raise_cells) == RAISE_CELL_IDS
    _assert_ids_cover_reached(RAISE_CELL_IDS, reached)


def test_every_point_is_reached_by_kill_kind(tmp_path: Path) -> None:
    """X-03, kill half: exactly one kill cell per reached (scenario, idx). Level 1, S2."""
    reached = _fresh_dry_runs(tmp_path)
    _assert_ids_cover_reached(list(KILL_CELL_IDS), reached)


# =========================================================================== X-04 dry-run order


@pytest.mark.parametrize("s", SCENARIOS)
def test_dry_run_determinism_and_hook_order(tmp_path: Path, s: str) -> None:
    """X-04: two dry runs agree, and the branch-specific hook order holds. Level 1, S5."""
    first = dry_run_points(s, tmp_path / "a", **publish_kw(s))
    second = dry_run_points(s, tmp_path / "b", **publish_kw(s))
    assert first == second
    assert first.count(COMMIT) == 1
    assert first[:2] == [("p0", "before"), ("p0", "after")]
    c = first.index(COMMIT)
    assert first[c - 1] == ("p8", "before")
    for i, (step, when) in enumerate(first):
        assert when == ("before" if i % 2 == 0 else "after"), (i, step, when)
        if when == "after":
            assert first[i - 1] == (step, "before"), i

    def rank(step: str) -> int:
        if step == "p0":
            return 0
        if step == "p0.legacy":
            return 1
        if step.startswith("gc."):
            return 2
        return 3

    ranks = [rank(step) for step, _ in first]
    assert ranks == sorted(ranks)
    assert ("p0.legacy", "before") in first and ("p1", "before") in first
    gc_points = [p for p in first if p[0].startswith("gc.")]
    if s == "S5":
        assert gc_points == []
    else:
        assert gc_points[:2] == [("gc.validate", "before"), ("gc.validate", "after")]


def _refuse_hv(mutate: Callable[[Path], None]) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        book = setup_scenario("S4", base)
        mutate(book)
        return book
    return build


def _refuse_manifest_dir(base: Path) -> Path:
    book = setup_scenario("S4", base)
    os.unlink(book / MANIFEST)
    write_file(book / MANIFEST / "inner.json", b"{}")
    return book


def _refuse_overflow(which: str) -> Callable[[Path], Path]:
    def build(base: Path) -> Path:
        builder: Callable[[Path], Path] = getattr(pub.TestPublishOverCorruptBook, f"_overflow_{which}")
        book = builder(base)
        add_debris(book)
        add_stale_tmp(book)
        return book
    return build


REFUSALS: dict[str, Callable[[Path], Path]] = {
    "P-20a-1": _refuse_hv(pub._hv_1),
    "P-20a-2": _refuse_hv(pub._hv_2),
    "P-20a-3": _refuse_hv(pub._hv_3),
    "P-20a-4": _refuse_hv(pub._hv_4),
    "P-20a-5": _refuse_hv(pub._hv_5),
    "P-20e-i-manifest-dir": _refuse_manifest_dir,
    "P-10-gen-link": pub._p10_a,
    "P-10-gen-file-nomanifest": pub._p10_b,
    "P-10-gen-file": pub._p10_c,
    "P-10-gen-link-debris": pub._p10_d,
    "P-20f-a-overflow": _refuse_overflow("a"),
    "P-20f-b-overflow": _refuse_overflow("b"),
    "P-20f-c-overflow": _refuse_overflow("c"),
}


@pytest.mark.parametrize("shape", list(REFUSALS))
def test_refusal_dry_run_stops_at_p0_before(tmp_path: Path, shape: str) -> None:
    """X-04, refusal shapes: the hook list is exactly ``[("p0","before")]``, then ``BookCorrupt``. Level 1, S5."""
    book = REFUSALS[shape](tmp_path)
    rec = HookRecorder()
    with pytest.raises(BookCorrupt):
        with pytest.MonkeyPatch.context() as mp:
            install_hooks(mp, rec)
            book_format.publish(book, make_inputs("v2"))
    assert rec.calls == [("p0", "before")]


# =========================================================================== WI-1.8: real SIGKILL (Y-01 .. Y-05)
#
# Matrix section "WI-1.8". The child (``book_format_crash_child.py``, not collected) replaces
# ``book_format._crash_point`` with a counter that, at the target call, appends an fsynced marker line and sends
# itself a real kernel ``SIGKILL``. One kill per child; the cells run concurrently in a ThreadPoolExecutor during a
# module-scoped kill phase, and the parametrised tests below judge the stored post-kill trees one by one.

CHILD = Path(__file__).with_name("book_format_crash_child.py")
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
KILL_TIMEOUT_S = 30
KILL_PHASE_CEILING_S = 180.0
KILL_WORKERS = min(8, os.cpu_count() or 2)

KILL_CELLS: list[tuple[str, int, str, str]] = list(RAISE_CELLS)
KILL_CELL_IDS: list[str] = [cell_id(*c) for c in KILL_CELLS]

RECOVERY_SCENARIOS: tuple[str, ...] = ("S1", "S4")
RECOVERY_PUBLISH_POINTS: tuple[Point, ...] = (
    *((f"p{k}", "after") for k in range(1, 8)), ("p8", "before"), COMMIT,
)
"""Y-02 values of i (F-18 bounding): the pre-commit ``after`` points p1..p7, ``("p8","before")`` and the commit."""
GC_VALIDATE: list[Point] = [("gc.validate", "before"), ("gc.validate", "after")]


def recovery_publish_indices(s: str) -> list[int]:
    return [POINTS[s].index(p) for p in RECOVERY_PUBLISH_POINTS]


def recovery_gc_points(s: str, i: int) -> list[Point]:
    """The GC points a ``collect_garbage`` reaches over the tree a publish killed at ``POINTS[s][i]`` leaves.

    The publish's own GC already ran, so exactly one canonical gen is unreferenced: the residue ``gen/{g_new}``
    before the commit, the previous gen after it. The tmp exists from ``("p4","after")`` until the commit. Each
    recovery cell re-derives this list from an in-process dry run over its template, so a wrong rule fails.
    """
    pts = [*GC_VALIDATE, ("gc.delete", "before"), ("gc.delete", "after")]
    if POINTS[s].index(("p4", "after")) <= i < commit_idx(s):
        pts += [("gc.tmp", "before"), ("gc.tmp", "after")]
    return pts


RECOVERY_TEMPLATES: list[tuple[str, int]] = [(s, i) for s in RECOVERY_SCENARIOS for i in recovery_publish_indices(s)]
RECOVERY_CELLS: list[tuple[str, int, int, str, str]] = [
    (s, i, j, gstep, gwhen) for s, i in RECOVERY_TEMPLATES for j, (gstep, gwhen) in enumerate(recovery_gc_points(s, i))
]


def recovery_id(s: str, i: int, j: int, gstep: str, gwhen: str) -> str:
    step, when = POINTS[s][i]
    return f"{s}-{i}-{step}-{when}-{j}-{gstep}-{gwhen}"


RECOVERY_CELL_IDS: list[str] = [recovery_id(*c) for c in RECOVERY_CELLS]


@dataclass(frozen=True)
class ChildRun:
    """One child's outcome; ``returncode is None`` means the 30 s timeout fired (the child was killed by us)."""

    returncode: int | None
    marker: list[str]
    stdout: str
    stderr: str


def child_env() -> dict[str, str]:
    """The parent's environment with this worktree's ``src`` and ``tests/unit`` first on ``PYTHONPATH``.

    ``COV_CORE_*`` is dropped: a SIGKILLed child never flushes coverage data, so measuring it only costs startup.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("COV_CORE_")}
    env["PYTHONPATH"] = os.pathsep.join([str(SRC_DIR), str(CHILD.parent)])
    return env


def run_child(spec: dict[str, Any]) -> ChildRun:
    marker = Path(spec["marker"])
    try:
        cp = subprocess.run(
            [sys.executable, str(CHILD), json.dumps(spec)],
            env=child_env(), capture_output=True, text=True, timeout=KILL_TIMEOUT_S,
        )
        code: int | None = cp.returncode
        out, err = cp.stdout, cp.stderr
    except subprocess.TimeoutExpired as exc:
        code = None
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    lines = marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []
    return ChildRun(code, lines, out, err)


def publish_spec(s: str, book: Path, marker: Path, kill_at: int, **extra: Any) -> dict[str, Any]:
    return {"mode": "publish", "book": str(book), "create": s == "S0", "tag": "v2", "kill_at": kill_at,
            "marker": str(marker), **extra}


@dataclass(frozen=True)
class KillCell:
    book: Path
    start: dict[str, tuple[Any, ...]]
    start_closed: dict[str, tuple[Any, ...]]
    run: ChildRun


@dataclass(frozen=True)
class Template:
    base: Path
    book: Path
    start_closed: dict[str, tuple[Any, ...]]
    run: ChildRun


@dataclass(frozen=True)
class RecoveryCell:
    template: Template
    book: Path
    before: dict[str, tuple[Any, ...]]
    closed_before: dict[str, tuple[Any, ...]]
    state_before: str
    run: ChildRun


@dataclass(frozen=True)
class KillPhase:
    cells: dict[str, KillCell]
    recovery: dict[str, RecoveryCell]
    wall_s: float
    children: int
    workers: int


def _kill_cell(base: Path, s: str, idx: int) -> KillCell:
    book = setup_scenario(s, base)
    start = snapshot(book)
    start_closed = closed_list(book)
    run = run_child(publish_spec(s, book, base / "marker.txt", idx))
    return KillCell(book, start, start_closed, run)


def _template(base: Path, s: str, i: int) -> Template:
    book = setup_scenario(s, base)
    start_closed = closed_list(book)
    run = run_child(publish_spec(s, book, base / "marker.txt", i))
    return Template(base, book, start_closed, run)


def _recovery_cell(tmpl: Template, base: Path, j: int) -> RecoveryCell:
    shutil.copytree(tmpl.base, base, symlinks=True)
    book = base / tmpl.book.relative_to(tmpl.base)
    before = snapshot(book)
    closed_before = closed_list(book)
    state_before = classify(book, full=True)
    run = run_child({"mode": "gc", "book": str(book), "kill_at": j, "marker": str(base / "gc-marker.txt")})
    return RecoveryCell(tmpl, book, before, closed_before, state_before, run)


def run_kill_phase(root: Path) -> KillPhase:
    """Every Y-01 cell, every Y-02 template and every Y-02 GC cell, one child each, on ``KILL_WORKERS`` threads."""
    t0 = time.monotonic()
    cells: dict[str, KillCell] = {}
    recovery: dict[str, RecoveryCell] = {}
    with ThreadPoolExecutor(max_workers=KILL_WORKERS) as pool:
        tmpl_futs: dict[Future[Template], tuple[str, int]] = {
            pool.submit(_template, root / "tmpl" / f"{s}-{i}", s, i): (s, i) for s, i in RECOVERY_TEMPLATES
        }
        cell_futs = {
            cid: pool.submit(_kill_cell, root / "kill" / cid, s, idx)
            for cid, (s, idx, _step, _when) in zip(KILL_CELL_IDS, KILL_CELLS)
        }
        rec_futs: dict[str, Future[RecoveryCell]] = {}
        for fut in as_completed(tmpl_futs):
            s, i = tmpl_futs[fut]
            tmpl = fut.result()
            for j, (gstep, gwhen) in enumerate(recovery_gc_points(s, i)):
                rid = recovery_id(s, i, j, gstep, gwhen)
                rec_futs[rid] = pool.submit(_recovery_cell, tmpl, root / "rec" / rid, j)
        cells = {cid: f.result() for cid, f in cell_futs.items()}
        recovery = {rid: f.result() for rid, f in rec_futs.items()}
    wall = time.monotonic() - t0
    return KillPhase(cells, recovery, wall, len(cells) + len(tmpl_futs) + len(recovery), KILL_WORKERS)


@pytest.fixture(scope="module")
def kill_phase(tmp_path_factory: pytest.TempPathFactory) -> KillPhase:
    return run_kill_phase(tmp_path_factory.mktemp("kill-phase"))


def assert_killed(run: ChildRun, marker: str) -> None:
    """The child died of a real SIGKILL (a timeout or a clean exit fails) exactly at the intended point."""
    assert run.returncode == -signal.SIGKILL, (run.returncode, run.stderr[-2000:])
    assert run.marker == [marker], run.marker


def _s5_untouched_start(now: dict[str, tuple[Any, ...]]) -> dict[str, tuple[Any, ...]]:
    """An S5 post-kill snapshot minus the only new paths a kill may leave: ``gen/10/**`` and the tmp."""
    residue = set(sub(now, f"{GEN_DIR}/{G_NEW['S5']}")) | set(sub(now, MANIFEST_TMP))
    return s5_start_paths({k: v for k, v in now.items() if k not in residue})


@pytest.mark.parametrize("s,idx,step,when", KILL_CELLS, ids=KILL_CELL_IDS)
def test_kill_cells(
    kill_phase: KillPhase, references: Callable[[str], Reference], s: str, idx: int, step: str, when: str
) -> None:
    """Y-01: a real SIGKILL at the idx-th hook call.

    ①②②′ on the post-kill tree, ③ after a re-run. Level 1+2, S5.
    """
    ref = references(s)
    cell = kill_phase.cells[cell_id(s, idx, step, when)]
    book, start = cell.book, cell.start
    committed = idx >= commit_idx(s)
    g_new = G_NEW[s]
    assert_killed(cell.run, f"publish {idx} {step} {when}")

    # ②′ on the post-kill tree (no cleanup ran: the residue is exactly what the live tree held at the point).
    assert leftover_problems(book, s, idx, ref) == []

    # ① state membership.
    state = classify(book, full=True)
    allowed = {"corrupt", "valid"} if s == "S5" else {"missing", "valid"}
    assert state in allowed, state

    # ② no mixed tags; pre-commit residue is allowed (②′ pins its content).
    post_kill = snapshot(book)
    if committed:
        m = assert_valid_with(book, "v2")
        assert m.generation == g_new
        if s == "S5":
            for g_old in ("1", "2", "9"):
                prefix = f"{GEN_DIR}/{g_old}"
                assert sub(post_kill, prefix) and sub(post_kill, prefix) == sub(start, prefix)
    elif s in ("S0", "S0u", "S3"):
        assert state == "missing"
    elif s == "S5":
        assert state == "corrupt"
        assert _s5_untouched_start(post_kill) == s5_start_paths(start)
    else:
        assert state == "valid"
        assert_valid_with(book, PREV_TAG[s])
        assert sub(post_kill, MANIFEST) == sub(start, MANIFEST)
        prev = f"{GEN_DIR}/{validate_stat(book).generation}"
        assert sub(post_kill, prev) == sub(start, prev)
    assert closed_list(book) == cell.start_closed

    # ③ convergence: re-run in the parent with the same inputs, nothing cleaned in between.
    g_rerun = book_format.publish(book, make_inputs("v2"), **publish_kw(s))
    if s == "S5":
        assert_valid_with(book, "v2")
        after_rerun = snapshot(book)
        if committed:
            assert g_rerun == g_new + 1
        else:
            residue = idx >= POINTS[s].index(("p1", "after"))
            assert g_rerun == g_new + (1 if residue else 0)  # a repair again: max(on-disk) + 1
            for g_old in ("1", "2", "9", *((str(g_new),) if residue else ())):
                prefix = f"{GEN_DIR}/{g_old}"
                assert sub(after_rerun, prefix) == sub(post_kill, prefix), prefix
        assert closed_list(book) == cell.start_closed
        book_format.publish(book, make_inputs("v2"))
    assert_converged(book, ref, cell.start_closed)


@pytest.mark.parametrize("s,i,j,gstep,gwhen", RECOVERY_CELLS, ids=RECOVERY_CELL_IDS)
def test_recovery_kill_cells(
    kill_phase: KillPhase, references: Callable[[str], Reference], tmp_path: Path,
    s: str, i: int, j: int, gstep: str, gwhen: str,
) -> None:
    """Y-02: kill publish at i, kill a later GC at its own point j, then re-run publish. Level 1+2, S5."""
    ref = references(s)
    cell = kill_phase.recovery[recovery_id(s, i, j, gstep, gwhen)]
    tmpl = cell.template
    step, when = POINTS[s][i]
    committed = i >= commit_idx(s)
    assert_killed(tmpl.run, f"publish {i} {step} {when}")
    assert closed_list(tmpl.book) == tmpl.start_closed

    # The GC point list this cell family enumerates is the one a real GC over this template reaches.
    dry = tmp_path / "dry"
    shutil.copytree(tmpl.base, dry, symlinks=True)
    rec = HookRecorder()
    with pytest.MonkeyPatch.context() as mp:
        install_hooks(mp, rec)
        book_format.collect_garbage(dry / tmpl.book.relative_to(tmpl.base))
    assert rec.calls == recovery_gc_points(s, i)

    # The GC kill landed inside GC, at j.
    assert_killed(cell.run, f"gc {j} {gstep} {gwhen}")
    book = cell.book

    # ① holds and the classification is unchanged from after the publish kill.
    assert cell.state_before == "valid"
    state = classify(book, full=True)
    assert state == cell.state_before
    m = assert_valid_with(book, "v2" if committed else PREV_TAG[s])
    now = snapshot(book)
    assert sub(now, MANIFEST) == sub(cell.before, MANIFEST)
    current = f"{GEN_DIR}/{m.generation}"
    assert sub(now, current) == sub(cell.before, current)
    assert closed_list(book) == cell.closed_before

    # ③ convergence.
    book_format.publish(book, make_inputs("v2"))
    assert_converged(book, ref, cell.closed_before)


def test_child_was_really_killed(tmp_path: Path) -> None:
    """Y-03: a ``finally`` and an ``atexit`` sentinel stay absent; the child ran this worktree's source. Level 4."""
    book = setup_scenario("S1", tmp_path)
    idx = POINTS["S1"].index(("p3", "after"))
    fin, ext = tmp_path / "finally.sentinel", tmp_path / "atexit.sentinel"
    run = run_child(publish_spec("S1", book, tmp_path / "marker.txt", idx,
                                 finally_sentinel=str(fin), atexit_sentinel=str(ext)))
    assert_killed(run, f"publish {idx} p3 after")
    assert not fin.exists()
    assert not ext.exists()
    first = run.stdout.splitlines()[0]
    assert first.startswith("file ")
    child_file = Path(first[len("file "):]).resolve()
    assert child_file == (SRC_DIR / "reader3_app" / "book_format.py").resolve()
    assert child_file == Path(book_format.__file__).resolve()
    print(f"\n[WI-1.8] child book_format.__file__ = {child_file}")


@pytest.mark.parametrize("s", ["S1", "S5"])
def test_child_positive_control(tmp_path: Path, references: Callable[[str], Reference], s: str) -> None:
    """Y-04: ``kill_at=-1`` exits 0 and commits exactly the in-process reference. Level 1+2, S1."""
    book = setup_scenario(s, tmp_path)
    start = snapshot(book)
    fin = tmp_path / "finally.sentinel"
    run = run_child(publish_spec(s, book, tmp_path / "marker.txt", -1, finally_sentinel=str(fin)))
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.marker == []
    assert fin.read_text(encoding="utf-8") == "finally ran"
    assert f"result {G_NEW[s]}" in run.stdout.splitlines()
    m = assert_valid_with(book, "v2")
    assert m.generation == G_NEW[s]
    assert (book / MANIFEST).read_bytes() == references(s).manifest_bytes
    if s == "S5":
        now = snapshot(book)
        for g_old in ("1", "2", "9"):
            prefix = f"{GEN_DIR}/{g_old}"
            assert sub(now, prefix) and sub(now, prefix) == sub(start, prefix)


def test_kill_phase_wall_time(kill_phase: KillPhase) -> None:
    """Y-05: the whole kill pool (one child per kill) finishes under the 180 s ceiling. Level 1, S2."""
    expected_children = len(KILL_CELLS) + len(RECOVERY_TEMPLATES) + len(RECOVERY_CELLS)
    print(f"\n[WI-1.8] kill phase: {kill_phase.children} children on {kill_phase.workers} workers "
          f"in {kill_phase.wall_s:.1f} s")
    assert kill_phase.children == expected_children
    assert len(kill_phase.cells) == len(KILL_CELLS)
    assert len(kill_phase.recovery) == len(RECOVERY_CELLS)
    assert kill_phase.wall_s < KILL_PHASE_CEILING_S


def test_kill_and_recovery_cells_are_parametrised_from_the_table() -> None:
    """X-03 / Y-02 bounding: the kill ids are the declared ids; the recovery i values are F-18's. Level 1, S2."""
    assert _parametrised_ids(test_kill_cells) == KILL_CELL_IDS
    assert _parametrised_ids(test_recovery_kill_cells) == RECOVERY_CELL_IDS
    assert list(RECOVERY_PUBLISH_POINTS) == [
        ("p1", "after"), ("p2", "after"), ("p3", "after"), ("p4", "after"), ("p5", "after"), ("p6", "after"),
        ("p7", "after"), ("p8", "before"), ("p8", "after"),
    ]
    for s in RECOVERY_SCENARIOS:
        assert [POINTS[s][i] for i in recovery_publish_indices(s)] == list(RECOVERY_PUBLISH_POINTS)
    assert "S5" not in RECOVERY_SCENARIOS
