# dsh 插件开发指南

本仓库管理基于 [Cordis](https://github.com/cordiverse/cordis) 框架的 dsh 插件。
**权威上游**：官方文档站 [DeepSeek Harness 开发文档](https://deepseek-harness.github.io/deepseek-harness/develop/basic/)
（技术预览，对应最新源码；本机 0.1.0 已实测支持本文所述 bundle 机制）。
dsh 插件分两种半区（half），可以只有其一，也可以双半齐全：

| 半区 | 运行位置 | 形态 |
|---|---|---|
| Host half | Node（dsh 进程内） | Cordis 插件：导出 name + apply(ctx) |
| Client half | 浏览器（web 页面内） | `window.__ModuleLoader__.load` 注册的 CJS 模块 |

## 1. 包结构

每个插件是一个 npm 包，位于 `packages/<name>/`：

```
packages/<name>/
├── package.json   # 元数据 + dsh.client 客户端声明 + exports["./client"]
├── index.js       # Host half（可选，纯 client 插件可省略）
├── client.js      # Client half（可选，纯 host 插件可省略）
├── install.sh     # 一键安装脚本（由 scripts/package.sh 打进 tarball）
├── reapply-lan-patches.sh  # 升级恢复脚本（可选）
└── README.md      # 插件说明
```

## 2. package.json 规范

```json
{
  "name": "dsh-my-plugin",
  "version": "0.1.0",
  "type": "module",
  "main": "index.js",
  "exports": {
    ".": "./index.js",
    "./client": "./client.js",
    "./package.json": "./package.json"
  },
  "dsh": {
    "client": {
      "inject": [],
      "platform": "web",
      "immediately": true
    }
  }
}
```

- **`exports["./client"]`**：客户端入口。dsh 的 Node 侧会扫描启用列表中的 web `dsh.client` 包，解析该导出、把构建产物哈希进启动图（boot graph），并在 `/plugins/<name>/client.js` 提供（带 source map）。
- **`dsh.client`**：声明这是一个浏览器端插件包。
  - `inject`：声明的浏览器服务（与 apply 收到的 ctx 白名单对应）。
  - `platform`：`"web"`。
  - `immediately`：装载策略。

## 3. Host half（index.js）

Cordis 插件两种写法：

```js
// 函数形式（无依赖声明）
export const name = "my-plugin";
export function apply(ctx) {
  ctx.logger?.info?.("[my-plugin] active");
  return () => { /* 卸载清理 */ };
}
```

```js
// 对象形式（声明 inject 依赖）
export const name = "my-plugin";
export const inject = ["someService"];
export const apply = {
  apply(ctx) { /* ctx.someService 可用 */ },
};
```

要点：
- `apply(ctx)` 的返回值若是函数，在插件 fiber 释放时执行（事件监听、定时器在此清理）。
- `inject` 告诉 Cordis 哪些服务必须先存在。
- 宿主端可访问 `ctx.logger`、`ctx.fs`、`ctx.web`、`ctx.bash` 等服务。

## 4. Client half（client.js）

浏览器端模块系统是**惰性 CJS 表**：脚本执行只注册 factory，副作用在模块物化（materialize）时运行。

```js
window.__ModuleLoader__.load({
  id: "my-plugin",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    // 浏览器端副作用（polyfill、样式注入等）放这里，物化时执行
    var name = "my-plugin";
    var inject = [];
    function apply(ctx) {
      ctx.logger?.info?.("[my-plugin] active: browser half");
    }
    exports.name = name;
    exports.inject = inject;
    exports.apply = apply;
    return module.exports;
  }
});
```

要点：
- **必须导出 `name` / `inject` / `apply`**：dsh 0.1.0-rc.6 起组合装载要求浏览器模块导出函数或带 apply 的对象，否则报 `invalid plugin ... received object`。
- `require` 同步解析顺序：平台种子词 → 已物化记录 → 壳静态注册 → 已注册 factory → 启动图外部脚本。
- 模块 ID（`id`）与包名一致；`<id>/client` 与裸 id 解析到同一导出。

## 5. 组合接入（如何让 dsh 加载插件）

> 权威参考：官方文档 [第一个插件](https://deepseek-harness.github.io/deepseek-harness/develop/basic/)、
> [打包与安装插件](https://deepseek-harness.github.io/deepseek-harness/develop/basic/publish)、
> [Cordis 框架教程](https://deepseek-harness.github.io/deepseek-harness/develop/cordis-tutorial/)。

### 5.1 两个概念：组合包（bundle）与 profile

- **组合包（bundle）**：附带一个配置层的 npm 包。manifest 在 package.json 的 `dsh` 键下声明：

```json
"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
```

包内 `cordis.patch.yml` 就是一层 patch（与 `--patch` overlay 同格式），区别是插件行按**包名**引用
（不是相对源码路径），由 Loader 双锚点解析（dsh 安装目录 → profile node_modules）：

```yaml
- insert:
    - id: my-plugin
      name: dsh-my-plugin
```

- **profile**：`$DSH_HOME/profiles/<name>` 目录，`package.json` 的 `dsh.profile.bundles` 列出有序
组合包。由 `dsh plugin` 自动创建和维护，无需手写。

没有 `dsh.bundle` 声明的包仍可安装，但只作为普通依赖：`dsh plugin` 会警告且不激活任何层。

### 5.2 官方安装流（推荐）

```bash
dsh plugin --profile web add ./dsh-my-plugin   # 相对路径自动锚定调用目录
```

首次使用自动初始化 profile（web 模板 = `@deepseek-ai/dsh-base` + `@deepseek-ai/dsh-web-app`），
pnpm 链接该包，reconcile 时发现 `dsh.bundle` 声明即追加进 `dsh.profile.bundles`。
`remove` 同时移除依赖与对应层。本仓库 tarball 的 `install.sh` 已优先走此流（失败回退复制+手动接线）。

### 5.3 层顺序与 patch 语义（易踩坑）

生效配置在空根上按序叠加：**bundles（按列表顺序）→ profile 的 cordis.patch.yml → home 级
`$DSH_HOME/cordis.patch.yml` → 每个 `--patch` overlay（按 argv 顺序）**。

- 后应用的层按行胜出，**patch 整行替换目标行的整个 `config` 值**，不是深度合并各键——
  覆盖某行时必须重述它需要的每一个键。
- 用户可在自己 profile 的 patch 层覆盖你的行，无需改动你的包——所以给用户大概率会保留的
  配置提供默认值。
- 内置组合包（`@deepseek-ai/dsh-base` 等）始终从 dsh 安装目录解析；pnpm 只管理树外包。

### 5.4 验证

```bash
dsh --profile web --dump-config   # 应看到 "# == dsh-my-plugin" 层与 insert 行
```

## 6. 本地开发与调试

- 本仓库内修改后跑 `bash scripts/build.sh` 做语法/结构校验。
- 本机快速迭代：复制到 `~/.dsh/profiles/node_modules/<name>/`，接线后刷新页面；客户端插件有 HMR 通道（dsh-client-hmr），改 client.js 后页面自动更新。
- 动态实验：会话里用 `cordis_define` / `cordis_run` 工具可在不落盘的情况下试跑插件，但动态插件**不保存、重启即失**，正式化必须走本仓库的常规开发流程。

## 7. 新插件脚手架

```bash
bash scripts/new-plugin.sh my-cool-plugin "描述文字"
```

生成 `packages/my-cool-plugin/` 后编辑实现。发布分发见 [publishing.md](publishing.md)。

## 8. 防崩检查清单（必读，MR-022/023 事故教训）

> 背景：memory-recall-dsh 插件曾因 manifest 契约缺失导致 dsh web **启动即崩、挂机约 3 小时**
> （缺 `dsh.client.platform` → 插件树组合失败；浏览器端 bundle 非 classic script → HARNESS 加载失败）。
> 下述检查已固化进本仓库工具链，新插件从脚手架生成即自带。

**开发 → 安装 → 激活，按顺序过一遍：**

1. **契约预检**（已集成进 `scripts/build.sh`，也可单独跑）：
   ```bash
   node scripts/preflight.mjs packages/<name>
   ```
   校验：`dsh.client.platform` 为非空字符串（web profile 只接受 `"web"`）、
   `exports["./client"]` 存在且指向 bundle、bundle 无顶层 `import/export`
   （classic script 要求）+ 含 `__ModuleLoader__.load` 注册 + 包名一致。

2. **bundle 是生成物就配生成器**：`client.js` 勿手改，改库文件后重新生成
   （如 memory-recall-dsh 的 `build-bundle.mjs` 模式），并跑 build.sh 防漂移。

3. **全量测试**：插件自带的 `node --test` 全绿后再分发。

4. **冒烟试启动**（防"启动即崩"，`install.sh --smoke`）：
   在隔离的 headless profile 真实 boot 插件组合（约 10-30s）；命中
   `client-modules` / `plugin tree failed` / `cannot resolve entry` 关键字
   判定为插件问题（exit 1），正式服务不受影响。`--restart` 内置冒烟，
   插件问题自动中止重启。

5. **激活与回滚**：
   - 在**终端**执行 `bash install.sh --restart`；⚠️ **严禁在 agent（dsh 会话）
     内部重启宿主 dsh web 进程**——agent 就跑在宿主进程里，重启即自杀；
   - dsh web 无 systemd/cron 托管，崩溃无人拉起（曾因此挂机 3 小时），
     如需常驻建议补 systemd user unit（`Restart=on-failure` + `StartLimitBurst=3`）；
   - 回滚：`bash install.sh --uninstall` + 重启 dsh。

6. **装后验证**：页面 200；`/plugins/<id>/client.js` 返回 200；boot 日志无
   `client-modules:` 报错；新会话里插件行为出现。