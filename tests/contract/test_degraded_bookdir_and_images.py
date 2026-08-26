"""受损书目录与图片路由的降级行为——都在 HTTP 边界上验，不是在文件系统上验。

两条 finding 合在一处，因为它们是同一个毛病的两面：**测试停在了 handler 前面**。

- tests/23：`test_remove_book_epub_keeps_the_marker_the_library_scan_looks_for`
  删掉 book.epub 之后只是重新 stat 了一次目录，从未调用 `library_view` 或
  `serve_epub`。它验证的是「文件系统还是文件系统」——把整个路由层换成
  `raise NotImplementedError`，那条测试照样绿。
- tests/15：图片路由只用良性文件名测过。真正能穿过路由到达 `serve_image` 的
  可疑输入只有一个（见下），而它当时会把 404 变成 500。

关于 tests/15 的威胁模型，一句话讲清为什么这里**没有**穿越用例：路由参数的
转换器是 `[^/]+`，uvicorn 又在匹配之前就 `unquote()` 了 raw_path，所以
`..%2F..%2Fconfig` 到达时已经是 `../../config`，含 `/`，匹配不上，404 发生在
路由层，handler 一次都不执行。写一条「穿越被挡住了」的用例只会得到一条**假绿**：
它断到的 404 来自路由，把 handler 里的守卫整个删掉它依然绿。所以这里只测真正
可达的那一个：`".."`。
"""

from __future__ import annotations


from conftest import BOOK_ID, World


# ---------------------------------------------------------------- tests/15

def _raw_get(app, path: str) -> int:
    """绕开 httpx，手搓 ASGI scope 直接驱动 app，返回状态码。

    **必须这么做**：httpx 按 RFC 3986 §5.2.4 在**发请求之前**就把 `..` 规范化掉，
    `/read/x/images/..` 会变成 `/read/x/`，于是打到的是阅读页而不是图片路由——
    第一版这条用例就是这样拿到 200 的。uvicorn 不做这一步规范化，所以走
    TestClient 测出来的是 httpx 的行为，不是这个应用的行为。

    `scope["path"]` 直接给解码后的字面量，正是 uvicorn 交给 app 的形状。
    """
    import asyncio

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"127.0.0.1")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8123),
    }
    try:
        asyncio.run(app(scope, receive, send))
    except Exception as exc:  # noqa: BLE001 - 未捕获异常就是这条用例要抓的 500
        return f"unhandled {type(exc).__name__}: {exc}"
    for m in messages:
        if m["type"] == "http.response.start":
            return m["status"]
    return "no response"


def test_点名一个目录当图片要404而不是500(world: World) -> None:
    """`".."` 不含 `/`，是唯一能匹配路由并到达 handler 的可疑输入。

    `basename("..")` 仍然是 `".."`，于是路径指向 images/ 的父目录。它**存在**，
    所以 `os.path.exists` 会放行，`FileResponse` 拿到一个目录，在 send 阶段炸开——
    一次「你要的文件不在」被报成「服务器坏了」。
    """
    (world.book_dir / "images").mkdir(parents=True, exist_ok=True)

    status = _raw_get(world.client.app, f"/read/{BOOK_ID}/images/..")

    assert status == 404, (
        f"点名一个目录得到 {status!r}；应当是 404——"
        "500 或未捕获异常会把「你要的文件不在」误报成服务端故障"
    )


def test_不存在的图片名照常404(world: World) -> None:
    """反向守卫：上面那条不能靠「把图片路由整个改成 404」而变绿。"""
    assert world.client.get(f"/read/{BOOK_ID}/images/nope.jpg").status_code == 404


def test_真实存在的图片仍然能取到(world: World) -> None:
    """最关键的反向守卫：`isfile` 不能顺手把正常图片也挡掉。

    没有这条，把 `os.path.isfile(...)` 写成 `False` 也不会有测试变红。
    """
    images = world.book_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    (images / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\nSENTINEL")

    resp = world.client.get(f"/read/{BOOK_ID}/images/cover.png")

    assert resp.status_code == 200, resp.text
    assert b"SENTINEL" in resp.content


# ---------------------------------------------------------------- tests/23

def test_书目录缺了epub时library页仍然渲染(world: World) -> None:
    """epub.js 的渲染源没了，但书还在库里——库页不能因此整页 500。"""
    epub = world.book_dir / "book.epub"
    assert epub.is_file(), "前置条件：这本书本来有 book.epub"
    epub.unlink()

    resp = world.client.get("/")

    assert resp.status_code == 200, (
        f"删掉一本书的 book.epub 之后整个书库页变成 {resp.status_code}；"
        "一本书坏掉不该让用户看不见其余的书"
    )


def test_书目录缺了epub时取epub得到404而不是500(world: World) -> None:
    """这条才真正走过 `serve_epub`——原来的测试从没调用过它。"""
    (world.book_dir / "book.epub").unlink()

    resp = world.client.get(f"/read/{BOOK_ID}/book.epub")

    assert resp.status_code == 404, (
        f"实得 {resp.status_code}；缺文件是可预期状态，应当是 404 而不是未捕获异常"
    )


def test_epub还在时取得到它(world: World) -> None:
    """反向守卫：上面那条不能靠「serve_epub 永远 404」而变绿。"""
    resp = world.client.get(f"/read/{BOOK_ID}/book.epub")
    assert resp.status_code == 200, resp.text
    assert resp.content[:2] == b"PK", "取回来的应当是个 zip（epub）"
