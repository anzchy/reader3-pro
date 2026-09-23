"""017 WI-4（审计 #1）——**读路由也是写者，它必须和写者排同一个队**。

`GET /api/notes/{book_id}` 与 `GET /api/notes/{book_id}/{chapter_index}` 看上去是读，
实际上会写盘：`_refresh_orphaned_annotations` 发现某条标注在正文里找不到了，就把它标成
`orphaned=True` 并**重写整份 notes.json**。而这次写是 load → 改 → save 的老三段，却
**没有握 `notes_service._book_write_lock`**——三个真正的写口（add / delete / update）
全都握着。

于是 011 WI-5a 刚建起来的乐观并发有一个从后门绕过去的缺口：

    GET  load → [ann1 活, ann2 "旧"]          （不在锁里）
    PUT  load → 改 ann2 → save → 200 OK       （在锁里，版本也对得上，客户端被告知成功）
    GET  save → [ann1 orphaned, ann2 "旧"]    （把自己 T0 的快照拍下去）

PUT 提交的那一版**无声消失**，而客户端手里拿着一个 200。锁看不见这件事，因为 GET
压根没进过队。审计 #1 用内存里的执行复现过这次丢失，这里把它钉成可重跑的断言。

### 交错是怎么做到确定的

在「refresh 算完、save 还没落盘」那一刻插一个闸：写者线程 B 在此放行，GET 侧等 B
`B_SETTLE_S` 秒。两个世界的行为**不对称**，这正是判据：

* 没有锁：B 一路畅通，毫秒级跑完 → GET 拿着陈旧快照盖下去 → 红。
* 有锁：B 堵在 `_book_write_lock` 上，等不到 → GET 存盘、放锁 → B 这才醒过来，
  基于**最新**状态写 → 绿。

闸挂在 `notes_service.save_annotations` 上——修复之后，读路由的存盘正是从这里走的
（`refresh_annotations_and_version` 在锁里按模块全局取它）。`fired == 1` 这条断言是
**守卫的守卫**：谁把存盘挪回路由自己的导入绑定（也就是把锁绕开的那个改法），闸就插不
进去，测试会红着说「我没插进去」，而不是悄悄变绿。

断言级别：
    L2  单个可观测值（盘上某条记录的 note_text、ETag header）
    L3  一次交错跑完之后的整盘终态 ＋ 两个参与者各自的结局
"""

from __future__ import annotations

import json
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient

from reader3_app import notes_service, search_service
from reader3_app.ai.books import BookUuidResolver
from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import NOTES_FILENAME, NOTES_SCHEMA_VERSION
from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry
from reader3_app.web import server

BOOK_ID = "get_refresh_lock_data"
CHAPTER = 0

#: 正文里**有**这句——带它的标注活着，写者 B 编辑的就是这一条。
LIVE_QUOTE = "LIVE-QUOTE-SENTINEL-0f21"
#: 正文里**没有**这句——GET 的 refresh 会把它标成 orphaned，从而触发那次存盘。
#: 没有这条，GET 就不写盘，也就没有本文件要测的那次覆盖。
GONE_QUOTE = "VANISHED-QUOTE-SENTINEL-9c4e"

NOTE_OLD = "写者 B 进场之前盘上的正文"
NOTE_NEW = "写者 B 提交成功的正文"

#: 放行写者 B 之后，GET 侧等它跑完的上限。有锁的世界里 B 一定等不到——这个超时是
#: 「修好了」这一侧的**固定成本**，不是 flaky：它不判 B 的速度，只判 B 有没有被挡住。
B_SETTLE_S = 0.5


def _build_book() -> Book:
    return Book(
        metadata=BookMetadata(title="Lock Fixture", language="en", authors=["017 WI-4"], description="fixture"),
        spine=[
            ChapterContent(
                id="item_0",
                href="chap0.html",
                title="Chapter One",
                content=f"<p>{LIVE_QUOTE}</p>",
                text=LIVE_QUOTE,
                order=0,
            )
        ],
        toc=[TOCEntry(title="Chapter One", href="chap0.html", file_href="chap0.html", anchor="")],
        images={},
        source_file="lock.epub",
        processed_at="2026-01-01T00:00:00+00:00",
    )


def _clear_caches() -> None:
    server.load_book_cached.cache_clear()
    search_service.load_book_cached.cache_clear()
    server._stats_cache.clear()


@dataclass
class World:
    client: TestClient
    books_dir: Path
    live_id: str

    @property
    def notes_path(self) -> Path:
        return self.books_dir / BOOK_ID / NOTES_FILENAME

    def records(self) -> List[Dict[str, Any]]:
        if not self.notes_path.exists():
            return []
        return list(json.loads(self.notes_path.read_text(encoding="utf-8")).get("annotations") or [])

    def text_on_disk(self, note_id: str) -> Optional[str]:
        for record in self.records():
            if record.get("id") == note_id:
                return record.get("note_text")
        return None

    def orphaned_on_disk(self, quote: str) -> Optional[bool]:
        for record in self.records():
            if record.get("quote") == quote:
                return bool(record.get("orphaned"))
        return None


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.chdir(tmp_path)
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    with open(books_dir / BOOK_ID / "book.pkl", "wb") as f:
        pickle.dump(_build_book(), f)

    live = Annotation(book_id=BOOK_ID, chapter_index=CHAPTER, type="note", quote=LIVE_QUOTE, note_text=NOTE_OLD, position=0)
    gone = Annotation(book_id=BOOK_ID, chapter_index=CHAPTER, type="marker", quote=GONE_QUOTE, position=1)
    notes_service.save_annotations(str(books_dir), BOOK_ID, [live, gone])

    monkeypatch.setattr(server, "BOOKS_DIR", str(books_dir))
    monkeypatch.setattr(server, "book_uuid_resolver", BookUuidResolver(str(tmp_path / "no_such_books_dir")))
    monkeypatch.delenv("READER3_TOKEN", raising=False)
    monkeypatch.delenv("READER3_ALLOWED_HOSTS", raising=False)

    _clear_caches()
    try:
        yield World(client=TestClient(server.app, base_url="http://127.0.0.1"), books_dir=books_dir, live_id=live.id)
    finally:
        _clear_caches()


class Interleave:
    """在 GET 的 save 之前放行写者 B，并记录闸到底有没有插进去。"""

    def __init__(self, writer: Callable[[], None]) -> None:
        self._writer = writer
        self._thread = threading.Thread(target=self._run, name="writer-B", daemon=True)
        self._go = threading.Event()
        self.b_done = threading.Event()
        self.fired = 0

    def _run(self) -> None:
        self._go.wait(timeout=10.0)
        try:
            self._writer()
        finally:
            self.b_done.set()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._thread.start()
        # 打桩目标必须写成字面量：`test_server_patch_seam_registry_complete` 扫的是 AST，
        # 循环变量里的名字它看不见，会（正确地）判成「这道锁从此不再完整」。
        monkeypatch.setattr(notes_service, "save_annotations", self._wrap(notes_service.save_annotations))

    def _wrap(self, real: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # B 自己的存盘不许再触发闸，否则它会等自己。
            if threading.current_thread() is self._thread or self.fired:
                return real(*args, **kwargs)
            self.fired += 1
            self._go.set()
            self.b_done.wait(timeout=B_SETTLE_S)
            return real(*args, **kwargs)

        return wrapper

    def join(self) -> None:
        self._go.set()
        self._thread.join(timeout=10.0)
        assert not self._thread.is_alive(), "写者 B 没能在 10 秒内跑完——锁没被放开"


@dataclass
class WriterOutcome:
    committed: bool = False
    conflict: bool = False
    error: Optional[BaseException] = None


def _make_writer(world: World, outcome: WriterOutcome, if_match: Optional[str]) -> Callable[[], None]:
    def write() -> None:
        try:
            notes_service.update_annotation_and_version(
                str(world.books_dir), BOOK_ID, world.live_id, NOTE_NEW, if_match=if_match
            )
            outcome.committed = True
        except notes_service.NotesVersionConflict:
            outcome.conflict = True
        except BaseException as e:  # noqa: BLE001 - 线程里的任何失败都得带回主线程判，不能只留在 stderr
            outcome.error = e

    return write


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", f"/{CHAPTER}"])
def test_L1_无条件写提交成功之后不许被GET的陈旧快照盖掉(
    world: World, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    outcome = WriterOutcome()
    iv = Interleave(_make_writer(world, outcome, if_match=None))
    iv.install(monkeypatch)

    resp = world.client.get(f"/api/notes/{BOOK_ID}{path}")
    iv.join()

    assert resp.status_code == 200
    assert iv.fired == 1, (
        f"闸一次都没插进去（fired={iv.fired}）——存盘的接缝挪了位置，"
        "这条用例证明不了任何交错。"
    )
    assert outcome.error is None, f"写者 B 炸了：{outcome.error!r}"
    assert outcome.committed, "写者 B 没能提交，本用例的前提不成立"
    assert world.text_on_disk(world.live_id) == NOTE_NEW, (
        "写者 B 被告知成功，盘上却还是旧正文——GET 的 refresh 把它 T0 的快照盖了上去。"
    )


@pytest.mark.parametrize("path", ["", f"/{CHAPTER}"])
def test_L2_带合法If_Match的写要么被告知冲突要么真的落在盘上(
    world: World, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    etag = notes_service.annotations_version(
        notes_service.load_annotations(str(world.books_dir), BOOK_ID)
    )

    outcome = WriterOutcome()
    iv = Interleave(_make_writer(world, outcome, if_match=etag))
    iv.install(monkeypatch)

    world.client.get(f"/api/notes/{BOOK_ID}{path}")
    iv.join()

    assert iv.fired == 1
    assert outcome.error is None, f"写者 B 炸了：{outcome.error!r}"
    if outcome.committed:
        assert world.text_on_disk(world.live_id) == NOTE_NEW, (
            "409 没发、200 发了，然后那一版正文不在盘上——这是最坏的一种：客户端没有任何理由重试。"
        )
    else:
        assert outcome.conflict, "既没提交也没冲突，写者 B 的结局不可归因"


@pytest.mark.parametrize("path", ["", f"/{CHAPTER}"])
def test_L3_没有交错时GET照旧把失配的标注标成orphaned并存盘(world: World, path: str) -> None:
    """护栏：加锁不许把 refresh 本身弄没了。"""
    resp = world.client.get(f"/api/notes/{BOOK_ID}{path}")

    assert resp.status_code == 200
    assert world.orphaned_on_disk(GONE_QUOTE) is True, "正文里找不到的标注没有被标成 orphaned"
    assert world.orphaned_on_disk(LIVE_QUOTE) is False, "正文里还在的标注被误标成了 orphaned"
    assert resp.headers.get("ETag"), "ETag header 没了"
    assert resp.headers["ETag"].strip('"') == notes_service.annotations_version(
        notes_service.load_annotations(str(world.books_dir), BOOK_ID)
    ), "返回的 ETag 和它自己刚写下去的那份盘不一致"


def test_L4_书级路由的响应体形状一个字段都没动(world: World) -> None:
    body = world.client.get(f"/api/notes/{BOOK_ID}").json()
    assert set(body.keys()) == {"schema_version", "book_id", "total_count", "annotations_by_chapter"}
    assert body["schema_version"] == NOTES_SCHEMA_VERSION
    assert body["total_count"] == 1, "orphaned 的那条不该出现在读结果里"
