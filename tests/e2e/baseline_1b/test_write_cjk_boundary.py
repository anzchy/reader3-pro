r"""WI-8 —— W-9a / W-9b：CJK 书上重复 W-1 与 W-7，卡 quote / prefix / suffix 的多字节边界。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-8（最高权威）。任务书：
`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md` §3 的 W-9 行、
§1「iframe 内建选区的标准路径」与「两套语料（English ＋ CJK）」、§0 的四条写作纪律。

**为什么这不是 W-1 / W-7 的重复。**

落库的 `quote` 由 `annotations.js` 的 `createAnnotation` 用 `idx.text.slice(s, e)` 切出来，
`prefix` / `suffix` 则是 `slice(s - 50, s)` 与 `slice(e, e + 50)`；到了服务端，
`Annotation.__post_init__` 用 `len(self.prefix) > 50` / `self.prefix[-50:]` 再截一次。
**两边数的不是同一个东西**：JS 的 `String.prototype.slice` 数的是 UTF-16 code unit，
Python 的 `len()` 与切片数的是码点。BMP 之内两者恰好一致，所以
`smoke_data`（`Alpha prose` / `Beta prose`）那本书**永远分辨不出**这两种口径——W-1 与 W-7
在字节口径的实现下照样全绿。而 `build_cjk` 的三句里有日文假名（`喫茶店で本を読んでいた`）
与韩文（`커피를 마시며 기다렸다`），正是最容易在编码环节被切错的一段——UTF-8 下每个字符
3 字节，按字节截断会在字符中间下刀。

⚠️ **但 CJK 语料只劈得开「字节 vs 非字节」这一刀，劈不开 code unit 与码点**（009 审计 F1）。
`咖啡館裡` 的三个口径是 **12 / 4 / 4**：UTF-16 code unit 数与码点数**相等**。所以上面那句
「两边数的不是同一个东西」在本模块的前半段里一次都没被证伪过——一个把 `slice` 换成码点
切分的实现，在整本 CJK 书上都是绿的。真正分得开的只有**星平面**（BMP 外）字符：1 码点 =
2 code unit = 4 UTF-8 字节。W-9a 因此在第 2 章注入一段含 `𠮷`（U+20BB7）与 `🍵`（U+1F375）
的文本，把这一刀补上；实测结论有两条，都推翻了本模块早先的说法：

* **`position` 是 UTF-16 code unit 偏移，不是码点偏移**（实测 60，码点口径会是 40）；
* **`slice(s - 50, s)` 的 50 与服务端 `prefix[-50:]` 的 50 不是同一个 50**：前者数 code
  unit，后者数码点。实测落盘 prefix 是 50 code unit / **35 码点**，服务端那一刀因此
  **根本没落下**。

细节与全部字面量见 `ASTRAL_*` 常量上方那一段。

所以本模块把 W-1 与 W-7 各在 CJK 书上重跑一遍，判据改成**逐码点**的：`quote` 的字符数、
`prefix`/`suffix` 的逐字内容、`<mark>` 覆盖文本的逐码点相等。它与 W-1 / W-7 失败的原因
不同——那两条守的是链路本身，本模块守的是链路上的编码口径。

**为什么选区必须取句中。** `build_cjk` 每章只有**一句**（`<p>{句子}</p>`，body 里没有
别的文本节点）。取章首则 `prefix` 天然为空，取章尾则 `suffix` 天然为空，而空串对
「截断口径对不对」这个问题什么都不说——用例当场退化成 W-1 的重复。W-9a 因此取
`他在咖啡館裡等了很久。` 的中段 `咖啡館裡`，让 prefix（`他在`）与 suffix（`等了很久。`）
两侧**都非空**，并各自断成字面量。

**关于全角标点。** `咖啡館裡` 本身不含标点：把句末的 `。` 划进选区就会让 suffix 变空，
两者不可兼得。全角句号落在 `suffix == "等了很久。"` 这条断言里被逐字钉住——它同样穿过
`slice` → JSON → `html.escape/unescape` → 落盘这条完整通路，只是站在 quote 的另一侧。

**与矩阵 §WI-8 的一处出入（2026-09-03 首跑实测）。** 矩阵把 W-9a 的期望写成
`suffix == "等了很久。"`，实测是 `'等了很久。\n'`。差的那个换行**来自语料而非生产代码**：
`tests/fixtures/epub_zip.py` 的 `_xhtml()` 拼的是 `"<body>{body}</body>\n"`，HTML 解析器
会把 `</body>` 之后的文本节点挪回 body 内，于是它进了 `buildTextIndex` 的偏移轴。本模块
按**实测值**钉死（详见 `CJK_CH0_SUFFIX` 的注释）——特征化用例记录的是今天的真实行为；
但这不是放宽：`"等了很久。\n"` 与 `"等了很久。"` 同为逐字判据，少一个全角句号照样红（D7）。

**与 W-9b 的分工**：W-9a 走 POST（新建），判据在 quote/prefix/suffix/position 的切分上；
W-9b 走 PUT（更新），判据在 `note_text` 的往返上——笔记正文本身是 CJK ＋ 假名 ＋ 한글，
覆盖的是「用户输入」这条与选区无关的另一条编码通路。

**生产代码本模块一行未改**（`annotations.js` 的 `createAnnotation`、
`models/annotations.py` 的 `Annotation.__post_init__` 都是被测对象，不是被改对象）。

------------------------------------------------------------------------------
**可失败性证据（§0 第四条纪律，定向破坏实录；D1–D10 为 2026-09-03，D11 为 2026-09-05 补，全部已还原）**
------------------------------------------------------------------------------

本模块两条都是**特征化用例**——被测行为上线数月，红不可得，`tdd-guardian` 的红收据在
这里必然记成 green 并判 `SEPARATION-BROKEN`，成因是「实现早于规格」。§0 第四条纪律因此
明令**不得靠破坏生产代码伪造红**，替代证据是定向破坏**用例自己的期望值**，逐条打靶，
每处留档三样：破坏点、逐字失败输出、还原核验。下表的失败输出全部逐字抄自 pytest。
**D11 是唯一一处改了生产代码行为的**，但它走 Playwright `page.route` 改写**响应体**，
落盘的 `src/` 一字未动——本分支禁止生产改动，`git diff --quiet -- src/` 是硬不变式。

| # | 破坏点（改的都是本文件的期望值，`src/` 一行未动） | 失败输出（逐字） | 它证明了哪一条判据不是摆设 |
|---|---|---|---|
| D1 | `CJK_CH0_QUOTE_CHARS = 4` → `12`（4 个 CJK 字符的 **UTF-8 字节数**） | `AssertionError: '咖啡館裡' 的 UTF-8 字节数与字符数相同，选它测不出「字节 vs 码点」——换一段真正的多字节文本` / `assert 12 != 12` | **元断言**：期望值本身必须能分辨两种口径。把期望值换成字节数，第一个响的是它——这正是它存在的意义 |
| D2 | `CJK_CH0_QUOTE_CHARS = 4` → `3`（绕开 D1 的元断言，直击主判据） | `AssertionError: 落库 quote 的字符数是 4，不是期望的 3。len() 数的是码点：UTF-8 字节数 12、UTF-16 code unit 数 4，三者在 CJK 上互不相等，这条断言只有取码点口径才成立` / `assert 4 == 3` | 「`len(quote)` 数的是**字符数**」。失败消息把三个口径的实测值一并打出来 |
| D3 | `CJK_CH0_POSITION = 2` → `6`（同一段文字的字节偏移） | `AssertionError: 落库的 position 是 2，不是期望的 6。它是 `idx.text.slice` 的起点 s：码点口径下 `他在` 是 2，字节口径下会是 6` / `assert 2 == 6` | 「**偏移**也是码点口径」。quote 全对而 position 按字节算的实现，只有这一条会响 |
| D4 | `CJK_CH0_PREFIX = "他在"` → `""` | `AssertionError: 落库的 prefix 是 '他在'，不是期望的 ''` / `assert '他在' == ''` | 「prefix 逐字相等」 |
| D5 | **把选区从句中挪到章首**：`CJK_CH0_QUOTE = "他在"`、`CHARS = 2`、`POSITION = 0`（prefix/suffix 的期望一个字没改） | `AssertionError: 落库的 prefix 是空的。build_cjk 每章只有一句，章首选区的 prefix 天然为空——空掉说明选区没取到句中，本条退化成 W-1 的重复` / `assert ''` | 「prefix **非空**」这条**不是**摆设，且它响的时候正好说出了本条退化成 W-1 的那句话 |
| D6 | **把选区挪到句尾**：`CJK_CH0_QUOTE = "等了很久。\n"`、`CHARS = 6`、`POSITION = 6`、`PREFIX = "他在咖啡館裡"` | 先红在 `assert_roundtrip` 的 DOM 判据上，**没走到** `assert suffix`：`Error: strict mode violation: get_by_test_id("rd-anno-span") resolved to 2 elements: 1) …>等了很久。</mark> 2) …>↵</mark>` | **没有**证明「suffix 非空」——见下方「D6 的诚实结论」 |
| D7 | `CJK_CH0_SUFFIX` 去掉全角句号（`"等了很久。\n"` → `"等了很久\n"`） | `AssertionError: 落库的 suffix 是 '等了很久。\n'，不是期望的 '等了很久\n'。suffix 取 slice(e, e + 50)（保头），全角句号在这一侧；少一个字说明切分口径变了` | 「suffix 逐字相等」，**且全角标点确实穿过了整条通路**。少一个字符就红 |
| D8 | 「刷新后 `<mark>` 逐码点」那两行的期望改成 `CJK_CH0_QUOTE[:-1]`（少末字「裡」） | `AssertionError: Locator expected to have text '咖啡館'` / `Actual value: 咖啡館裡` | DOM 侧的逐字往返。多吃/少吃一个字符都落在这里 |
| D9 | W-9b 的 `wait_for_note_text(..., W9B_NEW_BODY)` → `W9B_NEW_BODY[:-3]`（少 `한글。`） | `AssertionError: 8.0s 内 wi8-w9b-target-note 的 note_text 没有变成 '新的筆記內容，含日文かな與'，当前是 {…'note_text': '新的筆記內容，含日文かな與한글。'…}` | 笔记正文**落盘**侧的逐码点往返（한글 与全角句号都在判据之内） |
| D11 | **不是改期望值**：`page.route` 把 `annotations.js` 的 `createAnnotation` 换成**码点**算术（`Array.from(idx.text)` 切 quote/prefix/suffix，`position` 改成码点偏移） | `AssertionError: 落库的 position 是 40，不是今天的 60（UTF-16 code unit 口径）…` / `assert 40 == 60` | 星平面那一段的**口径**判据。**同一次破坏下，补它之前的 W-9a 是全绿的**——`咖啡館裡` 的 code unit 数与码点数都是 4，整本 CJK 书分辨不出这两种实现（009 审计 F1） |
| D10 | W-9b 的 `expect(tooltip).to_have_text(W9B_NEW_BODY)` → `W9B_NEW_BODY[:-3]` | `AssertionError: Locator expected to have text '新的筆記內容，含日文かな與'` / `Actual value: 新的筆記內容，含日文かな與한글。` | 笔记正文**读回**侧（tooltip 那条渠道）的逐码点往返 |

**为什么 D9 / D10 只改期望值、不改 `W9B_NEW_BODY` 本身。** 那个常量既是**输入**（填进
textarea）又是**期望**（读回来比对）——改它两侧同步变，用例照样绿，什么都证明不了。
一个「输入即期望」的往返判据，只能靠在**一侧**下刀来证伪。这一点值得写下来，因为它看起来
最像一个可以顺手做的破坏，而它恰恰是无效的那种。

**D6 的诚实结论：`assert suffix`（非空）这一条没能被隔离出来。** 想让 suffix 为空就得把
选区推到章内文本轴的末端，而末端那个 `\n` 在 `</p>` 之外——`AnnotationRenderer` 会把跨块
边界的标注渲成**两个** `<mark>`，于是 `assert_roundtrip` 的 strict 单例判据先红。换句话说，
在这本语料里，任何能让 suffix 变空的选区都会先撞上一条更早的判据。它的孪生判据
`assert prefix` 已由 D5 证明会响，两条形态相同；`assert suffix` 保留为**语料/选区一旦改动
就会响的前置守卫**，而不是一条已被实证过的判据——这一句写在这里，是为了不把它记成已证。

**十处破坏的还原核验，分两件事说清楚（它们证明的东西不同）：**

1. **本模块自身**——每次破坏前先 `cp` 一份副本，破坏、跑、再用副本**整份覆盖回去**，
   还原后重跑均为 `2 passed`。本文件此刻是新增的未跟踪文件，`git diff --stat` 对它
   **恒为空**，拿它当本模块的还原证据是假证据，所以这一侧的证据是副本比对 ＋ 重跑。
2. **别的文件**——全程 `git diff --stat` 输出为空，`git diff --stat -- src/` 同样为空。
   这才是那条命令真正证明的东西：**没有一处破坏落在 `src/` 或任何已跟踪文件上**，
   §0 第四条纪律禁止的「破坏生产代码伪造红」一次都没有发生。
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest
from playwright.sync_api import Page, expect

from conftest import BOOK_ID_CJK  # type: ignore[import-not-found]
from epub_corpus import CJK_SENTENCES  # type: ignore[import-not-found]
from helpers import (  # type: ignore[import-not-found]
    assert_corpus_unchanged,
    assert_roundtrip,
    open_reader,
    read_notes,
    seed_notes,
    select_in_frame,
    wait_for_note_text,
    wait_for_notes,
)

pytestmark = pytest.mark.baseline_1b


# ---------------------------------------------------------------------------
# W-9a 的坐标：CJK 书第 0 章（`build_cjk` 的第一句）
# ---------------------------------------------------------------------------
#
# 三个期望值全写成字面量（§0 第五条纪律）。它们**不是**从 `CJK_SENTENCES[0]` 切出来的：
# 从同一个源头切出期望值，等于拿运行期读到的值比运行期读到的值，语料一改这里跟着改，
# 断言永远绿。写死之后，「选区滑了一个字」在失败消息里是一个人能一眼认出的字面量。
#
# 下面那句 `assert_corpus_unchanged(*CORPUS_CHECKS)` 是**另一回事**：它不参与判据，只在语料被改动时
# 把失败点从 `select_in_frame: 章内找不到 …` 提前到一句说得清的话。

#: 到位探针（`open_reader` 的 `expect_text`）。含全角句号，与 quote 的用途相反——
#: 它要的是「这一章确实渲染出来了」，所以取整句。
CJK_CH0_ANCHOR = "他在咖啡館裡等了很久。"

#: 选区。**句中**四个字，两侧各留下非空的上下文。见模块 docstring「为什么选区必须取句中」。
CJK_CH0_QUOTE = "咖啡館裡"

#: `len(quote)`，**字符数**。同一段文字的 UTF-8 字节数是 12、UTF-16 code unit 数是 4——
#: 写死 4 就是在这三个口径之间做选择，而不是记录一个碰巧的数。
CJK_CH0_QUOTE_CHARS = 4

#: `createAnnotation` 的 `idx.text.slice(max(0, s - 50), s)`：保尾。本章 quote 之前只有
#: 两个字，远不到 50，所以整段都在。
CJK_CH0_PREFIX = "他在"

#: `idx.text.slice(e, min(len, e + 50))`：保头。全角句号在这一侧。
#:
#: ⚠️ **末尾那个 `\n` 是实测出来的，不是笔误，也不是可以省掉的空白。** 矩阵 §WI-8 预测
#: 本值为 `"等了很久。"`，2026-09-03 首跑实测为 `'等了很久。\n'`。成因在**语料**而不在
#: 生产代码：`tests/fixtures/epub_zip.py` 的 `_xhtml()` 拼的是 `"<body>{body}</body>\n"`，
#: 而 HTML 解析器会把 `</body>` 之后的那个换行文本节点**挪回 body 内部**；
#: `buildTextIndex` 用 TreeWalker 扫 body 的全部文本节点，于是它进了偏移轴。
#: W-1 / W-2 / W-3 看不到这一点，因为它们的 quote（`Alpha prose`）后面还有一个 `.`，
#: 而它们本来也不断 suffix。
#:
#: 按实测值钉死，**不是**放宽成 `startswith`：`"等了很久。\n"` 与 `"等了很久。"` 一样是
#: 逐字判据，少一个全角句号照样红（见 docstring 的 D7 —— 那一处正是把本常量末尾的全角
#: 句号去掉，用例当场红）。改成 `rstrip()` 或前缀匹配才是
#: 放宽——那会让「suffix 末尾多吃/少吃字符」这一整类切分缺陷从判据里消失。
CJK_CH0_SUFFIX = "等了很久。\n"

#: `position` 就是 `s`，即 quote 在**章内连续文本轴**上的起点。码点口径下是 2
#: （`他在` 两个字符），字节口径下会是 6。这条与 `CJK_CH0_QUOTE_CHARS` 互补：
#: 前者钉长度的口径，它钉**偏移**的口径。
CJK_CH0_POSITION = 2


# ---------------------------------------------------------------------------
# W-9b 的坐标：CJK 书第 1 章（日文那一句）
# ---------------------------------------------------------------------------

CJK_CH1_ANCHOR = "彼女は喫茶店で本を読んでいた。"

#: 句中五个字符，混了汉字与平假名（`で`）。选它而不是纯汉字段，是因为假名与汉字在
#: UTF-8 下同为 3 字节、在 UTF-16 下同为 1 code unit，但在**任何按字节下刀**的实现里
#: 会切在不同的地方——混排段落是这类缺陷最先显形的形状。
CJK_CH1_QUOTE = "喫茶店で本"

#: 目标条的 id 与 created_at 写死（§0 第五条纪律）：守恒律断的正是「它们没变」，
#: 让 `seed_notes` 生成随机 uuid 与「此刻」的话，断言就只能自己比自己。
W9B_TARGET_ID = "wi8-w9b-target-note"
W9B_CREATED_AT = "2026-01-01T00:00:00+00:00"

#: 旧正文纯简体，新正文混了繁体、全角逗号句号、日文平假名（`かな`）与韩文（`한글`）。
#: **刻意不含 `<` / `&` / `"`**：服务端 POST 时 `html.escape`、GET 时 `html.unescape`，
#: 带元字符会把本条变成一条转义往返用例，而转义有它自己的地方（contract lane）。
#: 本条要断的是**编码**往返，两件事不该在同一条判据里纠缠。
W9B_OLD_BODY = "旧的笔记内容"
W9B_NEW_BODY = "新的筆記內容，含日文かな與한글。"


# ---------------------------------------------------------------------------
# 星平面（BMP 之外）坐标：把「JS 数 UTF-16 code unit / Python 数码点」真正劈开
# ---------------------------------------------------------------------------
#
# **为什么必须补这一段（009 审计 F1）。** 本模块原先只有 `咖啡館裡` 一段语料，而它的
# 三个口径是 **12 / 4 / 4**——UTF-8 字节 12、UTF-16 code unit 4、码点 4。**后两者相等。**
# 于是模块 docstring 里那句「JS 的 slice 数 code unit、Python 的 len 数码点，两者分家」
# 在整个模块里**一次都没有被测到**：BMP 之内它们恒等，任何把 `slice` 换成码点切分的实现
# 都照样全绿。原先 `len(quote)` 那条断言的失败消息还写着「三者互不相等」，那句话对
# `咖啡館裡` 是**错的**（4 == 4）。真正能分家的只有星平面字符：每个占 **2 个** UTF-16
# code unit、**1 个**码点。
#
# 语料从哪来：CJK 书的三句都太短（11 / 15 / 13 字符），凑不出 50 code unit 的上下文窗口，
# 而 `tests/fixtures/**` 本波不归本模块改。所以本条在**第 2 章**（韩文那句，W-9b 用的是
# 第 1 章，互不打扰）的 body 开头**注入一个 `<p>`**，注入的文本全部写成下面这些字面量。
# 注入不是伪造：`buildTextIndex` 读的就是活的 DOM，`createAnnotation` 在注入后的轴上算出
# 来的 `position` / `prefix` / `suffix` 与真语料上算出来的走的是同一段代码。
#
# 代价写在明处：注入的段落**活不过 `page.reload()`**，所以星平面这一段只断**写路径**
# （落盘的 quote/position/prefix/suffix）与**刷新前**的那一次渲染，不做刷新往返。刷新往返
# 由上面 BMP 那一半（`assert_roundtrip`）覆盖，两半各管一件事。

#: 第 2 章的到位探针。也进 `CORPUS_CHECKS`——星平面那一段要逐字断整条文本轴。
CJK_CH2_ANCHOR = "커피를 마시며 기다렸다."

#: U+20BB7（罕用汉字「𠮷」）与 U+1F375（🍵）都在星平面：**1 个码点 = 2 个 UTF-16 code
#: unit = 4 个 UTF-8 字节**。挑这两个而不是随便一个 emoji，是因为它们一个是汉字一个是符号，
#: 覆盖了「罕用汉字」与「emoji」两类真实输入，而且都与本书的咖啡/茶主题对得上。
ASTRAL_HAN = "\U00020BB7"
ASTRAL_EMOJI = "\U0001F375"

#: 选区。三个口径 **11 / 5 / 3**（UTF-8 字节 / UTF-16 code unit / 码点），**两两不等**
#: ——这正是 `咖啡館裡` 做不到的事。混一个 BMP 汉字「茶」进去，是为了让「实现按固定倍数
#: 换算」（比如「码点数 = code unit 数 ÷ 2」）也当场错。
ASTRAL_QUOTE = ASTRAL_HAN + ASTRAL_EMOJI + "茶"

#: quote 之前的引文：20 个星平面汉字（40 code unit / 20 码点）＋ 20 个 BMP 汉字
#: （20 code unit / 20 码点）＝ **60 code unit / 40 码点**。
#: 60 > 50，所以 `slice(s - 50, s)` 这一刀**真的落在这段里**，而不是「整段都在」。
ASTRAL_LEAD = ASTRAL_HAN * 20 + "文" * 20

#: quote 之后的引文，对称构造：20 个 emoji ＋ 20 个 BMP 汉字 ＝ 60 code unit / 40 码点。
ASTRAL_TRAIL = ASTRAL_EMOJI * 20 + "字" * 20

#: 注入进第 2 章 body 开头的整段文本。
ASTRAL_PARAGRAPH = ASTRAL_LEAD + ASTRAL_QUOTE + ASTRAL_TRAIL

#: `position` 就是 `idx.text.slice` 的起点 `s`。**实测 60，也就是 UTF-16 code unit 口径**
#: ——同一个位置的**码点**偏移是 40。这条是本模块最要紧的一个特征化结论：
#: 模块 docstring 早先把 `position` 说成「码点口径」，那句话在 BMP 语料上无法证伪，
#: 一到星平面就是错的。今天的行为是 code unit，这里按今天的行为钉死。
#: 哪天有人把 `createAnnotation` 改成码点口径，本条当场红在 60 != 40 上——**那是正确的红**。
ASTRAL_POSITION_UTF16 = 60
ASTRAL_POSITION_CODEPOINTS = 40

#: `slice(s - 50, s)` 切的是 **50 个 code unit**：从 60 往回数 50 个 code unit，落在星平面
#: 汉字串的第 10 个 code unit 上（10 是偶数 ⇒ 正好在字符边界，不劈开代理对），于是留下
#: **15 个**星平面汉字 ＋ 20 个 BMP 汉字 = **35 码点 / 50 code unit**。
#:
#: 服务端 `Annotation.__post_init__` 的 `if len(self.prefix) > 50: self.prefix[-50:]`
#: 数的是**码点**：35 > 50 为假，**那一刀根本没落下**。所以落盘 prefix 的码点数是 35 而不是
#: 50——「两处 50 是同一个 50」这个想当然的读法，在星平面上是错的，这两个常量把它钉死。
ASTRAL_PREFIX = ASTRAL_HAN * 15 + "文" * 20
ASTRAL_PREFIX_CODEPOINTS = 35
ASTRAL_PREFIX_UTF16_UNITS = 50

#: `slice(e, e + 50)` 同理，保头：20 个 emoji（40 code unit）＋ 10 个 BMP 汉字 =
#: **30 码点 / 50 code unit**。同样没触发服务端的 `[:50]`。
ASTRAL_SUFFIX = ASTRAL_EMOJI * 20 + "字" * 10
ASTRAL_SUFFIX_CODEPOINTS = 30
ASTRAL_SUFFIX_UTF16_UNITS = 50

#: ⚠️ **一个明确的欠账，写在这里免得被当成已覆盖**：上面两刀都**恰好落在字符边界上**
#: （回退 50 个 code unit 时下标是偶数）。把引文的长度挪动一个 code unit，那一刀就会
#: **劈开一个代理对**，`slice` 会切出一个孤代理；孤代理编不成 UTF-8，`JSON.stringify` →
#: 服务端 `json` → `notes.json` 落盘这条链上会发生什么，本模块**没有测**，也不敢在
#: `baseline_1b` 里随手试——它可能是一个真缺陷（服务端 500），而本分支禁止改生产代码。
#: 要覆盖它得单开一条，且先决定「今天的行为」是不是可接受的行为。

_ASTRAL_INJECT_JS = r"""
(body, text) => {
  const doc = body.ownerDocument;
  const p = doc.createElement("p");
  p.textContent = text;
  body.insertBefore(p, body.firstChild);
  // 回读整条文本轴：`buildTextIndex` 用的就是这个 TreeWalker 口径，
  // 注入到底落在轴的哪个位置，由调用方逐字断，而不是由这里「大概应该对」。
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  let axis = "";
  while (walker.nextNode()) axis += walker.currentNode.data;
  return axis;
}
"""


def _counts(text: str) -> Tuple[int, int, int]:
    """`(UTF-8 字节数, UTF-16 code unit 数, 码点数)`——三种口径一次量齐。

    失败消息里把三个数一起打出来，是本模块唯一能让「切错口径」这类缺陷一眼可读的形式。
    """
    return (
        len(text.encode("utf-8")),
        len(text.encode("utf-16-le")) // 2,
        len(text),
    )


#: 语料绊线（喂给 `helpers.assert_corpus_unchanged`）。**这不是判据，是诊断**。
#:
#: `build_cjk` 的三句写在 `tests/fixtures/epub_corpus.py`，本模块把其中两句抄成了
#: 字面量。抄本与原本分家时，真正的失败点在 `select_in_frame` 里，报出来的是
#: 「章内找不到 '咖啡館裡'（body 文本 11 字符，开头 …）」——正确，但要读三层才明白。
#: 先在这里说清楚。
#:
#: 反过来，**不能**用 `CJK_SENTENCES[0]` 直接派生期望值：那样语料一改期望值跟着改，
#: 「选区滑了一个字」这类缺陷就再也不会红（§0 第五条纪律）。
CORPUS_CHECKS = (
    (
        CJK_SENTENCES[0],
        CJK_CH0_ANCHOR,
        f"语料第一句变了：{CJK_SENTENCES[0]!r} != {CJK_CH0_ANCHOR!r}。"
        "本模块的 quote / prefix / suffix 三个字面量都是从这一句上量出来的，要一起改。",
    ),
    (
        CJK_SENTENCES[1],
        CJK_CH1_ANCHOR,
        f"语料第二句变了：{CJK_SENTENCES[1]!r} != {CJK_CH1_ANCHOR!r}。",
    ),
    (
        CJK_SENTENCES[2],
        CJK_CH2_ANCHOR,
        f"语料第三句变了：{CJK_SENTENCES[2]!r} != {CJK_CH2_ANCHOR!r}。"
        "W-9a 的星平面那一段把注入段落之后的文本轴逐字断成 "
        "`ASTRAL_PARAGRAPH + CJK_CH2_ANCHOR + chr(10)`，这一句改了那条断言要一起改。",
    ),
)


def test_w9a_cjk_marker_keeps_quote_prefix_suffix_on_codepoint_boundaries(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-9a（S2，多字节边界等价类）：CJK 书上创建 marker → 刷新 → 逐码点往返。

    链路与 W-1 同构（选区 → `rd-anno-type-marker` → `createAnnotation` →
    `POST /api/notes/{book}/{chapter}` → 刷新 → `<mark>`），换的只有语料与判据口径。
    W-1 走真实鼠标拖选、本条走 `select_in_frame` 的程序化路径：拖选全表只留 W-1 那一条
    smoke（任务书 §1），而本条要断的是编码，与选区**怎么产生**无关。

    四条判据，缺一条就有一个具体的坏实现能全绿：

      1. `quote` 逐码点相等 ＋ 字符数 == 4  ⇒ 缺了，按字节切的实现（切出 12 字节 / 半个
         字符）在 quote 这一侧不显形；
      2. `position == 2`                    ⇒ 缺了，偏移量按字节算（6）照样绿——落库的
         quote 是对的，错的是它自称在哪；
      3. `prefix == "他在"` 且**非空**       ⇒ 缺了，本条与 W-1 同构（`build_cjk` 每章
         只有一句，章首选区的 prefix 天然为空）；
      4. `suffix == "等了很久。"` 且**非空** ⇒ 同上，且全角句号的往返没人管。

    第 5 条在 `assert_roundtrip` 里：刷新后 `<mark>` 覆盖的文本逐字等于选中的那一段，
    且终态恰好 1 条。本条在它之外再显式比一次**码点序列**——`==` 在 Python 里对
    NFC/NFD 不同规范化形式的字符串会判不等，而 `list(...)` 的失败消息会把是哪一个码点
    不同直接指出来，这在 CJK 上比一条「两个看起来一样的串不相等」有用得多。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)
    assert read_notes(e2e_books_dir, BOOK_ID_CJK) == [], "隔离 fixture 没生效：起点不是空的"

    # 期望值本身的元断言：字符数与字节数必须不同，否则第 1 条判据分辨不出两种口径。
    assert len(CJK_CH0_QUOTE.encode("utf-8")) != CJK_CH0_QUOTE_CHARS, (
        f"{CJK_CH0_QUOTE!r} 的 UTF-8 字节数与字符数相同，选它测不出「字节 vs 码点」——"
        "换一段真正的多字节文本"
    )
    # 上面那条只劈开「字节 vs 码点」。把 BMP 语料的三个口径全量到手，钉死后两个**相等**：
    # 这不是一条会红的判据，是一条**说明**——它当场写出「本段语料分辨不了 code unit 与
    # 码点」这件事，从而说明为什么本条后半段非补星平面不可（009 审计 F1）。
    assert _counts(CJK_CH0_QUOTE) == (12, 4, 4), (
        f"{CJK_CH0_QUOTE!r} 的三个口径实测是 {_counts(CJK_CH0_QUOTE)}，不是记录在案的 (12, 4, 4)。"
        "语料换过了？换之前先确认新语料在 BMP 之内——本条的整段注释建立在「后两者相等」上"
    )

    frame = open_reader(page, live_server, BOOK_ID_CJK, 0, CJK_CH0_ANCHOR)

    select_in_frame(frame, CJK_CH0_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()

    record = assert_roundtrip(
        page,
        e2e_books_dir,
        BOOK_ID_CJK,
        CJK_CH0_QUOTE,
        CJK_CH0_ANCHOR,
        expected_type="marker",
    )

    # --- 判据 1：quote 逐码点 + 字符数 ---------------------------------------
    quote = record["quote"]
    assert list(quote) == list(CJK_CH0_QUOTE), (
        f"落库的 quote 逐码点不等于选中的那一段：{list(quote)} != {list(CJK_CH0_QUOTE)}"
    )
    assert len(quote) == CJK_CH0_QUOTE_CHARS, (
        f"落库 quote 的字符数是 {len(quote)}，不是期望的 {CJK_CH0_QUOTE_CHARS}。"
        f"len() 数的是码点；本段的三个口径（UTF-8 字节 / UTF-16 code unit / 码点）实测是 "
        f"{_counts(quote)}——**字节数**与另外两个分家，而 code unit 与码点在 BMP 之内恒等，"
        "这一条只分辨得出「字节 vs 非字节」。code unit 与码点的分家由本条后半段的星平面语料断"
    )

    # --- 判据 2：position 也是码点偏移 ---------------------------------------
    assert record["position"] == CJK_CH0_POSITION, (
        f"落库的 position 是 {record['position']}，不是期望的 {CJK_CH0_POSITION}。"
        "它是 `idx.text.slice` 的起点 s：`他在` 在 UTF-16 code unit 与码点两种口径下同为 2"
        "（都在 BMP 内），字节口径下会是 6。**这一条只排除得掉字节口径**——code unit 与码点"
        "的分家由本条后半段的星平面语料断（`ASTRAL_POSITION_UTF16`）"
    )

    # --- 判据 3 / 4：prefix、suffix 都非空且逐字正确 --------------------------
    prefix, suffix = record["prefix"], record["suffix"]
    assert prefix, (
        "落库的 prefix 是空的。`build_cjk` 每章只有一句，章首选区的 prefix 天然为空——"
        "空掉说明选区没取到句中，本条退化成 W-1 的重复"
    )
    assert suffix, (
        "落库的 suffix 是空的。同理，句尾选区的 suffix 天然为空——本条要求两侧都有上下文"
    )
    assert prefix == CJK_CH0_PREFIX, (
        f"落库的 prefix 是 {prefix!r}，不是期望的 {CJK_CH0_PREFIX!r}。"
        "prefix 取 `slice(max(0, s - 50), s)`（保尾），"
        "服务端再按 `self.prefix[-50:]` 截一次——两处都必须是码点口径"
    )
    assert suffix == CJK_CH0_SUFFIX, (
        f"落库的 suffix 是 {suffix!r}，不是期望的 {CJK_CH0_SUFFIX!r}。"
        "suffix 取 `slice(e, e + 50)`（保头），全角句号在这一侧；少一个字说明切分口径变了"
    )

    # --- 判据 5：刷新后 `<mark>` 覆盖的文本，逐码点 ---------------------------
    # `assert_roundtrip` 已经断过一次 `text_content() == quote`。这里再比一次**码点
    # 序列**：`==` 对 NFC/NFD 两种规范化形式判不等，而失败消息只会说「两个看起来一样的
    # 串不相等」。`list(...)` 会直接指出是哪一个码点不同。
    # 判别位 `data-annotation-id` 在 ADR-0014 的闭合清单内。
    note_id = str(record["id"])
    mark = frame.locator(f'[data-testid="rd-anno-span"][data-annotation-id="{note_id}"]')
    expect(mark).to_have_text(CJK_CH0_QUOTE)
    assert list(mark.text_content() or "") == list(CJK_CH0_QUOTE), (
        f"刷新后 `<mark>` 覆盖的文本逐码点不等于选中的 {CJK_CH0_QUOTE!r}："
        f"{list(mark.text_content() or '')}"
    )

    # ======================================================================
    # 判据 6–9：星平面语料。上面全部判据在 BMP 之内，测不出 code unit ≠ 码点
    # ======================================================================
    # 见 `ASTRAL_*` 常量上方那一大段：`咖啡館裡` 的 code unit 数与码点数都是 4，
    # 所以「JS slice 数 code unit / Python len 数码点」这条模块级论断在上半段一次都
    # 没被证伪过。下面这一段是本模块唯一劈得开这两者的地方（009 审计 F1）。
    assert len(set(_counts(ASTRAL_QUOTE))) == 3, (
        f"{ASTRAL_QUOTE!r} 的三个口径是 {_counts(ASTRAL_QUOTE)}，其中有两个相等——"
        "这样的语料分辨不出三种口径中的某一对，本段的全部判据都会退化。"
        "选区必须同时含星平面字符（1 码点 = 2 code unit = 4 字节）与 BMP 字符"
    )
    assert _counts(ASTRAL_QUOTE) == (11, 5, 3), (
        f"{ASTRAL_QUOTE!r} 的三个口径实测 {_counts(ASTRAL_QUOTE)}，不是记录在案的 (11, 5, 3)。"
        "常量被改过了？下面 position / prefix / suffix 三个字面量都是按这个构造算出来的"
    )

    frame = open_reader(page, live_server, BOOK_ID_CJK, 2, CJK_CH2_ANCHOR)
    axis = frame.locator("body").evaluate(  # lint-e2e-selectors: allow —— iframe 内是用户那本书自己的 XHTML，不是我们的模板
        _ASTRAL_INJECT_JS, ASTRAL_PARAGRAPH
    )
    assert axis == ASTRAL_PARAGRAPH + CJK_CH2_ANCHOR + "\n", (
        "注入后的章内文本轴不是 `注入段落 + 第三句 + 换行`，实测 "
        f"{axis!r}。轴一旦不是这个形状，下面的 position / prefix / suffix 三个字面量就全部失准"
    )

    select_in_frame(frame, ASTRAL_QUOTE)
    page.get_by_test_id("rd-anno-type-marker").click()

    landed = wait_for_notes(e2e_books_dir, BOOK_ID_CJK, 2)
    astral_records = [r for r in landed if r["quote"] == ASTRAL_QUOTE]
    assert len(astral_records) == 1, (
        f"落库里 quote == {ASTRAL_QUOTE!r} 的不是恰好一条，而是 {len(astral_records)} 条："
        f"{landed}"
    )
    astral_record = astral_records[0]

    # --- 判据 6：星平面 quote 逐码点往返 --------------------------------------
    assert list(astral_record["quote"]) == list(ASTRAL_QUOTE), (
        f"落库的星平面 quote 逐码点不等于选中的那一段：{list(astral_record['quote'])} != "
        f"{list(ASTRAL_QUOTE)}。代理对被劈开时，这里会出现孤代理"
    )
    assert _counts(astral_record["quote"]) == (11, 5, 3), (
        f"落库的星平面 quote 三个口径是 {_counts(astral_record['quote'])}，不是 (11, 5, 3)"
    )

    # --- 判据 7：position 是 **UTF-16 code unit** 偏移，不是码点偏移 -----------
    # 这一条是本模块最要紧的特征化结论，它推翻了 docstring 早先「position 是码点口径」的说法
    # ——那句话在 BMP 语料上无法证伪。今天的行为是 code unit（60），码点口径会是 40。
    assert ASTRAL_POSITION_UTF16 != ASTRAL_POSITION_CODEPOINTS, (
        "两个期望值相等 ⇒ 这段引文根本分不开两种口径，判据 7 退化成空转"
    )
    assert astral_record["position"] == ASTRAL_POSITION_UTF16, (
        f"落库的 position 是 {astral_record['position']}，不是今天的 "
        f"{ASTRAL_POSITION_UTF16}（UTF-16 code unit 口径）。"
        f"若它变成 {ASTRAL_POSITION_CODEPOINTS}，说明 `createAnnotation` 的偏移改成了**码点**"
        "口径——那是一次行为变更，本条要随之改判，不是把断言放宽"
    )

    # --- 判据 8 / 9：50 那一刀切的是 code unit，服务端的 50 数的是码点 ---------
    # 两处 50 不是同一个 50。JS `slice(s - 50, s)` 回退 50 个 code unit，落盘时
    # `Annotation.__post_init__` 的 `len(prefix) > 50` 数的是码点（35 / 30，都不超）——
    # 于是服务端那一刀**根本没落下**。BMP 语料上这两个 50 恒等，永远看不出来。
    astral_prefix, astral_suffix = astral_record["prefix"], astral_record["suffix"]
    assert astral_prefix == ASTRAL_PREFIX, (
        f"落库的星平面 prefix 是 {astral_prefix!r}，不是期望的 {ASTRAL_PREFIX!r}"
    )
    assert astral_suffix == ASTRAL_SUFFIX, (
        f"落库的星平面 suffix 是 {astral_suffix!r}，不是期望的 {ASTRAL_SUFFIX!r}"
    )
    assert (len(astral_prefix), _counts(astral_prefix)[1]) == (
        ASTRAL_PREFIX_CODEPOINTS,
        ASTRAL_PREFIX_UTF16_UNITS,
    ), (
        f"落库 prefix 的 (码点数, code unit 数) 是 "
        f"({len(astral_prefix)}, {_counts(astral_prefix)[1]})，不是今天的 "
        f"({ASTRAL_PREFIX_CODEPOINTS}, {ASTRAL_PREFIX_UTF16_UNITS})。"
        "码点数变成 50 ⇒ 上游那一刀改成按码点回退了；code unit 数不再是 50 ⇒ 切的位置变了"
    )
    assert (len(astral_suffix), _counts(astral_suffix)[1]) == (
        ASTRAL_SUFFIX_CODEPOINTS,
        ASTRAL_SUFFIX_UTF16_UNITS,
    ), (
        f"落库 suffix 的 (码点数, code unit 数) 是 "
        f"({len(astral_suffix)}, {_counts(astral_suffix)[1]})，不是今天的 "
        f"({ASTRAL_SUFFIX_CODEPOINTS}, {ASTRAL_SUFFIX_UTF16_UNITS})"
    )

    # --- 星平面这一半**不断渲染**，以及为什么（实测，不是省略） -----------------
    #
    # 首版本条在这里断过「刷新前的那一次重绘也画得出 `<mark>`」，实测**画不出**。原因
    # 查清了，且与星平面无关：注入的 `<p>` 只在浏览器 DOM 里，`book.pkl` 里没有这段文字。
    # 服务端 `GET /api/notes/{book}/{chapter}` 会先跑 `_refresh_orphaned_annotations`
    # ——在章节正文里找不到 quote 的标注被判为 **orphaned** 并从返回值里滤掉。实测
    # `GET /api/notes/cjk_data/2` 返回 `count: 0`（落盘那条 `chapter_index` 确实是 2），
    # 于是 `loadAndRender()` 拿到空列表，一个 `<mark>` 都不画。**这是正确的服务端行为**：
    # 一段书里根本不存在的引文，本来就该判成孤儿。
    #
    # 所以星平面这一半的覆盖面写在明处：**只覆盖写路径**（`createAnnotation` 的
    # slice 口径 → POST → 落盘）。渲染与刷新往返由本条前半段的 BMP 语料 ＋
    # `assert_roundtrip` 覆盖，两半各管一件事，谁都不假装管了对方那件事。
    #
    # 下面这条不是「省略」，是把上面那段解释变成一条**会红的**判据：孤儿过滤一旦改掉，
    # 这里立刻红，读到的人会被带到这段注释上，而不是对着一句没人验证过的解释发呆。
    expect(frame.get_by_test_id("rd-anno-span")).to_have_count(0)


def test_w9b_cjk_note_body_survives_edit_and_reload(
    page: Page, live_server: str, e2e_books_dir: Path
) -> None:
    """W-9b（S5，往返不变式）：CJK 书上编辑笔记，正文本身也是 CJK ＋ 假名 ＋ 한글。

    链路与 W-7 同构（点 `<mark>` → `onAnnotationClick` → `openNoteEditorWithExisting`
    → 改文本 → `saveNote()` 的**更新**分支 → `PUT /api/notes/{book}/{chapter}/{id}`），
    换的是语料与正文。**它测的不是 W-7 那条链**——W-7 守的是更新守恒律（id / created_at /
    基数 / 旁观条），本条守的是 `note_text` 这个**用户输入**串在
    `textarea → JSON → html.escape → 落盘 → html.unescape → tooltip / 面板` 这一整圈里
    逐码点不变。两者失败的原因不同：把服务端的 escape/unescape 换成按字节处理，W-7 全绿
    （`old body` / `new body` 是纯 ASCII），本条红。

    **为什么在第 1 章而不是第 0 章。** 第 1 章是日文那句（`彼女は喫茶店で本を読んでいた。`），
    平假名与汉字混排；同时 `chapter_index=1` 让 PUT 的章号不是 `Annotation.chapter_index`
    的默认值 0——章号写错时这条会红，而在第 0 章上它恒真。（章号本身的完整覆盖是 K-6a／
    WI-9 的事，本条只是顺带不让它退化。）

    **只有一条标注，所以不传 `expected_count`。** 旁观条守恒是 W-7 的判据（那里有
    两条同章标注），在这里加一条旁观标注只会重复 W-7 已经钉住的东西，还要多付一次渲染。

    编辑态不会被那个 ~250ms 自持循环打掉——理由与实测证据在
    `tests/e2e/helpers.py` 的 `select_in_frame` docstring 里（`openNoteEditorWithExisting`
    末尾的 `focus()` 把选区折叠，epub.js 的 `selected` 不再 emit）。本条因此不加任何
    sleep、不加重试。
    """
    assert_corpus_unchanged(*CORPUS_CHECKS)

    seed_notes(
        e2e_books_dir,
        BOOK_ID_CJK,
        [
            {
                "id": W9B_TARGET_ID,
                "chapter_index": 1,
                "type": "note",
                "color": "yellow",
                "quote": CJK_CH1_QUOTE,
                "note_text": W9B_OLD_BODY,
                "created_at": W9B_CREATED_AT,
            }
        ],
    )
    before = read_notes(e2e_books_dir, BOOK_ID_CJK)
    assert [r["id"] for r in before] == [W9B_TARGET_ID], f"预置没落对：{before}"
    assert before[0]["note_text"] == W9B_OLD_BODY, (
        f"预置的 note_text 落盘后是 {before[0]['note_text']!r}，不是 {W9B_OLD_BODY!r}——"
        "起点就不对的话，后面「改成新值」那条断言证明不了是编辑起的作用"
    )

    frame = open_reader(page, live_server, BOOK_ID_CJK, 1, CJK_CH1_ANCHOR)

    target_mark = frame.locator(
        f'[data-testid="rd-anno-span"][data-annotation-id="{W9B_TARGET_ID}"]'
    )
    # 预置条的高亮必须先落在**正确的那段 CJK 文字**上，否则下面点开的编辑器是别处的。
    expect(target_mark).to_have_text(CJK_CH1_QUOTE)
    target_mark.click()

    # 编辑器带着**旧正文**打开，才说明走的是 `openNoteEditorWithExisting`（置了
    # `editingNoteId`）而不是 `openNoteEditor`。两者都会让编辑器可见，只有 textarea
    # 的初值能把它们分开——顺带这也是 CJK 正文的第一次读回（GET → textarea）。
    editor_input = page.get_by_test_id("rd-note-editor-input")
    expect(page.get_by_test_id("rd-note-editor")).to_be_visible()
    expect(editor_input).to_have_value(W9B_OLD_BODY)

    editor_input.fill(W9B_NEW_BODY)
    page.get_by_test_id("rd-note-editor-primary").click()

    # 等在**被改的那个量**上：PUT 不改条数，等条数会立刻带着旧正文返回（helpers 里写了理由）。
    updated = wait_for_note_text(e2e_books_dir, BOOK_ID_CJK, W9B_TARGET_ID, W9B_NEW_BODY)
    assert list(updated["note_text"]) == list(W9B_NEW_BODY), (
        f"盘上的 note_text 逐码点不等于填进去的那一段：{list(updated['note_text'])}"
    )

    record = assert_roundtrip(
        page,
        e2e_books_dir,
        BOOK_ID_CJK,
        CJK_CH1_QUOTE,
        CJK_CH1_ANCHOR,
        expected_type="note",
    )
    assert record["id"] == W9B_TARGET_ID, (
        f"往返回来的目标条 id 是 {record['id']!r}，不是预置的 {W9B_TARGET_ID!r}——"
        "更新分支变成了「删了重建」"
    )
    assert record["created_at"] == W9B_CREATED_AT, (
        f"目标条的 created_at 变了：{W9B_CREATED_AT!r} → {record['created_at']!r}。"
        "改内容不该重置创建时间"
    )

    # --- 读回渠道 (b)：iframe 内 hover `<mark>` → 外层 tooltip -----------------
    tooltip = page.get_by_test_id("rd-note-tooltip")
    assert tooltip.text_content() == "", (
        f"hover 之前 tooltip 就已经有文本 {tooltip.text_content()!r}——"
        "下面那句「hover 之后有新正文」会因此恒真，先在这里拦下来"
    )
    target_mark.hover()
    expect(tooltip).to_have_text(W9B_NEW_BODY)
    assert list(tooltip.text_content() or "") == list(W9B_NEW_BODY), (
        f"tooltip 的文本逐码点不等于新正文：{list(tooltip.text_content() or '')}"
    )

    # --- 读回渠道 (a)：Notes 面板 --------------------------------------------
    # 另一个端点（`GET /api/notes/{book}`）、另一套摘要逻辑、另一处 `html.unescape`：
    # 盘上对了不代表这里对。放最后，因为面板是覆盖整屏的浮层，先开它会挡住上面那次 hover。
    page.get_by_test_id("rd-rail-notes").click()
    item = page.locator(f'[data-testid="rd-notes-item"][data-note-id="{W9B_TARGET_ID}"]')
    expect(item).to_contain_text(W9B_NEW_BODY)
    assert W9B_OLD_BODY not in (item.text_content() or ""), (
        f"Notes 面板里还留着旧正文 {W9B_OLD_BODY!r}：{item.text_content()!r}"
    )
