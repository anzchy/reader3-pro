"""009 欠账 #43 part (i)：标注写路径上的失败必须**可归因**——失败了，而且说得出是哪一种失败。

**它守的是什么。** 标注写路径上有一族出口，失败时界面表现得与成功一模一样：不提示、不
报错、盘上什么都没有。#43 要买的是一个区分：一次写没落地时，事后能分清「请求根本没发出去」
（`requested: false`）、「发出去了但没回来」（`status: null`）和「回来了但被拒」（数字
`status`）。三者在「盘上少一条」这个唯一可观测面上完全一致，只有诊断记录能把它们分开。

**本模块的内容按工作项分批落地。** 本批（WI-1 ＋ WI-2）只写诊断底座本身的规格：
`window.Reader3NotesDiag` 的有界环形缓冲（W1-C1/C2/C3）、唯一的失败上报 helper
`reportNotesWriteFailure`（W1-C4/C9/C5）、以及加固后的 `showToast`（W1-C6/C10/C7/C8）。
把既有调用点改接到 helper 上是 WI-3..WI-6 的事，它们的用例随各自的工作项进本文件。

**落址：`tests/e2e/baseline_1b/`，带 `pytestmark = pytest.mark.baseline_1b`（2026-10-01，
023 #65）。** 本模块起初住在 `tests/e2e/` 根、登记在 `UNGROUPED_E2E_MODULES` 白名单里，理由是
`suite_hash` 的覆盖面：`scripts/soak_run.py` 的 `HASH_COVERED_PATHS` 把 `tests/e2e/baseline_1b`
当**目录**覆盖，根下的文件不在其内，放在根下就不动 `suite_hash`。那是一笔带到期条件的明账：
下一次本来就要动 `baseline_1b/`、`suite_hash` 无论如何都要变的改动里一并迁入。023 在 master
宣布第一个批次（012 开工前那一批）之前兑付了它（009 欠账 #65），与共享模块
`notes_conflict_support.py` 及另外三个同类白名单模块同批迁入，让一次 `suite_hash` 变化、
一个新的 10 轮批次一并覆盖。从此它计入 1b 门槛，也落进域 R 的零 skip 约束。

**本文件的共享基础设施全部是模块私有的**（矩阵 §0.2–§0.5）：toast 事件闩、console 捕获、
notes 路由注入、请求/响应日志。它们最便宜的住址是冻结的 `tests/e2e/helpers.py` /
`tests/e2e/conftest.py`，而放在那里会移动 `suite_hash`。

**选择器只用 `data-testid`。** 注入页面的 JS 里读 testid 一律用 `node.dataset.testid`，
不用 `getAttribute("data-testid")`——后者会被 `scripts/lint_e2e_selectors.py` 的
`LOCATOR_CALL_RE` 误报（陷阱记在 `tests/e2e/helpers.py:584-592`）。
"""

from __future__ import annotations

import json
import random
import re
import time
import uuid
from collections import Counter
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from playwright.sync_api import ConsoleMessage, Error as PlaywrightError, Page, Route, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    CH0_INDEX,
    CH0_QUOTE,
    NOTES_ENDPOINT_MARKER,
    assert_bystanders_unchanged,
    open_ch0,
    open_reader_settled,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_note_text,
)

pytestmark = pytest.mark.baseline_1b

# ---------------------------------------------------------------------------
# 矩阵里点名的常量
# ---------------------------------------------------------------------------

#: `Reader3NotesDiag.capacity` 的地板与天花板（W1-C1 / 修订 A6）。地板不是审美：FIFO 丢的是
#: **最旧**的，容量太小时一次压力运行里的**第一个**失败会被挤掉，而 `t` 字段存在的意义正是
#: 拿它去对服务端日志。天花板挡住「无界缓冲冒充有界」。
CAPACITY_FLOOR = 50
CAPACITY_CEILING = 200

#: `reportNotesWriteFailure` 的 console 行契约（矩阵 §0.3）：**一个字符串实参**，
#: 组 1 是一个 ring 条目超集的 `JSON.stringify`。
DIAG_CONSOLE_RE = re.compile(r"^\[Annotations\] notes write failed (\{.*\})$")
DIAG_CONSOLE_PREFIX = "[Annotations] notes write failed"

#: `createAnnotation` 各失败出口改接 helper 之前自带的 console 行前缀（`写入被拒` / `选区已失效…` /
#: `算出空 quote…` 三条都以它开头）。009 #50 之后它是**必须不出现**的前缀：出现即说明某个出口
#: 还在绕开 `reportNotesWriteFailure` 自己打日志（W1-C8 / W1-C11..C13 / W6-C6..C8 反向断它）。
LEGACY_CREATE_CONSOLE_PREFIX = "[Annotations] createAnnotation:"
#: 建标注的 POST 失败时的 toast 文案（`annotations.js`：`标注没能保存（{status}），请重试`，
#: 没有响应时不带括号）。字面量钉死，不从实现里推。
CREATE_REJECTED_TOAST_500 = "标注没能保存（500），请重试"
CREATE_REJECTED_TOAST_409 = "标注没能保存（409），请重试"
CREATE_NO_RESPONSE_TOAST = "标注没能保存，请重试"
CREATE_NO_OFFSETS_TOAST = "这段选区已失效，请重新选中再试"
CREATE_EMPTY_QUOTE_TOAST = "没取到选中的文字，请重新选中再试"

#: 一条 ring 条目至少带的字段（WI-1 验收条件）。
ENTRY_KEYS = ("op", "id", "status", "ok", "requested", "t")

#: toast 的实现寿命是 1400ms。W1-C10 的门槛**故意低于**它，让普通抖动没有影响；
#: W1-C8 用 1400 当「两次 toast 确实在同一个寿命内重叠」的非空转守卫。
TOAST_LIFETIME_MS = 1400
TOAST_READABLE_FLOOR_MS = 1000

# W1-C4 / W1-C9 共用的失败形状表。期望值住在 **Python** 里：在 JS 里用实现自己的表达式
# 重新推一遍期望，是披着测试外衣的同义反复。
#   (resp 的形状, requested 实参, 期望 status, 期望 ok, 期望 requested)
_OMIT = object()
FAILURE_SHAPE_TABLE: List[tuple] = [
    ("null", _OMIT, None, False, True),
    ("undefined", _OMIT, None, False, True),
    ({"ok": False, "status": 500}, _OMIT, 500, False, True),
    ({"ok": False, "status": 400}, _OMIT, 400, False, True),
    ({"ok": False, "status": 409}, _OMIT, 409, False, True),
    ({"ok": False, "status": 0}, _OMIT, 0, False, True),
    ({"ok": True, "status": 200}, _OMIT, 200, True, True),
    ("null", False, None, False, False),
]


# ---------------------------------------------------------------------------
# §0.2 toast 观测闩（`_install_page_latch`）
# ---------------------------------------------------------------------------
#
# 观测的是 **toast 事件**，不是「插入了一个 rd-toast 元素」：后者会悄悄规定「每次都删掉重插」
# 这一种单例实现。三种合规写法（删掉重插 / 保留一个节点改文字 / 先挂上再赋文字）都各自
# 让一次调用恰好记一个事件——最后一种要靠同一批次内的去重规则（R2-5）。
_LATCH_JS = r"""
(() => {
  if (window.__r3latch) return;
  const latch = { toastEvents: [], updatedEvents: 0, seq: 0 };
  window.__r3latch = latch;
  // node 不可 JSON 化：事件对象里只存 seq，节点放在旁边的数组里。
  const eventNodes = [];

  const now = () => performance.now() + performance.timeOrigin;
  const isToastEl = (n) => !!n && n.nodeType === 1 && !!n.dataset && n.dataset.testid === "rd-toast";
  const toastAncestor = (n) => {
    let cur = n && n.nodeType === 1 ? n : (n ? n.parentElement : null);
    while (cur) {
      if (isToastEl(cur)) return cur;
      cur = cur.parentElement;
    }
    return null;
  };
  const hitAtPrimary = () => {
    const btn = document.querySelector('[data-testid="rd-note-editor-primary"]');
    if (!btn) return null;
    const r = btn.getBoundingClientRect();
    if (!r.width && !r.height) return null;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || !hit.dataset) return null;
    return hit.dataset.testid || null;
  };
  const record = (kind, node, text) => {
    const rect = node.getBoundingClientRect();
    const ev = {
      seq: latch.seq++,
      kind,
      text,
      pointerEvents: getComputedStyle(node).pointerEvents,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
              top: rect.top, left: rect.left, right: rect.right, bottom: rect.bottom },
      liveCount: document.querySelectorAll('[data-testid="rd-toast"]').length,
      hitAtPrimary: hitAtPrimary(),
      insertedAt: now(),
      lifetimeMs: null,
    };
    latch.toastEvents.push(ev);
    eventNodes.push(node);
  };

  const observer = new MutationObserver((records) => {
    // 先把本批次里每条记录归类，再按去重规则过滤，最后按递送顺序落账。
    const classified = [];
    const insertedNodes = new Set();
    // (c) 的文字重建：同一 target 上第 i 条 characterData 记录的新值 = 第 i+1 条的 oldValue，
    // 最后一条的新值 = target.nodeValue（活值）。
    const cdByTarget = new Map();
    records.forEach((r, i) => {
      if (r.type === "characterData") {
        if (!cdByTarget.has(r.target)) cdByTarget.set(r.target, []);
        cdByTarget.get(r.target).push(i);
      }
    });
    records.forEach((r, i) => {
      if (r.type === "childList") {
        let inserted = false;
        r.addedNodes.forEach((n) => {
          if (isToastEl(n)) {
            classified.push({ i, kind: "insert", node: n, text: null });
            insertedNodes.add(n);
            inserted = true;
          }
        });
        if (!inserted) {
          const host = toastAncestor(r.target);
          if (host && r.addedNodes.length) {
            let text = "";
            r.addedNodes.forEach((n) => { text += n.textContent || ""; });
            classified.push({ i, kind: "update", node: host, text });
          }
        }
        r.removedNodes.forEach((n) => {
          if (isToastEl(n)) classified.push({ i, kind: "remove", node: n });
        });
      } else if (r.type === "characterData") {
        const host = toastAncestor(r.target);
        if (host) {
          const list = cdByTarget.get(r.target);
          const pos = list.indexOf(i);
          const text = pos + 1 < list.length ? records[list[pos + 1]].oldValue : r.target.nodeValue;
          classified.push({ i, kind: "update", node: host, text });
        }
      }
    });
    for (const c of classified) {
      if (c.kind === "insert") {
        // (a)：读的是递送时的 textContent，所以「先挂再赋文字」也拿得到最终消息。
        record("insert", c.node, c.node.textContent);
      } else if (c.kind === "update") {
        // 去重规则（R2-5）：同一批次里对节点 N 的插入记录压掉对 N 的一切更新记录。
        if (insertedNodes.has(c.node)) continue;
        record("update", c.node, c.text);
      } else if (c.kind === "remove") {
        for (let k = latch.toastEvents.length - 1; k >= 0; k--) {
          if (eventNodes[k] === c.node && latch.toastEvents[k].lifetimeMs === null) {
            latch.toastEvents[k].lifetimeMs = now() - latch.toastEvents[k].insertedAt;
            break;
          }
        }
      }
    }
  });
  const arm = () => observer.observe(document.documentElement, {
    childList: true, subtree: true, characterData: true, characterDataOldValue: true,
  });
  if (document.documentElement) arm();
  else document.addEventListener("readystatechange", arm, { once: true });
  window.addEventListener("reader3:annotations:updated", () => { latch.updatedEvents++; });
})();
"""


def _install_page_latch(page: Page) -> None:
    """在 `document_start` 装上 toast 事件闩。必须早于 `open_*`，才能赶在 `annotations.js` 之前。"""
    page.add_init_script(_LATCH_JS)


def _latch(page: Page) -> Dict[str, Any]:
    latch = page.evaluate("() => window.__r3latch ? JSON.parse(JSON.stringify(window.__r3latch)) : null")
    assert latch is not None, "toast 观测闩没有装上：_install_page_latch 必须在 open_* 之前调用"
    return latch


def _wait_until(page: Page, predicate_js: str, what: str, arg: Any = None) -> None:
    """等一个可观测谓词成立（Playwright 默认超时，不引入新常量）；等不到就以断言失败报出来。

    超时被翻译成 `AssertionError`，因为「规格要求的事件没有发生」本来就是一个断言结论，
    而不是一次环境故障。
    """
    try:
        page.wait_for_function(predicate_js, arg=arg)
    except PlaywrightError as exc:
        raise AssertionError(f"等不到：{what}（{type(exc).__name__}: {str(exc).splitlines()[0]}）") from None


# ---------------------------------------------------------------------------
# §0.3 console 捕获
# ---------------------------------------------------------------------------


def _console_errors(page: Page) -> List[ConsoleMessage]:
    """挂一个 `console` 监听，收 `error` 级消息。存的是 `ConsoleMessage` 本身而不只是 `text()`，
    因为 W1-C8 要伸进 `msg.args()`。返回的列表会随页面继续增长；「增量」断言一律是
    `len(after) - len(before)`。"""
    errors: List[ConsoleMessage] = []

    def _on(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            errors.append(msg)

    page.on("console", _on)
    return errors


# ---------------------------------------------------------------------------
# §0.5 请求/响应日志（`_install_wire_log`）
# ---------------------------------------------------------------------------


class _WireLog:
    """`/api/notes/` 的请求与响应，按到达顺序记在**同一张**表里。真实的线上观测，不是调用参数间谍。"""

    def __init__(self) -> None:
        self.entries: List[tuple] = []

    def __len__(self) -> int:
        return len(self.entries)

    def writes_after(self, i: int) -> List[tuple]:
        return [
            e for e in self.entries[i:]
            if e[0] == "req" and e[1] in ("POST", "PUT", "DELETE")
        ]

    def last_2xx_etag_before(self, i: int) -> Optional[str]:
        for e in reversed(self.entries[:i]):
            if e[0] == "resp" and 200 <= e[2] < 300:
                return e[3]
        return None


def _install_wire_log(page: Page) -> _WireLog:
    log = _WireLog()

    def _on_request(req) -> None:  # type: ignore[no-untyped-def]
        if NOTES_ENDPOINT_MARKER in req.url:
            log.entries.append(("req", req.method, req.url, req.headers.get("if-match")))

    def _on_response(resp) -> None:  # type: ignore[no-untyped-def]
        if NOTES_ENDPOINT_MARKER in resp.url:
            log.entries.append(("resp", resp.url, resp.status, resp.headers.get("etag")))

    page.on("request", _on_request)
    page.on("response", _on_response)
    return log


# ---------------------------------------------------------------------------
# §0.4 失败注入（`_route_notes`）
# ---------------------------------------------------------------------------


def _route_notes(
    page: Page,
    *,
    mode: str,
    method: Optional[str] = None,
    match: Optional[Callable[[Route], bool]] = None,
    headers: Optional[Dict[str, str]] = None,
    wire_log: Optional[_WireLog] = None,
    conflict_body: Optional[Callable[[Optional[str]], Dict[str, Any]]] = None,
) -> SimpleNamespace:
    """页面级 `page.route("**/api/notes/**")`，优先于冻结 conftest 的 context 级出网闸。

    * `mode="fulfill500"` ⇒ 一个真实的 500 `Response`；
    * `mode="abort"` ⇒ fetch 的 promise 被拒 ⇒ `.catch(() => null)` ⇒ `resp === null`；
    * `mode="conflict"` ⇒ 合成 409，体里的 `etag` **在处理函数里现读**
      `wire_log.last_2xx_etag_before(len(wire_log))`，永不写字面量；
    * `mode="observe"` ⇒ 只数不拦；
    * 目标之外的一切 ⇒ **`route.fallback()`，从不 `route.continue_()`**，让冻结的出网闸
      照样看见并记账这条请求。

    **计数无条件**（R2-4）：每次进入处理函数都先 `counts[method] += 1` 再分岔，包括
    fallback 那一支。
    """
    counts: Counter = Counter()
    state = SimpleNamespace(counts=counts, injected_etag=None, hits=0)

    def _handler(route: Route) -> None:
        req = route.request
        counts[req.method] += 1
        targeted = mode != "observe" and (method is None or req.method == method)
        if targeted and match is not None:
            targeted = match(route)
        if not targeted:
            route.fallback()
            return
        state.hits += 1
        if mode == "fulfill500":
            route.fulfill(
                status=500,
                content_type="application/json",
                body='{"detail":"injected"}',
                headers=headers,
            )
        elif mode == "abort":
            route.abort()
        elif mode == "conflict":
            assert wire_log is not None, "mode='conflict' 需要 wire_log 才能现读服务端最近一次发出的 ETag"
            etag = wire_log.last_2xx_etag_before(len(wire_log))
            state.injected_etag = etag
            body = conflict_body(etag) if conflict_body else {"etag": etag, "annotation": None}
            route.fulfill(
                status=409,
                content_type="application/json",
                body=json.dumps(body),
                headers=headers,
            )
        else:  # pragma: no cover - 用例写错了 mode
            route.fallback()
            raise AssertionError(f"_route_notes: 未知 mode {mode!r}")

    page.route("**/api/notes/**", _handler)
    return state


def _writes(counts: Counter) -> int:
    return counts["POST"] + counts["PUT"] + counts["DELETE"]


# ---------------------------------------------------------------------------
# 页内诊断面
# ---------------------------------------------------------------------------


def _assert_diag_surface(page: Page) -> None:
    """`window.Reader3NotesDiag` 必须在阅读器加载后存在，并暴露规格要求的公开面。"""
    surface = page.evaluate(
        """() => {
          const d = window.Reader3NotesDiag;
          if (!d) return null;
          return {
            capacity: typeof d.capacity,
            record: typeof d.record,
            entries: typeof d.entries,
            reportNotesWriteFailure: typeof d.reportNotesWriteFailure,
            showToast: typeof d.showToast,
          };
        }"""
    )
    assert surface == {
        "capacity": "number",
        "record": "function",
        "entries": "function",
        "reportNotesWriteFailure": "function",
        "showToast": "function",
    }, f"window.Reader3NotesDiag 的公开面不对（阅读器加载后）：{surface}"


def _diag_entries(page: Page) -> Optional[List[Dict[str, Any]]]:
    return page.evaluate("() => window.Reader3NotesDiag ? window.Reader3NotesDiag.entries() : null")


def _token() -> str:
    return uuid.uuid4().hex[:8]


def _open_plain(page: Page, base_url: str) -> None:
    open_reader_settled(page, base_url, BOOK_ID, CH0_INDEX, CH0_ANCHOR, expected_marks=0)


# ===========================================================================
# Unit: Reader3NotesDiag（有界环形缓冲）— WI-1
# ===========================================================================


def test_w1_c1_bounded_fifo_keeps_most_recent_window_with_usable_clock_and_capacity_floor(
    page: Page, live_server: str
) -> None:
    """W1-C1 · S5：`cap + 5` 次 record 之后只留最近的 `cap` 条，按调用顺序；`t` 单调且落在真实时间窗内。"""
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()

    t0 = time.time() * 1000
    got = page.evaluate(
        """(token) => {
          const d = window.Reader3NotesDiag;
          const cap = d.capacity;
          for (let i = 0; i < cap + 5; i++) d.record({ op: `probe-${token}-${i}` });
          const es = d.entries();
          return { cap, ops: es.map((e) => e.op), ts: es.map((e) => e.t) };
        }""",
        token,
    )
    t1 = time.time() * 1000

    cap = got["cap"]
    assert isinstance(cap, int) and not isinstance(cap, bool), f"capacity 不是整数：{cap!r}"
    assert CAPACITY_FLOOR <= cap <= CAPACITY_CEILING, (
        f"capacity={cap} 不在 [{CAPACITY_FLOOR}, {CAPACITY_CEILING}]：地板挡住「窗口小到把一次压力运行的"
        "第一个失败挤掉」，天花板挡住「无界冒充有界」"
    )
    ops, ts = got["ops"], got["ts"]
    assert len(ops) == cap, f"保留了 {len(ops)} 条，应当恰好 {cap} 条"
    assert ops == [f"probe-{token}-{i}" for i in range(5, cap + 5)], (
        f"保留窗口不是最近的 {cap} 条（FIFO）：头 {ops[:3]} … 尾 {ops[-3:]}"
    )
    assert all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in ts), f"t 不全是数：{ts[:5]}"
    assert ts == sorted(ts), "t 在保留窗口里不是非递减的"
    assert t0 <= min(ts) <= max(ts) <= t1, (
        f"t 不在真实墙钟区间里：[{min(ts)}, {max(ts)}] ⊄ [{t0}, {t1}]——常量、计数器、或别的时钟"
    )


# `entries()` 返回值上的变异程序字母表（W1-C2）。
_MUTATION_ALPHABET = ("push", "pop", "shift", "splice", "reverse", "sort", "length0", "setjunk")


def _mutation_programs() -> List[List[List[Any]]]:
    rng = random.Random(43)
    programs: List[List[List[Any]]] = []
    for _ in range(12):
        prog: List[List[Any]] = []
        for _ in range(rng.randint(1, 5)):
            op = rng.choice(_MUTATION_ALPHABET)
            if op == "push":
                prog.append(["push", {"op": f"junk-{rng.randint(0, 999)}"}])
            elif op == "splice":
                prog.append(["splice", rng.randint(0, 2)])
            elif op == "setjunk":
                prog.append(["setjunk", rng.randint(0, 2), f"junk-{rng.randint(0, 999)}"])
            else:
                prog.append([op])
        programs.append(prog)
    return programs


def test_w1_c2_read_accessor_returns_a_copy_no_caller_can_use_to_corrupt_state(
    page: Page, live_server: str
) -> None:
    """W1-C2 · S4：12 个随机变异程序（seed 43）作用在 `entries()` 的返回值上，内部状态一律不动。"""
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()
    programs = _mutation_programs()

    results = page.evaluate(
        """([token, programs]) => {
          const d = window.Reader3NotesDiag;
          return programs.map((prog, p) => {
            for (let k = 0; k < 3; k++) d.record({ op: `sentinel-${token}-${p}-${k}` });
            const before = JSON.stringify(d.entries());
            const arr = d.entries();
            for (const step of prog) {
              const [op, a, b] = step;
              if (op === "push") arr.push(a);
              else if (op === "pop") arr.pop();
              else if (op === "shift") arr.shift();
              else if (op === "splice") arr.splice(a, 1);
              else if (op === "reverse") arr.reverse();
              else if (op === "sort") arr.sort((x, y) => String(y && y.op).localeCompare(String(x && x.op)));
              else if (op === "length0") arr.length = 0;
              else if (op === "setjunk") arr[a] = b;
            }
            return JSON.stringify(d.entries()) === before;
          });
        }""",
        [token, programs],
    )
    leaking = [i for i, ok in enumerate(results) if not ok]
    assert results == [True] * 12, f"这些变异程序改到了内部状态（索引）：{leaking}；程序：{[programs[i] for i in leaking]}"


def test_w1_c3_capacity_boundary_exactly_cap_then_cap_plus_one(
    page: Page, live_server: str
) -> None:
    """W1-C3 · S2：恰好 `cap` 条时一条都不丢；再多一条时恰好丢一条，且丢的是最旧的。"""
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()

    got = page.evaluate(
        """(token) => {
          const d = window.Reader3NotesDiag;
          const cap = d.capacity;
          for (let i = 0; i < cap; i++) d.record({ op: `edge-${token}-${i}` });
          const atCap = d.entries().map((e) => e.op);
          d.record({ op: `edge-${token}-${cap}` });
          const atCapPlus1 = d.entries().map((e) => e.op);
          return { cap, atCap, atCapPlus1 };
        }""",
        token,
    )
    cap = got["cap"]
    assert got["atCap"] == [f"edge-{token}-{i}" for i in range(cap)], (
        f"恰好 {cap} 条时已经发生了淘汰（off-by-one）：长度 {len(got['atCap'])}，头 {got['atCap'][:2]}"
    )
    assert got["atCapPlus1"] == [f"edge-{token}-{i}" for i in range(1, cap + 1)], (
        f"第 {cap + 1} 条进来之后不是恰好丢掉最旧的一条：长度 {len(got['atCapPlus1'])}，"
        f"头 {got['atCapPlus1'][:2]}，尾 {got['atCapPlus1'][-2:]}"
    )


# ===========================================================================
# Unit: reportNotesWriteFailure — WI-1
# ===========================================================================

_REPORT_TABLE_JS = """([token, rows]) => {
  const d = window.Reader3NotesDiag;
  rows.forEach((row, i) => {
    const args = { op: `map-${token}-${i}`, id: `id-${token}-${i}`, message: `msg-${token}-${i}` };
    if (row.resp === "null") args.resp = null;
    else if (row.resp === "undefined") args.resp = undefined;
    else args.resp = row.resp;
    if (row.hasRequested) args.requested = row.requested;
    d.reportNotesWriteFailure(args);
  });
  return d.entries().filter((e) => typeof e.op === "string" && e.op.startsWith(`map-${token}-`));
}"""


def _table_rows() -> List[Dict[str, Any]]:
    rows = []
    for resp, requested, _s, _o, _r in FAILURE_SHAPE_TABLE:
        rows.append(
            {
                "resp": resp,
                "hasRequested": requested is not _OMIT,
                "requested": None if requested is _OMIT else requested,
            }
        )
    return rows


def test_w1_c4_requested_status_ok_mapping_over_the_whole_failure_shape_domain(
    page: Page, live_server: str
) -> None:
    """W1-C4 · S4：八种失败形状 → `(status, ok, requested)`，对着 Python 里的期望表逐行相等。"""
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()

    entries = page.evaluate(_REPORT_TABLE_JS, [token, _table_rows()])

    assert [e["op"] for e in entries] == [f"map-{token}-{i}" for i in range(len(FAILURE_SHAPE_TABLE))], (
        f"八次调用没有恰好各留一条 ring 条目：{[e.get('op') for e in entries]}"
    )
    got = [(e["status"], e["ok"], e["requested"]) for e in entries]
    want = [(s, o, r) for _resp, _req, s, o, r in FAILURE_SHAPE_TABLE]
    assert got == want, f"(status, ok, requested) 映射与期望表不符：\n  实际 {got}\n  期望 {want}"
    # `is None` 而不是「假值」：第 5 行的 status 0 必须作为 0 活下来。
    for i in (0, 1, 7):
        assert entries[i]["status"] is None, f"第 {i} 行 status 应当 is None：{entries[i]}"
    assert entries[5]["status"] == 0 and entries[5]["status"] is not None, (
        f"第 5 行 status:0 被抹成了 {entries[5]['status']!r}——`resp.status || null` 会摧毁中断/响应之分"
    )
    assert entries[6]["ok"] is True, f"第 6 行 ok 应当反映响应：{entries[6]}"
    for i, e in enumerate(entries):
        assert e["id"] == f"id-{token}-{i}", f"第 {i} 行 id 没有原样记下：{e}"


def test_w1_c9_console_payload_is_a_superset_of_the_ring_entry(
    page: Page, live_server: str
) -> None:
    """W1-C9 · S4：每次调用恰好一条单字符串 `console.error`，其 JSON 负载与同次的 ring 条目逐字段相等。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()

    before = len(errors)
    entries = page.evaluate(_REPORT_TABLE_JS, [token, _table_rows()])
    window = errors[before:]
    messages = [m.text for m in window]

    assert len(messages) == len(FAILURE_SHAPE_TABLE), (
        f"窗口内 console.error 应当恰好 {len(FAILURE_SHAPE_TABLE)} 条，实际 {len(messages)} 条：{messages}"
    )
    assert len(entries) == len(FAILURE_SHAPE_TABLE), f"ring 条目数不对：{entries}"
    parsed: List[Dict[str, Any]] = []
    for i, text in enumerate(messages):
        m = DIAG_CONSOLE_RE.match(text)
        assert m, f"第 {i} 条 console 行不是 `[Annotations] notes write failed {{…}}` 单字符串形态：{text!r}"
        parsed.append(json.loads(m.group(1)))
    for i, (p, e) in enumerate(zip(parsed, entries)):
        assert set(p) >= set(ENTRY_KEYS), f"第 {i} 条 console 负载缺字段：{sorted(set(ENTRY_KEYS) - set(p))}"
        assert {k: p[k] for k in ENTRY_KEYS} == {k: e[k] for k in ENTRY_KEYS}, (
            f"第 {i} 条两路通道不一致：\n  console {p}\n  ring    {e}"
        )
    assert parsed[0]["status"] is None, parsed[0]
    assert parsed[2]["status"] == 500, parsed[2]
    assert parsed[5]["status"] == 0 and parsed[5]["status"] is not None, parsed[5]
    assert parsed[6]["ok"] is True, parsed[6]
    assert parsed[7]["requested"] is False, parsed[7]
    assert len(set(messages)) == len(FAILURE_SHAPE_TABLE), "八条 console 行不两两相异——一个常量串冒充了多行"
    # 019 WI-8（WI8-E4）：没传 detail 的调用，负载里就没有 detail 这个键，键序恰好七个。
    for i, p in enumerate(parsed):
        assert list(p) == ["op", "requested", "status", "ok", "id", "t", "message"], (
            f"第 {i} 条 console 负载的键序不对：{list(p)}"
        )
        assert "detail" not in p, f"第 {i} 条没传 detail 却带了：{p}"


def test_w1_c5_one_invocation_exactly_one_of_each_effect(
    page: Page, live_server: str
) -> None:
    """W1-C5 · S5：n=1 与 n=4 时，ring 条目、toast 事件、console.error 各恰好 n 个。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()
    op = f"count-{token}"
    call_js = """([op, n]) => {
      for (let i = 0; i < n; i++) {
        window.Reader3NotesDiag.reportNotesWriteFailure({ op, resp: null, id: "x", message: "m" });
      }
    }"""

    base_errors = len(errors)
    base_events = len(_latch(page)["toastEvents"])

    def _observe(n: int) -> None:
        _wait_until(
            page,
            "(want) => window.__r3latch.toastEvents.length >= want",
            f"{n} 个 toast 事件",
            arg=base_events + n,
        )
        ring = [e for e in (_diag_entries(page) or []) if e.get("op") == op]
        events = _latch(page)["toastEvents"][base_events:]
        delta = len(errors) - base_errors
        assert len(ring) == n, f"{n} 次调用后 op={op} 的 ring 条目有 {len(ring)} 条"
        assert len(events) == n, f"{n} 次调用后 toast 事件有 {len(events)} 个：{events}"
        assert delta == n, (
            f"{n} 次调用后窗口内 console.error 增量为 {delta}：{[m.text for m in errors[base_errors:]]}"
        )
        assert all(e["liveCount"] == 1 for e in events), f"有 toast 事件时 DOM 里不止一个 rd-toast：{events}"

    page.evaluate(call_js, [op, 1])
    _observe(1)
    page.evaluate(call_js, [op, 3])
    _observe(4)


# ===========================================================================
# Unit: showToast（加固后）— WI-1
# ===========================================================================


def test_w1_c6_k_successive_toasts_leave_one_node_carrying_the_last_message(
    page: Page, live_server: str
) -> None:
    """W1-C6 · S5：连续 5 次 toast ⇒ 5 个事件、最后一条文案、DOM 里始终只有一个 `rd-toast`。"""
    _install_page_latch(page)
    _open_plain(page, live_server)
    _assert_diag_surface(page)
    token = _token()

    page.evaluate(
        """(token) => { for (let i = 0; i < 5; i++) window.Reader3NotesDiag.showToast(`t-${token}-${i}`); }""",
        token,
    )
    _wait_until(page, "() => window.__r3latch.toastEvents.length >= 5", "5 个 toast 事件")
    expect(page.get_by_test_id("rd-toast")).to_have_count(1)
    events = _latch(page)["toastEvents"]

    assert len(events) == 5, f"5 次调用应当是 5 个 toast 事件，实际 {len(events)} 个：{events}"
    assert events[-1]["text"] == f"t-{token}-4", f"最后一个事件的文案不是最后一条消息：{events[-1]}"
    assert max(e["liveCount"] for e in events) == 1, (
        f"toast 叠起来了（liveCount 最大 {max(e['liveCount'] for e in events)}）——不是单例"
    )


def _fire_create_500(page: Page, frame, type_testid: str) -> None:  # type: ignore[no-untyped-def]
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(type_testid).click()


def test_w1_c10_a_toast_stays_on_screen_long_enough_to_be_read(
    page: Page, live_server: str
) -> None:
    """W1-C10 · S3：经真实调用点触发的一个 toast，在 DOM 上存活 >= 1000ms。"""
    _install_page_latch(page)
    _route_notes(page, method="POST", mode="fulfill500")
    frame = open_ch0(page, live_server, expected_marks=0)
    _fire_create_500(page, frame, "rd-anno-type-marker")

    _wait_until(
        page,
        "() => window.__r3latch.toastEvents.some((e) => e.lifetimeMs !== null)",
        "一个带 data-testid=rd-toast 的 toast 出现并被移除",
    )
    events = _latch(page)["toastEvents"]
    assert len(events) == 1, f"应当恰好一个 toast 事件：{events}"
    life = events[0]["lifetimeMs"]
    assert life is not None and life >= TOAST_READABLE_FLOOR_MS, (
        f"toast 只在屏幕上待了 {life}ms（< {TOAST_READABLE_FLOOR_MS}ms）——形状对了，用户什么也没看到"
    )


def _intersects(a: Dict[str, float], b: Dict[str, float]) -> bool:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    return min(ax2, bx2) > max(a["x"], b["x"]) and min(ay2, by2) > max(a["y"], b["y"])


def test_w1_c7_a_toast_never_intercepts_a_pointer_aimed_at_the_note_editor_primary(
    page: Page, live_server: str
) -> None:
    """W1-C7 · S3：toast 与 `rd-note-editor-primary` 重叠时，命中测试仍落在按钮上。[CI RISK: 视口几何]"""
    # 视口是本例的前置条件，不是装饰。实测默认 1280×720：toast {x:581.7,y:659,w:116.6,h:35}，
    # PRIMARY {x:423.4,y:307,w:61.6,h:31}——两者不相交，断言 (1) 对任何实现都失败（本例空转）。
    # 900×360 实测：toast {x:391.7,y:299,w:116.6,h:35}，PRIMARY {x:407.4,y:295,w:61.6,h:31}——
    # PRIMARY 横向完全落在 toast 内，纵向交叠 27px，按钮中心在 toast 内（非临界值）。
    # 结论：CI 默认视口下 toast 根本不遮 PRIMARY；本例证明的是「真遮住时 pointer-events:none 仍放行」。
    page.set_viewport_size({"width": 900, "height": 360})
    _install_page_latch(page)
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor-primary")).to_be_visible()
    _assert_diag_surface(page)

    page.evaluate("() => window.Reader3NotesDiag.showToast('occlusion-probe')")
    _wait_until(page, "() => window.__r3latch.toastEvents.length >= 1", "一个 toast 事件")
    events = _latch(page)["toastEvents"]
    ev = events[0]
    primary_box = page.get_by_test_id("rd-note-editor-primary").bounding_box()
    assert primary_box is not None, "rd-note-editor-primary 没有 bounding box"

    # (1) 前置条件：断言，不是假设。
    assert _intersects(ev["rect"], primary_box), (
        "occlusion precondition no longer holds at this viewport — this case is vacuous, re-derive the geometry"
        f"（toast rect={ev['rect']}，primary box={primary_box}，viewport={page.viewport_size}）"
    )
    # (2)
    assert ev["pointerEvents"] == "none", f"toast 的 pointer-events 是 {ev['pointerEvents']!r}，应当是 'none'"
    # (3)
    assert ev["hitAtPrimary"] == "rd-note-editor-primary", (
        f"toast 在屏时，primary 按钮中心的 elementFromPoint 命中的是 {ev['hitAtPrimary']!r}"
    )
    # 活体对照：真的点得下去。
    page.get_by_test_id("rd-note-editor-primary").click()


def test_w1_c8_back_to_back_create_rejections_each_report_through_the_helper_with_no_legacy_line(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W1-C8 · S3（009 #50 改判）：`createAnnotation` 的 POST 被拒出口背靠背触发两次 ⇒ 两条
    `op:"create"`/`status:500` 的 ring 条目、两条 `notes write failed` 行、零条遗留行；文案、单例与
    非遮挡照旧。改判理由（规则 12）：维护者 2026-09-30 对 009 #50 的裁定把建标注出口从遗留通道
    改接到 `reportNotesWriteFailure`，原先「ring 为空、遗留行在」的断言按设计反转，文案从前缀改成全等。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    _route_notes(page, method="POST", mode="fulfill500")
    frame = open_ch0(page, live_server, expected_marks=0)
    base_errors = len(errors)

    _fire_create_500(page, frame, "rd-anno-type-marker")
    _wait_until(page, "() => window.__r3latch.toastEvents.length >= 1", "第一次被拒后的 rd-toast 事件")
    _fire_create_500(page, frame, "rd-anno-type-wavy")
    _wait_until(page, "() => window.__r3latch.toastEvents.length >= 2", "第二次被拒后的 rd-toast 事件")

    events = _latch(page)["toastEvents"]
    assert events[1]["insertedAt"] - events[0]["insertedAt"] < TOAST_LIFETIME_MS, (
        "the two create toasts did not overlap — `liveCount == 1` proves nothing here; re-tighten the flow"
        f"（间隔 {events[1]['insertedAt'] - events[0]['insertedAt']:.0f}ms）"
    )
    assert len(events) == 2, f"两次调用应当是两个 toast 事件：{events}"
    assert all(e["liveCount"] == 1 for e in events), f"toast 叠起来了：{events}"
    for e in events:
        assert e["text"] == CREATE_REJECTED_TOAST_500, (
            f"建标注被拒的 toast 文案不对（或丢了状态码插值）：{e['text']!r}"
        )
        assert e["pointerEvents"] == "none", f"建标注出口的 toast 没继承 pointer-events:none：{e}"

    ring = _diag_entries(page) or []
    assert len(ring) == 2, f"两次被拒应当恰好两条 ring 条目（009 #50）：{ring}"
    for e in ring:
        assert e["op"] == "create" and e["status"] == 500 and e["requested"] is True and e["ok"] is False, (
            f"建标注被拒的 ring 条目字段不对：{e}"
        )

    window = _app_errors(errors[base_errors:])
    legacy = [m for m in window if m.text.startswith(LEGACY_CREATE_CONSOLE_PREFIX)]
    assert legacy == [], f"建标注出口还在打遗留 console 行：{[m.text for m in legacy]}"
    diag = [m for m in window if DIAG_CONSOLE_RE.match(m.text)]
    assert len(diag) == 2, f"应当恰好两条 notes write failed 行：{[m.text for m in window]}"
    for m, e in zip(diag, ring):
        payload = json.loads(DIAG_CONSOLE_RE.match(m.text).group(1))  # type: ignore[union-attr]
        assert {k: payload[k] for k in ENTRY_KEYS} == {k: e[k] for k in ENTRY_KEYS}, (
            f"console 负载与 ring 条目不一致：\n  console {payload}\n  ring    {e}"
        )
        assert payload["message"] == CREATE_REJECTED_TOAST_500, f"console 负载的 message 不是 toast 文案：{payload}"

    # 落盘断言放在最后：文件轮询不能先把 toast 寿命耗掉（Race note §0.2）。
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "500 没有真的注入上：有东西落盘了"


# ===========================================================================
# Unit: saveNote() 的 PUT 编辑分支 — WI-3
# ===========================================================================
#
# Law：一次失败的编辑什么都不丢——编辑器的关闭是对「这次写落地了」的断言；失败时
# `notes.json` 与编辑前逐字节相同，用户的字仍在 `rd-note-editor-input` 里；失败的响应
# 永远不推进客户端的版本（`notesEtag`）。
#
# 预置总是「目标 note ＋ 同章一条 marker 旁观条」：W3-C5 的 `assert_bystanders_unchanged`
# 在零旁观条时会直接抛（空转即红），所以所有 WI-3 用例共用同一份两条的预置，失败侧与成功侧
# 才是同一个流程的两面。旁观条取 marker 而不是第二条 note，理由同 W-7：两条 note 的 `<mark>`
# 在 DOM 上不可分。

#: 旁观 marker 覆盖的文字（第 0 章里「One」这一段，与 W-7 同一处）。
W3_BYSTANDER_QUOTE = "One"

#: Chromium 自己打的资源加载失败行（`Failed to load resource: …500…` / `…net::ERR_FAILED`）。
#: 它是**浏览器**发的，不是页面 JS 的 `console.error`；每一次 fulfill(500) / abort 都会有一条，
#: 且与实现无关。「恰好一条 console.error」数的是**应用**发的行，所以把它排除在增量之外。
#: 实测（2026-09-22）：未改实现时 PUT 被 fulfill(500) ⇒ 恰好一条这样的行，且没有任何应用行。
BROWSER_RESOURCE_ERROR_PREFIX = "Failed to load resource:"

_EDIT_ENTRY_JS = (
    "() => !!window.Reader3NotesDiag && "
    "window.Reader3NotesDiag.entries().some((e) => e.op === 'edit')"
)


def _app_errors(errors: List[ConsoleMessage]) -> List[ConsoleMessage]:
    return [m for m in errors if not m.text.startswith(BROWSER_RESOURCE_ERROR_PREFIX)]


def _w3_seed(books_dir: Path, token: str) -> Dict[str, str]:
    note_id = f"w3-note-{token}"
    bystander_id = f"w3-bystander-{token}"
    original = f"original-{token}"
    seed_notes(
        books_dir,
        BOOK_ID,
        [
            {
                "id": note_id,
                "chapter_index": CH0_INDEX,
                "type": "note",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "note_text": original,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": bystander_id,
                "chapter_index": CH0_INDEX,
                "type": "marker",
                "color": "blue",
                "quote": W3_BYSTANDER_QUOTE,
                "created_at": "2026-01-01T00:00:01+00:00",
            },
        ],
    )
    return {"note_id": note_id, "bystander_id": bystander_id, "original": original}


def _w3_open_editor(page: Page, live_server: str, seed: Dict[str, str]) -> None:
    """打开第 0 章，点目标 `<mark>` 进入**编辑**态（`openNoteEditorWithExisting` 置 `editingNoteId`）。"""
    frame = open_ch0(page, live_server, expected_marks=2)
    # 取值先落进局部变量：f-string 里嵌 `seed["note_id"]` 的内层引号会让选择器 lint 的
    # ATTR_RE 读不出 `[data-annotation-id="…"]`，报成违规。
    note_id = seed["note_id"]
    mark = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]'
    )
    expect(mark).to_have_text(CH0_QUOTE)
    mark.click()
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    # 带着旧正文打开才说明走的是编辑分支（W-7 同款判据）。
    expect(page.get_by_test_id("rd-note-editor-input")).to_have_value(seed["original"])


def _edit_entries(page: Page) -> List[Dict[str, Any]]:
    return [e for e in (_diag_entries(page) or []) if e.get("op") == "edit"]


def test_w3_c1_a_failed_edit_conserves_both_the_disk_and_the_users_text(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W3-C1 · S5：PUT 被 500 ⇒ 编辑器还开着、字还在、盘上逐条不变、恰好一个 toast 与一条应用 console.error。"""
    token = _token()
    seed = _w3_seed(e2e_books_dir, token)
    _install_page_latch(page)
    errors = _console_errors(page)
    _w3_open_editor(page, live_server, seed)
    pre = read_notes(e2e_books_dir, BOOK_ID)

    edited = f"edited-{token}"
    page.get_by_test_id("rd-note-editor-input").fill(edited)
    _route_notes(page, method="PUT", mode="fulfill500")
    base_toasts = len(_latch(page)["toastEvents"])
    base_app_errors = len(_app_errors(errors))
    page.get_by_test_id("rd-note-editor-primary").click()
    _wait_until(page, _EDIT_ENTRY_JS, "Reader3NotesDiag 里出现一条 op == 'edit' 的失败条目")

    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    assert page.get_by_test_id("rd-note-editor-input").input_value() == edited, (
        "失败的编辑把用户的字从编辑器里弄丢了"
    )
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 1, f"这一次失败的编辑应当恰好一个 toast 事件：{toasts}"
    app_window = _app_errors(errors)[base_app_errors:]
    assert len(app_window) == 1, f"应当恰好一条应用 console.error：{[m.text for m in app_window]}"
    assert DIAG_CONSOLE_RE.match(app_window[0].text), f"console 行不合契约：{app_window[0].text!r}"
    edits = _edit_entries(page)
    assert len(edits) == 1, f"应当恰好一条 op:'edit' 条目：{edits}"
    assert edits[0]["id"] == seed["note_id"], f"失败条目的 id 不是被编辑的那条：{edits[0]}"

    # 落盘断言放最后（§0.2 Race note）：整列表等值，不是「条数相同」。
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "失败的编辑改动了 notes.json（部分写 / 幻影写）"


@pytest.mark.parametrize("mode", ["fulfill500", "abort"])
def test_w3_c3_the_two_failure_poles_are_distinguishable(
    page: Page, live_server: str, e2e_books_dir: Path, mode: str
) -> None:
    """W3-C3 · S2：`fulfill(500)` 与 `abort()` 在屏幕上一样，在 ring 条目里必须分得开；且 `requested` 有线上佐证。"""
    token = _token()
    seed = _w3_seed(e2e_books_dir, token)
    _w3_open_editor(page, live_server, seed)
    pre = read_notes(e2e_books_dir, BOOK_ID)

    page.get_by_test_id("rd-note-editor-input").fill(f"edited-{token}")  # lint-e2e-selectors: allow —— fill 的实参是输入正文，不是选择器
    state = _route_notes(page, method="PUT", mode=mode)
    before = Counter(state.counts)
    page.get_by_test_id("rd-note-editor-primary").click()
    _wait_until(page, _EDIT_ENTRY_JS, f"[{mode}] 一条 op == 'edit' 的失败条目")

    edits = _edit_entries(page)
    assert len(edits) == 1, f"[{mode}] 应当恰好一条 op:'edit' 条目：{edits}"
    entry = edits[0]
    assert entry["id"] == seed["note_id"], f"[{mode}] 条目 id 不对：{entry}"
    if mode == "fulfill500":
        assert entry["status"] == 500, f"[fulfill500] status 应当是 500：{entry}"
    else:
        assert entry["status"] is None, f"[abort] status 必须是 null（不是 0 / -1 / 缺省）：{entry}"
    assert entry["ok"] is False, f"[{mode}] ok 应当是 False：{entry}"
    assert entry["requested"] is True, f"[{mode}] requested 应当是 True：{entry}"
    assert _writes(state.counts) - _writes(before) == 1, (
        f"[{mode}] 路由层这一窗口里观察到的写请求不是恰好 1 次：before={dict(before)} after={dict(state.counts)}"
        "——`requested: true` 没有线上佐证"
    )
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, f"[{mode}] 失败的编辑改动了 notes.json"


def test_w3_c6_a_failed_edit_response_never_advances_the_client_etag(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W3-C6 · S5：带 ETag 的 500 不许毒化 `notesEtag`，也不许把它清空；下一次写仍带服务端真发过的版本。"""
    token = _token()
    poison = f'"poison-{token}"'
    seed = _w3_seed(e2e_books_dir, token)
    wire = _install_wire_log(page)
    _install_page_latch(page)
    _w3_open_editor(page, live_server, seed)

    page.get_by_test_id("rd-note-editor-input").fill(f"edited-{token}")  # lint-e2e-selectors: allow —— fill 的实参是输入正文，不是选择器
    _route_notes(page, method="PUT", mode="fulfill500", headers={"ETag": poison})
    page.get_by_test_id("rd-note-editor-primary").click()
    _wait_until(page, _EDIT_ENTRY_JS, "毒化 500 之后一条 op == 'edit' 的失败条目")
    i_fail = len(wire)
    page.unroute("**/api/notes/**")

    after = f"after-{token}"
    page.get_by_test_id("rd-note-editor-input").fill(after)
    page.get_by_test_id("rd-note-editor-primary").click()
    wait_for_note_text(e2e_books_dir, BOOK_ID, seed["note_id"], after, page=page)

    writes = wire.writes_after(i_fail)
    assert writes, f"失败之后没有观察到任何写请求：{wire.entries[i_fail:]}"
    if_match = writes[0][3]
    committed = wire.last_2xx_etag_before(i_fail)
    assert committed is not None, (
        f"失败之前的线上日志里没有带 ETag 的 2xx /api/notes/ 响应（读路径没播种？）：{wire.entries[:i_fail]}"
    )
    assert if_match != poison, f"失败响应的 ETag 毒化了下一次写的 If-Match：{if_match!r}"
    assert if_match is not None, "下一次写没带 If-Match——失败时把 notesEtag 清空了，DEG-S5 被悄悄解除武装"
    assert if_match == committed, (
        f"下一次写的 If-Match {if_match!r} 不是服务端最后一次真正提交的版本 {committed!r}"
    )
    expect(page.get_by_test_id("rd-conflict-dialog")).not_to_be_visible()
    edits = _edit_entries(page)
    assert len(edits) == 1, f"应当恰好一条 op:'edit' 条目（第二次成功的写不许记）：{edits}"


def test_w3_c4_a_409_on_edit_still_opens_the_conflict_dialog(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W3-C4 · S3：409 走 DEG-S5 冲突对话框，不被新的 `!ok` 守卫截成一个普通失败 toast。"""
    token = _token()
    seed = _w3_seed(e2e_books_dir, token)
    wire = _install_wire_log(page)
    _install_page_latch(page)
    _w3_open_editor(page, live_server, seed)
    pre = read_notes(e2e_books_dir, BOOK_ID)
    target = next(r for r in pre if r["id"] == seed["note_id"])
    remote = dict(target, note_text="remote-version")

    page.get_by_test_id("rd-note-editor-input").fill(f"edited-{token}")  # lint-e2e-selectors: allow —— fill 的实参是输入正文，不是选择器
    state = _route_notes(
        page,
        method="PUT",
        mode="conflict",
        wire_log=wire,
        conflict_body=lambda etag: {"etag": etag, "annotation": remote},
    )
    base_toasts = len(_latch(page)["toastEvents"])
    page.get_by_test_id("rd-note-editor-primary").click()

    expect(page.get_by_test_id("rd-conflict-dialog")).to_be_visible()
    assert state.injected_etag is not None, (
        "注入的 409 体里 etag 是 null——`if (body?.etag)` 会跳过，本例会因错误的理由变绿"
    )
    expect(page.get_by_test_id("rd-conflict-keep-mine")).to_be_visible()
    assert _edit_entries(page) == [], "409 是冲突，不是写失败：不该往 ring 里记 op:'edit'"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 0, f"409 不该弹失败 toast：{toasts}"


def test_w3_c5_the_success_path_is_unchanged(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W3-C5 · S1：不装任何路由的真实编辑——落盘、编辑器关闭、旁观条不动、零诊断。W3-C1/C3/C4/C6 的真路径对照。"""
    token = _token()
    seed = _w3_seed(e2e_books_dir, token)
    _install_page_latch(page)
    errors = _console_errors(page)
    _w3_open_editor(page, live_server, seed)
    pre = read_notes(e2e_books_dir, BOOK_ID)
    base_toasts = len(_latch(page)["toastEvents"])
    base_errors = len(errors)

    edited = f"edited-{token}"
    page.get_by_test_id("rd-note-editor-input").fill(edited)
    page.get_by_test_id("rd-note-editor-primary").click()
    record = wait_for_note_text(e2e_books_dir, BOOK_ID, seed["note_id"], edited, page=page)
    assert record["id"] == seed["note_id"]

    expect(page.get_by_test_id("rd-note-editor")).not_to_be_visible()
    post = read_notes(e2e_books_dir, BOOK_ID)
    assert_bystanders_unchanged(pre, post, changed_ids={seed["note_id"]})
    _wait_until(
        page,
        "() => window.__r3latch.updatedEvents >= 1",
        "成功的编辑派发 reader3:annotations:updated",
    )
    assert _diag_entries(page) == [], f"成功的编辑不该留下任何诊断条目：{_diag_entries(page)}"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 0, f"成功的编辑不该弹 toast：{toasts}"
    window = errors[base_errors:]
    assert len(window) == 0, f"成功的编辑不该有 console.error：{[m.text for m in window]}"


# ===========================================================================
# Unit: `deleteAnnotations` 与它的改色调用方 `toggleAnnotation` — WI-4（＋ 修订 A2）
# ===========================================================================
#
# 律：**宣告删掉了 ⇒ 盘上确实没有；删失败了 ⇒ 调用方接下来要做的事停下；停下不是永久的。**
# 多条删除的策略由矩阵钉死：失败不中断循环（部分进度保留）、每个失败 id 各报一次、有任何
# 一条失败就不宣告整体成功（不 `setCurrentAnnotations([])`、不派发
# `reader3:annotations:updated`），并返回一个调用方能检查的结果（A2）。

from helpers import (  # type: ignore[import-not-found]  # noqa: E402
    clear_selection_and_drain,
    mark_id_union,
    scan_marks,
    settle_marks,
    wait_for_notes,
)

#: 两条标注完全覆盖同一段 `CH0_QUOTE` 时渲染出的 `rd-anno-span` 个数（W4-C3）。
#: **这是渲染细节，不是规格**：从红跑实测钉下来，只给 `settle_marks` 当等待条件用。
#: W4-C3 的每一条判断都按 id（`mark_id_union`）下，从不按个数下，所以分段方式哪天变了，
#: 只需要重钉这一个数，没有任何断言会因此悄悄变弱。[CI RISK: DOM 分段个数]
_OVERLAP_MARKS = 1

_DELETE_ENTRY_JS = (
    "() => !!window.Reader3NotesDiag && "
    "window.Reader3NotesDiag.entries().some((e) => e.op === 'delete')"
)

#: 页面里 `deleteCurrentAnnotation` 将要枚举的 id 顺序，用与实现**同一个表达式**读出来（W4-C3）。
_DELETE_ORDER_JS = """() => {
  const ui = window.Reader3AnnotationUI;
  if (!ui) return null;
  const meta = ui.currentAnnotationMeta?.length
    ? ui.currentAnnotationMeta
    : ui.getAnnotationMetaForRange(ui.currentRange);
  return meta.map((m) => m.id);
}"""

_ENTRY_CONTRACT_KEYS = ("op", "id", "status", "ok", "requested")


def _w4_seed(books_dir: Path, token: str, specs: List[tuple]) -> List[str]:
    """在 `CH0_QUOTE` 上预置 `specs` 里的每一条 `(type, color)`，返回按顺序的 id。id 带本次运行的 token。"""
    ids: List[str] = []
    records: List[Dict[str, Any]] = []
    for n, (kind, color) in enumerate(specs):
        anno_id = f"w4-{kind}-{n}-{token}"
        ids.append(anno_id)
        records.append(
            {
                "id": anno_id,
                "chapter_index": CH0_INDEX,
                "type": kind,
                "color": color,
                "quote": CH0_QUOTE,
                "created_at": f"2026-01-01T00:00:0{n}+00:00",
            }
        )
    seed_notes(books_dir, BOOK_ID, records)
    return ids


def _delete_entries(page: Page) -> List[Dict[str, Any]]:
    return [e for e in (_diag_entries(page) or []) if e.get("op") == "delete"]


def _contract(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: entry.get(k) for k in _ENTRY_CONTRACT_KEYS}


def _updated(page: Page) -> int:
    return int(_latch(page)["updatedEvents"])


def test_w4_c1_a_failed_delete_leaves_the_annotation_on_disk_and_on_screen(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C1 · S5：DELETE 被 500 ⇒ 盘上逐条不变、mark 仍在屏幕上、一条带 id 的 ring 条目、不宣告成功。"""
    token = _token()
    (seeded_id,) = _w4_seed(e2e_books_dir, token, [("marker", "yellow")])
    _install_page_latch(page)
    errors = _console_errors(page)
    frame = open_ch0(page, live_server, expected_marks=1)
    pre = read_notes(e2e_books_dir, BOOK_ID)

    select_in_frame(frame, CH0_QUOTE)
    _route_notes(page, method="DELETE", mode="fulfill500")
    base_toasts = len(_latch(page)["toastEvents"])
    base_app_errors = len(_app_errors(errors))
    base_updated = _updated(page)
    page.get_by_test_id("rd-anno-delete").click()
    _wait_until(page, _DELETE_ENTRY_JS, "Reader3NotesDiag 里出现一条 op == 'delete' 的失败条目")

    settle_marks(page, frame, 1)
    assert mark_id_union(scan_marks(frame)) == {seeded_id}, (
        "删除失败了，屏幕上却不再是那条 mark——界面把它显示成已删除"
    )
    deletes = _delete_entries(page)
    assert len(deletes) == 1, f"应当恰好一条 op:'delete' 条目：{deletes}"
    assert _contract(deletes[0]) == {
        "op": "delete",
        "id": seeded_id,
        "status": 500,
        "ok": False,
        "requested": True,
    }, f"delete 失败条目不合契约：{deletes[0]}"
    assert _updated(page) - base_updated == 0, (
        "删除失败了却派发了 reader3:annotations:updated——宣告了整体成功"
    )
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 1, f"这一次失败的删除应当恰好一个 toast 事件：{toasts}"
    app_window = _app_errors(errors)[base_app_errors:]
    assert len(app_window) == 1, f"应当恰好一条应用 console.error：{[m.text for m in app_window]}"
    assert DIAG_CONSOLE_RE.match(app_window[0].text), f"console 行不合契约：{app_window[0].text!r}"

    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "失败的删除改动了 notes.json"


def test_w4_c2_the_abort_pole_on_delete_has_a_null_status_and_a_real_request(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C2 · S2：DELETE 被 abort ⇒ `status is None`、`requested: true` 且路由层真看见了这一次写。"""
    token = _token()
    (seeded_id,) = _w4_seed(e2e_books_dir, token, [("marker", "yellow")])
    frame = open_ch0(page, live_server, expected_marks=1)
    pre = read_notes(e2e_books_dir, BOOK_ID)

    select_in_frame(frame, CH0_QUOTE)
    state = _route_notes(page, method="DELETE", mode="abort")
    before = Counter(state.counts)
    page.get_by_test_id("rd-anno-delete").click()
    _wait_until(page, _DELETE_ENTRY_JS, "[abort] 一条 op == 'delete' 的失败条目")

    deletes = _delete_entries(page)
    assert len(deletes) == 1, f"[abort] 应当恰好一条 op:'delete' 条目：{deletes}"
    entry = deletes[0]
    assert entry["status"] is None, f"[abort] status 必须是 null（不是 0 / -1 / 缺省）：{entry}"
    assert _contract(entry) == {
        "op": "delete",
        "id": seeded_id,
        "status": None,
        "ok": False,
        "requested": True,
    }, f"[abort] delete 失败条目不合契约：{entry}"
    assert _writes(state.counts) - _writes(before) == 1, (
        f"[abort] 路由层这一窗口里观察到的写请求不是恰好 1 次：before={dict(before)} after={dict(state.counts)}"
        "——`requested: true` 没有线上佐证"
    )
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "[abort] 失败的删除改动了 notes.json"


@pytest.mark.parametrize("fail_position", ["first", "last"])
def test_w4_c3_multi_id_partial_failure_keeps_progress_and_reports_per_id(
    page: Page, live_server: str, e2e_books_dir: Path, fail_position: str
) -> None:
    """W4-C3 · S5：两条同段标注里只有一条的 DELETE 失败——另一条真删掉、只为失败那条记一条、不宣告成功。

    按失败 id 在枚举里的**位置**参数化：只失败第一条时，「第一次失败就 break」会让另一条
    也留在盘上，于是 `first` 那一项红；两项都绿的唯一实现是「失败不中断循环」。
    """
    token = _token()
    seeded = _w4_seed(e2e_books_dir, token, [("marker", "yellow"), ("wavy", "yellow")])
    _install_page_latch(page)
    frame = open_ch0(page, live_server, expected_marks=_OVERLAP_MARKS)

    select_in_frame(frame, CH0_QUOTE)
    order = page.evaluate(_DELETE_ORDER_JS)
    assert isinstance(order, list) and len(order) == 2 and set(order) == set(seeded), (
        f"删除将要枚举的 id 不是那两条预置（本例会空转）：{order!r} vs {seeded!r}"
    )
    fail_id = order[0] if fail_position == "first" else order[-1]
    (other_id,) = [i for i in order if i != fail_id]
    _route_notes(
        page,
        method="DELETE",
        mode="fulfill500",
        match=lambda route: fail_id in route.request.url,
    )
    base_updated = _updated(page)
    # WI-15（审计 #8）：`wait_for_notes` 是纯 Python 的 sleep 轮询，期间同步 route 回调——
    # 包括 conftest 给每个 context 挂的那道 `**/*` 出网闸——一个都跑不了。下面那个
    # `_wait_until` 只等到**失败**那条的诊断条目，对成功那条（other_id）的 DELETE 什么都没
    # 说：它可能还卡在出网闸的回调上。点完直接轮盘，正确的产品行为也会等到超时。
    try:
        with page.expect_response(
            lambda r: r.request.method == "DELETE" and other_id in r.url
        ):
            page.get_by_test_id("rd-anno-delete").click()
    except PlaywrightError as exc:
        raise AssertionError(
            f"[{fail_position}] 成功那条 {other_id!r} 的 DELETE 响应没等到"
            f"（{type(exc).__name__}）——它要么没发出去，要么卡在路由层"
        ) from None
    _wait_until(page, _DELETE_ENTRY_JS, f"[{fail_position}] 一条 op == 'delete' 的失败条目")

    wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    settle_marks(page, frame, 1)
    on_disk = {r["id"] for r in read_notes(e2e_books_dir, BOOK_ID)}
    assert on_disk == {fail_id}, (
        f"[{fail_position}] 盘上应当只剩失败的那条 {fail_id!r}（{other_id!r} 应当真删掉了）：{on_disk}"
    )
    deletes = _delete_entries(page)
    assert len(deletes) == 1, f"[{fail_position}] 应当恰好一条 op:'delete' 条目：{deletes}"
    assert deletes[0]["id"] == fail_id, (
        f"[{fail_position}] 失败条目的 id 不是失败的那条 {fail_id!r}：{deletes[0]}"
    )
    assert _updated(page) - base_updated == 0, (
        f"[{fail_position}] 有一条删除失败了却派发了 reader3:annotations:updated"
    )
    assert mark_id_union(scan_marks(frame)) == {fail_id}, (
        f"[{fail_position}] 屏幕上剩下的 mark 应当恰好是失败的那条 {fail_id!r}"
    )


def test_w4_c5_a_failed_delete_response_never_advances_the_client_etag(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C5 · S5：`notesWriteWithResync` 上带 ETag 的 500 不许毒化 `notesEtag`，也不许清空它。"""
    token = _token()
    poison = f'"poison-{token}"'
    (seeded_id,) = _w4_seed(e2e_books_dir, token, [("marker", "yellow")])
    wire = _install_wire_log(page)
    _install_page_latch(page)
    frame = open_ch0(page, live_server, expected_marks=1)

    select_in_frame(frame, CH0_QUOTE)
    _route_notes(page, method="DELETE", mode="fulfill500", headers={"ETag": poison})
    page.get_by_test_id("rd-anno-delete").click()
    _wait_until(page, _DELETE_ENTRY_JS, "毒化 500 之后一条 op == 'delete' 的失败条目")
    i_fail = len(wire)
    page.unroute("**/api/notes/**")

    clear_selection_and_drain(page, frame)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-wavy").click()
    wait_for_notes(e2e_books_dir, BOOK_ID, 2, page=page)

    writes = wire.writes_after(i_fail)
    assert writes, f"失败之后没有观察到任何写请求：{wire.entries[i_fail:]}"
    if_match = writes[0][3]
    committed = wire.last_2xx_etag_before(i_fail)
    assert committed is not None, (
        f"失败之前的线上日志里没有带 ETag 的 2xx /api/notes/ 响应（读路径没播种？）：{wire.entries[:i_fail]}"
    )
    assert if_match != poison, f"失败响应的 ETag 毒化了下一次写的 If-Match：{if_match!r}"
    assert if_match is not None, "下一次写没带 If-Match——失败时把 notesEtag 清空了，DEG-S5 被悄悄解除武装"
    assert if_match == committed, (
        f"下一次写的 If-Match {if_match!r} 不是服务端最后一次真正提交的版本 {committed!r}"
    )
    assert seeded_id in {r["id"] for r in read_notes(e2e_books_dir, BOOK_ID)}, (
        "删除失败的那条不在盘上了"
    )
    entries = _diag_entries(page) or []
    assert len(entries) == 1 and entries[0]["op"] == "delete", (
        f"应当恰好一条 op:'delete' 条目，成功的建不许记：{entries}"
    )


def _w4_recolor_fails(
    page: Page, live_server: str, e2e_books_dir: Path, token: str
) -> SimpleNamespace:
    """W4-C6 / W4-C7 共用的前半段：一条黄色 wavy，改成绿色重按 wavy，那次 DELETE 被 500。

    `toggleAnnotation("wavy")` 在 `selectedColor="green"` 下：同色的 wavy 没有，任意色的
    wavy 是 `[S]` ⇒ 先 `deleteAnnotations([S])`，再（错误的实现）`createAnnotation`。那次
    POST **故意不拦**：真发生了就真落盘，`read_notes` 当场显形。
    """
    (seeded_id,) = _w4_seed(e2e_books_dir, token, [("wavy", "yellow")])
    _install_page_latch(page)
    errors = _console_errors(page)
    frame = open_ch0(page, live_server, expected_marks=1)
    pre = read_notes(e2e_books_dir, BOOK_ID)

    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-color-green").click()
    _route_notes(page, method="DELETE", mode="fulfill500")
    base = SimpleNamespace(
        toasts=len(_latch(page)["toastEvents"]),
        app_errors=len(_app_errors(errors)),
        updated=_updated(page),
    )
    page.get_by_test_id("rd-anno-type-wavy").click()
    _wait_until(page, _DELETE_ENTRY_JS, "改色那次删除失败后一条 op == 'delete' 的条目")
    # 等网络静默再读盘：错误的实现会在失败之后紧接着发 POST，不等它落地就读盘会假绿。
    settle_marks(page, frame, 1)
    return SimpleNamespace(
        seeded_id=seeded_id, frame=frame, pre=pre, errors=errors, base=base
    )


def test_w4_c6_a_failed_recolor_delete_does_not_go_on_to_create(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C6 · S5：改色的「先删后建」里删失败了 ⇒ 不建。盘上整列表不变、只有一条 ring 条目。"""
    run = _w4_recolor_fails(page, live_server, e2e_books_dir, _token())

    assert read_notes(e2e_books_dir, BOOK_ID) == run.pre, (
        "改色那次删除失败了，盘上却变了——多半是接着建出了一条新的（ring 说删失败、盘说写成功）"
    )
    entries = _diag_entries(page) or []
    assert len(entries) == 1, f"整个用例应当恰好一条 ring 条目：{entries}"
    assert _contract(entries[0]) == {
        "op": "delete",
        "id": run.seeded_id,
        "status": 500,
        "ok": False,
        "requested": True,
    }, f"改色删除失败条目不合契约：{entries[0]}"
    toasts = _latch(page)["toastEvents"][run.base.toasts:]
    assert len(toasts) == 1, f"这一次失败的改色应当恰好一个 toast 事件：{toasts}"
    app_window = _app_errors(run.errors)[run.base.app_errors:]
    assert len(app_window) == 1, f"应当恰好一条应用 console.error：{[m.text for m in app_window]}"
    assert _updated(page) - run.base.updated == 0, (
        "改色那次删除失败了却派发了 reader3:annotations:updated"
    )
    assert mark_id_union(scan_marks(run.frame)) == {run.seeded_id}, (
        "屏幕上应当只剩旧颜色的那一条 mark"
    )


def test_w4_c7_the_failure_is_not_sticky_a_later_recolor_still_creates(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C7 · S5：前一次改色删失败之后，原因消失，再改一次色必须真的删旧建新——失败不是粘滞的。"""
    run = _w4_recolor_fails(page, live_server, e2e_books_dir, _token())
    assert read_notes(e2e_books_dir, BOOK_ID) == run.pre, "前半段：失败的改色改动了 notes.json"

    page.unroute("**/api/notes/**")
    clear_selection_and_drain(page, run.frame)
    select_in_frame(run.frame, CH0_QUOTE)
    base_updated = _updated(page)
    page.get_by_test_id("rd-anno-color-blue").click()
    try:
        with page.expect_response(
            lambda r: r.request.method == "POST" and NOTES_ENDPOINT_MARKER in r.url
        ):
            page.get_by_test_id("rd-anno-type-wavy").click()
    except PlaywrightError as exc:
        raise AssertionError(
            f"第二次（未拦截的）改色没有发出建新的那次 POST——失败被粘住了（{type(exc).__name__}）"
        ) from None
    wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    settle_marks(page, run.frame, 1)
    after = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == 1, f"改色之后盘上应当恰好一条：{after}"
    assert after[0]["color"] == "blue" and after[0]["type"] == "wavy", (
        f"第二次改色没有真的发生：{after[0]}"
    )
    assert after[0]["id"] != run.seeded_id, (
        f"盘上那条还是旧 id {run.seeded_id!r}——旧的没删 / 新的没建"
    )
    assert mark_id_union(scan_marks(run.frame)) == {after[0]["id"]}, (
        "屏幕与盘面不一致：屏幕上的 mark 不是新建的那一条"
    )
    entries = _diag_entries(page) or []
    assert len(entries) == 1, (
        f"整个用例应当恰好一条 ring 条目（第二次成功的改色不许记）：{entries}"
    )
    _wait_until(
        page,
        f"() => window.__r3latch.updatedEvents >= {base_updated + 1}",
        "成功的改色派发 reader3:annotations:updated",
    )


def test_w4_c4_the_success_path_is_unchanged(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W4-C4 · S1：不装任何路由的真实删除——盘上清空、mark 消失、派发 updated、零诊断。W4-C1/C2/C3/C5/C7 的真路径对照。"""
    token = _token()
    _w4_seed(e2e_books_dir, token, [("marker", "yellow")])
    _install_page_latch(page)
    errors = _console_errors(page)
    frame = open_ch0(page, live_server, expected_marks=1)

    select_in_frame(frame, CH0_QUOTE)
    base_toasts = len(_latch(page)["toastEvents"])
    base_errors = len(errors)
    base_updated = _updated(page)
    page.get_by_test_id("rd-anno-delete").click()

    assert wait_for_notes(e2e_books_dir, BOOK_ID, 0, page=page) == []
    settle_marks(page, frame, 0)
    _wait_until(
        page,
        f"() => window.__r3latch.updatedEvents >= {base_updated + 1}",
        "成功的删除派发 reader3:annotations:updated",
    )
    assert _diag_entries(page) == [], f"成功的删除不该留下任何诊断条目：{_diag_entries(page)}"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 0, f"成功的删除不该弹 toast：{toasts}"
    window = errors[base_errors:]
    assert len(window) == 0, f"成功的删除不该有 console.error：{[m.text for m in window]}"


# ===========================================================================
# Unit: `resolveConflict` 的「保留我的」写 — WI-5（＋ 修订 A1）
# ===========================================================================
#
# 律一：**收尾 ⇔ 落盘。** `settleConflict`（关对话框、采纳本地那版）当且仅当「保留我的」那次
# PUT 真的成功时才跑；失败时对话框留着，用户的字留着。
# 律二：**`notesEtag` 只经服务端真提交过的版本前进，且从不退回到空。** 失败响应带回的 ETag
# 不吸收（A1：守卫在 `rememberNotesEtag` 里面）；409 体里服务端主动告知的版本照吸收。
#
# 冲突对话框**没有任何自己的关闭路径**（`showModal()` ＋ `cancel` 被 `preventDefault()`），
# 开着的时候对话框外的一切控件都在遮罩后面：本单元的用例从不在对话框开着时去点
# `rd-note-editor-primary`；重试一律再点对话框**里面**的 `rd-conflict-keep-mine`；
# `input_value()` 不做可操作性检查，所以隔着遮罩读 textarea 仍然合法。
#
# 到达对话框用的是 W3-C4 的机制：PUT 被合成 409，体里的 `etag` 是**真服务端**最后一次发出的
# 那个（§0.4），于是客户端在 `openConflictFromResponse` 里吸收到的版本服务端认得。

_KEEP_MINE_ENTRY_JS = (
    "() => !!window.Reader3NotesDiag && "
    "window.Reader3NotesDiag.entries().some((e) => e.op === 'conflict-keep-mine')"
)


def _keep_mine_entries(page: Page) -> List[Dict[str, Any]]:
    return [e for e in (_diag_entries(page) or []) if e.get("op") == "conflict-keep-mine"]


def _w5_open_conflict(
    page: Page, live_server: str, e2e_books_dir: Path, token: str
) -> SimpleNamespace:
    """W5 共用的前半段：进编辑态、敲入本地那版、PUT 被合成 409（真 ETag）⇒ 冲突对话框开着。

    返回前**撤掉路由**：接下来被测的那一步各用例自己决定拦不拦。
    """
    seed = _w3_seed(e2e_books_dir, token)
    wire = _install_wire_log(page)
    _install_page_latch(page)
    errors = _console_errors(page)
    _w3_open_editor(page, live_server, seed)
    target = next(r for r in read_notes(e2e_books_dir, BOOK_ID) if r["id"] == seed["note_id"])
    theirs = f"theirs-{token}"
    remote = dict(target, note_text=theirs)
    mine = f"mine-{token}"

    page.get_by_test_id("rd-note-editor-input").fill(mine)
    state = _route_notes(
        page,
        method="PUT",
        mode="conflict",
        wire_log=wire,
        conflict_body=lambda etag: {"etag": etag, "annotation": remote},
    )
    page.get_by_test_id("rd-note-editor-primary").click()
    expect(page.get_by_test_id("rd-conflict-dialog")).to_be_visible()
    page.unroute("**/api/notes/**")
    return SimpleNamespace(
        seed=seed,
        note_id=seed["note_id"],
        wire=wire,
        errors=errors,
        conflict=state,
        mine=mine,
        theirs=theirs,
    )


def test_w5_c1_a_failed_keep_mine_does_not_settle_and_conserves_the_disk(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W5-C1 · S5：「保留我的」那次 PUT 被 500 ⇒ 对话框还开着、本地那版还在、盘上逐条不变、恰好一个通知。"""
    run = _w5_open_conflict(page, live_server, e2e_books_dir, _token())
    assert run.conflict.injected_etag is not None, (
        "注入的 409 体里 etag 是 null——`if (body?.etag)` 会跳过，本例会因错误的理由变绿"
    )

    _route_notes(page, method="PUT", mode="fulfill500")
    pre = read_notes(e2e_books_dir, BOOK_ID)
    base_toasts = len(_latch(page)["toastEvents"])
    base_app_errors = len(_app_errors(run.errors))
    page.get_by_test_id("rd-conflict-keep-mine").click()
    _wait_until(page, _KEEP_MINE_ENTRY_JS, "Reader3NotesDiag 里出现一条 op == 'conflict-keep-mine' 的失败条目")

    expect(page.get_by_test_id("rd-conflict-dialog")).to_be_visible()
    assert page.get_by_test_id("rd-note-editor-input").input_value() == run.mine, (
        "失败的「保留我的」把用户的那一版从编辑器里换掉了（settleConflict 跑了？）"
    )
    entries = _keep_mine_entries(page)
    assert len(entries) == 1, f"应当恰好一条 op:'conflict-keep-mine' 条目：{entries}"
    assert _contract(entries[0]) == {
        "op": "conflict-keep-mine",
        "id": run.note_id,
        "status": 500,
        "ok": False,
        "requested": True,
    }, f"「保留我的」失败条目不合契约：{entries[0]}"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 1, f"这一次失败的「保留我的」应当恰好一个 toast 事件：{toasts}"
    app_window = _app_errors(run.errors)[base_app_errors:]
    assert len(app_window) == 1, f"应当恰好一条应用 console.error：{[m.text for m in app_window]}"
    assert DIAG_CONSOLE_RE.match(app_window[0].text), f"console 行不合契约：{app_window[0].text!r}"
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "失败的「保留我的」改动了 notes.json"


def test_w5_c2_the_abort_pole_on_keep_mine_has_a_null_status_and_a_real_request(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W5-C2 · S2：「保留我的」那次 PUT 被 abort ⇒ `status` 为 null、`requested` 为真且有路由层佐证、不收尾。"""
    run = _w5_open_conflict(page, live_server, e2e_books_dir, _token())
    assert run.conflict.injected_etag is not None, (
        "注入的 409 体里 etag 是 null——`if (body?.etag)` 会跳过，本例会因错误的理由变绿"
    )

    state = _route_notes(page, method="PUT", mode="abort")
    pre = read_notes(e2e_books_dir, BOOK_ID)
    before = Counter(state.counts)
    page.get_by_test_id("rd-conflict-keep-mine").click()
    _wait_until(page, _KEEP_MINE_ENTRY_JS, "[abort] 一条 op == 'conflict-keep-mine' 的失败条目")

    entries = _keep_mine_entries(page)
    assert len(entries) == 1, f"[abort] 应当恰好一条 op:'conflict-keep-mine' 条目：{entries}"
    entry = entries[0]
    assert entry["id"] == run.note_id, f"[abort] 条目 id 不对：{entry}"
    assert entry["status"] is None, f"[abort] status 必须是 null（不是 0 / -1 / 缺省）：{entry}"
    assert entry["ok"] is False, f"[abort] ok 应当是 False：{entry}"
    assert entry["requested"] is True, f"[abort] requested 应当是 True：{entry}"
    assert _writes(state.counts) - _writes(before) == 1, (
        f"[abort] 路由层这一窗口里观察到的写请求不是恰好 1 次：before={dict(before)} after={dict(state.counts)}"
        "——`requested: true` 没有线上佐证"
    )
    expect(page.get_by_test_id("rd-conflict-dialog")).to_be_visible()
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "[abort] 失败的「保留我的」改动了 notes.json"


def test_w5_c3_a_failed_keep_mine_never_advances_the_client_etag_and_the_retry_lands(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W5-C3 · S5：带毒化 ETag 的 500 不许推进也不许清空 `notesEtag`；从对话框里重试，带服务端真版本落盘并收尾。"""
    token = _token()
    poison = f'"poison-{token}"'
    run = _w5_open_conflict(page, live_server, e2e_books_dir, token)
    assert run.conflict.injected_etag is not None, (
        "注入的 409 体里 etag 是 null——`if (body?.etag)` 会跳过，本例会因错误的理由变绿"
    )

    _route_notes(page, method="PUT", mode="fulfill500", headers={"ETag": poison})
    page.get_by_test_id("rd-conflict-keep-mine").click()
    _wait_until(page, _KEEP_MINE_ENTRY_JS, "毒化 500 之后一条 op == 'conflict-keep-mine' 的失败条目")
    i_fail = len(run.wire)
    page.unroute("**/api/notes/**")

    # 重试：对话框开着时唯一够得着的控件就是它自己里面的按钮。
    page.get_by_test_id("rd-conflict-keep-mine").click()
    wait_for_note_text(e2e_books_dir, BOOK_ID, run.note_id, run.mine, page=page)

    writes = run.wire.writes_after(i_fail)
    assert writes, f"失败之后没有观察到任何写请求：{run.wire.entries[i_fail:]}"
    if_match = writes[0][3]
    committed = run.wire.last_2xx_etag_before(i_fail)
    assert committed is not None, (
        f"失败之前的线上日志里没有带 ETag 的 2xx /api/notes/ 响应（读路径没播种？）：{run.wire.entries[:i_fail]}"
    )
    assert if_match != poison, f"失败响应的 ETag 毒化了重试的 If-Match：{if_match!r}"
    assert if_match is not None, "重试没带 If-Match——失败时把 notesEtag 清空了，DEG-S5 被悄悄解除武装"
    assert if_match == committed, (
        f"重试的 If-Match {if_match!r} 不是服务端最后一次真正提交的版本 {committed!r}"
    )
    expect(page.get_by_test_id("rd-conflict-dialog")).not_to_be_visible()
    entries = _keep_mine_entries(page)
    assert len(entries) == 1, f"整个用例应当恰好一条 op:'conflict-keep-mine' 条目（成功的重试不许记）：{entries}"
    toasts = _latch(page)["toastEvents"]
    assert len(toasts) == 1, f"整个用例应当恰好一个 toast 事件（成功的重试不许弹）：{toasts}"


@pytest.mark.parametrize("branch", ["keep-mine", "take-remote"])
def test_w5_c4_both_resolution_branches_on_the_success_path(
    page: Page, live_server: str, e2e_books_dir: Path, branch: str
) -> None:
    """W5-C4 · S1/S2：解决那一步完全不拦——「保留我的」真落盘并收尾；「采用远端」收尾且一条写都不发。W5-C1/C2/C3 的真路径对照。"""
    run = _w5_open_conflict(page, live_server, e2e_books_dir, _token())
    assert run.conflict.injected_etag is not None, (
        f"[{branch}] 注入的 409 体里 etag 是 null——`if (body?.etag)` 会跳过，本例会因错误的理由变绿"
    )
    pre = read_notes(e2e_books_dir, BOOK_ID)
    base_updated = _updated(page)
    i_click = len(run.wire)

    if branch == "keep-mine":
        page.get_by_test_id("rd-conflict-keep-mine").click()
        wait_for_note_text(e2e_books_dir, BOOK_ID, run.note_id, run.mine, page=page)
        expect(page.get_by_test_id("rd-conflict-dialog")).not_to_be_visible()
        post = read_notes(e2e_books_dir, BOOK_ID)
        assert_bystanders_unchanged(pre, post, changed_ids={run.note_id})
    else:
        with page.expect_response(
            lambda r: r.request.method == "GET" and NOTES_ENDPOINT_MARKER in r.url
        ):
            page.get_by_test_id("rd-conflict-take-remote").click()
        expect(page.get_by_test_id("rd-conflict-dialog")).not_to_be_visible()
        assert run.wire.writes_after(i_click) == [], (
            f"「采用远端」发出了写请求：{run.wire.writes_after(i_click)}"
        )
        assert read_notes(e2e_books_dir, BOOK_ID) == pre, "「采用远端」改动了 notes.json"
        assert page.get_by_test_id("rd-note-editor-input").input_value() == run.theirs, (
            "「采用远端」之后编辑器里不是远端那一版"
        )

    _wait_until(
        page,
        f"() => window.__r3latch.updatedEvents >= {base_updated + 1}",
        f"[{branch}] 收尾派发 reader3:annotations:updated",
    )
    assert _diag_entries(page) == [], f"[{branch}] 成功的解决不该留下任何诊断条目：{_diag_entries(page)}"
    toasts = _latch(page)["toastEvents"]
    assert len(toasts) == 0, f"[{branch}] 成功的解决不该弹 toast：{toasts}"


# ===========================================================================
# Unit: 不发请求的静默出口 — WI-6（＋ 修订 A3）
# ===========================================================================
#
# 律：**`requested: false` ⟺ 这一窗口里 `/api/notes/**` 上零请求；十个已识别的请求前失败
# 守卫各自保有诊断上报。** 正向：W6-C1/C4/C5/C6/C7；反向：W6-C2/C3。
# `createAnnotation` 的出口已经全部闭合（009 #50，019 WI-1）：原先按计划延后、走另一条通道的
# 三个出口——POST 失败（`op:"create"`，带 status）与两道请求前守卫 `create-no-offsets` /
# `create-empty-quote`——都改接到了 `reportNotesWriteFailure`，W6-C8 把全部七个失败出口串起来
# 断「一次调用恰好一条上报」。所以在建标注这条路上，「ring 是空的」就是「没有失败」。
#
# 路由只有一种：`mode="observe"`——只数、`fallback()`，不 fulfill、不 abort。它是观察者
# 不是替身，所以本单元没有集成义务要还（§9）。

from helpers import wait_for_write_activity_settled  # type: ignore[import-not-found]  # noqa: E402

#: 四个计划点名的守卫，按 W6-C1 的触发顺序。op 同时区分「守卫种类」（没选区 / 没书章上下文）
#: 与「入口」（建 / marker 改色 / 类型切换）。
W6_NAMED_GUARD_OPS = (
    "create-no-selection",
    "create-no-context",
    "marker-toggle-no-selection",
    "type-toggle-no-selection",
)
#: 修订 A3 追加的两个 UI 可达出口（W6-C4）。
W6_UI_EXIT_OPS = ("delete-no-ids", "save-empty-text")
#: 修订 A3 追加的两个防御性出口（W6-C5）。
W6_DEFENSIVE_EXIT_OPS = ("conflict-no-pending", "delete-no-context")
#: 009 #50（019 WI-1）改接的两道 `createAnnotation` 请求前守卫（W6-C6 / W6-C7）。命名沿用
#: 兄弟守卫的 `<入口>-<原因>` 惯例（父级裁定 D1）；「指名 create」落在 POST 出口的 `op:"create"` 上。
W6_CREATE_EXIT_OPS = ("create-no-offsets", "create-empty-quote")
#: 十个守卫 op 的登记表。新加一个守卫却复用既有 op，会让它的长度与集合大小对不上。
W6_GUARD_OP_REGISTRY = W6_NAMED_GUARD_OPS + W6_UI_EXIT_OPS + W6_DEFENSIVE_EXIT_OPS + W6_CREATE_EXIT_OPS

#: 把 `Reader3Ctx` 置空、把地址改成非阅读器路径，然后调用一次 `expr`；无论成败都复原。
#: 只 `replaceState` 走不到路径回落：`getReaderContext` 先读 `window.Reader3Ctx`，而它在
#: `reader.html` 里无条件被填上（矩阵 W6-C1 的 Gap 7 修复）。
_WITHOUT_READER_CONTEXT_JS = """async ({ which, probeId }) => {
  const ui = window.Reader3AnnotationUI;
  const pre = {
    hasRange: ui.currentRange !== null && ui.currentRange !== undefined,
    hasContent: ui.contentEl !== null && ui.contentEl !== undefined,
  };
  if (which === "create" && !(pre.hasRange && pre.hasContent)) return { pre, ran: false };
  const saved = window.Reader3Ctx;
  const savedPath = location.pathname + location.search;
  let result = null;
  try {
    window.Reader3Ctx = null;
    history.replaceState({}, "", "/library");
    if (which === "create") {
      await ui.createAnnotation({ type: "marker", color: "yellow" });
    } else {
      result = await ui.deleteAnnotations([probeId]);
    }
  } finally {
    history.replaceState({}, "", savedPath);
    window.Reader3Ctx = saved;
  }
  return {
    pre,
    ran: true,
    result,
    restored: location.pathname + location.search === savedPath && window.Reader3Ctx === saved,
  };
}"""


def _ring_len_at_least(n: int) -> str:
    return f"() => !!window.Reader3NotesDiag && window.Reader3NotesDiag.entries().length >= {n}"


def _toasts_at_least(n: int) -> str:
    return f"() => window.__r3latch.toastEvents.length >= {n}"


def _total(counts: Counter) -> int:
    return sum(counts.values())


def _assert_guard_entry(entry: Dict[str, Any], op: str, where: str) -> None:
    assert entry["op"] == op, f"[{where}] 守卫条目的 op 不对：期望 {op!r}，实际 {entry}"
    assert entry["requested"] is False, f"[{where}] 守卫没发请求，requested 必须是 False：{entry}"
    assert entry["status"] is None, f"[{where}] 没发请求就没有 status，必须是 null：{entry}"
    assert entry["ok"] is False, f"[{where}] 守卫条目的 ok 应当是 False：{entry}"


def test_w6_c1_four_named_guards_record_distinct_ops_with_no_request_and_no_traffic(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W6-C1 · S5：四个点名守卫各触发一次 ⇒ 四条 `requested:false`/`status:null` 条目、op 两两不同、
    路由层零请求、四个 toast 事件（单例、不拦指针）、盘上什么都没有。"""
    # 登记表自检：十个守卫、十个互不相同的 op。W6-C4/C5 的「与其余各个不同」都靠它。
    # 8 → 10（规则 12）：009 #50 把 `create-no-offsets` / `create-empty-quote` 两道守卫接进了
    # 诊断环（父级裁定 D1），登记表因此多两项；判据没有放宽，仍是「长度 == 集合大小 == 字面量」。
    assert len(W6_GUARD_OP_REGISTRY) == len(set(W6_GUARD_OP_REGISTRY)) == 10, (
        f"守卫 op 登记表不是十个互不相同的 op：{W6_GUARD_OP_REGISTRY}"
    )
    _install_page_latch(page)
    state = _route_notes(page, mode="observe")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    before = Counter(state.counts)
    assert _diag_entries(page) == [], f"触发守卫之前 ring 就不是空的：{_diag_entries(page)}"
    base_toasts = len(_latch(page)["toastEvents"])

    # 1. createAnnotation · 没有选区
    page.evaluate(
        """async () => {
          const ui = window.Reader3AnnotationUI;
          ui.currentRange = null;
          await ui.createAnnotation({ type: "marker", color: "yellow" });
        }"""
    )
    _wait_until(page, _ring_len_at_least(1), "[create-no-selection] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 1), "[create-no-selection] 一个 toast 事件")

    # 2. createAnnotation · 没有书/章上下文。`:1245` 挡在 `:1250` 前面，所以必须先恢复一个活选区。
    select_in_frame(frame, CH0_QUOTE)
    got = page.evaluate(_WITHOUT_READER_CONTEXT_JS, {"which": "create", "probeId": None})
    assert got["pre"] == {"hasRange": True, "hasContent": True}, (
        f"[create-no-context] 触发前没有活选区/内容元素——会先撞上 no-selection 守卫，本步不成立：{got}"
    )
    assert got["ran"] and got["restored"], f"[create-no-context] 上下文没有复原：{got}"
    _wait_until(page, _ring_len_at_least(2), "[create-no-context] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 2), "[create-no-context] 一个 toast 事件")

    # 3. toggleMarkerAnnotation · 没有选区（改色入口）
    page.evaluate(
        """async () => {
          const ui = window.Reader3AnnotationUI;
          ui.currentRange = null;
          await ui.toggleMarkerAnnotation("yellow");
        }"""
    )
    _wait_until(page, _ring_len_at_least(3), "[marker-toggle-no-selection] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 3), "[marker-toggle-no-selection] 一个 toast 事件")

    # 4. toggleAnnotation · 没有选区（类型切换入口）
    page.evaluate(
        """async () => {
          const ui = window.Reader3AnnotationUI;
          ui.currentRange = null;
          await ui.toggleAnnotation("wavy");
        }"""
    )
    _wait_until(page, _ring_len_at_least(4), "[type-toggle-no-selection] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 4), "[type-toggle-no-selection] 一个 toast 事件")

    entries = _diag_entries(page) or []
    assert len(entries) == 4, f"四次触发应当恰好四条 ring 条目：{entries}"
    for entry, op in zip(entries, W6_NAMED_GUARD_OPS):
        _assert_guard_entry(entry, op, op)
    ops = [e["op"] for e in entries]
    assert len(set(ops)) == 4, f"四个守卫的 op 不是两两不同：{ops}"
    assert _total(state.counts) - _total(before) == 0, (
        f"守卫触发期间 /api/notes/** 上有请求：before={dict(before)} after={dict(state.counts)}"
        "——`requested: false` 与线上事实矛盾"
    )
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 4, f"四次触发应当恰好四个 toast 事件：{toasts}"
    for t in toasts:
        assert t["pointerEvents"] == "none", f"守卫的 toast 会拦指针：{t}"
        assert t["liveCount"] == 1, f"守卫的 toast 叠起来了：{t}"
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "守卫触发却有东西落盘了"


@pytest.mark.parametrize("exit_op", list(W6_UI_EXIT_OPS))
def test_w6_c4_the_two_ui_reachable_silent_exits_now_report(
    page: Page, live_server: str, e2e_books_dir: Path, exit_op: str
) -> None:
    """W6-C4 · S3：全程经 UI——在没有标注的文字上点删除 / 空正文点保存 ⇒ 一条 `requested:false`
    条目（op 不与其余七个相撞）、零请求、一个 toast、一条应用 console.error、盘上不变、不派发 updated。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    state = _route_notes(page, mode="observe")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    if exit_op == "save-empty-text":
        page.get_by_test_id("rd-anno-note").click()
        expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
        page.get_by_test_id("rd-note-editor-input").fill("   ")  # lint-e2e-selectors: allow —— fill 的实参是输入正文，不是选择器
    before = Counter(state.counts)
    base_toasts = len(_latch(page)["toastEvents"])
    base_app_errors = len(_app_errors(errors))
    base_updated = _updated(page)
    assert _diag_entries(page) == [], f"[{exit_op}] 触发之前 ring 就不是空的：{_diag_entries(page)}"

    if exit_op == "delete-no-ids":
        page.get_by_test_id("rd-anno-delete").click()
    else:
        page.get_by_test_id("rd-note-editor-primary").click()
    _wait_until(page, _ring_len_at_least(1), f"[{exit_op}] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 1), f"[{exit_op}] 一个 toast 事件")

    entries = _diag_entries(page) or []
    assert len(entries) == 1, f"[{exit_op}] 应当恰好一条 ring 条目：{entries}"
    _assert_guard_entry(entries[0], exit_op, exit_op)
    others = [op for op in W6_GUARD_OP_REGISTRY if op != exit_op]
    assert entries[0]["op"] not in others, f"[{exit_op}] op 与另一个守卫的 op 相撞：{entries[0]}"
    assert _total(state.counts) - _total(before) == 0, (
        f"[{exit_op}] 守卫触发期间 /api/notes/** 上有请求：before={dict(before)} after={dict(state.counts)}"
    )
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 1, f"[{exit_op}] 应当恰好一个 toast 事件：{toasts}"
    app_window = _app_errors(errors)[base_app_errors:]
    assert len(app_window) == 1, f"[{exit_op}] 应当恰好一条应用 console.error：{[m.text for m in app_window]}"
    assert DIAG_CONSOLE_RE.match(app_window[0].text), f"[{exit_op}] console 行不合契约：{app_window[0].text!r}"
    assert _updated(page) - base_updated == 0, f"[{exit_op}] 什么都没写却派发了 reader3:annotations:updated"
    assert read_notes(e2e_books_dir, BOOK_ID) == [], f"[{exit_op}] 守卫触发却有东西落盘了"


@pytest.mark.parametrize("exit_op", list(W6_DEFENSIVE_EXIT_OPS))
def test_w6_c5_the_two_defensive_silent_exits_now_report(
    page: Page, live_server: str, e2e_books_dir: Path, exit_op: str
) -> None:
    """W6-C5 · S3：没有待决冲突时调 `resolveConflict(true)` / 没有书章上下文时调
    `deleteAnnotations([probe])` ⇒ 一条 `requested:false` 条目、零请求、一个 toast、盘上不变。"""
    _install_page_latch(page)
    state = _route_notes(page, mode="observe")
    open_ch0(page, live_server, expected_marks=0)
    token = _token()
    probe_id = f"probe-{token}"
    before = Counter(state.counts)
    base_toasts = len(_latch(page)["toastEvents"])
    assert _diag_entries(page) == [], f"[{exit_op}] 触发之前 ring 就不是空的：{_diag_entries(page)}"

    if exit_op == "conflict-no-pending":
        pending = page.evaluate(
            """async () => {
              const ui = window.Reader3AnnotationUI;
              const pending = ui.pendingConflict === null || ui.pendingConflict === undefined;
              if (pending) await ui.resolveConflict(true);
              return pending;
            }"""
        )
        assert pending is True, "[conflict-no-pending] 页面加载后 pendingConflict 不是空的——本步不成立"
    else:
        got = page.evaluate(_WITHOUT_READER_CONTEXT_JS, {"which": "delete", "probeId": probe_id})
        assert got["ran"] and got["restored"], f"[delete-no-context] 上下文没有复原：{got}"
        assert got["result"] == {"ok": False, "failedIds": [probe_id]}, (
            f"[delete-no-context] 没上下文时的删除结果不对（调用方要能看出一条都没删）：{got['result']}"
        )
    _wait_until(page, _ring_len_at_least(1), f"[{exit_op}] 一条守卫条目")
    _wait_until(page, _toasts_at_least(base_toasts + 1), f"[{exit_op}] 一个 toast 事件")

    entries = _diag_entries(page) or []
    assert len(entries) == 1, f"[{exit_op}] 应当恰好一条 ring 条目：{entries}"
    _assert_guard_entry(entries[0], exit_op, exit_op)
    others = [op for op in W6_GUARD_OP_REGISTRY if op != exit_op]
    assert entries[0]["op"] not in others, f"[{exit_op}] op 与另一个守卫的 op 相撞：{entries[0]}"
    if exit_op == "delete-no-context":
        assert entries[0]["id"] == probe_id, f"[delete-no-context] 条目没带上被放弃删除的 id：{entries[0]}"
    assert _total(state.counts) - _total(before) == 0, (
        f"[{exit_op}] 守卫触发期间 /api/notes/** 上有请求：before={dict(before)} after={dict(state.counts)}"
    )
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 1, f"[{exit_op}] 应当恰好一个 toast 事件：{toasts}"
    assert read_notes(e2e_books_dir, BOOK_ID) == [], f"[{exit_op}] 守卫触发却有东西落盘了"


def test_w6_c2_a_valid_create_issues_traffic_and_records_nothing(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W6-C2 · S5：律的反向——有效选区上的建（非默认色）真发了请求、盘上颜色对、零诊断零 toast。
    没有它，「计数器永远是 0」的夹具毛病会让 W6-C1 的 0 什么都不证明。"""
    _install_page_latch(page)
    state = _route_notes(page, mode="observe")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    before = Counter(state.counts)
    base_toasts = len(_latch(page)["toastEvents"])

    page.get_by_test_id("rd-anno-color-green").click()
    # 路由处理函数是 Python 回调：同步 Playwright 只在 Python 调进 Playwright 时才服务它。
    # `wait_for_notes` 是纯 Python 的轮询，不先把这次 POST 的响应等到手，请求会卡在观察路由上。
    try:
        with page.expect_response(
            lambda r: r.request.method == "POST" and NOTES_ENDPOINT_MARKER in r.url
        ):
            page.get_by_test_id("rd-anno-type-marker").click()
    except PlaywrightError as exc:
        raise AssertionError(f"有效选区上的建没有发出 POST（{type(exc).__name__}）") from None
    wait_for_write_activity_settled(page)
    wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    notes = read_notes(e2e_books_dir, BOOK_ID)

    assert _writes(state.counts) - _writes(before) >= 1, (
        f"有效的建没有经过路由层——计数器不是活的，W6-C1 的 0 不成立：{dict(state.counts)}"
    )
    assert len(notes) == 1, f"应当恰好一条落盘：{notes}"
    assert notes[0]["color"] == "green", f"请求的颜色没落盘（默认色冒充了写入值）：{notes[0]}"
    assert notes[0]["quote"] == CH0_QUOTE, f"落盘的 quote 不是选中的文字：{notes[0]}"
    assert _diag_entries(page) == [], f"成功的建不该留下任何诊断条目：{_diag_entries(page)}"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 0, f"成功的建不该弹 toast：{toasts}"


def test_w6_c3_the_recolor_composite_on_the_green_path(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W6-C3 · S1：不装任何路由的真改色（黄 wavy → 绿 wavy）——旧的真删了、新的真建了、零诊断。
    W4-C6 的真路径对照。"""
    token = _token()
    (seeded_id,) = _w4_seed(e2e_books_dir, token, [("wavy", "yellow")])
    _install_page_latch(page)
    errors = _console_errors(page)
    frame = open_ch0(page, live_server, expected_marks=1)

    select_in_frame(frame, CH0_QUOTE)
    base_toasts = len(_latch(page)["toastEvents"])
    base_errors = len(errors)
    base_updated = _updated(page)
    page.get_by_test_id("rd-anno-color-green").click()
    page.get_by_test_id("rd-anno-type-wavy").click()
    _wait_until(
        page,
        f"() => window.__r3latch.updatedEvents >= {base_updated + 1}",
        "成功的改色派发 reader3:annotations:updated",
    )
    after = wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    wait_for_write_activity_settled(page)
    settle_marks(page, frame, 1)
    after = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == 1, f"改色之后盘上应当恰好一条（旧的删了、新的建了）：{after}"
    rec = after[0]
    assert rec["color"] == "green" and rec["type"] == "wavy", f"改色没按请求落盘：{rec}"
    assert rec["quote"] == CH0_QUOTE, f"改色后的 quote 不对：{rec}"
    assert rec["id"] != seeded_id, f"盘上那条还是旧 id {seeded_id!r}——不是先删后建"
    assert seeded_id not in {r["id"] for r in after}, "旧的那条还在盘上"
    assert mark_id_union(scan_marks(frame)) == {rec["id"]}, "屏幕上的 mark 不是新建的那一条"
    assert _diag_entries(page) == [], f"成功的改色不该留下任何诊断条目：{_diag_entries(page)}"
    toasts = _latch(page)["toastEvents"][base_toasts:]
    assert len(toasts) == 0, f"成功的改色不该弹 toast：{toasts}"
    window = errors[base_errors:]
    assert len(window) == 0, f"成功的改色不该有 console.error：{[m.text for m in window]}"


# ===========================================================================
# Unit: createAnnotation 的失败出口全部走 reportNotesWriteFailure — 009 #50（019 WI-1）
# ===========================================================================
#
# 律（报告数守恒）：**一次失败的 `createAnnotation` 调用恰好产出一条 ring 条目、一个 toast
# 事件、一条 `[Annotations] notes write failed {json}` 行、零条遗留 `createAnnotation:` 行**；
# 不派发 `reader3:annotations:updated`，盘上什么都没有。`requested:false` ⟺ 这次调用在
# `/api/notes` 上零请求。成功的调用零条目、零 toast（W6-C2 与 W6-C8 的最后一步）。
#
# 两道请求前守卫靠**公开面**`window.Reader3AnnotationUI` 注入 `currentRange` / `currentOffsets`
# 触发（与 W6-C1 同一手法），驱动的是真的 `createAnnotation`，不是它的复刻。

#: 一次真的 `createAnnotation`（marker 黄）。
_CREATE_JS = """async () => {
  await window.Reader3AnnotationUI.createAnnotation({ type: "marker", color: "yellow" });
}"""

#: 一个不在正文文本索引里的游离 Range：`rangeAnchoredIn` 为假、`offsetFromNode` 取不到偏移。
#: `snapshot` 为 null 时不留快照；给了就原样作 `currentOffsets`。
_DETACHED_RANGE_CREATE_JS = """async ({ snapshot }) => {
  const ui = window.Reader3AnnotationUI;
  const d = ui.contentEl.ownerDocument;
  const t = d.createTextNode("x");
  const r = d.createRange();
  r.setStart(t, 0);
  r.setEnd(t, 1);
  ui.currentRange = r;
  ui.currentOffsets = snapshot;
  await ui.createAnnotation({ type: "marker", color: "yellow" });
}"""

#: 019 WI-8：同上，但在调用**之前**量出正文文本索引的长度 `L` 与 `Reader3Ctx.chapterIndex`，
#: 给 `create-no-offsets` 的 `detail` 当期望值。`L` 是测试自有的计算：同一个拒收过滤器
#: （`buildTextIndex` 的那一个——偏移轴就是它定义的），产品过滤器一改这里就得跟着改。
_DETACHED_RANGE_CREATE_MEASURED_JS = """async ({ snapshot }) => {
  const ui = window.Reader3AnnotationUI;
  const d = ui.contentEl.ownerDocument;
  const w = d.createTreeWalker(ui.contentEl, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (parent.closest("script, style, #annotation-toolbar, #note-editor, #note-tooltip")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let L = 0;
  while (w.nextNode()) L += w.currentNode.nodeValue.length;
  const ctxChapter = window.Reader3Ctx ? window.Reader3Ctx.chapterIndex : null;
  const t = d.createTextNode("x");
  const r = d.createRange();
  r.setStart(t, 0);
  r.setEnd(t, 1);
  ui.currentRange = r;
  ui.currentOffsets = snapshot;
  await ui.createAnnotation({ type: "marker", color: "yellow" });
  return { L, ctxChapter };
}"""

#: 019 WI-8：ring 条目的**确切**键序（`recordNotesDiag` 的字面顺序）。`ENTRY_KEYS` 只是「至少带」，
#: 多一个键它看不见——而 `detail` 恰恰必须只进 console、不进 ring。
RING_KEY_ORDER = ["op", "requested", "status", "ok", "id", "t"]
#: console 负载的确切键序；只有 `create-no-offsets` 在末尾多一个 `detail`。
PAYLOAD_KEY_ORDER = RING_KEY_ORDER + ["message"]


def _diag_payloads_since(errors: List[ConsoleMessage], base: Dict[str, int]) -> List[Dict[str, Any]]:
    """基线之后每条 `notes write failed` 行解析出的 JSON 负载（dict 保留 JSON 里的键序）。"""
    window = _app_errors(errors[base["errors"]:])
    return [
        json.loads(m.group(1))
        for m in (DIAG_CONSOLE_RE.match(x.text) for x in window)
        if m
    ]

#: 把活选区塌成一个点（修订 A4：先断 `hasRange` 前置条件，再 `cloneRange()`）。
_COLLAPSED_RANGE_CREATE_JS = """async () => {
  const ui = window.Reader3AnnotationUI;
  const pre = { hasRange: ui.currentRange !== null && ui.currentRange !== undefined };
  if (!pre.hasRange) return { pre, ran: false };
  const r = ui.currentRange.cloneRange();
  r.collapse(true);
  ui.currentRange = r;
  ui.currentOffsets = null;
  await ui.createAnnotation({ type: "marker", color: "yellow" });
  return { pre, ran: true };
}"""

#: 游离 Range ＋ 一张可用但为空的快照（修订 A4：chapterIndex 取自 `window.Reader3Ctx`，
#: 与 `getReaderContext()` 同源；不是数就不调用）。
_COLLAPSED_SNAPSHOT_CREATE_JS = """async () => {
  const ui = window.Reader3AnnotationUI;
  const chapterIndex = window.Reader3Ctx ? window.Reader3Ctx.chapterIndex : undefined;
  if (typeof chapterIndex !== "number") return { chapterIndex: String(chapterIndex), ran: false };
  const d = ui.contentEl.ownerDocument;
  const t = d.createTextNode("x");
  const r = d.createRange();
  r.setStart(t, 0);
  r.setEnd(t, 1);
  ui.currentRange = r;
  ui.currentOffsets = { chapterIndex, start: 3, end: 3 };
  await ui.createAnnotation({ type: "marker", color: "yellow" });
  return { chapterIndex, ran: true };
}"""


def _create_baseline(page: Page, errors: List[ConsoleMessage], where: str) -> Dict[str, int]:
    assert _diag_entries(page) == [], f"[{where}] 触发之前 ring 就不是空的：{_diag_entries(page)}"
    return {
        "toasts": len(_latch(page)["toastEvents"]),
        "errors": len(errors),
        "updated": _updated(page),
    }


def _assert_single_create_report(
    page: Page,
    errors: List[ConsoleMessage],
    base: Dict[str, int],
    *,
    where: str,
    op: str,
    requested: bool,
    status: Optional[int],
    toast_text: str,
) -> Dict[str, Any]:
    """一次失败的 `createAnnotation` ⇒ 恰好一条条目 / 一个 toast / 一条诊断行 / 零条遗留行 / 不派发 updated。

    ring 在 toast 之前同步写入（`reportNotesWriteFailure` 先 record 再 showToast），所以等到
    toast 之后直接读 ring 就是确定的终态，不再额外等待。
    """
    _wait_until(page, _toasts_at_least(base["toasts"] + 1), f"[{where}] 一个 toast 事件")

    entries = _diag_entries(page) or []
    assert len(entries) == 1, f"[{where}] 一次失败的建应当恰好一条 ring 条目：{entries}"
    entry = entries[0]
    assert set(entry) >= set(ENTRY_KEYS), f"[{where}] ring 条目缺字段：{sorted(set(ENTRY_KEYS) - set(entry))}"
    assert entry["op"] == op, f"[{where}] op 不对：期望 {op!r}，实际 {entry}"
    assert entry["requested"] is requested, f"[{where}] requested 应当是 {requested}：{entry}"
    if status is None:
        assert entry["status"] is None, f"[{where}] 没有响应时 status 必须是 null：{entry}"
    else:
        assert entry["status"] == status, f"[{where}] status 应当是 {status}：{entry}"
    assert entry["ok"] is False, f"[{where}] 失败条目的 ok 应当是 False：{entry}"
    assert entry["id"] is None, f"[{where}] 建标注没有 id 可带：{entry}"

    toasts = _latch(page)["toastEvents"][base["toasts"]:]
    assert len(toasts) == 1, f"[{where}] 应当恰好一个 toast 事件：{toasts}"
    assert toasts[0]["text"] == toast_text, f"[{where}] toast 文案不对：{toasts[0]['text']!r}"
    assert toasts[0]["pointerEvents"] == "none", f"[{where}] toast 会拦指针：{toasts[0]}"
    assert toasts[0]["liveCount"] == 1, f"[{where}] toast 叠起来了：{toasts[0]}"

    window = _app_errors(errors[base["errors"]:])
    legacy = [m for m in window if m.text.startswith(LEGACY_CREATE_CONSOLE_PREFIX)]
    assert legacy == [], f"[{where}] 还有遗留 createAnnotation console 行：{[m.text for m in legacy]}"
    diag = [m for m in window if DIAG_CONSOLE_RE.match(m.text)]
    assert len(diag) == 1, f"[{where}] 应当恰好一条 notes write failed 行：{[m.text for m in window]}"
    payload = json.loads(DIAG_CONSOLE_RE.match(diag[0].text).group(1))  # type: ignore[union-attr]
    assert {k: payload[k] for k in ENTRY_KEYS} == {k: entry[k] for k in ENTRY_KEYS}, (
        f"[{where}] console 负载与 ring 条目不一致：\n  console {payload}\n  ring    {entry}"
    )
    assert payload["message"] == toast_text, f"[{where}] console 负载的 message 不是 toast 文案：{payload}"

    assert _updated(page) - base["updated"] == 0, f"[{where}] 失败的建却派发了 reader3:annotations:updated"
    return entry


def test_w1_c11_create_post_500_produces_exactly_one_attributable_entry(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W1-C11 · S1：建标注的 POST 被 fulfill(500) ⇒ 一条 `op:"create"`/`status:500`/`requested:true`
    条目、toast 全等 `标注没能保存（500），请重试`、一条诊断行、零遗留行、一次 POST、盘上为空。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    state = _route_notes(page, mode="fulfill500", method="POST")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    base = _create_baseline(page, errors, "create-500")

    page.evaluate(_CREATE_JS)
    _assert_single_create_report(
        page, errors, base,
        where="create-500", op="create", requested=True, status=500, toast_text=CREATE_REJECTED_TOAST_500,
    )
    assert state.counts["POST"] == 1 and _writes(state.counts) == 1, (
        f"一次调用应当恰好一次 POST：{dict(state.counts)}"
    )
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "500 没有真的注入上：有东西落盘了"


def test_w1_c12_create_post_aborted_gives_status_null_and_the_generic_toast(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W1-C12 · S3：POST 被 abort（`resp === null`）⇒ `status:null` 但 `requested:true`（发出去了、
    没回来），toast 全等 `标注没能保存，请重试`（不带括号）。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    state = _route_notes(page, mode="abort", method="POST")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    base = _create_baseline(page, errors, "create-abort")

    page.evaluate(_CREATE_JS)
    _assert_single_create_report(
        page, errors, base,
        where="create-abort", op="create", requested=True, status=None, toast_text=CREATE_NO_RESPONSE_TOAST,
    )
    assert state.counts["POST"] == 1, f"一次调用应当恰好一次 POST：{dict(state.counts)}"
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "abort 没有真的注入上：有东西落盘了"


def test_w1_c13_409_then_409_after_resync_two_requests_one_report(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W1-C13 · S3：每次 POST 都回 409 ⇒ 线上两次 POST（原请求 ＋ 一次重同步重试），报告只有一条
    `status:409`。请求数与报告数分开断，咬的是「每次 fetch 报一次」。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    wire = _install_wire_log(page)
    state = _route_notes(page, mode="conflict", method="POST", wire_log=wire)
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    base = _create_baseline(page, errors, "create-409")

    page.evaluate(_CREATE_JS)
    wait_for_write_activity_settled(page)
    _assert_single_create_report(
        page, errors, base,
        where="create-409", op="create", requested=True, status=409, toast_text=CREATE_REJECTED_TOAST_409,
    )
    assert _writes(state.counts) == 2 and state.counts["POST"] == 2, (
        f"409 → 重同步 → 409 应当恰好两次 POST：{dict(state.counts)}"
    )
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "409 没有真的注入上：有东西落盘了"


def _assert_guard_create_report(
    page: Page,
    errors: List[ConsoleMessage],
    state: SimpleNamespace,
    before: Counter,
    base: Dict[str, int],
    e2e_books_dir: Path,
    *,
    op: str,
    where: str,
    toast_text: str,
) -> None:
    entry = _assert_single_create_report(
        page, errors, base, where=where, op=op, requested=False, status=None, toast_text=toast_text,
    )
    _assert_guard_entry(entry, op, where)
    others = [o for o in W6_GUARD_OP_REGISTRY if o != op]
    assert entry["op"] not in others, f"[{where}] op 与另一个守卫的 op 相撞：{entry}"
    assert _total(state.counts) - _total(before) == 0, (
        f"[{where}] 守卫触发期间 /api/notes/** 上有请求：before={dict(before)} after={dict(state.counts)}"
        "——`requested: false` 与线上事实矛盾"
    )
    assert read_notes(e2e_books_dir, BOOK_ID) == [], f"[{where}] 守卫触发却有东西落盘了"


@pytest.mark.parametrize("route_in", ["detached_range", "wrong_chapter_snapshot"])
def test_w6_c6_create_no_offsets_guard_reports_requested_false_and_sends_nothing(
    page: Page, live_server: str, e2e_books_dir: Path, route_in: str
) -> None:
    """W6-C6 · S3：`resolveOffsets` 取不到偏移的两条路（游离 Range 无快照 / 快照章号不符）⇒
    一条 `create-no-offsets` 守卫条目、零请求、toast 全等 `这段选区已失效，请重新选中再试`。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    state = _route_notes(page, mode="observe")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    before = Counter(state.counts)
    base = _create_baseline(page, errors, route_in)

    snapshot = None if route_in == "detached_range" else {"chapterIndex": 99, "start": 0, "end": 5}
    got = page.evaluate(_DETACHED_RANGE_CREATE_MEASURED_JS, {"snapshot": snapshot})
    _assert_guard_create_report(
        page, errors, state, before, base, e2e_books_dir,
        op="create-no-offsets", where=route_in, toast_text=CREATE_NO_OFFSETS_TOAST,
    )

    # 019 WI-8（WI8-E1）：「没有快照」与「快照来自别的章」必须在上报里分得开。
    # `hasSnapshot` 读的是**原始** `currentOffsets`——读 `offsetsUsable` 之后的值，章号不符
    # 那一路也会报 false，两种状态又糊成一种。
    assert got["ctxChapter"] == 0, f"[{route_in}] 前提：Reader3Ctx.chapterIndex 应当是 0：{got}"
    L = got["L"]
    assert isinstance(L, int) and L > len(CH0_QUOTE), f"[{route_in}] 前提：正文文本索引长度不对：{got}"
    entries = _diag_entries(page) or []
    assert len(entries) == 1, entries
    assert list(entries[0]) == RING_KEY_ORDER, (
        f"[{route_in}] ring 条目的键序必须恰好是 {RING_KEY_ORDER}：{list(entries[0])}"
    )
    assert "detail" not in entries[0], f"[{route_in}] detail 进了 ring：{entries[0]}"
    payloads = _diag_payloads_since(errors, base)
    assert len(payloads) == 1, payloads
    payload = payloads[0]
    assert "detail" in payload, (
        f"[{route_in}] create-no-offsets 的 console 负载没带 detail——分不清没快照还是快照章号不符：{payload}"
    )
    assert list(payload) == PAYLOAD_KEY_ORDER + ["detail"], f"[{route_in}] 负载键序不对：{list(payload)}"
    detail = payload["detail"]
    # 显式断键在：JSON 会把 undefined 直接丢掉，不能让「缺键」冒充 null。
    assert "snapshotChapter" in detail, f"[{route_in}] detail 缺 snapshotChapter：{detail}"
    if route_in == "detached_range":
        want = {"hasSnapshot": False, "snapshotChapter": None, "chapterIndex": 0, "textLength": L}
    else:
        want = {"hasSnapshot": True, "snapshotChapter": 99, "chapterIndex": 0, "textLength": L}
    assert detail == want, f"[{route_in}] detail 不对：\n  实际 {detail}\n  期望 {want}"


@pytest.mark.parametrize("route_in", ["collapsed_range", "collapsed_snapshot"])
def test_w6_c7_create_empty_quote_guard_reports_requested_false_and_sends_nothing(
    page: Page, live_server: str, e2e_books_dir: Path, route_in: str
) -> None:
    """W6-C7 · S3：`start === end` 的两条路（活选区塌成点 / 可用但为空的快照）⇒ 一条
    `create-empty-quote` 守卫条目、零请求、toast 全等 `没取到选中的文字，请重新选中再试`。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    state = _route_notes(page, mode="observe")
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    before = Counter(state.counts)
    base = _create_baseline(page, errors, route_in)

    if route_in == "collapsed_range":
        got = page.evaluate(_COLLAPSED_RANGE_CREATE_JS)
        assert got["pre"] == {"hasRange": True}, f"[{route_in}] 触发前没有活选区——本步不成立：{got}"
    else:
        got = page.evaluate(_COLLAPSED_SNAPSHOT_CREATE_JS)
        assert got["ran"] and isinstance(got["chapterIndex"], int), (
            f"[{route_in}] window.Reader3Ctx.chapterIndex 不是数——快照无从对上章号，本步不成立：{got}"
        )
    _assert_guard_create_report(
        page, errors, state, before, base, e2e_books_dir,
        op="create-empty-quote", where=route_in, toast_text=CREATE_EMPTY_QUOTE_TOAST,
    )


def test_w6_c8_every_create_exit_in_sequence_yields_exactly_one_report_each_in_order(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W6-C8 · S4：`createAnnotation` 的七个失败出口在同一页里依次各触发一次，最后一次有效的建 ⇒
    报告流与调用流一一对应：三个投影（op / requested / status）逐位相等、七个 toast、七条诊断行、
    零遗留行、线上 POST 1+1+2+1 = 5、成功一步不加条目、盘上恰好一条。"""
    _install_page_latch(page)
    errors = _console_errors(page)
    wire = _install_wire_log(page)
    _route_notes(page, mode="observe")
    post_mode = {"mode": "pass"}

    def _switch(route: Route) -> None:
        # 后注册的路由先被调用：非目标一律 fallback 给 observe（再落到冻结的出网闸）。
        mode = post_mode["mode"]
        if route.request.method != "POST" or mode == "pass":
            route.fallback()
        elif mode == "fulfill500":
            route.fulfill(status=500, content_type="application/json", body='{"detail":"injected"}')
        elif mode == "abort":
            route.abort()
        elif mode == "conflict":
            etag = wire.last_2xx_etag_before(len(wire))
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"etag": etag, "annotation": None}))
        else:  # pragma: no cover - 用例写错了 mode
            route.fallback()
            raise AssertionError(f"未知 post_mode {mode!r}")

    page.route("**/api/notes/**", _switch)
    frame = open_ch0(page, live_server, expected_marks=0)
    base = _create_baseline(page, errors, "w6-c8")

    def _post_count() -> int:
        return sum(1 for e in wire.entries if e[0] == "req" and e[1] == "POST")

    base_posts = _post_count()

    def _fire_500() -> None:
        post_mode["mode"] = "fulfill500"
        select_in_frame(frame, CH0_QUOTE)
        page.evaluate(_CREATE_JS)

    def _fire_no_offsets() -> None:
        select_in_frame(frame, CH0_QUOTE)
        page.evaluate(_DETACHED_RANGE_CREATE_JS, {"snapshot": None})

    def _fire_abort() -> None:
        post_mode["mode"] = "abort"
        select_in_frame(frame, CH0_QUOTE)
        page.evaluate(_CREATE_JS)

    def _fire_empty_quote() -> None:
        select_in_frame(frame, CH0_QUOTE)
        got = page.evaluate(_COLLAPSED_RANGE_CREATE_JS)
        assert got["pre"] == {"hasRange": True}, f"[empty-quote] 触发前没有活选区：{got}"

    def _fire_409() -> None:
        post_mode["mode"] = "conflict"
        select_in_frame(frame, CH0_QUOTE)
        page.evaluate(_CREATE_JS)
        wait_for_write_activity_settled(page)

    def _fire_no_selection() -> None:
        page.evaluate(
            """async () => {
              const ui = window.Reader3AnnotationUI;
              ui.currentRange = null;
              await ui.createAnnotation({ type: "marker", color: "yellow" });
            }"""
        )

    def _fire_no_context() -> None:
        select_in_frame(frame, CH0_QUOTE)
        got = page.evaluate(_WITHOUT_READER_CONTEXT_JS, {"which": "create", "probeId": None})
        assert got["pre"] == {"hasRange": True, "hasContent": True}, f"[no-context] 触发前没有活选区：{got}"
        assert got["ran"] and got["restored"], f"[no-context] 上下文没有复原：{got}"

    steps: List[tuple] = [
        ("500", _fire_500),
        ("no-offsets", _fire_no_offsets),
        ("abort", _fire_abort),
        ("empty-quote", _fire_empty_quote),
        ("409", _fire_409),
        ("no-selection", _fire_no_selection),
        ("no-context", _fire_no_context),
    ]
    for i, (name, fire) in enumerate(steps, start=1):
        fire()
        _wait_until(page, _toasts_at_least(base["toasts"] + i), f"[{name}] 第 {i} 个 toast 事件")
        got_len = len(_diag_entries(page) or [])
        assert got_len == i, f"[{name}] 第 {i} 步之后 ring 应当恰好 {i} 条，实际 {got_len} 条"

    # 最后一次有效的建：路由放行，真的落盘。
    post_mode["mode"] = "pass"
    select_in_frame(frame, CH0_QUOTE)
    try:
        with page.expect_response(
            lambda r: r.request.method == "POST" and NOTES_ENDPOINT_MARKER in r.url
        ):
            page.evaluate(_CREATE_JS)
    except PlaywrightError as exc:
        raise AssertionError(f"有效的建没有发出 POST（{type(exc).__name__}）") from None
    wait_for_write_activity_settled(page)
    notes = wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)

    entries = _diag_entries(page) or []
    assert [e["op"] for e in entries] == [
        "create", "create-no-offsets", "create", "create-empty-quote",
        "create", "create-no-selection", "create-no-context",
    ], f"报告流的 op 序列不对：{[e['op'] for e in entries]}"
    assert [e["requested"] for e in entries] == [True, False, True, False, True, False, False], (
        f"报告流的 requested 序列不对：{[e['requested'] for e in entries]}"
    )
    assert [e["status"] for e in entries] == [500, None, None, None, 409, None, None], (
        f"报告流的 status 序列不对：{[e['status'] for e in entries]}"
    )
    assert all(e["ok"] is False for e in entries), f"有失败条目的 ok 不是 False：{entries}"

    toasts = _latch(page)["toastEvents"][base["toasts"]:]
    assert len(toasts) == 7, f"七次失败 ＋ 一次成功应当恰好七个 toast 事件：{[t['text'] for t in toasts]}"

    window = _app_errors(errors[base["errors"]:])
    legacy = [m for m in window if m.text.startswith(LEGACY_CREATE_CONSOLE_PREFIX)]
    assert legacy == [], f"还有遗留 createAnnotation console 行：{[m.text for m in legacy]}"
    diag = [m for m in window if DIAG_CONSOLE_RE.match(m.text)]
    assert len(diag) == 7, f"应当恰好七条 notes write failed 行：{[m.text for m in window]}"
    payloads = [json.loads(DIAG_CONSOLE_RE.match(m.text).group(1)) for m in diag]  # type: ignore[union-attr]
    assert [{k: p[k] for k in ENTRY_KEYS} for p in payloads] == [{k: e[k] for k in ENTRY_KEYS} for e in entries], (
        f"console 负载与 ring 条目逐位不一致：\n  console {payloads}\n  ring    {entries}"
    )
    for p, t in zip(payloads, toasts):
        assert p["message"] == t["text"], f"console 负载的 message 与同次 toast 文案不一致：{p} / {t['text']!r}"

    assert _post_count() - base_posts == 5, (
        f"线上 POST 应当恰好 1(500)+1(abort)+2(409 重试)+1(成功) = 5 次，实际 {_post_count() - base_posts} 次"
    )
    assert len(notes) == 1 and notes[0]["quote"] == CH0_QUOTE, f"有效的建应当恰好落盘一条选中的文字：{notes}"

    # 019 WI-8（WI8-E3）：七个出口里只有 create-no-offsets 带 detail，且放在 message 之后；
    # 每条 ring 条目恰好六个键、顺序固定——这是「其余 op 的负载字节不变」的护栏
    # （值由上面的投影相等钉住，这里钉键集与键序）。
    for p, e in zip(payloads, entries):
        assert list(e) == RING_KEY_ORDER, f"ring 条目键序不对：{list(e)}（{e}）"
        extra = ["detail"] if p["op"] == "create-no-offsets" else []
        assert list(p) == PAYLOAD_KEY_ORDER + extra, f"{p['op']} 的 console 负载键序不对：{list(p)}"
    no_offsets = [p for p in payloads if p["op"] == "create-no-offsets"]
    assert len(no_offsets) == 1, no_offsets
    d = no_offsets[0]["detail"]
    assert d["hasSnapshot"] is False and d["snapshotChapter"] is None and d["chapterIndex"] == 0, (
        f"W6-C8 的 no-offsets 一步不留快照，detail 应当如实说出来：{d}"
    )


# ===========================================================================
# Unit: 成功路径护栏 create → edit → delete，不装任何路由 — WI-7
# ===========================================================================
#
# 律：**往返，且成功即静默。** 建 → 改 → 删让 `notes.json` 回到流程之前的样子；绿路径什么都
# 不发：零条 `ok:false` / `requested:false` 的 ring 条目、零个 toast 事件、零条 `console.error`，
# 在**每一个**观测点上都是。后半句本身就是一条律——它咬的是一个过于积极的 WI-3..WI-6 实现在
# 实际成功了的路径上也去上报。
#
# **不装任何 `page.route`。** 冻结 conftest 的 context 级出网闸是一个 Python 处理函数，
# 同步 Playwright 只在 Python 调进 Playwright 时才服务它，所以每一次触发写的点击都包在
# `page.expect_response(...)` 里，再 `wait_for_write_activity_settled`，最后才进
# `wait_for_notes(..., page=page)` 轮询（009 #49 起它用 `page.wait_for_timeout` 泵事件，
# 不再是纯 Python 的 `time.sleep`）。本用例不自带任何 sleep（W7-C1 的约束）。
#
# **旁观条放在第 1 章**（矩阵原文 `pre` 期望 `[]`，这里偏离一处并写明理由）：
# `assert_bystanders_unchanged` 在零条旁观时**按设计直接抛**（空转就是它要防的事），所以
# 矩阵要求的那次调用在一条单记录的流程里不可满足。旁观条放在第 1 章：第 0 章的流程与 `<mark>`
# 计数完全不受影响，「第 0 章恰好一条」仍按等号断；而整本书的 `notes.json` 是整份回写的，
# 建/改/删任何一步把别章的条目漏带回去，都在旁观条上当场显形——这比 `pre == []` 多守一件事。
# 「编辑的那条除 `note_text` 外逐字段原样」这一半由本用例自己按整字典等值断，因为旁观条
# helper 从不比较被改的那一条。

from helpers import (  # type: ignore[import-not-found]  # noqa: E402
    CH1_QUOTE,
    assert_roundtrip,
    reader_frame,
)

W7_BYSTANDER_CHAPTER = 1


def _w7_is_harness_egress_block(msg: ConsoleMessage, live_server: str) -> bool:
    """冻结 conftest 的出网闸把一切非本机请求 `abort` 掉（`reader.html` 头里的 Google Fonts），
    Chromium 于是每次文档加载都记两条 `Failed to load resource: net::ERR_FAILED`，其
    `location.url` 是那个**外部**资源。那是测试夹具的出网策略，不是写路径的输出；只剔它们。
    本机来源的任何 console.error——包括本机资源的非 2xx——照数不误。"""
    url = str((msg.location or {}).get("url") or "")
    return msg.text.startswith(BROWSER_RESOURCE_ERROR_PREFIX) and not url.startswith(live_server)


def _w7_observe(
    page: Page, errors: List[ConsoleMessage], live_server: str, where: str
) -> Dict[str, Any]:
    """一个观测点：toast 事件、ring 条目、console.error 三者都必须为零。返回本次读到的闩。

    闩与 `Reader3NotesDiag` 都随文档生灭（`add_init_script` 在每次导航时重装闩，ring 随
    `annotations.js` 重新求值），所以**刷新之前**必须先读一次——这正是矩阵要求逐步观测的原因。
    console 监听挂在 `Page` 上、跨刷新存活，从挂上起**全程**计数；唯一剔除的是出网闸造成的
    外部资源加载失败（见 `_w7_is_harness_egress_block`），剔掉的条数随失败消息一起报出。
    """
    latch = _latch(page)
    toasts = latch["toastEvents"]
    assert len(toasts) == 0, f"[{where}] 成功路径上不该有任何 toast 事件：{toasts}"
    entries = _diag_entries(page)
    assert entries is not None, f"[{where}] window.Reader3NotesDiag 不在——「零条失败」会是空转"
    bad = [e for e in entries if e.get("ok") is False or e.get("requested") is False]
    assert bad == [], f"[{where}] 成功路径上出现了失败诊断条目：{bad}"
    assert entries == [], f"[{where}] 成功路径不该往诊断环里写任何东西：{entries}"
    ours = [m for m in errors if not _w7_is_harness_egress_block(m, live_server)]
    assert len(ours) == 0, (
        f"[{where}] 成功路径上不该有 console.error："
        f"{[(m.text, (m.location or {}).get('url')) for m in ours]}"
        f"（另剔除出网闸造成的外部资源失败 {len(errors) - len(ours)} 条）"
    )
    return latch


def _w7_click_expecting(page: Page, testid: str, method: str, what: str) -> None:
    """点一下，并在同一次 Playwright 调用里等到那次写的响应——让 context 级出网闸的 Python
    处理函数有机会被服务。等不到就是「这次写根本没发出去」，以断言失败报出来。"""
    try:
        with page.expect_response(
            lambda r: r.request.method == method and NOTES_ENDPOINT_MARKER in r.url
        ) as info:
            page.get_by_test_id(testid).click()
    except PlaywrightError as exc:
        raise AssertionError(f"{what}没有发出 {method}（{type(exc).__name__}）") from None
    resp = info.value
    assert 200 <= resp.status < 300, f"{what}的 {method} 没有成功：HTTP {resp.status}"


def test_w7_c1_create_edit_delete_round_trip_is_exact_and_silent(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W7-C1 · S5 ＋ S4：不装任何路由的 建 → 改 → 删。每一步之后盘面按整字典等值、零 toast、
    零失败条目、零 console.error；最后 `notes.json` 回到流程之前。矩阵里每一条被路由的用例的
    总真路径对照（§9）。"""
    token = _token()
    bystander_id = f"w7-bystander-{token}"
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": bystander_id,
                "chapter_index": W7_BYSTANDER_CHAPTER,
                "type": "marker",
                "color": "blue",
                "quote": CH1_QUOTE,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )
    pre = read_notes(e2e_books_dir, BOOK_ID)
    assert [r["id"] for r in pre] == [bystander_id], f"预置没落对（隔离 fixture 没生效？）：{pre}"

    _install_page_latch(page)
    errors = _console_errors(page)
    updated_total = 0

    # --- 第 1 步：建一条笔记 -------------------------------------------------
    frame = open_ch0(page, live_server, expected_marks=0)
    _w7_observe(page, errors, live_server, "打开第 0 章之后")
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-note").click()
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    body1 = f"body-{token}"
    page.get_by_test_id("rd-note-editor-input").fill(body1)
    _w7_click_expecting(page, "rd-note-editor-primary", "POST", "新建笔记")
    wait_for_write_activity_settled(page)
    after_create = wait_for_notes(e2e_books_dir, BOOK_ID, 2, page=page)
    settle_marks(page, frame, 1)
    expect(page.get_by_test_id("rd-note-editor")).not_to_be_visible()

    created = [r for r in after_create if r["id"] != bystander_id]
    assert len(created) == 1, f"建之后第 0 章应当恰好多出一条：{after_create}"
    rec = created[0]
    note_id = str(rec["id"])
    assert rec["chapter_index"] == CH0_INDEX, f"新建那条落错了章：{rec}"
    assert rec["quote"] == CH0_QUOTE, f"新建那条的 quote 不是选中的文字：{rec}"
    assert rec["type"] == "note", f"Add Note 落成了别的类型：{rec}"
    assert rec["note_text"] == body1, f"新建那条的正文不是填进编辑器的那段：{rec}"
    expected_position = scan_marks(frame)["text"].index(CH0_QUOTE)
    assert rec["position"] == expected_position, (
        f"position 是 {rec['position']!r}，不是 CH0_QUOTE 在章文本里的偏移 {expected_position}"
    )
    assert_bystanders_unchanged(pre, after_create, changed_ids={note_id})
    assert mark_id_union(scan_marks(frame)) == {note_id}, "屏幕上的 mark 不是新建的那一条"
    latch = _w7_observe(page, errors, live_server, "建之后")
    updated_total += latch["updatedEvents"]

    # 刷新往返（冻结 helper，不重写）：刷新后高亮回到同一段文字上、终态仍是恰好 2 条。
    # 它会 reload——闩与 ring 随旧文档一起没了，所以上面那次观测必须在这之前。
    assert_roundtrip(
        page, e2e_books_dir, BOOK_ID, CH0_QUOTE, CH0_ANCHOR, expected_type="note", expected_count=2
    )
    frame = reader_frame(page, CH0_ANCHOR)
    settle_marks(page, frame, 1)
    assert read_notes(e2e_books_dir, BOOK_ID) == after_create, "刷新往返改动了 notes.json"
    _w7_observe(page, errors, live_server, "刷新往返之后")

    # --- 第 2 步：改正文 -----------------------------------------------------
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CH0_QUOTE)
    mark.click()
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    # 带着旧正文打开才说明走的是编辑分支（`openNoteEditorWithExisting`），而不是再建一条。
    expect(page.get_by_test_id("rd-note-editor-input")).to_have_value(body1)
    body2 = f"body2-{token}"
    page.get_by_test_id("rd-note-editor-input").fill(body2)
    _w7_click_expecting(page, "rd-note-editor-primary", "PUT", "编辑笔记")
    wait_for_write_activity_settled(page)
    edited = wait_for_note_text(e2e_books_dir, BOOK_ID, note_id, body2, page=page)
    expect(page.get_by_test_id("rd-note-editor")).not_to_be_visible()
    after_edit = read_notes(e2e_books_dir, BOOK_ID)

    assert edited["id"] == note_id
    by_id_create = {str(r["id"]): r for r in after_create}
    by_id_edit = {str(r["id"]): r for r in after_edit}
    assert set(by_id_edit) == set(by_id_create), f"编辑改变了条目集合：{after_edit}"
    assert by_id_edit[note_id] == {**by_id_create[note_id], "note_text": body2}, (
        "编辑除了 note_text 还动了别的字段（或被实现成了删了重建）：\n"
        f"  编辑前：{by_id_create[note_id]}\n  编辑后：{by_id_edit[note_id]}"
    )
    assert_bystanders_unchanged(after_create, after_edit, changed_ids={note_id})
    latch = _w7_observe(page, errors, live_server, "改之后")
    updated_total_after_edit = latch["updatedEvents"]

    # --- 第 3 步：删 ---------------------------------------------------------
    select_in_frame(frame, CH0_QUOTE)
    _w7_click_expecting(page, "rd-anno-delete", "DELETE", "删除标注")
    wait_for_write_activity_settled(page)
    wait_for_notes(e2e_books_dir, BOOK_ID, 1, page=page)
    settle_marks(page, frame, 0)
    latch = _w7_observe(page, errors, live_server, "删之后")
    updated_total += latch["updatedEvents"]
    assert latch["updatedEvents"] >= updated_total_after_edit + 1, (
        f"成功的删除没有派发 reader3:annotations:updated：改之后 {updated_total_after_edit}，"
        f"删之后 {latch['updatedEvents']}"
    )

    # 往返闭合：整字典等值，不是「条数回去了」。
    assert read_notes(e2e_books_dir, BOOK_ID) == pre, "建 → 改 → 删之后 notes.json 没有回到流程之前"
    assert updated_total >= 3, (
        f"三次成功的写应当至少派发 3 次 reader3:annotations:updated，实测 {updated_total}"
        "（刷新前一段 ＋ 刷新后一段相加）"
    )
