import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { ApiError } from '../api/client';
import { useToast } from '../hooks/useToast';
import type {
  AgentInfo,
  DailyRun,
  DailyRunItem,
  DailyRunItemStatus,
  DailyRunReport,
  DailyRunStatus,
  DailyRunSummary,
  LLMProvider,
  PresetSummary,
} from '../types';
import { formatBytes } from '../utils/format';
import { ConfirmDialog } from './ConfirmDialog';
import { DailyPresetEditor } from './DailyPresetEditor';
import { DiffView } from './DiffView';

interface DailyStandardizerPanelProps {
  agents: AgentInfo[];
}

type Stage = 'setup' | 'plan' | 'report';

/** 默认预设：与后端 `DailyRunCreate.preset_id` 的默认值保持一致 */
const DEFAULT_PRESET_ID = 'preset-wlog-daily-std';

const RUN_STATUS_LABEL: Record<DailyRunStatus, string> = {
  planned: '生成中',
  awaiting_confirm: '待确认',
  applied: '已应用',
  partially_applied: '部分成功',
  needs_review: '需复核',
  rejected: '已拒绝',
  failed: '失败',
  empty: '无可整理的日子',
};

const ITEM_STATUS_LABEL: Record<DailyRunItemStatus, string> = {
  pending: '排队中',
  planned: '待确认',
  failed: '生成失败',
  blocked: '写前验收不过',
  applied: '已应用',
  partially_applied: '碎片未清理',
  skipped: '已跳过',
  empty: '无可归档内容',
};

const KIND_LABEL: Record<string, string> = { A: '主文件', B: '会话导出', C: '主题碎片' };

/** 已写入/已作废的批次状态：此时不再允许拒绝（与后端 DailyRunService.reject 一致） */
const TERMINAL_RUNS: DailyRunStatus[] = ['applied', 'partially_applied', 'rejected'];

/**
 * 可勾选执行的状态：
 * - `planned`：写入归并后的日文件
 * - `empty`：模型判定本日无可归档内容 → 不写日文件，只在有碎片时清理碎片（主文件不动）
 */
function isApplicable(item: DailyRunItem): boolean {
  if (item.status === 'planned') return true;
  return item.status === 'empty' && item.fragments_to_delete.length > 0;
}

/** 该日执行时是否会写入日文件（用于确认弹窗如实标注每天的动作） */
function willWrite(item: DailyRunItem): boolean {
  return item.status === 'planned';
}

function isoOf(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * 工作日志标准化面板（M15 · 业务工具页内嵌）。
 *
 * 三阶段：参数 → 逐日计划（默认全部不勾选）→ 验收报告。
 * 计划阶段只读不落盘；只有显式确认的日期才会写入日文件并清理碎片（碎片走回收站）。
 */
export function DailyStandardizerPanel({ agents }: DailyStandardizerPanelProps) {
  const { push: toast } = useToast();
  const [stage, setStage] = useState<Stage>('setup');

  // ---- 参数 ----
  const [agentId, setAgentId] = useState(agents[0]?.id ?? '');
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    return isoOf(d);
  });
  const [dateTo, setDateTo] = useState(() => isoOf(new Date()));
  const [presetId, setPresetId] = useState(DEFAULT_PRESET_ID);
  const [providerId, setProviderId] = useState('');
  const [extra, setExtra] = useState('');
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);

  // ---- 批次 ----
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<DailyRun | null>(null);
  const [report, setReport] = useState<DailyRunReport | null>(null);
  const [history, setHistory] = useState<DailyRunSummary[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [rawDiff, setRawDiff] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [applyAll, setApplyAll] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);
  /** 正在页内编辑的工作日志预设 id（null = 未打开编辑器） */
  const [editPresetId, setEditPresetId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listPresets('WORKLOG'), api.listLLMProviders()])
      .then(([ps, lps]) => {
        setPresets(ps);
        const enabled = lps.filter((p) => p.enabled);
        setProviders(enabled);
        if (ps.some((p) => p.id === DEFAULT_PRESET_ID)) setPresetId(DEFAULT_PRESET_ID);
        else if (ps.length > 0) setPresetId(ps[0].id);
        if (enabled.length > 0) setProviderId(enabled[0].id);
      })
      .catch((e) => toast(`加载预设 / Provider 失败：${(e as Error).message}`, 'error'))
      .finally(() => setLoadingOptions(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadHistory = useCallback(
    async (id: string) => {
      if (!id) {
        setHistory([]);
        return;
      }
      try {
        setHistory(await api.listDailyRuns({ agent_id: id, limit: 20 }));
      } catch {
        setHistory([]); // 历史列表是辅助信息，失败不打扰用户
      }
    },
    [],
  );

  useEffect(() => {
    void loadHistory(agentId);
  }, [agentId, loadHistory]);

  const loadRun = useCallback(
    async (id: string) => {
      try {
        const r = await api.getDailyRun(id);
        setRun(r);
        return r;
      } catch (e) {
        toast(`加载批次失败：${(e as Error).message}`, 'error');
        return null;
      }
    },
    [toast],
  );

  // 生成阶段轮询（后台逐日跑 LLM，plan → awaiting_confirm / failed / empty）
  useEffect(() => {
    if (run?.status !== 'planned' || !runId) return;
    const timer = window.setInterval(() => {
      void loadRun(runId);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [run?.status, runId, loadRun]);

  const openRun = useCallback(
    async (id: string) => {
      setBusy(true);
      setReport(null);
      setChecked(new Set());
      setRunId(id);
      await loadRun(id);
      setStage('plan');
      setBusy(false);
      void loadHistory(agentId);
    },
    [agentId, loadHistory, loadRun],
  );

  const createRun = useCallback(async () => {
    if (!agentId) {
      toast('请选择 Agent', 'warning');
      return;
    }
    if (!providerId) {
      toast('请先在 设置 → LLM Provider 中配置并启用一个 Provider', 'warning');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast('请选择日期范围', 'warning');
      return;
    }
    if (dateFrom > dateTo) {
      toast('开始日期不能晚于结束日期', 'warning');
      return;
    }
    setBusy(true);
    try {
      const r = await api.createDailyRun({
        agent_id: agentId,
        date_from: dateFrom,
        date_to: dateTo,
        preset_id: presetId,
        provider_id: providerId,
        extra_instructions: extra.trim() || undefined,
      });
      setReport(null);
      setChecked(new Set());
      setRunId(r.run_id);
      setStage('plan');
      await loadRun(r.run_id);
      void loadHistory(agentId);
      if (r.reused) toast('与既有批次内容一致，已复用其结果（未重复调用 LLM）', 'info');
      else if (r.status === 'empty') toast('该范围内没有需要整理的日子', 'info');
      else toast(`已提交，正在逐日生成计划（共 ${r.days_total} 天）`, 'info');
    } catch (e) {
      toast(`创建批次失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [agentId, dateFrom, dateTo, presetId, providerId, extra, loadRun, loadHistory, toast]);

  const loadReport = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      setReport(await api.dailyRunReport(runId));
      setStage('report');
    } catch (e) {
      toast(`加载验收报告失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [runId, toast]);

  const doApply = useCallback(
    async (all: boolean) => {
      if (!runId) return;
      setBusy(true);
      try {
        const res = await api.applyDailyRun(runId, [...checked], all);
        const parts = [
          res.applied.length > 0 ? `${res.applied.length} 天已写入` : '',
          res.no_content.length > 0 ? `${res.no_content.length} 天无可归档内容（未写文件）` : '',
          res.partial.length > 0 ? `${res.partial.length} 天碎片未清理` : '',
          res.blocked.length > 0 ? `${res.blocked.length} 天写前验收不过` : '',
          res.failed.length > 0 ? `${res.failed.length} 天失败` : '',
        ].filter(Boolean);
        toast(parts.length > 0 ? `执行完成：${parts.join('、')}` : '执行完成：没有可写入的日子', 'success');
        setChecked(new Set());
        await loadRun(runId);
        void loadHistory(agentId);
        await loadReport();
      } catch (e) {
        const err = e as ApiError;
        const conflicts = (err.details as { conflicts?: { date: string; reason: string }[] } | undefined)
          ?.conflicts;
        if (conflicts && conflicts.length > 0) {
          toast(
            `未写入任何文件：${conflicts.length} 天的目标文件已被外部改动（${conflicts
              .map((c) => c.date)
              .join('、')}），请重新生成计划`,
            'error',
          );
        } else {
          toast(`执行失败：${err.message}`, 'error');
        }
        await loadRun(runId);
      } finally {
        setBusy(false);
        setConfirmApply(false);
      }
    },
    [runId, checked, loadRun, loadReport, loadHistory, agentId, toast],
  );

  const doSkip = useCallback(async () => {
    if (!runId || checked.size === 0) return;
    setBusy(true);
    try {
      const r = await api.skipDailyRun(runId, [...checked]);
      setRun(r);
      setChecked(new Set());
      toast(`已跳过 ${r.items.filter((i) => i.status === 'skipped').length} 天`, 'info');
      void loadHistory(agentId);
    } catch (e) {
      toast(`跳过失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [runId, checked, loadHistory, agentId, toast]);

  const doReject = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      setRun(await api.rejectDailyRun(runId));
      toast('已拒绝该批次（未写入任何文件）', 'info');
      void loadHistory(agentId);
    } catch (e) {
      toast(`拒绝失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
      setConfirmReject(false);
    }
  }, [runId, loadHistory, agentId, toast]);

  const toggleChecked = (date: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };

  const toggleRaw = (date: string) => {
    setRawDiff((prev) => {
      const next = new Set(prev);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };

  const generating = run?.status === 'planned';
  const applicable = useMemo(() => (run?.items ?? []).filter(isApplicable), [run?.items]);
  const hasDelivered = useMemo(
    () =>
      (run?.items ?? []).some(
        (i) =>
          i.status === 'applied' ||
          i.status === 'partially_applied' ||
          // 空日执行过（只清碎片）也要能看验收报告
          (i.status === 'empty' && i.decision === 'applied'),
      ),
    [run?.items],
  );
  const canAct = run?.status === 'awaiting_confirm' && !generating;

  /** 当前生效的工作日志预设（下拉选中的那个）：信息栏与页内编辑器都用它 */
  const currentPreset = presets.find((p) => p.id === presetId);

  const reloadPresets = useCallback(async () => {
    try {
      const ps = await api.listPresets('WORKLOG');
      setPresets(ps);
      if (!ps.some((p) => p.id === presetId)) setPresetId(ps[0]?.id ?? '');
    } catch (e) {
      toast(`刷新预设失败：${(e as Error).message}`, 'error');
    }
  }, [presetId, toast]);

  // ================= 参数 =================
  if (stage === 'setup') {
    return (
      <div className="daily-std">
        <div className="alert-banner warning">
          按「天」归并：把同一天的多份记录（主文件 / 会话导出 / 主题碎片）合并为唯一一份{' '}
          <span className="mono">memory/YYYY-MM-DD.md</span>。先生成计划，<b>逐日看完差异再确认写入</b>；
          确认前不写盘、不删任何文件。若某天全是噪音、没有值得留存的内容，模型会给出
          <b>「无可归档内容」</b>的判定——那天不产出日文件，也不会硬凑一篇。
        </div>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <label>Agent</label>
            <select className="select" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name || a.id}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ width: 170 }}>
            <label>开始日期</label>
            <input
              className="input"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div className="field" style={{ width: 170 }}>
            <label>结束日期</label>
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>

        <div className="section-title">工作日志标准化预设</div>
        {/* 预设信息栏：说清「当前生效的是哪个预设、它从哪来、专供谁用」——
            这类预设按边界不在设置页文档预设与主工作台「应用预设」里出现，
            因此必须在本界面标明身份与来源，避免用户找不到它在哪改。 */}
        {currentPreset && (
          <div className="daily-preset-info">
            <div className="daily-preset-info-head">
              <span className="daily-only-badge">大模型专用</span>
              <span className="daily-preset-info-name">
                {currentPreset.name}
                <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                  v{currentPreset.version}
                </span>
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                来源：{currentPreset.is_builtin ? '内置预设（随版本分发）' : '用户自建'}
              </span>
              <button
                className="btn btn-sm"
                style={{ marginLeft: 'auto' }}
                onClick={() => setEditPresetId(currentPreset.id)}
              >
                查看 / 编辑
              </button>
            </div>
            <div className="daily-preset-info-hint">
              该预设<b>专供大模型处理工作日志</b>（归并当天多份记录），不用于主工作台的文件整理；
              它不出现在「系统配置 → 文档预设」与主工作台「应用预设」中。修改保存后
              <b>重新生成批次即生效</b>。
            </div>
          </div>
        )}
        {loadingOptions ? (
          <div className="state-block">
            <div className="spinner-lg" />
            <div>正在加载…</div>
          </div>
        ) : presets.length === 0 ? (
          <div className="muted" style={{ fontSize: 13 }}>
            没有 WORKLOG 类型的预设。
          </div>
        ) : (
          <div className="daily-preset-list">
            {presets.map((p) => (
              <label key={p.id} className={`daily-preset${presetId === p.id ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="daily-preset"
                  checked={presetId === p.id}
                  onChange={() => setPresetId(p.id)}
                />
                <span style={{ minWidth: 0 }}>
                  <span className="daily-preset-name">
                    {p.name}
                    <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                      v{p.version}
                    </span>
                  </span>
                  {/* 功能简介来自后端 presets.description（文案事实源唯一，前端不硬编码） */}
                  <span className="daily-preset-desc">
                    {p.description?.trim() || '（该预设未填写说明）'}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="section-title">LLM Provider</div>
        {providers.length === 0 ? (
          <div className="hint" style={{ color: 'var(--danger)' }}>
            尚未配置启用的 LLM Provider：请先在 设置 → LLM Provider 管理 中添加并启用。
          </div>
        ) : (
          <div className="checkbox-grid" style={{ maxHeight: 120 }}>
            {providers.map((p) => (
              <label key={p.id} className="checkbox-row">
                <input
                  type="radio"
                  name="daily-provider"
                  checked={providerId === p.id}
                  onChange={() => setProviderId(p.id)}
                />
                <span style={{ minWidth: 0 }}>
                  {p.id}
                  <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                    {p.model}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="field" style={{ marginTop: 12 }}>
          <label>附加指令（可选）</label>
          <input
            className="input"
            placeholder="如：把「端口巡检」相关条目合并到一节"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
          />
        </div>

        <div className="daily-actions">
          <button className="btn btn-primary" onClick={() => void createRun()} disabled={busy}>
            {busy && <span className="spinner" />}
            生成计划
          </button>
        </div>

        {history.length > 0 && (
          <>
            <div className="section-title">该 Agent 的批次历史</div>
            <div className="table-wrap">
              <table className="daily-table">
                <thead>
                  <tr>
                    <th style={{ width: 190 }}>范围</th>
                    <th style={{ width: 90 }}>状态</th>
                    <th style={{ width: 60 }}>天数</th>
                    <th style={{ width: 90 }}>tokens</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((r) => (
                    <tr key={r.id} className="daily-history-row" onClick={() => void openRun(r.id)}>
                      <td className="mono" style={{ fontSize: 12 }}>
                        {r.date_from} ~ {r.date_to}
                      </td>
                      <td>
                        <span className={`daily-status ${r.status}`}>{RUN_STATUS_LABEL[r.status]}</span>
                      </td>
                      <td>{r.days_total}</td>
                      <td>{r.tokens_used}</td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {new Date(r.created_at * 1000).toLocaleString('zh-CN', { hour12: false })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {editPresetId && (
          <DailyPresetEditor
            presetId={editPresetId}
            onClose={() => setEditPresetId(null)}
            onSaved={(saved) => {
              toast(`预设已保存为 v${saved.version}；重新生成批次即生效`, 'success');
              void reloadPresets();
            }}
          />
        )}
      </div>
    );
  }

  // ================= 验收报告 =================
  if (stage === 'report') {
    return (
      <div className="daily-std">
        <div className="daily-toolbar">
          <button className="btn btn-sm" onClick={() => setStage('plan')} disabled={busy}>
            返回计划
          </button>
          <button className="btn btn-sm" onClick={() => setStage('setup')} disabled={busy}>
            新建批次
          </button>
          <button className="btn btn-sm" onClick={() => void loadReport()} disabled={busy}>
            {busy && <span className="spinner" />}
            重新核对
          </button>
        </div>

        {!report ? (
          <div className="state-block">
            <div className="spinner-lg" />
            <div>正在核对磁盘上的真实文件…</div>
          </div>
        ) : (
          <>
            <div className={`alert-banner ${report.passed ? 'info' : 'danger'}`}>
              {report.passed ? '验收通过：' : '验收未通过：'}已交付 {report.days_delivered} /{' '}
              {report.days_total} 天
              {report.items.filter((i) => i.empty).length > 0 &&
                `（其中 ${report.items.filter((i) => i.empty).length} 天判定无可归档内容，未产出文件、只清碎片）`}
              ，共 {report.tokens_used} tokens
              {report.cost_estimate_usd > 0 && `（约 $${report.cost_estimate_usd.toFixed(4)}）`}。
              {!report.passed && ' 下方列出未达成的核对项，可手工处理后「重新核对」。'}
            </div>

            <div className="table-wrap">
              <table className="daily-table">
                <thead>
                  <tr>
                    <th style={{ width: 110 }}>日期</th>
                    <th style={{ width: 110 }}>状态</th>
                    <th style={{ width: 70 }}>单文件</th>
                    <th style={{ width: 70 }}>命名</th>
                    <th style={{ width: 70 }}>章节</th>
                    <th style={{ width: 90 }}>无残留壳</th>
                    <th style={{ width: 90 }}>碎片已清</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.map((it) => (
                    <tr key={it.date}>
                      <td className="mono" style={{ fontSize: 12 }}>
                        {it.date}
                      </td>
                      <td>
                        <span className={`daily-status ${it.status}`}>
                          {ITEM_STATUS_LABEL[it.status] ?? it.status}
                        </span>
                      </td>
                      <td>{it.delivered ? <Check ok={it.single_file} /> : '—'}</td>
                      <td>{it.delivered ? <Check ok={it.naming_ok} /> : '—'}</td>
                      <td>{it.delivered ? <Check ok={it.sections_ok} /> : '—'}</td>
                      <td>{it.delivered ? <Check ok={it.no_residue} /> : '—'}</td>
                      {/* 空日不产出日文件，只核对碎片是否已清 */}
                      <td>
                        {it.delivered || it.empty ? <Check ok={it.fragments_gone} /> : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {it.details.length > 0 ? it.details.join('；') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    );
  }

  // ================= 计划（逐日确认） =================
  const items = run?.items ?? [];
  return (
    <div className="daily-std">
      <div className="daily-toolbar">
        <button className="btn btn-sm" onClick={() => setStage('setup')} disabled={busy}>
          返回参数
        </button>
        <button className="btn btn-sm" onClick={() => void loadRun(runId ?? '')} disabled={busy || !runId}>
          刷新
        </button>
        {hasDelivered && (
          <button className="btn btn-sm" onClick={() => void loadReport()} disabled={busy}>
            验收报告
          </button>
        )}
        <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>
          {run && `批次 ${run.id} · ${RUN_STATUS_LABEL[run.status]} · ${run.tokens_used} tokens`}
          {run?.token_budget ? ` / 预算 ${run.token_budget}` : ''}
          {/* 批次创建时绑定的预设版本（改预设不会重算已生成的计划，故在此如实标注） */}
          {run ? ` · 预设 v${run.preset_version}` : ''}
        </span>
      </div>

      {!run ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>加载批次中…</div>
        </div>
      ) : generating ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>
            正在逐日生成计划（{items.filter((i) => i.status !== 'pending').length} / {items.length}）…
            单日失败不会中断整批
          </div>
        </div>
      ) : (
        <>
          {run.error && run.status !== 'empty' && <div className="alert-banner danger">{run.error}</div>}
          {run.status === 'empty' ? (
            <div className="alert-banner info">
              {items.some((i) => i.status === 'empty')
                ? `本批 ${items.length} 天的来源经判定均无可归档内容（逐日理由见下方卡片），没有需要写入的日文件。`
                : '该范围内没有需要整理的日子。'}
            </div>
          ) : applicable.length === 0 ? (
            <div className="alert-banner danger">
              本批没有可执行的日子（逐日结果见下方卡片与失败原因）。
            </div>
          ) : (
            <div className="alert-banner warning">
              计划已生成（{items.length} 天，可执行 {applicable.length} 天）。请逐日查看差异后再勾选
              ——<b>默认全部不勾选</b>。写入前会自动备份日文件；碎片移入系统回收站，可恢复。
            </div>
          )}

          {items.map((item) => {
            const selectable = isApplicable(item) && canAct;
            return (
              <div key={item.date} className={`daily-day${checked.has(item.date) ? ' selected' : ''}`}>
                <label className="checkbox-row daily-day-head">
                  <input
                    type="checkbox"
                    checked={checked.has(item.date)}
                    disabled={!selectable}
                    onChange={() => toggleChecked(item.date)}
                  />
                  <span className="mono" style={{ fontWeight: 700 }}>
                    {item.date}
                  </span>
                  <span className="muted mono" style={{ fontSize: 11 }}>
                    {item.status === 'empty' ? (
                      '（本日不产出日文件）'
                    ) : (
                      <>
                        → {item.target_path}
                        {item.has_standard ? '（已有主文件，将就地归并）' : '（将新建）'}
                      </>
                    )}
                  </span>
                  <span className={`daily-status ${item.status}`}>
                    {ITEM_STATUS_LABEL[item.status] ?? item.status}
                  </span>
                </label>

                <div className="daily-day-body">
                  {item.error && <div className="alert-banner danger">{item.error}</div>}

                  {item.status === 'empty' && (
                    <div className="alert-banner info">
                      <b>本日无可归档内容</b>：{item.empty_reason?.trim() || '（模型未给理由）'}
                      <div className="hint" style={{ marginTop: 4 }}>
                        不产出 <span className="mono">{item.target_path}</span>；
                        {item.fragments_to_delete.length > 0
                          ? '只清理下面的 B/C 碎片'
                          : '本日也没有需要清理的碎片'}
                        ；若当天已有主文件 <span className="mono">YYYY-MM-DD.md</span> 则保持不动。
                      </div>
                    </div>
                  )}

                  <div className="daily-sources">
                    {item.sources.map((s) => (
                      <div key={s.path} className="daily-source">
                        <span className={`daily-kind kind-${s.kind.toLowerCase()}`}>
                          {s.kind} · {KIND_LABEL[s.kind] ?? s.kind}
                        </span>
                        <span className="mono" style={{ fontSize: 12, minWidth: 0 }} title={s.path}>
                          {s.path}
                        </span>
                        <span className="muted" style={{ fontSize: 11 }}>
                          {formatBytes(s.raw_bytes)}
                          {s.clean_bytes !== s.raw_bytes && ` → ${formatBytes(s.clean_bytes)}`}
                          {s.removed_total > 0 && `（剥壳 ${s.removed_total} 行）`}
                          {s.summarized && `（分块摘要 ${s.chunks} 段）`}
                        </span>
                      </div>
                    ))}
                  </div>

                  {item.fragments_to_delete.length > 0 && (
                    <div className="daily-fragments">
                      {item.status === 'empty' ? '拟清理' : '归并后拟删除'}{' '}
                      {item.fragments_to_delete.length} 个碎片（移入回收站）：
                      <span className="mono" style={{ fontSize: 12 }}>
                        {item.fragments_to_delete.join('、')}
                      </span>
                    </div>
                  )}

                  {item.format_report.violations.length > 0 && (
                    <div className="alert-banner danger" style={{ marginTop: 8 }}>
                      <b>强规则未通过（{item.format_report.violations.length} 项，该日不会被写入）</b>
                      <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                        {item.format_report.violations.slice(0, 6).map((v, i) => (
                          <li key={i}>
                            <span className="mono">{v.rule_id}</span> {v.rule_name}
                            {v.line != null ? `（第 ${v.line} 行）` : ''} — {v.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {item.notes.length > 0 && (
                    <div className="hint" style={{ marginTop: 8 }}>
                      {item.notes.join('；')}
                    </div>
                  )}

                  {/* 空日没有归并结果，不展示 diff（否则会误显示「与当前文件一致」） */}
                  {item.status !== 'empty' && (
                    <>
                      {item.unified_diff && (
                        <div style={{ marginTop: 8 }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => toggleRaw(item.date)}>
                            {rawDiff.has(item.date) ? '收起原始差异' : '查看原始差异'}
                          </button>
                        </div>
                      )}
                      {rawDiff.has(item.date) ? (
                        <pre className="diff-view" style={{ maxHeight: 320 }}>
                          {item.unified_diff || '（无差异）'}
                        </pre>
                      ) : (
                        <div style={{ marginTop: 6 }}>
                          <DiffView
                            htmlDiff={item.html_diff ?? ''}
                            identical={!item.unified_diff}
                            identicalText="归并结果与当前文件一致"
                          />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })}

          <div className="daily-actions">
            <button
              className="btn btn-primary"
              disabled={!canAct || checked.size === 0 || busy}
              onClick={() => {
                setApplyAll(false);
                setConfirmApply(true);
              }}
              title={checked.size === 0 ? '请先勾选要执行的日期' : `执行已勾选的 ${checked.size} 天`}
            >
              {busy && <span className="spinner" />}
              执行选中 {checked.size} 天
            </button>
            <button
              className="btn"
              disabled={!canAct || applicable.length === 0 || busy}
              onClick={() => {
                setApplyAll(true);
                setConfirmApply(true);
              }}
              title={`执行全部 ${applicable.length} 天`}
            >
              全部执行
            </button>
            <button
              className="btn"
              disabled={!canAct || checked.size === 0 || busy}
              onClick={() => void doSkip()}
              title="跳过已勾选的日期（不改写这些天）"
            >
              跳过选中
            </button>
            <button
              className="btn btn-danger"
              disabled={!run || busy || TERMINAL_RUNS.includes(run.status)}
              onClick={() => setConfirmReject(true)}
            >
              拒绝整批
            </button>
          </div>
        </>
      )}

      {confirmApply && run && (
        <ConfirmDialog
          title="确认执行选中日期"
          danger
          busy={busy}
          confirmText="确认执行"
          cancelText="取消"
          onConfirm={() => void doApply(applyAll)}
          onCancel={() => setConfirmApply(false)}
          message={
            <>
              <p>
                将对 Agent <b>{run.agent_id}</b> 的以下日期执行
                {applyAll ? '（全部可执行的日子）' : ''}：
              </p>
              <ul style={{ paddingLeft: 20 }}>
                {(applyAll ? applicable : applicable.filter((i) => checked.has(i.date))).map((i) => (
                  <li key={i.date}>
                    <span className="mono">{i.date}</span>
                    <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                      {willWrite(i)
                        ? `写入 ${i.target_path}，并清理 ${i.fragments_to_delete.length} 个碎片`
                        : `判定无可归档内容 → 不写日文件，只清理 ${i.fragments_to_delete.length} 个碎片`}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="hint">
                写入前自动备份原文件；碎片移入系统回收站（可恢复）；
                「无可归档内容」的日子不产出日文件，已有的主文件 <span className="mono">YYYY-MM-DD.md</span> 保持不动。
                若期间有任何一天的文件被外部改动，整批都不会写入。
              </p>
            </>
          }
        />
      )}

      {confirmReject && (
        <ConfirmDialog
          title="拒绝该批次"
          danger
          busy={busy}
          confirmText="确认拒绝"
          cancelText="取消"
          onConfirm={() => void doReject()}
          onCancel={() => setConfirmReject(false)}
          message={
            <p>
              拒绝后该批次作废，<b>不会写入或删除任何文件</b>。
            </p>
          }
        />
      )}
    </div>
  );
}

function Check({ ok }: { ok: boolean }) {
  return (
    <span className={ok ? 'daily-check ok' : 'daily-check bad'} title={ok ? '通过' : '未通过'}>
      {ok ? '✓' : '✗'}
    </span>
  );
}
