#!/usr/bin/env python3
"""凭据扫描（CI + pre-commit 双用，零依赖）。

## 为什么本仓库需要它

`TZHR-invest/dsh-plugins` 是 **public** 仓库，而它管理的恰恰是最容易夹带凭据的文件：
各插件的 `install.sh` 会往 `~/.dsh/profiles/<profile>/cordis.patch.yml` 里写
`apiKey: 'mk-…'`（metaso）、`rk_live_…`（memory-recall）、`ocx_data_…`（opencodex）
—— **三把 key 曾长期以明文躺在 5 台机器的同一个 patch 文件里**
（2026-09-15 排查；同日均已 chmod 600）。

历史是干净的（逐值 `git log -S` 验过 0 命中），但**一次「把本机 patch 拷进仓库当模板」
就会把三把 key 一起公开**。所以：CI 每次 push/PR 扫一遍，本地可用 `--staged` 挂 pre-commit。

## 用法

    python3 scripts/secret-scan.py                 # 扫全部跟踪文件（CI 用）
    python3 scripts/secret-scan.py --staged        # 只扫暂存区新增行（pre-commit 用）
    python3 scripts/secret-scan.py --history 200   # 额外扫最近 200 个提交的新增行
    python3 scripts/secret-scan.py --secrets-file ~/.meshdeck-secrets.md   # 值级反查

退出码：0 = 干净；1 = 命中；2 = 用法错误。

## 允许误报

行内写 `secret-scan: allow` 即跳过该行；已知的假值（全同字符、`0123456789abcdef`
顺序串、`${VAR}`/`<your-key>`/`changeme` 等占位符）内置放行。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# ── 规则 A：有固定前缀的真实凭据厂商（命中即失败）────────────────────────────
PREFIX_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("metaso api key", re.compile(r"\bmk-[0-9A-Fa-f]{24,}\b")),
    ("memory-recall key", re.compile(r"\brk_live_[0-9A-Za-z]{32,}\b")),
    ("opencodex key", re.compile(r"\bocx_data_[0-9a-f]{32,}\b")),
    ("openai/deepseek key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github pat", re.compile(r"\bghp_[A-Za-z0-9]{30,}\b")),
    ("github fine-grained pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("tailscale auth key", re.compile(r"\btskey-[a-z]+-[A-Za-z0-9]{16,}\b")),
]

# ── 规则 B：赋值语境里的字面量（"token: 'abc…'"）────────────────────────────
CONTEXT_RULE = re.compile(
    r"""(?ix)
    \b( api[_-]?key | apikey | access[_-]?token | auth[_-]?token | token
      | secret | passwd | password | requirepass | credential )
    \b \s* [:=] \s*
    (?: ["']([^"'\n]{12,})["'] | ([A-Za-z0-9_\-./+=]{16,}) )
    """
)

# ── 规则 C：无前缀的高熵串（仅在同行有 secret 语境时才算命中）──────────────
CONTEXT_WORDS = re.compile(
    r"(?i)\b(key|token|secret|passwd|password|requirepass|credential|bearer|授权|凭据|密钥)\b"
)
HIGH_ENTROPY = re.compile(r"\b(?:[0-9a-fA-F]{40,}|[A-Za-z0-9+/]{48,}={0,2})\b")

PLACEHOLDER = re.compile(
    r"""(?ix)
    ^( \$\{?[A-Za-z_][A-Za-z0-9_]*\}?      # ${VAR} / $VAR
     | <[^>]*>                             # <your-key>
     | \{\{[^}]*\}\}                       # {{ ... }}
     | (x{4,}|\*{3,}|\.{3,}|-{3,})         # xxxx / *** / ...
     | (your|my|the|example|sample|dummy|fake|test|placeholder|changeme|redacted
        | none|null|nil|true|false|todo|xxx+)
     | (bearer|basic|token|secret|api[_-]?key)   # 文档里的裸词
    )
    """
)

SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "vendor"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
               ".gz", ".tgz", ".whl", ".woff", ".woff2", ".ttf", ".so", ".node"}
MAX_BYTES = 2 * 1024 * 1024
ALLOW_PRAGMA = "secret-scan: allow"


def is_fake(value: str) -> bool:
    """明显的测试/占位值：全同字符、顺序串、纯重复子串。"""
    v = value.strip().strip("'\"")
    if len(v) < 12:
        return True
    if len(set(v)) <= 4:
        return True
    lowered = v.lower()
    for seq in ("0123456789abcdef", "abcdef0123456789", "0123456789abcde",
                "1234567890", "abcdefghij", "deadbeef"):
        if seq in lowered:
            return True
    # 形如 abababab…（周期 ≤ 4 的重复）
    for period in range(1, 5):
        if len(v) % period == 0 and len(set(v[i::period] for i in range(period))) == 1:
            return True
    return PLACEHOLDER.match(v) is not None


def mask(value: str) -> str:
    v = value.strip().strip("'\"")
    return f"{v[:6]}…（{len(v)} 字符）"


def scan_line(path: str, lineno: int, line: str, hits: list[tuple[str, int, str, str]]) -> None:
    if ALLOW_PRAGMA in line:
        return
    stripped = line.rstrip("\n")
    for name, pattern in PREFIX_RULES:
        for m in pattern.finditer(stripped):
            hits.append((path, lineno, name, mask(m.group(0))))
    for m in CONTEXT_RULE.finditer(stripped):
        value = m.group(2) or m.group(3) or ""
        if is_fake(value):
            continue
        hits.append((path, lineno, f"{m.group(1).lower()} 赋值", mask(value)))
    if CONTEXT_WORDS.search(stripped):
        for m in HIGH_ENTROPY.finditer(stripped):
            value = m.group(0)
            if is_fake(value):
                continue
            hits.append((path, lineno, "高熵串（同行含 secret 语境）", mask(value)))


def read_text(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None  # 二进制或读不到：跳过（本仓库的凭据都是文本）


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if p]


def scan_worktree(hits: list[tuple[str, int, str, str]]) -> int:
    count = 0
    for path in tracked_files():
        parts = set(path.split("/"))
        if parts & SKIP_DIRS or os.path.splitext(path)[1].lower() in SKIP_SUFFIX:
            continue
        text = read_text(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            scan_line(path, lineno, line, hits)
        count += 1
    return count


def scan_staged(hits: list[tuple[str, int, str, str]]) -> int:
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        capture_output=True, text=True, check=True).stdout
    path, lineno, added = "(staged)", 0, 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            lineno += 1
            added += 1
            scan_line(path, lineno, line[1:], hits)
    return added


def scan_history(limit: int, hits: list[tuple[str, int, str, str]]) -> int:
    revs = subprocess.run(["git", "rev-list", f"--max-count={limit}", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.split()
    count = 0
    for rev in revs:
        show = subprocess.run(["git", "show", "--unified=0", "--no-color",
                               "--format=%h", rev],
                              capture_output=True, text=True, check=True).stdout
        path, lineno = "(?)", 0
        for line in show.splitlines():
            if line.startswith("+++ b/"):
                path = f"{path if path != '(?)' else ''}{line[6:]}"
            elif line.startswith("@@"):
                m = re.search(r"\+(\d+)", line)
                lineno = int(m.group(1)) - 1 if m else 0
            elif line.startswith("+") and not line.startswith("+++"):
                lineno += 1
                local: list[tuple[str, int, str, str]] = []
                scan_line(path, lineno, line[1:], local)
                for _, _, name, masked in local:
                    hits.append((f"{rev[:8]}:{path}", lineno, name, masked))
        count += 1
    return count


def load_known_values(path: str) -> list[str]:
    text = read_text(path)
    if text is None:
        return []
    values: set[str] = set()
    for m in re.finditer(r"[A-Za-z0-9_\-]{20,}", text):
        v = m.group(0)
        if is_fake(v):
            continue
        if v.startswith(("http", "packages", "node_modules")):
            continue
        values.add(v)
    return sorted(values)


def scan_known(hits: list[tuple[str, int, str, str]], known: list[str]) -> int:
    if not known:
        return 0
    count = 0
    for path in tracked_files():
        parts = set(path.split("/"))
        if parts & SKIP_DIRS:
            continue
        text = read_text(path)
        if text is None:
            continue
        for value in known:
            for m in re.finditer(re.escape(value), text):
                lineno = text.count("\n", 0, m.start()) + 1
                hits.append((path, lineno, "已知凭据值（值级反查）", mask(value)))
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描仓库里的凭据泄漏")
    ap.add_argument("--staged", action="store_true", help="只扫暂存区新增行（pre-commit）")
    ap.add_argument("--history", type=int, default=0, metavar="N", help="额外扫最近 N 个提交")
    ap.add_argument("--secrets-file", default=None,
                    help="已知凭据登记文件（如 ~/.meshdeck-secrets.md）→ 值级反查")
    args = ap.parse_args()

    hits: list[tuple[str, int, str, str]] = []
    scanned = scan_staged(hits) if args.staged else scan_worktree(hits)
    if args.history:
        scan_history(args.history, hits)
    if args.secrets_file:
        path = os.path.expanduser(args.secrets_file)
        if not os.path.exists(path):
            print(f"⚠️  登记文件不存在：{path}（跳过值级反查）")
        else:
            scan_known(hits, load_known_values(path))

    if hits:
        print(f"❌ 发现 {len(hits)} 处疑似凭据（扫描单位：{scanned}）：\n")
        for path, lineno, name, masked in hits:
            print(f"  {path}:{lineno}  [{name}]  {masked}")
        print("\n处置：确属误报 → 该行加 `secret-scan: allow`；真凭据 → 立即轮换，"
              "并从提交里移除（值级轮换优先于改写历史）。")
        return 1

    mode = "暂存区" if args.staged else "工作区"
    extra = []
    if args.history:
        extra.append(f"最近 {args.history} 个提交")
    if args.secrets_file:
        extra.append("值级反查")
    suffix = f"（含 {'、'.join(extra)}）" if extra else ""
    print(f"✅ 干净：{mode} {scanned} 个扫描单位无凭据形态命中{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
