#!/usr/bin/env python3
"""PC（桌面视口）验证：mobile-ui 插件**绝不能**触碰右侧栏。

背景（2026-09-28 事故）：非移动端分支误调 closeRightbar() ⇒ 它点上游「收起右侧边栏」，
每次 sync（MutationObserver）都把用户的右侧栏收起 ⇒ 用户看到「不停打开/关闭右侧栏」。

判据：连续采样 N 秒，右侧栏的宽度 / grid 列 / 开关按钮 state 必须**保持不变**，
且 body 不得出现 dsh-mobile-rightbar（插件的移动端浮层 class）。

用法: python3 probe-pc-rightbar.py <base-url> <token-file> [--title 片段] [--seconds 8]
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE, TOKF = sys.argv[1], sys.argv[2]
TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
SECONDS = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 8
TOKEN = open(TOKF, encoding="utf-8").read().strip()

STATE = """
() => {
  const frame = [...document.querySelectorAll("div")].find((e) => {
    const cs = getComputedStyle(e);
    return cs.display === "grid" && e.children.length >= 3;
  });
  const rb = document.querySelector("[class*=rightbarCol]");
  const r = rb ? rb.getBoundingClientRect() : null;
  return {
    vw: window.innerWidth,
    grid: frame ? getComputedStyle(frame).gridTemplateColumns : null,
    gridInline: frame ? (frame.style.gridTemplateColumns || "(none)") : null,
    rb: r ? [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] : null,
    openBtn: !!document.querySelector('button[aria-label="打开右侧边栏"]'),
    closeBtn: !!document.querySelector('button[aria-label="收起右侧边栏"]'),
    mobileCls: document.body.classList.contains("dsh-mobile-ui"),
    overlayCls: document.body.classList.contains("dsh-mobile-rightbar"),
  };
}
"""

fails = []
with sync_playwright() as p:
    b = p.chromium.launch()
    # 桌面视口：1376x900（不 is_mobile，不 has_touch —— 与真 PC 一致）
    ctx = b.new_context(viewport={"width": 1376, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE}/?token={TOKEN}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)

    # PC 端：左侧栏直接可见，点第一个会话
    rows = page.query_selector_all("[role=treeitem][class*=sessionRow]") or page.query_selector_all("[role=treeitem]")
    picked = t = None
    for row in rows[:12]:
        s = (row.inner_text() or "").strip().replace("\n", " ")
        if TITLE and TITLE in s:
            picked, t = row, s[:26]; break
        if not TITLE and s and "新会话" not in s:
            picked, t = row, s[:26]; break
    if picked is None:
        print("找不到会话"); sys.exit(2)
    picked.click()
    page.wait_for_timeout(3000)
    print(f"base={BASE} 会话={t}")

    d0 = page.evaluate(STATE)
    print(f"视口宽={d0['vw']}（桌面档）  mobile class={d0['mobileCls']}")
    # 确保右侧栏处于「打开」状态（PC 上它就是上游原生三列之一）
    if d0["openBtn"]:
        page.evaluate("() => document.querySelector('button[aria-label=\"打开右侧边栏\"]').click()")
        page.wait_for_timeout(1500)
        d0 = page.evaluate(STATE)
        print("（先手动打开右侧栏，模拟用户在用的状态）")

    print(f"\n初始: grid={d0['grid']} inline={d0['gridInline']} rb={d0['rb']} "
          f"开按钮={d0['openBtn']} 收按钮={d0['closeBtn']}")
    base_rb, base_grid, base_inline = d0["rb"], d0["grid"], d0["gridInline"]

    print(f"\n连续采样 {SECONDS} 秒（每次 1s）:")
    samples = []
    for i in range(SECONDS):
        time.sleep(1)
        d = page.evaluate(STATE)
        samples.append(d)
        print(f"  t={i+1}s  rb={d['rb']}  grid={d['grid']}  inline={d['gridInline']}  "
              f"overlayCls={d['overlayCls']}  开={d['openBtn']} 收={d['closeBtn']}")

    changed = [s for s in samples if s["rb"] != base_rb or s["grid"] != base_grid or s["gridInline"] != base_inline]
    if changed:
        fails.append(f"右侧栏状态在 {len(changed)}/{SECONDS} 次采样中发生了变化（应为恒定）")
    if any(s["overlayCls"] for s in samples):
        fails.append("PC 端出现了 dsh-mobile-rightbar 浮层 class")
    if any(s["mobileCls"] for s in samples):
        fails.append("PC 端出现了 dsh-mobile-ui class")

    print()
    if fails:
        print(f"❌ {len(fails)} 项异常：")
        for f in fails:
            print("   - " + f)
        sys.exit(1)
    print(f"✅ PC 端右侧栏在 {SECONDS} 秒内保持不变（插件未触碰上游右侧栏）")
    page.screenshot(path="/tmp/pc-rightbar.png")
    ctx.close(); b.close()
