"""WI-1（011 §1）——打桩接缝的**归属登记表**与解析点断言。

这个模块守的是一件事：`tests/unit/**` 与 `tests/contract/**` 里那 20 个名字、76 处
`monkeypatch.setattr(server, "<name>", …)`，**patch 上去之后真的能被拦到**。
拦不到的形状只有一种：某个模块不是每次从 `server` 的命名空间里取这个名字，而是在
**导入期**就把它抓进了自己的 globals（或者抓成了另一个名字）。这个模块把三道检查
写成纯函数 + 三张表，跑在真树上，也跑在合成输入上。

三道检查，分工不同，**强度差三个数量级**：

* **Check A**（`identity_violation`）——`server.<name> is <owner>.<attr>`。
  ⚠️ **它是今天这棵树上的一句同义反复，而且对主要威胁是瞎的。**20 条里 19 条
  owner 就是 `reader3_app.web.server` 自己，`a is a` 不可能红。更要命的是：这个
  work item 存在的理由——router 拆分——恰恰是**保持同一性**的。`server.py` 一旦写上
  `from .routers.ai import _call_provider`，`server._call_provider is
  routers.ai._call_provider` 就是 True，Check A 全程绿灯。它只抓得住**重复定义**那一种
  变体（server 上留了一份旧副本）。留着它是因为它是一个便宜的棘轮，WI-4 必须来改它，
  **不是**因为它是这道守卫。A5 用红绿事实把这个瞎点钉死，别把它读成覆盖。

* **Check B**（`module_global_loads` / `scan_global_resolvers`）——AST 扫 `src/`，
  按名字算出「哪些模块从自己的 globals 里解析它」。两个 oracle：
  - **B-i `web_namespace_offenders`——这是 WI-1 的判据。**命名空间律：
    `reader3_app.web.` 下除 `reader3_app.web.server` 以外的任何模块都不许从自己的
    globals 里取名单上的名字。谓词里 `m == "reader3_app.web"` 那一支是**承重的**——
    前缀带着一个点，包自身落在律外，而 `web/__init__.py` 今天正是 `__all__ = []`，
    一个就在被守命名空间里的空车位。这条律**没有白名单可加**，要silence 它只能删掉
    一条有名字的语义规则，那是一个看得见、吵得起来的 diff。
  - **B-ii `GLOBAL_RESOLVERS`——特征化棘轮，不是判据。**它有一行就能silence 的解法
    （往 frozenset 里加一个模块名）。留着它，是因为它是唯一能注意到
    `reader3_app.web.` **之外**某个 resolver 消失掉的检查；B-i 的作用域决定了它对此
    结构性失明。两份工，别把棘轮读成律。
  注意 `OWNERSHIP` 那种 `resolvers ⊆ {owner}` 的写法在当前树上就是**红**的：
  `book_store.py` 解析它自己的 `load_book_cached`（147/176）、`ai/config.py` 解析它
  自己的 `load_ai_settings`（194/229/241）、`ai/rag.py` 解析 `BookVectorIndex`。
  定义者解析自己的定义是正常的。而且 `load_book_cached` 这个名字**今天有两个不同的
  对象**，扫描器分不开——011 §4 合并读路径之后（WI-6 重写本段）：
  `book_store.load_book_cached`（:79）是核心，`search_service` 只是 `import` 了它
  （:14），两边**是同一个对象**；`server.load_book_cached`（:385）才是那个不同的
  对象——D5-a 的薄包装，一参签名、吞异常、返回 `Optional`，与核心共享缓存
  （`_share_loader_cache_surface`）但刻意不共享身份，好让六处
  `monkeypatch.setattr(server, "load_book_cached", …)` 只拦住 server 侧那十一处调用。
  合并前这段写的是「search_service 上那个才是另一个」，现在正好反过来，别照旧读。
  按名字扫的扫描器既分不开「同一个对象的两处绑定」也分不开「同名的两个对象」——
  这就是 B 必须拆成律 + 棘轮的原因。

* **Check C**（`scan_import_time_captures` / `scan_captures_tree`）——导入期抓取。
  Check B 是按**名单上的名字**做 key 的；模块级 rebind 会把名单上的名字洗成一个不在
  名单上的名字，两个 oracle 就都看不见了。枚举**五种**形状：赋值右值的 `ast.Name`
  与 `ast.Attribute`（`_CALL = server._call_provider`）、默认参数（含 `kw_defaults`）、
  装饰器实参、`from … import <名单名> as <别名>`。两种**改名**形状是关键：
  `_CALL = server._call_provider` 正是 A12 失败信息里「让 router 通过 server 取这个名字」
  的偷懒写法——守卫自己给的补救措施，居然有一个不受守卫的拼法。
  这个坑这个仓库栽过：`tests/contract/conftest.py:11-15` 记着 `load_ai_settings` 的
  路径是默认参数、「导入时就绑好了，patch `DEFAULT_SETTINGS_PATH` 什么都不做」。

扫描集合：三道检查扫的是 **`set(OWNERSHIP) | {"post_stream"}`**，不是 `owner_attr`。
`post_stream` 是别名的 owner 侧名字，`GLOBAL_RESOLVERS["post_stream"]` 是空集，
`EXPECTED_CAPTURES["post_stream"]` 是 `server.py:49` 那条 `import_alias`。

`OWNERSHIP` 是**三列**表，不是两列：`server._egress_post_stream` 是
`from ..ai.providers._http import post_stream as _egress_post_stream` 的别名，
两列表达不了。今天恰好只有这一条 `name != owner_attr`（A2 钉住这个 1）。

`EXPECTED_CAPTURES` 今天**不是空的**，这比空基线严格地好：一个「什么都不返回」的
扫描器会在这条上当场红，而不是白拿一个绿。两条都是生产代码里真实存在的：
`server.py:49` 的别名，和 `server.py:104` 的 `book_uuid_resolver = BookUuidResolver(BOOKS_DIR)`
——后者正好解释了为什么 `BOOKS_DIR`（8 处）和 `book_uuid_resolver`（6 处）必须分别打桩：
`BOOKS_DIR` 在导入期就被烤进了 resolver 里，只 patch 前者拦不住后者。
`server.py:1614` 的 `bound = AI_WORKER_STOP_TIMEOUT_S` 是**函数内**局部绑定，不算，
A14 的负控就是钉这个边界的。

自检（哪一处改动让哪一条断言变红）：

* 把 `server.py` 里某个 `from ..routers.x import y` 删掉、并在 `server.py` 上留一份旧
  定义 ⇒ **A4 红**（Check A 的重复定义变体，是它唯一抓得住的形状）。
* 把某个名字改成 re-export（`server.py` 从新 router 里 import 回来）⇒ **A3 仍然绿**、
  **A6 红**。第一句是 A5 用断言钉住的事实，不是一段没人读的散文。
* 把 `module_global_loads` 从 `ast` 换成 `re` ⇒ **A8 红**（往 docstring / 注释 /
  字符串 / f-string 里塞名字，或者写成 `cfg.retrieve_passages`，答案都不许变）。
* 在 `src/reader3_app/web/` 下新建一个 router，让它从自己的 globals 里取名单上的名字
  ⇒ **A12 红**，而且**这条红没有白名单可以加**。
* 往 `GLOBAL_RESOLVERS` 里加一个模块名 ⇒ **A6 变绿而 A12 仍然红**——这就是 B-i 与
  B-ii 的分工，也是为什么判据是 A12 不是 A6。
* 把 `scan_global_resolvers` 的模块名派生从 `src/` 起算改成从仓库根起算（`web.server`
  或 `src.reader3_app.web.server`）⇒ **A10 红**。而 A12 会因此**永远绿**——那正是 A10
  存在的全部理由：一句在任何树上都绿的判据不是判据。
* 把 `web/__init__.py` 的模块名派生成 `reader3_app.web.__init__` ⇒ **A10 红**（包自身
  落到律外，`__all__ = []` 那个空车位就没人看着了）。
* 模块级写一个 `_CALL = server._call_provider` 或 `_STREAM = _egress_post_stream`
  ⇒ **A15 红**（A16 是它的合成负控）。写在函数体里 ⇒ 不报，A14 钉这一半。
* 让 `scan_import_time_captures` 返回空 ⇒ **A15 的探针那一半红**
  （`ai/config.py:145,154` 是真树上真实存在的 `default_arg` 抓取）。

**A15 探针的维护约定**：探针名字 `DEFAULT_SETTINGS_PATH` 依赖 `ai/config.py` 的两个
默认参数。如果那两个默认参数以后被重构掉了，**重新挑一个真树上的探针名字，不要把
这一半删掉**——删掉之后 `EXPECTED_CAPTURES` 的空/非空断言就再也分不清「树是干净的」
和「扫描器什么都不返回」。

断言档位（见 tests/unit/conftest.py）：L1 表形状，L2 返回值，L4 故障注入。
规格档位见 `.claude/tdd-guardian/tests-20260907T022653Z.md`。
"""

from __future__ import annotations

import ast
import importlib
import types
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Sequence, Set, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

SERVER_MODULE = "reader3_app.web.server"
WEB_PACKAGE = "reader3_app.web"

#: 打桩接缝上的 20 个名字（2026-09-07 AST 实测；任务文档 §1 的 70/12 是行级 grep 的产物）。
EXPECTED_NAMES: FrozenSet[str] = frozenset(
    {
        "retrieve_passages",
        "BOOKS_DIR",
        "_call_provider",
        "book_token_stats",
        "book_uuid_resolver",
        "load_book_cached",
        "load_ai_settings",
        "BookVectorIndex",
        "search_library",
        "build_full_book_context",
        "build_multi_chapter_context",
        "ai_queue",
        "_get_provider_runtime",
        "_egress_post_stream",
        "AI_WORKER_STOP_TIMEOUT_S",
        "search_book",
        "save_ai_settings",
        "choose_routing",
        "get_provider_base_url",
        "_http_get_json",
    }
)

#: name -> (owner_module, owner_attr)。第三列不是装饰：`_egress_post_stream` 是别名。
OWNERSHIP: Dict[str, Tuple[str, str]] = {
    "retrieve_passages": (SERVER_MODULE, "retrieve_passages"),
    "BOOKS_DIR": (SERVER_MODULE, "BOOKS_DIR"),
    "_call_provider": (SERVER_MODULE, "_call_provider"),
    "book_token_stats": (SERVER_MODULE, "book_token_stats"),
    "book_uuid_resolver": (SERVER_MODULE, "book_uuid_resolver"),
    "load_book_cached": (SERVER_MODULE, "load_book_cached"),
    "load_ai_settings": (SERVER_MODULE, "load_ai_settings"),
    "BookVectorIndex": (SERVER_MODULE, "BookVectorIndex"),
    "search_library": (SERVER_MODULE, "search_library"),
    "build_full_book_context": (SERVER_MODULE, "build_full_book_context"),
    "build_multi_chapter_context": (SERVER_MODULE, "build_multi_chapter_context"),
    "ai_queue": (SERVER_MODULE, "ai_queue"),
    "_get_provider_runtime": (SERVER_MODULE, "_get_provider_runtime"),
    # 唯一一条两列表达不了的：server.py:49 的 `import post_stream as _egress_post_stream`。
    "_egress_post_stream": ("reader3_app.ai.providers._http", "post_stream"),
    "AI_WORKER_STOP_TIMEOUT_S": (SERVER_MODULE, "AI_WORKER_STOP_TIMEOUT_S"),
    "search_book": (SERVER_MODULE, "search_book"),
    "save_ai_settings": (SERVER_MODULE, "save_ai_settings"),
    "choose_routing": (SERVER_MODULE, "choose_routing"),
    "get_provider_base_url": (SERVER_MODULE, "get_provider_base_url"),
    "_http_get_json": (SERVER_MODULE, "_http_get_json"),
}

#: 三道检查扫的名字集合：名单 ∪ 别名的 owner 侧名字。
SCAN_NAMES: FrozenSet[str] = frozenset(set(OWNERSHIP) | {"post_stream"})

#: B-ii 特征化棘轮。**不是判据**——往 frozenset 里加一个模块名就能让它变绿，A12 加不进去。
GLOBAL_RESOLVERS: Dict[str, FrozenSet[str]] = {
    # ── 2026-09-19（011 WI-4 第七步，ai 组）：以下 11 条全部**往松了走** ────────
    # 一个共同的原因：server.py 里读这些名字的地方，全在刚搬进 `routers/ai/` 的四个
    # 模块里（chat / summary / conversations / rag），搬过去之后改走 `_server.X`
    # 属性访问——不是模块级 Name load，扫描器按设计看不见。
    #
    # 空集会掩盖「这个名字已经没人用了」，所以逐名做了一次定向破坏（把 `_server.X`
    # 换成 `from ...server import X` 的导入期绑定），每次跑一整条 unit lane，事后
    # 按字节还原并 cmp 校验（11/11 还原 OK）。**每一条都红了，且红的不只是静态闸**：
    #
    #   名字                          | 行为测试红的条数（另加 a12＋a15 两道静态闸）
    #   AI_WORKER_STOP_TIMEOUT_S      | 1  lease Q4
    #   _call_provider                | 3  lease Q1/Q2/Q6 ＋ 8  event_loop T2e–T2l（另 19 error）
    #   _egress_post_stream           | 2  lease Q3/Q4（另 2 error）
    #   _get_provider_runtime         | 5  lease Q1–Q4/Q6 ＋ 8  event_loop T2e–T2l
    #   ai_queue                      | 1  lease Q3
    #   book_token_stats              | 5  event_loop T2h–T2l
    #   build_full_book_context       | 3  event_loop T2i/T2k/T2l
    #   build_multi_chapter_context   | 3  event_loop T2j/T2k/T2l
    #   choose_routing                | 1  lease Q1
    #   retrieve_passages             | 5  lease Q1–Q4/Q6 ＋ 9  event_loop T2d–T2l
    #   load_book_cached              | 8  event_loop T2e–T2l
    #
    # 与 WI-4 第五步的 `_http_get_json` 对照着看：那一条破坏后**只**红 a12，没有任何
    # 行为测试跟上，所以它是「只有静态闸护着」。这 11 条不是——它们每条都有行为覆盖，
    # 两道静态闸是第二层，不是唯一一层。
    # ADR-0006 的两条出口（`_call_provider` / `_egress_post_stream`）另有一条活证据：
    # `test_ai_queue_lease.py` 里 11 处 `monkeypatch.setattr(server, ...)` 这次一个字
    # 没动，Q1–Q6 照样全绿——桩打在 server 上、代码跑在 chat.py 里，接缝就在那儿。
    "AI_WORKER_STOP_TIMEOUT_S": frozenset(),
    "BOOKS_DIR": frozenset({SERVER_MODULE}),
    # ai/rag.py:6 模块级 import + 10、61 两处载入。search_service.py:312 与 reader3.py:709
    # 是**函数体内** import（局部绑定），按设计不算——见 A7 的对照半边。
    # 2026-09-19（011 WI-4 第三步）：从 {server, ai.rag} 降为 {ai.rag}，同样是放松。
    # server.py 里读这个名字的三处全在 /api/index/* 与 /api/library/stats 里，
    # 已经分别搬进 routers/search.py 与 routers/library.py，改走属性访问。
    # 接缝仍然承重的证据（定向破坏，两文件同时改成导入期绑定，已 cmp 还原）：
    # test_event_loop_not_blocked.py 的 T1 / T2c / T3×2 四条，加本文件 a15。
    "BookVectorIndex": frozenset({"reader3_app.ai.rag"}),
    "_call_provider": frozenset(),
    "_egress_post_stream": frozenset(),
    "_get_provider_runtime": frozenset(),
    # 2026-09-19（011 WI-4 第五步）：降为空集。读这个名字的两处都在 /api/ollama/*，
    # 已搬进 routers/settings.py，改走属性访问。破坏证据：换成导入期绑定后
    # 只红 a12（B-i 律），**没有任何行为测试跟着红**——这条接缝在 unit lane 里
    # 没有行为覆盖，护着它的就是 a12 加 a15 两道静态闸，别把它们当可有可无的。
    "_http_get_json": frozenset(),
    "ai_queue": frozenset(),
    "book_token_stats": frozenset(),
    "book_uuid_resolver": frozenset({SERVER_MODULE}),
    "build_full_book_context": frozenset(),
    "build_multi_chapter_context": frozenset(),
    "choose_routing": frozenset(),
    "get_provider_base_url": frozenset({SERVER_MODULE}),
    # ai/config.py:145 def + 194、229、241 三处载入。
    "load_ai_settings": frozenset({SERVER_MODULE, "reader3_app.ai.config"}),
    # 011 §4（WI-6）改：新增 `reader3_app.book_store`，并重写这段注释——旧注释在合并后
    # 是**反的**。今天的形状是「一个核心对象，三个模块从自己的 globals 里解析它」＋
    # 「server 上另有一个同名的薄包装」：
    #   - book_store.py:79 def，147（load_book）与 176（load_book_metadata）两处载入。
    #     定义者解析自己的定义，见 docstring；任何走共享缓存的实现都躲不掉这两处。
    #   - search_service.py:14 `from .book_store import ... load_book_cached`（不再是
    #     def——它自己的那份已经搬走了）+ 270、332、494、678 四处载入。它拿到的就是
    #     book_store 那个对象，**不再**是「另一个同名函数」。
    #   - web/server.py:385 仍 def 着那个 D5-a 薄包装——**这一个**才是与前两者不同一的
    #     那个对象：一参签名、吞异常、返回 Optional，与核心共享缓存但不共享身份。
    #     但 011 WI-4 之后它在 server.py 里的十一处载入**一处不剩**，全随路由搬进了
    #     routers/（library 2、notes 5、reader 1、ai/chat 2、ai/summary 1），改走属性
    #     访问，所以 server 从这个集合里掉了出去——def 是 Store 不是 Load，扫描器只数
    #     Load。破坏证据见上表最后一行：8 条 event_loop 测试跟着红。
    # 按名字扫的扫描器分不开「同一个对象的两处 import」与「同名的两个对象」——这正是
    # B 必须拆成律（A12）+ 棘轮（A6）的原因，合并前后都成立。
    "load_book_cached": frozenset(
        {"reader3_app.search_service", "reader3_app.book_store"}
    ),
    # 别名的 owner 侧名字：全 src/ 没有任何模块从自己的 globals 里取 `post_stream`。
    "post_stream": frozenset(),
    "retrieve_passages": frozenset(),
    # 2026-09-19（011 WI-4 第五步）：降为空集，理由同上（四处全在 /api/settings/*）。
    # 这条反过来有行为覆盖：破坏后除 a12 外还红了 test_settings_no_preference_loss.py
    # 的三条（单键 PUT 不得冲掉其它偏好）。
    "save_ai_settings": frozenset(),
    # 2026-09-19（011 WI-4 第二步）：这两条从 {server} 降为空集，方向是**放松**。
    # server.py 里唯一从自己 globals 里取这两个名字的地方，就是刚搬进
    # `web/routers/search.py` 的那几条路由；搬过去之后它们改走 `_server.search_book(...)`
    # 属性访问，不是模块级 Name load，所以扫描器看不见——这正是 `routers/__init__.py`
    # 那张表要的形状。server.py 侧的 import 留着，`server.search_book` 仍是打桩接缝。
    # 空集会掩盖「这个名字已经没人用了」，所以补一句接缝仍然承重的证据（定向破坏，
    # 已按字节还原）：把 search.py 的 `_server.search_book` 换成导入期绑定，红三条——
    # test_event_loop_not_blocked.py::test_T2b / test_T3，以及本文件的 a15（Check C）。
    "search_book": frozenset(),
    "search_library": frozenset(),
}

#: Check C 真树基线（2026-09-07 实测）。name -> [(相对路径, 行号, kind)]。
#: 两条都是生产代码里真实存在的导入期抓取，见模块 docstring。
EXPECTED_CAPTURES: Dict[str, List[Tuple[str, int, str]]] = {
    # server.py:104 `book_uuid_resolver = BookUuidResolver(BOOKS_DIR)`
    "BOOKS_DIR": [("src/reader3_app/web/server.py", 104, "module_assign")],
    # server.py:49 `from ..ai.providers._http import post_stream as _egress_post_stream`
    "post_stream": [("src/reader3_app/web/server.py", 49, "import_alias")],
}

#: A15 的探针：真树上真实存在的 default_arg 抓取。见 docstring 的维护约定。
PROBE_CAPTURE_NAME = "DEFAULT_SETTINGS_PATH"


# ==========================================================================
# 被测单元 —— 全部是纯函数，既跑真树也跑合成输入
# ==========================================================================


def identity_violation(
    name: str,
    server_mod: types.ModuleType,
    owner_mod: types.ModuleType,
    owner_attr: str,
) -> str | None:
    """Check A：`server.<name>` 与 `<owner>.<attr>` 不是同一个对象时返回诊断，否则 None。"""
    server_name = getattr(server_mod, "__name__", repr(server_mod))
    owner_name = getattr(owner_mod, "__name__", repr(owner_mod))
    missing = object()
    on_server = getattr(server_mod, name, missing)
    if on_server is missing:
        return (
            f"{server_name}.{name} 不存在：打桩点指向的名字已经不在 server 命名空间里了"
        )
    on_owner = getattr(owner_mod, owner_attr, missing)
    if on_owner is missing:
        return f"{owner_name}.{owner_attr} 不存在：registry 的 owner 列指向了一个不存在的符号"
    if on_server is on_owner:
        return None
    return (
        f"{server_name}.{name} 不是 {owner_name}.{owner_attr}："
        f"{on_server!r} vs {on_owner!r}。server 上留了一份旧副本，"
        f"monkeypatch.setattr(server, {name!r}, ...) 打的是那份旧副本"
    )


_BLOCK_STMTS = (
    ast.If,
    ast.Try,
    ast.While,
    ast.For,
    ast.AsyncFor,
    ast.With,
    ast.AsyncWith,
)


@lru_cache(maxsize=64)
def _parse(source: str, filename: str) -> ast.Module:
    """解析一次、复用多次。A9 会拿 119KB 的 server.py 反复调用同一个扫描器。"""
    return ast.parse(source, filename)


def _module_level_bindings(tree: ast.Module) -> Dict[str, List[ast.stmt]]:
    """模块级绑定：顶层 import / from-import / def / class / 赋值。

    刻意**不**下潜进函数体与 class 体：前者是局部绑定（`search_service.py:312`、
    `reader3.py:709` 就是这个形状，算成违规会让 Check B 在当前树上直接红），
    后者绑的是类属性不是模块 global。顶层的 `if` / `try` / `with` / 循环**要**下潜——
    条件式 import 依然是模块级绑定。
    """
    out: Dict[str, List[ast.stmt]] = {}

    def record(name: str, stmt: ast.stmt) -> None:
        out.setdefault(name, []).append(stmt)

    def visit(body: Iterable[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    record(alias.asname or alias.name.split(".")[0], stmt)
            elif isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    record(alias.asname or alias.name, stmt)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                record(stmt.name, stmt)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    for node in ast.walk(target):
                        if isinstance(node, ast.Name):
                            record(node.id, stmt)
            elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                if isinstance(stmt.target, ast.Name):
                    record(stmt.target.id, stmt)
            elif isinstance(stmt, _BLOCK_STMTS):
                visit(stmt.body)
                visit(getattr(stmt, "orelse", []) or [])
                visit(getattr(stmt, "finalbody", []) or [])
                for handler in getattr(stmt, "handlers", []) or []:
                    visit(handler.body)

    visit(tree.body)
    return out


def module_global_loads(source: str, filename: str, names: Iterable[str]) -> Set[str]:
    """Check B 内核：`names` 中被这份源码**模块级绑定**且在绑定语句之外**载入**的那些。

    只数 `ast.Name(ctx=Load)`。属性载入（`cfg.retrieve_passages`）按设计不数——
    那是 Check C 的活（A8 的 `other_attr` 位置、A16 的 `_CALL = server._call_provider`）。
    docstring / 注释 / 字符串字面量根本不产生 Name 节点，所以 A8 那条恒等式是免费的：
    它免费的前提正是「读 AST 不读文本」。
    """
    wanted = set(names)
    if not wanted:
        return set()
    tree = _parse(source, filename)
    bindings = _module_level_bindings(tree)
    relevant = wanted & set(bindings)
    if not relevant:
        return set()

    # 绑定语句**自身**里对同名的载入不算（递归自调用、`X = X` 之类）。
    excluded: Set[int] = set()
    for name in relevant:
        for stmt in bindings[name]:
            for node in ast.walk(stmt):
                if (
                    isinstance(node, ast.Name)
                    and node.id == name
                    and isinstance(node.ctx, ast.Load)
                ):
                    excluded.add(id(node))

    found: Set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in relevant
            and id(node) not in excluded
        ):
            found.add(node.id)
    return found


def iter_src_modules(repo_root: Path) -> List[Tuple[Path, str]]:
    """`(路径, 完整点分模块名)`，模块名从 `src/` 起算。排除 `__pycache__`。

    **从 `src/` 起算，不是从仓库根起算。**从仓库根起算会派生出
    `src.reader3_app.web.server`，B-i 的前缀就再也匹配不上任何东西，A12 永远绿。
    A10 钉的就是这一点。`__init__.py` 派生成包名本身（`reader3_app.web`），
    不是 `reader3_app.web.__init__`——否则包自身落在律外。
    """
    src_root = Path(repo_root) / "src"
    out: List[Tuple[Path, str]] = []
    for path in sorted(src_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(src_root).parts)
        parts[-1] = parts[-1][: -len(".py")]
        if parts[-1] == "__init__":
            parts.pop()
        out.append((path, ".".join(parts)))
    return out


def scan_global_resolvers(repo_root: Path, names: Iterable[str]) -> Dict[str, Set[str]]:
    """Check B over `src/`：name -> {从自己 globals 里解析它的点分模块名}。"""
    wanted = set(names)
    out: Dict[str, Set[str]] = {name: set() for name in wanted}
    for path, dotted in iter_src_modules(repo_root):
        source = path.read_text(encoding="utf-8")
        for name in module_global_loads(source, str(path), wanted):
            out[name].add(dotted)
    return out


def web_namespace_offenders(resolvers: Dict[str, Set[str]]) -> Set[Tuple[str, str]]:
    """Check B-i：命名空间律。纯函数，可以喂手搓的 `{name: {module}}`。

    `module == WEB_PACKAGE` 那一支是**承重的**：前缀 `"reader3_app.web."` 带着一个点，
    没有这一支，包自身（`web/__init__.py`，今天是 `__all__ = []`）就落在律外。
    """
    return {
        (name, module)
        for name, modules in resolvers.items()
        for module in modules
        if (module == WEB_PACKAGE or module.startswith(WEB_PACKAGE + "."))
        and module != SERVER_MODULE
    }


def format_offenders(offenders: Set[Tuple[str, str]]) -> str:
    """B-i 的失败信息。措辞是用例的一部分，不是装饰。"""
    return (
        f"{sorted(offenders)} —— reader3_app.web.* 下的模块从自己的 globals 里取了打桩名单上的名字。"
        "monkeypatch.setattr(server, ...) 够不着它，那 8 个 _call_provider 桩会一个都拦不住。"
        "**不要把模块名加进白名单**——这条规则里没有白名单可加。"
        "要么让 router 通过 server 取这个名字，要么把打桩点一起搬过去。"
    )


def scan_import_time_captures(
    source: str, filename: str, names: Iterable[str]
) -> List[Tuple[str, int, str]]:
    """Check C 内核：`(name, lineno, kind)`，kind ∈ 五种形状对应的四个标签。

    五种形状（plan 的枚举）：赋值右值里的 `ast.Name`、赋值右值里的 `ast.Attribute`
    （`_CALL = server._call_provider`，两者都记 `module_assign`）、默认参数
    （含 `kw_defaults`）、装饰器实参、`from … import <名单名> as <别名>`。

    **只走模块作用域**：顶层语句、顶层 `if/try/with/循环` 的分支、以及模块级 class
    体里的方法签名（它们的默认值同样在导入期求值）。**不下潜进函数体**——
    `server.py:1614` 的 `bound = AI_WORKER_STOP_TIMEOUT_S` 是函数内局部绑定，
    数进来的话 A14 的负控和 A15 的真树基线会同时红。
    """
    wanted = set(names)
    sites: List[Tuple[str, int, str]] = []
    if not wanted:
        return sites
    tree = _parse(source, filename)

    def hits(node: ast.AST) -> List[Tuple[str, int]]:
        out: List[Tuple[str, int]] = []
        for sub_node in ast.walk(node):
            if (
                isinstance(sub_node, ast.Name)
                and isinstance(sub_node.ctx, ast.Load)
                and sub_node.id in wanted
            ):
                out.append((sub_node.id, sub_node.lineno))
            elif isinstance(sub_node, ast.Attribute) and sub_node.attr in wanted:
                out.append((sub_node.attr, sub_node.lineno))
        return out

    def signature(node) -> None:
        for decorator in node.decorator_list:
            for name, lineno in hits(decorator):
                sites.append((name, lineno, "decorator_arg"))
        args = node.args
        defaults = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
        for default in defaults:
            for name, lineno in hits(default):
                sites.append((name, lineno, "default_arg"))

    def visit(body: Iterable[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    if alias.asname and alias.name in wanted:
                        sites.append((alias.name, stmt.lineno, "import_alias"))
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname and alias.name.split(".")[-1] in wanted:
                        sites.append((alias.name.split(".")[-1], stmt.lineno, "import_alias"))
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                value = getattr(stmt, "value", None)
                if value is not None:
                    for name, lineno in hits(value):
                        sites.append((name, lineno, "module_assign"))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                signature(stmt)
            elif isinstance(stmt, ast.ClassDef):
                for decorator in stmt.decorator_list:
                    for name, lineno in hits(decorator):
                        sites.append((name, lineno, "decorator_arg"))
                visit(stmt.body)
            elif isinstance(stmt, _BLOCK_STMTS):
                visit(stmt.body)
                visit(getattr(stmt, "orelse", []) or [])
                visit(getattr(stmt, "finalbody", []) or [])
                for handler in getattr(stmt, "handlers", []) or []:
                    visit(handler.body)

    visit(tree.body)

    deduped: List[Tuple[str, int, str]] = []
    seen: Set[Tuple[str, int, str]] = set()
    for site in sites:
        if site not in seen:
            seen.add(site)
            deduped.append(site)
    return deduped


def scan_captures_tree(
    repo_root: Path, names: Iterable[str]
) -> Dict[str, List[Tuple[str, int, str]]]:
    """Check C over `src/`：name -> [(仓库相对路径, 行号, kind)]。"""
    wanted = set(names)
    root = Path(repo_root)
    out: Dict[str, List[Tuple[str, int, str]]] = {}
    for path, _dotted in iter_src_modules(root):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        for name, lineno, kind in scan_import_time_captures(source, str(path), wanted):
            out.setdefault(name, []).append((relative, lineno, kind))
    return out


# ==========================================================================
# 真树扫描缓存（一次会话扫一遍，不是每条参数化用例扫一遍）
# ==========================================================================


@lru_cache(maxsize=4)
def _real_resolvers(repo_root: Path) -> Dict[str, FrozenSet[str]]:
    return {k: frozenset(v) for k, v in scan_global_resolvers(repo_root, SCAN_NAMES).items()}


@lru_cache(maxsize=4)
def _real_offenders(repo_root: Path) -> FrozenSet[Tuple[str, str]]:
    return frozenset(web_namespace_offenders(dict(_real_resolvers(repo_root))))



# ==========================================================================
# A1 / A2 —— registry 表形状
# ==========================================================================


def test_a1_registry_key_set_is_exactly_the_twenty_patched_names() -> None:
    """A1（L1/S3）：键集恰好是那 20 个名字。"""
    assert set(OWNERSHIP) == EXPECTED_NAMES, (
        f"surplus={sorted(set(OWNERSHIP) - EXPECTED_NAMES)} "
        f"missing={sorted(EXPECTED_NAMES - set(OWNERSHIP))}"
    )


@pytest.mark.parametrize("name", sorted(OWNERSHIP))
def test_a1_every_owner_module_imports_and_carries_its_attr(name: str) -> None:
    """A1（L1/S3）：每条 owner 都 import 得进来，owner_attr 都真的存在。"""
    owner_module, owner_attr = OWNERSHIP[name]
    mod = importlib.import_module(owner_module)
    assert hasattr(mod, owner_attr), (
        f"{owner_module}.{owner_attr} 不存在——registry 的 owner 列指向了一个不存在的符号"
    )


def test_a2_the_alias_entry_is_a_triple_and_its_two_columns_differ() -> None:
    """A2（L2/S2）：别名条目与同名条目对照，证明第三列不是装饰。"""
    assert OWNERSHIP["_egress_post_stream"] == (
        "reader3_app.ai.providers._http",
        "post_stream",
    ), OWNERSHIP["_egress_post_stream"]
    assert OWNERSHIP["BOOKS_DIR"] == (SERVER_MODULE, "BOOKS_DIR"), OWNERSHIP["BOOKS_DIR"]
    aliases = sorted(n for n, (_m, a) in OWNERSHIP.items() if n != a)
    assert aliases == ["_egress_post_stream"], (
        f"今天 name != owner_attr 的条目应当**恰好**只有别名那一条，实得 {aliases}"
    )


# ==========================================================================
# A3 / A4 / A5 —— Check A
# ==========================================================================


@pytest.mark.parametrize("name", sorted(OWNERSHIP))
def test_a3_check_a_holds_on_the_real_tree(name: str) -> None:
    """A3（L2/S3）：真树上 `server.<name> is <owner>.<attr>`，一名一例。"""
    server = importlib.import_module(SERVER_MODULE)
    owner_module, owner_attr = OWNERSHIP[name]
    owner_mod = importlib.import_module(owner_module)
    assert identity_violation(name, server, owner_mod, owner_attr) is None, (
        f"server.{name} 与 {owner_module}.{owner_attr} 不是同一个对象——"
        "server 上留了一份旧副本，打桩打在旧副本上"
    )


def test_a4_check_a_negative_control_duplicate_definition_names_both_sides() -> None:
    """A4（L4/S2）：重复定义被报出来并同时点名两侧；同构的对照对不报。"""
    fake_server = types.ModuleType("fake_server")
    fake_server._call_provider = lambda: "old"  # type: ignore[attr-defined]
    fake_router = types.ModuleType("fake_router")
    fake_router._call_provider = lambda: "new"  # type: ignore[attr-defined]

    msg = identity_violation("_call_provider", fake_server, fake_router, "_call_provider")
    assert msg is not None, (
        "server 上留着一份旧副本、owner 上是另一个对象——Check A 唯一抓得住的那种形状，"
        "它居然说没事"
    )
    assert all(t in msg for t in ("fake_server", "fake_router", "_call_provider")), msg

    sentinel = object()
    fake_server_ok = types.ModuleType("fake_server_ok")
    fake_owner_ok = types.ModuleType("fake_owner_ok")
    fake_server_ok.x = sentinel  # type: ignore[attr-defined]
    fake_owner_ok.x = sentinel  # type: ignore[attr-defined]
    assert identity_violation("x", fake_server_ok, fake_owner_ok, "x") is None, (
        "同一个对象也被报成违规——那这个检查是常量返回，不是检查"
    )


#: A5 的合成 router 源码：re-export 形状里 router **自己**定义并调用那个名字。
_A5_ROUTER_SRC = (
    "from ._http import post_json\n"
    "\n"
    "def _call_provider(name, **kw):\n"
    "    return post_json(name)\n"
    "\n"
    "def handler():\n"
    "    return _call_provider('anthropic')\n"
)


def test_a5_blind_spot_pin_re_export_keeps_check_a_green_and_makes_check_b_red() -> None:
    """A5（L4/S2）：把 Check A 的瞎点钉成红绿事实，而不是一段没人读的散文。"""
    fn = lambda **kw: None  # noqa: E731  —— 同一性刻意保持，镜像 `from .routers.ai import ...`
    fake_router = types.ModuleType("fake_router")
    fake_server = types.ModuleType("fake_server")
    fake_router._call_provider = fn  # type: ignore[attr-defined]
    fake_server._call_provider = fn  # type: ignore[attr-defined]

    assert (
        identity_violation("_call_provider", fake_server, fake_router, "_call_provider") is None
    ), (
        "Check A 在 re-export 形状上报了红——那它就不是这里描述的那个 Check A 了；"
        "本条的整个意义是钉住它在这里是绿的"
    )
    assert "_call_provider" in module_global_loads(
        _A5_ROUTER_SRC, "<fake router>", set(OWNERSHIP)
    ), "Check B 没抓到 re-export：两道检查同时对主要威胁失明，registry 就只是一张表"


# ==========================================================================
# A6 / A7 / A8 / A9 / A10 —— Check B 内核与 B-ii 棘轮
# ==========================================================================


@pytest.mark.parametrize("name", sorted(SCAN_NAMES))
def test_a6_b_ii_characterization_ratchet_global_resolver_map_is_unchanged(
    repo_root: Path, name: str
) -> None:
    """A6（L2/S3）：B-ii 特征化棘轮。**这不是判据**——判据是 A12。"""
    found = _real_resolvers(repo_root)
    got = set(found.get(name, set()))
    expected = set(GLOBAL_RESOLVERS[name])
    assert got == expected, (
        f"{name} 的模块级解析点变了：新增 {sorted(got - expected)}，消失 {sorted(expected - got)}。"
        "这是**特征化棘轮**，不是判据：往 frozenset 里加一个模块名就能让它变绿。"
        "判据是 A12（B-i 命名空间律），它加不进去。"
    )


_A7_VIOLATING = "from ..server import _call_provider\n\ndef handler():\n    return _call_provider('x')\n"
_A7_CONTROL = "def handler():\n    from ..server import _call_provider\n    return _call_provider('x')\n"


def test_a7_check_b_negative_control_reverse_import_vs_function_local_import() -> None:
    """A7（L4/S2）：模块级反向 import 报，函数体内 import 不报。"""
    names = set(OWNERSHIP)
    assert module_global_loads(_A7_VIOLATING, "<v>", names) == {"_call_provider"}, (
        "模块级 `from ..server import _call_provider` + 调用没被算成解析点——"
        "那个模块被导入之后再 patch server.<name> 根本改不到它的 global"
    )
    assert module_global_loads(_A7_CONTROL, "<c>", names) == set(), (
        "函数体内 import 是局部绑定，模块级 patch 本来就够不着也拦不住——"
        "把它算成违规会让 Check B 在当前树上直接红"
        "（search_service.py:312、reader3.py:709 就是这个形状）"
    )


_A8_SKELETONS: Tuple[str, ...] = (
    # 模块级 import + 函数体内载入
    (
        "from ..ai.rag import retrieve_passages\n"
        "from ..search_service import search_book\n"
        "# <<SPLICE>>\n"
        "def handler():\n"
        "    return retrieve_passages('q')\n"
    ),
    # 只有模块级 def，没有载入
    ("# <<SPLICE>>\ndef retrieve_passages(q):\n    return q\n"),
    # 空模块
    ("# <<SPLICE>>\n"),
)

_A8_PLACEMENTS = ("docstring", "comment", "str_literal", "fstring", "other_attr")


def _prose_lines(name: str, placement: str, n_mentions: int) -> List[str]:
    """生成只把 `name` 放进散文/属性位置的模块级语句，绝不产生一次 `ast.Name` 载入。"""
    if placement == "docstring":
        return [f'"""参见 {name} 的说明。"""' for _ in range(n_mentions)]
    if placement == "comment":
        return [f"# 这里提到 {name}，只是注释" for _ in range(n_mentions)]
    if placement == "str_literal":
        return [f'_S{i} = "{name}"' for i in range(n_mentions)]
    if placement == "fstring":
        return [f'_F{i} = f"see {name} {{1 + 1}}"' for i in range(n_mentions)]
    if placement == "other_attr":
        return [f"_A{i} = cfg.{name}" for i in range(n_mentions)]
    raise AssertionError(f"unknown placement {placement!r}")


def _splice(base: str, lines: Sequence[str]) -> str:
    return base.replace("# <<SPLICE>>", "\n".join(lines))


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    base=st.sampled_from(_A8_SKELETONS),
    name=st.sampled_from(sorted(OWNERSHIP)),
    placement=st.sampled_from(_A8_PLACEMENTS),
    n_mentions=st.integers(min_value=0, max_value=4),
)
def test_a8_law_prose_insensitivity(
    base: str, name: str, placement: str, n_mentions: int
) -> None:
    """A8（L2/S4）：往散文里加名字是恒等变换。这条性质杀掉一切正则实现。"""
    mutated = _splice(base, _prose_lines(name, placement, n_mentions))
    before = module_global_loads(_splice(base, []), "<gen>", SCAN_NAMES)
    after = module_global_loads(mutated, "<gen>", SCAN_NAMES)
    assert after == before, (
        f"往 {placement} 里加 {n_mentions} 次 {name} 改变了扫描结果："
        f"{sorted(before)} -> {sorted(after)}；扫描器在读文本而不是读 AST"
    )


def test_a8_anchor_a_real_file_that_says_post_stream_in_its_docstring(repo_root: Path) -> None:
    """A8 的真树锚：`_http.py` 的模块 docstring 里写着 `post_stream`，扫描结果必须是空。"""
    src = (repo_root / "src" / "reader3_app" / "ai" / "providers" / "_http.py").read_text(
        encoding="utf-8"
    )
    assert "post_stream" in src.splitlines()[3], (
        "锚点前提没了：_http.py 第 4 行不再提 post_stream，这条锚要重新挑一个真文件"
    )
    assert module_global_loads(src, "_http.py", {"post_stream"}) == set(), (
        "_http.py 定义了 post_stream 但没有从自己的 globals 里载入过它；"
        "扫到了就是把 docstring 里那次提及数进去了"
    )


_A9_SOURCES: Tuple[Tuple[str, str], ...] = (
    (_A7_VIOLATING, "<a9-violating>"),
    (_A5_ROUTER_SRC, "<a9-router>"),
)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n1=st.sets(st.sampled_from(sorted(SCAN_NAMES))),
    n2=st.sets(st.sampled_from(sorted(SCAN_NAMES))),
)
def test_a9_law_union_homomorphism_over_the_name_set(
    n1: Set[str], n2: Set[str], repo_root: Path
) -> None:
    """A9（L2/S6）：`f(S, N1 | N2) == f(S, N1) | f(S, N2)`，且 `f(S, N) ⊆ N`。

    仓库根走 tests/conftest.py 的 session ``repo_root`` fixture。本文件原先自己
    ``parents[2]`` 算了第二份——两份定义只要有一份跟着文件搬家而另一份没有，读的就是两棵树，
    而这条用例恰恰是拿真 ``server.py`` 当被测输入的。

    子集律两边都断。只断 ``n1`` 那半边，一个「对 N2 越界、对 N1 不越界」的扫描器可以全绿；
    而参数表里 ``n1``/``n2`` 谁在左谁在右纯属排版，没有任何理由让这条律只对左边成立。
    """
    server_src = (
        repo_root / "src" / "reader3_app" / "web" / "server.py"
    ).read_text(encoding="utf-8")
    for src, label in _A9_SOURCES + ((server_src, "server.py"),):
        both = module_global_loads(src, label, n1 | n2)
        parts = module_global_loads(src, label, n1) | module_global_loads(src, label, n2)
        assert both == parts, f"扫描结果依赖名字集合的分组方式：{sorted(n1)} / {sorted(n2)}"
        for names, side in ((n1, "n1"), (n2, "n2")):
            got = module_global_loads(src, label, names)
            assert got <= names, (
                f"扫描器在 {side} 上返回了不在请求集合里的名字："
                f"{sorted(got - names)}（请求={sorted(names)}，源={label}）"
            )


def test_a10_the_scan_reads_the_package_and_derives_full_dotted_module_names(
    repo_root: Path,
) -> None:
    """A10（L2/S2）：文件数下界 + 点分模块名派生。A12 的非空洞地基。"""
    sources = iter_src_modules(repo_root)
    derived = {dotted for _path, dotted in sources}

    assert "reader3_app.web.server" in derived, (
        f"模块名派生错了：得到 {sorted(n for n in derived if n.endswith('server'))}。"
        "B-i（A12）是对 'reader3_app.web.' 做前缀匹配的——前缀一旦对不上，offenders 永远是空集，"
        "那道判据就变成一句在任何树上都绿的废话"
    )
    assert "reader3_app.ai.rag" in derived, sorted(derived)[:20]
    assert not (derived & {"web.server", "src.reader3_app.web.server", "server"}), sorted(derived)[
        :20
    ]
    assert "reader3_app.web" in derived and "reader3_app.web.__init__" not in derived, (
        f"web/__init__.py 派生成了 {sorted(n for n in derived if 'web' in n)}。"
        "B-i 的前缀 'reader3_app.web.' 带着一个点，包自身落在律外——而 web/__init__.py 今天是 "
        "`__all__ = []`，正是往里塞共享 helper 的空位"
    )
    assert not any("__pycache__" in Path(p).parts for p, _d in sources), (
        "扫到了 __pycache__ 里的 .pyc 旁生成物"
    )
    assert len(sources) >= 20, (
        "扫了 0 个文件的话，A6 那 20 条参数化用例会因为 found[name] 恒为空集而在某些 baseline 下全绿"
    )


# ==========================================================================
# A12 / A13 —— Check B-i，WI-1 的判据
# ==========================================================================


@pytest.mark.parametrize("name", sorted(SCAN_NAMES))
def test_a12_b_i_namespace_law_holds_on_the_real_tree(repo_root: Path, name: str) -> None:
    """A12（L2/S3）：**WI-1 的判据**，一名一例。"""
    offenders = {(n, m) for (n, m) in _real_offenders(repo_root) if n == name}
    assert offenders == set(), format_offenders(offenders)


def test_a12_b_i_namespace_law_holds_on_the_real_tree_in_aggregate(repo_root: Path) -> None:
    """A12（L2）：整份 offender 集合的聚合断言。"""
    offenders = set(_real_offenders(repo_root))
    assert offenders == set(), format_offenders(offenders)


_A13_ROUTER_SRC = (
    "from .._http import post_json\n"
    "\n"
    "def _call_provider(name, **kw):\n"
    "    return post_json(name)\n"
    "\n"
    "def route():\n"
    "    return _call_provider('anthropic')\n"
)

_A13_SERVER_STUB = (
    "def _call_provider(name, **kw):\n"
    "    return name\n"
    "\n"
    "def api():\n"
    "    return _call_provider('x')\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a13_b_i_negative_control_same_source_two_namespaces(tmp_path: Path) -> None:
    """A13（L4/S2）：同一份源码放在 web 命名空间里报、放在外面不报。"""
    t1 = tmp_path / "tree1"
    _write(t1 / "src/reader3_app/web/server.py", _A13_SERVER_STUB)
    _write(t1 / "src/reader3_app/web/routers/__init__.py", "")
    _write(t1 / "src/reader3_app/web/routers/ai.py", _A13_ROUTER_SRC)

    offenders = web_namespace_offenders(scan_global_resolvers(t1, set(OWNERSHIP)))
    assert offenders == {("_call_provider", "reader3_app.web.routers.ai")}, offenders
    msg = format_offenders(offenders)
    assert "reader3_app.web.routers.ai" in msg and "要么把打桩点一起搬过去" in msg, msg

    t2 = tmp_path / "tree2"
    _write(t2 / "src/reader3_app/search_service.py", _A13_ROUTER_SRC)
    scan2 = scan_global_resolvers(t2, set(OWNERSHIP))
    out_of_namespace_offenders = web_namespace_offenders(scan2)
    assert out_of_namespace_offenders == set(), (
        "B-i 把 web 命名空间外的模块也报成违规了——三个合法豁免会当场红"
    )
    assert "reader3_app.search_service" in scan2["_call_provider"], (
        "扫描器根本没看见这个 resolver，上一条的绿是假的"
    )


def test_a13_b_i_is_pure_over_a_hand_built_resolver_map() -> None:
    """A13 的无文件系统半边：B-i 必须能喂一个手搓的 `{name: {module}}`。"""
    resolvers = {
        "_call_provider": {"reader3_app.web.routers.ai", "reader3_app.web.server"},
        "load_book_cached": {"reader3_app.search_service"},
        # 包自身：前缀带点，靠 `== "reader3_app.web"` 那一支才抓得住
        "BOOKS_DIR": {"reader3_app.web"},
    }
    assert web_namespace_offenders(resolvers) == {
        ("_call_provider", "reader3_app.web.routers.ai"),
        ("BOOKS_DIR", "reader3_app.web"),
    }, web_namespace_offenders(resolvers)


# ==========================================================================
# A14 / A16 / A15 —— Check C
# ==========================================================================


_A14_SRC = (
    "from ..ai.providers._http import post_stream as _egress_post_stream\n"  # 1
    "from .deps import Depends\n"  # 2
    "\n"  # 3
    "_STREAM = _egress_post_stream\n"  # 4
    "\n"  # 5
    "def route(dep=Depends(_call_provider)):\n"  # 6
    "    return dep\n"  # 7
    "\n"  # 8
    "def other(fn=_call_provider):\n"  # 9
    "    return fn\n"  # 10
    "\n"  # 11
    "@register(_call_provider)\n"  # 12
    "def handler():\n"  # 13
    "    bound = AI_WORKER_STOP_TIMEOUT_S\n"  # 14
    "    return _call_provider('x')\n"  # 15
)


def test_a14_check_c_negative_control_module_scope_reported_function_scope_not() -> None:
    """A14（L2/S3）：三类抓取报出来，两类非抓取不报；模块作用域 vs 函数作用域的两侧钉。"""
    sites = scan_import_time_captures(_A14_SRC, "<syn>", set(SCAN_NAMES))
    got = {(name, kind) for name, _lineno, kind in sites}
    expected = {
        ("post_stream", "import_alias"),
        ("_egress_post_stream", "module_assign"),
        ("_call_provider", "default_arg"),
        ("_call_provider", "decorator_arg"),
    }
    assert got == expected, f"少报的：{expected - got}；多报的：{got - expected}"
    assert not any(n == "AI_WORKER_STOP_TIMEOUT_S" for n, _, _ in sites), (
        "函数体内的局部绑定被算成 import-time capture 了——server.py:1614 的 "
        "`bound = AI_WORKER_STOP_TIMEOUT_S` 就是这个形状，A15 会在真树上当场红"
    )
    assert sum(1 for n, _, k in sites if k == "default_arg") == 2, sites
    assert set(sites) == {
        ("post_stream", 1, "import_alias"),
        ("_egress_post_stream", 4, "module_assign"),
        ("_call_provider", 6, "default_arg"),
        ("_call_provider", 9, "default_arg"),
        ("_call_provider", 12, "decorator_arg"),
    }, f"行号对不上：{sorted(sites)}"


_A16_SRC = (
    "from .. import server\n"  # 1
    "from ..ai.rag import retrieve_passages as _retrieve\n"  # 2
    "\n"  # 3
    "_CALL = server._call_provider\n"  # 4
    "\n"  # 5
    "def route():\n"  # 6
    '    return _CALL(_retrieve("q"))\n'  # 7
)


def test_a16_check_c_covers_the_two_rename_shapes() -> None:
    """A16（L2/S3）：两种把名单上的名字**洗出名单**的改名形状都必须被抓到。"""
    got = {(n, k) for n, _ln, k in scan_import_time_captures(_A16_SRC, "<syn>", set(SCAN_NAMES))}
    assert ("_call_provider", "module_assign") in got, (
        "模块级 `_CALL = server._call_provider` 没被算成 import-time capture——这正是 A12 失败信息里"
        "「让 router 通过 server 取这个名字」的偷懒写法。名字在导入期就被抓成 _CALL，"
        "8 处 monkeypatch.setattr(server, '_call_provider', …) 一个都拦不住；"
        "而 B-i 结构上看不见它（A8 明确要求 module_global_loads 不数 Attribute 载入）"
    )
    assert ("retrieve_passages", "import_alias") in got, (
        "`from … import <名单上的名字> as <别名>` 把名字洗成了非名单名字——"
        "src/reader3_app/web/server.py:49 自己就是这个形状，全 src/ 仅此两处（48/49，已核）"
    )


def test_a15_check_c_real_tree_baseline_with_a_live_probe(repo_root: Path) -> None:
    """A15（L2/S2）：真树基线 + 一个真实探针，让「空答案」不能白拿绿。"""
    captures = {k: sorted(v) for k, v in scan_captures_tree(repo_root, set(SCAN_NAMES)).items()}
    expected = {k: sorted(v) for k, v in EXPECTED_CAPTURES.items()}
    assert captures == expected, (
        f"新增的 import-time capture：{ {k: v for k, v in captures.items() if v != expected.get(k)} }。"
        "模块级抓取会把名单上的名字洗成一个不在名单上的名字，"
        "Check B 的两道 oracle 都看不见它——tests/contract/conftest.py:11-15 记着上一次栽在这个形状上"
    )

    probe_map = scan_captures_tree(repo_root, {PROBE_CAPTURE_NAME})
    probe = {t for sites in probe_map.values() for t in sites}
    assert ("src/reader3_app/ai/config.py", 145, "default_arg") in probe, (
        f"探针名字在真树上一个 capture 都没扫到（{sorted(probe)}）——上一条的空集是因为扫描器什么都不返回，"
        "不是因为树是干净的"
    )
    assert ("src/reader3_app/ai/config.py", 154, "default_arg") in probe, sorted(probe)
