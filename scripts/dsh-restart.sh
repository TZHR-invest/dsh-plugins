#!/bin/bash
# dsh-restart.sh — 统一的 dsh web 重启逻辑（systemd 优先，回退 pkill+nohup）
#
# 用法（二选一）：
#   1) source 后调用函数：  . scripts/dsh-restart.sh; restart_dsh [ROOT]
#   2) 独立运行：           bash scripts/dsh-restart.sh [ROOT]
#
# 背景（MR-026）：dsh web 已由 systemd --user 托管（dsh.service, Restart=always）。
# 旧脚本用 pkill + setsid nohup 手动拉起，与 systemd 的 Restart=always 冲突：
# pkill 杀掉进程后 systemd 3 秒内自动拉起新实例，脚本又手动拉起一个，
# 可能造成双实例抢 3080 端口。systemd 托管时应统一走 systemctl --user restart。
set -u

# 定位 dsh 安装根（与 install.sh 的 ROOT 定位一致，含 MR-025 增强）
dsh_find_root() {
  local ROOT="" CWD="" PID="" G="" d=""
  # 1) 从运行中的 dsh web 进程推导（覆盖 npm 全局安装 / npx 缓存两种形态）
  for PID in $(pgrep -f "dsh web" 2>/dev/null); do
    [ "$PID" = "$$" ] && continue
    CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
    [ -n "$CWD" ] && [ -d "$CWD/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$CWD" && break
  done
  # 2) npm root -g（npm 全局安装形态）
  if [ -z "$ROOT" ]; then
    G=$(npm root -g 2>/dev/null || true)
    [ -n "$G" ] && [ -d "$G/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-client-connection" ] && ROOT="$G/@deepseek-ai/dsh"
  fi
  # 3) npx 缓存回退
  if [ -z "$ROOT" ]; then
    for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
      d=${d%/}
      [ -d "$d/node_modules/@deepseek-ai/dsh-client-connection" ] || continue
      ROOT="$d"
      break
    done
  fi
  echo "$ROOT"
}

# 重启 dsh web。参数 $1 可选：dsh 安装根（缺省自动定位）。
restart_dsh() {
  local ROOT="${1:-}"
  [ -z "$ROOT" ] && ROOT="$(dsh_find_root)"
  echo "== 重启 dsh web =="
  # 1) systemd 托管优先
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet dsh.service 2>/dev/null; then
    echo "  [systemd] dsh.service 托管中 → systemctl --user restart dsh"
    systemctl --user restart dsh.service
    local rc=$?
    sleep 6
    if [ "$rc" = "0" ]; then
      curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪，请稍后手动刷新"
    fi
    return "$rc"
  fi
  # 2) 回退：pkill + setsid nohup（无 systemd 环境）
  echo "  [回退] 无 systemd 托管，pkill + 手动拉起"
  pkill -TERM -f "dsh web" 2>/dev/null
  pkill -TERM -f 'node_modules/.bin/dsh web' 2>/dev/null
  pkill -TERM -f 'npm exec @deepseek-ai/dsh web' 2>/dev/null
  pkill -TERM -f 'sh -c dsh web' 2>/dev/null
  pkill -TERM -f 'dsh/lib/bin.js web' 2>/dev/null
  sleep 3
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    local DSH_RUN="$ROOT/node_modules/.bin/dsh"
    if command -v dsh >/dev/null 2>&1; then DSH_RUN="$(command -v dsh)"; fi
    cd "$(dirname "$DSH_RUN")" || return 1
    setsid nohup "$DSH_RUN" web >> /tmp/dsh-web.log 2>&1 < /dev/null &
    echo "  新进程 PID=$!"
    sleep 8
    curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪，请稍后手动刷新"
    return 0
  else
    echo "  [警告] 无法定位 dsh 可执行文件，请手动重启 dsh web"
    return 1
  fi
}

# 独立执行模式
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  restart_dsh "$@"
fi
