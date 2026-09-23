"""017 WI-2（审计 #2）：每一处 provider 出口都必须**带着预算**出门。

`tests/unit/test_provider_retry.py` 的 R14–R20 守的是 `_call_provider` **收到**预算
之后的行为。这份文件守另一半：调用点有没有**交**预算。两件事分开守是有原因的——
把 `deadline=` / `should_stop=` 从某个调用点删掉，R14–R20 一条都不会红，那个路由
却悄悄退回审计 #2 描述的状态：504 已经交给客户端，重试还在发车。

**这是一条结构断言，不是行为断言**，说清楚它证明什么、不证明什么：

* 它证明：`routers/` 下每一处 `_server._call_provider(...)` 的关键字实参里同时有
  `deadline` 与 `should_stop`。
* 它**不**证明：传下去的那两个值是对的（比如 deadline 取自另一个请求的预算），
  也不证明 `should_stop` 真的会被翻起来。那两件事由 R14–R20 与
  `test_ai_queue_lease.py` 的 Q 系列各守一头。

选结构断言而不是「起一个真路由、掐表等 504」是个取舍：后者要真睡一秒多，且它红起来
的样子和负载抖动一模一样——009 欠账 #43 记着这种不可归因的红要花多少功夫才排得掉。

豁免一处，写下来而不是让它悄悄生效：`routers/settings.py` 的连通性自测显式传
`max_retries=0`（见 test_provider_retry.py R12），压根没有重试循环可停，而它的超时
就是用户点「测试」时愿意等的那一段。下面的 `_EXEMPT` 把它连同理由一起钉住——豁免
项改名或消失时这份文件会红，而不是默默放行。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = REPO_ROOT / "src" / "reader3_app" / "web" / "routers"

REQUIRED_KWARGS = ("deadline", "should_stop")

#: 文件相对路径 -> 豁免理由。**必须逐条有理由**；空理由等于没豁免。
_EXEMPT: Dict[str, str] = {
    "settings.py": (
        "连通性自测显式 max_retries=0（R12），没有重试循环可停；它的 timeout 就是"
        "用户点「测试」时愿意等的那一段，再叠一层预算只会让它提前失败。"
    ),
}


def _call_sites() -> List[Tuple[Path, ast.Call]]:
    """找出 `routers/` 下每一处 `_server._call_provider(...)`。"""
    found: List[Tuple[Path, ast.Call]] = []
    for path in sorted(ROUTERS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # `run_in_threadpool(_server._call_provider, ...)`：出口是**第一个位置实参**，
            # 不是被调用的那个名字。两种形状都要认。
            target = node.func
            is_direct = (
                isinstance(target, ast.Attribute) and target.attr == "_call_provider"
            )
            passes_as_arg = any(
                isinstance(a, ast.Attribute) and a.attr == "_call_provider"
                for a in node.args
            )
            if is_direct or passes_as_arg:
                found.append((path, node))
    return found


def test_每一处_provider_出口都在_routers_下被找得到() -> None:
    """先证明扫描器没扫空。

    扫空的话下面那条会「全绿地」什么也没检查——审计 #21/#29 记的正是这种闸。
    """
    sites = _call_sites()
    assert len(sites) >= 5, (
        f"只在 routers/ 下找到 {len(sites)} 处 provider 出口，太少了。"
        "要么调用形状变了（扫描器该跟着改），要么出口搬走了（那更要知道）。"
    )


def test_每一处_provider_出口都带着_deadline_与_should_stop() -> None:
    offenders: List[str] = []
    for path, call in _call_sites():
        rel = path.relative_to(ROUTERS_DIR).as_posix()
        if rel in _EXEMPT:
            continue
        names = {kw.arg for kw in call.keywords if kw.arg}
        missing = [k for k in REQUIRED_KWARGS if k not in names]
        if missing:
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno} 缺 {missing}")

    assert not offenders, (
        "这些 provider 出口没有带预算出门，等于退回审计 #2 的状态"
        "（504 已经返回，重试还在发车）：\n  " + "\n  ".join(offenders)
    )


def test_豁免名单里的文件确实存在且理由非空() -> None:
    """豁免项必须是活的。

    文件改名或删掉之后，一条留在名单里的死豁免会悄悄放行一个新的调用点。
    """
    for rel, reason in _EXEMPT.items():
        assert (ROUTERS_DIR / rel).is_file(), f"豁免名单里的 {rel} 已经不在了"
        assert reason.strip(), f"{rel} 的豁免没有写理由"
