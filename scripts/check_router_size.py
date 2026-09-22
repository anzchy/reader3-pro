#!/usr/bin/env python3
"""router 体量门禁 —— 让「每个 router < 500 行」第一次真的有牙。

**为什么需要这个脚本。** 「每个 router < 500 行」写在
`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §8 的
Phase 2a 退出门槛里，从写下那天（2026-08-16）到 2026-09-19 实测为止，
**`.github/workflows/*.yml` 与 `scripts/*.py` 里没有任何一处在检查它**。
它一直只是计划表里的一句散文。散文门槛有两个后果，第二个更坏：

1. 没人知道有没有达标，只能人肉 `wc -l`，而人肉的结果不进 CI、不留证据；
2. **它的豁免永远不会到期。** 011 §5 给 `routers/ai/chat.py` 开了一条
   具名豁免，理由是「里面有一个 433 行的单函数」。如果没有机器在测量，
   那个函数哪天被分解了，豁免也不会有人回来收 —— 门槛就这样一格一格松下去。
   本脚本把到期条件写成一条断言（见 `_check_exemption_still_earned`）：
   **豁免的理由一旦不成立，脚本转红并要求删掉豁免。**

**判据落在模块上，不落在包上。** 两条规则取并集：

- **R1** `web/routers/` 下每一个 `.py`，无论它声不声明路由。
  这条堵的是「把代码倒进 `_helpers.py` / `utils.py` 只为压线」——
  倒进去的那个文件一样被数。
- **R2** `web/` 下任何**声明了路由**的模块。这条堵的是
  「拆分没做完，路由还留在 `server.py` 里」，也堵「聚合入口只有几十行」
  充当达标证据 —— `__init__.py` 只要不声明路由就不被 R2 数，但它在
  `routers/` 下，被 R1 数。

**豁免写在本文件里，不写进外部配置。** `0c1c8a2` 的教训还热着：那次把阈值搬进
`.claude/tdd-guardian/config.json` 的 `thresholds` 子对象去迁就 tdd-guardian 插件，
`scripts/check_coverage_gate.py` 还在读顶层键，于是八条逐文件门槛里七条静默读成 0。
**两个读者、一份配置、两种键形状**，结局是漂移。这条门槛只有一个读者，
配置就放在读者旁边，改的人一眼看得见。

**零依赖，只用标准库**——与 `scripts/` 下其余脚本同口径。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = REPO_ROOT / "src" / "reader3_app" / "web"
ROUTERS_ROOT = WEB_ROOT / "routers"

#: 通用上限。计划 §8 Phase 2a 退出门槛的原文。
DEFAULT_MAX_LINES = 500

#: FastAPI 路由装饰器的方法名。`@app.get(...)` / `@router.post(...)` 都是
#: `ast.Attribute`，取 `.attr` 即可，不关心前面挂的是 `app` 还是 `router` ——
#: 关心了就会在改名那天漏判。
HTTP_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
)


class Exemption:
    """一条具名豁免。

    `min_function_lines` 是**到期条件**，不是描述：豁免的存在理由是
    「这个文件里有一个大到搬不走的单函数」。一旦文件里最大的顶层函数
    缩到这个数以下，理由就不成立了，脚本必须转红并要求删掉本条。
    """

    def __init__(
        self, rel_path: str, max_lines: int, min_function_lines: int, reason: str
    ) -> None:
        self.rel_path = rel_path
        self.max_lines = max_lines
        self.min_function_lines = min_function_lines
        self.reason = reason


#: **唯一具名例外。** 裁定与推导见 011 §5「豁免条款」，此处不重述理由全文。
#: N 的来源：不可搬走的正文实测 493 行（`api_ai_question` 433
#: ＋ 它独占的 `_stop_stream_worker` 60），余量给 import / docstring /
#: `APIRouter` 声明 / 路由装饰器。**只许下调，不许上调**（这条规则本身由
#: `tests/unit/test_router_size_gate.py` 末尾那条上界断言执行，不靠自觉）。
#:
#: 2026-09-19：拆分做完，chat.py **实测 547 行**，于是 N 从 560 下调到 550。
#: 原先的 67 行余量是拆分**之前**估的，事后看多估了 54 行——这正是「先定 N
#: 再搬家」的意义：560 不是照着结果填的。留 3 行而不是钉死在 547，是因为这条
#: 豁免要咬的是**函数拆没拆**（`min_function_lines`），不是「谁多写了一行注释」；
#: 而 lint 是仅发版触发的，为一行注释在发版那天转红，代价和收益不成比例。
EXEMPTIONS = (
    Exemption(
        rel_path="src/reader3_app/web/routers/ai/chat.py",
        max_lines=550,
        min_function_lines=400,
        reason=(
            "POST /api/ai/question 是一个 433 行的单函数（9 条顶层语句，"
            "其余全是 SSE 嵌套闭包）＋ 它独占的 _stop_stream_worker 60 行。"
            "把这条路由单独放一个文件、别的什么都不放，仍然过不了 500。"
            "拆它属于 Phase 2b 的 B 方案，前置条件是 CLAUDE.md:122 先结清。"
        ),
    ),
)


def declares_routes(tree: ast.AST) -> bool:
    """模块里有没有 FastAPI 路由装饰器。"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            call = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(call, ast.Attribute) and call.attr in HTTP_METHODS:
                return True
    return False


def largest_top_level_function(tree: ast.Module) -> int:
    """最大顶层函数的行数（`def` 那行到函数末尾，含嵌套闭包）。

    只看顶层：嵌套函数的跨度本来就包在外层里，再数一遍只会把同一段代码
    算两次。空模块返回 0。
    """
    spans = [
        node.end_lineno - node.lineno + 1
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
    ]
    return max(spans, default=0)


def count_lines(path: Path) -> int:
    """`wc -l` 口径：数换行符。门槛是拿 `wc -l` 谈的，就得跟它一致。"""
    return path.read_text(encoding="utf-8").count("\n")


def modules_under_test(web_root: Path) -> list[Path]:
    """R1 ∪ R2，按路径排序去重。"""
    routers_root = web_root / "routers"
    selected: set[Path] = set()

    if routers_root.is_dir():
        selected.update(p for p in routers_root.rglob("*.py"))

    for path in web_root.rglob("*.py"):
        if path in selected:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            # 语法错的文件不是本门禁该管的事，但也不能当它不存在 ——
            # 让它按「不声明路由」处理，真正的语法错误由 lint/测试炸出来。
            continue
        if declares_routes(tree):
            selected.add(path)

    return sorted(selected)


def _check_exemption_still_earned(
    exemption: Exemption, tree: ast.Module
) -> str | None:
    """豁免的理由还成立吗。不成立就返回一句要求删除它的话。"""
    biggest = largest_top_level_function(tree)
    if biggest >= exemption.min_function_lines:
        return None
    return (
        f"豁免已到期：{exemption.rel_path} 里最大的顶层函数只有 {biggest} 行"
        f"（< {exemption.min_function_lines}），开这条豁免的理由不再成立。"
        f"**删掉 scripts/check_router_size.py 里的这条 Exemption**，"
        f"让该文件回到 {DEFAULT_MAX_LINES} 行门槛。"
    )


def check(repo_root: Path) -> list[str]:
    """返回失败信息列表；空列表 = 通过。"""
    web_root = repo_root / "src" / "reader3_app" / "web"
    failures: list[str] = []
    by_path = {e.rel_path: e for e in EXEMPTIONS}
    used: set[str] = set()

    if not web_root.is_dir():
        return [f"找不到 {web_root} —— 门禁量不到东西，判 FAIL 而不是跳过。"]

    for path in modules_under_test(web_root):
        rel = path.relative_to(repo_root).as_posix()
        lines = count_lines(path)
        exemption = by_path.get(rel)
        limit = exemption.max_lines if exemption else DEFAULT_MAX_LINES

        if exemption is not None:
            used.add(rel)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            expired = _check_exemption_still_earned(exemption, tree)
            if expired:
                failures.append(expired)

        if lines > limit:
            tag = f"（具名豁免上限 {limit}）" if exemption else ""
            failures.append(f"FAIL  {rel}  {lines} 行 > {limit}{tag}")
        else:
            print(f"PASS  {rel:<62} {lines:>5} 行 <= {limit}")

    # 指向不存在文件的豁免判 FAIL，不跳过 —— 与 `check_coverage_gate.py` 里
    # 「匹配到零个文件的 glob 判 FAIL」同一条道理：一条指向已删除/改名文件的
    # 豁免，是一条永远不会到期的豁免。
    for rel in sorted(set(by_path) - used):
        failures.append(
            f"豁免指向的文件不存在：{rel}。改名或删除之后请同步删掉这条 Exemption —— "
            f"量不到的豁免判 FAIL，不判跳过。"
        )

    return failures


def main() -> int:
    failures = check(REPO_ROOT)
    if failures:
        print("\nrouter 体量门禁未通过：", file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        print(
            "\n门槛定义：计划 §8 Phase 2a 退出门槛；豁免条款：011 §5。",
            file=sys.stderr,
        )
        return 1
    print(f"\nrouter 体量门禁通过（通用上限 {DEFAULT_MAX_LINES} 行，"
          f"具名豁免 {len(EXEMPTIONS)} 条）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
