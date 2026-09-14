#!/usr/bin/env node
/**
 * patch-webserver.mjs — 给 @deepseek-ai/dsh-host-webserver/lib/index.js 打
 * 局域网访问令牌门卫补丁（幂等，可反复执行；--revert 可回滚）。
 *
 * 用法:
 *   node patch-webserver.mjs <webserver-lib-index.js> [--check] [--revert]
 *
 * 退出码:
 *   0 = 已是当前版本（或操作成功）；1 = 补丁缺失/操作失败；2 = 用法或读取失败；
 *   3 = 是旧版本（apply 可就地升级）。
 *
 * 补丁内容（全部以 "[dsh-lan-access] token gate" 标记）:
 *   1. import 区后插入 token-gate.js 全文（认证函数 + 内联登录页）
 *   2. handle 入口插入门卫调用（未授权 -> 401 登录页 / POST /__lan_auth）
 *      + index-401 兜底（browserAuth 拒绝时也换登录页）
 *   3. upgrade 入口插入门卫调用（未授权 -> 销毁 WebSocket 连接）
 *
 * 版本:
 *   v1 —— dsh 0.1.x 时代：门卫独立鉴权（lan-access-token），通过即放行；
 *   v2 —— dsh 0.1.2+ 适配：浏览器原生凭证通道（cookie / /?token= 启动令牌 URL）
 *         交由 host 的 browserAuth 裁决（需配合 patch-client-connection.mjs 把
 *         启动令牌固定为 lan-access-token）；门卫只拦完全无凭证的裸请求。
 *   v3 —— 2026-09-14：①回环不再短路（本机 127.0.0.1 也能看到登录页，不再只剩
 *         browserAuth 的纯文本 401）；②handle 入口加 index-401 兜底。
 *   已打 v1/v2 的安装运行 apply 会就地升级为 v3（v2 内嵌源码须与
 *   token-gate.v2.js 逐字节一致，否则拒绝改动并提示人工检查）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const GATE = readFileSync(join(HERE, "token-gate.js"), "utf8");
/** v2 版门卫源码（就地升级的匹配基准；由 0.2.3 的 token-gate.js 原样留档）。 */
const GATE_V2 = readFileSync(join(HERE, "token-gate.v2.js"), "utf8");

const IMPORT_ANCHOR = 'import z from "@deepseek-ai/schemastery";';
const HANDLE_ANCHOR = "\tconst handle = async (req, res) => {\n";
const UPGRADE_ANCHOR = "\t\tthis.server.on(\"upgrade\", (req, socket, head) => {\n";

const V3_MARKER = "token gate —— 自包含补丁源（v3）";
const V2_MARKER = "token gate —— 自包含补丁源（v2）";
const V1_MARKER = "token gate —— 自包含补丁源（v1）";

const HANDLE_BLOCK =
	"\t\t/* [dsh-lan-access] token gate v3 */\n" +
	"\t\tif (lanGateRequest(req, res)) return;\n" +
	"\t\tlanGateCatchIndexUnauthorized(req, res);\n";
/* v2 的 handle 块（就地升级时被替换掉；v2 由 0.2.x 的补丁脚本插入）。 */
const HANDLE_BLOCK_V2 =
	"\t\t/* [dsh-lan-access] token gate */\n" +
	"\t\tif (!lanGateIsLoopback(req) && lanGateRequest(req, res)) return;\n";
const UPGRADE_BLOCK =
	"\t\t\t/* [dsh-lan-access] token gate */\n" +
	"\t\t\tif (!lanGateIsLoopback(req) && !lanGateAuthorized(req)) {\n" +
	"\t\t\t\tsocket.destroy();\n" +
	"\t\t\t\treturn;\n" +
	"\t\t\t}\n";

/* v1 -> v2 原地升级的两处文本（v1 由旧版 token-gate.js 插入，锚点均唯一）。 */
const V1_AUTH_302 = 'res.writeHead(302, { location: "/", "set-cookie": lanGateCookie() });';
const V2_AUTH_302 =
	'/* v2: launch token 已由 client-connection 补丁固定为 lan-access-token，\n' +
	"\t\t\t * 302 到 /?token= 触发 host browserAuth 交换并种下其原生 cookie。 */\n" +
	"\t\t\tres.writeHead(302, { location: \"/?token=\" + encodeURIComponent(token), \"set-cookie\": lanGateCookie() });";
const V1_GATE_BRANCH =
	"\tconst via = lanGateAuthorized(req);\n" +
	'\tif (via === "") {\n' +
	'\t\tres.writeHead(401, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });\n' +
	"\t\tres.end(lanGatePage(false));\n" +
	"\t\treturn true;\n" +
	"\t}\n";
const V2_GATE_BRANCH =
	"\tconst via = lanGateAuthorized(req);\n" +
	'\tif (via === "") {\n' +
	"\t\t/* v2: 放行 host 原生凭证通道（浏览器 cookie 或 /?token= 启动令牌 URL），\n" +
	"\t\t * 由 browserAuth 裁决；门卫仅拦截完全无凭证的裸请求。 */\n" +
	"\t\tconst rawH = req.headers;\n" +
	'\t\tconst hasCookie = rawH !== void 0 && (typeof rawH.get === "function" ? rawH.get("cookie") : rawH.cookie) !== void 0;\n' +
	'\t\tconst hasLaunchToken = req.method === "GET" && pathname === "/" && /(?:^|[?&])token=[^&#]+/.test(req.url || "");\n' +
	"\t\tif (!hasCookie && !hasLaunchToken) {\n" +
	'\t\t\tres.writeHead(401, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });\n' +
	"\t\t\tres.end(lanGatePage(false));\n" +
	"\t\t\treturn true;\n" +
	"\t\t}\n" +
	"\t}\n";

/** 用函数式替换，避免补丁文本里的 `$` 被当成替换模式。 */
function splice(src, from, to) {
	return src.replace(from, () => to);
}

/** v2 -> v3：内嵌门卫源码与 handle 门卫块各换一处。 */
function upgradeV2toV3(src) {
	if (!src.includes(HANDLE_BLOCK_V2)) return { ok: false, why: "未找到 v2 的 handle 门卫块" };
	const v2GateBlock = IMPORT_ANCHOR + "\n" + GATE_V2 + "\n";
	if (!src.includes(v2GateBlock)) {
		return { ok: false, why: "内嵌 v2 门卫源码与 token-gate.v2.js 不一致（可能被手工改过）" };
	}
	let out = splice(src, v2GateBlock, IMPORT_ANCHOR + "\n" + GATE + "\n");
	out = splice(out, HANDLE_BLOCK_V2, HANDLE_BLOCK);
	if (!out.includes(V3_MARKER) || out.includes(V2_MARKER) || out.includes(HANDLE_BLOCK_V2)) {
		return { ok: false, why: "v2 -> v3 升级未完全生效" };
	}
	return { ok: true, src: out };
}

const file = process.argv[2];
const mode = process.argv.includes("--revert") ? "revert" : process.argv.includes("--check") ? "check" : "apply";
if (!file) {
	console.error("用法: node patch-webserver.mjs <webserver-lib-index.js> [--check] [--revert]");
	process.exit(2);
}

let src;
try {
	src = readFileSync(file, "utf8");
} catch (e) {
	console.error("[patch-webserver] 无法读取 " + file + ": " + e.message);
	process.exit(2);
}

const isV3 = src.includes(V3_MARKER);
const isV2 = src.includes(V2_MARKER);
const isV1 = src.includes(V1_MARKER);

if (mode === "check") {
	if (isV3) {
		console.log("[已有] webserver 令牌门卫补丁 v3（回环也出登录页 + index-401 兜底）");
		process.exit(0);
	}
	if (isV2 || isV1) {
		console.log("[旧版] webserver 令牌门卫补丁 " + (isV2 ? "v2" : "v1") + "（运行 apply 就地升级 v3）");
		process.exit(3);
	}
	console.log("[缺失] webserver 令牌门卫补丁");
	process.exit(1);
}

if (mode === "apply") {
	if (isV3) {
		console.log("[已有] webserver 令牌门卫补丁 v3（幂等跳过）");
		process.exit(0);
	}
	if (isV1) {
		/* 先 v1 -> v2（旧版文本替换），再走 v2 -> v3。 */
		if (!src.includes(V1_AUTH_302) || !src.includes(V1_GATE_BRANCH)) {
			console.error("[失败] v1 补丁块与预期不符，请人工检查 webserver 文件");
			process.exit(1);
		}
		src = splice(src, V1_MARKER, V2_MARKER);
		src = splice(src, V1_AUTH_302, V2_AUTH_302);
		src = splice(src, V1_GATE_BRANCH, V2_GATE_BRANCH);
		if (!src.includes(V2_MARKER) || src.includes(V1_AUTH_302) || src.includes(V1_GATE_BRANCH)) {
			console.error("[失败] v1 -> v2 升级未完全生效，请人工检查");
			process.exit(1);
		}
	}
	if (isV1 || isV2) {
		const upgraded = upgradeV2toV3(src);
		if (!upgraded.ok) {
			console.error("[失败] v2 -> v3 升级未生效：" + upgraded.why + "，请人工检查");
			process.exit(1);
		}
		writeFileSync(file, upgraded.src);
		console.log("[已升级] webserver 令牌门卫补丁 " + (isV1 ? "v1" : "v2") + " -> v3（" + file + "）");
		process.exit(0);
	}
	/* 全新安装 */
	if (!src.includes(IMPORT_ANCHOR)) {
		console.error("[失败] 未找到 import 锚点，dsh-host-webserver 版本结构可能已变化，请人工适配");
		process.exit(1);
	}
	if (!src.includes(HANDLE_ANCHOR)) {
		console.error("[失败] 未找到 handle 锚点，dsh-host-webserver 版本结构可能已变化，请人工适配");
		process.exit(1);
	}
	if (!src.includes(UPGRADE_ANCHOR)) {
		console.error("[失败] 未找到 upgrade 锚点，dsh-host-webserver 版本结构可能已变化，请人工适配");
		process.exit(1);
	}
	src = splice(src, IMPORT_ANCHOR, IMPORT_ANCHOR + "\n" + GATE + "\n");
	src = splice(src, HANDLE_ANCHOR, HANDLE_ANCHOR + HANDLE_BLOCK);
	src = splice(src, UPGRADE_ANCHOR, UPGRADE_ANCHOR + UPGRADE_BLOCK);
	writeFileSync(file, src);
	console.log("[已打] webserver 令牌门卫补丁 v3（" + file + "）");
	process.exit(0);
}

/* revert：移除 v3 补丁块（文本与插入时一致方可回滚）。 */
if (!isV3) {
	console.log("[跳过] 无 v3 补丁可回滚" + (isV1 || isV2 ? "（当前是 " + (isV2 ? "v2" : "v1") + "，请用对应旧版脚本回滚）" : ""));
	process.exit(0);
}
const gateBlock = IMPORT_ANCHOR + "\n" + GATE + "\n";
if (!src.includes(gateBlock)) {
	console.error("[失败] import 区补丁块与预期不符，请人工检查");
	process.exit(1);
}
src = splice(src, gateBlock, IMPORT_ANCHOR);
src = splice(src, HANDLE_BLOCK, "");
src = splice(src, UPGRADE_BLOCK, "");
writeFileSync(file, src);
console.log("[已回滚] webserver 令牌门卫补丁 v3（" + file + "）");
process.exit(0);
