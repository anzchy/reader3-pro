"""WI-5a —— notes 乐观并发的**后端半边**：`ETag` 出、`If-Match` 入、冲突返 409。

它修的不是文件级互相覆盖 —— 那件事 `notes_service._book_write_lock` 已经关掉了
（进程内 `threading.Lock` ＋ 跨进程 `fcntl.flock`，`add/delete/update` 三个写口都在锁里
做完 load→改→save）。任务书 §6 WI-5 写的「`os.replace` 只保证单次写入原子，不防两个并发
请求互相覆盖」这句话**今天已经不成立**，本文件不为它写一条断言。

真正还在丢的是**跨两次 HTTP 请求的陈旧写**：B 在 T0 读到 A0，A 在 T1 写成 A1，B 在 T2 把
基于 A0 算出来的正文提交上来 —— 服务端照单全收，A1 无声消失。锁看不见这件事，因为陈旧
性活在两次请求之间，不在文件内部。所以判据是乐观并发：版本号进出、不匹配返 409。

本文件的判据分两层，都落在 unit lane：

* **路由层**（`TestClient` 驱真 app）：没有 `If-Match` 时三条写路由逐字节保持今天的形状
  （ADR-0011 的护栏）；带陈旧 `If-Match` 时 409，**且盘上仍是较新的那一版**；409 的响应体
  带着服务端当前的正文与当前 ETag（WI-5b 的冲突对话框要同时摆出两版正文，本地那版客户端
  自己有，远端那版只能从 409 体里来）。
* **服务层**（真 `notes_service` ＋ `tmp_path` 真文件）：版本对内容敏感、对磁盘排版不敏感；
  以及本 WI 的核心判断 —— **比较必须发生在锁里**，两个握着同一个合法版本的写者并发进来，
  **恰好一个**成功。

### 为什么服务层的新函数是 `getattr` 取的，不是 import 进来的

红在先。实现还不存在时，`from reader3_app.notes_service import NotesVersionConflict` 会让
整个文件**收集失败**，而收集失败证明不了任何一条断言存在 —— 红证工具也会（正确地）把它
判成环境故障而不是红。所以新 API 一律按名字取，取不到就当成一次失败的尝试记进 outcome，
让断言在「期望一个 conflict，实得一个 AttributeError」上失败。这样红是关于**行为**的。

### 断言级别

    L2  单条可观测状态（一个响应字段、一个 header、盘上一条记录的 note_text）
    L3  并发跑完之后的整盘终态 ＋ 两个写者各自的结局
"""

from __future__ import annotations

import html
import json
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from reader3_app import notes_service, search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import NOTES_FILENAME
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

#: 以 ``_data`` 结尾，否则 ``_validate_book_id`` 在碰磁盘之前就 404。
BOOK_ID = "etag_sample_data"

CHAPTER = 0

#: 正文里必须出现的锚点：``_refresh_orphaned_annotations`` 在每次 GET 时会把正文里找不到
#: 的标注标成 orphaned **并重写 notes.json**，那会让「盘上是谁」这条判据被测试自己的读
#: 操作搅浑，也会让 ETag 在两次 GET 之间无故变化。
QUOTE = "ETAG-QUOTE-SENTINEL-7a3c05"

#: DEG-S5 那三版正文（e2e 用例里的 A0 / A1 / B）。三者两两不同，否则「谁盖了谁」不可判定。
#: A1 里的 ``&`` 是故意的：PUT 会 `html.escape`，所以盘上存的是 ``&amp;``，而 GET 与 409
#: 体都必须把它还原回 ``&`` —— 对话框要展示的是用户打的字，不是转义后的字节。
NOTE_A0 = "A 的初稿"
NOTE_A1 = "A 的修订版 & 补注"
NOTE_B = "B 基于初稿的修改"

#: 一个正确实现会让这个会合点**不可达**（第二个写者正卡在书级锁上），所以超时是从那个
#: 死等里出来的唯一出口，不是用挂钟造出来的竞态窗口。锁缺失时两个写者同时到达，超时不会
#: 被支付。
RENDEZVOUS_TIMEOUT_S = 2.0

JOIN_TIMEOUT_S = 30.0

#: 今天三条写路由的响应形状。ADR-0011 冻的就是这些；没有 `If-Match` 时必须一字不差。
CREATE_KEYS = {"id", "created_at", "message"}
CREATE_MESSAGE = "Annotation created successfully"
UPDATE_MESSAGE = "Annotation updated successfully"
CHAPTER_LIST_KEYS = {"book_id", "chapter_index", "count", "annotations"}
BOOK_LIST_KEYS = {"schema_version", "book_id", "total_count", "annotations_by_chapter"}


# --------------------------------------------------------------------------- 世界

def _build_book() -> Book:
    return Book(
        metadata=BookMetadata(
            title="ETag Fixture",
            language="en",
            authors=["WI-5a"],
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
        source_file="etag.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


@dataclass
class World:
    client: TestClient
    books_dir: Path

    @property
    def notes_path(self) -> Path:
        return self.books_dir / BOOK_ID / NOTES_FILENAME

    def records(self) -> List[Dict[str, Any]]:
        """盘上的标注，按**未来一次读取**会看到的样子读回来（不经任何缓存）。"""
        if not self.notes_path.exists():
            return []
        data = json.loads(self.notes_path.read_text(encoding="utf-8"))
        return list(data.get("annotations") or [])

    def text_on_disk(self, note_id: str) -> Optional[str]:
        for record in self.records():
            if record.get("id") == note_id:
                return record.get("note_text")
        return None


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.chdir(tmp_path)

    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    with open(books_dir / BOOK_ID / "book.pkl", "wb") as f:
        pickle.dump(_build_book(), f)

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    # resolver 在 __init__ 里就捕获了旧的 BOOKS_DIR，不一并换掉，任何触发 scan() 的路径
    # 都会走回开发者的真实 books/。
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(tmp_path / "no_such_books_dir")))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)

    _clear_caches()
    try:
        yield World(client=TestClient(server.app, base_url="http://127.0.0.1"), books_dir=books_dir)
    finally:
        # tmp_path 的 book 留在 LRU 里，会让下一个测试从一个已经不存在的目录读出书。
        _clear_caches()


# --------------------------------------------------------------------------- 小工具

def _create(world: World, note_text: str = NOTE_A0, headers: Optional[Dict[str, str]] = None):
    return world.client.post(
        f"/api/notes/{BOOK_ID}/{CHAPTER}",
        json={"type": "note", "color": "green", "quote": QUOTE, "note_text": note_text},
        headers=headers or {},
    )


def _seed_note(world: World, note_text: str = NOTE_A0) -> str:
    resp = _create(world, note_text)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _chapter_get(world: World):
    return world.client.get(f"/api/notes/{BOOK_ID}/{CHAPTER}")


def _etag(response) -> str:
    """响应上的 ETag，取不到就**在这里**失败并说清是哪条响应。

    取不到时返回 ``""`` 会让后续的 `If-Match` 变成「没带这个头」，于是一条本该红的
    冲突用例会以 200 通过 —— 恰好是本 WI 要消灭的那种静默。
    """
    value = response.headers.get("etag")
    assert value, f"响应没有 ETag：{response.request.method} {response.request.url} -> {response.status_code}"
    return value


def _update(world: World, note_id: str, note_text: str, if_match: Optional[str] = None):
    headers = {"If-Match": if_match} if if_match is not None else {}
    return world.client.put(
        f"/api/notes/{BOOK_ID}/{CHAPTER}/{note_id}",
        json={"note_text": note_text},
        headers=headers,
    )


def _delete(world: World, note_id: str, if_match: Optional[str] = None):
    headers = {"If-Match": if_match} if if_match is not None else {}
    return world.client.delete(f"/api/notes/{BOOK_ID}/{CHAPTER}/{note_id}", headers=headers)


def _update_and_version(
    books_dir: str,
    book_id: str,
    note_id: str,
    note_text: str,
    if_match: Optional[str],
) -> Tuple[Any, str]:
    """按名字调 WI-5a 的服务层原语（理由见模块 docstring 的「为什么是 getattr」）。"""
    fn = getattr(notes_service, "update_annotation_and_version", None)
    if fn is None:
        raise NotImplementedError("notes_service.update_annotation_and_version 不存在")
    return fn(books_dir, book_id, note_id, note_text, if_match=if_match)


def _classify(exc: BaseException) -> str:
    """把一次失败归类成 ``conflict`` 或一段可读的 ``error:…``。

    `NotesVersionConflict` 同样按名字取：类还不存在时每一次失败都归成 ``error:…``，
    于是断言在「期望一个 conflict」上失败 —— 这是一次关于行为的红，不是收集错误。
    """
    conflict_cls = getattr(notes_service, "NotesVersionConflict", None)
    if conflict_cls is not None and isinstance(exc, conflict_cls):
        return "conflict"
    return f"error:{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- 1. 没有 If-Match ⇒ 今天的形状

def test_create_without_if_match_keeps_todays_shape(world: World) -> None:
    """POST 不带 `If-Match` ⇒ 201 ＋ 今天那三个键，一个不多一个不少。

    ADR-0011 的护栏：`tests/contract` 整套一行不改还得全绿，靠的就是这条路径没动。
    """
    resp = _create(world)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == CREATE_KEYS, body
    assert body["message"] == CREATE_MESSAGE
    assert [r["note_text"] for r in world.records()] == [html.escape(NOTE_A0)]


def test_update_without_if_match_keeps_todays_shape(world: World) -> None:
    """PUT 不带 `If-Match` ⇒ 200 ＋ 逐字段相同的响应体（含今天的 `html.escape` 行为）。"""
    note_id = _seed_note(world)

    resp = _update(world, note_id, NOTE_A1)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "id": note_id,
        "note_text": html.escape(NOTE_A1),
        "message": UPDATE_MESSAGE,
    }
    assert world.text_on_disk(note_id) == html.escape(NOTE_A1)


def test_delete_without_if_match_keeps_todays_shape(world: World) -> None:
    """DELETE 不带 `If-Match` ⇒ 204 ＋ 空体，盘上那条真的没了。"""
    note_id = _seed_note(world)

    resp = _delete(world, note_id)

    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    assert world.records() == []


# --------------------------------------------------------------------------- 2. 正确的 If-Match ⇒ 写通过

def test_matching_if_match_is_accepted_and_the_response_hands_back_the_new_version(world: World) -> None:
    """带对版本的 PUT 成功，**而且新版本能从这次响应里直接拿到**。

    「能从响应里拿到」是活性判据：拿不到，客户端每写一次就得再 GET 一次才能继续写，
    而那次 GET 与下一次写之间又是一段新的陈旧窗口 —— 乐观并发会退化成一个更难看的循环。
    """
    note_id = _seed_note(world)
    before = _etag(_chapter_get(world))

    first = _update(world, note_id, NOTE_A1, if_match=before)
    assert first.status_code == 200, first.text
    after = _etag(first)
    assert after != before, "内容变了，版本却没动"

    # 响应里给回来的那个版本，下一次写直接可用；而上一版此刻已经陈旧。
    second = _update(world, note_id, NOTE_B, if_match=after)
    assert second.status_code == 200, second.text
    assert _update(world, note_id, "再来一次", if_match=before).status_code == 409


def test_matching_if_match_is_accepted_on_create_and_delete(world: World) -> None:
    """另两条写路由的「版本对得上」那一支：POST 201、DELETE 204，各自带回新版本。"""
    version = _etag(_chapter_get(world))

    created = _create(world, NOTE_A0, headers={"If-Match": version})
    assert created.status_code == 201, created.text
    note_id = str(created.json()["id"])
    after_create = _etag(created)
    assert after_create != version

    removed = _delete(world, note_id, if_match=after_create)
    assert removed.status_code == 204, removed.text
    assert _etag(removed) != after_create
    assert world.records() == []


@pytest.mark.parametrize(
    "shape",
    ["quoted", "unquoted", "weak"],
    ids=["quoted", "unquoted", "weak"],
)
def test_if_match_accepts_the_three_spellings_of_one_version(world: World, shape: str) -> None:
    """同一个版本的三种写法都认：`"v"`、裸 `v`、`W/"v"`。

    服务端自己发出去的是带引号的强 ETag，但客户端（以及中间件、代理、手搓 curl 的人）
    会把它抄成另外两种形状中的任意一种。把它们当成不同的版本，代价是一次**假冲突**：
    用户看到一个本不该出现的「二选一」对话框，然后学会无视它。
    """
    note_id = _seed_note(world)
    quoted = _etag(_chapter_get(world))
    bare = quoted.strip('"')
    spelling = {"quoted": quoted, "unquoted": bare, "weak": f'W/"{bare}"'}[shape]

    resp = _update(world, note_id, NOTE_A1, if_match=spelling)

    assert resp.status_code == 200, resp.text
    assert world.text_on_disk(note_id) == html.escape(NOTE_A1)


# --------------------------------------------------------------------------- 3. 陈旧的 If-Match ⇒ 409，且盘没动

def test_stale_if_match_is_refused_and_the_disk_still_holds_the_newer_text(world: World) -> None:
    """DEG-S5 的后端半边：B 拿着 A0 时代的版本写 ⇒ 409，**而盘上仍是 A1**。

    只断状态码是不够的：一个「返 409 然后照写不误」的实现能通过状态码断言，而那正是本闸
    要抓的那一类坏法 —— 用户看到冲突提示，数据却已经丢了。
    """
    note_id = _seed_note(world)
    b_version = _etag(_chapter_get(world))  # B 在 T0 读到的版本

    assert _update(world, note_id, NOTE_A1).status_code == 200  # A 在 T1 写成 A1

    conflict = _update(world, note_id, NOTE_B, if_match=b_version)  # B 在 T2 提交陈旧写

    assert conflict.status_code == 409, conflict.text
    assert world.text_on_disk(note_id) == html.escape(NOTE_A1), "409 之后盘上不是 A1：写被拒了却照样落了盘"
    assert len(world.records()) == 1


def test_conflict_body_carries_the_servers_current_text_and_a_usable_version(world: World) -> None:
    """409 的体里必须有**服务端当前那一版正文**，以及一个能直接拿去重试的版本。

    WI-5b 的对话框要同时摆出两版正文（本地 B 与远端 A1）。本地那版客户端自己有，远端那版
    只能从这个响应体里来 —— 没有它，WI-5b 造不出来。正文按 GET 的口径还原转义：用户看到的
    应该是他打的字，不是 ``&amp;``。
    """
    note_id = _seed_note(world)
    stale = _etag(_chapter_get(world))
    assert _update(world, note_id, NOTE_A1).status_code == 200

    conflict = _update(world, note_id, NOTE_B, if_match=stale)
    assert conflict.status_code == 409, conflict.text
    body = conflict.json()

    assert body["annotation"] is not None, f"409 体里没有远端那一版：{body}"
    assert body["annotation"]["id"] == note_id
    assert body["annotation"]["note_text"] == NOTE_A1, body["annotation"]

    # 体里给的版本能直接用来重试，一次就通 —— 冲突之后有出路，不是死胡同。
    retry = _update(world, note_id, NOTE_B, if_match=body["etag"])
    assert retry.status_code == 200, retry.text
    assert world.text_on_disk(note_id) == html.escape(NOTE_B)


def test_stale_if_match_on_delete_leaves_the_annotation_alone(world: World) -> None:
    """DELETE 也吃这一套：陈旧版本 ⇒ 409，那条标注还在盘上。

    删除是三条写路由里唯一不可逆的一条，所以「拒了就真的没删」这条判据比另外两条更硬。
    """
    note_id = _seed_note(world)
    stale = _etag(_chapter_get(world))
    assert _update(world, note_id, NOTE_A1).status_code == 200

    conflict = _delete(world, note_id, if_match=stale)

    assert conflict.status_code == 409, conflict.text
    assert [r["id"] for r in world.records()] == [note_id]
    assert world.text_on_disk(note_id) == html.escape(NOTE_A1)


def test_stale_if_match_on_create_refuses_and_writes_nothing(world: World) -> None:
    """POST 的 409：不写盘，且体里的 `annotation` 是 `null`。

    新建没有「服务端当前那一条」—— 还没有那条。所以这一支的 `annotation` 只能是 `null`，
    而 `etag` 仍然给：客户端据此重读、重试，不必猜。选择带上 `If-Match` 的客户端，等于
    声明「我的这次新建是基于我看到的那份列表」；服务端尊重它，而不是偷偷放行。
    """
    _seed_note(world)
    stale = _etag(_chapter_get(world))
    assert _create(world, "另一条").status_code == 201  # 别人先建了一条，版本前进

    conflict = _create(world, NOTE_B, headers={"If-Match": stale})

    assert conflict.status_code == 409, conflict.text
    body = conflict.json()
    assert body["annotation"] is None, body
    assert body["etag"]
    assert len(world.records()) == 2, "409 了却还是建了一条"
    assert NOTE_B not in [r["note_text"] for r in world.records()]


def test_conflict_on_an_already_deleted_note_reports_no_remote_version(world: World) -> None:
    """对方已经把那条删了 ⇒ 仍是 409（不是 404），且 `annotation` 为 `null`。

    两件事都要说清：
    * **409 压过 404**。对一个握着陈旧版本的客户端说「找不到」，会让它以为自己删重了、
      或者 id 写错了，而真相是「这里发生过你没看到的事」。前者让人重试，后者让人重读。
    * 这一支没有远端正文可给，所以 `annotation` 是 `null` —— 对话框该据此说「这条已被删除」，
      而不是摆出一版并不存在的文本。
    """
    note_id = _seed_note(world)
    stale = _etag(_chapter_get(world))
    assert _delete(world, note_id).status_code == 204

    conflict = _update(world, note_id, NOTE_B, if_match=stale)

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["annotation"] is None, conflict.json()
    assert world.records() == []


def test_conflict_reports_the_named_note_not_the_first_one(world: World) -> None:
    """书里有多条标注时，409 体里那一条必须是**请求点名的那一条**。

    取第一条（或任意一条）在只有一条标注的用例里看不出来，而对话框会据此摆出一段属于
    别的笔记的正文 —— 用户按着那段文字做二选一，丢掉的是自己这条。
    """
    other_id = _seed_note(world, "另一条的正文")
    target_id = _seed_note(world, NOTE_A0)
    assert other_id != target_id
    stale = _etag(_chapter_get(world))
    assert _update(world, target_id, NOTE_A1).status_code == 200

    conflict = _update(world, target_id, NOTE_B, if_match=stale)

    assert conflict.status_code == 409, conflict.text
    body = conflict.json()
    assert body["annotation"]["id"] == target_id, body["annotation"]
    assert body["annotation"]["note_text"] == NOTE_A1, body["annotation"]


# --------------------------------------------------------------------------- 4. 版本的语义

def test_reading_routes_carry_the_version_without_changing_their_bodies(world: World) -> None:
    """两条读路由都带 ETag，而**响应体一个字段都没动**（ADR-0011）。

    `GET /api/notes/{book_id}`（书级汇总）也带，且与章级那条是同一个值 —— 版本的粒度是
    「一本书的全部标注」，两条读路由读的是同一份状态。笔记面板只走书级那条，不给它 ETag
    就等于逼它为了拿一个版本号去多读一次章级路由。
    """
    note_id = _seed_note(world)

    chapter = _chapter_get(world)
    book = world.client.get(f"/api/notes/{BOOK_ID}")

    assert chapter.status_code == 200 and book.status_code == 200
    assert set(chapter.json()) == CHAPTER_LIST_KEYS
    assert set(book.json()) == BOOK_LIST_KEYS
    assert set(chapter.json()["annotations"][0]) == set(Annotation(book_id=BOOK_ID, quote=QUOTE).to_dict())
    assert chapter.json()["annotations"][0]["id"] == note_id
    assert _etag(chapter) == _etag(book)


def test_the_version_moves_when_a_notes_text_changes(world: World) -> None:
    """正文变了，版本必须跟着变 —— 否则「陈旧」永远判不出来。"""
    note_id = _seed_note(world)
    before = _etag(_chapter_get(world))

    assert _update(world, note_id, NOTE_A1).status_code == 200

    assert _etag(_chapter_get(world)) != before


def test_rewriting_identical_content_keeps_the_version_stable(world: World) -> None:
    """把同样的正文再写一遍，版本**不动**。

    **这是一个被选中的语义，不是一个副作用。** 版本由内容派生（内容的规范 JSON 的哈希），
    不是写入次数的计数器。两个理由：

    1. 版本回答的是「你手上是哪一份内容」，不是「这份内容被写过几次」。一次把 X 又写成 X
       的重试（网络超时后的重发就是这个形状）不该把所有其他客户端的版本作废 —— 那是纯粹的
       假冲突，而假冲突多了，真冲突就没人看了。
    2. 计数器要存盘，而本 WI 的硬约束是 `notes.json` 一个字节都不加（`NOTES_SCHEMA_VERSION`
       仍是 1，schema 归 012 管）。

    代价也说清楚：一次空写在版本上**不可见**。我们接受它 —— 空写没有改变任何人可能丢掉的
    东西。
    """
    note_id = _seed_note(world)
    assert _update(world, note_id, NOTE_A1).status_code == 200
    settled = _etag(_chapter_get(world))

    again = _update(world, note_id, NOTE_A1, if_match=settled)

    assert again.status_code == 200, again.text
    assert _etag(again) == settled
    assert _etag(_chapter_get(world)) == settled


def test_the_version_ignores_how_the_file_is_formatted_on_disk(world: World) -> None:
    """版本哈希的是**逻辑内容**，不是文件字节。

    012 迟早会重排 `notes.json`（缩进、键序）。如果版本跟着字节走，那次重排会让每一个在线
    客户端的 ETag 同时作废，而内容一条都没变 —— 一整轮凭空的冲突对话框。
    """
    _seed_note(world)
    before = _etag(_chapter_get(world))

    raw = json.loads(world.notes_path.read_text(encoding="utf-8"))
    # 同样的内容，另一种排版：不缩进、键序颠倒。
    reshuffled = {
        "annotations": [dict(reversed(list(item.items()))) for item in raw["annotations"]],
        "book_id": raw["book_id"],
        "schema_version": raw["schema_version"],
    }
    world.notes_path.write_text(json.dumps(reshuffled, ensure_ascii=False), encoding="utf-8")

    assert _etag(_chapter_get(world)) == before


# --------------------------------------------------------------------------- 5. 比较必须在锁里

def _stage_two_writers(
    monkeypatch: pytest.MonkeyPatch,
    launch,
) -> List[Tuple[str, Any]]:
    """把两个写者并排放进 load→save 之间的窗口，回收各自的结局。

    窗口靠在 `save_annotations` 外面包一层、停在 `Barrier(2)` 上撑开 —— 不睡挂钟，也**不
    改产品代码**（包在测试自己这一侧的模块命名空间上）。

    `barrier.wait` 带超时，理由与 WI-23 同：比较真的在锁里时，第二个写者正卡在书级锁上，
    会合点**不可达**，超时是从那个死等里出来的唯一出口。比较若在锁外，两个写者会一起到达，
    超时一分钱都不付。
    """
    barrier = threading.Barrier(2)
    real_save = notes_service.save_annotations

    def save_at_barrier(books_dir, book_id, annotations):
        try:
            barrier.wait(RENDEZVOUS_TIMEOUT_S)
        except threading.BrokenBarrierError:
            pass
        return real_save(books_dir, book_id, annotations)

    monkeypatch.setattr(notes_service, "save_annotations", save_at_barrier)

    outcomes: List[Tuple[str, Any]] = [("not-run", None), ("not-run", None)]

    def run(index: int) -> None:
        try:
            outcomes[index] = ("ok", launch(index))
        except BaseException as exc:  # noqa: BLE001 - 测试要把**任何**失败归类，而不是只认预期的那一种
            outcomes[index] = (_classify(exc), exc)

    threads = [threading.Thread(target=run, args=(i,), name=f"writer-{i}") for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
        assert not t.is_alive(), f"{t.name} 没有在 {JOIN_TIMEOUT_S}s 内结束：写者卡住了"

    barrier.abort()
    return outcomes


def test_two_writers_holding_the_same_version_leave_exactly_one_winner(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**本 WI 的核心判断**：两个写者握着同一个（当时合法的）版本并发进来，恰好一个成功。

    这条只有在比较与随后的写**同处一把锁**时才会绿 —— 也就是真的 compare-and-swap。比较
    若发生在锁外（比如在路由层先读一次文件再比），两个写者会各自读到同一个版本、各自通过
    检查、然后依次落盘：两个成功，后写者的内容盖掉前写者的，409 一次也不会发生。

    一次顺序调用两遍的测试在那种坏实现下同样是绿的，所以它证明不了任何事情。这里是并发。
    """
    note_id = _seed_note(world)
    shared_version = _etag(_chapter_get(world))
    books_dir = str(world.books_dir)
    texts = [NOTE_A1, NOTE_B]

    outcomes = _stage_two_writers(
        monkeypatch,
        lambda i: _update_and_version(books_dir, BOOK_ID, note_id, texts[i], shared_version),
    )

    kinds = sorted(kind for kind, _ in outcomes)
    assert kinds == ["conflict", "ok"], f"期望一胜一冲突，实得 {outcomes}"

    winner_index = next(i for i, (kind, _) in enumerate(outcomes) if kind == "ok")
    assert world.text_on_disk(note_id) == texts[winner_index], (
        f"盘上不是胜者写的那一版：{world.records()}"
    )
    assert len(world.records()) == 1


def test_a_check_outside_the_lock_would_let_both_writers_through(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向对照：把比较挪到锁外，同一场并发下**两个都成功** —— 后写者静默盖掉前写者。

    这条不是在为坏实现写规格，它是在给上一条用例称重。上一条断的是「恰好一个成功」；如果
    这套并发编排本身抓不住「两个都成功」，那条断言就是一句空话。这里用锁外预检把坏法真的
    演一遍：它照样绿不了上一条，而这里的两次成功说明编排有牙。

    顺带它也把任务书 §6 那句话证伪了：书级锁一直都在，两次写都拿到了锁、都成功了 ——
    丢的那一版不是被并发写坏的文件，是一次基于陈旧读的合法写。
    """
    note_id = _seed_note(world)
    books_dir = str(world.books_dir)
    texts = [NOTE_A1, NOTE_B]
    #: 锁外那次检查比的是什么不重要（这里是整份标注的规范化文本），重要的是它发生在锁**外**。
    snapshot = json.dumps(world.records(), sort_keys=True, ensure_ascii=False)

    def precheck_outside_the_lock(index: int):
        current = json.dumps(world.records(), sort_keys=True, ensure_ascii=False)
        assert current == snapshot, "锁外预检自己就没通过，这一轮编排不成立"
        return notes_service.update_annotation(books_dir, BOOK_ID, note_id, texts[index])

    outcomes = _stage_two_writers(monkeypatch, precheck_outside_the_lock)

    assert [kind for kind, _ in outcomes] == ["ok", "ok"], (
        f"锁外预检竟然拦住了一个写者：{outcomes}。"
        "那说明这套并发编排根本没让两个写者落在同一个窗口里，"
        "上一条『恰好一个成功』也就不再是证据。"
    )
    assert len(world.records()) == 1
