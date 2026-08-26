"""WI-24 —— token 估算与上下文窗口，两个方向相同的高估会相乘。

定义处：`.claude/tdd-guardian/plan-20260824T074825Z.md` WI-24（findings `ai/45`、`ai/46`）。

一句话：`estimate_tokens` 把中文低估 2–4 倍，`provider_context_window` 又把 Anthropic
的窗口高估 5 倍，两者相乘后 `choose_routing` 会把一整本中文书塞进一个它塞不下的请求，
provider 回硬 400 `prompt is too long`——而全仓**没有**任何 context-length 回退。

纯函数，无 I/O、无网络、不碰 `books/`、不碰 `config/ai_settings.json`。
假 book 全在内存里造。

断言层级（沿用本 lane 的约定）：
    L1 接线/冒烟
    L2 返回值，或落盘状态的单个字段
    L3 整棵可观察的末态
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reader3_app.ai.routing import (
    book_token_stats,
    estimate_tokens,
    provider_context_window,
)

# --------------------------------------------------------------------------
# 造料：按字符类别精确控制长度，不依赖任何真实文本。
# --------------------------------------------------------------------------

_CJK = "汉"  # U+6C49，基本汉字区
_ASCII = "a"


def _mk(n_cjk: int, n_ascii: int) -> str:
    return _CJK * n_cjk + _ASCII * n_ascii


def _fake_book(*texts: str) -> SimpleNamespace:
    """内存里的假 book：只需要 `spine[i].text` / `.title`。"""
    return SimpleNamespace(
        spine=[
            SimpleNamespace(text=t, title=f"第 {i + 1} 章", order=i)
            for i, t in enumerate(texts)
        ]
    )


# 三章：纯中文 / 纯英文 / 中英混排。
# 每章的字符数都刻意选在「除不尽」的位置上，这样「逐章估算求和」与
# 「join 成一个大字符串再估一次」之间的差会明显超出 ±1 的容差——
# 否则 K2 就抓不住 `book_token_stats` 退回 join 的那个变异。
_CH_CJK = _mk(301, 1)
_CH_EN = _mk(1, 401)
_CH_MIXED = _mk(304, 201)


# --------------------------------------------------------------------------
# K1 —— 承重断言：等长的中文比英文估出**显著更多**的 token。
# --------------------------------------------------------------------------


def test_k1_等长中文与英文的_token_比值落在_2_到_3_之间():
    """L3 / S2。

    断的是**具体区间**而不是 `cjk > ascii`：一个「中文每字 +1」的实现也满足后者，
    却仍然会把一本中文书低估到送上必失败的路。区间 [2.0, 3.0] 对应
    「中文 ~1.5 字符/token、其余 ~4 字符/token」这一口径（4 / 1.5 ≈ 2.67）。
    """
    cjk = estimate_tokens(_CJK * 300)
    ascii_ = estimate_tokens(_ASCII * 300)

    assert isinstance(cjk, int)
    assert isinstance(ascii_, int)
    assert ascii_ > 0, "英文估算不该退化成 0，否则比值无意义"

    ratio = cjk / ascii_
    assert 2.0 <= ratio <= 3.0, (
        f"同为 300 字符，中文估 {cjk} token、英文估 {ascii_} token，"
        f"比值 {ratio:.3f} 不在 [2.0, 3.0] 内"
    )


def test_k1b_空串与短串仍然是_max_1_的_int():
    """L2 / S1 —— 验收明确要求返回值仍是 `int`，仍 `max(1, ...)`。"""
    for text in ("", "a", "汉"):
        v = estimate_tokens(text)
        assert isinstance(v, int)
        assert v >= 1, f"{text!r} 估出了 {v}"


# --------------------------------------------------------------------------
# K2 —— 逐章求和与整书估算是同一口径。
# --------------------------------------------------------------------------


def test_k2_整书_token_等于逐章估算之和且最大章正确():
    """L3 / S2。

    `book_token_stats` 必须**逐章估算求和**，不能把全书 join 成一个大字符串再估：
    分段估算的前提就是分段。容差写死为 ±1（join 分隔符本身能带来的那点差）。
    """
    book = _fake_book(_CH_CJK, _CH_EN, _CH_MIXED)

    per_chapter = [
        estimate_tokens(_CH_CJK),
        estimate_tokens(_CH_EN),
        estimate_tokens(_CH_MIXED),
    ]
    book_tokens, max_chapter_tokens = book_token_stats(book)

    assert abs(book_tokens - sum(per_chapter)) <= 1, (
        f"book_tokens={book_tokens}，逐章之和={sum(per_chapter)}（逐章明细 {per_chapter}）"
    )
    assert max_chapter_tokens == max(per_chapter)


def test_k2b_空章节不参与统计():
    """L2 / S1 —— 回归保护：原实现跳过空 text，改成逐章求和后不能把空章算进去。"""
    book = _fake_book(_CH_EN, "", _CH_EN)
    book_tokens, max_chapter_tokens = book_token_stats(book)

    assert abs(book_tokens - 2 * estimate_tokens(_CH_EN)) <= 1
    assert max_chapter_tokens == estimate_tokens(_CH_EN)


def test_k2c_空_spine_返回两个零():
    """L2 / S1 —— 边界，且防止 `max(1, ...)` 从 estimate_tokens 漏进整书统计。"""
    assert book_token_stats(_fake_book()) == (0, 0)


# --------------------------------------------------------------------------
# K3 —— 生产 Claude 模型的窗口是 200K，不是 1M。
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-haiku-20241022",
        "claude-3-5-sonnet-20241022",
    ],
)
def test_k3_生产_claude_模型的上下文窗口是_200k(model):
    """L3 / S2 —— 1M 是特定 Sonnet 构建上的受限 beta，不是默认值。默认必须向下取。"""
    assert provider_context_window("anthropic", model) == 200_000


def test_k3b_anthropic_未知模型也向下取():
    """L2 / S1 —— 默认向下，因为没有 context-length 回退可兜底。"""
    assert provider_context_window("anthropic", "claude-未来型号") == 200_000
    assert provider_context_window("anthropic", "") == 200_000


# --------------------------------------------------------------------------
# K4 —— 防过度修复：模型名显式带 `-1m` 时仍是 1M。
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-4-5-1m",
        "claude-sonnet-4-20250514-1m",
    ],
)
def test_k4_模型名显式带_1m_时仍得到_1m(model):
    """L2 / S1 —— 修的是「默认值盖过解析结果」，不是「一律降到 200K」。"""
    assert provider_context_window("anthropic", model) == 1_000_000


# --------------------------------------------------------------------------
# K5 —— 其余 provider 的默认值一字未变。
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("openai", "gpt-4o", 128_000),
        ("openrouter", "some/model", 128_000),
        ("ollama", "llama3", 8192),
        ("gemini", "gemini-1.5-pro", 2_000_000),
        ("gemini", "gemini-2.0-flash", 1_000_000),
        ("nosuchprovider", "whatever", 128_000),
        ("", "", 128_000),
    ],
)
def test_k5_其余_provider_默认值不变(provider, model, expected):
    """L2 / S1 —— 回归保护：本 WI 只动 anthropic 那一支。"""
    assert provider_context_window(provider, model) == expected


# --------------------------------------------------------------------------
# K6 —— `ai/46`：那句关于「服务端会回退到 RAG」的假注释没了。
# --------------------------------------------------------------------------

_ROUTING_SRC = (
    Path(__file__).resolve().parents[2] / "src" / "reader3_app" / "ai" / "routing.py"
)
_LIE = "fallback will route to RAG"


def test_k6a_源码扫描本身是有效的():
    """L1 接线 / S1 —— 正控：证明这套扫描确实读到了文件、确实能找到存在的字符串。

    没有这条，K6b 就是一句空话：文件路径写错时它也「通过」。
    """
    src = _ROUTING_SRC.read_text(encoding="utf-8")
    assert len(src) > 500
    assert "def provider_context_window" in src
    assert _LIE in (src + _LIE), "扫描器连拼进去的字符串都找不到"


def test_k6b_关于_rag_回退的假注释已删除():
    """L1 接线 / S1 —— 全仓没有 context-length 错误处理器，这句话是假的。

    它**不能单独**作为本 WI 的验收：改注释不改默认值等于只删证据不修 bug。
    真正的验收是它与 K3 一起成立。
    """
    src = _ROUTING_SRC.read_text(encoding="utf-8")
    assert _LIE not in src, f"routing.py 仍然写着「{_LIE}」，但这个回退并不存在"
