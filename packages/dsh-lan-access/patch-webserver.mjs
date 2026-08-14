#!/usr/bin/env node
/**
 * patch-webserver.mjs — 给 @deepseek-ai/dsh-host-webserver/lib/index.js 打
 * 局域网访问令牌门卫补丁（幂等，可反复执行；--revert 可回滚）。
 *
 * 用法:
 *   node patch-webserver.mjs <webserver-lib-index.js> [--check] [--revert]
 *
 * 补丁内容（全部以 "[dsh-lan-access] token gate" 标记）:
 *   1. import 区后插入 token-gate.js 全文（认证函数 + 内联登录页）
 *   2. handle 入口插入门卫调用（未授权 -> 401 登录页 / POST /__lan_auth）
 *   3. upgrade 入口插入门卫调用（未授权 -> 销毁 WebSocket 连接）
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const GATE = readFileSync(join(HERE, "token-gate.js"), "utf8");

const IMPORT_ANCHOR = 'import z from "@deepseek-ai/schemastery";';
const HANDLE_ANCHOR = "\tconst handle = async (req, res) => {\n";
const UPGRADE_ANCHOR = "\t\tthis.server.on(\"upgrade\", (req, socket, head) => {\n";

const HANDLE_BLOCK =
	"\t\t/* [dsh-lan-access] token gate */\n" +
	"\t\tif (!lanGateIsLoopback(req) && lanGateRequest(req, res)) return;\n";
const UPGRADE_BLOCK =
	"\t\t\t/* [dsh-lan-access] token gate */\n" +
	"\t\t\tif (!lanGateIsLoopback(req) && !lanGateAuthorized(req)) {\n" +
	"\t\t\t\tsocket.destroy();\n" +
	"\t\t\t\treturn;\n" +
	"\t\t\t}\n";

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

const patched = src.includes("[dsh-lan-access] token gate");

if (mode === "check") {
	console.log(patched ? "[已有] webserver 令牌门卫补丁" : "[缺失] webserver 令牌门卫补丁");
	process.exit(patched ? 0 : 1);
}

if (mode === "apply") {
	if (patched) {
		console.log("[已有] webserver 令牌门卫补丁（幂等跳过）");
		process.exit(0);
	}
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
	src = src.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + "\n" + GATE + "\n");
	src = src.replace(HANDLE_ANCHOR, HANDLE_ANCHOR + HANDLE_BLOCK);
	src = src.replace(UPGRADE_ANCHOR, UPGRADE_ANCHOR + UPGRADE_BLOCK);
	writeFileSync(file, src);
	console.log("[已打] webserver 令牌门卫补丁（" + file + "）");
	process.exit(0);
}

// revert
if (!patched) {
	console.log("[跳过] 无补丁可回滚");
	process.exit(0);
}
const gateBlock = IMPORT_ANCHOR + "\n" + GATE + "\n";
if (!src.includes(gateBlock)) {
	console.error("[失败] import 区补丁块与预期不符，请人工检查");
	process.exit(1);
}
src = src.replace(gateBlock, IMPORT_ANCHOR);
src = src.replace(HANDLE_BLOCK, "");
src = src.replace(UPGRADE_BLOCK, "");
writeFileSync(file, src);
console.log("[已回滚] webserver 令牌门卫补丁（" + file + "）");
process.exit(0);