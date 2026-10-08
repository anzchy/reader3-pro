"""WI-2a.6 N6-11: the notes routes keep ``notes.json``'s top-level ``book_fingerprint``.

The unit lane proves every notes_service mutator carries the key. This proves no
route-level write path rebuilds the payload on its own: a raw seed holding
``STALE_FINGERPRINT`` goes through the real router (POST, PUT, DELETE, and the
orphan-refresh GET, which also writes) and the raw file is re-read after each request.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from deg_assertions import DEG_S1_ANNOTATION, STALE_FINGERPRINT  # type: ignore[import-not-found]

from conftest import BOOK_ID, World

KEY = "book_fingerprint"


def _read_raw(world: World) -> Dict[str, Any]:
    data = json.loads((world.book_dir / "notes.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_n6_11_notes_routes_keep_the_key_end_to_end(world: World) -> None:
    client = world.client
    # DEG_S1's quote is not in the fixture book's chapter 0, so the GET refresh orphans it and saves.
    seed = dict(DEG_S1_ANNOTATION)
    seed["book_id"] = BOOK_ID
    payload = {"schema_version": 1, "book_id": BOOK_ID, "annotations": [seed], KEY: STALE_FINGERPRINT}
    (world.book_dir / "notes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    listed = client.get(f"/api/notes/{BOOK_ID}")
    assert listed.status_code == 200, listed.text
    data = _read_raw(world)
    assert [a.get("orphaned") for a in data["annotations"]] == [True]
    assert data.get(KEY) == STALE_FINGERPRINT

    created = client.post(
        f"/api/notes/{BOOK_ID}/0",
        json={"type": "note", "color": "green", "quote": "traveller", "note_text": "n6-11 first"},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    data = _read_raw(world)
    assert note_id in {a["id"] for a in data["annotations"]}
    assert data.get(KEY) == STALE_FINGERPRINT

    updated = client.put(f"/api/notes/{BOOK_ID}/0/{note_id}", json={"note_text": "n6-11 edited"})
    assert updated.status_code == 200, updated.text
    data = _read_raw(world)
    assert [a.get("note_text") for a in data["annotations"] if a["id"] == note_id] == ["n6-11 edited"]
    assert data.get(KEY) == STALE_FINGERPRINT

    deleted = client.delete(f"/api/notes/{BOOK_ID}/0/{note_id}")
    assert deleted.status_code == 204, deleted.text
    data = _read_raw(world)
    assert note_id not in {a["id"] for a in data["annotations"]}
    assert data.get(KEY) == STALE_FINGERPRINT
