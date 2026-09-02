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
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import List

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


def test_read_notes_reports_absent_file_as_empty_not_as_an_error(tmp_path: Path) -> None:
    """「还没有任何标注」是合法状态，隔离 fixture 的缺省态就是它。

    `read_notes` 若对缺文件抛错，隔离 fixture 复位之后的每一条断言都得先包一层
    try —— 那层 try 迟早会把真正的读失败一起吞掉。
    """
    books_dir = tmp_path / "books"
    (books_dir / BOOK_ID).mkdir(parents=True)
    assert helpers.read_notes(books_dir, BOOK_ID) == []
