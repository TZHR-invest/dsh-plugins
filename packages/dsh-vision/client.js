window.__ModuleLoader__.load({
	id: "dsh-vision-tool",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		/* 浏览器端副作用在模块装载（materialize）时执行，模块加载即生效 */
		var name = "dsh-vision";
		var inject = [];
		function apply(ctx) {
			ctx.logger?.info?.("[dsh-vision] active: browser half mounted");
		}
		exports.name = name;
		exports.inject = inject;
		exports.apply = apply;
		return module.exports;
	}
});
