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

**执行体做五件事**（`check_tree`），任一违规即退出码 1，消息点名 nodeid / 文件:行 / 目录：

- 划分律 ＋ 白名单不空转（`partition_violations`）；
- 条数：`baseline_1b` == `EXPECTED_BASELINE_ITEMS`，四个 acceptance 目录各 ==
  `EXPECTED_ACCEPTANCE_PER_DIR[dir]`，白名单 == `EXPECTED_UNGROUPED_ITEMS`；marker ↔ 目录
  一一对应（`count_violations`）；
- **skip 轴动态性质**（`skip_marker_violations`，读的是探针拿回的**实际生效 marker**）：
  **未激活** acceptance 组的每条 item 上必须真的有 `skip` / `skipif`，**已激活**组
  （`ACTIVATED_ACCEPTANCE_DIRS`）的每条 item 上一个都不许有，每条 baseline item 上一个都
  不许有（`xfail` 一并禁）；
- skip 轴静态性质（`skip_axis_violations`，纯 AST）：
  * 域 R（`baseline_1b` 的**收集可达闭包**：`baseline_domain_files()` 求的 conftest 链
    ＋ import 闭包，见下）里**零** skip 构造——`pytest.skip(` / `pytest.importorskip(` /
    `pytest.xfail(` / `pytest.mark.skip` / `skipif` / `xfail`，**函数体与异常处理器里的一并计入**，
    **且 import 别名一并解析**（`from pytest import skip` / `import pytest as pt`）；
  * **未激活**的 acceptance 目录里每个 `test_*.py` **恰好**一个模块级 `pytestmark` 内的
    `pytest.mark.skip(reason=…)`，reason 非空且点名本组的激活阶段（`4B.1` / `P3` / `4A.4` / `2a`），
    模块内再无其他 skip 构造；**已激活**的 acceptance 目录里**零** skip 构造（与域 R 同款判据）；
  * 五个组目录内没有 `collect_ignore` / `collect_ignore_glob`。

**为什么需要「已激活组」这个口径（`ACTIVATED_ACCEPTANCE_DIRS`，2026-09-19 / 011 WI-5b-2）。**
上面两条 skip 轴原本要求**每一个** acceptance item 都带生效的 skip——「未激活组以 skip 形态
存在」在四个组全都没落地时，与「acceptance 组一律 skip」等价，于是当初就照后者写了。
`acceptance_2a` 的 DEG-S5 写冲突用例解禁并真的跑出 `1 passed` 的那一刻，两者分岔：守卫读到
「模块级 skip 有 0 个」，报的是违规，而它要求的**修法恰恰是把一条已经落地的用例重新关掉**。
判据在这里会给退化背书，所以必须有一处地方记下「哪些组已经激活」，并对它们**反向**判定。
登记表而不是开关：表内的组换的是一条**更严**的判据（零 skip ＋ 必须真的 passed），不是免检
——差别在于，写成免检开关时，「把一个还没落地的组塞进表里」会让那一组同时逃掉两侧。

**为什么静态与动态两条 skip 轴都要有。** 静态那条断的是「源码里写了一个模块级
`pytestmark = [..., pytest.mark.skip(...)]`」——它证明**存在一处赋值**，不证明**收集出来的
item 真的被 skip**。`pytestmark` 在模块里被第二次赋值（或被 `+=` 覆盖成不含 skip 的列表）时，
静态检查照旧只看见那一处合规的赋值，而四个 acceptance 组会**真的跑起来**：起服务、起浏览器、
对着还不存在的 testid 全红，或者更糟——碰巧绿，于是「未激活组以 skip 形态存在」这条契约
无声失效。反过来，动态那条读的是 `item.iter_markers()`，看不见「fixture 体里的
`pytest.skip()`」（那要到运行期才发生，收集期 marker 集合里没有它）。两条轴各自能被单独绕过，
合起来才闭合。

**为什么域 R 是求闭包而不是三条硬编码路径。** 早先的写法是
`[e2e/conftest.py, e2e/helpers.py, baseline_1b/**]`，漏掉了 **`tests/conftest.py`**（根
conftest 对 `tests/e2e` 下的每一条用例都生效）以及它和 `tests/e2e/conftest.py` 各自 import
的 fixture 模块（`tests/fixtures/epub_corpus.py`、`tests/fixtures/ai_stub.py`…）。一条
`@pytest.fixture(autouse=True)` 里的 `pytest.skip(...)` 写进 `tests/conftest.py`，可以把
66 条 baseline 全部摘掉，而旧的域 R 一声不响。`baseline_domain_files()` 因此从
「root→tests→tests/e2e→baseline_1b 的 conftest 链 ＋ helpers ＋ baseline_1b/**」出发，
沿 `import` 求传递闭包，只收 `tests/` 树内的模块（`src/` 不属于测试的 skip 轴，
白名单模块自己的合法 skip 也仍在域外）。

**为什么 skip 检查必须 `ast.walk` 整个模块，不是扫 `Module.body`。** 任务书 §8 G2 的
commit 级护栏点名的那句代码——

    @pytest.fixture(scope="session")
    def live_server(...):
        try:
            proc = _boot()
        except Exception as e:            # 「防御性」，某次 CI 抖动之后加的
            pytest.skip(f"e2e server unavailable: {e}")

在 AST 里的位置是 `Module → FunctionDef → Try → ExceptHandler → Expr → Call`，**深度 5**。
任何只看模块顶层语句或只看 `pytestmark` 赋值的实现都看不见它，而它的后果是 66 条
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
恰好 68、acceptance 恰好 17、其余 item 的模块必须在白名单里。

**常量的变更史**（改数字必须写理由，不要只覆盖）：

- `EXPECTED_BASELINE_ITEMS` 61 → **65**（2026-09-04，WI-17 / 欠账 #2）。61 是 2026-09-01 矩阵
  按 41 个测试函数推算的 collected 数，**预估，不是实测**；WI-1 起刻意不逐 WI 递增（递增会把
  本文件变成 13 路串行写入点，波内并行当场作废）。各模块的参数化条数在实现中漂移（harness
  自测 9、W-5a 8、K-2 11、K-3 6、X-1 4 …），Wave 6 收口后实测 65。「实测 == 常量」的断言由
  `tests/unit/test_e2e_group_guard.py` 承担，本文件的 `check_tree` 同时执行。
- `EXPECTED_BASELINE_ITEMS` 65 → **66**（2026-09-05，审计发现 #60）。009 分支改了
  `library.js` 的 `syncSelectionForBookId`（选择态的选择器从裸的 `[data-book-id="…"]` 限定到
  `.book-card` / `.book-row`），而那是一处**没有判据守着的生产语义变更**。补的判据是
  `tests/e2e/baseline_1b/test_library_nav_and_collections.py::test_x2d_...`，**恰好一条 item**
  ——选中与取消在同一条里做往返，不拆参数化。理由与可失败性证据（S5／S5b／S5c）写在该模块的
  docstring 里。
- `EXPECTED_BASELINE_ITEMS` 66 → **67**（2026-09-06，欠账 #22 兑付，分支 `016`）。修 #22 时
  实测出它的**第二个入口**：`epub-renderer.js` 的 `getFontSettings()` 自己回读 localStorage
  原始值，而边界校验只在 `reader.html` 的 `loadSettings()` 里——写个越界值进去，面板显示 17、
  正文渲染 99px。调换 save/apply 的顺序修不掉它，所以补了一条判据钉「面板与 iframe 同源」：
  `test_read_presentation_anchoring.py::test_r6c_...`，**恰好一条 item**，不做参数化。
  同一天 R-6a 的字号 / 间距两项刺激从两步收回一步（#22 一修，两步就回到原值、净变化为零），
  那是改 `steps` 的内容，**不改条数**。
- `EXPECTED_BASELINE_ITEMS` 67 → **68**（2026-09-21，欠账 #44 / #9 同批）。
  `test_w8a_selection_survives_rerender.py` 从白名单迁入 `baseline_1b`，**恰好一条 item**，
  不做参数化。迁入的时机不是随意挑的：同一个 commit 里 W-5a-③ 要按修好之后的行为改判，
  `baseline_1b/` 反正要动、`suite_hash` 反正要变，两件事合并只清零一次。它当初落在白名单
  就是为了等这一刻，到期条件写在 `UNGROUPED_E2E_MODULES` 那条注释里。
- `EXPECTED_ACCEPTANCE_ITEMS` 14 → **17**（同日，欠账 #14）：R-6 拆 a/b 后 R-6b 三条落进
  `acceptance_4b1`（Wave 4），该目录由 5 变 8。改成按目录定义再求和，是让「哪个目录少了一条」
  在失败消息里直接可读。
- `EXPECTED_ACCEPTANCE_ITEMS` 17 → **26**（2026-09-24，013 WI-9 批 A，用户决定 D5）：新增组
  `shell_4a`（REG-1 基线，验收 A9.10），**实测 9 条 item**（C9.22 按页参数化 ×3、C9.24、C9.25、
  C9.26、C9.38、C9.39 ×2）。它是一个**新的 acceptance 组**而不是白名单模块，理由是它守的是
  Phase 4A 整段的回归门，将来 WI-12 / WI-13 还会往里加，需要自己的按目录条数；它也不进
  `baseline_1b`，因为那会改 `suite_hash` 并清零 soak 计数。它**生而激活**（进
  `ACTIVATED_ACCEPTANCE_DIRS`）：守的是既有页面，没有「等功能落地」的 skip 期。阶段 token
  `4A.0` 只为满足「每组一个 token」的结构约束，激活组上用不到 skip reason。
  `EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 9 → **43**（2026-09-24，013 WI-10，token 与主题层）：
  **实测 +34**——`test_theme_resolution.py` 25（A10.2–A10.8 与 FA-03/04，10 组合参数化）、
  `test_fouc.py` 6（A10.9，DCL 与 body 插入两个采样点 × 3 页）、`test_track_d_wi7.py` 3
  （Track-D 折入 28–30，静态判据，带 `track_d_013` marker）。进 `shell_4a` 而不进白名单：
  它们守的是 Phase 4A 的同一道回归门，且计划把这些 node id 指定在此目录。
  `EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 43 → **44**（2026-09-24，013 WI-10 追加）：
  **实测 +1**——`test_dark_os_legacy_unchanged.py` 1（OS 深色、无存储主题时，library /
  reader 的 REG-1 testid 计算样式等于 671f580 在同一模拟下的独立采集）。同一道回归门，
  进 `shell_4a`。`EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 44 → **71**（2026-09-25，013 WI-12，设置页切片）：
  **实测 +27**（`pytest tests/e2e/shell_4a --collect-only -q` 数出 71）——
  `test_settings_confirm.py` 6（A12.2 / FP-15，三个破坏性动作 × 确认与关闭两条）、
  `test_settings_appearance.py` 7（A12.6–A12.8、FB-S10、WI-10 A10.3 设置页半边）、
  `test_settings_layout.py` 4（A12.4 / FV-08、FV-15 × 3 视口）、`test_settings_testids.py` 1
  （A12.3 DOM 半边）、`test_settings_rows.py` 9（FB-S01..S09、FD-17/18、FA-07）。设置页替换是
  Phase 4A 同一道回归门的一段，计划把这些 node id 指定在此目录。
  `EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 71 → **103**（2026-09-25，013 WI-13，书库页切片）：
  **实测 +32**（`pytest tests/e2e/shell_4a --collect-only -q` 数出 103）——
  `test_library_functional.py` 9（FB-L 收藏夹单飞、批量索引禁用、选择投影、视图互斥、排序、
  搜索去抖、卡片键盘激活 Enter/Space、地标与当前导航）、`test_library_layout.py` 6（1440 三栏、
  1024 右抽屉、390 双抽屉、长标题不溢出 × 3 视口）、`test_library_states.py` 2（空库、筛选为空）、
  `test_library_testids.py` 1（DOM 半边）、`test_library_theme_toggle.py` 7（主题切换 × 与设置页
  互通）、`test_track_d_wi1_page.py` 2（Track-D WI-1 行 1 / 3 / 7 的页面半边）、
  `test_track_d_wi3_page.py` 5（六态胶囊、越界即 unknown、S2 横幅与重建单飞）。书库页替换是
  Phase 4A 同一道回归门的一段。`test_dark_os_legacy_unchanged.py` 仍是 1 条（PAGES 收窄到
  reader，item 数不变）。`EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 103 → **104**（2026-09-25，013 终审 RV-1，FB-S09 D8 余项）：
  **实测 +1**（`pytest tests/e2e/shell_4a --collect-only -q` 数出 104）——
  `test_settings_rows.py::test_provider_save_failure_is_visible`（服务商卡片的保存请求在浏览器里
  被 route 成 500，卡片结果行显示「保存没有成功」与错误态，编辑中的模型值保留）。与 FB-S09 的
  偏好保存失败那一条同属设置页切片，进 `shell_4a`。
  `EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
- `EXPECTED_ACCEPTANCE_PER_DIR["shell_4a"]` 104 → **108**（2026-09-25，013 终审 RV-14，WI-11 验收 4 / 4a）：
  **实测 +4**（`pytest tests/e2e/shell_4a --collect-only -q` 数出 108）——
  `test_toast.py`：C11.07（真实停留等于 `--r3-dwell-toast` 的读值、同一时刻两次触发只剩一个
  `lib-toast`）、C11.08（`emulate_media(reduced_motion="reduce")` 下 token 与默认逐字相等且不为零，
  Toast 仍停留 N 毫秒）、C11.15（加载后把 token 改成 1500 / 7000 毫秒，真实停留跟着走，×2）。
  矩阵早就把这三行派给 e2e lane，此前一直没写。Toast 属于书库页切片，进 `shell_4a`。
  `EXPECTED_UNGROUPED_ITEMS`（55）与 `EXPECTED_BASELINE_ITEMS`（68）不变。
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

#: 六个组 marker，与 `tests/e2e/<marker>/` 目录一一对应（任务书 §0.5 的表是唯一定义处）。
GROUP_MARKERS = (
    "baseline_1b",
    "acceptance_4b1",
    "acceptance_p3",
    "acceptance_4a4",
    "acceptance_2a",
    "shell_4a",
)
BASELINE_MARKER = "baseline_1b"
ACCEPTANCE_MARKERS = GROUP_MARKERS[1:]

# `tests/e2e/baseline_1b/` 下的期望 item 数。**实测值**（变更史见文件头）。
EXPECTED_BASELINE_ITEMS = 68

# 四个 acceptance 目录各自的期望 item 数。合计由此派生，不另写字面量。
#   acceptance_4b1：R-6b ×3（Wave 4）＋ K-1b ＋ K-6b ＋ W-5b ×3（{marker, wavy, underline}，
#                  `toggleMarkerAnnotation` 与 `toggleAnnotation` 是两份独立实现）
#   acceptance_p3 ：DEG-S1…S4 朴素横幅形态
#   acceptance_4a4：DEG-S1…S4 设计规格形态（与 p3 共用断言主体，只换 testid 映射）
#   acceptance_2a ：DEG-S5 写冲突
#   shell_4a      ：013 REG-1 基线（C9.22 ×3、C9.24、C9.25、C9.26、C9.38、C9.39 ×2）＝ 9，
#                  ＋ WI-10 token/主题层 34（主题解析 25、FOUC 6、Track-D WI-7 3）＝ 43，
#                  ＋ WI-10 深色 OS 下旧页不变 1 ＝ 44，＋ WI-12 设置页 27 ＝ 71，
#                  ＋ WI-13 书库页 32 ＝ 103，＋ 终审 RV-1 服务商保存失败 1 ＝ 104，
#                  ＋ 终审 RV-14 Toast 停留（C11.07、C11.08、C11.15 ×2）4 ＝ 108
EXPECTED_ACCEPTANCE_PER_DIR: Dict[str, int] = {
    "acceptance_4b1": 8,
    "acceptance_p3": 4,
    "acceptance_4a4": 4,
    "acceptance_2a": 1,
    "shell_4a": 108,
}
EXPECTED_ACCEPTANCE_ITEMS = sum(EXPECTED_ACCEPTANCE_PER_DIR.values())

#: **已激活**的 acceptance 组目录名。这是一张**登记表，不是开关**。
#:
#: 一个目录进了这张表，就等于宣称「这一组的用例今天必须**真的跑出 passed**」，下面两条
#: skip 轴对它**反向**判定：静态轴要求组内一个 skip 构造都没有（与域 R 同款判据），动态轴
#: 要求它的每条 item 在收集期**没有**任何生效的 skip marker。表外的组维持原判据不变——
#: 「未激活组以 skip 形态存在」。
#:
#: 读作开关就错了：它不是「这一组免检」，而是「这一组换一条更严的判据」。把一个还没落地的
#: 组塞进来，等于让那一组同时逃掉两侧——既不被要求 skip，也没人真的在跑它，而条数轴数的是
#: collected，照样满分。所以往表里加名字的动作和改条数常量一样要写理由。
#:
#: 谁在什么时候该动它：某个组的 skip 被解禁、那一组的用例在 e2e lane 上真的转绿的**同一次**
#: 改动里，往表里加它的目录名（并同步 `tests/unit/test_e2e_group_guard.py` 里独立钉的那一份，
#: 两处相等由那个文件执行）。反过来要把一组关回去，先把名字从表里删掉，再加模块级 skip。
#: 后续 `acceptance_4b1`（阶段 4B.1）/ `acceptance_p3`（P3）/ `acceptance_4a4`（4A.4）解禁时
#: 各往里加一个名字；表满四个之日，`PHASE_TOKEN_FOR_DIR` 那条 reason 判据就再没有落点了。
#:
#: 变更史：
#: - `acceptance_2a` 进表（2026-09-19，011 WI-5b / WI-5b-2）。DEG-S5 写冲突对话框落地，
#:   `test_deg_s5_write_conflict.py` 的模块级 skip 删除后实测 `1 passed`。它是本仓历史上
#:   **第一个**被激活的 acceptance 组，「已激活组」这个口径也是因它而生：在它之前，两条轴
#:   要求**每一个** acceptance item 都带生效的 skip，于是解禁本身被读成违规。
#: - `shell_4a` 进表（2026-09-24，013 WI-9 批 A）。REG-1 基线守的是 `671f580` 的既有页面，
#:   建组即实测 `9 passed`，从来没有 skip 形态。
ACTIVATED_ACCEPTANCE_DIRS: FrozenSet[str] = frozenset({"acceptance_2a", "shell_4a"})

# `tests/e2e/` 下**不带组 marker**的模块白名单。这是唯一的豁免口径：不在这里、
# 又没有组 marker 的 item 一律违规。每一项都必须在本次收集里真的贡献 item——悬空条目
# 等于给下一个模块预开的门。
#
# **写的是仓库相对路径，不是 basename。** 按 `Path(...).name` 授权时，把
# `tests/e2e/test_harness_smoke.py` 移进任意一个没人管的子目录（`tests/e2e/legacy/`、
# `tests/e2e/wip/`…）——三段条数一条不差、划分律照旧成立、守卫全绿，而那个目录从此
# 是一块治外之地：往里再放模块只要重名就自动获得豁免。授权口径必须钉到**位置**上。
UNGROUPED_E2E_MODULES = {
    # harness spike 的落地证据：Playwright 起得来、能读到 epub.js iframe 内的内容。
    # 它是整条 e2e lane 的存活探针，早于分组存在，不属于任何激活阶段。
    "tests/e2e/test_harness_smoke.py",
    # ADR-0014 的运行期唯一性护栏：每个有界 testid 在真实 DOM 里只解析出一个节点。
    # 它守的是选择器口径而不是标注行为，与 009 的五个组正交。
    "tests/e2e/test_testid_dom_uniqueness.py",
    # 欠账 #43 part (i)：notes 写失败的可归因性（诊断环 / 单串 console.error / 单例 toast）。
    # 放白名单而不是 `baseline_1b`，理由与当年 w8a 一样是 `suite_hash` 覆盖面——迁进冻结
    # 目录就要清零 soak 计数。到期条件：下一次**本来就要**动 `baseline_1b/`、`suite_hash`
    # 无论如何都要变的改动里，把本文件一并迁入并撤掉这一条（`EXPECTED_BASELINE_ITEMS` 同批加）。
    "tests/e2e/test_notes_write_failure_is_attributable.py",
    # 017 WI-5（审计 #3、#9）：快照回落写下的 `cfi` 不得是一条失效 Range 算出来的。
    # 内容上它是 W-8a 家族（写路径、同一个「重绘作废选区」现场），但判据问的是**屏幕**
    # 而不是盘。落白名单的理由与上面那条一字不差：迁进 `baseline_1b/` 会改 `suite_hash`
    # 并把 soak 计数清零。到期条件也一样——下一次本来就要动 `baseline_1b/` 的改动里
    # 一并迁入，同批撤掉这一条并给 `EXPECTED_BASELINE_ITEMS` 加上去。
    "tests/e2e/test_stored_cfi_must_agree_with_quote.py",
    # 017 WI-6（审计 #5）：冲突对话框同一时刻只许有一次收尾在飞。它驱动的是 DEG-S5
    # 对话框，与 `acceptance_2a/test_deg_s5_write_conflict.py` 同一块 UI，但那一条是
    # **激活阶段**的验收（两个真上下文、服务端会不会 409、两支的去向），本条是单个
    # 上下文里两次点击之间的并发，两者判据不重叠，也就不该并进那个组、改它的
    # `EXPECTED_ACCEPTANCE_PER_DIR`。落白名单的理由与上面两条一字不差：迁进
    # `baseline_1b/` 会改 `suite_hash` 并把 soak 计数清零；到期条件同样是「下一次本来
    # 就要动 `baseline_1b/` 的改动里一并迁入，同批撤条目并给 `EXPECTED_BASELINE_ITEMS`
    # 加上去」。
    "tests/e2e/test_conflict_resolution_single_flight.py",
    # 017 WI-7（审计 #4）：收尾放进编辑器的那一版，必须连着它自己的基准令牌。与上一条
    # 同住 DEG-S5 对话框，但问的是**收尾之后**那次保存带的是哪一版令牌，不是两次点击之间
    # 的并发；和 `acceptance_2a` 那条激活验收同样不重叠。落白名单的理由与上面三条一字不差：
    # 迁进 `baseline_1b/` 会改 `suite_hash` 并把 soak 计数清零；到期条件同样是「下一次本来
    # 就要动 `baseline_1b/` 的改动里一并迁入，同批撤条目并给 `EXPECTED_BASELINE_ITEMS`
    # 加上去」。
    "tests/e2e/test_conflict_settled_text_keeps_its_base_etag.py",
    # 选区工具条关掉之后不得被 epub.js 的下一拍 `selected` 重新打开（K2 copy 的 soak 抖动）。
    # 内容上它是 K-2 家族，落白名单的理由与上面几条一字不差：迁进 `baseline_1b/` 会改
    # `suite_hash` 并把 soak 计数清零；到期条件同样是「下一次本来就要动 `baseline_1b/` 的
    # 改动里一并迁入，同批撤条目并给 `EXPECTED_BASELINE_ITEMS` 加上去」。
    "tests/e2e/test_selection_toolbar_stays_closed.py",
    # 009 #49（019 WI-2，WI2-E2）：盘上轮询期间，在途的写必须出得了门——钉的是
    # `wait_for_notes` 泵浏览器这件机制本身（旧 `time.sleep` 循环体上它确定地红）。
    # 不并进 `baseline_1b/`：它是 helpers 的机制护栏，不是 009 的业务用例；且根下新文件
    # 不在 `HASH_COVERED_PATHS` 里，放这里不额外移动 `suite_hash`。到期条件：无——
    # 它与任何组都正交，是长期住户（与 `test_testid_dom_uniqueness.py` 同类）。
    "tests/e2e/test_disk_poll_pumps_inflight_write.py",
}

# 上面几个白名单模块在一次 `tests/e2e --collect-only` 里贡献的 item 数。
# 2026-09-02 实测 7（smoke 1 + testid 唯一性 6）。这个数会随白名单模块自己的增减而变，
# 改它是**正确的修法**；变的是白名单模块的条数，不是 009 的门槛。
#
# 7 → **8**（2026-09-20，欠账 #44）：新增
# `tests/e2e/test_w8a_selection_survives_rerender.py`，**恰好一条 item**，不做参数化。
# 它落在白名单而不是 `baseline_1b` 是一笔带到期条件的明账，理由是 `suite_hash` 覆盖面。
#
# 8 → **7**（2026-09-21）：**上面那笔明账到期兑付。** W-5a-③ 的改判本来就要动
# `baseline_1b/`、`suite_hash` 无论如何都要变，所以把这个文件一并迁进去，省掉第二次清零
# ——这正是那条注释写的到期条件。白名单条目已撤，`EXPECTED_BASELINE_ITEMS` 同批 +1。
#
# 7 → **17**（2026-09-22，欠账 #43 part (i) 第一批 = 011 WI-1/WI-2）：新增
# `tests/e2e/test_notes_write_failure_is_attributable.py`。**17 − 7 = 10 是执行过的
# `--collect-only` 实测值，只算这一批**；矩阵预测全部落地后该模块是 37 条，WI-3..WI-7
# 每一批落地时各自再改这里一次，每次都写实测值，不预支。
#
# 17 → **23**（2026-09-22，欠账 #43 part (i) WI-3 = `saveNote()` PUT 编辑分支）：该模块
# 10 → 16 条，**+6 是执行过的 `--collect-only` 实测值**（W3-C1、W3-C3×2、W3-C6、W3-C4、W3-C5）。
#
# 23 → **31**（2026-09-22，欠账 #43 part (i) WI-4 = `deleteAnnotations()` ＋ 改色调用方
# `toggleAnnotation`，修订 A2）：该模块 16 → 24 条，**+8 是执行过的 `--collect-only` 实测值**
# （W4-C1、W4-C2、W4-C3×2、W4-C5、W4-C6、W4-C7、W4-C4；全量 116）。
#
# 31 → **36**（2026-09-22，欠账 #43 part (i) WI-5 = `resolveConflict()` 的「保留我的」写，
# 修订 A1）：该模块 24 → 29 条，**+5 是执行过的 `--collect-only` 实测值**
# （W5-C1、W5-C2、W5-C3、W5-C4×2；全量 121）。
#
# 36 → **43**（2026-09-22，欠账 #43 part (i) WI-6 = 请求前的静默出口，修订 A3）：该模块
# 29 → 36 条，**+7 是执行过的 `--collect-only` 实测值**
# （W6-C1、W6-C4×2、W6-C5×2、W6-C2、W6-C3；全量 128）。W6-C6 在 unit 道，不计入这里。
#
# 43 → **44**（2026-09-22，欠账 #43 part (i) WI-7 = 成功路径护栏 建 → 改 → 删，不装路由）：
# 该模块 36 → 37 条，**+1 是执行过的 `--collect-only` 实测值**（W7-C1；全量 129）。
# 矩阵 §10 预测的 37 条至此全部落地，与实测一致。
#
# 44 → **47**（2026-09-23，017 WI-5 = 审计 #3 / #9）：新增
# `tests/e2e/test_stored_cfi_must_agree_with_quote.py`，**+3 是执行过的
# `--collect-only` 实测值**（当场一次、刷新一次、外加一条「没有重绘介入时照旧写得出
# 能重锚的 cfi」的退化护栏）。三条都不参数化。#
# 47 → **51**（2026-09-23，017 WI-6 = 审计 #5）：新增
# `tests/e2e/test_conflict_resolution_single_flight.py`，**+4 是执行过的
# `--collect-only` 实测值**。四条对应三层防线各一条（按钮 `disabled`、
# `conflictSubmitting` 单飞守卫、写回来之后的冲突身份核对）外加一条「没有并发干扰时
# 照旧写盘收尾并放开按钮」的退化护栏；三层各自被逐一注掉验证过只红对应的那一条。
#
# 51 → **55**（2026-09-23，017 WI-7 = 审计 #4）：新增
# `tests/e2e/test_conflict_settled_text_keeps_its_base_etag.py`，**+4 是执行过的
# `--collect-only` 实测值**。一条钉住静默覆盖本身，两条钉住这枚基准令牌的另外两条边界
# （跟着自己的写前进、随编辑会话结束而清空），外加一条「没有第三方时照旧保存成功」的
# 退化护栏；三条边界各自被逐一破坏验证过只红对应的那一条。
#
# 55 → **63**（2026-09-28，fix/selection-toolbar-reopen）：新增
# `tests/e2e/test_selection_toolbar_stays_closed.py`，**+8 是执行过的 `--collect-only`
# 实测值**（四条关闭路径 copy / ask_ai / escape / outer_mousedown × 两个时机
# after_first_tick / before_first_tick；全量 256）。
#
# 63 → **71**（2026-09-30，009 #50，WI-1 of 019: +8）：白名单里已登记的
# `tests/e2e/test_notes_write_failure_is_attributable.py` 新增 8 条 item（W1-C11 / W1-C12 /
# W1-C13 各 1、W6-C6 ×2、W6-C7 ×2、W6-C8 1；W1-C8 是原地改判，不增条数）。**+8 是执行过的
# `--collect-only` 实测值**（baseline 68 / 白名单 71 / 全量 264）。
#
# 71 → **72**（2026-09-30，009 #49，WI-2 of 019: +1）：新增
# `tests/e2e/test_disk_poll_pumps_inflight_write.py`（WI2-E2，1 条，不参数化）。**+1 是执行过的
# `--collect-only` 实测值**（baseline 68 / 白名单 72 / 全量 265）。
EXPECTED_UNGROUPED_ITEMS = 72

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
    "shell_4a": "4A.0",
}
PHASE_TOKEN_RE = re.compile(r"4B\.1|P3|4A\.4|2a|4A\.0")

#: 阶段 token 必须整体出现，不能只是别人的前缀。`"4B.1" in "阶段 4B.10 再说"` 为真，
#: 于是一条把激活阶段写成 4B.10 的 reason 就能冒充 4B.1 的登记——substring 包含在这里
#: 不是判据。左右两侧只挡 ASCII 词字符与点号：中文紧邻（`阶段4B.1：`）仍算命中。
_PHASE_BOUNDARY = "[0-9A-Za-z_.]"


def phase_token_matches(reason: str, token: str) -> bool:
    """`token` 是否作为一个**完整**的阶段标识出现在 `reason` 里（`4B.10` 不算 `4B.1`）。"""
    if not token:
        return False
    return re.search(
        rf"(?<!{_PHASE_BOUNDARY}){re.escape(token)}(?!{_PHASE_BOUNDARY})", reason
    ) is not None


_SKIP_CALLS = ("pytest.skip", "pytest.importorskip", "pytest.xfail")
_SKIP_MARKS = ("pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail")
_COLLECT_IGNORE_NAMES = {"collect_ignore", "collect_ignore_glob"}

#: 收集期**实际生效**的 skip 类 marker 名（`item.iter_markers()` 里的名字，不是源码拼写）。
EFFECTIVE_SKIP_MARKERS = frozenset({"skip", "skipif"})
#: baseline 上一条都不许有：`xfail` 同样能让一条计入门槛的用例不再产出 `passed`。
BASELINE_FORBIDDEN_MARKERS = frozenset({"skip", "skipif", "xfail"})

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
DEFAULT_E2E_DIR = "tests/e2e"
PROBE_PLUGIN = "e2e_group_probe"
PROBE_PREFIX = "E2E_GROUP_PROBE"

#: 收集子进程的墙钟上限（秒）。没有它，`tests/e2e/conftest.py` 里一个阻塞 import
#: （轮询一个永不就绪的端口、等一个不存在的服务）会让分组闸**永远挂着**——CI 上表现为
#: 一个没有输出、没有退出码、也不会红的作业，比直接报错难诊断得多。超时翻译成
#: `CollectionError`，与「退出码非零」「零 item」同一条出口。
COLLECT_TIMEOUT_S = 300.0


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


def normalize_module(module: str) -> str:
    """把一个模块路径规范成仓库相对的 posix 形式（`./a\\b.py` → `a/b.py`），供白名单比对。"""
    text = str(module).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return Path(text).as_posix()


def collect_items(
    root: Path, e2e_dir: str = DEFAULT_E2E_DIR, *, timeout: float = COLLECT_TIMEOUT_S
) -> List[CollectedItem]:
    """在 `root` 下对 `e2e_dir` 跑**一次** `--collect-only`，经探针插件取回每个 item 的 marker 集合。

    不起服务、不起浏览器。退出码 0 且至少一条 item 才算成功；5（一条都没收到）、超时、
    其他非零一律抛 `CollectionError` 并附带输出——「守卫在空集上通过」正是 soak 数空集的
    发生方式，「守卫永远挂着」则连空集都数不出来。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SCRIPTS_DIR), env.get("PYTHONPATH", "")) if p
    )
    try:
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
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = "".join(
            s.decode("utf-8", "replace") if isinstance(s, bytes) else (s or "")
            for s in (exc.stdout, exc.stderr)
        )
        raise CollectionError(
            f"`pytest {e2e_dir} --collect-only` 在 {root} 下超时（>{timeout:g}s）并已被终止："
            "收集期挂死（阻塞的 import、等一个永不就绪的端口）会让分组闸既不红也不绿，"
            f"比非零退出码更难诊断。已捕获的输出：\n{partial}"
        ) from exc
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
        items.append(CollectedItem(nodeid=nodeid, module=normalize_module(module), markers=markers))
    if not items:
        raise CollectionError(f"`pytest {e2e_dir} --collect-only` 在 {root} 下一条 item 都没收到：\n{out}")
    return items


# ---------------------------------------------------------------------------
# 划分律 ＋ 白名单
# ---------------------------------------------------------------------------


def partition_violations(
    items: Sequence[CollectedItem], *, ungrouped_modules: Iterable[str] = UNGROUPED_E2E_MODULES
) -> List[str]:
    """条 (1) 划分：恰好一个组 marker，或模块在白名单里；双 marker 也红。条 (2) 白名单不得空转。

    白名单按**仓库相对路径**比对，不按 basename：见 `UNGROUPED_E2E_MODULES` 的注释。
    """
    whitelist = {normalize_module(m) for m in ungrouped_modules}
    out: List[str] = []
    for it in items:
        groups = it.group_markers()
        if len(groups) >= 2:
            out.append(
                f"[划分律] {it.nodeid} 同时带多个组 marker {sorted(groups)}——一条用例计入两道门槛，两边都会误报"
            )
        elif not groups and normalize_module(it.module) not in whitelist:
            out.append(
                f"[划分律] {it.nodeid} 没有组 marker，且模块 {normalize_module(it.module)} 不在 UNGROUPED_E2E_MODULES 白名单里"
                "——第三种状态不存在：要么加组 marker，要么显式登记（白名单认路径，改名或挪目录都要同步改）"
            )
    contributed = {normalize_module(it.module) for it in items if not it.group_markers()}
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
    whitelist = {normalize_module(m) for m in ungrouped_modules}

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
            1 for it in items if not it.group_markers() and normalize_module(it.module) in whitelist
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


def pytest_aliases(tree: ast.Module) -> Dict[str, str]:
    """模块里每个「最终指向 pytest 的名字」→ 它的规范全名。

    只认全限定 `pytest.` 拼写的判据有两个免费出口，都不需要任何权限：

        from pytest import skip          # 然后函数体里一句 `skip("flaky")`
        import pytest as pt              # 然后 `pt.skip(...)` / `@pt.mark.skip`

    两种写法在语义上与 `pytest.skip(...)` 完全等价，在 AST 里却根本不含 `pytest` 这个
    Name 节点。域 R 的「零 skip」如果只挡后者，等于把门锁在没有墙的地方。
    """
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name != "pytest" and not a.name.startswith("pytest."):
                    continue
                # `import pytest` 绑定的是首段 `pytest`；`import pytest.mark as m` 绑定 `m`。
                aliases[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module != "pytest" and not node.module.startswith("pytest."):
                continue
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    return aliases


def _canonical(node: ast.AST, aliases: Mapping[str, str]) -> str:
    """`_dotted()` 的结果按 `aliases` 还原成 `pytest.…` 全名；无别名时原样返回。"""
    dotted = _dotted(node)
    if not dotted:
        return ""
    head, _, rest = dotted.partition(".")
    base = aliases.get(head)
    if base is None:
        return dotted
    return f"{base}.{rest}" if rest else base


def _skip_constructs(path: Path, root: Path) -> List[str]:
    """`ast.walk` 整个模块，凡解析为 `pytest.skip(`/`importorskip(`/`xfail(` 的调用，或
    `pytest.mark.skip`/`skipif`/`xfail` 的属性链，一律计入——**import 别名先还原**。
    返回 `file:line  源码切片`。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = pytest_aliases(tree)
    rel = path.relative_to(root).as_posix()
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _canonical(node.func, aliases) in _SKIP_CALLS:
            hits.append(f"{rel}:{node.lineno}  {_source_line(path, node.lineno)}")
        elif isinstance(node, ast.Attribute) and _canonical(node, aliases) in _SKIP_MARKS:
            hits.append(f"{rel}:{node.lineno}  {_source_line(path, node.lineno)}")
        elif (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and aliases.get(node.id, "") in _SKIP_MARKS
        ):
            # `from pytest.mark import skip` 之后裸 `skip` 就是那个 marker 对象。
            hits.append(f"{rel}:{node.lineno}  {_source_line(path, node.lineno)}")
    # 同一行同时命中 Call 与 Attribute（`pytest.mark.skip(...)`）时只报一次。
    return sorted(set(hits), key=lambda s: (s.split(":")[0], int(s.split(":")[1].split()[0])))


def _module_level_skip_marks(tree: ast.Module) -> List[ast.Call]:
    aliases = pytest_aliases(tree)
    calls: List[ast.Call] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        for v in values:
            if isinstance(v, ast.Call) and _canonical(v.func, aliases) == "pytest.mark.skip":
                calls.append(v)
    return calls


# ---------------------------------------------------------------------------
# 域 R：baseline_1b 的收集可达闭包
# ---------------------------------------------------------------------------


def _resolve_import_target(name: str, search_roots: Sequence[Path]) -> Optional[Path]:
    rel = Path(*name.split("."))
    for base in search_roots:
        cand = base / f"{rel}.py"
        if cand.is_file():
            return cand
        pkg = base / rel / "__init__.py"
        if pkg.is_file():
            return pkg
    return None


def baseline_domain_files(root: Path, e2e_dir: str = DEFAULT_E2E_DIR) -> List[Path]:
    """域 R：收集 `baseline_1b` 时会被 import 的**全部测试侧模块**。

    种子 = 从仓库根一路到 `baseline_1b/` 的 conftest 链（`conftest.py`、`tests/conftest.py`、
    `tests/e2e/conftest.py`、`tests/e2e/baseline_1b/conftest.py`）＋ `tests/e2e/helpers.py`
    ＋ `baseline_1b/**.py`；然后沿 `import` 求传递闭包，按 pytest 的裸模块名解析顺序
    （`tests/e2e/` → `tests/fixtures/` → `tests/`，后两者由 root conftest 插进 `sys.path`）。

    闭包只收 `tests/` 树内的文件：`src/` 不是测试的 skip 轴，白名单模块（
    `test_testid_dom_uniqueness.py` 等）自己的合法环境性 skip 也仍在域外——那正是
    「域 R 是收集可达而不是整个 tests/e2e」这条边界的意义。
    """
    e2e = root / e2e_dir
    tests_dir = root / "tests"
    seeds: List[Path] = []
    for d in (root, tests_dir, e2e, e2e / BASELINE_MARKER):
        c = d / "conftest.py"
        if c.is_file():
            seeds.append(c)
    helpers = e2e / "helpers.py"
    if helpers.is_file():
        seeds.append(helpers)
    if (e2e / BASELINE_MARKER).is_dir():
        seeds += sorted((e2e / BASELINE_MARKER).rglob("*.py"))

    search_roots = [e2e, tests_dir / "fixtures", tests_dir]
    seen: Dict[Path, Path] = {}
    stack = list(seeds)
    while stack:
        f = stack.pop()
        if not f.is_file():
            continue
        key = f.resolve()
        if key in seen:
            continue
        seen[key] = f
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names: List[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                # `from X import a, b`：X 本身，以及 `X.a`（子模块形态）都试一遍。
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for n in names:
                target = _resolve_import_target(n, search_roots)
                if target is None:
                    continue
                try:
                    target.resolve().relative_to(tests_dir.resolve())
                except (ValueError, OSError):
                    continue
                stack.append(target)
    return sorted(seen.values(), key=lambda p: p.as_posix())


def skip_axis_violations(
    root: Path,
    e2e_dir: str = DEFAULT_E2E_DIR,
    *,
    activated_dirs: Iterable[str] = ACTIVATED_ACCEPTANCE_DIRS,
) -> List[str]:
    """条件 1–5（矩阵 Unit A 第四条）。域 R 零 skip；无 collect_ignore；acceptance 按
    `ACTIVATED_ACCEPTANCE_DIRS` 分两侧判——**未激活**组只许一个模块级带 reason 的 skip，
    **已激活**组一个 skip 构造都不许有。"""
    e2e = root / e2e_dir
    activated = set(activated_dirs)
    out: List[str] = []

    # ---- 域 R：baseline_1b 的收集可达闭包（conftest 链 ＋ import 闭包）--------------
    domain_r: List[Path] = baseline_domain_files(root, e2e_dir)
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
            if group in activated:
                # 已激活组：与域 R 同款判据——整组零 skip 构造，用例模块与辅助模块一视同仁。
                # 这里 `group` 就是目录名（`gdir = e2e / group`），不经过 marker 名。
                for hit in _skip_constructs(f, root):
                    out.append(
                        f"[skip 轴·已激活组] {hit}\n"
                        f"    {group} 已登记在 ACTIVATED_ACCEPTANCE_DIRS 里"
                        "（= 这一组今天必须真的跑出 passed），组内不得有任何 skip 构造"
                        "——留着的那一条会让一条已宣称激活的用例静默消失，而条数轴数的是 collected，"
                        "照样满分。要把这一组重新关掉，先把它从登记表里删掉并写明理由，"
                        "而不是在这里补一个 skip"
                    )
                continue
            hits = _skip_constructs(f, root)
            if not f.name.startswith("test_"):
                for hit in hits:
                    out.append(f"[skip 轴·acceptance] {hit}\n    非用例模块里不得有 skip 构造")
                continue
            marks = _module_level_skip_marks(tree)
            if len(marks) != 1:
                out.append(
                    f"[skip 轴·未激活组] {rel}: 模块级 pytestmark 里的 pytest.mark.skip 有 {len(marks)} 个，应恰好 1 个"
                    f"——{group} 不在 ACTIVATED_ACCEPTANCE_DIRS 里，未激活组以 skip 形态存在，"
                    "skip 只允许挂在模块级 pytestmark 上。"
                    "若这一组**已经**解禁并在 e2e lane 上真的转绿，正确的修法是把它登记进"
                    "ACTIVATED_ACCEPTANCE_DIRS（那一侧要求整组零 skip），不是把 skip 加回来"
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
            elif not phase_token_matches(reason, PHASE_TOKEN_FOR_DIR.get(group, "")):
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
# skip 轴动态性质（读探针拿回的实际生效 marker）
# ---------------------------------------------------------------------------


def group_dir_of(item: CollectedItem, e2e_dir: str = DEFAULT_E2E_DIR) -> Optional[str]:
    """item 所属的组**目录名**——从模块路径读，**不**从 marker 名猜。

    `ACTIVATED_ACCEPTANCE_DIRS` 按目录名索引，而 item 侧手里只有 marker 名
    （`acceptance_2a`…）。今天本仓五个组的 marker 名与目录名同形，直接拿 marker 当目录名
    去查表也能对——但那是**巧合，不是映射**。marker 与目录的对应关系由 `GROUP_MARKERS`
    那句「与 `tests/e2e/<marker>/` 目录一一对应」定义、由 `count_violations` 的 marker↔目录
    轴执行；一旦某个组把 marker 改成与目录不同名，拿 marker 查表会让登记表**静默地对谁都
    不生效**：已激活组既不被要求 passed，也不再被要求 skip，两条轴同时对它闭嘴，而条数轴
    数的是 collected，什么都看不出来。目录归属的定义处是模块路径，所以从它读。
    """
    prefix = f"{e2e_dir.rstrip('/')}/"
    rel = normalize_module(item.module)
    if not rel.startswith(prefix):
        return None
    head = rel[len(prefix) :].split("/", 1)[0]
    return head if head in GROUP_MARKERS else None


def skip_marker_violations(
    items: Sequence[CollectedItem],
    *,
    e2e_dir: str = DEFAULT_E2E_DIR,
    activated_dirs: Iterable[str] = ACTIVATED_ACCEPTANCE_DIRS,
) -> List[str]:
    """**未激活** acceptance 组的每条 item 必须真的带生效的 skip marker；**已激活**组的
    每条 item 一个都不许带；baseline 的一条都不许带。

    静态那条（`skip_axis_violations`）证明的是「源码里有一处合规的
    `pytestmark = [..., pytest.mark.skip(reason=…)]` 赋值」。那不等于「item 被 skip」——

        pytestmark = [pytest.mark.acceptance_p3, pytest.mark.skip(reason="激活阶段 P3…")]
        ...
        pytestmark = [pytest.mark.acceptance_p3]     # 调试时加的，忘了删

    第二次赋值胜出，四条 DEG 用例当场活了过来（对着还不存在的 testid 去起浏览器），
    而静态检查只看见第一处赋值，全绿。这条读的是 `item.iter_markers()` 的结果，
    是「未激活组以 skip 形态存在」这句契约的**唯一**可判定形式。
    """
    out: List[str] = []
    acceptance = set(ACCEPTANCE_MARKERS)
    activated = set(activated_dirs)
    for it in items:
        groups = it.group_markers()
        effective = set(it.markers) & EFFECTIVE_SKIP_MARKERS
        # 目录名从模块路径读，不拿 marker 名冒充（见 `group_dir_of` 的 docstring）。
        gdir = group_dir_of(it, e2e_dir)
        if groups & acceptance and gdir is not None and gdir in activated:
            if effective:
                out.append(
                    f"[skip 轴·生效·已激活组] {it.nodeid} 属于已激活组 {gdir}"
                    f"（ACTIVATED_ACCEPTANCE_DIRS），收集期却带着生效的 skip marker"
                    f" {sorted(effective)}（实际 marker：{sorted(it.markers)}）"
                    "——登记进那张表等于宣称这一组今天必须真的跑出 passed；"
                    "带着 skip 的它一条 passed 都不产出，而条数轴数的是 collected，照样满分"
                )
        elif groups & acceptance and not effective:
            out.append(
                f"[skip 轴·生效] {it.nodeid} 带 acceptance marker {sorted(groups & acceptance)}，"
                f"收集期却没有任何生效的 skip marker（实际 marker：{sorted(it.markers)}）"
                "——未激活组必须以 skip 形态存在；模块级 pytestmark 被二次赋值覆盖时，"
                "静态检查看不见，这条看得见"
            )
        forbidden = set(it.markers) & BASELINE_FORBIDDEN_MARKERS
        if BASELINE_MARKER in groups and forbidden:
            out.append(
                f"[skip 轴·生效] {it.nodeid} 是 baseline_1b，却带 {sorted(forbidden)} marker"
                "——计入门槛的用例一旦不产出 passed，G2 的分母就被悄悄改小了"
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
    activated_dirs: Iterable[str] = ACTIVATED_ACCEPTANCE_DIRS,
    items: Optional[Sequence[CollectedItem]] = None,
) -> List[str]:
    """对 `root/e2e_dir` 跑全部检查，返回违规列表（空 = 绿）。收集失败本身也是一条违规。

    `items` 已经收过一次时传进来即可：本脚本的成本模型是「**一次** `--collect-only`」
    （文件头「收集只跑一次」一节），`main()` 先收一次打摘要、再让 `check_tree()` 自己
    又收一次，等于把那条设计悄悄改成两次冷启动。
    """
    root = Path(root)
    violations: List[str] = []
    if items is None:
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
        violations += skip_marker_violations(
            items, e2e_dir=e2e_dir, activated_dirs=activated_dirs
        )
    violations += skip_axis_violations(root, e2e_dir, activated_dirs=activated_dirs)
    return violations


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(args[0]).resolve() if args else ROOT
    try:
        items = collect_items(root)
    except CollectionError as exc:
        print(f"分组守卫：收集失败\n{exc}")
        return 1
    violations = check_tree(root, items=items)
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
