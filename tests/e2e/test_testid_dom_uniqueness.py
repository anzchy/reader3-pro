"""ADR-0014 的**运行期**验证：渲染后的 DOM 里，`getByTestId()` 真的能唯一命中。

权威：`docs/adr/0014-bounded-testid-enumeration.md`。

**为什么静态那条不够。** `tests/unit/test_template_testid_uniqueness.py` 的 T1 证明的是
「一份模板文件内 `data-testid` 字面量互不重复」。静态唯一性与 DOM 唯一性**互不蕴含**，
两个方向都断：

  * 静态唯一 ⇏ DOM 唯一：`{% for book in books %}` 里那一个 `lib-book-card` 字面量，
    渲染后是 N 个节点。
  * DOM 唯一 ⇏ 静态唯一：互斥分支（`settings.js` 的 `set-provider-result` 两行）里
    同一个名字写两遍，页面上至多出现一个。

ADR-0014 的主张是「弹层与面板可以用 `getByTestId()` 稳定定位」，那是一句关于**浏览器里
那棵树**的话。它此前只有静态推论支撑，本文件把它放进真浏览器里测。
（ADR-0014 §Revisit When 第二条已经预留了这条路：「该换成渲染后 DOM 的运行期断言
——例如在 E2E harness 里扫一遍页面查重」。）

**立的不变式，逐字如下**（不是「任何 testid 都不许出现两次」——那条是错的，ADR-0014
明确允许无界集合共用一个字面量再靠判别位区分，写成那样的用例会在书库有第二本书的
那天被迫削弱）：

    把页面里全部 `[data-testid]` 节点按 testid 值分组。**大小 1 的组天然合规**。
    大小 > 1 的组，组内每个节点都必须带至少一个 `ALLOWED_DISCRIMINATORS` 里的属性，
    且**每个节点由 testid ＋ 它自己的判别位拼出的复合选择器，在活的 DOM 里恰好
    命中 1 个**。

这恰好等价于 Playwright strict 模式的真实要求：`getByTestId()` 要么唯一命中，要么必须
配一个判别位才能命中。

最后那一句 2026-09-05 改过，改的是**判据**不是措辞。此前写的是「组内判别位取值的元组
两两不同」，那是一条比要测的性质弱的推论：元组 `(book-id=b1)` 与 `(book-id=b1,
section=s)` 不相等，却是真子集关系，前者的复合选择器同时命中两个节点——一对真正有歧义
的节点从那条断言底下走过去了。现在直接把选择器拿去问浏览器，不再靠元组比较推。
原来那条比较仍然保留：它对「为什么不可分」给得出人话诊断，新那条只给得出命中数。

`ALLOWED_DISCRIMINATORS` 从 `scripts/lint_e2e_selectors.py` **导入**，21 个有界名从
`tests/unit/test_template_testid_uniqueness.py` **导入**——两处都是唯一定义处，抄一份
下来就是将来漂移的源头（「搬，不抄」）。

**不穿透 epub.js 的 iframe。** 理由与 `test_harness_smoke.py` 的 docstring 同一条，
而且更强：iframe 里是用户那本书自己的 XHTML，永远不会有 `data-testid`，扫它只会扫到空。

**三张页开在本模块自己的、装了出网闸的 context 里**，不是 `browser.new_page()`。
理由见下面 `gated_context` 那一段：默认 context 身上一副闸都没有，而 library / reader
的模板里各有一行 Google Fonts。
"""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

from conftest import (  # type: ignore[import-not-found]
    BOOK_ID,
    E2E_BOOK_IDS,
    _LOCAL_HOSTS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_module(path: Path, name: str):
    """按路径加载一个不是包的模块。只取常量，不跑 `main()`，不落盘。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"无法从 {path} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SELECTOR_LINT = _load_module(
    REPO_ROOT / "scripts" / "lint_e2e_selectors.py", "lint_e2e_selectors_for_dom_scan"
)
#: 判别位闭合清单的**唯一定义处**在 lint 里（`lint_e2e_selectors.py:70`，八项）。
#: 这里 import 而不是抄：两份拷贝就是将来漂移的来源。
ALLOWED_DISCRIMINATORS = frozenset(_SELECTOR_LINT.ALLOWED_DISCRIMINATORS)

_TEMPLATE_TESTIDS = _load_module(
    REPO_ROOT / "tests" / "unit" / "test_template_testid_uniqueness.py",
    "template_testid_targets_for_dom_scan",
)
#: ADR-0014 强制的有界名，13 ＋ 8。同样 import：那份文件是它们的唯一定义处。
LIBRARY_TARGETS: Tuple[str, ...] = _TEMPLATE_TESTIDS.LIBRARY_TARGETS
READER_TARGETS: Tuple[str, ...] = _TEMPLATE_TESTIDS.READER_TARGETS


def test_imported_target_lists_are_not_empty() -> None:
    """反空转：上面三个 import 若哪天返回空集合，下游的逐名断言会静默变成 0 条。

    `@pytest.mark.parametrize` 拿到空列表**不报错**（默认 `empty_parameter_set_mark`
    是 skip，只留一条 skipped），本文件里没有别的东西会因此变红——这就是本条存在的理由。

    钉的是下界，不是精确值：三个数各自的**精确值**都由别处守着，那才是它们的定义点。
    在这里再抄一份绝对值，等于把「那张表有多大」复制到两个文件里——改表的人（010 /
    013 往 library.html 加弹层时一定会改）得跑到一个跟他无关的文件里改一个数字。
      * `LIBRARY_TARGETS` / `READER_TARGETS` 的「只增不减」由
        `tests/unit/test_template_testid_uniqueness.py::test_t2_mandated_name_lists_only_grow`
        在定义点守着。
      * `ALLOWED_DISCRIMINATORS` 的**集合内容**由
        `tests/unit/test_lint_e2e_selectors_closed_list.py::test_s10_closed_list_is_exactly_the_eight_items`
        守着，且那八个名字是逐字抄自 ADR-0014 正文、不是从常量拷的。
    """
    assert len(LIBRARY_TARGETS) >= 5, LIBRARY_TARGETS
    assert len(READER_TARGETS) >= 3, READER_TARGETS
    assert len(ALLOWED_DISCRIMINATORS) >= 3, sorted(ALLOWED_DISCRIMINATORS)


# --------------------------------------------------------------------------------
# 出网闸：本模块自己的 context，装同一副闸
# --------------------------------------------------------------------------------
# `tests/e2e/conftest.py` 覆写的 `context` fixture 是**函数级**的，而本模块的页面是
# 模块级的（理由见下一段），拿不到它。此前这里走的是 `browser.new_page()`——那会在
# **默认 context** 里开页，那个 context 身上一副闸都没有。实测（2026-09-05）：
# library 与 reader 两页各自真的打了一次 `fonts.googleapis.com`。「e2e 零真实出网」
# 这条不变式在本模块上是空的。
#
# 修法是自己建一个 context 并装上同一副闸。**允许清单从 conftest import**：
# `_LOCAL_HOSTS` 是它的唯一定义处，抄一份下来就是将来漂移的源头。
#
# 谓词本身（六行）不得不重写一遍：conftest 里那份是 `context` fixture 内部的闭包，
# 没有任何可导入的出口，而本波的约束是「不改 conftest.py」（另有 agent 并行持有那个
# 文件）。**这是一份重复实现**，两处必须同时改；把它收成共享 helper 是本文件之外的
# 一笔欠账，记在这里。数据（那三个主机名）没有重复，只有谓词重复。
_GATE_HOSTS_SANITY = {"127.0.0.1", "localhost", "::1"}
assert set(_LOCAL_HOSTS) == _GATE_HOSTS_SANITY, (
    f"conftest._LOCAL_HOSTS 变成了 {sorted(_LOCAL_HOSTS)}——本模块的闸依赖它是回环三件套。"
    "它若被改宽，这里必须跟着重新论证，而不是静默继承。"
)

#: 正向对照用的外部 URL。取模板里真实存在的那个字体域，不编一个不存在的域名：
#: 编出来的域会因为 DNS 失败而 fetch 失败，那样这条对照证明的是「域名不存在」，
#: 不是「闸拦住了」。
_PROBE_URL = "https://fonts.googleapis.com/css2?family=Inter&display=swap"
_PROBE_ORIGIN = "https://fonts.googleapis.com"


def _install_egress_gate(context: BrowserContext) -> Set[str]:
    """给 context 装出网闸，返回被拦域的记录集（活的，随后续请求增长）。"""

    blocked: Set[str] = set()

    def _gate(route, request) -> None:  # type: ignore[no-untyped-def]
        parsed = urlparse(request.url)
        if parsed.scheme not in ("http", "https") or parsed.hostname in _LOCAL_HOSTS:
            route.continue_()
            return
        blocked.add(f"{parsed.scheme}://{parsed.netloc}")
        route.abort()

    context.route("**/*", _gate)
    return blocked


@pytest.fixture(scope="module")
def gated_context(
    browser: Browser, browser_context_args: Dict[str, Any], live_server: str
) -> Iterator[Tuple[BrowserContext, Set[str]]]:
    """模块级、装了出网闸的 context。产出 `(context, 被拦域集合)`。

    **建好之后先做一次正向对照，再交给用例。** 「闸装上了」和「闸真的拦得住」是两件
    事：`context.route` 调用成功不代表模式匹配到了，也不代表 abort 生效。所以这里在
    yield 之前开一张探针页，从被测服务的同源上下文里 fetch 一次真实外部 URL，要求
    (a) 它必须失败，(b) 失败的原因必须是被本闸记下来的那个域。同一张页上再 fetch 一次
    回环 URL 并要求成功——否则「全都失败」也能让 (a) 通过，那是一副焊死的闸，不是闸。

    对照跑完把记录清空，交给用例的是一张白纸：后续任何一个非回环域出现在里面，都是
    页面自己发的。
    """
    context = browser.new_context(**browser_context_args)
    try:
        blocked = _install_egress_gate(context)
        probe = context.new_page()
        try:
            probe.goto(f"{live_server}/api/health")
            outcome = probe.evaluate(
                """
                async ([external, local]) => {
                  const result = {};
                  try { await fetch(external, {mode: "no-cors"}); result.external = "reached"; }
                  catch (e) { result.external = "failed"; }
                  try { const r = await fetch(local); result.local = r.ok ? "ok" : "status-" + r.status; }
                  catch (e) { result.local = "failed"; }
                  return result;
                }
                """,
                [_PROBE_URL, f"{live_server}/api/health"],
            )
        finally:
            probe.close()
        assert outcome["external"] == "failed", (
            f"正向对照失败：{_PROBE_URL} 在装了闸的 context 里**打通了**（{outcome}）。"
            "闸没生效，本模块下面所有页面都在裸奔出网。"
        )
        assert _PROBE_ORIGIN in blocked, (
            f"外部 fetch 是失败了，但闸没记下 {_PROBE_ORIGIN}（记录：{sorted(blocked)}）。"
            "失败原因不是被拦，这条对照证明不了闸拦得住。"
        )
        assert outcome["local"] == "ok", (
            f"反向对照失败：回环 URL 也没通（{outcome}）。这副闸把被测服务一起拦了，"
            "「外部请求失败」就成了废话。"
        )
        blocked.clear()
        yield context, blocked
    finally:
        context.close()


# --------------------------------------------------------------------------------
# 页面固定装置：三个页面各加载一次
# --------------------------------------------------------------------------------
# 模块级而不是函数级（pytest-playwright 的 `page` 是函数级）：本文件全部是**只读**
# 断言，没有任何用例改页面状态，而逐名那 21 条若各自重新 goto，就是 21 次整页加载
# 换 21 行断言——20 倍的代价换不到任何额外信息。


#: 每个页面**允许被闸拦下**的外部域，逐页写死。
#:
#: 「拦下」≠「出网」——abort 掉的请求一个字节都没离开本机，零出网这条不变式由闸本身
#: 保证。这张表管的是另一件事：**页面还想往外打什么**。
#:
#: library / reader 的 `<head>` 里各有一行
#: `<link href="https://fonts.googleapis.com/css2?…" rel="stylesheet">`（library.html:10、
#: reader.html:11），所以这两页各有且仅有这一个域。同两行上面的 `preconnect` 不产生
#: HTTP 请求，闸看不到它；`fonts.gstatic.com` 只有在那份 CSS 加载成功后才会被请求，
#: 而它永远加载不成功，所以也不在表里——**写进去就是给未来的真变化预留一格静默**。
#:
#: settings 是空集，且这不是「碰巧」：那一页的模板没有任何外部资源，空集是它的规格。
#:
#: 本波的约束是「不改 src/」，所以这里没法把那两行 `<link>` 删掉再断言全空。表里多出
#: 任何一个新域，都是有人往模板或脚本里加了新的外部依赖——那正是要在这里显形的事。
EXPECTED_EGRESS_ATTEMPTS: Dict[str, frozenset] = {
    "library": frozenset({"https://fonts.googleapis.com"}),
    "reader": frozenset({"https://fonts.googleapis.com"}),
    "settings": frozenset(),
}


def _open(
    gated: Tuple[BrowserContext, Set[str]], base: str, path: str, key: str
) -> Iterator[Page]:
    context, blocked = gated
    page = context.new_page()
    # try 从**建页的下一行**开始：goto 与 networkidle 都可能抛（服务没起来、
    # 30 秒超时），而它们此前在 try 之外——抛出来的那一次，这张页和它占的
    # renderer 进程就泄漏到 session 结束。
    try:
        # 这张页**自己**发起的非回环域。不能拿 `blocked` 的前后差来算：那是 context
        # 级的累计集合，library 先记下 fonts.googleapis.com 之后，reader 再发同一个域
        # 时差集是空的——三页里有两页会因此变成空转。
        attempted: Set[str] = set()

        def _record(request) -> None:  # type: ignore[no-untyped-def]
            parsed = urlparse(request.url)
            if parsed.scheme in ("http", "https") and parsed.hostname not in _LOCAL_HOSTS:
                attempted.add(f"{parsed.scheme}://{parsed.netloc}")

        page.on("request", _record)
        page.goto(f"{base}{path}")
        # 三个页面都有 JS 注入的 testid 节点（书卡状态 pill、provider 卡片），它们要等
        # XHR 回来才进 DOM。只等 "load" 会在这些节点出现**之前**就扫完——那不是更稳，
        # 是把要测的东西扫掉了。
        page.wait_for_load_state("networkidle")
        expected = EXPECTED_EGRESS_ATTEMPTS[key]
        assert attempted <= expected, (
            f"{key} 页（{path}）试图打表外的非回环域：{sorted(attempted - expected)}。"
            f"它们这一轮被闸 abort 了（零字节出网），但表外就意味着有人新加了一条外部"
            f"依赖。已登记的：{sorted(expected)}。"
        )
        # 「发了」与「被拦了」是两件事，这一条钉的是后者：本页发出的每一个非回环域，
        # 都必须出现在闸的记录里。少一个 = 有一个请求绕过了 route（真出网了）。
        escaped = attempted - blocked
        assert not escaped, (
            f"{key} 页发往 {sorted(escaped)} 的请求**没有**被出网闸记下——"
            f"它们绕过了 context.route，也就是真的出网了。闸记录：{sorted(blocked)}"
        )
        if attempted != expected:
            # 少于预期只报不判：删掉一条外部依赖是**好事**，不该红。红的应该是随后
            # 「表没跟着删」这件事，而那由人来判。
            print(f"\n[egress] {key}: 实到 {sorted(attempted)} ⊂ 登记 {sorted(expected)}")
        yield page
    finally:
        page.close()


@pytest.fixture(scope="module")
def library_page(
    gated_context: Tuple[BrowserContext, Set[str]], live_server: str
) -> Iterator[Page]:
    yield from _open(gated_context, live_server, "/", "library")


@pytest.fixture(scope="module")
def reader_page(
    gated_context: Tuple[BrowserContext, Set[str]], live_server: str
) -> Iterator[Page]:
    yield from _open(gated_context, live_server, f"/read/{BOOK_ID}/0", "reader")


@pytest.fixture(scope="module")
def settings_page(
    gated_context: Tuple[BrowserContext, Set[str]], live_server: str
) -> Iterator[Page]:
    yield from _open(gated_context, live_server, "/settings", "settings")


#: 每个页面扫到的 testid 节点数下限（§0.5 反空转）。只用来证明「枚举确实跑了」——
#: 枚举一旦失灵返回空表，下面所有全称命题都会空转变绿。
#:
#: 三个值取齐 5，而不是各自贴着真值。2026-09-01 实测真值是 library 67 / reader 69 /
#: settings 46；此前 library 与 reader 钉的是 30，只有 2.2 倍余量。那个余量看着宽，
#: 实际上把反空转悄悄变成了越界闸门：013 重写书库与设置外壳、014 重写阅读器外壳时，
#: 中途状态掉到 30 以下是**计划之内的合法改动**，不该在一条只想证明「querySelectorAll
#: 没返回空表」的断言上先红一次。两者的到期时间完全不同——反空转是永久的，越界闸门
#: 随批次结束就该拆。
#:
#: 真值不写进注释：写了就得跟着页面改，改漏一次注释就开始骗人。实到值由断言消息报出。
NODE_FLOORS = {
    "library": 5,
    "reader": 5,
    "settings": 5,
}

PAGE_FIXTURES = {
    "library": "library_page",
    "reader": "reader_page",
    "settings": "settings_page",
}

#: 每页至少一个**点名的、只可能由 JS 注入**的哨兵 testid，及其应有的重数。
#:
#: `NODE_FLOORS` 那条下限管不了这件事，而且管不了是结构性的：它是一条**匿名**的
#: 计数下限，静态模板一个人就能满足（三页的静态 testid 各有几十个）。`library.js`
#: 或 `settings.js` 整个挂掉——404、语法错、初始化抛异常——页面照样渲出静态骨架，
#: 节点数照样远超 5，于是「全部动态 testid 一个不剩」这件事在本文件里**没有任何
#: 一条断言会红**：分组不变式对空组无话可说，逐名那两条只覆盖有界名。
#: 那正是本表要拦的洞。
#:
#: 三个名字都验过「只在 JS 里出现，模板里一个字都没有」：
#:   * `lib-book-{grid,row}-status-not-indexed` —— `library.js` 的
#:     `LIB_BOOK_{GRID,ROW}_STATUS_TESTID` 表，要等 `/api/library/status` 的 XHR 回来
#:     才 `setAttribute`。重数 = 书库里的书数，因此从 `E2E_BOOKS_IDS` 派生而不写 4：
#:     再加一本书时该红的是「书库条数」那条用例，不是这里（与 conftest 里同一条纪律）。
#:     语料四本都没建索引，状态恒为 `not_indexed`。
#:   * `rd-notes-empty` —— `notes-panel.js` 在 `DOMContentLoaded` 拉
#:     `/api/notes/{book}` 后，零条笔记时才创建的那个 div。`notes_isolation` 保证本
#:     模块看到的永远是零条，所以重数恒为 1。
#:   * `set-provider-refresh-models` —— `settings.js` 的 provider 卡片模板里，
#:     **只有 ollama 那张卡**才渲的按钮，因此重数恒为 1；它同时证明了「provider 列表
#:     的 XHR 回来了且循环跑完了」。取它而不取 `set-provider-card`，是因为后者的重数
#:     等于 provider 个数，会把 `ai/config.py` 的默认表钉进本文件。
#: **reader 页是空的，而且这是查过之后的结论，不是漏了。** `reader.html` 里有 69 个
#: testid 字面量，而阅读器页加载完成时扫到的节点数与它同量级——那一页在 load 时刻
#: **没有任何 JS 注入的 testid**：`rd-notes-empty` / `rd-notes-item` 要点开笔记面板
#: （`open()` 里才调 `loadAndRender`）、`rd-search-*` 要发起搜索、`rd-anno-span` 要先有
#: 标注、`rd-ai-conversation` 要先有会话，四者本模块一个都不满足。硬塞一个进去就得
#: 先造状态，那会把这个只读模块变成写模块。reader 页改用下面 `PAGE_SCRIPT_GLOBALS`
#: 那条等价强度的证据。
DYNAMIC_SENTINELS: Dict[str, Dict[str, int]] = {
    "library": {
        "lib-book-grid-status-not-indexed": len(E2E_BOOK_IDS),
        "lib-book-row-status-not-indexed": len(E2E_BOOK_IDS),
    },
    "reader": {},
    "settings": {"set-provider-refresh-models": 1},
}

#: 每页「该页脚本确实执行过」的第二重证据：只有脚本跑到底才会挂上去的全局对象名。
#:
#: 给 reader 用的（那一页没有 load 期的动态 testid，理由见上）。三个名字都是各自模块
#: 在 `DOMContentLoaded` 回调**末尾**无条件赋的：`toolbar.js:277` / `toc-panel.js:61` /
#: `notes-panel.js:211`。脚本 404、语法错、构造函数抛异常，三者任一都会让对应的名字
#: 消失——而这三条正是本文件扫的那 69 个 reader testid 背后的行为主。
#:
#: 不取 `Reader3AnnotationUI` / `Reader3Ctx` / `Reader3Epub`：它们要等 epub.js 把正文
#: 渲进 iframe 之后才挂，与 `networkidle` 之间没有确定的先后，钉了就是给本模块引进
#: 一个 flaky。要等它们得用 `helpers.settle_marks`，那是写路径用例的代价，本模块不付。
#:
#: library / settings 留空：那两页已经有点名的动态 testid 哨兵，重复一遍不增加信息。
PAGE_SCRIPT_GLOBALS: Dict[str, Tuple[str, ...]] = {
    "library": (),
    "reader": ("Reader3Toolbar", "Reader3TOCPanel", "Reader3NotesPanel"),
    "settings": (),
}

#: 反空转的空转：上面两张表若有哪一页两边都空，那一页就完全没有「JS 跑过」的证据，
#: 而 `NODE_FLOORS` 那条匿名下限静态骨架一个人就能满足。这条在 import 期就断。
for _key in ("library", "reader", "settings"):
    assert DYNAMIC_SENTINELS[_key] or PAGE_SCRIPT_GLOBALS[_key], (
        f"{_key} 页两张证据表都是空的——它的 JS 全挂时本文件不会红。"
    )
del _key


# --------------------------------------------------------------------------------
# 枚举：在页内一次遍历，把结构化数据带回 Python
# --------------------------------------------------------------------------------

ENUMERATE_TESTID_NODES = """
() => {
  const nodes = document.querySelectorAll("[data-testid]");  // # lint-e2e-selectors: allow —— 枚举，不是定位：本用例的被测对象是「页面里全部 testid 节点」的全集，压根没有被挑出来的目标元素，而契约禁的是「拿 class 或结构去定位某一个元素」。属性存在性形态 [data-testid] 落在 ATTR_RE 的「必须带值」之外，但它不是这条 lint 要防的东西。改用 getElementsByTagName("*") 能让正则扫不到，那是一条看不见的绕过，比显式放行糟得多。
  const out = [];
  for (const el of nodes) {
    const attrs = {};
    for (const a of el.attributes) {
      if (a.name.startsWith("data-")) attrs[a.name] = a.value;
    }
    // 取 attrs 里已经收好的值，而不是再调一次元素的属性读取方法：那个方法名与
    // Playwright 的 locator 属性读取同名，会被选择器 lint 的 LOCATOR_CALL_RE 当成
    // 一次定位抓走，报一条与本文件主张无关的假违规。少一次 DOM 调用，读起来也没变差。
    out.push({
      testid: attrs["data-testid"],
      tag: el.tagName.toLowerCase(),
      attrs: attrs,
    });
  }
  return out;
}
"""


def _scan(page: Page, key: str) -> List[Dict[str, Any]]:
    nodes = page.evaluate(ENUMERATE_TESTID_NODES)
    floor = NODE_FLOORS[key]
    assert len(nodes) >= floor, (
        f"{key} 页只扫到 {len(nodes)} 个 [data-testid] 节点（下限 >= {floor}）——"
        f"枚举失灵时下面的全称命题会空转通过，这条下限就是拦它的"
    )
    # 匿名下限之外，再点名几个只可能由 JS 注入的哨兵（见 DYNAMIC_SENTINELS 的注释：
    # 页面脚本整个挂掉时，静态骨架一个人就能满足上面那条下限）。
    counts = defaultdict(int)
    for node in nodes:
        counts[node["testid"]] += 1
    expected = DYNAMIC_SENTINELS[key]
    actual = {name: counts[name] for name in expected}
    assert actual == expected, (
        f"{key} 页的动态哨兵 testid 数目不对：实到 {actual}，应为 {expected}。"
        f"0 ＝ 该页的 JS 压根没跑到那一步（脚本 404 / 抛异常 / XHR 没回来），此时"
        f"整页的动态 testid 可能一个不剩，而节点数下限（{floor}）静态骨架一个人就能满足；"
        f"数目不符 ＝ 渲染循环没跑完或多跑了。"
    )
    globals_expected = PAGE_SCRIPT_GLOBALS[key]
    if globals_expected:
        present = page.evaluate(
            "(names) => names.filter((n) => window[n] != null)", list(globals_expected)
        )
        missing = sorted(set(globals_expected) - set(present))
        assert not missing, (
            f"{key} 页缺了这些「脚本跑过」的全局对象：{missing}。"
            f"它们是各自模块 DOMContentLoaded 回调末尾无条件挂的，缺一个就说明那个脚本"
            f"404 / 语法错 / 初始化抛了——此时本文件下面扫到的 testid 全是静态骨架。"
        )
    return nodes


def _group(nodes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        groups[node["testid"]].append(node)
    return dict(groups)


def _discriminator_key(node: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
    """节点身上那些**准入**判别位的 (名, 值) 元组，排序后可比。"""
    return tuple(
        sorted(
            (k, v) for k, v in node["attrs"].items() if k in ALLOWED_DISCRIMINATORS
        )
    )


def _violations(groups: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """返回人话的违规说明列表；空表示 DOM 满足 strict 模式的可定位性。"""
    out: List[str] = []
    for testid, members in sorted(groups.items()):
        if len(members) == 1:
            continue  # 大小 1 的组天然合规
        keys = [_discriminator_key(m) for m in members]
        bare = [m for m, k in zip(members, keys) if not k]
        if bare:
            out.append(
                f"{testid!r} 有 {len(members)} 个节点，其中 {len(bare)} 个身上没有任何"
                f"闭合清单里的判别位（{sorted(ALLOWED_DISCRIMINATORS)}）——"
                f"getByTestId() 对它必抛 strict violation，而且没有任何复合选择器能救。"
                f"裸节点：{[(m['tag'], m['attrs']) for m in bare]}"
            )
            continue
        if len(set(keys)) != len(keys):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            out.append(
                f"{testid!r} 有 {len(members)} 个节点，判别位取值撞了：{dupes}——"
                f"判别位不是免死金牌，取值相同的复合选择器照样命中多个"
            )
    return out


# --------------------------------------------------------------------------------
# 判别位「两两不同」不够：真正要的是「每个节点的复合选择器在真 DOM 里恰好命中 1 个」
# --------------------------------------------------------------------------------
# `_violations` 上面那条比的是**元组相等**，而元组不等不蕴含选择器可分。反例（纯 Python
# 就能构造，不用浏览器）：
#
#     A: [data-testid="x"][data-book-id="b1"]
#     B: [data-testid="x"][data-book-id="b1"][data-section="s"]
#
# 两个元组不相等，`len(set(keys)) == len(keys)` 通过；但 A 的复合选择器是 B 的**真子集**，
# 它同时命中 A 和 B——`page.locator(A)` 照抛 strict violation。一对真正有歧义的节点就这样
# 从那条断言底下走过去了。子集只是最容易说清的一种，同样的洞还有「判别位相同、
# 只靠一个不在闭合清单里的属性区分」等等。
#
# 与其枚举各种撞法，不如**直接把要测的性质拿去问浏览器**：为每个节点按它自己的判别位
# 拼出复合选择器，要求它在活的 DOM 里 `querySelectorAll().length === 1`。这既是
# ADR-0014 的字面主张，也正是 Playwright strict 模式的真实判据——不需要任何推论。
#
# 拼出来的选择器先过一遍仓库自己的选择器 lint（`selector_ok`）：一是证明动态拼串没绕过
# 契约（形态仍是 `[data-testid][判别位…]`），二是拼错时报在拼串上，而不是报成一条
# 莫名其妙的 DOM 断言失败。

COUNT_SELECTOR_MATCHES = """
(selectors) => selectors.map((s) => document.querySelectorAll(s).length)
"""


def _compound_selector(node: Dict[str, Any]) -> str:
    """节点的「testid ＋ 它自己的全部准入判别位」复合选择器。"""
    parts = [f'[data-testid="{node["testid"]}"]']
    parts.extend(f'[{k}="{v}"]' for k, v in _discriminator_key(node))
    return "".join(parts)


def _unresolvable(page: Page, groups: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """真 DOM 里复合选择器命中数 != 1 的节点。空表示 strict 模式真的能定位到每一个。"""
    targets: List[Tuple[str, Dict[str, Any], str]] = []
    out: List[str] = []
    for testid, members in sorted(groups.items()):
        if len(members) == 1:
            continue  # 大小 1 的组天然合规，光 testid 就唯一
        for node in members:
            for _, value in _discriminator_key(node):
                if '"' in value or "\\" in value:
                    out.append(
                        f"{testid!r} 的某个判别位取值里有引号或反斜杠（{value!r}），"
                        f"没法安全地拼进属性选择器——这本身就说明它不适合当判别位。"
                    )
                    break
            else:
                selector = _compound_selector(node)
                reason = _SELECTOR_LINT.selector_ok(selector)
                if reason is not None:
                    out.append(
                        f"{testid!r} 拼出的复合选择器 {selector!r} 过不了仓库的选择器 lint：{reason}"
                    )
                    continue
                targets.append((testid, node, selector))

    if not targets:
        return out

    counts = page.evaluate(COUNT_SELECTOR_MATCHES, [sel for _, _, sel in targets])
    assert len(counts) == len(targets), (
        f"页内计数返回了 {len(counts)} 个结果，送进去的是 {len(targets)} 个选择器"
    )
    for (testid, node, selector), hit in zip(targets, counts):
        if hit != 1:
            out.append(
                f"{selector} 在真 DOM 里命中 {hit} 个节点（应为 1）。"
                f"该节点：{(node['tag'], node['attrs'])}。"
                f"命中 >1 ＝ 这一组里另有节点的判别位是它的超集（或另有等价节点），"
                f"两个元组不相等并不蕴含选择器可分；命中 0 ＝ 拼串与 DOM 对不上。"
            )
    return out


# --------------------------------------------------------------------------------
# 断言一：分组不变式（无界集合合法，裸重名违规）
# --------------------------------------------------------------------------------


@pytest.mark.parametrize("page_key", sorted(PAGE_FIXTURES))
def test_every_duplicated_testid_is_separable_by_a_discriminator(
    page_key: str, request: pytest.FixtureRequest
) -> None:
    page: Page = request.getfixturevalue(PAGE_FIXTURES[page_key])
    nodes = _scan(page, page_key)
    groups = _group(nodes)
    multi = {k: v for k, v in groups.items() if len(v) > 1}

    print(
        f"\n[testid-scan] {page_key}: {len(nodes)} 个节点 / {len(groups)} 个组 / "
        f"{len(multi)} 个组大小 > 1"
    )
    for testid in sorted(multi):
        print(
            f"[testid-scan]   {testid} ×{len(multi[testid])} "
            f"判别位={[dict(_discriminator_key(m)) for m in multi[testid]]}"
        )

    # 两条一起报：`_violations` 说得清「为什么不可分」（裸节点 / 取值撞车），
    # `_unresolvable` 才是判据本身（活 DOM 里命中数）。只留后者会丢掉可读的诊断，
    # 只留前者会漏掉子集那一类。
    problems = _violations(groups) + _unresolvable(page, groups)
    assert problems == [], (
        f"{page_key} 页的 DOM 不满足 ADR-0014 的可定位性："
        + "\n  - ".join([""] + problems)
    )


# --------------------------------------------------------------------------------
# 断言二：ADR-0014 强制的有界名，逐个恰好命中 1 个
# --------------------------------------------------------------------------------
# 断言一是全称命题，它对「某个名字一个节点都没有」无话可说（空组不存在，也就不违规）。
# 这一条直接兑现 ADR-0014 的字面主张：`get_by_test_id(name)` 对这 21 个名字各命中 1 个。
#
# 用 `.count()` 而不是 `expect(...).to_be_visible()`：弹层与工具条初始是隐藏的
# （`aria-hidden`、`<dialog>` 未 open、`hidden`），而本条测的是**定位唯一性**，不是可见性。
# 隐藏元素照样能被 get_by_test_id 命中，strict violation 也照样会抛。


def _counts(page: Page, names: Tuple[str, ...]) -> Dict[str, int]:
    return {name: page.get_by_test_id(name).count() for name in names}


def test_library_bounded_testids_each_resolve_to_exactly_one_node(
    library_page: Page,
) -> None:
    actual = _counts(library_page, LIBRARY_TARGETS)
    print(f"\n[testid-count] library: {actual}")
    assert actual == {name: 1 for name in LIBRARY_TARGETS}, (
        "library 页上 ADR-0014 强制的有界名没有各自恰好命中 1 个节点。"
        "0 ＝ 该名字根本没渲染出来（这条断言对它空转）；≥2 ＝ getByTestId() 会抛 strict violation"
    )


def test_reader_bounded_testids_each_resolve_to_exactly_one_node(
    reader_page: Page,
) -> None:
    actual = _counts(reader_page, READER_TARGETS)
    print(f"\n[testid-count] reader: {actual}")
    assert actual == {name: 1 for name in READER_TARGETS}, (
        "reader 页上 ADR-0014 强制的有界名没有各自恰好命中 1 个节点。"
        "0 ＝ 该名字根本没渲染出来（这条断言对它空转）；≥2 ＝ getByTestId() 会抛 strict violation"
    )
