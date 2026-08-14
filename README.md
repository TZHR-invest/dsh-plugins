# dsh-plugins

dsh（DeepSeek Harness）插件 Monorepo：自研插件统一管理、脚手架与一键分发。

## 仓库结构

```
dsh-plugins/
├── packages/            # 插件包（每个目录是一个独立 npm 包）
│   └── dsh-lan-access/  # 局域网访问支持（randomUUID polyfill + 0.0.0.0 + 特权围栏）
├── templates/plugin/    # 新插件脚手架模板
├── scripts/
│   ├── new-plugin.sh    # 从模板创建新插件包
│   ├── build.sh         # 校验全部插件包（语法/JSON/结构）
│   └── package.sh       # 生成一键安装 tarball 到 dist/
├── docs/
│   ├── development.md   # 插件开发指南（机制/包规范/接线/调试）
│   └── publishing.md    # 分发指南（tarball 安装/升级恢复）
└── dist/                # 分发产物（构建生成，不入库）
```

## 快速开始

```bash
# 新插件
bash scripts/new-plugin.sh my-plugin "描述"

# 校验全部插件
bash scripts/build.sh

# 生成分发 tarball
bash scripts/package.sh
# -> dist/<name>-install.tar.gz，拷到目标机解压后 bash install.sh --restart
```

## 插件一览

| 包 | 说明 | 半区 | 分发 |
|---|---|---|---|
| dsh-lan-access | 局域网明文 HTTP 访问支持：浏览器 crypto.randomUUID polyfill、0.0.0.0 绑定、特权围栏放行 | client + host | tarball 一键安装 |

## 文档

- [开发指南](docs/development.md)：Host/Client 插件机制、package.json 规范、组合接线、调试
- [分发指南](docs/publishing.md)：tarball 生成、目标机安装、dsh 升级后恢复

> 安全提醒：lan-access 会把 dsh web 绑定到 0.0.0.0，任何可访问该端口的设备都能驱动 agent 执行命令，仅限可信内网使用。
