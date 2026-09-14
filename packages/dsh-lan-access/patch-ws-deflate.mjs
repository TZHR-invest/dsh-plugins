#!/usr/bin/env node
/**
 * patch-ws-deflate.mjs — 让 dsh 的 WebSocket 走 permessage-deflate（响应压缩）。
 *
 * ## 为什么需要（2026-09-14 实测）
 *
 * 浏览器与 dsh 之间的所有 Remote 流（含「打开历史会话」）复用同一条
 * `/api/remote.mux`，而 **WS 帧不经过 HTTP 层的 gzip**：打开一个活跃会话时服务端
 * 一次性回一帧 0.8–1.2 MB 的 JSON（消息正文 + 工具输出 + thinking 签名），在手机
 * 那条 ~10 KB/s 链路上要 ~120 秒，前端表现就是"一直显示正在加载"。
 *
 * 上游的 WebSocketServer 是 `new WebSocketServer({ noServer: true })` —— ws 服务端
 * 默认不开压缩，于是这一帧是**裸传**的。打开 permessage-deflate 后实测：
 *
 *     1.20 MB → 线上 255 KB（4.80x）
 *
 * 代价：服务端每帧多约 10 ms CPU（level 3），每连接一个 zlib 上下文（默认
 * `serverNoContextTakeover: true`，不累积）；ws 默认 `threshold: 1024`，
 * 小于 1 KB 的帧（事件流）不压缩，所以心跳/小事件不受影响。
 *
 * ## 用法
 *
 *     node patch-ws-deflate.mjs <dsh-api-gateway 目录> [--check] [--revert]
 *     例: node patch-ws-deflate.mjs ~/.npm-global/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-api-gateway
 *
 * ## 退出码（与 patch-webserver.mjs 同约定）
 *
 *     0 = 已是目标状态（或操作成功）；1 = 失败（锚点未找到/需人工适配）；
 *     2 = 用法或读取失败；3 = 未打（apply 可就地打上）。
 *
 * 幂等：可反复执行。上游若自己启用了 perMessageDeflate，也识别为"已有"。
 * 生效条件：**必须重启该机的 dsh web**（WebSocketServer 在进程启动时构造）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/** dsh-api-gateway 内两处 WebSocketServer 构造点（相对传入目录）。 */
const TARGETS = ["lib/index.js", "lib/types/stream-server.js"];
const OLD = "new WebSocketServer({ noServer: true })";
const NEW = "new WebSocketServer({ noServer: true, perMessageDeflate: true })";

const [dir, ...flags] = process.argv.slice(2);
const check = flags.includes("--check");
const revert = flags.includes("--revert");

if (dir === undefined) {
	console.error("用法: node patch-ws-deflate.mjs <dsh-api-gateway 目录> [--check] [--revert]");
	process.exit(2);
}

const files = TARGETS.map((rel) => join(dir, rel));
let sources;
try {
	sources = files.map((f) => readFileSync(f, "utf8"));
} catch (error) {
	console.error("[失败] 读取失败：" + error.message);
	process.exit(2);
}

const isPatched = sources.every((src) => src.includes("perMessageDeflate"));

if (check) {
	if (isPatched) {
		console.log("[已有] websocket permessage-deflate（" + files.length + " 处构造点）");
		process.exit(0);
	}
	console.log("[缺失] websocket permessage-deflate → 慢链路上打开历史会话要多传约 4 倍字节");
	process.exit(3);
}

if (revert) {
	let changed = 0;
	sources.forEach((src, i) => {
		if (!src.includes(NEW)) return;
		writeFileSync(files[i], src.split(NEW).join(OLD));
		changed++;
	});
	console.log(changed === 0
		? "[跳过] 没有可回滚的改动（未找到精确补丁串）"
		: "[已回滚] websocket permessage-deflate（" + changed + " 处；重启 dsh web 后回到未压缩）");
	process.exit(0);
}

if (isPatched) {
	console.log("[已有] websocket permessage-deflate，无需改动");
	process.exit(0);
}

let patched = 0;
const failed = [];
sources.forEach((src, i) => {
	if (src.includes("perMessageDeflate")) return; // 该文件已启用（可能是上游自带）
	if (!src.includes(OLD)) {
		failed.push(TARGETS[i]); // 结构变了，不猜、不改
		return;
	}
	writeFileSync(files[i], src.split(OLD).join(NEW));
	patched++;
});

if (failed.length > 0) {
	console.error("[失败] 未找到构造锚点（dsh-api-gateway 结构可能已变化，请人工适配）：" + failed.join("、"));
	process.exit(1);
}
console.log("[已打] websocket permessage-deflate（" + patched + " 处；重启该机 dsh web 后生效）");
process.exit(0);
