/**
 * dsh-web-search-metaso — Metaso（秘塔AI搜索）providers for the DeepSeek Harness web seam (ctx.web)。
 *
 * 注册两个 provider，让 dsh 自带的 web_search / web_fetch 工具直接获得秘塔能力：
 *   - MetasoSearchProvider（id: metaso）：POST {baseURL}/search，
 *     综合摘要 → WebSearchResult.content，网页条目 → sources[]（url/title/snippet/date）。
 *     搜索范围由配置 scope 决定（webpage|document|paper|image|video|podcast），
 *     也支持查询前缀约定 "scope:paper 关键词" 临时切换范围。
 *   - MetasoFetchProvider（id: metaso-reader）：POST {baseURL}/reader，
 *     网页全文转 markdown → WebFetchResult.body（kind: text），
 *     web_fetch 工具可直接返回整页可读内容。
 *
 * 凭据：apiKey 字面量，或 apiKeyEnv（credential-ref：Web Models 页面管理的
 * credentials 域 > 启动环境变量）。没有 key 时 available()=false，
 * web_search 自动回落其他可用 provider（如 deepseek-official），不报错。
 *
 * provider 选择：安装后若存在多个 search provider，需在 patch 层显式配置
 *   - id: web
 *     config:
 *       searchProvider: metaso
 * （install.sh 在提供 key 时自动写入；fetch 无其他注册者，自动选中）。
 *
 * 配置（cordis.patch.yml 的 insert config 或 Web Models 设置页）：
 *   apiKey:            秘塔 API key（mk- 开头，与 apiKeyEnv 至少其一）
 *   apiKeyEnv:         环境变量名（默认 METASO_API_KEY）
 *   baseURL:           默认 https://metaso.cn/api/v1
 *   scope:             默认搜索范围（默认 webpage）
 *   includeSummary:    是否请求综合摘要（默认 true，映射为 content）
 *   includeRawContent: 是否抓取来源原文（默认 false）
 *   maxResults:        单次返回条数上限 1-100（默认 10，seam 还会按上限截断）
 */
import z from "@deepseek-ai/schemastery";
import { credentialRef } from "@deepseek-ai/dsh-credentials";
import { installSettingsSection, settingsNamespace } from "@deepseek-ai/dsh-settings";
import { launchEnvironmentOf } from "@deepseek-ai/dsh-launch-environment";
import { WebError } from "@deepseek-ai/dsh-web";

export const name = "web-search-metaso";
export const inject = ["web"];

export const METASO_PROVIDER_ID = "metaso";
export const METASO_READER_PROVIDER_ID = "metaso-reader";
export const METASO_DEFAULT_BASE_URL = "https://metaso.cn/api/v1";
export const METASO_DEFAULT_API_KEY_ENV = "METASO_API_KEY";
const METASO_SCOPES = ["webpage", "document", "paper", "image", "video", "podcast"];
const USER_AGENT = "dsh-web-search-metaso/0.1.0";
const WEB_SEARCH_METASO_SETTINGS_NAMESPACE = settingsNamespace("web-search-metaso");

export const Config = z.object({
  apiKey: z.string().role("secret"),
  apiKeyEnv: z.string().role("credential-ref").default(METASO_DEFAULT_API_KEY_ENV),
  baseURL: z.string(),
  scope: z.string(),
  includeSummary: z.boolean().default(true),
  includeRawContent: z.boolean().default(false),
  maxResults: z.number().step(1).min(1).max(100).default(10),
});

/** 解析本次搜索的 scope：支持 "scope:paper 关键词" 前缀临时切换；否则用配置默认。 */
function parseScope(configScope, query) {
  const m = /^scope:(webpage|document|paper|image|video|podcast)[\s:]+/.exec(query);
  if (m) return { scope: m[1], query: query.slice(m[0].length) };
  return { scope: METASO_SCOPES.includes(configScope) ? configScope : "webpage", query };
}

/** 一次 Metaso 搜索：纯检索 HTTP POST，不消耗模型调用。 */
class MetasoSearchProvider {
  constructor(resolveOptions) {
    this.resolveOptions = resolveOptions;
  }
  id = METASO_PROVIDER_ID;
  available() {
    const options = this.resolveOptions();
    return ((options.apiKey?.length ?? 0) > 0 || options.resolveApiKey !== void 0) && URL.canParse(options.baseURL);
  }
  async search(request, signal) {
    const options = this.resolveOptions();
    const apiKey = await resolveKey(options, signal, "Metaso search");
    throwIfAborted(signal, "Metaso search");
    const { scope, query } = parseScope(options.scope, request.query);
    const size = request.maxResults ?? options.maxResults ?? 10;
    const endpoint = `${options.baseURL}/search`;
    const body = {
      q: query,
      scope,
      includeSummary: options.includeSummary ?? true,
      includeRawContent: options.includeRawContent ?? false,
      size: Math.min(Math.max(Math.trunc(size), 1), 100),
      conciseSnippet: false,
    };
    options.recordRequest?.({ endpoint, body });
    throwIfAborted(signal, "Metaso search");
    let response;
    try {
      response = await fetch(endpoint, {
        method: "POST",
        redirect: "error",
        headers: {
          authorization: `Bearer ${apiKey}`,
          "content-type": "application/json",
          accept: "application/json",
          "user-agent": USER_AGENT,
        },
        body: JSON.stringify(body),
        ...(signal !== void 0 ? { signal } : {}),
      });
    } catch (error) {
      if (signal?.aborted === true || isAbortError(error)) throw aborted(signal, "Metaso search");
      throw new WebError(`Metaso search request failed: ${String(error)}`, "WEB_PROVIDER_ERROR", { cause: error });
    }
    if (!response.ok) {
      throw new WebError(await errorDetail(response, "Metaso search"), "WEB_PROVIDER_ERROR");
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new WebError(`Metaso returned an unprocessable response body: ${String(error)}`, "WEB_PROVIDER_ERROR", { cause: error });
    }
    const seen = /* @__PURE__ */ new Set();
    const sources = [];
    for (const item of data.webpages ?? []) {
      if (typeof item.link !== "string" || item.link.length === 0 || seen.has(item.link)) continue;
      seen.add(item.link);
      sources.push({
        url: item.link,
        ...(typeof item.title === "string" && item.title.length > 0 ? { title: item.title } : {}),
        ...(typeof item.snippet === "string" && item.snippet.length > 0 ? { snippet: item.snippet } : {}),
        ...(typeof item.date === "string" && item.date.length > 0 ? { publishedAt: item.date } : {}),
      });
    }
    return {
      ...(typeof data.summary === "string" && data.summary.length > 0 ? { content: data.summary } : {}),
      sources,
      truncated: false,
    };
  }
}

/** Metaso 网页阅读 provider：POST /reader，网页全文转 markdown 文本。 */
class MetasoFetchProvider {
  constructor(resolveOptions) {
    this.resolveOptions = resolveOptions;
  }
  id = METASO_READER_PROVIDER_ID;
  available() {
    const options = this.resolveOptions();
    return ((options.apiKey?.length ?? 0) > 0 || options.resolveApiKey !== void 0) && URL.canParse(options.baseURL);
  }
  async fetch(request, signal) {
    const options = this.resolveOptions();
    const apiKey = await resolveKey(options, signal, "Metaso reader");
    throwIfAborted(signal, "Metaso reader");
    const endpoint = `${options.baseURL}/reader`;
    const body = { url: request.url };
    let response;
    try {
      response = await fetch(endpoint, {
        method: "POST",
        redirect: "error",
        headers: {
          authorization: `Bearer ${apiKey}`,
          "content-type": "application/json",
          accept: "application/json",
          "user-agent": USER_AGENT,
        },
        body: JSON.stringify(body),
        ...(signal !== void 0 ? { signal } : {}),
      });
    } catch (error) {
      if (signal?.aborted === true || isAbortError(error)) throw aborted(signal, "Metaso reader");
      throw new WebError(`Metaso reader request failed: ${String(error)}`, "WEB_PROVIDER_ERROR", { cause: error });
    }
    if (!response.ok) {
      throw new WebError(await errorDetail(response, "Metaso reader"), "WEB_PROVIDER_ERROR");
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new WebError(`Metaso reader returned an unprocessable response body: ${String(error)}`, "WEB_PROVIDER_ERROR", { cause: error });
    }
    const content =
      (typeof data.markdown === "string" && data.markdown.length > 0) ? data.markdown
        : (typeof data.content === "string" && data.content.length > 0) ? data.content
          : (typeof data.title === "string" ? data.title : "");
    return {
      url: request.url,
      statusCode: response.status,
      body: { kind: "text", content },
      truncated: false,
    };
  }
}

/** 解析一次操作的凭据；缺失时抛 WEB_PROVIDER_CREDENTIAL_MISSING。 */
async function resolveKey(options, signal, label) {
  throwIfAborted(signal, label);
  if (options.apiKey !== void 0 && options.apiKey.length > 0) return options.apiKey;
  let resolved;
  try {
    resolved = await abortable(options.resolveApiKey?.() ?? Promise.resolve(void 0), signal);
  } catch (error) {
    if (signal?.aborted === true || isAbortError(error)) throw aborted(signal, label);
    throw new WebError(`${label} credential resolution failed: ${String(error)}`, "WEB_PROVIDER_ERROR", { cause: error });
  }
  if (resolved !== void 0 && resolved.length > 0) return resolved;
  throw new WebError(
    `${label} has no API key for "${options.apiKeyEnv ?? METASO_DEFAULT_API_KEY_ENV}"; store it through the credentials service, export it in the launching environment, or set a literal "apiKey" in the web-search-metaso config`,
    "WEB_PROVIDER_CREDENTIAL_MISSING",
  );
}

/** 从非 2xx 响应提取可读错误信息（error / error.message / message 字段，兜底 HTTP 状态）。 */
async function errorDetail(response, label) {
  let message = `${label} API error (HTTP ${response.status})`;
  try {
    const parsed = await response.json();
    const detail = typeof parsed.error === "string" ? parsed.error : parsed.error?.message ?? parsed.message;
    if (detail !== void 0 && detail.length > 0) message = detail;
  } catch {
    /* 保持默认信息 */
  }
  return message;
}

/** 将当前配置与环境投影为下一次操作的选项（每次操作入口快照，一次搜索不混两个配置段）。 */
function resolveOptions(ctx, config) {
  const apiKeyEnv = credentialRef(config.apiKeyEnv ?? METASO_DEFAULT_API_KEY_ENV);
  const literalApiKey = config.apiKey !== void 0 && config.apiKey.length > 0 ? config.apiKey : void 0;
  return {
    ...(literalApiKey === void 0 ? {} : { apiKey: literalApiKey }),
    resolveApiKey: async () => {
      const credentials = ctx.get("credentials");
      if (credentials !== void 0) return (await credentials.resolve(apiKeyEnv))?.value;
      const ambient = launchEnvironmentOf(ctx).get(apiKeyEnv);
      return ambient !== void 0 && ambient.value.length > 0 ? ambient.value : void 0;
    },
    apiKeyEnv,
    baseURL: config.baseURL ?? METASO_DEFAULT_BASE_URL,
    scope: config.scope ?? "webpage",
    includeSummary: config.includeSummary ?? true,
    includeRawContent: config.includeRawContent ?? false,
    maxResults: config.maxResults ?? 10,
    recordRequest: (request) => {
      ctx.get("agents")?.currentInitiator()?.session.append("web/metaso-search-request", request);
    },
  };
}

/** 注册 Metaso 搜索与阅读 provider 到 ctx.web。 */
export function apply(ctx, config) {
  let current = () => config;
  installSettingsSection(ctx, WEB_SEARCH_METASO_SETTINGS_NAMESPACE, Config, config, {
    setSource: (source) => {
      current = source;
    },
    onChange: () => {},
  });
  const resolve = () => resolveOptions(ctx, current());
  ctx.web.registerSearchProvider(new MetasoSearchProvider(resolve));
  ctx.web.registerFetchProvider(new MetasoFetchProvider(resolve));
}

/** 将异步预检与调用方取消竞争：abort 后挂接的处理器继续观察，避免未处理拒绝。 */
function abortable(operation, signal) {
  if (signal === void 0) return operation;
  if (signal.aborted) return Promise.reject(aborted(signal));
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      reject(aborted(signal));
    };
    signal.addEventListener("abort", onAbort, { once: true });
    operation.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", onAbort);
        reject(new Error(String(error).replace(/^Error: /u, ""), { cause: error }));
      },
    );
  });
}

/** 调用方已取消时抛出稳定的取消错误。 */
function throwIfAborted(signal, label) {
  if (signal?.aborted === true) throw aborted(signal, label);
}

/** 构建 provider 的稳定取消错误，保留调用方 reason。 */
function aborted(signal, label = "Metaso") {
  return new WebError(`${label} aborted`, "WEB_ABORTED", { cause: signal?.aborted === true ? signal.reason : void 0 });
}

/** fetch/AbortSignal 的取消，统一为 WEB_ABORTED。 */
function isAbortError(error) {
  return error instanceof DOMException && error.name === "AbortError";
}
