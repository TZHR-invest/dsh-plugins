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
```

Optional: `apiKeyEnv` (default `METASO_API_KEY`, also resolved via the credentials domain), `baseURL` (default `https://metaso.cn/api/v1`), `scope` (default `webpage`), `includeSummary` (default true), `includeRawContent` (default false), `maxResults` (default 10, 1-100).
