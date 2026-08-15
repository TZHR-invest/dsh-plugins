# dsh-vision-tool

A **`vision` tool** for DeepSeek Harness agents: sends a local image to the OpenAI-compatible vision endpoint **you configure** and returns a text description — for when the current session model can't ingest images directly.

The plugin ships **no built-in defaults**: provider (baseURL), credentials, and models are all configured at install time. If configuration is incomplete the plugin loads normally but does not register the tool (log line shows what's missing) — it can never crash the host.

## Features

- Agent-callable tool: `vision image_path=/tmp/shot.png`
- Any OpenAI-compatible `/chat/completions` endpoint (vendor-agnostic)
- Credential resolution chain: inline `apiKey` → `apiKeyEnv` (environment variable) → `~/.dsh/.credentials.yaml` same-name key
- Optional **cross-check**: query several models and merge answers (`cross_check=true`) to guard against hallucinated descriptions
- `maxTokens` / `maxImageBytes` limits (optional)
- Requests go out via a `curl` subprocess — inherits host proxy env vars and avoids Cloudflare 403/1010 on default urllib/undici user agents

## Install

### Tarball

```bash
tar xzf dsh-vision-tool-install.tar.gz && cd dsh-vision-tool-install

# interactive: just run it and answer the prompts
bash install.sh --restart

# or parameterized (scriptable / repeatable deploys)
bash install.sh --restart \
  --vision-base-url https://example.com/v1 \
  --vision-api-key-env MY_VISION_KEY \
  --vision-model gpt-4o \
  --vision-models gpt-4o,qwen-vl-max,kimi-latest \
  --vision-max-tokens 2000
```

### npm

```bash
dsh plugin --profile web add dsh-vision-tool
# then configure: edit the dsh-vision-tool config section in ~/.dsh/profiles/web/cordis.patch.yml
```

## Install parameters (`--vision-*`)

| Parameter | Required | Meaning |
|---|---|---|
| `--vision-base-url` | ✅ | OpenAI-compatible chat/completions endpoint |
| `--vision-model` | ✅ | Default vision model |
| `--vision-api-key` | one of | API key inline |
| `--vision-api-key-env` | one of | Environment variable name (also tried as a key in `~/.dsh/.credentials.yaml`) |
| `--vision-models` | optional | Cross-check model list (comma-separated; needed for `cross_check=true`) |
| `--vision-max-tokens` | optional | Omitted from the request if not set |

> No parameters + interactive terminal → guided prompts. No parameters + non-interactive → empty config written (tool not registered); re-run with parameters, or edit the config section in `~/.dsh/profiles/web/cordis.patch.yml`.

## Usage (inside the agent)

```
vision image_path=/tmp/shot.png
vision image_path=/tmp/shot.png question="What text is in this image?"
vision image_path=/tmp/shot.png model=gpt-4o
vision image_path=/tmp/shot.png cross_check=true   # requires --vision-models configured at install
```

## Security

- No built-in keys — credentials come only from your install parameters / environment / credential file
- `~/.dsh/.credentials.yaml` should be chmod 600

## Troubleshooting

- **Tool doesn't appear**: log shows `[dsh-vision-tool] missing ...` — re-run install.sh with `--vision-*` parameters and restart
- **Credential resolution fails**: at least one of `apiKey` / `apiKeyEnv` (incl. credential-file same-name key)
- **Endpoint incompatible**: baseURL must be OpenAI-compatible (`/chat/completions`, `Authorization: Bearer`)
- **Empty output from reasoning models**: configure `--vision-max-tokens 2000` or higher

## License

MIT. Chinese documentation: [README.zh.md](README.zh.md)

---

*Part of [dsh-plugins](https://github.com/TZHR-invest/dsh-plugins) — a small monorepo of DSH plugins: [dsh-lan-gateway](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-lan-access), [dsh-vision-tool](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-vision), [dsh-mobile-ui](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-mobile-ui).*
