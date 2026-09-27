"""WI-3 (W3-C12): a warm resolver follows the on-disk identity through real routes.

``world`` has already resolved ``BOOK_ID`` once, so the resolver's cache holds
U1 before each mutation below. Unlike ``test_degradation_book_uuid.py`` this
module deliberately does **not** swap in a fresh resolver: the warm cache is
the thing under test. Before WI-3 the cache hit answered U1 no matter what the
file said.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid

import pytest

from reader3_app.ai.books import AI_META_FILENAME

from conftest import World

_UUID_ATTR = re.compile(r'data-book-uuid="([^"]*)"')


def _rendered_uuids(html: str) -> list[str]:
    return _UUID_ATTR.findall(html)


@pytest.mark.parametrize("mutation", ["rewrite", "corrupt", "delete_meta"])
def test_warm_resolver_follows_disk_identity(world: World, mutation: str) -> None:
    u1 = world.book_uuid
    meta = world.book_dir / AI_META_FILENAME
    assert json.loads(meta.read_text(encoding="utf-8"))["book_uuid"] == u1

    if mutation == "rewrite":
        u2 = str(uuid.uuid4())
        meta.write_text(json.dumps({"book_uuid": u2}), encoding="utf-8")

        resp = world.client.get("/")
        assert resp.status_code == 200
        assert _rendered_uuids(resp.text) == [u2]
        assert u1 not in resp.text

        stale = world.client.post("/api/ai/rag/retrieve", json={"book_uuid": u1, "query": "x"})
        assert stale.status_code == 404
        fresh = world.client.post("/api/ai/rag/retrieve", json={"book_uuid": u2, "query": "x"})
        assert fresh.status_code != 404
        assert json.loads(meta.read_text(encoding="utf-8")) == {"book_uuid": u2}

    elif mutation == "corrupt":
        meta.write_text('{"book_uuid": "this-is-not-a-uuid"}', encoding="utf-8")
        sha0 = hashlib.sha256(meta.read_bytes()).hexdigest()

        resp = world.client.get("/")
        assert resp.status_code == 200
        assert _rendered_uuids(resp.text) == [""]
        assert hashlib.sha256(meta.read_bytes()).hexdigest() == sha0

    else:
        meta.unlink()

        resp = world.client.get("/")
        assert resp.status_code == 200
        rendered = _rendered_uuids(resp.text)
        assert meta.exists()
        on_disk = json.loads(meta.read_text(encoding="utf-8"))["book_uuid"]
        assert rendered == [on_disk]
        assert on_disk != u1
