"""`/api/health` —— 存活探针。

拆自 `web/server.py`（011 WI-4）。**它不属于计划写的六组里的任何一组**：
它既不是 library/reader/notes/search/ai，也不是 settings（它不读也不写任何设置）。
与其硬塞进一个说不通的组，不如让它自己是一个 12 行的模块。

这条选择有个副作用，必须写下来而不是让它悄悄生效：六组搬完之后
`web/server.py` 不再声明任何路由，于是**它掉出了 `scripts/check_router_size.py`
的量程**（闸量的是「`routers/` 下的每个文件」∪「`web/` 下声明路由的模块」）。
换句话说，行数门槛管得住 router，管不住 server.py 里剩下的共享 helper。
这不是闸的缺陷——计划 §8 的门槛本来就是按「声明路由的模块」写的——但它是一笔
真实的、这次搬家之后才出现的敞口，记在 011 §5「搬完之后」一节。
"""
from __future__ import annotations

from fastapi import APIRouter


router: APIRouter = APIRouter()


@router.get("/api/health")
async def api_health():
    """就绪探针。009 的 Playwright `webServer` 与 Phase 5 的 `reader3 launch` 都用它。

    **故意不碰磁盘**：不扫 books/、不读 settings、不加载任何 book.pkl。探针要在
    书库为空甚至目录不存在时也能答 200，否则 webServer 只会报「服务没起来」，
    而真实原因是探针自己在一个空目录上 500 了。
    """
    return {"status": "ok", "version": _server._package_version()}

# ---------------------------------------------------------------------------
# 017 WI-1（审计 #7）——**这一行必须留在文件末尾**，在 `router` 与所有路由都定义完之后。
#
# `server` 在它自己的文件末尾要取 `routers.<本模块>.router` 这个**属性**来 include。
# 如果本模块在顶部就导入 `server`，而本进程又是从本模块开始导入的，那么 `server` 会在
# 本模块只执行到第 1 行的时候跑完整个文件体，然后去取一个还不存在的 `router`：
#     AttributeError: partially initialized module ... has no attribute 'router'
# 把导入挪到末尾，`router` 就已经在模块命名空间里，`server` 取得到，环自己解开。
#
# 这不影响打桩接缝：`_server.X` 仍是**调用时**解析属性，`monkeypatch.setattr(server, …)`
# 照常生效。绑的依旧是模块对象，不是属性——规矩见 `routers/__init__.py` 的 docstring。
# ---------------------------------------------------------------------------
from .. import server as _server  # noqa: E402
