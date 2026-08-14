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

# ── 1/3 插件安装与接线（官方 bundle 流优先，复制流回退）──────────────────
SRC="$HOME/.dsh/plugins/dsh-lan-access"
DST="$HOME/.dsh/profiles/node_modules/dsh-lan-access"
PATCH="$HOME/.dsh/profiles/web/cordis.patch.yml"
echo "== 1/3 插件安装与接线 =="

bundle_wired() {
  [ -f "$HOME/.dsh/profiles/web/package.json" ] && grep -q '"dsh-lan-access"' "$HOME/.dsh/profiles/web/package.json"
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
  if grep -q "dsh-lan-access" "$PATCH" 2>/dev/null; then
    echo "  [已有] $PATCH"
  else
    sed -i '/^[[:space:]]*\[\][[:space:]]*$/d' "$PATCH"
    printf -- "- insert:\n    - id: lan-access\n      name: 'dsh-lan-access'\n" >> "$PATCH"
    echo "  [已加] $PATCH"
  fi
}

if bundle_wired; then
  echo "  [已有] 官方 bundle 流已接线（web profile bundles 含 dsh-lan-access）"
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
echo "== 2/3 特权围栏补丁 =="
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

# ── 4/4 设置持久化放行补丁（第 4 层：浏览器端 settingsScope 强制 host 模式）─
echo "== 4/4 设置持久化放行补丁 =="
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