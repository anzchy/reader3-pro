#!/usr/bin/env python3
"""`tests/e2e/` 分组划分律的**常量定义处 ＋ 执行体**（WI-1 放常量，WI-17 落执行体）。

任务书 §0.5 明写：分组条数「**只允许在 `scripts/lint_e2e_groups.py` 定义/派生一次**，
验收条、守卫脚本、台账产物一律 import」。写死字面量的代价已经付过一次——把
`test_testid_dom_uniqueness.py` 的 7 条漏算成 76，会让 WI-1 的条数断言**在写第一行
009 代码之前就红**，而最省事的修法（删断言或改成 `>=`）恰好把划分律整个掏空。

**划分律（三分，任务书 §0.5）**：`tests/e2e` 的每一个 collected item 恰好落进三类之一——

1. 携带五个组 marker 之一（marker 与所在目录一一对应）；
2. 其模块名在 `UNGROUPED_E2E_MODULES` 白名单里；
3. 以上皆非 ⇒ **违规**。

白名单是唯一的豁免口径，且每一项都必须在本次收集里真的贡献 item——悬空条目等于给下一个
模块预开的门。

**执行体做四件事**（`check_tree`），任一违规即退出码 1，消息点名 nodeid / 文件:行 / 目录：

- 划分律 ＋ 白名单不空转（`partition_violations`）；
- 条数：`baseline_1b` == `EXPECTED_BASELINE_ITEMS`，四个 acceptance 目录各 ==
  `EXPECTED_ACCEPTANCE_PER_DIR[dir]`，白名单 == `EXPECTED_UNGROUPED_ITEMS`；marker ↔ 目录
  一一对应（`count_violations`）；
- skip 轴静态性质（`skip_axis_violations`，纯 AST）：
  * 域 R（`baseline_1b` 的收集可达链：`tests/e2e/conftest.py`、`tests/e2e/helpers.py`、
    `baseline_1b/**`）里**零** skip 构造——`pytest.skip(` / `pytest.importorskip(` /
    `pytest.xfail(` / `pytest.mark.skip` / `skipif` / `xfail`，**函数体与异常处理器里的一并计入**；
  * 四个 acceptance 目录里每个 `test_*.py` **恰好**一个模块级 `pytestmark` 内的
    `pytest.mark.skip(reason=…)`，reason 非空且点名本组的激活阶段（`4B.1` / `P3` / `4A.4` / `2a`），
    模块内再无其他 skip 构造；
  * 五个组目录内没有 `collect_ignore` / `collect_ignore_glob`。

**为什么 skip 检查必须 `ast.walk` 整个模块，不是扫 `Module.body`。** 任务书 §8 G2 的
commit 级护栏点名的那句代码——

    @pytest.fixture(scope="session")
    def live_server(...):
        try:
            proc = _boot()
        except Exception as e:            # 「防御性」，某次 CI 抖动之后加的
            pytest.skip(f"e2e server unavailable: {e}")

在 AST 里的位置是 `Module → FunctionDef → Try → ExceptHandler → Expr → Call`，**深度 5**。
任何只看模块顶层语句或只看 `pytestmark` 赋值的实现都看不见它，而它的后果是 65 条
baseline 全部 skipped、push gate 全绿。「扫顶层」是这类检查最自然、也最常见的写法，
所以把理由写在这里。

**为什么域 R 是「收集可达」而不是「整个 tests/e2e」。** `test_testid_dom_uniqueness.py`
与将来的其他白名单模块**允许**有自己的 skip（它们不计入 1b 门槛，一条环境性 skip 在那里
是合理的）。域写成「收集 `baseline_1b` 时可达的模块」精确对应了「哪些 skip 能把门槛掏空」，
不多不少。下一个人若把它扩成全目录，会被白名单模块的合法 skip 打红。

**收集只跑一次。** 用 `scripts/e2e_group_probe.py` 这个探针插件（`-p e2e_group_probe`）在
一次 `--collect-only` 里吐出每个 item 的 marker 集合，而不是对五个 marker 各跑一次 `-m`：
后者是 6 次 pytest 冷启动，变异树用例要在十几棵树上各做一遍，unit lane 会从秒级拖到分钟级。

**目录布局：五个组目录里既不能有 `__init__.py`，也不能有 `conftest.py`（2026-09-02 实测）。**
`tests/e2e/test_harness_smoke.py` 与 `tests/e2e/test_testid_dom_uniqueness.py` 都写
`from conftest import BOOK_ID`（裸模块名），依赖 pytest 的 prepend 模式把「第一个不含
`__init__.py` 的上层目录」插进 `sys.path`：

- 在 `tests/e2e/` 加 `__init__.py` ⇒ 插入点上移到 `tests/` ⇒ 两处裸 import 当场 ImportError；
- 在**子目录**加 `conftest.py` ⇒ 子目录那个也以顶层模块名 `conftest` 进 `sys.modules`，
  把 `tests/e2e/conftest.py` 挤掉。实测报错是
  `ImportError: cannot import name 'BOOK_ID' from 'conftest' (tests/e2e/baseline_1b/conftest.py)`。

所以任务书验收原文的「有 `__init__.py` **或**明确的 `conftest.py` 归属」两种写法在这里
**都不可用**：目录归属靠 `.gitkeep`（内含指针），组归属靠 item 上的 marker。将来若某组
真需要自己的 fixture，先得把那两处裸 import 改掉，不能反过来。**DEG-S3 的第二个服务进程
就是这样落地的**：spawner 住在 `tests/fixtures/deg_assertions.py`，两个 DEG 模块各自用一个
模块级 fixture 包一层——不是 `acceptance_p3/conftest.py`。
`tests/unit/test_e2e_group_layout.py` 是这条不等价的记录。

**为什么 `EXPECTED_E2E_ITEMS` 必须是派生值，不是字面量。** 全量里有 7 条来自
`test_testid_dom_uniqueness.py`——那是 ADR-0014 的运行期唯一性护栏，与 009 无关。
把总数焊死，等于把那个套件的条数写进 009 的门槛：它将来加一个 parametrize 值，红的
会是 009 的用例，而修法（改总数）与被改的东西毫无关系。派生式只钉三件事：baseline
恰好 65、acceptance 恰好 17、其余 item 的模块必须在白名单里。

**常量的变更史**（改数字必须写理由，不要只覆盖）：

- `EXPECTED_BASELINE_ITEMS` 61 → **65**（2026-09-04，WI-17 / 欠账 #2）。61 是 2026-09-01 矩阵
  按 41 个测试函数推算的 collected 数，**预估，不是实测**；WI-1 起刻意不逐 WI 递增（递增会把
  本文件变成 13 路串行写入点，波内并行当场作废）。各模块的参数化条数在实现中漂移（harness
  自测 9、W-5a 8、K-2 11、K-3 6、X-1 4 …），Wave 6 收口后实测 65。「实测 == 常量」的断言由
  `tests/unit/test_e2e_group_guard.py` 承担，本文件的 `check_tree` 同时执行。
- `EXPECTED_ACCEPTANCE_ITEMS` 14 → **17**（同日，欠账 #14）：R-6 拆 a/b 后 R-6b 三条落进
  `acceptance_4b1`（Wave 4），该目录由 5 变 8。改成按目录定义再求和，是让「哪个目录少了一条」
  在失败消息里直接可读。
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set

# ---------------------------------------------------------------------------
# 常量（唯一定义处）
# ---------------------------------------------------------------------------

#: 五个组 marker，与 `tests/e2e/<marker>/` 目录一一对应（任务书 §0.5 的表是唯一定义处）。
GROUP_MARKERS = (
    "baseline_1b",
    "acceptance_4b1",
    "acceptance_p3",
    "acceptance_4a4",
    "acceptance_2a",
)
BASELINE_MARKER = "baseline_1b"
ACCEPTANCE_MARKERS = GROUP_MARKERS[1:]

# `tests/e2e/baseline_1b/` 下的期望 item 数。**实测值**（变更史见文件头）。
EXPECTED_BASELINE_ITEMS = 65

# 四个 acceptance 目录各自的期望 item 数。合计由此派生，不另写字面量。
#   acceptance_4b1：R-6b ×3（Wave 4）＋ K-1b ＋ K-6b ＋ W-5b ×3（{marker, wavy, underline}，
#                  `toggleMarkerAnnotation` 与 `toggleAnnotation` 是两份独立实现）
#   acceptance_p3 ：DEG-S1…S4 朴素横幅形态
#   acceptance_4a4：DEG-S1…S4 设计规格形态（与 p3 共用断言主体，只换 testid 映射）
#   acceptance_2a ：DEG-S5 写冲突
EXPECTED_ACCEPTANCE_PER_DIR: Dict[str, int] = {
    "acceptance_4b1": 8,
    "acceptance_p3": 4,
    "acceptance_4a4": 4,
    "acceptance_2a": 1,
}
EXPECTED_ACCEPTANCE_ITEMS = sum(EXPECTED_ACCEPTANCE_PER_DIR.values())

# `tests/e2e/` 根目录下**不带组 marker**的模块白名单。这是唯一的豁免口径：不在这里、
# 又没有组 marker 的 item 一律违规。每一项都必须在本次收集里真的贡献 item——悬空条目
# 等于给下一个模块预开的门。
UNGROUPED_E2E_MODULES = {
    # harness spike 的落地证据：Playwright 起得来、能读到 epub.js iframe 内的内容。
    # 它是整条 e2e lane 的存活探针，早于分组存在，不属于任何激活阶段。
    "test_harness_smoke.py",
    # ADR-0014 的运行期唯一性护栏：每个有界 testid 在真实 DOM 里只解析出一个节点。
    # 它守的是选择器口径而不是标注行为，与 009 的五个组正交。
    "test_testid_dom_uniqueness.py",
}

# 上面两个白名单模块在一次 `tests/e2e --collect-only` 里贡献的 item 数。
# 2026-09-02 实测 7（smoke 1 + testid 唯一性 6）。这个数会随 testid 套件自己的增减而变，
# 改它是**正确的修法**；变的是白名单模块的条数，不是 009 的门槛。
EXPECTED_UNGROUPED_ITEMS = 7

# 派生值，不是字面量。见文件头「为什么必须派生」。
EXPECTED_E2E_ITEMS = (
    EXPECTED_BASELINE_ITEMS + EXPECTED_ACCEPTANCE_ITEMS + EXPECTED_UNGROUPED_ITEMS
)

#: skip reason 必须点名激活阶段。每个组只认**自己**的 token；p3 的 token 是字面 `P3`。
PHASE_TOKEN_FOR_DIR: Dict[str, str] = {
    "acceptance_4b1": "4B.1",
    "acceptance_p3": "P3",
    "acceptance_4a4": "4A.4",
    "acceptance_2a": "2a",
}
PHASE_TOKEN_RE = re.compile(r"4B\.1|P3|4A\.4|2a")

_SKIP_CALLS = ("pytest.skip", "pytest.importorskip", "pytest.xfail")
_SKIP_MARKS = ("pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail")
_COLLECT_IGNORE_NAMES = {"collect_ignore", "collect_ignore_glob"}

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
DEFAULT_E2E_DIR = "tests/e2e"
PROBE_PLUGIN = "e2e_group_probe"
PROBE_PREFIX = "E2E_GROUP_PROBE"


# ---------------------------------------------------------------------------
# 收集
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectedItem:
    """一次收集里的一个 item：nodeid、所属模块（相对 root 的 posix 路径）、生效的 marker 集合。"""

    nodeid: str
    module: str
    markers: FrozenSet[str]

    def group_markers(self) -> Set[str]:
        return set(self.markers) & set(GROUP_MARKERS)


class CollectionError(RuntimeError):
    """收集本身失败（import 错、marker 未注册、一条都没收到）。零用例是失败，不是通过。"""


def collect_items(root: Path, e2e_dir: str = DEFAULT_E2E_DIR) -> List[CollectedItem]:
    """在 `root` 下对 `e2e_dir` 跑**一次** `--collect-only`，经探针插件取回每个 item 的 marker 集合。

    不起服务、不起浏览器。退出码 0 且至少一条 item 才算成功；5（一条都没收到）与其他
    非零一律抛 `CollectionError` 并附带输出——「守卫在空集上通过」正是 soak 数空集的发生方式。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SCRIPTS_DIR), env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            e2e_dir,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            PROBE_PLUGIN,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise CollectionError(
            f"`pytest {e2e_dir} --collect-only` 在 {root} 下退出码 {proc.returncode}"
            f"（5 = 一条都没收到，零用例是失败）：\n{out}"
        )
    items: List[CollectedItem] = []
    for line in proc.stdout.splitlines():
        if not line.startswith(PROBE_PREFIX + "\t"):
            continue
        _, nodeid, names = line.split("\t", 2)
        module = nodeid.split("::", 1)[0]
        markers = frozenset(n for n in names.split(",") if n)
        items.append(CollectedItem(nodeid=nodeid, module=Path(module).as_posix(), markers=markers))
    if not items:
        raise CollectionError(f"`pytest {e2e_dir} --collect-only` 在 {root} 下一条 item 都没收到：\n{out}")
    return items


# ---------------------------------------------------------------------------
# 划分律 ＋ 白名单
# ---------------------------------------------------------------------------


def partition_violations(
    items: Sequence[CollectedItem], *, ungrouped_modules: Iterable[str] = UNGROUPED_E2E_MODULES
) -> List[str]:
    """条 (1) 划分：恰好一个组 marker，或模块在白名单里；双 marker 也红。条 (2) 白名单不得空转。"""
    whitelist = set(ungrouped_modules)
    out: List[str] = []
    for it in items:
        groups = it.group_markers()
        if len(groups) >= 2:
            out.append(
                f"[划分律] {it.nodeid} 同时带多个组 marker {sorted(groups)}——一条用例计入两道门槛，两边都会误报"
            )
        elif not groups and Path(it.module).name not in whitelist:
            out.append(
                f"[划分律] {it.nodeid} 没有组 marker，且模块 {Path(it.module).name} 不在 UNGROUPED_E2E_MODULES 白名单里"
                "——第三种状态不存在：要么加组 marker，要么显式登记"
            )
    contributed = {Path(it.module).name for it in items if not it.group_markers()}
    for name in sorted(whitelist - contributed):
        out.append(
            f"[白名单] {name} 在本次收集里一条 item 都没贡献（悬空条目 = 给下一个没人管的模块预开的门）"
        )
    return out


# ---------------------------------------------------------------------------
# 条数 ＋ marker ↔ 目录
# ---------------------------------------------------------------------------


def count_violations(
    items: Sequence[CollectedItem],
    *,
    e2e_dir: str = DEFAULT_E2E_DIR,
    expected_baseline: int = EXPECTED_BASELINE_ITEMS,
    expected_per_dir: Mapping[str, int] = EXPECTED_ACCEPTANCE_PER_DIR,
    expected_ungrouped: Optional[int] = EXPECTED_UNGROUPED_ITEMS,
    ungrouped_modules: Iterable[str] = UNGROUPED_E2E_MODULES,
) -> List[str]:
    """条数守卫 ＋ marker ↔ 目录一一对应。失败消息点名目录与两个数字、或 nodeid。"""
    out: List[str] = []
    e2e = e2e_dir.rstrip("/")
    whitelist = set(ungrouped_modules)

    def in_dir(it: CollectedItem, group: str) -> bool:
        return it.module.startswith(f"{e2e}/{group}/")

    # marker ↔ 目录：住在组目录里的每条必须带且只带该组 marker；带某组 marker 的必须住在该组目录。
    for it in items:
        groups = it.group_markers()
        for g in GROUP_MARKERS:
            if in_dir(it, g) and groups != {g}:
                out.append(
                    f"[marker↔目录] {it.nodeid} 住在 {e2e}/{g}/ 下，组 marker 却是 {sorted(groups)}（应恰好 {{{g!r}}}）"
                )
            if g in groups and not in_dir(it, g):
                out.append(
                    f"[marker↔目录] {it.nodeid} 带 {g} marker，却不住在 {e2e}/{g}/ 下——文件跑错目录"
                )

    n_baseline = sum(1 for it in items if BASELINE_MARKER in it.markers)
    if n_baseline != expected_baseline:
        out.append(
            f"[条数] baseline_1b 实测 {n_baseline} 条，期望 EXPECTED_BASELINE_ITEMS = {expected_baseline}"
        )
    for group, expected in expected_per_dir.items():
        n = sum(1 for it in items if in_dir(it, group))
        if n != expected:
            out.append(
                f"[条数] {e2e}/{group}/ 实测 {n} 条，期望 {expected} 条"
                "（少了 = 有人删了一条 skip 用例；多了 = 常量没跟着改，改常量要写理由）"
            )
    if expected_ungrouped is not None:
        n_ungrouped = sum(
            1 for it in items if not it.group_markers() and Path(it.module).name in whitelist
        )
        if n_ungrouped != expected_ungrouped:
            out.append(
                f"[条数] 白名单模块实测贡献 {n_ungrouped} 条，期望 EXPECTED_UNGROUPED_ITEMS = {expected_ungrouped}"
                "（白名单模块自己增减了 parametrize 值？改这个常量是正确的修法）"
            )
    return out


# ---------------------------------------------------------------------------
# skip 轴静态性质（纯 AST）
# ---------------------------------------------------------------------------


def _dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _source_line(path: Path, lineno: int) -> str:
    try:
        return path.read_text(encoding="utf-8").splitlines()[lineno - 1].strip()
    except (IndexError, OSError):
        return ""


def _skip_constructs(path: Path, root: Path) -> List[str]:
    """`ast.walk` 整个模块，凡 `pytest.skip(`/`importorskip(`/`xfail(` 调用或 `pytest.mark.skip`/`skipif`/`xfail`
    属性链一律计入。返回 `file:line  源码切片`。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(root).as_posix()
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dotted(node.func) in _SKIP_CALLS:
            hits.append(f"{rel}:{node.lineno}  {_source_line(path, node.lineno)}")
        elif isinstance(node, ast.Attribute) and _dotted(node) in _SKIP_MARKS:
            hits.append(f"{rel}:{node.lineno}  {_source_line(path, node.lineno)}")
    # 同一行同时命中 Call 与 Attribute（`pytest.mark.skip(...)`）时只报一次。
    return sorted(set(hits), key=lambda s: (s.split(":")[0], int(s.split(":")[1].split()[0])))


def _module_level_skip_marks(tree: ast.Module) -> List[ast.Call]:
    calls: List[ast.Call] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        for v in values:
            if isinstance(v, ast.Call) and _dotted(v.func) == "pytest.mark.skip":
                calls.append(v)
    return calls


def skip_axis_violations(root: Path, e2e_dir: str = DEFAULT_E2E_DIR) -> List[str]:
    """条件 1–5（矩阵 Unit A 第四条）。域 R 零 skip；acceptance 只许模块级带 reason 的 skip；无 collect_ignore。"""
    e2e = root / e2e_dir
    out: List[str] = []

    # ---- 域 R：baseline_1b 的收集可达链 -------------------------------------------
    domain_r: List[Path] = [e2e / "conftest.py", e2e / "helpers.py"]
    domain_r += sorted((e2e / BASELINE_MARKER).rglob("*.py")) if (e2e / BASELINE_MARKER).is_dir() else []
    for f in domain_r:
        if not f.is_file():
            continue
        for hit in _skip_constructs(f, root):
            out.append(
                f"[skip 轴·域 R] {hit}\n    baseline_1b 的收集可达链上不得有任何 skip 构造"
                "（函数体、fixture 体、异常处理器里的一并计入）——它会把计入门槛的用例悄悄摘掉"
            )

    # ---- 五个组目录：collect_ignore；acceptance：模块级 skip 恰好一个且带阶段 reason --
    for group in GROUP_MARKERS:
        gdir = e2e / group
        if not gdir.is_dir():
            continue
        for f in sorted(gdir.rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in _COLLECT_IGNORE_NAMES for t in node.targets
                ):
                    out.append(
                        f"[skip 轴·collect_ignore] {rel}:{node.lineno}  {_source_line(f, node.lineno)}\n"
                        "    collect_ignore 是比 skip 更隐蔽的消失方式，且不会出现在 --collect-only 的 skip 计数里"
                    )
            if group == BASELINE_MARKER:
                continue  # 域 R 已经查过零 skip
            hits = _skip_constructs(f, root)
            if not f.name.startswith("test_"):
                for hit in hits:
                    out.append(f"[skip 轴·acceptance] {hit}\n    非用例模块里不得有 skip 构造")
                continue
            marks = _module_level_skip_marks(tree)
            if len(marks) != 1:
                out.append(
                    f"[skip 轴·acceptance] {rel}: 模块级 pytestmark 里的 pytest.mark.skip 有 {len(marks)} 个，应恰好 1 个"
                    "——未激活组以 skip 形态存在，skip 只允许挂在模块级 pytestmark 上"
                )
                continue
            mark = marks[0]
            reason_node = next((kw.value for kw in mark.keywords if kw.arg == "reason"), None)
            reason = (
                reason_node.value
                if isinstance(reason_node, ast.Constant) and isinstance(reason_node.value, str)
                else ""
            )
            if not reason.strip():
                out.append(f"[skip 轴·acceptance] {rel}:{mark.lineno}: pytest.mark.skip 没有非空的 reason=")
            elif PHASE_TOKEN_FOR_DIR.get(group, "") not in reason:
                out.append(
                    f"[skip 轴·acceptance] {rel}:{mark.lineno}: skip reason 没有点名本组的激活阶段"
                    f" {PHASE_TOKEN_FOR_DIR.get(group)!r}（§0.5：reason 写明激活阶段与到期动作）：{reason!r}"
                )
            others = [h for h in hits if not h.startswith(f"{rel}:{mark.lineno}  ")]
            for hit in others:
                out.append(
                    f"[skip 轴·acceptance] {hit}\n    模块级 pytestmark 之外不得再有 skip 构造（函数级 skip 是条件 2 的反例）"
                )
    return out


# ---------------------------------------------------------------------------
# 总入口
# ---------------------------------------------------------------------------


def check_tree(
    root: Path,
    e2e_dir: str = DEFAULT_E2E_DIR,
    *,
    expected_baseline: int = EXPECTED_BASELINE_ITEMS,
    expected_per_dir: Mapping[str, int] = EXPECTED_ACCEPTANCE_PER_DIR,
    expected_ungrouped: Optional[int] = EXPECTED_UNGROUPED_ITEMS,
    ungrouped_modules: Iterable[str] = UNGROUPED_E2E_MODULES,
) -> List[str]:
    """对 `root/e2e_dir` 跑全部检查，返回违规列表（空 = 绿）。收集失败本身也是一条违规。"""
    root = Path(root)
    violations: List[str] = []
    try:
        items = collect_items(root, e2e_dir)
    except CollectionError as exc:
        violations.append(f"[收集] {exc}")
        items = []
    if items:
        violations += partition_violations(items, ungrouped_modules=ungrouped_modules)
        violations += count_violations(
            items,
            e2e_dir=e2e_dir,
            expected_baseline=expected_baseline,
            expected_per_dir=expected_per_dir,
            expected_ungrouped=expected_ungrouped,
            ungrouped_modules=ungrouped_modules,
        )
    violations += skip_axis_violations(root, e2e_dir)
    return violations


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(args[0]).resolve() if args else ROOT
    try:
        items = collect_items(root)
    except CollectionError as exc:
        print(f"分组守卫：收集失败\n{exc}")
        return 1
    violations = check_tree(root)
    n_base = sum(1 for it in items if BASELINE_MARKER in it.markers)
    per_dir = {
        g: sum(1 for it in items if it.module.startswith(f"{DEFAULT_E2E_DIR}/{g}/"))
        for g in ACCEPTANCE_MARKERS
    }
    n_ungrouped = sum(1 for it in items if not it.group_markers())
    print(
        f"分组守卫：收集 {len(items)} 条；baseline_1b {n_base}/{EXPECTED_BASELINE_ITEMS}；"
        + "；".join(f"{g} {per_dir[g]}/{EXPECTED_ACCEPTANCE_PER_DIR[g]}" for g in ACCEPTANCE_MARKERS)
        + f"；白名单 {n_ungrouped}/{EXPECTED_UNGROUPED_ITEMS}；派生总数 {EXPECTED_E2E_ITEMS}"
    )
    if violations:
        print(f"\n违规（{len(violations)} 处）：")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("分组守卫通过：划分律成立、条数与常量相等、skip 轴静态性质成立。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
