"""`scripts/lint_testid_naming.py` 的同文件内 testid 唯一性检查 ＋ 显式豁免登记。

矩阵：`.claude/tdd-guardian/tests-20260831-131500.md` U1–U23（WI-1）与 R1–R4（WI-6）。
权威：`docs/adr/0014-bounded-testid-enumeration.md`（Decision Outcome ＋ Migration Strategy）。
风格先例：`tests/unit/test_coverage_gate_failclosed.py`。

被测的是 `main()`。脚本不是包，所以用 `importlib.util.spec_from_file_location` 从路径加载。
它把 `ROOT` 写死成模块级常量，合成用例一律 `monkeypatch.setattr(mod, "ROOT", tmp_path)`
再往 `SCAN_GLOBS` 命中的相对路径下写文件——写不到那三个 glob 底下，lint 根本看不见。
`UNIQUENESS_EXEMPTIONS` 同理注入，免得豁免*机制*的测试挂在生产登记表的内容上。

**绝不碰 `books/`**（`tests/conftest.py` 记着 `process_epub()` 会 `shutil.rmtree()` 输出目录），
不 import `reader3.py`，除 `tmp_path` 外不写任何地方；U8 / R2 / R3 / R4 只读真实仓库。

矩阵 §0.4 规定了两段新报文的逐字格式，§0.5 规定「先断提取到的条数再断内容」，
§0「self-guarding rule」规定：断言若能在「压根没读文件」的实现下也成立，就必须额外断
`扫描 N 个文件`。本文件里的 U3 / U5 / U7 / U12(clean) / U13 / U14 / U17 / U21 / U22 都带这条护栏。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import tempfile
from pathlib import Path
from typing import Dict, Iterator, Optional, Set, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NAMING_LINT = REPO_ROOT / "scripts" / "lint_testid_naming.py"
TOKEN_REFS_LINT = REPO_ROOT / "scripts" / "lint_token_refs.py"
SETTINGS_JSX = REPO_ROOT / "designs" / "reader-pro-next" / "settings.jsx"

# 报文里的固定串。全角逗号/括号是契约的一部分（矩阵 §0.4），半角写法测不到东西。
UNIQ_HEADER = "同文件内重名的 testid"
DANGLING_HEADER = "失效的唯一性豁免"
SHAPE_HEADER = "不合规的 testid 名"
EXPR_HEADER = "拼接出来的 testid"
PASS_LINE = "命名 lint 通过：0 处违规。"

_MISSING = object()


# ---------------------------------------------------------------------------
# 加载与调用
# ---------------------------------------------------------------------------
def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"无法从 {path} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    """被测脚本。module 作用域——`@given` 用例不能依赖 function 作用域 fixture。"""
    return _load(NAMING_LINT, "lint_testid_naming_under_test")


def call_main(module) -> Tuple[int, str]:
    """把 `main()` 的两条退出路径归一成 `(退出码, 全部输出)`。

    不用 capsys：`@given` 的属性用例不能依赖 function 作用域 fixture，
    两边共用同一个 runner 才能保证例子用例与属性用例断的是同一段文本。
    """
    out, err = io.StringIO(), io.StringIO()
    payload = ""
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main()
        except SystemExit as exc:  # sys.exit(...) 路径
            raw = exc.code
            if raw is None:
                code = 0
            elif isinstance(raw, int):
                code = raw
            else:
                code = 1
                payload = str(raw)
    return code, out.getvalue() + err.getvalue() + payload


def require_exemptions_constant(module) -> None:
    """§0.3 约束 2：`UNIQUENESS_EXEMPTIONS` 必须是模块级 dict[(rel, literal) -> reason]。

    只有 R1 / R3 直接依赖生产常量本身，所以存在性由它们断言。注入型用例用
    `raising=False` 注入，好让它们在**行为**上变红（「重名没被报出来」），
    而不是三十条用例齐刷刷倒在同一句 hasattr 上——那种红说明不了规格。
    """
    assert hasattr(module, "UNIQUENESS_EXEMPTIONS"), (
        "scripts/lint_testid_naming.py 尚无模块级常量 UNIQUENESS_EXEMPTIONS："
        "ADR-0014 要求 dict[tuple[str, str], str]，键是 (仓库相对 POSIX 路径, testid 字面量)"
    )
    assert isinstance(module.UNIQUENESS_EXEMPTIONS, dict), (
        f"UNIQUENESS_EXEMPTIONS 必须是 dict，实际是 {type(module.UNIQUENESS_EXEMPTIONS)!r}"
    )


def patch_env(module, monkeypatch, root: Path, exemptions: Dict[Tuple[str, str], str]) -> None:
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "UNIQUENESS_EXEMPTIONS", dict(exemptions), raising=False)


@contextlib.contextmanager
def patched_env(
    module, root: Path, exemptions: Dict[Tuple[str, str], str]
) -> Iterator[None]:
    """`@given` 用的手工版 monkeypatch —— hypothesis 与 function 作用域 fixture 不兼容。"""
    old_root = module.ROOT
    old_exempt = getattr(module, "UNIQUENESS_EXEMPTIONS", _MISSING)
    module.ROOT = root
    module.UNIQUENESS_EXEMPTIONS = dict(exemptions)
    try:
        yield
    finally:
        module.ROOT = old_root
        if old_exempt is _MISSING:
            del module.UNIQUENESS_EXEMPTIONS
        else:
            module.UNIQUENESS_EXEMPTIONS = old_exempt


def run_in(module, root: Path, exemptions: Dict[Tuple[str, str], str]) -> Tuple[int, str]:
    with patched_env(module, root, exemptions):
        return call_main(module)


# ---------------------------------------------------------------------------
# fixture 助手
# ---------------------------------------------------------------------------
def write_scanned(root: Path, rel: str, body: str) -> Path:
    """rel 必须落在某条 SCAN_GLOBS 下，否则 lint 永远看不到这个文件（U23 钉住那三条 glob）。"""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def lines(*rows: str) -> str:
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# 输出解析（§0.5 反空转：解析不到东西一律炸，不许静默返回空集）
# ---------------------------------------------------------------------------
_DETAIL_RE = re.compile(r"'(?P<lit>[^']*)'\s*×(?P<count>\d+)\s*行\s*(?P<lines>[\d,\s]+)")


def _uniqueness_section(out: str) -> Optional[str]:
    idx = out.find(UNIQ_HEADER)
    if idx == -1:
        return None
    rest = out[idx:]
    end = rest.find("\n\n")
    return rest if end == -1 else rest[:end]


def _declared_count(out: str) -> int:
    m = re.search(re.escape(UNIQ_HEADER) + r"（(\d+) 处）", out)
    assert m is not None, f"唯一性小节的标题不是「{UNIQ_HEADER}（N 处）」：{out!r}"
    return int(m.group(1))


def _dup_groups(out: str) -> Dict[str, Set[int]]:
    """唯一性小节里的 {字面量: 行号集合}；小节不存在时返回 {}。

    小节存在却解析不出任何明细行 —— 或明细条数与标题里的 N 对不上 —— 一律判失败，
    否则「regex 一个也没匹配到」会让下游断言全部空转（§0.5 说这是本文件最大的失败模式）。
    """
    section = _uniqueness_section(out)
    if section is None:
        return {}
    groups: Dict[str, Set[int]] = {}
    for line in section.splitlines()[1:]:
        m = _DETAIL_RE.search(line)
        if m is None:
            continue
        nums = {int(n) for n in re.findall(r"\d+", m.group("lines"))}
        assert nums, f"明细行没有行号：{line!r}"
        assert len(nums) == int(m.group("count")), (
            f"×{m.group('count')} 与行号 {sorted(nums)} 对不上：{line!r}"
        )
        groups[m.group("lit")] = nums
    assert groups, (
        f"打了「{UNIQ_HEADER}」小节却解析不出任何 "
        f"「{{rel}}  {{literal!r}}  ×N  行 l1, l2」明细行：{out!r}"
    )
    declared = _declared_count(out)
    assert len(groups) == declared, (
        f"标题声称 {declared} 处，明细里只有 {len(groups)} 组：{sorted(groups)}；{out!r}"
    )
    return groups


def _dup_lines(out: str, literal: str) -> Set[int]:
    groups = _dup_groups(out)
    assert literal in groups, f"唯一性小节没有点名 {literal!r}：{out!r}"
    return groups[literal]


def _reported_literals(out: str) -> Set[str]:
    return set(_dup_groups(out))


# ===========================================================================
# U1：同文件同一个 data-testid 字面量出现两次 → 点名，且带上每一个行号
# ===========================================================================
U1_REL = "src/reader3_app/web/templates/dup.html"
U1_BODY = lines(
    '<dialog data-testid="lib-modal-add-books">',
    '  <button data-testid="lib-modal-add-books-close">x</button>',
    "</dialog>",
    '<dialog data-testid="lib-modal-add-books">',
    '  <button data-testid="lib-modal-index-errors-close">x</button>',
    "</dialog>",
)


def test_u1_same_file_duplicate_literal_named_with_every_line(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U1_REL, U1_BODY)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, f"同文件重名应当判违规，实际退出码 {code}：{out!r}"
    assert U1_REL in out, f"报文里没有出问题的文件路径：{out!r}"
    assert "'lib-modal-add-books'" in out, f"报文里没有 repr 引起来的字面量：{out!r}"
    # 只报第二次出现的实现会在这里挂 —— 这条才让本用例不只是「它红了」。
    assert _dup_lines(out, "lib-modal-add-books") == {1, 4}, out


# ===========================================================================
# U2：跨形态重名 —— 三种产生字面量的扫描形态两两配对，六种全覆盖
# ===========================================================================
def _emit_attr(_i: int) -> str:
    return '<div data-testid="rd-dup-name"></div>'


def _emit_prop(_i: int) -> str:
    return '<Sheet testId="rd-dup-name" />'


def _emit_table(i: int) -> str:
    return f'const RD_X{i}_TESTID = {{\n  a: "rd-dup-name",\n}};'


_EMITTERS = {"attr": _emit_attr, "prop": _emit_prop, "table": _emit_table}


@pytest.mark.parametrize(
    "first,second",
    [
        ("attr", "attr"),
        ("prop", "prop"),
        ("table", "table"),
        ("attr", "prop"),
        ("attr", "table"),
        ("prop", "table"),
    ],
)
def test_u2_cross_form_duplicates(mod, tmp_path, monkeypatch, first, second):
    body = _EMITTERS[first](0) + "\n" + _EMITTERS[second](1) + "\n"
    write_scanned(tmp_path, "designs/reader-pro-next/mix.jsx", body)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    # 三个计数器分形态各自查重的实现，前三个参数照样过，后三个必挂 —— 本用例的全部理由。
    assert code == 1, f"{first}+{second} 重名应当判违规，实际退出码 {code}：{out!r}"
    assert "'rd-dup-name'" in out, f"{first}+{second}：报文没点名字面量：{out!r}"
    assert len(_dup_lines(out, "rd-dup-name")) == 2, out


# ===========================================================================
# U3：同一字面量出现在两个不同文件 → 干净（ADR-0014 明写的盲区，不许被「改进」掉）
# ===========================================================================
def test_u3_same_literal_in_two_files_is_clean(mod, tmp_path, monkeypatch):
    body = '<div data-testid="lib-shared"></div>\n'
    write_scanned(tmp_path, "src/reader3_app/web/templates/a.html", body)
    write_scanned(tmp_path, "src/reader3_app/web/templates/b.html", body)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 0, f"跨文件同名不是违规，实际退出码 {code}：{out!r}"
    assert "扫描 2 个文件" in out, f"self-guard：两个文件都得真被扫到：{out!r}"
    assert "lib-shared" not in out, f"跨文件同名被误报了：{out!r}"


# ===========================================================================
# U4：一条豁免只放行一个 (文件, 字面量) 对，不是放行整个文件
# ===========================================================================
U4_REL = "designs/reader-pro-next/settings.jsx"
U4_BODY = lines(
    '{test === "ok" && <span data-testid="set-provider-result">OK</span>}',
    '{test === "fail" && <span data-testid="set-provider-result">Failed</span>}',
    '<span data-testid="set-other-dup">a</span>',
    '<span data-testid="set-other-dup">b</span>',
)
U4_REGISTRY = {(U4_REL, "set-provider-result"): "互斥分支"}


def test_u4_exemption_releases_one_pair_not_the_file(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U4_REL, U4_BODY)
    patch_env(mod, monkeypatch, tmp_path, U4_REGISTRY)

    code, out = call_main(mod)

    assert code == 1, f"未豁免的那组重名应当判违规，实际退出码 {code}：{out!r}"
    assert "'set-other-dup'" in out, f"未豁免的那组没被点名：{out!r}"
    # 否定的这半才分得开「放行了一个对」和「放行了整个文件」。
    assert "set-provider-result" not in out, f"已豁免的那组不该出现在任何小节：{out!r}"


# ===========================================================================
# U5：悬空豁免（登记了，但重名已经没了）→ fail-closed，并点名
# ===========================================================================
def test_u5_dangling_exemption_fails_closed(mod, tmp_path, monkeypatch):
    write_scanned(
        tmp_path,
        U4_REL,
        '{test === "ok" && <span data-testid="set-provider-result">OK</span>}\n',
    )
    patch_env(mod, monkeypatch, tmp_path, U4_REGISTRY)

    code, out = call_main(mod)

    assert code == 1, f"悬空豁免应当 fail-closed，实际退出码 {code}：{out!r}"
    assert DANGLING_HEADER in out, f"没有悬空豁免小节：{out!r}"
    assert U4_REL in out, f"悬空豁免没点名文件：{out!r}"
    assert "'set-provider-result'" in out, f"悬空豁免没点名字面量：{out!r}"
    # 上面三条都能从注入的登记表单独推出来；没有这条，压根不读文件的实现也能过。
    assert "扫描 1 个文件" in out, f"self-guard：文件没被真扫过：{out!r}"


# ===========================================================================
# U6：形状检查回归 —— `reader-` 前缀照旧判违规，照旧带提示
# ===========================================================================
def test_u6_shape_check_still_flags_page_prefix(mod, tmp_path, monkeypatch):
    write_scanned(
        tmp_path,
        "src/reader3_app/web/templates/legacy.html",
        lines(
            '<div data-testid="reader-shell"></div>',
            '<div data-testid="library-sidebar"></div>',
        ),
    )
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, f"页面全称前缀应当判违规，实际退出码 {code}：{out!r}"
    assert SHAPE_HEADER in out, f"形状违规小节不见了：{out!r}"
    assert "'reader-shell'" in out, out
    assert "'library-sidebar'" in out, out
    assert "页面全称前缀" in out, f"那条防止后来者加白名单的提示没了：{out!r}"


# ===========================================================================
# U7：完全唯一、完全 canonical 的树 → 退出 0，并打通过行
# ===========================================================================
def test_u7_clean_tree_exits_zero(mod, tmp_path, monkeypatch):
    write_scanned(
        tmp_path,
        "src/reader3_app/web/templates/ok.html",
        lines(
            '<dialog data-testid="lib-modal-add-books">',
            '  <button data-testid="lib-modal-add-books-close">x</button>',
            '  <button data-testid="lib-modal-add-books-primary">ok</button>',
            "</dialog>",
        ),
    )
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    # 承重的是这一条：它拦的是「整个文件 sys.exit(1)」这类实现。
    assert code == 0, f"干净的树不该判违规，实际退出码 {code}：{out!r}"
    assert "扫描 1 个文件" in out, f"self-guard：{out!r}"
    assert "3 个唯一 testid 名" in out, out
    assert PASS_LINE in out, out


# ===========================================================================
# U8：批次棘轮 —— 真实仓库 lint 全绿（不 patch 任何东西，只读）
# ===========================================================================
def test_u8_real_repo_lints_clean(mod):
    code, out = call_main(mod)

    # 红的时候，这里的 out 就是整批的进度显示：还剩哪几组重名没去掉。
    assert code == 0, out
    assert PASS_LINE in out, out


# ===========================================================================
# U9：幂等 —— 连跑两次，判决一致
# ===========================================================================
def test_u9_idempotent(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U4_REL, U4_BODY)
    patch_env(mod, monkeypatch, tmp_path, U4_REGISTRY)

    code1, out1 = call_main(mod)
    code2, out2 = call_main(mod)

    assert code1 == 1, f"第一次就该判违规：{out1!r}"
    # names / 重名计数器 / 已消费豁免集合被提到模块作用域时，第二次会报幻影重名。
    assert (code1, out1) == (code2, out2), f"两次运行不一致：\n{out1!r}\n{out2!r}"


# ===========================================================================
# U10：顺序无关 —— 判决对出现顺序的置换不变
# ===========================================================================
U10_LINES = (
    '<div data-testid="rd-a"></div>',
    '<div data-testid="rd-a"></div>',
    '<div data-testid="rd-b"></div>',
    '<Sheet testId="rd-c" />',
    '<Sheet testId="rd-c" />',
)
U10_LITERALS = ("rd-a", "rd-a", "rd-b", "rd-c", "rd-c")


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(order=st.permutations(range(len(U10_LINES))))
def test_u10_order_independent(mod, order):
    body = lines(*[U10_LINES[i] for i in order])
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        write_scanned(root, "designs/reader-pro-next/perm.jsx", body)
        code, out = run_in(mod, root, {})

    assert code == 1, f"order={order} 应当判违规：{out!r}"
    assert _reported_literals(out) == {"rd-a", "rd-c"}, f"order={order}：{out!r}"
    for lit in ("rd-a", "rd-c"):
        expected = {i + 1 for i, idx in enumerate(order) if U10_LITERALS[idx] == lit}
        assert _dup_lines(out, lit) == expected, f"order={order}, {lit}：{out!r}"


# ===========================================================================
# U11：出现三次 → 一组违规，带三个行号（不是 C(3,2)=3 组）
# ===========================================================================
def test_u11_three_occurrences_one_group(mod, tmp_path, monkeypatch):
    row = '<div data-testid="lib-x"></div>'
    write_scanned(tmp_path, "src/reader3_app/web/templates/triple.html", lines(row, row, row))
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, f"三次重名应当判违规，实际退出码 {code}：{out!r}"
    assert f"{UNIQ_HEADER}（1 处）" in out, f"分组数不是 1：{out!r}"
    assert "×3" in out, f"没打出现次数：{out!r}"
    assert _dup_lines(out, "lib-x") == {1, 2, 3}, out
    assert out.count("'lib-x'") == 1, f"两两比较式实现会打三次：{out!r}"


# ===========================================================================
# U12：`ATTR_EXPR_RE` 的行为逐字不变 —— 两个方向都要
# ===========================================================================
U12_REL = "designs/reader-pro-next/expr.jsx"


@pytest.mark.parametrize(
    "label,body,flagged,extra",
    [
        ("plus", '<div data-testid={t.root + "-close"}></div>\n', True, "t.root + "),
        ("template", "<div data-testid={`${p}-modal`}></div>\n", True, None),
        ("member", "<div data-testid={t.close}></div>\n", False, None),
        ("table-lookup", "<div data-testid={MODAL_TESTIDS[modal].close}></div>\n", False, None),
    ],
)
def test_u12_expression_concat_check_unchanged(
    mod, tmp_path, monkeypatch, label, body, flagged, extra
):
    write_scanned(tmp_path, U12_REL, body)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    if flagged:
        assert code == 1, f"{label}：拼接出来的 testid 应当判违规：{out!r}"
        assert EXPR_HEADER in out, f"{label}：拼接违规小节不见了：{out!r}"
        # 明细行必须指到第 1 行；不去逐字断表达式原文（实现可能转义或截断）。
        assert f"{U12_REL}:1" in out, f"{label}：明细行没指到出问题的行：{out!r}"
        if extra is not None:
            assert extra in out, f"{label}：明细行里没有表达式前缀 {extra!r}：{out!r}"
    else:
        # WI-4/WI-5 会正当地写出 {t.close} 与 {RD_SHEET_TESTIDS[testId].close}，
        # 干净这半就是让那些新原型代码得以存在的契约。
        assert code == 0, f"{label}：非拼接表达式不该判违规：{out!r}"
        assert EXPR_HEADER not in out, f"{label}：{out!r}"
        assert "扫描 1 个文件" in out, f"{label} self-guard：{out!r}"


# ===========================================================================
# U13：表达式形态不产生字面量，不进唯一性统计
# ===========================================================================
def test_u13_expression_form_not_counted_for_uniqueness(mod, tmp_path, monkeypatch):
    row = "<div data-testid={t.close}></div>"
    write_scanned(tmp_path, "designs/reader-pro-next/expr_dup.jsx", lines(row, row))
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 0, f"表达式形态不该进唯一性统计，实际退出码 {code}：{out!r}"
    assert UNIQ_HEADER not in out, f"表达式被当成字面量查重了：{out!r}"
    assert "t.close" not in out, out
    assert "扫描 1 个文件" in out, f"self-guard：{out!r}"
    assert PASS_LINE in out, out


# ===========================================================================
# U14：`PROP_LITERAL_RE` 的大小写敏感保持不变
# ===========================================================================
def test_u14_prop_regex_stays_case_sensitive(mod, tmp_path, monkeypatch):
    write_scanned(
        tmp_path,
        "designs/reader-pro-next/case.jsx",
        lines('<div data-testid="rd-panel"></div>', '<Sheet testid="rd-panel" />'),
    )
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    # 承重的是退出码：加了 re.IGNORECASE，同文件就有两处同名，这里立刻变 1。
    assert code == 0, f"小写 testid 不该被 PROP_LITERAL_RE 收进来，实际退出码 {code}：{out!r}"
    assert "1 个唯一 testid 名" in out, out
    assert "扫描 1 个文件" in out, f"self-guard：{out!r}"


# ===========================================================================
# U15：守恒 —— 每一组重名要么被报，要么被豁免，绝不凭空消失
# ===========================================================================
U15_REL = "designs/reader-pro-next/cons.jsx"


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_u15_conservation(mod, data):
    counts = data.draw(
        st.lists(st.integers(min_value=2, max_value=3), min_size=1, max_size=4), label="counts"
    )
    k = len(counts)
    noise = data.draw(st.integers(min_value=0, max_value=2), label="noise")
    flags = data.draw(
        st.lists(st.booleans(), min_size=k, max_size=k), label="exempt_flags"
    )

    dups = [f"rd-dup-{i}" for i in range(k)]
    rows = []
    for lit, n in zip(dups, counts):
        rows.extend([f'<div data-testid="{lit}"></div>'] * n)
    rows.extend(f'<div data-testid="rd-noise-{i}"></div>' for i in range(noise))

    exempt = {lit for lit, flag in zip(dups, flags) if flag}
    registry = {(U15_REL, lit): "generated" for lit in exempt}

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        write_scanned(root, U15_REL, lines(*rows))
        code, out = run_in(mod, root, registry)

    reported = _reported_literals(out)
    ctx = f"counts={counts} noise={noise} exempt={sorted(exempt)}：{out!r}"

    # 1. 守恒：不丢、不造。等号（而非 ⊆）同时否掉「全报一遍还顺便认豁免」
    #    和「靠跳过整个文件来认豁免」两种实现。
    assert reported == set(dups) - exempt, ctx
    # 2. 被豁免的绝不出现在违规里
    assert reported & exempt == set(), ctx
    # 3. 注入的豁免条条都是活的
    assert DANGLING_HEADER not in out, ctx
    # 4. 全豁免才绿；noise 字面量永远不影响判决
    assert (code == 0) == (len(exempt) == k), f"code={code}；{ctx}"


# ===========================================================================
# U16：一次运行里既有悬空豁免又有活重名 → 两者都要报
# ===========================================================================
def test_u16_dangling_and_live_reported_together(mod, tmp_path, monkeypatch):
    rel = "designs/reader-pro-next/both.jsx"
    write_scanned(
        tmp_path,
        rel,
        lines(
            '<div data-testid="set-gone-once"></div>',
            '<div data-testid="set-live-dup"></div>',
            '<div data-testid="set-live-dup"></div>',
        ),
    )
    patch_env(mod, monkeypatch, tmp_path, {(rel, "set-gone-once"): "stale"})

    code, out = call_main(mod)

    assert code == 1, f"实际退出码 {code}：{out!r}"
    # 报完第一节就 return 1 的实现，会把一次能修完的 5 个问题拆成 5 个来回。
    assert UNIQ_HEADER in out, out
    assert "'set-live-dup'" in out, out
    assert DANGLING_HEADER in out, out
    assert "'set-gone-once'" in out, out


# ===========================================================================
# U17：指向不存在的文件 / 指向扫描范围外的文件的豁免，都算悬空
# ===========================================================================
@pytest.mark.parametrize(
    "key",
    [
        ("designs/reader-pro-next/nope.jsx", "rd-x"),
        ("README.md", "lib-readme"),
    ],
    ids=["missing-file", "out-of-scan-scope"],
)
def test_u17_exemption_binding_to_nothing_is_dangling(mod, tmp_path, monkeypatch, key):
    write_scanned(
        tmp_path,
        "src/reader3_app/web/templates/ok.html",
        '<div data-testid="lib-ok"></div>\n',
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        lines('data-testid="lib-readme"', 'data-testid="lib-readme"'), encoding="utf-8"
    )
    patch_env(mod, monkeypatch, tmp_path, {key: "stale"})

    code, out = call_main(mod)

    assert code == 1, f"{key} 应当算悬空豁免，实际退出码 {code}：{out!r}"
    assert DANGLING_HEADER in out, out
    assert key[0] in out, f"没点名登记表里的路径：{out!r}"
    assert f"'{key[1]}'" in out, f"没点名登记表里的字面量：{out!r}"
    # self-guard，同时钉住第二个参数的真正主张：README.md 没被算成扫过的文件。
    assert "扫描 1 个文件" in out, out


# ===========================================================================
# U18：同一文件里既有形状违规又有唯一性违规 → 两节都在，退出 1
# ===========================================================================
def test_u18_shape_and_uniqueness_both_reported(mod, tmp_path, monkeypatch):
    write_scanned(
        tmp_path,
        "src/reader3_app/web/templates/mixed.html",
        lines(
            '<div data-testid="reader-shell"></div>',
            '<div data-testid="lib-dup"></div>',
            '<div data-testid="lib-dup"></div>',
        ),
    )
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, f"实际退出码 {code}：{out!r}"
    assert SHAPE_HEADER in out, f"既有的形状小节被新代码吞了：{out!r}"
    assert "'reader-shell'" in out, out
    assert UNIQ_HEADER in out, out
    assert "'lib-dup'" in out, out


# ===========================================================================
# U19：违规报文必须带静态近似的告诫与 ADR 指针
# ===========================================================================
def test_u19_message_carries_caveat_and_adr_pointer(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U1_REL, U1_BODY)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, out
    # ADR-0014 要求实现不得暗示 lint 证明了 DOM 唯一性；这条是该要求的唯一执行点。
    assert "静态近似" in out, out
    assert "跨文件" in out, out
    assert "docs/adr/0014-bounded-testid-enumeration.md" in out, out


# ===========================================================================
# U20：单调性 —— 加一次重名只能变坏，加一个新名字什么都不变
# ===========================================================================
_TOKEN = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=6)
_CANONICAL_NAME = st.builds(
    lambda prefix, tokens: prefix + "-" + "-".join(tokens),
    st.sampled_from(["lib", "rd", "set"]),
    st.lists(_TOKEN, min_size=1, max_size=3),
)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pair=st.tuples(_CANONICAL_NAME, _CANONICAL_NAME).filter(lambda p: p[0] != p[1]))
def test_u20_monotonicity(mod, pair):
    literal, other = pair
    # 不手抄正则：用被测模块导出的那一份来确认生成的名字确实 canonical。
    assert mod.CANONICAL.match(literal), literal
    assert mod.CANONICAL.match(other), other

    def run(rows) -> Tuple[int, str]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_scanned(root, "designs/reader-pro-next/mono.jsx", lines(*rows))
            return run_in(mod, root, {})

    base = [f'<div data-testid="{literal}"></div>']
    code1, out1 = run(base)
    code2, out2 = run(base + [f'<div data-testid="{literal}"></div>'])
    code3, out3 = run(base + [f'<div data-testid="{other}"></div>'])

    assert code1 == 0, f"{literal}：单次出现不该违规：{out1!r}"
    assert code2 == 1, f"{literal}：第二次出现应当违规：{out2!r}"
    assert f"'{literal}'" in out2, out2
    # 第三次跑是防止这条检查退化成「testid 越多越坏」。
    assert code3 == 0, f"{literal}+{other}：新字面量不该改变判决：{out3!r}"


# ===========================================================================
# U21：既不 canonical 又重名的字面量 → 两节都点名它
# ===========================================================================
U21_REL = "src/reader3_app/web/templates/bad_dup.html"
U21_BODY = lines(
    '<div data-testid="reader-dup"></div>',
    '<div data-testid="reader-dup"></div>',
)


def test_u21_non_canonical_and_duplicated_hits_both_sections(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U21_REL, U21_BODY)
    patch_env(mod, monkeypatch, tmp_path, {})

    code, out = call_main(mod)

    assert code == 1, f"实际退出码 {code}：{out!r}"
    assert SHAPE_HEADER in out, out
    assert UNIQ_HEADER in out, out
    # 每节各一次：这个精确条数才证明它没有被其中一个检查「吃掉」。
    hits = out.count("'reader-dup'")
    assert hits == 2, f"应当在形状小节与唯一性小节各出现一次，实际 {hits} 次：{out!r}"
    assert _dup_lines(out, "reader-dup") == {1, 2}, out
    assert "扫描 1 个文件" in out, f"self-guard：{out!r}"


# ===========================================================================
# U22：同一个非 canonical 重名被豁免 → 唯一性放行，形状照报
# ===========================================================================
def test_u22_exemption_does_not_launder_a_bad_name(mod, tmp_path, monkeypatch):
    write_scanned(tmp_path, U21_REL, U21_BODY)
    patch_env(mod, monkeypatch, tmp_path, {(U21_REL, "reader-dup"): "generated"})

    code, out = call_main(mod)

    # 豁免只该压住唯一性发现；压住形状检查就是登记者从未打算授予的提权。
    assert code == 1, f"形状违规仍然成立，实际退出码 {code}：{out!r}"
    assert SHAPE_HEADER in out, out
    assert out.count("'reader-dup'") == 1, (
        f"只该在形状小节出现一次：{out!r}"
    )
    assert UNIQ_HEADER not in out, out
    assert DANGLING_HEADER not in out, out
    assert "扫描 1 个文件" in out, f"self-guard：{out!r}"


# ===========================================================================
# U23：`SCAN_GLOBS` 就是那三条生产 glob（钉住被 mock 的常量的生产取值）
# ===========================================================================
def test_u23_scan_globs_are_exactly_the_three_production_patterns(mod):
    assert set(mod.SCAN_GLOBS) == {
        "designs/reader-pro-next/**/*.jsx",
        "designs/reader-pro-next/**/*.html",
        "src/reader3_app/web/templates/*.html",
    }, mod.SCAN_GLOBS


# ===========================================================================
# R1：生产豁免登记表恰好一条
# ===========================================================================
def test_r1_production_registry_has_exactly_one_entry(mod):
    require_exemptions_constant(mod)

    # 用集合相等而不是 len() == 1 —— 一条写错的登记同样满足 len。
    assert set(mod.UNIQUENESS_EXEMPTIONS) == {
        ("designs/reader-pro-next/settings.jsx", "set-provider-result")
    }, mod.UNIQUENESS_EXEMPTIONS

    reason = mod.UNIQUENESS_EXEMPTIONS[
        ("designs/reader-pro-next/settings.jsx", "set-provider-result")
    ]
    assert isinstance(reason, str) and reason.strip(), f"豁免理由是空的：{reason!r}"
    assert ("互斥" in reason) or ("ok" in reason and "fail" in reason), (
        f"理由没说清为什么这两处同名是合法的：{reason!r}"
    )


# ===========================================================================
# R2：`settings.jsx:79-80` 没有为了迎合 lint 而被合并
# ===========================================================================
def test_r2_settings_jsx_branches_not_merged():
    text = SETTINGS_JSX.read_text(encoding="utf-8")

    occurrences = [
        m.start() for m in re.finditer(re.escape('data-testid="set-provider-result"'), text)
    ]
    # 恰好 2 处，证明那条豁免今天仍然需要（R1 保持它单条，R2 保持重名为真）。
    assert len(occurrences) == 2, f"set-provider-result 出现 {len(occurrences)} 处"
    assert 'test === "ok"' in text, "互斥分支的 ok 那支不见了"
    assert 'test === "fail"' in text, "互斥分支的 fail 那支不见了"
    line_numbers = {text.count("\n", 0, pos) + 1 for pos in occurrences}
    assert len(line_numbers) == 2, f"两处应当在不同的行上：{sorted(line_numbers)}"


# ===========================================================================
# R3：豁免是承重的 —— 清空它，真实仓库变红，且恰好点名一个
# ===========================================================================
def test_r3_exemption_is_load_bearing(mod, monkeypatch):
    require_exemptions_constant(mod)
    monkeypatch.setattr(mod, "UNIQUENESS_EXEMPTIONS", {})

    code, out = call_main(mod)

    # U8 单独看，被「压根不查重」的实现满足；R3 证明查重是开着的。两条缺一不可。
    assert code == 1, out
    assert f"{UNIQ_HEADER}（1 处）" in out, (
        f"清空豁免后，整个仓库应当恰好剩一组同文件重名：{out!r}"
    )
    assert "'set-provider-result'" in out, out
    assert _reported_literals(out) == {"set-provider-result"}, out


# ===========================================================================
# R4：`lint_token_refs.py` 在真实仓库上仍然退出 0（附带损伤网）
# ===========================================================================
def test_r4_token_refs_lint_still_green():
    token_refs = _load(TOKEN_REFS_LINT, "lint_token_refs_under_test")
    code, out = call_main(token_refs)
    assert code == 0, out
