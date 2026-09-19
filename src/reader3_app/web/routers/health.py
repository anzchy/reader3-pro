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

from .. import server as _server

router = APIRouter()


@router.get("/api/health")
async def api_health():
    """就绪探针。009 的 Playwright `webServer` 与 Phase 5 的 `reader3 launch` 都用它。

    **故意不碰磁盘**：不扫 books/、不读 settings、不加载任何 book.pkl。探针要在
    书库为空甚至目录不存在时也能答 200，否则 webServer 只会报「服务没起来」，
    而真实原因是探针自己在一个空目录上 500 了。
    """
    return {"status": "ok", "version": _server._package_version()}



