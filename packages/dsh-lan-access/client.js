window.__ModuleLoader__.load({
	id: "dsh-lan-gateway",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		/* [LAN] 局域网明文 HTTP 属非安全上下文，浏览器不提供 crypto.randomUUID，此处补齐 v4 兜底。 */
		if (typeof globalThis !== "undefined" && typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.randomUUID !== "function") {
			try {
				Object.defineProperty(globalThis.crypto, "randomUUID", {
					configurable: true,
					writable: true,
					value: function randomUUID() {
						return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
							var r = Math.random() * 16 | 0;
							return (c === "x" ? r : (r & 3 | 8)).toString(16);
						});
					}
				});
			} catch (e) {}
		}
		/* dsh-lan-access —— 浏览器端 cordis 插件。
		 * dsh 0.1.0-rc.6 起组合装载要求浏览器模块导出函数或带 apply 的对象
		 * （"invalid plugin ... received object" 即缺 apply 所致）；polyfill 作为
		 * 模块副作用在装载时生效，apply 仅用于满足插件形状校验。 */
		var name = "lan-access";
		var inject = [];
		function apply(ctx) {
			ctx.logger?.info?.("[dsh-lan-access] active: browser crypto.randomUUID polyfill mounted");
		}
		exports.name = name;
		exports.inject = inject;
		exports.apply = apply;
		return module.exports;
	}
});
