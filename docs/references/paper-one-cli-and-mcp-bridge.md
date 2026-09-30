# paper-one：`paper` CLI 与 debug-only MCP bridge 参考

> **来源仓库**：https://github.com/xiaolai/paper-one
> **文档对应提交**：`d39f2df29466b42c76692f05f83b56929758866c`（2026-09-27T08:08:50+08:00），本文写于 2026-09-27。
> 下文中所有不带 URL 的 `path:line` 引用都指向该 SHA 下的 paper-one。
>
> **上游版本**
> - paper-one `0.4.8`（`package.json:4`，`src-tauri/Cargo.toml:3`）；Tauri `2.11.3`（`src-tauri/Cargo.toml:40`）；Node `>=24`，pnpm `10.33.0`（`package.json`，`engines` / `packageManager`）。
> - `tauri-plugin-mcp-bridge` `0.12.0`（`src-tauri/Cargo.toml:61` 声明 `"0.12"`，`src-tauri/Cargo.lock:7198-7202` 锁定为 0.12.0）。
> - `@hypothesi/tauri-mcp-server` `^0.12.0`（`package.json:76`），lockfile 解析为 0.12.0（`pnpm-lock.yaml:54-56`）。
> - 上游 bridge 源码读自 https://github.com/hypothesi/mcp-server-tauri 的 tag `v0.12.0`（提交 `283228159edf09bbf4d596b39cd396926c4437ae`，2026-07-05）。下文用 `U/` 代表 `https://github.com/hypothesi/mcp-server-tauri/blob/283228159edf09bbf4d596b39cd396926c4437ae/`。上游已发布 v0.13.0，本文没有读。
>
> **示例执行情况**：本文**所有示例均为「未执行」**，已执行的示例为 0 个。
> 原因：`pnpm install` 失败（corepack 下载 pnpm 10.33.0 时连不上 registry.npmjs.org）；本机 Node 是 v22，低于要求的 24。所以 `bin/paper.mjs` 构建不出来，也没有启动 Tauri app。
> 所有结论都来自静态阅读源码和测试。
>
> **约定**：没有标注的陈述是有出处的事实。「推断」表示源码里没有直接写明、由作者推理得出的结论。

---

## Part A — `paper` CLI

### A.1 入口与运行时

**构建产物与启动方式**
- `package.json` 声明 `"bin": {"paper": "./bin/paper.mjs"}`。但 `bin/paper.mjs` **不在 git 中**，它是 `pnpm build:cli`（`package.json:19` → `scripts/build-cli.mjs`）的产物。
- `scripts/build-cli.mjs` 的做法：用 Vite SSR 把 `src/cli/main.ts` 打成单文件，参数和产物特征如下。
  - `target: 'node24'`；
  - `ssr.noExternal: true`，即自包含，产物只剩 `node:` imports；
  - `inlineDynamicImports`；
  - 加上 `#!/usr/bin/env node` shebang；
  - 校验产物不小于 `MIN_BYTES=4096`；
  - 最后 `chmod 755`。
- 为什么要打包：源码用了无扩展名的 import，Node 的 ESM resolver 解析不了。Node 24 的 type stripping 不解决路径解析问题。脚本注释还指出，打出的单文件可以直接 `scp bin/paper.mjs other-mac:` 拷走使用。
- CI 只构建 CLI，不驱动 CLI：`.github/workflows/verify.yml:401-403` 跑 `pnpm verify --until build:cli`。

**进程边界**
- `src/cli/main.ts`（46 行）是唯一接触 `process` 的文件。它调用 `paper({argv: process.argv.slice(2), sinks, remote: (shelf) => openShelf({key: shelf, env: process.env, note})})`。
- 退出码写到 `process.exitCode`，不调用 `process.exit()`，这样 stdout 能先排空。

**无 daemon**
- `src/cli/paper.ts:13-17`：不带 `--shelf` 时，CLI 在进程内托管 `KernelServices`，不存在常驻 daemon。

**数据目录**（`src/hosts/node/services.ts:43-83`）

| 条件 | 数据目录 |
|---|---|
| 设置了 `PAPER_DATA_DIR`（`DATA_DIR_ENV`，第 50 行） | 该值 |
| macOS | `~/Library/Application Support/one.paper.reader` |
| Windows | `%APPDATA%\one.paper.reader` |
| Linux | `$XDG_DATA_HOME`（缺省为 `~/.local/share`）下的 `one.paper.reader` |

- 应用标识 `APP_IDENTIFIER = 'one.paper.reader'`（第 43 行）；该解析镜像 Tauri 的 `BaseDirectory.AppData`。
- `HOME` 为空字符串时会退回 `os.homedir()`（第 62-66 行），避免把库开在当前目录。
- 注意：`PAPER_DATA_DIR` 只有 Node host 读。app 端由 `tauri-plugin-peer` 处理，kernel 不处理（第 45-49 行注释，WI-8.6 陷阱）。

**`open()` 流程**（`src/cli/paper.ts:80-177`）

1. **远程分支**：给了 `--shelf` 就走 `remote(shelf)`。如果这个构建没有接 remote，则打印 `paper: this build cannot reach a remote shelf` 并以 exit 2 退出。
2. **本地分支**：`root = dataDir ?? defaultDataDir()`，再根据 `writes = !readingGrant(descriptor.grant)` 决定是读还是写。读写判断完全由表中的 grant 推导，见 A.3。
3. **写命令**：
   - `makeDataDir(root)`，然后 `acquireDataLock(root, {waitMs})`（第 110-118 行）。
   - 拿不到锁时抛 `LockHeld`，打印 `paper: another writer holds this library — …`，exit 1。
4. **打开 host**：`openNodeServices({dataDir: root, persist: writes})`（第 125-130 行）。读命令**一个字节都不写**，连 `index.json` 缓存也不写。
5. **写命令接 journal**：`openLocalJournal({services})`（来自 `capabilities/sync`，第 131-160 行），让 CLI 的修改进入 sync journal。
   - 背景（`src/cli/journaling.test.ts` 文件头）：在这之前 CLI 写入不产生 journal 条目，所以写入根本不会同步。
6. **关闭**：先关 journal，再关 host；锁在 `finally` 中释放。其他失败打印 `paper: <msg>`，exit 1。

**锁**（`src/hosts/node/lock.ts`）
- 锁文件是 `paper.cli.lock`（第 45 行），放在数据目录里。
- app 在 Rust 的 setup 阶段（webview 启动前，`src-tauri/src/lock.rs`）拿**同一个文件、同一种记录、同一套协议**（第 10-19 行）。
- 因此在运行中的 app 旁边执行 `paper book add` 会被拒绝，错误信息会点名 app 的 pid。
- 发布方式：先把记录写进私有临时文件并 fsync，再 `link` 到位。`link` 是原子且排他的，所以锁文件不可能没有可读的 owner。
  - 旧实现是 `open(path,'wx')` 后再写记录；在两步之间被 SIGKILL 会留下一个空锁文件，从此没有任何写者能进来（第 20-31 行）。
- 存活判定：pid 必须在运行，并且记录中的进程启动时间和主机 boot 时间都要与当前 OS 的回答一致，容差 `IDENTITY_TOLERANCE_MS = 5_000`（第 32-38、53 行）。
- 默认等锁 `DEFAULT_WAIT_MS = 5_000`（第 139 行）。
- 已知未覆盖的场景：桌面 UI 关着时手机（satchel）来同步（第 40-43 行）。

**`nodeSocket`**
- `src/cli/nodeSocket.ts:40-43`：`nodeSocketOpener(cookie)` 返回 `(url) => new WebSocket(url, {headers: {Cookie: cookie}})`。
- 浏览器会自己附带 HttpOnly cookie；Node 的 undici WebSocket 需要显式传 header。
- 这是 `--shelf` 远程调用的 socket 工厂。测试对着真实的 `node:http` upgrade 验证（`src/cli/nodeSocket.test.ts`）。

### A.2 语法：全局 flag、输出格式、退出码、错误形态

**全局 flag 与命令结构**（`src/cli/args.ts`）
- 全局 flag 是 `GLOBAL_FLAGS = ['--json','--help','-h','--shelf']`（第 47 行），在 argv 任意位置都会被识别（第 228-265 行）。`--` 之后不再解析 flag（`END_OF_FLAGS`，第 44 行）。
- `--shelf` 缺值，或者值以 `--` 开头，报错 `--shelf needs a shelf address, like https://shelf.example`（第 260 行）。
- 命令是**名词在前、单数**：`paper book list` 就是服务 `book.list`（第 15-20 行）。
- 名词或动词拼错时，按 Levenshtein 距离给出 "did you mean"（`SUGGEST_WITHIN = 3`）。

**参数强制转换（`coerce`）**

| 类型 | 规则 |
|---|---|
| `string` | 校验 `choices` |
| `number` | 空值得到 NaN，因此被拒 |
| `boolean` | `--no-<flag>` 置 false |
| `string[]` | 逗号分隔或重复出现均可，空值被拒 |

- 位置参数由字段的 `positional` 序号决定。
- 还会检查 `required`、`atLeastOne` 和 `withdrawn`。
- 解析结果 `Parsed` 是 `run`、`help`、`error` 三者之一。

**帮助**
- 有三层：`overview`、`nounHelp` 和 `serviceHelp`。
- `nounHelp` 显示每个动词的 grant，stream 类命令标 "· streams"。
- `serviceHelp` 显示 choices、atLeastOne 和 withdrawn。

**输出**（`src/cli/format.ts`）
- `--json`：`JSON.stringify(value ?? null, null, 2)`，输出完整行。stream 会被排空成一个数组。
- 人类可读格式：
  - 多行结果按 `descriptor.output.columns` 打成表格，单列最宽 `MAX_COLUMN = 200`，null 显示为 `—`；
  - 空数组打印 `nothing`；
  - 单个对象打成 key-value。
- `plain()` 去掉控制字符，防御 ANSI 注入（第 32-44 行）。

**退出码与错误形态**（`src/cli/run.ts`）

```ts
// src/cli/run.ts:41
export const EXIT = { ok: 0, refused: 1, usage: 2 } as const
```

- 设计理由见第 14-24 行。三个取值的含义：
  - 0 表示成功；
  - 1 表示服务拒绝（forbidden、conflict、unsupported、锁被占等），也包括 close 失败——close 失败不算成功；
  - 2 表示用法错误（解析错误、未知命令、withdrawn 字段），`malformed` 拒绝也映射为 2。
- 错误输出到 stderr，格式为 `paper: <name>: <code>: <message>`。
- stream 在客户端排空，`--limit` 也在客户端执行。上限是 `MAX_DRAIN_ROWS = 1_000_000` 和 `MAX_DRAIN_BYTES = 64 MiB`，超出任一抛 `{code: 'unsupported'}`。
- 本地调用同样做 grant 检查（`src/cli/caller.ts:98-110`）。默认持有全部 grant（`ALL_GRANTS`，由 `GRANT_FAMILIES` 推导，第 73-80 行），缺少时抛 `{code:'forbidden', message:'<svc> needs <grant>'}`。这个检查的目的是保证"表写错了 grant"在本机就能暴露（第 44-55 行注释）。
- 本机 Node host 没有 peer transport，因此 `device.list` 会按名拒绝（`unsupported`，exit 1），不会回一个空列表。`--json` 下也一样（`src/cli/run.test.ts:216-235`）。

### A.3 命令清单（33 条，10 个名词）

数据源是 `src/kernel/core/serviceTable.ts:543-1136` 的 `TABLE` 字面量。

- **R/W**：grant 以 `:read` 结尾就是读，否则是写（`readingGrant`，第 132 行）。
- **受众**：`paired-device` 表示可以服务给配对设备；`this-shelf` 表示只服务本 shelf（即读者自己的会话）。
- **远程可用**：列出经 `--shelf`（webhost 会话）能否执行。webhost 只授予 `WEB_READS`（即 `readServices()` 的全部 grant，`pump.ts:197`）加上 `position:write`（`src/capabilities/webhost/lib/pump.ts:236`；`src/cli/shelfLink.ts:33-40`），所以远程写命令会被 shelf 以 `forbidden` 拒绝。
- 没有特别说明时，参数中的 `book` 是 `BOOK_ID`：位置参数 0，必填（第 533 行）。

| 命令 | 行 | 参数（位置参数 / `--flag`） | 作用 | R/W · grant | 受众 | 远程可用 |
|---|---|---|---|---|---|---|
| `book list` | 546 | `--tag --author --finished --downloaded --since --limit` | 索引行分页；`since` 用于增量读取 | R · book:read · stream | paired-device | 是 |
| `book get` | 564 | `<book>` | 单条记录及其 ledger registers | R · book:read | paired-device | 是 |
| `book add` | 575 | `<book> <title> [author] --ext` | 创建记录，只写元数据 | W · book:write | paired-device | 否 |
| `book set` | 591 | `<book> --finished --position --progress --status --rating --review`，至少给一个；`--title`/`--author` 已 withdrawn | 修改字段 | W · book:write | paired-device | 否 |
| `book position` | 619 | `<book> <position> --progress` | 阅读位置，也是唯一对阅读设备放开的写 | W · position:write | paired-device | **是**（唯一的远程写） |
| `book remove` | 644 | `<book>` | 移入 trash | W · book:write | paired-device | 否 |
| `book restore` | 655 | `<book>` | 从 trash 恢复 | W · book:write | paired-device | 否 |
| `book search` | 666 | `<query> --limit` | 索引查询，支持 `tag:` / `-tag:` / `is:` / 文本 | R · book:read · stream | paired-device | 是 |
| `mark list` | 682 | `[book] --limit` | 某本书或全部 mark | R · mark:read · stream | paired-device | 是（`mark:read` 属于 `WEB_READS`） |
| `mark add` | 696 | `<book> <cfi> [text] --kind --colour --note --prefix --suffix --chapter --section` | 锚定高亮、笔记或书签 | W · mark:write | paired-device | 否 |
| `mark set` | 732 | `<mark> --book --note --colour`，note/colour 至少给一个 | 修改笔记或颜色 | W · mark:write | paired-device | 否 |
| `mark remove` | 749 | `<mark> --book` | 写 tombstone，删除可复制 | W · mark:write | paired-device | 否 |
| `card list` | 765 | `--limit` | 所有 live card，新的在前 | R · card:read · stream | paired-device | 是 |
| `card add` | 776 | `<text> --kind --book` | 建卡 | W · card:write | paired-device | 否 |
| `card remove` | 791 | `<card>` | 写 tombstone | W · card:write | paired-device | 否 |
| `tag list` | 806 | `--limit` | 标签及计数（stream，第 811-819 行解释了原因） | R · book:read · stream | paired-device | 是 |
| `tag add` | 825 | `<tag> --book a,b`（必填，string[]） | 多书打标签 | W · book:write | paired-device | 否 |
| `tag remove` | 839 | `<tag> [--book …]` | 从指定书去掉标签；不指定书则全库去掉 | W · book:write | paired-device | 否 |
| `tag rename` | 853 | `<from> <to>` | 全库改名；改成已存在的名字即合并 | W · book:write | paired-device | 否 |
| `content locate` | 869 | `<book>` | 返回 hash、size，以及本 shelf 是否持有字节 | R · book:read | paired-device | 是 |
| `content read` | 880 | `<book> --offset --length --expect` | 书的字节切片，base64 分块输出 | R · blob:read · stream | paired-device | 是 |
| `content evict` | 944 | `<book>` | 删除本设备上的字节副本（不复制到其他设备） | W · book:write | paired-device | 否 |
| `cover read` | 960 | `<book>` | 封面，base64 分块输出 | R · book:read · stream | paired-device | 是 |
| `passage search` | 977 | `<query> --limit` | 全文段落检索（多词为 AND，引号表示短语） | R · blob:read · stream | **this-shelf**（第 1008 行） | 是（`src/cli/remote.envelope.test.ts:137-143`） |
| `device list` | 1020 | — | 列出已配对 peer | R · device:read | paired-device | 本机 Node host 为 `unsupported` |
| `device grant` | 1031 | `<device> --grants …` | 替换某个 peer 的 grant 列表 | W · device:manage | paired-device | 否 |
| `device forget` | 1045 | `<device>` | 解除配对 | W · device:manage | paired-device | 否 |
| `shelf status` | 1058 | — | 角色、endpoint、书数、journal seq 等 | R · shelf:read | paired-device | 是 |
| `shelf sync` | 1069 | — | 在 satchel 上立即同步；在 shelf 上回 `started:false` 并附原因 | W · shelf:admin | paired-device | 否 |
| `shelf verify` | 1081 | — | 检查 index 与 journal 的完整性 | W · shelf:admin | paired-device | 否 |
| `trash list` | 1094 | `--limit` | 已删除的书，以及距离过期还剩多久 | R · book:read · stream | paired-device | 是 |
| `trash empty` | 1105 | `<count> [--books a,b]` | 表中**唯一**标记 `irreversible` 的命令（第 1134 行）。`count` 必须等于调用者预期删除的数量，否则拒绝 | W · shelf:admin | paired-device | 否 |

合计 33 条命令，10 个名词（`SERVICE_NOUNS`，第 228 行）：book、mark、card、tag、content、cover、passage、device、shelf、trash。

表中刻意**排除**了三类服务：`sync.*`、字节流（byte stream）和 `device.pair`（第 48-76 行）。

**一张表如何同时生成 CLI、客户端 stub 和权限面**

`serviceTable.ts:26-46` 的文件头声明，这一个字面量驱动四样东西：router 注册、client stub、CLI 命令、参考文档。

```ts
// src/kernel/core/serviceTable.ts:132
export const readingGrant = (grant: string): boolean => grant.endsWith(':read')
// :1226-1229 —— 读写分类由 grant 推导，不另立名单
export const readServices = () => SERVICE_TABLE.filter((one) => readingGrant(one.grant))
export const writeServices = () => SERVICE_TABLE.filter((one) => !readingGrant(one.grant))
// :1237-1239 —— 客户端 stub 由表派生，客户端无法点名不存在的服务
export function serviceClients(): readonly ClientContribution[] {
  return SERVICE_TABLE.map((one) => ({ name: one.name }))
}
// :1261-1274（节选）—— 按成员资格过滤，不按排除名单
return services.filter((one) => serviceDescriptor(one.name)?.audience === 'paired-device')
```

各个消费方如何使用这张表：
- **CLI**：`src/cli/args.ts` 用 `positionalFields` / `flagFields`（第 1277、1285 行）从每个 `ServiceField` 生成解析器和帮助；`run.ts:51` 的 `commandList()` 也由表派生。
- **锁**：`paper.ts` 用 `readingGrant` 决定是否拿写锁、是否挂 journal。
- **权限**：本地 `localCaller` 用 `grantCovers` 做检查；peer 端用 `servableToAnotherDevice` 过滤。`audience` 是必填字段，没有默认值（第 185-197 行），所以新增一行却忘写受众会编译失败。
- **类型**：`TABLE` 声明为 `as const satisfies readonly ServiceDescriptor[]`，经 `deepFreeze` 后成为 `SERVICE_TABLE`（第 1204 行）；`output.columns` 按 `WireShapes` 做类型约束（第 430-467 行）。

### A.4 `--shelf` 远程

**地址规则**（`src/cli/shelfAddress.ts:73-148`）
- 必须写完整 origin，含 scheme。**不接受裸主机名**，理由是猜 TLS 身份不安全（第 6-17 行）。
- 拒绝 userinfo，并且拒绝消息**不回显输入**，以免密码进入 stderr。
- 不接受 path、query 或 fragment。
- `[::1]` 被专门诊断：插件只绑定 IPv4 loopback。
- `http:` 只允许 loopback（`localhost`、`127.0.0.0/8`）；其余一律要求 https，例如套一层 `tailscale serve`（第 19-30、126-131 行）。
- 由 origin 派生三个地址：
  - `socket`：`ws(s)://host/ws`，派生逻辑复用 kernel 的 `socketUrl`；
  - `submit`：`/api/auth/submit`；
  - `session`：`/api/auth/session`。

**认证**（`src/cli/shelfLink.ts`）
- 凭据**只从环境变量读取**，不走 flag，也不落文件（第 9-30 行）。三个变量与 `scripts/shot-client.mjs` 共用：
  - `PAPER_CLIENT_COOKIE`
  - `PAPER_CLIENT_CODE`（shelf 屏幕上显示的 6 位码）
  - `PAPER_CLIENT_ORIGIN`
- 设置了 cookie 却没设 origin 时拒绝发送（第 255-266 行），防止把本地凭据发给别的 shelf。origin 与 `--shelf` 不一致同样拒绝。
- 流程：
  1. 用 cookie 调 `GET /api/auth/session`（第 188-220 行）。401 表示 `refused`，网络故障则直接抛错——宕机不等于吊销。
  2. cookie 失效但有 code 时，改用 `POST /api/auth/submit` 配对。
  3. 配对得到的新 cookie 先经 session 验证，**再**以"变量名 = 值"的形式打印到 stderr。打印的不是可粘贴执行的 `export` 语句，因为 cookie 中可能含有 `'`，会造成 shell 注入（第 290-310 行）。
- 传输：`connectToShelf({url: address.socket, open: nodeSocketOpener(cookie)})`，然后由 `remoteCaller({channel})` 包装（`src/cli/remote.ts`）。
- `run.ts` 分辨不出本地 caller 和远程 caller，所以"每条命令要么两边都能用，要么两边都不能用"，并且没有第二张命令表（`src/cli/remote.ts:9-17`）。
- 远程的 `ServiceCallError` 会被解包成与本地相同的拒绝形态，例如 `forbidden` 的拼写一致。

**可用动词**
- 所有读命令，加上 `book.position`。
- 其余写命令都会被 shelf 以 `forbidden` 拒绝。源码说明这是有意设计：写能力需要新的凭据类型，不需要新的传输方式（`src/cli/shelfLink.ts:33-40`）。

### A.5 示例（全部**未执行**）

```sh
# 1. 构建并查看帮助（未执行）
pnpm build:cli && ./bin/paper.mjs --help && ./bin/paper.mjs book --help
# 2. 按标签列书，JSON 交给 jq（未执行；stream 被排空成数组）
paper book list --tag history --limit 20 --json | jq '.[].title'
# 3. 新增一本书，只写元数据（未执行；app 正在运行时会因锁 exit 1）
paper book add my-book-id "Moby-Dick" "Herman Melville"
# 4. 给两本书打同一个标签（未执行；string[] 可以逗号分隔，也可以重复 --book）
paper tag add whaling --book my-book-id,other-id
# 5. 被 withdrawn 的字段会被点名拒绝（未执行；预期 exit 2）
paper book set my-book-id --title "New"
# 6. 不可逆清空：数量必须与 trash 实际一致（未执行）
paper trash list --json | jq length   # 假设输出 3
paper trash empty 3 --books a,b,c
# 7. 远程读取：用 6 位码配对（未执行；新凭据打印到 stderr）
PAPER_CLIENT_CODE=123456 paper --shelf https://studio.tail1234.ts.net book list --json
# 8. 拼错名词（未执行；预期提示 did you mean book，exit 2）
paper boook list
```

### A.6 测试

测试按 Vitest project 划分（`vitest.config.ts:73-88`）：
- **`cli` project**：`src/cli/**/*.test.ts`，但不含 envelope 类测试；
- **`service-envelope` project**：包含 `src/cli` 下的 envelope 测试，即 CLI 客户端经 fake wire 与 router 对话。

`src/cli/main.ts` 被排除在覆盖率之外（第 180-181 行）。

| 文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `src/cli/args.test.ts` | 46 | flag 与位置参数解析、类型强制转换、did-you-mean、help |
| `src/cli/run.test.ts` | 38 | 命令列表、退出码、`--json`、人类格式、`unsupported`、本地 grant 检查、排空上限、`paper()` 入口 |
| `src/cli/writers.test.ts` | 31 | 每个写服务都经 CLI 走一遍；写入留下的 journal bracket；两个写者不能交错执行（第 145、307、349 行） |
| `src/cli/remote.envelope.test.ts` | 20 | 每条命令都经过 envelope；缺 grant；取消；`paper --shelf`（第 252、542、612、679 行） |
| `src/cli/shelfLink.test.ts` | 18 | cookie 与 code 流程、origin 绑定、Set-Cookie 解析 |
| `src/cli/shelfAddress.test.ts` | 12 | 地址规则 |
| `src/cli/folderAliases.test.ts` | 11 | id 经 sanitize 后映射到文件夹是多对一；验证 add 和 restore 在别名冲突时点名拒绝（文件头第 9-25 行） |
| `src/cli/remote.test.ts` | 7 | `remoteCaller` 的错误解包 |
| `src/cli/caller.test.ts` | 6 | `localCaller` 的 grant 检查与取消 |
| `src/cli/journaling.test.ts` | 6 | CLI 写入进入 sync journal，以及保护真实库的各种拒绝（文件头第 12-25 行） |
| `src/cli/nodeSocket.test.ts` | 5 | 对真实的 `node:http` upgrade 验证 Cookie header |
| `scripts/build-cli.test.mjs` | 5 | 打包产物（shebang、自包含等） |

- 用例数用 `grep -cE '^\s*(it|test)(\.each(...))?\('` 统计，合计约 205。
- 注意：`folderAliases.ts` 和 `journaling.ts` **没有**对应的源文件。这两份测试针对的是 `paper()` 的端到端行为。

---

## Part B — debug-only MCP bridge

### B.1 编译期门控

```toml
# src-tauri/Cargo.toml:58-61
# Automation bridge for e2e testing. Registered only in debug desktop builds
# (see lib.rs); kept a normal dependency rather than a dev-dependency because
# dev-dependencies do not apply to a binary's own debug profile.
tauri-plugin-mcp-bridge = { version = "0.12", optional = true }
# src-tauri/Cargo.toml:184-187
[features]
default = ["desktop"]
desktop = [
    "dep:tauri-plugin-mcp-bridge",
```

```rust
// src-tauri/src/lib.rs:748-755
#[cfg(all(feature = "desktop", debug_assertions))]
{
    builder = builder.plugin(
        tauri_plugin_mcp_bridge::Builder::new()
            .bind_address("127.0.0.1")
            .base_port(mcp_bridge_port())
            .build(),
    );
}
```

**crate 始终编译，只有注册受门控**
- crate 是 optional 的，但 `desktop` 在 `default` features 里，所以**release 桌面构建同样会编译并链接这个 crate**。
- 受 `cfg(all(feature="desktop", debug_assertions))` 门控的是两件事：
  - 插件注册（`lib.rs:741-756`）；
  - 运行时 ACL `app.add_capability("mcp-bridge-debug", permissions ["mcp-bridge:default"], windows ["main"])`（`lib.rs:575-621`）。
- `lib.rs:598-609` 的注释明确承认 crate 会进入 RELEASE 构建，并更正了早先"静态声明会导致构建失败"的错误说法。
- 把 ACL 放在运行时注册，是为了让 grant 和插件处在同一个 `cfg` 下：发布构建不带这条 ACL，两者也不会漂移。
- `src-tauri/capabilities/desktop.json` 和 `default.json` 中都没有 mcp 权限。
- 缺少这条 ACL 时的症状：`mcp-bridge.script_result not allowed` 或 "Script execution timeout"。

**`debug_assertions` 的开关**
- Cargo 的 dev profile 默认开启，release profile 默认关闭。
- 因此 `pnpm app`（`tauri dev --config src-tauri/tauri.dev.conf.json`，`package.json:24`）会带上 bridge，`tauri build` 不会。`src-tauri/Cargo.toml` 中没有任何 `[profile.*]` 段，因此没有覆盖 `debug-assertions`（已 grep 确认）。

**端口**
- 固定为 `MCP_BRIDGE_PORT = 31415`（`lib.rs:13-23`）。
- 注释说明了选这个值的原因：插件默认端口 9223 并会向后扫描 100 个端口，而本机的 vmark 占用 9323；31415 离两者都足够远。
- 环境变量 `PAPER_MCP_PORT` 可以覆盖端口（`lib.rs:25-54`），按 `NonZeroU16` 解析；非法值会**直接 panic 并点名这个值**，不会悄悄回退到默认端口。
- 已知陷阱：上游 `find_available_port` 会从 base 扫描到 base+99，全部被占则回落到 base（`U/packages/tauri-plugin-mcp-bridge/src/discovery.rs#L16-L29`）。所以 31415 被占时，bridge 会**静默**改到 31416 及以后，而客户端仍然连 31415。这正是 `PAPER_MCP_PORT` 注释要求显式指定端口的原因（`lib.rs:27-33`）。

### B.2 架构与协议

```
 ┌──────────────────────┐   stdio (MCP JSON-RPC)   ┌──────────────────────────────┐
 │ MCP host             │ ───────────────────────▶ │ @hypothesi/tauri-mcp-server  │
 │ (Claude Code / Codex)│ ◀─────────────────────── │ 0.12.0 (Node)                │
 └──────────────────────┘                          └──────────────┬───────────────┘
                                                                  │ ws://MCP_BRIDGE_HOST:MCP_BRIDGE_PORT
 ┌──────────────────────┐                                         │ JSON {id,command,args}
 │ paper scripts        │ ws://127.0.0.1:31415                    │     ↔ {id,success,data|error}
 │ lib/bridge.mjs (无   │ ────────────── 同一协议 ─────────────┐  │ + 广播事件
 │ MCP, 只发 execute_js)│                                      ▼  ▼
 └──────────────────────┘                    ┌──────────────────────────────────────────┐
                                             │ Tauri app (debug) · tauri-plugin-mcp-bridge│
                                             │ tokio-tungstenite WS server 127.0.0.1:31415│
                                             │  ├─ execute_js ──▶ WKWebView evaluateJS    │
                                             │  │                 或 window.eval + invoke │
                                             │  │                 ('plugin:mcp-bridge|    │
                                             │  │                  script_result') 回传   │
                                             │  ├─ capture_native_screenshot (平台 API)   │
                                             │  ├─ invoke_tauri (仅 plugin:mcp-bridge|*) │
                                             │  └─ bridge.js 注入：包装 __TAURI__.core   │
                                             │     .invoke 做 IPC 监控                    │
                                             └──────────────────────────────────────────┘
```

**逐跳说明**

*跳 1：MCP host → MCP server*
- 使用 stdio 上的 MCP：`StdioServerTransport`，`U/packages/mcp-server/src/server.ts#L152-L154`。

*跳 2：MCP server → 插件*
- 纯 JSON 的 WebSocket，由 tokio-tungstenite 实现。
- 目标地址 `ws://${host}:${port}`：
  - host 取 `MCP_BRIDGE_HOST`，其次 `TAURI_DEV_HOST`，最后 `'localhost'`；
  - port 取 `MCP_BRIDGE_PORT`，缺省为 9223。
  - 出处：`U/packages/mcp-server/src/config.ts#L21-L37`、`#L80-L81`。
- 「推断」paper 被 gitignore 的 `.mcp.json` 应该设置了 `MCP_BRIDGE_PORT=31415`，否则连不到 31415。
- 响应形态是 `{id, success, data}` 或 `{id, success:false, error}`（`U/.../src/websocket.rs#L165-L180`）。
- 事件会**广播到同一个 socket**，所以客户端必须按 `id` 匹配响应（`scripts/lib/bridge.mjs:76-81`）。

*插件端*
- 插件名是 `mcp-bridge`，注册了 13 个 invoke 命令，并通过 `.js_init_script(include_str!("bridge.js"))` 注入脚本（`U/.../src/lib.rs#L161-L177`）。
- setup 阶段先 `find_available_port`，再启动 `WebSocketServer::new(port, &bind_address, …)`（`#L190-L218`）。
- 分发的命令：`invoke_tauri`、`list_windows`、`get_window_info`、`execute_js`、`capture_native_screenshot`、`resize_window`、`register_script`、`remove_script`、`clear_scripts`、`get_scripts`（`websocket.rs#L556-L607`）。
- `handle_invoke_tauri` 只放行 `plugin:mcp-bridge|*`，其他命令回 "Unsupported Tauri command"（`#L183-L250`）。
- `register_script` 通过 `inject_script_to_window` 追加一个带 `data-mcp-script-id` 的 `<script>`（`#L715` 起）。

**JS 如何执行**（`U/.../src/commands/execute_js.rs`）
- macOS 上，只要脚本文本里不含 `await `、`async `、`(async`、`.then(`、`Promise.`、`new Promise(`，就走原生 `WKWebView evaluateJavaScript:completionHandler:`，超时 10 s（`#L61-L145`、`#L167-L177`）。
- 否则走 `eval_with_ipc_callback`（`#L181-L316`）：`window.eval` 一段包装代码，执行完调用 `window.__TAURI__.core.invoke('plugin:mcp-bridge|script_result', {execId, …})` 回传结果；失败时退回 emit `__script_result` 事件，超时 5 s。
- 这回答了 paper `lib.rs:589-596` 注释中"尚未确定"的问题：异步脚本确实依赖 `script_result` 的 ACL grant。

**截图 / DOM / 点击 / 输入 / IPC**
- **截图**：首选原生 `capture_native_screenshot`，即 macOS 的 WKWebView takeSnapshot 或 Windows 的 WebView2 CapturePreview 等（`U/packages/mcp-server/src/driver/webview-executor.ts#L435-L475`）。失败时回退到经 `register_script` 注入的 html2canvas（`#L401-L421`）。
- **DOM**：通过 `execute_js` 注入 `scripts/dom-snapshot.js`，里面带 aria-api bundle（`U/packages/mcp-server/src/driver/scripts/`）。
- **点击**：`interact.js` 在元素上合成 `MouseEvent('mousedown'/'mouseup'/'click')`（`scripts/interact.js#L67-L91`）。这是**合成 DOM 事件，不是 OS 级输入**。
- **输入**：`keyboard.js` 直接设置 `element.value` 并派发 `input` 和 `change` 事件（`scripts/keyboard.js#L23-L27`）。
- **IPC**：`bridge.js` 包装 `window.__TAURI__.core.invoke`，记录调用和返回（`U/.../src/bridge.js#L116-L185`）；`ipc_monitor` 负责开关，`ipc_get_captured` 负责读取。

**MCP 工具**（20 个，`U/packages/mcp-server/src/tools-registry.ts#L112-L607`）

所有 `webview_*` 工具都额外接受 `windowId?` 和 `appIdentifier?`（`WindowTargetSchema`）。

| 工具 | 参数 |
|---|---|
| `get_setup_instructions` | — |
| `list_devices` | — |
| `driver_session` | `action` = start/stop/status；`host?`；`port?`；`appIdentifier?` |
| `webview_find_element` | `selector` |
| `read_logs` | `source` = console/android/ios/system；`lines=50`；`filter?`；`since?` |
| `webview_interact` | `action` = click/double-click/long-press/scroll/swipe/focus；`selector?`；`x?`；`y?`；`duration?`；`scrollX?`；`scrollY?`；`fromX…toY?` |
| `webview_screenshot` | `format` = png/jpeg（默认 jpeg）；`quality=80`；`filePath?`；`maxWidth?` |
| `webview_keyboard` | `action` = type/press/down/up；`selector?`；`text?`；`key?`；`modifiers?[]` |
| `webview_wait_for` | `type` = selector/text/ipc-event；`value`；`timeout=5000` |
| `webview_get_styles` | `selector`；`properties?`；`multiple=false` |
| `webview_execute_js` | `script`；`args?` |
| `webview_dom_snapshot` | `type` = accessibility/structure；`selector?` |
| `webview_select_element` | `timeout`（5000–120000，默认 60000） |
| `webview_get_pointed_element` | — |
| `ipc_execute_command` | `command`；`args?` |
| `ipc_monitor` | `action` = start/stop |
| `ipc_get_captured` | `filter?` |
| `ipc_emit_event` | `eventName`；`payload` |
| `ipc_get_backend_state` | `appIdentifier?` |
| `manage_window` | `action` = list/info/resize；`windowId?`；`width?`；`height?`；`logical=true` |

**认证与绑定地址**
- 上游默认 `bind_address: "0.0.0.0"`（`U/.../src/config.rs#L18-L25`）；paper 显式改成 `127.0.0.1`，理由是默认值会把 bridge 暴露到局域网（`lib.rs:741-747`）。
- WS 握手用 `accept_async`，**既没有认证，也不检查 Origin**（`U/.../src/websocket.rs#L644-L665`）。

### B.3 paper-one 如何使用 bridge

**两条接入路径**
- 仓库内脚本**不用 MCP**，直接说 WS 协议。
  - `scripts/lib/bridge.mjs`（168 行）没有 npm 依赖，也没有 MCP 客户端（第 5-7 行）；文件头写明 "DEBUG BUILDS ONLY … a release build answers nothing on this port"（第 16-19 行）。
  - `DEFAULT_PORT = 31415`（第 35 行），连接超时 8 s，执行超时 30 s。
  - `execute()` 发送 `{id: randomUUID(), command:'execute_js', args:{script}}`，按 id 匹配响应（第 143 行）；`evaluate()` 再对字符串结果做 `JSON.parse`。
  - 调用方：`scripts/circle-drive.mjs`、`public-drive.mjs`、`word-snap-live.mjs`、`lib/circle-scripts.mjs`，以及测试 `bridge.test.mjs`、`word-snap-live.test.mjs`。
- `@hypothesi/tauri-mcp-server` 在仓库里**只出现在 `package.json:76`**。「推断」它是给 gitignore 的 `.mcp.json` 用的，供 Claude Code / Codex 交互式驱动 app。
  - `.gitignore:130-139` 的 cc-suite PRIVATE 段忽略了 `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.agents/`、`.codex/` 和 `.mcp.json`，所以这些文件的内容无法核实。

**`circle-drive.mjs` 端到端**（229 行）
- 子命令：identity、marks、share、withdraw、shelf/unshelf、mute/unmute、friend。每个子命令输出一个 JSON 对象，退出码为 0/1/2。
- 连接失败时提示 "…(a RELEASE build answers nothing on this port)"（第 99 行）。
- `IDENTITY` 脚本（`scripts/lib/circle-scripts.mjs:28-40`）在页面内调用 `window.__TAURI__.core.invoke('plugin:peer|peer_circle_mine')`。这依赖 dev 配置里的 `withGlobalTauri: true`（`src-tauri/tauri.dev.conf.json`）；正式配置是 `false`（`tauri.conf.json:14`）。
- UI 操作用 aria-label 定位元素再 `.click()`（`flipSwitch`，第 389-403 行）。React 的受控 input 通过原生 setter 赋值。
- share 流程（第 189-211 行）：
  1. `reachMarginalia`；
  2. `READ_MARKS`；
  3. `SHARE_FIRST_UNSHARED`；
  4. 每 500 ms 轮询一次 `stateOfRow`，最多 60 次，直到按钮文字变成 'Withdraw'。
  注释写的是 "THE WAIT IS THE ASSERTION"。
- 通用的 `act()` 模式是"执行脚本 → 每 500 ms 轮询 `verify()`"（`scripts/lib/circle-navigate.mjs:16-39`，"THE ASSERTION IS THE OBSERVATION"）。

**编排与多实例**
- `scripts/circle-scenario.sh` 的阶段是 preflight → mutate → converge → negative，另有 `--falsify`（第 1-66 行）。它设 `port=31415`（第 83 行），`drive()` 执行 `node circle-drive.mjs --port "$port"`（第 274 行）。
- **多实例用两台机器加 ssh 隧道实现**，不在一台机器上跑两个实例：
  - `scripts/public-scenario.sh:60`：`ssh -N -L 31416:127.0.0.1:31415 <user@host>`；
  - `scripts/second-instance.sh`：`BRIDGE_PORT_REMOTE=31415`，`BRIDGE_PORT_LOCAL=31416`；
  - `circle-scenario.sh` 的 `--far-port` 就是隧道的本地端（第 740 行）。
- 不用单机双实例的原因：`PAPER_TEST_DATA_DIR` 只挪动 peer 插件的根目录，不挪 kernel 的 vault，两个实例仍会共用一个书库（`lib.rs:35-38`）。
- `sync-scenario.sh` 使用的是 `paper` CLI，**不是** bridge（`circle-scenario.sh:12-16`）。

**CI 还是本地**
- `.github/workflows/verify.yml:161-164` 只在 Linux 上**编译** bridge（它的 screenshot 模块）。
- 没有任何 workflow 运行 drive 脚本，所以 bridge 驱动的场景**只在本地跑**。

### B.4 安全推理

**release 构建在 31415 上的表现**
- 插件没有注册，就没有 listener，也就**没有任何东西应答**。这与 `bridge.mjs:16-19` 和 `circle-drive.mjs:99` 的说法一致。
- 但 crate 的代码仍被链接进 release 二进制（见 B.1）。「推断」在 `cfg` 之外没有调用点，所以它是死代码，不构成可达的攻击面。

**残余风险**（全部是「推断」，只适用于 debug 构建）
1. **浏览器可以跨源连上**：WS 不检查 Origin 也没有认证，而浏览器的 WebSocket 不受 CORS 约束。开发者在浏览器里打开的任意网页都能连 `ws://127.0.0.1:31415` 并发送 `execute_js`。
2. **注入的 JS 可以调用 app 命令**：dev 配置开启了 `withGlobalTauri: true`，所以注入的 JS 可以 `invoke` 主窗口 capability 允许的任何 app 命令。paper 自己的脚本就调用了 `plugin:peer|peer_circle_mine`，这意味着能读写真实数据目录里的数据和身份。
3. **端口漂移带来抢占和误连**：
   - 31415 被占时插件会静默改用 31416+，这时另一个进程可以占着 31415，接收本来发给 app 的脚本和返回值；
   - 在 debug 实例和别的 Tauri 项目并存时，也可能连错实例。
4. **ssh 隧道扩大了信任边界**：远端 31415 的访问权等同于本地 shell 用户的权限。
5. **已缓解的风险**：
   - 绑定 127.0.0.1，而不是上游默认的 0.0.0.0；
   - ACL 只授予 `main` 窗口，并且只在 debug 下存在；
   - `handle_invoke_tauri` 只放行 `plugin:mcp-bridge|*`。

---

## Part C — 对 Reader3 Pro 的启示（**均为建议，不是决定**）

- **建议：让一张表同时生成 CLI 和 API。** Reader3 Pro 的 CLI（`uv run reader3`）和 FastAPI 路由目前是分开维护的。可以参考 `SERVICE_TABLE` 的做法，用一张 dataclass 表同时生成 argparse 子命令、路由注册和权限（读/写）。这也符合 Constitution 原则 1（Data Structures First）。但要先评估这是否违反原则 2（YAGNI）：在命令数少于 10 的阶段，收益可能不足。
- **建议：固定 CLI 的退出码和错误格式。** 采用 `0 成功 / 1 拒绝 / 2 用法错误`，stderr 输出 `reader3: <cmd>: <code>: <message>`，并提供 `--json`。这样脚本和 LLM agent 更容易稳定调用。paper 的 `run.test.ts` 专门给退出码写了测试组，这一点可以借鉴。
- **建议：CLI 与运行中的 server 争用写入时，用单一锁协议。** 如果 `uv run reader3 <epub>` 在 server 运行时写 `books/*_data/`，可以借鉴 paper 的 "link 发布 + pid 与启动时间判活" 锁。这需要与 ADR-0007（crash-safe publish）对齐，并与 server 共用同一个锁文件，避免两套各自"看起来一致"的协议。
- **建议：测试专用的后门必须在注册和授权两层都做门控。** Reader3 Pro 是 Web 应用，Playwright 已经能直接驱动 DOM，**不需要**类似 MCP bridge 的东西。如果将来要加 test-only 端点，要做到四点：
  - 路由挂载和授权都放在同一个开关下（类比 `cfg` 同时包住 plugin 和 capability）；
  - 默认绑定 127.0.0.1；
  - 校验 Origin 或 token；
  - 在 contract 测试里断言生产配置下这些端点返回 404。
- **建议：E2E 中"等待即断言"。** paper 的 `act → poll verify` 模式对应 Playwright 的 `expect(locator).toHave…` 自动等待。可以在 `tests/e2e` 中统一禁止固定的 `sleep`，改用基于可观察状态的等待。
- **建议：凭据走环境变量并绑定 origin。** 如果 Reader3 Pro 以后给 CLI 加远程或 API key 参数，可以照搬 `shelfLink.ts` 的几条规则：
  - 不设 `--api-key` 这类 flag，避免凭据进入 shell history 和 `ps`；
  - 凭据必须与 origin 绑定才发送；
  - 非 loopback 地址一律要求 https。

---

## 附：对先前笔记的更正

1. **"bridge crate 是 optional 的，所以不会进 release"——不对。** `desktop` 是 default feature，crate 会被编译进 release 桌面构建。受 `debug_assertions` 门控的只有插件注册和 ACL（`Cargo.toml:184-194`，`lib.rs:598-609`）。
2. **"`bin/paper.mjs` 存在"——不对。** 它是 gitignore 的构建产物，由 `pnpm build:cli` 生成。
3. **"`src/cli/folderAliases.ts`、`journaling.ts` 是源文件"——不对。** 这两个文件不存在，只有对应的 `.test.ts`。
4. **"bridge 的使用方包括 circle-scenario.sh 和 sync-scenario.sh"——不准确。**
   - 通过 `lib/bridge.mjs` 直接连 bridge 的是 circle-drive、public-drive 和 word-snap-live 三个 `.mjs`；
   - `circle-scenario.sh` 是间接调用 circle-drive；
   - `sync-scenario.sh` 用的是 `paper` CLI。
5. **"脚本通过 `@hypothesi/tauri-mcp-server` 驱动 app"——不对。** 仓库脚本直接说 WS 协议，只发 `execute_js`；那个 npm 包只在 `package.json` 中声明。
6. **bridge 端口不一定是 31415。** 端口被占时插件会静默扫描到后续端口，paper 为此提供了 `PAPER_MCP_PORT`。
