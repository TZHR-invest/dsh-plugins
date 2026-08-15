# dsh-web-search-metaso

Metaso（秘塔AI搜索）providers for DeepSeek Harness web seam（`ctx.web`）。

让 dsh 自带的 `web_search` / `web_fetch` 工具直接获得秘塔能力，无需学习新工具名：

- **`web_search` 带综合摘要**：秘塔的 `summary` 映射为工具返回的 `content` 字段，模型直接拿到答案 + 来源链接，不再只是链接列表；
- **`web_fetch` 读网页全文**：秘塔 `/reader` 把任意网页转成 markdown 返回，补上"只能拿到片段"的短板；
- **纯检索端点**：一次搜索 = 一次 HTTP 调用（约 3 分钱/次），不消耗模型调用；
- **多范围搜索**：webpage / document（文库）/ paper（学术论文）/ image / video / podcast，由配置 `scope` 决定，或在查询里用 `scope:paper 关键词` 前缀临时切换。

> 原理：注册 `WebSearchProvider`（id: `metaso`）与 `WebFetchProvider`（id: `metaso-reader`）到 `ctx.web`，与官方 `@deepseek-ai/dsh-web-search-deepseek` 同一 seam，可随时切换后端。

## 安装

```bash
tar xzf dsh-web-search-metaso-install.tar.gz && cd dsh-web-search-metaso-install
bash install.sh --restart          # 交互输入 Metaso API key
```

- API key 获取：<https://metaso.cn/search-api/api-keys>（`mk-` 开头）
- 非交互安装：`bash install.sh --metaso-api-key mk-xxx --restart`
- 只用环境变量：`bash install.sh --metaso-api-key-env METASO_API_KEY`
- 装插件但**不切换**搜索后端（保留 deepseek 官方搜索）：`bash install.sh --no-switch`
- 安装器内置：契约预检（preflight）+ headless 试启动冒烟 + 卸载回滚；`--restart` 会先冒烟，插件有问题自动中止，不碰正式服务。

## 验证

重启后新开会话，让 agent 执行 `web_search("DeepSeek V4 发布")`——若返回带 `content`（综合摘要）即为生效。或：

```bash
curl -s https://metaso.cn/api/v1/search \
  -H "Authorization: Bearer mk-xxx" -H "Content-Type: application/json" \
  -d '{"q":"DeepSeek V4","scope":"webpage","size":3}'
```

## 配置

安装器写入 profile 的 `cordis.patch.yml`：

```yaml
- insert:
    - id: web-search-metaso
      name: 'dsh-web-search-metaso'
      config:
        apiKey: 'mk-xxx'          # 或 apiKeyEnv: 'METASO_API_KEY'
        scope: 'webpage'          # webpage|document|paper|image|video|podcast
# web_search 后端切换到 metaso（删除本段即回退 deepseek 官方搜索）
- id: web
  config:
    searchProvider: metaso
```

可选配置项：

| 字段 | 默认 | 说明 |
|---|---|---|
| `apiKey` | - | 秘塔 API key（与 apiKeyEnv 至少其一） |
| `apiKeyEnv` | `METASO_API_KEY` | 环境变量名（也支持 Web Models 页面管理的 credentials 域） |
| `baseURL` | `https://metaso.cn/api/v1` | API 端点 |
| `scope` | `webpage` | 默认搜索范围 |
| `includeSummary` | `true` | 是否请求综合摘要（映射为 content） |
| `includeRawContent` | `false` | 是否抓取来源原文 |
| `maxResults` | `10` | 单次返回条数上限（1-100） |

## 卸载

```bash
bash install.sh --uninstall   # 移除接线与源码副本
# 然后重启 dsh（watchdog 会自动拉起，或手动）
```

## 与 MCP 桥接方案对比

本插件为进程内 HTTP 调用（无子进程、key 走 credentials 域、工具名不膨胀）；另一种方案是通过 `@deepseek-ai/dsh-mcp-client` 桥接 `metaso-search-mcp`（工具名 `mcp__metaso__search` / `mcp__metaso__reader`，scope 参数完整）。两者可共存，按机器选择。
