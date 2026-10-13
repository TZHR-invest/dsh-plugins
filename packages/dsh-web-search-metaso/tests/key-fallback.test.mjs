#!/usr/bin/env node
/**
 * dsh-web-search-metaso —— 主/备 key 回退 + errCode 不再静默（2026-10-13 事故回归测试）
 *
 * 运行:  node --test packages/dsh-web-search-metaso/tests/
 *
 * ## 事故（为什么要有这些用例）
 *
 * 2026-10-13 07:13~07:27，一个 GUI 研究任务 fan-out 出 4 路子代理，对**同一把** metaso
 * key 打了 232 次 /search + 78 次 /reader（≈930 credits），账号随后归零。之后：
 *   - `{"errCode":3000,"errMsg":"余额不足"}` 是 **HTTP 200 + 业务错误**，旧实现只判
 *     `response.ok`，于是 `data["webpages"] ?? []` 变成空数组 ⇒ agent 看到的是
 *     「这次没有搜索结果」，**不是**计费错误（5 台机器的会话里连一行错误都没有）；
 *   - 这把 key 被多处共用（dsh 插件 / stock_selection / hermes），谁先打光不可控。
 *
 * 因此本文件锁两件事：① errCode 非 0 必须抛错（不静默）；② 额度类错误自动换
 * `fallbackApiKey`，且主 key 冷却到期后自动回到主 key（充值到账即自愈）。
 *
 * ## 为什么测试要搭沙箱
 *
 * 插件有 6 个 peerDependency（@deepseek-ai/*），本仓库里没有 node_modules。
 * 于是本测试在临时目录里放一个指向 dsh 安装目录 node_modules 的软链，再拷一份
 * index.js 进去 import —— 不改仓库、不动线上安装。
 */
import assert from "node:assert/strict";
import { copyFileSync, existsSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { after, before, test } from "node:test";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_SOURCE = join(HERE, "..", "index.js");

function findDshNodeModules() {
  const candidates = [
    process.env.DSH_NODE_MODULES,
    process.env.NPM_GLOBAL_ROOT === undefined ? undefined : join(process.env.NPM_GLOBAL_ROOT, "@deepseek-ai/dsh/node_modules"),
    "/home/wbaifan/.npm-global/lib/node_modules/@deepseek-ai/dsh/node_modules",
  ].filter((p) => typeof p === "string" && p.length > 0);
  return candidates.find((p) => existsSync(join(p, "@deepseek-ai/dsh-web"))) ?? null;
}

let sandbox;
let importSeq = 0;

before(() => {
  const deps = findDshNodeModules();
  if (deps === null) return;
  sandbox = mkdtempSync(join(tmpdir(), "metaso-fallback-"));
  symlinkSync(deps, join(sandbox, "node_modules"), "dir");
  copyFileSync(PLUGIN_SOURCE, join(sandbox, "index.js"));
});

after(() => {
  if (sandbox !== undefined) rmSync(sandbox, { recursive: true, force: true });
});

/**
 * 每个用例 import 一份**全新的模块实例**（URL 加查询串，绕开 ESM 缓存）：
 * 插件把「主 key 冷却」记在模块级变量里，共用实例会让用例互相串状态。
 */
async function freshPlugin(t) {
  if (sandbox === undefined) {
    t.skip("未找到 dsh 安装目录的 node_modules（可用 DSH_NODE_MODULES 指定）");
    return null;
  }
  importSeq += 1;
  const url = `${pathToFileURL(join(sandbox, "index.js")).href}?case=${importSeq}`;
  return import(url);
}

/** 用假 ctx 注册 provider，拿到真实实例（与 dsh 的 ctx.web 同形）。 */
function installProviders(mod, config) {
  const providers = {};
  const ctx = {
    get: () => void 0,
    web: {
      registerSearchProvider: (p) => {
        providers.search = p;
      },
      registerFetchProvider: (p) => {
        providers.fetch = p;
      },
    },
  };
  mod.apply(ctx, config);
  return providers;
}

/** 桩掉 globalThis.fetch，记录每次请求的 Authorization。 */
function stubFetch(handler, calls) {
  globalThis.fetch = async (url, init) => {
    const auth = init?.headers?.authorization ?? "";
    calls.push(auth);
    const { status = 200, body } = handler(calls.length, auth) ?? {};
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    };
  };
}

const QUOTA = { errCode: 3000, errMsg: "余额不足" };
const OK_SEARCH = {
  total: 1,
  webpages: [{ link: "https://example.com/a", title: "A", summary: "摘要", date: "2026年10月13日" }],
};
const OK_READER = { markdown: "# 正文", credits: 3, title: "标题" };

/**
 * 按 **用了哪把 key** 决定响应（而不是按第几次调用）——「冷却期间只有备 key 在跑」
 * 这类用例里，调用序号会重置，只有 key 才是稳定判据。
 */
const primaryExhausted = (okBody) => (n, auth) => (auth === "Bearer mk-primary" ? { body: QUOTA } : { body: okBody });

test("主 key 额度耗尽 ⇒ 自动改用备 key，且结果照常返回", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(primaryExhausted(OK_SEARCH), calls);
  const { search } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: 0,
  });
  const result = await search.search({ query: "MiniMax H3 继任者", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary", "Bearer mk-backup"], "第一次主 key、第二次备 key");
  assert.equal(result.sources.length, 1);
  assert.equal(result.sources[0].url, "https://example.com/a");
});

test("额度耗尽不再静默：没配备 key 时必须抛 WEB_PROVIDER_QUOTA_EXHAUSTED", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(() => ({ body: QUOTA }), calls);
  const { search } = installProviders(mod, { apiKey: "mk-primary", primaryCooldownSeconds: 0 });
  await assert.rejects(
    () => search.search({ query: "x", maxResults: 3 }, void 0),
    (error) => {
      assert.equal(error.code, "WEB_PROVIDER_QUOTA_EXHAUSTED");
      assert.match(error.message, /余额不足/);
      return true;
    },
  );
  assert.deepEqual(calls, ["Bearer mk-primary"], "没配 fallback 就不该有第二次请求");
});

test("鉴权类 errCode（2005）不换 key，按普通失败抛出", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(() => ({ body: { errCode: 2005, errMsg: "API密钥无效" } }), calls);
  const { search } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: 0,
  });
  await assert.rejects(() => search.search({ query: "x", maxResults: 3 }, void 0), (error) => {
    assert.equal(error.code, "WEB_PROVIDER_ERROR");
    return true;
  });
  assert.deepEqual(calls, ["Bearer mk-primary"]);
});

test("冷却期内直接用备 key（不再白撞主 key）", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(primaryExhausted(OK_SEARCH), calls);
  const { search } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: 600,
  });
  await search.search({ query: "第一次（触发换 key）", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary", "Bearer mk-backup"]);

  calls.length = 0;
  await search.search({ query: "冷却中", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-backup"], "冷却期内不该再撞主 key");
});

test("冷却到期后自动回到主 key（充值到账即无感恢复）", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(primaryExhausted(OK_SEARCH), calls);
  // 负冷却 = blockedUntil 落在过去 ⇒ 等价于「冷却已到期」
  const { search } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: -1,
  });
  await search.search({ query: "触发一次换 key（冷却即刻到期）", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary", "Bearer mk-backup"]);

  calls.length = 0;
  stubFetch(() => ({ body: OK_SEARCH }), calls);
  await search.search({ query: "冷却到期后", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary"], "冷却到期必须回到主 key");
});

test("web_fetch（/reader）同样支持回退", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(primaryExhausted(OK_READER), calls);
  const { fetch } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: 0,
  });
  const result = await fetch.fetch({ url: "https://example.com/a" }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary", "Bearer mk-backup"]);
  assert.equal(result.body.content, "# 正文");
});

test("主 key 正常时只用主 key（备 key 不参与）", async (t) => {
  const mod = await freshPlugin(t);
  if (mod === null) return;
  const calls = [];
  stubFetch(() => ({ body: OK_SEARCH }), calls);
  const { search } = installProviders(mod, {
    apiKey: "mk-primary",
    fallbackApiKey: "mk-backup",
    primaryCooldownSeconds: 0,
  });
  await search.search({ query: "正常路径", maxResults: 3 }, void 0);
  assert.deepEqual(calls, ["Bearer mk-primary"]);
});
