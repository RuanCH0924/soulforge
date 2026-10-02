import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type { PresetApplyPlan, PresetSummary } from '../types';
import { applyHunks, canRebuild, parseUnifiedDiff } from '../utils/unifiedDiff';
import type { DiffHunk } from '../utils/unifiedDiff';
import { ConfirmDialog } from './ConfirmDialog';
import { DiffHunkPicker } from './DiffHunkPicker';
import { Modal } from './Modal';

interface ApplyPresetModalProps {
  agentId: string;
  filePath: string;
  onClose: () => void;
  onDone: () => void;
}

/** 文件编辑页「应用预设」：选预设 → 生成 plan → diff 预览 → 确认写入（绝不直接覆盖） */
export function ApplyPresetModal({ agentId, filePath, onClose, onDone }: ApplyPresetModalProps) {
  const { push: toast } = useToast();
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string>('');
  const [extra, setExtra] = useState('');
  const [plan, setPlan] = useState<PresetApplyPlan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [applying, setApplying] = useState(false);
  // 「按块接受」：从 unified_diff 解析出的 hunk 与逐块勾选状态（默认全接受）
  const [hunks, setHunks] = useState<DiffHunk[]>([]);
  const [accepted, setAccepted] = useState<boolean[]>([]);
  const allAccepted = hunks.length === 0 || accepted.every(Boolean);
  // 解析可靠（全部接受能精确重建 proposed_content）时才允许「按块接受」；
  // 否则退回整段 diff + 整体应用，避免行粘连导致丢行。
  const hunksReliable = plan !== null && canRebuild(plan.current_snapshot, hunks, plan.proposed_content);

  useEffect(() => {
    api
      // scope=workbench：日志标准化预设专供大模型归并工作日志，不在本处列出
      .listPresets(undefined, 'workbench')
      .then((list) => {
        setPresets(list);
        if (list.length > 0) setSelected(list[0].id);
      })
      .catch((e) => toast(`加载预设失败：${(e as Error).message}`, 'error'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const generate = async () => {
    if (!selected) return;
    setPlanning(true);
    try {
      const p = await api.presetApplyPlan(selected, agentId, filePath, extra.trim() || undefined);
      setPlan(p);
      const parsed = parseUnifiedDiff(p.unified_diff);
      setHunks(parsed.hunks);
      setAccepted(parsed.hunks.map(() => true));
    } catch (e) {
      toast(`生成计划失败：${(e as Error).message}`, 'error');
    } finally {
      setPlanning(false);
    }
  };

  const execute = async () => {
    if (!plan) return;
    setApplying(true);
    try {
      if (allAccepted) {
        // 全部接受：走原路径（后端按 plan 写入，含格式校验结果）
        await api.presetApplyExecute(plan.preset_id, plan.plan_id, agentId, filePath);
        toast(`已应用预设并写入 ${filePath}（已自动备份原文件）`, 'success');
      } else {
        // 按块接受：只写入选中的改动。
        // 先核对磁盘内容仍是生成计划时的版本，避免覆盖计划生成后的外部改动（乐观锁）。
        const fresh = await api.readFile(agentId, filePath);
        if (fresh.content !== plan.current_snapshot) {
          toast('文件在生成计划后被改动，请点「返回选择」重新生成计划', 'warning');
          setConfirming(false);
          return;
        }
        const content = applyHunks(plan.current_snapshot, hunks, accepted);
        await api.writeFile(agentId, filePath, content, fresh.sha256);
        toast(`已写入选中的 ${accepted.filter(Boolean).length} 块改动到 ${filePath}（已自动备份）`, 'success');
      }
      setConfirming(false);
      onDone();
      onClose();
    } catch (e) {
      toast(`应用失败：${(e as Error).message}`, 'error');
    } finally {
      setApplying(false);
    }
  };

  const selectedPreset = presets.find((p) => p.id === selected);

  return (
    <Modal
      title={`应用预设 — ${filePath}`}
      onClose={onClose}
      width={860}
      footer={
        plan ? (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={() => { setPlan(null); setHunks([]); setAccepted([]); }} disabled={applying}>
              返回选择
            </button>
            <button className="btn btn-primary" onClick={() => setConfirming(true)} disabled={applying}>
              {applying && <span className="spinner" />}
              {allAccepted ? '确认写入' : `确认写入（${accepted.filter(Boolean).length} 块）`}
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={generate} disabled={planning || !selected}>
            {planning && <span className="spinner" />}
            生成计划
          </button>
        )
      }
    >
      {!plan ? (
        <>
          <div className="alert-banner info">
            应用预设会按预设结构补齐缺失章节，<b>不改动已有内容</b>；写入前自动备份原文件。走 plan + 确认两步。
          </div>
          <div className="section-title">选择预设（{presets.length} 个）</div>
          {loading ? (
            <div className="state-block">
              <div className="spinner-lg" />
              <div>正在加载预设...</div>
            </div>
          ) : presets.length === 0 ? (
            <div className="hint">
              没有可用于主工作台的预设。工作日志（WORKLOG）类预设专供大模型归并日志，
              请在「业务工具 → 日志标准化」界面使用。
            </div>
          ) : (
            <div className="checkbox-grid" style={{ maxHeight: 260 }}>
              {presets.map((p) => (
                <label key={p.id} className="checkbox-row">
                  <input
                    type="radio"
                    name="apply-preset"
                    checked={selected === p.id}
                    onChange={() => setSelected(p.id)}
                  />
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
          <div className="field mt-12">
            <label>附加指令（可选）</label>
            <input
              className="input"
              placeholder="如：保留『阅读策略』章节原内容不动"
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
            />
          </div>
          {selectedPreset?.description && (
            <div className="hint">说明：{selectedPreset.description}</div>
          )}
        </>
      ) : (
        <>
          <div className="alert-banner warning">
            共 {plan.lint_warnings.length} 条 lint 警告
            {plan.format_report && !plan.format_report.ok && (
              <> · {plan.format_report.violations.length} 处格式违规（机械修正后仍存在）</>
            )}
            ；请确认下方差异后写入（写入前自动备份）。
          </div>
          {plan.format_report && !plan.format_report.ok && (
            <div className="alert-banner danger mt-8">
              <b>模板格式校验未通过：</b>
              <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                {plan.format_report.violations.slice(0, 8).map((v, i) => (
                  <li key={i}>
                    <span className="mono">{v.rule_id}</span> {v.rule_name}
                    {v.line != null ? `（第 ${v.line} 行）` : ''} — {v.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.format_report && plan.format_report.ok && (
            <div className="alert-banner success mt-8">
              ✓ 输出文档符合模板格式规范（format_report.ok）
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <span className="badge-warn" style={{ background: 'rgba(59,130,246,.15)', color: 'var(--accent)' }}>
              {selectedPreset?.name ?? plan.preset_id}
            </span>
            <span className="muted text-sm">
              新增 {plan.proposed_content.length - plan.current_snapshot.length} 字符
            </span>
          </div>
          {hunksReliable ? (
            <>
              {!allAccepted && (
                <div className="alert-banner warning">
                  已拒绝 {hunks.length - accepted.filter(Boolean).length} 块：只写入选中的改动。
                  <b>按块写入不做整体格式校验</b>，写入前仍会自动备份原文件。
                </div>
              )}
              <DiffHunkPicker
                hunks={hunks}
                accepted={accepted}
                onChange={setAccepted}
                emptyText="（内容已符合预设结构，无需改动）"
              />
            </>
          ) : (
            <pre className="diff-view" style={{ maxHeight: '55vh' }}>
              {plan.unified_diff || '（内容已符合预设结构，无需改动）'}
            </pre>
          )}
        </>
      )}

      {confirming && plan && (
        <ConfirmDialog
          title="确认写入"
          danger
          busy={applying}
          confirmText="确认写入"
          cancelText="取消"
          onConfirm={execute}
          onCancel={() => setConfirming(false)}
          message={
            <>
              <p>
                将把预设应用到 <b className="mono">{plan.file_path}</b>（Agent: {plan.agent_id}）。
              </p>
              {allAccepted ? (
                <p className="hint">写入前会自动备份当前版本，可通过「历史」回滚。</p>
              ) : (
                <p className="hint">
                  本次<strong>只写入选中的 {accepted.filter(Boolean).length} 块改动</strong>
                  （其余 {hunks.length - accepted.filter(Boolean).length} 块保留原样）；不做整体格式校验。
                  写入前会自动备份当前版本，可通过「历史」回滚。
                </p>
              )}
            </>
          }
        />
      )}
    </Modal>
  );
}
