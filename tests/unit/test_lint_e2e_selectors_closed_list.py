"""`scripts/lint_e2e_selectors.py` 的复合选择器判别位必须收紧成一张闭合清单（ADR-0014 / WI-2）。

矩阵：`.claude/tdd-guardian/tests-20260831-131500.md` S1–S17。
权威：`docs/adr/0014-bounded-testid-enumeration.md` §Decision Outcome ——
「复合形态继续允许，但收紧为一张闭合清单」，清单是那八个携带用户数据 id 的属性。

被测的是两个东西：

  * `selector_ok(sel)` —— 纯函数。今天它对**任何** `data-*` 判别位都放行，
    所以 `[data-testid="lib-modal"][data-modal="add-books"]` 这种「用判别位区分
    四个同名弹层」的写法一路绿灯。ADR-0014 把弹层与面板判进「有界即逐个枚举」
    那一行，`data-modal` / `data-sheet` 随之从契约里删除 —— lint 要能拦住它们回来。
  * `main()` —— 文件遍历 ＋ `ALLOW_INLINE` 逐行逃生舱 ＋ `files == 0` 分支。
    新检查必须长在**逃生舱之后**（S5），且不能顺手把合规的复合选择器也一起拦掉
    （S17：整条 `main()` 通路上唯一证明「未加放行记号的合规复合选择器能活下来」的用例）。

脚本不是包，用 `importlib.util.spec_from_file_location` 从路径加载。`ROOT` 是模块级
`Path` 常量，凡是跑 `main()` 的用例一律 `monkeypatch.setattr` 指到 `tmp_path` 下自造的
`tests/e2e/`，**绝不写仓库**；唯一读真实仓库的是 S7（只读，且是本文件里被 mock 的那些
用例的真实路径对照）。没有任何用例碰 `books/`、导入 `reader3.py`、或在 `tmp_path` 之外落盘。

本文件自身含有 `data-modal` / `data-sheet` 字面量，那是固定装置，不是违规：
选择器 lint 只扫 `tests/e2e/`，命名 lint 只扫 `designs/` 与模板。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_PATH = REPO_ROOT / "scripts" / "lint_e2e_selectors.py"

# 八个名字**逐字抄自 ADR-0014 §Decision Outcome 的正文**，不是从 lint 的常量里拷的。
# 从常量拷等于让常量给自己判卷：常量里打错一个字，测试跟着一起错，两边一致地错。
ADR_0014_DISCRIMINATORS = (
    "data-book-id",
    "data-collection-id",
    "data-note-id",
    "data-annotation-id",
    "data-conversation-id",
    "data-provider",
    "data-section",
    "data-file-href",
)

ADR_LINK = "docs/adr/0014-bounded-testid-enumeration.md"

# S14 要清掉的旧约定原文（`lint_e2e_selectors.py` 模块 docstring 第 16 行）。
STALE_DOC_FRAGMENT = "第二种来自设计规格 §4 规则 5 的无界取值约定"


def _load_lint():
    spec = importlib.util.spec_from_file_location("lint_e2e_selectors_under_test", LINT_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {LINT_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_lint()


def run_main(module, capsys) -> Tuple[int, str]:
    """把 `main()` 的退出码与全部输出归一成 `(code, out)`。

    `main()` 目前只 `return`，不 `sys.exit`；这里仍然接住 `SystemExit`，
    这样「实现改成 sys.exit」不会把断言变成错误的绿或错误的红。
    """
    try:
        code = module.main()
    except SystemExit as exc:  # pragma: no cover - 现实现走不到
        raw = exc.code
        code = 0 if raw is None else raw if isinstance(raw, int) else 1
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def write_e2e(tmp_path: Path, name: str, source: str) -> Path:
    """在 `tmp_path/tests/e2e/` 下造一个被扫描的文件，并断言它确实落盘。"""
    target = tmp_path / "tests" / "e2e" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == source, "固定装置没写成，后面的断言全是空的"
    return target


def require_constant(module) -> set:
    """取 `ALLOWED_DISCRIMINATORS`；不存在就以断言失败告终，而不是 AttributeError。

    红阶段这条断言就是本批的第一条规格：闭合清单必须是**模块级常量**，
    因为 S9 要在调用期换掉它，文档与两条 lint 也都指向这一个定义处。
    """
    assert hasattr(module, "ALLOWED_DISCRIMINATORS"), (
        "scripts/lint_e2e_selectors.py 里没有模块级常量 ALLOWED_DISCRIMINATORS —— "
        f"闭合清单是 ADR-0014 的决定内容，必须有唯一定义处，见 {ADR_LINK}"
    )
    return set(module.ALLOWED_DISCRIMINATORS)


# --------------------------------------------------------------------------- S1


@pytest.mark.parametrize("attr", ADR_0014_DISCRIMINATORS)
def test_s1_eight_allowed_discriminators_are_compliant(mod, attr):
    """S1：八个准入判别位各自与 data-testid 配对，都合规。有界域上的穷举即完整规格。"""
    sel = f'[data-testid="x"][{attr}="v1"]'
    reason = mod.selector_ok(sel)
    assert reason is None, (attr, reason)


# --------------------------------------------------------------------------- S2


@pytest.mark.parametrize(
    "sel,attr",
    [
        ('[data-testid="lib-modal"][data-modal="add-books"]', "data-modal"),
        ('[data-testid="rd-sheet-close"][data-sheet="rd-ai-panel"]', "data-sheet"),
    ],
)
def test_s2_data_modal_and_data_sheet_are_violations_naming_the_attribute(mod, sel, attr):
    """S2：ADR-0014 的头条改动 —— 两个判别位出局，且报错要点名是哪一个属性。

    一条选择器里可以有三个属性，泛泛一句「复合选择器不合规」等于让人自己猜。
    """
    reason = mod.selector_ok(sel)
    assert reason is not None, f"{sel} 应当被拦下：{attr} 已被 ADR-0014 从契约里删除"
    assert attr in reason, (sel, reason)


# --------------------------------------------------------------------------- S3


@pytest.mark.parametrize(
    "attr",
    ["data-foo", "data-testid-2", "data-id", "data-state", "data-x"],
)
def test_s3_off_list_discriminator_is_a_violation(mod, attr):
    """S3：清单外的任意 `data-*` 都拦。

    `data-id` 与 `data-testid-2` 专治「按后缀放行」这类启发式实现。
    """
    sel = f'[data-testid="x"][{attr}="v"]'
    reason = mod.selector_ok(sel)
    assert reason is not None, f"{sel} 不在闭合清单内，应当被拦下"
    assert attr in reason, (sel, reason)


# --------------------------------------------------------------------------- S4


@pytest.mark.parametrize(
    "sel,fragment",
    [
        (".foo", None),
        ("#foo", None),
        ("div", None),
        ('div [data-testid="x"]', None),
        ('[data-testid="x"] > span', None),
        ('[data-testid="x"]:nth-child(2)', None),
        ("xpath=//div", "xpath="),
        ("css=.foo", "css="),
        ("text=Save", "text="),
        ('//div[@id="x"]', "//"),
        ("", "空选择器"),
        ("   ", "空选择器"),
    ],
)
def test_s4_pre_existing_interception_unchanged(mod, sel, fragment):
    """S4：验收条款「既有拦截行为不变」——旧的十二种形态一个都不能漏。

    引擎前缀与空串还额外钉住**报错文案**，这样「把它们改道走新的闭合清单分支」
    这种重构是看得见的（新分支会给出另一句话）。
    `.nth(` 不在这里 —— 它由 `main()` 的 NTH_RE 抓，见 S12 的第三行固定装置。
    """
    reason = mod.selector_ok(sel)
    assert reason is not None, sel
    if fragment == "空选择器":
        assert reason == "空选择器", (sel, reason)
    elif fragment is not None:
        assert fragment in reason, (sel, reason)


# --------------------------------------------------------------------------- S5


S5_SOURCE = '''page.locator('[data-testid="lib-modal"][data-modal="add-books"]')  # lint-e2e-selectors: allow
'''


def test_s5_allow_inline_releases_a_closed_list_violation(mod, tmp_path, monkeypatch, capsys):
    """S5：逐行逃生舱必须同样能放行「闭合清单」这条新检查。

    新检查最自然的落点是 `selector_ok`，而它对行一无所知；实现一旦把新检查
    放在 `allowed(line)` 之前的路径上，这条就红。
    扫描摘要用的是**全角逗号**，与 `lint_e2e_selectors.py:116` 一字不差 ——
    半角版本永远匹配不上，那样这条反空转断言就是死的。
    """
    write_e2e(tmp_path, "test_x.py", S5_SOURCE)
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    code, out = run_main(mod, capsys)

    assert code == 0, out
    assert "扫描 1 个文件，1 处选择器" in out, out  # 证明这处选择器被**看见并放行**，而不是压根没被扫到
    assert "选择器 lint 通过：0 处违规。" in out, out


# --------------------------------------------------------------------------- S6


@pytest.mark.parametrize(
    "sel",
    [
        '[data-testid="lib-book-card"]',
        '[data-testid="lib-book-card"][data-book-id="b1"][data-collection-id="c1"]',
    ],
)
def test_s6_single_testid_and_two_allowed_discriminators_are_compliant(mod, sel):
    """S6：元数 1 与元数 3 的边界。这条杀死「一律判违规」的假实现，也杀死只看 attrs[1] 的实现。"""
    assert mod.selector_ok(sel) is None, sel


# --------------------------------------------------------------------------- S7


#: `main()` 的扫描摘要。两个数都要，因为「扫了 25 个文件」与「看了 57 处选择器」
#: 各自会被不同的失效形态打到零：前者被坏掉的 ROOT，后者被「选择器提取正则不再匹配」。
SCAN_SUMMARY_RE = re.compile(r"扫描 (?P<files>\d+) 个文件，(?P<checked>\d+) 处选择器。")


def test_s7_real_repo_e2e_corpus_still_passes(mod, capsys):
    """S7：棘轮 —— 不打任何桩，用真实 ROOT 扫真实的 `tests/e2e/`。

    它是 S5 / S12 / S15 / S17 那些打了 ROOT 桩的用例的真实路径对照：那些用例证明
    `main()` 在**自造的**语料上判得对，只有这一条证明它在**真语料**上跑通。

    **为什么不接受「暂无用例」（2026-09-05 审计 · HIGH）。** 原判据是
    `("…0 处违规。" in out) or ("暂无用例" in out)`，也就是说：`ROOT` 指错、`SCAN_GLOBS`
    写坏、`tests/e2e/` 整个消失——任何让扫描面塌成空集的原因，都能让一条「证明真实用例树
    通过 lint」的用例绿着通过。空集通过的不是 lint，是虚无。「暂无用例」那条分支自有
    S15 在自造的空目录上钉着，本条不必也不该替它兜。

    所以判据改成：摘要必须在，两个数都必须为正，且以「0 处违规」收尾。
    数值只断**下界为正**，不断具体条数——写死 25/57 的话，红的会是「新增了一个 e2e 文件」
    这个动作本身，而修法与被改的东西无关（同 `E2E_BOOKS` 的取值理由）。
    """
    code, out = run_main(mod, capsys)
    assert code == 0, out

    m = SCAN_SUMMARY_RE.search(out)
    assert m is not None, (
        "真实 ROOT 下没有打印扫描摘要——说明 main() 走的是 files == 0 那条「暂无用例」分支："
        f"tests/e2e/ 扫不到任何文件（ROOT 指错？SCAN_GLOBS 写坏？）。输出：{out!r}"
    )
    files, checked = int(m.group("files")), int(m.group("checked"))
    assert files > 0, f"扫描到 0 个文件，本条证明不了任何事：{out!r}"
    assert checked > 0, (
        f"扫了 {files} 个文件却一处选择器都没看见——选择器提取（LOCATOR_CALL_RE / "
        f"DOLLAR_CALL_RE）多半已经匹配不上真实用例的写法了，零违规是空转来的：{out!r}"
    )
    assert "选择器 lint 通过：0 处违规。" in out, out


# --------------------------------------------------------------------------- S8


@pytest.mark.parametrize(
    "sel",
    [
        '[data-book-id="b1"]',
        '[data-book-id="b1"][data-collection-id="c1"]',
    ],
)
def test_s8_allowed_discriminator_without_testid_keeps_the_old_message(mod, sel):
    """S8：准入判别位但没有 data-testid —— 仍是违规，且必须是**旧**那句话。

    两个检查的先后顺序在这里可见：闭合清单检查如果排在 data-testid 存在性检查前面，
    就会对一条「缺 testid」的选择器报「判别位不在闭合清单内」，把人引向错的地方。
    """
    reason = mod.selector_ok(sel)
    assert reason is not None, sel
    assert "没有 data-testid" in reason, (sel, reason)


# --------------------------------------------------------------------------- S9


_S9_POOL = list(ADR_0014_DISCRIMINATORS) + ["data-modal", "data-sheet", "data-foo", "data-id"]


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    attrs=st.lists(st.sampled_from(_S9_POOL), min_size=0, max_size=3),
    raw_a=st.sets(st.sampled_from(_S9_POOL)),
    raw_b=st.sets(st.sampled_from(_S9_POOL)),
)
def test_s9_monotone_under_list_tightening(attrs, raw_a, raw_b):
    """S9：单调性 —— A ⊆ B 时，在 A 下合规必然在 B 下也合规；收紧只会拿掉合规，不会制造合规。

    外加一条 iff 刻画，这才让本条不是同义反复：它钉死了谓词本身，
    所以「在原来那套宽松检查上叠一张 data-modal 黑名单」这种实现会红（黑名单对白名单不单调）。

    这是全文件唯一给常量打桩的用例，因此也是 §0.3 实现约束 1 的执行者：
    `selector_ok()` 必须在**调用时**读模块全局，而不是把它捕获进默认参数。
    这里用 `pytest.MonkeyPatch.context()` 而非 monkeypatch 固定装置 ——
    函数域固定装置与 hypothesis 的 `@given` 混用会触发 HealthCheck。
    """
    module = _load_lint()
    assert hasattr(module, "ALLOWED_DISCRIMINATORS"), (
        "没有模块级常量 ALLOWED_DISCRIMINATORS，单调性无从谈起 —— 见 " + ADR_LINK
    )

    b = set(raw_b)
    a = set(raw_a) & b  # 构造保证 A ⊆ B
    sel = '[data-testid="x"]' + "".join(f'[{attr}="v"]' for attr in attrs)
    all_attrs = ["data-testid"] + list(attrs)

    def ok_under(allowed: set) -> bool:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(module, "ALLOWED_DISCRIMINATORS", set(allowed))
            return module.selector_ok(sel) is None

    ok_a = ok_under(a)
    ok_b = ok_under(b)

    assert (not ok_a) or ok_b, (sel, sorted(a), sorted(b))
    expected = "data-testid" in all_attrs and set(all_attrs) - {"data-testid"} <= a
    assert ok_a == expected, (sel, sorted(a), ok_a, expected)


# --------------------------------------------------------------------------- S10


def test_s10_closed_list_is_exactly_the_eight_items(mod):
    """S10：清单不增不减 —— 集合相等，不是包含，也不是长度。

    S1 在多出一个第九项时照样绿；只有这条能抓到「不改 ADR 就偷偷加一项」。
    """
    actual = require_constant(mod)
    assert actual == set(ADR_0014_DISCRIMINATORS), {
        "多出来的": sorted(actual - set(ADR_0014_DISCRIMINATORS)),
        "少掉的": sorted(set(ADR_0014_DISCRIMINATORS) - actual),
    }
    bad_shape = [a for a in sorted(actual) if not re.fullmatch(r"data-[a-z0-9-]+", a)]
    assert bad_shape == [], bad_shape
    assert "data-modal" not in actual, "ADR-0014 已把 data-modal 从契约里删除"
    assert "data-sheet" not in actual, "ADR-0014 已把 data-sheet 从契约里删除"


# --------------------------------------------------------------------------- S11


def test_s11_violation_message_names_attr_links_adr_and_states_the_procedure(mod):
    """S11：报错文案契约 —— 点名属性、给出 ADR 链接、说明新增判别位的手续。

    退化成一句「不允许」，就把一次 lint 失败变成一次考古。
    """
    reason = mod.selector_ok('[data-testid="x"][data-foo="v"]')
    assert reason is not None, "data-foo 不在闭合清单内，应当被拦下"
    assert "data-foo" in reason, reason
    assert ADR_LINK in reason, reason
    assert "无法枚举" in reason, reason


# --------------------------------------------------------------------------- S12


S12_SOURCE = '''page.locator('[data-testid="a"][data-modal="m"]')  # lint-e2e-selectors: allow
page.locator('[data-testid="b"][data-modal="m"]')
page.locator('.leaked')
'''


def test_s12_allow_inline_is_per_line_and_does_not_leak(mod, tmp_path, monkeypatch, capsys):
    """S12：逃生舱按行生效，不外溢到邻行（`allowed(line_no)` 的差一错误）。

    三行固定装置：第 1 行带记号的闭合清单违规、第 2 行不带记号的同类违规、第 3 行 class 选择器。
    期望恰好两处违规。断言用**完整的 rel:line 记号**：`main()` 打印的是 `  {rel}:{line}  …`，
    只断 `":1" not in out` 是不成立的 —— 路径里的 `:1`、两位数行号 `:12` 都会假匹配。
    """
    write_e2e(tmp_path, "test_leak.py", S12_SOURCE)
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    code, out = run_main(mod, capsys)

    assert code == 1, out
    assert "违规（2 处）" in out, out
    assert "tests/e2e/test_leak.py:2" in out, out
    assert "tests/e2e/test_leak.py:3" in out, out
    assert "tests/e2e/test_leak.py:1" not in out, out


# --------------------------------------------------------------------------- S13


_S13_ADVERSARIAL = [
    "[data-testid=]",
    '[data-testid="unclosed',
    '[[data-testid="x"]]',
    '[data-testid="a"][',
    'data-testid="x"',
    '"',
    "\x00",
]


@pytest.mark.parametrize("sel", _S13_ADVERSARIAL)
def test_s13_selector_ok_is_total_and_deterministic_on_adversarial_input(mod, sel):
    """S13（定向部分）：畸形输入下也不抛，返回 None 或 str，重复调用结果相等。"""
    first = mod.selector_ok(sel)
    assert first is None or isinstance(first, str), (sel, type(first))
    assert mod.selector_ok(sel) == first, sel


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(sel=st.text())
def test_s13_selector_ok_is_total_and_deterministic_on_arbitrary_text(sel):
    """S13（性质部分）：对任意文本全域可用且确定。

    全域性抓的是实现闭合清单时顺手写下的 `attrs[1]` 一类索引（IndexError）；
    确定性抓的是模块级记忆化（用可变对象当键，第二次就变了）。
    """
    module = _load_lint()
    first = module.selector_ok(sel)
    assert first is None or isinstance(first, str), (repr(sel), type(first))
    assert module.selector_ok(sel) == first, repr(sel)


# --------------------------------------------------------------------------- S14


def test_s14_module_docstring_points_at_adr_0014(mod):
    """S14：文档契约 —— docstring 指向 ADR-0014，且旧的无界约定原文已被搬走。

    自认弱：这是一条文档断言。留着，因为 ADR-0014 §Migration Strategy 第 2 步把
    「搬，不抄」列为交付物，而在一个由 LLM 改的仓库里，仍在宣称旧规则的注释
    是错误行为的活跃来源，不只是过时。
    """
    doc = mod.__doc__ or ""
    assert "0014-bounded-testid-enumeration" in doc, doc
    assert STALE_DOC_FRAGMENT not in doc, "旧的『无界取值约定』原文仍留在 docstring 里"


# --------------------------------------------------------------------------- S15


def test_s15_empty_corpus_still_exits_zero_with_its_own_message(mod, tmp_path, monkeypatch, capsys):
    """S15：`files == 0` 分支 —— 「没有文件」要与「零违规」在输出上仍然可区分。"""
    assert not (tmp_path / "tests" / "e2e").exists(), "本条要的就是根本没有 tests/e2e/"
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    code, out = run_main(mod, capsys)

    assert code == 0, out
    assert "暂无用例" in out, out


# --------------------------------------------------------------------------- S16


def test_s16_data_file_href_retention_rationale_is_in_the_source(mod):
    """S16：`data-file-href` 的保留理由必须写在源码里。

    ADR-0014 §Neutral 记录它当前只有 1 处使用，因此它是最可能被「没人用，删了吧」
    清掉的一项 —— 清掉之后 S10 会红，但红得没有解释。
    自认弱：与 S14 同类的文档断言。
    """
    text = LINT_PATH.read_text(encoding="utf-8")
    occurrences = text.count("data-file-href")
    assert occurrences >= 2, (
        f"源码里 data-file-href 只出现 {occurrences} 次；应至少两次："
        "一次在 ALLOWED_DISCRIMINATORS 里，一次在说明为何保留的注释里"
    )

    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if "data-file-href" in line]
    assert hits, "上一条断言已保证有出现，这里不该为空"
    region_lines: list[str] = []
    for i in hits:
        region_lines.extend(lines[max(0, i - 3): i + 4])
    region = "\n".join(region_lines)
    assert ("1 处" in region) or ("保留" in region), region


# --------------------------------------------------------------------------- S17


S17_SOURCE = '''page.locator('[data-testid="lib-book-card"][data-book-id="b1"]')
'''


def test_s17_compliant_composite_selector_survives_main_unmarked(mod, tmp_path, monkeypatch, capsys):
    """S17：一条合规的复合选择器，**不带放行记号**，要活着走完整个 `main()`。

    这是本文件补的洞：S1/S6 直接调 `selector_ok`；S5 只从逃生舱通过；S7 的真实语料两处
    选择器都带 `ALLOW_INLINE`。于是在 S17 之前，「凡复合选择器一律违规、靠满地 ALLOW_INLINE
    过活」的实现能同时通过 S1、S5、S7 与全部失败用例。只有这条能判它死。
    扫描摘要那句同时钉住 `checked` 计入了这处选择器，而不是把它跳过去。
    """
    write_e2e(tmp_path, "test_ok.py", S17_SOURCE)
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    code, out = run_main(mod, capsys)

    assert code == 0, out
    assert "扫描 1 个文件，1 处选择器" in out, out
    assert "选择器 lint 通过：0 处违规。" in out, out
    assert "违规（" not in out, out
