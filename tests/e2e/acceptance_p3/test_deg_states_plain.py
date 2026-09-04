"""WI-17 —— DEG-S1…S4 的**朴素横幅形态**（`acceptance_p3`，skip 形态，四条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「DEG-S1…S4 × 两种形态」。
任务书：`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §5（制造方式与断言表）、
§0.5（激活阶段 = **Phase 3 出口**，不计入 1b 门槛、不进 soak、不进 `suite_hash`）、§0 第三条纪律
（降级正向证据：**主动制造**降级条件，「没有横幅」不是证据）。设计规格：
`docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` §6.4（五条通用设计要求，尤其第 5 条
「朴素优先：Phase 3 的退出门槛只要求 DEG-S1–DEG-S4 **可见**，哪怕先落到现有 Jinja 模板的朴素横幅」）。

**断言主体不在本文件里。** 四条各自是 `tests/fixtures/deg_assertions.py` 里 `run_deg_sN(...)` 的一次
调用，本文件只贡献 **testid 映射表** `DEG_TESTIDS` 与 docstring。`acceptance_4a4/test_deg_states_spec.py`
是同一份主体的另一张映射表——「只改 testid 映射，断言语义不变」在结构上被
`tests/unit/test_e2e_group_guard.py` 的第七条钉住（调用集相等、来源唯一、映射表键集合相等）。
判据本身（`judge_deg_sN`）在 `tests/unit/test_deg_assertions_shared.py` 里今天就被正反两面跑过，
不是等到 Phase 3 出口才第一次被人读。

**映射表的取值来源**：前端计划 `plan-frontend-ui-refactor.md` §4 WI-1…WI-5 的「涉及 testid」栏里
标注〔**定义类·验于 010**〕的那些名字——它们在 010 上定死、012（Phase 3 存储）的朴素横幅「照抄」，
所以朴素形态用的就是 canonical 容器名。主操作按钮按 WI-1 的通式 `*-action`；4A.4 形态把它们换成
WI-2…WI-4 里各自的专名（`-excerpt` / `-reindex` / `-toggle`）。**朴素形态今天没有任何一个 testid
落在模板里**——它们全部是待注册的计划名，解 skip 的人先对照 WI-1…WI-5 逐个核对拼写。

**四条各自主动制造什么**（细节在 `deg_assertions` 文件头）：

* S1：`notes.json` 顶层 `book_fingerprint` 写成必然不匹配的值。今天 notes 里还没有这个键，
  012 定 schema 后若键名不同，改 `deg_assertions.NOTES_FINGERPRINT_KEY` 一处。
* S2：`chroma_db/index_meta.json` 写成「除指纹外全部像已索引」。今天 `_stale_reason` 不看指纹。
* S3：**另起一个 `READER3_ALLOW_PICKLE=1` 的服务进程**——环境变量在服务模块导入时读，session 级
  `live_server` 复用不了。那个 fixture 写在本模块（组目录不能有 conftest），spawner 在
  `deg_assertions.pickle_fallback_server`，起不来抛 `RuntimeError`、**不 skip**。skip 轴静态性质的
  域 G 管本文件（条件 1–4），域 R 管不到——所以「不用 skip 表达失败」是写在这里的约束，不是守卫替它守的。
* S4：把 `smoke_data` 复制成只有 `book.pkl` 的 `legacy_pkl_data`，用完删掉。

**解 skip 的顺序**：先在 Phase 3 出口的模板里确认四组 testid 存在 ⇒ 删本文件的 skip 行 ⇒
跑 `-m acceptance_p3` ⇒ `EXPECTED_ACCEPTANCE_PER_DIR["acceptance_p3"]` 保持 4（条数不变，只是不再 skip）。
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
    pytest.mark.acceptance_p3,
    pytest.mark.skip(
        reason=(
            "激活阶段 P3（Phase 3 出口）：DEG-S1…S4 的朴素横幅要到存储去 pickle 化（012）落地才存在，"
            "今天模板里没有任何 rd-degrade-*/lib-degrade-*/lib-status-stale/lib-storage-format-badge。"
            "到期动作：核对本文件 DEG_TESTIDS 与模板里的 testid 拼写一致后删本行；条数常量不变。"
        )
    ),
]

#: 朴素横幅形态的 testid 映射表。键集合由 `deg_assertions.DEG_TESTID_KEYS` 钉死。
#: 不加 `: Dict[str, str]` 注解是**有意的**：tests/unit/test_e2e_group_guard.py 的
#: `_testid_table_keys()` 用 AST 只认 `ast.Assign`（其断言原文就是「没有模块级
#: `DEG_TESTIDS = {...}`」），注解形态是 `ast.AnnAssign`，会让那条守卫瞎掉。
#: 该守卫已入红证、按行冻结，所以对齐的是这里。改回注解前先改守卫并重录。
DEG_TESTIDS = {
    # DEG-S1（阅读器）
    "s1_banner": "rd-degrade-s1",
    "s1_excerpt": "rd-degrade-s1-action",
    "s1_stale_badge": "rd-note-stale-badge",
    "s1_notes_rail": "rd-rail-notes",
    "s1_notes_panel": "rd-notes-panel",
    # DEG-S2（书库 ＋ 搜索面板）
    "s2_card": "lib-book-card",
    "s2_status_stale": "lib-status-stale",
    "s2_search_tab": "lib-panel-tab-search",
    "s2_banner": "lib-degrade-s2",
    "s2_reindex": "lib-degrade-s2-action",
    # DEG-S3（全局）
    "s3_lib_banner": "lib-degrade-s3",
    "s3_rd_banner": "rd-degrade-s3",
    "s3_toggle": "lib-degrade-s3-action",
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
    """DEG-S1（S3 / L2）：指纹不匹配 ⇒ 顶部横幅文案含「暂停套用」与「未删除」；一条不少；正文零 `<mark>`；面板逐条角标；摘录含 quote。"""
    run_deg_s1(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s2_stale_index_shows_fifth_state_and_search_banner(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S2（S3 / L2）：chroma 指纹不匹配 ⇒ 书卡第五态（不冒充「未索引」）＋ 搜索面板「索引已过期」提示条 ＋ 恰好一个重建按钮。"""
    run_deg_s2(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s3_pickle_fallback_warns_on_both_pages(
    page: Page, live_server: str, pickle_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S3（S3 / L2）：对照服务无告警条；`READER3_ALLOW_PICKLE=1` 的服务上书库与阅读器都有、文案同一份、清单可展开折叠。"""
    run_deg_s3(page, live_server, pickle_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s4_legacy_book_card_shows_storage_format_badge(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S4（S3 / L2）：一本只有 pkl 的书 ⇒ 书卡角标含 `pkl`；新格式书没有角标或角标不含 `pkl`。"""
    run_deg_s4(page, live_server, e2e_books_dir, BOOK_ID, list(E2E_BOOK_IDS), DEG_TESTIDS)
