"""dim 5. The simulated-EXDEV cells live in the crash matrix (mode exdev-simulated). Here:
the same-device enforcer refuses before step 1, and an optional REAL cross-device run."""
import errno
import os

import pytest

from proto import common as c
from proto import harness as h


@pytest.mark.parametrize("mech", ["A", "B"])
def test_q2_same_device_check_refuses_before_step1(tmp_path, monkeypatch, mech):
    book = h.setup(mech, "S1", str(tmp_path))
    before = c.snapshot_tree(book)
    real_stat = os.stat
    parent = ".staging" if mech == "A" else c.GEN

    class Fake:
        def __init__(self, st):
            self._st = st
            self.st_dev = st.st_dev + 1

        def __getattr__(self, name):
            return getattr(self._st, name)

    monkeypatch.setattr(os, "stat", lambda p, *a, **kw: (
        Fake(real_stat(p, *a, **kw)) if os.path.basename(os.fspath(p)) == parent else real_stat(p, *a, **kw)))
    steps = []
    with c.observing(lambda m, s, w: steps.append(s)), pytest.raises(c.SameDeviceError):
        h.MECH[mech]["publish"](book, c.book_contents(c.NEW))
    assert not [s for s in steps if not s.startswith("r")]  # refused before step 1
    monkeypatch.setattr(os, "stat", real_stat)
    h.MECH[mech]["recover"](book)
    assert c.classify(book, mech) == ("old-valid", 0)
    assert {k: v for k, v in c.snapshot_tree(book).items()} == before


@pytest.mark.skipif(not os.environ.get("PROTO_REAL_XDEV_DIR"),
                    reason="set PROTO_REAL_XDEV_DIR to a dir on ANOTHER device to run (never created here)")
def test_q2_real_exdev_rename_raises_not_copies(tmp_path):
    other = os.environ["PROTO_REAL_XDEV_DIR"]
    assert os.stat(other).st_dev != os.stat(str(tmp_path)).st_dev, "PROTO_REAL_XDEV_DIR is on the same device"
    src = tmp_path / "f"
    src.write_bytes(b"x")
    with pytest.raises(OSError) as ei:
        os.replace(str(src), os.path.join(other, "q2-proto-xdev-probe"))
    assert ei.value.errno == errno.EXDEV
    assert src.exists()


@pytest.mark.skipif(not os.environ.get("PROTO_REAL_XDEV_DIR"),
                    reason="set PROTO_REAL_XDEV_DIR to a dir on ANOTHER device to run (never created here)")
@pytest.mark.parametrize("mech", ["A", "B"])
def test_q2_real_exdev_staging_symlink_is_refused(tmp_path, mech):
    """The case today's sibling staging cannot see: the staging parent resolves onto another volume."""
    book = h.setup(mech, "S1", str(tmp_path))
    target = os.path.join(os.environ["PROTO_REAL_XDEV_DIR"], f"q2-proto-{mech}-{os.getpid()}")
    os.mkdir(target)
    try:
        link = os.path.join(book, ".staging" if mech == "A" else c.GEN)
        if mech == "B":  # move the existing generation aside so gen/ can become the symlink
            os.rename(link, link + ".keep")
        os.symlink(target, link)
        with pytest.raises(c.SameDeviceError):
            h.MECH[mech]["publish"](book, c.book_contents(c.NEW))
    finally:
        os.rmdir(target)
