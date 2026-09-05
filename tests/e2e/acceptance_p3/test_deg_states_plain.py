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
    """DEG-S1（S3 / L2）：指纹不匹配 ⇒ 顶部横幅文案含「暂停套用」与「未删除」；`GET /api/notes` 交出的**就是盘上那批**（id ＋ 逐字段）；正文零 `<mark>`；面板逐条角标；摘录含 quote。

    「一条不少」这个说法 2026-09-05 被审计判为不够：原判据只比条数，于是交出**另一批**同样
    多的标注也算通过。现在比的是身份——`judge_deg_s1` 收 `served_records`，按 id 配对后逐字段
    对（`S1_SERVED_IDENTITY_FIELDS`）。
    """
    run_deg_s1(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s2_stale_index_shows_fifth_state_and_search_banner(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S2（S3 / L2）：chroma 指纹不匹配 ⇒ 书卡第五态的**文案是「索引已过期」** ＋ 搜索面板同名提示条 ＋ **提示条内部**恰好一个重建按钮。

    两处 2026-09-05 审计后收紧，判据都在 `deg_assertions` 里（本文件仍只有那一次调用）：

    * 第五态原来只要求「非空且不含『未索引』」——一本 stale 书被渲染成「已索引」正好从这个
      缝里过去，而那是 DEG-S2 要消灭的头号形状。现在要求 `DEG_S2_STALE_STATUS_PHRASE`
      真的出现在书卡文案里；`lib-status-stale` 这个 testid 只证明「槽位在」，证明不了
      「槽位里填的是第五态的话」——前端计划 WI-3 点名的 `|| STATUS_META.not_indexed`
      正是往这个槽位里填别的态。
    * 重建按钮原来是**全页**计数，页面上任何别处（书卡上的、批量索引面板里的）有一个就满足；
      现在在 `lib-degrade-s2` 横幅内部数。作用域是断言的一部分。
    """
    run_deg_s2(page, live_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s3_pickle_fallback_warns_on_both_pages(
    page: Page, live_server: str, pickle_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S3（S3 / L2）：对照服务无告警条；`READER3_ALLOW_PICKLE=1` 的服务上书库与阅读器都有、文案同一份、清单可展开折叠，且**列的就是那批只有 pkl 的书**。

    清单原来只比条数——列出**别的**书、只要数量撞上就通过。现在每一项必须带
    `data-book-id`（ADR-0014 闭合清单里的判别位，不新增 testid），驱动把这批 id 收齐，
    判据与 `pkl_only_book_ids(books_dir)` 比**集合**，多一本少一本都点名。
    """
    run_deg_s3(page, live_server, pickle_server, e2e_books_dir, BOOK_ID, DEG_TESTIDS)


def test_deg_s4_legacy_book_card_shows_storage_format_badge(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """DEG-S4（S3 / L2）：一本只有 pkl 的书 ⇒ 书卡角标含 `pkl`；**每本新格式书的书卡各恰好 1 张**，其角标要么不存在、要么不含 `pkl`。

    「各恰好 1 张」不是凑数：后半句是**否定断言**，缺卡时它空真——一个把新格式书整批漏渲染
    的书库页，`fresh_badge_texts` 是空列表，旧判据全绿。所以先证明卡在（`fresh_cards_seen`
    每本 == 1），再证明它没戴 pkl 角标。2026-09-05 审计由两批独立找出同一处，修在共享驱动
    `run_deg_s4` / `judge_deg_s4` 里，两组同时生效。
    """
    run_deg_s4(page, live_server, e2e_books_dir, BOOK_ID, list(E2E_BOOK_IDS), DEG_TESTIDS)
