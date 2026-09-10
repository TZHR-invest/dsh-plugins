#!/usr/bin/env python3
"""dsh-mobile-ui 移动端布局探针：提问卡片（ask_user_question）可读性回归测试。

## 为什么需要这个探针

提问卡片曾在手机上出现「选项看不全 + 手指滑动也没反应」的故障（2026-09-11 定位修复）。
根因不是样式不生效，而是**覆盖了上游唯一的滚动容器**：

    上游 .card  { max-height: min(60vh,520px); overflow: hidden }
    上游 .body  { overflow-y: auto }          ← 卡片内唯一的滚动容器
    旧插件规则  .body { overflow: visible }    ← 把滚动容器废掉
    ⇒ ① 超出卡片的选项被 card 的 overflow:hidden 直接裁掉
      ② body 不再是滚动容器，③ 覆盖层里也没有可滚内容
      ⇒ 手指滑动零反应，后面的选项永久不可见

这类故障**静默且只在内容溢出时出现**（1~3 个选项时一切正常），靠肉眼审查 CSS 极难发现，
所以固化成几何测量：在真实上游 CSS + 真实 DOM 嵌套 + 真实插件代码下，
用 Playwright 断言「正文可滚 / 滚到底末项可见 / 真实触摸滑动后末项可见 / 提交按钮始终可见」。

## 用法

    python3 tests/mobile-layout-probe.py                 # 默认测当前安装副本
    python3 tests/mobile-layout-probe.py --plugin ./client.js
    python3 tests/mobile-layout-probe.py --viewport 320x568 --options 12

依赖：playwright（python）+ 已安装的 dsh（用于抽取上游 CSS）。退出码非 0 表示回归。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile

DSH_NODE_MODULES = pathlib.Path(
    os.environ.get(
        "DSH_NODE_MODULES",
        "/home/wbaifan/.npm-global/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai",
    )
)
DEFAULT_PLUGIN = pathlib.Path.home() / ".dsh/plugins/dsh-mobile-ui/client.js"

CONV_CSS_RE = r'const css\$4 = ("(?:[^"\\]|\\.)*");'
QQ_CSS_RE = r'const css = ("(?:[^"\\]|\\.)*");'


def extract_css(path: pathlib.Path, pattern: str, what: str) -> str:
    """从已安装的 dsh 客户端包里抽出上游 CSS（保证复现页与线上像素级同源）。"""
    if not path.exists():
        raise SystemExit(f"找不到 {path}（用 DSH_NODE_MODULES 指定 dsh 安装位置）")
    m = re.search(pattern, path.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"未能从 {path} 抽取 {what} 的 CSS（上游结构可能已变化）")
    return eval(m.group(1))


def build_page(plugin: pathlib.Path, options: int, detail_paras: int) -> str:
    conv_css = extract_css(DSH_NODE_MODULES / "dsh-client-ui-conversation/lib/client.js", CONV_CSS_RE, "ConversationRoot")
    qq_css = extract_css(DSH_NODE_MODULES / "dsh-client-ui-user-questions/lib/client.js", QQ_CSS_RE, "QuestionComposer")

    detail = "".join(
        f"<p>背景说明段落 {i + 1}：用于模拟真实场景中 detail 字段的长文本，"
        f"它会明显占据垂直空间。</p>"
        for i in range(detail_paras)
    )
    opts = "".join(
        f"""
        <button type="button" class="Mbwy4a_option" role="radio" aria-checked="false" aria-label="选项 {i + 1}">
          <span class="Mbwy4a_number">{i + 1}</span>
          <span class="Mbwy4a_optionCopy"><span class="Mbwy4a_optionLine">
            <span class="Mbwy4a_optionLabel">选项 {i + 1}：第 {i + 1} 个候选方案的简短标题</span>
            <span class="Mbwy4a_description">— 该方案的补充说明，用于占位真实文本长度。</span>
          </span></span>
        </button>"""
        for i in range(options)
    )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>mobile-layout-probe</title>
<style>
:root{{
  --dsw-alias-bg-base:#16171b; --dsw-alias-bg-layer-1:#1e1f24; --dsw-specific-input-major:#26272d;
  --dsw-alias-label-primary:rgba(255,255,255,.9); --dsw-alias-border-l2:rgba(255,255,255,.14);
  --dsw-alias-scrollbar-bg-l2:rgba(255,255,255,.2); --dsw-alias-scrollbar-hover-l2:rgba(255,255,255,.3);
  --dsh-composer-side-clearance:12px; --dsh-composer-card-max-width:720px;
  --dsh-chat-user-width:clamp(680px, 60vw, 860px); --dsh-scrollbar-width:0px;
  --dsh-conversation-column-width:100%;
}}
html,body{{margin:0;padding:0;height:100%;background:var(--dsw-alias-bg-base);color:#eee;
  font-family:-apple-system,"PingFang SC",system-ui,sans-serif}}
{conv_css}
{qq_css}
#app{{height:100%;display:grid;grid-template-columns:260px minmax(0,1fr) 0px}}
.sidebarCol{{background:#1a1b1f;border-right:1px solid rgba(255,255,255,.08)}}
.detailsCol{{background:#1a1b1f}}
.msg{{padding:10px 14px;margin:8px 12px;border-radius:12px;background:#22232a;line-height:1.5}}
</style></head>
<body>
<div id="app">
  <div class="sidebarCol" data-testid="sidebar">sidebar</div>
  <div class="wSkVaW_root" data-phase="active">
    <div class="wSkVaW_header" style="padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.08)">会话标题</div>
    <div class="wSkVaW_body">
      <div class="wSkVaW_scrollBody" data-conversation-scroll>
        <div data-slot="conversation.session"><div class="wSkVaW_viewArea">
          <div class="msg">用户：帮我看下这个方案。</div>
          <div class="msg">助手：好的，我需要你确认几个问题。</div>
        </div></div>
        <div class="wSkVaW_composerSeat" data-composer-seat>
          <div class="Mbwy4a_frame" data-question-key="probe">
            <section class="Mbwy4a_card" aria-labelledby="q1">
              <header class="Mbwy4a_header">
                <div class="Mbwy4a_headingBlock">
                  <div class="Mbwy4a_eyebrow">需要你的确认</div>
                  <h2 class="Mbwy4a_title" id="q1">这个任务应该按哪种方式继续？请在下面选择一项。</h2>
                </div>
                <div class="Mbwy4a_headerActions">
                  <button type="button" class="Mbwy4a_iconButton" aria-label="最小化">⌄</button>
                  <button type="button" class="Mbwy4a_iconButton" aria-label="取消">✕</button>
                </div>
              </header>
              <div class="Mbwy4a_body" data-question-scroll>
                <div class="Mbwy4a_detail">{detail}</div>
                <div class="Mbwy4a_options" role="radiogroup">{opts}
                  <div class="Mbwy4a_customRow">
                    <span class="Mbwy4a_number" aria-hidden="true">+</span>
                    <input class="Mbwy4a_fieldInput" placeholder="其他（自定义回答）">
                  </div>
                </div>
              </div>
              <div class="Mbwy4a_footer">
                <div class="Mbwy4a_footerActions"><button class="Mbwy4a_iconButton">跳过</button></div>
                <div class="Mbwy4a_footerActions">
                  <span class="Mbwy4a_progress">1/1</span>
                  <button class="Mbwy4a_primary">提交</button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="detailsCol" data-testid="details">details</div>
</div>
<script>window.__ModuleLoader__={{mode:"queue",load:function(reg){{window.__reg=reg}}}};</script>
<script src="file://{plugin}"></script>
<script>window.__reg.factory(function(){{throw new Error("no require")}});window.__reg.factory;window.__plug=window.__reg;window.__plug.factory(function(){{}});</script>
<script>try{{window.__plug.factory(function(){{}});}}catch(e){{}}</script>
</body></html>"""


MEASURE_JS = r"""
() => {
  const q = (s) => document.querySelector(s);
  const seat = q('[data-composer-seat]');
  const body = q('[data-question-scroll]');
  const opts = [...document.querySelectorAll('button[class*=Mbwy4a_option]')];
  const vis = (el) => {
    if (!el) return {ok:false, why:'missing'};
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return {ok:false, why:'zero-size'};
    const cx = r.left + r.width/2, cy = r.top + r.height/2;
    if (cy < 0 || cy > innerHeight) return {ok:false, why:'offscreen'};
    const hit = document.elementFromPoint(cx, cy);
    return {ok: !!hit && (hit === el || el.contains(hit) || hit.contains(el)), why: hit ? String(hit.className||hit.tagName) : 'null'};
  };
  return {
    vp: {w: innerWidth, h: innerHeight},
    seatQa: !!(seat && /dsh-mobile-qa/.test(seat.className)),
    bodyOverflow: body ? getComputedStyle(body).overflowY : null,
    bodyScroll: body ? body.scrollHeight - body.clientHeight : 0,
    last: vis(opts[opts.length-1]),
    submit: vis(q('[class*=Mbwy4a_primary]')),
  };
}
"""


def apply_plugin(page, plugin: pathlib.Path) -> None:
    """在页面里按真实加载路径执行插件：注册 → factory → apply(ctx)。"""
    page.add_script_tag(path=str(plugin))
    page.evaluate(
        """() => {
          const reg = window.__reg;
          window.__plug = reg.factory(function () { throw new Error('no require'); });
          window.__plug.apply({ logger: { info() {} } });
        }"""
    )


def probe(plugin, viewport, options, detail_paras, workdir):
    from playwright.sync_api import sync_playwright

    w, h = viewport
    html = build_page(plugin, options, detail_paras)
    page_path = workdir / f"probe-{options}-{w}x{h}.html"
    page_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=True, has_touch=True
        )
        page = ctx.new_page()
        page.goto(page_path.as_uri())
        apply_plugin(page, plugin)
        page.wait_for_timeout(500)

        before = page.evaluate(MEASURE_JS)

        # 真实手指滑动（touch 事件；滚轮不等价：移动端页面常只响应 touch）
        body = page.query_selector("[data-question-scroll]")
        box = body.bounding_box()
        if box:
            cx, y0, y1 = box["x"] + box["width"] / 2, box["y"] + box["height"] - 24, box["y"] + 24
            cdp = ctx.new_cdp_session(page)
            for _ in range(2):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": cx, "y": y0}]})
                for i in range(1, 11):
                    cdp.send("Input.dispatchTouchEvent", {
                        "type": "touchMove", "touchPoints": [{"x": cx, "y": y0 + (y1 - y0) * i / 10}]})
                    page.wait_for_timeout(16)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                page.wait_for_timeout(200)
        after_swipe = page.evaluate(MEASURE_JS)
        browser.close()

    return {
        "viewport": f"{w}x{h}",
        "options": options,
        "detail_paras": detail_paras,
        "scrollable": (before["bodyScroll"] or 0) > 1 and before["bodyOverflow"] in ("auto", "scroll"),
        "needs_scroll": (before["bodyScroll"] or 0) > 1,
        "last_visible_after_swipe": after_swipe["last"]["ok"],
        "submit_visible": before["submit"]["ok"],
        "seat_qa": before["seatQa"],
        "detail": {"before": before, "after_swipe": after_swipe},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="dsh-mobile-ui 提问卡片移动端布局探针")
    ap.add_argument("--plugin", default=str(DEFAULT_PLUGIN), help="被测 client.js 路径")
    ap.add_argument("--viewport", action="append", default=None, help="WxH，可重复（默认覆盖常见机型）")
    ap.add_argument("--options", type=int, action="append", default=None, help="选项数量，可重复")
    ap.add_argument("--detail-paras", type=int, default=2, help="detail 长文本段落数")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    plugin = pathlib.Path(args.plugin).expanduser()
    if not plugin.exists():
        raise SystemExit(f"被测插件不存在：{plugin}")

    viewports = [tuple(int(x) for x in v.lower().split("x")) for v in (args.viewport or ["320x568", "360x640", "390x844", "414x896"])]
    options_list = args.options or [1, 3, 6, 12]

    results = []
    with tempfile.TemporaryDirectory(prefix="dsh-mobile-probe-") as tmp:
        for vp in viewports:
            for n in options_list:
                results.append(probe(plugin, vp, n, args.detail_paras, pathlib.Path(tmp)))

    failures = [
        r for r in results
        if not r["last_visible_after_swipe"] or not r["submit_visible"] or (r["needs_scroll"] and not r["scrollable"])
    ]

    if args.json:
        # 纯 JSON 输出（供 CI/脚本消费）；结论用退出码表达
        print(json.dumps({"ok": not failures, "results": results}, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    else:
        print(f"被测插件: {plugin}")
        print(f"{'视口':<10} {'选项数':<7} {'内容溢出':<9} {'正文可滚':<9} {'滑动后末项可见':<15} {'提交可见':<9}")
        print("-" * 66)
        for r in results:
            print(f"{r['viewport']:<10} {r['options']:<8} {'是' if r['needs_scroll'] else '否':<10} "
                  f"{'✓' if r['scrollable'] else ('—' if not r['needs_scroll'] else '✗'):<10} "
                  f"{'✓' if r['last_visible_after_swipe'] else '✗':<16} {'✓' if r['submit_visible'] else '✗':<10}")

    print()
    if failures:
        print(f"❌ 回归：{len(failures)} 个用例不达标（选项被裁 / 滚动失效 / 提交按钮不可见）")
        for r in failures:
            print(f"   - {r['viewport']} options={r['options']}: {r['detail']['before']}")
        return 1
    print(f"✅ 全部 {len(results)} 个用例通过：选项可滚可见、提交按钮始终可见")
    return 0


if __name__ == "__main__":
    sys.exit(main())
