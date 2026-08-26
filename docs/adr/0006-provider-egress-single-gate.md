# ADR-0006: 所有 provider 的出站 HTTP 收敛到 `_http.py` 一个出口，只许 http(s)、拒绝 30x 跳转、key 永不下发浏览器、永不发往请求方指定的 base_url

| 字段 | 值 |
|---|---|
| Status | Accepted |
| Decision date | 2026-08-25（008 分支，尚未提交——`src/reader3_app/ai/providers/_http.py` 是未跟踪新文件，`git log` 无记录；`ai/config.py`、`web/server.py`、`ai/providers/gemini.py` 同批为已跟踪但未提交的修改，见 `git status`） |
| Recorded date | 2026-08-25 |
| Record type | Retrospective |
| Original rationale known | Yes |
| Confidence | High |
| Current compliance | Full |
| Evidence | `src/reader3_app/ai/providers/_http.py:1-11`（模块 docstring）、`:22-24`（`ALLOWED_SCHEMES`）、`:27-58`（`RedirectNotAllowed` / `_NoRedirectHandler`，取舍陈述在 `:39`）、`:60-83`（`validated_url` 的 `None` vs `""` 语义）；`src/reader3_app/ai/config.py:19-26`（`ProviderSettings` 无 `api_key` 字段）、`:207,212-221`（只留 `api_key_configured: bool`）；`src/reader3_app/web/server.py:1448-1462`（`_public_provider_config` 对外只吐 `api_key_configured`）、`:1789-1832`（`/api/settings/providers/{name}/test`，换 endpoint 必须自带 key，`:1804-1814` 注释点名 `web/C1`）；`src/reader3_app/ai/providers/gemini.py:61-63`（key 走 `x-goog-api-key` 头，不进 URL）；`src/reader3_app/ai/providers/{anthropic,gemini,ollama,openai,openrouter}.py` 均 `from ._http import ...`（五家全接入）；`tests/unit/test_provider_egress.py`（E1-E4，`_http.py` 层）；`tests/contract/test_provider_test_route.py`（E5-E7，路由层，`:5` 复述 `web/C1`） |
| Confirmation | `tests/unit/test_provider_egress.py`（E1 拒绝非 http(s) scheme、E2 五家 provider 出网前全部拒掉 `file:` URL、E3 重定向不带 `Authorization` 到第二跳、E4 Gemini key 不进 URL）；`tests/contract/test_provider_test_route.py`（E5 换 endpoint 不带 key 直接 400、E6 盘上的 key 绝不出现在发往请求指定 URL 的调用里、E7 不换 endpoint 时行为不变）。两个文件均已存在（`ls` 已核） |

## Context and Problem Statement

五家 provider（anthropic/openai/gemini/ollama/openrouter）都要把请求发到一个可能由用户设置甚至由单次请求指定的 `base_url`。这条出网路径一旦失守，泄漏的是用户的 API key。008 分支之前，四家（除 anthropic 外，它的 URL 是硬编码常量 `ANTHROPIC_MESSAGES_URL`，`anthropic.py:9`，不接受用户可控的 `base_url`，因此不需要过 `validated_url`）各自抄了一份 `_post_json`，`base_url` 校验、重定向处理、错误体解析四份各写各的。

`/api/settings/providers/{name}/test` 路由（`server.py:1789`）让问题不只是「四份重复代码」，而是「用户可以在单次请求里指定 `base_url`」——这条路由本身还没有鉴权（见 Decision Drivers 第三条），使得出网口的安全性不能只靠「代码写对了」，还要靠路由层再拦一道。

- **Observed State**：现在只有 `_http.py` 一个出口，且五家 provider 全部接入——`anthropic.py:6`、`gemini.py:6`、`ollama.py:5`、`openai.py:6`、`openrouter.py:6` 均 `from ._http import ...`。具体收口点：
  1. `post_json` 用的 opener 挂 `_NoRedirectHandler`，对 30x 一律拒绝而不跟随（`_http.py:31-58`，异常里带上原 URL 与目标 URL 方便定位）。
  2. `validated_url` 只放行 `http`/`https`（`_http.py:60-83`），且区分 `base_url=None`（调用方未配置，用 `default`）与 `base_url=""`（配置成了空字符串，直接抛 `ValueError`）——合并这两种情况等于把打错的配置静悄悄换成默认值（`_http.py:63-64,69`）。
  3. `ProviderSettings` 数据结构层面就没有 `api_key` 字段，只有 `api_key_configured: bool`（`config.py:19-26`，`:207,212-221` 是取值处），API key 原值无法经由 `/api/settings` 系列路由回传浏览器；`server.py:1448-1462` 的 `_public_provider_config` 对外只吐这个布尔值。
  4. `/api/settings/providers/{name}/test` 换了 endpoint 就必须自带 key，盘上存的 key 绝不发往请求指定的地址；回落检查发生在发请求**之前**（`server.py:1789-1832`，尤其 `:1808`）。
  5. Gemini 的 key 走 `x-goog-api-key` 请求头，不拼进 URL 查询串（`gemini.py:61-63`）。
- **Original Rationale**：写在代码里，出处明确。`_http.py:3-6` 陈述四份重复实现的后果——「一个像 #74 这样的修复要改四遍，而且不会都改到」；`_http.py:34-39` 陈述为什么不跟随重定向——urllib 默认跨 host 保留 `Authorization` 头，而 LLM chat/completions 接口正常路径不该出现 30x，取舍是「安全 vs 无人使用的兼容」；`server.py:1804-1814` 陈述为什么 `/test` 路由必须在发请求前就拒绝换 endpoint 不带 key 的组合——该路由本身无鉴权（`web/C1`），回落挪到发完之后，key 已经出去了。
- **Current Assessment**：五处收口（scheme 白名单、拒跳转、key 不回传浏览器、`/test` 路由自带 key 校验、Gemini key 走 header）今天都有对应测试锁定（见 Confirmation），不是只存在于 docstring 里的意图。

## Decision Drivers

- 四份重复的 `_post_json` 意味着一处修复要改四遍，且历史上不会都改到（`_http.py:3-6`）。
- urllib 默认跟随重定向并跨 host 保留 `Authorization` 头：白名单拦得住第一跳，拦不住第二跳（`_http.py:34-37`）。
- `/api/settings/providers/{name}/test` 路由本身没有鉴权（`web/C1`），只要还开着，任何能对本机发请求的一方就能探测；能不能顺手拿到用户存的 key，是这条路由自己必须守住的第二道线（`server.py:1804`）。
- Gemini 官方支持 key 走 header（`gemini.py:62`），而 query 串会被沿途反向代理、CDN、公司出口网关写进访问日志。
- 四家的错误 JSON 形状不一样（`error.message` / `message` / 顶层字符串，`_http.py:8-9`），强行在单出口里统一解析会把「解析不到就当成空回答」（`ai/73`）这类 bug 藏得更深——这条边界反过来限定了单出口该收多窄：只收「把字节取回来」，不收错误体语义。

## Considered Options

1. **单出口 `_http.py` + 拒绝重定向**（选定）——`post_json`/`validated_url` 是五家 provider 唯一的出网路径，scheme 白名单和 30x 拒绝只需要写一次、测一次。代价：`_http.py` 成为单点，改坏它影响全部五家；这个代价由 `tests/unit/test_provider_egress.py` 的 E1-E4 和 `tests/contract/test_provider_test_route.py` 的 E5-E7 兜底——单点的风险换来的是单点的测试覆盖，而不是四处都测不全。
2. **每家 provider 各自处理出网逻辑**——现状之前的做法。为什么不：`_http.py:3-6` 记录的正是这条路径的失败案例——四份 `_post_json` 各自维护，一处安全修复（如 scheme 白名单）要改四遍，历史上没有都改到；五份重复只会把泄漏面再乘以一。
3. **跟随重定向但剥掉跨 host 的 `Authorization` 头**——为什么不：`_http.py:38-39` 的取舍陈述——LLM 的 chat/completions 接口正常路径上一次都不该出现 30x，这里权衡的不是「安全 vs 兼容」，而是「安全 vs 无人使用的兼容」；维护一条几乎用不到的兼容路径，换来的是每次审计都要重新确认「剥头」逻辑本身没有漏洞。

## Decision Outcome

`post_json`/`validated_url`（`_http.py:60-121`）是全部五家 provider 出站 HTTP 的唯一入口，边界如下：

- **只许 http(s)**：`validated_url` 拒绝其余 scheme，包括 `file://`（会让 `urlopen` 读本地文件再顺着响应路径回传）与 `ftp://`/`gopher://`（`_http.py:22-23` 的注释点名了这两个）。
- **拒绝 30x**：`post_json` 用的 opener 挂 `_NoRedirectHandler`，对 301/302/303/307/308 一律抛 `RedirectNotAllowed` 而不跟随。
- **key 永不下发浏览器**：`ProviderSettings` 数据结构层面不携带 `api_key` 原值，对外路由只暴露 `api_key_configured: bool`。
- **key 永不发往请求方指定的 base_url**：`/api/settings/providers/{name}/test` 换 endpoint 必须自带 key，盘上存的 key 绝不用于请求指定的地址，且检查发生在出网之前。
- **Gemini key 走 header**：不拼进 URL 查询串。

**明确不做**：不统一各家的错误体解析（四家 JSON 形状不同，强行统一会把「解析不到就当空回答」的 bug 藏得更深，`_http.py:8-10`）；不给 `/api/*` 路由加鉴权——那是一个更大范围的决定，本 ADR 只负责「出网口本身不能成为泄漏点」，不负责「谁能调用这个出网口」（见 Negative）。

## Consequences

### Positive
- scheme 白名单和拒跳转只写一次、测一次，四份历史重复（`_http.py:3-6` 点名的 `ai/74`/`ai/75`）不会再各自漂移。
- API key 的「绝不回传浏览器」「绝不发往请求指定地址」两条约束落在类型（`ProviderSettings` 没有该字段）和路由（`_public_provider_config`、`/test` 路由的回落检查）两层，不依赖每个调用点自觉遵守。
- `validated_url` 的 `None`/`""` 区分（`_http.py:63-64`）让「没配置」和「配错了」不会互相掩盖，配置错误会在进入网络调用前就报出被拒的原值，而不是悄悄退回默认值。

### Negative
- 依赖 30x 跳转的自建网关/反向代理无法通过这条出网路径工作——`_http.py:39` 把这条兼容性明确判定为「无人使用」，一旦判断有误，用户侧的失败模式是连接被拒且没有绕过口子（`RedirectNotAllowed` 直接抛出，`_http.py:47-50`）。
- **`/api/*` 本身仍然没有鉴权**——这是本决定成立的前提缺口，不是本决定的解决范围。`server.py:1804` 的注释与 `tests/contract/test_provider_test_route.py:5`（`web/C1`）都记着这件事：本机任意进程或做 DNS rebinding 的网页仍能调用 `/api/settings/providers/{name}/test`。单出口挡住的是「key 被换了个地址的请求带出去」，挡不住本机上已经能打这条路由的调用方；`web/C1` 本身在 `docs/plans/` 里没有独立的定义处，唯一记录就是这两处代码内注释和测试 docstring。
- 四家错误体解析仍各自为政（`_http.py:8-10`）——这是本决定刻意留下的边界，不是遗漏，但意味着「解析不到就当空回答」这类 bug（`ai/73`）目前不受本 ADR 的任何约束保护。

### Neutral
- 五家 provider 是模块函数 + kw-only 参数 + `frozen` 的 `ProviderResponse`（`types.py:7-12`），没有共同基类；`server.py` 里 `_call_provider`（`:1310` 起）用 `if provider_name == "..."` 手写链路分发（`:1321`/`:1331`/`:1342`/`:1351`/`:1362`，对应 anthropic/gemini/ollama/openai/openrouter）。这是 Observed State，理由 Unknown，不在本 ADR 决定范围内。

## Revisit When

- 新增第六家 provider：确认它是否也接入 `_http.py`，还是有正当理由绕开。
- `/api/*` 引入本机鉴权：届时「单出口挡外泄、不挡本机滥用」这条 Negative 的前提改变，`/test` 路由那道「换 endpoint 必须自带 key」的第二道线是否还需要，需要重新评估。
- 出现一个必须支持 30x 跳转的正式用例（例如某厂商网关强制走跳转）：需要重新评估「安全 vs 无人使用的兼容」这条取舍是否仍然成立。

## Related

- ADR-0012（编号预留于 `docs/adr/0000-use-adrs.md`「首批 0001–0013」，与本决定的后续关系待该文写出后核对）。
- `docs/ai-providers-and-privacy.md`——记录的是「什么内容发往云端 provider」，不覆盖「key 本身怎么被保护」；两者互补，互不复述。
- 本 ADR 不取代 `docs/plans/` 中任何一段——检索 `web/C1`、`WI-11`、`ai/74`、`ai/75` 未在 `docs/plans/` 下命中；这些 finding 的唯一记录是 `_http.py`/`server.py` 的行内注释与 `tests/unit/test_provider_egress.py`、`tests/contract/test_provider_test_route.py` 的 docstring，本 ADR 是它们的第一份索引，不是替换。
