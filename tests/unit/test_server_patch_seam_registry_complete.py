"""WI-2（011 §1）——打桩接缝的**完整性锁**。

WI-1（`test_server_patch_seam_ownership.py`）有一张 20 个名字的 registry，并证明这些名字
在 `src/` 一侧确实是从 `server` 的命名空间里取的。这个模块守的是另一头：**树里真正被打桩
的名字集合，和那张表一字不差。**

`set(found) == set(OWNERSHIP)`，**等式，不是包含**。少一个名字要和多一个名字一样吵：
「registry 里写着某个名字受保护、树里其实没有任何一处打桩点在用它」，与
「树里多打了一个没登记的名字」是同一级别的谎。B9 就是钉这一条的负控。

## 为什么必须是 AST，不能是行级 grep

任务文档 §1 的 70 处 / 12 个文件就是行级 grep 的产物，真值是 76 / 15。grep 漏掉的三个
文件，每一个都对应一种**形状**：

* `tests/unit/test_settings_no_preference_loss.py:104-110` —— `monkeypatch.setattr(` 之后
  换行，参数在下一行。任何「一行里同时看见 setattr 和 server」的正则都读不到它。
* `tests/unit/test_fixture_damaged_bookdir.py:107,117` —— 同样是模块别名
  （`from reader3_app.web import server as web_server`）加上多行；`web_server` 这个拼法
  也不在 `monkeypatch.setattr(server,` 的字面模式里。
* `tests/contract/test_health_route.py:33` —— **字符串目标形状**
  `monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", …)`，全树独一处。一个只认
  对象形状的扫描器会带着一个洞发货，而且这个洞正好盖在 `BOOKS_DIR` 上。

再加上 `pytest.MonkeyPatch.context()` 的 `mp.setattr(...)` 句柄（`monkeypatch.` 前缀的
正则会漏），以及 `raising=False`（照收）。B6 把这些拉成一条**格式无关律**：抽出来的名字
集合不依赖调用怎么写。

## 三个返回通道，一个打桩点只能落进其中一个

`extract_patch_targets` 返回三段，B5 明确要求**互斥**——两个通道互相掩护的话，两条断言
就都不作数了：

1. **能解析到 server 模块 + 属性名是字面量** → 进名单。这是这道锁的正文。
2. **属性名不是字面量**（`monkeypatch.setattr(server, name_var, x)`）→ 报错，不是静默
   跳过。今天树上是零处，这是一根棘轮。静默跳过的版本会让名单短一截而全绿——那正是
   这道锁存在的理由。
3. **目标对象根本解析不到任何东西 + 属性名在 registry 上** → 报错。这是通道 2 的镜像：
   通道 2 管「名字是变量」，通道 3 管「目标是变量」。

通道 3 的**收窄是它能活下来的唯一形状**。`setattr(<动态加载的模块句柄>, "<字面量>", …)`
是这个仓库的家法，2026-09-07 实测约 14 处活的：`test_lint_e2e_selectors_closed_list.py`
（`ROOT` ×4、`ALLOWED_DISCRIMINATORS` @330）、`test_lint_testid_naming_uniqueness.py`
（`ROOT`、`UNIQUENESS_EXEMPTIONS`）、`test_coverage_gate_failclosed.py`（`CONFIG`、
`REPORT`）、`test_provider_response_parsing.py`（`post_json`）、`test_markexpr_guard.py:196`
（`_compile_markexpr`）。**这些属性名一个都不在 registry 上**，所以「只报属性名在名单上
的那些」落地当天就是绿的。一个「凡是解析不出目标就报」的版本会当场红十四次，然后在一周
内被删掉——洞就是这么重新打开的。

## 目标解析的三分法（B4 与 B11 靠它区分）

对一个 `ast.Name` 目标，按**作用域链**查它的绑定：

* 被 `import` 绑定、且在这条作用域链上**没有被非 import 语句重新绑定** → 解析成那个模块
  （是 `reader3_app.web.server` 就进名单，是别的模块就静默丢掉，B4 类 3/4）。
* 被 import 绑定过、但在更内层被普通赋值**遮蔽**了（`def t(): server = FakeThing()`）
  → 「解析得到，但不是 server」→ 静默。B4 类 5 就是这一格。
* **从来没有被任何 import 绑定过**（`mod = _load()`）→ 「什么都解析不到」→ 通道 3。

把这两格合并会让 B4 类 5 当场红（`BOOKS_DIR` 在名单上），拆开是设计，不是洁癖。
属性目标（`server.ai_queue`、`config.option`、`mod.subprocess`）一律不是模块本身，静默；
唯一的例外是 `import reader3_app.web.server` 之后写全的那条点分链。

## 计数只写下界，不写等值

`total >= 76` / `len(files) >= 15`，不是 `== 76 / == 15`。commit `0822a94`
（「把存量计数从等式/贴值下界改成关系断言」）在这个仓库里已经定过这个规矩：等值会逼着
每一条新加的打桩测试回来改这把锁，改着改着就没人看它了。下界抓得住这道锁真正要抓的
故障——**扫描器丢了一整类形状**——而对不是缺陷的增长保持沉默。同理，**不断言任何
按名字的出现次数**：集合才是不变量。

## 这个模块自己不许出现活的打桩点

B1 扫的就是 `tests/unit/**` 和 `tests/contract/**`，包括这个文件本身。所有负控都写成
**字符串字面量**或 `tmp_path` 下的文本文件；一旦哪个负控被写成模块体里真正的
`monkeypatch.setattr(server, …)`，它会被这次扫描收进去，B1 当场红。B1/B8/B9/B11 都重复
写着这句话。

自检（哪一处改动让哪一条断言变红）：

* 把 `extract_patch_targets` 从 `ast` 换成行级正则 ⇒ **B6 红**（多行/别名/`mp.` 句柄），
  **B2 红**（那三个 grep 漏掉的文件扫不到），**B3 红**。
* 只认对象形状、不认 `setattr("reader3_app.web.server.X", …)` 字符串目标
  ⇒ **B2/B3 红**，而且 `BOOKS_DIR` 在真树上会少一处（`test_health_route.py:33` 是全树
  唯一一处这个形状）。
* 把非字面量属性名 `except (AttributeError, TypeError): continue` 掉 ⇒ **B5 红**。
* 把「目标解析不出来」一律报出来（不收窄到 registry 名字）⇒ **B11 后半红**（家法那
  十四处会当场炸）。反过来一律静默 ⇒ **B11 前半红**。
* 把 B4 类 1/2 的属性目标（`server.ai_queue`）也算成 server 模块 ⇒ **B4 红**，而且真树上
  会多出 `release` / `books_dir` 两个名字，**B1 也红**。
* 把 `set(found) == set(OWNERSHIP)` 放宽成 `<=` 或 `>=` ⇒ **B9 红**（少一个名字不再吵）。
* 把 `total >= 76` 改成 `== 76` ⇒ 这条自检不会红，但下一个加打桩点的人会被迫来改这把
  锁——这正是 `0822a94` 禁掉的东西。
* 让 `iter_test_files` 漏掉 `conftest.py` ⇒ **B10 红**，并且 `tests/contract/conftest.py`
  里那 6 处打桩点会连带把 **B1 弄红**。

断言档位（见 tests/unit/conftest.py）：L1 表形状/走查，L2 返回值，L4 故障注入。
规格档位见 `.claude/tdd-guardian/tests-20260907T022653Z.md` 的 B1–B11。
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# tests/unit 没有 __init__.py，pytest 的 prepend 导入模式把这个目录放在 sys.path 上，
# 所以按裸模块名 import 兄弟测试模块是这个仓库的既有做法
# （test_ai_stub_contract.py 的 `from ai_stub import …`、
#   test_e2e_group_guard.py:55 的 `from test_soak_log_contract import …`）。
from test_server_patch_seam_ownership import OWNERSHIP

SERVER_MODULE = "reader3_app.web.server"

#: 这道锁扫的两个目录 —— 与 unit lane 的命令一致（`uv run pytest tests/unit tests/contract`）。
LANE_DIRS: Tuple[str, str] = ("tests/unit", "tests/contract")

#: 2026-09-07 实测下界。**只写下界**，理由见模块 docstring（commit 0822a94）。
MIN_OCCURRENCES = 76
MIN_TOUCHED_FILES = 15
MIN_SCANNED_FILES = 60


class PatchSite(NamedTuple):
    """通道 1：解析到了 server 模块、属性名是字面量。"""

    name: str
    lineno: int


class NonLiteralPatchTarget(NamedTuple):
    """通道 2：属性名不是字面量。B5 的失败信息按 `(文件, 行号)` 比对。"""

    filename: str
    lineno: int


class UnresolvableTarget(NamedTuple):
    """通道 3：目标对象解析不到任何东西，而属性名在 registry 上。"""

    filename: str
    lineno: int
    attr: str


ExtractResult = Tuple[
    List[PatchSite], List[NonLiteralPatchTarget], List[UnresolvableTarget]
]
TreeScan = Tuple[
    Dict[str, List[Tuple[str, int]]],
    List[NonLiteralPatchTarget],
    List[UnresolvableTarget],
]


# ==========================================================================
# 被测单元 —— 纯函数，既跑真树也跑合成源码字符串
# ==========================================================================



def _store_names(node: ast.AST) -> Set[str]:
    """一个赋值目标里所有被写入的名字（含解包、星号）。"""
    return {
        sub.id
        for sub in ast.walk(node)
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del))
    }


def _arg_names(args: ast.arguments) -> Set[str]:
    out = {a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)}
    if args.vararg is not None:
        out.add(args.vararg.arg)
    if args.kwarg is not None:
        out.add(args.kwarg.arg)
    return out


def _dotted(node: ast.AST) -> Optional[str]:
    """`a.b.c` -> "a.b.c"；根不是 Name 就返回 None。"""
    parts: List[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return ".".join(reversed(parts))


def _scope_bindings(body: Sequence[ast.stmt]) -> Tuple[Dict[str, Set[str]], Set[str], Set[str]]:
    """一个作用域**自己**的绑定：`(import 绑定, 非 import 绑定, 写全的点分模块名)`。

    刻意**不**下潜进嵌套的 `def` / `class` 体——那是另一个作用域，它们的局部变量遮蔽不到
    这里。顶层的 `if` / `try` / `with` / 循环**要**下潜：那还是同一个作用域。

    **已知的洞：流不敏感。** 返回的是「这个作用域里绑过什么」，不带语句顺序。多数时候这
    正好等于 Python 自己的规则——函数里任何一处赋值就让这个名字整体是局部的，所以
    「先 setattr 后赋值」在真 Python 里本来就是 UnboundLocalError，不是可用的打桩写法。
    唯一会错的形状是**同一个作用域里既 import 成 server、又另行赋值**：

        def test_x(monkeypatch):
            import reader3_app.web.server as server
            monkeypatch.setattr(server, "BOOKS_DIR", 1)   # 这里它还是真 server
            server = object()

    今天这个站点三个通道一个都不进（B13 把这个行为钉住）。它跟 B4 类 5
    （模块级 import server + 函数内 `server = FakeThing()`，那是真该忽略的）在本函数的
    返回值里长得一模一样：两者都是 imports 里有 server、rebound 里有这个名字。要分开，
    得让 `resolve` 知道 import 与赋值各自来自哪一层作用域——`handle_stmts` 现在把内外层
    `{**imports, **inner_i}` / `rebound | inner_r` 合并掉了，这个信息就在那里丢的。
    真树上零处，所以这是记在案的洞，不是今天要修的 bug。
    """
    imports: Dict[str, Set[str]] = {}
    rebound: Set[str] = set()
    dotted_modules: Set[str] = set()

    def walk(stmts: Iterable[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    dotted_modules.add(alias.name)
                    bound = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                    imports.setdefault(bound, set()).add(target)
            elif isinstance(stmt, ast.ImportFrom):
                base = stmt.module or ""
                for alias in stmt.names:
                    bound = alias.asname or alias.name
                    full = f"{base}.{alias.name}" if base else alias.name
                    imports.setdefault(bound, set()).add(full)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                rebound.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    rebound.update(_store_names(target))
            elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                rebound.update(_store_names(stmt.target))
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                rebound.update(_store_names(stmt.target))
                walk(stmt.body)
                walk(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars is not None:
                        rebound.update(_store_names(item.optional_vars))
                walk(stmt.body)
            elif isinstance(stmt, ast.Try):
                walk(stmt.body)
                walk(stmt.orelse)
                walk(stmt.finalbody)
                for handler in stmt.handlers:
                    if handler.name:
                        rebound.add(handler.name)
                    walk(handler.body)
            elif isinstance(stmt, (ast.If, ast.While)):
                walk(stmt.body)
                walk(stmt.orelse)

    walk(body)
    return imports, rebound, dotted_modules


# 矩阵的「Units under test」里还列了一个 `server_module_aliases(tree)`（整文件视角地列出
# 绑定到 server 模块的名字）。**这里刻意没有它。**整文件视角表达不了 B4 类 5 要求的那件事：
# 模块级 import 的 `server` 被函数内 `server = FakeThing()` 遮蔽。真正跑的解析走作用域链，
# 就在 `extract_patch_targets` 里。留一个语义更弱、又没有用例守着的同名概念在旁边，
# 迟早有人来「统一」这两者，而统一的方向一定是把作用域链拉平——那正好把 B4 类 5 打红。


def extract_patch_targets(
    source: str, filename: str, registry: Optional[Iterable[str]] = None
) -> ExtractResult:
    """三通道抽取。见模块 docstring 的「三个返回通道」与「目标解析的三分法」。"""
    names = set(OWNERSHIP) if registry is None else set(registry)
    tree = ast.parse(source, filename)

    collected: List[PatchSite] = []
    non_literal: List[NonLiteralPatchTarget] = []
    unresolvable: List[UnresolvableTarget] = []

    def resolve(node: ast.expr, imports: Mapping[str, Set[str]], rebound: Set[str],
                dotted_modules: Set[str]) -> str:
        if isinstance(node, ast.Name):
            if node.id not in imports:
                return "unresolvable"
            if node.id in rebound:
                # import 过、但在更内层被普通赋值遮蔽了：解析得到，只是不是 server。
                return "other"
            return "server" if SERVER_MODULE in imports[node.id] else "other"
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted == SERVER_MODULE and dotted in dotted_modules:
                return "server"
            # `server.ai_queue` / `config.option` / `mod.subprocess`：某个对象的属性，
            # 不是模块本身。B4 的类 1/2 就是这一格。
            return "other"
        return "unresolvable"

    def check_call(node: ast.Call, imports: Mapping[str, Set[str]], rebound: Set[str],
                   dotted_modules: Set[str]) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            fname = func.attr
        elif isinstance(func, ast.Name):
            fname = func.id
        else:
            return
        # `delattr` 今天零处；照收，因为「把名字从接缝上删掉」也是在用这条接缝。
        if fname not in ("setattr", "delattr"):
            return
        # 关键字拼法 `setattr(target=server, name="BOOKS_DIR", value=x)` 是合法的 pytest
        # 写法，而它的 `node.args` 是空的。这里原先直接 return，于是这种站点三个通道一个
        # 都不进——正好是通道 2/3 被引进来要消灭的那种**无声跳过**：注册表声称自己完整，
        # 而一处改拼法的打桩就能从它眼前消失。今天零处，属棘轮。
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        args = list(node.args)
        if len(args) < 2:
            if not args and "target" in kwargs:
                args.append(kwargs["target"])
            if len(args) == 1 and "name" in kwargs:
                args.append(kwargs["name"])
        if not args:
            return
        first = args[0]

        # 形状 2：字符串目标 `setattr("reader3_app.web.server.BOOKS_DIR", …)`。
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            module_part, _, attr = first.value.rpartition(".")
            if module_part == SERVER_MODULE:
                collected.append(PatchSite(attr, node.lineno))
            return

        kind = resolve(first, imports, rebound, dotted_modules)
        if kind == "other":
            return
        if len(args) < 2:
            non_literal.append(NonLiteralPatchTarget(filename, node.lineno))
            return
        name_node = args[1]
        if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
            attr = name_node.value
            if kind == "server":
                collected.append(PatchSite(attr, node.lineno))
            elif attr in names:
                unresolvable.append(UnresolvableTarget(filename, node.lineno, attr))
            return
        non_literal.append(NonLiteralPatchTarget(filename, node.lineno))

    def handle_expr(node: ast.AST, imports, rebound, dotted_modules) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                check_call(sub, imports, rebound, dotted_modules)

    def handle_stmts(stmts: Sequence[ast.stmt], imports, rebound, dotted_modules) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 装饰器与默认值在**外层**作用域求值。
                for decorator in stmt.decorator_list:
                    handle_expr(decorator, imports, rebound, dotted_modules)
                for default in list(stmt.args.defaults) + [
                    d for d in stmt.args.kw_defaults if d is not None
                ]:
                    handle_expr(default, imports, rebound, dotted_modules)
                inner_i, inner_r, inner_d = _scope_bindings(stmt.body)
                handle_stmts(
                    stmt.body,
                    {**imports, **inner_i},
                    rebound | inner_r | _arg_names(stmt.args),
                    dotted_modules | inner_d,
                )
            elif isinstance(stmt, ast.ClassDef):
                for decorator in stmt.decorator_list:
                    handle_expr(decorator, imports, rebound, dotted_modules)
                inner_i, inner_r, inner_d = _scope_bindings(stmt.body)
                handle_stmts(
                    stmt.body,
                    {**imports, **inner_i},
                    rebound | inner_r,
                    dotted_modules | inner_d,
                )
            elif isinstance(stmt, (ast.If, ast.While)):
                handle_expr(stmt.test, imports, rebound, dotted_modules)
                handle_stmts(stmt.body, imports, rebound, dotted_modules)
                handle_stmts(stmt.orelse, imports, rebound, dotted_modules)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                handle_expr(stmt.iter, imports, rebound, dotted_modules)
                handle_stmts(stmt.body, imports, rebound, dotted_modules)
                handle_stmts(stmt.orelse, imports, rebound, dotted_modules)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    handle_expr(item.context_expr, imports, rebound, dotted_modules)
                handle_stmts(stmt.body, imports, rebound, dotted_modules)
            elif isinstance(stmt, ast.Try):
                handle_stmts(stmt.body, imports, rebound, dotted_modules)
                for handler in stmt.handlers:
                    handle_stmts(handler.body, imports, rebound, dotted_modules)
                handle_stmts(stmt.orelse, imports, rebound, dotted_modules)
                handle_stmts(stmt.finalbody, imports, rebound, dotted_modules)
            else:
                handle_expr(stmt, imports, rebound, dotted_modules)

    top_i, top_r, top_d = _scope_bindings(tree.body)
    handle_stmts(tree.body, top_i, top_r, top_d)
    return collected, non_literal, unresolvable


def iter_test_files(roots: Sequence[Path]) -> List[Path]:
    """两个目录下所有 `*.py`（含 `conftest.py`），排除 `__pycache__`。"""
    out: List[Path] = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            out.append(path)
    return out


def scan_test_tree(
    roots: Sequence[Path],
    repo_root: Optional[Path] = None,
    registry: Optional[Iterable[str]] = None,
) -> TreeScan:
    """把 `extract_patch_targets` 折叠到整片测试树上；三个通道原样保留。"""
    found: Dict[str, List[Tuple[str, int]]] = {}
    non_literal: List[NonLiteralPatchTarget] = []
    unresolvable: List[UnresolvableTarget] = []
    for path in iter_test_files(roots):
        relative = (
            path.relative_to(repo_root).as_posix() if repo_root is not None else path.as_posix()
        )
        sites, bad_names, bad_targets = extract_patch_targets(
            path.read_text(encoding="utf-8"), relative, registry
        )
        for name, lineno in sites:
            found.setdefault(name, []).append((relative, lineno))
        non_literal.extend(bad_names)
        unresolvable.extend(bad_targets)
    return found, non_literal, unresolvable


def format_registry_mismatch(
    found: Mapping[str, List[Tuple[str, int]]], registry: Iterable[str]
) -> str:
    """名单与 registry 不一致时的诊断；一致时返回 `""`。

    多出来的名字必须带上 `file:line`——只打印 `found != expected` 的版本会让 B1 在实战里
    毫无用处（B8 钉这一条）。缺失的名字单独列一行，措辞里带「缺失」（B9 钉这一条）。
    """
    wanted = set(registry)
    surplus = sorted(set(found) - wanted)
    missing = sorted(wanted - set(found))
    if not surplus and not missing:
        return ""
    parts = ["打桩接缝名单与 registry 不一致。\n"]
    for name in surplus:
        where = ", ".join(f"{f}:{ln}" for f, ln in found[name])
        parts.append(f"  多出 {name}: {where}\n")
    if missing:
        parts.append("  缺失（registry 里有、树里没人打）: " + ", ".join(missing) + "\n")
    return "".join(parts)


def format_non_literal(
    entries: Sequence[NonLiteralPatchTarget], sources: Mapping[str, str]
) -> str:
    """把通道 2 的站点连同那一行源码渲染出来——光有 `(文件, 行号)` 没法定位是哪个变量。"""
    out: List[str] = []
    for filename, lineno in entries:
        lines = sources.get(filename, "").splitlines()
        text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else "<源码不可得>"
        out.append(f"  {filename}:{lineno}: {text}\n")
    return "".join(out)


# ==========================================================================
# 真树扫描缓存（一次会话扫一遍）
# ==========================================================================


@lru_cache(maxsize=4)
def _real_scan(repo_root: Path) -> TreeScan:
    roots = [Path(repo_root) / d for d in LANE_DIRS]
    return scan_test_tree(roots, repo_root=Path(repo_root))


def _files_touched(found: Mapping[str, List[Tuple[str, int]]]) -> Set[str]:
    return {f for sites in found.values() for f, _ in sites}


def _total_occurrences(found: Mapping[str, List[Tuple[str, int]]]) -> int:
    return sum(len(sites) for sites in found.values())


# ==========================================================================
# B1 / B2 —— 真树
# ==========================================================================


def test_b1_real_tree_name_set_equals_the_registry_and_both_loud_channels_are_empty(
    repo_root: Path,
) -> None:
    """B1（L2/S3）：树里被打桩的名字集合 == WI-1 的 registry 键集，且两个「解析不了」通道为空。

    等式，不是包含：少一个名字要和多一个名字一样吵。
    """
    found, non_literal, unresolvable = _real_scan(repo_root)

    # 直接比集合，**不要**把这一条写成 `format_registry_mismatch(...) == ""`：
    # 一个恒返回 `""` 的诊断函数会让这条断言在空扫描结果上也全绿。诊断只负责措辞，
    # 判据在这里。B8/B9 反过来钉诊断的内容。
    surplus = sorted(set(found) - set(OWNERSHIP))
    missing = sorted(set(OWNERSHIP) - set(found))
    assert not surplus and not missing, format_registry_mismatch(found, set(OWNERSHIP))

    assert non_literal == [], f"非字面量打桩目标：{non_literal}"
    assert unresolvable == [], (
        f"这些打桩点的目标对象解析不出来，而属性名在名单上：{unresolvable}。"
        "它们既没被算进名单，也没报过错——名单会短一截而全绿"
    )


def test_b2_real_tree_reaches_the_three_files_the_grep_missed_and_clears_the_floor(
    repo_root: Path,
) -> None:
    """B2（L2/S2）：三个 grep 漏掉的文件都扫得到，体量不是残根。"""
    found, _non_literal, _unresolvable = _real_scan(repo_root)
    touched = _files_touched(found)

    for path, shape in (
        ("tests/unit/test_settings_no_preference_loss.py", "多行调用（:104-110）"),
        ("tests/unit/test_fixture_damaged_bookdir.py", "别名 web_server + 多行"),
        ("tests/contract/test_health_route.py", "字符串目标（:33，全树唯一一处）"),
    ):
        assert path in touched, (
            f"{path} 没被扫到——它是行级 grep 漏掉的那三个之一（{shape}）。"
            f"扫到的文件：{sorted(touched)}"
        )

    assert ("tests/contract/test_health_route.py", 33) in found.get("BOOKS_DIR", []), (
        "字符串目标形状 `setattr(\"reader3_app.web.server.BOOKS_DIR\", …)` 没被算进 "
        f"BOOKS_DIR：{found.get('BOOKS_DIR')}"
    )
    assert ("tests/unit/test_fixture_damaged_bookdir.py", 107) in found.get("BOOKS_DIR", []), (
        "模块别名 `web_server` 下的打桩点没被算进 BOOKS_DIR："
        f"{found.get('BOOKS_DIR')}"
    )

    total = _total_occurrences(found)
    assert total >= MIN_OCCURRENCES and len(touched) >= MIN_TOUCHED_FILES, (
        f"扫到 {total} 处 / {len(touched)} 个文件，低于 2026-09-07 的实测基线 "
        f"{MIN_OCCURRENCES}/{MIN_TOUCHED_FILES}——扫描器丢了某一类形状"
    )


# ==========================================================================
# B3 —— 三种形状 + context manager 句柄
# ==========================================================================

#: 每一种在真树里出现过的拼法各来一遍。**写成字符串**，不是活代码：B1 扫的就是这个文件。
_B3_SRC = (
    "import reader3_app.web.server as srv\n"                       # 1
    "from reader3_app.web import server as web_server\n"           # 2
    "from reader3_app.web import server\n"                         # 3
    "\n"                                                           # 4
    "def a(monkeypatch):\n"                                        # 5
    '    monkeypatch.setattr(server, "BOOKS_DIR", "x")\n'          # 6
    "    monkeypatch.setattr(\n"                                   # 7
    "        server,\n"                                            # 8
    '        "book_uuid_resolver",\n'                              # 9
    "        object(),\n"                                          # 10
    "    )\n"                                                      # 11
    '    monkeypatch.setattr(server, "AI_WORKER_STOP_TIMEOUT_S", 0.2, raising=False)\n'  # 12
    '    monkeypatch.setattr("reader3_app.web.server.load_ai_settings", dict)\n'         # 13
    '    monkeypatch.setattr(srv, "search_book", None)\n'          # 14
    '    monkeypatch.setattr(web_server, "search_library", None,)\n'  # 15
    "\n"                                                           # 16
    "def b():\n"                                                   # 17
    "    with pytest.MonkeyPatch.context() as mp:\n"               # 18
    '        mp.setattr(server, "ai_queue", None)\n'               # 19
    '        mp.delattr(server, "choose_routing")\n'               # 20
)

#: 多行调用的 `setattr(` 在第 7 行，字符串字面量 `"book_uuid_resolver"` 在第 9 行。
_B3_MULTILINE_CALL_LINE = 7


def test_b3_all_three_shapes_plus_the_context_manager_form_are_collected() -> None:
    """B3（L2/S3）：对象形状 / 字符串目标 / 模块别名 / `mp.setattr` / 多行 / 尾逗号 / delattr。"""
    sites, non_literal, unresolvable = extract_patch_targets(_B3_SRC, "<syn>")

    assert {name for name, _ in sites} == {
        "BOOKS_DIR",
        "book_uuid_resolver",
        "AI_WORKER_STOP_TIMEOUT_S",
        "load_ai_settings",
        "search_book",
        "search_library",
        "ai_queue",
        "choose_routing",
    }, (
        f"少抽/抽错了：{sorted({n for n, _ in sites})}。"
        "`monkeypatch.` 前缀的正则会丢 mp.setattr 与 delattr；单行匹配会丢那个四行调用；"
        "只认 ast.Name 首参会丢字符串目标；只认 `from … import server` 会丢两个别名"
    )
    assert dict(sites)["book_uuid_resolver"] == _B3_MULTILINE_CALL_LINE, (
        f"多行调用报的行号是 {dict(sites)['book_uuid_resolver']}，应当是 setattr 调用所在的第 "
        f"{_B3_MULTILINE_CALL_LINE} 行，而不是字符串字面量所在的第 9 行"
    )
    assert (non_literal, unresolvable) == ([], []), (non_literal, unresolvable)


# ==========================================================================
# B4 —— 不许被收进来的打桩点
# ==========================================================================

_B4_HEADER = (
    "import reader3_app.reader3 as reader3\n"
    "from reader3_app.web import server\n"
    "\n"
)

_B4_CLASSES: Tuple[Tuple[str, str, str], ...] = (
    (
        "attr_of_a_server_attribute",
        "def t(monkeypatch, rec):\n"
        '    monkeypatch.setattr(server.ai_queue, "release", rec)\n',
        "打的是 server.ai_queue 这个对象的属性，不是 server 模块的属性"
        "（真树：tests/unit/test_ai_queue_lease.py:211）。收进来的话名单里会多出 release",
    ),
    (
        "attr_of_the_resolver",
        "def t(monkeypatch, p):\n"
        '    monkeypatch.setattr(server.book_uuid_resolver, "books_dir", p)\n',
        "同上（真树：tests/unit/test_settings_no_preference_loss.py:110）。"
        "收进来的话名单里会多出 books_dir",
    ),
    (
        "a_different_module",
        "def t(monkeypatch, guarded):\n"
        '    monkeypatch.setattr(reader3, "process_epub", guarded)\n',
        "目标解析到的是另一个模块（真树：tests/unit/conftest.py:118）。"
        "判别式必须是**解析出来的模块身份**，不是首参拼写成不成 `server`",
    ),
    (
        "string_target_of_a_different_module",
        "def t(monkeypatch, f):\n"
        '    monkeypatch.setattr("reader3_app.search_service.load_book_cached", f)\n',
        "字符串目标里的模块段不是 reader3_app.web.server。"
        "注意 load_book_cached 在名单上——按名字匹配的实现会在这里当场把它收进去",
    ),
    (
        "local_rebind_shadows_the_import",
        "def t(monkeypatch):\n"
        "    server = FakeThing()\n"
        '    monkeypatch.setattr(server, "BOOKS_DIR", "x")\n',
        "函数内 `server = FakeThing()` 遮蔽了模块级 import：解析得到，但不是 server 模块。"
        "把它和「什么都解析不到」合并会让它掉进通道 3（BOOKS_DIR 在名单上），当场红",
    ),
)


@pytest.mark.parametrize("label,body,why", _B4_CLASSES, ids=[c[0] for c in _B4_CLASSES])
def test_b4_each_non_collection_class_stays_silent(label: str, body: str, why: str) -> None:
    """B4（L2/S3）：五类不许被收的打桩点，逐类断言，失败信息带真树出处。"""
    result = extract_patch_targets(_B4_HEADER + body, "<syn>")
    assert result == ([], [], []), f"{label}：{why}。实得 {result}"


def test_b4_the_five_classes_together_yield_nothing_on_any_channel() -> None:
    """B4（L2/S3）：五类写在同一份源码里，顺序交互也不许把任何一个通道弄出东西。"""
    source = _B4_HEADER + "\n".join(body for _label, body, _why in _B4_CLASSES)
    result = extract_patch_targets(source, "<syn>")
    assert result == ([], [], []), f"扫描器把非 server 模块的打桩点也算进来了：{result}"


# ==========================================================================
# B5 —— 非字面量属性名
# ==========================================================================

_B5_SRC = (
    "from reader3_app.web import server\n"    # 1
    "\n"                                      # 2
    "def t(monkeypatch, name_var):\n"         # 3
    "    monkeypatch.setattr(server, name_var, 1)\n"  # 4
)


def test_b5_non_literal_attribute_name_is_reported_and_lands_in_exactly_one_channel(
    repo_root: Path,
) -> None:
    """B5（L4/S2）：合成的违规源码报进通道 2、且只报一次；真树上零处。"""
    names, non_literal, unresolvable = extract_patch_targets(_B5_SRC, "<syn>")

    assert non_literal == [("<syn>", 4)], (
        "非字面量属性名被静默跳过了——名单会短一截而全绿，正是这道锁要防的事。"
        f"实得 {non_literal}"
    )
    assert (names, unresolvable) == ([], []), (
        "同一个打桩点被记进了不止一个通道，两条断言会互相掩护。"
        f"实得 names={names} unresolvable={unresolvable}"
    )
    message = format_non_literal(non_literal, {"<syn>": _B5_SRC})
    assert "name_var" in message, (
        f"通道 2 的诊断没说清是哪个变量当了属性名，定位不到现场：{message!r}"
    )

    _found, real_non_literal, _unresolvable = _real_scan(repo_root)
    assert real_non_literal == [], (
        f"树里出现了非字面量打桩目标，这道锁从此不再完整：{real_non_literal}"
    )


# ==========================================================================
# B6 / B7 —— 两条律
# ==========================================================================

_ALIASES = ("server", "srv", "web_server", "s")
_IMPORT_FORMS = ("from", "import_as")
_HANDLES = ("monkeypatch", "mp")
_RAISING = ("", "raising=False", "raising=True")
_LAYOUTS = ("one_line", "split_after_paren", "one_arg_per_line", "trailing_comma")
_INDENTS = (0, 4, 8)


def _render_header(alias: str, import_form: str) -> str:
    if import_form == "from":
        return f"from reader3_app.web import server as {alias}\n"
    return f"import reader3_app.web.server as {alias}\n"


def _render_call(
    alias: str, name: str, handle: str, raising: str, layout: str, indent: int
) -> str:
    args = [alias, f'"{name}"', "_value"]
    if raising:
        args.append(raising)
    pad = " " * indent
    if layout == "one_line":
        body = f"{pad}{handle}.setattr({', '.join(args)})\n"
    elif layout == "trailing_comma":
        body = f"{pad}{handle}.setattr({', '.join(args)},)\n"
    elif layout == "split_after_paren":
        body = f"{pad}{handle}.setattr(\n{pad}    {', '.join(args)}\n{pad})\n"
    else:  # one_arg_per_line
        body = (
            f"{pad}{handle}.setattr(\n"
            + "".join(f"{pad}    {arg},\n" for arg in args)
            + f"{pad})\n"
        )
    if indent == 0:
        return body
    if indent == 4:
        return "def t(monkeypatch, mp, _value):\n" + body
    return "def t(monkeypatch, mp, _value):\n    if True:\n" + body


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    alias=st.sampled_from(_ALIASES),
    import_form=st.sampled_from(_IMPORT_FORMS),
    name=st.sampled_from(sorted(OWNERSHIP)),
    handle=st.sampled_from(_HANDLES),
    raising=st.sampled_from(_RAISING),
    layout=st.sampled_from(_LAYOUTS),
    indent=st.sampled_from(_INDENTS),
)
def test_b6_law_the_extracted_name_does_not_depend_on_how_the_call_is_spelled(
    alias: str,
    import_form: str,
    name: str,
    handle: str,
    raising: str,
    layout: str,
    indent: int,
) -> None:
    """B6（L2/S4）：格式无关律。任何一种拼法都必须抽出同一个名字。

    这条律被违反的产物是有案底的：任务文档 §1 的 70 处 / 12 个文件。
    """
    rendered = _render_header(alias, import_form) + _render_call(
        alias, name, handle, raising, layout, indent
    )
    sites, non_literal, unresolvable = extract_patch_targets(rendered, "<gen>")
    extracted = {n for n, _ in sites}
    assert extracted == {name}, f"这一种写法抽不出名字（或抽错了）：\n{rendered}\n得到 {extracted}"
    assert (non_literal, unresolvable) == ([], []), (
        f"合法写法掉进了报错通道：\n{rendered}\n{non_literal} / {unresolvable}"
    )


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    alias=st.sampled_from(_ALIASES),
    import_form=st.sampled_from(_IMPORT_FORMS),
    name_a=st.sampled_from(sorted(OWNERSHIP)),
    name_b=st.sampled_from(sorted(OWNERSHIP)),
    layout_a=st.sampled_from(_LAYOUTS),
    layout_b=st.sampled_from(_LAYOUTS),
    handle_a=st.sampled_from(_HANDLES),
    handle_b=st.sampled_from(_HANDLES),
)
def test_b7_law_extraction_is_a_concatenation_homomorphism(
    alias: str,
    import_form: str,
    name_a: str,
    name_b: str,
    layout_a: str,
    layout_b: str,
    handle_a: str,
    handle_b: str,
) -> None:
    """B7（L2/S6）：`extract(a + b) == extract(a) | extract(b)`。结果不许依赖前后文。"""
    header = _render_header(alias, import_form)
    body_a = _render_call(alias, name_a, handle_a, "", layout_a, 0)
    body_b = _render_call(alias, name_b, handle_b, "", layout_b, 0)

    def names_of(source: str) -> Set[str]:
        return {n for n, _ in extract_patch_targets(source, "<gen>")[0]}

    left = names_of(header + body_a)
    right = names_of(header + body_b)
    combined = names_of(header + body_a + body_b)
    assert combined == left | right, f"扫描器的结果依赖前后文：{left} ∪ {right} != {combined}"


# ==========================================================================
# B8 / B9 —— 失败信息的负控（合成树，写成文本）
# ==========================================================================

_SEED_HEADER = "from reader3_app.web import server\n\n"


def _seed(directory: Path, filename: str, patched: Sequence[str]) -> Path:
    """把一棵只含打桩点的合成测试树写成**文本**。绝不在这个模块体里写活的打桩点。"""
    directory.mkdir(parents=True, exist_ok=True)
    body = "".join(f'    monkeypatch.setattr(server, "{n}", 1)\n' for n in patched)
    path = directory / filename
    path.write_text(_SEED_HEADER + "def t(monkeypatch):\n" + body, encoding="utf-8")
    return path


#: `_SEED_HEADER` 两行 + `def t(monkeypatch):` 一行，所以第一个打桩点在第 4 行。
_SEED_FIRST_LINE = 4


def test_b8_negative_control_an_unregistered_name_names_file_and_line(tmp_path: Path) -> None:
    """B8（L4/S2）：多出来的名字必须连 file:line 一起报；干净的树不许报。"""
    bad_root = tmp_path / "bad"
    _seed(bad_root, "seed_bad.py", ["not_in_the_registry"])
    bad_scan, _nl, _ur = scan_test_tree([bad_root], repo_root=bad_root)
    message = format_registry_mismatch(bad_scan, set(OWNERSHIP))

    assert "not_in_the_registry" in message, message
    assert "seed_bad.py" in message, message
    assert f":{_SEED_FIRST_LINE}" in message, (
        f"失败信息里没有行号——只打印 `found != expected` 的版本会让 B1 在实战里毫无用处：{message}"
    )

    clean_root = tmp_path / "clean"
    _seed(clean_root, "seed_clean.py", ["BOOKS_DIR"])
    clean_scan, _nl2, _ur2 = scan_test_tree([clean_root], repo_root=clean_root)
    assert format_registry_mismatch(clean_scan, {"BOOKS_DIR"}) == "", (
        "干净的合成树也报了红——B1 的失败信息不可信"
    )


def test_b9_a_missing_name_is_as_loud_as_a_surplus_one(tmp_path: Path) -> None:
    """B9（L4/S2）：19/20 的树必须报出第 20 个名字。放宽成 `<=` 会让这条红。"""
    all_names = sorted(OWNERSHIP)
    short_root = tmp_path / "short"
    _seed(short_root, "seed_short.py", [n for n in all_names if n != "_egress_post_stream"])
    short_scan, _nl, _ur = scan_test_tree([short_root], repo_root=short_root)
    message = format_registry_mismatch(short_scan, set(OWNERSHIP))

    assert "_egress_post_stream" in message, message
    assert "缺失" in message, (
        "少一个名字没有被说成「缺失」——把比较放宽成 `set(found) <= set(OWNERSHIP)` 的版本"
        f"会在今天全绿，并且默默接受最后一处打桩点被删掉：{message}"
    )

    full_root = tmp_path / "full"
    _seed(full_root, "seed_full.py", all_names)
    full_scan, _nl2, _ur2 = scan_test_tree([full_root], repo_root=full_root)
    assert format_registry_mismatch(full_scan, set(OWNERSHIP)) == "", (
        "打满 20 个名字的合成树被报成不一致——B9 的上半段是假的"
    )


# ==========================================================================
# B10 —— 走查真的覆盖了这条 lane
# ==========================================================================


def test_b10_the_tree_scan_really_reads_the_lane(repo_root: Path) -> None:
    """B10（L1/S1）：两个目录都走到、conftest.py 收进来、__pycache__ 排除掉。"""
    files = iter_test_files([repo_root / d for d in LANE_DIRS])
    relative = {p.relative_to(repo_root).as_posix() for p in files}

    assert len(files) >= MIN_SCANNED_FILES, (
        f"只扫到 {len(files)} 个文件。扫了 0 个文件时 set(found)==set()，"
        "B1 只会在 registry 也为空时才红"
    )
    for conftest in ("tests/unit/conftest.py", "tests/contract/conftest.py"):
        assert conftest in relative, (
            f"{conftest} 没被扫到——tests/contract/conftest.py 一个文件就占了 76 处里的 6 处"
        )
    assert not any("__pycache__" in p.parts for p in files), "走查进了 __pycache__"


# ==========================================================================
# B11 —— 解析不出目标的那一格
# ==========================================================================

_B11_TEMPLATE = (
    "import importlib.util\n"                                            # 1
    "\n"                                                                 # 2
    "def _load():\n"                                                     # 3
    "    spec = importlib.util.spec_from_file_location('x', P)\n"        # 4
    "    ...\n"                                                          # 5
    "    return mod\n"                                                   # 6
    "\n"                                                                 # 7
    "def t(monkeypatch):\n"                                              # 8
    "    mod = _load()\n"                                                # 9
    '    monkeypatch.setattr(mod, "{attr}", None)\n'                     # 10
)

_B11_CALL_LINE = 10


def test_b11_unresolvable_target_with_a_registry_name_is_reported_house_idiom_is_not(
    repo_root: Path,
) -> None:
    """B11（L4/S2）：同一种句法，属性名在名单上就报、不在名单上就静默；真树上零处。"""
    on_registry = extract_patch_targets(
        _B11_TEMPLATE.format(attr="_call_provider"), "<syn>"
    )
    names, non_literal, unresolvable = on_registry

    assert unresolvable == [("<syn>", _B11_CALL_LINE, "_call_provider")], (
        "目标对象解析不出来、属性名却在名单上——这个打桩点既没进名单也没报错，"
        "锁看起来是满的、实际短一截。这是 B5 的镜像：B5 管『名字是变量』，本条管『目标是变量』。"
        f"实得 {unresolvable}"
    )
    assert (names, non_literal) == ([], []), (
        f"同一个打桩点落进了不止一个通道：names={names} non_literal={non_literal}"
    )

    house_idiom = extract_patch_targets(_B11_TEMPLATE.format(attr="ROOT"), "<syn2>")
    assert house_idiom == ([], [], []), (
        '把 setattr(mod, "ROOT", ...) 这类动态加载句柄一律报出来，这道锁落地当天就会在 '
        "test_lint_e2e_selectors_closed_list.py / test_lint_testid_naming_uniqueness.py / "
        "test_coverage_gate_failclosed.py / test_provider_response_parsing.py / "
        f"test_markexpr_guard.py 上红十四次，然后被删掉——收窄到「属性名在名单上」才是它能"
        f"活下来的形状。实得 {house_idiom}"
    )

    _found, _non_literal, real_unresolvable = _real_scan(repo_root)
    assert real_unresolvable == [], (
        f"真树上出现了「目标解析不出来 + 属性名在名单上」的打桩点：{real_unresolvable}。"
        "这是启发式棘轮不是证明：如果它确实是在给另一个恰好也有同名属性的模块打桩，"
        "代价是一行分诊和一句注释；它替换掉的漏报代价是一把默默变短的锁"
    )


# --------------------------------------------------------------------------
# B12 —— 关键字拼法不许无声消失（终审 M1）。 L4 / S2
# --------------------------------------------------------------------------

_B12_KW_ONLY = '''
import reader3_app.web.server as server

def test_x(monkeypatch):
    monkeypatch.setattr(target=server, name="BOOKS_DIR", value=1)
'''

_B12_MIXED = '''
import reader3_app.web.server as server

def test_x(monkeypatch):
    monkeypatch.setattr(server, name="BOOKS_DIR", value=1)
'''


def test_b12_the_keyword_argument_spelling_does_not_vanish() -> None:
    """`setattr(target=…, name=…)` 的 `node.args` 是空的。

    终审把这条列为 M1：这种站点原先三个通道一个都不进——既不是 PatchSite，也不是
    NonLiteralPatchTarget，也不是 UnresolvableTarget，它就是没了。这道锁的全部卖点是
    「注册表是完整的」，而一处改拼法的打桩就能从它眼前消失，是这个卖点最直接的反例。

    今天真树上零处，所以这是棘轮而不是修 bug；它的价值在于把「无声跳过」这条路提前堵上。
    """
    for label, src in (("全关键字", _B12_KW_ONLY), ("混合", _B12_MIXED)):
        names, non_literal, unresolvable = extract_patch_targets(src, "<syn>")
        assert [n for n, _ in names] == ["BOOKS_DIR"], (
            f"{label}拼法的打桩点没被收集：names={names} non_literal={non_literal} "
            f"unresolvable={unresolvable}。三个通道一个都不进，就是通道 2/3 被引进来"
            "要消灭的那种无声跳过"
        )
        assert (non_literal, unresolvable) == ([], []), (
            f"{label}拼法落进了不止一个通道：non_literal={non_literal} unresolvable={unresolvable}"
        )


# --------------------------------------------------------------------------
# B13 —— `_scope_bindings` 流不敏感这个洞的特征化（终审 M2）。 L2 / S2
# --------------------------------------------------------------------------

_B13_SAME_SCOPE_IMPORT_THEN_REBIND = '''
def test_x(monkeypatch):
    import reader3_app.web.server as server
    monkeypatch.setattr(server, "BOOKS_DIR", 1)
    server = object()
'''

_B13_B4C5_MODULE_IMPORT_LOCAL_FAKE = '''
import reader3_app.web.server as server

def test_x(monkeypatch):
    server = object()
    monkeypatch.setattr(server, "BOOKS_DIR", 1)
'''


def test_b13_the_flow_insensitivity_hole_is_characterized_not_claimed_closed() -> None:
    """**特征化，不是判决。** 这条钉的是今天的行为，包括它错的那一半。

    上面那份源码里 `setattr` 那一行的 `server` 真的是模块（赋值在它后面），所以那是一处
    真打桩点，而扫描器把它整个丢了——正是 B12 要消灭的那种无声跳过。下面那份是 B4 类 5，
    丢掉它是**对的**。两份在 `_scope_bindings` 的返回值里无法区分，所以今天它们同命。

    这条用例的作用是：谁把 `resolve` 改成能分辨作用域层次，这里会红，而红的方向是好的——
    到那时把上面那半改成断言它落进 `unresolvable`（而不是 `collected`：顺序敏感的解析
    值得一个响亮的「我不确定」，不值得一个安静的结论）。
    """
    hole = extract_patch_targets(_B13_SAME_SCOPE_IMPORT_THEN_REBIND, "<b13-hole>")
    assert hole == ([], [], []), (
        f"扫描器现在能看见同作用域 import-then-rebind 了：{hole}。这是改进——"
        "把本条改成断言它落进 unresolvable 通道，并更新 _scope_bindings 的「已知的洞」一段"
    )

    b4c5 = extract_patch_targets(_B13_B4C5_MODULE_IMPORT_LOCAL_FAKE, "<b13-b4c5>")
    assert b4c5 == ([], [], []), (
        f"B4 类 5（函数内 server = FakeThing()）不该被当成 server 打桩点：{b4c5}"
    )
