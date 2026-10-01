"""ADR-0007 step 6: a bad staged chapters file or a wrong offset fails readback before any
live rename, and the book dir is byte + inode + mtime_ns identical to before (both mechanisms).
Directory mtimes are excluded: staging / gen/<g> is created and removed inside the book dir.
"""
import glob
import json
import os

import pytest

from proto import common as c
from proto import harness as h


def _staged_paths(mech, book):
    if mech == "A":
        stage = glob.glob(os.path.join(book, ".staging", "*"))[0]
        return os.path.join(stage, "chapters.jsonl.tmp"), os.path.join(stage, "manifest.json.tmp")
    gens = sorted(os.listdir(os.path.join(book, c.GEN)), key=int)
    return os.path.join(book, c.GEN, gens[-1], c.CHAPTERS), os.path.join(book, "manifest.json.tmp")


def _flip_byte(chapters, _manifest):
    data = bytearray(c.read_bytes(chapters))
    data[5] ^= 0x01
    c.write_bytes(chapters, bytes(data))


def _wrong_offset(_chapters, manifest):
    doc = json.loads(c.read_bytes(manifest))
    doc["chapters"][1]["offset_bytes"] += 1
    c.write_bytes(manifest, json.dumps(doc).encode())


@pytest.mark.parametrize("damage", [_flip_byte, _wrong_offset], ids=["flipped-byte", "wrong-offset"])
@pytest.mark.parametrize("scenario", ["S0u", "S1", "S2", "S3"])
@pytest.mark.parametrize("mech", ["A", "B"])
def test_q2_step6_failure_leaves_book_dir_identical(tmp_path, mech, scenario, damage):
    book = h.setup(mech, scenario, str(tmp_path))
    before = c.snapshot_tree(book)
    state_before = c.classify(book, mech)
    label = h.MECH[mech]["label"]

    def obs(m, s, w):
        if m == label and s == f"{label}5" and w == "after":
            damage(*_staged_paths(mech, book))

    with c.observing(obs), pytest.raises(c.ReadbackError):
        h.MECH[mech]["publish"](book, c.book_contents(c.NEW))
    assert c.snapshot_tree(book) == before
    assert c.classify(book, mech) == state_before
