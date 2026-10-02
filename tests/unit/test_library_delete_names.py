"""018 WI-5a: tombstone / intent naming (matrix cases N-1, N-2).

``reader3_app.library_delete`` is imported lazily through ``ld()`` so the lane
collects while the module does not exist yet.
"""

from __future__ import annotations

import pytest
from delete_world import ld
from hypothesis import given, settings
from hypothesis import strategies as st

FOLDERS = st.from_regex(r"[A-Za-z0-9 ._\-é中]{1,40}_data", fullmatch=True)
PIDS = st.integers(min_value=0, max_value=2**31)
TOKENS = st.from_regex(r"[0-9a-f]{8}", fullmatch=True)


@settings(max_examples=300, deadline=None)
@given(folder=FOLDERS, pid=PIDS, token=TOKENS)
def test_n1_names_round_trip_and_families_are_disjoint(folder, pid, token):
    """N-1: both families round-trip, never cross-parse, never parse a folder, never end in ``_data``."""
    m = ld()
    tomb = m.tombstone_name(folder, pid, token)
    intent = m.intent_name(folder, pid, token)

    assert m.parse_tombstone(tomb) == (folder, pid, token)
    assert m.parse_intent(intent) == (folder, pid, token)

    assert m.parse_intent(tomb) is None
    assert m.parse_tombstone(intent) is None

    assert m.parse_tombstone(folder) is None
    assert m.parse_intent(folder) is None

    assert not tomb.endswith("_data")
    assert not intent.endswith("_data")


NON_PARSING = [
    ".x.deleted-1_data",
    ".x_data.deleted-1_data",
    ".x_data.deleted-12-abcdef12_data",
    "x_data.deleted-1",
    ".x_data.deleted-",
    ".x_data.deleted-1-ABCDEF12",
    ".x_data.deleted-1-abcdef12.intent.json.tmp",
]


@pytest.mark.parametrize("name", NON_PARSING, ids=NON_PARSING)
def test_n2_d10_dot_leading_data_dirs_are_books_not_tombstones(name):
    """N-2: none of these parse under either parser."""
    m = ld()
    assert m.parse_tombstone(name) is None
    assert m.parse_intent(name) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (".x_data.deleted-1", ("x_data", 1, None)),
        (".x_data.deleted-1-abcdef12", ("x_data", 1, "abcdef12")),
    ],
    ids=["legacy-no-token", "with-token"],
)
def test_n2_d10_controls_parse_as_tombstones(name, expected):
    """N-2 controls: the legacy (token-less) and the tokened tombstone both parse."""
    m = ld()
    assert m.parse_tombstone(name) == expected
    assert m.parse_intent(name) is None
