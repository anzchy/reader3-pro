# 剩余 High findings 的派发顺序（按价值，不按编号）

排序依据，从重到轻：
**用户数据被静默毁掉 > 本机被别人拿去执行 > 错答案被当成对答案 > 安全网自己是坏的。**

依据是这个仓库自己的判据（`ensure_book_uuid` 先例）：
**「读不懂的用户数据不许当成『没有』。」500 是可恢复的，删除不是。**
所以「丢标注」排在「答案是空的」前面——空答案用户看得见，丢标注看不见。

派发**严格串行**：`receipt.js record` 会跑整条 lane，两个 WI 同时红会互相污染 receipt。

| # | WI | Findings | 为什么排这里 |
|---|---|---|---|
| 1 | WI-23 | B4 | `notes.json` 并发写互相吞。丢的是用户**自己写的**批注，没有任何副本可恢复。 |
| 2 | WI-25 | ai/3 | uuid 竞态，输的一方拿到永远解析不出的 id → 对话与书失联。 |
| 3 | WI-26 | B5、B8 | `book.pkl` 无限制反序列化 = 本地代码执行。一份别人给的书就够。 |
| 4 | WI-27 | C1 | 无 Host／Origin 校验：任意网站可驱动本机 server（DNS rebinding）。 |
| 5 | WI-20 | B6 | 高亮偏移码点 vs UTF-16：中文＋emoji 下高亮锚到错的字上。盘上数据还在，故排在丢数据之后。 |
| 6 | WI-12 | ai/60、71、73 | 三家 provider 把失败当空回答返回——错答案伪装成对答案。 |
| 7 | WI-24 | ai/45、46 | token 估算与窗口双双高估，CJK 请求被送上必失败的路。 |
| 8 | WI-19 | A1≡B9、A2、B10、B11 | 向量索引返回指向已不存在文本的结果，相似度恒为 0。 |
| 9 | WI-21 | C4、C5 | AI 队列租约会漏，串行保证是假的。 |
| 10 | WI-22 | A39、A40、C6、C7 | 四类重活跑在事件循环上，单个请求能卡死整个 server。 |
| 11 | WI-29 | ai/13 | 既有设置文件权限不收紧。本机实测无 key，故不紧急；改动只有一行。 |
| 12 | WI-18 | tests/26、tests/2 | **测试层从这条开始**：fixture 自己是错的，于是它下游的测试都在测别的东西。 |
| 12.5 | **WI-30** | **web/E1（新）** | **插队到测试层之前。**`server.py` 的 `_http_get_json` 与 `worker_ollama` 仍直接 `urlopen`，URL 由用户可编辑的 `base_url` 传下来，无 scheme 白名单、无重定向守卫——`file://` 读本机文件并回传。这是 `ai/74` 同一个洞，WI-11 只收了五个 provider。按排序依据属「本机被别人拿去执行」档，高于其后所有安全网条目。由 WI-18 的 Z2 扫描暴露。 |
| 13 | WI-13 | tests/10–14、16 | 契约只冻结了信封，handler 返回空数组照样绿。 |
| 14 | WI-17 | tests/41–45 | 异常测试断的是「抛没抛」，不是「守住没守住」——本轮反复踩的同一个坑。 |
| 15 | WI-15 | tests/6、23、37、40 | 拿自己当预言机，或断言的是 fixture 不是被测对象。 |
| 16 | WI-16 | tests/18–21 | 场景测试没钉住它自己命名的那条性质。 |
| 17 | WI-14 | tests/15 ＋ 6 个可删守卫 | 路径安全在契约层零覆盖。 |
| 18 | WI-28 | D2、D4 | 闸门自己会放水；冒烟测的可能不是那个 wheel。放最后是因为它拦的是**未来**的回归。 |

**已完成**：WI-1–WI-6（并入 008 之前）、WI-7–WI-11、WI-23、WI-25、WI-26、WI-27、WI-20、WI-12、WI-24、WI-19（含 WI-19b）、WI-21、WI-22、WI-29（判定：原诊断机制被证伪，改为文档修复+回归围栏）、WI-18、WI-30、WI-13、WI-17。WI-14。**71 条 High 全部结清：69 fixed / 2 skipped（附证据）/ 0 transferred。**

**WI-13 记账偏差（如实记录）**：本 WI 不改 `src/`，交付物就是断言，所以未变异的真实代码上新断言本来就该是绿的——red receipt 是在 **R1 变异在位**时录的。这不是教科书意义上的 red（「缺陷存在时新断言拒绝了当前代码」而非「实现还不存在」），receipt 判 SEPARATION-HELD 成立，但这层区别不应被抹掉。

**WI-13 暴露的矩阵误判（第 10 次）**：finding tests/12 的措辞「handler 返回 0 命中仍绿」只有一半成立——`test_event_loop_not_blocked` 的 T2/T3 已经钉住了 handler 的透传。真窟窿在检索层（`search_service.search_library` 整个坏掉时全绿），变异因此下移一层。


**WI-30 的 separation 判定（SEPARATION-BROKEN，已记录理由）**：`receipt.js verify --id WI-30` 报 `tests/unit/test_ai_queue_lease.py` 有一行被改。改的是 **monkeypatch 的注入点**，不是被钉住的断言——生产接缝从 `urllib.request.urlopen` 挪到了 `_http.post_stream`，桩打在旧地址上就是打空。Q1–Q6 的断言一字未动。改完之后我重跑了「这两条测试还咬不咬」：N1（不注册 ollama 停止回调）→ Q3+Q4 红；N2（`ai_logger.error`→`debug`，3 处）→ 只有 Q4 红；N3（`if False:` 包住 `thread.join`）→ 只有 Q3 红。三条都精确命中，说明新接缝下性质仍然成立。


**注意 WI-28**：同文件的 `D3` 已由 WI-3 修完（`tests/unit/test_coverage_gate_failclosed.py`，
G1–G7）。WI-28 只做 `D2`，且要**扩写**那个文件而不是新建平行文件。


## WI-14 收尾记录（2026-08-26）

### tests/15 被我自己推翻：不是 must fix，是等价变异

审计说「删掉 `serve_image` 的 `os.path.basename()` 没有测试变红 → 未覆盖的路径穿越洞」。
第一句是真的，第二句不成立。

Starlette 的路径参数转换器默认是 `[^/]+`。uvicorn 把 `raw_path` 做 `unquote()` 后写进
`scope["path"]`，所以 `..%2F` 在**路由匹配之前**就已经变成 `../`——带 `/` 的 payload
根本匹配不上 `/read/{book_id}/images/{image_name}`，404 发生在路由层，handler 一次都不执行。
而 `os.path.basename(x) != x` 只在 `x` 含 `/` 时成立。

两边一合，结论是：**没有任何输入能让这行守卫产生可观测的差异**。实测：

| 变异 | 内容 | 结果 |
|---|---|---|
| MUTANT-A | 删掉 `_validate_book_id` 的枚举检查 | **7 红** — 真正拦人的是这一条 |
| MUTANT-B | 删掉 `_validate_book_id` 的 basename + 比对 | 642 全绿 |
| MUTANT-C | 删掉 `serve_image` 两处 basename | 642 全绿 |

B 和 C 是教科书意义上的 equivalent mutant。为它们写测试，只能写出一条**断在路由层 404
上**的假绿——删掉守卫它照样绿。审计所指的路径穿越，到此为止是被证伪的。

但**同一处确实有个可达的缺陷**，而且最后是照它修的：`image_name=".."` 不含 `/`，能匹配
路由；`basename("..")` 仍是 `".."`，于是 `os.path.exists(images/..)` 对一个**目录**为真，
`FileResponse` 拿到目录，在 send 阶段炸成 500。一次「文件不存在」被报成「服务器坏了」。
改 `exists` → `isfile`，用例在 `tests/contract/test_degraded_bookdir_and_images.py`
（手搓 ASGI scope，因为 httpx 按 RFC 3986 §5.2.4 在发请求前就把 `..` 规范化掉了，走
TestClient 测出来的是 httpx 的行为）。变异证据：MUTANT-K 精确 1 红，MUTANT-L（过度修正，
连真实图片也 404）2 红。

所以这条最终记 `fixed (WI-14)`，但**修的不是审计说的那个洞**——审计的前提仍然是错的，
这一点比状态位本身更值得留在这里。

### 方法论修正

此前我自己的变异复跑用了 `-k` 过滤（按文件跑），这正是 tests/6 与 tests/40 被误判成 High
的成因：它们在本文件里不咬，但套件里另有断言咬住同一条性质。**变异验证一律跑整套**。

另有两次锚点断言失败（MUTANT-H 早期版本、以及一次误从 pre-fix 备份还原），当时后续的
「N passed」都是空结果，已作废重跑。备份文件名此后一律区分 `*_pre` / `*_FIXED`。

### 本轮变异账（全部跑整套 tests/unit + tests/contract）

| # | 变异 | 实际变红 | 精确性 |
|---|---|---|---|
| A | `_validate_book_id` 枚举检查 | 7 | 符合预期（既有覆盖） |
| B/C | 两处 basename | 0 | 等价变异，见上 |
| D | 三处 `BookVectorIndex(..., books_dir=BOOKS_DIR)` 改默认路径 | 3 | 精确（tests/21 修复生效） |
| E | totals 量不到 → 退回 WARN | 1 | 精确 |
| F | criticalPaths 量不到 → 退回 WARN | 1 | 精确 |
| G | 删掉 `if not want: continue` | 7 | 含反向守卫，符合预期 |
| H | `base.setdefault(k, v)` | 0 | **无效变异**：种子配置里 `api_key: ""` 已存在，setdefault 不触发 |
| I | 白名单加 `api_key` | 2 | 新旧用例都咬，不具区分度 |
| J | 「只在没有 key 时才补」 | **1（仅新用例）** | 精确——这才是 tests/20 真正的缺口 |
| K | `isfile` 改回 `exists` | **1** | 精确（tests/15 的真缺陷） |
| L | `isfile` 收紧成「只认 .jpg 白名单」等过度修正 | 2 | 反向守卫：真实图片也被拒会红 |
| M | `serve_epub` 去掉 `exists` 检查 | **1** | 精确（tests/23 缺 epub → 404 而非 500） |
| N | 误注入到 `serve_epub` 而非 `library_view` | 1 | 变异本身放错位置，不作为 library 侧证据 |
| P | 删掉 `api_ai_put_conversation` 的**写侧**过滤、保留读侧 | **1** | 精确——正是原读回断言结构上抓不到的那一个 |
| Q | `build_huge_epub` 产出空章节 | **1** | 精确 |
| R | `build_huge_epub` 忽略 `chars` 参数 | **1** | 精确 |
| S | SSE chunk 攒到 `done` 再一次性冲出 | 3（含 2 条既有租约用例） | 咬住了，但不精确；关键在**原 `:336` 用例在同一变异下全绿** |

### 最终收口

**71 条 High：69 fixed / 2 skipped / 0 transferred。**

留 `skipped` 的两条都是**套件级假阳性**，不是「决定不修」：

- tests/6 —— `test_route_contracts.py:284-289` 已用 `must_contain=(BOOK_TITLE, CHAPTER_0_TITLE)` 独立钉住同一性质。
- tests/40 —— `test_scenarios.py:99-108` 已对 prefix 与 suffix 双向断言（KEEP-TAIL / KEEP-HEAD 各 50 字）。

两条都是按文件跑变异（`-k` 过滤）才显得「不咬」的，跑整套时另有断言咬住。它们没有任何
可实现的工作项——写出来的会是第二份重复断言，不是新覆盖。

原先转交 009 的两条（tests/19、tests/23）当天收回，都在 008 内以不依赖时序、也不依赖 012
fixture 的方式结清；`tasks/009-e2e-annotations.md` 已改写为「已结清 + 009 可选补充」的边界说明，
不再记为欠账。

收口时的套件状态：`tests/unit tests/contract` **654 passed**，`ruff check` 全绿，
所有被变异过的文件已按 `*_FIXED` 备份逐一 md5 核对还原，`__pycache__` 已清。
