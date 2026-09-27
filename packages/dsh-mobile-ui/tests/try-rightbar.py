#!/usr/bin/env python3
"""实验：直接触发上游「打开右侧边栏」，看 0.1.7 自己怎么布局（不改插件代码）。

若上游自带 overlay/抽屉式呈现 ⇒ 插件只需提供入口按钮；
若上游把 grid 改回多列挤压正文 ⇒ 插件需补 overlay CSS。
"""
import sys

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TOKEN = open(TOKF, encoding="utf-8").read().strip()

STATE = """
() => {
  const rect = (el) => { const r = el.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };
  const frame = [...document.querySelectorAll("div")].find((e) => getComputedStyle(e).display === "grid" && e.children.length >= 3) || null;
  const rb = document.querySelector("[class*=rightbarCol]");
  const center = document.querySelector("[class*=centerCol]");
  const handle = document.querySelector("[class*=handle]");
  const btns = [...document.querySelectorAll('button[aria-label]')]
    .filter((b) => /右侧边栏|侧边栏/.test(b.getAttribute("aria-label") || ""))
    .map((b) => ({ label: b.getAttribute("aria-label"), cls: (b.className || "").toString().slice(0, 40), rect: rect(b), vis: getComputedStyle(b).visibility }));
  const bodyCls = document.body.className;
  return {
    vw: window.innerWidth,
    gridInline: frame ? frame.style.gridTemplateColumns : null,
    gridComputed: frame ? getComputedStyle(frame).gridTemplateColumns : null,
    frameChildren: frame ? [...frame.children].map((c) => (c.className || "").toString().replace(/^pI_x6G_/, "")) : [],
    rightbar: rb ? { rect: rect(rb), display: getComputedStyle(rb).display, pos: getComputedStyle(rb).position, vis: getComputedStyle(rb).visibility, z: getComputedStyle(rb).zIndex, text: (rb.innerText || "").trim().slice(0, 60) } : null,
    center: center ? { rect: rect(center) } : null,
    handle: handle ? { rect: rect(handle), display: getComputedStyle(handle).display } : null,
    buttons: btns,
    bodyCls: bodyCls.slice(0, 120),
  };
}
"""


def show(tag, d):
    print(f"\n── {tag} ──")
    print(f"  视口={d['vw']}  gridInline={d['gridInline']}  gridComputed={d['gridComputed']}")
    print(f"  frame 子列={d['frameChildren']}")
    if d["rightbar"]:
        r = d["rightbar"]
        print(f"  rightbar: rect={r['rect']} display={r['display']} pos={r['pos']} vis={r['vis']} z={r['z']}")
        print(f"            text={r['text']!r}")
    if d["center"]:
        print(f"  centerCol: rect={d['center']['rect']}")
    if d["handle"]:
        print(f"  handle: rect={d['handle']['rect']} display={d['handle']['display']}")
    for b in d["buttons"]:
        print(f"  按钮 {b['label']!r} vis={b['vis']} rect={b['rect']} cls={b['cls']}")
    print(f"  body.class = {d['bodyCls']!r}")


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
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-tab-tools')"):
            break
    print(f"base={BASE} 会话={t}")
    show("初始（插件已把 grid 改成单列、右侧栏 height:0）", page.evaluate(STATE))

    # 触发上游「打开右侧边栏」
    ok = page.evaluate("""() => {
      const b = document.querySelector('button[aria-label="打开右侧边栏"]');
      if (!b) return false;
      b.click();
      return true;
    }""")
    print(f"\n触发上游「打开右侧边栏」: {'成功' if ok else '按钮不存在'}")
    page.wait_for_timeout(2000)
    show("点击后（内容已渲染，但 rightbar 仍 height:0 —— 被插件的单列 grid 压掉）", page.evaluate(STATE))

    # 候选修法：把 rightbarCol 变成覆盖整屏的浮层（不挤压正文）
    CAND = """
    body.dsh-mobile-ui [class*=rightbarCol]{
      position:fixed !important; inset:0 !important; width:auto !important; height:auto !important;
      z-index:2147482950 !important; display:block !important;
      background:var(--dsw-alias-bg-layer-1,#16171b) !important;
    }
    """
    page.add_style_tag(content=CAND)
    page.wait_for_timeout(1000)
    page.evaluate("() => window.dispatchEvent(new Event('resize'))")
    page.wait_for_timeout(1500)
    show("注入 overlay CSS 后", page.evaluate(STATE))
    inner = page.evaluate("""() => {
      const rb = document.querySelector('[class*=rightbarCol]');
      if (!rb) return null;
      const r = rb.getBoundingClientRect();
      const cx = Math.min(Math.max(r.left + r.width/2, 1), window.innerWidth - 1);
      const cy = Math.min(Math.max(r.top + r.height/2, 1), window.innerHeight - 1);
      const hit = document.elementFromPoint(cx, cy);
      const clickables = rb.querySelectorAll('button, [role=button], [role=treeitem]').length;
      return { rect: [r.left, r.top, r.width, r.height].map(Math.round),
               inViewport: r.left >= -1 && r.top >= -1 && r.right <= window.innerWidth + 1 && r.bottom <= window.innerHeight + 1,
               text: (rb.innerText || "").trim().replace(/\\n+/g, " | ").slice(0, 130),
               hitInside: !!(hit && rb.contains(hit)),
               hitDesc: hit ? (hit.className || hit.tagName).toString().slice(0, 46) : null,
               clickables };
    }""")
    print(f"\n  覆盖层面板: {inner}")
    page.screenshot(path="/tmp/rightbar-after.png")
    print("\n截图: /tmp/rightbar-after.png")
    ctx.close(); b.close()
