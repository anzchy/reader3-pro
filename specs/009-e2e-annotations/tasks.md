# 009-e2e-annotations —— 任务

- **对应阶段**: Phase 1b（Playwright E2E）
- **进入条件**: Phase 0 的 0.3（`--port` + `/api/health`）与 0.5（`data-testid` 全量补齐）完成。见 `docs/plans/20260816-plan-ui-migration-sequencing.md` §6
- **退出条件**: 本文全部用例在**主 CI**（非 nightly）绿灯
- **下游**: Phase 4A / 4B 的进入条件；Phase 3 的 soak 门槛（连绿 ≥10 次、跨度 ≥5 个工作日）数的就是这一套
- **契约**: K1–K6 见 `specs/007-hygiene-and-contracts/contracts/annotation-host-contracts.md`；降级状态 S1–S5 见 `docs/plans/20260815-spec-frontend-design.md` §6.4

> **引用规则**：用**符号名**与 **testid** 定位，不写代码行号。

---

## 0. 这套 E2E 为什么不能按常规写

标注的六个接触面里 **四个坏了不报错**（K1 缺元素 → `init()` 静默 return；K3 祖先链有包含块制造者 → 浮层可见但位置错；K4 事件名拼错 → 监听方永不触发；K6 上下文读不到 → 回退解析出错误章号）。**「跑完没报错」在这里等于没测。**

由此三条写作纪律，贯穿下面所有用例：

| 纪律 | 反例（不接受） | 正例 |
|---|---|---|
| **往返断言** | 断言 `POST /api/notes/*` 发生过 | 落库 → **刷新页面** → 高亮回到同一段文字上 |
| **几何断言** | `expect(toolbar).toBeVisible()` | 工具条矩形与选区矩形（换算到视口坐标后）相对位置在容差内 |
| **降级正向证据** | 断言「没有出现错误横幅」 | **主动制造** stale，断言横幅出现且文案匹配 |

> 上游技术栈计划原写「断言 `POST /api/notes/*` → 刷新 → 断言 iframe 内重现 `<mark>`」。**后半句才是门槛**；前半句留作失败时的诊断信息，不单独构成通过条件。

---

## 1. 基础设施

| 项 | 要求 |
|---|---|
| `webServer` | Playwright 起自己的实例，端口由 `--port` 指定（**不得用 8123**，会撞开发者本地与 CI 并发），就绪探针用 `GET /api/health` |
| **图书目录隔离** | `READER3_BOOKS_DIR` 指向 tmp 目录，测试前从 fixture 拷入。**任何用例都不得读写开发者真实的 `books/`**——本套用例会创建和删除标注。⚠️ `server.py` 在**模块导入时**把它读成模块级常量，因此必须在 `webServer` 启动前置入环境变量，运行期改无效 |
| 选择器 | **只允许 `data-testid` 与 ARIA role/name**。禁止 class、`nth-child`、层级结构选择器。CI lint 强制（0.5 的产出） |
| iframe 语料 | 至少两本：一本英文短篇、一本 CJK。CJK 那本用来卡 quote/prefix/suffix 的多字节边界 |
| 并发 | 每个 worker **一个独立服务进程 + 一份独立 books 目录副本**（因为上面那条：目录是进程级常量，同一进程内无法按用例切换），`notes.json` 不共享 |

**iframe 内建选区的标准路径**（Selection 不能跨 browsing context，所以必须在 child frame 内做）：

```
child frame 内 document.createRange() → 写入 iframe 的 Selection
  → 在 iframe document 上派发 mouseup
  → 点外层工具条（testid 定位）
  → 断言往返
```

真实鼠标拖选只保留 **1 条 smoke**，其余走上面这条程序化路径——拖选在 CI 上是头号 flaky 源，而 flaky 会把 soak 门槛的计数清零。

---

## 2. 读路径用例

| # | 用例 | 关键断言 |
|---|---|---|
| R-1 | 书库 → 打开书 → 阅读器渲染 | iframe 内有正文文本节点，非空白页 |
| R-2 | 章节导航（Prev / Next / TOC 点击） | 落到正确 spine index，URL 形状符合 K6 |
| R-3 | 既有标注恢复 | 预置 `notes.json` → 打开章节 → `<mark>` 出现在**预期的那段文字**上（比对 `textContent`，不是数量） |
| R-4 | 翻章后重绘 | 换章 → 新章高亮数量正确 **且** 旧章高亮不残留（K4 的可失败断言） |
| R-5 | 阅读页内搜索 | 命中高亮出现——**K5 的第二个消费方是 `search.js`**，这条用例是它唯一的护栏 |

---

## 3. 写路径用例（本文的重点）

> 4B.1 的退出门槛写的是「1b 的标注 E2E **零改动**全绿」。**这条只有在写路径被覆盖时才成立**——`commands.ts` 那六个方法（`toggleMarkerAnnotation` / `toggleAnnotation` / `deleteCurrentAnnotation` / `saveNote` / `deleteAnnotations` / `createAnnotation`）恰恰是最容易漏的一层：读侧渲染肉眼可见，写侧只在刷新后才暴露。

**每条用例的收尾动作统一为：刷新页面 → 断言高亮/笔记回到同一段文字上。** 没有这一步的用例不算数。

| # | 用例 | 补充断言 |
|---|---|---|
| W-1 | 创建 **marker** | 刷新后 `<mark>` 覆盖的 `textContent` 与选中文本一致 |
| W-2 | 创建 **wavy** | 同上，且样式类型正确 |
| W-3 | 创建 **underline** | 同上 |
| W-4 | 创建 **note**（含笔记正文） | 刷新后 tooltip / Notes 面板能读回笔记文本 |
| W-5 | **改色**（yellow → green） | 刷新后颜色为 green，且**标注 id 不变**（改色不是删了重建） |
| W-6 | **删除** | 刷新后该段文字上无 `<mark>`；`notes.json` 里对应条目消失；**其他标注不受影响** |
| W-7 | **笔记编辑保存**（打开已有笔记 → 改文本 → 保存） | 刷新后读回新文本；这条走 `note-editor` → `commands.saveNote` 的完整链 |
| W-8 | 重叠标注 | 在已有标注上再划一段重叠区域，两条都能刷新后恢复 |
| W-9 | CJK 书上重复一遍 W-1 与 W-7 | quote/prefix/suffix 的多字节边界 |
| W-10 | 同章重复文本消歧 | 章内出现两处相同文字，标注第二处，刷新后落在**第二处**（prefix/suffix 生效） |

**W-6 的反向断言不可省**：删除是唯一会破坏用户数据的操作，"删对了一条"和"顺手删掉了别的"在 UI 上看不出来。

---

## 4. K1–K6 各一条能失败的断言

| 契约 | 用例 | 断言 |
|---|---|---|
| **K1** | K-1 | 用 `page.evaluate` 移除 `annotation-toolbar` 后重载标注 UI → 断言控制台出现明确 `console.error` 且降级标记置位。**不能只断言"工具条不见了"**——契约的价值在于把静默变响亮 |
| **K2** | K-2 | 工具条每个 `data-action` 逐个点一遍，断言**结果**（标注真的产生/删除/改色），不是断言按钮存在 |
| **K3** | K-3 | ①三个浮层各跑 `containingBlockAncestor(el) === null`；②工具条矩形与选区矩形相对位置在容差内。判据与参考实现见契约文件 |
| **K4** | R-4 | 见读路径 R-4（翻章后新章高亮正确、旧章不残留） |
| **K5** | R-5 + W-1 | `search.js` 与 `annotations.js` 两个消费方各至少一条 |
| **K6** | K-6 | 在 `/read/{bookId}/{chapterIndex}` 上创建标注，断言 `notes.json` 里的 `chapter_index` **等于 URL 里那个数**。4B.1 删掉 `location.pathname` 回退后，另加一条：`window.Reader3Ctx` 缺失时抛错而非静默猜测 |

---

## 5. S1–S4 降级状态各一条正向证据

每条都要**主动制造**降级条件，再断言 UI 明确显示——「没有横幅」不是证据。

| 状态 | 制造方式 | 断言 |
|---|---|---|
| **S1** 标注 stale | 改写 `notes.json` 里的 spine 指纹使其与当前书不匹配 | 阅读器顶部横幅出现，文案匹配；Notes 面板逐条标记 |
| **S2** 索引 stale | 使 chroma 指纹不匹配 | 书卡第五态 + 搜索面板顶部提示 |
| **S3** pickle 回退告警 | `READER3_ALLOW_PICKLE=1` 启动 | 书库与阅读器都出现全局告警条 |
| **S4** 存储格式/迁移进度 | 准备一本旧格式书 | 书卡上 `storage_format` 标记正确 |

> S1–S4 的**落地阶段**是 Phase 3（先以朴素横幅落到 Jinja 模板）与 Phase 4A.4（按设计规格重做）。本文的用例随之分两批写：Phase 3 出口时对朴素形态断言，4A.4 改版后只改 testid 映射、断言语义不变。
>
> **S5（notes 写冲突）不在 1b**——它依赖 Phase 2a 的乐观并发，届时随 2a 一起补。

---

## 6. 其他

| # | 用例 | 说明 |
|---|---|---|
| X-1 | AI SSE 流式 | 首 token 到达 + 流正常结束 + 中断可恢复 |
| X-2 | 书库导航与集合切换 | 4A.4 切页时的护栏 |

---

## 7. 不在 1b 范围

- 迁移相关的 iframe 标注 E2E —— 属 **Phase 3 出口**（真实 `--migrate` 前后标注不漂移），在 `specs/012-storage-format/` 里
- S5 写冲突 UI —— 随 Phase 2a
- 视觉回归 / 截图对比 —— 本套只测行为
- 性能基准 —— 属 Phase 1a

---

## 8. 退出门槛

- 上面所有用例在**主 CI** 绿灯（非 nightly）
- 选择器 lint 通过：全套用例零 class / 结构选择器
- **零 flaky**：连续 3 次全量运行无偶发失败才算达标。理由见 soak 门槛——一条会偶发失败的 E2E 当不了 Phase 3 数据迁移的验收基准，而 flaky 会让计数反复清零
- 单次全量运行时长记录在案（后续 soak 期间要跑十次以上，时长本身就是可行性约束）
