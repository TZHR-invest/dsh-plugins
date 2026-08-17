#!/bin/bash
# package.sh — 为每个插件包生成一键安装 tarball 到 dist/
# 产物: dist/<name>-install.tar.gz（含 install.sh + reapply + README + <name>/ 插件源码）
# 目标机: tar xzf <name>-install.tar.gz && cd <name>-install && bash install.sh --restart
set -eu
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$REPO/dist/.staging"
rm -rf "$TMP"; mkdir -p "$TMP" "$REPO/dist"
MADE=0
for pkg in "$REPO"/packages/*/; do
  [ -d "$pkg" ] || continue
  NAME=$(basename "$pkg")
  PKGNAME=$(node -p "require('$pkg/package.json').name" 2>/dev/null || echo "$NAME")
  echo "== 打包 $NAME =="
  OUT="$TMP/$NAME-install"
  mkdir -p "$OUT/$NAME"
  cp "$pkg/package.json" "$pkg/index.js" "$OUT/$NAME/"
  [ -f "$pkg/client.js" ] && cp "$pkg/client.js" "$OUT/$NAME/"
  [ -f "$pkg/cordis.patch.yml" ] && cp "$pkg/cordis.patch.yml" "$OUT/$NAME/"
  [ -f "$pkg/token-gate.js" ] && cp "$pkg/token-gate.js" "$OUT/$NAME/"
  [ -f "$pkg/patch-webserver.mjs" ] && cp "$pkg/patch-webserver.mjs" "$OUT/$NAME/"
  [ -f "$pkg/install.sh" ] && cp "$pkg/install.sh" "$OUT/"
  [ -f "$pkg/reapply-lan-patches.sh" ] && cp "$pkg/reapply-lan-patches.sh" "$OUT/"
  [ -f "$pkg/README.md" ] && cp "$pkg/README.md" "$OUT/"
  # 共享重启脚本打进 tarball（install.sh 统一 source 它，避免内联逻辑漂移）
  if [ -f "$REPO/scripts/dsh-restart.sh" ]; then
    mkdir -p "$OUT/_dsh-common"
    cp "$REPO/scripts/dsh-restart.sh" "$OUT/_dsh-common/"
  fi
  if [ -f "$OUT/install.sh" ]; then
    tar czf "$REPO/dist/$PKGNAME-install.tar.gz" -C "$TMP" "$NAME-install"
    echo "  -> dist/$PKGNAME-install.tar.gz"
    MADE=1
  else
    echo "  [跳过] $NAME 无 install.sh（仅源码包，未生成 tarball）"
  fi
done
rm -rf "$TMP"
[ "$MADE" = "1" ] && echo "== 完成：dist/ 下即分发产物 =="