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

**配置读错一律 fail-closed，同一个道理。** `coverageMode` 没有默认值：一个决定门禁
拦不拦人的字段，缺失、拼错、大小写不同或干脆不是字符串时，只能退出报错，不能默默
滑向宽松的那一侧——那样得到的又是一个永远为绿、看起来却像有的门禁。同理，
`coverageThresholds` 里非零又不在 `METRICS` 里的键判 FAIL：那是一个你配了、却从未
被评估过的阈值。只有 `functions` 是已知的合法跳过（见 `KNOWN_SKIPS`）。
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

#: `coverageMode` 的全部合法取值。没有默认值：见模块 docstring。
#: 用 frozenset 而不是元组，与 `KNOWN_SKIPS` 同：这是成员判定，不是序列。
#: 代价是 `mode in LEGAL_MODES` 对不可哈希的值会抛 TypeError —— 所以
#: `_resolve_mode` 里那道 `isinstance` 是承重的，不是保险。展示时排序，
#: 否则报错消息里合法取值的顺序每次运行都不一样。
LEGAL_MODES = frozenset({"absolute", "no-decrease"})

#: `coverageThresholds` 里已知的、Python 侧确实无对应度量的键。
#: 只有这些允许被跳过；其余未知键是配置写错了，判 FAIL。
KNOWN_SKIPS = frozenset({"functions"})


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
            # 设了阈值却量不到，是**门禁坏了**，不是「暂时没数据」。
            # 老写法只报 WARN：把 pyproject 的 `branch = true` 删掉，报告里
            # num_branches 归零，branches 阈值 52 立刻变成一句提示，门禁照样退 0。
            # 一个不设阈值的指标在上面 `if not want` 就已经 continue 了，所以走到
            # 这里的每一项，都是有人明确要求过它拦人的。
            verdict = "FAIL —— 设了阈值却没被测量" if enforcing else "未测量（未拦截）"
            if enforcing:
                failures.append(
                    f"{name}: 阈值 {want}% 无法判定 —— 报告里 {tot_key} 为 0。"
                    f"分支覆盖没开？检查 pyproject.toml 的 [tool.coverage.run] branch = true"
                )
        elif actual + 1e-9 >= want:
            verdict = "PASS"
        else:
            verdict = "FAIL" if enforcing else "低于阈值（未拦截）"
            if enforcing:
                failures.append(f"{name}: {actual:.2f}% < {want}%")
        shown = "n/a" if actual is None else f"{actual:.2f}%"
        print(f"{name:<12}{shown:>10}{want:>9}%   {verdict}")

    unknown = [k for k in thresholds if k not in METRICS and thresholds[k]]
    skipped = [k for k in unknown if k in KNOWN_SKIPS]
    bogus = [k for k in unknown if k not in KNOWN_SKIPS]
    if skipped:
        print(f"\n跳过（Python 侧无对应度量）：{', '.join(skipped)}")
    for key in bogus:
        # 与上面那种合法跳过不同：这是一个从未被评估过的阈值，而配置的人以为它在拦人。
        failures.append(
            f"coverageThresholds 里的未知键 {key!r} 从未被评估 —— "
            f"可用的键：{', '.join(sorted(METRICS))}（外加已知跳过 "
            f"{', '.join(sorted(KNOWN_SKIPS))}）"
        )
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
            # 同上，且这里更严：criticalPaths 是绝对门槛，两种 mode 下都生效。
            # 「匹配到文件但一个分支都没有」和上面「匹配到 0 个文件」是同一类事故。
            failures.append(f"{glob}: branch 阈值 {want}% 无法判定 —— {len(matched)} 个文件里没有分支可测")
            print(f"  FAIL  {glob:<45} {len(matched)} 个文件，但没有分支可测 —— 分支覆盖没开？")
        elif actual + 1e-9 >= want:
            print(f"  PASS  {glob:<45} {actual:6.2f}% >= {want}%  ({len(matched)} 个文件)")
        else:
            failures.append(f"{glob}: branch {actual:.2f}% < {want}%")
            print(f"  FAIL  {glob:<45} {actual:6.2f}% <  {want}%  ({len(matched)} 个文件)")
    return failures


def _resolve_mode(cfg: dict) -> str:
    """读 `coverageMode`，非法即退出。**不给默认值**：见模块 docstring。

    `mode == "absolute"` 对任何类型都合法求值成 `False`，所以一个列表、一个 `null`、
    一处大小写不同，在旧实现里都会安静地把门禁关掉。消息里带上读到的原值，否则读的
    人还得自己去翻配置猜错在哪。
    """
    if "coverageMode" not in cfg:
        sys.exit(
            f"配置里缺 coverageMode（{CONFIG}）。这个字段决定门禁拦不拦人，"
            f"没有默认值。合法取值：{' / '.join(repr(m) for m in sorted(LEGAL_MODES))}"
        )
    mode = cfg["coverageMode"]
    if not isinstance(mode, str) or mode not in LEGAL_MODES:
        sys.exit(
            f"coverageMode 非法：读到 {mode!r}（{CONFIG}）。"
            f"合法取值：{' / '.join(repr(m) for m in sorted(LEGAL_MODES))}"
        )
    return mode


def main() -> int:
    cfg, report = _load()
    mode = _resolve_mode(cfg)
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
