"""WI-17 —— DEG-S1…S4 的**设计规格形态**（`acceptance_4a4`，skip 形态，四条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「DEG-S1…S4 × 两种形态」。
任务书 §5 末注：「Phase 3 出口时对朴素形态断言，4A.4 改版后**只改 testid 映射、断言语义不变**」；
§0.5 表：激活阶段 = **4A.4**，不计入 1b 门槛、不进 soak、不进 `suite_hash`。设计规格 §6.4 五条通用要求
＋ §5.4 `DegradeBanner`。

**本文件与 `acceptance_p3/test_deg_states_plain.py` 的差别只有 `DEG_TESTIDS` 的值。** 四个用例体
逐字相同（各自一次 `run_deg_sN(...)`），主体住在 `tests/fixtures/deg_assertions.py`。这不是靠人记住的
约定：`tests/unit/test_e2e_group_guard.py` 第七条断两组的跨模块调用集**相等**、全部来自同一个模块、
该模块在两个 acceptance 目录之外、两张映射表**键集合相同**。有人把 4a4 的断言复制一份改写，那条会红。

**映射表取值**：前端计划 `plan-frontend-ui-refactor.md` §4 WI-2…WI-5 的「涉及 testid」栏——
容器名与朴素形态相同（testid 契约的本意就是「重设计不得改 testid」），差别在主操作按钮换成各自的专名：
`rd-degrade-s1-excerpt`（WI-2）、`lib-degrade-s2-reindex`（WI-3）、`lib-degrade-s3-toggle`（WI-4）。
其余（`rd-note-stale-badge`、`lib-status-stale`、`lib-degrade-s3-list`、`lib-storage-format-badge`）
两形态同名。**这些名字今天都不在模板里**，解 skip 前逐个核对。

**已知限制（矩阵 Deferred 第 13 条）**：第七条守卫断的是跨模块调用集，一个 4a4 模块既调用共享函数又
在文件里私写几行 inline `assert`，守卫看不见。本文件刻意一行 inline assert 都没有，四个函数体只有那一次调用。

**2026-09-05 审计后判据收紧了四处**，全部落在共享主体里（本文件仍是四次调用、零行 inline assert，
p3 那份 docstring 写了逐条理由）：S1 比的是 `GET /api/notes` 交出的**记录身份**而不是条数；S2 的
第五态要求文案含「索引已过期」、重建按钮在**横幅内部**数；S3 的未迁移清单按 `data-book-id` 比集合；
S4 先要求每本新格式书的书卡**恰好 1 张**再断它没戴 pkl 角标（缺卡时那条否定断言是空真的——
这一条审计里由两批独立找出，改在 `run_deg_s4` 一处，两组同时生效）。

**解 skip 的顺序**：4A.4 书库页切片（前端计划 WI-13）、阅读器 DEG 挂载（WI-16）与书库侧 DEG-S3 / S4 延后验收（WI-16b）落地 ⇒ 核对映射表 ⇒
删本文件的 skip 行 ⇒ `-m acceptance_4a4` ⇒ 条数常量不变。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from playwright.sync_api import Page

from conftest import BOOK_ID, E2E_BOOK_IDS  # type: ignore[import-not-found]
from deg_assertions import (  # type: ignore[import-not-found]
    pickle_fallback_server,
    run_deg_s1,
    run_deg_s2,
    run_deg_s3,
    run_deg_s4,
)

pytestmark = [
    pytest.mark.acceptance_4a4,
    pytest.mark.skip(
        reason=(
            "激活阶段 4A.4：DEG-S1…S4 的设计规格形态（DegradeBanner 组件、第五态 StatusPill、"
            "storage_format 角标）要到前端计划 WI-13 / WI-16 / WI-16b 落地才存在。"
            "到期动作：核对本文件 DEG_TESTIDS 与 4A.4 模板/组件里的 testid 一致后删本行；条数常量不变。"
        )
    ),
]

#: 设计规格形态的 testid 映射表。与 p3 那张**键集合相同**，只有主操作按钮三处的值不同。
#: 不加 `: Dict[str, str]` 注解是**有意的**：tests/unit/test_e2e_group_guard.py 的
#: `_testid_table_keys()` 用 AST 只认 `ast.Assign`（其断言原文就是「没有模块级
#: `DEG_TESTIDS = {...}`」），注解形态是 `ast.AnnAssign`，会让那条守卫瞎掉。
#: 该守卫已入红证、按行冻结，所以对齐的是这里。改回注解前先改守卫并重录。
DEG_TESTIDS = {
    # DEG-S1（阅读器）
    "s1_banner": "rd-degrade-s1",
    "s1_excerpt": "rd-degrade-s1-excerpt",
    "s1_stale_badge": "rd-note-stale-badge",
    "s1_notes_rail": "rd-rail-notes",
    "s1_notes_panel": "rd-notes-panel",
    # DEG-S2（书库 ＋ 搜索面板）
    "s2_card": "lib-book-card",
    "s2_status_stale": "lib-status-stale",
    "s2_search_tab": "lib-panel-tab-search",
    "s2_banner": "lib-degrade-s2",
    "s2_reindex": "lib-degrade-s2-reindex",
    # DEG-S3（全局）
    "s3_lib_banner": "lib-degrade-s3",
    "s3_rd_banner": "rd-degrade-s3",
    "s3_toggle": "lib-degrade-s3-toggle",
    "s3_list": "lib-degrade-s3-list",
    # DEG-S4（书库）
    "s4_card": "lib-book-card",
    "s4_badge": "lib-storage-format-badge",
}


@pytest.fixture
def pickle_server(e2e_books_dir: Path, tmp_path: Path) -> Iterator[str]:
    """DEG-S3 专用：第二个服务进程，`READER3_ALLOW_PICKLE=1`。起不来就红（RuntimeError），不 skip。"""
    with pickle_fallback_server(e2e_books_dir, tmp_path) as base:
        yield base


def test_deg_s1_stale_notes_banner_says_paused_not_deleted(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S1（S3 / L2）：与 p3 同一判据，testid 换成设计规格形态。"""
    run_deg_s1(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s2_stale_index_shows_fifth_state_and_search_banner(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S2（S3 / L2）：与 p3 同一判据，testid 换成设计规格形态。"""
    run_deg_s2(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s3_pickle_fallback_warns_on_both_pages(
    page: Page, live_server: str, pickle_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S3（S3 / L2）：与 p3 同一判据，testid 换成设计规格形态。"""
    run_deg_s3(page, live_server, pickle_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s4_legacy_book_card_shows_storage_format_badge(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S4（S3 / L2）：与 p3 同一判据，testid 换成设计规格形态。"""
    run_deg_s4(page, live_server, e2e_books_dir, BOOK_ID, list(E2E_BOOK_IDS), DEG_TESTIDS)
