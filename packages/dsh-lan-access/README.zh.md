# dsh-lan-access 一键安装包

dsh web 局域网访问支持（浏览器端 crypto.randomUUID polyfill + 0.0.0.0 绑定 + 特权围栏放行 + **访问令牌验证**）。

## 适用条件

- 目标机器已安装并**运行过** @deepseek-ai/dsh web（首次运行会初始化 ~/.dsh/profiles/web 目录）
- 仅限**可信局域网**使用：0.0.0.0 会让局域网内任何设备访问本 GUI（可驱动 agent 执行任意命令），切勿暴露公网
- **访问令牌**：所有请求必须携带令牌（Cookie / `?token=` / `X-DSH-Token` / 登录页表单），未授权一律 401（登录页）。令牌经明文 HTTP 传输，防的是“未授权设备访问”，不防局域网内嗅探；如需防窃听请再套一层 HTTPS 反向代理

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

   安装时若未配置过令牌，会自动生成**随机访问令牌**（仅显示一次，请保存），写入 ~/.dsh/lan-access-token（权限 600）。
   安装后浏览器访问 `http://<目标机IP>:3080` 或 `http://127.0.0.1:3080` 都会看到令牌登录页（v3 起回环不再豁免；**看到登录页 = 服务正常，HTTP 401 属预期**）。

## 访问令牌

- 令牌文件：`~/.dsh/lan-access-token`（单行文本，`chmod 600`）。**修改后保存即生效，无需重启**（每次请求实时读取）
- **两条路径（v3 起行为一致）**：无论局域网 IP 还是本机 `localhost / 127.*`，无凭据一律出登录页
  - 例外：**WebSocket 握手**仍对回环放行（握手没法渲染表单，凭证靠浏览器 Cookie）
- 访问方式（任一即可）：
  - 浏览器首次访问看到登录页，粘贴令牌进入（自动种 Cookie，30 天有效）
  - `curl -H "X-DSH-Token: <令牌>" http://<IP>:3080/api/...`（**仅 API 通道**；根路径 `/` 认的是 `?token=` 或 Cookie）
  - 浏览器直接访问 `http://<IP>:3080/?token=<令牌>`（自动种 Cookie）
  - WebSocket 连接随 Cookie 自动携带，无需额外处理
- 登录表单提交点为 `POST /__lan_auth`（正确令牌 → 302 到 `/?token=` 触发 host browserAuth 交换 + Set-Cookie）
- **v3 新增 index-401 兜底**：即使带着已失效的 Cookie 被 host browserAuth 拒绝（Cookie 过期 / 浏览器 Cookie 签名密钥轮换过 / 换 origin 残留同名 Cookie），`/` 上那句纯文本英文 401 也会被换成登录页，用户永远有入口
- 删除令牌文件 = 关闭门卫（防锁死）；重新生成：删掉文件后重跑 `bash install.sh`

## 命令

| 命令 | 作用 |
|---|---|
| bash install.sh | 安装/补齐全部六层（幂等） |
| bash install.sh --check | 只检查状态，不改任何文件 |
| bash install.sh --restart | 安装后重启 dsh web 并 curl 验证 |

## 它装了什么

| 层 | 内容 | 落点 |
|---|---|---|
| 1 | webserver 绑定 0.0.0.0 | ~/.dsh/cordis.patch.yml |
| 2 | 插件源码 + profile 安装 | ~/.dsh/plugins/dsh-lan-access/、~/.dsh/profiles/node_modules/dsh-lan-access/ |
| 2 | 组合接线 | ~/.dsh/profiles/web/cordis.patch.yml 追加 insert 行 |
| 3 | 访问令牌 | ~/.dsh/lan-access-token（随机生成，600 权限） |
| 4 | 特权围栏放行 | node_modules/@deepseek-ai/dsh-client-connection/lib/index.js 一行补丁 |
| 5 | 设置持久化放行 | node_modules/@deepseek-ai/dsh-client-ui-settings/lib/client.js 一行补丁（settingsScope 强制 host，LAN 也可读写设置） |
| 6 | 令牌门卫 v3（401 登录页，含回环 + index-401 兜底 + WS 拦截） | node_modules/@deepseek-ai/dsh-host-webserver/lib/index.js 入口补丁（token-gate.js + patch-webserver.mjs，可 --revert 回滚） |

另外会把 reapply-lan-patches.sh 复制到 ~/.dsh/：**以后 dsh 升级/重装后**（第 4/5/6 层补丁会被覆盖），跑 `bash ~/.dsh/reapply-lan-patches.sh --restart` 即可恢复。

## 验证

- `curl -i http://127.0.0.1:3080/` 应 **401 + `content-type: text/html` + 登录页**（v3；旧的“回环应 200”写法自 dsh 0.1.2+ 起就不成立了）
- `curl -i http://<IP>:3080/` 同样应 401 + 登录页
- `curl -i "http://<IP>:3080/?token=<令牌>"` 应 **303 + Set-Cookie**
- `curl -H "X-DSH-Token: <令牌>" -X POST http://<IP>:3080/api/<method>` 应非 401/403（**API 通道；`/` 不认这个头**）
- 浏览器控制台执行 crypto.randomUUID() 应返回合法 UUID v4

## 单元测试

```bash
node --test packages/dsh-lan-access/tests/token-gate.test.mjs
```

覆盖回环/非回环、三条令牌通道、表单提交、以及 index-401 兜底（16 例）。

## 故障排查

- **web profile 未初始化**：install.sh 提示接线跳过 → 先跑一次 `dsh web` 再重跑 `bash install.sh`
- **特权围栏 sed 失败**（"代码结构已变化"）→ dsh 版本过新，需人工适配 dsh-client-connection/lib/index.js 中 PRIVILEGED_METHODS 附近的拦截逻辑
- **令牌门卫补丁失败**（"未找到锚点"）→ dsh-host-webserver 版本结构变化，需人工适配 patch-webserver.mjs 中的锚点
- **忘记令牌**：`cat ~/.dsh/lan-access-token`；或删除文件重跑 `bash install.sh` 重新生成
- **想关掉令牌验证**：`rm ~/.dsh/lan-access-token`（门卫自动关闭）；彻底移除补丁：`node ~/.dsh/plugins/dsh-lan-gateway/patch-webserver.mjs <webserver lib> --revert`
- **安装后 LAN 仍 403** → 检查 ~/.dsh/cordis.patch.yml 的 webserver 条目是否生效（重启后 `ss -ltnp | grep 3080` 应看到 0.0.0.0:3080 而非 127.0.0.1:3080）
