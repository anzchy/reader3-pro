"""WI-16 —— X-1：AI SSE 流式（浏览器侧增量渲染 ＋ 桩侧握手 ＋ 正常结束 ＋ 中断后可恢复）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-16（**R1 / R2 修订为准**）与文末 §A。
任务书：`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §6 X-1 行、§0 六条纪律
（尤其第四条「特征化用例的可失败性证据」）、§0.6 Wave 6 独占的理由。配对的服务端用例：
`tests/contract/test_scenarios.py::test_流式提问是边生成边推送而不是攒够一次性吐`（008，钉住服务端
是边生成边推）。**009 唯一的新信息是浏览器侧是不是边收边渲**——那只有真浏览器能回答。

**Law（增量性与前缀单调性）**：流式渲染过程中**那一条 assistant 消息**的文本，在每一次 DOM 更新后
都是最终文本的一个**前缀**，长度**单调不减**，更新次数 > 1，且最终文本 == 桩发出的全部 delta 拼接。
这比「更新次数 > 1」强得多：它同时杀掉「先渲染占位符再一次性替换」「乱序拼接」「重复追加」三类实现，
且**不含任何墙上时钟**。X-1a′ 再加一条因果律：`render(delta_0)` **happens-before** `send(delta_last)`
——由桩侧 gate 的放行方式记录，而不是掐表。

四条用例：X-1a（增量 + 前缀单调）、X-1a′（桩侧握手）、X-1b（正常结束 + 零出网）、X-1c（stop 后可恢复）。
桩的「gate 超时后干净收尾」契约由 `tests/unit/test_ai_stub_contract.py`（unit lane）单独钉住。

-------------------------------------------------------------------------------
无索引书的检索降级路径（2026-09-04 实测，写在这里是矩阵裁决 (3) 的要求）
-------------------------------------------------------------------------------
e2e 沙箱书**永远没有 `chroma_db/`**（`process_epub` 不建索引），所以 `/api/ai/question/{uuid}?stream=true`
恒走 `ai/rag.py` 的 `_keyword_fallback`。实测方式：按 `live_server` 同款起服务（`_server_env` 沙箱 +
`ai_settings.json` 指向本模块的桩），直接 POST：

    ch0 正文 = 'One Alpha prose.'
    question='Alpha'                  → 200 text/event-stream；首帧 `event: meta`（retrieval_sources 命中
                                         chapter 0 "Section 1"），次帧 `event: chunk` `{"delta": "Alpha "}`
    question='Alpha prose'            → 200，同上
    question='alpha PROSE'            → 200（大小写不敏感）
    question='Alpha 这一章讲了什么？'   → **400** application/json
                                         `{"detail":"This book is not indexed for semantic retrieval yet. …"}`
    question='这本书讲了什么？'         → 400，同上

**一处与矩阵不同的事实**：`_keyword_fallback` 做的是 `chapter.text.lower().find(query.lower())`——
把**整句提问**当子串找，不是分词后「有关键词命中」。所以矩阵给的提问 `"Alpha 这一章讲了什么？"` 会 400，
本模块的提问必须是语料正文的**逐字子串**：`QUESTION = "Alpha prose"`。零命中时 `RuntimeError` 在
`return StreamingResponse(...)` **之前**被转成 HTTP 400 普通 JSON，不是 SSE 的 `error` 事件——因此本模块
**没有任何**「失败以 SSE 形状到达」的断言。`ai.js` 对非 2xx 的处理是 `throw new Error(detail)` ⇒ 消息被
覆写成 `Error: …`，用例会红在一个与流式无关的原因上；提问写错就是这个形状。

-------------------------------------------------------------------------------
观测方式：为什么快照取 `thread.lastElementChild.innerText`（矩阵 R1 Gap 4）
-------------------------------------------------------------------------------
`ai.js` 的 `sendQuestion()` 在 fetch **之前**先后 `addMessage("user", text)` 与
`addMessage("assistant", "…")`，流式分支随后对那个占位节点 `innerText = answer` 逐块覆写。
`appendMessageToDOM` 建出的是 `div.ai-msg <role>`，**没有 testid**，且线程里此刻有用户问句 + 占位
两个节点。把 MutationObserver 挂在 `rd-ai-thread` 上快照**整个线程**的 innerText，第一帧就是用户问句，
`final.startswith(帧)` 必然假红——对着完全正确的实现红。所以快照取 **`lastElementChild.innerText`**：
流式期间它恒为那条 assistant 消息。

**本模块依赖一条 DOM 约定：新消息追加在线程末尾**（`appendMessageToDOM` 用 `appendChild`）。若有人把
assistant 消息改成插在前面，`lastElementChild` 会取到别的节点，四条全红——那是正确的红，修法是改这里的
取法，不是放松断言。

过滤规则：**只剔除与 `PLACEHOLDER = "…"` 严格相等的帧**（`ai.js` 的占位符同值）。用户问句为什么不会出现
在帧序列里：两次 `addMessage` 在同一个任务里同步执行，MutationObserver 的回调在微任务检查点才跑，那时
`lastElementChild` 已经是占位节点。任何比「== PLACEHOLDER」更宽的过滤（跳过前 N 帧、过滤所有非前缀帧）
都会把断言掏空，不得加。

**一处矩阵 R1 没写到的实测事实（2026-09-04 首跑四条全红抓到的）**：`done` 之后 `sendQuestion()` 调
`renderAll()` 重建线程，`appendMessageToDOM` 对带 `retrieval_sources` 的 assistant 消息会在**同一个节点里**
追加一个引用页脚 `div.ai-citations`（内含 `rd-ai-citation` 链接，文本 `引用\n第1章 Section 1`）。降级检索
恒命中一段，页脚恒在。于是终态的 `lastElementChild.innerText` 是 `回答 + "\n引用\n第1章 Section 1"`，
`snaps[-1] == "".join(DELTAS)` 对着正确实现假红。修法：**读那条消息自己的文本节点**（直接子节点里
`nodeType === 3` 的拼接，见 `_ANSWER_TEXT_JS`）——流式期间它与 `innerText` 逐字相同（占位节点只有一个
文本子节点），终态则只含回答、不含页脚。页脚是检索元数据到达 DOM 的证据，X-1b 单独断它一次
（`rd-ai-citation` 恰好 1 个、`data-section="0"`）；把它混进「回答文本」既错在语义上，也会让 SSE `meta`
事件改名这类回归无处可断。

-------------------------------------------------------------------------------
三个超时的序关系与用例预算（矩阵 R2 Gap E）
-------------------------------------------------------------------------------
`STUB_GATE_TIMEOUT (5.0) < RENDER_WAIT_TIMEOUT_S (15.0) < CASE_TIMEOUT_S (30.0)`，定义与模块级 `assert`
都在 `tests/fixtures/ai_stub.py`，本模块**不另起一套**（X-1c 复用同一套）。它决定的是 X-1a′ 的失败形态：
「攒够一次性吐」的实现下，桩在 5s 时干净收尾并保持 `completed=False`，浏览器随后一次性渲染，步骤 3 的
`wait_for_function`（显式 `timeout=RENDER_WAIT_TIMEOUT_S * 1000`）在 15s 内仍能等到首块，于是用例走到
`assert stub.completed is True` 并以**断言**失败，而不是 timeout。本仓库未装 pytest-timeout，
`CASE_TIMEOUT_S` 由 `ai_page` fixture 设成 Playwright 的默认超时（每一次隐式等待的上界），用例里每一次显式
等待都传更小的 `RENDER_WAIT_TIMEOUT_S`。沙箱 settings 的 provider `timeout_s`（`conftest.AI_STUB_PROVIDER_TIMEOUT_S`
= 10）夹在 gate 与 render 之间，理由在那个常量旁边。

-------------------------------------------------------------------------------
「请求已结束」的判据
-------------------------------------------------------------------------------
`sendQuestion()` 里 `setBusy(true)` 在 `await persistConversation()` **之后**才跑，所以点完 send 的一瞬
`rd-ai-send` 仍是 enabled——直接等「enabled」会在 busy 开始前就假通过。判据改成合取：
**最后一条消息不再是占位符 ∧ `rd-ai-send` enabled**。占位节点在 click 处理器里同步追加，click 返回时它已在；
流式期间前一项真、后一项假；`finally { setBusy(false) }` 之后两项同真。成功与 `Error: …` 两种结局都满足它，
于是失败时红在文本断言上（可诊断），不是红在等待超时上。

-------------------------------------------------------------------------------
定向破坏实录（§0 第四条纪律；全部经 `page.route` 改写响应体，`src/` 一个字节没动）
-------------------------------------------------------------------------------
本模块是特征化用例，红本来就不可得（收据必然记成 green）。替代证据是逐条打靶，见文末 `SABOTAGE_LOG`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Set
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Request, Response, expect

from ai_stub import (  # type: ignore[import-not-found]
    CASE_TIMEOUT_S,
    DELTAS,
    RENDER_WAIT_TIMEOUT_S,
    STUB_GATE_TIMEOUT,
    OllamaStub,
)
from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import open_reader  # type: ignore[import-not-found]

pytestmark = pytest.mark.baseline_1b

# 序关系在桩模块里已有一句模块级 assert；这里再断一次，让「有人把那句删了」在本模块 import 时就响。
assert STUB_GATE_TIMEOUT < RENDER_WAIT_TIMEOUT_S < CASE_TIMEOUT_S

#: 与 `ai.js` `sendQuestion()` 里 `this.addMessage("assistant", "…", {})` 的占位符同值。
PLACEHOLDER = "…"

#: 提问。**必须是语料正文的逐字子串**（见模块 docstring「无索引书的检索降级路径」）：
#: `smoke_data` 第 0 章正文是 `'One Alpha prose.'`。
QUESTION = "Alpha prose"
#: 打开阅读器时等的正文探针（`helpers.open_reader` 的 `expect_text`）。
CH0_ANCHOR = "Alpha prose."

#: 桩发出的全部 delta 拼接 == 用例期望的最终文本。**从桩常量派生**而不是再抄一遍字面量：
#: 这里比的是「浏览器渲染的 == 桩发出的」，两侧同源才是断言的意义。
FINAL_TEXT = "".join(DELTAS)

#: 一条消息节点**自己的**文本：直接子节点里文本节点的拼接。流式期间它与 `innerText` 逐字相同；
#: 终态不含 `renderAll()` 追加的引用页脚（那是子元素）。理由见模块 docstring「一处矩阵 R1 没写到的实测事实」。
_ANSWER_TEXT_JS = """
(node) => Array.from(node.childNodes).filter((n) => n.nodeType === 3).map((n) => n.data).join("")
"""

#: 预挂在 `rd-ai-thread` 上的观察器：每次变更记录 `lastElementChild` 自己的文本。
_INSTALL_OBSERVER_JS = f"""
() => {{
  const answerText = {_ANSWER_TEXT_JS.strip()};
  const thread = document.querySelector('[data-testid="rd-ai-thread"]');
  window.__snaps = [];
  new MutationObserver(() => {{
    const last = thread.lastElementChild;
    if (last) window.__snaps.push(answerText(last));
  }}).observe(thread, {{childList: true, subtree: true, characterData: true}});
  return true;
}}
"""

_LAST_MESSAGE_TEXT_JS = f"""
() => {{
  const answerText = {_ANSWER_TEXT_JS.strip()};
  const last = document.querySelector('[data-testid="rd-ai-thread"]').lastElementChild;
  return last ? answerText(last) : null;
}}
"""

#: 「请求已结束」：最后一条消息不再是占位符 ∧ send 已恢复 enabled。理由见模块 docstring。
_REQUEST_SETTLED_JS = f"""
(placeholder) => {{
  const answerText = {_ANSWER_TEXT_JS.strip()};
  const last = document.querySelector('[data-testid="rd-ai-thread"]').lastElementChild;
  const send = document.querySelector('[data-testid="rd-ai-send"]');
  return !!last && answerText(last) !== placeholder && !!send && !send.disabled;
}}
"""

#: 线程里的消息条数（每条消息一个直接子节点）。
_THREAD_CHILD_COUNT_JS = """
() => document.querySelector('[data-testid="rd-ai-thread"]').children.length
"""

#: X-1a′ 步骤 3：「浏览器确实渲染出了首块」——最后一条消息以 DELTAS[0] 开头且不是占位符。
_FIRST_DELTA_RENDERED_JS = f"""
([first, placeholder]) => {{
  const answerText = {_ANSWER_TEXT_JS.strip()};
  const last = document.querySelector('[data-testid="rd-ai-thread"]').lastElementChild;
  const text = last ? answerText(last) : "";
  return !!last && text !== placeholder && text.startsWith(first);
}}
"""


#: 被测服务恒在回环上（`tests/e2e/conftest.py` 的 `live_server` 挑的是 127.0.0.1 的空闲端口）。
#: 与 `conftest._LOCAL_HOSTS` 同义而**不 import**：本模块断的是「浏览器只跟本机说话」这条
#: 独立性质，从被测的闸那里取判据等于拿它自己证自己。
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: `reader.html` `<head>` 里两个**渲染阻塞**的字体 CDN（`preconnect` ×2 ＋ `stylesheet` ×1）。
#: 它们是模板今天就有的既存事实，`conftest` 的出网闸会把它们 abort 掉（那个闸的 docstring
#: 记着这段历史）。写成一份**字面量白名单**而不是「忽略所有被拦的域」：任何**新**出现的
#: 外部域——包括一次真的 provider 调用——都会落在白名单外，当场红。
_ALLOWED_EXTERNAL_ORIGINS = frozenset(
    {"https://fonts.googleapis.com", "https://fonts.gstatic.com"}
)


class _EgressLog:
    """浏览器侧出网台账：请求过哪些非回环 origin、**拿到过响应**的又有哪些。

    两个集合分别对应两件事：`requested` 是「页面试图连谁」（被 abort 的也算），
    `responded` 是「真的通了谁」。零真实出网这条不变式在浏览器侧的可判定形式是
    `responded == ∅`，而 `requested ⊆ 白名单` 把「试都不该试」也钉住。
    """

    def __init__(self) -> None:
        self.requested: Set[str] = set()
        self.responded: Set[str] = set()

    @staticmethod
    def _external_origin(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ""  # data: / blob:（epub.js 渲染正文用）根本不出网
        if parsed.hostname in _LOOPBACK_HOSTS:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"


@pytest.fixture
def browser_egress(page: Page) -> Iterator[_EgressLog]:
    """在**任何导航之前**挂上出网台账。

    必须比 `ai_page` 先建：监听器装在 `page.goto` 之后就漏掉了首个文档与 `<head>` 里那批
    子资源，而「多打了一个 provider」完全可能发生在页面加载期。
    """
    log = _EgressLog()

    def _on_request(request: Request) -> None:
        origin = log._external_origin(request.url)
        if origin:
            log.requested.add(origin)

    def _on_response(response: Response) -> None:
        origin = log._external_origin(response.url)
        if origin:
            log.responded.add(origin)

    page.on("request", _on_request)
    page.on("response", _on_response)
    yield log
    page.remove_listener("request", _on_request)
    page.remove_listener("response", _on_response)


@pytest.fixture
def ai_page(page: Page, live_server: str, ai_settings_ollama, browser_egress: _EgressLog) -> Iterator[Page]:  # type: ignore[no-untyped-def]
    """打开 `smoke_data` 第 0 章、点 `rd-rail-ai` 打开面板，并等到面板**真的**恢复完毕。

    `ai_settings_ollama` 必须在 `page.goto` **之前**生效：`reader.html` 把 `ai_default_provider`
    渲进 `Reader3Ctx.provider`，settings 晚一步写，页面拿到的就是 `anthropic`。

    「恢复完毕」的判据：`toggle()` → `restoreConversation()` → 空库 → `newChat()` → `renderThreads()`
    往 `rd-ai-history-list` 里追加一个 `rd-ai-conversation`；随后 `restoreConversation` 还会再跑一次
    `renderAll()`。**若在那之前就点 send**，`sendQuestion` 拿到的占位节点会被那次 `renderAll()` 重建成
    另一个节点，流式写进的是一个已脱离文档的元素——用例红，而红的原因与流式无关。所以先等历史项出现，
    再等 `networkidle`（那次 `renderAll()` 紧跟在 `/api/ai/conversations/…` 的响应之后，500ms 静默
    足以覆盖它）。
    """
    page.set_default_timeout(CASE_TIMEOUT_S * 1000)
    open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    page.get_by_test_id("rd-rail-ai").click()
    expect(page.get_by_test_id("rd-ai-panel")).to_have_attribute("aria-hidden", "false")
    expect(page.get_by_test_id("rd-ai-history-list").get_by_test_id("rd-ai-conversation")).to_have_count(1)
    page.wait_for_load_state("networkidle")
    assert page.evaluate(_INSTALL_OBSERVER_JS) is True
    yield page


def _send(page: Page, question: str) -> None:
    page.get_by_test_id("rd-ai-input").fill(question)
    page.get_by_test_id("rd-ai-send").click()


def _wait_settled(page: Page) -> str:
    """等请求结束（成功或 `Error: …`），返回最后一条消息的文本。"""
    page.wait_for_function(_REQUEST_SETTLED_JS, arg=PLACEHOLDER, timeout=RENDER_WAIT_TIMEOUT_S * 1000)
    text = page.evaluate(_LAST_MESSAGE_TEXT_JS)
    assert isinstance(text, str)
    return text


def _snapshots(page: Page) -> List[str]:
    raw = page.evaluate("() => window.__snaps.slice()")
    assert isinstance(raw, list)
    # 只剔除与占位符严格相等的帧。任何更宽的过滤都会把断言掏空——见模块 docstring。
    return [s for s in raw if s != PLACEHOLDER]


def _collapse_repeats(snaps: List[str]) -> List[str]:
    """去掉**连续**重复帧。MutationObserver 对同一段文本可能连发（属性/子树变更各一次），
    连续重复本身不是「没有增量」的证据；把它们折叠之后再要求严格增长，才既不误杀也不放水。"""
    out: List[str] = []
    for s in snaps:
        if not out or out[-1] != s:
            out.append(s)
    return out


def _incrementality_violations(snaps: List[str], final: str) -> List[str]:
    """**纯函数**判据：这串快照是否证明了「边收边渲」。返回违规列表（空 = 增量成立）。

    抽成纯函数只有一个理由：特征化用例没有红相位，而**这一条的判据本身可以被直接喂坏输入**。
    见 `SABOTAGE_LOG` 的 S5——两串坏序列直接喂进来，不需要起浏览器。

    它拦的是旧写法（`len(snaps) > 1` ＋ 前缀 ＋ 长度不减 ＋ 末帧 == 终态）**全部接受**的两串：

      * `[FINAL_TEXT, FINAL_TEXT]`——攒够一次性吐、末尾把 DOM 改了两次（`innerText = answer`
        之后 `renderAll()` 再重建一次，正是 `ai.js` 今天的收尾形状）。四条旧判据逐条成立。
      * `["", FINAL_TEXT]`——先清空占位、再一次性灌全文。空串是任何字符串的前缀，长度 0 ≤ N。

    两串的共同点：**没有任何一帧的文本是「一部分回答」**。所以新判据的核心是存在性——
    至少一帧满足 `0 < len(帧) < len(final)`。它不是「更严的同义反复」，而是把「增量渲染」
    这句话第一次写成了可判定的形式：非增量实现的每一帧要么是空的、要么就是全文。

    第二条（折叠连续重复后严格增长）今天由「前缀 ＋ 长度不减」蕴含（同长的两个前缀必然相等，
    所以重复帧只可能连续出现），留着是因为它蕴含于哪几条断言取决于那几条断言还在不在：
    谁若把「长度不减」放宽成「长度不减或相等即可」之类的写法，这一条仍会挡住重复追加。
    """
    problems: List[str] = []
    intermediate = [s for s in snaps if 0 < len(s) < len(final)]
    if not intermediate:
        problems.append(
            f"没有任何一帧是「回答的一部分」（长度严格落在 0 与 {len(final)} 之间）："
            f"{[len(s) for s in snaps]!r}。每一帧要么是空的、要么就是全文——"
            "这正是「攒够一次性渲染 ＋ 末尾把 DOM 改了两次」的形状，不是边收边渲"
        )
    collapsed = _collapse_repeats(snaps)
    if len(collapsed) < 2:
        problems.append(
            f"折叠连续重复帧后只剩 {len(collapsed)} 帧：{collapsed!r}——同一段文本被写了 N 次，"
            "不构成任何增量"
        )
    lens = [len(s) for s in collapsed]
    if any(b <= a for a, b in zip(lens, lens[1:])):
        problems.append(
            f"折叠连续重复帧后长度不是严格增长：{lens!r}（折叠后的帧 {collapsed!r}）——"
            "有帧在重复或回退"
        )
    return problems


# ---------------------------------------------------------------------------
# X-1a 首 token 增量渲染：更新次数 > 1 且每次更新都是最终文本的前缀（property / S5 / L2）
# ---------------------------------------------------------------------------
def test_x1a_streaming_renders_incrementally_and_every_frame_is_a_prefix(
    ai_page: Page, ai_stub: OllamaStub
) -> None:
    page = ai_page
    _send(page, QUESTION)
    final = _wait_settled(page)

    snaps = _snapshots(page)
    assert final == FINAL_TEXT, (
        f"最终文本不是桩发出的全部 delta 拼接：{final!r} != {FINAL_TEXT!r}"
        f"（若形如 'Error: …'，先查提问 {QUESTION!r} 是否仍是语料正文的逐字子串）"
    )
    assert len(snaps) > 1, (
        f"过滤占位符后只剩 {len(snaps)} 帧：{snaps!r}——浏览器侧是攒够一次性渲染，不是边收边渲"
    )
    not_prefix = [s for s in snaps if not final.startswith(s)]
    assert not not_prefix, f"以下帧不是最终文本的前缀（乱序/重复拼接）：{not_prefix!r}；全部帧 {snaps!r}"
    lengths = [len(s) for s in snaps]
    assert lengths == sorted(lengths), f"帧长度不是单调不减：{lengths!r}；全部帧 {snaps!r}"
    assert snaps[-1] == final == FINAL_TEXT, f"末帧 {snaps[-1]!r} != 终态 {final!r} != 期望 {FINAL_TEXT!r}"
    # 增量性本身（上面四条合起来仍接受 `[FINAL, FINAL]` 与 `["", FINAL]`——见
    # `_incrementality_violations` 的 docstring 与 SABOTAGE_LOG 的 S5）。
    problems = _incrementality_violations(snaps, FINAL_TEXT)
    assert not problems, "帧序列没有证明「边收边渲」：\n" + "\n".join(f"  - {p}" for p in problems) + (
        f"\n全部帧 {snaps!r}"
    )


# ---------------------------------------------------------------------------
# X-1a′ 桩侧握手：服务端收到全部 delta 之前，浏览器已渲染出第一块（property / S5 / L2）
# ---------------------------------------------------------------------------
def test_x1a_prime_first_delta_is_rendered_before_the_stub_sends_the_last_one(
    ai_page: Page, ai_stub: OllamaStub
) -> None:
    page = ai_page
    ai_stub.gate_mode = True  # 桩写完 DELTAS[:-1] 后阻塞于 gate.wait(STUB_GATE_TIMEOUT)

    _send(page, QUESTION)
    # 步骤 3：「浏览器确实渲染出了首块」。显式 timeout，不吃 Playwright 默认值（矩阵 R2）。
    page.wait_for_function(
        _FIRST_DELTA_RENDERED_JS,
        arg=[DELTAS[0], PLACEHOLDER],
        timeout=RENDER_WAIT_TIMEOUT_S * 1000,
    )
    # 步骤 4：放行。桩写出末块与 done 行。
    ai_stub.gate.set()
    final = _wait_settled(page)

    assert ai_stub.completed is True, (
        "桩没有走完握手：末块从未发出。gate 在 STUB_GATE_TIMEOUT 内没等到 set()——"
        "浏览器不是在流式期间渲染首块的（攒够一次性吐），或首块渲染晚于桩的超时"
    )
    assert ai_stub.gate_released_by_render is True, (
        "桩记录 gate 是超时放行而不是被 set() 放行——「浏览器先渲染、上游后发末块」这条因果没有成立"
    )
    assert final == FINAL_TEXT, f"握手走完后最终文本应完整：{final!r} != {FINAL_TEXT!r}"


# ---------------------------------------------------------------------------
# X-1b 流正常结束：最终文本 == 全部 chunk 拼接，且零真实出网（success / S1 / L1+L2）
# ---------------------------------------------------------------------------
def test_x1b_stream_ends_with_the_full_text_and_zero_real_egress(
    ai_page: Page, ai_stub: OllamaStub, ai_settings_ollama, browser_egress: _EgressLog
) -> None:  # type: ignore[no-untyped-def]
    """X-1b：终态文本 == 桩发出的全部 delta，且「零真实出网」在**三个可观测面**上各断一次。

    「零真实出网」这句话的可判定形式取决于**谁**可能出网，本条覆盖其中三面：

      1. **桩侧流量**（旧有）：`request_count == 1`、`payloads` 恰好一条——服务端没有把同一个
         提问打给桩两次，也没有在打桩之外另发一份。
      2. **服务端的出网面**（新增）：服务读的那份 `ai_settings.json` 里**只有一个** provider
         条目、它 enabled 且 `base_url` 就是回环上的桩、**全文没有任何非空 api_key**。
         没有凭据、没有第二个 endpoint，就没有「配置驱动的真实 provider 调用」这条路。
      3. **浏览器的出网面**（新增）：本条用例期间，页面拿到响应的非回环 origin 集合为空；
         试图连接的非回环 origin 只有模板 `<head>` 里那两个字体 CDN（`_ALLOWED_EXTERNAL_ORIGINS`），
         而它们全部被 `conftest` 的闸 abort、一个响应都没拿到。多打一个
         `https://api.anthropic.com` 之类会立刻落在白名单外。

    **仍未覆盖的一面（诚实登记）**：服务**进程**若在代码里硬编码一个出网目标（遥测、写死的
    provider host），本条三面都看不见——(1) 只数打桩的次数，(2) 只看配置，(3) 只看浏览器。
    真正闭合它需要一道服务端的 fail-closed 出网闸（在服务子进程里挂 socket 层拦截，只放行
    回环，并把被拦的目标回传给用例），那是一件独立的基建，不在本 WI 的授权范围内
    （`conftest.py` 本波不得改）。任务书 §0.6 的跨波欠账里另行登记。
    """
    page = ai_page
    assert ai_stub.base_url.startswith("http://127.0.0.1:"), f"桩不在回环地址上：{ai_stub.base_url}"
    assert ai_stub.request_count == 0, "打开面板不该触发任何 provider 请求"

    _send(page, QUESTION)
    final = _wait_settled(page)

    assert final == FINAL_TEXT, f"{final!r} != {FINAL_TEXT!r}（settings 文件：{ai_settings_ollama}）"
    assert ai_stub.request_count == 1, f"一次提问应恰好打桩一次，实际 {ai_stub.request_count} 次"
    assert len(ai_stub.payloads) == 1, (
        f"桩收到 {len(ai_stub.payloads)} 份请求体，应恰好 1 份：{ai_stub.payloads!r}"
    )
    assert ai_stub.completed is True, "桩没有发出末块与 done 行，流不是「正常结束」"
    sent_model = ai_stub.payloads[0].get("model")
    assert sent_model == "stub-model", f"服务端发给桩的 model 不是沙箱 settings 里的那个：{sent_model!r}"

    # (2) 服务端的出网面：那份 settings 里除了回环上的桩，没有第二个 endpoint、没有任何凭据。
    settings = json.loads(Path(ai_settings_ollama).read_text(encoding="utf-8"))
    providers = settings.get("providers", {})
    assert set(providers) == {"ollama"}, (
        f"沙箱 settings 里的 provider 不止桩一个：{sorted(providers)}（文件 {ai_settings_ollama}）"
        "——多出来的每一个都是一条真实出网的可能路径"
    )
    assert providers["ollama"].get("base_url") == ai_stub.base_url, (
        f"settings 里的 base_url {providers['ollama'].get('base_url')!r} 不是本条的桩地址 "
        f"{ai_stub.base_url!r}——服务端这一轮打的可能根本不是桩"
    )
    with_keys = [
        name for name, cfg in providers.items() if str((cfg or {}).get("api_key") or "").strip()
    ]
    assert not with_keys, (
        f"沙箱 settings 里这些 provider 带着非空 api_key：{with_keys}（文件 {ai_settings_ollama}）。"
        "e2e 的确定态是「没有凭据」——有 key 就有拿别人额度打真实 provider 的可能"
    )

    # (3) 浏览器的出网面：零非回环响应；非回环请求只允许模板既有的两个字体 CDN。
    assert browser_egress.responded == set(), (
        f"浏览器从这些非回环 origin 拿到了响应：{sorted(browser_egress.responded)}——"
        "「零真实出网」在浏览器侧的判据就是这个集合为空"
    )
    unexpected = browser_egress.requested - _ALLOWED_EXTERNAL_ORIGINS
    assert not unexpected, (
        f"浏览器试图连接白名单之外的外部 origin：{sorted(unexpected)}"
        f"（本条允许的只有模板 <head> 里的字体 CDN {sorted(_ALLOWED_EXTERNAL_ORIGINS)}，"
        "且它们全部被 conftest 的出网闸 abort）。新增一个外部依赖就要在这里显式登记"
    )
    # SSE `meta` 事件的 `retrieval_sources` 到达了 DOM：降级检索恒命中第 0 章，页脚恰好一条引用。
    citation = page.get_by_test_id("rd-ai-thread").get_by_test_id("rd-ai-citation")
    expect(citation).to_have_count(1)
    expect(citation).to_have_attribute("data-section", "0")


# ---------------------------------------------------------------------------
# X-1c 中断后可恢复：stop → 再发一次 → 完整收到（state / S5 / L2）
# ---------------------------------------------------------------------------
def test_x1c_stop_then_resend_completes_in_full(ai_page: Page, ai_stub: OllamaStub) -> None:
    page = ai_page
    # 第一次：与 X-1a′ 同一套 gate——桩写完前三块后阻塞，用例在「首块已渲染」之后点 stop，
    # **不用 sleep** 决定「流进行到一半」这个时点。
    ai_stub.gate_mode = True
    _send(page, QUESTION)
    page.wait_for_function(
        _FIRST_DELTA_RENDERED_JS,
        arg=[DELTAS[0], PLACEHOLDER],
        timeout=RENDER_WAIT_TIMEOUT_S * 1000,
    )
    expect(page.get_by_test_id("rd-ai-stop")).to_be_visible()
    page.get_by_test_id("rd-ai-stop").click()
    aborted = _wait_settled(page)
    assert aborted != FINAL_TEXT, "点了 stop 却收到了完整回答——stop 没有中止 fetch"
    # 因果断言（不掐表）：浏览器侧的收尾发生在桩放弃 gate **之前**。stop 若没真的中止 fetch，
    # 浏览器只会在桩 5s 超时干净收尾之后才结束——那时 gate_timed_out 已为 True。
    assert ai_stub.gate_timed_out is False, (
        "stop 之后浏览器侧的收尾发生在桩 gate 超时**之后**——stop 没有中止进行中的 fetch，"
        "「收尾」只是上游放弃后的自然结束"
    )
    assert ai_stub.completed is False, "stop 时桩还不该发出末块（gate 尚未放行）"
    expect(page.get_by_test_id("rd-ai-send")).to_be_enabled()

    # 放行桩，让第一个连接的 provider 侧收尾；第二次不再握手。
    ai_stub.gate.set()
    ai_stub.gate_mode = False

    # 第二次：同一面板、新问题。租约若没释放，第二次会在队列上等到 provider timeout_s，
    # 拿到的是 `Error: AI request timed out`——那正是本条要抓的东西。
    _send(page, QUESTION)
    final = _wait_settled(page)

    assert final == FINAL_TEXT, f"中断后的第二次提问没有完整收到：{final!r} != {FINAL_TEXT!r}"
    assert ai_stub.request_count == 2, f"两次提问应打桩两次，实际 {ai_stub.request_count} 次"
    thread_len = page.evaluate(_THREAD_CHILD_COUNT_JS)
    assert thread_len == 4, (
        f"线程里应有 4 条消息（问、被中止的答、问、完整的答），实际 {thread_len} 条——"
        "第二次提问不是同一面板里的新问题"
    )
    expect(page.get_by_test_id("rd-ai-send")).to_be_enabled()


SABOTAGE_LOG = """
2026-09-04，chromium 1280×720。S1–S3 经一次性模块 `tests/e2e/test_zz_sabotage_wi16.py` 用 `page.route`
改写 `/static/ai.js` 的响应体（每个改写目标断言在原文里**恰好出现 1 次**，命中数 != 1 即抛，不让「改写
没生效」冒充证据），四条用例各跑一遍；S4 针对 unit lane 的桩契约，改的是 `tests/fixtures/ai_stub.py`
的一份临时副本（就地替换 → 跑 → 从备份还原，sha256 前后一致）。还原核验：一次性模块已删；
`git status --short` 只剩本 WI 的文件；`git diff --quiet -- src/` 退出 0。耗时来自 `--durations=0`。

| # | 破坏点（改写目标） | 红 | 绿 | 失败输出摘录 / 失败形态 |
|---|---|---|---|---|
| S1 | `ai.js` 流式分支：`for await (… of streamSseResponse(resp))` → `streamSseResponse(new Response(await resp.text()))`（先读完整个 body 再回放），并把 `placeholderEl.innerText = answer` 那行删掉（只靠末尾 `renderAll()` 渲染一次） | X-1a / X-1a′ / X-1c | X-1b | X-1a：`过滤占位符后只剩 1 帧：['Alpha 是第一章的第一个词。']——浏览器侧是攒够一次性渲染`。**X-1a′ 以断言失败，call 5.06s**：`桩没有走完握手：末块从未发出。gate 在 STUB_GATE_TIMEOUT 内没等到 set()`——桩在 5s 干净收尾、浏览器随后一次性渲染、步骤 3 在 15s 预算内等到首块、用例走到 `assert stub.completed is True`；**不是** timeout（RENDER_WAIT 15s / CASE 30s 都没撞到），这正是 R2 序关系要买的失败形态。X-1c：`Locator expected to be visible`（`rd-ai-stop`，call 10.06s）——首块直到整段到齐才出现，那时请求已结束、stop 已隐藏。X-1b 绿：它只断终态，对「攒够再吐」本来就是盲的，这是 X-1a′ 存在的理由 |
| S2 | `ai.js` `placeholderEl.innerText = answer` → `= delta`（每块只渲染本块，破坏前缀单调性） | X-1a / X-1a′ / X-1c | X-1b | X-1a：`以下帧不是最终文本的前缀（乱序/重复拼接）：['是第一章的', '第一个', '词。']；全部帧 ['Alpha ', '是第一章的', '第一个', '词。', 'Alpha 是第一章的第一个词。']`。X-1a′（5.05s）与 X-1c（10.06s）红的形状同 S1：首块 `Alpha ` 一闪即被下一块覆写，「以 DELTAS[0] 开头」直到桩超时后的 `renderAll()` 才成立 |
| S3 | `ai.js` `abort()` 里的 `this.abortController?.abort?.()` 删掉（stop 不中止 fetch） | **仅 X-1c**（call 5.05s） | X-1a / X-1a′ / X-1b | `stop 之后浏览器侧的收尾发生在桩 gate 超时**之后**——stop 没有中止进行中的 fetch，「收尾」只是上游放弃后的自然结束`。**这一枪暴露了首版 X-1c 的盲区**：只断「第二次完整收到 + 桩请求数 == 2 + 线程 4 条」时，S3 下四条全绿——桩 5s 放弃后浏览器照样结束、第二次照样成功。因此录收据之后给 X-1c **追加**了两条断言（`ai_stub.gate_timed_out is False`、`ai_stub.completed is False`，见用例内注释）并给桩加了 `gate_timed_out` 标志；没有改动任何既有断言 |
| S4 | `tests/fixtures/ai_stub.py` 临时副本：gate 超时分支由「写 chunked 终止块」改成 `connection.shutdown(SHUT_RDWR); close()`（中止连接） | unit `test_gate_timeout_ends_the_body_cleanly_without_the_last_delta` | 另两条 unit | `Failed: gate 超时后桩没有干净收尾，客户端读到连接异常：ChunkedEncodingError: Response ended prematurely。 这会让 X-1a′ 从「断言失败」退化成「timeout 失败」`——正是契约条款 (3) 要拦的写法 |

-------------------------------------------------------------------------------
2026-09-05 追加的两枪（S5 / S7），打的是**判据本身**
-------------------------------------------------------------------------------

**S5（X-1a 的增量性判据，纯函数，不起浏览器）**：把两串坏序列直接喂给
`_incrementality_violations`，并同时用旧的四条判据（`len > 1` ／ 全是前缀 ／ 长度不减 ／
末帧 == 终态）算一遍同一串。`FINAL_TEXT` 长 16，实测：

| 喂进去的帧序列（按长度） | 旧四条判据 | 新判据 |
|---|---|---|
| `[16, 16]`（`[FINAL, FINAL]`：攒够一次性吐，末尾把 DOM 改了两次） | **接受** | 拒绝：`没有任何一帧是「回答的一部分」…` ＋ `折叠连续重复帧后只剩 1 帧` |
| `[0, 16]`（`["", FINAL]`：先清空再一次性灌全文） | **接受** | 拒绝：`没有任何一帧是「回答的一部分」（长度严格落在 0 与 16 之间）：[0, 16]` |
| `[5, 16]`（对照组：真增量） | 接受 | **接受**（零违规） |

前两串正是 `ai.js` 今天的收尾形状（`innerText = answer` 之后 `renderAll()` 再重建一次）在
「非增量实现」下会留下的痕迹——旧判据全盘接受，这一条用例的**全部目的**因此落空。

**S7（X-1b 的零出网判据，浏览器侧那一面）**：`page.route` 把 `/static/ai.js` 的
`async sendQuestion() {` 改写成「先 `fetch('https://api.anthropic.com/v1/messages')`、再调原实现」
（命中数核对为 1；`src/` 未动），即一个**既打桩又打真实 provider**的实现。实测出网台账：
`requested: ['https://api.anthropic.com', 'https://fonts.googleapis.com']`、`responded: []`。
于是 `requested - 白名单 == {'https://api.anthropic.com'}`，X-1b 的第 (3) 面**红**；而
`responded == ∅` 这一项**仍绿**——因为 `conftest` 的出网闸把它 abort 了。两项分工由此实测确认：
`responded` 断的是「有没有真的通」，`requested` 断的是「有没有试」，**能抓到这一枪的是后者**。
只断前者的写法会把「代码里多打了一个 provider」当成合规，理由仅仅是测试环境恰好把它拦下了。

每条用例各自被哪一枪咬住：X-1a ← S1（帧数）/ S2（前缀）/ S5（增量性判据本身）；
X-1a′ ← S1 / S2（都以 `completed` 断言失败，不以 timeout 失败）；
X-1b ← S7（浏览器侧多打一个真实 provider）——它对 S1–S3 那三种**流式实现**的破坏仍是全盲的
（终态等值用例的已知形状），但不再对「多打了一个出网目标」全盲；
X-1c ← S1 / S2（stop 不可见）/ S3（因果断言）；桩契约 ← S4。

**X-1b 仍未覆盖的一面**：服务**进程**里硬编码的出网目标（遥测、写死的 provider host）。
三面判据分别只数打桩次数、只看配置、只看浏览器，都够不到它。闭合它需要一道服务端的
fail-closed 出网闸：在 `live_server` 起子进程时注入一个 sitecustomize（或 `-X importtime` 式的
预载模块），把 `socket.socket.connect` 包一层，非回环目标一律抛并记录到一个文件，用例结束后
读那个文件断言为空。它要动 `tests/e2e/conftest.py` 与服务的启动方式，本波无授权，另行立项。
"""
