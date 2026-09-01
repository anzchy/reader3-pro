"""WI-4／WI-5：原型里的 `MODAL_TESTIDS` 与 `RD_SHEET_TESTIDS` 两张有界枚举表。

矩阵：`.claude/tdd-guardian/tests-20260831-131500.md` 的 P1–P16（WI-4）与 Q1–Q9（WI-5）。
裁决：`docs/adr/0014-bounded-testid-enumeration.md`。
风格先例：`tests/unit/test_coverage_gate_failclosed.py`。

被测的是两个**静态文本产物**：`designs/reader-pro-next/components.jsx` 与
`designs/reader-pro-next/reader.jsx`。没有 HTTP、没有浏览器、没有 `books/`。本文件里
的每一处读盘都是 `read_text()`，唯一的写盘是零。`tests/conftest.py` 提醒过
`process_epub()` 会对输出目录 `shutil.rmtree()`——这里既不 import `reader3.py`，也不碰
`books/`。

**为什么要 import lint 的正则而不是抄一份**（P5/P8/P12/P14/P15/Q2/Q6/Q8）：
`scripts/lint_testid_naming.py` 里的 `CANONICAL` / `ATTR_LITERAL_RE` / `PROP_LITERAL_RE`
/ `ATTR_EXPR_RE` / `TESTID_TABLE_RE` / `TABLE_VALUE_RE` 是 ADR-0013/0014 指定的唯一定义
点。测试自己抄一份，就会出现「测试看得见、lint 看不见」的表——那 70 个新字面量一个都
不会被检查。**P15 就是把两套 parser 钉在一起的那一条**。

**反空转与计数断言——对矩阵 §0.5 的一次有意偏离**：§0.5 要求凡「正则捞一把再断言」的用
例都先钉住**精确**条数，只给 P1／P3／P8／P10／Q5／Q6 六处开了下界白名单。本文件**不再照
此默认**。理由是那些精确计数在同时干**两件事**：

  1. **反空转**——证明正则真的捞到了东西，否则后面的 `assert offenders == []` 是空真。
     这件事是**永久**的。
  2. **越界闸门**——「WI-4 改不动这个数」。这件事的作用域是**本批次**，WI-4 落地即到期。

把两件事写成同一条 `==`，等于为一个已过期的收益永久付代价：任何与该断言无关的前端改动
都会让它变红，而红因与它守的不变式无关。这已经实际发生过两次。

**新的分界线**：

  * 数的是**本文件亲手维护的内容**——`MODAL_TESTIDS` 14×5=70、`SHARED_TESTIDS` 3×10=30、
    components.jsx 三张兄弟表的 9——**保留 `==`**。这种数只在有人**故意**编辑那张表时才
    变，那正是应该被看见的时刻。
  * 数的是**顺带清点的存量**——仓库文件里今天恰好有几处字面量、几个表块、几个标签——
    **这个数不进断言**。按优先级选治法：**关系断言 ＞ 删除 ＞ 下界**。
      - **关系断言**（P11／P15）：把主张直接写出来。P15 断「生产 `TESTID_TABLE_RE` 看到的
        表名集合 == 一个独立的、更宽松的声明扫描看到的集合」，P11 断「ConfirmModal 内部
        自己渲染的那个 `<Modal>` 确实落在被检查的标签集合里且带 `modal=`」。两条都比原来
        的 `==5` / `==7` / `==13` **严格更强**：新加一张表／一个弹层调用点时两边同步，不
        误报；而生产正则漏一张表、内部透传漏一个 prop 时照样红。
      - **删除**（P12 原来的 `len(total) == 146`）：在各分量已各自单断之后是恒真的，独立信
        息量为零。
      - **下界**（P12 的 `C_attr`、P15 的 `ctotal` / `rtotal`，以及原有的 P1／P3／P8／P10／
        Q5／Q6）：只承担反空转，取一个**远离今天真值**的数——删掉语料大半仍然通过，正则
        真坏了必然失败。下界还必须**非空转**：P15 里同一函数已经单断了 `modal_values == 70`
        与 `sheet_values == 5`，所以 `ctotal` / `rtotal` 的下界是**减掉这两个分量之后**才取
        的，否则那条下界会被前一条等式蕴含，成为一条恒真的新空转。**真值不写进注释**：那种
        注释无人维护、已经漂过（`T11_FILE_FLOOR` 的注释记 34、实测 35），要看真值就让断言
        消息把它报出来。

**Mock 边界**：除 Q9 只 monkeypatch `SCAN_GLOBS` 外，全部为 none——真实仓库文件，只读。
"""

from __future__ import annotations

import importlib.util
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROTO_DIR = REPO_ROOT / "designs" / "reader-pro-next"
LINT_PATH = REPO_ROOT / "scripts" / "lint_testid_naming.py"


def _load_lint():
    """脚本不是包，按路径加载（与 test_coverage_gate_failclosed.py 同一套写法）。"""
    spec = importlib.util.spec_from_file_location("testid_naming_under_test", LINT_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {LINT_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINT = _load_lint()


def _read(name: str) -> str:
    path = PROTO_DIR / name
    assert path.is_file(), f"原型文件不存在：{path}"
    return path.read_text(encoding="utf-8")


def _jsx_files() -> List[Path]:
    return sorted(PROTO_DIR.glob("*.jsx"))


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _extract(pattern: "re.Pattern[str]", text: str, expect_n: int, what: str) -> List[str]:
    """§0.5 的反空转闸门：先断条数，再把结果交出去。"""
    hits = pattern.findall(text)
    assert len(hits) == expect_n, (
        f"{what}：期望恰好 {expect_n} 处，实到 {len(hits)} 处 → {hits}"
    )
    return hits


def _extract_floor(pattern: "re.Pattern[str]", text: str, floor: int, what: str) -> List[str]:
    hits = pattern.findall(text)
    assert len(hits) >= floor, f"{what}：期望至少 {floor} 处，实到 {len(hits)} 处 → {hits}"
    return hits


# --------------------------------------------------------------------------
# 共享 parse helper（矩阵「Shared parse helper」一节，逐字照抄的三条正则）
# --------------------------------------------------------------------------

TABLE_BLOCK_RE = re.compile(r"const\s+MODAL_TESTIDS\s*=\s*\{(?P<body>.*?)\n\};", re.DOTALL)
SHEET_BLOCK_RE = re.compile(r"const\s+RD_SHEET_TESTIDS\s*=\s*\{(?P<body>.*?)\n\};", re.DOTALL)
SHARED_BLOCK_RE = re.compile(r"const\s+SHARED_TESTIDS\s*=\s*\{(?P<body>.*?)\n\};", re.DOTALL)
# key 的引号可选（revision 2）：reindex / conversations / cache 三个键是合法标识符，
# 本仓库的行文习惯就是裸写；SHARED_TESTIDS 的三个层级键（lib / rd / set）同理。
ENTRY_RE = re.compile(r'"?(?P<key>[a-z0-9-]+)"?\s*:\s*\{(?P<fields>[^}]*)\}')
FIELD_RE = re.compile(r'(?P<field>\w+)\s*:\s*"(?P<value>[^"]*)"')

# `\n};` 这个终止符是**故意**保留的：生产的 TESTID_TABLE_RE 用的就是它。测试能找到而
# lint 找不到的表，正是 P15 要堵的洞。


def _parse_block(
    block_re: "re.Pattern[str]", text: str, expect_entries: int, label: str
) -> Dict[str, Dict[str, str]]:
    blocks = list(block_re.finditer(text))
    assert len(blocks) == 1, (
        f"{label}：期望恰好 1 个 `const … = {{ … \\n}};` 块，实到 {len(blocks)} 个。"
        f"（0 个通常意味着这张表还不存在，或它的终止符生产的 TESTID_TABLE_RE 也认不出——见 P15）"
    )
    body = blocks[0].group("body")
    entries: Dict[str, Dict[str, str]] = {}
    for m in ENTRY_RE.finditer(body):
        entries[m.group("key")] = {
            f.group("field"): f.group("value") for f in FIELD_RE.finditer(m.group("fields"))
        }
    assert len(entries) == expect_entries, (
        f"{label}：期望 {expect_entries} 个条目，实到 {len(entries)} 个 → {sorted(entries)}"
    )
    return entries


def modal_table() -> Dict[str, Dict[str, str]]:
    return _parse_block(TABLE_BLOCK_RE, _read("components.jsx"), 14, "MODAL_TESTIDS")


def sheet_table() -> Dict[str, Dict[str, str]]:
    return _parse_block(SHEET_BLOCK_RE, _read("reader.jsx"), 4, "RD_SHEET_TESTIDS")


# --------------------------------------------------------------------------
# 锚定后的正则（revision 2 的三处修正）
# --------------------------------------------------------------------------

# `\bmodal\s*=\s*"` 会误吞 aria-modal="…"：`-` 与 `m` 之间恰好是一个词边界。
# reader.jsx 今天就有 3 处 aria-modal。后视断言 (?<![-\w]) 把它们排除。
MODAL_PROP_RE = re.compile(r'(?<![-\w])modal\s*=\s*"([^"]*)"')
# 同理：`\w` 不匹配 `-`，非锚定形态会从 `data-testid=` 里切出碎片 `testid`。
PROP_NAME_RE = re.compile(r"(?<![\w-])(\w*[Tt]est[Ii]d)\s*=")

PAGE_PROP_RE = re.compile(r"(?<![\w.$-])page\s*=(?!=)")
NAME_PROP_RE = re.compile(r"(?<![\w.$-])name\s*=(?!=)")
MODAL_ANY_PROP_RE = re.compile(r"(?<![\w.$-])modal\s*=(?!=)")
DATA_MODAL_ATTR_RE = re.compile(r"(?<![\w-])data-modal\s*=")

# 14 个弹层的所属页面，从计划逐字誊来：lib×7 / rd×4 / set×3。
PAGE_OF: Dict[str, str] = {
    "add-books": "lib",
    "index-errors": "lib",
    "create-collection": "lib",
    "rename-collection": "lib",
    "delete-collection": "lib",
    "clean-collection": "lib",
    "add-to-collection": "lib",
    "note-editor": "rd",
    "clear-conversation": "rd",
    "delete-note": "rd",
    "notes-review": "rd",
    "reindex": "set",
    "conversations": "set",
    "cache": "set",
}
MODAL_KEYS = set(PAGE_OF)
MODAL_FIELDS = {"root", "close", "cancel", "primary", "body"}
# 唯一的保留名例外，ADR-0014 说它是**唯一**一个。
RESERVED_ROOT = {"note-editor": "rd-note-editor"}


# --------------------------------------------------------------------------
# JSX 开标签扫描（P10 / P11）
# --------------------------------------------------------------------------

TAG_START_RE = re.compile(r"<(Modal|ConfirmModal|LiveRegion|Brand|ThemeToggle)\b")


def _jsx_tags(text: str, names: Tuple[str, ...] = ()) -> List[str]:
    """切出 JSX 开标签，**不能**在第一个 `>` 处截断。

    矩阵给的 `<(…)\\b.*?(?=/>|>)` 会在 `onClose={() => …}` 的箭头处断掉——那个 `>`
    在花括号里。改成一个记录花括号深度与字符串状态的扫描器：只在深度 0 的 `>` 处收
    尾。这是同一条断言的正确实现，不是放宽。
    """
    tags: List[str] = []
    for m in TAG_START_RE.finditer(text):
        if names and m.group(1) not in names:
            continue
        i = m.end()
        depth = 0
        quote = ""
        while i < len(text):
            ch = text[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in "\"'`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                break
            i += 1
        assert i < len(text), f"标签未闭合：{text[m.start():m.start() + 80]!r}"
        tags.append(text[m.start() : i + 1])
    return tags


def _slice_body(text: str, anchor: str, end_re: "re.Pattern[str]", label: str) -> str:
    """从 `anchor` 切到 `end_re` 的下一处命中，并做切片类用例的反空转守卫。"""
    assert text.count(anchor) == 1, (
        f"{label}：`{anchor}` 期望恰好出现 1 次，实到 {text.count(anchor)} 次"
    )
    start = text.index(anchor)
    m = end_re.search(text, start + len(anchor))
    assert m is not None, f"{label}：从 `{anchor}` 起找不到函数体的结束标记"
    body = text[start : m.end()]
    assert body.strip(), f"{label}：切出来的函数体是空的"
    assert len(body) < len(text), f"{label}：切片等于整份文件，切割没生效"
    return body


NEXT_TOP_BRACE_RE = re.compile(r"^\}", re.MULTILINE)
NEXT_TOP_FUNCTION_RE = re.compile(r"^function ", re.MULTILINE)


def _destructured_names(body: str, func: str) -> set:
    m = re.search(
        r"function " + func + r"\(props\)\s*\{\s*const\s*\{([^}]*)\}\s*=\s*props;",
        body,
        re.DOTALL,
    )
    assert m is not None, f"{func}：找不到 `const {{ … }} = props;` 解构行"
    return {n.strip() for n in m.group(1).split(",") if n.strip()}


# P15 的独立对照扫描：只认**声明头**，不关心终止符长什么样。它比生产的 TESTID_TABLE_RE
# 宽松得多，因此「生产正则能看到的表」必须是它的子集；两边不等就说明生产正则漏了表。
# 故意不复用生产常量——复用就成了同义反复，两套 parser 也就钉不到一起了。
TABLE_DECL_RE = re.compile(r"const\s+(\w*TESTID\w*)\s*=\s*\{")


def _declared_table_names(text: str) -> set:
    return set(TABLE_DECL_RE.findall(text))


def _assert_production_regex_sees_every_table(text: str, label: str) -> List[Tuple[str, "re.Match[str]"]]:
    """P15 的关系断言：生产正则找到的表名集合 == 独立声明扫描找到的表名集合。"""
    blocks = _table_blocks(text)
    seen = {name for name, _ in blocks}
    declared = _declared_table_names(text)
    assert seen == declared, (
        f"{label}：生产的 TESTID_TABLE_RE 与独立声明扫描看到的表不一致。\n"
        f"  生产正则漏掉（lint 在这些表里看到 0 个值，值一个都不会被校验）：{sorted(declared - seen)}\n"
        f"  只有生产正则看得到（通常意味着块边界串了）：{sorted(seen - declared)}\n"
        f"  两边都看得到：{sorted(seen & declared)}"
    )
    assert declared, f"{label}：一张 testid 表都没扫到，两个正则同时空转了"
    return blocks


def _table_blocks(text: str) -> List[Tuple[str, "re.Match[str]"]]:
    """用**生产的** TESTID_TABLE_RE 迭代，顺带把声明名捞出来。"""
    out: List[Tuple[str, "re.Match[str]"]] = []
    for m in LINT.TESTID_TABLE_RE.finditer(text):
        decl = re.match(r"const\s+(\w+)", m.group(0))
        assert decl is not None, f"表块开头不是 `const 名字`：{m.group(0)[:60]!r}"
        out.append((decl.group(1), m))
    return out


# ==========================================================================
# WI-4 — MODAL_TESTIDS 及其调用点
# ==========================================================================


def test_p1_data_modal_is_gone_from_every_prototype_jsx():
    """P1：`data-modal` 从 `designs/reader-pro-next/*.jsx` 里全部消失。

    下界理由（§0.5）：(a) 原型目录会独立于本批次增减文件；(b) 断言是对所有文件的全称
    命题；(c) 4 是今天的真实文件数，下界掉不到 0 个文件。

    数的是**属性**形态 `data-modal=`，不是裸字符串 `data-modal`：矩阵给的今日基数是 5
    （components.jsx:182,186,191,192,206），而裸字符串在同一份文件里还有第 6 处——:163
    那句 ADR 理由注释「判别位 data-modal 已删除」，正是 **P16 明文要求保留**的那一句。
    照裸字符串读，P1 与 P16 就互相排斥；照属性形态读，两条同时成立，且这一条依然拦得住
    「把判别位加回来」的那种改动，这才是它存在的理由。
    """
    files = _jsx_files()
    assert len(files) >= 4, f"原型 jsx 文件期望至少 4 个，实到 {len(files)} 个：{files}"

    offenders: List[Tuple[str, int, str]] = []
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if DATA_MODAL_ATTR_RE.search(line):
                offenders.append((_rel(path), lineno, line.strip()))

    assert offenders == [], (
        "判别位 data-modal 必须删除（ADR-0014）；仍有 "
        f"{len(offenders)} 处：\n" + "\n".join(f"  {r}:{n}  {t}" for r, n, t in offenders)
    )


def test_p2_literal_modal_props_are_all_table_keys():
    """P2：每个字面量 `modal="…"` 调用点都是 MODAL_TESTIDS 的键。"""
    # 先钉住正则自身的正确性，而不是信它。
    assert MODAL_PROP_RE.findall('<div aria-modal="true">') == [], (
        "MODAL_PROP_RE 吞掉了 aria-modal——后视断言 (?<![-\\w]) 失效了"
    )
    assert MODAL_PROP_RE.findall('<Modal modal="add-books">') == ["add-books"], (
        "MODAL_PROP_RE 认不出裸的 modal= prop"
    )

    literals: List[str] = []
    for name in ("app.jsx", "reader.jsx", "settings.jsx"):
        literals += MODAL_PROP_RE.findall(_read(name))
    assert len(literals) == 11, (
        f"字面量 modal= 调用点期望恰好 11 处（app.jsx 7 ＋ reader.jsx 4），实到 "
        f"{len(literals)} 处 → {literals}"
    )

    table = modal_table()
    assert set(literals) <= set(table), (
        f"调用点用了表里没有的 key：{sorted(set(literals) - set(table))}"
    )
    assert {"reindex", "conversations", "cache"} <= set(table), (
        "settings.jsx:164 传的是运行期变量 `modal={confirm}`，这三个 key 没有字面量调用点，"
        "只能经由 destructive 到达；表里必须为它们留位置。缺的："
        f"{sorted({'reindex', 'conversations', 'cache'} - set(table))}"
    )


def test_p3_no_testid_prop_other_than_bare_testId():
    """P3：反绕过——原型里唯一的 `*[Tt]est[Ii]d` prop 只能是裸的 `testId`。

    下界理由（§0.5）：(a) 文件数与 testId= 的处数都随无关改动变；(b) 断言是对匹配到的
    名字集合的全称等式；(c) reader.jsx 的四个 Sheet 调用点保证今天至少 4 处。

    这条存在的理由：`closeTestId="rd-x-close"` 对命名 lint 是**不可见**的
    （`PROP_LITERAL_RE` 要求逐字的 `testId`），会放进一个没有任何 lint 校验过的名字。
    """
    assert PROP_NAME_RE.findall('<div data-testid="x" testId="y">') == ["testId"], (
        "PROP_NAME_RE 的锚定不对：它要么切出了 data-testid 的碎片 `testid`，要么漏了 testId"
    )

    files = _jsx_files()
    assert len(files) >= 4, f"原型 jsx 文件期望至少 4 个，实到 {len(files)} 个"

    hits: List[Tuple[str, int, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for m in PROP_NAME_RE.finditer(text):
            hits.append((_rel(path), LINT.line_of(text, m.start(1)), m.group(1)))
    assert len(hits) >= 1, "一处 testId prop 都没扫到，正则空转了"

    names = {name for _, _, name in hits}
    offenders = [h for h in hits if h[2] != "testId"]
    assert names == {"testId"}, (
        "原型里只允许裸的 testId prop（ADR-0014 §Considered-Options-4 明确否决了 "
        "closeTestId 一类的新 prop）；越界的有：\n"
        + "\n".join(f"  {r}:{n}  {v}" for r, n, v in offenders)
    )


def test_p4_derivation_shape_holds_for_all_14_entries():
    """P4：14 个条目的派生形状——断的是关系，不是 70 个常量。"""
    table = modal_table()
    for k, t in sorted(table.items()):
        root = t.get("root")
        assert root, f"{k}：缺 root 字段"
        assert t.get("close") == root + "-close", f"{k}：close 应为 {root}-close，实为 {t.get('close')!r}"
        assert t.get("cancel") == root + "-cancel", f"{k}：cancel 应为 {root}-cancel，实为 {t.get('cancel')!r}"
        assert t.get("primary") == root + "-primary", f"{k}：primary 应为 {root}-primary，实为 {t.get('primary')!r}"
        assert t.get("body") == root + "-body", f"{k}：body 应为 {root}-body，实为 {t.get('body')!r}"
        if k in RESERVED_ROOT:
            continue
        assert k in PAGE_OF, f"{k}：不在 lib×7 / rd×4 / set×3 的页面归属表里"
        assert root == f"{PAGE_OF[k]}-modal-{k}", (
            f"{k}：root 应为 {PAGE_OF[k]}-modal-{k}，实为 {root!r}"
        )

    # 例外写在测试里，而不是藏在 skip 里：ADR-0014 说 note-editor 是**唯一**的保留名。
    assert table["note-editor"]["root"] == "rd-note-editor", (
        "note-editor 是 ADR-0014 唯一的保留名例外，root 必须是 rd-note-editor，"
        f"实为 {table['note-editor']['root']!r}"
    )


def test_p5_all_70_literals_are_unique_and_canonical():
    """P5：70 个字面量两两不同，且全部匹配**导入的** CANONICAL。"""
    table = modal_table()
    values = [v for t in table.values() for v in t.values()]
    assert len(values) == 70, f"期望 14×5=70 个字面量，实到 {len(values)} 个"
    dupes = [v for v, c in Counter(values).items() if c > 1]
    assert len(set(values)) == 70, f"表内有重复字面量：{sorted(dupes)}"
    bad = [v for v in values if not LINT.CANONICAL.match(v)]
    assert bad == [], f"不合规的 testid 名（正则 {LINT.CANONICAL.pattern}）：{bad}"


SHARED_SURVIVORS = {
    "lib": {
        "liveRegion": "lib-live-region",
        "topbar": "lib-topbar",
        "brand": "lib-brand",
        "themeToggle": "lib-theme-toggle",
        "mobileMenu": "lib-topbar-mobile-menu",
        "mobileInsights": "lib-topbar-mobile-insights",
        "navLibrary": "lib-topbar-nav-library",
        "navSettings": "lib-topbar-nav-settings",
        "addBooks": "lib-topbar-add-books",
        "backToLibrary": "lib-topbar-back-to-library",
    },
    "rd": {
        "liveRegion": "rd-live-region",
        "topbar": "rd-topbar",
        "brand": "rd-brand",
        "themeToggle": "rd-theme-toggle",
        "mobileMenu": "rd-topbar-mobile-menu",
        "mobileInsights": "rd-topbar-mobile-insights",
        "navLibrary": "rd-topbar-nav-library",
        "navSettings": "rd-topbar-nav-settings",
        "addBooks": "rd-topbar-add-books",
        "backToLibrary": "rd-topbar-back-to-library",
    },
    "set": {
        "liveRegion": "set-live-region",
        "topbar": "set-topbar",
        "brand": "set-brand",
        "themeToggle": "set-theme-toggle",
        "mobileMenu": "set-topbar-mobile-menu",
        "mobileInsights": "set-topbar-mobile-insights",
        "navLibrary": "set-topbar-nav-library",
        "navSettings": "set-topbar-nav-settings",
        "addBooks": "set-topbar-add-books",
        "backToLibrary": "set-topbar-back-to-library",
    },
}
REMOVED_SHARED_KEYS = {"modal", "modalClose", "modalCancel", "modalPrimary", "confirmBody"}


def test_p6_shared_testids_lost_exactly_five_keys_per_tier():
    """P6：SHARED_TESTIDS 每层恰好少了 5 个键，另外 10 个逐字不动。"""
    tiers = _parse_block(SHARED_BLOCK_RE, _read("components.jsx"), 3, "SHARED_TESTIDS")
    assert set(tiers) == {"lib", "rd", "set"}, f"层级键应为 lib/rd/set，实为 {sorted(tiers)}"

    for tier, expected in SHARED_SURVIVORS.items():
        got = tiers[tier]
        assert set(got) == set(expected), (
            f"SHARED_TESTIDS.{tier}：键集不对。多出 {sorted(set(got) - set(expected))}，"
            f"缺少 {sorted(set(expected) - set(got))}"
        )
        leftover = REMOVED_SHARED_KEYS & set(got)
        assert leftover == set(), (
            f"SHARED_TESTIDS.{tier}：这 5 个键应搬进 MODAL_TESTIDS 并从这里删除，仍在："
            f"{sorted(leftover)}"
        )
        for key, value in expected.items():
            assert got[key] == value, (
                f"SHARED_TESTIDS.{tier}.{key}：幸存的值必须逐字保留，期望 {value!r}，实为 {got[key]!r}"
            )


def test_p7_modal_testids_has_exactly_14_keys_each_with_5_fields():
    """P7：表的键集恰好是那 14 个，每个条目恰好 5 个字段。"""
    table = modal_table()
    assert set(table) == MODAL_KEYS, (
        f"多出 {sorted(set(table) - MODAL_KEYS)}，缺少 {sorted(MODAL_KEYS - set(table))}"
    )
    for k in sorted(table):
        assert set(table[k]) == MODAL_FIELDS, (
            f"{k}：字段集应为 {sorted(MODAL_FIELDS)}，实为 {sorted(table[k])}"
        )


def test_p8_no_string_concatenation_in_any_data_testid_expression():
    """P8：任何 `data-testid={…}` 表达式里不得有 `+` 或反引号。

    下界理由（§0.5）：(a) 表达式处数随任何原型改动变，包括本批次之外的；(b) 断言是对
    抽出来的表达式的全称命题；(c) 今天远多于 10 处。
    """
    offenders: List[Tuple[str, str]] = []
    total = 0
    for path in _jsx_files():
        text = path.read_text(encoding="utf-8")
        for expr in LINT.ATTR_EXPR_RE.findall(text):
            total += 1
            if "+" in expr or "`" in expr:
                offenders.append((_rel(path), expr.strip()))
    assert total >= 10, f"data-testid={{…}} 表达式期望至少 10 处，实到 {total} 处"
    assert offenders == [], (
        "testid 不得由拼接产生（设计规格 §4 规则 5 ／ ADR-0014）；违规："
        + "\n".join(f"  {r}  data-testid={{{e}}}" for r, e in offenders)
    )


DESTRUCTIVE_BLOCK_RE = re.compile(r"const\s+destructive\s*=\s*\{(?P<body>.*?)\n\s*\};", re.DOTALL)


def test_p9_settings_keeps_the_runtime_variable_form():
    """P9：settings.jsx 保持运行期变量形态，且该变量的取值域被表覆盖。

    绝不能为了「迎合 lint」把 :164 展开成三个字面量分支——那正是 ADR-0014
    §Considered-Options-4 拿来否决字面量 prop 的反面教材。
    """
    text = _read("settings.jsx")
    assert "modal={confirm}" in text, (
        "settings.jsx 的 ConfirmModal 必须保持 `modal={confirm}` 的运行期变量形态"
    )
    literal_sites = MODAL_PROP_RE.findall(text)
    assert literal_sites == [], (
        f"settings.jsx 里不该出现字面量 modal=\"…\"（aria-modal 已被锚定排除）：{literal_sites}"
    )

    blocks = list(DESTRUCTIVE_BLOCK_RE.finditer(text))
    assert len(blocks) == 1, f"`const destructive = {{ … }};` 期望 1 个块，实到 {len(blocks)} 个"
    keys = [m.group("key") for m in ENTRY_RE.finditer(blocks[0].group("body"))]
    assert len(keys) == 3, f"destructive 期望恰好 3 个键，实到 {len(keys)} 个 → {keys}"
    assert set(keys) == {"reindex", "conversations", "cache"}, f"destructive 键集不对：{sorted(keys)}"

    table = modal_table()
    assert set(keys) <= set(table), (
        f"destructive 的取值域必须整个落在 MODAL_TESTIDS 里，缺：{sorted(set(keys) - set(table))}"
    )


def test_p10_page_prop_gone_from_modals_and_kept_where_it_is_still_a_prop():
    """P10：Modal/ConfirmModal 不再有 `page=`／`name=`；Brand 一类仍然有。

    下界理由（§0.5）：(a) Brand/ThemeToggle/LiveRegion 的调用点随无关改动增减；(b) 断言
    是对抽出来的标签的全称命题；(c) 17 贴着今天的真实值（18）。

    正向那半是防「一把 sed 把所有 page= 都撸掉」的连带损伤。
    """
    modal_tags: List[Tuple[str, str]] = []
    page_tags: List[Tuple[str, str]] = []
    total = 0
    for path in _jsx_files():
        text = path.read_text(encoding="utf-8")
        for tag in _jsx_tags(text):
            total += 1
            head = tag[1 : tag.find(" ") if " " in tag else len(tag)]
            if head in ("Modal", "ConfirmModal"):
                modal_tags.append((_rel(path), tag))
            else:
                page_tags.append((_rel(path), tag))
    assert total >= 17, f"Modal/ConfirmModal/LiveRegion/Brand/ThemeToggle 标签期望至少 17 个，实到 {total} 个"

    bad_modal = [
        (r, t)
        for r, t in modal_tags
        if PAGE_PROP_RE.search(t) or NAME_PROP_RE.search(t) or not MODAL_ANY_PROP_RE.search(t)
    ]
    assert bad_modal == [], (
        "Modal/ConfirmModal 应当只带 modal=，不带 page=／name=；违规标签：\n"
        + "\n".join(f"  {r}\n    {t[:160]}" for r, t in bad_modal)
    )

    bad_page = [(r, t) for r, t in page_tags if not PAGE_PROP_RE.search(t)]
    assert bad_page == [], (
        "LiveRegion/Brand/ThemeToggle 的 page= 是真 prop，不能被顺手删掉；违规标签：\n"
        + "\n".join(f"  {r}\n    {t[:160]}" for r, t in bad_page)
    )

    # TopBar 没有 page prop——它自己推导，再传给 Brand / ThemeToggle。
    # 「TopBar 没被误伤」的真实内容就是这三行还在。
    components = _read("components.jsx")
    assert 'screen === "settings" ? "set" : "lib"' in components, (
        "TopBar 内部推导 page 的那行没了（components.jsx:219）"
    )
    assert "<Brand page={page} />" in components, "TopBar 不再把 page 传给 Brand"
    assert "<ThemeToggle page={page}" in components, "TopBar 不再把 page 传给 ThemeToggle"


def test_p11_every_modal_tag_carries_a_modal_prop_including_the_internal_one():
    """P11：每个 Modal/ConfirmModal 标签都带 modal=，**内部那个透传标签也在集合里**。

    真正要守的是：ConfirmModal 内部自己渲染的那个 `<Modal>`（components.jsx:205 一带）也
    得写成 `modal={modal}`。漏了它，四个 ConfirmModal 在运行期全坏，而所有「只看调用点」
    的用例照样绿。

    原来这条写成 `len(tags) == 13`。13 并**不点名**那个内部标签——另外 13 个调用点也能凑
    够 13，而它守的东西就此漏掉；同时任何新增／删除一个弹层调用点都会让它红在无关的地方。
    改成按**位置**取出 ConfirmModal 函数体里的那个 `<Modal>`，断它带 modal= 且确实落进了
    被全称检查的集合，再加一条远离真值的下界防扫描空转。这样它守的东西第一次真的被守住。
    """
    tags: List[Tuple[str, str]] = []
    for path in _jsx_files():
        for tag in _jsx_tags(path.read_text(encoding="utf-8"), ("Modal", "ConfirmModal")):
            tags.append((_rel(path), tag))
    assert len(tags) >= 6, (
        f"Modal/ConfirmModal 标签期望至少 6 个，实到 {len(tags)} 个——扫描空转了：\n"
        + "\n".join(f"  {r}  {t[:80]}" for r, t in tags)
    )

    # 按位置点名那个内部透传标签，而不是靠总数把它「顺带」数进去。
    confirm_body = _slice_body(
        _read("components.jsx"), "function ConfirmModal(props)", NEXT_TOP_BRACE_RE, "ConfirmModal"
    )
    inner = _jsx_tags(confirm_body, ("Modal",))
    assert len(inner) == 1, (
        f"ConfirmModal 的函数体里期望恰好 1 个 `<Modal …>` 开标签，实到 {len(inner)} 个：{inner}"
    )
    assert MODAL_ANY_PROP_RE.search(inner[0]), (
        "ConfirmModal 内部自己渲染的那个 `<Modal>` 没有 modal= prop——四个 ConfirmModal 在"
        f"运行期会全部渲染 data-testid={{undefined}}，而只看调用点的用例照样绿：\n    {inner[0][:160]}"
    )
    assert inner[0] in [t for _r, t in tags], (
        "ConfirmModal 内部那个 `<Modal>` 没有落进被检查的标签集合——_jsx_tags 的扫描漏了它，"
        "下面的全称断言对它就是空真：\n"
        f"    {inner[0][:160]}"
    )

    missing = [(r, t) for r, t in tags if not MODAL_ANY_PROP_RE.search(t)]
    assert missing == [], (
        "这些 Modal/ConfirmModal 没有 modal= prop：\n"
        + "\n".join(f"  {r}\n    {t[:160]}" for r, t in missing)
    )


def test_p12_every_testid_literal_in_components_is_distinct():
    """P12：components.jsx 内所有 testid 字面量互不重复——WI-1 那条法则的单文件形态。

    按**多重集**建，不是集合：集合形态下 |A∪B∪C| == |A|+|B|+|C| 与两两不交等价，等式
    什么也没多说；多重集形态还能抓到表内重复和 C 内重复（同一个 data-testid 挂在两个
    节点上），后者正是 WI-1 要报、P12 要定位的那种缺陷。
    """
    text = _read("components.jsx")
    blocks = _table_blocks(text)
    by_name = {name: m for name, m in blocks}
    assert "MODAL_TESTIDS" in by_name, (
        f"生产的 TESTID_TABLE_RE 看不到 MODAL_TESTIDS；它看到的是 {sorted(by_name)}"
    )
    assert "SHARED_TESTIDS" in by_name, f"看不到 SHARED_TESTIDS；只看到 {sorted(by_name)}"

    A = LINT.TABLE_VALUE_RE.findall(by_name["MODAL_TESTIDS"].group(1))
    B = LINT.TABLE_VALUE_RE.findall(by_name["SHARED_TESTIDS"].group(1))
    # D 由 TESTID_TABLE_RE 自动兜底：明天多一张兄弟表会自己落进来，不用手维护名单。
    D = [
        v
        for name, m in blocks
        if name not in ("MODAL_TESTIDS", "SHARED_TESTIDS")
        for v in LINT.TABLE_VALUE_RE.findall(m.group(1))
    ]

    remainder = ""
    prev = 0
    for _name, m in blocks:
        remainder += text[prev : m.start()]
        prev = m.end()
    remainder += text[prev:]
    C_attr = LINT.ATTR_LITERAL_RE.findall(remainder)
    C_prop = LINT.PROP_LITERAL_RE.findall(remainder)
    C = C_attr + C_prop

    assert len(A) == 70, f"MODAL_TESTIDS 期望 14×5=70 个值，实到 {len(A)}"
    assert len(B) == 30, f"SHARED_TESTIDS 期望 3×10=30 个值，实到 {len(B)}"
    assert len(D) == 9, f"三张兄弟表期望 4＋2＋3=9 个值，实到 {len(D)}"
    assert len(C_prop) == 0, f"components.jsx 不该有 testId=\"…\" prop 字面量：{C_prop}"
    # 下界而非精确值（见模块 docstring 的「新的分界线」）：这个数守的是「表外字面量集合
    # 非空」——空了的话下面的 `set(A) & set(C) == set()` 与末尾的唯一性断言就都空转了。
    # 越界闸门那一半随 WI-4 落地到期，不再钉住。
    assert len(C_attr) >= 10, (
        f"表外的 data-testid=\"…\" 字面量期望至少 10 处，实到 {len(C_attr)} 处——"
        f"少到这个地步说明 ATTR_LITERAL_RE 或表块扣减出了问题，"
        f"`set(A) & set(C) == set()` 与末尾的唯一性断言会一起空转。"
        f"\n  当前清单：{sorted(Counter(C_attr).items())}"
    )

    assert set(A) & set(B) == set(), f"MODAL_TESTIDS ∩ SHARED_TESTIDS = {sorted(set(A) & set(B))}"
    assert set(A) & set(C) == set(), f"MODAL_TESTIDS ∩ 表外字面量 = {sorted(set(A) & set(C))}"
    assert set(B) & set(D) == set(), f"SHARED_TESTIDS ∩ 兄弟表 = {sorted(set(B) & set(D))}"

    total = A + B + D + C
    # 这里**没有**对 len(total) 的断言，不是漏了：`total = A + B + D + C`，而 |A|、|B|、|D|、
    # |C_attr|、|C_prop| 上面各自已经断过，任何对 len(total) 的等式都是它们的和，恒真、
    # 零独立信息量，只会在无关改动动了 C_attr 时多红一次。见模块 docstring。
    dupes = sorted((v, c) for v, c in Counter(total).items() if c > 1)
    assert len(set(total)) == len(total), (
        f"components.jsx 同文件内出现重名 testid（WI-1 的唯一性检查会红）：{dupes}"
    )


def test_p13_every_root_recovers_its_key():
    """P13：root → key 的往返是可逆的——ADR-0014 §Risks 点名的「扁平表撞名」风险的直接测试。"""
    table = modal_table()

    def key_of(root: str) -> str:
        if root == "rd-note-editor":
            return "note-editor"
        _page, _sep, name = root.partition("-modal-")
        return name

    for k in sorted(table):
        root = table[k]["root"]
        assert key_of(root) == k, f"{k}：root {root!r} 反解出 {key_of(root)!r}"
        assert table[k]["close"].removesuffix("-close") == root, (
            f"{k}：close {table[k]['close']!r} 去掉后缀应回到 root {root!r}"
        )

    recovered = {key_of(t["root"]) for t in table.values()}
    assert recovered == set(table), (
        "root 集合与 key 集合不构成双射——两个页面复用同一个弹层名时就会这样。"
        f"反解得到 {sorted(recovered)}，表的键是 {sorted(table)}"
    )


def test_p14_modal_components_actually_read_modal_testids():
    """P14：Modal / ConfirmModal 真的去 MODAL_TESTIDS 查表了。

    没有这一条，整批可以在 MODAL_TESTIDS 是**完美死代码**的情况下全绿：表建好了、
    SHARED_TESTIDS 删干净了（P6 绿）、13 个调用点都改了（P10/P11 绿），而 Modal 的函数体
    里还写着 `const t = SHARED_TESTIDS[page];`——运行期每个弹层都渲染
    `data-testid={undefined}`。P12 抓不到（表内字面量依然互不相同），U8 抓不到（渲染为空
    自然没有重名）。这是唯一会红的一条。
    """
    text = _read("components.jsx")
    modal_body = _slice_body(text, "function Modal(props)", NEXT_TOP_BRACE_RE, "Modal")
    confirm_body = _slice_body(text, "function ConfirmModal(props)", NEXT_TOP_BRACE_RE, "ConfirmModal")

    assert "MODAL_TESTIDS[" in modal_body, (
        "Modal 的函数体没有查 MODAL_TESTIDS——这张表现在是死代码，弹层会渲染 "
        "data-testid={undefined}"
    )
    assert "SHARED_TESTIDS[" not in modal_body, "Modal 仍在读 SHARED_TESTIDS"
    assert "SHARED_TESTIDS[" not in confirm_body, "ConfirmModal 仍在读 SHARED_TESTIDS"

    modal_props = _destructured_names(modal_body, "Modal")
    assert "modal" in modal_props, f"Modal 没有解构出 modal prop：{sorted(modal_props)}"
    assert "page" not in modal_props, f"Modal 仍在解构 page：{sorted(modal_props)}"
    assert "name" not in modal_props, f"Modal 仍在解构 name：{sorted(modal_props)}"

    confirm_props = _destructured_names(confirm_body, "ConfirmModal")
    assert "modal" in confirm_props, f"ConfirmModal 没有解构出 modal prop：{sorted(confirm_props)}"
    assert "page" not in confirm_props, f"ConfirmModal 仍在解构 page：{sorted(confirm_props)}"
    assert "name" not in confirm_props, f"ConfirmModal 仍在解构 name：{sorted(confirm_props)}"

    modal_exprs = LINT.ATTR_EXPR_RE.findall(modal_body)
    assert len(modal_exprs) == 4, (
        f"Modal 体内的 data-testid={{…}} 期望恰好 4 处，实到 {len(modal_exprs)} → {modal_exprs}"
    )
    modal_fields = {e.strip().rsplit(".", 1)[-1] for e in modal_exprs}
    assert modal_fields == {"root", "close", "cancel", "primary"}, (
        f"Modal 取的字段应为 root/close/cancel/primary，实为 {sorted(modal_fields)}"
    )

    confirm_exprs = LINT.ATTR_EXPR_RE.findall(confirm_body)
    assert len(confirm_exprs) == 1, (
        f"ConfirmModal 体内的 data-testid={{…}} 期望恰好 1 处，实到 {len(confirm_exprs)} → {confirm_exprs}"
    )
    assert confirm_exprs[0].strip().rsplit(".", 1)[-1] == "body", (
        f"ConfirmModal 取的字段应为 body，实为 {confirm_exprs[0]!r}"
    )

    assert LINT.ATTR_LITERAL_RE.findall(modal_body) == [], "Modal 体内不该有字面量 data-testid"
    assert LINT.ATTR_LITERAL_RE.findall(confirm_body) == [], "ConfirmModal 体内不该有字面量 data-testid"


def test_p15_new_tables_are_visible_to_the_production_table_regex():
    """P15：两张新表在**生产的** TESTID_TABLE_RE 眼里是可见的。

    其他表用例都用测试自己的 TABLE_BLOCK_RE 解析。如果 MODAL_TESTIDS 写成生产正则认不
    出的终止形态（`};` 前没换行、结尾带行内注释、`} as const;`），测试的 helper 照样找
    得到，而**命名 lint 在这张表里看到 0 个值**——70 个新字面量一个都不会被校验，U8 会
    因为瞎了而绿。这是唯一把两套 parser 钉在一起的一条。

    主张断成**关系**而不是块数（原来钉的是 components 5 ／ reader 7）：块数是顺带清点的存
    量，加一张无关的兄弟表就会红，而红因与本条守的东西无关。改成「生产正则看到的表名集合
    == 独立声明扫描（`TABLE_DECL_RE`，只认声明头、不关心终止符）看到的集合」之后，新表两
    边同时可见故免疫，生产正则漏表则必红——比 `==5` / `==7` 严格更强。见模块 docstring。
    """
    components = _read("components.jsx")
    cblocks = _assert_production_regex_sees_every_table(components, "components.jsx")
    probe = [m for _n, m in cblocks if '"lib-modal-add-books"' in m.group(1)]
    assert len(probe) == 1, (
        f"含 \"lib-modal-add-books\" 的表块期望恰好 1 个，实到 {len(probe)} 个"
    )
    modal_values = LINT.TABLE_VALUE_RE.findall(probe[0].group(1))
    assert len(modal_values) == 70, f"MODAL_TESTIDS 块里生产正则应取到 70 个值，实到 {len(modal_values)}"
    # 下界而非精确值（原来钉的是 109）：本函数里只有上面那条 70 单独断过（30 与 9 归 P12
    # 管），所以这条不能像 P12 的 len(total) 那样直接删——它还在承担「生产的 TABLE_VALUE_RE
    # 在 MODAL_TESTIDS **之外**的表里也取到了值」。但 109 是顺带清点的存量，加一张兄弟表
    # 就红。**减掉那 70 再取下界**：直接对 ctotal 取任何 ≤70 的下界都会被上一条 `== 70`
    # 蕴含，成为恒真的空转，而这正是本次要清掉的东西。
    ctotal = sum(len(LINT.TABLE_VALUE_RE.findall(m.group(1))) for _n, m in cblocks)
    assert ctotal - len(modal_values) >= 10, (
        f"components.jsx 里 MODAL_TESTIDS 之外的表块合计期望至少 10 个值，实到 "
        f"{ctotal - len(modal_values)} 个（全部表块合计 {ctotal}）——"
        f"说明生产的 TABLE_VALUE_RE 在这些表里基本空转了"
    )

    reader = _read("reader.jsx")
    rblocks = _assert_production_regex_sees_every_table(reader, "reader.jsx")
    rprobe = [m for _n, m in rblocks if '"rd-ai-panel-resizer"' in m.group(1)]
    assert len(rprobe) == 1, (
        f"含 \"rd-ai-panel-resizer\" 的表块期望恰好 1 个，实到 {len(rprobe)} 个"
    )
    sheet_values = LINT.TABLE_VALUE_RE.findall(rprobe[0].group(1))
    assert len(sheet_values) == 5, f"RD_SHEET_TESTIDS 块里生产正则应取到 5 个值，实到 {len(sheet_values)}"
    # 下界而非精确值（原来钉的是 28）：28 里的 5 已由紧邻的 sheet_values 单断，剩下的 23 是
    # 六张兄弟表的存量盘点，加一个枚举项就红。同 ctotal，**减掉那 5 再取下界**，否则下界会
    # 被上一条 `== 5` 蕴含而恒真。
    rtotal = sum(len(LINT.TABLE_VALUE_RE.findall(m.group(1))) for _n, m in rblocks)
    assert rtotal - len(sheet_values) >= 10, (
        f"reader.jsx 里 RD_SHEET_TESTIDS 之外的表块合计期望至少 10 个值，实到 "
        f"{rtotal - len(sheet_values)} 个（全部表块合计 {rtotal}）——"
        f"说明生产的 TABLE_VALUE_RE 在这些兄弟表里基本空转了"
    )


def test_p16_adr_rationale_comment_above_modal_survives():
    """P16：Modal 上方那段 ADR-0014 的理由注释在重写后还在。

    只断被切出来的那 12 行，不断整份文件：整文件断言对一段漂到 400 行外的孤儿注释也会绿。
    公认的弱点（与 S14/S16 同类，变异分低），保留的理由是 `data-modal` 恰恰是后来者会
    「顺手加回来」的那种东西，而这段注释是 components.jsx 里唯一说明为什么不能加的地方。
    """
    text = _read("components.jsx")
    anchor = "function Modal(props)"
    assert text.count(anchor) == 1, f"`{anchor}` 期望恰好 1 处，实到 {text.count(anchor)} 处"
    lines = text.splitlines()
    idx = next(i for i, line in enumerate(lines) if anchor in line)
    region = "\n".join(lines[max(0, idx - 12) : idx + 1])

    assert "MODAL_TESTIDS" in region, f"注释区没提到 MODAL_TESTIDS：\n{region}"
    assert "docs/adr/0014-bounded-testid-enumeration.md" in region, (
        f"注释区没链到 ADR-0014：\n{region}"
    )
    assert "data-modal" in region and "删除" in region, (
        f"注释区没说明判别位 data-modal 已删除：\n{region}"
    )


# ==========================================================================
# WI-5 — RD_SHEET_TESTIDS 与 Sheet
# ==========================================================================

SHEET_KEYS = {"rd-toc-panel", "rd-notes-panel", "rd-search-panel", "rd-ai-panel"}


def test_q1_data_sheet_is_gone_from_reader_jsx():
    """Q1：`data-sheet` 从 reader.jsx 里消失（今天 2 处，:200 与 :211）。"""
    text = _read("reader.jsx")
    offenders = [
        (n, line.strip()) for n, line in enumerate(text.splitlines(), 1) if "data-sheet" in line
    ]
    assert text.count("data-sheet") == 0, (
        f"判别位 data-sheet 必须删除（ADR-0014）；仍有 {text.count('data-sheet')} 处：\n"
        + "\n".join(f"  reader.jsx:{n}  {t}" for n, t in offenders)
    )


def test_q2_four_sheet_call_sites_are_all_table_keys():
    """Q2：四个 Sheet 调用点的 testId 字面量恰好就是表的键集。"""
    literals = _extract(
        LINT.PROP_LITERAL_RE, _read("reader.jsx"), 4, "reader.jsx 的 testId=\"…\" prop"
    )
    assert set(literals) == SHEET_KEYS, (
        f"四个调用点的 testId 必须逐字保留（这四个名字已经在生产模板和改名表里）：{sorted(literals)}"
    )
    table = sheet_table()
    assert set(literals) == set(table), (
        f"表键与调用点必须双向相等；表里 {sorted(table)}，调用点 {sorted(set(literals))}"
    )


def test_q3_table_values_do_not_intersect_the_prop_literals():
    """Q3：表的值与四个 prop 字面量不相交——WI-1 与 WI-5 得以共存的那条约束。"""
    props = _extract(
        LINT.PROP_LITERAL_RE, _read("reader.jsx"), 4, "reader.jsx 的 testId=\"…\" prop"
    )
    values = [v for t in sheet_table().values() for v in t.values()]
    assert len(values) == 5, f"RD_SHEET_TESTIDS 期望 4×close ＋ 1×resizer = 5 个值，实到 {len(values)}"
    overlap = sorted(set(values) & set(props))
    assert overlap == [], (
        "RD_SHEET_TESTIDS 不能有 root 字段：一个 root 字面量会和同一个文件里调用点的 "
        "testId prop 字面量重名，WI-1 的唯一性检查会把 reader.jsx 判红。"
        f"重名的是：{overlap}"
    )


def test_q4_only_ai_panel_has_a_resizer():
    """Q4：只有 rd-ai-panel 有 resizer；派生形状成立。"""
    table = sheet_table()
    assert set(table) == SHEET_KEYS, f"表键应为四个面板名，实为 {sorted(table)}"
    for k in sorted(table):
        assert table[k].get("close") == k + "-close", (
            f"{k}：close 应为 {k}-close，实为 {table[k].get('close')!r}"
        )
    assert set(table["rd-ai-panel"]) == {"close", "resizer"}, (
        f"rd-ai-panel 应有且只有 close/resizer，实为 {sorted(table['rd-ai-panel'])}"
    )
    assert table["rd-ai-panel"]["resizer"] == "rd-ai-panel-resizer", (
        f"resizer 应为 rd-ai-panel-resizer，实为 {table['rd-ai-panel']['resizer']!r}"
    )
    for k in sorted(SHEET_KEYS - {"rd-ai-panel"}):
        assert set(table[k]) == {"close"}, (
            f"{k} 只应有 close——给它加 resizer 会为不存在的 DOM 节点发名字，"
            f"这种名字永远选不到、只会烂掉。实为 {sorted(table[k])}"
        )


def test_q5_old_sheet_names_are_gone_from_designs_and_src():
    """Q5：`rd-sheet-close` / `rd-sheet-resizer` 从 designs/ 与 src/ 两棵树里消失。

    下界理由（§0.5）：(a) 两棵树各自独立增长；(b) 断言是两个字面量 × 所有文件的全称命题；
    (c) 20 远低于今天的 32。

    `designs/reader-pro-next/*.css` 在范围内，因为一条键在 `[data-testid="rd-sheet-close"]`
    上的 CSS 规则是任何 lint 都看不到的活消费者。
    """
    files: List[Path] = []
    for pattern in ("designs/**/*.jsx", "designs/**/*.html", "designs/**/*.css"):
        files += list(REPO_ROOT.glob(pattern))
    for pattern in (
        "src/reader3_app/web/**/*.html",
        "src/reader3_app/web/**/*.js",
        "src/reader3_app/web/**/*.css",
    ):
        files += [p for p in REPO_ROOT.glob(pattern) if "/static/vendor/" not in p.as_posix()]
    files = sorted(set(files))
    assert len(files) >= 20, f"期望至少扫到 20 个文件，实到 {len(files)} 个"

    offenders: List[Tuple[str, int, str]] = []
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for old in ("rd-sheet-close", "rd-sheet-resizer"):
                if old in line:
                    offenders.append((_rel(path), lineno, old))
    assert offenders == [], (
        "旧的共享 sheet 名必须全部改成逐面板的名字；仍在：\n"
        + "\n".join(f"  {r}:{n}  {v}" for r, n, v in offenders)
    )


def test_q6_sheet_values_are_disjoint_from_all_other_literals_in_reader():
    """Q6：RD_SHEET_TESTIDS 的值与 reader.jsx 里其余全部字面量不相交（Q3 的一般形态）。

    B 用**导入的** TESTID_TABLE_RE 重建，不再手抄兄弟表名单——手抄的名单会烂（上一版就抄
    出了一个并不存在的 `RD_ANNO_TYPE`）。P15 断的是「生产 `TESTID_TABLE_RE` 看到的表名集合
    == 独立声明扫描看到的集合」，所以任何一张兄弟表都不会因为生产正则认不出它的终止形态而
    被悄悄漏掉——这里的 B 也就不会缺一块。

    B **不减去 A**：减掉就把 `set(A) & set(B) == ∅` 变成恒真，那正是 §0.5 要禁的空转。
    不减，这条断言才真的能在有人「为了和 MODAL_TESTIDS 对称」加上 `root: "rd-ai-panel"`
    时红掉。

    下界理由（§0.5）：(a) reader.jsx 是最大的原型，会随无关设计工作增加 testid；(b) 断言是
    对整个并集的全称命题；(c) 六张兄弟表本身就有 23 个，行内字面量还要多得多。
    """
    text = _read("reader.jsx")
    A = [v for t in sheet_table().values() for v in t.values()]
    assert len(A) == 5, f"RD_SHEET_TESTIDS 期望 5 个值，实到 {len(A)}"

    B: List[str] = LINT.ATTR_LITERAL_RE.findall(text) + LINT.PROP_LITERAL_RE.findall(text)
    for name, m in _table_blocks(text):
        if name == "RD_SHEET_TESTIDS":
            continue
        B += LINT.TABLE_VALUE_RE.findall(m.group(1))
    assert len(B) >= 40, f"reader.jsx 的其余字面量期望至少 40 个，实到 {len(B)} 个"

    overlap = sorted(set(A) & set(B))
    assert overlap == [], f"RD_SHEET_TESTIDS 的值和文件里别处的字面量重名：{overlap}"

    counts = Counter(A + B)
    dupes = sorted((v, c) for v, c in counts.items() if c > 1)
    assert dupes == [], (
        f"reader.jsx 自己就不满足 WI-1 的同文件唯一性检查，重名的有：{dupes}"
    )


def test_q7_sheet_prop_list_is_unchanged():
    """Q7：Sheet 没有新增 prop——ADR-0014 §Considered-Options-4 否决的那种设计。"""
    text = _read("reader.jsx")
    m = re.search(
        r"function Sheet\(props\)\s*\{\s*const\s*\{([^}]*)\}\s*=\s*props;", text, re.DOTALL
    )
    assert m is not None, "找不到 Sheet 的 `const { … } = props;` 解构行"
    names = {n.strip() for n in m.group(1).split(",") if n.strip()}
    assert names == {"title", "side", "width", "onClose", "children", "testId", "onResize"}, (
        f"Sheet 的 prop 列表必须原样不动（不许加 closeTestId / resizerTestId），实为 {sorted(names)}"
    )
    assert "props.actions" in text, (
        "props.actions 仍应直接访问而不是被解构进来——把它拉进解构必须是一次有意的决定"
    )


def test_q8_sheet_internals_look_the_two_names_up():
    """Q8：Sheet 内部是**查表**，不是把名字写死。

    这是 P14 的 sheet 侧对应物：没有它，`RD_SHEET_TESTIDS` 可以是死代码，而 Q2/Q4/Q5
    九条照样绿。
    """
    text = _read("reader.jsx")
    body = _slice_body(text, "function Sheet(props)", NEXT_TOP_FUNCTION_RE, "Sheet")

    assert "RD_SHEET_TESTIDS[" in body, "Sheet 的函数体没有查 RD_SHEET_TESTIDS"
    assert "rd-sheet-close" not in body, "Sheet 体内仍写死了 rd-sheet-close"
    assert "rd-sheet-resizer" not in body, "Sheet 体内仍写死了 rd-sheet-resizer"

    literals = LINT.ATTR_LITERAL_RE.findall(body)
    assert len(literals) == 0, f"Sheet 体内的字面量 data-testid 应为 0 处，实到 {literals}"
    exprs = LINT.ATTR_EXPR_RE.findall(body)
    assert len(exprs) == 3, (
        f"Sheet 体内的 data-testid={{…}} 表达式应为 3 处（:190 的透传 ＋ 两个由字面量改成的查表），"
        f"实到 {len(exprs)} → {exprs}"
    )


def test_q9_naming_lint_is_clean_when_restricted_to_designs(monkeypatch, capsys):
    """Q9（诊断档）：把 SCAN_GLOBS 收窄到 designs/ 后命名 lint 仍然退出 0。

    Mock 边界：只 monkeypatch SCAN_GLOBS；ROOT 与豁免注册表都是生产值。真实路径是 U8
    （全量 SCAN_GLOBS），U23 钉住这里刻意偏离的那个生产值。

    这是 U8 的**诊断切分**，不是独立覆盖：它让实施者不用读完 U8 的全量转储就能看出
    「模板改完了、原型还没」。删掉它不亏，删掉 U8 就丢了棘轮。
    """
    monkeypatch.setattr(
        LINT,
        "SCAN_GLOBS",
        (
            "designs/reader-pro-next/**/*.jsx",
            "designs/reader-pro-next/**/*.html",
        ),
    )
    code = LINT.main()
    out = capsys.readouterr().out
    assert "扫描 " in out and "个文件，" in out, f"lint 没打出扫描摘要，可能一个文件都没读到：{out!r}"
    assert code == 0, out
