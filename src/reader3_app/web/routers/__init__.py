"""按关切拆开的 FastAPI router。

**这个包里的每个模块怎么拿到 `server` 上的东西，是有规矩的，不是风格偏好。**

测试套里有 70 处 `monkeypatch.setattr(server, …)`，横跨 12 个测试文件、20 个属性名
（清单见 `tests/unit/test_server_patch_seam_ownership.py` 的 `OWNERSHIP`）。其中
`server._call_provider` 是本进程通往 LLM 的**唯一出口** —— 一次静默失效，等于一套以
「零真实 egress」为存在理由的测试拿着明文 API key 去打真实 provider。

拆 router 会把这些名字搬到别的模块，于是有两种写法，长得几乎一样，后果天差地别：

```python
from ..server import _call_provider      # ← 禁止
resp = _call_provider(...)               #   导入期绑定。monkeypatch 改的是 server 的
                                         #   属性，这里持有的是自己那份 —— 桩打在 A，
                                         #   代码走 B，测试继续绿，拦截的东西是零。

from .. import server as _server         # ← 这个
resp = _server._call_provider(...)       #   调用时才解析属性，monkeypatch 照常生效。
```

**不是靠自觉。** `tests/unit/test_server_patch_seam_ownership.py` 的 B-i 律
（`test_a12_b_i_namespace_law_holds_on_the_real_tree`）会把第一种写法当场判红：
2026-09-19 用它自己的扫描器实测过两种写法 ——

| 写法 | B-ii 模块级解析 | Check C 导入期抓取 |
|---|---|---|
| `from ..server import _call_provider` | `{'_call_provider'}` → 红 | `{}` |
| `_server._call_provider(...)` | `{}` | `{}` |

**绑模块、不绑属性**：router 在导入期只绑定 `server` 这个模块对象（那时它可能还没执行完，
但对象已经在 `sys.modules` 里），真正取属性要等到请求进来。

**这条规矩解决的是 router 这一侧，不解决 `server` 那一侧——本 docstring 曾经声称
「顺带解决了循环导入」，那句话是错的**（017 WI-1，审计 #7 判红）。`server.py` 在它自己的
文件末尾要取 `routers.X.router` 这个**属性**，于是谁先被导入就决定了成败：

| 进程里第一个导入的 | 结果 |
|---|---|
| `server`（console 脚本、绝大多数测试） | 正常 |
| 任意一个 router（`python -c`、单独跑某个测试文件、排查用 REPL） | 曾经必炸 |

炸法是 `AttributeError: partially initialized module ... has no attribute 'router'`。
**现在的修法**：每个 router 把 `from .. import server as _server` 放在**文件末尾**，
在 `router` 与所有路由都定义完之后。这样无论谁先导入，`server` 去取 `.router` 时它都已经存在。
新加 router 时照抄这个位置；`tests/unit/test_router_import_independence.py` 会逐个模块
起子进程验，并且有一条守卫盯着「清单与 `server.py` 的 include 列表一致」。

非接缝的东西（`notes_service` 的函数、`models.annotations.Annotation`、各服务层模块）
照常直接 import —— 规矩只管 `OWNERSHIP` 里那 20 个名字和 `server` 自己的私有 helper。
"""
