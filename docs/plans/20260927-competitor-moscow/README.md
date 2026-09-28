# 竞品对比与 MoSCoW 优先级（2026-09-27）

> **这是一份规划文档，不是账本，也不是执行顺序。**
> 已建成的事实只在 [`docs/feature-ledger.md`](../../feature-ledger.md)；执行顺序只在
> [`20260824-frontend-backend-plan-progress.md`](../20260824-frontend-backend-plan-progress.md)；分支编号只在
> [`plan-tech-stack-migration.md` §9](../20260816-tech-stack-migration/plan-tech-stack-migration.md)。
> 本文**不改**以上任何一处，也不分配分支编号——需要新分支的地方一律写「需在 §9 分配编号」。
> 本文的 MoSCoW 是给维护者拍板用的**提案**，被采纳的条目要落到上面三处才算数。

---

## 1. 范围与方法

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-27（所有数字当天抓取） |
| 我方基线 | `docs/feature-ledger.md`，Synced 2026-09-27 @ `8e1cf48`，F-001..F-041。本文我方列**只依据账本状态**（`accepted` / `partial` / `stub` / `absent` / `unknown`），逐格引 F-ID |
| 竞品来源 | [`appendix-competitors.md`](appendix-competitors.md)（25 个产品：17 个开源 + 8 个闭源）与 [`appendix-paper-one.md`](appendix-paper-one.md)（xiaolai/paper-one 深挖）。**本文关于竞品的每一条事实都出自这两份附录**，没有从记忆补充 |
| 约束来源 | ADR-0001（文件系统即数据库）、ADR-0004（ChromaDB + MiniLM，不换）、ADR-0008（技术栈边界：后端 Python、前端 TS 无框架、不做桌面壳）、ADR-0011（API v1 冻结，Phase 3 只许新增）；`CLAUDE.md` 宪章第 2 条 Simplicity / YAGNI、第 3 条 File-Based State |
| 产品定位（评判标尺） | 轻量、自托管、**单用户本机**的 EPUB 阅读器，核心是「和 LLM 一起读书」，并保持 "vibes codable"。**不做 KOReader，不做 Calibre。** |

**热度怎么量的**

- **开源**：GitHub stars（`gh api repos/OWNER/NAME` 实时读 `stargazers_count`），同时记 forks、最近 push、license。
- **闭源**：没有统一口径，用「热度代理」：iOS 评分数（iTunes lookup API；Kindle / Apple Books / Readwise 取美区，WeRead / 得到取中国区）、Moon+ Reader 用 AppBrain 的第三方下载估计、Gemini Notebook / Glasp / 得到 / WeRead 的用户数取公司或媒体声明。
- 两张表**分开排、不可互比**：stars 衡量的是 GitHub 关注度，不是使用量；各商店的评分数之间也不可比。

**注意事项（估计值与未能核实的数据）**

- 闭源用户数是公司/媒体声明，**非审计数字**；WeRead 的 2.1 亿累计用户是 2020 年的数字；Apple Books 预装，评分数严重低估；Readwise 付费产品，评分数低估。
- 能力矩阵取自各 repo README 的关键词检索（Readest 额外读了其 AI 助手 PR），`?` 表示**未能确认**，不等于没有。
- paper-one 的账本快照（2026-09-12）比其 HEAD 旧 15 天；此后的变化只来自 commit 标题与文件存在性，**没有跑过它的 app**；其主页 https://paper.one 未能打开。
- paper-one 的 MoSCoW 用法**没有在任何读到的材料里出现**（只在课程笔记的提纲里），本文的 MoSCoW 分桶是我方自拟，不是照搬。
- 我方账本本身的 `baseline` 行是 2026-09-27 回溯种下的，`Confirm` 步骤从代码推导、未在运行中的 app 上执行（见账本 Audit log）。

---

## 2. 竞品清单

### 2.1 开源，按 GitHub stars 排序

| # | 产品 | Stars | Forks | 最近 push | License | 类别 | 一句话 |
|---|---|---|---|---|---|---|---|
| 1 | [Open Notebook](https://github.com/lfnovo/open-notebook) | 39,544 | 4,583 | 2026-09-20 | MIT | AI「与资料对话」（NotebookLM 克隆） | 多 provider RAG + 笔记 + 播客；不是阅读器 |
| 2 | [KOReader](https://github.com/koreader/koreader) | 29,945 | 1,925 | 2026-09-27 | AGPL-3.0 | 电纸书 / Android 阅读器 | Kindle / Kobo / PocketBook / Android，多格式；有 AI 插件生态 |
| 3 | [Koodo Reader](https://github.com/koodo-reader/koodo-reader) | 28,317 | 2,116 | 2026-09-27 | AGPL-3.0 | 跨平台阅读器（桌面/移动/Docker web） | 同步、备份、自定义模型 AI（翻译、词典、摘要、Ask AI、AI Chat） |
| 4 | [Readest](https://github.com/readest/readest) | 24,640 | 1,619 | 2026-09-27 | AGPL-3.0 | 跨平台阅读器（Tauri） | 基于 foliate-js；AI 助手（2026-01 合入）做 BM25+向量混合 RAG，防剧透上下文 |
| 5 | [Calibre-Web](https://github.com/janeczku/calibre-web) | 18,255 | 1,866 | 2026-09-20 | GPL-3.0 | 自托管书库服务 | 基于 Calibre DB 浏览/阅读/下载；OPDS、书架、Kobo 同步 |
| 6 | [Audiobookshelf](https://github.com/advplyr/audiobookshelf) | 14,463 | 1,183 | 2026-09-26 | GPL-3.0 | 自托管有声书/播客服务 | 附带 EPUB/PDF web 阅读器与收藏 |
| 7 | [Kavita](https://github.com/Kareadita/Kavita) | 11,754 | 674 | 2026-09-27 | GPL-3.0 | 自托管阅读服务 | 多用户，漫画/书籍；EPUB 高亮批注、OPDS、收藏、阅读清单 |
| 8 | [bilingual_book_maker](https://github.com/yihong0618/bilingual_book_maker) | 9,811 | 1,287 | 2026-09-27 | MIT | AI + EPUB 工具（CLI） | 用 LLM 把 EPUB 译成双语版；不是阅读器 |
| 9 | [Foliate](https://github.com/johnfactotum/foliate) | 8,764 | 419 | 2026-04-08 | GPL-3.0 | Linux 桌面阅读器（GTK） | 其 foliate-js 引擎也驱动 Readest 与 paper-one |
| 10 | [Komga](https://github.com/gotson/komga) | 6,696 | 415 | 2026-09-25 | MIT | 自托管媒体服务 | API、OPDS v1/v2、Kobo 与 KOReader 同步 |
| 11 | [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) | 6,334 | 528 | 2026-09-26 | GPL-3.0 | 自托管书库服务 | 自动入库、规则书架 Magic Shelves、KOReader/Kobo 同步、send-to-eReader |
| 12 | [karpathy/reader3](https://github.com/karpathy/reader3)（我方上游） | 3,872 | 486 | 2025-11-18 | 无 | AI + EPUB 阅读器（极简） | 复制粘贴给 LLM 的工作流，无内置 AI；创建当天后未再维护 |
| 13 | [Thorium Reader](https://github.com/edrlab/thorium-reader) | 2,883 | 238 | 2026-09-25 | BSD-3-Clause | 桌面阅读器（Readium） | 无障碍优先；EPUB/PDF/有声书、OPDS、LCP DRM、TTS |
| 14 | [BookLore](https://github.com/booklore-app/booklore) | 1,251 | 91 | 2026-09-25 | AGPL-3.0 | 自托管书库服务 | 多用户、智能书架、自动元数据、Kobo/KOReader 同步、BookDrop 导入、OPDS |
| 15 | [assistant.koplugin](https://github.com/omer-faruq/assistant.koplugin) | 622 | 74 | 2026-09-26 | GPL-3.0 | 阅读器 AI 插件 | 在 KOReader 里就高亮文本问 Claude / GPT / Gemini / DeepSeek / Ollama |
| 16 | [taylorren/ai-reader](https://github.com/taylorren/ai-reader)（reader3 fork） | 12 | 2 | 2026-09-20 | 无 | AI + EPUB 阅读器 | 最高星的 reader3 fork：AI 分析/核查/讨论，Ollama 与 OpenAI 兼容 API，高亮导出 Markdown |
| 17 | [xiaolai/paper-one](https://github.com/xiaolai/paper-one)（"Paper"） | 8 | 5 | 2026-09-27 | MIT | 桌面/移动阅读器（Tauri 2 + React + Rust） | 个人项目、未发布；EPUB + PDF，锚定标注，可选 P2P 同步（详见下方小传） |

排除在排名之外（相邻品类，非阅读器）：calibre 桌面版（26,022★）；通用「与文档对话」RAG 工具 kotaemon、LocalGPT、PrivateGPT、AnythingLLM、RAGFlow、paper-qa；Zotero AI 插件；hectorqin/reader；已停服的 Omnivore。检索 "chat with epub" / "epub reader llm" 只找到 0–1★ 的 repo。

### 2.2 闭源 / 商业，按热度代理排序

| # | 产品 | 热度代理 | 类别 | 一句话 |
|---|---|---|---|---|
| 1 | Amazon Kindle（+ Ask this Book） | iOS 美区 4.86★ / **5,854,143** 条评分 | 书店 + 阅读器，AI 问答 | 2025-12 起 iOS（美区）对数千本畅销书提供防剧透 RAG 问答 |
| 2 | Gemini Notebook（原 NotebookLM） | **30M+ 用户**（2026-07，声明值） | AI「与资料对话」 | 上传书（PDF/文本）得到带引用问答、摘要、音频概览；2026-07-16 改名 |
| 3 | 微信读书 WeRead（+ AI问书） | iOS 中国区 4.86★ / **1,697,700** 条评分；约 2.1 亿累计用户（2020 年数字） | 书店 + 阅读器，AI 问答 | 2024-04-23 上线 AI问书：长按得到带书内引用与追问建议的回答 |
| 4 | Apple Books | iOS 美区 4.46★ / 93,679 条评分（预装，严重低估） | 书店 + 阅读器 | 高亮、收藏、iCloud 同步；未确认有书内问答 |
| 5 | Moon+ Reader | Android 约 2,800 万下载（AppBrain 第三方估计） | Android 阅读器 | TTS、批注、OPDS、Dropbox/WebDAV 同步；未确认 AI 问答 |
| 6 | 得到 Dedao（+ AI学习助手） | iOS 中国区 4.45★ / 32,453 条评分；声明 6,500 万+ 平台用户 | 课程 + 电子书 + 音频 | AI 助手问答并链回平台内容；不覆盖用户自己的文件 |
| 7 | Glasp | 2M+ 用户（站点声明） | 网页/PDF 高亮 + AI | 社交高亮，基于高亮生成 AI 摘要；不读 EPUB |
| 8 | Readwise Reader（+ Ghostreader） | iOS 美区 4.61★ / 584 条评分（付费，低估） | 稍后读 + EPUB/PDF + AI | Ghostreader 回答带回跳引用、释义/简化、感知阅读位置；TTS；高亮导出 Obsidian/Notion |

链接与原始数字见 [`appendix-competitors.md`](appendix-competitors.md) §(a)。

### 2.3 xiaolai/paper-one 小传

**栈**：Tauri 2 + React 19 + Vite 7 + TypeScript，Rust 后端；EPUB 走 foliate-js 的固定 fork，PDF 走 pdf.js 6.2；P2P 用 iroh / iroh-blobs；测试有 Vitest、Playwright、Stryker 变异测试、fast-check、dependency-cruiser。2026-08-24 创建，一个月内 ≥500 个 commit，v0.4.8，0 个 GitHub release，README 自称「个人项目……离发布还远」。
**构建方式是 kernel + capabilities**：`capabilities.manifest.json` 声明可选能力 `peer` / `sync` / `circle` / `public` / `voices` / `passages` / `webhost`，每项声明所支持的平台，`pnpm verify:without` 证明去掉某个能力后应用仍能构建。
**AI 已于 2026-09-19 全部移除**：commit「Remove every AI feature, and the surfaces they left behind」（211 个文件，−53,879 行）删掉了 companion、Look up、神经语音、本地 `llama-server`、Codex/Claude 路由、云端端点。理由原话：「the providers cannot be unified … and the set of useful things to do with a model inside a reader turned out to be very small」。它的 README 里 "gloss" 那条因此已过期。
**我方账本格式源自它的账本**：同样的五态（Shipped/Partial/Stub/Absent/Unknown ↔ 我方 accepted/partial/stub/absent/unknown）、同样的「a stub is not a feature」与「claim nothing」措辞；我方加了永久 `F-NNN` ID、必填 `Tests` / `Evidence`、absent 必须挂 debt 或计划。它的账本 Parts 2–3 有一张对 10 个阅读器的竞品矩阵与三桶分诊（table stakes / contested / differentiators）——本文 §4 沿用这个三桶结构；**我方账本里没有竞品矩阵，本文也不往账本里加**。

**对我方的含义**：Paper 是「和我们同源方法论、却在 AI 上得出相反结论」的对照组。它的移除理由是本文 §5 里 AI 类 Could / Won't 条目的反证依据，也是我方 AI 差异化必须「窄而深」而非「多而散」的提醒。

---

## 3. 能力对比矩阵

图例：✓ 有 · partial 有限/插件 · ✗ 无 · ? 附录未能确认 · n/a 不适用。
**我方列只依据账本状态**；竞品列取自两份附录（paper-one 列以 `appendix-paper-one.md` 的「Now」列为准，覆盖 `appendix-competitors.md` 矩阵里的过期格）。

| 组 | 能力 | **Reader3 Pro**（账本） | Readest | Koodo | KOReader | Kavita | paper-one | karpathy/reader3 | Kindle | WeRead |
|---|---|---|---|---|---|---|---|---|---|---|
| 阅读 | EPUB 阅读 | ✓ F-009 accepted | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗（专有格式；EPUB 经 Send-to-Kindle） | ✓（导入） |
| 阅读 | 阅读纸色主题 / 字体 | **stub** F-031、F-032（仅字号/段距 F-010 partial） | ? | ? | ? | ? | ✓ 5 主题 + 跟随系统、字体可选 | ? | ? | ? |
| 阅读 | 点按/手势翻页 | **stub** F-033（仅键盘，F-009） | ? | ? | ? | ? | ✓（滚轮/手势；webhost 点按翻页） | ? | ? | ? |
| 阅读 | TTS 朗读 | ✗（无行） | ✓ | ✓ | partial | ? | ✓（系统语音 + Kokoro 神经语音） | ✗ | ✓ | ✓ |
| 书库 | 应用内导入 | **stub** F-034（仅 CLI F-001） | ? | ? | ? | ? | ✓（文件夹、拖放） | ✗ | ? | ✓（导入） |
| 书库 | 删除书 | **absent** F-035 | ? | ? | ? | ? | ✓（回收站 + 撤销） | ? | ? | ? |
| 书库 | 收藏夹 / 书架 | ✓ F-006 accepted | ✓ | ✓ | ✓ | ✓ | ✓（收藏、标签、书架） | ✗ | ✓ | ✓ |
| 书库 | 书库备份 / 导出 | **stub** F-036 | ? | ✓（备份） | ? | ? | ✓（标签/标注/卡片导出导入） | ✗ | ? | ? |
| 搜索 | 关键词全文检索（书内 + 全库） | ✓ F-011 accepted | ? | ? | ? | ? | ✓（书内；全库经 `passages`，2026-09-24） | ? | ? | ? |
| 搜索 | 语义 / 混合检索（用户可见） | ✓ F-012 accepted | ✓（向量索引仅服务 AI） | ✗ | ✗ | ✗ | ✗（关键词倒排，推断） | ✗ | ? | ? |
| AI | 书内 RAG 问答 | ✓ F-013 accepted | ✓ 混合 RAG | partial（Ask AI / AI Chat，未确认向量 RAG） | partial（插件，选区） | ✗ | ✗（2026-09-19 移除） | ✗（手工复制粘贴） | ✓ Ask this Book | ✓ AI问书 |
| AI | 多 provider | ✓ F-014 accepted（5 家） | partial（Ollama + AI Gateway） | ✓（自定义模型） | partial（插件：Claude/GPT/Gemini/DeepSeek/Ollama） | ✗ | ✗（已移除） | ✗ | ? | ? |
| AI | 防剧透（上下文限于已读位置） | ✗（无行；RAG 取全书） | ✓ | ? | ? | ✗ | ✗ | ✗ | ✓（默认，可切全书） | ? |
| AI | 回答引用可回跳原文 | ✗（无行） | partial（X-Ray WIP 可跳证据） | ? | ? | ✗ | ✗（曾有，已移除） | ✗ | ? | ✓ |
| AI | 划词即问 | partial（F-018 工具栏有 Ask AI；账本未单列其行为） | ? | ✓（AI 词典/翻译/百科弹窗） | partial（插件） | ✗ | ✗（gloss 已移除） | ✗ | ? | ✓（长按问） |
| AI | 会话线程持久化 + 导出 | ✓ F-016 accepted | ? | ? | ? | ✗ | ✗（已移除） | ✗ | ? | ? |
| AI | 书库级 AI 对话 | partial：F-017 单书 accepted；全库/收藏范围 F-039 **stub** | ? | ? | ? | ✗ | ✗ | ✗ | ? | ? |
| 笔记 | 高亮 / 批注 | partial F-018（纯文本锚定，CFI 恒 null）、F-019 partial | ✓ | ✓ | ✓ | ✓（EPUB） | ✓（CFI 锚定 + 重新锚定） | ✗ | ✓ | ✓（社交） |
| 笔记 | 笔记导出 Markdown / PKM | ✗（无行；F-040 Confirm 记「复制全部笔记」可用） | ? | ✓（CSV/MD；Readwise、Notion、Anki） | ✓（Markdown） | ? | ✓（JSON + Markdown） | ✗ | ? | ? |
| 同步/设备 | 跨设备同步 | ✗（无行） | ✓（Readest Cloud、KOReader） | ✓（OneDrive/Google Drive/WebDAV/KOReader） | ✓（kosync） | ✓（进度） | ✓（P2P，可选） | ✗ | ✓ | ✓ |
| 同步/设备 | 多设备 / PWA | ✗（无行；局域网浏览器可用，PWA 未建） | ✓ | ✓ | ✓ | ✓（web） | partial（macOS；移动端壳 Partial） | ✗ | ✓ | ✓ |
| 格式 | PDF | **stub** F-038 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| 格式 | MOBI / AZW3 / FB2 / CBZ 等 | ✗（无行） | ✓ | ✓ | ✓ | partial（漫画/comics） | ✓ | ✗ | ? | ? |
| 自托管/API | 自托管 | ✓ F-027 accepted | partial（可自托管 web，云优先） | ✓（Docker web） | n/a（设备端） | ✓ | n/a（桌面） | ✓ | ✗ | ✗ |
| 自托管/API | OPDS | ✗（无行） | ✓ | ✓（客户端 + 服务端） | ✓ | ✓ | ✗（Absent） | ✗ | ✗ | ✗ |
| 自托管/API | 文档化 HTTP API | partial：路由冻结 F-028 accepted；`/docs` F-041 **unknown** | ? | ? | ? | ? | partial（`paper` CLI `--json`） | ✗ | ✗ | ✗ |

---

## 4. 差距分析

沿用 Paper 账本 Parts 2–3 的三桶。「谁有」一列只列附录里有据可查的产品。

### 4.1 Table stakes：我们缺、而几乎人人都有的

| # | 缺口 | 我方账本 | 谁有 |
|---|---|---|---|
| T-1 | 应用内导入书（上传/拖放） | F-034 stub | paper-one（文件夹、拖放）；BookLore（BookDrop）、Calibre-Web-Automated（自动入库）；附录 (c)12 记「应用内上传很常见」 |
| T-2 | 在应用里删书 | F-035 absent | paper-one（回收站 + 撤销）；附录 (c)12 把它与导入并列为开放项 |
| T-3 | 阅读主题 / 字体真的能用 | F-031、F-032 stub | paper-one（5 主题 + 跟随系统、字体选择、约 40 行排版项） |
| T-4 | 点按/手势翻页 | F-033 stub | paper-one（手势/滚轮翻页、webhost 浏览器端点按翻页） |
| T-5 | 高亮/批注可靠锚定 | F-018 partial（CFI 恒 null，#6–#8） | paper-one（CFI 锚定 + 无法放置的标注重新锚定）；Readest、Koodo、KOReader、Kavita、Kindle、WeRead 均 ✓ 批注 |
| T-6 | 笔记导出到 Markdown / PKM | 无行 | Koodo（CSV/MD，Readwise/Notion/Anki）、KOReader（Markdown）、paper-one（JSON/MD）、Readwise Reader（Obsidian/Notion）、taylorren/ai-reader（Markdown） |
| T-7 | PDF | F-038 stub | 矩阵里除 karpathy/reader3、bilingual_book_maker、taylorren、Dedao 外几乎全部 ✓ |
| T-8 | 多设备 / 同步 | 无行 | Readest、Koodo、KOReader、Kavita、Komga、CWA、BookLore、paper-one，全部商业产品 |
| T-9 | 书库备份 / 导出 | F-036 stub | Koodo（备份）、paper-one（标签/标注/卡片导出导入） |

> T-7 / T-8 虽是 table stakes，但与定位（EPUB、单用户本机）或 ADR-0001 冲突，§5 把它们放进 Won't 并给理由——「人人都有」不等于「我们该有」。

### 4.2 Contested / optional：真实但不普及的

| # | 能力 | 谁有 | 对我们的判断 |
|---|---|---|---|
| C-a | TTS 朗读 | Readest（多语言 + EPUB3 Media Overlays）、Thorium、Koodo、Moon+、Readwise、paper-one；Gemini Notebook / Open Notebook 做音频概览 | 浏览器原生语音可低成本做；神经语音不做 |
| C-b | OPDS | Calibre-Web、Kavita、Komga、CWA、BookLore、Koodo、Readest、Thorium、KOReader | 对「单用户本机」价值有限，但作为只读服务端能让 KOReader 取书 |
| C-c | 划词 AI（释义/简化/翻译） | Koodo、assistant.koplugin、WeRead、Readwise Ghostreader；paper-one 曾有 gloss 后移除 | Paper 的移除理由是反证；我们已有 Ask AI 入口，只做薄的一层 |
| C-d | X-Ray 实体抽取（人物/时间线/关系） | Kindle（经典 X-Ray）、Readest（WIP，PR #3119） | 成本高、效果依赖长上下文；本轮不做 |
| C-e | 整书 AI 翻译 / 双语 | bilingual_book_maker（9.8k★）、Readest（DeepL/Yandex）、Koodo | 已有成熟独立工具，不是阅读器的事 |
| C-f | 规则/智能书架、元数据补全、系列 | CWA Magic Shelves、BookLore、paper-one | Calibre 的地盘 |
| C-g | 多用户账户 | Kavita、Komga、Calibre-Web、BookLore | 违背单用户定位与 ADR-0001 |
| C-h | 双书并排阅读 | Readest | 小众 |
| C-i | 网页剪藏 / 稍后读 | Readest、Readwise Reader | 另一个产品 |
| C-j | 阅读统计 | paper-one 账本把它列为 Absent 且「table stakes missing」 | 我方 F-007 是书库统计，不是阅读时长；便宜可做 |
| C-k | 书签、脚注弹窗、跳转后返回 | paper-one | 便宜的阅读体验项 |

### 4.3 我们的差异化：要守住的

依据：附录 (c) 末尾「Where we are still differentiated」，以及 paper-one 附录 §4「What we have that Paper lacks」。

| # | 差异化 | 账本 | 为什么是护城河 | 具体缺口（→ §5） |
|---|---|---|---|---|
| D-1 | 5 家一等 provider（含 Anthropic、Gemini、OpenRouter）+ 单出口出网闸 | F-014、F-024 accepted | Readest 只有 Ollama + AI Gateway 且云优先；Paper 以「provider 无法统一」为由整体移除 AI——我们已经把这件事做成了 | 流式路径无重试（#36，F-014 Limits）——本轮不单列 |
| D-2 | 书内 RAG 问答 + 摘要，token 预算路由 | F-013 accepted | Kindle、WeRead、Readwise、Readest 都证明「书内问答」是这个品类的核心 | **防剧透**（Readest、Kindle、Readwise 有）；**引用回跳**（Readwise、WeRead、Readest X-Ray、Gemini Notebook 有）；**未建索引的书问不了自然语言问题**（#26，F-013 Limits） |
| D-3 | 每书多线程会话 + 导出（json/text/md） | F-016 accepted | 附录认定「在阅读器里我们是唯一同时具备……的自托管产品」之一 | 无 |
| D-4 | 书库级对话 | F-017 accepted（单书）；F-039 stub | 同上 | 全库/收藏范围只是占位 |
| D-5 | 用户可见的混合检索（关键词 + 语义），变音符归一 | F-011、F-012 accepted | Readest 的向量索引只服务 AI 对话；Paper 的全库检索是关键词倒排（推断） | 无（#35 性能债归 012） |
| D-6 | 自托管 Python 后端 + 冻结 API + 安全边界 + 崩溃安全发布 | F-003、F-023–F-028 | Paper 无对应的 HTTP API；Python ML 栈是 ADR-0008 的立足点 | `/docs` 行为未测（F-041） |

---

## 5. MoSCoW

**工作量刻度**：S ≈ 1 个单位（一个 WI 以内）、M ≈ 3（几个 WI）、L ≈ 8（一个分支级工作）。
**分桶判据**：
- **Must**：缺了它，产品是坏的或不可信的。具体说就是三类：可见的控件点了没反应；核心流程（导入 → 读 → 问）走不通；数据只能靠手删目录来管理。
- **Should**：高价值、有竞品证据、成本可控，而且多数已经挂在现有里程碑上。守护差异化的具体缺口也归这一档。
- **Could**：有需求、便宜或可选，排在 Should 之后。
- **Won't（本轮）**：明确不做，逐条写理由。

F-031..F-040 每行都已归入某一桶，见 §5.5 的对照表。

### 5.1 Must（6 项）

| ID | 能力 | 理由（定位价值 · 竞品证据） | 工作量 | 映射 | 依赖与风险 |
|---|---|---|---|---|---|
| **M-1** | 应用内导入 EPUB（文件选择 + 拖放 + 上传路由） | 书库页顶栏的「+ Add books」今天只弹一个「去跑 CLI」的对话框。一个以书库为首页的产品没有导入，会让人觉得不可信。· paper-one、BookLore、CWA 有；附录 (c)12 记「应用内上传很常见」 | M | **F-034** stub · debt **#57** · **012** 末波 Wave D | 验收要求按新格式落盘（ADR-0009），并走 ADR-0007 发布协议；012 仍被 soak 挡着。上传要受 F-023 origin guard 保护，上传的文件也要做路径安全校验（ADR-0012） |
| **M-2** | 应用内删书 | 今天删书只能手删 `books/{id}_data/`。· paper-one 有回收站 + 撤销 | S | **F-035** absent · debt **#58** · **018** WI-5（前端半条 FB-L18） | 依赖 018 WI-2 每书写锁（ADR-0015 Proposed）。必须让 `load_book_cached` 的缓存失效，否则删掉的书还能读到。回收站/撤销不在 #58 范围内，见 §7 Q6 |
| **M-3** | 阅读纸色主题 + 字体选择真正生效 | 阅读设置面板 12 个控件里 8 个是纯装饰（4 主题 + 4 字体，spec D1），点了都没反应，而且就在阅读器最常用的面板上。· paper-one 有 5 主题 + 字体 | M | **F-031** stub（#21）、**F-032** stub（spec D1）· **014** WI-18 | WI-18 定义为二选一字体（三款商用字体无授权）。localStorage 老 key 必须迁移（FB-R13 / FB-R13a）。F-031 的测试在 `tests/e2e/baseline_1b/`，**改动它会清零 soak**，所以必须等 012 开工之后才能动，而 014 本来就排在 012 之后 |
| **M-4** | 点按翻页区（左右页边） | 触屏或局域网平板上只能用键盘翻页，等于不能读。· paper-one 有 webhost 点按翻页和手势翻页 | S | **F-033** stub · debt **#11** · **014** WI-17 | #11 的裁定写的是「要么绑定、要么连 testid 一起删」，本文建议**绑定**。WI-17 本身在修三个翻页缺陷，点按翻页区要和翻页锁一起做。断言它「从不被使用」的用例在 `baseline_1b`，所以同样要等 soak 结束 |
| **M-5** | 零死表面：把不做的占位删掉 | 账本规则写明「stub 不是 feature」；spec 裁定「不做的不占位」（`spec-frontend-design.md` 书库右栏一行：Chat 的 `All books` / `Collection` → 删掉）。**它和 M-3、M-4 的区别**：那两条是把控件做通，这一条是把本轮不做的控件删掉 | S | **F-039** 删除占位（spec 已裁定）· **F-040** 删除「点评此书」按钮（本轮不做，重建见 C-5）· **F-038** 删除侧栏 PDF 类型按钮（PDF 为 W-4）· 书库侧属 013 遗留，阅读器侧属 **014** WI-16 外壳重写 | F-038 的 `scope=format:pdf` 属于冻结 API（ADR-0011），**只删 UI，不删 API 取值**。F-038 的用例在 `baseline_1b`，要等 soak 结束。删 testid 会让 `lint_testid_naming.py` 的计数变化（ADR-0013） |
| **M-6** | 「导入即可问」：没建索引的书也能回答自然语言问题 | 核心流程是导入 → 读 → 问，现在断在最后一步。没跑 `--index` 的书，任何自然语言提问都返回 400「没建索引」（F-013 Limits #26）。M-1 落地后，每本新导入的书都会先撞上这个问题。· 竞品把书内问答当作核心：Kindle、WeRead、Readwise、Readest | S | **F-013** Limits · debt **#26**（兑付方原写 011，011 已合入，但 #26 仍「未结清」）· 可选的另一半：导入后自动建索引，复用 F-002 / F-008 | 改法已写在 #26 行里：先分词，任一关键词命中就走回退，至少也要把文案改成可操作的。**#26 目前没有兑付方**（见 §7 Q4）。导入后自动建索引依赖 optional `semantic` extra，没装时必须优雅降级 |

**Must 小计：** M+S+M+S+S+S = 3+1+3+1+1+1 = **10 单位**

### 5.2 Should（7 项）

| ID | 能力 | 理由（定位价值 · 竞品证据） | 工作量 | 映射 | 依赖与风险 |
|---|---|---|---|---|---|
| **S-1** | **防剧透问答**：检索与上下文默认只限已读位置，可切换为「全书」 | 这是守护差异化 D-2 的第一个缺口。和 LLM 一起读小说时，全书检索会直接剧透。· Readest 按页过滤上下文（每页约 1,500 字符）；Kindle Ask this Book 默认防剧透，带「whole book」开关；Readwise Ghostreader 感知阅读位置 | M | **new**（扩展 F-013 / F-012）| 依赖 **014 WI-19「进度单一真相源」**，前端要能可靠给出当前位置。后端改动是按章节序号过滤检索，外加一个请求字段，属于 ADR-0011 允许的「只许新增」，要走 `routes.snapshot` 新增流程。风险一：token 预算路由（full_book / multi_chapter / rag）三条路径都要截断，漏一条就会剧透。风险二：切换开关的默认值是产品决定（§7 Q5）。**需在 §9 分配编号** |
| **S-2** | **引用回跳**：回答附出处片段，点一下跳回书中原文 | 这是守护差异化 D-2 的第二个缺口，也是可信度问题：RAG 答案要能被核对。· Readwise Ghostreader、WeRead AI问书（带引用与追问）、Readest X-Ray（WIP，可跳证据）、Gemini Notebook（带引用） | M | **new**（扩展 F-013）；跳转复用 F-011 的深链 `?q=&occurrence=` | 代码观察（非账本事实）：`src/reader3_app/web/routers/ai/chat.py` 的 SSE 载荷里已经有 `retrieval_sources`，所以主要工作量可能在前端。账本没有记录任何引用行为，所以这一条算 new。依赖 014 WI-16 阅读器外壳。跳转走 F-011 深链（纯文本定位），预计不受 F-018 的 CFI 缺口（#6）影响，但开工前要核实。**需在 §9 分配编号**（也可以和 S-1 同一分支） |
| **S-3** | 笔记 / 高亮导出（Markdown + JSON） | 「读完拿走」是给 LLM 和 PKM 用的出口，也最贴合定位：会话已经能导出（F-016），笔记却不能。· Koodo、KOReader、paper-one、Readwise Reader、taylorren/ai-reader | S | **new**（扩展 F-018）；现有「复制全部笔记」（F-040 Confirm）可复用 | 导出是新增的读路由，不改已有形状。和 F-036 书库导出（#53）的格式要对齐，别做出两套 JSON。**需在 §9 分配编号**，也可以并入 014 的笔记面板工作，但那样属于 014 范围变更 |
| **S-4** | 批注可靠锚定（修 CFI 恒 null） | F-018 仍是 partial，主要缺口就在这里：纯文本锚定遇到重复句子会锚错。· paper-one 用 CFI 锚定并能重新锚定；Readest、Koodo、KOReader、Kavita、Kindle、WeRead 都有批注 | M | **F-018** Limits · debt **#6–#8**（#8 已改派 011/014）· **014** WI-14（`annotations.js` 拆分） | ADR-0005 定的是「引文 + 前后文，CFI 可选优先」，这一条是让 CFI 真正写进去，不是改锚定策略。补 CFI 分支的用例会改动 `EXPECTED_BASELINE_ITEMS`，也就动了冻结集，必须等 soak 结束 |
| **S-5** | 书库 JSON 导出 / 备份 | 自托管用户需要能带走自己的数据，而且「导出书库 JSON」按钮已经在界面上了。· Koodo 有备份；paper-one 能导出/导入标签、标注、卡片 | S | **F-036** stub · debt **#53** · **018** WI-6 | 导出内容取决于存储格式（ADR-0009）。018 先出的版本要么限定字段，要么在 012 后升级，018 任务书需明确这一点。要和 S-3 的格式对齐 |
| **S-6** | 批量重建全部索引 | 设置页的按钮已经存在；换机或升级后，逐本跑 CLI 不现实。本条是 M-6「导入即可问」在运维侧的补充 | S | **F-037** stub · debt **#52** · **012** 末波 Wave D | 需要 generation swap（012 独有的依赖）。长任务要有进度，可复用 F-022 的降级组件 |
| **S-7** | PWA + `reader3 launch` | 用 ADR-0008 选定的方式拿到「像 app 一样」的体验：独立窗口、可安装、离线出壳，不做桌面壳。· Readest、Koodo、KOReader 与所有商业产品都有原生或多设备客户端 | M | **015** 前端 WI-20（PWA）+ 015 CLI 侧（`reader3 launch`，任务文件尚未写） | WI-20 的缓存白名单契约是隐私边界：`/api/**` 和书籍正文一律不进缓存。PWA 的 `manifest.json` 与存储格式的 manifest 同名但不是一回事，要区分。这一条**不是**同步，也不是原生 app（见 W-1、W-3） |

**Should 小计：** 3+3+1+3+1+1+3 = **15 单位**

### 5.3 Could（8 项）

| ID | 能力 | 理由 · 竞品证据 | 工作量 | 映射 | 依赖与风险 |
|---|---|---|---|---|---|
| **C-1** | 书库级跨书 / 收藏范围对话 | 把差异化 D-4 做完整。全库语义检索路由已经存在（F-012 `GET /api/search/library`），可以复用。· Open Notebook、Gemini Notebook 都是多来源问答 | M | **F-039**（M-5 先删占位，本条做成后再按真实功能加回）· **new** | 按书分库（ADR-0004：一书一库）意味着要对 N 个 ChromaDB 分别查询再合并；#35 全库搜索的性能债（归 012）必须先还。会话存储在哪里（按书还是项目根，ADR-0003）需要先定。**需在 §9 分配编号** |
| **C-2** | 划词 AI 预设动作（释义 / 简化 / 翻译） | 工具栏已经有 Ask AI 入口，加几个预设 prompt 成本很低。· Koodo、assistant.koplugin、WeRead 长按问、Readwise Ghostreader 有。**反证**：paper-one 做过 gloss / Look up，最后删掉了，理由是「useful things … very small」 | S | **new**（扩展 F-018 工具栏 / F-013） | 只做预设 prompt，不做弹窗词典，也不做本地模型。要走 F-015 的队列与预算 |
| **C-3** | 浏览器原生 TTS 朗读（Web Speech） | 零依赖就能补上 contested 项 C-a。· Readest、Thorium、Koodo、Moon+、Readwise、paper-one 有 | M | **new** | 要高亮正在读的词，就得碰 iframe 内部 DOM，这和 ADR-0002「永不触碰 iframe 内部 DOM」冲突，所以只能做不带跟读高亮的版本，或者经 epub.js API 实现。神经语音列入 W-8 |
| **C-4** | OPDS 只读服务端（catalog feed） | 让 KOReader、Koodo、Thorium 这类客户端能从我们的书库拿书，成本是一组只读路由。· Calibre-Web、Kavita、Komga、CWA、BookLore、Koodo、Readest、Thorium、KOReader 都有 OPDS | M | **new** | 是新增路由，要进 snapshot。F-023 的 token 机制，OPDS 客户端未必支持，需要评估。**不做** OPDS 客户端（从外部拉书） |
| **C-5** | 「点评此书」重建为：基于我的笔记生成 AI 书评 | 把一个死按钮变成 D-2 与 S-3 的交汇点：笔记 + LLM。· Glasp 有「基于高亮的 AI 摘要」 | S | **F-040**（M-5 先删按钮，本条做成后再加回）· **new** | 依赖 S-3 的笔记导出格式 |
| **C-6** | 书签 + 跳转后返回 + 脚注弹窗 | 便宜的阅读体验项。· paper-one 有书签、⌘[ / ⌘] 跳转后返回、脚注弹窗 | S | **new**（扩展 F-009） | 脚注弹窗涉及 iframe 内容，受 ADR-0002 约束。书签存储要按 ADR-0001 走文件 |
| **C-7** | 阅读统计（阅读时长 / 进度） | paper-one 账本把它列为 table stakes missing；我们的 F-007 是书库统计，不算阅读统计 | S | **new**（扩展 F-007） | 依赖 014 WI-19 的进度单一真相源 |
| **C-8** | `/docs` 交互式 API 文档：测过或关掉 | F-041 是 unknown：页面资源来自 CDN，离线不可用，而且有 token 时浏览器进不去 | S | **F-041** unknown · **new** | 如果选择关掉 `/docs`，会从 `routes.snapshot` 里删路由，ADR-0011 不允许删，需要裁定。只补一条行为测试的话，可以把它升级为 accepted |

**Could 小计：** 3+1+3+3+1+1+1+1 = **14 单位**

**工作量占比：** Must 10 + Should 15 = **25 / 39 ≈ 64%**（Could 14 ≈ 36%）。符合「约 60% 在 Must + Should、Must 保持小」的目标（Must 占 26%）。

### 5.4 Won't（本轮）

| ID | 不做 | 理由 | 竞品证据 / 约束 |
|---|---|---|---|
| **W-1** | 原生移动 / 桌面 app（iOS、Android、Electron、Tauri） | ADR-0008 已裁定不做桌面壳；桌面化用 S-7 的 PWA + `reader3 launch` 覆盖。Python ML 栈约 1.1 GB，任何打包都绕不开这个体积 | Readest、paper-one 走 Tauri；Koodo、KOReader 与商业产品都有原生客户端；ADR-0008 Revisit When 第 1 条 |
| **W-2** | 社交层 / 圈子 / 公开发布 | 违背「单用户本机」定位。这类能力的工程量要看 Paper 的 circle / public 两个 capability（签名、密封页、iroh-blobs、DHT），而它们连 Paper 自己都还是 Partial | paper-one circle / public；WeRead 的社交批注 |
| **W-3** | 同步（P2P、云盘、KOReader/Kobo 进度同步）与多用户账户 | ADR-0001 Revisit When 第 1 条明写：「出现多用户或跨设备同步需求」就要重新评估文件系统方案。本轮不触发这条重评；局域网浏览器访问已能覆盖「换个设备读」 | paper-one P2P；Koodo（OneDrive/Google Drive/WebDAV）；Komga、CWA、BookLore（Kobo/KOReader）；Kavita、Komga、Calibre-Web、BookLore（多用户） |
| **W-4** | PDF（**F-038**） | 定位是 EPUB 阅读器。PDF 需要第二个渲染器（pdf.js）、第二条摄取与文本抽取管线，批注锚定模型也不同，属于 L 级工作，而且会把阅读器最脆弱的部分（ADR-0002）翻倍。M-5 先删掉占位 UI，冻结 API 里的 `scope=format:pdf` 保留，照常返回 0 | 矩阵中几乎所有阅读器都支持 PDF，它是 table stakes（T-7）。**这是本文最有争议的一条 Won't**，见 §7 Q1 |
| **W-5** | MOBI / AZW3 / FB2 / CBZ / 漫画 | 同 W-4，而且离「和 LLM 读书」更远；用户可以用 calibre 转成 EPUB 后再导入 | Readest、Koodo、KOReader、paper-one；Kavita、Komga（漫画） |
| **W-6** | 复制 Calibre 的书库管理（元数据补全、封面抓取、系列、标签体系、规则/智能书架、文件夹监听自动入库、邮件 send-to-eReader） | 定位明确不做 Calibre。收藏夹（F-006）已经够用 | CWA Magic Shelves、BookLore 智能书架与 BookDrop、Calibre-Web send-to-eReader、paper-one 元数据补全/系列/标签 |
| **W-7** | 整书 AI 翻译 / 双语 EPUB 生成 | 这是批处理工具的活，token 成本高；已经有 9.8k★ 的成熟 CLI | bilingual_book_maker；Readest（DeepL/Yandex）；Koodo |
| **W-8** | 神经语音 / 音频概览 / 播客 | 模型下载和推理超出「轻量」的范围；C-3 的浏览器 TTS 已经够用 | paper-one Kokoro 82M；Gemini Notebook、Open Notebook 音频概览 |
| **W-9** | X-Ray 实体抽取 | L 级工作，效果依赖长上下文，连 Readest 都还是 WIP；S-1、S-2 两个更基础的缺口要先补 | Kindle 经典 X-Ray；Readest PR #3119 WIP |
| **W-10** | 内置本地推理（打包 llama-server 或 on-device 模型） | Ollama provider（F-014）已经覆盖本地模型。Paper 删掉本地推理的经验说明这是高维护、低回报的投入 | paper-one 2026-09-19 移除 `llama-server` 与 `tauri-plugin-inference` |
| **W-11** | 深度排版（x-height 校正、fidelity dial、CJK–Latin 间距等约 40 项） | M-3（WI-18：纸色、字号、行距、字体四个控件）之外不再扩展 | paper-one 约 40 行排版项 |
| **W-12** | 双书并排阅读、网页剪藏 / 稍后读 | 小众，或者属于另一个产品 | Readest；Readwise Reader |
| **W-13** | 换嵌入模型 / 向量库（例如为了追 BM25+向量 做重写） | ADR-0004：换模型就要全量重建，所以不换。我们已经有用户可见的混合检索（F-012） | Readest 混合 RAG |

### 5.5 F-031..F-040 落桶对照

| F-ID | 名称 | 账本状态 | 落桶 |
|---|---|---|---|
| F-031 | Reader paper themes | stub | **M-3** |
| F-032 | Reader font-family picker | stub | **M-3** |
| F-033 | Page-turn click zones | stub | **M-4** |
| F-034 | In-app book import | stub | **M-1** |
| F-035 | Book delete | absent | **M-2** |
| F-036 | Library JSON export | stub | **S-5** |
| F-037 | Bulk re-index all books | stub | **S-6** |
| F-038 | PDF format scope | stub | 能力 **W-4**；占位 UI 在 **M-5** 删除 |
| F-039 | Library chat all-books / collection scope | stub | 占位 **M-5** 删除；能力 **C-1** |
| F-040 | Notes「点评此书」 | stub | 按钮 **M-5** 删除；能力 **C-5** |
| （附）F-041 | Interactive API docs | unknown | **C-8** |

---

## 6. 建议的执行顺序

执行顺序的唯一定义处是 [进度盘 §2](../20260824-frontend-backend-plan-progress.md)，现行顺序是 **018 → 012 → 014 → 015**（013 已合入；012 与 014 严格串行）。下表只把 Must / Should **挂到**这条既有顺序上，不改顺序、不分配编号。

| 顺位（进度盘） | 分支 | 挂上去的条目 | 是否在该分支现有范围内 |
|---|---|---|---|
| 3.8 | `018-library-routes`（soak 等待期内做，不等 soak） | **M-2**（#58，WI-5）、**S-5**（#53，WI-6） | ✅ 已在 018 任务书内 |
| 3.8 附议 | 同上或另开 | **M-6**（#26：分词回退 + 可操作文案） | ❌ 不在 018 范围内。#26 只改 `ai/rag.py`，不依赖存储格式，技术上可以在 soak 期间做。可选的路子：由维护者裁定并入 018，这是范围变更，需要改 018 任务书；或者**需在 §9 分配编号**另开一条小分支 |
| 4 | `012-storage-format`（仍被 soak 挡着） | **M-1**（#57，末波 Wave D）、**S-6**（#52，末波 Wave D）；M-6 的「导入后自动建索引」一半建议并入 M-1 的验收 | M-1、S-6 ✅ 在 012 范围内；「导入后自动建索引」❌ 不在，需要改 012 任务书 |
| 6 | `014-ts-frontend-reader` | **M-3**（WI-18）、**M-4**（WI-17 + #11）、**M-5**（阅读器侧的 F-040 删除走 WI-16 外壳重写；书库侧的 F-039、F-038 按钮删除见下一行）、**S-4**（WI-14 + #6–#8） | M-3、M-4、S-4 ✅ 在 014 范围内。M-5 书库侧 ❌：spec 已裁定删除 F-039 的占位，但 013 合入时它仍在，建议并入 014 WI-16b「书库侧延后验收」，这是范围变更 |
| 7 | `015-launch-experience` | **S-7**（WI-20 PWA + `reader3 launch`） | ✅ 在 015 范围内。015 的 CLI 侧任务文件还没写，要按「领先一个分支即时补」的规则来 |
| 015 之后 | 新分支 | **S-1**（防剧透）、**S-2**（引用回跳）、**S-3**（笔记导出） | ❌ **需在 §9 分配编号**。S-1 与 S-2 同属 D-2，建议放一个分支。S-1 必须等 014 WI-19（进度单一真相源），S-2 必须等 014 WI-16。S-3 不依赖 015，可以在 014 合入后插在 015 之前，顺序由进度盘裁定 |

**两条贯穿全表的硬约束：**
1. **冻结集与 soak**。M-3、M-4、M-5 的 PDF 按钮删除、S-4 都会改动 `tests/e2e/baseline_1b/**` 下的用例。改一个字节，soak 计数就清零。所以这些条目只能在 012 开工之后做（soak 已经达标）。好在它们都挂在 014 上，而 014 本来就排在 012 之后，所以不需要调整顺序。018 与 M-6 要跑在 soak 期内，**必须保证冻结集 8 条路径零改动**。
2. **API 冻结（ADR-0011）**。M-1、M-2、S-1、S-3、S-5、S-6、C-4 都是**新增**路由或新增字段，都要走 `routes.snapshot` 的新增流程。任何「删路由」的做法（例如 C-8 关掉 `/docs`、M-5 去掉 `scope=format:pdf`）都不允许，除非另有裁定。

**被采纳之后**：条目在它挂靠的分支合入、lane 全绿后，才按账本规则更新对应的 F 行（stub → accepted 就地改级，new 追加新 F-NNN）。本文不预写任何账本行。

---

## 7. 未决问题

1. **PDF 放 Won't（W-4）还是 Could？** 这是本文最有争议的一条。竞品证据几乎一边倒，PDF 是 table stakes；但对「EPUB + LLM」的定位来说，它是 L 级工作，还要引入第二个渲染器。如果改判为 Could，M-5 就不该删 PDF 侧栏按钮。
2. **F-039 与 F-040 先删再建，维护者是否同意？** spec 已经裁定删掉 F-039 的占位，F-040 没有裁定。本文的建议是：两者都在 M-5 删掉，能力分别放进 C-1、C-5，做成以后再加回。
3. **M-3 是否该整体进 Must？** 本文的判断是：阅读器面板上点了没反应的主题和字体控件，会直接损害可信度。如果维护者认为「删掉占位」就足够（也就是走 #21「wire them or drop the testids」里 drop 的那一支），M-3 可以降为 S，把主题做通则挪到 Should。
4. **#26 的兑付方。** 009 债表把它的兑付方写作 011，011 已经合入，但 #26 仍「未结清」。它应该并入 018（范围变更）、012，还是**在 §9 分配新编号**？这个问题决定 M-6 能不能在 soak 期间落地。
5. **防剧透（S-1）默认开还是关？** Kindle 默认防剧透、带「whole book」开关。非虚构类书籍用户往往想要全书上下文。可选方案：按书设置、按提问切换，或者按体裁给默认值。
6. **M-2 删书要不要带回收站 / 撤销？** paper-one 有；#58 的验收只要求「删除后 404、缓存不掩盖」。回收站会引入 `books/.trash/` 这样的新目录约定，属于 ADR-0001 的范围，是否值得？
7. **Paper 移除 AI 的教训怎么吸收？** Paper 的结论是「在阅读器里用模型能做的有用事情很少」。本文的回应是只加深 D-2（防剧透、引用），不铺开划词类功能（C-2 只做预设 prompt，W-9、W-10 不做）。维护者是否认同这个「窄而深」的取向？
8. **S-2 是不是真的主要是前端工作？** 这取决于一条代码观察：`chat.py` 的 SSE 载荷里已经有 `retrieval_sources`。前端现在有没有丢弃这个字段、片段里有没有足够的定位信息（章节序号 + 引文），**都没有核实**。开工前应该跑一次 probe 再定工作量。
9. **工作量刻度（S=1 / M=3 / L=8）是否认可？** 64% 这个占比对刻度很敏感。比如 M-1 如果实际是 L，Must+Should 的占比会升到约 70%。
10. **竞品矩阵要不要长期维护？** Paper 把它放在账本里，我们的账本明确不收。如果需要定期复查（例如每个里程碑合入时），应该约定它放在哪里、多久刷新一次；本文和附录只是 2026-09-27 的快照。
