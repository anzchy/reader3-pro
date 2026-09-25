"""一本书的 `ai_meta.json` 坏了，书库不许因此打不开。

这条降级是本分支自己造的（`server._book_uuid_or_none`），不是既有行为的刻画，
所以它必须有自己的测试——否则下一次重构把 `except` 收窄或把调用点换回
`book_uuid_resolver.book_uuid_for_folder()`，整页会重新变成 500 而没有任何东西
会红。

**为什么是降级而不是 500**：坏的是一本书，塌的是整个书库首页。用户连 UI 都进
不去，也就无从修那本书。错误处理不该比错误本身更糟。

对应的三条可观测证据各有一条断言，缺一条这套降级就变成静默：
  1. 服务端 warning 点名是哪本书（`test_坏书在日志里被点名`）；
  2. 原文件一个字节都不改（`test_坏文件不被覆盖`）——覆盖会让用户的 AI 会话
     永久失联，而人还能修一个自己读得到的文件；
  3. 模板渲染成空串而不是字符串 "None"（`test_模板渲染空串而不是None`）。
     第 3 条是这里最容易悄悄坏掉的一条：Jinja 把 None 渲染成 "None"，那是个
     真值，会绕过前端 `frontend/src/library/chat.ts` 里 book uuid 为空的降级分支，
     于是前端拿着 "None" 当 uuid 去发请求。

坏 uuid 的书其 AI 端点应当 404（明确的缺失）而不是被换上一个新 uuid（无声的
数据丢失）。那条路径由 `test_route_contracts.py` 的 ``MISSING_UUID`` 用例覆盖，
此处不重复。
"""

from __future__ import annotations

import logging

import pytest

from reader3_app.ai.books import AI_META_FILENAME, BookUuidResolver
from reader3_app.web import server

from conftest import BOOK_ID, BOOK_TITLE, World

#: 合法 JSON、合法对象、`book_uuid` 是字符串——只是它不是个 UUID。
#: 选这个形态而不是「截断的 JSON」，是因为它同时打到 `ensure_book_uuid` 里那条
#: 「拒绝覆盖」的分支；截断的 JSON 只能打到解析那条。
CORRUPT_META = '{"book_uuid": "this-is-not-a-uuid"}'


@pytest.fixture
def broken_world(world: World, monkeypatch: pytest.MonkeyPatch) -> World:
    """把种子书的 ai_meta.json 弄坏，并丢掉解析器里已经缓存好的 uuid。

    只写文件是不够的：``world`` 建起来时已经调用过一次
    ``book_uuid_for_folder``，答案还在 ``_folder_to_uuid`` 里。不换掉解析器的话
    这条测试会拿到缓存值并绿得毫无意义。
    """
    (world.book_dir / AI_META_FILENAME).write_text(CORRUPT_META, encoding="utf-8")
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(world.books_dir)))
    return world


def test_书库首页照常打开(broken_world: World) -> None:
    resp = broken_world.client.get("/")
    assert resp.status_code == 200
    # 不止是 200——那本书本身必须还在页面上。只断言状态码的话，一个把坏书整本
    # 跳过的实现也能绿，而那是另一种数据丢失。
    assert BOOK_TITLE in resp.text


def test_模板渲染空串而不是None(broken_world: World) -> None:
    resp = broken_world.client.get("/")
    assert 'data-book-uuid=""' in resp.text
    assert "None" not in resp.text.split("data-book-uuid=")[1][:16]


def test_读书页也照常打开且uuid为空(broken_world: World) -> None:
    resp = broken_world.client.get(f"/read/{BOOK_ID}/0")
    assert resp.status_code == 200
    assert 'bookUuid: ""' in resp.text


def test_坏书在日志里被点名(broken_world: World, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="reader3.web.server"):
        broken_world.client.get("/")
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    # 点名是哪本书，否则一个有一百本书的库里这条日志等于没有。
    assert any(BOOK_ID in m for m in messages), messages


def test_坏文件不被覆盖(broken_world: World) -> None:
    path = broken_world.book_dir / AI_META_FILENAME
    broken_world.client.get("/")
    broken_world.client.get(f"/read/{BOOK_ID}/0")
    assert path.read_text(encoding="utf-8") == CORRUPT_META
