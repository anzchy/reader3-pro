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

from reader3_app.ai.providers.types import ProviderResponse
from reader3_app.web import server

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

#: The name ``params`` gives the collection it seeds. Named rather than inlined
#: because the L3 section below reads it back out of ``GET /api/collections``.
SEEDED_COLLECTION_NAME = "Seeded Shelf"


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

    collection = client.post("/api/collections", json={"name": SEEDED_COLLECTION_NAME})
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
            assert case.expected_keys, (
                f"{case} 没写 expected_keys。2xx 的 JSON 响应必须冻结顶层键集，"
                f"否则这条用例只断言了「返回了 2xx」——那正是本分支禁止的 wiring-only。"
                f"实测负载：{payload!r}"
            )
            # 这句必须在键集比对**之前**，而且不能是 `if isinstance(...)` 的守卫。
            # 旧写法把整段比对包在 `if isinstance(payload, dict)` 里，于是一个
            # 改成 `return []` 的 handler 直接从 if 底下溜过去，六组 nominal-JSON
            # 用例全都还是绿的——「契约被钉住了」的错觉，比没有测试更危险。
            assert isinstance(payload, dict), (
                f"{case.method} {path}: 声明了 expected_keys 就必须回一个 JSON 对象，"
                f"实得 {type(payload).__name__}：{payload!r}"
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
    ContractCase("GET", "/api/library", 200, expected_keys=("books",)),
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
    # 018 WI-5c (W5-12): DELETE /api/library/{book_id}. No 204 / 409 rows: those are
    # covered with real trees in test_library_delete_route.py (C-1, C-5, C-6, C-14).
    ContractCase("DELETE", "/api/library/{missing_book_id}", 404, must_contain=("Book not found",)),
    ContractCase("DELETE", "/api/library/notabook", 400),
    ContractCase("DELETE", "/api/library/{book_id}?delete_conversations=maybe", 400),
    ContractCase("DELETE", "/api/library/{book_id}?delete_conversations=1", 400, note="W5-8：只认 true/false（不分大小写）"),
    # 018 WI-6 (E24): GET /api/library/export. The envelope is exactly {"books"}; the
    # include grammar is exactly one value, "conversations" (case-insensitive), else 400.
    ContractCase("GET", "/api/library/export", 200, expected_keys=("books",)),
    ContractCase("GET", "/api/library/export?include=conversations", 200, expected_keys=("books",)),
    ContractCase("GET", "/api/library/export?include=bogus", 400),
    ContractCase("GET", "/api/library/export?include=", 400),
    ContractCase("GET", "/api/library/export?include=conversations&include=conversations", 400),
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


# =========================================================================== L3
# 内容断言（WI-13）。
#
# 上面六张表冻结的是**信封**：状态码、媒体类型、顶层键集。信封是必要的，但它对
# 「形状对、内容空」完全无感——把 handler 改成 `return {"collections": []}`、
# 恒返回 0 命中、恒 `success: false`，六张表照样全绿。那种测试给人「契约被钉住了」
# 的错觉，比没有测试更危险。
#
# 下面这一节钉的是**内容**：seed 出来的东西必须真的能从响应里读回来。每条用例都
# 写明了「如果这条不在，哪一种变异会溜过去」。
#
# 这一节不出网。连通性那条打的是 `server._call_provider`——`api_test_provider`
# 通往网络的唯一一条路（WI-30 之后 `server.py` 里另外两个出网点是
# `_egress_get_json` / `_egress_post_stream`，都不在这条路由的调用链上）。
# 不要 patch `urllib.request.urlopen`：`src/` 里已经一次直接调用都没有了，
# 打在那儿等于没打。


def test_L3_collections列表里必须真的有刚建的那个集合(
    client: TestClient, params: dict[str, str]
) -> None:
    """finding tests/11。

    表上那条 `GET /api/collections -> 200` 只冻结了 `{"collections"}` 这个键集，
    所以一个恒 `return {"collections": []}` 的 handler 是绿的——而列表路由最常见的
    坏法恰恰就是「存住了但列不出来」。
    """
    body = client.get("/api/collections").json()
    collections = body["collections"]

    assert isinstance(collections, list) and collections, (
        f"GET /api/collections 回了空列表，但 params 刚建过一个集合；实得 {body!r}"
    )

    by_id = {str(c.get("id")): c for c in collections}
    seeded_id = params["collection_id"]
    assert seeded_id in by_id, f"刚建的集合 {seeded_id} 不在列表里；实得 id={sorted(by_id)}"
    assert by_id[seeded_id]["name"] == SEEDED_COLLECTION_NAME, (
        f"集合 {seeded_id} 的 name 变了：期望 {SEEDED_COLLECTION_NAME!r}，"
        f"实得 {by_id[seeded_id]['name']!r}"
    )


def test_L3_全库搜索必须真的命中UNIQUE_TERM(client: TestClient, params: dict[str, str]) -> None:
    """finding tests/12。

    `UNIQUE_TERM` 这个常量存在的全部意义就是「命中它 = 章节正文确实被检索到了」
    （它只出现在 chapter 0，别处没有）。表上那条用例只断了十三个顶层键都在，
    于是一个恒返回 0 命中的 handler 照样绿——那正好把这个常量的意义抹平。
    """
    body = client.get(f"/api/search/library?q={UNIQUE_TERM}").json()

    assert body["total_matches"] >= 1, (
        f"搜 {UNIQUE_TERM!r} 一条都没命中，但它就在 chapter 0 的正文里；"
        f"total_matches={body['total_matches']} status_message={body['status_message']!r}"
    )

    results = body["results"]
    assert results, f"total_matches={body['total_matches']} 但 results 是空的：信封对、内容空"

    hits = [r for r in results if r.get("book_id") == BOOK_ID]
    assert hits, (
        f"命中里没有 seed 的那本书 {BOOK_ID}；实得 book_id="
        f"{sorted({str(r.get('book_id')) for r in results})}"
    )
    assert any(UNIQUE_TERM.lower() in str(h.get("match_text", "")).lower() for h in hits), (
        f"命中项的 match_text 里没有 {UNIQUE_TERM!r}；实得 "
        f"{[h.get('match_text') for h in hits[:5]]!r}"
    )

    assert BOOK_ID in body["book_order"], f"book_order 里没有 {BOOK_ID}：{body['book_order']!r}"
    assert body["grouped_by_book"].get(BOOK_ID), (
        f"grouped_by_book[{BOOK_ID!r}] 是空的，但 results 里有它的命中"
    )


def test_L3_rag检索必须返回真实段落(client: TestClient, params: dict[str, str]) -> None:
    """finding tests/13。

    这条是真端到端，没有打桩：seed 的书**没有**建语义索引，`retrieve_passages`
    因此走它自己的关键词回落，直接读 tmp_path 里那个 `book.pkl`。全程不加载
    `paraphrase-multilingual-MiniLM-L12-v2`，也不碰 chroma。

    表上那条只断了 `{"passages", "retrieval_time_ms"}` 两个键，所以一个恒
    `return {"passages": [], "retrieval_time_ms": 0}` 的 handler 是绿的。
    """
    resp = client.post(
        "/api/ai/rag/retrieve",
        json={"book_uuid": params["book_uuid"], "query": UNIQUE_TERM},
    )
    assert resp.status_code == 200, resp.text
    passages = resp.json()["passages"]

    assert passages, f"检索 {UNIQUE_TERM!r} 回了 0 段，但它就在 chapter 0 的正文里"

    matching = [p for p in passages if UNIQUE_TERM in str(p.get("text", ""))]
    assert matching, (
        f"没有一段正文含 {UNIQUE_TERM!r}——段落不是从 seed 那本书里来的；"
        f"实得 {[str(p.get('text', ''))[:80] for p in passages]!r}"
    )
    hit = matching[0]
    assert hit["chapter_order"] == 0, f"命中段落的 chapter_order 期望 0，实得 {hit['chapter_order']!r}"
    assert hit["chapter_title"] == CHAPTER_0_TITLE, (
        f"命中段落的 chapter_title 期望 {CHAPTER_0_TITLE!r}，实得 {hit['chapter_title']!r}"
    )


#: 五家 provider。`/api/settings/providers` 是设置页唯一的数据来源，列表空了
#: 前端就一个都选不出来——而顶层键集 `{"providers"}` 对此毫无感觉。
EXPECTED_PROVIDER_NAMES = ("anthropic", "openai", "gemini", "ollama", "openrouter")


def test_L3_provider列表必须列全五家(client: TestClient, params: dict[str, str]) -> None:
    """finding tests/14（前半）。"""
    body = client.get("/api/settings/providers").json()
    providers = body["providers"]

    assert isinstance(providers, list) and providers, f"provider 列表是空的：{body!r}"

    names = [str(p.get("name")) for p in providers]
    missing = sorted(set(EXPECTED_PROVIDER_NAMES) - set(names))
    assert not missing, f"provider 列表少了 {missing}；实得 {names}"


def test_L3_连通性自测在打桩成功时必须报success为True(
    client: TestClient, params: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """finding tests/14（后半）。

    表上那条只断了 `{"success", "provider", "message", "details"}` 四个键，于是一个
    恒 `success: false` 的 handler 是绿的——而这条路由的**全部**产出就是那个布尔值。

    桩打在 `server._call_provider`：`api_test_provider` 通往网络的唯一一条路。
    桩里那个 model 名字只出现在这个文件里，所以在 `details.model` 里见到它，
    是「provider 的回包确实被原样传出来了」的证据，而不是「handler 编了个 True」。
    """
    probe_model = "connectivity-probe-model-v1"
    calls: list[dict[str, Any]] = []

    def _stub_call_provider(provider_name: str, **kwargs: Any) -> ProviderResponse:
        calls.append({"provider": provider_name, **kwargs})
        return ProviderResponse(text="OK", model=probe_model, finish_reason="stop", token_count=2)

    monkeypatch.setattr(server, "_call_provider", _stub_call_provider)

    resp = client.post("/api/settings/providers/anthropic/test", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [c["provider"] for c in calls] == ["anthropic"], (
        f"期望恰好打一次 anthropic，实得 {[c['provider'] for c in calls]}"
    )
    assert body["success"] is True, (
        f"provider 回了正常响应，连通性自测却报 success={body['success']!r}；message={body['message']!r}"
    )
    assert body["provider"] == "anthropic"
    assert body["details"]["model"] == probe_model, (
        f"details.model 期望是桩返回的 {probe_model!r}，实得 {body['details'].get('model')!r}"
    )


# ------------------------------------------------------------ 提问长度上限（tests/16）

#: `api_ai_question` 的守卫写的是 `len(question) > 1000`，`question` 是 `strip()`
#: 之后的字符串。`len()` 数的是 **code point**，不是 byte。
QUESTION_MAX_CHARS = 1000

#: 恰好 1000 个 code point 的 ASCII 提问，且含 `UNIQUE_TERM`（可读性用，检索已打桩）。
QUESTION_AT_LIMIT = UNIQUE_TERM + "a" * (QUESTION_MAX_CHARS - len(UNIQUE_TERM))
QUESTION_OVER_LIMIT = QUESTION_AT_LIMIT + "a"

#: 1000 个汉字 = 1000 code point = 3000 byte（UTF-8）。守卫如果改成数 byte
#: （`len(question.encode())`），纯 ASCII 的两条用例**一条都不会红**，只有这条会。
QUESTION_AT_LIMIT_CJK = "书" * QUESTION_MAX_CHARS
QUESTION_OVER_LIMIT_CJK = "书" * (QUESTION_MAX_CHARS + 1)


@pytest.fixture
def stub_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    """让检索恒有结果，好让长度守卫成为响应里唯一的变量。

    `retrieve_passages` 的关键词回落是拿**整条 query** 去 `text.find()` 的，所以任何
    1000 字的提问都必然落空 → `RuntimeError` → 400。不打桩的话，「1000 字应当 200」
    这条用例会因为一个和长度无关的理由变红，于是它再也证明不了守卫的边界在哪。
    """

    def _stub(book_folder: str, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return ([{
            "chapter_id": "0",
            "chapter_order": 0,
            "chapter_title": CHAPTER_0_TITLE,
            "text": f"stubbed passage mentioning {UNIQUE_TERM}",
            "similarity": 1.0,
        }], 1)

    monkeypatch.setattr(server, "retrieve_passages", _stub)


@pytest.mark.parametrize(
    "question,label",
    [
        (QUESTION_AT_LIMIT, "1000 个 ASCII 字符"),
        (QUESTION_AT_LIMIT_CJK, "1000 个汉字（3000 byte）"),
    ],
    ids=["ascii-1000", "cjk-1000"],
)
def test_L3_提问恰好到上限必须放行(
    client: TestClient,
    params: dict[str, str],
    stub_retrieval: None,
    question: str,
    label: str,
) -> None:
    """finding tests/16。上限是闭区间：`> 1000` 才拒。"""
    assert len(question) == QUESTION_MAX_CHARS, "用例自检：长度必须正好卡在上限上"

    resp = client.post(
        f"/api/ai/question/{params['book_uuid']}",
        json={"question": question, "provider": "anthropic"},
    )
    assert resp.status_code == 200, f"{label} 应当放行，实得 {resp.status_code}：{resp.text[:400]}"


@pytest.mark.parametrize(
    "question,label",
    [
        (QUESTION_OVER_LIMIT, "1001 个 ASCII 字符"),
        (QUESTION_OVER_LIMIT_CJK, "1001 个汉字"),
    ],
    ids=["ascii-1001", "cjk-1001"],
)
def test_L3_提问超过上限必须拒且说明是长度问题(
    client: TestClient,
    params: dict[str, str],
    stub_retrieval: None,
    question: str,
    label: str,
) -> None:
    """finding tests/16。

    删掉整条 `if len(question) > 1000` 守卫，改这条之前的套件是全绿的——也就是说
    「提问长度有上限」这件事从来没有被任何一条断言拿住过。400 之外还要断消息里
    提到了那个上限：否则一个把超长提问按「空提问」拒掉的实现也能骗过状态码。
    """
    assert len(question) == QUESTION_MAX_CHARS + 1, "用例自检：长度必须正好越过上限一位"

    resp = client.post(
        f"/api/ai/question/{params['book_uuid']}",
        json={"question": question, "provider": "anthropic"},
    )
    assert resp.status_code == 400, f"{label} 应当被拒，实得 {resp.status_code}：{resp.text[:400]}"

    detail = str(resp.json()["detail"])
    assert str(QUESTION_MAX_CHARS) in detail, f"错误消息没提到上限 {QUESTION_MAX_CHARS}：{detail!r}"
    assert "long" in detail.lower(), f"错误消息没说明这是长度问题：{detail!r}"
