# __PACKAGE_NAME__

__DESCRIPTION__（dsh 插件）。

## 包结构

| 文件 | 作用 |
|---|---|
| package.json | 包元数据 + `dsh.client` 客户端插件声明 |
| index.js | 宿主端（Host half）：Cordis 插件，导出 name / apply(ctx) |
| client.js | 浏览器端（Client half）：`window.__ModuleLoader__.load` 注册 |

## 安装到 dsh

标准组合包（bundle）：本包声明 `dsh.bundle.patch`，官方 `dsh plugin add`
会自动 pnpm 链接并追加进 `dsh.profile.bundles` 层列表：

```bash
dsh plugin --profile web add <本包目录>
# 或从包内 tarball 分发：bash scripts/package.sh 生成 dist/*-install.tar.gz
# 目标机解压后 bash install.sh --restart（内部优先走官方 dsh plugin add）
```

旧式手动接线（`--patch` overlay 或 profile patch 的 insert）依然可用，
但 bundle 流是推荐方式。

## 验证

- 重启 dsh web 后浏览器访问，控制台应看到 `[__PLUGIN_ID__] active` 日志
- 目标机安装验证：`curl http://<IP>:3080/plugins/__PACKAGE_NAME__/client.js` 返回 200