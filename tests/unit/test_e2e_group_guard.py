"""WI-17 · Unit A —— `scripts/lint_e2e_groups.py` 的**执行体**：三分划分律 ＋ skip 轴 ＋ 条数守卫。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` 的 `## WI-17:` 一节（Unit A 的七条）。
任务书：`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §0.5
（三分划分律、目录布局、条数口径）、§0.6 跨波欠账 **#2**（「实测 == 常量」）与 **#14**
（acceptance 由 14 变 17）、§8 G2 的 commit 级护栏（`baseline_1b` 可达链零 skip）。

**三条 Law，各自对应一类「零成本零信号」的破坏：**

1. **划分守卫的可失败性**——对合法目录树守卫必须绿；对「少一条 / 多一条 / marker 错 /
   文件跑错目录 / skip 标记缺失」任一变异必须红。没有守卫时，删掉一条 skip 用例是
   零成本且零信号的（§8：「不要把未激活组的 skip 当成永久豁免」）。
2. **`tests/e2e` 的每一个 collected item 都必须被归属**——恰好一个组 marker，或其模块在
   显式白名单 `UNGROUPED_E2E_MODULES` 里。没有第三种状态。Round 1 默认「根目录只有 smoke」，
   于是 `test_testid_dom_uniqueness.py` 落在一切断言之外（Gap C）。
3. **`baseline_1b` 的收集可达链上零 skip 构造**——包括 fixture 体、辅助函数体、
   `try/except` 处理器里的（Gap D）。一句
   `except Exception: pytest.skip(...)` 写进 `tests/e2e/conftest.py` 的 `live_server`，
   后果是 66 条 baseline 全部 skipped、push gate 全绿。判据必须 `ast.walk` 整个模块，
   不是扫 `Module.body`：那句 skip 在 AST 里的深度是 5。

**本文件的两个域，不可互相替代**：真实仓库树（本条 1/2/4/5/6/7）与 `tmp_path` 上的
合成树（本条 3）。合成树对「真实仓库里多了一个没人管的模块」是盲的，那是真树划分律的
职责；真树对「守卫会不会在变异上红」是盲的（真树今天合法，永远只能证明绿），那是合成
树的职责。Gap C 的事故正发生在真树上，而当时合成树的性质全绿。

**成本模型**：本文件的子进程一律 `--collect-only` 或纯 skip 执行——不起服务、不起
浏览器、不加载 epub.js。真树收集只跑**一次**（`_real_items()` 记忆化），三条断言共用同一次
结果；跑三次既慢又可能因中途改文件而不自洽。

**红收据说明**：本文件在 `scripts/lint_e2e_groups.py` 只有常量、四个 acceptance 目录
还是 `.gitkeep` 的状态下写成并录红——执行体缺失时以 `assert hasattr(...)` 的断言失败
呈现，不是 ImportError；真树条数在 14 条 skip 用例落地前也是断言失败。

------------------------------------------------------------------------------
定向破坏实录（§0 第四条纪律；破坏点全在 `tests/e2e/` 的**临时副本**或工作树，`src/` 一字未动）
------------------------------------------------------------------------------
见文末 `SABOTAGE_LOG`——实现落地后回填，不改本文件任何断言行。
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, FrozenSet, List, Set, Tuple

import pytest

from test_soak_log_contract import (  # type: ignore[import-not-found]
    covered_paths,
    hash_command_block,
    read_soak_log,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GROUPS_LINT_PATH = SCRIPTS_DIR / "lint_e2e_groups.py"
SOAK_RUN_PATH = SCRIPTS_DIR / "soak_run.py"
E2E_DIR = REPO_ROOT / "tests" / "e2e"
E2E_REL = "tests/e2e"
UNIT_DIR = REPO_ROOT / "tests" / "unit"

ACCEPTANCE_DIRS: Tuple[str, ...] = (
    "acceptance_4b1",
    "acceptance_p3",
    "acceptance_4a4",
    "acceptance_2a",
    "shell_4a",
)
GROUP_MARKERS: Tuple[str, ...] = ("baseline_1b", *ACCEPTANCE_DIRS)

#: 矩阵条件 3：skip reason 里必须出现激活阶段标识。与守卫脚本各写一份是刻意的——
#: 本文件是守卫的**独立 oracle**，不从被测脚本 import 判据。
PHASE_TOKEN_RE = re.compile(r"4B\.1|P3|4A\.4|2a|4A\.0")

#: 每个组目录的 skip reason 必须点名**自己**的激活阶段。p3 的 token 是字面 `P3`。
PHASE_TOKEN_FOR_DIR: Dict[str, str] = {
    "acceptance_4b1": "4B.1",
    "acceptance_p3": "P3",
    "acceptance_4a4": "4A.4",
    "acceptance_2a": "2a",
    "shell_4a": "4A.0",
}

#: 共享断言主体模块的裸模块名与期望落点（矩阵 Unit A 第八条的条 (3)）。
SHARED_DEG_MODULE = "deg_assertions"
SHARED_DEG_MODULE_PATH = REPO_ROOT / "tests" / "fixtures" / "deg_assertions.py"

#: 跨模块调用集里**不计**的来源：测试框架自身。`conftest` 不在名单里——它只导出常量，
#: 常量不会出现在「被调用的名字」集合里，天然被过滤。
EXCLUDED_IMPORT_PREFIXES = ("pytest", "playwright", "typing", "pathlib", "dataclasses", "__future__")

SUMMARY_TOKEN_RE = re.compile(
    r"(\d+) (passed|failed|errors?|skipped|deselected|xfailed|xpassed)"
)

#: 每个子进程的墙钟上限（秒）。`--collect-only` / `--setup-plan` 都是秒级动作；
#: 没有上限时，一个阻塞的 import 会让 unit lane 永远挂着而不是红。
SUBPROCESS_TIMEOUT_S = 300

# --------------------------------------------------------------------------
# 三段条数的**独立字面量**（不从被测脚本 import）
#
# 本文件是 `scripts/lint_e2e_groups.py` 的独立 oracle。把期望值写成
# `g.EXPECTED_BASELINE_ITEMS` 的形式，断言就退化成 `x == x`：删掉三条 baseline 用例、
# 把常量从 67 改成 64，守卫与它的守卫**同时**变绿，而门槛已经低了三条。
# 这里的数字与守卫脚本各写一份，两份必须相等——这才是欠账 #2「实测 == 常量」的完整形态。
#
# 改这里的数字**必须**同时改 `scripts/lint_e2e_groups.py` 并在两处写明理由；
# 只改一处会红，那正是它存在的意义。
# --------------------------------------------------------------------------
# 66 → 67：2026-09-06 欠账 #22 兑付新增 R-6c（理由写在 `scripts/lint_e2e_groups.py`
# 的「常量的变更史」里，本文件不复述——两处只需数字相等）。
# 67 → 68：2026-09-21 欠账 #44 的回归闸从白名单迁入 `baseline_1b`（同批 W-5a-③ 改判，
# `suite_hash` 本来就要变，两件事合并只清零一次）。
# 68 → 76：2026-09-30 009 #62，WI-4 of 019: moved 8 items——
# `test_selection_toolbar_stays_closed.py` 从白名单迁入 `baseline_1b`（**实测 8 条 item**，
# 4 条关闭路径 × 2 个时机）；白名单同批 72 → 64，总数 265 不变。
CANONICAL_BASELINE_ITEMS = 76
CANONICAL_ACCEPTANCE_PER_DIR: Dict[str, int] = {
    "acceptance_4b1": 8,
    "acceptance_p3": 4,
    "acceptance_4a4": 4,
    "acceptance_2a": 1,
    "shell_4a": 109,
}
# 17 → 26：2026-09-24 013 WI-9 批 A（REG-1 基线，A9.10）新增已激活组 `shell_4a`，
# **实测 9 条 item**（C9.22 按页参数化 ×3、C9.24、C9.25、C9.26、C9.38、C9.39 ×2）。
# 理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里，本文件不复述。
# 26 → 60：2026-09-24 013 WI-10（token 与主题层）往 `shell_4a` 加 34 条，**实测**
# （`pytest tests/e2e/shell_4a --collect-only -q` 数出 43 = 9 + 34）：
# `test_theme_resolution.py` 25（A10.2 ×10、A10.3 ×5、A10.4、A10.5、A10.6 ×4、A10.7、
# A10.8 ×2、FA-03/04）、`test_fouc.py` 6（A10.9：DCL 与 body 插入两个采样点 × 3 页）、
# `test_track_d_wi7.py` 3（Track-D 折入 28–30）。
# 60 → 61：2026-09-24 013 WI-10 追加 `test_dark_os_legacy_unchanged.py` 1 条（shell_4a 43 → 44）。
# 61 → 88：2026-09-25 013 WI-12（设置页切片）往 `shell_4a` 加 27 条，**实测**
# （`pytest tests/e2e/shell_4a --collect-only -q` 数出 71 = 44 + 27）：`test_settings_confirm.py` 6、
# `test_settings_appearance.py` 7、`test_settings_layout.py` 4、`test_settings_testids.py` 1、
# `test_settings_rows.py` 9。理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里。
# 88 → 120：2026-09-25 013 WI-13（书库页切片）往 `shell_4a` 加 32 条，**实测**
# （`pytest tests/e2e/shell_4a --collect-only -q` 数出 103 = 71 + 32）：`test_library_functional.py` 9、
# `test_library_layout.py` 6、`test_library_states.py` 2、`test_library_testids.py` 1、
# `test_library_theme_toggle.py` 7、`test_track_d_wi1_page.py` 2、`test_track_d_wi3_page.py` 5。
# 理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里。
# 120 → 121：2026-09-25 013 终审 RV-1（FB-S09 D8 余项）往 `shell_4a` 加 1 条，**实测**
# （`pytest tests/e2e/shell_4a --collect-only -q` 数出 104 = 103 + 1）：
# `test_settings_rows.py::test_provider_save_failure_is_visible`。
# 理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里。
# 121 → 125：2026-09-25 013 终审 RV-14（WI-11 验收 4 / 4a 的真浏览器半边）往 `shell_4a` 加 4 条，
# **实测**（`pytest tests/e2e/shell_4a --collect-only -q` 数出 108 = 104 + 4）：
# `test_toast.py`（C11.07 ×1、C11.08 ×1、C11.15 按 1500 / 7000 参数化 ×2）。
# 理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里。
# 125 → 126：2026-10-01 018 WI-3（欠账 #51，计划 WI-4）往 `shell_4a` 加 1 条，**实测**
# （`pytest tests/e2e/shell_4a --collect-only -q` 数出 109 = 108 + 1）：
# `test_settings_rows.py::test_provider_save_conflict_is_visible`。
# 理由写在 `scripts/lint_e2e_groups.py` 的「常量的变更史」里。
CANONICAL_ACCEPTANCE_ITEMS = 126
# 7 → 8 / 91 → 92：2026-09-20 欠账 #44 新增
# `tests/e2e/test_w8a_selection_survives_rerender.py`（恰好一条 item）。它按内容属于
# `baseline_1b`，落在白名单是为了不动 `suite_hash` 的覆盖面——理由与到期动作写在
# `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 8 → 7：2026-09-21 那笔明账到期兑付，该文件迁进 `baseline_1b`。**总数仍是 92**——
# 一条 item 换了住址，没有增减，所以 `CANONICAL_E2E_ITEMS` 不动；动的是它落在哪一段。
# 7 → 17 / 92 → 102：2026-09-22 欠账 #43 part (i) 第一批（WI-1 ＋ WI-2）新增
# `tests/e2e/test_notes_write_failure_is_attributable.py`，**实测 10 条 item**（一次真的
# `pytest tests/e2e --collect-only -q` 数出来的，不是按矩阵推算的）。这只是本批的条数：
# 矩阵预测全部落地后是 37 条，WI-3..WI-7 每一批会各自再改这里一次，每次都取实测值。
# 理由与迁移条件写在 `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 17 → 23 / 102 → 108：2026-09-22 同一欠账的 WI-3（`saveNote()` PUT 编辑分支）落地，该模块
# 10 → 16 条，**+6 为实测值**（`pytest tests/e2e --collect-only -q` 全量 108）。
# 23 → 31 / 108 → 116：2026-09-22 同一欠账的 WI-4（`deleteAnnotations()` ＋ 改色调用方）落地，
# 该模块 16 → 24 条，**+8 为实测值**（`pytest tests/e2e --collect-only -q` 全量 116）。
# 31 → 36 / 116 → 121：2026-09-22 同一欠账的 WI-5（`resolveConflict()` 的「保留我的」写）落地，
# 该模块 24 → 29 条，**+5 为实测值**（`pytest tests/e2e --collect-only -q` 全量 121）。
# 36 → 43 / 121 → 128：2026-09-22 同一欠账的 WI-6（请求前的静默出口，修订 A3）落地，
# 该模块 29 → 36 条，**+7 为实测值**（`pytest tests/e2e --collect-only -q` 全量 128）。
# 43 → 44 / 128 → 129：2026-09-22 同一欠账的 WI-7（成功路径护栏，不装路由）落地，
# 该模块 36 → 37 条，**+1 为实测值**（`pytest tests/e2e --collect-only -q` 全量 129）。
# 44 → 47 / 129 → 132：2026-09-23 017 WI-5（审计 #3 / #9）新增
# `tests/e2e/test_stored_cfi_must_agree_with_quote.py`，**实测 3 条 item**，不参数化。
# 它按内容属于 `baseline_1b`，落白名单同样是为了不动 `suite_hash` 的覆盖面——理由与
# 到期动作写在 `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 47 → 51 / 132 → 136：2026-09-23 017 WI-6（审计 #5）新增
# `tests/e2e/test_conflict_resolution_single_flight.py`，**实测 4 条 item**，不参数化。
# 它与 `acceptance_2a/test_deg_s5_write_conflict.py` 共用 DEG-S5 对话框，但判据不重叠
# （那一条是激活阶段验收，这一条是同一上下文里两次点击之间的并发），因此不并进那个组。
# 落白名单的理由与到期动作写在 `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 51 → 55 / 136 → 140：2026-09-23 017 WI-7（审计 #4）新增
# `tests/e2e/test_conflict_settled_text_keeps_its_base_etag.py`，**实测 4 条 item**，不参数化。
# 它与上一条同住 DEG-S5 对话框，但问的是收尾之后那次保存带的是哪一版令牌，判据不重叠。
# 落白名单的理由与到期动作写在 `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 55 → 63：2026-09-28 fix/selection-toolbar-reopen 新增
# `tests/e2e/test_selection_toolbar_stays_closed.py`，**实测 8 条 item**（4 条关闭路径 × 2 个时机）。
# 落白名单的理由与到期动作写在 `scripts/lint_e2e_groups.py` 的白名单注释里，本文件不复述。
# 63 → 71：2026-09-30 009 #50，WI-1 of 019: +8——已登记的
# `tests/e2e/test_notes_write_failure_is_attributable.py` 新增 8 条 item（W1-C11/C12/C13、
# W6-C6 ×2、W6-C7 ×2、W6-C8），**实测**白名单 71。
# 71 → 72：2026-09-30 009 #49，WI-2 of 019: +1——新增
# `tests/e2e/test_disk_poll_pumps_inflight_write.py`（WI2-E2），**实测 1 条 item**，白名单 72。
# 72 → 64：2026-09-30 009 #62，WI-4 of 019: moved 8 items——
# `tests/e2e/test_selection_toolbar_stays_closed.py` 迁入 `baseline_1b/`（见上面 68 → 76），
# 白名单条目撤掉；**实测**白名单 64、baseline 76。一段换一段，`CANONICAL_E2E_ITEMS` 不动。
# 64 → 68：2026-10-01 020-debug-state WI-2（rebase 到 019 之后重数）新增
# `tests/e2e/test_debug_state.py`，**实测 4 条 item**（E1–E4 各一条，不参数化），白名单 68。
# 它是工具用的观测面，没有到期条件——理由写在 `scripts/lint_e2e_groups.py` 的白名单注释里。
CANONICAL_UNGROUPED_ITEMS = 68
# 140 → 149：同上，`shell_4a` 的 9 条。
# 149 → 183：2026-09-24 013 WI-10 往 `shell_4a` 加的 34 条（见上面 26 → 60 那条注释）。
# 183 → 184：同上，深色 OS 回归 1 条。
# 184 → 211：2026-09-25 013 WI-12 的 27 条（见上面 61 → 88 那条注释；全量实测 211）。
# 211 → 243：2026-09-25 013 WI-13 的 32 条（见上面 88 → 120 那条注释；全量实测 243）。
# 243 → 244：2026-09-25 013 终审 RV-1 的 1 条（见上面 120 → 121 那条注释；全量实测 244）。
# 244 → 248：2026-09-25 013 终审 RV-14 的 4 条（见上面 121 → 125 那条注释；全量实测 248）。
# 248 → 256：2026-09-28 fix/selection-toolbar-reopen 的 8 条白名单 item（见上面 55 → 63；全量实测 256）。
# 256 → 264：2026-09-30 009 #50，WI-1 of 019: +8（见上面 63 → 71；全量实测 264）。
# 264 → 265：2026-09-30 009 #49，WI-2 of 019: +1（见上面 71 → 72；全量实测 265）。
# 265 → 269：2026-10-01 020-debug-state WI-2 的 4 条白名单 item（见上面 64 → 68；全量实测 269）。
# 269 → 270：2026-10-01 018 WI-3 / 欠账 #51 的 1 条（见上面 125 → 126 那条注释；全量实测 270）。
CANONICAL_E2E_ITEMS = 270

#: **已激活**的 acceptance 组，与 `scripts/lint_e2e_groups.py` 的
#: `ACTIVATED_ACCEPTANCE_DIRS` 各写一份——本文件是守卫的独立 oracle，不从被测脚本 import
#: 判据（见上面 `PHASE_TOKEN_RE` 一带的同款说明）。两份必须相等，由
#: `test_activated_group_registry_is_pinned_independently_of_the_guard_constant` 执行。
#:
#: 只改一处就红，正是要的行为：一个目录进了那张表，等于宣称「这一组今天必须真的跑出
#: passed」，两条 skip 轴对它**反向**判定。若这里写成 `g.ACTIVATED_ACCEPTANCE_DIRS`，
#: 「把一个还没落地的组塞进登记表」就会让守卫与守卫的守卫同时变绿，而那一组的用例从此
#: 既不 skip 也不被要求 passed——两条轴对它都不说话。
#:
#: `acceptance_2a`：011 WI-5b（DEG-S5 写冲突对话框落地）解禁，2026-09-19。
#: `shell_4a`：013 WI-9 批 A（REG-1 基线）生而激活，2026-09-24——它守的是既有页面，
#: 没有「等功能落地」的 skip 期。
CANONICAL_ACTIVATED_ACCEPTANCE_DIRS: FrozenSet[str] = frozenset({"acceptance_2a", "shell_4a"})


# --------------------------------------------------------------------------
# 加载被测脚本（按路径；`scripts/` 不是包）
# --------------------------------------------------------------------------
_MODULE_CACHE: Dict[str, ModuleType] = {}


def _load(path: Path, name: str) -> ModuleType:
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    assert path.exists(), f"{path} 不存在"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"无法从 {path} 加载"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[name] = module
    return module


def _guard() -> ModuleType:
    """`scripts/lint_e2e_groups.py`，并断言执行体齐全。

    WI-1 只放了常量；执行体缺失在这里是一条**断言失败**而不是 AttributeError——
    这是本文件录红时的形态。
    """
    mod = _load(GROUPS_LINT_PATH, "lint_e2e_groups_guard_under_test")
    missing = [
        attr
        for attr in (
            "EXPECTED_BASELINE_ITEMS",
            "EXPECTED_ACCEPTANCE_PER_DIR",
            "EXPECTED_ACCEPTANCE_ITEMS",
            "EXPECTED_UNGROUPED_ITEMS",
            "UNGROUPED_E2E_MODULES",
            "collect_items",
            "partition_violations",
            "count_violations",
            "skip_axis_violations",
            "check_tree",
        )
        if not hasattr(mod, attr)
    ]
    assert not missing, (
        f"scripts/lint_e2e_groups.py 缺少 {missing}。WI-1 只放常量，划分律的执行体是 WI-17 的交付"
        "（任务书 §0.5：「这条划分律由 scripts/lint_e2e_groups.py 执行，不靠人眼」）。"
    )
    return mod


def _soak() -> ModuleType:
    assert SOAK_RUN_PATH.exists(), f"{SOAK_RUN_PATH} 不存在——soak 计数守卫（矩阵 Unit A 第五 / 六条）是 WI-17 的交付"
    return _load(SOAK_RUN_PATH, "soak_run_under_test")


_REAL_ITEMS: List[object] = []


def _real_items() -> List[object]:
    """真树的一次收集，全文件共用（矩阵：「全表只跑这一次收集」）。"""
    if not _REAL_ITEMS:
        _REAL_ITEMS.extend(_guard().collect_items(REPO_ROOT))
    return _REAL_ITEMS


def _module_of(item: object) -> str:
    return str(getattr(item, "module"))


def _markers_of(item: object) -> FrozenSet[str]:
    return frozenset(getattr(item, "markers"))


def _group_markers_of(item: object) -> Set[str]:
    return set(_markers_of(item)) & set(GROUP_MARKERS)


def _parse_summary_tokens(out: str) -> Dict[str, int]:
    counts = {k: 0 for k in ("passed", "failed", "errors", "skipped", "deselected")}
    tail = [ln for ln in out.splitlines() if " in " in ln and ("passed" in ln or "skipped" in ln or "failed" in ln or "error" in ln or "no tests ran" in ln)]
    assert tail, f"输出里找不到 pytest 的 summary 行：\n{out}"
    for n, key in SUMMARY_TOKEN_RE.findall(tail[-1]):
        if key.startswith("error"):
            key = "errors"
        if key in counts:
            counts[key] = int(n)
    return counts


# --------------------------------------------------------------------------
# Case 1：真实目录树上四个 acceptance 组的条数与 marker 正确（success / S2 / L1）
# --------------------------------------------------------------------------
def test_real_tree_acceptance_dir_counts_and_markers_match_constants() -> None:
    """四个目录各自的 item 数 == `EXPECTED_ACCEPTANCE_PER_DIR[dir]`，且每条恰好带自己目录的 marker。

    删掉一条 skip 用例——那个零成本零信号的动作——本条就是给它装信号的。
    """
    g = _guard()
    items = _real_items()

    per_dir: Dict[str, List[object]] = {
        d: [it for it in items if _module_of(it).startswith(f"{E2E_REL}/{d}/")]
        for d in ACCEPTANCE_DIRS
    }
    for d in ACCEPTANCE_DIRS:
        expected = g.EXPECTED_ACCEPTANCE_PER_DIR[d]
        assert len(per_dir[d]) == expected, (
            f"{E2E_REL}/{d}/ 实测收集到 {len(per_dir[d])} 条，常量期望 {expected} 条。"
            f"逐条：{[getattr(it, 'nodeid') for it in per_dir[d]]}"
        )
        for it in per_dir[d]:
            assert _group_markers_of(it) == {d}, (
                f"{getattr(it, 'nodeid')} 携带的组 marker 是 {sorted(_group_markers_of(it))}，"
                f"它住在 {d}/ 下，应当恰好是 {{{d!r}}}"
            )

    total = sum(len(v) for v in per_dir.values())
    assert total == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"四个 acceptance 目录合计 {total} 条，常量 EXPECTED_ACCEPTANCE_ITEMS = "
        f"{g.EXPECTED_ACCEPTANCE_ITEMS}（欠账 #14 要求两者相等）"
    )

    # 守卫脚本本身对真树退出码 0（矩阵 Expected output 第一句）。
    proc = subprocess.run(
        [sys.executable, str(GROUPS_LINT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"`python scripts/lint_e2e_groups.py` 对真实仓库树退出码 {proc.returncode}：\n"
        + proc.stdout
        + proc.stderr
    )


# --------------------------------------------------------------------------
# Case 2：收集结果是一个划分（property / S4 / L1）
# --------------------------------------------------------------------------
def test_real_tree_collection_is_a_partition_and_counts_match() -> None:
    g = _guard()
    items = _real_items()
    assert items, "tests/e2e 一条都没收到——零用例是失败，不是通过（policy-core 第 1 条）"

    whitelist: Set[str] = {Path(m).as_posix() for m in g.UNGROUPED_E2E_MODULES}

    # (0) 白名单必须按**路径**登记，不是 basename。按 basename 授权时，把
    #     `tests/e2e/test_harness_smoke.py` 挪进任意一个没人管的子目录，三段条数一条不差、
    #     划分律照旧成立，而那个目录从此免检。
    not_paths = sorted(m for m in whitelist if "/" not in m)
    assert not not_paths, (
        f"UNGROUPED_E2E_MODULES 里这些条目只是文件名而不是仓库相对路径：{not_paths}——"
        "basename 授权等于给「同名文件挪进任意子目录」预开的门"
    )
    assert whitelist == {
        f"{E2E_REL}/test_harness_smoke.py",
        f"{E2E_REL}/test_testid_dom_uniqueness.py",
        f"{E2E_REL}/test_notes_write_failure_is_attributable.py",
        # 017 WI-5（审计 #3 / #9）：盘上 cfi 与 quote 对不上时 quote 说了算。
        # 内容上属于 `baseline_1b`，落白名单是为了不动 `suite_hash` 的覆盖面——
        # 理由与到期动作写在 `scripts/lint_e2e_groups.py` 的白名单注释里。
        f"{E2E_REL}/test_stored_cfi_must_agree_with_quote.py",
        # 017 WI-6（审计 #5）：冲突对话框同一时刻只许有一次收尾在飞。
        # 同上，理由与到期动作在 `scripts/lint_e2e_groups.py` 的白名单注释里。
        f"{E2E_REL}/test_conflict_resolution_single_flight.py",
        # 017 WI-7（审计 #4）：收尾放进编辑器的那一版，必须连着它自己的基准令牌。
        # 同上，理由与到期动作在 `scripts/lint_e2e_groups.py` 的白名单注释里。
        f"{E2E_REL}/test_conflict_settled_text_keeps_its_base_etag.py",
        # （2026-09-30 009 #62，WI-4 of 019：`test_selection_toolbar_stays_closed.py`
        # 到期迁入 `baseline_1b/`，此处条目撤掉。）
        # 009 #49（019 WI-2，WI2-E2）：盘上轮询期间在途的写必须出得了门（helpers 机制护栏）。
        # 与前面几条一样，理由在 `scripts/lint_e2e_groups.py` 的白名单注释里。
        f"{E2E_REL}/test_disk_poll_pumps_inflight_write.py",
        # 020 WI-2：`Reader3Epub.getDebugState()` 只读观测面的真浏览器验收（E1–E4）。
        # 工具用的观测面，与 009 各组正交，没有到期条件——理由在 `scripts/lint_e2e_groups.py`。
        f"{E2E_REL}/test_debug_state.py",
    }, f"白名单的内容变了：{sorted(whitelist)}（加项要写理由，且它必须真的贡献 item）"

    # (1) 划分：恰好一个组 marker，或模块在白名单里。双 marker 也红。
    strays = [
        f"{getattr(it, 'nodeid')}  markers={sorted(_group_markers_of(it))}"
        for it in items
        if not (len(_group_markers_of(it)) == 1 or _module_of(it) in whitelist)
    ]
    assert not strays, (
        "以下 item 既不恰好带一个组 marker、其模块又不在 UNGROUPED_E2E_MODULES 里——"
        "第三种状态不存在：\n  " + "\n  ".join(strays)
    )
    doubles = [getattr(it, "nodeid") for it in items if len(_group_markers_of(it)) >= 2]
    assert not doubles, f"以下 item 同时带多个组 marker（两道门槛都会误报）：{doubles}"

    # (2) 白名单不得空转。
    contributed = {_module_of(it) for it in items if not _group_markers_of(it)}
    dangling = sorted(whitelist - contributed)
    assert not dangling, (
        f"白名单里的模块在这次收集里一条 item 都没贡献（悬空 = 给下一个模块预开的门）：{dangling}"
    )

    # (3) 条数：baseline == 常量；acceptance == 常量；白名单 == 常量；派生总数 == 全量。
    n_baseline = sum(1 for it in items if "baseline_1b" in _markers_of(it))
    n_acceptance = sum(1 for it in items if _group_markers_of(it) & set(ACCEPTANCE_DIRS))
    n_ungrouped = sum(1 for it in items if not _group_markers_of(it))
    assert n_baseline == g.EXPECTED_BASELINE_ITEMS, (
        f"带 baseline_1b 的 item 实测 {n_baseline} 条，常量 {g.EXPECTED_BASELINE_ITEMS}（欠账 #2：实测 == 常量）"
    )
    assert n_acceptance == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"带 acceptance marker 的 item 实测 {n_acceptance} 条，常量 {g.EXPECTED_ACCEPTANCE_ITEMS}"
    )
    assert n_ungrouped == g.EXPECTED_UNGROUPED_ITEMS, (
        f"白名单模块贡献 {n_ungrouped} 条，常量 {g.EXPECTED_UNGROUPED_ITEMS}"
    )
    assert len(items) == g.EXPECTED_E2E_ITEMS, (
        f"tests/e2e 全量 {len(items)} 条，派生值 EXPECTED_E2E_ITEMS = {g.EXPECTED_E2E_ITEMS}"
    )

    # 守卫自己的划分函数对真树给零违规——它与上面的独立 oracle 必须同解。
    assert g.partition_violations(items, ungrouped_modules=whitelist) == []


# --------------------------------------------------------------------------
# Case 2b：三段条数钉在**本文件的字面量**上（property / S4 / L1）
# --------------------------------------------------------------------------
def test_canonical_counts_are_pinned_independently_of_the_guard_constants() -> None:
    """66 / 8+4+4+1 / 7 / 90 四段，实测与**本文件的字面量**相等，且守卫常量与之相等。

    点名的失败模式：上一条把期望值写成 `g.EXPECTED_*`，于是「删三条 baseline 用例 ＋
    把常量改成 62」这套动作让守卫、守卫的守卫、soak 分母**三者同时**变绿——断言退化成
    `x == x`，条数轴整个失去信号。本条是那条断言缺的另一半：数字在这里**再写一遍**，
    两份必须对得上。只改一处就红，正是要的行为。
    """
    g = _guard()
    items = _real_items()

    # (1) 实测 == 本文件的字面量。
    n_baseline = sum(1 for it in items if "baseline_1b" in _markers_of(it))
    per_dir = {
        d: sum(1 for it in items if _module_of(it).startswith(f"{E2E_REL}/{d}/"))
        for d in ACCEPTANCE_DIRS
    }
    n_acceptance = sum(1 for it in items if _group_markers_of(it) & set(ACCEPTANCE_DIRS))
    n_ungrouped = sum(1 for it in items if not _group_markers_of(it))

    assert n_baseline == CANONICAL_BASELINE_ITEMS, (
        f"baseline_1b 实测 {n_baseline} 条，本文件钉的是 {CANONICAL_BASELINE_ITEMS} 条"
    )
    assert per_dir == CANONICAL_ACCEPTANCE_PER_DIR, (
        f"四个 acceptance 目录实测 {per_dir}，本文件钉的是 {CANONICAL_ACCEPTANCE_PER_DIR}"
    )
    assert n_acceptance == CANONICAL_ACCEPTANCE_ITEMS == sum(CANONICAL_ACCEPTANCE_PER_DIR.values())
    assert n_ungrouped == CANONICAL_UNGROUPED_ITEMS, (
        f"白名单模块实测贡献 {n_ungrouped} 条，本文件钉的是 {CANONICAL_UNGROUPED_ITEMS} 条"
    )
    assert len(items) == CANONICAL_E2E_ITEMS == (
        CANONICAL_BASELINE_ITEMS + CANONICAL_ACCEPTANCE_ITEMS + CANONICAL_UNGROUPED_ITEMS
    ), f"tests/e2e 全量实测 {len(items)} 条，本文件钉的是 {CANONICAL_E2E_ITEMS} 条"

    # (2) 守卫脚本的常量 == 本文件的字面量。两份口径必须同步演进。
    assert int(g.EXPECTED_BASELINE_ITEMS) == CANONICAL_BASELINE_ITEMS
    assert dict(g.EXPECTED_ACCEPTANCE_PER_DIR) == CANONICAL_ACCEPTANCE_PER_DIR
    assert int(g.EXPECTED_ACCEPTANCE_ITEMS) == CANONICAL_ACCEPTANCE_ITEMS
    assert int(g.EXPECTED_UNGROUPED_ITEMS) == CANONICAL_UNGROUPED_ITEMS
    assert int(g.EXPECTED_E2E_ITEMS) == CANONICAL_E2E_ITEMS


# --------------------------------------------------------------------------
# Case 3：对生成的变异目录树，守卫必红（property / S6 / L1）
# --------------------------------------------------------------------------
_PYTEST_INI = (
    "[pytest]\n"
    "addopts = --strict-markers\n"
    "markers =\n"
    + "".join(f"    {m}: synthetic\n" for m in GROUP_MARKERS)
)


def _skip_module(group: str, phase: str, *, n_tests: int = 1, skipped: bool = True, extra: str = "") -> str:
    marks = [f"pytest.mark.{group}"]
    if skipped:
        marks.append(f'pytest.mark.skip(reason="激活阶段 {phase}；到期动作：删本行")')
    body = "import pytest\n\npytestmark = [" + ", ".join(marks) + "]\n\n"
    for i in range(n_tests):
        body += f"def test_{group}_{i}():\n    assert 1 == 1\n\n"
    return body + extra


def _base_spec() -> Dict[str, str]:
    spec: Dict[str, str] = {
        "pytest.ini": _PYTEST_INI,
        f"{E2E_REL}/conftest.py": "import pytest\n\n\ndef helper_in_conftest():\n    return 1\n",
        f"{E2E_REL}/helpers.py": "def shared_helper():\n    return 1\n",
        f"{E2E_REL}/test_harness_smoke.py": "def test_smoke():\n    assert True\n",
        f"{E2E_REL}/baseline_1b/test_b.py": (
            "import pytest\n\npytestmark = pytest.mark.baseline_1b\n\n"
            "def test_b0():\n    assert True\n\n\ndef test_b1():\n    assert True\n"
        ),
    }
    for d in ACCEPTANCE_DIRS:
        spec[f"{E2E_REL}/{d}/test_{d}.py"] = _skip_module(d, PHASE_TOKEN_FOR_DIR[d])
    return spec


BASE_EXPECTED = dict(
    expected_baseline=2,
    expected_per_dir={d: 1 for d in ACCEPTANCE_DIRS},
    expected_ungrouped=1,
    # 白名单是**路径**，不是 basename：见 `_m_whitelisted_module_moved_into_subdir`。
    ungrouped_modules={f"{E2E_REL}/test_harness_smoke.py"},
    # 2026-09-19（011 WI-5b-2）新增。合成基准树的四个 acceptance 组**都未激活**、各带一个
    # 模块级 skip——这正是下面 21 个变异被写下来时所处的状态。显式传空集，是为了让这棵树的
    # 含义不随真实仓库的登记表漂移：真树上 `acceptance_2a` 已经激活，这里若跟着默认值走，
    # 合法基准树会因为「已激活组还留着 skip」当场判红，而红的原因与被测的那 21 条破坏毫无
    # 关系——最省事的修法（把 2a 从基准树里删掉）还会顺手砍掉 collect-ignore 那条变异的落点。
    # 已激活那一侧的牙由 `test_guard_is_red_when_an_activated_group_still_carries_a_skip`
    # 单独装，不挂在这棵对照树上。
    activated_dirs=frozenset(),
)


def _write_tree(root: Path, spec: Dict[str, str]) -> None:
    for rel, content in spec.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


Mutation = Callable[[Dict[str, str]], None]


def _m_one_fewer(spec: Dict[str, str]) -> None:
    del spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"]


def _m_one_more(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_p3", "P3", n_tests=2)


def _m_wrong_marker(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_4a4", "P3")


def _m_file_in_wrong_dir(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_4a4/test_strayed_p3.py"] = _skip_module("acceptance_p3", "P3")


def _m_skip_missing(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = _skip_module("acceptance_p3", "P3", skipped=False)


def _m_double_marker(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest\n\npytestmark = [pytest.mark.baseline_1b, pytest.mark.acceptance_2a]\n\n"
        "def test_b0():\n    assert True\n\n\ndef test_b1():\n    assert True\n"
    )


def _m_dangling_whitelist(spec: Dict[str, str]) -> None:
    del spec[f"{E2E_REL}/test_harness_smoke.py"]


def _m_skip_in_baseline_body(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest\n\npytestmark = pytest.mark.baseline_1b\n\n"
        "def test_b0():\n    try:\n        x = 1\n    except Exception as e:\n"
        "        pytest.skip(f'flaky today: {e}')\n    assert x == 1\n\n\n"
        "def test_b1():\n    assert True\n"
    )


def _m_skip_in_conftest_fixture(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/conftest.py"] = (
        "import pytest\n\n\n@pytest.fixture(scope='session')\ndef live_server():\n"
        "    try:\n        proc = object()\n    except Exception as e:\n"
        "        pytest.skip(f'e2e server unavailable: {e}')\n    yield proc\n"
    )


def _m_reason_without_phase(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "import pytest\n\npytestmark = [pytest.mark.acceptance_p3, pytest.mark.skip(reason='later')]\n\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )


def _m_function_level_skip(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "import pytest\n\npytestmark = pytest.mark.acceptance_p3\n\n"
        "@pytest.mark.skip(reason='激活阶段 P3；到期动作：删本行')\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )


def _m_collect_ignore(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/acceptance_2a/deg_helpers_2a.py"] = "collect_ignore = ['test_acceptance_2a.py']\n"


def _m_unregistered_root_module(spec: Dict[str, str]) -> None:
    spec[f"{E2E_REL}/test_nobody_owns_me.py"] = "def test_orphan():\n    assert True\n"


# --- 2026-09-05 追加的六个变异（gpt-5.6-sol 审计的 D7 组）-------------------------
#
# 六个都满足同一条判据：**在打补丁前的守卫上全绿**，而每一个都足以把某道门槛掏空。
# 它们不是「更多同类样本」，是六个各自独立的绕过路径。


def _m_skip_in_root_conftest(spec: Dict[str, str]) -> None:
    """域 R 漏了 `tests/conftest.py`：一条 autouse fixture 能把 66 条 baseline 全摘掉。

    根 conftest 对 `tests/e2e` 下的每一条用例都生效，却不在旧的三条硬编码路径里。
    收集条数一条不少（skip 发生在运行期），静态 skip 轴一声不响。
    """
    spec["tests/conftest.py"] = (
        "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef _ci_guard():\n"
        "    pytest.skip('CI 上先关掉，回头再说')\n"
    )


def _m_skip_in_transitively_imported_fixture_module(spec: Dict[str, str]) -> None:
    """域 R 漏了 import 闭包：`helpers.py` 引的语料模块里那句 skip 同样在可达链上。"""
    spec["tests/fixtures/corpus_stub.py"] = (
        "import pytest\n\n\ndef make_book(kind):\n"
        "    if kind == 'huge':\n        pytest.skip('语料太大，先跳过')\n    return kind\n"
    )
    spec[f"{E2E_REL}/helpers.py"] = (
        "from corpus_stub import make_book  # type: ignore[import-not-found]\n\n\n"
        "def shared_helper():\n    return make_book('small')\n"
    )


def _m_skip_via_direct_import_in_baseline(spec: Dict[str, str]) -> None:
    """`from pytest import skip` —— 与 `pytest.skip(...)` 语义等价，AST 里却没有 `pytest` 这个名字。"""
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest\nfrom pytest import skip\n\n"
        "pytestmark = pytest.mark.baseline_1b\n\n"
        "def test_b0():\n    if not _ready():\n        skip('server flaky today')\n    assert True\n\n\n"
        "def _ready():\n    return True\n\n\n"
        "def test_b1():\n    assert True\n"
    )


def _m_skip_via_module_alias_in_conftest(spec: Dict[str, str]) -> None:
    """`import pytest as pt` 之后 `pt.skip(...)`——§8 G2 那句护栏的别名写法。"""
    spec[f"{E2E_REL}/conftest.py"] = (
        "import pytest as pt\n\n\n@pt.fixture(scope='session')\ndef live_server():\n"
        "    try:\n        proc = object()\n    except Exception as e:\n"
        "        pt.skip(f'e2e server unavailable: {e}')\n    yield proc\n"
    )


def _m_skip_marker_via_module_alias_in_baseline(spec: Dict[str, str]) -> None:
    """`import pytest as p` 之后 `@p.mark.skip(...)`——别名形态的 marker 构造。"""
    spec[f"{E2E_REL}/baseline_1b/test_b.py"] = (
        "import pytest as p\n\npytestmark = p.mark.baseline_1b\n\n"
        "@p.mark.skip(reason='暂时不稳')\ndef test_b0():\n    assert True\n\n\n"
        "def test_b1():\n    assert True\n"
    )


def _m_whitelisted_module_moved_into_subdir(spec: Dict[str, str]) -> None:
    """白名单模块整体挪进一个没人管的子目录：basename 授权时三段条数**一条不差**。"""
    body = spec.pop(f"{E2E_REL}/test_harness_smoke.py")
    spec[f"{E2E_REL}/legacy/test_harness_smoke.py"] = body


def _m_pytestmark_reassigned_after_skip(spec: Dict[str, str]) -> None:
    """模块级 `pytestmark` 被二次赋值覆盖：静态检查仍看见那处合规的 skip 赋值，item 却真的活着。"""
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "import pytest\n\n"
        "pytestmark = [pytest.mark.acceptance_p3, "
        "pytest.mark.skip(reason='激活阶段 P3；到期动作：删本行')]\n\n"
        "# 调试时加的，忘了删——最后一次绑定胜出，上面那行 skip 从此不生效。\n"
        "pytestmark = [pytest.mark.acceptance_p3]\n\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )


def _m_reason_names_a_longer_phase_token(spec: Dict[str, str]) -> None:
    """reason 写的是 `4B.10`：substring 包含判据下它冒充 `4B.1` 登记成功。"""
    spec[f"{E2E_REL}/acceptance_4b1/test_acceptance_4b1.py"] = (
        "import pytest\n\npytestmark = [pytest.mark.acceptance_4b1, "
        "pytest.mark.skip(reason='激活阶段 4B.10；到期动作：删本行')]\n\n"
        "def test_acceptance_4b1_0():\n    assert True\n"
    )


MUTANTS: List[Tuple[str, Mutation, Tuple[str, ...]]] = [
    ("one-fewer", _m_one_fewer, ("acceptance_p3",)),
    ("one-more", _m_one_more, ("acceptance_p3",)),
    ("wrong-marker", _m_wrong_marker, ("test_acceptance_p3.py",)),
    ("file-in-wrong-dir", _m_file_in_wrong_dir, ("test_strayed_p3.py",)),
    ("skip-missing", _m_skip_missing, ("test_acceptance_p3.py", "skip")),
    ("double-marker", _m_double_marker, ("test_b.py",)),
    ("dangling-whitelist", _m_dangling_whitelist, ("test_harness_smoke.py",)),
    ("skip-in-baseline-body", _m_skip_in_baseline_body, ("test_b.py:", "skip")),
    ("skip-in-conftest-fixture", _m_skip_in_conftest_fixture, ("conftest.py:", "skip")),
    ("reason-without-phase", _m_reason_without_phase, ("test_acceptance_p3.py", "reason")),
    ("function-level-skip", _m_function_level_skip, ("test_acceptance_p3.py", "pytestmark")),
    ("collect-ignore", _m_collect_ignore, ("deg_helpers_2a.py", "collect_ignore")),
    ("unregistered-root-module", _m_unregistered_root_module, ("test_nobody_owns_me.py",)),
    # --- 2026-09-05 追加（审计 D7）---------------------------------------------
    ("skip-in-root-conftest", _m_skip_in_root_conftest, ("tests/conftest.py:", "skip")),
    (
        "skip-in-transitively-imported-fixture",
        _m_skip_in_transitively_imported_fixture_module,
        ("corpus_stub.py:", "skip"),
    ),
    ("skip-via-direct-import", _m_skip_via_direct_import_in_baseline, ("test_b.py:", "skip")),
    ("skip-via-module-alias", _m_skip_via_module_alias_in_conftest, ("conftest.py:", "skip")),
    (
        "skip-marker-via-module-alias",
        _m_skip_marker_via_module_alias_in_baseline,
        ("test_b.py", "skip"),
    ),
    (
        "whitelisted-module-moved-into-subdir",
        _m_whitelisted_module_moved_into_subdir,
        ("legacy/test_harness_smoke.py",),
    ),
    (
        "pytestmark-reassigned-after-skip",
        _m_pytestmark_reassigned_after_skip,
        ("test_acceptance_p3.py", "skip"),
    ),
    (
        "reason-names-a-longer-phase-token",
        _m_reason_names_a_longer_phase_token,
        ("test_acceptance_4b1.py", "4B.1"),
    ),
]


def test_guard_is_green_on_a_legal_synthetic_tree(tmp_path: Path) -> None:
    """对照支：合法树 ⇒ 零违规。没有这一支，一个「永远红」的守卫在下面全部变异上也全绿。"""
    g = _guard()
    _write_tree(tmp_path, _base_spec())
    violations = g.check_tree(tmp_path, **BASE_EXPECTED)
    assert violations == [], "合法的合成树被守卫判红：\n  " + "\n  ".join(violations)


def test_guard_accepts_the_alias_spelling_of_a_legal_module_level_skip(tmp_path: Path) -> None:
    """别名解析必须是**双向**的：`from pytest import mark` 写出来的合法 skip 不得被判红。

    只在「禁止」那一侧解析别名，会让守卫在合法的别名写法上误报——而误报的最省事修法
    （把别名解析删掉）恰好把 `_m_skip_via_direct_import` / `_m_skip_via_module_alias`
    那两条路重新打开。这条是那个修法的闸门。
    """
    g = _guard()
    spec = _base_spec()
    spec[f"{E2E_REL}/acceptance_p3/test_acceptance_p3.py"] = (
        "from pytest import mark\n\n"
        "pytestmark = [mark.acceptance_p3, mark.skip(reason='激活阶段 P3；到期动作：删本行')]\n\n"
        "def test_acceptance_p3_0():\n    assert True\n"
    )
    _write_tree(tmp_path, spec)
    violations = g.check_tree(tmp_path, **BASE_EXPECTED)
    assert violations == [], "别名写法的合法 acceptance 模块被判红：\n  " + "\n  ".join(violations)


def test_collection_subprocess_times_out_instead_of_hanging_forever(tmp_path: Path) -> None:
    """收集子进程必须有墙钟上限，超时翻译成 `CollectionError`。

    点名的失败模式：`tests/e2e/conftest.py` 里一个阻塞的 import（轮询一个永不就绪的
    端口、等一个没起来的服务）。没有 timeout 时 `subprocess.run` 永不返回，分组闸既不
    红也不绿——CI 上是一个没有输出、没有退出码的作业，比任何一种失败都难诊断。
    """
    g = _guard()
    spec = _base_spec()
    spec[f"{E2E_REL}/conftest.py"] = "import time\n\ntime.sleep(600)\n"
    _write_tree(tmp_path, spec)

    with pytest.raises(g.CollectionError) as excinfo:
        g.collect_items(tmp_path, timeout=3.0)
    msg = str(excinfo.value)
    assert "超时" in msg or "timeout" in msg.lower(), (
        f"收集确实没能完成，但异常没说是超时，读的人会去查退出码：{msg}"
    )


def test_main_collects_the_tree_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` 的一次运行只允许一次 `--collect-only`（文件头「收集只跑一次」的成本模型）。

    点名的失败模式：`main()` 自己收一次打摘要，再调 `check_tree()` 让它**又**收一次。
    两次冷启动在真树上是双倍 import 成本，在变异树上是每棵树两次——「一次收集」这条
    设计写在守卫脚本的文件头里，却没有任何东西执行它。
    """
    g = _guard()
    _write_tree(tmp_path, _base_spec())

    real = g.collect_items
    calls: List[Path] = []

    def counting(root, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(Path(root))
        return real(root, *args, **kwargs)

    monkeypatch.setattr(g, "collect_items", counting)
    g.main([str(tmp_path)])
    assert len(calls) == 1, (
        f"`main()` 对同一棵树跑了 {len(calls)} 次 `--collect-only`（期望 1 次）：{calls}"
    )


@pytest.mark.parametrize("name,mutate,tokens", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_guard_is_red_on_every_mutant_tree(
    tmp_path: Path, name: str, mutate: Mutation, tokens: Tuple[str, ...]
) -> None:
    """每一种变异都让守卫非空返回，且消息**点名**偏差项（文件 / 目录 / 关键字）。

    `return []` 式守卫（永远通过）在任一变异上红——本条正是为了杀掉那个实现。
    「只数文件个数不看 marker」在 wrong-marker / double-marker 上红；
    「不检查 skip 标记」在 skip-missing / function-level-skip 上红；
    「只扫 Module.body」在 skip-in-baseline-body / skip-in-conftest-fixture 上红。
    """
    g = _guard()
    spec = _base_spec()
    mutate(spec)
    _write_tree(tmp_path, spec)
    violations = g.check_tree(tmp_path, **BASE_EXPECTED)
    assert violations, f"变异 {name} 没有让守卫变红——守卫对这类破坏是盲的"
    joined = "\n".join(violations)
    for token in tokens:
        assert token in joined, (
            f"变异 {name} 让守卫红了，但消息没有点名 {token!r}，读的人无从知道错在哪：\n{joined}"
        )


# --------------------------------------------------------------------------
# Case 4：skip 轴的静态性质（property / S4 / L1）——本文件是守卫的独立 oracle
# --------------------------------------------------------------------------
_SKIP_CALLS = {"skip", "importorskip", "xfail"}
_SKIP_MARKS = {"skip", "skipif", "xfail"}


def _dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _skip_constructs(path: Path) -> List[str]:
    """`ast.walk` 整个模块：凡解析为 pytest.skip/importorskip/xfail 调用、或 pytest.mark.skip/skipif/xfail 属性链，一律计入。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dotted(node.func) in {f"pytest.{c}" for c in _SKIP_CALLS}:
            hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}  {_dotted(node.func)}(")
        elif isinstance(node, ast.Attribute) and _dotted(node) in {f"pytest.mark.{m}" for m in _SKIP_MARKS}:
            hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}  {_dotted(node)}")
    return hits


def _module_level_skip_marks(path: Path) -> List[ast.Call]:
    """模块级 `pytestmark = [...]` 里的 `pytest.mark.skip(...)` 调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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


def _domain_r_files() -> List[Path]:
    files = [E2E_DIR / "conftest.py", E2E_DIR / "helpers.py"]
    files += sorted((E2E_DIR / "baseline_1b").rglob("*.py"))
    return [f for f in files if f.is_file()]


def test_baseline_reachable_chain_has_zero_skip_constructs() -> None:
    """条件 1 ＋ 5：域 R（conftest / helpers / baseline_1b/**）里零 skip 构造，函数体与异常处理器一并计入。"""
    hits: List[str] = []
    for f in _domain_r_files():
        hits += _skip_constructs(f)
    assert not hits, (
        "baseline_1b 的收集可达链上出现了 skip 构造——每一条都是把计入门槛的用例悄悄摘掉：\n  "
        + "\n  ".join(hits)
    )
    # 守卫自己的静态检查与本 oracle 同解。
    assert _guard().skip_axis_violations(REPO_ROOT) == []


def test_every_acceptance_module_skips_only_via_module_level_pytestmark_with_phase_reason() -> None:
    """条件 2 ＋ 3 ＋ 4，**按组的激活状态分两侧判**；目录内无 collect_ignore 对两侧都不变。

    - **未激活**组（不在 `CANONICAL_ACTIVATED_ACCEPTANCE_DIRS` 里）：每个 `test_*.py` 恰好
      一个模块级 `pytest.mark.skip`，reason 非空且点名本组的激活阶段，模块内再无别的 skip 构造；
    - **已激活**组：**一个 skip 构造都不许有**——与域 R 同款判据。

    2026-09-19（011 WI-5b-2）改此条。原文是「四个 acceptance 目录里每个 `test_*.py` 恰好一个
    模块级 skip」，它在「第一个组被激活」这个事件之前是对的，之后不再是：`acceptance_2a` 的
    DEG-S5 写冲突用例已经解禁并跑出 passed，旧判据读到的却是「模块级 skip 有 0 个」，于是它
    要求的恰恰是把一条已经落地的用例重新关掉——判据反过来给退化背书。改的是**哪一侧**适用，
    不是放宽：未激活那一侧一字未动，已激活那一侧换成更严的「零 skip 构造」。
    """
    problems: List[str] = []
    seen_any = False
    for d in ACCEPTANCE_DIRS:
        activated = d in CANONICAL_ACTIVATED_ACCEPTANCE_DIRS
        for f in sorted((E2E_DIR / d).rglob("*.py")):
            text = f.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(f))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in {"collect_ignore", "collect_ignore_glob"} for t in node.targets
                ):
                    problems.append(f"{f.relative_to(REPO_ROOT)}:{node.lineno}  collect_ignore（比 skip 更隐蔽的消失方式）")
            if activated:
                # 已激活组：用例模块与辅助模块同一条判据——零 skip 构造。留着的任何一处都能
                # 让一条「已宣称必须 passed」的用例静默消失，与域 R 上那句 skip 是同一种事故。
                hits = _skip_constructs(f)
                if hits:
                    problems.append(
                        f"{f.relative_to(REPO_ROOT)}: {d} 已登记在 CANONICAL_ACTIVATED_ACCEPTANCE_DIRS 里"
                        f"（= 这一组今天必须真的跑出 passed），却仍有 skip 构造：{hits}"
                    )
                if f.name.startswith("test_"):
                    seen_any = True
                continue
            if not f.name.startswith("test_"):
                if _skip_constructs(f):
                    problems.append(f"{f.relative_to(REPO_ROOT)}: 非用例模块里出现 skip 构造")
                continue
            seen_any = True
            marks = _module_level_skip_marks(f)
            if len(marks) != 1:
                problems.append(f"{f.relative_to(REPO_ROOT)}: 模块级 pytestmark 里的 pytest.mark.skip 有 {len(marks)} 个，应恰好 1 个")
                continue
            reason = next((kw.value for kw in marks[0].keywords if kw.arg == "reason"), None)
            reason_text = reason.value if isinstance(reason, ast.Constant) and isinstance(reason.value, str) else ""
            if not reason_text.strip():
                problems.append(f"{f.relative_to(REPO_ROOT)}: skip 没有非空 reason")
            elif PHASE_TOKEN_FOR_DIR[d] not in reason_text:
                problems.append(
                    f"{f.relative_to(REPO_ROOT)}: skip reason 没有点名本组的激活阶段 {PHASE_TOKEN_FOR_DIR[d]!r}：{reason_text!r}"
                )
            elif not PHASE_TOKEN_RE.search(reason_text):
                problems.append(f"{f.relative_to(REPO_ROOT)}: reason 不含任何激活阶段标识：{reason_text!r}")
            # 模块级那一个之外，整个模块不得再有任何 skip 构造（函数级 skip 挪到模块级是条件 2 的反例）。
            others = [h for h in _skip_constructs(f) if not h.endswith(f":{marks[0].lineno}  pytest.mark.skip")]
            others = [h for h in others if f":{marks[0].lineno}  " not in h]
            if others:
                problems.append(f"{f.relative_to(REPO_ROOT)}: 模块级 pytestmark 之外还有 skip 构造：{others}")
    assert seen_any, "四个 acceptance 目录里一个 test_*.py 都没有——14 条 skip 用例是 WI-17 的交付"
    assert not problems, "skip 轴静态性质被破坏：\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------
# Case 5：四个 acceptance 组正选后按激活状态分账（guard / S3 / L1）
# --------------------------------------------------------------------------
#: 本条子进程读这个环境变量，把逐 item 的 setup 阶段结果**写文件**——不走 stdout。
#: 理由：pytest 自己会捕获插件里的 print，`--setup-plan` 下的输出形态还随版本变；写文件
#: 是唯一不受捕获策略影响的通道。
ACCEPTANCE_OUTCOME_ENV = "ACCEPTANCE_OUTCOME_PROBE_PATH"

#: 逐 item 探针插件，写进 `tmp_path`、经 `PYTHONPATH` 以 `-p` 加载，不入仓、不进任何 lane。
#: 形状照抄下面 `_ACCEPTANCE_WIRING_PLUGIN`（同文件 Case 5b），不发明新机制。
_ACCEPTANCE_OUTCOME_PLUGIN = '''
"""临时探针：在 `--setup-plan` 下逐 item 汇报 setup 阶段的结果。

`--setup-plan` 不执行任何 fixture 函数体、不执行用例体，所以**已激活组的那一条不进任何
summary 计数**：它不是 passed（call 阶段不执行，没有 call report），也不是 skipped。
只看 summary 的数字，已激活组就成了无人观察的一块。本探针补的正是这块：setup 阶段的
report 对每条 item 都有，skip 生效的会带 `skipped`，没被 skip 的走到 `passed`。
"""

import os


def pytest_runtest_logreport(report):
    if report.when != "setup":
        return
    with open(os.environ["ACCEPTANCE_OUTCOME_PROBE_PATH"], "a", encoding="utf-8") as fh:
        fh.write(f"{report.nodeid}\\t{'skipped' if report.skipped else report.outcome}\\n")
'''


def test_positive_selection_of_acceptance_groups_yields_exactly_the_skipped_count(
    tmp_path: Path,
) -> None:
    """`-m "acceptance_4b1 or …" --setup-plan` ⇒ 退出码 0、errors == failed == 0，且
    **逐目录**分账：登记表内各组的每一条都不是 skipped，表外各组的每一条都是 skipped。

    `errors == 0` 在这里只覆盖**收集期**的失败：模块级 import 错、语法错、marker 拼错。
    它**不**覆盖未激活组的 fixture 名写错和用例体里的 `NameError`——模块级 skip 在
    `pytest_runtest_setup` 里 tryfirst 生效，早于 fixture 装配、更早于用例体，所以那一路
    永远走不到那里。那半句由下一条
    `test_acceptance_wiring_resolves_without_the_module_level_skip` 承担（摘掉 skip 后跑
    `--setup-plan`）。

    2026-09-19（011 WI-5b-2）改此条。原文断 `passed == 0` 并写明「不起服务、不起浏览器」，
    两句都随 `acceptance_2a` 解禁而失效：那一组的 DEG-S5 用例现在**真的**起服务、起浏览器
    并跑出 passed，旧断言会把它读成「skip 被解开而阶段未到」。新口径不是把 `passed` 放宽成
    `>= 0`——那等于让这条用例对「某个未激活组悄悄活过来」和「已激活组悄悄被关掉」双向失明。
    两个数都钉：passed 恰好是登记表内各组的条数之和，skipped 恰好是其余各组的条数之和，
    两者相加仍须等于 `EXPECTED_ACCEPTANCE_ITEMS`。

    2026-09-20（欠账 #45）再改此条：子进程由**真跑**换成 `--setup-plan` ＋ 逐 item 探针。
    上一版让 unit lane 长出了一条浏览器依赖——`acceptance_2a` 解禁后，这里的子进程真的去
    launch Chromium，没装浏览器的机器上必红（确定性，不是 flaky）；CI run 35500630451 的
    `unit` job 就红在这一条，那个 job 不装 Chromium。`--setup-plan` 解析整条 fixture 闭包
    但不执行 fixture 函数体、不执行用例体，于是「不起服务、不起浏览器」重新成立。

    **本次换法的实质代价，写明在此，不许含混。** 原断言 `passed == n_activated` 证明的是
    「DEG-S5 **真的跑过并通过**」。`--setup-plan` 下 call 阶段不执行，这句话**不再由
    unit lane 证明**，改由 e2e lane 承担（`uv run pytest tests/e2e --browser chromium`，
    实测 `75 passed / 16 skipped`，DEG-S5 那一条就在里面）。这是**刻意的 lane 归位**，不是
    疏忽：「一条浏览器用例通不通得过」不该是 commit 时的性质，它属于 push 闸。本条在 unit
    lane 保留的是**归属**那一层——登记表内的组不得带生效 skip，表外的组必须带，逐目录判，
    两个方向的牙都还在。
    """
    g = _guard()
    activated = [d for d in ACCEPTANCE_DIRS if d in CANONICAL_ACTIVATED_ACCEPTANCE_DIRS]
    dormant = [d for d in ACCEPTANCE_DIRS if d not in CANONICAL_ACTIVATED_ACCEPTANCE_DIRS]

    plugin_dir = tmp_path / "outcome_probe"
    plugin_dir.mkdir()
    (plugin_dir / "acceptance_outcome_probe.py").write_text(
        _ACCEPTANCE_OUTCOME_PLUGIN, encoding="utf-8"
    )
    report_path = tmp_path / "outcomes.tsv"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(plugin_dir), env.get("PYTHONPATH", "")) if p
    )
    env[ACCEPTANCE_OUTCOME_ENV] = str(report_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            E2E_REL,
            "-m",
            " or ".join(ACCEPTANCE_DIRS),
            "--setup-plan",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-p",
            "acceptance_outcome_probe",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    out = proc.stdout + proc.stderr
    counts = _parse_summary_tokens(out)
    assert proc.returncode == 0, f"正选四个 acceptance 组时退出码 {proc.returncode}：\n{out}"
    assert counts["errors"] == 0, f"有 collection error——某条 acceptance 用例 import 不进来：\n{out}"
    assert counts["failed"] == 0, f"有 acceptance 用例真的跑起来并失败了：\n{out}"

    assert report_path.exists(), (
        f"探针一行都没写（{report_path} 不存在）——插件没被加载，本条证明不了任何事：\n{out}"
    )
    reported: List[Tuple[str, str]] = []
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        nodeid, _, outcome = line.partition("\t")
        reported.append((nodeid, outcome))
    detail = "\n  ".join(f"{nodeid}\t{outcome}" for nodeid, outcome in reported)

    # 覆盖面先于结论：理由同 Case 5b——覆盖面不全时「零个异常」毫无意义。
    assert len(reported) == CANONICAL_ACCEPTANCE_ITEMS, (
        f"探针只逐 item 汇报了 {len(reported)} 条，期望 {CANONICAL_ACCEPTANCE_ITEMS} 条——"
        f"覆盖面不全时「零个异常」毫无意义：\n  {detail}\n{out}"
    )

    by_dir: Dict[str, List[Tuple[str, str]]] = {
        d: [(n, o) for n, o in reported if n.startswith(f"{E2E_REL}/{d}/")]
        for d in ACCEPTANCE_DIRS
    }
    for d in ACCEPTANCE_DIRS:
        expected = CANONICAL_ACCEPTANCE_PER_DIR[d]
        assert len(by_dir[d]) == expected, (
            f"{E2E_REL}/{d}/ 的探针行数是 {len(by_dir[d])}，本文件独立钉的是 {expected}：\n  {detail}"
        )

    wrongly_skipped = [
        f"{n}\t{o}" for d in activated for n, o in by_dir[d] if o == "skipped"
    ]
    assert not wrongly_skipped, (
        f"以下 item 住在**已激活**组 {sorted(CANONICAL_ACTIVATED_ACCEPTANCE_DIRS)} 里却带生效 skip"
        f"——某条已宣称激活的用例又被关回去了：\n  " + "\n  ".join(wrongly_skipped) + f"\n{out}"
    )
    wrongly_live = [
        f"{n}\t{o}" for d in dormant for n, o in by_dir[d] if o != "skipped"
    ]
    assert not wrongly_live, (
        f"以下 item 住在**未激活**组 {dormant} 里却没被 skip 掉——某个未激活组的 skip 被解开"
        f"而阶段未到：\n  " + "\n  ".join(wrongly_live) + f"\n{out}"
    )

    n_activated = sum(len(by_dir[d]) for d in activated)
    n_dormant = sum(len(by_dir[d]) for d in dormant)
    assert n_activated + n_dormant == CANONICAL_ACCEPTANCE_ITEMS, (
        f"两类条数之和 == {n_activated + n_dormant}，本文件独立钉的是 "
        f"{CANONICAL_ACCEPTANCE_ITEMS}（差额 = 有 item 不住在四个组目录下）：\n  {detail}"
    )
    assert n_activated + n_dormant == g.EXPECTED_ACCEPTANCE_ITEMS, (
        f"两类条数之和 == {n_activated + n_dormant}，"
        f"期望 EXPECTED_ACCEPTANCE_ITEMS == {g.EXPECTED_ACCEPTANCE_ITEMS}：\n  {detail}"
    )


# --------------------------------------------------------------------------
# Case 5b：已激活组登记表，两条 skip 轴对它**反向**判定（guard / S6 / L1）
#
# `acceptance_2a` 是仓库历史上第一个被激活的 acceptance 组（011 WI-5b，DEG-S5 写冲突对话框
# 落地，2026-09-19）。在它之前，「未激活组以 skip 形态存在」对**每一个** acceptance item
# 成立；在它之后，那句话只对登记表之外的组成立，表内的组必须真的跑出 passed。
#
# 下面五条装的是反向那一侧的牙。没有它们，把新分支写成
#
#     if group in activated_dirs:
#         continue          # 「已激活，不用查」
#
# 也能让全套变绿——「已激活」就从一条更严的判据退化成一个免检开关，而那正是把一整组用例
# 悄悄关掉时最先会被按下的那个开关。上面 Case 4 / Case 5 对真树成立，但真树今天合法，
# 永远只能证明绿（文件头「两个域不可互相替代」）；反向的可失败性只能在合成树上证。
#
# **免检开关这条必须按轴拆开证，不能只靠走 `check_tree` 的那一条**（2026-09-19 复核实测）。
# 两条轴一起判时它们互相掩护：把 `skip_axis_violations` 的已激活分支整个掏空，动态轴那条
# 消息照样让 `check_tree` 非空返回、照样点名 `acceptance_2a` 与模块路径（nodeid 里本来就带），
# 于是整份本文件 38 passed，没有一条用例发现静态轴已经不设防。所以
# `skip_axis_violations` 与 `skip_marker_violations` **各有一条只调它自己**的用例，
# 走 `check_tree` 的那一条守的是第三件事：登记表真的被透传到了两条轴上。
# --------------------------------------------------------------------------
def test_activated_group_registry_is_pinned_independently_of_the_guard_constant() -> None:
    """守卫的 `ACTIVATED_ACCEPTANCE_DIRS` 与本文件独立钉的那份必须相等，且只能放 acceptance 目录名。

    与 `CANONICAL_*` 三段条数同一个理由（见那一节的注释）：登记表若只在守卫脚本里有一份，
    「往表里加一个还没落地的组」就是零成本零信号的——守卫对它不再要求 skip，也没有任何东西
    要求它 passed，两条轴同时对那一组闭嘴。两份各写一份，只改一处就红。
    """
    g = _guard()
    assert hasattr(g, "ACTIVATED_ACCEPTANCE_DIRS"), (
        "scripts/lint_e2e_groups.py 里没有 ACTIVATED_ACCEPTANCE_DIRS。"
        "两条 skip 轴要求每一个 acceptance item 都带生效的 skip，而 acceptance_2a 已经解禁——"
        "没有「已激活组」这个口径，守卫要求的恰恰是把一条已落地的用例重新关掉（011 WI-5b-2）"
    )
    actual = frozenset(g.ACTIVATED_ACCEPTANCE_DIRS)
    assert actual == CANONICAL_ACTIVATED_ACCEPTANCE_DIRS, (
        f"守卫登记的已激活组是 {sorted(actual)}，本文件独立钉的是 "
        f"{sorted(CANONICAL_ACTIVATED_ACCEPTANCE_DIRS)}——两处必须同时改，且都要写清楚"
        "是哪一次、因为什么进来的"
    )
    strays = sorted(actual - set(ACCEPTANCE_DIRS))
    assert not strays, (
        f"登记表里出现了不是 acceptance 目录名的条目 {strays}——它对任何一条轴都不生效，"
        "只会让读的人以为某个组已经激活"
    )


def test_guard_is_red_when_an_activated_group_still_carries_a_skip(tmp_path: Path) -> None:
    """已激活组里还留着模块级 skip ⇒ **`check_tree` 整体**必须红，且消息点名那一组。

    这是本条登记表存在的全部意义。「这一组今天必须真的跑出 passed」如果没有执行体，
    删掉 `pytest.mark.skip` 和把它加回来就都是零信号的动作：加回来之后条数一条不差、
    划分律成立、未激活那一侧的判据照样绿，而那一组的用例已经不再产出 passed。

    **它证明什么、不证明什么**（2026-09-19 复核更正）。本条原先在 assert 文案里写着
    「`if activated: continue` 式的实现（把已激活当成免检开关）正是这条要杀掉的」——那句话
    **经定向破坏实测证伪**，不成立：把 `skip_axis_violations` 已激活分支的
    `for hit in _skip_constructs(f, root):` 换成 `for hit in []:`（语义上就是
    `if group in activated: continue`），整份本文件仍 **38 passed**。原因是本条调的是
    `check_tree`，两条 skip 轴一起判，而它断的两件事（`violations` 非空、消息点名
    `acceptance_2a` / `test_acceptance_2a.py`）全部由**动态轴**那条消息独力满足——nodeid 里
    本来就带着模块路径。两条轴一起判的用例天然给单侧掏空留了掩护。

    所以分工是：静态轴那一侧的牙在
    `test_static_skip_axis_alone_is_red_when_an_activated_group_keeps_a_skip`（直接调
    `skip_axis_violations`），动态轴的在
    `test_effective_skip_marker_axis_flips_only_for_activated_groups`（直接喂 `CollectedItem`）；
    本条守的是第三件事，那两条都守不到：登记表真的从 `check_tree` 透传到了两条轴上。
    断言本身一字未改，改的是对它的描述。

    对照支是 `test_guard_is_green_on_a_legal_synthetic_tree`（同一棵树、空登记表 ⇒ 零违规），
    两条合起来才说明红是**登记表**带来的，不是这棵树本来就脏。
    """
    g = _guard()
    assert hasattr(g, "ACTIVATED_ACCEPTANCE_DIRS"), (
        "scripts/lint_e2e_groups.py 里没有 ACTIVATED_ACCEPTANCE_DIRS——"
        "已激活组的反向判定无从谈起（011 WI-5b-2）"
    )
    spec = _base_spec()  # 四个组各带一个合法的模块级 skip：空登记表下这棵树是**合法**的
    _write_tree(tmp_path, spec)
    violations = g.check_tree(
        tmp_path, **dict(BASE_EXPECTED, activated_dirs=frozenset({"acceptance_2a"}))
    )
    assert violations, (
        "acceptance_2a 已登记为已激活，组里却还留着模块级 skip，`check_tree` 没有红——"
        "登记表没有被透传到两条轴上。（单侧被掏空不由本条守，见 docstring：两条轴一起判时"
        "它们互相掩护，各自的牙在拆开调用的那两条用例里）"
    )
    joined = "\n".join(violations)
    assert "acceptance_2a" in joined and "test_acceptance_2a.py" in joined, (
        f"守卫红了，但消息没有点名出问题的那一组 / 那个文件，读的人无从知道是哪一侧错了：\n{joined}"
    )
    # 另外三组仍未激活、各自合法，不得被牵连判红——反向判定必须只作用于登记表之内。
    for d in ("acceptance_4b1", "acceptance_p3", "acceptance_4a4"):
        assert f"test_{d}.py" not in joined, (
            f"未激活的 {d} 被连坐判红：反向判定作用到了登记表之外的组上：\n{joined}"
        )


def test_static_skip_axis_alone_is_red_when_an_activated_group_keeps_a_skip(
    tmp_path: Path,
) -> None:
    """**静态轴单独**的牙：直接调 `skip_axis_violations`，不经 `check_tree`。

    与上一条的分工，一句话：上一条证明的是「`check_tree` 整体会红」，**不**证明静态轴那一侧
    有执行体。2026-09-19 实测：把 `skip_axis_violations` 已激活分支的
    `for hit in _skip_constructs(f, root):` 换成 `for hit in []:`（语义上就是
    `if group in activated: continue`，把已激活读成免检开关），整份本文件 **38 passed**——
    上一条断的 `violations` 非空与「消息点名 acceptance_2a / test_acceptance_2a.py」，
    全由动态轴那条消息独力满足（nodeid 里本来就带着模块路径）。两条轴一起判的用例互相掩护，
    单侧掏空只能由「只调它自己」的用例守。本条守静态那一侧。

    **第二段是静态轴不可被动态轴替代的那一类**，也是本条真正的理由。已激活组里写一句
    `pytest.skip(..., allow_module_level=True)`，整个模块在**收集期**就消失：item 压根不存在，
    `skip_marker_violations` 收到的集合里根本没有 `acceptance_2a` 这条——它一言不发不是判错，
    是看不见（同类还有 `collect_ignore`、整模块被排除）。动态轴在这一侧结构性地兜不住，
    而这恰恰是「把一整组已宣称激活的用例悄悄关掉」最省事的做法：条数轴数的是 collected，
    连被数的机会都没有。所以下面先把「动态轴确实哑口」坐实，再断静态轴必须说话——
    少了前半段，后半段就只是又一条同义反复。
    """
    g = _guard()
    assert hasattr(g, "ACTIVATED_ACCEPTANCE_DIRS"), (
        "scripts/lint_e2e_groups.py 里没有 ACTIVATED_ACCEPTANCE_DIRS——"
        "已激活组的静态反向判定无从谈起（011 WI-5b-2）"
    )
    activated = frozenset({"acceptance_2a"})
    dormant = ("acceptance_4b1", "acceptance_p3", "acceptance_4a4")

    # --- (1) 已激活组里还留着模块级 skip ⇒ 静态轴**单独**必须红 ------------------
    kept = tmp_path / "kept"
    _write_tree(kept, _base_spec())  # 空登记表下这棵树是合法的（见 BASE_EXPECTED 的注释）
    violations = g.skip_axis_violations(kept, activated_dirs=activated)
    assert violations, (
        "acceptance_2a 已登记为已激活，组里却还留着模块级 skip，`skip_axis_violations` "
        "单独判时没有红——已激活那一侧的静态判据是空的，「已激活」退化成了免检开关"
    )
    joined = "\n".join(violations)
    assert "acceptance_2a" in joined and "test_acceptance_2a.py" in joined, (
        f"静态轴红了，但消息没有点名出问题的那一组 / 那个文件：\n{joined}"
    )
    for d in dormant:
        assert f"test_{d}.py" not in joined, (
            f"未激活的 {d} 被连坐判红：反向判定作用到了登记表之外的组上：\n{joined}"
        )

    # --- (2) 收集期就看不见的消失方式：动态轴哑口，静态轴必须说话 ----------------
    spec = _base_spec()
    spec[f"{E2E_REL}/acceptance_2a/test_acceptance_2a.py"] = (
        "import pytest\n\n"
        "pytestmark = [pytest.mark.acceptance_2a]\n\n"
        "# 整模块在收集期消失：一条 item 都不进 --collect-only 的结果，动态轴无从判起。\n"
        "if True:\n"
        "    pytest.skip('e2e 环境没就绪，先整模块跳过', allow_module_level=True)\n\n"
        "def test_acceptance_2a_0():\n    assert True\n"
    )
    invisible = tmp_path / "invisible"
    _write_tree(invisible, spec)

    items = g.collect_items(invisible)
    from_2a = [getattr(it, "nodeid") for it in items if "acceptance_2a" in _module_of(it)]
    assert from_2a == [], (
        f"这棵树本该让 acceptance_2a 在收集期整个消失，实际还收到了 {from_2a}——"
        "样本立不住，下面那条就证明不了静态轴是不可替代的"
    )
    assert g.skip_marker_violations(items, activated_dirs=activated) == [], (
        "动态轴对这棵树本该一言不发：item 不存在时它无从判起。它若在这里红了，说明它红的"
        "是别的东西，本条就不再是「只有静态轴看得见」的样本"
    )

    hidden = g.skip_axis_violations(invisible, activated_dirs=activated)
    assert hidden, (
        "已激活组用 `pytest.skip(..., allow_module_level=True)` 把整模块从收集期摘掉，"
        "静态轴没有红——这一类消失方式动态轴结构性地看不见，静态轴是唯一的防线"
    )
    joined_hidden = "\n".join(hidden)
    assert "acceptance_2a" in joined_hidden and "test_acceptance_2a.py" in joined_hidden, (
        f"静态轴红了，但消息没有点名那一组 / 那个文件：\n{joined_hidden}"
    )
    for d in dormant:
        assert f"test_{d}.py" not in joined_hidden, (
            f"未激活的 {d} 被连坐判红：\n{joined_hidden}"
        )


def test_guard_is_red_when_a_dormant_group_is_missing_its_skip_under_a_registry(
    tmp_path: Path,
) -> None:
    """回归：登记表引入后，**未激活**那一侧的判据必须原样还在。

    `_m_skip_missing` 这条变异在空登记表下已经由 `test_guard_is_red_on_every_mutant_tree`
    覆盖。这里再跑一遍是换了条件：登记表**非空**。两条轴新增的分支若写成「先查 activated，
    命中就 continue，没命中也 continue」，或把判定错挂成「只要登记表非空就整体跳过 acceptance
    检查」，空登记表那一版仍然全绿，只有这条会红。
    """
    g = _guard()
    assert hasattr(g, "ACTIVATED_ACCEPTANCE_DIRS"), (
        "scripts/lint_e2e_groups.py 里没有 ACTIVATED_ACCEPTANCE_DIRS（011 WI-5b-2）"
    )
    spec = _base_spec()
    _m_skip_missing(spec)  # acceptance_p3 的模块级 skip 被删掉，而 p3 并未登记激活
    _write_tree(tmp_path, spec)
    violations = g.check_tree(
        tmp_path, **dict(BASE_EXPECTED, activated_dirs=frozenset({"acceptance_2a"}))
    )
    assert violations, (
        "未激活的 acceptance_p3 丢了模块级 skip，守卫却没红——引入已激活口径时把原来那一半弄丢了"
    )
    joined = "\n".join(violations)
    assert "test_acceptance_p3.py" in joined and "skip" in joined, (
        f"守卫红了，但消息没有点名 acceptance_p3 的 skip 缺失：\n{joined}"
    )


def test_effective_skip_marker_axis_flips_only_for_activated_groups() -> None:
    """动态轴（读收集期**实际生效**的 marker）单独一条，四种组合全判。

    单独装它的理由：上面那条合成树用例里静态轴与动态轴会**同时**报红，于是只改静态那一条
    也能让它绿——动态轴的反向判定没有任何东西执行，而「模块级 pytestmark 被二次赋值覆盖」
    这类事故只有动态轴看得见（见守卫脚本 `skip_marker_violations` 的 docstring）。这条直接
    喂 `CollectedItem`，把两条轴拆开。

    item 侧拿到的是 **marker 名**，登记表按**目录名**索引。本仓两者同形，但同形是巧合不是
    判据：这条用例连同守卫的实现都必须显式走 marker ↔ 目录的既有映射，否则将来某个组的
    marker 与目录改成不同名时，登记表会静默地对谁都不生效。
    """
    g = _guard()
    assert hasattr(g, "ACTIVATED_ACCEPTANCE_DIRS"), (
        "scripts/lint_e2e_groups.py 里没有 ACTIVATED_ACCEPTANCE_DIRS（011 WI-5b-2）"
    )
    activated, dormant = "acceptance_2a", "acceptance_p3"
    kw = dict(activated_dirs=frozenset({activated}))

    def item(d: str, *, skipped: bool) -> object:
        markers = {d} | ({"skip"} if skipped else set())
        return g.CollectedItem(
            nodeid=f"{E2E_REL}/{d}/test_x.py::test_x",
            module=f"{E2E_REL}/{d}/test_x.py",
            markers=frozenset(markers),
        )

    v_bad_activated = g.skip_marker_violations([item(activated, skipped=True)], **kw)
    assert v_bad_activated and activated in "\n".join(v_bad_activated), (
        f"{activated} 已激活，item 上却带着生效的 skip marker，动态轴没有红：{v_bad_activated}"
    )
    assert g.skip_marker_violations([item(activated, skipped=False)], **kw) == [], (
        f"{activated} 已激活且 item 没有 skip marker——这正是要的状态，动态轴不该判红"
    )
    v_bad_dormant = g.skip_marker_violations([item(dormant, skipped=False)], **kw)
    assert v_bad_dormant and dormant in "\n".join(v_bad_dormant), (
        f"未激活的 {dormant} 的 item 没有任何生效 skip marker，动态轴没有红（旧判据丢了）：{v_bad_dormant}"
    )
    assert g.skip_marker_violations([item(dormant, skipped=True)], **kw) == [], (
        f"未激活的 {dormant} 的 item 带生效 skip marker——合法状态，不该判红"
    )


# --------------------------------------------------------------------------
# Case 5b：摘掉模块级 skip 之后，acceptance 的 fixture 接线真的解析得开
#          （guard / S3 / L1；2026-09-05 审计 D7 追加）
# --------------------------------------------------------------------------
#: 临时探针插件，写进 `tmp_path`、经 `PYTHONPATH` 以 `-p` 加载，不入仓、不进任何 lane。
#: 用 raw 字符串：里面的 `\t` 要原样落到生成的文件里，由它自己的 f-string 求值。
_ACCEPTANCE_WIRING_PLUGIN = r'''
"""临时探针：摘掉模块级 skip，并在收集完成时逐 item 汇报 fixture 名的解析结果。

**为什么必须摘 skip。** `_pytest.skipping.pytest_runtest_setup` 是 tryfirst，模块级
`pytest.mark.skip` 在那里就把 item 结掉了——早于 `_pytest.python.pytest_runtest_setup`
装配 fixture，更早于用例体。所以「-m 正选四个组、断 errors == 0」那一路**永远**走不到
「fixture 名写错了」和「用例体里有 NameError」，它证明的只是模块 import 得进来。

**为什么配 `--setup-plan` 而不是真跑。** setup-plan 会解析整条 fixture 闭包（名字解析
不开就是 `fixture '…' not found` 的 ERROR），但不执行任何 fixture 函数体、不执行用例体：
不起服务、不起浏览器，成本仍是毫秒级。
"""

PREFIX = "ACCEPTANCE_WIRING"
#: `request` 不是真 fixture，永远不出现在 `name2fixturedefs` 里。
PSEUDO_FIXTURES = {"request"}


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        for node in item.listchain():
            node.own_markers = [m for m in node.own_markers if m.name not in ("skip", "skipif")]


def pytest_collection_finish(session):
    for item in session.items:
        info = getattr(item, "_fixtureinfo", None)
        if info is None:
            print(f"{PREFIX}\t{item.nodeid}\tNO_FIXTUREINFO")
            continue
        missing = sorted(
            n
            for n in info.names_closure
            if n not in info.name2fixturedefs and n not in PSEUDO_FIXTURES
        )
        print(f"{PREFIX}\t{item.nodeid}\t{','.join(missing)}")
'''


def test_acceptance_wiring_resolves_without_the_module_level_skip(tmp_path: Path) -> None:
    """摘掉模块级 skip 后 `--setup-plan`：每条 acceptance item 的 fixture 闭包都解析得开。

    点名的失败模式：一条未激活用例的签名里写着 `def test_x(page, live_serve)`（少个 r）。
    今天它被 skip，明天解开那行 skip 时才第一次以 `fixture 'live_serve' not found` 炸出来
    ——而那一天正是「阶段到期、要它跑起来」的那天。本条把那个信号提前到今天，且全程
    不执行任何 fixture 函数体、不起服务、不起浏览器。

    覆盖面本身也是断言的一部分：探针逐 item 打一行，行数必须等于 acceptance 总条数，
    否则「一条都没检查也叫全绿」。
    """
    plugin_dir = tmp_path / "wiring_probe"
    plugin_dir.mkdir()
    (plugin_dir / "acceptance_wiring_probe.py").write_text(
        _ACCEPTANCE_WIRING_PLUGIN, encoding="utf-8"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(plugin_dir), env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            E2E_REL,
            "-m",
            " or ".join(ACCEPTANCE_DIRS),
            "--setup-plan",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-p",
            "acceptance_wiring_probe",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    out = proc.stdout + proc.stderr

    reported = [ln.split("\t", 2) for ln in out.splitlines() if ln.startswith("ACCEPTANCE_WIRING\t")]
    assert len(reported) == CANONICAL_ACCEPTANCE_ITEMS, (
        f"探针只逐 item 汇报了 {len(reported)} 条，期望 {CANONICAL_ACCEPTANCE_ITEMS} 条——"
        f"覆盖面不全时「零个未解析」毫无意义：\n{out}"
    )
    unresolved = [f"{nodeid}: {names}" for _, nodeid, names in reported if names.strip()]
    assert not unresolved, (
        "以下 acceptance item 的 fixture 名在收集期就解析不开（解开 skip 那天才炸的东西，今天炸）：\n  "
        + "\n  ".join(unresolved)
    )
    assert proc.returncode == 0, (
        f"摘掉 skip 后 `--setup-plan` 退出码 {proc.returncode}——fixture 闭包没装配起来：\n{out}"
    )
    assert "ERROR" not in out, f"`--setup-plan` 报了 error（fixture 名解析不开就是这个形态）：\n{out}"


# --------------------------------------------------------------------------
# Case 6：四个 acceptance 目录与共享断言模块全在 suite_hash 覆盖之外（guard / S3 / L1）
# --------------------------------------------------------------------------
def test_acceptance_dirs_and_shared_deg_module_are_outside_suite_hash() -> None:
    covered = [c.rstrip("/") for c in covered_paths(hash_command_block(read_soak_log()))]

    def is_covered(rel: str) -> bool:
        return any(c == rel or rel.startswith(c + "/") or c.startswith(rel + "/") for c in covered)

    leaked = [f"{E2E_REL}/{d}" for d in ACCEPTANCE_DIRS if is_covered(f"{E2E_REL}/{d}")]
    assert not leaked, f"这些 acceptance 目录落进了 suite_hash 覆盖面（改一条 DEG 断言就清零 soak）：{leaked}"
    shared_rel = SHARED_DEG_MODULE_PATH.relative_to(REPO_ROOT).as_posix()
    assert not is_covered(shared_rel), (
        f"共享断言模块 {shared_rel} 在 suite_hash 覆盖面内——它只被未激活的组依赖，不该清零 soak"
    )


# --------------------------------------------------------------------------
# Case 7：acceptance_p3 与 acceptance_4a4 的断言主体是同一个函数集合（property / S4 / L1）
# --------------------------------------------------------------------------
def _cross_module_calls(path: Path) -> Dict[str, str]:
    """{被调用的跨模块函数名: 它 import 自哪个模块}。只认 `from X import name` 且 `name(...)` 真的被调用。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in EXCLUDED_IMPORT_PREFIXES:
                continue
            for alias in node.names:
                imported[alias.asname or alias.name] = node.module
    called: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    return {n: m for n, m in imported.items() if n in called}


def _invoked_names(path: Path) -> Set[str]:
    """本文件里**真的被调用**的名字集合（AST，不是文本搜索）。

    收三类：

    1. `f(...)` —— `ast.Call` 的 func 是 `ast.Name`；
    2. `mod.f(...)` —— func 是 `ast.Attribute` 且它的基名是本模块 `import X [as mod]`
       绑定的模块别名（限定基名，避免把 `dict.pop`、`Path.read_text` 之类的方法名
       误当成共享函数）；
    3. `@pytest.mark.parametrize(..., [(f, args), …])` 里作为**值**出现、随后由被装饰
       函数以形参名调用（`runner(...)`）的名字——这是本仓库真实的调用形态，直接要求
       `f(...)` 字面出现会把它误判成「没人调用」。

    **为什么不能用文本搜索。** 原实现是 `re.search(rf"\\b{name}\\b", 全部 unit 源码)`，
    于是一行 `from deg_assertions import run_deg_s1`、一句注释、甚至一段 docstring 里
    提到函数名，都足以「证明」它被跑过。而这条断言要证的恰恰是「在 skip 解开之前，
    有人真的执行过这段共享断言主体」——import 不执行任何东西。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    module_aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                module_aliases.add(a.asname or a.name.split(".")[0])

    invoked: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            invoked.add(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in module_aliases:
                invoked.add(func.attr)

    # (3) parametrize 间接调用。
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        argnames = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
        called_params = {
            c.func.id
            for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in argnames
        }
        if not called_params:
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and _dotted(dec.func).endswith("parametrize")):
                continue
            for sub in ast.walk(dec):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    invoked.add(sub.id)
    return invoked


def _testid_table_keys(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEG_TESTIDS" for t in node.targets):
            assert isinstance(node.value, ast.Dict), f"{path.name} 的 DEG_TESTIDS 不是字典字面量"
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"{path.relative_to(REPO_ROOT)} 没有模块级 `DEG_TESTIDS = {{...}}`")


def _resolve_bare_module(name: str) -> Path:
    for root in (E2E_DIR, REPO_ROOT / "tests" / "fixtures", REPO_ROOT / "tests"):
        cand = root / f"{name}.py"
        if cand.is_file():
            return cand
    raise AssertionError(f"解析不到共享模块 {name!r}（搜索了 tests/e2e、tests/fixtures、tests）")


def test_p3_and_4a4_share_the_same_assertion_body_function_set() -> None:
    p3_files = sorted((E2E_DIR / "acceptance_p3").glob("test_*.py"))
    a4_files = sorted((E2E_DIR / "acceptance_4a4").glob("test_*.py"))
    assert p3_files and a4_files, "两个 DEG 目录里都得有用例模块（WI-17 交付）"

    P: Dict[str, str] = {}
    for f in p3_files:
        P.update(_cross_module_calls(f))
    Q: Dict[str, str] = {}
    for f in a4_files:
        Q.update(_cross_module_calls(f))

    # (1) 集合相等，且非空。相等而不是「交集非空」：交集非空对「各自还有一半私有断言」是盲的。
    assert set(P), "acceptance_p3 没有调用任何跨模块函数——断言主体没有抽出去"
    assert set(P) == set(Q), (
        f"两组的跨模块调用集不相等：只在 p3 的 {sorted(set(P) - set(Q))}，只在 4a4 的 {sorted(set(Q) - set(P))}"
    )

    # (2) 每个共享函数在两组里 import 自同一个模块，且所有 m(f) 相同。
    sources = {P[f] for f in P} | {Q[f] for f in Q}
    for f in P:
        assert P[f] == Q[f], f"{f} 在 p3 来自 {P[f]!r}，在 4a4 来自 {Q[f]!r}——两份同名函数"
    assert sources == {SHARED_DEG_MODULE}, (
        f"共享断言主体应当只来自 {SHARED_DEG_MODULE!r} 一个模块，实际来自 {sorted(sources)}"
    )

    # (3) 共享模块位于两个 acceptance 目录之外。
    shared = _resolve_bare_module(SHARED_DEG_MODULE)
    assert shared == SHARED_DEG_MODULE_PATH, f"共享模块解析到 {shared}，期望 {SHARED_DEG_MODULE_PATH}"
    for d in ACCEPTANCE_DIRS:
        assert (E2E_DIR / d) not in shared.parents, f"共享模块落进了 {d}/"

    # (4) 两组 testid 映射表的键集合相同——值不同是设计使然，键不同就是语义漂移。
    assert len(p3_files) == 1 and len(a4_files) == 1, (
        "DEG 四条应各自集中在一个模块里（p3 一个、4a4 一个），映射表一个目录一份"
    )
    p3_keys = _testid_table_keys(p3_files[0])
    a4_keys = _testid_table_keys(a4_files[0])
    assert p3_keys == a4_keys, (
        f"testid 映射表的键集合不同：只在 p3 的 {sorted(p3_keys - a4_keys)}，只在 4a4 的 {sorted(a4_keys - p3_keys)}"
    )
    assert p3_keys, "映射表是空的"

    # (5) 每个共享函数都有 e2e 之外的**执行**：至少被 tests/unit 下某个文件真的调用
    #     （否则它在解 skip 之前是死代码）。判据是 AST 里的调用表达式，不是文本出现——
    #     一行 import、一句注释、一段 docstring 都不算「跑过」。
    this_file = Path(__file__).resolve()
    invoked_in_unit: Set[str] = set()
    for p in sorted(UNIT_DIR.glob("*.py")):
        if p.resolve() == this_file:
            continue
        invoked_in_unit |= _invoked_names(p)
    uninvoked = sorted(f for f in P if f not in invoked_in_unit)
    assert not uninvoked, (
        "这些共享函数在 tests/unit 下没有任何**调用**（只被 import / 只在注释里出现不算），"
        f"在 skip 解开之前没人跑过它们：{uninvoked}"
    )


# --------------------------------------------------------------------------
# 定向破坏实录（实现落地后回填；只增文本，不改上面的断言行）
# --------------------------------------------------------------------------
SABOTAGE_LOG = """
（实现落地后回填）
"""


# --------------------------------------------------------------------------
# 定向破坏实录（WI-17，2026-09-04）
#
# 本块是**追加**的，不是就地回填：本文件已入红收据 `009-WI-17`（lane unit，
# kind=assertion-failure），按行冻结，改动任何既有行都会把「先写测试」的证据变成一次
# 无法核对的声明。因此上面那个占位 `SABOTAGE_LOG` 原样保留，这里重新绑定同名常量
# ——Python 取最后一次绑定，读到的就是下面这份实录。
#
# 破坏一律在仓库副本上做（scratchpad 下 rsync 一份完整树，排除 .git/.venv/books），
# 用 `python scripts/lint_e2e_groups.py <副本根>` 打靶；真实树全程未改，
# `git diff --quiet -- src/` 通过。每次破坏后都还原并 `diff -q` 与真实树逐字节比对，
# 再重跑守卫确认回到全绿。
#
# **下面两个字符串里的 65 / 89 是誊抄，故意不随常量更新**（2026-09-05 注）：它们是那几次
# 运行的**逐字输出**，当天 baseline 就是 65 条、全量就是 89 条。审计发现 #60 之后常量升到
# 66 / 90，把誊抄一起改掉会把「跑过一次并抄回来」的证据变成一句无法核对的声明——那正是
# §0 第四条纪律要防的东西。要判断誊抄是否过期，看的是上面 `CANONICAL_*` 那几个字面量。
# --------------------------------------------------------------------------
SABOTAGE_LOG = """
副本基线（未破坏）：
  分组守卫：收集 89 条；baseline_1b 65/65；acceptance_4b1 8/8；acceptance_p3 4/4；
  acceptance_4a4 4/4；acceptance_2a 1/1；白名单 7/7；派生总数 89
  分组守卫通过：划分律成立、条数与常量相等、skip 轴静态性质成立。  rc=0

破坏 1 —— 删掉一条 skip 形式用例
  破坏点：移走 tests/e2e/acceptance_4b1/test_w5b_recolor_keeps_id.py（该模块 3 条 item）。
  结果：rc=1。摘要行降为「acceptance_4b1 5/8」，并报：
    [条数] tests/e2e/acceptance_4b1/ 实测 5 条，期望 8 条
      （少了 = 有人删了一条 skip 用例；多了 = 常量没跟着改，改常量要写理由）
  ——目录名与「实测/期望」两个数都在消息里，定位不用猜。
  还原核验：移回原路径，`diff -q` 与真实树一致；重跑 rc=0，8/8 恢复。

破坏 2 —— 往 baseline_1b 的用例函数体里塞一条 skip
  破坏点：在 tests/e2e/baseline_1b/test_kernel_overlay_geometry.py 第 351 行、
  函数 test_k3a_overlay_is_fixed_and_has_no_containing_block_ancestor 的**函数体第一行**
  插入 `pytest.skip("SABOTAGE：临时掏空 baseline")`。选函数体而不是模块顶层，正是为了打
  文件头点名的那个洞：只扫 Module.body 的写法看不见它，收集数还是 89，门槛却已被掏空。
  结果：rc=1（注意条数轴全绿 —— 65/65、89 条，只有 skip 轴响），报：
    [skip 轴·域 R] tests/e2e/baseline_1b/test_kernel_overlay_geometry.py:351
      pytest.skip("SABOTAGE：临时掏空 baseline")
      baseline_1b 的收集可达链上不得有任何 skip 构造（函数体、fixture 体、异常处理器里的
      一并计入）——它会把计入门槛的用例悄悄摘掉
  ——文件名与行号都在消息里。
  还原核验：copy 回备份，`diff -q` 与真实树一致；重跑 rc=0。

破坏 3 —— 让一个白名单条目贡献零条 item
  破坏点：把 tests/e2e/test_harness_smoke.py 改名为 test_harness_smoke_renamed_sabotage.py
  （文件仍在、item 仍被收集，只是白名单里那个名字对不上了）。
  结果：rc=1，三处违规同时响，互相印证：
    [划分律] tests/e2e/test_harness_smoke_renamed_sabotage.py::test_playwright_reaches_epubjs_iframe_content[chromium]
      没有组 marker，且模块不在 UNGROUPED_E2E_MODULES 白名单里——第三种状态不存在
    [白名单] test_harness_smoke.py 在本次收集里一条 item 都没贡献
      （悬空条目 = 给下一个没人管的模块预开的门）
    [条数] 白名单模块实测贡献 6 条，期望 EXPECTED_UNGROUPED_ITEMS = 7
  ——悬空白名单这一条正是要证的那条：名字留在清单里、却不再对应任何 item 时会红。
  还原核验：改回原名，`diff -q` 与真实树一致；重跑 rc=0，白名单 7/7。

结论：条数轴、skip 轴、划分律 ＋ 白名单不空转三条轴各自被单独打红过，失败消息都点到了
文件/目录与期望值。三次破坏全部还原并逐字节核验，真实树 `git status --short` 只剩本次
WI-17 的预期文件，`git diff --quiet -- src/` 通过。
"""


# --------------------------------------------------------------------------
# 审计 D7 的红收据（2026-09-05）
#
# 上面那三次破坏证明的是「守卫对它已经看得见的三类破坏会红」。本轮审计问的是另一个
# 问题：**哪些破坏它当时看不见**。做法是把 `scripts/lint_e2e_groups.py` 的**修改前**
# 版本（`git show HEAD:scripts/lint_e2e_groups.py`）加载进来，对下面八个新变异树逐个
# 跑 `check_tree()`，记录它当时的判定。八个**全部返回空违规列表**——即八条都是零成本、
# 零信号的绕过路径，不是「同类样本更多几个」。修补后八个全红。
#
# `src/` 一字未动；变异树全部建在 `tmp_path` 上。
# --------------------------------------------------------------------------
AUDIT_D7_BYPASS_LOG = """
变异名                                     修改前判定   掏空的是什么
-----------------------------------------  ----------  ------------------------------------
skip-in-root-conftest                      GREEN       域 R 漏了 tests/conftest.py：一条
                                                       autouse fixture 里的 pytest.skip()
                                                       摘掉全部 65 条 baseline，收集数不变
skip-in-transitively-imported-fixture      GREEN       域 R 漏了 import 闭包：helpers.py 引
                                                       的语料模块里的 skip 同样在可达链上
skip-via-direct-import                     GREEN       `from pytest import skip` —— 判据只认
                                                       全限定 `pytest.` 拼写
skip-via-module-alias                      GREEN       `import pytest as pt; pt.skip(...)`
                                                       —— 同上，§8 G2 那句护栏的别名写法
skip-marker-via-module-alias               GREEN       `import pytest as p; @p.mark.skip`
whitelisted-module-moved-into-subdir       GREEN       白名单按 basename 授权：把白名单模块
                                                       挪进 tests/e2e/legacy/，三段条数一条
                                                       不差、划分律照旧成立，该目录从此免检
pytestmark-reassigned-after-skip           GREEN       静态检查只证「有一处合规的 skip 赋值」
                                                       ——第二次赋值覆盖掉它之后，四条 DEG
                                                       用例真的活了过来
reason-names-a-longer-phase-token          GREEN       阶段 token 用 substring 包含判定：
                                                       reason 写 `4B.10` 就冒充了 `4B.1`

另两条（无变异树，形态是 API 缺失 / 计数）：
  collect_items() 当时没有 timeout 形参 —— 收集期挂死时守卫既不红也不绿，永远挂着；
  main() 对同一棵树收集 2 次 —— 与文件头「收集只跑一次」的成本模型直接矛盾。
"""
