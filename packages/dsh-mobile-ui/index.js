/**
 * dsh-mobile-ui — 宿主端（极简占位）。
 *
 * 本插件的实质在浏览器端（./client）：移动端视口（≤768px）下的
 * 响应式布局、阅读/触摸优化与底部导航。host half 仅需让 client
 * bundle 随组合装载即可，无需任何宿主服务。
 */
export const name = "dsh-mobile-ui";

export function apply(ctx) {
	ctx.logger?.info?.("[dsh-mobile-ui] active: host half (browser enhancement in ./client)");
}
