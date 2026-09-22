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


# ⚠️ 下面这条自 2026-09-19 起**是因为另一个原因绿的**，不要拿它当「设了却量不到」的
# 证据。它的配置用的是顶层 `"branch": 60`，而那个写法现在判配置错误（G11），于是它在
# 量任何东西之前就退非零了。原本要钉的语义改由 G10 用规范的嵌套写法承担。
# 这里**故意不动它**：它的行都在红收据 WI-T8 里，改了就是实现在改自己的规格。
# 两条合并成一条是一笔欠账（009 #34），要动它得先重录红证。
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


# --------------------------------------------------------------------------
# G9: criticalPaths 的门槛写在 rule["thresholds"] 里也必须真的拦人
#
# 回归形状是实际发生过的：0c1c8a2（2026-09-07，标题「criticalPaths 的 7 条逐文件
# 下限从来没生效过」）把配置从顶层 `"branch": N` 搬进 `"thresholds": {"branches": N}`，
# 因为 tdd-guardian 插件的 lib/config.js 只读 raw.thresholds。那次**只改了配置**，
# 本脚本的 `rule.get("branch") or rule.get("branches") or 0` 一行没动 —— 于是七条
# 下限从那天起全部读成 0，逐个 `>= 0%` 真空通过。同一个提交想消灭的状态，换了个
# 方向复发，活了 12 天没人撞见（commit 钩子只查 lane 新鲜度，不跑这个脚本）。
# --------------------------------------------------------------------------
def test_a_per_file_floor_written_under_thresholds_actually_binds(
    gate, tmp_path, monkeypatch, capsys
):
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        "criticalPaths": [
            {"glob": "src/reader3_app/web/server.py", "thresholds": {"branches": 80}}
        ],
    }
    report = {
        "totals": {
            "covered_lines": 100,
            "num_statements": 100,
            "covered_branches": 100,
            "num_branches": 100,
        },
        "files": {
            "src/reader3_app/web/server.py": {
                "summary": {
                    "covered_lines": 100,
                    "num_statements": 100,
                    # 10% —— 远低于配的 80%
                    "covered_branches": 10,
                    "num_branches": 100,
                }
            }
        },
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code != 0, (
        "branches: 80 写在 rule['thresholds'] 里，实测 10% 却放行 —— "
        f"门槛被读成了 0，逐文件下限形同虚设；实得：{out}"
    )
    assert "80" in out, f"失败信息里必须出现配的门槛值 80，否则看不出是跟谁比的：{out}"


# --------------------------------------------------------------------------
# G10: criticalPaths 的「设了却量不到」—— 用规范的嵌套写法重新钉一遍
#
# 与上面那条老的区别只有一处：配置写成 rule["thresholds"]["branches"]。
# 它必须因为「量不到」而红，而不是因为别的。所以这里断的是失败原因，不只是退出码。
# --------------------------------------------------------------------------
def test_an_unmeasurable_critical_path_fails_for_the_right_reason(
    gate, tmp_path, monkeypatch, capsys
):
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        "criticalPaths": [
            {"glob": "src/reader3_app/web/server.py", "thresholds": {"branches": 60}}
        ],
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

    assert code != 0, f"branches 门槛设了 60% 却量不到，门禁却放行；实得：{out}"
    assert "num_branches" in out, (
        f"失败信息必须说清「量不到」是什么意思（哪个字段为 0），否则读的人只能猜：{out}"
    )


# --------------------------------------------------------------------------
# G11: 逐文件门槛写在顶层 branch / branches 一律判配置错误
#
# 不做兼容回退，理由不是洁癖：这份配置有**两个**评判器。tdd-guardian 插件的
# lib/config.js 只读 raw.thresholds，顶层键它连看都不看。本脚本若兼容顶层写法，
# 得到的就是「CI 拦人、本地完全没有这道门槛」，而且没有任何人会被告知——
# 0c1c8a2 的提交信息自己写下的教训正是这一条。
# --------------------------------------------------------------------------
def test_a_misplaced_top_level_floor_is_a_configuration_error(
    gate, tmp_path, monkeypatch, capsys
):
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        # 覆盖率本身是满分的：唯一能让它红的只有「键放错了」这件事
        "criticalPaths": [{"glob": "src/reader3_app/web/server.py", "branch": 60}],
    }
    report = {
        "totals": {"covered_lines": 100, "num_statements": 100},
        "files": {
            "src/reader3_app/web/server.py": {
                "summary": {
                    "covered_lines": 100,
                    "num_statements": 100,
                    "covered_branches": 100,
                    "num_branches": 100,
                }
            }
        },
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code != 0, (
        "门槛写在顶层 branch 上，插件那一侧根本读不到，门禁却放行 —— "
        f"这正是 0c1c8a2 后活了 12 天的那个状态；实得：{out}"
    )
    assert "thresholds" in out, f"报错必须给出迁移目标 thresholds，否则修的人不知道往哪搬：{out}"


# --------------------------------------------------------------------------
# G12: 反向守卫 —— 一条规则不配 branches，不等于分支量不到就该拦
#
# 与 test_a_metric_with_no_threshold_is_still_not_a_failure 是同一条纪律的逐文件版。
# 没有这条，把「不设门槛就跳过」删掉不会有测试变红，于是 book_store.py 那种
# 0 分支的纯直线模块会被判成事故（2026-09-19 实测它就是这么红的）。
# --------------------------------------------------------------------------
def test_a_rule_that_sets_no_branch_floor_survives_a_branchless_file(
    gate, tmp_path, monkeypatch, capsys
):
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        "criticalPaths": [
            {
                "glob": "src/reader3_app/book_store.py",
                "thresholds": {"lines": 100, "statements": 100},
            }
        ],
    }
    report = {
        "totals": {"covered_lines": 100, "num_statements": 100},
        "files": {
            "src/reader3_app/book_store.py": {
                "summary": {
                    "covered_lines": 27,
                    "num_statements": 27,
                    # 纯直线代码：一个分支都没有，这不是事故
                    "covered_branches": 0,
                    "num_branches": 0,
                }
            }
        },
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, report)

    code, out = run_gate(gate, capsys)

    assert code == 0, (
        "这条规则刻意只压语句、不设分支门槛，却因为「没有分支可测」被拦下 —— "
        f"「不设门槛」被当成了「量不到」；实得：{out}"
    )
    assert "lines" in out and "statements" in out, (
        f"配了的那两项必须真的被判过，否则这条规则等于没配：{out}"
    )


# --------------------------------------------------------------------------
# G13: 一条门槛都不配的规则判 FAIL —— 与「匹配到 0 个文件」同类
# --------------------------------------------------------------------------
def test_a_rule_with_no_thresholds_at_all_fails(gate, tmp_path, monkeypatch, capsys):
    cfg = {
        "coverageMode": "absolute",
        "coverageThresholds": {},
        "criticalPaths": [{"glob": "src/reader3_app/web/server.py"}],
    }
    write_config(tmp_path, monkeypatch, gate, cfg)
    write_report(tmp_path, monkeypatch, gate, perfect_report(cfg))

    code, out = run_gate(gate, capsys)

    assert code != 0, f"一条什么都不判的 criticalPath 是一条永远绿的门槛，应当拦下：{out}"
