"""站内 URL 拼装（018 审计 20261007 #7，FX37-7）。

书目录名与图片文件名都是文件系统里的任意名字，可能含 ``#`` / ``?`` / ``%`` / 空格 / 非 ASCII。
直接塞进 f-string 得到的不是同一个资源：``/read/A#B_data/images/x.jpg`` 在浏览器里
``#`` 之后成了 fragment，请求打到 ``/read/A``。这里对每一段单独做百分号编码
（``safe=""``，``/`` 也编码），路由按段解码后拿回原名。

不是 router 模块：`/`、`/api/library`、阅读页三处共用这一个拼法，免得再分叉。
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote


def cover_url(book_id: str, image: Optional[str]) -> Optional[str]:
    """``/read/{book_id}/images/{image}``，两段各自百分号编码；没有图片 → ``None``。"""
    if not image:
        return None
    return f"/read/{quote(book_id, safe='')}/images/{quote(image, safe='')}"
