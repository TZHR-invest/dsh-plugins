# dsh-plugins

A small monorepo of plugins for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`) — self-hosted, battle-tested against real incidents (crash-prevention discipline, idempotent installers, upgrade recovery).

## Plugins

| Package | npm | What it does |
|---|---|---|
| [dsh-lan-gateway](packages/dsh-lan-access) | `dsh-lan-gateway` | **LAN / remote access gateway** for the Web UI: 0.0.0.0 binding, `crypto.randomUUID` polyfill, **token gate** (401 login page + WebSocket interception, loopback exempt), privileged-fence + settings-persistence exemptions, idempotent installer + `reapply-lan-patches.sh` recovery. Trusted networks only. |
| [dsh-vision-tool](packages/dsh-vision) | `dsh-vision-tool` | Registers a `vision` tool for agents: describe local images via **any OpenAI-compatible vision endpoint you configure** — no built-in keys, optional multi-model `cross_check` to guard against hallucinations. |
| [dsh-mobile-ui](packages/dsh-mobile-ui) | `dsh-mobile-ui` | Mobile UI for the Web GUI (≤768px): full-width responsive layout, overlay session drawer, 44px touch targets, safe-area support, reading enhancements — zero desktop impact. |

All three follow the official bundle contract (`dsh.bundle.patch`), pass the repo's contract preflight (classic-script bundles, no top-level import/export, `exports["./client"]` present), and ship idempotent installers with headless smoke tests and uninstall rollback.

## Install

```bash
# per-plugin tarball (see each package README) or via npm:
dsh plugin --profile web add dsh-lan-gateway
dsh plugin --profile web add dsh-vision-tool
dsh plugin --profile web add dsh-mobile-ui
```

> ⚠️ **Security**: dsh-lan-gateway binds the Web GUI to 0.0.0.0 — any device that can reach the port can drive the agent. Trusted networks only; the token gate is authorization, not encryption.

## Infrastructure in this repo

- `scripts/preflight.mjs` — contract preflight for plugin packages (the crash-prevention checklist: platform, exports, classic-script bundle, id consistency). Runs automatically in `build.sh`.
- `scripts/new-plugin.sh` + `templates/` — scaffold new plugins from a template with an auto-generated idempotent installer (preflight + headless smoke + idempotent wiring + uninstall rollback).
- `docs/development.md` — plugin development guide (host/client mechanism, package spec, wiring, debugging, §8 crash-prevention checklist).
- `docs/publishing.md` — tarball distribution guide.

## External plugins (registered only, not copied)

- **memory-recall-dsh** — long-term memory plugin (6 tools + auto recall injection + auto capture). Code lives in the `memory_recall` repo (`apps/api/src/plugins/dsh/`); this repo only links it to avoid source drift. Requires a self-deployed backend.
- **dshmarket** — visual plugin market inside the Web GUI (browse/search/install/update/uninstall 300+ community plugins, themes). Upstream: [dsh-market/dsh-market](https://github.com/dsh-market/dsh-market) (npm `dshmarket`, MIT, zero runtime deps); registered here only, not copied. Install: `dsh plugin --profile web add dshmarket`, then restart `dsh web`; entry at Settings → Plugin Market. Note: its in-UI one-click restart (loopback + same-origin guarded) is enabled by default — on hosts without a supervisor, prefer a manual terminal restart or set `allowRestart: false`.

## License

MIT. Chinese documentation: [README.zh.md](README.zh.md)
