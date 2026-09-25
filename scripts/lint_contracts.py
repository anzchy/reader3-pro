#!/usr/bin/env python3
"""013 WI-9 验收 3 / 6a / 11e：`npm run lint:contracts`——一条命令跑完全部契约检查。

依次跑 selector、naming、token-ref、inline-html、hardcode（含抑制面扫描）、
allowlist-monotone、depcruise；**不短路**，每项前打印 `== <名> ==`，结果 OR 起来，
末行 `lint:contracts: OK (7 checks)` 或 `lint:contracts: FAIL <a>, <b>`。

只用标准库：npm 以 `python3` 起它，子 lint 也都是纯标准库。所有检查都带 `--root`，
所以测试可以对一棵 tmp 副本跑整条命令；工具本身（脚本、node_modules）始终取自本仓库。

用法：python3 scripts/lint_contracts.py [--root DIR] [--base-ref REF]
  --base-ref 传给 allowlist-monotone；缺省 origin/master，解析不出即失败（fail closed）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CHILD_TIMEOUT_S = 180


def _commands(root: Path, base_ref: str | None) -> list[tuple[str, list[str], Path]]:
    py = sys.executable
    r = ["--root", str(root)]
    monotone = [py, str(SCRIPTS / "check_allowlist_monotone.py"), *r]
    if base_ref:
        monotone += ["--base-ref", base_ref]
    depcruise = ROOT / "node_modules" / ".bin" / "depcruise"
    return [
        ("selector", [py, str(SCRIPTS / "lint_e2e_selectors.py"), *r], ROOT),
        ("naming", [py, str(SCRIPTS / "lint_testid_naming.py"), *r], ROOT),
        ("token-ref", [py, str(SCRIPTS / "lint_token_refs.py"), *r], ROOT),
        ("inline-html", [py, str(SCRIPTS / "lint_inline_html.py"), *r], ROOT),
        ("hardcode", ["node", str(SCRIPTS / "lint_hardcode.mjs"), *r], ROOT),
        ("allowlist-monotone", monotone, ROOT),
        # depcruise 在目标树里跑，才读得到那棵树的 tsconfig 与 .dependency-cruiser.cjs。
        ("depcruise", [str(depcruise), "--config", ".dependency-cruiser.cjs", "frontend/src"], root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default=None)
    args = parser.parse_args(argv or [])
    root = args.root.resolve()

    failed: list[str] = []
    checks = _commands(root, args.base_ref)
    for name, cmd, cwd in checks:
        print(f"== {name} ==", flush=True)
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S)
            output, rc = proc.stdout + proc.stderr, proc.returncode
        except FileNotFoundError as exc:
            output, rc = f"无法启动：{exc}\n", 127
        except subprocess.TimeoutExpired:
            output, rc = f"超时（{CHILD_TIMEOUT_S}s）\n", 124
        sys.stdout.write(output if output.endswith("\n") or not output else output + "\n")
        print(f"-- {name}: rc={rc} ({time.monotonic() - started:.1f}s)", flush=True)
        if rc != 0:
            failed.append(name)

    if failed:
        print(f"lint:contracts: FAIL {', '.join(failed)}")
        return 1
    print(f"lint:contracts: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
