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
- **QA card** (`ask_user_question`, Mbwy4a component): JS detects the card and turns its composer seat into a full-height floating panel — no `:has()` dependency (works in WeChat/X5-style engines). The card's own `max-height` is lifted and its body stays the single scroll container, so long option lists scroll with a finger on every device; the footer button row wraps when narrow, so the submit button is always visible
- **Composer action row = two lines** (2026-09-11, per the user's choice): line 1 holds the tools (`+` / attach / access mode); line 2 holds the model trigger (taking all remaining width) + context ring + send. Two lines are *required*, not cosmetic: the full model name (`commandcode/deepseek/deepseek-v4.1-flash` = 40 chars ≈ 225px) physically cannot fit on one line inside a 390px viewport — the row has 332px of content width and the tools need 120px, leaving the model trigger ~61px (10/40 chars, measured). Wrapping lets it take 218px at the same viewport (38/40 chars) and the **full name from 400px up**, at the cost of row height 52 → 90px. The access-mode button always shows its shield icon plus its text (`@container (min-width: 170px)`, judged on the row's real width); a clipped model name always uses a real ellipsis.
- **Composer row visual consistency** (2026-09-11, from the user's "the heights don't match, it looks off" report): upstream ships six different control heights (add 28 / PermissionSelect 28 / model 28 / ContextMeter 28 / primary 34) and our own earlier patches had left a 36/40/44 mix with three font sizes (model 11px / access 13px / context 10px). Everything is now **44px tall with a 12px font** (which also satisfies the iOS HIG minimum touch size — measured: `+`/attach/access were only 36px), the primary button's upstream `translateY(-2px)` is cancelled (a single-line-era optical compensation that pushed its centre 2px below its row), and the access-mode button gets the same round solid background as `+`/attach (upstream renders it as a background-less compact trigger, which looked like a missing piece between two round buttons). **Invariants**: within a row, every button is the same height, the same font size, and their vertical centres spread ≤1.5px. ⚠️ This surfaced a fourth word-root leak: the message flow contains **no** `[class*=tools]` at all (only `xzv4MW_actions` / `TS9iAW_actions`), so the old `[class*=scrollBody] [class*=tools] button{min-height:36px}` was really hitting the composer's `uV2eYG_tools` and crushing `+`/attach/access to 36px — the actual cause of "row 1 is 36px while row 2 is 40/44px". It is now scoped to `[class*=flowItem]`, so message-flow buttons stay 36px and composer controls 44px. Never fake a single line with "no-wrap + shrink": upstream group buttons carry a non-compressible `min-width: 44px`, so a narrow row cannot resolve by shrinking and simply **overlaps** (the original bug: at 390px the model trigger covered the context ring by 4.3px and the access-mode button covered it by 5.7px).
- **Regression probe**: `python3 tests/mobile-layout-probe.py` drives a real headless Chromium (upstream CSS + real DOM nesting + the actual plugin bundle) across viewports, asserting two families of invariants: for the QA card — "option list scrolls / last option reachable after a real touch swipe / submit always visible / the fixed top-right menu button does not overlap the card"; for the composer row — "no two controls overlap / nothing spills past the card's right edge / every control is hit-testable / the access-mode icon *and* its text are always visible / the model name keeps at least 120px so it never degrades back into a sliver / a clipped model name uses a real ellipsis / icon, text and chevron are vertically centred". Exit code 1 on regression.
- **⚠️ The most dangerous pitfall in this plugin: word-root selectors** (three separate silent breakages on 2026-09-11). Upstream's `_7KE1Ra_triggerLabel / triggerIcon / triggerEffort` all contain **"trigger"**, so a bare `[class*=trigger]` hits them too: with `display:flex` the `text-overflow:ellipsis` is ignored (flex containers ignore it) and the model name is **cut mid-character**; with `min-height:40px` the label is stretched to full row height and its text hugs the top, so the chevron *looks* like it dropped to another line. Always narrow to `button[class*=trigger]`, and keep ellipsis on `display:block`. Likewise `button[aria-label*=访问模式] span { display:none }` hides the **shield icon as well** (it is a span too), leaving a completely blank button — hide only `[class*=triggerLabel]` and keep the icon permanently visible. Two more rules it guards: never override the card body's `overflow` (that is exactly what broke scrolling before), and hide the floating menu button whenever the question card is open (it sits at `top:48px; right:12px`, right on top of the card title). Related: a `min-width` floor on the trailing group's content is harmful — `flex:1 1 0` + `min-width:0` + `justify-content:flex-end` spills children **leftward** over the tools group once the box is narrower than its content minimum (measured: 9px at 365px viewport with `min-width:96px`), so express "the model name should stay readable" some other way.

## Maintenance notes (important)

- dsh frontend class names are build artifacts (hash prefixes). After a dsh upgrade, if selectors break:
  1. Verify `body.dsh-mobile-ui` and `#dsh-mobile-menu-btn` exist in the console
  2. Breakage usually hits layout classes (`[class*=frame]` etc.) — adjust CSS/JS to the new prefix
  3. Re-run `bash install.sh` after fixing
- Layout detection uses structural heuristics ("3-column grid + 56px first column"), not hard-coded class names, and buttons prefer `aria-label` — this tolerates class-name drift
- All DOM work is try/catch wrapped; any failure degrades silently (CSS layer still applies)
- **Never move React-rendered DOM nodes with JS** (`insertBefore`/`appendChild` on `pXSMma_root` etc.): React's fiber tree still records the old parent, so a re-render throws `removeChild` NotFoundError and the whole conversation view unmounts (blank page). Express every layout need in CSS (flex / order / :has) — the hero title pinning and the QA card are pure CSS for this reason.

## Rollback

`bash install.sh --uninstall` + restart dsh removes everything (no residual styles/DOM).

## License

MIT. Chinese documentation: [README.zh.md](README.zh.md)

---

*Part of [dsh-plugins](https://github.com/TZHR-invest/dsh-plugins) — a small monorepo of DSH plugins: [dsh-lan-gateway](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-lan-access), [dsh-vision-tool](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-vision), [dsh-mobile-ui](https://github.com/TZHR-invest/dsh-plugins/tree/main/packages/dsh-mobile-ui).*
