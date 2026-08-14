/**
 * __PACKAGE_NAME__ — 宿主端（Host half）。
 *
 * dsh host 插件是 Cordis 插件：导出 name 与 apply(ctx)。
 * - apply 的返回值若是函数，则在 fiber 释放（插件卸载）时执行，用于清理。
 * - 依赖其他服务时用 inject 声明（浏览器侧见 ./client.js，机制见 docs/development.md）。
 */
export const name = "__PLUGIN_ID__";

export function apply(ctx) {
	ctx.logger?.info?.("[__PLUGIN_ID__] active: host half mounted");
	return () => {
		/* 插件卸载时的清理 */
	};
}
