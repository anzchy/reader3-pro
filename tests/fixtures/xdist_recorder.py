"""pytest plugin for `test_xdist_collection_parity.py` (013 WI-9 A9.9, C9.35). Load with `-p xdist_recorder`.

It records which worker was handed which node id, then **claims the run protocol without
running anything**: no fixture is set up, no test body executes, no server or browser
starts. What remains is exactly the distribution xdist performed, which is the thing
§5.0's partition check is about.

Output: one file per worker, `$XDIST_RECORDER_DIR/<worker>.txt`, one node id per line.
Without xdist the worker name is `main`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):  # noqa: ARG001 - hook signature
    out_dir = Path(os.environ["XDIST_RECORDER_DIR"])
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    with (out_dir / f"{worker}.txt").open("a", encoding="utf-8") as fh:
        fh.write(item.nodeid + "\n")
    return True
