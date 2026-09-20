from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    finish_reason: str
    token_count: Optional[int] = None


class ProviderHTTPError(RuntimeError):
    """provider 回了 4xx/5xx。``status`` 是 HTTP 状态码。

    WI-6：在这之前，五家 provider 把所有 HTTP 错误压成裸 ``RuntimeError(msg)``，状态码
    只在「错误体里没有 message 时」才以字符串形式出现。于是
    ``server._call_provider`` 那道唯一的出口**分不出 429 和 401**——而这两件事要做的
    完全相反：一个该退避重试，一个重试三次只是让用户多等几秒才看到同一条「key 不对」。
    靠解析错误文本去分是靠不住的，那段文本来自服务端，随时会变。

    **继承 ``RuntimeError`` 不是随手写的**：``routers/search.py`` 那类
    ``except RuntimeError`` 分支、以及既有用例里断言 ``RuntimeError`` 的地方，都必须
    逐字保持原状。

    **``str()`` 必须与从前的 ``str(RuntimeError(msg))`` 逐字节相同**：这个串会经
    ``{"type": "error", "message": str(e)}`` 进 SSE 流、经
    ``{"success": false, "message": str(e)}`` 进连通性自测的响应体。ADR-0011 冻结之下
    那属于响应内容，不得变。所以这里只往 ``args`` 里放 message 一项，``status`` 走
    关键字参数存成属性——多塞一个位置参数就会让 ``str()`` 变成 ``("msg", 429)``。
    ``tests/unit/test_provider_retry.py`` 的 R11/R13 直接断言这件事。
    """

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = int(status)

