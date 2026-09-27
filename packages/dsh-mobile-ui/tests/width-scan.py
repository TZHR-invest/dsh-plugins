#!/usr/bin/env python3
"""多视口宽度扫描：三个 mobile-ui 工具按钮在各宽度下是否完整、是否被裁切/遮挡。

纪律来源 docs/dsh-mobile-ui.md §2.7：宽度相关的点击/显示故障**必须横扫视口**，
单宽度探针天生漏检。

用法: python3 width-scan.py <base-url> <token-file> [--title 片段]
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1]
TOKF = sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TOKEN = open(TOKF, encoding="utf-8").read().strip()

WIDTHS = [320, 360, 375, 390, 412, 430]
BTNS = [
    ("#dsh-mobile-more-proxy", "⋯"),
    ("#dsh-mobile-fold-composer", "▤"),
    ("#dsh-mobile-rightbar-toggle", "▥右侧栏"),
    ("#dsh-mobile-tab-menu", "☰"),
]

PROBE = """
(sels) => {
  const out = { vw: window.innerWidth, items: [], group: null };
  const g = document.querySelector("#dsh-mobile-tab-tools");
  if (g) {
    const r = g.getBoundingClientRect();
    const cs = getComputedStyle(g);
    out.group = { rect: [r.left, r.top, r.width, r.height].map(Math.round),
                  pos: cs.position, left: cs.left, right: cs.right, cls: (g.className||"").toString().slice(0,40) };
  }
  const clippedBy = (el) => {
    let node = el.parentElement;
    while (node && node !== document.documentElement) {
      const cs = getComputedStyle(node);
      if (cs.overflow !== "visible" || cs.overflowX !== "visible" || cs.overflowY !== "visible") {
        const r = node.getBoundingClientRect(), er = el.getBoundingClientRect();
        if (er.left < r.left - 0.5 || er.right > r.right + 0.5 || er.top < r.top - 0.5 || er.bottom > r.bottom + 0.5) {
          return { cls: (node.className || "").toString().slice(0, 48),
                   rect: [r.left, r.top, r.width, r.height].map(Math.round),
                   ov: cs.overflow };
        }
      }
      node = node.parentElement;
    }
    return null;
  };
  for (const [sel, name] of sels) {
    const el = document.querySelector(sel);
    if (!el) { out.items.push({ name, exists: false }); continue; }
    const r = el.getBoundingClientRect();
    let op = 1, vis = "visible", pe = "auto", node = el;
    while (node && node !== document.documentElement) {
      const cs = getComputedStyle(node);
      op *= parseFloat(cs.opacity || "1");
      if (cs.visibility === "hidden") vis = "hidden";
      if (cs.pointerEvents === "none") pe = "none";
      node = node.parentElement;
    }
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
    const hit = document.elementFromPoint(cx, cy);
    out.items.push({
      name, exists: true,
      rect: [r.left, r.top, r.width, r.height].map(Math.round),
      inViewport: r.left >= -0.5 && r.right <= window.innerWidth + 0.5 && r.top >= -0.5,
      overflowRight: Math.round(r.right - window.innerWidth),
      op: +op.toFixed(2), vis, pe,
      hitSelf: !!(hit && (hit === el || el.contains(hit))),
      hitDesc: hit ? (hit.id || hit.className || hit.tagName).toString().slice(0, 40) : null,
      clippedBy: clippedBy(el),
    });
  }
  return out;
}
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 900}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    page.click("#dsh-mobile-menu-btn", timeout=8000)
    page.wait_for_timeout(1500)
    rows = page.query_selector_all("[role=treeitem][class*=sessionRow]") or page.query_selector_all("[role=treeitem]")
    picked = title = None
    for row in rows[:12]:
        t = (row.inner_text() or "").strip().replace("\n", " ")
        if TITLE and TITLE in t:
            picked, title = row, t[:30]
            break
        if not TITLE and t and "新会话" not in t:
            picked, title = row, t[:30]
            break
    if picked is None:
        print("找不到目标会话"); sys.exit(2)
    picked.click()
    page.wait_for_timeout(1500)

    # ⚠️ 点会话项不会自动关抽屉（closeDrawer 只绑在 scrim 上）；关不掉的话
    # scrim（z-index 2147482995）会盖住全屏、把三个按钮的点击全吃掉 ⇒ 全是假阴性。
    # 正确姿势（抄 live-probe.py:122）：touchscreen.tap 点右侧空白，并**验证**已关。
    DRAWER_STATE = """
    () => {
      const vis = (el) => {
        if (!el) return false;
        const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        return cs.visibility !== "hidden" && parseFloat(cs.opacity || "1") > 0.5 && r.width > 1 && r.height > 1;
      };
      const scrim = document.querySelector(".dsh-mobile-scrim");
      const drawer = document.querySelector(".dsh-mobile-drawer");
      return { scrim: vis(scrim), drawer: vis(drawer), closed: !vis(scrim) && !vis(drawer) };
    }
    """
    closed = False
    for i in range(6):
        st = page.evaluate(DRAWER_STATE)
        if st["closed"]:
            closed = True
            break
        page.touchscreen.tap(390 - 30, 500)
        page.wait_for_timeout(900)
    print(f"抽屉已关闭: {closed}" + ("" if closed else "  ⚠️ 关不掉，下面结果不可信"))
    if not closed:
        sys.exit(3)

    for _ in range(25):
        page.wait_for_timeout(1000)
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-tab-tools')"):
            break
    print(f"base={BASE}  会话={title}\n")

    problems = []
    print(f"{'宽度':>5} | " + " | ".join(f"{n:^26}" for _, n in BTNS))
    for w in WIDTHS:
        page.set_viewport_size({"width": w, "height": 880})
        page.wait_for_timeout(2200)      # 等插件 resize sync
        d = page.evaluate(PROBE, BTNS)
        cells = []
        for it in d["items"]:
            if not it.get("exists"):
                cells.append("不存在")
                problems.append(f"{w}px: {it['name']} 不存在")
                continue
            flags = []
            if not it["inViewport"]:
                flags.append(f"出视口+{it['overflowRight']}px")
            if it["clippedBy"]:
                flags.append(f"被 {it['clippedBy']['cls'][:22]} 裁(ov={it['clippedBy']['ov']})")
            if it["op"] < 0.9:
                flags.append(f"op={it['op']}")
            if it["vis"] != "visible":
                flags.append("hidden")
            if it["pe"] == "none":
                flags.append("pe:none")
            if not it["hitSelf"]:
                flags.append(f"中心被{it['hitDesc']}吃")
            r = it["rect"]
            cells.append(f"{r[0]},{r[1]} {r[2]}x{r[3]}" + (" ⚠ " + ";".join(flags) if flags else " ✓"))
            if flags:
                problems.append(f"{w}px: {it['name']} → " + "; ".join(flags))
        print(f"{w:>5} | " + " | ".join(f"{c[:26]:^26}" for c in cells))
        if d["group"]:
            g = d["group"]
            print(f"        └ 工具组 pos={g['pos']} left={g['left']} right={g['right']} rect={g['rect']} cls={g['cls']}")

    print()
    if problems:
        print(f"❌ {len(problems)} 项异常：")
        for x in problems:
            print("   - " + x)
        sys.exit(1)
    print("✅ 全部宽度下所有工具按钮均完整、可见、可点")
    ctx.close(); b.close()
