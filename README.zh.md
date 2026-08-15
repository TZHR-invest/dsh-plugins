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
| memory-recall-dsh | Memory Recall 长期记忆插件：6 工具（store/search/profile/list/forget/update）+ 自动召回注入 + 自动捕获 | host | 自打包 tarball（见下） |

## 外部插件索引（只登记，不复制）

memory-recall-dsh 属于 **memory-recall 项目**（后端 + 测试连真实后端，代码单源于
`memory_recall` 仓库 `apps/api/src/plugins/dsh/`），本仓库**不复制其代码**
（双源会漂移，教训见 memory_recall MR-013 同类问题），仅在此登记入口：

- 源码与开发：`memory_recall/apps/api/src/plugins/dsh/`（24 测试含真实后端集成用例）
- 版本：1.2.0（memory_update 版本化修正工具，ADR-0009）
- 安装/分发：插件目录内 `bash package.sh` 生成自包含 tarball
  （`dist/memory-recall-dsh-install.tar.gz`，含契约预检），目标机
  `tar xzf` 后 `bash install.sh --api-key xxx --backend-url http://<后端>:8000`，
  激活 `bash install.sh --restart`（内置 headless 冒烟，插件问题自动中止）
- 后端地址由安装时配置（自部署远程服务器，不固定）

## 文档

- [开发指南](docs/development.md)：Host/Client 插件机制、package.json 规范、组合接线、调试
- [分发指南](docs/publishing.md)：tarball 生成、目标机安装、dsh 升级后恢复

> 安全提醒：lan-access 会把 dsh web 绑定到 0.0.0.0，任何可访问该端口的设备都能驱动 agent 执行命令，仅限可信内网使用。
