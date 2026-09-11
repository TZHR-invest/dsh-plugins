#!/usr/bin/env python3
"""dsh-mobile-ui 移动端布局探针：两处可读性/几何回归测试。

## 一、提问卡片（ask_user_question）

提问卡片曾在手机上出现「选项看不全 + 手指滑动也没反应」的故障（2026-09-11 定位修复）。
根因不是样式不生效，而是**覆盖了上游唯一的滚动容器**：

    上游 .card  { max-height: min(60vh,520px); overflow: hidden }
    上游 .body  { overflow-y: auto }          ← 卡片内唯一的滚动容器
    旧插件规则  .body { overflow: visible }    ← 把滚动容器废掉
    ⇒ ① 超出卡片的选项被 card 的 overflow:hidden 直接裁掉
      ② body 不再是滚动容器，③ 覆盖层里也没有可滚内容
      ⇒ 手指滑动零反应，后面的选项永久不可见

## 二、输入区操作行（composer row）

操作行曾出现「模型选择器压住上下文环 / 访问模式按钮压住模型选择器」（2026-09-11 定位修复）。
根因是**两条插件规则互相配合出的溢出**：

    旧插件规则  [class*=uV2eYG_row]{flex-wrap:nowrap}          ← 禁止换行
    旧插件规则  [class*=uV2eYG_row] > *{flex:0 1 auto}          ← 组可收缩
    上游组内按钮 min-width:44px                                 ← 但按钮不可压缩
    ⇒ 行宽不足时 flex 无法通过收缩解决，又禁止换行 ⇒ 各控件**溢出重叠**
      （实测 390px 会话页：访问模式↔模型重叠 5.7px、模型↔上下文重叠 4.3px）

这类故障同样**静默且只在特定宽度/控件数下出现**（hero 页 4 控件正常、会话页
多一个上下文按钮就重叠），肉眼审查 CSS 极难穷举，所以固化成几何测量：
真实上游 CSS + 真实 DOM 嵌套 + 真实插件代码，断言「任意两个控件都不重叠」。

## 用法

    python3 tests/mobile-layout-probe.py                 # 默认测当前安装副本
    python3 tests/mobile-layout-probe.py --plugin ./client.js
    python3 tests/mobile-layout-probe.py --viewport 320x568 --options 12
    python3 tests/mobile-layout-probe.py --only composer  # 只跑操作行
    python3 tests/mobile-layout-probe.py --only qa        # 只跑提问卡片

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
# 输入区（InputBar）上游 CSS：uV2eYG 词根
INPUTBAR_CSS_RE = r'const css\$1 = ("(?:[^"\\]|\\.)*");'


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
/* 顶层容器必须带 frame 词根：插件靠 [class*=frame] 找主布局（真实 dsh 同构） */
#app{{height:100%;display:grid;grid-template-columns:260px minmax(0,1fr) 0px}}
.sidebarCol{{background:#1a1b1f;border-right:1px solid rgba(255,255,255,.08)}}
.detailsCol{{background:#1a1b1f}}
.msg{{padding:10px 14px;margin:8px 12px;border-radius:12px;background:#22232a;line-height:1.5}}
</style></head>
<body>
<div id="app" class="frame">
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
    // 右上角菜单按钮在提问卡片打开时必须隐藏，否则会浮在卡片右上角遮住问题标题
    menuBtnDisplay: (() => { const m = document.getElementById('dsh-mobile-menu-btn'); return m ? getComputedStyle(m).display : null; })(),
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


def build_composer_page(plugin: pathlib.Path, with_context: bool, with_effort: bool,
                       model_label: str = "commandcode/deepseek/deepseek-v4.1-flash") -> str:
    """复现页：真实上游 InputBar CSS + 真实 DOM 嵌套（composerSeat > stack > root > card > row > tools/trailing）。

    with_context: 会话页有「上下文已用」按钮（hero 页没有）——正是多这一个控件才触发重叠。
    with_effort:  模型名带推理等级后缀（triggerEffort），会额外占宽。
    model_label:  模型显示名。默认用超长 provider/model（最坏情况，考验省略号）；
                  短名（目录内模型的友好名）用于对照正常观感。
    """
    conv_css = extract_css(DSH_NODE_MODULES / "dsh-client-ui-conversation/lib/client.js", CONV_CSS_RE, "ConversationRoot")
    input_css = extract_css(
        DSH_NODE_MODULES / "dsh-client-ui-conversation/lib/client.js", INPUTBAR_CSS_RE, "InputBar")

    effort = '<span class="_7KE1Ra_triggerEffort">Max</span>' if with_effort else ""
    ctx_btn = (
        '<span class="JObwrW_root"><button type="button" class="JObwrW_trigger" '
        'aria-label="上下文已用 18%" aria-haspopup="dialog"><svg viewBox="0 0 14 14" width="14" height="14">'
        '<circle class="JObwrW_track" cx="7" cy="7" r="5"></circle>'
        '<circle class="JObwrW_fill" cx="7" cy="7" r="5" stroke-dasharray="5.6 31.4" '
        'transform="rotate(-90 7 7)"></circle></svg></button></span>'
        if with_context else ""
    )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>composer-row-probe</title>
<style>
:root{{
  --dsw-alias-bg-base:#16171b; --dsw-alias-bg-layer-1:#1e1f24; --dsw-specific-input-major:#26272d;
  --dsw-specific-menu:#2a2b31; --dsw-specific-selector:#33343a;
  --dsw-alias-label-primary:rgba(255,255,255,.9); --dsw-alias-label-secondary:rgba(255,255,255,.7);
  --dsw-alias-label-tertiary:rgba(255,255,255,.5); --dsw-alias-label-caption:rgba(255,255,255,.4);
  --dsw-alias-border-l2:rgba(255,255,255,.14); --dsw-alias-border-l3:rgba(255,255,255,.2);
  --dsw-alias-interactive-bg-hover:rgba(255,255,255,.08);
  --dsh-composer-side-clearance:12px; --dsh-composer-card-max-width:720px;
  --dsh-composer-text-max-height:200px; --dsh-content-font-size:14px;
  --dsh-conversation-column-width:100%;
}}
html,body{{margin:0;padding:0;height:100%;background:var(--dsw-alias-bg-base);color:#eee;
  font-family:-apple-system,"PingFang SC",system-ui,sans-serif}}
{conv_css}
{input_css}
#app{{height:100%;display:grid;grid-template-columns:260px minmax(0,1fr) 0px}}
.sidebarCol{{background:#1a1b1f}} .detailsCol{{background:#1a1b1f}}
</style></head>
<body>
<div id="app" class="frame">
  <div class="sidebarCol" data-testid="sidebar">sidebar</div>
  <div class="wSkVaW_root" data-phase="active">
    <div class="wSkVaW_header" style="padding:8px 12px">会话标题</div>
    <div class="wSkVaW_body">
      <div class="wSkVaW_scrollBody" data-conversation-scroll>
        <div data-slot="conversation.session"><div class="wSkVaW_viewArea">&nbsp;</div></div>
        <div class="wSkVaW_composerSeat" data-composer-seat>
          <div class="wSkVaW_composerStack">
            <div class="uV2eYG_root">
              <div class="uV2eYG_card">
                <div class="uV2eYG_scroll"><div class="uV2eYG_grow">
                  <div class="uV2eYG_input" contenteditable="true" aria-label="发消息"></div>
                </div></div>
                <div class="uV2eYG_row">
                  <div class="uV2eYG_tools">
                    <button type="button" class="uV2eYG_add" aria-label="指令">
                      <svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 3v10M3 8h10" stroke="currentColor" fill="none"/></svg></button>
                    <button type="button" class="uV2eYG_add" aria-label="添加附件">
                      <svg viewBox="0 0 16 16" width="14" height="14"><path d="M5 8h6" stroke="currentColor" fill="none"/></svg></button>
                    <div class="uV2eYG_modes">
                      <button type="button" class="Sh0Q9G_trigger" aria-label="访问模式，当前：完全权限"
                        ><span class="Sh0Q9G_triggerIcon"><svg viewBox="0 0 16 16" width="14" height="14"><path d="M8 1l6 3v4c0 4-3 6-6 7-3-1-6-3-6-7V4z" fill="none" stroke="currentColor"/></svg></span><span class="Sh0Q9G_triggerLabel">完全权限</span></button>
                    </div>
                  </div>
                  <div class="uV2eYG_trailing">
                    <div class="_7KE1Ra_root">
                      <button type="button" class="_7KE1Ra_trigger" aria-label="选择模型，当前 {model_label}" aria-haspopup="menu">
                        <svg class="_7KE1Ra_triggerIcon" viewBox="0 0 16 16" width="16" height="16"><path d="M2 8h12" stroke="currentColor" fill="none"/></svg>
                        <span class="_7KE1Ra_triggerLabel">{model_label}</span>
                        {effort}
                        <svg class="_7KE1Ra_chevron" viewBox="0 0 14 14" width="14" height="14"><path d="M4 6l3 3 3-3" stroke="currentColor" fill="none"/></svg>
                      </button>
                    </div>
                    {ctx_btn}
                    <button type="button" class="uV2eYG_primary" aria-label="发送消息">
                      <svg viewBox="0 0 16 16" width="16" height="16"><path d="M8 13V3M4 7l4-4 4 4" stroke="currentColor" fill="none"/></svg></button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="detailsCol" data-testid="details">details</div>
</div>
<script>window.__ModuleLoader__={{mode:"queue",load:function(reg){{window.__reg=reg}}}};</script>
<script src="file://{plugin}"></script>
<script>window.__plug=window.__reg;window.__plug.factory(function(){{}});</script>
</body></html>"""


COMPOSER_MEASURE_JS = r"""
() => {
  const row = document.querySelector('[class*=uV2eYG_row]');
  if (!row) return {err: 'no composer row'};
  const btns = [...row.querySelectorAll('button')].map(b => {
    const r = b.getBoundingClientRect();
    return {aria: (b.getAttribute('aria-label')||'').slice(0, 24),
            x: +r.x.toFixed(1), y: +r.y.toFixed(1), right: +r.right.toFixed(1),
            bottom: +r.bottom.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1)};
  });
  // 任意两个控件重叠 = 回归（正是 2026-09-11 的故障形态）
  const overlaps = [];
  for (let i = 0; i < btns.length; i++) for (let j = i + 1; j < btns.length; j++) {
    const a = btns[i], b = btns[j];
    const ox = Math.min(a.right, b.right) - Math.max(a.x, b.x);
    const oy = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y);
    if (ox > 0.5 && oy > 0.5) overlaps.push({a: a.aria, b: b.aria, ox: +ox.toFixed(1)});
  }
  const card = document.querySelector('[class*=uV2eYG_card]');
  const cardRight = card ? +card.getBoundingClientRect().right.toFixed(1) : null;
  // 控件越出输入卡右边界 = 溢出（窄屏下被裁掉，点不到）
  const spill = cardRight === null ? [] : btns
      .filter(b => b.right > cardRight + 0.5)
      .map(b => ({aria: b.aria, over: +(b.right - cardRight).toFixed(1)}));
  const rowBox = row.getBoundingClientRect();

  // ── 子元素可见性断言（2026-09-11 两个静默故障的守卫）──
  const shown = (sel) => { const el = document.querySelector(sel);
    return el ? getComputedStyle(el).display !== 'none' : null; };
  const accessIconShown = shown('button[aria-label*=访问模式] [class*=triggerIcon]');
  // 权限文字只在行够宽时出现；出现时必须真的可见（不能是 0 宽空壳）
  const accessLabelEl = document.querySelector('button[aria-label*=访问模式] [class*=triggerLabel]');
  const accessLabelShown = accessLabelEl ? getComputedStyle(accessLabelEl).display !== 'none' : false;
  const accessLabelW = accessLabelEl && accessLabelShown
      ? +accessLabelEl.getBoundingClientRect().width.toFixed(1) : 0;
  // 推理等级后缀移动端必须隐藏（否则被压成 8px 宽的半截字符）
  const effortShown = shown('button[aria-label*=选择模型] [class*=triggerEffort]');

  // 省略号是否真的生效：被裁的 label 必须 overflow:hidden + text-overflow:ellipsis
  // （flex 容器会忽略 text-overflow → 硬切出半个字符，正是用户看到的"半截字母"）
  const label = document.querySelector('button[aria-label*=选择模型] [class*=_7KE1Ra_triggerLabel]');
  let ellipsisOk = true, modelLabelClipped = false, modelLabelW = null;
  if (label) {
    const lcs = getComputedStyle(label);
    const shown = lcs.display !== 'none';
    modelLabelW = shown ? +label.getBoundingClientRect().width.toFixed(1) : 0;
    modelLabelClipped = label.scrollWidth > label.clientWidth + 1;
    if (modelLabelClipped) {
      ellipsisOk = lcs.overflow === 'hidden' && lcs.textOverflow === 'ellipsis'
                   && lcs.display !== 'flex';
    }
  }

  // ── 视觉一致性（2026-09-11 用户反馈"高度不一致、怪怪的"的守卫）──
  // 同一操作行内所有按钮必须等高、同字号，且行内垂直中心离散 ≤1.5px
  const heights = [...new Set(btns.map(b => Math.round(b.h)))];
  const fonts = [...new Set([...row.querySelectorAll('button')]
      .map(b => getComputedStyle(b).fontSize))];
  // 按 top 分簇（不能用中心 y：控件 44px 高、两行中心仅差 50px，
  // 阈值稍大就会把两行并成一簇。等高后同行 top 必然相同，故对 top 聚类最稳）
  const tops = btns.map(b => b.y).sort((a, b) => a - b);
  const clusters = [];
  for (const ty of tops) {
    if (!clusters.length || ty - clusters[clusters.length - 1][0] > 6) clusters.push([ty]);
    else clusters[clusters.length - 1].push(ty);
  }
  const lineSpreads = clusters.map(c => +(Math.max(...c) - Math.min(...c)).toFixed(1));

  // 垂直对齐：label / chevron / 图标中心相对按钮中心的偏差 ≤1.5px
  const cy = (el) => { const b = el.getBoundingClientRect(); return b.y + b.height / 2; };
  const misaligned = [];
  for (const [name, btnSel, innerSel] of [
      ['模型名', 'button[aria-label*=选择模型]', '[class*=_7KE1Ra_triggerLabel]'],
      ['模型箭头', 'button[aria-label*=选择模型]', '[class*=_7KE1Ra_chevron]'],
      ['权限图标', 'button[aria-label*=访问模式]', '[class*=triggerIcon]']]) {
    const btn = document.querySelector(btnSel), el = document.querySelector(innerSel);
    if (!btn || !el || getComputedStyle(el).display === 'none') continue;
    const dev = Math.abs(cy(el) - cy(btn));
    if (dev > 1.5) misaligned.push({name, dev: +dev.toFixed(1)});
  }

  return {
    rowH: +rowBox.height.toFixed(1), rowW: +rowBox.width.toFixed(1),
    count: btns.length,
    minW: btns.length ? Math.min(...btns.map(b => b.w)) : 0,
    overlaps, spill,
    accessIconShown, accessLabelShown, accessLabelW, effortShown,
    modelLabelClipped, ellipsisOk, misaligned, modelLabelW,
    heights, fonts, lineSpreads,
    // 控件是否都可点（中心点命中自己）
    unclickable: btns.filter(b => {
      const cx = b.x + b.w / 2, cy2 = b.y + b.h / 2;
      const hit = document.elementFromPoint(cx, cy2);
      const el = [...row.querySelectorAll('button')].find(x => {
        const r = x.getBoundingClientRect();
        return Math.abs(r.x - b.x) < .5 && Math.abs(r.width - b.w) < .5; });
      return !hit || !el || !(hit === el || el.contains(hit) || hit.contains(el));
    }).map(b => b.aria),
  };
}
"""


def probe_composer(plugin, viewport, with_context, with_effort, workdir,
                   model_label="commandcode/deepseek/deepseek-v4.1-flash"):
    """操作行几何探针：断言控件互不重叠、不越界、可点击，且关键子元素该显示的都在。"""
    from playwright.sync_api import sync_playwright

    w, h = viewport
    html = build_composer_page(plugin, with_context, with_effort, model_label)
    tag = (f"composer-{'sess' if with_context else 'hero'}-{'eff' if with_effort else 'noeff'}"
           f"-{'long' if len(model_label) > 20 else 'short'}-{w}x{h}")
    page_path = workdir / f"{tag}.html"
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
        m = page.evaluate(COMPOSER_MEASURE_JS)
        browser.close()

    return {
        "viewport": f"{w}x{h}",
        "variant": ("会话页(含上下文)" if with_context else "首页(hero)")
                   + ("/长模型名" if len(model_label) > 20 else "/短模型名"),
        "effort": with_effort,
        **m,
    }


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

        # 真实手指滑动（touch 事件；滚轮不等价：移动端页面常只响应 touch）。
        # 反复滑动直到末项可见（模拟用户持续上滑），最多 8 次；
        # 滚不动的情况下滑多少次都不会可见 —— 因此不会掩盖真问题。
        body = page.query_selector("[data-question-scroll]")
        box = body.bounding_box()
        swipes = 0
        after_swipe = before
        if box:
            cx, y0, y1 = box["x"] + box["width"] / 2, box["y"] + box["height"] - 24, box["y"] + 24
            cdp = ctx.new_cdp_session(page)
            while swipes < 8:
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": cx, "y": y0}]})
                for i in range(1, 11):
                    cdp.send("Input.dispatchTouchEvent", {
                        "type": "touchMove", "touchPoints": [{"x": cx, "y": y0 + (y1 - y0) * i / 10}]})
                    page.wait_for_timeout(16)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                page.wait_for_timeout(200)
                swipes += 1
                after_swipe = page.evaluate(MEASURE_JS)
                if after_swipe["last"]["ok"]:
                    break
        browser.close()

    return {
        "viewport": f"{w}x{h}",
        "options": options,
        "detail_paras": detail_paras,
        "scrollable": (before["bodyScroll"] or 0) > 1 and before["bodyOverflow"] in ("auto", "scroll"),
        "needs_scroll": (before["bodyScroll"] or 0) > 1,
        "last_visible_after_swipe": after_swipe["last"]["ok"],
        "submit_visible": before["submit"]["ok"],
        "menu_btn_hidden_while_qa": before["menuBtnDisplay"] == "none",
        "swipes_to_reach_last": swipes,
        "seat_qa": before["seatQa"],
        "detail": {"before": before, "after_swipe": after_swipe},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="dsh-mobile-ui 移动端布局探针（提问卡片 + 输入区操作行）")
    ap.add_argument("--plugin", default=str(DEFAULT_PLUGIN), help="被测 client.js 路径")
    ap.add_argument("--viewport", action="append", default=None, help="WxH，可重复（默认覆盖常见机型）")
    ap.add_argument("--options", type=int, action="append", default=None, help="选项数量，可重复")
    ap.add_argument("--detail-paras", type=int, default=2, help="detail 长文本段落数")
    ap.add_argument("--only", choices=["qa", "composer"], default=None, help="只跑其中一组")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    plugin = pathlib.Path(args.plugin).expanduser()
    if not plugin.exists():
        raise SystemExit(f"被测插件不存在：{plugin}")

    viewports = [tuple(int(x) for x in v.lower().split("x")) for v in (args.viewport or ["320x568", "360x640", "390x844", "414x896"])]
    options_list = args.options or [1, 3, 6, 12]

    qa_results, composer_results = [], []
    with tempfile.TemporaryDirectory(prefix="dsh-mobile-probe-") as tmp:
        wd = pathlib.Path(tmp)
        if args.only in (None, "qa"):
            for vp in viewports:
                for n in options_list:
                    qa_results.append(probe(plugin, vp, n, args.detail_paras, wd))
        if args.only in (None, "composer"):
            # 会话页（含上下文按钮）+ 首页 hero；模型名分超长(provider/model 兜底)与短名两种，
            # 都要过：带推理等级后缀更宽，长名考验省略号。
            for vp in viewports:
                for with_ctx in (True, False):
                    composer_results.append(probe_composer(plugin, vp, with_ctx, True, wd))
            for vp in viewports[:2]:
                composer_results.append(probe_composer(
                    plugin, vp, True, True, wd, model_label="DeepSeek V4.1 Flash"))

    qa_failures = [
        r for r in qa_results
        if not r["last_visible_after_swipe"] or not r["submit_visible"]
        or not r["menu_btn_hidden_while_qa"] or (r["needs_scroll"] and not r["scrollable"])
    ]
    composer_failures = [
        r for r in composer_results
        if r.get("err") or r.get("overlaps") or r.get("spill") or r.get("unclickable")
        or r.get("count", 0) < 2
        # 权限图标必须常显（曾被 span 通配规则连图标一起隐藏 → 整个按钮空白）
        or not r.get("accessIconShown")
        # 权限文字必须常显且有真实宽度（两行布局后第一行独占，320px 也放得下；
        # 曾出现 span 通配规则把图标一起隐藏 → 按钮纯空白的故障）
        or not r.get("accessLabelShown") or (r.get("accessLabelW") or 0) < 20
        # 推理等级后缀必须隐藏（否则被压成半截字符）
        or r.get("effortShown")
        # 被裁的模型名必须走真省略号，不能硬切半个字符
        or (r.get("modelLabelClipped") and not r.get("ellipsisOk"))
        # 模型名必须够宽（两行布局后独占一行：320px 约 148px、390px 约 218px，
        # 而单行时代仅 40px → 只能看 7/40 字符）。下限取 120px 防退化成窄条，
        # 又不锁死具体像素（布局微调不该误报）。
        or 0 < (r.get("modelLabelW") or 0) < 120
        # 图标/文字/箭头必须垂直居中对齐
        or r.get("misaligned")
        # 控件必须等高、同字号（曾 36/40/44 三种高度混排 → 视觉"怪"）
        or len(r.get("heights") or [1]) != 1
        or len(r.get("fonts") or [1]) != 1
        # 行内垂直中心离散 ≤1.5px（发送键上游 translateY(-2px) 曾致偏移）
        or any(s > 1.5 for s in (r.get("lineSpreads") or [0]))
    ]

    if args.json:
        print(json.dumps({
            "ok": not qa_failures and not composer_failures,
            "qa": qa_results, "composer": composer_results,
        }, ensure_ascii=False, indent=2))
        return 1 if (qa_failures or composer_failures) else 0

    print(f"被测插件: {plugin}")

    if qa_results:
        print()
        print("── 提问卡片（ask_user_question）──")
        print(f"{'视口':<10} {'选项数':<7} {'内容溢出':<9} {'正文可滚':<9} {'滑动后末项可见':<15} {'提交可见':<9} {'菜单不遮挡':<10}")
        print("-" * 78)
        for r in qa_results:
            print(f"{r['viewport']:<10} {r['options']:<8} {'是' if r['needs_scroll'] else '否':<10} "
                  f"{'✓' if r['scrollable'] else ('—' if not r['needs_scroll'] else '✗'):<10} "
                  f"{'✓' if r['last_visible_after_swipe'] else '✗':<16} {'✓' if r['submit_visible'] else '✗':<10} "
                  f"{'✓' if r['menu_btn_hidden_while_qa'] else '✗':<10}")

    if composer_results:
        print()
        print("── 输入区操作行（composer row）──")
        print(f"{'视口':<10} {'形态':<24} {'控件':<5} {'重叠':<6} {'越界':<6} {'可点':<6} "
              f"{'权限图标':<9} {'权限文字':<9} {'省略号':<8} {'对齐':<6}")
        print("-" * 96)
        for r in composer_results:
            if r.get("err"):
                print(f"{r['viewport']:<10} {r['variant']:<24} ERR {r['err']}")
                continue
            ell = "—" if not r.get("modelLabelClipped") else ("✓" if r.get("ellipsisOk") else "✗")
            perm_txt = ("✓" if r.get("accessLabelShown") else "—")
            print(f"{r['viewport']:<10} {r['variant']:<24} {r['count']:<6} "
                  f"{'✓' if not r['overlaps'] else '✗':<7} {'✓' if not r['spill'] else '✗':<7} "
                  f"{'✓' if not r['unclickable'] else '✗':<7} "
                  f"{'✓' if r.get('accessIconShown') else '✗':<10} {perm_txt:<10} {ell:<9} "
                  f"{'✓' if not r.get('misaligned') else '✗':<6}")

    print()
    if qa_failures or composer_failures:
        if qa_failures:
            print(f"❌ 提问卡片回归：{len(qa_failures)} 个用例不达标（选项被裁 / 滚动失效 / 提交按钮不可见）")
            for r in qa_failures:
                print(f"   - {r['viewport']} options={r['options']}: {r['detail']['before']}")
        if composer_failures:
            print(f"❌ 操作行回归：{len(composer_failures)} 个用例不达标")
            for r in composer_failures:
                # 逐条列出真实原因，别只说"重叠/越界"（2026-09-11 曾因此误判）
                why = []
                if r.get("err"):
                    why.append(f"err={r['err']}")
                if r.get("overlaps"):
                    why.append(f"控件重叠={r['overlaps']}")
                if r.get("spill"):
                    why.append(f"越出卡片={r['spill']}")
                if r.get("unclickable"):
                    why.append(f"点不到={r['unclickable']}")
                if not r.get("accessIconShown"):
                    why.append("权限图标被隐藏(按钮会变空白)")
                if not r.get("accessLabelShown"):
                    why.append("权限文字未显示")
                elif (r.get("accessLabelW") or 0) < 20:
                    why.append(f"权限文字宽度异常={r.get('accessLabelW')}")
                if r.get("effortShown"):
                    why.append("推理等级后缀未隐藏(会被压成半截字符)")
                if r.get("modelLabelClipped") and not r.get("ellipsisOk"):
                    why.append("模型名被硬切而非省略号")
                mw = r.get("modelLabelW") or 0
                if 0 < mw < 120:
                    why.append(f"模型名被压得过窄({mw}px < 120px)")
                if r.get("misaligned"):
                    why.append(f"垂直未对齐={r['misaligned']}")
                if len(r.get("heights") or [1]) != 1:
                    why.append(f"控件高度不一致={r.get('heights')}")
                if len(r.get("fonts") or [1]) != 1:
                    why.append(f"字号不一致={r.get('fonts')}")
                if any(s > 1.5 for s in (r.get("lineSpreads") or [0])):
                    why.append(f"行内中心离散过大={r.get('lineSpreads')}")
                if r.get("count", 0) < 2:
                    why.append(f"控件数异常={r.get('count')}")
                print(f"   - {r['viewport']} {r.get('variant')}: " + "；".join(why or ["未知"]))
        return 1

    parts = []
    if qa_results:
        parts.append(f"提问卡片 {len(qa_results)} 个（选项可滚可见、提交始终可见、菜单不遮挡）")
    if composer_results:
        parts.append(f"操作行 {len(composer_results)} 个（互不重叠/不越界/可点击、"
                     f"权限图标常显、被裁模型名走省略号、图标文字垂直对齐）")
    print("✅ 全部通过：" + "；".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
