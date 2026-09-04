"""WI-17 —— K-6b：`window.Reader3Ctx` 缺失时**抛错而非静默猜测**，且相对非空基线零写入（`acceptance_4b1`，skip，一条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「K-6b（R1 修改）」。任务书 §4 的
K-6b 行、§0.5 现状特征化表的 K6 行。契约唯一定义处 `contracts/annotation-host-contracts.md` K6：
「**删除 `location.pathname` 回退分支**。`window.Reader3Ctx` 读不到时直接抛错，不要猜。这是 4B.1 里唯一
一处**故意的行为变更**——保留它意味着 4B.2 改路由后批注静默存到错章，污染用户数据的代价远高于少一层兜底。」

**与 `baseline_1b/test_kernel_actions_and_url.py`（K-6a）的分工。** K-6a 断今天的正向行为：URL 里的章号
落进 `chapter_index`。本条断 4B.1 之后的反向行为：上下文读不到时**什么都不写**、并且响亮。今天的
`getReaderContext()` 在 `Reader3Ctx` 缺失时会回退解析 `location.pathname`，所以今天本条的注入支会**成功写入
一条**（回退分支就是这么工作的）——那是 (2) 红，也是它今天必须 skip 的原因。

**两处从 Round 1 改掉的构造，理由必须留着（矩阵 R1）：**

1. **在渲染完成之后 `page.evaluate("delete window.Reader3Ctx")`，不是 `add_init_script`。**
   `epub-renderer.js` 与 `annotations.js` 的初始化都读 `Reader3Ctx`；文档创建前就删掉它，渲染器根本
   起不来，iframe 里没有正文，`select_in_frame` 建不出选区——用例在「创建标注」之前就以一个与 K6 无关的
   原因失败。渲染完成后再删，被破坏的只有「创建标注时去读上下文」这一条路径，正是契约点名的那条。
2. **相对一个非空基线断零增量，不是断「仍为空」。** 空基线上，「什么都没发生」（按钮委托坏了、选区没建
   起来、JS 早就整个报错停了）同样让它保持空 ⇒ 绿。对照支先证明这条链在注入前是通的（写成功一条），
   注入支再断 `read_notes() == baseline`（整列表等值）：静默写了一条 ⇒ 红；而「什么都没发生」也不再能
   靠空基线蒙混。

**语料事实（与 W-5a-⓪ 的旁观条同源，目的相反）**：第 0 章 body 是 `OneAlpha prose.`，`One`（`<h1>`）与
`Alpha prose`（`<p>`）互不重叠。对照支写在 `Alpha prose` 上，注入支选 `One`——要证明的是「另一段上什么都
没被写」。语料一改两边同时失效，W-5a-⓪ 那边的 docstring 也写着这句。

**解 skip 的顺序**：4B.1 删掉 `location.pathname` 回退 ⇒ 删本文件 skip 行 ⇒ `-m acceptance_4b1`。
4B.1 之后若有人把回退加回来，注入支会成功写入一条，(2) 红——那是正确的红。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    SELECTION_TIMEOUT_MS,
    open_ch0,
    read_notes,
    scan_marks,
    select_in_frame,
    wait_for_notes,
)

pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1：契约 K6 的『Reader3Ctx 缺失 ⇒ 抛错、不回退解析 location.pathname』是 4B.1 "
            "唯一故意的行为变更，今天回退分支仍在、注入支会成功写入一条。"
            "到期动作：4B.1 删掉回退分支后删本行。"
        )
    ),
]

#: 注入支选的另一段文字（`<h1>One</h1>`），与对照支的 `Alpha prose` 不重叠。
OTHER_QUOTE = "One"
#: 抛错消息里必须出现的 token——断内容，不断「有错误发生」。
CTX_TOKEN = "Reader3Ctx"
#: 对照支之后基线的条数，字面量（§0 第五条纪律）。
BASELINE_COUNT = 1


def _wait_for_error_mentioning(page: Page, sink: List[str], needle: str) -> List[str]:
    deadline = time.monotonic() + SELECTION_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        found = [m for m in sink if needle in m]
        if found:
            return found
        page.wait_for_timeout(50)
    return [m for m in sink if needle in m]


def test_k6b_missing_reader_ctx_throws_and_writes_nothing(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-6b（S3 / L2）：删掉 `window.Reader3Ctx` 后建标注 ⇒ 抛错点名 Reader3Ctx；`notes.json` 与基线逐字段相等；DOM 上没有新 `<mark>`。"""
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    # ---- 对照支：这条链在注入前是通的（非空基线）--------------------------------------
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()
    wait_for_notes(e2e_books_dir, BOOK_ID, BASELINE_COUNT)

    frame = open_ch0(page, live_server, expected_marks=BASELINE_COUNT)
    baseline = read_notes(e2e_books_dir, BOOK_ID)
    assert len(baseline) == BASELINE_COUNT, f"对照支应留下恰好 {BASELINE_COUNT} 条：{baseline}"
    assert baseline[0]["quote"] == CH0_QUOTE

    # ---- 注入支：渲染完成之后删掉全局上下文，只破坏「建标注时读上下文」这一条路径 --------
    errors: List[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    posts: List[str] = []
    page.on(
        "request",
        lambda req: posts.append(req.url) if req.method == "POST" and "/api/notes/" in req.url else None,
    )

    page.evaluate("() => { delete window.Reader3Ctx; }")
    assert page.evaluate("() => typeof window.Reader3Ctx") == "undefined", "注入没生效：Reader3Ctx 还在"

    select_in_frame(frame, OTHER_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()

    # (1) 抛错，且消息点名 Reader3Ctx。
    loud = _wait_for_error_mentioning(page, errors, CTX_TOKEN)
    assert loud, (
        f"Reader3Ctx 缺失时 {SELECTION_TIMEOUT_MS}ms 内没有任何点名它的 pageerror / console.error："
        f"{errors}\n    静默猜测（回退解析 location.pathname）就是契约 K6 说的最坏结果的入口"
    )

    # (2) 相对非空基线零增量：整列表逐字段等值。静默写了一条 ⇒ 红；没写但基线被动了 ⇒ 也红。
    assert posts == [], f"上下文缺失却仍发出了 POST /api/notes：{posts}"
    after = read_notes(e2e_books_dir, BOOK_ID)
    assert after == baseline, (
        f"上下文缺失时 notes.json 变了——这就是「污染用户数据」：\n  基线：{baseline}\n  现在：{after}"
    )

    # (3) 刷新后 DOM 上仍只有对照支那一条 `<mark>`，`One` 上没有新的。
    frame = open_ch0(page, live_server, expected_marks=BASELINE_COUNT)
    assert set(scan_marks(frame)["texts"]) == {CH0_QUOTE}, (
        f"刷新后 <mark> 的文本集合是 {set(scan_marks(frame)['texts'])}，期望只有 {{{CH0_QUOTE!r}}}"
    )
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(BASELINE_COUNT)
