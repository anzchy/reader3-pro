"""DEG-S1…S4 的**共享断言主体**：`acceptance_p3`（朴素横幅）与 `acceptance_4a4`（设计规格）共用。

任务书 §0.5 的结构要求：「4A.4 改版后**只改 testid 映射，断言语义不变**」。把断言主体抽成
一个共享函数、两组各传自己的映射表，「语义不变」就是结构上保证的，不是靠人记住。
`tests/unit/test_e2e_group_guard.py` 的第七条用例钉住：两组的跨模块调用集相等、全部来自
本模块、本模块在两个 acceptance 目录之外、两张映射表的键集合相同。

**为什么住在 `tests/fixtures/` 而不是某个 acceptance 目录里。** 落进 `acceptance_p3/` 会被
「acceptance 目录与 `suite_hash` 不相交」规则排除在哈希外，而它同时被两组依赖——一处改动
同时改变两组行为却没有任何计数变化。`tests/fixtures/` 由 `tests/conftest.py` 插进 `sys.path`
（unit 与 e2e 两条 lane 都能按裸模块名 import），而哈希命令只点名了该目录下的三个文件，
本文件不在其中（`tests/unit/test_e2e_group_guard.py` 第六条钉住这一点）。

**每个函数分两层**：`judge_deg_sN(...)` 是**纯判据**（只收观测值，抛 `AssertionError`，
unit lane 直接测正反两面）；`run_deg_sN(page, ...)` 是 Playwright 驱动（制造降级条件 →
读 DOM → 交给纯判据）。分层是为了让 14 条 skip 用例的**判据**在解 skip 之前就被跑过——
一条到期才第一次被执行的断言，与从没写过没有区别。

**判据一律比身份，不比条数**（2026-09-05 审计，四条 High/Medium 同一根因）。「几条 / 几个 /
几本」是最容易恰好撞对的观测量：`GET /api/notes` 交出**另一批**标注、未迁移清单列**另一批**书、
重建按钮长在**页面别处**、新格式书卡**整批没渲染**——四种都能让条数分毫不差地通过。所以：
`judge_deg_s1` 收 `served_records` 并逐字段比对（`S1_SERVED_IDENTITY_FIELDS`），
`judge_deg_s3` 收 `listed_book_ids` 比集合，`judge_deg_s2` 的按钮在**横幅内部**数，
`judge_deg_s4` 先要求每张书卡恰好 1 张再看角标。条数参数保留，但只是身份判据的一个投影；
两条否定断言（「新格式书不含 pkl 角标」「对照服务无告警条」）都先证明对象存在再断否定。

**模块级不 import playwright**：本文件被 unit lane 按裸模块名加载，浏览器依赖装歪不该让
一条纯判据用例红在与它无关的地方。Playwright 只在 `run_*` 函数体内 import。

**制造降级条件的四个抓手，各自是哪一层的事实**（解 skip 的人先核这一段）：

* **S1**：`notes.json` 顶层的书指纹键。ADR-0009 §Context 写明「`book_fingerprint()` 是
  notes/chroma 判定 stale 的唯一依据」。012 WI-2a 起 `notes_service.NOTES_FINGERPRINT_KEY` 定下
  这个键（每次保存原样保留）。本模块以同名的 `NOTES_FINGERPRINT_KEY = "book_fingerprint"`
  写入一个必然不匹配的值；两个常量的相等由单元测试 N6-01 钉住，改名要两处一起改。
* **S2**：`chroma_db/index_meta.json`。`vector_search.BookVectorIndex._stale_reason` 按
  `status` / `space` / `model_name` / `chunk_count` 判硬失效，012 WI-2a.7 起最后再比
  `book_fingerprint`。本模块写一份除指纹外全部「看起来已索引」的 meta ＋ 一个错的
  `book_fingerprint`：书有 `manifest.json` 时，这就是真实的软失效（`stale_reason == "fingerprint"`，
  `status` 保持 `indexed`，查询照常服务）；pkl-only 的书指纹判断不了，这份 meta 仍不算失效。
* **S3**：`READER3_ALLOW_PICKLE=1` **在模块导入时读**（ADR-0007 的 A2 条款），session 级
  `live_server` 复用不了，必须另起一个服务进程（`pickle_fallback_server`）。**它不用
  `pytest.skip` 表达失败**——起不来就抛 `RuntimeError`，那是红，不是跳过。
* **S4**：「旧格式书」= 只有 `book.pkl`、没有 `manifest.json` ＋ `chapters.jsonl` 的书目录。
  Phase 3 之后 `process_epub` 双写，沙箱里的书都是新格式；把一本复制成 `*_data` 并删掉两个
  新格式文件，就是一本旧格式书（`make_legacy_format_book`）。今天所有书都只有 pkl，删除是
  no-op，构造仍然成立。

testid 全部取自前端计划 `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md`
§4 WI-1…WI-5 的「涉及 testid」栏与设计规格 §6.4；映射表的键集合由 `DEG_TESTID_KEYS` 钉死。
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Iterator, List, Mapping, Optional, Sequence, Union

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from playwright.sync_api import Page

PathLike = Union[str, Path]

# ---------------------------------------------------------------------------
# 映射表的键（唯一定义处）与文案要求（定义类·验于 010）
# ---------------------------------------------------------------------------

#: 两张 testid 映射表都必须恰好有这些键。值可以不同（4A.4 换的就是 testid），键不同就是语义漂移。
DEG_TESTID_KEYS: FrozenSet[str] = frozenset(
    {
        # DEG-S1 标注 stale（阅读器）
        "s1_banner",  # 顶部横幅容器
        "s1_excerpt",  # 「查看原文摘录」入口
        "s1_stale_badge",  # Notes 面板逐条角标
        "s1_notes_rail",  # 打开 Notes 面板的按钮
        "s1_notes_panel",  # Notes 面板容器
        # DEG-S2 索引 stale（书库 ＋ 搜索面板）
        "s2_card",  # 书卡（带 data-book-id 判别位）
        "s2_status_stale",  # 书卡第五态
        "s2_search_tab",  # 打开搜索面板
        "s2_banner",  # 搜索面板顶部提示条
        "s2_reindex",  # 重建按钮
        # DEG-S3 pickle 回退告警（全局）
        "s3_lib_banner",
        "s3_rd_banner",
        "s3_toggle",  # 展开/折叠未迁移书目清单
        "s3_list",  # 清单容器
        # DEG-S4 存储格式角标（书库）
        "s4_card",
        "s4_badge",  # `storage_format` 角标
    }
)

#: DEG-S1 横幅文案必须同时含这两个片段（前端计划 WI-2：「少了『未删除』三个字，用户会以为数据没了」）。
DEG_S1_REQUIRED_PHRASES = ("暂停套用", "未删除")
#: DEG-S2 搜索面板提示条的文案片段（设计规格 §6.4：「索引已过期，结果可能不全」）。
DEG_S2_BANNER_PHRASE = "索引已过期"
#: 第五态**不得**冒充「未索引」（前端计划 WI-3：`|| STATUS_META.not_indexed` 本身就是 bug）。
NOT_INDEXED_LABEL = "未索引"
#: 书卡第五态自己的规范文案片段。**与横幅那条是两个独立的定义**，尽管今天字面相同：
#: 横幅住在搜索面板（`lib-degrade-s2`），第五态住在书卡（`lib-status-stale`），两处可以
#: 各自改文案。合成一个常量等于把「两处都要说对」偷偷降级成「一处说对就行」。
#:
#: **为什么光有 `lib-status-stale` 这个 testid 还不够。** 前端计划 WI-3 的锅正是
#: `STATUS_META[status] || STATUS_META.not_indexed`：渲染器可以在 stale 的槽位里填**任何**
#: 一态的文案。原判据只查「非空且不含『未索引』」，于是一本 stale 书被标成「已索引」照样绿——
#: 那恰是 DEG-S2 要消灭的形状（用户以为结果是全的）。判据必须落在文案本身上。
DEG_S2_STALE_STATUS_PHRASE = "索引已过期"
#: ADR-0009：`storage_format(book_id) -> Literal["json", "pkl"]`。角标文案里要能看到旧格式的字面。
STORAGE_FORMAT_PKL = "pkl"

#: notes.json 顶层的书指纹键与一个必然不匹配的值（见文件头 S1 一节）。
NOTES_FINGERPRINT_KEY = "book_fingerprint"
STALE_FINGERPRINT = "deg-stale-fingerprint-0000000000"

#: 预置给 S1 的那条标注：id / created_at 写死（§0 第五条纪律：守恒基准必须是字面量）。
DEG_S1_ANNOTATION = {
    "id": "wi17-deg-s1-marker",
    "chapter_index": 0,
    "type": "marker",
    "color": "yellow",
    "quote": "Alpha prose",
    "created_at": "2026-01-01T00:00:00+00:00",
}
DEG_S1_ANCHOR = "Alpha prose."

#: 旧格式书的目录名。必须以 `_data` 结尾（`server.py` 只扫这种目录），且不与 `E2E_BOOKS` 撞名。
LEGACY_BOOK_ID = "legacy_pkl_data"
NEW_FORMAT_FILES = ("manifest.json", "chapters.jsonl")

#: DEG-S3 未迁移书目清单里，每一项**必须**带的稳定标识属性。取 ADR-0014 闭合清单里的
#: `data-book-id`（书目录名取值无界，正是该清单要覆盖的那一类），所以不新增任何 testid。
#: 判据要的是**这批书是哪几本**，不是「有几本」——条数相等而书目全错，是最容易通过的错。
LIST_ITEM_BOOK_ID_ATTR = "data-book-id"

#: `GET /api/notes` 交出的记录与 `notes.json` 上的记录必须逐字段相等的字段清单。
#: 两个字段**有意**不在里面，各有各的合法理由：
#:   * `orphaned` —— 服务端每次读都按当前 spine 重算（`_refresh_orphaned_annotations`），
#:     盘上那一份是上次写入时的快照，两者不等是设计使然；
#:   * `note_text` —— 服务端交出前做 `html.unescape`，与盘上的转义形态可以合法地不同。
#: 其余字段是「stale 只暂停套用、不改内容」这条契约的可观测面：任何一项对不上，都说明
#: 服务端在降级路径上动了用户数据。
S1_SERVED_IDENTITY_FIELDS = (
    "id",
    "book_id",
    "chapter_index",
    "type",
    "color",
    "quote",
    "prefix",
    "suffix",
    "position",
    "cfi",
    "created_at",
)

STARTUP_TIMEOUT_S = 60


# ---------------------------------------------------------------------------
# 映射表校验
# ---------------------------------------------------------------------------


def require_testids(testids: Mapping[str, str], *, where: str) -> None:
    """键集合必须恰好是 `DEG_TESTID_KEYS`，值必须是非空字符串。在碰 `page` 之前抛，让错误落在最近处。"""
    keys = set(testids)
    missing = sorted(DEG_TESTID_KEYS - keys)
    unknown = sorted(keys - DEG_TESTID_KEYS)
    if missing or unknown:
        raise AssertionError(
            f"{where} 的 testid 映射表键集合不对：缺 {missing}，多 {unknown}。"
            "键集合的唯一定义处是 deg_assertions.DEG_TESTID_KEYS；4A.4 只许改值，不许改键。"
        )
    bad = sorted(k for k, v in testids.items() if not isinstance(v, str) or not v.strip())
    if bad:
        raise AssertionError(f"{where} 的 testid 映射表里这些键的值不是非空字符串：{bad}")


# ---------------------------------------------------------------------------
# 制造降级条件（纯文件系统 / 子进程；unit lane 可测）
# ---------------------------------------------------------------------------


def _notes_path(books_dir: PathLike, book_id: str) -> Path:
    return Path(books_dir) / book_id / "notes.json"


def make_notes_stale(books_dir: PathLike, book_id: str) -> List[Dict[str, Any]]:
    """预置一条标注（经生产 `save_annotations` 写盘），再把顶层指纹改成必然不匹配的值。返回预置后的标注列表。"""
    from reader3_app.models.annotations import Annotation
    from reader3_app.notes_service import save_annotations

    record = dict(DEG_S1_ANNOTATION)
    record["book_id"] = book_id
    path = _notes_path(books_dir, book_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_annotations(str(books_dir), book_id, [Annotation.from_dict(record)])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[NOTES_FINGERPRINT_KEY] = STALE_FINGERPRINT
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return list(payload["annotations"])


def read_notes_raw(books_dir: PathLike, book_id: str) -> List[Dict[str, Any]]:
    path = _notes_path(books_dir, book_id)
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8"))["annotations"])


def write_stale_index_meta(books_dir: PathLike, book_id: str) -> Path:
    """写一份「除指纹外看起来已索引」的 `chroma_db/index_meta.json`。返回文件路径。"""
    from reader3_app.vector_search import SPACE, _current_model_name

    meta_path = Path(books_dir) / book_id / "chroma_db" / "index_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "status": "indexed",
        "space": SPACE,
        "model_name": _current_model_name(),
        "chunk_count": 1,
        NOTES_FINGERPRINT_KEY: STALE_FINGERPRINT,
        "indexed_at": "2026-01-01T00:00:00+00:00",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def make_legacy_format_book(books_dir: PathLike, source_book_id: str, legacy_book_id: str = LEGACY_BOOK_ID) -> Path:
    """把一本沙箱书复制成只有 `book.pkl` 的旧格式书。返回新目录；调用方在 finally 里 `remove_book_dir`。"""
    if not legacy_book_id.endswith("_data"):
        raise ValueError(f"书目录名必须以 _data 结尾（server.py 只扫这种目录）：{legacy_book_id!r}")
    src = Path(books_dir) / source_book_id
    dst = Path(books_dir) / legacy_book_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("chroma_db", "notes.json", "ai_conversations"))
    for name in NEW_FORMAT_FILES:
        (dst / name).unlink(missing_ok=True)
    if not (dst / "book.pkl").is_file():
        raise RuntimeError(f"{dst} 里没有 book.pkl，构造不出旧格式书")
    return dst


def remove_book_dir(path: PathLike) -> None:
    """删掉注入的那本降级书。**不吞错误**——删不掉必须当场炸。

    原实现是 `shutil.rmtree(..., ignore_errors=True)`。它住在 `run_deg_s4` 的 `finally` 里，
    而那本 `legacy_pkl_data` 是**注入 session 级书库**的：删失败（权限、残留句柄、目录被占）
    时静默返回，之后同一 session 里每一条数书、遍历书库、断书卡集合的用例都会多看见一本书，
    红在与它八竿子打不着的地方。清理失败要么不存在，要么必须点名路径地喊出来。

    「目录本来就不在」不算失败：那正是本函数要达到的终态，且在 `finally` 里对它抛错会把
    真正的失败原因（body 里那个异常）盖掉。
    """
    target = Path(path)
    try:
        shutil.rmtree(target)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"注入的降级书目录删不掉：{target} → {exc}。"
            "它还在 session 级书库里，后面每一条按书库集合断言的用例都会被它污染"
        ) from exc
    if target.exists():
        raise RuntimeError(
            f"rmtree 没报错，但 {target} 仍然存在——注入的降级书留在了 session 级书库里"
        )


def pkl_only_book_ids(books_dir: PathLike) -> List[str]:
    """沙箱书库里「只有 pkl、没有新格式文件」的书——DEG-S3 清单应当列出的那些。"""
    out: List[str] = []
    for d in sorted(Path(books_dir).iterdir()):
        if d.is_dir() and d.name.endswith("_data") and (d / "book.pkl").is_file():
            if not all((d / n).is_file() for n in NEW_FORMAT_FILES):
                out.append(d.name)
    return out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def pickle_fallback_server(
    books_dir: PathLike,
    log_dir: PathLike,
    *,
    env: Optional[Mapping[str, str]] = None,
    command: Optional[Sequence[str]] = None,
    startup_timeout_s: float = STARTUP_TIMEOUT_S,
) -> Iterator[str]:
    """另起一个 `READER3_ALLOW_PICKLE=1` 的服务进程，产出 base URL。

    与 `tests/e2e/conftest.py::live_server` 同一套配方（空闲端口、`--port`、轮询 `/api/health`、
    日志落文件）。**不复用 `live_server`**：环境变量在服务模块导入时读，同一个进程改不了。
    **失败一律抛 `RuntimeError`，不 `pytest.skip`**——它住在本模块而不是 `acceptance_p3/conftest.py`
    （组目录不能有 conftest，理由见 `scripts/lint_e2e_groups.py`），所以 skip 轴静态性质的域 R
    管不到它；矩阵因此要求这里用异常表达失败，起不来就是红。

    `env` 缺省时取 `conftest._server_env(books_dir)`（e2e 运行期裸名 `conftest` 就是
    `tests/e2e/conftest.py`），本函数只追加 `READER3_ALLOW_PICKLE=1`。`command` 默认是 venv 里的
    `reader3-server --port N`；每个元素里的 `{port}` 会被替换成实际端口——unit 测试用它起一个
    只答 `/api/health` 的微型 HTTP 服务，以及一个立刻退出的命令，分别证明「起得来 ⇒ 产出 base URL
    且环境变量真的传进去了」与「启动即退出 ⇒ 抛错且带退出码」。
    """
    if env is None:
        from conftest import _server_env  # type: ignore[import-not-found]

        env = _server_env(Path(books_dir))
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    full_env = dict(env)
    full_env["READER3_ALLOW_PICKLE"] = "1"
    exe = Path(sys.executable).parent / "reader3-server"
    cmd = (
        [c.replace("{port}", str(port)) for c in command]
        if command is not None
        else [str(exe), "--port", str(port)]
    )
    log_path = Path(log_dir) / f"pickle-server-{port}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("w", encoding="utf-8")

    def _tail(limit: int = 4000) -> str:
        log_fh.flush()
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]

    try:
        server = subprocess.Popen(cmd, env=full_env, stdout=log_fh, stderr=subprocess.STDOUT, text=True)
    except OSError as exc:
        log_fh.close()
        raise RuntimeError(f"DEG-S3 的第二个服务进程起不来：{cmd} → {exc}") from exc
    try:
        deadline = time.monotonic() + startup_timeout_s
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(
                    f"DEG-S3 的第二个服务进程启动即退出（退出码 {server.returncode}）：{cmd}\n{_tail()}"
                )
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.1)
        else:
            server.kill()
            server.wait(timeout=10)
            raise RuntimeError(f"{startup_timeout_s}s 内没等到第二个服务的 /api/health：\n{_tail()}")
        yield base
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        log_fh.close()


# ---------------------------------------------------------------------------
# 纯判据（unit lane 直接测正反两面）
# ---------------------------------------------------------------------------


def judge_deg_s1(
    *,
    banner_text: str,
    records_before: Sequence[Mapping[str, Any]],
    records_after: Sequence[Mapping[str, Any]],
    served_records: Optional[Sequence[Mapping[str, Any]]] = None,
    served_count: Optional[int] = None,
    mark_count: int,
    badge_count: int,
    excerpt_text: str,
) -> None:
    """DEG-S1：横幅文案同时含「暂停套用」与「未删除」；交出来的**就是盘上那批**；正文零 `<mark>`；逐条角标数 == stale 条数；摘录含 quote 原文。

    **`served_records` 才是判据，`served_count` 只是它的一个投影。** 原实现只比条数，于是
    `GET /api/notes` 换掉、串章、张冠李戴地交出**另一批**标注，只要条数凑上就一路绿——而
    DEG-S1 要证的恰恰是「这一条没被动」。两个参数都保留是为了向后兼容既有调用点，但
    `served_records` 给了就以它为准（并顺带核对 `served_count` 与它自洽）；两个都不给，
    等于什么都没观测到，直接抛。
    """
    for phrase in DEG_S1_REQUIRED_PHRASES:
        if phrase not in banner_text:
            raise AssertionError(
                f"DEG-S1 横幅文案里没有「{phrase}」：{banner_text!r}。"
                "文案必须明说「标注暂停套用，未删除」——少了「未删除」用户会以为数据没了"
            )
    if list(records_after) != list(records_before):
        raise AssertionError(
            f"DEG-S1 之下 notes.json 的标注变了（stale 只停止套用，一条都不该动）：\n"
            f"  前：{list(records_before)}\n  后：{list(records_after)}"
        )
    if served_records is None and served_count is None:
        raise AssertionError(
            "judge_deg_s1 既没收到 served_records 也没收到 served_count——"
            "`GET /api/notes` 这一路根本没被观测，判据是空的"
        )
    served: Optional[List[Dict[str, Any]]] = (
        [dict(r) for r in served_records] if served_records is not None else None
    )
    if served is not None and served_count is not None and served_count != len(served):
        raise AssertionError(
            f"观测自相矛盾：served_count={served_count}，但 served_records 有 {len(served)} 条"
        )
    effective_count = len(served) if served is not None else int(served_count or 0)
    if effective_count != len(records_before):
        raise AssertionError(
            f"GET /api/notes 交出 {effective_count} 条，盘上 {len(records_before)} 条——服务端把 stale 标注吞掉了"
        )
    if served is not None:
        before_ids = [str(r.get("id")) for r in records_before]
        served_ids = [str(r.get("id")) for r in served]
        if len(set(served_ids)) != len(served_ids):
            raise AssertionError(f"GET /api/notes 交出的 id 有重复：{served_ids}")
        if sorted(served_ids) != sorted(before_ids):
            raise AssertionError(
                "GET /api/notes 交出的不是盘上那批标注（条数相同 ≠ 同一批）：\n"
                f"  盘上：{sorted(before_ids)}\n  交出：{sorted(served_ids)}"
            )
        by_id = {str(r.get("id")): r for r in served}
        for disk_record in records_before:
            rid = str(disk_record.get("id"))
            api_record = by_id[rid]
            for field in S1_SERVED_IDENTITY_FIELDS:
                if field not in disk_record:
                    continue
                if field not in api_record:
                    raise AssertionError(
                        f"GET /api/notes 交出的 id={rid} 少了字段 {field!r}：{api_record}"
                    )
                if api_record[field] != disk_record[field]:
                    raise AssertionError(
                        f"id={rid} 的 {field} 交出的是 {api_record[field]!r}，盘上是 "
                        f"{disk_record[field]!r}——stale 只暂停套用，不许改内容"
                    )
    if mark_count != 0:
        raise AssertionError(f"stale 之下正文里仍有 {mark_count} 个 rd-anno-span——标注套用没有停")
    if badge_count != len(records_before):
        raise AssertionError(
            f"Notes 面板的 stale 角标有 {badge_count} 个，stale 标注有 {len(records_before)} 条——要逐条标记，不是只在顶部放一条汇总"
        )
    quote = str(records_before[0]["quote"]) if records_before else ""
    if quote and quote not in excerpt_text:
        raise AssertionError(f"「查看原文摘录」给出的文本 {excerpt_text!r} 不含该标注的 quote 原文 {quote!r}")


def judge_deg_s2(*, status_text: str, banner_text: str, reindex_count: int) -> None:
    """DEG-S2：书卡第五态可见且不冒充「未索引」；搜索面板顶部提示条文案匹配；恰好一个重建按钮。"""
    if not status_text.strip():
        raise AssertionError("DEG-S2 书卡第五态的文案为空——第五态在视觉上等于不存在")
    if NOT_INDEXED_LABEL in status_text:
        raise AssertionError(
            f"DEG-S2 书卡第五态显示成了「{NOT_INDEXED_LABEL}」（{status_text!r}）——那是 `|| STATUS_META.not_indexed` 那个 bug 的形状，用户会去点「开始索引」"
        )
    if DEG_S2_BANNER_PHRASE not in banner_text:
        raise AssertionError(f"搜索面板顶部提示条文案里没有「{DEG_S2_BANNER_PHRASE}」：{banner_text!r}")
    if reindex_count != 1:
        raise AssertionError(f"提示条上的重建按钮应恰好 1 个，实际 {reindex_count} 个")
    # 最后一条：第五态的文案必须是**第五态自己的**，不是任意一句非「未索引」的话。
    #
    # 位置有意放在末尾。上面四条各自守着一个更早、更具体的失效模式（空文案 / 冒充未索引 /
    # 横幅文案 / 按钮基数），把这条插到中间会让那四条的失败消息被这一条抢走——一次
    # 「按钮数不对」的失败会被报成「文案不对」，把人指向错的地方。
    if DEG_S2_STALE_STATUS_PHRASE not in status_text:
        raise AssertionError(
            f"书卡第五态的文案 {status_text!r} 里没有「{DEG_S2_STALE_STATUS_PHRASE}」——"
            "「非空且不是『未索引』」不构成判据：一本 stale 书被标成「已索引」正好落在这个缝里，"
            "而那是 DEG-S2 要消灭的头号形状（用户以为搜索结果是全的）"
        )


def judge_deg_s3(
    *,
    control_lib_banner_count: int,
    library_banner_text: str,
    reader_banner_text: str,
    list_visible_before: bool,
    list_visible_after: bool,
    list_visible_after_second_toggle: bool,
    listed_count: int,
    expected_listed_count: int,
    listed_book_ids: Optional[Sequence[str]] = None,
    expected_book_ids: Optional[Sequence[str]] = None,
) -> None:
    """DEG-S3：对照服务上无告警条；pickle 服务上书库与阅读器**都**有，文案同一份；清单默认折叠、可展开再折叠、**列的是哪几本**正确。

    条数（`listed_count`）留着，但它不是判据的全部：一份列出了**别的**书的清单，只要长度
    撞上就通过原来的那条断言。`listed_book_ids` / `expected_book_ids` 成对给出时按**集合**
    逐个对，多一本少一本都点名。两个都不给等于只观测了长度——既有调用点仍能工作，但
    e2e 驱动 `run_deg_s3` 一律给。
    """
    if control_lib_banner_count != 0:
        raise AssertionError(
            f"未设 READER3_ALLOW_PICKLE 的服务上也出现了 {control_lib_banner_count} 个 S3 告警条——横幅常亮等于没有横幅"
        )
    if not library_banner_text.strip():
        raise AssertionError("pickle 服务的书库页没有 S3 告警条文案")
    if not reader_banner_text.strip():
        raise AssertionError("pickle 服务的阅读器页没有 S3 告警条文案——这是五条里唯一的全局降级，必须两页都出现")
    if library_banner_text.strip() != reader_banner_text.strip():
        raise AssertionError(
            f"两页的 S3 文案不一致（实现与文案各只有一份，见前端计划 WI-4 验收 7）：\n"
            f"  书库：{library_banner_text!r}\n  阅读器：{reader_banner_text!r}"
        )
    if list_visible_before:
        raise AssertionError("未迁移书目清单默认应折叠，实际一开始就可见")
    if not list_visible_after:
        raise AssertionError("点开关后未迁移书目清单没有展开")
    if list_visible_after_second_toggle:
        raise AssertionError("再点一次开关后清单没有折叠回去")
    if listed_count != expected_listed_count:
        raise AssertionError(
            f"清单列出 {listed_count} 本，沙箱里只有 pkl 的书有 {expected_listed_count} 本"
        )
    if (listed_book_ids is None) != (expected_book_ids is None):
        raise AssertionError(
            "listed_book_ids 与 expected_book_ids 必须成对给出——只给一半，比对就无从谈起"
        )
    if listed_book_ids is None or expected_book_ids is None:
        return
    listed = [str(b) for b in listed_book_ids]
    expected = [str(b) for b in expected_book_ids]
    if not expected:
        raise AssertionError(
            "沙箱里一本「只有 pkl」的书都没有——DEG-S3 的清单断言在这种书库上是空真的，"
            "先把降级条件造出来（`make_legacy_format_book`），别让一条永远成立的断言冒充证据"
        )
    if len(set(listed)) != len(listed):
        raise AssertionError(f"未迁移书目清单里有重复项：{listed}")
    extra = sorted(set(listed) - set(expected))
    missing = sorted(set(expected) - set(listed))
    if extra or missing:
        raise AssertionError(
            "未迁移书目清单列的不是「只有 pkl」的那批书（条数相等 ≠ 同一批）：\n"
            f"  多列了：{extra}\n  漏列了：{missing}\n"
            f"  清单：{sorted(listed)}\n  期望：{sorted(expected)}"
        )


def judge_deg_s4(
    *,
    legacy_badge_text: str,
    fresh_badge_texts: Sequence[str],
    legacy_cards_seen: Optional[int] = None,
    fresh_cards_seen: Optional[Mapping[str, int]] = None,
) -> None:
    """DEG-S4：两类书卡都**在**（各恰好一张）；旧格式书的角标文案含 `pkl`；新格式书要么没有角标，要么角标文案不含 `pkl`。

    **先证卡在，再证它没戴 pkl 角标。** 「新格式书的角标不含 pkl」是个否定断言，缺卡时它是
    空真的：一个把所有新格式书统统漏渲染的书库页，`fresh_badge_texts` 是空列表，原判据全绿。
    `fresh_cards_seen`（书 id → 该 id 在页面上解析出的书卡数）把「卡在」变成正向证据，
    每本必须恰好 1 张——0 张是漏渲染，≥2 张是重复渲染，两者都会让后面的角标断言失去意义。

    两个新参数可选，是为了兼容既有调用点；e2e 驱动 `run_deg_s4` 一律给。
    """
    if legacy_cards_seen is not None and legacy_cards_seen != 1:
        raise AssertionError(
            f"旧格式书 {LEGACY_BOOK_ID} 的书卡在书库页上解析出 {legacy_cards_seen} 张，期望恰好 1 张——"
            "S4 的正面（角标含 pkl）没有对象"
        )
    if fresh_cards_seen is not None:
        if not fresh_cards_seen:
            raise AssertionError(
                "一本新格式书都没传进来——「新格式书的角标不含 pkl」这条否定断言没有对象，是空真的"
            )
        bad = sorted((book_id, n) for book_id, n in fresh_cards_seen.items() if n != 1)
        if bad:
            raise AssertionError(
                f"这些新格式书的书卡不是恰好 1 张（书 id, 实际张数）：{bad}。"
                "缺卡时「角标不含 pkl」空真——漏渲染整批新格式书的书库页会全绿"
            )
    if STORAGE_FORMAT_PKL not in legacy_badge_text.lower():
        raise AssertionError(
            f"旧格式书的 storage_format 角标文案 {legacy_badge_text!r} 里看不到 {STORAGE_FORMAT_PKL!r}"
            "（ADR-0009：storage_format ∈ {json, pkl}）"
        )
    leaked = [t for t in fresh_badge_texts if STORAGE_FORMAT_PKL in t.lower()]
    if leaked:
        raise AssertionError(f"新格式书的角标也写着 pkl：{leaked}——角标没有区分两种格式")


# ---------------------------------------------------------------------------
# Playwright 驱动（e2e；playwright 只在函数体内 import）
# ---------------------------------------------------------------------------


def _card(page: "Page", card_testid: str, book_id: str):  # type: ignore[no-untyped-def]
    # 变量插值而不是把映射表下标写进 f-string：`{testids["x"]}` 里的引号会打断选择器 lint 的属性正则。
    return page.locator(f'[data-testid="{card_testid}"][data-book-id="{book_id}"]')


def run_deg_s1(page: "Page", base_url: str, books_dir: PathLike, book_id: str, testids: Mapping[str, str]) -> None:
    """制造 notes 指纹不匹配 → 打开阅读器 → 横幅 / 面板 / 正文 / API 四处观测 → 交给纯判据。"""
    require_testids(testids, where="run_deg_s1")
    from playwright.sync_api import expect

    from helpers import open_reader, scan_marks  # type: ignore[import-not-found]

    before = make_notes_stale(books_dir, book_id)
    frame = open_reader(page, base_url, book_id, int(DEG_S1_ANNOTATION["chapter_index"]), DEG_S1_ANCHOR)
    page.wait_for_load_state("networkidle")

    banner = page.get_by_test_id(testids["s1_banner"])
    expect(banner).to_be_visible()
    banner_text = banner.inner_text()

    page.get_by_test_id(testids["s1_excerpt"]).click()
    quote = str(DEG_S1_ANNOTATION["quote"])
    excerpt = page.get_by_text(quote, exact=False).first
    expect(excerpt).to_be_visible()
    excerpt_text = excerpt.inner_text()

    page.get_by_test_id(testids["s1_notes_rail"]).click()
    expect(page.get_by_test_id(testids["s1_notes_panel"])).to_be_visible()
    badge_count = page.get_by_test_id(testids["s1_stale_badge"]).count()

    resp = page.request.get(f"{base_url}/api/notes/{book_id}/{DEG_S1_ANNOTATION['chapter_index']}")
    served = resp.json().get("annotations", []) if resp.ok else []
    mark_count = len(scan_marks(frame)["texts"])

    judge_deg_s1(
        banner_text=banner_text,
        records_before=before,
        records_after=read_notes_raw(books_dir, book_id),
        # 交出去的是**记录本身**，不只是条数：判据要比 id 与逐字段内容。
        served_records=served,
        served_count=len(served),
        mark_count=mark_count,
        badge_count=badge_count,
        excerpt_text=excerpt_text,
    )


def run_deg_s2(page: "Page", base_url: str, books_dir: PathLike, book_id: str, testids: Mapping[str, str]) -> None:
    """制造 chroma 指纹不匹配 → 书库页书卡第五态 → 搜索面板提示条 → 纯判据。"""
    require_testids(testids, where="run_deg_s2")
    from playwright.sync_api import expect

    meta_path = write_stale_index_meta(books_dir, book_id)
    try:
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        status = _card(page, testids["s2_card"], book_id).get_by_test_id(testids["s2_status_stale"])
        expect(status).to_be_visible()
        status_text = status.inner_text()

        page.get_by_test_id(testids["s2_search_tab"]).click()
        banner = page.get_by_test_id(testids["s2_banner"])
        expect(banner).to_be_visible()
        judge_deg_s2(
            status_text=status_text,
            banner_text=banner.inner_text(),
            # 在**横幅内部**数，不是全页数。设计规格 §6.4 要的是「提示条上的重建按钮」——
            # 全页计数会被页面上任何别处的重建按钮（书卡上的、批量索引面板里的）满足，
            # 于是一条压根没长按钮的提示条也能过。作用域就是断言的一部分。
            reindex_count=banner.get_by_test_id(testids["s2_reindex"]).count(),
        )
    finally:
        shutil.rmtree(meta_path.parent, ignore_errors=True)


def run_deg_s3(
    page: "Page",
    control_base_url: str,
    pickle_base_url: str,
    books_dir: PathLike,
    book_id: str,
    testids: Mapping[str, str],
) -> None:
    """对照服务无告警条；pickle 服务两页都有、文案同一份；清单折叠/展开/条数 → 纯判据。"""
    require_testids(testids, where="run_deg_s3")
    from playwright.sync_api import expect

    from helpers import open_reader  # type: ignore[import-not-found]

    page.goto(f"{control_base_url}/")
    page.wait_for_load_state("networkidle")
    control_count = page.get_by_test_id(testids["s3_lib_banner"]).count()

    page.goto(f"{pickle_base_url}/")
    page.wait_for_load_state("networkidle")
    lib_banner = page.get_by_test_id(testids["s3_lib_banner"])
    expect(lib_banner).to_be_visible()
    library_text = lib_banner.inner_text()
    listing = page.get_by_test_id(testids["s3_list"])
    visible_before = listing.count() > 0 and listing.is_visible()
    page.get_by_test_id(testids["s3_toggle"]).click()
    expect(listing).to_be_visible()
    items = listing.get_by_role("listitem").all()
    listed_count = len(items)
    # 每一项的稳定标识，而不是「有几项」。缺 data-book-id 就当场抛：一份「渲染得出来但
    # 认不出是哪几本」的清单，对「哪些书还没迁移」这个问题一点用都没有，对判据同样没用。
    listed_book_ids: List[str] = []
    for index, item in enumerate(items):
        book_attr = item.get_attribute(LIST_ITEM_BOOK_ID_ATTR)
        if not book_attr:
            raise AssertionError(
                f"未迁移书目清单的第 {index} 项没有 {LIST_ITEM_BOOK_ID_ATTR}（文本：{item.inner_text()!r}）——"
                "清单必须能被机器认出列的是哪几本书，否则条数对了也证明不了列对了"
            )
        listed_book_ids.append(book_attr)
    page.get_by_test_id(testids["s3_toggle"]).click()
    expect(listing).to_be_hidden()
    visible_after_second = listing.is_visible()

    open_reader(page, pickle_base_url, book_id, int(DEG_S1_ANNOTATION["chapter_index"]), DEG_S1_ANCHOR)
    rd_banner = page.get_by_test_id(testids["s3_rd_banner"])
    expect(rd_banner).to_be_visible()

    judge_deg_s3(
        control_lib_banner_count=control_count,
        library_banner_text=library_text,
        reader_banner_text=rd_banner.inner_text(),
        list_visible_before=visible_before,
        list_visible_after=True,
        list_visible_after_second_toggle=visible_after_second,
        listed_count=listed_count,
        expected_listed_count=len(pkl_only_book_ids(books_dir)),
        listed_book_ids=listed_book_ids,
        expected_book_ids=pkl_only_book_ids(books_dir),
    )


def run_deg_s4(
    page: "Page",
    base_url: str,
    books_dir: PathLike,
    source_book_id: str,
    fresh_book_ids: Sequence[str],
    testids: Mapping[str, str],
) -> None:
    """造一本旧格式书 → 书库页两类书卡的角标 → 纯判据。用完删掉那本书。"""
    require_testids(testids, where="run_deg_s4")
    from playwright.sync_api import expect

    legacy_dir = make_legacy_format_book(books_dir, source_book_id, LEGACY_BOOK_ID)
    try:
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # 先数**书卡**，再看角标。缺卡时「角标不含 pkl」是空真的（见 judge_deg_s4），
        # 所以这里不能像原来那样只在 `badge.count()` 为真时才收集：那等于把「这本书压根
        # 没渲染出来」和「渲染出来了、没戴 pkl 角标」判成同一件事。
        legacy_card = _card(page, testids["s4_card"], LEGACY_BOOK_ID)
        legacy_cards_seen = legacy_card.count()
        fresh_cards_seen: Dict[str, int] = {}
        fresh_texts: List[str] = []
        for fresh_id in fresh_book_ids:
            card = _card(page, testids["s4_card"], fresh_id)
            seen = card.count()
            fresh_cards_seen[fresh_id] = seen
            if seen != 1:
                # 不在这里抛：整张表要收全，判据才能一次点名所有缺卡的书。
                continue
            badge = card.get_by_test_id(testids["s4_badge"])
            if badge.count():
                fresh_texts.append(badge.inner_text())

        legacy_badge_text = ""
        if legacy_cards_seen == 1:
            legacy_badge = legacy_card.get_by_test_id(testids["s4_badge"])
            expect(legacy_badge).to_be_visible()
            legacy_badge_text = legacy_badge.inner_text()

        judge_deg_s4(
            legacy_badge_text=legacy_badge_text,
            fresh_badge_texts=fresh_texts,
            legacy_cards_seen=legacy_cards_seen,
            fresh_cards_seen=fresh_cards_seen,
        )
    finally:
        remove_book_dir(legacy_dir)
