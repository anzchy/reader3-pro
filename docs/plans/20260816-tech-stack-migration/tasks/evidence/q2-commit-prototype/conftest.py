"""Q2 commit prototype: put this folder on sys.path and compute the crash matrix once."""
import os
import sys

import pytest

EV = os.path.dirname(os.path.abspath(__file__))
if EV not in sys.path:
    sys.path.insert(0, EV)


@pytest.fixture(scope="session")
def results():
    from proto import harness

    return harness.compute_all()
