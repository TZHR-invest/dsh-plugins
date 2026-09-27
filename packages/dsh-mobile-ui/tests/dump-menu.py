#!/usr/bin/env python3
"""点开 ⋯ 后 dump 菜单的真实结构/类名/定位，用于对比插件选择器为何失配。"""
import sys

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TOKEN = open(TOKF, encoding="utf-8").read().strip()

DUMP = """
() => {
  const menus = [...document.querySelectorAll('[role=menu], [role=listbox]')].filter((m) => {
    const r = m.getBoundingClientRect();
    return r.width > 40 && r.height > 20;
  });
  if (!menus.length) return { none: true };
  const m = menus[menus.length - 1];
  const r = m.getBoundingClientRect();
  const cs = getComputedStyle(m);
  const chain = [];
  let node = m.parentElement;
  while (node && node !== document.body && chain.length < 6) {
    const c = getComputedStyle(node);
    const rr = node.getBoundingClientRect();
    chain.push({
      tag: node.tagName, cls: (node.className || "").toString().slice(0, 80),
      pos: c.position, left: c.left, right: c.right, width: c.width,
      transform: c.transform === "none" ? null : c.transform,
      rect: [rr.left, rr.top, rr.width, rr.height].map(Math.round),
    });
    node = node.parentElement;
  }
  return {
    cls: (m.className || "").toString(),
    role: m.getAttribute("role"),
    rect: [r.left, r.top, r.width, r.height].map(Math.round),
    computed: { position: cs.position, left: cs.left, right: cs.right, top: cs.top,
                width: cs.width, minWidth: cs.minWidth, maxWidth: cs.maxWidth,
                transform: cs.transform, inset: cs.inset },
    inlineStyle: m.getAttribute("style"),
    firstItemCls: m.querySelector("[role=menuitem], button, a")?.className?.toString()?.slice(0, 60) || null,
    htmlHead: m.outerHTML.slice(0, 260),
    chain,
  };
}
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices.get("Pixel 7", p.devices["Pixel 5"]))
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    page.touchscreen.tap(*page.evaluate("() => { const r = document.querySelector('#dsh-mobile-menu-btn').getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]; }"))
    page.wait_for_timeout(1500)
    rows = page.query_selector_all("[role=treeitem][class*=sessionRow]") or page.query_selector_all("[role=treeitem]")
    picked = t = None
    for row in rows[:12]:
        s = (row.inner_text() or "").strip().replace("\n", " ")
        if TITLE and TITLE in s:
            picked, t = row, s[:26]; break
        if not TITLE and s and "新会话" not in s:
            picked, t = row, s[:26]; break
    picked.click()
    page.wait_for_timeout(1500)
    vw = page.viewport_size["width"]
    for _ in range(6):
        st = page.evaluate("() => ({s: !!document.querySelector('.dsh-mobile-scrim'), d: !!document.querySelector('.dsh-mobile-drawer')})")
        if not st["s"] and not st["d"]:
            break
        page.touchscreen.tap(vw - 30, 500)
        page.wait_for_timeout(800)
    for _ in range(20):
        page.wait_for_timeout(800)
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-more-proxy')"):
            break
    print(f"base={BASE}  会话={t}  视口宽={vw}\n")

    c = page.evaluate("""() => { const el = document.querySelector('#dsh-mobile-more-proxy');
        const r = el.getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]; }""")
    page.touchscreen.tap(*c)
    page.wait_for_timeout(1600)
    d = page.evaluate(DUMP)
    if d.get("none"):
        print("没有菜单"); sys.exit(2)
    print(f"菜单 cls = {d['cls']}")
    print(f"菜单 role= {d['role']}  rect={d['rect']}")
    print(f"computed = {d['computed']}")
    print(f"inline   = {d['inlineStyle']}")
    print(f"首条目 cls= {d['firstItemCls']}")
    print(f"htmlHead = {d['htmlHead']}")
    print("\n祖先链（自内向外）:")
    for x in d["chain"]:
        print(f"  {x['tag']:6s} cls={x['cls'][:56]:56s} pos={x['pos']:9s} L={x['left']:>8s} R={x['right']:>8s} w={x['width']:>8s} tf={x['transform']} rect={x['rect']}")
    ctx.close(); b.close()
