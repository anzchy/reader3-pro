"""017 WI-5（审计 #3、#9）——盘上那条 `cfi` 与 `quote` 对不上时，`quote` 说了算。

**审计 #3 描述的现场只对了一半，另一半必须写在这里，否则下一个人会照着错的地图修。**
它说的是 `createAnnotation` 拿**已经被判定不可信的** `this.currentRange` 去算 `cfi`
（`annotations.js` 的 `resolveOffsets` 刚刚回落到快照，说明那个 Range 不能信了）。
这条推断本身成立，但**那段代码今天一次都没执行过**：写侧取的是
``window.Reader3Epub.getContents()``，而 `epub-renderer.js` 把它实现成返回 epub.js 的
**View**，不是 `Contents`。View 上没有 `cfiFromRange`，于是
``typeof contents.cfiFromRange === "function"`` 恒假，`cfi` 恒为 `null`。
2026-09-23 在浏览器里实测：View 的原型链上只有 `highlight/mark/locationOf/…`，真正的
`Contents` 挂在 `view.contents` 上，它才有 `cfiFromRange` 与 `range`。

所以缺陷分两层，**能当场咬人的是第二层**：

* **潜伏的**（写侧）：哪天有人把 `getContents()` 接到真的 `Contents` 上，或换一版
  epub.js，那条「拿失效 Range 算 cfi」的路当天就活过来，而它写进盘的是一条与
  `quote`／`position` 自相矛盾的锚点。
* **现役的**（读侧）：`render()` 对带 `cfi` 的标注**无条件优先**用 CFI 重锚（CFI 分支
  跑在文本匹配之前），`rangeFromCfi` 只要**解析得出来**就用，从不与 `quote` 对照。
  一条指向别处或塌成一点的 `cfi`——旧数据、别的客户端写的、将来那条潜伏路径写的——
  当场让用户看见一道划在错地方的线，或者一道空的。盘上 `quote` 完全正确。

**修法是一条对称的规矩，两侧各执行一次**：*一条 `cfi` 只有在它和 `quote` 对得上时，
才值得写、才值得信*。读侧（本文件照的就是它）把解析出来的 Range 与 `quote` 比一次，
不一致就退回文本匹配；写侧在算 `cfi` 之前先要求活 Range 取出来的文字**正是**要存的
那段 `quote`，否则不写——这正是 #3 给的第二条处方「回落时就别写 cfi」，且不必新增
一个今天没人走得到的 helper。

**为什么 W-8a 照不出来（审计 #9）。** `baseline_1b/test_w8a_selection_survives_rerender.py`
断的是盘上的 `quote` 与 `position`，而这条缺陷**恰好满足**那两条断言——它坏的是渲染，
不是存储。判据因此必须问屏幕。

**落址：白名单，不是 `baseline_1b`。** 内容上它是 W-8a 家族，但迁进冻结目录会改
`suite_hash` 并把 soak 计数清零。到期条件与当年的 w8a 一样：下一次**本来就要**动
`baseline_1b/` 的改动里把它一并迁入，同批撤掉 `UNGROUPED_E2E_MODULES` 里的条目、
把 `EXPECTED_BASELINE_ITEMS` 加上去。

**三条 epubcfi 字面量是实测值，且每一条都自带「陷阱还在不在」的检查。** 它们由
2026-09-23 的浏览器探针从这两本 fixture 书上算出来。字面量最危险的失效方式不是报错，
而是**悄悄解析不出来**：`rangeFromCfi` 返回 null ⇒ 退回文本匹配 ⇒ 用例照绿，而它
从此什么都没测。所以前两条用例在断言之前，先在页面里确认那条 cfi **今天仍然指向
它该指的错地方**；这一步一旦红，说的是「语料变了，字面量要重算」，不是「产品坏了」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from playwright.sync_api import FrameLocator, Page, expect

from conftest import BOOK_ID, BOOK_ID_REPEAT  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    CH0_ANCHOR,
    open_reader,
    seed_notes,
)

#: `smoke_data` 第 0 章正文是 `<h1>One</h1><p>Alpha prose.</p>`。
QUOTE = "prose"
QUOTE_POSITION = 9

#: 指向同一段里的 `"Alph"`——一条**解析得出来、但指错地方**的 cfi。
CFI_POINTING_ELSEWHERE = "epubcfi(/6/2[c1]!/4/4,/1:0,/1:4)"
TEXT_AT_WRONG_CFI = "Alph"

#: 塌成一个点的 cfi。这正是「用一条已经失效的 Range 算出来的 cfi」最典型的形状：
#: 它不是 null，`extractContents()` 给出空片段，于是屏幕上多一个**空的** `<mark>`。
CFI_COLLAPSED = "epubcfi(/6/2[c1]!/4/4/1:9)"

#: `repeat_data` 第 0 章是同一句话重复 25 遍。`REPEAT_QUOTE` 每一遍里都出现，因此
#: **纯文本匹配必然落在第一次出现**（偏移 36）；下面这条 cfi 指向第 21 次（偏移 1596）。
#: 两条路径给出的**文字一模一样**，只有落点不同——这正是「CFI 重锚是不是还在带路」
#: 唯一测得出来的地方。
REPEAT_QUOTE = "the mast swung across the deck"
REPEAT_CFI_LATE = "epubcfi(/6/2[c1]!/4/2,/1:1596,/1:1626)"
REPEAT_FIRST_OFFSET = 36
REPEAT_LATE_OFFSET = 1596


def _seed_one(books_dir: Path, book_id: str, record: Dict[str, Any]) -> str:
    seed_notes(books_dir, book_id, [record])
    from helpers import read_notes  # type: ignore[import-not-found]

    (landed,) = read_notes(books_dir, book_id)
    assert landed["cfi"] == record["cfi"], f"预置没把 cfi 写进去：{landed}"
    return str(landed["id"])


def _cfi_resolves_to(page: Page, cfi: str) -> str:
    """那条 cfi 在**当前这篇文档**上解析出来的文字；解析不出来时返回一个尖括号标记。

    走 `window.ePub.CFI(...).toRange(doc)`，与 `annotations.js` 的 `rangeFromCfi`
    在这套 bundle 上实际走的是同一条回退路径（`Contents.range` 拿不到，因为
    `getContents()` 给的是 View）。

    **必须在正文还没被标注改动过的时候量。** CFI 是一条结构路径：`render()` 往
    段落里插一个 `<mark>` 就把那个文本节点劈成两半，同一条 cfi 当场解析不出来
    （实测抛异常，返回 `<error>`）。所以陷阱检查要在**盘上还没有那条标注**的那次
    页面加载里做，之后再预置、再进一次。
    """
    return page.evaluate(
        """(cfi) => {
          const view = window.Reader3Epub.getContents();
          const doc = view && view.document;
          if (!doc) return "<no-doc>";
          try {
            const range = new window.ePub.CFI(cfi).toRange(doc);
            return range ? range.toString() : "<unresolvable>";
          } catch (e) {
            return "<error>";
          }
        }""",
        cfi,
    )


def _mark_text(frame: FrameLocator, annotation_id: str) -> str:
    """那条标注在屏幕上罩住的文字（被切成多段时按文档顺序拼起来）。"""
    marks = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{annotation_id}"]')
    expect(marks).not_to_have_count(0)
    return "".join(marks.all_text_contents())


def _mark_offset(page: Page, annotation_id: str) -> int:
    """那条标注的 `<mark>` 落在正文文本轴上的起始偏移。

    `<mark>` 之前的全部文字有多长，它就落在哪里——`Range.toString()` 与
    `buildTextIndex` 一样是把途经的文本节点顺次拼起来，两根轴因此同刻度。
    """
    # 选择器在 Python 这边拼好再递进去：`scripts/lint_e2e_selectors.py` 认的是
    # 一行里完整的 `[data-testid=…][判别位=…]`，在 JS 里用 `+` 拼会把它切成碎片。
    selector = f'[data-testid="rd-anno-span"][data-annotation-id="{annotation_id}"]'
    return page.evaluate(
        """(sel) => {
          const view = window.Reader3Epub.getContents();
          const doc = view.document;
          const mark = doc.querySelector(sel);
          if (!mark) return -1;
          const r = doc.createRange();
          r.setStart(doc.body, 0);
          r.setEndBefore(mark);
          return r.toString().length;
        }""",
        selector,
    )


def test_盘上cfi指向别处时屏幕上罩住的仍是quote那一段(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """`quote` 对、`cfi` 错 ⇒ 屏幕上必须是 `quote` 那一段，不是 cfi 指的那一段。"""
    open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    resolved = _cfi_resolves_to(page, CFI_POINTING_ELSEWHERE)
    assert resolved == TEXT_AT_WRONG_CFI, (
        f"陷阱没装上：{CFI_POINTING_ELSEWHERE} 在这篇文档上解析成 {resolved!r}，"
        f"本该是 {TEXT_AT_WRONG_CFI!r}。语料变了，字面量要重算——"
        "在此之前下面那条断言即使绿也什么都没证明"
    )

    annotation_id = _seed_one(
        e2e_books_dir,
        BOOK_ID,
        {
            "chapter_index": 0,
            "type": "marker",
            "color": "yellow",
            "quote": QUOTE,
            "prefix": "Alpha ",
            "suffix": ".",
            "position": QUOTE_POSITION,
            "cfi": CFI_POINTING_ELSEWHERE,
        },
    )
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    rendered = _mark_text(frame, annotation_id)
    assert rendered == QUOTE, (
        f"盘上 quote={QUOTE!r} 是对的，屏幕上罩住的却是 {rendered!r}——"
        "渲染无条件优先信 cfi，而这条 cfi 指向别处"
    )


def test_盘上cfi塌成一个点时屏幕上罩住的仍是quote那一段(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """塌掉的 cfi 不是 null：它解析得出来，只是零宽。缺陷态下屏幕上是一个**空的** mark。"""
    open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)
    resolved = _cfi_resolves_to(page, CFI_COLLAPSED)
    assert resolved == "", (
        f"陷阱没装上：{CFI_COLLAPSED} 解析成 {resolved!r}，本该是一个零宽 Range。"
        "语料变了，字面量要重算"
    )

    annotation_id = _seed_one(
        e2e_books_dir,
        BOOK_ID,
        {
            "chapter_index": 0,
            "type": "marker",
            "color": "yellow",
            "quote": QUOTE,
            "prefix": "Alpha ",
            "suffix": ".",
            "position": QUOTE_POSITION,
            "cfi": CFI_COLLAPSED,
        },
    )
    frame = open_reader(page, live_server, BOOK_ID, 0, CH0_ANCHOR)

    rendered = _mark_text(frame, annotation_id)
    assert rendered == QUOTE, (
        f"屏幕上罩住的是 {rendered!r}（空串＝一个零宽的 mark），"
        f"盘上 quote 却是 {QUOTE!r}"
    )


def test_cfi与quote对得上时仍然优先按cfi重锚(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """护栏：不许用「把 CFI 分支整个删掉」来换上面两条的绿——那是退化，不是修复。

    `repeat_data` 第 0 章同一句话重复 25 遍。预置那条**不带 prefix/suffix**，所以
    `findRange` 的文本匹配必然落在第一次出现（偏移 36）；而它带的 cfi 指向第 21 次
    （偏移 1596），且取出来的文字与 `quote` 逐字相同。两条路径的**文字**分不出来，
    **落点**分得出来——删掉 CFI 分支，偏移就会从 1596 退回 36，本条当场红。
    """
    open_reader(page, live_server, BOOK_ID_REPEAT, 0, "SENTINEL")
    resolved = _cfi_resolves_to(page, REPEAT_CFI_LATE)
    assert resolved == REPEAT_QUOTE, (
        f"陷阱没装上：{REPEAT_CFI_LATE} 解析成 {resolved!r}，本该是 {REPEAT_QUOTE!r}"
    )

    annotation_id = _seed_one(
        e2e_books_dir,
        BOOK_ID_REPEAT,
        {
            "chapter_index": 0,
            "type": "marker",
            "color": "yellow",
            "quote": REPEAT_QUOTE,
            "prefix": "",
            "suffix": "",
            "position": REPEAT_LATE_OFFSET,
            "cfi": REPEAT_CFI_LATE,
        },
    )
    frame = open_reader(page, live_server, BOOK_ID_REPEAT, 0, "SENTINEL")

    assert _mark_text(frame, annotation_id) == REPEAT_QUOTE
    offset = _mark_offset(page, annotation_id)
    assert offset == REPEAT_LATE_OFFSET, (
        f"那条标注落在偏移 {offset}，应当是 cfi 指的 {REPEAT_LATE_OFFSET}；"
        f"{REPEAT_FIRST_OFFSET} 意味着它退回了纯文本匹配——CFI 重锚已经不带路了"
    )
