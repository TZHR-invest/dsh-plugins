# dsh-lan-gateway

LAN / remote access gateway for the **DeepSeek Harness** Web UI — a complete, token-gated solution:

- **0.0.0.0 binding** — reach the Web GUI from any device on your LAN (or via Tailscale, etc.)
- **`crypto.randomUUID` polyfill** — the browser only exposes this API in secure contexts (HTTPS / localhost); plain-HTTP LAN access would otherwise crash the client-side RPC layer. The polyfill is mounted in the browser bundle (and as a host-side tap as fallback).
- **Token gate** — non-loopback requests must present an access token: a 401 login page for browsers, WebSocket handshakes are destroyed without a valid token, loopback (localhost / 127.*) is exempt.
- **Privileged-fence exemption** — one-line patch so the host's privileged-method fence keeps working over LAN access.
- **Settings persistence** — forces the settings scope to host mode so General settings (language, appearance, …) are read/written even when reached via a LAN IP.
- **Idempotent installer + upgrade recovery** — `install.sh` (apply / --check / --restart / --uninstall) and `reapply-lan-patches.sh` to restore the node_modules patches after every dsh upgrade.

> ⚠️ **Trusted networks only.** Binding to 0.0.0.0 lets any device that can reach the port drive the agent (execute commands). The token gate keeps unauthorized devices out, but tokens travel in plain HTTP — add an HTTPS reverse proxy if you need protection from sniffing. Do **not** expose this to the public internet.

---

## Install (tarball, 3 steps)

On the target machine (must have run `@deepseek-ai/dsh web` at least once):

```bash
scp dsh-lan-gateway-install.tar.gz user@target:~/
cd ~ && tar xzf dsh-lan-gateway-install.tar.gz
cd dsh-lan-gateway-install && bash install.sh --restart
```

During install a **random access token is generated once and shown once** (saved to `~/.dsh/lan-access-token`, chmod 600). After restart, visiting `http://<target-ip>:3080` from another device shows the token login page; localhost stays token-free.

## Install (npm)

```bash
dsh plugin --profile web add dsh-lan-gateway
# then apply the privileged-fence / settings / webserver patches via the bundled installer:
bash ~/.dsh/plugins/dsh-lan-gateway/install.sh --restart
```

## Access token

- Token file: `~/.dsh/lan-access-token` (single line, chmod 600). **Changes take effect immediately** — the file is read on every request, no restart needed.
- Loopback (localhost / 127.*) is always exempt.
- LAN access, any of:
  - Browser: first visit shows the login page — paste the token (sets a 30-day HttpOnly cookie)
  - `curl -H "X-DSH-Token: <token>" http://<ip>:3080/`
  - `http://<ip>:3080/?token=<token>` (auto-sets the cookie)
  - WebSocket connections inherit the cookie automatically
- Login form posts to `POST /__lan_auth` (valid token → 302 + Set-Cookie).
- Delete the token file to disable the gate (fail-safe); regenerate by deleting the file and re-running `bash install.sh`.

## Commands

| Command | Effect |
|---|---|
| `bash install.sh` | Apply/complete all six layers (idempotent) |
| `bash install.sh --check` | Status check only, changes nothing |
| `bash install.sh --restart` | Install, restart dsh web, curl-verify |
| `bash install.sh --uninstall` | Remove wiring + revert patches |

## What it installs

| # | Layer | Location |
|---|---|---|
| 1 | Web server binds 0.0.0.0 | `~/.dsh/cordis.patch.yml` |
| 2 | Plugin source + profile install | `~/.dsh/plugins/dsh-lan-gateway/`, `~/.dsh/profiles/node_modules/dsh-lan-gateway/` |
| 3 | Profile bundle wiring | `~/.dsh/profiles/web/cordis.patch.yml` insert line |
| 4 | Access token (loopback exempt) | `~/.dsh/lan-access-token` (random, 600) |
| 5 | Privileged-fence exemption | one-line patch in `node_modules/@deepseek-ai/dsh-client-connection/lib/index.js` |
| 6 | Settings-persistence exemption | one-line patch in `node_modules/@deepseek-ai/dsh-client-ui-settings/lib/client.js` (settingsScope forced to host) |
| 7 | Token gate (401 login page + WS interception) | entry patch in `node_modules/@deepseek-ai/dsh-host-webserver/lib/index.js` (via `token-gate.js` + `patch-webserver.mjs`, `--revert` to roll back) |

`reapply-lan-patches.sh` is copied to `~/.dsh/` — after a dsh upgrade or reinstall (layers 5–7 get overwritten), run:

```bash
bash ~/.dsh/reapply-lan-patches.sh --restart
```

## Verify

```bash
curl http://127.0.0.1:3080/                          # 200 (loopback exempt)
curl http://<ip>:3080/                               # 401 login page without token
curl -H "X-DSH-Token: <token>" http://<ip>:3080/     # 200
```

In the browser console: `crypto.randomUUID()` returns a valid v4 UUID.

## Troubleshooting

- **"web profile not initialized"**: run `dsh web` once, then re-run `bash install.sh`.
- **Privileged-fence sed failure** ("code structure changed"): dsh version too new — adapt the interception logic near `PRIVILEGED_METHODS` in `dsh-client-connection/lib/index.js`.
- **Token-gate patch failure** ("anchor not found"): `dsh-host-webserver` internals changed — adapt the anchors in `patch-webserver.mjs`.
- **Forgot the token**: `cat ~/.dsh/lan-access-token`, or delete the file and re-run `bash install.sh`.
- **Disable the token gate**: `rm ~/.dsh/lan-access-token`; remove the patch fully with `node ~/.dsh/plugins/dsh-lan-gateway/patch-webserver.mjs <webserver lib> --revert`.
- **LAN still 403 after install**: check `~/.dsh/cordis.patch.yml` webserver entry took effect (`ss -ltnp | grep 3080` should show 0.0.0.0:3080, not 127.0.0.1:3080).

## Compatibility

Patches target the current `@deepseek-ai/dsh` rc line (anchor-based, verified against `dsh 0.1.0-rc.x`). Upgrades that change `dsh-client-connection` / `dsh-client-ui-settings` / `dsh-host-webserver` internals may require anchor updates — the installer detects and reports this instead of silently corrupting files.

## Security model

- No built-in keys. The token is generated at install time and stored in your home directory (600).
- Loopback exemption keeps your local session frictionless.
- Constant-time token comparison (SHA-256 + `timingSafeEqual`), HttpOnly + SameSite=Strict cookie, 30-day expiry.
- The token gate is **authorization, not encryption** — plain-HTTP LAN traffic can be sniffed. Use an HTTPS reverse proxy (Caddy/nginx) in front for untrusted networks.

## License

MIT. Chinese documentation: [README.zh.md](README.zh.md)

---

*Part of [dsh-plugins](https://github.com/TZHR-invest/dsh-plugins) — a small monorepo of DSH plugins: [dsh-lan-gateway](packages/dsh-lan-access), [dsh-vision-tool](packages/dsh-vision), [dsh-mobile-ui](packages/dsh-mobile-ui).*
