#!/bin/bash
# audit-npm-drift.sh — 审计「仓库源码 vs npm 产物」是否同内容（不止同版本号）
#
# 为什么需要它（2026-09-15 定案）
# ------------------------------------------------------------------
# `docs/publishing.md` §0 的既有自检只比对**版本号**：
#
#     node -p "require('./packages/x/package.json').version"   vs   npm view <pkg> version
#
# 而真实故障几乎都是「**版本号一样、内容不一样**」：
#   - 有人改了 `install.sh` / `client.js` 却忘了升 version ⇒ 号一样，npm 上是旧代码；
#   - 升了 version 但忘了重跑 `bash scripts/package.sh` ⇒ tarball 里的 package.json 是旧值；
#   - 发了 npm 后又在仓库里追改同版本 ⇒ 号一样，两份内容分叉。
# 2026-09-15 实测抓到一例：`dsh-web-search-metaso` 仓库与 npm 都是 **0.1.3**，
# 但 `install.sh` 内容不同（仓库多了一段 apiKeyEnv 提示）—— 纯版本号自检**完全无感**。
#
# 判据（本脚本）：把 npm 上的 tarball 拉下来解包，**逐文件 md5 比对仓库**。
#   退出码 0 = 全部一致；1 = 有漂移（**先补发/修版本，再谈其它**）。
#
# 用法
#     bash scripts/audit-npm-drift.sh              # 全部包
#     bash scripts/audit-npm-drift.sh dsh-mobile-ui  # 只查一个包
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ONLY="${1:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

drift=0
checked=0
for d in "$REPO"/packages/*/; do
  name=$(basename "$d")
  [ -n "$ONLY" ] && [ "$name" != "$ONLY" ] && continue
  pkg=$(node -p "require('$d/package.json').name" 2>/dev/null) || continue
  rv=$(node -p "require('$d/package.json').version" 2>/dev/null)
  nv=$(npm view "$pkg" version 2>/dev/null || echo "")
  echo "═══ $name  仓库=$rv npm=${nv:-未发布} ═══"
  if [ -z "$nv" ]; then
    echo "  [跳过] npm 上没有这个包（尚未发布）"
    continue
  fi
  if [ "$rv" != "$nv" ]; then
    echo "  ✗ 版本号就不一致（仓库=$rv npm=$nv）⇒ 该发版或该回滚仓库版本"
    drift=1
  fi
  url="https://registry.npmjs.org/$pkg/-/$pkg-$nv.tgz"
  code=$(curl -sL -o "$WORK/$name.tgz" -w '%{http_code}' "$url")
  if [ "$code" != "200" ]; then
    echo "  ✗ 产物下载失败（HTTP $code）—— npm CDN 用 HEAD 会一直 404，必须 GET"
    drift=1; continue
  fi
  mkdir -p "$WORK/x_$name" && tar xzf "$WORK/$name.tgz" -C "$WORK/x_$name"
  same=0; diffn=0; onlyrepo=""
  ( cd "$WORK/x_$name/package" && find . -type f | sed 's|^\./||' | sort ) | while read -r f; do
    if [ -f "$d$f" ]; then
      a=$(md5sum "$d$f" | cut -d' ' -f1); b=$(md5sum "$WORK/x_$name/package/$f" | cut -d' ' -f1)
      [ "$a" = "$b" ] || echo "  ✗ 内容不同: $f"
    else
      echo "  ⚠ 产物独有（仓库里没有这个文件）: $f"
    fi
  done
  # 「仅仓库」= 未进包的文件（.npmignore、测试、脚本等），只提示不判错
  while read -r f; do
    [ -n "$f" ] || continue
    [ -f "$d$f" ] && [ ! -e "$WORK/x_$name/package/$f" ] && onlyrepo="$onlyrepo $f"
  done < <(cd "$d" && git ls-files | sed "s|^packages/$name/||")
  # 逐文件结论用 python 重算（上面 while 在子 shell 里，计数拿不到）
  res=$(python3 - "$d" "$WORK/x_$name/package" <<'PY'
import hashlib, os, sys
repo, pkg = sys.argv[1], sys.argv[2]
same = diff = 0; bad = []
for root, _, files in os.walk(pkg):
    for fn in files:
        p = os.path.join(root, fn); rel = os.path.relpath(p, pkg)
        rp = os.path.join(repo, rel)
        if not os.path.isfile(rp):
            bad.append(f"产物独有 {rel}"); continue
        h = lambda x: hashlib.md5(open(x, 'rb').read()).hexdigest()
        if h(p) == h(rp): same += 1
        else: diff += 1; bad.append(f"内容不同 {rel}")
print(f"{same} {diff} " + ("; ".join(bad) if bad else ""))
PY
)
  echo "  一致 $(echo "$res" | cut -d' ' -f1) 个 / 不同 $(echo "$res" | cut -d' ' -f2) 个；仅仓库:${onlyrepo}"
  [ "$(echo "$res" | cut -d' ' -f2)" != "0" ] && { echo "$res" | cut -d' ' -f3- | tr ';' '\n' | sed 's/^/    /'; drift=1; }
  checked=$((checked+1))
done

echo
if [ "$drift" != "0" ]; then
  echo "❌ 发现漂移：仓库与 npm **内容/版本不一致** —— 处置＝升 version + bash scripts/package.sh + npm publish + 重跑本脚本"
  exit 1
fi
echo "✅ 已核 $checked 个包：仓库与 npm 逐文件一致"
