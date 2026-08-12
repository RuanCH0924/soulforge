import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type { PresetApplyPlan, PresetSummary } from '../types';
import { ConfirmDialog } from './ConfirmDialog';
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

  useEffect(() => {
    api
      .listPresets()
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
      await api.presetApplyExecute(plan.preset_id, plan.plan_id, agentId, filePath);
      toast(`已应用预设并写入 ${filePath}（已自动备份原文件）`, 'success');
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
            <button className="btn" onClick={() => setPlan(null)} disabled={applying}>
              返回选择
            </button>
            <button className="btn btn-primary" onClick={() => setConfirming(true)} disabled={applying}>
              {applying && <span className="spinner" />}
              确认写入
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
                  <span style={{ minWidth: 0 }}>
                    {p.name}
                    <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                      {p.target_file_type}
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
            <div className="alert-banner danger" style={{ marginTop: 8 }}>
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
            <div className="alert-banner success" style={{ marginTop: 8 }}>
              ✓ 输出文档符合模板格式规范（format_report.ok）
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <span className="badge-warn" style={{ background: 'rgba(59,130,246,.15)', color: 'var(--accent)' }}>
              {selectedPreset?.name ?? plan.preset_id}
            </span>
            <span className="muted" style={{ fontSize: 12 }}>
              新增 {plan.proposed_content.length - plan.current_snapshot.length} 字符
            </span>
          </div>
          <pre className="diff-view" style={{ maxHeight: '55vh' }}>
            {plan.unified_diff || '（内容已符合预设结构，无需改动）'}
          </pre>
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
              <p className="hint">写入前会自动备份当前版本，可通过「历史」回滚。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
