"""WI-7 —— W-8 重叠标注（a 写路径 / b 渲染路径）与 W-10 同章重复文本消歧（a 写路径 / b 文本回退）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-7。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §3 的 W-8 / W-10、
§0 的六条写作纪律、§1 的 iframe 内建选区标准路径。

四条用例分成两对，**每对都是「写路径」与「渲染路径」各一条**，理由与 W-8a/W-8b 的拆分
理由同源：两侧的失败原因不同且不相关。写路径坏在 `createAnnotation` 的偏移/上下文计算与
落库，渲染路径坏在 `findRange` 的定位与 `buildSegments` 的边界算法。一条用例买不到两个覆盖。

------------------------------------------------------------------------------
**开工实测推翻了矩阵的一条前提：这个应用今天从来产不出 CFI**（2026-09-03，chromium 1234）
------------------------------------------------------------------------------
矩阵在 Round 1 的 Gap 7 里写下过一条「关键更正」，三条用例都建在它上面：

    「经 UI 创建的标注**一律带 CFI**（`contents.cfiFromRange` 成功）」

**这句话是错的。** 实测证据（探针，已删；结论如下，复现方法写在末尾）：

* `window.Reader3Epub.getContents()` 返回的对象上 `typeof cfiFromRange !== "function"`，
  `cfiBase` 为 `undefined`。成因在 `epub-renderer.js`：`currentContents` 取自
  `rendition.on("rendered", (section, contents) => …)` 的第二个实参，而 epub.js 的
  `rendered` 事件给的第二个实参是 **view**，不是 `Contents`。`Contents` 挂在 `view.contents` 上。
* 于是 `createAnnotation` 里那段 `contents.cfiFromRange(this.currentRange)` **一次都没被执行过**
  （`typeof` 守卫直接短路），落库的 `cfi` 恒为 `null`。四本语料上创建的每一条标注都实测为
  `"cfi": null`。
* 反过来，**epub.js 本身产得出正确的 CFI，`render()` 的 CFI 分支也解析得动**：
  `rendition.on("selected", …)` 的第一个实参实测是
  `epubcfi(/6/2[c1]!/4/2,/1:1894,/1:1916)`（正是末次出现的区间），而
  `new window.ePub.CFI(那个串).toRange(iframe.document).toString()` 实测返回
  `"the shadow of the mast"`。所以 CFI 通路是**通的**，只是写路径没往里灌东西。

这件事对本模块的三处后果，逐条记在这里，因为它们都是「不写下来下一个人会重做一遍」的：

1. **W-8a 今天其实会分段。** 矩阵原本判定「UI 建的两条都带 CFI ⇒ 走直接包裹 ⇒ 断三段会对着
   正确实现红」，因此明令 W-8a 不作分段声明。前提虽然错了，**这条禁令仍然照办**：分段是
   `cfi == null` 的**推论**，不是 W-8a 想钉的性质；哪天有人把 `getContents()` 修对，W-8a 该
   继续绿（两条标注都还在），该红的是别处。想断分段去 W-8b，那里的 `cfi=None` 是**构造保证**的。
2. **W-10a 不是「CFI 路径」那条用例。** 矩阵给 W-10a 的判据里有一句「`cfi` 非空且以
   `epubcfi(` 开头（顺带证明 CFI 真的被算出来了——否则本条实际走的是回退路径，用例名不副实）」。
   按今天的实现，这句判据是一条**稳定假红**。按 §0.5 对 K1 / K6 / W-5 的处理惯例，
   `baseline-1b` 断的是**今天的行为**：本模块把它反过来写成 `cfi is None` 的**绊线**——
   哪天 `getContents()` 被修对，W-10a 当场红，红的地方正好是要重新裁决 W-10 分工的地方。
3. **`render()` 的 CFI 分支今天零覆盖，本 WI 不补。** 补它要新增第五条用例，而
   `EXPECTED_BASELINE_ITEMS = 61` 的口径是「每个 WI 按矩阵条数交付、WI-17 统一对账」
   （任务书 §0.6 的并行前提）。留成显式欠账，别留成沉默。

------------------------------------------------------------------------------
**位置一律用「iframe body 文本中的字符偏移」表达，绝不用「第几个 `<mark>`」**
------------------------------------------------------------------------------
任务书 §3 W-10 要的是「刷新后落在**第二处**」。章内只有一个 `<mark>` 时，「第 0 个 `<mark>`
的文本等于 quote」是一句**恒真**——一个「永远高亮第一处」的实现照样绿。所以本模块的
`_scan_marks` 把每个 `<mark>` 的文本节点在 body 文本轴上的起止偏移一并读出来，判据落在偏移上。

`_scan_marks` 走 `TreeWalker(SHOW_TEXT)` 而不是 `body.textContent`：两者在本语料上同解，
但前者与生产端 `buildTextIndex` 的取文本方式一致，不会因为将来有人往 body 里注入
`<style>` 而两边错位。

------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律）**——特征化用例天然无红，靠定向破坏留档
------------------------------------------------------------------------------
破坏点**一律打在用例自己的期望值/种子数据上，一行生产代码都没动**（§0：伪造的收据比没有
收据更坏）。五次全部已还原，`git diff --stat` 空。

逐字失败输出照抄自当时的运行，未做任何删改（只删掉了与判据无关的 `Captured stdout` 段）。

**D1** —— 把 W-8a 的期望并集 `{record_a["id"], record_b["id"]}` 改成 `{record_a["id"]}`：

    E   AssertionError: DOM 里渲染出的 id 并集是 {'66f9d2cb-…-5d48acc6b4ca', '0c4bffd6-…-e5d99d2317b9'},
        期望 {'0c4bffd6-…-e5d99d2317b9', '66f9d2cb-…-5d48acc6b4ca'}——有标注落了库却没渲染出来（或渲染
        出了不该有的）。分段：[('Alpha ', {'0c4bffd6…'}), ('pro', {'66f9d2cb…', '0c4bffd6…'}), ('se', {'66f9d2cb…'})]
    E   assert {'0c4bffd6-21...5d48acc6b4ca'} == {'0c4bffd6-21...e5d99d2317b9'}
    E     Extra items in the left set:
    E     '66f9d2cb-b36b-462e-8295-5d48acc6b4ca'

证明「两条都被渲染出来了，一条都没丢」这句判据真在数两条。（消息里「期望」后面仍印着两个 id，
是因为破坏只改了比较式没改插值文本——`assert` 那两行才是这次破坏的证据。）

**D2** —— 把 W-8b 的期望 `("pro", {W8B_MARKER_ID, W8B_WAVY_ID})` 改成 `("pro", {W8B_MARKER_ID})`：

    E   AssertionError: 分段结果与期望不符
    E       实际：[('Alpha ', {'wi7-w8b-marker'}), ('pro', {'wi7-w8b-wavy', 'wi7-w8b-marker'}), ('se', {'wi7-w8b-wavy'})]
    E       期望：[('Alpha ', {'wi7-w8b-marker'}), ('pro', {'wi7-w8b-marker'}), ('se', {'wi7-w8b-wavy'})]
    E   assert [('Alpha ', {...7-w8b-wavy'})] == [('Alpha ', {...7-w8b-wavy'})]
    E     At index 1 diff: ('pro', {'wi7-w8b-wavy', 'wi7-w8b-marker'}) != ('pro', {'wi7-w8b-marker'})

证明重叠段挂的是**恰好两个** id，不是「至少两个」——`buildSegments` 的 `covering` 过滤真在起作用。

**D3 / D4** —— 把 `_assert_at_last_occurrence` 的期望偏移由 `REPEAT_LAST_OFFSET` 改成
`REPEAT_FIRST_OFFSET`，分别单跑 W-10a 与 W-10b，两条各红一次：

    E   AssertionError: 刷新后 <mark> 落在偏移 1894，期望 1894（第一处在 22，末次在 1894）
    E   assert 1894 == 22

证明两条用例的位置判据都真的咬在偏移 1894 上（消息里的「期望 1894」同样是插值文本没跟着改，
`assert 1894 == 22` 是证据）。**真实的失败形状见 D5b**，那一条是从另一端打的，消息完整。

**D5a** —— 把 W-10b 的种子 `cfi=None` 换成指向**第一处**的真实 CFI
`epubcfi(/6/2[c1]!/4/2,/1:22,/1:44)`（该串实测可解析，`toRange().toString() == quote`）：

    E   AssertionError: 种子那一条的 cfi 是 'epubcfi(/6/2[c1]!/4/2,/1:22,/1:44)'，不是 None ——
        本条要测的是文本回退路径，cfi 非空时 `render()` 会先走 CFI 分支，prefix/suffix 不参与
    E   assert 'epubcfi(/6/2[c1]!/4/2,/1:22,/1:44)' is None

证明「种子的 cfi 确实是 None」那句核验不是空转。

**D5b** —— 同 D5a，且把上面那句核验一并短路掉，让位置判据自己接招：

    E   AssertionError: 刷新后 <mark> 落在偏移 22，期望 1894——落在了**第一处**（偏移 22）。
        `findRange` 的 `prefix + quote + suffix` 组合串分支被跳过了，退化成了裸 `text.indexOf(quote)`。
    E   assert 22 == 1894

**这是本表里最强的一条。** 它同时证明了三件事：位置判据能红；`cfi` 置空是**载荷性**的
（非空且可解析时 `render()` 先走 CFI 分支，prefix/suffix 根本不参与）；以及「落到第一处」
这个失败态在真实运行里长什么样。

**关于「不置空会不会恒绿」这个问题的准确答案。** 派活简报预判「W-10b 若不把 `cfi` 置空，
断言会因为走了 CFI 路径而恒绿」。按今天的实现，**这个预判只在种子数据里成立，在写路径上
不成立**——写路径根本产不出 CFI（见上文实测），所以「不置空」在 W-10b 里不是「照抄写路径的
产物」，而是「手写一个 CFI 塞进去」。D5b 就是这么做的：塞一个指向**第一处**的真实 CFI，
断言当场红在偏移 22 上。这既证明了 `cfi=None` 载荷性，也证明了 `render()` 的 CFI 优先级
——比原预判的「恒绿」是更强的证据，因为它给出了**方向**。

`cfi` 置空**确实生效**的核验方式，不靠推理：W-10b 在 `seed_notes` 之后立刻
`read_notes()` 读回落盘的那一条，断 `record["cfi"] is None`（`Annotation.from_dict` 对
`cfi` 不补默认值，读回来是什么就是什么）。这条断言与「落在末次出现」那条分开写，
是为了让「种子没落对盘」与「解析落错了处」在失败消息里分得开。

**复现「CFI 实测」的方法**（探针已删，结论留在上面）：在 `open_reader` 之后 `page.evaluate`
读 `window.Reader3Epub.getContents()` 的 `typeof cfiFromRange` 与 `cfiBase`；再挂一个
`window.Reader3Epub.rendition.on("selected", c => …)` 收 `cfiRange`，拿它去
`new window.ePub.CFI(c).toRange(window.Reader3Epub.getContentDocument())`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest
from playwright.sync_api import Page

from conftest import BOOK_ID, BOOK_ID_REPEAT  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    assert_bystanders_unchanged,
    assert_roundtrip,
    open_reader,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# 坐标（全部字面量 —— §0 第五条纪律：守恒/定位断言的基准不许是运行期读回来的值）
# ---------------------------------------------------------------------------
#
# `smoke_data`（`build_epub2`）第 0 章的 body 是 `<h1>One</h1><p>Alpha prose.</p>`，
# iframe 内 body 文本实测为 `"OneAlpha prose.\n"`（末尾那个 `\n` 是 `_xhtml` 模板里
# `</body>` 之后的换行，被 HTML 解析器归进 body）。
#
# 区间校验（部分重叠，非包含非相离）：A = `"Alpha pro"` = [3, 12)，B = `"prose"` = [9, 14)。
# `A ∩ B = [9, 12) = "pro"` 非空，且 `A ⊄ B`、`B ⊄ A`。**这是真部分重叠**——它是 W-8 的
# 全部前提：换成包含关系，`buildSegments` 只切两段，重叠段那条判据就再也走不到。
OVERLAP_A_QUOTE = "Alpha pro"
OVERLAP_B_QUOTE = "prose"
OVERLAP_UNION_TEXT = "Alpha prose"

#: W-8b 的两条种子 id 写死字面量：失败消息里「id 变成了别的」要是一个人一眼认得出的串，
#: 不是两个都不认识的 uuid（§0 第五条纪律，W-7 的先例）。
W8B_MARKER_ID = "wi7-w8b-marker"
W8B_WAVY_ID = "wi7-w8b-wavy"

#: 同理。W-10b 那一条。
W10B_ID = "wi7-w10b-fallback"

#: 种子的 `created_at` 也写死：它是 `Annotation` 的默认工厂字段，取 `now()` 会让
#: 「这条被删了重建」在整字典比对里显不出形。
SEED_CREATED_AT = "2026-01-01T00:00:00+00:00"

# `repeat_data`（`build_huge_epub(chars=1950, needle="SENTINEL")`）：`_HUGE_SENTENCE`
# 长 78 字符，`1950 == 78 * 25`，所以正文恰好是 25 遍完整句子 ＋ `SENTINEL`。
# iframe 内 body 文本实测 1959 字符（1950 + 8 + 模板换行 1）。
REPEAT_ANCHOR = "SENTINEL"
REPEAT_QUOTE = "the shadow of the mast"

#: 25 次出现。`findRange` 的 `text.indexOf(quote)` 兜底分支会命中**第一处**，
#: 所以「落在末次」与「落在第一处」在偏移上相差 1872 —— 一个不可能靠巧合对上的距离。
REPEAT_OCCURRENCES = 25
REPEAT_FIRST_OFFSET = 22
REPEAT_LAST_OFFSET = 1894

#: 末次出现前的 50 字符。**它本身不唯一**（重复句的一段，25 处都长这样）——
#: 唯一性来自下面的 suffix。用例 docstring 会再说一遍，因为读者很容易以为是 prefix 在起作用。
REPEAT_PREFIX = " across the deck once more. The lamp guttered and "

#: 末次出现后的全部剩余文本，42 字符。`SENTINEL` 只出现一次，所以
#: `prefix + quote + suffix` 这个组合串**全书唯一**，`findRange` 的 combo 分支必然命中末次。
REPEAT_SUFFIX = " swung across the deck once more. SENTINEL"

#: 生产端 `createAnnotation` 存下来的那一份多一个模板换行：
#: `suffix = idx.text.slice(e, e + 50)`，而 e 之后只剩 43 字符（42 + `\n`），不足 50 不截断。
REPEAT_STORED_SUFFIX = REPEAT_SUFFIX + "\n"


# ---------------------------------------------------------------------------
# 读 DOM：body 文本轴 ＋ 每个 `<mark>` 在轴上的位置与 id 集合
# ---------------------------------------------------------------------------

# 为什么用 `dataset.annotationIds` 而不是 `getAttribute("data-annotation-ids")`：
# 后者会被 `scripts/lint_e2e_selectors.py` 的 `LOCATOR_CALL_RE` 当成一处选择器扫到
# （它匹配 `.getAttribute(` 后面那个字符串实参），报「含非 data-* 属性选择器的部分」。
# 那是一次误报，但让它误报再逐行放行，等于把这条 lint 的信噪比往下拉；换个等价 API 更便宜。
_SCAN_MARKS_JS = r"""
() => {
  const body = document.body;
  const doc = body.ownerDocument;
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const marks = [];
  let text = "";
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const start = text.length;
    text += node.data;
    const parent = node.parentElement;
    // `closest` 取的是**最内层**的那个 `<mark>`：applySegments 产出的三段是兄弟节点，
    // 各含一个文本节点，于是这里一个文本节点恰好对应一段，顺序即 DOM 顺序。
    const host = parent ? parent.closest('[data-testid="rd-anno-span"]') : null;
    if (!host) continue;
    let ids = null;
    try {
      ids = JSON.parse(host.dataset.annotationIds || "[]");
    } catch (err) {
      ids = null;  // 解析不出来就交给 Python 侧报，别在这里吞掉
    }
    marks.push({ text: node.data, start, end: start + node.data.length, ids,
                 raw: host.dataset.annotationIds });
  }
  return { text, marks };
}
"""


def _scan_marks(frame: Any) -> Dict[str, Any]:
    """iframe body 的文本轴 ＋ 按 DOM 顺序排列的 `<mark>` 分段。

    返回 ``{"text": str, "marks": [{"text", "start", "end", "ids", "raw"}, …]}``。
    ``start`` / ``end`` 是在 ``text`` 上的字符偏移——本模块所有位置判据都落在它上面。
    """
    return frame.locator("body").evaluate(_SCAN_MARKS_JS)  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板


def _segments(scan: Dict[str, Any]) -> List[Tuple[str, Set[str]]]:
    """把扫描结果压成 `[(段文本, id 集合), …]`，DOM 顺序。`ids` 解析失败时当场抛。"""
    out: List[Tuple[str, Set[str]]] = []
    for mark in scan["marks"]:
        if mark["ids"] is None:
            raise AssertionError(
                f"`data-annotation-ids` 不是合法 JSON：{mark['raw']!r}。"
                "`applySegments` / `render()` 改过这个属性的写法？"
            )
        out.append((mark["text"], set(mark["ids"])))
    return out


def _all_ids(scan: Dict[str, Any]) -> Set[str]:
    ids: Set[str] = set()
    for _, seg_ids in _segments(scan):
        ids |= seg_ids
    return ids


def _sole_mark(scan: Dict[str, Any], quote: str) -> Dict[str, Any]:
    """章内恰好一个 `<mark>`、且它的文本恰好是 `quote` 时返回它，否则抛。

    「恰好一个」这半句是判据的一部分，不是取值的方便写法：W-10 的两条各自只该产生一条
    标注，多出来的任何一段都意味着渲染重复或选区跑偏。
    """
    marks = scan["marks"]
    if len(marks) != 1:
        raise AssertionError(
            f"期望章内恰好 1 个 `<mark>`，实际 {len(marks)} 个："
            f"{[(m['text'], m['start']) for m in marks]}"
        )
    mark = marks[0]
    assert mark["text"] == quote, (
        f"`<mark>` 覆盖的文本是 {mark['text']!r}，不是 {quote!r}"
    )
    return mark


def _assert_corpus_coordinates(text: str) -> None:
    """语料坐标自检：本模块的四个字面量偏移必须与 iframe 里真实的文本吻合。

    单独抽出来，是为了让「语料变了」与「锚定错了」在失败消息里分得开——两者的修法完全
    不同（前者改本文件的常量，后者改生产代码），而它们在「偏移不等于 1894」这一句里长得一样。
    """
    assert text.count(REPEAT_QUOTE) == REPEAT_OCCURRENCES, (
        f"语料变了：{REPEAT_QUOTE!r} 出现 {text.count(REPEAT_QUOTE)} 次，"
        f"本模块的坐标是按 {REPEAT_OCCURRENCES} 次算的（conftest 的 REPEAT_BOOK_CHARS 被改过？）"
    )
    assert text.find(REPEAT_QUOTE) == REPEAT_FIRST_OFFSET, (
        f"语料变了：第一处在偏移 {text.find(REPEAT_QUOTE)}，本模块按 {REPEAT_FIRST_OFFSET} 算"
    )
    assert text.rfind(REPEAT_QUOTE) == REPEAT_LAST_OFFSET, (
        f"语料变了：末次出现在偏移 {text.rfind(REPEAT_QUOTE)}，本模块按 {REPEAT_LAST_OFFSET} 算"
    )
    tail_start = REPEAT_LAST_OFFSET + len(REPEAT_QUOTE)
    assert text[tail_start : tail_start + len(REPEAT_SUFFIX)] == REPEAT_SUFFIX, (
        "语料变了：末次出现之后的文本不是 "
        f"{REPEAT_SUFFIX!r}，而是 {text[tail_start : tail_start + len(REPEAT_SUFFIX)]!r}"
    )


def _assert_at_last_occurrence(mark: Dict[str, Any], text: str) -> None:
    """`<mark>` 落在**末次出现**——位置用字符偏移表达，不用「第几个 `<mark>`」。

    两条判据合起来才够：
      * 数值判据 `start == REPEAT_LAST_OFFSET`，一个「永远高亮第一处」的实现在这里差 1872；
      * 字面量判据「紧随其后的 42 个字符是 `" swung … SENTINEL"`」——`SENTINEL` 全书唯一，
        所以这一句独立于任何偏移算术，直接说明「它落在的是有 SENTINEL 后文的那一处」。
    """
    assert mark["start"] == REPEAT_LAST_OFFSET, (
        f"刷新后 <mark> 落在偏移 {mark['start']}，期望 {REPEAT_LAST_OFFSET}"
        + (
            f"——落在了**第一处**（偏移 {REPEAT_FIRST_OFFSET}）。"
            "`findRange` 的 `prefix + quote + suffix` 组合串分支被跳过了，"
            "退化成了裸 `text.indexOf(quote)`。"
            if mark["start"] == REPEAT_FIRST_OFFSET
            else f"（第一处在 {REPEAT_FIRST_OFFSET}，末次在 {REPEAT_LAST_OFFSET}）"
        )
    )
    tail = text[mark["end"] : mark["end"] + len(REPEAT_SUFFIX)]
    assert tail == REPEAT_SUFFIX, (
        f"<mark> 之后的文本是 {tail!r}，不是末次出现应有的 {REPEAT_SUFFIX!r}"
    )


# ---------------------------------------------------------------------------
# W-8：重叠标注
# ---------------------------------------------------------------------------


def test_w8a_two_overlapping_annotations_both_persist_and_render(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-8a（S2，区间关系的边界等价类：**部分重叠**）：在已有 `<mark>` 之上再建选区。

    链路：选区 A → marker → 刷新 → **在已渲染出 `<mark>` 的文字上**再选 B → wavy → 刷新
    → 两条都在盘上、两条的 id 在 DOM 里都还在。

    **第二次按的是另一个 type，这是刻意的。** marker 之后按 wavy 走的是
    `toggleAnnotation` 的**创建**分支；若把 B 也改成 marker「简化用例」，走的会是
    `toggleMarkerAnnotation` 的同色 toggle-off 分支，本条会静默变成一条与 W-5a-⓪
    重复的删除用例，并丢掉全部重叠覆盖。

    **为什么第二次的偏移算得准：`buildTextIndex` 不排除 `<mark>` 内的文本节点。**
    它的 `acceptNode` 只挡 `script, style, #annotation-toolbar, #note-editor, #note-tooltip`，
    所以 A 的 `<mark>` 把 `"Alpha prose."` 切成 `"Alpha pro"` ＋ `"se.\\n"` 两个文本节点之后，
    偏移轴仍然连续，B 的 `"prose"` 照样定位在 9。这条事实是本用例能否稳定的关键——实测
    落库的 B 是 `position=9, quote="prose"`。

    **本条明确不作分段形态的声明**（矩阵原文，前提虽被实测更正但禁令照办，理由见模块
    docstring 第 1 条）：不断「恰好三段」「重叠段挂两个 id」。那是 `cfi == null` 的推论，
    不是本条要钉的性质；想断分段去 `test_w8b_*`，那里的 `cfi=None` 是构造保证的。

    自检：一个「第二次创建时把第一条覆盖掉」的实现在条数与并集上都红；一个「落库了但渲染
    时丢一条」的实现只在并集上红——两条判据抓的不是同一件事。
    """
    assert read_notes(e2e_books_dir, BOOK_ID) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    select_in_frame(frame, OVERLAP_A_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()
    record_a = assert_roundtrip(
        page, e2e_books_dir, BOOK_ID, OVERLAP_A_QUOTE, CH0_ANCHOR, expected_type="marker"
    )
    before = read_notes(e2e_books_dir, BOOK_ID)

    # 第二条：在 A 已经渲染成 `<mark>` 的那段文字上重新建选区。
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    select_in_frame(frame, OVERLAP_B_QUOTE)
    page.get_by_test_id("rd-anno-type-wavy").click()
    landed = wait_for_notes(e2e_books_dir, BOOK_ID, 2)

    by_quote = {r["quote"]: r for r in landed}
    assert set(by_quote) == {OVERLAP_A_QUOTE, OVERLAP_B_QUOTE}, (
        f"两条的 quote 不是 {OVERLAP_A_QUOTE!r} / {OVERLAP_B_QUOTE!r}：{landed}"
    )
    record_b = by_quote[OVERLAP_B_QUOTE]
    assert by_quote[OVERLAP_A_QUOTE]["type"] == "marker"
    assert record_b["type"] == "wavy", (
        f"第二条的 type 是 {record_b['type']!r}，不是按下的 wavy —— "
        "第二次按键走到了 toggle-off 分支？"
    )
    assert record_b["id"] != record_a["id"], (
        "两条标注共用了同一个 id —— 第二次创建把第一条改掉了，而不是新建"
    )

    page.reload()
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    scan = _scan_marks(frame)

    rendered_ids = _all_ids(scan)
    assert rendered_ids == {record_a["id"], record_b["id"]}, (
        f"DOM 里渲染出的 id 并集是 {rendered_ids}，期望 {{{record_a['id']!r}, {record_b['id']!r}}}"
        f"——有标注落了库却没渲染出来（或渲染出了不该有的）。分段：{_segments(scan)}"
    )
    covered = "".join(text for text, _ in _segments(scan))
    assert OVERLAP_UNION_TEXT in covered, (
        f"全部 `<mark>` 的文本拼起来是 {covered!r}，没有覆盖到两条标注的并集 "
        f"{OVERLAP_UNION_TEXT!r}"
    )

    # 终态再断一次条数（§0 第四条纪律：`wait_for_notes` 可能读到中间态），
    # 并断 A 这条旁观者逐字段原样——「第二次创建顺手改了第一条」在 UI 上看不出来。
    settled = read_notes(e2e_books_dir, BOOK_ID)
    assert len(settled) == 2, f"终态不是恰好 2 条，而是 {len(settled)} 条：{settled}"
    assert_bystanders_unchanged(before, settled, {record_b["id"]})


def test_w8b_overlapping_text_path_annotations_split_into_three_segments(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-8b（S2，`buildSegments` 边界集合算法）：部分重叠切出 `{左差, 交, 右差}` **三段有序**。

    与 W-8a 的**唯一**关键差别：两条种子都 `cfi=None`，这是它能进 `buildSegments` 的原因。
    `render()` 先 `filter(ann => ann?.cfi)`，带 CFI 的那批走 `extractContents` / `insertNode`
    直接包裹，压根不经过分段算法。（今天写路径也产不出 CFI ——见模块 docstring——但那是
    一个会被修掉的事实，而本条要的是**构造上的保证**，不是运气。）

    **分段推演**（实现前已核对，错了本条会稳定假红）：body 文本 `"OneAlpha prose.\\n"`。
    `findRange` 在 prefix / suffix 均空时跳过 combo 分支，直接 `text.indexOf(quote)`：
    A → `[3,12)`，B → `[9,14)`。边界集合 `{3, 9, 12, 14}`，相邻切片 `[3,9)` / `[9,12)` / `[12,14)`；
    `covering = ranges.filter(r => r.start <= start && r.end >= end)` 给出：

        | 切片     | 文本       | ids            |
        |----------|------------|----------------|
        | [3, 9)   | `"Alpha "` | {A}            |
        | [9, 12)  | `"pro"`    | {A, B}         |
        | [12, 14) | `"se"`     | {B}            |

    **判据是有序列表等值，不是集合、不是「存在一段挂两个 id」。** 集合断言会放过顺序颠倒，
    存在性断言会放过左右差段整个丢失。重叠段的 id 集合断的是**恰含两个**（`== {A, B}`），
    不是「至少两个」——`>=` 那种写法在 `covering` 把整章标注都算进来时照样绿。

    **一个看着像脆点、其实不是的地方**：`findRange` 若改成在空 prefix/suffix 时也走 combo
    分支，`"" + quote + ""` 恰好等于 quote，结论不变，本条**不会**因此红。写在这里免得被
    误当成脆弱依赖删掉。

    自检：把 `buildSegments` 换成「整个并集包一层挂两个 id」⇒ 只得一段 ⇒ 红；把 `covering`
    的过滤漏掉右端（只留 `r.start <= start`）⇒ `"se"` 段会多挂 A ⇒ 红。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID,
        [
            {
                "id": W8B_MARKER_ID,
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": OVERLAP_A_QUOTE,
                "prefix": "",
                "suffix": "",
                "position": 3,
                "cfi": None,
                "created_at": SEED_CREATED_AT,
            },
            {
                "id": W8B_WAVY_ID,
                "chapter_index": 0,
                "type": "wavy",
                "color": "yellow",
                "quote": OVERLAP_B_QUOTE,
                "prefix": "",
                "suffix": "",
                "position": 9,
                "cfi": None,
                "created_at": SEED_CREATED_AT,
            },
        ],
    )
    seeded = read_notes(e2e_books_dir, BOOK_ID)
    assert [r["cfi"] for r in seeded] == [None, None], (
        f"种子没落对盘：两条的 cfi 应当都是 None，实际 {[r['cfi'] for r in seeded]}。"
        "带 CFI 的标注走的是直接包裹分支，根本不进 buildSegments，本条会测错东西"
    )

    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    # 三段是渲染的产物，`loadAndRender()` 要等一次 fetch 往返；用 Playwright 的自动等待
    # 盯住最后一段出现，而不是 sleep 一个猜出来的毫秒数。
    frame.locator(  # lint-e2e-selectors: allow —— 判别位 data-annotation-id 在 ADR-0014 的闭合清单内
        f'[data-testid="rd-anno-span"][data-annotation-id="{W8B_WAVY_ID}"]'
    ).first.wait_for()

    actual = _segments(_scan_marks(frame))
    expected: List[Tuple[str, Set[str]]] = [
        ("Alpha ", {W8B_MARKER_ID}),
        ("pro", {W8B_MARKER_ID, W8B_WAVY_ID}),
        ("se", {W8B_WAVY_ID}),
    ]
    assert actual == expected, (
        "分段结果与期望不符\n"
        f"  实际：{actual}\n"
        f"  期望：{expected}"
    )


# ---------------------------------------------------------------------------
# W-10：同章重复文本消歧
# ---------------------------------------------------------------------------


def test_w10a_write_path_anchors_the_last_of_25_identical_phrases(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-10a（S1，写路径）：标 25 处相同文字中的**末次**，刷新后仍在末次出现的偏移上。

    语料是 `repeat_data`（`build_huge_epub(chars=1950, needle="SENTINEL")`，conftest 已建，
    本模块不新建语料）：25 遍同一句 ＋ 末尾 `SENTINEL`。`select_in_frame(..., occurrence=-1)`
    选末次那一处。

    **位置判据落在字符偏移上，不落在「第几个 `<mark>`」上。** 本章只会有一个 `<mark>`，
    「第 0 个 `<mark>` 的文本等于 quote」是一句恒真，一个「永远高亮第一处」的实现照样绿。
    偏移判据下，那个实现差 1872 个字符。

    **落库判据里有一条绊线：`cfi is None`。** 矩阵原写「`cfi` 非空且以 `epubcfi(` 开头」，
    实测那是一条稳定假红——`getContents()` 返回的不是 `Contents` 而是 view，
    `cfiFromRange` 不存在，写路径**从来**产不出 CFI（成因与证据见模块 docstring）。
    按 §0.5 对 K1 / K6 / W-5 的惯例，`baseline-1b` 断今天的行为：写成 `is None`，
    哪天有人把 `getContents()` 修对，本条当场红，而红的位置正是要重新裁决 W-10 分工的位置。

    **于是今天的锚定全靠 `prefix + quote + suffix`**，也就是说本条与 `test_w10b_*` 走的是
    同一条解析路径，分工是**写侧 / 读侧**而不是 CFI / 文本：本条钉的是 `createAnnotation`
    在偏移 1894 上算出的 `position` 与上下文窗口（50 字符），W-10b 钉的是 `findRange` 拿着
    手写的上下文能不能定位回同一处。

    **prefix 不唯一，suffix 才唯一。** `prefix` 是重复句的一段，25 处都长这样；
    `suffix` 因为含 `SENTINEL` 而全书唯一。所以起决定作用的是**组合串**，不是 prefix。
    """
    assert read_notes(e2e_books_dir, BOOK_ID_REPEAT) == [], "隔离 fixture 没生效：起点不是空的"

    frame = open_reader(page, live_server, BOOK_ID_REPEAT, 0, REPEAT_ANCHOR)
    _assert_corpus_coordinates(_scan_marks(frame)["text"])

    select_in_frame(frame, REPEAT_QUOTE, occurrence=-1)
    page.get_by_test_id("rd-anno-type-marker").click()
    record = wait_for_notes(e2e_books_dir, BOOK_ID_REPEAT, 1)[0]

    assert record["quote"] == REPEAT_QUOTE, f"落库的 quote 是 {record['quote']!r}"
    assert record["position"] == REPEAT_LAST_OFFSET, (
        f"落库的 position 是 {record['position']}，期望末次出现的 {REPEAT_LAST_OFFSET}"
        f"（第一处是 {REPEAT_FIRST_OFFSET}）"
    )
    assert record["prefix"] == REPEAT_PREFIX, (
        f"落库的 prefix 是 {record['prefix']!r}，期望 {REPEAT_PREFIX!r}"
    )
    assert record["suffix"] == REPEAT_STORED_SUFFIX, (
        f"落库的 suffix 是 {record['suffix']!r}，期望 {REPEAT_STORED_SUFFIX!r}"
        "——suffix 是消歧的唯一来源（含全书唯一的 SENTINEL），它被截短就没得消歧了"
    )
    assert record["cfi"] is None, (
        f"落库的 cfi 是 {record['cfi']!r}，而 baseline-1b 特征化的今日行为是 None。"
        "若 `getContents()` 已被修成返回真正的 Contents，那么 CFI 通路刚刚接上了："
        "W-10a / W-10b 的分工要重新裁决（本条会变成 CFI 路径用例，W-10b 仍是文本回退），"
        "并给 `render()` 的 CFI 分支补一条独立用例。见模块 docstring 第 3 条欠账"
    )

    page.reload()
    frame = open_reader(page, live_server, BOOK_ID_REPEAT, 0, REPEAT_ANCHOR)
    scan = _scan_marks(frame)
    _assert_corpus_coordinates(scan["text"])
    _assert_at_last_occurrence(_sole_mark(scan, REPEAT_QUOTE), scan["text"])

    settled = read_notes(e2e_books_dir, BOOK_ID_REPEAT)
    assert len(settled) == 1, f"终态不是恰好 1 条，而是 {len(settled)} 条：{settled}"


def test_w10b_text_fallback_path_anchors_the_last_of_25_identical_phrases(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-10b（S3，点名的失败模式）：`cfi` 为空时，降级解析必须仍然选中**同一处**。

    **不依赖 W-10a 的产物**（跨用例依赖 = flaky）：用 `seed_notes` 直接预置一条，
    `quote` 是那 25 处重复文字，`prefix` / `suffix` 取末次出现两侧，`cfi=None`。

    **这条用例能失败的方式是明确的：落到第一处。** `findRange` 先查
    `text.indexOf(prefix + quote + suffix)`，查不到才退到 `text.indexOf(quote)`；后者在本语料上
    命中的是偏移 22，而期望是 1894。把 `findRange` 换成裸 `indexOf(quote)` 的单行实现，
    本条红——这正是 §3 W-10 括号里「prefix/suffix 生效」要的那个判据。

    **唯一性来自 suffix，不是 prefix。** `prefix` 是重复句的一段，25 处都相同；
    `suffix` 含全书唯一的 `SENTINEL`。组合串因此唯一。读者很容易以为是 prefix 在起作用，
    所以这一句在 W-10a 与这里各写一遍。

    **`cfi` 置空真的生效了怎么核实**：`seed_notes` 之后立刻 `read_notes()` 读回落盘的那一条，
    断 `cfi is None`（`Annotation.from_dict` 对 `cfi` 不补默认值）。这条断言与位置断言分开写，
    是为了让「种子没落对盘」和「解析落错了处」在失败消息里分得开。载荷性的证据见模块
    docstring 的 D5b：把它换成指向**第一处**的真实 CFI，位置断言当场红在偏移 22 上。
    """
    seed_notes(
        e2e_books_dir,
        BOOK_ID_REPEAT,
        [
            {
                "id": W10B_ID,
                "chapter_index": 0,
                "type": "marker",
                "color": "yellow",
                "quote": REPEAT_QUOTE,
                "prefix": REPEAT_PREFIX,
                "suffix": REPEAT_SUFFIX,
                "position": REPEAT_LAST_OFFSET,
                "cfi": None,
                "created_at": SEED_CREATED_AT,
            }
        ],
    )
    seeded = read_notes(e2e_books_dir, BOOK_ID_REPEAT)
    assert len(seeded) == 1 and seeded[0]["id"] == W10B_ID, f"种子没落对盘：{seeded}"
    assert seeded[0]["cfi"] is None, (
        f"种子那一条的 cfi 是 {seeded[0]['cfi']!r}，不是 None —— "
        "本条要测的是文本回退路径，cfi 非空时 `render()` 会先走 CFI 分支，prefix/suffix 不参与"
    )

    frame = open_reader(page, live_server, BOOK_ID_REPEAT, 0, REPEAT_ANCHOR)
    frame.locator(  # lint-e2e-selectors: allow —— 判别位 data-annotation-id 在 ADR-0014 的闭合清单内
        f'[data-testid="rd-anno-span"][data-annotation-id="{W10B_ID}"]'
    ).first.wait_for()

    scan = _scan_marks(frame)
    _assert_corpus_coordinates(scan["text"])
    mark = _sole_mark(scan, REPEAT_QUOTE)
    assert mark["ids"] == [W10B_ID], f"`<mark>` 挂的 id 是 {mark['ids']}，期望 [{W10B_ID!r}]"
    _assert_at_last_occurrence(mark, scan["text"])

    # 渲染是只读路径：不该往盘上写任何东西。
    after = read_notes(e2e_books_dir, BOOK_ID_REPEAT)
    assert after == seeded, f"仅仅打开章节就改动了 notes.json：\n  前：{seeded}\n  后：{after}"
