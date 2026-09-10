# 分发指南（本地 tarball 一键安装）

目标：把仓库里的插件包分发到其他机器/环境的 dsh 上，一条命令装好。

## 0. 三条分发渠道与「必须升版本」纪律（2026-09-11 定案，先读这条）

本仓库的插件同时经 **三条渠道** 到达用户，三者必须同版本、同内容：

| 渠道 | 载体 | 谁在用 |
|---|---|---|
| npm | `npm i <包名>` | 外部/社区用户 |
| tarball | `dist/<name>-install.tar.gz` | 装机脚本、其他机器 |
| 仓库源码 | `packages/<name>/` | 本仓开发 |

**⚠️ 血泪教训（2026-09-11，一次查出 4 处）**：多个修复提交只改了代码、**没升 `version`**，
而 **npm 不允许覆盖已发布版本** → 仓库修好了，npm 上仍是坏代码。实测三例：

- `dsh-lan-gateway`：npm 版 `token-gate.js` 与修复前版本 md5 完全一致 → dsh 0.1.2+ 上 LAN 访问被旧门卫彻底挡死
- `dsh-web-search-metaso`：npm 版仍 `import installSettingsSection`（0.1.2 已移除该 API）→ 装上即崩溃
- `dsh-vision-tool`：npm 版缺 `apiKeyHeader` → opencodex 鉴权无法配置

**纪律：任何修改插件行为的提交，都必须同时升 `packages/<name>/package.json` 的 `version`；
只改文档/脚本注释可不升。** 版本号是唯一能让外部用户拿到修复的手段。

**发布后必须核对产物内容**（不要只看 `npm publish` 成功）：

```bash
npm publish                                   # 返回 PUT 202 = 异步受理，不是最终成功
# 轮询到 tarball 可下载（元数据约 3 分钟、tarball 约 4-5 分钟才就绪，期间 404 属正常）
curl -sI https://registry.npmjs.org/<pkg>/-/<pkg>-<ver>.tgz | head -1
# 解包与仓库逐文件对 md5 —— 这一步才是"发布成功"的判据
tar xzf <pkg>-<ver>.tgz && md5sum package/index.js packages/<name>/index.js
```

升版本后记得 **重新跑 `bash scripts/package.sh`**：tarball 里的 `package.json` 版本号
否则会停在上一次打包时的旧值，与 npm / 仓库不一致。

## 1. 生成分发产物

```bash
bash scripts/package.sh
```

为每个含 `install.sh` 的插件包生成 `dist/<name>-install.tar.gz`。
以 dsh-lan-access 为例，tarball 内含：

```
dsh-lan-access-install/
├── install.sh                 # 一键安装脚本（幂等）
├── reapply-lan-patches.sh     # 升级恢复脚本（自动拷到目标机 ~/.dsh/）
├── README.md
└── dsh-lan-access/            # 插件源码（package.json / index.js / client.js）
```

## 2. 目标机安装（三步）

```bash
scp dist/dsh-lan-access-install.tar.gz user@目标机:~/
cd ~ && tar xzf dsh-lan-access-install.tar.gz
cd dsh-lan-access-install && bash install.sh --restart
```
`install.sh` 自动完成全部接线（标准组合包，官方 bundle 流优先）：
1. webserver 绑定 0.0.0.0（写 `~/.dsh/cordis.patch.yml`）
2. 插件源码 → `~/.dsh/plugins/<name>/`（用户层，升级不丢）
3. **官方流接线**：`dsh plugin --profile web add <插件目录>` —— 自动 pnpm 链接、
   追加进 `dsh.profile.bundles` 层列表（包声明了 `dsh.bundle.patch`），并清理
   profile patch 里的旧手动接线行
4. dsh/pnpm 不可用或 add 失败时**回退**：复制到 `~/.dsh/profiles/node_modules/<name>/`
   + profile patch 手动 insert
5. 特权围栏补丁（`dsh-client-connection` 一行补丁，唯一的 node_modules 修改）

> 若目标机已有旧式手动接线（profile patch 的 insert 行），install.sh 检测到
> bundle 已接线后会自动移除旧行，避免重复 insert。

| 命令 | 作用 |
|---|---|
| `bash install.sh` | 安装/补齐（幂等） |
| `bash install.sh --check` | 只检查状态，不改文件 |
| `bash install.sh --restart` | 安装后重启 dsh web 并 curl 验证 |

## 2.5 直接走官方流（不走 tarball）

如果目标机可以直接访问插件源码（git clone / 挂载目录），官方 `dsh plugin` 一条命令即可：

```bash
dsh plugin --profile web add ./dsh-lan-access
# 卸载：dsh plugin --profile web remove dsh-lan-access（同时移除依赖与层）
```

但注意：pnpm 以 `link:` 方式引用源码路径，删掉源码目录会导致插件失效——tarball 方案的
install.sh 会把源码复制到 `~/.dsh/plugins/`（持久位置）再 add，因此 tarball 更适合一次性部署。

## 3. 目标机前置要求

- 已安装并**运行过** `@deepseek-ai/dsh web`（首次运行初始化 `~/.dsh/profiles/web`）
- 仅限**可信局域网**：0.0.0.0 绑定会让网内任何设备访问 GUI（可驱动 agent 执行任意命令），勿暴露公网

## 4. 升级与恢复

dsh 升级/重装后，node_modules 内的特权围栏补丁会被覆盖。在目标机执行：

```bash
bash ~/.dsh/reapply-lan-patches.sh --restart
```

脚本幂等：检查并补齐"插件安装 → 组合接线 → 围栏补丁"三层，`--check` 只报告。

## 5. 编写新插件的一键安装

插件包内放一个 `install.sh`（可参考 packages/dsh-lan-access/install.sh 复制改造），
约定：
- 脚本目录即插件包目录（tarball 解压后 `<name>-install/<name>/` 为插件源码，脚本自动探测两种布局）
- 支持 `apply` / `--check` / `--restart` 三种模式
- 插件源码复制时排除 install.sh / reapply-lan-patches.sh / README.md（install.sh 已内置该逻辑）

跑 `bash scripts/package.sh` 即自动打进 tarball。

## 6. dsh 0.1.1-rc.2+ 兼容性（2026-08-31 实测）

dsh 升级到 **0.1.1-rc.2** 后，本仓库全部插件（auto-archive / lan-access / mobile-ui / vision / web-search-metaso）已验证**无需修改即可正常安装运行**（devbox 实测：uninstall → install → restart 全流程通过，插件加载正常）。

但宿主层有三个 **dsh 官方行为变更**，目标机需注意：

1. **dsh web 启动必须显式传 `--trusted-host <LAN_IP>`**
   - 否则特权 API（settings.describe / credentials.describe 等）对 LAN 请求一律 403（token 也无法绕过）
   - 症状：手机端/远程浏览器刷新丢配置、模型界面报错（前端降级 process-local）
   - systemd 托管时改 `ExecStart`：`... dsh web --trusted-host 192.168.0.x`

2. **`~/.dsh/.credentials.yaml` 格式演进（⚠️ 升级注意）**：0.1.1-rc.2 起官方格式改为 `version: 1` + `refs:` 嵌套（纯映射是 pre-release 旧格式）。rc.2 **首次启动会自动迁移**旧格式（实测 05:41 迁移成功、服务正常），**无需人工干预**。**但若启动命令仍指向旧版本**（如 npx 缓存里的 rc.6），旧版不认识新格式会报 `must be a string` 崩溃——**升级后务必确认启动命令指向新版本**（systemd ExecStart / 脚本路径），而不是被旧版缓存路径误导

3. **reapply-lan-patches.sh 的 ROOT 定位依赖运行中进程**（MR-025 逻辑）：升级后需先重启 dsh 再跑 `reapply-lan-patches.sh --check`，否则可能误报补丁缺失（进程 cwd 状态未就绪）

## 7. 其他用户操作速查（新版本 0.1.1-rc.2+，2026-08-31 实测）

**场景 A：全新安装插件**（devbox 实测 uninstall→install→restart 全流程通过）
```bash
tar xzf <name>-install.tar.gz && cd <name>-install
bash install.sh --restart   # 自动接线+打补丁（lan-access）+重启
```

**场景 B：升级 dsh 版本后**（仅 lan-access 需重打补丁，其他插件不打 node_modules 补丁无需操作）
```bash
npm i -g @deepseek-ai/dsh@0.1.1-rc.2
# ⚠️ 关键：确认启动命令指向新版本（systemd ExecStart / 启动脚本路径），
#   若指向 npx 缓存等旧版路径，旧版会因 credentials 新格式崩溃（must be a string）
#   例：systemd 改 WorkingDirectory=全局 dsh 目录 + ExecStart=./lib/bin.js web --trusted-host <IP>
# 适配宿主层 3 项（见 §6）后重启 dsh（rc.2 首次启动自动迁移 credentials，无需干预）
bash ~/.dsh/reapply-lan-patches.sh --restart   # 幂等恢复 lan-access 补丁
```

**场景 C：升级插件本身**（重复安装幂等，不重复接线）
```bash
bash install.sh --restart
```

**已验证的幂等性**：cordis.patch.yml 不会重复追加；reapply 6/6 层可重复执行；安装器对已有安装报 [已有] 内容一致。

## 8. dsh 版本升级 checklist（devbox 踩坑总结，2026-08-31）

**升级前**（最关键：确认启动命令指向哪）
```bash
readlink -f $(which dsh)                                  # CLI 指向
cat /proc/$(pgrep -f 'dsh web' | head -1)/cmdline         # 服务实际路径（⚠️ 可能与 CLI 不一致！）
cp -r ~/.dsh ~/.dsh-backup-$(date +%Y%m%d)                # 备份
cat ~/.dsh/.credentials.yaml                              # 记录当前格式（回滚用）
```

**升级后**
```bash
npm i -g @deepseek-ai/dsh@0.1.1-rc.2
# ⚠️ 必须确认启动命令指向新版本：
#   - systemd 托管：改 WorkingDirectory=全局dsh目录 + ExecStart=./lib/bin.js web --trusted-host <IP>
#   - 启动脚本：改路径
#   - npx 缓存安装（home-wsl 等）：升级后旧 npx 缓存仍在 → 必须改指向全局或清缓存
# ⚠️ 版本一致性检查：升级后 CLI 版本必须 = 服务版本（devbox 曾 CLI rc.7 / 服务 rc.6 不一致数月）
# rc.2 首次启动自动迁移 credentials（无需干预）；但若启动的是旧版会崩（must be a string）
# 验证：dsh --version / 手机端 settings.describe 200（带 token）/ 插件加载 / reapply-lan-patches.sh --restart
```

**核心教训**：升级问题 90% 源于「装了新版但服务还在跑旧版」（CLI 与 systemd/脚本指向不一致）。先确认启动路径，再谈升级。