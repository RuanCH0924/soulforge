import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { ApiError } from '../api/client';
import { useToast } from '../hooks/useToast';
import type {
  AgentInfo,
  LLMProvider,
  PresetSummary,
  SummaryRun,
  SummaryRunCreateResult,
  SummaryRunReport,
  SummaryRunStatus,
  SummaryRunSummary,
} from '../types';
import { formatBytes } from '../utils/format';
import { ConfirmDialog } from './ConfirmDialog';
import { DailyPresetEditor } from './DailyPresetEditor';
import { DiffView } from './DiffView';

interface SummaryPanelProps {
  agents: AgentInfo[];
}

type Stage = 'setup' | 'plan' | 'report';

/** 默认预设：与后端 `SummaryRunCreate.preset_id` 的默认值保持一致 */
const DEFAULT_PRESET_ID = 'preset-mem-summarize';

const RUN_STATUS_LABEL: Record<SummaryRunStatus, string> = {
  planned: '生成中',
  awaiting_confirm: '待确认',
  applied: '已写入',
  needs_review: '需复核',
  rejected: '已拒绝',
  failed: '失败',
  empty: '无可归纳的来源',
};

const KIND_LABEL: Record<string, string> = { A: '主文件', B: '会话导出', C: '主题碎片' };

/** 已写入/已作废的批次：此时不再允许拒绝（与后端 SummaryService.reject 一致） */
const TERMINAL_RUNS: SummaryRunStatus[] = ['applied', 'needs_review', 'rejected'];

function isoOf(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 该范围是否恰好是一整个自然月（决定产物命名；与后端 `_is_full_month` 同一口径） */
function isFullMonth(from: string, to: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return false;
  const [y, m] = from.split('-');
  if (to.slice(0, 7) !== `${y}-${m}` || from.slice(8) !== '01') return false;
  const last = new Date(Number(y), Number(m), 0).getDate();
  return to === `${y}-${m}-${String(last).padStart(2, '0')}`;
}

function outputPathFor(from: string, to: string): string {
  return isFullMonth(from, to)
    ? `memory/${from.slice(0, 7)}-记忆归纳.md`
    : `memory/${from}_${to}-记忆归纳.md`;
}

/**
 * 工作日志总结面板（M16 · 业务工具页内嵌）。
 *
 * 三阶段：参数 → 归纳计划（含完整 diff）→ 验收报告。
 * 计划阶段只读不落盘；确认写入后产物落到 `memory/<范围>-记忆归纳.md`。
 * 源文件默认**不动**（只读归纳）；「清理源文件」是写入确认后单独触发的可选动作。
 */
export function SummaryPanel({ agents }: SummaryPanelProps) {
  const { push: toast } = useToast();
  const [stage, setStage] = useState<Stage>('setup');

  // ---- 参数 ----
  const [agentId, setAgentId] = useState(agents[0]?.id ?? '');
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return isoOf(d);
  });
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date();
    return isoOf(new Date(d.getFullYear(), d.getMonth() + 1, 0));
  });
  const [presetId, setPresetId] = useState(DEFAULT_PRESET_ID);
  const [providerId, setProviderId] = useState('');
  const [extra, setExtra] = useState('');
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);

  // ---- 批次 ----
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<SummaryRun | null>(null);
  const [report, setReport] = useState<SummaryRunReport | null>(null);
  const [history, setHistory] = useState<SummaryRunSummary[]>([]);
  const [rawDiff, setRawDiff] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  /** 正在页内编辑的归纳预设 id（null = 未打开编辑器） */
  const [editPresetId, setEditPresetId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listPresets('SUMMARY'), api.listLLMProviders()])
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

  const loadHistory = useCallback(async (id: string) => {
    if (!id) {
      setHistory([]);
      return;
    }
    try {
      setHistory(await api.listSummaryRuns({ agent_id: id, limit: 20 }));
    } catch {
      setHistory([]); // 历史列表是辅助信息，失败不打扰用户
    }
  }, []);

  useEffect(() => {
    void loadHistory(agentId);
  }, [agentId, loadHistory]);

  const loadRun = useCallback(
    async (id: string) => {
      try {
        const r = await api.getSummaryRun(id);
        setRun(r);
        return r;
      } catch (e) {
        toast(`加载批次失败：${(e as Error).message}`, 'error');
        return null;
      }
    },
    [toast],
  );

  // 生成阶段轮询（后台跑 LLM，planned → awaiting_confirm / failed / empty）
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
      setRawDiff(false);
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
      const r: SummaryRunCreateResult = await api.createSummaryRun({
        agent_id: agentId,
        date_from: dateFrom,
        date_to: dateTo,
        preset_id: presetId,
        provider_id: providerId,
        extra_instructions: extra.trim() || undefined,
      });
      setReport(null);
      setRawDiff(false);
      setRunId(r.run_id);
      setStage('plan');
      await loadRun(r.run_id);
      void loadHistory(agentId);
      if (r.reused) toast('与既有批次内容一致，已复用其结果（未重复调用 LLM）', 'info');
      else if (r.status === 'empty') toast('该范围内没有可归纳的记录', 'info');
      else toast(`已提交，正在归纳（共 ${r.source_count} 个来源）`, 'info');
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
      setReport(await api.summaryRunReport(runId));
      setStage('report');
    } catch (e) {
      toast(`加载验收报告失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [runId, toast]);

  const doApply = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      const r = await api.applySummaryRun(runId);
      if (r.status === 'needs_review') toast(`未通过写前验收，未写入任何文件：${r.error ?? ''}`, 'error');
      else toast(`已写入 ${r.output_path}（源文件保持不动）`, 'success');
      setRun(r);
      void loadHistory(agentId);
      await loadReport();
    } catch (e) {
      const err = e as ApiError;
      if (err.code === 'CONFLICT') toast(`未写入任何文件：${err.message}`, 'error');
      else toast(`写入失败：${err.message}`, 'error');
      await loadRun(runId);
    } finally {
      setBusy(false);
      setConfirmApply(false);
    }
  }, [runId, loadRun, loadReport, loadHistory, agentId, toast]);

  const doReject = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      setRun(await api.rejectSummaryRun(runId));
      toast('已拒绝该批次（未写入任何文件）', 'info');
      void loadHistory(agentId);
    } catch (e) {
      toast(`拒绝失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
      setConfirmReject(false);
    }
  }, [runId, loadHistory, agentId, toast]);

  const doCleanup = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      const res = await api.cleanupSummarySources(runId);
      const parts = [
        res.deleted.length > 0 ? `${res.deleted.length} 个源文件已移入回收站` : '',
        res.failed.length > 0 ? `${res.failed.length} 个失败` : '',
      ].filter(Boolean);
      toast(parts.length > 0 ? parts.join('、') : '没有需要清理的源文件', res.failed.length ? 'warning' : 'success');
      await loadRun(runId);
      if (stage === 'report') await loadReport();
    } catch (e) {
      toast(`清理失败：${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
      setConfirmCleanup(false);
    }
  }, [runId, stage, loadRun, loadReport, toast]);

  const generating = run?.status === 'planned';
  const canAct = run?.status === 'awaiting_confirm' && !generating;
  const canCleanup = Boolean(run?.applied_at) && !run?.cleanup_at;

  /** 当前生效的归纳预设（下拉选中的那个）：信息栏与页内编辑器都用它 */
  const currentPreset = presets.find((p) => p.id === presetId);

  const reloadPresets = useCallback(async () => {
    try {
      const ps = await api.listPresets('SUMMARY');
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
        <div className="alert-banner warning intro">
          <div className="alert-title">按「时间段」归纳 · 每次产出一份综述</div>
          <ul className="alert-points">
            <li>
              把该范围内的每日记录（主文件 / 会话导出 / 主题碎片）归纳为<b>一份</b>综述
              <span className="mono ml-6">memory/&lt;范围&gt;-记忆归纳.md</span>
              ：完成的工作 / 经验教训 / 重要决定 / 重要信息 / 待办事项（可选附录溯源表）。
            </li>
            <li>
              先生成计划，<b>看完差异再确认写入</b>；确认前不写盘、<b>不动任何源文件</b>。
            </li>
            <li>
              范围为整月时产物自动命名为
              <span className="mono">YYYY-MM-记忆归纳.md</span>；汇总写入后可另选
              <b>「清理源文件」</b>把对应日文件移入回收站（默认不清理）。
            </li>
          </ul>
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

        {dateFrom && dateTo && dateFrom <= dateTo && (
          <div className="hint">
            产物路径：<span className="mono">{outputPathFor(dateFrom, dateTo)}</span>
            {isFullMonth(dateFrom, dateTo) && '（整月，按 YYYY-MM 命名）'}
          </div>
        )}

        <div className="section-title">记忆归纳预设</div>
        {/* 预设信息栏：说清「当前生效的是哪个预设、它从哪来、专供谁用」——
            这类预设按边界不在设置页文档预设与主工作台「应用预设」里出现。 */}
        {currentPreset && (
          <div className="daily-preset-info">
            <div className="daily-preset-info-head">
              <span className="daily-only-badge">大模型专用</span>
              <span className="daily-preset-info-name">
                {currentPreset.name}
                <span className="muted text-xs ml-6">
                  v{currentPreset.version}
                </span>
              </span>
              <span className="muted text-sm">
                来源：{currentPreset.is_builtin ? '内置预设（随版本分发）' : '用户自建'}
              </span>
              <button
                className="btn btn-sm ml-auto"
                onClick={() => setEditPresetId(currentPreset.id)}
              >
                查看 / 编辑
              </button>
            </div>
            <div className="daily-preset-info-hint">
              该预设<b>专供大模型做记忆归纳</b>（把一段时间的记录归纳成单份综述），不用于主工作台的文件整理；
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
            没有 SUMMARY 类型的预设。
          </div>
        ) : (
          <div className="daily-preset-list">
            {presets.map((p) => (
              <label key={p.id} className={`daily-preset${presetId === p.id ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="summary-preset"
                  checked={presetId === p.id}
                  onChange={() => setPresetId(p.id)}
                />
                <span className="min-w-0">
                  <span className="daily-preset-name">
                    {p.name}
                    <span className="muted text-xs ml-6">
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
                  name="summary-provider"
                  checked={providerId === p.id}
                  onChange={() => setProviderId(p.id)}
                />
                <span className="min-w-0">
                  {p.id}
                  <span className="muted text-xs ml-6">
                    {p.model}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="field mt-12">
          <label>附加指令（可选）</label>
          <input
            className="input"
            placeholder="如：按项目分类归纳「完成的工作」；重点提炼与交换机相关的教训"
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
                    <th style={{ width: 110 }}>状态</th>
                    <th style={{ width: 70 }}>来源</th>
                    <th style={{ width: 90 }}>tokens</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((r) => (
                    <tr key={r.id} className="daily-history-row" onClick={() => void openRun(r.id)}>
                      <td className="mono text-sm">
                        {r.date_from} ~ {r.date_to}
                      </td>
                      <td>
                        <span className={`daily-status ${r.status}`}>{RUN_STATUS_LABEL[r.status]}</span>
                      </td>
                      <td>{r.source_count}</td>
                      <td>{r.tokens_used}</td>
                      <td className="muted text-sm">
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
            titlePrefix="编辑记忆归纳预设"
            notice={
              <>
                <div className="alert-title">本预设专供大模型做记忆归纳</div>
                <ul className="alert-points">
                  <li>
                    不出现在主工作台与「文档预设」页，只在日志总结界面查看与编辑。
                  </li>
                  <li>
                    保存后 <b>version +1</b> 并写入版本历史，可随时回溯。
                  </li>
                  <li>
                    <b>重新生成批次即生效</b>；已生成的计划不会重算。
                  </li>
                </ul>
              </>
            }
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
              {report.passed ? '验收通过：' : '验收未通过：'}
              {report.delivered ? `已写入 ${report.output_path}` : '汇总文件尚未写入'}，共{' '}
              {report.tokens_used} tokens
              {report.cost_estimate_usd > 0 && `（约 $${report.cost_estimate_usd.toFixed(4)}）`}。
              {!report.passed && ' 下方列出未达成的核对项，可手工处理后「重新核对」。'}
            </div>

            <div className="table-wrap">
              <table className="daily-table">
                <thead>
                  <tr>
                    <th style={{ width: 170 }}>核对项</th>
                    <th style={{ width: 70 }}>结果</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ['已写入汇总文件', report.delivered, '产物是否按范围写入 memory/'],
                      ['命名合规', report.naming_ok, '整月 → YYYY-MM；否则 起_止'],
                      ['章节齐全', report.sections_ok, '五大主章节存在且顺序正确'],
                      ['无残留壳', report.no_residue, '低价值元数据壳残留 = 0'],
                      ['源文件自洽', report.sources_ok, '未清理时都在 / 已清理时都不在'],
                    ] as [string, boolean, string][]
                  ).map(([label, ok, hint]) => (
                    <tr key={label}>
                      <td>{label}</td>
                      <td>
                        <Check ok={ok} />
                      </td>
                      <td className="muted text-sm">
                        {hint}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {report.details.length > 0 && (
              <div className="alert-banner danger mt-12">
                <b>未达成项说明</b>
                <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                  {report.details.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}

            {canCleanup && (
              <div className="daily-actions">
                <button className="btn btn-danger" onClick={() => setConfirmCleanup(true)} disabled={busy}>
                  清理源文件（{run?.sources.length ?? 0} 个）
                </button>
                <span className="hint" style={{ alignSelf: 'center' }}>
                  把该范围内的源文件移入系统回收站（可恢复）；产物自身不会被删除。
                </span>
              </div>
            )}
            {run?.cleanup_at && (
              <div className="alert-banner info mt-12">
                源文件已清理：{run.deleted_sources.length} 个已移入回收站
                {run.failed_sources.length > 0 && `，${run.failed_sources.length} 个失败：${run.failed_sources.join('；')}`}
                。产物 <span className="mono">{run.output_path}</span> 保持不动。
              </div>
            )}
          </>
        )}

        {confirmCleanup && (
          <ConfirmDialog
            title="清理源文件"
            danger
            busy={busy}
            confirmText="确认清理"
            cancelText="取消"
            onConfirm={() => void doCleanup()}
            onCancel={() => setConfirmCleanup(false)}
            message={
              <>
                <p>
                  将把该批次范围内的 <b>{run?.sources.length ?? 0} 个源文件</b>移入系统回收站：
                </p>
                <ul style={{ paddingLeft: 20, maxHeight: 220, overflow: 'auto' }}>
                  {(run?.sources ?? []).map((s) => (
                    <li key={s.path}>
                      <span className="mono text-sm">
                        {s.path}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="hint">
                  汇总产物 <span className="mono">{run?.output_path}</span> 不会被删除；
                  移入回收站的文件可手工恢复。此操作不可在界面内撤销。
                </p>
              </>
            }
          />
        )}
      </div>
    );
  }

  // ================= 计划（确认写入） =================
  return (
    <div className="daily-std">
      <div className="daily-toolbar">
        <button className="btn btn-sm" onClick={() => setStage('setup')} disabled={busy}>
          返回参数
        </button>
        <button className="btn btn-sm" onClick={() => void loadRun(runId ?? '')} disabled={busy || !runId}>
          刷新
        </button>
        {run?.applied_at && (
          <button className="btn btn-sm" onClick={() => void loadReport()} disabled={busy}>
            验收报告
          </button>
        )}
        <span className="muted text-sm ml-auto">
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
          <div>正在归纳（共 {run.source_count} 个来源）… 大范围归纳耗时较长，请稍候</div>
        </div>
      ) : (
        <>
          {run.error && run.status !== 'empty' && <div className="alert-banner danger">{run.error}</div>}
          {run.status === 'empty' ? (
            <div className="alert-banner info">
              {run.error || '该范围内没有可归纳的记录（memory/ 顶层没有符合日文件名模式的 .md）。'}
            </div>
          ) : run.status === 'awaiting_confirm' ? (
            <div className="alert-banner warning">
              计划已生成（{run.source_count} 个来源）。产物：
              <span className="mono" style={{ margin: '0 4px' }}>{run.output_path}</span>
              请看完下方差异后再确认写入——<b>确认前不写盘、不动任何源文件</b>。
              写入前会自动备份同名产物；源文件默认保留。
            </div>
          ) : null}

          <div className="daily-day">
            <div className="daily-day-head" style={{ padding: '10px 12px' }}>
              <span className="mono" style={{ fontWeight: 700 }}>
                {run.date_from} ~ {run.date_to}
              </span>
              <span className="muted mono text-xs">
                → {run.output_path}
              </span>
              <span className={`daily-status ${run.status}`}>{RUN_STATUS_LABEL[run.status]}</span>
            </div>

            <div className="daily-day-body">
              <div className="daily-sources">
                {run.sources.map((s) => (
                  <div key={s.path} className="daily-source">
                    <span className={`daily-kind kind-${s.kind.toLowerCase()}`}>
                      {s.kind} · {KIND_LABEL[s.kind] ?? s.kind}
                    </span>
                    <span className="mono text-sm min-w-0" title={s.path}>
                      {s.path}
                    </span>
                    <span className="muted text-xs">
                      {s.date} · {formatBytes(s.raw_bytes)}
                      {s.clean_bytes !== s.raw_bytes && ` → ${formatBytes(s.clean_bytes)}`}
                      {s.removed_total > 0 && `（剥壳 ${s.removed_total} 行）`}
                      {s.summarized && `（分块摘要 ${s.chunks} 段）`}
                    </span>
                  </div>
                ))}
              </div>

              {run.format_report.violations.length > 0 && (
                <div className="alert-banner danger mt-8">
                  <b>强规则未通过（{run.format_report.violations.length} 项，不会被写入）</b>
                  <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                    {run.format_report.violations.slice(0, 6).map((v, i) => (
                      <li key={i}>
                        <span className="mono">{v.rule_id}</span> {v.rule_name}
                        {v.line != null ? `（第 ${v.line} 行）` : ''} — {v.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {run.notes.length > 0 && (
                <div className="hint mt-8">
                  {run.notes.join('；')}
                </div>
              )}

              {run.status !== 'empty' && (
                <>
                  {run.unified_diff && (
                    <div className="mt-8">
                      <button className="btn btn-ghost btn-sm" onClick={() => setRawDiff((v) => !v)}>
                        {rawDiff ? '收起原始差异' : '查看原始差异'}
                      </button>
                    </div>
                  )}
                  {rawDiff ? (
                    <pre className="diff-view" style={{ maxHeight: 360 }}>
                      {run.unified_diff || '（无差异）'}
                    </pre>
                  ) : (
                    <div className="mt-6">
                      <DiffView
                        htmlDiff={run.html_diff ?? ''}
                        identical={!run.unified_diff}
                        identicalText="归纳结果与现有产物一致"
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="daily-actions">
            <button
              className="btn btn-primary"
              disabled={!canAct || busy}
              onClick={() => setConfirmApply(true)}
              title={canAct ? '确认写入汇总文件' : '仅待确认状态可写入'}
            >
              {busy && <span className="spinner" />}
              确认写入
            </button>
            {canCleanup && (
              <button className="btn btn-danger" onClick={() => setConfirmCleanup(true)} disabled={busy}>
                清理源文件
              </button>
            )}
            <button
              className="btn"
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
          title="确认写入汇总文件"
          danger
          busy={busy}
          confirmText="确认写入"
          cancelText="取消"
          onConfirm={() => void doApply()}
          onCancel={() => setConfirmApply(false)}
          message={
            <>
              <p>
                将为 Agent <b>{run.agent_id}</b> 写入归纳产物：
              </p>
              <ul style={{ paddingLeft: 20 }}>
                <li>
                  <span className="mono">{run.output_path}</span>
                  <span className="muted ml-8 text-sm">
                    （来源 {run.source_count} 个）
                  </span>
                </li>
              </ul>
              <p className="hint">
                写入前自动备份同名产物；<b>源文件保持不动</b>（如需清理，写入后在验收报告页单独执行）。
                若目标文件期间被外部改动，本次不会写入任何文件。
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

      {confirmCleanup && (
        <ConfirmDialog
          title="清理源文件"
          danger
          busy={busy}
          confirmText="确认清理"
          cancelText="取消"
          onConfirm={() => void doCleanup()}
          onCancel={() => setConfirmCleanup(false)}
          message={
            <>
              <p>
                将把该批次范围内的 <b>{run?.sources.length ?? 0} 个源文件</b>移入系统回收站：
              </p>
              <ul style={{ paddingLeft: 20, maxHeight: 220, overflow: 'auto' }}>
                {(run?.sources ?? []).map((s) => (
                  <li key={s.path}>
                    <span className="mono text-sm">
                      {s.path}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="hint">
                汇总产物 <span className="mono">{run?.output_path}</span> 不会被删除；移入回收站的文件可手工恢复。
              </p>
            </>
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
