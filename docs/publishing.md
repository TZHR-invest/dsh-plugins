# 分发指南（本地 tarball 一键安装）

目标：把仓库里的插件包分发到其他机器/环境的 dsh 上，一条命令装好。

## 0. 三条分发渠道与「必须升版本」纪律（2026-09-11 定案，先读这条）

本仓库的插件同时经 **三条渠道** 到达用户，三者必须同版本、同内容：

| 渠道 | 载体 | 谁在用 |
|---|---|---|
| npm | `npm i <包名>` | 外部/社区用户 |
| tarball | `dist/<name>-install.tar.gz` | 装机脚本、其他机器 |
| 仓库源码 | `packages/<name>/` | 本仓开发 |

**⚠️ 本仓库是 public（`TZHR-invest/dsh-plugins`）⇒ 推送前必跑凭据扫描**：

```bash
python3 scripts/secret-scan.py --secrets-file ~/.meshdeck-secrets.md   # 非零退出即不可推
```

值清单（`~/.meshdeck-secrets.md`）只在本地存在，故 CI 只跑形态扫描
（`.github/workflows/secret-scan.yml`，每次 push/PR 自动跑），**值级反查靠本地这一步补**。
风险点很具体：各插件 `install.sh` 会往 `cordis.patch.yml` 写 metaso / memory-recall / opencodex
三把 key —— 一次「把本机 patch 当模板拷进仓库」就会把它们一起公开（历史已逐值 `git log -S` 验过干净）。

**⚠️ 血泪教训（2026-09-11，一次查出 4 处）**：多个修复提交只改了代码、**没升 `version`**，
而 **npm 不允许覆盖已发布版本** → 仓库修好了，npm 上仍是坏代码。实测三例：

- `dsh-lan-gateway`：npm 版 `token-gate.js` 与修复前版本 md5 完全一致 → dsh 0.1.2+ 上 LAN 访问被旧门卫彻底挡死
- `dsh-web-search-metaso`：npm 版仍 `import installSettingsSection`（0.1.2 已移除该 API）→ 装上即崩溃
- `dsh-vision-tool`：npm 版缺 `apiKeyHeader` → opencodex 鉴权无法配置

**纪律：任何修改插件行为的提交，都必须同时升 `packages/<name>/package.json` 的 `version`；
只改文档/脚本注释可不升。** 版本号是唯一能让外部用户拿到修复的手段。

**✅ 2026-09-11 已全部补齐（五包三渠道一致）**：上述三例已随版本升版发布；同日另补两处并
首次发布 `dsh-auto-archive`。当前状态（发布后逐文件 md5 核对通过）：

| 包 | 版本 | 备注 |
|---|---|---|
| `dsh-lan-gateway` | **0.2.6** | `install.sh` 的补丁层**委托 `reapply-lan-patches.sh`**（单一事实源）：≤0.2.5 的 4/6–6/6 段按顶层 `node_modules/@deepseek-ai/<pkg>` 定位，而包嵌在 `dsh/node_modules/@deepseek-ai/` 下 ⇒ ①`--check` 误报三处「缺失」②**apply 同样静默跳过**（三段从未生效）③缺 7/7 deflate 段 ④reapply 分发用 `! -f` 守卫致**旧版永不更新**；另修重启验证判据（全局安装下 `$ROOT/node_modules/.bin/dsh` 不存在 ⇒ 整段验证被跳过）；补 `.npmignore` 防 `*.bak-*` 进包。**2026-09-14 已发 npm，8/8 逐文件 md5 核对一致**（本机 + home-wsl `--check` 双向验证） |
| `dsh-lan-gateway` | **0.2.5** | WS 响应压缩（permessage-deflate，慢链路 4.80x：1.20MB→256KB；须重启 dsh web）+ 部署/恢复脚本三处静默缺口修复（install/reapply 在 tarball 根目录、写入式文件清单漏补丁源、reapply 安装根定位在 office_64g 失效）。**2026-09-14 已发 npm 并逐文件 md5 核对：13/13 与仓库一致** |
| `dsh-lan-gateway` | 0.2.4 | 令牌门卫 v3：回环不再短路（本机 `127.0.0.1` 也出登录页 —— v2 下本机只能看到 host browserAuth 的纯文本 401）+ index-401 兜底（cookie 过期 / 签名密钥轮换时同样换登录页）；补 16 例单测 + `token-gate.v2.js` 留档（就地升级匹配基准） |
| `dsh-lan-gateway` | 0.2.3 | 安装器不再静默关闭响应压缩（loader patch 整体替换 config；慢链路 11.19MB→3.95MB） |
| `dsh-mobile-ui` | **0.2.8** | 「点三个点还是没反应」的**最终真根因**（用户第 4 次反馈后远程取证定位）：**自己人挖的坑 —— `opacity:0` 是「组不透明度」**。0.2.5 为给 header 瘦身，把 `[class*=wSkVaW_headerUtilities]` 设成 `position:absolute;opacity:0;pointer-events:none`，而上游「更多操作」菜单**恰好挂在这棵子树里**（祖先链 `menu → span._root_1nxmc_ → div → headerUtilities`）⇒ 菜单**弹出来了、几何全对**（实测 `rect=[8,122,396,42]`、条目「下载 Session 日志」齐全），却被祖先的组透明**整棵变不可见**，还继承 `pointer-events:none` ⇒ **看不见 + 点不动**。修法＝改用 `visibility:hidden`（同样不占布局、rect 照常可测；`display:none` 会算出 0×0，2026-09-14 已踩过），并给该子树里的 `[role=menu]/[class*=_list_1nxmc_]/[class*=_portal_]/[class*=QsffPG_menu]` 加 `visibility:visible`（**`visibility` 可被后代覆盖，`opacity` 不行**）。配套探针加固：`POPOVER` 断言从「只有几何与条目数」升级为**必须能看见能点到**（祖先链有效 opacity 逐级相乘 < 0.9 / `visibility!=visible` / `pointer-events:none` / `elementFromPoint(菜单中心)` 不属于菜单 ⇒ 任一命中即失败）——旧断言在菜单全透明时**一路绿灯**，正是连报三轮的原因。**未发 npm（令牌 401，见下）**，tarball 与 5 台机器已同步。**后补：2026-09-15 换新令牌后已发 npm**（GET 轮询第 16 次就绪，仓库 vs 产物 **13/13 文件 md5 一致**、`latest=0.2.8`；0.2.7 因令牌失效跳过，npm 从 0.2.6 直接跳到 0.2.8）|
| `dsh-mobile-ui` | **0.2.7** | 用户第三次报「点折叠左边的三个点还是没反应」的**真根因**：不是按钮、不是竞态，而是上游**右侧栏拖拽把手的隐形死区**——`pI_x6G_handle`（`dsh-client-ui-layout`）是 `position:absolute;top:0;bottom:0;width:8px;z-index:11;pointer-events:auto`，右侧栏折叠后 `rightbarCol` 缩成 `height:0`（`rect=[0,915,412,0]`）**但把手不跟着消失**，仍以固定 `left`（实测 276px）**贯穿整个视口高度**（0→915）⇒ x∈[276,284) 这一整列 8px 的 tap 全被吃掉（手机没有 col-resize，用户只感到「点了没反应」，正文按钮/输入框同样被挡）。工具组右对齐（⋯ 中心 = 视口宽−134）⇒ 只在 **410–417px** 这段视口压住 ⋯ 中心，**所以「390px 测着全好、手机却点不动」**（⭐ 单宽度探针天然漏检）。修法：`[class*=pI_x6G_handle]{display:none}`（移动端不需要 col-resize）+ 工具组 `position:relative;z-index:30` 第二道保险；`tests/live-probe.py` 新增 **12 档宽度扫描**（把手残留/按钮被覆盖/412px ⋯ 开合）——另用独立 14 档扫描证实全通过（含此前全灭的 410–418px）。**⚠️ npm 未发布**：本轮 npm 粒度令牌失效（`whoami` 返回 `{}`、publish 404），npm 上停在 0.2.6；其余两条渠道已到位 |
| `dsh-mobile-ui` | **0.2.6** | 修 0.2.5 新注入按钮的两个交互缺陷（用户报「三个点按钮点击没反应 / 折叠按钮不灵敏」）：①「更多操作」代理按钮**命中率仅 2/6** —— 上游「点外面就关」监听 `pointerdown`、我们的转发在 `click`，菜单开着时一次 tap 变成「先关又开」⇒ 净效果无变化；修法=在按钮的 pointerdown（早于 document）记下当前是否开着，开着就什么都不做（交给上游关闭），成为真 toggle；②两个 popover 的 `top` 改为**落在触发按钮下方**（QsffPG 42→74、_1nxmc_ 76→122）—— 原来菜单弹出后会盖住触发它的按钮，再点落在菜单上；③工具按钮 30×26 → **36×34** 且 tabs 行 25→34px（原尺寸低于插件 44px 触摸规范，手指易点偏）。实测命中率 2/6 → **6/6**；live-probe 增「⋯ 开合序列 [1,0]」与「触摸目标 ≥32px」断言。**已发 npm，5/5 md5 一致** |
| `dsh-mobile-ui` | **0.2.5** | 手机端**空间占比优化**（用户反馈「标题栏三行有点乱 / 正文显窄」）：①header 三行→两行（隐藏第三行的终端打开/选择打开方式/右侧边栏 —— 前两个点了是在**服务器**开终端、右侧栏早被插件隐藏），header **138 → 107px**；②唯一有用的「更多操作」改由 tabs 行**代理按钮**转发（上游按钮移出文档流但保留坐标 —— `display:none` 会让它算出 0×0 的菜单，实测踩到）；③tabs 行新增**折叠输入区**开关（阅读模式，输入区 230 → 0px，正文占比 **60% → 87%**，状态存 localStorage，提问卡片出现时强制展开）；④抽屉入口并入 tabs 工具组（原悬浮汉堡会压住第二行/tabs），**首页保留原入口**（`body:has([class*=wSkVaW_tabs])` 才隐藏 —— 一刀切隐藏会让 hero 页没有抽屉入口，实测踩到）。**2026-09-14 已发 npm，5/5 md5 一致** |
| `dsh-mobile-ui` | **0.2.4** | 移动端**顶部 popover 出视口**修复（用户报「点后台任务/终端/session 日志显示不全」）：后台任务菜单 `QsffPG_menu`（absolute left:0 + 宽 336，锚在 x=261 ⇒ **右溢 207px**）与通用菜单 `[role=menu][class*=_list_1nxmc_]`（right:0 + 宽 218，锚在 x=100 ⇒ **左溢 90px**，含「下载 Session 日志」「在终端打开」项）一律改 `fixed` 到视口（左右各 8px、宽自适应、顶部 42/76px、max-height + 滚动兜底）；配套：菜单打开时隐藏右上角悬浮汉堡按钮（新增第 4 态，否则压住菜单首行——vision 复核截图发现）；titleCluster 允许换行（有后台任务时 headerActions 多出 150px 不收缩的切换器 ⇒ crumbs 被压到 106px、子代理切换器溢出 8px）。live-probe 增两条 popover 断言。**2026-09-14 已发 npm，5/5 逐文件 md5 核对一致** |
| `dsh-mobile-ui` | **0.2.3** | 子代理切换器两处修复：①「个子代理」竖排成 96px 一列 + 被 crumbs 裁到点不开（`[class*=crumbs]` 的 white-space 继承泄漏 + 面包屑空间不足）；②箭头展开后**点不回去**（上游 trigger 无点击逻辑，靠 hover 打开）→ 复用上游键盘路径派发 ArrowDown/Escape。新增两个探针：`tests/mobile-layout-probe.py` 头部组 8 例、`tests/live-probe.py` 真机交互 |
| `dsh-mobile-ui` | 0.2.2 | 移动端操作行重做（两行排布 / 等高 44px / 权限按钮空白与半截字符等 5 类修复，0.1.2 → 0.2.2） |
| `dsh-vision-tool` | 0.1.2 | |
| `dsh-web-search-metaso` | 0.1.2 | 修复「切换段漏写 `fetchProvider` → `web_fetch` 全废」 |
| `dsh-auto-archive` | 0.1.1 | **首次发布**；修复 dsh 0.1.5 `persistence.list()/locate()` 变更致归档静默失效 |

## 0.1 客户端插件分发：为什么"本机改了"≠"别处也好了"（2026-09-11 定案）

`dsh-mobile-ui` 这类**客户端 bundle** 由**每台机器自己的 `dsh web`** 提供，浏览器加载的是
"它所连那台机器"的 `client.js`。因此修好 ai-agent 只对 ai-agent 生效，其余机器照旧跑旧代码
（实测：ai-agent 已是新版，devbox/trade-pc/office_64g 停在 `ff3547c9`、home-wsl 停在更旧的
`9e855e87`，即**修复前**的版本）。

**升级方式（不需要重启服务）**：客户端 bundle 路由每次读磁盘，**刷新浏览器即生效**。
只需把两个文件放到目标机的两处位置：

```bash
# 每台机器两处：源码目录 + 运行副本（缺一不可，运行副本才是实际被加载的）
cp client.js package.json ~/.dsh/plugins/dsh-mobile-ui/
cp client.js package.json ~/.dsh/profiles/node_modules/dsh-mobile-ui/
```

**⚠️ 只拷 `client.js` 忘记 `package.json` 会让版本核对撒谎**——`package.json` 里的 `version`
是唯一能一眼判断"这台是什么版本"的凭据（本轮 ai-agent 就曾因它停在 0.1.1 而误导过排查）。

**⚠️ 同步后必须做浏览器端验证，不能只看文件 md5。** 本轮实测一个反例：home-wsl 文件
md5 完全正确，浏览器却永远停在 "Loading plugins…"。根因与插件无关——
该机只有 tailscale 可达，且链路走 **DERP 中继（sfo）而非直连**（`direct connection not
established`，延迟 400-800ms、带宽 **153 KB/s**），而 dsh 的客户端插件聚合包有
**11.2 MB**，传输需 **73 秒**，浏览器等不及。定位手法：在目标机**本机** curl 同一 URL
（实测 0.066s 返回 200/11.2MB）即可区分"服务端问题"还是"链路问题"。

**教训（第二轮，同型复发）**：metaso 这次又是「仓库已修、npm 仍是坏版本」——
`npm i dsh-web-search-metaso` 装到 0.1.1 会复现 `web_fetch` 全废故障。
**升版本必须与修改放进同一个提交**，否则下一次仍会漏。核对现状用一条命令：

```bash
for d in packages/*/; do n=$(basename $d); r=$(node -p "require('./$d/package.json').version"); \
  m=$(npm view "$(node -p "require('./$d/package.json').name")" version 2>/dev/null || echo 未发布); \
  [ "$r" = "$m" ] && echo "✓ $n $r" || echo "⚠ $n 仓库=$r npm=$m"; done
```

**发布后必须核对产物内容**（不要只看 `npm publish` 成功）：

```bash
npm publish                                   # 返回 PUT 202 = 异步受理，不是最终成功
# 轮询到 tarball 可下载（元数据约 3 分钟、tarball 约 4-5 分钟才就绪，期间 404 属正常）
# ⚠️ 必须用 GET 探测：HEAD（curl -sI）对 npm CDN **会一直返回 404**，即使包早已可下载
#    —— 2026-09-14 实测白等了 5 分钟，换成 GET 立刻 200（元数据其实早就就绪了）
curl -sL -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/<pkg>/-/<pkg>-<ver>.tgz
# 解包与仓库逐文件对 md5 —— 这一步才是"发布成功"的判据
curl -sL -o pkg.tgz https://registry.npmjs.org/<pkg>/-/<pkg>-<ver>.tgz && tar xzf pkg.tgz \
  && md5sum package/index.js packages/<name>/index.js
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