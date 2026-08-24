# FeedDock Frontend Implementation Spec

Derived from `designs/feeddock-frontend-prototype/` (2026-07-28). This file is
the source of truth for Lane 1B / T9. Do not re-read the prototype; if
something is missing here, fix it here.

**Scope rule:** WeChat *single-article import* ships. WeChat *account
subscription* (W2) does not — see §7. `screens-w2.jsx` is excluded entirely.

**Fidelity rule:** layout, Chinese copy, responsive rules and the
accessibility contract are copied exactly. Loading/error states the prototype
omits are designed fresh (§8) — confirmed in-scope.

---

## 1. Route map

The prototype is one page with a `screen` string in state. Production uses real
routes.

| Plan page | URL | Prototype component |
|---|---|---|
| Landing / Login | `/` (redirect → `/inbox` when authed) | `FdLandingScreen` |
| Inbox | `/inbox` | `FdInboxScreen` |
| Add | `/add` | `FdAddScreen` |
| Reader | `/inbox/[itemId]` — intercepting route: drawer over `/inbox` on soft nav, full page on hard load | `FdDrawer` + `FdReaderBody` |
| Sources | `/sources` | `FdSourcesScreen` |
| Search | `/search` | `FdSearchScreen` |
| Agent access | `/agent` | `FdAgentScreen` |
| Account / privacy | `/account` | `FdAccountScreen` |

### Shell (applies to all routes except Landing)

```
<a class="fd-skip">跳到主要内容</a>        visually hidden until focused
.fd-shell (grid: 232px sidebar | 1fr)
├── aside.fd-sidebar              desktop only, sticky
│   ├── .fd-brand  [FD] FeedDock
│   ├── nav.fd-nav aria-label="主导航"
│   ├── .fd-sidebar__spacer
│   └── button.fd-account  [陈] 陈宇 / 受控 Beta   → /account
└── .fd-main
    ├── .fd-mobilebar   <768px: [FD] {title} [☰]
    ├── header.fd-topbar   sticky: h1 + sub + optional action
    └── main#fd-main-content .fd-content
        └── .fd-content__inner  (+ --narrow on /account, /add)
nav.fd-bottomnav        <768px, fixed, 5 cells
```

**Nav items** — label / icon / count suffix:

| key | label | icon | count |
|---|---|---|---|
| inbox | 收件箱 | inbox | `未读 {n}` |
| add | 添加内容 | plus | — |
| sources | 来源 | rss | `来源 {n}` |
| search | 搜索 | search | — |
| agent | Agent 访问 | key | `生效 {n}` |
| account | 账户与隐私 | user | — |

Nav item `title` = `label（countLabel）` when a count exists. Active item gets
`aria-current="page"`.

**Bottom nav (<768px)**: `inbox, add, sources, search` + a 5th 更多 button
opening the mobile sheet. The add cell's label shortens to `添加`. Inbox cell
shows a numeric badge when unread > 0 plus SR-only `未读 {n}`. 更多 gets
`.is-on` when on `/agent` or `/account`.

**Mobile sheet**: heading `更多`, close button labelled `关闭导航（Esc）`, nav
with only agent + account, `<hr class="fd-divider">`, full-width ghostdanger
`退出登录`.

**Top bar** — title / subtitle:

- inbox — `收件箱` / `未读 {n} · 收藏 {n} · RSS 来源 {n}`
- add — `添加内容` / `RSS 持续订阅 · 公众号与 X 单篇导入`
- sources — `来源` / `仅 RSS 订阅 · 共 {n} 个`
- search — `搜索` / `在自己的资料库中检索 · 共 {n} 条内容`
- agent — `Agent 访问` / `只读 · 限定范围 · 可过期 · 可撤销`
- account — `账户与隐私` / `{email}`

**Top-bar primary actions**: inbox → `添加内容` (primary, plus, →/add);
sources → `添加 RSS 订阅` (primary, plus, →/add); agent → `创建 Agent Token`
(primary, plus, opens dialog). Others: none.

### Global behaviours

- Scroll to top on every route change (design.md §10: 页面切换后阅读位置可预测).
- Escape closes the topmost layer: dialog → reader → mobile nav. Special case:
  Escape on the token *reveal* step must finish creation, never silently
  discard the grant.
- `document.body` scroll locked while any focus-trapped layer is mounted.

---

## 2. Component inventory

### Primitives (`app/_components/primitives/`)

**`useFocusTrap(ref)`** — on mount records `document.activeElement`, focuses
`[data-autofocus]` → first focusable → the node. Focusable selector:
`button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])`.
Tab/Shift+Tab wrap within the node, filtering to `offsetParent !== null`. Locks
body scroll. On unmount restores focus and scroll.

**`Button`** — props: `variant` (`primary|secondary|text|danger|ghostdanger`,
default secondary), `size` (`sm`), `block`, `type` (default button), `onClick`,
`disabled`, `loading`, `loadingLabel`, `icon`, `title`, `ariaLabel`,
`ariaPressed`, `autoFocusTarget`, `children`.
When `loading`: a `.fd-spinner` replaces the icon, button is disabled, label
becomes `loadingLabel`. Label always wrapped in `<span>`. `autoFocusTarget` →
`data-autofocus="true"`.
**Anchors styled as buttons are required** in three places (reader 查看原文,
import result 查看原文, 在原平台打开) — support an `as="a"` form.

**`IconButton`** — `icon`, `label` (used for both `title` and `aria-label`),
`on` (→`.is-on`), `large` (40px), `size` (icon px, default 18), `ariaPressed`.
32×32, forced to 44×44 on mobile.

**`Chip`** — `selected`, `onClick`, `disabled`, `icon`, `children`. Selected
state expressed **only** via `aria-pressed="true"`.

**`Badge`** — `tone` (`ok|warn|err|brand|muted`; omit = neutral), `icon`.
22px pill, icon size 12 weight 2.

**`Note`** — `tone` (`brand|warn|err|ok`), `icon` (default `info`, size 16),
`role` (`alert`/`status`).

**`Field`** — `id` (required; derives `{id}-err` / `{id}-hint`), `label`,
`hint`, `error`, `children`. **Hint is hidden when `error` is present.** Error
renders `<p class="fd-errtext" role="alert">` with an alert icon size 13.
**Fix the prototype gap:** wire `aria-describedby` on the control to the
hint/error id.

**`Empty`** — `icon` (default inbox, size 24), `title`, `desc`, `action`.
56px rounded icon tile, centered.

**`SkeletonList`** — `rows` (default 3). Renders
`.fd-list[aria-busy="true"][aria-live="polite"]`, SR-only `正在载入内容…`, then
N cards with bars at 62% / 94% / 40% (first bar 16px tall).

**`Tabs`** — `label`, `value`, `onChange`, `panelId`, `tabs[{value,label,count}]`.
`role="tablist"`; each tab `role="tab"`, `id="tab-{value}"`, `aria-selected`,
`aria-controls`. Numeric count renders a Badge (`brand` when selected, `muted`
otherwise).
**Scroll behaviour:** on value change, if `scrollWidth > clientWidth`, scroll
*the strip* so the active tab is centered:
`left = active.offsetLeft - (clientWidth - active.offsetWidth) / 2`, clamped at
0, smooth unless `prefers-reduced-motion`. Never `scrollIntoView` — it drags the
document on mobile.

**`Drawer`** — `eyebrow`, `title`, `onClose`, `footer`, `children`. Overlay +
`<section role="dialog" aria-modal="true" aria-labelledby="fd-drawer-title">`.
Close button labelled `关闭阅读视图（Esc）`, autofocused.
**Publishes footer height to `--fd-drawer-foot-h` on `documentElement`**
(measured on mount and on resize) so the mobile toast stack clears it.

**`Dialog`** — `title`, `desc`, `wide` (640px vs 520px), `dismissible` (when
false, overlay click is a no-op), `onClose`, `footer`. `aria-describedby` only
when `desc` given. Focus-trapped.

**`Toasts`** — `toasts[{id,tone,title,desc}]`, `onDismiss`, `aside` (shifts
left of the drawer). `role="status" aria-live="polite"`. Icon by tone:
`err`/`warn` → alert, `info` → info, else checkCircle (18). Dismiss button
labelled `关闭提示`.
**Lifecycle:** default tone `ok`; auto-dismiss after **4200ms** unless
`tone === "err"` — error toasts are sticky.

### Icons (`Icon`)

`viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, round caps/joins,
`aria-hidden="true"`, `focusable="false"`, `style={{display:"block",flex:"none"}}`.
Default size 20, `strokeWidth` 1.7. Unknown name → `dot`.

Set (32): `inbox plus rss search key user menu close chevronDown chevronRight
arrowLeft check checkCircle bookmark bookmarkFilled external alert info pause
play trash copy clock refresh mail filter shield eye doc wechat xmark terminal
link dot`.
`bookmarkFilled` = bookmark path with `fill="currentColor"`. `dot` = filled
circle r=4, `stroke="none"`. `xmark` (X logo) overrides strokeWidth to 2.2.
Copy path data verbatim from `icons.jsx:21-213`.

**`PlatformTag`** — `platform`: rss→rss icon, wechat→wechat icon, else xmark.
Renders `.fd-platform.fd-platform--{p}` with a colored dot + label.

### Content components (`app/_components/content/`)

`ArticleCard` (Inbox + Search), `ReaderBody`, `SourceRow`, `SourceHealth`,
`GrantRow`, `ImportResult`.

---

## 3. Per-screen spec

### 3.1 Landing / Login

```
.fd-landing
├── header.fd-lnav (sticky, blurred)  [FD FeedDock] [anchors] [邀请登录]
├── main
│   ├── section.fd-hero (grid 1.05fr/.95fr)
│   │   ├── .fd-hero__copy  eyebrow / h1 / lead / 3 points
│   │   └── section.fd-login #fd-signin
│   └── section.fd-boundary #fd-boundary  (2-col)
└── footer.fd-lfoot
```

Nav anchors: `这个版本做什么` → `#fd-what`, `不做什么` → `#fd-boundary`,
`邀请登录` → focuses the email input.

**Hero**
- Eyebrow (info icon 13px): `受控 Beta · 邀请制`
- H1 (44px, `<em>` renders brand-colored non-italic):
  `把值得留下的内容，变成 ` + `<em>Agent 可以查询</em>` + ` 的私人资料库`
- Lead: `持续接收 RSS，并把值得保留的公众号文章和 X Post 一键收进私人资料库；Codex、Claude 等 Agent 可在授权范围内查询最近内容，并返回原文与可核对的引用。`
- Points (icon / bold lead-in / rest):
  1. rss — **`持续订阅 RSS。`** ` RSS / Atom / JSON Feed 自动刷新，带健康状态、最后成功刷新时间与暂停开关。`
  2. doc — **`单篇导入公众号文章与 X Post。`** ` 提交一条公开链接，保存标题、作者、发布时间、正文与原始出处。`
  3. key — **`只读 Agent Token。`** ` 限定来源与日期范围、默认 30 天过期、随时撤销；Agent 只能读，不能改。`

**Sign-in card — idle/loading**
- H2 `邀请登录`
- Desc: `FeedDock 目前是邀请制。填写收到邀请的邮箱，我们会发送一次性登录链接，不需要设置密码。`
- Field `fd-login-email`, label `邮箱`. **Drop the prototype's demo hint.**
- `<input type="email" inputMode="email" autoComplete="email" placeholder="you@example.com">`,
  `aria-invalid`, disabled while loading, Enter submits.
- Primary block button, icon mail, `发送登录链接`, loadingLabel
  `正在发送登录链接…`, disabled when email is blank.
- Footer hint: `登录即表示你了解：这是受控 Beta，功能范围以本页说明为准。`

**Sign-in card — sent**
- H2 `登录链接已发送`
- Desc: `已向 <strong>{email}</strong> 发送登录链接，15 分钟内有效，只能使用一次。没收到可以检查垃圾邮件，或重新发送。`
- Secondary block button `换一个邮箱`.
- **Drop** the prototype's `这是设计原型：…` note and its
  `打开邮件中的登录链接` button — real magic link arrives by email.

**Errors** (inline in Field)
- Invalid format (client regex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`):
  `请输入有效的邮箱地址，例如 you@example.com。`
- Not invited (server): `这个邮箱不在邀请名单中。如果你有邀请码，请使用收到邀请的邮箱登录。`

Success toast: `已登录` / `登录链接已使用，本次登录有效期 30 天。`

**Boundary section** — H2 `这个版本做什么`, six green check lines:
1. `持续订阅并刷新 RSS / Atom / JSON Feed，显示健康状态与最后成功刷新时间`
2. `通过公开 URL 一次性导入公众号文章与 X Post`
3. `统一收件箱：全部 / 未读 / 收藏，按平台与来源筛选`
4. `正文阅读、原文回退、解析状态与完整溯源信息`
5. `按关键词、日期、来源与平台搜索自己的资料库`
6. `创建只读、限定范围、可过期、可撤销的 Agent Token`

H2 `这个版本不做什么`, six grey close lines:
1. `不持续跟踪公众号：公众号文章只能按单篇公开链接导入`
2. `不持续跟踪 X 账号，也不同步关注、点赞或书签`
3. `不提供 AI 摘要、推荐或向量检索`
4. `Agent 只能读取，不能修改订阅、状态、内容或账户`
5. `不提供公共 REST API、浏览器扩展或原生 App`
6. `不绕过登录、验证码、付费墙或平台访问控制`

Then Note (warn/info): `Beta 期间不收费。正式定价仍在验证中，会在收费前单独通知，不会自动扣款。`

**Footer**: `FeedDock · 受控 Beta`(strip 设计原型 wording) and
`阅读状态与 Agent 查询记录默认私有，不用于模型训练`.

### 3.2 Inbox

```
Tabs aria-label="收件箱分组"   [全部 n][未读 n][收藏 n]
.fd-filters   平台 chips | 来源 select | [清除筛选]
.fd-resultbar left: totals | right: current count
#fd-inbox-panel role="tabpanel" aria-labelledby="tab-{tab}"
└── section.fd-daygroup  h2 + .fd-list → ArticleCard[]
```

Tabs: `all 全部`, `unread 未读`, `saved 收藏`. **Counts are computed after
platform+source filtering but before tab filtering** — badges reflect the
current platform/source scope.

Platform chips: `全部平台 / RSS / 微信公众号 / X`. Changing platform **resets
source to all**.

Source select (label `来源`, `width:auto; minWidth:180px; minHeight:36px`):
`全部来源`, then `<optgroup label="RSS 订阅（n）">`, then
`<optgroup label="一次性导入来源（n）">` with `{name}（{平台标签}）`. Option
value is the composite key `{platform}:{sourceName}`.

Result bar — left: `共 <b>{n}</b> 条内容 · 未读 <b>{n}</b> · 收藏 <b>{n}</b> · RSS 来源 <b>{n}</b>`;
right: `当前结果 <b>{n}</b> 条` + `（已应用筛选）` when filters active.
`filtersActive = platform !== "all" || sourceKey !== "all"` (tabs don't count).

**Day grouping**: preserves first-seen order of dates from the sorted list.
Label: today → `今天 · 2026年7月28日`; previous day → `昨天 · {date}`;
otherwise `{YYYY}年{M}月{D}日` (no leading zeros). Heading text is
`{label} · {n} 条`. **Derive from a real clock, not a constant.**

**Sort**: `published` DESC, ties by `id` DESC.

**ArticleCard**
```
div.fd-item [.is-read][.is-active][.is-new]     whole card opens the reader
├── .fd-item__body
│   ├── toprow: ●unread dot + <span class="fd-sr">未读</span>
│   │           PlatformTag · {sourceName} · Badge{originLabel}
│   │           Badge warn+alert 部分解析 (parse==="partial")
│   │           Badge ok+check 新增 (isNew)
│   │           Badge brand+search {matchBadge} (search only)
│   ├── h3 > button.fd-item__titlebtn        2-line clamp
│   ├── p.fd-item__summary                   2-line clamp
│   └── meta: {author} · <time> · {rel} · {约 N 字 · M 分钟} · {已读|未读} [· 已收藏]
└── .fd-item__actions → IconButton (bookmark)
```
Separators are `<span class="fd-sep" aria-hidden="true">·</span>`.
Bookmark icon `bookmarkFilled` when saved else `bookmark`; `aria-pressed`;
label `{saved ? "取消收藏：" : "收藏："}{title}`.
Title button and bookmark button both `stopPropagation()` so the card click
doesn't double-fire.
Reading cost: `约 {words.toLocaleString("en-US")} 字 · {minutes} 分钟` — note
the **en-US thousands separator**, e.g. `约 5,600 字 · 17 分钟`.

**States**

| State | Render |
|---|---|
| Loading | `SkeletonList rows={4}` |
| Success | day-grouped list, 16px gap between groups |
| Empty — filtered | Empty icon `filter`, `当前筛选没有匹配的内容`, `已按平台或来源缩小了范围。清除筛选可以看到该分组下的全部内容。`, action `清除筛选` |
| Empty — unread | icon `checkCircle`, `没有未读内容`, `这个分组里的内容都已读完。RSS 订阅会持续送来新内容，也可以随时手动导入单篇文章。`, action `查看全部内容` |
| Empty — saved | icon `bookmark`, `暂无收藏`, `阅读文章时点击收藏，内容会留在这里，Agent 也可以按「已收藏」筛选查询。`, action `浏览全部内容` |
| Empty — cold start | icon `inbox`, `资料库还是空的`, `订阅一个 RSS 源开始持续接收内容，或导入一篇公众号文章 / 一条 X Post。`, action primary `添加内容` |
| Error | **new, §8** |

Empty states are wrapped in `.fd-card`.

Toasts: save → `已收藏` / `已取消收藏`, desc `《{title}》` (ok / info).
Opening an item marks it read and clears `isNew`.

### 3.3 Add

Content column is `--narrow` (880px). Three sections; RSS spans both columns.

Kind badges: `fd-kind--persistent` (brand-soft, refresh icon, `持续订阅`),
`fd-kind--once` (subtle+border, doc icon, `一次性导入`).

**A. RSS 订阅**
- H2 `RSS 订阅`; desc `FeedDock 会持续刷新 RSS / Atom / JSON Feed，新内容自动进入收件箱。RSS 是本版本唯一可持续刷新的连接方式。`
- Field `fd-rss-url`, label `Feed 或网站地址`, hint `可以填 Feed 地址，也可以填网站首页地址，FeedDock 会尝试自动发现 Feed。`,
  `type="url" inputMode="url"`, placeholder `https://example.com/feed`.
  When an error result is present the field-level error is suppressed (the note
  carries the message).
- Buttons: primary plus `订阅这个来源`, loadingLabel `正在发现 Feed…`;
  secondary `清空` shown only when the field has a value.
- **Drop `FdSamples` and all demo URLs.**

| State | Render |
|---|---|
| loading | Note brand/clock/status: `正在发现并校验 Feed…` |
| validation | `请填写完整网址，需要包含 https:// 或 http://。` (regex `/^https?:\/\/.+/i`) |
| success | Note ok/checkCircle/status: **`已订阅「{name}」。`** ` 首次回填 {n} 条最近内容，已进入收件箱。` + secondary-sm inbox `查看收件箱`, text-sm rss `在来源中管理`. Input cleared. |
| error — no feed | Note err/alert/alert: **`没有发现可用的 Feed。`** ` 目标页面没有可发现的 Feed 链接。可以直接填写 Feed 地址，或确认该站点是否提供 RSS。` + `错误码 FEED_NOT_FOUND` in mono @0.8 opacity |
| error — duplicate | same shell; `你已经订阅了「{name}」，可以在「来源」中管理它。`, code `ALREADY_SUBSCRIBED` |

Toasts: failure → err `订阅失败` / `没有发现可用的 Feed`; duplicate → warn
`已经订阅过这个来源`; success → ok `已订阅「{name}」` /
`已加入来源列表，正在获取最近内容…`, then a follow-up
`「{name}」新增 {n} 篇` / `已进入收件箱，标记为未读。` once the first refresh
completes (prototype fakes this with a 1300ms timer; production fires it when
the job reports).

**B. 公众号文章**
- H2 `公众号文章`; desc `提交一条公开的 <span class="fd-mono">mp.weixin.qq.com</span> 文章链接，导入这一篇文章。`
- Boundary Note (warn/info): `这是<strong>单篇导入</strong>，不是订阅。FeedDock <strong>不会</strong>持续跟踪该公众号，也不会自动获取它之后发布的文章。`
- Field `fd-wechat-url`, label `公众号文章链接`, placeholder `https://mp.weixin.qq.com/s/...`
- Primary plus `导入这一篇`, loadingLabel `正在获取文章…`

**C. X Post**
- H2 `X Post`; desc `提交一条公开的 X Post 链接，导入这一条内容。`
- Boundary Note: `这是<strong>单条导入</strong>，不是订阅。FeedDock <strong>不会</strong>跟随该账号、不同步关注关系、点赞或书签。`
- Field `fd-x-url`, label `X Post 链接`, placeholder `https://x.com/<账号>/status/<编号>`
- Primary plus `导入这一条`, loadingLabel `正在获取 Post…`

**Import outcome matrix.** Validation for both: `请填写完整网址，需要包含 https://。`

| Outcome | note | copy |
|---|---|---|
| success | ok / status | **`已导入 1 条内容。`** |
| partial | warn / status | **`已导入，正文部分解析。`** wechat: `正文图片未完整获取（4 张图片解析失败）。` x: `这是一个推文串，本次只导入了首条内容。` |
| unsupported | warn / alert | **`不支持这个链接。`** wechat: `只支持公开的 mp.weixin.qq.com 单篇文章链接。合集页、搜索结果页与第三方转载页暂不支持。` x: `只支持单条公开 Post 的链接，格式为 https://x.com/<账号>/status/<编号>。账号主页与列表页暂不支持。` code `UNSUPPORTED_URL` |
| blocked | err / alert | **`内容无法访问。`** wechat: `文章已被发布者删除或设为不可见，无法获取正文。已保留你提交的链接以便核对。` code `UPSTREAM_DELETED`. x: `这条 Post 属于受保护账号，无法公开获取。FeedDock 不会绕过任何访问控制。` code `UPSTREAM_PROTECTED` |
| error | err / alert | **`导入失败。`** |

Success/partial notes also show `《{title}》 · {sourceName} · {published}` and
two actions: secondary-sm inbox `在收件箱中打开`, and an anchor-button
text-sm with external icon 14px `查看原文`.
Failure notes show `错误码 {code}` in mono @0.8 opacity, plus, when an original
URL exists, a text-sm link `在原平台打开`.

Toasts: unsupported → warn `不支持这个链接` / `已保留你填写的地址，可以修改后重试。`;
blocked → err `内容无法访问` / `文章已被删除` or `受保护账号`;
success → ok `已导入 1 条内容` / `《{title}》`;
partial → warn `已导入，正文部分解析` / `《{title}》`.

### 3.4 Reader (drawer)

```
Drawer
├── head: eyebrow "{sourceName} · {originLabel}" | h2 {title} | [×]
├── body: article.fd-reader (max-width 720px, centered)
│   ├── badge row
│   ├── h1.fd-reader__title
│   ├── .fd-reader__meta {source} · {author} · <time> · {约 N 字 · M 分钟}
│   ├── [partial-parse note]
│   ├── .fd-reader__prose  <p> per paragraph
│   ├── provenance note
│   └── section 溯源信息 → dl.fd-prov
└── foot: [收藏] [查看原文↗] [打开来源]   ·   [标记为已读/未读]
```

Badge row: PlatformTag; origin badge (`brand` if subscribed else `muted`);
read badge — muted `已读` or brand `未读`; if saved, ok+bookmarkFilled `已收藏`;
parse badge — warn+alert `部分解析` or ok+check `解析完整`.

Partial note (warn/status): `<strong>正文部分解析。</strong>{parseNote} 已保留标题、来源与原始链接，可通过下方「查看原文」核对完整内容。`

**Prose**: each paragraph gets `lang={/[一-龥]/.test(p) ? "zh" : "en"}` — this
drives `:lang(zh) { line-height: 1.75 }`. Reproduce it.

Provenance note (brand/link): `<strong>本文来自 </strong>` then by origin —
subscription: `RSS 订阅「{sourceName}」，FeedDock 会持续刷新该来源。`;
import: `一次性导入的公开链接。FeedDock 不会持续跟踪「{sourceName}」的后续内容。`

**溯源信息** `<dl class="fd-prov">`, H2 `溯源信息` (14px):

| dt | dd |
|---|---|
| 来源 | `{sourceName}（{平台标签}）` |
| 作者 | `{author}` |
| 发布时间 | `{published}` |
| 原始链接 | `<a target="_blank" rel="noreferrer noopener">{originalUrl}</a>` |
| 抓取时间 | `{fetchedAt}` |
| 获取方式 | `RSS 订阅刷新` / `用户提交公开 URL 导入` |
| 解析器版本 | `{parser}` in mono |
| 解析状态 | `部分成功` / `成功` |

**Footer**: save button — primary+bookmark `收藏` when unsaved,
secondary+bookmarkFilled `取消收藏` when saved. Anchor-button secondary with
external 16px `查看原文`. `打开来源` (secondary, rss) **enabled only for
subscription origin**, otherwise disabled with
`title="一次性导入的内容没有可持续刷新的订阅来源"`. Right: text button, eye
icon when read / check when unread, `标记为未读` / `标记为已读`.

Toasts: read toggle → info `已标记为已读` / `已标记为未读`. `打开来源` → closes
reader, navigates to /sources, info `已跳转到来源管理` / `RSS 订阅「{name}」`.

When the reader is open, toasts get `aside`.

### 3.5 Sources

```
Note (brand/rss)         scope explainer
.fd-resultbar            counts ─── [添加订阅 secondary-sm]
.fd-card → SourceRow[]   border-bottom between rows
```

Explainer: `这里只列出 <strong>RSS 订阅</strong>——本版本唯一可以持续刷新的来源类型。公众号文章与 X Post 是一次性导入的单条内容，会直接出现在收件箱，不构成订阅关系。`

Result bar: `RSS 来源 <b>{n}</b> · 正常 <b>{n}</b> · 刷新失败 <b>{n}</b> · 已暂停 <b>{n}</b>`
+ secondary-sm plus `添加订阅`. Counting: ok = `!paused && health==="ok"`;
err = `!paused && health==="error"`; paused = `paused`.

**SourceRow**
```
.fd-srcrow[.is-paused]
├── body
│   ├── h3 {name} | health badge | Badge muted "未读 {n}"
│   ├── p {feedUrl}
│   ├── stats: 最后尝试刷新：{t} / 最后成功刷新：{t}
│   │          / 订阅于：{d} / [连续失败 {n} 次]
│   └── p.fd-hint {note}    (--color-error when health==="error")
└── actions [查看内容][暂停刷新|恢复刷新][退订]
```
Health badge: paused → muted+pause `已暂停`; error → err+alert `刷新失败`;
else ok+check `正常`. `连续失败 {n} 次` only when the streak > 0.
Actions: secondary-sm inbox `查看内容`; secondary-sm pause/play
`暂停刷新`/`恢复刷新`; ghostdanger-sm trash `退订`.

Empty: icon rss, `还没有 RSS 订阅`, `订阅一个 RSS 源之后，FeedDock 会持续刷新它，新内容自动进入收件箱。`, action primary `添加 RSS 订阅`.

Interactions:
- `查看内容` → filter inbox to that source, navigate, toast info `已筛选收件箱` / `来源：{name}`.
- Pause → note becomes `已暂停，不再抓取新内容。已有文章保留在资料库中。`;
  toast info `已暂停「{name}」` / `不再获取新内容，已有内容保留。` and
  `已恢复「{name}」` / `将在下次刷新周期继续获取新内容。`
- `退订` → confirm dialog: title `退订「{name}」？`; desc
  `退订后 FeedDock 不再刷新这个来源，也不会再收到它的新内容。` +
  (kept>0 ? `已有的 {kept} 条内容会保留在资料库中，可以在账户页单独删除。`
   : `这个来源目前没有已投递的内容，退订不会删除任何东西。`) +
  `重新订阅可以恢复刷新。`; confirm label `退订这个来源`.
  On confirm toast ok `已退订「{name}」` / `保留了 {kept} 条已有内容。`

### 3.6 Search

- H2 `搜索资料库`; desc `在标题、摘要、来源、作者与正文中检索。搜索只覆盖你自己的资料库，不检索互联网。`
- Keyword field `fd-search-q`, label `关键词`, placeholder
  `例如：Agent 记忆、MCP、开源模型`, wrapped in `.fd-searchwrap` with an
  absolutely-positioned search icon (16px) and `padding-left: 38px`.
- Date fields `fd-search-from` / `fd-search-to`, labels `起始日期` / `截止日期`,
  `type="date"`, `max={today}`.
- Source select `fd-search-source`, label `来源`, same optgroups as Inbox.
- Platform chips identical to Inbox.
- Buttons: primary search `搜索`, loadingLabel `正在搜索…`; secondary close
  `清除关键词与筛选`.

`hasFilters = platform!=="all" || sourceKey!=="all" || from || to`

| State | Render |
|---|---|
| idle | Empty icon search, `输入关键词开始搜索`, `可以先用日期、来源和平台缩小范围，再输入关键词。搜索结果与 Agent 通过 search_items 得到的结果一致。` |
| loading | `SkeletonList rows={3}` (form stays visible) |
| validation — empty q | Note err/alert: `请输入关键词。日期、来源和平台是筛选条件，不能单独作为搜索条件。` |
| validation — bad range | Note err/alert: `起始日期晚于截止日期，请调整日期范围。` |
| done + hits | result bar + ArticleCard[] with `matchBadge` |
| done + 0 hits | Empty icon search, `没有匹配「{q}」的内容`, desc below, action `清除关键词与筛选` |
| request error | **new, §8** |

Zero-result desc: `当前筛选：{全部平台|平台标签} · {全部来源|sourceName} · {from||不限起始} 至 {to||不限截止}。可以放宽日期范围或清除筛选后重试。`

Result bar — left: `关键词「<b>{q}</b>」命中 <b>{n}</b> 条` + `（已应用筛选）`;
right: `范围：{from||不限起始} 至 {to||不限截止} · {全部平台|平台标签}`

**Match badge**, first hit wins in this order: `标题命中`, `来源命中`,
`作者命中`, `摘要命中`, else `正文命中`.

**Semantics note:** the prototype does naive substring matching over
title+summary+source+author then content. Production must use the bounded
exact/prefix/trigram policy from T10 — the *badge* semantics above still apply.

`清除关键词与筛选` toasts info `已清除关键词与筛选`.

### 3.7 Agent access

```
Note (brand/shield)      read-only guarantee
section Agent Token      head + [创建 Agent Token] → .fd-card → GrantRow[]
section 最近的只读调用    head → .fd-tablewrap > table.fd-table--cards
Note (warn/info)         rate limits
```

Read-only note: `<strong>Agent 访问是只读的。</strong>` then
`持有 Agent Token 的客户端只能<strong>查询</strong>内容与来源，无法修改资料库：不能订阅或退订、不能导入或删除内容、不能改变已读与收藏状态、不能访问账户与付款信息。`

Token section: H2 `Agent Token`; desc `生效中 {n} 个 · 累计 {n} 个。明文令牌只在创建时展示一次。`

**GrantRow**
```
.fd-grant[.is-revoked]
├── h3 {name} + [已撤销 err/close | 生效中 ok/check] + [只读 muted/eye]
├── p.fd-mono "{tokenPrefix}··········（明文不再展示）"      10 middle dots
├── scope: 创建于 {t} / (撤销于 {t} | 有效期至 {d})
│          / 来源范围：{全部来源|list} / 内容起始日期：{d}
│          / 最近调用：{t} / 累计调用 {n} 次
└── actions [撤销 ghostdanger-sm] | [已撤销 disabled title="令牌已撤销，无法再次使用"]
```

Token empty: icon key, `还没有 Agent Token`, `创建一个只读令牌，Codex、Claude 等 Agent 就可以通过 POST /mcp 查询你的资料库并返回可核对的引用。`, action primary `创建 Agent Token`.

Audit section: H2 `最近的只读调用`; desc `记录调用的工具、筛选条件、返回条数与耗时。不记录正文内容，也不记录令牌本身。`
Table caption (SR-only): `最近的 Agent 只读调用记录`. Columns / `data-label`:
`时间`, `令牌`, `工具`, `筛选条件`, `返回`, `耗时`. Cells: `{at}`,
`{grantName}`, mono `{tool}`, mono `{filters}`, `{n} 条`, `{n} ms`.
**The `data-label` attributes drive the mobile card transform — required.**
Audit empty: icon terminal, `还没有调用记录`, `Agent 通过 POST /mcp 查询之后，调用记录会出现在这里。`
Rate-limit note (warn/info): `限额：每个令牌每分钟 30 次请求，每个账户最多 4 个并发请求；单次列表最多返回 50 条，正文每次最多 4,000 字。超出限额返回 429 并附带重试时间。`

**Revoke confirm**: title `撤销「{name}」？`; desc `撤销立即生效。正在使用这个令牌的 Agent 下一次请求会收到 401，需要用新令牌重新配置。已经产生的调用记录会保留。此操作无法撤销。`; confirm `撤销这个令牌`. Toast ok `已撤销「{name}」` / `该令牌已立即失效。`

#### Create-token dialog

**Step 1 — form.** Dialog `wide`, title `创建 Agent Token`, desc
`生成一个只读令牌，供 Codex、Claude 等 Agent 通过 POST /mcp 查询你的资料库。`
1. Note brand/shield: `令牌<strong>只能读取</strong>。它无法订阅或退订、无法导入或删除内容、无法修改已读与收藏状态。`
2. Error note (err/alert) when validation fails.
3. Field `fd-token-name`, label `名称`, hint `建议写明使用它的客户端，方便之后单独撤销。`, autofocused. Default `Claude Code · 新令牌`.
4. Field `fd-token-days`, label `有效期`, hint `到期时间：{today + days}`,
   select `7 天` / `30 天（默认）` / `90 天`, default `30`.
5. Field `fd-token-from`, label `内容起始日期`, hint `令牌只能读取这个日期之后的内容，更早的内容对 Agent 不可见。`, `type="date" max={today}`, default today − 30d.
6. `<fieldset>` legend `来源范围` (styled `.fd-label`), radios named
   `fd-token-scope`: `全部来源（含一次性导入的内容）` (value all, default) and
   `仅选定的 RSS 来源` (value selected). When selected: chip row (padding-left
   24px), label prefixed `✓ ` when on. If no sources:
   `<p class="fd-hint">当前没有 RSS 订阅可选。</p>`
7. Note warn/info: `限额：每分钟 30 次请求，每账户 4 个并发；单次列表最多 50 条，正文每次最多 4,000 字。`

Footer: secondary `取消`; primary `创建令牌`, loadingLabel `正在生成令牌…`.
Validation: empty name → `请给这个令牌起一个名字，方便之后识别和撤销。`;
selected scope with nothing chosen → `请至少选择一个来源，或改为「全部来源」。`

**Step 2 — reveal.** Dialog `wide dismissible={false}`, title
`令牌已创建，只显示这一次`, desc `关闭这个窗口后，明文令牌无法再次查看。FeedDock 只保存它的哈希值。`
1. Note warn/alert/alert: `<strong>请立即复制并妥善保存。</strong> 如果丢失，只能撤销这个令牌并重新创建一个。`
2. `.fd-token` block: `<code class="fd-token__value">{token}</code>` +
   secondary-sm copy `复制` (autofocused). Dark slate background.
3. After copy — Note ok/checkCircle/status: `已复制到剪贴板。现在可以把它配置到 Codex、Claude 或其他 MCP 客户端。`
   Before copy — `<p class="fd-hint">复制之后才能完成创建，避免令牌丢失。</p>`
4. `<dl class="fd-deflist">`: `名称`/{name} · `权限`/`只读（list_items · search_items · get_item · list_sources）` · `来源范围`/{全部来源 | joined by 、} · `内容起始日期`/`{d} 起` · `有效期`/`{n} 天，至 {d}` · `接入方式`/`POST {origin}/mcp（Bearer 令牌）` in mono

Footer: single primary `我已保存，完成`, **disabled until copied**, with
`title="请先复制令牌"` while disabled.
Copy toast: ok `已复制到剪贴板` / `请立即保存，关闭后无法再次查看。` Falls back
gracefully when `navigator.clipboard` is unavailable.
Finish toast: ok `已创建「{name}」` / `只读 · 有效期至 {d} · 可随时撤销。`

Token display format: `fd_agent_` + 40 chars from an unambiguous alphabet
(no `I`, `O`, `l`). `tokenPrefix` = first 13 chars. **Generation and hashing
belong to T11 — the UI only renders what the service returns once.**

### 3.8 Account & privacy

Content column `--narrow` (880px).

**账号信息** — desc `通过邮箱 Magic Link 登录，不设置密码。`

| dt | dd |
|---|---|
| 邮箱 | `{email}` |
| 登录方式 | `邮箱 Magic Link（单次有效，15 分钟过期）` |
| 邀请码 | `{invite}` in mono |
| 加入时间 | `{joinedAt}` |
| 当前阶段 | `受控 Beta · ` + Badge brand `未开始收费` |
| 资料库规模 | `内容 {n} 条 · RSS 来源 {n} 个 · Agent Token {n} 个` |

**隐私** — desc `下面这些是 FeedDock 对你的数据所做的承诺与保留策略。`

| dt | dd |
|---|---|
| 阅读状态 | `已读、收藏与阅读进度默认私有，仅你本人和你授权的 Agent 可见。` |
| 模型训练 | `你的内容与阅读记录不用于训练任何模型。` |
| Agent 查询记录 | `仅记录工具名、筛选条件、返回条数与耗时，不记录正文，也不记录令牌本身。` |
| 原始响应保留 | `抓取到的原始响应默认保留 30 天，之后自动清理。` |
| 正文快照保留 | `无引用关系的清洗后快照默认保留 90 天。` |
| 删除生效范围 | `删除后，内容会同时从收件箱、搜索、Agent 查询结果和对象存储中移除。` |

Note warn/info: `保留期限是当前 Beta 的默认值，可能在正式发布前调整；调整会提前在产品内说明。`

**登录状态** — desc `退出登录只结束这台设备上的会话，不影响资料库内容，也不会撤销已创建的 Agent Token。`, action ghostdanger close `退出登录`.
Sign-out toast: info `已退出登录` / `资料库内容与 Agent Token 未受影响。`

**危险操作** (`.fd-danger`)
- Row 1: `删除全部一次性导入的内容` / `将永久删除 {n} 条通过公众号 / X 链接导入的内容及其正文快照。RSS 订阅与其内容不受影响。此操作无法撤销。` / ghostdanger trash `删除导入内容`
- Row 2: `注销账户并删除全部数据` / `将永久删除 {n} 条内容、{n} 个 RSS 订阅、{n} 个 Agent Token 及全部阅读状态与调用记录。所有生效中的 Agent Token 会立即失效。此操作无法撤销。` / danger trash `注销账户`

**Delete-imports confirm**: title `删除全部一次性导入的内容？`; desc
`将永久删除 {n} 条通过公众号 / X 链接导入的内容及其正文快照，它们会同时从收件箱、搜索和 Agent 查询结果中消失。RSS 订阅与其内容不受影响。此操作无法撤销。`;
confirm `永久删除 {n} 条`. Toast ok `已删除 {n} 条导入内容` / `已从搜索与 Agent 查询结果中移除。`

**Delete-account dialog** (distinct from the generic confirm):
- Title `注销账户并删除全部数据？`
- Desc `将永久删除 {n} 条内容、{n} 个 RSS 订阅、{n} 个生效中的 Agent Token，以及全部阅读状态与调用记录。所有 Agent 会立即失去访问权限。此操作无法撤销。`
- Body: Note err/alert `这是不可逆操作。删除后无法通过邀请码或客服恢复任何内容。`
  + Field `fd-delete-confirm`, label `输入 {email} 以确认`, hint
  `必须与账号邮箱完全一致才能继续。`, `<input class="fd-input fd-input--mono" autoComplete="off" data-autofocus>`
- Footer: secondary `取消`; danger `永久删除账户` **disabled until the typed
  value, trimmed and lowercased, equals the account email**
- Toast ok `账户已注销` / `全部内容、订阅与令牌已删除。`

**Generic confirm dialog** (unsubscribe, revoke, delete-imports): body always
contains Note err/alert `请确认影响范围后再继续。` Footer: secondary `取消` +
danger `{confirmLabel}` (autofocused).

---

## 4. Data shapes

These are the *view* shapes. Service ports must satisfy them; they are not the
DB schema.

```ts
type Platform = "rss" | "wechat" | "x";
type Origin   = "subscription" | "import";     // no wechat_subscription

interface ItemView {
  id: string;
  platform: Platform;
  origin: Origin;
  sourceId: string | null;        // null for imports
  sourceName: string;
  author: string;
  title: string;
  summary: string;
  date: string;                   // YYYY-MM-DD — grouping + range filter
  published: string;              // YYYY-MM-DD HH:mm — display + sort
  words: number;
  minutes: number;
  read: boolean;
  saved: boolean;
  isNew?: boolean;                // 新增 badge, cleared on first open
  parse: "ready" | "partial";
  parseNote?: string;             // required when parse === "partial"
  originalUrl: string;
  fetchedAt: string;
  parser: string;                 // e.g. "rss-parser v1.4.0"
  content: string[];              // paragraphs, plain text
}

interface SourceView {
  id: string;
  name: string;
  feedUrl: string;
  siteUrl: string;
  health: "ok" | "error" | "paused";
  paused: boolean;
  lastAttempt: string;
  lastSuccess: string;
  failStreak: number;
  note: string;                   // "" when healthy
  subscribedAt: string;
  unreadCount: number;
}

interface GrantView {
  id: string;
  name: string;
  createdAt: string;
  expiresAt: string;
  scopeSources: "all" | string[];  // prototype pre-joined; return an array
  fromDate: string;
  revoked: boolean;
  revokedAt?: string;
  lastUsedAt: string | null;       // null renders 尚未使用
  callCount: number;
  tokenPrefix: string;             // 13 chars
}

interface AuditView {
  id: string;
  grantId: string;
  grantName: string;
  tool: "list_items" | "search_items" | "get_item" | "list_sources";
  filters: string;                 // pre-rendered; "—" when none
  rows: number;
  ms: number;
  at: string;
}

interface AccountView {
  name: string; email: string; invite: string; joinedAt: string;
}
```

**`rel`** (`2 小时前`) is precomputed in the mock. Derive it client-side from
`published` so it stays correct without a refetch.
**Avatar initial** is hardcoded `陈` in the prototype — derive from `name[0]`.
**`FD_TODAY = "2026-07-28"`** is a mock constant — replace with a real clock.

Helper functions to port: `platformLabel`, `originLabel` (subscription →
`RSS 订阅`, import → `单篇导入`), `isSubscribed`, `dayLabel`, `groupByDay`,
`sortItems`, `readingCost`, `sourceOptions`, `matchField`, `addDays`, `hostOf`
(strips `www.`).

**`sourceOptions` is derived from items, not sources** — otherwise
import-only sources never appear in the filter dropdown.

---

## 5. Responsive rules

Two breakpoints. Everything else fluid.

### Base (≥1200px)
`--page-gutter: 32px`, `--sidebar-global: 232px`, `--drawer-w: min(720px, 46vw)`,
`--content-max: 1280px`, narrow 880px, `--reading-max: 720px`.
`.fd-mobilebar`, `.fd-bottomnav`, `.fd-navdrawer` are `display: none`.

### ≤1199px — tablet
- `--page-gutter: 24px`; `--sidebar-global: 64px`; `--drawer-w: min(720px, 68vw)`.
- **Sidebar collapses to an icon rail**: brand name, nav labels, nav counts and
  the account meta all hidden; items center-justified with zeroed horizontal
  padding. The `title` attribute is the only remaining affordance.
- Add screen sections stack to one column.
- Hero → single column, gap 40px; hero title 44px → 40px.
- Dialog width → `calc(100vw - 48px)`.

### ≤767px — mobile (incl. 390px)
`--page-gutter: 16px`.

**Chrome**
- `.fd-shell` single column; sidebar `display: none`.
- `.fd-mobilebar` flex, sticky, `z-index: 100`, padding `8px 16px` with
  `padding-top: calc(8px + env(safe-area-inset-top))`. Its icon buttons forced
  to 44×44.
- `.fd-topbar` becomes **static** (loses sticky, blur, background, border),
  stacks vertically, padding `16px 16px 12px`. Title 20px → 18px. Header action
  buttons get `flex: 1 1 auto` and `min-height: 44px` — the primary action
  becomes a full-width 44px button under the title.
- `.fd-content` padding → `0 16px 96px` (clears the bottom nav).
- `.fd-bottomnav` grid, **5 equal columns**, fixed bottom, `z-index: 100`,
  `padding-bottom: env(safe-area-inset-bottom)`. Items column-flex,
  `min-height: 56px`, `min-width: 44px`, **font-size 11px**, tertiary color;
  active turns brand-hover + 600. Badge absolutely positioned
  `top: 4px; left: 50%; margin-left: 4px`, brand bg, white, 10px,
  `padding: 3px 5px`, pill radius.
- `.fd-navdrawer` becomes a **bottom sheet**: fixed left/right/bottom,
  `max-height: 80vh`, `overflow-y: auto`, top corners 16px,
  `padding: 16px 16px calc(24px + env(safe-area-inset-bottom))`, sheet-in
  animation (translateY 16px → 0, 200ms). Nav items restored to left-aligned
  48px rows with visible labels and counts.

**Inbox controls**
- `.fd-tabs`: gap 24px → 16px; gains a horizontal **fade mask**
  `linear-gradient(90deg, transparent 0, #000 12px, #000 calc(100% - 12px), transparent 100%)`
  and `scroll-padding-inline: 16px`. `.fd-tab` min-height 40px → **44px**.
- `.fd-filters` becomes a **horizontal scroller**: `flex-wrap: nowrap;
  overflow-x: auto; scrollbar-width: none; padding-bottom: 4px`, webkit
  scrollbar hidden. **Every direct child and every child of
  `.fd-filters__group` gets `flex: none`** — without this, CJK chip labels
  collapse to one glyph per line. The select inside gets
  `width: auto; min-width: 150px`. `.fd-chip` min-height 32px → **36px**.

**Article cards**
- `.fd-item`: padding 16px → 12px, gap 16px → 8px, **`flex-direction: column`**
  — the bookmark action moves below the body.
- `.fd-item__actions`: `flex-direction: row; align-self: flex-start`.
- `.fd-iconbtn` globally 32×32 → **44×44**.

**Reader drawer**
- `width: 100%; left: 0; border-left: 0`,
  `padding-bottom: env(safe-area-inset-bottom)`, animation swapped from
  slide-in-from-right to sheet-in.
- Head padding `12px 16px` + `padding-top: calc(12px + env(safe-area-inset-top))`;
  body 16px; foot `12px 16px` with all footer buttons `min-height: 44px`.
- Reader title 24px → **20px**.
- `.fd-prov` collapses to one column, gap 4px, `dt { margin-top: 8px }`.

**Dialogs**
- **Full-screen**: `inset: 0; transform: none; width: 100%; max-height: 100vh;
  border-radius: 0`, plain fade animation.
- Head `padding-top: calc(24px + env(safe-area-inset-top))`.
- Foot `padding-bottom: calc(16px + env(safe-area-inset-bottom))` and
  **`flex-direction: column-reverse`** — primary stacks above 取消 — every
  button `width: 100%; min-height: 44px`.

**Toasts**
- `left: 16px; right: 16px; width: auto`,
  `bottom: calc(72px + env(safe-area-inset-bottom))` — clears the bottom nav.
- `.fd-toasts--aside` (reader open):
  `bottom: calc(var(--fd-drawer-foot-h, 72px) + 12px + env(safe-area-inset-bottom))`
  — uses the height the Drawer publishes so the toast never covers the drawer's
  action bar.

**Rows and tables**
- `.fd-srcrow`, `.fd-grant`, `.fd-danger__row` → `flex-direction: column`.
  Source actions become full-width, left-justified, buttons 44px.
- `.fd-section` padding 24px → 16px, radius 12px → 8px.
- `.fd-deflist` → single column, gap 4px, `dt { margin-top: 8px }`.
- **`.fd-table--cards` becomes a stacked card list**: table/tbody/tr/td all
  `display: block; width: 100%`; `thead` hidden; each `tr` gets a bottom border
  and `padding: 8px 0`; each `td` loses its border, gets `padding: 4px 16px`,
  and gains a `::before` of `attr(data-label) "："` in tertiary 12px.

**Landing**
- Hero padding `32px 16px`, gap 32px; title → **32px**; lead 18px → 16px.
- Login card padding 32px → 20px, radius 16px → 12px, buttons 44px.
- Boundary inner single column, gap 24px, padding `32px 16px`.
- `.fd-lnav__links` hidden; nav CTA `min-height: 44px`.

### prefers-reduced-motion
All animations `.01ms`, iteration 1, transitions `.01ms`,
`scroll-behavior: auto` — all `!important`. Tabs additionally checks the media
query in JS to use `behavior: "auto"`.

**Touch-target rule:** every interactive element 32–40px on desktop becomes
44px on mobile.

---

## 6. Design tokens

Already catalogued by ui-tokenize (64 vars). Values live in `app/globals.css`
`:root`. Never hardcode — use `var(--token)`.

Colors: `--color-brand-primary #2497ea`, `--color-brand-hover #167cc4`,
`--color-brand-soft #eaf5fd`, `--color-text-{primary #2d2d2d, secondary #6b7280,
tertiary #9ca3af, inverse #fff}`, `--color-surface-{page #f3f3f3, container
#fff, subtle #f7f8fa, hover #f1f5f9}`, `--color-border-{default #e5e7eb, strong
#cbd5e1}`, `--color-success #22a06b`, `--color-warning #d97706`,
`--color-error #d64545`, `--color-danger #c93636`, `--color-focus-ring #66b8f0`,
`--color-overlay rgba(15,23,42,.48)`.

Type: `--font-sans`, `--font-mono`; `--text-xs 12` `-sm 14` `-base 16` `-lg 18`
`-xl 20` `-2xl 24` `-3xl 32`; `--line-tight 1.25` `-normal 1.5` `-reading 1.75`.

Space `--space-1..16` (4,8,12,16,20,24,32,40,48,64);
radius `sm 4 / md 8 / lg 12 / xl 16 / pill 999`;
`--border-default`, `--shadow-float`, `--shadow-overlay`.

Layout: `--content-max 1280px`, `--reading-max 720px`, `--drawer-w`,
`--sidebar-global`, `--page-gutter`.
Z: `--z-sticky 100`, `--z-dropdown 400`, `--z-overlay 800`, `--z-dialog 900`,
`--z-toast 1000`.

Runtime: `--fd-drawer-foot-h` set by the Drawer on `documentElement`,
consumed by the mobile toast offset, fallback 72px.

### Tokens to add (prototype hardcodes these)

The prototype hardcodes ~40 values. Promote at minimum:
- Component-state colors: primary-disabled `#a9d5f5`; danger hover `#ab2c2c` /
  disabled `#e5b4b4`; ghostdanger border `#edc9c9` / hover `#fdf2f2`.
- Badge and note palettes (ok `#eaf7f1`/`#1a7d53`/`#c7e9d9`; warn
  `#fdf4e7`/`#a35c05`/`#f2ddba`; err `#fdf0f0`/`#b23b3b`/`#f2d0d0`; brand
  `#cbe6fa`/`#1c5f8f`).
- Skeleton shimmer `#eef1f4` → `#f6f8fa`.
- Item hover `#fdfdfe`; new-item border `#b9dcf7` / bg `#fbfdff`.
- Token reveal block `#1f2937` / `#e5e7eb`.
- Platform dots: rss `#d97706` (= warning), x `#2d2d2d` (= text-primary) —
  alias these rather than duplicating.
- **Motion tokens — the prototype has none.** Define duration/easing:
  140ms ease-out (default), 160ms (fade/toast), 180ms (dialog pop),
  200ms cubic-bezier(.2,.8,.2,1) (sheet), 220ms same easing (drawer slide),
  700ms linear (spinner), 1200ms ease-in-out (shimmer).

Note `--gradient-ai` and `--text-3xl` are defined but unused; `#333333` on
reader prose deliberately differs from `--color-text-primary #2d2d2d`.

Inline styles in the prototype JSX should become classes — do not port
`style={{…}}` for layout.

---

## 7. W2 exclusion

**In scope, must ship:** WeChat single-article import — the `公众号文章` Add
section, `platform: "wechat"` items with `origin: "import"`, the `微信公众号`
filter chip, the wechat icon, `.fd-platform--wechat`.

**Excluded entirely:** account subscription, credential authorization, QR
scanning, and every entry point to them.

Do not port:
- `screens-w2.jsx` and its five exports.
- Any `w2` state, `toggleW2`, `w2Authorize`, `w2Revoke`, `w2SimulateExpiry`,
  `w2Search`, `w2Subscribe`.
- The floating W2 toggle pill and its copy in the mobile 更多 sheet.
- `origin: "wechat_subscription"` — the union is `subscription | import` only.
- `Source.platform` and `Source.fakeid` — with W2 gone every source is RSS, so
  the `s.platform !== "wechat"` filter disappears entirely.
- Sources screen: the 公众号订阅 group, the `W2 · Gate 后切片` tag, the
  `授权状态` stat, the `授权失效` / `风控暂停` badges and their hints, the
  two-group explainer variant.
- Account screen: the 微信授权 section.
- Reader: the `wechat_subscription` provenance branch and the
  `公众号订阅刷新（授权会话）` 获取方式 value.
- Inbox and Sources result bars: the `公众号来源 {n}` fragment.
- `.fd-kind--w2`, `.fd-section--w2`, `.fd-w2banner*`, `.fd-flagpanel*`,
  `.fd-switch*`, `.fd-mpcand*`, `.fd-avatar--mp` and their mobile overrides.

**Keep** the `wechat` icon and the PlatformTag wechat branch — imported WeChat
articles need them.

Surviving 公众号 copy is import-only and reinforces the boundary: `公众号文章`,
`公众号文章链接`, the mp.weixin.qq.com desc, the 单篇导入 boundary note, the
unsupported/deleted messages, `微信公众号` (platform label),
`不持续跟踪公众号：公众号文章只能按单篇公开链接导入` (landing), the danger-zone
delete copy, and the Add subtitle `RSS 持续订阅 · 公众号与 X 单篇导入`.

**Frozen types only** live in `src/modules/connectors/credentialed.ts` —
no UI, no route, no flag.

---

## 8. States the prototype omits — design these

Confirmed in scope. Match the prototype's visual language.

| Screen | Missing | Required |
|---|---|---|
| Inbox | error | Note err/alert + retry action; keep tabs and filters usable |
| Sources | loading, error | SkeletonList; error Note with retry |
| Agent | loading, error | SkeletonList for both token and audit lists |
| Account | loading, error | Skeleton for the stats row |
| Search | request failure | Note err/alert, distinct from the two validation errors |
| Reader | 404 / deleted | Empty state inside the drawer: the item was removed; offer the original URL when known |
| Reader | loading | Skeleton in the drawer body for hard loads |

The prototype's Inbox `loading` prop is hardcoded `false` — the skeleton path
exists but is never exercised. Wire it to real pending state.

---

## 9. Accessibility contract — preserve exactly

- Skip link `跳到主要内容`, visually hidden until focused.
- `aria-current="page"` on the active nav item.
- Full `role="tablist"` / `"tab"` / `"tabpanel"` wiring with `aria-controls`.
- `aria-modal` + focus trap + focus restore on drawer, dialog and mobile sheet.
- `aria-live="polite"` on toasts and skeletons; `aria-busy` on loading lists.
- `aria-pressed` on chips and bookmark buttons.
- `.fd-sr` SR-only text beside every visual-only indicator (unread dot,
  bottom-nav badge).
- `<caption>` on the audit table.
- `:focus-visible` 2px ring at 2px offset.
- **Fix the prototype gap:** `Field` must set `aria-describedby` on its control.
- Keyboard: Escape closes the topmost layer; Enter submits every single-field
  form.
