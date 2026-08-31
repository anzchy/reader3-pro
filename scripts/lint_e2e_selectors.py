#!/usr/bin/env python3
"""选择器 lint（007 步骤 0.5，三条 lint 里的第一条）。

管的是**谁在用 testid**：E2E 只允许用 data-testid 与 ARIA role/name 定位元素。
另有一条命名 lint（scripts/lint_testid_naming.py）管**谁在发 testid**，两条不重叠。

为什么：Phase 4 会按页重写 DOM。契约是「重设计可以任意改 class、改嵌套、改标签，
**不得改 testid**」。E2E 一旦用 class 或结构定位，Phase 4 的任何布局改动都会推翻整套 E2E
——而那套 E2E 正是 Phase 4 合并的门槛。

允许的选择器字符串形态，只有一种：

    [data-testid="…"]                          单个 testid
    [data-testid="…"][data-book-id="…"]        testid ＋ 一个闭合清单里的判别位

第二种的**适用范围**由 docs/adr/0014-bounded-testid-enumeration.md 定义（它取代了 ADR-0013
里的对应子命题）：判别位只能是 ALLOWED_DISCRIMINATORS 那八个携带用户数据 id 的属性
——取值无界、编译期枚举不出来，才配用复合形态。取值有界的同类元素（弹层、面板）一律
各有自己唯一的 testid 字面量，data-modal / data-sheet 已从契约里删除。
复合形态不是层级结构选择器——重设计改不动 data-* 属性。

ARIA 定位走 Playwright 的 get_by_role / get_by_label / get_by_text 等 API，不经过选择器字符串，
本 lint 不拦。get_by_test_id 同理。

被拦的：class 选择器（.foo）、id 选择器（#foo）、标签选择器、后代与子代组合子、
:nth-child 及其同类、xpath=/css=/text= 引擎前缀、以及 .nth(i) 这种按位置定位
——.nth(i) 不在计划原文的三项里，但它坏在同一个地方（重排即失效），所以一并拦。
真要放行某一处，在下面 ALLOW_INLINE 那行注释掉的记号旁写明理由。

``frame_locator`` 也在扫描之列（2026-08-26 补）。它此前不在名单里，因为写这条 lint
时 tests/e2e/ 还是空的，没人写过跨 iframe 的定位。009 的 harness spike 一落地就
暴露了这个洞：进 epub.js 的 iframe 要给一个 iframe 元素的选择器，那一处天然拿不到
testid，本该被拦下来**显式放行**，而不是从没被看见过。
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
    r"""\.(?:locator|frame_locator|frameLocator
        |query_selector_all|query_selector|querySelectorAll|querySelector
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

ADR_0014 = "docs/adr/0014-bounded-testid-enumeration.md"

# 可以当判别位的属性，闭合清单，唯一定义处。取自 ADR-0014 §Decision Outcome：
# 只有取值**无界**（来自用户数据、编译期枚举不出来）的 id 才配用复合形态。
# 要加第九项：先改 ADR，再改这里，并在注释里说明为何该取值集合无法枚举。
ALLOWED_DISCRIMINATORS = {
    "data-book-id",
    "data-collection-id",
    "data-note-id",
    "data-annotation-id",
    "data-conversation-id",
    "data-provider",
    "data-section",
    # data-file-href 全仓当前只有 1 处使用（ADR-0014 §Neutral），仍然保留：
    # 它是清单里最像「没人用，删了吧」的一项，而删掉它并不会让判据变清楚，
    # 只会让下一处文件路径定位重新变成一次要翻 ADR 的争论。
    "data-file-href",
}


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
    # 顺序有意为之：先判「有没有 data-testid」，再判「判别位准不准」。反过来会对一条
    # 压根没有 testid 的选择器报「判别位不在闭合清单内」，把人指向错的地方。
    # 在调用期读模块全局，不捕获进默认参数 —— 闭合清单只有一个定义处。
    allowed = ALLOWED_DISCRIMINATORS
    for attr in attrs:
        if attr == "data-testid":
            continue
        if attr not in allowed:
            return (
                f"判别位 {attr} 不在闭合清单内 —— 见 {ADR_0014}；"
                "新增需改 lint 的 ALLOWED_DISCRIMINATORS 并说明为何该取值集合无法枚举。"
            )
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
