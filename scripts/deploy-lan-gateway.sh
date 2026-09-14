#!/bin/bash
# deploy-lan-gateway.sh — 在目标机就地部署 dsh-lan-gateway 新版源码并重打令牌门卫补丁（幂等）。
#
# 为什么需要：升级 dsh / 换插件版本时，node_modules 里的门卫补丁会被覆盖，而
# patch-webserver.mjs 的就地升级（v2→v3）依赖 $DSH/plugins/dsh-lan-gateway 下的
# 新源码与 token-gate.v2.js 留档。本脚本把「同步源码 → 备份 → 升级补丁 → 语法校验」
# 串成一步，避免漏拷文件后补丁脚本启动即报错。
#
# 用法:
#   bash deploy-lan-gateway.sh --src <新源码目录> [--restart]
#
#   --src     含 token-gate.js / token-gate.v2.js / patch-webserver.mjs 的插件目录
#   --restart 补丁后重启 dsh web（默认只打补丁，不重启）
#
# 安全：改动前把 webserver lib 备份为 <file>.bak-<旧版本>-<时间戳>；任何一步失败即停。
set -u

SRC=""
RESTART=0
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="${2:-}"; shift 2 ;;
    --restart) RESTART=1; shift ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done
[ -n "$SRC" ] || { echo "用法: bash deploy-lan-gateway.sh --src <新源码目录> [--restart]"; exit 2; }
DSH="${DSH_HOME:-$HOME/.dsh}"
DST="$DSH/plugins/dsh-lan-gateway"

echo "== 1/5 校验新源码 =="
for f in token-gate.js token-gate.v2.js patch-webserver.mjs package.json; do
  if [ ! -f "$SRC/$f" ]; then echo "  [失败] 缺少 $SRC/$f"; exit 1; fi
done
echo "  [OK] $SRC 完整"

echo "== 2/5 定位 dsh 安装根与 webserver lib =="
PKG=""
# 1) 从监听 3080 的进程 cmdline 推导（最准；进程名形态各机不同：dsh web / bin.js web / ./lib/bin.js web）
PID=$(ss -ltnp 2>/dev/null | awk '/:3080 /{print $NF}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
[ -z "${PID:-}" ] && PID=$(pgrep -f 'bin\.js web|dsh web' 2>/dev/null | head -1)
if [ -n "${PID:-}" ]; then
  EXE=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null | awk '{print $2}')
  [ -n "${EXE:-}" ] && [ -e "$EXE" ] && PKG=$(dirname "$(dirname "$(readlink -f "$EXE")")")
fi
# 2) 已知安装位置兜底（office_64g 无 npm；devbox 走 nvm）
if [ -z "$PKG" ] || [ ! -d "$PKG/node_modules/@deepseek-ai" ]; then
  for g in "$(npm root -g 2>/dev/null)" "$HOME/.npm-global/lib/node_modules" \
           "$HOME/.local/node/lib/node_modules" /opt/node/lib/node_modules \
           "$HOME"/.nvm/versions/node/*/lib/node_modules; do
    if [ -n "$g" ] && [ -d "$g/@deepseek-ai/dsh" ]; then PKG="$g/@deepseek-ai/dsh"; break; fi
  done
fi
FW="$PKG/node_modules/@deepseek-ai/dsh-host-webserver/lib/index.js"
if [ ! -f "$FW" ]; then echo "  [失败] 未找到 webserver lib（PKG=${PKG:-空}）"; exit 1; fi
echo "  [OK] $FW"

echo "== 3/5 同步插件源码到 $DST =="
mkdir -p "$DST"
# 整目录拷（*.js/*.mjs/*.json/*.yml + README*）：写死文件清单会漏掉后加的补丁源
# （2026-09-14 踩到两次——先漏 install.sh/reapply 在包根，后差点漏 patch-ws-deflate.mjs）。
for f in "$SRC"/*.js "$SRC"/*.mjs "$SRC"/*.json "$SRC"/*.yml "$SRC"/README*.md; do
  [ -f "$f" ] && cp "$f" "$DST/"
done
# ⚠️ tarball 布局里 install.sh / reapply-lan-patches.sh 在**包根**（$SRC 的上一级），不在插件目录内。
# 只按 $SRC 找会把这两份运维脚本漏掉（2026-09-14 实际踩到：三台机器的 $DSH/reapply-lan-patches.sh
# 仍是旧版，自检文案还写着"回环豁免应 200"）。这里显式向上找一层。
PKGROOT="$(dirname "$SRC")"
if [ -f "$PKGROOT/reapply-lan-patches.sh" ]; then
  cp "$PKGROOT/reapply-lan-patches.sh" "$DSH/"
  cp "$PKGROOT/reapply-lan-patches.sh" "$DST/" 2>/dev/null || true
  echo "  [OK] 已更新 $DSH/reapply-lan-patches.sh（dsh 升级后的恢复入口）"
else
  echo "  [提示] $PKGROOT 无 reapply-lan-patches.sh（$DSH/reapply-lan-patches.sh 保持原样）"
fi
if [ -f "$PKGROOT/install.sh" ]; then
  # 只在目标机本来就有这份"随包安装器"时刷新（206 的约定；其他机器只有 reapply）
  if [ -f "$DSH/plugins/install.sh" ]; then
    cp "$PKGROOT/install.sh" "$DSH/plugins/install.sh"
    echo "  [OK] 已更新 $DSH/plugins/install.sh"
  else
    echo "  [提示] 该机无 $DSH/plugins/install.sh，跳过（需要时从 tarball 根手动放）"
  fi
fi
echo "  [OK] 已同步（$(ls "$DST" | wc -l) 个文件）"

echo "== 4/5 打补丁（含 v2 -> v3 就地升级）=="
VER=$(grep -o '（v[0-9]）' "$FW" | head -1 | tr -d '（）' || true)
[ -n "$VER" ] && cp "$FW" "$FW.bak-$VER-$(date +%Y%m%d-%H%M%S)" && echo "  [备份] $FW.bak-$VER-*"
node "$DST/patch-webserver.mjs" "$FW" || { echo "  [失败] 补丁脚本返回非 0"; exit 1; }
node --check "$FW" || { echo "  [失败] 打补丁后语法错误（备份在同目录 .bak-*）"; exit 1; }
echo "  [OK] 语法校验通过"

echo "== 5/5 结果 =="
node "$DST/patch-webserver.mjs" "$FW" --check
echo "  token 文件: $([ -f "$DSH/lan-access-token" ] && echo 存在 || echo 缺失)"

if [ "$RESTART" = "1" ]; then
  echo "== 重启 dsh web =="
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$HERE/_dsh-common/dsh-restart.sh" ]; then
    # shellcheck disable=SC1091
    . "$HERE/_dsh-common/dsh-restart.sh" && restart_dsh "$PKG"
  elif [ -f "$DSH/reapply-lan-patches.sh" ]; then
    echo "  [提示] 用 reapply 脚本的重启通道：bash $DSH/reapply-lan-patches.sh --restart"
  else
    echo "  [警告] 未找到重启通道，请手动重启 dsh web"
  fi
fi
echo "== 完成 =="
