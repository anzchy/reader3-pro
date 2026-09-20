# 性能基准存档

`scripts/bench.py --json <path>` 的原始产出。**只记录，不设阈值门禁**（008 §6）——
这里存的是「同一把尺量到的旧数」，好让下一次改动能回答「这次是优化还是劣化」。

| 文件 | 是什么 | 环境 |
|---|---|---|
| `011-wi2-before.json` | **Phase 2b 的 before 基准**，011 WI-2 的产出。测的是合并两处 `load_book_cached` **之前**的树（HEAD = WI-0 已落地、`src/` 未动） | macOS 26.3.1 / Apple M4 / 10 cores / Python 3.10.18 / repeat=5 |
| `011-wi5-after.json` | **同一序列的 after**，011 WI-5 的产出。测的是 WI-1…WI-4 落地之后的树（`book_store.py` 是唯一读盘点，`web.server` / `search_service` 的 `load_book_file` 绑定已删） | 同上（同机同 Python，repeat=5） |
| `011-wi8-after.json` | **WI-9 ＋ WI-8 双双落地之后的同一序列**（HEAD `a4e5f49`）。`--repeat 5`，其余全走默认（`--size 20`、`--chars 3000000`） | 同机同 Python，repeat=5，**电池供电、load_avg 2.29** |
| `011-wi9-isolation.json` | 第一次拆 WI-9 / WI-8 时跑的隔离基准，HEAD `b69a568`，**`--only counters,rss,query`（部分项）**。**已不用于归因**——它与当时的对照组既不同参数也不背靠背；保留是因为下面的复现性论证引用了它 | 同上，load_avg 2.58 |
| `011-iso-04a6839.json` | **逐提交隔离三件套之一**：`b69a568^`，WI-9 / WI-8 都还没有 | 同机同 Python，repeat=5，全默认参数，load_avg 4.15 |
| `011-iso-b69a568.json` | 三件套之二：只有 WI-9 | 同上，load_avg 3.88，与上一份相隔 55 秒 |
| `011-iso-a4e5f49.json` | 三件套之三：WI-9 ＋ WI-8 | 同上，load_avg 3.67，与上一份相隔 55 秒 |

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



## `011-iso-*.json` 三件套:把 WI-9 与 WI-8 的战果逐提交拆开

> **本节 2026-09-20 改过一次。** 初版用 `011-wi5-after.json` 当归因基准、并把全库搜索的
> 抖动移交 C5——两处都是错的,经 Codex 评审指出后重跑重写。错的原文不保留在正文里,
> 但错在哪、怎么发现的,记在本节末尾的「这一节错过什么」。

`011-wi5-after.json` **不能**当归因基准:它与 WI-9 之间隔着 `a58d59d`(WI-5a)、`cc6bb18`
(WI-5b)两个动 `src/` 的提交,而且它自己的 `after_library_search_bytes` 有一个离群样本
(`[237, 237, 237, 237, 176]` MiB,spread **25.7%**)。要把某一笔提交的战果单独说清,只能
**逐提交相邻比**:`SHA^` 对 `SHA`,而且三份要在同一台机器、同一段时间里连着跑完。

于是有了 `011-iso-*.json` 三件套——文件名直接带提交短 SHA,因为 `bench.py` 的 JSON schema
里**没有**记录 HEAD 的字段(schema 1 只有 `generated_at` / `environment` / `metrics`),
不写进文件名就没人知道它是在哪跑的:

| 存档 | 提交 | 是什么 |
|---|---|---|
| `011-iso-04a6839.json` | `04a6839` | WI-9 的父提交(＝ `b69a568^`),两项改动都还没有 |
| `011-iso-b69a568.json` | `b69a568` | 只有 WI-9(`array("I")`) |
| `011-iso-a4e5f49.json` | `a4e5f49` | WI-9 ＋ WI-8(stat 入 key，上限 4 → 12) |

三份跑于 09:06:23 / 09:07:18 / 09:08:13,相隔 55 秒,`load_avg` 4.15 / 3.88 / 3.67,
同机同电源状态(电池)。

| 指标 | `04a6839` | `b69a568` | `a4e5f49` | **WI-9 独得** | **WI-8 独得** |
|---|---|---|---|---|---|
| `rss.after_library_search_bytes` | 237.7 MiB | 114.1 MiB | 114.8 MiB | **−123.6 MiB** | **＋0.7 MiB** |
| `rss.after_huge_search_bytes` | 331.7 MiB | 195.4 MiB | 196.1 MiB | **−136.3 MiB** | **＋0.7 MiB** |
| `counters.unpickle_grand_total` | 95 | 95 | 95 | 0 | **0** |
| `counters.normalize_calls` | 549 | 549 | 541 | 0 | **−8** |
| `counters.normalize_chars` | 984,052 | 984,052 | 967,924 | 0 | **−16,128** |

rss 两项的 `spread_pct` 是 0.0% / 0.1% / 0.1%,counters 全 0.0%。单位是 **MiB**
(`rss_bytes()` 报字节,这里除 1048576),**不是 MB**。

**这组数被复跑验证过。** 第一次做隔离时,父提交那份是一个多小时后、`load_avg` **13.82**
(我自己在并行跑别的活)下跑的,另两份是 07:46 / 07:48、load 2.29 / 2.58 ——不是背靠背,
初稿却写成了「三份都是同机背靠背」。改的时候索性把三份全部重跑成真背靠背,结果
**逐格复现到 0.1 MiB 以内**(237.6→237.7、114.0→114.1、114.9→114.8;huge 三格
331.7 / 195.4 / 196.1 与原值完全一致),counters 一个数都没动。
结论:**这两项峰值 RSS 对 `load_avg` 不敏感**,旧数没错——但当时那句「背靠背」是错的,
而错的说法即使碰巧指向对的数,也会教后来的人用一套不成立的方法。

**`rss.*` 量的是 `ru_maxrss`——进程累计峰值,不是缓存驻留内存。** `worker_rss` 的 docstring
自己写了「峰值本来就不可分解」。237.6 MiB 里有 62.5 MiB 是解释器 ＋ FastAPI import 的底噪
(`after_import_bytes`),还没碰任何书。所以 ＋0.8 MiB **不能**读成「扩容在真实书库里只花 0.8 MB」。

**内存那两格 100% 是 WI-9 的。** rss worker 的书库含那本三百万字符的大部头
(`bench.py:912` `huge=True`),`/api/search/library` 一个请求要索引 20 × 8 × 2000 ＋ 3,000,000
≈ **332 万字符**;`list[int]` 约 36 B/格、`array("I")` 4 B/格 ⇒ 稳态差约 106 MiB,实测峰值差
123.6 MiB(扩容时新旧数组并存 ＋ 几百万临时 PyLong,峰值本就高于落定值)。

**WI-8 抬上限 4 → 12 只花了 ＋0.8 MiB**,因为条目里的 `index_map` 已被 WI-9 压掉一个数量级。
(反过来做会贵多少**没有测**,不要替它编一个数。)

### WI-8 对两个计数器几乎不动:实测与真正的原因

```
逐步 unpickle/normalize_calls（注意：bench.py:951 只存 runs[0] 的 steps，
      逐步明细是单样本；总计那三行才是 5 次的中位数，spread 0.0%）
                        04a6839   b69a568   a4e5f49
03_in_book_search         21/9      21/9      21/9     ← 一本书：8 章 ＋ 1 次查询词
04_library_page_again     40/9      40/9      40/9
05_library_search_1      55/189    55/189    55/181
05_library_search_2      75/369    75/369    75/361
05_library_search_3      95/549    95/549    95/541
```

1. **`unpickle_grand_total` 一次没少(95 → 95)。真正的原因在调用链,不在容量。**
   `search_library()`(`src/reader3_app/search_service.py:620`)在遍历书目的循环里**无条件**
   先调 `load_book_cached(book_id, books_dir)` 取 title / author,**然后**才谈索引。所以索引
   命中根本没有机会省掉那次读盘——把 `load_book_index` 的上限调到多少都一样。
   > 本节初版写的是「`load_book_index` 体内不读盘,所以 95 完全由 `load_book_cached` 的
   > maxsize=10 决定」。结论对,**理由错**:外层缓存命中本来就可能跳过内层 loader,
   > 这里跳不过是因为调用链先加载了正文。顺带,95 也不是纯容量常数——
   > 20＋1＋0＋19＋15＋20＋20 里第一轮是 15 不是 20,访问顺序参与了结果。
   >
   > **这里藏着一个真正的后续项**:让全库搜索在索引已温时不再走 `load_book_cached`
   > 取元数据,才是这条路径上的解法。它不属于 C5(见下),目前**无人认领**。

2. **省下的 8 次只在第一轮出现,二、三轮 `+180` 与 WI-9 前逐格相同。**
   合成书每本 **8 章**(`tests/fixtures/synthetic_library.py:51` `chapters: int = 8`),
   而每本还要为查询词再归一化一次(`search_service.py:180`),所以每轮 180 ＝
   20 × (8 ＋ 1),**不是 20 × 9 章**——`a4e5f49` 的提交信息把这句写错了。
   逐步明细里 `03_in_book_search` 一格直接把这条钉死:只搜一本书,却记了 **9 次 / 16,132
   字符** ＝ 8 章 × 2,016 ＋ 查询词那 4 个字符。
   −8 正好是一本书的 8 章(`normalize_chars` 同步 −16,128 ＝ 8 × 2016),即第 03 步书内搜索
   暖起来的那本在上限 12 下活到了第一轮;它的查询词归一化照旧发生,所以是 −8 不是 −9。
   二、三轮相同,是「普通 LRU 在容量低于工作集时、固定同序扫描后续轮次全 miss」的实测确认。

3. **归因口径:只拿 `counters.*` 与本次三跑的 `rss.*` 说话。**
   `011-wi2-before.json` / `011-wi5-after.json` 都是**电池供电**下、`load_avg` 分别
   6.83 / 4.17(10 核)跑的,`_ms` 各项 spread 在 13%–46%。**跨存档比 `_ms` 中位数不成立。**

### 那 75 次抖动归谁:**不归 C5**

本文件上一节结尾写着「缓存尺寸是 **WI-8** 的活」,本节初版则把它改写成「归 C5 / 012」。
**两个都不对。**

`plan-tech-stack-migration.md:764` 的 C5 白纸黑字只讲**书库首页**:「`library_view` 遍历
`books/*_data/`,对每个目录调 `load_book_cached()`——只为读书名、作者、封面这几个字段」,
修法是「`load_book_metadata(book_id)` 只读 `manifest.json`」。同一段还写明「C1 说的跨库搜索
是低频操作」。**首页元数据与全库搜索读正文是两条不同的访问路径**;C5 即使完全实现,也不会
自动让全库搜索不读正文、更不会让索引缓存扛得住顺序扫。

所以那 75 次(`1＋19＋15＋20＋20`)里,属于首页的那部分归 C5,属于**全库搜索**的那部分
**目前无人认领**,必须单独登记,不能藏在 C5 的完成勾里。

### 顺带更正一个被引用过的数

`baseline-performance-008.md:285` 写「LRU 在这种循环访问下比随机淘汰还差(随机能拿到约 50%)」。
20 本 × 3 轮、**2000 个种子**的模拟(满时均匀随机替换一个驻留条目):

```
  容量      LRU      随机(均值)   随机(min)  随机(max)
     4     0.0%       0.29%      0.0%      3.3%
    10     0.0%      13.77%      3.3%     25.0%     ← load_book_cached 今天的上限
    12     0.0%      22.19%     11.7%     33.3%     ← load_book_index 今天的上限
    19     0.0%      60.50%     51.7%     63.3%
    20    66.7%      66.67%     66.7%     66.7%
```

在 `load_book_cached` 真实的 cap=10 上,随机淘汰是 **13.77%**,不是「约 50%」;约 50% 要到
cap=19 才出现。**LRU 在任何 cap < 20 下恒为 0.0%**,这条是确定性的。
(本仓库此前另有一处口头引用过「cap=10 随机约 23.3%」——那是**单次采样**,落在
3.3%–25.0% 分布的顶端,不应再被引用。)

### 这一节错过什么

初版(提交 `ea1c694`)有三处实质错误,都是 Codex 评审指出、我复核确认后改的:
(1) 用 `011-wi5-after.json` 当归因基准,跨了两个动 `src/` 的提交,且该基准自身 spread 25.7%;
(2) 把全库搜索抖动移交 C5,而 C5 的范围只有首页;
(3) 「`load_book_index` 体内不读盘」这个理由是错的,真正的原因是 `search_library` 的调用链。
另外单位标成 MB(实为 MiB)、逐步明细未注明只有单样本。记在这里,因为
**逐步明细必须逐格核对、不能只对总账**是本文件上一节就已经写过的教训,这次又犯了一遍。
