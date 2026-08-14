#!/bin/bash
# build.sh — 校验仓库内所有插件包（语法 / JSON / 包结构），无副作用
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
for pkg in "$REPO"/packages/*/; do
  [ -d "$pkg" ] || continue
  NAME=$(basename "$pkg")
  echo "== $NAME =="
  [ -f "$pkg/package.json" ] || { echo "  [缺失] package.json"; FAIL=1; continue; }
  node -e "JSON.parse(require('fs').readFileSync('$pkg/package.json','utf8'))" \
    && echo "  [OK] package.json 合法" || FAIL=1
  if [ -f "$pkg/index.js" ]; then
    node --check "$pkg/index.js" && echo "  [OK] index.js 语法" || FAIL=1
  fi
  if [ -f "$pkg/client.js" ]; then
    node --check "$pkg/client.js" && echo "  [OK] client.js 语法" || FAIL=1
    grep -q '__ModuleLoader__.load' "$pkg/client.js" \
      && echo "  [OK] client.js 含 __ModuleLoader__.load 注册" || { echo "  [警告] client.js 未发现 __ModuleLoader__.load"; FAIL=1; }
    grep -q 'exports.apply' "$pkg/client.js" \
      && echo "  [OK] client.js 导出 apply（dsh >= 0.1.0-rc.6 要求）" || { echo "  [警告] client.js 未导出 apply"; FAIL=1; }
  fi
  for s in install.sh reapply-lan-patches.sh; do
    [ -f "$pkg/$s" ] && { bash -n "$pkg/$s" && echo "  [OK] $s 语法" || FAIL=1; }
  done
done
echo ""
if [ "$FAIL" = "1" ]; then echo "存在失败项"; exit 1; else echo "全部通过"; fi
