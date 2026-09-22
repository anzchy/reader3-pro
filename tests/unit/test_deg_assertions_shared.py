"""`tests/fixtures/deg_assertions.py` 的纯判据与降级构造，在 unit lane 上正反两面各跑一遍。

DEG-S1…S4 的八条 e2e 用例（`acceptance_p3` / `acceptance_4a4`）今天全部 skip，它们的断言主体
住在 `deg_assertions` 里。§0.5 的纪律是「一条到期才第一次被人读的断言，等于没写」——本文件让那些
判据**今天就被执行**：每个 `judge_deg_sN` 各有一组通过的观测与逐项失败的观测；每个 `run_deg_sN`
在碰 `page` 之前就拒绝键集合不对的映射表；四个降级构造在 `tmp_path` 上真的落盘并能被生产读取器读回；
`pickle_fallback_server` 真起一个子进程（微型 HTTP 服务 ＋ 一个立刻退出的命令）。

`tests/unit/test_e2e_group_guard.py` 第七条要求两组共用的每个函数都被 tests/unit 下某个文件点名——
本文件就是那个点名处。

不碰 `books/`；一切落盘都在 `tmp_path`。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict

import pytest

import deg_assertions as deg  # type: ignore[import-not-found]
from deg_assertions import (  # type: ignore[import-not-found]
    DEG_TESTID_KEYS,
    judge_deg_s1,
    judge_deg_s2,
    judge_deg_s3,
    judge_deg_s4,
    make_legacy_format_book,
    make_notes_stale,
    pickle_fallback_server,
    pkl_only_book_ids,
    read_notes_raw,
    remove_book_dir,
    require_testids,
    run_deg_s1,
    run_deg_s2,
    run_deg_s3,
    run_deg_s4,
    write_stale_index_meta,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_P3 = REPO_ROOT / "tests" / "e2e" / "acceptance_p3"
ACCEPTANCE_4A4 = REPO_ROOT / "tests" / "e2e" / "acceptance_4a4"


def _full_table() -> Dict[str, str]:
    return {k: f"tid-{k}" for k in DEG_TESTID_KEYS}


# --------------------------------------------------------------------------
# 映射表校验：run_* 在碰 page 之前就拒绝
# --------------------------------------------------------------------------
def test_require_testids_accepts_the_exact_key_set_and_rejects_drift() -> None:
    require_testids(_full_table(), where="ok")
    missing = _full_table()
    missing.pop("s1_banner")
    with pytest.raises(AssertionError, match="s1_banner"):
        require_testids(missing, where="missing")
    extra = _full_table()
    extra["s9_bogus"] = "x"
    with pytest.raises(AssertionError, match="s9_bogus"):
        require_testids(extra, where="extra")
    empty = _full_table()
    empty["s4_badge"] = ""
    with pytest.raises(AssertionError, match="s4_badge"):
        require_testids(empty, where="empty")


@pytest.mark.parametrize(
    "runner,args",
    [
        (run_deg_s1, ("http://x", "/tmp", "b_data")),
        (run_deg_s2, ("http://x", "/tmp", "b_data")),
        (run_deg_s3, ("http://x", "http://y", "/tmp", "b_data")),
        (run_deg_s4, ("http://x", "/tmp", "b_data", ["c_data"])),
    ],
    ids=["s1", "s2", "s3", "s4"],
)
def test_each_runner_rejects_a_bad_table_before_touching_the_page(runner, args) -> None:  # type: ignore[no-untyped-def]
    """`page=None`：映射表错时必须在任何 Playwright 调用之前抛 AssertionError，而不是 AttributeError。"""
    bad = _full_table()
    bad.pop("s2_card")
    with pytest.raises(AssertionError, match="s2_card"):
        runner(None, *args, bad)


def test_both_acceptance_tables_have_exactly_the_shared_key_set() -> None:
    """两张真实映射表的键集合都等于 `DEG_TESTID_KEYS`——第七条守卫断两表相等，这里断它们都对得上定义处。"""
    import ast

    for module_dir in (ACCEPTANCE_P3, ACCEPTANCE_4A4):
        files = sorted(module_dir.glob("test_*.py"))
        assert len(files) == 1, f"{module_dir} 下应恰好一个用例模块：{files}"
        tree = ast.parse(files[0].read_text(encoding="utf-8"))
        table = None
        for node in tree.body:
            # 两种赋值形态都要认：`DEG_TESTIDS = {...}`（ast.Assign）与
            # `DEG_TESTIDS: Dict[str, str] = {...}`（ast.AnnAssign）。只认 Assign 时，一旦有人
            # 给映射表加上类型注解，这条守卫就会在第一个目录上报「没有 DEG_TESTIDS」——那是
            # 断言自己瞎了，不是被测模块出错，且失败信息把人指向完全错的地方。
            # 注：test_e2e_group_guard.py 的 _testid_table_keys() 目前只认 Assign，两张真实
            # 映射表因此写成裸赋值；这里认两种是为了「注解回来时不再哑掉」，不放松任何断言。
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            elif isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                continue
            if not any(isinstance(t, ast.Name) and t.id == "DEG_TESTIDS" for t in targets):
                continue
            assert isinstance(node.value, ast.Dict)
            table = {k.value: v.value for k, v in zip(node.value.keys, node.value.values) if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
        assert table is not None, f"{files[0]} 没有 DEG_TESTIDS"
        require_testids(table, where=str(files[0].relative_to(REPO_ROOT)))


# --------------------------------------------------------------------------
# judge_deg_s1
# --------------------------------------------------------------------------
_S1_RECORDS = [dict(deg.DEG_S1_ANNOTATION, book_id="b_data")]


def _s1_ok() -> Dict[str, object]:
    return dict(
        banner_text="标注暂停套用（未删除）——本书内容已变化",
        records_before=_S1_RECORDS,
        records_after=[dict(r) for r in _S1_RECORDS],
        served_count=1,
        mark_count=0,
        badge_count=1,
        excerpt_text="…Alpha prose.…",
    )


def test_judge_deg_s1_passes_on_a_correct_observation() -> None:
    judge_deg_s1(**_s1_ok())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value,token",
    [
        ("banner_text", "标注暂停套用", "未删除"),
        ("banner_text", "标注未删除", "暂停套用"),
        ("records_after", [], "变了"),
        ("served_count", 0, "吞掉"),
        ("mark_count", 1, "套用没有停"),
        ("badge_count", 0, "逐条"),
        ("excerpt_text", "没有原文", "quote"),
    ],
)
def test_judge_deg_s1_fails_on_each_broken_observation(field: str, value: object, token: str) -> None:
    obs = _s1_ok()
    obs[field] = value
    with pytest.raises(AssertionError, match=token):
        judge_deg_s1(**obs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# judge_deg_s2
# --------------------------------------------------------------------------
def test_judge_deg_s2_passes_and_fails_where_it_should() -> None:
    judge_deg_s2(status_text="索引已过期", banner_text="索引已过期，结果可能不全", reindex_count=1)
    with pytest.raises(AssertionError, match="为空"):
        judge_deg_s2(status_text="  ", banner_text="索引已过期", reindex_count=1)
    with pytest.raises(AssertionError, match="未索引"):
        judge_deg_s2(status_text="未索引", banner_text="索引已过期", reindex_count=1)
    with pytest.raises(AssertionError, match="索引已过期"):
        judge_deg_s2(status_text="过期", banner_text="Semantic index stale", reindex_count=1)
    with pytest.raises(AssertionError, match="重建按钮"):
        judge_deg_s2(status_text="过期", banner_text="索引已过期", reindex_count=0)


# --------------------------------------------------------------------------
# judge_deg_s3
# --------------------------------------------------------------------------
def _s3_ok() -> Dict[str, object]:
    return dict(
        control_lib_banner_count=0,
        library_banner_text="正以 pickle 回退模式运行，有 4 本书尚未迁移",
        reader_banner_text="正以 pickle 回退模式运行，有 4 本书尚未迁移",
        list_visible_before=False,
        list_visible_after=True,
        list_visible_after_second_toggle=False,
        listed_count=4,
        expected_listed_count=4,
    )


def test_judge_deg_s3_passes_on_a_correct_observation() -> None:
    judge_deg_s3(**_s3_ok())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value,token",
    [
        ("control_lib_banner_count", 1, "常亮"),
        ("library_banner_text", "", "书库页"),
        ("reader_banner_text", "", "阅读器页"),
        ("reader_banner_text", "另一份文案", "不一致"),
        ("list_visible_before", True, "默认应折叠"),
        ("list_visible_after", False, "没有展开"),
        ("list_visible_after_second_toggle", True, "没有折叠"),
        ("listed_count", 3, "清单列出"),
    ],
)
def test_judge_deg_s3_fails_on_each_broken_observation(field: str, value: object, token: str) -> None:
    obs = _s3_ok()
    obs[field] = value
    with pytest.raises(AssertionError, match=token):
        judge_deg_s3(**obs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# judge_deg_s4
# --------------------------------------------------------------------------
def test_judge_deg_s4_passes_and_fails_where_it_should() -> None:
    judge_deg_s4(legacy_badge_text="旧格式 · pkl", fresh_badge_texts=[])
    judge_deg_s4(legacy_badge_text="PKL", fresh_badge_texts=["json"])
    with pytest.raises(AssertionError, match="pkl"):
        judge_deg_s4(legacy_badge_text="旧格式", fresh_badge_texts=[])
    with pytest.raises(AssertionError, match="新格式书"):
        judge_deg_s4(legacy_badge_text="pkl", fresh_badge_texts=["pkl"])


# --------------------------------------------------------------------------
# 降级构造：真的落盘，且生产读取器读得回
# --------------------------------------------------------------------------
def test_make_notes_stale_writes_a_production_readable_file_with_a_stale_fingerprint(tmp_path: Path) -> None:
    from reader3_app.notes_service import load_annotations

    books = tmp_path / "books"
    books.mkdir()
    records = make_notes_stale(books, "b_data")
    assert [r["id"] for r in records] == [deg.DEG_S1_ANNOTATION["id"]]
    loaded = load_annotations(str(books), "b_data")
    assert [a.id for a in loaded] == [deg.DEG_S1_ANNOTATION["id"]], "生产读取器读不回预置的那条"
    payload = json.loads((books / "b_data" / "notes.json").read_text(encoding="utf-8"))
    assert payload[deg.NOTES_FINGERPRINT_KEY] == deg.STALE_FINGERPRINT
    assert read_notes_raw(books, "b_data") == records
    assert read_notes_raw(books, "nope_data") == []


def test_write_stale_index_meta_is_readable_by_the_production_index(tmp_path: Path) -> None:
    from reader3_app.vector_search import SPACE, BookVectorIndex, _current_model_name

    books = tmp_path / "books"
    (books / "b_data").mkdir(parents=True)
    path = write_stale_index_meta(books, "b_data")
    assert path == books / "b_data" / "chroma_db" / "index_meta.json"
    meta = BookVectorIndex("b_data", books_dir=str(books))._read_meta()
    assert meta is not None, "生产的 _read_meta 读不回这份 meta"
    assert meta["status"] == "indexed" and meta["space"] == SPACE and meta["model_name"] == _current_model_name()
    assert meta[deg.NOTES_FINGERPRINT_KEY] == deg.STALE_FINGERPRINT


def test_make_legacy_format_book_strips_new_format_files_and_is_listed_as_pkl_only(tmp_path: Path) -> None:
    books = tmp_path / "books"
    src = books / "smoke_data"
    (src / "chroma_db").mkdir(parents=True)
    (src / "book.pkl").write_bytes(b"pkl")
    (src / "manifest.json").write_text("{}", encoding="utf-8")
    (src / "chapters.jsonl").write_text("", encoding="utf-8")
    (src / "chroma_db" / "x").write_text("x", encoding="utf-8")

    legacy = make_legacy_format_book(books, "smoke_data", "legacy_pkl_data")
    assert legacy == books / "legacy_pkl_data"
    assert (legacy / "book.pkl").is_file()
    assert not (legacy / "manifest.json").exists() and not (legacy / "chapters.jsonl").exists()
    assert not (legacy / "chroma_db").exists(), "复制旧格式书时不该把索引也带过去"
    assert pkl_only_book_ids(books) == ["legacy_pkl_data"], "smoke_data 有新格式文件，不该被算成只有 pkl"

    with pytest.raises(ValueError, match="_data"):
        make_legacy_format_book(books, "smoke_data", "legacy")
    remove_book_dir(legacy)
    assert not legacy.exists()


_HEALTH_SERVER = (
    "import os, sys\n"
    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
    "class H(BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        body = ('allow_pickle=' + os.environ.get('READER3_ALLOW_PICKLE', '')).encode()\n"
    "        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)\n"
    "    def log_message(self, *a): pass\n"
    "HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n"
)


# 在**父进程**里 urllib.request.urlopen 打一个真的子进程 server（回环）。
# tests/fixtures/deg_assertions.py 是冻结路径，而它 :357 的重试循环 catch
# (URLError, ConnectionError, OSError)——少标一个的表现是偶发红，不是稳定红。
# 名单锁在 tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS。
@pytest.mark.real_loopback_socket
def test_pickle_fallback_server_boots_a_real_process_with_the_env_var_set(tmp_path: Path) -> None:
    import urllib.request

    with pickle_fallback_server(
        tmp_path, tmp_path, env={"PATH": os.environ.get("PATH", "")}, command=[sys.executable, "-c", _HEALTH_SERVER]
    ) as base:
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as r:
            assert r.status == 200
            assert r.read().decode() == "allow_pickle=1", "READER3_ALLOW_PICKLE=1 没有传进子进程"


# 在**父进程**里 urllib.request.urlopen 打一个真的子进程 server（回环）。
# tests/fixtures/deg_assertions.py 是冻结路径，而它 :357 的重试循环 catch
# (URLError, ConnectionError, OSError)——少标一个的表现是偶发红，不是稳定红。
# 名单锁在 tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS。
@pytest.mark.real_loopback_socket
def test_pickle_fallback_server_raises_instead_of_skipping_when_the_process_dies(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="退出码 7"):
        with pickle_fallback_server(
            tmp_path, tmp_path, env={"PATH": os.environ.get("PATH", "")}, command=[sys.executable, "-c", "import sys; sys.exit(7)"]
        ):
            pass
