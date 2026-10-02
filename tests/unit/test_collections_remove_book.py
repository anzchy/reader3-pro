"""018 WI-5a: ``collections_service.remove_book_everywhere`` (matrix cases CO-1, CO-2).

The new function is looked up with ``getattr`` at call time so the file collects
before it exists (the red is an ``AttributeError`` inside each test).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from delete_world import SUBPROCESS_TIMEOUT_S, child_env, read_collections, write_collections
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

BOOK_IDS = st.sampled_from(["a_data", "b_data", "c_data"])
MAPPINGS = st.lists(st.lists(BOOK_IDS, max_size=5), max_size=4).map(lambda lists: {f"c{i}": ids for i, ids in enumerate(lists)})


def _remove(path, book_id):
    from reader3_app import collections_service

    fn = getattr(collections_service, "remove_book_everywhere")
    return fn(Path(path), book_id)


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(mapping=MAPPINGS, b=st.sampled_from(["a_data", "zz_data"]))
def test_co1_remove_everywhere_property(tmp_path, mapping, b):
    """CO-1: equals a filter of every list (order kept, empty lists kept), idempotent, no-op rewrite-free."""
    path = Path(tempfile.mkdtemp(dir=tmp_path)) / "config" / "library_collections.json"
    write_collections(path, mapping)
    original = path.read_bytes()
    st0 = os.stat(path)
    present = any(b in ids for ids in mapping.values())

    _remove(path, b)

    assert read_collections(path) == {cid: [x for x in ids if x != b] for cid, ids in mapping.items()}
    after_first = path.read_bytes()
    raw = json.loads(after_first)
    assert [c["id"] for c in raw["collections"]] == list(mapping)
    if not present:
        st1 = os.stat(path)
        assert after_first == original
        assert st1.st_mtime_ns == st0.st_mtime_ns

    _remove(path, b)

    assert path.read_bytes() == after_first


def test_co2a_missing_file_is_tolerated_and_not_created(tmp_path):
    """CO-2(a): no collections file -> no error and no file created."""
    path = tmp_path / "config" / "library_collections.json"

    _remove(path, "a_data")

    assert not path.exists()


LOCK_HOLDER = """
import fcntl, os, sys, time
lock_path, ready = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(lock_path), exist_ok=True)
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
with open(ready, "w") as f:
    f.write("locked")
time.sleep(0.5)
fcntl.flock(fd, fcntl.LOCK_UN)
os.close(fd)
"""


def test_co2b_remove_everywhere_takes_the_collections_lock(tmp_path):
    """CO-2(b): a child holding LOCK_EX on the ``.lock`` for 0.5 s makes the removal wait (>= 0.4 s)."""
    from reader3_app import collections_service

    path = tmp_path / "config" / "library_collections.json"
    write_collections(path, {"c1": ["a_data", "b_data"], "c2": ["a_data"]})
    lock_path = path.parent / collections_service.COLLECTIONS_LOCK_FILENAME
    ready = tmp_path / "ready"
    fn = getattr(collections_service, "remove_book_everywhere")

    proc = subprocess.Popen(
        [sys.executable, "-c", LOCK_HOLDER, str(lock_path), str(ready)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_env(),
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists():
            assert proc.poll() is None, "the lock-holder child exited before locking"
            assert time.monotonic() < deadline, "the lock-holder child never locked"
            time.sleep(0.01)
        t0 = time.monotonic()
        fn(path, "a_data")
        elapsed = time.monotonic() - t0
    finally:
        try:
            proc.communicate(timeout=SUBPROCESS_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=10)

    assert elapsed >= 0.4, f"the removal did not wait for the collections lock ({elapsed:.3f}s)"
    assert read_collections(path) == {"c1": ["b_data"], "c2": []}
