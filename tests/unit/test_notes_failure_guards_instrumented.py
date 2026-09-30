"""009 欠账 #43 part (i) WI-6 · W6-C6：十个已识别的「请求前失败守卫」各自保有诊断上报。

**它守的是什么。** `annotations.js` 写路径上有十个出口在**发请求之前**就放弃了：没选区、没书章
上下文、没有可删的 id、空正文、没有待决冲突……WI-6 让它们每一个都经
`reportNotesWriteFailure({op, requested: false, …})` 说话。Playwright 用例（W6-C1/C4/C5）验的是
它们**现在**的可观测行为；本条是一道源码层面的**保持**守卫：以后有人把其中一个改回裸
`return;`、或把上报挪到 `return` 之后变成死代码，这里当场红，并点名是哪一个。

**它不声称什么。** 这不是闭包：不扫全文件的 `return;`，也没有「允许静默」名单。新加的第十一个
静默出口不会让它红——那一条保证矩阵的决议记录明确放弃了（全文件 `return;` 有 58 处，绝大多数
是普通 UI 守卫，没法用文本规则把它们和写路径出口分开）。

**归属靠函数切片，不靠条件文本。** 两个守卫条件在文件里各有四份逐字相同的副本
（`!this.currentRange || !this.contentEl`、`!ctx.bookId || ctx.chapterIndex == null`），按条件文本
全文件搜，每一个登记位都会撞出歧义、对**正确**的实现也红。所以先用花括号计数把文件切成函数体
（跳过注释、字符串、模板字面量），再只在各自的切片里找。切片落点做自检：收尾的 `}` 必须与函数
声明行同一缩进，否则报「切片失步」而不是在错的范围里匹配。`askAi` 刻意不在切片名单里——它的
两道守卫与两个登记位逐字相同，却不在本条的主张之内。

**登记键是（函数，守卫身份），从不是行号。** 同一个 IIFE 里任何一次插入都会让下面的行号整体
移动，按行号钉的断言注定会红。

**另附 ETag 的两处例外钉（P1–P4）。** `notesEtag` 只经服务端真提交过的版本前进（修订 A1 的守卫
在 `rememberNotesEtag` 里），但有两处是对 409 体里服务端主动告知的版本**直接赋值**，刻意不经过
那个函数：建/删的 409 重试（`notesWriteWithResync`）与冲突对话框的吸收（`openConflictFromResponse`）。
若有人把前者改经 `rememberNotesEtag`（它对 409 是空操作），重试就会带着同一个过期的 `If-Match`
再撞一次——「连点两下删」的第二下从此永远失败，客户端还报 `status:409`，把客户端的毛病算到
服务端头上。这里钉的是次数、所在函数、以及在它前面没有 `rememberNotesEtag(` 调用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS_JS = REPO_ROOT / "src" / "reader3_app" / "web" / "static" / "js" / "annotations.js"
REL_PATH = ANNOTATIONS_JS.relative_to(REPO_ROOT).as_posix()

#: 要切的函数名，字面量、封闭。`askAi` 刻意不在内（见模块文档）。
SLICED_FUNCTIONS = (
    "createAnnotation",
    "toggleMarkerAnnotation",
    "toggleAnnotation",
    "deleteCurrentAnnotation",
    "deleteAnnotations",
    "saveNote",
    "resolveConflict",
    "notesWriteWithResync",
    "openConflictFromResponse",
)

_NO_RANGE = r"if\s*\(\s*!this\.currentRange\s*\|\|\s*!this\.contentEl\s*\)"
_NO_CONTEXT = r"if\s*\(\s*!ctx\.bookId\s*\|\|\s*ctx\.chapterIndex\s*==\s*null\s*\)"

#: （函数，守卫身份，守卫条件的模式，期望 op）。十行，与 e2e 那边的 `W6_GUARD_OP_REGISTRY` 同一组 op
#: （末两行是 009 #50 接进诊断环的两道请求前守卫，2026-09-30）。
INSTRUMENTED: Tuple[Tuple[str, str, str, str], ...] = (
    ("createAnnotation", "missing range/content", _NO_RANGE, "create-no-selection"),
    ("createAnnotation", "missing book/chapter context", _NO_CONTEXT, "create-no-context"),
    ("toggleMarkerAnnotation", "missing range/content", _NO_RANGE, "marker-toggle-no-selection"),
    ("toggleAnnotation", "missing range/content", _NO_RANGE, "type-toggle-no-selection"),
    ("deleteCurrentAnnotation", "no annotation ids", r"if\s*\(\s*!ids\.length\s*\)", "delete-no-ids"),
    ("saveNote", "empty trimmed text", r"if\s*\(\s*!text\s*\)", "save-empty-text"),
    ("resolveConflict", "no pending conflict", r"if\s*\(\s*!c\s*\)", "conflict-no-pending"),
    ("deleteAnnotations", "missing context", _NO_CONTEXT, "delete-no-context"),
    ("createAnnotation", "offset snapshot unavailable", r"if\s*\(\s*!offsets\s*\)", "create-no-offsets"),
    ("createAnnotation", "empty quote", r"if\s*\(\s*!quote\s*\)", "create-empty-quote"),
)

#: 409 体里服务端告知的版本，直接赋值（P1–P4）。
ETAG_ASSIGNMENT = "if (body?.etag) notesEtag = body.etag;"
ETAG_EXCEPTION_FUNCTIONS = ("notesWriteWithResync", "openConflictFromResponse")
REMEMBER_CALL = "rememberNotesEtag("

_BLOCK_TAIL_RE = re.compile(
    r"reportNotesWriteFailure\(\s*\{(?P<args>.*?)\}\s*\)\s*;\s*return\b[^;]*;\s*\Z",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# 词法：两张与源码等长的视图
# ---------------------------------------------------------------------------


def _views(src: str) -> Tuple[str, str]:
    """返回 `(no_comments, skeleton)`，两者与 `src` 等长、偏移一一对应。

    * `no_comments`：`//` 与 `/* */` 注释换成空格，字符串原样保留——守卫与 op 的匹配用它；
    * `skeleton`：注释之外，字符串与模板字面量的**文字部分**也换成空格（`${…}` 里的表达式
      仍是代码）——花括号计数用它。

    正则字面量不处理：切片落点的缩进自检会把由此造成的失步报出来。
    """
    n = len(src)
    no_comments = list(src)
    skeleton = list(src)
    # 帧：["code", 深度, 是否模板表达式] 或 ["tpl"]
    stack: List[list] = [["code", 0, False]]
    i = 0

    def blank(lo: int, hi: int, both: bool) -> None:
        for k in range(lo, hi):
            if src[k] == "\n":
                continue
            skeleton[k] = " "
            if both:
                no_comments[k] = " "

    while i < n:
        frame = stack[-1]
        ch = src[i]
        if frame[0] == "tpl":
            if ch == "\\":
                blank(i, min(i + 2, n), False)
                i += 2
            elif ch == "`":
                stack.pop()
                i += 1
            elif ch == "$" and i + 1 < n and src[i + 1] == "{":
                stack.append(["code", 0, True])
                i += 2
            else:
                blank(i, i + 1, False)
                i += 1
            continue
        nxt = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            end = src.find("\n", i)
            end = n if end == -1 else end
            blank(i, end, True)
            i = end
        elif ch == "/" and nxt == "*":
            end = src.find("*/", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end, True)
            i = end
        elif ch in ("'", '"'):
            j = i + 1
            while j < n and src[j] != ch and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, min(j, n), False)
            i = j + 1
        elif ch == "`":
            stack.append(["tpl"])
            i += 1
        elif ch == "{":
            frame[1] += 1
            i += 1
        elif ch == "}":
            if frame[1] == 0 and frame[2]:
                stack.pop()
            else:
                frame[1] -= 1
            i += 1
        else:
            i += 1
    return "".join(no_comments), "".join(skeleton)


def _match_brace(skeleton: str, open_idx: int) -> Optional[int]:
    """`skeleton[open_idx] == "{"`；返回与之配对的 `}` 的下标，配不上返回 None。"""
    depth = 0
    for k in range(open_idx, len(skeleton)):
        c = skeleton[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k
    return None


def _line_of(text: str, idx: int) -> Tuple[int, str]:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    end = len(text) if end == -1 else end
    return text.count("\n", 0, idx) + 1, text[start:end]


def _slice_function(no_comments: str, skeleton: str, name: str) -> Tuple[int, int]:
    """返回函数体 `{…}` 的 `[open, close]` 下标（含两端花括号）。找不到、找到多个、或切片失步都抛。"""
    decl_re = re.compile(
        rf"^(?P<indent>[ \t]*)(?:async[ \t]+)?(?:function[ \t]+)?{re.escape(name)}[ \t]*\([^()\n]*\)[ \t]*\{{[ \t]*$",
        re.MULTILINE,
    )
    decls = list(decl_re.finditer(no_comments))
    if len(decls) != 1:
        raise AssertionError(
            f"function slicing lost sync at `{name}` — expected exactly one declaration in {REL_PATH}, "
            f"found {len(decls)}; the file's structure changed; fix the slicer, do not loosen the match"
        )
    decl = decls[0]
    open_idx = no_comments.rindex("{", decl.start(), decl.end())
    close_idx = _match_brace(skeleton, open_idx)
    if close_idx is None:
        raise AssertionError(
            f"function slicing lost sync at `{name}` — no matching closing brace; "
            "the file's structure changed; fix the slicer, do not loosen the match"
        )
    lineno, line = _line_of(no_comments, close_idx)
    indent = decl.group("indent")
    if line[: len(indent)] != indent or not line[len(indent):].startswith("}"):
        raise AssertionError(
            f"function slicing lost sync at `{name}` — closing brace at {REL_PATH}:{lineno} "
            f"({line!r}) is not at the declaration's indentation {indent!r}; "
            "the file's structure changed; fix the slicer, do not loosen the match"
        )
    return open_idx, close_idx


def _contract_message(function: str, guard: str, detail: str) -> str:
    return (
        f"Known notes failure guard {function}/{guard} no longer matches its reporting contract at "
        f"{REL_PATH} (slice {function}). Restore reportNotesWriteFailure before return, or explicitly "
        f"migrate this site and its paired Playwright case. [{detail}]"
    )


def _check_guard(
    no_comments: str, skeleton: str, span: Tuple[int, int], function: str, guard: str, pattern: str, op: str
) -> Optional[str]:
    lo, hi = span
    body = no_comments[lo : hi + 1]
    hits = list(re.finditer(pattern, body))
    if len(hits) != 1:
        return _contract_message(function, guard, f"guard pattern matched {len(hits)} times in the slice, expected exactly 1")
    after = lo + hits[0].end()
    rest = no_comments[after:hi]
    stripped = rest.lstrip()
    if not stripped.startswith("{"):
        lineno, line = _line_of(no_comments, lo + hits[0].start())
        return _contract_message(
            function, guard, f"guard at line {lineno} is not a braced block ({line.strip()!r}); a report after a one-line return is unreachable"
        )
    block_open = after + (len(rest) - len(stripped))
    block_close = _match_brace(skeleton, block_open)
    if block_close is None or block_close > hi:
        return _contract_message(function, guard, "guard block has no matching closing brace inside the slice")
    inner = no_comments[block_open + 1 : block_close]
    if inner.count("reportNotesWriteFailure(") != 1:
        return _contract_message(
            function, guard, f"guard block calls reportNotesWriteFailure {inner.count('reportNotesWriteFailure(')} times, expected 1"
        )
    # 017 WI-13（审计 #21）：上报之前不许有任何可执行语句。
    #
    # 只看块**尾部**是「上报 ＋ return」的话，`{ return; 上报…; return; }` 逐字满足尾部
    # 形状——而那条上报是死代码，一次也不会执行。这条护栏自称查的就是这个（模块文档：
    # 「把上报挪到 `return` 之后变成死代码，这里当场红」），却恰恰漏掉了同一件事的另一种
    # 写法：不是把上报挪到后面，而是把 `return` 挪到前面。2026-09-23 实测，插一句
    # `return;` 之后整条护栏照样 1 passed。
    #
    # 判据取「上报必须是块里的第一条语句」：`no_comments` 已经把注释抹成空格，所以正确的
    # 十个登记位在这里都是纯空白。比逐个点名 `return` / `throw` / `break` 强的地方在于，
    # 它不需要预先想全所有能让下一行变成死代码的写法。代价是以后若真有登记位需要先算一
    # 个值再上报，这里会红——那是 fail-closed 的一侧，且失败信息直接把拦下的那段文本抄给
    # 你看。
    head = inner[: inner.index("reportNotesWriteFailure(")]
    if head.strip():
        lineno, _ = _line_of(no_comments, block_open)
        return _contract_message(
            function,
            guard,
            f"guard block at line {lineno} runs {head.strip()!r} before reporting; "
            "reportNotesWriteFailure must be the block's first statement, otherwise an early "
            "exit in front of it makes the report dead code that never runs",
        )
    tail = _BLOCK_TAIL_RE.search(inner)
    if not tail:
        return _contract_message(function, guard, "reportNotesWriteFailure(...) is not the statement immediately before the block's terminal return")
    args = tail.group("args")
    if not re.search(rf"""\bop\s*:\s*(["']){re.escape(op)}\1""", args):
        return _contract_message(function, guard, f"report does not carry op {op!r}: {{{args.strip()}}}")
    if not re.search(r"\brequested\s*:\s*false\b", args):
        return _contract_message(function, guard, "report does not carry requested: false")
    return None


def test_known_notes_failure_guards_retain_reporting() -> None:
    src = ANNOTATIONS_JS.read_text(encoding="utf-8")
    no_comments, skeleton = _views(src)
    spans = {name: _slice_function(no_comments, skeleton, name) for name in SLICED_FUNCTIONS}

    problems: List[str] = []
    assert len({row[3] for row in INSTRUMENTED}) == len(INSTRUMENTED) == 10, "登记表不是十个互不相同的 op"
    for function, guard, pattern, op in INSTRUMENTED:
        msg = _check_guard(no_comments, skeleton, spans[function], function, guard, pattern, op)
        if msg:
            problems.append(msg)

    # P1：原文里恰好两处。
    total = src.count(ETAG_ASSIGNMENT)
    if total != 2:
        problems.append(f"P1: `{ETAG_ASSIGNMENT}` occurs {total} times in {REL_PATH}, expected exactly 2")
    for function in ETAG_EXCEPTION_FUNCTIONS:
        lo, hi = spans[function]
        body = no_comments[lo : hi + 1]
        # P2：各自的切片里恰好一处。
        n = body.count(ETAG_ASSIGNMENT)
        if n != 1:
            problems.append(f"P2: `{ETAG_ASSIGNMENT}` occurs {n} times in slice {function}, expected exactly 1")
            continue
        at = body.index(ETAG_ASSIGNMENT)
        # P3：它前面没有 `rememberNotesEtag(` 调用。
        if REMEMBER_CALL in body[:at]:
            problems.append(
                f"P3: slice {function} calls {REMEMBER_CALL}…) before the 409-body ETag assignment — "
                "the 409 absorption must not be routed through the guarded helper"
            )
        # P4：`notesWriteWithResync` 里恰好一处且在其后；`openConflictFromResponse` 里零处。
        calls = body.count(REMEMBER_CALL)
        if function == "notesWriteWithResync":
            if calls != 1 or REMEMBER_CALL not in body[at:]:
                problems.append(
                    f"P4: slice {function} must contain exactly one {REMEMBER_CALL}…) call, after the assignment; "
                    f"found {calls} (after: {body[at:].count(REMEMBER_CALL)})"
                )
        elif calls != 0:
            problems.append(f"P4: slice {function} must contain no {REMEMBER_CALL}…) call; found {calls}")

    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# 017 WI-13（审计 #21）：检查器自身的变异用例
# ---------------------------------------------------------------------------
#
# 上面那条测试只在 `annotations.js` **当前**这一版上跑。它绿，可能是因为十个登记位真的
# 守着契约，也可能是因为检查器根本不会红——二者在那条测试里不可区分。审计 #21 命中的正是
# 后者：`_BLOCK_TAIL_RE` 只看块尾，于是「把 `return` 挪到上报前面」这种把上报变成死代码的
# 写法，逐字满足尾部形状，整条护栏照样 `1 passed`。
#
# 所以这里把检查器本身放到台上：喂它一份合成的、结构与真文件同形的 JS，逐个注入已知的破坏
# 写法，要求每一条都被拒、且拒绝理由指名道姓。每个用例都对应检查器里的一段判据——删掉那段
# 判据，对应的用例立刻红。合成源而不是改真文件，是因为真文件里十个登记位共用两个逐字相同的
# 守卫条件，在那上面注入会同时惊动别的登记位，红的原因就说不清了。

_SYNTHETIC_GUARD_PATTERN = r"if\s*\(\s*!text\s*\)"
_SYNTHETIC_OP = "save-empty-text"

_SYNTHETIC_TEMPLATE = """(function () {
  const app = {
    async saveNote() {
      const text = String(this.noteTextarea?.value || "").trim();
__GUARD__
      await this.write(text);
    },
  };
})();
"""

#: 正确写法：上报是块里的第一条语句，紧跟着块的终结 `return`。
_CORRECT_GUARD = """      if (!text) {
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
        return;
      }"""


def _run_checker(guard_source: str) -> Optional[str]:
    """把一段守卫源码塞进合成模块，走完整条真实路径（切视图 → 切函数 → 查契约）。"""
    src = _SYNTHETIC_TEMPLATE.replace("__GUARD__", guard_source)
    no_comments, skeleton = _views(src)
    span = _slice_function(no_comments, skeleton, "saveNote")
    return _check_guard(
        no_comments, skeleton, span, "saveNote", "synthetic", _SYNTHETIC_GUARD_PATTERN, _SYNTHETIC_OP
    )


def test_the_checker_accepts_the_shape_it_is_meant_to_accept() -> None:
    """阳性对照。没有它，「一律拒绝」也能让下面每一条变异用例变绿。"""
    assert _run_checker(_CORRECT_GUARD) is None, "检查器拒绝了它自己要求的正确写法"


def test_the_checker_ignores_comments_before_the_report() -> None:
    """边界：注释不是可执行语句，不许被「上报必须是第一条语句」误伤。

    十个真登记位里有几处在块里写了说明性注释，`_views` 会把它们抹成空格；这条用例把那个
    依赖钉死——若有人把 head 判据改成直接看原始源码，这里当场红，而真文件那条测试也会跟着
    红得莫名其妙。
    """
    guard = """      if (!text) {
        // 说明：这里只是解释，不产生任何可执行语句。
        /* 块注释同理 */
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
        return;
      }"""
    assert _run_checker(guard) is None, "注释被当成了上报之前的可执行语句"


#: （用例名，注入的守卫写法，拒绝理由里必须出现的字样）。每一行对应检查器里的一段判据。
_CHECKER_MUTANTS: Tuple[Tuple[str, str, str], ...] = (
    (
        # 审计 #21 命中的那一条：旧检查器在这里是绿的。
        "early_return_before_the_report",
        """      if (!text) {
        return;
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
      }""",
        "first statement",
    ),
    (
        # 同一件事的另一种写法：`return` 不是唯一能让下一行变成死代码的东西。
        "early_throw_before_the_report",
        """      if (!text) {
        throw new Error("nope");
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
      }""",
        "first statement",
    ),
    (
        "report_pushed_after_the_return",
        """      if (!text) {
        return;
      }
      if (false) {
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
      }""",
        "expected 1",
    ),
    (
        "report_deleted_entirely",
        """      if (!text) {
        return;
      }""",
        "expected 1",
    ),
    (
        "guard_is_not_a_braced_block",
        """      if (!text) return;
      reportNotesWriteFailure({ op: "save-empty-text", requested: false });""",
        "not a braced block",
    ),
    (
        "report_carries_the_wrong_op",
        """      if (!text) {
        reportNotesWriteFailure({ op: "save-something-else", requested: false });
        return;
      }""",
        "does not carry op",
    ),
    (
        # `requested: true` 会让诊断声称「请求发出去了」，而这一族守卫的全部意义就是没发。
        "report_claims_a_request_was_made",
        """      if (!text) {
        reportNotesWriteFailure({ op: "save-empty-text", requested: true });
        return;
      }""",
        "requested: false",
    ),
    (
        "report_is_not_the_statement_before_the_return",
        """      if (!text) {
        reportNotesWriteFailure({ op: "save-empty-text", requested: false });
        this.closeEditor();
        return;
      }""",
        "immediately before",
    ),
)


@pytest.mark.parametrize(
    ("guard_source", "expected_detail"),
    [pytest.param(guard, detail, id=name) for name, guard, detail in _CHECKER_MUTANTS],
)
def test_the_checker_rejects_every_known_way_to_break_the_contract(
    guard_source: str, expected_detail: str
) -> None:
    message = _run_checker(guard_source)
    assert message is not None, (
        "检查器放过了一个已知的破坏写法——上面那条护栏测试的绿色因此不作数：\n" + guard_source
    )
    assert expected_detail in message, (
        f"拒绝理由里没有 {expected_detail!r}，说明红是别的判据顺手撞出来的，不是这一条：\n{message}"
    )
