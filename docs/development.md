# dsh 插件开发指南

本仓库管理基于 [Cordis](https://github.com/cordiverse/cordis) 框架的 dsh 插件。
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

组合按层叠加（bundle → profile patch → home patch → --patch）：

1. **安装到 profile**（目标机执行）：`dsh plugin --profile web add dsh-my-plugin`（转发给 profile 的 pnpm），或直接把包复制到 `~/.dsh/profiles/node_modules/`。
2. **接线**：在 `~/.dsh/profiles/web/cordis.patch.yml`（或 `~/.dsh/cordis.patch.yml`）追加：

```yaml
- insert:
    - id: my-plugin
      name: 'dsh-my-plugin'
```

3. **验证**：`dsh --profile web --dump-config` 查看组合后的配置树；重启后浏览器控制台看插件日志。

## 6. 本地开发与调试

- 本仓库内修改后跑 `bash scripts/build.sh` 做语法/结构校验。
- 本机快速迭代：复制到 `~/.dsh/profiles/node_modules/<name>/`，接线后刷新页面；客户端插件有 HMR 通道（dsh-client-hmr），改 client.js 后页面自动更新。
- 动态实验：会话里用 `cordis_define` / `cordis_run` 工具可在不落盘的情况下试跑插件，但动态插件**不保存、重启即失**，正式化必须走本仓库的常规开发流程。

## 7. 新插件脚手架

```bash
bash scripts/new-plugin.sh my-cool-plugin "描述文字"
```

生成 `packages/my-cool-plugin/` 后编辑实现。发布分发见 [publishing.md](publishing.md)。
