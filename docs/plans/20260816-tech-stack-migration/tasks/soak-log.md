# `baseline_1b` soak 台账

> **状态：建账完成，尚未开始计数。** 下表**一行都还没有**，这是正确状态——soak 计数从
> **G2 达成之日**开始（见 [`009-e2e-annotations.md`](./009-e2e-annotations.md) §8）。
> **首行落账之前，本文件不构成对 G2 的任何宣称。**
>
> 字段定义、清零规则、门槛语义的**唯一定义处**是迁移计划 §7，本文件不复述，只做指针与执行细节。

<!-- 数据行从 G2 达成当天开始追加，一行一次全量运行，缺一列该行不计数。
     位置有硬要求：**紧接分隔行下方，中间不留空行**。契约测试只解析文件里第一张表的
     连续块，一个空行就把后面的行踢出解析范围——`pre-freeze` 检查会对它视而不见并
     照常报绿，也就是「拿冻结前的绿充数」这条正好检查不到。
     test_no_ledger_row_strays_outside_the_table 就是拦这个的。 -->
| ts_utc | commit | result | duration_s | suite_hash | browser | os | log |
|---|---|---|---|---|---|---|---|

---

## `suite_hash` 的取法

```bash
# baseline_1b 组用例 + harness 配置 + fixtures 的内容哈希，前 12 位
{ git ls-files -s tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
    tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py tests/fixtures/epub_zip.py \
    tests/fixtures/ai_stub.py tests/conftest.py \
  | git hash-object --stdin; } | cut -c1-12
```

当前 `suite_hash` 值：`91de0e171b5c`（2026-09-04 Wave 6 收口实测输出，非誊抄）。

**这个值处于 pre-freeze，不是冻结值。** G2 尚未开始。`baseline_1b` 的 22 个用例编号**今天全部落地**，
收集到 **65 条**（WI-3 的 harness 自测 9 条 ＋ WI-4 的创建路径 3 条 ＋ WI-5 的笔记创建/编辑 2 条
＋ Wave 2 的 14 条 ＋ Wave 3 的 18 条 ＋ Wave 4 的 9 条 ＋ Wave 5 的 6 条 ＋ Wave 6 的 4 条；
`tests/e2e` 全量 75 条，差额是 `acceptance_4b1` 的 3 条 skip 与白名单里的 smoke、testid 唯一性）。
Wave 7 还要往 acceptance 目录落 skip 用例并写「实测 == 常量」的守卫，acceptance 目录不在覆盖面内，
但守卫若碰 `conftest.py` 就会再变一次。写在这里是免得后来者拿今天这个值当冻结值。

**「61」是 2026-09-01 矩阵的预估，不是实测。** `scripts/lint_e2e_groups.py` 的 `EXPECTED_BASELINE_ITEMS`
从 WI-1 起就写着 61（矩阵按 41 个测试函数推算的 collected 数，已把 X-1 的 4 条算在内），且**故意**
不随每个 WI 递增——递增会把那个脚本变成 13 路串行写入点，波内并行当场作废。各模块的参数化条数
在实现中漂移（harness 自测 9、W-5a 8、K-2 11 等），所以 Wave 5 收到的 61 只是碰巧等于常量，
**不是「收齐」**；Wave 6 之后实测是 65。把常量改成实测值并加「实测 == 常量」断言归 WI-17
（跨波欠账 #2）。

**取值前必须先 `git add`。** 上面这条命令读的是**索引**，不是工作区：新用例文件在 `git add`
之前对 `git ls-files -s` 根本不存在，改过的 `helpers.py` 也仍报旧内容。WI-4、Wave 0、WI-5 三次
都在这里先拿到过一个「没变」的旧值（本次为 `06114374b405` → `6672e32e6687`）。

值的变更史（每次改都要写清作废原因，不要只覆盖数字）：

- `91de0e171b5c` ← Wave 6（WI-16）一个新模块 ＋ `tests/e2e/conftest.py` 新增两个 function 级 fixture ＋ 覆盖面**新增一个文件** `tests/fixtures/ai_stub.py`。三个理由各自都足以让旧值作废。
  - **用例增量**：`baseline_1b/test_other_ai_streaming.py`（X-1a 增量渲染且每帧是前缀、X-1a′ 桩侧握手「首块渲染 happens-before 末块发送」、X-1b 终态等值 ＋ 零真实出网 ＋ 引用页脚、X-1c stop 后重发完整收到，共 **4 条**）。baseline_1b **61 → 65 条**，`tests/e2e` 全量 **71 → 75 条**（72 passed + 3 skipped），全量耗时约 53s → **约 58s**。
  - **harness**：`conftest.py` 新增 `ai_stub`（ollama 形状的进程内 NDJSON 桩，127.0.0.1 临时端口）与 `ai_settings_ollama`（在沙箱 `ai_settings.json` 写入 `default_provider=ollama` 指向桩，用完删掉，前后复位 `ai_conversations/`）。`_server_env` 一行未动，其注入的 `READER3_AI_SETTINGS` 路径与 fixture 写的文件在运行期比对相等。**桩必须是 ollama 形状**：`server.py` 只有 `worker_ollama` 逐块推送，其余 provider 走 `worker_non_stream` 把整段答案当一个 `chunk`，浏览器侧 DOM 更新恒为 1 次，X-1a 不可能绿（矩阵 §A）。
  - **覆盖面新增 `tests/fixtures/ai_stub.py`**：它进了 `baseline_1b` 的 import 闭包，`test_soak_log_contract.py` 的闭包检查会要求它出现在上面的命令里。桩自身的「gate 超时后干净收尾、不发末块、不断连接」契约由 `tests/unit/test_ai_stub_contract.py`（3 条，unit lane）钉住——X-1a′ 的失败形态（断言失败而非 timeout）全靠它。
  - **两处实测订正**（已写进任务书 §6 X-1 行）：`rag.py` 的 `_keyword_fallback` 是**整句子串匹配**，矩阵给的提问 `"Alpha 这一章讲了什么？"` 对未建索引的沙箱书返回 400，本模块提问必须是正文逐字子串（`QUESTION = "Alpha prose"`）；`done` 后 `renderAll()` 会在**同一节点**里追加 `div.ai-citations`，快照不能读 `lastElementChild.innerText`，改读该节点自己的文本节点。
  - **定向破坏 4 处**（3 处 `page.route` 改写 `ai.js`，1 处改桩的临时副本），`src/` 一行未动。关键一发：把流式分支改成 `await resp.text()` 后回放，X-1a′ 以 `assert stub.completed is True` 失败、耗时 5.06s——证明 R2 的超时序关系把失败形态钉在了「断言失败」而不是「timeout」。S3（删 `abort()`）暴露首版 X-1c 对「stop 不中止 fetch」是盲的，录红后**追加**两条断言（`gate_timed_out is False`、`completed is False`），既有断言零改动。
  - 红收据 `009-WI-16`（lane e2e）记 `green`，verify 判 `SEPARATION-BROKEN`：逐行指纹核对，新增 21 行全在 X-1c 的追加断言与 `SABOTAGE_LOG` 块内，消失的记录行 1 条（破坏表占位）。
- `39f502b41e65` ← Wave 5（WI-10）一个新模块 ＋ `helpers.py` 与七个既有模块的 helper 上收。**两个理由各自都足以让旧值作废。**
  - **用例增量**：`baseline_1b/test_kernel_overlay_geometry.py`（K-3a 三浮层 `position: fixed` ＋ 祖先链无包含块制造者 ×3、K-3b 工具条对选区的绝对对位、K-3b′ 平移协变差分、K-3c 笔记编辑器贴边，共 **6 条**）。baseline_1b **55 → 61 条**（`EXPECTED_BASELINE_ITEMS` 的分母今天第一次被实测填满；「实测 == 61」的断言仍留给 WI-17），`tests/e2e` 全量 **65 → 71 条**（68 passed + 3 skipped），全量耗时约 50s → **约 53s**。
  - **helper 上收**（兑付欠账 #25）：`open_ch0`（三份合一）/ `settle_marks` / `open_reader_settled` / `open_font_popover` / `content_style` / `assert_corpus_unchanged` / `assert_visible_book_ids` / `collections_file` / `read_collections` / `http_json` / `delete_collections_with_prefix` / `frame_box` 进 `helpers.py`，七个模块切换调用点。除 `assert_corpus_unchanged` 外全是改名；那一个是把四个模块各自的字面量绊线抽成共有形状 `assert_corpus_unchanged(*checks)`，每模块的期望值与消息文本逐字留在各自的 `CORPUS_CHECKS` 里（§0 第五条：基准仍是字面量）。
  - **两处实测订正**（已写进任务书 §4 K-3 行）：三个浮层是 `<body>` 的直接子元素，祖先链只有 `BODY → HTML`，`rd-shell` 是兄弟——「给 `rd-shell` 加 transform 必红」这个纸面配方对着真实 DOM 是 6/6 绿，破坏点必须是 `<body>`；`smoke_data` 上 `Alpha prose` 的选区中心 x ≈ 130 落在 clamp 带内（下界 220），几何三条改用 `repeat_data`（s1 `deck`#6 cx 379 / top 180，s2 `lamp`#22 cx 735 / top 406）。实测布局 `frame_box = {x: 0, y: 40, w: 1280, h: 640}`，`Y_TOL = 20 < 40` 成立。
  - **定向破坏 5 处全部走 `page.route` 改写响应体**，`src/` 一行未动（`git diff --quiet -- src/` 退出 0）。其中一发证明了 K-3b 与 K-3b′ 并存的理由：删掉 `offsetRect` 的 `frameRect.top` 项，K-3b / K-3c 的 Y 轴红，**K-3b′ 绿**（偏移在差分里抵消）。
  - 红收据 `009-WI-10`（lane e2e）记 `green`，verify 判 `SEPARATION-BROKEN`：成因是录红后回填 `SABOTAGE_LOG` 字符串（第 546–563 行），用指纹逐行核对，全部 `assert` / `pytest.fail` 行与收据一致，无断言改动。
- `b509a1235914` ← Wave 4（WI-13/14/15）四个新模块。**纯用例增量，harness、语料、helper 与生产代码全部一行未动**——`conftest.py` / `helpers.py` / `tests/fixtures/*` / `src/` 这次都没进来（共享文件授权制见 §0.6，本波无人被授权）。
  - `baseline_1b/test_read_chapter_change_and_search.py`（R-4 换章重绘 ＋ R-5 iframe 内搜索高亮 latin/cjk 各一，**3 条**）、`test_read_presentation_anchoring.py`（R-6a 主题四态 / 字号 ± / 间距 ± 三条参数化，**3 条**）、`test_library_nav_and_collections.py`（X-2a 书架⇄阅读器往返、X-2b 侧栏范围切换、X-2c 集合范围书单，**3 条**）；`acceptance_4b1/test_r6b_cfi_reanchoring.py`（R-6b 三条，模块级 skip，**3 条**）。baseline_1b **46 → 55 条**，`tests/e2e` 全量 **53 → 65 条**（62 passed + 3 skipped），全量耗时约 42s → **约 50.4s**。
  - **三路并行的一条纪律，是本波最该带走的东西**：三个 agent 共用一个 worktree，WI-14 在跑定向破坏时把 `epub-renderer.js` 就地改了，被并跑的 WI-13 当场撞见。WI-13 的处置是对的——不碰它，自己**全程用 `page.route` 改写响应体**做破坏，一次都没写 `src/`。共享 worktree 的并行波次里这应当是硬性写法（已记为欠账 #25）。
  - **本波实测订正了欠账 #15 的说法**：字号 / 间距四个 ± 按钮的可访问名是**按钮文本 `−`（U+2212）与 `+`**，不是中文 `title`——accname 里 contents（2F）先于 title（2I）。`name="减小字号"` 匹配 0 个、`name="−"` 匹配 1 个。因为四个按钮两两重名，**限定到 `rd-pref-size` / `rd-pref-leading` 是正确性要求**，不限定就触发 strict mode 违规。
  - **另有三处生产行为被实测钉住并记账**：主题四态是死表面（欠账 #21，与 #11 同型）；字号 / 间距传到 iframe 里晚一拍，第一次点击对正文毫无效果（欠账 #22，用户可见）；多选模式的类名 `select-mode` 与样式表的 `.selection-mode` 对不上，复选框不悬停就看不见（欠账 #23）。

- `d44d99459b25` ← Wave 3.5 的 helper 上收 ＋ 一处 flaky 修复。**用例条数一条没变**（`baseline_1b` 仍 46、`tests/e2e` 仍 53），所以这次作废的不是「测了什么」，而是「怎么等」。
  - **helper 上收**（兑付欠账 #13）：`reader_frame` / `pathname_is` / `scan_marks` / `mark_id_union` 从三个 `baseline_1b` 模块提进 `helpers.py`，`open_reader` 改为委托 `reader_frame`。纯搬移——`git diff -U0 -- tests/ | grep assert` 全程只有一行变化，且是 `_scan_marks` → `scan_marks` 的改名。`scan_marks` 的返回值是两种旧形态的**超集**（`text`＋`marks` 的文本节点视角，与 `texts`＋`ids`＋`html` 的 `<mark>` 元素视角），两者都返回而不是互相推导，因为一个 `<mark>` 里有多个文本节点时它们会分叉。
  - **flaky 修复**（欠账 #16）：`test_write_recolor_and_delete.py` 的 `_open_ch0` 加了 `wait_for_load_state("networkidle")` ＋ 一次重复的数量断言。修前该模块约四成概率红；修后全量连绿 9 轮（末两轮 CPU 打满）、模块单跑 8/8 绿。**没有任何断言被删改或放松**，改的只是等待判据。
  - **代价**：全量耗时 24.51s → **约 42s**。多出来的十几秒全部是等第二遍重绘落定，是买确定性的钱。
  - 生产代码一行没动（`git diff --stat -- src/ designs/ scripts/ tests/e2e/conftest.py` 为空）。

- `6fac77825ac7` ← Wave 3（WI-9/11/12）三个新模块。**纯用例增量，harness 与语料一行未动**——`conftest.py` / `helpers.py` / `tests/fixtures/*` 这次都没进来，所以作废理由只有一个，比 Wave 2 那次干净。
  - `baseline_1b/test_kernel_actions_and_url.py`（K-2 七个 `data-action` 各一条结果断言 ＋ K-6a 直接进入 ×3 ＋ 站内翻章 ×1，共 **11 条**）、`test_kernel_host_elements.py`（K-1a 宿主齐备 ＋ init 行为证据，共 **2 条**）、`test_read_paths.py`（R-1 ＋ R-2 三机制 ＋ R-3，共 **5 条**）。baseline_1b **28 → 46 条**，`tests/e2e` 全量 **35 → 53 条**，全量耗时 19.01s → **24.51s**。生产代码一行没动（`git diff --stat -- src/ designs/` 为空）。
  - **本波实测到一处与既有记述冲突的事实，记在这里因为它会影响「同一套用例」的解读**：`rd-page-prev` / `rd-page-next` 是**死表面**——`reader.html` 的基础样式里就是 `display: none`（注释写着 keyboard-only navigation），且全仓 live 的 `js/*.js` 无任何绑定，唯一绑定在 `reader.html` 根本不加载的 legacy `js/pagination.js` 里。任何点它的用例只会等到 actionability 超时。R-2 的「三种导航机制」因此实际是 `rd-chapter-next`（站内，`<a href>` 被 `preventDefault` 截住）、TOC 行 `findAndGo()`（站内）、直接 `goto`（整页），而**不是**生成的 plan 里写的 `rd-page-next`。
  - **另一处实测契约**：站内导航时 **URL 落后于渲染**。`syncLocationToUrl()` 跑在 epub.js 的 `rendered` 回调里，所以点完 `rd-chapter-next` 或 TOC 行的那一刻，地址栏还是旧章号。WI-12 的定向破坏 D4′ 就是这么发现的：把 URL 期望改成隔壁章号，两个站内分支**照样绿**——因为断言执行时 URL 确实还是旧的。调换成「先断正文、再断 URL」之后同一发子弹三条全红。**任何先断 URL 的用例都在读陈旧状态。**

- `355afedd106b` ← Wave 2（WI-6/7/8）三个新模块 ＋ `tests/e2e/conftest.py` 的服务日志改道。**两个理由各自都足以让旧值作废，这里一并记。**
  - **用例增量**：`baseline_1b/test_write_recolor_and_delete.py`（W-5a-⓪①②③ ＋ W-6，5 个 def → 8 条参数化）、`test_write_overlap_and_disambiguation.py`（W-8a/8b、W-10a/10b 共 4 条）、`test_write_cjk_boundary.py`（W-9a/9b 共 2 条）。baseline_1b **14 → 28 条**，`tests/e2e` 全量 **21 → 35 条**。生产代码一行没动（`git diff --stat` 为空）。
  - **harness 修复**：`live_server` 原先 `stdout=subprocess.PIPE` 却从不在运行期 drain。管道容量 macOS 上是 65536 字节，实测一轮全量服务端要写 **74194 字节**——越过之后 uvicorn 卡死在 `write()` 上，此后每一条要 `page.goto` 的用例都 30 秒超时。**这是一条从建账起就在的潜伏缺陷，用例数是引爆它的量而不是它的因**：21 条时写不满 64 KiB 所以从没发作，Wave 2 涨到 35 条就跨过去了。现象极具误导性——前 27 条全绿，之后红绿交错（不碰网络的用例照常过），像随机 flaky 而不像服务端卡死。改法是把 `stdout` 落到 `tmp_path_factory` 下的日志文件：文件没有容量上限，也就不需要另起线程去 drain。修前 `6 failed, 29 passed in 187.12s`，修后 `35 passed in 19.01s`。
  - 让它作废的理由与 Wave 0 那次同类但更强：不只是「用例住在哪里」变了，**「这套用例在什么条件下能跑完」**也变了——改之前，超过约 27 条的任何一轮全量都跑不到底，冻结在那个 harness 上的 soak 计数根本不可能积累起来。
- `5e3da7c797f6` ← `tests/e2e/conftest.py` 新增 `context` fixture，把浏览器的出网掐到只剩被测服务。**用例条数没变**（仍是 baseline_1b 14 条 / `tests/e2e` 21 条），断言一条没动，变的是用例在什么网络条件下跑——这恰恰是让它作废的理由：改之前，这套用例的绿依赖于跑它的人能连上 `fonts.googleapis.com`，改之后不依赖了，两次「21 passed」不是同一套条件下的同一件事。全量耗时 32s → **14.07s**，差额就是原先真的去取了那两个字体域。
- `777174826be2` ← §0 第六条纪律落地：`helpers.py` 新增 `assert_bystanders_unchanged`（旁观条守恒从「各用例就地写一行 assert」抽成共用函数），W-7 改为调用它。**用例条数没变**（仍是 14 条），断言语义也没变（整字典等值原样），变的是它住在哪里——抽出来是为了让 `tests/unit/test_e2e_bystander_discipline.py` 有一个 grep 得到的名字可查。同 Wave 0，纯搬家一样让哈希作废。
- `6672e32e6687` ← Wave 1（WI-5）：新增 `baseline_1b/test_write_note_editor.py`（W-4 / W-7 两条，12 → 14 条），同时改 `helpers.py`——`assert_roundtrip` 加 `expected_count`（默认 1，三个既有调用点行为不变）、新增 `wait_for_note_text` 与 `_pick_target`。**两个被 hash 覆盖的文件同时改**，既有条数变了、既有文件内容也变了，两个理由各自都足以让旧值作废。（同批还改了 `scripts/lint_e2e_selectors.py`，但它**不在** hash 命令的文件清单内，不构成本次作废的原因——它的影响是扫描面 14 → 20 处，记在下面一段。）
- `06114374b405` ← Wave 0 的 helper 上收：四个私有 helper 从两个 baseline 模块提进 `helpers.py`，**三个被 hash 覆盖的文件同时改**。用例条数没变（前后都是 19 条、断言集合逐条比对无增删改），变的只是它们住在哪个文件里——`suite_hash` 覆盖的是文件内容而不是用例条数，所以纯搬家一样让它作废。
- `f56131cfe4ef` ← WI-4 的 `test_write_create_annotations.py` 进索引（3 条用例）。
- `70ee84519f02` ← WI-1–WI-3 一批提交（commit `0e411f8`）。

### 与 `suite_hash` 无关但会影响「同一套用例」判断的一次改动

2026-09-03（WI-5）修了 `scripts/lint_e2e_selectors.py` 的一个盲区：正则要求引号紧跟在 `(` 后，
于是**所有 f-string 形态的 locator 实参一处都没被扫到**；而 ADR-0014 的复合选择器要插一个
运行期 id，天然全是 f-string。实测旧正则会对一个同时含 `.some-class` 与 `[data-modal="…"]`
的探针文件报「0 处违规」。补上前缀后扫描面 **14 → 20 处**，全仓仍 0 违规。

记在这里的理由：这个脚本不在 `suite_hash` 的覆盖面内，所以它变了 hash 不变——但「这套用例
被什么强度的门禁把过关」确实变了。G2 冻结后若有人回头比对，光看 hash 会以为门禁没动过。

`70ee84519f02` 取代 `235802f4647d` 的原因**正是下面那条索引态的坑本身**：算它的时候
`tests/e2e/baseline_1b/` 与 `tests/e2e/helpers.py` 还未进索引，`git ls-files -s` 对它们
静默产出空，于是那个值算的是一个不含这两者的 suite。WI-1–WI-3 一批提交后重算得到
`70ee84519f02`。**这不是命令的缺陷被触发，是它被如实执行了**——留着这段是因为它是这条坑
唯一一次有据可查的实例。

**2026-09-02 补两个路径（WI-3 落地时由守卫逼出来的，两个都不是「顺手加宽」）：**

- `tests/conftest.py` —— **没有任何 import 语句指向它**，是 pytest 按目录层级自动加载的祖先
  conftest。它里面那个 `pytest_configure` 钩子校验 `-m` 表达式里的 marker，直接决定
  `-m baseline_1b` 能不能选中东西：改它就是改 suite。纯 AST 的 import 追踪永远看不见这一支，
  所以守卫里它是**按目录结构**入闭包的，不是追出来的。
- `tests/fixtures/epub_zip.py` —— `epub_corpus.py` 的每个 builder 都经它写盘，四本语料的字节
  全由它决定。它此前逃过守卫是因为守卫的模块解析序写反了（详见
  `tests/unit/test_soak_log_contract.py` 的 `_resolve_module` docstring）：裸名 `conftest`
  被解析成 `tests/conftest.py` 而不是 pytest 实际导入的 `tests/e2e/conftest.py`，于是后者整条
  语料依赖链都没进闭包。**结论碰巧对、理由是假的**，比直接报错更难发现。

### 与迁移计划 §7 命令的三处差异（改的是命令，不是规则）

§7 明确授权「若目录名不同，改的是这条命令，不是规则」。落地差异：

- `tests/e2e/baseline-1b` → `tests/e2e/baseline_1b`（WI-1 的实际目录名用下划线）；
- `tests/e2e/fixtures` → 本仓库没有这个目录，共享语料在 `tests/fixtures/`，按 §7 的裁定纳入 `epub_corpus.py`；
- `playwright.config.*` → **本仓库从来没有这个文件**（harness 配置在 `tests/e2e/conftest.py` 里），
  所以这一项被去掉，不是漏抄。

`git ls-files` 对未进索引的路径静默产出空，因此命令在任何时点都可跑、值合法；
文件一提交就自动进哈希，不需要再改命令。

### 取哈希前必须先确认工作树干净（运行器的前置检查）

`git ls-files -s` 读的是 **git 索引**，不是工作树。2026-09-02 实测：

| 状态 | 值 |
|---|---|
| 基线 | `990bfff749ef` |
| 改了工作树、未 `git add` | `990bfff749ef` ← 内容变了，哈希没变 |
| `git add` 之后 | `0b1448c13b23` |
| 还原后 | `990bfff749ef` |

**后果**：soak 期间有人改了 `baseline_1b` 的一条断言却没 `git add` 就跑全量，`suite_hash` 不变，
那次运行会被记成「同一套东西」的第 N 次绿——正是清零规则要堵的假绿路径，而命令的实现方式在这里漏了一档。

所以**取哈希前工作树对这几个路径必须是干净的**，且这应当是 `scripts/soak_run.py` 的前置检查，
不是靠人记得：

```bash
git status --porcelain -- \
  tests/e2e/baseline_1b tests/e2e/conftest.py tests/e2e/helpers.py \
  tests/e2e/test_harness_smoke.py tests/fixtures/epub_corpus.py
# 非空 ⇒ 拒绝落账：记的会是索引里的旧内容，不是刚跑过的那份
```

---

## 三类清零触发器（指针，规则正文在迁移计划 §7）

- `suite_hash` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- `browser` 或 `os` 变了 ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)
- 任意一次 `red` ⇒ 清零 —— [§7 台账字段（canonical）＋ 什么会让计数作废](../plan-tech-stack-migration.md#台账字段canonical-什么会让计数作废)

生产代码变（`commit` 列变）**不**清零；其余四个尚未激活的 acceptance 组怎么改也**不**清零——
它们不在上面那条命令的覆盖路径里。

### 冻结前的行怎么标

`suite_hash` 与本文表头记录的当前值不同的数据行，**必须在该行里显式写上 `pre-freeze`**，
它不计入 ≥10 次的分母。没有第二种标法：`result` 列只有 `green` / `red`，
拿一次冻结前的绿去凑数在台账上是无痕的，靠的就是这个标记。

**复核方式**：把上面那条命令复制出来跑一遍，输出应等于表头记的值。这是 review 动作，由人执行——
自动化用例**不**断言「表头的值 == 现在算出来的值」，那会让每一次合法的套件改动都红一条无关的用例，
而冻结的语义本来就是「这个值不随之后的改动走」。台账形状的机器可解析性由
`tests/unit/test_soak_log_contract.py` 守。

---

## 两条纳入/排除口径及其代价

### 1. `tests/fixtures/epub_corpus.py` —— **纳入**，代价是「纯单测改动也会清零」

它是 `build_epub2` / `build_epub3` / `build_cjk` 的所在地，`baseline_1b` 每一条用例读的都是它造出来的书。
不纳入，就等于允许「不动用例、只动语料」地重塑十次运行的含义。

**代价是实的，不藏**：这个文件今天有三个消费方，其中两个不在 e2e 一侧——

- `tests/unit/test_fixture_epub_corpus.py`（unit lane）
- `scripts/bench.py`（基准脚本）
- `tests/e2e/conftest.py`（e2e lane，即冻结的那一侧）

因此**一次纯单测目的的构造器改动也会把 soak 计数清零**。比如第十次运行前一天，有人为了
`tests/unit/test_fixture_epub_corpus.py` 的一条断言给 `build_epub2` 加个 `lang=` 参数——计数归零，
而归零的理由与 e2e 毫无关系。这是「宁可多清零，不可假计数」的一侧误差，接受；
写在这里是为了归零那天有人知道为什么。

### 2. `pyproject.toml` —— **排除**，代价是「marker 定义变更不触发清零」

它会因依赖升级等与被测行为无关的原因变动，纳入等于每次 bump 清零。

代价是：`pyproject.toml` 里的组 marker 定义（`baseline_1b` 等五个）如果被改动——比如某个 marker
被悄悄改名，导致一批用例不再被选中——`suite_hash` 不会变。**补偿手段**：每次运行必须把
`--collect-only` 的条数写进 `log` 列指向的产物里，并与 `scripts/lint_e2e_groups.py` 的
`EXPECTED_BASELINE_ITEMS` 对齐。分母不对，那次运行不算绿（判据见
[`009-e2e-annotations.md`](./009-e2e-annotations.md) §8 G2）。
