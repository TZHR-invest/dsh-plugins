#!/usr/bin/env python3
"""真机化交互验证：用真实设备描述符 + 触摸点击，验三个工具按钮的**行为**（不只是存在）。

判据（对照 docs/dsh-mobile-ui.md §3.3 / §6）：
  ⋯ → 必须弹出 [role=menu]，菜单在视口内、有条目、且**不被祖先透明/遮罩吃掉**
  ▤ → 输入区高度必须明显变化（折叠/展开）
  ☰ → 抽屉必须打开（.dsh-mobile-drawer 可见）
用法: python3 probe-actions.py <base-url> <token-file> [--device "Pixel 7"] [--title 片段]
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1]
TOKF = sys.argv[2]
DEVICE = sys.argv[sys.argv.index("--device") + 1] if "--device" in sys.argv else "Pixel 7"
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TAG = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "act"
TOKEN = open(TOKF, encoding="utf-8").read().strip()

DRAWER = """
() => {
  const vis = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.visibility !== "hidden" && parseFloat(cs.opacity || "1") > 0.5 && r.width > 1 && r.height > 1;
  };
  return { scrim: vis(document.querySelector(".dsh-mobile-scrim")),
           drawer: vis(document.querySelector(".dsh-mobile-drawer")) };
}
"""

MENU = """
() => {
  const menus = [...document.querySelectorAll('[role=menu], [role=listbox]')].filter((m) => {
    const r = m.getBoundingClientRect();
    return r.width > 40 && r.height > 20;
  });
  if (!menus.length) return { count: 0 };
  const m = menus[menus.length - 1];
  const r = m.getBoundingClientRect();
  // visibility 是继承属性：getComputedStyle(自身) 已含继承结果，只判它即可
  //（逐级判祖先会把「祖先 hidden 但自己 visible」误报成不可见，2026-09-28 踩过）。
  // opacity 是「组不透明度」、pointer-events 也是继承 ⇒ 这两项必须逐级。
  const vis = getComputedStyle(m).visibility;
  let op = 1, pe = "auto", node = m.parentElement;
  while (node && node !== document.documentElement) {
    const s = getComputedStyle(node);
    op *= parseFloat(s.opacity || "1");
    if (s.pointerEvents === "none") pe = "none";
    node = node.parentElement;
  }
  const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
  const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
  const hit = document.elementFromPoint(cx, cy);
  const items = m.querySelectorAll('[role=menuitem], button, a').length;
  return {
    count: menus.length,
    rect: [r.left, r.top, r.width, r.height].map(Math.round),
    inViewport: r.left >= -1 && r.right <= window.innerWidth + 1 && r.top >= -1 && r.bottom <= window.innerHeight + 1,
    effOpacity: +op.toFixed(2), visibility: vis, pointerEvents: pe,
    hitInside: !!(hit && m.contains(hit)),
    items,
    text: (m.innerText || "").replace(/\\n/g, " | ").slice(0, 90),
  };
}
"""

COMPOSER = """
() => {
  const c = document.querySelector('[class*=composerSeat]') || document.querySelector('[class*=composer]');
  if (!c) return null;
  const r = c.getBoundingClientRect();
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
}
"""


def tap(page, sel):
    box = page.evaluate("""(sel) => { const el = document.querySelector(sel); if (!el) return null;
        const r = el.getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; }""", sel)
    if box is None:
        return False
    page.touchscreen.tap(box[0], box[1])
    return True


fails = []
with sync_playwright() as p:
    b = p.chromium.launch()
    dev = p.devices.get(DEVICE) or p.devices["Pixel 5"]
    ctx = b.new_context(**dev)
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    print(f"base={BASE}  device={DEVICE} viewport={page.viewport_size}")

    tap(page, "#dsh-mobile-menu-btn")
    page.wait_for_timeout(1500)
    rows = page.query_selector_all("[role=treeitem][class*=sessionRow]") or page.query_selector_all("[role=treeitem]")
    picked = title = None
    for row in rows[:12]:
        t = (row.inner_text() or "").strip().replace("\n", " ")
        if TITLE and TITLE in t:
            picked, title = row, t[:28]
            break
        if not TITLE and t and "新会话" not in t:
            picked, title = row, t[:28]
            break
    if picked is None:
        print("找不到会话"); sys.exit(2)
    picked.click()
    page.wait_for_timeout(1500)
    for _ in range(6):
        if page.evaluate(DRAWER)["drawer"] is False and page.evaluate(DRAWER)["scrim"] is False:
            break
        page.touchscreen.tap(page.viewport_size["width"] - 30, 500)
        page.wait_for_timeout(900)
    print(f"会话：{title}\n")

    # ── ⋯ 更多操作 ──
    print("── ⋯ (dsh-mobile-more-proxy) ──")
    tap(page, "#dsh-mobile-more-proxy")
    page.wait_for_timeout(1500)
    m = page.evaluate(MENU)
    if not m.get("count"):
        print("  ✗ 点击后没有出现 [role=menu]")
        fails.append("⋯ 点击无菜单")
    else:
        print(f"  菜单 rect={m['rect']} items={m['items']} inViewport={m['inViewport']} "
              f"op={m['effOpacity']} vis={m['visibility']} pe={m['pointerEvents']} hitInside={m['hitInside']}")
        print(f"  文本: {m['text']}")
        if not m["inViewport"]:
            fails.append(f"⋯ 菜单出视口 {m['rect']}")
        if m["effOpacity"] < 0.9 or m["visibility"] != "visible" or m["pointerEvents"] == "none":
            fails.append(f"⋯ 菜单不可见（op={m['effOpacity']} vis={m['visibility']} pe={m['pointerEvents']}）")
        if not m["hitInside"]:
            fails.append("⋯ 菜单中心点不到（被盖）")
        if m["items"] == 0:
            fails.append("⋯ 菜单没有条目")
    page.screenshot(path=f"/tmp/{TAG}-menu.png")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)

    # ── ▤ 折叠输入区 ──
    print("\n── ▤ (dsh-mobile-fold-composer) ──")
    c0 = page.evaluate(COMPOSER)
    tap(page, "#dsh-mobile-fold-composer")
    page.wait_for_timeout(1200)
    c1 = page.evaluate(COMPOSER)
    print(f"  输入区高度 {c0[3] if c0 else None} → {c1[3] if c1 else None}")
    if c0 and c1 and abs(c0[3] - c1[3]) < 20:
        fails.append(f"▤ 点击后输入区高度没变化（{c0[3]} → {c1[3]}）")
    page.screenshot(path=f"/tmp/{TAG}-fold.png")
    tap(page, "#dsh-mobile-fold-composer")   # 复原
    page.wait_for_timeout(1000)

    # ── ☰ 打开抽屉 ──
    print("\n── ☰ (dsh-mobile-tab-menu) ──")
    before = page.evaluate(DRAWER)
    tap(page, "#dsh-mobile-tab-menu")
    page.wait_for_timeout(1500)
    after = page.evaluate(DRAWER)
    print(f"  点击前 {before}  →  点击后 {after}")
    if not after["drawer"]:
        fails.append(f"☰ 点击后抽屉没打开（{after}）")
    page.screenshot(path=f"/tmp/{TAG}-drawer.png")

    print()
    if fails:
        print(f"❌ {len(fails)} 项异常：")
        for f in fails:
            print("   - " + f)
        sys.exit(1)
    print("✅ 三个按钮行为均正常")
    ctx.close(); b.close()
