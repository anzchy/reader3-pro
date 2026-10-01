"""Crash-matrix harness shared by the tests and gen_matrix.py.

Phase 1 (thread pool): every cell whose crash is a real os._exit(137) in a
subprocess -- kill, recoverykill, wi7-reuse. Observers / crash specs are
thread-local, and nothing in phase 1 patches a global.
Phase 2 (main thread, sequential): in-process cells that patch os.replace etc. --
raise, raise+undofail, exdev (simulated), liveview + disk peak.
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from unittest import mock

from . import common as c
from . import fake_index as fi
from .mech_a_journal import JOURNAL, publish_a, recover_a
from .mech_b_generation import publish_b, recover_b

EV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = ("S0", "S0u", "S1", "S2", "S3")
SCENARIO_DOC = {
    "S0": "first publish, book dir does not exist, no user files",
    "S0u": "first publish, book dir holds only user files",
    "S1": "republish v1 -> v2, v1 had book.epub + images/",
    "S2": "republish v1 -> v2, v1 had NO images/ (artifact that did not exist before)",
    "S3": "first publish over a legacy flat-pkl book (no manifest)",
}
MECH = {
    "A": dict(label="a", publish=publish_a, recover=recover_a, commit="a10"),
    "B": dict(label="b", publish=publish_b, recover=recover_b, commit="b8"),
}
USER_CONTENT = {
    "notes.json": json.dumps({"notes": ["笔记 one"]}, ensure_ascii=False).encode(),
    "ai_meta.json": b'{"book_uuid": "00000000-0000-4000-8000-000000000000"}',
}
RECOVERYKILL = {"A": ("S1", "S2"), "B": ("S1", "S3")}
Point = Tuple[str, str]


@dataclass(frozen=True)
class Cell:
    mech: str
    scenario: str
    mode: str
    order: Tuple[int, ...]
    step: str
    when: str
    state: str
    residue: int
    user: str
    verdict: str

    def key(self) -> tuple:
        return (self.mech, self.mode, self.scenario, self.order)


# ---------------------------------------------------------------- fixtures


def setup(mech: str, scenario: str, base: str) -> str:
    book = os.path.join(base, "books", "sample_data")
    if scenario == "S0":
        return book
    os.makedirs(book)
    for name, data in USER_CONTENT.items():
        c.write_bytes(os.path.join(book, name), data)
    if scenario in ("S1", "S2"):
        MECH[mech]["publish"](book, c.book_contents(c.OLD, images=scenario == "S1"))
    elif scenario == "S3":
        c.write_artifacts(book, c.book_contents(c.OLD))
    return book


def user_snapshot(book: str) -> dict:
    return c.snapshot_files([os.path.join(book, n) for n in c.USER_FILES])


def user_verdict(before: dict, book: str) -> str:
    if not before:
        return "n/a"
    return "yes" if user_snapshot(book) == before else "NO"


def seek_ok(book: str, mech: str) -> bool:
    manifest = c.load_manifest(book)
    root = c.resolve_root(book, mech, manifest)
    for e in manifest["chapters"]:
        obj = c.read_chapter(manifest, root, e["id"])
        if obj["id"] != e["id"] or manifest["version"] not in obj["text"]:
            return False
    return True


def allowed(scenario: str, committed: bool) -> str:
    if committed:
        return "new-valid"
    return "missing" if scenario in ("S0", "S0u") else "old-valid"


def judge(mech: str, book: str, scenario: str, committed: bool, user: str, ok: bool = True) -> Tuple[str, int, str]:
    state, residue = c.classify(book, mech)
    good = ok and state == allowed(scenario, committed) and residue == 0 and user != "NO"
    if good and state == "new-valid":
        good = seek_ok(book, mech)
    return state, residue, "PASS" if good else "FAIL"


def run_cli(*args: str, crash: Optional[str] = None) -> int:
    env = {k: v for k, v in os.environ.items() if k != "PROTO_CRASH"}
    env["PYTHONPATH"] = EV
    if crash:
        env["PROTO_CRASH"] = crash
    code = "import sys; from proto.cli import main; sys.exit(main(sys.argv[1:]))"
    return subprocess.run([sys.executable, "-S", "-c", code, *args], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def record_points(fn: Callable[[], object], label: str, publish_only: bool = True) -> List[Point]:
    points: List[Point] = []

    def obs(m: str, s: str, w: str) -> None:
        if m == label and (not publish_only or not s.startswith("r")):
            points.append((s, w))

    with c.observing(obs):
        fn()
    return points


_POINTS: Dict[Tuple[str, str], List[Point]] = {}


def publish_points(mech: str, scenario: str) -> List[Point]:
    """Every (step, when) the publish actually reaches, from a clean dry run."""
    if (mech, scenario) not in _POINTS:
        with tempfile.TemporaryDirectory() as base:
            book = setup(mech, scenario, base)
            m = MECH[mech]
            _POINTS[(mech, scenario)] = record_points(
                lambda: m["publish"](book, c.book_contents(c.NEW)), m["label"])
    return _POINTS[(mech, scenario)]


def is_committed(mech: str, points: List[Point], idx: int) -> bool:
    return idx >= points.index((MECH[mech]["commit"], "after"))


# ---------------------------------------------------------------- phase 1: subprocess kills


def kill_cell(mech: str, scenario: str, idx: int) -> Cell:
    points = publish_points(mech, scenario)
    step, when = points[idx]
    with tempfile.TemporaryDirectory() as base:
        book = setup(mech, scenario, base)
        snap = user_snapshot(book)
        rc = run_cli("publish", mech.lower(), book, c.NEW, "1", crash=f"{mech.lower()}:{step}:{when}:kill")
        MECH[mech]["recover"](book)
        user = user_verdict(snap, book)
        state, residue, verdict = judge(mech, book, scenario, is_committed(mech, points, idx), user, ok=rc == 137)
    return Cell(mech, scenario, "kill", (idx,), step, when, state, residue, user, verdict)


def recoverykill_cells(mech: str, scenario: str, idx: int) -> List[Cell]:
    """Kill publish at point idx, then kill recover at each of its points, then recover cleanly."""
    points = publish_points(mech, scenario)
    step, when = points[idx]
    m = MECH[mech]
    out = []
    with tempfile.TemporaryDirectory() as base:
        book = setup(mech, scenario, base)
        run_cli("publish", mech.lower(), book, c.NEW, "1", crash=f"{mech.lower()}:{step}:{when}:kill")
        template = os.path.join(base, "template")
        shutil.copytree(book, template, symlinks=True)
        probe = os.path.join(base, "probe")
        shutil.copytree(template, probe, symlinks=True)
        rpoints = record_points(lambda: m["recover"](probe), m["label"], publish_only=False)
        for j, (rs, rw) in enumerate(rpoints):
            work = os.path.join(base, f"w{j}")
            shutil.copytree(template, work, symlinks=True)
            snap = user_snapshot(work)
            rc = run_cli("recover", mech.lower(), work, crash=f"{mech.lower()}:{rs}:{rw}:kill")
            m["recover"](work)
            user = user_verdict(snap, work)
            state, residue, verdict = judge(mech, work, scenario, is_committed(mech, points, idx), user,
                                            ok=rc == 137)
            out.append(Cell(mech, scenario, "recoverykill", (idx, j), f"{step}:{when}>{rs}", rw,
                            state, residue, user, verdict))
    return out


INDEX_FP = ("fp-old", "fp-new")


def index_points(start: str) -> List[Point]:
    with tempfile.TemporaryDirectory() as base:
        if start == "old":
            fi.publish_index(base, INDEX_FP[0])
        return record_points(lambda: fi.publish_index(base, INDEX_FP[1]), "i")


def wi7_cell(start: str, idx: int) -> Cell:
    points = index_points(start)
    step, when = points[idx]
    with tempfile.TemporaryDirectory() as base:
        root = os.path.join(base, "chroma_db")
        if start == "old":
            fi.publish_index(root, INDEX_FP[0])
        rc = run_cli("publish", "i", root, INDEX_FP[1], crash=f"i:{step}:{when}:kill")
        fi.recover_index(root)
        state, residue = fi.classify_index(root)
    committed = idx >= points.index(("i8", "after"))
    want = INDEX_FP[1] if committed else (INDEX_FP[0] if start == "old" else "missing")
    verdict = "PASS" if rc == 137 and state == want and residue == 0 else "FAIL"
    scen = "I-old" if start == "old" else "I-empty"
    return Cell("B-core(index)", scen, "kill", (idx,), step, when, state, residue, "n/a", verdict)


def phase1() -> List[Cell]:
    for mech in MECH:
        for scen in SCENARIOS:
            publish_points(mech, scen)  # warm the cache before threads read it
    for start in ("old", "empty"):
        index_points(start)
    jobs: List[Callable[[], object]] = []
    for mech in MECH:
        for scen in SCENARIOS:
            for i in range(len(publish_points(mech, scen))):
                jobs.append(lambda m=mech, s=scen, i=i: kill_cell(m, s, i))
        for scen in RECOVERYKILL[mech]:
            pts = publish_points(mech, scen)
            first = pts.index(("a7", "after")) if mech == "A" else 0
            for i in range(first, len(pts)):
                if pts[i] != ("a12", "after"):
                    jobs.append(lambda m=mech, s=scen, i=i: recoverykill_cells(m, s, i))
    for start in ("old", "empty"):
        for i in range(len(index_points(start))):
            jobs.append(lambda s=start, i=i: wi7_cell(s, i))
    cells: List[Cell] = []
    with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as pool:
        for res in pool.map(lambda f: f(), jobs):
            cells.extend(res if isinstance(res, list) else [res])
    return cells


# ---------------------------------------------------------------- phase 2: in-process


def raise_cell(mech: str, scenario: str, idx: int) -> Cell:
    points = publish_points(mech, scenario)
    step, when = points[idx]
    m = MECH[mech]
    with tempfile.TemporaryDirectory() as base:
        book = setup(mech, scenario, base)
        snap = user_snapshot(book)
        c.set_crash(f"{m['label']}:{step}:{when}:raise")
        try:
            m["publish"](book, c.book_contents(c.NEW))
            raised = False
        except c.InjectedCrash:
            raised = True
        finally:
            c.set_crash(None)
        m["recover"](book)
        user = user_verdict(snap, book)
        state, residue, verdict = judge(mech, book, scenario, is_committed(mech, points, idx), user, ok=raised)
    return Cell(mech, scenario, "raise", (idx,), step, when, state, residue, user, verdict)


def undofail_cell(scenario: str, idx: int, k: int) -> Optional[Cell]:
    """raise at a pre-commit step AND make the k-th restore rename fail; a fresh process recovers."""
    points = publish_points("A", scenario)
    step, when = points[idx]
    real_replace = os.replace
    seen = {"n": 0}

    def flaky_replace(src: str, dst: str, *a: object, **kw: object) -> None:
        if f"{os.sep}aside{os.sep}" in os.fspath(src):
            seen["n"] += 1
            if seen["n"] == k:
                raise OSError(errno.EIO, "injected restore failure")
        real_replace(src, dst, *a, **kw)

    with tempfile.TemporaryDirectory() as base:
        book = setup("A", scenario, base)
        snap = user_snapshot(book)
        c.set_crash(f"a:{step}:{when}:raise")
        try:
            with mock.patch("os.replace", flaky_replace):
                publish_a(book, c.book_contents(c.NEW))
            raised = False
        except c.InjectedCrash:
            raised = True
        finally:
            c.set_crash(None)
        if seen["n"] < k:
            return None  # this step never reached a k-th restore; not a cell
        journal_kept = os.path.lexists(os.path.join(book, JOURNAL))
        rc = run_cli("recover", "a", book)
        user = user_verdict(snap, book)
        state, residue, verdict = judge("A", book, scenario, False, user, ok=raised and journal_kept and rc == 0)
    return Cell("A", scenario, f"raise+undofail{k}", (idx,), step, when, state, residue, user, verdict)


class CopyCalled(AssertionError):
    pass


def exdev_cells(mech: str, scenario: str) -> List[Cell]:
    """Simulated EXDEV: the n-th os.replace/os.rename raises. Never shutil.move / copy."""
    m = MECH[mech]
    real_replace, real_rename = os.replace, os.rename
    out = []
    n = 0
    while True:
        n += 1
        calls = {"n": 0, "step": "-", "copied": False}

        def renamer(real: Callable[..., None]) -> Callable[..., None]:
            def fn(src: str, dst: str, *a: object, **kw: object) -> None:
                calls["n"] += 1
                if calls["n"] == n:
                    raise OSError(errno.EXDEV, "Cross-device link (simulated)", os.fspath(src))
                real(src, dst, *a, **kw)
            return fn

        def no_copy(*a: object, **kw: object) -> None:
            calls["copied"] = True
            raise CopyCalled("prototype must never copy")

        def obs(_m: str, s: str, w: str) -> None:
            if w == "before" and not s.startswith("r"):
                calls["step"] = s

        with tempfile.TemporaryDirectory() as base:
            book = setup(mech, scenario, base)
            snap = user_snapshot(book)
            err = None
            with c.observing(obs), mock.patch("os.replace", renamer(real_replace)), \
                    mock.patch("os.rename", renamer(real_rename)), \
                    mock.patch.multiple(shutil, move=no_copy, copy=no_copy, copy2=no_copy,
                                        copyfile=no_copy, copytree=no_copy):
                try:
                    m["publish"](book, c.book_contents(c.NEW))
                except OSError as exc:
                    err = exc
            if calls["n"] < n:
                break  # every rename the mechanism makes has been covered
            m["recover"](book)
            ok = err is not None and err.errno == errno.EXDEV and not calls["copied"]
            user = user_verdict(snap, book)
            state, residue, verdict = judge(mech, book, scenario, False, user, ok=ok)
        out.append(Cell(mech, scenario, "exdev-simulated", (n,), f"rename#{n}@{calls['step']}", "-",
                        state, residue, user, verdict))
    return out


@dataclass(frozen=True)
class LiveRow:
    mech: str
    scenario: str
    order: int
    step: str
    when: str
    state: str


def liveview(mech: str, scenario: str) -> Tuple[List[LiveRow], Dict[str, int]]:
    """Classify the live dir at every hook, as an unlocked concurrent reader would; also disk bytes."""
    m = MECH[mech]
    rows: List[LiveRow] = []
    with tempfile.TemporaryDirectory() as base:
        book = setup(mech, scenario, base)
        before = c.tree_bytes(book) if os.path.isdir(book) else 0
        peak = [before]

        def obs(_m: str, s: str, w: str) -> None:
            if _m == m["label"] and not s.startswith("r"):
                rows.append(LiveRow(mech, scenario, len(rows), s, w, c.classify(book, mech)[0]))
                peak[0] = max(peak[0], c.tree_bytes(book))

        with c.observing(obs):
            m["publish"](book, c.book_contents(c.NEW))
        after = c.tree_bytes(book)
    return rows, {"before": before, "peak": max(peak[0], after), "after": after}


@dataclass
class Results:
    cells: List[Cell]
    live: List[LiveRow]
    disk: Dict[Tuple[str, str], Dict[str, int]]


def phase2() -> Tuple[List[Cell], List[LiveRow], Dict[Tuple[str, str], Dict[str, int]]]:
    cells: List[Cell] = []
    for mech in MECH:
        for scen in SCENARIOS:
            for i in range(len(publish_points(mech, scen))):
                cells.append(raise_cell(mech, scen, i))
            cells.extend(exdev_cells(mech, scen))
    for scen in ("S1", "S2", "S3"):
        pts = publish_points("A", scen)
        for k in (1, 2):
            for i in range(pts.index(("a7", "after")), pts.index(("a10", "after"))):
                cell = undofail_cell(scen, i, k)
                if cell is not None:
                    cells.append(cell)
    live: List[LiveRow] = []
    disk = {}
    for mech in MECH:
        for scen in SCENARIOS:
            rows, d = liveview(mech, scen)
            live.extend(rows)
            disk[(mech, scen)] = d
    return cells, live, disk


def compute_all() -> Results:
    cells = phase1()
    more, live, disk = phase2()
    cells.extend(more)
    return Results(sorted(cells, key=Cell.key), live, disk)
