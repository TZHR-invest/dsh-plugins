/**
 * dsh 插件安装前契约预检（防 MR-022/MR-023 重演）
 *
 * 用法: node preflight.mjs <插件目录>
 * 退出码: 0 = 全部通过；1 = 存在失败项
 *
 * 检查项（dsh client-modules 加载器的硬性要求，缺一即 boot 崩溃）：
 *   1. package.json 可解析，main 入口存在；
 *   2. 若声明 `dsh.client`：`dsh.client.platform` 必须是非空字符串
 *      （web profile 只接受 "web"）——缺失会抛
 *      "dsh.client.platform must be a string"，整个插件树加载失败，dsh 启动即退出（MR-022）；
 *   3. 声明 `dsh.client` 时 `exports["./client"]` 必须存在且文件存在
 *      （client bundle 路径，缺失同样组合失败）；
 *   4. bundle 文件（exports["./client"] 指向）必须是 classic script：
 *      不含顶层 `import`/`export`（否则浏览器 SyntaxError，MR-023），
 *      且包含 `__ModuleLoader__.load` 注册（否则 HARNESS 报
 *      "loaded without registering"）。
 *
 * 注意：bundle 通常是生成产物（如 build-bundle.mjs 生成），勿手改；
 * 改动库文件后需重新生成并重跑本预检。
 */
import fs from "node:fs";
import path from "node:path";

const dir = process.argv[2];
if (!dir) {
  console.error("用法: node preflight.mjs <插件目录>");
  process.exit(2);
}

let failed = false;
const report = (ok, msg) => {
  console.log(`  ${ok ? "[PASS]" : "[FAIL]"} ${msg}`);
  if (!ok) failed = true;
};

// 1. package.json
const pkgPath = path.join(dir, "package.json");
let pkg = null;
try {
  pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  report(true, `package.json 可解析（${pkg.name ?? "<无 name>"} v${pkg.version ?? "?"}）`);
} catch (error) {
  report(false, `package.json 解析失败: ${error.message}`);
  process.exit(1);
}

const mainEntry = pkg.main ?? "index.js";
report(
  fs.existsSync(path.join(dir, mainEntry)),
  `main 入口存在（${mainEntry}）`,
);

// 2. dsh.client 声明
const dshClient = pkg.dsh?.client;
if (dshClient === undefined) {
  report(true, "未声明 dsh.client（服务端纯插件，不参与浏览器 bundle）");
} else {
  const platform = dshClient.platform;
  report(
    typeof platform === "string" && platform.length > 0,
    `dsh.client.platform 为非空字符串（当前: ${JSON.stringify(platform)}，web profile 需 "web"）`,
  );
  if (typeof platform === "string" && platform.length > 0) {
    const platformOk = platform === "web" || platform === "headless";
    report(platformOk, `platform 取值合法（${platform} ∈ web/headless）`);
  }

  // 3. exports["./client"]
  const clientExport = pkg.exports?.["./client"];
  if (typeof clientExport !== "string") {
    report(false, '声明了 dsh.client 但 exports["./client"] 缺失（必须指向 bundle 文件）');
  } else {
    const bundlePath = path.join(dir, clientExport);
    const exists = fs.existsSync(bundlePath);
    report(exists, `exports["./client"] 指向存在（${clientExport}）`);
    if (exists) {
      const content = fs.readFileSync(bundlePath, "utf8");
      // 4. classic script 形态
      const topLevelModuleSyntax = /^\s*(?:import|export)\s/m.test(content);
      report(!topLevelModuleSyntax, `bundle 无顶层 import/export（classic script 要求，MR-023）`);
      report(content.includes("__ModuleLoader__.load"), `bundle 含 __ModuleLoader__.load 注册`);
      report(
        content.includes(`"${pkg.name}"`) || content.includes(`id: "${pkg.name}"`),
        `bundle 注册 id 与包名一致（${pkg.name}）`,
      );
    }
  }
}

// 5. 生成产物提醒：bundle 是 build-bundle.mjs 的生成物时，应带生成标记（勿手改）
const hasBuilder = fs.existsSync(path.join(dir, "build-bundle.mjs"));
if (hasBuilder && typeof pkg.exports?.["./client"] === "string") {
  const bundlePath = path.join(dir, pkg.exports["./client"]);
  if (fs.existsSync(bundlePath)) {
    const bundle = fs.readFileSync(bundlePath, "utf8");
    report(
      bundle.includes("build-bundle.mjs") || bundle.includes("自动生成"),
      "bundle 带生成标记（build-bundle.mjs 产物，改库后须重新生成）",
    );
  }
}

console.log(failed ? "== 预检未通过：请修复后再安装，否则 dsh 可能启动即崩 ==" : "== 预检通过 ==");
process.exit(failed ? 1 : 0);
