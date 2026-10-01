"""dim 4: one generation core drives both the book (B) and a fake WI-7 index.
The kill cells are in the matrix (mechanism B-core(index)); here, the structural claim."""
import inspect

from proto import fake_index, generation_core, mech_b_generation


def test_q2_book_and_index_share_one_core():
    for mod in (fake_index, mech_b_generation):
        src = inspect.getsource(mod)
        assert "publish_generation" in src and "recover_generations" in src
        assert "os.replace" not in src  # the only commit rename lives in generation_core
    assert inspect.getsource(generation_core).count("os.replace(") == 1


def test_q2_index_cells_cover_both_starts(results):
    idx = [x for x in results.cells if x.mech == "B-core(index)"]
    assert {x.scenario for x in idx} == {"I-old", "I-empty"}
    assert {x.state for x in idx} == {"fp-old", "fp-new", "missing"}
    assert all(x.verdict == "PASS" and x.residue == 0 for x in idx)
