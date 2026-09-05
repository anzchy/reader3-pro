"""`helpers.assert_bystanders_unchanged` 自己的用例——守恒律的载体也要被守。

放在 unit lane 而不是 e2e：这个函数是纯 Python，输入是两份 `list[dict]`，不碰浏览器也不碰
服务进程。为一个字典比较买一次 chromium 冷启动是浪费（理由同
`test_e2e_helpers_notes_roundtrip.py`）。

**为什么它值得单独被测。** 它是 009 里唯一一个「断言本身被抽成函数」的地方——W-7 与今后
WI-6/7/8/9 的守恒判据全都落在它一个人身上。它要是空转，那几条用例会一起静默失效，而
`tests/unit/test_e2e_bystander_discipline.py` 只查「有没有调用它」，查不出「调用了但它不咬人」。
两个文件合起来才构成一条完整的规则：**必须调用**（那边）＋ **调用了就真的会红**（这边）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# 加载方式与 `test_e2e_helpers_notes_roundtrip.py` 一致：按文件路径，不把 `tests/e2e`
# 塞进 sys.path（会让裸模块名 `conftest` 在两条 lane 之间产生歧义）。
_HELPERS_PATH = Path(__file__).resolve().parents[1] / "e2e" / "helpers.py"
_spec = importlib.util.spec_from_file_location("reader3_e2e_helpers_bystanders", _HELPERS_PATH)
assert _spec and _spec.loader, f"无法按路径加载 {_HELPERS_PATH}"
helpers = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helpers
_spec.loader.exec_module(helpers)

assert_bystanders_unchanged = helpers.assert_bystanders_unchanged


def _rec(rid: str, **over: Any) -> Dict[str, Any]:
    """一条形状贴近真实 `notes.json` 条目的记录。字段值都是字面量（§0 第五条纪律）。"""
    base: Dict[str, Any] = {
        "id": rid,
        "chapter_index": 0,
        "type": "marker",
        "color": "blue",
        "quote": "One",
        "note_text": None,
        "created_at": "2026-01-01T00:00:01+00:00",
    }
    base.update(over)
    return base


TARGET = "target-note"
BYSTANDER = "bystander-marker"


def _pair() -> List[Dict[str, Any]]:
    return [_rec(TARGET, type="note", quote="Alpha prose", note_text="old body"), _rec(BYSTANDER)]


def test_passes_when_only_the_declared_target_changed() -> None:
    before = _pair()
    after = [_rec(TARGET, type="note", quote="Alpha prose", note_text="new body"), _rec(BYSTANDER)]
    assert_bystanders_unchanged(before, after, changed_ids={TARGET})


def test_reds_when_a_bystander_field_moved() -> None:
    """整章回写把正文写给了每一条——条数对、目标条也对，只有旁观条被顺手改了。"""
    before = _pair()
    after = [
        _rec(TARGET, type="note", quote="Alpha prose", note_text="new body"),
        _rec(BYSTANDER, note_text="new body"),
    ]
    with pytest.raises(AssertionError) as excinfo:
        assert_bystanders_unchanged(before, after, changed_ids={TARGET})
    message = str(excinfo.value)
    assert BYSTANDER in message, f"失败消息没点名是哪一条：{message}"
    assert "new body" in message, f"失败消息没把前后两份贴出来，没法定位改了什么：{message}"


def test_reds_when_a_bystander_vanished() -> None:
    """整章回写只带了请求里那一条——旁观条整条消失，而 HTTP 照样 200。"""
    before = _pair()
    after = [_rec(TARGET, type="note", quote="Alpha prose", note_text="new body")]
    with pytest.raises(AssertionError) as excinfo:
        assert_bystanders_unchanged(before, after, changed_ids={TARGET})
    assert "没了" in str(excinfo.value), (
        f"「不见了」与「被改了」要报成两件事，否则诊断把人指向错的方向：{excinfo.value}"
    )


def test_a_new_schema_field_on_a_bystander_is_caught() -> None:
    """整字典等值的**理由**：挑字段的写法会漏掉下一个被加进 schema 的字段。

    这里给旁观条加一个 `_pair()` 没有的字段。任何「比对 id / quote / color」的实现都会
    放过它；整字典等值不会。012 要动 `Annotation`，所以这不是假想的场景。
    """
    before = _pair()
    after = [
        _rec(TARGET, type="note", quote="Alpha prose", note_text="new body"),
        _rec(BYSTANDER, cfi="epubcfi(/6/4!/4/2/2,/1:0,/1:3)"),
    ]
    with pytest.raises(AssertionError):
        assert_bystanders_unchanged(before, after, changed_ids={TARGET})


def test_zero_bystanders_reds_instead_of_silently_passing() -> None:
    """一次「零条旁观」的调用什么都没断到——而静默空转正是本函数要防的那件事本身。

    这条是本文件里最重要的一条：没有它，「预置漏了旁观条」或「changed_ids 写宽了」会让
    调用方**以为**自己断过守恒，`test_e2e_bystander_discipline.py` 也查得到调用，
    两道机制一起被绕过去。
    """
    before = _pair()
    with pytest.raises(AssertionError) as excinfo:
        assert_bystanders_unchanged(before, list(before), changed_ids={TARGET, BYSTANDER})
    assert "没有旁观条可断" in str(excinfo.value)


def test_ids_are_compared_as_strings() -> None:
    """`changed_ids` 传 int、记录里是 str（或反过来）不该被当成「没声明的改动」。"""
    before = [_rec("7", type="note", note_text="old"), _rec(BYSTANDER)]
    after = [_rec("7", type="note", note_text="new"), _rec(BYSTANDER)]
    assert_bystanders_unchanged(before, after, changed_ids={7})
