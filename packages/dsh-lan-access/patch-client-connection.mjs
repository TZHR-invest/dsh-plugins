#!/usr/bin/env node
/**
 * patch-client-connection.mjs — 给 @deepseek-ai/dsh-client-connection/lib/index.js 打
 * dsh 0.1.2+ 局域网令牌补丁（幂等，可反复执行；--revert 可回滚）。
 *
 * 用法:
 *   node patch-client-connection.mjs <client-connection-lib-index.js> [--check] [--revert]
 *
 * 补丁内容（全部以 "[dsh-lan-access] client-connection" 标记）:
 *   1. import 区补入 node:fs/os/path（读取 lan-access-token 所需）；
 *   2. processLaunchToken 优先返回 ~/.dsh/lan-access-token（存在时）——
 *      使 LAN URL 的 ?token= 与门卫令牌统一且跨重启稳定，浏览器原生
 *      browserAuth cookie 交换（GET /?token=xxx）因此可直接使用该令牌；
 *   3. requestRejection 在 browserAuth 未通过时接受 X-DSH-Token == launch token
 *      （curl/脚本等无浏览器 cookie 的 LAN API 调用通道）。
 *
 * 依赖 dsh 0.1.2+ 代码结构；0.1.1 及更早版本结构不同，勿用。
 */
import { readFileSync, writeFileSync } from "node:fs";

const IMPORT_ANCHOR = 'import { credentialKey } from "@deepseek-ai/dsh-credentials";';
const IMPORT_ADD =
	'import { readFileSync } from "node:fs";\n' +
	'import { homedir } from "node:os";\n' +
	'import { join } from "node:path";';
const PATCH_MARK = "/* [dsh-lan-access] client-connection patch v1（dsh 0.1.2+） */";

const LAUNCH_OLD = "\tconst created = encodeBase64Url(randomBytes(SECRET_BYTES));";
const LAUNCH_NEW =
	"\t/* [dsh-lan-access] client-connection patch: prefer lan-access-token as the launch token */\n" +
	"\tlet created = \"\";\n" +
	"\ttry {\n" +
	'\t\tcreated = readFileSync(join(process.env.DSH_HOME || join(homedir(), ".dsh"), "lan-access-token"), "utf8").trim();\n' +
	"\t} catch {}\n" +
	"\tif (created.length === 0) created = encodeBase64Url(randomBytes(SECRET_BYTES));";

const REJECT_OLD =
	"\t/** Apply the configured Host/Origin fence, then browser authentication. */\n" +
	"\trequestRejection(request) {\n" +
	"\t\tif (!isTrustedApiRequest(request, this.trustedHosts)) return 403;\n" +
	"\t\treturn this.browserAuth.isAuthenticated(request) ? void 0 : 401;\n" +
	"\t}";
const REJECT_NEW =
	"\t/** Apply the configured Host/Origin fence, then browser authentication. */\n" +
	"\trequestRejection(request) {\n" +
	"\t\tif (!isTrustedApiRequest(request, this.trustedHosts)) return 403;\n" +
	"\t\tif (this.browserAuth.isAuthenticated(request)) return void 0;\n" +
	"\t\t/* [dsh-lan-access] client-connection patch: LAN API token channel (X-DSH-Token == launch token) */\n" +
	"\t\tconst rawH = request.headers;\n" +
	'\t\tconst got = rawH && typeof rawH.get === "function" ? rawH.get("x-dsh-token") : rawH && rawH["x-dsh-token"];\n' +
	"\t\tif (typeof got === \"string\" && got.length > 0 && tokenMatches(got, this.browserAuth.launchToken)) return void 0;\n" +
	"\t\treturn 401;\n" +
	"\t}";

const file = process.argv[2];
const mode = process.argv.includes("--revert") ? "revert" : process.argv.includes("--check") ? "check" : "apply";
if (!file) {
	console.error("用法: node patch-client-connection.mjs <client-connection-lib-index.js> [--check] [--revert]");
	process.exit(2);
}

let src;
try {
	src = readFileSync(file, "utf8");
} catch (e) {
	console.error("[patch-client-connection] 无法读取 " + file + ": " + e.message);
	process.exit(2);
}

const patched = src.includes("[dsh-lan-access] client-connection patch v1");

if (mode === "check") {
	console.log(patched ? "[已有] client-connection 局域网令牌补丁" : "[缺失] client-connection 局域网令牌补丁");
	process.exit(patched ? 0 : 1);
}

if (mode === "apply") {
	if (patched) {
		console.log("[已有] client-connection 局域网令牌补丁（幂等跳过）");
		process.exit(0);
	}
	if (!src.includes(IMPORT_ANCHOR)) {
		console.error("[失败] 未找到 import 锚点，dsh-client-connection 版本结构可能已变化（需 0.1.2+），请人工适配");
		process.exit(1);
	}
	if (!src.includes(LAUNCH_OLD)) {
		console.error("[失败] 未找到 processLaunchToken 锚点，dsh-client-connection 版本结构可能已变化，请人工适配");
		process.exit(1);
	}
	if (!src.includes(REJECT_OLD)) {
		console.error("[失败] 未找到 requestRejection 锚点，dsh-client-connection 版本结构可能已变化，请人工适配");
		process.exit(1);
	}
	src = src.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + "\n" + IMPORT_ADD + "\n" + PATCH_MARK);
	src = src.replace(LAUNCH_OLD, LAUNCH_NEW);
	src = src.replace(REJECT_OLD, REJECT_NEW);
	writeFileSync(file, src);
	console.log("[已打] client-connection 局域网令牌补丁（" + file + "）");
	process.exit(0);
}

/* revert */
if (!patched) {
	console.log("[跳过] 无补丁可回滚");
	process.exit(0);
}
const importBlock = IMPORT_ANCHOR + "\n" + IMPORT_ADD + "\n" + PATCH_MARK;
if (!src.includes(importBlock)) {
	console.error("[失败] import 区补丁块与预期不符，请人工检查");
	process.exit(1);
}
src = src.replace(importBlock, IMPORT_ANCHOR);
if (!src.includes(LAUNCH_NEW) || !src.includes(REJECT_NEW)) {
	console.error("[失败] 函数区补丁块与预期不符，请人工检查");
	process.exit(1);
}
src = src.replace(LAUNCH_NEW, LAUNCH_OLD);
src = src.replace(REJECT_NEW, REJECT_OLD);
writeFileSync(file, src);
console.log("[已回滚] client-connection 局域网令牌补丁（" + file + "）");
process.exit(0);
