"""Layer 1 of the route contract: the API v1 inventory snapshot.

Definition site: `docs/plans/20260816-tech-stack-migration/tasks/008-test-safety-net.md`
§4 layer 1 and §8. The snapshot itself lives in `routes.snapshot` next to this file
and carries its own header explaining what it includes and why.

This is the mechanical enforcer of the v1 freeze. Phase 2 splits `web/server.py`
into routers; if a router lands under the wrong `prefix`, or a route is dropped in
the move, this test is the thing that says so — before the TypeScript frontend of
Phase 4 discovers it against a running server.

It deliberately does **not** assert a count. A count says "something changed";
a set difference says *what* changed, which is the only form a reviewer can act on.
"""

from __future__ import annotations

from pathlib import Path

from starlette.routing import Mount

from reader3_app.web.server import app

SNAPSHOT_PATH = Path(__file__).resolve().parent / "routes.snapshot"

#: Starlette synthesises these on every route; they carry no contract of their own.
_IMPLICIT_METHODS = frozenset({"HEAD", "OPTIONS"})


def current_inventory() -> set[str]:
    """Normalise `app.routes` into the same `METHOD /path` lines the snapshot holds."""
    lines: set[str] = set()
    for route in app.routes:
        if isinstance(route, Mount):
            lines.add(f"MOUNT {route.path}")
            continue
        for method in getattr(route, "methods", None) or []:
            if method in _IMPLICIT_METHODS:
                continue
            lines.add(f"{method} {route.path}")
    return lines


def snapshot_inventory() -> set[str]:
    lines: set[str] = set()
    for raw in SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.add(line)
    return lines


def test_路由清单与快照一致():
    live = current_inventory()
    frozen = snapshot_inventory()

    added = sorted(live - frozen)
    removed = sorted(frozen - live)

    assert not (added or removed), (
        "API v1 的路由集合变了。这不是自动修复的地方——先确认这次改动是故意的，"
        "再手工更新 tests/contract/routes.snapshot 并在 PR 描述里写清破坏性与迁移路径"
        "（tasks/008-test-safety-net.md §8）。\n"
        f"  多了（代码里有、快照里没有）: {added or '无'}\n"
        f"  少了（快照里有、代码里没有）: {removed or '无'}"
    )


def test_快照文件本身是排好序的():
    """乱序的快照会让 diff 变噪音，而「diff 里一眼看懂」是这份文件的全部价值。"""
    lines = [
        raw.strip()
        for raw in SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines()
        if raw.strip() and not raw.strip().startswith("#")
    ]
    assert lines == sorted(lines), "routes.snapshot 的正文必须按行文本排序"
    assert len(lines) == len(set(lines)), "routes.snapshot 有重复行"


def test_每条快照行都能解析成方法和路径():
    """守卫上一条：如果解析规则松到什么都能过，前两条测试就会真空通过。"""
    allowed = {"GET", "POST", "PUT", "DELETE", "PATCH", "MOUNT"}
    for line in sorted(snapshot_inventory()):
        method, _, path = line.partition(" ")
        assert method in allowed, f"未知方法 {method!r}（行：{line!r}）"
        assert path.startswith("/"), f"路径必须以 / 开头（行：{line!r}）"
