#!/usr/bin/env python3
"""验证「用语义锚点 [class*=headerUtilities] [role=menu] 替代 hash」能否把 ⋯ 菜单拉回视口。

在浏览器里注入候选 CSS（不改插件文件），对比注入前后菜单 rect。
"""
import sys

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TOKEN = open(TOKF, encoding="utf-8").read().strip()

CANDIDATE = """
body.dsh-mobile-ui [class*=headerUtilities] [role=menu]{
  position:fixed !important; left:8px !important; right:8px !important; width:auto !important;
  min-width:0 !important; max-width:none !important; max-height:calc(100vh - 150px) !important;
  overflow:auto !important; top:122px !important;
  visibility:visible !important; pointer-events:auto !important;
}
"""

MEASURE = """
() => {
  const menus = [...document.querySelectorAll('[role=menu]')].filter((m) => {
    const r = m.getBoundingClientRect();
    return r.width > 40 && r.height > 20;
  });
  if (!menus.length) return { none: true };
  const m = menus[menus.length - 1];
  const r = m.getBoundingClientRect();
  const cs = getComputedStyle(m);
  // ⚠️ visibility 是继承属性：getComputedStyle(元素) 已含继承结果，
  //    只看自身即可。逐级判祖先会把「祖先 hidden 但自己 visible」误报成不可见
  //    （2026-09-28 实测踩过：候选 CSS 明明生效却被判失败）。
  const visSelf = cs.visibility;
  let op = 1, pe = "auto", hiddenAncestor = null, node = m.parentElement;
  while (node && node !== document.documentElement) {
    const s = getComputedStyle(node);
    op *= parseFloat(s.opacity || "1");          // opacity 是组不透明度，必须逐级相乘
    if (s.visibility === "hidden") hiddenAncestor = (node.className || node.tagName).toString().slice(0, 50);
    if (s.pointerEvents === "none") pe = "none"; // pointer-events 继承
    node = node.parentElement;
  }
  const cx = Math.min(Math.max(r.left + r.width/2, 1), window.innerWidth - 1);
  const cy = Math.min(Math.max(r.top + r.height/2, 1), window.innerHeight - 1);
  const hit = document.elementFromPoint(cx, cy);
  return {
    cls: (m.className || "").toString().slice(0, 70),
    rect: [r.left, r.top, r.width, r.height].map(Math.round),
    pos: cs.position, left: cs.left, right: cs.right,
    inViewport: r.left >= -1 && r.right <= window.innerWidth + 1 && r.top >= -1 && r.bottom <= window.innerHeight + 1,
    effOpacity: +op.toFixed(2), visibility: visSelf, hiddenAncestor, pointerEvents: pe,
    hitInside: !!(hit && m.contains(hit)),
    items: m.querySelectorAll('[role=menuitem], button, a').length,
  };
}
"""


def open_session(page, vw):
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
    return t


def tap_more(page):
    page.touchscreen.tap(*page.evaluate("""() => { const el = document.querySelector('#dsh-mobile-more-proxy');
        const r = el.getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; }"""))
    page.wait_for_timeout(1600)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices.get("Pixel 7", p.devices["Pixel 5"]))
    page = ctx.new_page()
    vw = page.viewport_size["width"]
    title = open_session(page, vw)
    print(f"base={BASE} 会话={title} 视口宽={vw}\n")

    tap_more(page)
    before = page.evaluate(MEASURE)
    print("【注入前】")
    for k in ("cls", "rect", "pos", "left", "right", "inViewport", "effOpacity", "visibility", "hiddenAt", "pointerEvents", "hitInside", "items"):
        print(f"  {k:12s} = {before.get(k)}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)

    page.add_style_tag(content=CANDIDATE)
    page.wait_for_timeout(400)
    tap_more(page)
    after = page.evaluate(MEASURE)
    print("\n【注入候选 CSS 后】")
    for k in ("cls", "rect", "pos", "left", "right", "inViewport", "effOpacity", "visibility", "hiddenAt", "pointerEvents", "hitInside", "items"):
        print(f"  {k:12s} = {after.get(k)}")

    ok = (after.get("inViewport") and after.get("effOpacity", 0) >= 0.9
          and after.get("visibility") == "visible" and after.get("pointerEvents") != "none"
          and after.get("hitInside") and after.get("items"))
    print("\n" + ("✅ 候选 CSS 有效：菜单回到视口内且可见可点" if ok else "❌ 候选 CSS 不足以修复"))
    page.screenshot(path="/tmp/menu-after.png")
    ctx.close(); b.close()
    sys.exit(0 if ok else 1)
