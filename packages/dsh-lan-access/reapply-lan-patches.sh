#!/bin/bash
# reapply-lan-patches.sh — @deepseek-ai/dsh 升级/重装后，恢复局域网访问支持（幂等，可反复执行）。
#
# 用法:
#   bash ~/.dsh/reapply-lan-patches.sh            # 检查并补齐缺失的补丁
#   bash ~/.dsh/reapply-lan-patches.sh --check    # 只报告状态，不改文件
#   bash ~/.dsh/reapply-lan-patches.sh --restart  # 补齐后重启服务并验证
#
# 局域网访问支持由六层组成：
#   1. 绑定 0.0.0.0       -> ~/.dsh/cordis.patch.yml（用户配置层，升级不丢）
#   2. crypto.randomUUID  -> dsh-lan-access 客户端插件（用户插件层，升级不丢，
#                            本脚本负责从 ~/.dsh/plugins 重新安装 + 接线）
#   3. 访问令牌           -> ~/.dsh/lan-access-token（升级不丢；缺失时自动重新生成）
#   4. 特权围栏放行        -> node_modules 一行补丁（会被升级覆盖，本脚本重打）
#   5. 设置持久化放行      -> node_modules 一行补丁（会被升级覆盖，本脚本重打）
#   6. 令牌门卫            -> dsh-host-webserver 入口补丁（会被升级覆盖，本脚本重打）
set -u

MODE="${1:-apply}"
DSH="${DSH_HOME:-$HOME/.dsh}"

# ── 1/6 插件安装与接线（官方 bundle 流优先，复制流回退）──────────────────
if [ -d "$DSH/plugins/dsh-lan-gateway" ]; then
  SRC="$DSH/plugins/dsh-lan-gateway"; DST="$DSH/profiles/node_modules/dsh-lan-gateway"
else
  SRC="$DSH/plugins/dsh-lan-access"; DST="$DSH/profiles/node_modules/dsh-lan-access"
fi
PATCH="$DSH/profiles/web/cordis.patch.yml"
echo "== 1/6 插件安装与接线 =="

bundle_wired() {
  [ -f "$DSH/profiles/web/package.json" ] && grep -qE '"(dsh-lan-access|dsh-lan-gateway)"' "$DSH/profiles/web/package.json"
}
legacy_wired() {
  [ -f "$DST/client.js" ] && grep -q "randomUUID" "$DST/client.js" 2>/dev/null \
    && [ -f "$PATCH" ] && grep -q 'id: lan-access' "$PATCH"
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
  if [ ! -d "$SRC" ]; then
    echo "  [缺失] 插件源码 $SRC 不存在，请人工恢复"
    return 1
  fi
  if [ ! -f "$DST/client.js" ]; then
    mkdir -p "$DST" && cp "$SRC"/* "$DST/" && echo "  [已装] $DST"
  fi
  if grep -qE "dsh-lan-(access|gateway)" "$PATCH" 2>/dev/null; then
    echo "  [已有] $PATCH"
  else
    sed -i '/^[[:space:]]*\\[\\][[:space:]]*$/d' "$PATCH"
    printf -- "- insert:\n    - id: lan-access\n      name: 'dsh-lan-gateway'\n" >> "$PATCH"
    echo "  [已加] $PATCH"
  fi
}

if bundle_wired; then
  echo "  [已有] 官方 bundle 流已接线（web profile bundles 含 dsh-lan-gateway）"
  cleanup_legacy_lines "$PATCH"
elif legacy_wired; then
  echo "  [已有] 旧复制流已接线（$DST + $PATCH）"
elif [ ! -d "$SRC" ]; then
  echo "  [缺失] 插件源码 $SRC 不存在，请人工恢复"
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] 未接线（将执行 dsh plugin --profile web add $SRC）"
else
  # 官方流：dsh plugin add（自动 pnpm 链接 + 追加 bundles 层）
  DSH_CMD=""
  command -v dsh >/dev/null 2>&1 && DSH_CMD="dsh"
  if [ -z "$DSH_CMD" ]; then
    for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
      d=${d%/}
      [ -x "$d/node_modules/.bin/dsh" ] && { DSH_CMD="$d/node_modules/.bin/dsh"; break; }
    done
  fi
  if [ -n "$DSH_CMD" ] && command -v pnpm >/dev/null 2>&1; then
    echo "  执行: $DSH_CMD plugin --profile web add $SRC"
    if "$DSH_CMD" plugin --profile web add "$SRC"; then
      echo "  [已装] 官方 bundle 流接线成功"
      cleanup_legacy_lines "$PATCH"
    else
      echo "  [回退] dsh plugin add 失败，改用复制+手动接线"
      install_legacy || exit 1
    fi
  else
    echo "  [回退] 无 dsh 或 pnpm，改用复制+手动接线"
    install_legacy || exit 1
  fi
fi

# ── 2/6 访问令牌（升级不丢；缺失时重新生成）────────────────────────────────
TOKEN_FILE="$DSH/lan-access-token"
echo "== 2/6 访问令牌 =="
if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
  echo "  [已有] $TOKEN_FILE"
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $TOKEN_FILE（将自动生成随机令牌）"
else
  TOKEN=$(node -e 'console.log(require("node:crypto").randomBytes(24).toString("hex"))' 2>/dev/null || true)
  [ -z "$TOKEN" ] && TOKEN=$(openssl rand -hex 24 2>/dev/null || true)
  if [ -z "$TOKEN" ]; then
    echo "  [失败] 无法生成随机令牌（需要 node 或 openssl）"
  else
    (umask 177; printf '%s\n' "$TOKEN" > "$TOKEN_FILE")
    chmod 600 "$TOKEN_FILE"
    echo "  [已生成] $TOKEN_FILE"
    echo "  局域网访问令牌（仅显示这一次）：$TOKEN"
  fi
fi

# ── 3/6 特权围栏补丁（唯一留在 node_modules 的补丁）────────────────────────
# 定位 dsh 安装根：优先从正在运行的 dsh web 进程推导（其 cwd 即安装根，覆盖
# npm 全局安装 node ~/.npm-global/bin/dsh web 的场景），其次 npm root -g，
# 最后回退 ~/.npm/_npx 缓存。以 dsh-client-connection 存在为准（MR-025）。
ROOT=""
for PID in $(pgrep -f "dsh web" 2>/dev/null); do
  [ "$PID" = "$$" ] && continue
  CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
  [ -n "$CWD" ] && [ -d "$CWD/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$CWD" && break
done
if [ -z "$ROOT" ]; then
  G=$(npm root -g 2>/dev/null || true)
  [ -n "$G" ] && [ -d "$G/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$G/@deepseek-ai/dsh"
fi
if [ -z "$ROOT" ]; then
  for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
    d=${d%/}
    [ -d "$d/node_modules/@deepseek-ai/dsh-client-connection" ] || continue
    ROOT="$d"
    break
  done
fi
echo "== 3/6 特权围栏补丁 =="
if [ -z "$ROOT" ]; then
  echo "  错误：找不到 dsh 安装目录"; exit 1
fi
echo "  安装目录: $ROOT"
F="$ROOT/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js"
if grep -q 'PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, trustedHosts)' "$F" 2>/dev/null; then
  echo "  [已有] 特权围栏"
elif [ -f "$F" ]; then
  if [ "$MODE" = "--check" ]; then
    echo "  [缺失] 特权围栏"
  else
    sed -i 's/PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, [[]])/PRIVILEGED_METHODS.has(method) \&\& !isTrustedApiRequest(request, trustedHosts)/' "$F"
    if grep -q 'PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, trustedHosts)' "$F"; then
      echo "  [已打] 特权围栏"
    else
      echo "  [失败] 特权围栏——该版本代码结构已变化，请人工处理"
    fi
  fi
else
  echo "  [缺失] $F（该版本可能已无此文件，请人工确认）"
fi
node --check "$F" 2>/dev/null && echo "  语法 OK"

# ── 4/6 设置持久化放行补丁（第 5 层：浏览器端 settingsScope 强制 host 模式）─
echo "== 4/6 设置持久化放行补丁 =="
F4="$ROOT/node_modules/@deepseek-ai/dsh-client-ui-settings/lib/client.js"
if grep -q 'new SettingsScopeController(connection.api, spec, "host")' "$F4" 2>/dev/null; then
  echo "  [已有] 设置持久化放行"
elif [ ! -f "$F4" ]; then
  echo "  [缺失] $F4（该版本可能已无此文件，请人工确认）"
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] 设置持久化放行"
else
  sed -i 's/connection\.isLoopback ? "host" : "memory"/"host"/' "$F4"
  if grep -q 'new SettingsScopeController(connection.api, spec, "host")' "$F4"; then
    echo "  [已打] 设置持久化放行（LAN 访问也可读写设置）"
  else
    echo "  [失败] 设置持久化放行——该版本代码结构已变化，请人工处理"
  fi
fi
[ -f "$F4" ] && node --check "$F4" 2>/dev/null && echo "  语法 OK"

# ── 5/6 webserver 令牌门卫补丁 ─────────────────────────────────────────────
echo "== 5/6 webserver 令牌门卫补丁 =="
FW="$ROOT/node_modules/@deepseek-ai/dsh-host-webserver/lib/index.js"
if [ ! -f "$SRC/patch-webserver.mjs" ]; then
  echo "  [缺失] $SRC/patch-webserver.mjs（插件源码不完整，请重新安装 dsh-lan-gateway）"
elif [ "$MODE" = "--check" ]; then
  if node "$SRC/patch-webserver.mjs" "$FW" --check; then
    echo "  [已有] webserver 令牌门卫"
  else
    echo "  [缺失] webserver 令牌门卫"
  fi
else
  if node "$SRC/patch-webserver.mjs" "$FW"; then
    echo "  [已打] webserver 令牌门卫（LAN 未授权请求将看到 401 登录页）"
  else
    echo "  [失败] webserver 令牌门卫——请人工处理"
  fi
  [ -f "$FW" ] && node --check "$FW" 2>/dev/null && echo "  语法 OK"
fi

if [ "$MODE" = "--check" ]; then
  echo "== 检查完成（未改动任何文件）=="
  exit 0
fi

# ── 可选重启 ───────────────────────────────────────────────────────────────
if [ "$MODE" = "--restart" ]; then
  echo "== 重启服务 =="
  # 统一重启逻辑：systemd 托管优先，回退 pkill（MR-026）
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$HERE/../../scripts/dsh-restart.sh" ]; then
    . "$HERE/../../scripts/dsh-restart.sh"
    restart_dsh "$ROOT"
  elif [ -f "$HOME/dsh-plugins/scripts/dsh-restart.sh" ]; then
    . "$HOME/dsh-plugins/scripts/dsh-restart.sh"
    restart_dsh "$ROOT"
  else
    echo "  [警告] 未找到共享 dsh-restart.sh，请手动重启: systemctl --user restart dsh"
  fi
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
fi