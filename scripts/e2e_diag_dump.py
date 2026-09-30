"""失败时把浏览器侧证据 dump 出来，用于给 baseline_1b 那族 8 秒超时归因。

为什么是一个 `-p` 插件而不是一条新用例：
  - `tests/e2e/conftest.py` 与 `helpers.py` 在冻结集里，动一个字节就改变 `suite_hash`，已通过的
    soak 批次不再覆盖、须重跑一批并重跑机制闸（2026-09-28 起的批次规则；写这段时是「清零台账」）；
  - `tests/e2e/` 根下的新文件虽然不在 `suite_hash` 的覆盖面内，但要改
    `scripts/lint_e2e_groups.py` 的收集数常量，而且只能**复现**那条流程，
    观察不到真正红掉的那几条冻结用例；
  - 本文件落在 `scripts/` 下，用 `PYTHONPATH=scripts pytest -p e2e_diag_dump` 挂上去
    （`scripts/` 不是包，所以走 `PYTHONPATH` 而不是 `-p scripts.e2e_diag_dump`）。
    冻结集零改动、收集数不变，而且观察的就是红掉的那一条用例本身。
    （⬛ 2026-09-30：「冻结集零改动」是写这段时的事实；019 为 #49 / #62 已改过冻结集，本文件自身仍不在其中。）

**光看诊断环不够，这是第二版加网络与 console 的理由。**
011 证过「写成功不往环里记东西」，所以环空只等于「没有**被报告的写失败**」。
它同时兼容三种互斥的根因，必须靠「请求到底发没发、回了什么」才能分开：

  | 请求发出了吗 | 回应 | 根因 |
  |---|---|---|
  | 没发 | —        | 动作压根没走到写这一步（产品／可操作性） |
  | 发了 | 非 2xx   | **产品缺陷**（且是一条环没盖住的静默出口） |
  | 发了 | 2xx      | 盘上没在 8s 内可见 ⇒ 测试侧等待太短 |
  | 发了 | 一直没回 | CPU 饿死，整条管线比 8s 慢 ⇒ 既不是产品错也不是 8 这个数错 |
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time

import pytest
from playwright.sync_api import Error as PlaywrightError

_OUT = pathlib.Path(os.environ.get("E2E_DIAG_OUT", "e2e-diag")).resolve()
_EVENTS: dict[str, dict] = {}
_LATE: dict[str, dict] = {}
_NOTES_MARK = "/api/notes"
# 文件名 = 净化后的前缀（截 120）+ 完整 nodeid 的 sha256 前 12 位（019 WI-7，审计 #1）。
# 旧写法只截前 150 个字符：W6-C7 的两个参数共享前 152 个字符，后写的静默盖掉先写的；
# 截的还是字符不是字节，CJK 参数能撑爆 NAME_MAX。判据钉在 `tests/unit/test_e2e_diag_dump_names.py`。
_UNSAFE = re.compile(r"[^A-Za-z0-9._\[\]-]")
_PREFIX_MAX = 120
_DIGEST_LEN = 12


# 浏览器侧的 fetch 台账。**必须是注入脚本，不能是 page.on(...) 监听器。**
# 实测：把 request/response 挂成 Playwright 监听器会把这条红整个压掉
# （5 跑 0 红、耗时从 66–86s 回落到无压力档的 56–58s），和 `--tracing` 同属观察者效应——
# 每条事件都要跨进程回调一次 Python，改变了事件泵的节奏。
# 注入脚本只在浏览器里跑，整场测试零 Python 往返，失败那一刻才 evaluate 一次。
_FETCH_LEDGER = """
(() => {
  if (window.__r3FetchLog) return;
  const log = [];
  window.__r3FetchLog = log;
  const t0 = Date.now();
  const orig = window.fetch;
  window.fetch = function (...args) {
    const url = String((args[0] && args[0].url) || args[0] || "");
    const method = (args[1] && args[1].method) || (args[0] && args[0].method) || "GET";
    if (!/\/api\/notes/.test(url)) return orig.apply(this, args);
    const rec = { method, url, sent: Date.now() - t0, settled: null, status: null, error: null };
    log.push(rec);
    return orig.apply(this, args).then(
      (r) => { rec.settled = Date.now() - t0; rec.status = r.status; return r; },
      (e) => { rec.settled = Date.now() - t0; rec.error = String(e); throw e; }
    );
  };
})();
"""


@pytest.fixture(autouse=True)
def _r3_diag_capture(request):
    # 只对真的要浏览器的用例挂钩子，别把不需要 page 的用例拖去开浏览器。
    if "page" not in request.fixturenames:
        yield
        return
    page = request.getfixturevalue("page")
    page.add_init_script(_FETCH_LEDGER)
    yield
    # 第二次快照：makereport 那一刻写请求可能还悬着，到 teardown 时它要么回了、
    # 要么抛了。这一条差值就是「产品吞掉了失败」与「压根没跑完」的判别器。
    rec = _LATE.get(request.node.nodeid)
    if rec is None:
        return
    try:
        rec["late_fetch"] = page.evaluate("() => window.__r3FetchLog || '__NO_LOG__'")
        # responseEnd 由网络栈记账，不经过 JS 主线程 —— 这是「响应回来晚」
        # 与「JS 跑得晚」的唯一判别器。
        rec["late_perf"] = page.evaluate("""() => (performance.getEntriesByType('resource') || [])
  .filter((e) => /\\/api\\/notes/.test(e.name))
  .map((e) => ({
    name: e.name.replace(/^https?:\\/\\/[^/]+/, ''),
    start: Math.round(e.startTime),
    reqStart: Math.round(e.requestStart || 0),
    respStart: Math.round(e.responseStart || 0),
    respEnd: Math.round(e.responseEnd || 0),
    dur: Math.round(e.duration),
  }))""")
        rec["late_diag"] = page.evaluate(
            "() => (window.Reader3NotesDiag && window.Reader3NotesDiag.entries)"
            " ? window.Reader3NotesDiag.entries() : '__NO_RING__'"
        )
    except PlaywrightError as exc:
        rec["late_error"] = f"{type(exc).__name__}: {exc}"
    _write(rec)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    report = yield
    rep = report.get_result()
    # 只在 call 阶段动手：此时 page fixture 还没拆，页面仍活着。缺省只 dump 失败；
    # `E2E_DIAG_ALWAYS=1` 时每条都 dump（019 WI-2 / 009 #49 的压力臂：全绿的一轮若不 dump，
    # 「慢请求簇没了」就只剩「没有失败」撑着）。开关在**钩子执行时**读，不像 `_OUT` 那样
    # 在 import 时定死；只认字面 "1"，"0" / 空串都是关。判据钉在
    # `tests/unit/test_e2e_diag_dump_always.py`。
    if rep.when != "call":
        return
    if not rep.failed and os.environ.get("E2E_DIAG_ALWAYS") != "1":
        return
    page = item.funcargs.get("page") if hasattr(item, "funcargs") else None
    if page is None:
        return

    record: dict = {"test": item.nodeid}
    try:
        record["fetch"] = page.evaluate("() => window.__r3FetchLog || '__NO_LOG__'")
    except PlaywrightError as exc:
        record["fetch_error"] = f"{type(exc).__name__}: {exc}"
    try:
        record["perf"] = page.evaluate("""() => (performance.getEntriesByType('resource') || [])
  .filter((e) => /\\/api\\/notes/.test(e.name))
  .map((e) => ({
    name: e.name.replace(/^https?:\\/\\/[^/]+/, ''),
    start: Math.round(e.startTime),
    reqStart: Math.round(e.requestStart || 0),
    respStart: Math.round(e.responseStart || 0),
    respEnd: Math.round(e.responseEnd || 0),
    dur: Math.round(e.duration),
  }))""")
    except PlaywrightError as exc:
        record["perf_error"] = f"{type(exc).__name__}: {exc}"
    try:
        record["diag"] = page.evaluate(
            "() => (window.Reader3NotesDiag && window.Reader3NotesDiag.entries)"
            " ? window.Reader3NotesDiag.entries() : '__NO_RING__'"
        )
    except PlaywrightError as exc:  # 页面已关 / 导航中 —— 记下来，别把它伪装成「环是空的」
        record["diag_error"] = f"{type(exc).__name__}: {exc}"
    record["url"] = page.url

    _LATE[item.nodeid] = record
    _write(record)


def _write(record: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / _dump_name(record["test"])).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _dump_name(nodeid: str) -> str:
    """nodeid → dump 文件名。前缀只给人看；区分全靠摘要，所以摘要**总是**追加、且取自完整 nodeid。

    用 sha256 不用 `hash()`：call 阶段与 teardown 阶段的两次写必须落进同一个文件，
    不能随 `PYTHONHASHSEED` 变。前缀纯 ASCII，整个名字至多 138 字节。
    """
    prefix = _UNSAFE.sub("_", nodeid)[:_PREFIX_MAX]
    digest = hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:_DIGEST_LEN]
    return f"{prefix}-{digest}.json"
