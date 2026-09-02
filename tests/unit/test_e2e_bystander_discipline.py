"""凡断「同章多于一条标注」的 e2e 用例，必须显式断一次旁观条守恒。

**这条检查存在的理由是「漏写不会红」。** `assert_roundtrip(expected_count=N)` 只保证
目标条往返成功、总数是 N；同章其余条目有没有被顺手改掉，它一概不管——**而且刻意不管**，
因为对每个调用点都成立的断言等于恒真（见 `helpers.assert_roundtrip` 的 docstring）。

于是「多标注用例忘了断旁观条」是一种**静默失效**：用例照样全绿，只是少测了一整类缺陷
（服务端整章回写漏条、客户端候选集放宽误删）。静默失效的规则留在散文里没有用，必须机器可查。
任务书 §0 第五条纪律与 §0.6 的跨波欠账表都指向本文件。

放在 `tests/unit/` 而不是某个 lint 脚本里，是照 `test_e2e_group_layout.py` 的先例：
`scripts/` 下的 lint 脚本存常量，断言存这里；而且 unit lane 才是 `gateOn: commit` 的那条。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

E2E_ROOT = Path(__file__).resolve().parents[1] / "e2e"

#: 只认关键字实参形态。`helpers.py` 里的形参默认值 `expected_count: int = 1` 取值为 1，
#: 不触发；`expected_count == 1` 这类比较没有等号赋值形态，也不触发。
EXPECTED_COUNT_RE = re.compile(r"expected_count\s*=\s*(\d+)")

#: 逃生口，形态与选择器 lint 的 `# lint-e2e-selectors: allow` 一致：必须写理由。
#: 用在「本章确实有多条，但旁观条守恒由别的判据以更强的形式覆盖」这种场合。
ESCAPE_RE = re.compile(r"#\s*bystanders:\s*n/a\s*——\s*\S")

REQUIRED_CALL = "assert_bystanders_unchanged"


def _offending_lines(text: str) -> List[Tuple[int, str]]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # 整行注释里提到 `expected_count=2` 的（docstring、说明性注释）不是调用点。
        # 不这么滤的话，失败消息里会混进几行只是「谈到」它的散文，把人指向错的行。
        # 逃生口是**代码行尾**的注释，所以不能一概按 `#` 排除。
        if line.lstrip().startswith("#"):
            continue
        match = EXPECTED_COUNT_RE.search(line)
        if match and int(match.group(1)) > 1 and not ESCAPE_RE.search(line):
            hits.append((lineno, line.strip()))
    return hits


def test_multi_annotation_cases_assert_bystander_conservation() -> None:
    violations = []
    for path in sorted(E2E_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = _offending_lines(text)
        if hits and REQUIRED_CALL not in text:
            rel = path.relative_to(E2E_ROOT.parents[1])
            for lineno, line in hits:
                violations.append(f"  {rel}:{lineno}  {line}")

    assert not violations, (
        "下列用例传了 expected_count > 1，却没有调用 "
        f"`{REQUIRED_CALL}`：\n" + "\n".join(violations) + "\n\n"
        "`assert_roundtrip` 只管目标条与总数，同章旁观条有没有被动过它不管（刻意的）。"
        "漏断不会红，只会少测一整类缺陷——服务端整章回写漏条、客户端候选集放宽误删。\n"
        "确有理由不断的，在该行末尾写 `# bystanders: n/a —— <理由>`。"
    )


def test_the_check_itself_can_fail() -> None:
    """本检查不是空转：造一段违规文本，它必须被判出来；合规的两种形态必须放行。"""
    offending = 'assert_roundtrip(page, d, b, q, a, expected_count=2)\n'
    assert _offending_lines(offending), "违规形态没被识别出来，本检查是空转的"

    assert not _offending_lines(
        "assert_roundtrip(page, d, b, q, a, expected_count=1)\n"
    ), "expected_count=1 是单条形态，不该触发"

    assert not _offending_lines(
        "assert_roundtrip(page, d, b, q, a, expected_count=2)  "
        "# bystanders: n/a —— 本章两条互相重叠，守恒由 W-8 的分段断言覆盖\n"
    ), "带理由的逃生口没有放行"

    assert _offending_lines(
        "assert_roundtrip(page, d, b, q, a, expected_count=2)  # bystanders: n/a\n"
    ), "逃生口没写理由，不该放行"

    assert not _offending_lines(
        "    # 说明：这里传 expected_count=2 是因为同章有一条旁观标注\n"
    ), "整行注释只是谈到它，不是调用点"
