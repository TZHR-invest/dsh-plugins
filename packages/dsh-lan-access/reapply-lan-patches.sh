#!/bin/bash
# reapply-lan-patches.sh — @deepseek-ai/dsh 升级/重装后，恢复局域网访问支持（幂等，可反复执行）。
#
# 用法:
#   bash ~/.dsh/reapply-lan-patches.sh            # 检查并补齐缺失的补丁
#   bash ~/.dsh/reapply-lan-patches.sh --check    # 只报告状态，不改文件
#   bash ~/.dsh/reapply-lan-patches.sh --restart  # 补齐后重启服务并验证
#
# 局域网访问支持由三层组成：
#   1. 绑定 0.0.0.0       -> ~/.dsh/cordis.patch.yml（用户配置层，升级不丢）
#   2. crypto.randomUUID  -> dsh-lan-access 客户端插件（用户插件层，升级不丢，
#                            本脚本负责从 ~/.dsh/plugins 重新安装 + 接线）
#   3. 特权围栏放行        -> node_modules 一行补丁（唯一会被升级覆盖的，本脚本重打）
set -u

MODE="${1:-apply}"

# ── 1/3 插件安装（源码 ~/.dsh/plugins -> profile 安装目录）──────────────────
SRC="$HOME/.dsh/plugins/dsh-lan-access"
DST="$HOME/.dsh/profiles/node_modules/dsh-lan-access"
echo "== 1/3 插件安装 =="
if [ -f "$DST/client.js" ] && grep -q "randomUUID" "$DST/client.js" 2>/dev/null; then
  echo "  [已有] $DST"
elif [ -d "$SRC" ]; then
  if [ "$MODE" = "--check" ]; then
    echo "  [缺失] $DST（可安装）"
  else
    mkdir -p "$DST" && cp "$SRC"/* "$DST/" && echo "  [已装] $DST"
  fi
else
  echo "  [缺失] 插件源码 $SRC 不存在，请人工恢复"
fi

# ── 2/3 组合接线（web profile 用户 patch 层）────────────────────────────────
PATCH="$HOME/.dsh/profiles/web/cordis.patch.yml"
echo "== 2/3 组合接线 =="
if grep -q "dsh-lan-access" "$PATCH" 2>/dev/null; then
  echo "  [已有] $PATCH"
elif [ "$MODE" = "--check" ]; then
  echo "  [缺失] $PATCH 中的 lan-access 行"
else
  printf -- "- insert:\n    - id: lan-access\n      name: 'dsh-lan-access'\n" >> "$PATCH"
  echo "  [已加] $PATCH"
fi

# ── 3/3 特权围栏补丁（唯一留在 node_modules 的补丁）────────────────────────
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
echo "== 3/3 特权围栏补丁 =="
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
    sed -i 's/PRIVILEGED_METHODS.has(method) && !isTrustedApiRequest(request, \[\])/PRIVILEGED_METHODS.has(method) \&\& !isTrustedApiRequest(request, trustedHosts)/' "$F"
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

if [ "$MODE" = "--check" ]; then
  echo "== 检查完成（未改动任何文件）=="
  exit 0
fi

# ── 可选重启 ───────────────────────────────────────────────────────────────
if [ "$MODE" = "--restart" ]; then
  echo "== 重启服务 =="
  pkill -TERM -f 'node_modules/.bin/dsh web' 2>/dev/null
  pkill -TERM -f 'npm exec @deepseek-ai/dsh web' 2>/dev/null
  pkill -TERM -f 'sh -c dsh web' 2>/dev/null
  sleep 3
  cd "$ROOT" || exit 1
  setsid nohup ./node_modules/.bin/dsh web >> /tmp/dsh-web.log 2>&1 < /dev/null &
  echo "新进程 PID=$!"
  sleep 8
  curl -s -o /dev/null -w '127.0.0.1:3080 页面 -> %{http_code}\n' http://127.0.0.1:3080/
  curl -s -o /dev/null -w '192.168.0.206:3080 页面 -> %{http_code}\n' http://192.168.0.206:3080/
  curl -s -o /dev/null -w 'LAN Host settings.describe（应非 403）-> %{http_code}\n' -H "Host: 192.168.0.206:3080" -X POST http://127.0.0.1:3080/api/settings.describe
  curl -s -o /dev/null -w '插件 bundle（应 200）-> %{http_code}\n' http://127.0.0.1:3080/plugins/dsh-lan-access/client.js
  echo "== 完成 =="
fi
