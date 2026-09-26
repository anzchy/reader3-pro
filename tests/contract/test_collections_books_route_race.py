"""WI-3 #1: ``POST /api/collections/{id}/books`` removes against the locked state.

The route used to read the collection outside the lock and drop every ``remove``
id that was not in that snapshot. A book added by another writer between the
snapshot and the locked mutation was then silently kept. The law here: the
route's result equals applying the request's ``add`` then ``remove`` to the
state at the moment of its locked mutation.

The interleaving is made deterministic with a pass-through wrapper on
``collections_service.update_collection_books``, the attribute the router calls.
On its first call the wrapper runs a real concurrent write through the real
service, then the route's own call. It sits after the route's snapshot and
before its mutation whether or not the fix keeps the existence check, so it
cannot silently stop firing.

The collections file is always ``server._collections_file_path()``, never
``World.collections_path`` (a different file).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from reader3_app import collections_service
from reader3_app.web import server

from conftest import BOOK_ID, MISSING_COLLECTION_ID, World

ALPHA = ["x0_data", "x1_data", "x2_data", "x3_data", BOOK_ID]


def _apply(ids: Iterable[str], add: Iterable[str], remove: Iterable[str]) -> list[str]:
    """Mirror of ``update_collection_books``: append new adds in order, then drop removes."""
    out = list(ids)
    for b in add:
        if b not in out:
            out.append(b)
    drop = set(remove)
    return [b for b in out if b not in drop]


def _path() -> Path:
    return server._collections_file_path()


def _sha(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _new_collection(client: TestClient) -> tuple[str, str]:
    name = f"c{uuid.uuid4().hex[:12]}"
    r = client.post("/api/collections", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"], name


class _Window:
    """Pass-through wrapper on ``update_collection_books``; injects one real concurrent write."""

    def __init__(self, concurrent: Callable[[Callable[..., Any], Path, str], None]) -> None:
        self.real = collections_service.update_collection_books
        self.concurrent = concurrent
        self.fired = 0

    def __call__(
        self, path: Path, cid_: str, *, add: Iterable[str] = (), remove: Iterable[str] = ()
    ) -> collections_service.Collection:
        if self.fired == 0:
            self.fired += 1
            self.concurrent(self.real, path, cid_)
        return self.real(path, cid_, add=add, remove=remove)


# --------------------------------------------------------------------------- #
# cc1 a concurrent add inside the route's window is removable
# --------------------------------------------------------------------------- #


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    initial=st.lists(st.sampled_from(ALPHA), unique=True),
    conc=st.tuples(st.sets(st.sampled_from(ALPHA)), st.sets(st.sampled_from(ALPHA))),
    req_add=st.sets(st.just(BOOK_ID)),
    req_remove=st.sets(st.sampled_from(ALPHA)),
)
@example(initial=[], conc=({"x0_data"}, set()), req_add=set(), req_remove={"x0_data"})
def test_cc1_route_linearizable_under_interleaving(
    world: World,
    initial: list[str],
    conc: tuple[set[str], set[str]],
    req_add: set[str],
    req_remove: set[str],
) -> None:
    client = world.client
    cid, _ = _new_collection(client)
    p = _path()
    collections_service.update_collection_books(p, cid, add=initial)

    def concurrent(real: Callable[..., Any], path: Path, cid_: str) -> None:
        real(path, cid_, add=conc[0], remove=conc[1])

    hook = _Window(concurrent)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(collections_service, "update_collection_books", hook)
        r = client.post(
            f"/api/collections/{cid}/books",
            json={"add": sorted(req_add), "remove": sorted(req_remove)},
        )

    expected = _apply(_apply(initial, conc[0], conc[1]), req_add, req_remove)
    assert r.status_code == 200, r.text
    assert hook.fired == 1
    assert r.json()["book_ids"] == expected
    g = client.get(f"/api/collections/{cid}")
    assert g.status_code == 200
    assert g.json()["book_ids"] == expected
    on_disk = collections_service.get_collection(p, cid)
    assert on_disk is not None and on_disk.book_ids == expected


# --------------------------------------------------------------------------- #
# cc2 removing a non-member is a no-op
# --------------------------------------------------------------------------- #


def test_cc2_nonmember_remove_is_noop(world: World) -> None:
    client = world.client
    cid, name = _new_collection(client)
    p = _path()
    collections_service.update_collection_books(p, cid, add=[BOOK_ID])
    before = collections_service.get_collection(p, cid)
    assert before is not None

    r = client.post(f"/api/collections/{cid}/books", json={"remove": ["ghost_data"]})

    assert r.status_code == 200, r.text
    assert r.json()["book_ids"] == [BOOK_ID]
    after = collections_service.get_collection(p, cid)
    assert after is not None
    assert after.book_ids == [BOOK_ID]
    assert (after.id, after.name, after.created_at) == (before.id, name, before.created_at)


# --------------------------------------------------------------------------- #
# cc3 a missing collection is 404 and writes nothing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("variant", ["absent", "gone_in_window"])
def test_cc3_missing_collection_404(world: World, variant: str) -> None:
    client = world.client
    p = _path()

    if variant == "absent":
        _new_collection(client)
        sha0 = _sha(p)
        r = client.post(f"/api/collections/{MISSING_COLLECTION_ID}/books", json={"remove": ["x0_data"]})
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Collection not found"
        assert _sha(p) == sha0
        return

    cid, name = _new_collection(client)
    sha_after_delete: list[Optional[str]] = []

    def concurrent(real: Callable[..., Any], path: Path, cid_: str) -> None:
        collections_service.delete_collection(path, cid_)
        sha_after_delete.append(_sha(path))

    hook = _Window(concurrent)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(collections_service, "update_collection_books", hook)
        r = client.post(f"/api/collections/{cid}/books", json={"remove": ["x0_data"]})

    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Collection not found"
    assert hook.fired == 1
    assert collections_service.get_collection(p, cid) is None
    assert _sha(p) == sha_after_delete[0]
    assert name not in [c.name for c in collections_service.load_collections(p)]
