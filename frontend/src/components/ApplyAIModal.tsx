import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type { AIJob, LLMProvider, PresetSummary } from '../types';
import { renderMarkdown } from '../utils/markdown';
import { applyHunks, canRebuild, parseUnifiedDiff } from '../utils/unifiedDiff';
import type { DiffHunk } from '../utils/unifiedDiff';
import { ConfirmDialog } from './ConfirmDialog';
import { DiffHunkPicker } from './DiffHunkPicker';
import { Modal } from './Modal';

interface ApplyAIModalProps {
  agentId: string;
  filePath: string;
  onClose: () => void;
  onDone: () => void;
}

const TERMINAL = new Set(['awaiting_confirm', 'failed', 'applied', 'rejected', 'superseded']);

/** 「AI 整理」向导：选预设 + provider + 附加指令 → 生成 → 轮询 → diff 预览 → 应用/拒绝/重新生成 */
export function ApplyAIModal({ agentId, filePath, onClose, onDone }: ApplyAIModalProps) {
  const { push: toast } = useToast();
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [presetId, setPresetId] = useState('');
  const [providerId, setProviderId] = useState('');
  const [extra, setExtra] = useState('');
  const [job, setJob] = useState<AIJob | null>(null);
  const [generating, setGenerating] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [acting, setActing] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [regenerateExtra, setRegenerateExtra] = useState('');
  // 「按块接受」：从 unified_diff 解析出的 hunk 与逐块勾选状态（默认全接受）
  const [hunks, setHunks] = useState<DiffHunk[]>([]);
  const [accepted, setAccepted] = useState<boolean[]>([]);
  const allAccepted = hunks.length === 0 || accepted.every(Boolean);
  // 解析可靠（全部接受能精确重建 AI 输出）时才允许「按块接受」，否则退回整段 diff + 整体应用
  const hunksReliable =
    job?.status === 'awaiting_confirm' &&
    canRebuild(job.input_snapshot ?? '', hunks, job.output_content ?? '');
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    // scope=workbench：排除「专供大模型处理工作日志」的预设（那类只在日志标准化界面用）
    Promise.all([api.listPresets(undefined, 'workbench'), api.listLLMProviders()])
      .then(([ps, lps]) => {
        setPresets(ps);
        const enabled = lps.filter((p) => p.enabled);
        setProviders(enabled);
        if (ps.length > 0) setPresetId(ps[0].id);
        if (enabled.length > 0) setProviderId(enabled[0].id);
      })
      .catch((e) => toast(`加载失败：${(e as Error).message}`, 'error'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 轮询任务状态
  const poll = useCallback(
    (jobId: string) => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = window.setInterval(async () => {
        try {
          const j = await api.getAIJob(jobId);
          setJob(j);
          if (TERMINAL.has(j.status)) {
            if (timerRef.current) window.clearInterval(timerRef.current);
            if (j.status === 'awaiting_confirm') {
              toast('AI 整理完成，请查看差异后确认', 'success');
            } else if (j.status === 'failed') {
              toast(`AI 整理失败：${j.error ?? '未知错误'}`, 'error');
            }
          }
        } catch (e) {
          if (timerRef.current) window.clearInterval(timerRef.current);
          toast(`查询任务失败：${(e as Error).message}`, 'error');
        }
      }, 1000);
    },
    [toast],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  // 「按块接受」：任务进入待确认态后把差异解析为 hunk（默认全接受）。
  // 只在任务切换 / 状态变化时重解析，避免重置用户的勾选。
  useEffect(() => {
    const diff = job?.status === 'awaiting_confirm' ? job.diff_plan_json?.unified_diff ?? '' : '';
    const parsed = parseUnifiedDiff(diff);
    setHunks(parsed.hunks);
    setAccepted(parsed.hunks.map(() => true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status]);

  const generate = async () => {
    if (!presetId || !providerId) {
      toast('请先选择预设和 Provider', 'warning');
      return;
    }
    setGenerating(true);
    try {
      const r = await api.createAIJob({
        agent_id: agentId,
        file_path: filePath,
        preset_id: presetId,
        provider_id: providerId,
        extra_instructions: extra.trim() || undefined,
      });
      setJob({ id: r.job_id, status: r.status } as AIJob);
      poll(r.job_id);
      toast('已提交 AI 整理任务，后台执行中…', 'info');
    } catch (e) {
      toast(`创建任务失败：${(e as Error).message}`, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const apply = async () => {
    if (!job) return;
    setActing(true);
    try {
      if (allAccepted) {
        await api.applyAIJob(job.id);
        toast('已应用 AI 整理结果（已自动备份原文件）', 'success');
      } else {
        // 按块接受：按选中 hunk 重建内容后交后端；后端仍跑同一套格式 + lint 闸门
        const content = applyHunks(job.input_snapshot ?? '', hunks, accepted);
        await api.applyAIJob(job.id, content);
        toast(`已写入选中的 ${accepted.filter(Boolean).length} 块改动（已自动备份原文件）`, 'success');
      }
      setConfirming(false);
      onDone();
      onClose();
    } catch (e) {
      toast(`应用失败：${(e as Error).message}`, 'error');
      setConfirming(false);
      setJob((prev) => (prev ? { ...prev, status: 'failed' } : prev)); // lint 拦截等 → 刷新为失败态
    } finally {
      setActing(false);
    }
  };

  const reject = async () => {
    if (!job) return;
    setActing(true);
    try {
      await api.rejectAIJob(job.id);
      toast('已拒绝本次 AI 整理结果', 'info');
      onClose();
    } catch (e) {
      toast(`拒绝失败：${(e as Error).message}`, 'error');
    } finally {
      setActing(false);
    }
  };

  const regenerate = async () => {
    if (!job) return;
    setActing(true);
    try {
      const r = await api.regenerateAIJob(job.id, regenerateExtra.trim());
      setJob({ id: r.job_id, status: r.status } as AIJob);
      setRegenerateExtra('');
      poll(r.job_id);
      toast('已提交重新生成任务', 'info');
    } catch (e) {
      toast(`重新生成失败：${(e as Error).message}`, 'error');
    } finally {
      setActing(false);
    }
  };

  const busy = job && (job.status === 'pending' || job.status === 'running');
  const selectedPreset = presets.find((p) => p.id === presetId);

  return (
    <Modal
      title={`AI 整理 — ${filePath}`}
      onClose={onClose}
      width={880}
      footer={
        !job ? (
          <button className="btn btn-primary" onClick={generate} disabled={generating || loading}>
            {generating && <span className="spinner" />}
            生成
          </button>
        ) : job.status === 'awaiting_confirm' ? (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={reject} disabled={acting}>
              拒绝
            </button>
            <button className="btn" onClick={regenerate} disabled={acting || !regenerateExtra.trim()}>
              重新生成
            </button>
            <button className="btn btn-primary" onClick={() => setConfirming(true)} disabled={acting}>
              {acting && <span className="spinner" />}
              应用
            </button>
          </div>
        ) : (
          <button className="btn btn-ghost" onClick={onClose}>
            关闭
          </button>
        )
      }
    >
      {!job ? (
        <>
          <div className="alert-banner warning">
            AI 会按预设结构重写文档并生成差异预览，<b>必须经你确认后才写入</b>（写入前自动备份）。
            <br />
            大文件（&gt;30KB）会被拒绝；单文件默认单次调用，不会自动循环。
          </div>
          <div className="section-title">选择预设（{presets.length} 个）</div>
          {loading ? (
            <div className="state-block">
              <div className="spinner-lg" />
              <div>正在加载…</div>
            </div>
          ) : (
            <div className="checkbox-grid" style={{ maxHeight: 160 }}>
              {presets.map((p) => (
                <label key={p.id} className="checkbox-row">
                  <input type="radio" name="ai-preset" checked={presetId === p.id} onChange={() => setPresetId(p.id)} />
                  <span className="min-w-0">
                    {p.name}
                    <span className="muted text-xs ml-6">
                      {p.target_file_type}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}

          <div className="section-title">选择 LLM Provider</div>
          {providers.length === 0 ? (
            <div className="hint" style={{ color: 'var(--danger, #d9534f)' }}>
              尚未配置启用的 LLM Provider：请先在 设置 → LLM Provider 管理 中添加并启用。
            </div>
          ) : (
            <div className="checkbox-grid" style={{ maxHeight: 120 }}>
              {providers.map((p) => (
                <label key={p.id} className="checkbox-row">
                  <input type="radio" name="ai-provider" checked={providerId === p.id} onChange={() => setProviderId(p.id)} />
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
              placeholder="如：把关于群聊的章节合并"
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
            />
          </div>
          {selectedPreset?.description && <div className="hint">预设说明：{selectedPreset.description}</div>}
        </>
      ) : busy ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>AI 正在整理中（{job.status === 'pending' ? '排队中' : '执行中'}）… 请稍候</div>
        </div>
      ) : job.status === 'awaiting_confirm' ? (
        <>
          <div className="alert-banner warning">
            已生成（使用 {job.total_tokens ?? 0} tokens）
            {job.diff_plan_json && !job.diff_plan_json.format_report.ok && (
              <> · 存在 {job.diff_plan_json.format_report.violations.length} 处格式违规，应用会被拦截。</>
            )}
            {job.diff_plan_json && job.diff_plan_json.lint_warnings.length > 0 && (
              <> · 存在 {job.diff_plan_json.lint_warnings.length} 条 lint 警告，应用时会被拦截。</>
            )}
          </div>
          {job.diff_plan_json && !job.diff_plan_json.format_report.ok && (
            <div className="alert-banner danger mt-8">
              <b>模板格式校验未通过</b>（以下违规项机械修正后仍存在，需修改模板或重新生成）：
              <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                {job.diff_plan_json.format_report.violations.slice(0, 8).map((v, i) => (
                  <li key={i}>
                    <span className="mono">{v.rule_id}</span> {v.rule_name}
                    {v.line != null ? `（第 ${v.line} 行）` : ''} — {v.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <span className="muted text-sm">
              {showDiff ? '逐块确认差异（可分别接受 / 拒绝）：' : '预览 AI 整理后的文档：'}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowDiff((v) => !v)}>
              {showDiff ? '查看预览' : '查看差异'}
            </button>
          </div>
          {showDiff ? (
            hunksReliable ? (
              <>
                {!allAccepted && (
                  <div className="alert-banner warning">
                    已拒绝 {hunks.length - accepted.filter(Boolean).length} 块：只应用选中的改动。
                    后端仍会按同一套模板格式 + lint 闸门校验，不通过则拒绝写入。
                  </div>
                )}
                <DiffHunkPicker
                  hunks={hunks}
                  accepted={accepted}
                  onChange={setAccepted}
                  emptyText="（AI 输出与原内容一致）"
                  maxHeight="50vh"
                />
              </>
            ) : (
              <pre className="diff-view" style={{ maxHeight: '50vh' }}>
                {job.diff_plan_json?.unified_diff || '（AI 输出与原内容一致）'}
              </pre>
            )
          ) : (
            <div
              className="md-preview md-preview-flow"
              style={{
                maxHeight: '50vh',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '12px 14px',
              }}
            >
              <div dangerouslySetInnerHTML={{ __html: renderMarkdown(job.output_content ?? '') }} />
            </div>
          )}
          <div className="section-title" style={{ marginTop: 10 }}>
            重新生成（带新指令）
          </div>
          <input
            className="input"
            placeholder="如：上次漏了「核心边界」章节，请补上"
            value={regenerateExtra}
            onChange={(e) => setRegenerateExtra(e.target.value)}
          />
        </>
      ) : job.status === 'failed' ? (
        <div className="state-block">
          <div className="alert-banner danger">AI 整理失败：{job.error ?? '未知错误'}</div>
          {job.diff_plan_json && !job.diff_plan_json.format_report.ok && (
            <div className="alert-banner danger mt-8">
              <b>模板格式校验未通过：</b>
              <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                {job.diff_plan_json.format_report.violations.slice(0, 8).map((v, i) => (
                  <li key={i}>
                    <span className="mono">{v.rule_id}</span> {v.rule_name}
                    {v.line != null ? `（第 ${v.line} 行）` : ''} — {v.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {job.diff_plan_json && job.diff_plan_json.lint_warnings.length > 0 && (
            <div className="item-list" style={{ marginTop: 10 }}>
              {job.diff_plan_json.lint_warnings.map((w, i) => (
                <div key={i} className="item">
                  <div className="item-title">
                    <span className="mono">{w.rule_name}</span>
                  </div>
                  <div className="item-sub">{w.suggestion}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="state-block">
          <div className="alert-banner info">任务已{job.status === 'applied' ? '应用并写入' : job.status === 'rejected' ? '拒绝' : '被替换'}。</div>
        </div>
      )}

      {confirming && job && (
        <ConfirmDialog
          title="确认应用 AI 结果"
          danger
          busy={acting}
          confirmText="确认写入"
          cancelText="取消"
          onConfirm={apply}
          onCancel={() => setConfirming(false)}
          message={
            <>
              <p>
                将把 AI 整理结果写入 <b className="mono">{job.file_path}</b>（Agent: {job.agent_id}）。
              </p>
              {allAccepted ? (
                <p className="hint">写入前自动备份当前版本；AI 输出需通过模板格式与 lint 检查。</p>
              ) : (
                <p className="hint">
                  本次<strong>只应用选中的 {accepted.filter(Boolean).length} 块改动</strong>
                  （其余 {hunks.length - accepted.filter(Boolean).length} 块保留原样）；
                  后端仍会按同一套模板格式 + lint 闸门校验，不通过则拒绝写入。写入前自动备份。
                </p>
              )}
            </>
          }
        />
      )}
    </Modal>
  );
}
