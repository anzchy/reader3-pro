"""Crash matrix: kill / raise / raise+undofail / recoverykill / exdev-simulated / wi7-reuse.

One parametrized test per (mechanism, mode, scenario); the per-step rows are in MATRIX.md.
"""
import pytest

import gen_matrix
from proto import harness as h

GROUPS = (
    [("A", m, s) for m in ("kill", "raise", "exdev-simulated") for s in h.SCENARIOS]
    + [("A", f"raise+undofail{k}", s) for k in (1, 2) for s in ("S1", "S2", "S3")]
    + [("A", "recoverykill", s) for s in h.RECOVERYKILL["A"]]
    + [("B", m, s) for m in ("kill", "raise", "exdev-simulated") for s in h.SCENARIOS]
    + [("B", "recoverykill", s) for s in h.RECOVERYKILL["B"]]
    + [("B-core(index)", "kill", s) for s in ("I-old", "I-empty")]
)


@pytest.mark.parametrize("mech,mode,scenario", GROUPS, ids=["-".join(g) for g in GROUPS])
def test_q2_cells(results, mech, mode, scenario):
    cells = [x for x in results.cells if (x.mech, x.mode, x.scenario) == (mech, mode, scenario)]
    assert cells, "group produced no cells"
    bad = [x for x in cells if x.verdict != "PASS"]
    assert not bad, bad[:5]


def test_q2_every_crash_point_is_covered(results):
    """kill and raise each cover every hook point the publish reaches, both mechanisms."""
    for mech in h.MECH:
        for scen in h.SCENARIOS:
            n = len(h.publish_points(mech, scen))
            for mode in ("kill", "raise"):
                got = [x for x in results.cells if (x.mech, x.mode, x.scenario) == (mech, mode, scen)]
                assert len(got) == n


def test_q2_no_corrupt_no_residue_user_intact(results):
    assert not [x for x in results.cells if x.state == "corrupt"]
    assert not [x for x in results.cells if x.residue]
    assert not [x for x in results.cells if x.user == "NO"]
    both = {x.state for x in results.cells if x.mech in ("A", "B")}
    assert both == {"missing", "old-valid", "new-valid"}


def test_q2_exdev_surface(results):
    """B makes exactly one rename per publish (the pointer); A makes 2 + 2*existing artifacts."""
    for scen in h.SCENARIOS:
        b = [x for x in results.cells if (x.mech, x.mode, x.scenario) == ("B", "exdev-simulated", scen)]
        assert [x.step for x in b] == ["rename#1@b8"]
    a = [x for x in results.cells if (x.mech, x.mode, x.scenario) == ("A", "exdev-simulated", "S1")]
    assert len(a) == 10  # journal + 4 asides + 4 staged + manifest


def test_q2_matrix_is_current(results):
    with open(gen_matrix.MATRIX, encoding="utf-8") as f:
        committed = f.read()
    assert gen_matrix.render(results) == committed, "MATRIX.md is stale: rerun gen_matrix.py"
