#!/usr/bin/env node
/**
 * token-gate.js 单元测试（v3）。
 *
 * 运行: node --test packages/dsh-lan-access/tests/
 *
 * 覆盖点（对应 2026-09-14 的事故）：
 *   1. 回环请求也要能拿到登录页（v2 的回环短路曾让 127.0.0.1 只剩纯文本 401）；
 *   2. 无凭据 → 登录页；令牌 query/header/cookie 三条通道 → 放行并种 Cookie；
 *   3. POST /__lan_auth 正确/错误令牌的两种响应；
 *   4. index-401 兜底：browserAuth 的 401 换登录页，其余状态码/路径透传。
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";

const TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef";

let home;
before(() => {
	home = mkdtempSync(join(tmpdir(), "lan-gate-test-"));
	writeFileSync(join(home, "lan-access-token"), TOKEN + "\n", { mode: 0o600 });
	process.env.DSH_HOME = home;
});
after(() => {
	delete process.env.DSH_HOME;
	rmSync(home, { recursive: true, force: true });
});

const {
	lanGateAuthorized,
	lanGateCatchIndexUnauthorized,
	lanGateIsLoopback,
	lanGateRequest,
} = await import("../token-gate.js");

/** 最小 req 假体。 */
function makeReq({ method = "GET", url = "/", host = "127.0.0.1:3080", cookie, header } = {}) {
	const headers = { host };
	if (cookie !== void 0) headers.cookie = cookie;
	if (header !== void 0) headers["x-dsh-token"] = header;
	return { method, url, headers, on: () => {} };
}

/** 可投喂表单 body 的 req 假体（POST /__lan_auth 用）。 */
function makeFormReq(body) {
	const handlers = new Map();
	const req = makeReq({ method: "POST", url: "/__lan_auth" });
	req.on = (event, handler) => {
		handlers.set(event, handler);
		return req;
	};
	/** 依次触发 data / end，返回 end 处理完成的 Promise。 */
	req.emitBody = async () => {
		handlers.get("data")?.(body);
		await new Promise((resolve) => setImmediate(resolve));
		handlers.get("end")?.();
		await new Promise((resolve) => setImmediate(resolve));
	};
	return req;
}

/** 最小 res 假体（记录 writeHead/end/setHeader）。 */
function makeRes() {
	return {
		status: null,
		headers: null,
		body: void 0,
		headersSent: false,
		setHeaders: [],
		writeHead(status, headers) {
			this.status = status;
			this.headers = headers;
			this.headersSent = true;
			return this;
		},
		setHeader(name, value) {
			this.setHeaders.push([name, value]);
		},
		end(body) {
			this.body = body;
		},
	};
}

test("回环 + 无凭据 GET / → 401 登录页（v3 的核心修正）", () => {
	const res = makeRes();
	const handled = lanGateRequest(makeReq(), res);
	assert.equal(handled, true);
	assert.equal(res.status, 401);
	assert.match(res.headers["content-type"], /text\/html/);
	assert.match(res.body, /访问验证/);
	assert.match(res.body, /placeholder="访问令牌"/);
});

test("非回环 + 无凭据 → 同样登录页", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ host: "192.168.0.202:3080" }), res), true);
	assert.equal(res.status, 401);
	assert.match(res.body, /访问验证/);
});

test("回环 + ?token= 正确 → 放行并种 Cookie", () => {
	const res = makeRes();
	const handled = lanGateRequest(makeReq({ url: "/?token=" + TOKEN }), res);
	assert.equal(handled, false);
	assert.deepEqual(res.setHeaders, [["set-cookie", expectCookie()]]);
});

test("非回环 + X-DSH-Token 正确 → 放行", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ host: "192.168.0.202:3080", header: TOKEN }), res), false);
});

test("lan cookie 正确 → 放行（不再种 Cookie）", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ cookie: "dsh_lan_token=" + TOKEN }), res), false);
	assert.deepEqual(res.setHeaders, []);
});

test("lan cookie 错误 → 门卫放行（由 browserAuth 拒绝，再由 index-401 兜底换成登录页）", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ cookie: "dsh_lan_token=wrong" }), res), false);
	assert.equal(res.status, null);
	lanGateCatchIndexUnauthorized(makeReq({ cookie: "dsh_lan_token=wrong" }), res);
	res.writeHead(401, { "content-type": "text/plain; charset=utf-8" });
	res.end("dsh web authentication required; reopen the URL printed by dsh web.\n");
	assert.equal(res.status, 401);
	assert.match(res.body, /访问验证/);
});

test("带任意 cookie（如 browserAuth 已失效）→ 门卫放行，交给 browserAuth 裁决", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ cookie: "dsh-auth-abc=stale" }), res), false);
});

test("POST /__lan_auth 正确令牌 → 302 到 /?token=", async () => {
	const res = makeRes();
	const req = makeFormReq("token=" + TOKEN);
	lanGateRequest(req, res);
	await req.emitBody();
	assert.equal(res.status, 302);
	assert.equal(res.headers.location, "/?token=" + TOKEN);
	assert.match(res.headers["set-cookie"], /^dsh_lan_token=/);
});

test("POST /__lan_auth 错误令牌 → 401 + 错误提示页", async () => {
	const res = makeRes();
	const req = makeFormReq("token=wrong");
	lanGateRequest(req, res);
	await req.emitBody();
	assert.equal(res.status, 401);
	assert.match(res.body, /令牌不正确/);
});

test("__lan_auth 非 POST → 405", () => {
	const res = makeRes();
	assert.equal(lanGateRequest(makeReq({ url: "/__lan_auth" }), res), true);
	assert.equal(res.status, 405);
});

test("未配置令牌文件 → 门卫关闭，一切放行", () => {
	const saved = process.env.DSH_HOME;
	process.env.DSH_HOME = join(home, "nope");
	try {
		const res = makeRes();
		assert.equal(lanGateAuthorized(makeReq()), "cookie");
		assert.equal(lanGateRequest(makeReq({ host: "192.168.0.202:3080" }), res), false);
		assert.equal(res.status, null);
	} finally {
		process.env.DSH_HOME = saved;
	}
});

test("index-401 兜底：browserAuth 的纯文本 401 被换成登录页", () => {
	const res = makeRes();
	lanGateCatchIndexUnauthorized(makeReq({ cookie: "dsh-auth-abc=stale" }), res);
	// 模拟 host browserAuth 的 writeUnauthorized()
	res.writeHead(401, { "cache-control": "no-store", "content-type": "text/plain; charset=utf-8" });
	res.end("dsh web authentication required; reopen the URL printed by dsh web.\n");
	assert.equal(res.status, 401);
	assert.match(res.headers["content-type"], /text\/html/);
	assert.match(res.body, /访问验证/);
	assert.doesNotMatch(res.body, /authentication required/);
});

test("index-401 兜底：200 原样透传", () => {
	const res = makeRes();
	lanGateCatchIndexUnauthorized(makeReq(), res);
	res.writeHead(200, { "content-type": "text/html" });
	res.end("<html>app</html>");
	assert.equal(res.status, 200);
	assert.equal(res.body, "<html>app</html>");
});

test("index-401 兜底：非 index 路径的 401 不劫持", () => {
	const res = makeRes();
	lanGateCatchIndexUnauthorized(makeReq({ url: "/api/session/modelCatalog" }), res);
	res.writeHead(401, { "content-type": "application/json" });
	res.end('{"error":"unauthorized"}');
	assert.equal(res.status, 401);
	assert.equal(res.body, '{"error":"unauthorized"}');
});

test("index-401 兜底：POST 请求不劫持", () => {
	const res = makeRes();
	lanGateCatchIndexUnauthorized(makeReq({ method: "POST" }), res);
	res.writeHead(401, { "content-type": "text/plain" });
	res.end("nope");
	assert.equal(res.status, 401);
	assert.equal(res.body, "nope");
});

test("回环判定：Host 语义", () => {
	assert.equal(lanGateIsLoopback(makeReq({ host: "127.0.0.1:3080" })), true);
	assert.equal(lanGateIsLoopback(makeReq({ host: "localhost:3080" })), true);
	assert.equal(lanGateIsLoopback(makeReq({ host: "192.168.0.202:3080" })), false);
});

function expectCookie() {
	return "dsh_lan_token=" + TOKEN + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" + 60 * 60 * 24 * 30;
}
