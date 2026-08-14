/**
 * dsh-vision — 视觉读图工具插件（Host half only）。
 *
 * 给 agent 注册一个 `vision` 工具：把本地图片 base64 后发送到用户配置的
 * OpenAI 兼容视觉模型端点，返回文字描述。用于当前会话模型不支持图像输入的场景。
 *
 * 插件没有任何内置默认值：provider（baseURL）、凭据（apiKey / apiKeyEnv）、
 * 模型（defaultModel / visionModels）全部由用户配置。未配置完整时插件正常
 * 激活但不会注册 vision 工具（日志给出缺项提示），绝不导致宿主崩溃。
 *
 * 配置（cordis.patch.yml 的 insert config）：
 *   baseURL:       OpenAI 兼容 chat/completions 端点（必填）
 *   apiKey:        API key（与 apiKeyEnv 至少其一）
 *   apiKeyEnv:     环境变量名（与 apiKey 至少其一；有该环境变量时也尝试
 *                  ~/.dsh/.credentials.yaml 中的同名键）
 *   defaultModel:  默认视觉模型（必填）
 *   visionModels:  cross_check=true 时的核对模型列表（可选，未配置时
 *                  cross_check 不可用）
 *   maxTokens:     可选；不配置则请求不带 max_tokens（端点默认）
 *   maxImageBytes: 可选；不配置则不限制图片大小
 *
 * 网络经 curl 子进程发出（继承宿主代理环境变量，并避开 Cloudflare 对
 * urllib/undici 默认 UA 的 403 code 1010 拦截）。
 */
import { defineTool } from "@deepseek-ai/dsh-tools";
import z from "@deepseek-ai/schemastery";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const name = "dsh-vision";

export const inject = ["tools", "systemPrompt"];

// 本 fork 的 schemastery：不调用 .required() 即字段可选（未配置时为 undefined），
// 且无 .default() 就无默认值——每个字段都由用户配置决定。
export const Config = z.object({
  baseURL: z.string(),
  apiKey: z.string(),
  apiKeyEnv: z.string(),
  defaultModel: z.string(),
  visionModels: z.array(z.string()),
  maxTokens: z.number(),
  maxImageBytes: z.number(),
});

/** 返回缺失的必填项列表；配置完整返回空数组。 */
function missingConfig(config) {
  const missing = [];
  if (!config.baseURL) missing.push("baseURL");
  if (!config.defaultModel) missing.push("defaultModel");
  if (!config.apiKey && !config.apiKeyEnv) missing.push("apiKey 或 apiKeyEnv");
  return missing;
}

function resolveApiKey(config) {
  if (config.apiKey) return config.apiKey;
  if (config.apiKeyEnv) {
    if (process.env[config.apiKeyEnv]) return process.env[config.apiKeyEnv];
    try {
      const text = readFileSync(join(homedir(), ".dsh", ".credentials.yaml"), "utf8");
      const m = new RegExp("^" + config.apiKeyEnv + ":\\s*(\\S+)", "m").exec(text);
      if (m) return m[1];
    } catch {
      /* 无凭据文件 */
    }
  }
  return "";
}

/** 调一次视觉模型，返回描述文本。curl 子进程发出（继承代理 env）。 */
function callVision(config, model, b64, question, signal) {
  const base = config.baseURL.replace(/\/+$/, "");
  const url = /\/chat\/completions$/.test(base)
    ? base
    : base + "/chat/completions";
  const key = resolveApiKey(config);
  if (!key) {
    throw new Error(
      "dsh-vision: 凭据解析失败——配置 apiKey，或设置环境变量 " + config.apiKeyEnv +
        "（或写入 ~/.dsh/.credentials.yaml 同名键）",
    );
  }
  const body = {
    model,
    messages: [{
      role: "user",
      content: [
        { type: "text", text: question },
        { type: "image_url", image_url: { url: "data:image/png;base64," + b64 } },
      ],
    }],
  };
  if (config.maxTokens !== void 0) body.max_tokens = config.maxTokens;
  const cmd = ["curl", "-s", "-m", "150",
    "-H", "Authorization: Bearer " + key,
    "-H", "Content-Type: application/json",
    "--data", JSON.stringify(body), url];

  return new Promise((resolve, reject) => {
    const proc = spawn("curl", cmd, {
      signal,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    proc.stdout.on("data", (d) => { out += d; });
    proc.stderr.on("data", (d) => { err += d; });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`dsh-vision: curl exit ${code}: ${String(err).slice(0, 200)}`));
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(out);
      } catch {
        reject(new Error("dsh-vision: 非 JSON 响应: " + out.slice(0, 200)));
        return;
      }
      const choice = parsed.choices?.[0];
      if (!choice) {
        reject(new Error("dsh-vision: API 错误: " + JSON.stringify(parsed).slice(0, 300)));
        return;
      }
      const msg = choice.message ?? {};
      const content = String(msg.content ?? "").trim();
      if (content) {
        resolve(content);
        return;
      }
      // reasoning 模型 content 为空时回退到推理尾部
      const reasoning = String(msg.reasoning ?? "").trim();
      resolve(reasoning ? reasoning.slice(-500) + " [content empty, showing reasoning tail]" : "(empty reply)");
    });
  });
}

function applyTool(ctx, config) {
  ctx.tools.register(defineTool({
    name: "vision",
    description:
      "Describe a local image file via the configured OpenAI-compatible vision model endpoint " +
      "(default model " + config.defaultModel + "). Returns a text description; use it when " +
      "you need image content that the current model cannot ingest directly " +
      "(e.g. screenshots, diagrams, photos).",
    parameters: {
      image_path: {
        type: "string",
        required: true,
        description: "Path to the image file (PNG/JPEG/WebP/GIF).",
      },
      question: {
        type: "string",
        description: "Optional custom question. Default: detailed description of all visible text, colors, shapes, layout.",
      },
      model: {
        type: "string",
        description: "Optional vision model id. Default: " + config.defaultModel + ".",
      },
      cross_check: {
        type: "boolean",
        description: "Optional: when true, ask all configured visionModels and merge their answers (guards against hallucination). Default false.",
      },
    },
    output: {
      schema: {
        type: "object",
        additionalProperties: false,
        properties: {
          model: { type: "string", required: true },
          endpoint: { type: "string", required: true },
          description: { type: "string", required: true },
        },
      },
      render: (_args, value) => [{ type: "text", text: value.description }],
      presentationMeta: (_args, value) => value,
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      let buf;
      try {
        buf = await readFile(args.image_path, { signal: exec.signal });
      } catch (e) {
        throw new Error("dsh-vision: 无法读取图片 " + args.image_path + ": " + e.message);
      }
      if (buf.length === 0) throw new Error("dsh-vision: 图片文件为空: " + args.image_path);
      if (config.maxImageBytes !== void 0 && buf.length > config.maxImageBytes) {
        throw new Error(
          `dsh-vision: 图片过大 (${Math.round(buf.length / 1024)} KB)，上限 ${Math.round(config.maxImageBytes / 1024 / 1024 * 10) / 10} MB`,
        );
      }
      const b64 = buf.toString("base64");
      const question = args.question ||
        "请详细描述这张图片的内容，包括所有可见的文字、颜色、形状、布局和细节。";
      let models;
      if (args.cross_check) {
        if (!config.visionModels || config.visionModels.length === 0) {
          throw new Error("dsh-vision: cross_check 需要配置 visionModels 列表（插件配置）");
        }
        models = config.visionModels;
      } else {
        models = [args.model || config.defaultModel];
      }

      const results = [];
      for (const model of models) {
        results.push({
          model,
          description: await callVision(config, model, b64, question, exec.signal),
        });
      }
      if (results.length === 1) {
        return {
          model: results[0].model,
          endpoint: config.baseURL,
          description: results[0].description,
        };
      }
      return {
        model: results.map((r) => r.model).join("+"),
        endpoint: config.baseURL,
        description: results.map((r) => "【" + r.model + "】" + r.description).join("\n\n"),
      };
    },
    presentResult(_args, result) {
      if (result.isError) return void 0;
      const meta = result.meta;
      if (meta === void 0 || typeof meta.description !== "string") return void 0;
      return {
        card: "generic",
        title: "Vision",
        kind: "vision",
        model: meta.model,
        endpoint: meta.endpoint,
        description: meta.description,
        content: [{ type: "text", text: meta.description }],
      };
    },
    presentCall(args) {
      return {
        card: "generic",
        title: "Vision " + args.image_path,
        kind: "vision",
        locations: [{ path: args.image_path }],
      };
    },
  }));
}

export function apply(ctx, config) {
  const missing = missingConfig(config);
  if (missing.length > 0) {
    ctx.logger?.warn?.(
      "[dsh-vision] 未配置 " + missing.join("、") +
        "，vision 工具未注册。请在 cordis.patch.yml 的 dsh-vision 配置段补全后重启（见 README）。",
    );
    return () => {};
  }
  ctx.logger?.info?.("[dsh-vision] active: vision tool registered (endpoint=" + config.baseURL + ")");
  ctx.systemPrompt.section({
    name: "tool:vision",
    order: 500,
    text: "The vision tool reads a local image file and returns a text description via the configured " +
      "OpenAI-compatible vision model (" + config.defaultModel + "). Use it when you need to see " +
      "image content the current model cannot ingest directly.",
  });
  applyTool(ctx, config);
  return () => {
    /* 工具随 registry 作用域自动注销；无需额外清理 */
  };
}
