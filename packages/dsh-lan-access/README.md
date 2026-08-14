# dsh-lan-access 一键安装包

dsh web 局域网访问支持（浏览器端 crypto.randomUUID polyfill + 0.0.0.0 绑定 + 特权围栏放行）。

## 适用条件

- 目标机器已安装并**运行过** @deepseek-ai/dsh web（首次运行会初始化 ~/.dsh/profiles/web 目录）
- 仅限**可信局域网**使用：0.0.0.0 会让局域网内任何设备访问本 GUI（可驱动 agent 执行任意命令），切勿暴露公网

## 安装步骤（三步）

1. 把本 tarball 拷到目标机器（scp / U 盘均可）：

   ```bash
   scp dsh-lan-access-install.tar.gz user@目标机:~/
   ```

2. 解压：

   ```bash
   cd ~ && tar xzf dsh-lan-access-install.tar.gz
   ```

3. 一键安装并重启验证：

   ```bash
   cd dsh-lan-access-install
   bash install.sh --restart
   ```

   安装后浏览器访问 `http://<目标机IP>:3080` 即可（非 localhost 访问必须走本插件补的 randomUUID polyfill）。

## 命令

| 命令 | 作用 |
|---|---|
| bash install.sh | 安装/补齐全部四层（幂等） |
| bash install.sh --check | 只检查状态，不改任何文件 |
| bash install.sh --restart | 安装后重启 dsh web 并 curl 验证 |

## 它装了什么

| 层 | 内容 | 落点 |
|---|---|---|
| 1 | webserver 绑定 0.0.0.0 | ~/.dsh/cordis.patch.yml |
| 2 | 插件源码 + profile 安装 | ~/.dsh/plugins/dsh-lan-access/、~/.dsh/profiles/node_modules/dsh-lan-access/ |
| 2 | 组合接线 | ~/.dsh/profiles/web/cordis.patch.yml 追加 insert 行 |
| 3 | 特权围栏放行 | node_modules/@deepseek-ai/dsh-client-connection/lib/index.js 一行补丁 |
| 4 | 设置持久化放行 | node_modules/@deepseek-ai/dsh-client-ui-settings/lib/client.js 一行补丁（settingsScope 强制 host，LAN 也可读写设置） |

另外会把 reapply-lan-patches.sh 复制到 ~/.dsh/：**以后 dsh 升级/重装后**（第 3 层补丁会被覆盖），跑 `bash ~/.dsh/reapply-lan-patches.sh --restart` 即可恢复。

## 验证

- curl http://<IP>:3080/plugins/dsh-lan-access/client.js 应返回 200 且含 randomUUID
- 浏览器控制台执行 crypto.randomUUID() 应返回合法 UUID v4
- 安装前若 crypto.randomUUID 为 undefined，安装并刷新页面后应变为函数

## 故障排查

- **web profile 未初始化**：install.sh 提示接线跳过 → 先跑一次 `dsh web` 再重跑 `bash install.sh`
- **特权围栏 sed 失败**（"代码结构已变化"）→ dsh 版本过新，需人工适配 dsh-client-connection/lib/index.js 中 PRIVILEGED_METHODS 附近的拦截逻辑
- **安装后 LAN 仍 403** → 检查 ~/.dsh/cordis.patch.yml 的 webserver 条目是否生效（重启后 `ss -ltnp | grep 3080` 应看到 0.0.0.0:3080 而非 127.0.0.1:3080）
