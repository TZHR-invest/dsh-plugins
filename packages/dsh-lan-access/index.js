/**
 * dsh-lan-access — 宿主端（极简占位）。
 *
 * 本插件的实质在浏览器端（./client）：为明文 HTTP 的局域网访问补齐
 * crypto.randomUUID —— 浏览器只在安全上下文（HTTPS / localhost）暴露该方法，
 * 局域网 IP 明文访问时缺失，导致 dsh 客户端插件（消息 ID / RPC ID / 会话节点 ID）
 * 崩溃。这里只需让 client bundle 随组合装载即可。
 */
export const name = "lan-access";

export function apply(ctx) {
	ctx.logger?.info?.("[dsh-lan-access] active: browser crypto.randomUUID polyfill mounted");
}
