# 让 agent 驱动 / 调试 Web UI：MCP browser bridge 调研与 reader3-pro 借鉴建议

> **调研日期**：2026-09-28。本文只基于五份调研底稿（官方、社区/vendor、开源浏览器 MCP、开源内嵌/框架 bridge、仓库现状），没有做额外的 web 调研。
> **姊妹文档**：[paper-one：`paper` CLI 与 debug-only MCP bridge 参考](paper-one-cli-and-mcp-bridge.md)。它拆解的是 Tauri app 内嵌 bridge；本文回答的是"普通 Web 应用要不要、要什么样的 bridge"。
> **示例执行情况**：本文没有安装或运行任何被调研的 MCP server，结论来自文档、源码静态阅读和仓库 `path:line`。
>
> **约定**：
> - 没有标注的陈述都附有 URL 或仓库 `path:line`（仓库路径相对 reader3-pro 根目录）。
> - 【推断】表示来源没有直接写明、由作者推理得出，后面给一句依据。
> - 【未核实】= 只在二手来源见到；未核验 = 拿不到一手数据；【不可达】= 访问失败。这三类标记从底稿原样照搬。
> - 官方来源编号 O1–O18，vendor/社区来源编号 C1–C18（对应底稿中的 S1–S18）。

---

## 1. TL;DR

- **官方立场**：Anthropic 的核心要求是"give Claude a check it can run"，其中包括截图对比（O3）。唯一点名浏览器 MCP 的现行官方文档是 MCP quickstart，示例用的是 Playwright MCP（O2）。官方给的工具优先级是 MCP > Bash > Claude in Chrome > computer use（O7）。
- **社区共识**：agent 需要"眼睛"来闭合 UI 验证环；a11y snapshot 适合做交互主通道；token 成本主要来自 snapshot 在历史里的累积（C11、C13）；对 coding agent，CLI + 结果落盘通常比常驻 MCP 更省（C4、C7、C10），这一点 Microsoft 自己也承认（C4）。
- **两个主流开源 bridge**：playwright-mcp（37,629★，72 个工具）和 chrome-devtools-mcp（52,671★，59 个工具）都支持进 iframe，都能执行任意 JS。playwright-mcp 的 `browser_run_code_unsafe` 默认开启，README 自称 "RCE-equivalent"；chrome-devtools-mcp 默认向 Google 发使用统计和 CrUX 请求。
- **内嵌型 bridge 是给"没有 CDP"的宿主用的**：Tauri 插件（309★）默认绑 0.0.0.0、无认证、不查 Origin，也不进 iframe；Next `/_next/mcp` 和 Vite/Storybook 插件只给框架语义层信息，不看 DOM。
- **非 MCP 的 gstack browse** 是这批里唯一有显式 `frame` 命令、绑 127.0.0.1 + Bearer token、CDP 默认拒绝的方案，也是用户已经在用的标准浏览工具。
- **reader3-pro 现状**：纯 Web 应用，固定监听 127.0.0.1:8123；E2E 已经用 pytest-playwright 的 `frame_locator` 进入 epub.js iframe（`tests/e2e/helpers.py:163-179`）；页面上已有 `window.Reader3Epub` 桥（`src/reader3_app/web/static/js/epub-renderer.js:375-401`），但**没有 CFI/进度的结构化 getter**。
- **关键风险**：soak 台账证明，重观测（tracing、不过滤的 request 监听）会把 flaky 压掉（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md:884-898`）。任何观测方案都不能挂到 soak 跑上。
- **推荐方案："不自建 bridge，补一个只读观测面"**：不做 Tauri 式应用内 MCP bridge；在 `window.Reader3Epub` 上加一个只读的 `getDebugState()`；agent 的交互式驱动用 gstack `/browse`；回归仍由 `tests/e2e/` 的 pytest-playwright 承担，agent 的探索结果转写成 pytest 用例。备选 A 为 chrome-devtools-mcp（只查 console/network/perf），备选 B 为 playwright-mcp（探索式写测试）。

---

## 2. 调研范围与方法

**日期**：2026-09-28。

**问题清单**：Q1 官方怎么说；Q2 社区和 vendor 怎么做；Q3/Q4 有哪些开源 MCP bridge、各自原理与安全面；Q5 工具清单；Q6 最佳实践；Q7 对 reader3-pro 的借鉴。

**方法**：
- 五个并行 subagent 各写一份底稿：官方来源、社区与 vendor、开源浏览器 MCP、开源内嵌/框架 bridge、仓库现状（只读，`path:line` 引用）。
- 底稿里的 stars、pushed_at、archived 字段用 `gh api repos/<o>/<r>` 读取（开源浏览器 MCP 底稿 2026-09-28 00:11 UTC；内嵌 bridge 底稿 2026-09-28T00:14Z）。
- 主会话复核：写本文时（2026-09-28 00:59 UTC）用 `gh api` 抽查了 6 个仓库。结果：playwright-mcp 37,629、chrome-devtools-mcp 52,671、mcp-server-tauri 309、mcp-server-browserbase 3,413（archived=true）、next-devtools-mcp 823，与底稿一致；BrowserMCP/mcp 读到 7,136，底稿是 7,135，差 1，属正常漂移，下表按底稿取值。仓库侧的 `path:line` 抽查了 `epub-renderer.js:375-401` 与 `frontend/src/shared/debug.ts`，内容与底稿一致。
- npm registry 版本号与发布日期**未核验**：内嵌 bridge 底稿记录本机 `curl registry.npmjs.org` 被权限拒绝（2026-09-28T00:2xZ），版本号一律取自仓库 `package.json`。

### 2.1 来源清单

| 来源 | 类别 | 访问日期 | 状态 |
|---|---|---|---|
| O1 https://code.claude.com/docs/en/mcp | 官方 | 2026-09-28 | 可达 [摘录，结构化] |
| O2 https://code.claude.com/docs/en/mcp-quickstart | 官方 | 2026-09-28 | 可达 [原文] |
| O3 https://code.claude.com/docs/en/best-practices | 官方 | 2026-09-28 | 可达 [原文] |
| O4 https://www.anthropic.com/engineering/claude-code-best-practices | 官方 | 2026-09-28 | 现 308 到 O3；旧版正文取自 Wayback 20250601 快照（WebFetch【不可达】，改用 gstack browse 读到）[原文] |
| O5 https://code.claude.com/docs/en/chrome | 官方 | 2026-09-28 | 可达 [原文] |
| O6 https://support.claude.com/en/articles/12012173-getting-started-with-claude-in-chrome | 官方 | 2026-09-28 | 可达 [摘录] |
| O7 https://code.claude.com/docs/en/computer-use | 官方 | 2026-09-28 | 可达 [原文] |
| O8 https://code.claude.com/docs/en/desktop | 官方 | 2026-09-28 | 可达 [摘录] |
| O9 https://code.claude.com/docs/en/skills | 官方 | 2026-09-28 | 可达 [摘录] |
| O10 https://code.claude.com/docs/en/agent-sdk/mcp | 官方 | 2026-09-28 | 可达 [原文] |
| O11 https://claude.com/blog/building-agents-with-the-claude-agent-sdk | 官方 | 2026-09-28 | 可达（anthropic.com/engineering 原链接 308 到此）[摘录] |
| O12 https://www.anthropic.com/engineering/writing-tools-for-agents | 官方 | 2026-09-28 | 可达 [摘录] |
| O13 https://www.anthropic.com/engineering/code-execution-with-mcp | 官方 | 2026-09-28 | 可达 [摘录] |
| O14 https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents | 官方 | 2026-09-28 | 可达 [摘录] |
| O15 https://www.anthropic.com/engineering/harness-design-long-running-apps | 官方 | 2026-09-28 | 可达 [摘录] |
| O16 https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | 官方 | 2026-09-28 | 可达 [摘录] |
| O17 https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool | 官方 | 2026-09-28 | 可达 [摘录] |
| O18 https://claude.com/plugins/playwright | 官方（目录页，内容标注 "Made by Microsoft"） | 2026-09-28 | 可达 [摘录] |
| C1 https://developer.chrome.com/blog/chrome-devtools-mcp | vendor | 2026-09-28 | 可达 |
| C2 https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session | vendor | 2026-09-28 | 可达 |
| C3 https://github.com/ChromeDevTools/chrome-devtools-mcp （README） | vendor | 2026-09-28 | 可达 |
| C4 https://github.com/microsoft/playwright-cli ＋ https://playwright.dev/docs/getting-started-cli | vendor | 2026-09-28 | 可达 |
| C5 https://debbie.codes/blog/letting-playwright-mcp-explore-your-site/ | vendor（员工个人博客） | 2026-09-28 | 可达 |
| C6 https://til.simonwillison.net/claude-code/playwright-mcp-claude-code | 社区 | 2026-09-28 | 可达 |
| C7 https://mariozechner.at/posts/2025-11-02-what-if-you-dont-need-mcp/ | 社区 | 2026-09-28 | 可达 |
| C8 https://news.ycombinator.com/item?id=45947444 | 社区 | 2026-09-28 | 可达 |
| C9 https://www.builder.io/blog/playwright-mcp-server-claude-code | 社区 | 2026-09-28 | 可达 |
| C10 https://shipyard.build/blog/playwright-mcp-vs-cli/ | 社区 | 2026-09-28 | 可达 |
| C11 https://only-cli.com/blog/playwright-mcp-token-cost/ | 社区 | 2026-09-28 | 可达 |
| C12 https://dev.to/pointchecknote/browser-automation-with-claude-playwright-mcp-why-accessibility-snapshots-beat-screenshots-2pke | 社区 | 2026-09-28 | 可达 |
| C13 https://github.com/microsoft/playwright-mcp/issues/1233 | 社区 | 2026-09-28 | 可达，open |
| C14 https://github.com/microsoft/playwright-mcp/issues/1177 | 社区 | 2026-09-28 | 可达，open |
| C15 https://github.com/microsoft/playwright-mcp/issues/1479 | 社区 | 2026-09-28 | 可达，closed |
| C16 https://github.com/microsoft/playwright-mcp/issues/1495 | 社区 | 2026-09-28 | 可达，closed |
| C17 https://github.com/microsoft/playwright/pull/42691 | 社区（PR，含 vendor review） | 2026-09-28 | 可达，closed 未 merge |
| C18 https://www.sentinelone.com/vulnerability-database/cve-2025-9611/ | 社区（安全数据库） | 2026-09-28 | 可达 |
| R1 https://github.com/microsoft/playwright-mcp | 开源仓库 | 2026-09-28 | 可达 |
| R2 https://github.com/ChromeDevTools/chrome-devtools-mcp | 开源仓库 | 2026-09-28 | 可达 |
| R3 https://github.com/browserbase/mcp-server-browserbase | 开源仓库 | 2026-09-28 | 可达，archived |
| R4 https://github.com/browserbase/stagehand | 开源仓库（非 MCP） | 2026-09-28 | 可达 |
| R5 https://github.com/browser-use/browser-use | 开源仓库 | 2026-09-28 | 可达 |
| R6 https://github.com/BrowserMCP/mcp | 开源仓库 | 2026-09-28 | 可达，事实停更 |
| R7 https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer | 开源仓库 | 2026-09-28 | 可达，archived |
| R8 https://github.com/hypothesi/mcp-server-tauri | 开源仓库 | 2026-09-28 | 可达 |
| R9 https://github.com/amafjarkasi/electron-mcp-server | 开源仓库 | 2026-09-28 | 可达 |
| R10 https://github.com/halilural/electron-mcp-server | 开源仓库 | 2026-09-28 | 可达 |
| R11 https://github.com/clharman/circuit-mcp | 开源仓库 | 2026-09-28 | 可达（snowfort-ai 重定向至此） |
| R12 https://github.com/vercel/next-devtools-mcp | 开源仓库 | 2026-09-28 | 可达 |
| R13 https://github.com/vercel/next.js （packages/next/src/server/mcp） | 开源仓库 | 2026-09-28 | 可达 |
| R14 https://github.com/antfu/nuxt-mcp-dev | 开源仓库 | 2026-09-28 | 可达 |
| R15 https://github.com/webfansplz/vite-plugin-vue-mcp | 开源仓库 | 2026-09-28 | 可达，2025-04-20 后停更 |
| R16 https://github.com/storybookjs/storybook （code/addons/mcp） | 开源仓库 | 2026-09-28 | 可达 |
| R17 本机 `~/.claude/skills/gstack/browse/`（上游 https://github.com/garrytan/gstack） | 开源仓库（非 MCP） | 2026-09-28 | 本地源码可读 |
| V1 https://vercel.com/docs/agent-resources/vercel-mcp | vendor（托管服务文档） | 2026-09-28 | WebSearch 摘要，工具名未核验 |
| V2 https://storybook.js.org/docs/ai/mcp/overview | vendor（文档） | 2026-09-28 | 可达 |
| P1 `docs/references/paper-one-cli-and-mcp-bridge.md` | 仓库内 | 2026-09-28 | 存在 |
| P2 仓库现状底稿引用的源码、测试、ADR、CI、soak 台账（见 §9 各行路径） | 仓库内 | 2026-09-28 | 存在（§9 路径已逐一 `ls`） |

**只在底稿里一笔带过、未单独计数的线索**：WebMCP（webmachinelearning/webmcp 等）、vercel-labs agent-browser、nuxt-modules/mcp-toolkit、unplugin-mcp、vite-plugin-mcp-client-tools、react-devtools-mcp；playwright-mcp issue #915/#1216/#1329/#514/#1639、microsoft/playwright #39955，以及 testdino、qaskills.sh 的二手文章（均为搜索摘要，未抓取）。

### 2.2 分类计数

| 类别 | 数量 | 编号 |
|---|---|---|
| 官方 | 18 | O1–O18 |
| vendor | 7 | C1–C5、V1、V2 |
| 社区 | 13 | C6–C18 |
| 开源仓库 | 17 | R1–R17 |
| 仓库内 | 2 组 | P1、P2 |
| **合计（不含仓库内）** | **55** | |

**不可达记录**：
- Wayback `https://web.archive.org/web/2025-05-01/https://www.anthropic.com/engineering/claude-code-best-practices`：WebFetch【不可达】（2026-09-28 约 08:05 CST），改用 gstack browse 读到 20250601 快照。
- `registry.npmjs.org`：本机 curl 被权限拒绝，npm 版本与发布日期未核验。
- 社区底稿与开源浏览器 MCP 底稿均声明本次没有【不可达】URL。

---

## 3. 官方资料（Q1）

本节只收 Anthropic / Claude Code 官方来源。[原文] 表示 WebFetch 返回了完整原文；[摘录] 表示只拿到抽取器给的片段，引号内是抽取器给出的逐字短语，上下文未逐字复核。本次全程**没有**调用任何 `mcp__claude-in-chrome__*` 工具，Claude in Chrome 的内容只来自文档。

### 3.1 配置与共享

- **添加与 scope**：`claude mcp add [options] <name> <url-or-command>`，stdio 必须用 `--` 分隔。scope 分 Local（默认，存 `~/.claude.json`）、Project（写 `.mcp.json`，"Shared: Yes"）、User；优先级 Local > Project > User > Plugin > claude.ai connectors（O1）。
- **Playwright 是官方唯一演示的浏览器 MCP**：`claude mcp add playwright -- npx -y @playwright/mcp@latest`，"it gives Claude a browser it can navigate, click, and read, and it needs no account"；建议 "pointing it at your local dev server to check that a page still renders after a change"（O2）。
- **"Added" 不等于能运行**：要用 `claude mcp list` 或 `/mcp` 确认 `✔ Connected`；首次 npx 下载慢时可设 `MCP_TIMEOUT=60000`（O2）。
- **`.mcp.json` 的审批**：交互式会话里 project-scoped server 使用前要用户批准；但 "`claude -p`, Agent SDK, and cloud sessions, servers load without prompting"；v2.1.196 起审批只在 trusted workspace 生效；可用 `disabledMcpjsonServers`、`--strict-mcp-config` 阻止加载（O1）。审批存在的理由是 "so a repository you clone can't launch processes on your machine without your consent"（O2）。
- **输出上限**：MCP 输出超过 10,000 token 告警，默认上限 25,000 token（`MAX_MCP_OUTPUT_TOKENS`），超限时落盘并以文件引用替换（O1）。这对 a11y snapshot 很大的页面直接相关（参见 §4.2 的 C13）。
- **上下文成本**：每个已连接的 server 都占上下文，不用就移除（O2）；Chrome 集成默认常开会 "increases context usage since browser tools are always loaded"（O5）。
- **SDK 权限**：优先用 `allowedTools`（如 `mcp__playwright__*`）精确放行，不要用 `bypassPermissions`（O10）。

### 3.2 验证闭环

- **核心原则**："Give Claude a check it can run: tests, a build, a screenshot to compare"；没有检查时 "'looks done' is the only signal available"（O3）。
- **UI 改动的推荐 prompt**："[paste screenshot] implement this design. take a screenshot of the result and compare it to the original. list differences and fix them"（O3）。旧版博文的说法是 "Write code, screenshot result, iterate"，并点名 Puppeteer MCP，称 2–3 轮后效果明显更好（O4）。该博文已 308 到 O3，Puppeteer 措辞不在现行页面上。
- **证据而非断言**："Have Claude show evidence rather than asserting success: the test output, the command it ran and what it returned, or a screenshot of the result"（O3）。
- **检查强度分四档**：单 prompt → `/goal` → Stop hook（"deterministic gate"）→ 独立验证 subagent（O3）。
- **"do all testing as a human user would"**：明确要求用浏览器自动化做端到端验证后，Claude 能发现 "bugs that weren't obvious from the code alone"（O14）。
- **生成与评估分离**：evaluator 拿到 Playwright MCP 后 "interact with the live page directly before scoring each criterion"；"Out of the box, Claude is a poor QA agent"，要读 evaluator 日志调 prompt（O15）。
- **LLM-as-judge 不够稳健**：Agent SDK 博文把视觉反馈（Playwright MCP 截图、多 viewport、交互测试）列为验证手段之一，但称 LLM as judge "generally not a very robust method"（O11）。
- **DOM 与截图的取舍**："DOM-based interactions execute quickly but consume many tokens, while screenshot-based interactions are slower but more token-efficient"（O16）。判断结果要检查环境的真实状态，而不是只看界面提示（O16）。

### 3.3 调试与已知盲区

- **console 要带着问题去读**："Tell Claude what patterns to look for rather than asking for all console output, since logs can be verbose"（O5）。
- **原生对话框是盲区**：Puppeteer MCP 看不到 `alert` 模态框（O14）；JS 对话框会阻塞 Claude in Chrome（O5）。
- **提示注入**："instructions on webpages or contained in images might override your instructions"（O17）。

### 3.4 工具选择与 Claude in Chrome

- **官方工具优先级**：有 MCP 用 MCP，其次 Bash，浏览器任务且已配置时用 Claude in Chrome，最后才是 computer use（O7）。
- **Claude in Chrome**：共享浏览器登录态、在可见窗口里操作；需要 Anthropic 直付订阅并 `/login`，API key 认证时关闭（O5）。支持文档原话："Claude in Chrome is enhanced with our safety classifiers but is still risky"（O6）。
- **Desktop Preview / autoVerify**：Desktop 可启动 dev server 并在 Browser pane 里 "takes screenshots, inspects the DOM, clicks elements, fills forms"，配置在 `.claude/launch.json`（O8）。`/run`、`/verify` 技能能推断 "browser-driven" 项目的启动方式（O9）。
- **目录页不是背书**：claude.com 的 Playwright 插件页标注 "Made by Microsoft"，描述基于 accessibility tree、"without requiring vision models"（O18）。这证明 Anthropic 目录收录了它，不构成 Anthropic 的技术论述。

### 3.5 未找到官方论述的内容

- Playwright MCP 与 Claude in Chrome 在 Web UI 测试上的取舍（无头/有头、隔离 profile/共享登录态、CI 可用性）：**未找到官方论述**。O7 只给了粗粒度优先级。
- accessibility snapshot 与 screenshot 在 Claude Code 里的选择建议：**未找到官方论述**。O16 只从 eval 角度比较了 token 与速度；O18 的 a11y 说法来自 Microsoft。
- 在 CI 或 `claude -p` 里跑 Playwright MCP 做 UI 回归：**未找到官方论述**。
- Playwright MCP 的具体 flag（`--headless`、`--isolated`、`--user-data-dir`）：**未找到官方论述**。O2 只提到 `--browser`。
- 视觉回归基线、截图 diff 阈值：**未找到官方论述**。
- **iframe 内部状态怎么观测**（本仓库最关心的问题）：**未找到官方论述**。
- **应用内嵌 debug bridge 的门控与安全**：**未找到官方论述**。
- 【推断】官方叙事重心已从第三方浏览器 MCP 转向自家的 Claude in Chrome、Desktop autoVerify 和 `/verify`。依据：现行 O3 不再点名 Puppeteer/Playwright，而 O4 的相关措辞随 308 下线；Playwright 仍保留在 O2 作入门示例。
- 【推断】Claude in Chrome 不适合 CI。依据：O5 要求 `/login` 认证，且依赖可见 Chrome 窗口。

---

## 4. 社区实践（Q2）

社区底稿的引文来自 WebFetch 抓取后的摘要，不是逐字核对过的全文。

### 4.1 vendor 来源（Google Chrome 团队、Microsoft Playwright 团队）

- **C1 Chrome DevTools MCP 发布文**（2025-09-23）：立论是 coding agent "are not able to see what the code they generate actually does when it runs in the browser"。给了五类可直接照抄的 prompt，包括 "Verify in the browser that your change works as expected"、图片加载失败的网络排查、"looks strange" 的布局排查、"loading slowly" 时跑 performance trace 看 LCP。这篇**没有任何安全提示**。
- **C2 autoConnect**（2025-12-11）：Chrome M144+ 用 `--autoConnect` 复用用户已登录的会话；用户可在 DevTools 里选中元素或失败请求交给 agent。安全设计：用户先在 `chrome://inspect/#remote-debugging` 手动开启，每次连接 Chrome 弹窗授权，会话期间显示 "controlled by automated test software" 横幅。
- **C3 chrome-devtools-mcp README**："Avoid sharing sensitive or personal information that you don't want to share with MCP clients"；默认收集使用统计（`--no-usage-statistics` 关闭），performance 工具可能把 trace 发给 CrUX API（`--no-performance-crux` 关闭）；提供 `--isolated`、`--headless`、`--slim`（"for doing only basic browser tasks"）和非 MCP 的 CLI。
- **C4 Playwright CLI**：官方原话，coding agents "increasingly favor CLI–based workflows exposed as SKILLs over MCP because CLI invocations are more token-efficient"，可以避免 "large tool schemas and verbose accessibility trees" 进入 context；MCP 仍适合需要持久状态、反复推理页面结构的 agent loop。snapshot 落盘到 `.playwright-cli/`，支持按元素、深度、bounding-box 截取；`playwright-cli install --skills`。
- **C5 Debbie O'Brien（撰文时为 Microsoft Playwright DevRel）**（2025-06-18）：流程是"探索 URL → 找到关键功能 → 生成 `@playwright/test` 测试 → 运行并迭代到通过"。prompt 约束："DO run steps one by one using the tools provided by the Playwright MCP"、role-based locator、auto-retrying assertion、除非必要不加 timeout。agent 顺带发现了一个真实的搜索 bug。作者承认结果会因模型和版本而不同。

### 4.2 社区来源

- **C6 Simon Willison TIL**（约 2025-07-01【推断：根据对应 X 帖 ID 估计】）：第一次要明确说 "playwright mcp"，否则 Claude 可能改用 Bash 自写 Playwright 脚本；用 headed 浏览器时登录可由人手动完成，cookie 在会话内保留。
- **C7 Mario Zechner**（2025-11-02）：实测 Playwright MCP 21 个工具占 13.7k tokens（context 的 6.8%），Chrome DevTools MCP 26 个工具占 18.0k tokens（9.0%），自写 README 只有 225 tokens。替代方案是 4 个经 CDP 9222 端口工作的极简 Node 脚本（`start.js`、`nav.js`、`eval.js`、`screenshot.js`，截图只输出文件路径）。原则：只写 agent 真正用得到的工具；结果先落盘，再由代码组合。
- **C8 HN 讨论**：共识是 MCP 工具描述有明显 context 开销、本地单人开发 CLI 更简单；分歧在分发与可移植性（chowfi："distributing tools to many users without relying on their environments"）、凭据边界和发现性。
- **C9 Builder.io**（2026-03-09）："agent 自验"闭环，改完代码让 Claude 打开 localhost 确认再交人 review；认证用 `--storage-state` 复用手动登录的会话；**固定 `@playwright/mcp` 版本**，用 `@latest` 或 beta 可能在会话中途让工具失效。给出 a11y ref 约 120 tokens、screenshot 约 1,500 tokens【推断：这是单元素/单步量级，与 C11/C13 的整页数字口径不同】。
- **C10 Shipyard**（2026-03-13）：CI 里的 E2E、截图、脚本化流程适合 CLI；探索陌生系统、从零生成 E2E 套件、self-healing selector 适合 MCP。结论："CLI now covers most standard agent-based browser automation needs"。
- **C11 only-cli**（无日期）：每个任务 Playwright MCP 约 114k tokens、CLI 约 25k、纯文本渲染器约 500。关键洞见："The expensive part is not the snapshot. It is the eleven previous snapshots that are still in the transcript"。【未核实】二手文章普遍称"Playwright 团队 benchmark 114k vs 27k"，本次没有找到 Microsoft 一手出处，C11 写的是 25k。
- **C12 a11y snapshot vs screenshot**（2026-08-05）：文章认为 snapshot 更确定、一次 200–400 tokens。评论者 Mads Hansen 反驳：ref 只在同一页面状态内稳定，建议 snapshot 驱动交互、screenshot 作第二证据通道。Alex Bickov：CSS transform、z-index 冲突在 a11y tree 里看不到，"different bug classes, not that one replaces the other"。
- **C13 playwright-mcp #1233**（2025-11-30，open）：复杂页面 snapshot 50KB–540KB，2–3 个页面后触发 HTTP 413 "Prompt is too long"；有团队因此 "completely ban all Playwright MCP tools"。
- **C14 playwright-mcp #1177**（2025-10-31，open）：Ant Design、Angular CDK 渲染到 body 下 overlay 的弹层**不在 snapshot 里**。【推断】规避办法是 `browser_evaluate` 或 CSS 选择器直接操作，依据是这两条路径不依赖 snapshot ref。搜索摘要称同源 iframe 会内联进 snapshot、跨源 iframe 要切 frame，出自 qaskills.sh 二手摘要，【未核实】。
- **C15 playwright-mcp #1479**（2026-03-21，closed）：恶意页面用 CSS 隐藏的指令仍会出现在 a11y tree 里，形成间接 prompt injection；建议把 snapshot 视为不可信输入。
- **C16 playwright-mcp #1495**（2026-03-30，closed）：`browser_run_code` 用的 `vm` 模块不是沙箱，`page.constructor.constructor('return process')()` 可拿到 `child_process`；与 prompt injection 结合即完整宿主机接管。
- **C17 microsoft/playwright PR #42691**（2026-09-12，closed 未 merge）：PR 想默认禁用 `browser_run_code_unsafe`，并把 extension 模式 CDP Relay 从 `0.0.0.0` 改绑 `127.0.0.1`。维护者以工具 "deliberately named `_unsafe`"、`WSServer.listen` 默认已绑 `localhost` 为由拒绝。【推断】vendor 立场是"命名即警示，用户自行 opt-out"，依据是拒绝理由本身。
- **C18 CVE-2025-9611**（NVD 发布 2026-01-07）：Playwright MCP 0.0.40 之前不校验 Origin，存在 DNS rebinding / CSRF 风险，访问恶意网页即可调用本地 MCP 工具；CVSS 7.2；缓解是升级到 ≥0.0.40、配置 `allowedHosts`、MCP 运行期间不浏览不可信站点。

---

## 5. 开源 MCP bridge 横评（Q3/Q4）

### 5.1 总表

Stars 与更新时间取自底稿的 `gh api` 读数：浏览器类 2026-09-28 00:11 UTC，内嵌/框架类 2026-09-28T00:14Z。"主会话抽查"指 §2 的复核。

| 项目 | 链接 | Stars（核验日期） | 最近更新 | Transport | 运行位置 | 页面感知方式 | iframe 支持 | dev-only gating | 安全要点 | 核验状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| Playwright MCP | https://github.com/microsoft/playwright-mcp | 37,629（2026-09-28） | commit 2026-09-25；v0.0.82（2026-09-18） | stdio 默认；`--port` 开 Streamable HTTP `/mcp` + SSE `/sse` | 外部进程，自启浏览器；`--cdp-endpoint` / `--extension` 可接已开浏览器 | a11y snapshot（带 ref）为主；screenshot；console；network | 支持（#106、#559、#1394 均 closed/completed） | 47 个工具需 `--caps` 开启 | README："**not** a security boundary"；`browser_run_code_unsafe` 默认开且 "RCE-equivalent"；`--allowed-origins` 不是安全边界；HTTP 模式校验 Host 防 rebinding，无 token【推断：http.ts 中只见 Host 校验】；0.0.40 前有 CVE-2025-9611（C18） | gh api 核验；主会话抽查一致 |
| Chrome DevTools MCP | https://github.com/ChromeDevTools/chrome-devtools-mcp | 52,671（2026-09-28） | commit 2026-09-25；v1.10.1（2026-09-23） | 仅 stdio | 外部进程，puppeteer 自启 Chrome；`--browserUrl`/`--wsEndpoint`/`--autoConnect` 接已开 Chrome | a11y text snapshot（带 uid）；screenshot；console（source-map 堆栈）；network；perf trace；heap snapshot | 支持，含 OOPIF（#186、#703 closed/completed）；iframe perf（#214）open | vision/screencast/memory/extensions/3p/webmcp/pwa 需 flag；`--slim` 只剩 3 个 | 默认发使用统计与 CrUX；`evaluate_script` 可执行任意 JS（`--javascriptEvaluation=false` 关闭）；`--allowedUrlPattern`（Chrome 149+）；开 remote debugging port 后本机任何程序都能控制浏览器 | gh api 核验；主会话抽查一致 |
| Browserbase MCP | https://github.com/browserbase/mcp-server-browserbase | 3,413（2026-09-28） | commit 2026-07-20；v3.0.0（2026-03-31） | stdio；Streamable HTTP（自托管 `--port` / 托管 `https://mcp.browserbase.com/mcp`） | 云端浏览器 | Stagehand 的 LLM `observe`/`extract`；无 screenshot 工具 | MCP 层未核验（Stagehand 自称支持嵌套 iframe） | `--experimental`（内容未核验） | **已归档**；托管版 Bearer API key；自托管 HTTP 无入站认证【推断：`src/transport.ts` 未见 Authorization 代码】 | gh api 核验（archived=true）；主会话抽查一致 |
| browser-use（MCP 模式） | https://github.com/browser-use/browser-use | 116,516（2026-09-28） | commit 2026-09-26；0.13.10（2026-09-04） | 仅 stdio（`--mcp` / `--cli-mcp`） | 本地 Chrome，默认有头 + 持久 profile | 带 index 的可交互元素列表；raw HTML；screenshot；可委托 LLM agent | 【推断】继承 `cross_origin_iframes: True`，依据是 MCP 复用同一 BrowserSession | 无 | `allowed_domains`；`--cli-mcp` 的 `browser_exec` 可执行任意 Python；有遥测，关闭方式未核验 | gh api 核验 |
| BrowserMCP | https://github.com/BrowserMCP/mcp | 7,135（2026-09-28；主会话读到 7,136） | 最后 commit 2025-04-24；npm 0.1.3 | stdio；server↔扩展走 WebSocket 9009 | 用户日常 Chrome（经扩展） | aria snapshot；screenshot；console | 不支持（#96 open） | 无 | WS 无鉴权；未指定 host【推断：依据源码 + `ws` 库默认行为，可能监听所有网卡，未实测】；启动时 kill 占用 9009 的进程 | gh api 核验；事实停更 |
| Puppeteer（参考实现） | https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer | 304（整个 servers-archived 仓库，2026-09-28） | `src/puppeteer` 最后 commit 2025-05-15 | 仅 stdio | 自启浏览器 | 无 snapshot，CSS selector 盲操作；screenshot；console resource | 【推断】不支持，依据是源码无 frame 处理 | 无 | **已归档**；README CAUTION："can access local files and local/internal IP addresses"；`puppeteer_evaluate` 任意 JS | gh api 核验 |
| Tauri bridge（tauri-plugin-mcp-bridge + @hypothesi/tauri-mcp-server） | https://github.com/hypothesi/mcp-server-tauri | 309（2026-09-28） | v0.13.0（2026-08-28） | stdio / 裸 WebSocket JSON | Rust 插件嵌在 app 进程内；MCP server 是外部 Node 进程 | 注入 JS 做结构快照；原生 WebView 截图 | 【推断】不支持，依据是 `dom-snapshot.js` grep 不到 `iframe` | 插件本身无门控，靠宿主 `#[cfg(debug_assertions)]` | 默认 **0.0.0.0**、无认证、不查 Origin（v0.13.0 仍如此）；`webview_execute_js` | gh api 核验；主会话抽查一致 |
| electron-mcp-server（amafjarkasi） | https://github.com/amafjarkasi/electron-mcp-server | 85（2026-09-28） | 2026-09-12；v1.5.0 | stdio / CDP | 外部进程 | CDP outerHTML、querySelectorAll、截图；无 a11y 树 | 【推断】OOPIF 可经 `targetId` 选中，同进程 iframe 不行 | 靠 app 是否开调试端口 | `cdp_command` 任意 CDP 无允许名单；有路径 allowed roots | gh api 核验 |
| electron-mcp-server（halilural） | https://github.com/halilural/electron-mcp-server | 71（2026-09-28） | 2026-08-06；v1.5.1 | stdio / CDP | 外部进程 | 注入 JS 汇总交互元素；CDP 截图 | 未发现 | README 建议 app 按 `NODE_ENV` 开调试端口 | 四档 `SECURITY_LEVEL`，唯一在 MCP 层对 eval 做风险评估 | gh api 核验 |
| circuit-electron | https://github.com/clharman/circuit-mcp | 59（2026-09-28） | 2026-02-07 | stdio / Playwright `_electron.launch` | 外部进程，自己拉起 app | Playwright a11y 快照 + ref | 【推断】只操作主 frame，依据是无 frame 工具 | 无 | `fs_read_file`/`fs_write_file` 路径无校验 | gh api 核验 |
| next-devtools-mcp | https://github.com/vercel/next-devtools-mcp | 823（2026-09-28） | 2026-09-15；package.json 0.4.1 | stdio / HTTP 调 `/_next/mcp` | 外部代理进程 | 自身不感知页面；`browser_eval` 只返回 agent-browser 安装说明 | 不适用 | 只能连 `next dev` | 带遥测 | gh api 核验；主会话抽查一致 |
| Next.js 内置 `/_next/mcp` | https://github.com/vercel/next.js （packages/next/src/server/mcp） | 142,797（next.js 仓库，2026-09-28） | 2026-09-28 | Streamable HTTP（无状态） | dev server 中间件 | 经 HMR 从已打开的浏览器会话拉错误和页面元数据；不截图、不做 DOM 快照 | 不适用 | 只在 hot-reloader 挂载；`experimental.mcpServer` 默认 true | 无 token；`blockCrossSiteDEV` 查 Origin，**不带 Origin 的请求放行** | gh api 核验 |
| nuxt-mcp-dev / vite-plugin-mcp | https://github.com/antfu/nuxt-mcp-dev | 911（2026-09-28） | 2026-03-01；v0.3.2 | SSE（`/__mcp/sse`） | dev server 中间件 | 不感知页面，只读构建期信息 | 不适用 | `configureServer` 只在 `vite serve` 运行 | 无 token；【推断】在 Vite cors/host 校验之后，依据是 Vite 源码中间件顺序；启动时会**自动改写** `.mcp.json` 等客户端配置 | gh api 核验 |
| vite-plugin-vue-mcp | https://github.com/webfansplz/vite-plugin-vue-mcp | 580（2026-09-28） | **2025-04-20** 后无推送 | SSE / Vite HMR ws RPC | dev server 中间件 + 页面 overlay | Vue devtools-kit 组件树、状态、路由、Pinia | 未发现 | `apply: 'serve'` | 能改组件状态（`edit-component-state`） | gh api 核验；停更 |
| Storybook `@storybook/addon-mcp` | https://github.com/storybookjs/storybook （code/addons/mcp） | 91,162（storybook 仓库，2026-09-28） | 2026-09-27；10.6 起并入主仓库 | Streamable HTTP，`POST /mcp` | dev server 中间件 | story 索引、组件清单、跑 Vitest 与 a11y；不操作 DOM | story 渲染在 iframe 里，但工具不操作 DOM | `experimental_devServer`，static 构建不可用（V2） | 本地无认证；Origin/Host 检查未核验 | gh api 核验 |

**读表要点**：
- 能在 DOM/a11y 层看到 UI 并支持 iframe 的只有 playwright-mcp 和 chrome-devtools-mcp（browser-use 为【推断】）。内嵌型里 Tauri 不进 iframe，Next/Nuxt/Storybook 不看 DOM。
- dev-only 门控有三种形态：编译期（Tauri `cfg`，靠宿主写对）、dev server 生命周期（Next、Vite、Storybook，生产构建里没有这段代码路径）、运行时开关（Electron 按 `NODE_ENV` 开调试端口，最容易误开）。来源：内嵌 bridge 底稿 §6 的横向归纳。
- 认证普遍缺失：六个内嵌/框架 MCP 实现中只有 Storybook 在 composition 场景有 Bearer；Tauri 默认 0.0.0.0 且不查 Origin，暴露面最大。

### 5.2 工作原理

**Playwright MCP**（R1）
- 主通道是 `browser_snapshot` 输出的 ARIA 树，每个元素带 ref；交互工具的 `target` 可以用 ref，也可以用唯一 selector。README："No vision models needed"。
- 默认用持久 profile（`~/Library/Caches/ms-playwright/mcp-{channel}-{workspace-hash}`）；`--isolated` 用内存 profile；`--extension` 经 "Playwright Extension" 接已开的 Chrome/Edge 并复用登录态。
- 文件访问默认限制在 workspace roots 内并禁止 `file://`；`--secrets <dotenv>` 会把工具响应里匹配到的明文替换掉；默认会暴露页面经 WebMCP API 注册的工具，`--no-webmcp` 关闭。
- README 现在主动推荐 coding agent 改用 [Playwright CLI + Skills](https://github.com/microsoft/playwright-cli)，理由是更省 token。

**Chrome DevTools MCP**（R2）
- 产品名 "Chrome DevTools for agents"。puppeteer 驱动 Chrome，复用 DevTools frontend 分析 performance trace，另提供 CLI。
- `take_snapshot` 生成带 uid 的 a11y 文本快照；`role="presentation"` 的 iframe 要 `verbose=true` 才会出现（#703 维护者说明）。
- `--pageIdRouting` 默认开启，页面类工具都要传 `pageId`，便于多 agent 并发。
- 只支持 stdio，依据是 `src/bin/chrome-devtools-mcp-main.ts` 里只有 `new StdioServerTransport()`。

**Browserbase MCP**（R3）
- 已归档，README 称其为托管服务 `https://mcp.browserbase.com/mcp` 的自托管版本。浏览器跑在 Browserbase 云上，`act`/`observe`/`extract` 交给 Stagehand 用自然语言执行，默认模型 `google/gemini-2.5-flash-lite`。MCP 层不暴露 raw snapshot。

**browser-use（MCP 模式）**（R5）
- 本体是 Python agent 库。`browser-use --mcp` 提供 16 个工具，其中 `retry_with_browser_use_agent` 会把任务交给内置 LLM agent；`--cli-mcp` 只有 2 个工具，`browser_exec` 执行任意 Python（预置 `js()`、`cdp()`）。
- 页面感知是带 index 的可交互元素列表，【推断】不是 a11y snapshot 路线，依据是工具描述和 index 机制。

**BrowserMCP**（R6）
- MCP server + Chrome 扩展，README 称 "adapted from the Playwright MCP server"，改为驱动用户自己的浏览器以复用登录态。
- 公开仓库 "currently cannot yet be built on its own"，工具定义在私有 monorepo 里，工具名只能从 npm bundle 读出。
- 最后 commit 2025-04-24，151 个 open issues（2026-09-28 读取）。

**Puppeteer 参考实现**（R7）
- MCP 早期官方参考实现，已归档。没有 snapshot 工具，交互靠 CSS selector 盲操作；截图同时存为 `screenshot://<name>` resource，console 以 `console://logs` resource 提供。危险启动参数（`--no-sandbox` 等）默认抛错，需 `allowDangerous: true`。

**Tauri bridge**（R8）
- Rust 插件嵌在 app 进程内，开一个 WebSocket；外部 Node MCP server 经 stdio 接 agent、经 WS 接插件。之所以要嵌进 app，是因为 Tauri 的 webview 没有 CDP 可接（姊妹文档 Part B 的逐跳拆解，见 [paper-one 文档](paper-one-cli-and-mcp-bridge.md)）。
- v0.13.0 增量：工具从 20 降到 19（`webview_get_styles` 并入 `webview_find_element`）；`ipc_execute_command` 改经 webview，受 capability ACL 约束；页面刷新或 HMR 后重新注入 `__MCP__` helper（https://github.com/hypothesi/mcp-server-tauri/releases/tag/v0.13.0）。
- 风险点在 v0.13.0 上未变：`config.rs` 默认 `bind_address: "0.0.0.0"`；`websocket.rs:685` 为 `accept_async(stream)`，无认证、不查 Origin；插件 `lib.rs` grep 不到 `debug_assertions`。

**Electron 系**（R9–R11）
- 没有找到"嵌在 app 进程里"的主流 Electron MCP bridge。三者都是外部进程：attach 模式经 `--remote-debugging-port` 走 CDP（amafjarkasi、halilural），launch 模式用 Playwright `_electron.launch` 拉新实例（circuit）。所以 dev-only 取决于 app 在什么条件下开调试端口。
- amafjarkasi 的输入走 CDP `Input.dispatchMouseEvent`，是浏览器层真实输入事件，不是合成 DOM 事件。

**next-devtools-mcp 与 `/_next/mcp`**（R12、R13）
- next-devtools-mcp 是薄代理：`nextjs_index` 发现本机 `next dev` 端口，向 `/_next/mcp` 发 `tools/list`；`nextjs_call` 转发 `tools/call`。2026-06-24 提交 #145 后 `browser_eval` 不再内嵌 Playwright MCP。
- Next 官方文档 `docs/01-app/02-guides/mcp.mdx` 仍写 "Browser Testing: Playwright MCP integration"，与源码**不一致**；以源码为准，因为源码是行为的定义处，文档落后于 #145。
- `/_next/mcp` 由 `get-mcp-middleware.ts` 拦截，每个请求新建无状态 `StreamableHTTPServerTransport`。`get_errors`、`get_page_metadata` 经 `sendHmrMessage` 向**已打开该页面的浏览器会话**取数据，所以浏览器里必须开着页面。
- 挂载点 `server/dev/hot-reloader-turbopack.ts:1285`，只在 `next dev` 存在；【推断】浏览器里的跨源页面会被 `blockCrossSiteDEV` 挡住，但本机任意非浏览器进程都能调用，依据是不带 Origin 的请求直接放行。

**Vite / Nuxt / Storybook 插件**（R14–R16）
- nuxt-mcp-dev 在 `configureServer` 挂 `GET /__mcp/sse` 和 `POST /__mcp/messages`，用的是已被 Streamable HTTP 取代的 HTTP+SSE；只读 Vite config、模块图和 Nuxt 元数据。
- vite-plugin-vue-mcp 是这一节唯一真正观察运行中 UI（组件层）的 Vite 插件：经 HMR ws 建 birpc RPC，请求页面里的 Vue devtools-kit，但已停更。
- Storybook addon-mcp 在 dev server 的 express 上注册 `POST /mcp`，用 `@tmcp/transport-http`；官方文档写明 "requires Storybook's dev server… not available with static or published Storybooks"（V2）。

### 5.3 相关但非 MCP

| 项目 | 为什么不算 MCP bridge |
|---|---|
| Stagehand（R4，25,420★） | TypeScript/Python/Go 的浏览器自动化 SDK（`act`/`observe`/`extract`）。README 提到的 MCP 是引导去用 Browserbase 托管 MCP；MCP 形态只存在于已归档的 R3 和托管服务。 |
| gstack browse（R17） | CLI + 常驻 Bun daemon，`POST /command` 发 HTTP JSON；`src/` 里 grep 不到 `modelcontextprotocol` 或 `McpServer`。以 Skill 形式由 agent 经 Bash 调用。 |
| Playwright CLI（C4） | Microsoft 官方的 CLI + Skills 形态，snapshot 落盘到 `.playwright-cli/`，定位就是替代 MCP 给 coding agent 用。 |
| WebMCP（webmachinelearning/webmcp 4,340★ 等） | W3C 提案的浏览器 API（`navigator.modelContext`），由页面自己声明工具；本身不是 MCP transport，要 MCP-B 扩展或 polyfill 桥接；面向生产用户能力，不是 dev-only 调试 bridge。playwright-mcp 默认会收集页面注册的 WebMCP 工具（R1）。 |
| agent-browser（vercel-labs） | CLI，不是 MCP；next-devtools-mcp 的 `browser_eval` 现在只返回它的安装说明。本次未深入。 |
| Vercel MCP（V1） | 是 MCP，但属于云平台运维（项目、部署、日志、Toolbar 评论），不观察 UI，工具名未核验。 |
| nuxt-modules/mcp-toolkit、unplugin-mcp、vite-plugin-mcp-client-tools、react-devtools-mcp | 前两者用于构建生产 MCP server 或提供构建上下文；后两者确实观察 UI，但 star 极少（17★、2★/1★），只记一笔。 |

**gstack browse 工作原理**（本仓库在用，所以单列）

```
agent ─Bash─▶ browse CLI ──HTTP POST /command (Bearer)──▶ Bun.serve daemon @127.0.0.1:<随机 10000–60000>
                 │ 读 <project>/.gstack/browse.json（port+token，0600）         │
                 └ 首次调用自动拉起 daemon（约 3s），之后每条命令约 100ms      ▼
                                                                 Playwright chromium.launch / launchPersistentContext
```

- **驱动方式**：daemon 用 Playwright（gstack `package.json` 中 `playwright ^1.58.2`）；raw CDP 只用于 `cdp-inspector.ts` 与允许名单内的 `cdp` 命令。cookie、tab、登录态跨调用保留；空闲 30 分钟退出；日志写在 `.gstack/browse-{console,network,dialog}.log`。
- **页面感知**：`snapshot` 基于 ARIA 树生成 `@eN` ref，`-C` 另扫 cursor:pointer/onclick 的 div 生成 `@cN`，`-D` 做 diff，`-a` 出带标注的截图。
- **iframe**：`frame <sel|@ref|--name n|--url pattern|main>`（`meta-commands.ts:1001-1033`）切换上下文后，snapshot 与读写命令都在该 frame 里执行（`snapshot.ts:146`、`read-commands.ts:219`、`write-commands.ts:140`）；frame detach 时自动回退（`tab-session.ts:159`）；快照加一行头 `[Context: iframe src="..."]`（`snapshot.ts:589-592`）。以上路径均相对 `~/.claude/skills/gstack/browse/src/`。
- **安全**：listener 全部绑 `127.0.0.1`（`server.ts:2360/2995/3077/3118`）；Bearer token 来自 `crypto.randomUUID()`，状态文件 `0o600`（`server.ts:3017`），缺 token 返回 401（`server.ts:2672-2679`）；token 分 read/write/admin/meta/control scope（`token-registry.ts:75`）；`cdp-allowlist.ts` 只列约 23 个方法，`Runtime.evaluate`、`Target.*`、`Fetch.*` 不在其中；导入 cookie 后 `js`/`eval` 只能在对应域名执行（`read-commands.ts:185-200`）；`text`/`html`/`snapshot` 输出包在 `BEGIN/END UNTRUSTED EXTERNAL CONTENT` 标记里。
- **已知缺口**：`/health` 在 headed 模式或 Origin 以 `chrome-extension://` 开头时会返回 root token（`server.ts:1780-1787`），源码 TODO 承认 headed 模式下任何 localhost 调用方都能拿到（`server.ts:2796-2798` 附近）。【推断】网页因 CORS 读不到，本机非浏览器进程可以，依据是 daemon 未设 `Access-Control-Allow-Origin`。

---

## 6. 工具清单（Q5）

类别统一为：导航、交互、读取状态、截图、console/network、执行 JS、断言、会话管理。大工具集只列与本仓库最相关的行，完整列表见来源链接。

### 6.1 Playwright MCP 与 Chrome DevTools MCP

**Playwright MCP**：共 72 个工具（25 个默认开启，47 个需 `--caps`），下表列 24 行（含 25 个工具）。完整列表：https://github.com/microsoft/playwright-mcp/blob/main/README.md （"Tools" 一节）。

**Chrome DevTools MCP**：共 59 个工具（`--slim` 模式只有 `navigate`、`evaluate`、`screenshot` 3 个），下表列 23 行（含 24 个工具），关键参数省略几乎所有工具都有的 `pageId` 与 `includeSnapshot?`。完整列表：https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md 。

| Bridge | Tool 名 | 类别 | 作用 | 关键参数 | 来源链接 |
|---|---|---|---|---|---|
| playwright-mcp | `browser_navigate` | 导航 | 打开 URL | url | https://github.com/microsoft/playwright-mcp/blob/main/README.md |
| playwright-mcp | `browser_navigate_back` | 导航 | 后退 | — | 同上 |
| playwright-mcp | `browser_click` | 交互 | 点击 | target, element?, doubleClick?, button?, modifiers? | 同上 |
| playwright-mcp | `browser_type` | 交互 | 输入文本 | target, text, submit?, slowly? | 同上 |
| playwright-mcp | `browser_press_key` | 交互 | 按键 | key | 同上 |
| playwright-mcp | `browser_hover` | 交互 | 悬停 | target | 同上 |
| playwright-mcp | `browser_drag` | 交互 | 两元素间拖放 | startTarget, endTarget | 同上 |
| playwright-mcp | `browser_handle_dialog` | 交互 | 处理 alert/confirm/prompt | accept, promptText? | 同上 |
| playwright-mcp | `browser_mouse_drag_xy` | 交互 | 按坐标拖拽（`--caps=vision`） | startX, startY, endX, endY | 同上 |
| playwright-mcp | `browser_snapshot` | 读取状态 | a11y 快照 | target?, filename?, depth?, boxes? | 同上 |
| playwright-mcp | `browser_find` | 读取状态 | 在 snapshot 里搜文本或正则 | text? / regex? | 同上 |
| playwright-mcp | `browser_localstorage_get` | 读取状态 | 读 localStorage 条目（`--caps=storage`） | key | 同上 |
| playwright-mcp | `browser_emulate_media` | 读取状态 | 模拟 colorScheme、reducedMotion 等 | colorScheme?, reducedMotion?, … | 同上 |
| playwright-mcp | `browser_take_screenshot` | 截图 | 页面或元素截图 | target?, type?, filename?, fullPage?, scale | 同上 |
| playwright-mcp | `browser_console_messages` | console/network | 读 console | level, all?, filename? | 同上 |
| playwright-mcp | `browser_network_requests` | console/network | 请求列表 | static, filter?, filename? | 同上 |
| playwright-mcp | `browser_route` | console/network | mock 请求（`--caps=network`） | pattern, status?, body?, … | 同上 |
| playwright-mcp | `browser_evaluate` | 执行 JS | 在页面或元素上执行 JS | function, target?, filename? | 同上 |
| playwright-mcp | `browser_run_code_unsafe` | 执行 JS | 在 **server 进程**执行 Playwright 代码，等同 RCE，默认开启 | code? / filename? | 同上 |
| playwright-mcp | `browser_wait_for` | 断言 | 等文本出现/消失或固定时间 | time?, text?, textGone? | 同上 |
| playwright-mcp | `browser_verify_text_visible` | 断言 | 断言文本可见（`--caps=testing`） | text | 同上 |
| playwright-mcp | `browser_generate_locator` | 断言 | 为元素生成测试 locator（`--caps=testing`） | target | 同上 |
| playwright-mcp | `browser_tabs` | 会话管理 | 列出、新建、关闭、切换标签页 | action, index?, url? | 同上 |
| playwright-mcp | `browser_start_tracing` / `browser_stop_tracing` | 会话管理 | 开始/结束 trace（`--caps=devtools`） | — | 同上 |
| chrome-devtools-mcp | `navigate_page` | 导航 | 打开 URL，或后退/前进/刷新 | type, url?, ignoreCache?, initScript?, timeout? | https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md |
| chrome-devtools-mcp | `new_page` | 导航 | 新开标签页 | url, background?, isolatedContext?, timeout? | 同上 |
| chrome-devtools-mcp | `click` | 交互 | 点击元素 | uid, dblClick? | 同上 |
| chrome-devtools-mcp | `fill` | 交互 | 填写输入框或选 select 选项 | uid, value | 同上 |
| chrome-devtools-mcp | `type_text` | 交互 | 向焦点输入框键入 | text, submitKey? | 同上 |
| chrome-devtools-mcp | `press_key` | 交互 | 按键或组合键 | key | 同上 |
| chrome-devtools-mcp | `drag` | 交互 | 元素间拖拽 | from_uid, to_uid | 同上 |
| chrome-devtools-mcp | `handle_dialog` | 交互 | 处理对话框 | action, promptText? | 同上 |
| chrome-devtools-mcp | `take_snapshot` | 读取状态 | 带 uid 的 a11y 文本快照 | verbose?, filePath? | 同上 |
| chrome-devtools-mcp | `get_css_styles` | 读取状态 | 元素匹配的 CSS 规则与层叠 | uid, pageSize? | 同上 |
| chrome-devtools-mcp | `emulate` | 读取状态 | 模拟配色、CPU 降速、网络、viewport 等 | colorScheme?, cpuThrottlingRate?, networkConditions?, viewport?, … | 同上 |
| chrome-devtools-mcp | `take_screenshot` | 截图 | 页面或元素截图 | uid?, fullPage?, format?, quality?, filePath? | 同上 |
| chrome-devtools-mcp | `list_console_messages` | console/network | console 列表 | types?, pageSize?, includePreservedMessages?, includeStackTraces? | 同上 |
| chrome-devtools-mcp | `get_console_message` | console/network | 按 id 读单条 console | msgid | 同上 |
| chrome-devtools-mcp | `list_network_requests` | console/network | 请求列表 | pageSize?, resourceTypes?, includePreservedRequests? | 同上 |
| chrome-devtools-mcp | `get_network_request` | console/network | 单个请求详情 | reqid?, requestFilePath?, responseFilePath? | 同上 |
| chrome-devtools-mcp | `performance_start_trace` / `performance_stop_trace` | console/network | 录 performance trace（Core Web Vitals） | reload?, autoStop?, filePath? | 同上 |
| chrome-devtools-mcp | `evaluate_script` | 执行 JS | 在页面执行 JS 函数 | function, args?, dialogAction?, filePath?, waitForStableDom? | 同上 |
| chrome-devtools-mcp | `wait_for` | 断言 | 等文本出现 | text[], timeout? | 同上 |
| chrome-devtools-mcp | `lighthouse_audit` | 断言 | Lighthouse 审计（不含 performance） | device?, mode?, outputDirPath? | 同上 |
| chrome-devtools-mcp | `list_pages` | 会话管理 | 列出页面 | — | 同上 |
| chrome-devtools-mcp | `select_page` | 会话管理 | 选择后续调用的目标页面 | bringToFront? | 同上 |
| chrome-devtools-mcp | `resize_page` | 会话管理 | 调整页面尺寸 | width, height | 同上 |

### 6.2 Tauri bridge、Next `/_next/mcp`、gstack browse

**Tauri bridge v0.13.0**：19 个工具，全列。工具名出处 `packages/mcp-server/src/tools-registry.ts@v0.13.0`（https://github.com/hypothesi/mcp-server-tauri ）；参数取自姊妹文档 [paper-one 文档](paper-one-cli-and-mcp-bridge.md) Part B 的 v0.12.0 工具表，再叠加 v0.13.0 release notes 的增量（https://github.com/hypothesi/mcp-server-tauri/releases/tag/v0.13.0 ）。所有 `webview_*` 工具还接受 `windowId?`、`appIdentifier?`。

**Next.js `/_next/mcp`**：9 个工具，全列。出处 https://github.com/vercel/next.js/tree/canary/packages/next/src/server/mcp/tools 。

**gstack browse**：**非 MCP**，是 CLI 命令集，下表按类别列与本仓库相关的命令。完整列表见本机 `~/.claude/skills/gstack/browse/SKILL.md` 的 "Full Command List"（上游 https://github.com/garrytan/gstack ）。gstack 的"关键参数"只写底稿里出现过的形式，其余标"—"。

| Bridge | Tool 名 | 类别 | 作用 | 关键参数 | 来源链接 |
|---|---|---|---|---|---|
| Tauri | `driver_session` | 会话管理 | 开始/结束/查询与 app 的会话 | action=start/stop/status, host?, port?, appIdentifier? | https://github.com/hypothesi/mcp-server-tauri |
| Tauri | `get_setup_instructions` | 会话管理 | 返回接入说明 | — | 同上 |
| Tauri | `list_devices` | 会话管理 | 列出设备（移动端） | — | 同上 |
| Tauri | `manage_window` | 会话管理 | 窗口 list/info/resize；v0.13 新增 focus/minimize/maximize | action, windowId?, width?, height?, logical | 同上 |
| Tauri | `webview_interact` | 交互 | click/double-click/long-press/scroll/swipe/focus；v0.13 新增 hover、right-click，多匹配时必须传 `nth` | action, selector?, x?, y?, nth? | 同上 |
| Tauri | `webview_keyboard` | 交互 | type/press/down/up | action, selector?, text?, key?, modifiers? | 同上 |
| Tauri | `webview_select_element` | 交互 | 让用户在页面上点选元素【推断：按工具名与 timeout 参数】 | timeout | 同上 |
| Tauri | `webview_find_element` | 读取状态 | 查元素；v0.13 并入 `webview_get_styles`，返回 ref、bbox、可见性 | selector, strategy(css/xpath/text)?, nth?, limit?, properties?, visibleOnly?, includeHtml? | 同上 |
| Tauri | `webview_dom_snapshot` | 读取状态 | a11y 或结构快照（注入 `dom-snapshot.js`） | type=accessibility/structure, selector? | 同上 |
| Tauri | `webview_get_pointed_element` | 读取状态 | 读取用户指向的元素【推断：按工具名】 | — | 同上 |
| Tauri | `ipc_get_backend_state` | 读取状态 | 读后端状态【推断：按工具名】 | appIdentifier? | 同上 |
| Tauri | `webview_screenshot` | 截图 | 原生 WebView 截图，失败回退 html2canvas | format, quality, filePath?, maxWidth? | 同上 |
| Tauri | `read_logs` | console/network | 读 console/android/ios/system 日志 | source, lines, filter?, since? | 同上 |
| Tauri | `ipc_monitor` | console/network | 开关 IPC 监听（Web 应用的对应物是 fetch/network） | action=start/stop | 同上 |
| Tauri | `ipc_get_captured` | console/network | 读取捕获的 IPC 调用 | filter? | 同上 |
| Tauri | `ipc_execute_command` | 执行 JS | 调用 app IPC 命令；v0.13 起经 webview，受 capability ACL 约束 | command, args? | 同上 |
| Tauri | `ipc_emit_event` | 执行 JS | 派发 IPC 事件 | eventName, payload | 同上 |
| Tauri | `webview_execute_js` | 执行 JS | 在顶层文档执行 JS | script, args? | 同上 |
| Tauri | `webview_wait_for` | 断言 | 等 selector/text/ipc-event | type, value, timeout | 同上 |
| Next `/_next/mcp` | `get_errors` | console/network | 配置错误、浏览器运行时错误、构建错误（stack 已 source map） | — | https://github.com/vercel/next.js/tree/canary/packages/next/src/server/mcp/tools |
| Next `/_next/mcp` | `get_logs` | console/network | 返回 dev 日志文件路径（含浏览器 console 与 server 输出） | — | 同上 |
| Next `/_next/mcp` | `get_page_metadata` | 读取状态 | 当前页面涉及的 route、layout、组件（来自活跃浏览器会话） | — | 同上 |
| Next `/_next/mcp` | `get_project_metadata` | 读取状态 | 项目路径、dev server URL | — | 同上 |
| Next `/_next/mcp` | `get_routes` | 读取状态 | 扫描文件系统得到路由 | routerType? | 同上 |
| Next `/_next/mcp` | `get_server_action_by_id` | 读取状态 | 按 Server Action ID 定位文件与导出 | actionId | 同上 |
| Next `/_next/mcp` | `get_compilation_issues` | 断言 | 全项目编译问题（仅 Turbopack） | — | 同上 |
| Next `/_next/mcp` | `compile_route` | 会话管理 | 按需编译路由（仅 Turbopack） | routeSpecifier?, path? | 同上 |
| Next `/_next/mcp` | `get_request_insights` | console/network | App Router 请求 span 记录；【推断】需开 `experimental.requestInsights` | requestId?, htmlRequestId? | 同上 |
| gstack（非 MCP） | `goto` / `back` / `forward` / `reload` / `url` | 导航 | 页面导航 | — | 本机 `~/.claude/skills/gstack/browse/SKILL.md` |
| gstack（非 MCP） | `click` / `fill` / `type` / `press` / `hover` / `select` / `scroll` / `dialog-accept` | 交互 | 页面交互，目标可用 snapshot 的 `@eN` ref | — | 同上 |
| gstack（非 MCP） | `frame` | 会话管理 | 切进 iframe 或回到主 frame | `<sel\|@ref\|--name n\|--url pattern\|main>` | 同上；`meta-commands.ts:1001-1033` |
| gstack（非 MCP） | `snapshot` | 读取状态 | ARIA 快照并生成 `@eN`/`@cN` ref | `-i -c -d N -s sel -D -a -o path -C -H json` | 同上 |
| gstack（非 MCP） | `text` / `html` / `accessibility` / `attrs` / `is` / `storage` / `css` / `inspect` | 读取状态 | 读文本、HTML、a11y、属性、状态、存储、样式、CDP 级联 | — | 同上 |
| gstack（非 MCP） | `screenshot` / `diff` / `responsive` / `pdf` | 截图 | 截图、对比、多尺寸 | — | 同上 |
| gstack（非 MCP） | `console` / `network` / `perf` | console/network | 读 console、网络、性能 | — | 同上 |
| gstack（非 MCP） | `js` / `eval` | 执行 JS | 在当前页或当前 frame 执行 JS；导入 cookie 后受域名限制 | —（`--out` 算写操作） | 同上；`read-commands.ts:185-200` |
| gstack（非 MCP） | `cdp` | 执行 JS | 执行允许名单内的约 23 个 CDP 方法 | `<Domain.method>` | 同上；`cdp-allowlist.ts` |
| gstack（非 MCP） | `wait` | 断言 | 等待条件 | — | 同上 |
| gstack（非 MCP） | `tabs` / `newtab` / `tab` / `closetab` / `status` / `restart` / `stop` | 会话管理 | 标签页与 daemon 管理 | — | 同上 |

**覆盖情况**：本节覆盖 5 个 bridge（playwright-mcp、chrome-devtools-mcp、Tauri、Next `/_next/mcp`、gstack browse），其中 gstack 是非 MCP。其余项目的工具表见底稿对应链接：Browserbase 6 个（R3 README）、browser-use 16+2 个（`browser_use/mcp/server.py`、`cli_mcp.py`）、BrowserMCP 12 个（npm bundle 0.1.3）、Puppeteer 7 个（R7 README）、amafjarkasi 36 个、halilural 4 个、circuit 32 个、next-devtools-mcp 4 个、nuxt-mcp-dev 7+1 个、vue-mcp 7 个、Storybook 8 组。

---

## 7. 最佳实践汇总（Q6）

### 7.1 共识

1. **给 agent 一个它能自己跑的检查，UI 改动要在真实浏览器里自验**，出示截图或测试输出作证据，而不是口头宣布完成。〔O3、O14、C1、C5、C6、C9〕
2. **UI 断言要沉淀成可重复的测试**：探索会话生成 `@playwright/test` 用例，约束为 role-based locator + auto-retry assertion、不加硬 timeout，并让 agent 跑到绿。〔C5；O3 的 "give Claude a check it can run"〕
3. **a11y snapshot 作交互主通道**，比纯 screenshot 更确定。〔C4、C9、C12、O18（Microsoft 描述）〕
4. **token 成本主要来自 snapshot 在历史里的累积**；大页面几步就会撑爆 context。〔C7、C11、C13；O1 的 25,000 token 默认上限〕
5. **对 coding agent，CLI/Skill + 结果落盘通常比常驻 MCP 更省 token**，vendor 也认可。〔C4、C7、C10、C11；C3 的 `--slim` 与 CLI；O3："CLI tools are the most context-efficient way to interact with external services"〕
6. **MCP 仍适合探索式任务、从零生成测试、需要持久状态的长流程**。〔C4、C5、C10〕
7. **不用的 server 要移除，浏览器工具不要默认常开**。〔O2、O5〕
8. **生成与评估分离**，evaluator 要调成怀疑型，并事先约定 "done" 的定义。〔O3、O15〕
9. **读 console 要带着模式去找**，不要全量拉取。〔O5〕
10. **页面内容是不可信输入**：snapshot 可携带间接 prompt injection，加上可执行代码的工具即升级为 RCE 或外泄。〔O17、C3、C15、C16、C18；gstack 的 UNTRUSTED 标记（R17）〕
11. **本地监听端口不能默认视为安全**：要 Origin/Host 校验、用户授权、隔离 profile。〔C2、C3、C17、C18；Tauri 反例（R8）〕
12. **固定 MCP 包版本**，`@latest` 会在会话中途让工具失效。〔C9〕
13. **snapshot 不完整**：portal/overlay、原生对话框、部分 iframe 会让 agent 看漏。〔C14、O5、O14；BrowserMCP #96（R6）〕
14. **截图与 snapshot 抓的是不同类的 bug**：布局、z-index、canvas 只有截图或 trace 看得到。〔C12 评论、C1〕

### 7.2 分歧

| 议题 | 一方 | 另一方 | 本文判断 |
|---|---|---|---|
| MCP 还是 CLI | 单人 coding agent 应改用 CLI 或自写脚本〔C7、C10、C11；C8 中 badlogic、cstrahan〕 | MCP 的价值在标准化分发、凭据边界、跨环境一致〔C8 中 lsaferite、chowfi〕；vendor 两头都保留〔C3、C4〕 | 本仓库是单人本地开发，交互驱动选 CLI（gstack）；MCP 作为可选备选。【推断：依据是 §9 的现状与 C4 的场景划分】 |
| snapshot 与 screenshot 哪个省 token | snapshot 便宜：120–400 vs 约 1,500 tokens〔C9、C12〕 | 复杂页面整页 snapshot 反而更贵〔C11；"贵 5.5 倍"为搜索摘要，【未核实】〕；O16 称 screenshot 交互更省 token | 口径不同：前者是单元素，后者是复杂页面加历史累积。我更信 C11/C13 的整页口径，因为 C13 是真实用户在 issue 里报的 413 错误，而 C9 自己给的是单元素量级。 |
| 能否省掉 screenshot | 只用 snapshot〔C12 正文〕 | 两通道并存〔C12 评论、C1〕 | 并存；epub.js 的分页排版正是布局类问题。 |
| 危险工具默认开还是关 | 默认禁用 `browser_run_code_unsafe`、收紧绑定〔C16、C17 PR〕 | 命名即警示，拒绝改默认〔C17 维护者〕；只补文档〔C15〕 | 用户侧自行约束：若采用 playwright-mcp，按 §9 备选 B 处理。 |
| snapshot 内联返回还是只给文件引用 | 落盘或按需返回〔C4、C13〕 | action 响应内联 snapshot〔issue #1639，未抓取，【未核实】〕 | 【推断】是往返次数与 context 的权衡，依据是两方各自的诉求。 |
| 是否连接用户真实的已登录浏览器 | 方便〔C2 autoConnect、C7 复制 profile；O5 Claude in Chrome 共享登录态〕 | 不暴露敏感信息、防注入〔C3、C15；O6 "still risky"〕 | 本仓库无账号体系（`src/reader3_app/web/server.py:134-135`），不需要登录态，没有理由连真实浏览器。 |
| DOM 交互还是截图交互 | DOM 交互快但耗 token〔O16〕 | 截图交互慢但省 token〔O16〕 | 与上面 snapshot/screenshot 的分歧同源，未找到官方论述针对 Claude Code 给出建议（§3.5）。 |

---

## 8. 与 paper-one 文档的对照

[paper-one 文档](paper-one-cli-and-mcp-bridge.md) 分析的是 Tauri app 的内嵌 bridge。Tauri 的 webview 没有 CDP 可接，所以必须把 bridge 编进 app；reader3-pro 是跑在 127.0.0.1:8123 的普通 Web 应用（`src/reader3_app/web/server.py:1072-1073`），任何 CDP/Playwright 工具都能直接连上。下面按仓库现状底稿 §8 逐条对照；行号均指 `docs/references/paper-one-cli-and-mcp-bridge.md`。

### 8.1 仍然成立的结论

| paper-one 的结论 | 在 reader3-pro 的对应物 |
|---|---|
| "注册门控 vs 编译门控"要分开看（`:317-323`） | 问题变成：dev 路由、注入脚本、debug getter 会不会进 wheel 和生产模板，挂载与授权是否在同一开关下。Part C 的四条（同开关、绑 127.0.0.1、Origin/token 校验、contract 测试断言生产下 404，`:490-494`）可以直接沿用；最后一条可由 `tests/contract/routes.snapshot` 承接（`docs/adr/0008-tech-stack-boundary.md:13`）。 |
| 逐跳架构拆解（`:337-383`） | 仍是 MCP host → stdio → MCP server → 页面，只是中间跳从自建 WS 变成 CDP 或 Playwright。 |
| 交互保真度：合成 DOM 事件 vs OS 级输入（`:393-394`） | 与本仓库现有取舍直接对应：`select_in_frame` 用程序化 Range + 合成 `mouseup` 代替真实拖选，理由是"拖选在 CI 上是头号 flaky 源"（`tests/e2e/helpers.py:331-336`）。 |
| 截图、DOM 快照、日志、网络监控的能力清单（`:390-422`） | 直接作为 §9 fit-gap 表的行。 |
| 端口选择与漂移风险（`:331-335,474-476`） | 本仓库端口解析已"非法即报错、不回落"（`src/reader3_app/web/server.py:1086-1099`），思路相同。 |
| 浏览器可跨源连上无 Origin 校验的本地 WS（`:472`） | 任何新增本地控制面都要回答同一个问题。本仓库 HTTP 面已有 Host 白名单、可选 token、改动型方法的 Origin 校验三道闸（`src/reader3_app/web/server.py:238-296`），新控制面不能低于这个水位。 |
| "等待即断言"（`:449-450,495`） | 与 Playwright 自动等待、`reader_frame` 的"先等正文再断 URL"同构（`tests/e2e/helpers.py:194-218`）。 |
| Part C："Reader3 Pro 是 Web 应用，Playwright 已经能直接驱动 DOM，**不需要**类似 MCP bridge 的东西"（`:490`） | 本次调研的证据支持这一结论，见 §9.2 的推荐方案。 |

### 8.2 不再成立或不适用的部分

| paper-one 的内容 | 为什么不适用 |
|---|---|
| Cargo feature / `cfg(debug_assertions)` 门控、release 二进制是否链接 crate（`:289-329,467-469`） | Python 与静态 JS 没有编译期裁剪。对应手段只有运行时开关，或不打包进 wheel（`scripts/check_wheel_contents.py`）。 |
| Tauri capability 与 ACL（`:319-325`）、`__TAURI__.core.invoke` 的 IPC 监控（`:395,442,473`）、`ipc_*` 工具（`:417-421`） | Web 应用没有 IPC 层。对应物是 `fetch` 与 SSE，由 Playwright network 事件或 init-script fetch 台账覆盖。 |
| 原生截图 API（WKWebView takeSnapshot 等，`:391`）、`manage_window`、`list_devices` | 浏览器里由 CDP 截图取代，没有窗口和移动设备维度。 |
| WKWebView `evaluateJavaScript` 与异步脚本回传的 ACL 依赖（`:385-388`） | CDP `Runtime.evaluate` 原生支持 await。 |
| 多实例靠两台机器 + ssh 隧道（`:452-458`） | 本仓库用 `READER3_BOOKS_DIR` + `--port` 子进程即可单机多开（`tests/e2e/conftest.py:100-129`）。 |
| CI 还是本地（`:461-463`） | 本仓库 E2E 已经进了 CI（`.github/workflows/tests.yml:169-231`），问题改成"agent 驱动的会话是否只在本地跑"。 |

### 8.3 paper-one 框架没覆盖、Web 应用特有的点

- **跨 iframe**：epub.js 正文在 iframe 里，Selection 不能跨 browsing context（`tests/e2e/helpers.py:222-224`）。bridge 工具必须能进 frame，否则只看得到宿主壳。Tauri bridge 恰好不进 iframe（§5.1），这是即便不看 CDP 问题也不能照搬它的又一理由。
- **观测者效应**：CPU 压力下，`--tracing=retain-on-failure`（7 跑 0 红）和不过滤的 `page.on(request/response)`（3 跑 0 红）把 flaky 压掉了，对照组 4 跑 4 红；台账原话是"凡是『给 e2e 加观测来查这条 flaky』的方案，都要先证明自己没把被查的东西压掉"（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md:884-898`）。
- **出站白名单**：E2E 会 abort 所有非本机 http(s) 请求（`tests/e2e/conftest.py:291-330`）。【推断】agent 驱动的浏览器会话若不加同样约束，看到的页面会与测试不同，依据是字体 CDN 曾阻塞 `load` 导致每条 30s 超时（`tests/e2e/conftest.py:295-311`）。

---

## 9. reader3-pro 借鉴建议（Q7）

### 9.1 Fit-gap

| 能力 | 现状（仓库文件路径） | 缺口 | 建议方案 | 工作量 S/M/L | 风险 |
|---|---|---|---|---|---|
| 进入 epub.js iframe 交互 | E2E 用 `frame_locator('[data-testid="rd-viewport"] iframe')`（`tests/e2e/helpers.py:163-179`）；宿主容器 `src/reader3_app/web/templates/reader.html:1467` | agent 交互式会话没有约定的进 frame 方式 | gstack `frame '[data-testid="rd-viewport"] iframe'` 后再 `snapshot`；备选 A/B 靠各自的 iframe 支持（§5.1） | S | 翻页后 ref 失效（C12），每次翻页后要重新 snapshot |
| 当前位置（CFI） | 没有 getter，`relocated` 只用来算进度（`src/reader3_app/web/static/js/epub-renderer.js:303`）；原始 `rendition` 已挂在 `window.Reader3Epub`（`:375-377`） | 外部只能自己拼 `Reader3Epub.rendition.currentLocation()`，仓库里没有调用点 | `getDebugState()` 返回 `currentLocation()` 的 start/end CFI | S | 首帧 `rendered` 之前为空，getter 要返回 `null` 字段而不是抛错 |
| spine index 与 href | `window.Reader3Ctx.chapterIndex` 在 `rendered` 时回写（`src/reader3_app/web/static/js/epub-renderer.js:283-288`）；URL 经 `history.replaceState` 同步（`:224-229`） | 没有 href，也没有和 CFI 放在同一次读取里 | getter 一并返回 index、href | S | 两个来源不同步时要以哪个为准需定义（【推断】建议以 `currentLocation()` 为准，依据是它是 epub.js 自身状态） |
| 阅读进度 | 只写进 `#reading-progress` 的 DOM 文本（`src/reader3_app/web/static/js/epub-renderer.js:235-248`） | 无结构化值，只能解析中文文案 | getter 返回百分比数值 | S | 与 DOM 文本的舍入规则要一致 |
| 标注高亮 | iframe 内 `mark[data-testid="rd-anno-span"]`（`src/reader3_app/web/static/js/annotations.js:483,544`）；E2E 靠 `scan_marks`（`tests/e2e/helpers.py:668`） | agent 要进 iframe 才能数 mark | getter 返回 mark 数 | S | 只读计数，不暴露正文 |
| 标注写失败诊断 | `window.Reader3NotesDiag`（frozen，ring buffer 容量 100，`src/reader3_app/web/static/js/annotations.js:150-161,187-208`） | 已可读，但与位置信息分散在两个全局上 | getter 附最近 N 条 `entries()` | S | 条目可能含书内文本片段【推断：依据是它记录写失败上下文】，N 要小 |
| console 日志 | 渲染器无条件 `console.log`，前缀 `[Reader3] epub-renderer`（`src/reader3_app/web/static/js/epub-renderer.js:15-19`）；legacy JS 共 41 处 | 噪声大；新 TS 的 `debug.log` 未接线（`frontend/src/shared/debug.ts:1-28`） | agent 按前缀过滤读取（O5）；gstack `console`；需要 source-map 堆栈时用备选 A | S | 全量拉 console 撑 context（O5、C11） |
| 网络 | E2E 用 init-script fetch 台账（`tests/e2e/notes_conflict_support.py:123,206,290`） | agent 侧无约定 | gstack `network`；深挖时用备选 A 的 `list_network_requests` | S | 挂到 soak 上会压掉 flaky（下一行） |
| 观测者效应 | tracing 与不过滤 request 监听会压掉 flaky（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md:884-898`） | 没有成文规则约束 agent/MCP 观测 | 规则：soak 跑（`scripts/soak_run.py`）不挂 tracing、MCP 或 agent 观测；getter 只拉不推、不注册监听 | S | 若违反，soak 台账会出现假绿 |
| 服务端 debug 端点 | 没有 debug flag 或 test-only 路由（`src/reader3_app/web/server.py:91`）；唯一探针 `/api/health`（`src/reader3_app/web/routers/health.py:22-30`） | —（这是刻意的） | **保持不加**。ADR-0012 已写明本机任何进程都能调 `/api/*`（`docs/adr/0012-security-boundaries.md:67`），新端点只会扩大这个缺口 | — | 若将来要加，按 paper-one Part C 四条 + `tests/contract/routes.snapshot` 断言生产 404 |
| 前端 debug 开关 | `localStorage["reader3.debug"]` 每次调用现读（`frontend/src/shared/debug.ts:1-28`），legacy `static/js` 不受它管 | getter 在 legacy JS 里，不能直接 import 这个 TS 模块 | 见 §9.3 的门控取舍 | S | 两处各写一份 key 检查会漂移 |
| MCP 配置 | `.mcp.json:1-7` 只有 `claude-design`，未跟踪、未 gitignore | 无浏览器 MCP | 默认不加；采用备选 A/B 时写成 project scope 并先审 `.mcp.json` | S | 提交后 `-p`/SDK 会不经审批加载（O1） |
| 回归 | `uv run pytest tests/e2e --browser chromium`，push 门控（`.claude/tdd-guardian/config.json:26-35`）；CI e2e job（`.github/workflows/tests.yml:169-231`） | agent 的探索发现没有落成测试的约定 | 探索 → 生成 pytest 用例（C5 做法），`tests/e2e/helpers.py` 新增 helper 复用 getter | M | 生成的用例要过选择器 lint（`scripts/lint_e2e_selectors.py:1-30`），只允许 testid 与 ARIA |
| 出站隔离 | E2E abort 所有非本机请求（`tests/e2e/conftest.py:291-330`） | agent 会话没有同样约束 | 约定 agent 会话只访问 127.0.0.1；备选 A 可用 `--blockedUrlPattern`（C3 / R2） | S | 【推断】页面与测试看到的不一致，依据是 `tests/e2e/conftest.py:295-311` 记录的字体 CDN 阻塞 |

### 9.2 推荐方案："不自建 bridge，补一个只读观测面"

**1. 不做 Tauri 式应用内 MCP bridge。**
- Tauri 需要内嵌 bridge，是因为它的 webview 没有 CDP 可接（§5.2、§8）。reader3-pro 在 127.0.0.1:8123 上是普通网页（`src/reader3_app/web/server.py:1072-1073`），playwright-mcp、chrome-devtools-mcp、gstack browse 都能直接连上，它们的 iframe 支持也强于 Tauri bridge（§5.1）。
- paper-one 文档 Part C 已经得出同一结论（`docs/references/paper-one-cli-and-mcp-bridge.md:490`）。
- 服务端 debug 端点会扩大 ADR-0012 承认的缺口：本机任何能发 HTTP 的进程都能调 `/api/*`（`docs/adr/0012-security-boundaries.md:67`）。内嵌 bridge 普遍无认证（§5.1 读表要点），Next 也放行不带 Origin 的请求（R13），没有理由在本仓库复制这个形态。
- ADR-0008 要求"避免为不存在的需求预先付架构复杂度的税"（`docs/adr/0008-tech-stack-boundary.md:86`）。

**2. 在 `window.Reader3Epub` 上加只读的 `getDebugState()`。**
- 位置：`src/reader3_app/web/static/js/epub-renderer.js:375-401` 的对象字面量里加一个方法。它是前端纯函数，不加路由、不加依赖。
- 返回字段：`rendition.currentLocation()` 的 start/end CFI、spine index 与 href、进度百分比、iframe 内 `mark[data-testid="rd-anno-span"]` 的数量、`Reader3NotesDiag.entries()` 最近 N 条。缺值时返回 `null`，不抛错。
- **它怎么回答 epub.js iframe 的可观测性问题**：状态读取不再需要跨进 iframe。任何 driver 都在顶层页面做一次 `evaluate` 即可：pytest-playwright 的 `page.evaluate`、gstack 的 `js`、playwright-mcp 的 `browser_evaluate`、chrome-devtools-mcp 的 `evaluate_script`。只有**交互**（点正文、选区、点 mark）才需要进 frame：测试用 `frame_locator`（`tests/e2e/helpers.py:177`），agent 用 gstack `frame`。
- 测试：在 `tests/e2e/helpers.py` 加一个 `debug_state(page)` helper，新用例用它，而不是再各写一段 `window.__*` 探针（现有探针清单见仓库底稿 §1，例如 `tests/e2e/baseline_1b/test_read_paths.py:82-83`）。实现按 TDD Guardian 流程走（CLAUDE.md 的全局约定）。

**3. agent 的交互式驱动用 gstack `/browse`。**
- 它已经是用户的标准浏览工具（全局 CLAUDE.md 要求 web 浏览一律用 `/browse`）。
- 有显式 `frame` 命令、只绑 127.0.0.1 且要 Bearer token、CDP 默认拒绝（§5.3）。
- CLI + daemon 形态让 snapshot 留在 daemon 侧、按需读取，符合 §7.1 第 4、5 条的 token 共识。

**4. 回归仍由 `tests/e2e/` 的 pytest-playwright 承担。**
- agent 的探索结果转写成 pytest 用例，即 C5 的"探索 → 生成测试"做法；用例必须过 `scripts/lint_e2e_selectors.py`。
- **观测者效应警告**：不要给 soak 跑挂 tracing、MCP 或任何 agent 观测（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md:884-898`）。`getDebugState()` 只拉不推、不注册监听，【推断】不调用时对事件泵零影响，依据是它只读已有对象；但在 soak 套件里高频调用它仍需先证明不改变结果。

### 9.3 门控取舍：`getDebugState()` 要不要挂在 `reader3.debug` 开关下

| 选项 | 好处 | 代价 |
|---|---|---|
| A. 复用 `localStorage["reader3.debug"] === "1"` 门控 | 与 `frontend/src/shared/debug.ts:1-28` 的约定一致，默认关闭 | `src/reader3_app/web/static/js/epub-renderer.js` 是 legacy 静态 JS，不能 import 这个 TS 模块，只能再写一份 key 检查，两处会漂移；测试和 agent 都要多一步设置（测试可用 `add_init_script`）；开关关着时 getter 返回什么需要额外定义 |
| B. 始终开启、只读 | 零设置，任何 driver 一次 `evaluate` 可用 | 多暴露一个全局方法 |

**本文倾向 B。** 理由：`window.Reader3Epub` 已经把原始 `rendition` 和 `book` 暴露在全局（`src/reader3_app/web/static/js/epub-renderer.js:376-377`），`currentLocation()` 本来就能调；`Reader3NotesDiag` 也是始终开启的 frozen 全局（`src/reader3_app/web/static/js/annotations.js:150-161`）。getter 只是把已可读的状态打包，不新增能力。【推断】因此不扩大攻击面，依据是同源脚本已经能拿到全部原料。选 A 的唯一实质收益是"默认安静"，而 getter 不打日志，本来就是安静的。

### 9.4 备选方案

**备选 A：加 chrome-devtools-mcp，只用于 console、network 与 performance trace。**
- 用途：gstack 覆盖较弱的部分，即带 source-map 堆栈的 console、请求详情、LCP trace（C1、R2）。
- 配置：在 `.mcp.json` 加 project-scoped 条目；**固定版本**（C9），带 `--isolated`、`--no-usage-statistics`、`--no-performance-crux`（C3）；需要时加 `--blockedUrlPattern` 屏蔽外网。
- **不要**用 `--autoConnect` 连用户真实的已登录 Chrome（C2、C3、C15）；本仓库无登录态需求（`src/reader3_app/web/server.py:134-135`）。
- 注意 `.mcp.json` 目前未跟踪，且含 `claude-design`（`.mcp.json:1-7`）；提交前先审内容，并记住提交后 `-p`/SDK 会不经审批加载（O1）。
- 工作量 S；代价是每会话多占约 18.0k tokens 工具描述（C7），`--slim` 只剩 3 个工具可缓解（R2）。

**备选 B：加 playwright-mcp，用于探索式写测试。**
- 用途：C5 的"探索 → 生成测试"流程、`--caps=testing` 的 `browser_generate_locator` 与 verify 工具。
- 配置：**固定版本**，且 ≥0.0.40 以包含 CVE-2025-9611 的 DNS rebinding 修复（C18）；`--isolated`。
- 风险：`browser_run_code_unsafe` 默认开启且 "RCE-equivalent"（R1），维护者拒绝改默认（C17）；`--allowed-origins` 不是安全边界（R1）；snapshot 在历史里累积，C11 实测每任务约 114k tokens，大页面会触发 413（C13）。
- 生成的用例要改写成 pytest-playwright 并过 `scripts/lint_e2e_selectors.py`，因为仓库 E2E 是 Python（`tests/e2e/`），而 C5 生成的是 TS `@playwright/test`。
- 工作量 S（配置）+ M（每条用例的转写）。

### 9.5 明确不采用

| 方案 | 理由 |
|---|---|
| BrowserMCP | 最后 commit 2025-04-24，事实停更；iframe 不支持（#96 open）；WS 9009 无鉴权（R6） |
| Browserbase MCP | 已归档；浏览器在云端，连不上本机 127.0.0.1 服务【推断：依据是运行位置为 Browserbase 云】（R3） |
| Puppeteer 参考实现 | 已归档；无 snapshot，不进 iframe（R7） |
| Claude in Chrome | 用户全局 CLAUDE.md 禁止 `mcp__claude-in-chrome__*`；Anthropic 自己称 "still risky"（O6）；不适合 CI（§3.5【推断】） |
| 自写 Python MCP server 包一层 Playwright | 与上面的现成方案重复；与 ADR-0008 的简单性约束冲突（`docs/adr/0008-tech-stack-boundary.md:86`）；还要自己解决 C15/C16/C18 那一整套安全问题 |

---

## 10. 未决问题与待核实项

**需要决定的**
1. `getDebugState()` 的门控：本文倾向始终开启（§9.3），需要用户确认。若选门控，要决定 legacy JS 里那份 key 检查如何与 `frontend/src/shared/debug.ts` 保持一致。
2. `Reader3NotesDiag` 条目是否含书内文本，以及 getter 返回几条（N）。需要读 `src/reader3_app/web/static/js/annotations.js:187-208` 的条目结构后定。
3. 是否提交 `.mcp.json`。目前只有 `claude-design`（`.mcp.json:1-7`）；如采用备选 A/B，要先决定团队共享还是 local scope。
4. 新 getter 与现有测试侧 `window.__*` 探针的关系：只给新用例用，还是逐步替换旧探针。后者会碰到 soak 冻结值 `suite_hash`（`docs/plans/20260816-tech-stack-migration/tasks/soak-log.md:3-4`），需要单独评估。

**待核实（底稿原样标注）**
- Browserbase `--experimental` 具体启用什么：未核验。Browserbase MCP 层的 iframe 支持：未核验。
- browser-use MCP 遥测的关闭方式：未核验。
- BrowserMCP 的 WebSocket 是否只监听 localhost：只有源码推断，未实测。
- Playwright MCP HTTP 模式是否有 token 认证：README 没写，只有源码推断。
- Storybook addon-mcp 的 Origin/Host 检查：未核验。多数工具参数：未核验。
- Vercel MCP 的 Toolbar 工具名：未核验。
- Next dev server 默认绑定所有接口还是 localhost：未核验。
- Vite 把 cors/host 校验挂在插件之前的最低版本：未核验。
- 所有 npm 版本号与发布日期：未核验（`registry.npmjs.org` 被权限拒绝）。
- "Playwright 团队 benchmark 114k vs 27k"：【未核实】，无一手出处，C11 写的是 25k。
- "snapshot 比 screenshot 贵 5.5 倍"：【未核实】（搜索摘要）。
- 同源 iframe 内联进 playwright-mcp snapshot、跨源需切 frame：【未核实】（qaskills.sh 二手摘要）。与此相对，R1 的 #106、#559 直接说明 snapshot 已包含 iframe 内容；本文以 R1 的 issue 为准，因为它们是维护者关闭时的一手回复。
- playwright-mcp issue #1639（action 响应内联 snapshot）：【未核实】，未抓取。

**本文未覆盖**
- 没有实际运行任何被调研的 server，iframe 支持均来自 issue 与源码，未在 reader3-pro 的 epub.js iframe 上实测。推荐方案落地前，应先用 gstack `frame` 在真实阅读页上走一遍（翻页、选区、点 mark）。
- 仓库底稿指出的两处文档漂移不属于本文范围，只记一笔：ADR-0008 仍引用已删除的 `READER3_LIBRARY_UI=classic` 开关（`docs/adr/0008-tech-stack-boundary.md:12,82,100`）；`.github/workflows/tests.yml:154` 的注释与 `:21-26,56-57` 新增的 `pull_request` 触发冲突。

---

## 自检清单

- [x] 来源 ≥15，其中官方 ≥3、社区 ≥4、开源仓库 ≥6。实际：官方 18、vendor 7、社区 13、开源仓库 17，合计 55（§2.2）。
- [x] 横评表每行都有链接、核验日期和核验状态（§5.1，15 行）。
- [x] 工具表覆盖 ≥4 个 bridge 且带来源链接。实际 5 个：playwright-mcp、chrome-devtools-mcp、Tauri、Next `/_next/mcp`、gstack browse（非 MCP）（§6）。
- [ ] 没有既无 URL 又无【推断】标记的事实陈述。**未勾选**：已尽力逐条挂出处，但未做逐句机械审计。已知例外有两类：（1）引用用户全局 `~/.claude/CLAUDE.md` 的约定（用 `/browse`、禁用 `mcp__claude-in-chrome__*`、TDD Guardian），这是仓库外文件，没有 `path:line`；（2）正文用 O/C/R/V 编号代替重复 URL，编号与 URL 的对应在 §2.1。
- [x] §9 引用的每个路径都存在。已用 `ls`/`test -e` 逐一核对 §9 中的 20 个仓库路径，全部存在；`~/.claude/skills/gstack/...` 下的路径属于仓库外的 gstack 源码，不在此项范围内。
- [x] 明确回答了 epub.js iframe 的可观测性方案（§9.2 第 2 条：状态经顶层 `window.Reader3Epub.getDebugState()` 一次 `evaluate` 读取，只有交互才进 frame）。
- [x] `git status --short` 与快照 `git-status-before.txt` 相比没有差异（`docs/references/` 本来就整体未跟踪）；`git status --short --untracked-files=all docs/references` 只多出本文件 `docs/references/ui-e2e-debug-mcp-bridge-survey.md`，另一项是既有的 `paper-one-cli-and-mcp-bridge.md`。
