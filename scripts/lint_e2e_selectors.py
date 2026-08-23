#!/usr/bin/env python3
"""选择器 lint（007 步骤 0.5，三条 lint 里的第一条）。

管的是**谁在用 testid**：E2E 只允许用 data-testid 与 ARIA role/name 定位元素。
另有一条命名 lint（scripts/lint_testid_naming.py）管**谁在发 testid**，两条不重叠。

为什么：Phase 4 会按页重写 DOM。契约是「重设计可以任意改 class、改嵌套、改标签，
**不得改 testid**」。E2E 一旦用 class 或结构定位，Phase 4 的任何布局改动都会推翻整套 E2E
——而那套 E2E 正是 Phase 4 合并的门槛。

允许的选择器字符串形态，只有一种：

    [data-testid="…"]                          单个 testid
    [data-testid="…"][data-book-id="…"]        testid ＋ 另一个 data-* 携带 id

第二种来自设计规格 §4 规则 5 的无界取值约定：书、集合、笔记、会话的 id 不能枚举成 testid，
所以同类元素共用一个字面量 testid，id 由另一个 data-* 属性携带。它不是层级结构选择器
——重设计改不动 data-* 属性。

ARIA 定位走 Playwright 的 get_by_role / get_by_label / get_by_text 等 API，不经过选择器字符串，
本 lint 不拦。get_by_test_id 同理。

被拦的：class 选择器（.foo）、id 选择器（#foo）、标签选择器、后代与子代组合子、
:nth-child 及其同类、xpath=/css=/text= 引擎前缀、以及 .nth(i) 这种按位置定位
——.nth(i) 不在计划原文的三项里，但它坏在同一个地方（重排即失效），所以一并拦。
真要放行某一处，在下面 ALLOW_INLINE 那行注释掉的记号旁写明理由。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_GLOBS = (
    "tests/e2e/**/*.py",
    "tests/e2e/**/*.ts",
    "tests/e2e/**/*.js",
)

# 取这些调用的第一个字符串实参。覆盖 Playwright 的 Python 与 JS 两套 API 名。
LOCATOR_CALL_RE = re.compile(
    r"""\.(?:locator|query_selector_all|query_selector|querySelectorAll|querySelector
        |wait_for_selector|waitForSelector|is_visible|isVisible|click|fill|type|hover
        |press|check|uncheck|select_option|selectOption|text_content|textContent
        |get_attribute|getAttribute|inner_text|innerText|count)\s*\(\s*
        (?P<q>['"])(?P<sel>.*?)(?P=q)""",
    re.VERBOSE,
)
DOLLAR_CALL_RE = re.compile(r"\.\$\$?\s*\(\s*(?P<q>['\"])(?P<sel>.*?)(?P=q)")
NTH_RE = re.compile(r"\.nth\s*\(")

# 允许的整串形态：一个或多个 [data-*="…"]，且其中至少有一个是 data-testid。
ATTR_RE = re.compile(r'\[\s*(data-[a-z0-9-]+)\s*=\s*"[^"]*"\s*\]')
ALLOW_INLINE = "# lint-e2e-selectors: allow"


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def selector_ok(sel: str) -> str | None:
    """返回 None 表示合规，否则返回不合规的原因。"""
    stripped = sel.strip()
    if not stripped:
        return "空选择器"
    for prefix in ("xpath=", "css=", "text=", "//"):
        if stripped.startswith(prefix):
            return f"用了 {prefix} 引擎/路径，只允许 data-testid 属性选择器"
    consumed = ATTR_RE.sub("", stripped)
    if consumed.strip():
        return f"含非 data-* 属性选择器的部分：{consumed.strip()!r}"
    attrs = ATTR_RE.findall(stripped)
    if "data-testid" not in attrs:
        return "没有 data-testid，只有 " + ", ".join(attrs)
    return None


def main() -> int:
    violations: list[tuple[str, int, str, str]] = []
    files = 0
    checked = 0

    for pattern in SCAN_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            files += 1
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(ROOT))
            lines = text.splitlines()

            def allowed(line_no: int) -> bool:
                return ALLOW_INLINE in lines[line_no - 1]

            for m in list(LOCATOR_CALL_RE.finditer(text)) + list(DOLLAR_CALL_RE.finditer(text)):
                checked += 1
                line = line_of(text, m.start("sel"))
                reason = selector_ok(m.group("sel"))
                if reason and not allowed(line):
                    violations.append((rel, line, m.group("sel"), reason))

            for m in NTH_RE.finditer(text):
                line = line_of(text, m.start())
                if not allowed(line):
                    violations.append((rel, line, ".nth(…)", "按位置定位，重排即失效"))

    if files == 0:
        print("选择器 lint：tests/e2e/ 下暂无用例（008／009 会建），本条为 0 违规通过。")
        return 0

    print(f"扫描 {files} 个文件，{checked} 处选择器。")
    if violations:
        print(f"\n违规（{len(violations)} 处）——只允许 data-testid 与 ARIA role/name：")
        for rel, line, sel, reason in violations:
            print(f"  {rel}:{line}  {sel!r}\n      {reason}")
        print(f"\n  确有必要放行的，在该行末尾加 `{ALLOW_INLINE}` 并写明理由。")
        return 1

    print("选择器 lint 通过：0 处违规。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
