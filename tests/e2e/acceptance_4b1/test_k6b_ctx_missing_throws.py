"""WI-17 —— K-6b：`window.Reader3Ctx` 缺失时**抛错而非静默猜测**，且相对非空基线零写入（`acceptance_4b1`，skip，一条）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「K-6b（R1 修改）」。任务书 §4 的
K-6b 行、§0.5 现状特征化表的 K6 行。契约唯一定义处 `contracts/annotation-host-contracts.md` K6：
「**删除 `location.pathname` 回退分支**。`window.Reader3Ctx` 读不到时直接抛错，不要猜。这是 4B.1 里唯一
一处**故意的行为变更**——保留它意味着 4B.2 改路由后批注静默存到错章，污染用户数据的代价远高于少一层兜底。」

**与 `baseline_1b/test_kernel_actions_and_url.py`（K-6a）的分工。** K-6a 断今天的正向行为：URL 里的章号
落进 `chapter_index`。本条断 4B.1 之后的反向行为：上下文读不到时**什么都不写**、并且响亮。今天的
`getReaderContext()` 在 `Reader3Ctx` 缺失时会回退解析 `location.pathname`，所以今天本条的注入支会**成功写入
一条**（回退分支就是这么工作的）——那是 (2) 红，也是它今天必须 skip 的原因。

**两处从 Round 1 改掉的构造，理由必须留着（矩阵 R1）：**

1. **在渲染完成之后 `page.evaluate("delete window.Reader3Ctx")`，不是 `add_init_script`。**
   `epub-renderer.js` 与 `annotations.js` 的初始化都读 `Reader3Ctx`；文档创建前就删掉它，渲染器根本
   起不来，iframe 里没有正文，`select_in_frame` 建不出选区——用例在「创建标注」之前就以一个与 K6 无关的
   原因失败。渲染完成后再删，被破坏的只有「创建标注时去读上下文」这一条路径，正是契约点名的那条。
2. **相对一个非空基线断零增量，不是断「仍为空」。** 空基线上，「什么都没发生」（按钮委托坏了、选区没建
   起来、JS 早就整个报错停了）同样让它保持空 ⇒ 绿。对照支先证明这条链在注入前是通的（写成功一条），
   注入支再断 `read_notes() == baseline`（整列表等值）：静默写了一条 ⇒ 红；而「什么都没发生」也不再能
   靠空基线蒙混。

**第三处构造，2026-09-05 由 009 审计发现 #56 逼出来：`pageerror` 与 `console.error` 分两个 sink。**
首版把两者 `append` 进同一个列表 `errors`，然后断「`errors` 里有一条点名 Reader3Ctx」。那条断言
**接受一个只记了一笔然后照常返回的实现**——`console.error("… Reader3Ctx …"); return {bookId: null, …}`
让它绿，而这正是契约 K6 明令不要的静默失败的另一副面孔（第一副是猜 `location.pathname`）。合流的
sink 让「谁满足了它」不可分辨，本条要断的却恰恰是**抛**与**记**的差别。现在 (1) 只认 `pageerror`；
`console.error` 降级为失败消息里的诊断信息，一条都不参与判定。

**为什么 `pageerror` 这条判据是可满足的（实测，2026-09-05，playwright 1.62 / chromium）。** 创建路径
是异步的，且 promise 被丢掉了——工具条的 click 监听器 `handleAction(action)` 直接 `return
this.toggleMarkerAnnotation(...)`，返回值没人接。`createAnnotation` 里抛出的错于是不是「未捕获异常」
而是**未处理的 rejection**。探针实测：playwright 把两者**都**报成 `pageerror`（`setTimeout` 里同步
throw、以及 `(async () => { throw ... })()`，两条都到了 `page.on("pageerror")`），而
`console.error(...)` **不产生** `pageerror`。所以 4B.1 无论把 throw 放在 `getReaderContext()` 里还是
放在调用点，(1) 都拿得到证据；能让 (1) 红的只有「不抛」。

**空 sink 不许冒充通过。** 「一条 pageerror 都没有」在页面没加载、选区没建起来、工具条没唤出时同样
成立。(0) 先断工具条可见（点击本身还有 playwright 的可操作性等待兜一层），(1) 的失败消息再把两个
sink 的条数逐个列出来，把三种读法（都空／只有 console／有 pageerror 但不点名）当场分开。

**语料事实（与 W-5a-⓪ 的旁观条同源，目的相反）**：第 0 章 body 是 `OneAlpha prose.`，`One`（`<h1>`）与
`Alpha prose`（`<p>`）互不重叠。对照支写在 `Alpha prose` 上，注入支选 `One`——要证明的是「另一段上什么都
没被写」。语料一改两边同时失效，W-5a-⓪ 那边的 docstring 也写着这句。

**解 skip 的顺序**：4B.1 删掉 `location.pathname` 回退 ⇒ 删本文件 skip 行 ⇒ `-m acceptance_4b1`。
4B.1 之后若有人把回退加回来，注入支会成功写入一条，(2) 红——那是正确的红。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    SELECTION_TIMEOUT_MS,
    open_ch0,
    read_notes,
    scan_marks,
    select_in_frame,
    wait_for_notes,
)

pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1：契约 K6 的『Reader3Ctx 缺失 ⇒ 抛错、不回退解析 location.pathname』是 4B.1 "
            "唯一故意的行为变更，今天回退分支仍在、注入支会成功写入一条。"
            "到期动作：4B.1 删掉回退分支后删本行。"
        )
    ),
]

#: 注入支选的另一段文字（`<h1>One</h1>`），与对照支的 `Alpha prose` 不重叠。
OTHER_QUOTE = "One"
#: 抛错消息里必须出现的 token——断内容，不断「有错误发生」。
CTX_TOKEN = "Reader3Ctx"
#: 对照支之后基线的条数，字面量（§0 第五条纪律）。
BASELINE_COUNT = 1
#: 刺激的前置宿主：它可见，才谈得上「点了之后什么都没抛」（见 (0)）。
TOOLBAR_TESTID = "rd-anno-toolbar"


def _wait_for_hits(page: Page, sink: List[str], needle: str) -> List[str]:
    """轮询**一个** sink，等到里面出现含 `needle` 的消息；超时就返回当下的（可能是空的）命中集。

    参数是单个 sink 而不是「若干个 sink 拼起来的那一个」——这是审计发现 #56 的收口点。
    两个来源混进同一个列表之后，「是谁满足了这条断言」在断言处就再也分不出来了，而本模块
    要断的差别恰恰住在来源上：`pageerror` ⇒ 真的抛了，`console.error` ⇒ 只是记了一笔。
    """
    deadline = time.monotonic() + SELECTION_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        found = [m for m in sink if needle in m]
        if found:
            return found
        page.wait_for_timeout(50)
    return [m for m in sink if needle in m]


def test_k6b_missing_reader_ctx_throws_and_writes_nothing(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """K-6b（S3 / L2）：删掉 `window.Reader3Ctx` 后建标注 ⇒ **pageerror** 点名 Reader3Ctx（console.error 不算）；`notes.json` 与基线逐字段相等；DOM 上没有新 `<mark>`。"""
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    # ---- 对照支：这条链在注入前是通的（非空基线）--------------------------------------
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()
    wait_for_notes(e2e_books_dir, BOOK_ID, BASELINE_COUNT)

    frame = open_ch0(page, live_server, expected_marks=BASELINE_COUNT)
    baseline = read_notes(e2e_books_dir, BOOK_ID)
    assert len(baseline) == BASELINE_COUNT, f"对照支应留下恰好 {BASELINE_COUNT} 条：{baseline}"
    assert baseline[0]["quote"] == CH0_QUOTE

    # ---- 注入支：渲染完成之后删掉全局上下文，只破坏「建标注时读上下文」这一条路径 --------
    # 两个 sink 严格分开（审计发现 #56）：page_errors 是判据，console_errors 只进失败消息。
    page_errors: List[str] = []
    console_errors: List[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    posts: List[str] = []
    page.on(
        "request",
        lambda req: posts.append(req.url) if req.method == "POST" and "/api/notes/" in req.url else None,
    )

    page.evaluate("() => { delete window.Reader3Ctx; }")
    assert page.evaluate("() => typeof window.Reader3Ctx") == "undefined", "注入没生效：Reader3Ctx 还在"

    select_in_frame(frame, OTHER_QUOTE)

    # (0) 刺激确实发生过：工具条**此刻**可见，下一行的点击才是「建标注」而不是空转。
    #     「一条 pageerror 都没有」在页面没走到读上下文那一步时同样成立，(1) 会以一条空 sink
    #     报绿——所以空 sink 必须先报成它自己。这条是第二道：`select_in_frame` 内部已经等过
    #     一次工具条可见（S3 实测就是它先红的，见 SABOTAGE_LOG），本行断的是选区建好之后、
    #     点击发生之前那一段里它**没有被 ~250ms 自激循环关掉**，且不依赖 helper 的内部实现。
    expect(page.get_by_test_id(TOOLBAR_TESTID)).to_be_visible()
    page.get_by_test_id("rd-anno-type-marker").click()

    # (1) 抛错：至少一条 **pageerror** 点名 Reader3Ctx。console.error 不参与判定——
    #     「记一笔然后照常返回」是契约 K6 不接受的那种静默，不能拿来给「抛了」作证。
    loud = _wait_for_hits(page, page_errors, CTX_TOKEN)
    assert loud, (
        f"Reader3Ctx 缺失后 {SELECTION_TIMEOUT_MS}ms 内没有任何点名它的 **pageerror**。\n"
        f"  pageerror（{len(page_errors)} 条，判据）：{page_errors}\n"
        f"  console.error（{len(console_errors)} 条，仅诊断，不能替 (1) 作证）：{console_errors}\n"
        "    三种读法：两个 sink 都空 ⇒ 这条路径压根没跑到读上下文那一步；"
        "只有 console.error 点名了它 ⇒ 实现记了一笔就照常返回，与静默猜测同罪（审计发现 #56）；"
        "有 pageerror 但不点名 ⇒ 抛的是别的错，K6 要的是一条说得出缺了什么的错。"
    )

    # (2) 相对非空基线零增量：整列表逐字段等值。静默写了一条 ⇒ 红；没写但基线被动了 ⇒ 也红。
    assert posts == [], f"上下文缺失却仍发出了 POST /api/notes：{posts}"
    after = read_notes(e2e_books_dir, BOOK_ID)
    assert after == baseline, (
        f"上下文缺失时 notes.json 变了——这就是「污染用户数据」：\n  基线：{baseline}\n  现在：{after}"
    )

    # (3) 刷新后 DOM 上仍只有对照支那一条 `<mark>`，`One` 上没有新的。
    frame = open_ch0(page, live_server, expected_marks=BASELINE_COUNT)
    assert set(scan_marks(frame)["texts"]) == {CH0_QUOTE}, (
        f"刷新后 <mark> 的文本集合是 {set(scan_marks(frame)['texts'])}，期望只有 {{{CH0_QUOTE!r}}}"
    )
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(BASELINE_COUNT)


# ---------------------------------------------------------------------------
# 可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-05，全部已还原）
# ---------------------------------------------------------------------------

SABOTAGE_LOG = """
2026-09-05，chromium 1280×720，playwright 1.62。本条今天 skip，跑它证明不了任何事——所以证据不是
「跑一遍看它绿」，而是**把 4B.1 的两种可能实现合成出来**，看判据分不分得开。合成走
`page.route("**/static/js/annotations.js", …)`：从磁盘读出真实的 `annotations.js`、在内存里把
`getReaderContext()` 的 `location.pathname` 回退段替换掉、`route.fulfill()` 喂给浏览器；锚点串先
`assert source.count(FALLBACK) == 1`——锚点对不上时这次运行当场判废，不让「替换了个寂寞」冒充证据。
`src/` 一个字节没碰。承载破坏的是一次性模块 `test_zz_tmp_sabotage_56.py`（`import` 本模块的用例函数、
装好 route 再直接调它，**被测断言逐字是同一份**；模块级 skip 不随函数传递，所以 skip 行从头到尾没动过），
跑完即删，因此它没有进入任何条数常量。还原核验：一次性模块已删；`git diff --quiet -- src/` 退出 0。

| # | 合成出来的实现（只改 `getReaderContext()` 的回退段） | 判据 (1) | 失败输出（逐字）／形态 |
|---|---|---|---|
| S1「漏洞版」 | `console.error("[Annotations] missing window.Reader3Ctx; skipping annotation"); return { bookId: null, chapterIndex: null };`——记一笔，照常返回，**不抛** | **红** | `AssertionError: Reader3Ctx 缺失后 8000ms 内没有任何点名它的 **pageerror**。` ／ `pageerror（0 条，判据）：[]` ／ `console.error（1 条，仅诊断，不能替 (1) 作证）：['[Annotations] missing window.Reader3Ctx; skipping annotation']` ／ `assert []`。(2)(3) 在这一支下本来就成立（它确实什么都没写）——**能把它判红的只有 (1)**，这正是审计发现 #56 要的那条差别 |
| S2「正确版」 | `throw new Error("[Annotations] window.Reader3Ctx is missing - refusing to guess the chapter");` | **满足** | 整条用例 `1 passed in 13.73s`——(1) 拿到 pageerror，(2) 零写入，(3) 刷新后仍只有对照支那一条 `<mark>`。没有任何一条断言因「生产没准备好」而红 |
| S0「反证」 | 生产同 S1（漏洞版）；**用例**换成 `HEAD` 上合流 sink 的旧版（`git show HEAD:… > zz_tmp_old56.py`，一个字没改） | 旧判据 **绿** | `2 passed`（漏洞版与正确版**都**绿）。旧判据 `errors` 里同时装着两个来源，`console.error` 那一条就把它满足了——这就是发现 #56 说的假绿，也是 S1 那一枪的对照 |
| S3「空 sink」 | 生产：正确版 ＋ 在 `handleSelectionRange(range) {` 首行插 `if (!window.Reader3Ctx) return;`（刺激根本不发生，工具条永不唤出；只在注入支生效，对照支照常） | 轮不到 (1) | `playwright._impl._errors.Error: Locator.evaluate: Error: select_in_frame: 8000ms 内 rd-anno-toolbar 没有进入 is-visible。选区文本="One" rangeCount=1 Reader3AnnotationUI=present`。**红在 `select_in_frame` 自己的门里，早于 (0) 与 (1)**——空 sink 报成了它自己，不是报成一条「没抛错」。(0) 因此是第二道而不是第一道，它守的是选区建好之后到点击之前那一段 |

**S2 能成立靠一条实测事实，不是靠推理**：创建路径的 promise 被丢掉了（工具条的 click 监听器
`return this.toggleMarkerAnnotation(...)`，返回值没人接），所以 `getReaderContext()` 里的 throw
到不了「未捕获异常」，只是一条**未处理的 rejection**。独立探针（`sync_playwright` 起一个空白页，
分别 `setTimeout(() => { throw ... })` 与 `(async () => { throw ... })()`）实测 playwright 1.62 把
**两者都**报成 `pageerror`，而 `console.error(...)` 一条 `pageerror` 都不产生。所以 (1) 对 4B.1 是
可满足的，而 S1 那种写法在任何实现姿势下都满足不了它。
"""
