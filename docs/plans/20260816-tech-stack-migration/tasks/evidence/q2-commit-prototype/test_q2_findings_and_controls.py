"""Findings the prototype surfaced, plus negative controls proving the classifier has teeth."""
import os
from unittest import mock

import pytest

from proto import common as c
from proto import harness as h
from proto import mech_a_journal as ma


def _kill_then(mech, scenario, base, step, when, recover=True):
    book = h.setup(mech, scenario, base)
    rc = h.run_cli("publish", mech.lower(), book, c.NEW, "1", crash=f"{mech.lower()}:{step}:{when}:kill")
    assert rc == 137
    if recover:
        h.MECH[mech]["recover"](book)
    return book


def test_q2_control_unrecovered_mid_window_kill_is_corrupt(tmp_path):
    """Today's situation (in-memory undo only): SIGKILL inside the window, nobody recovers."""
    book = _kill_then("A", "S2", str(tmp_path), "a9.images", "after", recover=False)
    assert c.classify(book, "A")[0] == "corrupt"


def test_q2_control_rollback_that_skips_new_artifacts_leaves_mixed_state(tmp_path):
    """Q2's 'rollback failed to discard artifacts that did not exist before': drop that branch
    from recovery and the S2 cell turns into the mixed state."""
    book = _kill_then("A", "S2", str(tmp_path), "a9.images", "after", recover=False)
    journal = ma.json.loads(c.read_bytes(os.path.join(book, ma.JOURNAL)))
    for e in journal["artifacts"]:
        e["existed"] = True  # pretend every artifact existed -> images/ has no aside -> left in place
    c.write_bytes(os.path.join(book, ma.JOURNAL), ma.json.dumps(journal).encode())
    ma.recover_a(book)
    state, residue = c.classify(book, "A")
    assert state == "corrupt"


@pytest.mark.parametrize("embed_txid,want", [(True, "new-valid"), (False, "corrupt")])
def test_q2_finding_a_commit_identity_must_be_per_transaction(tmp_path, embed_txid, want):
    """FINDING (A): recovery decides 'committed?' by live-manifest sha == journal sha. Republishing
    byte-identical content makes old and new manifests equal unless the manifest carries the txid;
    a kill mid-window is then misread as committed, rolled FORWARD, and the asides are deleted."""
    book = h.setup("A", "S0u", str(tmp_path))
    ma.publish_a(book, c.book_contents(c.NEW), embed_txid=embed_txid)
    c.set_crash("a:a9.book.epub:before:raise")
    try:
        with pytest.raises(c.InjectedCrash), mock.patch.object(ma, "recover_a", lambda b: "skipped"):
            ma.publish_a(book, c.book_contents(c.NEW), embed_txid=embed_txid)  # simulate SIGKILL: no rollback
    finally:
        c.set_crash(None)
    ma.recover_a(book)
    assert c.classify(book, "A")[0] == want


def test_q2_s0_half_born_dir_classifies_missing(tmp_path):
    """A first publish killed early leaves only .staging/ or gen/ (+ B's pointer tmp): 'missing'."""
    for mech, step in (("A", "a6"), ("B", "b6")):
        book = _kill_then(mech, "S0", str(tmp_path / mech), step, "after", recover=False)
        leftovers = set(os.listdir(book))
        assert leftovers == ({".staging"} if mech == "A" else {c.GEN, "manifest.json.tmp"})
        assert c.classify(book, mech)[0] == "missing"


@pytest.mark.parametrize("step", ["b3", "b6", "b8"])
def test_q2_b_failed_cleanup_is_only_garbage(tmp_path, step):
    """B's analogue of raise+undofail: the in-process cleanup itself fails. Nothing live was
    touched, so a fresh-process recover just garbage-collects the unreferenced generation."""
    book = h.setup("B", "S1", str(tmp_path))
    snap = h.user_snapshot(book)
    c.set_crash(f"b:{step}:before:raise")
    try:
        with mock.patch.object(c, "discard", side_effect=OSError("injected cleanup failure")), \
                pytest.raises(OSError):
            h.MECH["B"]["publish"](book, c.book_contents(c.NEW))
    finally:
        c.set_crash(None)
    assert c.classify(book, "B")[0] == "old-valid"  # readers never noticed
    assert h.run_cli("recover", "b", book) == 0
    assert c.classify(book, "B") == ("old-valid", 0)
    assert h.user_snapshot(book) == snap
