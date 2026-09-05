"""WI-17 —— K-1b：宿主 `annotation-toolbar` 缺失时**响亮失败**（`acceptance_4b1`，skip 形态，一条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「K-1b」。任务书 §4 的 K-1b 行、
§0.5「`baseline-1b` 对 K1 / K6 / W-5 的现状特征化」表的 K1 行。契约的唯一定义处：
`docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` K1——
「七个 id 提为 `overlays.ts` 顶部的 `OVERLAY_IDS` 常量表；init 时逐个校验，缺任何一个 `console.error`
并标记降级。**把静默失败变成响亮失败**——这是本次拆分单点价值最高的一处改动。」

**与 `baseline_1b/test_kernel_host_elements.py`（K-1a）的分工。** K-1a 断七个宿主**在场**且 `init()`
真的跑完了——那是前置条件成立的正向证据，今天绿。本条断的是前置条件**不成立时**会发生什么：今天的
`init()` 第一行是 `if (!this.contentEl || !this.toolbar) return;`，一声不吭；4B.1 之后必须 `console.error`
点名缺失的那个 id，并把降级标记置位。**不能只断言「工具条不见了」**——那句对今天的静默 return 也绿，
契约的价值恰恰在于把静默变响亮。

**怎么制造「宿主缺失」。** 任务书原文写「用 `page.evaluate` 移除 `annotation-toolbar` 后重载标注 UI」。
「重载标注 UI」在契约里没有对应的入口（`annotations.js` 的 IIFE 只在脚本求值时 init 一次），所以这里
改用 `page.route` 改写 `reader.html` 的响应体：在 `<script src="/static/js/annotations.js">` 之前插入一句
`document.querySelector('[data-testid="rd-anno-toolbar"]').remove()`，让宿主在 `AnnotationUI` 构造之前
就不在 DOM 上。这与 §0.6 欠账 #25 的纪律一致（定向破坏一律走 `page.route` 改写响应体，不动 `src/`），
且定位仍是 testid（选择器 lint 通过）。**注入是否生效由一条前置断言证明**（`rd-anno-toolbar` 计数为 0），
否则「没有 console.error」可能只是因为宿主根本没被删掉。

**降级标记的形态（待 4B.1 定名，见文末）。** 契约只写「标记降级」，没定属性名。本条按
`DEGRADED_ATTR = "data-annotation-degraded"` 挂在 `rd-shell` 上、值里含缺失的 id 来写——理由：不新发一个
testid（ADR-0014 的有界枚举不为一个只在故障态出现的元素扩大），而值携带 id 正是契约「点名缺失的那个 id」
在 DOM 侧的对应。4B.1 若定了别的名字，改这一个常量，不改断言。

**三段结构**：对照支（宿主齐备时没有点名它的 `console.error`）→ 注入支（宿主缺失 ⇒ 点名它的
`console.error` ≥ 1 ＋ 降级标记置位）→ 反面（此时没有任何写库发生）。对照支不是装饰：没有它，
一个「每次加载都 console.error 一遍 annotation-toolbar」的实现照样让注入支绿。

**解 skip 的顺序**：4B.1 落地 `OVERLAY_IDS` 校验 ⇒ 对齐 `DEGRADED_ATTR` ⇒ 删本文件 skip 行 ⇒
`-m acceptance_4b1`；`EXPECTED_ACCEPTANCE_PER_DIR["acceptance_4b1"]` 不变（仍是 8）。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List

import pytest
from playwright.sync_api import Page, Route, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_INDEX,
    SELECTION_TIMEOUT_MS,
    open_reader,
    read_notes,
)

pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1：契约 K1 的『缺宿主 ⇒ console.error 点名 id ＋ 降级标记』要 overlays.ts 的 "
            "OVERLAY_IDS 校验落地后才存在——今天 init() 第一行是静默 return。"
            "到期动作：把 DEGRADED_ATTR 对齐到 4B.1 实际的标记属性名，然后删本行。"
        )
    ),
]

#: 契约 K1 七元集里爆炸半径最大的那个：缺它整个标注 UI 不初始化。
MISSING_HOST_ID = "annotation-toolbar"
MISSING_HOST_TESTID = "rd-anno-toolbar"

#: 降级标记：挂在 `rd-shell` 上的属性，值里含缺失的 id。4B.1 定名后只改这一个常量。
DEGRADED_ATTR = "data-annotation-degraded"
SHELL_TESTID = "rd-shell"

#: 注入点：在这个 script 标签之前删掉宿主。模板里它必须恰好出现一次，否则注入位置不可判定。
ANNOTATIONS_SCRIPT_TAG = '<script src="/static/js/annotations.js"></script>'
REMOVE_HOST_SNIPPET = (
    "<script>document.querySelector('[data-testid=\"rd-anno-toolbar\"]').remove();</script>"  # lint-e2e-selectors: allow —— 这是注入进页面的 JS 源码字符串，不是 Playwright 定位调用；选择器在浏览器里由 document.querySelector 求值，Python 侧拿不到 locator，改不成 get_by_test_id
)

#: 等 console.error 到达的上限。console 事件经 CDP 异步送达，紧跟 goto 之后同步读列表会读到空。
CONSOLE_WAIT_MS = SELECTION_TIMEOUT_MS


def _wait_for_console_hit(page: Page, hits: List[str], needle: str) -> List[str]:
    deadline = time.monotonic() + CONSOLE_WAIT_MS / 1000
    while time.monotonic() < deadline:
        found = [m for m in hits if needle in m]
        if found:
            return found
        page.wait_for_timeout(50)
    return [m for m in hits if needle in m]


def test_k1b_missing_toolbar_host_logs_console_error_and_sets_degraded_marker(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-1b（S3 / L2）：删掉 `annotation-toolbar` 宿主再加载 ⇒ `console.error` 点名它 ＋ `rd-shell` 上降级标记置位；且无写库。"""
    console_errors: List[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # ---- 对照支：宿主齐备时，没有点名它的 console.error，也没有降级标记 ----------------
    open_reader(page, live_server, BOOK_ID, CH0_INDEX, CH0_ANCHOR)
    expect(page.get_by_test_id(MISSING_HOST_TESTID)).to_have_count(1)
    page.wait_for_load_state("networkidle")
    control_hits = [m for m in console_errors if MISSING_HOST_ID in m]
    assert not control_hits, (
        f"宿主齐备时也出现了点名 {MISSING_HOST_ID!r} 的 console.error：{control_hits}——"
        "一个「每次加载都报一遍」的实现会让下面的注入支空转"
    )
    expect(page.get_by_test_id(SHELL_TESTID)).not_to_have_attribute(DEGRADED_ATTR, re.compile(r".+"))

    # ---- 注入支：改写 reader.html 响应体，在 annotations.js 求值之前删掉宿主 ---------------
    def strip_host(route: Route) -> None:
        if route.request.resource_type != "document":
            route.continue_()
            return
        response = route.fetch()
        body = response.text()
        assert body.count(ANNOTATIONS_SCRIPT_TAG) == 1, (
            f"reader.html 里 {ANNOTATIONS_SCRIPT_TAG!r} 出现 {body.count(ANNOTATIONS_SCRIPT_TAG)} 次，注入点不可判定"
        )
        route.fulfill(response=response, body=body.replace(ANNOTATIONS_SCRIPT_TAG, REMOVE_HOST_SNIPPET + ANNOTATIONS_SCRIPT_TAG))

    page.route(f"**/read/{BOOK_ID}/*", strip_host)
    console_errors.clear()
    open_reader(page, live_server, BOOK_ID, CH0_INDEX, CH0_ANCHOR)

    # 注入生效的证据：宿主真的不在 DOM 上。没有这一句，「没报错」可能只是没删成。
    expect(page.get_by_test_id(MISSING_HOST_TESTID)).to_have_count(0)

    # (1) console.error 点名缺失的那个 id——断内容而非「有错误发生」，后者会被任何无关报错满足。
    loud = _wait_for_console_hit(page, console_errors, MISSING_HOST_ID)
    assert loud, (
        f"宿主 {MISSING_HOST_ID!r} 缺失，{CONSOLE_WAIT_MS}ms 内没有任何点名它的 console.error。"
        f"收到的 error 级消息：{console_errors}\n"
        "    这正是契约 K1 说的静默失败：init() 第一行 return，标注功能整体失灵而页面照常渲染。"
    )

    # (2) 降级标记置位，值里点名缺失的 id。
    expect(page.get_by_test_id(SHELL_TESTID)).to_have_attribute(
        DEGRADED_ATTR, re.compile(re.escape(MISSING_HOST_ID))
    )

    # (3) 反面：降级态下没有任何写库发生（降级是「停用」，不是「带病运行」）。
    assert read_notes(e2e_books_dir, BOOK_ID) == [], (
        f"降级态下 notes.json 不该有任何写入，实际：{read_notes(e2e_books_dir, BOOK_ID)}"
    )
