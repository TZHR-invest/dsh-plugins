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
#   3. 访问令牌                  -> ~/.dsh/lan-access-token（LAN 访问必须持有，回环豁免）
#   4. 特权围栏放行              -> dsh-client-connection 一行补丁（dsh 升级后可能被覆盖，
#                                  届时重跑本脚本或 ~/.dsh/reapply-lan-patches.sh 即可）
#   5. 设置持久化放行            -> dsh-client-ui-settings 一行补丁
#   6. 令牌门卫                  -> dsh-host-webserver 入口补丁（401 登录页 + WebSocket 拦截）
#
# 安全说明：0.0.0.0 会让局域网内任何设备可访问本 GUI（可驱动 agent 执行命令）。
# 本包为其增加访问令牌验证：非本机（回环）请求必须携带令牌
# （Cookie / ?token= / X-DSH-Token / 登录页表单），未授权一律 401。
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
if [ ! -f "$PLUGIN/token-gate.js" ] || [ ! -f "$PLUGIN/patch-webserver.mjs" ]; then
  echo "  错误：安装包缺少令牌门卫补丁源（token-gate.js / patch-webserver.mjs）"; exit 1
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
PATCH1="$DSH/cordis.patch.yml"
echo "== 1/6 webserver 绑定 0.0.0.0 =="
if [ -f "$PATCH1" ] && grep -q 'id: webserver' "$PATCH1" 2>/dev/null; then
  if grep -q "0.0.0.0" "$PATCH1"; then
    echo "  [已有] $PATCH1"
  else
    echo "  [跳过] $PATCH1 已有 webserver 配置但未绑定 0.0.0.0，为避免覆盖你的配置，请人工修改"
    FAIL=1
  fi
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $PATCH1 中的 webserver 0.0.0.0 条目"
else
  mkdir -p "$DSH"
  cat >> "$PATCH1" <<'EOF'
- id: webserver
  config:
    host: '0.0.0.0'
    port: 3080
EOF
  echo "  [已加] $PATCH1"
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
    echo "  回环（localhost/127.0.0.1）访问豁免，无需令牌。"
  fi
fi

# ── 4/6 特权围栏补丁（第 4 层，唯一留在 node_modules 的补丁）───────────────
echo "== 4/6 特权围栏补丁 =="
if [ -z "$ROOT" ]; then
  echo "  [跳过] 未定位 dsh 安装目录"
elif [ ! -d "$ROOT/node_modules/@deepseek-ai" ]; then
  echo "  [跳过] $ROOT 下无 @deepseek-ai 包，请人工确认 dsh 安装位置"
else
  F="$ROOT/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js"
  if grep -q 'PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, trustedHosts)' "$F" 2>/dev/null; then
    echo "  [已有] $F"
  elif [ ! -f "$F" ]; then
    echo "  [缺失] $F（该版本可能已无此文件，请人工确认）"
    FAIL=1
  elif [ "$MODE" = "--check" ]; then
    echo "  [缺失] 特权围栏"
  else
    sed -i 's/PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, [[]])/PRIVILEGED_METHODS.has(method) \&\& !isTrustedApiRequest(request, trustedHosts)/' "$F"
    if grep -q 'PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, trustedHosts)' "$F"; then
      echo "  [已打] 特权围栏"
    else
      echo "  [失败] 特权围栏——该版本代码结构已变化，请人工处理"
      FAIL=1
    fi
  fi
  [ -f "$F" ] && node --check "$F" 2>/dev/null && echo "  语法 OK"
fi


# ── 5/6 设置持久化放行补丁（第 5 层：浏览器端 settingsScope 强制 host 模式）─
echo "== 5/6 设置持久化放行补丁 =="
if [ -z "$ROOT" ]; then
  echo "  [跳过] 未定位 dsh 安装目录"
elif [ ! -d "$ROOT/node_modules/@deepseek-ai" ]; then
  echo "  [跳过] $ROOT 下无 @deepseek-ai 包，请人工确认 dsh 安装位置"
else
  F4="$ROOT/node_modules/@deepseek-ai/dsh-client-ui-settings/lib/client.js"
  if grep -q 'new SettingsScopeController(connection.api, spec, "host")' "$F4" 2>/dev/null; then
    echo "  [已有] 设置持久化放行"
  elif [ ! -f "$F4" ]; then
    echo "  [缺失] $F4（该版本可能已无此文件，请人工确认）"
    FAIL=1
  elif [ "$MODE" = "--check" ]; then
    echo "  [缺失] 设置持久化放行"
  else
    sed -i 's/connection\.isLoopback ? "host" : "memory"/"host"/' "$F4"
    if grep -q 'new SettingsScopeController(connection.api, spec, "host")' "$F4"; then
      echo "  [已打] 设置持久化放行（LAN 访问也可读写设置）"
    else
      echo "  [失败] 设置持久化放行——该版本代码结构已变化，请人工处理"
      FAIL=1
    fi
  fi
  [ -f "$F4" ] && node --check "$F4" 2>/dev/null && echo "  语法 OK"
fi

# ── 6/6 webserver 令牌门卫补丁（第 6 层）────────────────────────────────────
echo "== 6/6 webserver 令牌门卫补丁 =="
if [ -z "$ROOT" ]; then
  echo "  [跳过] 未定位 dsh 安装目录"
elif [ ! -d "$ROOT/node_modules/@deepseek-ai" ]; then
  echo "  [跳过] $ROOT 下无 @deepseek-ai 包，请人工确认 dsh 安装位置"
else
  FW="$ROOT/node_modules/@deepseek-ai/dsh-host-webserver/lib/index.js"
  if [ ! -f "$FW" ]; then
    echo "  [缺失] $FW（该版本可能已无此文件，请人工确认）"
    FAIL=1
  elif [ "$MODE" = "--check" ]; then
    if node "$PLUGIN/patch-webserver.mjs" "$FW" --check; then
      echo "  [已有] webserver 令牌门卫"
    else
      echo "  [缺失] webserver 令牌门卫"
    fi
  else
    if node "$PLUGIN/patch-webserver.mjs" "$FW"; then
      echo "  [已打] webserver 令牌门卫（LAN 未授权请求将看到 401 登录页）"
    else
      echo "  [失败] webserver 令牌门卫——请人工处理"
      FAIL=1
    fi
    [ -f "$FW" ] && node --check "$FW" 2>/dev/null && echo "  语法 OK"
  fi
fi

# ── 附加：分发升级恢复脚本 ─────────────────────────────────────────────────
if [ -f "$HERE/reapply-lan-patches.sh" ] && [ ! -f "$DSH/reapply-lan-patches.sh" ] && [ "$MODE" != "--check" ]; then
  cp "$HERE/reapply-lan-patches.sh" "$DSH/"
  echo "== 附加 =="
  echo "  [已装] $DSH/reapply-lan-patches.sh（dsh 升级后用它恢复）"
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
    if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet dsh.service 2>/dev/null; then
      echo "  [systemd] dsh.service 托管中 → systemctl --user restart dsh"
      systemctl --user restart dsh.service
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
      if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
        cd "$ROOT" || exit 1
        setsid nohup ./node_modules/.bin/dsh web >> /tmp/dsh-web.log 2>&1 < /dev/null &
        echo "  新进程 PID=$!"
        sleep 8
        curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪"
      else
        echo "  [警告] 无法定位 dsh 可执行文件，请手动重启 dsh web"
      fi
    fi
  fi
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    TOKEN=""
    [ -f "$DSH/lan-access-token" ] && TOKEN=$(cat "$DSH/lan-access-token")
    curl -s --noproxy '*' -o /dev/null -w '127.0.0.1:3080 页面（回环豁免，应 200）-> %{http_code}\n' http://127.0.0.1:3080/
    if [ -n "$IP" ]; then
      curl -s --noproxy '*' -o /dev/null -w "$IP:3080 无令牌（应 401 登录页）-> %{http_code}\n" "http://$IP:3080/"
      if [ -n "$TOKEN" ]; then
        curl -s --noproxy '*' -o /dev/null -w "$IP:3080 带令牌（应 200）-> %{http_code}\n" -H "X-DSH-Token: $TOKEN" "http://$IP:3080/"
        curl -s --noproxy '*' -o /dev/null -w 'LAN Host settings.describe（带令牌，应非 403）-> %{http_code}\n' -H "Host: $IP:3080" -H "X-DSH-Token: $TOKEN" -X POST http://127.0.0.1:3080/api/settings.describe
      fi
    fi
    curl -s --noproxy '*' -o /dev/null -w '插件 bundle（应 200）-> %{http_code}\n' http://127.0.0.1:3080/plugins/dsh-lan-gateway/client.js
    echo "== 完成 =="
  else
    echo "  无法定位 dsh 可执行文件，请手动重启 dsh web"
  fi
fi