/**
 * dsh-auto-archive — 自动归档闲置会话（Host half）。
 *
 * 工作区会话"闲置 N 天无活动"后自动加入归档集合（archivedSessionIds）：
 * 仅从列表视图隐藏，**不删除任何数据**；取消归档可在找回后恢复原位。
 *
 * 活动度判定与 dsh 自带 session.list 排序完全一致（host-apiproxy 的
 * sessionListUpdatedAt）：updatedAt = max(header.createdAt, lastPromptAt)，
 * 其中 lastPromptAt 仅在用户发消息（user/message 且 data.source.kind==="user"）
 * 时更新。冷会话（未挂载到内存）以持久化文件的 mtime 作为最后活动时间，
 * 免去整段日志回放。
 *
 * 激活：apply 内用 ctx.inject 延迟启动（dsh-session-projection 文档明确的
 * "服务缺失时保持休眠、不影响组装"模式）。web 组合挂齐三个服务后生效；
 * headless 等未挂载这些服务的 profile 中静默等待，不阻塞启动。
 *
 * 观测：除 console/logger 双路输出外，另写心跳文件
 * /tmp/dsh-auto-archive-heartbeat.log（激活与每次扫描各追加一行），
 * 用于确认插件确实在运行（dsh web 的 ctx.logger 不写进程日志）。
 *
 * 安全边界（默认行为，均可配置）：
 *   - 跳过运行中的会话（agent 处于 running）；
 *   - 跳过已归档会话（幂等，重复归档是 no-op）；
 *   - 跳过 subagent 子会话（归父会话管理，单独归档会破坏子代理面板）；
 *   - 跳过 blank（从未开过 turn）会话；
 *   - 默认只归档冷会话（archiveAttached=false）——内存中挂载的会话
 *     意味着有浏览器/界面正在打开，归档会把使用者从该会话踢出去；
 *   - 单次扫描上限 maxArchivePerRun，防止阈值误配导致一次性误归档。
 *
 * 配置（cordis.patch.yml 中 - id: dsh-auto-archive 的 config，改后需重启）:
 *   idleDays:            闲置天数阈值，默认 7
 *   scanIntervalMinutes: 扫描间隔分钟，默认 60
 *   dryRun:              true 只打印将归档的会话不实际操作，默认 false
 *   archiveAttached:     是否允许归档内存中挂载的会话，默认 false
 *   skipBlank:           是否跳过从未开过 turn 的 blank 会话，默认 true
 *   maxArchivePerRun:    单次扫描归档上限，默认 100
 */
import { appendFileSync } from "node:fs";
import z from "@deepseek-ai/schemastery";

export const name = "dsh-auto-archive";

export const Config = z.object({
  idleDays: z.number().min(0.1).default(7),
  scanIntervalMinutes: z.number().min(1).default(60),
  dryRun: z.boolean().default(false),
  archiveAttached: z.boolean().default(false),
  skipBlank: z.boolean().default(true),
  maxArchivePerRun: z.natural().min(1).default(100),
});

const MS_PER_DAY = 24 * 60 * 60 * 1000;
const HEARTBEAT_FILE = "/tmp/dsh-auto-archive-heartbeat.log";

/**
 * 与 host-apiproxy sessionListMetadata 完全一致的折叠：
 * blank —— 直到出现第一个非 turn/start 事件才变为 false；
 * lastPromptAt —— 仅用户消息（source.kind === "user"）更新。
 */
function foldListMetadata(events) {
  let state = { blank: true, lastPromptAt: null };
  for (const event of events) {
    const blank = state.blank && event.type !== "turn/start";
    const lastPromptAt =
      event.type === "user/message" && event.data?.source?.kind === "user" ? event.time : state.lastPromptAt;
    state = { blank, lastPromptAt };
  }
  return state;
}

/** 简单守卫：可用的 agent 状态是否为 running。 */
function isRunning(ctx, sessionId) {
  const agents = ctx.get("agents");
  return agents?.get?.(sessionId)?.status === "running";
}

/** 守卫：会话是否为 subagent 子会话（其展示归父会话管理）。 */
function isSubagent(meta) {
  return meta?.origin === "subagent" || meta?.parentSession !== void 0;
}

/** 追加一行心跳，供外部确认插件在运行（fs 追加失败仅忽略）。 */
function heartbeat(line) {
  try {
    appendFileSync(HEARTBEAT_FILE, `[${new Date().toISOString()}] ${line}\n`, "utf8");
  } catch {
    /* 心跳失败不影响功能 */
  }
}

export function apply(ctx) {
  // 延迟启动：web 组合服务到位后生效；缺失时静默等待，不影响宿主启动。
  return ctx.inject(["workspaceRegistry", "sessions", "sessionPersistence"], (ctx2, config) => {
    const workspaceRegistry = ctx2.workspaceRegistry;
    const sessions = ctx2.sessions;
    const persistence = ctx2.sessionPersistence;
    const logger = ctx2.logger ?? console;
    const tag = "[dsh-auto-archive]";
    // 双路输出：console 落进程 stdout（dsh web 实测仅此路可 grep）；ctx.logger 供界面侧。
    const log = (message) => { console.log(`${tag} ${message}`); logger?.info?.(`${tag} ${message}`); };
    const warn = (message) => { console.warn(`${tag} ${message}`); logger?.warn?.(`${tag} ${message}`); };
    let disposed = false;

    const cfg = config ?? {};
    const idleMs = (cfg.idleDays ?? 7) * MS_PER_DAY;
    const idleDaysLabel = cfg.idleDays ?? 7;
    const intervalMs = (cfg.scanIntervalMinutes ?? 60) * 60 * 1000;
    const dryRun = cfg.dryRun === true;
    const archiveAttached = cfg.archiveAttached === true;
    const skipBlank = cfg.skipBlank !== false;
    const maxArchivePerRun = cfg.maxArchivePerRun ?? 100;

    /** 一次扫描：收集候选并归档。任何异常只记日志。 */
    async function runSweep() {
      const now = Date.now();
      const archivedSet = new Set(workspaceRegistry.archivedSessionIds);
      const attached = sessions.list();
      const attachedById = new Map(attached.map((session) => [session.id, session]));

      /** attached 会话（内存中挂载）：事件折叠 lastPromptAt/blank。 */
      const attachedCandidates = [];
      for (const session of attached) {
        const meta = session.header;
        if (meta === void 0 || isSubagent(meta)) continue;
        if (isRunning(ctx2, session.id)) continue;
        const folded = foldListMetadata(session.events);
        const updatedAt = Math.max(meta.createdAt ?? 0, folded.lastPromptAt ?? 0);
        attachedCandidates.push({ id: session.id, updatedAt, blank: folded.blank, cold: false });
      }

      /** 冷会话：header 元数据 + 文件 mtime 作为最后活动时间。 */
      const coldCandidates = [];
      if (persistence !== void 0) {
        const metas = await persistence.list(void 0);
        for (const meta of metas) {
          if (attachedById.has(meta.id)) continue;
          if (meta.cwd === void 0) continue;
          if (isSubagent(meta)) continue;
          if (isRunning(ctx2, meta.id)) continue;
          let mtime = meta.createdAt ?? 0;
          try {
            const location = persistence.locate(meta);
            if (location?.path !== void 0) {
              const fs = await import("node:fs/promises");
              const stat = await fs.stat(location.path);
              mtime = stat.mtimeMs;
            }
          } catch (error) {
            warn(`cold stat failed for ${meta.id}: ${String(error)}`);
          }
          coldCandidates.push({
            id: meta.id,
            updatedAt: Math.max(meta.createdAt ?? 0, mtime),
            blank: false, // 冷会话不做 blank 探测（需读整段日志，代价高）
            cold: true,
          });
        }
      }

      const all = archiveAttached ? [...attachedCandidates, ...coldCandidates] : coldCandidates;
      const candidates = all
        .filter((c) => !archivedSet.has(c.id))
        .filter((c) => !(skipBlank && c.blank === true))
        .filter((c) => now - c.updatedAt >= idleMs)
        .sort((a, b) => b.updatedAt - a.updatedAt); // 最久未动的优先

      let archived = 0;
      for (const candidate of candidates) {
        if (archived >= maxArchivePerRun) {
          warn(`hit maxArchivePerRun=${maxArchivePerRun}; remaining candidates wait for the next scan`);
          break;
        }
        const idleDays = (now - candidate.updatedAt) / MS_PER_DAY;
        const label = candidate.cold ? "cold" : "attached";
        if (dryRun) {
          log(`[dry-run] would archive ${candidate.id} (${label}, idle ${idleDays.toFixed(1)}d)`);
          heartbeat(`dry-run would archive ${candidate.id} (${idleDays.toFixed(1)}d)`);
          continue;
        }
        try {
          await workspaceRegistry.archiveSession(candidate.id);
          archived += 1;
          log(`archived ${candidate.id} (${label}, idle ${idleDays.toFixed(1)}d)`);
          heartbeat(`archived ${candidate.id} (${idleDays.toFixed(1)}d)`);
        } catch (error) {
          warn(`archive failed for ${candidate.id}: ${String(error)}`);
        }
      }
      const summary = `sweep done: candidates=${candidates.length} archived=${archived} (attached=${attachedCandidates.length} cold=${coldCandidates.length})`;
      log(summary);
      heartbeat(summary);
    }

    /** 带 try/catch 的定时入口：任何失败只记录，绝不中断宿主。 */
    const safeSweep = () => {
      if (disposed) return;
      void runSweep().catch((error) => {
        if (disposed) return;
        warn(`sweep failed: ${error instanceof Error ? error.stack : String(error)}`);
        heartbeat(`sweep failed: ${String(error)}`);
      });
    };

    const activeLine = `active: idleDays=${idleDaysLabel} archiveAttached=${archiveAttached} dryRun=${dryRun} skipBlank=${skipBlank} maxArchivePerRun=${maxArchivePerRun}`;
    log(activeLine);
    heartbeat(activeLine);

    // 启动后 3s 先跑首轮，再进入周期扫描；两个定时器都不阻止进程退出。
    const first = setTimeout(safeSweep, 3000);
    first.unref?.();
    const timer = setInterval(safeSweep, intervalMs);
    timer.unref?.();

    return () => {
      disposed = true;
      clearTimeout(first);
      clearInterval(timer);
      log("disposed: timer cleared");
    };
  });
}
