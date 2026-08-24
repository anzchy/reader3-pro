"""Layer 2 of the route contract: six table-driven groups over one assertion runner.

Definition site: `docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md`
§4 layer 2. The groups are `library / reader / notes / search / ai / settings`.

What every case asserts, via `run_case`:

* the exact status code;
* the response's media type;
* for a 2xx JSON object, the **exact set of top-level keys** — not "the keys I care
  about are present". Freezing the key set is what makes a handler that quietly
  stops returning `status_message` turn this lane red. It is also the reason a
  handler replaced by `return {}` cannot pass: the set comparison fails outright;
* for a 4xx, that the error shape is `{"detail": <non-empty>}`, so error handling
  stays uniform across the Phase 2 router split;
* for HTML and text, that named substrings really came back.

`expected_keys` is mandatory for any 2xx JSON object (see the guard in `run_case`).
That guard exists so a future case cannot degrade into "it returned 200".

Values in bodies are asserted in `test_scenarios.py`, where a scenario can set up
the data it then reads back. This file freezes *shape*; that file freezes *behaviour*.

Where a route is only represented here by its error cases, the reason is written on
the table entry, and the happy path lives in `test_scenarios.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import (
    BOOK_AUTHOR,
    BOOK_ID,
    BOOK_TITLE,
    CHAPTER_0_TITLE,
    MISSING_BOOK_ID,
    MISSING_COLLECTION_ID,
    MISSING_UUID,
    UNIQUE_TERM,
    World,
)

MISSING_CONVERSATION_ID = "33333333-3333-4333-8333-333333333333"
SEEDED_CONVERSATION_ID = "22222222-2222-4222-8222-222222222222"
SEEDED_MESSAGE_TEXT = "a seeded user turn"


@dataclass(frozen=True)
class ContractCase:
    """One request and everything that must be true of its response."""

    method: str
    path: str
    expected_status: int
    body: Any = None
    #: Exact top-level key set for a 2xx JSON object. Required for those; unused otherwise.
    expected_keys: tuple[str, ...] = ()
    #: Media type prefix, compared against the part of Content-Type before ';'.
    content_type: str = "application/json"
    #: Substrings that must appear in the decoded body (HTML and plain-text routes).
    must_contain: tuple[str, ...] = ()
    #: Exact bytes for binary routes.
    expected_bytes: bytes | None = None
    note: str = ""

    def __str__(self) -> str:  # drives readable pytest ids
        return f"{self.method} {self.path} -> {self.expected_status}"


@pytest.fixture
def params(world: World) -> dict[str, str]:
    """Seed one of every addressable resource, so each table case stands alone.

    Cases must not depend on each other's side effects — a table where case 7 only
    passes because case 3 ran first stops being a table and becomes a script, and
    `-k` or `-p no:randomly` would break it.
    """
    client = world.client

    collection = client.post("/api/collections", json={"name": "Seeded Shelf"})
    assert collection.status_code == 201, collection.text

    annotation = client.post(
        f"/api/notes/{BOOK_ID}/0",
        json={"type": "note", "color": "green", "quote": "traveller", "note_text": "seeded"},
    )
    assert annotation.status_code == 201, annotation.text

    conversation = client.put(
        f"/api/ai/conversations/{world.book_uuid}/{SEEDED_CONVERSATION_ID}",
        json={
            "provider": "anthropic",
            "model": "seeded-model",
            "messages": [
                {
                    "id": "msg-1",
                    "role": "user",
                    "content": SEEDED_MESSAGE_TEXT,
                    "timestamp": "2026-01-01T00:00:00Z",
                }
            ],
        },
    )
    assert conversation.status_code == 200, conversation.text

    return {
        "book_id": BOOK_ID,
        "missing_book_id": MISSING_BOOK_ID,
        "book_uuid": world.book_uuid,
        "missing_uuid": MISSING_UUID,
        "collection_id": collection.json()["id"],
        "missing_collection_id": MISSING_COLLECTION_ID,
        "conversation_id": SEEDED_CONVERSATION_ID,
        "missing_conversation_id": MISSING_CONVERSATION_ID,
        "note_id": annotation.json()["id"],
        "term": UNIQUE_TERM,
    }


def run_case(client: TestClient, case: ContractCase, params: dict[str, str]) -> None:
    path = case.path.format(**params)
    kwargs: dict[str, Any] = {}
    if case.body is not None:
        kwargs["json"] = case.body

    response = client.request(case.method, path, **kwargs)

    assert response.status_code == case.expected_status, (
        f"{case.method} {path}: 期望 {case.expected_status}，实得 {response.status_code}；body={response.text[:400]}"
    )

    media_type = response.headers.get("content-type", "").split(";")[0].strip()
    assert media_type == case.content_type, (
        f"{case.method} {path}: Content-Type 期望 {case.content_type}，实得 {media_type!r}"
    )

    if case.expected_status == 204:
        assert response.content == b"", f"{case.method} {path}: 204 不应带 body"
        return

    if case.expected_bytes is not None:
        assert response.content == case.expected_bytes
        return

    if media_type == "application/json":
        payload = response.json()
        if 200 <= case.expected_status < 300:
            if isinstance(payload, dict):
                assert case.expected_keys, (
                    f"{case} 没写 expected_keys。2xx 的 JSON 对象必须冻结顶层键集，"
                    f"否则这条用例只断言了「返回了 2xx」——那正是本分支禁止的 wiring-only。"
                    f"实测键集：{sorted(payload)}"
                )
                assert set(payload) == set(case.expected_keys), (
                    f"{case.method} {path}: 顶层键集变了。\n"
                    f"  多了: {sorted(set(payload) - set(case.expected_keys))}\n"
                    f"  少了: {sorted(set(case.expected_keys) - set(payload))}"
                )
        else:
            assert isinstance(payload, dict) and "detail" in payload, (
                f"{case.method} {path}: 错误响应必须是 {{'detail': ...}}，实得 {payload!r}"
            )
            assert payload["detail"], f"{case.method} {path}: detail 为空"

    for fragment in case.must_contain:
        assert fragment in response.text, f"{case.method} {path}: 响应里找不到 {fragment!r}"


COLLECTION_KEYS = ("id", "name", "created_at", "book_ids")
SETTINGS_KEYS = ("default_provider", "providers", "preferences")
PROVIDER_KEYS = (
    "name",
    "api_key_configured",
    "base_url",
    "model_name",
    "enabled",
    "timeout",
    "max_retries",
)
CONVERSATION_KEYS = (
    "schema_version",
    "book_uuid",
    "book_folder",
    "conversation_id",
    "provider",
    "model",
    "created_at",
    "last_updated",
    "messages",
)


# --------------------------------------------------------------------------- library

LIBRARY_CASES = [
    ContractCase(
        "GET",
        "/",
        200,
        content_type="text/html",
        must_contain=(BOOK_TITLE, BOOK_AUTHOR),
    ),
    ContractCase("GET", "/api/collections", 200, expected_keys=("collections",)),
    ContractCase("POST", "/api/collections", 201, body={"name": "Fresh"}, expected_keys=COLLECTION_KEYS),
    ContractCase("POST", "/api/collections", 422, body={}, note="name 缺失 -> pydantic"),
    ContractCase("POST", "/api/collections", 400, body={"name": ""}, note="name 空串 -> 业务校验"),
    ContractCase("GET", "/api/collections/{collection_id}", 200, expected_keys=COLLECTION_KEYS),
    ContractCase("GET", "/api/collections/{missing_collection_id}", 404),
    ContractCase("GET", "/api/collections/not-a-uuid", 400, note="id 形状非法先于存在性"),
    ContractCase(
        "PUT",
        "/api/collections/{collection_id}",
        200,
        body={"name": "Renamed"},
        expected_keys=COLLECTION_KEYS,
    ),
    ContractCase("PUT", "/api/collections/{missing_collection_id}", 404, body={"name": "x"}),
    ContractCase("PUT", "/api/collections/{collection_id}", 400, body={"name": ""}),
    ContractCase(
        "POST",
        "/api/collections/{collection_id}/books",
        200,
        body={"add": [BOOK_ID], "remove": []},
        expected_keys=COLLECTION_KEYS,
    ),
    ContractCase(
        "POST",
        "/api/collections/{collection_id}/books",
        404,
        body={"add": [MISSING_BOOK_ID], "remove": []},
        note="add 里的书不存在 -> _validate_book_id 报 404",
    ),
    ContractCase("POST", "/api/collections/{missing_collection_id}/books", 404, body={"add": [], "remove": []}),
    ContractCase("DELETE", "/api/collections/{collection_id}", 204, content_type=""),
    ContractCase("DELETE", "/api/collections/{missing_collection_id}", 404),
    ContractCase(
        "GET",
        "/api/library/stats",
        200,
        expected_keys=(
            "scope",
            "books_total",
            "books_indexed",
            "indexed_percent",
            "sections_total",
            "chunks_total",
            "computed_at",
        ),
    ),
    ContractCase("GET", "/api/library/stats?scope=bogus", 400),
    ContractCase("GET", "/api/library/stats?scope=collection:{missing_collection_id}", 404),
]


@pytest.mark.parametrize("case", LIBRARY_CASES, ids=str)
def test_library契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    run_case(client, case, params)


# ---------------------------------------------------------------------------- reader

READER_CASES = [
    ContractCase("GET", "/settings", 200, content_type="text/html", must_contain=("<html",)),
    ContractCase(
        "GET",
        "/read/{book_id}/0",
        200,
        content_type="text/html",
        must_contain=(BOOK_TITLE, CHAPTER_0_TITLE),
    ),
    ContractCase("GET", "/read/{book_id}/99", 404, note="章节越界"),
    ContractCase("GET", "/read/{missing_book_id}/0", 404),
    ContractCase(
        "GET",
        "/read/{book_id}/book.epub",
        200,
        content_type="application/epub+zip",
        expected_bytes=b"PK\x03\x04 not-a-real-zip",
    ),
    ContractCase("GET", "/read/{missing_book_id}/book.epub", 404),
    ContractCase(
        "GET",
        "/read/{book_id}/images/cover.jpg",
        200,
        content_type="image/jpeg",
        expected_bytes=b"\xff\xd8\xff\xe0 jpeg-ish",
    ),
    ContractCase("GET", "/read/{book_id}/images/nope.jpg", 404),
    # GET /read/{book_id} 现在必然抛 TypeError（见 test_known_defects.py），
    # 所以它不在这张表里；清单快照仍然守着这条路由的存在。
]


@pytest.mark.parametrize("case", READER_CASES, ids=str)
def test_reader契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    run_case(client, case, params)


# ----------------------------------------------------------------------------- notes

NOTE_LIST_KEYS = ("book_id", "chapter_index", "count", "annotations")

NOTES_CASES = [
    ContractCase(
        "GET",
        "/api/notes/{book_id}",
        200,
        expected_keys=("schema_version", "book_id", "total_count", "annotations_by_chapter"),
    ),
    ContractCase("GET", "/api/notes/{missing_book_id}", 404),
    ContractCase("GET", "/api/notes/{book_id}/0", 200, expected_keys=NOTE_LIST_KEYS),
    ContractCase("GET", "/api/notes/{book_id}/99", 400, note="章节越界在 notes 上是 400，不是 404"),
    ContractCase("GET", "/api/notes/{book_id}/abc", 422, note="路径参数不是整数"),
    ContractCase("GET", "/api/notes/{missing_book_id}/0", 404),
    ContractCase(
        "POST",
        "/api/notes/{book_id}/0",
        201,
        body={"type": "marker", "color": "yellow", "quote": "traveller"},
        expected_keys=("id", "created_at", "message"),
    ),
    ContractCase("POST", "/api/notes/{book_id}/0", 422, body={"quote": "x"}, note="type 缺失"),
    ContractCase("POST", "/api/notes/{book_id}/0", 400, body={"type": "bogus", "quote": "x"}),
    ContractCase("POST", "/api/notes/{book_id}/0", 400, body={"type": "marker", "quote": "   "}),
    ContractCase(
        "POST",
        "/api/notes/{book_id}/0",
        400,
        body={"type": "marker", "quote": "x", "color": "chartreuse"},
    ),
    ContractCase(
        "POST", "/api/notes/{book_id}/0", 400, body={"type": "note", "quote": "x"}, note="type=note 缺 note_text"
    ),
    ContractCase("POST", "/api/notes/{missing_book_id}/0", 404, body={"type": "marker", "quote": "x"}),
    ContractCase(
        "PUT",
        "/api/notes/{book_id}/0/{note_id}",
        200,
        body={"note_text": "edited"},
        expected_keys=("id", "note_text", "message"),
    ),
    ContractCase("PUT", "/api/notes/{book_id}/0/nope", 404, body={"note_text": "x"}),
    ContractCase("PUT", "/api/notes/{book_id}/0/{note_id}", 400, body={"note_text": "  "}),
    ContractCase("PUT", "/api/notes/{missing_book_id}/0/x", 404, body={"note_text": "x"}),
    ContractCase("DELETE", "/api/notes/{book_id}/0/{note_id}", 204, content_type=""),
    ContractCase("DELETE", "/api/notes/{book_id}/0/nope", 404),
    ContractCase("DELETE", "/api/notes/{missing_book_id}/0/x", 404),
]


@pytest.mark.parametrize("case", NOTES_CASES, ids=str)
def test_notes契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    run_case(client, case, params)


# ---------------------------------------------------------------------------- search

SEARCH_CASES = [
    ContractCase(
        "GET",
        "/api/search/library?q={term}",
        200,
        expected_keys=(
            "query",
            "results",
            "grouped_by_book",
            "book_order",
            "book_metadata",
            "index_status_by_book",
            "total_matches",
            "searched_books",
            "failed_books",
            "unindexed_books",
            "is_truncated",
            "execution_time_ms",
            "status_message",
        ),
    ),
    ContractCase("GET", "/api/search/library?q=x&mode=bogus", 400),
    ContractCase("GET", "/api/search/library?q=x&sort_by=bogus", 400),
    ContractCase(
        "GET",
        "/api/search/{book_id}?q={term}",
        200,
        expected_keys=(
            "query",
            "results",
            "total_matches",
            "searched_books",
            "failed_books",
            "unindexed_books",
            "is_truncated",
            "execution_time_ms",
            "status_message",
        ),
    ),
    ContractCase("GET", "/api/search/{missing_book_id}?q=x", 404),
    ContractCase(
        "GET",
        "/api/search/{book_id}?q=x&mode=semantic",
        400,
        note="未建索引的书做语义检索 -> 400，不是 500",
    ),
    ContractCase(
        "POST",
        "/api/highlight/{book_id}/0",
        200,
        body={"search_term": UNIQUE_TERM},
        expected_keys=("ranges", "total_matches", "selected_occurrence_index"),
    ),
    ContractCase("POST", "/api/highlight/{book_id}/99", 404, body={"search_term": "x"}),
    ContractCase("POST", "/api/highlight/{missing_book_id}/0", 404, body={"search_term": "x"}),
    ContractCase("POST", "/api/highlight/{book_id}/0", 422, body={}, note="search_term 缺失"),
    ContractCase(
        "GET",
        "/api/index/{book_id}/status",
        200,
        expected_keys=("book_id", "status", "chunk_count", "model_name"),
    ),
    ContractCase("GET", "/api/index/{missing_book_id}/status", 404),
    ContractCase(
        "POST",
        "/api/index/{missing_book_id}",
        404,
        body={"force_reindex": False},
        note="真建索引会加载 embedding 模型（约 16 秒），happy path 见 test_scenarios.py",
    ),
]


@pytest.mark.parametrize("case", SEARCH_CASES, ids=str)
def test_search契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    run_case(client, case, params)


# -------------------------------------------------------------------------------- ai

AI_CASES = [
    ContractCase(
        "GET",
        "/api/ai/conversations/{book_uuid}",
        200,
        expected_keys=("book_uuid", "provider", "conversations"),
    ),
    ContractCase("GET", "/api/ai/conversations/{missing_uuid}", 404),
    ContractCase("GET", "/api/ai/conversations/not-a-uuid", 404, note="uuid 形状非法也归 404"),
    ContractCase(
        "GET",
        "/api/ai/conversations/{book_uuid}/{conversation_id}",
        200,
        expected_keys=CONVERSATION_KEYS,
    ),
    ContractCase("GET", "/api/ai/conversations/{book_uuid}/{missing_conversation_id}", 404),
    ContractCase("GET", "/api/ai/conversations/{book_uuid}/not-a-uuid", 400, note="conversation_id 形状非法 -> 400"),
    ContractCase("GET", "/api/ai/conversations/{missing_uuid}/{conversation_id}", 404),
    ContractCase(
        "PUT",
        "/api/ai/conversations/{book_uuid}/{conversation_id}",
        200,
        body={"provider": "anthropic", "messages": []},
        expected_keys=("ok",),
    ),
    ContractCase(
        "PUT",
        "/api/ai/conversations/{book_uuid}/{conversation_id}",
        400,
        body={"provider": "bogus", "messages": []},
    ),
    ContractCase(
        "PUT",
        "/api/ai/conversations/{missing_uuid}/{conversation_id}",
        404,
        body={"provider": "anthropic", "messages": []},
    ),
    ContractCase("PUT", "/api/ai/conversations/{book_uuid}/{conversation_id}", 422, body={}, note="provider 缺失"),
    ContractCase(
        "DELETE",
        "/api/ai/conversations/{book_uuid}/{conversation_id}",
        204,
        note="handler `return None`，FastAPI 仍挂 application/json；"
        "collections/notes 的 DELETE 用 Response(204) 则不挂。现状不一致，如实记录",
    ),
    ContractCase(
        "DELETE",
        "/api/ai/conversations/{book_uuid}/{missing_conversation_id}",
        204,
        note="删不存在的会话是幂等的 204，不是 404 —— 这是现状，不是主张",
    ),
    ContractCase("DELETE", "/api/ai/conversations/{missing_uuid}/{conversation_id}", 404),
    ContractCase(
        "GET",
        "/api/ai/conversations/{book_uuid}/{conversation_id}/export",
        200,
        expected_keys=CONVERSATION_KEYS,
    ),
    ContractCase(
        "GET",
        "/api/ai/conversations/{book_uuid}/{conversation_id}/export?format=md",
        200,
        content_type="text/markdown",
        must_contain=("# AI Conversation", SEEDED_MESSAGE_TEXT),
    ),
    ContractCase(
        "GET",
        "/api/ai/conversations/{book_uuid}/{conversation_id}/export?format=text",
        200,
        content_type="text/plain",
        must_contain=(f"User: {SEEDED_MESSAGE_TEXT}",),
    ),
    ContractCase("GET", "/api/ai/conversations/{book_uuid}/{conversation_id}/export?format=zip", 400),
    ContractCase("GET", "/api/ai/conversations/{book_uuid}/{missing_conversation_id}/export", 404),
    ContractCase(
        "POST",
        "/api/ai/rag/retrieve",
        200,
        body={"book_uuid": "{book_uuid}", "query": UNIQUE_TERM},
        expected_keys=("passages", "retrieval_time_ms"),
    ),
    ContractCase(
        "POST",
        "/api/ai/rag/retrieve",
        400,
        body={"book_uuid": "{book_uuid}", "query": "zzz-no-such-word"},
        note="未建索引且关键词回落也没命中 -> 400",
    ),
    ContractCase("POST", "/api/ai/rag/retrieve", 404, body={"book_uuid": MISSING_UUID, "query": "x"}),
    ContractCase("POST", "/api/ai/rag/retrieve", 422, body={}, note="book_uuid/query 缺失"),
    ContractCase(
        "POST",
        "/api/ai/question/{book_uuid}",
        200,
        body={"question": UNIQUE_TERM, "provider": "anthropic"},
        expected_keys=("answer", "message_id", "retrieval_sources", "metadata"),
    ),
    ContractCase(
        "POST",
        "/api/ai/question/{book_uuid}",
        400,
        body={"question": "   ", "provider": "anthropic"},
    ),
    ContractCase("POST", "/api/ai/question/{missing_uuid}", 404, body={"question": "x", "provider": "anthropic"}),
    ContractCase("POST", "/api/ai/question/{book_uuid}", 422, body={"provider": "anthropic"}, note="question 缺失"),
    ContractCase(
        "POST",
        "/api/ai/summary/{book_uuid}",
        400,
        body={"provider": "anthropic"},
        note="summary 用固定英文检索串，未建索引时关键词回落必然落空 -> 400；happy path 见 test_scenarios.py",
    ),
    ContractCase("POST", "/api/ai/summary/{missing_uuid}", 404, body={"provider": "anthropic"}),
    ContractCase("POST", "/api/ai/summary/{book_uuid}", 422, body={}, note="provider 缺失"),
    ContractCase(
        "GET",
        "/api/ollama/status",
        200,
        expected_keys=("running", "base_url", "error"),
        note="测试里网络是关的，所以走 running=False 分支",
    ),
    ContractCase("GET", "/api/ollama/models", 503, note="ollama 不可达 -> 503"),
]


@pytest.mark.parametrize("case", AI_CASES, ids=str)
def test_ai契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    # book_uuid 只在运行时才知道，body 里的占位符在这里补上。
    if isinstance(case.body, dict) and case.body.get("book_uuid") == "{book_uuid}":
        case = replace(case, body={**case.body, "book_uuid": params["book_uuid"]})
    run_case(client, case, params)


# -------------------------------------------------------------------------- settings

SETTINGS_CASES = [
    ContractCase("GET", "/api/settings", 200, expected_keys=SETTINGS_KEYS),
    ContractCase("PUT", "/api/settings", 200, body={"default_provider": "openai"}, expected_keys=SETTINGS_KEYS),
    ContractCase("PUT", "/api/settings", 400, body={"default_provider": "bogus"}),
    ContractCase("GET", "/api/settings/providers", 200, expected_keys=("providers",)),
    ContractCase("GET", "/api/settings/providers/anthropic", 200, expected_keys=PROVIDER_KEYS),
    ContractCase("GET", "/api/settings/providers/bogus", 404),
    ContractCase(
        "GET",
        "/api/settings/export",
        200,
        expected_keys=("default_provider", "preferences", "providers"),
    ),
    ContractCase(
        "POST",
        "/api/settings/import",
        200,
        body={"default_provider": "openai"},
        expected_keys=SETTINGS_KEYS,
    ),
    ContractCase("POST", "/api/settings/import", 422, body=[], note="body 不是对象"),
    ContractCase(
        "PUT",
        "/api/settings/providers/anthropic",
        200,
        body={"model_name": "renamed-model"},
        expected_keys=PROVIDER_KEYS,
    ),
    ContractCase("PUT", "/api/settings/providers/bogus", 404, body={"model_name": "x"}),
    ContractCase("PUT", "/api/settings/providers/anthropic", 422, body={"timeout": "abc"}),
    ContractCase("DELETE", "/api/settings/providers/openai", 204),
    ContractCase("DELETE", "/api/settings/providers/bogus", 404),
    ContractCase(
        "POST",
        "/api/settings/providers/anthropic/test",
        200,
        body={},
        expected_keys=("success", "provider", "message", "details"),
    ),
    ContractCase("POST", "/api/settings/providers/bogus/test", 404, body={}),
]


@pytest.mark.parametrize("case", SETTINGS_CASES, ids=str)
def test_settings契约(client: TestClient, params: dict[str, str], case: ContractCase) -> None:
    run_case(client, case, params)
