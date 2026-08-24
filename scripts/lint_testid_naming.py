#!/usr/bin/env python3
"""命名 lint（007 步骤 0.5，三条 lint 里的第二条）。

管的是**谁在发 testid**：模板与原型里每一个 data-testid 的值都必须匹配 canonical 正则。
另有一条选择器 lint（scripts/lint_e2e_selectors.py）管**谁在用 testid**，两条不重叠。

为什么光有选择器 lint 不够：选择器 lint 全绿，模板里照样可以新增 `reader-search-hit`
这种名字，命名方案随即失守。

四种形态都要扫，少一种就有漏网之鱼：

  1. data-testid="字面量"          —— 最常见的一种
  2. testId="字面量"               —— Sheet 组件把 prop 透传成 data-testid。
                                     原型的 134 个统计漏掉的正是这 4 个，见
                                     contracts/testid-rename-map.md §1
  3. 标识符含 TESTID 的 const 表里的字面量 —— 规格 §4 规则 5 说的「改静态映射表」。
                                     值在表里，属性上写的是 {表[key]}，形态 1 扫不到
  4. data-testid={表达式}          —— 表达式里不得出现 + 或模板字面量。这是规则 5
                                     「不得由变量拼接或模板插值产生」的机器化形式

⚠️ 显式点名：那 24 个带 `reader-` / `library-` 前缀的旧名（`reader-shell`、`library-sidebar`
   一类）**是不合规的**。它们形似合规——有前缀、有连字符——但用的是页面全称而不是
   `rd-` / `lib-`，批量改名时最容易被当成「已经对了」跳过。正则天然把它们判为违规，
   这正是要的效果；本注释存在的意义是防止后来者看到 lint 报它们就往白名单里加。
   全部 24 个的新名见 contracts/testid-rename-map.md。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_GLOBS = (
    "designs/reader-pro-next/**/*.jsx",
    "designs/reader-pro-next/**/*.html",
    "src/reader3_app/web/templates/*.html",
)

# canonical 正则。唯一真相源是 plan-tech-stack-migration.md §6 步骤 0.5 的 regex 代码块，
# 从那个代码块复制，不要从它上面的 Markdown 表格里复制（表格里的 | 被转义成 \|）。
CANONICAL = re.compile(r"^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$")

ATTR_LITERAL_RE = re.compile(r'data-testid\s*=\s*"([^"]*)"')
PROP_LITERAL_RE = re.compile(r'\btestId\s*=\s*"([^"]*)"')
ATTR_EXPR_RE = re.compile(r"data-testid\s*=\s*\{([^}]*)\}")
TESTID_TABLE_RE = re.compile(r"const\s+\w*TESTID\w*\s*=\s*\{(.*?)\n\};", re.DOTALL)
TABLE_VALUE_RE = re.compile(r':\s*"([^"]*)"')


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def main() -> int:
    bad_names: list[tuple[str, int, str, str]] = []
    bad_exprs: list[tuple[str, int, str]] = []
    files = 0
    names: set[str] = set()

    for pattern in SCAN_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            files += 1
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(ROOT))

            found: list[tuple[int, str, str]] = []
            for m in ATTR_LITERAL_RE.finditer(text):
                found.append((m.start(1), m.group(1), "data-testid"))
            for m in PROP_LITERAL_RE.finditer(text):
                found.append((m.start(1), m.group(1), "testId prop"))
            for table in TESTID_TABLE_RE.finditer(text):
                for m in TABLE_VALUE_RE.finditer(table.group(1)):
                    found.append((table.start(1) + m.start(1), m.group(1), "静态映射表"))

            for pos, value, kind in found:
                names.add(value)
                if not CANONICAL.match(value):
                    bad_names.append((rel, line_of(text, pos), value, kind))

            for m in ATTR_EXPR_RE.finditer(text):
                expr = m.group(1)
                if "+" in expr or "`" in expr:
                    bad_exprs.append((rel, line_of(text, m.start(1)), expr.strip()))

    print(f"扫描 {files} 个文件，{len(names)} 个唯一 testid 名。")

    if bad_names:
        print(f"\n不合规的 testid 名（{len(bad_names)} 处）——正则 {CANONICAL.pattern}：")
        for rel, line, value, kind in bad_names:
            hint = ""
            if value.startswith(("reader-", "library-")):
                hint = "  ← 页面全称前缀，不是 rd- / lib-；这类是要改的，不是要放行的"
            print(f"  {rel}:{line}  {value!r}  [{kind}]{hint}")

    if bad_exprs:
        print(f"\n拼接出来的 testid（{len(bad_exprs)} 处）——违反设计规格 §4 规则 5：")
        for rel, line, expr in bad_exprs:
            print(f"  {rel}:{line}  data-testid={{{expr}}}")
        print("  有界取值改静态映射表，无界 id 改「字面量 testid ＋ 另一个 data-* 携带 id」。")

    if bad_names or bad_exprs:
        return 1

    print("命名 lint 通过：0 处违规。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
