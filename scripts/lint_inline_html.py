#!/usr/bin/env python3
"""013 WI-9 验收 6（§9.1）：模板里的内联 `<style>` / `style=` / 内联 `<script>` 只减不增。

口径（PLAN :812 a1 / :813 a2 / D7）：

* **style 计数** = 每个 `<style>` 块的 `结束行 - 起始行`（单行块记 1）＋ 每个 `style=` 属性。
  `<script>` / `<style>` 体内的 `style =` 字样不算属性（那是 JS 写样式，归 WI-14 的 ESLint 规则）。
* **script 计数** = 不带 `src` 的 `<script>` 元素数，每个模板至多减去一个 body 的 sha256
  命中 `FOUC_SHA256` 的块——FOUC 首帧脚本是 §9.1 唯一的豁免，按内容哈希认，不按位置认。

两者都与 `scripts/inline_html_allowlist.json` **严格相等**比较：高于登记值失败，低于登记值
也失败（降了就得在同一个改动里把登记值降下来——有余量的登记值等于长回去的许可证）。
未登记的模板允许 0；登记了却没有该模板的条目算悬空，失败。

登记值只减不增由 `scripts/check_allowlist_monotone.py` 对 merge-base 把关。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_REL = "src/reader3_app/web/templates"
ALLOWLIST_REL = "scripts/inline_html_allowlist.json"

#: D7：FOUC 首帧脚本 body（`<script>` 与 `</script>` 之间的原样文本，UTF-8）的 sha256。
#: WI-10 落 FOUC 脚本时登记；至多一个——两个哈希就是两段"唯一豁免"，自相矛盾。
#: 登记值 = reader.html / library.html / settings.html 三处 <head> 里同一段 stamp 的 body
#: （localStorage reader3.ui.colorScheme → data-theme，reader3.reader.theme → data-reading-theme）。
FOUC_SHA256: frozenset[str] = frozenset(
    {"70684a64b26e9d7c931a6cdaf49c27670a70c5994bac9a953b16c446a640fb00"}
)

STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.S | re.I)
SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
SRC_ATTR_RE = re.compile(r"(?<![\w-])src\s*=", re.I)
STYLE_ATTR_RE = re.compile(r"(?<![\w-])style\s*=\s*[\"']", re.I)
BODY_SPAN_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)


def _blank_bodies(text: str) -> str:
    """把 script/style 元素整段换成等长空白，属性扫描就看不到体内的 `style =`。"""
    return BODY_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def count_template(text: str, fouc_hashes: frozenset[str] | None = None) -> tuple[int, int]:
    """返回 `(style 计数, script 计数)`，口径见模块说明。"""
    hashes = FOUC_SHA256 if fouc_hashes is None else fouc_hashes

    style = 0
    for m in STYLE_BLOCK_RE.finditer(text):
        start_line = text.count("\n", 0, m.start())
        end_line = text.count("\n", 0, m.end())
        style += max(1, end_line - start_line)
    style += len(STYLE_ATTR_RE.findall(_blank_bodies(text)))

    script = 0
    fouc_used = False
    for m in SCRIPT_RE.finditer(text):
        if SRC_ATTR_RE.search(m.group(1)):
            continue
        digest = hashlib.sha256(m.group(2).encode("utf-8")).hexdigest()
        if not fouc_used and digest in hashes:
            fouc_used = True
            continue
        script += 1
    return style, script


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv or [])
    root: Path = args.root

    problems: list[str] = []
    hashes = FOUC_SHA256
    if len(hashes) > 1:
        problems.append(f"FOUC_SHA256 登记了 {len(hashes)} 个哈希：FOUC 豁免至多一个")
    for h in sorted(hashes):
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            problems.append(f"FOUC_SHA256 条目不是 64 位小写十六进制：{h!r}")

    allow_path = root / ALLOWLIST_REL
    try:
        allow = json.loads(allow_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"lint_inline_html: 读不了登记表 {allow_path}: {exc}")
        return 1
    if set(allow) != {"style", "script"}:
        problems.append(f"{ALLOWLIST_REL} 只能有 style / script 两节，实际 {sorted(allow)}")

    templates = sorted((root / TEMPLATES_REL).glob("*.html"))
    if not templates:
        print(f"lint_inline_html: {root / TEMPLATES_REL} 下没有模板——空扫描不算通过。")
        return 1

    names = {p.name for p in templates}
    for p in templates:
        counts = dict(zip(("style", "script"), count_template(p.read_text(encoding="utf-8"), hashes)))
        for kind, actual in counts.items():
            allowed = allow.get(kind, {}).get(p.name, 0)
            if actual > allowed:
                problems.append(f"{TEMPLATES_REL}/{p.name} {kind}: {actual} > {allowed}（超出登记值）")
            elif actual < allowed:
                problems.append(
                    f"{TEMPLATES_REL}/{p.name} {kind}: {actual} < {allowed}（已降低，请在同一改动里把登记值降到 {actual}）"
                )
    for kind in ("style", "script"):
        for name in sorted(set(allow.get(kind, {})) - names):
            problems.append(f"{ALLOWLIST_REL} {kind}.{name}: no such template（悬空条目，请删除）")

    print(f"扫描 {len(templates)} 个模板。")
    if problems:
        print(f"内联 HTML 违规（{len(problems)} 条）：")
        for line in problems:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
