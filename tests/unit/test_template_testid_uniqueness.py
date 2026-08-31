"""WI-3：两份 Jinja 模板的 testid 唯一性、改名与放置（ADR-0014 落地）。

矩阵：`.claude/tdd-guardian/tests-20260831-131500.md` 的 T1–T11。
权威：`docs/adr/0014-bounded-testid-enumeration.md`（Decision Outcome ＋ Migration Strategy）。

被测的是两份**静态文本产物**：`src/reader3_app/web/templates/library.html` 与
`reader.html`。没有服务器、没有 Jinja 渲染、不碰 `books/`（`tests/conftest.py` 记着
`process_epub()` 会对输出目录 `shutil.rmtree()`）。每个用例都只 `read_text()`。

要立的**律**是**单射性**：一份模板内，DOM 节点 → `data-testid` 值的映射必须是单射，
`len(literals) == len(set(literals))`。这正是 Playwright strict 模式要求的性质，也是
ADR-0014 存在的理由。T1 直接陈述它；T8 把它加强成**放置**——光有单射性，21 个唯一的
名字贴在 21 个错误的节点上照样成立。
次律是 **id 守恒**：本批不得改动任何 `id=` 值（`annotations.js:415,420` 用
`getElementById` 取 `#anno-color-row` 与 `#note-tooltip`）。T5、T9 守这一条。

**期望的名字清单是从 ADR-0014 抄下来的，不是从模板里读出来的**——一个从被测产物里
推导自己期望值的测试什么都没断言。

正则与 canonical 一律从 `scripts/lint_testid_naming.py` **导入**，保持唯一定义处；
若 lint 的正则错了，本文件会朝同一个方向错，而那由 WI-1 的 U1/U2 拦。
"""

from __future__ import annotations

import importlib.util
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = REPO_ROOT / "src" / "reader3_app" / "web" / "templates"
LIBRARY_HTML = TEMPLATES / "library.html"
READER_HTML = TEMPLATES / "reader.html"
LINT_PATH = REPO_ROOT / "scripts" / "lint_testid_naming.py"


def _load_lint():
    """脚本不是包，按路径加载。只取常量，不调用 `main()`，不写任何文件。"""
    spec = importlib.util.spec_from_file_location("lint_testid_naming_for_tmpl", LINT_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {LINT_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LINT = _load_lint()
ATTR_LITERAL_RE = _LINT.ATTR_LITERAL_RE
CANONICAL = _LINT.CANONICAL


# --- 期望清单：逐字转自 ADR-0014「Decision Outcome」与矩阵 WI-3 的名字表 -------------

# library.html —— 13 个。注意 add-to-collection 弹层**没有** primary 按钮
# （只有 Cancel），所以「四个后缀套四个弹层」的机械改名是错的，T4 专门拦它。
LIBRARY_TARGETS = (
    "lib-modal-add-books",
    "lib-modal-add-books-close",
    "lib-modal-add-books-primary",
    "lib-modal-index-errors",
    "lib-modal-index-errors-close",
    "lib-modal-index-errors-primary",
    "lib-modal-create-collection",
    "lib-modal-create-collection-close",
    "lib-modal-create-collection-cancel",
    "lib-modal-create-collection-primary",
    "lib-modal-add-to-collection",
    "lib-modal-add-to-collection-close",
    "lib-modal-add-to-collection-cancel",
)

# reader.html —— 6 处改名 ＋ 2 处新增 = 8。
READER_TARGETS = (
    "rd-note-editor",
    "rd-note-editor-cancel",
    "rd-note-editor-primary",
    "rd-search-panel-close",
    "rd-ai-panel-resizer",
    "rd-ai-panel-close",
    "rd-anno-colors",
    "rd-note-tooltip",
)

MANDATED = frozenset(LIBRARY_TARGETS) | frozenset(READER_TARGETS)

# 退役的 9 个名字，两份模板里都不得再出现。
RETIRED = (
    "lib-modal",
    "lib-modal-close",
    "lib-modal-cancel",
    "lib-modal-primary",
    "rd-modal",
    "rd-modal-cancel",
    "rd-modal-primary",
    "rd-sheet-close",
    "rd-sheet-resizer",
)

# T8：四个 <dialog> 各自应当持有的 testid 全集（集合相等，不是包含）。
# 非 lib-modal-* 的成员是该弹层里原有的内容 testid，把它们算进来才让断言有牙。
DIALOG_EXPECTED: Dict[str, set] = {
    "add-books-modal": {
        "lib-modal-add-books",
        "lib-modal-add-books-close",
        "lib-modal-add-books-primary",
    },
    "index-errors-modal": {
        "lib-modal-index-errors",
        "lib-modal-index-errors-close",
        "lib-modal-index-errors-primary",
        "lib-index-errors",
    },
    "create-collection-modal": {
        "lib-modal-create-collection",
        "lib-modal-create-collection-close",
        "lib-modal-create-collection-cancel",
        "lib-modal-create-collection-primary",
        "lib-collection-name-input",
    },
    "add-to-collection-modal": {
        "lib-modal-add-to-collection",
        "lib-modal-add-to-collection-close",
        "lib-modal-add-to-collection-cancel",
        "lib-add-to-collection-select",
    },
}

# T1/T6 共用的抽取下限（§0.5 允许下限的十处之一：这两份文件持有的 testid 远多于本批
# 触及的 21 个，且随无关的 UI 工作增长；真正的断言是对抽取集合的全称命题，计数只需
# 证明非空）。今天的真值：library.html 63 处 / 54 唯一，reader.html 67 处 / 66 唯一。
TEMPLATE_FLOORS = {
    "library.html": 40,
    "reader.html": 60,
}

TEMPLATE_PATHS = {
    "library.html": LIBRARY_HTML,
    "reader.html": READER_HTML,
}


def _read(name: str) -> str:
    path = TEMPLATE_PATHS[name]
    assert path.is_file(), f"模板不存在：{path}"
    return path.read_text(encoding="utf-8")


def _literals(name: str) -> List[str]:
    """抽取一份模板里全部 `data-testid="字面量"`，并先过反空转下限（§0.5）。

    T1 与 T6 共用这一个抽取口，两处下限因此不会各自漂移。
    """
    text = _read(name)
    lits = ATTR_LITERAL_RE.findall(text)
    floor = TEMPLATE_FLOORS[name]
    assert len(lits) > floor, (
        f"{name} 只抽到 {len(lits)} 个 data-testid 字面量（下限 > {floor}）——"
        f"抽取失败时下游断言会空转通过，这条下限就是拦它的"
    )
    return lits


# --------------------------------------------------------------------------------
# T1：单射性——每个 data-testid 字面量在一份模板里恰好出现一次
# --------------------------------------------------------------------------------


@pytest.mark.parametrize("template", ["library.html", "reader.html"])
def test_t1_every_testid_literal_occurs_once_per_template(template: str) -> None:
    lits = _literals(template)
    dupes = {k: v for k, v in Counter(lits).items() if v > 1}
    assert dupes == {}, (
        f"{template} 内有重名的 data-testid（Playwright strict 模式下 getByTestId() 直接抛）："
        f"{dupes}"
    )


# --------------------------------------------------------------------------------
# T2：21 个目标名各出现恰好一次；9 个退役名两份模板里都不存在
# --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "name"),
    [("library.html", n) for n in LIBRARY_TARGETS]
    + [("reader.html", n) for n in READER_TARGETS],
)
def test_t2_target_testid_present_exactly_once(template: str, name: str) -> None:
    text = _read(template)
    needle = f'data-testid="{name}"'
    count = text.count(needle)
    assert count == 1, (
        f"{template} 里 {needle} 出现 {count} 次，应为 1 次（ADR-0014 的名字清单）。"
        f"0 次＝改名没落地；≥2 次＝改名贴到了第二个节点上"
    )


@pytest.mark.parametrize(
    ("template", "name"),
    [(t, n) for t in ("library.html", "reader.html") for n in RETIRED],
)
def test_t2_retired_testid_absent(template: str, name: str) -> None:
    text = _read(template)
    needle = f'data-testid="{name}"'
    hits = [
        (i + 1, line.strip())
        for i, line in enumerate(text.splitlines())
        if needle in line
    ]
    assert hits == [], f"{template} 仍持有已退役的 testid {name!r}：{hits}"


# --------------------------------------------------------------------------------
# T3：data-modal= / data-sheet= 两个判别位从两份模板里消失
# --------------------------------------------------------------------------------


@pytest.mark.parametrize("template", ["library.html", "reader.html"])
@pytest.mark.parametrize("attr", ["data-modal=", "data-sheet="])
def test_t3_discriminator_attribute_removed(template: str, attr: str) -> None:
    text = _read(template)
    survivors = [
        (i + 1, line.strip())
        for i, line in enumerate(text.splitlines())
        if attr.rstrip("=") in line
    ]
    assert text.count(attr) == 0, (
        f"{template} 仍有 {attr}（ADR-0014 删除了这两个判别位）：{survivors}"
    )


# --------------------------------------------------------------------------------
# T4：反向守卫——不得凭空发明的名字
# --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "why"),
    [
        (
            "lib-modal-add-to-collection-primary",
            "add-to-collection 弹层只有 Cancel，没有 primary 按钮",
        ),
        ("lib-modal-add-books-cancel", "add-books 弹层没有 Cancel 按钮"),
        ("lib-modal-index-errors-cancel", "index-errors 弹层没有 Cancel 按钮"),
    ],
)
def test_t4_name_not_invented(name: str, why: str) -> None:
    text = _read("library.html")
    assert name not in text, (
        f"library.html 出现了 {name!r}，但{why}——"
        f"名字必须照着真实 DOM 一个个写，不能用「四个后缀 × 四个弹层」机械生成"
    )


# --------------------------------------------------------------------------------
# T5：annotations.js 依赖的 id 一字未动
# --------------------------------------------------------------------------------

ANNOTATION_IDS = (
    "anno-color-row",
    "note-tooltip",
    "note-editor",
    "note-editor-cancel",
    "note-editor-save",
    "reader-search-close",
    "ai-resize-handle",
    "reader-ai-close",
)


@pytest.mark.parametrize("the_id", ANNOTATION_IDS)
def test_t5_annotation_id_untouched(the_id: str) -> None:
    text = _read("reader.html")
    needle = f'id="{the_id}"'
    count = text.count(needle)
    assert count == 1, (
        f"reader.html 里 {needle} 出现 {count} 次，应为 1 次——"
        f"加 data-testid 是纯增量，id 一个都不许动（annotations.js 用 getElementById 取）"
    )


def test_t5_id_not_renamed_into_the_new_testid() -> None:
    text = _read("reader.html")
    # ⚠️ 红→绿之间修正过的断言（原文是 `assert 'id="rd-note-editor"' not in text`）。
    # 原断言与 T2 互斥、任何实现都过不了：`data-testid="rd-note-editor"` 拆开来是
    # `data-test` ＋ `id="rd-note-editor"`，而 T2 要求这个字符串在 reader.html 里恰好
    # 出现 1 次。故 T2 成立 ⟹ 原 T5 必假。加负向后顾把 `data-testid=` 排除掉，守的东西
    # 一点没少：真把 `id=` 改成新 testid 名，仍然会被抓住。
    revived = re.search(r'(?<!data-test)id="rd-note-editor"', text)
    assert revived is None, (
        "有人把 id 改成了新 testid 的名字。改 id 会静默弄坏标注工具条，"
        "而别处不会有任何测试失败"
    )


# --------------------------------------------------------------------------------
# T6：两份模板里每个 testid 都匹配**导入的** CANONICAL
# --------------------------------------------------------------------------------


@pytest.mark.parametrize("template", ["library.html", "reader.html"])
def test_t6_all_literals_match_canonical(template: str) -> None:
    lits = _literals(template)  # 下限先行，否则 `[v for v in [] if ...] == []` 恒真
    offenders = sorted({v for v in lits if not CANONICAL.match(v)})
    assert offenders == [], (
        f"{template} 里有不匹配 canonical 正则 {CANONICAL.pattern} 的 testid：{offenders}"
    )


# --------------------------------------------------------------------------------
# T7：反绕过——不得有单引号形态，也不得有 Jinja 插值形态
# --------------------------------------------------------------------------------
# ATTR_LITERAL_RE 只认双引号字面量。`data-testid='lib-modal'` 对命名 lint 与 T1 的
# 单射性检查同时隐形——这是重名能在 U8 全绿的情况下重新长出来的真实路径。

BYPASS_FORMS = ("data-testid='", 'data-testid="{{', "data-testid={{")


@pytest.mark.parametrize("template", ["library.html", "reader.html"])
@pytest.mark.parametrize("form", BYPASS_FORMS)
def test_t7_no_invisible_testid_form(template: str, form: str) -> None:
    text = _read(template)
    hits = [
        (i + 1, line.strip())
        for i, line in enumerate(text.splitlines())
        if form in line
    ]
    assert hits == [], (
        f"{template} 里出现了 {form!r} 形态的 data-testid——"
        f"这种写法 ATTR_LITERAL_RE 看不见，唯一性检查与命名 lint 会一起失明：{hits}"
    )


# --------------------------------------------------------------------------------
# T8：结构放置——每个弹层自己的子元素带的是该弹层的名字
# --------------------------------------------------------------------------------

DIALOG_RE = re.compile(r"<dialog\b.*?</dialog>", re.DOTALL)
DIALOG_ID_RE = re.compile(r'\bid\s*=\s*"([^"]*)"')


def _dialog_blocks() -> Dict[str, str]:
    text = _read("library.html")
    blocks = DIALOG_RE.findall(text)
    assert len(blocks) == 4, (
        f"library.html 里切出了 {len(blocks)} 个 <dialog> 块，应为 4 个"
    )
    by_id: Dict[str, str] = {}
    for block in blocks:
        m = DIALOG_ID_RE.search(block)
        assert m is not None, f"有 <dialog> 块没有 id=：{block[:120]!r}"
        by_id[m.group(1)] = block
    assert len(by_id) == 4, f"四个 <dialog> 的 id 不互异：{sorted(by_id)}"
    return by_id


def test_t8_library_has_exactly_four_dialogs() -> None:
    by_id = _dialog_blocks()
    assert set(by_id) == set(DIALOG_EXPECTED), (
        f"library.html 的 <dialog> id 集合变了：{sorted(by_id)}"
    )


@pytest.mark.parametrize("dialog_id", sorted(DIALOG_EXPECTED))
def test_t8_dialog_carries_exactly_its_own_testids(dialog_id: str) -> None:
    block = _dialog_blocks()[dialog_id]
    found = set(ATTR_LITERAL_RE.findall(block))
    expected = DIALOG_EXPECTED[dialog_id]
    assert found == expected, (
        f"#{dialog_id} 持有的 testid 集合不对。"
        f"缺：{sorted(expected - found)}；多：{sorted(found - expected)}。"
        f"把对的 13 个名字贴到错的 13 个节点上，T1/T2/T4 都会放过，这条不会"
    )


# --------------------------------------------------------------------------------
# T9：reader.html 两个新增的 testid 落在两个指定的节点上
# --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("the_id", "testid"),
    [
        ("anno-color-row", "rd-anno-colors"),
        ("note-tooltip", "rd-note-tooltip"),
    ],
)
def test_t9_new_testid_sits_on_the_named_node(the_id: str, testid: str) -> None:
    text = _read("reader.html")
    matches = [line for line in text.splitlines() if f'id="{the_id}"' in line]
    assert len(matches) == 1, (
        f"reader.html 里 id=\"{the_id}\" 的行有 {len(matches)} 行，应为 1 行——"
        f"没有这条守卫，下面那句就退化成「文件里某处有」"
    )
    assert f'data-testid="{testid}"' in matches[0], (
        f"{testid} 没有贴在 #{the_id} 这一行上：{matches[0].strip()!r}"
    )


# --------------------------------------------------------------------------------
# T10：9 个退役名在整个 src/reader3_app/web/ 下都不存在
# --------------------------------------------------------------------------------
# 命名 lint 的 SCAN_GLOBS 只覆盖 templates/*.html，完全看不见 static/**。
# 所以这条是全仓唯一能拦住「library.js 里 el.dataset.testid = 'lib-modal-close'」的东西。

WEB_ROOT = REPO_ROOT / "src" / "reader3_app" / "web"
WEB_EXTS = {".html", ".js", ".css"}
# 下限（§0.5 十处之一）：(a) 这棵树随无关的前端工作增长；(b) 断言是 9 个名字 × 全部
# 文件的全称命题，计数只需证明非空；(c) 今天真值 26 个文件，远在 15 之上。
WEB_FILE_FLOOR = 15


def _web_files() -> List[Path]:
    files = [
        p
        for p in sorted(WEB_ROOT.rglob("*"))
        if p.is_file()
        and p.suffix in WEB_EXTS
        and "static/vendor/" not in p.relative_to(REPO_ROOT).as_posix()
    ]
    assert len(files) >= WEB_FILE_FLOOR, (
        f"只走到 {len(files)} 个文件（下限 >= {WEB_FILE_FLOOR}）——"
        f"遍历失败时下面的断言会空转通过"
    )
    return files


def test_t10_retired_names_absent_from_whole_web_tree() -> None:
    hits = []
    for path in _web_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in RETIRED:
            # ⚠️ 红→绿之间修正过的断言（原文是 `if name in text`）。
            # 原断言与 T2 互斥、任何实现都过不了：RETIRED 里的 `lib-modal` 是 T2 要求的
            # 13 个新名字（lib-modal-add-books 等）的前缀，library.html 又在扫描范围内，
            # 所以 T2 成立 ⟹ 原 T10 必假。
            #
            # 修正二稿（评审后）：一稿写的是整词匹配 `(?![-\w])`，那是过度收窄——9 个退役名
            # 里只有 `lib-modal` 真的与 T2 相撞，一稿却把豁免发给了全部 9 个，于是
            # `data-testid="rd-modal-close"` 这种「拿退役名当前缀现造的新名」全线放行
            # （`rd-modal-close` 不在 RETIRED 里，形状合规，且 static/** 在命名 lint 的
            # SCAN_GLOBS 之外——没有任何别的东西会拦它）。二稿只豁免**确实被 T2 强制**的那些：
            # 取从退役名起算的最长 token，唯有它恰好是一个已授权新名时才放行。
            for m in re.finditer(r"(?<![-\w])" + re.escape(name) + r"[-a-z0-9]*", text):
                token = m.group()
                if token != name and token in MANDATED:
                    continue
                hits.append((rel, token))
    assert sorted(set(hits)) == [], (
        f"已退役的 testid 名（或以它为前缀现造的新名）还活在 src/reader3_app/web/ 下："
        f"{sorted(set(hits))}。命名 lint 看不见 static/**，JS 侧的复活只有这条能拦"
    )


# --------------------------------------------------------------------------------
# T11：data-modal / data-sheet 在代码里再无消费者
# --------------------------------------------------------------------------------
# 范围（矩阵 revision 2 修正过）：static/**、templates/**、**tests/e2e/**、designs/**。
# `tests/**` 被收窄成 `tests/e2e/**`：WI-2 自己的单测 test_lint_e2e_selectors_closed_list.py
# 必然含有字面量 "data-modal"（S2/S5/S9/S12 都拿它当夹具），e2e 才是「消费者」会住的地方，
# 单测里住的是「标本」。
# `docs/`、`.claude/`、`specs/` **故意排除**——ADR-0014、计划与契约都在正文里正当地讨论
# 这个属性名。这条排除是有意的，注释在此是为了让后来者不要「顺手补上」。
# 除属性拼写外还查 JS 属性形态 dataset.modal / dataset.sheet：AC 说的是「消费者」，
# 而消费者读的是 dataset.modal，不是属性拼写。

T11_ROOTS = (
    "src/reader3_app/web/static",
    "src/reader3_app/web/templates",
    "tests/e2e",
    "designs",
)
T11_EXTS = {".html", ".js", ".jsx", ".css", ".py", ".ts"}
# ⚠️ 红→绿之间修正过的断言（原文是 `T11_NEEDLES = ("data-modal", "data-sheet",
# "dataset.modal", "dataset.sheet")`，在下面按裸子串匹配）。
# 原断言与 P16 互斥、任何实现都过不了：P16 要求 components.jsx 里那条
# 「判别位 data-modal 已删除——理由见 docs/adr/0014-…」的说明注释逐字留存，
# 而该注释含有裸子串 data-modal。P16 成立 ⟹ 原 T11 必假。
# 这与 WI-4/5 红阶段给 P1 定的读法是同一条：本用例的主张是「还有**消费者**」，注释不是消费者。
#
# 修正二稿（评审后）：一稿把针收窄成「判别位后面跟着 = " \' ] ) 之一」。那是在错的维度上
# 让步——冲突只有一处、且只在注释里，一稿却把放行发给了四棵树里所有非该形态的写法，于是这些
# **真消费者**全线放行，而且没有任何别的 lint 兜底（选择器 lint 只扫 tests/e2e/**，命名 lint
# 的 SCAN_GLOBS 既不含 static/** 也不含 *.css）：
#   data-modal = "add-books"      属性名与 = 之间有空格（T3 数的是裸串 "data-modal="，同样漏）
#   <div data-sheet aria-hidden>  无值属性
#   [data-sheet^="rd-"] { … }     CSS 前缀匹配选择器（$= *= ~= |= 同理）
#   getAttribute(`data-modal`)    反引号
# 二稿改为在对的维度上让步：**先剥注释，再按原裸子串匹配**。命题回到「注释不是消费者」这一句
# 本身，上面四种形态又全部落网。
T11_NEEDLES = ("data-modal", "data-sheet", "dataset.modal", "dataset.sheet")

_T11_BLOCK = {".js": ("/*", "*/"), ".jsx": ("/*", "*/"), ".ts": ("/*", "*/"),
              ".css": ("/*", "*/"), ".html": ("<!--", "-->")}
_T11_LINE = {".js": "//", ".jsx": "//", ".ts": "//", ".py": "#"}


def _t11_strip_comments(text: str, suffix: str) -> str:
    """把注释内容换成空格，保留换行与列位，好让行号仍然对得上。

    宁可剥不干净也不能剥过头：剥过头会把真消费者藏起来，让 T11 空转变绿。
    """
    out = list(text)
    n = len(text)
    block = _T11_BLOCK.get(suffix)
    line = _T11_LINE.get(suffix)
    i = 0
    while i < n:
        if block and text.startswith(block[0], i):
            end = text.find(block[1], i + len(block[0]))
            end = n if end == -1 else end + len(block[1])
            for j in range(i, end):
                if out[j] != "\n":
                    out[j] = " "
            i = end
            continue
        if line and text.startswith(line, i):
            end = text.find("\n", i)
            end = n if end == -1 else end
            for j in range(i, end):
                out[j] = " "
            i = end
            continue
        i += 1
    return "".join(out)
# 下限（§0.5 十处之一）：(a) 四棵树都独立于本批增长；(b) 断言是 4 个字面量 × 全部文件
# 的全称命题；(c) 今天真值 34 个文件。
#
# ⚠️ 与矩阵的偏差，明写在此：矩阵 T11 写的下限是 `> 40`，并称「> 40 far below today's
# count」。对真仓核过：按 revision 2 收窄后的范围今天只有 34 个文件，所以 40 这个数是
# revision 1（范围还是整个 `tests/**`）留下的陈旧常量。照抄 40 会让 T11 恒红在反空转
# 守卫上——一个改模板与改原型都治不好的红，与本用例真正的主张（0 命中）无关。这里取 30，
# 满足 §0.5 的 (c)「贴近今天的真值，删掉语料的大半仍会失败」。主张本身一字未动。
T11_FILE_FLOOR = 30


def _t11_files() -> List[Path]:
    files: List[Path] = []
    for root in T11_ROOTS:
        base = REPO_ROOT / root
        assert base.is_dir(), f"T11 的范围目录不存在：{base}"
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in T11_EXTS:
                continue
            rel = p.relative_to(REPO_ROOT).as_posix()
            if "static/vendor/" in rel:
                continue
            files.append(p)
    assert len(files) > T11_FILE_FLOOR, (
        f"只走到 {len(files)} 个文件（下限 > {T11_FILE_FLOOR}）——"
        f"遍历失败时 0 命中是空转出来的"
    )
    return files


def test_t11_discriminators_have_no_consumers_left() -> None:
    hits = []
    for path in _t11_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(
            _t11_strip_comments(
                path.read_text(encoding="utf-8", errors="replace"), path.suffix
            ).splitlines(),
            start=1,
        ):
            if any(needle in line for needle in T11_NEEDLES):
                hits.append((rel, lineno, line.strip()))
    assert hits == [], (
        f"data-modal / data-sheet 还有消费者（ADR-0014 已把这两个判别位删出契约）：{hits}"
    )
