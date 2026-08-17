# dsh-auto-archive

自动归档闲置会话 —— 工作区会话闲置 N 天无活动后，自动加入归档集合（从列表隐藏），**数据保留、可随时取消归档**。

宿主端（Host half）插件，无需浏览器端 bundle。活动度判定与 dsh 自带的 session.list 排序完全一致（`updatedAt = max(createdAt, lastPromptAt)`，lastPromptAt 仅在用户发消息时更新）。

## 效果

| 行为 | 说明 |
|---|---|
| 闲置判定 | 上次用户消息距今 ≥ `idleDays` 天（默认 7） |
| 归档动作 | 写入 registry 全局 `archivedSessionIds`，所有列表视图隐藏该会话 |
| 数据 | 不删除、不压缩、不动原始会话文件，取消归档即恢复原位 |
| 扫描周期 | 默认每小时一次；插件启动 3 秒后立即执行首轮扫描 |
| 安全性 | 单次扫描默认最多归档 100 个；所有扫尾异常只记日志，绝不中断宿主 |

## 安全边界（默认值，均可配置）

- 跳过错开运行中的会话（agent running）；
- 跳过错开已归档会话（幂等，重复归档是 no-op）；
- 跳过错开 subagent 子会话（归父会话管理，单独归档会破坏子代理面板）；
- 错开 blank（从未开过 turn）会话；
- **默认只归档冷会话**（`archiveAttached: false`）——内存中挂载的会话意味着有界面正打开，归档会把使用者从该会话踢出；
- 单次扫描上限 `maxArchivePerRun`（默认 100），防止阈值误配一次性误归档。

## 配置

配置写在 `~/.dsh/profiles/web/cordis.patch.yml` 中 `- id: dsh-auto-archive` 的 `config:` 段，修改后重启 dsh 生效：

```yaml
- insert:
    - id: dsh-auto-archive
      name: 'dsh-auto-archive'
      config:
        idleDays: 7              # 闲置天数阈值（默认 7）
        scanIntervalMinutes: 60  # 扫描间隔分钟（默认 60）
        dryRun: false            # true 时只打印将归档的会话，不实际操作
        archiveAttached: false   # true 时也允许归档内存中挂载（正在被界面打开）的会话
        skipBlank: true          # 跳过从未开过 turn 的 blank 会话
        maxArchivePerRun: 100    # 单次扫描归档上限
```

## 安装与激活

```bash
cd path/to/dsh-plugins/packages/dsh-auto-archive
bash install.sh --check          # 只读检查（源码副本 + 契约预检 + patch 接线）
bash install.sh                  # 安装：源码留档 + 运行副本 + patch 接线
bash install.sh --smoke          # headless 隔离 profile 试启动冒烟（不影响正式服务）
bash install.sh --restart        # 冒烟通过后重启 dsh web，插件生效
```

参数：`--idle-days N`、`--scan-minutes N`、`--dry-run`、`--archive-attached`、`--no-config`（不写配置，用插件默认值）、`--profile web|headless`。

> ⚠️ 重启必须在**终端**执行（`bash install.sh --restart`），不要在 agent 会话内执行——agent 跑在宿主进程里，重启即自杀（MR-022/023 教训）。

### 卸载

```bash
bash install.sh --uninstall   # 移除 patch 接线 + 运行副本；重启 dsh 后生效
```

## 工作原理（源码要点）

- 活动度折叠与 host-apiproxy `sessionListMetadata` 一致：`lastPromptAt` 仅统计 `user/message` 且 `data.source.kind === "user"` 的事件。
- attached（内存挂载）会话：事件折叠，不出磁盘；
- cold（冷）会话：用持久化文件 mtime 作为最后活动时间，避免整段日志回放；
- 归档调用 `ctx.workspaceRegistry.archiveSession(id)`（与 UI 右键"归档会话"同一 API）。

## 运行日志

插件的激活、归档、扫描汇总均以 `[dsh-auto-archive]` 前缀写入进程日志：

```bash
tail -f /tmp/dsh-web.log | grep dsh-auto-archive
```

另有心跳文件（激活与每次扫描各追加一行，最直接的存活证明）：

```bash
tail -f /tmp/dsh-auto-archive-heartbeat.log
```

## 已知限制

- 冷会话不做 blank 探测（需读整段日志），blank 旧会话会被按普通会话处理；
- 配置修改需重启 dsh 生效（无热更新）；
- 归档不省存储——只归档不做删除是本插件设计原则，需要删除请另行处理。
