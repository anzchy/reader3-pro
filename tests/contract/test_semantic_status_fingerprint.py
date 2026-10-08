"""012 WI-2a.7 V7-13: ``GET /api/index/{book_id}/status`` carries the soft fingerprint stale.

The unit lane pins ``BookVectorIndex.status()``; this pins that the route returns it as-is rather than
re-deriving a status. The fixture book is given a real manifest (``book_format.publish`` over the seeded
pkl-only dir, which leaves the flat ``book.pkl`` untouched), then the DEG-S2 fixture writes its
"indexed except for the fingerprint" meta.
"""

from __future__ import annotations

from book_format_helpers import make_inputs
from deg_assertions import write_stale_index_meta  # type: ignore[import-not-found]

from conftest import BOOK_ID, World
from reader3_app import book_format

FP_X = "0123456789abcdef" * 4


def test_v7_13_status_route_reports_fingerprint_stale_and_keeps_indexed(world: World) -> None:
    book_format.publish(world.book_dir, make_inputs("v0", book_fingerprint=FP_X), create=False)
    write_stale_index_meta(world.books_dir, BOOK_ID)

    response = world.client.get(f"/api/index/{BOOK_ID}/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("stale") is True
    assert body.get("stale_reason") == "fingerprint"
    assert body["status"] == "indexed"
