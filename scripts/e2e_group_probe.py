"""`scripts/lint_e2e_groups.py` 专用的 pytest 探针插件：一次收集，吐出每个 item 的 marker 集合。

只被守卫以 `-p e2e_group_probe` 加载（`PYTHONPATH` 指到 `scripts/`），不注册进 pyproject，
不参与任何 lane。理由是成本：矩阵允许「对五个组 marker 各跑一次 `-m` 收集再取交集」，
但那是 **6 次** pytest 冷启动（每次约 0.5–0.8s）；变异树用例要在十几棵树上各做一遍，
6× 会把 unit lane 从秒级拖到分钟级。一次收集 ＋ 一个探针把它压回 1×。

输出格式（每个 item 一行，前缀固定，其余行由 `-q` 的常规输出产生，守卫只读带前缀的行）：

    E2E_GROUP_PROBE\t<nodeid>\t<marker1,marker2,...>

`iter_markers()` 取的是 item 上**全部**生效的 marker（模块级 `pytestmark`、类级、函数级
装饰器、`pytest.param(marks=…)`），所以「一条用例同时带两个组 marker」在这里可见。
"""

from __future__ import annotations

PREFIX = "E2E_GROUP_PROBE"


def pytest_collection_finish(session):  # type: ignore[no-untyped-def]
    for item in session.items:
        names = sorted({m.name for m in item.iter_markers()})
        print(f"{PREFIX}\t{item.nodeid}\t{','.join(names)}")
