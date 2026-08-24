# 007-hygiene-and-contracts —— 任务

- **对应阶段**: Phase 0（合同与止血）
- **进入条件**: 无。这是整个迁移的第一个分支
- **退出条件**: 两个 P0 修复并人工 smoke；`--port` 与 `/api/health` 可用；testid 在原型与模板两侧一致且两条 lint 在 CI 里生效（违规数归零）。见 `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` §7
- **下游**: 0.3 与 0.5 阻塞 Phase 1b（009）；0.7 收敛 `book_store` 的合并范围，阻塞 Phase 2a；整个 Phase 0 阻塞其余一切
- **跨计划**: **0.4 / 0.5 / 0.8 三项的产物是[前端计划](../../20260817-frontend-ui-refactor/README.md)的前置契约**——0.4 的 `escapeHtml` 收敛决定 4A.3 `escape.ts` 的形状，0.5 的 canonical 正则与两条 lint 是前端全部测试矩阵的选择器基础，0.8 的 token 悬空 lint 是 DEG-S1–DEG-S5 横幅不静默失色的保证。三项**在本分支实施**，前端计划只引用不重述
- **节奏**: 每项独立 PR，目标一周内合完

> **引用规则**：用**符号名**定位，不写代码行号。

---

## 0. 这个分支不是一次 `/tdd-guardian:workflow` 能跑完的

七项里**只有两项是 test-first 形状**。其余五项要么产物不是代码（lint 配置、打包元数据），要么验收方式不是断言（人工 smoke、装出来能跑）。

| 项 | 走 workflow | 为什么 |
|---|:--:|---|
| **0.1** `process_epub()` 的 `rmtree` 删掉用户标注 | ✅ | 数据丢失 bug，红→绿边界干净，纯 Python |
| **0.3** `--port` / `READER3_PORT` ＋ `GET /api/health` | ✅ | 参数优先级 + 路由契约，两类断言都直接 |
| 0.2 wheel 打包漏 `static/js` | ❌ | 验收是「`uv build` 解包后文件在不在」，属打包脚本，不是单测 |
| 0.4 四个 JS 文件 IIFE 化 | ❌ | 没有 JS 测试宿主（要到 013 才有）。护栏靠人工 smoke |
| 0.5 testid 定名 ＋ 两条 lint | ❌ | 产物是 lint 规则本身。它的「测试」就是违规计数从 138 归零 |
| 0.8 token 悬空引用 lint | ❌ | 同上，产物是 lint 本身。「测试」是差集为 0 |
| 0.6 事实性修复 | ❌ | 改常量与示例配置 |
| 0.7 删死代码 | ❌ | 删除动作。护栏是 0.1/0.3 的测试与人工 smoke |

**别把 ❌ 的项塞进 workflow。** `tdd-planner` 会尽职地为「改 `pyproject.toml` 的 glob」设计测试矩阵，然后 `design-tests` 的 wiring-only 门槛把它挡下来，你白跑两个 stage。

具体的 workflow 输入见 §9。

---

## 1. 现状（2026-08-16 实测）

已经做完的，不要重做：

| 项 | 状态 |
|---|---|
| 0.6 的 `.gitignore` 合并冲突标记 | ✅ 已修（commit `6080928`） |
| 0.7 删死代码 `SearchIndex` / `BookIndex.from_book_pkl` / `SearchIndex.build_from_library` | ✅ 已删。`BookIndex` / `ChapterIndex` dataclass 仍在 `search_service.py`，**是活代码，不要动** |
| spec-kit 退场、规划文档合并进本文件夹 | ✅ |

**全部八项已完成**（0.1 / 0.3 / 0.4 / 0.5 / 0.7 / 0.8 见各节的 ✅；0.2 与 0.6 于 2026-08-23 收尾），**六项人工 smoke 已走完**（§8.1）。

### ✅ 合入记录（本文是这条事实的唯一定义处）

**007 已于 2026-08-24 合入 `master`，Phase 0 关闭。** 别处提到「007 是否在主干上」一律链回这一节，不要重述数字。

| 事实 | 值 | 复核命令 |
|---|---|---|
| PR | [#18](https://github.com/anzchy/reader3-pro/pull/18)，31 commits / 162 files / +16419 −4529 | `gh pr view 18` |
| 合并 commit | `3f63135`（`Merge pull request #18 from anzchy:007-hygiene-and-contracts`） | `git log --oneline -1 master` |
| 分支领先量 | **0** —— 分支上的东西一件不落全在主干 | `git rev-list --count master..007-hygiene-and-contracts` |
| CI 首次实跑 | run `32679593647`，`workflow_dispatch` on `master`，**全绿**（契约 lint 7s / wheel 44s） | `gh run view 32679593647` |

> **CI 那一行不是锦上添花，是这次合入真正解锁的东西。** `workflow_dispatch` 只对**默认分支上存在的 workflow** 生效，而合入之前 `master` 上一个 workflow 文件都没有——也就是说，「CI 改成仅发版触发、日常靠手点补偿」这套安排，在 007 合入之前**根本点不动**，补偿措施是张空头支票。run `32679593647` 是它第一次真的能跑，也是三条契约 lint 与 wheel 打包第一次在主干上被验过。
>
> 分支 `007-hygiene-and-contracts` 合入后**保留未删**（001–006 同样都还在远端），删不删随后再定。

> ⚠️ **本行此前写着「0.3 已完成」，是错的。** 实测 `src/reader3_app/web/server.py` 里
> 既没有 `READER3_PORT`、没有 `--port`，也没有 `/api/health`——`main()` 仍是写死的
> `uvicorn.run(app, host="127.0.0.1", port=8123)`。2026-08-23 才真正实现。
> 记账错误本身值得留一行：**"已完成"这四个字没有护栏，写错了没有任何东西会报警**，
> 这正是 008 要建测试网、而不是继续靠文档记账的理由。

---

## 0.1 P0-1：重新处理一本书会静默删光该书全部用户标注

**症状**：`reader3.py` 的 `process_epub()` 在写入任何内容之前对 `output_dir`（即 `books/{name}_data/`）调 `shutil.rmtree()`。用户产生的数据和再生成的产物**住在同一个目录里**：

| 会被删掉，且不可再生 | 可以再生 |
|---|---|
| `notes.json`（全部标注） | `book.pkl` |
| `ai_meta.json`（book_uuid，会话追踪靠它） | `book.epub` |
| `ai_conversations/` | `images/` |
| `chroma_db/`（重建要跑一遍 embedding） | |

无警告、无备份。`ai_meta.json` 被删的后果比看上去重：`book_uuid` 变了，历史会话就和这本书断开了。

**修法**：staging 目录 + 完整校验 + 原子切换。**顺序照 Phase 3 的「两文件提交协议」**——那是唯一定义处（`plan-tech-stack-migration.md` Phase 3），本文不复述。staging 目录必须和目标同父目录，否则 `os.replace` 跨文件系统不原子。

**测试目标**（`tests/unit/`）：

- 目录里已有 `notes.json` / `ai_meta.json` / `ai_conversations/` / `chroma_db/` 时重新处理 → 四者内容逐字节不变
- `book_uuid` 在重新处理前后相同
- `book.pkl` / `book.epub` / `images/` 确实被刷新（别把「保住用户数据」写成「什么都不改」）
- 中途失败（校验不过 / 写一半抛异常）→ 原目录**完全不变**，staging 残留可被下次干净重跑
- 首次处理（目录不存在）仍然正常

> 所有测试用 `tests/conftest.py` 的 `books_dir` fixture。**永远不要让测试指向真实 `books/`**——这个 bug 的本质就是它会删掉那里的东西。conftest 的 docstring 已经写了这条。

**明确不做**：`lru_cache` 失效。三处缓存（`search_service.py` 两处、`web/server.py` 一处）的 key 都不含 mtime，所以重新处理之后服务器还会继续供旧 `Book`。这是**另一个 bug**，和数据丢失叠加但不同源，计划里也没给它派活。

> ⚠️ **未分配**：`lru_cache` 失效目前不在任何里程碑名下。它天然属于 011（`book_store` 三处 loader 合并——那次会同时碰到全部三处缓存）。开 011 的骨架时把它收进去，别让它就这么漂着。

---

## 0.2 P0-2：打出来的 wheel 阅读器不可用

`pyproject.toml` 的 `[tool.setuptools.package-data]` 写的是 `"reader3_app.web" = ["templates/*.html", "static/*"]`。setuptools 的 `*` **不递归**，于是 `static/js/`、`static/css/`、`static/vendor/` 三个子目录一个都没打进去——`epub.min.js`、`annotations.js`、`reader.css` 全部缺失。

本地 `uv run` 走源码树，所以这个问题在开发中永远看不见。

**验收**（这就是它不走 workflow 的原因——验收是一段构建脚本，不是断言）：

```
uv build → 解包 wheel → 断言 templates/、static/js/、static/css/、static/vendor/ 下的文件确实存在
```

把这段做成 CI 的一步（008 建 CI 时接管）。**必须在 Phase 4「dist 提交进 git」之前修**，否则 dist 提交了也发不出去。

✅ 已完成（2026-08-23）。

- **修法**：`package-data` 的 `"static/*"` → `"static/**/*"`（`**` 需 setuptools ≥62.3，`[build-system]` 已要求 ≥68）。修后 wheel 里 css 5 ＋ js 6 ＋ vendor 2 共 13 个子目录文件全部就位，模板与静态资源合计 28 个，缺 0。
- **守卫**：`scripts/check_wheel_contents.py`，接进 `.github/workflows/lint.yml` 的**新 job `wheel`**。它**不进 `contracts` job**——那个 job 的「零依赖、不装任何东西」是刻意保住的性质（让 lint 在还没有 `tests/` 的分支上也能跑），而本检查要 `uv build`。
- **判定不是抽查是对账**：源码树 `web/templates/` 与 `web/static/` 下的每个文件都必须在 wheel 里有对应条目。抽查会在有人新增 `static/img/` 时静默失效。
- ⚠️ **实施中发现的第二个坑，比原 bug 更阴**：本地做过一次成功构建之后，`src/reader3.egg-info/SOURCES.txt` 会列全整棵树；而 `pyproject.toml` 开着 `include-package-data = true`，setuptools 会把 SOURCES.txt 里的文件也算作包数据。于是**把 `package-data` 改回坏的 `static/*`，wheel 依然是完整的**，检查照样绿。`build/lib/` 的残留同理。CI 是干净检出所以看不见——**这个陷阱只在本地咬人，而本地恰恰是改 `pyproject.toml` 的人第一时间验证的地方**。脚本因此在构建前自清这两处。两个方向都已实测：坏配置 exit 1、好配置 exit 0。

---

## 0.3 端口可配置 ＋ 健康探针

`web/server.py` 的 `main()` 里 `uvicorn.run(app, host="127.0.0.1", port=8123)` 是写死的，没有 env 也没有 CLI 覆盖。

这已经造成过实际阻塞：为采集 classic UI 截图，必须绕过 `reader3-server` 入口直接调 uvicorn。对 Phase 1b 的影响更直接——Playwright 要起自己的实例，固定端口会撞开发者本地的 8123，CI 并发跑也会抢端口。

**做什么**：

- `READER3_PORT` env + `--port` CLI，**CLI 优先于 env，env 优先于 8123 默认值**
- 新增 `GET /api/health`，返回一个小 JSON 就绪载荷

`/api/health` 是两行代码，但它是 Phase 1b 的 Playwright `webServer` 就绪探针——没有它只能轮询 HTML 页面，慢且易误判。Phase 5 的 `reader3 launch` 直接复用。

**测试目标**：优先级三种组合（`tests/unit/`）；`/api/health` 的状态码与载荷形状（`tests/contract/`，FastAPI TestClient）。

**明确不做**：Playwright `webServer` 配置本身（属 009）。

✅ 已完成（2026-08-23）。

- `resolve_port(argv, env)` 是个纯函数，优先级 **`--port` > `READER3_PORT` > `DEFAULT_PORT` 8123**；`--port 9000` 与 `--port=9000` 两种写法都收。
- **非法值抛错，不回落默认值**。静默回落会把「你写错了」伪装成「一切正常」——服务照样起来，只是起在 8123 上，然后撞开发者本地那个实例。`main()` 捕获后打一行到 stderr 并 `return 2`。
- `GET /api/health` 返回 `{"status": "ok", "version": "<包版本>"}`，版本走 `importlib.metadata`。**故意不碰磁盘**：不扫 `books/`、不读 settings、不加载任何 `book.pkl`。009 起的实例常跑在空目录里，探针一旦顺手扫书库就会在那里 500，而 `webServer` 只会报「服务没起来」。
- **测试**：`tests/unit/test_resolve_port.py`（三种优先级组合 ＋ 空 env ＋ 六个非法值 ＋ 边界 1/65535）、`tests/contract/test_health_route.py`（状态码、载荷形状、书库目录不存在时仍 200）。18 条，全绿；全量 68 条全绿。
- **实测 smoke**：`READER3_PORT=8199` → 起在 8199；`READER3_PORT=8199 … --port 8200` → 起在 **8200**（CLI 赢）；`/api/health` 实回 `{"status":"ok","version":"1.4.0"}`；`READER3_PORT=abc` → `reader3-server: READER3_PORT 不是整数：'abc'`。

---

## 0.4 四个落后 JS 文件 IIFE 化

`search.js` / `ai.js` / `settings.js` / `library-search.js` 四个文件的顶层函数直接挂在全局。实测**四个文件全都定义了 `escapeHtml`**——谁后加载谁赢，而它们的实现并不等价。这是个正在等着咬人的 XSS 面。

包 IIFE，只导出确实需要跨文件用的符号。参见技术栈计划 B1。

**验收**：人工 smoke 四个页面（library / reader / settings / 跨库搜索）。013 建起前端测试宿主之后补自动化。

✅ 已完成（commit `f11b346`）。

---

## 0.5 testid 定名 ＋ 两条 lint

**顺序是先改原型、后回贴模板**（合流计划 §4.1）。原型侧 138 个 testid 站点，**0 个合规**，全部需要改名。

> 计划里此前写的是 134。差的四个是 `Sheet` 的 `testId=` prop——只 grep `data-testid=` 的口径看不见它们。
> 对账过程见 [`contracts/testid-rename-map.md`](../contracts/testid-rename-map.md) §1；「24 个危险名」那个数没变。

**这是两条不同的 lint，不是一条**——对照表见 `plan-tech-stack-migration.md` §6 步骤 0.5 下方的注。一句话概括：**选择器 lint 约束测试代码，命名 lint 约束模板与原型**。只有前者的话，模板里照样可以新增 `reader-search-hit` 这种名字，命名方案随即失守。

canonical 正则在 `plan-tech-stack-migration.md` §6 的「canonical 正则（唯一真相源）」代码块里。**从那个代码块复制，不要从任何表格里复制**——表格单元格内 `|` 必须转义成 `\|`，复制出去会得到一条永不命中的正则，lint 全绿而命名方案毫无约束。本文不复述那个正则，正是为了不制造第二个复制源。

命名 lint 必须**显式点名设计规格 §4.1 那 24 个带 `reader-` / `library-` 前缀的 testid**：它们形似合规，批量改名时最容易被当成「已经对了」跳过，而正则会把它们判为不合规——正是要的效果。

**验收**：lint 初始状态 138 条违规 → 改完归零，两条 lint 都在 CI 里生效。

✅ 已完成。逐条新旧映射、回贴覆盖清单、以及 `data-modal` / `data-sheet` 判别位的约定，
见 [`contracts/testid-rename-map.md`](../contracts/testid-rename-map.md)。落地结果：原型 221 个唯一
testid 全部合规；现有模板与生成 DOM 回贴了其中 152 个，反向新造为 0；三条 lint 在
`.github/workflows/lint.yml` 里分三步跑，均为 0 违规。

> **2026-08-23：`lint.yml` 改成只在发版时触发**（`release.published` ＋ `v*` tag push ＋
> 手动 `workflow_dispatch`），日常 push 与 PR 都不再跑。退出条件里「在 CI 里生效」仍然成立，
> 但**生效的频率降了**：中间攒的违规要等到发版那天才会一次性暴露。三条 lint 都是零依赖
> 标准库脚本，本地 `python3 scripts/lint_*.py` 随手能跑——把它当成发版前的关门检查，
> 别当成写代码时的实时护栏。触发条件的定义在 `lint.yml` 的头部注释，此处不重述。

> **testid 必须早于 Phase 1b 动笔。** 这是全篇最便宜也最容易漏的一条：Phase 4 的任何布局改动都会推翻用 class 或结构选择器写的 E2E。合流计划 §8 把「testid 定名拖到 1b 之后」列为头号返工源。

---

## 0.6 事实性修复

| 项 | 状态 |
|---|---|
| `.gitignore` 末尾的合并冲突标记 | ✅ 已修 |
| `pyproject.toml` 版本号对齐 git tag | ✅ `0.1.0` → `1.4.0`（2026-08-23）。全仓库只有这一处版本号，`/api/health` 通过 `importlib.metadata` 读它，不再抄一份 |
| `ai_settings.example.json` 补齐 provider | ✅ 五个 provider 齐了（2026-08-23）。**不是手抄补两段，是整份从 `ai/config.py` 的 `default_settings_dict()` 生成**——手抄就是给同一个事实开第二处定义，下次改默认值又会漏 |

> `max_retries` 现在会出现在示例文件里，因为它本来就在 `default_settings_dict()` 里、也本来就会被写进用户的 `config/ai_settings.json`。**这不是把它「接通」**——见下。
>
> 示例文件与默认值的漂移目前没有护栏。**一条 `assert json.load(example) == default_settings_dict()` 的单测归 008**，本分支不建（007 的 `tests/` 才刚有雏形）。

**`max_retries` 不在 0.6 里。** 它能填、能存、能读回、`settings.js` 也在渲染，但没有任何 provider 消费它。删掉还是接通都是行为变更，归 Phase 2——技术栈计划 Phase 2 有专门一条。别顺手在 007 里处理掉。

---

## 0.8 token 悬空引用 lint

**这是第三条 lint，与 0.5 的两条并列**——0.5 管 testid 命名与选择器，本条管 CSS 自定义属性。合流计划 §6 步骤 0.8。

`var(--typo)` **不报错**：CSS 自定义属性引用一个不存在的名字时静默回落到继承值，页面照常渲染，只是颜色/尺寸变成了别的东西。这一类缺陷靠人眼过规格是抓不住的——设计规格里实测到三处，全都是「看起来完全正常」的行：

| 悬空引用 | 出处 | 后果 |
|---|---|---|
| `--r3-warn` / `--r3-danger` | 设计规格 §6.4 设计要求 1 | 五个降级横幅拿不到状态色，长得像普通提示。Codex 复审 #8 已记录 |
| `--r3-sidebar-w` / `--r3-right-w` | 设计规格 §6.2 三栏 Grid | `grid-template-columns` 整条声明失效，三栏塌成默认布局 |
| `--r3-text-quiet` | 只在 sepia / green / night 三个阅读主题里被赋值 | paper 主题（默认）下无定义 |

**三处已在 007 修掉**（见 [`spec-frontend-design.md`](../../20260817-frontend-ui-refactor/spec-frontend-design.md) 的 §3.2 / §3.3 / §3.4 / §6.2 / §6.4）。本条要做的是**不让它再长出来**。

实现约十行：扫 `designs/reader-pro-next/`、`static/css/`、`templates/*.html` 与设计规格里的 CSS 代码块，收集全部 `--x:` 定义与全部 `var(--x)` 引用，求差集；浏览器内置或第三方定义的走白名单。**验收：差集为空，且在 CI 里生效。**

> 注意 `var(--x, fallback)` 的两义性：带 fallback 的引用**照样要判违规**。fallback 是给运行时降级用的，不是给拼错名字用的——一条永远走 fallback 的 `var()` 是死代码，而它看起来在正常工作。

✅ 已完成（commit `7f7fd86`）。`scripts/lint_token_refs.py`：扫 22 个来源、271 个定义 / 1119 处引用，悬空 0、带 fallback 0。

---

## 0.7 删除死代码

✅ 已完成。`SearchIndex`、`BookIndex.from_book_pkl`、`SearchIndex.build_from_library` 均已不在树中。

保留的记录：这三个符号是 A5 的「第四处」loader，带一个裸 `pickle.load`。先删再谈合并，否则 011 的 `book_store.py` 会把一个静默失败分支收编成现役设计。`BookIndex` / `ChapterIndex` dataclass **是活的**，三条运行路径在用。

---

## 8. 退出门槛

- [x] 0.1 修复；用户数据在重新处理后逐字节不变；中断可干净重跑
- [x] 0.2 修复；`uv build` 解包后 `static/js` / `static/css` / `static/vendor` 齐全；**且装出来真能跑**（见 §8.1 的 S2）
- [x] 0.3 `--port` 与 `READER3_PORT` 生效且优先级正确；`GET /api/health` 可用
- [x] 0.4 四个文件 IIFE 化；四个页面人工 smoke 通过
- [x] 0.5 testid 两侧一致；两条 lint 在 CI 里生效且违规数为 0
- [x] 0.6 版本号对齐；示例配置补齐两个 provider
- [x] 0.7 死代码已删
- [x] 0.8 token 悬空引用 lint 在 CI 里生效，差集为 0
- [x] 六项人工 smoke checklist 走一遍（正文见 §8.1，2026-08-23 全绿）

### 8.1 六项人工 smoke checklist

> **这份清单此前只有引用、没有正文。** 技术栈计划 §阶段重排里写着「独立 commit ＋
> 六项人工 smoke checklist」，但六项是哪六项，两份文档都没写过。2026-08-23 按
> 「哪几项非人眼／非装包不可验」把它定下来：**0.5 与 0.8 不在其中**——那两项的
> 判据是 lint 违规数为 0，机器已经在管，再走一遍人工是重复记账。

| # | 对应 | 怎么验 | 结果（2026-08-23） |
|---|---|---|---|
| S1 | 0.1 | 真实书里造一条标注 → 重新处理该 epub → 用户数据还在 | ✅ `notes.json` / `ai_meta.json` **sha256 逐字节不变**，`ai_conversations` 在，无 staging 残留，刷新后高亮回到同一段文字 |
| S2 | 0.2 | wheel 装进**干净 venv** → 起服务 → 阅读器不白屏 | ✅ 修完两个 bug 后全绿（下详）。`static/{js,css,vendor}` 8 个资源全 200，正文 15844 字，高亮渲染，零控制台错误 |
| S3 | 0.3 | `--port` ／ `READER3_PORT` ／ `/api/health` | ✅ 8137 起服务时用户自己的 8123 实例正在跑，没有互相干扰——这正是这一项存在的理由 |
| S4 | 0.4 | 四个页面（library / reader / settings / 跨库搜索）零控制台错误 | ✅ 唯一一条错误是 `/api/ollama/models` 503，Ollama 没起时的设计行为，设置页降级成安装指引 |
| S5 | 0.6 | 示例配置能被**真实 loader** 吃下去 | ✅ 与 `default_settings_dict()` 逐键相等，五个 provider 全部解析出 model／timeout／retries |
| S6 | 0.7 | 删死代码后关键词与语义搜索都还在 | ✅ 关键词 200 有结果；语义在未索引的书上返回空并显示「Results from 0 indexed books (1 not indexed)」 |

**S2 揪出了一个比 0.2 本身更严重的问题，已一并修掉。**

`static/**/*` 修好之后，`check_wheel_contents.py` 全绿、文件确实都进了 wheel——
但把 wheel 装进干净 venv 起服务，**`/`、`/settings`、`/read/*` 每个 HTML 页面都 500**。

原因与打包无关：`pyproject.toml` 的依赖只有下界没有上界，干净环境解析出
**starlette 1.6.0**，而 `templates.TemplateResponse(name, context)` 这个旧签名
在 1.x 里已被删除（0.29 起就标了废弃）。仓库的 `uv.lock` 钉着 0.49.3，所以
`uv run` 与 pytest **全程绿灯，一次都没报过**。

修法是把三处调用点改成新签名 `TemplateResponse(request, name, context)`——
0.49 与 1.6 都吃，因此不需要给依赖加上界（加上界只是把问题冻住，不是修好）。
两个版本下都实测过三个路由 200，仓库 68 条测试仍全绿。

护栏是新增的 `scripts/smoke_installed_wheel.py`，接进 CI 的 `wheel` job：
造一本合成 epub（`READER3_BOOKS_DIR` 指到临时目录，**绝不碰真 `books/`**）→
装 wheel 进干净 venv → 起真的 `reader3-server` 子进程 → 打四个路由。
**它是全仓库唯一一处按最新依赖解析的地方**，`uv.lock` 在这里故意不参与——
任何「依赖出大版本 → 装出来起不来」的问题，只有它看得见。已实测会咬人：
把 `/settings` 改回旧签名，它报 `500` 并退出 1。

> 这两件事值得分开记：**「文件进没进 wheel」和「装出来能不能跑」会独立地坏。**
> 007 原本只写了前者，于是修完 0.2 之后，一个每个页面都 500 的 wheel 仍然会
> 通过全部退出门槛。

---

## 9. 给 `/tdd-guardian:workflow` 的输入

> **硬约束**：`workflow` 会**拒绝**含反引号、`|`、`>`、`<`、`;`、`&&`、`||`、`$(` 或换行的 `$ARGUMENTS`（它把这些当 shell 注入向量）。所以输入必须是**单行纯文本，路径不加反引号**。下面两段照抄即可。

**0.1**：

```
/tdd-guardian:workflow Fix a data-loss bug in src/reader3_app/reader3.py: process_epub calls shutil.rmtree on its output directory books/NAME_data before writing anything, and user-owned files live in that same directory - notes.json, ai_meta.json, ai_conversations/ and chroma_db/ - so reprocessing an EPUB silently destroys every annotation for that book and changes its book_uuid. Replace the rmtree with a staging directory plus full validation plus atomic switch: write the regenerated artifacts (book.pkl, book.epub, images/) into a staging directory under the same parent so the final swap is atomic, validate them, then swap into place while preserving every user-owned file byte for byte. Follow the step ordering of the two-file commit protocol defined in docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md Phase 3 - read that section first, it is the canonical definition. Out of scope: lru_cache invalidation, and any change to the Book dataclass or the pickle format. Put tests in tests/unit and use the books_dir fixture from tests/conftest.py, never the real books/ directory.
```

**0.3**（0.1 合入后再跑）：

```
/tdd-guardian:workflow Make the reader3 server port configurable and add a readiness probe. The main function in src/reader3_app/web/server.py hardcodes host 127.0.0.1 and port 8123 in its uvicorn.run call with no env or CLI override, which stops Playwright from starting its own instance and makes concurrent CI runs fight over the port. Add a READER3_PORT environment variable and a --port command line flag, where the flag wins over the env var and the env var wins over the 8123 default. Also add a GET /api/health route returning a small JSON readiness payload, which Phase 1b will use as its Playwright webServer probe. Put precedence tests in tests/unit and the route contract test in tests/contract using FastAPI TestClient. Out of scope: every other route, and the Playwright webServer config itself.
```

### 跑之前知道这两件事

1. **coverage gate 第一次不会拦你。** `coverageMode` 是 `no-decrease` 且 `baseline` 为 `null`，首次运行（以及每次换分支）会把当时的覆盖率**记为基线并直接通过**。所以 007 上跑出来的「PASS」不代表达标——真正的门槛在 008 立。见 `tasks/008-test-safety-net.md` §1。
2. **workflow 不会替你 commit**，这是设计如此。它跑到全绿就停，提交是你的决定。
