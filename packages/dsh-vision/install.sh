#!/bin/bash
# install.sh.template — 通用 dsh 插件安装器模板（dsh-plugins）
# 新插件由 scripts/new-plugin.sh 从本模板生成 packages/<name>/install.sh；
# 也可手动复制并替换 dsh-vision。memory-recall-dsh/install.sh 即为本模板的
# 早期实例化产物（含插件特有逻辑）。
#
# 用法（在插件源码目录执行，或 --src 指定）:
#   bash install.sh --plugin <插件名> [--src <源码目录>] [--profile web|headless]
#                 [--api-key <key>] [--check | --smoke | --restart | --uninstall]
#
# 内置防崩（MR-022/023 教训，勿删）：
#   1. 契约预检：node _dsh-common/preflight.mjs（dsh.client.platform /
#      exports["./client"] / classic-script bundle），未通过拒绝安装；
#   2. headless 试启动冒烟：--restart 前先在隔离 profile 真实 boot，
#      命中插件加载错误关键字即中止，正式服务不受影响。
set -u

PLUGIN="dsh-vision-tool"
SRC=""
PROFILE="web"
API_KEY=""
VISION_BASE_URL=""
VISION_API_KEY=""
VISION_API_KEY_ENV=""
VISION_MODEL=""
VISION_MODELS=""
VISION_MAX_TOKENS=""
MODE="apply"

i=0
ARGS=("$@")
while [ $i -lt ${#ARGS[@]} ]; do
  arg="${ARGS[$i]}"
  case "$arg" in
    --check) MODE="check" ;;
    --restart) MODE="restart" ;;
    --smoke) MODE="smoke" ;;
    --uninstall) MODE="uninstall" ;;
    --plugin=*) PLUGIN="${arg#--plugin=}" ;;
    --src=*) SRC="${arg#--src=}" ;;
    --profile=*) PROFILE="${arg#--profile=}" ;;
    --api-key=*) API_KEY="${arg#--api-key=}" ;;
    --plugin) i=$((i + 1)); PLUGIN="${ARGS[$i]:-}"; [ -n "$PLUGIN" ] || { echo "用法: --plugin <name>"; exit 1; } ;;
    --src) i=$((i + 1)); SRC="${ARGS[$i]:-}" ;;
    --profile) i=$((i + 1)); PROFILE="${ARGS[$i]:-web}" ;;
    --api-key) i=$((i + 1)); API_KEY="${ARGS[$i]:-}" ;;
    --vision-base-url) i=$((i + 1)); VISION_BASE_URL="${ARGS[$i]:-}" ;;
    --vision-base-url=*) VISION_BASE_URL="${arg#--vision-base-url=}" ;;
    --vision-api-key) i=$((i + 1)); VISION_API_KEY="${ARGS[$i]:-}" ;;
    --vision-api-key=*) VISION_API_KEY="${arg#--vision-api-key=}" ;;
    --vision-api-key-env) i=$((i + 1)); VISION_API_KEY_ENV="${ARGS[$i]:-}" ;;
    --vision-api-key-env=*) VISION_API_KEY_ENV="${arg#--vision-api-key-env=}" ;;
    --vision-model) i=$((i + 1)); VISION_MODEL="${ARGS[$i]:-}" ;;
    --vision-model=*) VISION_MODEL="${arg#--vision-model=}" ;;
    --vision-models) i=$((i + 1)); VISION_MODELS="${ARGS[$i]:-}" ;;
    --vision-models=*) VISION_MODELS="${arg#--vision-models=}" ;;
    --vision-max-tokens) i=$((i + 1)); VISION_MAX_TOKENS="${ARGS[$i]:-}" ;;
    --vision-max-tokens=*) VISION_MAX_TOKENS="${arg#--vision-max-tokens=}" ;;
    --*) echo "未知参数: $arg"; exit 1 ;;
  esac
  i=$((i + 1))
done

[ -n "$PLUGIN" ] || { echo "错误: 缺少 --plugin <name>"; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -n "$SRC" ] || SRC="$HERE"
# tarball 分发布局：install.sh 在根、插件源码在同名子目录（如 <name>-install/<name>/）
if [ ! -f "$SRC/package.json" ] && [ -f "$SRC/$PLUGIN/package.json" ]; then
  SRC="$SRC/$PLUGIN"
fi
# 契约预检脚本位置：优先所在仓库（packages/<name>/install.sh → ../../scripts），
# 其次环境变量 DSH_PLUGINS_REPO，最后 $HOME/dsh-plugins
for CAND in "$HERE/../../scripts" "${DSH_PLUGINS_REPO:-$HOME/dsh-plugins}/scripts"; do
  if [ -n "$CAND" ] && [ -f "$CAND/preflight.mjs" ]; then
    COMMON="$CAND"
    break
  fi
done
[ -n "${COMMON:-}" ] || COMMON=""
DSH="${DSH_HOME:-$HOME/.dsh}"
DST_PLUGINS="$DSH/plugins/$PLUGIN"
DST_PROFILE="$DSH/profiles/node_modules/$PLUGIN"
PATCH="$DSH/profiles/$PROFILE/cordis.patch.yml"
FAIL=0

# 全部关键文件一致（package.json + 所有 .js；.mjs 类构建/预检工具属开发期，不部署）
FILES_IDENTICAL() {
  local src="$1" dst="$2"
  for f in "$src"/*.js; do
    [ -f "$f" ] || continue
    local base
    base="$(basename "$f")"
    [ -f "$dst/$base" ] || return 1
    diff -q "$f" "$dst/$base" >/dev/null 2>&1 || return 1
  done
  diff -q "$src/package.json" "$dst/package.json" >/dev/null 2>&1 || return 1
  return 0
}

echo "== $PLUGIN 安装（mode: $MODE, profile: $PROFILE）=="
echo "  DSH 目录: $DSH"
echo "  源码目录: $SRC"

# ── 0/4 前置检查 + 契约预检 ─────────────────────────────────────────────
echo "== 0/4 前置检查 =="
[ -f "$SRC/package.json" ] || { echo "  错误: 缺少 $SRC/package.json"; exit 1; }
for f in "$SRC"/*.js; do
  node --check "$f" >/dev/null 2>&1 || { echo "  错误: 语法检查失败 $f"; FAIL=1; }
done
[ "$FAIL" = "1" ] && exit 1
echo "  [OK] 源码完整，语法检查通过"

echo "== 0.5/4 契约预检（$COMMON/preflight.mjs）=="
if [ -f "$COMMON/preflight.mjs" ]; then
  if node "$COMMON/preflight.mjs" "$SRC"; then
    echo "  [OK] 加载器契约检查通过"
  else
    if [ "$MODE" = "check" ]; then
      FAIL=1
    else
      echo "  [错误] 契约预检未通过——安装会破坏 dsh 启动，已中止。请修复后重试。"
      exit 1
    fi
  fi
else
  echo "  [跳过] 无共享 preflight.mjs"
fi

# ── 1/4 源码留档 ─────────────────────────────────────────────────────────
echo "== 1/4 源码留档 =="
if [ -f "$DST_PLUGINS/index.js" ] && FILES_IDENTICAL "$SRC" "$DST_PLUGINS"; then
  echo "  [已有] $DST_PLUGINS（内容一致）"
else
  if [ "$MODE" = "check" ]; then
    echo "  [缺失/不同] $DST_PLUGINS"; FAIL=1
  else
    mkdir -p "$DST_PLUGINS"
    cp "$SRC"/package.json "$SRC"/*.js "$DST_PLUGINS/"
    echo "  [已装] $DST_PLUGINS"
  fi
fi

# ── 2/4 运行副本 ─────────────────────────────────────────────────────────
echo "== 2/4 运行副本 =="
if [ -f "$DST_PROFILE/index.js" ] && FILES_IDENTICAL "$SRC" "$DST_PROFILE"; then
  echo "  [已有] $DST_PROFILE（内容一致）"
else
  if [ "$MODE" = "check" ]; then
    echo "  [缺失/不同] $DST_PROFILE"; FAIL=1
  else
    mkdir -p "$DST_PROFILE"
    cp "$SRC"/package.json "$SRC"/*.js "$DST_PROFILE/"
    echo "  [已装] $DST_PROFILE"
  fi
fi

# ── 2.5/4 视觉配置收集（用户提供 provider + model，无内置默认值）──────────
VISION_YAML=""
collect_vision_config() {
  if [ -z "$VISION_BASE_URL$VISION_API_KEY$VISION_API_KEY_ENV$VISION_MODEL$VISION_MODELS$VISION_MAX_TOKENS" ] && [ -t 0 ]; then
    echo "== 视觉配置（dsh-vision 无内置默认值，请提供 provider 与模型）=="
    read -r -p "  OpenAI 兼容端点 baseURL（如 https://opencode.ai/zen/go/v1）: " VISION_BASE_URL
    read -r -p "  默认视觉模型 defaultModel（如 mimo-v2.5）: " VISION_MODEL
    echo "  凭据二选一："
    read -r -p "    apiKey（直接填密钥，回车跳过）: " VISION_API_KEY
    if [ -z "$VISION_API_KEY" ]; then
      read -r -p "    apiKeyEnv（环境变量名，如 OPENCODE_GO_API_KEY）: " VISION_API_KEY_ENV
    fi
    read -r -p "  cross_check 模型列表（逗号分隔，可回车跳过）: " VISION_MODELS
  elif [ -n "$VISION_BASE_URL$VISION_API_KEY$VISION_API_KEY_ENV$VISION_MODEL$VISION_MODELS$VISION_MAX_TOKENS" ]; then
    if [ -t 0 ]; then
      [ -n "$VISION_BASE_URL" ] || read -r -p "  补充 baseURL: " VISION_BASE_URL
      [ -n "$VISION_MODEL" ] || read -r -p "  补充 defaultModel: " VISION_MODEL
      if [ -z "$VISION_API_KEY" ] && [ -z "$VISION_API_KEY_ENV" ]; then
        read -r -p "  补充 apiKey（或回车后用 apiKeyEnv）: " VISION_API_KEY
        [ -n "$VISION_API_KEY" ] || read -r -p "  补充 apiKeyEnv: " VISION_API_KEY_ENV
      fi
    fi
  fi
  local missing=""
  # --check 只读：patch 已含本插件接线且带 baseURL 时视为已有配置（不误报，2026-08-15 回归测试发现）
  if [ "$MODE" = "check" ] && [ -f "$PATCH" ] && grep -q -- "- id: $PLUGIN" "$PATCH" 2>/dev/null && grep -q "baseURL" "$PATCH" 2>/dev/null; then
    echo "  [OK] 视觉配置已在 $PATCH 中（--check 只读，不重复收集）"
    return
  fi
  [ -n "$VISION_BASE_URL" ] || missing="$missing baseURL"
  [ -n "$VISION_MODEL" ] || missing="$missing defaultModel"
  if [ -z "$VISION_API_KEY" ] && [ -z "$VISION_API_KEY_ENV" ]; then missing="$missing apiKey/apiKeyEnv"; fi
  if [ -n "$missing" ]; then
    echo "  [警告] 缺少:$missing——将写入空配置，vision 工具不会注册。"
    echo "         可重跑 install.sh 传 --vision-* 参数，或编辑 $PATCH 后重启。"
    return
  fi
  local y=""
  y="$y        baseURL: '$VISION_BASE_URL'\n"
  if [ -n "$VISION_API_KEY" ]; then
    y="$y        apiKey: '$VISION_API_KEY'\n"
  else
    y="$y        apiKeyEnv: '$VISION_API_KEY_ENV'\n"
  fi
  y="$y        defaultModel: '$VISION_MODEL'\n"
  if [ -n "$VISION_MODELS" ]; then
    local list="["
    local IFS_OLD="$IFS"; IFS=","
    for m in $VISION_MODELS; do
      list="$list'$(echo "$m" | tr -d ' ')',"
    done
    IFS="$IFS_OLD"
    list="${list%,}]"
    y="$y        visionModels: $list\n"
  fi
  if [ -n "$VISION_MAX_TOKENS" ]; then
    y="$y        maxTokens: $VISION_MAX_TOKENS\n"
  fi
  VISION_YAML="$y"
  echo "  [OK] 视觉配置已收集（endpoint=$VISION_BASE_URL, model=$VISION_MODEL）"
}
[ "$MODE" = "uninstall" ] || collect_vision_config

# ── 3/4 profile patch 接线 ───────────────────────────────────────────────
echo "== 3/4 组合接线（$PATCH）=="
if [ -f "$PATCH" ] && grep -qE -- "- id: $PLUGIN" "$PATCH" 2>/dev/null; then
  echo "  [已有] $PATCH 中的 $PLUGIN 接线"
elif [ "$MODE" = "check" ]; then
  echo "  [缺失] $PATCH 中的 $PLUGIN 接线"; FAIL=1
else
  mkdir -p "$(dirname "$PATCH")"
  if [ -f "$PATCH" ] && grep -q '^\[\]$' "$PATCH" 2>/dev/null; then
    sed -i '/^\[\]$/d' "$PATCH"
  fi
  if [ -n "$VISION_YAML" ]; then
    cat >> "$PATCH" <<PATCHEOF

# $PLUGIN：dsh 插件（视觉读图，provider/model 由安装时用户提供）
- insert:
    - id: $PLUGIN
      name: '$PLUGIN'
      config:
$(printf '%b' "$VISION_YAML")
PATCHEOF
  else
    cat >> "$PATCH" <<PATCHEOF

# $PLUGIN：dsh 插件（视觉读图，尚未配置——重跑 install.sh 传 --vision-* 参数或编辑本文件）
- insert:
    - id: $PLUGIN
      name: '$PLUGIN'
      config: {}
PATCHEOF
  fi
  echo "  [已加] $PATCH"
fi

# ── headless 试启动冒烟（防"启动即崩"）──────────────────────────────────
ROOT=""
for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
  d=${d%/}
  [ -d "$d/node_modules/@deepseek-ai" ] || continue
  ROOT="$d"
  break
done
SMOKE_LOG=/tmp/dsh-plugin-smoke.log
SMOKE_TEST() {
  local dsh_bin="$1"
  echo "== 冒烟：headless 试启动（隔离环境，不影响正式服务）=="
  if [ ! -d "$DSH/profiles/headless" ]; then
    echo "  [跳过] headless profile 未初始化（首次运行 dsh --profile headless 可初始化）"
    return 0
  fi
  if [ -f "$DSH/profiles/headless/cordis.patch.yml" ] && grep -qE -- "- id: $PLUGIN" "$DSH/profiles/headless/cordis.patch.yml" 2>/dev/null; then
    echo "  [已有] headless 插件接线"
  else
    mkdir -p "$DSH/profiles/headless"
    [ -f "$DSH/profiles/headless/cordis.patch.yml" ] || printf '[]\n' > "$DSH/profiles/headless/cordis.patch.yml"
    sed -i '/^\[\]$/d' "$DSH/profiles/headless/cordis.patch.yml"
    if [ -n "$VISION_YAML" ]; then
      cat >> "$DSH/profiles/headless/cordis.patch.yml" <<PATCHEOF

# $PLUGIN：dsh 插件（自动接入，供 headless 冒烟试启动）
- insert:
    - id: $PLUGIN
      name: '$PLUGIN'
      config:
$(printf '%b' "$VISION_YAML")
PATCHEOF
    else
      cat >> "$DSH/profiles/headless/cordis.patch.yml" <<PATCHEOF

# $PLUGIN：dsh 插件（自动接入，供 headless 冒烟试启动）
- insert:
    - id: $PLUGIN
      name: '$PLUGIN'
      config: {}
PATCHEOF
    fi
    echo "  [已接线] headless profile（自动接入，仅用于冒烟）"
  fi
  local start_ts end_ts
  start_ts=$(date +%s)
  if timeout 120 env MEMORY_RECALL_API_KEY="${MEMORY_RECALL_API_KEY:-}" "$dsh_bin" --profile headless "1" > "$SMOKE_LOG" 2>&1; then
    end_ts=$(date +%s)
    echo "  [PASS] headless 试启动成功（$((end_ts - start_ts))s），插件组合无问题"
    return 0
  fi
  end_ts=$(date +%s)
  echo "  [FAIL] headless 试启动失败（$((end_ts - start_ts))s）"
  if grep -qiE "client-modules|plugin tree failed|cannot resolve entry|$PLUGIN" "$SMOKE_LOG"; then
    echo "  命中插件组合/加载错误关键字，判定为插件问题："
    grep -iE "client-modules|plugin tree failed|cannot resolve entry|$PLUGIN" "$SMOKE_LOG" | head -5
    echo "  完整日志: $SMOKE_LOG"
    echo "  回滚：bash install.sh --uninstall 后重启 dsh 即可恢复"
    return 1
  fi
  echo "  未命中插件关键字（疑似 LLM/网络类问题），完整日志: $SMOKE_LOG"
  return 2
}

# ── 4/4 冒烟 + 重启（可选）──────────────────────────────────────────────
if [ "$MODE" = "smoke" ] || [ "$MODE" = "restart" ]; then
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    SMOKE_TEST "$ROOT/node_modules/.bin/dsh"
    SMOKE_RC=$?
    [ "$MODE" = "smoke" ] && exit "$SMOKE_RC"
    if [ "$SMOKE_RC" = "1" ]; then
      echo "  [中止] 冒烟判定插件有问题，不重启 dsh（正式服务保持当前状态）"
      exit 1
    fi
  else
    echo "  [警告] 无法定位 dsh 可执行文件，冒烟跳过"
  fi
fi

if [ "$MODE" = "restart" ]; then
  echo "== 4/4 重启 dsh =="
  # 统一重启逻辑：systemd 托管优先，回退 pkill（MR-026）
  if [ -n "$COMMON" ] && [ -f "$COMMON/dsh-restart.sh" ]; then
    . "$COMMON/dsh-restart.sh"
    restart_dsh "$ROOT"
  else
    # tarball 分发场景无 scripts/dsh-restart.sh：内联 systemd 兜底
    if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet dsh.service 2>/dev/null; then
      echo "  [systemd] dsh.service 托管中 → systemctl --user restart dsh"
      systemctl --user restart dsh.service
      sleep 6
      curl -s --noproxy '*' -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪"
    else
      echo "  [警告] 未找到共享 dsh-restart.sh 且无 systemd 托管，请手动重启 dsh web"
    fi
  fi
  if [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    curl -s -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪，请稍后手动刷新"
    curl -s -o /dev/null -w "  $PLUGIN bundle -> %{http_code}\n" "http://127.0.0.1:3080/plugins/$PLUGIN/client.js"
  else
    echo "  [警告] 无法定位 dsh 可执行文件，请手动重启 dsh web"
  fi
fi

# ── 卸载 ─────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
  echo "== 卸载 =="
  if [ -f "$PATCH" ]; then
    python3 - "$PATCH" "$PLUGIN" <<'PYEOF'
import sys, re
path, plugin = sys.argv[1], sys.argv[2]
lines = open(path).read().split("\n")
removed = 0
i = 0
while i < len(lines):
    if lines[i].startswith("- insert:"):
        j = i + 1
        while j < len(lines) and not lines[j].startswith("- "):
            j += 1
        block = lines[i:j]
        if re.search(r"id:\s*'?" + re.escape(plugin) + r"'?", "\n".join(block)):
            removed += 1
            # 吞掉块前紧邻的注释行与空行
            k = i - 1
            while k >= 0 and (lines[k].strip() == "" or lines[k].lstrip().startswith("#")):
                k -= 1
            del lines[k + 1:j]
            i = k + 1
            continue
    i += 1
open(path, "w").write("\n".join(lines))
print("  [已清] 移除 %d 个 %s insert 块（含注释与 config）" % (removed, plugin))
PYEOF
    rm -rf "$DST_PROFILE" "$DST_PLUGINS"
  fi
  echo "  完成。重启 dsh 后插件移除生效。"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  echo "== 检查完成（未改动任何文件）=="
  [ "$FAIL" = "1" ] && echo "（存在缺失项，直接运行 bash install.sh 即可补齐）"
  exit 0
fi

echo "== 完成 =="
echo "  重启 dsh 后插件生效（bash install.sh --restart 可一键重启验证）。"
