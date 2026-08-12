import { useEffect, useState } from 'react';
import { api } from '../api';
import { isRoleVisible, useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';
import type { AgentInfo, SyncPlanResult } from '../types';
import { formatBytes, similarityColor, similarityPercent } from '../utils/format';

interface SyncModalProps {
  agents: AgentInfo[];
  onClose: () => void;
  onDone: () => void;
}

export function SyncModal({ agents, onClose, onDone }: SyncModalProps) {
  const { push: toast } = useToast();
  const { settings } = useSettings();
  const [src, setSrc] = useState<string>(agents[0]?.id ?? '');
  const [dst, setDst] = useState<string>(agents[1]?.id ?? agents[0]?.id ?? '');
  const [srcFiles, setSrcFiles] = useState<string[]>([]);
  const [planFiles, setPlanFiles] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<SyncPlanResult | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [confirmExec, setConfirmExec] = useState(false);

  useEffect(() => {
    if (!src) return;
    let cancelled = false;
    api
      .listFiles(src)
      .then((fs) => {
        if (!cancelled) {
          // 与文件面板保持一致：隐藏的角色（MEMORY/SKILL/META/OTHER）不进入待选列表
          const paths = fs
            .filter((f) => isRoleVisible(f.role, settings))
            .map((f) => f.path)
            .sort((a, b) => a.localeCompare(b));
          setSrcFiles(paths);
          // 默认不勾选任何文件，由用户按需选择要生成计划的文件
          setPlanFiles(new Set());
        }
      })
      .catch((e) => {
        if (!cancelled) toast(`加载文件失败：${(e as Error).message}`, 'error');
      });
    return () => {
      cancelled = true;
    };
  }, [src, settings, toast]);

  function togglePlanFile(p: string) {
    setPlanFiles((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  async function generatePlan() {
    if (!src || !dst || src === dst) {
      toast('请选择两个不同的 Agent', 'warning');
      return;
    }
    if (planFiles.size === 0) {
      toast('请至少选择一个文件', 'warning');
      return;
    }
    setPlanning(true);
    try {
      const res = await api.syncPlan(src, dst, [...planFiles]);
      setPlan(res);
      setChecked(new Set()); // 铁律：默认全部不勾选，用户确认影响范围
    } catch (e) {
      toast(`生成同步计划失败：${(e as Error).message}`, 'error');
    } finally {
      setPlanning(false);
    }
  }

  function toggleChecked(p: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  async function executeSync() {
    if (!plan) return;
    setExecuting(true);
    try {
      const res = await api.syncExecute(plan.plan_id, [...checked]);
      const okCount = res.results.filter((r) => r.status === 'ok').length;
      toast(`同步完成：${okCount} 个文件已写入 ${plan.dst_agent}`, 'success');
      onDone();
      onClose();
    } catch (e) {
      toast(`同步失败：${(e as Error).message}`, 'error');
    } finally {
      setExecuting(false);
      setConfirmExec(false);
    }
  }

  const dstOptions = agents.filter((a) => a.id !== src);

  return (
    <Modal
      title="跨 Agent 同步"
      onClose={onClose}
      width={820}
      footer={
        plan ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setPlan(null)} disabled={executing}>
              返回修改
            </button>
            <button
              className="btn btn-primary"
              disabled={checked.size === 0 || executing}
              onClick={() => setConfirmExec(true)}
            >
              {executing && <span className="spinner" />}
              执行同步（{checked.size} 个文件）
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={generatePlan} disabled={planning}>
            {planning && <span className="spinner" />}
            生成同步计划
          </button>
        )
      }
    >
      {!plan ? (
        <>
          <div className="alert-banner info">
            同步分两步：先生成差异计划，再勾选要同步的文件执行。绝不整文件覆盖。
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>源 Agent（提供文件）</label>
              <select className="select" value={src} onChange={(e) => setSrc(e.target.value)}>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name || a.id}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>目标 Agent（接收文件）</label>
              <select className="select" value={dst} onChange={(e) => setDst(e.target.value)}>
                {dstOptions.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name || a.id}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="section-title">选择要生成计划的文件（{planFiles.size} / {srcFiles.length}）</div>
          <div className="checkbox-grid">
            {srcFiles.map((p) => (
              <label key={p} className="checkbox-row">
                <input type="checkbox" checked={planFiles.has(p)} onChange={() => togglePlanFile(p)} />
                <span className="mono" style={{ fontSize: 12 }} title={p}>
                  {p}
                </span>
              </label>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="alert-banner warning">
            计划已生成（{plan.files.length} 个文件）。请逐个查看差异，勾选确认要同步的文件——<b>默认全部不勾选</b>。
          </div>
          {plan.files.map((f) => {
            const isChecked = checked.has(f.path);
            return (
              <div
                key={f.path}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  marginBottom: 12,
                  background: 'var(--bg-base)',
                }}
              >
                <label className="checkbox-row" style={{ padding: '8px 10px', cursor: 'pointer' }}>
                  <input type="checkbox" checked={isChecked} onChange={() => toggleChecked(f.path)} />
                  <span className="mono sync-plan-path" style={{ fontWeight: 700 }} title={f.path}>
                    {f.path}
                  </span>
                  <span
                    className={`similarity-bar ${similarityColor(f.similarity)}`}
                    style={{ margin: 0, flex: 'none', minWidth: 120 }}
                  >
                    <div className="similarity-track">
                      <div className="similarity-fill" style={{ width: similarityPercent(f.similarity) }} />
                    </div>
                    <span>{similarityPercent(f.similarity)}</span>
                  </span>
                  <span className="muted" style={{ fontSize: 11 }}>
                    {formatBytes(f.size_src)} → {formatBytes(f.size_dst)}
                  </span>
                </label>
                <div style={{ padding: '0 10px 10px' }}>
                  <div dangerouslySetInnerHTML={{ __html: f.html_diff }} />
                </div>
              </div>
            );
          })}
        </>
      )}

      {confirmExec && plan && (
        <ConfirmDialog
          title="确认执行同步"
          danger
          busy={executing}
          confirmText="确认同步"
          cancelText="取消"
          onConfirm={executeSync}
          onCancel={() => setConfirmExec(false)}
          message={
            <>
              <p>
                将把 <b>{checked.size}</b> 个文件从 <b>{plan.src_agent}</b> 同步到{' '}
                <b>{plan.dst_agent}</b>：
              </p>
              <ul style={{ paddingLeft: 20 }}>
                {[...checked].map((p) => (
                  <li key={p} className="mono">
                    {p}
                  </li>
                ))}
              </ul>
              <p className="hint">每个文件写入前会自动备份目标 Agent 的当前版本。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
