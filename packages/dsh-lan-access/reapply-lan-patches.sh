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
#   6. 令牌门卫            -> dsh-host-webserver 入口补丁 v3（会被升级覆盖，本脚本重打；
#                            含回环登录页 + index-401 兜底）
set -u

MODE="${1:-apply}"
DSH="${DSH_HOME:-$HOME/.dsh}"

# ── 0/7 用户层 webserver 绑定 + 压缩配置自检（2026-09-11 新增）──────────────
#
# 为什么需要：$DSH/cordis.patch.yml 里的 `- id: webserver` 行会**整体替换**
# dsh-web-app bundle 的该行 config，而 bundle 原本自带 `compression: gzip`。
# 旧版 install.sh 只写 host/port，于是压缩被静默关闭 —— 所有响应不压缩，
# 客户端插件聚合包 11.2MB 原样传输，慢链路（tailscale DERP）上要 73 秒，
# 表现为浏览器长期停在 "Loading plugins…"。这里负责检测并补齐。
#
# 注：与脚本其余检查一致，--check 只用文本 [缺失]/[已有] 报告、**不改文件也不改退出码**
#     （本脚本的约定是 --check 恒 exit 0，靠读输出判断）。
echo "== 0/7 webserver 绑定与压缩自检 =="
PATCH_TOP="$DSH/cordis.patch.yml"
if [ ! -f "$PATCH_TOP" ] || ! grep -q 'id: webserver' "$PATCH_TOP" 2>/dev/null; then
  echo "  [缺失] $PATCH_TOP 无 webserver 绑定（局域网可能无法访问；重装 install.sh 可修）"
elif ! grep -q 'compression:' "$PATCH_TOP" 2>/dev/null; then
  if [ "$MODE" = "--check" ]; then
    echo "  [缺失] $PATCH_TOP 缺 compression* → 响应不压缩（慢链路会明显变慢）"
  else
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
    ' "$PATCH_TOP" > "$PATCH_TOP.tmp-compress" && mv "$PATCH_TOP.tmp-compress" "$PATCH_TOP"
    echo "  [已补] compression: gzip（自定义 profile 的用户层 patch 为热加载，数秒内自动生效、无需重启）"
  fi
else
  echo "  [已有] webserver 绑定 + compression"
fi

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
# 定位 dsh 安装根（2026-09-14 扩策略）。
# ⚠️ 为什么改：原实现只认「pgrep 'dsh web' 的 cwd」→ npm root -g → npx 缓存，
# 而 office_64g 三条全不成立（cmdline 是 `<abs>/lib/bin.js web`（不含 "dsh web" 子串）、
# cwd=/（watchdog 先 cd /）、**该机无 npm**）⇒ ROOT 为空 ⇒ 第 4/5/6 层补丁被静默跳过，
# 表现为"脚本跑了"但门卫没恢复（2026-09-14 实测：--check 在 3/6 直接报"找不到 dsh 安装目录"）。
# 策略顺序：
#   ① 监听 3080 的进程 cmdline（argv[1] = dsh bin.js 绝对路径，最准）
#   ② 运行中进程的 cwd（devbox 的 systemd WorkingDirectory 指向安装根）
#   ③ 已知安装位置（npm root -g，其次常见前缀，含 ~/.local/node）
#   ④ ~/.npm/_npx 缓存
# 以 dsh-client-connection 存在为准（MR-025）。
ROOT=""
DSH_ENTRY_RE='bin\.js web|dsh web|node_modules/\.bin/dsh web'

PID=$(ss -ltnp 2>/dev/null | awk '/:3080 /{print $NF}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
[ -z "${PID:-}" ] && PID=$(pgrep -f "$DSH_ENTRY_RE" 2>/dev/null | head -1)
if [ -n "${PID:-}" ] && [ "$PID" != "$$" ]; then
  EXE=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null | awk '{print $2}')
  if [ -n "${EXE:-}" ] && [ -e "$EXE" ]; then
    CAND=$(dirname "$(dirname "$(readlink -f "$EXE")")")
    [ -d "$CAND/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$CAND"
  fi
fi
if [ -z "$ROOT" ]; then
  for PID in $(pgrep -f "$DSH_ENTRY_RE" 2>/dev/null); do
    [ "$PID" = "$$" ] && continue
    CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
    [ -n "$CWD" ] && [ -d "$CWD/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$CWD" && break
  done
fi
if [ -z "$ROOT" ]; then
  for G in "$(npm root -g 2>/dev/null)" "$HOME/.npm-global/lib/node_modules" \
           "$HOME/.local/node/lib/node_modules" /opt/node/lib/node_modules \
           "$HOME"/.nvm/versions/node/*/lib/node_modules; do
    if [ -n "$G" ] && [ -d "$G/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-client-connection" ]; then
      ROOT="$G/@deepseek-ai/dsh"; break
    fi
  done
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
if grep -q 'isTrustedApiRequest(request, this.trustedHosts)' "$F" 2>/dev/null; then
  echo "  [已有] 特权围栏（0.1.2+ 官方原生 trustedHosts 实现，无需补丁）"
elif grep -q 'PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, trustedHosts)' "$F" 2>/dev/null; then
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
if [ ! -f "$F4" ]; then
  echo "  [缺失] $F4（该版本可能已无此文件，请人工确认）"
elif grep -q 'ctx\.remote\.\$host\.isLoopback ? "host" : "memory"' "$F4" 2>/dev/null; then
  # 0.1.2+ 结构：persistence 由客户端按 isLoopback 选择，需强制 host 使 LAN 可写设置
  if [ "$MODE" = "--check" ]; then
    echo "  [缺失] 设置持久化放行（0.1.2+ 结构）"
  else
    sed -i 's/ctx\.remote\.\$host\.isLoopback ? "host" : "memory"/"host"/' "$F4"
    if ! grep -q 'ctx\.remote\.\$host\.isLoopback ? "host" : "memory"' "$F4" && grep -q 'const persistence = "host"' "$F4"; then
      echo "  [已打] 设置持久化放行（0.1.2+ 结构，LAN 访问也可读写设置）"
    else
      echo "  [失败] 设置持久化放行——0.1.2+ 结构适配失败，请人工处理"
    fi
  fi
elif grep -q 'const persistence = "host"' "$F4" 2>/dev/null; then
  echo "  [已有] 设置持久化放行（0.1.2+ 结构已打）"
elif grep -q 'new SettingsScopeController(connection.api, spec, "host")' "$F4" 2>/dev/null; then
  echo "  [已有] 设置持久化放行"
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
  node "$SRC/patch-webserver.mjs" "$FW" --check
  case $? in
    0) echo "  [已有] webserver 令牌门卫 v3" ;;
    3) echo "  [旧版] webserver 令牌门卫（运行本脚本即可就地升级 v3）" ;;
    *) echo "  [缺失] webserver 令牌门卫" ;;
  esac
else
  if node "$SRC/patch-webserver.mjs" "$FW"; then
    echo "  [已完成] webserver 令牌门卫 v3（未授权请求 = 401 登录页，含回环）"
  else
    echo "  [失败] webserver 令牌门卫——请人工处理"
  fi
  [ -f "$FW" ] && node --check "$FW" 2>/dev/null && echo "  语法 OK"
fi

# ── 6/6 client-connection 局域网令牌补丁（dsh 0.1.2+：launch token 固定 +
#      X-DSH-Token API 通道；配合 5/6 门卫 v2 完成 LAN 浏览器/API 闭环）─────────
echo "== 6/6 client-connection 局域网令牌补丁 =="
FC="$ROOT/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js"
if [ ! -f "$SRC/patch-client-connection.mjs" ]; then
  echo "  [缺失] $SRC/patch-client-connection.mjs（插件源码不完整，请更新 dsh-lan-gateway/dsh-lan-access 至含 0.1.2 适配版本）"
elif [ "$MODE" = "--check" ]; then
  if node "$SRC/patch-client-connection.mjs" "$FC" --check; then
    echo "  [已有] client-connection 令牌补丁"
  else
    echo "  [缺失] client-connection 令牌补丁"
  fi
else
  if node "$SRC/patch-client-connection.mjs" "$FC"; then
    echo "  [已打] client-connection 令牌补丁（launch token 固定 + X-DSH-Token API 通道）"
  else
    echo "  [失败] client-connection 令牌补丁——请人工处理"
  fi
  [ -f "$FC" ] && node --check "$FC" 2>/dev/null && echo "  语法 OK"
fi

# ── 7/7 websocket 响应压缩补丁（permessage-deflate，2026-09-14 新增）──────────
# 为什么：WS 帧**不走 HTTP 的 gzip** —— 打开历史会话时服务端一次性回一帧
#   0.8–1.2 MB 的 JSON（消息正文/工具输出/thinking 签名），手机那条 ~10 KB/s
#   链路上要 ~120 秒，前端表现为"一直显示正在加载"。开压缩实测 1.20 MB → 255 KB
#   （4.80x）；ws 默认 threshold=1024，小于 1 KB 的小帧（事件流）不压缩。
# ⚠️ 生效需**重启该机 dsh web**（WebSocketServer 在进程启动时构造）。
echo "== 7/7 websocket 响应压缩补丁 =="
FG="$ROOT/node_modules/@deepseek-ai/dsh-api-gateway"
if [ ! -f "$SRC/patch-ws-deflate.mjs" ]; then
  echo "  [缺失] $SRC/patch-ws-deflate.mjs（插件源码不完整，请更新 dsh-lan-access）"
elif [ "$MODE" = "--check" ]; then
  if node "$SRC/patch-ws-deflate.mjs" "$FG" --check; then
    echo "  [已有] websocket permessage-deflate（重启 dsh web 后才生效）"
  else
    echo "  [缺失] websocket permessage-deflate（慢链路上打开历史会话要多传约 4 倍字节）"
  fi
else
  if node "$SRC/patch-ws-deflate.mjs" "$FG"; then
    echo "  [已完成] websocket permessage-deflate（重启该机 dsh web 后生效）"
  else
    echo "  [失败] websocket 响应压缩补丁——请人工处理"
  fi
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
  if [ -f "$HERE/_dsh-common/dsh-restart.sh" ]; then
    # tarball 内自带共享重启脚本（package.sh 打入 _dsh-common/）
    . "$HERE/_dsh-common/dsh-restart.sh"
    restart_dsh "$ROOT"
  elif [ -f "$HERE/../../scripts/dsh-restart.sh" ]; then
    # 开发环境：dsh-plugins 仓库 scripts/
    . "$HERE/../../scripts/dsh-restart.sh"
    restart_dsh "$ROOT"
  elif [ -f "$HOME/dsh-plugins/scripts/dsh-restart.sh" ]; then
    . "$HOME/dsh-plugins/scripts/dsh-restart.sh"
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
  # 端到端：用 ?token= 换 host browserAuth cookie，再取首页（旧的 /plugins/<id>/client.js
  # 检查在 dsh 0.1.5 已失效——客户端插件走 /plugins/??a,b&rev= 聚合 URL，单包路径必 404）。
  COOKIE=$(curl -s --noproxy '*' -D - -o /dev/null "http://127.0.0.1:3080/?token=$TOKEN" | grep -i '^set-cookie' | head -1 | sed 's/^[Ss]et-[Cc]ookie: //' | cut -d';' -f1)
  if [ -n "$COOKIE" ]; then
    curl -s --noproxy '*' -o /dev/null -w '应用首页（带 browserAuth cookie，应 200）-> %{http_code}\n' -H "Cookie: $COOKIE" http://127.0.0.1:3080/
  else
    echo '  [警告] 未换到 browserAuth cookie（token 与运行实例不一致？）'
  fi
  echo "== 完成 =="
fi