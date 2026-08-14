# __PACKAGE_NAME__

__DESCRIPTION__（dsh 插件）。

## 包结构

| 文件 | 作用 |
|---|---|
| package.json | 包元数据 + `dsh.client` 客户端插件声明 |
| index.js | 宿主端（Host half）：Cordis 插件，导出 name / apply(ctx) |
| client.js | 浏览器端（Client half）：`window.__ModuleLoader__.load` 注册 |

## 安装到 dsh

方式一（本机开发）：复制本目录到 `~/.dsh/profiles/node_modules/`，并在
`~/.dsh/profiles/web/cordis.patch.yml` 追加接线：

```yaml
- insert:
    - id: __PLUGIN_ID__
      name: '__PACKAGE_NAME__'
```

方式二（其他机器分发）：仓库根目录执行 `bash scripts/package.sh`，把生成的
`dist/__PACKAGE_NAME__-install.tar.gz` 拷到目标机，解压后 `bash install.sh --restart`。

## 验证

- 重启 dsh web 后浏览器访问，控制台应看到 `[__PLUGIN_ID__] active` 日志
- 目标机安装验证：`curl http://<IP>:3080/plugins/__PACKAGE_NAME__/client.js` 返回 200
