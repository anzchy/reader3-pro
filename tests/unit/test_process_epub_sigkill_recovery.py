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
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pytest

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
