"""`scripts/check_coverage_gate.py` 的门禁必须 fail-closed（audit-008 WI-3）。

矩阵：`.claude/tdd-guardian/tests-20260824T074825Z.md` G1–G7。

被测的是 `main()`：`coverageMode` 只要不是逐字的 `"absolute"`（拼错、大小写不同、
键缺失、值不是字符串），旧实现就静默降级成「只报数」并 `exit 0` —— 一个看起来像
门禁的东西，实际不拦任何人。同类第二处：`coverageThresholds` 里写错的键（`branch`
少个 s）只在「跳过」那行打印一下，与 `functions` 那种合法跳过混在一起。

脚本不是包，所以用 `importlib.util.spec_from_file_location` 从路径加载。它把
`CONFIG` / `REPORT` 写死成模块级 `Path` 常量，所以这里一律 `monkeypatch.setattr`
指到 `tmp_path` 下自造的 json，**绝不读写仓库里那两份真文件**。唯一例外是 G7：
它只读真实的 `.claude/tdd-guardian/config.json`（只读，不写）。
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GATE_PATH = REPO_ROOT / "scripts" / "check_coverage_gate.py"
REAL_CONFIG = REPO_ROOT / ".claude" / "tdd-guardian" / "config.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("coverage_gate_under_test", GATE_PATH)
    assert spec is not None and spec.loader is not None, f"无法从 {GATE_PATH} 加载"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def run_gate(mod, capsys) -> Tuple[int, str]:
    """把 `main()` 的两条退出路径归一成 `(退出码, 全部输出)`。

    `main()` 既有 `return 1`，也有 `_load()` 那种 `sys.exit("消息")`（退出码 1，
    消息走 stderr）。只断其中一条的测试会被另一条绕过去。返回的文本里同时含
    stdout、stderr 和 `SystemExit` 携带的消息对象，所以「消息里要有原值」这类
    断言不依赖实现选了哪条路径。
    """
    payload = ""
    try:
        code = mod.main()
    except SystemExit as exc:  # sys.exit(...) 路径
        raw = exc.code
        if raw is None:
            code = 0
        elif isinstance(raw, int):
            code = raw
        else:
            code = 1
            payload = str(raw)
    captured = capsys.readouterr()
    return code, captured.out + captured.err + payload


def write_config(tmp_path: Path, monkeypatch, mod, cfg: Dict[str, Any]) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG", path)
    return path


def write_report(tmp_path: Path, monkeypatch, mod, report: Dict[str, Any]) -> Path:
    path = tmp_path / "coverage-unit.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(mod, "REPORT", path)
    return path


def perfect_report(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """一份不会因为阈值或 criticalPaths 而 FAIL 的报告。

    `criticalPaths` 的「匹配到 0 个文件判 FAIL」是既有语义，不在本 WI 范围内，
    所以报告按传入配置的 glob 造出满分文件条目 —— 否则 G1/G5/G6/G7 会因为一条
    与 `coverageMode` 无关的 FAIL 而变绿/变红，测的就不是这次要测的东西了。
    """
    files: Dict[str, Any] = {}
    for rule in cfg.get("criticalPaths") or []:
        glob = rule.get("glob") or rule.get("path") or ""
        candidate = glob.replace("*", "w").replace("?", "w").replace("[", "").replace("]", "")
        assert fnmatch.fnmatch(candidate, glob), f"无法为 glob 造出匹配文件：{glob}"
        files[candidate] = {
            "summary": {
                "covered_lines": 100,
                "num_statements": 100,
                "covered_branches": 100,
                "num_branches": 100,
            }
        }
    return {
        "totals": {
            "covered_lines": 100,
            "num_statements": 100,
            "covered_branches": 100,
            "num_branches": 100,
        },
        "files": files,
    }


def failing_report() -> Dict[str, Any]:
    """lines 1% —— 低于任何现实阈值。"""
    return {
        "totals": {
            "covered_lines": 1,
            "num_statements": 100,
            "covered_branches": 1,
            "num_branches": 100,
        },
        "files": {},
    }


# --------------------------------------------------------------------------
# G1: coverageMode 拼错 → 拦
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_mode", ["absolut", "Absolute", "ABSOLUTE", ""])
def test_typoed_coverage_mode_exits_nonzero(gate, tmp_path, monkeypatch, capsys, bad_mode):
    cfg = {"coverageMode": bad_mode, "coverageThresholds": {"lines": 70}}
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    code, text = run_gate(gate, capsys)

    assert code != 0, f"coverageMode={bad_mode!r} 应当拦下，实际退出码 {code}"
    if bad_mode:
        assert bad_mode in text, f"消息里没有读到的原值 {bad_mode!r}：{text!r}"
    # 只说「非法」的门禁，读的人还得自己去翻配置猜错在哪。
    assert "absolute" in text and "no-decrease" in text, f"消息里没列出合法取值：{text!r}"


# --------------------------------------------------------------------------
# G2: coverageMode 键缺失 → 拦
# --------------------------------------------------------------------------
def test_missing_coverage_mode_exits_nonzero(gate, tmp_path, monkeypatch, capsys):
    cfg = {"coverageThresholds": {"lines": 70}}
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    code, text = run_gate(gate, capsys)

    # 旧实现默认成 "no-decrease"，即最宽松的那一侧，然后 exit 0。
    assert code != 0, f"缺 coverageMode 应当拦下，实际退出码 {code}"
    assert "coverageMode" in text, f"消息里没点名是哪个字段：{text!r}"


# --------------------------------------------------------------------------
# G3: coverageMode 非字符串 → 拦，且不是 TypeError
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_mode", [True, 1, ["absolute"], None])
def test_non_string_coverage_mode_exits_nonzero(gate, tmp_path, monkeypatch, capsys, bad_mode):
    cfg = {"coverageMode": bad_mode, "coverageThresholds": {"lines": 70}}
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    try:
        code, text = run_gate(gate, capsys)
    except (TypeError, AttributeError) as exc:
        pytest.fail(f"coverageMode={bad_mode!r} 应当被拦成有话说的退出，而不是 {exc!r}")

    assert code != 0, f"coverageMode={bad_mode!r} 应当拦下，实际退出码 {code}"
    assert "absolute" in text and "no-decrease" in text, f"消息里没列出合法取值：{text!r}"


# --------------------------------------------------------------------------
# G4: 两个合法值的行为与修改前逐字一致
# --------------------------------------------------------------------------
def test_legal_modes_behave_exactly_as_before(gate, tmp_path, monkeypatch, capsys):
    report = failing_report()

    absolute_dir = tmp_path / "absolute"
    absolute_dir.mkdir()
    cfg_abs = {"coverageMode": "absolute", "coverageThresholds": {"lines": 70}}
    write_config(absolute_dir, monkeypatch, gate, cfg_abs)
    write_report(absolute_dir, monkeypatch, gate, report)
    code_abs, text_abs = run_gate(gate, capsys)

    assert code_abs == 1, f"absolute + 不达标报告应当 FAIL，实际退出码 {code_abs}"
    assert "FAIL" in text_abs, f"absolute 模式没有报 FAIL：{text_abs!r}"

    nodec_dir = tmp_path / "no-decrease"
    nodec_dir.mkdir()
    cfg_nodec = {"coverageMode": "no-decrease", "coverageThresholds": {"lines": 70}}
    write_config(nodec_dir, monkeypatch, gate, cfg_nodec)
    write_report(nodec_dir, monkeypatch, gate, report)
    code_nodec, text_nodec = run_gate(gate, capsys)

    # 「no-decrease 下不拦截」是 docstring 里写明了理由的既有决定，不在本 WI 范围。
    assert code_nodec == 0, f"no-decrease 不应拦截，实际退出码 {code_nodec}"
    assert "未生效" in text_nodec, f"no-decrease 没有宣告门禁未生效：{text_nodec!r}"


# --------------------------------------------------------------------------
# G5: coverageThresholds 里非零的未知键 → 拦
# --------------------------------------------------------------------------
def test_unknown_nonzero_threshold_key_exits_nonzero(gate, tmp_path, monkeypatch, capsys):
    cfg = {"coverageMode": "absolute", "coverageThresholds": {"lines": 70, "branch": 52}}
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    code, text = run_gate(gate, capsys)

    assert code != 0, f"未知阈值键 branch 应当拦下，实际退出码 {code}"
    assert "branch" in text, f"消息里没点名 branch：{text!r}"


# --------------------------------------------------------------------------
# G6: functions 仍是已知的合法跳过
# --------------------------------------------------------------------------
@pytest.mark.parametrize("functions_value", [0, 100])
def test_functions_threshold_is_a_known_legal_skip(
    gate, tmp_path, monkeypatch, capsys, functions_value
):
    cfg = {"coverageMode": "absolute", "coverageThresholds": {"functions": functions_value}}
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    code, text = run_gate(gate, capsys)

    # coverage.py 不按函数计数；G5 的检查不许误伤这个位子。
    assert code == 0, f"functions={functions_value} 是合法跳过，不该 FAIL：{text!r}"


# --------------------------------------------------------------------------
# G7: 仓库当前的真实配置不会被自己拦下
# --------------------------------------------------------------------------
def test_repo_config_passes_the_validator(gate, tmp_path, monkeypatch, capsys):
    assert REAL_CONFIG.is_file(), f"读不到真实配置：{REAL_CONFIG}"
    real_cfg = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))

    monkeypatch.setattr(gate, "CONFIG", REAL_CONFIG)  # 只读，不写
    write_report(tmp_path, monkeypatch, gate, perfect_report(real_cfg))

    code, text = run_gate(gate, capsys)

    assert code == 0, f"新校验把仓库自己的配置拦下了：{text!r}"


# --------------------------------------------------------------------------
# G8 (web/D2): 设了阈值却量不到 → 拦，不是 WARN
#
# 具体的回归形状：有人从 pyproject.toml 的 [tool.coverage.run] 里删掉
# `branch = true`（或者换一条不带 --cov-branch 的命令）。报告里 num_branches
# 归零，_pct() 老老实实返回 None —— 然后老实现把 branches 阈值 52 打印成一行
# WARN，退 0。门禁看起来在跑，实际上那一项已经不拦人了。
#
# 「量不到」和「不设门槛」必须是两件事：后者在 `if not want` 就 continue 了，
# 所以凡是走到 None 分支的指标，都是有人明确要求过它拦人的。
# --------------------------------------------------------------------------
def test_a_threshold_that_cannot_be_measured_fails_the_gate(
    gate, tmp_path, monkeypatch, capsys
):
    cfg = {"coverageMode": "absolute", "coverageThresholds": {"lines": 70, "branches": 52}}
    report = {
        "totals": {
            "covered_lines": 100,
            "num_statements": 100,
            # 分支覆盖没开时 coverage.py 就是这个形状
            "covered_branches": 0,
            "num_branches": 0,
        },
        "files": {},
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code != 0, (
        "branches 阈值 52 无法判定，门禁却退 0 —— 删掉 pyproject 的 branch = true "
        "就能让分支门槛静默消失，而 CI 仍然是绿的"
    )
    assert "branches" in out and "num_branches" in out, (
        f"失败信息必须指出是哪一项、为什么量不到，否则读的人只能去猜；实得：{out}"
    )


def test_an_unmeasurable_critical_path_fails_the_gate(gate, tmp_path, monkeypatch, capsys):
    """criticalPaths 是绝对门槛，「匹配到文件但没有分支」和「匹配到 0 个文件」同类。"""
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        "criticalPaths": [{"glob": "src/reader3_app/web/server.py", "branch": 60}],
    }
    report = {
        "totals": {"covered_lines": 100, "num_statements": 100},
        "files": {
            "src/reader3_app/web/server.py": {
                "summary": {
                    "covered_lines": 100,
                    "num_statements": 100,
                    "covered_branches": 0,
                    "num_branches": 0,
                }
            }
        },
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code != 0, "criticalPaths 的 branch 门槛量不到却放行了"
    assert "server.py" in out


def test_a_metric_with_no_threshold_is_still_not_a_failure(gate, tmp_path, monkeypatch, capsys):
    """反向守卫：不设阈值就是不设门槛，不能被上面那条顺手连坐。

    没有这条，把 `if not want: continue` 删掉也不会有测试变红，
    于是「量不到就拦」会悄悄扩张成「没测量过的指标一律拦」。
    """
    cfg = {"coverageMode": "absolute", "coverageThresholds": {"lines": 70, "branches": 0}}
    report = {
        "totals": {
            "covered_lines": 100,
            "num_statements": 100,
            "covered_branches": 0,
            "num_branches": 0,
        },
        "files": {},
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code == 0, f"branches 阈值为 0（= 不设门槛），不该因为量不到而拦人；实得：{out}"
