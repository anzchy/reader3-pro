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

扫描范围有两档（M4）：`SCAN_GLOBS`（原型 ＋ 模板）走形状 ＋ 唯一性；
`SHAPE_ONLY_SCAN_GLOBS`（`src/reader3_app/web/static/**/*.js`）**只走形状**，理由写在
那个常量上方。JS 侧此前完全在扫描范围之外，等于没有任何东西在管它发出去的名字长什么样。

除形状之外还管**同文件内的字面量唯一性**（裁决见 docs/adr/0014-bounded-testid-enumeration.md）：
有界集合的每个成员各有自己唯一的 testid，同一个文件里同一个字面量出现两次即违规。
这只是唯一性的静态近似——真正要保证的是渲染后 DOM 里的唯一性，静态扫描证明不了：
跨文件汇入同一页的重名看不见，互斥分支里的合法同名会被误判。后者以
`UNIQUENESS_EXEMPTIONS` 显式登记，不靠合并分支来迎合 lint；登记表悬空（重名已经没了）
同样判违规，免得豁免变成永久的静默通行证。
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_GLOBS = (
    "designs/reader-pro-next/**/*.jsx",
    "designs/reader-pro-next/**/*.html",
    "src/reader3_app/web/templates/*.html",
)

# M4：前端 JS 也在发 testid（当时 `library.js` 的状态 pill——013 起已迁到 TS、`settings.js` 的 provider 卡片、
# `search.js` / `notes-panel.js` 的动态列表），在此之前**没有任何东西在管这些名字的形状**。
# 它们进扫描范围，但**只参与 CANONICAL 形状检查，不参与同文件唯一性检查**：
#   * JS 里同一个 testid 字面量「在 `const` 表里定义一次、在别处 `setAttribute` 再引用
#     一次」是完全正常的写法，把唯一性套上去只会制造假阳性，逼人去登记豁免——豁免多了
#     这条检查本身就废了（ADR-0014 的 Revisit When 第二条：超过 3 条即为信号）。
#   * 而唯一性的**真正**保证已经由 `tests/e2e/test_testid_dom_uniqueness.py` 在真浏览器
#     里承担了：它扫的是渲染后的 DOM，而 DOM 唯一性才是 Playwright strict 模式真正在乎
#     的东西。静态近似在 JS 上尤其不准（一个字面量渲成 N 个节点、互斥分支各写一次），
#     运行期断言才是它该待的地方。
#
# `frontend/src/**/*.ts`（013 WI-9 验收 A9.13，用户裁定 D6）：TS 源码根同样在发 testid，
# 同样只走形状——理由与上面 JS 那条完全相同。少了它，WI-3 #1、WI-12 #3、WI-13 #6 在 TS
# 上都是空过。`frontend/tests/` 不在内：测试是 testid 的**使用方**，归选择器 lint 管。
SHAPE_ONLY_SCAN_GLOBS = (
    "src/reader3_app/web/static/**/*.js",
    "frontend/src/**/*.ts",
)

# vendor 是第三方 JS（epub.js 等），不是我们发的 testid，扫它只会扫出别人的代码。
# dist 是 Vite 产物（压缩后的 frontend/src）：它发的名字已经在源码那一侧查过，
# 压缩又会把 `*TESTID*` 常量名改掉——在产物上查只会得到更少、更难读的命中。
SHAPE_ONLY_EXCLUDE = (
    "src/reader3_app/web/static/vendor/",
    "src/reader3_app/web/static/dist/",
)

# canonical 正则。这里就是唯一真相源（裁决见 docs/adr/0013-testid-invariant.md）——
# 文档一律链接到这个常量，不要在任何 Markdown 表格里另抄一份（表格里的 | 会被转义成 \|）。
CANONICAL = re.compile(r"^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$")

ATTR_LITERAL_RE = re.compile(r'data-testid\s*=\s*"([^"]*)"')
PROP_LITERAL_RE = re.compile(r'\btestId\s*=\s*"([^"]*)"')
ATTR_EXPR_RE = re.compile(r"data-testid\s*=\s*\{([^}]*)\}")
# 收尾的 `};` 允许有缩进：原型的表都在模块顶层（`};` 顶格），但（013 前的）`library.js` /
# `library-chat.js` 的表包在 IIFE 里，收尾写的是 `  };`。要求顶格等于对这些表**视而不见**
# ——而看不见的表照样让 lint 退出 0，是最坏的一种「通过」。
TESTID_TABLE_RE = re.compile(r"const\s+\w*TESTID\w*\s*=\s*\{(.*?)\n[ \t]*\};", re.DOTALL)
TABLE_VALUE_RE = re.compile(r':\s*"([^"]*)"')
# DOM API 的两种写法（013 WI-9，A9.13）：`el.setAttribute("data-testid", <expr>)` 与
# `el.dataset.testid = <expr>`。静态 JS 与 TS 都这么发 testid，此前只有 JSX/模板的属性形态
# 被扫到。<expr> 是单个字符串字面量 → 走形状检查；含 `+` 或模板插值 → 按拼接判违规
# （规格 §4 规则 5）；其余（标识符、`TABLE.key` 查表）放行——表里的值由 TESTID 表那条管。
# <expr> 里的字符串字面量整段吞下：字面量内含 `)`（如 `")"`）时，`[^)]*` 会在字面量中间截断，
# 截出的半截表达式既非字面量也非拼接，于是被放行——一个不合形状的名字就此漏检（013 WI-13
# 期间由 C9.16 的性质测试随机撞出）。
SET_ATTR_RE = re.compile(
    r"""\.setAttribute\(\s*(["'])data-testid\1\s*,\s*"""
    r"""(?P<expr>(?:"[^"\n]*"|'[^'\n]*'|`[^`\n]*`|[^)"'`])*?)\s*\)"""
)
# 同理，`dataset.testid = ';'` 的 `[^;\n]*` 会在字面量里的 `;` 处截断。
DATASET_RE = re.compile(
    r"""\.dataset\.testid\s*=(?!=)\s*(?P<expr>(?:"[^"\n]*"|'[^'\n]*'|`[^`\n]*`|[^;\n"'`])*?)\s*(?:;|$)""",
    re.MULTILINE,
)
STRING_LITERAL_RE = re.compile(r"""^(?:"([^"\\]*)"|'([^'\\]*)'|`([^`\\$]*)`)$""")

ADR_0014 = "docs/adr/0014-bounded-testid-enumeration.md"

# 同文件内重名的显式豁免登记表：{(仓库相对 POSIX 路径, testid 字面量): 理由}。
# 只登记「至多渲染一个」的互斥分支，别拿它掩盖真重名——那是把 lint 关掉，不是放行一条。
# 悬空的条目（该文件里已无该重名）会被报为违规，请删除而不是留着。
# 超过 3 条就说明静态近似与真实需求偏离太远，见 ADR-0014 的 Revisit When。
UNIQUENESS_EXEMPTIONS: dict[tuple[str, str], str] = {
    (
        "designs/reader-pro-next/settings.jsx",
        "set-provider-result",
    ): "test === \"ok\" / test === \"fail\" 两条互斥分支，至多渲染一个",
}


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def classify_expr(expr: str) -> tuple[str, str | None]:
    """DOM API 形态里的 <expr>：("literal", 值) / ("concat", None) / ("opaque", None)。"""
    m = STRING_LITERAL_RE.match(expr)
    if m:
        return "literal", next(g for g in m.groups() if g is not None)
    if "+" in expr or "`" in expr:
        return "concat", None
    return "opaque", None


def main(argv: list[str] | None = None) -> int:
    # `--root` (013 WI-9)：反例播种进 tmp 副本，不碰真实仓库。不传 argv 即不带参数
    # ——不是 sys.argv，pytest 底下那是 pytest 自己的参数。
    parser = argparse.ArgumentParser(description="testid 命名 lint")
    parser.add_argument("--root", type=Path, default=None, help="要扫的仓库根（默认本检出）")
    args = parser.parse_args(argv or [])
    root = args.root.resolve() if args.root else ROOT
    # 形状违规按 (文件, 字面量) 分组：同一个坏名字出现两次是一条待办，不是两条。
    bad_names: dict[tuple[str, str], tuple[list[int], list[str]]] = {}
    bad_exprs: list[tuple[str, int, str]] = []  # (文件, 行, 展示用的表达式)
    files = 0
    names: set[str] = set()
    # 唯一性统计的键是 (文件, 字面量)——跨文件同名不算重名，这是 ADR-0014 明写的盲区。
    occurrences: dict[tuple[str, str], list[int]] = defaultdict(list)

    # (路径, 是否参与唯一性检查)。两条 glob 家族的差别只在这个布尔上，扫描与形状检查
    # 的代码是同一份——分成两个循环写就是两份会各自漂移的 parser。
    targets: list[tuple[Path, bool]] = []
    for pattern in SCAN_GLOBS:
        for path in sorted(root.glob(pattern)):
            targets.append((path, True))
    for pattern in SHAPE_ONLY_SCAN_GLOBS:
        for path in sorted(root.glob(pattern)):
            if any(x in path.relative_to(root).as_posix() for x in SHAPE_ONLY_EXCLUDE):
                continue
            targets.append((path, False))

    for path, check_uniqueness in targets:
        files += 1
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()

        found: list[tuple[int, str, str]] = []
        for m in ATTR_LITERAL_RE.finditer(text):
            found.append((m.start(1), m.group(1), "data-testid"))
        for m in PROP_LITERAL_RE.finditer(text):
            found.append((m.start(1), m.group(1), "testId prop"))
        for table in TESTID_TABLE_RE.finditer(text):
            for m in TABLE_VALUE_RE.finditer(table.group(1)):
                found.append((table.start(1) + m.start(1), m.group(1), "静态映射表"))
        for regex, kind in ((SET_ATTR_RE, "setAttribute"), (DATASET_RE, "dataset.testid")):
            for m in regex.finditer(text):
                verdict, value = classify_expr(m.group("expr"))
                if verdict == "literal":
                    found.append((m.start("expr"), value, kind))
                elif verdict == "concat":
                    bad_exprs.append((rel, line_of(text, m.start("expr")), f"{kind} {m.group('expr').strip()}"))

        for pos, value, kind in found:
            line = line_of(text, pos)
            names.add(value)
            if check_uniqueness:
                # 四种形态汇进同一个计数器：分形态各自查重会漏掉跨形态的重名。
                occurrences[(rel, value)].append(line)
            if not CANONICAL.match(value):
                lines, kinds = bad_names.setdefault((rel, value), ([], []))
                lines.append(line)
                if kind not in kinds:
                    kinds.append(kind)

        for m in ATTR_EXPR_RE.finditer(text):
            expr = m.group(1)
            if "+" in expr or "`" in expr:
                bad_exprs.append((rel, line_of(text, m.start(1)), f"data-testid={{{expr.strip()}}}"))

    # 豁免只压住唯一性发现，压不住形状检查——那是登记者从未打算授予的提权。
    duplicates = {key: sorted(lines) for key, lines in occurrences.items() if len(lines) > 1}
    exempted = {key for key in duplicates if key in UNIQUENESS_EXEMPTIONS}
    reported_dups = {key: lines for key, lines in duplicates.items() if key not in exempted}
    # 登记表绑定的是本仓库（ROOT）的文件。--root 指向别的树（tmp 副本、夹具）时，那棵树
    # 里根本没有的登记文件不归它负责；只有那棵树里确实存在的登记文件才参与悬空判定。
    # 扫描本仓库时照旧：登记文件缺失即悬空（U17）。
    foreign = root.resolve() != Path(ROOT).resolve()
    dangling = sorted(
        key
        for key in UNIQUENESS_EXEMPTIONS
        if key not in duplicates and not (foreign and not (root / key[0]).exists())
    )

    print(f"扫描 {files} 个文件，{len(names)} 个唯一 testid 名。")

    if bad_names:
        print(f"\n不合规的 testid 名（{len(bad_names)} 处）——正则 {CANONICAL.pattern}：")
        for (rel, value), (lines, kinds) in sorted(bad_names.items()):
            hint = ""
            if value.startswith(("reader-", "library-")):
                hint = "  ← 页面全称前缀，不是 rd- / lib-；这类是要改的，不是要放行的"
            where = ",".join(str(n) for n in sorted(lines))
            print(f"  {rel}:{where}  {value!r}  [{'/'.join(kinds)}]{hint}")

    if bad_exprs:
        print(f"\n拼接出来的 testid（{len(bad_exprs)} 处）——违反设计规格 §4 规则 5：")
        for rel, line, expr in bad_exprs:
            print(f"  {rel}:{line}  {expr}")
        print("  有界取值改静态映射表，无界 id 改「字面量 testid ＋ 另一个 data-* 携带 id」。")

    if reported_dups:
        print(f"\n同文件内重名的 testid（{len(reported_dups)} 处）——ADR-0014 的唯一性检查：")
        for (rel, value), lines in sorted(reported_dups.items()):
            where = ", ".join(str(n) for n in lines)
            print(f"  {rel}  {value!r}  ×{len(lines)}  行 {where}")
        print("  这只是静态近似：跨文件汇入同一页的重名看不见。互斥分支里的合法同名请在")
        print(f"  UNIQUENESS_EXEMPTIONS 登记，理由见 {ADR_0014}。")

    if dangling:
        print(f"\n失效的唯一性豁免（{len(dangling)} 条）——登记了但该文件里已无该重名，请删除该条：")
        for rel, value in dangling:
            print(f"  {rel}  {value!r}")

    if bad_names or bad_exprs or reported_dups or dangling:
        return 1

    print("命名 lint 通过：0 处违规。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
