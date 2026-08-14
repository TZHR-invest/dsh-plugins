/* [dsh-lan-access] token gate —— 自包含补丁源（v1）。
 * 本文件被 patch-webserver.mjs 原样插入到 dsh-host-webserver/lib/index.js，
 * 同时可被独立 import 做单元测试。不要在无补丁的模块外修改本节函数。 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { createHash, timingSafeEqual } from "node:crypto";

const LAN_GATE_COOKIE = "dsh_lan_token";
const LAN_GATE_AUTH_PATH = "/__lan_auth";
const LAN_GATE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

/** 令牌文件：$DSH_HOME/lan-access-token（默认 ~/.dsh/lan-access-token）。 */
export function lanGateTokenFile() {
	return join(process.env.DSH_HOME || join(homedir(), ".dsh"), "lan-access-token");
}

/** 读取令牌（trim 后）；文件缺失或不可读时返回空串（=未启用门卫）。 */
export function lanGateReadToken() {
	try {
		return readFileSync(lanGateTokenFile(), "utf8").trim();
	} catch {
		return "";
	}
}

/** 恒定时间比较（先各自 sha256 再 timingSafeEqual，避免长度/内容侧信道）。 */
export function lanGateEquals(got, want) {
	if (typeof got !== "string" || typeof want !== "string") return false;
	if (got.length === 0 || want.length === 0) return false;
	const g = createHash("sha256").update(got, "utf8").digest();
	const w = createHash("sha256").update(want, "utf8").digest();
	return timingSafeEqual(g, w);
}

/** 请求是否来自本机回环（localhost / 127.* / ::1）——回环豁免令牌。 */
export function lanGateIsLoopback(req) {
	try {
		const host = new URL("http://" + (req.headers.host || "")).hostname;
		if (host === "localhost" || host === "[::1]" || host === "::1") return true;
		return host.startsWith("127.");
	} catch {
		return false;
	}
}

/**
 * 请求是否持有有效令牌。返回通过通道：
 *   "cookie" —— Cookie 通过（或未配置令牌=门卫关闭）；
 *   "query"  —— URL ?token= / ?dsh_token= 通过；
 *   "header" —— X-DSH-Token 通过；
 *   ""       —— 未授权。
 */
export function lanGateAuthorized(req) {
	const token = lanGateReadToken();
	if (!token) return "cookie";
	const url = req.url || "/";
	const qmark = url.indexOf("?");
	if (qmark !== -1) {
		try {
			const q = new URLSearchParams(url.slice(qmark + 1));
			const qt = q.get("token") || q.get("dsh_token");
			if (qt !== null && lanGateEquals(qt, token)) return "query";
		} catch {}
	}
	const header = req.headers["x-dsh-token"];
	if (typeof header === "string" && lanGateEquals(header, token)) return "header";
	const cookieHeader = req.headers.cookie;
	if (typeof cookieHeader === "string") {
		for (const part of cookieHeader.split(";")) {
			const eq = part.indexOf("=");
			if (eq === -1) continue;
			if (part.slice(0, eq).trim() === LAN_GATE_COOKIE && lanGateEquals(part.slice(eq + 1).trim(), token)) return "cookie";
		}
	}
	return "";
}

/** 认证成功时种下的会话 Cookie（HttpOnly + SameSite=Strict，30 天）。 */
export function lanGateCookie() {
	const token = lanGateReadToken();
	return LAN_GATE_COOKIE + "=" + encodeURIComponent(token) + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" + LAN_GATE_COOKIE_MAX_AGE;
}

/** 内联登录页（无任何外部资源依赖，深色）。hasError 时展示错误提示。 */
/** 内联登录页（无任何外部资源依赖，深色）。hasError 时展示错误提示。 */
export function lanGatePage(hasError) {
	const page = [
		"<!doctype html>",
		'<html lang="zh-CN">',
		"<head>",
		'<meta charset="utf-8">',
		'<meta name="viewport" content="width=device-width, initial-scale=1">',
		"<title>DeepSeek Harness · 访问验证</title>",
		"<style>",
		":root{color-scheme:dark}",
		"*{box-sizing:border-box}",
		'body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d1117;color:#e6edf3;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}',
		'.card{width:min(92vw,380px);padding:32px 28px;background:#161b22;border:1px solid #30363d;border-radius:12px}',
		"h1{margin:0 0 6px;font-size:18px;letter-spacing:.2px}",
		".sub{margin:0 0 20px;color:#8b949e;font-size:13px;line-height:1.6}",
		'input{width:100%;padding:10px 12px;margin-bottom:14px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:14px}',
		"input:focus{outline:none;border-color:#58a6ff}",
		'button{width:100%;padding:10px;border:0;border-radius:8px;background:#238636;color:#fff;font-size:14px;font-weight:600;cursor:pointer}',
		"button:hover{background:#2ea043}",
		".err{margin-top:14px;color:#f85149;font-size:13px}",
		"</style>",
		"</head>",
		"<body>",
		'<div class="card">',
		"<h1>DeepSeek Harness</h1>",
		'<p class="sub">此服务已启用局域网访问令牌。请输入令牌后进入。</p>',
		'<form method="post" action="' + LAN_GATE_AUTH_PATH + '">',
		'<input type="password" name="token" placeholder="访问令牌" autocomplete="current-password" autofocus required>',
		'<button type="submit">进入</button>',
		"</form>",
	];
	if (hasError) page.push('<div class="err">令牌不正确，请重试</div>');
	page.push("</div>", "</body>", "</html>");
	return page.join("\n") + "\n";
}
/** POST /__lan_auth：校验表单令牌，成功则种 Cookie 并 302 到 /。 */
export function lanGateHandleAuth(req, res) {
	const token = lanGateReadToken();
	let body = "";
	let done = false;
	req.on("data", (chunk) => {
		if (done) return;
		body += chunk;
		if (body.length > 8192) {
			done = true;
			req.destroy();
		}
	});
	req.on("end", () => {
		if (done) return;
		done = true;
		let got = "";
		try {
			got = new URLSearchParams(body).get("token") || "";
		} catch {}
		if (token !== "" && lanGateEquals(got, token)) {
			res.writeHead(302, { location: "/", "set-cookie": lanGateCookie() });
			res.end();
		} else {
			res.writeHead(401, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
			res.end(lanGatePage(true));
		}
	});
}

/**
 * 非回环请求的统一门卫入口。返回 true 表示本函数已处理完响应；
 * 返回 false 表示授权通过、放行后续路由。query/header 通道通过时顺带种 Cookie。
 */
export function lanGateRequest(req, res) {
	const pathname = new URL(req.url || "/", "http://x").pathname;
	if (pathname === LAN_GATE_AUTH_PATH) {
		if (req.method === "POST") {
			lanGateHandleAuth(req, res);
		} else {
			res.writeHead(405, { allow: "POST" });
			res.end("method not allowed");
		}
		return true;
	}
	const via = lanGateAuthorized(req);
	if (via === "") {
		res.writeHead(401, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
		res.end(lanGatePage(false));
		return true;
	}
	if (via !== "cookie" && !res.headersSent) {
		res.setHeader("set-cookie", lanGateCookie());
	}
	return false;
}