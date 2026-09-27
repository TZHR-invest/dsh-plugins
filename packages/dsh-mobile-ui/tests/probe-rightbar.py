#!/usr/bin/env python3
"""验证右侧边栏（工作区文件）入口按钮：点开 → 面板全屏可见可点 → 关闭。

用法: python3 probe-rightbar.py <base-url> <token-file> [--title 片段]
"""
import sys

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TAG = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "rb"
TOKEN = open(TOKF, encoding="utf-8").read().strip()

STATE = """
() => {
  const rb = document.querySelector("[class*=rightbarCol]");
  const r = rb ? rb.getBoundingClientRect() : null;
  let op = 1, pe = "auto", node = rb ? rb.parentElement : null;
  while (node && node !== document.documentElement) {
    const s = getComputedStyle(node);
    op *= parseFloat(s.opacity || "1");
    if (s.pointerEvents === "none") pe = "none";
    node = node.parentElement;
  }
  const hit = r ? document.elementFromPoint(Math.min(Math.max(r.left + r.width/2, 1), innerWidth-1),
                                            Math.min(Math.max(r.top + r.height/2, 1), innerHeight-1)) : null;
  return {
    cls: document.body.className.includes("dsh-mobile-rightbar"),
    rect: r ? [r.left, r.top, r.width, r.height].map(Math.round) : null,
    pos: rb ? getComputedStyle(rb).position : null,
    vis: rb ? getComputedStyle(rb).visibility : null,
    effOpacity: +op.toFixed(2), pointerEvents: pe,
    inViewport: !!(r && r.left >= -1 && r.top >= -1 && r.right <= innerWidth+1 && r.bottom <= innerHeight+1),
    /* ⚠️ 收起态的 rightbarCol 是 [0, innerHeight, w, 0]：top/bottom 都等于视口高，
       单看 inViewport 会误判成「可见」（2026-09-28 踩过）⇒ 必须叠加尺寸判据。 */
    visible: !!(r && r.width > 100 && r.height > 100 && r.top < innerHeight),
    text: rb ? (rb.innerText || "").trim().replace(/\\n+/g, " | ").slice(0, 120) : null,
    hitInside: !!(hit && rb && rb.contains(hit)),
    clickables: rb ? rb.querySelectorAll("button, [role=button], [role=treeitem]").length : 0,
    btnOn: !!document.querySelector("#dsh-mobile-rightbar-toggle.dsh-mobile-on"),
  };
}
"""


def tap(page, sel):
    box = page.evaluate("""(sel) => { const el = document.querySelector(sel); if (!el) return null;
        const r = el.getBoundingClientRect();
        return (r.width > 0 && r.height > 0) ? [r.left + r.width/2, r.top + r.height/2] : null; }""", sel)
    if box is None:
        return False
    page.touchscreen.tap(box[0], box[1])
    return True


fails = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices.get("Pixel 7", p.devices["Pixel 5"]))
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    tap(page, "#dsh-mobile-menu-btn")
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
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-rightbar-toggle')"):
            break
    print(f"base={BASE} 会话={t} 视口={page.viewport_size}\n")

    d0 = page.evaluate(STATE)
    print(f"初始: 按钮激活={d0['btnOn']} 面板 rect={d0['rect']}")

    if not tap(page, "#dsh-mobile-rightbar-toggle"):
        print("✗ 找不到 #dsh-mobile-rightbar-toggle 按钮"); sys.exit(2)
    page.wait_for_timeout(2200)
    d1 = page.evaluate(STATE)
    print("\n点击「工作区文件」按钮后:")
    for k in ("cls", "rect", "pos", "vis", "effOpacity", "pointerEvents", "inViewport", "visible", "hitInside", "clickables", "btnOn"):
        print(f"  {k:12s} = {d1.get(k)}")
    print(f"  text = {d1.get('text')!r}")
    if not d1["visible"]:
        fails.append(f"面板未全屏可见 rect={d1['rect']}")
    if d1["vis"] != "visible" or d1["effOpacity"] < 0.9 or d1["pointerEvents"] == "none":
        fails.append(f"面板不可见 vis={d1['vis']} op={d1['effOpacity']} pe={d1['pointerEvents']}")
    if not d1["hitInside"]:
        fails.append("面板中心点不到（被覆盖）")
    if d1["clickables"] < 3:
        fails.append(f"面板内可点元素过少（{d1['clickables']}）")
    # ⚠️ 面板首屏内容随上游版本不同：0.1.7 是「开始/工作区文件/新建终端」菜单，
    #    0.1.5 直接是文件树 ⇒ 只要求有实质内容，别锁死文案。
    if len((d1["text"] or "").strip()) < 10:
        fails.append(f"面板内容为空或过短：{d1['text']!r}")
    page.screenshot(path=f"/tmp/{TAG}-open.png")

    # 用上游自带按钮关闭
    closed = page.evaluate("""() => {
      const b = document.querySelector('button[aria-label="收起右侧边栏"]');
      if (!b) return false;
      b.click(); return true;
    }""")
    page.wait_for_timeout(1200)
    d2 = page.evaluate(STATE)
    print(f"\n点上游「收起右侧边栏」({closed}) 后: 按钮激活={d2['btnOn']} 面板 rect={d2['rect']} visible={d2['visible']}")
    if d2["visible"]:
        fails.append(f"关闭后面板仍全屏可见 rect={d2['rect']}")
    if d2["btnOn"]:
        fails.append("关闭后工具按钮仍处于激活态")

    # 再打开一次；随后**用面板内上游自带的收起按钮**关闭
    # （面板是全屏浮层、z-index 远高于工具组 ⇒ 打开期间工具按钮被盖住，关闭入口在面板右上角）
    tap(page, "#dsh-mobile-rightbar-toggle")
    page.wait_for_timeout(1800)
    d3 = page.evaluate(STATE)
    print(f"再次打开: visible={d3['visible']}")
    if not d3["visible"]:
        fails.append("工具按钮第二次打开失败")
    covered = page.evaluate("""() => {
      const b = document.querySelector('#dsh-mobile-rightbar-toggle');
      if (!b) return null;
      const r = b.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
      return !(hit && (hit === b || b.contains(hit)));
    }""")
    print(f"打开期间工具组被面板覆盖: {covered}（预期 true —— 关闭走面板内按钮）")
    closed2 = page.evaluate("""() => {
      const b = document.querySelector('button[aria-label="收起右侧边栏"]');
      if (!b) return false;
      b.click(); return true;
    }""")
    page.wait_for_timeout(1300)
    d4 = page.evaluate(STATE)
    print(f"从面板内收起({closed2}): visible={d4['visible']} 按钮激活={d4['btnOn']}")
    if d4["visible"]:
        fails.append("面板内收起按钮没能关闭")
    if d4["btnOn"]:
        fails.append("关闭后工具按钮仍处激活态")

    print()
    if fails:
        print(f"❌ {len(fails)} 项异常：")
        for f in fails:
            print("   - " + f)
        sys.exit(1)
    print("✅ 右侧边栏入口：可打开、全屏可见可点、能关闭")
    ctx.close(); b.close()
