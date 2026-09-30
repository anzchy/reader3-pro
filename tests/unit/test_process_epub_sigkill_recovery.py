"""WI-1 (fix/crash-safety-bugs): a dead run's un-landed commit is detected, not deleted.

``_commit_staged_artifacts`` parks the superseded ``book.epub`` / ``images/`` in
its staging directory and keeps the undo list in memory. A SIGKILL between the
first aside and the marker skips the in-process rollback, so the old
``book.pkl`` sits beside new (or missing) artifacts, and the parked originals
are the only copies left. The next run used to ``rmtree`` that directory as
debris. It must now refuse, change nothing on disk, and tell the operator how
to put the old version back.

Law (matrix tests-20260926-154111.md, WI-1):

1. No deletion of the last copy of a superseded artifact of the version that
   is live when the next call starts.
2. The call refuses iff some own-named, unowned leftover has a top-level
   ``book.pkl`` and a top-level ``*.superseded`` entry; a refusal is
   side-effect-free and repeatable.
3. When the call does not refuse, a clean run converges to v2.

Test names here avoid the words the refusal message is checked for (the pytest
tmp dir is named after the test, and every path in the message carries it).
"""

from __future__ import annotations

import ast
import errno
import fcntl
import hashlib
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bookdir import USER_PATHS, make_seeded_book_dir, staging_leftovers, user_subset
from epub_builder import IMAGES_V1, IMAGES_V2, MARKER_V1, MARKER_V2, sha256_of, snapshot_tree
from reader3_app import reader3
from test_process_epub_commit import assert_consistent, load_pkl, make_shape, marker_of

LOCK = ".lock"
SHAPES = ["seeded", "absent", "user_only", "missing_epub", "missing_images"]
ABBR = {
    "seeded": "S",
    "absent": "AB",
    "user_only": "UO",
    "missing_epub": "ME",
    "missing_images": "MI",
}
LOCK_MESSAGE = "another process is already processing"
CHILD_TIMEOUT_S = 60

# --------------------------------------------------------------------------- #
# The spec, written out (matrix §0 "REFUSE"). W1-C8 checks the implementation
# against this table cell by cell; it is deliberately not derived from the
# implementation's predicate.
# --------------------------------------------------------------------------- #

R, D, NA = "refuse", "delete", None


def _row(s, ab, uo, me, mi):
    return {"seeded": s, "absent": ab, "user_only": uo, "missing_epub": me, "missing_images": mi}


REFUSE: Dict[str, Dict[str, Optional[str]]] = {
    "build_mid": _row(D, D, D, D, D),
    "build_pkl_tmp": _row(D, D, D, D, D),
    "built": _row(D, D, D, D, D),
    "after_A": _row(R, D, D, D, R),
    "after_B": _row(R, D, D, R, R),
    "after_C": _row(R, D, D, R, R),
    "after_D": _row(R, D, D, R, R),
    "after_E": _row(D, D, D, D, D),
    "rb_images_partial": _row(R, D, D, R, R),
    "rb_images": _row(R, NA, NA, R, NA),
    "rb_between": _row(R, D, D, D, R),
    "rb_epub": _row(R, NA, NA, NA, R),
    "rb_done": _row(D, D, D, D, D),
    "cleanup_partial_pkl_only": _row(D, D, D, D, D),
    "cleanup_partial_no_epub": _row(D, D, D, D, D),
}
POINTS = list(REFUSE)
LOCKLESS_POINTS = ("cleanup_partial_pkl_only", "cleanup_partial_no_epub")
FORWARD = ("A", "B", "C", "D", "E")

# --------------------------------------------------------------------------- #
# Child interpreter: chooses the kill point; the kill itself is a real SIGKILL.
# --------------------------------------------------------------------------- #

CHILD = r"""
import errno, json, os, pickle, shutil, signal, sys

out, epub_path, spec_json, sentinel = sys.argv[1:5]
spec = json.loads(spec_json)

from reader3_app import reader3

real_replace, real_rename = os.replace, os.rename
real_unlink, real_rmtree, real_dump = os.unlink, shutil.rmtree, pickle.dump
state = {"n": 0}


def die(tag, src="", dst=""):
    with open(sentinel, "w") as f:
        json.dump({"pid": os.getpid(), "n": state["n"], "tag": tag,
                   "src": str(src), "dst": str(dst)}, f)
        f.flush()
        os.fsync(f.fileno())
    os.kill(os.getpid(), signal.SIGKILL)


def rename_hook(real):
    def hook(src, dst, *a, **kw):
        s, d = os.fspath(src), os.fspath(dst)
        state["n"] += 1
        if spec.get("kill_before_commit_nth") == state["n"]:
            die("commit_nth", s, d)
        if spec.get("kill_before_dst") == d:
            die("before_dst", s, d)
        suffix = spec.get("kill_before_src_endswith")
        if suffix and s.endswith(suffix):
            die("before_src", s, d)
        if spec.get("raise_when_dst") == d:
            raise OSError(errno.EIO, "injected I/O error")
        result = real(src, dst, *a, **kw)
        if spec.get("kill_after_dst") == d:
            die("after_dst", s, d)
        if s.endswith("book.pkl.tmp"):
            # A build-phase atomic pickle write is not a commit step.
            state["n"] = 0
        return result
    return hook


def unlink_hook(path, *a, **kw):
    name = spec.get("kill_before_unlink_name")
    if name and os.path.basename(os.fspath(path)) == name:
        die("unlink", os.fspath(path), name)
    return real_unlink(path, *a, **kw)


def rmtree_hook(path, *a, **kw):
    if spec.get("kill_before_rmtree_own_staging") and os.path.basename(
        os.fspath(path)
    ).endswith(f".staging-{os.getpid()}"):
        die("rmtree_own_staging", os.fspath(path))
    return real_rmtree(path, *a, **kw)


def dump_hook(obj, f, *a, **kw):
    if spec.get("kill_in_pickle_dump"):
        die("pickle_dump")
    return real_dump(obj, f, *a, **kw)


os.replace = rename_hook(real_replace)
os.rename = rename_hook(real_rename)
os.unlink = unlink_hook
shutil.rmtree = rmtree_hook
pickle.dump = dump_hook

reader3.process_epub(epub_path, out)
sys.exit(3)
"""

PLAIN_CHILD = r"""
import sys
from reader3_app import reader3
reader3.process_epub(sys.argv[2], sys.argv[1])
"""


def run_child(tmp_path: Path, out: Path, epub: Path, spec: dict, *, premise: bool = True) -> dict:
    sentinels = tmp_path / "sentinels"
    sentinels.mkdir(exist_ok=True)
    sentinel = sentinels / f"{uuid.uuid4().hex}.json"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(out), str(epub), json.dumps(spec), str(sentinel)],
        timeout=CHILD_TIMEOUT_S,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == -signal.SIGKILL, (
        f"child for {spec} was not SIGKILLed (rc={proc.returncode}); "
        f"stderr tail: {proc.stderr[-3000:]}"
    )
    assert sentinel.is_file(), f"child for {spec} died without writing its sentinel"
    sent = json.loads(sentinel.read_text())
    if premise:
        assert staging_leftovers(out) == [f"{out}.staging-{sent['pid']}"], (
            f"premise: the killed child for {spec} should leave exactly its own staging dir"
        )
    return sent


def a_reaped_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait(timeout=30)
    return proc.pid


# --------------------------------------------------------------------------- #
# Shapes, observation helpers
# --------------------------------------------------------------------------- #


def make_any(shape: str, books_dir: Path, epub_v1: Path, name: str) -> Path:
    if shape == "seeded":
        return make_seeded_book_dir(books_dir, epub_v1, name=name)
    return make_shape(shape, books_dir, epub_v1, name)


def listing(d: Path) -> Optional[List[str]]:
    return sorted(os.listdir(d)) if d.is_dir() else None


def live_marker(out: Path) -> Optional[str]:
    return marker_of(load_pkl(out)) if (out / "book.pkl").is_file() else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Roles:
    """Labels every generated path "v1"/"v2" by content, so layouts can be compared."""

    def __init__(self, epub_v1: Path, epub_v2: Path):
        self.epub = {sha256_of(epub_v1): "v1", sha256_of(epub_v2): "v2"}
        self.img = {_sha(b): "v1" for b in IMAGES_V1.values()}
        self.img.update({_sha(b): "v2" for b in IMAGES_V2.values()})

    def tree(self, root: Path) -> Dict[str, str]:
        roles: Dict[str, str] = {}
        if not root.is_dir():
            return roles
        for key in snapshot_tree(root):
            if key in USER_PATHS:
                continue
            roles[key] = self._role(root, key)
        return roles

    def _role(self, root: Path, key: str) -> str:
        top = key.rstrip("/").split("/")[0]
        path = root / key.rstrip("/")
        if key.endswith("/") and top in ("images", "images.superseded") and "/" not in key[:-1]:
            kids = {self.img.get(sha256_of(path / n), "other") for n in os.listdir(path)}
            if not kids:
                return "empty"
            return kids.pop() if len(kids) == 1 else "multi"
        if top in ("images", "images.superseded"):
            return self.img.get(sha256_of(path), "other")
        if key in ("book.epub", "book.epub.superseded"):
            return self.epub.get(sha256_of(path), "other")
        if key == "book.pkl":
            return "v1" if marker_of(load_pkl(root)) == MARKER_V1 else "v2"
        if key == "book.pkl.tmp":
            return "tmp"
        if key == LOCK:
            return "lock"
        return "other"

    def layout(self, out: Path, dead: Path) -> Dict[str, str]:
        both = {f"out/{k}": v for k, v in self.tree(out).items()}
        both.update({f"dead/{k}": v for k, v in self.tree(dead).items()})
        return both


@pytest.fixture
def roles(epub_v1: Path, epub_v2: Path) -> Roles:
    return Roles(epub_v1, epub_v2)


@pytest.fixture
def v2_src(tmp_path: Path, epub_v2: Path) -> Path:
    src = tmp_path / "scratch" / "v2_data"
    reader3.process_epub(str(epub_v2), str(src))
    return src


Item = Tuple[str, str, str, int]


def artifact_items(root: Path, *, live_only: bool = False) -> Set[Item]:
    """``(kind, name, sha256, inode)`` of every generated artifact found under ``root``."""
    items: Set[Item] = set()
    for base, kind in (("book.pkl", "pkl"), ("book.epub", "epub")):
        for name in [base] if live_only else [base, base + ".superseded"]:
            p = root / name
            if p.is_file():
                items.add((kind, base, sha256_of(p), os.stat(p).st_ino))
    for dname in ["images"] if live_only else ["images", "images.superseded"]:
        d = root / dname
        if d.is_dir():
            for n in os.listdir(d):
                if (d / n).is_file():
                    items.add(("img", n, sha256_of(d / n), os.stat(d / n).st_ino))
    return items


def found(roots: Iterable[Path]) -> Set[Item]:
    items: Set[Item] = set()
    for r in roots:
        items |= artifact_items(Path(r))
    return items


def law_baseline(out: Path, dead_dirs: Sequence[Path], a1: Set[Item]) -> Tuple[Optional[str], Set[Item]]:
    """``(M, pub0)`` computed right before the next call (matrix W1-C8, round-2 timing)."""
    m = live_marker(out)
    if m is None:
        artifacts: Set[Item] = set()
    elif m == MARKER_V1:
        artifacts = a1
    else:
        artifacts = artifact_items(out, live_only=True)
    return m, found([out, *dead_dirs]) & artifacts


def assert_law1(out: Path, pub0: Set[Item], ctx: str) -> None:
    after = found([out, *map(Path, staging_leftovers(out))])
    lost = pub0 - after
    assert not lost, f"{ctx}: the last copy of a published artifact was lost: {sorted(lost)}"


# --------------------------------------------------------------------------- #
# The next call, three ways
# --------------------------------------------------------------------------- #


def fail_next_run(out: Path, epub_v2: Path, ctx: str = "") -> None:
    """A next run that passes cleanup, builds, then fails validation before any commit."""
    real_read_epub = reader3.epub.read_epub

    def spineless(path, *a, **kw):
        parsed = real_read_epub(path, *a, **kw)
        parsed.spine = []
        return parsed

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3.epub, "read_epub", spineless)
        try:
            reader3.process_epub(str(epub_v2), str(out))
        except reader3.ArtifactValidationError as exc:
            assert "spine" in str(exc), f"{ctx}: failed for another reason: {exc}"
        except RuntimeError as exc:
            pytest.fail(f"{ctx}: expected to pass cleanup, but the call raised RuntimeError: {exc}")
        else:
            pytest.fail(f"{ctx}: the spineless run did not fail validation")


def clean_next_run(out: Path, epub_v1: Path, epub_v2: Path, ctx: str = "") -> None:
    reader3.process_epub(str(epub_v2), str(out))
    assert assert_consistent(out, epub_v1, epub_v2, context=ctx) == MARKER_V2
    assert staging_leftovers(out) == [], f"{ctx}: staging left behind by a clean run"


def expect_refusal(out: Path, epub_v2: Path, dead_dirs: Sequence[Path], ctx: str = "") -> RuntimeError:
    watched = [d for d in [out, *dead_dirs] if d.exists()]
    before = {str(d): (snapshot_tree(d), listing(d)) for d in watched}
    listing0 = sorted(os.listdir(out.parent))
    try:
        reader3.process_epub(str(epub_v2), str(out))
    except RuntimeError as exc:
        caught = exc
    else:
        pytest.fail(f"{ctx}: the next run did not stop; it processed the book")
    changed = [d for d in before if (snapshot_tree(Path(d)), listing(Path(d))) != before[d]]
    assert changed == [], f"{ctx}: the stopped call modified {changed}"
    assert sorted(os.listdir(out.parent)) == listing0, (
        f"{ctx}: the stopped call changed the books dir listing"
    )
    return caught


# --------------------------------------------------------------------------- #
# Forging dead-run states by hand, from the on-disk protocol only
# --------------------------------------------------------------------------- #


def _rm(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    elif os.path.lexists(p):
        os.unlink(p)


def _forge_commit(out: Path, dead: Path, point: str) -> None:
    os.makedirs(out, exist_ok=True)
    live_epub, live_images = out / "book.epub", out / "images"
    undo: List[Tuple[Optional[Path], Path]] = []
    last = point[len("after_"):] if point.startswith("after_") else "D"
    for step in FORWARD[: FORWARD.index(last) + 1]:
        if step in ("A", "B"):
            live = live_epub if step == "A" else live_images
            aside = dead / f"{live.name}.superseded"
            if os.path.lexists(live):
                os.replace(live, aside)
                undo.append((aside, live))
            else:
                undo.append((None, live))
        elif step == "C":
            os.replace(dead / "book.epub", live_epub)
        elif step == "D":
            os.replace(dead / "images", live_images)
        else:
            os.replace(dead / "book.pkl", out / "book.pkl")
    if point.startswith("after_"):
        return
    # The marker rename raised; replay _restore over reversed(undo).
    (epub_aside, _), (images_aside, _) = undo
    if point == "rb_images_partial":
        os.unlink(live_images / sorted(os.listdir(live_images))[0])
        return
    shutil.rmtree(live_images)
    if point == "rb_images":
        return
    if images_aside is not None:
        os.replace(images_aside, live_images)
    if point == "rb_between":
        return
    os.unlink(live_epub)
    if point == "rb_epub":
        return
    if epub_aside is not None:
        os.replace(epub_aside, live_epub)


def forge_dead_run(
    out: Path,
    v2_src: Path,
    point: str,
    *,
    lock: bool = True,
    suffix: Optional[int] = None,
    drop: Iterable[str] = (),
) -> Path:
    if point in LOCKLESS_POINTS:
        assert suffix is not None and not lock, "cleanup_partial_* is lockless with a reaped pid"
    dead = Path(f"{out}.staging-{os.getppid() if suffix is None else suffix}")
    dead.mkdir()
    if lock:
        (dead / LOCK).touch()
    shutil.copy2(v2_src / "book.epub", dead / "book.epub")
    (dead / "images").mkdir()
    if point != "build_mid":
        for n in sorted(os.listdir(v2_src / "images")):
            shutil.copy2(v2_src / "images" / n, dead / "images" / n)
        if point == "build_pkl_tmp":
            (dead / "book.pkl.tmp").write_bytes(b"")
        else:
            shutil.copy2(v2_src / "book.pkl", dead / "book.pkl")
            if point == "cleanup_partial_no_epub":
                _rm(dead / "book.epub")
            elif point != "built":
                commit_point = "rb_done" if point == "cleanup_partial_pkl_only" else point
                _forge_commit(out, dead, commit_point)
    for name in drop:
        _rm(dead / name)
    return dead


# --------------------------------------------------------------------------- #
# Reading the message the way an operator would
# --------------------------------------------------------------------------- #

MOVE_LINE = re.compile(r"^\s*(?P<src>/\S.*?) -> (?P<dst>/\S.*?)\s*$")
REMOVE_WORD = re.compile(r"(?i)remove|delete")


def parse_moves(msg: str) -> List[Tuple[str, str]]:
    return [(m["src"], m["dst"]) for m in map(MOVE_LINE.match, msg.splitlines()) if m]


def says_remove(msg: str, path: Path | str) -> bool:
    return any(str(path) in line and REMOVE_WORD.search(line) for line in msg.splitlines())


def follow_message(msg: str, dead: Path) -> None:
    """Execute exactly what the message prescribes; never look at the disk to decide."""
    for src, dst in parse_moves(msg):
        try:
            if says_remove(msg, dst):
                _rm_strict(Path(dst))
            os.rename(src, dst)
        except OSError as exc:
            pytest.fail(
                f"following the message failed at {src} -> {dst}: "
                f"errno {errno.errorcode.get(exc.errno or 0, exc.errno)}"
            )
    if says_remove(msg, dead):
        try:
            shutil.rmtree(dead)
        except OSError as exc:
            pytest.fail(f"the staging dir named for removal could not be removed: errno {exc.errno}")


def _rm_strict(p: Path) -> None:
    # No existence check: an instruction to remove a path that is not there fails.
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        os.unlink(p)


# --------------------------------------------------------------------------- #
# W1-C1
# --------------------------------------------------------------------------- #


def test_w1_c01_real_kill_before_marker(tmp_path, books_dir, epub_v1, epub_v2):
    out = make_seeded_book_dir(books_dir, epub_v1, "k_data")
    full_before = snapshot_tree(out)

    sent = run_child(tmp_path, out, epub_v2, {"kill_before_dst": str(out / "book.pkl")})
    dead = Path(f"{out}.staging-{sent['pid']}")
    assert sent["dst"] == str(out / "book.pkl")

    # Anti-vacuity: this really is the mixed state the bug report describes.
    assert marker_of(load_pkl(out)) == MARKER_V1
    assert sha256_of(out / "book.epub") == sha256_of(epub_v2)
    for name in ("book.pkl", "book.epub.superseded", "images.superseded"):
        assert (dead / name).exists(), f"premise: {name} should be parked in the dead dir"

    exc = expect_refusal(out, epub_v2, [dead], ctx="C1")
    assert str(dead) in str(exc)
    assert user_subset(snapshot_tree(out)) == user_subset(full_before)


# --------------------------------------------------------------------------- #
# W1-C2
# --------------------------------------------------------------------------- #


def probe_commit_calls(shape: str, books_dir: Path, epub_v1: Path, epub_v2: Path, name: str):
    out = make_any(shape, books_dir, epub_v1, name)
    calls: List[Tuple[str, str]] = []

    def recorder(real):
        def rec(src, dst, *a, **kw):
            calls.append((os.fspath(src), os.fspath(dst)))
            return real(src, dst, *a, **kw)

        return rec

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "replace", recorder(os.replace))
        mp.setattr(os, "rename", recorder(os.rename))
        reader3.process_epub(str(epub_v2), str(out))
    # process_epub stages book.pkl with a plain write today, so there is usually
    # no build-phase rename to skip; if one appears, count from after it.
    tmp = [i for i, (s, _) in enumerate(calls) if s.endswith("book.pkl.tmp")]
    result = calls[tmp[-1] + 1:] if tmp else calls
    assert len(result) >= 3 and result[-1][1] == str(out / "book.pkl"), result
    return out, result


def refuse_expected(calls: List[Tuple[str, str]], n: int) -> bool:
    return any(dst.endswith(".superseded") for _, dst in calls[: n - 1])


def _step_of(dst: str, out: Path) -> str:
    if dst.endswith("book.epub.superseded"):
        return "A"
    if dst.endswith("images.superseded"):
        return "B"
    return {str(out / "book.epub"): "C", str(out / "images"): "D", str(out / "book.pkl"): "E"}[dst]


def _norm(path: str, out: Path, dead: Path | str) -> str:
    return path.replace(str(dead), "<dead>").replace(str(out), "<out>")


def test_w1_c02_real_kill_before_every_commit_rename(
    tmp_path, books_dir, epub_v1, epub_v2, v2_src, roles
):
    probe_out, probe = probe_commit_calls("seeded", books_dir, epub_v1, epub_v2, "probe_data")
    probe_dead = f"{probe_out}.staging-{os.getpid()}"
    outcomes = []
    for n in range(1, len(probe) + 1):
        ctx = f"C2 n={n}"
        out = make_seeded_book_dir(books_dir, epub_v1, f"n{n}_data")
        full_before = snapshot_tree(out)
        user0 = user_subset(full_before)
        v1 = artifact_items(out, live_only=True)

        sent = run_child(tmp_path, out, epub_v2, {"kill_before_commit_nth": n})
        dead = Path(f"{out}.staging-{sent['pid']}")
        assert _norm(sent["dst"], out, dead) == _norm(probe[n - 1][1], probe_out, probe_dead), ctx
        assert user_subset(snapshot_tree(out)) == user0, ctx

        point = "built" if n == 1 else f"after_{_step_of(probe[n - 2][1], probe_out)}"
        twin = make_seeded_book_dir(books_dir, epub_v1, f"n{n}_twin_data")
        twin_dead = forge_dead_run(twin, v2_src, point)
        assert roles.layout(out, dead) == roles.layout(twin, twin_dead), f"{ctx}: forge fidelity"

        if refuse_expected(probe, n):
            exc = expect_refusal(out, epub_v2, [dead], ctx=ctx)
            assert str(dead) in str(exc), ctx
            outcomes.append("refuse")
            assert v1 <= found([out, *map(Path, staging_leftovers(out))]), ctx
        else:
            fail_next_run(out, epub_v2, ctx)
            assert snapshot_tree(out) == full_before, ctx
            assert staging_leftovers(out) == [], ctx
            outcomes.append("proceed")
            assert v1 <= found([out]), ctx
            assert user_subset(snapshot_tree(out)) == user0, ctx
            clean_next_run(out, epub_v1, epub_v2, ctx)
        assert user_subset(snapshot_tree(out)) == user0, ctx

    assert "refuse" in outcomes and "proceed" in outcomes, outcomes


# --------------------------------------------------------------------------- #
# W1-C3, W1-C4
# --------------------------------------------------------------------------- #


def test_w1_c03_real_kill_after_marker(tmp_path, books_dir, epub_v1, epub_v2):
    out = make_seeded_book_dir(books_dir, epub_v1)
    user0 = user_subset(snapshot_tree(out))

    sent = run_child(tmp_path, out, epub_v2, {"kill_after_dst": str(out / "book.pkl")})
    dead = Path(f"{out}.staging-{sent['pid']}")
    assert marker_of(load_pkl(out)) == MARKER_V2
    assert (dead / "book.epub.superseded").exists() and (dead / "images.superseded").exists()
    assert not (dead / "book.pkl").exists()
    epub_ino = os.stat(out / "book.epub").st_ino

    fail_next_run(out, epub_v2, "C3")
    assert assert_consistent(out, epub_v1, epub_v2, context="C3") == MARKER_V2
    assert staging_leftovers(out) == []
    assert os.stat(out / "book.epub").st_ino == epub_ino
    assert user_subset(snapshot_tree(out)) == user0

    clean_next_run(out, epub_v1, epub_v2, "C3 clean")
    assert user_subset(snapshot_tree(out)) == user0


def test_w1_c04_real_kill_inside_pickle_dump(tmp_path, books_dir, epub_v1, epub_v2):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)

    sent = run_child(tmp_path, out, epub_v2, {"kill_in_pickle_dump": True})
    dead = Path(f"{out}.staging-{sent['pid']}")
    # The matrix expected book.pkl.tmp here, but _build_into_staging writes the
    # staged marker straight to staging/book.pkl (no tmp + rename). The real
    # state is a zero-byte book.pkl with no aside, which is just as sharp: a
    # predicate keyed on book.pkl alone would stop here.
    assert (dead / "book.pkl").is_file() and os.stat(dead / "book.pkl").st_size == 0
    assert not (dead / "book.pkl.tmp").exists()
    assert not [n for n in os.listdir(dead) if n.endswith(".superseded")]
    assert snapshot_tree(out) == full_before

    clean_next_run(out, epub_v1, epub_v2, "C4")
    assert not dead.exists()
    assert user_subset(snapshot_tree(out)) == user_subset(full_before)


# --------------------------------------------------------------------------- #
# W1-C5
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shape", ["absent", "user_only", "missing_epub", "missing_images"])
def test_w1_c05_real_kill_before_marker_per_shape(
    shape, tmp_path, books_dir, epub_v1, epub_v2, v2_src, roles
):
    ctx = f"C5 {shape}"
    out = make_any(shape, books_dir, epub_v1, f"{ABBR[shape]}_data")
    full_before = snapshot_tree(out)

    sent = run_child(tmp_path, out, epub_v2, {"kill_before_dst": str(out / "book.pkl")})
    dead = Path(f"{out}.staging-{sent['pid']}")

    twin = make_any(shape, books_dir, epub_v1, f"{ABBR[shape]}_twin_data")
    twin_dead = forge_dead_run(twin, v2_src, "after_D")
    assert roles.layout(out, dead) == roles.layout(twin, twin_dead), f"{ctx}: forge fidelity"

    if shape in ("missing_epub", "missing_images"):
        msg = str(expect_refusal(out, epub_v2, [dead], ctx=ctx))
        present = "images.superseded" if shape == "missing_epub" else "book.epub.superseded"
        absent = "book.epub.superseded" if shape == "missing_epub" else "images.superseded"
        assert present in msg and absent not in msg, msg
    else:
        fail_next_run(out, epub_v2, ctx)
        assert staging_leftovers(out) == []
        assert user_subset(snapshot_tree(out)) == user_subset(full_before)
        assert not (out / "book.pkl").exists()
        clean_next_run(out, epub_v1, epub_v2, ctx)


# --------------------------------------------------------------------------- #
# W1-C6
# --------------------------------------------------------------------------- #

C6_VARIANTS = {
    "rb_images": {"kill_before_src_endswith": "images.superseded"},
    "rb_between": {"kill_before_unlink_name": "book.epub"},
    "rb_epub": {"kill_before_src_endswith": "book.epub.superseded"},
    "rb_done": {"kill_before_rmtree_own_staging": True},
    "rb_cleanup_partial": {"kill_before_unlink_name": "book.pkl"},
}


@pytest.mark.parametrize("variant", list(C6_VARIANTS))
def test_w1_c06_real_kill_inside_rollback(
    variant, tmp_path, books_dir, epub_v1, epub_v2, v2_src, roles
):
    ctx = f"C6 {variant}"
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    user0 = user_subset(full_before)
    v1 = artifact_items(out, live_only=True)
    images_ino = full_before["images/"][3]

    spec = {"raise_when_dst": str(out / "book.pkl"), **C6_VARIANTS[variant]}
    sent = run_child(tmp_path, out, epub_v2, spec)
    dead = Path(f"{out}.staging-{sent['pid']}")
    names = set(os.listdir(dead))

    if variant == "rb_images":
        assert not (out / "images").exists() and "images.superseded" in names, ctx
        point = "rb_images"
    elif variant == "rb_between":
        assert os.stat(out / "images").st_ino == images_ino, ctx
        assert roles.tree(out)["images/"] == "v1", ctx
        assert sha256_of(out / "book.epub") == sha256_of(epub_v2), ctx
        assert names == {LOCK, "book.pkl", "book.epub.superseded"}, (ctx, names)
        point = "rb_between"
    elif variant == "rb_epub":
        assert roles.tree(out)["images/"] == "v1", ctx
        assert not (out / "book.epub").exists(), ctx
        point = "rb_epub"
    elif variant == "rb_done":
        assert snapshot_tree(out) == full_before, ctx
        assert names == {LOCK, "book.pkl"}, (ctx, names)
        point = "rb_done"
    else:
        assert snapshot_tree(out) == full_before, ctx
        assert "book.pkl" in names and not [n for n in names if n.endswith(".superseded")]
        point = "rb_done" if LOCK in names else "cleanup_partial_pkl_only"

    twin = make_seeded_book_dir(books_dir, epub_v1, "twin_data")
    if point in LOCKLESS_POINTS:
        twin_dead = forge_dead_run(twin, v2_src, point, lock=False, suffix=a_reaped_pid())
    else:
        twin_dead = forge_dead_run(twin, v2_src, point)
    assert roles.layout(out, dead) == roles.layout(twin, twin_dead), f"{ctx}: forge fidelity"

    if variant in ("rb_images", "rb_between", "rb_epub"):
        exc = expect_refusal(out, epub_v2, [dead], ctx=ctx)
        assert str(dead) in str(exc), ctx
        assert v1 <= found([out, *map(Path, staging_leftovers(out))]), ctx
    else:
        fail_next_run(out, epub_v2, ctx)
        assert snapshot_tree(out) == full_before, ctx
        assert staging_leftovers(out) == [], ctx
        assert v1 <= found([out]), ctx
        clean_next_run(out, epub_v1, epub_v2, ctx)
    assert user_subset(snapshot_tree(out)) == user0, ctx


# --------------------------------------------------------------------------- #
# W1-C7
# --------------------------------------------------------------------------- #


def test_w1_c07_real_kill_inside_next_runs_cleanup(tmp_path, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    user0 = user_subset(snapshot_tree(out))
    # A reaped-pid suffix rather than getppid(): rmtree may unlink .lock before
    # the kill fires, and a live pid would then (correctly) read as a live owner.
    dead = forge_dead_run(out, v2_src, "after_E", suffix=a_reaped_pid())
    before_live = snapshot_tree(out)

    sent = run_child(
        tmp_path, out, epub_v2, {"kill_before_unlink_name": "book.epub.superseded"}, premise=False
    )
    assert sent["dst"] == "book.epub.superseded"
    assert dead.is_dir() and not (dead / "book.pkl").exists()
    assert staging_leftovers(out) == [str(dead)]
    assert snapshot_tree(out) == before_live

    clean_next_run(out, epub_v1, epub_v2, "C7")
    assert user_subset(snapshot_tree(out)) == user0


# --------------------------------------------------------------------------- #
# W1-C8
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shape", SHAPES)
def test_w1_c08_law_over_every_forged_state(shape, books_dir, epub_v1, epub_v2, v2_src):
    verdicts = []
    for point in POINTS:
        expected = REFUSE[point][shape]
        if expected is None:
            continue
        ctx = f"{shape}/{point}"
        out = make_any(shape, books_dir, epub_v1, f"{ABBR[shape]}_{point}_data")
        full_before = snapshot_tree(out)
        user0 = user_subset(full_before)
        a1 = artifact_items(out, live_only=True) if out.is_dir() else set()

        if point in LOCKLESS_POINTS:
            dead = forge_dead_run(out, v2_src, point, lock=False, suffix=a_reaped_pid())
        else:
            dead = forge_dead_run(out, v2_src, point)
        if point != "after_E":
            assert a1 <= found([out, dead]), (
                f"{ctx}: the forge itself lost an artifact"
            )

        m, pub0 = law_baseline(out, [dead], a1)
        if point == "after_E":
            assert m == MARKER_V2, ctx
        else:
            assert m == (None if shape in ("absent", "user_only") else MARKER_V1), ctx

        if expected == R:
            e1 = expect_refusal(out, epub_v2, [dead], ctx=ctx)
            assert_law1(out, pub0, ctx)
            e2 = expect_refusal(out, epub_v2, [dead], ctx=ctx + " (again)")
            assert str(e1) == str(e2), ctx
        else:
            fail_next_run(out, epub_v2, ctx)
            assert staging_leftovers(out) == [], ctx
            assert_law1(out, pub0, ctx)
            if (shape, point) in (("seeded", "rb_done"), ("missing_epub", "rb_between")):
                assert live_marker(out) == MARKER_V1, ctx
                v1_imgs = {i for i in a1 if i[0] == "img"}
                assert v1_imgs and v1_imgs <= artifact_items(out, live_only=True), ctx
            clean_next_run(out, epub_v1, epub_v2, ctx)
        assert user_subset(snapshot_tree(out)) == user0, ctx
        verdicts.append(expected)

    if shape == "seeded":
        assert R in verdicts and D in verdicts, verdicts
    if shape == "absent":
        assert R not in verdicts, verdicts


# --------------------------------------------------------------------------- #
# W1-C9
# --------------------------------------------------------------------------- #

C9_BASES = {
    "after_E": (LOCK, "book.epub.superseded", "images.superseded"),
    "built": (LOCK, "book.pkl", "book.epub", "images"),
    "rb_done": (LOCK, "book.pkl"),
}


def _subsets(entries: Sequence[str]):
    for r in range(len(entries) + 1):
        yield from itertools.combinations(entries, r)


@pytest.mark.parametrize("base", list(C9_BASES))
def test_w1_c09_partial_leftovers_stay_deletable(base, books_dir, epub_v1, epub_v2, v2_src):
    entries = C9_BASES[base]
    count = 0
    for i, kept in enumerate(_subsets(entries)):
        ctx = f"C9 {base} kept={kept}"
        out = make_seeded_book_dir(books_dir, epub_v1, f"{base}_{i}_data")
        user0 = user_subset(snapshot_tree(out))
        a1 = artifact_items(out, live_only=True)
        dead = forge_dead_run(
            out,
            v2_src,
            base,
            lock=LOCK in kept,
            suffix=a_reaped_pid(),
            drop=[e for e in entries if e not in kept and e != LOCK],
        )
        assert set(os.listdir(dead)) == set(kept), ctx
        _, pub0 = law_baseline(out, [dead], a1)

        fail_next_run(out, epub_v2, ctx)
        assert staging_leftovers(out) == [], ctx
        assert_law1(out, pub0, ctx)
        clean_next_run(out, epub_v1, epub_v2, ctx)
        assert user_subset(snapshot_tree(out)) == user0, ctx
        count += 1
    assert count == 2 ** len(entries)


# --------------------------------------------------------------------------- #
# W1-C10
# --------------------------------------------------------------------------- #

C10_CELLS = [(s, p) for p in POINTS for s in SHAPES if REFUSE[p][s] == R] + [("seeded", "c1_real_kill")]
C10_NO_STRAY = {("seeded", p) for _, p in C10_CELLS} | {
    ("missing_epub", "after_B"),
    ("missing_images", "after_A"),
    ("missing_images", "after_B"),
    # The matrix lists MI/after_C as a stray cell, but MI has no images/ and
    # step D has not run yet, so nothing v2 is left once the epub is back:
    # the stricter full-equality check applies.
    ("missing_images", "after_C"),
    ("missing_images", "rb_between"),
    ("missing_images", "rb_epub"),
}


@pytest.mark.parametrize("shape,point", C10_CELLS, ids=[f"{ABBR[s]}-{p}" for s, p in C10_CELLS])
def test_w1_c10_following_the_message_restores_the_book(
    shape, point, tmp_path, books_dir, epub_v1, epub_v2, v2_src, roles
):
    ctx = f"C10 {shape}/{point}"
    out = make_any(shape, books_dir, epub_v1, f"{ABBR[shape]}_data")
    full_before = snapshot_tree(out)
    user0 = user_subset(full_before)
    a1 = artifact_items(out, live_only=True)
    if point == "c1_real_kill":
        sent = run_child(tmp_path, out, epub_v2, {"kill_before_dst": str(out / "book.pkl")})
        dead = Path(f"{out}.staging-{sent['pid']}")
    else:
        dead = forge_dead_run(out, v2_src, point)
    m, pub0 = law_baseline(out, [dead], a1)
    assert m == MARKER_V1, ctx

    msg = str(expect_refusal(out, epub_v2, [dead], ctx=ctx))
    moves = parse_moves(msg)
    asides = {n for n in os.listdir(dead) if n.endswith(".superseded")}
    assert {src for src, _ in moves} == {str(dead / n) for n in asides}, (ctx, msg)
    for src, dst in moves:
        name = os.path.basename(src)
        assert dst == str(out / name.removesuffix(".superseded")), (ctx, src, dst)

    follow_message(msg, dead)

    after = snapshot_tree(out)
    if (shape, point) in C10_NO_STRAY:
        assert after == full_before, (
            f"{ctx}: added {sorted(set(after) - set(full_before))}, "
            f"lost {sorted(set(full_before) - set(after))}, "
            f"changed {sorted(p for p in set(after) & set(full_before) if after[p] != full_before[p])}"
        )
    else:
        for p in full_before:
            assert after.get(p) == full_before[p], f"{ctx}: {p} not restored"
        live_roles = roles.tree(out)
        extra = [k for k in after if k not in full_before and k not in USER_PATHS]
        assert extra, f"{ctx}: expected a stray v2 artifact in this cell"
        assert all(live_roles[k] == "v2" for k in extra), (ctx, {k: live_roles[k] for k in extra})
    if (shape, point) == ("seeded", "rb_between"):
        assert os.stat(out / "images").st_ino == full_before["images/"][3]

    fail_next_run(out, epub_v2, ctx)
    assert_law1(out, pub0, ctx)
    clean_next_run(out, epub_v1, epub_v2, ctx)
    assert user_subset(snapshot_tree(out)) == user0, ctx


# --------------------------------------------------------------------------- #
# W1-C11
# --------------------------------------------------------------------------- #

C11_STATES = [
    ("missing_images", "after_D"),
    ("missing_epub", "after_D"),
    ("seeded", "after_B"),
    ("seeded", "after_D"),
    ("seeded", "after_A"),
]


@pytest.mark.parametrize("shape,point", C11_STATES, ids=[f"{ABBR[s]}-{p}" for s, p in C11_STATES])
def test_w1_c11_message_fragments(shape, point, books_dir, epub_v1, epub_v2, v2_src):
    out = make_any(shape, books_dir, epub_v1, f"{ABBR[shape]}_data")
    dead = forge_dead_run(out, v2_src, point)
    asides = sorted(n for n in os.listdir(dead) if n.endswith(".superseded"))
    live_present = {a: os.path.lexists(out / a.removesuffix(".superseded")) for a in asides}

    msg = str(expect_refusal(out, epub_v2, [dead], ctx="C11"))
    lines = msg.splitlines()

    assert str(dead) in msg and str(out) in msg, msg
    for name in ("book.epub.superseded", "images.superseded"):
        assert (name in msg) == (name in asides), (name, msg)
    assert "mixed" in msg.lower(), msg
    for aside, present in live_present.items():
        live = str(out / aside.removesuffix(".superseded"))
        says = [ln for ln in lines if live in ln and REMOVE_WORD.search(ln)]
        if present:
            assert says, f"no instruction to clear the occupied {live}:\n{msg}"
        else:
            assert not says, f"an instruction to clear {live}, which is not there:\n{msg}"
    assert says_remove(msg, dead), msg
    assert re.search(r"(?i)refus", msg) and "until" in msg.lower(), msg
    assert LOCK_MESSAGE not in msg, msg


# --------------------------------------------------------------------------- #
# W1-C12
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("combo", ["one_each", "one_each_swapped", "two_parked", "two_plain"])
def test_w1_c12_every_leftover_classified_first(combo, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    s1, s2 = os.getppid(), a_reaped_pid()
    if combo == "one_each_swapped":
        s1, s2 = s2, s1

    if combo in ("one_each", "one_each_swapped"):
        parked = forge_dead_run(out, v2_src, "after_D", suffix=s1)
        plain = forge_dead_run(out, v2_src, "build_mid", suffix=s2)
        msg = str(expect_refusal(out, epub_v2, [parked, plain], ctx=combo))
        assert str(parked) in msg and str(plain) not in msg, msg
    elif combo == "two_parked":
        first = forge_dead_run(out, v2_src, "after_D", suffix=s1)
        second = forge_dead_run(out, v2_src, "rb_epub", suffix=s2)
        msg = str(expect_refusal(out, epub_v2, [first, second], ctx=combo))
        assert str(first) in msg and str(second) in msg, msg
    else:
        forge_dead_run(out, v2_src, "rb_done", suffix=s1)
        forge_dead_run(out, v2_src, "built", suffix=s2)
        fail_next_run(out, epub_v2, combo)
        assert staging_leftovers(out) == []
        assert snapshot_tree(out) == full_before


# --------------------------------------------------------------------------- #
# W1-C13, W1-C14
# --------------------------------------------------------------------------- #


def _hold(lock_path: Path) -> int:
    fd = os.open(lock_path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _release(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


@pytest.mark.parametrize("variant", ["held", "held_plus_dead", "held_plus_dead_swapped"])
def test_w1_c13_live_lock_has_priority(variant, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    if variant == "held":
        held = forge_dead_run(out, v2_src, "after_D")
        dirs = [held]
    else:
        s1, s2 = os.getppid(), a_reaped_pid()
        if variant.endswith("swapped"):
            s1, s2 = s2, s1
        held = forge_dead_run(out, v2_src, "build_mid", suffix=s1)
        parked = forge_dead_run(out, v2_src, "after_D", suffix=s2)
        dirs = [held, parked]
    fd = _hold(held / LOCK)
    try:
        msg = str(expect_refusal(out, epub_v2, dirs, ctx=variant))
    finally:
        _release(fd)
    assert LOCK_MESSAGE in msg, msg
    assert "mixed" not in msg.lower(), msg


@pytest.mark.parametrize("variant", ["reaped_parked", "live_pid_parked", "reaped_pkl_only"])
def test_w1_c14_lockless_pid_fallback(variant, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    if variant == "reaped_parked":
        dead = forge_dead_run(out, v2_src, "after_D", lock=False, suffix=a_reaped_pid())
        msg = str(expect_refusal(out, epub_v2, [dead], ctx=variant))
        assert str(dead) in msg and "mixed" in msg.lower(), msg
    elif variant == "live_pid_parked":
        dead = forge_dead_run(out, v2_src, "after_D", lock=False, suffix=os.getppid())
        msg = str(expect_refusal(out, epub_v2, [dead], ctx=variant))
        assert LOCK_MESSAGE in msg, msg
    else:
        forge_dead_run(
            out, v2_src, "cleanup_partial_pkl_only", lock=False, suffix=a_reaped_pid()
        )
        fail_next_run(out, epub_v2, variant)
        assert staging_leftovers(out) == []
        assert snapshot_tree(out) == full_before
        clean_next_run(out, epub_v1, epub_v2, variant)


# --------------------------------------------------------------------------- #
# W1-C15
# --------------------------------------------------------------------------- #


def _make_decoy(path: Path, v2_src: Path, epub_v1: Path) -> Path:
    path.mkdir()
    shutil.copy2(v2_src / "book.pkl", path / "book.pkl")
    shutil.copy2(epub_v1, path / "book.epub.superseded")
    (path / "images.superseded").mkdir()
    (path / "images.superseded" / "cover.png").write_bytes(b"decoy image")
    (path / "notes.json").write_text('{"notes": [{"id": "decoy"}]}', encoding="utf-8")
    return path


@pytest.mark.parametrize("companion", ["none", "parked", "plain"])
@pytest.mark.parametrize("decoy_name", ["sample_data.staging-backup", "sample_data.staging-1_data"])
def test_w1_c15_decoy_siblings(decoy_name, companion, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    assert out.name == "sample_data"
    full_before = snapshot_tree(out)
    decoy = _make_decoy(books_dir / decoy_name, v2_src, epub_v1)
    decoy_before = snapshot_tree(decoy)

    if companion == "none":
        clean_next_run_keeping(out, epub_v1, epub_v2, [str(decoy)])
        assert sha256_of(out / "book.epub") == sha256_of(epub_v2)
    elif companion == "parked":
        dead = forge_dead_run(out, v2_src, "after_D")
        msg = str(expect_refusal(out, epub_v2, [dead, decoy], ctx=companion))
        assert str(dead) in msg and str(decoy) not in msg, msg
    else:
        forge_dead_run(out, v2_src, "rb_done")
        fail_next_run(out, epub_v2, companion)
        assert snapshot_tree(out) == full_before
        assert staging_leftovers(out) == [str(decoy)]
        clean_next_run_keeping(out, epub_v1, epub_v2, [str(decoy)])
    assert snapshot_tree(decoy) == decoy_before


def clean_next_run_keeping(out: Path, epub_v1: Path, epub_v2: Path, kept: List[str]) -> None:
    reader3.process_epub(str(epub_v2), str(out))
    assert assert_consistent(out, epub_v1, epub_v2) == MARKER_V2
    assert staging_leftovers(out) == kept


# --------------------------------------------------------------------------- #
# W1-C16
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("where", ["nested", "top_level"])
def test_w1_c16_top_level_entries_only(where, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    dead = forge_dead_run(out, v2_src, "built")
    if where == "nested":
        (dead / "images" / "cover.superseded").write_bytes(b"\x89PNG legit name")
        fail_next_run(out, epub_v2, where)
        assert staging_leftovers(out) == []
        assert snapshot_tree(out) == full_before
    else:
        os.rename(dead / "book.epub", dead / "book.epub.superseded")
        expect_refusal(out, epub_v2, [dead], ctx=where)


# --------------------------------------------------------------------------- #
# W1-C17
# --------------------------------------------------------------------------- #


def test_w1_c17_stays_inert_across_attempts(books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    dead = forge_dead_run(out, v2_src, "after_D")
    trees0 = (snapshot_tree(out), snapshot_tree(dead), sorted(os.listdir(books_dir)))

    e1 = expect_refusal(out, epub_v2, [dead], ctx="call 1")
    proc = subprocess.run(
        [sys.executable, "-c", PLAIN_CHILD, str(out), str(epub_v2)],
        timeout=CHILD_TIMEOUT_S,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, proc.stdout
    assert str(dead) in proc.stderr, proc.stderr[-3000:]
    assert (snapshot_tree(out), snapshot_tree(dead), sorted(os.listdir(books_dir))) == trees0
    e3 = expect_refusal(out, epub_v2, [dead], ctx="call 3")

    assert str(e1) == str(e3)
    assert (snapshot_tree(out), snapshot_tree(dead), sorted(os.listdir(books_dir))) == trees0


# --------------------------------------------------------------------------- #
# W1-C18
# --------------------------------------------------------------------------- #

SCANNED = ["test_process_epub_sigkill_recovery.py", "test_collections_concurrency.py"]


def _unbounded_calls(path: Path) -> Tuple[List[int], int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # A name bound to a threading primitive is not a Popen result.
    threading_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "threading"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    bad: List[int] = []
    runs = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        kws = {k.arg for k in node.keywords}
        func = node.func
        receiver = func.value.id if isinstance(func.value, ast.Name) else None
        if receiver == "subprocess" and func.attr in ("run", "check_output", "call", "check_call"):
            runs += func.attr == "run"
            if "timeout" not in kws:
                bad.append(node.lineno)
        elif func.attr in ("wait", "communicate") and receiver not in threading_names:
            if "timeout" not in kws:
                bad.append(node.lineno)
    return bad, runs


def test_w1_c18_every_subprocess_is_bounded():
    here = Path(__file__).parent
    total_runs = 0
    offenders = {}
    for name in SCANNED:
        bad, runs = _unbounded_calls(here / name)
        total_runs += runs
        if bad:
            offenders[name] = bad
    assert offenders == {}
    assert total_runs >= 1


# =========================================================================== #
# Follow-up hardening (plan-20260926-212356 WI-1, matrix tests-20260926-212356)
#
# C19-C23: fail closed on staging inspection, scope and disambiguate the
# recovery message, release the lock when images/ cannot be created.
# C24-C27: keep this run's own staging when an in-process rollback left the
# previous version parked in it (Amendment 1, WI-1(f)).
#
# Test and param ids avoid every word the message or stderr is checked for;
# free-text checks go through scrub()/words() because every path carries the
# pytest tmp dir, which is named after the test.
# =========================================================================== #


def scrub(msg: str, tmp_path: Path) -> str:
    return msg.replace(str(tmp_path), "<tmp>")


def path_tokens(line: str) -> List[Path]:
    return [Path(t.rstrip(":,.;)'\"")) for t in re.findall(r"/\S+", line)]


def words(line: str) -> str:
    return re.sub(r"/\S+", " ", line)


def says_remove_exact(msg: str, p: Path | str) -> bool:
    target = Path(p)
    return any(
        REMOVE_WORD.search(words(line)) and target in path_tokens(line) for line in msg.splitlines()
    )


def under(p: Path | str, out: Path) -> bool:
    return Path(p) == out or out in Path(p).parents


def has_note(msg: str, p: Path | str, rx: str) -> bool:
    target = Path(p)
    return any(
        target in path_tokens(line) and re.search(rx, words(line)) for line in msg.splitlines()
    )


def pinned_uninspectable(msg: str, p: Path | str) -> bool:
    target = Path(p)
    for line in msg.splitlines():
        w = words(line)
        if (
            target in path_tokens(line)
            and re.search(r"(?i)inspect\b.*\bby hand", w)
            and re.search(r"(?i)only copy", w)
            and not REMOVE_WORD.search(w)
        ):
            return True
    return False


def removal_lines(msg: str) -> List[str]:
    return [line for line in msg.splitlines() if REMOVE_WORD.search(words(line))]


def stderr_lines_naming(err: str, p: Path | str) -> List[str]:
    target = Path(p)
    return [line for line in err.splitlines() if target in path_tokens(line)]


def errno_text_in(text: str, err: int) -> bool:
    return os.strerror(err) in text or errno.errorcode[err] in text


def staging_of(out: Path) -> Path:
    return Path(f"{os.path.normpath(out)}.staging-{os.getpid()}")


class Proxy:
    """Stands in for a module as seen by ``reader3``: overrides win, the rest delegates.

    Installed with ``mp.setattr(reader3, "os", ...)`` / ``(reader3, "shutil", ...)``
    so the fault reaches only reader3's own calls, never snapshot_tree, listing()
    or expect_refusal, which use the same functions.
    """

    def __init__(self, real: Any, **overrides: Callable[..., Any]):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


OsProxy = Proxy
ShutilProxy = Proxy


def listing_overrides(fault: Callable[[str], None]) -> Dict[str, Callable[..., Any]]:
    """listdir and scandir together, so switching between them cannot disarm a fault."""

    def listdir(path: Any = ".") -> List[str]:
        fault(os.path.normpath(os.fspath(path)))
        return os.listdir(path)

    def scandir(path: Any = ".") -> Any:
        fault(os.path.normpath(os.fspath(path)))
        return os.scandir(path)

    return {"listdir": listdir, "scandir": scandir}


ERR_CLASS = {errno.EACCES: PermissionError, errno.ENOTDIR: NotADirectoryError}


def raise_on_listing(target: Path, err: int) -> Callable[[str], None]:
    def fault(p: str) -> None:
        if p == str(target):
            raise ERR_CLASS.get(err, OSError)(err, os.strerror(err), p)

    return fault


def file_hashes(roots: Iterable[Path]) -> Counter:
    hashes: Counter = Counter()
    for root in roots:
        root = Path(root)
        if root.is_file():
            hashes[sha256_of(root)] += 1
            continue
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                hashes[sha256_of(Path(dirpath) / name)] += 1
    return hashes


def follow_exact(msg: str, dirs: Sequence[Path]) -> None:
    """An operator that acts on exact path tokens only: moves, then the named deletions."""
    for src, dst in parse_moves(msg):
        try:
            if says_remove_exact(msg, dst):
                _rm_strict(Path(dst))
            os.rename(src, dst)
        except OSError as exc:
            pytest.fail(f"following the message failed at {src} -> {dst}: errno {exc.errno}")
    for d in dirs:
        if says_remove_exact(msg, d):
            try:
                shutil.rmtree(d)
            except OSError as exc:
                pytest.fail(f"a staging dir named for deletion could not be cleared: {exc.errno}")


# --------------------------------------------------------------------------- #
# W1-C19 family: fail closed on inspection (WI-1a)
# --------------------------------------------------------------------------- #


def test_w1_c19_unreadable_leftover_real_mode(tmp_path, books_dir, epub_v1, epub_v2, v2_src):
    if os.geteuid() == 0:
        pytest.skip("root reads a mode-000 directory")
    out = make_seeded_book_dir(books_dir, epub_v1)
    plain = forge_dead_run(out, v2_src, "rb_done")
    hidden = forge_dead_run(out, v2_src, "after_D", suffix=a_reaped_pid())
    before = {d: snapshot_tree(d) for d in (out, plain, hidden)}
    listing0 = sorted(os.listdir(books_dir))

    os.chmod(hidden, 0)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            reader3.process_epub(str(epub_v2), str(out))
    finally:
        os.chmod(hidden, 0o700)
    msg = str(excinfo.value)

    assert hidden in [t for line in msg.splitlines() for t in path_tokens(line)], msg
    assert errno_text_in(scrub(msg, tmp_path), errno.EACCES), msg
    assert LOCK_MESSAGE not in msg, msg
    assert pinned_uninspectable(msg, hidden), msg
    assert not says_remove_exact(msg, hidden), msg

    for d, snap in before.items():
        assert snapshot_tree(d) == snap, f"{d} changed on a stopped call"
    assert sorted(os.listdir(books_dir)) == listing0

    follow_message(msg, hidden)
    assert hidden.exists()
    assert snapshot_tree(hidden) == before[hidden]


@pytest.mark.parametrize("err", [errno.EIO, errno.EACCES, errno.ENOTDIR], ids=["e1", "e2", "e3"])
def test_w1_c19b_listing_errno(err, tmp_path, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    victim = forge_dead_run(out, v2_src, "built", suffix=a_reaped_pid())
    plain = forge_dead_run(out, v2_src, "rb_done")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3, "os", OsProxy(os, **listing_overrides(raise_on_listing(victim, err))))
        msg = str(expect_refusal(out, epub_v2, [victim, plain], ctx=f"C19b {err}"))

    assert victim in [t for line in msg.splitlines() for t in path_tokens(line)], msg
    assert errno_text_in(scrub(msg, tmp_path), err), msg
    assert pinned_uninspectable(msg, victim), msg
    assert not says_remove_exact(msg, victim), msg


@pytest.mark.parametrize("variant", ["gone_only", "gone_then_parked"])
def test_w1_c19c_vanished_leftover(variant, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    user0 = user_subset(snapshot_tree(out))
    gone = forge_dead_run(out, v2_src, "built", suffix=900001)
    if variant == "gone_only":
        other = forge_dead_run(out, v2_src, "rb_done", suffix=900002)
    else:
        other = forge_dead_run(out, v2_src, "after_D", suffix=900002)
    assert sorted([gone.name, other.name])[0] == gone.name
    listing0 = sorted(os.listdir(books_dir))
    out0, other0 = snapshot_tree(out), snapshot_tree(other)

    def vanish(p: str) -> None:
        if p == str(gone):
            shutil.rmtree(gone)
            os.listdir(gone)  # the real FileNotFoundError

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3, "os", OsProxy(os, **listing_overrides(vanish)))
        if variant == "gone_only":
            reader3.process_epub(str(epub_v2), str(out))
        else:
            with pytest.raises(RuntimeError) as excinfo:
                reader3.process_epub(str(epub_v2), str(out))

    if variant == "gone_only":
        assert assert_consistent(out, epub_v1, epub_v2) == MARKER_V2
        assert staging_leftovers(out) == []
        assert user_subset(snapshot_tree(out)) == user0
    else:
        msg = str(excinfo.value)
        assert {src for src, _ in parse_moves(msg)} == {
            str(other / "book.epub.superseded"),
            str(other / "images.superseded"),
        }, msg
        assert LOCK_MESSAGE not in msg, msg
        assert snapshot_tree(out) == out0
        assert snapshot_tree(other) == other0
        assert sorted(os.listdir(books_dir)) == sorted(set(listing0) - {gone.name})


C19D_ROLES = list(itertools.permutations(["unreadable", "parked", "plain"]))


@pytest.mark.parametrize("order", C19D_ROLES, ids=[f"perm{i}" for i in range(len(C19D_ROLES))])
def test_w1_c19d_all_classified_first(order, tmp_path, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    suffix = {role: 900001 + i for i, role in enumerate(order)}
    plain = forge_dead_run(out, v2_src, "built", suffix=suffix["plain"])
    unreadable = forge_dead_run(out, v2_src, "built", suffix=suffix["unreadable"])
    parked = forge_dead_run(out, v2_src, "after_D", suffix=suffix["parked"])

    with pytest.MonkeyPatch.context() as mp:
        fault = raise_on_listing(unreadable, errno.EIO)
        mp.setattr(reader3, "os", OsProxy(os, **listing_overrides(fault)))
        msg = str(expect_refusal(out, epub_v2, [unreadable, parked, plain], ctx=str(order)))

    assert unreadable in [t for line in msg.splitlines() for t in path_tokens(line)], msg
    assert errno_text_in(scrub(msg, tmp_path), errno.EIO), msg
    assert pinned_uninspectable(msg, unreadable), msg
    assert not says_remove_exact(msg, unreadable), msg
    assert {src for src, _ in parse_moves(msg)} == {
        str(parked / "book.epub.superseded"),
        str(parked / "images.superseded"),
    }, msg
    assert LOCK_MESSAGE not in msg, msg

    u0 = snapshot_tree(unreadable)
    follow_message(msg, unreadable)
    assert unreadable.exists()
    assert snapshot_tree(unreadable) == u0


@pytest.mark.parametrize("pair", [(900001, 900002), (900002, 900001)], ids=["lock_low", "lock_high"])
def test_w1_c19e_held_lock_first(pair, tmp_path, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    s1, s2 = pair
    held = forge_dead_run(out, v2_src, "build_mid", suffix=s1)
    unreadable = forge_dead_run(out, v2_src, "built", suffix=s2)
    fd = _hold(held / LOCK)
    try:
        with pytest.MonkeyPatch.context() as mp:
            fault = raise_on_listing(unreadable, errno.EIO)
            mp.setattr(reader3, "os", OsProxy(os, **listing_overrides(fault)))
            msg = str(expect_refusal(out, epub_v2, [held, unreadable], ctx=str(pair)))
    finally:
        _release(fd)
    assert LOCK_MESSAGE in msg, msg
    assert "mixed" not in scrub(msg, tmp_path).lower(), msg


@pytest.mark.parametrize("variant", ["own_digits", "not_own"])
def test_w1_c19f_file_shaped_leftover(variant, tmp_path, books_dir, epub_v1, epub_v2):
    out = make_seeded_book_dir(books_dir, epub_v1)
    if variant == "own_digits":
        f = Path(f"{out}.staging-{a_reaped_pid()}")
        f.write_bytes(b"not a dir")
        sha0 = sha256_of(f)
        msg = str(expect_refusal(out, epub_v2, [f], ctx=variant))
        assert f in [t for line in msg.splitlines() for t in path_tokens(line)], msg
        assert errno_text_in(scrub(msg, tmp_path), errno.ENOTDIR), msg
        assert pinned_uninspectable(msg, f), msg
        assert not says_remove_exact(msg, f), msg
        assert sha256_of(f) == sha0
    else:
        decoy = books_dir / "sample_data.staging-backup"
        decoy.write_bytes(b"not a dir")
        sha0 = sha256_of(decoy)
        clean_next_run_keeping(out, epub_v1, epub_v2, [str(decoy)])
        assert sha256_of(decoy) == sha0


# --------------------------------------------------------------------------- #
# W1-C20, C20b, C21: scope and disambiguate the steps (WI-1b, WI-1c)
# --------------------------------------------------------------------------- #

ODD = {
    "odd1": "notes.json.superseded",
    "odd2": "ai_meta.json.superseded",
    "odd3": "chroma_db.superseded",
    "odd4": ".superseded",
}


def _add_odd(dead: Path, name: str) -> Path:
    p = dead / name
    if name == "chroma_db.superseded":
        p.mkdir()
        (p / "x.bin").write_bytes(b"odd-index")
    else:
        p.write_bytes(f"odd:{name}".encode())
    return p


def _odd_state(p: Path) -> Any:
    if p.is_dir():
        return snapshot_tree(p)
    st_ = os.stat(p)
    return (sha256_of(p), st_.st_ino, st_.st_mtime_ns)


@pytest.mark.parametrize("odd", list(ODD))
def test_w1_c20_odd_aside_listed_only(odd, books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    dead = forge_dead_run(out, v2_src, "after_D")
    odd_path = _add_odd(dead, ODD[odd])
    odd_before = _odd_state(odd_path)

    msg = str(expect_refusal(out, epub_v2, [dead], ctx=odd))

    assert {src for src, _ in parse_moves(msg)} == {
        str(dead / "book.epub.superseded"),
        str(dead / "images.superseded"),
    }, msg
    for line in removal_lines(msg):
        for t in path_tokens(line):
            if under(t, out):
                assert t in {out / "book.epub", out / "images"}, (line, msg)
            assert t != out, (line, msg)
    assert odd_path in [t for line in msg.splitlines() for t in path_tokens(line)], msg
    assert not says_remove_exact(msg, dead), msg
    assert has_note(msg, dead, r"(?i)keep"), msg

    follow_message(msg, dead)
    assert snapshot_tree(out) == full_before
    assert _odd_state(odd_path) == odd_before
    assert dead.exists()

    msg2 = str(expect_refusal(out, epub_v2, [dead], ctx=f"{odd} again"))
    assert parse_moves(msg2) == [], msg2
    assert odd_path in [t for line in msg2.splitlines() for t in path_tokens(line)], msg2


def test_w1_c20b_odd_aside_alone(books_dir, epub_v1, epub_v2, v2_src):
    out = make_seeded_book_dir(books_dir, epub_v1)
    dead = forge_dead_run(out, v2_src, "built")
    odd_path = _add_odd(dead, "notes.json.superseded")

    e1 = expect_refusal(out, epub_v2, [dead], ctx="C20b")
    msg = str(e1)
    assert parse_moves(msg) == [], msg
    for line in removal_lines(msg):
        assert not [t for t in path_tokens(line) if under(t, out)], (line, msg)
    assert odd_path in [t for line in msg.splitlines() for t in path_tokens(line)], msg
    assert not says_remove_exact(msg, dead), msg
    assert has_note(msg, dead, r"(?i)keep"), msg

    e2 = expect_refusal(out, epub_v2, [dead], ctx="C20b again")
    assert str(e2) == msg


def _c21_scenario(books_dir: Path, epub_v1: Path, v2_src: Path, variant: str):
    out = make_seeded_book_dir(books_dir, epub_v1)
    d1 = forge_dead_run(out, v2_src, "after_D")
    drop = ["book.epub.superseded"] if variant == "images_only" else []
    d2 = forge_dead_run(out, v2_src, "after_D", suffix=a_reaped_pid(), drop=drop)
    return out, d1, d2


@pytest.mark.parametrize("variant", ["both", "images_only"])
def test_w1_c21_two_dead_runs_same_artifact(
    variant, tmp_path, books_dir, epub_v1, epub_v2, v2_src, roles
):
    out, d1, d2 = _c21_scenario(books_dir, epub_v1, v2_src, variant)
    msg = str(expect_refusal(out, epub_v2, [d1, d2], ctx=variant))
    moves = parse_moves(msg)

    assert not [m for m in moves if m[1] == str(out / "images")], msg
    assert not says_remove_exact(msg, out / "images"), msg
    if variant == "both":
        assert not says_remove_exact(msg, out / "book.epub"), msg
        assert moves == [], msg
    else:
        assert moves == [(str(d1 / "book.epub.superseded"), str(out / "book.epub"))], msg
        assert says_remove_exact(msg, out / "book.epub"), msg
    tokens = [t for line in msg.splitlines() for t in path_tokens(line)]
    assert d1 / "images.superseded" in tokens and d2 / "images.superseded" in tokens, msg
    assert re.search("(?i)inspect", scrub(msg, tmp_path)), msg
    assert not says_remove_exact(msg, d1) and not says_remove_exact(msg, d2), msg
    for d in (d1, d2):
        assert has_note(msg, d, r"(?i)keep"), (d, msg)

    images_before = {k: v for k, v in snapshot_tree(out).items() if k.startswith("images")}
    asides_before = {d: snapshot_tree(d / "images.superseded") for d in (d1, d2)}
    follow_exact(msg, [d1, d2])
    assert {k: v for k, v in snapshot_tree(out).items() if k.startswith("images")} == images_before
    for d, snap in asides_before.items():
        assert snapshot_tree(d / "images.superseded") == snap
    if variant == "images_only":
        assert roles.tree(out)["book.epub"] == "v1"

    # The substring-driven operator, on a fresh copy of the same scenario.
    books2 = tmp_path / "books2"
    books2.mkdir()
    out2, e1, e2 = _c21_scenario(books2, epub_v1, v2_src, variant)
    msg2 = str(expect_refusal(out2, epub_v2, [e1, e2], ctx=f"{variant} copy"))
    images2 = {k: v for k, v in snapshot_tree(out2).items() if k.startswith("images")}
    follow_message(msg2, e1)
    assert e1.is_dir() and (e1 / "images.superseded").is_dir()
    assert {k: v for k, v in snapshot_tree(out2).items() if k.startswith("images")} == images2


# --------------------------------------------------------------------------- #
# W1-C22, C22b: the message law over generated leftover sets
# --------------------------------------------------------------------------- #

C22_ASIDES = [
    "book.epub.superseded",
    "images.superseded",
    "notes.json.superseded",
    ".superseded",
    "chroma_db.superseded",
]
KNOWN_ASIDES = {"book.epub.superseded": "book.epub", "images.superseded": "images"}
DIR_ASIDES = {"images.superseded", "chroma_db.superseded"}
USER_BYTES = {"notes.json": b"user-notes", "ai_meta.json": b"user-meta", "chroma_db/db.bin": b"user-db"}


def _build_c22(root: Path, dirs: Sequence[Set[str]], occupied: Set[str]) -> Tuple[Path, List[Path]]:
    out = root / "books" / "s_data"
    (out / "chroma_db").mkdir(parents=True)
    for rel, data in USER_BYTES.items():
        (out / rel).write_bytes(data)
    if "book.epub" in occupied:
        (out / "book.epub").write_bytes(b"live-epub")
    if "images" in occupied:
        (out / "images").mkdir()
        (out / "images" / "live.png").write_bytes(b"live-image")
    leftovers = []
    for i, asides in enumerate(dirs):
        d = Path(f"{out}.staging-90000{i}")
        d.mkdir()
        (d / LOCK).touch()
        (d / "book.pkl").write_bytes(f"{i}:pkl".encode())
        for name in sorted(asides):
            data = f"{i}:{name}".encode()
            if name in DIR_ASIDES:
                (d / name).mkdir()
                (d / name / "f.bin").write_bytes(data)
            else:
                (d / name).write_bytes(data)
        leftovers.append(d)
    return out, leftovers


def _without_locks(tree: Dict[str, Any]) -> Dict[str, Any]:
    """018 WI-2 amendment: drop the book-lock dir `.locks/` (ADR-0015 contract item 1)."""
    return {k: v for k, v in tree.items() if k != ".locks/" and not k.startswith(".locks/")}


def _refuse_twice(out: Path, epub_v2: Path) -> str:
    msgs = []
    for _ in range(2):
        with pytest.raises(RuntimeError) as excinfo:
            reader3.process_epub(str(epub_v2), str(out))
        msgs.append(str(excinfo.value))
    assert msgs[0] == msgs[1]
    return msgs[0]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    dirs=st.lists(st.sets(st.sampled_from(C22_ASIDES), min_size=1), min_size=1, max_size=3),
    occupied=st.sets(st.sampled_from(["book.epub", "images"])),
)
def test_w1_c22_message_law(dirs, occupied, tmp_path, epub_v2):
    root = Path(tempfile.mkdtemp(dir=tmp_path))
    out, leftovers = _build_c22(root, dirs, occupied)
    books_before = _without_locks(snapshot_tree(root / "books"))

    msg = _refuse_twice(out, epub_v2)

    # 0. a refusal is side-effect-free
    assert _without_locks(snapshot_tree(root / "books")) == books_before
    # 0b. 018 WI-2 amendment: the one thing outside that comparison, `.locks/`, holds
    # nothing but lock files (ADR-0015 contract item 1).
    locks = root / "books" / ".locks"
    assert locks.is_dir()
    assert all(p.is_file() and p.name.endswith(".lock") for p in locks.iterdir()), sorted(
        p.name for p in locks.iterdir()
    )
    moves = parse_moves(msg)
    dsts = [Path(dst) for _, dst in moves]
    count = {a: sum(a in s for s in dirs) for a in KNOWN_ASIDES}
    # 1. only the two known live paths are ever move destinations
    assert set(dsts) <= {out / "book.epub", out / "images"}, msg
    # 2. no destination twice
    assert len(dsts) == len(set(dsts)), msg
    # 3. a move iff exactly one directory parks that artifact, from that directory
    for aside, live in KNOWN_ASIDES.items():
        got = [src for src, dst in moves if Path(dst) == out / live]
        if count[aside] == 1:
            owner = next(d for d, s in zip(leftovers, dirs) if aside in s)
            assert got == [str(owner / aside)], msg
        else:
            assert got == [], msg
    # 4. liveness
    for dst in dsts:
        if os.path.lexists(dst):
            assert says_remove_exact(msg, dst), (dst, msg)
    for d, s in zip(leftovers, dirs):
        if all(a in KNOWN_ASIDES and count[a] == 1 for a in s):
            assert says_remove_exact(msg, d), (d, msg)
        else:
            assert not says_remove_exact(msg, d), (d, msg)
            assert has_note(msg, d, r"(?i)keep"), (d, msg)
    # 5. safety: nothing under out is named for removal except a move destination
    for line in removal_lines(msg):
        for t in path_tokens(line):
            if under(t, out):
                assert t in dsts, (line, msg)
    # 6. every parked entry is listed
    tokens = {t for line in msg.splitlines() for t in path_tokens(line)}
    for d, s in zip(leftovers, dirs):
        for a in s:
            assert d / a in tokens, (d / a, msg)
    # 7. conservation under a strict operator
    parked = file_hashes([d / a for d, s in zip(leftovers, dirs) for a in s])
    follow_exact(msg, leftovers)
    kept = file_hashes([out, *[d for d in leftovers if d.exists()]])
    assert not parked - kept, (parked - kept, msg)
    for rel, data in USER_BYTES.items():
        assert (out / rel).read_bytes() == data


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    dirs=st.lists(st.sets(st.sampled_from(list(KNOWN_ASIDES)), min_size=1), min_size=1, max_size=3),
    occupied=st.sets(st.sampled_from(["book.epub", "images"])),
    odd=st.sampled_from(["notes.json.superseded", ".superseded", "chroma_db.superseded"]),
    data=st.data(),
)
def test_w1_c22b_odd_addition_relation(dirs, occupied, odd, data, tmp_path, epub_v2):
    k = data.draw(st.integers(0, len(dirs) - 1))
    root = Path(tempfile.mkdtemp(dir=tmp_path))
    out, leftovers = _build_c22(root, dirs, occupied)
    msg1 = _refuse_twice(out, epub_v2)
    _add_odd(leftovers[k], odd)
    msg2 = _refuse_twice(out, epub_v2)

    def live_named(msg: str) -> Set[Path]:
        return {
            t for line in removal_lines(msg) for t in path_tokens(line) if under(t, out)
        }

    def dirs_named(msg: str) -> Set[Path]:
        return {d for d in leftovers if says_remove_exact(msg, d)}

    assert set(parse_moves(msg2)) == set(parse_moves(msg1)), (msg1, msg2)
    assert live_named(msg2) == live_named(msg1), (msg1, msg2)
    assert dirs_named(msg2) == dirs_named(msg1) - {leftovers[k]}, (msg1, msg2)
    assert leftovers[k] / odd in {t for line in msg2.splitlines() for t in path_tokens(line)}


# --------------------------------------------------------------------------- #
# W1-C23: makedirs(images) failure releases the lock (WI-1e)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "fault",
    [OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)), KeyboardInterrupt()],
    ids=["f1", "f2"],
)
def test_w1_c23_images_dir_fault(fault, books_dir, epub_v1, epub_v2):
    out = make_seeded_book_dir(books_dir, epub_v1)
    before = snapshot_tree(out)
    user0 = user_subset(before)
    staging = str(staging_of(out))

    def makedirs(p: Any, *a: Any, **kw: Any) -> None:
        p = os.fspath(p)
        if os.path.basename(p) == "images" and os.path.dirname(p) == staging:
            raise fault
        os.makedirs(p, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader3, "os", OsProxy(os, makedirs=makedirs))
        fds0 = len(os.listdir("/dev/fd"))
        with pytest.raises(type(fault)) as excinfo:
            reader3.process_epub(str(epub_v2), str(out))
        fds1 = len(os.listdir("/dev/fd"))

    if isinstance(fault, OSError):
        assert excinfo.value.errno == errno.ENOSPC
    assert staging_leftovers(out) == []
    assert fds1 == fds0
    assert snapshot_tree(out) == before
    clean_next_run(out, epub_v1, epub_v2, "C23")
    assert user_subset(snapshot_tree(out)) == user0


# --------------------------------------------------------------------------- #
# W1-C24..C27: commit-failure staging retention (Amendment 1, WI-1(f))
# --------------------------------------------------------------------------- #


class CommitFaults:
    """One forward fault in the commit, optionally one fault in its rollback.

    Steps are matched by exact ``(src, dst)`` paths, never by substring:
    A/B park the live epub/images, C/D land the new ones, F is the first fsync
    of ``out`` (F2 the second, after the marker), E is the marker rename. The
    forward fault raises before the real call, so the step has no effect.
    """

    def __init__(
        self,
        out: Path,
        step: Optional[str],
        restore: str = "none",
        *,
        on_step: Optional[Callable[[], None]] = None,
        unlistable_after_start: bool = False,
        on_rmtree_staging: Optional[Callable[[], None]] = None,
    ):
        self.out = Path(out)
        self.staging = staging_of(self.out)
        self.step = step
        self.restore = restore
        self.on_step = on_step
        self.unlistable_after_start = unlistable_after_start
        self.on_rmtree_staging = on_rmtree_staging
        self.boom = OSError(errno.EIO, "commit-fault-sentinel")
        self.step_fired = False
        self.restore_fired = False
        self.commit_started = False
        self.out_fsyncs = 0

    def install(self, mp: pytest.MonkeyPatch) -> None:
        mp.setattr(
            reader3,
            "os",
            OsProxy(
                os,
                replace=self._replace,
                fsync=self._fsync,
                unlink=self._unlink,
                remove=self._unlink,
                **listing_overrides(self._listing),
            ),
        )
        mp.setattr(reader3, "shutil", ShutilProxy(shutil, rmtree=self._rmtree))

    def _forward(self) -> None:
        self.step_fired = True
        if self.on_step is not None:
            self.on_step()
        raise self.boom

    def _restore_fault(self) -> None:
        self.restore_fired = True
        raise OSError(errno.EIO, "restore-fault-sentinel")

    def _replace(self, src: Any, dst: Any, *a: Any, **kw: Any) -> None:
        s, d = Path(os.fspath(src)), Path(os.fspath(dst))
        st_, out = self.staging, self.out
        if d == st_ / "book.epub.superseded":
            self.commit_started = True
        if not self.step_fired:
            hit = {
                "A": d == st_ / "book.epub.superseded",
                "B": d == st_ / "images.superseded",
                "C": s == st_ / "book.epub" and d == out / "book.epub",
                "D": s == st_ / "images" and d == out / "images",
                "E": d == out / "book.pkl",
            }.get(self.step or "", False)
            if hit:
                self._forward()
        elif self.restore in ("rep_epub", "rep_images") and not self.restore_fired:
            name = "book.epub" if self.restore == "rep_epub" else "images"
            if s == st_ / f"{name}.superseded":
                self._restore_fault()
        os.replace(src, dst, *a, **kw)

    def _fsync(self, fd: int) -> None:
        try:
            is_out = os.path.samestat(os.fstat(fd), os.stat(self.out))
        except OSError:
            is_out = False
        if is_out:
            self.out_fsyncs += 1
            if not self.step_fired and (
                (self.step == "F" and self.out_fsyncs == 1)
                or (self.step == "F2" and self.out_fsyncs == 2)
            ):
                self._forward()
        os.fsync(fd)

    def _unlink(self, path: Any, *a: Any, **kw: Any) -> None:
        if (
            self.step_fired
            and self.restore == "dis_epub"
            and Path(os.fspath(path)) == self.out / "book.epub"
        ):
            self._restore_fault()
        os.unlink(path, *a, **kw)

    def _rmtree(self, path: Any, *a: Any, **kw: Any) -> None:
        p = Path(os.fspath(path))
        if self.step_fired and self.restore == "dis_images" and p == self.out / "images":
            self._restore_fault()
        if p == self.staging and self.on_rmtree_staging is not None:
            self.on_rmtree_staging()
        shutil.rmtree(path, *a, **kw)

    def _listing(self, p: str) -> None:
        if self.unlistable_after_start and self.commit_started and p == str(self.staging):
            raise OSError(errno.EIO, os.strerror(errno.EIO), p)


C24_STEPS = ("A", "B", "C", "D", "F", "E")
C24_RESTORES = ("none", "rep_epub", "rep_images", "dis_epub", "dis_images")


def _commit_shape(shape: str, books_dir: Path, epub_v1: Path) -> Path:
    if shape == "absent":
        return books_dir / "sample_data"
    out = make_seeded_book_dir(books_dir, epub_v1)
    if shape == "bare_epub":
        (out / "book.epub").unlink()
    elif shape == "bare_images":
        shutil.rmtree(out / "images")
    elif shape == "user_files":
        (out / "notes.json").write_text('{"notes": [{"id": "extra"}]}', encoding="utf-8")
        (out / "chroma_db" / "extra.bin").write_bytes(b"extra index segment")
    return out


def _step_unreachable(shape: str, step: str) -> bool:
    # Revision 3: with no live artifact there is no aside rename to fault.
    return (step == "A" and shape in ("bare_epub", "absent")) or (
        step == "B" and shape in ("bare_images", "absent")
    )


def _v1_hashes(out: Path) -> Counter:
    roots = [p for p in (out / "book.epub", out / "images") if p.exists()]
    return file_hashes(roots)


def _asides_intact(staging: Path, full_before: Dict[str, Tuple]) -> None:
    epub = staging / "book.epub.superseded"
    if epub.exists():
        assert os.stat(epub).st_ino == full_before["book.epub"][3]
        assert sha256_of(epub) == full_before["book.epub"][0]
    images = staging / "images.superseded"
    if images.exists():
        assert os.stat(images).st_ino == full_before["images/"][3]
        expected = {
            k[len("images/"):]: v for k, v in full_before.items()
            if k.startswith("images/") and k != "images/"
        }
        assert snapshot_tree(images) == expected


def _run_faulted(faults: CommitFaults, out: Path, epub_v2: Path, capsys) -> Tuple[Any, str, int, int]:
    capsys.readouterr()
    with pytest.MonkeyPatch.context() as mp:
        faults.install(mp)
        fds0 = len(os.listdir("/dev/fd"))
        with pytest.raises(OSError) as excinfo:
            reader3.process_epub(str(epub_v2), str(out))
        fds1 = len(os.listdir("/dev/fd"))
    return excinfo, capsys.readouterr().err, fds0, fds1


@pytest.mark.parametrize("shape", ["seeded", "bare_epub", "bare_images"])
def test_w1_c24_commit_x_restore_faults(shape, tmp_path, epub_v1, epub_v2, capsys):
    combos = 0
    for step in C24_STEPS:
        if _step_unreachable(shape, step):
            continue
        for restore in C24_RESTORES:
            if (restore == "dis_epub" and shape == "bare_epub") or (
                restore == "dis_images" and shape == "bare_images"
            ):
                continue
            combos += 1
            ctx = f"{shape}/{step}/{restore}"
            books = Path(tempfile.mkdtemp(dir=tmp_path)) / "books"
            books.mkdir()
            out = _commit_shape(shape, books, epub_v1)
            full_before = snapshot_tree(out)
            v1 = _v1_hashes(out)
            faults = CommitFaults(out, step, restore)

            excinfo, err, fds0, fds1 = _run_faulted(faults, out, epub_v2, capsys)

            assert faults.step_fired, f"{ctx}: matrix error, the step never ran"
            assert excinfo.value is faults.boom, ctx
            assert fds1 == fds0, ctx
            lost = v1 - file_hashes([out, *map(Path, staging_leftovers(out))])
            assert not lost, f"{ctx}: parked bytes lost: {lost}"
            staging = faults.staging
            if not faults.restore_fired:
                assert snapshot_tree(out) == full_before, ctx
                assert staging_leftovers(out) == [], ctx
                continue
            assert staging.is_dir(), ctx
            assert reader3._staging_dir_is_owned(str(staging)) is False, ctx
            _asides_intact(staging, full_before)
            assert len(stderr_lines_naming(err, staging)) >= 1, (ctx, err)

            msg = str(expect_refusal(out, epub_v2, [staging], ctx=ctx))
            follow_message(msg, staging)
            assert snapshot_tree(out) == full_before, ctx
            assert staging_leftovers(out) == [], ctx
    assert combos == {"seeded": 30, "bare_epub": 20, "bare_images": 20}[shape]


def test_w1_c24b_restore_fault_representative(books_dir, epub_v1, epub_v2, capsys):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    user0 = user_subset(full_before)
    faults = CommitFaults(out, "E", "rep_images")
    staging = faults.staging

    excinfo, err, _, _ = _run_faulted(faults, out, epub_v2, capsys)

    assert excinfo.value is faults.boom
    lines = stderr_lines_naming(err, staging)
    assert lines, err
    assert any(
        re.search(r"(?i)\bkept\b", words(line))
        and re.search(r"(?i)only copy", words(line))
        and not REMOVE_WORD.search(words(line))
        for line in lines
    ), err
    assert any(
        "could not restore" in line and out / "images" in path_tokens(line)
        for line in err.splitlines()
    ), err

    assert reader3._staging_dir_is_owned(str(staging)) is False
    assert os.stat(staging / "images.superseded").st_ino == full_before["images/"][3]
    # Pinned (Revision 3): the rollback carries on past a failed restore.
    assert not (staging / "book.epub.superseded").exists()
    assert sha256_of(out / "book.epub") == full_before["book.epub"][0]

    msg = str(expect_refusal(out, epub_v2, [staging], ctx="C24b"))
    parked = {str(staging / n) for n in os.listdir(staging) if n.endswith(".superseded")}
    assert {src for src, _ in parse_moves(msg)} == parked, msg
    follow_message(msg, staging)
    assert snapshot_tree(out) == full_before

    clean_next_run(out, epub_v1, epub_v2, "C24b")
    assert user_subset(snapshot_tree(out)) == user0


def test_w1_c24c_restore_fault_real_mode(books_dir, epub_v1, epub_v2, capsys):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory modes")
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    faults = CommitFaults(out, "E", "none", on_step=lambda: os.chmod(out, 0o500))
    staging = faults.staging
    try:
        excinfo, err, _, _ = _run_faulted(faults, out, epub_v2, capsys)
    finally:
        os.chmod(out, 0o700)

    assert excinfo.value is faults.boom
    assert any(re.search(r"(?i)\bkept\b", words(line)) for line in stderr_lines_naming(err, staging)), err
    assert staging.is_dir()
    assert reader3._staging_dir_is_owned(str(staging)) is False
    assert (staging / "book.epub.superseded").exists() and (staging / "images.superseded").exists()
    _asides_intact(staging, full_before)

    msg = str(expect_refusal(out, epub_v2, [staging], ctx="C24c"))
    follow_message(msg, staging)
    assert snapshot_tree(out) == full_before


@pytest.mark.parametrize("shape", ["seeded", "bare_epub", "bare_images", "absent", "user_files"])
def test_w1_c25_full_rollback_clears_staging(shape, tmp_path, epub_v1, epub_v2, capsys):
    for step in C24_STEPS:
        if _step_unreachable(shape, step):
            continue
        ctx = f"{shape}/{step}"
        books = Path(tempfile.mkdtemp(dir=tmp_path)) / "books"
        books.mkdir()
        out = _commit_shape(shape, books, epub_v1)
        full_before = snapshot_tree(out)
        faults = CommitFaults(out, step, "none")

        excinfo, err, fds0, fds1 = _run_faulted(faults, out, epub_v2, capsys)

        assert faults.step_fired, f"{ctx}: matrix error, the step never ran"
        assert excinfo.value is faults.boom, ctx
        assert stderr_lines_naming(err, faults.staging) == [], (ctx, err)
        assert staging_leftovers(out) == [], ctx
        assert snapshot_tree(out) == full_before, ctx
        assert fds1 == fds0, ctx
        clean_next_run(out, epub_v1, epub_v2, ctx)


@pytest.mark.parametrize("variant", ["ok", "after_marker"])
def test_w1_c26_staging_after_marker(variant, books_dir, epub_v1, epub_v2, capsys):
    out = make_seeded_book_dir(books_dir, epub_v1)
    seen: List[List[str]] = []
    staging = staging_of(out)
    faults = CommitFaults(
        out,
        "F2" if variant == "after_marker" else None,
        on_rmtree_staging=lambda: seen.append(sorted(os.listdir(staging))),
    )
    capsys.readouterr()
    with pytest.MonkeyPatch.context() as mp:
        faults.install(mp)
        if variant == "ok":
            reader3.process_epub(str(epub_v2), str(out))
        else:
            with pytest.raises(OSError) as excinfo:
                reader3.process_epub(str(epub_v2), str(out))
            # Pinned (Revision 3): a fault after the marker is re-raised.
            assert excinfo.value is faults.boom
    err = capsys.readouterr().err

    assert assert_consistent(out, epub_v1, epub_v2) == MARKER_V2
    assert seen and {"book.epub.superseded", "images.superseded"} <= set(seen[-1]), seen
    assert staging_leftovers(out) == []
    assert stderr_lines_naming(err, staging) == [], err
    clean_next_run(out, epub_v1, epub_v2, variant)


C27_VARIANTS = {
    "after_rollback_fault": ("E", "rep_images"),
    "after_clean_rollback": ("E", "none"),
    "after_success": (None, "none"),
}


@pytest.mark.parametrize("variant", list(C27_VARIANTS))
def test_w1_c27_staging_unlistable_at_exit(variant, books_dir, epub_v1, epub_v2, capsys):
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    step, restore = C27_VARIANTS[variant]
    faults = CommitFaults(out, step, restore, unlistable_after_start=True)
    staging = faults.staging

    capsys.readouterr()
    with pytest.MonkeyPatch.context() as mp:
        faults.install(mp)
        if variant == "after_success":
            reader3.process_epub(str(epub_v2), str(out))
        else:
            with pytest.raises(OSError) as excinfo:
                reader3.process_epub(str(epub_v2), str(out))
            assert excinfo.value is faults.boom
    err = capsys.readouterr().err

    assert faults.commit_started
    assert any(
        re.search(r"(?i)\bkept\b", words(line))
        and errno_text_in(words(line), errno.EIO)
        and not REMOVE_WORD.search(words(line))
        for line in stderr_lines_naming(err, staging)
    ), err
    assert staging.is_dir()
    assert reader3._staging_dir_is_owned(str(staging)) is False

    if variant == "after_rollback_fault":
        msg = str(expect_refusal(out, epub_v2, [staging], ctx=variant))
        follow_message(msg, staging)
        assert snapshot_tree(out) == full_before
    else:
        clean_next_run(out, epub_v1, epub_v2, variant)


def test_w1_c27b_staging_unlistable_real_mode(books_dir, epub_v1, epub_v2, capsys):
    if os.geteuid() == 0:
        pytest.skip("root reads a mode-000 directory")
    out = make_seeded_book_dir(books_dir, epub_v1)
    full_before = snapshot_tree(out)
    staging = staging_of(out)
    faults = CommitFaults(out, "E", "none", on_step=lambda: os.chmod(staging, 0o000))
    try:
        excinfo, err, _, _ = _run_faulted(faults, out, epub_v2, capsys)
    finally:
        if staging.exists():
            os.chmod(staging, 0o700)

    assert excinfo.value is faults.boom
    assert any(
        re.search(r"(?i)\bkept\b", words(line)) and errno_text_in(words(line), errno.EACCES)
        for line in stderr_lines_naming(err, staging)
    ), err
    assert staging.is_dir()
    assert (staging / "book.epub.superseded").exists() and (staging / "images.superseded").exists()
    _asides_intact(staging, full_before)

    msg = str(expect_refusal(out, epub_v2, [staging], ctx="C27b"))
    follow_message(msg, staging)
    assert snapshot_tree(out) == full_before
