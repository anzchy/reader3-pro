# Reader Pro Next — 设计规格与高保真原型

这个目录把**规格**与**原型**放在一起：规格描述现状与合同，原型是可运行的目标形态。改动其一时请同步另一个。

## 目录结构

```
designs/reader-pro-next/
├── README.md                       ← 本文件
├── index.html                      ← 原型入口（含全部 CSS 与 design token）
├── data.jsx                        ← mock 数据；形状对齐 spec §7.1
├── components.jsx                  ← 跨屏共用组件（Modal / Toggle / 焦点陷阱 / 面板…）
├── app.jsx                         ← 应用外壳 + Library 屏
├── reader.jsx                      ← Reader 屏（分页、批注、TOC、笔记、搜索、AI）
├── settings.jsx                    ← Settings 屏
├── design-notes.md                 ← 设计取向、色板、交互模型的简述
├── assets/                         ← 原型用到的真实内容素材
└── spec/
    ├── reader-pro-spec.md          ← 现状实现审计 + §0.3 已确认的产品决策
    ├── reader-pro-next-parity.md   ← 原型 vs 现状的两轮对齐审计与收口状态
    └── screenshots/                ← 22 张旧 UI 实测截图（spec §14 的证据）
```

## 运行原型

```bash
cd designs/reader-pro-next
python3 -m http.server 8125 --bind 127.0.0.1   # file:// 会被 CORS 挡掉 jsx 加载
open http://127.0.0.1:8125/index.html
```

| URL | 屏幕 |
|---|---|
| `/index.html` | Library（默认） |
| `/index.html?screen=reader` | Reader |
| `/index.html?screen=settings` | Settings |
| `/index.html?screen=reader&state=epub-missing` | Reader 的 EPUB 缺失错误屏 |

## 文档分工与权威范围

每条事实只有一个家。要改某项，改它的**权威文档**，其余文档只许引用。

| 文档 | 权威范围 | 不权威 |
|---|---|---|
| `README.md`（本文件） | 原型的性质、原型 → 生产的翻译规则 | 目标设计、实施顺序 |
| `spec/reader-pro-spec.md` | **现在**是什么样（现状审计、路由、组件、已知缺口）＋ §0.3 五条已拍板的产品决策 | 目标设计、实施顺序 |
| `spec/reader-pro-next-parity.md` | 原型相对现状**补齐了什么、还差什么** | 同上 |
| `docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md` | **应该**变成什么样：双层 token、testid 命名、逐页规格、iframe 边界（§6.0）、降级状态设计（§6.4） | 实施顺序、分支编号 |
| `docs/plans/20260816-tech-stack-migration/plan-tech-stack-migration.md` | 技术栈选型、后端架构、存储格式、A1–A5 架构决策，**以及实施顺序**：阶段划分、门槛、分支编号、耦合点 | 设计细节 |
| `docs/plans/20260817-frontend-ui-refactor/contracts/annotation-host-contracts.md` | 标注宿主契约 K1–K6 | — |
| `docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md` | **前端工作项 WI-1–WI-20 ＋ 前端测试矩阵**，以及原型 → 生产的事实基线 | 后端分层、存储格式、分支编号 |
| `docs/plans/20260816-tech-stack-migration/tasks/{分支名}.md` | **后端分支**的任务清单（007 / 008 / 009）。前端分支没有任务文件 | — |

## 原型的性质（重要）

原型用 **React 18 + 浏览器内 Babel** 写成，而 migration plan 明确不引入 React。这不矛盾：

- 原型是**可执行的规格**，用来验证交互、状态机与视觉，不是要移植的生产代码。
- 生产实现按 migration plan Phase 4 走 **TypeScript + Vite 多页构建**，无框架。

**最容易做错的事：把原型当成待移植的代码。** 下面三节是从原型到生产的翻译规则，本目录是它们的唯一真相源。

## 原型 → 生产的翻译规则

### 直接可移植

| 项 | 说明 |
|---|---|
| DOM 结构与 class 命名 | 原型的标记结构就是目标结构，Jinja 模板照抄 |
| 全部 CSS 与 token 值 | `index.html` 的样式块即 Phase 4 的 CSS 产物来源（token 改名见设计规格 §3） |
| 交互状态机 | 单面板互斥、分层 Escape、选区 → 工具条 → 编辑器。原型里是 React state，生产里写成每页一个显式状态对象 + 一个 render 函数，**不需要框架** |
| 可访问性实现 | 焦点陷阱与焦点归还、`role="switch"`、`aria-live` 播报、`role="button"` 的书卡 |
| 空态 / 错误态文案 | `No results found for "{query}"`、`Search failed — …`、EPUB 缺失屏 |

### 明确**不可**移植（照搬即错）

| 项 | 原型做法 | 生产必须做法 |
|---|---|---|
| **分页** | CSS 多列 + `translateX`，作用于普通 DOM | epub.js `flow: paginated`，在 iframe 内。原型的 `usePagination` 是**行为参考**，不是实现参考 |
| **标注锚定** | `{paragraph, start, end}` 字符偏移 | 保留现有 CFI + quote/prefix/suffix（`Annotation` dataclass）。**绝不用原型的偏移方案替换** |
| **数据流** | `data.jsx` 同步本地状态，零网络 | 每个面板需要 loading / error / empty 三态。原型只做了 empty 与 error，**loading 骨架屏未建** |

> ⚠️ **偏移单位陷阱**：原型的偏移是 JS 字符串下标，即 **UTF-16 code unit**；后端 `search_service.py` 的偏移是 **Unicode code point**。谁把原型的偏移逻辑挪到跨端复用的共享模块，谁就会在 emoji 与非 BMP 字符上错位。这条已写进 migration plan 的 API 契约要求。

### 原型验证出来的、值得带进生产的三条行为

这三条是原型实测中发现并修复的缺陷，epub.js 版本**同样会有**，应写成 Phase 4B 的测试用例：

1. **连续翻页只前进一步** —— 事件处理器读到的是上一次渲染的页码。epub.js 的 `rendition.next()` 是异步的，快速按键同样会用陈旧状态排队。
2. **快翻跨章会一次跳两章** —— 换章后新章页数未知时不得继续响应翻页；需要一个"重新测量前锁住"的闸门。
3. **向前翻页跨章后落在新章第 1 页** —— 导致上一章永远读不到。跨章向前必须落到上一章**末页**。第 3 条在当前生产实现里是否存在**尚未验证**，建议 Phase 1b 顺手加一条 E2E。

### 值得反向移植回生产的一个实现

原型用**按所有边界切分段落文本**来渲染重叠批注，而不是 `Range.surroundContents()`（后者跨元素会抛异常，重叠批注会互相破坏 DOM）。这个策略与锚定方案无关，可直接落到 4B.1 拆出的 `renderer.ts`。
