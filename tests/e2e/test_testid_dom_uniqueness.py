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
    且组内这些判别位取值的元组两两不同。

这恰好等价于 Playwright strict 模式的真实要求：`getByTestId()` 要么唯一命中，要么必须
配一个判别位才能命中。

`ALLOWED_DISCRIMINATORS` 从 `scripts/lint_e2e_selectors.py` **导入**，21 个有界名从
`tests/unit/test_template_testid_uniqueness.py` **导入**——两处都是唯一定义处，抄一份
下来就是将来漂移的源头（「搬，不抄」）。

**不穿透 epub.js 的 iframe。** 理由与 `test_harness_smoke.py` 的 docstring 同一条，
而且更强：iframe 里是用户那本书自己的 XHTML，永远不会有 `data-testid`，扫它只会扫到空。
"""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from playwright.sync_api import Browser, Page

from conftest import BOOK_ID  # type: ignore[import-not-found]

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
    """反空转：上面两个 import 若哪天返回空元组，下游的逐名断言会静默变成 0 条。"""
    assert len(LIBRARY_TARGETS) == 13, LIBRARY_TARGETS
    assert len(READER_TARGETS) == 8, READER_TARGETS
    assert len(ALLOWED_DISCRIMINATORS) == 8, sorted(ALLOWED_DISCRIMINATORS)


# --------------------------------------------------------------------------------
# 页面固定装置：三个页面各加载一次
# --------------------------------------------------------------------------------
# 模块级而不是函数级（pytest-playwright 的 `page` 是函数级）：本文件全部是**只读**
# 断言，没有任何用例改页面状态，而逐名那 21 条若各自重新 goto，就是 21 次整页加载
# 换 21 行断言——20 倍的代价换不到任何额外信息。


def _open(browser: Browser, base: str, path: str) -> Iterator[Page]:
    page = browser.new_page()
    page.goto(f"{base}{path}")
    # 三个页面都有 JS 注入的 testid 节点（书卡状态 pill、provider 卡片），它们要等
    # XHR 回来才进 DOM。只等 "load" 会在这些节点出现**之前**就扫完——那不是更稳，
    # 是把要测的东西扫掉了。
    page.wait_for_load_state("networkidle")
    try:
        yield page
    finally:
        page.close()


@pytest.fixture(scope="module")
def library_page(browser: Browser, live_server: str) -> Iterator[Page]:
    yield from _open(browser, live_server, "/")


@pytest.fixture(scope="module")
def reader_page(browser: Browser, live_server: str) -> Iterator[Page]:
    yield from _open(browser, live_server, f"/read/{BOOK_ID}/0")


@pytest.fixture(scope="module")
def settings_page(browser: Browser, live_server: str) -> Iterator[Page]:
    yield from _open(browser, live_server, "/settings")


#: 每个页面扫到的 testid 节点数下限（§0.5 反空转）。取值远低于今天的真值，只用来证明
#: 「枚举确实跑了」——枚举一旦失灵返回空表，下面所有全称命题都会空转变绿。
NODE_FLOORS = {
    "library": 30,
    "reader": 30,
    "settings": 5,
}

PAGE_FIXTURES = {
    "library": "library_page",
    "reader": "reader_page",
    "settings": "settings_page",
}


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

    problems = _violations(groups)
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
