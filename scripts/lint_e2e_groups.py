"""`tests/e2e/` 分组划分律的**常量定义处**（WI-1 的地基；执行体在 WI-17）。

任务书 §0.5 明写：分组条数「**只允许在 `scripts/lint_e2e_groups.py` 定义/派生一次**，
验收条、守卫脚本、台账产物一律 import」。写死字面量的代价已经付过一次——把
`test_testid_dom_uniqueness.py` 的 7 条漏算成 76，会让 WI-1 的条数断言**在写第一行
009 代码之前就红**，而最省事的修法（删断言或改成 `>=`）恰好把划分律整个掏空。

划分律本身（每个 collected item 恰好落进三类之一：带组 marker / 在白名单里 / 违规）
的**可执行断言在 WI-17**。本次只放常量，不放执行体：WI-1 结束时五个组目录还是空的，
一个此刻就跑的划分检查除了绿以外什么都证明不了。

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
真需要自己的 fixture，先得把那两处裸 import 改掉，不能反过来。
`tests/unit/test_e2e_group_layout.py` 是这条不等价的记录。

**为什么 `EXPECTED_E2E_ITEMS` 必须是派生值，不是字面量 82。** 82 里有 7 条来自
`test_testid_dom_uniqueness.py`——那是 ADR-0014 的运行期唯一性护栏，与 009 无关。
把 82 焊死，等于把那个套件的条数写进 009 的门槛：它将来加一个 parametrize 值，红的
会是 009 的用例，而修法（改 82）与被改的东西毫无关系。派生式只钉三件事：baseline
恰好 61、acceptance 恰好 14、其余 item 的模块必须在白名单里。
"""

from __future__ import annotations

# `tests/e2e/baseline_1b/` 下的期望 item 数（任务书 §0.5 的「条数」小节）。
EXPECTED_BASELINE_ITEMS = 61

# 四个 acceptance 组的期望 item 数合计。11 → 14 的差额来自 `acceptance_4b1` 由 2 变 5：
# W-5 拆 a/b 的裁决把 W-5b 放进该组，且 W-5b 必须在 {marker, wavy, underline} 上参数化。
EXPECTED_ACCEPTANCE_ITEMS = 14

# `tests/e2e/` 根目录下**不带组 marker**的模块白名单。这是唯一的豁免口径：不在这里、
# 又没有组 marker 的 item 一律违规（WI-17 执行）。每一项都必须在某次收集里真的贡献
# item——悬空条目等于给下一个模块预开的门。
UNGROUPED_E2E_MODULES = {
    # harness spike 的落地证据：Playwright 起得来、能读到 epub.js iframe 内的内容。
    # 它是整条 e2e lane 的存活探针，早于分组存在，不属于任何激活阶段。
    "test_harness_smoke.py",
    # ADR-0014 的运行期唯一性护栏：每个有界 testid 在真实 DOM 里只解析出一个节点。
    # 它守的是选择器口径而不是标注行为，与 009 的五个组正交。
    "test_testid_dom_uniqueness.py",
}

# 上面两个白名单模块在一次 `tests/e2e --collect-only` 里贡献的 item 数。
# 2026-09-02 实测 7（smoke 1 + testid 唯一性 6）。它此前从没被记录过——WI-1 是它的
# 记录处。这个数会随 testid 套件自己的增减而变，改它是**正确的修法**；变的是白名单
# 模块的条数，不是 009 的门槛。
EXPECTED_UNGROUPED_ITEMS = 7

# 派生值，不是字面量。见文件头「为什么必须派生」。
EXPECTED_E2E_ITEMS = (
    EXPECTED_BASELINE_ITEMS + EXPECTED_ACCEPTANCE_ITEMS + EXPECTED_UNGROUPED_ITEMS
)
