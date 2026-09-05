"""WI-17 —— W-5b：改色后颜色变为 green、**`id` 不变**、该段文字上仍**恰好一条**（`acceptance_4b1`，skip，参数化 ×3）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` `## WI-17:` Unit B「W-5b（R1 修改）」。任务书 §3 的
W-5b 行、§0.5「W-5 为什么也落在这里（2026-09-01 裁定）」、§0.6 跨波欠账 **#9**。期望行为的落地定义在前端计划
`plan-frontend-ui-refactor.md` 的 WI-14。

**Law（S5，身份守恒）**：「改色」是对**同一条**标注的一次原地更新——`id` 不变、`type` 不变、`quote` 不变、
`color` 变为所点的色、该段文字上标注总数不变。

**为什么必须是三条参数。** `marker` 走 `toggleMarkerAnnotation`，`wavy` / `underline` 走 `toggleAnnotation`，
**是两份独立实现**。4B.1 要改的是两处，只写一条等于只给其中一处买了期望行为的证据。

**⚠️ 阻塞者：跨波欠账 #9——改色 wavy / underline 今天会静默丢数据。** `toggleAnnotation` 的异色分支先
`await deleteAnnotations(anyIds)`，其中的 `loadAndRender()` 重绘会 `normalize()` 文本节点，把 `currentRange`
塌成空 range，紧接着的 `createAnnotation` 带着空 `quote` 吃一个 400——净结果 `DELETE 204 → POST 400 →
该选区一条不剩`（W-5a-③ 特征化了它）。**4B.1 必须先修掉 #9，再解本模块的 skip**：否则 `wavy` /
`underline` 两个参数连「有一条标注在」都不成立，红的会是「0 条」而不是「id 变了」，把人指向错的地方。
`marker` 那一支今天不丢数据但会**另加一条**（W-5a-②），本条在它上面红在「2 条」。

**4B.1 配对关系（Gap 10，必须在两边 docstring 各写一次；W-5a 那边在
`baseline_1b/test_write_recolor_and_delete.py`）：**

| W-5b 参数 | 对应的 W-5a 支 | 4B.1 同 commit 动作 |
|---|---|---|
| `marker` | W-5a-② | 解开本参数的 skip；W-5a-② 改判或转出 |
| `wavy` | W-5a-③[wavy] | 同上 |
| `underline` | W-5a-③[underline] | 同上 |

**W-5a-⓪（同色重按 = 删除）不在这张表里**：4B.1 改的是异色分支，同色分支的 toggle-off 语义不变，
那一支在 4B.1 之后**应当保持绿**。W-5a-⓪ 的旁观条断言对 4B.1 的改法有约束力：若顺手把
`getExistingAnnotationIds` 的候选集从「选区命中」放宽成「整章同 type 同 color」，W-5a-⓪ 会红——那是正确
的红，不得靠删旁观条来「修」它。

**为什么用 `seed_notes` 预置一条带字面量 id 的标注，而不是从 UI 建。** §0 第五条纪律：守恒断言的基准必须是
字面量。从 UI 建再读回 id，`after["id"] == before["id"]` 是拿运行期读到的值比运行期读到的值——实现把整条
记录换掉、只要换得一致就照样绿。`W5B_TARGET_ID` 写死，「id 变成了别的」在失败消息里就是一个人能认出的字面量。

------------------------------------------------------------------------------
**为什么只断终态不够：「删了重建」能把七条终态判据一条不落地骗过（2026-09-05 审计 #54）**
------------------------------------------------------------------------------
下面那串终态断言（恰好 1 条、`id` 同、`color` green、`type` / `quote` / `created_at` 原样、
DOM 一个 `<mark>` 只带这个 id）读起来像是把身份守恒说满了，其实它们描述的只是**盘上最后
长什么样**。一个先 `DELETE` 掉那条、再 `POST` 一条**把 `id` 与 `created_at` 原样填回去**的
实现，落盘的终态与原地 `PUT` **逐字节相同**——七条终态判据一条都不会红。

而两者不是同一件事。`DELETE` 与 `POST` 之间有一个窗口，窗口里那条标注**不在库**：进程在
那里崩掉、或者两条请求之间断网，用户就少一条数据；`PUT` 没有这个窗口。契约（前端计划
WI-14）写的是「**原地**更新」，判据就得落在**动作**上，不能只落在**结果**上——「终态一样」
恰恰是这个洞的定义，不是它的反证。

所以本条把改色期间 `/api/notes/` 上的写请求按发出顺序收进一个列表，断四件事：
**收集器真的看见了那次打到目标 id 的 `PUT`**（绊线）、**零次 `DELETE` 零次 `POST`**、
**那个 `PUT` 恰好一次**、**整串写序恰好只有它**。这与 W-5a-③ 的 `EXPECTED_WRITE_SEQUENCE`
（`baseline_1b/test_write_recolor_and_delete.py`，009 审计 F5 补的那条）是同一条纪律的两半：
那边断的是今天这条「先删后建」的路**确实走了哪几步**，这边断的是 4B.1 之后它**一步都不许再走**。

**空转陷阱与绊线的次序。** 「零 `DELETE`、零 `POST`」在收集器**一条都没收到**时平凡成立——
探针没挂上、端点 URL 改了名、点击压根没触发写，三种情况都会让本条以「全绿」的方式什么都没
证明。所以第一句必须是绊线：看不见那次 `PUT` 就红，并把观察到的整串写请求原样贴进消息里。
次序不能反——先断「零 DELETE」的话，一次空收集会先给出一个绿，读失败输出的人要多绕一圈才
发现自己在看一条空转的用例。

------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-05 审计 #54，改动全部已还原）**
------------------------------------------------------------------------------
本模块是 skip 形态，**跑都不跑**，所以「它红过」不能靠跑一遍来证明。做法是：本地**临时**摘掉
模块级 skip，用 `page.add_init_script` 在 `annotations.js` 之前把 `window.fetch` 包一层，
把改色时发出的第一次写请求**替换**成一种合成实现的写序（后续的写吞掉），从而在网线上造出
「若干种实现分别长什么样」。终态那一半由脚手架直接把 `notes.json` 写成「一次成功的原地改色
应有的样子」，**五种模式写的是同一份终态**——于是七条终态判据在每一种模式下都绿，模式之间
唯一的差别只剩写序。这正是审计 #54 要展示的那件事。

| # | 合成实现（网线上出现什么） | 审计前的判据 | 本次加固后的判据 | 红在哪一句 |
|---|---|---|---|---|
| A | **漏洞实现**：`DELETE /…/{target}` → `POST /…/{ch}`，重建时把 `id` 与 `created_at` 原样填回去 | **3 passed** | **3 failed** | 绊线（`puts_to_target`） |
| B | **正确实现**：单次 `PUT /…/{target}`，不删不建 | — | **3 passed** | 无 |
| C | 一次写都不发（探针空转的等价物） | — | failed | 绊线 |
| D | 同一条 `PUT` 发两遍 | — | failed | `EXPECTED_RECOLOR_PUTS` |
| E | `PUT` 目标一次 ＋ `PUT` 另一个 id 一次 | — | failed | 写序等值 |

**A 行是本次审计的全部理由**：同一发子弹下，审计前的版本 `3 passed`，加固后的版本 `3 failed`。
「删了重建」确实能把七条终态判据一条不落地骗过，而它现在骗不过写序。A 的失败输出（逐字）::

    E       AssertionError: 整个改色期间，`/api/notes/` 上一次打到 id='wi17-w5b-target-underline' 的 PUT 都没有。实际观察到的写请求（按发出顺序）：[('DELETE', 'wi17-w5b-target-underline'), ('POST', None)]
    E             出现 DELETE ＋ POST ⇒ 改色被实现成了「删掉再建一条一模一样的」，这正是本段要拦的；
    E       assert []

**C 行是空转陷阱的实证**：`observed == []` 时「零 DELETE、零 POST」两条平凡成立，绊线把它变成
一次红，消息里贴的是 `实际观察到的写请求（按发出顺序）：[]`。D / E 各自证明后两条断言不是
A 的陪衬——D 下绊线与「零 DELETE/POST」都绿，只有计数红；E 下前三条全绿，只有写序等值红。

⚠️ **B 行证明的到底是什么，别读多了。** 它证明的是**写序那四条断言接受一次原地 `PUT`**，
不是「生产代码已经能原地改色」。今天的服务端 `PUT` 只认 `note_text`（见文末那条欠账），
B 的那次 `PUT` 会被 400；终态是脚手架写上去的。所以 B 是「新加的判据不会误伤正确实现」的
证据，不是解 skip 的依据——解 skip 的依据仍然是 #9 ＋ 前端两处异色分支 ＋ 服务端 `color`。

**脚手架为什么不用 `page.route`**（一条踩过的弯路，值得留档）。本仓的定向破坏惯例是
`page.route` 改写响应体（§0.6 欠账 #25），第一版照此写，结果 DELETE 与 POST 被**饿死 8 秒**：
Playwright 同步 API 只有在等它自己的操作时才把浏览器事件泵到本进程，而 `_wait_for_color`
是纯 Python 的 `time.sleep` 循环，期间 route 回调一个都跑不了（`helpers.
wait_for_write_activity_settled` 的 docstring 里写过同一条机制）。改成「浏览器侧 init script
造写序 ＋ Python 侧直接写盘」之后不再有拦截，也就不再依赖事件泵。**生产端不受此限**——那里
没有拦截器，写请求本来就与本进程的事件泵无关。

五次破坏各自单跑、逐次还原；还原后本文件与破坏前**逐字节相同**（`shasum -a256` 相同），
skip 已复位，`acceptance_4b1` 复收 8 条。**`src/` 一个字节都没有改过**（`git diff --quiet -- src/`
无输出）：写序由页面内的 `fetch` 包装造出来，落盘的生产代码一字未动。

（与 `baseline_1b/test_write_recolor_and_delete.py` 那条注记的**区别**：那边写「本文件未跟踪，
`git diff` 对它恒空，别拿它当收据」——本文件已经在 `a7654a2` 上被跟踪了，`git diff` 对它有效。
但还原收据仍以哈希比对为准：`git diff` 只能说明「与 HEAD 的差异是本次加固」，说不了「破坏期间
那五版的痕迹都清掉了」，而哈希比对能。）

**解 skip 的顺序**：修 #9 ⇒ 4B.1 把两处异色分支改成原地改色（PUT，不删不建）⇒ 删本文件 skip 行 ⇒
`-m acceptance_4b1` ⇒ 同一 commit 里按上表处置 W-5a-② / ③。

⚠️ **4B.1 落地时还要动服务端**：今天的 `PUT /api/notes/{book}/{chapter}/{note_id}` 只认
`note_text`（`UpdateAnnotationRequest` 只有这一个字段，`notes_service.update_annotation` 也
只改这一个字段），空的 `note_text` 直接 400。「原地改色」需要它能改 `color`——这是本条 skip
背后的第三件欠账，前两件是 #9 与前端的两处异色分支。
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_INDEX,
    CH0_QUOTE,
    NOTES_ENDPOINT_MARKER,
    NOTES_WAIT_S,
    open_ch0,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_write_activity_settled,
)

pytestmark = [
    pytest.mark.acceptance_4b1,
    pytest.mark.skip(
        reason=(
            "激活阶段 4B.1：『改色保 id』要前端计划 WI-14 把两处异色分支改成原地更新才存在；"
            "且必须先修掉跨波欠账 #9（wavy/underline 异色重按静默丢数据），否则两个参数连一条标注都剩不下。"
            "到期动作：修 #9 → 落地原地改色 → 删本行，并在同一 commit 按 docstring 的配对表处置 W-5a-②/③。"
        )
    ),
]

#: 预置那条的 id / 颜色 / 创建时间全是字面量（§0 第五条纪律）。id 带参数名，三个参数互不相撞。
W5B_TARGET_ID_PREFIX = "wi17-w5b-target-"
SEED_COLOR = "yellow"
SEED_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: 要点的色板与期望落库的颜色。必须与 `SEED_COLOR` 不同，否则本条测的是同色分支（W-5a-⓪）。
SWATCH_TESTID = "rd-anno-color-green"
EXPECTED_COLOR = "green"

#: 改色之后该段文字上应当恰好一条——字面量基准。`>= 1` 对「另加一条」（今天的 marker 分支）也绿。
EXPECTED_COUNT_AFTER_RECOLOR = 1

#: 这次改色在 `/api/notes/` 上应当发出的写请求条数：**恰好一次 PUT**，打在目标 id 上。
#: 字面量（§0 第五条纪律）。`>= 1` 对「PUT 两遍」也绿，而那意味着一次动作发了两次写。
EXPECTED_RECOLOR_PUTS = 1

#: 原地改色**一次都不许出现**的两个动词。它们各自对应一种「换掉整条记录」的实现：
#: `DELETE` ＋ `POST` 是删了重建，单独的 `POST` 是「换支笔再画一遍」（今天的 marker 分支）。
FORBIDDEN_RECOLOR_METHODS = ("DELETE", "POST")

#: 收集器只收这三个动词。`/api/notes/` 上的 `GET` 是 `loadAndRender()` 的重绘噪声——
#: 一次页面加载就有两次（见 `helpers.settle_marks`），收进来只会淹掉真正的写。
NOTES_WRITE_METHODS = ("PUT", "POST", "DELETE")


def _notes_write_of(request: Any) -> Optional[Tuple[str, Optional[str]]]:
    """把一次网络请求归约成 `(动词, 目标 note_id)`；不是标注写请求就返回 `None`。

    `POST /api/notes/{book}/{chapter}` 没有 id 段，归约成 `("POST", None)`——**它照样要被
    记下来**：本条要拦的正是「多出一次没有目标的新建」。`DELETE` / `PUT` 是
    `/api/notes/{book}/{chapter}/{note_id}`，id 从末段取并 `unquote`（`createAnnotation`
    那一侧是 `encodeURIComponent` 写进去的，不解码的话一个含冒号的 id 会比不上）。

    只看 **path**，不看 query 与 fragment：`urlsplit` 天然把它们排除在外，而字符串切分
    会把一个将来可能出现的 `?…` 带进 id 里，表现是「id 对不上」而不是「多了个 query」。
    """
    if NOTES_ENDPOINT_MARKER not in request.url:
        return None
    method = str(request.method).upper()
    if method not in NOTES_WRITE_METHODS:
        return None
    parts = [p for p in urlsplit(request.url).path.split("/") if p]
    # ["api", "notes", book_id, chapter_index] ＋ 可选的 note_id
    note_id = unquote(parts[4]) if len(parts) >= 5 else None
    return method, note_id


@contextmanager
def _capture_notes_writes(page: Page) -> Iterator[List[Tuple[str, Optional[str]]]]:
    """在 `with` 体内收集 `/api/notes/` 上**按发出顺序**排列的写请求 `(动词, note_id)`。

    收 `request` 事件而不是 `response`：请求的**发出**顺序才是调用方的写序，响应回来的先后
    受服务端耗时影响，钉它等于把断言绑在时序抖动上（这条理由与 `baseline_1b/
    test_write_recolor_and_delete.py` 的 `EXPECTED_WRITE_SEQUENCE` 是同一条，009 审计 F5）。

    观察点在**网络层**，不是 `window.fetch`：一个在页面加载时就把 `fetch` 抓在手里、
    自己拆成删＋建的实现绕得过任何 JS 层探针，绕不过这里。

    出了 `with` 就摘监听（`finally`，所以断言抛异常也摘得掉）——留着的话，紧接着那次
    `open_ch0` 刷新会把重绘的请求继续灌进同一个列表，失败消息里就会混进与本次动作无关的条目。
    """
    observed: List[Tuple[str, Optional[str]]] = []

    def _record(request: Any) -> None:
        hit = _notes_write_of(request)
        if hit is not None:
            observed.append(hit)

    page.on("request", _record)
    try:
        yield observed
    finally:
        page.remove_listener("request", _record)


def _wait_for_color(books_dir: Path, book_id: str, note_id: str, color: str) -> Dict[str, Any]:
    """等 `note_id` 那条的 `color` 变成 `color`。等的是被改的那个量，不是条数（条数在原地更新下不变）。"""
    deadline = time.monotonic() + NOTES_WAIT_S
    while time.monotonic() < deadline:
        for r in read_notes(books_dir, book_id):
            if r.get("id") == note_id and r.get("color") == color:
                return r
        time.sleep(0.05)
    final = read_notes(books_dir, book_id)
    current: Optional[Dict[str, Any]] = next((r for r in final if r.get("id") == note_id), None)
    if current is None:
        raise AssertionError(
            f"{NOTES_WAIT_S}s 后 id={note_id!r} 已经不在 notes.json 里——改色被实现成了「删掉再建」"
            f"（或欠账 #9 的丢数据路径）。现存：{[r.get('id') for r in final]}，共 {len(final)} 条"
        )
    raise AssertionError(f"{NOTES_WAIT_S}s 内 {note_id} 的 color 没有变成 {color!r}，当前 {current!r}")


@pytest.mark.parametrize(
    "action_testid,anno_type",
    [
        pytest.param("rd-anno-type-marker", "marker", id="marker"),
        pytest.param("rd-anno-type-wavy", "wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", "underline", id="underline"),
    ],
)
def test_w5b_recolor_keeps_id_and_leaves_exactly_one_annotation(
    page: Page, live_server: str, e2e_books_dir: Path, action_testid: str, anno_type: str
) -> None:
    """W-5b（S5 / L2）：预置 yellow 的 T → 选中同段 → 点 green → 重按 T → 刷新 ⇒ 1 条、id 同、color green、type 同、DOM 一个 `<mark>` 只带这个 id。"""
    target_id = W5B_TARGET_ID_PREFIX + anno_type
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": target_id,
                "chapter_index": CH0_INDEX,
                "type": anno_type,
                "color": SEED_COLOR,
                "quote": CH0_QUOTE,
                "created_at": SEED_CREATED_AT,
            }
        ],
    )
    before = read_notes(e2e_books_dir, BOOK_ID)
    assert [r["id"] for r in before] == [target_id], f"预置没落对：{before}"
    assert before[0]["color"] != EXPECTED_COLOR, "预置色与目标色相同，本条会退化成同色分支（W-5a-⓪）"

    frame = open_ch0(page, live_server, expected_marks=1)
    select_in_frame(frame, CH0_QUOTE)

    # 收集窗口从「点色板」开到「写活动排空」为止，把这次改色发出的写请求一条不漏地收下。
    # `wait_for_write_activity_settled` 而不是 `networkidle`：后者是文档生命周期事件，
    # 对当前文档只到达一次，点击之后立刻调它会 0.001s 返回（理由在它自己的 docstring 里），
    # 一次延迟补发的 POST 就会落在窗口之外——而「有没有补发」正是本段要断的事。
    with _capture_notes_writes(page) as observed:
        page.get_by_test_id(SWATCH_TESTID).click()
        page.get_by_test_id(action_testid).click()
        _wait_for_color(e2e_books_dir, BOOK_ID, target_id, EXPECTED_COLOR)
        wait_for_write_activity_settled(page)

    # ---- 动作侧：这次改色必须是一次原地 PUT，不是「删了重建」（审计 #54）------------------
    # 顺序是刻意的：**绊线先说话**。下面「零 DELETE、零 POST」在 `observed` 为空时平凡成立，
    # 先断它等于给一次「什么都没收到」发一个绿。所以第一句断的是收集器真的看见了那次 PUT。
    puts_to_target = [m for m, note_id in observed if m == "PUT" and note_id == target_id]
    assert puts_to_target, (
        f"整个改色期间，`{NOTES_ENDPOINT_MARKER}` 上一次打到 id={target_id!r} 的 PUT 都没有。"
        f"实际观察到的写请求（按发出顺序）：{observed}\n"
        "    出现 DELETE ＋ POST ⇒ 改色被实现成了「删掉再建一条一模一样的」，这正是本段要拦的；\n"
        "    整个列表为空 ⇒ 收集器什么都没收到（点击没触发写？端点 URL 改名了？），"
        "下面那两条「零 DELETE / 零 POST」此刻会平凡成立，别把它们的绿当成证据"
    )
    forbidden = [(m, note_id) for m, note_id in observed if m in FORBIDDEN_RECOLOR_METHODS]
    assert forbidden == [], (
        f"改色 {anno_type} 期间发出了 {len(forbidden)} 次 {'/'.join(FORBIDDEN_RECOLOR_METHODS)}："
        f"{forbidden}（完整写序：{observed}）。\n"
        "    契约（前端计划 WI-14）要的是**原地更新**：DELETE ＋ POST 之间有一个那条标注不在库的"
        "窗口，崩在窗口里用户就少一条数据，而终态判据看不见这个窗口——它只看盘上最后长什么样"
    )
    assert len(puts_to_target) == EXPECTED_RECOLOR_PUTS, (
        f"改色 {anno_type} 对 id={target_id!r} 发了 {len(puts_to_target)} 次 PUT，"
        f"期望恰好 {EXPECTED_RECOLOR_PUTS} 次（完整写序：{observed}）。"
        "一次动作发两次写 ⇒ 去抖或事件绑定重复了"
    )
    assert observed == [("PUT", target_id)], (
        f"改色期间 `{NOTES_ENDPOINT_MARKER}` 上的写序是 {observed}，"
        f"期望恰好 {[('PUT', target_id)]}。"
        "多出的条目里若有打到**别的 id** 的 PUT，说明这次改色顺手动了不该动的记录——"
        "上面三条各自都放它过去（它既不是 DELETE/POST，也不打在目标 id 上）"
    )

    # ---- 刷新到确定的终态再断（§0 第四条纪律：轮询到期望值不是终态）----------------------
    frame = open_ch0(page, live_server, expected_marks=EXPECTED_COUNT_AFTER_RECOLOR)
    after: List[Dict[str, Any]] = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == EXPECTED_COUNT_AFTER_RECOLOR, (
        f"改色 {anno_type} 之后该章应恰好 {EXPECTED_COUNT_AFTER_RECOLOR} 条，实际 {len(after)} 条：{after}\n"
        "    2 条 ⇒ 走了「换支笔再画一遍」（今天的 marker 分支，W-5a-②）；0 条 ⇒ 欠账 #9 的丢数据路径（W-5a-③）"
    )
    record = after[0]
    assert record["id"] == target_id, (
        f"改色之后 id 变了：{record['id']!r} != {target_id!r}——改色被实现成了「删了重建」，这正是本条要拦的"
    )
    assert record["color"] == EXPECTED_COLOR, f"落库的 color 是 {record['color']!r}，不是所点的 {EXPECTED_COLOR!r}"
    assert record["type"] == anno_type, f"改色顺手把 type 从 {anno_type!r} 改成了 {record['type']!r}"
    assert record["quote"] == CH0_QUOTE, f"改色顺手把 quote 从 {CH0_QUOTE!r} 改成了 {record['quote']!r}"
    assert record["created_at"] == SEED_CREATED_AT, (
        f"created_at 从 {SEED_CREATED_AT!r} 变成了 {record['created_at']!r}——原地更新不该动创建时间"
    )

    # ---- DOM 侧：该段文字上恰好一个 `<mark>`，且只携带这一个 id ----------------------------
    span = frame.get_by_test_id("rd-anno-span")
    expect(span).to_have_count(EXPECTED_COUNT_AFTER_RECOLOR)
    expect(span).to_have_text(CH0_QUOTE)
    raw_ids = span.evaluate("(el) => el.dataset.annotationIds")
    assert json.loads(raw_ids) == [target_id], (
        f"<mark> 携带的 id 列表是 {raw_ids}，期望恰好 [{target_id!r}]——两条重合时会合并进同一个 <mark>，靠计数看不出来"
    )
