#!/bin/bash
# install.sh — dsh 局域网访问支持 一键安装（新机器部署 / 重装恢复）
# 随安装包分发：本脚本 + dsh-lan-access/（插件源码）。
#
# 用法:
#   bash install.sh            # 安装全部六层（幂等，可反复执行）
#   bash install.sh --check    # 只报告状态，不修改任何文件
#   bash install.sh --restart  # 安装后重启 dsh web 并验证（会中断当前 web 服务几秒）
#
# 局域网访问由六层组成：
#   1. webserver 绑定 0.0.0.0    -> ~/.dsh/cordis.patch.yml（用户配置层）
#   2. crypto.randomUUID 插件    -> ~/.dsh/plugins/dsh-lan-access/ + profile 安装 + 组合接线
#   3. 访问令牌                  -> ~/.dsh/lan-access-token（访问必须持有；v3 起回环也要）
#   4. 特权围栏放行              -> dsh-client-connection 一行补丁（dsh 升级后可能被覆盖，
#                                  届时重跑本脚本或 ~/.dsh/reapply-lan-patches.sh 即可）
#   5. 设置持久化放行            -> dsh-client-ui-settings 一行补丁
#   6. 令牌门卫                  -> dsh-host-webserver 入口补丁 v3（401 登录页，含回环 +
#                                   index-401 兜底 + WebSocket 拦截）
#
# 安全说明：0.0.0.0 会让局域网内任何设备可访问本 GUI（可驱动 agent 执行命令）。
# 本包为其增加访问令牌验证：所有浏览器/HTTP 请求必须携带令牌
# （Cookie / ?token= / X-DSH-Token / 登录页表单），未授权一律 401 登录页。
# 令牌经明文 HTTP 传输，防的是“未授权设备访问”，不防局域网内嗅探；
# 如需防窃听请再套一层 HTTPS 反向代理。仅限可信局域网使用，勿暴露公网。
set -u

MODE="${1:-apply}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DSH="${DSH_HOME:-$HOME/.dsh}"
if [ -d "$HERE/dsh-lan-access" ]; then
  PLUGIN="$HERE/dsh-lan-access"   # tarball 解压布局
else
  PLUGIN="$HERE"                  # monorepo 包内直接运行
fi
FAIL=0

echo "== dsh-lan-gateway 一键安装（mode: $MODE）=="
echo "  DSH 目录: $DSH"
echo "  安装包目录: $HERE"

# ── 0/6 前置检查：安装包完整性 + 定位 dsh 安装根 ───────────────────────────
echo "== 0/6 前置检查 =="
if [ ! -f "$PLUGIN/package.json" ] || [ ! -f "$PLUGIN/client.js" ]; then
  echo "  错误：安装包缺少 dsh-lan-gateway/ 插件源码（$PLUGIN 不完整）"; exit 1
fi
if [ ! -f "$PLUGIN/token-gate.js" ] || [ ! -f "$PLUGIN/token-gate.v2.js" ] || [ ! -f "$PLUGIN/patch-webserver.mjs" ]; then
  echo "  错误：安装包缺少令牌门卫补丁源（token-gate.js / token-gate.v2.js / patch-webserver.mjs）"; exit 1
fi
echo "  [OK] 插件源码完整"

ROOT=""
PID=$(pgrep -f 'node_modules/.bin/dsh web' 2>/dev/null | head -1)
if [ -n "${PID:-}" ]; then
  CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
  [ -n "$CWD" ] && [ -d "$CWD/node_modules/@deepseek-ai" ] && ROOT="$CWD"
fi
if [ -z "$ROOT" ]; then
  for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
    d=${d%/}
    [ -d "$d/node_modules/@deepseek-ai" ] || continue
    ROOT="$d"
    break
  done
fi
if [ -z "$ROOT" ]; then
  G=$(npm root -g 2>/dev/null || true)
  [ -n "$G" ] && [ -d "$G/@deepseek-ai" ] && ROOT="${G%/node_modules}"
fi
if [ -n "$ROOT" ]; then
  echo "  [OK] dsh 安装目录: $ROOT"
else
  echo "  [警告] 未找到 dsh 安装目录（检查 pgrep / ~/.npm/_npx / npm root -g）；"
  echo "         第 4/5/6 层补丁将跳过。请先安装并启动过 @deepseek-ai/dsh。"
  FAIL=1
fi

# ── 1/6 webserver 绑定 0.0.0.0（第 1 层）───────────────────────────────────
#
# ⚠️ 必须同时重述 compression* 三个键（2026-09-11 实测定案）：
#    loader patch 会**整体替换**目标行的 config（dsh-web-app/cordis.patch.yml 原文：
#    "A patch replaces the targeted row's whole config, so each row below restates
#    every key it owns"）。dsh-web-app bundle 里该行本来自带
#    `compression: gzip`（level 1、阈值 1024），我们只写 host/port 就把它**静默关掉**了
#    → 所有响应不压缩。后果在慢链路上被放大：客户端插件聚合包 11.2MB 原样传输，
#    经 tailscale DERP 中继（~130KB/s）需 73 秒，表现为长期停在
#    "Loading plugins…"（home-wsl 实测）。补上后同一包 3.95MB / 30 秒（压缩比 2.8x）。
PATCH1="$DSH/cordis.patch.yml"
echo "== 1/6 webserver 绑定 0.0.0.0（含压缩配置）=="

# 幂等修复：块已在但缺 compression（旧版安装器留下的），就地补齐
repair_compression() {
  local f="$1"
  [ -f "$f" ] || return 0
  grep -q 'id: webserver' "$f" 2>/dev/null || return 0
  grep -q 'compression:' "$f" 2>/dev/null && return 0
  awk '
    BEGIN { inblk = 0 }
    /^[[:space:]]*-[[:space:]]*id:[[:space:]]*webserver/ { inblk = 1 }
    inblk && /^[[:space:]]*port:/ {
      print
      print "    compression: gzip"
      print "    compressionLevel: 6"
      print "    compressionThresholdBytes: 1024"
      inblk = 0
      next
    }
    { print }
  ' "$f" > "$f.tmp-compress" && mv "$f.tmp-compress" "$f"
  echo "  [已补] $f 缺 compression*，已就地加入（否则响应不压缩）"
}

if [ -f "$PATCH1" ] && grep -q 'id: webserver' "$PATCH1" 2>/dev/null; then
  if grep -q "0.0.0.0" "$PATCH1"; then
    echo "  [已有] $PATCH1"
    if [ "$MODE" = "--check" ]; then
      grep -q 'compression:' "$PATCH1" \
        || { echo "  [缺失] $PATCH1 缺 compression*（响应不压缩，慢链路会明显变慢）"; FAIL=1; }
    else
      repair_compression "$PATCH1"
    fi
  else
    echo "  [跳过] $PATCH1 已有 webserver 配置但未绑定 0.0.0.0，为避免覆盖你的配置，请人工修改"
    FAIL=1
  fi
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $PATCH1 中的 webserver 0.0.0.0 条目"
else
  mkdir -p "$DSH"
  cat >> "$PATCH1" <<'EOF'
# ⚠️ loader patch 会整体替换该行 config，故 bundle 自带的 compression* 必须一并重述，
#    否则响应不压缩（慢链路/移动端会明显变慢；详见 dsh-lan-access/install.sh 注释）。
- id: webserver
  config:
    host: '0.0.0.0'
    port: 3080
    compression: gzip
    compressionLevel: 6
    compressionThresholdBytes: 1024
EOF
  echo "  [已加] $PATCH1（含 compression: gzip）"
fi

# ── 2/6 插件安装与接线（官方 bundle 流优先，复制流回退）──────────────────
echo "== 2/6 插件安装与接线 =="
PATCH2="$DSH/profiles/web/cordis.patch.yml"
DST_PLUGINS="$DSH/plugins/dsh-lan-gateway"
DST_PROFILE="$DSH/profiles/node_modules/dsh-lan-gateway"

bundle_wired() {
  [ -f "$DSH/profiles/web/package.json" ] && grep -qE '"(dsh-lan-access|dsh-lan-gateway)"' "$DSH/profiles/web/package.json"
}
legacy_wired() {
  [ -f "$DST_PROFILE/client.js" ] && grep -q "randomUUID" "$DST_PROFILE/client.js" 2>/dev/null \
    && [ -f "$PATCH2" ] && grep -q 'id: lan-access' "$PATCH2"
}

cleanup_legacy_lines() {
  local f="$1"
  [ -f "$f" ] || return 0
  grep -q 'id: lan-access' "$f" || return 0
  awk '
    function flush(   i, skipnext) {
      if (!start) return
      if (has_lan && cnt == 1) { start=0; return }
      skipnext=0
      for (i=1; i<=n; i++) {
        if (skipnext) { skipnext=0; continue }
        if (lines[i] ~ /^[[:space:]]*- id: lan-access[[:space:]]*$/) { skipnext=1; continue }
        print lines[i]
      }
      start=0
    }
    {
      if ($0 ~ /^[[:space:]]*- insert:[[:space:]]*$/) {
        flush()
        start=1; n=0; cnt=0; has_lan=0
        lines[++n]=$0
        next
      }
      if (start) {
        lines[++n]=$0
        if ($0 ~ /^[[:space:]]*- id: lan-access[[:space:]]*$/) { has_lan=1; cnt++ }
        else if ($0 ~ /^[[:space:]]*- id:/) cnt++
        next
      }
      print
    }
    END { flush() }
  ' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  [ -s "$f" ] || printf '[]\n' > "$f"
  echo "  [清理] 移除 $f 旧手动接线行（bundle 已接管）"
}


install_legacy() {
  # 复制流：安装到共享 node_modules + 手动 patch 接线
  mkdir -p "$DST_PROFILE"
  find "$PLUGIN" -maxdepth 1 -type f \
    ! -name "install.sh" ! -name "reapply-lan-patches.sh" ! -name "README.md" \
    -exec cp {} "$DST_PROFILE/" \;
  echo "  [已装] $DST_PROFILE"
  if [ ! -d "$DSH/profiles/web" ]; then
    echo "  [跳过] web profile 尚未初始化（$DSH/profiles/web 不存在）"
    echo "         请先运行一次 dsh web 完成初始化，再重跑本脚本接线"
    FAIL=1
  elif ! grep -qE "dsh-lan-(access|gateway)" "$PATCH2" 2>/dev/null; then
    sed -i '/^[[:space:]]*\\[\\][[:space:]]*$/d' "$PATCH2"
    cat >> "$PATCH2" <<'EOF'
- insert:
    - id: lan-access
      name: 'dsh-lan-gateway'
EOF
    echo "  [已加] $PATCH2"
  fi
}

if bundle_wired; then
  echo "  [已有] 官方 bundle 流已接线（web profile bundles 含 dsh-lan-gateway）"
  cleanup_legacy_lines "$PATCH2"
elif legacy_wired; then
  echo "  [已有] 旧复制流已接线（$DST_PROFILE + $PATCH2）"
else
  # 1) 用户层源码备份（持久位置，升级不丢；dsh plugin 的 link 指向这里）
  if [ "$MODE" != "--check" ]; then
    mkdir -p "$DST_PLUGINS"
    find "$PLUGIN" -maxdepth 1 -type f \
      ! -name "install.sh" ! -name "reapply-lan-patches.sh" ! -name "README.md" \
      -exec cp {} "$DST_PLUGINS/" \;
    echo "  [已装] $DST_PLUGINS（用户层源码，升级不丢）"
  fi
  # 2) 官方流：dsh plugin add（自动初始化 profile / pnpm 链接 / 追加 bundles 层）
  DSH_CMD=""
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then DSH_CMD="$ROOT/node_modules/.bin/dsh"; fi
  if [ -z "$DSH_CMD" ] && command -v dsh >/dev/null 2>&1; then DSH_CMD="dsh"; fi
  if [ "$MODE" = "--check" ]; then
    if [ -n "$DSH_CMD" ] && command -v pnpm >/dev/null 2>&1; then
      echo "  [缺失] 未接线（将执行 dsh plugin --profile web add，自动加层）"
    else
      echo "  [缺失] 未接线（无 dsh/pnpm，将走复制流）"
    fi
  elif [ -n "$DSH_CMD" ] && command -v pnpm >/dev/null 2>&1; then
    echo "  执行: $DSH_CMD plugin --profile web add $DST_PLUGINS"
    if "$DSH_CMD" plugin --profile web add "$DST_PLUGINS"; then
      echo "  [已装] 官方 bundle 流接线成功（bundles 层 + pnpm link）"
      cleanup_legacy_lines "$PATCH2"
    else
      echo "  [回退] dsh plugin add 失败，改用复制+手动接线"
      install_legacy
    fi
  else
    echo "  [回退] 无 dsh 或 pnpm，改用复制+手动接线"
    install_legacy
  fi
fi

# ── 3/6 访问令牌（第 3 层，令牌门卫的钥匙）─────────────────────────────────
TOKEN_FILE="$DSH/lan-access-token"
echo "== 3/6 访问令牌 =="
if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
  echo "  [已有] $TOKEN_FILE（修改令牌：直接编辑该文件，单行文本，保存即生效）"
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $TOKEN_FILE（将自动生成 48 位随机十六进制令牌）"
  FAIL=1
else
  TOKEN=$(node -e 'console.log(require("node:crypto").randomBytes(24).toString("hex"))' 2>/dev/null || true)
  [ -z "$TOKEN" ] && TOKEN=$(openssl rand -hex 24 2>/dev/null || true)
  if [ -z "$TOKEN" ]; then
    echo "  [失败] 无法生成随机令牌（需要 node 或 openssl）"
    FAIL=1
  else
    (umask 177; printf '%s\n' "$TOKEN" > "$TOKEN_FILE")
    chmod 600 "$TOKEN_FILE"
    echo "  [已生成] $TOKEN_FILE"
    echo ""
    echo "  ================================================================"
    echo "   局域网访问令牌（仅显示这一次，请妥善保存）："
    echo ""
    echo "   $TOKEN"
    echo ""
    echo "  ================================================================"
    echo ""
    echo "  使用方式（任一即可，登录页提交表单后自动种 Cookie）："
    echo "    - 浏览器首次访问会看到登录页，粘贴令牌即可进入"
    echo "    - curl -H \"X-DSH-Token: $TOKEN\" http://<IP>:3080/"
    echo "    - 浏览器直接访问 http://<IP>:3080/?token=$TOKEN"
    echo "  v3 起回环（localhost/127.0.0.1）同样出登录页——本机也需先过令牌。"
    echo "  注意：出现登录页 = 服务正常（HTTP 401 属预期，不是故障）。"
  fi
fi

# ── 4/6 补丁层（特权围栏 / 设置持久化 / 令牌门卫 / websocket 压缩）──────────
#
# ⚠️ 为什么**委托 reapply-lan-patches.sh**（2026-09-14 重构，勿改回内联三段）：
#   本脚本原先自己实现 4/5/6 三段，三段都按**顶层**
#   `${ROOT}/node_modules/@deepseek-ai/<pkg>` 定位，而 dsh 把包嵌在
#   `${ROOT}/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/<pkg>`
#   ⇒ `[ ! -f "$F" ]` 恒真：
#     ① `--check` 永久误报「缺失（该版本可能已无此文件，请人工确认）」；
#     ② **apply 模式同样落进该分支、静默跳过** —— 这三段补丁实际上从未生效过，
#        全靠 `reapply-lan-patches.sh` 兜住（2026-09-14 home-wsl 实证）；
#     ③ 而且本脚本**没有 7/7（websocket permessage-deflate）段**，
#        走 tarball 装机的机器拿不到 WS 压缩（慢链路症状会复现）。
#   ⇒ 补丁层收敛到 reapply 单一事实源：嵌套定位正确、段数完整（0/7–7/7）、
#     重启后的验证也更全（回环 401 / LAN 401 / ?token= 303 / 首页 200）。
#     两处实现同一逻辑 = 必然漂移，上面的误报就是漂移的产物。
REAPPLY="$DSH/reapply-lan-patches.sh"

# 先分发/更新恢复脚本 —— 补丁层的唯一入口
# ⚠️ 必须"总是覆盖"而不是 `! -f` 才拷：旧写法让**已有旧版 reapply 的机器永远停在旧逻辑**
#    （home-wsl 就带着 9/11 版、没有 7/7 段，而 install.sh 拒绝更新它 ⇒ 压缩补丁永远打不上）
if [ "$MODE" != "--check" ] && [ -f "$HERE/reapply-lan-patches.sh" ]; then
  if [ -f "$REAPPLY" ] && ! cmp -s "$HERE/reapply-lan-patches.sh" "$REAPPLY"; then
    cp "$REAPPLY" "$REAPPLY.bak-$(date +%Y%m%d-%H%M%S)"
    echo "  [更新] $REAPPLY（旧版已备份为 .bak-<时间戳>）"
  fi
  cp "$HERE/reapply-lan-patches.sh" "$DSH/" && chmod +x "$REAPPLY"
fi

echo "== 4/6 补丁层（特权围栏 / 设置持久化 / 令牌门卫 / websocket 压缩）=="
if [ ! -f "$REAPPLY" ]; then
  echo "  [缺失] $REAPPLY（安装包应自带 reapply-lan-patches.sh，请检查包完整性）"
  FAIL=1
elif [ "$MODE" = "--check" ]; then
  echo "  → 以下 0/7–7/7 为 reapply-lan-patches.sh 的输出"
  bash "$REAPPLY" --check
else
  bash "$REAPPLY" || FAIL=1
fi

if [ "$MODE" = "--check" ]; then
  echo "== 检查完成（未改动任何文件）=="
  [ "$FAIL" = "1" ] && echo "（存在缺失项，直接运行 bash install.sh 即可补齐）"
  exit 0
fi

# ── 可选重启并验证 ─────────────────────────────────────────────────────────
if [ "$MODE" = "--restart" ]; then
  echo "== 重启服务 =="
  # 统一重启逻辑：systemd 托管优先，回退 pkill（MR-026）
  if [ -f "$HERE/_dsh-common/dsh-restart.sh" ]; then
    # tarball 内自带共享重启脚本（package.sh 打入 _dsh-common/）
    . "$HERE/_dsh-common/dsh-restart.sh"
    restart_dsh "$ROOT"
  elif [ -f "$HERE/../../scripts/dsh-restart.sh" ]; then
    # 开发环境：dsh-plugins 仓库 scripts/
    . "$HERE/../../scripts/dsh-restart.sh"
    restart_dsh "$ROOT"
  else
    # 极端场景（无共享脚本）：内联完整重启逻辑（systemd → pkill 回退）
    SVC=""
    if command -v systemctl >/dev/null 2>&1; then
      for SVC in dsh.service dsh-web.service; do
        systemctl --user is-active --quiet "$SVC" 2>/dev/null && break
      done
    fi
    if [ -n "$SVC" ]; then
      echo "  [systemd] $SVC 托管中 → systemctl --user restart $SVC"
      systemctl --user restart "$SVC"
      sleep 6
      curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪"
    else
      echo "  [回退] 无 systemd 托管，pkill + 手动拉起"
      pkill -TERM -f "dsh web" 2>/dev/null
      pkill -TERM -f 'node_modules/.bin/dsh web' 2>/dev/null
      pkill -TERM -f 'npm exec @deepseek-ai/dsh web' 2>/dev/null
      pkill -TERM -f 'sh -c dsh web' 2>/dev/null
      pkill -TERM -f 'dsh/lib/bin.js web' 2>/dev/null
      sleep 3
      if [ -n "$(command -v dsh 2>/dev/null)" ]; then
        cd "$ROOT" || exit 1
        setsid nohup "$(command -v dsh)" web >> /tmp/dsh-web.log 2>&1 < /dev/null &
        echo "  新进程 PID=$!"
        sleep 8
        curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪"
      else
        echo "  [警告] 无法定位 dsh 可执行文件，请手动重启 dsh web"
      fi
    fi
  fi
  # ⚠️ 判据用「PATH 里有 dsh」而不是 `$ROOT/node_modules/.bin/dsh`：全局安装
  #    （npm i -g / ~/.local/node、~/.npm-global）下 .bin 在 <prefix>/bin，
  #    $ROOT/node_modules/.bin/ 并不存在 ⇒ 旧判据为假、整段验证被跳过并误报
  #    「无法定位 dsh 可执行文件」（2026-09-14 home-wsl 实证）。
  DSH_BIN="$(command -v dsh 2>/dev/null || true)"
  if [ -n "$DSH_BIN" ]; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    TOKEN=""
    [ -f "$DSH/lan-access-token" ] && TOKEN=$(cat "$DSH/lan-access-token")
    curl -s --noproxy '*' -o /dev/null -w '127.0.0.1:3080 页面（v3：无凭据应 401 登录页）-> %{http_code}\n' http://127.0.0.1:3080/
    curl -s --noproxy '*' http://127.0.0.1:3080/ | grep -q '访问验证' \
      && echo '  回环登录页内容 -> OK（含「访问验证」表单）' \
      || echo '  [警告] 回环未返回登录页（补丁未生效？）'
    if [ -n "$IP" ]; then
      curl -s --noproxy '*' -o /dev/null -w "$IP:3080 无令牌（应 401 登录页）-> %{http_code}\n" "http://$IP:3080/"
      if [ -n "$TOKEN" ]; then
        curl -s --noproxy '*' -o /dev/null -w "$IP:3080 ?token=（应 303 + 种 Cookie）-> %{http_code}\n" "http://$IP:3080/?token=$TOKEN"
        curl -s --noproxy '*' -o /dev/null -w 'LAN Host settings.describe（带令牌，应非 403）-> %{http_code}\n' -H "Host: $IP:3080" -H "X-DSH-Token: $TOKEN" -X POST http://127.0.0.1:3080/api/settings.describe
      fi
    fi
    # 端到端：用 ?token= 换 host browserAuth cookie，再取首页（旧的
    # /plugins/<id>/client.js 检查在 dsh 0.1.5 已失效——客户端插件走 /plugins/??a,b&rev= 聚合 URL）。
    COOKIE=$(curl -s --noproxy '*' -D - -o /dev/null "http://127.0.0.1:3080/?token=$TOKEN" | grep -i '^set-cookie' | head -1 | sed 's/^[Ss]et-[Cc]ookie: //' | cut -d';' -f1)
    if [ -n "$COOKIE" ]; then
      curl -s --noproxy '*' -o /dev/null -w '应用首页（带 browserAuth cookie，应 200）-> %{http_code}\n' -H "Cookie: $COOKIE" http://127.0.0.1:3080/
    else
      echo '  [警告] 未换到 browserAuth cookie（token 与运行实例不一致？）'
    fi
    echo "== 完成 =="
  else
    echo "  无法定位 dsh 可执行文件，请手动重启 dsh web"
  fi
fi