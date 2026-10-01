"""seek: chapters are addressable by byte offset (non-ASCII, so bytes != chars).
liveview: what an unlocked concurrent reader sees at every hook point (informational for A)."""
import json
import os

import pytest

from proto import common as c
from proto import harness as h


@pytest.mark.parametrize("mech", ["A", "B"])
def test_q2_seek_every_chapter_by_offset(tmp_path, mech):
    book = h.setup(mech, "S1", str(tmp_path))
    h.MECH[mech]["publish"](book, c.book_contents(c.NEW))
    manifest = c.load_manifest(book)
    root = c.resolve_root(book, mech, manifest)
    raw = c.read_bytes(os.path.join(root, c.CHAPTERS))
    text_offsets = [len(x) for x in raw.decode().splitlines(keepends=True)]
    byte_offsets = [len(x) for x in raw.splitlines(keepends=True)]
    assert text_offsets != byte_offsets  # the fixture really exercises byte offsets
    for e in manifest["chapters"]:
        obj = c.read_chapter(manifest, root, e["id"])
        assert obj == json.loads(raw[e["offset_bytes"]:e["offset_bytes"] + e["length_bytes"]])
        assert c.NEW in obj["text"]


def test_q2_every_new_valid_cell_passed_the_seek_check(results):
    new = [x for x in results.cells if x.state == "new-valid"]
    assert new and all(x.verdict == "PASS" for x in new)  # judge() runs seek_ok on every one


def test_q2_liveview_b_is_snapshot_consistent(results):
    b = [r for r in results.live if r.mech == "B"]
    assert b and {r.state for r in b} <= {"missing", "old-valid", "new-valid"}


def test_q2_liveview_a_exposes_transient_states(results):
    """Documented, not a failure: A's flat layout is visibly mixed during a8/a9."""
    a = [r for r in results.live if r.mech == "A"]
    corrupt = {(r.scenario, r.step.split(".")[0]) for r in a if r.state == "corrupt"}
    assert {("S1", "a8"), ("S1", "a9"), ("S2", "a9")} <= corrupt
    assert all(r.step.startswith(("a8", "a9", "a10")) for r in a if r.state == "corrupt")
    early = {(r.scenario, r.step) for r in a if r.state == "pkl-only-new"}
    assert ("S0", "a10") in early  # dual-write pkl visible via missing->pkl before the marker
    s3_missing = [r for r in a if r.scenario == "S3" and r.state == "missing"]
    assert s3_missing  # a legacy book transiently disappears from a reader's view
