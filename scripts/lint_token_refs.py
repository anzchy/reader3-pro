#!/usr/bin/env python3
"""0.8 token 悬空引用 lint —— `var(--x)` 里的 `x` 必须有定义。

定义处：`docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` 步骤 0.8。
本文件是那条定义的实现，不重述条款。两条判定：

1. **悬空**：被 `var()` 引用、却没有任何 `--x:` 定义的名字。
2. **fallback**：`var(--x, fallback)` 照样违规——fallback 是给运行时降级用的，
   不是给拼错名字用的；一条永远走 fallback 的 `var()` 是看起来在正常工作的死代码。

外部定义的名字（浏览器内置、第三方）走 `scripts/token_ref_whitelist.txt`。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 扫描集：现状样式的全部所在地。与迁移计划步骤 0.8 的清单一致。
SCAN_GLOBS = (
    "designs/reader-pro-next/**/*.html",
    "designs/reader-pro-next/**/*.jsx",
    "designs/reader-pro-next/**/*.css",
    "src/reader3_app/web/static/**/*.css",
    "src/reader3_app/web/templates/*.html",
)
# 设计规格里的 CSS 代码块也算——规格是 token 的定义处，悬空引用最早在那里成型。
SPEC_DOCS = (
    "docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md",
    "docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md",
)

WHITELIST_FILE = ROOT / "scripts" / "token_ref_whitelist.txt"

# `--x:` 出现在声明位置即为定义。`var(--x)` 后面没有冒号，不会误判。
DEFINE_RE = re.compile(r"(?<![\w-])(--[A-Za-z0-9_-]+)\s*:")
# 捕获引用名，以及紧跟其后的分隔符——`,` 意味着带 fallback。
REFERENCE_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*([,)])")
CSS_FENCE_RE = re.compile(r"^```css$(.*?)^```$", re.MULTILINE | re.DOTALL)


def load_whitelist() -> set[str]:
    if not WHITELIST_FILE.exists():
        return set()
    names = set()
    for line in WHITELIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line)
    return names


def sources() -> list[tuple[Path, str, int]]:
    """(路径, 文本, 行号偏移)。规格文档只取 ```css 围栏里的内容。"""
    out: list[tuple[Path, str, int]] = []
    seen: set[Path] = set()
    for glob in SCAN_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            if path in seen:
                continue
            seen.add(path)
            out.append((path, path.read_text(encoding="utf-8"), 0))
    for rel in SPEC_DOCS:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in CSS_FENCE_RE.finditer(text):
            offset = text[: match.start(1)].count("\n")
            out.append((path, match.group(1), offset))
    return out


def main() -> int:
    whitelist = load_whitelist()
    defined: set[str] = set()
    references: list[tuple[Path, int, str, bool]] = []

    for path, text, offset in sources():
        defined.update(DEFINE_RE.findall(text))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, delimiter in REFERENCE_RE.findall(line):
                references.append((path, line_no + offset, name, delimiter == ","))

    dangling: list[tuple[Path, int, str]] = []
    fallbacks: list[tuple[Path, int, str]] = []
    for path, line_no, name, has_fallback in references:
        rel = path.relative_to(ROOT)
        if name not in defined and name not in whitelist:
            dangling.append((rel, line_no, name))
        if has_fallback:
            fallbacks.append((rel, line_no, name))

    for label, rows in (("悬空引用", dangling), ("带 fallback 的引用", fallbacks)):
        for rel, line_no, name in rows:
            print(f"{rel}:{line_no}: {label} {name}")

    total = len(dangling) + len(fallbacks)
    scanned = len({path for path, _, _ in sources()})
    print(
        f"\n0.8 token 悬空引用 lint：扫 {scanned} 个来源，"
        f"{len(defined)} 个定义 / {len(references)} 处引用，"
        f"悬空 {len(dangling)}、带 fallback {len(fallbacks)}。"
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
