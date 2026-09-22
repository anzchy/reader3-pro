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

**绑模块、不绑属性，顺带解决了循环导入**：`server.py` 在文件末尾 include 这些 router，
router 在导入期只绑定 `server` 这个模块对象（那时它还没执行完，但对象已经在
`sys.modules` 里），真正取属性要等到请求进来。

非接缝的东西（`notes_service` 的函数、`models.annotations.Annotation`、各服务层模块）
照常直接 import —— 规矩只管 `OWNERSHIP` 里那 20 个名字和 `server` 自己的私有 helper。
"""
