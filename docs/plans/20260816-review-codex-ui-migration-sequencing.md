结论先行：**NEEDS REVISION**。我不同意主计划文末“只剩两个非阻塞决策”的判断。R12 形成了真实依赖环，R5 判据不完整，存储迁移也缺少双文件事务协议；这些都应在开工前修订。

本次为只读静态核验，没有运行测试、启动服务器或修改文件。

## 类别 1：R1–R12 落地质量

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 1 | HIGH | 9/10 | R1 的职责判断合理，但“纯拆分”与“`commands.ts` 不直接碰 DOM”无法同时按现有方法机械落地：六个方法直接读取 `Range`、`contentEl`、textarea，并操作 overlay、renderer 与事件。 | [specs/014-ts-frontend-reader/tasks.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/014-ts-frontend-reader/tasks.md>) §4B.1 `commands.ts`；[annotations.js](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/web/static/js/annotations.js>) `saveNote()` / `createAnnotation()` / `deleteAnnotations()` | 在拆分前定义 `SelectionSnapshot` 与 `CommandPorts`：interactions/note-editor 提取 DOM 输入，commands 只编排 notes API、renderer、overlay ports；否则取消“不得碰 DOM”的门槛。 |
| 2 | MEDIUM | 10/10 | R4 的运行时代码删除边界正确，`BookIndex` / `ChapterIndex` 仍由三条活路径使用；但 001 的 plan/data-model/tasks 仍要求实现 `SearchIndex`、`from_book_pkl()`、`build_from_library()`，属于会把死代码重新引入的残留引用。 | [search_service.py](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/search_service.py>) `load_book_index()`；[specs/_archive/001-search-features/tasks.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/_archive/001-search-features/tasks.md>) T027/T029/T030；[data-model.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/_archive/001-search-features/data-model.md>) `SearchIndex` | 给 001 文档加醒目的 `Superseded` 说明，将三项标记为取消并指向当前 per-book `load_book_index()` 路径。 |
| 3 | HIGH | 9/10 | R5 的 `containingBlockAncestor()` 仍会漏报：未检查独立 `translate` / `rotate` / `scale`、`content-visibility`，也漏了 `will-change: contain/content-visibility/backdrop-filter/translate/rotate/scale`。这些属性可以建立 fixed containing block。[CSS Transforms 2](https://www.w3.org/TR/css-transforms-2/)、[CSS Containment 2](https://www.w3.org/TR/css-contain-2/)、[CSS Will Change](https://www.w3.org/TR/css-will-change/) | [annotation-host-contracts.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/contracts/annotation-host-contracts.md>) K3 `containingBlockAncestor()` | 补齐属性集合，并为每种制造属性建立参数化浏览器断言；旧 Safari 还应检查 `webkitBackdropFilter`。 |
| 4 | CRITICAL | 10/10 | R12 把未来状态测试塞进 Phase 1b 的“全部绿灯”门槛：K1 的响亮失败和 K6 的抛错要到 4B.1 才实现；S1–S4 要到 Phase 3/4A.4 才实现，而 Phase 3、4A 又依赖 1b 先通过，形成直接依赖环。 | [specs/009-e2e-annotations/tasks.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/009-e2e-annotations/tasks.md>) §4/§5/§8；[主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §7；[specs/014-ts-frontend-reader/tasks.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/014-ts-frontend-reader/tasks.md>) §4B.1 | 将 E2E 分成 `baseline-1b` 与按阶段激活的 acceptance 组：K1/K6 新行为在 4B.1 激活，S1–S4 在 Phase 3/4A.4 激活；只有 baseline 计入 1b 和 soak。 |
| 5 | HIGH | 10/10 | R12 并未与 K1–K6 完整对应：W-5 要求“改色且 id 不变”，但当前色板只改变下一次创建颜色，后端 PUT 也只能改笔记文本；K2 的 Copy/Ask AI 不能用“标注产生”断言；K5 没有明确覆盖 `applyThemeSettings()`，`displaySectionIndex()` 也只可能被 R-2 间接覆盖。 | [specs/009-e2e-annotations/tasks.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/009-e2e-annotations/tasks.md>) W-5/K-2/K-5；[annotations.js](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/web/static/js/annotations.js>) `setSelectedColor()` / `toggleMarkerAnnotation()`；[server.py](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/web/server.py>) `api_update_annotation()` | 1b 的 W-5 改为现状特征化；若产品确需原地改色，单列 API+UI 行为变更阶段。K2 分别断言 clipboard、AI event/panel；K5 增加主题应用测试，并显式把 R-2 映射到 `displaySectionIndex()`。 |

## 类别 2：两个未决项的明确裁决

| 未决项 | 明确推荐 | 理由 | 选错的代价 |
|---|---|---|---|
| R6 / 性能 C5 落点 | **推迟到 Phase 3，与 `manifest.json` 同批完成。** | 当前只有一本书；为 Phase 2b 新造短命书目 sidecar，会额外引入缓存失效、原子写、文档与清理协议，收益不足以覆盖第二种持久格式。 | 选 Phase 2b：产生两套元数据真相源并承担清理债务；选 Phase 3 的代价只是首页全文反序列化多保留一个阶段。 |
| 标注暗色变体 | **采用显式 `--p-hl-*-dk`。** | 可审计对比度、跨浏览器确定、无需为 `color-mix()` 维护旧 Safari fallback。 | 选动态混色：不同浏览器/色彩空间结果可能漂移，标注可读性难以成为稳定验收。 |
| 原型 token 映射 | **不保留原型 token 别名，4A.1 按角色一次性替换。** | 避免生产 CSS 同时存在一层、两层两套词汇。 | 保留兼容别名：新 CSS 会继续引用旧名，双层体系名存实亡。 |

推荐映射：

- `--canvas` → `--r3-bg`
- `--surface` / `--surface-raised` → `--r3-surface` / `--r3-surface-raised`
- `--surface-muted` 按用途拆为 `--r3-surface-sunken` 或 `--r3-surface-hover`
- `--text` / `--ink` / `--muted` / `--quiet` → `--r3-text` / `--r3-text` / `--r3-text-muted` / `--r3-text-subtle`
- `--anno-*` 的原始值进入 `--p-hl-*`；组件只能使用 `--r3-hl-*`
- `--page-bg` / `--page-ink` / `--page-quiet` → 新增 `--r3-reading-bg` / `--r3-reading-text` / `--r3-reading-text-muted`，不要与 app chrome 的 surface/text 混为一个角色

## 类别 3：此前未覆盖的盲区

### 内部一致性

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 6 | HIGH | 10/10 | 技术计划仍写“Playwright 可 nightly”，而主计划和 009 明确要求标注 E2E 在主 CI；两个门槛不能同时成立。 | [技术计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-plan-tech-stack-migration.md>) Phase 1；[009 tasks](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/009-e2e-annotations/tasks.md>) 退出门槛 | 明确标注核心套件进入主 CI；仅额外浏览器、视觉或长耗时 AI 场景允许 nightly。 |
| 7 | MEDIUM | 10/10 | 4B.3 写“四字体”，设计规格写 `system/serif` 二选一；设计规格又同时把思源宋体称为待删除商业字体和可 self-host 开源字体。 | [014 tasks](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/014-ts-frontend-reader/tasks.md>) §4B.3；[前端设计规格](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-spec-frontend-design.md>) D1/§6.3 | 全部统一为 `system/serif` 两值；明确 serif 是 self-host Source Han Serif，或在资产未落地前使用系统 serif fallback。 |
| 8 | MEDIUM | 10/10 | S1–S5 使用不存在的 `--r3-warn` / `--r3-danger`，而 token 表定义的是 `--r3-warning` / `--r3-error`。 | [前端设计规格](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-spec-frontend-design.md>) §3.3/§6.4 | 统一使用已经定义的 `--r3-warning` / `--r3-error`，并补相应 subtle/background semantic token。 |

### 完整性

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 9 | HIGH | 10/10 | §9 声称九个里程碑各有 `tasks.md`，实际只有 009 与 014；其余七个里程碑缺少可恢复清单，无法支撑“单人可随时暂停”。 | [主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §9；[specs](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs>) | 至少在分支开工前创建任务骨架，记录前置条件、完成证据、当前 checkpoint、回滚步骤与下一动作；M0/M1 应先补。 |
| 10 | MEDIUM | 10/10 | 当前已实现字号/行距和 `reader3-font-settings`，计划却称控件全无处理器，并改成四个新 localStorage key；未定义一次性迁移会重置用户偏好。 | [reader.html](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/web/templates/reader.html>) `Font Settings Script`；[epub-renderer.js](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/src/reader3_app/web/static/js/epub-renderer.js>) `getFontSettings()`；[前端设计规格](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-spec-frontend-design.md>) D1/§6.3 | 4B.3 增加 legacy JSON 读取、范围校验、写入新 key、迁移完成标记及回归测试。 |
| 11 | MEDIUM | 9/10 | Phase 5 只定义“启动”，没有服务所有权与关闭语义：端口上已有 Reader3 时是否复用、浏览器关闭是否停服、Ctrl-C 如何传递、如何避免杀死用户自有进程均未说明。 | [技术计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-plan-tech-stack-migration.md>) Phase 5 `reader3 launch` | 规定前台模式：只终止自己创建的子进程；健康的既有 Reader3 可复用但不拥有；非 Reader3 端口占用立即报错；SIGINT/SIGTERM 转发并等待退出。 |
| 12 | MEDIUM | 10/10 | 新增 env、localStorage key、`manifest.json`、`chapters.jsonl` 和迁移命令，却没有把技术文档更新列入阶段门槛，违反仓库明确规则。 | [AGENTS.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/AGENTS.md>) Documentation Rule；[docs/technical-detail.md](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/technical-detail.md>) Update Rule | Phase 0/3/4B/5 各自增加 `docs/technical-detail.md` 与相关数据位置文档更新任务。 |

### 可行性

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 13 | HIGH | 9/10 | E2E 执行器混用了两套模型：仓库安装的是 Python `pytest-playwright`，009 却使用 Node Playwright Test 的 `webServer` 概念，同时要求每 worker 一服务；当前没有可执行拓扑。[Python runner](https://playwright.dev/python/docs/test-runners)、[Node webServer](https://playwright.dev/docs/test-webserver) | [pyproject.toml](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/pyproject.toml>) dev dependencies；[009 tasks](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/009-e2e-annotations/tasks.md>) §1 | 明确选择 Python runner；用 pytest worker/session fixture 启动子进程、先设置 `READER3_BOOKS_DIR`、分配空闲端口。初版主 CI 单 worker；需要并行时再按 worker id 分库分端口。 |
| 14 | HIGH | 9/10 | `manifest.json + chapters.jsonl` 是两文件提交，但计划只写“写入→校验”；崩溃可能留下 manifest 指向半文件，且“自动回退 pkl”与 `READER3_ALLOW_PICKLE=1` 默认关闭互相矛盾，所谓“删新文件即可回滚”也漏了开启 legacy read 的步骤。 | [技术计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-plan-tech-stack-migration.md>) Phase 3/A2/A5；[主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §4 | 定义状态机：写两个 tmp、fsync、完整验证、先原子替换 chapters、最后替换 manifest 作为 commit marker；区分 missing/valid/corrupt，且只有显式 legacy flag 才读 pkl。 |
| 15 | HIGH | 9/10 | iframe 门槛“`textContent` 与文本偏移不变”只是必要条件，不足以证明 CFI 不变；包裹/拆分文本节点可保持扁平文本相同却改变 DOM path。“逐字节”对 JS DOMString 也不是可执行定义。 | [前端设计规格](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-spec-frontend-design.md>) §6.0；[014 tasks](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/014-ts-frontend-reader/tasks.md>) §4B.2 | 改为“UTF-16 code-unit 序列不变 + body 结构签名不变 + 同一 CFI 在调整主题/栏宽后仍解析到同一 quote”的三重断言。 |
| 16 | MEDIUM | 9/10 | 两个“机器可验”规则仍不可直接实现：testid 正则在原始 Markdown 中是 `\|`，复制进正则会匹配字面 pipe；依赖规则只禁止部分反向 import，不能禁止 `interactions → notes-api` 绕过 commands，也没有全局 cycle 规则。 | [主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §6/§7；[014 tasks](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/specs/014-ts-frontend-reader/tasks.md>) §4B.1 出口 | 在代码块中固定 canonical regex：`^(?:lib|rd|set)-[a-z0-9]+(?:-[a-z0-9]+)*$`；选定 dependency-cruiser，并配置 `no-circular`、禁止 interactions 直连 notes-api、notes-api 禁止 sibling runtime import 等规则。 |

### 歧义

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 17 | MEDIUM | 9/10 | “开工前必须冻结四份合同”有两种读法：全部冻结后 Phase 0 才开工；或每份只需在其消费者开工前冻结。表中 token/messages 又分别落在 4A.1/4A，实施者会写出完全不同的依赖图。 | [主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §3 | 改成“各消费者开工前冻结”，并逐项列前置边：testid→1b、API v1→2a、token/messages→首个页面切片。 |

### 风险与排序

| # | 严重度 | 置信度 | 发现 | 位置 | 建议 |
|---|---|---:|---|---|---|
| 18 | HIGH | 10/10 | §6 声称 1b“不阻塞后端”、Track D“不阻塞任何人”，但 §7 规定 Phase 3 同时依赖 1b soak 与 Track D；真实 M3 是 M2、M1b、MD 三路汇合点。 | [主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) §6/§7/§9 | 把措辞改为“1b 不阻塞 2a/2b，但阻塞 M3；MD 仅阻塞 M3”，并在 §9 增加正式 DAG/依赖表。 |
| 19 | HIGH | 9/10 | 4A.2 先迁 settings，4A.3 才建立 `api.ts` / `idb.ts` / `messages.ts`；当前 settings 已有 provider API、持久化和文案逻辑，因此会被迫先写临时代码再重构。 | [主计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260816-plan-ui-migration-sequencing.md>) Phase 4A；[技术计划](</Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/docs/plans/20260815-plan-tech-stack-migration.md>) 工具链与逐页切片 | 调整为 `4A.0 → 4A.1 → 4A.3(core) → 4A.2 → 4A.4`；至少把 api/idb/messages/escape 放到 settings 前。 |

## Overall Verdict

**NEEDS REVISION**

Top 3 风险：

1. **Phase 1b 退出门槛存在依赖环**，当前计划无法按顺序跑通。
2. **Phase 3 缺少双文件事务、失败状态和显式回滚协议**，可能让派生数据处于半提交状态。
3. **浏览器安全门槛并未真正机器化**：E2E runner 拓扑未定，K3 判据漏属性，iframe 判据不足以保护 CFI。

计划最强的地方：权威文档分工、Phase 4A/4B 拆分，以及 Phase 3→4B 围绕标注锚定严格串行，这三个顶层决策是成立的；问题集中在修复落地和门槛可执行性，不需要推翻总体架构。