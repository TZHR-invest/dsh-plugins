#!/usr/bin/env python3
"""dsh-mobile-ui 真实页面（live）交互探针：头部切换器几何 + 子代理菜单 toggle + 抽屉回归。

和 `mobile-layout-probe.py`（静态复现页 + 真实上游 CSS）互补：那套测**几何**，
这套测**交互**——2026-09-14 的两个问题都只在真实 dsh 页面上出现：

  ① 头部子代理切换器被 crumbs 裁掉：宽度只露 27px（「[方块] 8」），
     且中心点的点击落在右侧 headerActions 的“标准模式”上 ⇒ 打不开子代理列表；
  ② 上游切换器在**触摸设备上只能开不能收**：trigger 的 onClick 是条件绑定
     （`onClick: openTitle === void 0 ? void 0 : …`，头部这个变体没有 openTitle
     ⇒ 本体无点击逻辑），“打开”实际靠容器 onMouseEnter(150ms)，
     而再点同一处不会再产生 mouseenter ⇒ 既关不掉也开不回来。
     插件用官方键盘路径补的 toggle：展开时点→Escape，收起时点→ArrowDown。

用法（需要目标机 dsh web 在跑，且会话列表里有**含子代理**的会话）：

    python3 tests/live-probe.py
    python3 tests/live-probe.py --base-url http://192.168.0.205:3080 --session miniqmt
    python3 tests/live-probe.py --token-file ~/.dsh/lan-access-token --viewport 390x844

退出码非 0 = 回归。桌面（>768px）语义不在本探针范围：上游 hover 开合，插件不介入。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

MENUS = "() => document.querySelectorAll('[class*=ZKlsPq_menu]').length"
ROWS = """() => [...document.querySelectorAll('[class*=ZKlsPq_row]')]
  .map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.x + 40), Math.round(r.y + 20)]; })"""
GEOM = """() => {
  const sw = [...document.querySelectorAll('button[class*=ZKlsPq_trigger]')].pop();
  const crumbs = document.querySelector('[class*=wSkVaW_crumbs]') || document.querySelector('[class*=crumbs]');
  if (!sw || !crumbs) return { err: sw ? 'no crumbs' : 'no switcher (该会话没有子代理？)' };
  const b = sw.getBoundingClientRect(), c = crumbs.getBoundingClientRect();
  const t = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
  return {
    text: (sw.textContent || '').trim(), w: Math.round(b.width), h: Math.round(b.height),
    clipped: b.right > c.right + 0.5, tall: b.height > 40,
    clickable: !!(t && t.closest && t.closest('button[class*=ZKlsPq_trigger]')),
    crumbsText: (crumbs.innerText || '').replace(/\\n/g, ' ').slice(0, 60),
  };
}"""
POPOVER = """(sel) => { const m = document.querySelector(sel); if (!m) return null;
  const r = m.getBoundingClientRect();
  const items = m.querySelectorAll('[role=menuitem],[class*=row],[class*=item_]').length;
  const mid = document.elementFromPoint(r.right - 40, r.top + 16);
  return { left: Math.round(r.left), right: Math.round(r.right), h: Math.round(r.height), items: items,
    ok: r.left >= -0.5 && r.right <= window.innerWidth + 0.5,
    topRightHit: mid ? String(mid.className || '').split(' ').pop().slice(0, 22) : null,
    hamburger: (document.getElementById('dsh-mobile-menu-btn') || {}).style ? document.getElementById('dsh-mobile-menu-btn').style.display : '?' }; }"""

DRAWER = """() => { const s = document.querySelector('[class*=sidebarCol]');
  return s ? (getComputedStyle(s).display + ':' + Math.round(s.getBoundingClientRect().width)) : 'none'; }"""

# ⚠️ [role=treeitem] 里**混着工作区节点**（点它会切换工作区 → 整批换掉会话列表，
#   2026-09-14 实测按索引点会点到工作区）；会话行才带 sessionRow 类名，必须用它过滤。
SESSION_ROWS_JS = "[...document.querySelectorAll('[role=treeitem][class*=sessionRow]')]"
SESSION_LABELS = """(needle) => %s
  .map(r => (r.textContent || '').trim())
  .filter(t => !needle || t.includes(needle))""" % SESSION_ROWS_JS
SESSION_CLICK = """(t) => { for (const r of %s)
  if ((r.textContent || '').trim() === t) { r.click(); return true; } return false; }""" % SESSION_ROWS_JS


def run(args) -> int:
    from playwright.sync_api import sync_playwright

    token_file = pathlib.Path(args.token_file).expanduser()
    if not token_file.exists():
        print(f"找不到 token 文件：{token_file}")
        return 2
    token = token_file.read_text(encoding="utf-8").strip()
    w, h = (int(x) for x in args.viewport.lower().split("x"))
    base = args.base_url.rstrip("/")
    fails: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(f"{base}/?token={token}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # ① 逐个试开会话，直到找到一个**有子代理**的（列表里多数会话没有切换器）
        page.touchscreen.tap(w - 33, 69)
        page.wait_for_timeout(1300)
        labels = page.evaluate(SESSION_LABELS, args.session or "")
        page.touchscreen.tap(w - 30, 500)          # 关抽屉
        page.wait_for_timeout(1000)
        if not labels:
            print(f"❌ 会话列表里没有可打开的会话（--session={args.session!r}）")
            return 2
        geom, opened = {"err": "未找到含子代理的会话"}, None
        for i in range(args.session_tries):
            page.touchscreen.tap(w - 33, 69)       # 开抽屉
            page.wait_for_timeout(1200)
            # ⚠️ 每次都要重新读列表：点开其它工作区的会话会切换工作区，会话列表随之整批变化
            #   （按索引点会点错行 —— 必须"读当下这一行的文本 → 再按该文本点")
            rows_now = page.evaluate(SESSION_LABELS, args.session or "")
            if i >= len(rows_now):
                break
            label = rows_now[i]
            clicked = page.evaluate(SESSION_CLICK, label)
            if not clicked:
                continue
            page.wait_for_timeout(1500)
            page.touchscreen.tap(w - 30, 500)      # 点 scrim 关抽屉（点会话项不会自动关）
            page.wait_for_timeout(800)
            # 会话历史可能很大（实测 1.1MB，首次渲染要数秒）⇒ 轮询等切换器出现，别固定睡眠
            geom, opened = {"err": "未找到含子代理的会话"}, label
            for _ in range(12):
                geom = page.evaluate(GEOM)
                if not geom.get("err"):
                    break
                page.wait_for_timeout(1000)
            if not geom.get("err"):
                break
            print(f"  跳过（无子代理切换器）：{label[:40]}")
        if opened:
            print(f"打开会话：{opened[:40]}")

        # ② 头部切换器几何
        print(f"切换器：{json.dumps(geom, ensure_ascii=False)}")
        if geom.get("err"):
            fails.append(geom["err"])
        else:
            if geom["clipped"]:
                fails.append(f"切换器被 crumbs 裁掉（宽仅 {geom['w']}px，right 超出 crumbs）")
            if geom["tall"]:
                fails.append(f"切换器非单行（高 {geom['h']}px > 40px）")
            if not geom["clickable"]:
                fails.append("切换器中心点不到它（被其它元素覆盖）")

        # ③ toggle：连点 4 次应为 开/关/开/关
        if not geom.get("err"):
            sw = page.evaluate("""() => { const b = [...document.querySelectorAll('button[class*=ZKlsPq_trigger]')].pop();
                const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }""")
            seq = []
            for _ in range(4):
                page.touchscreen.tap(sw["x"], sw["y"])
                page.wait_for_timeout(800)
                seq.append(page.evaluate(MENUS))
            print(f"toggle 序列：{seq}（期望 [1,0,1,0]）")
            if seq != [1, 0, 1, 0]:
                fails.append(f"点击无法临时开合：{seq}（期望 [1,0,1,0]）")

            # ③b 顶部 popover 不许出视口（2026-09-14 用户报「点后台任务/终端/session 日志显示不全」：
            #     上游按桌面宽度做左/右对齐 —— 后台任务菜单 right 溢出 207px、「更多操作」菜单 left 溢出 90px）
            for name, trig_sel, menu_sel in (
                ("后台任务菜单", "button[class*=QsffPG_trigger]", "[class*=QsffPG_menu]"),
                # 「更多操作」的入口是插件注入的**代理按钮**：上游按钮已被移出可点层
                # （position:absolute; opacity:0; pointer-events:none —— 否则它会算出 0×0 的菜单，
                #  见 client.js 里 headerUtilities 段注释），点它才算走用户的真实路径
                ("更多操作菜单", "#dsh-mobile-more-proxy", "[role=menu][class*=_list_1nxmc_]"),
            ):
                pos = page.evaluate(
                    """(s) => { const b = document.querySelector(s); if (!b) return null;
                         const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }""", trig_sel)
                if not pos:
                    print(f"  [{name}] 入口不存在，跳过")
                    continue
                page.touchscreen.tap(pos[0], pos[1])
                page.wait_for_timeout(1500)
                g = page.evaluate(POPOVER, menu_sel)
                print(f"  [{name}] {json.dumps(g, ensure_ascii=False)}")
                if not g or not g.get("ok"):
                    fails.append(f"{name}跑出视口（{g}）—— 上游对齐按桌面宽度算，插件的浮层约束失效？")
                elif g.get("items", 0) < 1:
                    fails.append(f"{name}打开后没有任何条目（{g}）")
                page.keyboard.press("Escape")
                page.wait_for_timeout(800)

            # ③c header 瘦身 + 折叠输入区（2026-09-14：用户反馈「标题栏三行有点乱 / 正文显得窄」）
            lay = page.evaluate("""() => {
              const hdr = document.querySelector('header'); const hb = hdr ? hdr.getBoundingClientRect().bottom : 0;
              const seat = document.querySelector('[class*=composerSeat]');
              const seatVis = seat && getComputedStyle(seat).display !== 'none' && seat.getBoundingClientRect().height > 0;
              const bottom = seatVis ? seat.getBoundingClientRect().top : window.innerHeight;
              const tools = [...document.querySelectorAll('#dsh-mobile-tab-tools button')].map(b => b.id);
              const hamburger = document.getElementById('dsh-mobile-menu-btn');
              return { headerH: Math.round(hb), readPct: Math.round((bottom - hb) / window.innerHeight * 100),
                tools: tools, hamburgerHidden: hamburger ? getComputedStyle(hamburger).display === 'none' : null }; }""")
            print(f"  [布局] header={lay['headerH']}px 正文占比={lay['readPct']}% 工具={lay['tools']}")
            # 行数回涨（三行 header ⇒ 138px）或工具组缺失都算回归
            if lay["headerH"] > 120:
                fails.append(f"header 又变高了（{lay['headerH']}px > 120px，是不是行数回涨了？）")
            if len(lay["tools"]) < 3:
                fails.append(f"tabs 行工具组不全：{lay['tools']}（应含 more-proxy / fold-composer / tab-menu）")
            if lay.get("hamburgerHidden") is not True:
                fails.append("会话页的原悬浮汉堡没隐藏（会压住第二行/tabs 行）")
            # 折叠切换：正文占比应显著上升，且按钮状态跟着翻
            fold = page.evaluate("""() => { const b = document.getElementById('dsh-mobile-fold-composer'); if (!b) return null;
                const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }""")
            if fold:
                page.touchscreen.tap(fold[0], fold[1])
                page.wait_for_timeout(1200)
                folded = page.evaluate("""() => {
                  const seat = document.querySelector('[class*=composerSeat]');
                  const seatVis = seat && getComputedStyle(seat).display !== 'none' && seat.getBoundingClientRect().height > 0;
                  const hb = document.querySelector('header').getBoundingClientRect().bottom;
                  const bottom = seatVis ? seat.getBoundingClientRect().top : window.innerHeight;
                  return { hidden: document.body.classList.contains('dsh-mobile-composer-hidden'),
                    readPct: Math.round((bottom - hb) / window.innerHeight * 100) }; }""")
                print(f"  [折叠] hidden={folded['hidden']} 正文占比={folded['readPct']}%")
                if not folded["hidden"] or folded["readPct"] < lay["readPct"] + 15:
                    fails.append(f"折叠输入区没生效（{lay['readPct']}% → {folded['readPct']}%）")
                page.touchscreen.tap(fold[0], fold[1])   # 复原，别影响后续断言
                page.wait_for_timeout(1000)
                back = page.evaluate("() => document.body.classList.contains('dsh-mobile-composer-hidden')")
                if back:
                    fails.append("再次点击没能恢复输入区")

            # ④ 菜单行可进入子代理（面包屑应变成两段）
            page.touchscreen.tap(sw["x"], sw["y"])
            page.wait_for_timeout(800)
            rows = page.evaluate(ROWS)
            if not rows:
                fails.append("菜单里没有 ZKlsPq_row（上游结构可能已变）")
            else:
                page.touchscreen.tap(rows[0][0], rows[0][1])
                page.wait_for_timeout(3000)
                after = page.evaluate("""() => { const c = document.querySelector('[class*=crumbs]');
                    return c ? (c.innerText || '').replace(/\\n/g, ' ').slice(0, 60) : ''; }""")
                print(f"点子代理行后面包屑：{after}")
                if "/" not in after or len(after) <= len((geom.get("crumbsText") or "")):
                    fails.append(f"点子代理行没有进入子代理会话（面包屑未变化：{after!r}）")

        # ⑤ 抽屉回归（补丁不得吞掉其它点击）
        page.touchscreen.tap(w - 33, 69)
        page.wait_for_timeout(1200)
        drawer_open = page.evaluate(DRAWER)
        page.touchscreen.tap(w - 30, 500)
        page.wait_for_timeout(1000)
        drawer_closed = page.evaluate(DRAWER)
        print(f"抽屉：开={drawer_open} 关={drawer_closed}")
        if drawer_open.startswith("none") or not drawer_closed.startswith("none"):
            fails.append(f"抽屉开合回归（开={drawer_open} 关={drawer_closed}）")

        browser.close()

    print()
    if fails:
        print(f"❌ 真实页面回归：{len(fails)} 项不达标")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ 真实页面交互全部通过（切换器完整可点、点击可开可收、菜单可进入子代理、抽屉正常）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="dsh-mobile-ui 真实页面交互探针")
    ap.add_argument("--base-url", default="http://127.0.0.1:3080", help="dsh web 地址")
    ap.add_argument("--token-file", default="~/.dsh/lan-access-token", help="门卫/访问令牌文件")
    ap.add_argument("--session", default=None, help="会话标题片段（默认按列表顺序逐个试）")
    ap.add_argument("--session-tries", type=int, default=6, help="最多试开几个会话以找到含子代理的")
    ap.add_argument("--viewport", default="390x844", help="WxH（默认 390x844，手机档）")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
