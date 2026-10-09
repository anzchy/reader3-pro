"""012 WI-3.2: the web mapping of a corrupt book (central handler, single-book routes, listing routes).

Matrix: ``.claude/tdd-guardian/tests-20261009-wi3.md`` section ``## WI-3.2`` (revision 2, rulings Q1-Q6), cases
S3-14b-W, S3-18, S3-18L, S3-19, S3-19L, S3-19b, S3-19c, S3-20, S3-20b, S3-20c, S3-21, S3-22, S3-23. S3-05c is
the existing traversal / id-validation contract files, run unedited.

The law: one corrupt book is answered loudly on its own routes and never leaks the fallback or a path.

* Every single-book route that loads a corrupt book answers 500: plain HTML (no traceback) for ``/read/*`` and
  exactly ``CORRUPT_JSON`` for JSON routes.
* No byte of the flat pkl's content reaches the response, ``notes.json`` is not written, no path or folder name
  appears in the body; the AI queue lease taken before the load is released by the raise.
* A listing never answers 500 because of it; the other books stay listed.
* One ERROR record per corrupt request, no WARNING, no traceback. Missing-state behavior is unchanged.

The flat ``book.pkl`` stays in place in every corrupt case, so the book stays listed (``_validate_book_id``) and
the case is also the no-fallback scenario.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, List, Optional

import pytest
from book_format_helpers import MANIFEST, PKL, snapshot
from wi2b_world import FP_A, disk, gen_inputs, publish_gen, rec, seed_notes, version_on_disk, write_book_pkl

from conftest import (
    BOOK_ID,
    BOOK_TITLE,
    CHAPTER_0_TITLE,
    CHAPTER_1_TITLE,
    FAKE_ANSWER,
    UNIQUE_TERM,
    World,
    _clear_caches,
)
from reader3_app import book_format, book_lock

CORRUPT_JSON = {"detail": "Book storage is corrupt", "state": "corrupt"}
GOOD = "zgood_data"
SHAPES = ["garbage", "truncated", "dangling", "format-v2"]


def corrupt(world: World, shape: str) -> None:
    book = world.book_dir
    if shape == "garbage":
        (book / MANIFEST).write_bytes(b"{ not json")
    else:
        publish_gen(world.books_dir, BOOK_ID, ["x"], FP_A, "A")
        if shape == "truncated":
            raw = (book / MANIFEST).read_bytes()
            (book / MANIFEST).write_bytes(raw[: len(raw) // 2])
        elif shape == "dangling":
            shutil.rmtree(book / "gen" / "1")
        elif shape == "format-v2":
            doc = json.loads((book / MANIFEST).read_bytes())
            doc["format_version"] = 2
            (book / MANIFEST).write_text(json.dumps(doc), encoding="utf-8")
        else:  # pragma: no cover - a typo in the shape list must not pass
            raise AssertionError(shape)
    assert (book / PKL).is_file(), "the flat pkl must stay so the book stays listed"
    assert book_format.classify(book, full=False) == "corrupt"


def real_gen_pkl(books: Path, folder: str, texts: List[str], fp: str, tag: str,
                 pkl: Optional[bytes] = None) -> int:
    """``publish_gen`` with a real pickle as the generation's ``book.pkl`` (default: the flat pkl's bytes)."""
    inputs = dataclasses.replace(gen_inputs(texts, fp, tag), pkl=pkl or (books / folder / PKL).read_bytes())
    with book_lock.acquire(str(books), folder, mode=book_lock.EXCLUSIVE, holder="import"):
        return book_format.publish(books / folder, inputs)


def no_disclosure(world: World, text: str) -> None:
    assert str(world.project_root) not in text
    assert str(world.books_dir) not in text
    assert BOOK_ID not in text


def errors(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def warnings_(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _assert_corrupt_html(world: World, resp: Any) -> None:
    assert resp.status_code == 500, resp.text
    assert resp.headers["content-type"].startswith("text/html"), resp.headers["content-type"]
    text = resp.text
    assert "Traceback" not in text
    for leaked in (UNIQUE_TERM, CHAPTER_0_TITLE, CHAPTER_1_TITLE, BOOK_TITLE):
        assert leaked not in text, leaked
    no_disclosure(world, text)


def _assert_corrupt_json(world: World, resp: Any) -> None:
    assert resp.status_code == 500, resp.text
    assert resp.headers["content-type"].startswith("application/json"), resp.headers["content-type"]
    assert resp.json() == CORRUPT_JSON
    no_disclosure(world, resp.text)


# --------------------------------------------------------------------------- reading page


@pytest.mark.parametrize("path", [f"/read/{BOOK_ID}/0", f"/read/{BOOK_ID}/1", f"/read/{BOOK_ID}"])
@pytest.mark.parametrize("shape", SHAPES)
def test_s3_18_reading_page_corrupt_manifest_is_500_html_without_flat_content(
    world: World, shape: str, path: str
) -> None:
    corrupt(world, shape)
    _clear_caches()
    before = snapshot(world.book_dir)

    resp = world.client.get(path)

    _assert_corrupt_html(world, resp)
    assert snapshot(world.book_dir) == before


def test_s3_18l_reading_page_logs_exactly_one_error(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    corrupt(world, "garbage")
    _clear_caches()
    caplog.clear()

    resp = world.client.get(f"/read/{BOOK_ID}/0")

    assert resp.status_code == 500
    assert len(errors(caplog)) == 1, [r.getMessage() for r in errors(caplog)]
    assert warnings_(caplog) == [], [r.getMessage() for r in warnings_(caplog)]
    assert "Traceback" not in caplog.text


def test_s3_14b_w_no_memo_through_a_route(world: World) -> None:
    real_gen_pkl(world.books_dir, BOOK_ID, ["x"], FP_A, "A")
    _clear_caches()
    r1 = world.client.get(f"/read/{BOOK_ID}/0")
    assert r1.status_code == 200, r1.text
    # The reader page renders chapters client-side (epub.js), so the server-rendered proof that the flat pkl was
    # read is the book title and the TOC titles, not UNIQUE_TERM (matrix deviation, reported).
    assert BOOK_TITLE in r1.text and CHAPTER_0_TITLE in r1.text

    m0 = os.stat(world.book_dir / MANIFEST)
    shutil.rmtree(world.book_dir / "gen" / "1")
    m1 = os.stat(world.book_dir / MANIFEST)
    assert (m1.st_ino, m1.st_mtime_ns, m1.st_size) == (m0.st_ino, m0.st_mtime_ns, m0.st_size)
    # No cache clear here: the verdict must not be memoized anywhere between the route and book_store.
    r2 = world.client.get(f"/read/{BOOK_ID}/0")

    assert r2.status_code == 500
    assert UNIQUE_TERM not in r2.text
    assert BOOK_TITLE not in r2.text and CHAPTER_0_TITLE not in r2.text
    no_disclosure(world, r2.text)


# --------------------------------------------------------------------------- notes


NOTES_ROUTES = [
    ("GET", f"/api/notes/{BOOK_ID}", None, {}),
    ("GET", f"/api/notes/{BOOK_ID}/0", None, {}),
    ("POST", f"/api/notes/{BOOK_ID}/0", {"type": "marker", "quote": "q"}, {}),
    ("PUT", f"/api/notes/{BOOK_ID}/0/n1", {"note_text": "y"}, {}),
    ("DELETE", f"/api/notes/{BOOK_ID}/0/n1", None, {}),
    ("POST", f"/api/notes/{BOOK_ID}/0/n1/disposition", {"action": "delete"}, {"If-Match": '"v"'}),
]


@pytest.mark.parametrize(("method", "url", "body", "headers"), NOTES_ROUTES,
                         ids=[f"{m} {u}" for m, u, _, _ in NOTES_ROUTES])
def test_s3_19_every_notes_route_on_a_corrupt_book_is_500_corrupt_json(
    world: World, method: str, url: str, body: Any, headers: dict
) -> None:
    seed_notes(world.book_dir, [rec("n1", 0, "QUOTE-NOT-IN-FLAT", book_id=BOOK_ID)])
    before = disk(world.book_dir)
    corrupt(world, "garbage")
    _clear_caches()

    resp = world.client.request(method, url, json=body, headers=headers)

    _assert_corrupt_json(world, resp)
    assert disk(world.book_dir) == before
    assert not (world.book_dir / "notes.json.tmp").exists()


def _corrupt_book_with_notes(world: World) -> bytes:
    """Root manifest corrupt, flat pkl present and valid, notes.json holding one annotation; returns its bytes."""
    seed_notes(world.book_dir, [rec("n1", 0, "QUOTE-NOT-IN-FLAT", book_id=BOOK_ID)])
    corrupt(world, "garbage")
    assert (world.book_dir / PKL).is_file()
    _clear_caches()
    raw = (world.book_dir / "notes.json").read_bytes()
    assert json.loads(raw)["annotations"], "the seeded annotation must be on disk"
    return raw


# Coordinator peer ruling 2026-10-09 (WI-3.2): explicit pins for the two notes writers. The disposition row is the
# pin for a behaviour change — on this state it used to answer 409 "Book fingerprint unavailable" and now answers
# the central 500. The disposition sends the real current version as If-Match, so no precondition path can mask it.
def test_s3_19_pin_put_note_on_corrupt_manifest_with_valid_flat_pkl(world: World) -> None:
    before = _corrupt_book_with_notes(world)

    resp = world.client.put(f"/api/notes/{BOOK_ID}/0/n1", json={"note_text": "y"})

    assert resp.status_code == 500, resp.text
    assert resp.json() == {"detail": "Book storage is corrupt", "state": "corrupt"}
    assert (world.book_dir / "notes.json").read_bytes() == before


def test_s3_19_pin_disposition_on_corrupt_manifest_with_valid_flat_pkl(world: World) -> None:
    before = _corrupt_book_with_notes(world)
    version = version_on_disk(str(world.books_dir), BOOK_ID)

    resp = world.client.post(
        f"/api/notes/{BOOK_ID}/0/n1/disposition", json={"action": "delete"}, headers={"If-Match": f'"{version}"'}
    )

    assert resp.status_code == 500, resp.text
    assert resp.json() == {"detail": "Book storage is corrupt", "state": "corrupt"}
    assert (world.book_dir / "notes.json").read_bytes() == before


def test_s3_19l_notes_get_logs_exactly_one_error(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    corrupt(world, "garbage")
    _clear_caches()
    caplog.clear()

    resp = world.client.get(f"/api/notes/{BOOK_ID}")

    assert resp.status_code == 500
    assert resp.json() == CORRUPT_JSON
    assert len(errors(caplog)) == 1, [r.getMessage() for r in errors(caplog)]
    assert warnings_(caplog) == [], [r.getMessage() for r in warnings_(caplog)]
    assert "Traceback" not in caplog.text


# --------------------------------------------------------------------------- search, highlight, AI


def _json_route_rows() -> list:
    return ["search", "highlight", "ai-question", "ai-summary"]


def _call_json_route(world: World, row: str) -> Any:
    c = world.client
    if row == "search":
        return c.get(f"/api/search/{BOOK_ID}?q={UNIQUE_TERM}")
    if row == "highlight":
        return c.post(f"/api/highlight/{BOOK_ID}/0", json={"search_term": UNIQUE_TERM})
    if row == "ai-question":
        # `provider` is a required field of AIQuestionRequest; without it the case is a 422, not a load.
        return c.post(f"/api/ai/question/{world.book_uuid}",
                      json={"question": f"Who is {UNIQUE_TERM}?", "provider": "anthropic"})
    if row == "ai-summary":
        return c.post(f"/api/ai/summary/{world.book_uuid}", json={"provider": "anthropic", "max_tokens": 128})
    raise AssertionError(row)  # pragma: no cover


@pytest.mark.parametrize("row", _json_route_rows())
def test_s3_19b_other_single_book_json_routes_are_500_corrupt_json(world: World, row: str) -> None:
    corrupt(world, "garbage")
    _clear_caches()
    before = snapshot(world.book_dir)

    resp = _call_json_route(world, row)

    _assert_corrupt_json(world, resp)
    assert UNIQUE_TERM not in resp.text
    assert FAKE_ANSWER not in resp.text
    assert snapshot(world.book_dir) == before


def test_s3_19c_streaming_ask_on_a_corrupt_book_releases_the_queue_lease(world: World) -> None:
    corrupt(world, "garbage")
    _clear_caches()
    url = f"/api/ai/question/{world.book_uuid}"
    body = {"question": f"Who is {UNIQUE_TERM}?", "provider": "anthropic"}

    r1 = world.client.post(url + "?stream=true", json=body)
    t = time.monotonic()
    r2 = world.client.post(url + "?stream=true", json=body)
    dt = time.monotonic() - t

    for r in (r1, r2):
        assert r.status_code == 500, r.text
        assert r.json() == CORRUPT_JSON
    assert dt < 3.0, f"the second stream request waited {dt:.2f}s: the first one leaked its lease"

    os.unlink(world.book_dir / MANIFEST)
    _clear_caches()
    # Added after red (input fix, no assertion touched): the `world` book has no semantic index, so retrieval uses
    # the keyword fallback, which only hits when the question is the term itself (as test_scenarios.py sends it).
    body = {"question": UNIQUE_TERM, "provider": "anthropic"}
    r3 = world.client.post(url, json=body)
    assert r3.status_code == 200, r3.text
    assert r3.json()["answer"] == FAKE_ANSWER


# --------------------------------------------------------------------------- listings


def _corrupt_plus_good(world: World, good_texts: List[str]) -> None:
    corrupt(world, "garbage")
    write_book_pkl(world.books_dir, GOOD, good_texts, None)
    _clear_caches()


def test_s3_20_home_and_stats_survive_one_corrupt_book(world: World) -> None:
    _corrupt_plus_good(world, ["good text"])

    home = world.client.get("/")
    assert home.status_code == 200, home.text
    assert GOOD in home.text
    assert BOOK_TITLE not in home.text
    assert "Traceback" not in home.text

    stats = world.client.get("/api/library/stats?fresh=true")
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["books_total"] == 2
    assert body["sections_total"] == 1
    no_disclosure(world, stats.text)


def test_s3_20b_library_and_export_list_the_corrupt_book_as_unreadable(world: World) -> None:
    _corrupt_plus_good(world, ["good text"])

    lib = world.client.get("/api/library")
    exp = world.client.get("/api/library/export")

    for resp in (lib, exp):
        assert resp.status_code == 200, resp.text
        entries = {e["book_id"]: e for e in resp.json()["books"]}
        assert entries[GOOD]["title"] == GOOD
        assert entries[BOOK_ID] == {"book_id": BOOK_ID, "error": "unreadable"}
        assert BOOK_TITLE not in resp.text


def test_s3_20c_library_search_lists_the_corrupt_book_as_failed(world: World) -> None:
    _corrupt_plus_good(world, [f"good {UNIQUE_TERM} text"])

    resp = world.client.get(f"/api/search/library?q={UNIQUE_TERM}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert BOOK_ID in body["failed_books"]
    assert GOOD in body["book_order"]
    assert body["results"] and all(r["book_id"] == GOOD for r in body["results"])
    assert body["total_matches"] >= 1


# --------------------------------------------------------------------------- pins and negative controls


def test_s3_21_corrupt_flat_pkl_in_the_missing_state_is_404_pinned(world: World) -> None:
    (world.book_dir / PKL).write_bytes(b"\x80\x05not-a-pickle-at-all")
    _clear_caches()

    for url in (f"/read/{BOOK_ID}/0", f"/api/notes/{BOOK_ID}"):
        resp = world.client.get(url)
        assert resp.status_code == 404, (url, resp.text)
        assert resp.json() == {"detail": "Book not found"}
        assert "Traceback" not in resp.text


@pytest.mark.parametrize("row", ["missing", "valid", "no-flat"])
def test_s3_22_healthy_and_absent_books_are_unaffected(world: World, row: str) -> None:
    if row == "valid":
        real_gen_pkl(world.books_dir, BOOK_ID, ["x"], FP_A, "A")
    elif row == "no-flat":
        corrupt(world, "garbage")
        os.unlink(world.book_dir / PKL)
    _clear_caches()

    page = world.client.get(f"/read/{BOOK_ID}/0")
    notes = world.client.get(f"/api/notes/{BOOK_ID}")

    if row == "no-flat":
        for resp in (page, notes):
            assert resp.status_code == 404, resp.text
            assert resp.json() == {"detail": "Book not found"}
    else:
        assert page.status_code == 200, page.text
        # Chapter text is rendered client-side (epub.js); BOOK_TITLE / CHAPTER_0_TITLE are what the server renders.
        assert BOOK_TITLE in page.text and CHAPTER_0_TITLE in page.text
        assert notes.status_code == 200, notes.text
        assert notes.json()["book_id"] == BOOK_ID


def test_s3_23_corrupt_500_bodies_disclose_no_path_and_no_folder_name(world: World) -> None:
    corrupt(world, "dangling")
    _clear_caches()

    responses = {
        "html": world.client.get(f"/read/{BOOK_ID}/0"),
        "notes": world.client.get(f"/api/notes/{BOOK_ID}"),
        "search": world.client.get(f"/api/search/{BOOK_ID}?q={UNIQUE_TERM}"),
        "ai": world.client.post(f"/api/ai/question/{world.book_uuid}",
                                json={"question": f"Who is {UNIQUE_TERM}?", "provider": "anthropic"}),
    }
    for name, resp in responses.items():
        assert resp.status_code == 500, (name, resp.text)
        no_disclosure(world, resp.text)
        assert os.sep + "gen" + os.sep not in resp.text, name
        assert MANIFEST not in resp.text, name
        if name != "html":
            assert resp.json() == CORRUPT_JSON, name
