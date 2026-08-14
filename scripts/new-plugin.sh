#!/bin/bash
# new-plugin.sh <name> [description] — 从模板创建新 dsh 插件包
# 用法:
#   bash scripts/new-plugin.sh my-cool-plugin "我的第一个 dsh 插件"
# 生成 packages/<name>/，含 package.json / index.js / client.js / README.md
set -eu
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${1:-}"
DESC="${2:-${NAME:-} dsh 插件}"
if [ -z "$NAME" ]; then
  echo "用法: bash scripts/new-plugin.sh <name> [description]"; exit 1
fi
case "$NAME" in
  *[!a-z0-9-]*|''|-*) echo "错误：名字只允许小写字母/数字/连字符（^[a-z0-9-]+$）"; exit 1 ;;
esac
DEST="$REPO/packages/$NAME"
if [ -e "$DEST" ]; then echo "错误：$DEST 已存在"; exit 1; fi
cp -r "$REPO/templates/plugin" "$DEST"
# 占位符替换
for f in "$DEST"/*; do
  sed -i "s/__PACKAGE_NAME__/$NAME/g; s/__PLUGIN_ID__/$NAME/g; s|__DESCRIPTION__|$DESC|g" "$f"
done
# 基本校验
node --check "$DEST/index.js" && node --check "$DEST/client.js"
node -e "JSON.parse(require('fs').readFileSync('$DEST/package.json','utf8'))" \
  && echo "package.json 合法"
echo "== 已创建 $DEST =="
echo "下一步:"
echo "  1) 编辑 packages/$NAME/index.js 与 client.js 实现功能"
echo "  2) 本地验证: bash scripts/build.sh"
echo "  3) 分发: bash scripts/package.sh"
