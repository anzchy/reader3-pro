# 性能基准存档

`scripts/bench.py --json <path>` 的原始产出。**只记录，不设阈值门禁**（008 §6）——
这里存的是「同一把尺量到的旧数」，好让下一次改动能回答「这次是优化还是劣化」。

| 文件 | 是什么 | 环境 |
|---|---|---|
| `011-wi2-before.json` | **Phase 2b 的 before 基准**，011 WI-2 的产出。测的是合并两处 `load_book_cached` **之前**的树（HEAD = WI-0 已落地、`src/` 未动） | macOS 26.3.1 / Apple M4 / 10 cores / Python 3.10.18 / repeat=5 |
| `011-wi5-after.json` | **同一序列的 after**，011 WI-5 的产出。测的是 WI-1…WI-4 落地之后的树（`book_store.py` 是唯一读盘点，`web.server` / `search_service` 的 `load_book_file` 绑定已删） | 同上（同机同 Python，repeat=5） |

## 读 `011-wi2-before.json` 之前先知道两件事

**一、这是 `bench.py` 第一次真的跑通。** 011 开工时它有两处独立的坏：

1. `_install_unpickle_counters()` 插在 `mod._Reader3Unpickler` 上，而那三个符号在
   收敛到 `safe_pickle.py` 时就没了 → `AttributeError`，指标 4/5 直接不产出。
2. **五个 worker 的 `TestClient` 全是裸构造**，而服务端那道 Host 白名单只放行
   127.0.0.1 / localhost / [::1]，`TestClient` 默认发 `testserver` → 每个请求
   400 `Invalid host header`。指标 2 会当场炸（它自己查了状态码），指标 1/3/4/5/6
   **安静地量到 400 响应**：计数器全 0、RSS 量的是错误页。

所以在此之前没有任何一份可信的基准数，`011-wi2-before.json` 就是零号。第 2 条的
教训写进了 `expect_ok()`：非 2xx 当场炸，不让仪器坏掉的表现形式是「所有数都很漂亮
地等于 0」。

**二、`unpickle` 那一组有两种口径，别混着比。**

* `web.server` / `search_service` / `vector_search` 是**归属计数**：包的是每个模块
  自己那份 `load_book_file` 模块级绑定。
* `safe_pickle_total` 包的是 `safe_pickle.safe_load`，不管谁调都算一次。

WI-3 会把两处 loader 并成一份，`web.server` 那一格因此会掉下去——**那不说明少读了
一次盘**，只说明绑定换了地方。跨越这次重构仍然可比的是 `safe_pickle_total`。
今天两者相等（100 = 40 + 60），意味着没有第四个绕开这三个绑定的读盘点。

## 基线里已经能看见 WI-3 要修的东西

`counters` 的逐步明细（`metrics.counters.steps`）：

```
01_library_page       web.server+20      20 本书全 unpickle 一遍
02_reader_page        web.server+1       打开第一本
03_in_book_search     search_service+1   ← 同一本书，换一处 loader，再 unpickle 一遍
04_library_page_again web.server+19      LRU maxsize=10 撑不住 20 本，19 本重读
05_library_search_×3  search_service+20/次
```

第 03 步那一次就是 §0.2 说的「同一本书在进程里躺两份」，第 04 步是 maxsize=10 对
20 本书的抖动。WI-3 的验收「反序列化计数相对基准不上升」拿这份数当对照。

## after（`011-wi5-after.json`）：省了 5 次，而**掉到「未测到」的那两格不是省出来的**

同一段固定 8 步序列，同一台机器：

| 口径 | before | after | 怎么读 |
|---|---:|---:|---|
| `safe_pickle_total` | 100 | **95** | 唯一跨这次重构可比的数。-5 |
| `unpickle_grand_total` | 100 | **95** | 仍与上一行相等 ⇒ 没有第四个绕开被追踪绑定的读盘点 |
| `book_store` | —（当时不存在） | **95** | 新的读盘点，非零 |
| `web.server` | 40 | **未测到（None）** | ↓ 见下 |
| `search_service` | 60 | **未测到（None）** | ↓ 见下 |
| `vector_search` | 0 | 0 | 这条序列本来就不走语义检索 |
| `pickle_load_fallback` | 0 | 0 | 没有绕开 allow-list 的裸 `pickle.load` |
| `normalize_calls` / `chars` | 549 / 984052 | 549 / 984052 | WI-5 不碰归一化，逐字不变是**预期** |

**`web.server` 与 `search_service` 从 40 / 60 变成「未测到」不是性能收益，一次盘都不是
它俩省下来的。** 那两格数的从来就是「哪个模块自己那份 `load_book_file` 模块级绑定被调
到了」；WI-1…WI-3 把读盘并进 `book_store.py`、WI-5 顺手删掉那两处已经用不上的 import 之
后，绑定根本不在那两个模块上了，于是它们进的是 `unpickle_unmeasured` 而不是记 0 ——沿用
`vector_search` 那一支同一条口径：**「没测到」和「测到了 0 次」是两件事**，把前者写成 0
会被读成「这两处 loader 一次都没被走到」，那是假的（它们照走，只是转发给了 `book_store`）。
探针本身也在 WI-5 一并修了：模块缺 `load_book_file` 时报 None，不再 `AttributeError`
——那正是 011 开工时整项指标不产出的坏法，不许重演第二回。

真正省下来的 5 次在逐步明细里看得见：

```
                       before                     after
03_in_book_search      search_service+1           —               ← 同一本书的第二次 unpickle 没了（省 1）
05_library_search_1    search_service+19          book_store+15   ← 两份 LRU 并成一份（省 4）
```

第 03 步是 §0.2 那个「同一本书在进程里躺两份」，合并之后直接消失，省 1 次；第 05 步第一轮
19 → 15，省 4 次——`library_view` 刚跑完留下的 maxsize=10 缓存现在和全库搜索共享，这一轮有
5 本是命中的（before 那一轮也已经命中 1 本，所以净省 4 而不是 5）。1 ＋ 4 ＝ 5，与
`safe_pickle_total` 的 100 → 95 对得上。

**这两个数早先在本文件里都写错过**：表里 before 那格写的是 `+20`（真值 +19，逐步明细是
累计值，1 → 20 的增量是 19），正文写的是「第 05 步第一轮少 5 次」（真值 4）。两处错误方向
相反，凑出来的总数恰好还是 5，所以从总数看不出来——这正是逐步明细必须逐格核对、不能只对
总账的理由。

剩下的 95 次**不全是**抖动：其中 20 次是步骤 01 的强制首次载入，20 本书每本至少要读一次，
任何缓存都省不掉。真正归因于 `maxsize=10` 对 20 本书抖动的是另外 75 次（步骤 02 的
+1、04 的 +19、05 三轮的 +15/+20/+20，合计 1＋19＋15＋20＋20＝75）。缓存尺寸是 **WI-8** 的活（它同时管
`load_book_index` 那个 maxsize=4、且命中时不重新 stat 的洞），不是 012 的，也不在 011 §4
的范围里。

