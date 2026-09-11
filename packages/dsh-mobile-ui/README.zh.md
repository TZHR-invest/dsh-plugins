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
python3 tests/mobile-layout-probe.py        # 移动端布局回归探针（提问卡片 + 输入区操作行）
```

**回归探针**（`tests/mobile-layout-probe.py`）：用真实上游 CSS + 真实 DOM 嵌套 +
真实插件代码，在 headless Chromium 里按视口跑矩阵，回归时退出码 1。两组：

**① 提问卡片**（视口 × 选项数）：断言「正文可滚 / 真实手指滑动后最后一个选项可见 /
提交按钮始终可见 / 右上角菜单按钮不遮挡卡片」。它守的是两条硬纪律——

1. **绝不要覆盖提问卡片正文（`Mbwy4a_body` / `data-question-scroll`）的 overflow**：
   上游卡片是 `max-height:min(60vh,520px)+overflow:hidden`，正文才是它唯一的滚动容器，
   把它改成 `visible` 会让放不下的选项被卡片直接裁掉、且再也滚不出来（2026-09-11 修复的真实故障）。
2. **浮层打开时必须隐藏右上角菜单按钮**：它固定在 `top:48px; right:12px`，
   正好压在提问卡片标题右侧（截图实证），所以菜单按钮的显隐要按
   「抽屉 / 设置面板 / 提问卡片」三态判定，而不是只看抽屉。

**② 输入区操作行**（视口 × 会话页/首页 × 长/短模型名）：断言「任意两个控件都不重叠 /
不越出输入卡右边界 / 都点得到 / 权限图标与文字都常显 / 模型名够宽（≥120px）/
被裁模型名走真省略号 / 图标文字箭头垂直居中对齐 / **同行控件等高同字号且中心离散
≤1.5px**」。它守的是第三条硬纪律——

3. **绝不能用"禁止换行 + 强行收缩"来硬塞单行**：上游组内按钮有
   `min-width:44px` 不可压缩，`flex-wrap:nowrap` 下宽度不足时 flex 无法收缩化解，
   只能**溢出重叠**（2026-09-11 修复的真实故障：390px 会话页
   访问模式↔模型重叠 5.7px、模型↔上下文重叠 4.3px）。正确做法是恢复上游
   `flex-wrap:wrap` 作兜底，并让 **trailing 组吃满余量、只留模型按钮一个可收缩项**。

**⚠️ `[class*=trigger]` / `[class*=访问模式] span` 这两类词根选择器是本插件最危险的坑**
（2026-09-11 一次性踩中三处，全部静默）：

- 上游 `_7KE1Ra_triggerLabel / triggerIcon / triggerEffort` 类名里都含 **"trigger"**。
  `[class*=trigger]{display:flex}` 会把 `text-overflow:ellipsis` 废掉（flex 容器忽略它）
  → 模型名被**硬切出半个字符**；`[class*=trigger]{min-height:40px}` 还会把 label
  撑成整行高、文字贴顶 → 视觉上 chevron 像"掉到下一行"。
  ⇒ 一律限定 `button[class*=trigger]`；省略号必须配 `display:block`。
- `button[aria-label*=访问模式] span{display:none}` 的 `span` 通配会连**盾牌图标**
  （也是 span）一起隐藏 → 整个按钮**纯空白**。⇒ 只隐藏 `[class*=triggerLabel]`，
  图标必须常显（它是该按钮唯一不变的识别物）。

另外两条同源教训：**trailing 的 `min-width` 不能给小**（`flex:1 1 0` + `min-width:0`
+ `justify-content:flex-end` 时，盒宽小于内容最小宽会把子元素**向左溢出**压住工具组——
实测 `min-width:96px` 时 365px 压 9px、410px 压 2px；而"模型名至少多宽"这种业务意图
不该用 min-width 表达）；**按容器查询而非视口猜**（操作行自带 `container-type:inline-size`，
`@container (min-width:324px)` 决定权限文字显隐，比按视口宽度判断稳）。

探针已做**双向对照**验证：修复前的版本返回 1（抓到 4 个重叠/越界用例 +
"权限图标被隐藏"/"推理等级后缀未隐藏"），完整修复版返回 0 —— 即它抓得住这两类缺陷，
不是"永远绿灯"的假探针。

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
- **操作行 = 两行布局**（2026-09-11 按用户反馈两轮迭代定型）：
  - 第一行：工具组（`+` / 附件 / 访问模式）······ 上下文环　发送
  - 第二行：模型选择器（**独占整行**）

  为什么必须两行：完整模型名（如 `commandcode/deepseek/deepseek-v4.1-flash`
  = 40 字符 ≈ 225px）在单行里**物理上放不下**——390px 视口整行内容仅 332px、
  工具组最少 120px，单行最多只能给模型名约 61px（10/40 字符，实测）。
  模型独占整行后同一视口可达 236px，**340px 以上就完整显示**；
  代价是行高 52 → 98~102px。

  ⚠️ **第一版两行排布（工具组独占第一行、模型+上下文+发送在第二行）是错的**：
  它在第一行右侧留出 **183px 空白**（412px 实测），用户一眼看出"上面空了一块"。
  正确做法是把上下文环与发送提到第一行右侧填满，模型独占第二行
  （空块 183px → 8px）。实现用 `display:contents` 打散 `trailing`，
  让其子元素成为 row 的直接 flex 项，再用 `order` 指定视觉顺序、
  `margin-left:auto` 把后两者推到最右 —— **纯 CSS，不移动 DOM**
  （搬 React 节点会在重渲染时 removeChild 抛错）。
  权限按钮恒显盾牌图标 + 文字（`@container (min-width:170px)` 判据，第一行独占后
  320px 也放得下「完全权限」）；被裁的模型名一律走**真省略号**。

- **操作行视觉统一**（2026-09-11 用户反馈"高度不一致、怪怪的"实测定案）：
  上游六种控件高度本不相同（add 28 / PermissionSelect 28 / 模型 28 / ContextMeter 28
  / primary 34，而我们此前的补丁又留下 36/40/44 混排），字号也散落三代
  （模型 11px / 权限 13px / 上下文 10px）。现已全部统一为 **44px 高 + 12px 字号**
  （顺带满足 iOS HIG 最小可点尺寸——实测原来 `+`/附件/权限 只有 36px 可点高度），
  并取消发送键上游的 `translateY(-2px)`（那是单行时代的视觉补偿，多行下让它的
  中心比同行低 2px），权限按钮补上与 `+`/附件 相同的圆形实底（上游它是无底色
  紧凑触发器，夹在两个圆形实底按钮中间显得"缺一块"，是"怪"的主要来源）。
  **判据**：恰为两行、同一行内所有按钮等高同字号、垂直中心离散 ≤1.5px、
  **每行右侧空块 ≤60px**（后者正是"空了一块"的量化守卫）。

  ⚠️ 另一个隐蔽坑：浏览器 UA 默认给 `<button>` 是 **`text-align:center`**。
  模型名独占整行后，居中会让文字从 69px 处才开始（实测 412px），
  与上一行的 `+` 按钮不对齐 —— 必须显式 `text-align:left`。
  （旧排布里 label 宽度恰好等于文字宽度、没有富余空间居中，所以一直没暴露。）

  ⚠️ 这条修复暴露了第四处**词根选择器泄漏**：消息流里**并不存在** `[class*=tools]`
  （实测消息流只有 `xzv4MW_actions` / `TS9iAW_actions`），所以旧规则
  `[class*=scrollBody] [class*=tools] button{min-height:36px}` 唯一命中的对象是
  **输入框的 `uV2eYG_tools`**，把 `+`/附件/权限 压成 36px —— 这正是"第一行 36px、
  第二行 40/44px"的根源。现已限定到 `[class*=flowItem]` 内，消息流按钮保持
  36px、输入框控件 44px，两者互不干扰。

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
- **右上角菜单按钮的显隐必须是三态判定**（抽屉 / 设置面板 / 提问卡片）：
  该按钮固定在 `top:calc(48px + safe-area); right:12px`，提问卡片打开时正好压在
  卡片标题右侧（2026-09-11 由真实页面截图发现）。旧写法只看 `drawerOpen`，
  既会在提问卡片上造成遮挡，也会把设置面板打开时隐藏的菜单在下次 sync 又显示回来。

## 回滚

bash install.sh --uninstall 后重启 dsh 即完全移除（不残留样式/导航 DOM）。
