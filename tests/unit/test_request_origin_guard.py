"""WI-27 —— 请求边界的三道闸：Host 校验、改动型请求的 Origin 校验、可选的应用令牌。

绑 loopback 不等于安全。同机上任何进程（包括浏览器里任意一个标签页）都够得着
127.0.0.1:8123；更糟的是 **DNS rebinding**：攻击者的域名先解析到自己的 IP，页面加载
完再改解析到 127.0.0.1，受害者浏览器里那个页面于是能对本服务发同源请求，读走书库、
标注、以及 provider API key。

这一组测试钉住三件事，以及**两条反向断言**——反向断言在这里和正向断言一样承重，因为
「一律要求令牌」「无 Origin 也拒」都是能让正向断言全绿、同时把「打开就能读」的本地
体验和 curl 工具链一起弄坏的过度修复。

本文件的隔离约定（tests/unit/conftest.py 那两条 autouse 围栏之外还要自己做的）：
* ``server.BOOKS_DIR`` 是模块级常量，只能 monkeypatch 到 tmp_path；
* ``server.book_uuid_resolver`` 在 __init__ 里就捕获了旧的 BOOKS_DIR，必须一并换掉，
  否则任何触发 scan() 的路径都会走回开发者的真实 books/；
* ``TestClient`` **不进 with**：lifespan 只在 __enter__ 时跑，不进就不会有 startup 扫库；
* 所有 env 只经 ``monkeypatch.setenv`` / ``delenv``，绝不留给下一个测试。
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from reader3_app import search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import NOTES_FILENAME, save_annotations
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

#: 以 ``_data`` 结尾，否则 ``_validate_book_id`` 在碰磁盘之前就 404。
BOOK_ID = "guard_sample_data"

#: 三个哨兵串，全仓唯一。断「拒了」容易，断「没漏」要靠它们：H1 断的是
#: 被拒的响应体里**一个字节的书库内容都没有**，而不只是状态码对。
BOOK_TITLE = "GUARD-TITLE-3f21a9"
QUOTE = "GUARD-QUOTE-SENTINEL-9b7c11"
NOTE_ID = "11111111-2222-4333-8444-555555555555"

TOKEN = "GUARD-TOKEN-d4e5f6"


def _build_book() -> Book:
    """一章，正文里含 QUOTE。

    含 QUOTE 不是装饰：``_refresh_orphaned_annotations`` 在 GET 时会把正文里找不到的
    标注标成 orphaned 并**重写 notes.json**，那样 H3 的「资源仍在盘上」就会被测试自己
    的读操作搅浑。
    """
    return Book(
        metadata=BookMetadata(
            title=BOOK_TITLE,
            language="en",
            authors=["Guard Fixture"],
            description="fixture",
        ),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title="Chapter One",
                content=f"<p>{QUOTE}</p>",
                text=QUOTE,
                order=0,
            )
        ],
        toc=[TOCEntry(title="Chapter One", href="chap0.html", file_href="chap0.html", anchor="")],
        images={},
        source_file="guard.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


@dataclass
class Guarded:
    client: TestClient
    books_dir: Path

    @property
    def notes_path(self) -> Path:
        return self.books_dir / BOOK_ID / NOTES_FILENAME

    def notes_on_disk(self) -> dict:
        return json.loads(self.notes_path.read_text(encoding="utf-8"))


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Guarded]:
    monkeypatch.chdir(tmp_path)

    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    with open(books_dir / BOOK_ID / "book.pkl", "wb") as f:
        pickle.dump(_build_book(), f)

    save_annotations(
        str(books_dir),
        BOOK_ID,
        [
            Annotation(
                id=NOTE_ID,
                book_id=BOOK_ID,
                chapter_index=0,
                type="marker",
                color="yellow",
                quote=QUOTE,
            )
        ],
    )

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    monkeypatch.setattr(
        server,
        "book_uuid_resolver",
        BookUuidResolver(str(tmp_path / "no_such_books_dir")),
    )
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)

    _clear_caches()
    try:
        yield Guarded(client=TestClient(server.app, base_url="http://127.0.0.1"), books_dir=books_dir)
    finally:
        # tmp_path 的 book 留在 LRU 里，会让下一个测试从一个已经不存在的目录读出书。
        _clear_caches()


def _new_annotation_payload() -> dict:
    return {
        "type": "marker",
        "color": "green",
        "quote": QUOTE,
        "prefix": "",
        "suffix": "",
    }


# --------------------------------------------------------------------------
# H1 —— Host 校验（承重：去掉 TrustedHostMiddleware 这条就红）
# --------------------------------------------------------------------------

def test_H1_evil_host_被拒且响应体不含任何书库内容(guarded: Guarded) -> None:
    """rebinding 打过来的请求，带的是攻击者的域名——这就是拦住它的抓手。

    断两件事，缺一不可：状态码是 400（Starlette TrustedHostMiddleware 的语义），
    以及响应体里一个书库字段都没有。只断状态码的话，一个「先把数据算出来、再套个
    400 外壳」的实现能骗过测试。
    """
    resp = guarded.client.get(f"/api/notes/{BOOK_ID}", headers={"Host": "evil.example"})

    assert resp.status_code == 400

    body = resp.text
    assert QUOTE not in body
    assert BOOK_TITLE not in body
    assert BOOK_ID not in body
    assert "annotations_by_chapter" not in body


def test_H1b_同一条路由在放行的_host_下确实会吐出哨兵(guarded: Guarded) -> None:
    """给 H1 的否定断言兜底。

    没有这一条，H1 那四个 ``not in`` 在「这条路由本来就不返回这些字段」时也会绿，
    于是它证明的东西是零。
    """
    resp = guarded.client.get(f"/api/notes/{BOOK_ID}", headers={"Host": "127.0.0.1"})

    assert resp.status_code == 200
    body = resp.text
    assert QUOTE in body
    assert BOOK_ID in body
    assert "annotations_by_chapter" in body


# --------------------------------------------------------------------------
# H2 —— 本机三种写法照常放行（回归保护）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_H2_本机_host_照常_200(guarded: Guarded, host: str) -> None:
    resp = guarded.client.get("/api/health", headers={"Host": host})
    assert resp.status_code == 200, f"{host} 被自己的 host 闸拦下了"
    assert resp.json()["status"] == "ok"


@pytest.mark.parametrize("host", ["127.0.0.1:8123", "localhost:8123", "[::1]:8123"])
def test_H2b_带端口的本机_host_照常_200(guarded: Guarded, host: str) -> None:
    """浏览器真正发出去的 Host 头是带端口的，allowlist 里写的是不带端口的。"""
    resp = guarded.client.get("/api/health", headers={"Host": host})
    assert resp.status_code == 200, f"{host} 被自己的 host 闸拦下了"


def test_H2c_allowed_hosts_可被环境变量覆盖(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """env 必须在**请求时**读，不是 import 时读。

    在 import 时读的实现，这条会红——``server`` 早在 fixture 之前就被 import 了。
    """
    monkeypatch.setenv("READER3_ALLOWED_HOSTS", "reader.lan, 127.0.0.1")

    assert guarded.client.get("/api/health", headers={"Host": "reader.lan"}).status_code == 200
    assert guarded.client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


# --------------------------------------------------------------------------
# H3 —— 改动型请求的 Origin 校验
# --------------------------------------------------------------------------

def test_H3_跨站_origin_的_delete_被拒且标注仍在盘上(guarded: Guarded) -> None:
    """403，并且盘上那条标注一个字节都没动。

    只断状态码不够：「先删了、再返回 403」同样能绿，而标注不可再生。
    """
    resp = guarded.client.delete(
        f"/api/notes/{BOOK_ID}/0/{NOTE_ID}",
        headers={"Origin": "https://evil.example"},
    )

    assert resp.status_code == 403

    on_disk = guarded.notes_on_disk()
    assert [a["id"] for a in on_disk["annotations"]] == [NOTE_ID]
    assert on_disk["annotations"][0]["quote"] == QUOTE


def test_H3b_跨站_origin_的_post_被拒且没有新增标注(guarded: Guarded) -> None:
    resp = guarded.client.post(
        f"/api/notes/{BOOK_ID}/0",
        json=_new_annotation_payload(),
        headers={"Origin": "https://evil.example"},
    )

    assert resp.status_code == 403
    assert len(guarded.notes_on_disk()["annotations"]) == 1


def test_H3c_同源_origin_的_delete_照常放行(guarded: Guarded) -> None:
    """给 H3 兜底：闸门认的是「跨站」，不是「带了 Origin 头」。"""
    resp = guarded.client.delete(
        f"/api/notes/{BOOK_ID}/0/{NOTE_ID}",
        headers={"Host": "127.0.0.1:8123", "Origin": "http://127.0.0.1:8123"},
    )

    assert resp.status_code == 204
    assert guarded.notes_on_disk()["annotations"] == []


# --------------------------------------------------------------------------
# H4 —— 无 Origin 头的改动型请求放行（防过度修复）
# --------------------------------------------------------------------------

def test_H4_无_origin_头的_post_不被拒(guarded: Guarded) -> None:
    """curl 和原生客户端不发 Origin。这是刻意放行的，不是漏网。

    浏览器**一定**会给跨站的改动型请求带上 Origin，所以「无 Origin 即放行」不给
    rebinding 留门；而拒掉它会当场弄坏本地工具链。
    """
    resp = guarded.client.post(f"/api/notes/{BOOK_ID}/0", json=_new_annotation_payload())

    assert resp.status_code != 403
    assert resp.status_code == 201
    assert len(guarded.notes_on_disk()["annotations"]) == 2


def test_H4b_无_origin_头的_delete_不被拒(guarded: Guarded) -> None:
    resp = guarded.client.delete(f"/api/notes/{BOOK_ID}/0/{NOTE_ID}")

    assert resp.status_code != 403
    assert resp.status_code == 204


# --------------------------------------------------------------------------
# H5 —— 设了 READER3_TOKEN 之后
# --------------------------------------------------------------------------

def test_H5_设了token后无令牌请求被拒(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """401，不是 403——认证失败和跨站拒绝是两种失败，不该共用一个码。"""
    monkeypatch.setenv("READER3_TOKEN", TOKEN)

    denied = guarded.client.get(f"/api/notes/{BOOK_ID}")
    assert denied.status_code == 401
    assert QUOTE not in denied.text

    allowed = guarded.client.get(f"/api/notes/{BOOK_ID}", headers={"X-Reader3-Token": TOKEN})
    assert allowed.status_code == 200
    assert allowed.json()["book_id"] == BOOK_ID


def test_H5b_令牌也能走查询参数(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """``<img src>`` / epub.js 的 iframe 加不上自定义头，只能靠 ?token=。"""
    monkeypatch.setenv("READER3_TOKEN", TOKEN)

    assert guarded.client.get(f"/api/notes/{BOOK_ID}?token={TOKEN}").status_code == 200


def test_H5c_错误令牌被拒(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("READER3_TOKEN", TOKEN)

    resp = guarded.client.get(f"/api/notes/{BOOK_ID}", headers={"X-Reader3-Token": "wrong-token"})
    assert resp.status_code == 401
    assert QUOTE not in resp.text


def test_H5d_设了token后改动型路由也要令牌且没有副作用(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("READER3_TOKEN", TOKEN)

    resp = guarded.client.delete(f"/api/notes/{BOOK_ID}/0/{NOTE_ID}")
    assert resp.status_code == 401
    assert [a["id"] for a in guarded.notes_on_disk()["annotations"]] == [NOTE_ID]


def test_H5e_设了token后健康探针仍然可达(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """探针是 009 的 Playwright webServer 和 Phase 5 launch 判断「起没起来」的唯一抓手。

    它不吐任何书库内容，所以豁免它的代价是零；不豁免的代价是设了令牌之后启动探测全挂。
    """
    monkeypatch.setenv("READER3_TOKEN", TOKEN)

    resp = guarded.client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --------------------------------------------------------------------------
# H6 —— 没设 READER3_TOKEN 时（防过度修复；默认体验不许被这次改动动到）
# --------------------------------------------------------------------------

def test_H6_没设token时无令牌请求照常_200(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """默认行为必须和今天一模一样：打开就能读，不需要任何令牌。"""
    monkeypatch.delenv("READER3_TOKEN", raising=False)

    resp = guarded.client.get(f"/api/notes/{BOOK_ID}")
    assert resp.status_code == 200
    assert resp.json()["book_id"] == BOOK_ID


def test_H6b_没设token时改动型请求照常成功(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("READER3_TOKEN", raising=False)

    resp = guarded.client.post(f"/api/notes/{BOOK_ID}/0", json=_new_annotation_payload())
    assert resp.status_code == 201
    assert len(guarded.notes_on_disk()["annotations"]) == 2


def test_H6c_空的_READER3_TOKEN_等同于没设(guarded: Guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    """``READER3_TOKEN=`` 是「我不要令牌」，不是「令牌是空串，所以谁都进不来」。"""
    monkeypatch.setenv("READER3_TOKEN", "")

    assert guarded.client.get(f"/api/notes/{BOOK_ID}").status_code == 200
