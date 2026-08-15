# dsh-mobile-ui

Mobile UI enhancements for the DeepSeek Harness Web GUI — turns dsh into a real mobile experience on phones (≤768px viewport):

- **Responsive layout** — hides the left icon rail, content goes full-width; session list opens as an overlay drawer
- **Touch-optimized** — 44px touch targets (iOS HIG), no double-tap zoom delay, no tap highlight, 16px inputs (prevents iOS focus auto-zoom)
- **Reading enhancements** — message spacing, bubble width, and helper text (tool rows / context-injection / status stats) scaled for small screens
- **Right-top menu** — the drawer (new session / sessions / settings) opens from a floating round button
- **Safe-area aware** — `env(safe-area-inset-*)` support for notched displays
- **Zero desktop impact** — every enhancement lives inside a `max-width: 768px` media query

## Install

```bash
# from the plugin source directory
bash install.sh            # install (idempotent)
bash install.sh --restart  # install + restart dsh web (headless smoke test; aborts on plugin problems)
bash install.sh --uninstall  # remove completely
```

Or via npm:

```bash
dsh plugin --profile web add dsh-mobile-ui
```

What the installer does:
1. Source kept at `~/.dsh/plugins/dsh-mobile-ui/`
2. Runtime copy at `~/.dsh/profiles/node_modules/dsh-mobile-ui/`
3. Web profile bundle wiring (`cordis.patch.yml` insert)

## Development

```bash
bash scripts/build.sh     # syntax + contract preflight (incl. classic-script check)
bash scripts/package.sh   # build dist/dsh-mobile-ui-install.tar.gz
```

Fast local iteration: copy to `~/.dsh/profiles/node_modules/dsh-mobile-ui/` and refresh the page (client plugins have an HMR channel — client.js edits apply on refresh).

## How it works

- **CSS layer**: injects `style[data-plugin-css=dsh-mobile-ui]`, all rules wrapped in `@media (max-width:768px)` — desktop loads none of it
- **JS layer**: `matchMedia`-driven; on narrow screens the main grid goes single-column, the sidebar is hidden and becomes a fixed overlay drawer with scrim

## Maintenance notes (important)

- dsh frontend class names are build artifacts (hash prefixes). After a dsh upgrade, if selectors break:
  1. Verify `body.dsh-mobile-ui` and `#dsh-mobile-menu-btn` exist in the console
  2. Breakage usually hits layout classes (`[class*=frame]` etc.) — adjust CSS/JS to the new prefix
  3. Re-run `bash install.sh` after fixing
- Layout detection uses structural heuristics ("3-column grid + 56px first column"), not hard-coded class names, and buttons prefer `aria-label` — this tolerates class-name drift
- All DOM work is try/catch wrapped; any failure degrades silently (CSS layer still applies)

## Rollback

`bash install.sh --uninstall` + restart dsh removes everything (no residual styles/DOM).

## License

MIT. Chinese documentation: [README.zh.md](README.zh.md)

---

*Part of [dsh-plugins](https://github.com/TZHR-invest/dsh-plugins) — a small monorepo of DSH plugins: [dsh-lan-gateway](packages/dsh-lan-access), [dsh-vision-tool](packages/dsh-vision), [dsh-mobile-ui](packages/dsh-mobile-ui).*
