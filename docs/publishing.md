# 分发指南（本地 tarball 一键安装）

目标：把仓库里的插件包分发到其他机器/环境的 dsh 上，一条命令装好。

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