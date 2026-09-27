#!/usr/bin/env python3
"""诊断右侧边栏（工作区文件面板）：frame grid / detailsCol / 相关按钮。

用法: python3 dump-rightbar.py <base-url> <token-file> [--title 片段]
"""
import sys

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
TOKEN = open(TOKF, encoding="utf-8").read().strip()

JS = """
() => {
  const rect = (el) => { const r = el.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };
  const out = { grid: null, cols: [], buttons: [] };

  // 主布局 frame（display:grid 且子元素 ≥3）
  const frames = [...document.querySelectorAll("div")].filter((e) => {
    const cs = getComputedStyle(e);
    return cs.display === "grid" && e.children.length >= 3;
  });
  if (frames.length) {
    const f = frames[0], cs = getComputedStyle(f);
    out.grid = { cls: (f.className || "").toString().slice(0, 70), cols: cs.gridTemplateColumns,
                 rect: rect(f), inlineCols: f.style.gridTemplateColumns || null, vw: window.innerWidth };
    for (const ch of f.children) {
      const cs = getComputedStyle(ch);
      out.cols.push({ cls: (ch.className || "").toString().slice(0, 70), display: cs.display,
                      pos: cs.position, vis: cs.visibility, rect: rect(ch),
                      overflow: cs.overflow, text: (ch.innerText || "").trim().slice(0, 40) });
    }
  }

  // 含关键词的按钮（不论可见性）
  document.querySelectorAll("button, [role=button]").forEach((el) => {
    const label = ((el.getAttribute("aria-label") || "") + " " + (el.title || "") + " " + (el.innerText || "").slice(0, 14)).trim();
    if (/侧边栏|右侧|文件|预览|面板|详情|工作区|sidebar|panel|detail|file/i.test(label)) {
      const cs = getComputedStyle(el);
      out.buttons.push({ label: label.slice(0, 44), cls: (el.className || "").toString().slice(0, 54),
                         display: cs.display, vis: cs.visibility, rect: rect(el) });
    }
  });
  return out;
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
        if page.evaluate("() => !!document.querySelector('#dsh-mobile-tab-tools')"):
            break
    print(f"base={BASE} 会话={t} 视口={page.viewport_size}\n")
    d = page.evaluate(JS)

    if d["grid"]:
        g = d["grid"]
        print(f"frame grid: cls={g['cls']}")
        print(f"  cols(computed) = {g['cols']}")
        print(f"  cols(inline)   = {g['inlineCols']}   ← 插件若改单列会写在这里")
        print(f"  rect={g['rect']}\n  ── 三列 ──")
        for c in d["cols"]:
            print(f"    cls={c['cls'][:52]:52s} display={c['display']:12s} pos={c['pos']:9s} vis={c['vis']:8s} rect={c['rect']} text={c['text']!r}")
    else:
        print("（没找到 display:grid 且 ≥3 子元素的 frame）")

    print(f"\n── 含侧栏/文件关键词的按钮（{len(d['buttons'])} 个）──")
    for x in d["buttons"]:
        print(f"  label={x['label']!r:46s} display={x['display']:10s} vis={x['vis']:8s} rect={x['rect']} cls={x['cls'][:40]}")
    ctx.close(); b.close()
