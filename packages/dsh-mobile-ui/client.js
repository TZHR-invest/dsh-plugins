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
			/* 底部导航栏 */
			"#dsh-mobile-tabbar{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;display:none;height:calc(52px + env(safe-area-inset-bottom,0px));padding-bottom:env(safe-area-inset-bottom,0px);align-items:stretch;background:var(--dsw-alias-bg-overlay,rgba(16,17,20,.92));backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-top:1px solid var(--dsw-alias-border-l2,rgba(255,255,255,.12));box-shadow:0 -4px 16px rgba(0,0,0,.18)}",
			"#dsh-mobile-tabbar button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;min-height:48px;background:none;border:none;color:var(--dsw-alias-label-secondary,rgba(255,255,255,.62));font-size:11px;line-height:1;cursor:pointer;padding:6px 0 2px}",
			"#dsh-mobile-tabbar button svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}",
			"#dsh-mobile-tabbar button:active{opacity:.7}",
			"#dsh-mobile-tabbar button.dsh-mobile-active{color:var(--dsw-alias-brand-primary,#4f7cff)}",
			/* 抽屉遮罩 */
			"#dsh-mobile-scrim{position:fixed;inset:0;z-index:2147482990;background:rgba(0,0,0,.55);display:none;opacity:0;transition:opacity .2s ease}",
			"#dsh-mobile-scrim.dsh-mobile-visible{display:block;opacity:1}",
			/* 会话抽屉（sidebar 变身 overlay） */
			"body.dsh-mobile-ui [class*=sidebarCol].dsh-mobile-drawer{display:block !important;position:fixed !important;top:0;left:0;bottom:0;width:min(84vw,320px) !important;z-index:2147482995;box-shadow:4px 0 24px rgba(0,0,0,.35);overflow-y:auto;animation:dsh-mobile-drawer-in .18s ease}",
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
			/* 底部导航显示 + composer 底部留白 */
			"  body.dsh-mobile-ui #dsh-mobile-tabbar{display:flex}",
			"  body.dsh-mobile-ui [class*=composerSeat],body.dsh-mobile-ui [class*=composerStack]{padding-bottom:calc(64px + env(safe-area-inset-bottom,0px)) !important}",
			/* 头部紧凑（允许换行，标题不再截断） */
			"  body.dsh-mobile-ui [class*=header]{flex-wrap:wrap;row-gap:4px}",
			/* 触摸目标：composer 区按钮/触发器 ≥44px（iOS HIG） */
			"  body.dsh-mobile-ui [class*=composerSeat] button,body.dsh-mobile-ui [class*=composerStack] button{min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center}",
			"  body.dsh-mobile-ui [class*=composerSeat] [class*=trigger],body.dsh-mobile-ui [class*=composerStack] [class*=trigger]{min-height:40px}",
			/* 输入框圆角与内边距（视觉更圆润、输入更舒适） */
			"  body.dsh-mobile-ui [class*=input]{border-radius:18px !important}",
			"  body.dsh-mobile-ui textarea{border-radius:18px !important}",
			/* 阅读：消息流边距与间距 */
			"  body.dsh-mobile-ui [class*=scrollBody]{padding:12px 12px 0}",
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
			"  body.dsh-mobile-ui textarea:focus,body.dsh-mobile-ui [class*=input]:focus-within{outline:none;box-shadow:0 0 0 2px var(--dsw-alias-brand-primary,rgba(79,124,255,.45))}",,
			"}",
			/* 底部导航栏（移动端）增强样式 */
			"#dsh-mobile-tabbar{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;display:none;height:calc(58px + env(safe-area-inset-bottom,0px));padding-bottom:env(safe-area-inset-bottom,0px);align-items:stretch;background:var(--dsw-alias-bg-layer-1,rgba(22,23,27,.96));backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-top:1px solid var(--dsw-alias-border-l2,rgba(255,255,255,.14));box-shadow:0 -4px 20px rgba(0,0,0,.25)}",
			"#dsh-mobile-tabbar button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:50px;background:none;border:none;color:var(--dsw-alias-label-secondary,rgba(255,255,255,.6));font-size:12px;line-height:1;cursor:pointer;padding:8px 0 2px;border-radius:10px;margin:3px 6px;transition:color .15s ease,background .15s ease}",
			"#dsh-mobile-tabbar button svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}",
			"#dsh-mobile-tabbar button:active{background:var(--dsw-alias-interactive-bg-hover,rgba(255,255,255,.08))}",
			"#dsh-mobile-tabbar button.dsh-mobile-active{color:var(--dsw-alias-brand-primary,#4f7cff)}",
			"#dsh-mobile-tabbar button.dsh-mobile-active::before{content:'';position:absolute;top:2px;left:50%;transform:translateX(-50%);width:24px;height:3px;border-radius:2px;background:var(--dsw-alias-brand-primary,#4f7cff)}",
			"#dsh-mobile-tabbar button{position:relative}",
			/* 抽屉视觉：右侧圆角 + 更实背景 */
			"body.dsh-mobile-ui [class*=sidebarCol].dsh-mobile-drawer{border-radius:0 18px 18px 0}",
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
					if (document.getElementById("dsh-mobile-tabbar")) {
						tabbar = document.getElementById("dsh-mobile-tabbar");
						scrim = document.getElementById("dsh-mobile-scrim");
						return;
					}
					scrim = document.createElement("div");
					scrim.id = "dsh-mobile-scrim";
					scrim.addEventListener("click", function () { closeDrawer(); });
					document.body.appendChild(scrim);

					tabbar = document.createElement("div");
					tabbar.id = "dsh-mobile-tabbar";
					tabbar.setAttribute("role", "navigation");
					tabbar.setAttribute("aria-label", "移动端导航");
					var defs = [
						{ key: "new", label: "新建", icon: "<svg viewBox='0 0 24 24'><path d='M12 5v14M5 12h14'/></svg>" },
						{ key: "sessions", label: "会话", icon: "<svg viewBox='0 0 24 24'><path d='M4 6h16M4 12h10M4 18h7'/></svg>" },
						{ key: "settings", label: "设置", icon: "<svg viewBox='0 0 24 24'><circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55h.09a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z'/></svg>" }
					];
					for (var i = 0; i < defs.length; i++) {
						(function (d) {
							var b = document.createElement("button");
							b.type = "button";
							b.setAttribute("aria-label", d.label);
							b.innerHTML = d.icon + "<span>" + d.label + "</span>";
							b.addEventListener("click", function () {
								try {
									if (d.key === "new") {
										var nb = findSidebarButton("新建会话");
										if (nb) nb.click();
									} else if (d.key === "sessions") {
										openDrawer();
									} else if (d.key === "settings") {
										var sb = document.querySelector("button[aria-label=设置]");
										if (sb) { sb.click(); }
										else { openDrawer(); }
									}
								} catch (e) { /* 入口转发失败静默 */ }
							});
							tabbar.appendChild(b);
						})(defs[i]);
					}
					document.body.appendChild(tabbar);
				}

				function openDrawer() {
					var side = getSidebar();
					if (!side) return;
					side.classList.add("dsh-mobile-drawer");
					if (scrim) scrim.classList.add("dsh-mobile-visible");
					drawerOpen = true;
					/* 折叠态 sidebar 只有图标 rail，展开以显示会话列表 */
					var tog = findSidebarButton("打开侧边栏");
					if (tog) { try { tog.click(); } catch (e) {} }
				}
				function closeDrawer() {
					var side = getSidebar();
					if (side) side.classList.remove("dsh-mobile-drawer");
					if (scrim) scrim.classList.remove("dsh-mobile-visible");
					drawerOpen = false;
				}

				function sync() {
					try {
						if (mq.matches) {
							document.body.classList.add("dsh-mobile-ui");
							var frame = findFrame();
							if (frame) {
								if (savedGrid === null) savedGrid = frame.style.gridTemplateColumns;
								frame.style.gridTemplateColumns = FRAME_GRID_NARROW;
							}
							var side = getSidebar();
							/* 抽屉态下 sidebar 保持可见，否则隐藏 */
							side.style.display = drawerOpen ? "" : "none";
							ensureChrome();
							if (tabbar) tabbar.style.display = "";
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
