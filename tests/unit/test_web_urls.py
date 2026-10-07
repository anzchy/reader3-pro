"""FX37-7 (audit #7): ``web.urls.cover_url`` percent-encodes each path segment.

Law (round-trip): for any folder / image name without ``/`` or NUL, the URL has exactly the
five parts ``["", "read", q(folder), "images", q(image)]`` and unquoting each encoded part
gives the input back. Names made only of unreserved characters are unchanged.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from reader3_app.web.urls import cover_url

_SEGMENT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="/\x00"),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in (".", ".."))


@given(folder=_SEGMENT, image=_SEGMENT)
def test_cover_url_round_trips_both_segments(folder: str, image: str) -> None:
    url = cover_url(folder, image)
    assert url is not None
    parts = url.split("/")
    assert len(parts) == 5, url
    assert parts[:2] == ["", "read"] and parts[3] == "images"
    assert unquote(parts[2]) == folder
    assert unquote(parts[4]) == image
    assert "#" not in url and "?" not in url and " " not in url


@pytest.mark.parametrize(
    ("folder", "image", "expected"),
    [
        ("dracula_data", "cover.jpg", "/read/dracula_data/images/cover.jpg"),
        ("A#B_data", "cover.jpg", "/read/A%23B_data/images/cover.jpg"),
        ("a_data", "c#1.jpg", "/read/a_data/images/c%231.jpg"),
        ("a b_data", "x?y.png", "/read/a%20b_data/images/x%3Fy.png"),
        ("50%_data", "%41.jpg", "/read/50%25_data/images/%2541.jpg"),
    ],
)
def test_cover_url_examples(folder: str, image: str, expected: str) -> None:
    assert cover_url(folder, image) == expected


@pytest.mark.parametrize("image", [None, ""])
def test_no_image_is_no_url(image: object) -> None:
    assert cover_url("a_data", image) is None  # type: ignore[arg-type]
