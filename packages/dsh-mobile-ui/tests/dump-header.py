#!/usr/bin/env python3
"""打开一个真实会话，dump 会话头部（header）里所有按钮的几何/可见性，定位 ⋯ 与 ☰ 的问题。

用法: python3 dump-header.py <base-url> <token-file> [--title 片段] [--width 390]
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1]
TOKF = sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
WIDTH = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 390
TAG = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "dump"
TOKEN = open(TOKF, encoding="utf-8").read().strip()

DUMP_JS = """
() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll("button, [role=button], a[class*=btn]").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.top < -5 || r.top > 260) return;          // 只看贴顶的头部区域（排除滚出屏的内容）
    if (r.left < -5 || r.left > window.innerWidth + 5) return;
    const cs = getComputedStyle(el);
    let op = 1, vis = "visible", pe = "auto", node = el;
    while (node && node !== document.documentElement) {
      const s = getComputedStyle(node);
      op *= parseFloat(s.opacity || "1");
      if (s.visibility === "hidden") vis = "hidden";
      if (s.pointerEvents === "none") pe = "none";
      node = node.parentElement;
    }
    const key = (el.id || "") + "|" + (el.className || "").toString().slice(0, 40) + "|" + Math.round(r.left) + "," + Math.round(r.top);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      id: el.id || null,
      cls: (el.className || "").toString().slice(0, 70),
      label: el.getAttribute("aria-label") || (el.innerText || "").trim().slice(0, 14) || null,
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      op: +op.toFixed(2), vis, pe,
      clipped: el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1,
      scrollW: el.scrollWidth, clientW: el.clientWidth,
    });
  });
  const tabs = document.querySelector('[class*=tabs]');
  const header = document.querySelector('[class*=titleRow]') || document.querySelector('[class*=wSkVaW_header]');
  return {
    buttons: out,
    tabsFound: !!tabs,
    tabsCls: tabs ? tabs.className.toString().slice(0, 90) : null,
    headerFound: !!header,
    headerCls: header ? header.className.toString().slice(0, 90) : null,
    headerRect: header ? (() => { const r = header.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; })() : null,
    toolGroup: !!document.querySelector("#dsh-mobile-tab-tools"),
  };
}
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": WIDTH, "height": 900}, is_mobile=True, has_touch=True, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    print(f"base={BASE} width={WIDTH}")

    # 打开抽屉 → 选一个真实会话（跳过空的新会话）
    page.click("#dsh-mobile-menu-btn", timeout=8000)
    page.wait_for_timeout(1500)
    rows = page.query_selector_all("[role=treeitem][class*=sessionRow]") or page.query_selector_all("[role=treeitem]")
    picked, title = None, None
    for row in rows[:12]:
        txt = (row.inner_text() or "").strip().replace("\n", " ")
        if TITLE:
            if TITLE in txt:
                picked, title = row, txt[:34]
                break
        elif "新会话" not in txt and txt:
            picked, title = row, txt[:34]
            break
    if picked is None:
        print("找不到目标会话"); sys.exit(2)
    picked.click()
    page.wait_for_timeout(1500)
    scrim = page.query_selector("[class*=scrim]")
    if scrim:
        try:
            scrim.click(timeout=3000)
        except Exception:
            page.keyboard.press("Escape")
    # 等会话内容 + 插件 sync（文档：历史可能很大，改用轮询）
    for i in range(30):
        page.wait_for_timeout(1000)
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-tab-tools') || !!document.querySelector('[class*=tabs]')"):
            break
    page.wait_for_timeout(2500)
    print(f"会话：{title}\n")
    d = page.evaluate(DUMP_JS)
    print(f"tabs 行: {d['tabsFound']}  cls={d['tabsCls']}")
    print(f"header : {d['headerFound']}  cls={d['headerCls']}  rect={d['headerRect']}")
    print(f"插件工具组 #dsh-mobile-tab-tools: {d['toolGroup']}")
    print("\n--- 头部区域按钮 ---")
    for x in d["buttons"]:
        flags = []
        if x["op"] < 0.9:
            flags.append(f"op={x['op']}")
        if x["vis"] != "visible":
            flags.append("visibility:hidden")
        if x["pe"] == "none":
            flags.append("pointer-events:none")
        if x["clipped"]:
            flags.append(f"内容溢出 scrollW={x['scrollW']}>clientW={x['clientW']}")
        print(f"  id={x['id']} cls={x['cls'][:46]} label={x['label']} rect={x['rect']} " + ("; ".join(flags) if flags else ""))
    page.screenshot(path=f"/tmp/mob-{TAG}-{WIDTH}.png")
    print(f"\n截图: /tmp/mob-{TAG}-{WIDTH}.png")
    ctx.close()
    b.close()
