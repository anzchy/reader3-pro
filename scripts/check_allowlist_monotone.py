#!/usr/bin/env python3
"""013 WI-9 验收 6a / 11e：登记表只减不增，对照 merge-base 判定。

被守的两张表：

* `scripts/inline_html_allowlist.json` —— `{"style": {模板: int}, "script": {模板: int}}`
* `scripts/hardcode_baseline.json` —— `{文件: ["selector:property", ...]}`

规则（递归）：dict 的键只能是 base 键的子集；int 只能 `<=`；list 只能是 base 的子集。
base = `git merge-base HEAD <base_ref>`（默认 `origin/master`），读的是**工作区**里的当前
文件，所以未提交的增长也会被看见。对照的是 merge-base 而不是 `HEAD~1`：分支上先涨后
平的两次提交（base→4→4）照样算增长。

**失败即关闭**：base 解析不出来（ref 不存在、没有 origin、不是 git 仓库）抛
`BaseUnresolvedError`，CLI 退出 1 并写明 cannot resolve base——绝不退回本地 master、
`HEAD` 或"没有可比对象就算通过"。

base 时该文件还不存在 → 不设约束（它是本分支新建的）；当前文件被删 → 通过（删光是最小）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_REF = "origin/master"
GUARDED = ("scripts/inline_html_allowlist.json", "scripts/hardcode_baseline.json")


class BaseUnresolvedError(Exception):
    """merge-base 解析失败。调用方必须当失败处理，不得当"无可比对象"放行。"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)


def resolve_base(repo: Path, base_ref: str | None) -> str:
    ref = base_ref or DEFAULT_BASE_REF
    if not Path(repo).is_dir():
        raise BaseUnresolvedError(f"{repo} 不是目录")
    verify = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if verify.returncode != 0:
        raise BaseUnresolvedError(f"ref {ref!r} 解析不出（{verify.stderr.strip() or 'no such ref'}）")
    mb = _git(repo, "merge-base", "HEAD", ref)
    if mb.returncode != 0 or not mb.stdout.strip():
        raise BaseUnresolvedError(f"HEAD 与 {ref!r} 没有 merge-base（{mb.stderr.strip()}）")
    return mb.stdout.strip()


def _compare(base: Any, cur: Any, where: str, out: list[str]) -> None:
    if isinstance(base, dict) and isinstance(cur, dict):
        for key in sorted(cur):
            sub = f"{where}{key}" if not where else f"{where} {key}"
            if key not in base:
                out.append(f"{sub}: 新增键（base 里没有）")
            else:
                _compare(base[key], cur[key], sub, out)
    elif isinstance(base, bool) or isinstance(cur, bool):
        if base != cur:
            out.append(f"{where}: 值变了 {base!r}→{cur!r}")
    elif isinstance(base, int) and isinstance(cur, int):
        if cur > base:
            out.append(f"{where}: {base}→{cur}（增长）")
    elif isinstance(base, list) and isinstance(cur, list):
        for item in sorted(set(map(str, cur)) - set(map(str, base))):
            out.append(f"{where}: 新增条目 {item}")
    elif type(base) is not type(cur):
        out.append(f"{where}: 类型变了 {type(base).__name__}→{type(cur).__name__}")
    elif base != cur:
        out.append(f"{where}: 值变了 {base!r}→{cur!r}")


def check_allowlist_monotone(repo: Path, base_ref: str | None, path: str) -> list[str]:
    """返回违规描述（空 = 通过）；base 解析失败抛 `BaseUnresolvedError`。"""
    repo = Path(repo)
    base = resolve_base(repo, base_ref)
    current_file = repo / path
    if not current_file.is_file():
        return []
    shown = _git(repo, "show", f"{base}:{path}")
    if shown.returncode != 0:
        exists = _git(repo, "cat-file", "-e", f"{base}:{path}")
        if exists.returncode != 0:
            return []  # base 时还不存在：本分支新建，不设约束
        raise BaseUnresolvedError(f"读不出 {base[:12]}:{path}（{shown.stderr.strip()}）")
    try:
        base_data = json.loads(shown.stdout)
        cur_data = json.loads(current_file.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{path}: 不是合法 JSON（{exc}）"]
    problems: list[str] = []
    _compare(base_data, cur_data, "", problems)
    return [f"{path}: {p}" for p in problems]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default=None, help=f"默认 {DEFAULT_BASE_REF}")
    args = parser.parse_args(argv or [])

    problems: list[str] = []
    try:
        base = resolve_base(args.root, args.base_ref)
        for rel in GUARDED:
            problems += check_allowlist_monotone(args.root, args.base_ref, rel)
    except BaseUnresolvedError as exc:
        print(f"allowlist-monotone: cannot resolve base — {exc}")
        print("  无法确定对照基线即判失败（fail closed）；CI 需 fetch-depth: 0 且能取到 origin/master。")
        return 1

    print(f"对照 merge-base {base[:12]}（{args.base_ref or DEFAULT_BASE_REF}），检查 {len(GUARDED)} 张登记表。")
    if problems:
        print(f"登记表增长（{len(problems)} 条）——登记表只减不增：")
        for p in problems:
            print(f"  {p}")
        return 1
    print("登记表未增长。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
