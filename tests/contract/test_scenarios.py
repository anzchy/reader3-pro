"""Layer 3 of the route contract: the few endpoints that carry real domain logic.

Definition site: `docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md`
§4 layer 3. Deliberately short. Layer 2 already froze every route's shape; a scenario
only earns its place when a *value* has to survive a round trip through the filesystem,
or when a rule (escaping, truncation, orphaning, key redaction) lives in the handler.

Each test here would still pass if you only checked status codes — which is exactly
why none of them do. They compare what came back against what went in, character
for character.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from reader3_app.ai.providers.types import ProviderResponse

from conftest import (
    BOOK_ID,
    BOOK_TITLE,
    CHAPTER_0_TITLE,
    FAKE_ANSWER,
    FAKE_MODEL,
    UNIQUE_TERM,
    World,
)

CONV_A = "aaaaaaaa-0000-4000-8000-000000000001"
CONV_B = "aaaaaaaa-0000-4000-8000-000000000002"


# ------------------------------------------------------------------ annotations CRUD


def test_标注的增删改查是一致的(world: World) -> None:
    """POST 存进去的字段，GET 必须逐字返回；PUT 后要变；DELETE 后要 404。

    这是用户产生的、丢了不能重新生成的数据，所以断言到字段级而不是状态码级。
    注意 v1 的 PUT 只能改 `note_text`——`UpdateAnnotationRequest` 没有 `color` 字段，
    所以「改颜色」在这份冻结的 API 里做不到（见交付报告）。
    """
    client = world.client
    payload = {
        "type": "note",
        "color": "pink",
        "quote": "a traveller who spoke of Ozymandias",
        "prefix": "I met ",
        "suffix": ", king",
        "position": 12,
        "cfi": "epubcfi(/6/4!/4/2/2)",
        "note_text": 'Tom & "Jerry" <3',
    }
    created = client.post(f"/api/notes/{BOOK_ID}/0", json=payload)
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    listed = client.get(f"/api/notes/{BOOK_ID}/0")
    assert listed.status_code == 200
    items = listed.json()["annotations"]
    assert [a["id"] for a in items] == [note_id]
    got = items[0]

    assert got["quote"] == payload["quote"]
    assert got["prefix"] == payload["prefix"]
    assert got["suffix"] == payload["suffix"]
    assert got["type"] == "note"
    assert got["color"] == "pink"
    assert got["position"] == 12
    assert got["cfi"] == payload["cfi"]
    assert got["book_id"] == BOOK_ID
    assert got["chapter_index"] == 0
    assert got["orphaned"] is False
    # 写入时 html.escape、读出时 html.unescape，来回必须是恒等的。
    assert got["note_text"] == 'Tom & "Jerry" <3'

    updated = client.put(f"/api/notes/{BOOK_ID}/0/{note_id}", json={"note_text": "second thoughts & more"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == note_id

    after_update = client.get(f"/api/notes/{BOOK_ID}/0").json()["annotations"][0]
    assert after_update["note_text"] == "second thoughts & more"
    assert after_update["quote"] == payload["quote"], "改笔记不该动引文"

    assert client.delete(f"/api/notes/{BOOK_ID}/0/{note_id}").status_code == 204
    assert client.get(f"/api/notes/{BOOK_ID}/0").json()["annotations"] == []
    assert client.delete(f"/api/notes/{BOOK_ID}/0/{note_id}").status_code == 404


def test_上下文超长时前缀留尾巴后缀留开头(world: World) -> None:
    """50 字上限的截断方向是有意的：prefix 保留紧挨引文的那一段，suffix 同理。

    截反了不会报错，只会让重定位在长段落里静默漂移——所以这条断言的是方向，不是长度。
    """
    prefix = "P" * 60 + "KEEP-TAIL"
    suffix = "KEEP-HEAD" + "S" * 60
    created = world.client.post(
        f"/api/notes/{BOOK_ID}/0",
        json={"type": "marker", "quote": "traveller", "prefix": prefix, "suffix": suffix},
    )
    assert created.status_code == 201, created.text

    got = world.client.get(f"/api/notes/{BOOK_ID}/0").json()["annotations"][0]
    assert len(got["prefix"]) == 50 and got["prefix"].endswith("KEEP-TAIL")
    assert len(got["suffix"]) == 50 and got["suffix"].startswith("KEEP-HEAD")


def test_引文在正文里找不到的标注会被判为孤儿并从列表消失(world: World) -> None:
    """`_refresh_orphaned_annotations` 是 notes 这一组里唯一有判断的地方。

    直接改盘上的 notes.json 而不是走 API，因为 API 不接受一条对不上正文的标注——
    孤儿是**书变了**造成的，只有从磁盘那侧才能造出这个局面。
    """
    client = world.client
    created = client.post(f"/api/notes/{BOOK_ID}/0", json={"type": "marker", "quote": "traveller"})
    note_id = created.json()["id"]
    assert len(client.get(f"/api/notes/{BOOK_ID}/0").json()["annotations"]) == 1

    notes_path = world.book_dir / "notes.json"
    data = json.loads(notes_path.read_text(encoding="utf-8"))
    data["annotations"][0]["quote"] = "text that this book has never contained"
    notes_path.write_text(json.dumps(data), encoding="utf-8")

    after = client.get(f"/api/notes/{BOOK_ID}/0").json()
    assert after["annotations"] == [] and after["count"] == 0

    # 孤儿只是被过滤掉，不是被删掉——盘上仍要留着，并被标记。
    persisted = json.loads(notes_path.read_text(encoding="utf-8"))["annotations"]
    assert [a["id"] for a in persisted] == [note_id]
    assert persisted[0]["orphaned"] is True


def test_整本书的标注按章节分组并统计(world: World) -> None:
    client = world.client
    client.post(f"/api/notes/{BOOK_ID}/0", json={"type": "marker", "quote": "traveller"})
    client.post(f"/api/notes/{BOOK_ID}/1", json={"type": "marker", "quote": "colossal"})
    client.post(f"/api/notes/{BOOK_ID}/1", json={"type": "underline", "quote": "decay"})

    body = client.get(f"/api/notes/{BOOK_ID}").json()
    assert body["total_count"] == 3
    groups = {g["chapter_index"]: g for g in body["annotations_by_chapter"]}
    assert sorted(groups) == [0, 1]
    assert groups[0]["count"] == 1 and groups[0]["chapter_title"] == CHAPTER_0_TITLE
    assert groups[1]["count"] == 2
    assert {a["quote"] for a in groups[1]["annotations"]} == {"colossal", "decay"}


# ------------------------------------------------------------- AI conversations


def test_AI会话的持久化(world: World) -> None:
    """建会话 → 列表能看见 → 导出里有那条消息 → 删掉 → 列表里没了。

    导出断言的是消息正文本身，不是「导出返回了 200」：Phase 2 若把 messages 丢在
    序列化的某一层，状态码不会变，正文会没。
    """
    client = world.client
    uuid = world.book_uuid
    turn = "what does the traveller say about the pedestal"

    saved = client.put(
        f"/api/ai/conversations/{uuid}/{CONV_A}",
        json={
            "provider": "anthropic",
            "model": "claude-fixture",
            "messages": [
                {
                    "id": "m1",
                    "role": "user",
                    "content": turn,
                    "timestamp": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "m2",
                    "role": "assistant",
                    "content": "Nothing beside remains.",
                    "timestamp": "2026-01-01T00:00:01Z",
                },
            ],
        },
    )
    assert saved.status_code == 200 and saved.json() == {"ok": True}

    listing = client.get(f"/api/ai/conversations/{uuid}").json()
    assert [c["conversation_id"] for c in listing["conversations"]] == [CONV_A]
    assert listing["book_uuid"] == uuid

    thread = client.get(f"/api/ai/conversations/{uuid}/{CONV_A}").json()
    assert thread["book_folder"] == BOOK_ID
    assert thread["provider"] == "anthropic"
    assert [(m["role"], m["content"]) for m in thread["messages"]] == [
        ("user", turn),
        ("assistant", "Nothing beside remains."),
    ]

    as_text = client.get(f"/api/ai/conversations/{uuid}/{CONV_A}/export?format=text")
    assert as_text.text == f"User: {turn}\n\nAssistant: Nothing beside remains.\n"

    as_md = client.get(f"/api/ai/conversations/{uuid}/{CONV_A}/export?format=md").text
    assert f"- conversation_id: `{CONV_A}`" in as_md
    assert turn in as_md and "Nothing beside remains." in as_md

    assert client.delete(f"/api/ai/conversations/{uuid}/{CONV_A}").status_code == 204
    assert client.get(f"/api/ai/conversations/{uuid}").json()["conversations"] == []
    assert client.get(f"/api/ai/conversations/{uuid}/{CONV_A}").status_code == 404


def test_只有角色和id都合法的消息才会落盘(world: World) -> None:
    """`api_ai_put_conversation` 会静默丢掉 role 不是 user/assistant、或 id 为空的消息。

    静默丢弃是最容易在重构里走样的那类行为——它没有错误路径可以断言，只能断言结果。
    """
    client = world.client
    client.put(
        f"/api/ai/conversations/{world.book_uuid}/{CONV_B}",
        json={
            "provider": "anthropic",
            "messages": [
                {"id": "ok", "role": "user", "content": "kept", "timestamp": "t"},
                {"id": "sys", "role": "system", "content": "dropped by role", "timestamp": "t"},
                {"id": "", "role": "user", "content": "dropped by empty id", "timestamp": "t"},
            ],
        },
    )
    thread = client.get(f"/api/ai/conversations/{world.book_uuid}/{CONV_B}").json()
    assert [m["content"] for m in thread["messages"]] == ["kept"]


# --------------------------------------------------------------------- AI answering


def test_提问把provider的回答原样放进answer字段(world: World) -> None:
    """假 provider 返回一段独一无二的字符串，断言它出现在 `answer` 里。

    这是这几条 AI 路由唯一不会退化成 wiring-only 的写法：断言「stub 被调用过」在
    handler 把结果丢掉之后照样绿，断言这段哨兵文本走到了正确的字段则不会。
    """
    client = world.client
    body = client.post(
        f"/api/ai/question/{world.book_uuid}",
        json={"question": UNIQUE_TERM, "provider": "anthropic"},
    )
    assert body.status_code == 200, body.text
    payload = body.json()

    assert payload["answer"] == FAKE_ANSWER
    assert payload["metadata"]["model"] == FAKE_MODEL
    assert payload["metadata"]["provider"] == "anthropic"
    assert payload["metadata"]["token_count"] == 7

    # 检索到的段落必须真的来自这本书的第 0 章。
    sources = payload["retrieval_sources"]
    assert sources and sources[0]["chapter_order"] == 0
    assert sources[0]["chapter_title"] == CHAPTER_0_TITLE
    assert UNIQUE_TERM in sources[0]["text"]


def test_提问带上会话id时回答会被写进那条会话(world: World) -> None:
    """`_save_conversation_snapshot` 只在历史里带 conversation_id 时触发。

    这是问答与持久化之间唯一的耦合点，也是重构最容易漏掉的一条线。
    """
    client = world.client
    uuid = world.book_uuid
    client.post(
        f"/api/ai/question/{uuid}",
        json={
            "question": UNIQUE_TERM,
            "provider": "anthropic",
            "conversation_history": [
                {
                    "id": "m1",
                    "role": "user",
                    "content": UNIQUE_TERM,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "conversation_id": CONV_A,
                }
            ],
        },
    )

    thread = client.get(f"/api/ai/conversations/{uuid}/{CONV_A}")
    assert thread.status_code == 200, "带 conversation_id 提问后，那条会话必须存在于磁盘上"
    messages = thread.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == FAKE_ANSWER


def _parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    """Split an SSE body into (event, data) pairs. Blocks are separated by a blank line."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if name:
            events.append((name, json.loads(data)))
    return events


def test_流式提问按meta_chunk_done的顺序推事件(world: World) -> None:
    """`?stream=true` 是同一条路由的另一套返回体，清单快照看不见它变了。

    Phase 4 的前端要按 `event:` 名字分派，所以这里断言的是**事件序列和字段**，
    不是「响应是 200」。
    """
    with world.client.stream(
        "POST",
        f"/api/ai/question/{world.book_uuid}?stream=true",
        json={"question": UNIQUE_TERM, "provider": "anthropic"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.read().decode("utf-8"))

    assert [name for name, _ in events] == ["meta", "chunk", "done"]

    meta = dict(events[0][1])
    assert meta["metadata"]["provider"] == "anthropic"
    assert meta["retrieval_sources"][0]["chapter_title"] == CHAPTER_0_TITLE
    assert meta["message_id"]

    assert events[1][1]["delta"] == FAKE_ANSWER

    done = dict(events[2][1])
    assert done["model"] == FAKE_MODEL
    assert done["finish_reason"] == "stop"
    assert "generation_time_ms" in done["metadata"]


def test_总结把provider的回答解析进content(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """`/api/ai/summary` 用的是一句固定英文检索串，未建索引的书必然检索落空（400）。

    所以这里换掉 `retrieve_passages`，让路由跑到真正要测的那一段：provider 回的
    JSON 被 `_parse_summary_payload` 拆进 `content` 的三个字段。检索本身归
    `/api/ai/rag/retrieve` 的用例，不在这里重复。
    """
    from reader3_app.web import server

    def _fake_retrieve(book_folder: str, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return (
            [
                {
                    "chapter_id": "0",
                    "chapter_order": 0,
                    "chapter_title": CHAPTER_0_TITLE,
                    "text": f"...{UNIQUE_TERM}...",
                    "similarity": 1.0,
                }
            ],
            3,
        )

    def _fake_call(provider_name: str, **kwargs: Any) -> ProviderResponse:
        return ProviderResponse(
            text=json.dumps({"overview": FAKE_ANSWER, "highlights": ["one", "two"], "background": "b"}),
            model=FAKE_MODEL,
            finish_reason="stop",
            token_count=9,
        )

    monkeypatch.setattr(server, "retrieve_passages", _fake_retrieve)
    monkeypatch.setattr(server, "_call_provider", _fake_call)

    body = world.client.post(f"/api/ai/summary/{world.book_uuid}", json={"provider": "anthropic", "max_tokens": 128})
    assert body.status_code == 200, body.text
    payload = body.json()

    assert payload["content"] == {
        "overview": FAKE_ANSWER,
        "highlights": ["one", "two"],
        "background": "b",
    }
    assert payload["book_uuid"] == world.book_uuid
    assert payload["provider"] == "anthropic"
    assert payload["model"] == FAKE_MODEL
    assert payload["token_count"] == 9
    assert payload["from_cache"] is False
    assert payload["metadata"]["retrieval_time_ms"] == 3
    assert payload["metadata"]["finish_reason"] == "stop"


def test_总结收到散文时降级成overview而不是报错(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """模型不听话、回了散文而不是 JSON，是**预期的降级路径**：整段进 overview。

    这条分支只在日志里留痕，没有错误码——不测就永远不会有人发现它坏了。
    """
    from reader3_app.web import server

    monkeypatch.setattr(
        server,
        "retrieve_passages",
        lambda book_folder, **kwargs: ([], 1),
    )
    monkeypatch.setattr(
        server,
        "_call_provider",
        lambda provider_name, **kwargs: ProviderResponse(
            text="这不是 JSON，就是一段话。", model=FAKE_MODEL, finish_reason="stop", token_count=4
        ),
    )

    payload = world.client.post(f"/api/ai/summary/{world.book_uuid}", json={"provider": "anthropic"}).json()
    assert payload["content"] == {
        "overview": "这不是 JSON，就是一段话。",
        "highlights": [],
        "background": "",
    }


# ------------------------------------------------------------------------- search


def test_书内搜索返回真实的章节命中(world: World) -> None:
    """断言到 `match_text` 与左右上下文，而不是「有结果」——搜索的价值全在这三个字段上。"""
    body = world.client.get(f"/api/search/{BOOK_ID}?q={UNIQUE_TERM}").json()
    assert body["total_matches"] == 1
    hit = body["results"][0]
    assert hit["book_id"] == BOOK_ID
    assert hit["book_title"] == BOOK_TITLE
    assert hit["chapter_order"] == 0
    assert hit["chapter_title"] == CHAPTER_0_TITLE
    assert hit["match_text"] == UNIQUE_TERM
    assert hit["context_before"].endswith("spoke of")
    assert hit["context_after"].startswith(", king")
    assert hit["occurrence_index"] == 0

    miss = world.client.get(f"/api/search/{BOOK_ID}?q=zzz-no-such-word").json()
    assert miss["total_matches"] == 0 and miss["results"] == []


def test_高亮返回的区间正好圈住搜索词(world: World) -> None:
    """`ranges` 是要交给前端按字符下标画高亮的，偏一位就画歪。"""
    body = world.client.post(f"/api/highlight/{BOOK_ID}/0", json={"search_term": UNIQUE_TERM}).json()
    assert body["total_matches"] == 1
    assert body["selected_occurrence_index"] == 0
    (span,) = body["ranges"]

    chapter_text = f"I met a traveller who spoke of {UNIQUE_TERM}, king of kings."
    assert chapter_text[span["start"] : span["end"]] == UNIQUE_TERM


# --------------------------------------------------------------------- collections


def test_合集与书的关联会体现在统计里(world: World) -> None:
    client = world.client
    collection_id = client.post("/api/collections", json={"name": "Shelf"}).json()["id"]

    added = client.post(f"/api/collections/{collection_id}/books", json={"add": [BOOK_ID], "remove": []})
    assert added.status_code == 200
    assert added.json()["book_ids"] == [BOOK_ID]
    assert client.get(f"/api/collections/{collection_id}").json()["book_ids"] == [BOOK_ID]

    stats = client.get(f"/api/library/stats?scope=collection:{collection_id}&fresh=true").json()
    assert stats["scope"] == f"collection:{collection_id}"
    assert stats["books_total"] == 1
    assert stats["sections_total"] == 2, "两章的书，统计里就该是 2"

    removed = client.post(f"/api/collections/{collection_id}/books", json={"add": [], "remove": [BOOK_ID]})
    assert removed.json()["book_ids"] == []
    empty = client.get(f"/api/library/stats?scope=collection:{collection_id}&fresh=true").json()
    assert empty["books_total"] == 0 and empty["sections_total"] == 0


# ------------------------------------------------------------------------ settings


def test_API_KEY_写得进去但读不出来(world: World) -> None:
    """项目的一条硬规则：API key 永远不回传浏览器，导出里也不能带。

    这条如果退化成只看状态码，泄漏会静悄悄地发生。
    """
    client = world.client
    secret = "sk-super-secret-do-not-leak"

    put = client.put("/api/settings/providers/openai", json={"api_key": secret, "enabled": True})
    assert put.status_code == 200
    assert "api_key" not in put.json()
    assert put.json()["api_key_configured"] is True

    for path in ("/api/settings", "/api/settings/providers/openai", "/api/settings/export"):
        assert secret not in client.get(path).text, f"{path} 泄漏了 api_key"

    # 盘上必须真的写进去了，否则上面三条只是「没存所以没漏」。
    assert secret in world.settings_path.read_text(encoding="utf-8")


def test_导入设置不会带进api_key也不会覆盖已有的(world: World) -> None:
    client = world.client
    client.put("/api/settings/providers/openai", json={"api_key": "sk-existing"})

    imported = client.post(
        "/api/settings/import",
        json={
            "default_provider": "openai",
            "providers": {"openai": {"api_key": "sk-from-import", "model_name": "imported-model"}},
        },
    )
    assert imported.status_code == 200
    assert imported.json()["default_provider"] == "openai"

    on_disk = json.loads(world.settings_path.read_text(encoding="utf-8"))
    assert on_disk["providers"]["openai"]["api_key"] == "sk-existing", "导入不得覆盖已有的 key"
    assert on_disk["providers"]["openai"]["model_name"] == "imported-model"


def test_设置改动会落盘并被下一次读取看见(world: World) -> None:
    client = world.client
    assert client.get("/api/settings").json()["default_provider"] == "anthropic"

    client.put("/api/settings", json={"default_provider": "gemini"})
    assert client.get("/api/settings").json()["default_provider"] == "gemini"
    assert json.loads(world.settings_path.read_text(encoding="utf-8"))["default_provider"] == "gemini"


# ------------------------------------------------------------------------- indexing


def test_建索引的返回体原样透传给前端(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """真建索引要加载 embedding 模型（实测约 16 秒），放不进 unit lane。

    所以这里换掉 `BookVectorIndex`，只守住「路由不改写索引层给出的状态」这一条。
    索引本身的正确性归 `tests/integration`，不归契约层。
    """
    from reader3_app.web import server

    sentinel = {
        "book_id": BOOK_ID,
        "status": "indexed",
        "chunk_count": 42,
        "model_name": "sentinel-embedder",
        "indexed_at": "2026-01-01T00:00:00+00:00",
    }

    class _FakeIndex:
        def __init__(self, book_id: str, *, books_dir: str) -> None:
            self.book_id = book_id

        def index_book(self, *, force_reindex: bool = False) -> dict[str, Any]:
            return {**sentinel, "forced": force_reindex}

    monkeypatch.setattr(server, "BookVectorIndex", _FakeIndex)

    body = world.client.post(f"/api/index/{BOOK_ID}", json={"force_reindex": True})
    assert body.status_code == 200, body.text
    assert body.json() == {**sentinel, "forced": True}


def test_没建索引的书状态是not_indexed(world: World) -> None:
    body = world.client.get(f"/api/index/{BOOK_ID}/status").json()
    assert body["book_id"] == BOOK_ID
    assert body["status"] == "not_indexed"
    assert body["chunk_count"] == 0


def test_索引元数据被状态接口原样读出(world: World) -> None:
    """状态接口读的是 `chroma_db/index_meta.json`，不需要 chromadb 本体。"""
    meta_dir = world.book_dir / "chroma_db"
    meta_dir.mkdir()
    meta = {
        "book_id": BOOK_ID,
        "status": "indexed",
        "chunk_count": 7,
        "model_name": "written-by-the-test",
        "indexed_at": "2026-01-01T00:00:00+00:00",
    }
    (meta_dir / "index_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    assert world.client.get(f"/api/index/{BOOK_ID}/status").json() == meta
