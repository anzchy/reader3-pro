#!/usr/bin/env python3
"""覆盖率门禁 —— CI 侧的执行者。

**为什么需要这个脚本。** 覆盖率阈值的唯一定义处是
`.claude/tdd-guardian/config.json` 的 `coverageThresholds` / `coverageMode` /
`criticalPaths`。那份配置驱动的是**本地** tdd-guardian 门禁；CI 里没有
tdd-guardian，如果在 workflow YAML 里再写一遍 `--cov-fail-under=70`，就有了两份
互相不知道对方存在的阈值。两份阈值只有一种结局：漂移，然后没人知道哪份是真的。
本脚本读那一份配置，所以 YAML 里不出现任何数字。

**零依赖，只用标准库**——与 `scripts/` 下其余四个脚本同口径，好让它在没装
开发依赖的环境里也能跑（`python3 scripts/check_coverage_gate.py`）。

**`no-decrease` 模式下它不拦截，只报数。** 那个模式的语义是「与上次运行相比不
下降」，而 CI 每次都是全新环境、没有上次运行。在这里假装能判定，只会给出一个
永远为绿的门禁——比没有门禁更糟，因为它看起来像有。所以那种模式下它把数字打
出来并明确宣告「门禁未生效」。008 收尾把 `coverageMode` 切成 `absolute` 之后，
这里才开始真的拦人。

**`criticalPaths` 在两种模式下都是绝对值**，所以它们始终生效。其中一条规则容易
反直觉：**匹配到零个文件的 glob 判 FAIL 而不是 PASS**。一个指向已被删除或改名的
模块的门槛，是一条永远绿的门槛；判它 FAIL 才能让改名的人立刻知道要更新配置。
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".claude" / "tdd-guardian" / "config.json"
REPORT = REPO_ROOT / "coverage-unit.json"

#: `coverageThresholds` 的键 → coverage.py JSON 里的 (已覆盖, 总数) 字段对。
#: `functions` 不在其中：coverage.py 不按函数计数，pytest-cov 的 JSON 里没有对应
#: 字段。配置里那个 `"functions": 0` 是 tdd-guardian 的通用 schema 留的位子，
#: 在 Python 侧无法判定 —— 判定不了的阈值不许假装判定，直接跳过并说明。
METRICS = {
    "lines": ("covered_lines", "num_statements"),
    "statements": ("covered_lines", "num_statements"),
    "branches": ("covered_branches", "num_branches"),
}


def _pct(covered: int, total: int) -> float | None:
    """总数为 0 时返回 None，而不是 100.0。

    `100%` 与 `没有可测的东西` 是两件完全不同的事。把后者显示成前者，会让一个
    完全没开分支覆盖的报告看起来是满分。上层拿到 None 时报 WARN，不报 PASS。
    """
    return None if total == 0 else covered * 100.0 / total


def _load() -> tuple[dict, dict]:
    if not CONFIG.is_file():
        sys.exit(f"读不到阈值配置：{CONFIG}")
    if not REPORT.is_file():
        sys.exit(
            f"读不到覆盖率报告：{REPORT}\n"
            "先跑 unit lane 生成它："
            "uv run pytest tests/unit tests/contract --cov=src/reader3_app "
            "--cov-report=json:coverage-unit.json"
        )
    return json.loads(CONFIG.read_text()), json.loads(REPORT.read_text())


def _check_totals(cfg: dict, totals: dict, enforcing: bool) -> list[str]:
    failures: list[str] = []
    thresholds = cfg.get("coverageThresholds", {})
    print("\n总体覆盖率")
    print(f"{'指标':<12}{'实测':>10}{'阈值':>10}   判定")
    for name, (cov_key, tot_key) in METRICS.items():
        want = thresholds.get(name)
        if not want:  # 0 或缺失都视为「不设门槛」
            continue
        actual = _pct(totals.get(cov_key, 0), totals.get(tot_key, 0))
        if actual is None:
            verdict = "WARN —— 这项没被测量，无法判定"
        elif actual + 1e-9 >= want:
            verdict = "PASS"
        else:
            verdict = "FAIL" if enforcing else "低于阈值（未拦截）"
            if enforcing:
                failures.append(f"{name}: {actual:.2f}% < {want}%")
        shown = "n/a" if actual is None else f"{actual:.2f}%"
        print(f"{name:<12}{shown:>10}{want:>9}%   {verdict}")

    skipped = [k for k in thresholds if k not in METRICS and thresholds[k]]
    if skipped:
        print(f"\n跳过（Python 侧无对应度量）：{', '.join(skipped)}")
    return failures


def _check_critical(cfg: dict, files: dict) -> list[str]:
    """`criticalPaths` —— 两种 coverageMode 下都是绝对值，始终生效。"""
    rules = cfg.get("criticalPaths") or []
    if not rules:
        return []

    failures: list[str] = []
    print("\ncriticalPaths（绝对门槛，不受 coverageMode 影响）")
    for rule in rules:
        glob = rule.get("glob") or rule.get("path") or ""
        want = rule.get("branch") or rule.get("branches") or 0
        matched = {p: s for p, s in files.items() if fnmatch.fnmatch(p, glob)}

        if not matched:
            # 判 FAIL 而不是 PASS：见模块 docstring。
            failures.append(f"{glob}: 匹配到 0 个文件")
            print(f"  FAIL  {glob:<45} 匹配到 0 个文件 —— 模块被删了或改名了？")
            continue

        covered = sum(s["summary"].get("covered_branches", 0) for s in matched.values())
        total = sum(s["summary"].get("num_branches", 0) for s in matched.values())
        actual = _pct(covered, total)
        if actual is None:
            print(f"  WARN  {glob:<45} {len(matched)} 个文件，但没有分支可测")
        elif actual + 1e-9 >= want:
            print(f"  PASS  {glob:<45} {actual:6.2f}% >= {want}%  ({len(matched)} 个文件)")
        else:
            failures.append(f"{glob}: branch {actual:.2f}% < {want}%")
            print(f"  FAIL  {glob:<45} {actual:6.2f}% <  {want}%  ({len(matched)} 个文件)")
    return failures


def main() -> int:
    cfg, report = _load()
    mode = cfg.get("coverageMode", "no-decrease")
    enforcing = mode == "absolute"

    print(f"coverageMode = {mode}")
    if not enforcing:
        print(
            "→ 总体阈值**不拦截**，只报数。\n"
            "  `no-decrease` 的语义是「与上次运行相比不下降」，而 CI 每次都是全新环境、\n"
            "  没有上次运行。在这里假装能判定，得到的是一个永远为绿的门禁。\n"
            "  008 收尾把它切成 `absolute` 之后，这里才开始真的拦人。"
        )

    failures = _check_totals(cfg, report.get("totals", {}), enforcing)
    failures += _check_critical(cfg, report.get("files", {}))

    if failures:
        print("\n覆盖率门禁 FAIL：")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\n覆盖率门禁 PASS" + ("" if enforcing else "（总体阈值未生效，见上）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
