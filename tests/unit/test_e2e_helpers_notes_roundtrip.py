"""WI-3 的 unit lane 那一条：`seed_notes` 写出的 `notes.json` 必须能被**生产代码**读回。

矩阵（`.claude/tdd-guardian/tests-20260901-224500.md` §WI-3）把这条判给 unit lane 而不是
e2e，理由是成本：它断的是一个 JSON 文件的形状，放进 e2e 等于为一条形状断言买一次
chromium 冷启动。这里不需要浏览器，也不需要服务进程。

**它守的是什么。** `notes_service.save_annotations` 写的是一个**对象**
（`{"schema_version": …, "book_id": …, "annotations": [...]}`），不是裸数组。
`seed_notes` 若图省事写成 `json.dump(list_of_dicts)`，`load_annotations` 会以
`NotesFileError` 拒绝整份文件 —— 于是每一个 notes 端点 500，而**用例侧看到的表现**
只是「R-3 / R-6 / DEG-S1 莫名其妙地红」，离真正的原因隔着一整条请求链。
把这条钉在 unit lane，是让那个错误在离它最近的地方响。

Spec level **S6**：`hypothesis` 在无界域上生成 `list[Annotation]`（四种 type、四种
color、CJK/emoji 混合的 quote、`note_text` 可为 `None` 或空串、`prefix`/`suffix`
跨过 50 字符截断边界）。
Assertion strategy **L2**：断的是磁盘副作用，经生产读取器读回后逐字段比对。
Mock boundary **none**：真 `notes_service`、真 `tmp_path`，不 mock 文件系统。

**什么重构会让它红**：helper 改成写裸数组、漏写 `schema_version`、或 012 改了 notes 的
on-disk schema 而没同步 helper。**改任何一条 e2e 用例都不会让它红** —— 这正是它该有的
耦合面。

------------------------------------------------------------------------------
**2026-09-05 审计（D1）之后，本文件多守一条与 notes 无关的 helper 契约**：
`helpers.mark_id_union` 的「`data-annotation-ids` 是字符串数组」。它同样是纯 Python
（输入是一份 `scan` 字典），同样不值得为它买一次 chromium 冷启动，而 `tests/e2e/` 下
每加一条 item 都要动 `scripts/lint_e2e_groups.py` 的条数常量——所以它落在 unit lane，
落在这个已经按路径加载了 `helpers.py` 的文件里，而不是新开一个只有两条用例的模块。
两组用例在文件里以横线分节，加载 helper 的那段是共用的。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader3_app.models.annotations import Annotation
from reader3_app.notes_service import NOTES_SCHEMA_VERSION, load_annotations

# `tests/e2e/` 不是 package，unit lane 的 sys.path 上也没有它。按文件路径加载，
# 而不是把 `tests/e2e` 塞进 sys.path：塞进去会让 `conftest` 这个裸模块名在两条 lane
# 之间产生歧义，而那正是 `scripts/lint_e2e_groups.py` 记录过的那个坑。
_HELPERS_PATH = Path(__file__).resolve().parents[1] / "e2e" / "helpers.py"
_spec = importlib.util.spec_from_file_location("reader3_e2e_helpers_under_test", _HELPERS_PATH)
assert _spec and _spec.loader, f"无法按路径加载 {_HELPERS_PATH}"
helpers = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helpers
_spec.loader.exec_module(helpers)


BOOK_ID = "roundtrip_data"

# 拉丁 + CJK + emoji 混排。emoji 是 BMP 之外的码位，它同时压住 UTF-16 代理对：
# quote 一旦被按 UTF-16 单元切过一刀，往返就不再恒等。
_QUOTE_ALPHABET = "abcXYZ .,'\"\\/<>&é咖啡館での夜커피\U0001f4d6\U0001f9ea"


def _annotations(book_id: str) -> st.SearchStrategy[Annotation]:
    text = st.text(alphabet=_QUOTE_ALPHABET, min_size=0, max_size=60)
    return st.builds(
        Annotation,
        id=st.uuids().map(str),
        book_id=st.just(book_id),
        chapter_index=st.integers(min_value=0, max_value=40),
        type=st.sampled_from(["marker", "wavy", "underline", "note"]),
        color=st.sampled_from(["yellow", "green", "pink", "blue"]),
        # quote 非空是 `Annotation.__post_init__` 的硬要求，不是本条用例的口味。
        quote=st.text(alphabet=_QUOTE_ALPHABET, min_size=1, max_size=60),
        # 60 > 50：故意越过 `__post_init__` 的截断边界。截断是幂等的（prefix 留后
        # 50、suffix 留前 50，再截一次结果不变），所以往返恒等仍然成立 —— 而一个
        # 在写盘时**自己**再截一刀、或截错方向的 helper 会在这里露出来。
        prefix=text,
        suffix=text,
        position=st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)),
        cfi=st.one_of(st.none(), st.text(alphabet=_QUOTE_ALPHABET, min_size=1, max_size=40)),
        note_text=st.one_of(st.none(), st.just(""), text),
        created_at=st.datetimes().map(lambda d: d.isoformat()),
        orphaned=st.booleans(),
    )


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(annotations=st.lists(_annotations(BOOK_ID), min_size=0, max_size=6))
def test_seed_notes_round_trips_through_production_load_annotations(
    tmp_path_factory: pytest.TempPathFactory, annotations: List[Annotation]
) -> None:
    """写 → 用生产的 `load_annotations` 读回 → 逐字段等值，且顺序保持。"""
    books_dir = tmp_path_factory.mktemp("books")
    (books_dir / BOOK_ID).mkdir()

    helpers.seed_notes(books_dir, BOOK_ID, annotations)

    loaded = load_annotations(str(books_dir), BOOK_ID)
    assert [a.to_dict() for a in loaded] == [a.to_dict() for a in annotations]

    # `read_notes` 是同一份磁盘状态的第二个读取口径（list[dict]）。两个口径必须同解，
    # 否则 e2e 侧断言的东西和服务端读到的东西可以静默地不是一回事。
    assert helpers.read_notes(books_dir, BOOK_ID) == [a.to_dict() for a in annotations]


def test_seed_notes_writes_the_production_object_shape_not_a_bare_array(tmp_path: Path) -> None:
    """S1 的那个例子，把上面那条性质失败时的**原因**写成一句可读的话。

    往返红了以后，「哪里错了」有两种可能：形状错了，或字段错了。这条只答第一种，
    所以它红的时候诊断是零成本的。
    """
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    helpers.seed_notes(
        books_dir,
        BOOK_ID,
        [Annotation(book_id=BOOK_ID, chapter_index=0, quote="Alpha prose", type="marker", color="yellow")],
    )

    raw = json.loads((books_dir / BOOK_ID / "notes.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict), "notes.json 顶层必须是对象；裸数组会让每个 notes 端点 500"
    assert raw["schema_version"] == NOTES_SCHEMA_VERSION
    assert raw["book_id"] == BOOK_ID
    assert isinstance(raw["annotations"], list) and len(raw["annotations"]) == 1


def _record_forms(book_id: str) -> st.SearchStrategy[Tuple[Annotation, str]]:
    """(标注, 交给 `seed_notes` 时的**形态**)。三种形态，一条 e2e 里都真的用过。

    e2e 侧的调用点**绝大多数传的是 dict 字面量**（`test_read_paths.py` /
    `test_write_note_editor.py` / `deg_assertions.py` …），而 2026-09-05 之前这个文件
    只生成 `Annotation` 实例——于是 `seed_notes` 里那条 `isinstance(item, Mapping)` 的
    转换分支、以及 `data.setdefault("book_id", book_id)` 这一句，**在 unit lane 上一次
    都没跑过**（审计 D4）。三种形态混在同一个列表里生成，是因为调用点也是混着写的。
    """
    return st.tuples(
        _annotations(book_id),
        st.sampled_from(["instance", "dict", "dict_without_book_id"]),
    )


def _as_seed_item(annotation: Annotation, form: str) -> Any:
    if form == "instance":
        return annotation
    data = annotation.to_dict()
    if form == "dict_without_book_id":
        del data["book_id"]
    return data


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pairs=st.lists(_record_forms(BOOK_ID), min_size=1, max_size=6))
def test_seed_notes_round_trips_dicts_and_instances_mixed_in_one_list(
    tmp_path_factory: pytest.TempPathFactory, pairs: List[Tuple[Annotation, str]]
) -> None:
    """S6：三种形态混排写进去，生产读取器读回来的必须是**同一批标注**，顺序不变。

    期望值取自生成器手上的那个 `Annotation`（`ann.to_dict()`），**不是**把
    `seed_notes` 的 `setdefault` 逻辑在这里抄一遍——抄一遍会让「helper 不再补
    `book_id`」这类缺陷两边同时发生、互相抵消。缺 `book_id` 的那一种因此断的是一句
    实话：**它必须被补成 `seed_notes` 的那本书**，而不是 `""`（`Annotation.__post_init__`
    会拒）也不是别本书。
    """
    books_dir = tmp_path_factory.mktemp("books")
    (books_dir / BOOK_ID).mkdir()

    items = [_as_seed_item(ann, form) for ann, form in pairs]
    # 调用方手上的 dict 不该被 helper 就地改（`seed_notes` 是 `dict(item)` 的副本）。
    # 快照要在调用之前取：之后取就成了同一个对象的两个名字。
    before = [dict(i) if isinstance(i, dict) else i for i in items]

    helpers.seed_notes(books_dir, BOOK_ID, items)

    loaded = load_annotations(str(books_dir), BOOK_ID)
    assert [a.to_dict() for a in loaded] == [ann.to_dict() for ann, _ in pairs]
    assert helpers.read_notes(books_dir, BOOK_ID) == [ann.to_dict() for ann, _ in pairs]
    assert all(a.book_id == BOOK_ID for a in loaded), (
        f"有条目的 book_id 不是 {BOOK_ID!r}：{[a.book_id for a in loaded]}"
    )
    assert items == before, (
        "seed_notes 就地改了调用方传进来的 dict（`book_id` 应当补在副本上）。"
        "e2e 侧常把同一份 dict 字面量在一条用例里用两次，就地改会让第二次看到的不是原件。"
    )


def test_seed_notes_fills_book_id_for_a_dict_record_that_omits_it(tmp_path: Path) -> None:
    """上面那条性质里「缺 `book_id`」那一支的定值例子，红的时候诊断是零成本的。

    e2e 侧的 dict 字面量几乎都不写 `book_id`（R-3 / R-6 / DEG-S1 的预置都是这样）。
    helper 若停止补这个字段，`Annotation.from_dict` 会拿到 `""`，`__post_init__` 当场
    `ValueError: book_id is required`——那时红的是 30 余条 e2e，而不是这里。
    """
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)

    helpers.seed_notes(
        books_dir,
        BOOK_ID,
        [
            {"id": "no-book-id", "chapter_index": 0, "quote": "Alpha prose", "type": "marker", "color": "yellow"},
            {"id": "has-book-id", "book_id": BOOK_ID, "chapter_index": 1, "quote": "Beta prose", "type": "wavy"},
        ],
    )

    loaded = load_annotations(str(books_dir), BOOK_ID)
    assert [a.id for a in loaded] == ["no-book-id", "has-book-id"]
    assert [a.book_id for a in loaded] == [BOOK_ID, BOOK_ID]
    assert [a.quote for a in loaded] == ["Alpha prose", "Beta prose"]


def test_seed_notes_refuses_anything_that_is_neither_annotation_nor_mapping(tmp_path: Path) -> None:
    """第三条分支：既不是 `Annotation` 也不是 `Mapping` 时**抛**，不静默跳过。

    静默跳过的表现是「预置了 3 条，页面上只有 2 条」——而用例会把它读成生产端的渲染缺陷。
    """
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)

    with pytest.raises(TypeError, match="seed_notes"):
        helpers.seed_notes(books_dir, BOOK_ID, [("id", "not-a-mapping")])


# ---------------------------------------------------------------------------
# `helpers.mark_id_union`：`data-annotation-ids` 的形状契约（2026-09-05 审计 D1）
# ---------------------------------------------------------------------------
#
# 为什么和上面的 notes 往返同住一个文件：理由写在模块 docstring 末节。


def _scan(*raw_ids: Any) -> Dict[str, Any]:
    """`scan_marks()` 返回值里 `mark_id_union` 唯一会读的那一项。

    只造 `ids`：多造几个键会让这几条用例假装自己也在测 `scan_marks` 的其他视图，
    而它们一个都没断。
    """
    return {"ids": list(raw_ids)}


def test_mark_id_union_unions_the_arrays_across_marks() -> None:
    assert helpers.mark_id_union(_scan('["a1", "a2"]', '["a2", "a3"]')) == {"a1", "a2", "a3"}
    assert helpers.mark_id_union(_scan("[]")) == set()


def test_mark_id_union_rejects_a_json_object_keyed_by_the_expected_ids() -> None:
    """D1 的那颗子弹：**对象**而不是数组时必须红。

    2026-09-05 之前的写法是 `union |= set(json.loads(raw))`，而 `set()` 对字典取的是
    **键**——实测 `set({"a1": 0, "a2": 0})` 就是 `{"a1", "a2"}`。于是一个把
    `data-annotation-ids` 写成对象的生产实现，会让每一条「并集等于这几个 id」的读路径
    判据照常绿：判据测的东西（契约是数组）与它实际能分辨的东西已经不是一回事。
    契约来自 `annotations.js` 的 `JSON.stringify(ids)`，`ids` 是 `Array<string>`。
    """
    served = '{"a1": 0, "a2": 0}'
    with pytest.raises(AssertionError, match="数组") as exc:
        helpers.mark_id_union(_scan(served))
    assert served in str(exc.value), "失败消息必须点名实际服务到 DOM 上的那一串"


def test_mark_id_union_rejects_non_string_elements() -> None:
    """数组里混进非字符串同样要红：`{"a1", 3}` 与任何 id 集合比对都只会红得莫名其妙。"""
    served = '["a1", 3]'
    with pytest.raises(AssertionError, match="非字符串") as exc:
        helpers.mark_id_union(_scan(served))
    assert served in str(exc.value)


def test_mark_id_union_rejects_a_mark_without_the_attribute_or_with_broken_json() -> None:
    """两条既有守卫（属性缺失 / 不是合法 JSON）也各钉一条，免得下次重写时悄悄丢掉。"""
    with pytest.raises(AssertionError, match="data-annotation-ids"):
        helpers.mark_id_union(_scan(None))
    with pytest.raises(AssertionError, match="合法 JSON"):
        helpers.mark_id_union(_scan("[a1"))


def test_read_notes_reports_absent_file_as_empty_not_as_an_error(tmp_path: Path) -> None:
    """「还没有任何标注」是合法状态，隔离 fixture 的缺省态就是它。

    `read_notes` 若对缺文件抛错，隔离 fixture 复位之后的每一条断言都得先包一层
    try —— 那层 try 迟早会把真正的读失败一起吞掉。
    """
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    assert helpers.read_notes(books_dir, BOOK_ID) == []
