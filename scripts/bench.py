#!/usr/bin/env python3
"""性能基准 —— 六项指标的可重跑测量器（tasks/008-test-safety-net.md §6）。

**这个脚本存在的理由不是跑出六个数，是让半年后的人能拿同一把尺再量一次。**
012 换存储格式时唯一能回答「这次是优化还是劣化」的东西，就是「同一个脚本、同一
个口径、跑出来的新数与旧数」。所以每项都：跑多次、报中位数与全距（min–max）、
把环境戳一起写进 JSON。**单次采样不是基准**，它连自己的噪声有多大都说不出来。

任务书写「基准只记录、不设阈值门禁，等有了多次运行的方差数据再谈」——那份方差
数据就是本脚本的产出之一。`--repeat` 默认 5，每项的 `spread_pct` 直接告诉读的人
哪几项噪声大到还不配设门禁。

## 依赖口径

**脚本自身零第三方依赖，只用标准库**，与 `scripts/` 下其余五个脚本一致。但被测
对象是本仓库的生产代码，它要 fastapi / httpx / ebooklib —— 一个不 import 被测代码
的性能基准无法存在。折中因此是：**父进程纯标准库**（`--help`、聚合、写 JSON 都
不需要项目环境），**子进程 import 被测包**。所以正确的跑法是

    uv run python scripts/bench.py

裸 `python3 scripts/bench.py` 会在预检那一步给出明确的错误提示而不是一屏
ImportError。预检故意用一个独立子进程做，因为父进程一旦 import 了被测包，后面
所有「冷启动」测量就都不冷了。

## 进程模型：为什么每个采样都是一个新进程

三处 `@lru_cache`（`web.server.load_book_cached` maxsize=10、
`search_service.load_book_cached` maxsize=10、`search_service.load_book_index`
maxsize=4）加上 Python 自己的模块 import 缓存，意味着**同进程内的第二次永远不是
冷启动**。可选口径有两个：

  A. 全新进程（本脚本采用）—— 含解释器启动、import、模块级初始化，是用户按下
     `reader3-server` 到能服务第一个请求真正等的那段时间。
  B. 同进程内 `cache_clear()` 三处缓存 —— 更稳（无解释器启动噪声），但它测不到
     import 成本，而 import 恰恰是冷启动里最大的一块。

选 A，因为 §6 说这项是给「Phase 5 的启动体验」做对照的，用户等的是 A 不是 B。
代价是 A 的方差更大（解释器启动受系统调度影响），这一点在基准记录文档里写明。

书库同样每次采样重建一份全新的临时目录：`prepare` 这个 worker 先建库，
`cold_start` 再在另一个进程里量。如果复用同一份书库，第一次采样的 startup 会写下
`ai_meta.json`，第二次采样干的活就和第一次不是一回事了。

## 安全

所有落盘一律在 `tempfile.TemporaryDirectory()` 里。**绝不指向真实的 `books/`**：
`reader3.process_epub()` 会在输出目录旁开 staging 并 `os.replace` 覆盖，而标注是
用户产生的、错了不能重新生成的数据。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SRC_DIR = REPO_ROOT / "src"

#: worker 把结果写在带这个前缀的一行上。用行前缀而不是整份 stdout，是因为被测代码
#: 会往 stdout 打日志（`load_book_cached` 里就有一处 `print`），整份解析会被它污染。
MARKER = "@@BENCH@@ "

#: 首页 TTFB 要画成曲线，不是一个点 —— 只测 20 本那一个点，这项指标唯一能暴露的
#: 东西（`library_view` 对 N 本书逐本 unpickle 的 O(n) 扫描）就看不见了。
DEFAULT_SIZES = (1, 5, 10, 20)

#: `search_service._normalize_with_map` 的重复计算只有在「同一批书被反复搜」时
#: 才现形。搜一次的计数是「必要开销」，搜三次减搜一次才是「浪费」。
LIBRARY_SEARCH_ROUNDS = 3


# --------------------------------------------------------------------------- #
# 通用小工具（父子进程共用）
# --------------------------------------------------------------------------- #


def rss_bytes() -> int:
    """当前进程的峰值 RSS，单位统一成字节。

    `ru_maxrss` 的单位**随平台变**：macOS/BSD 是字节，Linux 是 KiB。写死一种换算，
    跨机对比时就是 1024 倍的错 —— 而这种错不会让任何断言变红，只会让下一个人得出
    「换存储格式后内存降了三个数量级」这种结论。
    """
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw) if sys.platform == "darwin" else int(raw) * 1024


def emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(MARKER + json.dumps(payload) + "\n")
    sys.stdout.flush()


def worker_syspath() -> None:
    for p in (str(SRC_DIR), str(FIXTURES_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


# --------------------------------------------------------------------------- #
# worker: prepare —— 造一份一次性的合成书库
# --------------------------------------------------------------------------- #


def worker_prepare(args: argparse.Namespace) -> None:
    """在 `--books-dir` 下建 N 本合成书；`--huge` 再加一本三百万字符的。

    走 pickle 直写而不是 `process_epub`，理由与 `synthetic_library` 的 docstring
    同：被测的是**读路径**，它只见得到 `book.pkl`。EPUB 解析成本由 `ingest`
    这个 worker 单独量，两者是两个口径，不该混进一个数里。
    """
    worker_syspath()
    from synthetic_library import make_synthetic_library

    books = Path(args.books_dir)
    make_synthetic_library(books, count=args.size)
    if args.huge:
        _write_huge_book(books, chars=args.chars)
    emit({"ok": True, "size": args.size, "huge": bool(args.huge)})


def _write_huge_book(books_dir: Path, *, chars: int) -> Path:
    """一本单章三百万字符的书，正文末尾放 needle。

    needle 放最后，搜它才会走完整扫；放开头量到的是提前退出。
    """
    import pickle
    from datetime import datetime

    from epub_corpus import huge_chapter_text
    from reader3_app.reader3 import Book, BookMetadata, ChapterContent, TOCEntry

    text = huge_chapter_text(chars, needle=" HUGENEEDLE")
    out = books_dir / "huge_data"
    (out / "images").mkdir(parents=True, exist_ok=True)
    book = Book(
        metadata=BookMetadata(
            title="The Long One",
            language="en",
            authors=["Anon"],
            identifiers=["urn:uuid:reader3-huge"],
        ),
        spine=[
            ChapterContent(
                id="c1",
                href="text/c1.xhtml",
                title="The Long One",
                content=f"<p>{text}</p>",
                text=text,
                order=0,
            )
        ],
        toc=[TOCEntry(title="The Long One", href="text/c1.xhtml", file_href="text/c1.xhtml", anchor="")],
        images={},
        source_file="huge.epub",
        processed_at=datetime(2026, 8, 24, 0, 0, 0).isoformat(),
    )
    with open(out / "book.pkl", "wb") as f:
        pickle.dump(book, f)
    return out


# --------------------------------------------------------------------------- #
# worker: cold_start —— 指标 1
# --------------------------------------------------------------------------- #


def worker_cold_start(args: argparse.Namespace) -> None:
    """全新进程：import → startup 扫描 → 首个请求返回。

    三段分开报，因为它们会被不同的改动影响：import 受依赖树影响，startup 受书库
    规模影响，首个请求受模板与 unpickle 影响。合成一个数就分不出来是谁变了。
    """
    worker_syspath()
    os.environ["READER3_BOOKS_DIR"] = args.books_dir

    t0 = time.perf_counter()
    from reader3_app.web import server

    t1 = time.perf_counter()
    from fastapi.testclient import TestClient

    t2 = time.perf_counter()
    client = TestClient(server.app)
    with client:  # 上下文管理器才会跑 startup 事件（book_uuid_resolver.scan()）
        t3 = time.perf_counter()
        response = client.get("/")
        t4 = time.perf_counter()

    emit(
        {
            "import_server_ms": (t1 - t0) * 1000,
            "import_testclient_ms": (t2 - t1) * 1000,
            "startup_scan_ms": (t3 - t2) * 1000,
            "first_page_ms": (t4 - t3) * 1000,
            "ready_to_serve_ms": (t3 - t0) * 1000,
            "status_code": response.status_code,
            "rss_bytes": rss_bytes(),
        }
    )


# --------------------------------------------------------------------------- #
# worker: ttfb —— 指标 6
# --------------------------------------------------------------------------- #


def worker_ttfb(args: argparse.Namespace) -> None:
    """冷进程里首页的第一个响应耗时。含 Jinja 模板渲染，不含解释器启动与 import。

    口径故意排除 import：import 与书库规模无关，把它算进来会给曲线加一个几百毫秒
    的常数项，把线性关系压成一条看起来很平的线。
    """
    worker_syspath()
    os.environ["READER3_BOOKS_DIR"] = args.books_dir

    from fastapi.testclient import TestClient

    from reader3_app.web import server

    client = TestClient(server.app)
    with client:
        t0 = time.perf_counter()
        response = client.get("/")
        t1 = time.perf_counter()
        body_len = len(response.content)

    emit(
        {
            "ttfb_ms": (t1 - t0) * 1000,
            "status_code": response.status_code,
            "body_bytes": body_len,
            "rss_bytes": rss_bytes(),
        }
    )


# --------------------------------------------------------------------------- #
# worker: query —— 指标 2
# --------------------------------------------------------------------------- #


def worker_query(args: argparse.Namespace) -> None:
    """首次查询 vs 二次相同查询，三种作用域各一对。

    **必须成对报。** 孤零零一个「二次耗时」量不出 `lru_cache` 的收益 —— 收益是
    两者的差，不是任何一个的绝对值。
    """
    worker_syspath()
    os.environ["READER3_BOOKS_DIR"] = args.books_dir

    from fastapi.testclient import TestClient

    from reader3_app.web import server

    out: Dict[str, Any] = {}
    client = TestClient(server.app)
    with client:

        def timed(path: str, params: Dict[str, Any]) -> float:
            t0 = time.perf_counter()
            r = client.get(path, params=params)
            elapsed = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                raise RuntimeError(f"{path} -> {r.status_code}: {r.text[:200]}")
            return elapsed

        # **顺序是算过的，不是随手排的。** `load_book_index` 是 maxsize=4，谁先跑，
        # 谁就把后面那一对的「首次」变成缓存命中，配出一个假的加速比。全库搜索会
        # 走遍 21 本、把缓存冲成「最后访问的 4 本」，所以它必须排在最前：之后测的
        # 小书与大部头都保证已被淘汰，三对的「首次」都是真的冷。
        lib = {"q": "tide", "mode": "keyword"}
        out["library_first_ms"] = timed("/api/search/library", lib)
        out["library_second_ms"] = timed("/api/search/library", lib)

        # 小书（8 章 × 2000 字符）：量的是缓存机制本身的开销尺度
        small = {"q": "tide", "mode": "keyword"}
        out["inbook_small_first_ms"] = timed("/api/search/synth03_data", small)
        out["inbook_small_second_ms"] = timed("/api/search/synth03_data", small)

        # 大部头（单章三百万字符）：量的是缓存能省下多少真实工作
        huge = {"q": "HUGENEEDLE", "mode": "keyword"}
        out["inbook_huge_first_ms"] = timed("/api/search/huge_data", huge)
        out["inbook_huge_second_ms"] = timed("/api/search/huge_data", huge)

    out["rss_bytes"] = rss_bytes()
    emit(out)


# --------------------------------------------------------------------------- #
# worker: rss —— 指标 3
# --------------------------------------------------------------------------- #


def worker_rss(args: argparse.Namespace) -> None:
    """峰值 RSS 的四个断点。

    `ru_maxrss` 是**峰值**不是当前值，所以它只增不减：后一个断点的数字里含前一个
    的峰。报增量而不是各自的绝对值会更好看，但那是编的 —— 峰值本来就不可分解。
    这里如实报累积值，读的人自己看台阶。
    """
    worker_syspath()
    os.environ["READER3_BOOKS_DIR"] = args.books_dir

    baseline = rss_bytes()
    from fastapi.testclient import TestClient

    from reader3_app.web import server

    after_import = rss_bytes()
    client = TestClient(server.app)
    with client:
        client.get("/")
        after_library_page = rss_bytes()
        client.get("/api/search/library", params={"q": "tide", "mode": "keyword"})
        after_library_search = rss_bytes()
        client.get("/api/search/huge_data", params={"q": "HUGENEEDLE", "mode": "keyword"})
        after_huge_search = rss_bytes()

    emit(
        {
            "baseline_bytes": baseline,
            "after_import_bytes": after_import,
            "after_library_page_bytes": after_library_page,
            "after_library_search_bytes": after_library_search,
            "after_huge_search_bytes": after_huge_search,
        }
    )


# --------------------------------------------------------------------------- #
# worker: counters —— 指标 4 与 5
# --------------------------------------------------------------------------- #


def _install_unpickle_counters() -> Dict[str, List[int]]:
    """给三处 loader 各自的 `_Reader3Unpickler` 装计数，外加 `pickle.load` 兜底。

    **数的是真正的 unpickle 次数，不是 `load_book_cached()` 的调用次数。** 后者含
    缓存命中，而 A5 要合并三处 loader 想省的是前者。包装在这里做，不改 `src/`：
    为了好测去改被测代码，测到的就不是生产行为了。
    """
    import pickle

    import reader3_app.search_service as search_service
    from reader3_app.web import server

    mods: Dict[str, Any] = {"web.server": server, "search_service": search_service}
    try:
        import reader3_app.vector_search as vector_search
    except ImportError:
        # chromadb 是可选依赖；装不上时这一处 loader 报 None 而不是 0 ——
        # 「没测到」和「测到了 0 次」是两件事，混成一个 0 会读成「这处 loader 是死代码」。
        mods["vector_search"] = None
    else:
        mods["vector_search"] = vector_search

    counts: Dict[str, List[int]] = {}
    for name, mod in mods.items():
        if mod is None:
            continue
        box = [0]
        counts[name] = box
        base = mod._Reader3Unpickler

        class Counting(base):  # type: ignore[misc, valid-type]
            def load(self, _box: List[int] = box, _base: Any = base) -> Any:
                _box[0] += 1
                return _base.load(self)

        mod._Reader3Unpickler = Counting

    fallback = [0]
    counts["pickle_load_fallback"] = fallback
    original_load = pickle.load

    def counting_load(*a: Any, **kw: Any) -> Any:
        fallback[0] += 1
        return original_load(*a, **kw)

    pickle.load = counting_load  # type: ignore[assignment]
    return counts


def _install_normalize_counter() -> Dict[str, int]:
    import reader3_app.search_service as search_service

    stats = {"calls": 0, "chars": 0}
    original = search_service._normalize_with_map

    def counting(text: str, *, case_sensitive: bool) -> Any:
        stats["calls"] += 1
        stats["chars"] += len(text or "")
        return original(text, case_sensitive=case_sensitive)

    search_service._normalize_with_map = counting  # type: ignore[assignment]
    return stats


def worker_counters(args: argparse.Namespace) -> None:
    """一段有代表性的操作序列，逐步记录两个计数器。

    序列是照着「什么样的操作能让重复暴露出来」倒推的，不是随手挑的：

      1. 打开书库首页（20 本 > `load_book_cached` 的 maxsize=10）
      2. 打开其中一本的阅读页
      3. 在这本书里搜一次 —— 触发的是 `search_service` **另一份**缓存
      4. 回到书库首页
      5. 全库搜三次，同样的词 —— 20 本 > `load_book_index` 的 maxsize=4

    只调一次的序列会让两个计数器恒等于「必要开销」，看不出任何重复。步骤 3 是为
    「同一本书被两处 loader 各 unpickle 一遍」设的，步骤 5 是为「同一份文本被反复
    归一化」设的。
    """
    worker_syspath()
    os.environ["READER3_BOOKS_DIR"] = args.books_dir

    counts = _install_unpickle_counters()
    norm = _install_normalize_counter()

    from fastapi.testclient import TestClient

    from reader3_app.web import server

    steps: List[Dict[str, Any]] = []

    def snapshot(label: str) -> None:
        steps.append(
            {
                "step": label,
                "unpickle": {k: v[0] for k, v in counts.items()},
                "normalize_calls": norm["calls"],
                "normalize_chars": norm["chars"],
            }
        )

    # 打开的是**书库里第一本**，不是随手挑一本。`library_view` 按 os.listdir 的
    # 顺序逐本 load，maxsize=10 的 LRU 因此保证淘汰掉最先访问的那几本 —— 挑一本
    # 名字好看的会撞上「它恰好在最后十本里」的运气，那次采样测到的就是缓存命中。
    # 刻意不排序：`library_view` 用的就是裸 os.listdir 的顺序，这里要的是「它最先
    # load 的那一本」，排过序就不一定是同一本了。
    first_book = [p for p in os.listdir(args.books_dir) if p.endswith("_data")][0]

    client = TestClient(server.app)
    with client:
        snapshot("00_startup")
        client.get("/")
        snapshot("01_library_page")
        client.get(f"/read/{first_book}/0")
        snapshot("02_reader_page")
        client.get(f"/api/search/{first_book}", params={"q": "tide", "mode": "keyword"})
        snapshot("03_in_book_search")
        client.get("/")
        snapshot("04_library_page_again")
        for i in range(LIBRARY_SEARCH_ROUNDS):
            client.get("/api/search/library", params={"q": "tide", "mode": "keyword"})
            snapshot(f"05_library_search_{i + 1}")

    total = steps[-1]
    emit(
        {
            "steps": steps,
            "unpickle_total": total["unpickle"],
            "unpickle_grand_total": sum(
                v for k, v in total["unpickle"].items() if k != "pickle_load_fallback"
            ),
            "normalize_calls_total": total["normalize_calls"],
            "normalize_chars_total": total["normalize_chars"],
            "vector_search_instrumented": "vector_search" in counts,
            "rss_bytes": rss_bytes(),
        }
    )


# --------------------------------------------------------------------------- #
# worker: ingest —— 冷启动的第二种口径（含 EPUB 解析）
# --------------------------------------------------------------------------- #


def worker_ingest(args: argparse.Namespace) -> None:
    """把一本三百万字符的 EPUB 走完 `process_epub`。

    这不是「冷启动」的一部分 —— 读路径永远只见 `book.pkl`。单列，是因为 §6 点名
    要覆盖三百万字符路径，而那条路径上最贵的一段就在这里。写进临时目录：
    `process_epub` 会在输出目录旁开 staging 并 `os.replace`，指向真实 `books/`
    一次就够毁掉用户的标注。
    """
    worker_syspath()
    from epub_corpus import build_huge_epub

    from reader3_app.reader3 import process_epub

    workdir = Path(args.books_dir)
    epub_path = workdir / "huge.epub"

    t0 = time.perf_counter()
    build_huge_epub(epub_path, chars=args.chars)
    t1 = time.perf_counter()
    book = process_epub(str(epub_path), str(workdir / "huge_data"))
    t2 = time.perf_counter()

    emit(
        {
            "build_epub_ms": (t1 - t0) * 1000,
            "process_epub_ms": (t2 - t1) * 1000,
            "epub_bytes": epub_path.stat().st_size,
            "pkl_bytes": (workdir / "huge_data" / "book.pkl").stat().st_size,
            "chapters": len(book.spine),
            # 报出来是为了让「这次真的走了三百万字符路径」可被核对 —— 一个悄悄
            # 只处理了三千字符的基准会给出一个很好看的数。
            "text_chars": sum(len(c.text or "") for c in book.spine),
            "rss_bytes": rss_bytes(),
        }
    )


WORKERS: Dict[str, Callable[[argparse.Namespace], None]] = {
    "prepare": worker_prepare,
    "cold_start": worker_cold_start,
    "ttfb": worker_ttfb,
    "query": worker_query,
    "rss": worker_rss,
    "counters": worker_counters,
    "ingest": worker_ingest,
}


# --------------------------------------------------------------------------- #
# 父进程：调度、聚合、输出
# --------------------------------------------------------------------------- #


class WorkerError(RuntimeError):
    pass


def run_worker(name: str, extra: Sequence[str]) -> Dict[str, Any]:
    """跑一个 worker 子进程，返回它 emit 的那一行 JSON，外加父侧量到的整体墙钟。

    `wall_ms` 由父进程量，含解释器启动 —— 那正是「冷启动」口径 A 里 worker 自己
    量不到的那一段。
    """
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", name, *extra]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    wall_ms = (time.perf_counter() - t0) * 1000
    if proc.returncode != 0:
        raise WorkerError(f"worker {name} 退出码 {proc.returncode}\n{proc.stderr[-3000:]}")
    for line in proc.stdout.splitlines():
        if line.startswith(MARKER):
            payload = json.loads(line[len(MARKER) :])
            payload["_wall_ms"] = wall_ms
            return payload
    raise WorkerError(f"worker {name} 没有输出结果行\nstdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}")


def series(samples: Sequence[float], unit: str) -> Dict[str, Any]:
    """一组采样 → 中位数 ＋ 全距 ＋ 相对全距。

    `spread_pct` 是 `(max-min)/median`，它是「这项现在配不配设门禁」的判据：
    全距比你想守的回归幅度还大的指标，设了阈值只会得到一个天天误报的 CI。
    """
    values = [float(v) for v in samples]
    med = statistics.median(values)
    lo, hi = min(values), max(values)
    return {
        "unit": unit,
        "n": len(values),
        "median": round(med, 3),
        "min": round(lo, 3),
        "max": round(hi, 3),
        "spread_pct": round((hi - lo) / med * 100, 1) if med else None,
        "samples": [round(v, 3) for v in values],
    }


def collect(
    runs: Sequence[Dict[str, Any]], keys: Sequence[str], unit: str
) -> Dict[str, Any]:
    return {k: series([r[k] for r in runs], unit) for k in keys if k in runs[0]}


def _prepared_library(stack: List[str], *, size: int, huge: bool, chars: int) -> str:
    tmp = tempfile.mkdtemp(prefix="reader3-bench-")
    stack.append(tmp)
    books = Path(tmp) / "books"
    books.mkdir()
    extra = ["--books-dir", str(books), "--size", str(size), "--chars", str(chars)]
    if huge:
        extra.append("--huge")
    run_worker("prepare", extra)
    return str(books)


def _cleanup(stack: List[str]) -> None:
    for path in stack:
        shutil.rmtree(path, ignore_errors=True)
    stack.clear()


def bench_cold_start(repeat: int, size: int) -> Dict[str, Any]:
    runs = []
    for _ in range(repeat):
        stack: List[str] = []
        try:
            books = _prepared_library(stack, size=size, huge=False, chars=0)
            runs.append(run_worker("cold_start", ["--books-dir", books]))
        finally:
            _cleanup(stack)
    out = collect(
        runs,
        ["import_server_ms", "import_testclient_ms", "startup_scan_ms", "first_page_ms", "ready_to_serve_ms", "_wall_ms"],
        "ms",
    )
    out["peak_rss"] = series([r["rss_bytes"] for r in runs], "bytes")
    out["_library_size"] = size
    return out


def bench_ttfb(repeat: int, sizes: Sequence[int]) -> Dict[str, Any]:
    by_size: Dict[str, Any] = {}
    for size in sizes:
        runs = []
        for _ in range(repeat):
            stack: List[str] = []
            try:
                books = _prepared_library(stack, size=size, huge=False, chars=0)
                runs.append(run_worker("ttfb", ["--books-dir", books]))
            finally:
                _cleanup(stack)
        entry = collect(runs, ["ttfb_ms", "_wall_ms"], "ms")
        entry["body_bytes"] = series([r["body_bytes"] for r in runs], "bytes")
        entry["per_book_ms"] = round(entry["ttfb_ms"]["median"] / size, 3)
        by_size[str(size)] = entry
    by_size["_fit"] = _linear_fit(
        [float(s) for s in sizes],
        [by_size[str(s)]["ttfb_ms"]["median"] for s in sizes],
    )
    return by_size


def _linear_fit(xs: Sequence[float], ys: Sequence[float]) -> Dict[str, Any]:
    """最小二乘拟合 `ttfb = intercept + slope × n`，外加 R²。

    曲线要不要读成「线性」，判据是 slope 与 intercept 的相对大小加上 R²，不是眼力。
    截距是「与书库规模无关的固定成本」（模板编译、TestClient 首个请求），斜率才是
    §6 想抓的那个 O(n) 扫描。截距远大于 slope×n 时曲线看起来是平的 —— 那不代表
    没有 O(n)，只代表在这个规模区间里它还没占主导，这个区别必须写进结论。
    """
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    return {
        "slope_ms_per_book": round(slope, 4),
        "intercept_ms": round(intercept, 3),
        "r_squared": round(1 - ss_res / ss_tot, 4) if ss_tot else None,
    }


def bench_query(repeat: int, size: int, chars: int) -> Dict[str, Any]:
    runs = []
    for _ in range(repeat):
        stack: List[str] = []
        try:
            books = _prepared_library(stack, size=size, huge=True, chars=chars)
            runs.append(run_worker("query", ["--books-dir", books]))
        finally:
            _cleanup(stack)
    keys = [
        "inbook_small_first_ms",
        "inbook_small_second_ms",
        "inbook_huge_first_ms",
        "inbook_huge_second_ms",
        "library_first_ms",
        "library_second_ms",
    ]
    out = collect(runs, keys, "ms")
    for pair in ("inbook_small", "inbook_huge", "library"):
        first = out[f"{pair}_first_ms"]["median"]
        second = out[f"{pair}_second_ms"]["median"]
        out[f"{pair}_speedup_x"] = round(first / second, 1) if second else None
    return out


def bench_rss(repeat: int, size: int, chars: int) -> Dict[str, Any]:
    runs = []
    for _ in range(repeat):
        stack: List[str] = []
        try:
            books = _prepared_library(stack, size=size, huge=True, chars=chars)
            runs.append(run_worker("rss", ["--books-dir", books]))
        finally:
            _cleanup(stack)
    keys = [
        "baseline_bytes",
        "after_import_bytes",
        "after_library_page_bytes",
        "after_library_search_bytes",
        "after_huge_search_bytes",
    ]
    out = collect(runs, keys, "bytes")
    out["_platform_unit_note"] = (
        f"ru_maxrss on {sys.platform} read as "
        f"{'bytes' if sys.platform == 'darwin' else 'KiB, multiplied by 1024'}"
    )
    return out


def bench_counters(repeat: int, size: int) -> Dict[str, Any]:
    runs = []
    for _ in range(repeat):
        stack: List[str] = []
        try:
            books = _prepared_library(stack, size=size, huge=False, chars=0)
            runs.append(run_worker("counters", ["--books-dir", books]))
        finally:
            _cleanup(stack)
    loaders = sorted(runs[0]["unpickle_total"].keys())
    out: Dict[str, Any] = {
        "unpickle": {
            name: series([r["unpickle_total"][name] for r in runs], "count")
            for name in loaders
        },
        "unpickle_grand_total": series([r["unpickle_grand_total"] for r in runs], "count"),
        "normalize_calls": series([r["normalize_calls_total"] for r in runs], "count"),
        "normalize_chars": series([r["normalize_chars_total"] for r in runs], "count"),
        "vector_search_instrumented": runs[0]["vector_search_instrumented"],
        "steps": runs[0]["steps"],
        "_library_size": size,
        "_library_search_rounds": LIBRARY_SEARCH_ROUNDS,
    }
    return out


def bench_ingest(repeat: int, chars: int) -> Dict[str, Any]:
    runs = []
    for _ in range(repeat):
        stack: List[str] = []
        try:
            tmp = tempfile.mkdtemp(prefix="reader3-bench-")
            stack.append(tmp)
            runs.append(run_worker("ingest", ["--books-dir", tmp, "--chars", str(chars)]))
        finally:
            _cleanup(stack)
    out = collect(runs, ["build_epub_ms", "process_epub_ms", "_wall_ms"], "ms")
    out["epub_bytes"] = series([r["epub_bytes"] for r in runs], "bytes")
    out["pkl_bytes"] = series([r["pkl_bytes"] for r in runs], "bytes")
    out["peak_rss"] = series([r["rss_bytes"] for r in runs], "bytes")
    out["_chars"] = chars
    out["_text_chars_out"] = runs[0]["text_chars"]
    return out


def environment() -> Dict[str, Any]:
    """环境戳。**没有它的性能数字是不可复现的，等于没有。**

    机型与 CPU 用 `sysctl` 取（macOS）；取不到就留 None 而不是编一个 —— 一个错的
    机型标注比没有标注更坏，它会让下一个人以为两次测量可比。
    """
    info: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        # 电源与负载不是花絮：笔记本在电池上会降频，同时跑着别的活会抢核。
        # 两次测量之间只要这两项变了，墙钟类指标就不可比 —— 不记下来，下一个人
        # 会把「换了电源」读成「代码变慢了」。
        "load_avg": [round(v, 2) for v in os.getloadavg()],
    }
    if sys.platform == "darwin":
        for key, sysctl_key in (
            ("cpu_brand", "machdep.cpu.brand_string"),
            ("mem_bytes", "hw.memsize"),
        ):
            try:
                info[key] = subprocess.run(
                    ["sysctl", "-n", sysctl_key], capture_output=True, text=True, timeout=5
                ).stdout.strip() or None
            except (OSError, subprocess.SubprocessError):
                info[key] = None
        info["power"] = _darwin_power()
    return info


def _darwin_power() -> Optional[str]:
    try:
        batt = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5
        ).stdout.strip().splitlines()
        mode = subprocess.run(
            ["pmset", "-g"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    low = next((ln.split()[-1] for ln in mode.splitlines() if "lowpowermode" in ln), "?")
    source = batt[0] if batt else "?"
    detail = batt[1].strip() if len(batt) > 1 else ""
    return f"{source} | {detail} | lowpowermode={low}"


def preflight() -> None:
    """在一个独立子进程里确认被测包能 import。

    独立子进程是必须的：父进程一旦 import 了 `reader3_app`，后面所有「冷启动」
    就都不冷了 —— 而冷启动是本脚本的第一项指标。
    """
    probe = "import sys; sys.path.insert(0, %r); import reader3_app.web.server" % str(SRC_DIR)
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    if proc.returncode != 0:
        sys.exit(
            "预检失败：当前解释器 import 不了 reader3_app。\n"
            "  正确跑法：uv run python scripts/bench.py\n"
            "  本脚本自身零第三方依赖，但被测代码需要 fastapi / httpx / ebooklib。\n"
            f"  解释器：{sys.executable}\n"
            f"  原始错误：\n{proc.stderr[-1500:]}"
        )


def _fmt_bytes(n: float) -> str:
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 * 1024):.1f} MiB"


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    env = report["environment"]
    lines.append("=" * 78)
    lines.append("reader3-pro 性能基准（tasks/008-test-safety-net.md §6）")
    lines.append("=" * 78)
    lines.append(f"时间     : {report['generated_at']}")
    lines.append(f"环境     : {env['platform']} / {env.get('cpu_brand') or env['machine']} / {env['cpu_count']} cores")
    lines.append(f"Python   : {env['python']} ({env['implementation']})")
    lines.append(f"电源     : {env.get('power') or 'n/a'}")
    lines.append(f"负载     : load avg {env.get('load_avg')}")
    lines.append(f"重复次数 : {report['repeat']}")
    lines.append("")

    def row(label: str, s: Dict[str, Any], fmt: str = "ms") -> None:
        if fmt == "bytes":
            body = f"{_fmt_bytes(s['median']):>12}  [{_fmt_bytes(s['min'])} – {_fmt_bytes(s['max'])}]"
        elif fmt == "count":
            body = f"{s['median']:>12.0f}  [{s['min']:.0f} – {s['max']:.0f}]"
        else:
            body = f"{s['median']:>12.1f}  [{s['min']:.1f} – {s['max']:.1f}]"
        spread = f"  ±{s['spread_pct']}%" if s.get("spread_pct") is not None else ""
        lines.append(f"  {label:<34}{body}{spread}")

    m = report["metrics"]

    if "cold_start" in m:
        cs = m["cold_start"]
        lines.append(f"[1] 冷启动（全新进程，{cs['_library_size']} 本书，不含 EPUB 解析）  ms 中位数 [min – max]")
        for key, label in (
            ("_wall_ms", "整体墙钟（含解释器启动）"),
            ("import_server_ms", "import reader3_app.web.server"),
            ("import_testclient_ms", "import TestClient"),
            ("startup_scan_ms", "startup: book_uuid 扫描"),
            ("ready_to_serve_ms", "可服务第一个请求"),
            ("first_page_ms", "首页第一个响应"),
        ):
            if key in cs:
                row(label, cs[key])
        row("峰值 RSS", cs["peak_rss"], "bytes")
        lines.append("")

    if "ingest" in m:
        ing = m["ingest"]
        lines.append(
            f"[1b] 大部头入库（源 {ing['_chars']:,} 字符 → 落盘 {ing['_text_chars_out']:,} 字符，含 EPUB 解析）"
        )
        row("build_epub（造语料，非生产路径）", ing["build_epub_ms"])
        row("process_epub", ing["process_epub_ms"])
        row("epub 体积", ing["epub_bytes"], "bytes")
        row("book.pkl 体积", ing["pkl_bytes"], "bytes")
        row("峰值 RSS", ing["peak_rss"], "bytes")
        lines.append("")

    if "query" in m:
        q = m["query"]
        lines.append("[2] 首次查询 vs 二次相同查询")
        for prefix, label in (
            ("library", "全库搜索 · 20 本 + 1 本大部头"),
            ("inbook_small", "书内搜索 · 小书 8 章 × 2000 字符"),
            ("inbook_huge", "书内搜索 · 大部头 3M 字符"),
        ):
            lines.append(f"  {label}")
            row("  首次", q[f"{prefix}_first_ms"])
            row("  二次（相同查询）", q[f"{prefix}_second_ms"])
            lines.append(f"    {'加速比':<32}{q[f'{prefix}_speedup_x']}x")
        lines.append("")

    if "rss" in m:
        r = m["rss"]
        lines.append("[3] 峰值 RSS（累积，ru_maxrss 只增不减）")
        for key, label in (
            ("baseline_bytes", "解释器 + 本脚本"),
            ("after_import_bytes", "+ import 服务端"),
            ("after_library_page_bytes", "+ 首页（20 本 unpickle）"),
            ("after_library_search_bytes", "+ 全库关键词搜索"),
            ("after_huge_search_bytes", "+ 大部头搜索（3M 字符）"),
        ):
            row(label, r[key], "bytes")
        lines.append(f"  单位口径: {r['_platform_unit_note']}")
        lines.append("")

    if "counters" in m:
        c = m["counters"]
        lines.append(f"[4] 反序列化次数（一段典型序列，{c['_library_size']} 本书）")
        for name, s in sorted(c["unpickle"].items()):
            row(name, s, "count")
        row("合计（三处 loader）", c["unpickle_grand_total"], "count")
        lines.append("")
        lines.append("[5] 归一化次数 _normalize_with_map")
        row("调用次数", c["normalize_calls"], "count")
        row("归一化字符总量", c["normalize_chars"], "count")
        lines.append("")
        lines.append("  逐步：")
        prev = {"unpickle": {}, "normalize_calls": 0}
        for step in c["steps"]:
            deltas = []
            for k, v in sorted(step["unpickle"].items()):
                d = v - prev["unpickle"].get(k, 0)
                if d:
                    deltas.append(f"{k}+{d}")
            dn = step["normalize_calls"] - prev["normalize_calls"]
            if dn:
                deltas.append(f"normalize+{dn}")
            lines.append(f"    {step['step']:<26}{'  '.join(deltas) or '—'}")
            prev = step
        lines.append("")

    if "ttfb" in m:
        lines.append("[6] 首页冷启动 TTFB × 书库规模（不含 import，含 Jinja 渲染）")
        lines.append(f"  {'书库规模':<12}{'TTFB 中位数':>14}{'[min – max]':>22}{'每本 ms':>12}")
        for size in sorted((k for k in m["ttfb"] if not k.startswith("_")), key=int):
            e = m["ttfb"][size]
            s = e["ttfb_ms"]
            lines.append(
                f"  {size + ' 本':<12}{s['median']:>13.1f} "
                f"{'[' + format(s['min'], '.1f') + ' – ' + format(s['max'], '.1f') + ']':>22}"
                f"{e['per_book_ms']:>12.2f}"
            )
        fit = m["ttfb"]["_fit"]
        lines.append(
            f"  最小二乘: ttfb ≈ {fit['intercept_ms']} ms + {fit['slope_ms_per_book']} ms × n"
            f"   (R² = {fit['r_squared']})"
        )
        lines.append("")

    lines.append("注：基准只记录、不设阈值门禁（§6）。spread_pct 大的指标先别设门禁。")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="reader3-pro 性能基准（§6 六项指标）")
    parser.add_argument("--worker", choices=sorted(WORKERS), help=argparse.SUPPRESS)
    parser.add_argument("--books-dir", help=argparse.SUPPRESS)
    parser.add_argument("--size", type=int, default=20, help="合成书库规模（默认 20，见 synthetic_library 的 docstring）")
    parser.add_argument("--huge", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--chars", type=int, default=3_000_000, help="大部头字符数（默认三百万）")
    parser.add_argument("--repeat", type=int, default=5, help="每项指标的重复次数（默认 5）")
    parser.add_argument(
        "--sizes",
        default=",".join(str(s) for s in DEFAULT_SIZES),
        help="TTFB 曲线的书库规模，逗号分隔（默认 1,5,10,20）",
    )
    parser.add_argument("--only", help="只跑这几项，逗号分隔：cold_start,ingest,query,rss,counters,ttfb")
    parser.add_argument("--json", dest="json_path", help="把机器可读结果写到这个路径")
    args = parser.parse_args(argv)

    if args.worker:
        WORKERS[args.worker](args)
        return 0

    preflight()

    wanted = set((args.only or "cold_start,ingest,query,rss,counters,ttfb").split(","))
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    repeat = max(1, args.repeat)

    metrics: Dict[str, Any] = {}
    if "cold_start" in wanted:
        print("… [1] 冷启动", file=sys.stderr)
        metrics["cold_start"] = bench_cold_start(repeat, args.size)
    if "ingest" in wanted:
        print("… [1b] 大部头入库", file=sys.stderr)
        metrics["ingest"] = bench_ingest(repeat, args.chars)
    if "query" in wanted:
        print("… [2] 首次/二次查询", file=sys.stderr)
        metrics["query"] = bench_query(repeat, args.size, args.chars)
    if "rss" in wanted:
        print("… [3] 峰值 RSS", file=sys.stderr)
        metrics["rss"] = bench_rss(repeat, args.size, args.chars)
    if "counters" in wanted:
        print("… [4][5] 反序列化 / 归一化计数", file=sys.stderr)
        metrics["counters"] = bench_counters(repeat, args.size)
    if "ttfb" in wanted:
        print(f"… [6] TTFB × 规模 {sizes}", file=sys.stderr)
        metrics["ttfb"] = bench_ttfb(repeat, sizes)

    report = {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repeat": repeat,
        "environment": environment(),
        "metrics": metrics,
    }

    print(render(report))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"\n机器可读结果 → {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
