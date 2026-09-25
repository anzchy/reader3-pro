"""013 WI-10 C10.13: the WCAG contrast helper the theme e2e cases rely on.

A contrast helper without sRGB linearisation still orders colours plausibly, so the
e2e thresholds would pass or fail for the wrong reason. Pin it to known values.
"""

from __future__ import annotations

import pytest
import shell_4a_theme as th
from hypothesis import given, settings
from hypothesis import strategies as st


def test_black_on_white_is_21() -> None:
    assert th.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-9)


def test_spec_subtle_text_value() -> None:
    # spec §3.3 contrast table: --r3-text-subtle #707070 on --r3-bg #f5f5f5 is 4.54.
    assert round(th.contrast("#707070", "#f5f5f5"), 2) == 4.54


def test_identical_colours_are_1() -> None:
    assert th.contrast("rgb(12, 34, 56)", "#0c2238") == pytest.approx(1.0)


def test_parse_forms_agree() -> None:
    assert th.parse_rgb("rgb(1, 2, 3)") == th.parse_rgb("rgb(1 2 3)") == (1.0, 2.0, 3.0)
    assert th.parse_rgb("#abc") == th.parse_rgb("#aabbcc")
    assert th.parse_rgb("rgba(1, 2, 3, 1)") == (1.0, 2.0, 3.0)


def test_translucent_colour_is_refused() -> None:
    with pytest.raises(ValueError):
        th.parse_rgb("rgba(0, 0, 0, 0)")


channel = st.integers(min_value=0, max_value=255)
colour = st.tuples(channel, channel, channel).map(lambda t: tuple(float(x) for x in t))


@settings(max_examples=200, deadline=None)
@given(colour, colour)
def test_contrast_is_symmetric_and_at_least_1(a, b) -> None:
    assert th.contrast(a, b) == pytest.approx(th.contrast(b, a))
    assert 1.0 <= th.contrast(a, b) <= 21.0 + 1e-9


def test_expected_stamp_table() -> None:
    assert th.expected_stamp(None, None) == [None, "auto"]
    assert th.expected_stamp("system", "auto") == [None, "auto"]
    assert th.expected_stamp("bogus", "bogus") == [None, "auto"]
    assert th.expected_stamp("dark", "night") == ["dark", "night"]
    assert th.expected_stamp("light", "paper") == ["light", "paper"]
    assert len(th.STORAGE_ROWS) == 25
