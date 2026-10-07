"""018 WI-5b: adding a book to a collection while it is being deleted (matrix case B-5c, ruled Q5).

Law: after any interleaving of add-to-collection with a delete, the deleted folder is
in no collection.

The interleaving is made deterministic the same way as
``test_collections_books_route_race.py``: a pass-through wrapper on
``collections_service.update_collection_books`` (the attribute the router calls)
runs a real ``delete_book("a_data")`` first, then delegates. The route's own
existence check has already passed by then, so only a predicate re-checked inside
the collections lock can refuse the add. The wrapper forwards any extra argument the
route passes, so it keeps firing whatever shape that recheck takes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from conftest import World
from delete_world import U, V, file_bytes, ld, make_book, read_collections
from reader3_app import collections_service
from reader3_app.web import server

A = "a_data"
B = "b_data"


def _path() -> Path:
    return server._collections_file_path()


def test_b5c_add_book_racing_delete_returns_404_and_collection_unchanged(world: World, monkeypatch) -> None:
    """B-5c: the add lands after the delete committed -> 404 "Book not found", file bytes as the
    delete left them, and ``a_data`` is in no collection, including after a same-name re-create."""
    m = ld()
    client = world.client
    make_book(world.books_dir, A, title="Alpha", body="AAAA alpha", book_uuid=U)
    make_book(world.books_dir, B, title="Beta", body="BBBB beta", book_uuid=V)

    r = client.post("/api/collections", json={"name": "c1"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    p = _path()
    collections_service.update_collection_books(p, cid, add=[B])
    assert read_collections(p) == {cid: [B]}

    real = collections_service.update_collection_books
    fired: List[int] = []
    after_delete: List[Optional[bytes]] = []

    def racing(path: Any, cid_: str, *args: Any, **kwargs: Any) -> Any:
        if not fired:
            fired.append(1)
            m.delete_book(
                str(world.books_dir),
                A,
                delete_conversations=True,
                conversation_root=None,
                collections_path=str(p),
            )
            after_delete.append(file_bytes(p))
        return real(path, cid_, *args, **kwargs)

    monkeypatch.setattr(collections_service, "update_collection_books", racing)
    resp = client.post(f"/api/collections/{cid}/books", json={"add": [A]})
    monkeypatch.setattr(collections_service, "update_collection_books", real)

    assert fired == [1]
    assert not (world.books_dir / A).exists()
    assert (resp.status_code, "Book not found" in resp.text) == (404, True), resp.text
    assert file_bytes(p) == after_delete[0]
    assert read_collections(p) == {cid: [B]}
    g = client.get(f"/api/collections/{cid}")
    assert g.status_code == 200, g.text
    assert g.json()["book_ids"] == [B]

    make_book(world.books_dir, A, title="Alpha 2", body="AAAA again", book_uuid=U)
    assert all(A not in ids for ids in read_collections(p).values())
    g = client.get(f"/api/collections/{cid}")
    assert g.json()["book_ids"] == [B]
