"""WI-6 —— W-5a 四岔特征化 ＋ W-6 删除（含反向断言）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-6（最高权威）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §3（W-5a / W-6）、
§0.5（`baseline-1b` 对 K1 / K6 / W-5 的现状特征化）、§0 六条写作纪律、
§1（iframe 内建选区的标准路径）、§0.6（本模块是 Wave 2 的三份产出之一）。

**这五组用例断的是「id 集合的代数」**——每一次操作对**该段文字上**的标注 id 集合的作用
都是一个确定的集合运算，且刷新后仍成立。律的定义域是**选区命中的那些条目**，不是整章的
条目，所以每条运算都写成对**全章集合**的作用，把没被选中的条目显式地放进等式里：

    W-5a-⓪  同色重按（marker / wavy / underline 各一次）  S'_章 = S_章 \\ S_选区
    W-5a-①  点色板                                        S'_章 = S_章（恒等）
    W-5a-②  异色重按 marker                               S_选区 ⊂ S'_选区，|S'| = |S| + 1
    W-5a-③  异色重按 wavy / underline                     S_选区 ∩ S'_选区 = ∅，**|S'| = 0**
    W-6     删除                                          S'_章 = S_章 \\ {target}

**本模块断的一律是今天的行为，不是 4B.1 之后的行为**（任务书 §0.5 的裁定）。
`baseline_1b` 里**不得出现任何「改色后 id 不变」的断言**——那是 `acceptance_4b1` 的
W-5b，写进 1b 就是把一条注定红的用例混进门槛。四支各自的 4B.1 配对关系写在各自的
docstring 里。

依据的方法名（**不写行号**，任务书的引用规则）：`setSelectedColor`、
`toggleMarkerAnnotation` → `getExistingMarkerIds` → `getExistingAnnotationIds`、
`toggleAnnotation`、`deleteCurrentAnnotation` → `deleteAnnotations`。

------------------------------------------------------------------------------
⚠️ **W-5a-③ 的期望值与矩阵原文不一致，本模块按实测写，理由在这里**
------------------------------------------------------------------------------
矩阵与任务书 §3 都把 W-5a-③ 的今日行为记作「**先删后建**，id 变了，`|S'| == 1`、
`color == "green"`」。**实测不是这样。** 今天的真实行为是「**删成功、建失败**」：

    DELETE /api/notes/{book}/{chapter}/{oldId}  → 204
    POST   /api/notes/{book}/{chapter}          → **400**，payload 的 quote 是 **空串**

净结果 `|S'| == 0` ——那条 wavy / underline **被销毁且没有替代品**。成因是
`toggleAnnotation` 的异色分支里 `deleteAnnotations(anyIds)` 会 `await` 一次
`loadAndRender()`，而 `render()` 首先 `clearExistingAnnotationMarks()` 拆掉 `<mark>`
并 `normalize()` 合并文本节点；`this.currentRange` 的两个端点在这次合并里塌到同一个
偏移上，紧接着跑的 `createAnnotation` 于是把 `quote` 算成空串，服务端拒收。
marker 那一支（W-5a-②）不经过这条路——它不先删，所以 `currentRange` 是好的。

「删成功、建失败」这个**结果**是确定的：只要选区还活着，异色分支必然走这条路。
但**能不能活着走到这里**曾经是竞态，当时没看出来。2026-09-03 实测本模块约四成概率红在
「一次 DELETE 都没发」上，根因不在改色分支，而在一次页面加载会跑**两遍**
`loadAndRender()`，第二遍的 `normalize()` 把测试刚装上的选区就地折叠——详见
`helpers.settle_marks` 的 docstring（欠账 #16 的等待纪律唯一定义处；本模块原先的 `_open_ch0`
已于 Wave 5 上收为 `helpers.open_ch0`，欠账 #25）。原先那句「实测 10/10 稳定，不是竞态」
写过头了：10/10 是真的，但它测的是「赢下那场加载竞态之后」的稳定性。`open_ch0` 现在等到
网络静默、两遍重绘都跑完才返回，
这条路才真的确定。

**这是一个真实的生产缺陷（用户数据丢失），不是本模块的构造问题。** 本模块按「特征化今天
的行为」的定则如实断言它，并把 DELETE 204 / POST 400 / `quote == ""` 三件事一起断死——
一旦有人修好这条路（无论是修 stale range 还是 4B.1 的原地改色），本条会红，而**那是正确
的红**。计划文档的 W-5a-③ 期望值需要按本条回写，这一条已在 WI-6 的回报里点名。

------------------------------------------------------------------------------
**为什么每一步之间都要刷新，且刷新之后必须先等 `<mark>` 数量到位再建选区**
------------------------------------------------------------------------------
两个理由，第二个是实测逼出来的：

1. `getAnnotationMetaForRange` 靠 `range.intersectsNode(mark)` 找已有标注，它需要 DOM
   里真的存在那个 `<mark>`。不刷新就依赖创建后的即时重绘时机，是一个去抖竞态。
2. **更要紧的**：`loadAndRender()` 的重绘会拆 `<mark>` 并 `normalize()` 文本节点，
   任何早于它建好的选区都会在那一刻失效（上面 W-5a-③ 的成因就是这个）。所以刷新之后
   必须先 `expect(rd-anno-span).to_have_count(n)` 等重绘落定，**再**建选区。这不是
   sleep，等的是一个可观测的确定条件；等不到就红。

------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录，2026-09-03，五处全部已还原）**
------------------------------------------------------------------------------
本模块五组用例全是特征化用例——被测行为上线数月，**红不可得**。§0 明令不得靠破坏生产代码
去伪造一次红，所以下面每一处破坏都打在**用例自己的期望值**上，每次只动一个判据：动一个
判据而红，证明的是「这一条断言咬住的是它自己那件事」；把整块挖空只能证明断言不空转。

| # | 破坏点（用例自己的期望值，每次只动一处） | 失败输出（逐字，id 已缩写） | 它证明了哪条判据不是摆设 |
|---|---|---|---|
| D1 | W-5a-⓪ 断言里的 `== [bystander_before["id"]]` 改成 `== [target["id"]]` | `AssertionError: ... assert ['80c4fb36-…'] == ['4a4ffa30-…']` ／ `At index 0 diff: '80c4fb36-…' != '4a4ffa30-…'`（marker / wavy / underline **三个参数各红一次**） | 差集律的「删对了哪一条」那一半——留下的必须是旁观条，不是目标条 |
| D2 | W-6 的 `assert len(after) == EXPECTED_AFTER_DELETE` 改成 `== EXPECTED_BEFORE_DELETE` | `AssertionError: 删掉一条之后 notes.json 应当恰好剩 2 条（删前 2 条），实际 1 条：[{'id': 'wi6-w6-bystander-marker', …}]` ／ `assert 1 == 2` | 基数判据真的在数数（2 → 1），不是 `> 0` 那种对「删光」也绿的弱断言 |
| D3 | W-5a-② 的 `== {first_id, green_id}` 改成 `== {first_id}` | `AssertionError: 合并后的 <mark> 携带的 id 集合是 {'349464b7-…', '84c2b431-…'}，期望 …` ／ `Extra items in the left set: '349464b7-…'` | 「两条并存、且都渲染进同一个 `<mark>`」的 DOM 侧证据——磁盘对了而渲染丢了必须红 |
| D4 | W-5a-③ 的 `assert len(after) == EXPECTED_AFTER_RECOLOR_TOGGLE` 改成 `== 1`（即矩阵原文的期望值） | `AssertionError: 异色重按 wavy 之后 notes.json 应当剩 1 条，实际 0 条：[]` ／ `assert 0 == 1`（underline 同） | 「删成功、建失败」这条特征化结论本身——**这一次红正是矩阵原期望值会得到的结果**，是本模块偏离矩阵的实证 |
| D5 | W-5a-① 的 `changed_ids=frozenset()` 改成 `changed_ids={after[0]["id"]}` | `AssertionError: 没有旁观条可断：before 里的 id 是 ['ab748640-…']，而 changed_ids 是 ['ab748640-…']——两者相减为空。这次调用什么都没断到（预置漏了旁观条？changed_ids 写宽了？）` | 恒等律的守卫不空转：`changed_ids` 一旦放宽到把唯一那条也算进去，`assert_bystanders_unchanged` 自己就拒收 |

五次破坏各自单跑、逐次还原；还原后本文件与破坏前**逐字节相同**（`diff` 无输出），
`git diff --stat -- src tests scripts` 与 `git status --short -- src` 均无输出，
全模块复跑 8 passed。**生产代码（`src/`）在本模块落地全过程中一个字节都没有改过**——
§0 明令不得靠改实现去伪造一次红，上面五次全部打在用例自己的期望值上。

------------------------------------------------------------------------------
**【交叉指针】W-5a-⓪ 的旁观条与 WI-5 的 W-7 是同一个构造，两条都不是冗余**
------------------------------------------------------------------------------
见下方 `test_w5a0_same_color_repress_removes_only_the_selected_one` 的 docstring；
它按用例号 ＋ WI 号点名 `test_w7_editing_a_note_changes_its_body_and_nothing_else`
（W-7 / WI-5），兑付任务书 §0.6 跨波欠账 #1。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from playwright.sync_api import Page, Response, expect

from conftest import BOOK_ID  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_QUOTE,
    assert_bystanders_unchanged,
    open_ch0,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b

#: 全模块只用第 0 章。`<h1>One</h1><p>Alpha prose.</p>`——两段文字**不相邻不重叠**，
#: 所以 `AnnotationRenderer.render()` 的分段会给它们各出一个 `<mark>`。重叠的话
#: 「旁观条的高亮还在」会退化成「目标条的高亮还在」。
CH0_INDEX = 0

#: 旁观条落在 `<h1>One</h1>` 上，与目标条的 `Alpha prose`（在 `<p>` 里）互不相干。
#: 与 WI-5 的 W-7 同构，见模块 docstring 的交叉指针。
BYSTANDER_QUOTE = "One"

#: 色板上要点的那个颜色。**它必须与默认色不同**——相同的话 W-5a-②/③ 测的就变成同色分支
#: （即 W-5a-⓪）了。写成常量而不是三处字面量，是为了让「默认色改了」只需要改一处。
SWATCH_COLOR = "green"
SWATCH_TESTID = "rd-anno-color-green"

#: W-6 的两条预置。id 与 created_at 全写死（§0 第五条纪律）：守恒律断的正是它们没被动过，
#: 让 `seed_notes` 生成随机 uuid，断言就只能拿运行期读到的值去比运行期读到的值。
W6_TARGET_ID = "wi6-w6-target-marker"
W6_BYSTANDER_ID = "wi6-w6-bystander-marker"

#: 删除前后的条数基准，**字面量**（§0 第五条纪律）。`> 0` 这类弱断言对「把整章删光」
#: 与「一条都没删」都绿。
EXPECTED_BEFORE_DELETE = 2
EXPECTED_AFTER_DELETE = 1

#: W-5a-③ 的终态条数。**0 而不是矩阵原文的 1**——理由见模块 docstring 那一整节。
EXPECTED_AFTER_RECOLOR_TOGGLE = 0

#: 异色重按 wavy / underline 时那次注定失败的 POST 的状态码与 payload 里的 quote。
#: 断死它们是为了给「删了没建成」这个结论一个**机制层面的**判据：将来若有人把 stale
#: range 修好，红的会是这两条，且失败消息直接说清楚变的是哪一环。
EXPECTED_FAILED_POST_STATUS = 400
EXPECTED_FAILED_POST_QUOTE = ""

#: `notes_service.save_annotations` 写的顶层**对象**的键。任务书 §3 的勘误行点名过：
#: 「删完后仍是合法 JSON **数组**」按字面实现会稳定假红——盘上是对象，不是数组。
NOTES_TOPLEVEL_KEYS = {"schema_version", "book_id", "annotations"}


# ---------------------------------------------------------------------------
# 本模块内部的小工具。共享面上的东西一律走 `helpers.py`，这三个不共享：
# 它们各自只被本模块用到，抽出去反而多一处要同步演化的定义。
# ---------------------------------------------------------------------------


def _ids(records: List[Dict[str, Any]]) -> List[str]:
    return [str(r["id"]) for r in records]


def _pick(records: List[Dict[str, Any]], quote: str) -> Dict[str, Any]:
    """按 quote 挑出**恰好一条**。挑不出唯一的一条就当场抛，不往下断。"""
    hits = [r for r in records if r.get("quote") == quote]
    if len(hits) != 1:
        raise AssertionError(
            f"quote={quote!r} 的记录有 {len(hits)} 条（要求恰好 1 条）。完整列表：{records}"
        )
    return hits[0]


def _notes_payload(books_dir: Path, book_id: str) -> Dict[str, Any]:
    """读回 `notes.json` 的**顶层对象原样**，不经过 `helpers.read_notes` 的解包。

    `read_notes` 只返回 `annotations` 列表，看不见文件形状；而 W-6 要断的正是
    「删完之后文件仍是那个对象，不是被删成空文件 / 裸数组 / 不存在」。
    """
    path = books_dir / book_id / "notes.json"
    assert path.exists(), f"notes.json 不见了：{path}（删除路径把整个文件删掉了？）"
    raw = path.read_text(encoding="utf-8")
    assert raw.strip(), f"notes.json 是空文件：{path!s}"
    return json.loads(raw)


def _is_notes_post(response: Response) -> bool:
    return response.request.method == "POST" and "/api/notes/" in response.url


# ---------------------------------------------------------------------------
# W-5a-⓪ 同色重按 = 差集删除
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_testid",
    [
        pytest.param("rd-anno-type-marker", id="marker"),
        pytest.param("rd-anno-type-wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", id="underline"),
    ],
)
def test_w5a0_same_color_repress_removes_only_the_selected_one(
    page: Page, live_server: str, e2e_books_dir: Path, action_testid: str
) -> None:
    """W-5a-⓪（S5，**差集律** `S'_章 = S_章 \\ S_选区`）：同色重按只撤销选区上的那一条。

    走的是 `toggleMarkerAnnotation` 里 `getExistingMarkerIds(selected)` 非空的那一支
    （marker），以及 `toggleAnnotation` 里 `getExistingAnnotationIds(type, color)` 非空的
    那一支（wavy / underline）。**两份独立实现**，所以参数化 ×3 而不是挑一个代表。

    **它的判别力全部来自「同章还剩下什么」这一半。** 只 seed 一条标注时，「章内所有同
    (type, color) 的条目全删」与「只删选区命中的那一条」**是同一个函数**——两个语义完全
    不同的实现在那个构造上不可区分。而 4B.2 的一个自然重构恰好会把两者分开：
    `getExistingAnnotationIds(type, color)` 若不再查 DOM、改为按 type + color 过滤整章的
    `loadedAnnotations`，`currentRange` 就完全不参与，用户在第 9 段重按 Marker 会**静默
    删掉第 1–8 段的同色标注**。差集形式把「没被选中的那些必须一字不动」写进了律本身。

    三条构造理由，缺一条本用例就会稳定假红或失去判别力：

    * **全程不点色板。** 每次刷新都会把 `selectedColor` 复位为默认色；中途手动点一次色板
      去「凑」颜色，一旦默认色与所点色不同就落进**异色**分支，本条测的就变成 W-5a-②/③ 了。
      不碰 = 三次创建/重按必然同色 = 必然走命中的那一支。
    * **颜色与 type 从落库记录里读、并在动作前断两条相等，不写字面量 `"yellow"`。**
      默认色是实现细节，写死它会让一次无关的默认值调整把本条打红；而**不断它相等**则会让
      本条在一个「两条恰好不同色」的世界里悄悄退化回「只 seed 一条」的旧形态。
      落不进同一 (type, color) 时以 `pytest.fail` 立刻停，**不是 skip**——默认色是确定的，
      落不进说明实现或语料变了，那是要修的事。
    * **每一步之间都刷新，且刷新后先等 `<mark>` 数量到位再建选区**（理由见模块 docstring）。

    **【4B.1 配对】本条是四支里唯一在 4B.1 之后仍应保持绿的一支。** 4B.1 改的是**异色**
    分支（W-5b「改色不删不建，id 不变」），同色分支的 toggle-off 语义不变。若 4B.1 顺手把
    候选集从「选区命中」放宽成「整章同 type 同 color」，本条会红——**那是正确的红**，
    修法是改回实现，不是改本条。

    **【交叉指针 · 兑付任务书 §0.6 跨波欠账 #1】本条的旁观条与 WI-5 的
    `test_w7_editing_a_note_changes_its_body_and_nothing_else`（W-7）是同一个构造
    （`quote="One"`、同章、与目标条不相邻不重叠），两条都不是冗余：**

      * **W-7 守服务端**：`PUT /api/notes/{book}/{chapter}/{id}` →
        `notes_service.update_annotation`，那条链是 load 整章 → 改一条 → 整章回写；
        回写少带一条，同章别的标注就没了，而 HTTP 200 照样返回。
      * **本条守客户端**：`toggleMarkerAnnotation` / `toggleAnnotation` →
        `getExistingAnnotationIds` 的**候选集**，退化方向是「选区命中」被放宽。

    把 W-7 删了，服务端整章回写漏条没人管；把本条删了，客户端候选集放宽没人管。
    两条各自能红在对方绿的地方。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    # --- 1. 在 "Alpha prose" 上建目标条 ---------------------------------------
    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(action_testid).click()
    wait_for_notes(e2e_books_dir, BOOK_ID, 1)

    # --- 2. 刷新 → 在 "One" 上用**同一个 action、同一个默认色**再建一条旁观条 -----
    frame = open_ch0(page, live_server, expected_marks=1)
    select_in_frame(frame, BYSTANDER_QUOTE)
    page.get_by_test_id(action_testid).click()
    wait_for_notes(e2e_books_dir, BOOK_ID, 2)

    # --- 3. 刷新 → 读出两条，断前置条件 ---------------------------------------
    frame = open_ch0(page, live_server, expected_marks=2)
    before = read_notes(e2e_books_dir, BOOK_ID)
    assert len(before) == 2, f"toggle 触发之前同章应当恰好 2 条，实际 {len(before)} 条：{before}"
    target = _pick(before, CH0_QUOTE)
    bystander = _pick(before, BYSTANDER_QUOTE)

    # --- 4. 前置条件：两条必须同 type 同 color，否则本条测的不是那个缺陷 --------
    if target["type"] != bystander["type"] or target["color"] != bystander["color"]:
        pytest.fail(
            "本条要求 toggle 触发的那一刻同章存在**两条同 type 同 color** 的标注，"
            "否则「按整章 type+color 过滤后删光」与「只删选区命中的」不可区分。"
            f"实际 target=({target['type']!r}, {target['color']!r})、"
            f"bystander=({bystander['type']!r}, {bystander['color']!r})。"
            "全程没碰色板，所以两条本应同色——落不进同一 (type, color) 说明"
            "`selectedColor` 的默认值或复位时机变了。"
        )
    bystander_before = dict(bystander)

    # --- 5. 回到 "Alpha prose" 上重按同一个 action（仍不碰色板）----------------
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(action_testid).click()
    wait_for_notes(e2e_books_dir, BOOK_ID, 1)

    # --- 断言 ------------------------------------------------------------------
    frame = open_ch0(page, live_server, expected_marks=1)
    after = read_notes(e2e_books_dir, BOOK_ID)

    # (1) 列表等值：既断了 target 消失，也断了 bystander 还在、还只有它一条、顺序没乱
    assert _ids(after) == [bystander_before["id"]], (
        f"同色重按之后剩下的应当**只**有旁观条 {[bystander_before['id']]}，"
        f"实际是 {_ids(after)}。\n"
        "  多一条 ⇒ 重按变成了「再建一条」；少一条 ⇒ 候选集被放宽成整章过滤，"
        "把没选中的旁观条也删了；一条没少 ⇒ 同色分支整个失效。\n"
        f"  完整列表：{after}"
    )

    # (2) 整字典逐字段相等。挑字段断会漏掉下一个被加进 schema 的字段（`Annotation`
    #     今天 13 个字段，012 还要动它），也会放过「删了再按新 id 重建旁观条」。
    assert after[0] == bystander_before, (
        f"旁观条被动过了。\n  动作前：{bystander_before}\n  动作后：{after[0]}"
    )

    # (3) 走共用 helper 再断一次守恒。就地写 `assert a == b` 在语义上等价，但**是 grep
    #     不到的**——`tests/unit/test_e2e_bystander_discipline.py` 只认得这个共用的名字
    #     （§0 第六条纪律：静默失效的规则必须机器可查）。
    assert_bystanders_unchanged(before, after, changed_ids={target["id"]})

    # (4) DOM 侧的独立证据：磁盘对了而渲染丢了、或反过来，都必须红
    spans = frame.get_by_test_id("rd-anno-span")
    expect(spans).to_have_count(1)
    expect(spans).to_have_text(BYSTANDER_QUOTE)

    # (5) 文件形状仍然合法
    payload = _notes_payload(e2e_books_dir, BOOK_ID)
    assert NOTES_TOPLEVEL_KEYS <= set(payload), (
        f"notes.json 的顶层键缺了 {NOTES_TOPLEVEL_KEYS - set(payload)}：{payload}"
    )
    assert isinstance(payload["annotations"], list), (
        f"notes.json 的 annotations 不是列表：{payload['annotations']!r}"
    )


# ---------------------------------------------------------------------------
# W-5a-① 点色板 = 恒等
# ---------------------------------------------------------------------------


def test_w5a1_color_swatch_click_changes_no_existing_annotation(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-5a-①（S5，**恒等律** `S'_章 = S_章`）：点色板只改「下一次用什么颜色」。

    依据的方法名是 `setSelectedColor`——它做的全部事情是记住颜色并 `syncSelectedColor()`
    刷一下按钮的选中态，**一条已有标注都不碰**。本条把这句话变成可失败的：建一条标注 →
    重新选中同一段 → 点绿色色板 → **不点任何 action** → 刷新 → 整条记录逐字段原样。

    **为什么断的是 id 集合等值 + 整字典等值，而不是「存在一条 yellow」。**
    「`notes.json` 里存在一条默认色的标注」会放过「顺手多写了一条 green」；
    只断条数会放过「把那条原地改成了 green」。两条判据合起来才把这两种偏差都杀掉。

    **为什么不写死默认色 `"yellow"`。** 默认色是实现细节（同 W-5a-⓪ 的构造理由）。
    这里承重的字面量是**点下去的那个色** `SWATCH_COLOR`：断「那条的 color 不是我刚点的
    那个」，比断「它还是 yellow」更贴近本条要证的事，且不随默认值调整而假红。

    **【4B.1 配对】本条在 4B.1 之后会红，且那是预期的。** 4B.1 要给色板加上「立即改已有
    标注颜色」的行为（前端计划 WI-14 / 本文的 W-5b）。届时本条随 `acceptance_4b1` 的
    W-5b 一起改判——同一个 commit 里处理，不要单独修其中一边。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()
    before = wait_for_notes(e2e_books_dir, BOOK_ID, 1)
    record_before = dict(before[0])

    # 刷新之后再点色板：`selectedColor` 此刻是复位后的默认色，点绿色是一次**真的换色**。
    frame = open_ch0(page, live_server, expected_marks=1)
    assert record_before["color"] != SWATCH_COLOR, (
        f"预置那条的颜色本来就是 {SWATCH_COLOR!r}，点同色色板不构成一次换色，"
        f"本条会退化成一句恒真。完整条目：{record_before}"
    )

    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(SWATCH_TESTID).click()

    # 色板按钮的选中态换了，才说明 `setSelectedColor` 真的被调用过——否则下面那句
    # 「什么都没变」对「点击根本没绑上」也绿。ARIA 定位，不经过选择器字符串。
    expect(page.get_by_test_id(SWATCH_TESTID)).to_have_class(
        "anno-color is-selected"  # lint-e2e-selectors: allow —— 这是 to_have_class 的期望值，不是选择器；`is-selected` 由 syncSelectedColor 挂上
    )

    # **不点任何 action**，直接刷新。
    frame = open_ch0(page, live_server, expected_marks=1)
    after = read_notes(e2e_books_dir, BOOK_ID)

    assert _ids(after) == _ids(before), (
        f"点一次色板之后 id 集合变了：{_ids(before)} → {_ids(after)}。"
        "色板今天只调 `setSelectedColor`，不该产生或删除任何标注"
    )
    assert len(after) == 1, f"点色板之后不是恰好 1 条，而是 {len(after)} 条：{after}"
    assert after[0]["color"] != SWATCH_COLOR, (
        f"点了 {SWATCH_COLOR!r} 色板之后，已有标注的颜色变成了 {after[0]['color']!r}。"
        "这是 4B.1 的期望行为（W-5b），今天不该发生；若 4B.1 已落地，本条应随 W-5b 一起改判"
    )
    # 整字典等值走共用 helper：`changed_ids` 是空集，因为本次动作**什么都不该改**。
    assert_bystanders_unchanged(before, after, changed_ids=frozenset())


# ---------------------------------------------------------------------------
# W-5a-② 异色重按 marker = 真超集
# ---------------------------------------------------------------------------


def test_w5a2_recolor_then_repress_marker_adds_a_second_one(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-5a-②（S5，**真超集律** `S ⊂ S'`、`|S'| = |S| + 1`）：旧黄条保留，另加一条绿的。

    依据的方法名是 `toggleMarkerAnnotation`：它调 `getExistingMarkerIds(selected)`，而后者
    **按颜色过滤**。同一段文字上已有的是默认色那条，按下绿色之后过滤结果为空 ⇒ 走创建分支
    ⇒ 两条并存，id 各自独立。**「改色」今天不是一个操作**，它是「换一支笔，再画一遍」。

    **两条完全重合的标注在 DOM 上合并成一个 `<mark>`。** `render()` 的文本路径
    （`buildSegments` → `applySegments`）按边界切段，两条同起同止 ⇒ 一段 ⇒ 一个 `<mark>`，
    其 `data-annotation-ids` 携带两个 id。所以 DOM 侧的判据是「恰好一个 `<mark>`，
    它携带的 id 集合等于两条的 id 集合」，不是「两个 `<mark>`」。

    **为什么断 id 集合而不是「有两条」。** `|S'| == 2` 对「删了旧的、建了两条新的」也绿；
    `S ⊂ S'` 把「旧那条还是原来那条」钉住。两个判据都要。

    **【4B.1 配对（Gap 10）】本条与 `acceptance_4b1` 的 W-5b[marker] 是同一操作的相反
    断言。** 4B.1 落地的**同一个 commit** 里：解开 W-5b[marker] 的 skip，并把本条改判/转出。
    单边记录迟早漂移，所以这条配对关系同时写在两边的 docstring 里。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()
    before = wait_for_notes(e2e_books_dir, BOOK_ID, 1)
    first_id = str(before[0]["id"])

    frame = open_ch0(page, live_server, expected_marks=1)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(SWATCH_TESTID).click()
    page.get_by_test_id("rd-anno-type-marker").click()
    wait_for_notes(e2e_books_dir, BOOK_ID, 2)

    frame = open_ch0(page, live_server, expected_marks=1)  # 两条重合 ⇒ 合并成一个 `<mark>`
    after = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == 2, f"异色重按 marker 之后不是 2 条，而是 {len(after)} 条：{after}"
    assert first_id in _ids(after), (
        f"旧那条（id={first_id!r}）不见了。今天的 marker 异色分支是「另加一条」，"
        f"不是「先删后建」——后者是 4B.1 之后 wavy/underline 那一支的形状。现存：{_ids(after)}"
    )
    new_records = [r for r in after if str(r["id"]) != first_id]
    assert len(new_records) == 1, f"新增的不是恰好一条：{new_records}"
    green_id = str(new_records[0]["id"])

    colors = sorted(r["color"] for r in after)
    assert colors == sorted([before[0]["color"], SWATCH_COLOR]), (
        f"两条的颜色分布是 {colors}，期望 {sorted([before[0]['color'], SWATCH_COLOR])}——"
        "旧那条的颜色应当原样，新那条应当是刚点的色板色"
    )
    assert {r["quote"] for r in after} == {CH0_QUOTE}, (
        f"两条的 quote 不都是 {CH0_QUOTE!r}：{[r['quote'] for r in after]}"
    )
    assert {r["type"] for r in after} == {"marker"}, (
        f"两条的 type 不都是 marker：{[r['type'] for r in after]}"
    )

    # 旧那条逐字段原样：本次动作只该新增，不该动它。
    assert_bystanders_unchanged(before, after, changed_ids={green_id})

    # DOM 侧：合并后的那一个 `<mark>` 同时携带两个 id。
    span = frame.get_by_test_id("rd-anno-span")
    expect(span).to_have_text(CH0_QUOTE)
    # `dataset.annotationIds` 而不是 `getAttribute("data-annotation-ids")`：后者的名字在
    # 选择器 lint 的扫描清单里，会被当成一个选择器实参扫到（属性名不是选择器，那是误报）。
    raw_ids = span.evaluate("(el) => el.dataset.annotationIds")
    assert set(json.loads(raw_ids)) == {first_id, green_id}, (
        f"合并后的 <mark> 携带的 id 集合是 {set(json.loads(raw_ids))}，"
        f"期望 {{{first_id!r}, {green_id!r}}}——两条完全重合的标注应当渲染成同一个 "
        "`<mark>` 且带上两个 id"
    )


# ---------------------------------------------------------------------------
# W-5a-③ 异色重按 wavy / underline = 删了，且没建成
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_testid",
    [
        pytest.param("rd-anno-type-wavy", id="wavy"),
        pytest.param("rd-anno-type-underline", id="underline"),
    ],
)
def test_w5a3_recolor_then_repress_destroys_without_replacing(
    page: Page, live_server: str, e2e_books_dir: Path, action_testid: str
) -> None:
    """W-5a-③（S5，**不相交律** `S ∩ S' = ∅`）：异色重按把旧条删掉，**新条没建成**。

    依据的方法名是 `toggleAnnotation`：同 type 异色时它先 `deleteAnnotations(anyIds)`
    删掉该 type 的旧条，再 `createAnnotation` 建新的。`toggleMarkerAnnotation`（W-5a-②）
    是另一份独立实现，没有这个「先删」的动作——两条用例的差别只有一个集合关系，
    合并成「颜色变成 green 了」的话两支实现都能绿，合并即失去信息。

    ------------------------------------------------------------------------
    ⚠️ **本条的期望值与矩阵原文不一致，按实测写。完整理由在模块 docstring。**
    ------------------------------------------------------------------------
    矩阵与任务书都记作「先删后建，`|S'| == 1`、`color == "green"`、id 变了」。
    **实测是「删成功、建失败」**：`deleteAnnotations` 里 `await loadAndRender()` 的重绘
    `clearExistingAnnotationMarks()` + `normalize()` 把 `currentRange` 的两个端点塌到同一
    偏移，紧接着的 `createAnnotation` 于是把 `quote` 算成空串，`POST` 被服务端 400 拒收。
    净结果 `|S'| == 0`——那条标注**被销毁且没有替代品**，是一次真实的用户数据丢失。
    这个**结果**是确定的（选区活着就必然走这条路），但 2026-09-03 发现「能不能活着走到
    这里」曾是竞态：加载期第二遍 `loadAndRender()` 会折叠测试装上的选区，那种情况下一次
    DELETE 都不发。原先那句「实测 10/10 稳定，不是竞态」测的是赢下那场竞态之后的稳定性。
    现在由 `helpers.open_ch0` 等网络静默兜住，见 `helpers.settle_marks` 的 docstring。

    所以本条断三件事，第三件是机制层面的：

      1. `S ∩ S' == ∅`（矩阵的律，今天以 `S' == ∅` 的形式平凡成立）；
      2. `len(S') == 0`（**字面量基准**，写 1 会稳定假红）；
      3. 那次替代性 POST 确实发生过、确实带着空 `quote`、确实被 400 拒收。

    第 3 条不是装饰：只断「剩 0 条」的话，一个「异色重按 = 纯删除，压根不试图新建」的
    实现也全绿，而那是**另一种**语义。断死 DELETE→POST(400) 这个序列，本条才真的在描述
    今天这条路走过了哪几步。

    **【4B.1 配对（Gap 10）】本条两个参数在 4B.1 之后都会变红**，与
    `acceptance_4b1` 的 W-5b[wavy] / W-5b[underline] 逐参数配对，同一 commit 内一并处理。
    在那之前，任何把这条路修好的改动（哪怕只是修 stale range 让 POST 不再 400）也会让
    本条红——**那是正确的红**，说明行为变了，本条要随之改判，不是把断言放宽。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_ch0(page, live_server, expected_marks=0)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(action_testid).click()
    before = wait_for_notes(e2e_books_dir, BOOK_ID, 1)
    old_id = str(before[0]["id"])
    expected_type = action_testid.rsplit("-", 1)[-1]
    assert before[0]["type"] == expected_type, (
        f"预置那条的 type 是 {before[0]['type']!r}，不是按下的 {expected_type!r}"
    )

    frame = open_ch0(page, live_server, expected_marks=1)
    select_in_frame(frame, CH0_QUOTE)
    page.get_by_test_id(SWATCH_TESTID).click()

    deletes: List[int] = []
    page.on(
        "response",
        lambda r: deletes.append(r.status)
        if r.request.method == "DELETE" and "/api/notes/" in r.url
        else None,
    )
    # 等那次注定失败的 POST，而不是 sleep：`expect_response` 等的是一个确定的事件。
    with page.expect_response(_is_notes_post) as post_info:
        page.get_by_test_id(action_testid).click()
    failed_post = post_info.value

    assert deletes == [204], (
        f"异色重按应当先发一次 DELETE 并得到 204，实际收到的 DELETE 状态序列是 {deletes}。"
        "一次都没有 ⇒ `toggleAnnotation` 的「同类型异色先删旧」那一段失效了"
    )
    assert failed_post.status == EXPECTED_FAILED_POST_STATUS, (
        f"替代性 POST 的状态是 {failed_post.status}，不是今天的 "
        f"{EXPECTED_FAILED_POST_STATUS}。行为变了：删掉旧条之后的那次新建不再被拒收——"
        "这正是 4B.1（W-5b）要达成的事，若 4B.1 已落地，本条应随 W-5b 一起改判"
    )
    posted = failed_post.request.post_data_json or {}
    assert posted.get("quote") == EXPECTED_FAILED_POST_QUOTE, (
        f"替代性 POST 的 quote 是 {posted.get('quote')!r}，不是今天的空串。"
        "空串是 stale `currentRange` 在重绘 `normalize()` 之后塌成折叠态的直接后果；"
        "它一旦变成真的选中文本，说明 stale range 被修好了，本条要改判"
    )

    wait_for_notes(e2e_books_dir, BOOK_ID, EXPECTED_AFTER_RECOLOR_TOGGLE)
    frame = open_ch0(page, live_server, expected_marks=0)
    after = read_notes(e2e_books_dir, BOOK_ID)

    assert len(after) == EXPECTED_AFTER_RECOLOR_TOGGLE, (
        f"异色重按 {expected_type} 之后 notes.json 应当剩 "
        f"{EXPECTED_AFTER_RECOLOR_TOGGLE} 条，实际 {len(after)} 条：{after}"
    )
    assert set(_ids(after)) & {old_id} == set(), (
        f"旧那条（id={old_id!r}）还在：{after}。异色分支应当先把它删掉"
    )
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(0)


# ---------------------------------------------------------------------------
# W-6 删除
# ---------------------------------------------------------------------------


def test_w6_delete_removes_only_the_clicked_annotation(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-6（S5，**差集律** `S'_章 = S_章 \\ {target}`）：删掉被点名的那一条，别的一字不动。

    链路：点 iframe 内目标 `<mark>` → `onAnnotationClick`（把该 mark 上的 metadata 收进
    `currentAnnotationMeta`）→ `rd-anno-delete` → `deleteCurrentAnnotation` →
    `deleteAnnotations(ids)` → 逐 id `DELETE /api/notes/{book}/{chapter}/{id}`。

    **反向断言不可省**（任务书 §3）：删除是唯一会破坏用户数据的操作，「删对了一条」和
    「顺手删掉了别的」在 UI 上看不出来。只有正向断言时，一个「清空整章标注」的实现全绿；
    加上反向与基数断言之后它必红。

    ⚠️ **旁观条必须落在与目标条不同的文字上，这是构造前提不是随手选的。**
    `deleteCurrentAnnotation()` 取的是 `currentAnnotationMeta` 上的**全部** id 然后一次性
    `deleteAnnotations(ids)`，而点击一个 `<mark>` 会把该 mark 上的所有 metadata 收进
    current。把旁观条放在与目标条**重叠**的同一段文字上，两条会渲染进同一个 `<mark>`，
    今天的实现会把它们一起删掉——那不是抓到了缺陷，那是夹具选错了，反向断言会**假红**。

    **【与 W-5a-⓪ 的分工，两条都不是重复】** 本条走 `deleteCurrentAnnotation`
    （读的是点击产生的 `currentAnnotationMeta`），W-5a-⓪ 走 `toggle*` 的同色分支
    （读的是 `currentRange` 命中的集合）。**两条路径各自独立地能把别人的数据删掉**，
    所以两条用例各自都带旁观条断言。

    **基数基准写字面量。** `EXPECTED_BEFORE_DELETE = 2` / `EXPECTED_AFTER_DELETE = 1`
    ——`> 0` 这类弱断言对「把整章删光」和「一条都没删」都绿（§0 第五条纪律）。

    **文件形状断的是「对象」，不是「数组」。** `notes_service.save_annotations` 写的是
    `{"schema_version": …, "book_id": …, "annotations": [...]}`；任务书原文「删完后仍是
    合法 JSON **数组**」按字面实现会稳定假红。012 若改 payload 形状，本条是那次改动的
    第一个红灯。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": W6_TARGET_ID,
                "chapter_index": CH0_INDEX,
                "type": "marker",
                "color": "yellow",
                "quote": CH0_QUOTE,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": W6_BYSTANDER_ID,
                "chapter_index": CH0_INDEX,
                "type": "marker",
                "color": "blue",
                "quote": BYSTANDER_QUOTE,
                "created_at": "2026-01-01T00:00:01+00:00",
            },
        ],
    )
    before = read_notes(e2e_books_dir, BOOK_ID)
    assert _ids(before) == [W6_TARGET_ID, W6_BYSTANDER_ID], f"预置没落对：{before}"
    assert len(before) == EXPECTED_BEFORE_DELETE, (
        f"删除前应当恰好 {EXPECTED_BEFORE_DELETE} 条，实际 {len(before)} 条：{before}"
    )
    bystander_before = dict(before[1])

    frame = open_ch0(page, live_server, expected_marks=EXPECTED_BEFORE_DELETE)

    target_mark = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{W6_TARGET_ID}"]'
    )
    expect(target_mark).to_have_text(CH0_QUOTE)
    target_mark.click()

    # 工具条开了才有 Delete 可点。这一断不是凑数：`onAnnotationClick` 首行遇到非
    # `mark.annotation` 就 return，静默 return 之后下面的 click 会以「元素不可见」超时，
    # 报出来的是 Playwright 的超时而不是「点击没落在标注上」。
    expect(page.get_by_test_id("rd-anno-toolbar")).to_be_visible()
    page.get_by_test_id("rd-anno-delete").click()

    wait_for_notes(e2e_books_dir, BOOK_ID, EXPECTED_AFTER_DELETE)
    frame = open_ch0(page, live_server, expected_marks=EXPECTED_AFTER_DELETE)
    after = read_notes(e2e_books_dir, BOOK_ID)

    # --- 基数：从 2 变 1，字面量基准 ------------------------------------------
    assert len(after) == EXPECTED_AFTER_DELETE, (
        f"删掉一条之后 notes.json 应当恰好剩 {EXPECTED_AFTER_DELETE} 条"
        f"（删前 {EXPECTED_BEFORE_DELETE} 条），实际 {len(after)} 条：{after}"
    )

    # --- 正向：目标 id 消失，目标段落上没有 `<mark>` ---------------------------
    assert W6_TARGET_ID not in _ids(after), (
        f"目标条 id={W6_TARGET_ID!r} 还在 notes.json 里：{after}"
    )
    expect(
        frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{W6_TARGET_ID}"]')
    ).to_have_count(0)
    spans = frame.get_by_test_id("rd-anno-span")
    expect(spans).to_have_count(1)
    assert spans.text_content() == BYSTANDER_QUOTE, (
        f"刷新后仅存的那个 `<mark>` 覆盖的文本是 {spans.text_content()!r}，"
        f"不是旁观条的 {BYSTANDER_QUOTE!r}——目标段落上的高亮没删干净？"
    )

    # --- 反向：无关条的 id 仍在，逐字段原样，且它的 `<mark>` 仍在渲染 -----------
    assert _ids(after) == [W6_BYSTANDER_ID], (
        f"删除之后剩下的应当**只**有无关条 {[W6_BYSTANDER_ID]}，实际是 {_ids(after)}"
    )
    assert after[0] == bystander_before, (
        f"无关条被动过了。\n  删除前：{bystander_before}\n  删除后：{after[0]}"
    )
    assert_bystanders_unchanged(before, after, changed_ids={W6_TARGET_ID})
    expect(
        frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{W6_BYSTANDER_ID}"]')
    ).to_have_text(BYSTANDER_QUOTE)

    # --- 文件形状：仍是那个顶层**对象**，不是空文件 / 裸数组 / 不存在 -----------
    payload = _notes_payload(e2e_books_dir, BOOK_ID)
    assert isinstance(payload, dict), (
        f"notes.json 的顶层不是对象而是 {type(payload).__name__}：{payload!r}。"
        "`save_annotations` 写的是 {'schema_version': …, 'book_id': …, 'annotations': [...]}"
    )
    assert NOTES_TOPLEVEL_KEYS <= set(payload), (
        f"notes.json 的顶层键缺了 {NOTES_TOPLEVEL_KEYS - set(payload)}：{payload}"
    )
    assert isinstance(payload["annotations"], list), (
        f"notes.json 的 annotations 不是列表：{payload['annotations']!r}"
    )
    assert len(payload["annotations"]) == EXPECTED_AFTER_DELETE, (
        f"文件里的 annotations 有 {len(payload['annotations'])} 条，"
        f"期望 {EXPECTED_AFTER_DELETE} 条：{payload['annotations']}"
    )
