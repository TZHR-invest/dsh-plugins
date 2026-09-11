# dsh-web-search-metaso

Metaso (秘塔AI搜索) providers for the DeepSeek Harness web seam (`ctx.web`).

Upgrades the built-in `web_search` / `web_fetch` tools with Metaso's search API — no new tool names to learn:

- **`web_search` returns page summaries**: Metaso's `summary` (long) / `snippet` (short) map to each source's snippet field — the model gets excerpts plus cited URLs, not just a link list.
- **`web_fetch` reads full pages**: Metaso `/reader` converts any web page to markdown.
- **Dedicated retrieval endpoint**: one search = one HTTP call (≈ ¥0.03), no model turn consumed.
- **Multi-scope search**: webpage / document / paper / image / video / podcast, via the `scope` config or a `scope:paper keywords` query prefix.

> Registers `WebSearchProvider` (id `metaso`) and `WebFetchProvider` (id `metaso-reader`) on the same `ctx.web` seam as `@deepseek-ai/dsh-web-search-deepseek` — switch backends anytime.

## Install

```bash
tar xzf dsh-web-search-metaso-install.tar.gz && cd dsh-web-search-metaso-install
bash install.sh --restart          # interactive: enter your Metaso API key
```

- Get an API key: <https://metaso.cn/search-api/api-keys> (`mk-` prefix)
- Non-interactive: `bash install.sh --metaso-api-key mk-xxx --restart`
- Env-var based: `bash install.sh --metaso-api-key-env METASO_API_KEY`
- Install without switching the search backend: `bash install.sh --no-switch`
- The installer runs contract preflight + headless boot smoke test before `--restart`; a plugin problem aborts the restart automatically.

## Uninstall

```bash
bash install.sh --uninstall   # removes wiring and copies, then restart dsh
```

## Config

Written to the profile's `cordis.patch.yml` by the installer:

```yaml
- insert:
    - id: web-search-metaso
      name: 'dsh-web-search-metaso'
      config:
        apiKey: 'mk-xxx'          # or apiKeyEnv: 'METASO_API_KEY'
        scope: 'webpage'
- id: web
  config:
    searchProvider: metaso        # delete this block to keep deepseek-official
    fetchProvider: metaso-reader  # ⚠️ 必写，见下方说明
```

> **⚠️ `fetchProvider` 必须一起写**（2026-09-11 四台机器实测）
>
> profile patch 的 `config` 块对基础层是**整体替换**而非合并。基础层本身设有
> `fetchProvider: http`，若这里只写 `searchProvider`，`fetchProvider` 会被吞掉 →
> `http` 与 `metaso-reader` 两个 fetch provider 同时可用 → 运行时抛：
>
> ```
> multiple usable web providers are registered (http, metaso-reader); configure one explicitly
> ```
>
> **结果是 `web_fetch` 完全不可用**（工具调用直接失败，与目标 URL 无关）。
> 二者择一：`metaso-reader`（秘塔服务端抓取，返回干净 markdown，不受本地 DNS
> / fake-ip 影响）或 `http`（本地直连，免费，但会拒绝解析到非公网 IP 的域名——
> 在 OpenClash fake-ip 网络下境外站点基本都取不到）。

Optional: `apiKeyEnv` (default `METASO_API_KEY`, also resolved via the credentials domain), `baseURL` (default `https://metaso.cn/api/v1`), `scope` (default `webpage`), `includeSummary` (default true), `includeRawContent` (default false), `maxResults` (default 10, 1-100).

## 会话遥测事件（`web/metaso-search-request`）为何要判断宿主词汇表

本插件每次搜索会向会话日志追加一条遥测事件 `web/metaso-search-request`。**dsh 的会话
格式迁移器只认识宿主内置的事件类型白名单**，遇到白名单外的类型会**拒绝整段会话**：

```
format v0 contains unknown historical event type "web/metaso-search-request" at seq N;
migration refuses unknown historical events even when ignorable
```

→ 后果是**凡是用过本插件搜索的历史会话都打不开**（2026-09-11 实发：某机 10 个会话受影响）。
且 `session.append` **不校验类型**，所以写入时一切正常，故障只在**读回**时才暴露。
(`ignorable` 也救不了：v0 迁移路径下 `allowLegacySteering` 恒为 true。)

**因此 `recordRequest` 会先用动态 import 取宿主的 `KNOWN_SESSION_EVENT_TYPES`，
宿主不认识就跳过这条遥测** —— 宁可少一条日志，也不让会话读不出来。

> 用动态 import 而非静态：静态 import 解析失败会**直接毁掉整个插件**；动态失败只跳过遥测。
> 已打开的**旧会话**（日志里已含该事件）需要宿主侧补丁才能读回，
> 见 meshdeck 仓 `scripts/dsh-reapply-session-event-patch.py`。
