import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type {
  AgentInfo,
  FileInfo,
  SuperSyncConfig,
  SuperSyncLogEntry,
  SuperSyncLogLevel,
  SuperSyncStatus,
} from '../types';

interface SuperSyncPanelProps {
  agents: AgentInfo[];
}

type SubTab = 'status' | 'scope' | 'logs';

const STATE_LABEL: Record<string, string> = {
  running: '运行中',
  stopped: '已停止',
  error: '异常',
};

const LEVELS: SuperSyncLogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

/** 状态轮询间隔：需 ≤ 3 秒（需求） */
const STATUS_POLL_MS = 2500;

/** 允许纳入超级同步的核心文档（矩阵列固定为这些文档，与后端 SYNC_FILENAMES 保持一致） */
const SYNC_DOCUMENTS = ['SOUL.md', 'AGENTS.md', 'USER.md', 'MEMORY.md', 'IDENTITY.md'];

function formatClock(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', { hour12: false });
}

/** datetime-local 值 → unix 秒 */
function localInputToUnix(value: string): number | undefined {
  if (!value) return undefined;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? undefined : Math.floor(t / 1000);
}

/**
 * 超级同步面板（业务工具页内嵌）：
 * - 运行状态：独立脚本进程的 运行中/已停止/异常，2.5s 自动刷新 + 手动刷新；
 * - 同步范围：选择参与 Agent 与其下具体文件，支持按路径/类型批量筛选；
 * - 同步日志：按级别 / 时间范围检索、查看变更内容、导出。
 */
export function SuperSyncPanel({ agents }: SuperSyncPanelProps) {
  const { push: toast } = useToast();
  const [sub, setSub] = useState<SubTab>('status');

  // ---- 状态 ----
  const [status, setStatus] = useState<SuperSyncStatus | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.superSyncStatus());
    } catch {
      // 静默失败：保留上次状态
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshStatus]);

  const toggleRun = useCallback(
    async (action: 'start' | 'stop' | 'restart') => {
      setStatusBusy(true);
      try {
        if (action === 'stop' || action === 'restart') {
          setStatus(await api.stopSuperSync());
        }
        if (action === 'start' || action === 'restart') {
          setStatus(await api.startSuperSync());
        }
        toast(action === 'stop' ? '超级同步已停止' : '超级同步已启动', 'success');
      } catch (e) {
        toast(`${action === 'stop' ? '停止' : '启动'}失败：${(e as Error).message}`, 'error');
      } finally {
        setStatusBusy(false);
        void refreshStatus();
      }
    },
    [refreshStatus, toast],
  );

  // ---- 范围配置 ----
  const [config, setConfig] = useState<SuperSyncConfig | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filesByAgent, setFilesByAgent] = useState<Record<string, FileInfo[]>>({});
  const [loadingAgent, setLoadingAgent] = useState<Record<string, boolean>>({});
  const savedRef = useRef<string>('');
  const loadedRef = useRef<Set<string>>(new Set());
  const loadingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    void (async () => {
      try {
        const cfg = await api.superSyncConfig();
        setConfig(cfg);
        savedRef.current = JSON.stringify(cfg);
      } catch (e) {
        toast(`加载同步配置失败：${(e as Error).message}`, 'error');
      }
    })();
  }, [toast]);

  const ensureFiles = useCallback(
    async (agentId: string) => {
      if (loadedRef.current.has(agentId) || loadingRef.current.has(agentId)) return;
      loadingRef.current.add(agentId);
      setLoadingAgent((prev) => ({ ...prev, [agentId]: true }));
      try {
        const fs = await api.listFiles(agentId);
        loadedRef.current.add(agentId);
        setFilesByAgent((prev) => ({ ...prev, [agentId]: fs }));
      } catch (e) {
        loadingRef.current.delete(agentId);
        toast(`加载 ${agentId} 文件失败：${(e as Error).message}`, 'error');
      } finally {
        setLoadingAgent((prev) => ({ ...prev, [agentId]: false }));
      }
    },
    [toast],
  );

  /** 矩阵行：当前全部 Agent（并保留配置里残留的 id，避免静默丢失勾选） */
  const allAgentIds = useMemo(() => {
    const ids = agents.map((a) => a.id);
    (config?.agents ?? []).forEach((id) => {
      if (!ids.includes(id)) ids.push(id);
    });
    return ids;
  }, [agents, config?.agents]);

  /** 文档列 → 拥有该文档的 Agent 集合（仅统计白名单内的核心文档） */
  const fileIndex = useMemo(() => {
    const map = new Map<string, Set<string>>();
    allAgentIds.forEach((id) =>
      (filesByAgent[id] ?? []).forEach((f) => {
        if (!SYNC_DOCUMENTS.includes(f.path)) return;
        const owners = map.get(f.path) ?? new Set<string>();
        owners.add(id);
        map.set(f.path, owners);
      }),
    );
    return map;
  }, [allAgentIds, filesByAgent]);

  /** 矩阵列：白名单文档中至少被一个 Agent 拥有的那些（按白名单固定顺序） */
  const columns = useMemo(
    () => SYNC_DOCUMENTS.filter((name) => fileIndex.has(name)),
    [fileIndex],
  );

  /** 已勾选矩阵：agent → 已选文档集合，供单元格 O(1) 判定 */
  const checkedByAgent = useMemo(() => {
    const map = new Map<string, Set<string>>();
    allAgentIds.forEach((id) => map.set(id, new Set(config?.files[id] ?? [])));
    return map;
  }, [allAgentIds, config?.files]);

  const agentLabel = useCallback(
    (id: string) => agents.find((a) => a.id === id)?.display_name || id,
    [agents],
  );

  // 进入「同步范围」即加载全部 Agent 的文件清单，用于构建文档列
  useEffect(() => {
    if (sub !== 'scope') return;
    allAgentIds.forEach((id) => void ensureFiles(id));
  }, [sub, allAgentIds, ensureFiles]);

  const anyLoading = Object.values(loadingAgent).some(Boolean);

  const updateConfig = useCallback((updater: (prev: SuperSyncConfig) => SuperSyncConfig) => {
    setConfig((prev) => (prev ? updater(prev) : prev));
  }, []);

  // 脏标记：与最近一次保存的快照比较
  useEffect(() => {
    if (config) setDirty(JSON.stringify(config) !== savedRef.current);
  }, [config]);

  /** 统一改写矩阵：mutate 直接改 files，随后由 files 反推 agents（有勾选的 Agent 才参与同步） */
  const applyFiles = useCallback(
    (mutate: (files: Record<string, string[]>) => Record<string, string[]>) => {
      updateConfig((prev) => {
        const files = mutate({ ...prev.files });
        const extra = Object.keys(files).filter((id) => !prev.agents.includes(id));
        const agentsNext = [...prev.agents, ...extra].filter((id) => (files[id]?.length ?? 0) > 0);
        return { ...prev, agents: agentsNext, files };
      });
    },
    [updateConfig],
  );

  /** 单元格：某个 Agent 的某个文档是否纳入同步 */
  const toggleCell = useCallback(
    (agentId: string, path: string, checked: boolean) => {
      applyFiles((files) => {
        const current = new Set(files[agentId] ?? []);
        if (checked) current.add(path);
        else current.delete(path);
        files[agentId] = [...current];
        return files;
      });
    },
    [applyFiles],
  );

  /** 文档列：该文档在所有拥有它的 Agent 上整体勾选 / 取消（全选按钮归属文档列） */
  const setColumn = useCallback(
    (path: string, checked: boolean) => {
      applyFiles((files) => {
        (fileIndex.get(path) ?? new Set<string>()).forEach((id) => {
          const current = new Set(files[id] ?? []);
          if (checked) current.add(path);
          else current.delete(path);
          files[id] = [...current];
        });
        return files;
      });
    },
    [applyFiles, fileIndex],
  );

  const saveConfig = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await api.updateSuperSyncConfig(config);
      setConfig(saved);
      savedRef.current = JSON.stringify(saved);
      setDirty(false);
      const running = status?.state === 'running';
      toast(running ? '同步范围已保存（需重启超级同步生效）' : '同步范围已保存', 'success');
    } catch (e) {
      toast(`保存失败：${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }, [config, status?.state, toast]);

  // ---- 日志 ----
  const [levels, setLevels] = useState<Set<SuperSyncLogLevel>>(new Set(LEVELS));
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [logLimit, setLogLimit] = useState(200);
  const [logs, setLogs] = useState<SuperSyncLogEntry[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logLoading, setLogLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const logParams = useMemo(
    () => ({
      levels: [...levels].join(',') || undefined,
      since: localInputToUnix(since),
      until: localInputToUnix(until),
      limit: logLimit,
    }),
    [levels, since, until, logLimit],
  );

  const loadLogs = useCallback(async () => {
    setLogLoading(true);
    try {
      const res = await api.superSyncLogs(logParams);
      setLogs(res.items);
      setLogTotal(res.total);
    } catch (e) {
      toast(`加载日志失败：${(e as Error).message}`, 'error');
    } finally {
      setLogLoading(false);
    }
  }, [logParams, toast]);

  useEffect(() => {
    if (sub === 'logs') void loadLogs();
  }, [sub, loadLogs]);

  const exportLogs = useCallback(async () => {
    try {
      await api.exportSuperSyncLogs({
        levels: logParams.levels,
        since: logParams.since,
        until: logParams.until,
      });
      toast('日志已导出', 'success');
    } catch (e) {
      toast(`导出失败：${(e as Error).message}`, 'error');
    }
  }, [logParams, toast]);

  const toggleLevel = (lv: SuperSyncLogLevel) => {
    setLevels((prev) => {
      const next = new Set(prev);
      if (next.has(lv)) next.delete(lv);
      else next.add(lv);
      return next;
    });
  };

  const stateClass = status?.state ?? 'stopped';

  return (
    <div className="super-sync">
      <div className="page-tabs">
        {(
          [
            ['status', '运行状态'],
            ['scope', '同步范围'],
            ['logs', '同步日志'],
          ] as [SubTab, string][]
        ).map(([key, label]) => (
          <button key={key} className={`page-tab${sub === key ? ' active' : ''}`} onClick={() => setSub(key)}>
            {label}
          </button>
        ))}
      </div>

      {/* ================= 运行状态 ================= */}
      {sub === 'status' && (
        <div>
          <div className="ss-status-card">
            <span className={`ss-dot ${stateClass}`} />
            <div style={{ flex: 1 }}>
              <div className="ss-status-title">{STATE_LABEL[stateClass] ?? stateClass}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                独立脚本进程，即使关闭 Soulforge 主进程仍会持续运行
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-primary"
                disabled={statusBusy || status?.state === 'running'}
                onClick={() => void toggleRun('start')}
              >
                {statusBusy && status?.state !== 'running' && <span className="spinner" />}
                启动
              </button>
              <button
                className="btn"
                disabled={statusBusy || !status || status.state === 'stopped'}
                onClick={() => void toggleRun('stop')}
              >
                停止
              </button>
              <button className="btn" disabled={statusBusy} onClick={() => void toggleRun('restart')}>
                重启
              </button>
              <button className="btn btn-ghost" onClick={() => void refreshStatus()} title="立即刷新状态">
                刷新
              </button>
            </div>
          </div>

          {status?.state === 'error' && (
            <div className="alert-banner danger">
              脚本进程存在但心跳超时（可能卡死），建议「重启」。
              {status.last_error ? ` 最近错误：${status.last_error}` : ''}
            </div>
          )}

          <div className="ss-meta-grid">
            <Meta label="PID" value={status?.pid ?? '—'} />
            <Meta label="启动来源" value={status?.source === 'ui' ? 'UI 按钮' : status?.source === 'cli' ? '命令行' : '—'} />
            <Meta label="启动时间" value={formatClock(status?.started_at)} />
            <Meta label="最近心跳" value={formatClock(status?.last_heartbeat)} />
            <Meta
              label="心跳间隔"
              value={status?.interval_seconds != null ? `${status.interval_seconds}s` : '—'}
            />
            <Meta label="轮询次数" value={status?.ticks ?? 0} />
            <Meta label="已同步文件数" value={status?.synced_total ?? 0} />
            <Meta label="最近同步" value={formatClock(status?.last_sync_at)} />
          </div>

          <div className="section-title">参与同步的 Agent</div>
          {status?.agents && status.agents.length > 0 ? (
            <div className="ss-chip-row">
              {status.agents.map((a) => (
                <span key={a} className="ss-chip">
                  {a}
                </span>
              ))}
            </div>
          ) : (
            <div className="muted" style={{ fontSize: 13 }}>
              尚未配置同步范围（切换到「同步范围」选择 Agent 与文件）。
            </div>
          )}
        </div>
      )}

      {/* ================= 同步范围 ================= */}
      {sub === 'scope' && (
        <div>
          <div className="alert-banner info">
            选择参与同步的 Agent，以及每个 Agent 下纳入同步范围的文件。仅「同名且被选中」的文件会在秒级内保持内容一致；
            未选中的 Agent 与文件绝不纳入同步。
          </div>

          {!config ? (
            <div className="state-block">
              <div className="spinner-lg" />
              <div>加载配置中…</div>
            </div>
          ) : (
            <>
              <div className="ss-toolbar">
                <div className="field" style={{ margin: 0, width: 120 }}>
                  <label>轮询间隔（秒）</label>
                  <input
                    className="input"
                    type="number"
                    min={0.5}
                    max={60}
                    step={0.5}
                    value={config.interval_seconds}
                    onChange={(e) =>
                      updateConfig((prev) => ({ ...prev, interval_seconds: Number(e.target.value) || 1 }))
                    }
                  />
                </div>
                <div className="field" style={{ margin: 0, width: 140 }}>
                  <label>日志留存（天，≥30）</label>
                  <input
                    className="input"
                    type="number"
                    min={30}
                    max={3650}
                    value={config.retention_days}
                    onChange={(e) =>
                      updateConfig((prev) => ({ ...prev, retention_days: Number(e.target.value) || 30 }))
                    }
                  />
                </div>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                  {dirty && <span className="muted" style={{ fontSize: 12 }}>有未保存修改</span>}
                  <button
                    className="btn btn-primary"
                    disabled={!dirty || saving}
                    onClick={() => void saveConfig()}
                    title="保存同步范围（参与同步的 Agent 与保留天数）"
                  >
                    {saving && <span className="spinner" />}
                    保存范围
                  </button>
                </div>
              </div>

              <div className="section-title">同步矩阵（行 = Agent，列 = 文档；打勾 = 纳入同步）</div>

              <div className="alert-banner info" style={{ marginBottom: 12 }}>
                同步以「文档」为单位：对同一个文档，可一键全选所有拥有它的 Agent 一起同步。
                仅 {SYNC_DOCUMENTS.join('、')} 这 {SYNC_DOCUMENTS.length} 个核心文档参与同步。
              </div>

              {allAgentIds.length === 0 ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  暂无 Agent。
                </div>
              ) : columns.length === 0 ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  所选 Agent 中没有可同步的核心文档（{SYNC_DOCUMENTS.join('、')}）。
                </div>
              ) : (
                <>
                  <div className="ss-matrix-wrap">
                    <table className="ss-matrix">
                      <thead>
                        <tr>
                          <th className="ss-matrix-corner">Agent \ 文档</th>
                          {columns.map((p) => {
                            const owners = [...(fileIndex.get(p) ?? [])];
                            const allSel =
                              owners.length > 0 &&
                              owners.every((id) => checkedByAgent.get(id)?.has(p));
                            const anyChecked = owners.some((id) => checkedByAgent.get(id)?.has(p));
                            return (
                              <th key={p} className="ss-matrix-col">
                                <div className="ss-col-name" title={p}>
                                  {p}
                                </div>
                                <div className="ss-col-actions">
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    disabled={allSel}
                                    title={`全选所有拥有 ${p} 的 Agent`}
                                    onClick={() => setColumn(p, true)}
                                  >
                                    全选
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    disabled={!anyChecked}
                                    title={`清空所有拥有 ${p} 的 Agent`}
                                    onClick={() => setColumn(p, false)}
                                  >
                                    清空
                                  </button>
                                </div>
                              </th>
                            );
                          })}
                        </tr>
                      </thead>
                      <tbody>
                        {allAgentIds.map((agentId) => (
                          <tr key={agentId}>
                            <th className="ss-matrix-row" title={agentId}>
                              <span className="ss-row-name">{agentLabel(agentId)}</span>
                            </th>
                            {columns.map((p) => {
                              const has = fileIndex.get(p)?.has(agentId) ?? false;
                              const checked = checkedByAgent.get(agentId)?.has(p) ?? false;
                              return (
                                <td key={p} className={`ss-matrix-cell${has ? '' : ' na'}`}>
                                  {has ? (
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      title={`${agentId} × ${p}`}
                                      onChange={(e) => toggleCell(agentId, p, e.target.checked)}
                                    />
                                  ) : (
                                    <span className="muted">—</span>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                    共 {columns.length} 个文档 × {allAgentIds.length} 个 Agent；已勾选{' '}
                    {config.agents.length} 个 Agent /{' '}
                    {Object.values(config.files).reduce((sum, arr) => sum + arr.length, 0)} 个单元格。
                    {anyLoading && ' 正在加载文件清单…'}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {/* ================= 同步日志 ================= */}
      {sub === 'logs' && (
        <div>
          <div className="ss-toolbar">
            <span className="muted" style={{ fontSize: 12 }}>级别：</span>
            {LEVELS.map((lv) => (
              <label key={lv} className="checkbox-row" style={{ padding: '0 6px 0 0' }}>
                <input type="checkbox" checked={levels.has(lv)} onChange={() => toggleLevel(lv)} />
                <span style={{ fontSize: 12 }}>{lv}</span>
              </label>
            ))}
            <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>时间：</span>
            <input
              className="input"
              type="datetime-local"
              style={{ maxWidth: 210 }}
              value={since}
              onChange={(e) => setSince(e.target.value)}
            />
            <span className="muted">~</span>
            <input
              className="input"
              type="datetime-local"
              style={{ maxWidth: 210 }}
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
            <select
              className="select"
              style={{ maxWidth: 110 }}
              value={logLimit}
              onChange={(e) => setLogLimit(Number(e.target.value))}
            >
              {[100, 200, 500, 1000].map((n) => (
                <option key={n} value={n}>
                  最近 {n} 条
                </option>
              ))}
            </select>
            <button className="btn btn-sm" onClick={() => void loadLogs()} disabled={logLoading}>
              {logLoading && <span className="spinner" />}
              查询
            </button>
            <button className="btn btn-sm" onClick={() => void exportLogs()}>
              导出
            </button>
          </div>

          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
            共 {logTotal} 条（日志留存 ≥ 30 天，可导出为 .jsonl）
          </div>

          {logs.length === 0 ? (
            <div className="state-block">
              <div>暂无同步日志</div>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="ss-log-table">
                <thead>
                  <tr>
                    <th style={{ width: 168 }}>时间</th>
                    <th style={{ width: 70 }}>级别</th>
                    <th style={{ width: 70 }}>事件</th>
                    <th>文件</th>
                    <th style={{ width: 180 }}>源 → 目标</th>
                    <th style={{ width: 60 }}>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((row, i) => {
                    const isOpen = expanded.has(i);
                    const detail = row.diff || row.error || row.message;
                    return (
                      <tr
                        key={`${row.ts_unix}-${i}`}
                        className={detail ? 'ss-log-row' : undefined}
                        onClick={() => {
                          if (!detail) return;
                          setExpanded((prev) => {
                            const next = new Set(prev);
                            if (next.has(i)) next.delete(i);
                            else next.add(i);
                            return next;
                          });
                        }}
                      >
                        <td className="mono" style={{ fontSize: 12 }}>
                          {new Date(row.ts_unix * 1000).toLocaleString('zh-CN', { hour12: false })}
                        </td>
                        <td>
                          <span className={`ss-level ss-level-${row.level.toLowerCase()}`}>{row.level}</span>
                        </td>
                        <td style={{ fontSize: 12 }}>{row.event}</td>
                        <td className="mono" style={{ fontSize: 12 }}>
                          {row.path ?? row.message ?? '—'}
                          {isOpen && detail && <pre className="ss-log-diff">{detail}</pre>}
                        </td>
                        <td className="mono" style={{ fontSize: 12 }}>
                          {row.source_agent ? `${row.source_agent} → ${row.target_agent}` : '—'}
                        </td>
                        <td style={{ fontSize: 12 }}>{row.result ?? '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="ss-meta">
      <div className="ss-meta-label">{label}</div>
      <div className="ss-meta-value">{value}</div>
    </div>
  );
}
