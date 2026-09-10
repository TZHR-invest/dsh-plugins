# dsh-mobile-ui

dsh web 移动端 UI 优化插件：在手机（≤768px 视口）上把 dsh 变成真正的移动端体验。

- **响应式布局**：隐藏左侧图标栏，内容全宽；会话列表以抽屉形式展开
- **右上角菜单按钮**：新建 / 会话列表 / 设置 全部入口收纳进抽屉
- **阅读增强**：消息间距、气泡宽度、辅助文本（工具行/上下文注入/状态统计）字号提升
- **触摸优化**：防双击缩放延迟、点击高亮去除、输入框 16px（防 iOS focus 自动缩放）
- **安全区适配**：env(safe-area-inset-*) 支持刘海屏
- **桌面零影响**：所有增强仅在 ≤768px 媒体查询下生效

## 安装

```bash
# 在插件源码目录
bash install.sh            # 安装（幂等）
bash install.sh --restart  # 安装并重启 dsh web（含 headless 冒烟，插件问题自动中止）
bash install.sh --uninstall  # 卸载
```

安装内容：
1. 源码留档 `~/.dsh/plugins/dsh-mobile-ui/`
2. 运行副本 `~/.dsh/profiles/node_modules/dsh-mobile-ui/`
3. web profile 组合接线（`cordis.patch.yml` 插入插件行）

## 开发与验证

```bash
bash scripts/build.sh                       # 语法 + 契约预检（含 classic-script 校验）
bash scripts/package.sh                     # 打包 dist/dsh-mobile-ui-install.tar.gz
python3 tests/mobile-layout-probe.py        # 移动端布局回归探针（提问卡片可滚动/选项可达）
```

**提问卡片回归探针**（`tests/mobile-layout-probe.py`）：用真实上游 CSS + 真实 DOM 嵌套 +
真实插件代码，在 headless Chromium 里按视口 × 选项数跑矩阵，断言「正文可滚 / 真实手指
滑动后最后一个选项可见 / 提交按钮始终可见」，回归时退出码 1。它守的是一条硬纪律——
**绝不要覆盖提问卡片正文（`Mbwy4a_body` / `data-question-scroll`）的 overflow**：
上游卡片是 `max-height:min(60vh,520px)+overflow:hidden`，正文才是它唯一的滚动容器，
把它改成 `visible` 会让放不下的选项被卡片直接裁掉、且再也滚不出来（2026-09-11 修复的真实故障）。

本地快速迭代：复制到 `~/.dsh/profiles/node_modules/dsh-mobile-ui/` 后刷新页面
（客户端插件有 HMR 通道，改 client.js 后页面自动更新）。

## 工作原理

- **CSS 层**：注入 style[data-plugin-css=dsh-mobile-ui]，全部规则包在
  @media (max-width:768px) 内，桌面端不加载任何效果。
- **JS 层**：matchMedia 驱动；窄屏时把主布局 grid 改为单列、隐藏侧边栏，
  注入右上角菜单按钮 + 遮罩；菜单把侧边栏临时变为 fixed 抽屉（overlay）。
- **hero 标题置顶**：纯 CSS 实现——composerHero 栈在 hero 态撑满视口
  （flex:1），输入卡 margin-top:auto 沉底，标题/工作区行自然留在顶部。
- **提问卡片**：JS 检测到卡片后把它的 composerSeat 变成铺满可视高度的浮层，
  卡片自身的 max-height 放开、正文保持为唯一滚动容器（卡片内 `data-question-scroll`），
  footer 钉在浮层底部。选择器优先用上游稳定属性（`data-question-key` /
  `data-question-scroll` / `data-composer-seat`），hash 类名只作兜底。

## 维护须知（重要）

- dsh 前端 CSS 类名是构建产物（hash 前缀），升级 dsh 后若选择器失效：
  1. 浏览器控制台确认 body.dsh-mobile-ui 类与 #dsh-mobile-tabbar 存在；
  2. 失效通常发生在布局类（[class*=frame] 等），按新版类名前缀微调 CSS/JS；
  3. 修好后重新 bash install.sh。
- 布局探测采用「三列 grid + 首列 56px」结构识别（非类名硬编码），
  对类名漂移有一定容错；按钮转发优先 aria-label（新建会话 等）。
- **严禁用 JS 移动 React 渲染的 DOM 节点**（insertBefore/appendChild 搬动
  pXSMma_root 等）：React fiber 树仍记录旧父节点，重渲染时 removeChild 抛
  NotFoundError，整个会话视图被卸载 → 页面空白。布局需求一律用 CSS
  （flex/order/:has）表达；hero 标题置顶即纯 CSS 实现。
- **严禁覆盖提问卡片正文的 overflow**（2026-09-11 故障根因，已由探针看住）：
  上游 `.card{max-height:min(60vh,520px);overflow:hidden}` 且 `.body{overflow-y:auto}`
  ——正文是卡片内唯一滚动容器。改成 `overflow:visible` 会造成
  「选项看不全 + 手指滑动毫无反应」：卡片把放不下的选项裁掉，正文又不再滚动，
  浮层里也没有可滚内容（实测 6 选项时 body 内容 1047px / 可见 319px，滑动后几何零变化）。
  正确做法是**给正文更多高度**（浮层撑满视口 + 卡片 max-height:100%），而不是动它的 overflow。

## 回滚

bash install.sh --uninstall 后重启 dsh 即完全移除（不残留样式/导航 DOM）。
