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
# 「更多操作」菜单的**语义锚**（2026-09-28 修）：
#   ⚠️ 别再写死 `_list_1nxmc_` —— 0.1.7 漂移成 `_list_gzo7u_`，且**失效是静默的**
#   （选择器不命中 ⇒ 菜单看着"没打开"，报出来的却是"跑出视口/没有条目"，指错方向）。
#   两版实测都成立的锚：菜单祖先里始终有 `wSkVaW_headerUtilities`
#   （祖先链 menu → span._root_*_1 → div → div.wSkVaW_headerUtilities → titleRow → header）。
MORE_MENU = "[class*=headerUtilities] [role=menu]"

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
  // ⚠️ 几何正常 ≠ 人能看见/能点：必须同时查「中心命中自身」+「祖先链上的有效可见性」
  //    （2026-09-15 教训：菜单 rect 完全正确、条目也在，但祖先 opacity:0 把它整棵子树变透明，
  //     只断言 left/right/items 的旧版探针一路放行 ⇒ 用户连报三轮「没反应」）
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(20, r.height / 2));
  // ⚠️ visibility 只看**自身计算值**：祖先 visibility:hidden 会被后代的 visible 覆盖（这正是本插件的修法），
  //    扫祖先链会把「已经修好」判成 hidden（2026-09-15 自测踩到）。opacity 相反 —— 组不透明度**必须逐级相乘**。
  const vis = getComputedStyle(m).visibility; let op = 1, n = m;
  while (n && n !== document.body) { op *= parseFloat(getComputedStyle(n).opacity || '1'); n = n.parentElement; }
  return { left: Math.round(r.left), right: Math.round(r.right), h: Math.round(r.height), items: items,
    ok: r.left >= -0.5 && r.right <= window.innerWidth + 0.5,
    topRightHit: mid ? String(mid.className || '').split(' ').pop().slice(0, 22) : null,
    visibility: vis, effectiveOpacity: +op.toFixed(2), pointerEvents: getComputedStyle(m).pointerEvents,
    hitSelf: !!(hit && (hit === m || m.contains(hit))),
    hitTop: hit ? String(hit.id || hit.className || hit.tagName).split(' ').filter(Boolean).pop().slice(0, 22) : null,
    hamburger: (document.getElementById('dsh-mobile-menu-btn') || {}).style ? document.getElementById('dsh-mobile-menu-btn').style.display : '?' }; }"""

DRAWER = """() => { const s = document.querySelector('[class*=sidebarCol]');
  return s ? (getComputedStyle(s).display + ':' + Math.round(s.getBoundingClientRect().width)) : 'none'; }"""

# ⚠️ [role=treeitem] 里**混着工作区节点**（点它会切换工作区 → 整批换掉会话列表，
#   2026-09-14 实测按索引点会点到工作区）；会话行才带 sessionRow 类名，必须用它过滤。
SESSION_ROWS_JS = "[...document.querySelectorAll('[role=treeitem][class*=sessionRow]')]"
SESSION_LABELS = """(needle) => %s
  .map(r => (r.textContent || '').trim())
  .filter(t => !needle || t.includes(needle))""" % SESSION_ROWS_JS
# ⚠️ 当前会话那一行带 `selected` 类 —— 点它等于没点。判断"有没有可打开的会话"必须排除它，
#   否则「只有一个当前会话的工作区」会被误判成"有会话可开"（2026-09-28 home-wsl 实测踩到）。
SESSION_LABELS_UNSELECTED = """(needle) => %s
  .filter(r => !String(r.className || '').includes('selected'))
  .map(r => (r.textContent || '').trim())
  .filter(t => !needle || t.includes(needle))""" % SESSION_ROWS_JS

# ⚠️ 这里曾有个 SESSION_CLICK（JS `el.click()`）—— **已删除、勿再加回**：它在会话行上
#   时灵时不灵（2026-09-28 实测连点 5 次只有 2 次真跳转），会把「没点动」伪装成
#   「已进入会话」，于是后面所有断言都在测首页 ⇒ 报出一串**指向错误方向**的假回归。
#   正确做法 = `click_session()`（真实 tap，走用户路径）。


def tap_sel(page, sel):
    """按选择器点元素中心；不存在或尺寸为 0 返回 False。

    ⚠️ 别再用硬编码坐标：抽屉入口的位置/归属随 dsh 版本漂移过（0.1.5 是右上角悬浮汉堡，
    0.1.7 header 压矮后同一坐标落空）—— 2026-09-28 实测 `tap(w-33, 69)` 在 0.1.7 上
    压根没打开抽屉，⑤ 于是恒红，看起来像回归、其实是探针自己点空了。
    """
    box = page.evaluate("""(sel) => { const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return (r.width > 0 && r.height > 0) ? [r.left + r.width / 2, r.top + r.height / 2] : null; }""", sel)
    if box is None:
        return False
    page.touchscreen.tap(box[0], box[1])
    return True


def open_drawer(page):
    """开抽屉：会话页点 tabs 行的 ☰，回退首页右上角悬浮汉堡。返回点到的选择器或 None。"""
    for sel in ("#dsh-mobile-tab-menu", "#dsh-mobile-menu-btn"):
        if tap_sel(page, sel):
            return sel
    return None


def close_drawer(page, w):
    """关抽屉：点右侧空白。

    抽屉开着时插件会插一层 `#dsh-mobile-scrim.dsh-mobile-visible` 吃点击（它**在** DOM 里），
    但**不能点它的中心** —— 抽屉宽 320px、屏幕 390px，中心落在抽屉自身上；所以要偏右缘点。
    """
    page.touchscreen.tap(w - 30, 500)


def ensure_closed(page):
    """抽屉若开着就关掉；已关则**什么都不点**（在已关时乱点会误触页面内容）。"""
    w = page.viewport_size["width"]
    if not page.evaluate(DRAWER).startswith("none"):
        close_drawer(page, w)
        page.wait_for_timeout(700)
    return page.evaluate(DRAWER)


def open_drawer_confirmed(page, tries=3, poll=6):
    """点开抽屉并**轮询**确认，返回 (入口选择器, display:width)。

    为什么不「点一下、睡固定时长、再读一次」：2026-09-28 实测同一版本会偶发读到 none
    （采样竞态）⇒ 单次采样会让断言时红时绿、把真回归淹没在假阳性里。
    """
    w = page.viewport_size["width"]
    state, used = "none:0", None
    for _ in range(tries):
        used = open_drawer(page)
        if used is None:
            return None, state
        for _ in range(poll):
            state = page.evaluate(DRAWER)
            if not state.startswith("none"):
                return used, state
            page.wait_for_timeout(500)
        close_drawer(page, w)                      # 没开成 ⇒ 归零重试
        page.wait_for_timeout(600)
    return used, state


def click_session(page, label):
    """按标题点开会话 —— 用**真实 tap**（点行中心），不要用 JS `el.click()`。

    ⚠️ 2026-09-28 实测：`el.click()` 在会话行上**时灵时不灵**（连点 5 次只有 2 次真跳转），
    而症状极隐蔽 —— 探针以为"已进入会话"，其实还停在原页面，于是 ③b~③e 全都在测错对象
    （这正是"探针报绿却什么都没测到"的成因之一）。tap 走用户的真实路径，可靠。
    行可能被滚出抽屉可视区 ⇒ 先 scrollIntoView，再确认中心确实落在视口内。
    """
    box = page.evaluate("""(label) => {
        const r = [...document.querySelectorAll('[role=treeitem][class*=sessionRow]')]
          .find(e => (e.textContent || '').trim() === label);
        if (!r) return null;
        r.scrollIntoView({block: 'center'});
        const b = r.getBoundingClientRect();
        const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
        if (cx < 2 || cy < 2 || cx > innerWidth - 2 || cy > innerHeight - 2) return null;
        return [cx, cy]; }""", label)
    if box is None:
        return False
    page.touchscreen.tap(box[0], box[1])
    return True


def on_session_page(page):
    """当前是否是**会话页**（而不是首页/启动页）：会话页才有 header 与 tabs 行工具组。"""
    return page.evaluate("""() => ({ header: !!document.querySelector('header'),
        tools: document.querySelectorAll('#dsh-mobile-tab-tools button').length,
        ham: (() => { const h = document.getElementById('dsh-mobile-menu-btn');
            return h ? getComputedStyle(h).display : null; })() })""")


def reveal_sessions(page, needle="", max_expand=4):
    """确保抽屉里有**当前会话以外**的会话行可点 —— 工作区折叠时先展开它（抽屉需已开）。

    ⚠️ 落地状态因机而异（2026-09-28 home-wsl 实测踩到）：dsh 的抽屉是**工作区树**
    （每个工作区行带 `aria-expanded`）。ai-agent/devbox 落在已展开的工作区、直接有会话行；
    而 home-wsl 落在只含「当前那个空会话」的工作区 —— 48 个历史会话全在**折叠**的工作区里
    ⇒ 旧写法「开抽屉 → 读行」只看到 1 行、且正是当前会话，点它等于没点，
    探针报「会话列表里没有可打开的会话」，**而机器其实完全正常**。
    判据必须用**未选中**行数（`selected` 类），不是行数本身。
    """
    for _ in range(max_expand):
        unsel = page.evaluate(SESSION_LABELS_UNSELECTED, needle)
        if unsel:
            return unsel
        box = page.evaluate("""(needle) => {
            const cands = [...document.querySelectorAll('[role=treeitem]')]
              .filter(e => !String(e.className || '').includes('sessionRow')
                        && e.getAttribute('aria-expanded') === 'false'
                        && (!needle || (e.innerText || '').includes(needle)));
            if (!cands.length) return null;
            const e = cands[0];
            e.scrollIntoView({block: 'nearest'});
            const r = e.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return null;
            return [r.left + r.width / 2, r.top + r.height / 2]; }""", needle)
        if box is None:
            return []
        page.touchscreen.tap(box[0], box[1])
        page.wait_for_timeout(2000)
    return page.evaluate(SESSION_LABELS_UNSELECTED, needle)


def run(args) -> int:
    from playwright.sync_api import sync_playwright

    token_file = pathlib.Path(args.token_file).expanduser()
    if not token_file.exists():
        print(f"找不到 token 文件：{token_file}")
        return 2
    token = token_file.read_text(encoding="utf-8").strip()
    w, h = (int(x) for x in args.viewport.lower().split("x"))
    base = args.base_url.rstrip("/")
    fails, skips = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(f"{base}/?token={token}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # ① 逐个试开会话，直到找到一个**有子代理**的（列表里多数会话没有切换器）
        open_drawer(page)
        page.wait_for_timeout(1300)
        reveal_sessions(page, args.session or "")   # 工作区折叠时先展开（否则只会看到当前会话那行）
        labels = page.evaluate(SESSION_LABELS, args.session or "")
        ensure_closed(page)                       # 幂等关抽屉（已关则不点，免得误触）
        page.wait_for_timeout(1000)
        if not labels:
            print(f"❌ 会话列表里没有可打开的会话（--session={args.session!r}）")
            return 2
        geom, opened = {"err": "未找到含子代理的会话"}, None
        for i in range(args.session_tries):
            open_drawer(page)                      # 开抽屉（按元素点，勿硬编码坐标）
            page.wait_for_timeout(1200)
            # ⚠️ 每次都要重新读列表：点开其它工作区的会话会切换工作区，会话列表随之整批变化
            #   （按索引点会点错行 —— 必须"读当下这一行的文本 → 再按该文本点")
            reveal_sessions(page, args.session or "")
            rows_now = page.evaluate(SESSION_LABELS, args.session or "")
            # ⚠️⚠️ 每个出口都必须先关抽屉！上面刚 open_drawer 过，直接 break/continue 会把
            #   **开着的抽屉**留给后面的断言：抽屉宽 320px，③b 点的「后台任务」在 x≈146..270
            #   ⇒ 那一下实际点在**抽屉里的行**上（点到「新会话/工作区」），页面被带成空会话视图，
            #   于是后面报出「工具组不全 / ⋯ 按钮不能开合」等一串**指向错误方向**的假回归。
            #   （2026-09-28 实测：探针全绿的假象与这次假回归都源于此。）
            if i >= len(rows_now):
                ensure_closed(page)
                break
            label = rows_now[i]
            clicked = click_session(page, label)
            if not clicked:
                ensure_closed(page)
                continue
            page.wait_for_timeout(1500)
            # ⚠️ 只在抽屉确实开着时才点 scrim：无条件点会在**已关**时误触会话页内容
            #   （2026-09-28 实测把页面带到别的视图 ⇒ 后面断言全测错对象、报一堆假回归）。
            ensure_closed(page)
            page.wait_for_timeout(400)
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
        ensure_closed(page)          # 兜底：绝不能带着开着的抽屉去跑后面的断言
        page.wait_for_timeout(500)

        # ⚠️ 先确认**真的进了会话页**再往下断言：会话行没点动时，后面 ③b~③e 会拿首页去量，
        #   报出来的是"工具组不全 / ⋯ 按钮不能开合"之类**指向错误方向**的假回归。
        st = on_session_page(page)
        for _ in range(2):                          # 自愈：重新开抽屉→点会话→关抽屉
            if st["header"] and st["tools"]:
                break
            print(f"⚠️ 当前不在会话页（header={st['header']} tabs工具={st['tools']}）⇒ 重进一次")
            open_drawer(page)
            page.wait_for_timeout(1200)
            rows_retry = page.evaluate(SESSION_LABELS, args.session or "")
            if rows_retry:
                click_session(page, rows_retry[0])
                page.wait_for_timeout(2000)
            ensure_closed(page)
            page.wait_for_timeout(3500)
            st = on_session_page(page)
        if not st["header"] or st["tools"] == 0:
            print(f"❌ 重进也没能到会话页（header={st['header']} tabs工具={st['tools']} "
                  f"悬浮汉堡={st['ham']}）—— 会话行点了没反应？")
            print("   ⇒ 后面所有断言都会测错对象，直接中止（这是探针自身故障，不是插件回归）")
            fails.append("探针没能进入会话页（会话行点击失效）⇒ 断言未执行，先修探针")
            browser.close()
            print()
            print(f"❌ 真实页面回归：{len(fails)} 项不达标")
            for f in fails:
                print(f"   - {f}")
            return 1

        # ② 头部切换器几何
        print(f"切换器：{json.dumps(geom, ensure_ascii=False)}")
        if geom.get("err"):
            # 「试开的会话都没有子代理」= 本次**覆盖不到**，记 skip（否则每次跑都红、真回归被淹没）。
            #   ⚠️ 但本条**无法区分**两种成因：①本会话真的没有子代理（常态）
            #     ②上游把触发点改了（改名/换标签）—— 症状完全相同，都是"找不到切换器"。
            #   ② 的静态判据已核过（2026-09-28，0.1.5 与 0.1.7 的 dsh-client-ui-subagent
            #   bundle 逐句对照，三处契约一致）：触发点是
            #     jsxs("button", {className: …trigger|…switcherTrigger, "aria-expanded": open,
            #                      onKeyDown: ArrowDown → changeOpen(true)})
            #   关闭在 root 的 navigate：Escape → changeOpen(false, true)。
            #   ⇒ 复验命令与结论见 docs/dsh-mobile-ui.md §3.1；要**真覆盖**需含子代理的会话
            #     （本机历史上 0 个：179 会话头部 delegationDepth 全 0、正文 0 个 parentSessionId）
            #     ⇒ python3 tests/live-probe.py --session "<含子代理的会话标题>"
            skips.append(f"子代理切换器断言未覆盖（本会话无子代理；**也可能是上游改了触发点**，"
                         f"判据见 docs/dsh-mobile-ui.md §3.1）：{geom['err']}")
        else:
            if geom["clipped"]:
                fails.append(f"切换器被 crumbs 裁掉（宽仅 {geom['w']}px，right 超出 crumbs）")
            if geom["tall"]:
                fails.append(f"切换器非单行（高 {geom['h']}px > 40px）")
            if not geom["clickable"]:
                fails.append("切换器中心点不到它（被其它元素覆盖）")

        # ③ 子代理切换器 toggle：连点 4 次应为 开/关/开/关
        #   ⚠️ 这一段**必须**有子代理会话（header 才渲染 ZKlsPq_trigger）。
        #   ③b~③e 与子代理无关，**已从本 guard 里摘出去** —— 2026-09-28 实测发现：
        #   本机 179 个会话 delegationDepth 全为 0 ⇒ 永远找不到切换器 ⇒ 旧写法下
        #   「⋯ 按钮 / 412px 隐形死区 / header 瘦身 / 折叠输入区」这一整组**静默跳过**，
        #   而那正是用户报过故障的区域（探针全绿却什么都没测）。
        sw = page.evaluate("""() => { const b = [...document.querySelectorAll('button[class*=ZKlsPq_trigger]')].pop();
            if (!b) return null; const r = b.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }""")
        if not geom.get("err") and sw:
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
            ("更多操作菜单", "#dsh-mobile-more-proxy", MORE_MENU),
        ):
            pos = page.evaluate(
                """(s) => { const b = document.querySelector(s); if (!b) return null;
                     const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }""", trig_sel)
            if not pos:
                if trig_sel == "#dsh-mobile-more-proxy":
                    # 插件的 ⋯ 代理按钮在会话页本该存在 ⇒ 缺失=工具组没挂上，是**真回归**
                    fails.append("「更多操作」代理按钮不存在（#dsh-mobile-more-proxy 缺失，工具组没挂上？）")
                else:
                    # 上游**按需渲染**：该会话没有后台任务时压根不画这个按钮
                    # （2026-09-28 实测：本机该会话有「23 个后台任务」⇒ 有按钮；
                    #   devbox 同一会话没有 ⇒ 无按钮。查过两版 bundle，QsffPG 这个 hash **没漂移**，
                    #   别把"没有按钮"误判成"上游改结构了"。）
                    skips.append(f"{name}未覆盖：该会话没有后台任务，上游不渲染该按钮")
                    print(f"  [{name}] 入口不存在（该会话没有后台任务）⇒ 记 skip")
                continue
            page.touchscreen.tap(pos[0], pos[1])
            page.wait_for_timeout(1500)
            g = page.evaluate(POPOVER, menu_sel)
            print(f"  [{name}] {json.dumps(g, ensure_ascii=False)}")
            if not g or not g.get("ok"):
                fails.append(f"{name}跑出视口（{g}）—— 上游对齐按桌面宽度算，插件的浮层约束失效？")
            elif g.get("items", 0) < 1:
                fails.append(f"{name}打开后没有任何条目（{g}）")
            # ⚠️⚠️ 光有几何和条目不算数：必须真能看见、真能点到
            #   （2026-09-15 血泪：菜单 rect 全对、条目也在，但祖先 wSkVaW_headerUtilities 的
            #    opacity:0 把整棵子树变透明 + pointer-events:none 被继承 ⇒ 用户「点了没反应」，
            #    而只断言 left/right/items 的旧版探针一路绿灯）
            elif g.get("visibility") == "hidden" or g.get("effectiveOpacity", 1) < 0.9 \
                    or g.get("pointerEvents") == "none" or not g.get("hitSelf"):
                fails.append(
                    f"{name}看得见却点不到（visibility={g.get('visibility')} "
                    f"有效opacity={g.get('effectiveOpacity')} pointer-events={g.get('pointerEvents')} "
                    f"中心命中={g.get('hitTop')}）—— 祖先 opacity:0 的组透明 / pointer-events 继承泄漏？")
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

        # ③d 工具按钮必须真的能用：⋯ 代理按钮开→关一次就翻状态
        #     （曾因「上游 pointerdown 先关 / 我们的 click 又开」的竞态，命中率只有 2/6 ——
        #      用户报「三个点按钮点击没反应」；折叠按钮也曾因 30×26 目标过小被报「不灵敏」）
        menus_js = "() => document.querySelectorAll('%s').length" % MORE_MENU
        mp = page.evaluate("""() => { const b = document.getElementById('dsh-mobile-more-proxy'); if (!b) return null;
            const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }""")
        if mp:
            seq = []
            for _ in range(2):
                page.touchscreen.tap(mp[0], mp[1])
                page.wait_for_timeout(1000)
                seq.append(page.evaluate(menus_js))
            print(f"  [⋯ 代理按钮] 开合序列={seq}（期望 [1,0]）")
            if seq != [1, 0]:
                fails.append(f"「更多操作」代理按钮不能开合：{seq}（上游 pointerdown 与转发 click 的竞态又回来了？）")
            # 按钮尺寸：触摸目标不得小于 32px（插件规范 44，实测 30×26 时用户报"不灵敏"）
            size = page.evaluate("""() => { const b = document.getElementById('dsh-mobile-more-proxy');
                if (!b) return null; const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }""")
            if size and (size[0] < 32 or size[1] < 30):
                fails.append(f"工具按钮触摸目标过小：{size}")

        # ③e ⚠️⚠️ 宽度相关的「隐形死区」回归（2026-09-14 用户第三次报「三个点没反应」的真根因）
        #     上游右侧栏 resize 把手 pI_x6G_handle 是 absolute;top:0;bottom:0;width:8px;
        #     z-index:11;pointer-events:auto —— 右侧栏折叠后 rightbarCol 缩成 height:0，
        #     但把手**不跟着消失**，仍以 8px 宽、贯穿整个视口高度钉在固定 x（实测 276..284）。
        #     工具组是右对齐的（⋯ 中心 = 视口宽 - 134）⇒ 它只在 **410–417px** 这段视口里
        #     正好压住 ⋯ 的中心：「390px 测着全好、用户手机却点不动」就是这么来的。
        #     ⇒ 断言**必须扫一批宽度**，单宽度探针天然漏检；同时确认把手已不可命中
        #     （插件 0.2.7 起 display:none，另给工具组 position:relative;z-index:30 做第二道保险）。
        HITTEST = """() => {
          const h = document.querySelector('[class*=pI_x6G_handle]');
          const hs = h ? getComputedStyle(h) : null;
          return { handle: h ? { display: hs.display, pe: hs.pointerEvents } : null,
            buttons: [...document.querySelectorAll('#dsh-mobile-tab-tools button')].map(b => {
              const r = b.getBoundingClientRect();
              const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
              return { id: b.id, self: !!(t && (t === b || b.contains(t))),
                top: t ? (t.id || String(t.className || '').split(' ').filter(Boolean).pop() || t.tagName) : null }; }) }; }"""
        dead, covered, probe412 = [], [], None
        for vw in (320, 360, 375, 390, 400, 410, 412, 415, 418, 428, 460, 768):
            page.set_viewport_size({"width": vw, "height": h})
            page.wait_for_timeout(320)
            r = page.evaluate(HITTEST)
            if r["handle"] and r["handle"]["display"] != "none":
                dead.append(vw)
            miss = [f"{x['id']}←{x['top']}" for x in r["buttons"] if not x["self"]]
            if miss:
                covered.append(f"{vw}px:{','.join(miss)}")
            if vw == 412:                       # 用户实测踩中的那一段宽度，做端到端点击验证
                c412 = page.evaluate("""() => { const b = document.getElementById('dsh-mobile-more-proxy');
                  if (!b) return null; const r = b.getBoundingClientRect();
                  return [r.x + r.width / 2, r.y + r.height / 2]; }""")
                seq2 = []
                if c412:
                    for _ in range(2):
                        page.touchscreen.tap(c412[0], c412[1])
                        page.wait_for_timeout(900)
                        seq2.append(page.evaluate(menus_js))
                    if seq2[1]:                 # 别把菜单留着干扰后续断言
                        page.touchscreen.tap(c412[0], c412[1])
                        page.wait_for_timeout(700)
                probe412 = seq2
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(500)
        print(f"  [宽度扫描 12 档] 把手残留={dead or '无'} 按钮被覆盖={covered or '无'} 412px ⋯开合={probe412}（期望 [1,0]）")
        if dead:
            fails.append(f"右侧栏拖拽把手又在这些宽度残留成隐形死区：{dead}px"
                         f"（pI_x6G_handle 覆盖整列 ⇒ 该列 tap 全被吃掉）")
        if covered:
            fails.append(f"tabs 行工具按钮被别的层盖住（点不到）：{covered}")
        if probe412 is not None and probe412 != [1, 0]:
            fails.append(f"412px（用户手机宽度）下 ⋯ 按钮仍不能开合：{probe412}")
        # ④ 需切换器（没有子代理的会话跑不了）
        if not geom.get("err") and sw:
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
        # ⚠️ 抽屉开着时会盖一层 #dsh-mobile-scrim 罩住 ☰，此时点 ☰ 实际落在 scrim 上
        #   = **关**抽屉 ⇒ 必须先归零再断言（否则报"抽屉打不开"是假阳性）。
        pre = ensure_closed(page)
        used, drawer_open = open_drawer_confirmed(page)
        close_drawer(page, w)
        page.wait_for_timeout(1000)
        drawer_closed = page.evaluate(DRAWER)
        print(f"抽屉：前置={pre} 开={drawer_open} 关={drawer_closed}（入口 {used}）")
        if used is None:
            fails.append("抽屉入口按钮不可点（#dsh-mobile-tab-menu / #dsh-mobile-menu-btn 都没有）")
        elif drawer_open.startswith("none"):
            fails.append(f"抽屉打不开（开={drawer_open}，入口 {used}）")
        elif not drawer_closed.startswith("none"):
            fails.append(f"抽屉关不上（关={drawer_closed}）")

        browser.close()

    print()
    if skips:
        print(f"⚠️ {len(skips)} 项未覆盖（**不算回归**；要覆盖请用 --session 指定含子代理的会话）：")
        for x in skips:
            print(f"   - {x}")
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
