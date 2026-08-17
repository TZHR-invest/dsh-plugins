/**
 * dsh-mobile-ui — 浏览器端 bundle（classic script）。
 *
 * 移动端（≤768px 视口）体验增强，两层：
 *   1. CSS 层：响应式阅读/触摸/间距/安全区优化（桌面端完全不受影响）；
 *   2. JS 层：隐藏左侧图标栏释放全宽 + 底部导航栏（新建/会话/设置），
 *      会话列表以抽屉（drawer）形式展开。
 *
 * 防崩纪律（MR-022/023）：
 *   - 本 bundle 无顶层 import/export，由 dsh web 按 classic script 加载；
 *   - 全部 DOM 操作 try/catch，任何失败静默降级（CSS 层仍生效）；
 *   - 选择器优先 aria-label，其次词根类名前缀匹配（[class*=xxx]），
 *     降低 dsh 升级后 hash 类名漂移导致的失效风险。
 */
window.__ModuleLoader__.load({
	id: "dsh-mobile-ui",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

		/* ═══════════════════ CSS 层 ═══════════════════ */
		var MOBILE_CSS = [
			"/* dsh-mobile-ui 移动端增强（≤768px 生效，桌面不受影响） */",
			/* 右上角菜单按钮（入口：打开会话抽屉——抽屉内含新建/会话列表/设置） */
			"#dsh-mobile-menu-btn{position:fixed;top:calc(48px + env(safe-area-inset-top,0px));right:12px;z-index:2147483000;display:none;width:42px;height:42px;border-radius:50%;background:var(--dsw-alias-bg-layer-1,rgba(22,23,27,.94));border:1px solid var(--dsw-alias-border-l2,rgba(255,255,255,.14));color:var(--dsw-alias-label-primary,rgba(255,255,255,.88));align-items:center;justify-content:center;cursor:pointer;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);box-shadow:0 2px 12px rgba(0,0,0,.3);transition:transform .12s ease}",
			"#dsh-mobile-menu-btn:active{transform:scale(.92)}",
			"#dsh-mobile-menu-btn svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}",
			/* 抽屉遮罩 */
			"#dsh-mobile-scrim{position:fixed;inset:0;z-index:2147482990;background:rgba(0,0,0,.55);display:none;opacity:0;transition:opacity .2s ease}",
			"#dsh-mobile-scrim.dsh-mobile-visible{display:block;opacity:1}",
			/* 会话抽屉（sidebar 变身 overlay） */
			"body.dsh-mobile-ui [class*=sidebarCol].dsh-mobile-drawer{display:block !important;position:fixed !important;top:0;left:0;bottom:0;width:min(84vw,320px) !important;z-index:2147482995;box-shadow:4px 0 24px rgba(0,0,0,.35);overflow-y:auto;animation:dsh-mobile-drawer-in .18s ease}",
			/* 设置弹层打开时：抽屉释放宽度/overflow 约束（弹层 100vw 全屏，不被抽屉裁剪） */
			"body.dsh-mobile-ui [class*=sidebarCol].dsh-mobile-settings-open{overflow:visible !important;width:100vw !important;max-width:100vw !important;box-shadow:none !important}",
			"@keyframes dsh-mobile-drawer-in{from{transform:translateX(-16px);opacity:0}to{transform:none;opacity:1}}",
			/* 移动端规则 */
			"@media (max-width:768px){",
			"  *{touch-action:manipulation;-webkit-tap-highlight-color:transparent}",
			"  html{-webkit-text-size-adjust:100%}",
			/* 16px 输入框字号防 iOS focus 自动缩放 */
			"  body.dsh-mobile-ui textarea,body.dsh-mobile-ui input,body.dsh-mobile-ui select{font-size:16px !important}",
			/* 布局单列（JS 同步改内联样式；此处 !important 兜底防 React 重渲染还原） */
			"  body.dsh-mobile-ui [class*=frame]{grid-template-columns:minmax(0,1fr) !important}",
			"  body.dsh-mobile-ui [class*=sidebarCol]{display:none}",
			/* 移动端隐藏右侧详情列（桌面 0px 面板，窄屏下会占行推挤内容） */
			"  body.dsh-mobile-ui [class*=detailsCol]{display:none !important}",
			/* 右上角菜单按钮显示（无底部导航栏，输入区直接贴底） */
			"  body.dsh-mobile-ui #dsh-mobile-menu-btn{display:flex}",
			"  body.dsh-mobile-ui [class*=composerSeat],body.dsh-mobile-ui [class*=composerStack]{padding-bottom:calc(10px + env(safe-area-inset-bottom,0px)) !important}",
			/* 头部紧凑（允许换行，标题不再截断） */
			"  body.dsh-mobile-ui [class*=header]{flex-wrap:wrap;row-gap:4px}",
			/* 触摸目标：composer 区按钮/触发器 ≥44px（iOS HIG） */
			"  body.dsh-mobile-ui [class*=composerSeat] button,body.dsh-mobile-ui [class*=composerStack] button{min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center}",
			"  body.dsh-mobile-ui [class*=composerSeat] [class*=trigger],body.dsh-mobile-ui [class*=composerStack] [class*=trigger]{min-height:40px}",
			/* 统计行（LLM 用时/首token）允许换行防截断（分段 nowrap 片段的父容器） */
			"  body.dsh-mobile-ui [class*=composerStack] > *,body.dsh-mobile-ui [class*=composerSeat] > *{white-space:normal !important;overflow-wrap:anywhere !important}",
			/* 抽屉会话列表项触摸目标 44px */
			"  body.dsh-mobile-ui [class*=sidebarCol] [class*=listArea] button{min-height:44px !important}",
			/* hero 布局：内容顶部对齐可滚动，输入区经 margin-top:auto 沉底贴视口底部 */
			"  body.dsh-mobile-ui [class*=scrollBody]{justify-content:flex-start !important}",
			"  body.dsh-mobile-ui [class*=composerSeat]{margin-top:auto !important}",
			"  body.dsh-mobile-ui [class*=composerSeat] [class*=uV2eYG_root]{margin-top:auto !important}",
			/* hero 标题置顶（纯 CSS，不移动 DOM）：composerHero 栈撑满视口，
			   输入卡经 margin-top:auto 沉底，标题/工作区行自然留在顶部。
			   禁止用 JS insertBefore 搬动 React 节点——重渲染时 removeChild 抛
			   NotFoundError，整个会话视图会被卸载（页面清空） */
			"  body.dsh-mobile-ui [class*=composerSeat]:has([class*=composerHero]){flex:1 1 auto !important;margin-top:0 !important}",
			"  body.dsh-mobile-ui [class*=composerHero]{flex:1 1 auto !important}",
			"  body.dsh-mobile-ui [class*=composerHero] > [class*=pXSMma_root]{flex:0 0 auto !important;height:auto !important;margin-top:24px !important}",
			"  body.dsh-mobile-ui [class*=composerHero] > [class*=heroWorkspaceRow]{flex:0 0 auto !important;height:auto !important}",
			/* 工作区行内按钮豁免 44px 触摸高（保持 28px 原高） */
			"  body.dsh-mobile-ui [class*=heroWorkspaceRow] button{min-height:28px !important;min-width:0 !important;height:auto !important}",
		/* QA 问答卡片（Mbwy4a）移动端适配：全屏弹层（与设置面板同构）——
		   seat 固定铺满视口 + 内部滚动，footer（跳过/提交）sticky 钉屏幕底部。
		   任何设备/视口/系统字体下提交按钮都必然可见；QA 关闭后自动恢复 */
		"  body.dsh-mobile-ui [class*=composerSeat].dsh-mobile-qa{position:fixed !important;top:100px !important;left:8px !important;right:8px !important;bottom:auto !important;margin:0 !important;z-index:2147482999 !important;padding:12px !important;max-height:calc(100vh - 150px) !important;max-height:calc(100dvh - 150px) !important;overflow-y:auto !important;background:transparent !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_card]{width:100% !important;max-width:none !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_body]{overflow:visible !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer]{position:sticky !important;bottom:0 !important;background:var(--dsw-alias-bg-layer-1,rgb(44,44,46)) !important}",
			/* QA footer 防溢出：内容超宽时换行（跳过/提交换行后仍可见，提交永不被裁） */
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer]{flex-wrap:wrap !important;row-gap:4px !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer] [class*=footerActions]{flex-wrap:wrap !important;min-width:0 !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer] button{flex:0 1 auto !important;min-width:0 !important;font-size:12px !important;padding:0 8px !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer] [class*=iconButton]{flex:0 0 44px !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer] [class*=progress]{flex:0 1 auto !important;min-width:0 !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_pager]{flex:0 1 auto !important;min-width:0 !important}",
			"  body.dsh-mobile-ui [class*=Mbwy4a_footer] button[class*=_primary]{flex:0 0 auto !important}",
			/* 操作行单行紧凑：hero 4 元素 / 会话页 5 元素（含上下文按钮）一行放下。
			   权限按钮移动端图标模式（44px 隐藏文字防撑宽），上下文紧凑 36px，
			   模型选择器 127px 居中显示（轻微截断可接受） */
			"  body.dsh-mobile-ui [class*=uV2eYG_row]{flex-wrap:nowrap !important;gap:4px !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_row] > *{flex:0 1 auto !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_tools],body.dsh-mobile-ui [class*=uV2eYG_modes]{padding:0 !important;gap:4px !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_row] [class*=trigger]{display:flex !important;align-items:center !important;line-height:1.2 !important}",
			"  body.dsh-mobile-ui button[aria-label*=选择模型]{display:flex !important;align-items:center !important;justify-content:center !important;flex:0 0 auto !important;max-width:136px !important;font-size:11px !important;padding:0 6px !important;overflow:hidden !important;text-overflow:ellipsis !important;white-space:nowrap !important}",
			"  body.dsh-mobile-ui button[aria-label*=访问模式]{width:44px !important;flex:0 0 44px !important;padding:0 !important;justify-content:center !important}",
			"  body.dsh-mobile-ui button[aria-label*=访问模式] span,body.dsh-mobile-ui button[aria-label*=访问模式] [class*=label]{display:none !important}",
			"  body.dsh-mobile-ui button[aria-label*=上下文]{width:36px !important;max-width:36px !important;min-width:36px !important;flex:0 0 36px !important;padding:0 !important;font-size:10px !important;justify-content:center !important;overflow:hidden !important}",
			"  body.dsh-mobile-ui button[aria-label*=上下文] span,body.dsh-mobile-ui button[aria-label*=上下文] [class*=label]{max-width:30px !important;overflow:hidden !important;text-overflow:ellipsis !important;white-space:nowrap !important}",
			/* 输入框圆角与内边距（视觉更圆润、输入更舒适；卡左右加宽） */
			"  body.dsh-mobile-ui [class*=input]{border-radius:18px !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_root]{padding-left:8px !important;padding-right:8px !important}",
			"  body.dsh-mobile-ui textarea{border-radius:18px !important}",
			/* 输入卡片彻底去边框白边（border/box-shadow 全清，背景跟随主题变量） */
			"  body.dsh-mobile-ui [class*=card]{border:none !important;box-shadow:none !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_card],body.dsh-mobile-ui [class*=uV2eYG_input]{border:none !important;box-shadow:none !important}",
			/* 阅读：消息流边距与间距（左右 8px，内容更宽） */
			"  body.dsh-mobile-ui [class*=scrollBody]{padding:12px 8px 0}",
			"  body.dsh-mobile-ui [class*=flowItem]{margin-bottom:14px}",
			"  body.dsh-mobile-ui [class*=userBubble],body.dsh-mobile-ui [class*=bubble]{max-width:92% !important}",
			/* 辅助文本字号提升（词根容错：actions/meta/caption/stamp/hint/tools/badge） */
			"  body.dsh-mobile-ui [class*=scrollBody] :is([class*=actions],[class*=meta],[class*=caption],[class*=stamp],[class*=hint],[class*=tools],[class*=badge],[class*=timing]){font-size:13px !important;white-space:normal !important;overflow-wrap:anywhere !important}",
			/* 状态统计行可读性（允许换行防截断） */
			"  body.dsh-mobile-ui [class*=statsRow],body.dsh-mobile-ui [class*=summaryRow],body.dsh-mobile-ui [class*=metrics]{font-size:12px !important;white-space:normal !important;overflow-wrap:anywhere}",
			/* 头像缩小省空间 */
			"  body.dsh-mobile-ui [class*=avatar]{width:28px !important;height:28px !important}",
			/* AI 正文与工具行视觉分隔 */
			"  body.dsh-mobile-ui [class*=markdown]{margin-top:6px}",
			/* 头部标题允许换行（防截断） */
			"  body.dsh-mobile-ui [class*=header] [class*=title],body.dsh-mobile-ui [class*=crumbs]{white-space:normal;overflow-wrap:anywhere}",
			/* 输入框聚焦反馈 */
			"  body.dsh-mobile-ui textarea:focus,body.dsh-mobile-ui [class*=input]:focus-within{outline:none;box-shadow:0 0 0 2px var(--dsw-alias-brand-primary,rgba(79,124,255,.45))}",
			/* 消息流操作按钮（复制/反馈/分享）触摸目标提升 */
			"  body.dsh-mobile-ui [class*=scrollBody] [class*=actions] button,body.dsh-mobile-ui [class*=scrollBody] [class*=tools] button{min-width:36px;min-height:36px;display:inline-flex;align-items:center;justify-content:center}",
			"}",

			/* 320px 小屏: 操作行进一步压缩防重叠 */
			"@media (max-width:360px){",
			"  body.dsh-mobile-ui button[aria-label*=选择模型]{max-width:110px !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_row]{gap:2px !important}",
			"  body.dsh-mobile-ui [class*=uV2eYG_tools],body.dsh-mobile-ui [class*=uV2eYG_modes]{gap:2px !important}",
			"  body.dsh-mobile-ui button[aria-label*=上下文]{margin-left:8px !important}",
			"}",
			/* 抽屉视觉：右侧圆角 + 更实背景 */
			"body.dsh-mobile-ui [class*=sidebarCol].dsh-mobile-drawer{border-radius:0 18px 18px 0;padding-bottom:64px !important;box-sizing:border-box !important}",
			/* 设置面板（VOzbGW 弹层）移动端：全宽 + 菜单收窄 + 内容区加宽 */
			"body.dsh-mobile-ui [class*=VOzbGW_panel]{left:0 !important;right:0 !important;width:100vw !important;max-width:100vw !important;border-radius:0 !important;box-sizing:border-box !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_overlay]{align-items:flex-start !important;padding-top:12px !important;padding-bottom:12px !important;box-sizing:border-box !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_panel]{max-height:calc(100vh - 24px) !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content],body.dsh-mobile-ui [class*=VOzbGW_options]{flex:1 1 auto !important;min-height:0 !important;max-height:none !important;overflow-y:auto !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_options]{padding-bottom:16px !important;box-sizing:border-box !important}",
			/* 模型选择菜单居中锚定（原 left:-150 固定值，按钮靠左时会出屏幕左侧） */
			"body.dsh-mobile-ui [class*=_7KE1Ra_menu]{left:50% !important;transform:translateX(-50%) !important;min-width:250px !important;max-width:calc(100vw - 24px) !important}",
			/* trailing 基础 gap 2px：hero（无上下文）模型右扩吃 gap，左缘保持不变 */
			"body.dsh-mobile-ui [class*=uV2eYG_trailing]{gap:2px !important}",
			/* 会话页（有上下文按钮）：上下文 margin-left 右移 12px（只扩模型↔上下文间距） */
			"body.dsh-mobile-ui [class*=uV2eYG_trailing]:has(button[aria-label*=上下文]) button[aria-label*=上下文]{margin-left:12px !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav]{width:68px !important;flex:0 0 68px !important;min-width:68px !important;overflow:visible !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav] [class*=navList]{flex:1 1 auto !important;height:auto !important;max-height:none !important;overflow-y:auto !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav] button,body.dsh-mobile-ui [class*=VOzbGW_nav] [role=button]{white-space:nowrap !important;overflow:hidden !important;text-overflow:ellipsis !important}",
			/* 选项卡改竖排（icon 上/文字下居中）：dsh 默认横排 icon+88px 标签总宽 112px，
			   88px 窄栏放不下会裁掉文字；竖排后 88px 宽容纳 4 字标签 */
			"body.dsh-mobile-ui [class*=VOzbGW_nav] [class*=navCell]{flex-direction:column !important;justify-content:center !important;align-items:center !important;gap:4px !important;padding:4px 0 !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav] [class*=navCell] svg{width:20px !important;height:20px !important;flex:0 0 auto !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav] [class*=navLabel]{flex:0 0 auto !important;width:auto !important;max-width:100% !important;min-width:0 !important;text-align:center !important;font-size:12px !important;line-height:1.2 !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_nav] [class*=navTitle]{width:100% !important;box-sizing:border-box !important;padding:0 8px !important;white-space:nowrap !important;overflow:hidden !important;text-overflow:ellipsis !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content]{flex:1 1 auto !important;min-width:0 !important;max-width:calc(100% - 68px) !important;padding:0 12px !important;overflow:hidden !important}",
			/* 头部防重叠加固：关闭按钮固定右侧 + 打开配置文件允许收缩 */
			"body.dsh-mobile-ui [class*=VOzbGW_header]{display:flex !important;align-items:center !important;justify-content:flex-end !important;gap:8px !important;padding:0 12px !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_close]{flex:0 0 28px !important;margin-left:0 !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_actions]{white-space:nowrap !important;overflow:hidden !important;text-overflow:ellipsis !important;min-width:0 !important}",
			/* 设置行内文字全宽（防 label 列被 flex 收缩成竖排窄列） */
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=section]{width:100% !important;max-width:100% !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=row]{flex-direction:column !important;align-items:stretch !important;gap:4px !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=rowText]{flex:1 1 auto !important;min-width:0 !important;align-items:stretch !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=row] > *:last-child{flex:0 0 auto !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=title],body.dsh-mobile-ui [class*=VOzbGW_content] [class*=rowText]{width:100% !important;max-width:100% !important;white-space:normal !important;overflow-wrap:anywhere !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=title]{display:block !important;flex:1 1 auto !important;align-self:stretch !important}",
			"body.dsh-mobile-ui [class*=VOzbGW_content] [class*=rowText]{flex:1 1 auto !important;min-width:0 !important}",
			/* 会话行操作菜单（dsh portal 弹层，原 z-index:1100）提升层级：
			   抽屉(2147482995)/遮罩(2147482990)层级过高会把菜单盖住（归档等操作不可见）。
			   仅移动端提升，菜单 fixed 定位不受抽屉 overflow 裁剪；QA 卡片(2147482999)仍居最上 */
			"body.dsh-mobile-ui [class*=_portal_]{z-index:2147482996 !important}",
			/* dsh 模态弹层容器提升：目录选择(添加工作区)/Modal 的 portal root 是 fixed z-index:1000，
			   会被抽屉(2147482995)/遮罩(2147482990)盖住 → 弹框不可见。
			   [role=dialog] 定位容器统一提升到 2996 与菜单同级(< QA 2999) */
			"body.dsh-mobile-ui div:has(> [role=dialog]){z-index:2147482996 !important}",
		].join("\n");

		function injectStyle() {
			try {
				if (typeof document === "undefined") return;
				var tagId = "dsh-mobile-ui";
				if (document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]")) return;
				var tag = document.createElement("style");
				tag.dataset.plugin = "dsh-mobile-ui";
				tag.dataset.pluginCss = tagId;
				tag.textContent = MOBILE_CSS;
				document.head.appendChild(tag);
			} catch (e) { /* CSS 注入失败不致命 */ }
		}

		/* ═══════════════════ JS 增强层 ═══════════════════ */
		var MOBILE_MQ = "(max-width: 768px)";
		var FRAME_GRID_NARROW = "minmax(0, 1fr)";

		function initMobile() {
			try {
				if (typeof window === "undefined" || typeof document === "undefined") return;
				injectStyle();
				var mq = window.matchMedia(MOBILE_MQ);
				var tabbar = null;
				var scrim = null;
				var drawerOpen = false;
				var settingsOpen = false;   /* 设置弹层打开标志（弹层关闭时恢复导航栏） */
				var savedGrid = null;   /* 窄屏前的 frame 原始 grid（宽屏恢复用） */

				/* 主布局 frame：display:grid 的顶层容器（CSS 生效前 3 列 / 生效后 1 列均可） */
				function findFrame() {
					var els = document.querySelectorAll("[class*=frame]");
					for (var i = 0; i < els.length; i++) {
						var el = els[i];
						if (!el || !el.children || el.children.length < 3) continue;
						var cs = window.getComputedStyle(el);
						if (cs.display === "grid") {
							var cols = cs.gridTemplateColumns.split(" ").length;
							if (cols >= 1 && cols <= 3) return el;
						}
					}
					return null;
				}
				function getSidebar() {
					var frame = findFrame();
					return frame && frame.children[0] ? frame.children[0] : null;
				}
				function findSidebarButton(label) {
					var side = getSidebar();
					if (!side) return null;
					var btns = side.querySelectorAll("button");
					for (var i = 0; i < btns.length; i++) {
						if ((btns[i].getAttribute("aria-label") || "") === label) return btns[i];
					}
					return null;
				}

				function ensureChrome() {
					if (document.getElementById("dsh-mobile-menu-btn")) {
						tabbar = document.getElementById("dsh-mobile-menu-btn");
						scrim = document.getElementById("dsh-mobile-scrim");
						return;
					}
					scrim = document.createElement("div");
					scrim.id = "dsh-mobile-scrim";
					scrim.addEventListener("click", function () { closeDrawer(); });
					document.body.appendChild(scrim);

					/* 右上角菜单按钮：打开会话抽屉（抽屉内含 新建/会话列表/设置 全部入口）。
					   复用 tabbar 变量承载，显隐逻辑（模态隐藏/恢复）零改动 */
					tabbar = document.createElement("button");
					tabbar.id = "dsh-mobile-menu-btn";
					tabbar.type = "button";
					tabbar.setAttribute("aria-label", "菜单");
					tabbar.innerHTML = "<svg viewBox='0 0 24 24'><path d='M4 7h16M4 12h16M4 17h10'/></svg>";
					tabbar.addEventListener("click", function () {
						try { openDrawer(); } catch (e) { /* 忽略 */ }
					});
					document.body.appendChild(tabbar);
				}

				function setTabActive(key) {
					try {
						if (!tabbar) return;
						var btns = tabbar.querySelectorAll("button");
						for (var i = 0; i < btns.length; i++) {
							if (btns[i].getAttribute("aria-label") === key) btns[i].classList.add("dsh-mobile-active");
							else btns[i].classList.remove("dsh-mobile-active");
						}
					} catch (e) { /* 忽略 */ }
				}
				function openDrawer() {
					var side = getSidebar();
					if (!side) return;
					side.classList.add("dsh-mobile-drawer");
					if (scrim) scrim.classList.add("dsh-mobile-visible");
					drawerOpen = true;
					/* 抽屉/设置模态打开时隐藏底部导航栏（避免双层级干扰） */
					if (tabbar) tabbar.style.display = "none";
					setTabActive("会话");
					/* 折叠态 sidebar 只有图标 rail，展开以显示会话列表 */
					var tog = findSidebarButton("打开侧边栏");
					if (tog) { try { tog.click(); } catch (e) {} }
				}
				function closeDrawer() {
					var side = getSidebar();
					if (side) {
						side.classList.remove("dsh-mobile-drawer");
						side.classList.remove("dsh-mobile-settings-open");
					}
					if (scrim) scrim.classList.remove("dsh-mobile-visible");
					drawerOpen = false;
					settingsOpen = false;
					setTabActive("");
					if (tabbar) tabbar.style.display = "";
				}

				function sync() {
					try {
						if (mq.matches) {
							/* 设置弹层状态检测：出现（用户手动点抽屉设置）→ 释放抽屉约束 + 隐藏菜单；
							   消失 → 恢复抽屉/菜单 */
							{
								var ov2 = document.querySelector("[class*=VOzbGW_overlay]");
								var ovVisible = ov2 && getComputedStyle(ov2).display !== "none";
								if (ovVisible && !settingsOpen) {
									settingsOpen = true;
									var sd = getSidebar();
									if (sd) sd.classList.add("dsh-mobile-settings-open");
									if (tabbar) tabbar.style.display = "none";
								} else if (!ovVisible && settingsOpen) {
									settingsOpen = false;
									var sd2 = getSidebar();
									if (sd2) sd2.classList.remove("dsh-mobile-settings-open");
									if (tabbar) tabbar.style.display = "";
								}
							}
							document.body.classList.add("dsh-mobile-ui");
							/* QA 弹层标记：JS 检测 Mbwy4a 卡片（不依赖 :has，兼容微信 X5 等旧内核）。
							   加 class 到 composerSeat，CSS 据此全屏化；卡片消失即移除 */
							try {
								var qaFrame = document.querySelector("[class*=Mbwy4a_frame]");
								var qaSeat = null;
								if (qaFrame) {
									var qn = qaFrame.parentElement;
									while (qn) { if ((typeof qn.className === "string" ? qn.className : "").indexOf("composerSeat") >= 0) { qaSeat = qn; break; } qn = qn.parentElement; }
								}
								if (qaSeat) qaSeat.classList.add("dsh-mobile-qa");
								else { var qOld = document.querySelector("[class*=composerSeat].dsh-mobile-qa"); if (qOld) qOld.classList.remove("dsh-mobile-qa"); }
							} catch (e) { /* QA 标记失败静默 */ }
							/* hero 标题置顶改由纯 CSS 实现（composerHero 撑满视口 + 输入卡沉底），
							   不再用 insertBefore 搬动 React 节点——移动节点会导致 React 重渲染
							   removeChild 抛 NotFoundError，整个会话视图卸载（页面空白） */
							var frame = findFrame();
							if (frame) {
								if (savedGrid === null) savedGrid = frame.style.gridTemplateColumns;
								frame.style.gridTemplateColumns = FRAME_GRID_NARROW;
							}
							var side = getSidebar();
							/* 抽屉态下 sidebar 保持可见，否则隐藏 */
							side.style.display = drawerOpen ? "" : "none";
							ensureChrome();
							if (tabbar) tabbar.style.display = drawerOpen ? "none" : "";
						} else {
							document.body.classList.remove("dsh-mobile-ui");
							var frame2 = findFrame();
							if (frame2) {
								if (savedGrid) frame2.style.gridTemplateColumns = savedGrid;
								savedGrid = null;
							}
							var side2 = getSidebar();
							if (side2) side2.style.display = "";
							closeDrawer();
							if (tabbar) tabbar.style.display = "none";
						}
					} catch (e) { /* 同步失败静默 */ }
				}

				/* 监听视口变化 */
				if (typeof mq.addEventListener === "function") {
					mq.addEventListener("change", sync);
				} else if (typeof mq.addListener === "function") {
					mq.addListener(sync);
				}

				/* 首次同步 + 等待 React 渲染出 frame 后重试 */
				sync();
				var tries = 0;
				var retryTimer = setInterval(function () {
					tries++;
					if (findFrame()) { sync(); if (tries > 3) clearInterval(retryTimer); }
					else if (tries > 30) clearInterval(retryTimer);
				}, 500);

				/* DOM 结构变化（React 重渲染）后重新同步 */
				var mo = null;
				if (typeof MutationObserver !== "undefined") {
					var debounce = null;
					mo = new MutationObserver(function () {
						if (debounce) clearTimeout(debounce);
						debounce = setTimeout(sync, 200);
					});
					mo.observe(document.body, { childList: true, subtree: true });
				}

				/* 卸载清理 */
				return function () {
					try {
						if (retryTimer) clearInterval(retryTimer);
						if (debounce) clearTimeout(debounce);
						if (mo) mo.disconnect();
						if (tabbar && tabbar.parentNode) tabbar.parentNode.removeChild(tabbar);
						if (scrim && scrim.parentNode) scrim.parentNode.removeChild(scrim);
						document.body.classList.remove("dsh-mobile-ui");
					} catch (e) { /* 清理失败静默 */ }
				};
			} catch (e) {
				return function () { /* 初始化失败，静默降级 */ };
			}
		}

		/* ═══════════════════ Cordis 插件形状 ═══════════════════ */
		var name = "dsh-mobile-ui";
		var inject = [];
		function apply(ctx) {
			ctx.logger?.info?.("[dsh-mobile-ui] active: browser mobile UI enhancement mounted");
			return initMobile();
		}
		exports.name = name;
		exports.inject = inject;
		exports.apply = apply;
		return module.exports;
	}
});
