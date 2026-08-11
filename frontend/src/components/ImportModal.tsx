import { useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';
import type { AgentInfo, ImportPreviewResult, ImportStrategy } from '../types';
import { formatBytes } from '../utils/format';

interface ImportModalProps {
  agents: AgentInfo[];
  onClose: () => void;
  onDone: () => void;
}

const STRATEGY_LABEL: Record<ImportStrategy, string> = {
  skip: '跳过（默认）',
  merge: '合并',
  overwrite: '覆盖',
};

export function ImportModal({ agents, onClose, onDone }: ImportModalProps) {
  const { push: toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [targetAgent, setTargetAgent] = useState<string>(agents[0]?.id ?? '');
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [strategies, setStrategies] = useState<Record<string, ImportStrategy>>({});
  const [previewing, setPreviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirmExec, setConfirmExec] = useState(false);

  function onPickFile(f: File | null) {
    setFile(f);
    setFileName(f ? f.name : '');
    setPreview(null);
  }

  async function doPreview() {
    if (!file) {
      toast('请先选择要导入的 tar.gz 文件', 'warning');
      return;
    }
    setPreviewing(true);
    try {
      const res = await api.importPreview(file, targetAgent);
      setPreview(res);
      // 铁律：冲突文件默认全部 skip
      const defaults: Record<string, ImportStrategy> = {};
      res.conflicts.forEach((c) => {
        defaults[c.path] = 'skip';
      });
      setStrategies(defaults);
    } catch (e) {
      toast(`预览失败：${(e as Error).message}`, 'error');
    } finally {
      setPreviewing(false);
    }
  }

  async function doImport() {
    if (!preview) return;
    setImporting(true);
    try {
      const res = await api.importExecute(preview.upload_id, targetAgent, strategies);
      const acted = res.results.filter((r) => r.action !== 'skipped').length;
      toast(`导入完成：${acted} 个文件已写入 ${targetAgent}`, 'success');
      onDone();
      onClose();
    } catch (e) {
      toast(`导入失败：${(e as Error).message}`, 'error');
    } finally {
      setImporting(false);
      setConfirmExec(false);
    }
  }

  const conflictPaths = new Set((preview?.conflicts ?? []).map((c) => c.path));

  return (
    <Modal
      title="导入 Prompt Pack"
      onClose={onClose}
      width={720}
      footer={
        preview ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setPreview(null)} disabled={importing}>
              返回
            </button>
            <button
              className="btn btn-primary"
              disabled={importing}
              onClick={() => setConfirmExec(true)}
            >
              {importing && <span className="spinner" />}
              执行导入
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={doPreview} disabled={previewing || !file}>
            {previewing && <span className="spinner" />}
            预览导入
          </button>
        )
      }
    >
      {!preview ? (
        <>
          <div className="field">
            <label>导入文件（.tar.gz）</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".tar.gz,.tgz,.gz"
              style={{ display: 'none' }}
              onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="input"
                placeholder="选择文件"
                readOnly
                value={fileName}
                onClick={() => fileInputRef.current?.click()}
              />
              <button className="btn" onClick={() => fileInputRef.current?.click()}>
                选择文件
              </button>
            </div>
          </div>
          <div className="field">
            <label>目标 Agent</label>
            <select className="select" value={targetAgent} onChange={(e) => setTargetAgent(e.target.value)}>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name || a.id}
                </option>
              ))}
            </select>
          </div>
          <div className="alert-banner info">导入前会自动备份目标 Agent 的现有文件；冲突文件逐个选择处理方式。</div>
        </>
      ) : (
        <>
          <div className="field" style={{ fontSize: 13 }}>
            <b>导入包信息</b>
            <div className="hint">
              Agent: <span className="mono">{preview.manifest.agent_id}</span> · 导出时间:{' '}
              {preview.manifest.export_time} · 文件数:{' '}
              {preview.manifest.files.length} · 目标:{' '}
              <span className="mono">{preview.target_agent_id}</span>
            </div>
          </div>

          <div className="section-title">冲突文件（默认全部跳过，请逐个确认）</div>
          {preview.conflicts.length === 0 ? (
            <div className="hint" style={{ color: 'var(--success)' }}>
              没有冲突文件，导入将全部直接写入。
            </div>
          ) : (
            preview.conflicts.map((c) => (
              <div key={c.path} className="import-conflict">
                <span className="conflict-tag">冲突</span>
                <span className="conflict-path">{c.path}</span>
                <span className="muted" style={{ fontSize: 11, flex: 'none' }}>
                  {c.exists_in_target && c.target_size != null ? `目标已存在 ${formatBytes(c.target_size)}` : '目标不存在'}
                </span>
                <select
                  className="select"
                  value={strategies[c.path] ?? 'skip'}
                  onChange={(e) =>
                    setStrategies((prev) => ({ ...prev, [c.path]: e.target.value as ImportStrategy }))
                  }
                >
                  {(Object.keys(STRATEGY_LABEL) as ImportStrategy[]).map((s) => (
                    <option key={s} value={s}>
                      {STRATEGY_LABEL[s]}
                    </option>
                  ))}
                </select>
              </div>
            ))
          )}

          <div className="section-title">将写入的文件（{preview.manifest.files.length} 个）</div>
          <div className="item-list" style={{ maxHeight: 180, overflowY: 'auto' }}>
            {preview.manifest.files.map((f) => (
              <div key={f.path} className="item" style={{ cursor: 'default' }}>
                <div className="item-title" style={{ fontWeight: 400 }}>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {f.path}
                  </span>
                  {conflictPaths.has(f.path) && (
                    <span className="muted" style={{ fontSize: 11 }}>
                      （{STRATEGY_LABEL[strategies[f.path] ?? 'skip']}）
                    </span>
                  )}
                  <span className="muted" style={{ fontSize: 11 }}>
                    {formatBytes(f.size)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {confirmExec && preview && (
        <ConfirmDialog
          title="确认导入"
          danger
          busy={importing}
          confirmText="确认导入"
          cancelText="取消"
          onConfirm={doImport}
          onCancel={() => setConfirmExec(false)}
          message={
            <>
              <p>
                将把 <b>{preview.manifest.files.length}</b> 个文件导入到 <b>{preview.target_agent_id}</b>
                。
              </p>
              <p className="hint">冲突文件将按上面选择的策略处理；写入前自动备份现有文件。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
