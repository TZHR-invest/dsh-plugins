#!/bin/bash
# install.sh — dsh 局域网访问支持 一键安装（新机器部署 / 重装恢复）
# 随安装包分发：本脚本 + dsh-lan-access/（插件源码）。
#
# 用法:
#   bash install.sh            # 安装全部三层（幂等，可反复执行）
#   bash install.sh --check    # 只报告状态，不修改任何文件
#   bash install.sh --restart  # 安装后重启 dsh web 并验证（会中断当前 web 服务几秒）
#
# 局域网访问由三层组成：
#   1. webserver 绑定 0.0.0.0    -> ~/.dsh/cordis.patch.yml（用户配置层）
#   2. crypto.randomUUID 插件    -> ~/.dsh/plugins/dsh-lan-access/ + profile 安装 + 组合接线
#   3. 特权围栏放行              -> dsh-client-connection 一行补丁（dsh 升级后可能被覆盖，
#                                   届时重跑本脚本或 ~/.dsh/reapply-lan-patches.sh 即可）
#
# 安全提示：0.0.0.0 会让局域网内任何设备可访问本 GUI（可驱动 agent 执行命令），
# 仅限可信局域网使用，勿暴露公网。
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

echo "== dsh-lan-access 一键安装（mode: $MODE）=="
echo "  DSH 目录: $DSH"
echo "  安装包目录: $HERE"

# ── 0/4 前置检查：安装包完整性 + 定位 dsh 安装根 ───────────────────────────
echo "== 0/4 前置检查 =="
if [ ! -f "$PLUGIN/package.json" ] || [ ! -f "$PLUGIN/client.js" ]; then
  echo "  错误：安装包缺少 dsh-lan-access/ 插件源码（$PLUGIN 不完整）"; exit 1
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
  echo "         第 3 层特权围栏将跳过。请先安装并启动过 @deepseek-ai/dsh。"
  FAIL=1
fi

# ── 1/4 webserver 绑定 0.0.0.0（第 1 层）───────────────────────────────────
PATCH1="$DSH/cordis.patch.yml"
echo "== 1/4 webserver 绑定 0.0.0.0 =="
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

# ── 2/4 插件安装（第 2 层前半：源码 + profile 安装目录）────────────────────
echo "== 2/4 插件安装 =="
DST_PLUGINS="$DSH/plugins/dsh-lan-access"
DST_PROFILE="$DSH/profiles/node_modules/dsh-lan-access"
if [ -f "$DST_PROFILE/client.js" ] && grep -q "randomUUID" "$DST_PROFILE/client.js" 2>/dev/null; then
  echo "  [已有] $DST_PROFILE"
else
  if [ "$MODE" = "--check" ]; then
    echo "  [缺失] $DST_PROFILE（可安装）"
  else
    mkdir -p "$DST_PLUGINS" "$DST_PROFILE"
    for d in "$DST_PLUGINS" "$DST_PROFILE"; do
      mkdir -p "$d"
      find "$PLUGIN" -maxdepth 1 -type f \
        ! -name "install.sh" ! -name "reapply-lan-patches.sh" ! -name "README.md" \
        -exec cp {} "$d/" \;
    done
    echo "  [已装] $DST_PLUGINS"
    echo "  [已装] $DST_PROFILE"
  fi
fi

# ── 3/4 组合接线（第 2 层后半：web profile 用户 patch）────────────────────
PATCH2="$DSH/profiles/web/cordis.patch.yml"
echo "== 3/4 组合接线 =="
if grep -q "dsh-lan-access" "$PATCH2" 2>/dev/null; then
  echo "  [已有] $PATCH2"
elif [ ! -d "$DSH/profiles/web" ]; then
  echo "  [跳过] web profile 尚未初始化（$DSH/profiles/web 不存在）"
  echo "         请先运行一次 dsh web 完成初始化，再重跑本脚本接线"
  FAIL=1
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $PATCH2 中的 lan-access 接线行"
else
  cat >> "$PATCH2" <<'EOF'
- insert:
    - id: lan-access
      name: 'dsh-lan-access'
EOF
  echo "  [已加] $PATCH2"
fi

# ── 4/4 特权围栏补丁（第 3 层，唯一留在 node_modules 的补丁）───────────────
echo "== 4/4 特权围栏补丁 =="
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
  pkill -TERM -f 'node_modules/.bin/dsh web' 2>/dev/null
  pkill -TERM -f 'npm exec @deepseek-ai/dsh web' 2>/dev/null
  pkill -TERM -f 'sh -c dsh web' 2>/dev/null
  sleep 3
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    cd "$ROOT" || exit 1
    setsid nohup ./node_modules/.bin/dsh web >> /tmp/dsh-web.log 2>&1 < /dev/null &
    echo "新进程 PID=$!"
    sleep 8
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    curl -s -o /dev/null -w '127.0.0.1:3080 页面 -> %{http_code}\n' http://127.0.0.1:3080/
    [ -n "$IP" ] && curl -s -o /dev/null -w "$IP:3080 页面 -> %{http_code}\n" "http://$IP:3080/"
    curl -s -o /dev/null -w 'LAN Host settings.describe（应非 403）-> %{http_code}\n' -H "Host: $IP:3080" -X POST http://127.0.0.1:3080/api/settings.describe
    curl -s -o /dev/null -w '插件 bundle（应 200）-> %{http_code}\n' http://127.0.0.1:3080/plugins/dsh-lan-access/client.js
    echo "== 完成 =="
  else
    echo "  无法定位 dsh 可执行文件，请手动重启 dsh web"
  fi
fi